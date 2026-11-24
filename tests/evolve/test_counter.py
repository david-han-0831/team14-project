"""Task 9: 반례 처치와 고쳐 쓰기 대조 (설계 3.5)."""
from __future__ import annotations

import json

import common
import counter
import notes
import solve
from fakes import PUB_MARK, SECRET, ScriptedLLM, fake_items

BRIEF = "강의 브리프 본문이다. **브리프 문장 하나**가 여기 있다. 다른 문장도 있다."


def two_entry_notes():
    n = notes.new_notes("weekXX", "seen+ce")
    notes.add_entry(n, "c1", "처음 규칙 하나다.", ["s"], "public-fail", 1)
    notes.add_entry(n, "c2", "처음 규칙 둘이다.", ["s"], "public-fail", 1)
    return n


def gen_json(entry_id, quote="브리프 문장 하나", q=None):
    return json.dumps({"q": q or f"{entry_id} 규칙을 그대로 따르면 틀리게 되는 상황을 묻는 반례 문항이다",
                       "options": [f"옳은 설명 {entry_id}", f"함정 {entry_id}", f"틀린 설명 가 {entry_id}", f"틀린 설명 나 {entry_id}"],
                       "answer_text": f"옳은 설명 {entry_id}", "trap_text": f"함정 {entry_id}", "quote": quote}, ensure_ascii=False)


def make_llm(weak_fails=("n01",), gen=gen_json, revise=None, strong_fails=()):
    """출제자: 항목마다 반례 1개. 거르는 풀이자(중간 모델): strong_fails 의 반례만 틀린다.
    풀이자: weak_fails 항목의 반례는 함정을 고르되, 노트에 '고친 규칙 <id>' 가 있으면 맞힌다."""
    def fn(model, system, user, hint=None):
        if system == counter.GEN_SYSTEM:
            return gen(hint["entry_id"])
        if system == counter.REVISE_SYSTEM:
            return (revise or (lambda eid: json.dumps({"action": "rewrite", "rule": f"고친 규칙 {eid} 이다."}, ensure_ascii=False)))(hint["entry_id"])
        q = hint["q"]
        eid = q["entry_id"]
        if model == common.MID_MODEL:
            return f"ANSWER: {(q['trap'] if eid in strong_fails else q['answer']) + 1}"
        fooled = eid in weak_fails and f"고친 규칙 {eid}" not in user
        return f"ANSWER: {(q['trap'] if fooled else q['answer']) + 1}"
    return ScriptedLLM(fn)


def calls(llm, system):
    return [c for c in llm.calls if c["system"] == system]


def treat(n, llm, **kw):
    args = dict(brief=BRIEF, llm=llm, public_bank=[], ladder_bank=[], week="weekXX", round_no=1)
    args.update(kw)
    return counter.treat_ce(n, ["n01", "n02"], **args)


# ---------------------------------------------------------------- 기계 검사
def test_mechanical_check_codes():
    ce = {"q": "가" * 30, "options": ["a", "b", "c", "d"], "answer": 1, "trap": 1, "evidence": {"quote": "브리프에 없는 말이 여기에 있다"}}
    assert set(counter.mechanical_check(ce, BRIEF, [])) == {"trap_is_answer", "quote_not_in_brief"}


def test_mechanical_check_format_and_duplicate():
    pub = fake_items(1, "p")
    ce = {"q": pub[0]["q"], "options": ["a", "b", "c"], "answer": 0, "trap": 1, "evidence": {"quote": "브리프 문장 하나"}}
    assert set(counter.mechanical_check(ce, BRIEF, pub)) == {"format", "dup_public"}


def test_quote_check_ignores_markdown_and_spacing():
    ce = {"q": "가" * 30, "options": ["a", "b", "c", "d"], "answer": 0, "trap": 1, "evidence": {"quote": "브리프  문장 하나가 여기 있다."}}
    assert counter.mechanical_check(ce, BRIEF, []) == []


def test_too_short_quote_is_rejected():
    ce = {"q": "가" * 30, "options": ["a", "b", "c", "d"], "answer": 0, "trap": 1, "evidence": {"quote": "브리프"}}
    assert counter.mechanical_check(ce, BRIEF, []) == ["quote_not_in_brief"]


# ---------------------------------------------------------------- 평가 문항과의 겹침
def test_overlap_drop_reports_numbers_only():
    text = SECRET + "와 같은 긴 문장 하나를 그대로 베낀 반례"
    kept, info = counter.overlap_drop([{"id": "ce-1", "q": text}, {"id": "ce-2", "q": "전혀 다른 내용의 반례 문항 문장이다"}], [{"id": "t3-1", "q": text, "options": []}])
    assert [c["id"] for c in kept] == ["ce-2"]
    assert info["dropped"] == 1 and info["checked"] is True and info["max"] == 1.0
    assert SECRET not in json.dumps(info, ensure_ascii=False)


def test_overlap_drop_without_ladder_is_marked_unchecked():
    kept, info = counter.overlap_drop([{"id": "ce-1", "q": "문장"}], [])
    assert len(kept) == 1 and info == {"dropped": 0, "max": None, "checked": False}


# ---------------------------------------------------------------- 출제
def test_generate_maps_texts_to_indices_and_shuffles():
    n = two_entry_notes()
    ce = counter.generate(n["entries"][0], BRIEF, make_llm(), week="weekXX", ce_id="ce-n01-1-1")
    assert ce["options"][ce["answer"]] == "옳은 설명 n01" and ce["options"][ce["trap"]] == "함정 n01"
    assert ce["type"] == "mc" and ce["id"] == "ce-n01-1-1" and ce["entry_id"] == "n01" and ce["week"] == "weekXX" and ce["concept"] == "c1"
    assert ce["evidence"]["quote"] == "브리프 문장 하나"
    again = counter.generate(n["entries"][0], BRIEF, make_llm(), week="weekXX", ce_id="ce-n01-1-1")
    assert again["options"] == ce["options"]                       # 같은 id 면 같은 순서 (재현 가능)


def test_generate_returns_none_on_garbage_or_unmatched_texts():         # Review Focus 1
    n = two_entry_notes()
    assert counter.generate(n["entries"][0], BRIEF, make_llm(gen=lambda eid: "죄송합니다"), week="weekXX", ce_id="x") is None
    bad = lambda eid: json.dumps({"q": "문항", "options": ["a", "b", "c", "d"], "answer_text": "없는 보기", "trap_text": "b", "quote": "브리프 문장 하나"})
    assert counter.generate(n["entries"][0], BRIEF, make_llm(gen=bad), week="weekXX", ce_id="x") is None


def test_generator_sees_entry_and_brief_only():
    n = two_entry_notes()
    llm = make_llm()
    counter.generate(n["entries"][0], BRIEF, llm, week="weekXX", ce_id="x")
    user = llm.calls[0]["user"]
    assert "처음 규칙 하나다." in user and "브리프 문장 하나" in user and "처음 규칙 둘이다." not in user
    assert llm.calls[0]["model"] == common.STRONG_MODEL


# ---------------------------------------------------------------- 거르기 · 풀기
def test_validate_keeps_only_ces_the_brief_reader_gets_right_twice():
    n = two_entry_notes()
    llm = make_llm(strong_fails=("n02",))
    ces = [counter.generate(e, BRIEF, llm, week="weekXX", ce_id=f"ce-{e['id']}") for e in n["entries"]]
    kept = counter.validate(ces, BRIEF, llm)
    assert [c["entry_id"] for c in kept] == ["n01"]
    mid = [c for c in llm.calls if c["model"] == common.MID_MODEL]
    assert len(mid) == 4 and all("브리프 문장 하나" in c["user"] for c in mid)


def test_probe_reports_accuracy_and_trap_rate():
    n = two_entry_notes()
    llm = make_llm()
    ces = [counter.generate(e, BRIEF, llm, week="weekXX", ce_id=f"ce-{e['id']}") for e in n["entries"]]
    rows = counter.probe(ces, notes.notes_text(n), llm)
    assert rows == [{"id": "ce-n01", "entry_id": "n01", "acc": 0.0, "trap_rate": 1.0}, {"id": "ce-n02", "entry_id": "n02", "acc": 1.0, "trap_rate": 0.0}]
    weak = [c for c in llm.calls if c["model"] == common.WEAK_MODEL]
    assert len(weak) == 6 and all("[학습 노트]" in c["user"] and "브리프 문장 하나" not in c["user"] for c in weak)


# ---------------------------------------------------------------- 반례 처치
def test_treat_ce_revises_only_entries_whose_ce_failed():
    n = two_entry_notes()
    out = treat(n, make_llm())
    assert out["revised"] == ["n01"] and out["deleted"] == []
    assert n["entries"][0]["rule"] == "고친 규칙 n01 이다." and n["entries"][0]["history"][0]["rule"] == "처음 규칙 하나다."
    assert n["entries"][1]["rule"] == "처음 규칙 둘이다." and n["entries"][1]["history"] == []
    assert out["generated"] == 3 and out["passed"] == 3 and out["revise_calls"] == 1
    assert out["trap_rate"] == [0.5, 0.0] and out["retest_acc"] == [1.0, None]


def test_treat_ce_second_pass_generates_fresh_ce_for_revised_only():
    llm = make_llm()
    treat(two_entry_notes(), llm)
    gens = calls(llm, counter.GEN_SYSTEM)
    assert [c["hint"]["entry_id"] for c in gens] == ["n01", "n02", "n01"]      # 1회차 항목 2개, 2회차는 고친 n01 만
    assert "고친 규칙 n01 이다." in gens[2]["user"]


def test_generator_and_validator_inputs_have_no_ladder_or_public_items():
    llm = make_llm()
    ladder = [{**q, "rung": "T3"} for q in fake_items(2, "t3", mark=SECRET)]
    treat(two_entry_notes(), llm, public_bank=fake_items(2, "p", mark=PUB_MARK), ladder_bank=ladder)
    big = [c for c in llm.calls if c["model"] != common.WEAK_MODEL]
    assert big and not any(SECRET in c["user"] or PUB_MARK in c["user"] for c in big)
    assert not any(SECRET in c["user"] for c in llm.calls)


def test_bad_rewrite_is_rejected_and_original_kept():                  # Review Focus 1
    n = two_entry_notes()
    out = treat(n, make_llm(revise=lambda eid: json.dumps({"action": "rewrite", "rule": "3번을 고른다."}, ensure_ascii=False)))
    assert n["entries"][0]["rule"] == "처음 규칙 하나다." and out["rejected_rewrites"] == 1 and out["revised"] == []


def test_unparseable_revision_keeps_entry():
    n = two_entry_notes()
    out = treat(n, make_llm(revise=lambda eid: "모르겠습니다"))
    assert n["entries"][0]["rule"] == "처음 규칙 하나다." and out["revised"] == [] and out["revise_calls"] == 1


def test_delete_action_removes_entry():
    n = two_entry_notes()
    out = treat(n, make_llm(revise=lambda eid: json.dumps({"action": "delete"})))
    assert out["deleted"] == ["n01"] and [e["id"] for e in n["entries"]] == ["n02"]
    assert len(calls(make_llm(), counter.GEN_SYSTEM)) == 0


def test_all_ces_filtered_means_no_revision():
    n = two_entry_notes()
    llm = make_llm(gen=lambda eid: gen_json(eid, quote="브리프에 없는 인용 문장이다"))
    out = treat(n, llm)
    assert out["generated"] == 2 and out["passed"] == 0 and out["revised"] == [] and out["trap_rate"] == [None]
    assert calls(llm, counter.REVISE_SYSTEM) == [] and [c for c in llm.calls if c["model"] != common.STRONG_MODEL] == []


def test_overlapping_ce_is_dropped_before_anyone_solves_it():
    n = two_entry_notes()
    leaked = SECRET + " 평가 문항과 글자까지 똑같은 반례 문항 문장이다"
    llm = make_llm(gen=lambda eid: gen_json(eid, q=leaked if eid == "n01" else None))
    out = treat(n, llm, ladder_bank=[{"id": "t3-1", "q": leaked, "options": [], "rung": "T3"}])
    assert out["overlap"]["dropped"] == 1 and out["passed"] == 1
    assert not any(SECRET in c["user"] for c in llm.calls if c["system"] == solve.SYSTEM)


def test_treat_ce_skips_ids_that_no_longer_exist():
    n = two_entry_notes()
    notes.delete_entry(n, "n02", 1)
    out = treat(n, make_llm())
    assert out["generated"] == 2          # n01 1회차 + 고친 n01 2회차


# ---------------------------------------------------------------- 고쳐 쓰기만 (대조)
def test_treat_rev_respects_budget_and_gets_no_counterexample():
    n = two_entry_notes()
    notes.add_entry(n, "c3", "처음 규칙 셋이다.", ["s"], "public-fail", 1)
    llm = make_llm()
    out = counter.treat_rev(n, ["n01", "n02", "n03"], budget=2, brief=BRIEF, llm=llm, round_no=1)
    assert out["revise_calls"] == 2 and out["revised"] == ["n01", "n02"] and n["entries"][2]["rule"] == "처음 규칙 셋이다."
    assert len(llm.calls) == 2 and not any("반례" in c["user"] for c in llm.calls)
    assert all(c["system"] == counter.REVISE_SYSTEM for c in llm.calls)


def test_treat_rev_cycles_when_budget_exceeds_entries():
    n = two_entry_notes()
    out = counter.treat_rev(n, ["n01", "n02"], budget=3, brief=BRIEF, llm=make_llm(), round_no=1)
    assert out["revise_calls"] == 3 and out["revised"] == ["n01", "n02"]
    assert len(n["entries"][0]["history"]) == 2


def test_treat_rev_with_zero_budget_makes_no_call():
    llm = make_llm()
    out = counter.treat_rev(two_entry_notes(), ["n01"], budget=0, brief=BRIEF, llm=llm, round_no=1)
    assert llm.calls == [] and out == {"revise_calls": 0, "revised": [], "deleted": [], "rejected_rewrites": 0}


def test_mock_llm_runs_the_whole_treatment():
    n = two_entry_notes()
    out = counter.treat_ce(n, ["n01", "n02"], brief=BRIEF, llm=common.LLM(mock=True), public_bank=[], ladder_bank=[], week="weekXX", round_no=1)
    assert out["generated"] >= 2 and set(out) >= {"passed", "revised", "deleted", "trap_rate", "retest_acc", "overlap", "revise_calls", "rejected_rewrites"}
