# Runtime-swap conformance contract

**Status:** DRAFT for Phase-00 exit gate (ROADMAP §25 + ADR-0009 sub-item 7).
**Audience:** envoy maintainers, kailash-py maintainers, kailash-rs-bindings maintainers, Foundation board (the contract underwrites the runtime-pluggability endorsement ask).
**Source contract:**

- ROADMAP.md line 25 — "Runtime-swap conformance contract drafted (both implementations feature-identical per test vectors)."
- ROADMAP.md lines 95–98 — Phase 02 exit criterion: "Cross-runtime conformance vectors pass (both runtimes behave identically)."
- ADR-0009 §312 sub-item 7 — "Runtime-swap conformance contract. Both runtime implementations must be feature-identical per cross-SDK conformance test vectors. Enforcement: every release gate."
- specs/runtime-abstraction.md (FROZEN v1) — the abstract interface this contract enforces conformance on.

**Why this draft exists:** Envoy's openness posture in CHARTER + ADR-0009 stands on the structural promise that a user who opts into `kailash-py` instead of `kailash-rs-bindings` gets the **same behaviour, only slower** — never different behaviour. Without a written conformance contract, "feature-identical" is a marketing claim with no enforcement surface. This document operationalises it: which surfaces are byte-identical, which are semantically-equivalent, what the test-vector format is, how the cross-runtime CI gate fails, and what counts as a release-blocking conformance break.

The conformance contract is the structural defence of two BETs:

- **BET-3 (Sovereignty):** the user must always have a fully-open-source runtime they can swap to without losing functionality. If `kailash-py` doesn't honour the same contract, BET-3 falsifies — sovereignty is rhetoric, not code.
- **BET-6 (Contract parity):** the cross-SDK promise that polyglot deployments produce the same bytes for the same operations.

If this contract is missing, the no-orphan-detection rule (`rules/orphan-detection.md`) applies recursively at the runtime level: a feature exposed in one runtime but not the other becomes a per-runtime orphan, the user is silently coupled to the runtime that has it, and the runtime swap is no longer a one-flag operation.

---

## 1. Operational definition of "feature-identical"

Two runtimes are **feature-identical** for the purpose of this contract iff:

1. **Surface parity.** Every method on the abstract `KailashRuntime` interface (specs/runtime-abstraction.md §13) is implemented by both runtimes. No runtime exposes a method the other does not.
2. **Tier-correct output.** For every method, the runtime's output meets the contract tier assigned to that method:
   - **Byte-identical tier:** `output_a == output_b` byte-for-byte across runtimes for the same input. Hash equality on the canonical form.
   - **Semantically-equivalent tier:** `verdict(output_a) == verdict(output_b)` per the published similarity oracle (BET-6 §3.5). Bytes may differ; the load-bearing semantic conclusion does not.
3. **Error parity.** Every error class enumerated in `specs/runtime-abstraction.md §Error taxonomy` is raised by both runtimes under the same trigger conditions, with the same error class name. The error message MAY differ (semantically-equivalent text); the typed class MUST NOT.
4. **Side-effect parity.** Methods that produce side effects (Ledger writes, Trust Vault updates, key-rotation entries) write the same canonical entries on both runtimes, byte-identical on the entry's canonical form, even when the wall-clock timestamps differ (timestamps are excluded from canonical form per specs/ledger.md).

A runtime that fails ANY of (1)–(4) for ANY method on ANY input fixture in the conformance corpus is **non-conformant** and blocks release.

## 2. The two-tier contract

### 2.1 Byte-identical surfaces

| Surface                                   | Method(s)                                                                                   | Why byte-identical?                                                                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Canonical-form serialisation              | `envelope_canonical_form`, `trust_sign` (over canonical form), `ledger_append` (entry hash) | JCS RFC 8785 + NFC. The whole point of canonical form is byte-identity across implementations.                                         |
| Hash-chain construction                   | `ledger_append`, `head_commitment`, `ledger_verify_chain`                                   | Hash chain integrity is byte-bound — any divergence breaks chain verification across runtimes.                                         |
| Cryptographic signature verification      | `trust_verify_chain`, `runtime_verify`                                                      | Ed25519 verification is byte-deterministic; cross-runtime verification is the structural test.                                         |
| Set equality on cascade revocation        | `trust_cascade_revoke`                                                                      | Set equality is byte-equality on the sorted member set; ordering may differ (BFS vs DFS).                                              |
| Envelope intersection                     | `envelope_intersect`                                                                        | Output envelope is canonical-form; intersection algorithm is deterministic per spec.                                                   |
| Subset-proof verification                 | `trust_verify_subset_proof`                                                                 | Specs/sub-agent-delegation.md `is_subset_envelope` is a structural algorithm — byte-deterministic.                                     |
| Budget arithmetic                         | `budget_reserve`, `budget_record`, `budget_snapshot`, `budget_velocity_check`               | Integer microdollar arithmetic — no float drift, no rounding.                                                                          |
| Classifier ensemble aggregation           | `ensemble_aggregate`                                                                        | Aggregation function over verdicts is deterministic; classifier-internal LLM calls are not aggregated, only their structured verdicts. |
| Two-phase signing record fields           | `phase_a_sign_intent`, `phase_b_sign_outcome` (signed-canonical fields)                     | Signed canonical fields excluding wall-clock timestamps; signature bytes byte-identical.                                               |
| Envelope re-read checkpoint result        | `envelope_re_read_checkpoint`                                                               | Reads canonical envelope from Trust Vault — bytes from disk.                                                                           |
| First-time-action gate fingerprint        | `first_time_action_gate` (gate-result hash component)                                       | Specs/session-state.md fingerprint hash — byte-deterministic.                                                                          |
| Tool-output sanitisation result structure | `tool_output_sanitize` (verdict + structural fields)                                        | Structural sanitisation verdict; LLM-provided text content is in the §Semantically-equivalent tier.                                    |
| Runtime device-key signing                | `runtime_sign`, `runtime_verify`                                                            | Ed25519 over canonical-form payload.                                                                                                   |
| Prompt-assembly canonical hash            | `prompt_assemble.rendered_canonical_hash`                                                   | Canonical form of (system_prompt, envelope_pin, context_slice, user_message) per BET-6 §6.                                             |

### 2.2 Semantically-equivalent surfaces

| Surface                              | Method(s)                                                | Why semantically-equivalent?                                                           |
| ------------------------------------ | -------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Agent reasoning text                 | LLM-driven response generation under any abstract method | LLMs are non-deterministic across runtimes (tokenisation, temperature, batching).      |
| Grant Moment prompt text             | `grant_moment_surface.prompt_text`                       | LLM-rendered for the user; structured payload (action, scope, posture) byte-identical. |
| Tool-call timing metadata            | observability metadata on `tool_output_sanitize`         | Wall-clock + jitter; consistent under byte-identical structural payload.               |
| Classifier verdict explanations      | `classifier_invoke.explanation`                          | LLM-rendered; structured `verdict_class` field byte-identical.                         |
| `prompt_assemble.rendered_bytes`     | `prompt_assemble.rendered_bytes`                         | Tokenisation may differ; canonical hash byte-identical.                                |
| `tool_output_sanitize.text_for_user` | `tool_output_sanitize.text_for_user`                     | LLM-rendered explanation; structural sanitisation outcome byte-identical.              |

### 2.3 The promotion question

A surface in the §Semantically-equivalent tier MAY be promoted to §Byte-identical if a security threat surfaces that requires the bytes themselves to be deterministic (e.g. a token-bucket replay defence on tool-call timing metadata). Promotion is a contract change and triggers a full-sibling re-derivation per specs-authority.md MUST Rule 5b.

The reverse — demotion from byte-identical to semantically-equivalent — is BLOCKED. Once a surface is byte-identical, it stays byte-identical. Demotion would silently widen the runtimes' permitted divergence.

## 3. Test-vector format

A conformance vector is a JSON fixture with this canonical shape. Every vector in the corpus conforms to this schema; any vector that does not validate against the schema is rejected at corpus-load time.

```json
{
  "schema_version": "envoy-conformance-vector/1.0",
  "vector_id": "<unique stable id, e.g. N3-005-structural-grant-required>",
  "vector_class": "N1 | N2 | N3 | N4 | N5 | N6 | E1 | E2 | E3 | E4 | E5 | E6 | E7",
  "tier": "byte-identical | semantically-equivalent",
  "method_under_test": "envelope_canonical_form | trust_sign | ledger_append | ...",
  "spec_anchor": "specs/runtime-abstraction.md §Envelope",
  "spec_section_hash": "sha256:<hash of the anchor section at corpus mint time>",
  "input": {
    "//": "free-form input object whose shape is method-specific",
    "envelope": { ... },
    "action": { ... },
    "session_state": { ... }
  },
  "expected": {
    "//": "byte-identical tier: literal expected output (or hash of it for large outputs)",
    "//": "semantically-equivalent tier: verdict + similarity-oracle metadata",
    "output_canonical_hash": "sha256:...",
    "raises": null,
    "verdict": "PASS | FAIL | GRANT_REQUIRED | ..."
  },
  "tolerance": {
    "//": "applies only to semantically-equivalent tier; absent for byte-identical",
    "similarity_oracle": "exact-match | levenshtein<=N | sbert-cosine>=0.95 | ...",
    "ignore_fields": ["timestamps.wall_clock_ms", "metadata.runtime_internal_id"]
  },
  "provenance": {
    "minted_at": "<iso8601>",
    "minted_by": "envoy-phase-NN | foundation-mint | ...",
    "discovery_round": "R3 | post-incident | mint",
    "associated_threats": ["T-015"],
    "associated_bets": ["BET-6", "BET-3"]
  }
}
```

**Key invariants:**

1. **`tier` is per-vector, not per-method.** A method may have vectors in BOTH tiers — e.g. `tool_output_sanitize` has byte-identical vectors for the structural verdict AND semantically-equivalent vectors for the user-facing text. Both tiers' vectors share the same `method_under_test`.
2. **`spec_section_hash` is mint-time-frozen.** Vectors trace to a specific anchor of the spec at the moment they were authored. If the spec changes, the vector's hash mismatch surfaces as a re-derivation requirement (specs-authority.md MUST Rule 5b).
3. **`expected.output_canonical_hash` is the byte-identical assertion handle.** Both runtimes produce the same canonical hash, or the vector fails. The hash-prefix distinguishes hash domains (`sha256:` for content, `sha256-jcs:` for canonical-form-then-hash to make it clear the comparator is canonical-form-aware).
4. **`tolerance` is mandatory for semantically-equivalent vectors.** A semantic vector with no oracle is a dead vector — it can never fail.
5. **`provenance.associated_threats` cross-references threats from specs/threat-model.md** so a vector failure can be triaged back to the user-facing risk it defends against.

## 4. Vector corpus enumeration

The conformance corpus is composed of two families:

| Family                               | Source                                                                                                                                                | Vector count target                      | Cadence                                                                                                   |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **N-vectors** (Foundation cross-SDK) | Foundation publishes the canonical N1–N6 corpus at `terrene.foundation/conformance/n-vectors/v{X}/` per ADR-0001. envoy consumes by reference + hash. | 70 (10+15+10+10+15+10)                   | Per Foundation release cadence (Phase 02+).                                                               |
| **E-vectors** (Envoy-specific)       | envoy authors and maintains under `tests/fixtures/conformance/e-vectors/` in this repo.                                                               | 132 (67+20+15+15+20+arbitrary+arbitrary) | Per envoy release; new vectors land with PRs that fix conformance regressions or add adversarial corpora. |

### 4.1 N-vector breakdown

| ID  | Surface                               | Vector count | Tier                                                         | Maps to specs/runtime-abstraction.md method                              |
| --- | ------------------------------------- | ------------ | ------------------------------------------------------------ | ------------------------------------------------------------------------ |
| N1  | Knowledge filter (pre-retrieval gate) | 10           | byte-identical                                               | `envelope_check` against `field_allowlist_per_model` + DataFlow boundary |
| N2  | Envelope cache invalidation           | 15           | byte-identical                                               | Cache layer behind `envelope_check` (5-property invalidation)            |
| N3  | Structural-vs-semantic partition      | 10           | byte-identical (partition)                                   | `envelope_check.classifier_breakdown`                                    |
| N4  | Verdict rendering                     | 10           | byte-identical (structured) + semantically-equivalent (text) | `grant_moment_surface`, `envelope_check.verdict_text`                    |
| N5  | Posture ceiling                       | 15           | byte-identical                                               | `envelope_check.effective_posture`                                       |
| N6  | Session-scoped cache correctness      | 10           | byte-identical                                               | `first_time_action_gate.fingerprint`                                     |

### 4.2 E-vector breakdown

| ID  | Surface                                 | Vector count   | Tier           | Maps to specs/runtime-abstraction.md method          |
| --- | --------------------------------------- | -------------- | -------------- | ---------------------------------------------------- |
| E1  | Envelope canonical JSON                 | 67             | byte-identical | `envelope_canonical_form`                            |
| E2  | Delegation Record signing               | 20             | byte-identical | `trust_sign` over `DelegationRecord`                 |
| E3  | Cascade revocation BFS/DFS set equality | 15             | byte-identical | `trust_cascade_revoke` (set equality, ordering free) |
| E4  | Cycle detection                         | 15             | byte-identical | `trust_verify_chain` cycle-detection branch          |
| E5  | Subset-proof verification               | 20 adversarial | byte-identical | `trust_verify_subset_proof`                          |
| E6  | Two-phase signing orphan resolution     | TBD (≥10)      | byte-identical | `phase_a_orphan_resolve`                             |
| E7  | Ledger head-commitment monotonicity     | TBD (≥10)      | byte-identical | `head_commitment`, `ledger_append`                   |

Phase-00 exits with the schema fixed and the N1–N6 + E1–E5 corpora populated by reference. E6 + E7 vector counts are filled at Phase-01 mint cadence (per `specs/runtime-abstraction.md §Open questions §1`).

## 5. Surface-by-surface conformance disposition

The table below covers every method on the abstract `KailashRuntime` interface, the contract tier it sits in, the vector class that exercises it, and any tolerance band. This table is the single source of truth for cross-runtime conformance — if a method is missing here, it is unenforced; if a method is present here, its conformance is binding.

| Method                        | Tier                                                                            | Vector class   | Tolerance band                                                                                                        |
| ----------------------------- | ------------------------------------------------------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------- |
| `startup`                     | byte-identical                                                                  | E7-startup     | `attestation_emitted_at` excluded from canonical form; `binary_hash` MUST match expected per runtime                  |
| `shutdown`                    | byte-identical                                                                  | E7-shutdown    | Side-effect: pending Ledger writes flushed; in-memory secrets zeroed (verifiable via heap scan)                       |
| `runtime_identity`            | byte-identical                                                                  | E7-identity    | `version` differs (kailash-py vs kailash-rs-bindings); `algorithm_identifier` MUST match exactly                      |
| `trust_sign`                  | byte-identical                                                                  | E2             | None — Ed25519 over canonical form                                                                                    |
| `trust_verify_chain`          | byte-identical                                                                  | E4             | None                                                                                                                  |
| `trust_cascade_revoke`        | byte-identical                                                                  | E3             | Set equality only — ordering of returned `set[str]` may differ                                                        |
| `trust_verify_subset_proof`   | byte-identical                                                                  | E5             | None                                                                                                                  |
| `envelope_canonical_form`     | byte-identical                                                                  | E1             | None — JCS RFC 8785 + NFC                                                                                             |
| `envelope_intersect`          | byte-identical                                                                  | E1 + E5        | None                                                                                                                  |
| `envelope_check`              | byte-identical                                                                  | N3 + N5        | `latency_ms` excluded; `failed_checks[].error_message` is text but error class is byte-identical                      |
| `envelope_re_read_checkpoint` | byte-identical                                                                  | N2 + T-015 reg | None                                                                                                                  |
| `phase_a_sign_intent`         | byte-identical                                                                  | E6             | `intent_id` UUID-v7 — vector pins generator seed; `phase_a_signed_at` excluded from canonical                         |
| `phase_b_sign_outcome`        | byte-identical                                                                  | E6             | Same as above for `phase_b_signed_at`                                                                                 |
| `phase_a_orphan_resolve`      | byte-identical                                                                  | E6             | None                                                                                                                  |
| `ledger_append`               | byte-identical                                                                  | E7             | `entry_id` UUID-v7 — vector pins generator seed                                                                       |
| `ledger_query`                | byte-identical                                                                  | N4             | Returned ordering pinned by query spec (specs/ledger.md §Query)                                                       |
| `ledger_verify_chain`         | byte-identical                                                                  | E7             | None                                                                                                                  |
| `head_commitment`             | byte-identical                                                                  | E7             | `committed_at` excluded                                                                                               |
| `classifier_invoke`           | semantically-equivalent                                                         | N4             | Tolerance: `verdict_class ∈ {PASS, FAIL, ESCALATE}` byte-identical; `explanation` text similarity ≥ SBERT cosine 0.85 |
| `ensemble_aggregate`          | byte-identical                                                                  | N3 + N4        | None — aggregation is structural over the verdicts                                                                    |
| `classifier_registry_resolve` | byte-identical                                                                  | N4-registry    | None                                                                                                                  |
| `budget_reserve`              | byte-identical                                                                  | E7-budget      | None — integer microdollars                                                                                           |
| `budget_record`               | byte-identical                                                                  | E7-budget      | None                                                                                                                  |
| `budget_snapshot`             | byte-identical                                                                  | E7-budget      | None                                                                                                                  |
| `budget_velocity_check`       | byte-identical                                                                  | E7-budget      | None                                                                                                                  |
| `runtime_sign`                | byte-identical                                                                  | E2             | None                                                                                                                  |
| `runtime_verify`              | byte-identical                                                                  | E2             | None                                                                                                                  |
| `prompt_assemble`             | byte-identical (canonical hash) + semantically-equivalent (rendered_bytes)      | N4             | `rendered_canonical_hash` byte-identical; `rendered_bytes` token-equivalent under tokenizer-version pin               |
| `tool_output_sanitize`        | byte-identical (verdict + structural) + semantically-equivalent (text_for_user) | N3 + N4        | Structural sanitisation result byte-identical; user-facing text similarity ≥ SBERT cosine 0.85                        |
| `first_time_action_gate`      | byte-identical                                                                  | N6             | None — fingerprint hash is structural                                                                                 |
| `grant_moment_surface`        | byte-identical (structured payload) + semantically-equivalent (prompt_text)     | N4             | Structured request/result byte-identical; user-visible text under similarity-oracle                                   |

## 6. Tolerance bands for non-determinism

Non-determinism in the conformance layer is enumerated and bounded. Anything not listed here is BLOCKED — a method that produces non-deterministic output for a class not in this list is non-conformant.

### 6.1 Wall-clock timestamps

Every method that records a timestamp emits both:

- A **canonical-form payload** with the timestamp **excluded** (the byte-identical surface).
- A **wall-clock timestamp field** outside the canonical payload (the per-runtime surface).

The canonical payload is what gets signed; the timestamp is metadata. Vector assertions are against the canonical payload; the timestamp field is checked against a tolerance window (`abs(ts_a - ts_b) < 5s` is acceptable when both runtimes execute the same vector in the same CI run).

### 6.2 UUID generation

UUID-v7 contains a wall-clock prefix + random tail. Vectors that need to assert `entry_id` / `intent_id` / `prompt_id` byte-identity pin the **generator seed** (24-byte deterministic seed for the random tail; first 8 bytes are wall-clock-derived and are part of the vector input, not the runtime's state). Both runtimes accept the seed via `RuntimeConfig.deterministic_uuid_seed` (Phase 02 conformance-mode-only flag).

### 6.3 Ordering of `set[T]` returns

Methods returning a set (most prominent: `trust_cascade_revoke`) may emit elements in BFS-vs-DFS-different order. Vectors assert **set equality**, not list equality. The vector's `expected` field is a sorted list; the runner sorts the runtime's output before comparison.

### 6.4 LLM-driven text

Text fields produced by an LLM (Grant Moment prompt text, classifier explanation, tool-output user-facing text) are compared via the **similarity oracle** specified in the vector's `tolerance.similarity_oracle` field. The oracle defaults to SBERT cosine ≥ 0.85, with the option for stricter `levenshtein<=10` on short structured strings.

The similarity oracle's MODEL is itself version-pinned in the vector — a vector minted against `sbert-en-2024-q4` continues to use that model even if the Foundation publishes a newer one. Oracle-model upgrades are handled by minting NEW vectors that pin the new oracle; old vectors stay with the old oracle until retired.

### 6.5 Tokenisation drift on `prompt_assemble.rendered_bytes`

Different tokenisers produce different rendered bytes for the same prompt. The runner pins the tokeniser via `PromptAssembleConfig.tokenizer_version`; vectors assert byte-identity under the pinned tokeniser. Runtime-internal tokenisation experiments (e.g. switching from BPE to SentencePiece) require new vectors.

### 6.6 Latency / jitter

Every method has a per-class latency budget (specs/envelope-model.md §80). Vectors do NOT assert latency (cross-runtime latency is expected to differ by ~8× — Rust is faster). Latency is enforced by `acceptance-metrics.md` thresholds, not by conformance vectors.

## 7. Runner contract

Each runtime ships a **conformance runner** binary that:

1. Reads the conformance corpus from a directory (or URI).
2. Loads each vector, validates against the schema, computes the spec-anchor hash and asserts it matches the spec at runtime time (so a stale vector against a moved spec section is detected).
3. Drives the runtime through the `method_under_test` with the vector's `input`.
4. Compares the runtime's output to the vector's `expected` per the tier's comparator.
5. Emits a per-vector verdict to a structured report (JSON).

### 7.1 kailash-py runner

Lives at `tests/conformance/runner_py.py` in this repo. Driven by pytest:

```
pytest tests/conformance/ \
  --runtime=kailash-py \
  --corpus-dir=tests/fixtures/conformance/ \
  --report=.conformance-report-py.json
```

Per ROADMAP + ADR-0009 + kailash-py#605: kailash-py implements PACT N4/N5 vector consumption as a Phase 02 blocker. The Python runner is the canonical reference implementation for the runner contract.

### 7.2 kailash-rs-bindings runner

Lives at `tests/conformance/runner_rs.py` (same repo, Python entry point because the binding surface is Python). Driven by pytest:

```
pytest tests/conformance/ \
  --runtime=kailash-rs-bindings \
  --corpus-dir=tests/fixtures/conformance/ \
  --report=.conformance-report-rs.json
```

The rs-bindings runner imports `kailash` (Rust-binding package), constructs an `RsRuntime`, and drives it through the same vector corpus. The runner code is deliberately runtime-agnostic — it depends only on the abstract `KailashRuntime` interface; the runtime-specific instantiation is a single-line factory.

### 7.3 Cross-runtime comparator

A third process consumes both reports and emits the final verdict:

```
python tests/conformance/cross_runtime_comparator.py \
  --report-py=.conformance-report-py.json \
  --report-rs=.conformance-report-rs.json \
  --verdict=.cross-runtime-verdict.json
```

The comparator's verdict rules:

- For each `vector_id`, both reports must contain a result.
- Tier byte-identical: `report_py[vector_id].output_canonical_hash == report_rs[vector_id].output_canonical_hash`.
- Tier semantically-equivalent: similarity oracle invoked over the two outputs; passes iff ≥ tolerance threshold.
- Any mismatch is a CONFORMANCE_BREAK with severity `RELEASE_BLOCKER`.

The verdict file is the artefact the CI gate publishes.

## 8. Cross-runtime CI gate

### 8.1 Trigger

The cross-runtime CI gate runs:

1. On every PR that modifies `specs/runtime-abstraction.md`, `specs/envelope-model.md`, `specs/trust-lineage.md`, `specs/ledger.md`, or any `tests/conformance/**` file in this repo.
2. On every PR in `kailash-py` or `kailash-rs-bindings` that touches a runtime-abstraction-implementing file (gated by upstream CI hooks; envoy CI re-runs to confirm).
3. On every release-tag of `envoy`, `kailash-py`, or `kailash-rs-bindings`.

### 8.2 What it asserts

For every vector in the corpus, both runtimes produce a matching result per §7.3. The full verdict must be `ALL_PASS` — any single CONFORMANCE_BREAK fails the gate.

### 8.3 What it produces

`.cross-runtime-verdict.json` artefact with per-vector breakdown:

```json
{
  "schema_version": "envoy-conformance-verdict/1.0",
  "verdict": "ALL_PASS | CONFORMANCE_BREAK",
  "corpus_total": 202,
  "passed": 202,
  "failed": 0,
  "breakdown": {
    "byte-identical": { "total": 198, "passed": 198, "failed": 0 },
    "semantically-equivalent": { "total": 4, "passed": 4, "failed": 0 }
  },
  "failures": [],
  "runtime_versions": {
    "kailash-py": "X.Y.Z",
    "kailash-rs-bindings": "X.Y.Z"
  },
  "corpus_version_hash": "sha256:<hash of the vector corpus directory>",
  "generated_at": "<iso8601>"
}
```

When `verdict = CONFORMANCE_BREAK`, `failures[]` lists each broken vector with its `vector_id`, `tier`, the two outputs, and the comparator's distinguishing finding.

### 8.4 Failure handling

When a vector breaks:

1. **Specific runtime is at fault.** The CI gate triages: which runtime produced the deviation? If the vector's `expected.output_canonical_hash` matches one runtime's output and not the other's, the deviating runtime is marked authoritative-fault.
2. **Spec is ambiguous.** If both runtimes produce different but plausible outputs and the vector's `expected` matches neither, the spec section pointed to by `spec_anchor` is ambiguous. This triggers a spec-clarity issue against the spec, NOT against either runtime.
3. **Vector is stale.** If the vector's `spec_section_hash` no longer matches the current spec section, the vector is stale and is regenerated against the new spec section. The CI gate fails until the regeneration lands.

In all three cases, the gate is RELEASE_BLOCKING. No release of `envoy`, `kailash-py`, or `kailash-rs-bindings` may ship while the gate is red.

### 8.5 Adversarial vector escalation

A NEW vector minted by `/redteam` or by a security disclosure is provisionally ADVISORY (failing it warns but does not block) for one release cycle. After one release cycle the vector becomes BLOCKING. This avoids a freshly-minted vector blocking an in-flight release that was prepared before the vector existed.

The advisory window is documented in the vector's `provenance` block:

```json
"provenance": {
  ...
  "discovery_round": "post-incident",
  "advisory_until": "<iso8601 — set to 'now + 30 days' at mint>",
  "blocking_after": "<iso8601 — same value>"
}
```

After `blocking_after`, the runner promotes the vector to RELEASE_BLOCKER automatically.

## 9. Vector lifecycle

### 9.1 Minting

A new vector is minted when:

- A new method lands on the abstract `KailashRuntime` interface (vector is mandatory before the method ships in either runtime).
- A `/redteam` round produces an adversarial fixture not yet in the corpus.
- A field-incident (a user-reported bug) reveals a divergence between runtimes; the regression test becomes a vector.
- The Foundation publishes a new N-vector or revises an existing one.

The minter:

1. Drafts the vector JSON, including `spec_anchor` and `spec_section_hash`.
2. Validates against the schema.
3. Runs the vector against both runtimes; vectors are MINT-PASS only if both runtimes pass — a vector that fails one runtime at mint time is a regression masquerading as a vector. (Exception: adversarial vectors that intentionally test for a not-yet-implemented defence; these are minted with `tier_assertion: deferred` and an issue tracking implementation.)
4. PRs the vector with the regression-test PR (or to envoy alone if no implementation change is needed).

### 9.2 Retiring

A vector is retired when:

- The spec section it anchors to is removed (the contract surface no longer exists).
- The threat it tests is reclassified as out-of-scope.
- It is replaced by a more comprehensive vector.

Retirement requires:

1. Updating `provenance.retired_at` + `provenance.retirement_reason`.
2. Moving the vector to `tests/fixtures/conformance/retired/` (preserves history; runner skips this directory).
3. Recording the retirement in the same PR that justifies it.

A retired vector MUST NEVER be deleted from the corpus directory tree. The audit trail is the corpus history.

### 9.3 Spec-anchor hash invalidation

When a spec section's text changes (e.g. specs/runtime-abstraction.md §Envelope is edited), every vector whose `spec_anchor` points to that section MUST be re-derived. The CI gate detects stale vectors at runtime and fails:

```
[ERROR] Vector N3-005-structural-grant-required has stale spec_section_hash.
        spec_anchor: specs/runtime-abstraction.md §Envelope
        expected:    sha256:abc123...
        observed:    sha256:def456...
        Action:      re-derive vector against current spec section, or revert spec edit.
```

Re-derivation is a small operation (inputs unchanged; expected output recomputed against the current spec) but it is mandatory.

## 10. Phase migration

The conformance contract evolves across phases as the runtimes mature.

| Phase | Conformance gate state                                                                                                                                         |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 00    | Contract drafted (this document); abstract interface frozen (specs/runtime-abstraction.md FROZEN v1); vector corpus skeleton in place.                         |
| 01    | kailash-py runtime ships; E1–E7 vectors green against kailash-py-only (N-vectors are advisory because Foundation N-corpus runner depends on Phase-02 binding). |
| 02    | kailash-rs-bindings ships; cross-runtime gate goes RELEASE_BLOCKING for ALL vectors (N1–N6 + E1–E7). PACT N4/N5 Python runner lands (kailash-py#605).          |
| 03    | Semantic-equivalence harness lands (similarity oracle + adversarial corpus); §6.4 LLM-text vectors enforce.                                                    |
| 04    | Multi-provider verification (cross-runtime over multiple LLM providers); reproducible-build verification stream feeds vector minting.                          |

**Phase-00 exit:** this document + skeleton corpus + the Phase-01 ramp plan above. Phase-00 does NOT require the gate to be green — it requires the contract to be written and the runners to be designable from it.

## 11. The "feature-identical" promise — what the user sees

When a user installs envoy with the `kailash-py` runtime instead of `kailash-rs-bindings`:

| Property                                                                                                  | Both runtimes deliver?                                                                                                                                                              |
| --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Every CLI command (`envoy init`, `envoy boundaries`, `envoy ledger export`, `envoy runtime switch`, etc.) | Yes. CLI surface is uniform.                                                                                                                                                        |
| Every Grant Moment behaves identically (same envelope check → same verdict)                               | Yes (byte-identical envelope_check)                                                                                                                                                 |
| Every Ledger entry's canonical hash is identical                                                          | Yes (byte-identical ledger_append + canonical form)                                                                                                                                 |
| Every Trust Vault export imports identically into the other runtime                                       | Yes (byte-identical trust_sign + envelope_canonical_form)                                                                                                                           |
| Every channel-adapter behaves identically                                                                 | Yes (channels are over the abstract interface)                                                                                                                                      |
| Every Daily Digest renders the same structure (numbers, counts, titles)                                   | Yes (structured payload byte-identical)                                                                                                                                             |
| Every Daily Digest renders the same exact text                                                            | NO — text is semantically-equivalent (similarity oracle), not byte-identical. The structural numbers / counts are byte-identical; the natural-language summary may differ slightly. |
| Hot-path latency is identical                                                                             | NO — Rust is ~8× faster (per acceptance-metrics.md). The semantic outcome is the same; the time to compute it is not.                                                               |
| Binary distribution model is identical                                                                    | NO — kailash-rs-bindings ships a compiled binary (per ADR-0009 composite license); kailash-py is pure Python (per ADR-0009).                                                        |

The "feature-identical" promise is precisely: the user gets the same SECURITY POSTURE, the same LEDGER, the same ENVELOPES, the same GRANT MOMENTS — only at different speeds and through different distribution channels. This is the structural promise the conformance contract enforces.

## 12. Open questions / Phase-01 carry-forward

1. **N3 + N6 corpus filling cadence.** specs/runtime-abstraction.md §Open questions §1 — when does the Foundation publish the canonical N3 + N6 corpora? This contract assumes Phase-02 cadence; if the Foundation slips, kailash-py#605 (N4/N5 runner) inherits the slip.
2. **Semantic-equivalence harness scoring.** specs/runtime-abstraction.md §Open questions §3 — what is the canonical similarity metric for "semantically-equivalent" Grant Moment text across runtimes, and what divergence threshold escalates to a BET-6 falsifier? §6.4 of this document proposes SBERT cosine ≥ 0.85; counsel + Foundation cryptographic-review confirm.
3. **Reproducible-build stream cadence.** specs/runtime-abstraction.md §Open questions §4 — does runtime startup gate on at-least-N-reproducer-confirmations or accept first-confirmation? §10 Phase 04 row depends.
4. **Tokeniser-pin propagation.** §6.5 pins the tokeniser; if the Foundation later mandates a different tokeniser for the prompt-assembly canonical form, every prompt-assemble vector re-derives. Does the Foundation own the tokeniser pin, or does each runtime declare its own and the contract asserts compatibility?
5. **Conformance-mode-only flags.** §6.2 introduces `RuntimeConfig.deterministic_uuid_seed` as a conformance-mode-only flag. Does the abstract interface formally declare conformance-mode flags as a separate type-bag, or are they regular config fields with mode-gated semantics? Phase-02 design item.
6. **Vector corpus distribution.** Where is the canonical corpus hosted? `terrene.foundation/conformance/` vs `github.com/terrene-foundation/conformance-vectors` vs in-repo at `tests/fixtures/conformance/`. The latter is operationally simplest but couples envoy releases to Foundation-vector releases. Phase-01 decision.

---

**Cross-references:**

- specs/runtime-abstraction.md (FROZEN v1) — abstract interface this contract enforces conformance on
- specs/envelope-model.md §Canonical JSON — JCS RFC 8785 + NFC source for E1
- specs/trust-lineage.md §Chain verification — E2/E4 source
- specs/ledger.md §Hash chain + §Head commitment — E7 source
- specs/sub-agent-delegation.md §`is_subset_envelope` — E5 source
- specs/threat-model.md (50 threats) — `provenance.associated_threats` cross-reference target
- specs/acceptance-metrics.md — Phase-by-phase exit criteria + latency thresholds
- ADR-0001 (DECISIONS.md §3) — runtime architecture + conformance vectors at every release gate
- ADR-0009 (DECISIONS.md §276) — runtime-pluggability + sub-item 7 (conformance contract)
- ROADMAP.md §25 — the gate-item this draft closes
- workspaces/phase-00-alignment/issues/manifest.md — kailash-py#605 (N4/N5 Python runner Phase-02 blocker), kailash-rs#503-#519 (binding-surface gaps)
- 03-license-compatibility-statement.md — license compatibility for the runtime-pluggability stack the conformance contract underwrites
- 01-envoy-concept-one-pager.md — Foundation board ask; this contract is the substantive backstop for the "feature-identical" framing in §"What we are asking the Board to endorse"

**Drafted:** 2026-05-01 by envoy Phase-00 work, in response to ROADMAP §25 + ADR-0009 sub-item 7.
**Review owners:** envoy Phase-00 maintainers (substantive sign-off); kailash-py + kailash-rs-bindings maintainers (runner-side adoption); Foundation cryptographic review (semantic-equivalence oracle confirmation §6.4); Foundation board (endorsement of "feature-identical" framing this contract enforces).
