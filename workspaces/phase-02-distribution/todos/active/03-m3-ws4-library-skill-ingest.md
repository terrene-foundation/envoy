# M3 — WS-4 Envelope Library + SKILL Ingest (Phase-02)

**Milestone:** Phase-02 Milestone-3 (WS-4). Expands shards **S8, S8e, S9a, S9b** from `workspaces/phase-02-distribution/02-plans/01-architecture.md` § Sharding plan (rows S8/S8e/S9a/S9b). This milestone ships the Foundation-Verified Envelope Library read+verify path, the shared 2-of-N steward-quorum verifier, the EnterpriseDeploymentRecord verifier + dual-sign gate, and the SKILL.md→envelope translator with the CO validator. It is **buildable now** — every WS-4 deliverable is greenfield code behind already-frozen Phase-01 interfaces (`envoy/envelope/template_resolver.py:49-56` resolver Protocol, the `foundation-verified:`/`community:` URI schemes at `template_resolver.py:27-28`, `envoy/runtime/protocol.py:170-173` `classifier_registry_resolve`, stubbed at `kailash_py.py:407` with `Phase02SubstrateNotWiredError`), with no dependency on the Phase-00 legal/trademark/export gates (those gate _release_, not _build_, per `02-plans/01-architecture.md` § Legal-gate-aware build sequence). The load-bearing cross-cut: **`verify_steward_quorum` is built exactly once in S8** (recommended module `envoy/registry/steward_quorum.py`) and **reused by S8e** (EnterpriseDeploymentRecord verifier) and the classifier registry — do not let any shard grow a parallel verifier. The acceptance split that governs S9a vs S9b: the Phase-02 exit criterion "CO validator accepts 100 benign + rejects 3 adversarial" (ROADMAP §108) is **split per-shard** — S9a (AST + score-band) is accountable for the **2 AST-catchable** adversarial samples (permission-escalation, exfiltration via literal undeclared-capability calls), and S9b (step-5 classifier ensemble) is accountable for the **1 dynamic-dispatch** sample — so S9a's gate must NOT claim all 3.

Spec context per `rules/specs-authority.md` MUST Rule 7. Primary specs read for this milestone: `specs/envelope-library.md` (FV tier, 2-of-N steward signing, error taxonomy), `specs/skill-ingest.md` (CO validator 6 steps, declared-vs-inferred step-3, score thresholds, install flow), `specs/foundation-ops.md` (registry #1 `envoy-registry:envelope-library:v1` Nexus-backed/content-addressed/Ed25519; registry-schema resolve algorithm §57; signing ceremonies §77-83), `specs/enterprise-deployment.md` (EnterpriseDeploymentRecord schema §19-38, verifier §43-49, dual-sign — Phase-02 per §15; disablement is Phase-03 per §16 and is OUT OF SCOPE this milestone). WS-4 deep-dive: `workspaces/phase-02-distribution/01-analysis/01-research/04-ws4-library-skill-ingest.md`.

**Framework-first (per `rules/framework-first.md`):** the registry is ONE `NexusApp` handler set (delegate to nexus-specialist before any direct route wiring — direct axum/HTTP is BLOCKED); the metadata table is a DataFlow `@db.model` (delegate to dataflow-specialist — raw SQL is BLOCKED).

---

## S8 — Steward-quorum verifier + Envelope Library FV registry (Nexus handlers + FV verify path)

**Type:** Build+Wire

**Value-anchor:** `ROADMAP.md:96` (source e — Phase-02 spec exit criterion the user approved) reads VERBATIM: "**Envelope Library v1:** Foundation-Verified tier live; Community tier frozen." This shard delivers the FV-tier read+verify path that makes "Foundation-Verified tier live" true for an end user importing `foundation-verified:family-starter@v3`. It is the root primitive (no deps) the rest of the milestone reuses.

**Implements:** `specs/foundation-ops.md` registry #1 (§17) + registry-schema resolve algorithm (§57 steps a-e) + signing ceremonies (§77-83 — verify side only); `specs/envelope-library.md` FV-tier row (§17) + error taxonomy `LibraryUnreachableError`/`PublisherSignatureInvalidError`/`FVTierMembershipNotProvenError`/`TemplateHashMismatchError` (§64-70). Builds the resolver named at `envoy/envelope/template_resolver.py:52-53` (`FoundationVerifiedTemplateResolver`).

**Depends:** — (root; wave-1 per `02-plans/01-architecture.md` § Roots). S9a, S9b, and S8e all depend on this shard.

**Scope:** Build `verify_steward_quorum(threshold, content_hash, signatures, pinned_pubkeys, revocation_list)` ONCE at `envoy/registry/steward_quorum.py` over the existing `kailash.trust.key_manager.InMemoryKeyManager.verify` primitive, returning a base verdict each consumer maps to its own taxonomy. Build the tier-aware `NexusApp` handler set (`library.fetch`, `library.resolve_tier`, `library.list`, `library.publish`) with Community/Org publish gated behind a feature flag returning a typed 503 refusal, content-addressed by `sha256(canonical_bytes(content))` over the existing `envoy/envelope/canonical_bytes.py` pipeline, with a DataFlow `@db.model` metadata table mapping `template_id@version → content_hash + tier + steward_signatures[] + published_at`. Wire `FoundationVerifiedTemplateResolver` as a thin Nexus-client + local-verify + content-addressed-cache wrapper that re-hashes fetched bytes, calls `verify_steward_quorum(threshold=2, …)` against the client-pinned Foundation stewardship key set, and re-verifies cache hits against pinned keys (cache is never a trust bypass).

**Acceptance criteria (testable):**

- EC-S8.1: `verify_steward_quorum(2, …)` returns True when ≥2 distinct pinned non-revoked steward keys validly sign `content_hash`; raises the base error when only 1 distinct key validates (consumer maps to `FVTierMembershipNotProvenError`). Behavioral test (call + assert raise/return per `rules/testing.md`), at `tests/integration/test_registry_resolve_signature_threshold.py` + `tests/integration/test_envelope_library_tier_signatures.py`.
- EC-S8.2: a revoked steward key is hard-rejected even when present; a rotated-out (but not revoked) key still validates templates signed before rotation (revocation = subtractive hard-fail; rotation = additive). Test asserts both branches distinctly.
- EC-S8.3: `FoundationVerifiedTemplateResolver.resolve("foundation-verified:family-starter@v3")` round-trips fetch→re-hash→quorum-verify→return `EnvelopeTemplate(template_origin="foundation-verified")`; a 1-byte content tamper raises `TemplateHashMismatchError` (`tests/regression/test_t020_envelope_template_supply_chain.py`).
- EC-S8.4: offline path — with the Nexus endpoint unreachable AND a content-addressed cache HIT, resolve still re-verifies against pinned keys and succeeds; cache MISS raises `LibraryUnreachableError` (`specs/envelope-library.md:64`).
- EC-S8.5: `library.publish` for tier=Community returns a typed 503 "Community publishing opens Phase-03" refusal; the tier enum + `PublisherSignatureInvalidError`/`SybilSuspicionThresholdExceededError` taxonomy are SHAPE-present but the publish handler is gated off.
- EC-S8.6: read-back verification (Tiers 2-3 per `rules/testing.md`) — after `library.publish` (FV ceremony entry), `library.fetch` by `content_hash` returns byte-identical content.
- EC-S8.7 (single-helper structural gate): exactly one `def verify_steward_quorum(` exists in the tree (`grep -rc` = 1); no parallel quorum-verify in any adapter or the EDR verifier.

**Capacity check (per `rules/autonomous-execution.md` § Per-Session Capacity Budget):** load-bearing logic ≈ the quorum verifier + resolver verify path (~250-350 LOC); the Nexus handler set + `@db.model` is largely framework-stamped boilerplate (DataFlow/Nexus generate the surface). Invariants held: re-hash-before-trust, quorum-distinctness, revocation-vs-rotation distinctness, cache-re-verify, tier-publish-gate = 5. Live loop (deterministic crypto round-trip + Nexus integration harness). Within one shard. Describable in 3 sentences: "Build the 2-of-N steward verifier once; build the tier-aware Nexus registry; wire the FV resolver to fetch+re-hash+quorum-verify locally."

---

## S8e — EnterpriseDeploymentRecord schema + verifier + dual-sign gate

**Type:** Build

**Value-anchor:** `ROADMAP.md:96` (source e — Phase-02 FV-tier exit criterion) — the EDR verifier rides the same Phase-02 cross-runtime-conformance landing per `specs/enterprise-deployment.md:15` ("**Phase 02** — EnterpriseDeploymentRecord schema + verifier + dual-sign gate shipped as part of runtime cross-runtime-conformance landing"). Delivers the enterprise-deployment trust gate that lets an org admin + employee dual-sign an enterprise template overlay — the buyer-facing capability the Phase-02 enterprise surface promises.

**Implements:** `specs/enterprise-deployment.md` EnterpriseDeploymentRecord schema (§19-38), verifier 6 steps (§43-49), dual-sign requirement (`EnterpriseDualSignMissingError` §77), error taxonomy (§74-83). **Reuses `verify_steward_quorum` from S8** for the org-Trust-Lineage-root signature checks.

**Depends:** S8 (the shared `verify_steward_quorum` primitive + the registry verify substrate).

**Scope:** Build the `EnterpriseDeploymentRecord` schema (closed `scope` enum — any other value rejected per §40) and its envelope-import-time verifier implementing all 6 steps (§43-49): org_genesis_hash resolves to a known org Trust Lineage root, deploying-principal signature valid against org Trust Lineage, affected-employee signature valid against employee Genesis, scope in closed enum, `enabled_at` within 365 days, `verification_algorithm` current-or-migration-compatible. Enforce the REQUIRED dual-sign gate (org_admin + affected_employee both present) raising `EnterpriseDualSignMissingError` on either-missing. **Explicitly OUT OF SCOPE (Phase-03 per `specs/enterprise-deployment.md:16`):** the disablement flow, 24h cooling-off, cross-channel confirm, N=5 posture ratchet — do NOT build `test_edr_disablement_24h_cooling_off.py` or `test_enterprise_n5_posture_ratchet.py` this milestone.

**Acceptance criteria (testable):**

- EC-S8e.1: a fully-valid dual-signed EDR passes all 6 verifier steps; each targeted single-step failure (unknown org_genesis_hash, invalid org-admin sig, invalid employee sig, scope outside enum, `enabled_at` >365 days, incompatible algorithm) raises the mapped error (`EnterpriseDeploymentRecordInvalidError`/`EnterpriseModeRevokedError`/`EnterpriseAlgorithmMigrationRequiredError`/`EnterpriseScopeMismatchError`). Behavioral, at `tests/integration/test_edr_verifier_six_steps.py`.
- EC-S8e.2: a single-signed EDR (org admin only, OR employee only) raises `EnterpriseDualSignMissingError`; the dual-signed record is accepted (`tests/integration/test_edr_dual_sign_required.py`).
- EC-S8e.3: `tests/regression/test_t024_enterprise_delegation_upward.py` — the T-024 abuser-IT vector is refused at verify time (the disablement-side defense is Phase-03; this shard covers the verify+dual-sign half).
- EC-S8e.4 (shared-verifier structural gate): the EDR verifier's org-Trust-Lineage signature check routes through the S8 `verify_steward_quorum` / shared key-verify helper — `grep` confirms no second quorum/verify implementation introduced by this shard.
- EC-S8e.5 (scope guard): no Phase-03 disablement test file is created this milestone (`find tests -name 'test_edr_disablement*' -o -name 'test_enterprise_n5*'` returns empty).

**Capacity check:** load-bearing logic ≈ the 6-step verifier + dual-sign gate (~200-250 LOC); schema is declarative. Invariants: 6 verifier steps each fail-closed + dual-sign-required + reuse-shared-verifier + Phase-03-scope-exclusion = within the 5-10 band. Live loop (deterministic signature round-trip). One shard. Three sentences: "Build the EDR schema with closed scope enum; build the 6-step import-time verifier reusing S8's quorum primitive; enforce the dual-sign gate. Disablement is Phase-03."

**Status: ✅ COMPLETE** (2026-06-10, `feat/wave2-batch2`).

## Verification (S8e)

- Plan reference re-checked: `02-plans/01-architecture.md` S8e row + `specs/enterprise-deployment.md` §19-49 — schema fields, closed scope enum, 6 steps, dual-sign all match line-by-line.
- EC-S8e.1 ✅ `tests/integration/test_edr_verifier_six_steps.py` (13 tests: green path + each targeted single-step failure → mapped error). EC-S8e.2 ✅ `test_edr_dual_sign_required.py` (4 tests). EC-S8e.3 ✅ `tests/regression/test_t024_enterprise_delegation_upward.py` (`@pytest.mark.regression`, 2 tests). EC-S8e.4 ✅ single-verifier AST gate green (`test_steward_quorum_single_helper.py`; EDR verify routes through `verify_steward_quorum` 1-of-1 at `envoy/enterprise/verifier.py`). EC-S8e.5 ✅ `find tests -name 'test_edr_disablement*' -o -name 'test_enterprise_n5*'` empty.
- Wiring: signature math via kailash `InMemoryKeyManager.verify` (real crypto, Tier 2 no-mocking); `known_org_roots` + migration-algorithm set + clock injected (deterministic).
- Spec deviation reconciled in same branch: step-2 wording now names `org_admin_signature_hex` + the resolved-org-root anchor (`specs/enterprise-deployment.md` § Verification).

---

## S9a — SKILL→envelope translator + CO validator steps 1-4,6 (AST inference + score-band)

**Type:** Build+Wire

**Value-anchor:** `ROADMAP.md:108` (source e — Phase-02 exit criterion, user-approved) reads VERBATIM: "CO validator rejects 3 constructed adversarial skill samples (permission-escalation, exfiltration, privilege-overreach) and accepts 100 benign ones" — **this shard is accountable for 2 of the 3** (the AST-catchable permission-escalation + exfiltration samples that make literal undeclared-capability calls). Also `ROADMAP.md:98` ("**`SKILL.md` translator:** lint + CO-compliance validator + automated envelope generator"). Delivers the install-time gate that protects a user from an over-privileged or mis-declared skill.

**Implements:** `specs/skill-ingest.md` SKILL.md parser (§13-15), ENVELOPE.md generator (§17-19), permission→PACT-dimension mapping (§21-33), CO validator steps 1, 2, 3 (declared=inferred, §41), 4 (over-privilege), 6 (publisher signature, §44), score thresholds ≥0.8/0.5-0.8/<0.5 (§46), install flow (§69), error taxonomy `COValidatorRefusedError`/`OverPrivilegeWarning`/`UnknownPermissionPatternError`/`SkillSourceHashMismatchError` (§78-85). Step-6 publisher-signature verify reuses the S8 Ed25519 verify primitive.

**Depends:** S8 (shared Ed25519 verify for step-6 + the registry-resolve substrate for the permission→PACT-dimension registry lookup at step-2).

**Scope:** Build the SKILL.md parser + ENVELOPE.md companion generator + `infer_permissions(skill_code) → InferredPermissionSet` via a CONSERVATIVE Python `ast` static walk (literal-call-only: `subprocess`/`os.system`→`bash:`/`exec:`, `open(…,"w")`→`file-write:`, `requests/httpx.post`→`http-post:<host>`, etc.) plus an import-graph second opinion that can only RAISE a warning, never auto-reject. Build `compare_declared_inferred(declared, inferred) → score` with the **asymmetric routing that IS the design**: literal undeclared-capability call (AST-proven `inferred ⊋ declared`) → score <0.5 → REJECT; import-graph-only extra → score 0.5-0.8 → pass-WITH-WARNING at Grant Moment; `declared ⊋ inferred` → `OverPrivilegeWarning` (step-4, NOT a reject). Wire steps 1 (schema valid), 2 (registry lookup against `envoy-registry:permission-to-pact-dimension:v1`), 4, 6; emit a typed "adversarial-pattern check pending ensemble" surface where step-5 will land (S9b) — surfaced, not silent.

**Acceptance criteria (testable, probe-driven per `rules/probe-driven-verification.md` — STRUCTURAL assertions on raised error / returned score, NOT regex over validator prose):**

- EC-S9a.1 (the 2 AST-catchable adversarial samples): the **permission-escalation** sample and the **exfiltration** sample — each making a LITERAL call to an undeclared capability (e.g. `requests.post` to an undeclared host; `subprocess` with no declared `bash:`) — each produce score <0.5 and raise `COValidatorRefusedError`. Structural assert on score band + raised type, at `tests/integration/test_co_validator_3_adversarial_corpus.py` (this shard owns 2 of its 3 rows).
- EC-S9a.2 (dynamic-dispatch sample rejected DIRECTLY by AST-only — the critical gate): a sample that reaches an undeclared capability via a LITERAL `getattr`/`eval`/`importlib` call site is rejected by S9a's AST walk because the dynamic-dispatch construct is itself a literal call node the conservative walk flags as undeclared-capability reach → score <0.5 → `COValidatorRefusedError`. (This is distinct from S9b's runtime dynamic-dispatch sample where the capability is only provable at invocation; S9a's gate must reject the AST-visible dynamic-dispatch construct directly so the milestone does not depend on S9b for any AST-visible case.)
- EC-S9a.3 (0 false-reject on benign): all 100 benign skills accept (score ≥0.8 OR 0.5-0.8 warning band; zero `COValidatorRefusedError`). The structural defense is the asymmetric routing — import-graph-only "extra" signals land in the WARNING band, never REJECT. At `tests/integration/test_co_validator_100_benign_corpus.py`. Any single false-reject is a build-blocking finding, not a tuning knob.
- EC-S9a.4: `declared ⊋ inferred` produces `OverPrivilegeWarning` (step-4) surfaced at Grant Moment — NOT a reject (`tests/integration/test_co_validator_six_steps.py`).
- EC-S9a.5: step-2 maps every documented permission pattern (bash/file-read/file-write/http-post/mcp/oauth/exec) via the registry; an unknown pattern raises `UnknownPermissionPatternError`. Step-6 publisher-sig failure raises `PublisherSignatureInvalidError`; `skill_source_hash` mismatch raises `SkillSourceHashMismatchError`.
- EC-S9a.6: the corpus (100 benign + 3 adversarial fixtures) is authored at `tests/acceptance/phase_02/co_validator_corpus/` as a deliverable (`specs/skill-ingest.md:109-110`); the step-5 surface emits a typed "pending ensemble" marker (not a silent pass).

**Capacity check:** load-bearing logic ≈ the AST inference walk + asymmetric comparison/score-band router (~350-450 LOC — the literal-call AST visitor is the dense part). Invariants: conservative-literal-only inference + asymmetric-routing (REJECT vs WARNING band) + 0-false-reject-on-benign + AST-visible-dynamic-dispatch-direct-reject + step-2/4/6 wiring = within the 5-10 band. Live loop (the corpus IS the deterministic feedback harness — write inference engine, run against 103 fixtures, iterate). One shard. Three sentences: "Build the conservative AST permission-inference walk + import-graph advisory; build the asymmetric score-band comparison that routes literal-undeclared-call to REJECT and import-only-extra to WARNING; wire steps 1/2/4/6 and the corpus. Accountable for the 2 AST-catchable adversarial samples + any AST-visible dynamic-dispatch construct; step-5 is S9b."

**Status: ✅ COMPLETE** (2026-06-10, `feat/wave2-batch2`).

## Verification (S9a)

- Plan reference re-checked: `specs/skill-ingest.md` §13-46, 69, 78-85 — parser, generator, mapping table, steps 1/2/3/4/6, thresholds, install-flow taxonomy all match.
- EC-S9a.1 ✅ permission-escalation + exfiltration samples → score 0.3 (<0.5) + `COValidatorRefusedError` (`test_co_validator_3_adversarial_corpus.py`). EC-S9a.2 ✅ literal `getattr`/`eval`/`importlib` dynamic-dispatch construct rejected DIRECTLY by the AST walk (no S9b dependency for AST-visible cases). EC-S9a.3 ✅ **100/100 benign accepted, zero `COValidatorRefusedError`** (75 clean ≥0.8, 25 warning band — `test_co_validator_100_benign_corpus.py`). EC-S9a.4 ✅ over-declaration → `OverPrivilegeWarning`, NOT a reject (`test_co_validator_six_steps.py`). EC-S9a.5 ✅ all 7 documented patterns map (+ `http-get` added, spec'd); unknown → `UnknownPermissionPatternError`; step-6 → `PublisherSignatureInvalidError` (incl. malformed-sig crypto exception mapped fail-closed); hash mismatch → `SkillSourceHashMismatchError`. EC-S9a.6 ✅ 103-fixture corpus at `tests/acceptance/phase_02/co_validator_corpus/`; step-5 emits typed `AdversarialCheckPending` (structural assert).
- Wiring: step-2 via real `resolve_permission` registry surface (pinned table transcribed from spec, fail-closed on miss); step-6 reuses the S8 Ed25519 `key_manager.verify` primitive (no second verifier); static `ast.parse` only — validator never executes skill code; 131 tests green incl. `-W error` re-run.
- Spec updates landed same branch: `http-get` mapping, oauth→operational axis placement, empty financial/temporal note, step-3 asymmetric-routing § (`specs/skill-ingest.md`).

---

## S9b — CO validator step-5 (classifier ensemble) — substrate-gated

**Type:** Build+Wire

**Value-anchor:** `ROADMAP.md:108` (source e — Phase-02 exit criterion, user-approved) — **this shard is accountable for the remaining 1 of 3** adversarial samples: the **dynamic-dispatch** sample whose undeclared capability is only provable at runtime invocation (NOT a literal AST call node S9a can see), caught by the classifier ensemble against `envoy-registry:adversarial-skill-patterns:v1`. Closes the 3-of-3 adversarial-rejection exit criterion together with S9a.

**Implements:** `specs/skill-ingest.md` CO validator step-5 (adversarial-pattern detection against `envoy-registry:adversarial-skill-patterns:v1`, §43); `AdversarialSkillPatternMatchedError` (§79); `specs/foundation-ops.md` classifier registry #17 (§33) resolved via `classifier_registry_resolve` then invoked via the classifier-ensemble (≥2 classifiers, "disagreement fails CLOSED by default" per `protocol.py:166-167`). Wires `classifier_registry_resolve` step (b) through the S8 `verify_steward_quorum`.

**Depends:** S8 (shared quorum verifier for `classifier_registry_resolve` step b) **AND S6a** (WS-6 ClassificationPolicy — the classifier-invoke / ensemble-aggregate substrate currently stubbed `Phase02SubstrateNotWiredError` at `kailash_py.py:395-405`). **Loop = base (substrate-gated)** per `02-plans/01-architecture.md` S9b row — no live loop until the S6a ClassificationPolicy substrate lands, so this shard sequences AFTER S6a in WS-6.

**Scope:** Wire `classifier_registry_resolve(registry_id)` in BOTH the `kailash_py` and `kailash_rs_bindings` adapters (cross-runtime parity — both implement the frozen Protocol; both must be byte/semantically conformant per the WS-1 contract) implementing the 5-step resolve (§57: fetch → quorum-verify via S8 → fetch content_ref → hash-compare → return). Resolve the `adversarial-skill-patterns:v1` classifier and invoke it through the ensemble (≥2 members, disagreement fails CLOSED). Integrate step-5 into the CO validator pipeline behind S9a's "pending ensemble" surface, flipping it from typed-pending to live. Accountable specifically for the runtime dynamic-dispatch adversarial sample.

**Acceptance criteria (testable, probe-driven structural per `rules/probe-driven-verification.md`):**

- EC-S9b.1 (the 1 dynamic-dispatch adversarial sample): the runtime-dynamic-dispatch sample (undeclared capability reachable only at invocation, NOT an AST-visible literal call) is rejected by the classifier ensemble → raises `AdversarialSkillPatternMatchedError`. Structural assert on raised type, completing `tests/integration/test_co_validator_3_adversarial_corpus.py` to 3-of-3.
- EC-S9b.2: ensemble disagreement (1 member flags, 1 clears) fails CLOSED (refuse) per `protocol.py:166-167`.
- EC-S9b.3: `classifier_registry_resolve` 5-step resolve — a `signing_threshold_met=false` entry raises `RegistryThresholdNotMetError`; an `artifact_hash` mismatch raises `RegistryArtifactHashMismatchError`; an expired entry raises `RegistryEntryExpiredError` (`tests/integration/test_registry_resolve_signature_threshold.py` + `test_registry_artifact_hash_match.py` + `test_registry_expiry_refresh.py`). Step (b) routes through the S8 `verify_steward_quorum` (structural grep gate — no parallel verifier).
- EC-S9b.4 (cross-runtime parity): `classifier_registry_resolve` behaves byte/semantically identically across the `kailash_py` and `kailash_rs_bindings` adapters (conformance assertion per the WS-1 contract).
- EC-S9b.5: with S9a + S9b both landed, the full corpus gate passes — 100 benign accept, 3 adversarial reject (the combined Phase-02 exit criterion ROADMAP §108).

**Capacity check:** load-bearing logic ≈ `classifier_registry_resolve` 5-step wiring across two adapters + ensemble-aggregate integration (~250-350 LOC). Invariants: quorum-verify-reuse + hash-compare + cross-runtime-parity + ensemble-fail-closed + step-5-pipeline-integration = within the 5-10 band. **Loop = base until S6a lands**, then live — sequence after S6a; do NOT start S9b before the ClassificationPolicy substrate exists (it is the live-loop gate). One shard. Three sentences: "Wire classifier_registry_resolve in both adapters reusing S8's quorum verifier; invoke the adversarial-patterns ensemble fail-closed; flip S9a's pending-step-5 surface live. Accountable for the 1 runtime dynamic-dispatch adversarial sample; substrate-gated on S6a."

---

**4 todos.** Sequencing: **S8 first** (root, builds the shared `verify_steward_quorum`), then **S8e** and **S9a** in parallel (both depend only on S8, INDEPENDENT scopes — `envoy/enterprise/` vs `envoy/skill_ingest/`), then **S9b last** (substrate-gated on both S8 and WS-6 S6a; its live loop does not open until S6a's ClassificationPolicy lands). The 3-of-3 adversarial-rejection exit criterion (ROADMAP §108) is met only when S9a (2 samples + AST-visible dynamic-dispatch) AND S9b (1 runtime dynamic-dispatch sample) are both landed.
