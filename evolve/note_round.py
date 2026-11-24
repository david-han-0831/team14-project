"""노트 루프: 풀이자가 [학습 노트만] 보고 기출을 풀고, 제안자가 틀린 것을 보고 노트를 고쳐 쓴다 (설계 3.3).

  # 탐색 실행: 프롬프트를 다듬을 때. 기출만 푼다. 사다리(평가 전용)는 읽지도 풀지도 않는다. 리포트를 남기지 않는다
  python evolve/note_round.py --exp exp1 --week week09 --explore --tag try1
  # 확정 실행: 동결(커밋)한 뒤 한 번. 가설 판정은 이것으로만 한다. 끊기면 같은 명령을 다시 실행하면 이어서 돈다
  python evolve/note_round.py --exp exp1 --week week09
  python evolve/note_round.py --exp exp1 --week week09 --mock        # 가짜 풀이자로 형식 확인 (리포트에 mock 표시)

실험과 갈래:
  exp1  seen, concept                H1(오버피팅이 잡히는가) · H2(어떤 종류인가) · H4
  exp2  seen, seen+ce, seen+rev      H3(반례 처치가 줄이는가)
한 라운드: ① 풀이(문항당 3회) → ② 틀린 기출 뽑기 → ③ 제안(덧붙이기만) → ④ 고치기(exp2 의 두 갈래만)
사다리 평가는 기준선(빈 노트)과 3라운드 뒤, 두 번. 1라운드의 ① 은 기준선 결과를 그대로 쓴다.

출력(확정 실행): evolve/reports/ladder-<exp>-<week>.json, evolve/notes/<exp>/<갈래>/<week>.json
저장 지점: evolve/runs/<exp>-<week>-…/  (단계마다 파일 하나. 있으면 다시 호출하지 않는다)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from common import LLM, REPORT_DIR, ROOT, RUN_DIR, STRONG_MODEL, WEAK_MODEL, brief_bundle, jdump, load_bank, log, update_report_index
from counter import treat_ce, treat_rev
from ladder import RUNGS, arm_arrays, decompose, item_acc, joint_bootstrap, judge, rung_table
from note_propose import propose_entries
from notes import add_entry, new_notes, notes_text
from solve import run as solve_run

EXPERIMENTS = {"exp1": ["seen", "concept"], "exp2": ["seen", "seen+ce", "seen+rev"]}
ROUNDS, K, MAX_NEW = 3, 3, 5
N_BOOT, SEED = 10000, 14
NOTES_DIR = ROOT / "evolve" / "notes"


class Store:
    """저장 지점. 키는 'baseline/T1', 'seen/r2/solve' 같은 경로이고 파일은 root/<키>.json"""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str):
        p = self.path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put(self, key: str, obj) -> None:
        jdump(obj, self.path(key))


def _git(*a) -> str:
    try:
        return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def freeze_info() -> dict:
    """동결 정보: 지금 커밋과, evolve/ 아래에 커밋하지 않은 변경이 있는지."""
    return {"commit": _git("rev-parse", "--short", "HEAD") or "unknown", "dirty": bool(_git("status", "--porcelain", "--", "evolve"))}


def _mean(v) -> float:
    v = list(v)
    return sum(v) / len(v) if v else 0.0


def _r4(d: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def run_experiment(exp: str, week: str, llm, store: Store, *, explore: bool, mock: bool, arms: list[str] | None = None,
                   public_bank: list[dict] | None = None, ladder_bank: list[dict] | None = None, freeze: dict | None = None) -> dict | None:
    """탐색 실행이면 None(기출 정답률은 로그와 저장 지점에만), 확정 실행이면 리포트 dict."""
    if exp not in EXPERIMENTS:
        raise ValueError(exp)
    arms = arms or EXPERIMENTS[exp]
    if not set(arms) <= set(EXPERIMENTS[exp]):
        raise ValueError(f"{exp} 의 갈래가 아닙니다: {arms}")
    freeze = freeze or freeze_info()
    public = public_bank if public_bank is not None else load_bank("public", [week])
    if not public:
        raise SystemExit(f"기출 문항이 없습니다: {week}")

    table = None
    ladder: list[dict] = []
    if not explore:
        ladder = ladder_bank if ladder_bank is not None else load_bank("ladder", [week])
        table = rung_table(public, ladder) if ladder else None
        if not table or not table["T1"] or not table["T3"]:
            raise SystemExit("사다리 문항이 없습니다. 확정 실행은 비공개 사다리(LADDER_DIR 또는 ../team14-heldout/ladder)가 있어야 합니다. "
                             "사다리 없이 기출만 보려면 --explore 를 쓰세요.")
        if not mock and freeze["dirty"]:
            raise SystemExit("동결되지 않았습니다. evolve/ 아래에 커밋하지 않은 변경이 있습니다. 커밋한 뒤 확정 실행을 하세요.")
        by_id = {q["id"]: q for q in ladder}
        rung_items = {"T1": public, "T2": [by_id[i] for i in table["T2"]], "T3": [by_id[i] for i in table["T3"]]}
    else:
        rung_items = {"T1": public}      # 탐색 실행은 사다리를 읽지 않는다

    now = dt.datetime.now().isoformat(timespec="seconds")
    meta = store.get("meta")
    if meta is None:
        meta = {"exp": exp, "week": week, "commit": freeze["commit"], "explore": explore, "mock": mock, "started": now, "resumed": []}
    else:
        if meta["commit"] != freeze["commit"]:
            raise SystemExit(f"다른 커밋({meta['commit']})으로 만든 저장 지점입니다. 지금은 {freeze['commit']}. 새 --tag 로 다시 시작하세요.")
        if meta["explore"] != explore:
            raise SystemExit("탐색 실행의 저장 지점과 확정 실행의 저장 지점은 섞어 쓸 수 없습니다. 저장 위치를 확인하세요.")
        meta["resumed"].append(now)
    store.put("meta", meta)

    def solve(key: str, items: list[dict], text: str) -> dict:
        got = store.get(key)
        if got is None:
            ns = SimpleNamespace(bank="notes", weeks=week, condition="notes", k=K, model=WEAK_MODEL, effort="low", limit=0, out="", mock=mock)
            log(f"[{key}] 풀이 {len(items)}문항 × {K}회")
            got = solve_run(ns, llm, patched=bool(text), bank=items, context=text)
            store.put(key, got)
        return got

    base = {r: solve(f"baseline/{r}", rung_items[r], "") for r in rung_items}
    brief = brief_bundle(week)
    out_arms: dict[str, dict] = {}
    finals: dict[str, dict] = {}
    train: dict[str, dict] = {}
    for arm in arms:
        treated = arm in ("seen+ce", "seen+rev")
        notes = new_notes(week, arm)
        rejected_n = 0
        t1 = []
        treats: list[dict] = []
        counts = {"propose_calls": 0, "ce_generated": 0, "revise_calls": 0}
        for r in range(1, ROUNDS + 1):
            run_r = base["T1"] if r == 1 else solve(f"{arm}/r{r}/solve", public, notes_text(notes))
            t1.append(run_r["summary"]["acc"])
            done = store.get(f"{arm}/r{r}/notes")
            if done is not None:
                notes, rejected_n = done["notes"], done["rejected_n"]
                treats, counts = done.get("treats", treats), done.get("counts", counts)
                continue
            acc = item_acc(run_r)
            failed = [q for q in public if acc[q["id"]] < 1]       # 한 번이라도 틀린 기출
            prop = store.get(f"{arm}/r{r}/proposed")
            if prop is None and treated and r == 1:
                # 1라운드 제안은 seen 의 것을 그대로 받는다(같은 빈 노트, 같은 틀린 문항). 제안자 한 번의 우연이 갈래 차이로 보이지 않게
                prop = store.get("seen/r1/proposed")
                if prop is None:
                    raise SystemExit("seen 갈래를 먼저 실행하세요. 이 갈래는 seen 의 1라운드 제안에서 갈라집니다.")
                store.put(f"{arm}/r{r}/proposed", prop)
                for e in prop["added"]:
                    add_entry(notes, e["concept"], e["rule"], e["sources"], e["origin"]["from"], r)
            elif prop is None:
                log(f"[{arm}/r{r}] 틀린 기출 {len(failed)}문항 → 제안")
                prop = propose_entries(arm, week, failed, notes, llm, public, MAX_NEW, round_no=r)
                store.put(f"{arm}/r{r}/proposed", prop)
                counts["propose_calls"] += 1 if failed else 0
            else:      # 제안은 저장됐지만 노트 저장 전에 끊긴 경우: 다시 부르지 않고 같은 항목을 넣는다
                for e in prop["added"]:
                    add_entry(notes, e["concept"], e["rule"], e["sources"], e["origin"]["from"], r)
                counts["propose_calls"] += 1 if (failed and not (treated and r == 1)) else 0
            rejected_n += len(prop["rejected"])
            if treated:      # ④ 고치기: 이번 라운드에 생긴 항목만
                tr = store.get(f"{arm}/r{r}/treat")
                if tr is None:
                    new_ids = [e["id"] for e in prop["added"]]
                    if arm == "seen+ce":
                        out = treat_ce(notes, new_ids, brief, llm, public, ladder, week, round_no=r)
                    else:
                        ref = store.get(f"seen+ce/r{r}/treat")
                        if ref is None:
                            raise SystemExit("seen+ce 갈래를 먼저 실행하세요. seen+rev 는 seen+ce 가 쓴 고쳐 쓰기 횟수만큼만 고칩니다.")
                        out = treat_rev(notes, new_ids, ref["out"]["revise_calls"], brief, llm, round_no=r)
                    tr = {"out": out, "notes": notes}
                    store.put(f"{arm}/r{r}/treat", tr)
                else:
                    notes = tr["notes"]
                out = tr["out"]
                treats.append({k: v for k, v in out.items() if k != "ces"})
                counts["ce_generated"] += out.get("generated", 0)
                counts["revise_calls"] += out["revise_calls"]
                log(f"[{arm}/r{r}] 고치기: 출제 {out.get('generated', 0)} · 통과 {out.get('passed', 0)} · 고쳐 쓰기 호출 {out['revise_calls']} · 고침 {out['revised']} · 지움 {out['deleted']}")
            notes["round"] = r
            store.put(f"{arm}/r{r}/notes", {"notes": notes, "rejected_n": rejected_n, "treats": treats, "counts": counts})
            log(f"[{arm}/r{r}] 노트 항목 {len(notes['entries'])}개 (이번 라운드 +{len(prop['added'])}, 버림 {len(prop['rejected'])})")
        finals[arm] = {r: solve(f"{arm}/final/{r}", rung_items[r], notes_text(notes)) for r in rung_items}
        t1.append(finals[arm]["T1"]["summary"]["acc"])
        out_arms[arm] = {"t1_by_round": [round(x, 4) for x in t1], "notes_n": len(notes["entries"]), "rejected_n": rejected_n}
        if treated:
            out_arms[arm]["treat"] = treats
        train[arm] = counts
        log(f"[{arm}] 기출 정답률(라운드 0→{ROUNDS}): {out_arms[arm]['t1_by_round']} · 노트 {len(notes['entries'])}항목")

    if explore:
        return None

    base_acc = {r: item_acc(base[r]) for r in RUNGS}
    arrs = {arm: arm_arrays(table, base_acc, {r: item_acc(finals[arm][r]) for r in RUNGS}) for arm in arms}
    for arm in arms:
        d = decompose(arrs[arm])
        out_arms[arm]["final"] = {r: round(_mean(arrs[arm][r]["after"]), 4) for r in RUNGS}
        out_arms[arm]["decomp"] = _r4(d)
    boot = joint_bootstrap(arrs, N_BOOT, SEED)
    first = arrs[arms[0]]
    canon = json.dumps(sorted(ladder, key=lambda q: q["id"]), ensure_ascii=False, sort_keys=True)
    return {
        "exp": exp, "week": week, "date": dt.date.today().isoformat(), "mock": mock, "k": K, "rounds": ROUNDS, "model": WEAK_MODEL,
        "n": {r: len(table[r]) for r in RUNGS}, "dropped_pairs": table["dropped_pairs"],
        "baseline": {r: round(_mean(first[r]["base"]), 4) for r in RUNGS},
        "arms": out_arms, "train": train, "boot": boot,
        "judge": judge(boot, len(table["T1"]), exp) if set(arms) == set(EXPERIMENTS[exp]) else None,
        "freeze": {"commit": freeze["commit"], "dirty": freeze["dirty"], "ladder_sha256": hashlib.sha256(canon.encode("utf-8")).hexdigest(),
                   "params": {"rounds": ROUNDS, "k": K, "max_new": MAX_NEW, "solver": WEAK_MODEL, "proposer": STRONG_MODEL, "n_boot": N_BOOT, "seed": SEED}},
        "resumed": meta["resumed"], "usage": llm.usage.to_dict(),
    }


def store_root(exp: str, week: str, explore: bool, mock: bool, tag: str) -> Path:
    name = f"{exp}-{week}-{'explore' if explore else 'confirm'}" + ("-mock" if mock else "") + (f"-{tag}" if tag else "")
    return RUN_DIR / name


def publish(report: dict, store: Store) -> Path:
    """확정 실행의 리포트와 라운드별 노트를 사이트가 읽는 위치에 쓴다. mock 은 파일 이름에 표시해 실측을 덮어쓰지 않는다."""
    suffix = "-mock" if report["mock"] else ""
    for arm in report["arms"]:
        by_round = [store.get(f"{arm}/r{r}/notes")["notes"] for r in range(1, ROUNDS + 1)]
        jdump({"exp": report["exp"], "week": report["week"], "arm": arm, "mock": report["mock"], "final": by_round[-1], "by_round": by_round},
              NOTES_DIR / f"{report['exp']}{suffix}" / arm / f"{report['week']}.json")
    out = REPORT_DIR / f"ladder-{report['exp']}-{report['week']}{suffix}.json"
    jdump(report, out)
    update_report_index()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exp", required=True, choices=sorted(EXPERIMENTS))
    ap.add_argument("--week", required=True)
    ap.add_argument("--explore", action="store_true", help="탐색 실행: 기출만 푼다. 사다리를 쓰지 않고 리포트를 남기지 않는다")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--arms", default="", help="일부 갈래만 (예: seen,concept). 비우면 그 실험의 전체")
    ap.add_argument("--tag", default="", help="저장 위치 이름에 붙는 꼬리표. 탐색 실행을 여러 번 나눠 둘 때")
    a = ap.parse_args()

    store = Store(store_root(a.exp, a.week, a.explore, a.mock, a.tag))
    llm = LLM(mock=a.mock)
    log(f"=== 노트 루프 {a.exp} · {a.week} · {'탐색' if a.explore else '확정'} 실행 · mock={a.mock} · 저장 {store.root}")
    report = run_experiment(a.exp, a.week, llm, store, explore=a.explore, mock=a.mock, arms=a.arms.split(",") if a.arms else None)
    if report is None:
        for arm in (a.arms.split(",") if a.arms else EXPERIMENTS[a.exp]):
            last = store.get(f"{arm}/r{ROUNDS}/notes")
            log(f"--- {arm} 의 노트 ---\n" + (notes_text(last["notes"]) or "(비어 있음)"))
        log(f"탐색 실행 끝. 사다리는 풀지 않았습니다. ${llm.usage.usd:.2f}")
        return
    out = publish(report, store)
    log(f"→ {out}")
    for arm, x in report["arms"].items():
        d = x["decomp"]
        log(f"  {arm:9} Δ1={d['d1']} Δ2={d['d2']} Δ3={d['d3']} · O_암기={d['O_mem']} O_측면={d['O_facet']} G={d['G']}")
    log(f"  판정: {report['judge']}  · n={report['n']} · 커밋 {report['freeze']['commit']} · ${report['usage']['usd']}")


if __name__ == "__main__":
    main()
