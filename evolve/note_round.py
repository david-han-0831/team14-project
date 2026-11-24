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

import common
import counter
from common import LLM, MID_MODEL, REPORT_DIR, ROOT, RUN_DIR, STRONG_MODEL, WEAK_MODEL, brief_bundle, jdump, load_bank, log, update_report_index
from counter import treat_ce, treat_rev
from ladder import RUNGS, arm_arrays, decompose, item_acc, joint_bootstrap, judge, rung_table
from note_propose import propose_entries
from notes import add_entry, new_notes, notes_text
from solve import run as solve_run

EXPERIMENTS = {"exp1": ["seen", "concept"], "exp2": ["seen", "seen+ce", "seen+rev"]}
ROUNDS, K, MAX_NEW = 3, 3, 5
N_BOOT, SEED = 10000, 14
NOTES_DIR = ROOT / "evolve" / "notes"
# 확정 실행의 입력이 되는 경로. 여기에 커밋하지 않은 변경이 있으면 실제 확정 실행을 시작하지 않는다
FROZEN_PATHS = ("evolve", "content/briefs", "assets/data/quiz")
# 동결한 사다리 문항 집합의 해시(주차별). 문항은 비공개이고 해시만 공개한다. 실제 확정 실행은 읽은 문항의 해시가 이것과 다르면 시작하지 않는다
LADDER_SHA256: dict[str, str] = {
    "week09": "d959c127af33e841f2538d9eb2a0c3323f446c1f46eaea745a4092e8832b33cd",     # 2026-11-24 동결. 2단 18 + 3단 20
}


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
    """동결 정보: 지금 커밋과, 실험의 입력(코드·브리프·기출)에 커밋하지 않은 변경이 있는지."""
    return {"commit": _git("rev-parse", "--short", "HEAD") or "unknown", "dirty": bool(_git("status", "--porcelain", "--", *FROZEN_PATHS))}


def ladder_hash(items: list[dict]) -> str:
    """사다리 문항 집합의 해시. 문항의 내용 필드만 쓴다(읽을 때 붙는 week·bank 는 제외)."""
    keys = ("id", "rung", "pair", "type", "q", "options", "answer", "tol", "unit")
    canon = json.dumps(sorted(({k: q[k] for k in keys if k in q} for q in items), key=lambda q: q["id"]), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def run_params() -> dict:
    """결과를 바꿀 수 있는 설정. 리포트에 남기고, 이어 돌릴 때 처음과 같은지 대조한다."""
    return {"rounds": ROUNDS, "k": K, "max_new": MAX_NEW, "solver": WEAK_MODEL, "proposer": STRONG_MODEL, "validator": MID_MODEL,
            "n_boot": N_BOOT, "seed": SEED, "ce_per_entry": 1, "ce_passes": counter.CE_PASSES, "validate_k": counter.VALIDATE_K,
            "overlap": counter.OVERLAP, "backend": common.BACKEND, "cli_isolation": " ".join(common.CLI_ISOLATION)}


def report_path(exp: str, week: str, mock: bool) -> Path:
    return REPORT_DIR / f"ladder-{exp}-{week}{'-mock' if mock else ''}.json"


def guard_existing_report(exp: str, week: str, mock: bool, store: "Store") -> None:
    """실측 확정 리포트가 이미 있으면, 그것을 만든 실행을 이어 돌리는 경우가 아닌 한 시작하지 않는다(다시 돌려 마음에 드는 쪽만 남기는 일을 막는다)."""
    p = report_path(exp, week, mock)
    if mock or not p.exists():
        return
    meta = store.get("meta")
    if meta is None or meta.get("started") != json.loads(p.read_text(encoding="utf-8")).get("run_started"):
        raise SystemExit(f"이미 확정 실행 리포트가 있습니다: {p.name}. 확정 실행은 한 번만 합니다. 설정을 바꿔 다시 재려면 새 실험 번호로 설계에 기록하고 진행하세요.")


def _mean(v) -> float:
    v = list(v)
    return sum(v) / len(v) if v else 0.0


def _r4(d: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def run_experiment(exp: str, week: str, llm, store: Store, *, explore: bool, mock: bool, arms: list[str] | None = None,
                   public_bank: list[dict] | None = None, ladder_bank: list[dict] | None = None, freeze: dict | None = None,
                   h1_exp1: str | None = None) -> dict | None:
    """탐색 실행이면 None(기출 정답률은 로그와 저장 지점에만), 확정 실행이면 리포트 dict.
    h1_exp1: 실험 2 의 H3 판정에 쓰는 실험 1 의 H1 결과. 주지 않으면 실험 1 리포트에서 읽는다."""
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
        lhash = ladder_hash(ladder)
        if not mock:      # 실제 확정 실행의 동결 조건
            if freeze["commit"] == "unknown":
                raise SystemExit("커밋을 확인할 수 없습니다(git 실패). 확정 실행은 동결 커밋이 확인돼야 시작합니다.")
            if freeze["dirty"]:
                raise SystemExit(f"동결되지 않았습니다. {', '.join(FROZEN_PATHS)} 아래에 커밋하지 않은 변경이 있습니다. 커밋한 뒤 확정 실행을 하세요.")
            if week not in LADDER_SHA256:
                raise SystemExit(f"동결한 사다리 해시가 없습니다: {week}. note_round.LADDER_SHA256 에 해시를 적고 커밋한 뒤 실행하세요. (지금 읽은 문항의 해시: {lhash})")
            if LADDER_SHA256[week] != lhash:
                raise SystemExit(f"사다리 문항이 동결한 것과 다릅니다. 동결 {LADDER_SHA256[week][:12]}… / 지금 {lhash[:12]}… (LADDER_DIR 과 비공개 폴더의 사본을 확인하세요)")
        by_id = {q["id"]: q for q in ladder}
        rung_items = {"T1": public, "T2": [by_id[i] for i in table["T2"]], "T3": [by_id[i] for i in table["T3"]]}
    else:
        lhash = None
        rung_items = {"T1": public}      # 탐색 실행은 사다리를 읽지 않는다

    now = dt.datetime.now().isoformat(timespec="seconds")
    params = run_params()
    meta = store.get("meta")
    if meta is None:
        meta = {"exp": exp, "week": week, "commit": freeze["commit"], "explore": explore, "mock": mock, "started": now, "resumed": [],
                "ladder_sha256": lhash, "params": params}
    else:
        if meta["commit"] != freeze["commit"]:
            how = "새 --tag 로 다시 시작하세요." if explore else f"동결 커밋({meta['commit']})을 체크아웃해 이어 돌리세요."
            raise SystemExit(f"다른 커밋({meta['commit']})으로 만든 저장 지점입니다. 지금은 {freeze['commit']}. {how}")
        if meta["explore"] != explore:
            raise SystemExit("탐색 실행의 저장 지점과 확정 실행의 저장 지점은 섞어 쓸 수 없습니다. 저장 위치를 확인하세요.")
        if meta["mock"] != mock:
            raise SystemExit("가짜 풀이자(mock)로 만든 저장 지점과 실제 실행의 저장 지점은 섞어 쓸 수 없습니다. --tag 를 확인하세요.")
        if meta.get("ladder_sha256") != lhash:
            raise SystemExit("사다리 문항이 처음 시작할 때와 다릅니다. 같은 문항 집합으로 이어 돌려야 합니다.")
        if meta.get("params") != params:
            diff = sorted(k for k in params if (meta.get("params") or {}).get(k) != params[k])
            raise SystemExit(f"설정이 처음 시작할 때와 다릅니다: {diff}. 처음과 같은 설정으로 이어 돌려야 합니다.")
        meta["resumed"].append(now)
    store.put("meta", meta)

    def solve(key: str, items: list[dict], text: str) -> dict:
        got = store.get(key)
        if got is None:
            ns = SimpleNamespace(bank="notes", weeks=week, condition="notes", k=K, model=WEAK_MODEL, effort="low", limit=0, out="", mock=mock)
            log(f"[{key}] 풀이 {len(items)}문항 × {K}회")
            # strict: 빈 응답이면 여기서 멈춘다. 저장하지 않으므로 다시 실행하면 이 단계부터 한다
            got = solve_run(ns, llm, patched=bool(text), bank=items, context=text, strict=True)
            store.put(key, got)
        return got

    def unparsed(runs: dict) -> int:
        return sum(1 for run in runs.values() for r in run["results"] for a in r["attempts"] if a["pred"] is None)

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
    if exp == "exp2" and h1_exp1 is None:      # 실험 2 의 H3 는 실험 1 에서 H1 이 확인됐을 때만 판정한다 (설계 3.7)
        p1 = report_path("exp1", week, mock)
        h1_exp1 = (json.loads(p1.read_text(encoding="utf-8")).get("judge") or {}).get("H1") if p1.exists() else None
    return {
        "exp": exp, "week": week, "date": dt.date.today().isoformat(), "mock": mock, "k": K, "rounds": ROUNDS, "model": WEAK_MODEL,
        "n": {r: len(table[r]) for r in RUNGS}, "dropped_pairs": table["dropped_pairs"],
        "baseline": {r: round(_mean(first[r]["base"]), 4) for r in RUNGS},
        "arms": out_arms, "train": train, "boot": boot,
        "judge": judge(boot, len(table["T1"]), exp, h1_exp1) if set(arms) == set(EXPERIMENTS[exp]) else None,
        # 답을 읽지 못해 오답으로 채점된 시도 수(평가 단계만). 0 이 아니면 그 수치를 의심해야 한다
        "unparsed_attempts": {"baseline": unparsed(base), **{arm: unparsed(finals[arm]) for arm in arms}},
        "freeze": {"commit": freeze["commit"], "dirty": freeze["dirty"], "ladder_sha256": lhash, "params": params},
        "run_started": meta["started"], "resumed": meta["resumed"],
        "usage": llm.usage.to_dict(),      # 마지막으로 실행한 프로세스의 사용량(이어 돌렸으면 전체보다 작다)
    }


def store_root(exp: str, week: str, explore: bool, mock: bool, tag: str) -> Path:
    name = f"{exp}-{week}-{'explore' if explore else 'confirm'}" + ("-mock" if mock else "") + (f"-{tag}" if tag else "")
    return RUN_DIR / name


def publish(report: dict, store: Store) -> Path | None:
    """확정 실행의 리포트와 라운드별 노트를 사이트가 읽는 위치에 쓴다. mock 은 파일 이름에 표시해 실측을 덮어쓰지 않는다.
    일부 갈래만 돌린 실행은 게시하지 않는다(None). 다른 실행이 만든 실측 리포트는 덮어쓰지 않는다."""
    if set(report["arms"]) != set(EXPERIMENTS[report["exp"]]):
        return None
    out = report_path(report["exp"], report["week"], report["mock"])
    if not report["mock"] and out.exists() and json.loads(out.read_text(encoding="utf-8")).get("run_started") != report["run_started"]:
        raise SystemExit(f"이미 확정 실행 리포트가 있습니다: {out.name}. 다른 실행의 결과로 덮어쓰지 않습니다.")
    suffix = "-mock" if report["mock"] else ""
    for arm in report["arms"]:
        by_round = [store.get(f"{arm}/r{r}/notes")["notes"] for r in range(1, ROUNDS + 1)]
        jdump({"exp": report["exp"], "week": report["week"], "arm": arm, "mock": report["mock"], "final": by_round[-1], "by_round": by_round},
              NOTES_DIR / f"{report['exp']}{suffix}" / arm / f"{report['week']}.json")
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
    if not a.explore:
        guard_existing_report(a.exp, a.week, a.mock, store)
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
    log(f"→ {out}" if out else "일부 갈래만 돌린 실행이라 리포트를 게시하지 않았습니다(저장 지점에는 남아 있습니다).")
    for arm, x in report["arms"].items():
        d = x["decomp"]
        log(f"  {arm:9} Δ1={d['d1']} Δ2={d['d2']} Δ3={d['d3']} · O_암기={d['O_mem']} O_측면={d['O_facet']} G={d['G']}")
    log(f"  판정: {report['judge']}  · n={report['n']} · 커밋 {report['freeze']['commit']} · ${report['usage']['usd']}")


if __name__ == "__main__":
    main()
