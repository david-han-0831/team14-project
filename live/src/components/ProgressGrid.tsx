import { CONDITIONS, type Condition, type Question } from "../lib/api";
import { CONDITION_LABEL } from "../lib/labels";
import type { Cell, CellStatus } from "../lib/runner";

export type Cells = Record<string, Partial<Record<Condition, Cell>>>;

const SYMBOL: Record<CellStatus, string> = { idle: "·", running: "", ok: "✓", wrong: "✗", failed: "!" };
const STATUS_LABEL: Record<CellStatus, string> = { idle: "대기", running: "진행 중", ok: "정답", wrong: "오답", failed: "실패" };

export default function ProgressGrid({ questions, cells }: { questions: Question[]; cells: Cells }) {
  return (
    <div className="grid-wrap">
      <table className="grid">
        <thead>
          <tr>
            <th scope="col">문항</th>
            {CONDITIONS.map((c) => (
              <th key={c} scope="col">
                {CONDITION_LABEL[c]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {questions.map((q) => (
            <tr key={q.id}>
              <th scope="row" title={q.q}>
                {q.id}
              </th>
              {CONDITIONS.map((c) => {
                const status = cells[q.id]?.[c]?.status ?? "idle";
                return (
                  <td key={c} className={`cell cell-${status}`} aria-label={`${CONDITION_LABEL[c]}: ${STATUS_LABEL[status]}`}>
                    {status === "running" ? <span className="spinner" aria-hidden="true" /> : SYMBOL[status]}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
