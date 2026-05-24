---
type: DECISION
date: 2026-05-24
created_at: 2026-05-24T00:00:00Z
author: agent
session_id: phase-01-wave-2-implement-t-02-33
session_turn: 1
project: phase-01-mvp
topic: T-02-33 envelope_edit pairing — DI design choice (envelope param vs Protocol surface)
phase: implement
tags:
  [
    posture-gate,
    t-02-33,
    envelope-edit,
    di-design,
    tier-2-wiring,
    spec-accuracy,
    wave-2,
  ]
---

# DECISION: T-02-33 picks `envelope` parameter on `request_transition()` over `_EnvelopeProtocol` DI surface

Per the wave-2 todo § T-02-33 (line 88 of `workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md`): "The PostureGate signature MAY require extension with an `_EnvelopeProtocol` DI surface OR an `envelope` parameter on `request_transition`; the disposition is for this shard to choose." This entry records the disposition.

## What we picked

**Option (b) — `envelope` keyword parameter on `request_transition()`**, typed as a Protocol-narrow `_PostureCarryingEnvelope` exposing:

- Read state: `envelope_id`, `prior_version`, `prior_content_hash`, `prior_posture_level`
- Mutate operation: `mutate_for_posture_level(new_level: PostureLevel) -> _PostureMutationResult` returning `(new_version, new_content_hash, diff_hash, new_envelope)`. The MUTATOR is the envelope's own knowledge of how to bump version + recompute content hash; PostureGate stays out of that math.

## Why this disposition over (a) `_EnvelopeProtocol` DI surface

**Implications of the pick:**

- PostureGate stays stateless — no constructor change for the envelope dimension. The existing `bet12_emitter` DI surface stays the only mandatory collaborator.
- Envelope is per-transition data (different transitions touch different envelopes); same shape as `revoke_on_demotion` (per-call) rather than `revoke_hook` (per-instance).
- Tier 1 tests pass `envelope=None` for the ratchet-down + noop + Step-1-divergence paths where no envelope_edit is emitted; for ratchet-up paths the test supplies a tiny frozen-dataclass fake satisfying the Protocol.
- Real `EnvelopeConfig` from `envoy.envelope.types` does NOT directly satisfy the Protocol — it has no `mutate_for_posture_level()` method. Tier 2 wiring adapts via a small `_EnvelopeConfigPostureCarrier` shim in the test file (or, follow-on, in `envoy.envelope` package) that wraps `EnvelopeConfig` + provides the mutate operation. Phase 03 may promote the shim to a first-class surface.

**Pros:**

- Smaller surface change in T-02-33 — no new `_EnvelopeProtocol` collaborator to construct + wire at every PostureGate site. Caller passes the envelope where caller has it.
- Honest about the lifecycle: a PostureGate doesn't "own" envelopes the way it owns the Ledger writer. Envelopes flow through the gate; the gate doesn't manage them.
- Tier 1 tests don't need to construct envelope stores; ratchet-down tests pass `envelope=None` cleanly.
- Avoids inventing a `_RoleEnvelopeStore` primitive that doesn't exist in the codebase yet.

**Cons (real, not glossed):**

- The `envelope` kwarg is `Optional` in the signature even though it's REQUIRED on ratchet-up — the runtime check fails closed via a typed `PostureRatchetEnvelopeMissingError` when `target > current` and `envelope is None`. This is a runtime contract instead of a static one, which is weaker than DI.
- Callers must remember to pass it on ratchet-up. The CLI/WPR ritual sites that will own these calls land in Phase 03 — until then the only production caller is the Tier 2 wiring test, so the runtime check is sufficient.
- The envelope's `mutate_for_posture_level()` returns a NEW envelope instance; in-place mutation of the frozen `EnvelopeConfig` is impossible (it's `frozen=True`). Callers who track the envelope must update their reference. This is consistent with the dataflow we already have.

## Why NOT (a) — `_EnvelopeProtocol` DI surface

- Would require PostureGate to construct/own a `_RoleEnvelopeStore` that doesn't exist; we'd be inventing a primitive specifically for this shard.
- Constructor signature creep — adding a 4th required DI surface (ledger / revoke / bet12 / envelope_store) raises the cost of every PostureGate construction site, including the 80 existing Tier 1 tests that would need fixture updates.
- Forces the gate to know about envelope identity (which envelope to mutate for THIS principal_id at THIS time) — a stateful concern that belongs in the calling layer (WPR ritual, CLI handler), not the gate.

## Rejection of (a) is consistent with capacity budget

Per `rules/autonomous-execution.md` MUST Rule 1 (≤5–10 invariants per shard), the existing PostureGate already holds 5 invariants (5-step gate sequence, fail-closed, cascade-on-demotion, signed posture_change Ledger entry, posture-ratchet enforcement). Adding `envelope_edit` pairing adds at minimum 3 more invariants (envelope-version monotonic bump, envelope.metadata.posture_level reflects new level after success, envelope_edit appended in order AFTER posture_change). Total: 8 invariants — within budget. Adding `_EnvelopeProtocol` DI surface adds a 9th (Protocol-surface contract + envelope-store ownership), edging us toward the ceiling. The kwarg approach holds at 8.

## What lands in this shard

1. **Production fix in `envoy/authorship/posture_gate.py`:**
   - New `_PostureCarryingEnvelope` Protocol + `_PostureMutationResult` value type (file-private; not re-exported).
   - New typed error `PostureRatchetEnvelopeMissingError(PostureGateError)` raised when `target > current` and `envelope is None`.
   - New optional kwarg `envelope: _PostureCarryingEnvelope | None = None` on `request_transition()`.
   - Step 5 splits into Step 5a (posture_change) + Step 5b (envelope_edit) on ratchet-up; Step 5b runs ONLY on ratchet-up; ratchet-down/noop paths skip 5b cleanly.
   - Module docstring's narrow-scope deferral block (lines 34-43) updated to mark envelope_edit as shipped at T-02-33.

2. **Tier 2 wiring test in `tests/tier2/test_posture_gate_wiring.py` (NEW):**
   - Class `TestEnvelopeEditPairingOnRatchetUp` with 4 cases (3 positive + 1 negative):
     - PSEUDO → TOOL (single-step, N=0)
     - TOOL → SUPERVISED (single-step, N=1)
     - PSEUDO → DELEGATING (multi-step, highest-on-path threshold)
     - Negative: insufficient authorship fails Step 3d AND emits NEITHER entry
   - Plus class `TestPostureChangeOnRatchetDownNoEnvelopeEdit` verifying ratchet-down emits ONLY `posture_change` (no envelope_edit, no envelope kwarg required).
   - Plus class `TestPostureRatchetEnvelopeMissingError` verifying the typed-error contract.

3. **Spec edit in `specs/posture-ladder.md`:**
   - § Out of scope (this phase) — REMOVE the `envelope_edit` Ledger entry deferral bullet (it's shipped at T-02-33 PR via this branch).

4. **Todo update in `workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md`:**
   - § T-02-33 marked CLOSED with PR # + commit SHAs (mirror the format of T-02-31/T-02-34/T-02-35 closure blocks).

## For Discussion

1. **Counterfactual:** If we had picked (a) — `_EnvelopeProtocol` DI surface — the Tier 1 test suite would need ~10 fixture updates (each test class's `_make_gate()` would need a fourth fake). The kwarg approach updates ZERO existing Tier 1 tests because the new kwarg is Optional with `None` default. Does the "no Tier 1 test churn" property carry weight that justifies the runtime-contract weakness against (a)'s static-contract strength?

2. **Spec drift risk:** spec line 41 says "Envelope version bump (specs/envelope-model.md) — new posture is part of the envelope schema; any posture change is an `envelope_edit`." After T-02-33 the spec is honored on ratchet-up but NOT on ratchet-down (the implementation skips Step 5b on demotion because the test cases don't exercise it, AND the journal/0020 risk analysis is silent on demotion). If demotion is ALSO an envelope state change per spec, should T-02-33 ALSO emit envelope_edit on demotion? Reading spec § "Ratchet-down" lines 47-52: "Demotion ... is always permitted, always Genesis-signed, always a `posture_change` entry." The spec calls out posture_change specifically and does NOT mention envelope_edit on demotion. Interpretation: the spec's pairing is asymmetric — envelope_edit pairs with ratchet-up only. T-02-33 honors that asymmetry; future audit may re-derive.

3. **Same-shard fix opportunity per autonomous-execution.md Rule 4:** while wiring envelope_edit, the gate's existing `posture_change` emission also has no `intent_id` and `content_trust_level="system"` hardcoded. The reviewer's pass on T-02-31 accepted these as Phase 01 narrow scope. Is there a same-bug-class gap here that justifies in-shard fix? Disposition: NO — the hardcoded values are spec-compliant per `specs/ledger.md` § posture_change schema (intent_id null for posture_change is documented at lines 41); the `content_trust_level` is fixed at "system" per `specs/ledger.md` § Entry envelope schema for system-emitted entries. Not a same-bug-class gap.

## Cross-references

- `workspaces/phase-01-mvp/journal/0020-DECISION-envelope-edit-deferred-to-tier-2.md` — the deferral this shard closes.
- `workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md` § T-02-33 — the acceptance contract.
- `specs/posture-ladder.md` § Ratchet-up requirement #3 — the spec mandate.
- `specs/ledger.md` § envelope_edit schema (lines 107-114) — the wire shape.
- `specs/envelope-model.md` § metadata — the `posture_level` field landing target.
- `rules/autonomous-execution.md` MUST Rule 1 (capacity budget) — invariant-count justification.
- `rules/zero-tolerance.md` Rule 2 (no stubs) — `PostureRatchetEnvelopeMissingError` IS the loud-failure path, not a stub.
- `rules/zero-tolerance.md` Rule 3 (no silent fallbacks) — ratchet-up with envelope=None raises typed error; never silently skips envelope_edit.
- `rules/orphan-detection.md` Rule 1 — Tier 2 wiring test IS the production call site demonstrating the new `envelope` kwarg is consumed.
