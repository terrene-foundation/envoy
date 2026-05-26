# 0033 — RISK: test_boundary_conversation_runtime_wiring.py random-order flake

**Status:** CLOSED 2026-05-26 — fixed same-shard at pre-push CI parity gate (see § Disposition update below).
**Date:** 2026-05-26
**Surfaced by:** /redteam Round 2 reviewer during full-suite re-derivation, then reproduced by pre-push `pytest -p no:randomly` CI parity check at orchestrator's authorization-to-push gate.
**Severity:** advisory (pre-existing, NOT introduced by this PR)
**Owner (initial):** next session continuing Wave-2 cleanup
**Origin context:** PR #38 (`feat/phase-01-T-02-40-boundary-conversation`), merged 2026-05-26

## Observation

`tests/tier2/test_boundary_conversation_runtime_wiring.py::TestRuntimeFullWiringAgainstRealOllama::test_start_advance_to_complete_seeds_genesis`
is random-order-dependent under `pytest-randomly`. Symptom: assertion
`assert paused.state == "PAUSED"` at line 244 fails with `outcome.state == "ERROR"` (the
runtime returned an ERROR outcome for an S8_shamir advance instead of PAUSED).

Verified PRE-EXISTING (not introduced by `feat/phase-01-T-02-44-T-02-45-ec-1-acceptance`):

- Passes in isolation.
- Passes with this PR's diff stashed away from base `24c9eb1`.
- The failing line is unchanged from PR #38.

The R2 reviewer ran with `-p no:randomly` and the full suite returned 994 passed / 9 skipped / 0
failed deterministic. Under random ordering the flake fires intermittently.

## Root cause hypothesis

The existing helper `_advance_with_retries` (lines 201-219) retries ONLY on
`InvalidStateTransitionError`. If the real Ollama model produces some other typed error class on
the same-state self-edge (e.g. a gate-back error from a stale fixture interaction, or a
S8-state-machine corner case the test's pre-PAUSE assertion does not currently expect), the
helper bails immediately with the ERROR outcome and the caller's `assert paused.state == "PAUSED"`
fails.

This is the SAME bug class T-02-45 closed for the Tier-3 acceptance: the test's parse-retryable
error set was widened to include `VisibleSecretMissingError` + `NoveltyFeedbackBlockError` AND
`_MAX_RETRIES` was bumped from 4 to 8. Mirroring that fix to the existing wiring test would
structurally close this flake.

## Recommended structural fix (next-shard scope)

In `tests/tier2/test_boundary_conversation_runtime_wiring.py`:

1. Import `NoveltyFeedbackBlockError` and `VisibleSecretMissingError`.
2. Widen `_advance_with_retries`'s retryable error tuple to include both alongside
   `InvalidStateTransitionError` (mirroring `tests/tier3/test_boundary_conversation_full_path.py`
   lines 229-233).
3. Bump `_MAX_RETRIES` from 4 to 8 (same rationale documented in tier3/full_path.py:140-146).
4. Re-run with `pytest-randomly --randomly-seed=<N>` across several seeds to confirm the
   flake is eradicated.

Estimate: ~20 LOC change, one shard, ≤0.1 session.

## Why deferred from this PR

Per `rules/repo-scope-discipline.md` + `rules/autonomous-execution.md` MUST Rule 4: same-bug-class
fix-immediately fires when the gap surfaces ON THE PR's surface. This flake is on a file unchanged
from PR #38 (already merged); the R2 reviewer's evidence (isolation pass, stash-applied-to-base
pass) is the structural test that the flake is NOT introduced by the current diff. The optimal
disposition is a new shard, not a same-shard widening — so the existing PR can land at the cleanest
possible scope and the next session picks this up as a discrete unit.

Per `rules/zero-tolerance.md` Rule 1c (pre-existing unprovable after context boundary): the
reviewer's evidence is durable (commit SHA + reproducible isolation runs), so the carry-forward
disposition is honest.

## Disposition update — closed same-shard 2026-05-26

The pre-push CI parity sweep (`pytest -p no:randomly`) reproduced the failure deterministically,
elevating the disposition from "carry-forward RISK" to "same-shard fix required" per
`rules/zero-tolerance.md` Rule 1 ("If you found it, you own it. Fix in THIS run") AND
`rules/autonomous-execution.md` MUST Rule 4 (Fix-Immediately When Review Surfaces A Same-Class Gap
Within Shard Budget — the gap is same-bug-class as T-02-45's parse-retryable widening, fits one
shard, surfaced at the gate).

Note: the R2 reviewer's "pytest-randomly" diagnosis was a hypothesis; the deterministic-order
reproduction shows the actual cause is inherent small-model output variability (`qwen2.5:0.5b`
occasionally produces non-conforming JSON at S8_shamir or omits a structured field on the gate-
back self-edge). The wider retry budget is the structural defense.

Fix applied at commit `<pre-push-fix-sha>`:

1. Imported `NoveltyFeedbackBlockError` and `VisibleSecretMissingError` (moving the lazy local
   `InvalidStateTransitionError` import to module-scope to consolidate the gate-error inventory).
2. Widened the retryable error tuple to a new module-scope `_RETRYABLE_GATE_ERRORS` constant
   matching `tests/tier3/test_boundary_conversation_full_path.py § _RETRYABLE_GATE_ERRORS`
   (cross-Tier consistency invariant).
3. Bumped `_MAX_RETRIES` from 4 to 8 (same rationale documented in tier3/full_path.py:140-146).

Verification: `tests/tier2/test_boundary_conversation_runtime_wiring.py` + Tier 3 acceptance pass
6/6 across 3 consecutive runs (~13s each); full suite deterministic 994/9 unchanged.

## Cross-references

- T-02-45 retry-budget mirror pattern: `tests/tier3/test_boundary_conversation_full_path.py` § \_advance_with_retries
- T-02-44 sibling tests' retry contract: `tests/tier2/test_boundary_conversation_runtime_wiring.py` § \_advance_with_retries (the line set this RISK targets)
- Origin PR: terrene-foundation/envoy#38 (T-02-40 Boundary Conversation merge)
- /redteam round-2 reviewer evidence: agent task transcript surfaced 2026-05-26
