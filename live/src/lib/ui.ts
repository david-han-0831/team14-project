// 화면 상태에서 파생되는 판단 (테스트하기 쉽게 순수 함수로 둔다)
import type { SetName } from "./api";

export type Phase = "loading" | "ready" | "running" | "finished" | "closed" | "error";

/** 실행 버튼을 누를 수 있는가. 고른 세트의 문항이 실제로 화면에 올라와 있을 때만. */
export function canRun(s: { phase: Phase; setName: SetName; loadedSet: SetName | null; questionCount: number }): boolean {
  return (s.phase === "ready" || s.phase === "finished") && s.loadedSet === s.setName && s.questionCount > 0;
}
