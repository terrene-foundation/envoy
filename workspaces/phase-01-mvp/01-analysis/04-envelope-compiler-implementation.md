# 04 — Envelope Compiler Implementation

**Document role:** Phase 01 implementation deep-dive for the Envelope Compiler primitive (shard 4 of /analyze, first of the per-primitive shards 4–19). Establishes the verified upstream provider, the Envoy-new-code surface, and the integration contract for downstream primitives that consume envelopes.

**Date:** 2026-05-04 (shard 4 of /analyze).
**Status:** DRAFT — load-bearing for shards 8 (Boundary Conversation), 10 (Grant Moment), 5 (Trust store), 16 (Channel adapters).
**Discipline:** Cite, do not paraphrase frozen specs. Per `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, Phase 01 /analyze MUST cite Phase 00 artifacts by path + section, never paraphrase. The shard's question is NEVER "is this spec right?"; it is "given this spec is frozen, how do I wire `kailash-py` to deliver it?"

---

## 1. Source spec citation

Frozen specs the compiler implements against (cited; not edited):

- `specs/envelope-model.md` § Schema (top-level `EnvelopeConfig` JSON wire format) — owns the canonical 5-dimension schema and the `metadata.algorithm_identifier` block.
- `specs/envelope-model.md` § Algorithms § "Canonical JSON (§14.1 of source)" — RFC 8785 JCS + NFC normalization + integer microdollars + lexicographic ordering. Cross-runtime byte-identity per BET-6.
- `specs/envelope-model.md` § Algorithms § "`intersect_envelopes(a, b)` (§14.5 of source)" — per-dimension MIN ceilings, INTERSECTION allowlists, UNION denylists; raises `AlgorithmMismatchError`, `SchemaVersionMismatchError`, `IntersectConflictError` per § Error taxonomy.
- `specs/envelope-model.md` § Algorithms § "Naming convention (Round 2 R2-HIGH closure)" — `intersect_envelopes` is the algorithm spec name; `envelope_intersect` is the runtime ABC method name; both refer to the same canonical algorithm.
- `specs/envelope-model.md` § Error taxonomy — 24 typed errors, each Ledger-recorded with `content_trust_level: system`; error messages MUST NOT echo raw envelope content.
- `specs/sub-agent-delegation.md` § "`is_subset_envelope` algorithm" — runtime re-derives the SubsetProof from full parent + sub envelopes; parent-supplied proof is hint only (R2-H2 fix). The compiler must be capable of producing the inputs `is_subset_envelope` consumes.
- `specs/envelope-library.md` § "Trust tiers" + § "Cross-domain consumer mapping" — template provenance flows into `metadata.authorship_score.template_provenance` and per-dimension `imported_constraints[]` lists; the compiler is the integration owner for resolving template imports at compile time.
- `specs/cross-domain-flows.md` § "Concept" + § "Algorithm" — `cross_domain_rules_authored` is a top-level array on the compiled envelope; imported cross-domain rules fold into this list with `authored=false` semantics at template-import time (`specs/envelope-model.md` § Field semantics for late-added fields).
- `specs/tool-output-sanitization.md` § "Surface" — `tool_output_sanitize(output, tool_name, envelope)` consumes `envelope.semantic_checks.tool_output_classifier_ensemble` + `envelope.tool_output_budget_bytes`; the compiler MUST emit both fields populated for every shipped envelope or T-010/T-011 structural defense fails closed unnecessarily.

---

## 2. Verified provider citation

**Provider module:** `kailash.trust.pact.envelopes` (kailash-py SDK, pure-Python).

**Verified exports** (read 2026-05-03 from `~/repos/loom/kailash-py/src/kailash/trust/pact/envelopes.py`):

- `intersect_envelopes(a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig, *, dimension_scope: frozenset[str] | None = None) -> ConstraintEnvelopeConfig` — defined line 336; per-dimension MIN/INTERSECTION/UNION semantics matching `specs/envelope-model.md` § "`intersect_envelopes(a, b)`"; supports EATP `#170` dimension-scoped delegation.
- `RoleEnvelope` — `@dataclass(frozen=True)` defined line 419; carries `defining_role_address`, `target_role_address`, `envelope: ConstraintEnvelopeConfig`, `gradient_thresholds: GradientThresholdsConfig | None`, `version: int`.
- `RoleEnvelope.validate_tightening(...)` — staticmethod line 437; enforces monotonic tightening with `_validate_finite()` NaN/Inf guards (per `.claude/rules/pact-governance.md` security invariant 5).
- `TaskEnvelope` — `@dataclass(frozen=True)` defined line 690; `parent_envelope_id`, `envelope`, `expires_at`; `is_expired` property at line 706.
- `compute_effective_envelope(role_address, role_envelopes, task_envelope=None, org_envelope=None) -> ConstraintEnvelopeConfig | None` — defined line 716; walks accountability chain root→target intersecting RoleEnvelopes, then applies active TaskEnvelope.
- `compute_effective_envelope_with_version(...) -> EffectiveEnvelopeSnapshot` — defined line 794; returns SHA-256 `version_hash` over ancestor envelope versions for TOCTOU defense.
- All 7 symbols re-exported via `kailash.trust.pact.__init__.py` `__all__` (lines 100–142).

**Verified closure (per `03-kailash-py-mvp-readiness.md` § 5 verification protocol):**

- ISS-02 ↔ `terrene-foundation/kailash-py#594` — closed 2026-04-24T17:01:13Z (`gh issue view 594 --repo terrene-foundation/kailash-py --json closedAt`).
- `closedByPullRequestsReferences: []` — no merging PR; the closure was an "already-satisfied" Foundation-voice comment by `esperie` (issue comment ID `IC_kwDORmHuac8AAAABATBhaw`, 2026-04-24T17:01:12Z).
- Citable evidence in the close comment: cross-SDK byte-identity test `tests/unit/cross_sdk/test_envelope_round_trip.py::test_envelope_intersection_matches_fixture` consumes the canonical fixture `envelope_with_intersection.json`; same fixture consumed by kailash-rs `eatp::constraints::ConstraintEnvelope::intersect` for cross-SDK parity (EATP D6). Verified passing 2026-04-25.
- 190 internal tests across 5 files (`test_envelopes.py` 75, `test_envelope_properties.py` 42, `test_dimension_scope.py` 22, `test_adversarial.py` 19, `test_nan_security.py` 32) — Foundation-side coverage that Phase 01 inherits.

**Provider-side gap (informational, not blocking):** the kailash-py `ConstraintEnvelopeConfig` (`src/kailash/trust/pact/config.py:239`) is a `pydantic.BaseModel` carrying the 5 PACT dimensions plus `confidentiality_clearance`, `max_delegation_depth`, `expires_at`. It does NOT carry the Envoy-spec-mandated `metadata.algorithm_identifier`, `composition_rules`, `cross_domain_rules_authored`, `tool_output_budget_bytes`, `semantic_checks.tool_output_classifier_ensemble`, or `metadata.authorship_score` blocks (per `specs/envelope-model.md` § Schema). These are Envoy-superset fields the compiler must layer on top — see § 3.

---

## 3. Envoy-new-code surface

The compiler's Envoy-new-code surface is the gap between (a) the kailash-py `ConstraintEnvelopeConfig` shape (5 dimensions + clearance) and (b) the `specs/envelope-model.md` § Schema top-level `EnvelopeConfig` shape (5 dimensions + 8 metadata + composition + cross-domain + tool-output + semantic-checks blocks). The compiler is the integration boundary that:

1. **Materializes `EnvelopeConfig` from `EnvelopeConfigInput`.** Boundary Conversation (shard 8) emits an `EnvelopeConfigInput` — a structured envelope-authoring outcome derived from a Kaizen `BaseAgent` `Signature` (per `specs/envelope-model.md` § Algorithms references and `01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 5). The compiler validates, normalizes (NFC), canonicalizes (JCS), assigns `envelope_id` (uuid-v7), pins `metadata.algorithm_identifier`, computes `metadata.authorship_score` (per `specs/envelope-model.md` § Algorithms § "Authorship Score (§8, §14.7, §14.8 of source — see specs/authorship-score.md)"), and emits the full `EnvelopeConfig`.

2. **Wraps `ConstraintEnvelopeConfig` for kailash-py interop.** The compiler extracts the 5-dimension subset of `EnvelopeConfig` into a `ConstraintEnvelopeConfig` for every kailash-py call site (`intersect_envelopes`, `RoleEnvelope.validate_tightening`, `compute_effective_envelope`). The Envoy superset fields remain on the Envoy `EnvelopeConfig` and are folded back in after intersection. The "fold-back" is non-trivial for `composition_rules` (UNION with unique-ID requirement per `specs/envelope-model.md` § Algorithms § `intersect_envelopes`) and for `cross_domain_rules_authored` (UNION with `order` lexicographic tie-break per `specs/cross-domain-flows.md` § Algorithm `rules.sort(key=lambda r: r.order)`) — these are Envoy-side concerns the upstream provider does not handle.

3. **Resolves Envelope Library template imports.** When `EnvelopeConfigInput` references a Foundation-Verified or Community template (per `specs/envelope-library.md` § "Trust tiers"), the compiler fetches the template, validates publisher signature + reputation, copies template constraints into per-dimension `imported_constraints[]` with `authored=false` + `template_origin` + `template_hash`, and folds template `composition_rules` + cross-domain rules into the appropriate top-level lists. Phase 01 ships with the **publisher signature stub** only (Foundation Library registry endpoint is Phase 02 per `specs/foundation-ops.md` § Envelope Library registry #1); local templates from disk are accepted at Phase 01.

4. **Enforces monotonic tightening at compile time.** Child-envelope compile (Boundary Conversation re-prompt; sub-agent SubsetProof construction; Grant-Moment-authored exception) MUST call `RoleEnvelope.validate_tightening(parent_envelope=…, child_envelope=…)` before signing. Compile-time enforcement closes the orphan-class hazard where the validator exists but the framework never invokes it (per `.claude/rules/orphan-detection.md` MUST Rule 1).

5. **Emits canonical-form bytes for downstream consumers.** Every `EnvelopeConfig` the compiler emits MUST also emit a `canonical_bytes: bytes` and `content_hash: str` (sha256 hex) computed via JCS over NFC-normalized fields with integer microdollars (per `specs/envelope-model.md` § Algorithms § "Canonical JSON"). Downstream consumers — Trust store (delegation-record `effective_envelope_hash`), Ledger (`envelope_edit` entries), Sub-agent SubsetProof (`parent_envelope_hash` / `sub_envelope_hash` per `specs/sub-agent-delegation.md`) — all read this hash; producing it once at compile time is the single-point defense against drift across consumers.

6. **Writes a Ledger entry on every compile.** Per `specs/envelope-model.md` § Error taxonomy, every error and every successful compile produces a Ledger entry with `content_trust_level: system`. The compiler is the writer; the Ledger primitive (shard 6) is the sink.

The Envoy-new-code surface is roughly the 6 sentences above. No invariant beyond what `specs/envelope-model.md` already mandates is being introduced.

---

## 4. Class structure sketch (interfaces only — no implementation)

Module path (Envoy-side, proposed): `envoy.envelope.compiler`.

```python
# envoy/envelope/types.py — Envoy-superset envelope types
class EnvelopeConfigInput:
    """Structured envelope-authoring outcome from Boundary Conversation.
    Owns the user's authoring intent before validation/canonicalization.
    """
    schema_version: str  # "envelope/1.0"
    metadata: EnvelopeMetadataInput  # may include unresolved template references
    financial: FinancialDimensionInput
    operational: OperationalDimensionInput
    temporal: TemporalDimensionInput
    data_access: DataAccessDimensionInput
    communication: CommunicationDimensionInput
    composition_rules: list[CompositionRuleInput]
    cross_domain_rules_authored: list[CrossDomainRuleInput]
    tool_output_budget_bytes: int
    semantic_checks: SemanticChecksInput

class EnvelopeConfig:
    """Compiled envelope per `specs/envelope-model.md` § Schema."""
    # ... 5 dimensions, metadata, composition, cross-domain, tool-output,
    #     semantic-checks blocks per the frozen schema ...
    canonical_bytes: bytes        # JCS over NFC; Envoy-new-code emits this once
    content_hash: str             # sha256 hex over canonical_bytes
    envelope_version: int

# envoy/envelope/compiler.py — the primitive
class EnvelopeCompiler:
    """Compiles authored EnvelopeConfigInput into a canonical EnvelopeConfig.

    Integration boundary between Boundary Conversation output and the rest
    of the system. Single-point enforcement of:
    - NFC normalization + JCS canonicalization
    - Algorithm-identifier pinning
    - Template-import resolution (FV / Community / local)
    - Monotonic-tightening validation against parent
    - Authorship Score computation per `specs/authorship-score.md`
    - Ledger-entry emission on success / typed-error on failure
    """
    def __init__(
        self,
        *,
        template_resolver: EnvelopeTemplateResolver,  # Phase 01: local-only stub
        authorship_scorer: AuthorshipScorer,          # shard 9 dependency
        ledger_writer: LedgerWriter,                  # shard 6 dependency
        algorithm_identifier: AlgorithmIdentifier,    # pinned at construction
    ) -> None: ...

    def compile(
        self,
        config_input: EnvelopeConfigInput,
        *,
        parent: EnvelopeConfig | None = None,    # for child-envelope compile
    ) -> EnvelopeConfig: ...
        # Steps:
        # 1. Validate schema_version + algorithm_identifier match
        # 2. Resolve template imports (publisher sig + reputation; local-only P01)
        # 3. NFC-normalize all string values
        # 4. Validate every numeric field via math.isfinite (NaN/Inf guard)
        # 5. If parent: RoleEnvelope.validate_tightening(parent.dimensions, child.dimensions)
        # 6. Compute authorship_score
        # 7. JCS canonicalize → canonical_bytes + content_hash
        # 8. Emit Ledger entry (envelope_compile or envelope_edit)
        # 9. Return EnvelopeConfig

    def to_constraint_envelope_config(
        self, env: EnvelopeConfig
    ) -> "kailash.trust.pact.config.ConstraintEnvelopeConfig": ...
        # Project the 5-dimension + clearance subset into the kailash-py shape
        # so kailash-py's intersect_envelopes / validate_tightening can consume it.

    def from_constraint_envelope_config(
        self, cec: "kailash.trust.pact.config.ConstraintEnvelopeConfig",
        *, envoy_super_fields: EnvelopeSuperFields,
    ) -> EnvelopeConfig: ...
        # Lift a kailash-py result back into Envoy superset by folding in
        # composition_rules / cross_domain_rules_authored / tool-output /
        # semantic-checks blocks held alongside.

    def intersect(
        self,
        a: EnvelopeConfig,
        b: EnvelopeConfig,
        *,
        dimension_scope: frozenset[str] | None = None,
    ) -> EnvelopeConfig: ...
        # Wraps kailash.trust.pact.envelopes.intersect_envelopes for the
        # 5-dimension core; folds Envoy-superset blocks per:
        #   composition_rules: UNION with unique-ID requirement
        #   cross_domain_rules_authored: UNION with order lexicographic tie-break
        #   tool_output_budget_bytes: MIN
        #   semantic_checks.*classifier_ensemble: SUPERSET (more-or-equal classifiers)

class EnvelopeTemplateResolver:  # Phase 01: local-only
    def resolve(self, ref: TemplateRef) -> EnvelopeTemplate: ...
```

**Naming alignment.** `EnvelopeCompiler.intersect` invokes the algorithm spec name `intersect_envelopes` (per `specs/envelope-model.md` § "Naming convention" R2-HIGH closure). The runtime ABC name `envelope_intersect` (per `specs/runtime-abstraction.md`) is the alias the runtime-abstraction stub (shard 18) will surface.

**Frozen-context default.** Following the security-reviewer-on-MCP precedent (`.claude/rules/security.md` § "Rust: Fail-Closed Security Defaults"), `EnvelopeCompiler.compile` MUST default `parent=None` only when the caller is the first-time-author path (Boundary Conversation EC-1 onboarding). Every other call path is a child-envelope compile and MUST pass `parent`. A `parent=None` call from any non-onboarding site is BLOCKED — surfaces the equivalent of `MonotonicTighteningError` early.

---

## 5. Integration points to neighboring primitives

(≤ 5 cross-primitive references; per `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget.)

1. **Boundary Conversation (shard 8) → EnvelopeCompiler.** The Conversation's Kaizen `BaseAgent` Signature emits an `EnvelopeConfigInput`; the compiler validates and emits `EnvelopeConfig`. Per `specs/envelope-model.md` § Algorithms § "First-time-action gate (§19 of source)", the conversation's outcome is the seed for the user's first envelope. Failure mode: a malformed `EnvelopeConfigInput` raises `EnvelopeValidationError`; the conversation re-prompts on the offending field.

2. **Grant Moment (shard 10) → EnvelopeCompiler.** Per `specs/envelope-model.md` § Error taxonomy, every Grant Moment that authors an exception (approve+author flow per `specs/cross-domain-flows.md` § "User-authored rule onboarding") triggers a child-envelope compile. The compiler enforces `RoleEnvelope.validate_tightening` so an approved Grant cannot widen the parent envelope. Cascade revocation per `specs/trust-lineage.md` invalidates the descendant compile if the originating grant is revoked.

3. **Trust store (shard 5) → EnvelopeCompiler.** `DelegationRecord.effective_envelope_hash` (per `specs/sub-agent-delegation.md` § Helper functions § `sha256_canonical_form`) reads the compiler's `EnvelopeConfig.content_hash`. Single-point hash production at compile time means the Trust store, Ledger, and SubsetProof verifier all agree on the same canonical bytes — no drift surface between consumers.

4. **Envoy Ledger (shard 6) → EnvelopeCompiler.** Every successful compile and every typed-error emits a Ledger entry per `specs/envelope-model.md` § Error taxonomy ("Every error logged as Ledger entry with `content_trust_level: system`"). The compiler invokes `LedgerWriter.append(...)` on completion. Phase 01 ships local-hash-chain Ledger writer per `01-analysis/03-kailash-py-mvp-readiness.md` § 4 (TieredAuditDispatcher #596 is OPEN; Envoy implements locally).

5. **Channel adapters / cross-channel (shard 16) → EnvelopeCompiler (EC-7, EC-8).** Per `specs/envelope-model.md` § Schema § `communication.channel_allowlist`, the compiled envelope binds which of the 8 channels (CLI + Web + 6 messaging) the agent may use. Cross-channel coherence (EC-8 acceptance gate per `01-analysis/02-mvp-objectives.md`) requires that a Day-1 envelope compiled on one channel is recognized verbatim by an action initiated on another channel 6 days later — `content_hash` byte-identity is the structural defense.

The Envelope Library (publisher reputation + force-install) is a Phase 02 surface per `specs/foundation-ops.md` § Envelope Library registry #1; Phase 01 ships the local-template-resolver stub only.

---

## 6. Tier 2 / Tier 3 test surface

Per `.claude/rules/testing.md` § Tier 2 + § Tier 3 + `.claude/rules/orphan-detection.md` MUST Rule 1 (production call site + Tier 2 wiring test in the same PR) + MUST Rule 2 (Tier 2 imports through the framework facade, not the manager class).

**Tier 2 (real infrastructure — no mocking; binding-boundary safe):**

- `tests/integration/test_envelope_compiler_wiring.py` — exercises `EnvelopeCompiler.compile(...)` through the `envoy_agent` facade with a real Boundary-Conversation-shaped `EnvelopeConfigInput` fixture; asserts (a) `canonical_bytes` is byte-equal to the expected JCS-NFC encoding of the fixture, (b) `content_hash` matches the SHA-256 of `canonical_bytes`, (c) a real Ledger entry is appended (read-back-verified per `.claude/rules/testing.md` § Tier 3 logic of state persistence).
- `tests/integration/test_envelope_compiler_intersect_through_kailash_py.py` — calls `EnvelopeCompiler.intersect(parent, child)` and confirms the result's 5-dimension subset is byte-equal to a direct call of `kailash.trust.pact.envelopes.intersect_envelopes(...)` against the same dimensions; covers the round-trip `to_constraint_envelope_config` → `from_constraint_envelope_config` invariant.
- `tests/integration/test_envelope_compiler_monotonic_tightening_at_compile.py` — child-envelope compile with a deliberately-widened dimension MUST raise `MonotonicTighteningError`; covers the orphan-class hazard explicitly (the validator exists upstream; we prove the framework calls it).
- `tests/integration/test_envelope_compiler_template_import_local.py` — Phase 01 local-only: the compiler reads a local template file, copies constraints into per-dimension `imported_constraints[]` with `authored=false` + `template_hash`, and the resulting `EnvelopeConfig` is byte-stable across two compiles of the same input.
- `tests/integration/test_envelope_compiler_jcs_corpus.py` — re-uses the upstream-shipped 67 JCS test vectors per `specs/envelope-model.md` § Test location. Cross-SDK byte-identity per BET-6.

**Tier 3 (real everything — cross-channel, cross-process):**

- `tests/e2e/test_envelope_byte_identity_across_channels.py` — exercises EC-7 / EC-8 acceptance: a `content_hash` produced by a CLI-compiled envelope MUST match the `content_hash` read by a Web-channel action 6 days later; persistence verified by read-back. Tests the cross-channel invariant the channel-as-UI thesis (BET-11) depends on.

**Tier 1 / regression / spec-compliance:**

- The kailash-py `envelopes.py` already ships 190 unit tests (per gh#594 closure comment); Envoy adds 0 Tier 1 coverage on `intersect_envelopes` proper. Envoy adds Tier 1 coverage ONLY on the `EnvelopeCompiler` Envoy-new-code surface (input validation, template-resolver protocol, authorship-score hook).
- Per `.claude/rules/testing.md` § "Verify NEW modules have NEW tests" — any new module under `envoy.envelope.*` is grep-checked for test coverage at /redteam.
- Regression tests `tests/regression/test_t005_*.py`, `test_t013_*.py`, `test_t023_*.py`, `test_t094_*.py`, `test_t104_*.py`, `test_t105_*.py` per `specs/envelope-model.md` § Test location — Phase 01 ships at minimum T-104 (envelope-version binding) and T-105 (sub-agent envelope-downgrade defense) since they are load-bearing for Grant Moment + sub-agent integration.

**Mechanical sweep (for /redteam):**

- `grep -rln "EnvelopeCompiler" envoy_agent/ tests/` — every primitive-deep-dive shard that integrates with the compiler must have at least one direct call site reachable from a production code path.
- `grep -rln "ConstraintEnvelopeConfig" envoy_agent/` — every direct kailash-py shape touch must be inside `to_constraint_envelope_config` / `from_constraint_envelope_config`; bare references at higher layers indicate a leak of the Envoy/upstream boundary.

---

## 7. Frozen-spec ambiguity check

Per `01-shard-plan.md` § 4 failure-mode protocol, the deep-dive STOPS if a HIGH-severity gap surfaces in the frozen spec. None surfaced in this shard. Two MEDIUM-severity ambiguities are noted but are NOT shard-blocking; they are recorded here so shard 22 (spec-gap analysis) can dispose them.

**MED-1 — `metadata.algorithm_identifier.cross_domain_rules` registry-version pin lifecycle.** `specs/envelope-model.md` § Field semantics for late-added fields says the pin "owns the cross-domain rule grammar"; `specs/cross-domain-flows.md` § Algorithm consumes the same registry version for evaluation. The frozen specs do not say whether a registry-version BUMP requires re-compiling existing envelopes (and re-signing all DelegationRecords in the Trust store) or whether existing envelopes continue to evaluate against the version pinned at compile time. Phase 01 disposition: implement the latter (envelopes carry their compile-time pin; registry bumps do not retroactively invalidate envelopes). This matches the `envelope_version` binding semantics and is the only choice consistent with cascade-revocation NOT being triggered by Foundation infrastructure changes (per `specs/envelope-library.md` § "Trust tiers" anti-Foundation-capture posture). NOT spec-blocking — a Phase-04-grade clarification.

**MED-2 — Authorship Score computation timing in compile pipeline.** `specs/envelope-model.md` § Algorithms § "Authorship Score (§8)" cross-references `specs/authorship-score.md` for novelty + minimum-impact algorithms; `specs/envelope-library.md` § Cross-domain consumer mapping says `imported_count` accounting flows from the Library through `template_provenance`. The timing — does the compiler compute the authorship score BEFORE or AFTER template imports fold in their `imported_constraints[]` — is unstated. Phase 01 disposition: the compiler computes Authorship Score AFTER template imports because the spec explicitly distinguishes `authored_count` from `imported_count` (only authored constraints count toward the score per `specs/authorship-score.md`). This is the only ordering consistent with BET-12 (governance-primary-surface = authorship); template-import-then-score is the only ordering that prevents template-padding from inflating the score. NOT spec-blocking — Phase-01 implementation can proceed; Phase 02 may surface this as an `## Open question` extension on `specs/authorship-score.md`.

No HIGH gap. The deep-dive proceeds.

---

## 8. Cross-references

Specs (frozen — read-only at this shard):

- `/Users/esperie/repos/dev/envoy/specs/envelope-model.md` § Schema, § Algorithms (Canonical JSON, Composition-rule DSL, `intersect_envelopes`, Naming convention, Authorship Score, First-time-action gate), § Error taxonomy.
- `/Users/esperie/repos/dev/envoy/specs/envelope-library.md` § Trust tiers, § Cross-domain consumer mapping.
- `/Users/esperie/repos/dev/envoy/specs/sub-agent-delegation.md` § `is_subset_envelope` algorithm, § Helper functions.
- `/Users/esperie/repos/dev/envoy/specs/cross-domain-flows.md` § Concept, § Algorithm, § "User-authored rule onboarding".
- `/Users/esperie/repos/dev/envoy/specs/tool-output-sanitization.md` § Surface, § Algorithm.

Phase 00 / Phase 01 prior work (cited; not re-derived):

- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § "Per-shard structure" (8-step structure), § 4 failure-mode protocol.
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` EC-1 (Boundary Conversation onboarding), EC-2 (Grant Moments), EC-7 (8-channel onboarding), EC-8 (cross-channel week).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 1 (Envelope compiler), § 5 verification protocol.
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` (citation discipline; no re-derivation).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` items 1–2 (`intersect_envelopes`, `RoleEnvelope` / `TaskEnvelope`).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` § 2 row 1 (kailash-py functional; kailash-rs different-name; ISS-01 + ISS-02).

Verified upstream provider:

- `/Users/esperie/repos/loom/kailash-py/src/kailash/trust/pact/envelopes.py` lines 336 (`intersect_envelopes`), 419 (`RoleEnvelope`), 437 (`validate_tightening`), 690 (`TaskEnvelope`), 716 (`compute_effective_envelope`), 794 (`compute_effective_envelope_with_version`).
- `/Users/esperie/repos/loom/kailash-py/src/kailash/trust/pact/__init__.py` `__all__` lines 100–142.
- `/Users/esperie/repos/loom/kailash-py/src/kailash/trust/pact/config.py:239` (`ConstraintEnvelopeConfig`).
- ISS-02 closure: `gh issue view 594 --repo terrene-foundation/kailash-py` — closed 2026-04-24T17:01:13Z; "already-satisfied" disposition; canonical fixture `envelope_with_intersection.json` shared with kailash-rs ISS-01.

Rules consulted:

- `/Users/esperie/repos/dev/envoy/.claude/rules/orphan-detection.md` MUST Rule 1, Rule 2.
- `/Users/esperie/repos/dev/envoy/.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget.
- `/Users/esperie/repos/dev/envoy/.claude/rules/communication.md` (plain-language framing).
- `/Users/esperie/repos/dev/envoy/.claude/rules/specs-authority.md` MUST Rule 4 (read-then-act), MUST Rule 5b (no spec edits at this shard).
- `/Users/esperie/repos/dev/envoy/.claude/rules/testing.md` § Tier 2 + Tier 3.
