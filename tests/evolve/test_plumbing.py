"""Task 1: 노트 조건, 브리프 묶음, 사다리 은행, 문항·참고 글을 직접 받는 풀이."""
from __future__ import annotations

import json

import common
import solve
from fakes import fake_items, ns


def test_brief_bundle_week09_includes_week08(monkeypatch):
    monkeypatch.setattr(common, "brief_text", lambda w: f"<{w}>")
    assert common.brief_bundle("week09") == "<week08>\n\n<week09>"
    assert common.brief_bundle("week04") == "<week04>"


def test_notes_condition_returns_given_text():
    assert common.context_for("week09", "notes", notes_text="규칙 A") == "규칙 A"
    assert common.context_for("week09", "notes") == ""


def test_ladder_bank_missing_dir_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("LADDER_DIR", str(tmp_path / "none"))
    assert common.load_bank("ladder", ["week09"]) == []


def test_ladder_bank_keeps_rung_and_pair(tmp_path, monkeypatch):
    qs = [{**fake_items(1, "a")[0], "rung": "T2", "pair": "p1"}, {**fake_items(1, "b")[0], "rung": "T3"}]
    (tmp_path / "index.json").write_text(json.dumps({"banks": ["week09.json"]}), encoding="utf-8")
    (tmp_path / "week09.json").write_text(json.dumps({"week": "week09", "questions": qs}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("LADDER_DIR", str(tmp_path))
    bank = common.load_bank("ladder", ["week09"])
    assert [(q["rung"], q.get("pair")) for q in bank] == [("T2", "p1"), ("T3", None)]
    assert all(q["bank"] == "ladder" and q["week"] == "week09" for q in bank)


def test_run_with_explicit_bank_and_context(scripted_llm):
    llm = scripted_llm(lambda model, system, user, **kw: "ANSWER: 1")
    out = solve.run(ns(k=2), llm, bank=fake_items(3, "x"), context="노트 글")
    assert out["summary"]["n"] == 3 and out["summary"]["acc"] == 1.0
    assert len(llm.calls) == 6
    assert all("[참고 자료" in c["user"] and "노트 글" in c["user"] for c in llm.calls)


def test_run_with_empty_context_has_no_reference_block(scripted_llm):
    llm = scripted_llm(lambda *a, **kw: "ANSWER: 2")
    out = solve.run(ns(), llm, bank=fake_items(1, "x"), context="")
    assert "[참고 자료" not in llm.calls[0]["user"]
    assert out["summary"]["acc"] == 0.0


def test_run_copies_rung_and_pair_to_result_rows(scripted_llm):
    item = {**fake_items(1, "x")[0], "rung": "T2", "pair": "p-1"}
    out = solve.run(ns(), scripted_llm(lambda *a, **kw: "ANSWER: 1"), bank=[item], context="")
    assert out["results"][0]["rung"] == "T2" and out["results"][0]["pair"] == "p-1"


def test_report_index_lists_ladder_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "REPORT_DIR", tmp_path)
    (tmp_path / "ladder-exp1-week09.json").write_text(json.dumps({"exp": "exp1", "week": "week09", "date": "2026-11-25", "mock": True}), encoding="utf-8")
    common.update_report_index()
    idx = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert idx["ladders"] == [{"file": "ladder-exp1-week09.json", "exp": "exp1", "week": "week09", "date": "2026-11-25", "mock": True}]
