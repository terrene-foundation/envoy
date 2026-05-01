# 10 — Data Model

**Document status:** draft v1 — ready for `/redteam`
**Date:** 2026-04-21
**Scope:** Every persisted entity's schema, storage location, retention policy, serialization, and export format. Trust Vault, Connection Vault, Envoy Ledger, Envelope history, Session state, Authorship Score history, Foundation Health Heartbeat client state, ritual state machines, attestation records, runtime device keys, Shamir shards (metadata only).
**Sources:** doc 00 v3, doc 02 v3 (envelope schema), doc 03 v2 (Trust Lineage schemas), doc 09 v3 (T-003 retention + T-012 content-trust-level + T-053 sync threats), doc 01 v1 (ritual state), doc 05 v1 (runtime state).

---

## 1. Storage model

Envoy stores user data in **three physical containers** on the device:

| Container            | Purpose                                                                                             | Encryption                                                            | Sync-eligible                                         | Recovery                         |
| -------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------- |
| **Trust Vault**      | Envoy's own keys, envelope state, posture, Shamir commitments, ritual state, ledger head-commitment | User-derived key + device Secure Enclave                              | Yes (opt-in, ciphertext-only per doc 00 §4.1 item 10) | Shamir 3-of-5                    |
| **Connection Vault** | Third-party credentials (API keys, channel tokens, OAuth refresh)                                   | OS keychain / Secure Enclave wrapper                                  | No (keychain is device-local)                         | Re-entered after Shamir recovery |
| **Ledger**           | Append-only hash-chained record of all grants, actions, refusals, posture changes, ritual events    | Per-entry content-addressed; keys derived from Trust Vault master key | Yes (opt-in)                                          | Via Shamir + sync-target         |

Shadow segments (doc 03 v2 §10.2) are a **fourth, local-only, never-synced** container holding duress-event tracking.

---

## 2. Trust Vault

### 2.1 File format

```text
TrustVault file layout (binary):
[magic bytes: "ENVOY-TV-v1"][schema_version][algorithm_identifier][padding-bucket-size]
[encrypted master key, key-wrapped by Shamir threshold]
[encrypted primary envelope region]
[encrypted posture history]
[encrypted shamir_public_commitments]
[encrypted ritual state]
[encrypted chain_head_commitment]
[encrypted enterprise_deployment_record cache]
[encrypted first-time-action fingerprint cache]
[encrypted hidden envelope region (Phase 04; always-present padded dummy in Phase 01-03)]
[padding to padding-bucket boundary]
[MAC-tag over above]
```

**Padding buckets:** discrete sizes {1 MiB, 4 MiB, 16 MiB, 64 MiB}. Vault always lands in a bucket; file size does not distinguish hidden envelope presence (doc 03 v2 §11.2 defense).

### 2.2 Encryption

- **Outer cipher:** AES-256-GCM (authenticated encryption).
- **Key derivation:** master key from passphrase via Argon2id (configurable params; default m=2^17, t=3, p=1). XOR with device-bound Secure Enclave secret (where available) to bind to device.
- **Per-region keys:** derived from master via HKDF-SHA-256 with region-specific info strings.

### 2.3 Schema per region

- **Envelope region** — `EnvelopeConfig` (doc 02 v3 §2.2) + signed `RoleEnvelope` chain.
- **Posture history** — list of `{posture_level, transition_timestamp, transition_cause, evidence_hash, signed_by}`.
- **Shamir commitments** — `{shard_public_commitments: [...], m_of_n: [3,5], algorithm_identifier: slip39}`. No shard material stored — only public commitments for recovery verification.
- **Ritual state** — active ritual instances per doc 01 §2.1.
- **Chain-head commitment** — per doc 03 v2 §6.3.
- **EnterpriseDeploymentRecord cache** — verified records + their expiry timestamps.
- **First-time-action fingerprints** — SessionObservedState + per-envelope-version tool-call fingerprints (doc 02 §19).

### 2.4 Retention

Trust Vault is retained **as long as the Envoy installation exists**. Key destruction (doc 03 §11.1) is the only disposition. Backups via Shamir are user-responsibility.

### 2.5 Sync

- **Local-only by default** per doc 00 v3 §4.1 item 10.
- **Opt-in cloud sync** via Native Foundation sync node OR third-party (iCloud/Dropbox/Keybase/WebDAV/S3/git). All ciphertext.
- **Sync protocol:** versioned chunks of fixed size (256 KiB); constant-write-rate maintained so sync traffic doesn't distinguish hidden envelope activity (doc 03 v2 §11.2).
- **Integrity:** every sync carries `{chain_head_commitment, ledger_head_commitment}` dual-signed (Genesis + device). Rollback detected per T-100.

---

## 3. Connection Vault

### 3.1 Purpose

Third-party credentials — API keys, channel bot tokens, OAuth refresh tokens — separate from Trust Vault (per doc 00 v3 §4.1 item 12).

### 3.2 Storage

- **macOS:** Keychain access group specific to Envoy binary identifier.
- **Windows:** Credential Manager scoped to Envoy user principal.
- **Linux:** Secret Service (GNOME Keyring / KWallet).
- **Mobile iOS:** Secure Enclave + Keychain Sharing disabled.
- **Mobile Android:** Android Keystore + hardware-backed where available.

### 3.3 Schema (per entry)

```json
{
  "entry_id": "uuid-v7",
  "principal_genesis_id": "sha256:...",
  "credential_type": "api_key | oauth_refresh | channel_bot_token | ...",
  "service_identifier": "anthropic.com | slack.com/team/T123 | ...",
  "entry_envelope_scope": "<EnvelopeConfig fragment declaring what this credential can be used for>",
  "ciphertext": "<OS-keychain-encrypted blob>",
  "created_at": "iso8601",
  "last_used_at": "iso8601",
  "expires_at": "iso8601 | null",
  "usage_counter": int,
  "rotation_policy": "on_demand | scheduled | never"
}
```

### 3.4 Per-principal isolation (Phase 03 Shared Household)

In multi-principal deployment, Connection Vault entries are keyed by `principal_genesis_id`. OS-keychain access attributes restrict each principal's entries to that principal's Envoy runtime process context. Cross-principal access requires Grant Moment.

### 3.5 Recovery

Connection Vault does **NOT** live in Shamir backup. After Shamir recovery on a new device:

- Trust Vault restored from shards.
- Connection Vault is empty.
- User re-authenticates each channel / model provider via fresh Grant Moments.
- Re-authentication uses the recovered Trust Vault's envelope (no re-onboarding of boundaries).

### 3.6 Sync

**Never synced.** Connection Vault is device-local. Rationale: OS keychain cross-device sync is OS-level (iCloud Keychain, etc.); not Envoy's business.

---

## 4. Envoy Ledger

### 4.1 Purpose

Hash-chained append-only record of every grant, action, refusal, posture change, ritual event, envelope edit, revocation. Rooted in EATP Trust Lineage (doc 03).

### 4.2 Physical format

```text
Ledger file layout (plaintext JSON-lines over encrypted transport):
{entry_1}\n
{entry_2}\n
...

Each entry encrypted with per-entry AES-256-GCM key derived from Trust Vault master.
```

### 4.3 Entry envelope

```json
{
  "entry_id": "sha256:<content_hash>",
  "parent_hash": "sha256:<previous_entry_id>",
  "sequence": 4721,
  "lamport_clock": {"device_id": "...", "local_seq": 523},
  "timestamp": "iso8601",
  "type": "<entry type>",
  "content": {<type-specific payload>},
  "content_trust_level": "user-authored | tool-output | channel-message | derived-external | heartbeat | system | sub-agent | llm-authored",
  "description_content_hash": "sha256:<hex>",
  "description_content_hash_algorithm": "sha256",
  "signed_by": "<device_key OR Genesis depending on type>",
  "signature_hex": "<ed25519 sig over canonical form sans signature>",
  "algorithm_identifier": {<...>},
  "schema_version": "ledger-entry/1.0"
}
```

### 4.4 Entry types (canonical set)

- `GenesisRecord` — user's root identity (first entry).
- `RoleEnvelopeCreated` — initial envelope written.
- `envelope_edit` — change to envelope (diff attached; content_trust_level=user-authored).
- `DelegationRecord` — Phase A intent signing record (see doc 04 §two-phase-signing — doc 10 defers to doc 04 for full details).
- `PhaseBRecord` — outcome record linked to Phase A by intent_id.
- `RevocationRecord` — revocation with cascade_target_ids.
- `ReasoningCommit` — LLM-authored record at tool-call decision boundary (doc 02 §16).
- `grant_moment` — record of a Grant Moment's outcome (approve/deny/modify/timeout).
- `posture_change` — posture level transition.
- `unlock_event` — generic unlock (real or duress; indistinguishable).
- `RuntimeAttestation` — runtime startup attestation.
- `KeyRotationRecord` — key rotation (dual-signed).
- `MigrationAnnouncement` — algorithm migration boundary.
- `HaltedByRollback` — in-flight action halted by envelope tightening (doc 02 §6.1 + doc 09 T-104).
- `session_boundary_crossed` — session state reset event.
- `EnterpriseDeploymentRecord` — enterprise attestation activation.
- `EnterpriseDeploymentDisablementRecord` — enterprise attestation deactivation.
- `FoundationHealthHeartbeatConsent` — opt-in signed consent.
- `ritual_completion` — Boundary Conversation / Weekly Posture Review / Monthly Trust Report events.
- `shamir_distribution_checklist_update` — user-ticked distribution progress (Boundary Conversation S8).
- `skill_install` — with CO validator result + force_install flag if any.
- `skill_removal`.
- `channel_connected` / `channel_disconnected`.
- `model_switch` / `runtime_switch`.
- `LedgerConflictEntry` — CRDT merge conflict needing user resolution.
- `ClockSkewEvent` — OS-clock-rollback detection event.
- `system_error` — internal runtime errors.

### 4.5 Hash chain

Every entry's `parent_hash` references the previous entry's `entry_id`. First entry (GenesisRecord) has `parent_hash = "sha256:0"` (genesis anchor). Verification: walk from any entry to GenesisRecord via parent_hash chain; every hash matches.

### 4.6 Retention + GDPR (doc 09 T-003)

- **Default retention:** forever.
- **Tombstone** — user may mark an entry as tombstoned. Tombstoned entries retain `(timestamp, type, signer)` metadata but `content` is replaced with a commitment + MARKER. Chain integrity preserved.
- **Per-entry key destruction** — stronger than tombstone; destroys the per-entry key so content is cryptographically inaccessible.
- **Retention policy** — user declares in envelope: `{grant_moments: 2y, actions: 5y, posture_changes: forever}`. Expired entries auto-tombstone or auto-key-destroy per policy.

### 4.7 Sync

Same sync protocol as Trust Vault. Additional constraint: `ledger_head_commitment` signed by runtime device key on every sync; monotonic non-decreasing (T-100 defense).

---

## 5. Envelope history

Envelope history is a subset of the Ledger — all entries of type `envelope_edit` + `RoleEnvelopeCreated`. Materialized index (for fast replay):

```json
{
  "index_id": "envelope_history_index_v1",
  "entries": [
    {"version": 1, "entry_id": "sha256:...", "timestamp": "...", "diff_summary": "initial"},
    {"version": 2, "entry_id": "sha256:...", "timestamp": "...", "diff_summary": "added 2 authored constraints"},
    ...
  ]
}
```

Index rebuilt on Envoy startup from Ledger replay. Cached in Trust Vault for fast access.

Query: `envoy envelope history --version N` → returns envelope at version N (computed via forward replay from GenesisRecord to version N's entry).

---

## 6. Session state (SessionObservedState)

Per doc 02 §15.

```json
{
  "session_id": "uuid-v7",
  "principal_genesis_id": "sha256:...",
  "started_at": "iso8601",
  "boundary_of_session": "agent-turn-reset | envelope-edit-user-authored | explicit-reset | sub-agent-spawn",
  "observed_data_classifications": [
    {"classification": "tax_info", "first_seen_at": "...", "source_tool_call_intent_id": "..."}
  ],
  "tool_calls_made": [
    {"tool_name": "read_email", "intent_id": "...", "phase_a_record_id": "...", "timestamp": "..."}
  ],
  "cross_domain_flows": [...],
  "first_time_action_fingerprints": ["sha256:...", ...],
  "goal_reconfirmation": {
    "N_tool_calls_since_last": 3,
    "initial_intent_hash": "sha256:...",
    "last_reconfirmation_at": "iso8601 | null"
  },
  "integrity_hash": "sha256:<hash of canonical form>"
}
```

**Integrity:** `integrity_hash` is recomputed at every write; mismatch detected → `CompositionStateCorruptedError`; state zeroed + Ledger entry written.

**Persistence:** Trust Vault. Persisted across Envoy restart if vault is unlocked within lock window.

---

## 7. Authorship Score history

Tracked as a materialized index over Ledger (similar to envelope history):

```json
{
  "principal_genesis_id": "sha256:...",
  "authorship_events": [
    {
      "timestamp": "...",
      "entry_id": "sha256:...",
      "constraint_added": true,
      "novelty_check_passed": true,
      "minimum_impact_passed": true,
      "cumulative_score": 3
    }
  ]
}
```

Queryable via `envoy authorship history`. Rebuilt on startup from Ledger.

---

## 8. Foundation Health Heartbeat client state

```json
{
  "opted_in": true,
  "consent_grant_moment_record_id": "sha256:...",
  "consent_grant_moment_revocation_record_id": null,
  "per_install_random_id": "<rotated quarterly>",
  "random_id_rotation_schedule": {"next_rotation_at": "iso8601"},
  "payload_schema_version": "heartbeat/1.0",
  "last_heartbeat_sent_at": "iso8601 | null",
  "last_heartbeat_accepted_at": "iso8601 | null",
  "flag_counters": {<since-last-heartbeat counters for each flag>}
}
```

Stored in Trust Vault. Counters reset on successful send. Revocation via Grant Moment sets `consent_grant_moment_revocation_record_id`; no further Heartbeats sent.

---

## 9. Runtime device keys

Per doc 05 §4.

```json
{
  "runtime_device_key_id": "sha256:<pubkey>",
  "runtime_device_pubkey_hex": "...",
  "runtime_device_privkey_storage": "secure_enclave | tpm | trust_vault",
  "runtime_family": "kailash-py | kailash-rs-bindings",
  "runtime_version": "3.20.1",
  "binary_hash": "sha256:...",
  "generated_at": "iso8601",
  "rotated_at": "iso8601 | null",
  "previous_key_id": "sha256:... | null"
}
```

Private half in Secure Enclave / TPM where possible; software-fallback in Trust Vault.

---

## 10. Shadow segment (doc 03 v2 §10.2)

Local-only, never-synced container. Stored as a separate file in Envoy's data directory. Encrypted with a key derived from ONLY the real passphrase (not duress).

Contents:

```json
{
  "duress_events": [
    {"detected_at": "iso8601", "unlock_attempt_hash": "sha256:...", "post-unlock_action_summary": "honeypot capabilities served"}
  ],
  "clock_skew_history": [...],
  "internal_runtime_signals": [...]
}
```

**Never in Ledger.** Never in any sync target. Only accessible during real-passphrase sessions.

---

## 11. Cross-references

- **doc 02 v3** — EnvelopeConfig schema (§2.2), SessionObservedState (§15), classifier registry (§14.6) — doc 10 is the persistence consumer.
- **doc 03 v2** — GenesisRecord, DelegationRecord, RevocationRecord, KeyRotationRecord, MigrationAnnouncement, FoundationAllowlistOverrideRecord schemas — doc 10 stores them as Ledger entries.
- **doc 04** — Ledger entry-level canonical format + hash chain + two-phase signing (doc 10 defers to doc 04 for per-entry encryption algorithm).
- **doc 05** — runtime operations (ledger_append, ledger_query) consume doc 10's storage.
- **doc 09 v3** — T-003 retention + GDPR; T-012 content_trust_level; T-040 lost device encryption; T-053 sync ciphertext discipline; T-100 rollback; T-101 fork reconciliation.
- **doc 01** — ritual state machines consume doc 10's Trust Vault storage.

---

## 12. Open questions for `/redteam`

1. Padding bucket sizes (1/4/16/64 MiB) — too coarse? Users with tiny vaults waste space; users with huge vaults jump buckets often.
2. Ledger rebuild from Ledger-replay — expensive for multi-year vaults. Materialized indexes mitigate. At what vault size do we need pagination?
3. Connection Vault OS-keychain — what if OS keychain is compromised? No Envoy-level defense; this is explicitly Phase 01 scope per doc 09 T-040.
4. Shadow segment visibility — power users may still `ls ~/envoy-data/` and notice a shadow file. Use hidden-file semantics + constant-size-across-installs? Covered by doc 03 §11.2 padding principle; verify applies to shadow segment.
5. Heartbeat per-install random ID rotation quarterly — enough? Attacker correlating cross-quarter submissions could potentially link.
6. Ledger entry types (§4.4) — is this set complete? Any missing from doc 09 threat flow?
7. GDPR right-to-erasure via per-entry key destruction — does this satisfy legal bar in all jurisdictions? Requires counsel.

---

**End of doc 10 v1.**
