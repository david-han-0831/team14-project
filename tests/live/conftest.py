"""라이브 실험실 테스트 공용 도우미."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _live_env(monkeypatch):
    """기본은 가짜 풀이자 모드. 실제 키·끄기 설정이 테스트에 새지 않게 한다."""
    monkeypatch.setenv("LIVE_MOCK", "1")
    monkeypatch.delenv("LIVE_DISABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


class FakeLLM:
    """evolve.common.LLM 과 같은 ask() 모양. 정해진 글을 돌려주고 받은 인자를 기록한다."""

    def __init__(self, text: str | None = None, exc: Exception | None = None):
        self.text, self.exc = text, exc
        self.last_model = self.last_user = self.last_system = self.last_effort = None
        self.usage = type("U", (), {"input_tokens": 0, "output_tokens": 0})()

    def ask(self, model, system, user, effort="low", **kw):
        self.last_model, self.last_system, self.last_user, self.last_effort = model, system, user, effort
        if self.exc is not None:
            raise self.exc
        self.usage.input_tokens += 120
        self.usage.output_tokens += 30
        return self.text


@pytest.fixture
def fake_llm_factory():
    return lambda text: FakeLLM(text=text)


@pytest.fixture
def raising_llm_factory():
    return lambda exc: FakeLLM(exc=exc)


def raw_question(qid: str) -> dict:
    """정답이 들어 있는 원본 문항 (은행 파일에서 직접 읽는다)."""
    base = ROOT / "assets" / "data" / "quiz"
    for name in json.loads((base / "index.json").read_text(encoding="utf-8"))["banks"]:
        for q in json.loads((base / name).read_text(encoding="utf-8"))["questions"]:
            if q.get("id") == qid:
                return q
    raise KeyError(qid)
