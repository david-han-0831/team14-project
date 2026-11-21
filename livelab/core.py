"""라이브 실험실 서버 로직.

evolve/ 연구 코드를 그대로 불러 쓴다(프롬프트·채점·자료 조건이 갈라지지 않게). evolve/ 는 수정하지 않는다.
세트·조건·모델은 여기서 고정한다. 클라이언트가 바꿀 수 없다.
"""
from __future__ import annotations

import json
import os
import sys
import time
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


def health() -> dict:
    return {
        "live": is_live(),
        "model": MODEL,
        "sets": [{"name": name, "weeks": weeks, "n": len(_set_questions(name))} for name, weeks in SETS.items()],
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


def solve(qid: str, condition: str, llm=None) -> dict:
    if condition not in CONDITIONS:
        raise LiveError(400, "알 수 없는 조건입니다")
    q = _QUESTIONS.get(qid) if isinstance(qid, str) else None
    if q is None:
        raise LiveError(400, "알 수 없는 문항입니다")
    if not is_live():
        raise LiveError(503, "라이브 실행이 꺼져 있습니다")
    if llm is None:
        llm = ev_common.LLM(mock=os.environ.get("LIVE_MOCK") == "1", usage=ev_common.Usage())

    week = q["week"]
    ctx = ev_common.context_for(week, condition)
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
