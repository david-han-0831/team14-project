import type { Round } from "../lib/api";
import { formatPct } from "../lib/stats";

const weekLabel = (w: string) => `${Number(w.replace("week", ""))}주차`;

export default function EvolveLog({ rounds }: { rounds: Round[] }) {
  if (rounds.length === 0) return <p className="muted">아직 기록된 진화 라운드가 없습니다.</p>;
  return (
    <>
      <p className="muted small">
        자가 진화 루프(<code>evolve/round.py</code>)가 한 번 돌 때마다 남긴 리포트를 그대로 읽어 보여 줍니다. 최신 순입니다.
      </p>
      <ol className="evolve-log">
        {rounds.map((r) => (
          <li key={r.round} className="evolve-round">
            <div className="evolve-head">
              <span className="evolve-date">{r.date ?? "날짜 미기록"}</span>
              <strong>
                라운드 {r.round} · {r.weeks.map(weekLabel).join(", ")}
              </strong>
              <span className={r.accepted ? "tag ok" : "tag"}>{r.accepted ? "채택" : "기각"}</span>
            </div>

            {r.acc_before !== null && r.acc_after !== null && (
              <p className="evolve-score">
                사이트 페이지 조건 정답률 {formatPct(r.acc_before)} → {formatPct(r.acc_after)}
                {r.n_public !== null && ` (${r.n_public}문항)`}
                {r.ci_overlap && <span className="muted"> · 전후 신뢰구간이 겹쳐 개선이라고 단정할 수 없습니다</span>}
              </p>
            )}

            {r.weak_concepts.length > 0 && (
              <p className="small">
                틀린 개념:{" "}
                {r.weak_concepts.map((w) => (
                  <span key={w.week + w.concept}>
                    <code>{w.concept}</code> <span className="muted">({w.ids.join(", ")})</span>{" "}
                  </span>
                ))}
              </p>
            )}

            {r.patches.length === 0 ? (
              <p className="muted small">고친 카드가 없습니다.</p>
            ) : (
              <ul className="evolve-patches">
                {r.patches.map((p) => (
                  <li key={p.week + p.card_id}>
                    <div>
                      <span className="tag">
                        {weekLabel(p.week)} 카드 {p.card_id}
                      </span>{" "}
                      <strong>{p.title}</strong>
                    </div>
                    {p.reason && <p className="small">고친 이유: {p.reason}</p>}
                    {p.easy && (
                      <details>
                        <summary>추가된 설명 보기</summary>
                        <p className="small">{p.easy}</p>
                      </details>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}
