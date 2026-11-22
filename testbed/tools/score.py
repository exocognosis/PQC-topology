#!/usr/bin/env python3
"""Score a testbed run: discovery accuracy, supported-vs-negotiated gap,
HNDL and TNFL risk under the paper's model, remediation ranking, CBOM.

Usage: python3 tools/score.py results/<run> [--groundtruth groundtruth.json]

Inputs in results/<run>/:
  <host>/access.log        nginx telemetry (negotiated protocol, cipher, group)
  <host>/handshakes.tsv    optional, from tools/extract_handshakes.sh
  probe/probe.json         from tools/probe.py
  inventory.json           optional, {"<host>": {"public": "<ip>"}} for cloud runs
Outputs: report.md, score.json, cbom.json in results/<run>/.
Standard library only.
"""
import argparse
import collections
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis  # noqa: E402  (stdlib-only extra analyses)

INF = math.inf
HOSTS = ["gw", "lb", "appa", "appb", "data"]
GROUP_IDS = {"0x11ec": "X25519MLKEM768", "4588": "X25519MLKEM768",
             "0x11eb": "SecP256r1MLKEM768", "4587": "SecP256r1MLKEM768",
             "0x11ed": "SecP384r1MLKEM1024", "4589": "SecP384r1MLKEM1024",
             "29": "X25519", "0x001d": "X25519", "30": "X448",
             "23": "prime256v1", "0x0017": "prime256v1", "24": "secp384r1", "25": "secp521r1",
             "256": "ffdhe2048", "257": "ffdhe3072"}
CIPHER_IDS = {"0x009d": "AES256-GCM-SHA384", "0x009c": "AES128-GCM-SHA256",
              "0xc02c": "ECDHE-ECDSA-AES256-GCM-SHA384", "0xc02b": "ECDHE-ECDSA-AES128-GCM-SHA256",
              "0xcca9": "ECDHE-ECDSA-CHACHA20-POLY1305", "0x1302": "TLS_AES_256_GCM_SHA384",
              "0x1301": "TLS_AES_128_GCM_SHA256", "0x1303": "TLS_CHACHA20_POLY1305_SHA256"}


# --------------------------------------------------------------------------- model
def kex_break_time(protocol, cipher, group, tq, tpq=INF):
    """Break time of a negotiated layer (Definition 3: min over kex and cipher).

    tpq is the break time of the post-quantum component (assumption A6; INF by default).
    """
    c = (cipher or "").upper()
    if "3DES" in c or "DES-CBC3" in c or "RC4" in c:
        return 0.0  # classically broken
    g = group or "-"
    if "MLKEM" in g.upper():
        t_kex = max(tq, tpq)  # hybrid, rule H with assumption A2
    elif g not in ("-", ""):
        t_kex = tq  # (EC)DHE: Shor-vulnerable
    elif protocol == "TLSv1.2" and "ECDHE" not in c and "DHE" not in c:
        t_kex = tq  # static RSA key transport
    else:
        t_kex = tq  # unknown: conservative
    t_cipher = INF  # AES-128/256, ChaCha20: Grover margin treated as policy (inf)
    return min(t_kex, t_cipher)


def window(t_fix, H, L, T):
    """Exposure window W (Definition 4)."""
    if T == INF:
        return 0.0
    return max(0.0, t_fix - max(-H, T - L))


def tq_samples(scen):
    pts = [(f"T_Q={t}", [float(t)]) for t in scen["T_Q_points"]]
    a, b = scen["T_Q_uniform"]
    n = 3001
    grid = [a + (b - a) * i / (n - 1) for i in range(n)]
    pts.append((f"E[T_Q~U({a},{b})]", grid))
    return pts


# --------------------------------------------------------------------------- inputs
def ip_map(gt, run_dir):
    m = {}
    for h, v in gt["hosts"].items():
        if v.get("private"):
            m[v["private"]] = h
        for ip in v.get("local_extra", []) or []:
            m[ip] = h
    inv = os.path.join(run_dir, "inventory.json")
    if os.path.exists(inv):
        with open(inv) as f:
            for h, v in json.load(f).items():
                if v.get("public"):
                    m[v["public"]] = h
    return m


def read_access_logs(run_dir, ips):
    """Observed channels (server_host, caller_host) -> Counter of (proto, cipher, group)."""
    obs = collections.defaultdict(collections.Counter)
    for host in HOSTS:
        path = os.path.join(run_dir, host, "access.log")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                parts = line.split()
                if len(parts) < 7:
                    continue
                _, remote, _, proto, cipher, group = parts[:6]
                caller = ips.get(remote, "unknown:" + remote)
                if caller == "probe":
                    continue
                obs[(host, caller)][(proto, cipher, GROUP_IDS.get(group.lower(), group))] += 1
    return obs


def read_handshakes(run_dir, ips, gt):
    """Passive pcap view, counted only at the server's own capture to avoid duplicates."""
    own = {h: {v.get("private")} | set(v.get("local_extra", []) or []) for h, v in gt["hosts"].items()}
    inv = os.path.join(run_dir, "inventory.json")
    if os.path.exists(inv):  # cloud runs: a server's public address is also its own
        with open(inv) as f:
            for h, v in json.load(f).items():
                if v.get("public"):
                    own.setdefault(h, set()).add(v["public"])
    obs = collections.defaultdict(collections.Counter)
    for host in HOSTS:
        path = os.path.join(run_dir, host, "handshakes.tsv")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 7 or cols[0] not in own.get(host, set()):
                    continue
                src, _, dst, ver, cs, ks, curve = cols[:7]
                if not cs:
                    continue  # ServerKeyExchange-only record
                proto = "TLSv1.3" if ver == "0x0304" else "TLSv1.2"
                grp = ks or curve or "-"
                caller = ips.get(dst, "unknown:" + dst)
                if caller == "probe":
                    continue
                obs[(host, caller)][
                    (proto, CIPHER_IDS.get(cs, cs), GROUP_IDS.get(grp.lower(), grp))] += 1
    return obs


# --------------------------------------------------------------------------- analysis
def prf(found, truth):
    f, t = set(found), set(truth)
    tp = len(f & t)
    return {"tp": tp, "fp": len(f - t), "fn": len(t - f),
            "precision": tp / len(f) if f else (1.0 if not t else 0.0),
            "recall": tp / len(t) if t else 1.0}


def discovery_accuracy(gt, probe):
    rows, totals = [], collections.Counter()
    for lst in gt["listeners"]:
        key = f'{lst["host"]}:{lst["port"]}'
        p = probe["listeners"].get(key, {})
        cert_gt = gt["certs"][lst["cert"]]
        cert_p = p.get("cert") or {}
        r = {"listener": key,
             "versions": prf(p.get("tls_versions", []), lst["tls_versions"]),
             "groups": prf(p.get("groups", []), lst["groups"]),
             "tls12_ciphers": prf(p.get("tls12_ciphers", []), lst["tls12_ciphers"]),
             # TLS 1.2 groups are scored only when the probe enumerated them (newer probes)
             "tls12_groups": (prf(p.get("tls12_groups", []), lst.get("tls12_groups", []))
                              if "tls12_groups" in p else None),
             "cert_key_ok": cert_p.get("key") == cert_gt["key"],
             "cert_sig_ok": cert_p.get("sig") == cert_gt["sig"]}
        rows.append(r)
        for k in ("versions", "groups", "tls12_ciphers", "tls12_groups"):
            for m in ("tp", "fp", "fn"):
                totals[m] += r[k][m] if r[k] else 0
        totals["cert_ok"] += int(r["cert_key_ok"] and r["cert_sig_ok"])
    static_rows = []
    for name, truth in gt["certs"].items():
        found = (probe.get("static") or {}).get("certs", {}).get(name)
        static_rows.append({"cert": name, "found": bool(found),
                            "key_ok": bool(found) and found["key"] == truth["key"],
                            "sig_ok": bool(found) and found["sig"] == truth["sig"]})
    tp, fp, fn = totals["tp"], totals["fp"], totals["fn"]
    return {"listeners": rows, "static": static_rows,
            "overall": {"precision": tp / (tp + fp) if tp + fp else 1.0,
                        "recall": tp / (tp + fn) if tp + fn else 1.0,
                        "certs_correct": f'{totals["cert_ok"]}/{len(rows)}',
                        "static_certs_correct": f'{sum(r["key_ok"] and r["sig_ok"] for r in static_rows)}/{len(static_rows)}'}}


def channel_params(gt, server, caller):
    cp = gt["channel_params"]
    return cp.get(f"{server}->{caller}", cp["default"])


def reachable_channels(origin, edges):
    """Inferred Ch(d): read-path channels whose server end is reachable from origin."""
    seen, stack = {origin}, [origin]
    adj = collections.defaultdict(set)
    for s, c in edges:
        adj[s].add(c)
    while stack:
        x = stack.pop()
        for y in adj[x]:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return sorted((s, c) for s, c in edges if s in seen)


def channel_window(configs, t_fix, H, L, tq, reading, tpq=INF):
    """Window of one channel over its negotiated configurations (Definition 4').

    reading="worst": max over configurations with a positive share (any of d exposed).
    reading="share": share-weighted mixture sum_k q_k W_k (how much of d is exposed).
    """
    total = sum(n for n in configs.values() if n > 0)
    if total == 0:
        return 0.0
    vals = [(n / total, window(t_fix, H, L, kex_break_time(p, ci, g, tq, tpq)))
            for (p, ci, g), n in configs.items() if n > 0]
    if reading == "share":
        return sum(q * w for q, w in vals)
    return max(w for _, w in vals)


def risk_for(gt, obs, channels, dc, samples, fixed_now=frozenset(), reading="worst", tpq=INF):
    """R(d) and sunk R0(d), averaged over T_Q samples (Definition 5, max over channels)."""
    R = R0 = 0.0
    for tq in samples:
        best = best0 = 0.0
        for (s, c) in channels:
            params = channel_params(gt, s, c)
            t_fix = 0.0 if (s, c) in fixed_now else params["t_fix"]
            configs = obs.get((s, c), {})
            best = max(best, params["O"] * channel_window(configs, t_fix, params["H"], dc["L"], tq, reading, tpq))
            best0 = max(best0, params["O"] * channel_window(configs, 0.0, params["H"], dc["L"], tq, reading, tpq))
        R += best
        R0 += best0
    k = len(samples)
    return dc["C"] * R / k, dc["C"] * R0 / k


def tnfl(gt, probe, samples, tpq=INF):
    static = (probe.get("static") or {}).get("certs", {})
    subj = {v["subject"]: k for k, v in static.items() if v.get("subject")}
    parent = {k: subj.get(v.get("issuer")) for k, v in static.items()}
    def quantum_vulnerable(k):
        key = (static.get(k) or {}).get("key") or ""
        return key.startswith("RSA") or key.startswith("EC")
    def tau(k):
        tp = gt["trust_params"].get(k)
        if not tp:
            return None
        v = tp["V"] if tp["expiry_enforced"] else INF
        mig = (tp["T_mig"] + tp["D"]) if tp["verifier_updatable"] else INF
        return min(v, mig, tp["Lambda"])
    out = {"keys": {}, "artifacts": {}}
    for k in static:
        t = tau(k)
        if t is None:
            continue
        S = []
        for tq in samples:
            T = tq if quantum_vulnerable(k) else tpq
            S.append(max(0.0, t - T) if T != INF else 0.0)
        out["keys"][k] = {"tau": t, "S": sum(S) / len(S), "quantum_vulnerable": quantum_vulnerable(k)}
    for art, meta in gt["artifacts"].items():
        chain, k = [], meta["signer"]
        while k and k not in chain:
            chain.append(k)
            nxt = parent.get(k)
            k = nxt if nxt != k else None
        vals = []
        for tq in samples:
            m = 0.0
            for key in chain:
                t = tau(key)
                T = tq if quantum_vulnerable(key) else tpq
                if t is None or T == INF:
                    continue
                m = max(m, max(0.0, t - T))
            vals.append(m)
        out["artifacts"][art] = {"chain": chain, "R_T": meta["C"] * meta["A"] * sum(vals) / len(vals),
                                 "dominant_key": max(chain, key=lambda x: out["keys"].get(x, {}).get("S", 0))}
    return out


# --------------------------------------------------------------------------- SSH plane
PSEUDO_KEX = ("ext-info-", "kex-strict-")


def real_kex(algs):
    return [a for a in algs if not a.startswith(PSEUDO_KEX)]


def ssh_break_time(alg, tq, tpq=INF):
    """Hybrid SSH key exchange (ML-KEM or sntrup761 with X25519) breaks at max(T_Q, T_PQ)."""
    return max(tq, tpq) if ("mlkem" in alg or "sntrup" in alg) else tq


def read_ssh_pcap(run_dir, ips, gt):
    """Negotiated SSH key exchange per channel, from KEXINIT messages captured at the server:
    the first client algorithm that the server also offers (RFC 4253, section 7.1)."""
    obs = collections.defaultdict(collections.Counter)
    for lst in gt.get("ssh_listeners", []):
        path = os.path.join(run_dir, lst["host"], "ssh_kexinit.tsv")
        if not os.path.exists(path):
            continue
        conns = collections.defaultdict(dict)
        for line in open(path):
            f = line.rstrip("\n").split("\t")
            if len(f) < 5 or not f[4]:
                continue
            src, sport, dst, dport, algs = f[0], f[1], f[2], f[3], f[4].split(",")
            if dport == str(lst["port"]):
                conns[(src, sport)]["client"] = algs
            elif sport == str(lst["port"]):
                conns[(dst, dport)]["server"] = algs
        for (cip, _), kx in conns.items():
            caller = ips.get(cip, "unknown:" + cip)
            if caller == "probe" or "client" not in kx or "server" not in kx:
                continue
            neg = next((a for a in kx["client"] if a in kx["server"] and not a.startswith(PSEUDO_KEX)), None)
            obs[(lst["host"], caller)][neg or "none"] += 1
    return obs


def read_sshd_log(run_dir, gt):
    """Negotiated SSH key exchange per listener from sshd's own DEBUG1 log (telemetry).
    sshd's debug lines carry no connection identifier, so concurrent sessions cannot be
    attributed to callers reliably; the log is compared with the captures per listener.
    Failed negotiations, such as the probe's, appear as "(no match)" and are skipped."""
    obs = collections.defaultdict(collections.Counter)
    for lst in gt.get("ssh_listeners", []):
        path = os.path.join(run_dir, lst["host"], "sshd.log")
        if not os.path.exists(path):
            continue
        for line in open(path, errors="replace"):
            m = re.search(r"kex: algorithm: (\S+)", line)
            if m and not m.group(1).startswith("("):
                obs[f'{lst["host"]}:{lst["port"]}'][m.group(1)] += 1
    return obs


def ssh_risk(gt, obs, cls, samples, reading="worst", fixed=frozenset(), tpq=INF):
    R = R0 = 0.0
    for tq in samples:
        best = best0 = 0.0
        for s, c in cls["channels"]:
            p = channel_params(gt, s, c)
            cnt = {a: n for a, n in obs.get((s, c), {}).items() if n > 0}
            tot = sum(cnt.values())
            if not tot:
                continue
            for tf, acc in (((0.0 if (s, c) in fixed else p["t_fix"]), "R"), (0.0, "R0")):
                ws = [(n / tot, window(tf, p["H"], cls["L"], ssh_break_time(a, tq, tpq))) for a, n in cnt.items()]
                w = sum(q * x for q, x in ws) if reading == "share" else max(x for _, x in ws)
                if acc == "R":
                    best = max(best, p["O"] * w)
                else:
                    best0 = max(best0, p["O"] * w)
        R += best
        R0 += best0
    k = len(samples)
    return cls["C"] * R / k, cls["C"] * R0 / k


def ssh_plane(gt, probe, run_dir, ips, key_samples):
    if not gt.get("ssh_listeners"):
        return None
    pcap, logs = read_ssh_pcap(run_dir, ips, gt), read_sshd_log(run_dir, gt)
    if not pcap and not logs:
        return None
    disc = []
    for lst in gt["ssh_listeners"]:
        found = next((r for r in probe.get("ssh", []) if r["host"] == lst["host"]), None)
        disc.append({"listener": f'{lst["host"]}:{lst["port"]}',
                     "kex": prf(real_kex(found["kex_algorithms"]) if found else [], lst["kex"])})
    chans = []
    for ch in sorted(pcap):
        a = pcap[ch]
        tot = sum(a.values()) or 1
        chans.append({"channel": f"{ch[0]}->{ch[1]}", "negotiated_pcap": {k: round(v / tot, 3) for k, v in a.most_common()},
                      "connections_pcap": sum(a.values())})
    agree = []
    for lst in gt["ssh_listeners"]:
        key = f'{lst["host"]}:{lst["port"]}'
        tot = collections.Counter()
        for (srv, _), cnt in pcap.items():
            if srv == lst["host"]:
                tot.update(cnt)
        agree.append({"listener": key, "pcap": dict(tot), "log": dict(logs.get(key, {})),
                      "agree": "yes" if tot == logs.get(key) else ("no log" if key not in logs else "NO")})
    risk = {}
    for name, cls in gt.get("ssh_classes", {}).items():
        cls_ch = [tuple(c) for c in cls["channels"]]
        row = {}
        for reading in ("worst", "share"):
            R, R0 = ssh_risk(gt, pcap, cls, key_samples, reading)
            gains = {f"{s}->{c}": round(R - ssh_risk(gt, pcap, cls, key_samples, reading, frozenset([(s, c)]))[0], 3)
                     for s, c in cls_ch}
            row[reading] = {"R": round(R, 3), "sunk": round(R0, 3), "fix_one": gains}
        risk[name] = row
    return {"discovery": disc, "channels": chans, "log_agreement": agree, "risk": risk}


# --------------------------------------------------------------------------- CBOM
def cbom(gt, probe, obs, cov=None):
    comps, seen = [], set()
    def add(ref, comp):
        if ref not in seen:
            seen.add(ref)
            comp["bom-ref"] = ref
            comps.append(comp)
    for (s, c), counter in obs.items():
        for (proto, cipher, group), n in counter.items():
            if group not in ("-", ""):
                add(f"algo:{group}", {"type": "cryptographic-asset", "name": group,
                    "cryptoProperties": {"assetType": "algorithm",
                        "algorithmProperties": {"primitive": "kem" if "MLKEM" in group else "key-agree"}},
                    "properties": [{"name": "dytallix:break-time-class",
                                    "value": "hybrid" if "MLKEM" in group else "shor-vulnerable"}]})
        total = sum(counter.values())
        add(f"proto:{s}->{c}", {"type": "cryptographic-asset", "name": f"TLS {s}->{c}",
            "cryptoProperties": {"assetType": "protocol", "protocolProperties": {
                "type": "tls", "cipherSuites": [{"name": ci} for (_, ci, _) in sorted(counter)]}},
            "properties": [{"name": "dytallix:channel", "value": f"{s}->{c}"}] +
                          [{"name": f"dytallix:negotiated:{p}:{g}", "value": f"{n / total:.3f}"}
                           for (p, _, g), n in sorted(counter.items())]})
    for name, cert in ((probe.get("static") or {}).get("certs") or {}).items():
        add(f"cert:{name}", {"type": "cryptographic-asset", "name": name,
            "cryptoProperties": {"assetType": "certificate", "certificateProperties": {
                "subjectName": cert.get("subject"), "issuerName": cert.get("issuer"),
                "notValidAfter": cert.get("not_after")}},
            "properties": [{"name": "dytallix:key-algorithm", "value": str(cert.get("key"))},
                           {"name": "dytallix:signature-algorithm", "value": str(cert.get("sig"))}]})
    meta = {"component": {"type": "application", "name": "pqc-topology-testbed"}}
    if cov:
        meta["properties"] = [
            {"name": "dytallix:coverage:classesWithLabels", "value": str(cov["classes_with_labels"])},
            {"name": "dytallix:coverage:labeledFractionOfInferred", "value": str(cov["labeled_fraction_of_inferred"])},
            {"name": "dytallix:coverage:channelsWithNegotiationData", "value": str(cov["channels_with_negotiation_data"])},
            {"name": "dytallix:coverage:unknownChannels", "value": str(cov["unknown_channels"])},
            {"name": "dytallix:coverage:residualUnknownRisk", "value": str(cov["residual_unknown_risk"])}]
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": meta, "components": comps}


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--groundtruth", default="groundtruth.json")
    a = ap.parse_args()
    with open(a.groundtruth) as f:
        gt = json.load(f)
    with open(os.path.join(a.run_dir, "probe", "probe.json")) as f:
        probe = json.load(f)
    ips = ip_map(gt, a.run_dir)
    obs = read_access_logs(a.run_dir, ips)
    passive = read_handshakes(a.run_dir, ips, gt)
    disc = discovery_accuracy(gt, probe)
    scen = tq_samples(gt["scenarios"])
    edges = sorted(obs)

    # supported vs negotiated
    gap = []
    for lst in gt["listeners"]:
        key = f'{lst["host"]}:{lst["port"]}'
        supported = probe["listeners"].get(key, {}).get("groups", []) or ["(TLS 1.2 RSA kex)"]
        neg = collections.Counter()
        for (s, c), cnt in obs.items():
            if s == lst["service"]:
                for (p, ci, g), n in cnt.items():
                    neg[g if g != "-" else f"{p} {ci}"] += n
        tot = sum(neg.values()) or 1
        gap.append({"listener": key, "supported": supported,
                    "negotiated": {g: round(n / tot, 3) for g, n in neg.most_common()},
                    "handshakes_logged": sum(neg.values())})

    # passive agreement: per channel, do logs and pcaps show the same groups?
    agree = []
    for ch in sorted(set(obs) | set(passive)):
        lg = {g for (_, _, g) in obs.get(ch, {})}
        pg = {g for (_, _, g) in passive.get(ch, {})}
        verdict = "no pcap" if not pg else ("yes" if lg == pg else "NO")
        agree.append({"channel": f"{ch[0]}->{ch[1]}", "log_groups": sorted(lg),
                      "pcap_groups": sorted(pg), "pcap_handshakes": sum(passive.get(ch, {}).values()),
                      "agree": verdict})

    # HNDL risk per data class
    hndl = {}
    for name, dc in gt["data_classes"].items():
        flow = dc["labeled_flow"]
        labeled = [(flow[i], flow[i + 1]) for i in range(len(flow) - 1)]
        local = [(s, c) for (s, c) in edges if s == dc["origin"]]
        inferred = reachable_channels(dc["origin"], edges)
        res = {"labeled_channels": [f"{s}->{c}" for s, c in labeled],
               "inferred_channels": [f"{s}->{c}" for s, c in inferred],
               "inference_extra": sorted(set(f"{s}->{c}" for s, c in inferred) -
                                         set(f"{s}->{c}" for s, c in labeled)),
               "endpoint_view": {g for (_, _, g) in obs.get(local[0], {})} if local else set(),
               "scenarios": {}}
        res["endpoint_view"] = sorted(res["endpoint_view"])
        for label, samples in scen:
            Rl, _ = risk_for(gt, obs, local, dc, samples)
            R, R0 = risk_for(gt, obs, labeled, dc, samples)
            Ri, Ri0 = risk_for(gt, obs, inferred, dc, samples)
            Rls, _ = risk_for(gt, obs, local, dc, samples, reading="share")
            Rs, Rs0 = risk_for(gt, obs, labeled, dc, samples, reading="share")
            Ris, _ = risk_for(gt, obs, inferred, dc, samples, reading="share")
            res["scenarios"][label] = {"local": round(Rl, 3), "labeled": round(R, 3),
                                       "labeled_sunk": round(R0, 3), "labeled_remediable": round(R - R0, 3),
                                       "inferred": round(Ri, 3), "inferred_sunk": round(Ri0, 3),
                                       "share": {"local": round(Rls, 3), "labeled": round(Rs, 3),
                                                 "labeled_sunk": round(Rs0, 3),
                                                 "labeled_remediable": round(Rs - Rs0, 3),
                                                 "inferred": round(Ris, 3)}}
        hndl[name] = res

    # remediation: total C-weighted risk reduction from fixing one channel now
    rem = []
    key_label, key_samples = scen[-1]
    for ch in edges:
        gain = {"worst": 0.0, "share": 0.0}
        for name, dc in gt["data_classes"].items():
            flow = dc["labeled_flow"]
            labeled = [(flow[i], flow[i + 1]) for i in range(len(flow) - 1)]
            for reading in gain:
                base, _ = risk_for(gt, obs, labeled, dc, key_samples, reading=reading)
                after, _ = risk_for(gt, obs, labeled, dc, key_samples, fixed_now=frozenset([ch]),
                                    reading=reading)
                gain[reading] += base - after
        rem.append({"channel": f"{ch[0]}->{ch[1]}", "risk_reduction": round(gain["worst"], 3),
                    "risk_reduction_share": round(gain["share"], 3)})
    rem.sort(key=lambda r: -r["risk_reduction"])

    trust = tnfl(gt, probe, key_samples)
    ssh = ssh_plane(gt, probe, a.run_dir, ips, key_samples)

    # dual reading: does the first fix depend on the reading?
    first = {r: (max(rem, key=lambda x: (x[col], -edges.index(tuple(x["channel"].split("->", 1)))))["channel"]
                 if rem and max(x[col] for x in rem) > 0 else None)
             for r, col in (("worst", "risk_reduction"), ("share", "risk_reduction_share"))}
    readings = {"worst_first_fix": first["worst"], "share_first_fix": first["share"],
                "diverge": first["worst"] != first["share"]}

    def is_hybrid(cfg):
        return kex_break_time(*cfg, 1.0) == INF
    actions = analysis.remediation_actions(gt, obs, edges, key_samples, risk_for, is_hybrid, rem)
    comp = analysis.complementarity(gt, obs, edges, key_samples, risk_for) if len(edges) <= 15 else None
    cov = analysis.coverage(gt, obs, edges, key_samples, risk_for, reachable_channels)
    unc = analysis.uncertainty_analysis(gt, obs, edges, risk_for)
    priors = analysis.prior_sensitivity(gt, obs, risk_for)

    # sensitivity to a finite break time of the post-quantum components (assumption A6)
    pq = []
    for tpq in gt["scenarios"].get("T_PQ_points", []):
        row = {"T_PQ": tpq, "hndl": {}, "tnfl": {}}
        for name, dc in gt["data_classes"].items():
            flow = dc["labeled_flow"]
            labeled = [(flow[i], flow[i + 1]) for i in range(len(flow) - 1)]
            w, _ = risk_for(gt, obs, labeled, dc, key_samples, reading="worst", tpq=tpq)
            sh, _ = risk_for(gt, obs, labeled, dc, key_samples, reading="share", tpq=tpq)
            row["hndl"][name] = {"worst": round(w, 3), "share": round(sh, 3)}
        tr = tnfl(gt, probe, key_samples, tpq=tpq)
        row["tnfl"] = {k: round(v["S"], 3) for k, v in tr["keys"].items()}
        pq.append(row)
    score = {"discovery": disc, "supported_vs_negotiated": gap, "passive_agreement": agree,
             "hndl": hndl, "remediation": rem, "tnfl": trust, "pq_sensitivity": pq, "ssh_plane": ssh,
             "scenario_for_rankings": key_label,
             "ssh": probe.get("ssh", []),
             "readings": readings, "actions": actions, "complementarity": comp, "coverage": cov,
             "uncertainty": unc, "prior_sensitivity": priors}
    with open(os.path.join(a.run_dir, "score.json"), "w") as f:
        json.dump(score, f, indent=2, default=str)
    with open(os.path.join(a.run_dir, "cbom.json"), "w") as f:
        json.dump(cbom(gt, probe, obs, cov), f, indent=2)
    write_report(a.run_dir, score)
    print(open(os.path.join(a.run_dir, "report.md")).read())


def write_report(run_dir, s):
    L = []
    o = s["discovery"]["overall"]
    L += ["# Testbed run report", "",
          "## Discovery accuracy (active probe vs declared configuration)", "",
          f"- Versions, groups, TLS 1.2 suites: precision {o['precision']:.3f}, recall {o['recall']:.3f}",
          f"- Served certificates correct (key and signature algorithm): {o['certs_correct']}",
          f"- Static certificates correct: {o['static_certs_correct']}", "",
          "| Listener | Groups P/R | TLS 1.2 suites P/R | TLS 1.2 groups P/R | Cert |", "|---|---|---|---|---|"]
    for r in s["discovery"]["listeners"]:
        g, c, t2 = r["groups"], r["tls12_ciphers"], r.get("tls12_groups")
        t2s = f"{t2['precision']:.2f}/{t2['recall']:.2f}" if t2 else "not probed"
        L.append(f"| {r['listener']} | {g['precision']:.2f}/{g['recall']:.2f} | "
                 f"{c['precision']:.2f}/{c['recall']:.2f} | {t2s} | {'ok' if r['cert_key_ok'] and r['cert_sig_ok'] else 'MISMATCH'} |")
    L += ["", "## Supported vs negotiated (server telemetry)", "",
          "| Listener | Supported (probe) | Negotiated share (logs) | Handshakes |", "|---|---|---|---|"]
    for r in s["supported_vs_negotiated"]:
        neg = ", ".join(f"{g} {v:.0%}" for g, v in r["negotiated"].items())
        L.append(f"| {r['listener']} | {', '.join(r['supported'])} | {neg} | {r['handshakes_logged']} |")
    L += ["", "## Passive capture agreement", "", "| Channel | Log groups | pcap groups | pcap handshakes | Agree |",
          "|---|---|---|---|---|"]
    for r in s["passive_agreement"]:
        L.append(f"| {r['channel']} | {', '.join(r['log_groups'])} | {', '.join(r['pcap_groups'])} | "
                 f"{r['pcap_handshakes']} | {r['agree']} |")
    L += ["", "## HNDL risk by data class", ""]
    for name, r in s["hndl"].items():
        L += [f"### {name}", "",
              f"- Endpoint view of origin: negotiated {', '.join(r['endpoint_view']) or 'n/a'}",
              f"- Labeled flow: {', '.join(r['labeled_channels'])}",
              f"- Inferred flow adds: {', '.join(r['inference_extra']) or 'nothing'}", "",
              "| Reading | Scenario | Local | Propagated (labeled) | Sunk | Remediable | Propagated (inferred) |",
              "|---|---|---|---|---|---|---|"]
        for reading in ("worst", "share"):
            for lab, v in r["scenarios"].items():
                v = v if reading == "worst" else v["share"]
                L.append(f"| {reading} | {lab} | {v['local']} | {v['labeled']} | {v['labeled_sunk']} | "
                         f"{v['labeled_remediable']} | {v['inferred']} |")
        L.append("")
    L += [f"## Remediation ranking ({s['scenario_for_rankings']}, fix one channel now)", "",
          "| Channel | Risk reduction (worst case) | Risk reduction (share-weighted) |", "|---|---|---|"]
    L += [f"| {r['channel']} | {r['risk_reduction']} | {r['risk_reduction_share']} |" for r in s["remediation"]]
    if s.get("readings"):
        rd = s["readings"]
        L += ["", (f"**Readings diverge:** the first fix is {rd['worst_first_fix']} under the worst-case reading "
                   f"and {rd['share_first_fix']} under the share-weighted reading." if rd["diverge"] else
                   f"The worst-case and share-weighted readings agree on the first fix ({rd['worst_first_fix']}).")]
    if s.get("actions"):
        L += ["", "## Remediation actions (gain per cost, worst-case reading)", "",
              "Removing a channel's classical fallback stops its classical sessions now. Recorded classical "
              "traffic stays sunk, so its risk effect equals migrating the channel now (the remediable part, "
              "Proposition 7(f)); it differs in cost, which here is the refused legacy share.", "",
              "| Action | Channel | Cost | Gain (worst) | Gain (share) | Gain / cost |", "|---|---|---|---|---|---|"]
        L += [f"| {x['action']} | {x['channel']} | {x['cost']} | {x['gain_worst']} | {x['gain_share']} | "
              f"{x['gain_per_cost_worst']} |" for x in s["actions"] if x["gain_worst"] > 0 or x["gain_share"] > 0]
    if s.get("complementarity"):
        L += ["", "## Complementarity (gap = g(e, f) - g(e) - g(f); positive means fixing one raises the other's value)", ""]
        for r, v in s["complementarity"].items():
            pairs = ", ".join(f"{p['pair'][0]} + {p['pair'][1]}: {p['gap']}" for p in v["complementary_pairs"][:5])
            L.append(f"- {r}: max gap {v['max_gap']}" + (f"; complementary pairs: {pairs}" if pairs else ""))
    if s.get("uncertainty"):
        u = s["uncertainty"]
        L += ["", f"## Uncertainty ({u['draws']} draws, T_Q ~ {u['prior']}, {u['grid_points']}-point grid)", "",
              "The ranking is recomputed for each draw of the uncertain parameters (C, L, O, t_fix, H as "
              "specified in groundtruth.json). P(top-1) and P(top-k) are over draws in which some channel has "
              f"a positive gain. {u['note'].capitalize()}. Rule: {u['rule']}.", ""]
        for r, v in u["readings"].items():
            L += [f"### {r} reading: robust first fix {v['robust_first_fix']} (point estimate: {v['point_first_fix']}; "
                  f"draws with no positive gain: {v['draws_with_zero_gain']})", "",
                  f"| Channel | Point gain | Mean gain | 90% interval | P(top-1) | P(top-{u['k']}) |", "|---|---|---|---|---|---|"]
            L += [f"| {c['channel']} | {c['point_gain']} | {c['mean_gain']} | {c['ci90'][0]}–{c['ci90'][1]} | "
                  f"{c['p_top1']} | {c['p_topk']} |" for c in v["channels"] if c["p_topk"] > 0 or c["mean_gain"] > 0]
            L.append("")
        L.append("**Robust first fixes diverge between readings.**" if u["readings_diverge"]
                 else "Robust first fixes agree between readings.")
    if s.get("coverage"):
        c = s["coverage"]
        L += ["", "## Coverage", "",
              f"- Data classes with labeled flows: {c['classes_with_labels']:.0%}",
              f"- Labeled share of inferred flow channels: {c['labeled_fraction_of_inferred']:.0%}",
              f"- Flow channels with negotiation telemetry: {c['channels_with_negotiation_data']:.0%}",
              f"- Channels with an unattributed caller: {c['unknown_channels']}; residual risk if they carried "
              f"the classes of their server: {c['residual_unknown_risk']}"]
    if s.get("prior_sensitivity"):
        rows = s["prior_sensitivity"]
        cls = list(rows[0]["hndl"])
        L += ["", "## CRQC-arrival prior x T_PQ sensitivity (propagated risk)", "",
              "| Prior | T_PQ | " + " | ".join(f"{d} worst | {d} share" for d in cls) + " |",
              "|---|---|" + "---|---|" * len(cls)]
        L += [f"| {r['prior']} | {r['T_PQ']} | " + " | ".join(f"{r['hndl'][d]['worst']} | {r['hndl'][d]['share']}" for d in cls)
              + " |" for r in rows]
    L += ["", f"## TNFL ({s['scenario_for_rankings']})", "", "| Key | Acceptance horizon τ | Forgery window S | Quantum-vulnerable |",
          "|---|---|---|---|"]
    for k, v in sorted(s["tnfl"]["keys"].items()):
        L.append(f"| {k} | {v['tau']} | {v['S']:.2f} | {v['quantum_vulnerable']} |")
    for art, v in s["tnfl"]["artifacts"].items():
        L += ["", f"- {art}: chain {' → '.join(v['chain'])}; R_T = {v['R_T']:.2f}; dominant key: {v['dominant_key']}"]
    if s.get("pq_sensitivity"):
        L += ["", f"## Sensitivity to post-quantum breaks ({s['scenario_for_rankings']})", "",
              "| T_PQ | " + " | ".join(f"{d} worst | {d} share" for d in s["pq_sensitivity"][0]["hndl"]) +
              " | " + " | ".join(f"S({k})" for k in sorted(s["pq_sensitivity"][0]["tnfl"])) + " |",
              "|---" * (1 + 2 * len(s["pq_sensitivity"][0]["hndl"]) + len(s["pq_sensitivity"][0]["tnfl"])) + "|"]
        for r in s["pq_sensitivity"]:
            L.append(f"| {r['T_PQ']} | " + " | ".join(f"{v['worst']} | {v['share']}" for v in r["hndl"].values()) +
                     " | " + " | ".join(str(r["tnfl"][k]) for k in sorted(r["tnfl"])) + " |")
    if s.get("ssh_plane"):
        sp = s["ssh_plane"]
        L += ["", f"## SSH plane ({s['scenario_for_rankings']})", ""]
        L += [f"- Discovery {d['listener']}: key exchange precision {d['kex']['precision']:.3f}, "
              f"recall {d['kex']['recall']:.3f}" for d in sp["discovery"]]
        L += ["", "| Channel | Negotiated (pcap) | Connections |", "|---|---|---|"]
        L += [f"| {c['channel']} | {', '.join(f'{k} {v:.0%}' for k, v in c['negotiated_pcap'].items())} | "
              f"{c['connections_pcap']} |" for c in sp["channels"]]
        L += [f"- sshd log vs captures at {a['listener']}: {a['agree']} (pcap {a['pcap']}, log {a['log']})"
              for a in sp["log_agreement"]]
        for name, r in sp["risk"].items():
            for reading, v in r.items():
                L.append(f"- {name} ({reading}): R = {v['R']}, sunk = {v['sunk']}, fix one now: "
                         + ", ".join(f"{k} {g}" for k, g in v["fix_one"].items()))
    if s["ssh"]:
        L += ["", "## SSH key exchange", ""]
        L += [f"- {r['host']}: {', '.join(r['kex_algorithms'])}" for r in s["ssh"]]
    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
