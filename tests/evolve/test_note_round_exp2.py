"""Task 10: 실험 2 갈래 (seen, seen+ce, seen+rev). 1라운드 제안 공유, 고쳐 쓰기 예산 맞춤, H3 판정."""
from __future__ import annotations

import hashlib
import json

import pytest

import common
import counter
import note_propose
import note_round as nr
from fakes import PUB_MARK, SECRET, ScriptedLLM, fake_items

FREEZE = {"commit": "testcommit", "dirty": False}
BRIEF = "강의 브리프 본문이다. 브리프 문장 하나가 여기 있다."


@pytest.fixture(autouse=True)
def _brief(monkeypatch):
    monkeypatch.setattr(nr, "brief_bundle", lambda week: BRIEF)


def pub():
    return fake_items(4, "p", mark=PUB_MARK)


def lad():
    t2 = [{**q, "rung": "T2", "pair": f"p-{i}", "bank": "ladder"} for i, q in enumerate(fake_items(4, "t2", mark=SECRET), 1)]
    t3 = [{**q, "rung": "T3", "bank": "ladder"} for q in fake_items(3, "t3", mark=SECRET)]
    return t2 + t3


def make_llm():
    """풀이자: 노트가 있으면 기출을 맞힌다. '고친 규칙'이 노트에 있으면 3단 문항 하나(t3-1)도 맞힌다.
    반례: 풀이자는 '고친 규칙'이 없으면 함정을 고른다. 거르는 풀이자는 항상 맞힌다."""
    def fn(model, system, user, hint=None):
        if system == note_propose.SYSTEM:
            tag = hashlib.sha1(user.encode()).hexdigest()[:6]
            return json.dumps({"entries": [{"concept": "c", "rule": f"규칙 {tag} 이다.", "sources": ["s"]}]}, ensure_ascii=False)
        if system == counter.GEN_SYSTEM:
            eid = hint["entry_id"]
            return json.dumps({"q": f"{eid} 규칙을 그대로 따르면 틀리게 되는 상황을 묻는 반례 문항이다",
                               "options": [f"옳은 설명 {eid}", f"함정 {eid}", f"틀린 설명 가 {eid}", f"틀린 설명 나 {eid}"],
                               "answer_text": f"옳은 설명 {eid}", "trap_text": f"함정 {eid}", "quote": "브리프 문장 하나"}, ensure_ascii=False)
        if system == counter.REVISE_SYSTEM:
            return json.dumps({"action": "rewrite", "rule": f"고친 규칙 {hint['entry_id']} 이다."}, ensure_ascii=False)
        q = hint["q"]
        if "entry_id" in q:                                    # 반례 문항
            fooled = model == common.WEAK_MODEL and "고친 규칙" not in user
            return f"ANSWER: {(q['trap'] if fooled else q['answer']) + 1}"
        has_notes = "[학습 노트]" in user
        ok = (has_notes and q["id"].startswith("p-")) or (has_notes and q["id"] in ("t2-1", "t2-2")) or ("고친 규칙" in user and q["id"] == "t3-1")
        return "ANSWER: 1" if ok else "ANSWER: 2"
    return ScriptedLLM(fn)


def run(tmp_path, llm, **kw):
    args = dict(explore=False, mock=True, public_bank=pub(), ladder_bank=lad(), freeze=FREEZE, h1_exp1="확인")
    args.update(kw)
    return nr.run_experiment("exp2", "weekXX", llm, nr.Store(tmp_path), **args)


def by_system(llm, system):
    return [c for c in llm.calls if c["system"] == system]


def test_exp2_round1_entries_are_shared(tmp_path):
    llm = make_llm()
    run(tmp_path, llm)
    store = nr.Store(tmp_path)
    r1 = lambda arm: [e["rule"] for e in store.get(f"{arm}/r1/proposed")["added"]]
    assert r1("seen") == r1("seen+ce") == r1("seen+rev") and len(r1("seen")) == 1
    assert len(by_system(llm, note_propose.SYSTEM)) == 1          # 1라운드 제안은 한 번만 부른다


def test_ce_arm_revises_and_rev_arm_gets_the_same_budget(tmp_path):
    rep = run(tmp_path, make_llm())
    ce, rev = rep["arms"]["seen+ce"]["treat"], rep["arms"]["seen+rev"]["treat"]
    assert [x["revise_calls"] for x in ce] == [1, 0, 0] == [x["revise_calls"] for x in rev]
    assert ce[0]["revised"] == ["n01"] and rev[0]["revised"] == ["n01"]
    assert ce[0]["generated"] == 2 and ce[0]["passed"] == 2 and "ces" not in ce[0]
    assert "treat" not in rep["arms"]["seen"]
    assert rep["train"] == {"seen": {"propose_calls": 1, "ce_generated": 0, "revise_calls": 0},
                            "seen+ce": {"propose_calls": 0, "ce_generated": 2, "revise_calls": 1},
                            "seen+rev": {"propose_calls": 0, "ce_generated": 0, "revise_calls": 1}}


def test_rev_arm_never_sees_a_counterexample(tmp_path):
    llm = make_llm()
    run(tmp_path, llm)
    assert len(by_system(llm, counter.GEN_SYSTEM)) == 2           # 반례 출제는 seen+ce 에서만 (1회차 + 고친 항목 2회차)
    revs = by_system(llm, counter.REVISE_SYSTEM)
    assert len(revs) == 2 and sum("반례" in c["user"] for c in revs) == 1


def test_exp2_judges_only_h3(tmp_path):
    rep = run(tmp_path, make_llm())
    assert set(rep["judge"]) == {"H3", "H1_재현", "H1_실험1"} and rep["exp"] == "exp2"
    assert rep["arms"]["seen"]["final"] == {"T1": 1.0, "T2": 0.5, "T3": 0.0}
    assert rep["arms"]["seen+ce"]["final"]["T3"] == pytest.approx(1 / 3, abs=1e-4)


def test_exp2_evaluation_calls_equal_across_arms(tmp_path):
    run(tmp_path, make_llm())
    store = nr.Store(tmp_path)
    n = lambda arm: sum(len(store.get(f"{arm}/final/{r}")["results"]) * nr.K for r in ("T1", "T2", "T3"))
    assert n("seen") == n("seen+ce") == n("seen+rev") == 33      # 평가 때 문항당 호출 수가 갈래마다 같다 (T = 0 의 근거)


def test_ladder_never_reaches_big_models_and_overlap_is_checked(tmp_path):
    llm = make_llm()
    rep = run(tmp_path, llm)
    assert not any(SECRET in c["user"] for c in llm.calls if c["model"] != common.WEAK_MODEL)
    assert rep["arms"]["seen+ce"]["treat"][0]["overlap"]["checked"] is True


def test_explore_does_not_load_ladder_for_overlap_check(tmp_path):
    llm = make_llm()
    assert run(tmp_path, llm, explore=True) is None
    assert not any(SECRET in c["user"] for c in llm.calls)
    assert nr.Store(tmp_path).get("seen+ce/r1/treat")["out"]["overlap"]["checked"] is False


def test_running_rev_without_ce_checkpoint_stops(tmp_path):
    with pytest.raises(SystemExit, match="seen\\+ce"):
        run(tmp_path, make_llm(), explore=True, arms=["seen", "seen+rev"])


def test_running_ce_without_seen_checkpoint_stops(tmp_path):
    with pytest.raises(SystemExit, match="seen 갈래"):
        run(tmp_path, make_llm(), explore=True, arms=["seen+ce"])


def test_exp2_resume_makes_no_new_calls(tmp_path):
    llm = make_llm()
    rep1 = run(tmp_path, llm)
    n1 = len(llm.calls)
    rep2 = run(tmp_path, llm)
    assert len(llm.calls) == n1 and rep2["arms"] == rep1["arms"] and rep2["judge"] == rep1["judge"]


def test_treated_notes_survive_interrupt_before_notes_checkpoint(tmp_path):
    rep = run(tmp_path, make_llm())
    store = nr.Store(tmp_path)
    for key in ("seen+ce/r1/notes", "seen+ce/r2/solve", "seen+ce/r2/proposed", "seen+ce/r2/treat", "seen+ce/r2/notes",
                "seen+ce/r3/solve", "seen+ce/r3/proposed", "seen+ce/r3/treat", "seen+ce/r3/notes", "seen+ce/final/T1", "seen+ce/final/T2", "seen+ce/final/T3"):
        store.path(key).unlink(missing_ok=True)
    llm = make_llm()
    rep2 = run(tmp_path, llm)
    assert rep2["arms"]["seen+ce"] == rep["arms"]["seen+ce"]
    assert by_system(llm, counter.GEN_SYSTEM) == [] and by_system(llm, counter.REVISE_SYSTEM) == []      # 처치는 다시 하지 않는다
