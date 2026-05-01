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

## Cross-principal (Phase 03)

Dual-signed if affects both principals. First principal's dialog → second principal's dialog on their channel. Action executes only after both signed. 24h cooling-off for high-stakes.

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

- `tests/integration/test_grant_moment_state_machine.py` — M0→M4 transitions + 5min timeout (Tier 2).
- `tests/integration/test_grant_moment_render_all_channels.py` — visible secret + dialog content rendered every active channel.
- `tests/regression/test_t008_grant_moment_replay_nonce.py` — T-008 nonce defense; duplicate replay refused.
- `tests/regression/test_t018_dialog_spoofing_visible_secret.py` — T-018 defense; visible-secret mismatch refused.
- `tests/regression/test_t019_novelty_friction_5s_read_delay.py` — T-019 defense; 5s + double-tap on novel pattern.
- `tests/regression/test_t093_velocity_raise_24h_cooling_off.py` — T-093 R2-H4 cooling-off enforcement.
- `tests/integration/test_h03_primary_channel_binding.py` — high-stakes Grant Moment routes only to primary channel.
- `tests/integration/test_cross_principal_dual_signature.py` — Phase 03 dual-signed flow + 24h cool-off for high-stakes.
- `tests/integration/test_grant_moment_back_pressure.py` — N-parallel queue ceiling behavior.
- `tests/e2e/test_grant_moment_real_to_honeypot_latency_parity.py` — duress latency distinguisher prevention.

## Open questions

1. Default 5min timeout — empirical calibration; mobile users may need longer, CLI users shorter.
2. Novel-pattern double-tap UX — accessibility implications for motor-impaired users; alternative friction (long-press + verbal confirm) needed.
3. Back-pressure ceiling N — Phase 01 telemetry will inform tuning (likely 3-5 concurrent grants per principal).
4. Cross-principal 24h cool-off scope — applies to all high-stakes or only above a per-principal threshold; coordination with envelope-model.md needed.
5. Honeypot-path latency parity testing — how to assert byte-for-byte identical timing between real and decoy paths without leaking via test infrastructure.
