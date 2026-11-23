import { CONDITIONS, type Condition } from "../lib/api";
import { CONDITION_LABEL } from "../lib/labels";
import { formatPct } from "../lib/stats";

export interface ConditionStat {
  acc: number | null;
  ci: [number, number] | null;
  answered: number;
  failed: number;
}

export default function ResultBars({ stats }: { stats: Record<Condition, ConditionStat> }) {
  return (
    <div className="bars">
      {CONDITIONS.map((c) => {
        const s = stats[c];
        return (
          <div key={c} className={`bar-row condition-${c}`}>
            <div className="bar-label">{CONDITION_LABEL[c]}</div>
            <div className="bar-track" role="img" aria-label={`${CONDITION_LABEL[c]} 정답률 ${formatPct(s.acc)}`}>
              {s.acc !== null && <div className="bar-fill" style={{ width: `${s.acc * 100}%` }} />}
              {s.ci && (
                <div className="bar-ci" style={{ left: `${s.ci[0] * 100}%`, width: `${Math.max((s.ci[1] - s.ci[0]) * 100, 0.6)}%` }} />
              )}
            </div>
            <div className="bar-value">
              <strong>{formatPct(s.acc)}</strong>
              <span>
                {s.answered > 0 ? `${s.answered}문항` : "아직 없음"}
                {s.ci ? ` · CI ${formatPct(s.ci[0])}–${formatPct(s.ci[1])}` : ""}
                {s.failed > 0 ? ` · 실패 ${s.failed}칸 제외` : ""}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
