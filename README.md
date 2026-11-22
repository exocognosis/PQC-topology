# PQC Topology: post-quantum migration risk from your network graph

[![CI](https://github.com/exocognosis/PQC-topology/actions/workflows/ci.yml/badge.svg)](https://github.com/exocognosis/PQC-topology/actions/workflows/ci.yml)
[![Code license: Apache-2.0](https://img.shields.io/badge/code-Apache--2.0-blue.svg)](LICENSE)
[![Paper license: CC BY 4.0](https://img.shields.io/badge/paper-CC%20BY%204.0-lightgrey.svg)](LICENSE-paper.md)
[![Proofs: Lean 4 + Mathlib](https://img.shields.io/badge/proofs-Lean%204%20%2B%20Mathlib-purple.svg)](lean/)

Which connection should you migrate to post-quantum cryptography first? This repository
answers that with a typed graph model of **harvest-now-decrypt-later (HNDL)** and
**trust-now-forge-later (TNFL)** risk. It turns a cryptographic inventory (which services
talk to which, over which key exchange, carrying which data) into exposure windows, a split
between sunk and remediable risk, and a ranked migration plan.

It contains the paper, machine-checked proofs of its results, a reproducible TLS/SSH testbed
with ML-KEM, and a small tool for scoring your own estate.

**Author:** Rick Glenn, Technical Cofounder, Dytallix, Inc.

## Who this is for

* **Security architects and PQC migration leads** who have a cryptographic inventory or
  CBOM and need to decide what to fix first, and to explain why.
* **Researchers** working on quantum risk models, Mosca's inequality, or crypto-agility.
* **Tool builders** who want a formally specified scoring model to put behind discovery
  data.

## What it tells you that a flat inventory does not

* **Data travels.** A database link that already uses ML-KEM does not protect records that
  leave over a classical hop further along the path. Risk follows the data flow through
  the graph, including cycles.
* **Some risk is already sunk.** Traffic recorded before you migrate stays decryptable
  later. The model separates that part from the part migration can still remove
  (a windowed form of Mosca's inequality).
* **"Supports PQC" is not "uses PQC".** In the testbed, a gateway with hybrid
  X25519MLKEM768 enabled still negotiated classical X25519 for 26–27% of handshakes, and a
  legacy SSH client negotiated classical key exchange with a server that offers ML-KEM.
  Weighting by measured session shares changed which channel should be fixed first.
* **Short-lived secrets are not an HNDL problem; long-lived data is.** Data lifetime enters
  every window, so session tokens and 15-year records rank very differently on the same link.
* **Fixes interact.** Fixing one hop on a path can be worth nothing until the others are
  fixed too, so greedy "biggest single win" plans can be far from optimal. The tooling
  reports these complementarities.

## Score your own estate (5 minutes)

Describe your services, channels (with measured key-exchange shares if you have them) and
data classes in a JSON file like [`examples/estate.json`](examples/estate.json), then:

```bash
pip install numpy
python3 examples/estate_risk.py examples/estate.json
```

```
class                  worst    sunk   share    sunk  channels
customer-records       2.741   2.250   1.470   0.750  edge<-internet, api<-edge, ...
session-tokens         0.000   0.000   0.000   0.000  edge<-internet, api<-edge, auth<-api
partner-orders         0.180   0.020   0.180   0.020  db<-orders, orders<-partner

worst-case reading                share-weighted reading
orders<-partner          0.324    orders<-partner          0.650
edge<-internet           0.251    edge<-internet           0.000
...
```

Inputs per channel: observability `O` (how likely an adversary records it), years to fix
`t_fix`, years of history already exposed `H`, and session shares by key exchange
(`classical`, `hybrid`, `broken`). Per data class: origin service, criticality `C`, secrecy
lifetime `L` in years, and flow direction (`read`, `write` or `both`). The CRQC arrival time
is a prior (`point`, `uniform` or `shifted-exponential`), not a single guess. All of these
are assumptions you should vary; the testbed shows how rankings respond to errors in them.

## Contents

| Path | What it is |
|---|---|
| [`topological-pqc-discovery.html`](topological-pqc-discovery.html) | The paper (source of truth) |
| [`Topological-PQC-Discovery.pdf`](Topological-PQC-Discovery.pdf) | The paper as a single-column PDF |
| [`ieee/`](ieee/) | IEEE conference version: `paper.tex`, `paper.pdf`, and `build_tex.py`, which generates the LaTeX from the HTML |
| [`examples/`](examples/) | `estate_risk.py`: score your own estate from a JSON inventory |
| [`lean/`](lean/) | Lean 4 + Mathlib proofs of the formal results (45 theorems; Appendix C of the IEEE version) |
| [`testbed/`](testbed/) | Reproducible testbed: local Docker or Hetzner Cloud estate (nginx + OpenSSL 3.5 with ML-KEM, OpenSSH 10), discovery probe, scorer, CBOM output, run results |
| [`testbed/synth/`](testbed/synth/) | Synthetic-topology experiments: scaling, flow inference, rank stability, uncertainty, remediation planning |
| [`testbed/tests/`](testbed/tests/) | Property tests linking each Lean theorem to the scorer and engine code |
| [`testbed/tools/analysis.py`](testbed/tools/analysis.py) | Uncertainty-aware ranking, cost-aware remediation actions, complementarity, coverage, CRQC-prior sensitivity |

## Main results

* **Model.** Primitives are classified by break time; HNDL exposure is a window of recorded
  traffic that recovers Mosca's inequality and splits risk into sunk and remediable parts;
  TNFL risk propagates down the trust graph. Channels that negotiate a mix of
  configurations are scored by measured session shares.
* **Proofs.** Lemmas 1–2, Propositions 1–4 and 6–8 and Corollary 1 are machine-checked in
  Lean 4 (only the standard axioms; no `sorry`).
* **Testbed.** On a local estate and on six Hetzner Cloud servers, discovery recovers the
  deployed configuration exactly, and outputs a CycloneDX-style CBOM.
* **Synthetic estates.** Propagation handles 100,000 services in under a second; rankings
  tolerate about 10% error in declared parameters but not 25%. Inferring flows from
  read paths alone misses write flows entirely; typed flows restore them.

## Reproducing

Requirements: Docker and Python 3 (with `numpy`, `scipy`, `pytest`, `hypothesis` for the
experiments and tests); Terraform, `jq`, `rsync` and a Hetzner Cloud token for cloud runs;
[elan](https://github.com/leanprover/elan) for Lean; [Tectonic](https://tectonic-typesetting.github.io/) for the IEEE PDF.

```bash
cd testbed
make local-run RUN=local-1 SECONDS_WINDOW=120   # local estate, ~3 minutes
make synth                                      # synthetic experiments, ~3.5 minutes
make test                                       # property tests (Lean statements vs code)
python3 tools/score.py results/local-1          # rescore a run: dual readings, uncertainty, actions, coverage
```

Cloud runs are described in [`testbed/README.md`](testbed/README.md).

```bash
cd lean && lake exe cache get && lake build     # Lean proofs (pins Mathlib d13f23b7)
```

The proofs were checked with Lean 4 v4.34.1 against Mathlib commit
`d13f23b723b8a846827a245b89c10fc7d3f11612`, which `lean/lakefile.toml` pins.

```bash
python3 ieee/build_tex.py && (cd ieee && tectonic paper.tex)   # IEEE PDF from the HTML
```

## Related standards and terms

NIST FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA); hybrid key exchange
X25519MLKEM768 in TLS 1.3 and `mlkem768x25519-sha256` in SSH; cryptographic bills of
materials (CBOM); crypto-agility; Mosca's theorem; harvest now, decrypt later; store now,
decrypt later (SNDL).

## Status and contributing

This is a working draft. The HTML version includes an editor's note (hidden in print)
listing the remaining pre-submission items. Questions, field data on key-exchange shares and
counterexamples are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md), or start a
[discussion](https://github.com/exocognosis/PQC-topology/discussions).

## Citation

Use GitHub's **Cite this repository** button (from [`CITATION.cff`](CITATION.cff)), or:

```bibtex
@misc{glenn2026topopqc,
  author = {Rick Glenn},
  title  = {Topological Post-Quantum Cryptography Discovery: A Typed Graph Model of
            Harvest-Now and Forge-Later Risk, with Exposure Windows, Break-Time
            Semantics, and Remediation Planning},
  year   = {2026},
  howpublished = {\url{https://github.com/exocognosis/PQC-topology}}
}
```

## License

Code, scripts, configuration, Lean proofs and data: [Apache License 2.0](LICENSE).
Paper text and figures: [CC BY 4.0](LICENSE-paper.md).
