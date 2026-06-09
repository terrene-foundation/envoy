---
type: DECISION
date: 2026-06-08
project: phase-02-distribution
phase: todos
topic: /todos creation — 47 todos from the 33-shard map; red-team dispositions
tags: [todos, sharding, capacity, red-team, value-ranking]
---

# 0007 — DECISION: /todos creation + red-team dispositions

`/todos` expanded the `/analyze` 31-shard architecture map into **47 todos** across 7 files (`todos/active/_index.md` + `01..07-*.md`): value-ranked `_index.md` spine (I authored) + 6 milestone files + 1 cross-cutting test/acceptance file (parallel agents, waves of 3). Two `/todos`-time splits applied: **S13 → S13a/S13b** (M5 agent, Flutter+QR overflow) and **S4g → S4g-1/S4g-2** (capacity red-team, below) → **33 implementation shards + 14 test/acceptance = 47 todos.**

## Red-team (2 lenses)

- **Completeness/traceability** (agent `a598e494`): **CLEAN — 0 CRIT/0 HIGH.** All 33 shards → todos (1:1); all 10 ECs → acceptance batteries; all 6 workstreams + enabling items (S8e EnterpriseDeploymentRecord, S13b localization, S7v verifier, S17 onboarding) present; DAG consistent; cross-milestone edges (S9b→S6a, S12→S4g-1, S15→WS-1-embed) present. 4 doc-hygiene findings (below).
- **Capacity/quality** (agent `a151da7f`): citations excellent (**23/23 resolve, zero phantom**); acceptance criteria concrete; Tier-2/3 real-infra discipline correct; conformance hash-equality (not probe) correct. **1 HIGH + 3 MED + 2 LOW** (below).

## Dispositions

| Finding                                                                                                                                                       | Sev      | Disposition                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **S4g overflows budget** (8 load-bearing invariants by its own count, ~450 LOC, downstream of the high-risk S4r) — same class as the S13 split, left un-split | **HIGH** | **FIXED**: split into S4g-1 (core cross-process grant flow: M0→M4 + JCS-signed resolution + replay-nonce + back-pressure, ≤5 inv / ~280 LOC) + S4g-2 (velocity-raise monotonic-skew + 3-deep tree + cooling-off, ≤3 inv / ~180 LOC). Per `autonomous-execution.md` MUST Rule 1, sharding lands at `/todos`, not `/implement`. |
| S11 self-flags "at capacity" (~450-500 LOC) with no split valve                                                                                               | MED      | **FIXED**: pre-authorized split valve added (S11a STAR share-split + OHTTP / S11b DP + total-ε + k-floor + `maybe_record_flag`; seam = DP-before-share-split).                                                                                                                                                                |
| Wire todos assert "zero `Phase02SubstrateNotWiredError`" but not the broader "zero mock data" grep                                                            | MED      | **FIXED centrally**: `_index.md` § Build vs Wire now carries a binding global wire-gate (`grep -rn 'MOCK_\|FAKE_\|DUMMY_\|in-memory dict\|placeholder\|Phase02SubstrateNotWiredError' <module>` = 0 in non-test code) per `zero-tolerance.md` Rule 2 — applies to every wire todo whether or not its text restates it.        |
| Conformance no-N4-probe guard is a reviewer sweep, should be mechanical                                                                                       | MED      | **FIXED centrally**: `_index.md` § Build vs Wire now mandates a mechanical grep backing every reviewer-sweep acceptance (N4 case: `grep -rn 'probe\|llm_judge\|semantic_scor' tests/conformance/` = 0 in any N4 path) per `agents.md` § mechanical-sweep.                                                                     |
| `_index.md` M2 anchor cited `journal/0048` (a Phase-01 entry) without workspace prefix → broken path                                                          | MED      | **FIXED**: prefixed `workspaces/phase-01-mvp/`.                                                                                                                                                                                                                                                                               |
| `00-objectives-to-deliverables.md` EC-02.4 row stale ("E1–E7 semantic") + EC-02.5 row stale ("iMessage" as built)                                             | LOW      | **FIXED**: EC-02.4 → byte-identical (N4 text Phase-03); EC-02.5 → WhatsApp + Signal Path B (iMessage/Signal-A de-scoped Phase-04).                                                                                                                                                                                            |
| Shard-count label drift (31 vs 32 vs 33)                                                                                                                      | LOW      | **FIXED**: reconciled to 33 impl shards / 47 todos; S12 dep updated to S4g-1.                                                                                                                                                                                                                                                 |
| S7v split valve under-specified (cross-repo); S4r sub-line citations may drift                                                                                | LOW      | **CARRY-FORWARD to `/implement`** per `specs-authority.md` Rule 5c (amend-at-launch): re-resolve S4r's `runtime.py` sub-ranges at S4r launch; name S7v's split-target repo at S7v launch. Recorded here as the launch-time obligation.                                                                                        |

## Net

Todo list structurally complete + DAG-consistent + citations clean; the one HIGH (S4g over-budget) and the capacity MEDs are fixed at `/todos` (not deferred to `/implement`, per the budget rule). Ready for the human approval gate after the forest-vs-trees value-ranking surface (next).
