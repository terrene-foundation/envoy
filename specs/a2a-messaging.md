# a2a-messaging

## Purpose

Agent-to-agent messaging in Shared Household; cross-principal dual-signed actions.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 + 07-channels-and-adapters.md v1`.
- **Threats mitigated:** T-106 A2A adversarial cooperation.
- **BETs tested:** BET-3 sovereignty across multi-principal.

## Phase 03 deliverable.

## A2A message schema

```json
{
  "type": "A2AMessage",
  "sender_principal_genesis_id": "sha256:...",
  "recipient_principal_genesis_id": "sha256:...",
  "sender_envelope_hash": "sha256:...",
  "recipient_envelope_hash_expected": "sha256:...",
  "action_type": "<enum>",
  "composed_intent_hash": "sha256:<hash of proposed collective outcome>",
  "timestamp": <iso8601>, "nonce": <hex>,
  "signature_by_sender_hex": <ed25519>
}
```

## Envelope-binding

Every A2A message covers `(sender_envelope_hash, recipient_envelope_hash, action_type, composed_intent_hash)`. Recipient verifies its envelope allows receiving this message type from this sender AND contributing to this composed_intent.

## Cross-principal dual-signed action

For actions affecting BOTH principals (shared calendar, shared budget): requires signed Grant Moment from BOTH principals. 24h cooling-off for high-stakes (matches specs/enterprise-deployment.md pattern).

## Composition-aware

`composed_intent_hash` evaluated against both principals' envelopes before delivery. Composition rules (per specs/envelope-model.md §Algorithms §Composition-rule DSL) apply cross-principal.

## T-106 defense

Composed intent must pass both principals' envelope checks INDEPENDENTLY; neither single envelope allows the composed action alone.

## Error taxonomy

| Error                                 | Trigger                                                                                | User action                                                                     | Retry                      |
| ------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | -------------------------- |
| `EnvelopeHashMismatchError`           | `recipient_envelope_hash_expected` ≠ recipient's live envelope hash at receive         | Sender re-fetches recipient's current envelope; resign                          | Manual                     |
| `RecipientEnvelopeRejectsActionError` | Recipient's envelope does not allow `action_type` from this sender                     | Refuse delivery; surface to recipient as Ledger entry only (no payload visible) | Never                      |
| `ComposedIntentRejectedError`         | `composed_intent_hash` fails composition-rule eval against either principal's envelope | Refuse cross-principal action; surface to both principals via Grant Moment      | Manual after envelope edit |
| `DualSignatureMissingError`           | Cross-principal dual-signed action missing one of the two signatures                   | Surface Grant Moment to missing principal; await dual-sign                      | Auto after dual-sign       |
| `CrossPrincipalCoolingOffError`       | High-stakes cross-principal action attempted within 24h of cooling-off                 | Wait for cooling-off window to close; resume                                    | Auto after window          |
| `NonceReplayError`                    | A2A message nonce already seen for this sender↔recipient pair                          | Refuse; sender re-issues with fresh nonce                                       | Manual                     |
| `SignatureInvalidError`               | Sender's ed25519 signature fails verification                                          | Refuse; sender's key may be revoked or rotated; consult specs/trust-lineage.md  | Never                      |

## Cross-references

- specs/envelope-model.md — composition_rules cross-principal.
- specs/grant-moment.md — dual-signed flow.
- specs/trust-lineage.md — cross-principal delegation.
- specs/shared-household.md — Shared Household principal lifecycle.
- specs/threat-model.md — T-106.

## Test location

- `tests/integration/test_a2a_envelope_binding.py` — `(sender_envelope_hash, recipient_envelope_hash, action_type, composed_intent_hash)` cover (Tier 2).
- `tests/integration/test_a2a_dual_signed_high_stakes.py` — 24h cooling-off + dual signature flow.
- `tests/regression/test_t106_a2a_adversarial_cooperation.py` — composed intent rejected when neither single envelope allows it but the composition would.
- `tests/integration/test_a2a_nonce_replay.py` — replay detection per sender↔recipient pair.

## Open questions

1. Composed-intent-hash semantics for ≥3 principals (extension beyond pairwise) — Phase 04 work.
2. 24h cooling-off duration — empirical calibration vs faster cycles for trusted dyads.
3. Recipient-side rejection telemetry — how much sender learns about why recipient refused (privacy vs UX).
