# runtime-abstraction

## Purpose

Abstract `kailash-runtime` interface that Envoy programs against. Two shipped implementations (kailash-py + kailash-rs-bindings); byte-identical contract for spec-driven outputs, semantically-equivalent for LLM-composed outputs.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/05-runtime-abstraction.md v2`.
- **Threats mitigated:** T-004 two-phase signing, T-015 envelope re-read checkpoint, T-050a/b binary threats, T-060 binary poisoning, T-105 subset-proof verifier.
- **BETs tested:** BET-6 contract parity, BET-3 sovereignty (runtime pluggability).

## Abstract interface

`KailashRuntime` (ABC). Every method below MUST be implemented by both `kailash-py` and `kailash-rs-bindings` runtimes. Methods in §Contract partition §Byte-identical MUST produce byte-identical outputs on identical inputs; §Semantically-equivalent methods MUST produce semantically-equivalent outputs under BET-6.

### Lifecycle

| Method               | Signature                 | Semantics                                                                                       |
| -------------------- | ------------------------- | ----------------------------------------------------------------------------------------------- |
| `startup(config)`    | `(RuntimeConfig) -> None` | Load device key, verify binary hash vs manifest, prepare classifier cache.                      |
| `shutdown()`         | `() -> None`              | Flush Ledger pending writes, zero in-memory secrets, release file handles.                      |
| `runtime_identity()` | `() -> RuntimeIdentity`   | Return `{runtime_family, version, binary_hash, device_bound_pubkey_hex, algorithm_identifier}`. |

### Trust Lineage

| Method                                   | Signature                                                        | Semantics                                                                                                         |
| ---------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `trust_sign(record, key)`                | `(DelegationRecord \| RevocationRecord \| ..., KeyRef) -> bytes` | Byte-identical; JCS + Ed25519 signature over record's canonical form per specs/envelope-model.md §Canonical JSON. |
| `trust_verify_chain(record)`             | `(DelegationRecord) -> VerifyResult`                             | Byte-identical; 10-step chain verification per specs/trust-lineage.md §Chain verification.                        |
| `trust_cascade_revoke(root_id)`          | `(str) -> set[str]`                                              | Byte-identical SET equality; ordering may differ (BFS vs DFS).                                                    |
| `trust_verify_subset_proof(parent, sub)` | `(EnvelopeConfig, EnvelopeConfig) -> VerificationResult`         | Runtime-signed; specs/sub-agent-delegation.md §`is_subset_envelope` algorithm.                                    |

### Envelope

| Method                                         | Signature                                            | Semantics                                                                              |
| ---------------------------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `envelope_canonical_form(envelope)`            | `(EnvelopeConfig) -> bytes`                          | Byte-identical; JCS-RFC8785 + NFC per specs/envelope-model.md §Canonical JSON.         |
| `envelope_intersect(a, b)`                     | `(EnvelopeConfig, EnvelopeConfig) -> EnvelopeConfig` | Byte-identical; specs/envelope-model.md §`intersect_envelopes`.                        |
| `envelope_check(envelope, action)`             | `(EnvelopeConfig, Action) -> CheckResult`            | Structural + semantic check; may dispatch Grant Moment on FIRST_TIME_REQUIRES_GRANT.   |
| `envelope_re_read_checkpoint(envelope, depth)` | `(EnvelopeConfig, int) -> ReadCheckpointResult`      | T-015 defense: re-read envelope from Trust Vault every N composition-rule evaluations. |

### Two-phase signing

| Method                                          | Signature                                     | Semantics                                                                               |
| ----------------------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------- |
| `phase_a_sign_intent(intent)`                   | `(PhaseAIntent) -> PhaseARecord`              | Delegation-key-signed; envelope_check runs pre-sign; writes to Ledger.                  |
| `phase_b_sign_outcome(outcome)`                 | `(PhaseBOutcome, intent_id) -> PhaseBRecord`  | Runtime-device-key-signed; linked to `intent_id`.                                       |
| `phase_a_orphan_resolve(intent_id, resolution)` | `(str, Resolution) -> PhaseAOrphanResolution` | User-chosen resolution (retry / failed / investigate); Genesis-signed via Grant Moment. |

### Ledger

| Method                          | Signature                                           | Semantics                                                                       |
| ------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------- |
| `ledger_append(entry)`          | `(LedgerEntry) -> LedgerEntry` (entry_id populated) | Byte-identical hash chain; parent_hash + entry_id computed over canonical form. |
| `ledger_query(filter)`          | `(LedgerQueryFilter) -> list[LedgerEntry]`          | Read-path; applies specs/classification-policy.md `apply_read_classification`.  |
| `ledger_verify_chain(from, to)` | `(int, int) -> VerifyResult`                        | Byte-identical; per specs/ledger.md §Export + independent verifier.             |
| `head_commitment()`             | `() -> HeadCommitment`                              | Byte-identical; monotonic non-decreasing; specs/ledger.md §Head commitment.     |

### Classifier

| Method                                     | Signature                                                           | Semantics                                                                                             |
| ------------------------------------------ | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `classifier_invoke(ref, content, ctx)`     | `(str, bytes, ClassifierContext) -> ClassifierVerdict`              | Semantically-equivalent; 2+ classifiers per ensemble mandatory.                                       |
| `ensemble_aggregate(verdicts, policy)`     | `(list[ClassifierVerdict], UnavailabilityPolicy) -> EnsembleResult` | Byte-identical aggregation; disagreement fails CLOSED by default.                                     |
| `classifier_registry_resolve(registry_id)` | `(str) -> RegistryEntry`                                            | Fetches, verifies 2-of-N steward signatures, hash-matches; specs/foundation-ops.md §Registry schemas. |

### Budget

| Method                               | Signature                           | Semantics                                                                              |
| ------------------------------------ | ----------------------------------- | -------------------------------------------------------------------------------------- |
| `budget_reserve(session, cost)`      | `(SessionID, int) -> ReservationID` | Byte-identical; integer microdollars; specs/budget-tracker.md.                         |
| `budget_record(reservation, actual)` | `(ReservationID, int) -> None`      | Finalize; surplus/deficit reconciled.                                                  |
| `budget_snapshot(session)`           | `(SessionID) -> BudgetSnapshot`     | `{per_call, per_session, per_hour_velocity, per_day, per_month}` integer microdollars. |
| `budget_velocity_check(session)`     | `(SessionID) -> VelocityResult`     | Raises `BudgetVelocityExceededError` if any ceiling breached.                          |

### Runtime device-key signing

| Method                                 | Signature                       | Semantics                                                                  |
| -------------------------------------- | ------------------------------- | -------------------------------------------------------------------------- |
| `runtime_sign(payload)`                | `(bytes) -> bytes`              | Ed25519 signature with device-bound key (Secure Enclave / TPM / software). |
| `runtime_verify(payload, sig, pubkey)` | `(bytes, bytes, bytes) -> bool` | Byte-identical verification.                                               |

### Prompt + tool-output

| Method                                                     | Signature                                                              | Semantics                                                                               |
| ---------------------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `prompt_assemble(system, envelope, context, user_message)` | `(SystemPrompt, EnvelopeConfig, ContextSlice, str) -> AssembledPrompt` | Envelope-pinned system prompt (T-015 defense); consumer of specs/envelope-model.md.     |
| `tool_output_sanitize(output, tool_name, envelope)`        | `(bytes, str, EnvelopeConfig) -> SanitizeResult`                       | specs/tool-output-sanitization.md §Algorithm; fail-closed on classifier unavailability. |
| `first_time_action_gate(session, tool_name, args)`         | `(SessionObservedState, str, dict) -> GateResult`                      | specs/session-state.md §`first_time_action_gate`.                                       |
| `grant_moment_surface(request)`                            | `(GrantMomentRequest) -> GrantMomentResult`                            | specs/grant-moment.md dispatch; channel-adapter routing.                                |

## `RuntimeIdentity`

`{runtime_family, version, binary_hash, device_bound_pubkey_hex, algorithm_identifier}`.

## `AssembledPrompt` (return type of `prompt_assemble`)

```json
{
  "schema_version": "assembled-prompt/1.0",
  "prompt_id": "uuid-v7",
  "system_prompt_canonical_hash": "sha256:...",
  "envelope_pin": {
    "envelope_id": "uuid-v7",
    "envelope_version": <int>,
    "envelope_hash": "sha256:..."
  },
  "context_slice": {
    "ledger_head_at_assembly": "sha256:...",
    "session_id": "uuid-v7",
    "session_observed_state_hash": "sha256:..."
  },
  "user_message_canonical_hash": "sha256:...",
  "rendered_bytes": <bytes>,
  "rendered_bytes_size": <int>,
  "rendered_canonical_hash": "sha256:...",
  "assembled_at": "<iso8601>",
  "runtime_signature_hex": "<ed25519>"
}
```

**Cross-runtime byte-identity (BET-6):** for the same `(system_prompt, envelope, context_slice, user_message)` quadruple, every runtime MUST produce the same `rendered_canonical_hash`. The `rendered_bytes` itself MAY differ in tokenization details for non-canonical fields (whitespace, comment markers) but the canonical-hash MUST match.

**T-015 defense surface:** `envelope_pin.envelope_hash` is the system-prompt-pinning anchor. Any runtime that drifts from the pin between `prompt_assemble` and `prompt_send` MUST raise `EnvelopeRePinDriftError`. The Envelope re-read checkpoint (specs/envelope-model.md §Algorithms §`envelope_re_read_checkpoint`) consumes this field.

**`SystemPrompt`, `ContextSlice`, `SanitizeResult`, `GateResult`, `GrantMomentRequest`, `GrantMomentResult`** — declared as input/output types on the abstract interface table; their schemas live in their owning specs (system-prompt = part of envelope.metadata; ContextSlice = `{ledger_head, session_id, session_observed_state_hash}`; SanitizeResult per specs/tool-output-sanitization.md §Surface; GateResult per specs/session-state.md §`first_time_action_gate`; GrantMomentRequest/Result per specs/grant-moment.md §Schema).

## Runtime device key (§4)

Distinct from user Genesis. Lives in Secure Enclave / TPM / software-fallback. Signs Phase B, SubsetProof re-verification, HALTED records, head commitments. Rotation via `KeyRotationRecord` with `key_scope: "runtime_device"` (canonical Ledger entry type owned by specs/trust-lineage.md §Key rotation) — dual-signed (old + new runtime keys) + user-Genesis co-signature (F-02 fix: prevents self-rotation under runtime compromise).

**Naming note:** earlier drafts used `RuntimeKeyRotationRecord` as a distinct type. V-04 reconciliation: there is ONE canonical entry type `KeyRotationRecord` with a `key_scope` field (values: `"runtime_device" | "genesis" | "per_entry" | "master"`). Cross-reference specs/trust-lineage.md §Key rotation for schema.

## Two-phase signing (doc 00 v3 §8 Test-2)

Phase A intent pre-execution (delegation-key-signed); Phase B outcome post-execution (runtime-device-key-signed); orphan resolution at next session start with Grant Moment.

## Contract partition (BET-6)

**Byte-identical:** `envelope_canonical_form`, `trust_sign`, `delegation_id` hashing, ledger hash chain, `cascade_revoke` SET equality, `envelope_intersect`, subset-proof runtime_verification_signature, head_commitment.

**Semantically-equivalent:** agent LLM responses, Grant Moment prompt text, tool-call timing metadata.

### Contract-tier enforcement (machine-readable)

The byte-identical/semantically-equivalent partition is enforced in code, not prose: every `KailashRuntime` Protocol method carries a `@byte_identical` or `@semantically_equivalent` decorator (`envoy/runtime/contract_tier.py`) that stamps `__contract_tier__`. `assert_all_methods_tagged()` fails loudly (`MissingContractTierError`) on any untagged method — there is no silent default, and demoting a method from byte-identical to semantically-equivalent is BLOCKED. The BET-6 conformance harness (`envoy/runtime/conformance/`, `tests/conformance/harness.py`) reads these tiers to select the byte-identity (hash-equality) scorer vs the deferred semantic scorer per method. The N3 structural-vs-semantic dispatch is observed deterministically via the cross-runtime dispatch-observation hook (`envoy/runtime/dispatch_observation.py`), not output heuristics. (Shipped: Phase-02 shard S1.)

## Conformance vectors N1–N6 decoded

Inherited from doc 05 v2 / PACT N-vectors. Each vector is a cross-SDK byte-identity gate per BET-6.

- **N1 — Knowledge Filter** (pre-retrieval gate). Envelope `field_allowlist_per_model` gates which fields the runtime fetches from DataFlow BEFORE classification; prevents over-fetch of classified data. 10 vectors.
- **N2 — Envelope Cache** (5-property invalidation: envelope_version, algorithm_identifier, classifier_ensemble_versions, posture_level, principal_genesis_id). Cache MUST invalidate on any of the 5 properties changing. 15 vectors.
- **N3 — Structural-vs-semantic partition** (BET-2 cross-SDK). Every envelope check that reports `structural`-class error MUST NOT require LLM invocation; every check reporting `semantic`-class MUST dispatch to the classifier ensemble. Partition byte-identity on classification-only test fixtures. 10 vectors.
- **N4 — Verdict rendering**. Envelope check verdict → user-facing text via `grant_moment_surface`. Byte-identical structured payload; rendered text is semantically-equivalent across runtimes. 10 vectors.
- **N5 — Posture ceiling**. `effective_posture ≤ min(envelope-declared, principal-current)` enforced at `envelope_check`. 15 vectors.
- **N6 — Session-scoped cache correctness**. `SessionObservedState.tool_calls_made` (specs/session-state.md) fingerprint must hash identically across runtimes given the same tool_name + args; cache reset emits `session_boundary_crossed` with identical content_hash. 10 vectors.

## Runtime attestation (RuntimeAttestation Ledger entry)

Producer for `RuntimeAttestation` entry type (specs/ledger.md §Entry types). Emitted:

- At every `startup()` — attests the runtime's binary hash + device-bound key pubkey + claimed algorithm_identifier matches the expected manifest.
- At every `runtime_switch` — before the switch record is written, the target runtime is verified via its attestation.
- On-demand by `envoy runtime attest` CLI.

```json
{
  "type": "RuntimeAttestation",
  "schema_version": "runtime-attest/1.0",
  "runtime_identity": {
    "runtime_family": "kailash-py | kailash-rs-bindings",
    "version": "<str>",
    "binary_hash": "sha256:<binary_bytes>",
    "device_bound_pubkey_hex": "<str>",
    "algorithm_identifier": {...}
  },
  "device_attestation": {
    "attestation_type": "secure_enclave | tpm | software",
    "attestation_hash": "sha256:<platform_attestation_bytes>"
  },
  "reproducible_build_refs": [
    {"reproducer_id": "<str>", "verification_hash": "sha256:...", "verified_at": "<iso8601>"}
  ],
  "attested_at": "<iso8601>",
  "signed_by": "runtime_device_key",
  "signature_hex": "ed25519"
}
```

## Envoy-specific conformance E1–E7

- **E1** Envelope canonical JSON (67 vectors).
- **E2** Delegation Record signing (20 vectors).
- **E3** Cascade revocation BFS/DFS set-equality (15 vectors).
- **E4** Cycle detection (15 vectors).
- **E5** Subset-proof verification (20 adversarial vectors).
- **E6** Two-phase signing orphan resolution.
- **E7** Ledger head-commitment monotonicity.

## Runtime picker (§8 Phase 02)

First-run picker: kailash-rs-bindings default vs kailash-py opt-in. Switch via `envoy runtime switch` — requires (a) passphrase unlock (not warm), (b) Genesis-signed `runtime_switch` Ledger entry (specs/ledger.md §Entry types; V-05 canonical naming uses lower-snake-case), (c) runtime-attestation verification of target.

## Security gates per phase

- **Phase 00:** abstract interface spec published + binding-gap GH issues tracked.
- **Phase 01:** kailash-py impl; E1–E7 vectors pass; two-phase + envelope re-read functional; algorithm-identifier schema landed.
- **Phase 02:** kailash-rs-bindings impl; BET-6 contract parity; N1–N6 Python runner (kailash-py#605); binary hash verification; N=3 mirrors; reproducible-build stream.
- **Phase 03:** semantic-equivalence harness; multi-device runtime switch.
- **Phase 04:** multi-provider verification; PQ migration planning.

## Error taxonomy

`RuntimeNotReadyError`, `RuntimeShutdownError`, `AlgorithmIdentifierMismatchError`, `PhaseAIntentSigningFailedError`, `PhaseBOrphanError`, `LedgerRollbackDetectedError`, `LedgerVerificationFailedError`, `ClassifierUnavailableError`, `RuntimeSignatureVerificationFailedError`, `BudgetExhaustedError`, `BudgetVelocityExceededError`.

## Cross-references

All other specs. Runtime is the composition layer.

## Test location

Phase 01 wires only the `kailash-py` runtime (per brief constraint #1); it ships the abstract `KailashRuntime` Protocol, runtime attestation at startup, and the single-runtime byte-canonical path. Tested in-repo:

- `tests/tier2/test_envoy_runtime_wiring.py` — `KailashRuntime` Protocol wiring + `RuntimeIdentity` / `RuntimeAttestation` surface against the Phase-01 `kailash-py` runtime.
- `tests/tier1/test_envelope_canonical_bytes_pure.py` — single-runtime byte-canonical form (the byte-identity inputs the cross-runtime conformance vectors will compare in Phase 02).

## Out of scope (this phase)

The cross-runtime conformance harness and second-runtime defenses land in Phase 02, when `kailash-rs-bindings` is wired (per § Security gates per phase + brief constraint #2 "abstract interface MUST exist even though only one implementation is wired"):

- N1–N6 + E1–E7 conformance vectors (run against BOTH `kailash-py` AND `kailash-rs-bindings`) — Phase 02.
- Cross-runtime byte-identity + semantic-equivalence (BET-6 two-runtime harness) — Phase 02 / Phase 03.
- `envoy runtime switch` picker + attestation-on-switch — Phase 02.
- T-015 envelope re-read checkpoint, T-050a/b binary-mirror + signing-key revocation, T-060 runtime-binary-poisoning — Phase 02 (binary distribution).
- T-105 sub-agent SubsetProof re-derivation — Phase 03 (specs/sub-agent-delegation.md).

## Open questions

1. N3 + N6 corpus filling cadence — Round 1 R1-HIGH flagged the 10-vector / 10-vector counts as placeholders. When does the Foundation publish the canonical N3 + N6 corpora, and what cadence governs subsequent expansion (per-release? Per-discovered-edge?).
2. Runtime selection at install-time UX — first-run picker default is kailash-rs-bindings with kailash-py opt-in; how is this surfaced for users who installed via `pip install kailash-py` directly (bypassing the picker), and should `envoy runtime switch` warn about implicit-default vs explicit-pick?
3. Semantic-equivalence harness scoring — what is the canonical similarity metric for "semantically-equivalent" Grant Moment text across runtimes, and what divergence threshold escalates to a BET-6 falsifier?
4. Reproducible-build verification stream cadence — third-party reproducers publish on what schedule, and does runtime startup gate on at-least-N-reproducer-confirmations or accept first-confirmation?
5. Cross-runtime tool-call timing metadata — `tool-call timing metadata` is currently §Semantically-equivalent; under what circumstances would the timing metadata become byte-significant (e.g. token-bucket replay defense), promoting it to §Byte-identical?
