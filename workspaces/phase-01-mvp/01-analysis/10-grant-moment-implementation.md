# 10 — Grant Moment Implementation

**Document role:** Phase 01 implementation deep-dive for the Grant Moment primitive (shard 10 of /analyze; Group C per `01-shard-plan.md` § 5; depends on shards 4, 5, 6, 8). Establishes the verified upstream provider, the Envoy-new-code orchestrator surface, the 3-resolution-shape state machine, the cascade-revocation glue, the channel-handoff contract, and the integration points to neighbouring primitives. The Grant Moment is the EC-2 owner: 3 resolution shapes (approve / decline / approve-with-modification) MUST execute end-to-end with cascade revocation working.

**Date:** 2026-05-03 (shard 10 of /analyze).
**Status:** DRAFT — load-bearing for shards 11 (Daily Digest reads grant outcomes), 12 (Budget tracker fires Grant Moments via threshold callback), 16 (Channel adapters host the dialog UI surface).
**Discipline:** Cite, do not paraphrase frozen specs. Per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, Phase 01 /analyze MUST cite Phase 00 artifacts by path + section, never paraphrase. The shard's question is NEVER "is this spec right?"; it is "given this spec is frozen, how do I wire `kailash-py` to deliver it?" Per `rules/specs-authority.md` MUST Rule 4 + Rule 5b (no spec edits at this shard).

**Capacity check:** 1 primitive, 3 source specs (`grant-moment.md`, `envelope-model.md` cross-spec, `ledger.md` cross-spec, `trust-lineage.md` cross-spec for cascade), ~6 invariants tracked (3-shape state-machine completeness; signed-consent JCS-NFC byte determinism; cascade-revocation BFS reaches every descendant; channel-handoff contract is a function not a UI; mid-conversation pause-resume composition with PlanSuspension; primary-channel binding for high-stakes), ≤4 cross-primitive references (Envelope compiler, Trust store, Ledger, Channel adapters). Within `rules/autonomous-execution.md` budget.

---

## 1. Source spec citation

Frozen specs the Grant Moment implements against (cited; not edited):

- `specs/grant-moment.md` § Schema § `GrantMomentRequest` (lines 15–47) — wire format constructed at M0 and dispatched to channel adapters at M1; canonical-JCS-signed by the requesting `delegation_key`; signature scope = entire request minus `signature_by_delegator_hex`.
- `specs/grant-moment.md` § Schema § `GrantMomentResult` (lines 49–70) — wire format the channel adapter returns at M3; canonical-JCS-signed by `delegation_key` on Approve / Approve+author; **no key signing for Deny** ("signed Ledger entry only" per line 51).
- `specs/grant-moment.md` § State machine (line 74) — `M0 construct → M1 render (all active channels) → M2 await decision (5min default; per-envelope override) → M3 sign or decline → M4 complete`.
- `specs/grant-moment.md` § Rendering (lines 78–86) — every dialog shows visible secret + proposed action + why asking + consequence preview + 4 options (Approve once / Approve+author / Deny / Modify).
- `specs/grant-moment.md` § Novelty-aware friction (T-019, lines 88–92) — novel patterns require 5s read-delay + double-tap + cross-channel confirm for high-stakes; primary-channel binding for high-stakes.
- `specs/grant-moment.md` § Velocity-raise ratchet (T-093 R2-H4, lines 94–96) — velocity-raise CANNOT be approved inline; requires Weekly Posture Review OR cross-channel Grant Moment with 24h cooling-off.
- `specs/grant-moment.md` § Timeout (lines 102–104) — default 5min; identical behaviour between real + honeypot paths; queue back-pressure after N parallel.
- `specs/grant-moment.md` § Produced artifact (lines 106–108) — "Signed `DelegationRecord` per specs/trust-lineage.md + Phase A intent per specs/ledger.md §two-phase signing" — the Grant Moment does not define a new persistence layer; it composes Trust Lineage + Ledger.
- `specs/grant-moment.md` § Error taxonomy (lines 110–123) — 10 typed errors; load-bearing for fail-closed semantics under timeouts, channel hangs, replay, visible-secret mismatch, novelty-friction bypass, back-pressure overflow, and cross-channel confirm failure.
- `specs/grant-moment.md` § Cross-references (lines 125–134) — the spec explicitly forwards to `envelope-model.md`, `trust-lineage.md`, `ledger.md`, `channel-adapters.md`, `boundary-conversation.md`, `weekly-posture-review.md`, `budget-tracker.md`, `threat-model.md`. The Grant Moment is the orchestration surface that ties these together.

Cross-spec citations (not Grant Moment-owned, but the Grant Moment consumes / writes / reads them):

- `specs/envelope-model.md` § Schema (lines 16–84) — the 5-dimension `EnvelopeConfig`; the Grant Moment's "approve_and_author" decision triggers a child-envelope compile via the Envelope compiler (shard 4 § 5 row 2).
- `specs/envelope-model.md` § Algorithms § Canonical JSON (line 98+) — RFC 8785 JCS + NFC normalization; signed-consent records canonicalized via this exact algorithm per `specs/grant-moment.md` line 72 ("Both schemas are canonicalized via specs/envelope-model.md §Canonical JSON; cross-runtime byte-identity per BET-6").
- `specs/ledger.md` § Entry envelope schema (lines 14–34) — every Grant Moment outcome is a Ledger row; the envelope shape is locked at the Ledger layer, not at the Grant Moment layer.
- `specs/ledger.md` § Ledger entry schemas § `grant_moment` (lines 350–364) — the Ledger-row form persisted after M3 sign-or-decline. Fields: `request_ref`, `result_ref`, `intent_id`, `decision` (one of 4 enum values: `approve_once | approve_and_author | deny | modify`), `decided_at`, `envelope_version_at_decision`, `novelty_class`, `signed_by: delegation_key`.
- `specs/ledger.md` § Ledger entry schemas § `PhaseARecord` (lines 366–380) — pre-execution Phase A intent envelope; `intent_id`, `tool_name`, `tool_args_canonical_hash`, `envelope_version`, `envelope_check_passed: true`, `phase_a_at`, `ttl_expires_at`, `signed_by: delegation_key`.
- `specs/ledger.md` § Ledger entry schemas § `PhaseBRecord` (lines 382–397) — post-execution outcome; `intent_id`, `phase_a_ref`, `outcome` (success | failure | partial), `outcome_summary_hash`, `phase_b_at`, `signed_by: runtime_device_key`.
- `specs/ledger.md` § Ledger entry schemas § `PhaseAOrphanResolution` (lines 399–414) — at next session start, orphan Phase A (no Phase B within 30d TTL) surfaces as this record; `phase_a_ref`, `intent_id`, `resolution` (retry_idempotent | record_as_failed | investigate), `user_decision_grant_ref`, `resolved_at`, `signed_by: runtime_device_key`.
- `specs/trust-lineage.md` § Schema § DelegationRecord (lines 36–54) — `signature_by_delegator_hex` covers canonical form excluding itself; covers `type`, `schema_version`, `chain_parent_id`, `nonce`, `envelope_version`, `effective_envelope_hash`, `enterprise_context`, `sub_agent_derivation`. The Grant Moment is one of two production write paths into `DelegationRecord` (the other is the Boundary Conversation Genesis-seeding path per shard 5 § 5).
- `specs/trust-lineage.md` § Algorithms § Cascade revocation (lines 80–85) — kailash-py BFS walker at `src/kailash/trust/revocation/cascade.py`; kailash-rs DFS recursion at `crates/eatp/src/delegation.rs:807`; **BFS/DFS parity: return SETs are equal (contractual); Ledger ordering may differ**; atomic within a single Trust Vault transaction; cross-device divergence handled by Ledger CRDT merge (specs/ledger-merge.md). CHARTER §41 mandates cascade revocation as a hard constraint.
- `specs/trust-lineage.md` § Algorithms § Nonce per-principal partitioning (§6.1 C-02 fix, lines 94–99) — `nonces[principal_genesis_id]` separate table per principal; sliding 90-day FIFO; T-008 nonce defense.
- `specs/boundary-conversation.md` § PlanSuspension (cross-spec via shard 8) — when a Grant Moment fires DURING a Boundary Conversation, the conversation pauses with a `PlanSuspension` and resumes when the Grant Moment resolves at M4. Composition is "first-class" — the Grant Moment is not a UI modal blocking the conversation; it is a state-machine peer that the conversation observes.

---

## 2. Verified provider citation

Per `03-kailash-py-mvp-readiness.md` § 5 verification protocol — the Grant Moment is **A-grade upstream** at the 2026-04-21 baseline (per § 3 row 7); the freshness gate confirmed no regression as of 2026-05-03.

### 2.1 Direct providers (verified in shards 4, 5, 6 — re-cited here)

| Capability the Grant Moment requires                                                         | Provider module                                                                                                                                                                                           | Shard verified | Closed ISS / PR                                                         |
| -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | ----------------------------------------------------------------------- |
| Ed25519 signing of `GrantMomentRequest` + `GrantMomentResult`                                | `kailash.trust.signing.crypto.sign(...)` / `verify_signature(...)` (lines 120, 168)                                                                                                                       | Shard 5 § 2.2  | n/a — present pre-Phase 00                                              |
| Canonical-JSON serialization for signature scope                                             | `kailash.trust.signing.crypto.serialize_for_signing(...)` (line 223); also used by Envoy-side `envoy.ledger.canonical.canonical_dumps` per shard 6 § 3.2                                                  | Shard 6 § 3.2  | #757 / #756 (Unicode pinning) — closed Apr 25                           |
| Algorithm-identifier embedding on every signed record                                        | `kailash.trust.signing.algorithm_id.AlgorithmIdentifier` (lines 1–162; default `"ed25519+sha256"`)                                                                                                        | Shard 5 § 3.4  | ISS-32 / #604 — closed 2026-04-25T14:43:55Z                             |
| Cascade revocation (BFS walker; atomic snapshot/rollback)                                    | `kailash.trust.revocation.cascade.cascade_revoke(agent_id, store, reason, revoked_by, broadcaster, delegation_registry)` (line 154) returning `RevocationResult(success, events, revoked_agents, errors)` | Shard 5 § 3.3  | ISS-05 / #595 — closed 2026-04-25 (docstring cross-ref improvement)     |
| Envelope intersection for "approve-with-modification" child-envelope compile                 | `kailash.trust.pact.envelopes.intersect_envelopes(a, b, *, dimension_scope=None)` (line 336)                                                                                                              | Shard 4 § 2    | ISS-02 / #594 — closed 2026-04-24T17:01:13Z (semantic parity confirmed) |
| Monotonic-tightening enforcement for child envelope                                          | `kailash.trust.pact.envelopes.RoleEnvelope.validate_tightening(...)` (line 437) with `_validate_finite()` NaN/Inf guards                                                                                  | Shard 4 § 2    | n/a — present pre-Phase 00; PACT security invariant 5                   |
| DelegationRecord persistence                                                                 | `kailash.trust.chain.DelegationRecord` (line 222 of `chain.py`) + `kailash.trust.chain_store.sqlite.SqliteTrustStore` (line 55)                                                                           | Shard 5 § 2.2  | ISS-12 / #597 — closed 2026-04-24T17:02:09Z                             |
| Ledger-row append (`grant_moment`, `PhaseARecord`, `PhaseBRecord`, `PhaseAOrphanResolution`) | `envoy.ledger.EnvoyLedger.append(entry_type, content, *, intent_id, content_trust_level)` (Envoy-new-code per shard 6 § 4) wrapping `kailash.trust.audit.AuditStore`                                      | Shard 6 § 4    | #707 / #711 (`df.transaction()`) — closed Apr 25                        |

### 2.2 The "Grant Moment defines no new persistence layer" finding

Per `specs/grant-moment.md` § Produced artifact (lines 106–108) read literally: "Signed `DelegationRecord` per specs/trust-lineage.md + Phase A intent per specs/ledger.md §two-phase signing." The signed-consent record IS a Ledger entry (`grant_moment` type per `specs/ledger.md` line 59 + lines 350–364); the produced grant IS a `DelegationRecord` (per `specs/trust-lineage.md` § Schema). The Grant Moment **composes** these two; it does NOT define a third persistence layer.

This collapses the "What's the signed-consent record format?" design question (key design question #3 in the shard prompt): the format is fixed by the cross-references — `GrantMomentRequest` (12-field schema, JCS+NFC, Ed25519-signed by `delegation_key`) at M0 → `GrantMomentResult` (10-field schema, JCS+NFC, Ed25519-signed by `delegation_key` for approve/modify, unsigned for deny) at M3 → `grant_moment` Ledger row (8-field schema with `request_ref` and `result_ref` pointers) persisted at M4. The two pointer fields (`request_ref`, `result_ref`) preserve the wire-format-canonicalized originals byte-for-byte; the Ledger row is the operational index, the wire formats are the cryptographic evidence.

### 2.3 Indirect-closure PR refs that improve Grant Moment determinism

- **#672** — Python `format_record_id_for_event` cross-SDK with kailash-rs BP-048. Effect: every Grant Moment Ledger entry whose content references a classified-PK model routes through the helper. The 8-hex SHA-256 prefix shape is identical Python ↔ Rust per `rules/event-payload-classification.md` Rule 1 + Rule 2.
- **#731** — TraceEvent timestamp microsecond padding cross-SDK. Effect: `decided_at`, `phase_a_at`, `phase_b_at`, `resolved_at`, `ttl_expires_at` are all microsecond-padded identically; the JCS canonical form of a `GrantMomentResult` produced on macOS at `T10:00:00.123Z` is byte-equal to one produced on Linux at the same instant (no `.123000` vs `.123000000` divergence).
- **#707 / #711** — `df.transaction()` context manager. Effect: the (`PhaseARecord` write + Trust-store `DelegationRecord` insert + `grant_moment` Ledger row) tuple is atomic; a power-loss between the three leaves the system in a state where either all-three or none persisted.

### 2.4 What `kailash-py` does NOT provide — Envoy-new-code surface preview

`kailash-py` does NOT provide:

1. The 3-resolution-shape state machine orchestrator (M0→M4 with branching at M3 by decision enum).
2. The channel-handoff dispatch — `request_grant_moment(envelope_violation, channel) → resolution` is an Envoy-side coordination contract.
3. The composition glue between Boundary Conversation `PlanSuspension` and Grant Moment M2 await (the cross-primitive pause-resume).
4. The Grant Moment-driven path INTO `cascade_revoke(...)` — the upstream cascade primitive is the descender, but the user-driven revoke decision (the "this descendant grant should die because I'm revoking the originating grant" finding) is Envoy-side.
5. The novelty-class classifier (novel | familiar_repeat | high_stakes) — cross-references `specs/budget-tracker.md` velocity ratchet + `specs/envelope-library.md` template provenance for "is this an unseen recipient / unseen tool / new dollar range / new N-gram" detection.
6. The visible-secret render-side check (`VisibleSecretMismatchError` per `specs/grant-moment.md` line 120) — Trust-Vault stored secret vs render-time bytes.

These six items are the Envoy-new-code surface; § 3 below itemises them.

---

## 3. Envoy-new-code surface

The Envoy-new-code surface is the gap between (a) the upstream `kailash-py` primitives that sign / persist / cascade and (b) the `specs/grant-moment.md` 3-shape orchestrator + channel-handoff + mid-conversation-pause contract. The orchestrator IS the Grant Moment primitive; everything else is composition.

### 3.1 Module shape: `envoy.grant_moment` orchestrator composing upstream

The Phase 01 Envoy-new-code surface is a Python package `envoy.grant_moment` exposing the facade `GrantMomentOrchestrator`. The package composes:

- `kailash.trust.signing.crypto.sign / verify_signature` (Shard 5 § 2.2) — for signing scope per `specs/grant-moment.md` § Schema (request and result wire formats).
- `kailash.trust.signing.algorithm_id.AlgorithmIdentifier` (Shard 5 § 3.4) — embedded on every signed record via the same `_with_algorithm_id()` helper pattern that `TrustStoreAdapter` uses (Shard 5 § 4).
- `envoy.envelope.compiler.EnvelopeCompiler` (Shard 4 § 4) — invoked on Approve+author and Modify decisions to compile a tighter child envelope; the compiler internally calls `RoleEnvelope.validate_tightening` so the Grant Moment cannot widen the parent envelope.
- `envoy.ledger.EnvoyLedger.append(...)` (Shard 6 § 4) — single-point write boundary for `PhaseARecord` (M0 emit), `grant_moment` Ledger row (M4 emit), `PhaseBRecord` (post-execution, written by the runtime at the tool-execution callback), and `PhaseAOrphanResolution` (next-session-start sweep).
- `envoy.trust.TrustStoreAdapter.record_delegation(...)` and `.revoke(...)` (Shard 5 § 4) — DelegationRecord persistence on Approve / Approve+author / Modify; cascade-revocation glue on user-driven revoke.

Per `rules/orphan-detection.md` Rule 1 + Rule 3, the `GrantMomentOrchestrator` is the single facade exposed on the framework's top-level surface (`envoy.grant_moment` namespace); every other class in the module is reached through it.

### 3.2 Surface to be built (Envoy-new-code)

1. **`envoy.grant_moment.GrantMomentOrchestrator`** — facade with `.request_grant_moment(envelope_violation, channel) → GrantMomentResolution`, `.resolve(request_id, decision_payload) → DelegationRecord | None`, `.revoke(grant_id, reason) → RevocationResult` (cascade-driven), `.next_session_orphan_sweep() → list[PhaseAOrphanResolution]`. Composes upstream signing + Envoy compiler + Envoy ledger + Trust store adapter.

2. **`envoy.grant_moment.state_machine.GrantMomentState`** — pure-data state machine implementing M0 → M1 → M2 → M3 → M4 per `specs/grant-moment.md` § State machine (line 74). States: `CONSTRUCTED` (M0), `RENDERING` (M1), `AWAITING_DECISION` (M2 — bounded by `timeout_seconds`, default 300s), `SIGNING_OR_DECLINING` (M3), `COMPLETE` (M4), `EXPIRED` (M2 timeout fired), `BACK_PRESSURED` (queue ceiling exceeded). Transitions are gated by typed events (`DialogRendered`, `UserDecided`, `TimeoutFired`, `ChannelHung`, `BackPressureBlocked`).

3. **`envoy.grant_moment.resolution.ResolutionShape` (the 3-shape contract per EC-2)** — sealed enum with 3 variants matching the 4 spec decisions per `specs/grant-moment.md` line 58 mapped onto the EC-2 acceptance gate per `02-mvp-objectives.md` lines 31–43:
   - **`Approve`** (covers `approve_once` + `approve_and_author` from the spec — the EC-2 acceptance gate calls these one resolution shape because both produce a signed `DelegationRecord`; `approve_and_author` ALSO triggers a child-envelope compile to capture the new authored constraint persistently). Effect: `record_delegation(...)` writes `DelegationRecord`; `EnvoyLedger.append("grant_moment", ...)` writes the Ledger row with `decision: "approve_once" | "approve_and_author"`. On `approve_and_author`, the Envelope compiler is also invoked with the `author_payload.new_constraint` to mint a child envelope; per `specs/grant-moment.md` line 62 the constraint MUST pass `novelty_check_passed` and `minimum_impact_passed` (both are pre-computed and embedded in the result; the compiler enforces them as inputs to `RoleEnvelope.validate_tightening`).
   - **`Decline`** (= `deny` from the spec). Effect: NO `DelegationRecord` written (per `specs/grant-moment.md` line 51 "by no key (Deny — signed Ledger entry only)"); NO envelope mutation; ONLY a `grant_moment` Ledger row with `decision: "deny"`. Per `specs/grant-moment.md` § Cross-references, the Boundary Conversation re-prompt path is the Boundary Conversation's concern, not the Grant Moment's.
   - **`ApproveWithModification`** (= `modify` from the spec). Effect: the `result.modify_payload.new_args_canonical` replaces the original `request.tool_args_canonical`; a fresh `intent_id = sha256(new_args_canonical_hash + nonce)` is computed; `DelegationRecord` is written carrying the modified args via `effective_envelope_hash`; the Envelope compiler is invoked with a tighter dimension constraint that captures the user's narrowing decision (per shard 4 § 5 row 2 "compile a tighter child envelope per shard 4's `intersect_envelopes`"). This is the **only** of the 3 shapes that mutates the envelope structurally **without** the user requesting a persistent author rule (`approve_and_author` does that); `modify` is action-scoped, `approve_and_author` is rule-scoped.

   The mapping from spec's 4 decisions to EC-2's 3 shapes:

   | Spec decision (`specs/grant-moment.md` line 58) | EC-2 resolution shape     | Envelope mutation?                                              | DelegationRecord written?                | Ledger entries                                                                                                |
   | ----------------------------------------------- | ------------------------- | --------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
   | `approve_once`                                  | `Approve`                 | No                                                              | Yes (action-scoped)                      | `PhaseARecord` + `grant_moment` (decision="approve_once")                                                     |
   | `approve_and_author`                            | `Approve`                 | Yes (child compile via Envelope compiler with `new_constraint`) | Yes                                      | `PhaseARecord` + `grant_moment` (decision="approve_and_author") + `envelope_edit`                             |
   | `deny`                                          | `Decline`                 | No                                                              | No (per `specs/grant-moment.md` line 51) | `grant_moment` (decision="deny") only                                                                         |
   | `modify`                                        | `ApproveWithModification` | Yes (child compile with tighter args-canonical)                 | Yes (with modified args)                 | `PhaseARecord` (with new intent_id over modified args) + `grant_moment` (decision="modify") + `envelope_edit` |

   Per `rules/zero-tolerance.md` Rule 6 (Implement Fully): all 3 shapes (4 spec decisions) MUST execute end-to-end at Phase 01 ship; partial implementation is BLOCKED. The EC-2 acceptance gate per `02-mvp-objectives.md` line 42 is the structural test.

4. **`envoy.grant_moment.violation_detector.OutOfEnvelopeDetector`** — interceptor wrapping the `kailash.kaizen` tool-call surface (BaseAgent / ToolNode hot path per `02-kailash-py-survey.md` item 13) such that EVERY tool call evaluated against the active `EffectiveEnvelope` (per `kailash.trust.pact.envelopes.compute_effective_envelope` from shard 4 § 2) flows through this detector. The detector returns `EnvelopeViolation | None`; on `EnvelopeViolation`, the Kaizen agent's tool dispatch is suspended (`PlanSuspension`-shaped) and the Grant Moment orchestrator is invoked.

   This collapses key design question #5 (out-of-envelope detection): the **interceptor wrapping every tool call** is the answer. The Envelope compiler does NOT detect violations (it produces the envelope), the Kaizen runtime does NOT detect violations (it executes tools), the dedicated `OutOfEnvelopeDetector` mediates by composing both. The detector lives in `envoy.grant_moment` because it is the Grant Moment's structural prerequisite — without it, no violation surfaces and no Grant Moment fires.

5. **`envoy.grant_moment.channel_handoff.ChannelHandoff` API** — pure-function dispatch contract `request_grant_moment(envelope_violation: EnvelopeViolation, channel: ChannelAdapterRef) → GrantMomentResolution`. The function:
   1. Constructs `GrantMomentRequest` at M0 (sign with `delegation_key`).
   2. Dispatches to `channel.render_grant_moment(request)` (the channel adapter's contract per shard 16 — UI rendering is the channel's concern).
   3. `await`s the channel's `result_future` with timeout = `request.timeout_seconds`.
   4. On result: validates the signature (Approve / Approve+author / Modify) or absence-of-signature (Deny per `specs/grant-moment.md` line 51); maps to `ResolutionShape`; returns.
   5. On timeout: emits `GrantMomentExpiredError`; emits a `grant_moment` Ledger row with `decision: "expired"` (per `specs/grant-moment.md` § Error taxonomy line 114; the Ledger row is the audit trail even on expiry).

   This collapses key design question #2 (channel surface): the Grant Moment orchestrator's contract with channels is a **function call** (`render_grant_moment` returns a `result_future`), NOT a UI library. The channel adapter (shard 16) hosts the rendering; the Grant Moment hosts the orchestration. Symmetric across all 8 channels (CLI + Web + 6 messaging) per EC-7 acceptance.

   **Primary-channel binding**: per `specs/grant-moment.md` line 92 ("primary-channel binding — high-stakes Grant Moments render ONLY on user's designated primary channel"), high-stakes Grant Moments raise `NotPrimaryChannelError` per line 117 if dispatched to a non-primary channel. The orchestrator MUST check `request.primary_only` against `channel.is_primary` before dispatching; the channel name in the error message follows `channel-adapters.md` H-03.

6. **`envoy.grant_moment.signed_consent.SignedConsentBuilder`** — single-point construction of `GrantMomentRequest` and `GrantMomentResult` per the wire formats. Responsibilities:
   1. Compute `tool_args_canonical_hash` via `envoy.ledger.canonical.canonical_dumps` (same JCS+NFC pipeline as the Ledger; cross-runtime byte-identity per BET-6 — shared pipeline IS the structural defense against drift).
   2. Compute `intent_id = sha256(tool_args_canonical_hash || nonce || envelope_hash)` per `specs/grant-moment.md` line 28 + `specs/trust-lineage.md` § Algorithms § Nonce per-principal partitioning (nonce drawn from `nonces[principal_genesis_id]` to satisfy T-008).
   3. Embed `algorithm_identifier` via `_with_algorithm_id(...)` helper pattern (Shard 5 § 3.4).
   4. Sign canonical-form bytes via `kailash.trust.signing.crypto.sign(canonical_bytes, delegation_private_key)` for Approve / Approve+author / Modify; produce **unsigned** result envelope for Deny (per `specs/grant-moment.md` line 51).
   5. Verify the visible-secret bytes match the Trust-Vault stored secret; on mismatch, raise `VisibleSecretMismatchError` (per line 120) and refuse render. The visible-secret check is structural — the Grant Moment orchestrator receives the rendered visible-secret bytes from the channel adapter and compares them against `TrustStoreAdapter.get_visible_secret(principal_id)` (a Trust-Vault region read).

7. **`envoy.grant_moment.cascade.CascadeRevocationOrchestrator`** — wraps `kailash.trust.revocation.cascade.cascade_revoke(...)` per Shard 5 § 3.3 + `specs/trust-lineage.md` § Algorithms § Cascade revocation. Responsibilities:
   1. Accept a user-initiated revocation (typically via Daily Digest "your N grants — revoke any?" or via a fresh Grant Moment with `decision: "deny"` referencing the originating grant).
   2. Resolve the grant's `chain_parent_id` graph from the Trust store — the `delegation_registry` argument to `cascade_revoke` is the registry of all descendants reachable from the target.
   3. Call `cascade_revoke(agent_id=target, store=SqliteTrustStore, reason=user_text, revoked_by=principal_genesis_id)`.
   4. Receive `RevocationResult.revoked_agents` (the BFS set of all descendants).
   5. Emit ONE `RevocationRecord` Ledger entry per the cascade (signed by Genesis key per `specs/trust-lineage.md` § Schema § RevocationRecord line 60); payload includes `cascade_target_count`, `cascade_target_ids`.
   6. Verify `verify_cascade_complete(revocation_id)` (shard 5 § 3.3 contract) — ALL descendants in the lineage graph are present in the result set; defense against malformed `delegation_registry` under-reporting descendants.

   This collapses key design question #4 (cascade revocation timing): the cascade is **synchronous within a single Trust Vault transaction** per `specs/trust-lineage.md` line 85 ("Atomic within a single Trust Vault transaction"). EC-2 acceptance per `02-mvp-objectives.md` line 42 ("cascade-revocation of any descendant grant when the originating grant is revoked") AND EC-8 acceptance per `02-mvp-objectives.md` line 117 ("cascade revocation of a Day-1 grant correctly revokes a Day-6 child grant initiated from a different channel") are both structurally testable: the cross-channel descendant grant is reachable via `chain_parent_id` regardless of the channel that originated it; the BFS walker is channel-agnostic.

8. **`envoy.grant_moment.boundary_pause.PlanSuspensionBridge`** — composition glue with the Boundary Conversation primitive (shard 8) per the spec's M0→M4 state machine. Responsibilities:
   1. Detect that an active Boundary Conversation `PlanSuspension` (per `02-kailash-py-survey.md` item 13 + ISS-13 / #598 closure on PlanSuspension parity, 2026-04-25) is the parent of the Grant Moment fire.
   2. On Grant Moment M0 (construct), notify the Boundary Conversation that a child Grant Moment has spawned; the conversation enters PAUSED state, holding its Kaizen agent context.
   3. On Grant Moment M4 (complete), notify the Boundary Conversation with the `ResolutionShape` outcome; the conversation resumes from the suspended `PlanSuspension` with the resolution as input.
   4. On Grant Moment M2 timeout (no decision within `timeout_seconds`), notify the Boundary Conversation with `GrantMomentExpiredError`; the conversation re-issues from a fresh `PlanSuspension` per `specs/grant-moment.md` line 114 "Re-issue Grant Moment via runtime; cooldown applies if repeated within session".

   This collapses key design question #6 (mid-conversation pause-resume): the bridge is a **typed-event channel** between the two primitives, not a shared mutable state. The Boundary Conversation (shard 8) is Kaizen-BaseAgent-backed; the Grant Moment is its own state machine; PlanSuspension is the upstream-provided pause primitive that links them. The Grant Moment never reaches into Boundary Conversation internals.

9. **`envoy.grant_moment.novelty.NoveltyClassifier`** — implements `specs/grant-moment.md` § Novelty-aware friction. Classifies each request into `novel | familiar_repeat | high_stakes`:
   - **Novel pattern** detection: unseen recipient OR new dollar range outside ±25% of 30-day P50 OR tool unseen in last 7 days OR new N-gram sequence (per spec lines 89–90). The detector reads the Ledger via `EnvoyLedger.query(filter={types: ["grant_moment"], since: 7_days_ago})` for the per-tool / per-recipient / per-dollar-range distributions.
   - **Familiar repeat** detection: matches a prior Grant Moment within the 30-day window with same `tool_name` + same recipient bucket + same dollar bucket. Phase 01 emits a "batch-to-envelope conversion offer" hint in the result envelope but does NOT auto-author the constraint (the offer routes through Weekly Posture Review per spec).
   - **High-stakes** detection: dollar amount above per-envelope `high_stakes_threshold_microdollars` OR tool-name in `envelope.semantic_checks.communication_content_classifier_ensemble` BLOCK list OR composition rule with `verdict: "block+grant_moment"` triggered. High-stakes triggers primary-channel binding per spec line 92 + 5s read-delay + double-tap + cross-channel confirm per spec line 90.

   `NoveltyClassifier` populates `request.novelty_class` and `request.primary_only` (the latter is `true` when `novelty_class == "high_stakes"`).

10. **`envoy.grant_moment.errors`** — the 10 typed errors per `specs/grant-moment.md` § Error taxonomy lines 110–123: `GrantMomentExpiredError`, `GrantMomentTimeoutError`, `DualSignatureRequiredError` (Phase 03 placeholder; raised but not consumed in Phase 01 single-principal), `NotPrimaryChannelError`, `VelocityRaiseCoolingOffError`, `GrantMomentReplayError`, `VisibleSecretMismatchError`, `NoveltyFrictionRequiredError`, `BackPressureQueueFullError`, `CrossChannelConfirmFailedError`. Each subclasses a base `GrantMomentError`. Each maps to a `system_error` Ledger entry per `specs/ledger.md` § System error.

### 3.3 What is explicitly NOT Envoy-new-code

- **Ed25519 signing primitives** — `kailash.trust.signing.crypto` only. Per `rules/independence.md`, no rolled crypto.
- **DelegationRecord / RevocationRecord persistence** — `kailash.trust.chain` + `kailash.trust.chain_store.sqlite.SqliteTrustStore` via `TrustStoreAdapter`.
- **Cascade BFS walker** — `kailash.trust.revocation.cascade.cascade_revoke(...)` per Shard 5; Envoy provides the orchestration (when to fire), not the algorithm.
- **Envelope compilation / monotonic-tightening enforcement** — `EnvelopeCompiler` per Shard 4; Envoy Grant Moment delegates the child-envelope compile.
- **Hash-chain Ledger writer** — `EnvoyLedger.append(...)` per Shard 6 § 4 (which itself is composition over upstream `AuditStore`).
- **Channel UI rendering** — channel adapters (shard 16) host the rendering; the Grant Moment exposes a `request_grant_moment(envelope_violation, channel) → resolution` contract.
- **PlanSuspension primitive** — upstream per ISS-13 / #598 closure.
- **Cross-principal dual-signed grants** — Phase 03 deferral per `specs/grant-moment.md` § Cross-principal lines 98–100. Phase 01 raises `DualSignatureRequiredError` if invoked but never consumes the path.

---

## 4. Class structure sketch (interfaces only)

Module path (Envoy-side, proposed): `envoy.grant_moment`.

```python
# envoy/grant_moment/types.py
@dataclass(frozen=True)
class EnvelopeViolation:
    """Surfaced by OutOfEnvelopeDetector when a tool call breaches the active envelope."""
    envelope_id: str
    envelope_version: int
    envelope_hash: str
    violated_dimension: Literal["financial", "operational", "temporal", "data_access", "communication"]
    violated_constraint_id: str
    why_asking: Literal["envelope_violation", "composition_rule", "first_time", "velocity_raise", "cross_principal", "data_access_classifier"]
    tool_name: str
    tool_args_canonical: dict
    consequence_preview: ConsequencePreview  # budget_microdollars, reversibility, recipient, data_classification

@dataclass(frozen=True)
class GrantMomentRequest:
    """Wire format per specs/grant-moment.md § Schema § GrantMomentRequest (lines 19-46).
    Constructed at M0; canonical-JCS-signed by delegation_key over the canonical form
    minus signature_by_delegator_hex itself."""
    schema_version: str  # "grant-moment/1.0"
    request_id: str      # uuid-v7
    session_id: str
    principal_genesis_id: str
    envelope_id: str
    envelope_version: int
    envelope_hash: str
    intent_id: str
    nonce: str
    tool_name: str
    tool_args_canonical: dict
    tool_args_canonical_hash: str
    why_asking: str
    consequence_preview: dict
    novelty_class: Literal["novel", "familiar_repeat", "high_stakes"]
    primary_only: bool
    timeout_seconds: int  # default 300; per-envelope override
    issued_at: str
    delegation_key_pubkey_hex: str
    signature_by_delegator_hex: str

@dataclass(frozen=True)
class GrantMomentResult:
    """Wire format per specs/grant-moment.md § Schema § GrantMomentResult (lines 53-69).
    Returned at M3; signed by delegation_key for approve/modify; UNSIGNED for deny
    (per spec line 51)."""
    schema_version: str
    result_id: str
    request_id: str
    decision: Literal["approve_once", "approve_and_author", "deny", "modify"]
    decided_at: str
    decided_on_channel_id: str
    modify_payload: Optional[dict]   # {new_args_canonical, new_args_canonical_hash} for modify
    author_payload: Optional[dict]   # {new_constraint, novelty_check_passed, minimum_impact_passed} for approve_and_author
    decided_by_principal_genesis_id: str
    co_signer_principal_genesis_id: Optional[str]  # Phase 03 only
    delegation_record_ref: Optional[str]
    phase_a_record_ref: str
    signature_by_delegator_hex: Optional[str]      # None for deny
    co_signature_hex: Optional[str]

class ResolutionShape(Enum):
    """The 3 EC-2 shapes; covers the spec's 4 decisions per § 3.2 mapping table."""
    APPROVE = "approve"                                # approve_once or approve_and_author
    DECLINE = "decline"                                # deny
    APPROVE_WITH_MODIFICATION = "approve_with_modification"  # modify

@dataclass(frozen=True)
class GrantMomentResolution:
    shape: ResolutionShape
    result: GrantMomentResult
    delegation_record_ref: Optional[str]   # None for DECLINE
    envelope_edit_ref: Optional[str]       # set for approve_and_author and modify

# envoy/grant_moment/orchestrator.py
class GrantMomentOrchestrator:
    """Single facade for the Grant Moment primitive.

    Composes:
      - envoy.envelope.compiler.EnvelopeCompiler (shard 4)
      - envoy.trust.TrustStoreAdapter (shard 5)
      - envoy.ledger.EnvoyLedger (shard 6)
      - kailash.trust.signing.crypto.{sign, verify_signature}
      - kailash.trust.revocation.cascade.cascade_revoke
    """

    def __init__(
        self,
        *,
        compiler: "envoy.envelope.compiler.EnvelopeCompiler",
        trust_store: "envoy.trust.TrustStoreAdapter",
        ledger: "envoy.ledger.EnvoyLedger",
        novelty_classifier: "NoveltyClassifier",
        principal_id: str,             # rules/tenant-isolation.md Rule 1 — present from day 1
        algorithm_identifier: "AlgorithmIdentifier",  # pinned at construction
        back_pressure_ceiling: int = 5,                # specs/grant-moment.md § Open question 3
    ) -> None: ...

    async def request_grant_moment(
        self,
        violation: EnvelopeViolation,
        channel: "envoy.channels.ChannelAdapterRef",
    ) -> GrantMomentResolution:
        """M0→M4 pipeline.
        1. M0 construct: build GrantMomentRequest, classify novelty, sign via delegation_key
        2. M1 render: dispatch to channel.render_grant_moment(request); enforce primary-channel binding
        3. M2 await: await result_future with request.timeout_seconds
        4. M3 sign-or-decline: validate signature shape per decision; raise typed errors
        5. M4 complete: write PhaseARecord + DelegationRecord + grant_moment + (optional envelope_edit)
        """
        ...

    async def resolve_decline(self, request: GrantMomentRequest, result: GrantMomentResult) -> GrantMomentResolution: ...
        # No DelegationRecord; only grant_moment Ledger row with decision="deny"

    async def resolve_approve(self, request: GrantMomentRequest, result: GrantMomentResult) -> GrantMomentResolution: ...
        # PhaseARecord + DelegationRecord + grant_moment Ledger row
        # If decision=="approve_and_author": invoke EnvelopeCompiler.compile(child_input, parent=current_envelope)
        # and append envelope_edit Ledger row

    async def resolve_modify(self, request: GrantMomentRequest, result: GrantMomentResult) -> GrantMomentResolution: ...
        # Recompute intent_id over modified args; new PhaseARecord + DelegationRecord + grant_moment + envelope_edit

    async def revoke(self, *, grant_id: str, reason: str) -> "kailash.trust.revocation.cascade.RevocationResult":
        """Cascade-revoke a grant and all its descendants via Trust store.

        Wraps kailash.trust.revocation.cascade.cascade_revoke per shard 5 § 3.3.
        Atomic within Trust Vault transaction per specs/trust-lineage.md line 85.
        Emits a single RevocationRecord Ledger entry covering the entire cascade;
        verify_cascade_complete asserts every descendant in the lineage graph is in
        the result set.
        """
        ...

    async def next_session_orphan_sweep(self) -> list["PhaseAOrphanResolution"]:
        """At session start, sweep PhaseA records with no PhaseB within 30d TTL.
        Per specs/grant-moment.md § Cross-references → specs/ledger.md § Two-phase signing.
        """
        ...

# envoy/grant_moment/violation_detector.py
class OutOfEnvelopeDetector:
    """Wraps every Kaizen tool-call dispatch; returns EnvelopeViolation | None.

    Constructed by the runtime at session start with the current EffectiveEnvelope
    (per kailash.trust.pact.envelopes.compute_effective_envelope, shard 4). Re-pins
    the envelope on Grant Moment M4 envelope-edit emissions.
    """

    def __init__(self, *, effective_envelope_provider: Callable[[], "EnvelopeConfig"]) -> None: ...

    def evaluate(self, *, tool_name: str, tool_args: dict) -> EnvelopeViolation | None: ...

# envoy/grant_moment/channel_handoff.py
class ChannelHandoff:
    """Pure-function dispatch contract.

    The Grant Moment orchestrator's contract with channel adapters (shard 16):
        request_grant_moment(envelope_violation, channel) → resolution
    The function constructs the wire-format request, calls channel.render_grant_moment,
    awaits result_future with timeout, validates signature, returns resolution.
    """

    @staticmethod
    async def dispatch(
        *,
        request: GrantMomentRequest,
        channel: "envoy.channels.ChannelAdapterRef",
        timeout_seconds: int,
    ) -> GrantMomentResult: ...

# envoy/grant_moment/cascade.py
class CascadeRevocationOrchestrator:
    """Wraps kailash.trust.revocation.cascade.cascade_revoke for Grant-Moment-driven
    revocation (EC-2) and cross-channel descendant verification (EC-8)."""

    async def cascade_revoke(
        self,
        *,
        grant_id: str,
        reason: str,
        revoked_by_principal_genesis_id: str,
    ) -> "kailash.trust.revocation.cascade.RevocationResult": ...

    async def verify_cascade_complete(self, *, revocation_id: str) -> bool: ...

# envoy/grant_moment/boundary_pause.py
class PlanSuspensionBridge:
    """Typed-event channel between Boundary Conversation (shard 8) and Grant Moment.

    Listens for `grant_moment.spawned` / `grant_moment.completed` / `grant_moment.expired`
    events; coordinates pause-resume of the parent Boundary Conversation's
    PlanSuspension primitive (kailash-py post-ISS-13 / #598).
    """
    ...
```

Per `rules/facade-manager-detection.md` Rule 3, `GrantMomentOrchestrator.__init__` takes its dependencies (compiler, trust_store, ledger, novelty_classifier, principal_id, algorithm_identifier) explicitly — no global lookup, no self-construction. Per Rule 1, the orchestrator is the single `*-Orchestrator`-shape class on the framework's top-level surface; the Tier 2 wiring tests in § 6 are named per Rule 2 convention.

Per `rules/orphan-detection.md` Rule 1, `envoy.grant_moment.GrantMomentOrchestrator` MUST be invoked from a production hot path within 5 commits of landing. The hot path is `OutOfEnvelopeDetector.evaluate(...) → request_grant_moment(...)` — the detector's call site lives inside the Kaizen tool-dispatch interceptor (Boundary Conversation runtime + every subsequent agent loop).

---

## 5. Integration points

The Grant Moment composes 5 neighbouring primitives. Each is a clean unidirectional or bidirectional hop.

| Neighbouring primitive (shard) | Hook                                                                                                                                                                                                                                                                                                                              | Direction      | Spec citation                                                                                                 |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------- |
| Envelope compiler (4)          | `EnvelopeCompiler.compile(new_constraint, parent=current_envelope)` invoked on `approve_and_author` and `modify`; uses `intersect_envelopes` for grant-scope intersect; `RoleEnvelope.validate_tightening` enforces monotonic tightening                                                                                          | GM → EC        | shard 4 § 5 row 2; `specs/envelope-model.md` § Algorithms § `intersect_envelopes`                             |
| Trust store + lineage (5)      | `TrustStoreAdapter.record_delegation(...)` for Approve / Approve+author / Modify; `.revoke(...)` for cascade revocation; `_with_algorithm_id(...)` helper threads algorithm_identifier                                                                                                                                            | GM ↔ TS        | shard 5 § 4 + § 3.3; `specs/trust-lineage.md` § Schema § DelegationRecord + § Algorithms § Cascade revocation |
| Envoy Ledger (6)               | `EnvoyLedger.append("PhaseARecord", ...)` at M0; `EnvoyLedger.append("grant_moment", ...)` at M4; `EnvoyLedger.append("PhaseBRecord", ...)` post-execution by runtime; `EnvoyLedger.append("PhaseAOrphanResolution", ...)` at next-session-start sweep; `EnvoyLedger.append("envelope_edit", ...)` on approve_and_author / modify | GM → L         | shard 6 § 5.1 row "Grant Moment"; `specs/ledger.md` lines 350–414                                             |
| Boundary Conversation (8)      | `PlanSuspensionBridge` listens for `grant_moment.spawned/completed/expired`; the BC suspends its PlanSuspension during M0→M4 and resumes with the resolution as input                                                                                                                                                             | GM ↔ BC        | `specs/boundary-conversation.md` § PlanSuspension (cross-spec); ISS-13 / #598 closure                         |
| Channel adapters (16)          | `ChannelHandoff.dispatch(request, channel, timeout)` calls `channel.render_grant_moment(request)`; the channel hosts UI rendering and returns `result_future`; primary-channel binding enforced by orchestrator pre-dispatch                                                                                                      | GM → CA → GM   | `specs/grant-moment.md` § Rendering + § Cross-principal; `specs/channel-adapters.md` § H-03 primary-channel   |
| Authorship Score (9)           | The Score reads grant approval/decline history via `EnvoyLedger.query(filter={types: ["grant_moment"], decision in [...]})` to compute novelty/authorship-density per `specs/authorship-score.md` § Re-derivation; the Grant Moment supplies the consent inputs                                                                   | GM → AS (read) | `specs/authorship-score.md` § Re-derivation from the Ledger                                                   |
| Daily Digest (11)              | The Digest reads `grant_moment` Ledger rows for the prior day to render "your N grants" sections; the Grant Moment is the producer                                                                                                                                                                                                | GM → DD (read) | `specs/daily-digest.md` (out of scope this shard)                                                             |
| Budget tracker (12)            | Budget threshold callback (per ISS-29 / #603 closure) fires a Grant Moment via `request_grant_moment(...)` when a budget ceiling is approached; the Grant Moment is the consumer of the threshold callback                                                                                                                        | BT → GM        | `specs/budget-tracker.md` § velocity-raise; `specs/grant-moment.md` § Velocity-raise ratchet (T-093 R2-H4)    |

Per `rules/orphan-detection.md` Rule 1, each integration above MUST have a production call site in the Envoy hot path within 5 commits of the orchestrator landing. The shard-10 implementation PR ships the orchestrator AND its primary call site (the `OutOfEnvelopeDetector.evaluate(...) → request_grant_moment(...)` wiring inside the Kaizen tool-dispatch interceptor); secondary call sites (Budget tracker fires; Daily Digest reads; Authorship Score reads) land with their respective shard PRs.

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/testing.md` § "Tier 2 (Integration): Real infrastructure recommended" — real SQLite + real Ed25519 + real Kaizen `BaseAgent` + real Channel adapters; NO mocking. EC-2 acceptance gate per `02-mvp-objectives.md` lines 31–43 directly tests this primitive end-to-end.

Per `rules/orphan-detection.md` Rule 2 + Rule 2a + `rules/facade-manager-detection.md` Rule 1 + Rule 2: every wired manager + crypto-pair surface MUST have a Tier 2 wiring test that imports through the facade and asserts an externally-observable effect.

### 6.1 Tier 2 — wiring + 3-shape end-to-end + cascade

| Test file                                                                            | What it exercises                                                                                                                                                                                                                                                                                                                                                                                         | EC tested                    |
| ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| `tests/integration/test_grant_moment_orchestrator_wiring.py`                         | Per `rules/facade-manager-detection.md` Rule 2 naming convention: imports `from envoy.grant_moment import GrantMomentOrchestrator`, constructs against a real EnvelopeCompiler + real TrustStoreAdapter + real EnvoyLedger + real Channel adapter, calls `.request_grant_moment(...)` for each of the 4 spec decisions, asserts the expected Ledger rows + DelegationRecord persistence + envelope edits. | EC-2                         |
| `tests/integration/test_grant_moment_resolve_approve_once.py`                        | M0→M4 with `decision="approve_once"`. Asserts: `PhaseARecord` written; `DelegationRecord` written via `TrustStoreAdapter.record_delegation`; `grant_moment` Ledger row written with `decision: "approve_once"`; NO `envelope_edit` row; resolution shape is `Approve`.                                                                                                                                    | EC-2                         |
| `tests/integration/test_grant_moment_resolve_approve_and_author.py`                  | M0→M4 with `decision="approve_and_author"`. Asserts: `PhaseARecord` + `DelegationRecord` + `grant_moment` + **`envelope_edit`** rows all written; the new envelope is byte-stable per `EnvelopeCompiler.compile`'s JCS+NFC pipeline; `RoleEnvelope.validate_tightening` was invoked (the new envelope is NOT wider than parent on any dimension).                                                         | EC-2                         |
| `tests/integration/test_grant_moment_resolve_decline.py`                             | M0→M4 with `decision="deny"`. Asserts: NO `DelegationRecord` (per `specs/grant-moment.md` line 51); ONLY a `grant_moment` Ledger row with `decision: "deny"` and `signature_by_delegator_hex: null`; resolution shape is `Decline`; envelope state is unchanged from M0.                                                                                                                                  | EC-2                         |
| `tests/integration/test_grant_moment_resolve_modify.py`                              | M0→M4 with `decision="modify"`. Asserts: a fresh `intent_id` recomputed over the modified args; `PhaseARecord` written with the NEW intent_id; `DelegationRecord` covering the modified args (new `effective_envelope_hash`); `grant_moment` Ledger row with `decision: "modify"`; `envelope_edit` Ledger row capturing the action-scoped tightening; resolution shape is `ApproveWithModification`.      | EC-2                         |
| `tests/integration/test_grant_moment_three_shapes_byte_identity.py`                  | Run all 3 resolution shapes through the orchestrator on macOS + Linux + Windows (CI matrix); JCS canonical bytes of every signed-consent record are byte-identical across OS (modulo `decided_on_channel_id` which is per-channel-instance). Per `specs/grant-moment.md` line 72 cross-runtime byte-identity.                                                                                             | EC-2, BET-6                  |
| `tests/integration/test_grant_moment_cascade_revoke_bfs_complete.py`                 | Build a 3-deep delegation tree (Day-1 grant → Day-3 child → Day-5 grandchild); call `orchestrator.revoke(grant_id=root)`; assert `RevocationResult.revoked_agents` reaches every descendant; assert ONE `RevocationRecord` Ledger entry written with `cascade_target_count == 3`; assert `verify_cascade_complete` returns True.                                                                          | EC-2 cascade                 |
| `tests/integration/test_grant_moment_cascade_revoke_idempotent.py`                   | Second revoke of same grant returns `RevocationResult(success=True, events=[], revoked_agents=[])` per `kailash.trust.revocation.cascade.cascade_revoke` docstring lines 191–196.                                                                                                                                                                                                                         | EC-2 cascade                 |
| `tests/integration/test_grant_moment_cascade_partial_failure_rollback.py`            | Force a chain-deletion failure mid-cascade; assert prior deletions roll back via `_rollback_chains` per shard 5 § 6.1; `RevocationResult.success == False`; the originating grant remains active until the failure is resolved.                                                                                                                                                                           | EC-2 cascade                 |
| `tests/integration/test_grant_moment_state_machine_timeout_M2.py`                    | Per `specs/grant-moment.md` § Test location `test_grant_moment_state_machine.py`: M0→M4 transitions + 5-min default timeout; on timeout, `GrantMomentExpiredError` raised; `grant_moment` Ledger row written with `decision: "expired"`.                                                                                                                                                                  | EC-2                         |
| `tests/integration/test_grant_moment_render_all_channels.py`                         | Per `specs/grant-moment.md` § Test location: visible secret + dialog content rendered on every active channel; symmetric across CLI + Web + 6 messaging adapters.                                                                                                                                                                                                                                         | EC-2, EC-7                   |
| `tests/integration/test_grant_moment_primary_channel_binding_h03.py`                 | High-stakes Grant Moment with `primary_only=true` raises `NotPrimaryChannelError` when dispatched to a non-primary channel; the error message names the user's designated primary channel per `specs/channel-adapters.md` H-03.                                                                                                                                                                           | EC-2                         |
| `tests/integration/test_grant_moment_visible_secret_round_trip.py`                   | Per `rules/orphan-detection.md` Rule 2a (crypto-pair round-trip THROUGH the facade): the visible-secret bytes rendered by the channel adapter MUST byte-match the Trust-Vault stored secret read via `TrustStoreAdapter.get_visible_secret(principal_id)`; mismatch raises `VisibleSecretMismatchError`.                                                                                                  | EC-2 (T-018 defense)         |
| `tests/integration/test_grant_moment_principal_dimension.py`                         | Per `rules/tenant-isolation.md` Rule 1 + Rule 2: orchestrator constructed without `principal_id` raises `PrincipalRequiredError`; cache keys (e.g. nonce table) are keyed by `principal_genesis_id`.                                                                                                                                                                                                      | tenant-isolation             |
| `tests/integration/test_grant_moment_classified_record_id_redaction.py`              | Per `rules/event-payload-classification.md` Rule 4: a Grant Moment whose `consequence_preview.recipient` references a classified-PK model (e.g. `Account` keyed by classified `email`) emits a DomainEvent whose `record_id` is `sha256:XXXXXXXX`-prefixed; raw email NOT in `repr(payload)`.                                                                                                             | event-payload-classification |
| `tests/integration/test_grant_moment_atomic_phase_a_and_delegation_under_failure.py` | Per #707 / #711: kill the process between `PhaseARecord` write and `DelegationRecord` insert; on restart, the orphan sweep picks up the orphan Phase A; `PhaseAOrphanResolution` is emitted at next session start with `resolution: "investigate"`.                                                                                                                                                       | EC-2                         |
| `tests/integration/test_grant_moment_back_pressure_queue_full.py`                    | Per `specs/grant-moment.md` § Open question 3 + line 122: N=back_pressure_ceiling parallel grants pending; (N+1)-th `request_grant_moment` raises `BackPressureQueueFullError`.                                                                                                                                                                                                                           | EC-2                         |
| `tests/integration/test_grant_moment_velocity_raise_24h_cooling_off.py`              | Per `specs/grant-moment.md` § Velocity-raise ratchet (T-093 R2-H4): inline velocity-raise approval refused with `VelocityRaiseCoolingOffError`; only 24h-cooled-off cross-channel Grant Moment OR Weekly Posture Review path approves.                                                                                                                                                                    | EC-2 (T-093)                 |

### 6.2 Tier 3 — cross-channel + duress-latency parity + EC-8

| Test file                                                            | What it exercises                                                                                                                                                                                                                                                             | EC tested        |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- | ------------- | ---- |
| `tests/e2e/test_grant_moment_cross_channel_descendant_revoke_ec8.py` | EC-8 acceptance gate: Day-1 `Approve` grant on Telegram → Day-3 child grant on Slack → Day-6 user revokes Day-1 grant from CLI; cascade BFS reaches the Slack-originated child grant; both grants are revoked; the Trust Lineage `chain_parent_id` graph is channel-agnostic. | EC-2 + EC-8      |
| `tests/e2e/test_grant_moment_real_to_honeypot_latency_parity.py`     | Per `specs/grant-moment.md` § Test location: real path latency vs duress honeypot path latency MUST be byte-for-byte identical (T-041 distinguisher prevention). The orchestrator must NOT branch on duress/real before M4; the timing IS the distinguisher.                  | T-041 defense    |
| `tests/e2e/test_grant_moment_phase_a_orphan_resolution_30d_ttl.py`   | A `PhaseARecord` with no `PhaseBRecord` within 30d TTL surfaces at next-session-start as a `PhaseAOrphanResolution` Ledger row; the user is prompted to choose `retry_idempotent                                                                                              | record_as_failed | investigate`. | EC-2 |
| `tests/e2e/test_grant_moment_three_shapes_independent_verifier.py`   | EC-9 cross-implementation invariant: spawn the shard-7 verifier (separate codebase) against an Envoy-produced Ledger export containing all 3 resolution shapes; verifier passes; tampering battery (single-bit flip in any signed-consent record) detects every form.         | EC-2 + EC-9      |

### 6.3 Regression tests (per `specs/grant-moment.md` § Test location lines 138–147)

| Test file                                                      | Threat                                                         | Phase 01 ship?                                                                        |
| -------------------------------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `tests/regression/test_t008_grant_moment_replay_nonce.py`      | T-008 replay; duplicate nonce or duplicate `intent_id` refused | Yes — load-bearing for EC-2                                                           |
| `tests/regression/test_t018_dialog_spoofing_visible_secret.py` | T-018; visible-secret mismatch refused                         | Yes — load-bearing for EC-2                                                           |
| `tests/regression/test_t019_novelty_friction_5s_read_delay.py` | T-019; 5s + double-tap on novel pattern                        | Yes — load-bearing for EC-2                                                           |
| `tests/regression/test_t093_velocity_raise_24h_cooling_off.py` | T-093 R2-H4; cooling-off enforcement                           | Yes — load-bearing for EC-2                                                           |
| `tests/integration/test_h03_primary_channel_binding.py`        | H-03; high-stakes routes only to primary channel               | Yes — load-bearing for EC-2                                                           |
| `tests/integration/test_cross_principal_dual_signature.py`     | Phase 03 dual-signed flow                                      | **Phase 03 deferral** — Phase 01 raises `DualSignatureRequiredError` placeholder only |
| `tests/integration/test_grant_moment_back_pressure.py`         | N-parallel queue ceiling                                       | Yes — load-bearing for EC-2                                                           |

### 6.4 Mechanical sweep (for /redteam)

Per `rules/agents.md` § "Reviewer Prompts Include Mechanical AST/Grep Sweep":

- `grep -rln "GrantMomentOrchestrator" envoy/ tests/` — every Phase 01 production code path that triggers a Grant Moment (`OutOfEnvelopeDetector`, `BudgetTracker.threshold_callback`, `BoundaryConversation.first_time_action_gate`) must reach the orchestrator.
- `grep -rln "ResolutionShape" tests/integration/` — at least one test per shape (`APPROVE`, `DECLINE`, `APPROVE_WITH_MODIFICATION`).
- `grep -rln "cascade_revoke" envoy/grant_moment/` — exactly one direct call site (inside `CascadeRevocationOrchestrator.cascade_revoke`); higher-layer callers MUST go through the orchestrator.
- `grep -rln "delegation_key.*sign\b\|signature_by_delegator_hex" envoy/grant_moment/` — every signing site routes through `kailash.trust.signing.crypto.sign` via `SignedConsentBuilder`; no inline `Ed25519` bytes.

---

## 7. Frozen-spec ambiguity check

Per `01-shard-plan.md` § 4 failure-mode protocol: if a primitive deep-dive surfaces a HIGH gap in the frozen spec, STOP the deep-dive; convene MUST-Rule-5b sweep before continuing.

This shard surfaced **NO HIGH-severity ambiguity** in `specs/grant-moment.md`, `specs/envelope-model.md`, `specs/ledger.md`, or `specs/trust-lineage.md` that the Phase 00 redteam did not already close. Three MEDIUM-severity items are noted but do NOT block the shard.

### 7.1 MED-1 — Out-of-envelope detection point (key design question #5)

The shard prompt asks: "WHO detects the violation? The envelope compiler? The Kaizen runtime? An interceptor wrapping every tool call?"

`specs/grant-moment.md` § Schema's `why_asking` enum (line 33) lists `envelope_violation | composition_rule | first_time | velocity_raise | cross_principal | data_access_classifier` — six trigger types. The spec does not name WHICH primitive detects each. Reading the cross-spec dependencies:

- `envelope_violation` — the `EffectiveEnvelope` itself is the producer of "this action violates X dimension"; the Envelope compiler IS the source of the envelope, but a runtime-side **interceptor** is the source of the **violation event**.
- `composition_rule` — `specs/envelope-model.md` § composition_rules — same: a runtime-side interceptor evaluates the rule against the proposed action.
- `first_time` — `specs/envelope-model.md` § Algorithms § "First-time-action gate" — the gate fires on first-ever invocation of (tool_name, recipient_bucket, dollar_bucket); the runtime-side interceptor evaluates the gate.
- `velocity_raise` — `specs/budget-tracker.md` § velocity-raise — the Budget tracker (shard 12) fires the threshold callback per ISS-29 / #603.
- `cross_principal` — Phase 03 deferral.
- `data_access_classifier` — `specs/envelope-model.md` § `semantic_checks.data_access_classifier_ensemble` — the classifier ensemble is evaluated by the runtime-side interceptor.

**Phase 01 disposition:** the **`OutOfEnvelopeDetector`** is the runtime-side interceptor that consolidates 5 of the 6 trigger types (all except `velocity_raise` which is Budget-tracker-driven). The detector wraps the Kaizen `BaseAgent`'s tool-dispatch hot path. This is the only structurally-coherent answer — putting violation detection in the Envelope compiler couples authoring to evaluation; putting it in the Kaizen runtime couples agent execution to envelope semantics; the dedicated detector module mediates. The decision is recorded here so shard 22 can dispose; this is NOT a HIGH-severity gap because the spec does not require any specific architecture, only that violations are detected and the Grant Moment fires.

### 7.2 MED-2 — Signed-consent record format vs Ledger-row format (key design question #3)

The shard prompt asks: "Signed-consent record format: Ed25519-signed by user's authority key (Trust Vault), canonical-JSON serialized, written to Ledger as a typed entry. Field schema?"

`specs/grant-moment.md` § Schema defines TWO wire formats (`GrantMomentRequest` 12 fields; `GrantMomentResult` 10 fields). `specs/ledger.md` § Ledger entry schemas § `grant_moment` (lines 350–364) defines a 8-field Ledger row that POINTS to the wire formats via `request_ref` and `result_ref`.

The "signed-consent record" is therefore THREE artifacts, not one:

1. The canonical-JCS-NFC-encoded `GrantMomentRequest` bytes (signed by `delegation_key`, scope = entire request minus `signature_by_delegator_hex`).
2. The canonical-JCS-NFC-encoded `GrantMomentResult` bytes (signed by `delegation_key` for approve / approve_and_author / modify; **unsigned** for deny per spec line 51).
3. The `grant_moment` Ledger row referencing the above by `request_ref` + `result_ref`.

The signing key is the `delegation_key` per `specs/grant-moment.md` line 17, NOT the Genesis key. The shard prompt's "user's authority key (Trust Vault)" framing is slightly imprecise — Genesis is Trust-Vault-backed; the `delegation_key` is the agent's per-session signing key, established at Boundary Conversation seeding via Genesis-signed `DelegationRecord` per `specs/trust-lineage.md` § Schema.

**Phase 01 disposition:** the format is fully specified by the cross-spec set; no ambiguity. The "what's the signed-consent record format?" question collapses to "the wire-format pair plus the Ledger pointer row, as canonicalized via JCS+NFC, signed by `delegation_key`, persisted via `EnvoyLedger.append`". This is implementation latitude, NOT a spec gap.

### 7.3 MED-3 — Mid-conversation pause-resume composition with Boundary Conversation (key design question #6)

`specs/boundary-conversation.md` § PlanSuspension is cross-spec; this shard does not edit it. The composition contract — "if a Grant Moment fires DURING Boundary Conversation, how does PlanSuspension compose?" — is structurally answered by `PlanSuspensionBridge` (§ 3.2 item 8) using upstream `kailash-py` PlanSuspension primitive (post-ISS-13 / #598 closure 2026-04-25).

**Phase 01 disposition:** the bridge is a typed-event channel between two state machines (BC's PlanSuspension and Grant Moment's M0→M4). Neither primitive reaches into the other's internals. Shard 8 (Boundary Conversation deep-dive) ships the BC side of the bridge; shard 10 (this shard) ships the Grant Moment side. The contract IS the bridge. This is NOT a spec gap; it is a cross-shard integration design that both shards' implementation deep-dives must pre-declare. Logged here so shard 8 (when it runs) consumes this section; logged in shard 8's eventual cross-references for the symmetric reciprocal.

### 7.4 None HIGH-severity surfaced

No HIGH-severity ambiguity surfaced. The Grant Moment primitive is well-specified (3-shape contract is explicit; signed-consent format is wire-format-pinned across two specs; cascade revocation is upstream-provided with BFS/DFS parity contract; channel surface is delegated to channel adapters). The Phase 00 redteam closed the load-bearing items (R2-H4 velocity-raise ratchet; H-03 primary-channel binding; H-01 nested-signature scope; CRIT-01 device-attestation). Phase 01 implementation can proceed.

---

## 8. Cross-references

### Frozen specs (DO NOT EDIT — read-only at this shard)

- `/Users/esperie/repos/dev/envoy/specs/grant-moment.md` § Purpose, § Provenance, § Schema § GrantMomentRequest (lines 19–46), § Schema § GrantMomentResult (lines 53–69), § State machine (line 74), § Rendering (lines 78–86), § Novelty-aware friction (lines 88–92), § Velocity-raise ratchet (lines 94–96), § Cross-principal (lines 98–100), § Timeout (lines 102–104), § Produced artifact (lines 106–108), § Error taxonomy (lines 110–123), § Cross-references (lines 125–134), § Test location (lines 138–147), § Open questions (lines 149–155).
- `/Users/esperie/repos/dev/envoy/specs/envelope-model.md` § Schema (lines 16–84), § Algorithms § Canonical JSON, § Algorithms § `intersect_envelopes`, § Composition rules.
- `/Users/esperie/repos/dev/envoy/specs/ledger.md` § Entry envelope schema (lines 14–34), § Two-phase signing (lines 519–523), § Ledger entry schemas § `grant_moment` (lines 350–364), § Ledger entry schemas § `PhaseARecord` (lines 366–380), § Ledger entry schemas § `PhaseBRecord` (lines 382–397), § Ledger entry schemas § `PhaseAOrphanResolution` (lines 399–414), § Error taxonomy.
- `/Users/esperie/repos/dev/envoy/specs/trust-lineage.md` § Schema § DelegationRecord (lines 36–54), § Schema § RevocationRecord (lines 60–71), § Algorithms § Cascade revocation (lines 80–85), § Algorithms § Nonce per-principal partitioning (§6.1 C-02 fix, lines 94–99). CHARTER §41 cascade-revocation hard constraint.
- `/Users/esperie/repos/dev/envoy/specs/boundary-conversation.md` § PlanSuspension (cross-spec via shard 8).

### Phase 01 prior shard outputs (cited; not re-derived)

- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § "Per-shard structure" (8-section structure), § 4 failure-mode protocol, § 5 sequencing (Group C — Grant Moment depends on shards 4, 5, 6, 8).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` EC-2 (3 resolution shapes + cascade revocation, lines 31–43), EC-7 (8-channel symmetry), EC-8 (cross-channel coherence + Day-1/Day-6 cascade, lines 116–117).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 7 (Grant Moment — A grade unchanged), § 5 verification protocol, § 4 (zero hard upstream blockers).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md` § 4 EnvelopeCompiler.intersect / .compile contracts, § 5 row 2 Grant Moment integration.
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 3.3 cascade-revocation glue, § 3.4 algorithm-identifier `_with_algorithm_id()` helper, § 4 TrustStoreAdapter interface.
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 4 EnvoyLedger.append contract, § 5.1 Grant Moment writer row (entry types: `grant_moment`, `PhaseARecord`, `PhaseBRecord`, `PhaseAOrphanResolution`).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` (citation discipline; no re-derivation).

### Phase 00 verified citations

- `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` item 17 (Trust Lineage signing — A grade), item 13 (Kaizen BaseAgent for Boundary Conversation host of PlanSuspension), item 3 (cascade revocation BFS).

### Verified upstream provider (read-only references)

- `~/repos/loom/kailash-py/src/kailash/trust/signing/crypto.py` lines 38, 120, 168, 223, 264 (Ed25519 keypair / sign / verify_signature / serialize_for_signing / hash_chain).
- `~/repos/loom/kailash-py/src/kailash/trust/signing/algorithm_id.py` lines 1–162 (post-#604 scaffold; default `"ed25519+sha256"`).
- `~/repos/loom/kailash-py/src/kailash/trust/revocation/cascade.py` line 154 (`cascade_revoke`); lines 71 (`RevocationResult`).
- `~/repos/loom/kailash-py/src/kailash/trust/pact/envelopes.py` line 336 (`intersect_envelopes`), line 437 (`RoleEnvelope.validate_tightening`).
- `~/repos/loom/kailash-py/src/kailash/trust/chain.py` line 222 (`DelegationRecord`).

### Closed upstream issues verified

- terrene-foundation/kailash-py#594 (ISS-02 — `intersect_envelopes` parity) — closed 2026-04-24T17:01:13Z.
- terrene-foundation/kailash-py#595 (ISS-05 — cascade-revocation docstring cross-reference) — closed 2026-04-25.
- terrene-foundation/kailash-py#598 (ISS-13 — `PlanSuspension` parity) — closed 2026-04-25 (load-bearing for PlanSuspensionBridge).
- terrene-foundation/kailash-py#604 (ISS-32 — algorithm-identifier schema) — closed 2026-04-25T14:43:55Z.
- terrene-foundation/kailash-py#603 (ISS-29 — `BudgetTracker` threshold-callback API) — closed 2026-04-25 (load-bearing for Budget-tracker-fires-Grant-Moment).
- terrene-foundation/kailash-py#672 (Python `format_record_id_for_event` cross-SDK) — closed Apr 25.
- terrene-foundation/kailash-py#707, #711 (`df.transaction()`) — closed Apr 25.
- terrene-foundation/kailash-py#731 (timestamp microsecond padding cross-SDK) — closed Apr 25.

### Applicable rules

- `.claude/rules/zero-tolerance.md` Rule 4 (no SDK workarounds — Grant Moment composes upstream, does not re-implement), Rule 6 (Implement Fully — all 3 EC-2 shapes, not 2).
- `.claude/rules/orphan-detection.md` Rule 1 (production call site within 5 commits), Rule 2 (Tier 2 wiring through facade), Rule 2a (crypto-pair round-trip — sign/verify_signature on signed-consent records), Rule 3 (deletion not deprecation).
- `.claude/rules/facade-manager-detection.md` Rule 1 (Tier 2 test exists), Rule 2 (test file naming `test_<lowercase>_wiring.py`), Rule 3 (constructor receives explicit deps, no global lookup).
- `.claude/rules/event-payload-classification.md` Rule 1 (single-point filter at emitter), Rule 2 (classified-PK hash), Rule 4 (end-to-end Tier 2 test).
- `.claude/rules/tenant-isolation.md` Rule 1 (`principal_id` dimension on every cache key), Rule 2 (typed `PrincipalRequiredError` on missing dimension).
- `.claude/rules/specs-authority.md` Rule 4 (read specs before acting; this shard reads 4 specs), Rule 5b (no spec edits at this shard).
- `.claude/rules/testing.md` § 3-Tier Testing § Tier 2 + Tier 3 (real infrastructure recommended).
- `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget (6 invariants tracked; 4 cross-primitive references; within budget).

### Forward references (next shards / future phases)

- shard 11 — Daily Digest reads `grant_moment` Ledger rows for prior-day rendering.
- shard 12 — Budget tracker fires Grant Moments via threshold callback (ISS-29 / #603).
- shard 16 — Channel adapters host the Grant Moment dialog UI per `specs/channel-adapters.md` H-03; symmetric across CLI + Web + 6 messaging.
- shard 8 — Boundary Conversation owns the BC side of `PlanSuspensionBridge`; this shard owns the Grant Moment side.
- Phase 03 — Cross-principal dual-signed grants per `specs/grant-moment.md` § Cross-principal lines 98–100; `DualSignatureRequiredError` placeholder ships Phase 01 but consumer path is Phase 03.
