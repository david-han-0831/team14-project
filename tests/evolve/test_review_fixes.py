"""동결 전 독립 검토에서 나온 지적의 재현 테스트. 각 테스트 위에 지적 번호를 적는다."""
from __future__ import annotations

import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

import common
import counter
import ladder
import note_propose as np_
import note_round as nr
import notes
import solve
from fakes import PUB_MARK, SECRET, ScriptedLLM, fake_items, ns

FREEZE = {"commit": "testcommit", "dirty": False}
BRIEF = "강의 브리프 본문이다. 브리프 문장 하나가 여기 있다."


def s(point, lo, hi):
    return {"point": point, "lo": lo, "hi": hi}


# ================================================================ C1: 사용량 제한·빈 응답이 오답으로 굳는 문제
def _cli(monkeypatch, payload):
    """claude -p 가 항상 같은 JSON 을 돌려주게 한다. 잠든 시간 목록을 돌려준다."""
    sleeps = []
    monkeypatch.setattr(common.time, "sleep", sleeps.append)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(payload), stderr=""))
    llm = common.LLM(mock=False)
    llm.backend = "claude-cli"
    return llm, sleeps


def test_cli_raises_when_usage_limit_persists(monkeypatch):
    llm, sleeps = _cli(monkeypatch, {"is_error": True, "result": "Claude AI usage limit reached|1764000000"})
    with pytest.raises(RuntimeError, match="사용량 제한"):
        llm.ask(common.WEAK_MODEL, "s", "u")
    assert sleeps == [60, 120]            # 두 번 기다려 보고, 세 번째에도 같으면 멈춘다(빈 답을 돌려주지 않는다)


def test_cli_generic_failure_is_not_mistaken_for_rate_limit(monkeypatch):
    llm, sleeps = _cli(monkeypatch, {"is_error": True, "result": "Failed to generate response"})     # 'rate' 가 글자로 들어 있다
    with pytest.raises(RuntimeError, match="claude -p 실패"):
        llm.ask(common.WEAK_MODEL, "s", "u")
    assert sleeps == [5, 5]


def test_cli_retries_an_empty_successful_response(monkeypatch):
    llm, sleeps = _cli(monkeypatch, {"is_error": False, "result": "", "usage": {}})
    assert llm.ask(common.WEAK_MODEL, "s", "u") == ""
    assert sleeps == [5, 5]               # 빈 답은 두 번 더 시도한다. 그래도 비면 빈 문자열(엄격한 호출자가 멈춘다)


def test_strict_solve_raises_on_empty_response():
    with pytest.raises(RuntimeError, match="빈 응답"):
        solve.run(ns(), ScriptedLLM(lambda *a, **k: ""), bank=fake_items(1, "x"), context="", strict=True)


def test_non_strict_solve_keeps_old_behaviour():
    out = solve.run(ns(), ScriptedLLM(lambda *a, **k: ""), bank=fake_items(1, "x"), context="")
    assert out["summary"]["acc"] == 0.0


def test_strict_solve_accepts_unparseable_but_non_empty_answer():
    out = solve.run(ns(), ScriptedLLM(lambda *a, **k: "잘 모르겠습니다"), bank=fake_items(1, "x"), context="", strict=True)
    assert out["results"][0]["attempts"][0]["pred"] is None and out["summary"]["unparsed"] == 1


def pub():
    return fake_items(4, "p", mark=PUB_MARK)


def lad():
    t2 = [{**q, "rung": "T2", "pair": f"p-{i}", "bank": "ladder"} for i, q in enumerate(fake_items(4, "t2", mark=SECRET), 1)]
    return t2 + [{**q, "rung": "T3", "bank": "ladder"} for q in fake_items(3, "t3", mark=SECRET)]


def make_llm(empty_for=(), unparsed_for=()):
    def fn(model, system, user, hint=None):
        if model == common.WEAK_MODEL:
            qid = hint["q"]["id"]
            if qid in empty_for:
                return ""
            if qid in unparsed_for:
                return "잘 모르겠습니다"
            return "ANSWER: 1" if "[학습 노트]" in user and qid.startswith("p-") else "ANSWER: 2"
        tag = hashlib.sha1(user.encode()).hexdigest()[:6]
        return json.dumps({"entries": [{"concept": "c", "rule": f"규칙 {tag} 이다.", "sources": ["s"]}]}, ensure_ascii=False)
    return ScriptedLLM(fn)


def run(tmp_path, llm, exp="exp1", **kw):
    args = dict(explore=False, mock=True, public_bank=pub(), ladder_bank=lad(), freeze=FREEZE)
    args.update(kw)
    return nr.run_experiment(exp, "weekXX", llm, nr.Store(tmp_path), **args)


def test_note_round_stops_on_empty_solver_response_and_saves_nothing_for_that_step(tmp_path):
    with pytest.raises(RuntimeError, match="빈 응답"):
        run(tmp_path, make_llm(empty_for=("t3-2",)))
    store = nr.Store(tmp_path)
    assert store.get("baseline/T1") is not None and store.get("baseline/T3") is None      # 끊긴 단계는 저장되지 않는다
    rep = run(tmp_path, make_llm())                                                         # 다시 돌리면 그 단계부터 한다
    assert rep["unparsed_attempts"] == {"baseline": 0, "seen": 0, "concept": 0}


def test_report_counts_unparsed_attempts(tmp_path):
    rep = run(tmp_path, make_llm(unparsed_for=("t3-1",)))
    assert rep["unparsed_attempts"] == {"baseline": 3, "seen": 3, "concept": 3}


def test_counter_probe_is_strict():
    n = notes.new_notes("weekXX", "seen+ce")
    notes.add_entry(n, "c", "규칙이다.", ["s"], "public-fail", 1)
    ce = {"id": "ce-1", "entry_id": "n01", "type": "mc", "week": "weekXX", "concept": "c", "q": "문항", "options": ["a", "b", "c", "d"], "answer": 0, "trap": 1}
    with pytest.raises(RuntimeError, match="빈 응답"):
        counter.probe([ce], notes.notes_text(n), ScriptedLLM(lambda *a, **k: ""))
    with pytest.raises(RuntimeError, match="빈 응답"):
        counter.validate([ce], BRIEF, ScriptedLLM(lambda *a, **k: ""))


# ================================================================ I1·I2: H3 판정
def _exp2_boot(d1_point, o_lo=0.02):
    return {"seen": {"O": s(.3, .1, .5)}, "diff": {"seen+rev|seen+ce": {"O": s(.15, o_lo, .3)}, "seen+ce|seen+rev": {"d1": s(d1_point, -.2, .1)}}}


def test_h3_passes_when_d1_loss_is_exactly_one_item():
    # n=18, k=3 → Δ1 차이는 1/54 격자. 한 문항분(3/54 = 0.05555…)은 4자리 반올림으로 −0.0556 이 된다. "한 문항분 넘게 낮지 않다" 이므로 통과
    assert ladder.judge(_exp2_boot(round(-3 / 54, 4)), 18, "exp2", h1_exp1="확인")["H3"] == "확인"
    assert ladder.judge(_exp2_boot(round(-4 / 54, 4)), 18, "exp2", h1_exp1="확인")["H3"] == "확인 못 함"


def test_h3_is_not_judged_unless_exp1_confirmed_h1():
    for h1 in ("확인 못 함", None):
        j = ladder.judge(_exp2_boot(0.0), 18, "exp2", h1_exp1=h1)
        assert j["H3"] == "판정 안 함" and j["H1_실험1"] == (h1 or "없음")
    j = ladder.judge(_exp2_boot(0.0), 18, "exp2", h1_exp1="확인")
    assert j == {"H3": "확인", "H1_재현": "재현", "H1_실험1": "확인"}


# ================================================================ I3·I4: 동결 보장
def test_real_confirmatory_refuses_unknown_commit(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="커밋을 확인할 수 없습니다"):
        run(tmp_path, make_llm(), mock=False, freeze={"commit": "unknown", "dirty": False})


def test_freeze_info_checks_briefs_and_public_bank_too(monkeypatch):
    seen = []
    monkeypatch.setattr(nr, "_git", lambda *a: seen.append(a) or "")
    nr.freeze_info()
    status = next(a for a in seen if a[0] == "status")
    assert {"evolve", "content/briefs", "assets/data/quiz"} <= set(status)


def _ladder_hash(items):
    return nr.ladder_hash(items)


def test_real_confirmatory_checks_expected_ladder_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(nr, "LADDER_SHA256", {"weekXX": "0" * 64})
    with pytest.raises(SystemExit, match="사다리 문항이 동결한 것과 다릅니다"):
        run(tmp_path, make_llm(), mock=False)
    monkeypatch.setattr(nr, "LADDER_SHA256", {})
    with pytest.raises(SystemExit, match="동결한 사다리 해시가 없습니다"):
        run(tmp_path, make_llm(), mock=False)
    monkeypatch.setattr(nr, "LADDER_SHA256", {"weekXX": _ladder_hash(lad())})
    assert run(tmp_path, make_llm(), mock=False)["mock"] is False


def test_mock_store_cannot_feed_a_real_run(tmp_path, monkeypatch):
    monkeypatch.setattr(nr, "LADDER_SHA256", {"weekXX": _ladder_hash(lad())})
    run(tmp_path, make_llm(), mock=True)
    with pytest.raises(SystemExit, match="가짜 풀이자"):
        run(tmp_path, make_llm(), mock=False)


def test_resume_with_a_different_ladder_is_refused(tmp_path):
    run(tmp_path, make_llm())
    changed = lad()
    changed[-1] = {**changed[-1], "q": changed[-1]["q"] + " (바뀜)"}
    with pytest.raises(SystemExit, match="사다리 문항이 처음 시작할 때와 다릅니다"):
        run(tmp_path, make_llm(), ladder_bank=changed)


def test_resume_with_different_settings_is_refused(tmp_path, monkeypatch):
    run(tmp_path, make_llm())
    monkeypatch.setattr(nr, "K", 5)
    with pytest.raises(SystemExit, match="설정이 처음 시작할 때와 다릅니다"):
        run(tmp_path, make_llm())


def test_freeze_params_record_models_and_counterexample_settings(tmp_path):
    p = run(tmp_path, make_llm())["freeze"]["params"]
    assert p["solver"] == common.WEAK_MODEL and p["proposer"] == common.STRONG_MODEL and p["validator"] == common.MID_MODEL
    assert (p["ce_per_entry"], p["ce_passes"], p["validate_k"], p["overlap"]) == (1, 2, 2, 0.5)
    assert p["backend"] == common.BACKEND and "cli_isolation" in p


def _report(run_started="A", arms=("seen", "concept"), mock=False):
    return {"exp": "exp1", "week": "weekXX", "mock": mock, "run_started": run_started, "arms": {a: {} for a in arms}, "freeze": {"commit": "c"}}


def test_publish_refuses_to_overwrite_a_report_from_another_run(tmp_path, monkeypatch):
    monkeypatch.setattr(nr, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(nr, "NOTES_DIR", tmp_path / "notes")
    monkeypatch.setattr(nr, "update_report_index", lambda: None)
    store = nr.Store(tmp_path / "store")
    for arm in ("seen", "concept"):
        for r in (1, 2, 3):
            store.put(f"{arm}/r{r}/notes", {"notes": notes.new_notes("weekXX", arm)})
    out = nr.publish(_report("A"), store)
    assert out.name == "ladder-exp1-weekXX.json"
    assert nr.publish(_report("A"), store) == out                 # 같은 실행을 이어 돌린 뒤 다시 쓰는 것은 된다
    with pytest.raises(SystemExit, match="이미 확정 실행 리포트가 있습니다"):
        nr.publish(_report("B"), store)


def test_existing_report_blocks_a_fresh_confirmatory_run_before_any_call(tmp_path, monkeypatch):
    monkeypatch.setattr(nr, "REPORT_DIR", tmp_path / "reports")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "ladder-exp1-weekXX.json").write_text(json.dumps(_report("A")), encoding="utf-8")
    with pytest.raises(SystemExit, match="이미 확정 실행 리포트가 있습니다"):
        nr.guard_existing_report("exp1", "weekXX", False, nr.Store(tmp_path / "fresh"))
    resumed = nr.Store(tmp_path / "same")
    resumed.put("meta", {"started": "A"})
    nr.guard_existing_report("exp1", "weekXX", False, resumed)       # 같은 실행이면 통과
    nr.guard_existing_report("exp1", "weekXX", True, nr.Store(tmp_path / "fresh"))     # mock 은 다른 파일 이름이라 무관


def test_partial_arm_run_is_not_published(tmp_path, monkeypatch):
    monkeypatch.setattr(nr, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(nr, "NOTES_DIR", tmp_path / "notes")
    assert nr.publish(_report("A", arms=("seen",)), nr.Store(tmp_path / "store")) is None
    assert not (tmp_path / "reports").exists()


def test_report_carries_run_start_time(tmp_path):
    rep = run(tmp_path, make_llm())
    assert rep["run_started"] == nr.Store(tmp_path).get("meta")["started"]


# ================================================================ I5: 대조군 예산
def _rev_llm():
    return ScriptedLLM(lambda model, system, user, hint=None: json.dumps({"action": "rewrite", "rule": f"고친 규칙 {hint['entry_id']} 이다."}, ensure_ascii=False))


def test_treat_rev_spills_to_older_entries_when_there_are_no_new_ones():
    n = notes.new_notes("weekXX", "seen+rev")
    notes.add_entry(n, "c1", "오래된 규칙 하나다.", ["s"], "public-fail", 1)
    notes.add_entry(n, "c2", "오래된 규칙 둘이다.", ["s"], "public-fail", 2)
    out = counter.treat_rev(n, [], budget=2, brief=BRIEF, llm=_rev_llm(), round_no=3)
    assert out["revised"] == ["n02", "n01"] and out["revise_calls"] == 2 and out["budget"] == 2 and out["unspent"] == 0


def test_treat_rev_uses_new_entries_first_then_older_ones():
    n = notes.new_notes("weekXX", "seen+rev")
    for i in range(3):
        notes.add_entry(n, f"c{i}", f"규칙 {i} 이다.", ["s"], "public-fail", 1)
    out = counter.treat_rev(n, ["n03"], budget=2, brief=BRIEF, llm=_rev_llm(), round_no=2)
    assert out["revised"] == ["n03", "n02"]


def test_treat_rev_reports_unspent_budget_when_notes_are_empty():
    out = counter.treat_rev(notes.new_notes("weekXX", "seen+rev"), [], budget=2, brief=BRIEF, llm=_rev_llm(), round_no=1)
    assert out["revise_calls"] == 0 and out["budget"] == 2 and out["unspent"] == 2


# ================================================================ I6: 버린 사유 기록, 형식 방어
def _gen(eid, quote="브리프 문장 하나", options=None):
    return json.dumps({"q": f"{eid} 규칙을 그대로 따르면 틀리게 되는 상황을 묻는 반례 문항이다",
                       "options": options if options is not None else [f"옳은 설명 {eid}", f"함정 {eid}", f"틀린 가 {eid}", f"틀린 나 {eid}"],
                       "answer_text": f"옳은 설명 {eid}", "trap_text": f"함정 {eid}", "quote": quote}, ensure_ascii=False)


def test_treat_ce_records_why_each_counterexample_was_dropped():
    n = notes.new_notes("weekXX", "seen+ce")
    for i in range(1, 4):
        notes.add_entry(n, f"c{i}", f"처음 규칙 {i} 이다.", ["s"], "public-fail", 1)

    def fn(model, system, user, hint=None):
        if system == counter.GEN_SYSTEM:
            eid = hint["entry_id"]
            return "죄송합니다" if eid == "n01" else _gen(eid, quote="브리프에 없는 인용 문장이다" if eid == "n02" else "브리프 문장 하나")
        q = hint["q"]
        return f"ANSWER: {q['trap'] + 1}"              # 거르는 풀이자도 틀린다 → validator 탈락
    out = counter.treat_ce(n, ["n01", "n02", "n03"], brief=BRIEF, llm=ScriptedLLM(fn), public_bank=[], ladder_bank=[], week="weekXX", round_no=1)
    assert out["dropped"] == [{"entry_id": "n01", "why": ["parse"]}, {"entry_id": "n02", "why": ["quote_not_in_brief"]}, {"entry_id": "n03", "why": ["validator"]}]


def test_overlap_drop_is_recorded_without_item_text():
    n = notes.new_notes("weekXX", "seen+ce")
    notes.add_entry(n, "c1", "처음 규칙이다.", ["s"], "public-fail", 1)
    leaked = SECRET + " 평가 문항과 글자까지 똑같은 반례 문항 문장이다"

    def fn(model, system, user, hint=None):
        return json.dumps({"q": leaked, "options": ["가 보기", "나 보기", "다 보기", "라 보기"], "answer_text": "가 보기", "trap_text": "나 보기", "quote": "브리프 문장 하나"}, ensure_ascii=False)
    out = counter.treat_ce(n, ["n01"], brief=BRIEF, llm=ScriptedLLM(fn), public_bank=[], ladder_bank=[{"id": "t3-1", "q": leaked, "options": [], "rung": "T3"}], week="weekXX", round_no=1)
    assert out["dropped"] == [{"entry_id": "n01", "why": ["overlap"]}]
    assert SECRET not in json.dumps({k: v for k, v in out.items() if k != "ces"}, ensure_ascii=False) and out["ces"] == []


@pytest.mark.parametrize("options", [5, "가나다라", ["a", "b", "c", 4], None])
def test_generate_rejects_malformed_options(options):
    n = notes.new_notes("weekXX", "seen+ce")
    notes.add_entry(n, "c1", "처음 규칙이다.", ["s"], "public-fail", 1)
    llm = ScriptedLLM(lambda *a, **k: json.dumps({"q": "문항", "options": options, "answer_text": "a", "trap_text": "b", "quote": "브리프 문장 하나"}))
    assert counter.generate(n["entries"][0], BRIEF, llm, week="weekXX", ce_id="x") is None


def test_revise_prompt_does_not_claim_what_the_student_chose():
    n = notes.new_notes("weekXX", "seen+ce")
    notes.add_entry(n, "c1", "처음 규칙이다.", ["s"], "public-fail", 1)
    ce = {"q": "반례 문제", "options": ["옳은", "함정", "다", "라"], "answer": 0, "trap": 1}
    llm = ScriptedLLM(lambda *a, **k: json.dumps({"action": "keep"}))
    counter.revise(n["entries"][0], ce, BRIEF, llm)
    user = llm.calls[0]["user"]
    assert "학생이 고른 보기" not in user and "규칙만 믿으면 고르게 되는 보기: 함정" in user


def test_unparseable_proposal_is_recorded():
    n = notes.new_notes("weekXX", "seen")
    out = np_.propose_entries("seen", "weekXX", fake_items(1, "p"), n, ScriptedLLM(lambda *a, **k: "죄송합니다. " + "가" * 500), public_bank=[])
    assert out["parse_failed"] is True and out["raw_head"].startswith("죄송합니다.") and len(out["raw_head"]) <= 300
    ok = np_.propose_entries("seen", "weekXX", fake_items(1, "p"), n,
                             ScriptedLLM(lambda *a, **k: json.dumps({"entries": [{"concept": "c", "rule": "규칙이다.", "sources": "week09 개념 4"}]}, ensure_ascii=False)), public_bank=[])
    assert ok["parse_failed"] is False and "raw_head" not in ok
    assert n["entries"][0]["sources"] == ["week09 개념 4"]           # 문자열 출처를 글자 단위로 쪼개지 않는다


# ================================================================ 노트 항목 제약의 빈틈 (Minor 였으나 동결되는 제약이라 함께 고침)
@pytest.mark.parametrize("concept", ["w09a-c28 정답", "정답은 3번을 고른다", "가" * 61])
def test_concept_field_is_checked_like_the_rule(concept):
    n = notes.new_notes("weekXX", "seen")
    llm = ScriptedLLM(lambda *a, **k: json.dumps({"entries": [{"concept": concept, "rule": "규칙이다.", "sources": ["s"]}]}, ensure_ascii=False))
    out = np_.propose_entries("seen", "weekXX", fake_items(1, "p"), n, llm, public_bank=[])
    assert out["added"] == [] and out["rejected"][0]["why"] == ["concept"]


def test_proposer_is_told_the_cap():
    user = np_.build_user("seen", "weekXX", fake_items(7, "p"), notes.new_notes("weekXX", "seen"), "브리프", max_new=5)
    assert "최대 5개" in user


@pytest.mark.parametrize("rule", [
    "ADAS(Hu et al. 2025)는 메타 에이전트가 설계한다. AFlow(Zhang et al. 2025)는 MCTS 로 탐색한다. 두 방법은 워크플로우 디자인에 속한다.",
    "학습 문항 35개 중 21개에 같은 선택지가 나왔고 항상 정답이었다.",
    "같은 문제를 10번 문제없이 풀면 pass^10 이 1 이다.",
    "예를 들어 p. 25 의 표에서 e.g. 분류 과제의 초기 하네스를 든다. 값은 0.893 이다. 이것이 근거다.",
])
def test_check_rule_false_positives_are_gone(rule):
    assert notes.check_rule(rule) == []


@pytest.mark.parametrize("rule,code", [
    ("이 경우 3번을 선택한다.", "option_ref"),
    ("이런 질문은 3번이 맞다.", "option_ref"),
    ("마지막 보기를 고른다.", "option_ref"),
    ("답: 3", "option_ref"),
    ("하나다.둘이다.셋이다.넷이다.", "too_long"),
    ("하나다\n둘이다\n셋이다\n넷이다", "too_long"),
])
def test_check_rule_catches_the_evasions(rule, code):
    assert code in notes.check_rule(rule)
