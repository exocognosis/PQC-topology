# Testbed run report

## Discovery accuracy (active probe vs declared configuration)

- Versions, groups, TLS 1.2 suites: precision 1.000, recall 1.000
- Served certificates correct (key and signature algorithm): 5/5
- Static certificates correct: 10/10

| Listener | Groups P/R | TLS 1.2 suites P/R | TLS 1.2 groups P/R | Cert |
|---|---|---|---|---|
| gw:443 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | ok |
| lb:8443 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | ok |
| appa:9443 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | ok |
| appb:9444 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | ok |
| data:7443 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | ok |

## Supported vs negotiated (server telemetry)

| Listener | Supported (probe) | Negotiated share (logs) | Handshakes |
|---|---|---|---|
| gw:443 | X25519MLKEM768, X25519, prime256v1 | X25519MLKEM768 74%, X25519 26% | 477 |
| lb:8443 | (TLS 1.2 RSA kex) | TLSv1.2 AES256-GCM-SHA384 100% | 477 |
| appa:9443 | X25519 | X25519 100% | 636 |
| appb:9444 | X25519 | X25519 100% | 318 |
| data:7443 | X25519MLKEM768 | X25519MLKEM768 100% | 158 |

## Passive capture agreement

| Channel | Log groups | pcap groups | pcap handshakes | Agree |
|---|---|---|---|---|
| appa->appb | X25519 | X25519 | 159 | yes |
| appa->lb | X25519 | X25519 | 477 | yes |
| appb->appa | X25519 | X25519 | 318 | yes |
| data->appa | X25519MLKEM768 | X25519MLKEM768 | 158 | yes |
| gw->client | X25519, X25519MLKEM768 | X25519, X25519MLKEM768 | 477 | yes |
| lb->gw | - | - | 477 | yes |

## HNDL risk by data class

### records

- Endpoint view of origin: negotiated X25519MLKEM768
- Labeled flow: data->appa, appa->lb, lb->gw, gw->client
- Inferred flow adds: appa->appb, appb->appa

| Reading | Scenario | Local | Propagated (labeled) | Sunk | Remediable | Propagated (inferred) |
|---|---|---|---|---|---|---|
| worst | T_Q=5 | 0.0 | 11.0 | 10.0 | 1.0 | 11.0 |
| worst | T_Q=10 | 0.0 | 6.0 | 5.0 | 1.0 | 6.0 |
| worst | T_Q=15 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 |
| worst | E[T_Q~U(5,20)] | 0.0 | 4.067 | 3.334 | 0.733 | 4.067 |
| share | T_Q=5 | 0.0 | 6.0 | 5.0 | 1.0 | 6.0 |
| share | T_Q=10 | 0.0 | 3.5 | 2.5 | 1.0 | 3.5 |
| share | T_Q=15 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 |
| share | E[T_Q~U(5,20)] | 0.0 | 2.4 | 1.667 | 0.733 | 2.4 |

### profile

- Endpoint view of origin: negotiated X25519
- Labeled flow: appb->appa, appa->lb, lb->gw, gw->client
- Inferred flow adds: appa->appb

| Reading | Scenario | Local | Propagated (labeled) | Sunk | Remediable | Propagated (inferred) |
|---|---|---|---|---|---|---|
| worst | T_Q=5 | 0.3 | 2.4 | 1.8 | 0.6 | 2.4 |
| worst | T_Q=10 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| worst | T_Q=15 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| worst | E[T_Q~U(5,20)] | 0.05 | 0.34 | 0.18 | 0.16 | 0.34 |
| share | T_Q=5 | 0.3 | 1.5 | 0.9 | 0.6 | 1.5 |
| share | T_Q=10 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| share | T_Q=15 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| share | E[T_Q~U(5,20)] | 0.05 | 0.25 | 0.09 | 0.16 | 0.25 |

## Remediation ranking (E[T_Q~U(5,20)], fix one channel now)

| Channel | Risk reduction (worst case) | Risk reduction (share-weighted) |
|---|---|---|
| gw->client | 0.68 | 0.0 |
| lb->gw | 0.03 | 0.733 |
| appa->appb | 0.0 | 0.0 |
| appa->lb | 0.0 | 0.0 |
| appb->appa | 0.0 | 0.0 |
| data->appa | 0.0 | 0.0 |

**Readings diverge:** the first fix is gw->client under the worst-case reading and lb->gw under the share-weighted reading.

## Remediation actions (gain per cost, worst-case reading)

Removing a channel's classical fallback stops its classical sessions now. Recorded classical traffic stays sunk, so its risk effect equals migrating the channel now (the remediable part, Proposition 7(f)); it differs in cost, which here is the refused legacy share.

| Action | Channel | Cost | Gain (worst) | Gain (share) | Gain / cost |
|---|---|---|---|---|---|
| remove_fallback | gw->client | 0.258 | 0.68 | 0.0 | 2.637 |
| migrate | gw->client | 1.0 | 0.68 | 0.0 | 0.68 |
| migrate | lb->gw | 1.0 | 0.03 | 0.733 | 0.03 |

## Complementarity (gap = g(e, f) - g(e) - g(f); positive means fixing one raises the other's value)

- worst: max gap 0.091; complementary pairs: gw->client + lb->gw: 0.091, appa->lb + lb->gw: 0.021
- share: max gap 0.128; complementary pairs: appa->lb + lb->gw: 0.128

## Uncertainty (200 draws, T_Q ~ U[5,20], 201-point grid)

The ranking is recomputed for each draw of the uncertain parameters (C, L, O, t_fix, H as specified in groundtruth.json). P(top-1) and P(top-k) are over draws in which some channel has a positive gain. Declared values are treated as medians of lognormal distributions unless a channel or class spec says otherwise. Rule: robust first fix = channel with the highest P(top-1) over draws with any positive gain; ties broken by mean gain, then by name.

### worst reading: robust first fix gw->client (point estimate: gw->client; draws with no positive gain: 0)

| Channel | Point gain | Mean gain | 90% interval | P(top-1) | P(top-3) |
|---|---|---|---|---|---|
| gw->client | 0.68 | 0.711 | 0.178–1.239 | 0.945 | 0.985 |
| lb->gw | 0.03 | 0.067 | 0.0–0.342 | 0.055 | 0.73 |
| appa->lb | 0.0 | 0.015 | 0.0–0.075 | 0.0 | 0.55 |
| appb->appa | 0.0 | 0.0 | 0.0–0.002 | 0.0 | 0.245 |

### share reading: robust first fix lb->gw (point estimate: lb->gw; draws with no positive gain: 0)

| Channel | Point gain | Mean gain | 90% interval | P(top-1) | P(top-3) |
|---|---|---|---|---|---|
| lb->gw | 0.733 | 0.739 | 0.0–1.703 | 0.88 | 0.935 |
| appa->lb | 0.0 | 0.058 | 0.0–0.309 | 0.12 | 0.57 |
| appb->appa | 0.0 | 0.0 | 0.0–0.002 | 0.0 | 0.3 |

**Robust first fixes diverge between readings.**

## Coverage

- Data classes with labeled flows: 100%
- Labeled share of inferred flow channels: 73%
- Flow channels with negotiation telemetry: 100%
- Channels with an unattributed caller: 0; residual risk if they carried the classes of their server: 0.0

## CRQC-arrival prior x T_PQ sensitivity (propagated risk)

| Prior | T_PQ | records worst | records share | profile worst | profile share |
|---|---|---|---|---|---|
| uniform[5,20] | inf | 4.067 | 2.4 | 0.34 | 0.25 |
| uniform[5,20] | 15.0 | 4.067 | 2.4 | 0.34 | 0.25 |
| uniform[5,20] | 10.0 | 4.067 | 3.448 | 0.34 | 0.25 |
| late uniform[10,30] | inf | 0.925 | 0.612 | 0.0 | 0.0 |
| late uniform[10,30] | 15.0 | 0.925 | 0.612 | 0.0 | 0.0 |
| late uniform[10,30] | 10.0 | 0.925 | 0.925 | 0.0 | 0.0 |
| early 5+Exp(mean 4) | inf | 7.264 | 4.1 | 0.911 | 0.644 |
| early 5+Exp(mean 4) | 15.0 | 7.264 | 4.1 | 0.911 | 0.644 |
| early 5+Exp(mean 4) | 10.0 | 7.264 | 5.671 | 0.911 | 0.644 |
| lognormal median 12 | inf | 4.12 | 2.441 | 0.274 | 0.208 |
| lognormal median 12 | 15.0 | 4.12 | 2.441 | 0.274 | 0.208 |
| lognormal median 12 | 10.0 | 4.12 | 3.605 | 0.274 | 0.208 |

## TNFL (E[T_Q~U(5,20)])

| Key | Acceptance horizon τ | Forgery window S | Quantum-vulnerable |
|---|---|---|---|
| fw-signer | 3 | 0.00 | True |
| int-ecdsa | 3 | 0.00 | True |
| root-mldsa | 20 | 0.00 | False |
| root-rsa | 20 | 7.50 | True |

- firmware.bin: chain fw-signer → int-ecdsa → root-rsa; R_T = 7.50; dominant key: root-rsa

## Sensitivity to post-quantum breaks (E[T_Q~U(5,20)])

| T_PQ | records worst | records share | profile worst | profile share | S(fw-signer) | S(int-ecdsa) | S(root-mldsa) | S(root-rsa) |
|---|---|---|---|---|---|---|---|---|
| 20 | 4.067 | 2.4 | 0.34 | 0.25 | 0.0 | 0.0 | 0.0 | 7.5 |
| 15 | 4.067 | 2.4 | 0.34 | 0.25 | 0.0 | 0.0 | 5.0 | 7.5 |
| 10 | 4.067 | 3.448 | 0.34 | 0.25 | 0.0 | 0.0 | 10.0 | 7.5 |
| 5 | 4.067 | 4.067 | 0.34 | 0.34 | 0.0 | 0.0 | 15.0 | 7.5 |

## SSH plane (E[T_Q~U(5,20)])

- Discovery data:22: key exchange precision 1.000, recall 1.000

| Channel | Negotiated (pcap) | Connections |
|---|---|---|
| data->appb | mlkem768x25519-sha256 100% | 24 |
| data->ops | curve25519-sha256 100% | 18 |
- sshd log vs captures at data:22: yes (pcap {'curve25519-sha256': 18, 'mlkem768x25519-sha256': 24}, log {'curve25519-sha256': 18, 'mlkem768x25519-sha256': 24})
- records-export (worst): R = 1.69, sunk = 1.0, fix one now: data->appb 0.0, data->ops 0.69
- records-export (share): R = 1.69, sunk = 1.0, fix one now: data->appb 0.0, data->ops 0.69

## SSH key exchange

- data: mlkem768x25519-sha256, sntrup761x25519-sha512@openssh.com, curve25519-sha256, ecdh-sha2-nistp256, ext-info-s, kex-strict-s-v00@openssh.com
