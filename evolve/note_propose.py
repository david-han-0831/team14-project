"""노트 제안자: 풀이자가 틀린 기출을 바탕으로 학습 노트 항목을 덧붙인다.

갈래마다 제안자가 보는 것이 다르다 (설계 3.4 "누가 무엇을 보는가").
  seen 계열 (seen, seen+ce, seen+rev)  틀린 기출의 문제·보기·정답 내용 + 브리프   ← 실제 자가 진화 에이전트와 같은 조건
  concept                              틀린 기출의 개념 이름만 + 브리프           ← 페이지 루프의 규칙
평가 전용 문항은 이 모듈에 들어오지 않는다. 이 모듈은 은행을 직접 읽지 않고 넘겨받은 것만 쓴다.
"""
from __future__ import annotations

import json
import re

from common import STRONG_MODEL, brief_bundle
from notes import add_entry, check_rule, notes_text
from verify import leakage

ARMS = ("seen", "concept", "seen+ce", "seen+rev")

SYSTEM = (
    "당신은 대학원 '최신딥러닝이론및응용' 수업의 학습 노트를 쓰는 조교입니다. "
    "다른 학생은 이 노트만 보고 시험을 봅니다. 주어진 강의 브리프만 근거로 쓰고, 브리프에 없는 내용은 쓰지 않습니다. "
    "출력은 JSON 하나만: {\"entries\": [{\"concept\", \"rule\", \"sources\"}]}. "
    "rule 은 설명문 3문장 이하입니다. 보기 번호나 보기의 위치, 문제 번호를 가리키는 말은 쓰지 않습니다. "
    "sources 는 근거가 된 브리프의 절 이름 배열입니다. 이미 노트에 있는 내용은 다시 쓰지 않습니다."
)


def sees_items(arm: str) -> bool:
    if arm not in ARMS:
        raise ValueError(arm)
    return arm != "concept"


def _item_block(i: int, q: dict) -> str:
    """기출 한 문항을 제안자에게 보여 주는 글. 보기 번호와 문항 id 는 넣지 않는다."""
    s = f"({i}) 개념: {q.get('concept', '')}\n    문제: {q['q'].strip()}"
    if q["type"] == "mc":
        s += "\n    보기: " + " / ".join(o.strip() for o in q["options"])
        s += f"\n    옳은 보기의 내용: {q['options'][int(q['answer'])].strip()}"
    else:
        s += f"\n    옳은 값: {q['answer']}{(' ' + q['unit']) if q.get('unit') else ''}"
    return s


MAX_CONCEPT = 60     # 개념 이름의 최대 길이. 풀이자는 "(개념) 규칙"을 보므로 개념 칸도 제약을 받는다


def build_user(arm: str, week: str, failed: list[dict], notes: dict, brief: str, max_new: int = 5) -> str:
    cur = notes_text(notes) or "(아직 비어 있음)"
    if sees_items(arm):
        body = "[풀이자가 틀린 기출 문제]\n" + "\n".join(_item_block(i, q) for i, q in enumerate(failed, 1))
        ask = "위 문제들을 다음에는 맞힐 수 있도록 노트에 덧붙일 항목을 쓰세요."
    else:
        concepts = list(dict.fromkeys(q.get("concept") or "(미분류)" for q in failed))
        body = "[풀이자가 약한 개념]\n" + "\n".join(f"- {c}" for c in concepts)
        ask = "위 개념을 이해하는 데 필요한 내용을 노트에 덧붙일 항목으로 쓰세요."
    limits = (f"항목은 최대 {max_new}개입니다(넘는 것은 버려집니다. 더 다뤄야 하면 중요한 것부터, 한 항목이 여러 내용을 함께 다뤄도 됩니다). "
              f"rule 은 3문장 이하, concept 은 {MAX_CONCEPT}자 이하의 짧은 개념 이름입니다(넘으면 그 항목은 버려집니다).")
    return (f"[주차] {week}\n\n[지금의 학습 노트]\n{cur}\n\n{body}\n\n[강의 브리프]\n{brief}\n\n{ask} {limits} JSON 으로만 답합니다.")


def _norm(rule: str) -> str:
    return re.sub(r"\s+", "", rule)


def parse_entries(text: str) -> list[dict]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    ents = obj.get("entries") if isinstance(obj, dict) else None
    return [e for e in ents if isinstance(e, dict)] if isinstance(ents, list) else []


def propose_entries(arm: str, week: str, failed: list[dict], notes: dict, llm, public_bank: list[dict],
                    max_new: int = 5, round_no: int = 0) -> dict:
    """통과한 항목을 notes 에 덧붙인다(수정·삭제는 하지 않는다). 버린 항목은 사유와 함께 돌려준다."""
    if not failed:
        return {"added": [], "rejected": [], "raw_n": 0, "parse_failed": False}
    text = llm.ask(STRONG_MODEL, SYSTEM, build_user(arm, week, failed, notes, brief_bundle(week), max_new), effort="high", max_tokens=6000,
                   mock_hint={"kind": "note_propose", "concept": failed[0].get("concept", "")})
    raw = parse_entries(text)
    added, rejected = [], []
    for e in raw:
        rule = str(e.get("rule") or "").strip()
        concept = str(e.get("concept") or "").strip()
        src = e.get("sources")
        sources = [src] if isinstance(src, str) and src.strip() else [str(x) for x in src] if isinstance(src, list) else []
        why: list[str] = []
        if not rule or not concept:
            why = ["format"]
        elif not sources:
            why = ["no_sources"]
        elif len(concept) > MAX_CONCEPT or check_rule(concept):
            why = ["concept"]
        else:
            why = check_rule(rule)
            if not why and _norm(rule) in {_norm(x["rule"]) for x in notes["entries"]}:
                why = ["duplicate"]
            if not why and arm == "concept" and leakage([{"week": week, "card_id": "note", "title": "", "pro": rule, "easy": ""}], public_bank):
                why = ["leak"]     # 개념만 보는 갈래는 기출 문장을 베낄 수 없다 (페이지 루프와 같은 검사)
        if not why and len(added) >= max_new:
            why = ["over_cap"]
        if why:
            rejected.append({"concept": concept, "rule": rule, "why": why})
            continue
        added.append(add_entry(notes, concept, rule, sources, "public-fail", round_no))
    out = {"added": added, "rejected": rejected, "raw_n": len(raw), "parse_failed": not raw}
    if not raw:      # 통째로 해석하지 못한 응답: 빈 제안과 구분되게 앞부분을 남긴다(탐색 실행에서 원인을 보려고)
        out["raw_head"] = (text or "")[:300]
    return out
