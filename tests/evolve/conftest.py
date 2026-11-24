"""evolve 노트 루프 테스트 설정. 도우미는 fakes.py (tests/live 의 conftest 와 이름이 겹치지 않게)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT / "evolve"), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fakes import ScriptedLLM  # noqa: E402


@pytest.fixture
def scripted_llm():
    return ScriptedLLM


@pytest.fixture(autouse=True)
def _no_private_sets(monkeypatch, tmp_path):
    """테스트가 실제 비공개 세트·사다리를 읽지 않게 빈 폴더로 돌린다."""
    monkeypatch.setenv("HELDOUT_DIR", str(tmp_path / "_no_heldout"))
    monkeypatch.setenv("LADDER_DIR", str(tmp_path / "_no_ladder"))
