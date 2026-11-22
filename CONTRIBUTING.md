# Contributing

Issues, questions and pull requests are welcome, especially from people planning or running
a post-quantum migration.

## Useful contributions

* **Field data.** Measured key-exchange shares (how often a PQC-capable endpoint still
  negotiates classical X25519/ECDHE/RSA) from real estates, anonymized. The model's ranking
  depends on these shares, and published numbers are scarce.
* **Discovery adapters.** Readers for other sources of handshake data (load-balancer logs,
  Zeek `ssl.log`/`ssh.log`, cloud flow logs, CBOM files) that produce channel shares.
* **Model questions.** If a definition or proposition does not fit an estate you know, open
  an issue with the case. Counterexamples are as useful as code.
* **Proofs.** The paper results that are not yet formalized are listed in Table 13 of the
  paper (Appendix C of the IEEE version).

## Before opening a pull request

```bash
cd testbed && make test lint        # property tests and lint
python3 examples/estate_risk.py examples/estate.json
cd lean && lake build               # if you touched the proofs
```

* Keep seeded results reproducible: do not change the default seeds or the
  `results/` snapshots unless the change is the point of the PR.
* A change to a definition in the paper must keep the Lean statement and the property test
  that links it to the code in step (`testbed/tests/`).
* Do not commit packet captures, operator logs, tokens or real addresses from your estate.

By contributing you agree that code is licensed under Apache-2.0 and paper text under
CC BY 4.0, as in the rest of the repository.
