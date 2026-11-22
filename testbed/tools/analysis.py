"""Extra analyses for the scorer: parameter uncertainty, cost-aware remediation actions,
complementarity, coverage and CRQC-prior sensitivity.

Standard library only, like score.py, because it runs on the host during `make local-run`.
Risk itself is always computed by the caller's `risk_for` (score.py), so the model of the
paper (Definitions 4, 4' and 5) has a single implementation.

Distribution specs (used in groundtruth.json "uncertainty" and "scenarios"):
  {"dist": "fixed"}                          the declared value
  {"dist": "lognormal", "sigma": s}          declared value is the MEDIAN; value * exp(s Z)
  {"dist": "uniform", "lo": a, "hi": b}      absolute interval
  {"dist": "relative_uniform", "rel": r}     value * U[1 - r, 1 + r]
  {"dist": "triangular", "lo": a, "mode": m, "hi": b}
Sampled values are clipped: O to [0, 1]; C, t_fix, H to >= 0; L to > 0.
"""
import copy
import math
import random
import statistics

INF = float("inf")
EPS = 1e-12
ROBUST_RULE = ("robust first fix = channel with the highest P(top-1) over draws with any "
               "positive gain; ties broken by mean gain, then by name")


# --------------------------------------------------------------------------- distributions
def quantile_grid(spec, m=201):
    """Equal-weight quantile grid for a CRQC-arrival prior."""
    d = spec.get("dist", "uniform")
    us = [(i + 0.5) / m for i in range(m)]
    if d == "point":
        return [float(spec["value"])] * m
    if d == "uniform":
        return [spec["lo"] + (spec["hi"] - spec["lo"]) * u for u in us]
    if d == "shifted_exp":
        return [spec["shift"] - spec["mean"] * math.log(1 - u) for u in us]
    if d == "lognormal":
        nd = statistics.NormalDist()
        return [spec["median"] * math.exp(spec["sigma"] * nd.inv_cdf(u)) for u in us]
    raise ValueError(f"unknown prior {d!r}")


def _clip(par, v):
    if par == "O":
        return min(1.0, max(0.0, v))
    if par == "L":
        return max(1e-9, v)
    return max(0.0, v)


def draw_value(spec, value, rng, par):
    if not spec or spec.get("dist", "fixed") == "fixed":
        return value
    d = spec["dist"]
    if d == "lognormal":
        v = value * math.exp(spec["sigma"] * rng.gauss(0.0, 1.0))
    elif d == "uniform":
        v = rng.uniform(spec["lo"], spec["hi"])
    elif d == "relative_uniform":
        v = value * rng.uniform(1 - spec["rel"], 1 + spec["rel"])
    elif d == "triangular":
        v = rng.triangular(spec["lo"], spec["hi"], spec["mode"])
    else:
        raise ValueError(f"unknown distribution {d!r}")
    return _clip(par, v)


def sample_gt(gt, unc, rng):
    """One draw of the model parameters; channel and class order is fixed for reproducibility."""
    g = copy.deepcopy(gt)
    default = unc.get("default", {})
    for key in sorted(g["channel_params"]):
        p = g["channel_params"][key]
        if not isinstance(p, dict):
            continue
        spec = unc.get("channels", {}).get(key, {})
        for par in ("O", "t_fix", "H"):
            if par in p:
                p[par] = draw_value(spec.get(par, default.get(par)), p[par], rng, par)
    for name in sorted(g["data_classes"]):
        dc = g["data_classes"][name]
        spec = unc.get("classes", {}).get(name, {})
        for par in ("C", "L"):
            dc[par] = draw_value(spec.get(par, default.get(par)), dc[par], rng, par)
    return g


# --------------------------------------------------------------------------- gains
def labeled_channels(dc):
    f = dc["labeled_flow"]
    return [(f[i], f[i + 1]) for i in range(len(f) - 1)]


def fix_gains(gt, obs, edges, samples, risk_for, reading, fixed_sets):
    """Total C-weighted risk reduction (all data classes, labeled flows) for each fix set."""
    out = []
    base = {}
    for name, dc in gt["data_classes"].items():
        base[name] = risk_for(gt, obs, labeled_channels(dc), dc, samples, reading=reading)[0]
    for S in fixed_sets:
        g = 0.0
        for name, dc in gt["data_classes"].items():
            after = risk_for(gt, obs, labeled_channels(dc), dc, samples, fixed_now=frozenset(S), reading=reading)[0]
            g += base[name] - after
        out.append(g)
    return out


def _pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _first_fix(gains, names):
    """Argmax gain, ties by name; None when every gain is zero."""
    best = min(range(len(names)), key=lambda i: (-gains[i], names[i]))
    return names[best] if gains[best] > EPS else None


def uncertainty_analysis(gt, obs, edges, risk_for):
    """Monte Carlo over parameter uncertainty: P(top-1), P(top-k), mean and 90% interval of
    each channel's fix-one gain, and a robust first fix, under both readings."""
    unc = gt.get("uncertainty")
    if not unc or not edges:
        return None
    a, b = gt["scenarios"]["T_Q_uniform"]
    m = unc.get("grid", 201)
    samples = quantile_grid({"dist": "uniform", "lo": a, "hi": b}, m)
    k, n = unc.get("k", 3), unc.get("draws", 200)
    rng = random.Random(unc.get("seed", 7))
    names = [f"{s}->{c}" for s, c in edges]
    singles = [[e] for e in edges]
    point = {r: fix_gains(gt, obs, edges, samples, risk_for, r, singles) for r in ("worst", "share")}
    draws = {"worst": [], "share": []}
    for _ in range(n):
        g = sample_gt(gt, unc, rng)
        for r in draws:
            draws[r].append(fix_gains(g, obs, edges, samples, risk_for, r, singles))
    out = {"draws": n, "grid_points": m, "prior": f"U[{a},{b}]", "k": k, "rule": ROBUST_RULE,
           "note": "declared values are treated as medians of lognormal distributions unless "
                   "a channel or class spec says otherwise", "readings": {}}
    for r, rows in draws.items():
        top1 = [0] * len(edges)
        topk = [0] * len(edges)
        valid = 0
        for gains in rows:
            order = sorted(range(len(edges)), key=lambda i: (-gains[i], names[i]))
            if gains[order[0]] <= EPS:
                continue
            valid += 1
            top1[order[0]] += 1
            for i in order[:k]:
                if gains[i] > EPS:
                    topk[i] += 1
        chans = []
        for i, nm in enumerate(names):
            col = [row[i] for row in rows]
            chans.append({"channel": nm, "point_gain": round(point[r][i], 3),
                          "mean_gain": round(sum(col) / len(col), 3),
                          "ci90": [round(_pct(col, 0.05), 3), round(_pct(col, 0.95), 3)],
                          "p_top1": round(top1[i] / valid, 3) if valid else 0.0,
                          "p_topk": round(topk[i] / valid, 3) if valid else 0.0})
        chans.sort(key=lambda c: (-c["p_top1"], -c["mean_gain"], c["channel"]))
        robust = chans[0]["channel"] if valid and chans[0]["p_top1"] > 0 else None
        out["readings"][r] = {"channels": chans, "robust_first_fix": robust,
                              "point_first_fix": _first_fix(point[r], names),
                              "draws_with_zero_gain": n - valid}
    rw, rs = out["readings"]["worst"]["robust_first_fix"], out["readings"]["share"]["robust_first_fix"]
    out["readings_diverge"] = rw != rs
    return out


# --------------------------------------------------------------------------- actions
def remediation_actions(gt, obs, edges, samples, risk_for, is_hybrid, rem):
    """First-class actions with costs. 'migrate' fixes the channel now. 'remove_fallback'
    stops its classical sessions now; recorded classical traffic stays sunk, so its risk
    effect equals migrating now (Proposition 7(f): the remediable part q * min(t_fix, W)),
    but it costs refused legacy clients instead of migration work."""
    costs = gt.get("costs", {})
    by = {r["channel"]: r for r in rem}
    acts = []
    for s, c in edges:
        name = f"{s}->{c}"
        p = gt["channel_params"].get(name, {})
        cnt = obs.get((s, c), {})
        tot = sum(cnt.values()) or 1
        q_classical = sum(n for cfg, n in cnt.items() if not is_hybrid(cfg)) / tot
        gw, gs = by[name]["risk_reduction"], by[name]["risk_reduction_share"]
        cm = p.get("cost_migrate", costs.get("migrate", 1.0))
        acts.append({"action": "migrate", "channel": name, "cost": round(cm, 3),
                     "gain_worst": gw, "gain_share": gs,
                     "gain_per_cost_worst": round(gw / cm, 3) if cm else None})
        if 0 < q_classical < 1:  # only a channel that also negotiates a hybrid has a fallback
            cf = p.get("cost_fallback", q_classical * costs.get("legacy_client_weight", 1.0))
            acts.append({"action": "remove_fallback", "channel": name, "cost": round(cf, 3),
                         "classical_share": round(q_classical, 3), "gain_worst": gw, "gain_share": gs,
                         "gain_per_cost_worst": round(gw / cf, 3) if cf else None})
    acts.sort(key=lambda x: (-(x["gain_per_cost_worst"] or 0), x["channel"], x["action"]))
    return acts


def complementarity(gt, obs, edges, samples, risk_for):
    """gap(e, f) = g({e, f}) - g(e) - g(f): positive when fixing one raises the other's value."""
    pairs = [(edges[i], edges[j]) for i in range(len(edges)) for j in range(i + 1, len(edges))]
    out = {}
    for r in ("worst", "share"):
        single = dict(zip(edges, fix_gains(gt, obs, edges, samples, risk_for, r, [[e] for e in edges])))
        pg = fix_gains(gt, obs, edges, samples, risk_for, r, [list(p) for p in pairs])
        rows = [{"pair": [f"{a[0]}->{a[1]}", f"{b[0]}->{b[1]}"], "gain_pair": round(g, 3),
                 "gap": round(g - single[a] - single[b], 3)} for (a, b), g in zip(pairs, pg)]
        rows.sort(key=lambda x: -x["gap"])
        out[r] = {"max_gap": rows[0]["gap"] if rows else 0.0,
                  "complementary_pairs": [x for x in rows if x["gap"] > 1e-9]}
    return out


# --------------------------------------------------------------------------- coverage
def coverage(gt, obs, edges, samples, risk_for, reachable):
    """Labeled vs inferred flows, negotiation telemetry, and residual risk from channels whose
    caller could not be attributed (worst-case reading, default channel parameters)."""
    per, lab_n, inf_n, tel_n, tel_have, resid = {}, 0, 0, 0, 0, 0.0
    unknown = [ch for ch in edges if ch[1].startswith("unknown:")]
    for name, dc in gt["data_classes"].items():
        lab = labeled_channels(dc) if dc.get("labeled_flow") else []
        inf = reachable(dc["origin"], edges)
        both = set(lab) | set(inf)
        tel_n += len(both)
        tel_have += sum(1 for ch in both if sum(obs.get(ch, {}).values()) > 0)
        holders = {dc["origin"]} | {c for _, c in inf}
        u = [ch for ch in unknown if ch[0] in holders]
        r_add = 0.0
        if u and lab:
            r_add = (risk_for(gt, obs, lab + u, dc, samples)[0] - risk_for(gt, obs, lab, dc, samples)[0])
        resid += r_add
        lab_n += len(set(lab) & set(inf))
        inf_n += len(inf)
        per[name] = {"labeled_channels": len(lab), "inferred_channels": len(inf),
                     "labeled_fraction_of_inferred": round(len(set(lab) & set(inf)) / len(inf), 3) if inf else 1.0,
                     "unknown_channels": len(u), "residual_unknown_risk": round(r_add, 3)}
    labeled_classes = sum(1 for dc in gt["data_classes"].values() if dc.get("labeled_flow"))
    return {"classes_with_labels": round(labeled_classes / max(1, len(gt["data_classes"])), 3),
            "labeled_fraction_of_inferred": round(lab_n / inf_n, 3) if inf_n else 1.0,
            "channels_with_negotiation_data": round(tel_have / tel_n, 3) if tel_n else 1.0,
            "unknown_channels": len(unknown), "residual_unknown_risk": round(resid, 3), "per_class": per}


# --------------------------------------------------------------------------- priors
def _tpq(v):
    return INF if v in (None, "inf", "Infinity") else float(v)


def prior_sensitivity(gt, obs, risk_for):
    """Propagated risk per data class (both readings) for each CRQC-arrival prior and T_PQ."""
    sc = gt["scenarios"]
    priors = sc.get("T_Q_priors")
    if not priors:
        return None
    rows = []
    for pr in priors:
        samples = quantile_grid(pr, sc.get("prior_grid_points", 201))
        for tpq in sc.get("T_PQ_prior_points", ["inf"]):
            row = {"prior": pr["name"], "T_PQ": "inf" if _tpq(tpq) == INF else _tpq(tpq), "hndl": {}}
            for name, dc in gt["data_classes"].items():
                lab = labeled_channels(dc)
                row["hndl"][name] = {r: round(risk_for(gt, obs, lab, dc, samples, reading=r, tpq=_tpq(tpq))[0], 3)
                                     for r in ("worst", "share")}
            rows.append(row)
    return rows
