# shared-household

## Purpose

Multi-principal Envoy configuration where 2–10 named humans share a device/deployment with distinct Genesis Records, distinct passphrases, distinct envelopes, and a shared Ledger. Phase 03 exit-gate acceptance criterion: 5-person Shared Household E2E (specs/acceptance-metrics.md).

## Provenance

- **Source analysis:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md v3 §4.2 item 14` + `09-threat-model.md v3 T-002 household-adversarial` + `02-envelope-model.md v3 §3.5 composition semantics`.
- **Threats mitigated:** T-002 household-adversarial exploitation, T-041 duress honeypot under shared device, T-090 Grant-Moment spam against non-inviter.
- **BETs tested:** BET-3 sovereignty (per-principal), BET-12 governance-primary-surface under multi-principal, Phase 03 5-person acceptance gate.

## Principal lifecycle

### Invite

1. Inviter (existing principal with posture ≥ TOOL) runs `envoy household invite --display-name "Alex"`.
2. Generates invite token: 32-byte random; expiry 72h; single-use.
3. Invitee unlocks with their own passphrase on same device; creates distinct Genesis Record; Shamir ritual mandatory per specs/shamir-recovery.md (each principal has independent 3-of-5 shards).
4. Inviter signs `HouseholdInviteAcceptedRecord` entry binding invitee's Genesis public key to the household.
5. Invitee's first posture defaults to `PSEUDO` (specs/posture-ladder.md).

### Co-presence verification (T-002 mitigation)

- First Delegation Record per cross-principal action requires physical co-presence evidence: shared QR code scanned on both principals' authenticated sessions within 60s window.
- After initial ceremony, cross-principal actions within 30-day window may skip co-presence; after 30d, co-presence required again.
- Co-presence verification is itself a Ledger entry `CoPresenceVerifiedRecord` dual-signed.

### Exit

1. Departing principal runs `envoy household exit`.
2. Their Genesis remains cryptographically valid (Ledger history preserved), but:
   - Trust Vault removes their envelope + ritual state.
   - Connection Vault entries scoped to their principal are re-encrypted to new keys (specs/connection-vault.md §Per-principal isolation).
   - Future Delegations from exited Genesis are rejected unless re-invited.
3. `HouseholdExitRecord` Ledger entry dual-signed by departing principal + at least one remaining principal.

### Abuse-survivor review (T-002 enforcement)

- Any principal may flag another principal's action as abusive; flag creates `HouseholdAbuseFlaggedRecord` with reason_content_hash.
- Flag auto-demotes the flagged principal's posture to TOOL.
- 7-day abuse-survivor review period; flagged principal cannot ratchet back up.
- Resolved by 2-of-N remaining principals signing `HouseholdAbuseResolvedRecord`.
- Unresolved at 7d → persists; flagged principal may still author their own constraints but cannot issue cross-principal Delegations.

## Schema

### HouseholdConfig (Trust Vault region)

```json
{
  "household_id": "sha256:<content_hash>",
  "schema_version": "household/1.0",
  "principals": [
    {
      "genesis_id": "sha256:...",
      "display_name": "Alex",
      "joined_at": "<iso8601>",
      "status": "active | exited | abuse-flagged",
      "posture_level": "PSEUDO | TOOL | SUPERVISED | DELEGATING | AUTONOMOUS"
    }
  ],
  "invites_pending": [
    {
      "invite_id": "sha256:...",
      "display_name": "Bea",
      "expires_at": "<iso8601>",
      "token_hash": "sha256:..."
    }
  ],
  "cross_principal_policy": {
    "co_presence_window_days": 30,
    "auto_demote_on_abuse_flag": true,
    "abuse_review_days": 7
  }
}
```

### Ledger entry types owned by shared-household

- `HouseholdInviteAcceptedRecord` — dual-signed (inviter + invitee); links invitee Genesis to household.
- `HouseholdExitRecord` — dual-signed (departing + one remaining principal).
- `HouseholdAbuseFlaggedRecord` — single-signed (flagger); reason hashed.
- `HouseholdAbuseResolvedRecord` — 2-of-N signed.
- `CoPresenceVerifiedRecord` — dual-signed; cryptographic proof of co-presence ceremony.

All registered in specs/ledger.md §Entry types.

## Composition algorithm (cross-references specs/envelope-model.md)

Cross-principal action:

```python
def compose_cross_principal_action(principals: list[Principal], action: Action) -> ComposedEnvelope:
    # 1. Each participating principal's envelope is fetched from their Trust Vault.
    envelopes = [p.current_envelope() for p in principals]
    # 2. intersect_envelopes() per specs/envelope-model.md §Algorithms.
    composed = envelopes[0]
    for env in envelopes[1:]:
        composed = intersect_envelopes(composed, env)
    # 3. Effective posture = MIN across principals (specs/posture-ladder.md).
    composed.effective_posture = min(p.posture_level for p in principals)
    # 4. Each principal's Grant Moment required unless all are DELEGATING/AUTONOMOUS
    #    under envelope that covers this action.
    return composed
```

**Signature rule:** cross-principal Delegations carry a `co_signers: [genesis_id]` field; each co-signer appends their signature + canonical form hash (JCS). Signature order is lexicographic on genesis_id.

## Ritual routing

Rituals are per-principal:

- Daily Digest (specs/daily-digest.md) — one per principal; may be jointly viewed.
- Weekly Posture Review (specs/weekly-posture-review.md) — each principal runs their own.
- Monthly Trust Report (specs/monthly-trust-report.md) — per-principal + household-summary view.
- Grant Moment (specs/grant-moment.md) — routed to the principal whose envelope blocked the action; cross-principal needs all.

## Error taxonomy

| Error                                         | Trigger                                                                  | User action                                               |
| --------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------- |
| `HouseholdInviteExpiredError`                 | Invite token past 72h expiry.                                            | Inviter regenerates invite.                               |
| `HouseholdInviteReplayError`                  | Invite token reused after acceptance.                                    | Security alert; new invite required.                      |
| `HouseholdCoPresenceRequiredError`            | Cross-principal action without co-presence evidence in window.           | Run co-presence ceremony (QR scan).                       |
| `HouseholdAbuseFlagActiveError`               | Delegation attempt by abuse-flagged principal.                           | Wait for review; restore via 2-of-N resolution.           |
| `HouseholdCrossPrincipalConsentRequiredError` | Action requires multi-principal envelope intersect; consent not present. | Other principals must approve via Grant Moment.           |
| `HouseholdExitInProgressError`                | Action attempted against exiting principal.                              | Retry after exit completes.                               |
| `HouseholdPrincipalLimitExceededError`        | Invite beyond 10 principals.                                             | Cap enforced; upgrade to enterprise tier for larger orgs. |

## Cross-references

- **specs/trust-lineage.md** — each principal has independent Genesis + key rotation.
- **specs/envelope-model.md** — `intersect_envelopes` composition for cross-principal actions.
- **specs/posture-ladder.md** — per-principal posture; MIN composition for cross-principal.
- **specs/ledger.md** — household-specific entry types.
- **specs/grant-moment.md** — cross-principal Grant dispatch.
- **specs/a2a-messaging.md** — principal-to-principal messaging wraps shared-household composition.
- **specs/shamir-recovery.md** — per-principal independent 3-of-5.
- **specs/connection-vault.md** — per-principal isolation.
- **specs/acceptance-metrics.md** — Phase 03 5-person E2E gate.
- **specs/threat-model.md** — T-002, T-041, T-090.

## Test location

`tests/integration/test_shared_household_e2e.py` (Phase 03 gate) exercises:

- 5-principal invite + ratchet-up + daily digest round-trip.
- Cross-principal action requiring co-presence.
- Abuse flag → auto-demote → 2-of-N resolution.
- Exit with credential re-encryption.
- Invite token replay rejection.

Threat tests T-002/T-041/T-090 live here, per specs/threat-model.md §Test location.

## Open questions

1. Upper bound of 10 principals — empirical Phase 03; enterprise tier begins beyond.
2. Co-presence window trade-off (30d too long? too short?) — user research Phase 03.
3. Abuse-flag anonymity — current: flagger identity visible; Phase 04 may blind.
4. Shared-household duress interplay — each principal has distinct duress honeypot; cross-principal duress coupling TBD.
