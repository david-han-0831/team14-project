import type { Health, SetName } from "../lib/api";
import { SET_LABEL } from "../lib/labels";

interface Props {
  health: Health;
  setName: SetName;
  running: boolean;
  done: number;
  total: number;
  runnable: boolean;
  onSet: (s: SetName) => void;
  onRun: () => void;
  onStop: () => void;
}

export default function RunControls({ health, setName, running, done, total, runnable, onSet, onRun, onStop }: Props) {
  return (
    <div className="controls">
      <div className="segmented" role="group" aria-label="문항 세트">
        {health.sets.map((s) => (
          <button key={s.name} type="button" aria-pressed={s.name === setName} disabled={running} onClick={() => onSet(s.name)}>
            {SET_LABEL[s.name]} <span className="count">{s.n}</span>
          </button>
        ))}
      </div>
      <div className="actions">
        {running ? (
          <button type="button" className="btn" onClick={onStop}>
            멈춤
          </button>
        ) : (
          <button type="button" className="btn primary" onClick={onRun} disabled={!runnable}>
            실험 실행
          </button>
        )}
        <span className="progress-text" aria-live="polite">
          {total === 0 ? "문항을 불러오는 중" : running || done > 0 ? `${done} / ${total}칸` : `${total}칸 · 모델 ${health.model}`}
        </span>
      </div>
    </div>
  );
}
