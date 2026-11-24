"""전이 사다리: 향상을 세 단으로 재서 오버피팅을 두 종류로 나눈다 (설계 3.6, 3.7).

  1단 T1 기출 그대로 / 2단 T2 바꿔 쓴 기출(기출과 1:1 짝) / 3단 T3 같은 개념의 다른 측면
  Δk = (노트 있을 때 정답률) − (빈 노트 정답률)
  O_암기(O_mem) = Δ1 − Δ2    O_측면(O_facet) = Δ2 − Δ3    G = Δ3    Δ1 = O_mem + O_facet + G
보조 분석은 단마다 정규화 향상 g = Δ / (1 − 기준선) 으로 같은 식을 쓴다(이름 앞에 n).

이 모듈은 숫자만 다룬다. 모델을 부르지 않고 문항 글을 보지 않는다.
"""
from __future__ import annotations

import random

RUNGS = ("T1", "T2", "T3")
STAT_KEYS = ("d1", "d2", "d3", "O_mem", "O_facet", "G", "O", "O_facet-O_mem",
             "nd1", "nd2", "nd3", "nO_mem", "nO_facet", "nG", "nO", "nO_facet-nO_mem")
MIN_VALID = 0.9      # 정규화 통계가 정의되는 반복이 이 비율보다 적으면 구간을 내지 않는다


def item_acc(run: dict) -> dict[str, float]:
    """solve.run 결과 → {문항 id: 정답률}"""
    return {r["id"]: r["acc"] for r in run["results"]}


def rung_table(public_bank: list[dict], ladder_bank: list[dict]) -> dict:
    """단별 문항 id 목록. 짝(2단 문항)이 없는 기출은 1단에서도 뺀다."""
    pair_of: dict[str, str] = {}
    for q in ladder_bank:
        if q.get("rung") == "T2" and q.get("pair"):
            pair_of.setdefault(q["pair"], q["id"])
    t1 = [q["id"] for q in public_bank if q["id"] in pair_of]
    return {"T1": t1, "T2": [pair_of[i] for i in t1],
            "T3": [q["id"] for q in ladder_bank if q.get("rung") == "T3"],
            "dropped_pairs": [q["id"] for q in public_bank if q["id"] not in pair_of]}


def arm_arrays(table: dict, base: dict[str, dict[str, float]], after: dict[str, dict[str, float]]) -> dict:
    """한 갈래의 단별 문항 정답률 배열(table 순서). base·after 는 {단: {id: 정답률}}"""
    return {r: {"base": [base[r][i] for i in table[r]], "after": [after[r][i] for i in table[r]]} for r in RUNGS}


def _sub(x, y):
    return None if x is None or y is None else x - y


def _from_means(b: list[float], a: list[float]) -> dict:
    d = [a[k] - b[k] for k in range(3)]
    n = [d[k] / (1 - b[k]) if b[k] < 1 - 1e-12 else None for k in range(3)]
    out = {"d1": d[0], "d2": d[1], "d3": d[2], "O_mem": d[0] - d[1], "O_facet": d[1] - d[2], "G": d[2], "O": d[0] - d[2],
           "nd1": n[0], "nd2": n[1], "nd3": n[2], "nO_mem": _sub(n[0], n[1]), "nO_facet": _sub(n[1], n[2]), "nG": n[2], "nO": _sub(n[0], n[2])}
    out["O_facet-O_mem"] = out["O_facet"] - out["O_mem"]
    out["nO_facet-nO_mem"] = _sub(out["nO_facet"], out["nO_mem"])
    return out


def _mean(v: list[float]) -> float:
    return sum(v) / len(v)


def decompose(arr: dict) -> dict:
    """한 갈래의 분해(점추정). 단별 기준선 정답률 base1~3 도 함께 준다."""
    b = [_mean(arr[r]["base"]) for r in RUNGS]
    a = [_mean(arr[r]["after"]) for r in RUNGS]
    return {**_from_means(b, a), "base1": b[0], "base2": b[1], "base3": b[2]}


def _interval(point, vals: list[float | None], n_boot: int) -> dict:
    ok = sorted(v for v in vals if v is not None)
    if point is None or len(ok) < MIN_VALID * n_boot:
        return {"point": None if point is None else round(point, 4), "lo": None, "hi": None}
    m = len(ok)
    return {"point": round(point, 4), "lo": round(ok[int(0.025 * m)], 4), "hi": round(ok[min(m - 1, int(0.975 * m))], 4)}


def joint_bootstrap(arrs: dict[str, dict], n_boot: int = 10000, seed: int = 14) -> dict:
    """문항 단위 부트스트랩. 반복마다 짝 번호 한 벌(T1·T2 공용)과 T3 번호 한 벌을 뽑아 모든 갈래·모든 통계에 같이 쓴다.
    반환: {갈래: {통계: {point, lo, hi}}, "diff": {"A|B": {통계: {...}}}}  (diff 는 A − B, 모든 순서쌍)"""
    arms = list(arrs)
    first = arrs[arms[0]]
    n_p, n_3 = len(first["T1"]["base"]), len(first["T3"]["base"])
    if n_p == 0 or n_3 == 0 or len(first["T2"]["base"]) != n_p:
        raise ValueError(f"단이 비었거나 1·2단 짝이 맞지 않습니다: T1={n_p} T2={len(first['T2']['base'])} T3={n_3}")
    rng = random.Random(seed)
    point = {a: _from_means([_mean(arrs[a][r]["base"]) for r in RUNGS], [_mean(arrs[a][r]["after"]) for r in RUNGS]) for a in arms}
    samples: dict[str, dict[str, list]] = {a: {k: [] for k in STAT_KEYS} for a in arms}
    for _ in range(n_boot):
        ip = [rng.randrange(n_p) for _ in range(n_p)]
        i3 = [rng.randrange(n_3) for _ in range(n_3)]
        for a in arms:
            x = arrs[a]
            b = [sum(x["T1"]["base"][i] for i in ip) / n_p, sum(x["T2"]["base"][i] for i in ip) / n_p, sum(x["T3"]["base"][i] for i in i3) / n_3]
            f = [sum(x["T1"]["after"][i] for i in ip) / n_p, sum(x["T2"]["after"][i] for i in ip) / n_p, sum(x["T3"]["after"][i] for i in i3) / n_3]
            st = _from_means(b, f)
            for k in STAT_KEYS:
                samples[a][k].append(st[k])
    out: dict = {a: {k: _interval(point[a][k], samples[a][k], n_boot) for k in STAT_KEYS} for a in arms}
    out["diff"] = {}
    for a in arms:
        for b_ in arms:
            if a == b_:
                continue
            out["diff"][f"{a}|{b_}"] = {k: _interval(_sub(point[a][k], point[b_][k]), [_sub(u, v) for u, v in zip(samples[a][k], samples[b_][k])], n_boot)
                                        for k in STAT_KEYS}
    return out


def _pos(x) -> bool:
    return x is not None and x > 0


def _sign(x) -> str:
    if x is None:
        return "계산 불가"
    return "작다" if x < 0 else ("크다" if x > 0 else "같다")


def judge(boot: dict, n_pairs: int, exp: str, h1_exp1: str | None = None) -> dict:
    """사전 등록한 조건 그대로 판정한다 (설계 3.7). 3라운드 뒤의 주 분석 기준.
    h1_exp1: 실험 2 를 판정할 때 실험 1 의 H1 결과. "확인"이 아니면 H3 를 판정하지 않는다."""
    h1 = _pos(boot["seen"]["O"]["lo"])
    if exp == "exp1":
        if not h1:
            h2 = "판정 안 함"
        elif _pos(boot["seen"]["O_facet-O_mem"]["lo"]) and _pos(boot["seen"]["nO_facet-nO_mem"]["point"]):
            h2 = "확인"
        else:
            h2 = "구분 못 함"
        d = boot["diff"]["concept|seen"]
        return {"H1": "확인" if h1 else "확인 못 함", "H2": h2,
                "H4": {"O": _sign(d["O"]["point"]), "d1": _sign(d["d1"]["point"])}}     # 방향만 (탐색적)
    if exp == "exp2":
        less_o = _pos(boot["diff"]["seen+rev|seen+ce"]["O"]["lo"])
        d1 = boot["diff"]["seen+ce|seen+rev"]["d1"]["point"]
        # Δ1 손실이 한 문항분(1/n)을 "넘지" 않으면 된다. 점추정은 4자리로 반올림돼 있으므로 그 오차만큼 여유를 둔다
        keeps = d1 is not None and d1 >= -1 / n_pairs - 5e-5
        if h1_exp1 != "확인":
            h3 = "판정 안 함"       # 도구가 오버피팅을 잡지 못했으면(실험 1 의 H1) 처치 효과를 판정하지 않는다
        else:
            h3 = "확인" if (less_o and keeps) else "확인 못 함"
        return {"H3": h3, "H1_재현": "재현" if h1 else "재현 안 됨", "H1_실험1": h1_exp1 or "없음"}
    raise ValueError(exp)
