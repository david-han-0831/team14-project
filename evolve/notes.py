"""학습 노트: 노트 루프가 라운드마다 고쳐 쓰는 규칙 목록(교수님이 말한 "메모리").

풀이자는 이 노트만 보고 문제를 푼다. 항목에는 기계적 제약이 걸린다(모든 갈래 공통):
  - 규칙 문장은 3문장 이하
  - 보기 번호·위치, 문항 id 를 가리키는 표현 금지 (바꿔 쓴 문항에서는 보기 순서가 달라져 측정만 흐린다)
설계: docs/superpowers/specs/2026-11-24-transfer-ladder-counterexample-design.md 3.3
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MAX_SENTENCES = 3

# 문장 끝: 마침표·물음표·느낌표 뒤가 공백·글의 끝·새 문장의 첫 글자일 때, 또는 줄바꿈 (0.893 같은 소수점은 끊지 않는다)
_SENT_END = re.compile(r"[.?!](?=\s|$|[가-힣A-Z\"'(\[])|\n+")
# 마침표가 붙지만 문장 끝이 아닌 약어 (Lin et al. 2026, e.g., p. 25)
_ABBR = re.compile(r"\b(?:et al|e\.g|i\.e|vs|cf|Fig|pp?|No)\.", re.I)
# 보기를 번호·위치로 가리키는 표현. "3번 풀어" 같은 횟수 표현은 걸리지 않게 뒤따르는 말을 본다
_OPTION_REF = re.compile(
    # 동그라미 숫자는 보기를 가리킬 때만 막는다 (브리프처럼 "① … ② … ③ …" 로 열거하는 것은 괜찮다)
    r"(?:정답|답|보기|선택지)\s*(?:은|는|이|가)?\s*[:：]?\s*[①-⑤]"
    r"|[①-⑤]\s*번?\s*(?:을|를|이|가|은|는)?\s*(?:보기|선택지|고른|고르|골라|선택|정답|답이|답은|답을|맞|옳)"
    r"|(?<!\d)[1-5]\s*번\s*(?:을|를|이|가|은|는)?\s*(?:보기|선택지|고른|고르|골라|선택|정답|답이|답은|답을|맞)"
    r"|(?:정답|답)\s*(?:은|이|는)?\s*[1-5]\s*번"
    r"|(?:정답|답)\s*[:：]\s*[1-5](?![\d.])"
    r"|(?:보기|선택지)\s*[1-5](?!\d)"
    r"|(?:첫|두|세|네|다섯)\s*번째\s*(?:보기|선택지)"
    r"|마지막\s*(?:보기|선택지)"
)
# 문항을 번호·id 로 가리키는 표현. "문항 35개", "10번 문제없이" 같은 수량·횟수 표현은 걸리지 않게 한다
_ITEM_REF = re.compile(
    r"w\d\d[a-z]*-"
    r"|문항\s*\d+(?!\d|\s*개|\s*중|\s*문)"
    r"|\d+\s*번\s*(?:문제|문항)\s*(?:의|은|는|이|가|에서|에|처럼)"
    r"|문제\s*\d+\s*번"
)


def new_notes(week: str, arm: str) -> dict:
    return {"week": week, "arm": arm, "round": 0, "entries": [], "deleted": [], "seq": 0}


def check_rule(rule: str) -> list[str]:
    """항목 제약 위반 사유 목록. 빈 목록이면 통과."""
    rule = (rule or "").strip()
    if not rule:
        return ["empty"]
    why = []
    plain = _ABBR.sub(lambda m: m.group(0).replace(".", ""), rule)
    if len([s for s in _SENT_END.split(plain) if s.strip()]) > MAX_SENTENCES:
        why.append("too_long")
    if _OPTION_REF.search(rule):
        why.append("option_ref")
    if _ITEM_REF.search(rule):
        why.append("item_ref")
    return why


def _find(notes: dict, entry_id: str) -> dict:
    for e in notes["entries"]:
        if e["id"] == entry_id:
            return e
    raise KeyError(entry_id)


def add_entry(notes: dict, concept: str, rule: str, sources: list[str], origin_from: str, round_no: int) -> dict:
    why = check_rule(rule)
    if why:
        raise ValueError(f"노트 항목 제약 위반: {why}")
    notes["seq"] += 1
    e = {"id": f"n{notes['seq']:02d}", "concept": concept, "rule": rule.strip(), "sources": list(sources),
         "origin": {"round": round_no, "from": origin_from}, "history": []}
    notes["entries"].append(e)
    return e


def revise_entry(notes: dict, entry_id: str, new_rule: str, origin_from: str, round_no: int) -> None:
    why = check_rule(new_rule)
    if why:
        raise ValueError(f"노트 항목 제약 위반: {why}")
    e = _find(notes, entry_id)
    e["history"].append({"rule": e["rule"], "round": round_no, "replaced_by": origin_from})
    e["rule"] = new_rule.strip()


def delete_entry(notes: dict, entry_id: str, round_no: int) -> None:
    e = _find(notes, entry_id)
    notes["entries"].remove(e)
    notes["deleted"].append({**e, "deleted_round": round_no})


def notes_text(notes: dict) -> str:
    """풀이자에게 주는 글. 항목이 없으면 빈 문자열(= 자료 없음 조건과 같다)."""
    if not notes["entries"]:
        return ""
    return "[학습 노트]\n" + "\n".join(f"- ({e['concept']}) {e['rule']}" for e in notes["entries"])


def load_notes(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_notes(notes: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
