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

Trust Lineage primitives are implemented UPSTREAM (per § Provenance: kailash-py
`src/kailash/trust/{chain,operations,signing,revocation}/` + kailash-rs
`crates/eatp/src/{delegation,keys,canonical}.rs`); their unit + integration
coverage lives in the upstream SDK test suites. This Phase-01 consumer repo
exercises the trust-lineage CONSUMER surface (genesis seeding, cascade revoke,
two-head commitments) via:

- `tests/tier1/test_trust_store_principal_id.py` — `TrustStoreAdapter` genesis seeding + principal-id lifecycle (Tier 1).
- `tests/tier1/test_trust_cascade_and_shamir.py` — cascade-revocation wrapper + Shamir export/import hooks (T-01-14, Tier 1).
- `tests/tier2/test_trust_cascade_revoke_facade_wiring.py` — cascade-revoke facade wiring through the production runtime (Tier 2).
- `tests/tier2/test_cascade_revocation_orchestrator_wiring.py` + `tests/tier2/test_cascade_revocation_ec8c_real_infra.py` — cascade-revoke orchestration (EC-8c real-infra, Tier 2).
- `tests/tier2/test_shamir_commitments_bound_to_genesis.py` — Shamir commitments bound to Genesis (two-head commitment consumer surface, Tier 2).

## Out of scope (this phase)

The following exercise UPSTREAM EATP trust-lineage primitives (kailash-py
`src/kailash/trust/` + kailash-rs `crates/eatp/`) or Phase-02+/deferred threat
surfaces. Per `rules/spec-accuracy.md` Rule 4, the workstream lives in the
upstream SDK test suites and the algorithm-identifier exit gate
(kailash-py#604 + kailash-rs#519 + mint#6), NOT this Phase-01 consumer repo;
each threat regression is additionally cross-referenced in its OWNING consumer
spec's `## Test location` per `specs/threat-model.md`. Citations move into
`## Test location` above if/as this consumer repo grows its own coverage.

- Upstream lineage-record lifecycle: Genesis self-sig + device-attestation, device-transfer dual-attestation, 10-step per-dimension delegation verifier, BFS/DFS cascade-revoke parity, nonce-per-principal partitioning, key-rotation dual-signed records, algorithm-migration announcement, subset-proof nested canonicalization, two-head commitment monotonicity, key-destruction irreversibility, duress-honeypot distinct-Genesis.
- Upstream threat regressions (owned by the upstream primitive + cross-referenced in the owning consumer spec): T-002, T-024, T-030, T-041, T-042, T-100, T-102, T-103, T-104, T-105.

## Open questions

1. Honeypot chain design — distinct Genesis confirmed (H-08 resolved in source v2); cross-Ledger visibility remains an open design question (deferred past Phase 01).
2. Key rotation frequency — on-demand default; no scheduled rotation.
3. Phase B signed by runtime device key, not delegation key — correct separation per doc 05 F-04.
4. Cross-principal dual-signed Grant Moment window — 24h default.
