"""반례 처치: 노트 규칙을 글자 그대로 따르면 틀리는 문항을 만들어, 그 문항에서 틀린 규칙을 고쳐 쓴다 (설계 3.5).

교수님 제안("메모리 규칙대로 풀면 틀릴 문제를 만들어 학습시키면 규칙이 완화되지 않을까")을 옮긴 것이다.
  ① 출제   항목마다 반례 1문항 (함정 보기 + 브리프 인용)                       큰 모델, 노트 항목과 브리프만 본다
  ② 거르기 기계 검사 → 평가 문항과의 문장 겹침(스크립트만 본다) → 브리프를 본 풀이자가 2회 모두 정답
  ③ 풀기   풀이자가 지금 노트만 보고 반례를 푼다 (3회)
  ④ 고치기 틀린 반례의 항목을 [항목, 반례와 정답, 브리프]로 고쳐 쓴다
  고친 항목에 대해 한 번 더. 반례 문항은 학습용이며 평가에 쓰지 않는다.
treat_rev 는 대조군이다: 반례 없이 같은 횟수만큼 고쳐 쓰기만 한다.
"""
from __future__ import annotations

import json
import random
import re
from types import SimpleNamespace

from common import MID_MODEL, STRONG_MODEL, WEAK_MODEL
from notes import check_rule, delete_entry, notes_text, revise_entry
from solve import run as solve_run

OVERLAP = 0.5        # 문장 3-gram 자카드. 이 값 이상이면 같은 문항으로 본다
MIN_QUOTE = 6        # 브리프 인용의 최소 길이(공백 제외)
CE_PASSES = 2        # 라운드당 반례 처치 횟수 (2회차는 고친 항목에만)
VALIDATE_K = 2       # 거르는 풀이자가 맞혀야 하는 횟수

GEN_SYSTEM = (
    "당신은 대학원 '최신딥러닝이론및응용' 수업의 출제자입니다. 학생의 학습 노트에 적힌 규칙 하나가 주어집니다. "
    "그 규칙을 글자 그대로 따르거나 지나치게 넓혀 적용하는 학생이 틀리게 되는 객관식 문제 하나를 만듭니다. "
    "보기는 넷입니다. 하나는 강의 브리프로 뒷받침되는 옳은 보기이고, 하나는 노트의 규칙만 믿으면 고르게 되는 함정 보기입니다. 나머지 둘도 브리프 기준으로 틀려야 합니다. "
    "문제는 브리프에 있는 내용만으로 답이 하나로 정해져야 합니다. 브리프에 없는 내용, '확인 필요'로 표시된 내용은 쓰지 않습니다. "
    "출력은 JSON 하나만: {\"q\", \"options\"(문자열 4개), \"answer_text\"(옳은 보기를 그대로), \"trap_text\"(함정 보기를 그대로), \"quote\"(정답의 근거가 되는 브리프 문장을 그대로)}."
)
REVISE_SYSTEM = (
    "당신은 대학원 '최신딥러닝이론및응용' 수업의 학습 노트를 고쳐 쓰는 조교입니다. 다른 학생은 이 노트만 보고 시험을 봅니다. "
    "주어진 노트 항목 하나를 강의 브리프에 비추어 고칩니다. 할 수 있는 일: 조건·예외·적용 범위를 덧붙인다, 규칙을 더 일반적으로 바꾼다, 틀렸거나 쓸모없으면 지운다, 고칠 것이 없으면 그대로 둔다. "
    "고친 규칙은 설명문 3문장 이하입니다. 보기 번호나 보기의 위치, 문제 번호를 가리키는 말은 쓰지 않습니다. 브리프에 없는 내용은 쓰지 않습니다. "
    "출력은 JSON 하나만: {\"action\": \"rewrite\" | \"delete\" | \"keep\", \"rule\": \"rewrite 일 때 고친 규칙\"}."
)


def _json(text: str):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _plain(s: str) -> str:
    """인용 대조용: 공백과 마크다운 강조 기호를 뺀다."""
    return re.sub(r"[\s*`_]+", "", s or "")


def _grams(s: str, n: int = 3) -> set[str]:
    s = re.sub(r"\s+", "", s or "")
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def _jacc(a: str, b: str) -> float:
    ga, gb = _grams(a), _grams(b)
    return len(ga & gb) / len(ga | gb) if ga and gb else 0.0


def _entry(notes: dict, entry_id: str) -> dict | None:
    return next((e for e in notes["entries"] if e["id"] == entry_id), None)


# ---------------------------------------------------------------- ① 출제
def generate(entry: dict, brief: str, llm, week: str, ce_id: str) -> dict | None:
    """노트 항목 하나에 대한 반례 문항. 해석할 수 없으면 None. 보기 순서는 ce_id 로 정해지는 순서로 섞는다."""
    user = (f"[노트 항목]\n({entry['concept']}) {entry['rule']}\n\n[강의 브리프]\n{brief}\n\n"
            "이 규칙만 믿는 학생이 틀리게 되는 객관식 문제 하나를 JSON 으로만 답합니다.")
    obj = _json(llm.ask(STRONG_MODEL, GEN_SYSTEM, user, effort="high", max_tokens=4000,
                        mock_hint={"kind": "ce_generate", "entry_id": entry["id"], "quote": brief.strip()[:40]}))
    raw_opts = (obj or {}).get("options")
    if not obj or not isinstance(raw_opts, list) or not all(isinstance(o, str) for o in raw_opts):
        return None
    opts = [o.strip() for o in raw_opts]
    ans, trap = str(obj.get("answer_text") or "").strip(), str(obj.get("trap_text") or "").strip()
    if not str(obj.get("q") or "").strip() or opts.count(ans) != 1 or opts.count(trap) != 1:
        return None
    random.Random(ce_id).shuffle(opts)
    return {"id": ce_id, "entry_id": entry["id"], "type": "mc", "week": week, "concept": entry["concept"],
            "q": str(obj["q"]).strip(), "options": opts, "answer": opts.index(ans), "trap": opts.index(trap),
            "evidence": {"quote": str(obj.get("quote") or "").strip()}}


# ---------------------------------------------------------------- ② 거르기
def mechanical_check(ce: dict, brief: str, public_bank: list[dict]) -> list[str]:
    why = []
    opts = ce.get("options") or []
    ok_form = bool(str(ce.get("q") or "").strip()) and len(opts) == 4 and len(set(opts)) == 4 \
        and all(isinstance(ce.get(k), int) and 0 <= ce[k] < len(opts) for k in ("answer", "trap"))
    if not ok_form:
        why.append("format")
    if ce.get("answer") == ce.get("trap"):
        why.append("trap_is_answer")
    quote = _plain((ce.get("evidence") or {}).get("quote", ""))
    if len(quote) < MIN_QUOTE or quote not in _plain(brief):
        why.append("quote_not_in_brief")
    if any(_jacc(ce.get("q", ""), p["q"]) >= OVERLAP for p in public_bank):
        why.append("dup_public")
    return why


def overlap_drop(ces: list[dict], ladder_bank: list[dict]) -> tuple[list[dict], dict]:
    """평가 문항(전이 사다리)과 문장이 겹치는 반례를 뺀다. 스크립트만 비교하며 문항 글은 어디에도 남기지 않는다."""
    if not ladder_bank:
        return list(ces), {"dropped": 0, "max": None, "checked": False}
    kept, worst = [], 0.0
    for ce in ces:
        j = max(_jacc(ce["q"], q["q"]) for q in ladder_bank)
        worst = max(worst, j)
        if j < OVERLAP:
            kept.append(ce)
    return kept, {"dropped": len(ces) - len(kept), "max": round(worst, 2), "checked": True}


def _ns(model: str, k: int, condition: str, week: str):
    return SimpleNamespace(bank="counterexample", weeks=week, condition=condition, k=k, model=model, effort="low", limit=0, out="", mock=False)


def validate(ces: list[dict], brief: str, llm, k: int = VALIDATE_K) -> list[dict]:
    """브리프를 본 풀이자가 k 회 모두 맞힌 반례만 남긴다. 못 맞히면 문항 결함으로 본다."""
    if not ces:
        return []
    run = solve_run(_ns(MID_MODEL, k, "brief", ces[0]["week"]), llm, bank=ces, context=brief, strict=True)
    ok = {r["id"] for r in run["results"] if r["acc"] == 1}
    return [ce for ce in ces if ce["id"] in ok]


# ---------------------------------------------------------------- ③ 풀기
def probe(ces: list[dict], notes_txt: str, llm, k: int = 3) -> list[dict]:
    """풀이자가 노트만 보고 반례를 푼 결과. trap_rate = 함정 보기를 고른 비율."""
    if not ces:
        return []
    run = solve_run(_ns(WEAK_MODEL, k, "notes", ces[0]["week"]), llm, patched=bool(notes_txt), bank=ces, context=notes_txt, strict=True)
    by = {r["id"]: r for r in run["results"]}
    return [{"id": ce["id"], "entry_id": ce["entry_id"], "acc": by[ce["id"]]["acc"],
             "trap_rate": sum(1 for a in by[ce["id"]]["attempts"] if a["pred"] == ce["trap"]) / k} for ce in ces]


# ---------------------------------------------------------------- ④ 고치기
# 고쳐 쓴 규칙이 항목 제약을 어겼을 때 다시 쓰라고 알려 주는 말
_WHY_TEXT = {"too_long": "문장이 3개를 넘었습니다. 3문장 이하로 줄여야 합니다(한 문장에 여러 내용을 담아도 됩니다)",
             "option_ref": "보기의 번호나 위치를 가리켰습니다", "item_ref": "문제 번호를 가리켰습니다", "empty": "규칙이 비어 있습니다"}


def revise(entry: dict, ce: dict | None, brief: str, llm, feedback: dict | None = None) -> dict:
    """항목을 고쳐 쓴다. ce 가 None 이면 근거 문항 없이 브리프만 보고 고친다(대조군).
    feedback = {"rule": 앞서 낸 규칙, "why": [위반 사유]} 를 주면 그 사유를 알려 주고 다시 쓰게 한다."""
    head = f"[노트 항목]\n({entry['concept']}) {entry['rule']}\n\n"
    if ce is not None:
        others = [o for i, o in enumerate(ce["options"]) if i not in (ce["answer"], ce["trap"])]
        head += ("[이 항목만 믿고 풀면 틀리는 반례 문제]\n"
                 f"문제: {ce['q']}\n보기: {' / '.join(ce['options'])}\n옳은 보기의 내용: {ce['options'][ce['answer']]}\n"
                 f"이 항목의 규칙만 믿으면 고르게 되는 보기: {ce['options'][ce['trap']]}\n나머지 보기: {' / '.join(others)}\n"
                 "노트만 본 학생은 이 문제를 틀렸습니다.\n\n")
        ask = "위 반례에서도 틀리지 않도록 이 노트 항목을 고쳐 쓰세요."
    else:
        ask = "이 노트 항목을 브리프에 비추어 더 정확하고 일반적으로 고쳐 쓰세요."
    if feedback:
        ask += (f"\n\n[앞서 낸 고친 규칙은 버려졌습니다]\n{feedback['rule']}\n버려진 이유: "
                + "; ".join(_WHY_TEXT.get(w, w) for w in feedback["why"]) + ".\n같은 뜻을 지키되 이 제약을 지켜 다시 쓰세요.")
    obj = _json(llm.ask(STRONG_MODEL, REVISE_SYSTEM, head + f"[강의 브리프]\n{brief}\n\n{ask} JSON 으로만 답합니다.", effort="high", max_tokens=3000,
                        mock_hint={"kind": "revise", "entry_id": entry["id"]})) or {}
    action = obj.get("action")
    rule = str(obj.get("rule") or "").strip()
    if action == "delete":
        return {"action": "delete", "rule": None}
    if action == "rewrite" and rule:
        return {"action": "rewrite", "rule": rule}
    return {"action": "keep", "rule": None}


def _revise_and_apply(notes: dict, entry_id: str, ce: dict | None, brief: str, llm, origin: str, round_no: int, acc: dict) -> bool:
    """항목 하나를 고쳐 쓰고 노트에 반영한다. 고친 규칙이 제약을 어기면 사유를 알려 주고 한 번만 다시 쓰게 한다. 바뀌었으면 True."""
    entry = _entry(notes, entry_id)
    out = revise(entry, ce, brief, llm)
    why = check_rule(out["rule"]) if out["action"] == "rewrite" else []
    if why:
        acc["retries"] += 1
        out = revise(entry, ce, brief, llm, feedback={"rule": out["rule"], "why": why})
    return _apply(notes, entry_id, out, origin, round_no, acc)


def _apply(notes: dict, entry_id: str, out: dict, origin: str, round_no: int, acc: dict) -> bool:
    """고쳐 쓰기 결과를 노트에 반영한다. 항목이 바뀌었으면 True."""
    if out["action"] == "delete":
        delete_entry(notes, entry_id, round_no)
        acc["deleted"].append(entry_id)
        if entry_id in acc["revised"]:
            acc["revised"].remove(entry_id)
        return False
    if out["action"] == "rewrite":
        why = check_rule(out["rule"])
        if why:      # 다시 쓰게 했는데도 제약을 어긴 고쳐 쓰기는 버리고 원래 항목을 둔다
            acc["rejected_rewrites"] += 1
            acc["rejected_reasons"].append({"entry_id": entry_id, "why": why})
            return False
        revise_entry(notes, entry_id, out["rule"], origin, round_no)
        if entry_id not in acc["revised"]:
            acc["revised"].append(entry_id)
        return True
    return False


def treat_ce(notes: dict, new_ids: list[str], brief: str, llm, public_bank: list[dict], ladder_bank: list[dict],
             week: str, round_no: int = 0, passes: int = CE_PASSES) -> dict:
    """이번 라운드에 생긴 항목(new_ids)에 반례 처치를 한다. 노트를 그 자리에서 고친다."""
    acc = {"generated": 0, "passed": 0, "overlap": {"dropped": 0, "max": None, "checked": bool(ladder_bank)},
           "trap_rate": [], "retest_acc": [], "revise_calls": 0, "retries": 0, "revised": [], "deleted": [], "rejected_rewrites": 0,
           "rejected_reasons": [], "dropped": [], "ces": []}      # dropped: 걸러진 반례의 항목과 사유(문항 글은 남기지 않는다)
    targets = list(new_ids)
    for p in range(1, passes + 1):
        targets = [i for i in targets if _entry(notes, i) is not None]
        if not targets:
            break
        ces = []
        for eid in targets:
            acc["generated"] += 1
            ce = generate(_entry(notes, eid), brief, llm, week, f"ce-{eid}-{round_no}-{p}")
            why = ["parse"] if ce is None else mechanical_check(ce, brief, public_bank)
            if why:
                acc["dropped"].append({"entry_id": eid, "why": why})
            else:
                ces.append(ce)
        kept, ov = overlap_drop(ces, ladder_bank)
        acc["dropped"] += [{"entry_id": c["entry_id"], "why": ["overlap"]} for c in ces if c not in kept]
        acc["overlap"]["dropped"] += ov["dropped"]
        if ov["max"] is not None:
            acc["overlap"]["max"] = max(acc["overlap"]["max"] or 0.0, ov["max"])
        ces = validate(kept, brief, llm)
        acc["dropped"] += [{"entry_id": c["entry_id"], "why": ["validator"]} for c in kept if c not in ces]
        acc["passed"] += len(ces)
        acc["ces"] += ces
        if not ces:
            acc["trap_rate"].append(None)
            acc["retest_acc"].append(None)
            break
        rows = probe(ces, notes_text(notes), llm)
        acc["trap_rate"].append(round(sum(r["trap_rate"] for r in rows) / len(rows), 4))
        changed = []
        for ce, row in zip(ces, rows):
            if row["acc"] == 1 or _entry(notes, ce["entry_id"]) is None:
                continue
            acc["revise_calls"] += 1
            if _revise_and_apply(notes, ce["entry_id"], ce, brief, llm, "counterexample", round_no, acc):
                changed.append(ce)
        if changed:      # 점검 값: 고친 뒤 같은 반례를 다시 풀린다. 효과의 증거로 쓰지 않는다
            again = probe(changed, notes_text(notes), llm)
            acc["retest_acc"].append(round(sum(r["acc"] for r in again) / len(again), 4))
        else:
            acc["retest_acc"].append(None)
        targets = [ce["entry_id"] for ce in changed]
    return acc


def treat_rev(notes: dict, new_ids: list[str], budget: int, brief: str, llm, round_no: int = 0) -> dict:
    """대조군: 반례 없이 고쳐 쓰기만 budget 번 한다. 이번 라운드의 새 항목부터, 모자라면 이전 항목(최근 것부터)으로 넘어가고,
    그래도 남으면 처음부터 다시 돈다. 노트가 비어 예산을 못 쓰면 unspent 에 남긴다."""
    acc = {"revise_calls": 0, "retries": 0, "revised": [], "deleted": [], "rejected_rewrites": 0, "rejected_reasons": [], "budget": budget, "unspent": 0}
    ids = [i for i in new_ids if _entry(notes, i) is not None]
    ids += [e["id"] for e in reversed(notes["entries"]) if e["id"] not in ids]
    i = 0
    while acc["revise_calls"] < budget and ids:
        eid = ids[i % len(ids)]
        acc["revise_calls"] += 1
        _revise_and_apply(notes, eid, None, brief, llm, "revise", round_no, acc)
        if _entry(notes, eid) is None:
            ids.remove(eid)
        else:
            i += 1
    acc["unspent"] = budget - acc["revise_calls"]
    return acc
