import { describe, expect, test } from "vitest";
import { ApiError, type Condition, type Question, type SolveResult } from "./api";
import { runExperiment, type Cell } from "./runner";

const CONDS: Condition[] = ["none", "brief", "page"];
const questions = (n: number): Question[] =>
  Array.from({ length: n }, (_, i) => ({ id: `q${i}`, week: "week09", type: "mc", q: `문제 ${i}`, options: ["a", "b"], concept: "c" }));
const ok = (qid: string, condition: Condition, correct = true): SolveResult =>
  ({ qid, condition, pred: 0, correct, input_tokens: 10, output_tokens: 2, ms: 1 });
const tick = () => new Promise((r) => setTimeout(r, 0));

function recorder() {
  const cells: Array<[string, Condition, Cell]> = [];
  return { cells, onCell: (qid: string, c: Condition, cell: Cell) => void cells.push([qid, c, cell]) };
}
const finalStatus = (cells: Array<[string, Condition, Cell]>) => {
  const m = new Map<string, Cell["status"]>();
  for (const [q, c, cell] of cells) m.set(`${q}/${c}`, cell.status);
  return m;
};

describe("runExperiment", () => {
  test("runs every question × condition once with at most 3 in flight", async () => {
    const calls: string[] = [];
    let inFlight = 0, maxInFlight = 0;
    const rec = recorder();
    const out = await runExperiment({
      questions: questions(5), conditions: CONDS, signal: new AbortController().signal, onCell: rec.onCell, retryDelayMs: 0,
      solve: async (qid, c) => {
        calls.push(`${qid}/${c}`); inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
        await tick(); inFlight--; return ok(qid, c, c !== "none");
      },
    });
    expect(out.stopped).toBe("done");
    expect(calls).toHaveLength(15);
    expect(new Set(calls).size).toBe(15);
    expect(maxInFlight).toBeLessThanOrEqual(3);
    const st = finalStatus(rec.cells);
    expect(st.get("q0/none")).toBe("wrong");
    expect(st.get("q0/page")).toBe("ok");
    expect([...st.values()].every((s) => s === "ok" || s === "wrong")).toBe(true);
  });

  test("retries a failed cell once, then marks it failed and continues", async () => {
    const attempts = new Map<string, number>();
    const rec = recorder();
    const out = await runExperiment({
      questions: questions(3), conditions: ["none"], signal: new AbortController().signal, onCell: rec.onCell, retryDelayMs: 0,
      solve: async (qid, c) => {
        attempts.set(qid, (attempts.get(qid) ?? 0) + 1);
        if (qid === "q1") throw new ApiError(502, "모델 호출에 실패했습니다");
        return ok(qid, c);
      },
    });
    expect(out.stopped).toBe("done");
    expect(attempts.get("q1")).toBe(2);
    const st = finalStatus(rec.cells);
    expect(st.get("q1/none")).toBe("failed");
    expect(st.get("q0/none")).toBe("ok");
    expect(st.get("q2/none")).toBe("ok");
  });

  test("a cell that fails once and then succeeds is not failed", async () => {
    let first = true;
    const rec = recorder();
    await runExperiment({
      questions: questions(1), conditions: ["none"], signal: new AbortController().signal, onCell: rec.onCell, retryDelayMs: 0,
      solve: async (qid, c) => { if (first) { first = false; throw new ApiError(429, "많음"); } return ok(qid, c); },
    });
    expect(finalStatus(rec.cells).get("q0/none")).toBe("ok");
  });

  test("stops with 'too-many-failures' after 5 consecutive failed cells", async () => {
    const started = new Set<string>();
    const out = await runExperiment({
      questions: questions(20), conditions: ["none"], signal: new AbortController().signal, onCell: () => {}, concurrency: 1, retryDelayMs: 0,
      solve: async (qid) => { started.add(qid); throw new ApiError(502, "실패"); },
    });
    expect(out.stopped).toBe("too-many-failures");
    expect(started.size).toBe(5);
  });

  test("a success resets the consecutive-failure count", async () => {
    const out = await runExperiment({
      questions: questions(12), conditions: ["none"], signal: new AbortController().signal, onCell: () => {}, concurrency: 1, retryDelayMs: 0,
      solve: async (qid, c) => { if (Number(qid.slice(1)) % 5 === 4) return ok(qid, c); throw new ApiError(502, "실패"); },
    });
    expect(out.stopped).toBe("done");
  });

  test("stops with 'disabled' on a 503 and starts no further requests", async () => {
    const started: string[] = [];
    const out = await runExperiment({
      questions: questions(10), conditions: ["none"], signal: new AbortController().signal, onCell: () => {}, concurrency: 1, retryDelayMs: 0,
      solve: async (qid, c) => { started.push(qid); if (qid === "q2") throw new ApiError(503, "꺼짐"); return ok(qid, c); },
    });
    expect(out.stopped).toBe("disabled");
    expect(started).toEqual(["q0", "q1", "q2"]);
  });

  test("abort: no new requests start and late responses do not call onCell", async () => {
    const ctrl = new AbortController();
    const started: string[] = [];
    const rec = recorder();
    const release: Array<() => void> = [];
    const p = runExperiment({
      questions: questions(10), conditions: ["none"], signal: ctrl.signal, onCell: rec.onCell, concurrency: 2, retryDelayMs: 0,
      solve: (qid, c) => { started.push(qid); return new Promise((res) => release.push(() => res(ok(qid, c)))); },
    });
    await tick();
    expect(started).toEqual(["q0", "q1"]);
    ctrl.abort();
    release.forEach((r) => r());
    const out = await p;
    expect(out.stopped).toBe("aborted");
    expect(started).toEqual(["q0", "q1"]);
    expect(rec.cells.filter(([, , cell]) => cell.status === "ok" || cell.status === "wrong")).toHaveLength(0);
  });

  test("already-aborted signal starts nothing", async () => {
    const ctrl = new AbortController(); ctrl.abort();
    let n = 0;
    const out = await runExperiment({
      questions: questions(3), conditions: CONDS, signal: ctrl.signal, onCell: () => {},
      solve: async (qid, c) => { n++; return ok(qid, c); },
    });
    expect(out.stopped).toBe("aborted");
    expect(n).toBe(0);
  });

  test("waits before retrying a failed cell", async () => {
    const times: number[] = [];
    await runExperiment({
      questions: questions(1), conditions: ["none"], signal: new AbortController().signal, onCell: () => {}, retryDelayMs: 40,
      solve: async (qid, c) => { times.push(Date.now()); if (times.length === 1) throw new ApiError(429, "많음"); return ok(qid, c); },
    });
    expect(times).toHaveLength(2);
    expect(times[1] - times[0]).toBeGreaterThanOrEqual(35);
  });

  test("does not retry a 400 (the request itself is wrong)", async () => {
    let n = 0;
    const rec = recorder();
    await runExperiment({
      questions: questions(1), conditions: ["none"], signal: new AbortController().signal, onCell: rec.onCell, retryDelayMs: 0,
      solve: async () => { n++; throw new ApiError(400, "잘못된 요청"); },
    });
    expect(n).toBe(1);
    expect(finalStatus(rec.cells).get("q0/none")).toBe("failed");
  });
});
