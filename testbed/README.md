# PQC topology testbed

A small, reproducible estate for evaluating the paper *Topological Post-Quantum
Cryptography Discovery*. It runs the discovery pipeline of §9 against services
with a known, declared configuration, then applies the paper's HNDL and TNFL
model to what was discovered.

The same configuration runs in two ways:

* **Local Docker:** one machine, about 3 minutes.
* **Hetzner Cloud:** six small servers on a real private network, with a real
  public path to the gateway, about 30–45 minutes.

## Estate

```
client ──443──▶ gw ──8443──▶ lb ──9443──▶ appa ──7443──▶ data      (records, L=15)
(internet)                                  ▲ │
                                            │ └──9444──▶ appb      (profile, L=8)
                                            └── /callback (cycle)
```

| Listener | Key exchange | Certificate | Purpose in the evaluation |
|---|---|---|---|
| gw:443 | X25519MLKEM768, X25519, P-256 (TLS 1.2/1.3) | ECDSA P-256 | Edge supports hybrid; legacy clients still negotiate X25519 |
| lb:8443 | TLS 1.2 RSA key transport only | RSA-2048 | No forward secrecy, Shor-vulnerable |
| appa:9443, appb:9444 | X25519 only, mutual TLS | ECDSA P-256 | Vulnerable internal hops; the call cycle tests fixpoint propagation |
| data:7443 | X25519MLKEM768 only | ML-DSA-65 | Quantum-safe hop at the data origin |

PKI: an RSA-4096 legacy root that is never rotated issues an ECDSA intermediate,
which issues the leaf certificates and a firmware-signing key. The firmware is
CMS-signed. A separate ML-DSA-65 root issues the `data` certificate. Clients are
curl on OpenSSL 3.5 (modern) and on OpenSSL 1.1.1 (legacy).

`groundtruth.json` declares all of this, together with the model's inputs:
criticality, lifetime, observability, remediation time, history and
acceptance-horizon parameters. These inputs are assumptions, not measurements.

## What a run measures

| Output | Source | Paper |
|---|---|---|
| Discovery precision and recall (versions, groups, TLS 1.2 suites and ECDHE groups, certificates) | `tools/probe.py`, active handshakes only | §9, §13 |
| Supported vs negotiated groups per listener | probe vs nginx `$ssl_curve` telemetry | §9 |
| Agreement between server logs and packet captures | tcpdump + tshark | §9 |
| HNDL risk per data class: local, propagated (labeled and inferred), sunk, remediable, under the worst-case and share-weighted readings | `tools/score.py` | §6, §6.6, §10.1 |
| Remediation ranking (fix one channel now), under both readings | `tools/score.py` | §8, §13.5 |
| TNFL acceptance horizons, forgery windows and firmware risk | static scan + trust parameters | §7, §10.2 |
| Sensitivity to a finite post-quantum break time `T_PQ` (`scenarios.T_PQ_points`) | `tools/score.py` | §6.5, §13.7 |
| SSH key exchange offered, and negotiated per channel on the local SSH plane | nmap `ssh2-enum-algos`; KEXINIT in captures (`tools/extract_ssh.sh`) and sshd log | §9, §13.8 |
| CycloneDX 1.6 CBOM with `dytallix:*` properties | `results/<run>/cbom.json` | §9 |

Each run writes `report.md`, `score.json` and `cbom.json` to `results/<run>/`.

## Local run

Requires Docker and Python 3.

```bash
make local-run RUN=local-1 SECONDS_WINDOW=120
```

## Hetzner run

Requires Terraform ≥ 1.5, jq, rsync, an SSH key and a Hetzner Cloud API token.

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars   # set admin_cidrs to your IP
export HCLOUD_TOKEN=...                                             # token for the target project
make cloud-plan                  # review: 6 servers, 1 network, 2 firewalls, 1 SSH key
make cloud-up                    # creates the servers (billed hourly from here on)
make cloud-deploy                # waits for boot, copies files, builds images, starts services
make cloud-run RUN=hetzner-1 MINUTES=15
make cloud-destroy               # deletes everything this testbed created
```

Check that `server_type` (default `cx23`) is still offered with
`hcloud server-type list`, and override it in `terraform.tfvars` if not.

### Running alongside other Hetzner workloads

The testbed is safe to run in parallel with other servers in the same account:

* It creates only its own resources, all named `pqc-topo-*` and labelled
  `testbed=pqc-topology`. It never lists, reads or changes other servers.
  `cloud-destroy` removes only what is in its own Terraform state.
* Its private network is used only by its own servers, so an overlapping
  address range in another network is harmless.
* Probes and traffic stay inside the testbed: the gateway's port 443 accepts
  only the client server, and all other listeners are reachable only on the
  testbed's private network. Nothing scans outside hosts, as Hetzner's terms
  require.

Two things to check before starting:

* **Project server limit.** Six more servers must fit within your project's
  limit.
* **Isolation.** Preferably use a separate Hetzner Cloud project with its own
  token, so the testbed cannot affect production by mistake.
* **SSH key already registered.** If your public key is already registered in
  the same project (for example for other servers), Hetzner may refuse to
  register it again. In that case set `existing_ssh_key_name` in
  `terraform.tfvars` to reuse it.

## Synthetic topologies

`make synth` (Python 3 with numpy and scipy, about 1.5 minutes) runs the experiments of
§13.9 on generated estates and writes `results/synth/summary.json`:

* `validate`: the synthetic engine reproduces the testbed scores (Tables 6 and 7).
* `fixpoint`: Appendix A, naive iteration and brute-force reachability agree.
* `scaling`: running time of Appendix A up to 100,000 services.
* `inference`: precision and risk overstatement of inferred flows.
* `stability`: rank stability under parameter noise, alternative T_Q priors, and the two readings.
* `greedy`: greedy and group-aware selection against exhaustive search.

All runs are seeded. Use `--only NAME` to run one experiment and `--quick` for a smoke test.

## Tests linking the proofs to the code

`make test` (pytest and hypothesis) runs `tests/test_properties.py`. Each test checks the
statement of one Lean theorem in `../lean/TopoPQC.lean` on random inputs, against the
scorer (`tools/score.py`) or the synthetic engine (`synth/engine.py`). The test vectors in
`tests/vectors.json` are both proved in Lean (theorems `vec_*`, generated by
`tests/gen_lean_vectors.py`) and checked against the scorer. A test fails if the
generated Lean block is out of date.

## Security notes

* All keys are throwaway test keys generated by `make pki`. Each server receives
  only its own private keys. The probe reads certificates and signatures, never
  keys.
* SSH is open only to `admin_cidrs`. Host keys are recorded in
  `.ssh_known_hosts` inside this directory, not in `~/.ssh`.

## Limitations

* **Not a real enterprise.** The estate is small and synthetic, and traffic is
  deterministic.
* **Assumed parameters.** Observability and other model parameters are declared
  inputs, not measured.
* **No IPsec.** IPsec discovery is not yet included.
* **SSH plane is local only.** The local estate adds an SSH server on `data` and backup
  pulls from `appb` (OpenSSH 10) and a legacy `ops` host (OpenSSH 8.x); the Hetzner
  deployment does not. SSH channels are scored as their own data class.
