"""Task 3: 갈래별 제안자. 누가 무엇을 보는가(설계 3.4)를 테스트로 고정한다."""
from __future__ import annotations

import json
from pathlib import Path

import note_propose as np_
import notes
from fakes import fake_items


def _payload(entries):
    return json.dumps({"entries": entries}, ensure_ascii=False)


def test_concept_arm_never_sees_item_text():
    failed = fake_items(2, "p", concepts=["aflow", "aflow"])
    user = np_.build_user("concept", "week09", failed, notes.new_notes("week09", "concept"), "브리프 본문")
    assert "aflow" in user and user.count("aflow") == 1
    assert failed[0]["q"] not in user and failed[0]["options"][0] not in user
    assert "브리프 본문" in user


def test_seen_arm_sees_question_and_answer_text_but_no_position():
    failed = fake_items(1, "p")
    user = np_.build_user("seen", "week09", failed, notes.new_notes("week09", "seen"), "브리프 본문")
    assert failed[0]["q"] in user and failed[0]["options"][failed[0]["answer"]] in user
    assert all(o in user for o in failed[0]["options"])
    assert "정답: 1" not in user and "1번" not in user and failed[0]["id"] not in user


def test_all_seen_arms_get_the_same_input():
    failed = fake_items(2, "p")
    n = notes.new_notes("week09", "seen")
    assert np_.build_user("seen", "week09", failed, n, "b") == np_.build_user("seen+ce", "week09", failed, n, "b") == np_.build_user("seen+rev", "week09", failed, n, "b")


def test_existing_notes_are_shown_to_proposer():
    n = notes.new_notes("week09", "seen")
    notes.add_entry(n, "c", "이미 있는 규칙이다.", ["s"], "public-fail", 1)
    assert "이미 있는 규칙이다." in np_.build_user("seen", "week09", fake_items(1, "p"), n, "b")


def test_proposer_input_is_built_only_from_its_arguments():
    # 평가 전용 문항은 build_user 의 인자가 아니다. 모듈이 은행을 직접 읽지 않는지 확인한다.
    src = Path(np_.__file__).read_text(encoding="utf-8")
    assert "load_bank" not in src and "ladder" not in src and "heldout" not in src


def test_propose_filters_and_caps(scripted_llm):
    entries = [{"concept": "c", "rule": f"규칙 {i} 이다.", "sources": ["s"]} for i in range(7)]
    entries += [{"concept": "c", "rule": "3번을 고른다.", "sources": ["s"]}, {"concept": "c", "rule": "출처 없다.", "sources": []}, {"rule": "개념 없다.", "sources": ["s"]}]
    llm = scripted_llm(lambda *a, **kw: _payload(entries))
    n = notes.new_notes("week09", "seen")
    out = np_.propose_entries("seen", "week09", fake_items(1, "p"), n, llm, public_bank=[], max_new=5)
    assert len(out["added"]) == 5 and len(n["entries"]) == 5 and out["raw_n"] == 10
    assert [e["rule"] for e in n["entries"]] == [f"규칙 {i} 이다." for i in range(5)]
    whys = {tuple(r["why"]) for r in out["rejected"]}
    assert {("option_ref",), ("no_sources",), ("format",), ("over_cap",)} <= whys
    assert n["entries"][0]["origin"] == {"round": 0, "from": "public-fail"}


def test_propose_records_round_number(scripted_llm):
    n = notes.new_notes("week09", "seen")
    np_.propose_entries("seen", "week09", fake_items(1, "p"), n, scripted_llm(lambda *a, **kw: _payload([{"concept": "c", "rule": "규칙이다.", "sources": ["s"]}])), public_bank=[], round_no=2)
    assert n["entries"][0]["origin"]["round"] == 2


def test_propose_with_garbage_output_adds_nothing(scripted_llm):       # Review Focus 1
    n = notes.new_notes("week09", "seen")
    out = np_.propose_entries("seen", "week09", fake_items(1, "p"), n, scripted_llm(lambda *a, **kw: "죄송합니다"), public_bank=[])
    assert out["added"] == [] and out["raw_n"] == 0 and n["entries"] == []


def test_propose_with_broken_json_adds_nothing(scripted_llm):
    n = notes.new_notes("week09", "seen")
    out = np_.propose_entries("seen", "week09", fake_items(1, "p"), n, scripted_llm(lambda *a, **kw: '{"entries": [{"concept": '), public_bank=[])
    assert out["added"] == [] and n["entries"] == []


def test_propose_without_failures_makes_no_call(scripted_llm):
    llm = scripted_llm(lambda *a, **kw: "{}")
    out = np_.propose_entries("seen", "week09", [], notes.new_notes("week09", "seen"), llm, public_bank=[])
    assert llm.calls == [] and out == {"added": [], "rejected": [], "raw_n": 0}


def test_concept_arm_applies_leak_check(scripted_llm):
    item = {**fake_items(1, "p")[0], "week": "week09"}
    llm = scripted_llm(lambda *a, **kw: _payload([{"concept": "c", "rule": item["q"], "sources": ["s"]}]))     # 기출 문장을 그대로 베낀 규칙
    out = np_.propose_entries("concept", "week09", [item], notes.new_notes("week09", "concept"), llm, public_bank=[item])
    assert out["added"] == [] and out["rejected"][0]["why"] == ["leak"]


def test_seen_arm_skips_leak_check(scripted_llm):
    item = {**fake_items(1, "p")[0], "week": "week09"}
    llm = scripted_llm(lambda *a, **kw: _payload([{"concept": "c", "rule": item["q"], "sources": ["s"]}]))
    out = np_.propose_entries("seen", "week09", [item], notes.new_notes("week09", "seen"), llm, public_bank=[item])
    assert len(out["added"]) == 1


def test_mock_llm_produces_a_valid_entry():
    import common
    n = notes.new_notes("week09", "seen")
    out = np_.propose_entries("seen", "week09", fake_items(1, "p"), n, common.LLM(mock=True), public_bank=[])
    assert len(out["added"]) == 1


def test_duplicate_of_existing_rule_is_rejected(scripted_llm):
    n = notes.new_notes("week09", "seen")
    notes.add_entry(n, "c", "이미 있는 규칙이다.", ["s"], "public-fail", 1)
    llm = scripted_llm(lambda *a, **kw: _payload([{"concept": "c", "rule": "이미 있는  규칙이다.", "sources": ["s"]}, {"concept": "c", "rule": "새 규칙이다.", "sources": ["s"]},
                                                  {"concept": "c", "rule": "새 규칙이다.", "sources": ["s"]}]))
    out = np_.propose_entries("seen", "week09", fake_items(1, "p"), n, llm, public_bank=[], round_no=2)
    assert [e["rule"] for e in out["added"]] == ["새 규칙이다."]
    assert [r["why"] for r in out["rejected"]] == [["duplicate"], ["duplicate"]]
