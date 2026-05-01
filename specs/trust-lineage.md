# trust-lineage

## Purpose

Genesis Records, Delegation Records, signing paths, cascade revocation, key rotation, algorithm migration, sub-agent subset-proof verifier, enterprise-attestation verifier. The cryptographic spine binding every agent action to a named human identity.

## Provenance

- **Source analysis:** `workspaces/phase-00-alignment/01-analysis/03-trust-lineage.md` v2 FROZEN.
- **Threats mitigated:** T-002 household-adversarial, T-024 enterprise-attestation, T-041 duress honeypot, T-042 key destruction + hidden envelope, T-100 chain-level rollback, T-102 replay, T-103 cycle, T-104 envelope-version binding, T-105 sub-agent subset-proof.
- **BETs tested:** BET-6 contract parity (signing byte-identity), BET-9a upstream EATP primitives.
- **Cross-SDK:** kailash-py `src/kailash/trust/{chain,operations,signing,revocation}/` ✅; kailash-rs `crates/eatp/src/{delegation,keys,canonical}.rs` ✅; algorithm-identifier schema kailash-py#604 + kailash-rs#519 + mint#6 (Phase 01 exit gate).

## Schema

### GenesisRecord

```json
{
  "type": "GenesisRecord", "schema_version": "genesis/1.0",
  "genesis_id": "sha256:<content_hash>",
  "principal_display_name": <str>, "principal_pseudonym": <str>,
  "created_at": <iso8601>,
  "algorithm_identifier": {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"},
  "public_key_hex": <str>,
  "device_attestation": {"device_id": <str>, "attestation_type": "secure_enclave|tpm|software", "attestation_hash": <sha256>},
  "shamir_threshold": {"m_of_n": [3,5], "shard_public_commitments": [<algo:hash>]},
  "enterprise_context": null | {...},
  "self_signature_hex": <str>
}
```

**Device-attestation enforcement (CRIT-01 fix):** verified at Phase 01 (NOT deferred to Phase 03+). Stolen Genesis + keypair rejected without matching current-device attestation. Exception: explicit cross-device activation via `GenesisDeviceTransferRecord` signed by both old + new device attestations.

### DelegationRecord

```json
{
  "type": "DelegationRecord", "schema_version": "delegation/1.0",
  "delegation_id": "sha256:<content_hash>",
  "chain_parent_id": "sha256:... | null",
  "delegator": {"genesis_id": <sha256>, "public_key_hex": <str>},
  "delegatee": {"agent_id": <str>, "device_binding": {"device_id": <str>, "binding_pubkey_hex": <str>}},
  "capabilities": [{"capability_id": <str>, "scope": {...}}],
  "envelope_version": <int>,
  "effective_envelope_hash": <sha256>,
  "valid_from": <iso8601>, "valid_until": <iso8601>,
  "nonce": <hex>,
  "algorithm_identifier": {...},
  "sub_agent_derivation": null | SubsetProof,
  "enterprise_context": null | {"enterprise_deployment_record_hash": <sha256>, "org_genesis_hash": <sha256>, "scope": <closed_enum>, "edr_schema_version": "edr/1.0"},
  "signature_by_delegator_hex": <str>
}
```

**Signing scope:** `signature_by_delegator_hex` covers canonical form (JCS + NFC per specs/envelope-model.md §Canonical JSON) of record EXCLUDING `signature_by_delegator_hex` itself; covers `type`, `schema_version` (C-01 fix), `chain_parent_id`, `nonce`, `envelope_version`, `effective_envelope_hash`, `enterprise_context`, `sub_agent_derivation`. When `sub_agent_derivation = SubsetProof`, outer canonicalization EXCLUDES SubsetProof's own inner signatures (H-01 nested-signature rule).

### RevocationRecord

```json
{
  "type": "RevocationRecord", "schema_version": "revocation/1.0",
  "revocation_id": <sha256>, "target_delegation_id": <sha256>,
  "revoker": {"genesis_id": <sha256>, "public_key_hex": <str>},
  "reason": <str>, "reason_content_hash": <sha256>, "reason_content_hash_algorithm": "sha256",
  "reason_content_trust_level": "user-authored | system | derived-external",
  "cascade_target_count": <int>, "cascade_target_ids": [<sha256>],
  "revoked_at": <iso8601>, "nonce": <hex>,
  "algorithm_identifier": {...},
  "signature_by_revoker_hex": <str>
}
```

## Algorithms

### Chain verification (§3.4 source)

10 verification steps: delegation_id hash, signature verify, algorithm_identifier match, time window, chain_parent_id validity + non-revoked + capability-superset, nonce-uniqueness (per-principal table per C-02), cycle-free, depth ≤ 16, transitive authority, capability-existence at current envelope version.

### Cascade revocation (§5 source)

- kailash-py: BFS walker at `src/kailash/trust/revocation/cascade.py`.
- kailash-rs: DFS recursion at `crates/eatp/src/delegation.rs:807`.
- BFS/DFS parity: return SETs are equal (contractual); Ledger ordering may differ.
- Atomic within a single Trust Vault transaction; cross-device divergence handled by Ledger CRDT merge (see specs/ledger-merge.md).

### Cycle detection (§6.2 source, T-103)

- At record creation: walk ancestors for cycle detection before accepting.
- DAG invariant: `chain_parent_id` references earlier-sequenced record.
- Forward-walk cascade only; backward walk explicitly forbidden.
- 15-vector test corpus for cycle construction attempts.

### Nonce per-principal partitioning (§6.1 C-02 fix)

- `nonces[principal_genesis_id]` — separate table per principal.
- Sliding 90-day FIFO, 10^6 entries per principal's table.
- Malicious co-principal cannot evict victim's nonces (cross-principal isolation).
- Per-principal rate limit: 100/min, 10^4/day; beyond = anomaly alert.

### Algorithm migration

- `MigrationAnnouncement` Ledger entry marks transition.
- `to_algorithm_identifier` MUST be in Foundation-signed migration-allowlist (`envoy-registry:migration-allowlist:v1`); prevents downgrade attack.
- Legacy records verifiable under original algorithm.
- Trust Vault re-encrypts master under new algorithm; per-entry keys re-derived lazily.
- Shamir re-ritual required if SLIP-0039 scheme changes.

### Key rotation

Canonical Ledger entry type: `KeyRotationRecord` with `key_scope: "runtime_device" | "genesis" | "per_entry" | "master"` (V-04 reconciliation per round-1-specs-comprehensive.md). Used for all key rotations across runtime, genesis, and data-at-rest keys.

```json
{
  "type": "KeyRotationRecord",
  "schema_version": "key-rotation/1.0",
  "key_scope": "runtime_device | genesis | per_entry | master",
  "old_pubkey_hex": "<str>",
  "new_pubkey_hex": "<str>",
  "reason": "<str>",
  "reason_content_hash": "sha256:...",
  "reason_content_trust_level": "user-authored | system",
  "old_key_signature_hex": "<ed25519>",
  "new_key_signature_hex": "<ed25519>",
  "genesis_cosignature_hex": "<ed25519>",
  "nonce": "<hex>",
  "algorithm_identifier": {...}
}
```

**Dual-signed (old + new)** prevents self-rotation under key compromise; **Genesis co-signature** (F-02 doc 05 fix) prevents compromised runtime from rotating itself without user co-sign. See specs/runtime-abstraction.md §Runtime device key for runtime-specific rotation semantics.

### Duress honeypot (§10 source, T-041)

- Honeypot: **distinct Genesis Record** (H-08 resolved — not sub-delegation).
- DuressUnlockEvent → local-only shadow segment (NEVER synced; CRIT-03 fix).
- Generic `unlock_event` written to synced Ledger (no duress label).
- Indistinguishable from real unlock at Ledger level.

### Key destruction (§11, T-042)

- Secure Enclave / TPM key eviction via platform-specific API.
- `KeyDestructionEvent` signed by old key as final act.
- Trust Vault file overwritten; Connection Vault entries inaccessible.
- Ledger remains publicly verifiable; content encryption keys destroyed.

### Hidden envelope (§11.2, Phase 04)

- Two passphrases, two Shamir sets.
- File-size padding to discrete buckets.
- Constant-write-rate to prevent distinguishability.
- Sync traffic uniformity; decryption-timing uniformity.

### Two head-commitments (§6.3 H-06 fix)

- **Trust Lineage chain-head** signed by Genesis key; pins DelegationRecord chain tip.
- **Ledger head** signed by runtime device key (doc 05 §4.1); pins Ledger tip.
- Both monotonic non-decreasing; both checked at every sync.

## Error taxonomy

`GenesisRecordInvalidError`, `GenesisPrincipalNotFoundError`, `DelegationChainInvalidError`, `DelegationReplayDetectedError`, `DelegationCycleDetectedError`, `DelegationChainDepthExceededError`, `DelegationOutOfTimeWindowError`, `DelegationCapabilityNotInParentError`, `CapabilityDeadError`, `SubsetProofFailedError`, `EnterpriseDeploymentRecordInvalidError`, `EnterpriseDeploymentAlreadyDisabledError`, `AlgorithmMismatchError`, `KeyRotationSignatureInvalidError`, `DuressUnlockDetectedError` (internal runtime signal, NEVER user-surfaced).

## Cross-references

- **specs/envelope-model.md** — envelope_version binding, RoleEnvelope/TaskEnvelope consumers.
- **specs/sub-agent-delegation.md** — SubsetProof verifier.
- **specs/enterprise-deployment.md** — EnterpriseDeploymentRecord verifier.
- **specs/ledger.md** — Ledger-level head-commitment, CRDT merge interaction.
- **specs/shamir-recovery.md** — shard_public_commitments + recovery flow.
- **specs/runtime-abstraction.md** — `trust_sign()`, `trust_verify_chain()`, `trust_cascade_revoke()`.
- **specs/trust-vault.md** — private key storage + shadow segment.
- **specs/threat-model.md** — T-002/T-041/T-042/T-100/T-102/T-103/T-104/T-105.

## Conformance vectors

- **Signing** — 20 vectors (Ed25519 edge cases + canonical-form edge cases + schema edge cases).
- **Cascade** — 15 vectors (depth × branching × revocation pattern + BFS/DFS set equality).
- **Cycle detection** — 15 vectors (direct + CRDT-merge-induced + timestamp-ambiguous + deep + valid-but-suspicious).
- **Subset-proof nested signature** — 5 vectors (H-01 canonicalization rule).

## Test location

- `tests/integration/test_genesis_record_lifecycle.py` — Genesis self-sig, device-attestation enforcement at Phase 01, public_key_hex round-trip (Tier 2).
- `tests/integration/test_genesis_device_transfer_record.py` — old + new device dual-attestation; cross-device activation flow.
- `tests/integration/test_delegation_record_per_dimension_verifier.py` — 10-step chain verification across delegation_id hash, signature, algorithm_identifier, time window, chain_parent_id non-revoked, capability-superset, nonce uniqueness, cycle-free, depth ≤ 16, transitive authority.
- `tests/integration/test_cascade_revoke_bfs_dfs_parity.py` — BFS (kailash-py) + DFS (kailash-rs) return identical SETs; Ledger ordering may differ.
- `tests/integration/test_nonce_per_principal_partitioning.py` — sliding 90-day FIFO, 10^6 entries per principal; cross-principal isolation.
- `tests/integration/test_key_rotation_record_dual_signed.py` — old + new key signatures + Genesis cosignature; `key_scope` in {runtime_device, genesis, per_entry, master}.
- `tests/integration/test_algorithm_migration_announcement.py` — `MigrationAnnouncement` + `to_algorithm_identifier` in Foundation migration-allowlist; legacy records verifiable under original algorithm.
- `tests/integration/test_duress_honeypot_distinct_genesis.py` — duress unlock writes to local-only shadow segment; synced Ledger sees only generic `unlock_event`.
- `tests/integration/test_key_destruction_event_irreversible.py` — Secure Enclave / TPM eviction + `KeyDestructionEvent` final-act signing; Trust Vault overwrite.
- `tests/integration/test_two_head_commitments.py` — Trust Lineage chain-head (Genesis-signed) + Ledger head (runtime-device-key-signed); both monotonic at sync.
- `tests/integration/test_subset_proof_nested_canonicalization.py` — H-01 nested-signature rule: outer `signature_by_delegator_hex` excludes SubsetProof's own inner signatures.
- `tests/regression/test_t002_household_adversarial.py` — T-002 household-adversarial vault read defense.
- `tests/regression/test_t024_enterprise_attestation.py` — T-024 verifier (consumer of specs/enterprise-deployment.md).
- `tests/regression/test_t030_compromised_model_provider.py` — T-030 model-provider compromise propagation defense.
- `tests/regression/test_t030_response_key_rotation_migration.py` — key-rotation + algorithm-migration response under T-030 compromised-model-provider scenarios (cross-spec with specs/model-adapter.md).
- `tests/regression/test_t041_duress_honeypot.py` — T-041 distinct-Genesis honeypot indistinguishability at Ledger level.
- `tests/regression/test_t042_key_destruction_hidden_envelope.py` — T-042 key destruction + hidden-envelope-bucket padding.
- `tests/regression/test_t100_chain_level_rollback.py` — T-100 chain-head monotonic non-decreasing.
- `tests/regression/test_t102_replay_defense.py` — T-102 nonce-uniqueness across CRDT merge.
- `tests/regression/test_t103_cycle_construction.py` — T-103 15-vector cycle-construction corpus.
- `tests/regression/test_t104_envelope_version_binding.py` — T-104 `envelope_version` + `effective_envelope_hash` binding.
- `tests/regression/test_t105_sub_agent_subset_proof.py` — T-105 SubsetProof verifier (consumer of specs/sub-agent-delegation.md).

## Open questions

1. Honeypot chain design — distinct Genesis confirmed (H-08 resolved in source v2); cross-Ledger visibility TBD.
2. Key rotation frequency — on-demand default; no scheduled rotation.
3. Phase B signed by runtime device key, not delegation key — correct separation per doc 05 F-04.
4. Cross-principal dual-signed Grant Moment window — 24h default.
