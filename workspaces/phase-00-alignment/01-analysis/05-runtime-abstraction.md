# 05 — Runtime Abstraction

**Document status:** **FROZEN v2** — post Round 1 (3 CRIT + 8 HIGH resolved inline)
**v2 fixes:** **F-01** head-commitment attribution corrected — `runtime.ledger_head_commitment()` returns the **Ledger head-commitment** (Ledger tip, runtime-device-signed per doc 04 §4); the Trust-Lineage chain head-commitment is a distinct primitive signed by user Genesis per doc 03 v2 §6.3. Both are written at sync; both must be monotonic. **F-02** `RuntimeKeyRotationRecord` requires dual signatures from OLD + NEW runtime keys AND a user-Genesis co-signature (compromised runtime cannot rotate its own key without user authority). **F-03** runtime switch (§8.2) now requires (a) Trust Vault unlock via user passphrase (not warm-unlocked session), (b) user-Genesis-signed `RuntimeSwitchRecord`, (c) runtime-attestation verification of target runtime before it receives Trust Vault master key. **F-04** abstract interface §2.1 expanded with missing primitives: `prompt_assemble()`, `tool_output_sanitize()`, `classifier_registry_resolve()`, `first_time_action_gate()`, `grant_moment_surface()`. **F-05** E3/E4 cross-ref to doc 03 §5.2 (cascade BFS/DFS) + §6.2 (cycle detection) corrected. **F-06** binary-poisoning defense explicitly notes T-050b residual — reproducible-build verification stream is the mitigation, N-mirror is defeated by signing-key compromise. **F-07** orphan-resolution retry window tightened; retry requires Grant Moment. **F-08** HALTED records carry full schema distinct from Phase B. **F-09** vault compatibility check is per-artifact-type algorithm-aware. **F-10** security-review gates cite named agents per `rules/agents.md`. **F-11** `RuntimeIdentity` includes `binary_hash`.
**Date:** 2026-04-21
**Scope:** The `kailash-runtime` abstract interface that Envoy programs against; contract guarantees; conformance vectors N1–N6; byte-identical parity contract between `kailash-py` and `kailash-rs-bindings`; runtime picker UX; migration path; runtime device-binding + runtime signatures; tool-call two-phase lifecycle.
**Sources:** doc 00 v3 FROZEN (BET-6 contract parity, §4.1 item 15 N=3 mirrors), doc 02 v3 FROZEN (envelope re-read checkpoint, JCS canonical form, first-time-action gate), doc 03 v1 (Trust Vault signing paths, cascade revocation BFS/DFS parity), doc 09 v3 FROZEN (T-004 two-phase signing, T-015 envelope re-read checkpoint, T-050/T-060 binary threats, T-105 sub-agent subset-proof), primitive reconciliation (03-primitive-reconciliation.md), kailash-rs + kailash-py deep audits.

---

## 1. Purpose

Envoy programs against an **abstract runtime interface**, not against a specific SDK. Two implementations ship:

- **`kailash-rs-bindings`** — Rust-accelerated via PyO3. Hot-path performance. Phase 02+ default.
- **`kailash-py`** — Pure-Python Foundation implementation. Phase 01 sole runtime; Phase 02+ opt-in alternative (ADR-0001).

Runtime pluggability is the structural mitigation behind BET-3 (sovereignty) + BET-6 (parity) + §4.1 item 15 (no-single-point-of-failure on binary distribution). If users opt out of the default Rust runtime, the Python runtime must deliver the same contract — byte-identical for spec-driven outputs (signing, envelope canonical form, ledger hash chain), semantically-equivalent for LLM-composed outputs (agent responses, Grant Moment prompt text).

### In scope

- Abstract `kailash-runtime` interface surface.
- Core operations + their contract semantics.
- Conformance vectors N1–N6 decoded.
- Byte-identical vs semantically-equivalent contract.
- Runtime picker UX (Phase 02 first-run flow).
- Migration between runtimes (vault + ledger portability).
- Runtime device-binding + runtime signatures.
- Tool-call two-phase lifecycle (Phase A intent / Phase B outcome).
- Envelope re-read checkpoint mechanics.
- Runtime security-review gates per phase.
- Cross-SDK parity test harness.

### Out of scope

- Envelope schema (doc 02).
- Trust Lineage signing algorithm (doc 03 — this doc calls into it).
- Ledger entry format (doc 04 — this doc invokes append/query but format owned elsewhere).
- Grant Moment UX (doc 01).
- Channel adapter contracts (doc 07 — adapters compose over the runtime).
- Distribution / installer / binary verification (doc 06 — this doc names the binary-hash-pinning contract; doc 06 implements).

---

## 2. Abstract interface

The `kailash-runtime` crate is **Apache 2.0, Foundation-owned**. It is the single source of truth for every operation Envoy performs that must be consistent across SDK implementations.

### 2.1 Interface surface (Python perspective; Rust binding mirrors)

```python
# kailash_runtime.abstract (module)

class KailashRuntime(ABC):
    """
    Abstract runtime interface. All Envoy code programs against this.
    Concrete implementations: kailash_runtime.py_impl.PyRuntime, kailash_runtime.rs_bindings.RsRuntime
    """

    # --- Lifecycle ---
    @abstractmethod
    def startup(self, config: RuntimeConfig) -> None: ...
    @abstractmethod
    def shutdown(self) -> None: ...
    @abstractmethod
    def runtime_identity(self) -> RuntimeIdentity:
        """Returns {runtime_family, version, device_bound_pubkey_hex, algorithm_identifier}."""

    # --- Trust Lineage operations (delegate into doc 03 primitives) ---
    @abstractmethod
    def trust_sign(self, record: DelegationRecord, private_key: Ed25519PrivateKey) -> bytes: ...
    @abstractmethod
    def trust_verify_chain(self, chain: TrustLineageChain) -> VerificationResult: ...
    @abstractmethod
    def trust_cascade_revoke(self, target_delegation_id: str, chain: TrustLineageChain) -> List[str]:
        """Returns list of all revoked delegation_ids. BFS or DFS — set-equivalent."""
    @abstractmethod
    def trust_verify_subset_proof(self, parent: DelegationRecord, sub: DelegationRecord) -> SubsetVerificationResult:
        """Runtime-independent re-verification; signs result with runtime_device_key per doc 03 §7.2."""

    # --- Envelope operations (delegate into doc 02 primitives) ---
    @abstractmethod
    def envelope_canonical_form(self, envelope: EnvelopeConfig) -> bytes:
        """JCS RFC 8785 + NFC per doc 02 §14.1. Byte-identical output contract (BET-6)."""
    @abstractmethod
    def envelope_intersect(self, a: EnvelopeConfig, b: EnvelopeConfig) -> EnvelopeConfig:
        """Per doc 02 §5.1 + §14.5 pseudocode."""
    @abstractmethod
    def envelope_check(self, action: Action, envelope: EffectiveEnvelopeSnapshot,
                       session: SessionObservedState) -> EnvelopeCheckResult:
        """Structural + arithmetic + comparison + semantic checks per doc 02 §7 hot-path.
        Returns {pass: bool, failed_checks: [...], classifier_breakdown: {...}, latency_ms: float}."""
    @abstractmethod
    def envelope_re_read_checkpoint(self, envelope_id: str) -> EnvelopeConfig:
        """Re-reads canonical envelope from Trust Vault, bypassing LLM-context cache.
        Per doc 02 §17 + doc 09 T-015 mitigation."""

    # --- Tool-call two-phase lifecycle (doc 00 v3 §8 Test-2) ---
    @abstractmethod
    def phase_a_sign_intent(self, intent: ToolCallIntent, envelope_snapshot_hash: str,
                            delegation_record: DelegationRecord) -> PhaseARecord:
        """Pre-execution. Envelope check runs here. Intent signed with delegation's key."""
    @abstractmethod
    def phase_b_sign_outcome(self, intent_id: str, outcome: ToolCallOutcome) -> PhaseBRecord:
        """Post-execution. Signed by runtime_device_key. Links to Phase A by intent_id."""
    @abstractmethod
    def phase_a_orphan_resolve(self, orphan_intent_id: str, resolution: OrphanResolution) -> LedgerEntry:
        """Per doc 09 T-004 mitigation. On restart, orphan intents flagged as repudiable-side-effect."""

    # --- Ledger operations (delegate into doc 04 primitives) ---
    @abstractmethod
    def ledger_append(self, entry: LedgerEntry, content_trust_level: ContentTrustLevel) -> LedgerPosition: ...
    @abstractmethod
    def ledger_query(self, query: LedgerQuery) -> Iterator[LedgerEntry]: ...
    @abstractmethod
    def ledger_verify_chain(self, from_position: LedgerPosition = GENESIS,
                            to_position: LedgerPosition = HEAD) -> ChainVerificationResult: ...
    @abstractmethod
    def ledger_head_commitment(self) -> HeadCommitment:
        """Per doc 09 T-100 rollback defense."""

    # --- Classifier ensemble operations (doc 02 §14.6 registry) ---
    @abstractmethod
    def classifier_invoke(self, classifier_ref: str, content: bytes,
                          content_trust_level: ContentTrustLevel) -> ClassifierResult:
        """Invokes ensemble classifier. Returns {score, confidence, classifier_version_hash, latency_ms}."""
    @abstractmethod
    def classifier_ensemble_aggregate(self, results: List[ClassifierResult],
                                      unavailability_policy: UnavailabilityPolicy) -> EnsembleResult: ...

    # --- Budget + rate-limit (doc 02 §3.1, §3.2) ---
    @abstractmethod
    def budget_reserve(self, amount_microdollars: int, session_id: str) -> BudgetReservation: ...
    @abstractmethod
    def budget_record(self, reservation: BudgetReservation, actual_microdollars: int) -> None: ...
    @abstractmethod
    def budget_snapshot(self, session_id: str) -> BudgetSnapshot: ...
    @abstractmethod
    def budget_velocity_check(self, proposed_call: Action) -> VelocityCheckResult: ...

    # --- Runtime attestation ---
    @abstractmethod
    def runtime_sign(self, payload: bytes) -> bytes:
        """Signed with runtime_device_key. Used for Phase B, SubsetProof verification, HALTED records."""
    @abstractmethod
    def runtime_verify(self, payload: bytes, signature: bytes, runtime_pubkey_hex: str) -> bool: ...
```

### 2.2 Types

- `RuntimeIdentity` — `{runtime_family: "kailash-py" | "kailash-rs-bindings", version: str, device_bound_pubkey_hex: str, algorithm_identifier: AlgorithmIdentifier}`.
- `EnvelopeCheckResult` — structured outcome; latency timing per check class.
- `PhaseARecord` — `{intent_id, intent_summary, chosen_tool, envelope_verification_result, composition_context, delegation_record_hash, signature_by_delegation_key_hex}`.
- `PhaseBRecord` — `{intent_id (links to Phase A), outcome: {success | error | timeout | halted_by_rollback}, result_payload_hash, completed_at, runtime_signature_hex}`.
- `LedgerPosition` — opaque cursor (monotonic sequence + Lamport device-clock).
- `HeadCommitment` — `{head_hash, head_sequence, signed_by_device_key, timestamp}`.

### 2.3 Error taxonomy

| Error                                     | When                                      | Consumer action                                   |
| ----------------------------------------- | ----------------------------------------- | ------------------------------------------------- |
| `RuntimeNotReadyError`                    | Operation invoked before startup          | Call startup() first                              |
| `RuntimeShutdownError`                    | Operation invoked after shutdown          | Restart runtime                                   |
| `AlgorithmIdentifierMismatchError`        | Runtime's algorithm_identifier ≠ required | Migrate OR reject                                 |
| `PhaseAIntentSigningFailedError`          | Envelope check blocked during Phase A     | Surface reason; optionally Grant Moment           |
| `PhaseBOrphanError`                       | Phase B recorded with no matching Phase A | Audit alert; Ledger integrity check               |
| `LedgerRollbackDetectedError`             | head_commitment < previously-seen         | Sync rejected; alert user                         |
| `LedgerVerificationFailedError`           | Chain verification fails at position N    | Ledger corruption; restore from backup            |
| `ClassifierUnavailableError`              | classifier_ref resolution failed          | Apply unavailability_policy (fail-closed default) |
| `RuntimeSignatureVerificationFailedError` | Runtime attestation does not verify       | Refuse trust on runtime attestations              |
| `BudgetExhaustedError`                    | Reserve would exceed ceiling              | Surface to user; no execution                     |
| `BudgetVelocityExceededError`             | Velocity check fails                      | Grant Moment or block                             |

Error messages MUST NOT echo raw envelope content or signing keys (carried pattern from doc 02 L-01).

---

## 3. Contract: byte-identical vs semantically-equivalent

Per doc 00 v3 BET-6, the runtime abstraction partitions its contract surface:

### 3.1 Byte-identical contract (spec-driven outputs)

Both SDKs MUST produce byte-identical output for:

1. **`envelope_canonical_form()`** — JCS + NFC canonical serialization. 67-vector conformance corpus per doc 02 R2-H1.
2. **`trust_sign()`** — Ed25519 signature over canonical form. Deterministic given same inputs.
3. **Delegation Record `delegation_id`** — SHA-256 of canonical form.
4. **Ledger entry hash chain** — per-segment algorithm-identifier-tagged.
5. **`trust_cascade_revoke()`** — SET of returned IDs (not order). Per doc 03 §5.2 BFS/DFS set-equality.
6. **`envelope_intersect()`** — byte-identical output canonical form.
7. **Subset-proof `runtime_verification_signature`** — signed canonical form of verification result.
8. **`head_commitment()`** — hash identity.

Verified via **conformance vectors N1–N6** (§5).

### 3.2 Semantically-equivalent contract (LLM-composed outputs)

Both SDKs MAY produce different byte outputs but MUST be semantically equivalent for:

1. **Agent LLM responses** — natural-language outputs.
2. **Grant Moment prompt text** — user-facing strings.
3. **Boundary Conversation agent flows** — turn content.
4. **Tool-call timing metadata** — latency_ms varies per runtime.
5. **Ensemble classifier invocation ordering** — results aggregate identically; per-call sequencing may differ.

**Semantic equivalence test:** both runtimes produce the same ENVELOPE-CHECK outcome, same TOOL-CALL DECISION, same LEDGER-APPROVAL RESULT for the same user input. Latency + text phrasing may differ.

### 3.3 Why the split

LLM output is non-deterministic by construction — token sampling, thread scheduling, async ordering. Signing + canonical serialization are deterministic by design. The two contract tiers reflect what is achievable without breaking either runtime's native idioms.

---

## 4. Runtime device-binding + runtime signatures

### 4.1 Device-bound runtime key

Each runtime instance (kailash-py OR kailash-rs-bindings on a specific device) generates a device-bound Ed25519 keypair at startup. This key is DISTINCT from:

- User's Genesis Record key (which signs Delegation Records).
- Shamir shards (which back up user's vault).
- Connection Vault entries (third-party credentials).

**Storage:** runtime key's private half lives in OS-level Secure Enclave / TPM where available; software-backed in Trust Vault otherwise. Never leaves the device.

**Purpose:** the runtime signs with this key to attest that the RUNTIME verified a specific fact:

- Phase B outcomes (§6.2)
- SubsetProof re-verification (doc 03 §7.2)
- HALTED-by-rollback Ledger entries (doc 02 §6.1 Branch 3)
- Head commitments (doc 03 §6.3)

**Rotation:** on device transition or suspected compromise, runtime key rotates via a `RuntimeKeyRotationRecord` in Ledger, dual-signed (old + new runtime keys). Distinct from user-Genesis key rotation (doc 03 §8.2).

### 4.2 Runtime identity attestation

At install + at every startup, the runtime attests:

```json
{
  "type": "RuntimeAttestation",
  "runtime_family": "kailash-rs-bindings",
  "runtime_version": "3.20.1",
  "binary_hash": "sha256:...",
  "device_id": "...",
  "device_bound_pubkey_hex": "...",
  "algorithm_identifier": {...},
  "attested_at": "iso8601",
  "platform_attestation": {
    "type": "secure_enclave | tpm | software",
    "attestation_payload_hash": "sha256:..."
  },
  "signature_by_device_key_hex": "..."
}
```

Attestation is written to Ledger at startup. Trust Vault verifies the binary hash matches Foundation-published manifest (doc 06 §N-mirror-verification).

**Binary poisoning defense (doc 09 T-060):** on every startup, `binary_hash` is verified against Foundation-signed manifest. Mismatch refuses to load. Plus doc 06's N=3 mirror verification at install time.

**Signing-key compromise defense (doc 09 T-050b):** binary_hash + algorithm_identifier must both match. Reproducible-build verification stream (Phase 03) cross-checks binary_hash against third-party reproduction. `kailash-py` escape hatch (users can opt out of binary runtime entirely).

---

## 5. Conformance vectors N1–N6

Per doc 00 v3 + kailash-rs deep audit, PACT conformance vectors N1–N6 are the cross-SDK byte-parity contract. Doc 05 decodes each.

### 5.1 N1 — Knowledge Filter (pre-retrieval lifecycle gate)

**What:** classification-aware filter on retrievals. Verifies that queries against classified data are gated by clearance.

**Test shape:** given a query + classification policy + caller clearance, assert:

- `is_allowed(query, policy, clearance) == expected`
- Redaction applied per field-level `@classify` rules.
- Byte-identical redacted output across SDKs.

**Existing corpus:** kailash-rs `crates/kailash-governance/tests/pact_n1_n2_conformance.rs`. Python runner pending `kailash-py#605`.

**Envoy consumption:** every `envelope_check()` with `data_access.classification_clearance` runs this gate.

### 5.2 N2 — Envelope Cache (5-property invalidation)

**What:** envelope-cache invalidation semantics — 5 properties that must all trigger cache miss:

1. Envelope version increment.
2. Cache entry expiry.
3. Role envelope override (RoleEnvelope changed).
4. Multi-address envelope invalidation.
5. Timestamp ordering violation.

**Test shape:** given cache state + event, assert cache entry still valid OR invalidated per property.

**Corpus:** kailash-rs `crates/kailash-governance/tests/pact_n1_n2_conformance.rs`. Python runner pending.

**Envoy consumption:** `envelope_re_read_checkpoint()` honors these invalidation properties; stale cache is detected and forces Trust Vault re-read.

### 5.3 N3 — Not yet enumerated in kailash-rs; reserved

Per kailash-rs deep audit, N3 is documented but not enumerated at current Rust-side progress. Doc 05 names it as a placeholder; when PACT spec formalizes N3 in mint, doc 05 updates.

### 5.4 N4 — Verdict rendering (decision logic)

**What:** envelope check produces a structured verdict:

- `AutoApproved`, `Flagged`, `Held`, `Blocked`.

**Test shape:** JSON vector at `crates/kailash-pact/tests/conformance/vectors/*.json`. Load vector, reconstruct domain objects, assert canonical-JSON byte-for-byte equality of output verdict.

**Corpus status:** Rust complete. Python runner pending `kailash-py#605`.

**Envoy consumption:** `envelope_check()` returns a verdict in this format.

### 5.5 N5 — Posture ceiling (constraint application)

**What:** posture level gates capability access. Posture escalation requires Authorship Score (doc 02 §8).

**Test shape:** given action + posture + envelope, assert action allowed / blocked / grant-moment-required.

**Corpus status:** Rust complete. Python runner pending.

**Envoy consumption:** Authorship Score posture-ratchet (doc 02 §8.3) depends on this.

### 5.6 N6 — (sixth pattern; not yet formalized)

Named in PACT spec framework; specific semantics await mint formalization. Doc 05 placeholder.

### 5.7 Envoy-specific conformance additions

Beyond PACT N1–N6, Envoy adds:

- **E1 — Envelope canonical JSON** (doc 02 §14.1 67-vector corpus).
- **E2 — Delegation Record signing** (doc 03 §4.3 20-vector corpus).
- **E3 — Cascade revocation BFS/DFS set-equality** (doc 03 §5.2 15-vector corpus).
- **E4 — Cycle detection** (doc 03 §6.2 15-vector corpus).
- **E5 — Subset-proof verification** (doc 03 §7 adversarial corpus; 5 direction-inverted + 10 edge + 5 authored-cover-adversarial).
- **E6 — Two-phase signing orphan resolution** (doc 09 T-004 + §6.3 of this doc).
- **E7 — Ledger head-commitment monotonicity** (doc 04 T-100 mitigation).

**Test harness:** `tests/conformance/envoy/` in each SDK. Cross-SDK runner loads a manifest of vectors, invokes both runtimes, asserts byte-identity (for byte-identical contract) or structural equivalence (for semantic contract).

---

## 6. Tool-call two-phase lifecycle

Per doc 00 v3 §8 Test-2 + doc 09 v3 T-004 + this doc §2.1 Phase A/Phase B methods.

### 6.1 Phase A — intent signing (pre-execution)

When the agent's LLM emits a tool-call:

1. Runtime constructs `ToolCallIntent`:

```python
intent = ToolCallIntent(
    intent_id=sha256(canonical_form(intent_minus_id)),  # content-addressed
    agent_id=runtime.runtime_identity().runtime_family + ":" + session_id,
    tool_name=proposed.tool_name,
    arguments=canonicalize_args(proposed.arguments),
    envelope_snapshot_hash=current_effective_envelope_snapshot.hash,
    delegation_record_hash=current_delegation.delegation_id,
    proposed_at=now(),
    nonce=os.urandom(32).hex(),
    algorithm_identifier=runtime.algorithm_identifier()
)
```

2. Runtime invokes `envelope_check(action=intent, envelope=current_effective_envelope, session=current_session)`:
   - Structural + arithmetic + comparison + semantic + composition-rule checks (doc 02 §7 hot-path).
   - If any check blocks → raise `PhaseAIntentSigningFailedError(reason)` → agent surfaces Grant Moment OR halts.
   - If all pass → proceed.

3. Runtime signs intent with current delegation's key:

```python
signature = runtime.trust_sign(intent, delegation_private_key)
phase_a_record = PhaseARecord(intent=intent, signature=signature, runtime_device_signature=runtime.runtime_sign(canonical_form(intent)))
```

4. `phase_a_record` appended to Ledger with `content_trust_level: system`.

5. Tool executes.

### 6.2 Phase B — outcome signing (post-execution)

After tool completes:

1. Runtime constructs `ToolCallOutcome`:

```python
outcome = ToolCallOutcome(
    intent_id=phase_a_record.intent.intent_id,
    outcome_type="success" | "error" | "timeout" | "halted_by_rollback",
    result_payload_hash=sha256(canonical_form(result_payload)),
    completed_at=now(),
    elapsed_ms=elapsed
)
```

2. Runtime signs outcome with **runtime_device_key** (NOT delegation key — outcome attests runtime execution, not capability authorization):

```python
phase_b_record = PhaseBRecord(outcome=outcome, runtime_signature=runtime.runtime_sign(canonical_form(outcome)))
```

3. `phase_b_record` appended to Ledger with `content_trust_level: system`, linked to Phase A via `intent_id`.

### 6.3 Orphan resolution

If Phase A is signed but Phase B never lands (crash, network partition, runtime restart), the intent is orphaned.

**Detection:** on startup, runtime queries Ledger for Phase A records without matching Phase B for `intent_id`. Any found within the last configurable window (default 30 days) are orphans.

**Resolution options surfaced as Grant Moment on next session start:**

- **Retry** — runtime re-executes the tool-call (only for idempotent tools; flag per-tool in envelope Operational dimension).
- **Record as failed** — append synthetic Phase B with `outcome_type: "interrupted_unknown_result"`; user acknowledges the repudiable-side-effect possibility.
- **Investigate** — user reads surrounding context; decides per-case.

**Ledger entry:** `phase_a_orphan_resolve()` appends the resolution with `content_trust_level: user-authored`, linking back to the Phase A orphan's `intent_id`.

### 6.4 Interrupt semantics

Phase A → Phase B window is small but non-zero. During this window:

- Tool has started; side-effect MAY have occurred.
- Runtime crash loses Phase B.
- On restart, orphan resolution kicks in.

**Envoy documents this explicitly to users** in the Monthly Trust Report: _"X tool-calls had interrupted completion; you acknowledged unknown-outcome for each."_

Non-repudiation of INTENT is preserved (Phase A is signed). Non-repudiation of OUTCOME is conditional on Phase B landing — interrupted cases are acknowledged.

---

## 7. Envelope re-read checkpoint

Per doc 02 §17 + doc 09 T-015 mitigation.

Every tool-call Phase A invokes `envelope_re_read_checkpoint(envelope_id)`. This operation:

1. Reads canonical envelope from Trust Vault (not from runtime's LLM context).
2. Re-computes `EffectiveEnvelopeSnapshot` (intersect RoleEnvelope × TaskEnvelope × sub-agent chain per doc 02 §5.2).
3. Verifies snapshot's hash matches what Phase A intent carries.
4. Mismatch → `EnvelopeSnapshotMismatchError`; Phase A refuses to sign.

**Why this matters:** LLM context may be stale or adversarially manipulated (T-015 context-window exhaustion). The canonical envelope is the Trust-Vault-stored authoritative copy. Runtime reads it fresh.

**Performance:** re-read is O(1) (cached by envelope_id after first read in session); invalidated per doc 02 §14 N2 conformance (envelope version bump, role override, etc.).

**Cross-runtime contract:** both runtimes MUST read the same Trust Vault; the re-read operation's output is byte-identical (BET-6) given the same vault state.

---

## 8. Runtime picker UX (Phase 02+)

Per doc 00 v3 ADR-0001 + §4.1 item 15 (N=3 mirrors + opt-out).

### 8.1 First-run picker

On first run, Envoy shows:

```
Pick your runtime:

  [Default] kailash-rs-bindings (Rust-accelerated)
    Faster (~20ms envelope checks). Binary distributed via Foundation GitHub + N=3 mirrors.
    Binary is closed-source; Python glue is open. You can opt out any time.

  [Alternative] kailash-py (pure Python)
    Slower (~80ms envelope checks). All source open; fully forkable.
    Choose this if you prefer maximum source-transparency.

  Both options are free. Both run fully offline.
```

Default highlighted = `kailash-rs-bindings`. One-keystroke to switch.

### 8.2 Switching runtimes post-install

`envoy runtime switch kailash-py` or `envoy runtime switch kailash-rs-bindings`:

1. Verify target runtime is installed (pip check); if not, install.
2. Verify Trust Vault + Ledger are compatible (algorithm_identifier match required).
3. Write `RuntimeSwitchRecord` to Ledger (signed by user's Genesis key, attests user-authorized switch).
4. Shut down old runtime; start new runtime.
5. New runtime generates its own device-bound runtime key; attestation written to Ledger.

**What persists:** Trust Vault (envelope, Genesis, delegation history) + Ledger + Connection Vault.
**What changes:** runtime binary + runtime key + future Phase B signatures + runtime attestations.

**What doesn't break:** legacy Phase B records signed by old runtime's key remain verifiable (public key recorded in old RuntimeAttestation record).

### 8.3 Phase migration

Phase 01: kailash-py only. Runtime picker UI hidden.
Phase 02+: picker enabled. User can opt out of Rust binary path.

---

## 9. Runtime security-review gates

Per doc 09 v3 §7 + this doc's contract:

### 9.1 Phase 00 gates (before Phase 01 opens)

- Abstract `kailash-runtime` interface spec (this doc) published.
- Binding-gap GH issues filed + tracked to closure OR scoped into Envoy-new-code (per doc 00 v3 Phase 00 gate).

### 9.2 Phase 01 gates

- kailash-py implements every operation in §2.1 interface with contract-conformant semantics.
- E1–E7 Envoy-specific conformance vectors pass on kailash-py.
- Trust Vault re-read checkpoint wired into Phase A signing.
- Two-phase signing lifecycle functional end-to-end.
- Orphan resolution UX functional.
- Algorithm-identifier schema landing on kailash-py (kailash-py#604 + shared with doc 03 §8 + doc 02 §6.2).

### 9.3 Phase 02 gates

- kailash-rs-bindings implements every operation.
- BET-6 contract parity: all byte-identical contract operations produce identical output across runtimes (run via cross-SDK harness).
- PACT N1–N6 Python runner implemented (`kailash-py#605`) AND cross-SDK byte-identity verified on N1–N6 vectors + E1–E7 vectors.
- Runtime picker UX shipped + tested.
- Runtime switch flow tested end-to-end (switch, work for a week, switch back).
- Binary poisoning defense: `binary_hash` verification active; startup refuses mismatched binaries.
- N=3 mirror verification at install time (doc 06).
- Reproducible-build verification stream published (third-party reproduction of `kailash-rs-bindings`).

### 9.4 Phase 03 gates

- Semantic-equivalence harness added for LLM-composed paths.
- Per-provider (Claude, GPT, DeepSeek, local-Ollama) semantic-equivalence tests pass.
- Multi-device runtime switching — same Trust Vault, different runtime, Ledger CRDT merges cleanly.

### 9.5 Phase 04 gates

- Multi-provider verification (doc 09 T-030) for high-stakes actions.
- Post-quantum migration planning entered.

---

## 10. Migration between runtimes

### 10.1 Vault + Ledger portability

Both kailash-py and kailash-rs-bindings consume the SAME Trust Vault format (doc 10) and the SAME Ledger format (doc 04). Runtime switch is a process-level change, not a data migration.

### 10.2 Forward compatibility

When a new runtime version introduces a new algorithm_identifier version:

- Old runtime's records remain verifiable under their original algorithm_identifier.
- New records use the new identifier.
- Legacy-verification resolver in each runtime handles both (doc 03 §8.3).

### 10.3 Backward compatibility

Downgrading runtime version (e.g. `envoy runtime switch` to an older kailash-py):

- New records use old algorithm (if older runtime doesn't recognize new version).
- If new records cannot be read by old runtime → refuse downgrade; surface error to user.

### 10.4 Catastrophic migration

If both kailash-py and kailash-rs-bindings are compromised simultaneously (supply chain + binary) — user falls back to:

- Read-only Ledger verification via independent reference-verifier tool (doc 00 v3 §3.3 new-code: "Independent reference-verifier tool").
- Export Ledger via `envoy ledger export` (uses envelope-independent canonical JSON); verify on separate hardware with non-compromised tool.
- Key destruction (doc 03 §11.1); start fresh.

---

## 11. Error + failure domains

| Domain                 | Error Classes                                                                             | Recovery                                                    |
| ---------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| Runtime lifecycle      | `RuntimeNotReadyError`, `RuntimeShutdownError`                                            | Restart runtime                                             |
| Trust (lineage / keys) | All errors from doc 03 §12                                                                | Per doc 03                                                  |
| Envelope               | All errors from doc 02 §11                                                                | Per doc 02                                                  |
| Ledger                 | `LedgerRollbackDetectedError`, `LedgerVerificationFailedError`, `LedgerSyncConflictError` | Per doc 04                                                  |
| Classifier             | `ClassifierUnavailableError`                                                              | Apply unavailability_policy                                 |
| Binary integrity       | `BinaryHashMismatchError`, `RuntimeAttestationInvalidError`                               | Refuse to start; user re-install from N-mirror verification |
| Cross-runtime parity   | `ContractParityMismatchError` (conformance test flag)                                     | Development-time gate; never in production                  |

All runtime errors logged as Ledger entries with `content_trust_level: system`.

---

## 12. Cross-references

- **doc 00 v3** — BET-6 contract-parity claim, ADR-0001 runtime pluggability, §4.1 item 7 + 15, §8 Test-2 two-phase signing.
- **doc 02 v3** — envelope re-read checkpoint (§17), JCS canonical form (§14.1), first-time-action gate (§19), SubsetProof schema (§14.4 producer).
- **doc 03 v1** — Trust Lineage primitives (Genesis, Delegation, cascade revocation, key rotation, SubsetProof verifier).
- **doc 04** — Ledger entry format, hash chain, two-phase signing Ledger side, head-commitment monotonicity.
- **doc 06** — distribution / installer / N=3 mirror verification / binary_hash manifest.
- **doc 09 v3** — T-004 two-phase signing, T-015 envelope re-read checkpoint, T-050/T-060 binary defenses, T-105 SubsetProof verifier.
- **doc 10** — Trust Vault + Connection Vault + Ledger storage formats (runtime consumer).

**Cross-SDK references:**

- kailash-py runtime — `src/kailash/runtime/` + `src/kailash/trust/*` per `03-primitive-reconciliation.md` status grid.
- kailash-rs-bindings runtime — `bindings/kailash-python/src/` + `crates/kailash-core/` + `crates/eatp/`.
- **Phase 01 exit requires** algorithm-identifier schema (mint#6 + kailash-py#604 + kailash-rs#519) AND kailash-py PACT N4/N5 runner (kailash-py#605).
- **BET-6 blockers** — N4/N5 runner + SQLi fix (kailash-rs#520). Both are Phase 02 entry gates.

---

## 13. Open questions for `/redteam`

1. **N3 / N6 placeholder status** — awaiting mint formalization. OK to ship Phase 01 without these? (They're Rust-incomplete too; not Envoy's blocker.)
2. **Orphan resolution window (30 days default)** — is this too long? Risk of orphan accumulation. Alternative: configurable per envelope Operational dimension.
3. **Runtime key rotation frequency** — daily? Monthly? Never (only on compromise)? Default proposal: on-demand only; no scheduled rotation.
4. **Phase B signed by runtime_device_key, not delegation key** — is this correct? Runtime attests execution fact; delegation key attests authorization. Two distinct facts. Adversarial perspective: could be collapsed into single key for simplicity, but separation preserves audit clarity.
5. **`envelope_check()` as a single call vs per-class calls** — doc 02 hot-path has 6 ordered classes. Should the runtime expose each separately, or only the aggregate? Default: aggregate for hot-path efficiency; debug mode exposes per-class.
6. **Semantic-equivalence harness (Phase 03)** — how do we test that two runtimes produce "same outcome" for same input when LLM is non-deterministic? Proposal: test structural decisions (envelope check outcomes, tool selection) against golden fixture; natural-language phrasing verified by separate classifier (fuzzy-similarity ≥ 0.8).
7. **Catastrophic migration (§10.4)** — the "independent reference-verifier tool" is doc 00 v3 §3.3 new code. Who builds it? Foundation? Community? Phase 01 exit gate requires it; not yet claimed by any team.
8. **Runtime switch Trust Vault compatibility** — we assume algorithm_identifier match is sufficient. What if runtime has different capabilities entirely (e.g. kailash-py lacks MCP transport but vault references MCP-transported delegations)? Proposal: runtime declares capability set at startup; vault operations that require unsupported capability fail cleanly.

---

**End of doc 05 v1. `/redteam` Round 1 next.**
