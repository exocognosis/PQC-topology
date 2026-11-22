"""Risk engine for synthetic estates (paper §6, §6.6, §8, Appendix A).

The window is vectorized over realizations of T_Q; `check_against_scorer` verifies it
against the scalar `window` of tools/score.py, so both implement Definition 4.
"""
import os
import sys
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import score  # noqa: E402  (the testbed scorer; single source of the scalar model)

INF = float("inf")


# --------------------------------------------------------------------------- model
def window_vec(t_fix, H, L, T):
    """Definition 4 for an array of break times T (inf allowed)."""
    with np.errstate(invalid="ignore"):
        return np.maximum(0.0, t_fix - np.maximum(-H, T - L))


def check_against_scorer(rng, n=2000):
    """Vectorized window must equal score.window on random inputs, including T = inf."""
    for _ in range(n):
        t_fix, H, L = rng.uniform(0, 4), rng.uniform(0, 25), rng.uniform(0.5, 30)
        T = INF if rng.random() < 0.2 else rng.uniform(0, 40)
        a = float(window_vec(t_fix, H, L, np.array([T]))[0])
        b = score.window(t_fix, H, L, T)
        assert abs(a - b) < 1e-12, (t_fix, H, L, T, a, b)
    return n


@dataclass
class Channel:
    src: int            # server end (data moves src -> dst on the read path)
    dst: int
    O: float
    tfix: float
    H: float
    configs: list       # [(share, kind)], kind in {"classical", "hybrid", "broken"}


@dataclass
class DataClass:
    origin: int
    C: float
    L: float
    labeled: list = field(default_factory=list)   # channel indices
    inferred: list = field(default_factory=list)


def break_times(kind, t, tpq=INF):
    if kind == "classical":
        return t
    if kind == "hybrid":
        return np.maximum(t, tpq)
    return np.zeros_like(t)  # classically broken


def channel_exposure(ch, L, t, reading, tfix=None, tpq=INF):
    """O(e) * W_e (worst case) or O(e) * W-bar_e (share-weighted), per realization."""
    tf = ch.tfix if tfix is None else tfix
    rows = [(q, window_vec(tf, ch.H, L, break_times(k, t, tpq))) for q, k in ch.configs if q > 0]
    if not rows:
        return np.zeros_like(t)
    if reading == "share":
        W = sum(q * w for q, w in rows)
    else:
        W = np.max([w for _, w in rows], axis=0)
    return ch.O * W


def class_matrices(chans, dc, idx, t, reading, tpq=INF):
    """Exposure E and sunk exposure E0 for the channels idx of one data class (|idx| x m)."""
    if not idx:
        z = np.zeros((0, len(t)))
        return z, z
    E = np.array([channel_exposure(chans[i], dc.L, t, reading, tpq=tpq) for i in idx])
    E0 = np.array([channel_exposure(chans[i], dc.L, t, reading, tfix=0.0, tpq=tpq) for i in idx])
    return E, E0


def risk(E, C, w):
    """Definition 5: C * E_TQ[max_e O W_e], expectation as weighted mean over realizations."""
    return 0.0 if E.shape[0] == 0 else C * float(np.dot(w, E.max(axis=0)))


def fix_one_gains(E, E0, C, w):
    """Risk reduction from fixing each channel now (t_fix = 0), others unchanged."""
    k = E.shape[0]
    if k == 0:
        return np.zeros(0)
    s = np.sort(E, axis=0)
    top1 = s[-1]
    top2 = s[-2] if k > 1 else np.zeros_like(top1)
    others = np.where(E >= top1, top2, top1)          # max over the other rows (ties handled)
    after = np.maximum(others, E0)
    return C * ((top1 - after) @ w)


def fix_set_gain(E, E0, C, w, rows):
    if E.shape[0] == 0 or not rows:
        return 0.0
    E2 = E.copy()
    E2[list(rows)] = E0[list(rows)]
    return C * float(np.dot(w, E.max(axis=0) - E2.max(axis=0)))


# --------------------------------------------------------------------------- Appendix A
def tarjan_scc(n, adj):
    """Iterative Tarjan. Returns comp[] and SCCs in reverse topological order (sinks first)."""
    index, low, comp = [-1] * n, [0] * n, [-1] * n
    onstack, stack, sccs, counter = [False] * n, [], [], 0
    for root in range(n):
        if index[root] != -1:
            continue
        work = [(root, 0)]
        while work:
            v, i = work[-1]
            if i == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                onstack[v] = True
            if i < len(adj[v]):
                work[-1] = (v, i + 1)
                w_ = adj[v][i]
                if index[w_] == -1:
                    work.append((w_, 0))
                elif onstack[w_]:
                    low[v] = min(low[v], index[w_])
                continue
            work.pop()
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
            if low[v] == index[v]:
                scc = []
                while True:
                    x = stack.pop()
                    onstack[x] = False
                    comp[x] = len(sccs)
                    scc.append(x)
                    if x == v:
                        break
                sccs.append(scc)
    return comp, sccs


def propagate_condensation(n, edges, omega):
    """Appendix A: X(u) = max omega over channels whose tail is reachable from u."""
    adj = [[] for _ in range(n)]
    out = [[] for _ in range(n)]
    for j, (x, y) in enumerate(edges):
        adj[x].append(y)
        out[x].append(j)
    comp, sccs = tarjan_scc(n, adj)
    val = [0.0] * len(sccs)
    for i, scc in enumerate(sccs):           # sinks first
        v = 0.0
        for x in scc:
            for j in out[x]:
                v = max(v, omega[j])
                cy = comp[edges[j][1]]
                if cy != i:
                    v = max(v, val[cy])
        val[i] = v
    return [val[comp[u]] for u in range(n)]


def propagate_naive(n, edges, omega):
    """Kleene iteration of the recurrence of §6.4; returns values and rounds used."""
    X = [0.0] * n
    rounds = 0
    while True:
        rounds += 1
        changed = False
        for j, (x, y) in enumerate(edges):
            v = max(X[x], omega[j], X[y])
            if v > X[x]:
                X[x] = v
                changed = True
        if not changed:
            return X, rounds


def propagate_brute(n, edges, omega):
    adj = [[] for _ in range(n)]
    for x, y in edges:
        adj[x].append(y)
    X = []
    for u in range(n):
        seen, st = {u}, [u]
        while st:
            a = st.pop()
            for b in adj[a]:
                if b not in seen:
                    seen.add(b)
                    st.append(b)
        X.append(max([omega[j] for j, (x, _) in enumerate(edges) if x in seen] or [0.0]))
    return X


def reachable_channels(n, edges, origin):
    adj = [[] for _ in range(n)]
    for j, (x, y) in enumerate(edges):
        adj[x].append((y, j))
    seen, st = {origin}, [origin]
    while st:
        a = st.pop()
        for b, _ in adj[a]:
            if b not in seen:
                seen.add(b)
                st.append(b)
    return [j for j, (x, _) in enumerate(edges) if x in seen]
