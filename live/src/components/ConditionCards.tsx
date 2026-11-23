import { CONDITIONS } from "../lib/api";
import { CONDITION_DESC, CONDITION_LABEL } from "../lib/labels";

export default function ConditionCards() {
  return (
    <ul className="conditions">
      {CONDITIONS.map((c) => (
        <li key={c} className={`condition condition-${c}`}>
          <span className="swatch" aria-hidden="true" />
          <div>
            <strong>{CONDITION_LABEL[c]}</strong>
            <p>{CONDITION_DESC[c]}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
