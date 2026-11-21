// 문항 × 조건 실행기. 동시 요청 수 제한, 칸마다 1회 재시도, 취소, 연속 실패 시 중단.
import { ApiError, type Condition, type Question, type SolveResult } from "./api";

export type CellStatus = "idle" | "running" | "ok" | "wrong" | "failed";
export interface Cell {
  status: CellStatus;
  result?: SolveResult;
}
export type StopReason = "done" | "aborted" | "disabled" | "too-many-failures";

export interface RunOptions {
  questions: Question[];
  conditions: Condition[];
  solve: (qid: string, condition: Condition, signal: AbortSignal) => Promise<SolveResult>;
  signal: AbortSignal;
  onCell: (qid: string, condition: Condition, cell: Cell) => void;
  concurrency?: number;
}

export const MAX_CONSECUTIVE_FAILURES = 5;

export async function runExperiment(opts: RunOptions): Promise<{ stopped: StopReason }> {
  const { questions, conditions, solve, signal, onCell } = opts;
  const concurrency = Math.max(1, opts.concurrency ?? 3);
  const tasks: Array<[string, Condition]> = [];
  for (const q of questions) for (const c of conditions) tasks.push([q.id, c]);

  let next = 0;
  let consecutiveFailures = 0;
  let stop: StopReason | null = null;
  const halted = () => stop !== null || signal.aborted;

  async function attempt(qid: string, c: Condition): Promise<SolveResult | "failed" | "disabled"> {
    for (let i = 0; i < 2; i++) {
      try {
        return await solve(qid, c, signal);
      } catch (e) {
        if (e instanceof ApiError && e.status === 503) return "disabled";
        if (halted()) return "failed";
      }
    }
    return "failed";
  }

  async function worker() {
    while (!halted() && next < tasks.length) {
      const [qid, c] = tasks[next++];
      onCell(qid, c, { status: "running" });
      const r = await attempt(qid, c);
      if (halted()) {
        onCell(qid, c, { status: "idle" }); // 멈춘 뒤 도착한 응답은 버린다
        return;
      }
      if (r === "disabled") {
        stop = "disabled";
        onCell(qid, c, { status: "idle" });
        return;
      }
      if (r === "failed") {
        onCell(qid, c, { status: "failed" });
        if (++consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) stop = "too-many-failures";
        continue;
      }
      consecutiveFailures = 0;
      onCell(qid, c, { status: r.correct ? "ok" : "wrong", result: r });
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, tasks.length) }, worker));
  if (stop) return { stopped: stop };
  return { stopped: signal.aborted ? "aborted" : "done" };
}
