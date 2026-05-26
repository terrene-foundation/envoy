---
type: DECISION
date: 2026-05-26
created_at: 2026-05-26T13:20:20.539Z
author: co-authored
session_id: 92477210-aea3-485d-8a59-66f07d1a19b1
project: phase-01-mvp
topic: Wave-4 EnvoyGrantMomentRuntime facade (M0→M4 driver)
phase: implement
tags: [wave-4, grant-moment, runtime, facade]
source_commit: f086be91026c9d2f7ae9b86dde4df3345f51bf08
---

# Wave-4 EnvoyGrantMomentRuntime facade landed (M0→M4)

Commit: `f086be91026c` (merged via PR #41, 2026-05-26).

**Commit**: `f086be91026c` — feat(phase-01-wave-4): land EnvoyGrantMomentRuntime facade (M0→M4)

**Body**:

Wave-4 runtime facade composing the eight Wave-3 grant_moment structural
primitives into the M0→M4 lifecycle per `specs/grant-moment.md` § State
machine and § Test location "Runtime layer (deferred to Wave-4 facade)".

Surface:

- issue_grant_moment — M0 construct + sign + Phase A intent + M1 dispatch
- await_decision — M2 await with timeout → GrantMomentExpiredError
- post_decision — adapter-side push delivering the user's resolution
- submit_resolution — M3 sign-or-decline → M4 complete + DelegationRecord
- acknowledge_friction — caller-driven friction-token accumulator (T-019)
- confirm_cross_channel — high-stakes cross-channel confirm leg
- revoke_prior_grant — EC-8 cascade revocation surface
- emit*queue*{hold,resume} — bridge fan-out
- visible_secret_hash_for — T-018 hash plumbing for adapter render checks

Raise-path defenses wired at M3:

- T-008 GrantMomentReplayError (nonce + intent_id dedup at M0)
- T-018 VisibleSecretMismatchError (hash plumbing; raise at adapter)
- T-019 NoveltyFrictionRequiredError (5s read-delay + token enforcer)
- T-093 VelocityRaiseCoolingOffError (24h cooling-off ratchet)
- H-03 NotPrimaryChannelError (high-stakes decided-on non-primary)
- CrossChannelConfirmFailedError (high-stakes confirm leg missing)
- DualSignatureRequiredError (Phase-03 cross-principal contract pin)
- BackPressureQueueFullError (N-parallel queue ceiling)
- GrantMomentExpiredError / GrantMomentTimeoutError (M2 + per-channel)

Two-phase signing per `specs/ledger.md`: PhaseARecord emitted at M0
issue (links request via intent_id); DelegationRecord emitted at M3
with phase_a_ref back-link.

Per `rules/agent-reasoning.md`: zero content classification + zero
keyword routing — every decision arrives from an injected primitive
(NoveltyClassifier verdict, ChannelHandoff dispatch, OutOfEnvelopeDetector
classification). Per `rules/facade-manager-detection.md` Rule 3: every
dependency injected; no global lookups; no hidden singletons.

Closes Wave-3's deferred Wave-4 facade obligation per
`workspaces/phase-01-mvp/.session-notes` § Forest pick.

## Why this change was made

Wave-3 shipped the eight structural Grant Moment primitives (`state_machine`,
`signed_consent`, `resolution`, `channel_handoff`, `novelty`,
`out_of_envelope`, `cascade_orchestrator`, `plan_suspension_bridge`) but
deferred the M0→M4 orchestrator — `specs/grant-moment.md` § Test location
explicitly carves it out as "Runtime layer (deferred to Wave-4 facade)."
Without the facade, the eight primitives were 2,407 LOC of orphaned
infrastructure with no production hot-path call site (the failure mode
`rules/orphan-detection.md` MUST Rule 1 is designed to prevent).

The facade landed as a single shard rather than two (issue + resolve)
because the M0 + M2 + M3 + M4 transitions all share invariants (Phase A
intent emission, two-phase signing back-link, nonce dedup, friction-token
accumulator) — splitting would have exceeded `rules/autonomous-execution.md`
§ Per-Session Capacity Budget on invariant tracking (5-10 simultaneous).

## What this unlocks / blocks

- **Unlocks Wave-4 channels** (PR #42 — `feat/phase-01-wave-4-channels-foundation`):
  the channel adapters now have an M1 dispatch target. Foundation shard
  shipped today.
- **Blocks Phase 02** until cross-principal dual-sign + cross-channel hop +
  literal 3-deep cascade test wire up (see journal-0035 § Phase 02
  follow-ups).

## For Discussion

- **Single-shard vs split** — did the 1166-test suite verify every invariant,
  or did some land untested because of the breadth? (Counterfactual: if
  redteam Round 1 had surfaced 11 HIGH instead of 10, would we have
  needed to split mid-flight per `rules/autonomous-execution.md` § Per-Session
  Capacity Budget?)
- **Two-phase signing back-link via `phase_a_ref` vs `phase_a_record_ref`** —
  spec/ledger.md and specs/grant-moment.md still differ on the field name
  (F-SP-R2-2 carry-forward from journal-0035). Should `/codify` close the
  drift before Wave-A parallel siblings land?
- **Phase-01 cross-principal refusal at M0 vs M3** — the facade refuses
  `is_cross_principal=True` at M0 with `DualSignatureRequiredError`.
  Alternative was to allow construction and refuse at M3 sign. Spec § Cross-principal
  is silent on which boundary the refusal lands. Is the M0 choice correct
  for Phase 02's dual-sign verify path, or will it constrain that design?
