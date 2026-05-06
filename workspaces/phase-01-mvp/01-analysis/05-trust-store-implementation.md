# 05 — Trust Store + Lineage — Implementation Analysis

**Document role:** Phase 01 implementation analysis for the Trust Store + Trust Lineage primitive (shard 5 of 25 of the /analyze plan, per `01-shard-plan.md` §2). Identifies the verified `kailash-py` provider modules, the Envoy-new-code surface that wraps them, and the integration points to neighboring primitives. Cites Phase 00 + Phase 01 frozen artifacts; never paraphrases.

**Date:** 2026-05-03 (shard 5 of /analyze).
**Status:** DRAFT — load-bearing for shards 7 (Independent Verifier), 9 (Authorship Score), 10 (Grant Moment), 15 (Shamir Recovery), 16 (Channel Adapters).
**Capacity check:** 1 primitive, 2 source specs (`trust-vault.md`, `trust-lineage.md`), 3 cross-spec touch-points (`posture-ladder.md`, `authorship-score.md`, `shamir-recovery.md`), ~6 invariants tracked. Within `rules/autonomous-execution.md` § Per-Session Capacity Budget.

---

## 1. Source spec citation

The Trust Store + Lineage primitive is defined by two frozen Phase 00 specs. Phase 01 implementation MUST NOT re-derive these — per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, the shard's question is "given this spec is frozen, how do I wire `kailash-py` to deliver it?" not "is the spec right?".

- **Trust Vault (encrypted local storage)** — `specs/trust-vault.md` § Purpose + § File format + § Encryption + § Memory hygiene + § Duress support + § Key destruction + § Error taxonomy. Key facts cited verbatim:
  - § File format: "Binary with magic-bytes header, algorithm_identifier, padding-bucket size, encrypted master key (Shamir-wrapped), encrypted regions (envelope / posture / Shamir commitments / ritual state / chain head / enterprise cache / first-time fingerprints / hidden envelope), padding, MAC tag."
  - § Encryption: "Outer: AES-256-GCM. Master key: Argon2id from passphrase (m=2^17, t=3, p=1) XOR with Secure Enclave/TPM-bound secret. Per-region keys: HKDF-SHA-256 with region info-strings."
  - § Memory hygiene (T-071): "Auto-lock after 15min idle (configurable). Lock-during-idle clears all in-memory secrets."
  - § Cross-references: links to `trust-lineage.md`, `ledger.md`, `connection-vault.md`, `shamir-recovery.md`, `data-model.md`, `threat-model.md`.
- **Trust Lineage (Genesis + Delegation + Cascade)** — `specs/trust-lineage.md` § Purpose + § Schema (GenesisRecord, DelegationRecord, RevocationRecord) + § Algorithms (Chain verification, Cascade revocation, Cycle detection, Nonce per-principal partitioning, Algorithm migration, Key rotation) + § Error taxonomy. Key facts cited verbatim:
  - § Provenance / Cross-SDK: "kailash-py `src/kailash/trust/{chain,operations,signing,revocation}/` ✅; kailash-rs `crates/eatp/src/{delegation,keys,canonical}.rs` ✅; algorithm-identifier schema kailash-py#604 + kailash-rs#519 + mint#6 (Phase 01 exit gate)."
  - § Algorithms — Cascade revocation: "kailash-py: BFS walker at `src/kailash/trust/revocation/cascade.py`. kailash-rs: DFS recursion at `crates/eatp/src/delegation.rs:807`. BFS/DFS parity: return SETs are equal (contractual); Ledger ordering may differ."
  - § Algorithms — Nonce per-principal partitioning (§6.1 C-02 fix): "`nonces[principal_genesis_id]` — separate table per principal. Sliding 90-day FIFO, 10^6 entries per principal's table. Malicious co-principal cannot evict victim's nonces (cross-principal isolation)."
  - § Algorithms — Two head-commitments (§6.3 H-06 fix): "Trust Lineage chain-head signed by Genesis key; pins DelegationRecord chain tip. Ledger head signed by runtime device key (doc 05 §4.1); pins Ledger tip. Both monotonic non-decreasing; both checked at every sync."
- **Posture-ladder integration** — `specs/posture-ladder.md` § Provenance: "mirrors kailash-py `PostureStore` / `PostureEvidence` / `SQLitePostureStore` primitives (filed mint#4 + kailash-py#597 for spec parity)." Posture state lives adjacent to Trust Lineage and is read by the Trust store adapter.
- **Authorship-score integration** — `specs/authorship-score.md` § Re-derivation from the Ledger: re-derives from Ledger slice; Trust store adapter exposes the Genesis-signed posture-change Ledger entries that authorship-score's posture-ratchet gate consumes.
- **Shamir recovery hooks** — `specs/shamir-recovery.md` § Algorithm + § Default threshold + § Recovery flow: "SLIP-0039 via audited libraries: ... Python `slip39` / `python-shamir-mnemonic`." Per shard scope, only the recovery-ritual hooks on Trust store are in scope here; the full Shamir primitive is shard 15.

---

## 2. Verified provider citation (post-freshness-gate)

Per `03-kailash-py-mvp-readiness.md` § 5 (verification protocol) + § 3 row 2 (Trust store + lineage), the Phase 00 survey baseline (`02-kailash-py-survey.md` items 17, 18) was extended by the 2026-05-03 freshness gate. Verification was executed for this shard:

### 2.1 Closed-issue references

| Phase 00 ISS | GH#                               | Closed               | PR/landed-feature                                                                                                  | Verified location                                                                                                                                                            |
| ------------ | --------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ISS-32       | terrene-foundation/kailash-py#604 | 2026-04-25T14:43:55Z | "Algorithm-identifier schema implementation" — `AlgorithmIdentifier` dataclass scaffold (mint ISS-31 forward-path) | `~/repos/loom/kailash-py/src/kailash/trust/signing/algorithm_id.py` lines 1–162 — exports `AlgorithmIdentifier`, `coerce_algorithm_id`, `ALGORITHM_DEFAULT="ed25519+sha256"` |
| ISS-12       | terrene-foundation/kailash-py#597 | 2026-04-24T17:02:09Z | "Confirm Phase-13 posture/verification type bundle completeness" — canonical 5-posture set + `SQLitePostureStore`  | `~/repos/loom/kailash-py/src/kailash/trust/posture/posture_store.py` lines 1–80; exports `SQLitePostureStore`, `validate_agent_id`                                           |
| ISS-05       | terrene-foundation/kailash-py#595 | 2026-04-25           | Cascade-revocation docstring cross-reference (no behavior change)                                                  | `~/repos/loom/kailash-py/src/kailash/trust/revocation/cascade.py` lines 1–46 (docstring asserts BFS/DFS set equality with kailash-rs)                                        |

### 2.2 Verified module + symbol export

Confirmed by reading absolute-path source under `~/repos/loom/kailash-py/src/kailash/`:

- **`kailash.trust.chain`** (Phase 00 cited `:122-300+` and `:400-600`) — verified at `~/repos/loom/kailash-py/src/kailash/trust/chain.py`:
  - `class GenesisRecord` at line 122
  - `class DelegationRecord` at line 222
  - `class ChainConstraintEnvelope` at line 443
  - `class AuditAnchor` at line 510
  - `class TrustLineageChain` at line 672 (with `verify(VerificationLevel)` per Phase 00 survey item 18 line 562)
  - Companion enums `AuthorityType`, `CapabilityType`, `ActionResult`, `ConstraintType`, `VerificationLevel` at lines 45–113
- **`kailash.trust.operations`** — verified at `~/repos/loom/kailash-py/src/kailash/trust/operations/__init__.py`:
  - `class TrustOperations` at line 176 with `establish` / `delegate` / `verify` / `audit` (Phase 1 (Week 2) implements ESTABLISH/VERIFY; Phase 1 (Week 3) implements DELEGATE/AUDIT per module docstring lines 13–15)
  - `class TrustKeyManager` at line 108 (in-memory; "Production would use HSM or secure key management service")
  - Imports `TrustStore` from `kailash.trust.chain_store` (line 71)
- **`kailash.trust.signing.crypto`** — verified at `~/repos/loom/kailash-py/src/kailash/trust/signing/crypto.py`:
  - `generate_keypair() -> Tuple[str, str]` at line 38
  - `sign(payload, private_key) -> str` at line 120, `verify_signature(...)` at line 168
  - `serialize_for_signing(obj) -> str` at line 223 (canonical-JSON producer)
  - `hash_chain(data) -> str` at line 264
  - `hash_trust_chain_state` / `_salted` at lines 288, 319
  - `class DualSignature` at line 495; `dual_sign` / `dual_verify` at lines 595, 623
- **`kailash.trust.signing.algorithm_id`** (post-#604) — verified at `~/repos/loom/kailash-py/src/kailash/trust/signing/algorithm_id.py`:
  - `ALGORITHM_DEFAULT = "ed25519+sha256"` (line 45). Module docstring line 7 + 22 names this as the **scaffold form awaiting mint ISS-31** — only `ed25519+sha256` is permitted today; non-default values raise `NotImplementedError` (lines 86–91). The wire format `{"algorithm": "<id>"}` (line 105) is stable across mint ISS-31; only the value space changes.
  - This is the ISS-32 / #604 closure verified in §2.1.
- **`kailash.trust.chain_store`** + `kailash.trust.chain_store.sqlite`\*\* — verified at `~/repos/loom/kailash-py/src/kailash/trust/chain_store/__init__.py` and `.../sqlite.py`:
  - `class TrustStore(ABC)` at `__init__.py:63` — abstract base; concrete implementations: `InMemoryTrustStore`, `FilesystemStore`, `SqliteTrustStore`, `PostgresTrustStore`.
  - `class SqliteTrustStore(TrustStore)` at `sqlite.py:55` — single-file persistence (default `~/.eatp/trust.db`), WAL mode, `threading.local()` per-thread connections, `asyncio.to_thread()` async wrapping. Schema (lines 41–51): `agent_id TEXT PRIMARY KEY, chain_data TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, authority_id TEXT, created_at TEXT, updated_at TEXT, deleted_at TEXT, expires_at TEXT`.
- **`kailash.trust.revocation.cascade`** — verified at `~/repos/loom/kailash-py/src/kailash/trust/revocation/cascade.py`:
  - `async def cascade_revoke(agent_id, store, reason, revoked_by, broadcaster, delegation_registry) -> RevocationResult` at line 154. Docstring lines 162–190 confirms: idempotency check (already-revoked = no-op); BFS via `CascadeRevocationManager`; snapshot-and-rollback partial-failure semantics; cross-SDK BFS/DFS set-equality contract (lines 23–46).
  - `dataclass RevocationResult` at line 71 — exposes `success`, `events`, `revoked_agents`, `errors`.
- **`kailash.trust.posture.SQLitePostureStore`** — verified at `~/repos/loom/kailash-py/src/kailash/trust/posture/posture_store.py`:
  - Module docstring lines 9–24: stores current posture per `agent_id` + transition history; security properties (`validate_agent_id`, symlink rejection, 0o600 perms, parameterized SQL, history bounded ≤10,000).
  - `class SQLitePostureStore` is exported (line 47); `validate_agent_id` (line 60) restricts agent IDs to `^[a-zA-Z0-9_-]+$`.

### 2.3 Indirectly-relevant closures (per `03-kailash-py-mvp-readiness.md` § 2.2)

These improve Trust Store reliability without being primary providers:

- `#707` / `#711` — `df.transaction()` + `db.transactions_sync.begin()` context-manager: relevant for atomic multi-record write boundaries when cascade-revoke spans many chains.
- `#757` / `#756` — pin Unicode byte vectors for canonical-input + canonical-JSON: relevant for cross-SDK signing-byte-identity (BET-6).
- `#731` — TraceEvent timestamp microsecond padding: relevant for cross-SDK timestamp determinism on signed records.

---

## 3. Envoy-new-code surface

Per `03-kailash-py-mvp-readiness.md` § 3 row 2: "**Envoy-new-code:** SQLite-backed `TrustStore` adapter (or use `SQLitePostureStore` pattern); single-principal lineage seeding." Concrete surface, scoped to the four required hooks per the shard prompt:

### 3.1 `envoy.trust.TrustStoreAdapter` — composition wrapper, not re-implementation

A Python class composed over `kailash.trust.chain_store.SqliteTrustStore` + `kailash.trust.posture.SQLitePostureStore` + `kailash.trust.operations.TrustOperations`. Not a new implementation of the SDK primitives — per `rules/zero-tolerance.md` Rule 4 ("No Workarounds for Core SDK Issues") + `rules/independence.md` § 1 (this proprietary product implements TF specs, but the open-source Python SDK kailash-py provides these primitives directly under Apache 2.0).

Responsibilities of the adapter:

1. **Single-principal lineage seeding ritual.** Wraps the Boundary Conversation output (shard 8) and invokes `TrustOperations.establish(...)` to create the initial Genesis Record + Trust Lineage Chain for the user. Persists the result via `SqliteTrustStore.store_chain(...)`. Records the "Genesis seeded" event to the Envoy Ledger (shard 6).
2. **Trust Vault cipher binding.** The adapter is responsible for the Trust Vault file format (`specs/trust-vault.md` § File format) — `SqliteTrustStore` is plaintext SQLite by default, so the adapter wraps the SQLite file inside the AES-256-GCM Trust Vault container (Argon2id + Secure Enclave/TPM-bound secret per § Encryption, region-keys via HKDF-SHA-256). The `SqliteTrustStore` instance opens against a path inside the unlocked vault region.
3. **Principal-dimension key-shape hook.** See § 3.2.
4. **Cascade-revocation glue.** See § 3.3.
5. **Algorithm-identifier threading at write boundaries.** Every `GenesisRecord` and `DelegationRecord` written through the adapter MUST carry `AlgorithmIdentifier()` (per `kailash.trust.signing.algorithm_id` line 154 `coerce_algorithm_id` helper) — defaulting to `"ed25519+sha256"` until mint ISS-31 lands. This is the structural defense against pre-#604 hardcoded `"Ed25519"` strings (Phase 00 survey item 19, line 590) drifting back into Envoy code.
6. **Recovery-ritual hooks for Shamir (shard 15).** Adapter exposes `export_master_key_for_shamir() -> bytes` and `import_master_key_from_shamir(reconstructed: bytes) -> None` so the Shamir primitive can read/write the Trust Vault master key without re-implementing the vault crypto.

### 3.2 Principal-dimension key-shape hook (tenant-isolation invariant)

`SqliteTrustStore` schema at `chain_store/sqlite.py:41-51` uses `agent_id TEXT PRIMARY KEY` — no `tenant_id` or `principal_id` column. Phase 01 ships single-principal (one user, one Genesis), so on the kailash-py surface `agent_id` is the de-facto principal proxy. **This is sufficient at the kailash-py layer but insufficient at the Envoy layer.**

Per `.claude/rules/tenant-isolation.md` Rule 1 ("Cache Keys Include Tenant_id for Multi-Tenant Models") — applied with the Phase 03 multi-principal forward-compat in mind:

- The Envoy adapter MUST construct every persistence-key, every cache-key, and every metric-label with a `principal_id` dimension present from day 1, even though Phase 01 has exactly one principal.
- Canonical Envoy adapter key shape: `envoy:trust:v1:{principal_id}:chain:{agent_id}` (where `principal_id == agent_id` in single-principal Phase 01, but the dimension stays in the key).
- BLOCKED by tenant-isolation Rule 1 § DO NOT: dropping `principal_id` "because there's only one principal in MVP" — exactly the rationalization the rule names. The 36-byte hedge survives the Phase 03 multi-principal refactor unchanged.
- Strict mode (Rule 2): missing `principal_id` at the adapter boundary MUST raise `PrincipalRequiredError` (typed), not silently default to "default".

This applies cross-cuttingly to:

- `TrustStoreAdapter` itself (chain reads/writes)
- Adjacent `PostureStoreAdapter` (wraps `SQLitePostureStore`) — same rule, same key-shape
- Cascade-revocation invalidation patterns (Rule 3) — `invalidate_principal(principal_id)` MUST be the entry point, not `invalidate_all_chains()`

Per `specs/trust-lineage.md` § Algorithms — Nonce per-principal partitioning (§6.1 C-02 fix): the spec already contains the principal-dimension contract: "`nonces[principal_genesis_id]` — separate table per principal." The Envoy adapter MUST honor this even in Phase 01 single-principal — the table-per-principal nonce structure is the data shape; populating exactly one principal's table on day 1 is correct, defaulting away the dimension is incorrect.

### 3.3 Cascade-revocation glue (EC-2)

`kailash.trust.revocation.cascade.cascade_revoke()` provides the BFS walker + snapshot-and-rollback contract. The Envoy adapter wraps it for two integrations required by EC-2 ("3 Grant Moments triggered and resolved correctly", `02-mvp-objectives.md` lines 31–43):

1. **Grant-Moment-driven revocation:** when a user revokes a previously-granted out-of-envelope action via Grant Moment UI (shard 10), the adapter calls `cascade_revoke(agent_id=<grant-moment-target>, store=<SqliteTrustStore>, reason=<user-text>, revoked_by=<principal-genesis-id>)`. The returned `RevocationResult.revoked_agents` set is written as a single Ledger entry covering the whole cascade.
2. **Cross-channel descendant verification (EC-8 hook):** `02-mvp-objectives.md` EC-8 (lines 116–117) requires "cascade revocation of a Day-1 grant correctly revokes a Day-6 child grant initiated from a different channel." The Envoy adapter MUST expose a `verify_cascade_complete(revocation_id)` method that loads the latest `RevocationResult.revoked_agents` set and checks that every descendant in the Trust Lineage's `chain_parent_id` graph is included — defense against a malformed `delegation_registry` that under-reports descendants.

### 3.4 Algorithm-identifier versioning (post-#604, structural lock-in)

Per `~/repos/loom/kailash-py/src/kailash/trust/signing/algorithm_id.py` lines 80–91 + `specs/trust-lineage.md` § Algorithm migration: every Genesis / Delegation / Revocation / KeyRotation record written through the adapter MUST embed `algorithm_identifier` matching the canonical wire shape `{"algorithm": "ed25519+sha256"}`. The Envoy-new-code structural defense:

- Adapter exposes a single `_with_algorithm_id()` helper that every record-construction code path goes through. No record dataclass is constructed without algorithm_identifier set.
- The mint ISS-31 forward path (per the algorithm*id.py module docstring) only changes the \_value space* of `algorithm`; the dict shape stays. The Envoy adapter is therefore future-proof: a future migration to (say) `"mldsa44+sha256"` (post-quantum) requires zero re-threading of code, only a value-space update — the structural form is already there.
- BLOCKED rationalization (per Phase 00 survey item 19 + `rules/zero-tolerance.md` Rule 4): re-introducing hardcoded `"Ed25519"` strings anywhere in Envoy code is BLOCKED, even though kailash-py's own legacy `chain.py` GenesisRecord dataclass (line 523, Phase 00 survey citation) still has `signature_algorithm: str = "Ed25519"` at the dataclass level. The adapter wraps that legacy field but writes the canonical algorithm_identifier dict alongside.

---

## 4. Class structure sketch (interfaces only)

This is a pseudocode sketch, not implementation. Per the per-shard structure (`01-shard-plan.md` §2 step 4): "Sketch the primitive's class structure (interfaces, not implementation)."

```python
# envoy/trust/store.py — adapter wrapping kailash-py providers

from kailash.trust.chain import (
    GenesisRecord, DelegationRecord, TrustLineageChain,
)
from kailash.trust.chain_store.sqlite import SqliteTrustStore
from kailash.trust.posture.posture_store import SQLitePostureStore
from kailash.trust.operations import TrustOperations, TrustKeyManager
from kailash.trust.revocation.cascade import cascade_revoke, RevocationResult
from kailash.trust.signing.algorithm_id import (
    AlgorithmIdentifier, coerce_algorithm_id,
)


class PrincipalRequiredError(Exception):
    """Raised when an adapter call is missing the required principal_id dimension."""


class VaultLockedError(Exception):
    """Raised when a vault-touching adapter call fires while the Trust Vault container is locked.

    Carry-forward R2-M-02 disposition (per `workspaces/phase-01-mvp/04-validate/round-4-implementation-comprehensive.md` § 4):
    every adapter method that reads or writes the vault region MUST raise this typed error
    when invoked outside an `unlock(passphrase)` -> `lock()` window or after the idle timer
    expired. No silent fallback to a sentinel; no implicit re-unlock.
    """


class TrustStoreAdapter:
    """Envoy-side adapter over kailash-py trust primitives.

    Composes SqliteTrustStore + SQLitePostureStore + TrustOperations
    inside an AES-256-GCM Trust Vault container (specs/trust-vault.md).
    Threads principal_id through every key-shape (tenant-isolation Rule 1)
    and AlgorithmIdentifier through every signed-record write boundary.
    """

    def __init__(
        self,
        vault_path: str,
        principal_id: str,
        # Vault-cipher params from specs/trust-vault.md § Encryption
    ) -> None: ...

    # --- Vault lifecycle surface (carry-forward R2-M-02 disposition) ---
    # Per workspaces/phase-01-mvp/04-validate/round-4-implementation-comprehensive.md § 4:
    # explicit vault lifecycle is part of the § 4 step-3 (vault container) contract.
    # Every adapter method that reads/writes the vault region MUST guard against
    # VaultLockedError (per specs/trust-vault.md § Encryption + § File format).
    async def unlock(self, passphrase: str) -> None:
        """Derive the master key (Argon2id + Secure-Enclave/TPM-bound secret),
        AES-256-GCM-decrypt the vault region, start the idle-lock timer."""
        ...

    async def lock(self) -> None:
        """Zeroize the in-memory master key, encrypt-back any dirty pages,
        cancel the idle-lock timer."""
        ...

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """`async with TrustStoreAdapter(...) as ts:` auto-locks on exit
        regardless of exception path. Invokes self.lock()."""
        ...

    def _idle_timer_reset(self) -> None:
        """Every adapter call (read or write) MUST invoke this before returning
        so the idle-lock timer resets to the configured TTL. Internal; not
        part of the public surface."""
        ...

    # --- Genesis seeding (single-principal Phase 01) ---
    async def seed_genesis(
        self,
        principal_display_name: str,
        principal_pseudonym: str,
        device_attestation: dict,
        shamir_threshold: tuple[int, int],
    ) -> GenesisRecord: ...

    # --- Chain access (principal_id-keyed) ---
    async def get_chain(
        self, *, principal_id: str, agent_id: str
    ) -> TrustLineageChain: ...

    async def store_chain(
        self, *, principal_id: str, chain: TrustLineageChain
    ) -> None: ...

    # --- Delegation (Grant-Moment write path) ---
    async def record_delegation(
        self,
        *,
        principal_id: str,
        delegator: GenesisRecord,
        delegatee_agent_id: str,
        capabilities: list[dict],
        envelope_version: int,
        effective_envelope_hash: str,
        valid_from, valid_until,
    ) -> DelegationRecord:
        """Record a delegation under `delegator`.

        Carry-forward R2-M-04 disposition (per `workspaces/phase-01-mvp/04-validate/round-4-implementation-comprehensive.md` § 4):
        this method MUST route every delegation through
        `kailash.trust.operations.TrustOperations.delegate(...)` and exercise the
        upstream's full 10-step verification (cycle-free check, depth ≤ 16, capability
        intersection, monotonic tightening, signing-key ownership, algorithm-identifier
        coercion, parent_hash linkage, timestamp ordering, principal_id consistency,
        envelope-version monotonicity). The adapter MUST NOT bypass any of the 10
        steps with a "fast path" — `rules/zero-tolerance.md` Rule 4 forbids
        re-implementing SDK logic.
        """
        ...

    # --- Cascade revocation (EC-2 + EC-8) ---
    async def revoke(
        self,
        *,
        principal_id: str,
        agent_id: str,
        reason: str,
        revoked_by: str,
    ) -> RevocationResult: ...

    async def verify_cascade_complete(
        self, *, principal_id: str, revocation_id: str
    ) -> bool: ...

    # --- Posture (specs/posture-ladder.md integration) ---
    async def get_posture(
        self, *, principal_id: str, agent_id: str
    ) -> "PostureLevel": ...

    async def set_posture(
        self, *, principal_id: str, agent_id: str,
        posture: "PostureLevel", evidence,
    ) -> None: ...

    # --- Shamir hooks (shard 15) ---
    async def export_master_key_for_shamir(self) -> bytes: ...
    async def import_master_key_from_shamir(self, reconstructed: bytes) -> None: ...

    # --- Internal: structural lock-ins ---
    def _to_spec_wire_form(self, algorithm_dict: dict) -> dict:
        """Translate upstream's 1-key form into the spec's 3-key wire form.

        Round 2 R2-H-01 fix: spec-mandated 3-key wire form
        (specs/trust-lineage.md L24).

        Upstream `kailash.trust.signing.algorithm_id.AlgorithmIdentifier.to_dict()`
        emits the 1-key scaffold form `{"algorithm": "ed25519+sha256"}` (kailash-py
        algorithm_id.py line 105, post-#604 scaffold awaiting mint ISS-31).
        The Phase 00 frozen specs `specs/trust-lineage.md` line 24 +
        `specs/independent-verifier.md` line 35 mandate the 3-key form
        `{"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}` on every
        on-disk DelegationRecord / GenesisRecord / RevocationRecord that the
        Independent Verifier (shard 7) consumes.

        This helper is the SINGLE point of producer-side translation per
        `rules/specs-authority.md` MUST Rule 6 (deviations from upstream are
        explicitly acknowledged at one bottleneck, never spread across call
        sites). Every record-construction path routes through
        `_with_algorithm_id()` which routes through this helper before write.

        Verified by `tests/integration/test_producer_verifier_wire_shape_round_trip.py`
        (R2-H-01 regression) — see `02-plans/02-test-strategy.md` § EC-9 battery.
        """
        # Parse upstream's compound "ed25519+sha256" form
        compound = algorithm_dict.get("algorithm", "")
        sig, _, hash_alg = compound.partition("+")
        return {
            "sig": sig or "ed25519",
            "hash": hash_alg or "sha256",
            "shamir": "slip39",
        }

    def _with_algorithm_id(self, record_dict: dict) -> dict:
        """Embed canonical algorithm_identifier on every signed-record dict.

        Single point of enforcement — no record-construction path bypasses
        this helper. Forward-path-safe per kailash-py#604 / mint ISS-31.

        Round 2 R2-H-01 fix: spec-mandated 3-key wire form
        (specs/trust-lineage.md L24). Upstream's 1-key dict from
        `AlgorithmIdentifier().to_dict()` is translated by
        `_to_spec_wire_form()` before persistence; the on-wire bytes match
        the 3-key spec form that the Independent Verifier (shard 7,
        `specs/independent-verifier.md` L35) consumes.
        """
        upstream_form = AlgorithmIdentifier().to_dict()
        record_dict["algorithm_identifier"] = self._to_spec_wire_form(upstream_form)
        return record_dict

    def _key(self, principal_id: str, suffix: str) -> str:
        """Canonical key shape — principal_id always present (Rule 1)."""
        if not principal_id:
            raise PrincipalRequiredError(
                "TrustStoreAdapter calls require principal_id dimension"
            )
        return f"envoy:trust:v1:{principal_id}:{suffix}"
```

This sketch is interfaces only; implementation is shard-out-of-scope.

---

## 5. Integration points

The Trust Store underpins five neighboring primitives. Each is one Envoy primitive ↔ Trust Store hop.

| Neighboring primitive (shard) | Hook                                                                                                           | Direction     | Spec citation                                                          |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------- | ---------------------------------------------------------------------- |
| Boundary Conversation (8)     | `seed_genesis(...)` invoked at end of first-time-user conversation; principal-id provisioned                   | BC → TS write | `specs/boundary-conversation.md` (out of scope this shard)             |
| Envelope compiler (4)         | Compiled `RoleEnvelope` written into the Trust Vault `envelope` region; `envelope_version` recorded            | EC → TS write | `specs/envelope-model.md` § envelope_version binding                   |
| Authorship Score (9)          | `get_posture()` + posture-change Ledger entries read by authorship-score's posture-ratchet gate                | TS → AS read  | `specs/authorship-score.md` § Re-derivation; `specs/posture-ladder.md` |
| Grant Moment (10)             | Signed-consent records written via `record_delegation(...)` + `_with_algorithm_id` Ed25519 signing             | GM → TS write | `specs/trust-lineage.md` § Schema (DelegationRecord)                   |
| Daily Digest (11)             | Reads cascade-revocation outcomes via `RevocationResult` logs to render "your N grants revoked today" sections | TS → DD read  | `specs/daily-digest.md` (out of scope this shard)                      |
| Shamir recovery (15)          | `export_master_key_for_shamir()` / `import_master_key_from_shamir()` hooks at backup + recovery rituals        | TS ↔ Shamir   | `specs/shamir-recovery.md` § Recovery flow + § Rotation ritual         |
| Channel adapters (16)         | Cross-channel coherence (EC-8): a grant on Telegram is honored by a Slack-initiated action 3 days later        | Adapters → TS | `02-mvp-objectives.md` EC-8 acceptance gate                            |

Per `rules/orphan-detection.md` Rule 1 ("Every `db.*` / `app.*` Facade Has a Production Call Site"), each adapter method enumerated in §4 MUST have at least one production call site in the Envoy hot path within 5 commits of the facade landing — no method may be exposed without a hot-path consumer. The integration-point table above pre-declares the required call sites.

Per `rules/facade-manager-detection.md` Rule 1 ("Every Manager-Shape Class Has a Tier 2 Test"), `TrustStoreAdapter` is a `*Adapter`-shape class on the framework's top-level surface; it MUST have at least one Tier 2 test that imports it through the framework facade and asserts an externally-observable effect (a row in the SQLite database, a signed record verifiable by `verify_signature`, a successful cascade-revocation propagation).

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/testing.md` § "Tier 2 (Integration): Real infrastructure recommended" — real SQLite + real Ed25519 keys, NO mocking. Phase 01 EC-2, EC-4, EC-5, EC-8 all transitively require Trust Store integration tests.

### 6.1 Tier 2 — real infrastructure

| Test                                                      | Asserts                                                                                                                                                     | Spec source                                                                                |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `test_trust_store_adapter_genesis_round_trip.py`          | `seed_genesis(...)` writes a real `GenesisRecord` to a real `SqliteTrustStore`; `get_chain(...)` returns the same record; `verify_signature` passes Ed25519 | `specs/trust-lineage.md` § Schema GenesisRecord                                            |
| `test_trust_store_adapter_principal_dimension.py`         | Adapter raises `PrincipalRequiredError` when `principal_id` missing; SQLite key shape contains `principal_id`                                               | `rules/tenant-isolation.md` Rule 1 + Rule 2                                                |
| `test_trust_store_adapter_algorithm_identifier.py`        | Every record written carries `algorithm_identifier == {"algorithm": "ed25519+sha256"}`; non-default algorithm raises `NotImplementedError` (#604 scaffold)  | `kailash.trust.signing.algorithm_id` lines 80–91                                           |
| `test_trust_store_adapter_cascade_revoke_bfs_complete.py` | Build a 3-deep delegation tree; revoke root; assert `RevocationResult.revoked_agents` reaches every descendant; `verify_cascade_complete` returns True      | `specs/trust-lineage.md` § Cascade revocation; `kailash.trust.revocation.cascade` line 154 |
| `test_trust_store_adapter_cascade_revoke_idempotent.py`   | Second revoke of same agent returns `RevocationResult(success=True, events=[], revoked_agents=[])`                                                          | `kailash.trust.revocation.cascade.cascade_revoke` docstring lines 191–196                  |
| `test_trust_store_adapter_cascade_partial_failure.py`     | Force a chain-deletion failure mid-cascade; assert prior deletions roll back via `_rollback_chains`; `RevocationResult.success == False`                    | `kailash.trust.revocation.cascade.cascade_revoke` docstring lines 173–177                  |
| `test_trust_store_adapter_vault_unlock_aes256gcm.py`      | Real Argon2id derivation + AES-256-GCM outer encryption; tamper at file level rejected with `VaultMACVerificationFailedError`                               | `specs/trust-vault.md` § File format + § Error taxonomy                                    |
| `test_trust_store_adapter_posture_round_trip.py`          | `set_posture(SUPERVISED) -> get_posture()` returns SUPERVISED; transition history queryable via `SQLitePostureStore` with bounded limit ≤10,000             | `kailash.trust.posture.posture_store` lines 9–24                                           |

### 6.2 Tier 3 — cross-OS portability + cross-tool interop

| Test                                                | Asserts                                                                                                                                                                                                                         | EC tested |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `test_trust_store_cross_os_portability.py` (BET-9b) | Trust Vault + Trust Store SQLite created on macOS unlocks correctly on Linux + Windows (and vice versa); per-OS file-permission semantics honored (0o600 on POSIX)                                                              | EC-5      |
| `test_trust_store_shamir_master_key_roundtrip.py`   | `export_master_key_for_shamir()` produces bytes that, after SLIP-0039 3-of-5 split + reconstruction, restore the original master key via `import_master_key_from_shamir()`; cross-tool reconstruct via `python-shamir-mnemonic` | EC-5      |
| `test_trust_store_cross_channel_coherence_7day.py`  | A `record_delegation(...)` from channel A on Day 1 + `revoke(...)` from channel B on Day 6 produces an EC-8-compatible cascade                                                                                                  | EC-8      |

### 6.3 Wiring tests (orphan-detection + facade-manager-detection)

Per `rules/facade-manager-detection.md` Rule 2 (test file naming convention) + Rule 3 (constructor receives parent framework instance):

- Test file MUST be named `test_trust_store_adapter_wiring.py` (adapter-shape, predictable name; `/redteam` automatically detects missing wiring).
- Constructor MUST receive an explicit `vault_path` + `principal_id` (no global lookup, no self-construction of the underlying `SqliteTrustStore`); the `SqliteTrustStore` instance is owned by the adapter and not pulled from a module-global.

Per `rules/orphan-detection.md` Rule 2a (Crypto-Pair Round-Trip) — `sign` / `verify_signature`, `seed_genesis` / `verify_chain`, `record_delegation` / `revoke` are all paired operations: each pair MUST be exercised through the adapter facade in at least one Tier 2 round-trip test (not two unit tests with mocks of each other's halves).

---

## 7. Frozen-spec ambiguity surfaced during analysis

Per `01-shard-plan.md` § 4 ("Failure modes + mitigations"), HIGH-severity spec ambiguity escalates via the failure-mode protocol — STOP the deep-dive, convene MUST-Rule-5b sweep, edit spec under full-sibling redteam economics. Lower-severity ambiguity is logged here but does not block the shard.

### 7.1 LOW — `principal_id` vs `agent_id` terminology

`specs/trust-lineage.md` § Algorithms — Nonce per-principal partitioning uses `principal_genesis_id`. `kailash-py`'s `SqliteTrustStore` schema uses `agent_id`. `specs/posture-ladder.md` § Shared Household uses `principal`. The mapping is consistent (the principal IS the human; the principal's Genesis is the cryptographic root; downstream agents receive delegated trust) but the terminology drift is a future-confusion risk. This is NOT escalating to HIGH today because:

- Phase 01 is single-principal (one human → one Genesis → all agents share the principal_id).
- The kailash-py API is what it is; the Envoy adapter does the principal_id ↔ agent_id mapping.
- Phase 03 multi-principal will need a clean `principal_id` distinct from `agent_id`, but that's downstream work — and `specs/trust-lineage.md` already has `principal_genesis_id` as the canonical principal anchor. No spec edit required today.

**Disposition:** logged as a Phase 03 readiness concern; not a Phase 01 blocker.

### 7.2 RESOLVED (Round 2 R2-H-01) — algorithm_identifier wire shape

`specs/trust-lineage.md` line 24 + `specs/independent-verifier.md` line 35 mandate the 3-key form `{"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}` on every signed-record on-disk wire shape. `kailash-py`'s `algorithm_id.py` (post-#604 scaffold awaiting mint ISS-31) emits the 1-key form `{"algorithm": "ed25519+sha256"}` from `AlgorithmIdentifier().to_dict()` (line 105).

**Resolution (Round 2 R2-H-01 fix):** the Envoy adapter is the SINGLE point of producer-side translation between upstream's 1-key form and the spec's 3-key form. `_to_spec_wire_form()` (§ 4 sketch, sibling helper to `_with_algorithm_id()`) performs the translation; every record-construction path routes through `_with_algorithm_id()` which routes through `_to_spec_wire_form()` before persistence. The on-wire bytes match the 3-key spec form that the Independent Verifier (shard 7) consumes via the bundle parser per `specs/independent-verifier.md` line 35.

**Per `rules/specs-authority.md` MUST Rule 6 — explicit deviation from upstream:** the Envoy adapter intentionally diverges from `kailash.trust.signing.algorithm_id.AlgorithmIdentifier.to_dict()`'s 1-key wire format because the Phase 00 frozen specs `specs/trust-lineage.md` L24 + `specs/independent-verifier.md` L35 mandate the 3-key form on the signed-record on-disk surface. Spec authority overrides upstream scaffold form. The deviation is contained to ONE bottleneck (`_to_spec_wire_form()`), so when mint ISS-31 reconciles upstream to the 3-key form, the helper becomes a pass-through and removal is mechanical. This is the structural defense per `rules/specs-authority.md` Rule 4 (read-then-act): Envoy's wire shape matches the spec, full stop. Verified by `tests/integration/test_producer_verifier_wire_shape_round_trip.py` per `02-plans/02-test-strategy.md` § EC-9 battery.

### 7.3 None HIGH-severity surfaced

No HIGH-severity ambiguity surfaced during this shard. The Trust Store + Lineage primitive is well-specified (cross-SDK ✅ on both kailash-py and kailash-rs per `specs/trust-lineage.md` § Provenance), well-provisioned upstream (12-of-13 Phase 00-filed issues closed; #604 algorithm-identifier closed and verified at `signing/algorithm_id.py`), and the Envoy-new-code surface is composition-and-integration, not re-implementation.

---

## 8. Cross-references

- **Phase 01 brief:** `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`
- **Inheritance map:** `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md`
- **Sharding plan:** `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (shard 5 row) + § 5 (sequencing — Trust store is in Group A, no upstream Phase 01 deps; gates Authorship Score (9), Grant Moment (10), Shamir (15))
- **MVP objectives:** `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` EC-2 (Grant Moments cascade), EC-5 (Shamir reconstruct), EC-8 (cross-channel coherence)
- **kailash-py readiness:** `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 2 + § 5 verification protocol
- **Methodology bridge:** `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`
- **Phase 00 survey items:** `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` items 5 (PostureStore), 17 (TrustOperations + GenesisRecord + DelegationRecord), 18 (TrustLineageChain.verify), 19 (algorithm-identifier hardcoding pre-#604)
- **Phase 00 reconciliation:** `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` rows 5, 17, 18, 19
- **Source specs (FROZEN — DO NOT EDIT):** `specs/trust-vault.md`, `specs/trust-lineage.md`, `specs/posture-ladder.md`, `specs/authorship-score.md`, `specs/shamir-recovery.md`
- **Verified provider modules (read-only references):**
  - `~/repos/loom/kailash-py/src/kailash/trust/chain.py` (lines 122–300+, 400–600+, 672+)
  - `~/repos/loom/kailash-py/src/kailash/trust/operations/__init__.py` (lines 71, 108, 176)
  - `~/repos/loom/kailash-py/src/kailash/trust/signing/crypto.py` (lines 38, 120, 168, 223, 264, 595, 623)
  - `~/repos/loom/kailash-py/src/kailash/trust/signing/algorithm_id.py` (lines 1–162, post-#604 scaffold)
  - `~/repos/loom/kailash-py/src/kailash/trust/chain_store/__init__.py` (lines 63+)
  - `~/repos/loom/kailash-py/src/kailash/trust/chain_store/sqlite.py` (lines 41–80)
  - `~/repos/loom/kailash-py/src/kailash/trust/posture/posture_store.py` (lines 47–80)
  - `~/repos/loom/kailash-py/src/kailash/trust/revocation/cascade.py` (lines 71–219)
- **Closed upstream issues verified:** terrene-foundation/kailash-py#604 (closed 2026-04-25T14:43:55Z), terrene-foundation/kailash-py#597 (closed 2026-04-24T17:02:09Z), terrene-foundation/kailash-py#595 (closed 2026-04-25)
- **Applicable rules:** `.claude/rules/tenant-isolation.md` Rule 1 + Rule 2 + Rule 3 (cascade-scoped invalidation), `.claude/rules/orphan-detection.md` Rule 1 + Rule 2 + Rule 2a (crypto-pair round-trip), `.claude/rules/facade-manager-detection.md` Rule 1 + Rule 2 + Rule 3, `.claude/rules/zero-tolerance.md` Rule 4 (no SDK workarounds), `.claude/rules/testing.md` § Tier 2 + § Tier 3, `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget
