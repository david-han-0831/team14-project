"""evolve 노트 루프 테스트 공용 도우미. 가짜 문항과 가짜 LLM 만 쓴다(비공개 세트를 읽지 않는다)."""
from __future__ import annotations

from types import SimpleNamespace

import common  # evolve/common.py (conftest 가 path 에 넣는다)

SECRET = "사다리전용표식XYZ"      # 사다리(평가 전용) 가짜 문항에 넣는 표식. 제안자 입력에 나타나면 유출이다
PUB_MARK = "기출전용표식QRS"      # 기출 가짜 문항에 넣는 표식


def fake_items(n: int, prefix: str, concepts: list[str] | None = None, mark: str = "", week: str = "weekXX") -> list[dict]:
    """객관식 4지, 정답은 0번. 문제 문장은 유출 검사(25자 이상 겹침)에 걸릴 만큼 길다."""
    out = []
    for i in range(1, n + 1):
        out.append({
            "id": f"{prefix}-{i}", "type": "mc", "week": week, "bank": "public",
            "q": f"{mark}가짜 질문 {prefix}{i}: 다음 중 이 개념을 가장 정확하게 설명한 것은 무엇인가",
            "options": [f"{prefix}{i} 의 옳은 설명", f"{prefix}{i} 의 틀린 설명 가", f"{prefix}{i} 의 틀린 설명 나", f"{prefix}{i} 의 틀린 설명 다"],
            "answer": 0, "concept": (concepts[i - 1] if concepts else f"concept-{prefix}{i}"),
        })
    return out


class _Usage:
    def __init__(self):
        self.calls, self.usd = 0, 0.0

    def to_dict(self):
        return {"calls": self.calls, "input_tokens": 0, "output_tokens": 0, "usd": 0.0, "by_model": {}}


class ScriptedLLM:
    """evolve.common.LLM 과 같은 ask() 모양. 호출을 fn 에 넘기고 받은 인자를 calls 에 기록한다."""

    def __init__(self, fn):
        self.fn = fn
        self.calls: list[dict] = []
        self.usage = _Usage()
        self.mock = True

    def ask(self, model, system, user, effort="low", max_tokens=4000, mock_hint=None):
        self.calls.append({"model": model, "system": system, "user": user, "hint": mock_hint})
        self.usage.calls += 1
        return self.fn(model, system, user, hint=mock_hint)


def ns(bank="public", weeks="weekXX", condition="notes", k=1):
    return SimpleNamespace(bank=bank, weeks=weeks, condition=condition, k=k, model=common.WEAK_MODEL, effort="low", limit=0, out="", mock=True)
