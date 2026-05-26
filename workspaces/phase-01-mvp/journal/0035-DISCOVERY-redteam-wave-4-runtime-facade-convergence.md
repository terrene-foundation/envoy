---
type: DISCOVERY
date: 2026-05-26
created_at: 2026-05-26T11:30:00Z
author: agent
session_id: 8d16380b-9f76-422c-aef7-8d805d4d19e3
project: phase-01-mvp
topic: Wave-4 EnvoyGrantMomentRuntime facade /redteam convergence — 4-round parallel multi-agent audit
phase: redteam
tags:
  [wave-4, grant-moment, runtime-facade, redteam, convergence, CLEAN×2, EC-2]
---

# /redteam Wave-4 EnvoyGrantMomentRuntime — CONVERGED (4 rounds across 3 axes)

Branch `feat/phase-01-wave-4-grant-moment-runtime` (HEAD `9b8708f`,
4 commits ahead of main `2eee262`) reached the brief Exit criterion
("0 CRITICAL/HIGH findings, 2 clean rounds") via four rounds of parallel
multi-agent audit closing the **EC-2 acceptance gate** ("3 Grant Moments
triggered and resolved correctly") via the runtime facade.

## Round trajectory

| Axis              | R1             | R2             | R3    | R4    | 2-CLEAN met at |
| ----------------- | -------------- | -------------- | ----- | ----- | -------------- |
| Security          | NEEDS_FOLLOWUP | NEEDS_FOLLOWUP | CLEAN | CLEAN | R3 + R4        |
| Code/Architecture | NEEDS_FOLLOWUP | CLEAN          | CLEAN | —     | R2 + R3        |
| Spec compliance   | NEEDS_FOLLOWUP | CLEAN          | CLEAN | —     | R2 + R3        |

## What landed in this PR

**Facade** (commit `f086be9` — 1003 LOC across 2 files):

- `envoy/grant_moment/runtime.py::EnvoyGrantMomentRuntime` — the M0→M4
  facade composing the 8 Wave-3 structural primitives (state_machine,
  signed_consent, resolution, channel_handoff, cascade_orchestrator,
  plan_suspension_bridge, novelty, out_of_envelope).
- `envoy/grant_moment/__init__.py` extended with `EnvoyGrantMomentRuntime`,
  `GrantMomentOutcome`, and 3 friction token constants.

**Tests** (commit `24b5fa3` — 11 spec-named files at `tests/integration/`,
`tests/regression/`, `tests/e2e/`):

- All 9 deferred Wave-4 test files cited in `specs/grant-moment.md`
  § Test location "Runtime layer (deferred to Wave-4 facade)".
- Plus the EC-2 acceptance test
  `tests/e2e/test_grant_moment_3_resolution_shapes_with_cascade.py`.
- Shared harness at `tests/helpers/grant_moment_harness.py` exposes
  `make_runtime()` + stub adapters so each test file imports rather
  than duplicates fixture wiring.

**R1-fix** (commit `e2709c6` — 10 HIGH + 15 MEDIUM closures):
see commit body for full enumeration. Highlights:

- T-008 nonce + intent_id dedup stores bounded via `OrderedDict` FIFO
  eviction at `dedup_store_ceiling=100_000` (security-R1 HIGH-1).
- Velocity-raise cooling-off moved from `time.monotonic()` →
  `time.time()` wall-clock; matches user-facing 24h claim (security-R1 HIGH-3).
- Phase-01 cross-principal refusal at M0 boundary
  (`DualSignatureRequiredError`) — Phase 03 wires the verification path.
- Phase-B ledger row retagged `DelegationRecord` → `grant_moment` per
  `specs/ledger.md` § grant_moment with 8 canonical fields
  (analyst-R1 HIGH-3).
- All 5 ERROR-outcome paths in `submit_resolution` emit structured
  `logger.warning("grant_moment.refused", ...)` (reviewer-R1 HIGH-4).
- `NoveltyFrictionRequiredError.friction_kind` discriminator
  (KIND_READ_DELAY_WALLCLOCK / KIND_READ_DELAY_TOKEN_MISSING /
  KIND_DOUBLE_TAP_MISSING) replaces substring-prose assertions per
  `rules/probe-driven-verification.md` MUST-1.

**R2-fix** (commit `9b8708f` — 1 HIGH + 2 MED + 3 LOW closures):

- `_resolve_delegation_pubkey_hex` raises on BOTH `getter is None` AND
  `result is None` branches (the R1 patch had only closed the first
  branch — security-R2 HIGH).
- Dispatch-failure cleanup ordering: ledger emit BEFORE dedup release.
  If audit append fails, the dedup reservations stay in place —
  GrantMomentReplayError on retry is safer than nonce-burn-without-audit
  (security-R2 MED-1).
- Forward-clock-skew limitation documented in runtime docstring AND
  `specs/grant-moment.md` § Velocity-raise per `rules/specs-authority.md`
  Rule 6 (security-R2 MED-2).
- `confirm_cross_channel` reordering (`_require_inflight` → high_stakes
  → channel set) so KeyError surfaces correct cause; rejects non-high-
  stakes calls as programming error (security-R2 LOW-1+2).
- New `tests/integration/test_grant_moment_dedup_store_fifo_eviction.py`
  pins the bounded-collection invariant (security-R2 LOW-3).

## Convergence verdict

Brief Exit criterion ("0 CRITICAL/HIGH findings, 2 clean rounds") is MET
for all three audit axes:

- 0 CRITICAL findings across 4 rounds.
- 0 HIGH findings standing (10 HIGH from R1 + 1 HIGH from R2 all closed
  by same-shard fixes per `rules/autonomous-execution.md` MUST Rule 4).
- 2 consecutive clean rounds per axis.

**EC-2 acceptance gate is structurally met:** the runtime facade drives
all three resolution shapes (Approve / Decline / ApproveWithModification)
end-to-end through `tests/e2e/test_grant_moment_3_resolution_shapes_with_cascade.py`

- exercises the EC-8 cascade-revocation contract anchor (root + 3
  expected descendants; Phase 02 lifts to a literal 3-deep delegation tree
  once Trust Vault container persistence lands).

## Carry-forward to /codify

- **F-SP-R2-2 (carry-forward from Wave-3 redteam):** `phase_a_record_ref`
  (grant-moment.md:66) vs `phase_a_ref` (ledger.md:391,407) cross-spec
  terminology drift. Pre-existing; explicitly out of Wave-4 blast radius
  per session-notes 2026-05-26.
- **Phase 02 follow-ups** documented in code + specs (NOT deferred
  issues — Phase 02 is the next-phase scope marker, not a follow-up
  bucket):
  - Persist nonce/intent_id dedup into TrustVault sub-store so
    replay-defense survives process restart.
  - Persist velocity-raise wall-clock + monotonic baseline so
    forward-skew is detectable.
  - Lift Phase-01 cross-principal refusal to full dual-sign +
    cross-channel hop + 24h cool-off flow.
  - Trust Vault container wrappers MUST expose `get_public_key` per
    the runtime's hardened protocol.
  - Lift EC-8 test to literal 3-deep delegation tree.

## Receipts

- Branch `feat/phase-01-wave-4-grant-moment-runtime` HEAD `9b8708f`.
- Commits: `f086be9` (facade), `24b5fa3` (tests), `e2709c6` (R1-fix),
  `9b8708f` (R2-fix).
- Full suite: 1170 passed, 9 skipped (was 974 before Wave-4; +196 net).
- Round 1 reports: security-r1, reviewer-r1, analyst-r1 agent IDs
  recorded in session transcript.
- Round 2 reports: security-r2 (NEEDS_FOLLOWUP), reviewer-r2 (CLEAN),
  analyst-r2 (CLEAN) agent IDs in session transcript.
- Round 3 reports: security-r3 (CLEAN), reviewer-r3 (CLEAN),
  analyst-r3 (CLEAN) agent IDs in session transcript.
- Round 4 report: security-r4 (CLEAN) agent ID in session transcript.

## For Discussion

1. **Cross-principal Phase-01 refusal — is the M0-boundary gate the
   right disposition, or should the wire-shape continue to accept
   `is_cross_principal=True` and signal Phase-03 deferral some other
   way?** The current refusal makes the test contract pin "Phase 03
   not implemented" structurally visible, but a downstream agent that
   tries to test cross-principal flows in Phase 01 hits a hard wall
   rather than a graceful "wire-shape accepted, runtime deferred"
   path. Counterfactual: if we'd kept the wire-shape acceptance, would
   the security review have surfaced the fake-co-signer gap at all,
   or would it have lingered into Phase 02?

2. **Wall-clock vs monotonic for the velocity-raise cooling-off —
   the R1+R2 trajectory inverted from `monotonic()` (restart-vulnerable)
   to `time.time()` (skew-vulnerable). Is the right Phase 01 disposition
   `time.time()` (current) OR should we ship a hybrid that uses
   `min(time.time() - last_wallclock, time.monotonic() - last_monotonic)`
   so BOTH attack surfaces are closed?** Phase 02 lifts to TrustVault
   persistence anyway, but if a Phase 01 operator wants both defenses
   right now, the hybrid is one extra dict field.

3. **EC-2 acceptance — the test exercises all 3 resolution shapes
   through the runtime AND the cascade revocation surface AND the
   3-deep cascade contract (via the orchestrator's `expected_descendants`
   set). Is this structurally enough to declare EC-2 met, or does the
   brief's "3 Grant Moments triggered and resolved correctly" wording
   imply a richer end-to-end scenario (e.g., 3 grants across 3 different
   tools + 3 different channels + 3 different envelopes)?** The current
   test exercises 3 distinct resolution paths but uses the same envelope
   - tool + channel; if the brief intent is broader, the test should be
     parameterized.
