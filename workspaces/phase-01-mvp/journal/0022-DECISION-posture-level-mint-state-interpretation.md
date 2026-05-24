---
type: DECISION
date: 2026-05-24
created_at: 2026-05-24T01:00:00Z
author: co-authored
session_id: phase-01-rt1-shard1-invariants-and-mint-state
session_turn: 1
project: phase-01-mvp
topic: F-4 closure — metadata.posture_level is mint-state, not current-effective-posture
phase: redteam
tags:
  [
    posture-gate,
    envelope-model,
    mint-state,
    rt1-shard1,
    f-4-closure,
    spec-accuracy,
    audit-trail,
  ]
---

# DECISION: `metadata.posture_level` is the envelope's mint-time audit annotation, not the current effective posture

Closes the For Discussion #2 ambiguity from `workspaces/phase-01-mvp/journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md` § "For Discussion" #2 — the spec-asymmetric pairing question raised by Round 1 /redteam F-4 (HIGH). User-approved disposition: mint-state interpretation.

## What we picked

`metadata.posture_level` reflects the envelope's **mint-time posture** and is **immutable** after the `envelope_edit` emission that minted this envelope version. Reading the field tells you "what posture was active when this envelope version was minted" — NOT "what is the current effective posture for this principal."

The current effective posture is derived by walking the Ledger's `posture_change` entries (the audit chain). Ratchet-down emits a `posture_change` entry only (no `envelope_edit`, no envelope mutation); the envelope's `posture_level` stays at the mint-time value. The next ratchet-up mints a NEW envelope version whose `posture_level` reflects the new mint state, paired with both a `posture_change` AND an `envelope_edit` entry per `specs/posture-ladder.md` § Ratchet-up requirement #3.

## Why this disposition

**Implications of the pick:**

- The asymmetric pairing in `specs/posture-ladder.md` § Ratchet-up vs § Ratchet-down (lines 47-52) is consistent: ratchet-up mints a new envelope version (new mint state); ratchet-down emits `posture_change` only (no envelope mutation, no version bump).
- The `_PostureCarryingEnvelope.mutate_for_posture_level()` Protocol returns a NEW envelope (per `journal/0021` § "Cons" — "in-place mutation of the frozen `EnvelopeConfig` is impossible"). The original envelope reference stays at its mint-time `posture_level`; only the freshly-minted envelope carries the new value.
- The effective-posture-derivation path is the Ledger walk (audit chain), NOT the envelope read. Downstream consumers that need current effective posture MUST walk the Ledger; they MUST NOT trust the envelope field as the current value.
- Round 1 /redteam F-4 surfaced this as a HIGH gap — without explicit semantics, a future audit could misread the envelope field as authoritative and silently bypass the Ledger walk.

**Pros:**

- Clean alignment with `specs/posture-ladder.md` § Ratchet-down semantics (demotion emits `posture_change` only).
- Mint-state is a strictly additive interpretation of the field — every existing Phase-01 caller that writes `posture_level` writes it at envelope-mint time, so no Phase-01 production code changes.
- The mint-immutability invariant pins the Step 5b trust boundary: a malicious adapter cannot mutate posture_level on the in-flight envelope after the gate has signed the entry; the gate sees `prior_posture_level` AND the freshly-minted `new_posture_level` as distinct values via the `_PostureMutationResult`.

**Cons (real, not glossed):**

- "Read the envelope" is no longer sufficient to learn the current effective posture — operators MUST also know to walk the Ledger. This is a documented field-semantics requirement now (`specs/envelope-model.md` § Schema field semantics for `metadata.posture_level`), but a forgetful consumer could still call `envelope.metadata.posture_level` and get the mint-state value instead of the live one.
- The field has no production read consumer at Phase 01 — it is purely an audit annotation. The risk is the field becomes orphan over time. Mitigation: the spec field-semantics block names it as audit-only AND a Tier 1 test exercises the field read so the symbol is structurally non-orphan.

## What lands in this shard (RT-1 Shard 1)

1. **Spec edit in `specs/envelope-model.md` § Schema field semantics for `metadata.posture_level`:** explicit "Mint-state semantics" paragraph + "Audit-only role" sentence pinning the interpretation.

2. **Tier 2 test strengthening:** `tests/tier2/test_posture_gate_wiring.py::TestPostureChangeOnRatchetDownNoEnvelopeEdit` now asserts that `envelope.metadata.posture_level` is UNCHANGED on demotion (positive pin of mint-immutability).

3. **Tier 2 test addition:** new class `TestEnvelopePostureLevelIsMintStateOnRatchetUp` — ratchet-up returns a `_PostureMutationResult` whose `new_posture_level` reflects the NEW mint state, while the ORIGINAL envelope reference's `metadata.posture_level` stays at the prior mint-time value (mint-immutability invariant on the source envelope).

4. **Tier 1 test addition:** `TestPostureLevelMintStateRead` exercises the read path against a real envelope so the field is structurally non-orphan per `rules/orphan-detection.md` Rule 1.

## For Discussion

1. **Counterfactual:** if we had picked "current-effective-posture" interpretation, every demotion would have required an `envelope_edit` (to update the field to the new lower posture), breaking the asymmetric pairing in `specs/posture-ladder.md` § Ratchet-down and requiring a spec rewrite. The mint-state interpretation honors the spec as written — no spec contradiction, no Phase-01 caller migration. Was there a third interpretation we missed?

2. **Phase-03 verifier:** the spec field-semantics block names this as audit-only with no production read consumer. If a future independent verifier needs to cross-check the envelope's posture_level against the matching `posture_change` entry's `to_posture` at the same timestamp, where does that verifier live — in `envoy/envelope/` (envelope-side) or `envoy/ledger/` (audit-side)? Per `journal/0021` § "Cross-references" it would extend `independent-verifier.md`. Not load-bearing for RT-1 Shard 1.

3. **Documentation surface:** the field's audit-only role is documented in `specs/envelope-model.md` field-semantics. Should we also annotate `EnvelopeMetadata.posture_level` in code (docstring on the dataclass field) to surface the mint-state semantics at the import site? Disposition: deferred — `EnvelopeMetadata` is a frozen dataclass whose docstring already reads from the spec; adding inline annotation risks spec/code drift per `rules/specs-authority.md` Rule 9.

## Cross-references

- `workspaces/phase-01-mvp/journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md` § "For Discussion" #2 — the ambiguity this entry closes.
- `specs/envelope-model.md` § Schema field semantics for `metadata.posture_level` — the canonical spec text after this disposition.
- `specs/posture-ladder.md` § Ratchet-up + § Ratchet-down (lines 31-52) — the spec authority for the asymmetric pairing.
- `tests/tier2/test_posture_gate_wiring.py::TestPostureChangeOnRatchetDownNoEnvelopeEdit` — the strengthened mint-immutability assertion on demotion.
- `tests/tier2/test_posture_gate_wiring.py::TestEnvelopePostureLevelIsMintStateOnRatchetUp` — new positive pin on ratchet-up mint-state minting.
- `rules/zero-tolerance.md` Rule 3 — no silent fallback; the spec field-semantics block names the audit-only role explicitly.
- `rules/orphan-detection.md` Rule 1 — the Tier 1 read test prevents the field from becoming structurally orphan.
- Round 1 /redteam audit: F-4 (HIGH) — the surfacing of the ambiguity that drove this DECISION.
