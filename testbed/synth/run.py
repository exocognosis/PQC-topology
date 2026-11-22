"""Synthetic-topology experiments for §13 of the paper.

  python3 synth/run.py [--only NAME ...] [--quick]

Experiments (all seeded; results in results/synth/summary.json and report.md):
  validate   engine reproduces the testbed scores (Tables 6 and 7); T_Q grid check
  fixpoint   condensation (Appendix A) = naive fixpoint = brute-force reachability
  scaling    running time of Appendix A vs graph size; naive worst case
  inference  precision of inferred flows and risk overstatement vs forwarding and cycles
  stability  rank stability under parameter noise and alternative T_Q priors; readings
  greedy     greedy and grouped heuristic (§8.2) vs optimal fix sets
"""
import argparse
import itertools
import json
import math
import os
import sys
import time

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import engine as E  # noqa: E402
from engine import Channel, DataClass  # noqa: E402

OUT = os.path.join(ROOT, "results", "synth")
INF = float("inf")


# --------------------------------------------------------------------------- T_Q priors
def prior_grid(name, m=201):
    """Equal-weight quantile grid for a CRQC-arrival prior (shapes, not survey fits)."""
    u = (np.arange(m) + 0.5) / m
    if name == "uniform[5,20]":
        t = 5 + 15 * u
    elif name == "late uniform[10,30]":
        t = 10 + 20 * u
    elif name == "early 5+Exp(mean 4)":
        t = 5 - 4 * np.log(1 - u)
    elif name == "lognormal median 12":
        t = 12 * np.exp(0.4 * stats.norm.ppf(u))
    elif name == "point 10":
        t = np.full(m, 10.0)
    else:
        raise ValueError(name)
    return t, np.full(m, 1.0 / m)


PRIORS = ["uniform[5,20]", "late uniform[10,30]", "early 5+Exp(mean 4)", "lognormal median 12", "point 10"]


# --------------------------------------------------------------------------- generator
def gen_estate(rng, n=200, layers=5, out_deg=3, p_back=0.05, f_fwd=0.6,
               mix=(0.45, 0.35, 0.17, 0.03), edge_mix=(0.2, 0.2, 0.6, 0.0)):
    """Layered service graph with callbacks. Node 0 is the internet client.

    A call caller -> callee gives a read-path channel callee -> caller. Data classes
    originate at the deepest layer (and some middle nodes). The labeled flow of a class
    forwards along each outgoing channel of a node that holds it with probability f_fwd,
    so labeled is a subset of inferred by construction; f_fwd = 1 makes them equal.
    """
    sizes = [max(1, n // 40)]
    rest = n - sizes[0]
    sizes += [rest // (layers - 1) + (1 if i < rest % (layers - 1) else 0) for i in range(layers - 1)]
    layer_nodes, nxt = [], 1
    for s in sizes:
        layer_nodes.append(list(range(nxt, nxt + s)))
        nxt += s
    N = nxt
    layer_of = {v: i for i, ns in enumerate(layer_nodes) for v in ns}
    calls = set()
    for g in layer_nodes[0]:
        calls.add((0, g))
    for li in range(layers - 1):
        for v in layer_nodes[li]:
            for _ in range(out_deg):
                tgt_layer = li + 1 if (li + 2 >= layers or rng.random() < 0.8) else li + 2
                calls.add((v, int(rng.choice(layer_nodes[tgt_layer]))))
    for li in range(1, layers):
        for v in layer_nodes[li]:
            if rng.random() < p_back:  # callback into an upper layer: creates cycles
                calls.add((v, int(rng.choice(layer_nodes[rng.integers(0, li)]))))
    edges = sorted((callee, caller) for caller, callee in calls)
    chans = []
    kinds = ["classical", "hybrid", "mixed", "broken"]
    for x, y in edges:
        edge = (y == 0)
        if edge:
            O, tfix = 1.0, 1.0
        elif layer_of.get(x) == 0 or layer_of.get(y) == 0:
            O, tfix = 0.5, float(rng.integers(1, 4))
        else:
            O, tfix = float(rng.choice([0.1, 0.2, 0.3])), float(rng.integers(1, 4))
        kind = kinds[rng.choice(4, p=edge_mix if edge else mix)]
        if kind == "mixed":
            q = float(rng.uniform(0.05, 0.5))
            cfg = [(q, "classical"), (1 - q, "hybrid")]
        else:
            cfg = [(1.0, kind)]
        chans.append(Channel(x, y, O, tfix, float(rng.uniform(2, 20)), cfg))
    out = [[] for _ in range(N)]
    for j, (x, _) in enumerate(edges):
        out[x].append(j)
    classes = []
    origins = list(layer_nodes[-1]) + [v for li in range(1, layers - 1) for v in layer_nodes[li]
                                       if rng.random() < 0.1]
    for o in origins:
        dc = DataClass(o, float(rng.uniform(0.1, 1.0)), float(rng.choice([2, 5, 8, 15, 25])))
        holders, st, lab = {o}, [o], set()
        first = int(rng.choice(out[o])) if out[o] else None   # every class leaves its origin
        while st:
            a = st.pop()
            for j in out[a]:
                if rng.random() < f_fwd or j == first:
                    lab.add(j)
                    b = edges[j][1]
                    if b not in holders:
                        holders.add(b)
                        st.append(b)
        dc.labeled = sorted(lab)
        dc.inferred = E.reachable_channels(N, edges, o)
        assert set(dc.labeled) <= set(dc.inferred)
        classes.append(dc)
    return N, edges, chans, classes


def total_gains(chans, classes, t, w, reading, mode="labeled", tpq=INF):
    g = np.zeros(len(chans))
    for dc in classes:
        idx = getattr(dc, mode)
        Em, E0 = E.class_matrices(chans, dc, idx, t, reading, tpq)
        if idx:
            np.add.at(g, idx, E.fix_one_gains(Em, E0, dc.C, w))
    return g


def rank_metrics(a, b, k=5):
    """Top-1 agreement, top-k overlap, weighted tau over channels nonzero in either."""
    nz = (a > 1e-12) | (b > 1e-12)
    if nz.sum() == 0:
        return None
    ia, ib = np.argsort(-a, kind="stable"), np.argsort(-b, kind="stable")
    kk = min(k, int(nz.sum()))
    top1 = bool(ia[0] == ib[0])
    overlap = len(set(ia[:kk]) & set(ib[:kk])) / kk
    tau = stats.weightedtau(a[nz], b[nz]).statistic if nz.sum() > 1 else 1.0
    return top1, overlap, float(tau)


def q(xs, p):
    return float(np.percentile(xs, p)) if len(xs) else float("nan")


# --------------------------------------------------------------------------- experiments
def exp_validate(args):
    """Engine reproduces Tables 6 and 7 from the testbed's own logs."""
    import score as S
    rng = np.random.default_rng(1)
    n_win = E.check_against_scorer(rng)
    gt = json.load(open(os.path.join(ROOT, "groundtruth.json")))
    out = {"window_checks": n_win, "runs": {}}
    for run in ("hetzner-1", "local-e2e"):
        rd = os.path.join(ROOT, "results", run)
        obs = S.read_access_logs(rd, S.ip_map(gt, rd))
        ref = json.load(open(os.path.join(rd, "score.json")))
        names = sorted({h for ch in obs for h in ch})
        nid = {h: i for i, h in enumerate(names)}
        edges = sorted(obs)
        chans = []
        for (s, c) in edges:
            p = S.channel_params(gt, s, c)
            tot = sum(obs[(s, c)].values())
            cfg = []
            for (pr, ci, g), n in obs[(s, c)].items():
                T = S.kex_break_time(pr, ci, g, 1.2345)
                kind = "hybrid" if T == INF else ("broken" if T == 0 else "classical")
                cfg.append((n / tot, kind))
            chans.append(Channel(nid[s], nid[c], p["O"], p["t_fix"], p["H"], cfg))
        key = [lab for lab, _ in S.tq_samples(gt["scenarios"])][-1]
        t = np.array(S.tq_samples(gt["scenarios"])[-1][1])
        w = np.full(len(t), 1.0 / len(t))
        res, ok = {}, True
        classes = []
        for name, d in gt["data_classes"].items():
            f = d["labeled_flow"]
            lab = [edges.index((f[i], f[i + 1])) for i in range(len(f) - 1)]
            dc = DataClass(nid[d["origin"]], d["C"], d["L"], lab, [])
            classes.append(dc)
            for reading in ("worst", "share"):
                Em, E0 = E.class_matrices(chans, dc, lab, t, reading)
                R, R0 = E.risk(Em, dc.C, w), E.risk(E0, dc.C, w)
                r = ref["hndl"][name]["scenarios"][key]
                r = r if reading == "worst" else r["share"]
                good = abs(R - r["labeled"]) < 1e-3 and abs(R0 - r["labeled_sunk"]) < 1e-3
                ok &= good
                res[f"{name}/{reading}"] = {"engine": [round(R, 3), round(R0, 3)],
                                            "scorer": [r["labeled"], r["labeled_sunk"]], "match": good}
        for reading, col in (("worst", "risk_reduction"), ("share", "risk_reduction_share")):
            g = total_gains(chans, classes, t, w, reading)
            refg = {r["channel"]: r[col] for r in ref["remediation"]}
            for j, (s, c) in enumerate(edges):
                good = abs(g[j] - refg[f"{s}->{c}"]) < 1e-3
                ok &= good
            both = [edges.index(("gw", "client")), edges.index(("lb", "gw"))]
            bg = 0.0
            for dc in classes:
                Em, E0 = E.class_matrices(chans, dc, dc.labeled, t, reading)
                rows = [dc.labeled.index(j) for j in both if j in dc.labeled]
                bg += E.fix_set_gain(Em, E0, dc.C, w, rows)
            res[f"fix/{reading}"] = {"gw->client": round(g[edges.index(('gw', 'client'))], 3),
                                     "lb->gw": round(g[edges.index(('lb', 'gw'))], 3), "both": round(bg, 3)}
        # coarse midpoint grid used by the synthetic runs vs the scorer's 3001-point grid
        t2, w2 = prior_grid("uniform[5,20]", args.m)
        diffs = []
        for dc in classes:
            for reading in ("worst", "share"):
                a = E.risk(E.class_matrices(chans, dc, dc.labeled, t, reading)[0], dc.C, w)
                b = E.risk(E.class_matrices(chans, dc, dc.labeled, t2, reading)[0], dc.C, w2)
                diffs.append(abs(a - b))
        out["runs"][run] = {"all_match": bool(ok), "values": res, "grid_max_abs_diff": round(max(diffs), 4)}
    return out


def exp_fixpoint(args):
    rng = np.random.default_rng(2)
    n_inst, agree, max_rounds = (200 if args.quick else 1000), 0, 0
    for _ in range(n_inst):
        n = int(rng.integers(3, 30))
        m = int(rng.integers(n, 3 * n))
        edges = [(int(rng.integers(n)), int(rng.integers(n))) for _ in range(m)]
        edges = [(x, y) for x, y in edges if x != y]
        omega = [float(rng.choice([0, rng.uniform(0, 5)])) for _ in edges]
        a = E.propagate_condensation(n, edges, omega)
        b, r = E.propagate_naive(n, edges, omega)
        c = E.propagate_brute(n, edges, omega)
        agree += int(a == b == c)
        max_rounds = max(max_rounds, r)
    return {"instances": n_inst, "all_three_agree": agree, "max_naive_rounds": max_rounds}


def exp_scaling(args):
    rng = np.random.default_rng(3)
    sizes = [1000, 3000, 10000, 30000] + ([] if args.quick else [100000])
    rows = []
    for n in sizes:
        m = 3 * n
        edges = [(int(rng.integers(n)), int(rng.integers(n))) for _ in range(m)]
        omega = list(rng.uniform(0, 5, size=m))
        reps, ts = 3, []
        for _ in range(reps):
            t0 = time.perf_counter()
            E.propagate_condensation(n, edges, omega)
            ts.append(time.perf_counter() - t0)
        rows.append({"nodes": n, "channels": m, "seconds": round(min(ts), 4)})
    x = np.log([r["nodes"] + r["channels"] for r in rows])
    y = np.log([r["seconds"] for r in rows])
    slope = float(np.polyfit(x, y, 1)[0])
    chain = []
    for n in [250, 500, 1000, 2000]:
        edges = [(i, i + 1) for i in range(n - 1)]          # adversarial order for naive iteration
        omega = [0.0] * (n - 2) + [1.0]
        t0 = time.perf_counter()
        _, r = E.propagate_naive(n, edges, omega)
        tn = time.perf_counter() - t0
        t0 = time.perf_counter()
        E.propagate_condensation(n, edges, omega)
        tc = time.perf_counter() - t0
        chain.append({"nodes": n, "naive_rounds": r, "naive_seconds": round(tn, 4),
                      "condensation_seconds": round(tc, 5)})
    return {"random_graphs": rows, "loglog_slope": round(slope, 3), "chain_worst_case": chain}


def exp_inference(args):
    seeds = 10 if args.quick else 40
    t, w = prior_grid("uniform[5,20]", args.m)
    grid = []
    for p_back in (0.0, 0.05, 0.2):
        for f in (0.25, 0.5, 0.75, 1.0):
            prec, ratio, zero_lab, n_cls = [], [], 0, 0
            for s in range(seeds):
                rng = np.random.default_rng(1000 + s)
                N, edges, chans, classes = gen_estate(rng, n=args.n, p_back=p_back, f_fwd=f)
                for dc in classes:
                    n_cls += 1
                    prec.append(len(dc.labeled) / len(dc.inferred) if dc.inferred else 1.0)
                    Rl = E.risk(E.class_matrices(chans, dc, dc.labeled, t, "worst")[0], dc.C, w)
                    Ri = E.risk(E.class_matrices(chans, dc, dc.inferred, t, "worst")[0], dc.C, w)
                    if Rl <= 1e-12:
                        zero_lab += 1
                    else:
                        assert Ri >= Rl * (1 - 1e-9), (Ri, Rl)   # inference never under-reports (§6.4)
                        ratio.append(Ri / Rl)
            grid.append({"p_back": p_back, "f_fwd": f, "classes": n_cls,
                         "precision_median": round(q(prec, 50), 3), "precision_iqr": [round(q(prec, 25), 3), round(q(prec, 75), 3)],
                         "risk_ratio_median": round(q(ratio, 50), 3), "risk_ratio_p90": round(q(ratio, 90), 3),
                         "risk_ratio_max": round(max(ratio), 3) if ratio else None,
                         "risk_ratio_min": round(min(ratio), 6) if ratio else None,
                         "labeled_zero_risk_classes": zero_lab})
    return {"seeds": seeds, "nodes": args.n, "grid": grid}


def exp_stability(args):
    seeds = 8 if args.quick else 30
    draws = 3 if args.quick else 5
    t0, w0 = prior_grid("uniform[5,20]", args.m)
    noise = {}
    priors = {p: [] for p in PRIORS[1:]}
    readings = []
    for s in range(seeds):
        rng = np.random.default_rng(2000 + s)
        N, edges, chans, classes = gen_estate(rng, n=args.n)
        base = total_gains(chans, classes, t0, w0, "worst")
        share = total_gains(chans, classes, t0, w0, "share")
        m = rank_metrics(base, share)
        if m:
            readings.append(m)
        for p in PRIORS[1:]:
            t, w = prior_grid(p, args.m)
            m = rank_metrics(base, total_gains(chans, classes, t, w, "worst"))
            if m:
                priors[p].append(m)
        for sigma in (0.1, 0.25, 0.5, 1.0):
            for _ in range(draws):
                pert = []
                for ch in chans:
                    z = rng.normal(size=3)
                    pert.append(Channel(ch.src, ch.dst, float(np.clip(ch.O * math.exp(sigma * z[0]), 0, 1)),
                                        ch.tfix * math.exp(sigma * z[1]), ch.H * math.exp(sigma * z[2]), ch.configs))
                pcls = [DataClass(dc.origin, dc.C, dc.L * math.exp(sigma * rng.normal()), dc.labeled, dc.inferred)
                        for dc in classes]
                m = rank_metrics(base, total_gains(pert, pcls, t0, w0, "worst"))
                if m:
                    noise.setdefault(sigma, []).append(m)

    def summ(ms):
        if not ms:
            return None
        a = np.array(ms, dtype=float)
        return {"n": len(ms), "top1_agree": round(float(a[:, 0].mean()), 3),
                "top5_overlap_mean": round(float(a[:, 1].mean()), 3),
                "wtau_median": round(q(a[:, 2], 50), 3), "wtau_p10": round(q(a[:, 2], 10), 3)}
    return {"seeds": seeds, "draws_per_sigma": draws, "nodes": args.n,
            "noise": {str(k): summ(v) for k, v in sorted(noise.items())},
            "priors_vs_uniform": {k: summ(v) for k, v in priors.items()},
            "worst_vs_share": summ(readings)}


def greedy(Es, budget, tie):
    chosen = []
    for _ in range(budget):
        best, bj = -1.0, None
        cand = [j for j in range(len(tie)) if j not in chosen]
        for j in sorted(cand, key=lambda j: (-tie[j], j)):     # ties: larger remediable exposure, then index
            g = set_gain(Es, chosen + [j])
            if g > best + 1e-12:
                best, bj = g, j
        chosen.append(bj)
    return set_gain(Es, chosen)


def set_gain(Es, S):
    S = set(S)
    tot = 0.0
    for (idx, Em, E0, C, w) in Es:
        rows = [r for r, j in enumerate(idx) if j in S]
        tot += E.fix_set_gain(Em, E0, C, w, rows)
    return tot


def grouped(Es, budget, tie, n_ch):
    """§8.2 heuristic, group-aware greedy: candidates are single channels and, per data
    class, the group of its channels with remediable exposure. Each step adds the candidate
    with the largest marginal gain per channel added that still fits the budget."""
    cands = [[j] for j in range(n_ch)]
    for (idx, Em, E0, C, w) in Es:
        G = sorted({j for r, j in enumerate(idx) if float(np.dot(w, Em[r] - E0[r])) > 1e-12})
        if len(G) > 1:
            cands.append(G)
    chosen = []
    while len(chosen) < budget:
        base, best, bc = set_gain(Es, chosen), -1.0, None
        for G in sorted(cands, key=lambda G: (-sum(tie[j] for j in G), G)):
            new = [j for j in G if j not in chosen]
            if not new or len(chosen) + len(new) > budget:
                continue
            v = (set_gain(Es, chosen + new) - base) / len(new)
            if v > best + 1e-12:
                best, bc = v, new
        chosen += bc
    return set_gain(Es, chosen)


def exp_greedy(args):
    n_inst = 30 if args.quick else 150
    t, w = prior_grid("uniform[5,20]", 101)
    res = {}
    for reading in ("worst", "share"):
        for budget in (1, 2, 3):
            res[f"{reading}/k={budget}"] = {"greedy": [], "greedy_index_ties": [], "grouped": [], "opt_zero": 0}
    rng = np.random.default_rng(4)
    made, sizes = 0, []
    while made < n_inst:
        N, edges, chans, classes = gen_estate(rng, n=14, layers=4, out_deg=2, p_back=0.1)
        if not (8 <= len(chans) <= 40):
            continue
        made += 1
        sizes.append(len(chans))
        for reading in ("worst", "share"):
            Es = []
            for dc in classes:
                Em, E0 = E.class_matrices(chans, dc, dc.labeled, t, reading)
                if dc.labeled:
                    Es.append((dc.labeled, Em, E0, dc.C, w))
            tie = np.zeros(len(chans))
            for (idx, Em, E0, C, w_) in Es:
                np.add.at(tie, idx, C * ((Em - E0) @ w_))
            for budget in (1, 2, 3):
                opt = max(set_gain(Es, S) for S in itertools.combinations(range(len(chans)), budget))
                r = res[f"{reading}/k={budget}"]
                if opt <= 1e-12:
                    r["opt_zero"] += 1
                    continue
                r["greedy"].append(greedy(Es, budget, tie) / opt)
                r["greedy_index_ties"].append(greedy(Es, budget, np.zeros(len(chans))) / opt)
                r["grouped"].append(grouped(Es, budget, tie, len(chans)) / opt)
    out = {"instances": n_inst, "tie_rule": "largest remediable exposure, then lowest index",
           "channels_per_instance": [min(sizes), max(sizes)]}
    for k, r in res.items():
        out[k] = {"with_positive_opt": len(r["greedy"]), "opt_zero": r["opt_zero"]}
        for alg in ("greedy", "greedy_index_ties", "grouped"):
            a = np.array(r[alg])
            out[k][alg] = {"gap_fraction": round(float((a < 1 - 1e-9).mean()), 3) if len(a) else None,
                           "worst_ratio": round(float(a.min()), 3) if len(a) else None,
                           "mean_ratio": round(float(a.mean()), 3) if len(a) else None}
    return out


EXPS = {"validate": exp_validate, "fixpoint": exp_fixpoint, "scaling": exp_scaling,
        "inference": exp_inference, "stability": exp_stability, "greedy": exp_greedy}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=list(EXPS))
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--n", type=int, default=200, help="services per synthetic estate")
    ap.add_argument("--m", type=int, default=201, help="T_Q quantile-grid points")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "summary.json")
    summary = json.load(open(path)) if os.path.exists(path) else {}
    for name in args.only:
        t0 = time.perf_counter()
        summary[name] = EXPS[name](args)
        summary[name]["_seconds"] = round(time.perf_counter() - t0, 1)
        summary[name]["_quick"] = args.quick
        print(f"== {name} ({summary[name]['_seconds']} s)")
        print(json.dumps(summary[name], indent=1)[:3000])
        json.dump(summary, open(path, "w"), indent=2)


if __name__ == "__main__":
    main()
