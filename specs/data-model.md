# data-model

## Purpose

Every persisted entity's schema + storage location + retention + serialization + export format.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/10-data-model.md v1`.
- **Threats mitigated:** T-003 retention, T-012 content_trust_level, T-040 lost device, T-053 sync compromise.
- **BETs tested:** BET-3 sovereignty (local-first), BET-9b binding compatibility.

## Four physical containers

1. **Trust Vault** — Envoy's keys + envelope + posture + Shamir commitments + ritual state + Ledger head + Heartbeat client state + `SessionObservedState` (specs/session-state.md). Encrypted AES-256-GCM; master key from Argon2id passphrase + Secure Enclave XOR. Opt-in sync (ciphertext); `SessionObservedState` NOT synced (session-scoped, per-device).
2. **Connection Vault** — third-party credentials in OS keychain. Per-principal isolated (Phase 03). NEVER synced.
3. **Ledger** — hash-chained append-only; per-entry encryption; opt-in sync.
4. **Shadow segment** — local-only, never-synced. `DuressUnlockEvent`s, clock-skew history, runtime internal signals. Encrypted with real-passphrase-only key. Referenced by specs/trust-vault.md §Duress support + specs/trust-lineage.md §Duress honeypot.

The `_index.md` description "Trust Vault + Connection Vault + Ledger + shadow segment" enumerates these four in the same order — capitalization follows the canonical names above (Trust Vault / Connection Vault / Ledger are proper nouns; "shadow segment" is a common-noun region designation).

**Session-boundary semantics:** session-scoped state (first-time-action fingerprints, goal-reconfirmation counter, pending Phase-A orphans) lives in Trust Vault region `SessionObservedState` per specs/session-state.md §Persistence. Cache reset on session boundary emits `session_boundary_crossed` Ledger entry.

## Trust Vault regions

Envelope / Posture history / Shamir commitments / Ritual state / Chain head commitment / Enterprise deployment cache / First-time-action fingerprints / Hidden envelope region (Phase 04 + padded dummy Phase 01–03).

Padding buckets: 1 MiB, 4 MiB, 16 MiB, 64 MiB — vault lands in a bucket; file size does not distinguish hidden-envelope presence.

## Connection Vault per-entry schema

`{entry_id, principal_genesis_id, credential_type, service_identifier, entry_envelope_scope, ciphertext, created_at, last_used_at, expires_at, usage_counter, rotation_policy}`.

Platforms: macOS Keychain / Windows Credential Manager / Linux Secret Service / iOS Secure Enclave / Android Keystore.

## Ledger materialized indexes

Rebuilt from Ledger replay at startup; cached in Trust Vault:

- Envelope history (version → entry_id).
- Authorship Score history (cumulative events).
- Heartbeat counters (since-last-send).

## Retention

- Trust Vault: forever (until key destruction).
- Connection Vault: until user removes OR credential expires.
- Ledger: user-declared policy per envelope; tombstone + per-entry key destruction supported.
- Shadow segment: forever locally; never syncs.

## Sync

- Trust Vault + Ledger: opt-in via native Foundation node + third-party (iCloud/Dropbox/Keybase/WebDAV/S3/git).
- Protocol: versioned 256 KiB chunks; constant-write-rate; dual head-commitments.
- Connection Vault: NEVER.
- Shadow segment: NEVER.

## Export

`envoy vault export` (Shamir-protected); `envoy ledger export --format json|pdf`.

## Error taxonomy

| Error                            | Trigger                                                                           | User action                                                                 | Retry                  |
| -------------------------------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------- |
| `ContainerNotInitializedError`   | Read/write attempt against a container before its initial provisioning ritual ran | Run the appropriate `envoy init` ritual (vault / connection / ledger)       | Manual after init      |
| `EncryptionContextMismatchError` | Per-region HKDF info-string does not match the stored encrypted region            | Halt; surface as potential corruption or version skew; user runs audit      | Never (manual recover) |
| `ShadowSegmentCorruptError`      | Shadow segment MAC tag fails verification under real-passphrase-only key          | Treat as hostile-tamper or disk corruption; segment unrecoverable by design | Never                  |
| `MigrationRequiredError`         | Container schema version older than current binary's supported lower bound        | Run `envoy migrate <container>`; verify backup before                       | Manual after migrate   |
| `PaddingBucketOverflowError`     | Trust Vault write exceeds the largest padding bucket (64 MiB) before next sync    | Vault prune ritual; user reviews stale ritual-state regions                 | Manual after prune     |
| `SyncTransportUnavailableError`  | Foundation sync node + every configured third-party fallback unreachable          | Local-only mode continues; alert on prolonged unavailability                | Auto with backoff      |
| `RetentionPolicyViolationError`  | Ledger query against an entry past user-declared retention boundary               | Surface tombstone metadata only; content keys destroyed per policy          | Never                  |

All errors persisted to Ledger as `system_error` per specs/ledger.md §System error with `record_id` redacted via `format_record_id_for_event` per specs/classification-policy.md.

## Cross-references

All specs. data-model.md is the persistence layer for every primitive.

- specs/trust-vault.md — Trust Vault region layout + encryption.
- specs/connection-vault.md — per-entry schema + platform keychains.
- specs/ledger.md — hash-chained append-only + retention.
- specs/session-state.md — `SessionObservedState` region.
- specs/trust-lineage.md — duress honeypot + shadow segment consumer.
- specs/threat-model.md — T-003, T-012, T-040, T-053.
- specs/classification-policy.md — `format_record_id_for_event` redaction at audit-row write.

## Test location

- `tests/integration/test_trust_vault_region_layout.py` — region encryption + HKDF info-string isolation (Tier 2).
- `tests/integration/test_connection_vault_per_principal.py` — per-principal isolation across macOS Keychain / Windows Credential Manager / Linux Secret Service (Tier 2 where keychain available, Tier 1 mock fallback for CI).
- `tests/integration/test_ledger_materialized_index_rebuild.py` — rebuild from Ledger replay at startup (Tier 2).
- `tests/integration/test_shadow_segment_real_only_key.py` — duress passphrase cannot read shadow segment.
- `tests/integration/test_padding_bucket_size_indistinguishable.py` — file size in {1, 4, 16, 64} MiB regardless of hidden-envelope presence.
- `tests/integration/test_sync_chunked_write_rate.py` — 256 KiB versioned chunks + constant-write-rate.
- `tests/regression/test_t002_household_adversarial.py` — T-002 household-adversarial vault read.
- `tests/regression/test_t018_visible_secret.py` — T-018 visible-secret rendering across data-bearing entries.
- `tests/regression/test_t040_lost_device.py` — T-040 lost-device recovery via Shamir.
- `tests/regression/test_t053_sync_compromise.py` — T-053 sync target tampering detected at head commitment.

## Open questions

1. Materialized-index cache TTL — should the rebuild-on-startup model retain a warm cache across runs, and if so, where (Trust Vault region vs separate cache file)?
2. Connection Vault rotation policy — per-entry `rotation_policy` semantics: hard-expiry (refuse), warn-expiry (Grant Moment), or both?
3. Cross-platform shadow segment binding — Linux Secret Service does not always provide secure-enclave-equivalent binding; is the real-passphrase-only encryption sufficient on those platforms, or does shadow segment require degraded-mode tagging?
4. Tombstone-vs-key-destruction policy default — should Ledger default retention shift from "forever" to a tombstone-after-N-years policy, and how does that interact with EATP audit obligations?
5. Padding-bucket promotion strategy — when does a 4 MiB vault promote to 16 MiB, and should promotion emit a Ledger entry (potential side-channel) or remain silent?
