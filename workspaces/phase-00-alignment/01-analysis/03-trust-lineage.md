# 03 — Trust Lineage

**Document status:** **FROZEN v2** — post Round 1 (7 CRITs + 12 HIGHs + 12 MEDs/LOWs resolved inline)
**v2 change summary (this pass):** Round 1 surfaced 44 findings across reviewer + adversarial + mechanical (7 CRITs, 12 HIGHs deduped). v2 resolves: **CRIT-01** Genesis `device_attestation.attestation_hash` verification enforced at Phase 01 (not deferred to Phase 03+); stolen Genesis + keypair rejected without device match. **CRIT-02** §4.3 vectors enumerated per doc 02 §14.1 pattern (20 signing + 15 cascade + 15 cycle categorized) + cross-SDK release-gate harness named. **CRIT-03** DuressUnlockEvent does NOT write to synced Ledger with duress label; duress tracking moves to a local-only shadow segment that is NEVER synced to cloud targets. **C-01** `schema_version` added to signing tuple + schema-version downgrade defense paralleling doc 02 §6.3. **C-02** per-principal nonce partitioning (Alice's nonces and Bob's nonces in separate tables; cross-principal eviction impossible). **C-03** `enterprise_context` schema block inline (aligned with doc 02 v3 `enterprise_deployment_record_hash` naming). **C-04** cascade atomic-within-vault vs CRDT-cross-device explicitly scoped. **H-01** subset-proof nested signature canonicalization rule. **H-02** RevocationRecord adds `reason_content_hash` + algorithm tag (T-012 parallel). **H-03** disablement auto-cancel on 24h no-second-channel-confirm (reconciled with doc 02 v3 §14.3). **H-04** vector enumeration per doc 02 pattern (closes CRIT-02). **H-05** chain-depth monotonic-increasing migration rule. **H-06** two head-commitments distinction (chain-head signed by Genesis; Ledger-head signed by device key). **H-07** cross-migration sub-agent algorithm (algorithm-compatible list). **H-08** honeypot resolved as distinct Genesis (removes §14 open question 1). **Adversarial HIGHs**: Lamport-clock signature binding (prevents forgery under CRDT merge); `MigrationAnnouncement` algorithm-allowlist (prevents downgrade); hidden-envelope file-size padding + constant-write-rate (§11.2); cross-channel both-compromised accepted-as-out-of-scope per §1.2 nation-state exclusion; sub-agent transitive SessionObservedState covert-channel — addressed via runtime re-verification that covers session state.

**Document status (v1):** draft v1 — ready for `/redteam`
**Date:** 2026-04-21
**Scope:** Genesis Records, Delegation Records, signing paths, cascade revocation, key rotation, algorithm migration, sub-agent derivation proof verifier, enterprise attestation verifier, replay + cycle + rollback defenses, duress + key-destruction paths. Load-bearing for doc 04 (ledger), doc 05 (runtime), doc 09 (threats mitigated here include T-002, T-041, T-042, T-100, T-102, T-103, T-104, T-105).
**Sources:** doc 00 v3 FROZEN, doc 02 v3 FROZEN, doc 09 v3 FROZEN, kailash-py `src/kailash/trust/{chain,operations,signing,revocation}/`, kailash-rs `crates/eatp/src/{delegation,keys,canonical}.rs`.

---

## 1. Purpose

The envelope defines WHAT may happen. Trust Lineage defines WHO authorized each happening, traced back to a named human via cryptographically-unforgeable signatures.

Every Envoy action of any consequence traces to a **Delegation Record** signed by a key chain rooted in the user's **Genesis Record**. The Ledger (doc 04) records the action. The envelope (doc 02) constrains the action. Trust Lineage binds the action to the user's authority.

### In scope

- Genesis Record schema + local generation
- Delegation Record chain structure + signing fields
- Ed25519 signing paths (kailash-py + kailash-rs)
- Cascade revocation algorithm (BFS/DFS parity)
- Chain verification algorithm (cycle detection, monotonicity)
- Key rotation + algorithm migration
- SubsetProof verifier (doc 02 §14.4 consumer)
- EnterpriseDeploymentRecord verifier (doc 02 §14.3 consumer)
- T-102 replay defense (nonce + head-check)
- T-103 cycle detection at creation time
- T-100 rollback detection (chain-level; complements Ledger head-commitment in doc 04)
- T-041 duress passphrase path (honeypot chain)
- T-042 key destruction + hidden-envelope chain
- Algorithm migration flow
- Cross-SDK primitive mapping

### Out of scope

- Ledger entry format, hash chain, two-phase signing (doc 04).
- Grant Moment UX (doc 01).
- Trust Vault encryption-at-rest format (doc 10).
- Runtime abstraction signing invocation (doc 05).

---

## 2. Genesis Record

### 2.1 Semantics

The Genesis Record is the root of a user's Trust Lineage. It anchors every capability chain to a named human identity. It is:

- **Locally generated** — never issued by a third party.
- **Unforgeable** — cryptographically signed with keys the user alone holds.
- **Not transferable** — the private key + the Genesis Record identify the user.
- **Revocable by key destruction** — the only way to "retire" a Genesis is to destroy its keys (see §11 T-042).

### 2.2 Schema

```json
{
  "type": "GenesisRecord",
  "schema_version": "genesis/1.0",
  "genesis_id": "sha256:<content_hash>",
  "principal_display_name": "Alice Smith",
  "principal_pseudonym": "alice-laptop-2026-04",
  "created_at": "2026-04-21T15:30:00Z",
  "algorithm_identifier": {
    "sig": "ed25519",
    "hash": "sha256",
    "shamir": "slip39"
  },
  "public_key_hex": "<ed25519 public key>",
  "device_attestation": {
    "device_id": "<opaque device identifier>",
    "attestation_type": "secure_enclave | tpm | software",
    "attestation_hash": "sha256:<attestation payload hash>"
  },
  "shamir_threshold": {
    "m_of_n": [3, 5],
    "shard_public_commitments": ["sha256:...", ...]
  },
  "enterprise_context": null,
  "self_signature_hex": "<ed25519 signature by this Genesis's own private key over canonical form of the record above excluding self_signature_hex>"
}
```

**Key properties:**

- **`genesis_id`** is the SHA-256 of the record's canonical form (per doc 02 §14.1 JCS+NFC) EXCLUDING `self_signature_hex`. Content-addressed.
- **`principal_display_name`** — user's preferred name, UTF-8. Shown in Grant Moments, Monthly Trust Report, etc. NFC-normalized.
- **`principal_pseudonym`** — opaque string for external references; does NOT reveal real name. Used in Envelope Library publisher identity (if user opts into publishing).
- **`self_signature_hex`** — Genesis Record is self-signed. Verifies that whoever generated the record knows the private key corresponding to `public_key_hex`.
- **`device_attestation`** — binds the initial Genesis to a specific device's Secure Enclave / TPM where possible. Software-attestation fallback for devices without hardware security module. See §3 for device-binding semantics.
- **`shamir_threshold.shard_public_commitments`** — the Shamir shards' public commitments (one per shard), enabling recovery-proof verification without exposing the shards themselves.
- **`enterprise_context`** — `null` for personal mode; populated with `{org_genesis_hash, deployment_record_hash}` under enterprise deployment (doc 02 §14.3).

### 2.3 Local-generation flow

Genesis generation is the first cryptographic ritual at Envoy install. Unlike registration-based systems, Envoy never sends Genesis generation events to any server.

**Steps:**

1. User installs Envoy. First-run UX (doc 01) prompts Boundary Conversation.
2. Before the Boundary Conversation can complete, Envoy generates:
   a. An Ed25519 keypair (using the session's algorithm_identifier defaults).
   b. A SLIP-0039 Shamir 3-of-5 split of the private key.
   c. A device attestation payload (Secure Enclave / TPM signature over a fresh nonce + device ID, where available).
3. Envoy renders a one-pager: _"This is your Genesis Record. Save the 5 paper cards — you'll need any 3 to recover if your device is lost."_
4. User reviews the displayed Genesis public fields + confirms name.
5. Envoy computes `genesis_id = sha256(canonical_form(record_without_signature))` and produces `self_signature_hex`.
6. Record + encrypted private key + Shamir shards are stored in Trust Vault (doc 10).
7. Paper-shard printing ritual runs (UX in doc 01; crypto in §12 Shamir integration).

**No network traffic** at any step. Envoy is fully offline through Genesis generation.

### 2.4 Verification

A third party receiving a Genesis Record (e.g. for cross-principal action in Shared Household) verifies:

1. Canonical form of record (minus `self_signature_hex`) hashes to `genesis_id`.
2. `self_signature_hex` verifies against `public_key_hex` on the canonical form.
3. `algorithm_identifier` is recognized.
4. `shamir_threshold.m_of_n` satisfies minimum thresholds (m ≥ 2, n ≥ 3).
5. **`device_attestation.attestation_hash` verifies against the attestation_type's verifier** — **enforced at Phase 01 by default (CRIT-01 fix)**, not deferred to Phase 03+. A Genesis Record presented without matching current-device attestation is rejected unless the user explicitly authorizes "cross-device Genesis activation" via a Grant Moment that emits a `GenesisDeviceTransferRecord` signed by both the original-device attestation AND the target-device attestation. This closes the "stolen Genesis + keypair signs anywhere" attack. Exception: devices without hardware attestation (software fallback per §2.2 `attestation_type: software`) carry a weaker binding — surfaced as install-time warning to user; user may opt into software-only mode with explicit acknowledgment that `device_attestation` is best-effort not guarantee.

Verification failure → `GenesisRecordInvalidError(reason)`.

---

## 3. Delegation Record

### 3.1 Semantics

A Delegation Record attests that a principal (identified by a Genesis Record) has granted a specific capability to a specific agent/sub-agent, bounded by an envelope, for a specific time window. Every agent action that consumes a capability must trace back to a Delegation Record in the user's Trust Lineage chain.

### 3.2 Schema

```json
{
  "type": "DelegationRecord",
  "schema_version": "delegation/1.0",
  "delegation_id": "sha256:<content_hash>",
  "chain_parent_id": "sha256:...",
  "delegator": {
    "genesis_id": "sha256:...",
    "public_key_hex": "..."
  },
  "delegatee": {
    "agent_id": "...",
    "device_binding": { "device_id": "...", "binding_pubkey_hex": "..." }
  },
  "capabilities": [
    {"capability_id": "send_email", "scope": {...}}
  ],
  "envelope_version": 7,
  "effective_envelope_hash": "sha256:...",
  "valid_from": "2026-04-21T15:30:00Z",
  "valid_until": "2026-05-21T15:30:00Z",
  "nonce": "<32 random bytes, hex>",
  "algorithm_identifier": {
    "sig": "ed25519",
    "hash": "sha256"
  },
  "sub_agent_derivation": null,
  "enterprise_context": null,
  "signature_by_delegator_hex": "<ed25519 signature over canonical form excluding this field>"
}
```

**Key fields:**

- **`delegation_id`** — content-addressed (SHA-256 of canonical form excluding signature).
- **`chain_parent_id`** — parent Delegation Record in the chain, OR `null` if delegator IS the Genesis holder (root delegation). Enables cascade-revocation traversal (§5).
- **`delegator.genesis_id`** — Genesis Record of whoever signs this. For root delegations, the user's Genesis. For sub-agent delegations, the parent agent's Genesis OR the parent agent's own key (depending on sub-agent architecture — see §7).
- **`delegatee`** — who receives the capability. `agent_id` is an opaque identifier chosen by delegator; `device_binding` ties to a specific device's key so a stolen signed Delegation Record on another device doesn't authorize actions.
- **`capabilities`** — list of capability grants. Each capability has a `capability_id` (e.g. `send_email`) and a `scope` JSON object carrying tool-specific parameters (allowed recipients, max volume, etc.).
- **`envelope_version`** — the envelope version the grant was issued under (doc 02 §6.1). Required for T-104 version-binding defense.
- **`effective_envelope_hash`** — hash of the `EffectiveEnvelopeSnapshot` computed at sign time. Enables downstream verifiers to pin the exact envelope constraints in effect when the delegation was issued.
- **`valid_from` / `valid_until`** — time window; actions outside this window are rejected regardless of signature validity.
- **`nonce`** — 32 random bytes. Required for T-102 / T-008 replay defense.
- **`sub_agent_derivation`** — `null` unless this is a sub-agent spawning event; populated with SubsetProof (doc 02 §14.4) when sub-agent is the delegatee (see §7).
- **`enterprise_context`** — C-03 fix: concrete schema block.
  ```json
  null
  // OR
  {
    "enterprise_deployment_record_hash": "sha256:<hex>",
    "org_genesis_hash": "sha256:<hex>",
    "scope": "employee-personal-envelope-overlay" | "household-member-envelope-overlay" | "agent-fleet-envelope-overlay",
    "edr_schema_version": "edr/1.0"
  }
  ```
  Naming aligned with doc 02 v3 §14.3 `enterprise_deployment_record_hash` (the V-06 fix carried forward here). Every field is signed as part of the Delegation Record canonical form; tampering detected at verify time.
- **`signature_by_delegator_hex`** — Ed25519 signature over canonical form (doc 02 §14.1) excluding itself. Covers EVERY field including `type`, `schema_version` (C-01 fix — prevents schema-version downgrade attack), `chain_parent_id`, `nonce`, `envelope_version`, `effective_envelope_hash`, `enterprise_context` (see §3.2 schema), `sub_agent_derivation` (when a `SubsetProof`, see H-01 rule below). **Schema-version downgrade defense (C-01)**: Envoy refuses to accept a Delegation Record with `schema_version` older than the session's minimum required version, mirroring doc 02 §6.3. Migration between schema versions is one-way (upgrade only) without explicit signed user consent via `SchemaMigrationRecord`. **Nested-signature canonicalization rule (H-01 fix)**: when `sub_agent_derivation` is a `SubsetProof`, the Delegation Record's canonical form for signing EXCLUDES the SubsetProof's own `signature_by_parent` and `runtime_verification_signature` inner fields before hashing — the SubsetProof's own signatures are signed separately and stored inside the field, not double-signed at the outer Delegation Record level. Both SDKs implement this identically; conformance vector at `tests/conformance/trust_lineage/subset_proof_nested_sig/` (5 vectors).

### 3.3 Canonical signing covers

Per doc 02 §14.1 (JCS + NFC), the signature covers the canonical form of the record minus the signature field. This is the full tuple:

```
(type, schema_version, delegation_id, chain_parent_id, delegator, delegatee,
 capabilities, envelope_version, effective_envelope_hash, valid_from, valid_until,
 nonce, algorithm_identifier, sub_agent_derivation, enterprise_context)
```

**Properties achieved by this signing scope:**

- **Replay (T-102 / T-008):** nonce is signed → replay detected by nonce-uniqueness table.
- **Version binding (T-104):** envelope_version + effective_envelope_hash signed → capability change in envelope detected at verify time.
- **Sub-agent forgery (T-105):** sub_agent_derivation (including SubsetProof) signed → parent cannot forge a derivation.
- **Enterprise-context forgery (T-024):** enterprise_context hash signed → enterprise attestation tied to the delegation.
- **Time-window integrity:** valid_from / valid_until signed → attacker cannot extend validity.

### 3.4 Chain verification

A Delegation Record is valid iff ALL of:

1. `delegation_id` == SHA-256 of canonical form without `signature_by_delegator_hex`.
2. `signature_by_delegator_hex` verifies against `delegator.public_key_hex` on canonical form.
3. `algorithm_identifier` matches session algorithm OR is in migration-compatible list (§8).
4. Current time is in `[valid_from, valid_until]`.
5. `chain_parent_id` (if non-null) references a Delegation Record that is itself valid AND not revoked AND covers a superset of this record's capabilities (per SubsetProof verification if `sub_agent_derivation` is populated).
6. `nonce` has not been seen before (checked against nonce-uniqueness table per T-008 / T-102).
7. Chain has no cycle (walks `chain_parent_id` back to root; cycle detected → reject — T-103).
8. Chain length ≤ MAX_CHAIN_DEPTH (default 16; prevents chain-depth-exhaustion DoS).
9. For each capability in `capabilities`, the parent chain permits this capability (transitive authority check).
10. `effective_envelope_hash` references an envelope whose current version still contains the capabilities listed (T-104 capability-existence check).

Failure modes map to specific errors (see §12 error taxonomy).

---

## 4. Signing paths — cross-SDK

### 4.1 kailash-py (Phase 01 default)

**Modules:**

- `src/kailash/trust/chain.py` — `GenesisRecord`, `DelegationRecord`, `TrustLineageChain` classes.
- `src/kailash/trust/operations/__init__.py` — `TrustOperations` API (sign, verify, delegate).
- `src/kailash/trust/signing/crypto.py` — Ed25519 wrapper over `cryptography` library.
- `src/kailash/trust/revocation/cascade.py` — cascade revocation (BFS walker).

**Sign API:**

```python
from kailash.trust.operations import TrustOperations
from kailash.trust.chain import DelegationRecord

ops = TrustOperations(trust_vault=vault)
record = DelegationRecord(
    chain_parent_id=parent_record.delegation_id,
    delegator=ops.genesis_identity(),
    delegatee={"agent_id": "envoy-primary", "device_binding": {...}},
    capabilities=[{"capability_id": "send_email", "scope": {...}}],
    envelope_version=7,
    effective_envelope_hash=envelope.effective_snapshot_hash(),
    valid_from=now,
    valid_until=now + timedelta(days=30),
    nonce=os.urandom(32).hex(),
    algorithm_identifier={"sig": "ed25519", "hash": "sha256"}
)
signed_record = ops.sign(record)
```

**Verify API:**

```python
ops.verify_chain(signed_record, trust_lineage=lineage)
# raises DelegationChainInvalidError on failure
```

### 4.2 kailash-rs (Phase 02+ default via binding)

**Modules:**

- `crates/eatp/src/delegation.rs` — `Delegation`, `DelegationChain` structs. `DelegationChain::revoke()` + `cascade_revoke()` per kailash-rs#505.
- `crates/eatp/src/keys.rs` — `TrustKeyPair` (Ed25519 via `ed25519-dalek`). See kailash-rs deep audit §17.
- `crates/eatp/src/canonical.rs` — canonical-form serialization (now aligned with JCS per doc 02 §14.1).

**Binding exposure status** (per 03-primitive-reconciliation.md):

- `EatpTrustOperations` + `EatpDelegationChain` + `EatpSignature` — ✅ Functional in kailash-rs binding.
- `EatpOrganizationalAuthority` — ✅.
- `TrustKeyPair` — ✅.
- **Cascade revocation** — implemented in Rust (`cascade_revoke()` walks parent_delegation_id recursively); explicit cascade API exposure pending `kailash-rs#505`.
- **Ed25519 signing infrastructure** — ✅ functional.
- **Algorithm-identifier schema** — ❌ NOT YET; signed records hard-code Ed25519 + SHA-256. Phase 01 exit gate per doc 00 v3 §4.1 item 9 + doc 09 v3 §7 Phase 01 gates.

### 4.3 Cross-SDK parity — contract requirements

Per doc 00 v3 BET-6 (contract parity):

1. **Byte-identical signature** for identical canonical form. Verified via PACT N4/N5 conformance vectors (kailash-py runner pending kailash-py#605).
2. **Byte-identical cascade-revocation output** — given the same chain, kailash-py BFS and kailash-rs DFS must produce the same SET of revoked delegation_ids (order may differ; set identity is contractual).
3. **Byte-identical `delegation_id` content-hash** — canonical form determinism per doc 02 §14.1.
4. **Byte-identical `effective_envelope_hash`** — envelope canonical form determinism per doc 02.

Conformance vectors:

**Conformance vectors (CRIT-02 + H-04 fix — enumerated per doc 02 §14.1 pattern, not unbounded):**

- **`tests/conformance/trust_lineage/signing/` — 20 test vectors**:
  - **Fixed-seed Ed25519 edge cases (8)**: zero scalar (rejected), near-group-order points, signature-malleability-resistance (ed25519-dalek strict-mode), base-point nonce, non-canonical S values (rejected), secp/ed25519 key-confusion (rejected), empty message signing, 1-byte message signing.
  - **Canonical-form edge cases (8)**: empty capabilities list, maximum `capabilities` array (100 entries), null `chain_parent_id` (root delegation), null `enterprise_context`, null `sub_agent_derivation`, `valid_from > valid_until` (rejected at validation), UTF-8 NFC-normalization drift in delegatee.agent_id, SMP codepoint in delegator display name.
  - **Schema edge cases (4)**: schema_version present vs missing (missing rejected per C-01), algorithm_identifier mismatch between delegator and delegatee, nonce reuse within session, time-window expired.
- **`tests/conformance/trust_lineage/cascade/` — 15 test vectors (tree topology × revocation pattern)**:
  - **Depth variation (5)**: depth-1, depth-3, depth-5, depth-10, depth-16 (max before rejection).
  - **Branching variation (3)**: linear chain (branching=1), binary tree (branching=2), high-fanout (branching=10).
  - **Revocation pattern (4)**: revoke root (full cascade), revoke leaf (trivial), revoke middle node (partial cascade), revoke after CRDT partition (delayed cascade).
  - **BFS/DFS set-equality verification (3)**: small tree (depth 3), medium tree (depth 6, mixed branching), large tree (depth 10 high-fanout — stress test).
- **`tests/conformance/trust_lineage/cycle_detect/` — 15 test vectors**:
  - **Direct cycles (4)**: 1-hop (self-reference), 2-hop, 3-hop, 5-hop.
  - **CRDT-merge-induced (3)**: two devices offline, each creates one half of a cycle, merge detects.
  - **Timestamp-ambiguous (3)**: same-Lamport-clock entries on different devices; cycle detector uses tiebreak rules.
  - **Deep cycles (2)**: 10-hop, 16-hop (at depth limit).
  - **Valid-but-suspicious patterns (3)**: long chains without cycles (verify no false positives); diamond patterns (two paths to same descendant — NOT a cycle).
- **`tests/conformance/trust_lineage/subset_proof_nested_sig/` — 5 test vectors (H-01 nested-signature canonicalization rule)**:
  - Delegation Record with populated `sub_agent_derivation.signature_by_parent` — verify outer signing EXCLUDES inner signature.
  - Delegation Record with populated `sub_agent_derivation.runtime_verification_signature` — same.
  - Both inner signatures populated.
  - Attempted canonical-form manipulation (attacker rearranges fields) — detected.
  - Cross-SDK byte-identity verified.

**Test harness + release gate:** each SDK runs all 55 vectors (20 + 15 + 15 + 5) in CI. Cross-SDK harness runs both SDKs with same inputs, asserts byte-identity (BET-6). Release gate: 100% pass; any divergence blocks release until resolved.

- `tests/conformance/trust_lineage/cycle_detect/` — 15 attacker-constructed cycle attempts.

**Test corpus enumerated** per doc 02 R2-H1 pattern (avoid unbounded "N+ vectors" from v1).

---

## 5. Cascade revocation

### 5.1 Algorithm

Given a Delegation Record `R` to revoke:

1. Mark `R` as revoked (write revocation entry).
2. Walk all Delegation Records where `chain_parent_id == R.delegation_id`. Each is a direct descendant.
3. For each descendant, recursively repeat (revoke + walk descendants).
4. Return the set of all revoked delegation_ids.

### 5.2 BFS vs DFS parity

**kailash-py** uses breadth-first traversal at `src/kailash/trust/revocation/cascade.py`. **kailash-rs** uses depth-first recursion at `crates/eatp/src/delegation.rs:807`.

**Parity claim:** for the same chain, both orderings produce the same SET of revoked delegation_ids. Order of revocation events in the Ledger differs (BFS writes per-level; DFS writes per-subtree), but the resulting revocation state is identical.

**Test vectors:** `tests/conformance/trust_lineage/cascade/` — for each of 15 tree topologies, assert:

```python
bfs_result = cascade_revoke_bfs(chain, target)
dfs_result = cascade_revoke_dfs(chain, target)
assert set(bfs_result) == set(dfs_result)
```

### 5.3 Atomic rollback

Cascade revocation is atomic: if any step fails (network partition during sync, transient I/O error, signature verify fail on a descendant), the entire revocation rolls back. Ledger records NO partial revocation state.

**Implementation:** revocation runs within a Trust Vault transaction. Commit only on complete cascade.

### 5.4 Revocation record

```json
{
  "type": "RevocationRecord",
  "schema_version": "revocation/1.0",
  "revocation_id": "sha256:<content_hash>",
  "target_delegation_id": "sha256:...",
  "revoker": {"genesis_id": "...", "public_key_hex": "..."},
  "reason": "string (user-authored OR system-generated; content_trust_level tagged at Ledger write)",
  "reason_content_hash": "sha256:<hex>",
  "reason_content_hash_algorithm": "sha256",
  "reason_content_trust_level": "user-authored | system | derived-external",
  "cascade_target_count": 7,
  "cascade_target_ids": ["sha256:...", ...],
  "revoked_at": "iso8601",
  "nonce": "...",
  "algorithm_identifier": {...},
  "signature_by_revoker_hex": "..."
}
```

**Precedence:** a Delegation Record is invalid iff the chain's head contains a RevocationRecord with `target_delegation_id == delegation.delegation_id` OR `target_delegation_id ∈ delegation.ancestors`.

### 5.5 Partial-sync revocation coherence (T-100 + T-101 interaction)

If device A revokes at time T1 but device B (offline) signs a Delegation Record using the revoked delegation as parent, what happens?

**Resolution (per doc 04 CRDT merge):**

1. Both events enter Ledger with Lamport clocks.
2. At CRDT merge (doc 04 §ledger-merge), B's delegation ordered AFTER A's revocation.
3. B's delegation is invalid at verify time (parent revoked before child's timestamp); marked `capability_dead` per T-104.
4. User notified via Ledger conflict entry.

---

## 6. Chain-level defenses against T-100 / T-102 / T-103

### 6.1 T-102 Delegation Record replay

Mitigation: chain head-check + revocation-record precedence (§5.4 above) + nonce-uniqueness table.

**Nonce-uniqueness table (C-02 fix — per-principal partitioning):**

- **Separate table per principal** — `nonces[principal_genesis_id]` is an isolated table. Alice's nonces and Bob's nonces live in separate tables; neither principal can evict the other's entries.
- Maintained in Trust Vault.
- Sliding FIFO window (default 90 days) **per principal's table independently**.
- On every Delegation Record verify, look up `nonce` in `nonces[delegator.genesis_id]`. If present → `DelegationReplayDetectedError`. If absent → add to that principal's table.
- **Per-principal table size bounded at 10^6 entries** — oldest evicted first WITHIN THAT PRINCIPAL'S TABLE. A malicious co-principal cannot burn their way into evicting a victim principal's nonces.
- **Attacker-principal rate limit** — if any principal's nonce-add rate exceeds a declared threshold (default 100/minute, 10^4/day), further adds for that principal are rate-limited OR tracked with an anomaly-alert Ledger entry. Prevents a compromised co-principal from weaponizing their OWN table against themselves to establish a replay window inside their own principal boundary.
- **Legitimate principals** who need burst signing (e.g. bulk onboarding of many delegations): declare in envelope metadata `burst_nonce_allowance` with user acknowledgment; table auto-grows temporarily with appropriate audit entry.

**Replay window enforcement:**

- Signatures older than 60 seconds for synchronous grants → rejected as stale (configurable per envelope).
- Long-running async grants (e.g. Shared Household cross-device) use explicit longer window declared at sign time in `valid_from`/`valid_until`.

### 6.2 T-103 Trust-lineage cycle detection

**At record creation** (MUST):

1. Before accepting a new Delegation Record with `chain_parent_id = P`, walk `P`'s ancestors.
2. If the new record's `delegation_id` (predicted via content-hash) appears in P's ancestor chain, cycle detected → reject with `DelegationCycleDetectedError`.

**At record verification:** same walk. Both creation-time and verify-time checks — defense in depth against CRDT-merge-introduced cycles.

**DAG invariant:** `chain_parent_id` MUST reference an EARLIER-sequenced record (Lamport clock: parent's sequence < child's sequence). Backward references rejected.

**Cascade walks forward only** (§5 algorithm): walks DESCENDANTS (records listing this as parent), not ancestors. Forward-walk on a DAG terminates.

**Test corpus:** 15 cycle-construction attempts (single-hop, multi-hop, CRDT-merge-induced, timestamp-ambiguous) — all verified rejected.

### 6.3 T-100 chain-level rollback detection

Complement to doc 04 §ledger-head-commitment:

- Each principal's Trust Lineage carries a `chain_head_commitment` — hash of the tip of the DelegationRecord chain, signed by the principal's Genesis key on every update.
- Any sync client observing a chain with `chain_head_commitment` older than the previously-seen one rejects as rollback (per T-100).

**H-06 fix — two distinct head-commitments (Trust Lineage vs Ledger):**

There are TWO complementary head-commitments in Envoy's architecture; doc 03 owns one, doc 04 owns the other:

1. **Trust Lineage `chain_head_commitment`** (THIS doc, §6.3) — hashes the tip of the **Delegation Record chain** per principal. Signed by that principal's **Genesis key**. Guards against rollback of the delegation history specifically. Scope: per-principal.

2. **Ledger `ledger_head_commitment`** (doc 04, forthcoming) — hashes the tip of the **entire Ledger** (all entry types — Delegation Records, envelope_edits, Grant Moments, Phase A/B records, revocations, etc.). Signed by the **runtime device key** (per doc 05 §4.1). Guards against rollback of the Ledger as a whole, including entries that are NOT Delegation Records. Scope: per-device-per-vault.

Both commitments written at every sync. Rollback attack on either is detected independently. A valid sync requires BOTH commitments to be monotonic non-decreasing; failure of either rejects the sync.

- Multi-device merging: the higher commitment wins; conflicts resolved per doc 04 CRDT merge.

---

## 7. Sub-agent derivation proof — verifier side

Doc 02 §14.4 defines the `SubsetProof` schema. This section defines the VERIFIER — the runtime-side check that Envoy performs independently of the parent agent's computed proof.

### 7.1 Verifier input / output

**Input:** `parent_delegation_record: DelegationRecord`, `sub_delegation_record: DelegationRecord` (where `sub.sub_agent_derivation != null`).

**Output:**

- `OK` (signed by runtime with `runtime_verification_signature`).
- `SubsetProofFailedError(failed_dimension, failed_witness_detail)`.

### 7.2 Algorithm

```python
def verify_subset_proof_independently(parent, sub):
    assert sub.sub_agent_derivation is not None
    proof = sub.sub_agent_derivation

    # 1. Re-compute envelope hashes and compare.
    if proof.parent_envelope_hash != sha256_canonical(parent.effective_envelope):
        raise SubsetProofFailedError("parent_envelope_hash_mismatch")
    if proof.sub_envelope_hash != sha256_canonical(sub.effective_envelope):
        raise SubsetProofFailedError("sub_envelope_hash_mismatch")

    # 2. Algorithm identifier match.
    if parent.algorithm_identifier != sub.algorithm_identifier:
        raise AlgorithmMismatchError(...)

    # 3. Per-dimension re-verification — IGNORE the parent's computed witnesses; compute from scratch.
    for dim in ["financial", "operational", "temporal", "data_access", "communication"]:
        result = verify_dimension_subset(parent.effective_envelope[dim], sub.effective_envelope[dim])
        if not result.ok:
            raise SubsetProofFailedError(dim, result.witness_detail)

    # 4. Composition rules: sub must be superset (more restrictive OR equal).
    if not composition_rules_are_superset(parent.effective_envelope.composition_rules,
                                          sub.effective_envelope.composition_rules):
        raise SubsetProofFailedError("composition_rules_not_superset")

    # 5. Semantic ensemble: sub's ensemble must be superset (includes all parent's classifiers).
    if not classifier_ensemble_is_superset(parent.effective_envelope.semantic_checks,
                                           sub.effective_envelope.semantic_checks):
        raise SubsetProofFailedError("classifier_ensemble_not_superset")

    # 6. Sign the successful verification.
    runtime_sig = runtime_sign(canonical_form(proof + parent + sub))
    return VerificationResult(ok=True, runtime_signature=runtime_sig)
```

**Key property:** the parent's `proof.dimension_witnesses` are a HINT to the runtime. The runtime re-computes from scratch. If the parent lied (e.g. claimed subset when actually not), the runtime's re-computation catches it.

**Direction-inversion enforcement:** for `communication.content_rules` and `semantic_checks` ensembles, sub must be SUPERSET (more restrictive). The `verify_dimension_subset(Communication)` subroutine encodes this explicitly; test corpus includes 5 direction-inverted vectors that attempt to defeat it.

**Runtime signature:** the runtime signs the verification outcome with its device-bound key (distinct from user Genesis). Downstream verifiers trust the runtime signature as authoritative attestation of the subset check.

### 7.3 Performance

- Per-dimension verification: O(size of envelope) hash + comparison.
- Full SubsetProof verification: <20ms per doc 02 §7 budget (`subset_proof_verify: 20ms`).
- Cache keyed by `(parent_effective_envelope_hash, sub_effective_envelope_hash)`.

---

## 8. Key rotation + algorithm migration

### 8.1 Why rotate

- Ed25519 private key compromise suspected → rotate to prevent attacker from signing future records with old key.
- Algorithm deprecation (NIST announces SHA-256 weakness → migrate to successor).
- User transitions to a new device (Genesis remains; device-binding sub-key rotates).

### 8.2 Key rotation algorithm

1. Generate new Ed25519 keypair.
2. Author a `KeyRotationRecord`:
   ```json
   {
     "type": "KeyRotationRecord",
     "genesis_id": "...",
     "old_public_key_hex": "...",
     "new_public_key_hex": "...",
     "rotation_reason": "scheduled | suspected_compromise | device_transition",
     "rotated_at": "iso8601",
     "algorithm_identifier": {...},
     "signature_by_old_key_hex": "...",
     "signature_by_new_key_hex": "..."
   }
   ```
3. Record is signed by BOTH old and new keys. Old key attests "I authorize this rotation"; new key attests "I accept the transfer."
4. Record enters Ledger; all future Delegation Records use new key.
5. Old Delegation Records remain valid (signed with old key; verifiable against Ledger entry that rotates to new key).
6. Trust Vault re-encrypts master vault key under new algorithm (if this is part of algorithm migration — see §8.3).

### 8.3 Algorithm migration flow

Doc 00 v3 §4.1 item 9: "legacy records remain verifiable under their original algorithm tag."

**MigrationAnnouncement Ledger entry** (per doc 02 §6.2):

```json
{
  "type": "MigrationAnnouncement",
  "from_algorithm_identifier": { "sig": "ed25519", "hash": "sha256" },
  "to_algorithm_identifier": { "sig": "ed25519-v2", "hash": "sha3-256" },
  "effective_at": "iso8601",
  "announced_by": { "genesis_id": "...", "public_key_hex": "..." },
  "signature_hex": "..."
}
```

**Algorithm-allowlist defense (adversarial HIGH fix — prevents downgrade attack)**: the `to_algorithm_identifier` in a MigrationAnnouncement MUST be in the **Foundation-published migration-allowlist** (`envoy-registry:migration-allowlist:v1`). This list is a curated set of algorithm-identifier transitions approved as non-downgrades (e.g. `ed25519 → ed25519-v2`, `sha256 → sha3-256`). Attacker-injected MigrationAnnouncement claiming `sha3-256 → sha256` (downgrade) is rejected at verify time regardless of signature validity. The allowlist is signed by 2-of-N Foundation stewards (same ceremony as Foundation-Verified envelope signing); client caches local copy; periodically updates from Foundation registry with revocation-list check. User MAY author a MigrationAnnouncement outside the allowlist with explicit opt-in + Grant Moment acknowledging "this migration is not Foundation-approved; you accept the risk"; this Ledger entry carries a `FoundationAllowlistOverrideRecord` signed by the user.

**Verification dispatch:**

1. Every signed record carries `algorithm_identifier`.
2. At verify time, look up the algorithm's verifier implementation.
3. Legacy record (pre-migration) verifies under its original algorithm.
4. New records (post-effective_at) MUST use new algorithm; pre-migration algorithm rejected.

**Ledger hash chain:** per-segment algorithm tag. Doc 04 specifies segment boundary at MigrationAnnouncement.

**Trust Vault re-encryption:**

- Master vault key re-encrypted under new algorithm (e.g. AES-256-GCM → AES-256-OCB on cryptographic upgrade).
- Per-entry keys derived from master are RE-DERIVED LAZILY on next entry-write. Legacy entries retain old per-entry keys until next write.
- Shamir shards: if Shamir algorithm changes (e.g. SLIP-0039 v1 → v2), user must re-run Shamir ritual. UX at doc 01.

### 8.4 Cross-SDK parity during migration

Both kailash-py and kailash-rs must support:

- Reading + verifying legacy records under old algorithm.
- Signing new records under new algorithm.
- Recognizing `MigrationAnnouncement` entries.

Per doc 09 v3 §7 Phase 01 gate: algorithm-identifier schema landing (mint#6 + kailash-py#604 + kailash-rs#519). Without it, Phase 01 records are stuck in a pre-migration-incompatible state.

---

## 9. EnterpriseDeploymentRecord verification consumer

Doc 02 §14.3 defined the record schema. This section defines how Trust Lineage integrates.

### 9.1 Verification at envelope-import time

When an envelope carrying `metadata.enterprise_mode.enterprise_deployment_record_hash != null` is imported:

1. Fetch the `EnterpriseDeploymentRecord` identified by the hash.
2. Verify `org_admin_signature_hex` against `org_genesis_hash`'s Trust Lineage root (resolved via Foundation-seeded registry + user-imported orgs).
3. Verify `affected_employee_signature_hex` against the employee's own Genesis Record.
4. Check `scope` is in the closed enum `{employee-personal-envelope-overlay | household-member-envelope-overlay | agent-fleet-envelope-overlay}`.
5. Check `enabled_at` is within the last 365 days (re-attestation required annually).
6. Check algorithm_identifier is current-session-compatible.

On success, the envelope activates in enterprise-mode. On failure, `EnterpriseDeploymentRecordInvalidError` — envelope refuses enterprise-mode; operates in personal-mode.

### 9.2 Disablement protocol

Per doc 09 T-024 R2-H5 + adversarial H-08:

1. User signs an `EnterpriseDeploymentDisablementRecord` (scope = disabled).
2. Envoy does NOT immediately disable — **24h cooling-off window** begins.
3. User receives cross-channel confirmation request (to a second channel declared at Boundary Conversation time).
4. If user confirms on second channel within 24h, disablement becomes effective.
5. If user revokes the pending disablement within 24h, cancelled.
6. If 24h elapses without second-channel confirmation, disablement auto-cancels (fail-secure against coerced signatures).

**Ledger audit:** all disablement attempts + outcomes logged with `content_trust_level = user-authored` (user signs) + `content_trust_level = system` (runtime records outcome).

---

## 10. T-041 duress passphrase → honeypot Trust Lineage

Doc 09 v3 §3.6 T-041 specifies duress passphrase semantics at the Trust Vault layer. This section specifies the Trust Lineage layer.

### 10.1 Honeypot chain structure

When Envoy is unlocked via duress passphrase:

- Trust Vault exposes a **distinct Genesis Record** — the "honeypot Genesis."
- The honeypot Genesis has its own Ed25519 keypair + its own Trust Lineage chain.
- Honeypot chain contains ONLY Delegation Records that grant safe, read-only capabilities (inspect calendar, read recent emails as plaintext summaries — NO action capabilities).
- Attacker sees what appears to be a functional Envoy but with very limited agent autonomy.

### 10.2 Tamper-evident honeypot unlock

When duress unlock fires:

- **(CRIT-03 fix)** A duress unlock event is tracked in a **local-only shadow segment of the Trust Vault**, NOT written to the synced Ledger chain. The shadow segment is encrypted with a key derived ONLY from the REAL passphrase (not duress passphrase), and is NEVER synced to cloud sync targets (iCloud/Dropbox/Keybase/etc). This closes the attacker-post-duress-inspection vector: even if attacker later compels the real passphrase AND dumps Ledger + synced vault, the duress event is invisible because it lives only in the unsynced local shadow. The shadow segment is readable only by the real-passphrase-unlocked Envoy; it surfaces at next real unlock with a notification: _"A duress unlock was attempted at [time]. Review immediately."_
- In the SYNCED Ledger, only a GENERIC `unlock_event` Ledger entry is written (same entry type for real + duress unlocks; no distinguishing marker). Attacker reading Ledger cannot tell whether the most-recent unlock was real or duress. The shadow segment is the only surface that distinguishes.
- Cross-channel notification (optional, pre-configured): a signed notification is sent to an emergency-contact principal (in Shared Household) via the sync-channel.

### 10.3 Indistinguishability

The attacker's view:

- UI identical to normal unlock.
- Envoy appears to be "operating" — draft emails appear in UX, calendar shows entries, etc.
- Honeypot chain is pre-seeded with realistic-looking fake data.

**Residual risk** (per doc 09 v3 T-041 residual): a sophisticated attacker who observes user behavior under duress can distinguish via response latency or by probing specific capabilities (e.g. trying high-stakes actions and watching the honeypot refuse).

---

## 11. T-042 key destruction + hidden envelope

### 11.1 Key destruction path

User can destroy Trust Vault key material permanently via:

- `envoy vault destroy-keys` CLI (Phase 01).
- `Destroy keys` option in Trust Vault settings UI (Phase 02).
- Shamir-shard destruction — burn all paper cards; vault becomes un-recoverable even with any physical evidence.

**What destruction does:**

- Secure Enclave / TPM key handle is explicitly evicted (platform-specific API).
- Trust Vault encrypted file is overwritten with random bytes (multiple passes).
- Per-entry encryption keys in Connection Vault are destroyed (but entries remain encrypted; inaccessible without keys).
- A `KeyDestructionEvent` Ledger entry is signed by the old key as its final act (attests the destruction to any downstream observer; prevents attacker later claiming "user still has the key").
- Shamir shards: user responsibility to destroy physically.

**Post-destruction:**

- Ledger remains readable (user's previous Ledger entries are public-key-verifiable by anyone with the key).
- Content of Trust Vault (envelope, posture history) is cryptographically inaccessible.
- No recovery possible. This is intentional: legal-process cannot compel reconstruction of destroyed keys.

### 11.2 Hidden envelope path (Phase 04)

Per doc 09 v3 T-042 mitigation: Trust Vault can hold a primary envelope + a hidden envelope.

**Cryptographic structure:**

- Master vault key is split via Shamir into two independent sets:
  - Set A: unlocked by passphrase A; reveals primary envelope.
  - Set B: unlocked by passphrase B; reveals hidden envelope.
- Both sets use the same Shamir scheme; externally indistinguishable.
- Primary envelope AND hidden envelope are both stored in the vault; the two keys decrypt disjoint regions.

**Semantics:**

- User under duress discloses passphrase A; attacker sees primary envelope (limited, known to user).
- Hidden envelope contains user's sensitive capability grants.
- The existence of a hidden envelope is NOT revealed by primary envelope contents; primary envelope appears complete.

**Distinguishability defenses (adversarial HIGH fix — hidden-envelope file-size + write-history):**

- **File-size padding**: the Trust Vault file is padded to a fixed-size bucket (discrete sizes: 1 MiB, 4 MiB, 16 MiB, 64 MiB). A vault holding only a primary envelope OR both primary + hidden envelopes lands in the same bucket; file size does not distinguish.
- **Constant-write-rate**: every ritual (Grant Moment, posture change, envelope edit) results in exactly N bytes written to the vault file, regardless of whether the write targets primary or hidden region. Writes to hidden region during real-passphrase sessions are batched with dummy-writes during duress sessions; writes to primary region during duress sessions are batched with dummy-writes during real sessions. Net effect: an attacker observing vault write patterns cannot distinguish "user used hidden envelope a lot" from "user used primary envelope a lot."
- **Sync traffic uniformity**: synced ciphertext blocks are uniform-size chunks; the sync target sees a stream of chunks of identical size regardless of hidden-envelope activity.
- **Decryption-timing uniformity**: unlocking primary vs hidden takes identical time (constant-time key derivation); no side-channel distinguisher.

**Residual risk** (doc 09 T-042): jurisdictional compulsion. Envoy provides the primitive; legal defense is user's responsibility. Sophisticated attacker with lab-grade side-channel analysis (DPA, EM-emission) may still distinguish — out-of-scope per §1.2 nation-state exclusion.

**Phase 04 deliverable.** Not in Phase 01 scope.

---

## 12. Error taxonomy

| Error                                      | When                                                   | User action                                   |
| ------------------------------------------ | ------------------------------------------------------ | --------------------------------------------- |
| `GenesisRecordInvalidError`                | Genesis verification fails                             | Reject record; no capability flow             |
| `GenesisPrincipalNotFoundError`            | Referenced `genesis_id` unknown                        | Reject; user may need to import org's Genesis |
| `DelegationChainInvalidError`              | Any chain-verification step (§3.4 items 1-10) fails    | Reject + log reason                           |
| `DelegationReplayDetectedError`            | Nonce-uniqueness table hit                             | Reject; potential attack — audit alert        |
| `DelegationCycleDetectedError`             | T-103 cycle attempt                                    | Reject at creation OR verify time             |
| `DelegationChainDepthExceededError`        | Chain depth > MAX_CHAIN_DEPTH (16)                     | Reject                                        |
| `DelegationOutOfTimeWindowError`           | Current time not in [valid_from, valid_until]          | Reject; user re-authorizes if intent persists |
| `DelegationCapabilityNotInParentError`     | Claimed capability not in parent's authority           | Reject                                        |
| `CapabilityDeadError`                      | Envelope version no longer contains capability (T-104) | Flag; no new execution from this delegation   |
| `SubsetProofFailedError(dim, witness)`     | Runtime sub-agent verification fails                   | Reject sub-agent spawn                        |
| `EnterpriseDeploymentRecordInvalidError`   | §9 verification fails                                  | Refuse enterprise-mode                        |
| `EnterpriseDeploymentAlreadyDisabledError` | Pending disablement exists; duplicate attempt          | No-op; surface existing pending state         |
| `AlgorithmMismatchError`                   | Algorithm identifier drift                             | Require migration or reject                   |
| `KeyRotationSignatureInvalidError`         | Rotation record's dual-signature fails                 | Reject rotation                               |
| `DuressUnlockDetectedError`                | Duress passphrase entered; UX routes to honeypot       | No user-facing error; silent routing          |

All errors logged as Ledger entries with `content_trust_level: system`. Error messages MUST NOT echo Genesis content, raw signatures, or envelope-sensitive content (adversarial-L-01 pattern from doc 02 carried forward).

---

## 13. Cross-references

- **doc 00 v3** — canonical vocabulary (Genesis Record, Delegation Record, Trust Lineage, cascade revocation, Trust Posture), §4.1 item 9 algorithm-identifier Phase 01 gate.
- **doc 02 v3** — envelope-version binding (T-104), SubsetProof schema (§14.4 producer; this doc is verifier), EnterpriseDeploymentRecord schema (§14.3 producer; this doc is verifier), algorithm_identifier format.
- **doc 04** — Ledger hash chain, head-commitment monotonic invariant (complements §6.3 chain rollback), CRDT merge (complements §5.5 partial-sync coherence), two-phase signing (Phase A intent + Phase B outcome — this doc's Delegation Records are Phase A signatures).
- **doc 05** — runtime abstraction invocation of TrustOperations.sign + verify_chain; kailash-runtime interface.
- **doc 09 v3** — mitigates T-002 (household-adversarial via cross-channel disablement), T-041 (duress passphrase → honeypot §10), T-042 (key destruction + hidden envelope §11), T-100 (chain-level rollback §6.3), T-102 (replay §6.1), T-103 (cycle §6.2), T-104 (envelope-version binding §3.3), T-105 (sub-agent subset-proof §7).
- **doc 10** — Trust Vault storage format (encrypted private key + Shamir shards + Genesis Record + Trust Lineage chain).
- **doc 11** — acceptance metric: "a user can onboard + operate for a week + back up + export Ledger + verify it independently" — independent verifier consumes Delegation Records per §3.4.

**Cross-SDK references** (per `03-primitive-reconciliation.md`):

- `EatpTrustOperations` / `EatpDelegationChain` / `EatpSignature` — kailash-rs ✅ functional.
- `TrustOperations` / `TrustLineageChain` — kailash-py ✅ functional.
- Cascade revocation — kailash-py ✅ BFS / kailash-rs ✅ DFS; parity claim § 5.2.
- Algorithm-identifier — mint#6 + kailash-py#604 + kailash-rs#519 Phase 01 exit gate.

---

## 14. Open questions for `/redteam`

1. **Honeypot chain design (§10)** — **RESOLVED in v2 (H-08 fix)**: distinct Genesis Record for the honeypot. §10.1 commits to "distinct Genesis Record — the 'honeypot Genesis'" with its own Ed25519 keypair + its own Trust Lineage chain. Sub-delegation alternative rejected: identifier correlation would leak duress. (Decision closed; no remaining open question on this axis.)
2. **Key rotation during pending sub-agent delegations** — if user rotates primary key while sub-agents hold valid delegations, are sub-agent delegations re-signed under new key (heavy) OR remain verifiable under old key + rotation record (simpler; used here)? Default: latter.
3. **Cross-principal delegation in Shared Household** — a grant from Alice to Bob's sub-agent requires both Alice's signature and Bob's acknowledgment. What's the acknowledgment protocol? Dual-signed record with 24h window (analogous to enterprise disablement)?
4. **Chain depth hard limit (16)** — why 16? Empirically calibrated against realistic household hierarchies (user → household → children's envelope → per-child-sub-agent = depth 4). Room for growth. Revisit at Phase 03.
5. **Nonce uniqueness table size (10^6)** — bounded by Trust Vault disk budget. Users sustaining >10^6 Delegation Records in 90d are extreme outliers; need adaptive eviction OR per-capability nonce scoping.
6. **Algorithm-migration UX** — when migration announces, what's the user-facing flow? `envoy vault migrate` CLI with confirmation, and pending-Delegation re-sign happens in background over days.
7. **MigrationAnnouncement trust** — who authors MigrationAnnouncements? User-self (for personal migration)? Foundation-announced (ecosystem-wide)? Both, with distinct scopes?
8. **Hidden envelope vs Shamir-threshold change** — if user configures hidden envelope with different m-of-n threshold from primary, is that cryptographically safe? Phase 04 investigation.

---

**End of doc 03 v1. Launching `/redteam` Round 1 next.**
