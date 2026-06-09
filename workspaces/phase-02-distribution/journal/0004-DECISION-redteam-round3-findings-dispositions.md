---
type: DECISION
date: 2026-06-08
project: phase-02-distribution
phase: analyze
topic: /analyze red-team round 3 — round-2 fixes CLOSED; 2 HIGH (single E-vector-tier root cause); fixed
tags:
  [
    analyze,
    redteam,
    convergence,
    conformance-vectors,
    byte-identity,
    spec-accuracy,
  ]
---

# 0004 — DECISION: /analyze red-team round 3 findings + dispositions

Three parallel schema-less round-3 agents: closure, fresh-correctness, fresh-traceability. Agent IDs: closure `a0949a2f`, correctness `a7eab7fd`, traceability `a1a0b8f0`.

## Closure of round-2 findings: ALL CLOSED ✅

The closure agent verified all 10 R2 findings landed (S5b boundary shard, S17 onboarding, S15m musl, the pinned SAS/store-poll/DP params, WS-6 depth correction, shard count 31, S7v rewire). 0 not-closed.

## New findings (round 3): 0 CRIT / 2 HIGH / 2 MED — single root cause

The two HIGH are the SAME bug class — the E-vector tier was mislabeled (inherited from the WS-1 deep-dive's "E1–E7 semantic-equivalence for LLM paths" framing). **Verified against source** (`specs/runtime-abstraction.md:188-196,58,205`): E1–E7 are ALL byte-identical/structural (canonical JSON, signing, set-equality, cycle detection, proof verification, orphan resolution, head-commitment monotonicity) — NONE are LLM-composed. The genuine semantic-equivalence surfaces are the rendered-text outputs (N4, Grant Moment text), and that harness is largely Phase-03 (`:207`).

| ID        | Finding                                                                                                                                                                                                                                                                                             | Disposition                                                                                                                                                                                             |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R3-HIGH-1 | **S3a/S3b mislabel E1–E7 as "semantic-equivalence (probe-judged)" → loop `base`.** They are byte-identical (deterministic hash-equality → `live`). Demoting byte-identical→semantic weakens the security gate (BLOCKED per the conformance contract) and mis-sizes the shards (base vs multiplier). | **FIXED**: S3a/S3b relabeled byte-identical, loop `live`; loop-legend corrected (all Phase-02 conformance vectors are byte-identical → `live`; semantic-equivalence rendered-text harness is Phase-03). |
| R3-HIGH-2 | **Critical-path prose `S1→S2a→S3b→S7v` named an edge (S3b→S7v) the round-2 R2-LOW-2 rewire deleted.** The rewire (S7v→S2b/c) was itself based on the mislabel — E7 IS byte-identical and lives in S3b, so S7v→S3b is correct.                                                                       | **FIXED**: S7v rewired to depend on S3b (E7 byte-identical) + S4s; critical path `S1→S2a→S3b→S7v` is now valid. R2-LOW-2's rewire reverted (it acted on the wrong premise).                             |
| R3-MED-1  | **Level-2-wave enumeration stale post-S5b** — S5o depends on S5b (level-3), S7v on S3b (WS-1 path), not "only S4s".                                                                                                                                                                                 | **FIXED**: level enumeration corrected (level-2 = {S4i,S4r,S5b,S6a,S6b}; level-3 = {S4g,S5o}; level-4 = {S6c}; S7v on the WS-1 path).                                                                   |
| R3-MED-2  | **Critical-path exemplar named a non-existent edge** (traceability agent, same area as R3-HIGH-2).                                                                                                                                                                                                  | **FIXED** with R3-HIGH-2 (the edge now exists correctly).                                                                                                                                               |

## Items surviving as LOW / non-blocking (folded, no re-flag expected)

- S17 ADR-0006 degraded-mode runtime is app-logic-in-scope, not just bundling (note at `/todos`).
- Store-poll interval/backoff value is a `/todos` tuning parameter (correctness closed by monotonic-version re-check).
- Pinned params (SAS ≤2⁻²⁰, total-ε-over-window) confirmed CORRECT by the correctness agent.

## Net disposition

Round-2 fixes all held. Round 3's 2 HIGH were a single root cause (E-vector tier mislabel from the WS-1 deep-dive), verified against `runtime-abstraction.md` and fixed in the plan + the WS-1 research doc (correction note). The convergence counter resets; round 4 verifies the E-tier fix is consistent and sweeps for anything remaining. Trajectory: R1 9H → R2 2H → R3 2H(one root cause) — converging.
