from __future__ import annotations

import pytest

from conftest import raw_question
from livelab import core


def test_bank_week09_has_18_questions_without_answers():
    b = core.bank("week09")
    assert b["set"] == "week09" and b["weeks"] == ["week09"]
    assert len(b["questions"]) == 18
    for q in b["questions"]:
        assert set(q) == {"id", "week", "type", "q", "options", "concept"}


def test_bank_seed_has_39_questions():
    b = core.bank("seed")
    assert b["weeks"] == ["week02", "week04", "week08"] and len(b["questions"]) == 39


def test_bank_num_question_has_no_options():
    nums = [q for q in core.bank("week09")["questions"] if q["type"] == "num"]
    assert nums and all(q["options"] is None for q in nums)


def test_bank_unknown_set_is_400():
    with pytest.raises(core.LiveError) as e:
        core.bank("week99")
    assert e.value.status == 400


@pytest.mark.parametrize("qid,cond", [("w09a-c03", "everything"), ("nope", "none"), ("", "none")])
def test_solve_rejects_unknown_inputs(qid, cond):
    with pytest.raises(core.LiveError) as e:
        core.solve(qid, cond)
    assert e.value.status == 400


def test_solve_grades_correct_answer(fake_llm_factory):
    q = raw_question("w09a-c03")
    r = core.solve("w09a-c03", "none", llm=fake_llm_factory(f"풀이\nANSWER: {q['answer'] + 1}"))
    assert r["qid"] == "w09a-c03" and r["condition"] == "none"
    assert r["correct"] is True and r["pred"] == q["answer"]
    assert r["input_tokens"] == 120 and r["output_tokens"] == 30 and r["ms"] >= 0


def test_solve_grades_wrong_answer(fake_llm_factory):
    q = raw_question("w09a-c03")
    wrong = (q["answer"] + 1) % len(q["options"])
    r = core.solve("w09a-c03", "none", llm=fake_llm_factory(f"ANSWER: {wrong + 1}"))
    assert r["correct"] is False and r["pred"] == wrong


def test_solve_unparseable_answer_is_wrong_not_error(fake_llm_factory):
    r = core.solve("w09a-c03", "page", llm=fake_llm_factory("모르겠습니다"))
    assert r["pred"] is None and r["correct"] is False


def test_solve_prompt_has_context_only_when_condition_gives_one(fake_llm_factory):
    llm = fake_llm_factory("ANSWER: 1")
    core.solve("w09a-c03", "none", llm=llm)
    assert "[참고 자료" not in llm.last_user and llm.last_user.startswith("[문제]\n")
    assert llm.last_model == "claude-haiku-5-5" and llm.last_effort == "low"
    llm = fake_llm_factory("ANSWER: 1")
    core.solve("w09a-c03", "page", llm=llm)
    assert llm.last_user.startswith("[참고 자료: week09]\n") and "\n\n[문제]\n" in llm.last_user


def test_solve_never_sends_the_answer_key_to_the_solver(fake_llm_factory):
    q = raw_question("w09a-c03")
    llm = fake_llm_factory("ANSWER: 1")
    core.solve("w09a-c03", "none", llm=llm)
    assert q["explanation"][:40] not in llm.last_user


def test_solve_is_503_when_disabled(monkeypatch):
    monkeypatch.setenv("LIVE_DISABLED", "1")
    with pytest.raises(core.LiveError) as e:
        core.solve("w09a-c03", "none")
    assert e.value.status == 503


def test_solve_with_mock_env_returns_a_graded_result():
    r = core.solve("w09a-c03", "brief")
    assert isinstance(r["correct"], bool) and isinstance(r["input_tokens"], int)


@pytest.mark.parametrize("env,expected", [
    ({}, False),
    ({"ANTHROPIC_API_KEY": ""}, False),
    ({"ANTHROPIC_API_KEY": "x"}, True),
    ({"ANTHROPIC_API_KEY": "x", "LIVE_DISABLED": "1"}, False),
    ({"ANTHROPIC_API_KEY": "x", "LIVE_DISABLED": "true"}, False),
    ({"LIVE_MOCK": "1"}, True),
    ({"LIVE_MOCK": "1", "LIVE_DISABLED": "1"}, False),
])
def test_is_live(env, expected):
    assert core.is_live(env) is expected


def test_llm_retry_exhaustion_maps_to_429_without_leaking_detail(raising_llm_factory):
    with pytest.raises(core.LiveError) as e:
        core.solve("w09a-c03", "none", llm=raising_llm_factory(RuntimeError("API 재시도 실패")))
    assert e.value.status == 429 and "재시도 실패" not in e.value.message


def test_llm_api_error_maps_to_502(raising_llm_factory):
    import anthropic
    import httpx

    exc = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    with pytest.raises(core.LiveError) as e:
        core.solve("w09a-c03", "none", llm=raising_llm_factory(exc))
    assert e.value.status == 502


def test_health_lists_sets_with_counts():
    h = core.health()
    assert h["live"] is True and h["model"] == "claude-haiku-5-5"
    assert {(s["name"], s["n"]) for s in h["sets"]} == {("week09", 18), ("seed", 39)}


def test_reports_include_recorded_week09_run():
    r = next(x for x in core.reports() if x["weeks"] == "week09")
    assert [(run["condition"], run["acc"]) for run in r["runs"]] == [("none", 0.6667), ("brief", 1.0), ("page", 0.9444)]
    assert r["runs"][0]["n"] == 18 and len(r["runs"][0]["acc_ci95"]) == 2
