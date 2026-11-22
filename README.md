# Topological Post-Quantum Cryptography Discovery

A typed graph model of harvest-now-decrypt-later (HNDL) and trust-now-forge-later (TNFL)
risk for post-quantum migration, with exposure windows, break-time semantics and
remediation planning. This repository contains the paper, its machine-checked proofs,
and the testbed and experiments that evaluate it.

**Author:** Rick Glenn, Technical Cofounder, Dytallix, Inc.

## Contents

| Path | What it is |
|---|---|
| [`topological-pqc-discovery.html`](topological-pqc-discovery.html) | The paper (source of truth) |
| [`Topological-PQC-Discovery.pdf`](Topological-PQC-Discovery.pdf) | The paper as a single-column PDF |
| [`ieee/`](ieee/) | IEEE conference version: `paper.tex`, `paper.pdf`, and `build_tex.py`, which generates the LaTeX from the HTML |
| [`lean/`](lean/) | Lean 4 + Mathlib proofs of the formal results (45 theorems; Appendix C of the IEEE version) |
| [`testbed/`](testbed/) | Reproducible testbed: local Docker or Hetzner Cloud estate, discovery probe, scorer, run results |
| [`testbed/synth/`](testbed/synth/) | Synthetic-topology experiments (scaling, inference precision, rank stability, greedy vs optimal) |
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
  deployed configuration exactly. A gateway that supports hybrid ML-KEM still negotiates
  classical X25519 for 26–27% of handshakes, and a legacy SSH client negotiates classical
  key exchange with a server that offers ML-KEM. Weighting exposure by measured shares
  reverses which channel should be fixed first.
* **Synthetic estates.** Propagation handles 100,000 services in under a second; rankings
  tolerate about 10% error in declared parameters but not 25%.

## Reproducing

Requirements: Docker and Python 3 (with `numpy`, `scipy`, `pytest`, `hypothesis` for the
experiments and tests); Terraform, `jq`, `rsync` and a Hetzner Cloud token for cloud runs;
[elan](https://github.com/leanprover/elan) for Lean; [Tectonic](https://tectonic-typesetting.github.io/) for the IEEE PDF.

```bash
cd testbed
make local-run RUN=local-1 SECONDS_WINDOW=120   # local estate, ~3 minutes
make synth                                      # synthetic experiments, ~1.5 minutes
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

## Status

This is a working draft. The HTML version includes an editor's note (hidden in print)
listing the remaining pre-submission items.

## Citation

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
