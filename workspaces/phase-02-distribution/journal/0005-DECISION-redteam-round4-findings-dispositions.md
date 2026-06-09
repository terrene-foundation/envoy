---
type: DECISION
date: 2026-06-08
project: phase-02-distribution
phase: analyze
topic: /analyze red-team round 4 — E-tier fix consistent; 1 HIGH (N4 rendered-text over-sweep sibling); fixed
tags: [analyze, redteam, convergence, conformance-vectors, tier-precision]
---

# 0005 — DECISION: /analyze red-team round 4 findings + dispositions

Three parallel schema-less round-4 agents: E-tier closure/consistency, final-correctness sweep, final-traceability/DAG. Agent IDs: closure `a892e261`, correctness `aedf9d83`, traceability `ace059dd`.

## Verifications passed

- **E-tier fix (R3): CONSISTENT** — all 7 consistency checks pass (S3a/S3b byte-identical+live, S7v→S3b, critical path valid, no stale "semantic E-vector" refs, DAG acyclic, E7 confirmed byte-identical against `runtime-abstraction.md:196`).
- **DAG + traceability: CLEAN** — 31 shards, acyclic, depth-4, all EC + enabling items covered, no orphans. The traceability agent confirmed S7v→S3b is _more_ correct than the round-2 S2b/c (the verifier consumes E7, which lives in S3b, not the N-vectors).

## New finding (round 4): 0 CRIT / 1 HIGH — over-sweep sibling of R3

| ID        | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Disposition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R4-HIGH-1 | **The R3 legend edit over-corrected.** Fixing "E-vectors are byte-identical" I wrote "ALL N1–N6 + E1–E7 are byte-identical" — but **N4's rendered verdict TEXT is genuinely semantic-equivalence** (`runtime-abstraction.md:152` — "structured payload byte-identical; rendered text semantically-equivalent across runtimes"). So S2c (owns N4), labeled `live`, contains a semantic slice that can't be byte-gated. Same tier-precision bug class as R1-HIGH-8 (E-vectors / S5-S6) and R3-HIGH-1 (E-vectors), now on the N-vector side. | **FIXED**: legend now states the exact tiers — N1/N2/N5/N6 + N3 (structural-partition byte-identity + deterministic dispatch-observation) + N4-structured-payload + E1–E7 are byte-identical/`live`; the ONE semantic slice is N4's rendered verdict TEXT, whose scoring metric + Phase-02-vs-03 placement is an OPEN spec question (`runtime-abstraction.md:239`) flagged for `/todos`. S2c scope + spec-gaps updated. No shard added (the byte-identity work lands this phase; the semantic-scoring placement is a flagged `/todos` decision, not a silent drop or a false `live` label). |

## Items confirmed sound (no action)

All three agents independently confirmed the CORE design: WS-3 SAS transcript-binding + ≤2⁻²⁰ floor (MITM-safe), WS-6 store-poll-PRIMARY rendezvous + `GrantMomentExpiredError` audit preservation (`runtime.py:722`), WS-5 STAR+OHTTP+total-ε, WS-4 quorum-once + S9a/S9b accountability split, the legal-gate classification (EAR redistribution-not-build), the acyclic depth-4 DAG. The churn across rounds 3+4 was exclusively conformance-vector **tier-labeling precision** (a genuinely intricate N1–N6/E1–E7 mixed-tier surface), now exhaustively correct for every family.

## Net disposition + convergence status

Trajectory: **R1 2C/9H → R2 0C/2H → R3 0C/2H → R4 0C/1H.** Findings monotonically diminishing; rounds 3+4 were the same bug class (tier precision) on E-vectors then N4, both now resolved. The design is confirmed sound by independent agents. Not yet at the formal EC-6 "0 CRIT/0 HIGH × 2 consecutive clean rounds" bar — one confirming round (round 5) verifies the N4 fix introduced no further sibling. Receipts: this journal + agent IDs above.
