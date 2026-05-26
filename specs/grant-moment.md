# grant-moment

## Purpose

Per-action consent state machine; Delegation Record production; visual-secret binding; novelty-aware friction.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/01-ux-rituals.md v2 §4`.
- **Threats mitigated:** T-008 Grant Moment replay (nonce + intent_id defense), T-018 dialog spoofing, T-019 habituation, T-093 velocity ratchet.
- **BETs tested:** BET-1 authorship, BET-12 governance-primary-surface.

## Schema

### `GrantMomentRequest`

Wire format the runtime constructs at M0 and dispatches to channel adapters at M1. Canonical-JCS-signed by the requesting `delegation_key`; signature scope = the entire request minus `signature_by_delegator_hex`.

```json
{
  "schema_version": "grant-moment/1.0",
  "request_id": "uuid-v7",
  "session_id": "uuid-v7",
  "principal_genesis_id": "sha256:...",
  "envelope_id": "uuid-v7",
  "envelope_version": <int>,
  "envelope_hash": "sha256:...",
  "intent_id": "sha256:...",
  "nonce": "<hex>",
  "tool_name": "<str>",
  "tool_args_canonical": {...},
  "tool_args_canonical_hash": "sha256:...",
  "why_asking": "envelope_violation | composition_rule | first_time | velocity_raise | cross_principal | data_access_classifier",
  "consequence_preview": {
    "budget_microdollars": <int>,
    "reversibility": "reversible | reversible_with_cost | irreversible",
    "recipient": "<str>",
    "data_classification": "Public | Internal | Confidential | Restricted | HighlyConfidential"
  },
  "novelty_class": "novel | familiar_repeat | high_stakes",
  "primary_only": <bool>,
  "timeout_seconds": <int>,
  "issued_at": "<iso8601>",
  "delegation_key_pubkey_hex": "<hex>",
  "signature_by_delegator_hex": "<ed25519>"
}
```

### `GrantMomentResult`

Wire format the channel adapter returns at M3 sign-or-decline. Canonical-JCS-signed by `delegation_key` (Approve / Approve+author) or by no key (Deny — signed Ledger entry only). For dual-signed cross-principal grants, two `GrantMomentResult` rows merge per specs/a2a-messaging.md §Cross-principal dual-signed action.

```json
{
  "schema_version": "grant-moment/1.0",
  "result_id": "uuid-v7",
  "request_id": "uuid-v7",
  "decision": "approve_once | approve_and_author | deny | modify",
  "decided_at": "<iso8601>",
  "decided_on_channel_id": "<str>",
  "modify_payload": {"new_args_canonical": {...}, "new_args_canonical_hash": "sha256:..."},
  "author_payload": {"new_constraint": {...}, "novelty_check_passed": <bool>, "minimum_impact_passed": <bool>},
  "decided_by_principal_genesis_id": "sha256:...",
  "co_signer_principal_genesis_id": "sha256:... | null",
  "delegation_record_ref": "<ledger-entry-id>",
  "phase_a_record_ref": "<ledger-entry-id>",
  "signature_by_delegator_hex": "<ed25519>",
  "co_signature_hex": "<ed25519> | null"
}
```

Both schemas are canonicalized via specs/envelope-model.md §Canonical JSON; cross-runtime byte-identity per BET-6.

## State machine

M0 construct → M1 render (all active channels) → M2 await decision (5min default timeout; per-envelope override) → M3 sign or decline → M4 complete.

## Rendering

Every dialog shows:

- Visible secret (icon + color + phrase, stored in Trust Vault).
- Proposed action (tool + args summary).
- Why asking (envelope violation / composition rule / first-time / velocity).
- Consequence preview (budget, reversibility, recipient, data).
- Options: Approve once / Approve+author / Deny / Modify.

## Novelty-aware friction (T-019)

- **Novel pattern** (unseen recipient, new dollar range outside ±25% of 30-day P50, tool unseen in last 7 days, new N-gram sequence) → 5s read-delay + double-tap + cross-channel confirm for high-stakes.
- **Familiar repeat** → batch-to-envelope conversion offer at Weekly Posture Review.
- Primary-channel binding — high-stakes Grant Moments render ONLY on user's designated primary channel.

## Velocity-raise ratchet (T-093 R2-H4)

Raising velocity limits CANNOT be approved inline. Requires Weekly Posture Review OR cross-channel Grant Moment with 24h cooling-off.

**Phase 01 known limitation (per `rules/specs-authority.md` Rule 6):**
The Phase 01 cooling-off uses `time.time()` (wall-clock) so the 24h
math matches the user-facing claim AND so the ratchet survives process
restart in the same calendar window. Forward clock skew (NTP catch-up
jump, admin clock change, container clock adjustment) can shorten the
window; backward skew is benign. Phase 02 persists the last-approved
timestamp into the TrustVault alongside a monotonic baseline so
forward-skew becomes detectable.
**User impact:** Phase 01 deployments on systems with managed clocks
(typical) experience the documented 24h gate; deployments on systems
where the operator can move the clock forward MUST treat the gate as
advisory until Phase 02 lands.

## Cross-principal (Phase 03)

Dual-signed if affects both principals. First principal's dialog → second principal's dialog on their channel. Action executes only after both signed. 24h cooling-off for high-stakes.

**Phase 01 deviation (per `rules/specs-authority.md` Rule 6):**
The Phase 01 `EnvoyGrantMomentRuntime` REFUSES every cross-principal grant
at the M0 boundary (`issue_grant_moment` raises
`DualSignatureRequiredError`) because Phase 01 lacks a co-signature
verification path. A single principal able to populate
`co_signer_principal_genesis_id` without a matching `co_signature_hex`
would otherwise produce a "cross-principal grant" without the second
principal's actual signature — exactly the wire-shape-only-defense gap
security review surfaced. Phase 03 wires the verify path + the 24h
cooling-off + the channel hop and lifts the M0 refusal.
**User impact:** Phase 01 ships single-principal grants only; cross-principal
attempts surface a typed error naming Phase 03 as the implementation target.

## Timeout

Default 5min. Identical behavior between real + honeypot paths (prevents duress latency distinguisher). Queue back-pressure after N parallel Grant Moments.

## Produced artifact

Signed `DelegationRecord` per specs/trust-lineage.md + Phase A intent per specs/ledger.md §two-phase signing.

## Error taxonomy

| Error                            | Trigger                                                                                          | User action                                                                                      | Retry                      |
| -------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ | -------------------------- |
| `GrantMomentExpiredError`        | User did not respond within timeout_seconds (default 5min); state machine reaches M2 expiry      | Re-issue Grant Moment via runtime; cooldown applies if repeated within session                   | Manual after re-issue      |
| `GrantMomentTimeoutError`        | Channel transport hung mid-render before reaching M2 await                                       | Surface channel-degraded warning; user re-issues on alternate channel                            | Manual after diagnosis     |
| `DualSignatureRequiredError`     | Cross-principal (Phase 03) action: first principal signed but second principal's dialog pending  | Wait for second principal; surface "awaiting co-signer" UX; honor 24h cooling-off                | Manual on second signature |
| `NotPrimaryChannelError`         | High-stakes Grant Moment (above Financial/Communication threshold) routed to non-primary channel | Approve on user's designated primary channel (named in error per specs/channel-adapters.md H-03) | Never (structural defense) |
| `VelocityRaiseCoolingOffError`   | Velocity-raise approval attempted before 24h cooling-off elapses (T-093 R2-H4)                   | Wait until cooling-off window expires; OR route through Weekly Posture Review                    | Auto after window          |
| `GrantMomentReplayError`         | Same nonce or `intent_id` observed twice (T-008 nonce defense)                                   | Refuse duplicate; surface to runtime as a programming or hostile-replay event                    | Never                      |
| `VisibleSecretMismatchError`     | Rendered visible-secret bytes diverge from Trust-Vault stored secret                             | Refuse render; user enters Boundary Conversation re-pair flow                                    | Manual after re-pair       |
| `NoveltyFrictionRequiredError`   | Caller attempted to bypass 5s read-delay / double-tap on novel-pattern Grant Moment              | Refuse approval; UX enforces full friction sequence                                              | Manual after sequence      |
| `BackPressureQueueFullError`     | N parallel Grant Moments exceeded queue ceiling                                                  | Surface "too many concurrent grants" banner; user resolves pending grants before issuing more    | Manual                     |
| `CrossChannelConfirmFailedError` | High-stakes Grant Moment cross-channel confirm leg failed                                        | User completes confirm on second channel; runtime holds M3 sign step                             | Manual after confirm       |

## Cross-references

- specs/envelope-model.md — composition rules + first-time-action gate trigger.
- specs/trust-lineage.md — Delegation Record signing.
- specs/ledger.md — Grant Moment Ledger entries.
- specs/channel-adapters.md — per-channel rendering + primary-channel binding.
- specs/boundary-conversation.md — visible secret setup.
- specs/weekly-posture-review.md — velocity-raise cooling-off coordination.
- specs/budget-tracker.md — velocity-raise ratchet (T-093).
- specs/threat-model.md — T-008, T-018, T-019, T-093.

## Test location

The Grant Moment surface ships in two layers; the test files split along the
same boundary:

### Structural layer (landed) — Wave-3 primitives

- `tests/tier1/test_grant_moment_state_machine_transitions.py` — M0→M4 transition
  table, JCS+NFC canonicalization round-trip, signed Request/Result wire
  shapes, 3 ResolutionShape → 4 spec decisions mapping, and the 10-error
  taxonomy contract (`TestErrorTaxonomy` class; 10 of its tests carry
  `@pytest.mark.regression` + `Contract pin: <threat>` docstrings naming
  T-008 / T-018 / T-019 / T-093 / H-03 + the back-pressure / cross-principal
  / cross-channel-confirm surfaces).
- `tests/tier1/test_grant_moment_out_of_envelope_detector.py` — every
  classification branch of the `OutOfEnvelopeDetector`.
- `tests/tier1/test_grant_moment_channel_handoff.py` — primary-channel-binding
  dispatch (`high_stakes=True` AND `primary_only=True` paths), refusal
  vocabulary, render-failure isolation.
- `tests/tier1/test_grant_moment_novelty_classifier.py` — 3-class friction
  classifier coverage + totality (exhaustive 32-combo enumeration + 100-input
  randomized totality check).
- `tests/tier2/test_cascade_revocation_orchestrator_wiring.py` — cascade
  completeness verification + `CascadeIncompleteError` raise path against a
  `_RuntimeProtocol`-shaped stub.
- `tests/tier2/test_plan_suspension_bridge_wiring.py` — typed-event
  subscribe/unsubscribe/emit + idempotency dedupe + subscriber-failure
  isolation.

Run `pytest -m regression` to select the threat-mitigation contract pins
across the Wave-3 + Boundary Conversation test surfaces.

### Runtime layer (landed) — `EnvoyGrantMomentRuntime`

The following test files exercise behaviors that depend on the M0→M4
runtime facade (timeout loop, dedup store, channel-render driver, queue
manager, friction enforcer, two-phase Ledger signer) — the facade composes
this spec's structural primitives. Both the facade and these tests landed
in the Wave-4 milestone per `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md` § Surfaces

- `workspaces/phase-01-mvp/02-plans/01-build-sequence.md` § Wave 4. The
  runtime facade ships at `envoy/grant_moment/runtime.py::EnvoyGrantMomentRuntime`
- the shared test harness at `tests/helpers/grant_moment_harness.py`.

* `tests/integration/test_grant_moment_state_machine.py` — Tier-2 runtime
  M0→M4 with 5-minute timeout against the facade.
* `tests/integration/test_grant_moment_render_all_channels.py` — visible
  secret + dialog content rendered every active channel via the facade.
* `tests/regression/test_t008_grant_moment_replay_nonce.py` — T-008 nonce
  defense raise path (the wire-shape Contract pin lives in the structural
  layer above; this file exercises the runtime dedup store's refusal).
* `tests/regression/test_t018_dialog_spoofing_visible_secret.py` — T-018
  defense raise path (the wire-shape Contract pin lives above; this file
  exercises the channel-adapter render's mismatch refusal).
* `tests/regression/test_t019_novelty_friction_5s_read_delay.py` — T-019
  defense raise path (Contract pin above; this file exercises the runtime
  friction enforcer's bypass refusal).
* `tests/regression/test_t093_velocity_raise_24h_cooling_off.py` — T-093
  R2-H4 raise path (Contract pin above; this file exercises the
  budget-tracker integration layer's cooling-off ratchet).
* `tests/integration/test_h03_primary_channel_binding.py` — H-03 raise path
  at M3 sign-or-decline when a high-stakes `GrantMomentResult` arrives from
  a non-primary `decided_on_channel_id` (the M1 dispatch refusal is covered
  in the structural layer via `test_grant_moment_channel_handoff.py`).
* `tests/integration/test_cross_principal_dual_signature.py` — Phase 03
  dual-signed flow + 24h cool-off for high-stakes.
* `tests/integration/test_grant_moment_back_pressure.py` — N-parallel queue
  ceiling behavior.
* `tests/e2e/test_grant_moment_real_to_honeypot_latency_parity.py` — duress
  latency distinguisher prevention.
* `tests/e2e/test_grant_moment_3_resolution_shapes_with_cascade.py` —
  EC-2 acceptance gate (3 resolution shapes execute end-to-end through the
  runtime facade) + EC-8 cascade-revocation anchor (root + 3 expected
  descendants — Phase 01 exercises the runtime's verification half of
  the contract; the BFS itself lives in upstream
  `kailash.trust.cascade_revoke`). Phase 02 lifts the test to a literal
  3-deep delegation tree once Trust Vault container persistence lands.
* `tests/integration/test_grant_moment_cross_channel_confirm_failed.py` —
  `CrossChannelConfirmFailedError` runtime raise paths (analyst-R1 HIGH-1):
  missing confirm leg AND confirm-channel-same-as-decided collapse.
* `tests/integration/test_grant_moment_friction_token_vocabulary.py` —
  closed-vocabulary friction-token validation (security-R1 MED-1): typo'd
  tokens are rejected loudly so the enforcer cannot be silently bypassed.

## Open questions

1. Default 5min timeout — empirical calibration; mobile users may need longer, CLI users shorter.
2. Novel-pattern double-tap UX — accessibility implications for motor-impaired users; alternative friction (long-press + verbal confirm) needed.
3. Back-pressure ceiling N — Phase 01 telemetry will inform tuning (likely 3-5 concurrent grants per principal).
4. Cross-principal 24h cool-off scope — applies to all high-stakes or only above a per-principal threshold; coordination with envelope-model.md needed.
5. Honeypot-path latency parity testing — how to assert byte-for-byte identical timing between real and decoy paths without leaking via test infrastructure.
