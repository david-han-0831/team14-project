"""사후 분해: 이미 머지된 라운드의 패치를, 나중에 만든 비공개 세트까지 써서 다시 잰다.

라운드 당시에는 비공개 세트가 없어 O·G 를 계산하지 못한 경우에 쓴다. 패치 이전 페이지(git 의 과거 시점)와
이후 페이지로 공개·비공개 세트를 같은 실행 안에서 네 번 푼다(같은 풀이자, 같은 날).

  python evolve/retro.py --round 1 --weeks week09 --before-ref 9b545c6
  python evolve/retro.py --round 1 --weeks week09 --before-ref 9b545c6 --k 3     # 문항당 3회 풀어 흔들림을 줄인다
  python evolve/retro.py ... --mock                                               # API 없이 형식 확인

before = --before-ref 시점의 weeks/<week>.html, after = --after-ref (기본: 지금 작업 트리의 페이지).
출력: evolve/reports/retro-round-NN.json (실험실 페이지가 "사후 분해"로 표시)

주의: 비공개 세트가 그 라운드 뒤에 만들어졌다면 엄밀한 사전 등록 측정이 아니다. 리포트의 note 에 남긴다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from types import SimpleNamespace

from common import LLM, REPORT_DIR, ROOT, WEAK_MODEL, jdump, load_bank, log, update_report_index
from solve import run as solve_run


def git_show(ref: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8").stdout


def rev(ref: str) -> str:
    return subprocess.run(["git", "rev-parse", "--short", ref], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def ns(weeks: str, bank: str, k: int, model: str, mock: bool):
    return SimpleNamespace(bank=bank, weeks=weeks, condition="page", k=k, model=model, effort="low", limit=0, out="", mock=mock)


def changed(before: dict, after: dict) -> dict:
    """문항별 정답률이 바뀐 것만: {id: [전, 후]}"""
    b = {r["id"]: r["acc"] for r in before["results"]}
    a = {r["id"]: r["acc"] for r in after["results"]}
    return {i: [b[i], a[i]] for i in b if i in a and b[i] != a[i]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", type=int, required=True, help="다시 재는 라운드 번호")
    ap.add_argument("--weeks", required=True)
    ap.add_argument("--before-ref", required=True, help="패치 이전 페이지가 있는 git 시점")
    ap.add_argument("--after-ref", default="", help="패치 이후 시점 (비우면 지금 작업 트리)")
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--model", default=WEAK_MODEL)
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()

    weeks = a.weeks.split(",")
    if not load_bank("heldout", weeks):
        raise SystemExit("대상 주차의 비공개 문항이 없습니다. 사후 분해는 비공개 세트가 있어야 합니다.")
    before_html = {w: git_show(a.before_ref, f"weeks/{w}.html") for w in weeks}
    after_html = {w: git_show(a.after_ref, f"weeks/{w}.html") for w in weeks} if a.after_ref else None
    for w in weeks:
        cur = after_html[w] if after_html else (ROOT / "weeks" / f"{w}.html").read_text(encoding="utf-8")
        if cur == before_html[w]:
            raise SystemExit(f"{w}: 전후 페이지가 같습니다. --before-ref 를 확인하세요.")

    llm = LLM(mock=a.mock)
    log(f"=== 사후 분해 round-{a.round:02d} · weeks={a.weeks} · before={a.before_ref} · k={a.k} · mock={a.mock}")
    log("[1/4] 공개 · 패치 이전 페이지")
    pub_b = solve_run(ns(a.weeks, "public", a.k, a.model, a.mock), llm, html_override=before_html)
    log("[2/4] 비공개 · 패치 이전 페이지")
    hid_b = solve_run(ns(a.weeks, "heldout", a.k, a.model, a.mock), llm, html_override=before_html)
    log("[3/4] 공개 · 패치 이후 페이지")
    pub_a = solve_run(ns(a.weeks, "public", a.k, a.model, a.mock), llm, html_override=after_html, patched=True)
    log("[4/4] 비공개 · 패치 이후 페이지")
    hid_a = solve_run(ns(a.weeks, "heldout", a.k, a.model, a.mock), llm, html_override=after_html, patched=True)

    d_pub = round(pub_a["summary"]["acc"] - pub_b["summary"]["acc"], 4)
    d_hid = round(hid_a["summary"]["acc"] - hid_b["summary"]["acc"], 4)
    O = round(d_pub - d_hid, 4)
    T = 0.0  # 네 번 모두 같은 호출 수
    G = round(d_pub - O - T, 4)
    nb_b, nb_a = hid_b["summary"].get("acc_nonbasic"), hid_a["summary"].get("acc_nonbasic")
    ci_b, ci_a = pub_b["summary"]["acc_ci95"], pub_a["summary"]["acc_ci95"]
    hci_b, hci_a = hid_b["summary"]["acc_ci95"], hid_a["summary"]["acc_ci95"]

    def overlap(x, y):
        return not (y[0] > x[1] or x[0] > y[1])

    orig = {}
    p = REPORT_DIR / f"round-{a.round:02d}.json"
    if p.exists():
        orig = json.loads(p.read_text(encoding="utf-8"))
    report = {
        "retro": True, "round": a.round, "date": dt.date.today().isoformat(), "weeks": weeks, "mock": a.mock, "model": a.model, "k": a.k,
        "before_ref": a.before_ref, "after_ref": a.after_ref or "작업 트리",
        # HEAD 같은 움직이는 이름은 나중에 뜻이 달라지므로 커밋 해시도 함께 남긴다
        "before_commit": rev(a.before_ref), "after_commit": rev(a.after_ref) if a.after_ref else None,
        "n_public": pub_b["summary"]["n"], "n_heldout": hid_b["summary"]["n"],
        "ci95": {"public_before": ci_b, "public_after": ci_a, "overlap": overlap(ci_b, ci_a),
                 "heldout_before": hci_b, "heldout_after": hci_a, "heldout_overlap": overlap(hci_b, hci_a)},
        "baseline": {"acc_public": pub_b["summary"]["acc"], "acc_heldout": hid_b["summary"]["acc"]},
        "after": {"acc_public": pub_a["summary"]["acc"], "acc_heldout": hid_a["summary"]["acc"]},
        "decomposition": {"delta_public": d_pub, "delta_heldout": d_hid, "O": O, "T": T, "G": G,
                          "note": "O = Δ공개 − Δ비공개. T 는 호출 수 동일이라 0. G = Δ공개 − O − T = Δ비공개."},
        "heldout_nonbasic": {"n": hid_b["summary"].get("n_nonbasic"), "acc_before": nb_b, "acc_after": nb_a,
                             "delta": round(nb_a - nb_b, 4) if (nb_a is not None and nb_b is not None) else None},
        "changed": {"public": changed(pub_b, pub_a), "heldout": changed(hid_b, hid_a)},
        "original_round": {"date": orig.get("date"), "acc_public_before": (orig.get("baseline") or {}).get("acc_public"),
                           "acc_public_after": (orig.get("after") or {}).get("acc_public")} if orig else None,
        "patches": [{"week": x.get("week"), "card_id": x.get("card_id"), "concept": x.get("concept"), "title": x.get("title")} for x in orig.get("patches", [])],
        "note": "사후 측정. 비공개 세트는 이 라운드 뒤에 만들어졌다(출제자는 브리프만 보고 패치된 페이지는 보지 않음). "
                "전후 네 번을 같은 실행에서 풀어 풀이자·날짜 차이를 없앴다. 표본이 작으니 신뢰구간과 함께 읽는다.",
        "usage": llm.usage.to_dict(),
    }
    out = REPORT_DIR / f"retro-round-{a.round:02d}.json"
    jdump(report, out)
    update_report_index()
    log(f"→ {out}")
    log(f"  공개 {report['baseline']['acc_public']} → {report['after']['acc_public']} (Δ {d_pub})  비공개 {report['baseline']['acc_heldout']} → {report['after']['acc_heldout']} (Δ {d_hid})")
    log(f"  O={O} T={T} G={G}  변별 문항 {nb_b} → {nb_a}  CI 공개 {ci_b}→{ci_a} 비공개 {hci_b}→{hci_a}  ${report['usage']['usd']}")


if __name__ == "__main__":
    main()
