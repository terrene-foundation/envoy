# 01 — Wave 1: Foundation primitives

**Purpose:** Build the 7 foundation primitives that no other primitive depends on. Parallelizable across worktrees per `rules/agents.md` § "Worktree Isolation for Compiling Agents". Wave 1 must converge before Wave 2 launches.

**Source authority:** `02-plans/01-build-sequence.md` § Wave 1 + `02-plans/03-package-skeleton.md` § 2.

**Capacity discipline:** Each todo below names its `## Capacity check` (LOC + invariants + call-graph hops). Sharding decisions are pinned at /todos opening per `rules/autonomous-execution.md`.

---

## T-01-10 — Build envoy/envelope/

**Implements:** `specs/envelope-model.md` + `specs/sub-agent-delegation.md`

**Source:** Build seq § Wave 1 #envoy.envelope.compiler; shard `01-analysis/04-envelope-compiler-implementation.md` § 4.

**Steps (per shard 4 § 4):**

1. Skeleton + types — `envoy/envelope/__init__.py`, `types.py` (24 typed errors), empty `compiler.py`.
2. Canonical-bytes pipeline — JCS+NFC `canonical_bytes` + `content_hash` matching shard 6 Ledger pipeline.
3. `compile()` against `kailash.trust.pact.envelopes` — wraps `intersect_envelopes`, `RoleEnvelope.validate_tightening`, `compute_effective_envelope`. **Sort `authored_constraints` lexicographically at construction** (R2-M-03). **Propagate `IntersectConflictError` to caller; never silently fall back** (R2-M-05).
4. Template-resolver stub — local-only Phase 01; Foundation Library deferred Phase 02.

**Tests added:** `tests/tier1/test_envelope_canonical_bytes_pure.py`; `tests/tier1/test_envelope_config_dataclass_post_init.py` (Tier 1 coverage seeded; full unit suite consolidated in `07-tests-tier1.md`).

**Capacity check:** ~350 LOC; 6 invariants (JCS-canonical-order; NFC normalization; content-hash equivalence; sort discipline; intersect-error propagation; template-resolver Phase 01 stub); 2 call-graph hops. Within budget.

**Spec edits:** None (all spec content already frozen v1).

**Estimate:** 1 session.

### Verification (2026-05-06 — COMPLETE)

Per /implement workflow Step 7:

1. **Plan section re-read.** `02-plans/01-build-sequence.md` § Wave 1 #envoy.envelope.compiler steps 1-4 + shard `01-analysis/04-envelope-compiler-implementation.md` § 4 (10-step compile pipeline post-R2-M-03 expansion).
2. **Detail-by-detail check.**
   - Steps 1 (skeleton + types), 2 (canonical-bytes pipeline), 3 (compile() against `kailash.trust.pact.envelopes`), 4 (template-resolver stub) — all shipped at `envoy/envelope/{compiler.py, types.py, canonical_bytes.py, template_resolver.py, errors.py, __init__.py}` (1262 LOC across 7 modules).
   - R2-M-03: `_sort_authored_constraints()` lives in `compiler.py:_sort_authored_constraints`; covered by `tests/tier1/test_envelope_compiler_pipeline.py::TestR2M03AuthoredConstraintsSort` (2 tests, both green).
   - R2-M-05: `IntersectConflictError` declared in `errors.py`; `intersect()` method DEFERRED to Wave 3 (T-03-50 Grant Moment) — see DEVIATION below.
   - V-06 (canonical clearance enum): `ConfidentialityLevel.PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED/HIGHLY_CONFIDENTIAL` — `tests/tier1/test_envelope_config_dataclass_post_init.py::TestConfidentialityLevelEnum::test_canonical_names_are_pact_aligned`.
   - 4-key algorithm_identifier (R3-M-02 carry-forward): `AlgorithmIdentifier(sig, hash, shamir, canonical_json)` defaults — covered by `TestAlgorithmIdentifierDefaults::test_default_4_key_form`.
3. **Wiring check.** `envoy/__init__.py` re-exports `EnvelopeCompiler` per `rules/orphan-detection.md` Rule 6. Hot-path call site is `envoy/cli.py` (T-05-90 Wave 5 — within 5-commit headroom of Rule 1 since T-01-10 is the very first commit-class). T-01-11 (Tier 2 wiring test) blocks on T-01-12 + T-01-17, scheduled for Wave 1 milestone gate.
4. **Journal constraint check.** journal/0001 (cite-don't-paraphrase) — every spec citation in compiler.py uses path + section. journal/0004 Pattern 3 (per-field wire-shape sweeps) — algorithm_identifier emits the canonical 4-key form.
5. **Tests.** 42/42 Tier 1 tests pass in 0.14s. `pip check` clean.
6. **Spec edits.** None made — spec is frozen v1 and the implementation matches it.

### Deviations (per `rules/specs-authority.md` MUST Rule 6 + `spec-accuracy.md`)

**`EnvelopeCompiler.intersect()` deferred to Wave 3.** Shard 4 § 4 lists `intersect()` as part of EnvelopeCompiler's public surface. The full kailash-py `intersect_envelopes` wrap requires a clearance-mapping translation layer (kailash-py uses lowercase `public/restricted/confidential/secret/top_secret`; envoy spec uses `Public/Internal/Confidential/Restricted/HighlyConfidential` per V-06). That mapping work belongs in Wave 3 where Grant Moment (T-03-50) surfaces the first divergent-dim intersect consumer. Shipping a partial intersect that raises `NotImplementedError` on divergent dims would violate `rules/zero-tolerance.md` Rule 6 (Implement Fully) + Rule 2 (No Stubs). Consequence: Wave-3 todo T-03-50 picks up `intersect()` as part of Grant Moment cascade-revocation orchestrator wiring; `IntersectConflictError` stays in `errors.py` as the typed-error declaration consumed by that producer. Captured in `journal/0008-DECISION-intersect-deferred-to-wave-3.md`.

**`uuid.uuid4` instead of `uuid-v7`** for `envelope_id`. Spec § Schema L23 says `"envelope_id": "uuid-v7"` (time-orderable). `uuid.uuid7` is not in stdlib until Python 3.14; Python 3.13 (pyproject `requires-python>=3.11`) ships `uuid4`. Phase 02 entry can flip to uuid-v7 once the toolchain bumps; this is a non-load-bearing forensics-trail concern (envelope_id is opaque to consumers).

---

## T-01-11 — Wire envoy/envelope/ (Tier 2)

**Implements:** `rules/orphan-detection.md` Rule 1 (every facade has a hot-path call site within 5 commits).

**Action:** `tests/tier2/test_envelope_compiler_wiring.py` — exercises `EnvelopeCompiler.compile()` end-to-end against real Trust store fixture; asserts Ledger row appended; asserts JCS round-trip byte-identity.

**Acceptance:** Test green against real SQLite + real Ed25519 keypair. NO mocking.

**Blocks on:** T-01-10 + T-01-12 (Trust store fixture) + T-01-17 (Ledger fixture).

**Estimate:** 0.25 session.

---

## T-01-12 — Build envoy/trust/store + types

**Implements:** `specs/trust-vault.md` + `specs/trust-lineage.md`

**Source:** Build seq § Wave 1 #envoy.trust.store; shard `01-analysis/05-trust-store-implementation.md` § 4 steps 1-2.

**Steps:**

1. Adapter shell + `principal_id` keying — `envoy/trust/store.py` constructor takes `vault_path` + `principal_id` (no defaults; `PrincipalRequiredError` per `rules/tenant-isolation.md` Rule 2).
2. `SqliteTrustStore` + `SQLitePostureStore` composition — Genesis seeding ritual (`seed_genesis`); `record_delegation`; `get_chain` / `store_chain`. **Route `record_delegation()` through `TrustOperations.delegate(...)` 10-step verification** (R2-M-04).

**Capacity check:** ~250 LOC; 5 invariants (principal_id required; Genesis seed signing; delegation chain depth ≤16; cycle-free verification; store composition contract); 3 call-graph hops. Within budget.

**Estimate:** 1 session.

### Verification (2026-05-06 — COMPLETE)

Per /implement workflow Step 7:

1. **Plan section re-read.** Shard `01-analysis/05-trust-store-implementation.md` § 4 steps 1-2 + journal/0009 async-migration disposition (Option A).
2. **Detail-by-detail check.**
   - Step 1 (adapter shell + principal_id keying): `envoy/trust/store.py:TrustStoreAdapter.__init__` raises `PrincipalRequiredError` on empty/non-string principal_id; covered by `tests/tier1/test_trust_store_principal_id.py::TestConstructorPrincipalIdDiscipline` (4 tests).
   - Step 2 (SqliteTrustStore + SQLitePostureStore composition + Genesis + R2-M-04 routing):
     - `seed_genesis()` async; routes through `TrustOperations.establish` (10-step verification); raises `GenesisAlreadySeededError` on re-seed; refuses cross-principal seeds.
     - `record_delegation()` async; routes through `TrustOperations.delegate` (R2-M-04 carry-forward); refuses cross-principal delegators; **kailash's `CapabilityNotFoundError` propagates when delegating unowned capability** (positive verification of R2-M-04 — see `TestDelegationRouting::test_delegate_unowned_capability_refused_by_kailash`).
     - `get_chain()` / `store_chain()` / `list_chain_ids()` async with principal_id discipline.
3. **Wiring check.** `TrustStoreAdapter` exported via `envoy.trust.__init__`. Phase 01 hot-path call sites land in T-01-15 (R2-H-01 wire-form) + T-01-16 (Tier 2 wiring) + T-02-31 (PostureGate consumes Trust store on transition) — all within 5-commit headroom.
4. **Journal constraint check.** journal/0001 (cite-don't-paraphrase) — every kailash citation in store.py uses module path. journal/0004 Pattern 4 (per-shard freshness gate) — kailash-py 2.13.4 signatures verified at implementation time, surfaced journal/0009.
5. **Tests.** 58/58 Tier 1 tests pass in 0.24s. `pip check` clean.
6. **Spec edits.** None made — spec is frozen v1 and the implementation matches it.

### Deviations (per `rules/specs-authority.md` MUST Rule 6 + journal/0009)

**TrustStoreAdapter is async** (kailash-py 2.13.4 `TrustOperations` + `SqliteTrustStore` + `SQLitePostureStore` are all async). Shard 5 § 4 cited sync signatures; the actual upstream is async. Captured in `journal/0009-DISCOVERY-trust-store-async-deviation.md`. User approved Option A (full async migration).

**Constructor takes 2 more deps than shard 5 indicated** — kailash-py's `TrustOperations(authority_registry, key_manager, trust_store, max_delegation_depth=10)` requires a Phase 01 in-process `_InMemoryAuthorityRegistry` (kailash declares only the `AuthorityRegistryProtocol`, no concrete impl) + an `InMemoryKeyManager()`. Phase 02 entry replaces both with Foundation-stewarded equivalents.

**`CapabilityRequest(capability, capability_type)` not `CapabilityRequest(name)`** — the shard's signature was wrong. Fixed at construction; every Phase 01 capability ships as `CapabilityType.ACTION` (per `specs/posture-ladder.md` mapping; ACCESS + DELEGATION are Phase 02).

---

## T-01-13 — Build envoy/trust/vault (AES-256-GCM container + lifecycle)

**Implements:** `specs/trust-vault.md` § File format

**Source:** Shard `01-analysis/05-trust-store-implementation.md` § 4 step 3.

**Steps:**

1. AES-256-GCM Trust Vault container — wrap SQLite file in vault per spec.
2. Argon2id + Secure-Enclave/TPM-bound secret on macOS / Linux / Windows (per platform).
3. **Vault lifecycle (R2-M-02):** `unlock(passphrase)`, `lock()`, `__aexit__(...)`, `_idle_timer_reset()`, `VaultLockedError`.

**Capacity check:** ~300 LOC; 4 invariants (AES-256-GCM correct; Argon2id parameters; idle-timer monotonic; fail-closed default); 2 call-graph hops. Within budget.

**Blocks on:** T-01-12.

**Estimate:** 1 session.

## Verification — T-01-13

Status: SHIPPED 2026-05-06. Commit (per-todo cadence on `feat/phase-01-wave-1-foundation-t-01-13`).

- `envoy/trust/vault.py` (~390 LOC) — `TrustVault` class with `create()` / `unlock()` / `lock()` / `read()` / `write()` / `unlocked()` context manager + `__aenter__` / `__aexit__` lifecycle.
- `envoy/trust/errors.py` adds 5 typed errors: `VaultError` (base), `VaultLockedError`, `VaultUnlockFailedError`, `VaultMACVerificationFailedError`, `Argon2ParameterMismatchError`, `AutoLockIdleTimeoutError`.
- `pyproject.toml` adds direct deps: `cryptography>=44.0` (AES-256-GCM via `cryptography.hazmat.primitives.ciphers.aead.AESGCM`), `argon2-cffi>=23.0` (Argon2id KDF).
- File format: 53-byte header (`b"ETVT"` magic + version + payload_len + salt + Argon2id (m, t, p) + nonce) followed by AES-256-GCM ciphertext + tag. Header bytes are AAD — any header tamper fails MAC verification.
- Argon2id parameters pinned to canonical (m=2^17, t=3, p=1) per `specs/trust-vault.md` § Encryption; non-canonical params raise `Argon2ParameterMismatchError`.
- Idle-lock timer: cancel-and-recreate on every `read()` / `write()` / `_touch_activity()`; auto-lock fires after `idle_ttl_seconds` (default 15min per spec § Memory hygiene); subsequent access raises `AutoLockIdleTimeoutError`.
- Master key zeroized on `lock()` via in-place bytearray overwrite (best-effort residency minimization per `rules/trust-plane-security.md` MUST NOT Rule 3 — Phase 02 will add `ctypes.memset` cleansing).
- Atomic write per `rules/trust-plane-security.md` MUST Rule 7 — temp file + fsync + `os.replace`.
- Restrictive permissions per Rule 6 — `chmod 0o600` after write (POSIX).
- `__del__` emits `ResourceWarning` (does NOT call `lock()` — finalizer/event-loop deadlock per `rules/patterns.md` § Async Resource Cleanup).

**Test coverage**: `tests/tier1/test_trust_vault_lifecycle.py` (25 cases, 8 classes): `TestConstructionDefaults` (3 — default TTL = 15min; positive TTL required; sealed initial state); `TestCreate` (3 — write+seal, refuse-overwrite, reject-empty-passphrase); `TestUnlock` (5 — correct passphrase, wrong passphrase, missing file, idempotency, empty passphrase); `TestReadWriteGuards` (3 — sealed-vault read/write raise, round-trip); `TestLock` (3 — seal, idempotency, master-key zeroize); `TestIdleLock` (2 — auto-lock fires, activity resets timer); `TestUnlockedContextManager` (2 — unlock-on-entry/lock-on-exit, lock-on-exception); `TestFileFormatIntegrity` (3 — truncation, magic-byte corruption, ciphertext byte-flip); `TestArgon2ParameterStrictMatch` (1 — non-canonical params rejected).

**Verification gate**: pytest tier1+regression `117 passed in 6.76s`; **zero collection errors; zero warnings**.

**Out of T-01-13 scope** (Phase 02+ shards):

- Secure-Enclave / TPM-bound secret XOR (per spec § Encryption — needs platform-specific work; Phase 02).
- Per-region HKDF-SHA-256 keys (Phase 02 — Phase 01 ships single-region).
- Padding buckets {1, 4, 16, 64} MiB indistinguishability (Phase 04).
- Duress passphrase + honeypot Genesis (Phase 04).
- Hidden envelope + shadow segment (Phase 04).
- `envoy vault destroy-keys` CLI for T-042 mitigation (Phase 02).
- Integration with TrustStoreAdapter (T-01-16 Tier 2 wiring will route SQLite paths through the vault region).

inspect.signature methodology applied — `argon2.low_level.hash_secret_raw` + `cryptography.hazmat.primitives.ciphers.aead.AESGCM.{encrypt,decrypt}` signatures verified against current installed versions before writing code.

---

## T-01-14 — Build envoy/trust/cascade + algorithm_id helpers

**Implements:** `specs/trust-lineage.md` § Cascade revocation + § Algorithm identifiers

**Source:** Shard `01-analysis/05-trust-store-implementation.md` § 4 steps 4-5.

**Steps:**

1. Cascade revocation glue — wraps `kailash.trust.revocation.cascade.cascade_revoke`; `verify_cascade_complete` for EC-8 (cross-channel cascade Day-1 → Day-6 child).
2. Algorithm-identifier helper + Shamir export hooks — `_with_algorithm_id` single-point; `export_master_key_for_shamir` / `import_master_key_from_shamir`.

**Capacity check:** ~150 LOC; 3 invariants (cascade BFS reaches every descendant; verify_cascade_complete contract; algorithm_id single-point routing); 3 call-graph hops. Within budget.

**Blocks on:** T-01-12 + T-01-13.

**Estimate:** 0.5 session.

## Verification — T-01-14

Status: SHIPPED 2026-05-06. Commit (per-todo cadence on `feat/phase-01-wave-1-t-01-14`).

- `envoy/trust/store.py` adds `revoke(*, agent_id, reason, revoked_by)` (cascade revocation wrapper around `kailash.trust.revocation.cascade.cascade_revoke`) + `verify_cascade_complete(*, agent_id)` (EC-8 cross-channel cascade defense; raises `CascadeIncompleteError` on gap, `RevocationNotFoundError` on cache miss). Phase 01 caches `RevocationResult` per `agent_id` in `_last_revocations: dict[str, RevocationResult]`; T-01-17 (Ledger persistence) replaces with persisted `RevocationRecord` rows.
- Algorithm-identifier helper (`_with_algorithm_id` + `_to_spec_wire_form`) was already shipped in T-01-15 (R2-H-01 wire-form translator); T-01-14 step 5 was a no-op for that sub-step.
- `envoy/trust/vault.py` adds Shamir hooks per shard 5 § 4 step 6: `await vault.export_master_key_for_shamir() -> bytes` (returns 32-byte master key copy; vault MUST be unlocked) + `await vault.import_master_key_from_shamir(reconstructed: bytes) -> None` (installs reconstructed 32-byte key; vault MUST be sealed; AES-GCM tag check on decrypt — wrong key bytes raise `VaultUnlockFailedError`, vault stays sealed).
- New typed errors in `envoy/trust/errors.py`: `RevocationError` (base), `RevocationNotFoundError`, `CascadeIncompleteError`, `MasterKeySizeError`. Backwards-compatible — existing error hierarchy unchanged.
- inspect.signature sweep clean on `kailash.trust.revocation.cascade.cascade_revoke` (verified 6-arg signature with broadcaster + delegation_registry as `Optional` defaults — Phase 01 narrow scope passes None for both, kailash uses internal defaults).

**Test coverage**: `tests/tier1/test_trust_cascade_and_shamir.py` (20 cases / 5 classes): `TestRevokeWrapper` (4 unsafe-shape parametric + 1 unsafe-revoked_by + 3 contract — idempotent no-op, cache, re-revoke); `TestVerifyCascadeComplete` (4 — return-True on cached, RevocationNotFoundError on unknown, unsafe-id rejection, per-agent_id cache lookup); `TestShamirExport` (3 — 32-byte size, independent copy semantics, unlocked-vault precondition); `TestShamirImport` (5 — round-trip, wrong-size rejection, wrong-bytes rejection, sealed-vault precondition, missing-file FileNotFoundError).

**Verification gate**: pytest tier1+regression `141 passed in 9.71s`; zero collection errors; zero warnings.

**Out of T-01-14 scope** (later shards):

- Tier 2 wiring with real Genesis chain + real cascade BFS verification (T-01-16).
- Persisted RevocationRecord rows + Ledger entry per cascade (T-01-17).
- Shamir m-of-n splitting + recovery ritual (T-15 ShamirRitualCoordinator, Wave 2).
- Cross-SDK BFS/DFS parity test (kailash-py BFS vs kailash-rs DFS) is a Tier 3 e2e gate, not T-01-14 scope.

---

## T-01-15 — Build envoy/trust/algorithm_id wire-form translator (R2-H-01 LOAD-BEARING)

**Implements:** R2-H-01 fix per `04-validate/round-2-implementation-comprehensive.md` + `journal/0004` Pattern 3.

**Source:** Shard `01-analysis/05-trust-store-implementation.md` § 4 step 5a.

**Action:** Implement `TrustStoreAdapter._to_spec_wire_form(algorithm_dict)` translation helper. EVERY record-construction path routes through `_with_algorithm_id()` which routes through `_to_spec_wire_form()` before write, translating upstream's 1-key `{"algorithm": "ed25519+sha256"}` form into spec-mandated 3-key `{"sig", "hash", "shamir"}` form per `specs/trust-lineage.md` L24.

**LOAD-BEARING:** This MUST land BEFORE any record-persistence path lights up (per `.session-notes` § Traps). If T-01-17 (Ledger persistence) lands first, every persisted record carries the wrong wire form and the verifier will reject every entry.

**Tests added:** `tests/regression/test_r2_h_01_algorithm_id_wire_form.py` (producer-verifier round-trip; 3-key form on disk).

**Capacity check:** ~80 LOC translator + test; 2 invariants (spec wire shape; round-trip byte-identity); 2 call-graph hops. Within budget.

**Blocks on:** T-01-12.
**Blocks:** T-01-17 (Ledger persistence) + T-01-18 (Ledger facade).

**Estimate:** 0.25 session.

## Verification — T-01-15

Status: SHIPPED 2026-05-06. Commit (per-todo cadence on `feat/phase-01-wave-1-foundation`).

- `envoy/trust/store.py` adds `_to_spec_wire_form(algorithm_dict) -> dict` (pure translator, splits upstream's `<sig>+<hash>` compound on `+`, pins shamir to `slip39`) + `_with_algorithm_id(record_dict) -> dict` (single bottleneck, returns NEW dict per gate-review M-01 immutability contract). Helper is current-orphan with 5-commit grace until T-01-17 wires production consumers.
- `kailash.trust.signing.algorithm_id.AlgorithmIdentifier()` import added; `inspect.signature` sweep confirms upstream signatures match shard 5 § 4 step 5a citations exactly (no async deviation, no constructor-arg drift). See `journal/0010`.
- `tests/regression/test_r2_h_01_algorithm_id_wire_form.py` (14 cases, 3 classes): `TestToSpecWireForm` (6); `TestWithAlgorithmId` (5 — including new immutability test added per gate-review M-01); `TestProducerVerifierRoundTrip` (3).
- `tests/regression/test_h01_principal_id_path_traversal_safety.py` (19 cases, 2 classes): added per security-review H-01 — covers 11 unsafe-shape rejections + 7 safe-shape acceptances (Phase 01 pseudonyms with `@`, `.`, `+`) + 2 length-cap boundary tests. Backed by envoy-side `_validate_id_safety` helper that allows real-world principal_pseudonyms while blocking `..` / `/` / `\\x00` / control chars / leading `.` / over-length.
- Shard-budget actual: ~120 LOC translator+validator+helpers + ~300 LOC tests; within ≤500 LOC + ≤5 invariants + ≤3 call-graph hops.

**Verification gate**: pytest tier1+regression `90 passed in 0.22s`; zero collection errors; zero warnings.

**Gate-review fixes applied in same shard** (per `rules/autonomous-execution.md` MUST Rule 4):

- H-01 (security HIGH): path-traversal validation on every public boundary — `__init__`, `seed_genesis`, `record_delegation`, `get_chain` — using envoy-side `_validate_id_safety` that allows Phase 01 pseudonyms (`alice@example`, `agent.42+ci`) while rejecting `../`, `/`, `\\x00`, control chars, and over-length shapes.
- M-01 (security MEDIUM): `_with_algorithm_id` is non-mutating; returns a new dict; immutability regression test added.
- M-02 (security MEDIUM): `close()` zeroizes `_keys` dict on the InMemoryKeyManager (defensive — minimizes private-key residency window pre-T-01-13 vault container).
- M-03 (security MEDIUM): `_register_phase01` renamed via name-mangling to `__register_phase01_only` (private to `_InMemoryAuthorityRegistry`); call site uses the mangled attribute access; runtime check verifies the registry type before dispatch.
- HIGH-1 (review): spec citation drift corrected — `independent-verifier.md L35` documents the 4-key segment-boundary form; `trust-lineage.md L24` is the sole authority for the 3-key trust-lineage on-wire form. Citations updated in store.py docstring + regression test docstrings.
- MEDIUM-2 (review): `chain.py:523` line citation fixed to `chain.py::GenesisRecord (line 148)` (file:symbol form).
- L-02 (security LOW): `__import__` runtime resolution in `compiler.py::_fold_templates` replaced with module-scope `from envoy.envelope.types import ImportedConstraint`.

**Out-of-shard, follow-up todo filed**: L-03 frozen-dataclass invariants on the 5 dimension dataclasses + `EnvelopeMetadata` + `SemanticChecks`. Significant refactor (changes EnvelopeCompiler.compile() flow + requires `object.__setattr__` in `__post_init__` for dimension dimensions); deserves its own shard budget. Tracked in `12-followup-l03-frozen-dimension-dataclasses.md`.

---

## T-01-16 — Wire envoy/trust/ (Tier 2)

**Implements:** `rules/facade-manager-detection.md` Rule 1 (Tier 2 wiring through facade).

**Action:** `tests/tier2/test_trust_store_adapter_wiring.py` (~8 cases per shard 5 § 6.1) + R2-H-01 producer-verifier wire-shape round-trip regression test + `tests/tier2/test_principal_required_error_strict_mode.py` (R1-M-04).

**Acceptance:** All green against real SQLite + real Argon2id timing + real Ed25519 keypair. NO mocking.

**Blocks on:** T-01-12 through T-01-15.

**Estimate:** 0.5 session.

---

## T-01-17 — Build envoy/ledger/types + canonical_json + hash_chain

**Implements:** `specs/ledger.md` + `specs/ledger-merge.md`

**Source:** Build seq § Wave 1 #envoy.ledger; shard `01-analysis/06-envoy-ledger-implementation.md` § 4 steps 1-2.

**Steps:**

1. Skeleton + entry types — 35 dataclasses transcribed from `specs/ledger.md` lines 47-91. 8 typed errors. `EntryEnvelope` frozen dataclass.
2. Canonical JSON + hash chain — `canonical_dumps()` matching `#757`/`#756`/`#731` byte pinning. `HashChainBuilder.build()` pure function.

**Tests added:** `tests/tier1/test_ledger_canonical_dumps_byte_pinning.py`; `tests/tier1/test_format_record_id_for_event.py`.

**Capacity check:** ~400 LOC; 7 invariants (35-dataclass schema; canonical-JSON byte pin; #757 timestamp normalization; #756 input dict ordering; #731 numeric-format pin; hash chain shape; entry-envelope freezing); 2 call-graph hops. Within budget.

**Blocks on:** T-01-15 (algorithm_id wire form must exist).

**Estimate:** 1 session.

## Verification — T-01-17

Status: SHIPPED 2026-05-06. Commit (per-todo cadence on `feat/phase-01-wave-1-t-01-17`).

- `envoy/ledger/__init__.py` exports the public surface (15 symbols: 9 errors + 6 dataclasses/builders + 2 canonical-JSON entry points).
- `envoy/ledger/lamport.py` (~75 LOC): `LamportClock` frozen dataclass with `__post_init__` shape validation + `to_dict`/`from_dict` for canonical-JSON round-trip.
- `envoy/ledger/canonical.py` (~170 LOC): `canonical_dumps(obj) -> bytes` pure function applying all 7 byte-pinning invariants + `CanonicalJsonEncoder` streaming variant. Recursive `_normalize` transform (str→NFC, datetime→microsecond-padded UTC ISO 8601, date→isoformat, bytes→hex, dict/list→recurse, float→TypeError per spec int-only). `_format_timestamp` enforces 27-char `YYYY-MM-DDTHH:MM:SS.NNNNNNZ` shape per #731.
- `envoy/ledger/hash_chain.py` (~210 LOC): `EntryEnvelope` frozen dataclass with 14-field schema + `__post_init__` shape validation (sha256: prefix, sequence ≥ 0, schema_version pin, **3-key algorithm_identifier enforcement** per T-01-15 R2-H-01 inheritance) + `HashChainBuilder` with `build_unsigned()` (pure-function entry_id derivation via `sha256(canonical_dumps(envelope_without_signature))`) + `seal()` (assembles final envelope post-signing).
- `envoy/ledger/head.py` (~135 LOC): `HeadCommitment` (head_sequence + head_entry_id + signed_at + signature_hex; defends T-100 rollback) + `HaltedByRollbackRecord` (forensic record for the 3 detection reasons: sequence_decrease / head_signature_mismatch / algorithm_identifier_downgrade).
- `envoy/ledger/errors.py` (~120 LOC): `LedgerError` base + 8 typed errors per spec § Error taxonomy (LedgerHaltedError, LedgerRollbackDetectedError, LedgerVerificationFailedError, LedgerSyncConflictError, LedgerConflictFloodError, EntryKeyDestroyedError, PhaseAOrphanDetectedError, LedgerAlgorithmMismatchError).

**Test coverage**: `tests/tier1/test_ledger_canonical_dumps_byte_pinning.py` (40 cases / 11 classes) — covers all 7 byte-pinning invariants + EntryEnvelope/LamportClock/HeadCommitment shape validation + HashChainBuilder determinism + 3-key algorithm_identifier enforcement. `tests/tier1/test_format_record_id_for_event.py` (7 cases / 4 classes) — verifies the kailash-py helper symbol is callable + produces stable output for the no-policy path (the Phase 01 narrow surface; T-01-18 wires the policy-aware path).

**Verification gate**: pytest tier1+regression `191 passed in 11.41s`; zero collection errors; zero warnings.

**Out of T-01-17 scope** (T-01-18 + later shards):

- `EnvoyLedger` facade with `append/query/verify_chain/head_commitment/export` (T-01-18).
- Atomic transaction wrapping (`df.transaction()` boundary around sign + audit_store.append + head.update) (T-01-18).
- Two-phase signing (PhaseARecord + PhaseBRecord) wired through runtime (Wave 3 Grant Moment).
- CRDT merge protocol (Wave 2+ via `specs/ledger-merge.md`).
- Per-region HKDF-derived per-entry encryption keys + tombstones (Phase 02).
- Per-type Content schema dataclasses for entry types owned at the Ledger layer (lands when each consumer primitive ships).

inspect.signature methodology applied — `dataflow.classification.event_payload.format_record_id_for_event` signature verified against current installed kailash version before writing the test.

---

## T-01-18 — Build envoy/ledger/facade + atomic transaction + head_commitment + two_phase

**Source:** Shard 6 § 4 steps 3-5.

**Steps:**

1. `EnvoyLedger.append()` facade + atomic transaction — wraps upstream `AuditStore` inside `df.transaction()` (post-#707/#711). Single-point filter at emitter routes `record_id` through `format_record_id_for_event` (per `rules/event-payload-classification.md`).
2. HeadCommitment monotonic guard + `HaltedByRollback` — rollback emits halt entry BEFORE refusing further writes.
3. Two-phase signing + orphan resolution — `PhaseARecord` / `PhaseBRecord` linked by `intent_id`; 30-day TTL orphan sweep at session start.

**Capacity check:** ~350 LOC; 6 invariants (atomicity; head-commitment monotonic; halt-before-refuse; phase-A/B linkage; TTL sweep correctness; emitter single-point filter); 3 call-graph hops. Within budget.

**Blocks on:** T-01-17.

**Estimate:** 1 session.

---

## T-01-19 — Build envoy/ledger/export

**Implements:** `specs/ledger.md` § Export bundle + `specs/independent-verifier.md` § Bundle format

**Source:** Shard 6 § 4 step 6.

**Action:** `envoy ledger export --format json|pdf` produces signed bundle for shard 7 verifier. Bundle includes Genesis Record, full chain, segment-boundary algorithm identifiers, trust anchor.

**Tests added:** `tests/tier2/test_envoy_ledger_export_round_trip.py`.

**Capacity check:** ~200 LOC; 3 invariants (bundle schema; signature over bundle; segment-boundary identifier shape); 2 call-graph hops. Within budget.

**Blocks on:** T-01-17 + T-01-18.

**Estimate:** 0.5 session.

---

## T-01-20 — Build envoy/ledger/segment_boundary 4-key serializer (R3-M-02)

**Implements:** R3-M-02 carry-forward; `specs/independent-verifier.md` L35 4-key form.

**Action:** Extend export-bundle serializer to produce 4-key `algorithm_identifier` at segment boundaries per `specs/independent-verifier.md` L35: `{"sig": "ed25519", "hash": "sha256", "shamir": "slip39", "canonical_json": "jcs-rfc8785"}`.

**Why:** Phase 01 verifier's segment-boundary contract mandates the 4-key form (the `canonical_json` key documents JCS-RFC-8785 which the verifier must validate against). Shard 6's existing 3-key form is a producer bug.

**Tests added:** `tests/tier2/test_envoy_ledger_segment_boundary.py` — asserts 4-key form on every segment-boundary entry.

**Capacity check:** ~50 LOC; 1 invariant (4-key shape); 1 call-graph hop. Within budget.

**Blocks on:** T-01-19.

**Estimate:** 0.25 session.

---

## T-01-21 — Wire envoy/ledger/ (Tier 2)

**Action:** Per `02-plans/03-package-skeleton.md` § 3 Tier 2 list — 11 wiring tests covering facade + crypto round-trip + atomic-append-under-failure + head-commitment-monotonic + phase-A/B-intent-id-link + canonical-JSON-byte-identity + export-round-trip + classification-policy-redaction.

**Files:**

- `tests/tier2/test_envoy_ledger_wiring.py`
- `tests/tier2/test_envoy_ledger_crypto_round_trip.py` (per `rules/orphan-detection.md` Rule 2a)
- `tests/tier2/test_envoy_ledger_atomic_append_under_failure.py`
- `tests/tier2/test_envoy_ledger_head_commitment_monotonic.py`
- `tests/tier2/test_envoy_ledger_phase_a_b_intent_id_link.py`
- `tests/tier2/test_envoy_ledger_canonical_json_byte_identity.py`
- `tests/tier2/test_envoy_ledger_query_filter_principal_id.py` (R1-M-04 tenant-isolation)

**Acceptance:** All green against real SQLite. NO mocking.

**Blocks on:** T-01-17 through T-01-20.

**Estimate:** 1 session.

---

## T-01-22 — Build envoy/model/router (BYOM picker + Envoy router + risk annotator + response filter)

**Implements:** `specs/model-adapter.md`

**Source:** Build seq § Wave 1 #envoy.model.router; shard `01-analysis/13-model-adapter-implementation.md` § 3.

**Steps:**

1. BYOM picker + .env writer — first-launch CLI; writes `KAILASH_LLM_PROVIDER` + `KAILASH_LLM_DEPLOYMENT`; routes secrets to Connection Vault (NEVER `.env` plaintext).
2. EnvoyModelRouter — wraps `LlmClient.from_env()`; per-primitive override map (`ENVOY_BOUNDARY_MODEL`, `ENVOY_DIGEST_MODEL`, `ENVOY_GRANT_MOMENT_SUMMARY_MODEL`, `ENVOY_DEFAULT_MODEL`).
3. EnvoyProviderRiskAnnotator — preset-name → `ProviderRisk` annotation per spec lines 17-29.
4. Response-filter pipeline (Phase 01 minimum) — token-budget check; leak-canary stub (Phase 04 corpus); goal-drift classifier stub.

**Capacity check:** ~330 LOC; 5 invariants (LlmClient.from_env contract; per-primitive override resolution; risk annotation semantics; response filter chain order; token-budget enforcement); 3 call-graph hops. Within budget.

**Blocks on:** T-01-25 (Connection Vault for secret routing).

**Estimate:** 1 session.

---

## T-01-23 — Wire envoy/model/router (Tier 2) + R1-M-02 chat_async route test

**Action:** `tests/tier2/test_envoy_model_router_wiring.py` — exercises per-primitive override against real LLM (Ollama for CI; real Claude/GPT for staging) + `tests/tier2/test_envoy_model_router_chat_async_routing.py` (R1-M-02) — asserts router routes through `LlmDeployment.chat_async()` per shard 13 § 7.1 HOLD.

**Acceptance:** Both tests green against real Ollama + real provider where staging credentials available. NO mocking.

**Blocks on:** T-01-22.

**Estimate:** 0.5 session.

---

## T-01-24 — Build envoy/connection_vault/ (keyring + per-principal isolation)

**Implements:** `specs/connection-vault.md`

**Source:** Build seq § Wave 1 #envoy.connection_vault; shard `01-analysis/14-connection-vault-implementation.md` § 3.

**Steps:**

1. Adapter + 11-field schema — `envoy/connection_vault/adapter.py`; serializes 11 fields into `keyring.set_password()` 3-tuple via canonical-JSON.
2. Per-principal isolation + envelope-scope enforcement — `principal_genesis_id` keyed; `EnvelopeScopeMismatchError` on get without active scope.
3. `expires_at` + `usage_counter` enforcement — fail-closed defaults; 7 typed errors.
4. `.env` first-run import path — Boundary Conversation reads `.env` and writes Vault; post-onboarding `.env` no longer source of truth.

**Capacity check:** ~280 LOC; 5 invariants (11-field schema; principal_id key; envelope-scope match; lifecycle enforcement; .env one-time import); 2 call-graph hops. Within budget.

**Estimate:** 1 session.

---

## T-01-25 — Wire envoy/connection_vault/ (Tier 2)

**Action:** `tests/tier2/test_connection_vault_adapter_wiring.py` — real `keyring` against macOS Keychain / Linux Secret Service / Windows Credential Manager.

**Acceptance:** All green on each OS; NO mocking. (CI matrix runs all 3.)

**Blocks on:** T-01-24.

**Estimate:** 0.5 session.

---

## T-01-26 — Build envoy/runtime/ (abstract stub + sole kailash_py adapter)

**Implements:** `specs/runtime-abstraction.md`

**Source:** Build seq § Wave 1 #envoy.runtime; shard `01-analysis/18-runtime-abstraction-stub.md`.

**Steps:**

1. Abstract interface contract — Python ABC matching spec; ALL methods declared abstract.
2. `kailash_py` adapter (sole Phase 01 backend) — implements every ABC method by composing the relevant Envoy primitive.
3. Feature-flagged `kailash_rs_bindings` slot — empty module raising `RuntimeBackendNotWired` until Phase 02.

**Capacity check:** ~150 LOC; 3 invariants (every ABC method declared abstract; kailash_py adapter is sole Phase 01 backend; rust slot raises until Phase 02); 2 call-graph hops. Within budget.

**Estimate:** 0.5 session.

---

## T-01-27 — Build envoy/heartbeat/ (5 stubs only — R2-H-02 partition)

**Implements:** R2-H-02 fix per `04-validate/round-2-implementation-comprehensive.md`; shard 17 § 7.3.

**Source:** Shard `01-analysis/17-foundation-health-heartbeat-decision.md` (DE-SCOPED).

**Action:** 5 stubs only:

1. `envoy/heartbeat/client.py` — `HeartbeatClient.maybe_record_flag()` no-op invoked by 21 emit-site primitives. Genuine Phase 01 hot-path consumer.
2. `envoy/heartbeat/star_prio.py` — `PhaseDeferredError` stub. Phase 01 production code MUST NEVER call.
3. `envoy/heartbeat/ohttp.py` — `PhaseDeferredError` stub.
4. `envoy/heartbeat/signed_consent.py` — `PhaseDeferredError` stub.
5. `envoy/heartbeat/registry.py` — `PhaseDeferredError` stub.

**LOAD-BEARING:** R2-H-02 partition prevents the stub-and-deferred-test mismatch from `rules/orphan-detection.md` Rule 4a. Regression grep MUST verify zero non-test imports of the four `PhaseDeferredError` modules.

**Tests added:** `tests/regression/test_r2_h_02_heartbeat_stub_partition.py` — asserts `client.maybe_record_flag` is invoked by ≥21 emit sites; asserts zero production imports of the 4 deferred modules.

**Capacity check:** ~100 LOC stubs + 1 regression test; 2 invariants (no-op client; deferred-modules unreachable from production); 1 call-graph hop. Within budget.

**Estimate:** 0.25 session.

---

## Wave 1 milestone gate

Per `02-plans/01-build-sequence.md` § 3 Milestone 1, Wave 1 converges when:

1. Every Wave 1 primitive's Tier 2 wiring test green.
2. `tests/tier3/test_envoy_ledger_cross_os_byte_identity.py` — 3-OS matrix produces byte-identical canonical export. (Parallel to wave; runs once Wave 1 done.)
3. `tests/tier2/test_envelope_compiler_intersect_through_kailash_py.py` — round-trip with upstream `intersect_envelopes` byte-equal.
4. `tests/tier2/test_trust_store_adapter_genesis_round_trip.py` — Genesis seeded; verified by `verify_signature`.

**Wall-clock estimate:** ~2 sessions parallel (Trust store + Ledger are the bottleneck at 2 sessions each; rest run in parallel worktrees).

---

## Cross-references

- Build sequence: `02-plans/01-build-sequence.md` § Wave 1
- Package skeleton: `02-plans/03-package-skeleton.md` § 2 (envelope, trust, ledger, model, connection_vault, runtime, heartbeat)
- Primitive shards: `01-analysis/{04,05,06,13,14,17,18}-*-implementation.md`
- Orphan/facade rules: `.claude/rules/orphan-detection.md`, `.claude/rules/facade-manager-detection.md`
- Tenant-isolation rule: `.claude/rules/tenant-isolation.md`
- Event payload classification: `.claude/rules/event-payload-classification.md`
- DataFlow identifier safety: `.claude/rules/dataflow-identifier-safety.md`
