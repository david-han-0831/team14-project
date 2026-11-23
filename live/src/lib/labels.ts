import type { Condition, SetName } from "./api";

export const CONDITION_LABEL: Record<Condition, string> = { none: "자료 없음", brief: "브리프", page: "사이트 페이지" };
export const CONDITION_DESC: Record<Condition, string> = {
  none: "문제만 보고 풉니다. 모델이 원래 아는 것만으로 답합니다.",
  brief: "강의 원본과 대조해 쓴 주차 브리프를 함께 줍니다.",
  page: "공개 사이트의 주차 페이지 본문을 함께 줍니다. 예상 문제는 뺍니다.",
};
export const SET_LABEL: Record<SetName, string> = { week09: "9주차 검증 문항", seed: "2·4·8주차 시드 문항" };
export const SITE_URL = "https://wukong-daima.github.io/team14-project/";
export const REPO_URL = "https://github.com/wukong-daima/team14-project";
// evolve/common.py 의 PRICE 표와 같은 값 (claude-haiku-5-5, 100만 토큰당 달러)
export const PRICE_IN = 0.1;
export const PRICE_OUT = 0.5;
