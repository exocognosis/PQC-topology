# Testbed run report

## Discovery accuracy (active probe vs declared configuration)

- Versions, groups, TLS 1.2 suites: precision 1.000, recall 1.000
- Served certificates correct (key and signature algorithm): 5/5
- Static certificates correct: 10/10

| Listener | Groups P/R | TLS 1.2 suites P/R | TLS 1.2 groups P/R | Cert |
|---|---|---|---|---|
| gw:443 | 1.00/1.00 | 1.00/1.00 | not probed | ok |
| lb:8443 | 1.00/1.00 | 1.00/1.00 | not probed | ok |
| appa:9443 | 1.00/1.00 | 1.00/1.00 | not probed | ok |
| appb:9444 | 1.00/1.00 | 1.00/1.00 | not probed | ok |
| data:7443 | 1.00/1.00 | 1.00/1.00 | not probed | ok |

## Supported vs negotiated (server telemetry)

| Listener | Supported (probe) | Negotiated share (logs) | Handshakes |
|---|---|---|---|
| gw:443 | X25519MLKEM768, X25519, prime256v1 | X25519MLKEM768 74%, X25519 26% | 477 |
| lb:8443 | (TLS 1.2 RSA kex) | TLSv1.2 AES256-GCM-SHA384 100% | 477 |
| appa:9443 | X25519 | X25519 100% | 636 |
| appb:9444 | X25519 | X25519 100% | 318 |
| data:7443 | X25519MLKEM768 | X25519MLKEM768 100% | 159 |

## Passive capture agreement

| Channel | Log groups | pcap groups | pcap handshakes | Agree |
|---|---|---|---|---|
| appa->appb | X25519 | X25519 | 159 | yes |
| appa->lb | X25519 | X25519 | 477 | yes |
| appb->appa | X25519 | X25519 | 318 | yes |
| data->appa | X25519MLKEM768 | X25519MLKEM768 | 159 | yes |
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
