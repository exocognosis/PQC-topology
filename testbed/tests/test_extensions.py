"""Tests for the uncertainty, flow, remediation and reporting extensions.

Where a statement is an instance of a Lean theorem it says so; the others are code
invariants of the new analyses, not proved results.
"""
import collections
import copy
import itertools
import json
import os
import sys

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("tools", "synth", "tests"):
    sys.path.insert(0, os.path.join(ROOT, sub))
import analysis as A  # noqa: E402
import engine as E  # noqa: E402
import run as R  # noqa: E402
import score as S  # noqa: E402
from test_properties import CFG, estates  # noqa: E402

INF = float("inf")
settings.register_profile("ext", max_examples=60, deadline=None)
settings.load_profile("ext")


def chain_gt(est):
    """Turn the estates() strategy output into a scorer ground truth with labeled flows."""
    gt, obs, chans, dc, samples = est
    g = copy.deepcopy(gt)
    g["scenarios"] = {"T_Q_uniform": [5, 20]}
    g["data_classes"] = {"d": {"origin": chans[0][0], "C": dc["C"], "L": dc["L"],
                               "labeled_flow": None}}
    return g, obs, chans


def gains_for(g, obs, chans, samples, reading, sets):
    """Fix gains over the channel set `chans` of one data class (unordered labeled flow)."""
    dc = g["data_classes"]["d"]
    base = S.risk_for(g, obs, chans, dc, samples, reading=reading)[0]
    return [base - S.risk_for(g, obs, chans, dc, samples, fixed_now=frozenset(s), reading=reading)[0]
            for s in sets]


# --------------------------------------------------------------------------- remediation
@given(estates())
def test_fixing_more_never_hurts(est):
    """g({e, f}) >= max(g(e), g(f)): risk is non-decreasing in t_fix (Lean: prop2_monotone)."""
    g, obs, chans = chain_gt(est)
    samples = est[4]
    for reading in ("worst", "share"):
        single = gains_for(g, obs, chans, samples, reading, [[c] for c in chans])
        for i, j in itertools.combinations(range(len(chans)), 2):
            pair = gains_for(g, obs, chans, samples, reading, [[chans[i], chans[j]]])[0]
            assert pair >= max(single[i], single[j]) - 1e-12
            assert pair >= -1e-12


@given(estates())
def test_share_gains_bounded_by_worst_risk(est):
    """Share-weighted risk <= worst-case risk (Lean: prop7_risk_le_worst), for any fix set."""
    g, obs, chans = chain_gt(est)
    dc, samples = g["data_classes"]["d"], est[4]
    for k in range(len(chans) + 1):
        fixed = frozenset(chans[:k])
        assert (S.risk_for(g, obs, chans, dc, samples, fixed_now=fixed, reading="share")[0]
                <= S.risk_for(g, obs, chans, dc, samples, fixed_now=fixed, reading="worst")[0] + 1e-12)


@given(estates())
def test_remove_fallback_action(est):
    """Offered only on channels that negotiate both hybrid and classical; same gain as migrate;
    cost = classical share x legacy weight (code invariant)."""
    gt, obs, chans, dc, samples = est
    rem = [{"channel": f"{s}->{c}", "risk_reduction": 0.5, "risk_reduction_share": 0.25} for s, c in chans]
    g = dict(gt, costs={"migrate": 1.0, "legacy_client_weight": 2.0})
    acts = A.remediation_actions(g, obs, chans, samples, S.risk_for,
                                 lambda cfg: S.kex_break_time(*cfg, 1.0) == INF, rem)
    for s, c in chans:
        cnt = obs[(s, c)]
        tot = sum(cnt.values())
        qc = sum(n for cfg, n in cnt.items() if S.kex_break_time(*cfg, 1.0) != INF) / tot
        fb = [a for a in acts if a["channel"] == f"{s}->{c}" and a["action"] == "remove_fallback"]
        mg = [a for a in acts if a["channel"] == f"{s}->{c}" and a["action"] == "migrate"]
        assert len(mg) == 1
        assert bool(fb) == (0 < qc < 1)
        if fb:
            assert fb[0]["gain_worst"] == mg[0]["gain_worst"]
            assert abs(fb[0]["cost"] - round(2.0 * qc, 3)) < 1e-9


# --------------------------------------------------------------------------- uncertainty
@given(estates())
@settings(max_examples=15)
def test_degenerate_uncertainty_collapses(est):
    """With every parameter fixed, each draw equals the point estimate: intervals collapse
    and the point first fix has P(top-1) = 1 (code invariant)."""
    gt, obs, chans, dc, samples = est
    g = dict(gt, scenarios={"T_Q_uniform": [5, 20]},
             data_classes={"d": {"origin": chans[0][0], "C": dc["C"], "L": dc["L"],
                                 "labeled_flow": [x for ch in chans for x in ch]}},
             uncertainty={"draws": 4, "seed": 1, "grid": 21, "k": 2, "default": {}})
    # labeled_flow pairs: (s0,c0),(c0,s1),(s1,c1)...; use edges that exist in obs only
    edges = sorted(obs)
    u = A.uncertainty_analysis(g, obs, edges, S.risk_for)
    for r, v in u["readings"].items():
        for c in v["channels"]:
            assert c["ci90"][0] == c["ci90"][1] == c["mean_gain"] == c["point_gain"]
        if v["point_first_fix"] is not None:
            top = next(c for c in v["channels"] if c["channel"] == v["point_first_fix"])
            assert top["p_top1"] == 1.0
            assert v["robust_first_fix"] == v["point_first_fix"]


def test_sample_gt_clips_and_is_reproducible():
    gt = json.load(open(os.path.join(ROOT, "groundtruth.json")))
    unc = {"default": {"O": {"dist": "lognormal", "sigma": 3.0}, "t_fix": {"dist": "lognormal", "sigma": 3.0},
                       "H": {"dist": "uniform", "lo": -5, "hi": 5}, "L": {"dist": "lognormal", "sigma": 3.0}}}
    import random
    a = A.sample_gt(gt, unc, random.Random(3))
    b = A.sample_gt(gt, unc, random.Random(3))
    assert a == b
    for p in a["channel_params"].values():
        if isinstance(p, dict):
            assert 0.0 <= p["O"] <= 1.0 and p["t_fix"] >= 0 and p["H"] >= 0
    assert all(dc["L"] > 0 for dc in a["data_classes"].values())


# --------------------------------------------------------------------------- priors and coverage
@given(estates(), st.integers(0, 30))
def test_point_prior_matches_point_scenario(est, v):
    gt, obs, chans, dc, samples = est
    grid = A.quantile_grid({"dist": "point", "value": v}, 11)
    assert abs(S.risk_for(gt, obs, chans, dc, grid)[0] - S.risk_for(gt, obs, chans, dc, [float(v)])[0]) < 1e-12


def test_prior_rows_share_le_worst_and_coverage_on_runs():
    for run in ("local-e2e", "hetzner-1", "local-ssh"):
        sj = json.load(open(os.path.join(ROOT, "results", run, "score.json")))
        for row in sj["prior_sensitivity"]:
            for v in row["hndl"].values():
                assert v["share"] <= v["worst"] + 1e-9           # Lean: prop7_risk_le_worst
        c = sj["coverage"]
        for k in ("classes_with_labels", "labeled_fraction_of_inferred", "channels_with_negotiation_data"):
            assert 0.0 <= c[k] <= 1.0
        assert c["classes_with_labels"] == 1.0 and c["unknown_channels"] == 0
        assert sj["readings"]["diverge"] == (sj["readings"]["worst_first_fix"] != sj["readings"]["share_first_fix"])


# --------------------------------------------------------------------------- engine: noisy-OR
@given(st.lists(st.tuples(st.sampled_from([0.0, 0.1, 0.5, 1.0]), st.integers(0, 9)), min_size=1, max_size=6))
def test_noisyor_dominates_max_and_same_zero_set(rows):
    O = np.array([o for o, _ in rows], float)
    W = np.array([[float(x)] for _, x in rows])
    noisy = E.noisyor_value(W, O)[0]
    worst = float((O[:, None] * W).max())
    assert noisy >= worst - 1e-12                                    # code invariant
    assert (noisy == 0) == (worst == 0)                              # same zero set as Lean: prop3_zero_iff


# --------------------------------------------------------------------------- engine: flows
def test_flow_modes_and_typed_dominance():
    """Typed inference contains the labeled flow, so it never under-reports (Lean:
    prop1_dominance); 'both' contains read and write closures; enabling write classes and
    replication leaves the read classes of the same seed unchanged."""
    t, w = R.prior_grid("uniform[5,20]", 41)
    for seed in range(6):
        base = R.gen_estate(np.random.default_rng(seed), n=60)
        N, edges, chans, classes = R.gen_estate(np.random.default_rng(seed), n=60, p_write=0.4, p_repl=0.0,
                                                flow_seed=100 + seed)
        reads = [dc for dc in classes if dc.kind == "read"]
        assert [(d.origin, d.labeled) for d in reads] == [(d.origin, d.labeled) for d in base[3]]
        N, edges, chans, classes = R.gen_estate(np.random.default_rng(seed), n=60, p_write=0.4, p_repl=0.3,
                                                flow_seed=100 + seed)
        for dc in classes:
            assert set(dc.labeled) <= set(dc.inferred)
            Rl = E.risk(E.class_matrices(chans, dc, dc.labeled, t, "worst")[0], dc.C, w)
            Ri = E.risk(E.class_matrices(chans, dc, dc.inferred, t, "worst")[0], dc.C, w)
            assert Ri >= Rl - 1e-12
            both = set(E.reachable_channels(N, edges, dc.origin, "both"))
            assert set(E.reachable_channels(N, edges, dc.origin, "read")) <= both
            assert set(E.reachable_channels(N, edges, dc.origin, "write")) <= both


# --------------------------------------------------------------------------- local search
@given(st.integers(0, 10_000))
@settings(max_examples=12)
def test_local_search_improves_and_is_bounded(seed):
    rng = np.random.default_rng(seed)
    N, edges, chans, classes = R.gen_estate(rng, n=12, layers=4, out_deg=2, p_back=0.1)
    t, w = R.prior_grid("uniform[5,20]", 41)
    parts = []
    for dc in classes:
        if dc.labeled:
            Em, E0 = E.class_matrices(chans, dc, dc.labeled, t, "worst")
            parts.append((dc.labeled, Em, E0, dc.C))

    def gain(Sset):
        Sset, tot = set(Sset), 0.0
        for idx, Em, E0, C in parts:
            tot += E.fix_set_gain(Em, E0, C, w, [r for r, j in enumerate(idx) if j in Sset])
        return tot
    n, k = len(chans), 2
    if n < k:
        return
    start = R._grouped_fn(gain, n, k, np.zeros(n), [])
    improved = R._local_search(gain, n, start)
    opt = max(gain(list(s)) for s in itertools.combinations(range(n), k))
    assert len(set(improved)) == k
    assert gain(start) - 1e-12 <= gain(improved) <= opt + 1e-12


def test_flow_modes_exact_sets():
    """Tiny graph: 0 calls 1, 9 calls 1, 1 calls 2 (read-path channels 1->0, 1->9, 2->1).
    Read data from 2 reaches 1, then 0 and 9; write data from 0 reaches 1, then 2, but
    never uses 1->9, because 9 does not hold it."""
    edges = [(1, 0), (1, 9), (2, 1)]
    assert sorted(E.reachable_channels(10, edges, 2, "read")) == [0, 1, 2]
    assert sorted(E.reachable_channels(10, edges, 0, "write")) == [0, 2]
    assert sorted(E.reachable_channels(10, edges, 0, "read")) == []
    assert sorted(E.reachable_channels(10, edges, 0, "both")) == [0, 1, 2]


def test_residual_unknown_risk_nonzero_path():
    """An unattributed caller on a holder's server adds R(labeled + U) - R(labeled)."""
    gt = {"channel_params": {"default": {"O": 0.2, "t_fix": 1.0, "H": 20.0}},
          "data_classes": {"d": {"origin": "a", "C": 1.0, "L": 15, "labeled_flow": ["a", "b"]}}}
    obs = {("a", "b"): collections.Counter({CFG["hybrid"]: 5}),
           ("a", "unknown:10.0.0.9"): collections.Counter({CFG["classical"]: 3})}
    edges = sorted(obs)
    samples = [5.0, 10.0, 15.0]
    cov = A.coverage(gt, obs, edges, samples, S.risk_for, S.reachable_channels)
    dc, lab, u = gt["data_classes"]["d"], [("a", "b")], [("a", "unknown:10.0.0.9")]
    expect = S.risk_for(gt, obs, lab + u, dc, samples)[0] - S.risk_for(gt, obs, lab, dc, samples)[0]
    assert cov["unknown_channels"] == 1
    assert cov["residual_unknown_risk"] > 0
    assert abs(cov["residual_unknown_risk"] - round(expect, 3)) < 1e-9
