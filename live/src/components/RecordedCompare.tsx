import { CONDITIONS, type Condition, type Report } from "../lib/api";
import { CONDITION_LABEL } from "../lib/labels";
import { formatPct } from "../lib/stats";
import type { ConditionStat } from "./ResultBars";

interface Props {
  report: Report | undefined;
  stats: Record<Condition, ConditionStat> | null; // null 이면 기록된 결과만 보여 준다
}

export default function RecordedCompare({ report, stats }: Props) {
  if (!report) return <p className="muted">이 세트로 기록된 결과가 아직 없습니다.</p>;
  const date = report.date ? report.date.slice(0, 10) : "날짜 미기록";
  return (
    <div className="table-wrap">
      <table className="compare">
        <thead>
          <tr>
            <th scope="col">조건</th>
            {stats && <th scope="col">이번 실행</th>}
            <th scope="col">기록된 결과 ({date})</th>
          </tr>
        </thead>
        <tbody>
          {CONDITIONS.map((c) => {
            const rec = report.runs.find((r) => r.condition === c);
            return (
              <tr key={c}>
                <th scope="row">{CONDITION_LABEL[c]}</th>
                {stats && <td>{formatPct(stats[c].acc)}</td>}
                <td>
                  {rec ? `${formatPct(rec.acc)} (${rec.n}문항, CI ${formatPct(rec.acc_ci95[0])}–${formatPct(rec.acc_ci95[1])})` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="muted small">
        기록된 결과는 같은 코드(<code>evolve/experiments.py e3</code>)를 로컬에서 돌려 저장소에 남긴 값입니다. 모델 {report.model}, 문항당 1회.
      </p>
    </div>
  );
}
