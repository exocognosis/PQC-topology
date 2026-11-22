"""Property tests linking the Lean theorems (lean/TopoPQC.lean) to the code.

Each test checks, on random inputs, the statement of one Lean theorem against the
testbed scorer (tools/score.py) or the synthetic engine (synth/engine.py). Integer-valued
parameters keep the float arithmetic exact. Run with:  python3 -m pytest -q tests
"""
import collections
import json
import os
import sys

import numpy as np
from hypothesis import assume, given, settings
from hypothesis import strategies as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "synth"))
sys.path.insert(0, HERE)
import engine as E  # noqa: E402
import gen_lean_vectors  # noqa: E402
import score as S  # noqa: E402

INF = float("inf")
settings.register_profile("ci", max_examples=300, deadline=None)
settings.load_profile("ci")

tfix_s = st.integers(0, 5).map(float)
H_s = st.integers(0, 30).map(float)
L_s = st.integers(1, 30).map(float)
T_s = st.one_of(st.integers(0, 40).map(float), st.just(INF))

# negotiated configurations, as the scorer reads them from access logs
CFG = {"hybrid": ("TLSv1.3", "TLS_AES_256_GCM_SHA384", "X25519MLKEM768"),
       "classical": ("TLSv1.3", "TLS_AES_256_GCM_SHA384", "x25519"),
       "rsa": ("TLSv1.2", "AES256-GCM-SHA384", "-"),
       "broken": ("TLSv1.2", "DES-CBC3-SHA", "-")}


# --------------------------------------------------------------------------- vectors
def test_vectors_match_scorer():
    """Every vector proved in Lean (vec_*) holds for score.window."""
    for v in json.load(open(os.path.join(HERE, "vectors.json")))["vectors"]:
        assert S.window(v["tfix"], v["H"], v["L"], v["T"]) == v["W"], v["name"]


def test_lean_vectors_current():
    """The generated block in TopoPQC.lean matches vectors.json."""
    assert gen_lean_vectors.block() in open(gen_lean_vectors.LEAN).read()


# --------------------------------------------------------------------------- Lemma 1, 2
@given(tfix_s, H_s, L_s, T_s)
def test_lemma1_mosca(tfix, H, L, T):
    assume(T != INF and -H <= T - L)
    assert S.window(tfix, H, L, T) == max(0.0, L + tfix - T)


@given(H_s, L_s, T_s)
def test_lemma1_sunk(H, L, T):
    assume(T != INF)
    assert S.window(0.0, H, L, T) == max(0.0, min(H, L - T))


@given(tfix_s, H_s, L_s, T_s)
def test_lemma1_remediable(tfix, H, L, T):
    w = S.window(tfix, H, L, T)
    assert w - S.window(0.0, H, L, T) == min(tfix, w)


@given(tfix_s, H_s, L_s)
def test_lemma1_safe(tfix, H, L):
    assert S.window(tfix, H, L, INF) == 0.0


@given(tfix_s, H_s, L_s, T_s)
def test_W_eq_zero_iff(tfix, H, L, T):
    assume(T != INF)
    assert (S.window(tfix, H, L, T) == 0.0) == (tfix + H <= 0 or tfix + L <= T)


@given(tfix_s, H_s, L_s, T_s, T_s)
def test_lemma2_max_min(tfix, H, L, T1, T2):
    w1, w2 = S.window(tfix, H, L, T1), S.window(tfix, H, L, T2)
    assert S.window(tfix, H, L, max(T1, T2)) == min(w1, w2)
    assert S.window(tfix, H, L, min(T1, T2)) == max(w1, w2)


@given(tfix_s, tfix_s, H_s, H_s, L_s, L_s, T_s, T_s)
def test_Wb_mono(t1, t2, h1, h2, l1, l2, a, b):
    lo = (min(t1, t2), min(h1, h2), min(l1, l2), max(a, b))
    hi = (max(t1, t2), max(h1, h2), max(l1, l2), min(a, b))
    assert S.window(*lo) <= S.window(*hi)


# --------------------------------------------------------------------------- risk (score.py)
@st.composite
def estates(draw):
    """A small estate in the scorer's own input format: gt, obs, channels, data class."""
    k = draw(st.integers(1, 5))
    chans = [(f"s{i}", f"c{i}") for i in range(k)]
    cp = {"default": {"O": 0.1, "t_fix": 1.0, "H": 10.0}}
    obs = {}
    for ch in chans:
        cp[f"{ch[0]}->{ch[1]}"] = {"O": draw(st.sampled_from([0.0, 0.1, 0.5, 1.0])),
                                   "t_fix": draw(tfix_s), "H": draw(H_s)}
        n = draw(st.lists(st.sampled_from(list(CFG)), min_size=1, max_size=3))
        obs[ch] = collections.Counter(CFG[c] for c in n)
    dc = {"C": draw(st.sampled_from([0.0, 0.5, 1.0])), "L": draw(L_s)}
    samples = draw(st.lists(st.integers(0, 30).map(float), min_size=1, max_size=4))
    return {"channel_params": cp}, obs, chans, dc, samples


@given(estates(), st.data())
def test_prop1_dominance(est, data):
    gt, obs, chans, dc, samples = est
    sub = data.draw(st.lists(st.sampled_from(chans), unique=True))
    for reading in ("worst", "share"):
        a = S.risk_for(gt, obs, sub, dc, samples, reading=reading)[0]
        b = S.risk_for(gt, obs, chans, dc, samples, reading=reading)[0]
        assert a <= b + 1e-12


@given(estates(), st.integers(0, 3))
def test_prop2_monotone(est, bump):
    """Raising C, L, O, t_fix or H, or replacing hybrid sessions by classical ones,
    never lowers risk (prop2_monotone, prop7_monotone)."""
    gt, obs, chans, dc, samples = est
    gt2 = json.loads(json.dumps(gt))
    for p in gt2["channel_params"].values():
        p["O"] = min(1.0, p["O"] + 0.25 * bump)
        p["t_fix"] += bump
        p["H"] += bump
    obs2 = {ch: collections.Counter({(CFG["classical"] if c == CFG["hybrid"] else c): n
                                     for c, n in cnt.items()}) for ch, cnt in obs.items()}
    dc2 = {"C": min(1.0, dc["C"] + 0.25 * bump), "L": dc["L"] + bump}
    for reading in ("worst", "share"):
        a = S.risk_for(gt, obs, chans, dc, samples, reading=reading)[0]
        b = S.risk_for(gt2, obs2, chans, dc2, samples, reading=reading)[0]
        assert a <= b + 1e-12


@given(estates())
def test_prop3_zero_iff(est):
    gt, obs, chans, dc, samples = est
    R = S.risk_for(gt, obs, chans, dc, samples)[0]

    def channel_zero(ch):
        p = gt["channel_params"][f"{ch[0]}->{ch[1]}"]
        return p["O"] == 0 or all(
            S.window(p["t_fix"], p["H"], dc["L"], S.kex_break_time(*cfg, tq)) == 0
            for cfg in obs[ch] for tq in samples)
    assert (R == 0) == (dc["C"] == 0 or all(channel_zero(ch) for ch in chans))


# --------------------------------------------------------------------------- Proposition 7
@given(estates())
def test_prop7_le_worst(est):
    gt, obs, chans, dc, samples = est
    share = S.risk_for(gt, obs, chans, dc, samples, reading="share")[0]
    worst = S.risk_for(gt, obs, chans, dc, samples, reading="worst")[0]
    assert share <= worst + 1e-12


@given(tfix_s, H_s, L_s, st.integers(0, 30).map(float), st.sampled_from(list(CFG)), st.integers(1, 9))
def test_prop7_point_mass(tfix, H, L, tq, cfg, n):
    cnt = {CFG[cfg]: n}
    assert S.channel_window(cnt, tfix, H, L, tq, "share") == S.channel_window(cnt, tfix, H, L, tq, "worst")


@given(tfix_s, H_s, L_s, st.integers(0, 30).map(float), st.integers(1, 20), st.integers(0, 20))
def test_prop7_classical_share(tfix, H, L, tq, nc, nh):
    cnt = {CFG["classical"]: nc, CFG["hybrid"]: nh}
    q = nc / (nc + nh)
    got = S.channel_window(cnt, tfix, H, L, tq, "share")
    assert abs(got - q * S.window(tfix, H, L, tq)) < 1e-9


@given(tfix_s, H_s, L_s, st.integers(0, 30).map(float),
       st.dictionaries(st.sampled_from(list(CFG)), st.integers(1, 9), min_size=1))
def test_prop7_remediable(tfix, H, L, tq, mix):
    cnt = {CFG[k]: n for k, n in mix.items()}
    tot = sum(cnt.values())
    lhs = S.channel_window(cnt, tfix, H, L, tq, "share") - S.channel_window(cnt, 0.0, H, L, tq, "share")
    rhs = sum(n / tot * min(tfix, S.window(tfix, H, L, S.kex_break_time(*c, tq))) for c, n in cnt.items())
    assert abs(lhs - rhs) < 1e-9


# --------------------------------------------------------------------------- Proposition 4
@st.composite
def graphs(draw):
    n = draw(st.integers(1, 12))
    edges = draw(st.lists(st.tuples(st.integers(0, n - 1), st.integers(0, n - 1)), max_size=30))
    omega = draw(st.lists(st.sampled_from([0.0, 0.5, 1.0, 2.0, 3.5]), min_size=len(edges), max_size=len(edges)))
    return n, edges, omega


def recur(n, edges, omega, X):
    Y = [0.0] * n
    for j, (x, y) in enumerate(edges):
        Y[x] = max(Y[x], omega[j], X[y])
    return Y


@given(graphs())
def test_prop4_fixpoint_and_condensation(g):
    n, edges, omega = g
    X = E.propagate_brute(n, edges, omega)
    assert recur(n, edges, omega, X) == X                       # prop4_fixpoint
    assert E.propagate_condensation(n, edges, omega) == X       # prop4_condensation
    assert E.propagate_naive(n, edges, omega)[0] == X           # least fixpoint from 0


@given(graphs(), st.data())
def test_prop4_least(g, data):
    """Any pre-fixpoint F(Y) <= Y lies above X (prop4_least)."""
    n, edges, omega = g
    X = E.propagate_brute(n, edges, omega)
    Y = data.draw(st.lists(st.sampled_from([0.0, 1.0, 2.0, 3.5, 5.0]), min_size=n, max_size=n))
    Y = [max(y, x) if data.draw(st.booleans()) else y for y, x in zip(Y, X)]
    if all(a <= b for a, b in zip(recur(n, edges, omega, Y), Y)):
        assert all(x <= y for x, y in zip(X, Y))


@given(graphs())
def test_prop4_scc(g):
    n, edges, omega = g
    X = E.propagate_brute(n, edges, omega)
    adj = [[] for _ in range(n)]
    for x, y in edges:
        adj[x].append(y)
    comp, _ = E.tarjan_scc(n, adj)
    for u in range(n):
        for v in range(n):
            if comp[u] == comp[v]:
                assert X[u] == X[v]


# --------------------------------------------------------------------------- Proposition 6, Corollary 1
@given(st.lists(st.tuples(st.integers(0, 20), st.integers(1, 5)), min_size=1, max_size=5),
       st.integers(1, 25))
def test_prop6_layercake(dist, a):
    """E[(a - T)^+] = integral_0^a P[T < s] ds for a discrete T (exact, piecewise)."""
    ts = np.array([t for t, _ in dist], float)
    ps = np.array([w for _, w in dist], float)
    ps /= ps.sum()
    lhs = float(np.dot(ps, np.maximum(0.0, a - ts)))
    grid = np.sort(np.unique(np.concatenate([[0.0, float(a)], ts[(ts > 0) & (ts < a)]])))
    rhs = 0.0
    for lo, hi in zip(grid[:-1], grid[1:]):
        rhs += (hi - lo) * float(ps[ts < (lo + hi) / 2].sum())   # P[T < s] is constant inside
    assert abs(lhs - rhs) < 1e-9


@given(st.lists(st.integers(0, 20), min_size=1, max_size=4), st.lists(st.integers(0, 20), min_size=1, max_size=4),
       st.integers(1, 25))
def test_cor1_independent(tq, tpq, a):
    """Independent uniform-on-support T_Q, T_PQ: E[(a - max)^+] = integral F G (cor1_hybrid)."""
    tq, tpq = np.array(tq, float), np.array(tpq, float)
    lhs = float(np.mean([max(0.0, a - max(x, y)) for x in tq for y in tpq]))
    pts = np.sort(np.unique(np.concatenate([[0.0, float(a)], tq, tpq])))
    pts = pts[(pts >= 0) & (pts <= a)]
    rhs = sum((hi - lo) * float((tq < (lo + hi) / 2).mean() * (tpq < (lo + hi) / 2).mean())
              for lo, hi in zip(pts[:-1], pts[1:]))
    assert abs(lhs - rhs) < 1e-9
    upper = sum((hi - lo) * float(min((tq < (lo + hi) / 2).mean(), (tpq < (lo + hi) / 2).mean()))
                for lo, hi in zip(pts[:-1], pts[1:]))
    assert rhs <= upper + 1e-12                                    # cor1_upper


# --------------------------------------------------------------------------- Proposition 8
def test_prop8_counterexample():
    """prop8_values: windows 7 and sunk 5 on two channels give reductions 0, 0, 0, 2."""
    Em = np.array([[7.0], [7.0]])
    E0 = np.array([[5.0], [5.0]])
    w = np.array([1.0])
    vals = [E.fix_set_gain(Em, E0, 1.0, w, r) for r in ([], [0], [1], [0, 1])]
    assert vals == [0.0, 0.0, 0.0, 2.0]
