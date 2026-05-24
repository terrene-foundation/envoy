# connection-vault

## Purpose

Third-party credential storage (API keys, channel tokens, OAuth refresh) — OS keychain wrapper, per-principal isolated.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/10-data-model.md v1 §3`.
- **Threats mitigated:** T-007 credential storage; never-synced by design.
- **BETs tested:** BET-3 sovereignty.

## Distinct from Trust Vault

- Trust Vault: Envoy's own keys + envelope.
- Connection Vault: third-party credentials (API keys, channel bot tokens, OAuth refresh).

## Platforms

- macOS: Keychain access group specific to Envoy.
- Windows: Credential Manager.
- Linux: Secret Service (GNOME Keyring / KWallet).
- iOS: Secure Enclave.
- Android: Keystore.

## Per-entry schema

| Field                  | Type                                                                     | Description                                                                                                                       |
| ---------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `entry_id`             | UUID-v7                                                                  | Stable identifier for this credential entry; client refers to it by id.                                                           |
| `principal_genesis_id` | sha256 hex                                                               | Owning principal (per specs/trust-lineage.md).                                                                                    |
| `credential_type`      | enum (api_key / bot_token / oauth_refresh / basic_auth / webhook_secret) | Drives rotation + UX hint.                                                                                                        |
| `service_identifier`   | str                                                                      | Free-form ("openai", "telegram-bot", "stripe-webhook"); registered against specs/foundation-ops.md service registry.              |
| `entry_envelope_scope` | `EnvelopeScopeRef`                                                       | The envelope-scope under which this credential may be used (per specs/envelope-model.md §Operational + Communication dimensions). |
| `ciphertext`           | bytes                                                                    | OS-keychain-encrypted credential payload (no plaintext leaves keychain).                                                          |
| `created_at`           | `datetime` UTC                                                           | Entry creation timestamp; signed for audit.                                                                                       |
| `last_used_at`         | `datetime` UTC                                                           | Updated on every successful retrieval; useful for unused-credential cleanup.                                                      |
| `expires_at`           | `datetime` or `null`                                                     | Optional expiry; runtime refuses use after expiry.                                                                                |
| `usage_counter`        | `int`                                                                    | Monotonic counter; observable via specs/foundation-health-heartbeat.md (anonymous aggregate only).                                |
| `rotation_policy`      | enum (never / yearly / quarterly / monthly / on_event)                   | Policy hint for UX nudges.                                                                                                        |

## Per-principal isolation (Phase 03)

Entries keyed by `principal_genesis_id`. Cross-principal access requires Grant Moment.

## Never synced

OS keychain is device-local by design. After Shamir recovery, user re-authenticates each channel/model via fresh Grant Moments.

## Clipboard hygiene

Grant Moment dialogs that capture credentials use secure-text-field inputs (bypass clipboard on iOS; Secret.Filled on Android). Auto-clear clipboard after N seconds (30 default).

## Error taxonomy

| Error                                        | Trigger                                                                        | User action                                                     | Retry                      |
| -------------------------------------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------- | -------------------------- |
| `KeychainUnavailableError`                   | OS keychain not unlocked or service unavailable                                | Unlock keychain (Touch ID / passphrase / device unlock); retry  | Auto after unlock          |
| `EntryExpiredError`                          | Retrieval after `expires_at`                                                   | Re-authenticate via Grant Moment; rotation_policy hint surfaces | Manual after rotation      |
| `CrossPrincipalAccessRefusedError`           | Principal A retrieves entry owned by Principal B without Grant Moment          | Request cross-principal Grant Moment from owning principal      | Manual after Grant         |
| `EnvelopeScopeMismatchError`                 | Caller's session envelope does not include this entry's `entry_envelope_scope` | Refuse use; user widens envelope OR uses different credential   | Manual after envelope edit |
| `EntryNotFoundError`                         | `entry_id` absent (deleted, never existed, or wrong principal)                 | UX surfaces "credential gone"; user re-pairs channel            | Manual                     |
| `RotationOverdueWarn` (advisory, not raised) | `rotation_policy` cadence exceeded since `created_at`                          | UX nudge to rotate; not a hard block                            | Manual                     |
| `UsageCounterOverflowError`                  | `usage_counter` reaches int64 ceiling (defensive guard)                        | Reset counter via re-pair; investigate cause (hostile usage?)   | Never (programming bug)    |
| `PrincipalRequiredError`                     | Vault constructed without a valid sha256-hex `principal_genesis_id`            | Provide the principal's `genesis_id` (sha256 hex, 64 lowercase) | Never (programming bug)    |
| `InvalidServiceIdentifierError`              | `service_identifier` fails `^[a-z0-9._-]+$` / >256 chars / empty               | Rename service per the validator contract                       | Manual after rename        |
| `RecordSchemaVersionError`                   | Keychain record's `schema_version` differs from this build's contract          | Upgrade Envoy build OR re-pair credential at current version    | Manual after upgrade       |
| `CorruptedRecordError`                       | Keychain record / index payload fails JSON decode / shape validation           | Re-pair credential (record was tampered or truncated)           | Manual after re-pair       |

## §X Change log

- 2026-05-24 — Added 4 defensive error rows (`PrincipalRequiredError`, `InvalidServiceIdentifierError`, `RecordSchemaVersionError`, `CorruptedRecordError`) per code-reviewer HIGH-1 + security-reviewer M2/M3 (T-01-24 gate-review). `PrincipalRequiredError` mirrors `envoy/trust/errors.py` contract (`rules/tenant-isolation.md` Rule 2). `InvalidServiceIdentifierError` formalises shard 14 § 7.2 disposition. `RecordSchemaVersionError` distinguishes "present-but-unparseable-version" from `EntryNotFoundError` ("absent"). `CorruptedRecordError` translates raw stdlib decode/key/value exceptions into the typed taxonomy per `rules/zero-tolerance.md` Rule 3a.

## Cross-references

- specs/trust-vault.md — separate container; Shamir doesn't cover Connection Vault.
- specs/grant-moment.md — credential Grant Moment flow.
- specs/channel-adapters.md — channel credentials.
- specs/foundation-ops.md — service-identifier registry.
- specs/foundation-health-heartbeat.md — anonymous usage_counter aggregate.
- specs/threat-model.md — T-007.

## Test location

- `tests/integration/test_connection_vault_per_platform.py` — macOS/Windows/Linux/iOS/Android keychain round-trip (Tier 2, real OS keychain when available).
- `tests/regression/test_t007_credential_storage_no_sync.py` — T-007 defense; vault never copied to sync surfaces.
- `tests/integration/test_per_principal_isolation.py` — Principal A cannot retrieve Principal B's entry without Grant Moment.
- `tests/integration/test_envelope_scope_enforcement.py` — entry_envelope_scope vs session envelope.
- `tests/integration/test_post_shamir_recovery_repair.py` — Connection Vault empty after Shamir; user re-pairs.
- `tests/regression/test_clipboard_autoclear_30s.py` — credential capture clears clipboard ≤30s.

## Open questions

1. Linux Secret Service availability fallback — what if neither GNOME Keyring nor KWallet present (CLI-only env).
2. `service_identifier` registry vs free-form — strictness of validation; phase-gated.
3. `rotation_policy` enforcement strength — advisory nudge vs hard expiry on overdue.
4. Cross-device migration UX — Phase 02 multi-device pairing requires deliberate re-issue, not transparent sync.
5. Per-credential clearance vs envelope-scope expressiveness — sufficient or needs orthogonal policy.
