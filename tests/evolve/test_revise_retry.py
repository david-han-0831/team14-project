"""실험 2 탐색 실행에서 드러난 문제: 고쳐 쓴 규칙이 제약(3문장 이하 등)을 어겨 전부 버려져 처치가 아무 일도 하지 않았다.
제약을 어기면 사유를 알려 주고 한 번 더 쓰게 한다(두 갈래 공통). 그래도 어기면 버리고 사유를 남긴다."""
from __future__ import annotations

import json

import common
import counter
import notes
from fakes import ScriptedLLM

BRIEF = "강의 브리프 본문이다. 브리프 문장 하나가 여기 있다."
LONG = "하나다. 둘이다. 셋이다. 넷이다."        # 4문장 → too_long


def one_entry():
    n = notes.new_notes("weekXX", "seen+ce")
    notes.add_entry(n, "c1", "처음 규칙이다.", ["s"], "public-fail", 1)
    return n


def make_llm(rewrites):
    """고쳐 쓰기 호출마다 rewrites 에서 차례로 꺼내 준다. 반례는 풀이자가 항상 함정을 고른다(고친 뒤 재시험만 맞힌다)."""
    left = list(rewrites)

    def fn(model, system, user, hint=None):
        if system == counter.GEN_SYSTEM:
            eid = hint["entry_id"]
            return json.dumps({"q": f"{eid} 규칙을 그대로 따르면 틀리게 되는 상황을 묻는 반례 문항이다",
                               "options": [f"옳은 {eid}", f"함정 {eid}", f"다 {eid}", f"라 {eid}"],
                               "answer_text": f"옳은 {eid}", "trap_text": f"함정 {eid}", "quote": "브리프 문장 하나"}, ensure_ascii=False)
        if system == counter.REVISE_SYSTEM:
            return json.dumps({"action": "rewrite", "rule": left.pop(0)}, ensure_ascii=False)
        q = hint["q"]
        fooled = model == common.WEAK_MODEL and "고친 규칙" not in user
        return f"ANSWER: {(q['trap'] if fooled else q['answer']) + 1}"
    return ScriptedLLM(fn)


def revise_calls(llm):
    return [c for c in llm.calls if c["system"] == counter.REVISE_SYSTEM]


def treat(n, llm):
    return counter.treat_ce(n, ["n01"], brief=BRIEF, llm=llm, public_bank=[], ladder_bank=[], week="weekXX", round_no=1, passes=1)


def test_violating_rewrite_gets_one_retry_with_the_reason():
    n = one_entry()
    llm = make_llm([LONG, "고친 규칙이다. 예외가 하나 있다."])
    out = treat(n, llm)
    assert n["entries"][0]["rule"] == "고친 규칙이다. 예외가 하나 있다." and out["revised"] == ["n01"]
    assert out["revise_calls"] == 1 and out["retries"] == 1 and out["rejected_rewrites"] == 0 and out["rejected_reasons"] == []
    second = revise_calls(llm)[1]["user"]
    assert "3문장" in second and LONG in second          # 무엇이 왜 버려졌는지 알려 준다


def test_rewrite_that_still_violates_is_dropped_with_reason():
    n = one_entry()
    llm = make_llm([LONG, "정답은 ②이다."])
    out = treat(n, llm)
    assert n["entries"][0]["rule"] == "처음 규칙이다." and out["revised"] == []
    assert out["rejected_rewrites"] == 1 and out["retries"] == 1
    assert out["rejected_reasons"] == [{"entry_id": "n01", "why": ["option_ref"]}]
    assert len(revise_calls(llm)) == 2                    # 다시 쓰기는 한 번만


def test_valid_rewrite_is_not_retried():
    n = one_entry()
    llm = make_llm(["고친 규칙이다."])
    out = treat(n, llm)
    assert out["retries"] == 0 and len(revise_calls(llm)) == 1


def test_control_arm_gets_the_same_retry():
    n = one_entry()
    llm = make_llm([LONG, "고친 규칙이다."])
    out = counter.treat_rev(n, ["n01"], budget=1, brief=BRIEF, llm=llm, round_no=1)
    assert out["revised"] == ["n01"] and out["revise_calls"] == 1 and out["retries"] == 1 and out["unspent"] == 0
    assert not any("반례" in c["user"] for c in llm.calls)       # 다시 쓰라는 안내에도 반례라는 말이 들어가지 않는다


def test_budget_counts_entries_tried_not_retries():
    n = notes.new_notes("weekXX", "seen+rev")
    notes.add_entry(n, "c1", "규칙 하나다.", ["s"], "public-fail", 1)
    notes.add_entry(n, "c2", "규칙 둘이다.", ["s"], "public-fail", 1)
    llm = make_llm([LONG, "고친 규칙 하나다.", "고친 규칙 둘이다."])
    out = counter.treat_rev(n, ["n01", "n02"], budget=2, brief=BRIEF, llm=llm, round_no=1)
    assert out["revised"] == ["n01", "n02"] and out["revise_calls"] == 2 and out["retries"] == 1 and len(llm.calls) == 3
