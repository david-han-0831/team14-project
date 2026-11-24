"""Task 4: 전이 사다리 분해, 공동 부트스트랩, 가설 판정 (설계 3.6, 3.7)."""
from __future__ import annotations

import pytest

import ladder
from fakes import fake_items


def arr(b1, a1, b2, a2, b3, a3):
    return {"T1": {"base": b1, "after": a1}, "T2": {"base": b2, "after": a2}, "T3": {"base": b3, "after": a3}}


def s(point, lo, hi):
    return {"point": point, "lo": lo, "hi": hi}


def test_item_acc_reads_solve_results():
    run = {"results": [{"id": "a", "acc": 1 / 3}, {"id": "b", "acc": 1.0}]}
    assert ladder.item_acc(run) == {"a": 1 / 3, "b": 1.0}


def test_identity_holds():
    d = ladder.decompose(arr([0, .5, 1], [1, 1, 1], [0, .5, 1], [1, .5, 1], [0, 0, 1, 1], [0, .5, 1, 1]))
    assert d["d1"] == pytest.approx(d["O_mem"] + d["O_facet"] + d["G"])
    assert d["O"] == pytest.approx(d["d1"] - d["d3"]) == pytest.approx(d["O_mem"] + d["O_facet"])
    assert d["O_facet-O_mem"] == pytest.approx(d["O_facet"] - d["O_mem"])
    assert (d["base1"], d["base2"], d["base3"]) == (0.5, 0.5, 0.5)


def test_pure_memorisation_shows_up_as_O_mem():
    d = ladder.decompose(arr([0, 0], [1, 1], [0, 0], [0, 0], [0, 0], [0, 0]))
    assert (d["O_mem"], d["O_facet"], d["G"]) == (1.0, 0.0, 0.0)


def test_facet_narrowness_shows_up_as_O_facet():
    d = ladder.decompose(arr([0, 0], [1, 1], [0, 0], [1, 1], [0, 0], [0, 0]))
    assert (d["O_mem"], d["O_facet"], d["G"]) == (0.0, 1.0, 0.0)


def test_normalised_gain_divides_by_headroom():
    d = ladder.decompose(arr([.5, .5], [1, 1], [.5, .5], [.75, .75], [0, 0], [.25, .25]))
    assert (d["nd1"], d["nd2"], d["nd3"]) == (1.0, 0.5, 0.25)
    assert d["nO_mem"] == 0.5 and d["nO_facet"] == 0.25 and d["nG"] == 0.25


def test_normalised_gain_is_none_at_ceiling():                          # Review Focus 5
    d = ladder.decompose(arr([0, 0], [1, 1], [0, 0], [1, 1], [1, 1], [1, 1]))
    assert d["nd3"] is None and d["nO_facet"] is None and d["nG"] is None and d["nO_facet-nO_mem"] is None
    assert d["nd1"] == 1.0 and d["nO_mem"] == 0.0


def test_rung_table_drops_unpaired_public_items():
    pub = fake_items(3, "p")
    lad = [{**fake_items(1, "t2")[0], "rung": "T2", "pair": "p-1"}, {**fake_items(1, "t2b")[0], "rung": "T2", "pair": "p-3"},
           {**fake_items(1, "t3")[0], "rung": "T3"}]
    t = ladder.rung_table(pub, lad)
    assert t["T1"] == ["p-1", "p-3"] and t["T2"] == ["t2-1", "t2b-1"] and t["T3"] == ["t3-1"] and t["dropped_pairs"] == ["p-2"]


def test_arm_arrays_follow_table_order():
    table = {"T1": ["a", "b"], "T2": ["a2", "b2"], "T3": ["c"], "dropped_pairs": []}
    base = {"T1": {"b": .5, "a": 0}, "T2": {"a2": 0, "b2": .5}, "T3": {"c": 1}}
    after = {"T1": {"a": 1, "b": 1}, "T2": {"a2": 1, "b2": .5}, "T3": {"c": 1}}
    assert ladder.arm_arrays(table, base, after) == arr([0, .5], [1, 1], [0, .5], [1, .5], [1], [1])


def test_bootstrap_is_reproducible_and_joint():
    a = arr([0] * 6, [1, 1, 1, 0, 0, 0], [0] * 6, [1, 1, 1, 0, 0, 0], [0] * 5, [0] * 5)
    b1 = ladder.joint_bootstrap({"seen": a}, n_boot=500, seed=14)
    b2 = ladder.joint_bootstrap({"seen": a}, n_boot=500, seed=14)
    assert b1 == b2
    # T1 과 T2 가 문항마다 같으면 짝 추출에서는 O_mem 이 매번 정확히 0 이다 (따로 뽑으면 0 이 아니다)
    assert b1["seen"]["O_mem"]["lo"] == b1["seen"]["O_mem"]["hi"] == 0.0
    assert b1["seen"]["d1"]["point"] == 0.5 and b1["seen"]["d1"]["lo"] < 0.5 < b1["seen"]["d1"]["hi"]


def test_bootstrap_changes_with_seed():
    a = arr([0] * 6, [1, 1, 1, 0, 0, 0], [0] * 6, [1, 0, 1, 0, 0, 0], [0] * 5, [1, 0, 0, 0, 0])
    assert ladder.joint_bootstrap({"seen": a}, n_boot=200, seed=1) != ladder.joint_bootstrap({"seen": a}, n_boot=200, seed=2)


def test_arm_diff_uses_same_resample():
    a = arr([0] * 4, [1, 1, 0, 0], [0] * 4, [1, 1, 0, 0], [0] * 4, [0] * 4)
    boot = ladder.joint_bootstrap({"x": a, "y": a}, n_boot=300, seed=14)
    assert boot["diff"]["x|y"]["O"]["lo"] == boot["diff"]["x|y"]["O"]["hi"] == 0.0
    assert set(boot["diff"]) == {"x|y", "y|x"}


def test_bootstrap_interval_is_none_when_ceiling_resamples_dominate():
    # 3단 기준선이 전부 1 → 정규화 통계는 모든 반복에서 정의되지 않는다
    a = arr([0, 0], [1, 1], [0, 0], [1, 1], [1, 1], [1, 1])
    boot = ladder.joint_bootstrap({"seen": a}, n_boot=100, seed=14)
    assert boot["seen"]["nd3"] == {"point": None, "lo": None, "hi": None}
    assert boot["seen"]["d3"]["point"] == 0.0


def test_bootstrap_rejects_empty_rung():
    with pytest.raises(ValueError):
        ladder.joint_bootstrap({"seen": arr([0], [1], [0], [1], [], [])}, n_boot=10)


def test_judge_exp1_rules():
    boot = {"seen": {"O": s(.3, .1, .5), "O_facet-O_mem": s(.2, -.05, .4), "nO_facet-nO_mem": s(.2, 0, .4)},
            "diff": {"concept|seen": {"O": s(-.1, -.3, .1), "d1": s(-.05, -.2, .1)}}}
    j = ladder.judge(boot, n_pairs=18, exp="exp1")
    assert j["H1"] == "확인" and j["H2"] == "구분 못 함" and j["H4"] == {"O": "작다", "d1": "작다"}
    boot["seen"]["O_facet-O_mem"] = s(.2, .01, .4)
    assert ladder.judge(boot, 18, "exp1")["H2"] == "확인"
    boot["seen"]["nO_facet-nO_mem"] = s(-.1, -.3, .1)          # 보조 분석이 반대 방향
    assert ladder.judge(boot, 18, "exp1")["H2"] == "구분 못 함"
    boot["seen"]["nO_facet-nO_mem"] = s(None, None, None)      # 보조 분석을 계산할 수 없음
    assert ladder.judge(boot, 18, "exp1")["H2"] == "구분 못 함"
    boot["seen"]["O"] = s(.1, -.02, .3)
    j = ladder.judge(boot, 18, "exp1")
    assert j["H1"] == "확인 못 함" and j["H2"] == "판정 안 함"


def test_judge_exp2_needs_both_conditions():
    boot = {"seen": {"O": s(.3, .1, .5)},
            "diff": {"seen+rev|seen+ce": {"O": s(.15, .02, .3)}, "seen+ce|seen+rev": {"d1": s(-.10, -.2, 0)}}}
    assert ladder.judge(boot, 18, "exp2", h1_exp1="확인") == {"H3": "확인 못 함", "H1_재현": "재현", "H1_실험1": "확인"}          # Δ1 손실이 1/18 보다 크다
    boot["diff"]["seen+ce|seen+rev"]["d1"] = s(-.05, -.2, .1)
    assert ladder.judge(boot, 18, "exp2", h1_exp1="확인")["H3"] == "확인"
    boot["diff"]["seen+rev|seen+ce"]["O"] = s(.15, -.02, .3)
    assert ladder.judge(boot, 18, "exp2", h1_exp1="확인")["H3"] == "확인 못 함"
    boot["seen"]["O"] = s(.1, -.1, .3)
    assert ladder.judge(boot, 18, "exp2", h1_exp1="확인")["H1_재현"] == "재현 안 됨"
