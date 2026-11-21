"""라이브 실험실 서버 로직.

evolve/ 연구 코드를 그대로 불러 쓴다(프롬프트·채점·자료 조건이 갈라지지 않게). evolve/ 는 수정하지 않는다.
세트·조건·모델은 여기서 고정한다. 클라이언트가 바꿀 수 없다.
"""
from __future__ import annotations

import json
import os
import sys
import time
import zlib
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
_EVOLVE = str(ROOT / "evolve")
if _EVOLVE not in sys.path:
    sys.path.insert(0, _EVOLVE)

import common as ev_common  # noqa: E402  (evolve/common.py)
import solve as ev_solve  # noqa: E402  (evolve/solve.py)

SETS: dict[str, list[str]] = {"week09": ["week09"], "seed": ["week02", "week04", "week08"]}
CONDITIONS = ("none", "brief", "page")
MODEL = "claude-haiku-5-5"
EFFORT = "low"
_PUBLIC_FIELDS = ("id", "week", "type", "q", "options", "concept")  # 정답·해설은 내려주지 않는다


class LiveError(Exception):
    """HTTP 상태로 바뀌는 오류. message 는 사용자에게 그대로 보이므로 내부 예외 원문을 넣지 않는다."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _load_questions() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for weeks in SETS.values():
        for q in ev_common.load_bank("public", weeks):
            out[q["id"]] = q
    return out


_QUESTIONS = _load_questions()


def is_live(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    if env.get("LIVE_DISABLED", "").strip().lower() in ("1", "true"):
        return False
    return env.get("LIVE_MOCK") == "1" or bool(env.get("ANTHROPIC_API_KEY"))


def _set_questions(set_name: str) -> list[dict]:
    weeks = SETS.get(set_name)
    if weeks is None:
        raise LiveError(400, "알 수 없는 문항 세트입니다")
    return [q for q in _QUESTIONS.values() if q["week"] in weeks]


def _material(week: str, condition: str) -> str:
    """조건에 맞는 참고 자료. 파일이 없거나 비어 있으면 빈 문자열."""
    try:
        return ev_common.context_for(week, condition) or ""
    except OSError:
        return ""


def health() -> dict:
    weeks = sorted({w for ws in SETS.values() for w in ws})
    return {
        "live": is_live(),
        "model": MODEL,
        "sets": [{"name": name, "weeks": ws, "n": len(_set_questions(name))} for name, ws in SETS.items()],
        # 배포 번들에 자료가 빠졌는지 드러낸다 (빠지면 자료 조건이 '자료 없음'과 같아진다)
        "materials": {w: {c: bool(_material(w, c)) for c in ("brief", "page")} for w in weeks},
    }


def bank(set_name: str) -> dict:
    qs = _set_questions(set_name)
    return {
        "set": set_name,
        "weeks": SETS[set_name],
        "questions": [{k: q.get(k) for k in _PUBLIC_FIELDS} for q in qs],
    }


def _map_llm_error(exc: Exception) -> LiveError:
    try:
        import anthropic
    except ImportError:  # SDK 없이 도는 가짜 풀이자 모드
        anthropic = None
    if anthropic is not None and isinstance(exc, anthropic.RateLimitError):
        return LiveError(429, "지금은 요청이 많습니다. 잠시 뒤 다시 시도해 주세요")
    if isinstance(exc, RuntimeError) and "재시도" in str(exc):
        return LiveError(429, "지금은 요청이 많습니다. 잠시 뒤 다시 시도해 주세요")
    return LiveError(502, "모델 호출에 실패했습니다")


API_TIMEOUT_S = 25.0  # 서버 함수 시간 제한(60초) 안에 끝나도록


def _anthropic_client():
    """SDK 내부 재시도 없이, 짧은 시간 제한으로. 재시도는 브라우저 쪽 실행기가 한다."""
    import anthropic

    return anthropic.Anthropic(max_retries=0, timeout=API_TIMEOUT_S)


class _FailFastMessages:
    """messages.create 의 API 오류를 곧바로 LiveError 로 바꾼다.

    evolve 의 LLM.ask 는 한도 초과 때 최대 60초씩 세 번 잠들고 5xx 도 기다렸다 재시도한다.
    연구 스크립트에는 맞지만 서버 함수에서는 시간 제한에 걸려 죽는다. 여기서 먼저 끊는다.
    """

    def __init__(self, inner):
        self._inner = inner

    def create(self, **kw):
        import anthropic

        try:
            return self._inner.create(**kw)
        except anthropic.APIError as exc:
            raise _map_llm_error(exc) from None


class _FailFastClient:
    def __init__(self, inner):
        self.messages = _FailFastMessages(inner.messages)


def _make_llm(qid: str, condition: str):
    if os.environ.get("LIVE_MOCK") == "1":
        # 가짜 풀이자는 칸마다 시드를 달리해 정답·오답이 섞이게 한다 (실제 호출에는 영향 없음)
        seed = zlib.crc32(f"{qid}/{condition}".encode())
        return ev_common.LLM(mock=True, usage=ev_common.Usage(), seed=seed)
    # 실제 호출은 항상 API 백엔드 (evolve 의 EVOLVE_BACKEND 환경 설정과 무관하게)
    llm = ev_common.LLM(mock=True, usage=ev_common.Usage())  # mock=True: 생성자에서 클라이언트를 만들지 않게
    llm.mock = False
    llm.backend = "api"
    llm._client = _FailFastClient(_anthropic_client())
    return llm


def solve(qid: str, condition: str, llm=None) -> dict:
    if condition not in CONDITIONS:
        raise LiveError(400, "알 수 없는 조건입니다")
    q = _QUESTIONS.get(qid) if isinstance(qid, str) else None
    if q is None:
        raise LiveError(400, "알 수 없는 문항입니다")
    if not is_live():
        raise LiveError(503, "라이브 실행이 꺼져 있습니다")
    if llm is None:
        llm = _make_llm(qid, condition)

    week = q["week"]
    ctx = _material(week, condition)
    if condition != "none" and not ctx:
        raise LiveError(502, "참고 자료를 불러오지 못했습니다")
    # evolve/solve.py 의 run() 과 같은 프롬프트 모양
    user = (f"[참고 자료: {week}]\n{ctx}\n\n" if ctx else "") + "[문제]\n" + ev_solve.fmt_question(q)
    t0 = time.time()
    try:
        text = llm.ask(MODEL, ev_solve.SYSTEM, user, effort=EFFORT,
                       mock_hint={"kind": "solve", "condition": condition, "q": q, "patched": False})
    except LiveError:
        raise
    except Exception as exc:  # noqa: BLE001  모델 호출 오류는 상태 코드로만 알린다
        raise _map_llm_error(exc) from None
    pred = ev_solve.parse_answer(text, q)
    return {
        "qid": qid,
        "condition": condition,
        "pred": pred,
        "correct": bool(ev_solve.is_correct(q, pred)),
        "input_tokens": int(llm.usage.input_tokens),
        "output_tokens": int(llm.usage.output_tokens),
        "ms": int((time.time() - t0) * 1000),
    }


def reports() -> list[dict]:
    out = []
    for p in sorted(ev_common.REPORT_DIR.glob("exp-e3-*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if r.get("mock"):
            continue
        out.append({
            "file": p.name,
            "weeks": r.get("weeks"),
            "date": r.get("date"),
            "model": r.get("model"),
            "runs": [{"condition": x.get("condition"), "acc": x.get("acc"), "acc_ci95": x.get("acc_ci95"), "n": x.get("n")}
                     for x in r.get("runs", [])],
        })
    return out
