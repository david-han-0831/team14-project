import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ClosedNotice from "./components/ClosedNotice";
import ConditionCards from "./components/ConditionCards";
import EvolveLog from "./components/EvolveLog";
import ProgressGrid, { type Cells } from "./components/ProgressGrid";
import RecordedCompare from "./components/RecordedCompare";
import ResultBars, { type ConditionStat } from "./components/ResultBars";
import RunControls from "./components/RunControls";
import UsageLine from "./components/UsageLine";
import { CONDITIONS, getBank, getHealth, getReports, postSolve, type Condition, type Health, type Question, type Report, type Round, type SetName } from "./lib/api";
import { CONDITION_LABEL, SET_LABEL, SITE_URL } from "./lib/labels";
import { runExperiment, type StopReason } from "./lib/runner";
import { accuracy, bootstrapCI } from "./lib/stats";
import { canRun, type Phase } from "./lib/ui";

const SET_WEEKS: Record<SetName, string> = { week09: "week09", seed: "week02,week04,week08" };
const STOP_TEXT: Partial<Record<StopReason, string>> = {
  aborted: "실행을 멈췄습니다. 지금까지 채워진 칸만으로 계산한 값입니다.",
  "too-many-failures": "연속으로 실패해 실행을 멈췄습니다. 잠시 뒤 다시 시도해 주세요.",
};

export default function App() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [health, setHealth] = useState<Health | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [rounds, setRounds] = useState<Round[]>([]);
  const [setName, setSetName] = useState<SetName>("week09");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loadedSet, setLoadedSet] = useState<SetName | null>(null); // 화면의 문항이 어느 세트 것인지
  const [reloadKey, setReloadKey] = useState(0); // "다시 시도" 때 문항도 다시 받는다
  const [cells, setCells] = useState<Cells>({});
  const [stopReason, setStopReason] = useState<StopReason | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ctrlRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    setPhase("loading");
    setError(null);
    setReloadKey((k) => k + 1);
    try {
      const [h, r] = await Promise.all([getHealth(), getReports()]);
      setHealth(h);
      setReports(r.reports);
      setRounds(r.rounds);
      setPhase(h.live ? "ready" : "closed");
    } catch {
      setError("서버에 연결하지 못했습니다.");
      setPhase("error");
    }
  }, []);

  useEffect(() => {
    void load();
    return () => ctrlRef.current?.abort();
  }, [load]);

  // 세트가 바뀌면 문항을 다시 받고 표를 비운다 (실행 중에는 세트를 바꿀 수 없다)
  useEffect(() => {
    if (!health?.live) return;
    let cancelled = false;
    // 새 세트를 받는 동안 이전 세트 문항으로 실행되지 않게 먼저 비운다
    setQuestions([]);
    setLoadedSet(null);
    setCells({});
    getBank(setName)
      .then((b) => {
        if (cancelled) return;
        setQuestions(b.questions);
        setLoadedSet(b.set);
        setCells({});
        setStopReason(null);
        setPhase((p) => (p === "finished" ? "ready" : p));
      })
      .catch(() => {
        if (cancelled) return;
        setError("문항을 불러오지 못했습니다.");
        setPhase("error");
      });
    return () => {
      cancelled = true;
    };
  }, [health?.live, setName, reloadKey]);

  const run = useCallback(() => {
    if (!canRun({ phase, setName, loadedSet, questionCount: questions.length })) return;
    ctrlRef.current?.abort(); // 혹시 남아 있는 이전 실행을 끊는다
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    const current = () => ctrlRef.current === ctrl; // 이전 실행의 늦은 응답이 새 표에 섞이지 않게
    setCells({});
    setStopReason(null);
    setPhase("running");
    void runExperiment({
      questions,
      conditions: CONDITIONS,
      solve: postSolve,
      signal: ctrl.signal,
      onCell: (qid, c, cell) => {
        if (!current()) return;
        setCells((prev) => ({ ...prev, [qid]: { ...prev[qid], [c]: cell } }));
      },
    }).then(({ stopped }) => {
      if (!current()) return;
      if (stopped === "disabled") {
        setHealth((h) => (h ? { ...h, live: false } : h));
        setPhase("closed");
        return;
      }
      setStopReason(stopped);
      setPhase("finished");
    });
  }, [phase, questions, setName, loadedSet]);

  const stop = useCallback(() => ctrlRef.current?.abort(), []);

  const stats = useMemo(() => {
    const out = {} as Record<Condition, ConditionStat>;
    for (const c of CONDITIONS) {
      const values: number[] = [];
      let failed = 0;
      for (const q of questions) {
        const s = cells[q.id]?.[c]?.status;
        if (s === "ok") values.push(1);
        else if (s === "wrong") values.push(0);
        else if (s === "failed") failed++;
      }
      out[c] = { acc: accuracy(values), ci: bootstrapCI(values), answered: values.length, failed };
    }
    return out;
  }, [cells, questions]);

  const usage = useMemo(() => {
    let calls = 0, input = 0, output = 0;
    for (const row of Object.values(cells))
      for (const cell of Object.values(row))
        if (cell?.result) {
          calls++;
          input += cell.result.input_tokens;
          output += cell.result.output_tokens;
        }
    return { calls, input, output };
  }, [cells]);

  const total = questions.length * CONDITIONS.length;
  const done = CONDITIONS.reduce((n, c) => n + stats[c].answered + stats[c].failed, 0);
  const recovered = useMemo(
    () => questions.filter((q) => cells[q.id]?.none?.status === "wrong" && (cells[q.id]?.brief?.status === "ok" || cells[q.id]?.page?.status === "ok")),
    [cells, questions],
  );
  const reportFor = (s: SetName) => reports.find((r) => r.weeks === SET_WEEKS[s]);
  const hasRun = done > 0;

  return (
    <>
      <header className="site-header">
        <div className="wrap">
          <a className="brand" href={SITE_URL}>
            <span className="dot" aria-hidden="true" />
            EvoLecture · Team14
          </a>
          <a className="back" href={SITE_URL}>
            주차별 공부 사이트로
          </a>
        </div>
      </header>

      <main className="wrap">
        <section className="hero">
          <p className="eyebrow">E3 · 하네스 효과 실험</p>
          <h1>라이브 실험실 — 자료를 주면 정답률이 오르는가</h1>
          <p className="lead">
            작은 모델에게 수업 문제를 세 가지 조건으로 풀립니다. 아무 자료 없이, 주차 브리프와 함께, 공개 사이트 페이지와 함께. 버튼을 누르면
            이 페이지가 문항을 하나씩 실제로 풀리고, 채점 결과가 아래 표에 채워집니다.
          </p>
        </section>

        {phase === "loading" && <p className="muted">불러오는 중입니다.</p>}

        {phase === "error" && (
          <div className="notice" role="alert">
            <strong>{error}</strong>
            <p>
              <button type="button" className="btn" onClick={() => void load()}>
                다시 시도
              </button>
            </p>
          </div>
        )}

        {phase === "closed" && (
          <>
            <ClosedNotice />
            <h2>세 가지 조건</h2>
            <ConditionCards />
            {(Object.keys(SET_LABEL) as SetName[]).map((s) => (
              <section key={s}>
                <h2>기록된 결과 · {SET_LABEL[s]}</h2>
                <RecordedCompare report={reportFor(s)} stats={null} />
              </section>
            ))}
          </>
        )}

        {health?.live && (phase === "ready" || phase === "running" || phase === "finished") && (
          <>
            <h2>세 가지 조건</h2>
            <ConditionCards />

            <h2>실행</h2>
            <RunControls
              health={health}
              setName={setName}
              running={phase === "running"}
              done={done}
              total={total}
              runnable={canRun({ phase, setName, loadedSet, questionCount: questions.length })}
              onSet={setSetName}
              onRun={run}
              onStop={stop}
            />
            {phase === "finished" && stopReason && STOP_TEXT[stopReason] && (
              <p className="notice inline" role="status">
                {STOP_TEXT[stopReason]}
              </p>
            )}
            <ProgressGrid questions={questions} cells={cells} />

            <h2>결과</h2>
            <ResultBars stats={stats} />
            <p className="muted small">신뢰구간은 문항 단위 부트스트랩으로 브라우저에서 계산합니다. 실패한 칸은 정답률에서 뺍니다.</p>
            {phase === "finished" && (
              <div className="recovered">
                <h3>자료 없이는 틀리고, 자료가 있을 때 맞힌 문항 {recovered.length}개</h3>
                {recovered.length > 0 ? (
                  <ul>
                    {recovered.map((q) => (
                      <li key={q.id}>
                        <code>{q.id}</code> <span className="concept">{q.concept}</span> {q.q.slice(0, 60)}
                        {q.q.length > 60 ? "…" : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">이번 실행에서는 없었습니다.</p>
                )}
              </div>
            )}

            <h2>기록된 결과와 비교 · {SET_LABEL[setName]}</h2>
            <RecordedCompare report={reportFor(setName)} stats={hasRun ? stats : null} />

            {hasRun && (
              <>
                <h2>사용량</h2>
                <UsageLine calls={usage.calls} input={usage.input} output={usage.output} />
              </>
            )}
          </>
        )}
        {(phase === "closed" || phase === "ready" || phase === "running" || phase === "finished") && (
          <section id="evolve-log">
            <h2>진화 기록 — 언제, 무엇을 고쳤나</h2>
            <EvolveLog rounds={rounds} />
          </section>
        )}
      </main>

      <footer className="site-footer">
        <div className="wrap">
          Team14 · 최신딥러닝이론및응용 · 풀이 프롬프트와 채점은 저장소의 <code>evolve/</code> 코드를 그대로 씁니다. 조건 이름:{" "}
          {CONDITIONS.map((c) => CONDITION_LABEL[c]).join(" / ")}
        </div>
      </footer>
    </>
  );
}
