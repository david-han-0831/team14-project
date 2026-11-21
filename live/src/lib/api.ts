// 서버 함수(/api/*) 호출과 응답 타입. 서버: livelab/http.py

export type Condition = "none" | "brief" | "page";
export const CONDITIONS: Condition[] = ["none", "brief", "page"];
export type SetName = "week09" | "seed";

export interface Question {
  id: string;
  week: string;
  type: "mc" | "num";
  q: string;
  options: string[] | null;
  concept: string;
}
export interface SolveResult {
  qid: string;
  condition: Condition;
  pred: number | null;
  correct: boolean;
  input_tokens: number;
  output_tokens: number;
  ms: number;
}
export interface Health {
  live: boolean;
  model: string;
  sets: { name: SetName; weeks: string[]; n: number }[];
}
export interface Bank {
  set: SetName;
  weeks: string[];
  questions: Question[];
}
export interface ReportRun {
  condition: Condition;
  acc: number;
  acc_ci95: [number, number];
  n: number;
}
export interface Report {
  file: string;
  weeks: string;
  date: string | null;
  model: string;
  runs: ReportRun[];
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    const msg = body && typeof body === "object" && "error" in body ? String((body as { error: unknown }).error) : "요청에 실패했습니다";
    throw new ApiError(res.status, msg);
  }
  if (body === null) throw new ApiError(res.status, "응답을 읽지 못했습니다");
  return body as T;
}

export const getHealth = () => request<Health>("/api/health");
export const getBank = (set: SetName) => request<Bank>(`/api/bank?set=${set}`);
export const getReports = () => request<{ reports: Report[] }>("/api/reports").then((r) => r.reports);
export const postSolve = (qid: string, condition: Condition, signal: AbortSignal) =>
  request<SolveResult>("/api/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ qid, condition }),
    signal,
  });
