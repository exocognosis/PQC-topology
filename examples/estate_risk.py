#!/usr/bin/env python3
"""Score your own estate for harvest-now-decrypt-later (HNDL) risk.

    python3 examples/estate_risk.py examples/estate.json [--json out.json]

Input: a JSON inventory of services, channels (with measured key-exchange shares) and
data classes; see examples/estate.json. Output: per-class risk under both readings of
the paper (worst case and share-weighted), the sunk part that no migration can remove,
and a ranking of which channel to migrate first. Needs numpy only.

The model is the paper's (Definitions 4-5, Definition 4', Propositions 1-7); the
functions come from testbed/synth/engine.py, which the property tests check against the
Lean statements.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "testbed", "synth"))
import engine as E  # noqa: E402

KINDS = {"classical", "hybrid", "broken"}


def crqc_grid(p):
    """Equal-weight quantile grid for the CRQC arrival time T_Q (years from now)."""
    m = int(p.get("points", 201))
    u = (np.arange(m) + 0.5) / m
    kind = p["kind"]
    if kind == "point":
        t = np.full(m, float(p["value"]))
    elif kind == "uniform":
        t = p["low"] + (p["high"] - p["low"]) * u
    elif kind == "shifted-exponential":
        t = p["shift"] - p["mean"] * np.log(1 - u)
    else:
        raise ValueError(f"unknown crqc_prior kind {kind!r}: use point, uniform or shifted-exponential")
    return t, np.full(m, 1.0 / m)


def load(path):
    with open(path) as f:
        spec = json.load(f)
    names = spec["services"]
    ix = {n: i for i, n in enumerate(names)}
    chans, edges, labels = [], [], []
    for c in spec["channels"]:
        bad = set(c["configs"]) - KINDS
        if bad:
            raise ValueError(f"{c['server']}<-{c['caller']}: unknown config kinds {bad}")
        tot = sum(c["configs"].values())
        configs = [(q / tot, k) for k, q in c["configs"].items()]
        s, d = ix[c["server"]], ix[c["caller"]]
        chans.append(E.Channel(s, d, float(c["O"]), float(c["t_fix"]), float(c["H"]), configs))
        edges.append((s, d))
        labels.append(f"{c['server']}<-{c['caller']}")
    tpq = spec.get("T_PQ", "inf")
    tpq = math.inf if tpq in ("inf", None) else float(tpq)
    classes = []
    for d in spec["data_classes"]:
        dc = E.DataClass(ix[d["origin"]], float(d["C"]), float(d["L"]), kind=d.get("flow", "read"))
        mode = d.get("flow", "read")
        idx = d.get("channels")  # explicit labels override inference
        idx = [labels.index(x) for x in idx] if idx else E.reachable_channels(len(names), edges, dc.origin, mode)
        classes.append((d["name"], dc, idx))
    return spec, chans, labels, classes, tpq


def analyse(path):
    spec, chans, labels, classes, tpq = load(path)
    t, w = crqc_grid(spec["crqc_prior"])
    out = {"classes": [], "first_fix": {}}
    gains = {r: np.zeros(len(chans)) for r in ("worst", "share")}
    for name, dc, idx in classes:
        row = {"class": name, "channels": [labels[i] for i in idx]}
        for r in ("worst", "share"):
            Em, E0 = E.class_matrices(chans, dc, idx, t, r, tpq=tpq)
            row[f"risk_{r}"] = E.risk(Em, dc.C, w)
            row[f"sunk_{r}"] = E.risk(E0, dc.C, w)
            g = E.fix_one_gains(Em, E0, dc.C, w)
            for j, i in enumerate(idx):
                gains[r][i] += g[j]
        out["classes"].append(row)
    for r in ("worst", "share"):
        order = np.argsort(-gains[r], kind="stable")
        out["first_fix"][r] = [{"channel": labels[i], "gain": float(gains[r][i]),
                                "classical_share": round(sum(q for q, k in chans[i].configs if k != "hybrid"), 3)}
                               for i in order]
    return out


def show(out):
    print("Per data class (risk = C x E[max exposure]; sunk = part no migration can remove)\n")
    print(f"{'class':<20}{'worst':>8}{'sunk':>8}{'share':>8}{'sunk':>8}  channels")
    for c in out["classes"]:
        print(f"{c['class']:<20}{c['risk_worst']:8.3f}{c['sunk_worst']:8.3f}"
              f"{c['risk_share']:8.3f}{c['sunk_share']:8.3f}  {', '.join(c['channels']) or '-'}")
    print("\nMigrate first (risk removed by fixing one channel now, summed over classes)\n")
    print(f"{'worst-case reading':<34}{'share-weighted reading'}")
    for a, b in zip(out["first_fix"]["worst"], out["first_fix"]["share"]):
        print(f"{a['channel']:<22}{a['gain']:8.3f}    {b['channel']:<22}{b['gain']:8.3f}")
    if out["first_fix"]["worst"][0]["channel"] != out["first_fix"]["share"][0]["channel"]:
        print("\nThe readings disagree on the first fix. Use worst case for secrets where one exposed "
              "record is enough (keys, credentials); share-weighted for bulk data.")
    if any(f["gain"] == 0 for f in out["first_fix"]["worst"]):
        print("\nA zero gain means another exposed channel on the same flow still leaks the data: "
              "fixing one hop alone does not help, fixing the hops together does (Proposition 8).")
    mixed = [f for f in out["first_fix"]["worst"] if 0 < f["classical_share"] < 1]
    for f in mixed:
        print(f"\n{f['channel']} also negotiates PQC: removing its classical fallback "
              f"({f['classical_share']:.0%} of sessions) removes the same risk as migrating it, "
              "at the cost of refusing legacy clients (paper §6.6).")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("estate", help="estate JSON, see examples/estate.json")
    ap.add_argument("--json", help="also write the results as JSON")
    a = ap.parse_args()
    out = analyse(a.estate)
    show(out)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
