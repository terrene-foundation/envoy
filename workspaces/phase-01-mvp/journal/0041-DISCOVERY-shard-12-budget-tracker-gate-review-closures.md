---
type: DISCOVERY
date: 2026-05-28
created_at: 2026-05-28T00:00:00Z
author: co-authored
project: phase-01-mvp
topic: shard-12 Budget tracker — gate-review (reviewer + security-reviewer) closures
phase: implement
tags: [shard-12, budget, gate-review, fix-immediately, EC-8]
---

# 0041 — DISCOVERY: shard 12 Budget tracker — /implement gate-review closures

## Where we are

`feat/phase-01-shard-12-budget-tracker` ships the multi-window Budget tracker
primitive (`envoy/budget/` — orchestrator + ledger emitter + threshold
dispatcher + runtime adapter + types/errors/reset-scheduler/anomaly-detector,
~1,300 LOC; 12 spec-pre-declared + orphan/facade-mandated test files, ~900 LOC
tests; 12 new tests on Tier-1/2 + the new closure tests, 56 total budget tests).
Removes the 4 `Phase02SubstrateNotWiredError` budget stubs in the kailash-py
runtime adapter — the orchestrator is now on the production hot path
(`rules/orphan-detection.md` Rule 1).

Two commits:

- `8b6100a feat(budget): shard 12 — multi-window Budget tracker primitive`
- `53135ab fix(budget): /implement gate-review closures — HIGH#1 guard timing + MEDIUMs`

Suite: 1580 passed, 9 skipped (no regressions vs. the 1569 baseline + 11 new
review-closure tests). Ruff clean. Spec (`specs/budget-tracker.md`)
reconciled: test paths to the project's tier layout per
`rules/spec-accuracy.md` Rule 1; new § Ledger entries emitted documents the
3 emitted entry types (`budget_reservation_record` / `budget_threshold_crossed`
/ `budget_extended`) with their content shapes — additive to the owning
spec, no `specs/ledger.md` edit (avoids the Rule 5b sibling-re-derivation
sweep at this shard).

## Why it was built

EC-8(b) "no double-billing in Budget tracker against multi-channel actions"
(`02-mvp-objectives.md` line 117) depends on this primitive, and the
Phase-01 ship predicate (line 149) requires all 7 cross-cutting deliverables.
The Budget tracker was fully designed (`01-analysis/12`) but never built;
the runtime budget surface (`KailashPyRuntime.budget_*`) raised
`Phase02SubstrateNotWiredError` on every call. The session's pick was
"build Budget tracker first" precisely because it gates BOTH EC-8(b) AND
independent ship-predicate completion.

## Gate-review trajectory (single round, both reviewers in parallel)

`/implement` MUST gate per `rules/agents.md`. Reviewer + security-reviewer
launched as parallel background agents on `git diff main..HEAD`. Both ran
mechanical sweeps first (per `rules/agents.md` § "Reviewer Prompts Include
Mechanical AST/Grep Sweep") then LLM judgment:

| Finding                                               | Source          | Severity | Disposition                                                                    |
| ----------------------------------------------------- | --------------- | -------- | ------------------------------------------------------------------------------ |
| record_for_call expired-replay over-releases siblings | reviewer HIGH-1 | HIGH     | Fix same-shard (commit `53135ab`)                                              |
| record_for_call partial-fail could double-charge      | security M1     | MEDIUM   | Fix same-shard (same guard fix)                                                |
| budget_velocity_check ignores in-flight reserved      | reviewer M2     | MEDIUM   | Fix same-shard                                                                 |
| Zero structured logging in budget package             | reviewer M3     | MEDIUM   | Fix same-shard                                                                 |
| threshold_bps lossy for non-canonical thresholds      | security M2     | MEDIUM   | Phase-02 (`subscribe_threshold` is public API; doc/validate at boundary later) |
| Unbounded `_pending` list                             | security L1     | LOW      | Fix same-shard (list → deque)                                                  |
| `apply_override` discards in-flight reservations      | security L2     | LOW      | Documented Phase-01 boundary; no change                                        |
| Dispatcher shared buffer interleave note              | reviewer L4     | LOW      | Single-thread Phase-01; informational                                          |
| MI isinstance test for `BudgetExhaustedError`         | reviewer L5     | LOW      | Fix same-shard (explicit dual-catch test)                                      |
| `or 0` idiom on int 0                                 | reviewer L6     | LOW      | No defect; informational                                                       |

All same-bug-class HIGH + MEDIUMs fixed in the SAME session per
`rules/autonomous-execution.md` Rule 4 (warm context + ≤500 LOC load-bearing
fits one shard budget). Security-reviewer cleared the commit (no
CRITICAL/HIGH from the security axis).

## Two patterns worth carrying forward

### 1. The EC-8 invariant has a mirror — no double-RELEASE either

The reviewer's HIGH was structurally identical to the EC-8(b) double-billing
guard the shard already implements: a repeated `record_for_call` of an
EXPIRED handle re-ran `_rollback`, which calls upstream
`tracker.record(reserved, 0)`. Upstream's saturating-subtract floors at 0,
so each replay ate a _sibling_ in-flight reservation's held capacity on the
same window. EC-8 forbids double-CHARGE; the same accounting-integrity
discipline forbids double-RELEASE.

Fix: mark the reservation consumed in `_recorded_reservations` BEFORE the
mutation (record-intent-first), so any retry hits the double-record guard
above instead of re-running release/record. One change closes both the
HIGH and the security M1 (partial-failure-retry double-charge) — same
invariant timing on the same code path.

The lesson: when implementing an accounting guard, sweep for the dual
defense — every "no double-X" invariant has a "no double-not-X" mirror.
A guard set only on the success path is half a guard.

### 2. Spec-mandated test names trigger a path-reconcile, not a layout fight

`specs/budget-tracker.md` § Test location (frozen) named `tests/unit/` and
`tests/integration/` paths. The project uses `tests/tier1/`, `tests/tier2/`,
`tests/regression/`, `tests/e2e/`. The daily-digest wave (`0040`) set the
precedent: reconcile the spec to the real paths per `rules/spec-accuracy.md`
Rule 1, NOT the other way around. Spec citations describe what ships today;
the real test paths ship today, the cited paths don't.

Cost: one § edit. Benefit: the spec doesn't lie, and the next /redteam round
running spec-citation hygiene (`tools/spec-cite-check.py`) passes without
suppressing the mismatch.

## Receipts

- Branch: `feat/phase-01-shard-12-budget-tracker`
- Commits: `8b6100a` (shard) + `53135ab` (review closures)
- Reviewer agent: `a46ad138d0c97840c` (1 HIGH, 2 MEDIUM, 3 LOW; all closed or documented)
- Security-reviewer agent: `a554320cf2712a176` (cleared — 0 CRITICAL/HIGH, 2 MEDIUM, 2 LOW)
- Test suite: 1580 passed, 9 skipped (no regression vs. 1569 + 11 new closure tests)
- Ruff: clean on all touched files
- Spec: `specs/budget-tracker.md` § Test location reconciled + § Ledger entries emitted added (additive — no `ledger.md` edit, no Rule-5b sibling re-derivation)

## What unblocks next

EC-8(a) cross-channel state-equivalence test + EC-8(c) cross-channel
cascade test were the original EC-8 picks deferred behind the Budget
tracker dependency. Both are now buildable against shipped primitives
(orchestrator + cascade orchestrator + ledger + 5 channel adapters), and
EC-8(b)'s double-billing guard is in place. The next shard writes the
4 EC-8 acceptance tests named in `02-test-strategy.md` § EC-8 (envelope
byte-identity, cross-channel cascade, no-double-billing, 7-day coherence
e2e).

Wave-5 (CLI packaging) remains gated on EC-3 ∧ EC-7 ∧ EC-8. EC-3 ✓ (PR
#44). EC-7 is DEGRADE-ACCEPTABLE at 5 channels (current); EC-8 unblocks
next shard. EC-9 (independent ledger verifier) remains a separate-repo
task per `rules/repo-scope-discipline.md` + `01-analysis/07-independent-
verifier-design.md` § 3.1 (`terrene-foundation/envoy-ledger-verifier`).

## For Discussion

1. **Counterfactual**: would single-agent review (vs parallel reviewer +
   security-reviewer) have surfaced the HIGH (expired-replay over-release)?
   The reviewer reproduced it via a targeted probe ("`record_for_call`
   called twice on an expired handle, what happens to siblings?"). The
   security-reviewer flagged the same code path's M1 (partial-failure
   double-charge) from a different angle (atomicity ordering, not replay).
   The two findings converged on the SAME fix area but from different
   threat models. Specific data: 1 HIGH + 1 MEDIUM caught by 2 reviewers
   in parallel; the HIGH was structural (load-bearing if it shipped), the
   MEDIUM was defense-in-depth. Parallel review found 2 same-class issues
   at the same cost as serial review of either axis alone.

2. **Specific data**: spec § Ledger entries emitted documents 3 new entry
   types (`budget_threshold_crossed`, `budget_reservation_record`,
   `budget_extended`) but the `specs/ledger.md` enumeration ("35 types"
   per design doc § 1) is now stale (38 with budget). The Rule-5b
   re-derivation cost of editing `ledger.md` is the explicit reason this
   shard deferred the enumeration update. Question: should `/codify` for
   shard 12 schedule the `ledger.md` edit (with its sibling re-derivation
   budget) as a Phase-01 follow-up, or defer to a multi-primitive enumeration
   sweep at Phase-01 wrap-up? Either way the budget entry types ARE
   documented (in `budget-tracker.md` § Ledger entries emitted) and the
   producer code accepts them — the ledger spec's enumeration count is
   the only stale surface.

3. **Counterfactual**: would the HIGH have been caught by the existing
   test suite without the explicit `test_repeated_expired_record_preserves_siblings`
   regression? No — the original tests covered single-record success
   paths and single-call double-record (EC-8b), not repeated-record-of-
   expired siblings. The reviewer's HIGH-1 was a class the spec didn't
   anticipate ("no double-RELEASE" mirror of "no double-CHARGE"). The
   regression test is now permanent (`@pytest.mark.regression`,
   `rules/testing.md` § Regression Testing) and pins the invariant
   against future refactor.
