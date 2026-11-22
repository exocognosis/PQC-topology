#!/usr/bin/env python3
"""Active discovery for the PQC topology testbed.

Runs inside the pqc-nginx image (OpenSSL 3.5). For every listener in the
ground-truth file it determines, using only handshakes and public data:
  * supported TLS versions,
  * supported TLS 1.3 key-exchange groups (one handshake per candidate group),
  * supported TLS 1.2 cipher suites (one handshake per candidate suite),
  * supported TLS 1.2 ECDHE groups (one handshake per candidate group),
  * the served leaf certificate (key and signature algorithms, validity).
It also parses certificates and CMS signatures found in a static artifact
directory (never private keys), and optionally SSH key-exchange algorithms.

Discovery uses the listener list only to know where to look; it does not read
the declared groups or ciphers, so the scorer can compare them fairly.
"""
import argparse
import glob
import json
import os
import re
import subprocess

GROUPS = ["X25519MLKEM768", "SecP256r1MLKEM768", "SecP384r1MLKEM1024", "X25519", "X448",
          "prime256v1", "secp384r1", "secp521r1", "ffdhe2048", "ffdhe3072"]
TLS12_GROUPS = ["X25519", "X448", "prime256v1", "secp384r1", "secp521r1"]
TLS12_CIPHERS = ["ECDHE-ECDSA-AES256-GCM-SHA384", "ECDHE-ECDSA-AES128-GCM-SHA256",
                 "ECDHE-ECDSA-CHACHA20-POLY1305", "ECDHE-ECDSA-AES256-SHA384",
                 "ECDHE-RSA-AES256-GCM-SHA384", "ECDHE-RSA-AES128-GCM-SHA256",
                 "AES256-GCM-SHA384", "AES128-GCM-SHA256", "AES256-SHA", "AES128-SHA",
                 "DES-CBC3-SHA"]


def s_client(host, port, extra, timeout=8):
    cmd = ["openssl", "s_client", "-connect", f"{host}:{port}", "-servername", host,
           "-brief"] + extra
    try:
        p = subprocess.run(cmd, input=b"", capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, ""
    text = (p.stdout + p.stderr).decode(errors="replace")
    return "CONNECTION ESTABLISHED" in text, text


def parse_x509_text(text):
    def grab(pattern):
        m = re.search(pattern, text, re.M)
        return m.group(1).strip() if m else None
    key_alg = grab(r"Public Key Algorithm:\s*(.+)$")
    bits = grab(r"Public-Key:\s*\((\d+) bit")
    curve = grab(r"NIST CURVE:\s*(\S+)") or grab(r"ASN1 OID:\s*(\S+)")
    if key_alg == "rsaEncryption" and bits:
        key = f"RSA-{bits}"
    elif key_alg == "id-ecPublicKey":
        key = {"P-256": "EC-P256", "prime256v1": "EC-P256", "P-384": "EC-P384",
               "secp384r1": "EC-P384"}.get(curve or "", f"EC-{curve}")
    else:
        key = key_alg
    return {
        "subject": grab(r"Subject:\s*(.+)$"),
        "issuer": grab(r"Issuer:\s*(.+)$"),
        "key": key,
        "sig": grab(r"Signature Algorithm:\s*(.+)$"),
        "not_after": grab(r"Not After\s*:\s*(.+)$"),
        "is_ca": "CA:TRUE" in text,
    }


def cert_from_pem(pem_text):
    p = subprocess.run(["openssl", "x509", "-noout", "-text"], input=pem_text.encode(),
                       capture_output=True)
    return parse_x509_text(p.stdout.decode(errors="replace"))


def served_cert(host, port):
    cmd = ["openssl", "s_client", "-connect", f"{host}:{port}", "-servername", host,
           "-showcerts"]
    try:
        p = subprocess.run(cmd, input=b"", capture_output=True, timeout=8)
    except subprocess.TimeoutExpired:
        return None
    out = p.stdout.decode(errors="replace")
    m = re.search(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", out, re.S)
    return cert_from_pem(m.group(0)) if m else None


def probe_listener(host, port):
    res = {"host": host, "port": port, "reachable": False, "tls_versions": [],
           "groups": [], "tls12_ciphers": [], "tls12_groups": [], "cert": None}
    for ver, flag in (("TLSv1.2", "-tls1_2"), ("TLSv1.3", "-tls1_3")):
        ok, _ = s_client(host, port, [flag])
        if ok:
            res["tls_versions"].append(ver)
    res["reachable"] = bool(res["tls_versions"])
    if "TLSv1.3" in res["tls_versions"]:
        for g in GROUPS:
            ok, _ = s_client(host, port, ["-tls1_3", "-groups", g])
            if ok:
                res["groups"].append(g)
    if "TLSv1.2" in res["tls_versions"]:
        for c in TLS12_CIPHERS:
            ok, _ = s_client(host, port, ["-tls1_2", "-cipher", c + ":@SECLEVEL=0"])
            if ok:
                res["tls12_ciphers"].append(c)
    if res["reachable"]:
        res["cert"] = served_cert(host, port)
    if any(c.startswith("ECDHE") for c in res["tls12_ciphers"]):
        # In TLS 1.2 the supported-groups list also restricts the curves of an ECDSA
        # certificate (RFC 8422), so a lone candidate group can fail for that reason alone.
        # Offer the candidate first and the certificate's curve second, then read which
        # group the server actually used for the ephemeral key.
        cert_curve = {"EC-P256": "prime256v1", "EC-P384": "secp384r1"}.get((res["cert"] or {}).get("key"))
        for g in TLS12_GROUPS:
            offer = g if cert_curve in (None, g) else f"{g}:{cert_curve}"
            ok, text = s_client(host, port, ["-tls1_2", "-groups", offer, "-cipher", "ECDHE:@SECLEVEL=0"])
            m = re.search(r"Temp Key:\s*(.+)", text)
            if ok and m and re.search(rf"\b{re.escape(g)}\b", m.group(1)):
                res["tls12_groups"].append(g)
    return res


def static_scan(directory):
    certs, signatures = {}, {}
    for path in sorted(glob.glob(os.path.join(directory, "*.pem"))):
        name = os.path.basename(path)[:-4]
        if name.endswith(".chain") or name == "clientca":
            continue  # bundles duplicate individual certificates
        with open(path) as f:
            text = f.read()
        if "BEGIN CERTIFICATE" not in text:
            continue  # never read private keys
        certs[name] = cert_from_pem(text)
    for path in sorted(glob.glob(os.path.join(directory, "*.p7s"))):
        p = subprocess.run(["openssl", "cms", "-cmsout", "-print", "-inform", "DER", "-in", path],
                           capture_output=True)
        text = p.stdout.decode(errors="replace")
        sig = re.findall(r"signatureAlgorithm:\s*\n\s*algorithm:\s*(\S+)", text)
        dig = re.findall(r"digestAlgorithm:\s*\n\s*algorithm:\s*(\S+)", text)
        q = subprocess.run(["openssl", "pkcs7", "-inform", "DER", "-in", path, "-print_certs",
                            "-noout"], capture_output=True)
        subjects = re.findall(r"subject=(.+)", q.stdout.decode(errors="replace"))
        signatures[os.path.basename(path)] = {
            "signature_algorithms": sorted(set(sig)),
            "digest_algorithms": sorted(set(dig)),
            "embedded_cert_subjects": subjects,
        }
    return {"certs": certs, "signatures": signatures}


def ssh_scan(host):
    p = subprocess.run(["nmap", "-Pn", "-p", "22", "--script", "ssh2-enum-algos", host],
                       capture_output=True, timeout=60)
    text = p.stdout.decode(errors="replace")
    m = re.search(r"kex_algorithms: \(\d+\)\n((?:\|\s+\S+\n)+)", text)
    kex = re.findall(r"\|\s+(\S+)", m.group(1)) if m else []
    return {"host": host, "kex_algorithms": kex}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groundtruth", required=True)
    ap.add_argument("--static-dir")
    ap.add_argument("--ssh", nargs="*", default=[], help="hosts to scan for SSH KEX")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(a.groundtruth) as f:
        gt = json.load(f)
    out = {"listeners": {}, "static": None, "ssh": []}
    for lst in gt["listeners"]:
        key = f'{lst["host"]}:{lst["port"]}'
        out["listeners"][key] = probe_listener(lst["host"], lst["port"])
        print(key, out["listeners"][key]["tls_versions"], out["listeners"][key]["groups"],
              out["listeners"][key]["tls12_ciphers"], flush=True)
    if a.static_dir:
        out["static"] = static_scan(a.static_dir)
    for h in a.ssh:
        out["ssh"].append(ssh_scan(h))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
