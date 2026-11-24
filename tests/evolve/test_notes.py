"""Task 2: 학습 노트 자료형과 항목 제약."""
from __future__ import annotations

import pytest

import notes


@pytest.mark.parametrize("rule,code", [
    ("", "empty"),
    ("   ", "empty"),
    ("하나다. 둘이다. 셋이다. 넷이다.", "too_long"),
    ("이 경우 3번을 고른다.", "option_ref"),
    ("정답은 ②이다.", "option_ref"),
    ("이런 질문에서는 첫 번째 보기가 옳다.", "option_ref"),
    ("보기 2 가 정답이다.", "option_ref"),
    ("w09a-c28 의 답은 MCTS 다.", "item_ref"),
    ("문항 7 은 AFlow 를 묻는다.", "item_ref"),
    ("3번 문제의 답은 MCTS 다.", "item_ref"),
])
def test_check_rule_flags(rule, code):
    assert code in notes.check_rule(rule)


def test_check_rule_accepts_three_sentences_with_numbers():
    assert notes.check_rule("pass@k 는 k 번 중 한 번이라도 맞히면 성공이다. p=0.2, k=10 이면 0.893 이다. 결함 문항은 k 를 늘려도 0 이다.") == []


def test_check_rule_does_not_mistake_trial_counts_for_option_numbers():
    assert notes.check_rule("같은 문제를 3번 풀어 3번 모두 맞히면 pass^3 이 1 이다.") == []


def test_add_then_text_and_ids():
    n = notes.new_notes("week09", "seen")
    notes.add_entry(n, "pass-at-k", "규칙 하나다.", ["week09 개념 9"], "public-fail", 1)
    notes.add_entry(n, "aflow", "규칙 둘이다.", ["week08 개념 6"], "public-fail", 1)
    assert [e["id"] for e in n["entries"]] == ["n01", "n02"]
    assert n["entries"][0]["origin"] == {"round": 1, "from": "public-fail"} and n["entries"][0]["history"] == []
    assert notes.notes_text(n) == "[학습 노트]\n- (pass-at-k) 규칙 하나다.\n- (aflow) 규칙 둘이다."


def test_empty_notes_text_is_empty_string():
    assert notes.notes_text(notes.new_notes("week09", "seen")) == ""


def test_add_entry_rejects_violation():
    n = notes.new_notes("week09", "seen")
    with pytest.raises(ValueError):
        notes.add_entry(n, "c", "3번을 고른다.", [], "public-fail", 1)
    assert n["entries"] == []


def test_revise_keeps_history_and_delete_moves_entry():
    n = notes.new_notes("week09", "seen+ce")
    notes.add_entry(n, "c", "처음 규칙이다.", [], "public-fail", 1)
    notes.revise_entry(n, "n01", "고친 규칙이다.", "counterexample", 1)
    assert n["entries"][0]["rule"] == "고친 규칙이다."
    assert n["entries"][0]["history"][0]["rule"] == "처음 규칙이다."
    notes.delete_entry(n, "n01", 1)
    assert n["entries"] == [] and n["deleted"][0]["id"] == "n01"
    notes.add_entry(n, "c", "새 규칙이다.", [], "public-fail", 2)
    assert n["entries"][0]["id"] == "n02"      # 지운 id 를 다시 쓰지 않는다


def test_revise_rejects_violation_and_keeps_original():
    n = notes.new_notes("week09", "seen+ce")
    notes.add_entry(n, "c", "처음 규칙이다.", [], "public-fail", 1)
    with pytest.raises(ValueError):
        notes.revise_entry(n, "n01", "정답은 ③이다.", "counterexample", 1)
    assert n["entries"][0]["rule"] == "처음 규칙이다." and n["entries"][0]["history"] == []


def test_save_and_load_roundtrip(tmp_path):
    n = notes.new_notes("week09", "seen")
    notes.add_entry(n, "c", "규칙이다.", ["s"], "public-fail", 1)
    p = tmp_path / "a" / "week09.json"
    notes.save_notes(n, p)
    assert notes.load_notes(p) == n
