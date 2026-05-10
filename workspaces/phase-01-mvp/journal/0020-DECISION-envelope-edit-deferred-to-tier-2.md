---
type: DECISION
date: 2026-05-10
created_at: 2026-05-10T00:00:00Z
author: agent
session_id: phase-01-wave-2-implement-t-02-31
session_turn: 5
project: phase-01-mvp
topic: envelope_edit Ledger entry pairing on ratchet-up deferred to T-02-33 (Tier 2 wiring)
phase: implement
tags:
  [
    posture-gate,
    t-02-31,
    t-02-33,
    envelope-edit,
    spec-accuracy,
    deviation-acknowledgment,
    wave-2,
  ]
---

# DECISION: envelope_edit Ledger pairing deferred from T-02-31 to T-02-33

T-02-31 (PostureGate, commit `74d66d0` on branch `feat/phase-01-T-02-31-posture-gate`) implements the 5-step fail-closed posture transition gate per `specs/posture-ladder.md` § Algorithm. The reviewer's gate-review pass surfaced one MEDIUM finding that this entry resolves: spec line 41 mandates that ratchet-up writes BOTH a `posture_change` Ledger entry AND a paired `envelope_edit` Ledger entry. T-02-31 emits ONLY the `posture_change` entry.

## What the spec says (spec line 41)

> Envelope version bump (specs/envelope-model.md) — new posture is part of the envelope schema; any posture change is an `envelope_edit`.

## What T-02-31 ships

`PostureGate.request_transition` (Step 5) emits a single `posture_change` Ledger entry per `specs/ledger.md` § posture_change schema (lines 239-253). The wire shape is byte-for-byte spec-compliant for the `posture_change` entry; the paired `envelope_edit` is absent.

## Why it was deferred

The `envelope_edit` Ledger entry per `specs/ledger.md` § envelope_edit (separately documented in that spec) requires:

1. A live `EnvelopeCompiler` reference at the call site (PostureGate currently has only `_LedgerProtocol` + `_RevokeHook` as DI surfaces).
2. A real `EnvoyLedger` instance threaded through with the envelope-version chain wired (the Phase-01 in-memory `EnvoyLedger` does support `append()`, but the envelope-version chain itself is not yet a load-bearing surface).
3. Coordination with the envelope's `metadata.posture_level` field (which is a Phase-01 envelope schema attribute the compiler writes; PostureGate cannot mutate the envelope without the compiler).
4. A new `_EnvelopeProtocol` DI surface on PostureGate (or a refactor passing the envelope through `request_transition`).

Adding all four to T-02-31 would push the shard out of capacity (`rules/autonomous-execution.md` MUST Rule 1 — ≤5-10 invariants). T-02-33 (Tier 2 wiring) is the natural landing site because:

- Tier 2 wiring already constructs a real `EnvoyLedger` against a real Trust store fixture.
- Tier 2 wiring exercises `EnvelopeCompiler.compile()` end-to-end (T-01-11 already shipped this pattern at `tests/tier2/test_envelope_compiler_wiring.py`).
- The envelope's `metadata.posture_level` field write fits naturally inside the compile path's posture-aware compilation step.

## Alternatives considered

| Alternative                                                              | Why rejected                                                                                                                                                                                                            |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Implement `envelope_edit` emission in T-02-31 alongside `posture_change` | Out of capacity (~150 LOC additional + new DI surface + new envelope-mutation contract). Per Rule 1 the shard is at ~190 LOC load-bearing today; adding envelope_edit would push to ~340 LOC and add 3+ new invariants. |
| Defer the entire posture-ratchet gate to T-02-33                         | Pushes the load-bearing 5-step fail-closed enforcement out of Phase-01 wave-2; downstream consumers (CLI `envoy posture` T-05-90, Weekly Posture Review T-04-XX) need PostureGate before T-02-33 lands.                 |
| Ship `envelope_edit` as a stub raising `NotImplementedError`             | Violates `rules/zero-tolerance.md` Rule 2 (no stubs in production code).                                                                                                                                                |
| Document deferral inline with no successor shard                         | Violates `rules/spec-accuracy.md` Rule 5 (incremental spec-extension workflow) — a deviation without a named-successor shard becomes silent drift.                                                                      |

## Disposition (what landed in this fix-commit)

Per `rules/specs-authority.md` Rule 6 (deviation acknowledgment), the deferral is documented at THREE surfaces in this same fix-commit per `rules/autonomous-execution.md` Rule 4 (same-bug-class fits one shard):

1. **`envoy/authorship/posture_gate.py` module docstring** — narrow-scope section adds a 5-line block naming the deferral and pointing to T-02-33 + this journal entry.
2. **`specs/posture-ladder.md`** — new `## Out of scope (this phase)` section before `## Test location` (per `rules/spec-accuracy.md` Exception 1 — bounded out-of-scope sections, not gap trackers) explicitly enumerating `envelope_edit` (with successor T-02-33), cooling-off TIMER (Phase 03), annual decay scheduler (Phase 03), per-dimension scope (Phase 03), Shared Household composition (Phase 03+), and `PostureAnnualDecayPendingError` (Phase 03).
3. **`workspaces/phase-01-mvp/todos/active/02-wave-2-...md` § T-02-33** — to be updated in this fix-commit to add an acceptance bullet: "Per `journal/0020-...md`, T-02-33 wires the paired `envelope_edit` Ledger entry on ratchet-up (currently absent in T-02-31's `posture_change`-only emission)."

## Risk this entry pins

The latent risk: **deferring the second-half of a paired Ledger contract creates a window where forensic recovery from `posture_change` entries alone cannot reconstruct the envelope-version chain**. A Phase-01 verifier walking the chain sees `posture_change` entries with `from_posture`/`to_posture` but cannot bind those to the envelope schema version that was active. T-02-33 closes this by emitting the paired `envelope_edit` with the envelope's content_hash + version bump.

Mitigation in the interim: Phase-01 single-device single-principal topology means only ONE active envelope at any time; the `posture_change` entry's `signed_by="genesis_key"` + Ledger envelope-level signature still binds the transition to the device. The reconstruction gap is bounded to "which envelope schema version was active when this transition fired", which is non-load-bearing for Phase-01 ship gates.

## Cross-references

- `specs/posture-ladder.md` § Out of scope (this phase) — the bounded-deferral surface this journal entry corresponds to.
- `specs/posture-ladder.md` § Ratchet-up requirement #3 — the spec mandate this defers.
- `envoy/authorship/posture_gate.py` module docstring narrow-scope — the implementation acknowledgment.
- `workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md` § T-02-33 — the named successor shard.
- `rules/spec-accuracy.md` Exception 1 + Rule 5 — the structural authority for bounded out-of-scope sections.
- `rules/specs-authority.md` Rule 6 — the deviation-acknowledgment requirement.
- `rules/autonomous-execution.md` MUST Rule 1 (capacity budget) + Rule 4 (same-bug-class within shard).
- Reviewer report (PR #19 gate review) F-1 — the finding this entry resolves.

## For Discussion

1. The reviewer surfaced this finding only at the gate-review stage AFTER the implementation shipped. The original spec-pass at /implement time did identify the spec lines 35-42 as "ratchet-up requires ALL of" four conditions — but the implementation's narrow-scope docstring only acknowledged THREE of them (cooling-off, annual_decay, multi-step) and missed the envelope_edit fourth. Should the implementer's "narrow-scope deferrals" docstring section be REQUIRED to enumerate every spec section's "requires ALL of" / "MUST" clauses with explicit DEFERRED / IMPLEMENTED status, so missing-acknowledgment cases like this one become structurally visible at code-review time rather than gate-review time? (Counterfactual: had the docstring at line 27-35 listed all 4 ratchet-up clauses with status, the missing 4th would have surfaced at the implementer's own self-review.)

2. The deferral disposition (acknowledge in spec § Out of scope + journal + successor-shard acceptance bullet) is the SAME shape as the `12-spec-citation-hygiene.md` Phase-A/B split applied earlier in this session. Both turn "spec promises X but code doesn't ship X yet" into a tracked deferral with named successor. Should `rules/specs-authority.md` formalize this as the canonical "deviation-with-successor" pattern (currently described loosely in Rule 6), with a structural template (3 surfaces: spec § Out of scope, journal DECISION, successor-shard acceptance bullet)?

3. Phase-01 verifier walks the Ledger chain and sees `posture_change` entries WITHOUT paired `envelope_edit` entries until T-02-33 ships. A future verifier walking a Ledger that includes both pre-T-02-33 (posture_change-only) and post-T-02-33 (paired) entries needs to handle the asymmetry. Should T-02-33 emit a one-time `MigrationAnnouncement` Ledger entry (per `specs/ledger.md` § MigrationAnnouncement schema) at first activation to mark the cutover, OR should the verifier be tolerant by design (treat absent `envelope_edit` for entries before timestamp T as "Phase-01-only ledger")? The forensic recovery contract at `specs/ledger.md` § Halted state argues for explicit cutover marking.
