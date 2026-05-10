# ledger

## Purpose

Hash-chained append-only record of every grant, action, refusal, posture change, ritual event. Rooted in EATP Trust Lineage. Primary user-surface per doc 00 v3 §2.3 item 4.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/04-ledger.md` v1.
- **Threats mitigated:** T-003 retention + GDPR, T-004 two-phase signing, T-100 rollback, T-101 fork reconciliation, T-102 replay (deferred to trust-lineage), T-104 version binding.
- **BETs tested:** BET-6 contract parity (head-commitment byte identity).

## Entry envelope schema

```json
{
  "entry_id": "sha256:<content_hash>", "parent_hash": "sha256:<prev_entry_id>",
  "sequence": <int>,
  "lamport_clock": {
    "lamport_time": <int>,
    "device_id": <sha256>,
    "local_seq": <int>
  },
  "timestamp": <iso8601>, "type": <EntryType>,
  "intent_id": "sha256:<content_hash> | null",
  "content": {...type-specific...},
  "content_trust_level": "user-authored | tool-output | channel-message | derived-external | heartbeat | system | sub-agent | llm-authored",
  "description_content_hash": <sha256>, "description_content_hash_algorithm": "sha256",
  "signed_by": <device_key | genesis_key>,
  "signature_hex": <ed25519>,
  "algorithm_identifier": {...},
  "schema_version": "ledger-entry/1.0"
}
```

**Field semantics (V-02 + V-03 fix per round-1-specs-comprehensive.md):**

- `lamport_clock.lamport_time` — monotonic logical clock per doc 04 v1 §7. Max observed `lamport_time` across all local + ingested entries on this device + 1. Primary sort key for CRDT merge (see specs/ledger-merge.md).
- `lamport_clock.device_id` — SHA-256 of device binding pubkey. Secondary sort key (tie-breaker on `lamport_time` ties).
- `lamport_clock.local_seq` — per-device monotonic sequence; tertiary sort key.
- `intent_id` — SHA-256 content hash of Phase-A-signed intent envelope. Non-null on `PhaseARecord` (generated) + `PhaseBRecord` (linked to Phase A). Null on entry types unrelated to two-phase signing (e.g., `GenesisRecord`, `KeyRotationRecord`, `posture_change`). Links Phase A → Phase B across devices for orphan resolution + CRDT merge `IntentIdConflict` detection.

## Entry types

Every entry type MUST have a named producer spec that owns its schema, producer context, and verification semantics. Types without a producer spec are BLOCKED from appearing in this list (per `rules/orphan-detection.md`).

| Entry type                              | Producer spec (schema owner)                                                                                                                             | Signer               |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| `GenesisRecord`                         | specs/trust-lineage.md §GenesisRecord                                                                                                                    | Genesis self-sig     |
| `GenesisDeviceTransferRecord`           | specs/ledger.md §Ledger entry schemas §`GenesisDeviceTransferRecord` + specs/trust-lineage.md §GenesisRecord                                             | Genesis + device     |
| `RoleEnvelopeCreated`                   | specs/ledger.md §Ledger entry schemas §`RoleEnvelopeCreated`                                                                                             | Delegation key       |
| `envelope_edit`                         | specs/ledger.md §Ledger entry schemas §`envelope_edit`                                                                                                   | Delegation key       |
| `DelegationRecord`                      | specs/trust-lineage.md §DelegationRecord                                                                                                                 | Delegator            |
| `PhaseARecord`                          | specs/ledger.md §Ledger entry schemas §`PhaseARecord` + specs/ledger.md §Two-phase signing + specs/runtime-abstraction.md                                | Delegation key       |
| `PhaseBRecord`                          | specs/ledger.md §Ledger entry schemas §`PhaseBRecord` + specs/ledger.md §Two-phase signing + specs/runtime-abstraction.md                                | Runtime device key   |
| `PhaseAOrphanResolution`                | specs/ledger.md §Ledger entry schemas §`PhaseAOrphanResolution` + specs/ledger.md §Two-phase signing + specs/grant-moment.md                             | Runtime device key   |
| `RevocationRecord`                      | specs/trust-lineage.md §RevocationRecord                                                                                                                 | Revoker              |
| `ReasoningCommit`                       | specs/session-state.md §ReasoningCommit                                                                                                                  | Runtime device key   |
| `grant_moment`                          | specs/ledger.md §Ledger entry schemas §`grant_moment` + specs/grant-moment.md §Schema (dialog wire-formats)                                              | Delegation key       |
| `posture_change`                        | specs/ledger.md §Ledger entry schemas §`posture_change` + specs/posture-ladder.md §Algorithm                                                             | Genesis key          |
| `unlock_event`                          | specs/ledger.md §Ledger entry schemas §`unlock_event` + specs/trust-lineage.md §Duress honeypot (generic; duress-indistinguishable)                      | Genesis key          |
| `RuntimeAttestation`                    | specs/runtime-abstraction.md §Runtime attestation                                                                                                        | Runtime device key   |
| `KeyRotationRecord`                     | specs/trust-lineage.md §Key rotation (dual runtime-key + Genesis co-sig)                                                                                 | Old+new + Genesis    |
| `EntryKeyDestruction`                   | specs/ledger.md §Ledger entry schemas §`EntryKeyDestruction` + specs/trust-lineage.md §Key destruction                                                   | Old key final act    |
| `KeyDestructionEvent`                   | specs/ledger.md §Ledger entry schemas §`KeyDestructionEvent` + specs/trust-lineage.md §Key destruction (master-key destruction; distinct from per-entry) | Old key final act    |
| `MigrationAnnouncement`                 | specs/ledger.md §Ledger entry schemas §`MigrationAnnouncement` + specs/trust-lineage.md §Algorithm migration                                             | Genesis key          |
| `FoundationAllowlistOverrideRecord`     | specs/foundation-ops.md §Allowlist override                                                                                                              | Foundation + User    |
| `HaltedByRollback`                      | specs/ledger.md §Head commitment (rollback detection halt record)                                                                                        | Runtime device key   |
| `session_boundary_crossed`              | specs/session-state.md §Schema                                                                                                                           | Runtime device key   |
| `EnterpriseDeploymentRecord`            | specs/enterprise-deployment.md                                                                                                                           | Enterprise auth key  |
| `EnterpriseDeploymentDisablementRecord` | specs/ledger.md §Ledger entry schemas §`EnterpriseDeploymentDisablementRecord` + specs/enterprise-deployment.md §Disablement (T-024 R2-H5)               | User Genesis         |
| `FoundationHealthHeartbeatConsent`      | specs/ledger.md §Ledger entry schemas §`FoundationHealthHeartbeatConsent` + specs/foundation-health-heartbeat.md §Consent layer                          | Genesis key          |
| `ritual_completion`                     | specs/ledger.md §Ledger entry schemas §`ritual_completion` (consumers: daily-digest.md / weekly-posture-review.md / monthly-trust-report.md)             | Runtime device key   |
| `shamir_distribution_checklist_update`  | specs/ledger.md §Ledger entry schemas §`shamir_distribution_checklist_update` + specs/shamir-recovery.md §Distribution guidance                          | Genesis key          |
| `skill_install`                         | specs/ledger.md §Ledger entry schemas §`skill_install` + specs/skill-ingest.md §Install flow                                                             | Genesis key          |
| `skill_removal`                         | specs/ledger.md §Ledger entry schemas §`skill_removal` (consumer: specs/skill-ingest.md uninstall path)                                                  | Genesis key          |
| `channel_connected`                     | specs/ledger.md §Ledger entry schemas §`channel_connected` / `channel_disconnected` + specs/channel-adapters.md §Lifecycle methods                       | Genesis key          |
| `channel_disconnected`                  | specs/ledger.md §Ledger entry schemas §`channel_connected` / `channel_disconnected` + specs/channel-adapters.md §Lifecycle methods                       | Genesis key          |
| `model_switch`                          | specs/ledger.md §Ledger entry schemas §`model_switch` / `runtime_switch` + specs/runtime-abstraction.md §Runtime picker                                  | Genesis key          |
| `runtime_switch`                        | specs/ledger.md §Ledger entry schemas §`model_switch` / `runtime_switch` + specs/runtime-abstraction.md §Runtime picker                                  | Genesis key          |
| `LedgerConflictEntry`                   | specs/ledger.md §Ledger entry schemas §`LedgerConflictEntry` + specs/ledger-merge.md §Conflict types                                                     | Runtime device key   |
| `ClockSkewEvent`                        | specs/ledger.md §Ledger entry schemas §`ClockSkewEvent` (consumer: specs/remote-time-anchor.md)                                                          | Runtime device key   |
| `time_anchor`                           | specs/remote-time-anchor.md §Anchor record                                                                                                               | Runtime device key   |
| `system_error`                          | specs/ledger.md §System error (runtime-emitted internal-fault record)                                                                                    | Runtime device key   |
| `tool_output_sanitization_event`        | specs/tool-output-sanitization.md §Ledger record                                                                                                         | Runtime device key   |
| `HouseholdInviteAcceptedRecord`         | specs/ledger.md §Ledger entry schemas §`HouseholdInviteAcceptedRecord` + specs/shared-household.md                                                       | Inviter + invitee    |
| `HouseholdExitRecord`                   | specs/ledger.md §Ledger entry schemas §`HouseholdExitRecord` + specs/shared-household.md                                                                 | Departing + remainer |
| `HouseholdAbuseFlaggedRecord`           | specs/ledger.md §Ledger entry schemas §`HouseholdAbuseFlaggedRecord` + specs/shared-household.md                                                         | Flagger              |
| `HouseholdAbuseResolvedRecord`          | specs/ledger.md §Ledger entry schemas §`HouseholdAbuseResolvedRecord` + specs/shared-household.md                                                        | 2-of-N remainers     |
| `CoPresenceVerifiedRecord`              | specs/ledger.md §Ledger entry schemas §`CoPresenceVerifiedRecord` + specs/shared-household.md §Co-presence verification                                  | Both principals      |

**Local-only scope:** `DuressUnlockEvent` is NEVER written to the synced Ledger; it lives in the shadow segment per specs/data-model.md §Four physical containers #4 + specs/trust-lineage.md §Duress honeypot (CRIT-03).

## Ledger entry schemas (consolidated)

Every entry shares the envelope (per §Entry envelope schema below); the table above lists per-type schema producers. The entries below are owned at the Ledger layer (no dedicated owning spec) and have their schema declared here.

### `RoleEnvelopeCreated`

```json
{"type": "RoleEnvelopeCreated", "schema_version": "1.0",
 "envelope_id": "uuid-v7", "envelope_version": <int>, "envelope_hash": "sha256:...",
 "role_label": "<str>", "parent_envelope_hash": "sha256:... | null",
 "signed_by": "delegation_key"}
```

### `envelope_edit`

```json
{"type": "envelope_edit", "schema_version": "1.0",
 "envelope_id": "uuid-v7", "prior_version": <int>, "new_version": <int>,
 "diff_hash": "sha256:...", "rollback_grace_window_seconds": <int>,
 "signed_by": "delegation_key"}
```

### `ritual_completion`

Owner: emitted by whichever ritual surface completes (specs/daily-digest.md / specs/weekly-posture-review.md / specs/monthly-trust-report.md). Schema is uniform across rituals.

```json
{
  "type": "ritual_completion",
  "schema_version": "1.0",
  "ritual_kind": "daily_digest | weekly_posture_review | monthly_trust_report",
  "ritual_id": "uuid-v7",
  "scheduled_for": "<iso8601>",
  "completed_at": "<iso8601>",
  "channel_id": "<adapter id>",
  "user_response": "no_reply | yes | no | skip | modify",
  "receipt_hash": "sha256:...",
  "signed_by": "runtime_device_key"
}
```

### `channel_connected` / `channel_disconnected`

Owner: specs/channel-adapters.md §Lifecycle methods. Same schema for both, distinguished by `type`.

```json
{
  "type": "channel_connected | channel_disconnected",
  "schema_version": "1.0",
  "channel_id": "<adapter id>",
  "principal_genesis_id": "sha256:...",
  "credential_entry_ref": "<connection-vault entry_id> | null",
  "capabilities_hash": "sha256:...", // hash of ChannelCapabilities at this moment
  "reason": "user_action | quota_exhausted | auth_revoked | shutdown",
  "signed_by": "genesis_key"
}
```

### `ClockSkewEvent`

Owner: specs/remote-time-anchor.md (defense against T-103 clock-skew). Emitted whenever local-clock vs remote-anchor delta exceeds tolerance.

```json
{"type": "ClockSkewEvent", "schema_version": "1.0",
 "local_clock_at_detection": "<iso8601>",
 "anchor_clock_at_detection": "<iso8601>",
 "skew_milliseconds": <int>,
 "tolerance_milliseconds": <int>,
 "anchor_quorum_count": <int>,
 "anchor_quorum_threshold": <int>,
 "actions_paused": <bool>,  // true if Temporal-dimension actions paused
 "signed_by": "runtime_device_key"}
```

### `MigrationAnnouncement` (schema thinness — MED-R3-1 closure)

Owner: specs/trust-lineage.md §Algorithm migration.

```json
{"type": "MigrationAnnouncement", "schema_version": "1.0",
 "from_algorithm_identifier": {...},
 "to_algorithm_identifier": {...},
 "effective_at": "<iso8601>",
 "foundation_steward_signatures_hex": ["<ed25519>", ...],  // M-of-N
 "signed_by": "genesis_key"}
```

### `EntryKeyDestruction` (schema thinness — MED-R3-1 closure)

Owner: specs/trust-lineage.md §Key destruction (per-entry destruction; distinct from `KeyDestructionEvent` master-key form).

```json
{
  "type": "EntryKeyDestruction",
  "schema_version": "1.0",
  "destroyed_entry_id": "<ledger-entry-id>",
  "destroyed_at": "<iso8601>",
  "destruction_reason": "retention_expired | gdpr_deletion | user_action | revocation_cascade",
  "signed_by": "old_per_entry_key"
} // final act of the destroyed key
```

### `shamir_distribution_checklist_update` (schema thinness — MED-R3-1 closure)

Owner: specs/shamir-recovery.md §Distribution guidance.

```json
{"type": "shamir_distribution_checklist_update", "schema_version": "1.0",
 "checklist_revision": <int>,
 "shard_holders": [{"shard_index": <int>, "holder_label": "<str>", "last_verified_at": "<iso8601>"}],
 "completion_pct": <float 0..1>,
 "signed_by": "genesis_key"}
```

### `skill_removal` (HIGH-R4-1 closure)

Owner: specs/skill-ingest.md (uninstall path; install path is §Install flow).

```json
{
  "type": "skill_removal",
  "schema_version": "1.0",
  "skill_id": "<str>",
  "skill_name": "<str>",
  "removal_reason": "user_action | registry_revocation | abuse_flag_resolved | force_uninstall_on_pattern_match",
  "removed_at": "<iso8601>",
  "signed_by": "genesis_key"
}
```

### `unlock_event` (MED-R4-8 closure)

Owner: specs/trust-lineage.md §Duress honeypot. Generic; duress vs real unlock is structurally indistinguishable at the Ledger level (T-002 defense).

```json
{
  "type": "unlock_event",
  "schema_version": "1.0",
  "unlocked_at": "<iso8601>",
  "device_fingerprint_hash": "sha256:...",
  "session_id": "uuid-v7",
  "signed_by": "genesis_key"
}
```

### `posture_change` (MED-R4-8 closure)

Owner: specs/posture-ladder.md §Algorithm. Records every posture transition (raise / lower / annual decay).

```json
{
  "type": "posture_change",
  "schema_version": "1.0",
  "from_posture": "PSEUDO | TOOL | SUPERVISED | DELEGATING | AUTONOMOUS",
  "to_posture": "PSEUDO | TOOL | SUPERVISED | DELEGATING | AUTONOMOUS",
  "dimension_scope": "global | financial | operational | temporal | data_access | communication",
  "trigger": "user_request | annual_decay | enterprise_attestation | weekly_review | authorship_threshold",
  "evidence_ref": "<ledger-entry-id | null>",
  "signed_by": "genesis_key"
}
```

### `model_switch` / `runtime_switch` (MED-R4-8 closure)

Owner: specs/runtime-abstraction.md §Runtime picker. Same schema for both, distinguished by `type`.

```json
{"type": "model_switch | runtime_switch", "schema_version": "1.0",
 "from_identifier": "<str>",  // model name or runtime family+version
 "to_identifier": "<str>",
 "reason": "user_action | binding_gap | provider_unreachable | annotation_drift | algorithm_migration",
 "envelope_re_pin_required": <bool>,
 "signed_by": "genesis_key"}
```

### `HouseholdInviteAcceptedRecord` (MED-R4-8 closure)

Owner: specs/shared-household.md.

```json
{
  "type": "HouseholdInviteAcceptedRecord",
  "schema_version": "1.0",
  "household_id": "uuid-v7",
  "inviter_principal_genesis_id": "sha256:...",
  "invitee_principal_genesis_id": "sha256:...",
  "invite_envelope_scope_hash": "sha256:...",
  "accepted_at": "<iso8601>",
  "co_presence_verified_ref": "<ledger-entry-id>",
  "signed_by": ["inviter_genesis", "invitee_genesis"]
}
```

### `HouseholdExitRecord` (MED-R4-8 closure)

Owner: specs/shared-household.md.

```json
{"type": "HouseholdExitRecord", "schema_version": "1.0",
 "household_id": "uuid-v7",
 "departing_principal_genesis_id": "sha256:...",
 "remaining_principal_genesis_ids": ["sha256:...", ...],
 "exit_reason": "voluntary | abuse_response | dissolution",
 "exited_at": "<iso8601>",
 "signed_by": ["departing_genesis", "remaining_genesis"]}
```

### `HouseholdAbuseFlaggedRecord` (MED-R4-8 closure)

Owner: specs/shared-household.md.

```json
{
  "type": "HouseholdAbuseFlaggedRecord",
  "schema_version": "1.0",
  "household_id": "uuid-v7",
  "flagger_principal_genesis_id": "sha256:...",
  "flag_payload_hash": "sha256:...", // payload encrypted; hash for audit-only
  "flagged_at": "<iso8601>",
  "abuse_resolved_ref": "<ledger-entry-id | null>",
  "signed_by": "flagger_genesis"
}
```

### `HouseholdAbuseResolvedRecord` (MED-R4-8 closure)

Owner: specs/shared-household.md.

```json
{
  "type": "HouseholdAbuseResolvedRecord",
  "schema_version": "1.0",
  "household_id": "uuid-v7",
  "abuse_flagged_ref": "<ledger-entry-id>",
  "resolution_outcome": "exit | reconciliation | escalation",
  "resolved_at": "<iso8601>",
  "signed_by": ["remainer_1_genesis", "remainer_2_genesis"]
}
```

### `CoPresenceVerifiedRecord` (MED-R4-8 closure)

Owner: specs/shared-household.md §Co-presence verification.

```json
{
  "type": "CoPresenceVerifiedRecord",
  "schema_version": "1.0",
  "principal_a_genesis_id": "sha256:...",
  "principal_b_genesis_id": "sha256:...",
  "verification_method": "in_person_qr | proximity_bluetooth | shared_secret_phrase",
  "verified_at": "<iso8601>",
  "signed_by": ["principal_a_genesis", "principal_b_genesis"]
}
```

### `grant_moment` (MED-R5-2 closure)

Owner: specs/grant-moment.md (dialog wire-formats `GrantMomentRequest` + `GrantMomentResult` per §Schema; this is the Ledger-row form persisted by the runtime after M3 sign-or-decline).

```json
{"type": "grant_moment", "schema_version": "1.0",
 "request_ref": "uuid-v7",  // pointer to GrantMomentRequest
 "result_ref": "uuid-v7",   // pointer to GrantMomentResult
 "intent_id": "sha256:...",
 "decision": "approve_once | approve_and_author | deny | modify",
 "decided_at": "<iso8601>",
 "envelope_version_at_decision": <int>,
 "novelty_class": "novel | familiar_repeat | high_stakes",
 "signed_by": "delegation_key"}
```

### `PhaseARecord` (MED-R5-2 closure)

Owner: specs/ledger.md §Two-phase signing + specs/runtime-abstraction.md.

```json
{"type": "PhaseARecord", "schema_version": "1.0",
 "intent_id": "sha256:...",
 "tool_name": "<str>",
 "tool_args_canonical_hash": "sha256:...",
 "envelope_version": <int>,
 "envelope_check_passed": true,
 "phase_a_at": "<iso8601>",
 "ttl_expires_at": "<iso8601>",
 "signed_by": "delegation_key"}
```

### `PhaseBRecord` (MED-R5-2 closure)

Owner: specs/ledger.md §Two-phase signing + specs/runtime-abstraction.md.

```json
{
  "type": "PhaseBRecord",
  "schema_version": "1.0",
  "intent_id": "sha256:...",
  "phase_a_ref": "<ledger-entry-id>",
  "outcome": "success | failure | partial",
  "outcome_summary_hash": "sha256:...",
  "phase_b_at": "<iso8601>",
  "signed_by": "runtime_device_key"
}
```

### `PhaseAOrphanResolution` (MED-R5-2 closure)

Owner: specs/ledger.md §Two-phase signing + specs/grant-moment.md (Grant Moment surfaces at next session start).

```json
{
  "type": "PhaseAOrphanResolution",
  "schema_version": "1.0",
  "phase_a_ref": "<ledger-entry-id>",
  "intent_id": "sha256:...",
  "resolution": "retry_idempotent | record_as_failed | investigate",
  "user_decision_grant_ref": "<ledger-entry-id>",
  "resolved_at": "<iso8601>",
  "signed_by": "runtime_device_key"
}
```

### `KeyDestructionEvent` (MED-R5-2 closure)

Owner: specs/trust-lineage.md §Key destruction. Distinct from `EntryKeyDestruction` (per-entry key destruction); this is master-key destruction.

```json
{
  "type": "KeyDestructionEvent",
  "schema_version": "1.0",
  "destroyed_key_scope": "master | runtime_device | delegation",
  "destroyed_key_pubkey_hex": "<hex>",
  "destroyed_at": "<iso8601>",
  "destruction_reason": "user_action | revocation_cascade | compromise_response | retention_policy",
  "successor_key_pubkey_hex": "<hex> | null",
  "signed_by": "old_key"
}
```

### `LedgerConflictEntry` (MED-R5-2 closure)

Owner: specs/ledger-merge.md §Conflict types. Persisted when CRDT merge surfaces a conflict that requires user adjudication.

```json
{"type": "LedgerConflictEntry", "schema_version": "1.0",
 "conflict_kind": "IntentIdConflict | DivergentParent | LamportTie | DuplicateNonce",
 "left_entry_ref": "<ledger-entry-id>",
 "right_entry_ref": "<ledger-entry-id>",
 "left_lamport_clock": {"lamport_time": <int>, "device_id": "<str>", "local_seq": <int>},
 "right_lamport_clock": {"lamport_time": <int>, "device_id": "<str>", "local_seq": <int>},
 "merge_decision": "left_wins | right_wins | both_kept | user_pending",
 "resolved_at": "<iso8601 | null>",
 "signed_by": "runtime_device_key"}
```

### `EnterpriseDeploymentDisablementRecord` (MED-R5-2 closure)

Owner: specs/enterprise-deployment.md §Disablement (T-024 R2-H5).

```json
{
  "type": "EnterpriseDeploymentDisablementRecord",
  "schema_version": "1.0",
  "edr_ref": "<ledger-entry-id>", // pointer to EnterpriseDeploymentRecord being disabled
  "disablement_reason": "user_offboarding | enterprise_revocation | compromise_response | policy_change",
  "disabled_at": "<iso8601>",
  "user_acknowledged": true,
  "signed_by": "user_genesis"
}
```

### `FoundationHealthHeartbeatConsent` (MED-R5-2 closure)

Owner: specs/foundation-health-heartbeat.md §Consent layer.

```json
{
  "type": "FoundationHealthHeartbeatConsent",
  "schema_version": "1.0",
  "consent_state": "opted_in | opted_out | pending",
  "consent_text_hash": "sha256:...", // pinned consent dialog text bytes
  "consented_at": "<iso8601>",
  "rotation_window_quarter": "<YYYY-Qn>", // installation random ID rotation epoch
  "signed_by": "genesis_key"
}
```

### `GenesisDeviceTransferRecord` (MED-R5-2 closure)

Owner: specs/trust-lineage.md §GenesisRecord (device-attestation enforcement).

```json
{
  "type": "GenesisDeviceTransferRecord",
  "schema_version": "1.0",
  "old_device_attestation": {
    "device_pubkey_hex": "<hex>",
    "device_fingerprint_hash": "sha256:..."
  },
  "new_device_attestation": {
    "device_pubkey_hex": "<hex>",
    "device_fingerprint_hash": "sha256:..."
  },
  "transferred_at": "<iso8601>",
  "transfer_reason": "device_replacement | device_loss | device_upgrade",
  "signed_by": ["old_device_genesis", "new_device_genesis"]
}
```

### `skill_install` (MED-R5-2 closure)

Owner: specs/skill-ingest.md §Install flow.

```json
{"type": "skill_install", "schema_version": "1.0",
 "skill_id": "<str>",
 "skill_name": "<str>",
 "skill_source": "envoy-registry | community | organization | force_install",
 "skill_envelope_companion_hash": "sha256:...",
 "co_validator_passed": true,
 "permissions_granted": ["<permission>", ...],
 "installed_at": "<iso8601>",
 "signed_by": "genesis_key"}
```

## Two-phase signing (T-004)

- **Phase A** — intent signed by delegation key; envelope check runs pre-sign; recorded before execution.
- **Phase B** — outcome signed by runtime device key; linked by `intent_id`.
- **Orphan resolution** — 30-day window; Grant Moment at next session start; retry (idempotent tools only) / record-as-failed / investigate.

## Head commitment (T-100)

- Runtime-device-key-signed `HeadCommitment` at every sync.
- Monotonic non-decreasing `head_sequence`.
- Rollback detected on decrease → `LedgerRollbackDetectedError`.
- Complements Trust-Lineage chain-head (Genesis-signed, per specs/trust-lineage.md §two-head-commitments).

### `HaltedByRollback` record

When the runtime detects a rollback (`head_sequence` decrease or `HeadCommitment` signature failure), it appends a `HaltedByRollback` entry BEFORE halting further Ledger writes. The entry preserves the last-known-good head + the detected-inconsistent head + the runtime attestation, so forensic recovery can locate the divergence point.

```json
{
  "type": "HaltedByRollback",
  "schema_version": "halt/1.0",
  "last_known_good_head": {"sequence": <int>, "entry_id": "sha256:..."},
  "detected_head": {"sequence": <int>, "entry_id": "sha256:..."},
  "detection_reason": "sequence_decrease | head_signature_mismatch | algorithm_identifier_downgrade",
  "runtime_identity": {...},
  "halted_at": "<iso8601>"
}
```

The above is the **inner content** persisted at `EntryEnvelope.content`. The
outer `EntryEnvelope` carries `type="HaltedByRollback"`, `signed_by=device:<id>`,
and `signature_hex=<ed25519 hex>` per § Entry envelope schema (lines 17-33).
Inner content does NOT duplicate `signature_hex`; the canonical wire-form
locates the signature on the outer envelope only.

Signed by the runtime device key. After halt, the runtime refuses further Ledger writes until the user completes an `envoy ledger audit` ritual that resolves the divergence.

## System error (runtime-emitted fault records)

Uncaught runtime exceptions, classifier unavailability beyond retry, signature verification failures not attributable to a specific primitive, and other internal-fault conditions produce a `system_error` Ledger entry instead of a stack trace:

```json
{
  "type": "system_error",
  "schema_version": "system-error/1.0",
  "fault_class": "classifier_unavailable | signature_verification | runtime_panic | resource_exhausted | other",
  "fault_fingerprint": "sha256:<stable_hash_of_fault_class+caller_site>",
  "context_hash": "sha256:<redacted_context>",
  "user_surfaced": <bool>,
  "signed_by": "runtime_device_key",
  "signature_hex": "ed25519"
}
```

Content MUST NOT echo raw PII, secrets, or envelope internals — only a stable fault fingerprint. Fault fingerprints cluster related faults for operational visibility without content leaks (see `rules/dataflow-classification.md` + `rules/event-payload-classification.md`).

## CRDT merge (T-101) — see specs/ledger-merge.md

- Lamport-clock ordering on merge.
- Conflict-flood rate-limit: 20 unresolved per principal per session; semantic batching.
- `LedgerConflictEntry` written for each detected conflict; user resolution at next session start.

## Retention + GDPR (T-003)

- **Default:** forever.
- **Tombstone** — metadata preserved (timestamp, type, signer); content replaced with commitment.
- **Per-entry key destruction** — stronger; keys destroyed via `EntryKeyDestruction` record; `destroyed_entries` set in Trust Vault.
- **User retention policy** — envelope declares `{grant_moments: 2y, actions: 5y, posture_changes: forever}`.

## Segment boundary on MigrationAnnouncement

Ledger partitioned into algorithm-identifier-tagged segments at each `MigrationAnnouncement`. Chain verification dispatches per segment.

## Export + independent verifier

- `envoy ledger export --format json` → signed export bundle.
- PDF form carries `receipt_hash` pointing to JSON.
- Independent reference-verifier (`envoy-ledger-verify`) separate Python package; Phase 01 exit gate per doc 00 v3.

## Error taxonomy

| Error                           | Trigger                                                                                      | User action                                                                            |
| ------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `LedgerRollbackDetectedError`   | `HeadCommitment.head_sequence` decreases between syncs OR head signature fails verification. | Run `envoy ledger audit`; divergence surfaces with last-known-good head.               |
| `LedgerVerificationFailedError` | Hash-chain verification at entry N fails (parent_hash mismatch or signature failure).        | Run `envoy-ledger-verify`; identifies failing entry; manual audit required.            |
| `LedgerSyncConflictError`       | Sync target and local disagree on `HeadCommitment` beyond CRDT-mergeable range.              | Restart sync; if persists, rebuild from last good head.                                |
| `EntryKeyDestroyedError`        | Read attempted against an entry in `destroyed_entries` set (content keys destroyed).         | Entry metadata still readable; content unrecoverable by design.                        |
| `PhaseAOrphanDetectedError`     | Session start finds Phase A intent in `pending_phase_a_orphans` beyond 30d TTL.              | Grant Moment surfaces; user resolves retry / record-as-failed / investigate.           |
| `LedgerConflictFloodError`      | CRDT merge conflicts exceed 20 per-principal cap in one session.                             | Sync suspended until existing conflicts resolved via `envoy ledger conflicts resolve`. |
| `LedgerHaltedError`             | Ledger already halted by `HaltedByRollback`; new append refused.                             | Complete audit ritual before further writes.                                           |
| `LedgerAlgorithmMismatchError`  | Entry's `algorithm_identifier` does not match the active segment per §Segment boundary.      | Verify segment boundary; ensure current segment uses matching algorithm.               |

All errors emitted as `system_error` Ledger entries per §System error when they originate inside the runtime.

## Cross-references

- **specs/trust-lineage.md** — Delegation/Genesis/Revocation records as Ledger entries.
- **specs/envelope-model.md** — envelope_edit + effective-envelope-snapshot tracking.
- **specs/ledger-merge.md** — CRDT protocol.
- **specs/runtime-abstraction.md** — `ledger_append`, `ledger_query`, `ledger_verify_chain`, `head_commitment`, `phase_a_sign_intent`, `phase_b_sign_outcome`, `phase_a_orphan_resolve`.
- **specs/data-model.md** — per-entry encryption + master_key derivation.
- **specs/threat-model.md** — T-003, T-004, T-100, T-101, T-104.

## Test location

- `tests/tier1/test_ledger_canonical_dumps_byte_pinning.py` — canonical-bytes byte-identity pinning across producer + verifier; covers `HaltedByRollbackRecord` `_SCHEMA_VERSION = "halt/1.0"` + sorted `runtime_identity.algorithm_identifier` tuple (Tier 1, shipped T-01-17 + /redteam Round 2).
- `tests/tier1/test_format_record_id_for_event.py` — `format_record_id_for_event` redaction across every entry-type emission per `specs/classification-policy.md` (Tier 1, shipped T-01-17).
- `tests/regression/test_haltedbyrollback_record_minted_on_rollback.py` — rollback detection writes `HaltedByRollbackRecord` before refusing further writes; covers T-100 head-commitment rollback halt (regression, shipped /redteam Round 2).
- `tests/regression/test_round1_observability_log_keys.py` — round-1 WARN log-key contract pinned for halt-record + rollback-detected log lines (regression, shipped /redteam Round 2).

## Out of scope (this phase)

Tests scheduled to land in named successor shards. Per `rules/spec-accuracy.md` Rule 4, the workstream lives in `workspaces/phase-01-mvp/todos/active/`; this section names ONLY the test-file path each shard will create. Citations move into `## Test location` above as the shards land.

- `envoy-ledger-verify` independent verifier — Phase 01 exit gate, scheduled in T-06-104 + T-08-131 (`06-side-channel-verifier.md`, `08-tests-tier3-acceptance.md`).
- Phase A → Phase B linkage by `intent_id` (two-phase signing) — scheduled in T-03-50 (`03-wave-3-grant-moment-budget.md`).
- T-004 streaming-LLM pre-sign defense — scheduled in T-03-50.
- T-008 Grant Moment replay defense via Phase A `intent_id` — scheduled in T-03-50.

Phase-04+ work is out of Phase 01 scope: Lamport-clock 3-field merge ordering on CRDT (multi-device), `head_sequence` monotonicity across syncs, `EntryKeyDestruction` + `destroyed_entries`, `KeyDestructionEvent` distinct-from-per-entry, segment-boundary partition on `MigrationAnnouncement`, post-quantum migration path + allowlist gate, regressions T-003 / T-013 / T-101 / T-104. All Phase-04+ items tracked at `specs/threat-model.md` and `specs/ledger-merge.md`.

## Open questions

- CRDT canonical ordering (Lamport vs VClock) — Lamport chosen; revisit Phase 03.
- Per-entry key destruction under master_key leak — documented residual; Phase 04 per-segment keys.
- Verifier language — Python community default; Rust variant Phase 04.
