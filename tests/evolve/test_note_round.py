"""Task 5: 실험 1 실행기. 저장 지점, 탐색/확정, 유출 경로를 가짜 문항으로 확인한다."""
from __future__ import annotations

import hashlib
import json

import pytest

import common
import note_round as nr
from fakes import PUB_MARK, SECRET, ScriptedLLM, fake_items

FREEZE = {"commit": "testcommit", "dirty": False}


def pub():
    return fake_items(4, "p", mark=PUB_MARK)


def lad():
    t2 = [{**q, "rung": "T2", "pair": f"p-{i}", "bank": "ladder"} for i, q in enumerate(fake_items(4, "t2", mark=SECRET), 1)]
    t3 = [{**q, "rung": "T3", "bank": "ladder"} for q in fake_items(3, "t3", mark=SECRET)]
    return t2 + t3


def make_llm(with_notes=("p-1", "p-2", "p-3", "p-4", "t2-1", "t2-2"), always=(), fail_at: int | None = None):
    """풀이자: 노트가 있으면 with_notes 문항을, 노트와 무관하게 always 문항을 맞힌다. 제안자: 입력에서 정해지는 규칙 1개."""
    def fn(model, system, user, hint=None):
        if fail_at is not None and len(llm.calls) == fail_at:
            raise RuntimeError("끊김")
        if model == common.WEAK_MODEL:
            qid = hint["q"]["id"]
            ok = qid in always or ("[학습 노트]" in user and qid in with_notes)
            return "ANSWER: 1" if ok else "ANSWER: 2"
        tag = hashlib.sha1(user.encode()).hexdigest()[:6]
        return json.dumps({"entries": [{"concept": "c", "rule": f"규칙 {tag} 이다.", "sources": ["s"]}]}, ensure_ascii=False)
    llm = ScriptedLLM(fn)
    return llm


def solver_calls(llm):
    return [c for c in llm.calls if c["model"] == common.WEAK_MODEL]


def run(tmp_path, llm, **kw):
    args = dict(explore=False, mock=True, public_bank=pub(), ladder_bank=lad(), freeze=FREEZE)
    args.update(kw)
    return nr.run_experiment("exp1", "weekXX", llm, nr.Store(tmp_path), **args)


def test_exp1_end_to_end_report_shape(tmp_path):
    rep = run(tmp_path, make_llm())
    assert set(rep["arms"]) == {"seen", "concept"} and rep["n"] == {"T1": 4, "T2": 4, "T3": 3}
    assert rep["exp"] == "exp1" and rep["week"] == "weekXX" and rep["mock"] is True and rep["k"] == 3 and rep["rounds"] == 3
    assert rep["baseline"] == {"T1": 0.0, "T2": 0.0, "T3": 0.0}
    seen = rep["arms"]["seen"]
    assert seen["t1_by_round"] == [0.0, 1.0, 1.0, 1.0] and seen["final"] == {"T1": 1.0, "T2": 0.5, "T3": 0.0}
    d = seen["decomp"]
    assert (d["d1"], d["O_mem"], d["O_facet"], d["G"]) == (1.0, 0.5, 0.5, 0.0)
    assert d["d1"] == pytest.approx(d["O_mem"] + d["O_facet"] + d["G"])
    assert rep["judge"]["H1"] == "확인" and rep["judge"]["H2"] in ("확인", "구분 못 함")
    assert rep["freeze"]["commit"] == "testcommit" and len(rep["freeze"]["ladder_sha256"]) == 64
    assert rep["freeze"]["params"]["n_boot"] == 10000 and rep["freeze"]["params"]["seed"] == 14


def test_baseline_is_shared_and_round1_reuses_it(tmp_path):
    llm = make_llm()
    run(tmp_path, llm)
    # 풀이 호출 수 = 기준선 (4+4+3)*3 + 갈래마다 [r2, r3 풀이 4*3*2 + 최종 평가 (4+4+3)*3]
    assert len(solver_calls(llm)) == 33 + 2 * (24 + 33)


def test_explore_never_touches_ladder(tmp_path):
    llm = make_llm()
    out = run(tmp_path, llm, explore=True)
    assert out is None
    assert not any(SECRET in c["user"] for c in llm.calls)        # 사다리 문항의 표식이 어떤 호출에도 없다
    assert len(solver_calls(llm)) == 12 + 2 * (24 + 12)            # 기출만: 기준선 + 갈래마다 r2, r3, 마지막 기출 풀이


def test_ladder_items_never_reach_proposer(tmp_path):
    llm = make_llm()
    run(tmp_path, llm)
    big = [c for c in llm.calls if c["model"] != common.WEAK_MODEL]
    assert big and not any(SECRET in c["user"] for c in big)


def test_concept_arm_proposer_sees_no_item_text(tmp_path):
    llm = make_llm()
    nr.run_experiment("exp1", "weekXX", llm, nr.Store(tmp_path), explore=True, mock=True, arms=["concept"], public_bank=pub(), freeze=FREEZE)
    big = [c for c in llm.calls if c["model"] != common.WEAK_MODEL]
    assert big and not any(PUB_MARK in c["user"] for c in big)


def test_resume_makes_no_new_calls_and_no_duplicate_entries(tmp_path):     # Review Focus 3
    llm = make_llm()
    rep1 = run(tmp_path, llm)
    n1 = len(llm.calls)
    rep2 = run(tmp_path, llm)
    assert len(llm.calls) == n1
    assert rep2["arms"] == rep1["arms"] and rep2["judge"] == rep1["judge"]
    assert len(rep2["resumed"]) == 1 and rep1["resumed"] == []


def test_interrupted_run_resumes_midway(tmp_path):
    clean = run(tmp_path / "clean", make_llm())
    with pytest.raises(RuntimeError):
        run(tmp_path / "broken", make_llm(fail_at=60))
    resumed = run(tmp_path / "broken", make_llm())
    assert resumed["arms"] == clean["arms"] and resumed["boot"] == clean["boot"]


def test_interrupt_between_proposal_and_notes_does_not_duplicate_entries(tmp_path):
    store = nr.Store(tmp_path)
    rep = run(tmp_path, make_llm())
    # 2라운드 이후의 저장 지점과 1라운드 노트를 지워 "제안은 저장됐지만 노트는 저장 전"인 상태를 만든다
    for key in ("seen/r1/notes", "seen/r2/solve", "seen/r2/proposed", "seen/r2/notes", "seen/r3/solve", "seen/r3/proposed", "seen/r3/notes",
                "seen/final/T1", "seen/final/T2", "seen/final/T3"):
        store.path(key).unlink(missing_ok=True)
    rep2 = run(tmp_path, make_llm())
    assert rep2["arms"]["seen"]["notes_n"] == rep["arms"]["seen"]["notes_n"] == 1


def test_round_with_no_failures_still_finishes(tmp_path):                  # Review Focus 2
    llm = make_llm(always=("p-1", "p-2", "p-3", "p-4"))
    rep = run(tmp_path, llm)
    assert rep["arms"]["seen"]["notes_n"] == 0 and rep["arms"]["seen"]["decomp"]["d1"] == 0
    assert [c for c in llm.calls if c["model"] != common.WEAK_MODEL] == []
    assert rep["judge"]["H1"] == "확인 못 함" and rep["judge"]["H2"] == "판정 안 함"


def test_confirmatory_without_ladder_stops_with_message(tmp_path):         # Review Focus 4
    with pytest.raises(SystemExit, match="사다리 문항이 없습니다"):
        run(tmp_path, make_llm(), ladder_bank=[])


def test_real_confirmatory_refuses_dirty_tree(tmp_path):
    with pytest.raises(SystemExit, match="동결되지 않았습니다"):
        run(tmp_path, make_llm(), mock=False, freeze={"commit": "c", "dirty": True})


def test_store_from_other_commit_is_refused(tmp_path):
    run(tmp_path, make_llm())
    with pytest.raises(SystemExit, match="다른 커밋"):
        run(tmp_path, make_llm(), freeze={"commit": "other", "dirty": False})


def test_explore_store_cannot_be_reused_for_confirmatory(tmp_path):
    run(tmp_path, make_llm(), explore=True)
    with pytest.raises(SystemExit, match="탐색 실행"):
        run(tmp_path, make_llm())


def test_unpaired_public_item_is_trained_on_but_not_scored(tmp_path):
    ladder = [q for q in lad() if q.get("pair") != "p-4"]
    rep = run(tmp_path, make_llm(), ladder_bank=ladder)
    assert rep["n"] == {"T1": 3, "T2": 3, "T3": 3} and rep["dropped_pairs"] == ["p-4"]
    assert rep["arms"]["seen"]["t1_by_round"][0] == 0.0          # 학습 곡선은 기출 전체(4문항) 기준


def test_partial_arms_run_has_no_judgement(tmp_path):
    rep = run(tmp_path, make_llm(), arms=["seen"])
    assert set(rep["arms"]) == {"seen"} and rep["judge"] is None

