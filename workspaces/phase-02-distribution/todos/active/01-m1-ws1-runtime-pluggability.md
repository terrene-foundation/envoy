# M1 — WS-1 Runtime Pluggability

**Milestone value.** WS-1 delivers the headline Phase-02 capability the user's brief names first (`briefs/00-phase-02-scope.md` §WS-1; `ROADMAP.md:76-80` "Runtime pluggability — ADR-0001+0009 delivery"): Envoy programs against ONE abstract `KailashRuntime` interface with TWO wired implementations (`kailash-rs-bindings` default for speed, `kailash-py` opt-out for full open-source forkability), a first-run picker, and `envoy runtime switch` with attestation. This is the critical-path milestone (S1 → S2a → S3b → S7v, depth-4 per `02-plans/01-architecture.md`) and carries the phase's hardest correctness risk: the BET-6 cross-runtime **byte-identity conformance harness**. **Legal-gate note:** WS-1 is **buildable NOW** — building crypto-bearing binaries is not export-controlled, only cross-border redistribution is (`02-plans/01-architecture.md` § Legal-gate-aware build sequence). The ONLY gate that could force WS-1 rework is the **ADR-0009 Foundation-board endorsement of the runtime-pluggability model** (`DECISIONS.md:323` "Foundation board must endorse the runtime-pluggability model in writing before public launch"); every other ADR-0009 item (composite LICENSE, SPDX, export-control, trademark) gates _release_, not _build_.

**Accuracy anchor (carry into every shard below).** E1–E7 **and** N1–N6-structured payloads are **byte-identical** — verified by hash-equality with a live deterministic loop (`runtime-abstraction.md:139-143,188-196`; Round-3 correction `01-analysis/01-research/01-ws1-runtime-pluggability.md:605-607`). The ONE semantic-equivalence slice is **N4's rendered verdict TEXT** (the structured N4 payload is byte-identical; only the user-facing rendered string is semantically-equivalent — `runtime-abstraction.md:152`); its placement is **settled Phase-03** (`runtime-abstraction.md:207`), and only its **scoring metric** is an open spec question (`runtime-abstraction.md:239`). Therefore **Phase-02 conformance = byte-identity across every family (N1–N6 structured + E1–E7)**; the N4 rendered-text harness lands with the Phase-03 semantic-equivalence harness. Demoting any byte-identical method to semantic is BLOCKED — it weakens a security gate (`zero-tolerance.md` Rule 4; `journal/0004` R3-HIGH).

**Recommendation carried from `/analyze`:** PyO3 **compile-time embed** is recommended over uv-managed subprocess for the single-binary distribution (offline-atomic install + cleanest T-060 one-hash story — `01-ws1-runtime-pluggability.md:246-281`). That decision lands in M6/S15 (size-validated against the <50 MB cap, `specs/distribution.md:78-82`); M1 is interpreter-embedding-agnostic because `get_runtime()` is identical under both embed strategies.

---

## S1 — Contract-tier Protocol metadata + cross-runtime dispatch-observation hook + harness skeleton

- **Type:** Build
- **Value-anchor:** `briefs/00-phase-02-scope.md` §WS-1 names "Cross-runtime conformance: N1–N6 + E1–E7 vectors run against BOTH runtimes — BET-6 two-runtime harness"; the tier metadata is the load-bearing prerequisite that lets that harness mechanically pick the right scorer per method (`01-ws1-runtime-pluggability.md:189-191`).
- **Implements:** `specs/runtime-abstraction.md` §Contract partition (`:139-143`), §Conformance vectors (`:145-154`); closes Spec-gap-2 (`01-ws1-runtime-pluggability.md:517-523`).
- **Depends:** — (root, Wave 1).
- **Scope:** Land the `@byte_identical` / `@semantically_equivalent` contract-tier metadata on `KailashRuntime` (deferred at `protocol.py:13`) as a method-co-located decorator so adding a method without a tier is a loud authoring error; add a deterministic cross-runtime dispatch-observation hook (records "did this call dispatch to the classifier ensemble" for the N3 structural-vs-semantic partition); build the parametrized pytest harness skeleton over `get_runtime(family=...)` (`selection.py:37`, the ONE seam) with two pluggable scorer stubs and per-vector IDs for failure localization.
- **Acceptance criteria:**
  - Every one of the 30 Protocol methods carries a machine-readable contract tier; a method missing its tier decorator fails an authoring-time assertion (no hand-maintained method→tier map).
  - The corpus row schema supports a **per-field** tier tag (not only per-vector), so N3/N4 mixed-tier families are expressible (closes Spec-gap-3, `01-ws1-runtime-pluggability.md:525-529`).
  - Harness skeleton collects under `tests/conformance/`, parametrizes `["kailash-py","kailash-rs-bindings"]` × vector, and emits test IDs of the form `test_<family>[<runtime>-<vector_id>]` (runtime axis visible in the failure line).
  - Dispatch-observation hook records classifier-dispatch occurrence deterministically; a unit test asserts a structural-class check records "no dispatch" and a semantic-class check records "dispatch".
- **Capacity check:** invariants ≈ 4 (tier-co-location, per-field tier schema, single-seam routing, dispatch-observation determinism); call-graph hops ≈ 2–3 (decorator → protocol → harness loader); LOC ≈ 350 load-bearing (metadata + hook + skeleton, excludes corpus). Live feedback loop (pytest collection + unit assertions). **Within budget.**

---

## S2a — rs-bindings adapter wiring behind the frozen interface (31 methods, 9 groups)

- **Status / Verification (2026-06-11, redteam Wave-2 gate — W2G-002):** SHIPPED as **18 of 31 methods genuinely wired**, **13 substrate-gated**. The 18 wired forward to a real backend: the kailash binding (`trust_sign`, `envelope_intersect`, `runtime_sign`/`runtime_verify`), the shared envoy primitive (`envelope_canonical_form`), the `ledger_*` (EnvoyLedger), and the `budget_*` (BudgetRuntimeAdapter). The 13 substrate-gated methods (`envelope_check`, `envelope_re_read_checkpoint`, `trust_verify_subset_proof`, `phase_a_sign_intent`, `phase_b_sign_outcome`, `phase_a_orphan_resolve`, `classifier_invoke`, `ensemble_aggregate`, `classifier_registry_resolve`, `prompt_assemble`, `tool_output_sanitize`, `first_time_action_gate`, `grant_moment_surface`) raise a typed `RuntimeNotReadyError` naming the gating engine shard (S5o / S6a / S6c), DI-gated pending those engines — NOT a phantom forward (the pre-gate code forwarded to a non-existent `self._trust_store.<name>` surface that produced an opaque `AttributeError` under DI). Verified: `tests/tier1/test_kailash_rs_bindings_shape_parity.py` (parametrized typed-raise over the 13 + trust_sign/envelope_intersect direct-call tests).
- **Type:** Wire
- **Value-anchor:** `briefs/00-phase-02-scope.md` §WS-1 "`kailash-rs-bindings` integration as **default** runtime"; this is the literal delivery of the Rust-accelerated default the user's ADR-0001 picker promises (`DECISIONS.md:47`).
- **Implements:** `specs/runtime-abstraction.md` §Abstract interface (`:13-91`, all 9 method groups); fills the Phase-01 seam at `envoy/runtime/adapters/kailash_rs_bindings.py:46`.
- **Depends:** S1 (needs the harness + tier metadata to gate each wired method).
- **Scope:** Replace each `Phase02SubstrateNotWiredError` body in `KailashRsBindingsRuntime` with a forward to the Rust binding's equivalent, mirroring `KailashPyRuntime`'s boundary discipline (hex-string→`bytes` encoding at the boundary, `kailash_py.py:28-42`); hold the EXACT sync/async shape per method (`trust_cascade_revoke` is sync in the Protocol — `protocol.py`; the ledger methods are `async def`), so structural `isinstance` typing cannot mask an awaited non-coroutine; wire `runtime_sign`/`runtime_verify` to the platform device-key surface (Secure Enclave / TPM, the rs adapter owns attestation). Do NOT flip `RS_BINDINGS_ENABLED` here — wiring precedes flag-flip (that gates on S2b/S2c/S3a/S3b green).
- **Acceptance criteria:**
  - The wireable surface (18/31) forwards to the binding/primitive/ledger/budget core; the 13 substrate-gated methods raise a typed `RuntimeNotReadyError` naming the gating shard (S5o/S6a/S6c), NOT a phantom forward; zero `Phase02SubstrateNotWiredError` bodies remain (grep clean). [Amended 2026-06-11 per W2G-002 — original "all 30 forward" was the pre-gate aspiration; see Status/Verification above.]
  - Each method's sync/async shape matches the Protocol declaration; a test awaits every `async def` method and calls every sync method directly (no shape mismatch).
  - `runtime_sign` returns `bytes` satisfying the `-> bytes` contract; the conformance harness (S2b/S3a) is what proves byte-equality with `kailash-py`.
  - "rs adapter satisfies `isinstance(adapter, KailashRuntime)`" is explicitly NOT treated as a completion signal (`zero-tolerance.md` Rule 3d; `01-ws1-runtime-pluggability.md:344-354`) — completion is gated on the byte-identical harness, not structural typing.
- **Capacity check:** invariants ≈ 5 (boundary encoding, sync/async parity per method, device-key path, no-flag-flip, structural-typing-is-insufficient); call-graph hops ≈ 3 (adapter → PyO3 binding → Rust core); LOC ≈ 450 (30 forwards, mostly pattern-stamped). Live loop (harness gates each method). **At budget — boundary-encoding + sync/async parity are the load-bearing invariants; the 30 forwards are pattern-repetition, not 30 independent invariants.** Within budget.

---

## S2b — N1–N3 byte-identity vector families green (both runtimes)

- **Type:** Build
- **Value-anchor:** `briefs/00-phase-02-scope.md` §WS-1 BET-6 two-runtime harness; N1–N3 prove the pre-retrieval/cache/partition contract is byte-identical across runtimes — the first third of the conformance corpus the user's brief requires.
- **Implements:** `specs/runtime-abstraction.md` §Conformance vectors N1–N6 (`:149-151`): N1 Knowledge Filter (10), N2 Envelope Cache 5-property invalidation (15), N3 structural-vs-semantic partition (10).
- **Depends:** S2a (the rs adapter must forward before its outputs can be hashed).
- **Scope:** Author + run the N1, N2, N3 vector families. N1/N2 are pure byte-identity (hash-equality between runtimes). N3 is the mixed-shape family: byte-identity on the structural slice (classification-only fixtures, no classifier invocation) PLUS dispatch-occurred verification on the semantic slice (using S1's dispatch-observation hook) — N3's assertion is "structural-class checks NEVER invoke the classifier, semantic-class always dispatch," both byte-identical/deterministic, NOT a probe (`runtime-abstraction.md:151`; `01-ws1-runtime-pluggability.md:97-102`).
- **Acceptance criteria:**
  - N1–N3 vectors produce hash-equal canonical output across `kailash-py` and `kailash-rs-bindings` (cross-runtime equivalence gate).
  - N2's 5-property invalidation (envelope_version, algorithm_identifier, classifier_ensemble_versions, posture_level, principal_genesis_id) — each property change independently triggers cache invalidation, byte-identically on both runtimes.
  - On any mismatch the byte-identity scorer emits both canonical-JSON sides + first differing byte offset + JSON path (e.g. "differs at `entries[3].timestamp`") — NOT a bare `assert a == b` (`01-ws1-runtime-pluggability.md:160-167`).
  - N3 records zero classifier dispatch on the structural slice and dispatch-occurred on every semantic-slice vector.
- **Capacity check:** invariants ≈ 4 (N1 pre-fetch gate, N2 5-property invalidation, N3 partition byte-identity, N3 dispatch-occurred); call-graph hops ≈ 2 (corpus loader → scorer → adapter); LOC ≈ 300 (35 vectors + scorer wiring, vectors are data not logic). Live loop (hash-equality). **Within budget.**

---

## S2c — N4–N6 families: N5/N6 + N4 structured-payload byte-identity

- **Type:** Build
- **Value-anchor:** `briefs/00-phase-02-scope.md` §WS-1 BET-6 harness; N4–N6 complete the N-corpus — posture-ceiling enforcement (N5) and session-cache fingerprint correctness (N6) are byte-identical user-facing safety invariants.
- **Implements:** `specs/runtime-abstraction.md` §Conformance vectors (`:152-154`): N4 verdict rendering (10), N5 posture ceiling (15), N6 session-scoped cache fingerprint (10).
- **Depends:** S2a.
- **Scope:** Author + run N5 (posture ceiling: `effective_posture ≤ min(envelope-declared, principal-current)`, byte-identical) and N6 (`SessionObservedState.tool_calls_made` fingerprint hashes identically across runtimes; cache reset emits `session_boundary_crossed` with identical content_hash). For N4, verify **only the structured payload byte-identity** — N4's structured verdict object hashes equal across runtimes. **N4's rendered verdict TEXT semantic-equivalence is explicitly DEFERRED to Phase-03** (`runtime-abstraction.md:152,207`); do NOT author a probe for rendered text in Phase-02. Only N4's scoring metric is an open spec question (`runtime-abstraction.md:239`) — flagged, not resolved here.
- **Acceptance criteria:**
  - N5–N6 + N4-structured produce hash-equal canonical output across both runtimes.
  - N4 acceptance asserts **structured-payload byte-identity ONLY**; the rendered-text equivalence row is marked Phase-03 (not collected as a Phase-02 gate). A reviewer sweep confirms no probe/semantic-scorer fires on N4 rendered text in this shard.
  - N6 cache-reset `session_boundary_crossed` content_hash is byte-identical across runtimes (consumes the boundary-signal contract WS-6/S5b owns; harness uses fixtures, not the live WS-6 store).
  - Field-level diff localization on mismatch (same scorer as S2b).
- **Capacity check:** invariants ≈ 4 (N5 posture ceiling, N6 fingerprint identity, N6 boundary content_hash, N4 structured-only / no-rendered-text); call-graph hops ≈ 2; LOC ≈ 300 (35 vectors + N4 payload/text split logic). Live loop. **Within budget. The N4 structured-vs-rendered split is the one subtle invariant — call it out in the reviewer prompt.**

---

## S3a — E1–E4 byte-identical vectors (hash-equality)

- **Type:** Build
- **Value-anchor:** `briefs/00-phase-02-scope.md` §WS-1 BET-6; E1–E4 are the Envoy-specific crypto-path conformance core (canonical JSON, delegation signing, cascade-revoke, cycle detection) — the byte-identity that makes "same behavior, only slower" a verifiable claim for opt-out users.
- **Implements:** `specs/runtime-abstraction.md` §Envoy-specific conformance E1–E7 (`:190-193`): E1 envelope canonical JSON (67), E2 Delegation Record signing (20), E3 cascade-revoke BFS/DFS set-equality (15), E4 cycle detection (15).
- **Depends:** S2a.
- **Scope:** Author + run E1–E4 as **byte-identical** vectors with the live hash-equality loop (Round-3 correction: these are byte-identical, NOT semantic — `01-ws1-runtime-pluggability.md:605-607`). E1 hashes the JCS-RFC8785 + NFC canonical form; E2 verifies Ed25519 signature bytes match; E3 asserts SET-equality of the cascade-revoke result (ordering may differ BFS vs DFS, but the set is byte-identical); E4 asserts identical cycle-detection verdicts. Run the byte-identity slice across the full OS matrix (macos-14, ubuntu-22.04/24.04, windows-2022) to catch cross-language NFC drift (`01-ws1-runtime-pluggability.md:181-185`).
- **Acceptance criteria:**
  - E1–E4 vectors hash-equal across both runtimes; loop is `live` (deterministic), not probe-judged.
  - E3 asserts SET-equality (order-insensitive) — a BFS-vs-DFS ordering difference does NOT fail; a set-membership difference DOES.
  - The byte-identity slice runs green on all 4 OS targets (a Rust runtime that truncates a combining character on Windows NTFS is a silent BET-6 falsifier a single-OS run never catches).
  - Mismatch localizes to method + vector + field (per the S1 scorer).
- **Capacity check:** invariants ≈ 4 (E1 canonical-hash, E2 signature bytes, E3 set-equality-not-order, E4 cycle verdict) + the cross-OS NFC invariant; call-graph hops ≈ 2–3; LOC ≈ 300 (117 vectors are data; logic is the 4 scorers + OS-matrix wiring). Live loop, multiplied budget eligible (`autonomous-execution.md` § Feedback Loops). **Within budget.**

---

## S3b — E5–E7 byte-identical vectors (hash-equality) — critical-path long pole

- **Type:** Build
- **Value-anchor:** `briefs/00-phase-02-scope.md` §WS-1 BET-6; E7 head-commitment monotonicity is the byte-identical invariant the mandatory Rust verifier (M2/S7v) reuses — this shard is on the depth-4 critical path (S1 → S2a → **S3b** → S7v).
- **Implements:** `specs/runtime-abstraction.md` §Envoy-specific conformance (`:194-196`): E5 subset-proof verification (20 adversarial), E6 two-phase signing orphan resolution, E7 ledger head-commitment monotonicity (≥10); reused by the verifier per `independent-verifier.md:198-200`.
- **Depends:** S2a.
- **Scope:** Author + run E5–E7 as **byte-identical** vectors (Round-3 correction — these are structural, NOT semantic). E5 verifies subset-proof `runtime_verification_signature` bytes on 20 adversarial cases; E6 asserts identical two-phase orphan-resolution records (Phase-A intent / Phase-B outcome linkage); E7 asserts `head_commitment()` is byte-identical AND monotonic non-decreasing across both runtimes. **Source E7 vectors from the shared verifier corpus** (git-submodule-pin or vendored versioned fixture per `01-ws1-runtime-pluggability.md:148-151`) so there is ONE E7 truth feeding both this harness and S7v — avoid two E7 corpora.
- **Acceptance criteria:**
  - E5–E7 hash-equal across both runtimes; loop `live`.
  - E7 asserts BOTH byte-identity AND monotonic-non-decreasing (`runtime-abstraction.md:58` "Byte-identical; monotonic").
  - E7 vectors are sourced from the single shared corpus S7v also consumes (one truth, not two) — open question #2 in `_index.md` resolved here at authoring time.
  - E5's 20 adversarial subset-proof cases all verify byte-identically; a forged subset-proof fails on both runtimes identically.
- **Capacity check:** invariants ≈ 4 (E5 subset-proof bytes, E6 orphan-linkage identity, E7 byte-identity, E7 monotonicity) + the single-corpus-source invariant; call-graph hops ≈ 3 (corpus pin → scorer → adapter → verifier-shared fixture); LOC ≈ 280. Live loop. **Within budget. Critical-path shard — do not bundle with S3a; the shared-corpus decision is the load-bearing coordination point with S7v.**

---

## S3p — First-run runtime picker + `envoy runtime switch` UX state machine

- **Type:** Build+Wire
- **Value-anchor:** `briefs/00-phase-02-scope.md` §WS-1 "First-run runtime picker + `envoy runtime switch`"; ADR-0001's picker is the user-facing promise — "Run with Rust acceleration or pure-Python, default Rust, opt-out one keystroke" (`DECISIONS.md:47`) — and ADR-0009 item 4 requires transparent disclosure with no hidden defaults (`DECISIONS.md:300`).
- **Implements:** `specs/runtime-abstraction.md` §Runtime picker (`:198-200`); reconciles `selection.py:21-24` ("Phase-02: family resolution shifts to read the first-run picker output"); closes Spec-gap-6 (picker config wire format, `01-ws1-runtime-pluggability.md:547-552`).
- **Depends:** S2a (switch target must be a wired runtime to attest).
- **Scope (Build half):** Add `runtime_picker.py` mirroring the in-tree `byom_picker.py` precedent (writes a `runtime-choice` config: family + chosen-at timestamp + chosen-by Genesis); define the picker config wire schema (Spec-gap-6); change `get_runtime(family=None)` to default to reading that config instead of the hardcoded `"kailash-py"` at `selection.py:51`. **Scope (Wire half):** Add an `envoy runtime` click subgroup (`switch`/`show`) to the single click-group CLI (`cli/main.py:34`) wired to the real selection config; the `switch` state machine gates on the three-part contract (cold passphrase unlock → target attestation → Genesis-signed `runtime_switch` Ledger entry) and forces an envelope re-read checkpoint (T-015). Define the `runtime_switch` Ledger entry schema (from_family, to_family, target_attestation_hash, re_read_checkpoint_result, signed_by — Spec-gap-4, `01-ws1-runtime-pluggability.md:531-537`).
- **Acceptance criteria (Build gate):**
  - Picker writes a signed runtime-choice config; `get_runtime(family=None)` resolves from it; default is `kailash-rs-bindings` (ADR-0001) when picker has run, with the config schema documented.
  - Picker presents the one-keystroke opt-out exactly as ADR-0001 copy promises; transparent disclosure of active runtime (ADR-0009 item 4).
- **Acceptance criteria (Wire gate):**
  - `envoy runtime show` reports the active runtime from the live config; `envoy runtime switch <target>` runs the full state machine in order: cold-unlock → attest → re-read-checkpoint → Genesis-signed `runtime_switch` entry → flip default → confirm copy.
  - A warm-only Vault session refuses `switch` (cold unlock required, `runtime-abstraction.md:200`).
  - The `runtime_switch` entry is written ONLY after target attestation succeeds (ordering enforced; attestation-before-record).
- **Capacity check:** invariants ≈ 5 (picker config schema, default resolution, cold-unlock gate, switch ordering, re-read-checkpoint forcing); call-graph hops ≈ 3 (CLI → selection → picker config / ledger); LOC ≈ 400 (picker + CLI subgroup + state machine). Live loop (CLI exercisable). **At budget — separate Build (picker/config) and Wire (switch state machine) acceptance gates as listed.** Within budget.

---

## S3t — Attestation-on-switch (T-015 envelope re-read + T-060 binary-poisoning fail-closed)

- **Type:** Wire
- **Value-anchor:** `briefs/00-phase-02-scope.md` §WS-1 "attestation-on-switch" + "Phase-02 threat gates: T-015 envelope re-read checkpoint, T-060 runtime-binary-poisoning"; this is the security receipt that makes the picker trustworthy — a poisoned Rust binary can never become the active runtime.
- **Implements:** `specs/runtime-abstraction.md` §Runtime attestation (`:156-186`), §Security gates per phase (`:206` Phase-02: "binary hash verification"); T-060 fail-closed mirrors `MirrorSignatureMismatchError`/`ReproducibleBuildFailedError` (`specs/distribution.md:94-95`).
- **Depends:** S3p (the switch state machine is the host for attestation-on-switch).
- **Scope:** Fill the Phase-01 attestation stub with real values — `runtime_identity()` returns the reproducible-build `binary_hash` (not `"sha256:phase-01-software-fallback"`, `kailash_py.py:148`) and ledger export emits a populated `runtime_attestation` (not `{}`, `export.py:333-338`). Emit the `RuntimeAttestation` Ledger entry at all three moments (every `startup()`, every `runtime_switch` BEFORE the switch record, on-demand `envoy runtime attest`). On switch, verify the target's `binary_hash` against the expected reproducible-build manifest with an N=3 mirror cross-check (`distribution.md:33`); a hash mismatch or revoked key REFUSES the switch fail-closed (T-060). Force `envelope_re_read_checkpoint` as part of the switch transaction so no envelope pinned under the old runtime's `algorithm_identifier` survives (T-015; N2 invalidation trigger, `runtime-abstraction.md:150`).
- **Acceptance criteria:**
  - `RuntimeAttestation` entry emitted at all three moments with the real 5-field `RuntimeIdentity` (reconcile against the 3-field `envoy.ledger.head.RuntimeIdentity` per Spec-gap-1, `01-ws1-runtime-pluggability.md:503-515` — document which type the attestation vector uses).
  - A poisoned target (binary_hash ≠ manifest) REFUSES the switch; NO `runtime_switch` record is written (fail-closed; attestation-before-record proven by test).
  - A revoked signing key REFUSES the switch (mirrors `RevokedSigningKeyError`).
  - The switch transaction forces an envelope re-read checkpoint; a test asserts no old-algorithm-identifier-pinned envelope survives the switch (T-015).
  - `envoy runtime attest` runs the on-demand attestation and reports binary_hash vs manifest verdict.
- **Capacity check:** invariants ≈ 5 (attestation at 3 moments, binary_hash-vs-manifest, fail-closed-on-mismatch, attestation-before-record ordering, T-015 re-read forcing); call-graph hops ≈ 3 (switch → attest → manifest/mirror → ledger); LOC ≈ 350. Live loop (testable via fixture-poisoned binary). **Within budget.**

---

## Milestone capacity + sequencing summary

- **8 shards.** Wave 1 root: **S1**. Then **S2a** (gates everything). Then the conformance families **S2b, S2c, S3a, S3b** parallelize off S2a (independent corpora — size by family, not "all vectors at once", `autonomous-execution.md` § Per-Session Capacity Budget). **S3p** (←S2a) and **S3t** (←S3p) are the picker/attestation chain.
- **Critical path through M1:** S1 → S2a → S3b → (M2) S7v (depth-4). S3b is the long pole; its shared-E7-corpus decision is the coordination point with the M2 verifier.
- **Flag-flip gate:** `RS_BINDINGS_ENABLED` flips ONLY after the byte-identical slice (S2b/S2c/S3a/S3b) is green on BOTH runtimes; `kailash-py` stays the production default until the FULL N1–N6-structured + E1–E7 corpus passes (`01-ws1-runtime-pluggability.md:358-369`).
- **Open questions carried to `/implement`** (from `_index.md` + `01-ws1-runtime-pluggability.md:562-602`): contract-tier metadata format (S1 — recommend decorator), E7 single-corpus source (S3b), `RuntimeIdentity` 5-field-vs-3-field reconciliation (S3t), N4 rendered-text scoring metric (Phase-03, not Phase-02). None block M1 build.
