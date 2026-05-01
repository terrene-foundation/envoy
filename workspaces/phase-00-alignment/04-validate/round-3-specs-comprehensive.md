# Round 3 — Specs Comprehensive Audit

**Scope:** Full re-derivation against `/Users/esperie/repos/dev/envoy/specs/` (37 spec files + `_index.md`) and 12 frozen analysis docs in `workspaces/phase-00-alignment/01-analysis/`. R1 + R2 outputs explicitly NOT trusted; every assertion re-derived per `rules/specs-authority.md` MUST Rule 5b.

**Methodology:** R1 completeness, R2 full-sibling re-derivation, R3 orphan detection, R4 threat-model coverage, R5 acceptance-criterion traceability. Mechanical sweeps (`grep` per-section, per-field, per-threat) + LLM judgment.

---

## Severity distribution

| Severity     | Count |
| ------------ | ----- |
| **CRIT**     | 2     |
| **HIGH**     | 9     |
| **MED**      | 13    |
| **LOW**      | 6     |
| **Total**    | 30    |

**Verdict:** NOT CONVERGED. R3 introduces 2 CRIT + 9 HIGH (plus 13 MED). Convergence requires 0 CRIT + 0 HIGH across two consecutive full-sibling rounds; R3 fails the threshold and resets the convergence counter to zero. Round-2 fixes that LANDED are confirmed — closures of envelope-model new fields, session-state.pre_authorized_patterns, ledger.time_anchor, foundation-health-heartbeat duplicate Purpose, ledger §Consent layer, foundation-ops registry #18, runtime-abstraction AssembledPrompt — verified intact. New findings concentrate in (a) field-path drift between envelope schema and consumer algorithms, (b) orphan Ledger entry types whose schemas are missing in their declared producer specs, (c) broken §-level cross-references that point to non-existent headings, (d) signature-name drift on `evaluate_cross_domain_rules`, (e) incomplete R2-HIGH closure for session-state.md T-022 (residual references in 4 places).

---

## R1 — Completeness sweep

Every spec MUST carry `## Purpose / ## Provenance / ## Schema (if owns one) / ## Algorithm (if owns one) / ## Error taxonomy / ## Cross-references / ## Test location / ## Open questions`. Mechanical grep across all 37 specs confirms every mandatory heading present. **R1: 0 findings.**

---

## R2 — Full-sibling re-derivation (cross-spec drift)

### CRIT-R2-1 — Algorithm reads undefined field path `envelope.envelope_version`

- **Where:** `tool-output-sanitization.md:58` — `cache_key=(sha256(canonical_bytes).hex(), tool_name, envelope.envelope_version)`.
- **Schema reality:** `envelope-model.md:23` defines the field as `metadata.version` (nested under `metadata`, named `version` not `envelope_version`). The full path is `envelope.metadata.version`.
- **Same drift:** `runtime-abstraction.md:150` N2 cache invalidation lists "envelope_version" as a property, and `tool-output-sanitization.md:104` documents the cache key as `(content_hash, tool_name, envelope_version, classifier_version)`. `tool-output-sanitization.md:128` uses `envelope_version_at_invocation` in the Ledger record schema. `session-state.md:56,97,166` use `envelope_version_at_session_start` / `envelope_version_at_commit`.
- **Severity rationale:** Algorithm reads a field that does not exist at the path written. The wire-format envelope's `metadata.version` int is the only such field; consumers calling `envelope.envelope_version` would `AttributeError` against the schema as written. This is rubric-CRIT (algorithm reads undefined field).
- **Disposition:** Either (a) rename schema field `metadata.version` → top-level `envelope_version` to match consumer assumptions, or (b) update every consumer to read `envelope.metadata.version`. Option (a) is closer to current usage; option (b) preserves the namespace under `metadata`.

### CRIT-R2-2 — `imported_constraints[]` schema undefined; algorithm reads undefined fields

- **Where:** `authorship-score.md:49-51` — algorithm reads `c.template_origin`, `c.template_hash` from each item in `getattr(envelope, dim).imported_constraints`.
- **Schema reality:** `envelope-model.md:42, 49, 54, 61, 67` declare `imported_constraints: [...]` as a placeholder `[...]` only. No item-shape defined; no `template_origin` field, no `template_hash` field.
- **Severity rationale:** `re-derive_authorship_counters` algorithm reads two named fields off list items whose shape is undefined in the schema. Rubric-CRIT.
- **Disposition:** Land an inline shape declaration in `envelope-model.md` for `imported_constraints[]`, e.g. `[{"constraint_id": <str>, "rule_ast": {...}, "authored": false, "template_origin": <str>, "template_hash": <sha256>}]`.

### HIGH-R2-1 — `evaluate_cross_domain_rules` parameter-name drift between caller and callee

- **Callee signature:** `cross-domain-flows.md:66` — `def evaluate_cross_domain_rules(output_bytes, tool_name, envelope, registry_version)`.
- **Caller call:** `tool-output-sanitization.md:64-67` —
  ```python
  evaluate_cross_domain_rules(
      output=canonical_bytes, tool_name=tool_name,
      envelope=envelope,
      cross_domain_registry_version=envelope.metadata.algorithm_identifier.cross_domain_rules,
  )
  ```
- **Drift:** (1) caller uses kwarg `output=` but signature declares `output_bytes`; (2) caller uses kwarg `cross_domain_registry_version=` but signature declares `registry_version`. The keyword-argument call would `TypeError` at execution.
- **Severity rationale:** Cross-spec algorithm signature drift; one caller, one callee, two name mismatches. R3-HIGH per rubric.
- **Disposition:** Rename callee parameters to match the caller's keyword names, or rename caller's kwargs to match callee.

### HIGH-R2-2 — `tool_output_sanitize` signature drift in Purpose blurb vs Surface vs Algorithm vs runtime ABC

- **`tool-output-sanitization.md:5` (Purpose):** `tool_output_sanitize(output, classifier_ensemble, envelope)`.
- **`tool-output-sanitization.md:18` (Surface):** `tool_output_sanitize(output, tool_name, envelope)`.
- **`tool-output-sanitization.md:33` (Algorithm):** `def tool_output_sanitize(output, tool_name, envelope)`.
- **`runtime-abstraction.md:89`:** `tool_output_sanitize(output, tool_name, envelope)`.
- **Drift:** Purpose paragraph (line 5) is the lone holdout — second parameter `classifier_ensemble` vs `tool_name`. Round 2 R2-MED notes ostensibly aligned all four; the Purpose blurb was missed.
- **Disposition:** Rewrite line 5 to read `tool_output_sanitize(output, tool_name, envelope)`.

### HIGH-R2-3 — `grant-moment.md §Schema` referenced but does not exist

- **Reference:** `runtime-abstraction.md:127` — "GrantMomentRequest/Result per specs/grant-moment.md §Schema".
- **Reality:** `grant-moment.md` has no `## Schema` heading. Section list: Purpose / Provenance / State machine / Rendering / Novelty-aware friction / Velocity-raise ratchet / Cross-principal / Timeout / Produced artifact / Error taxonomy / Cross-references / Test location / Open questions.
- **Severity rationale:** Cross-spec reference points to non-existent named section; reader cannot locate the schema. HIGH per rubric (broken cross-ref to a load-bearing primitive).
- **Disposition:** Either add `## Schema` to grant-moment.md defining `GrantMomentRequest` + `GrantMomentResult`, or update runtime-abstraction.md cross-ref to point to `§Produced artifact` (which mentions `DelegationRecord` + `Phase A intent` but does not define the request/response types).

### HIGH-R2-4 — Session-state R2-HIGH closure incomplete (T-022 residual references)

- **R2 closure context:** Round 2 R2-HIGH "T-022 misclassification removed; T-022 now skill-ingest.md / foundation-ops.md / envelope-library.md only".
- **Provenance line:** `session-state.md:10` correctly removed T-022 from the canonical `Threats mitigated:` list and adds a closure note.
- **Residual non-closure:**
  1. `session-state.md:65` — "This is intentional per T-022 mitigation."
  2. `session-state.md:199` — "**specs/threat-model.md** — T-013, T-015, T-019, T-022."
  3. `session-state.md:211` — "Threat tests T-013/T-015/T-019/T-022 live here, per specs/threat-model.md §Test location."
  4. `session-state.md:217` — "...documented in T-022..."
- **Severity rationale:** R2-HIGH closure declared complete but four references remain. This is partial-closure drift; rubric-HIGH.
- **Disposition:** Strike T-022 from lines 65, 199, 211, 217 in session-state.md.

### HIGH-R2-5 — Orphan threat T-031 referenced in trust-lineage test path

- **Where:** `trust-lineage.md:198` — `tests/regression/test_t031_model_collusion.py` — T-031 cross-model collusion (key-rotation + algorithm-migration response).
- **Source reality:** `workspaces/phase-00-alignment/01-analysis/09-threat-model.md` declares T-001..T-030, T-040..T-107 (with T-061 reserved). No T-031 in source enumeration.
- **Severity rationale:** Test path claims to defend a threat ID that does not exist in the canonical threat catalog. HIGH per rubric (orphan threat).
- **Disposition:** Either (a) drop the test claim, or (b) propose a new threat T-031 in the source threat-model anchor doc and document the mitigation primitive properly.

### HIGH-R2-6 — Orphan Ledger entry: `RoleEnvelopeCreated` schema missing from declared producer

- **Ledger.md row:** `ledger.md:51` — `RoleEnvelopeCreated` claims producer `specs/envelope-model.md §Schema`.
- **Reality:** `envelope-model.md §Schema` defines the `EnvelopeConfig` JSON wire format only. There is no `RoleEnvelopeCreated` Ledger-entry-specific schema (entry_envelope, type tag, signing scope, etc.). The cross-ref points to the entity wire format, not the entry-type schema.
- **Severity rationale:** `_index.md:72` mandates "Every Ledger entry type listed in specs/ledger.md §Entry types MUST have a named producer spec owning its schema." `RoleEnvelopeCreated` violates that contract — no schema exists. HIGH per `rules/orphan-detection.md` Rule 1.
- **Disposition:** Either (a) add an explicit `RoleEnvelopeCreated` schema block to envelope-model.md or trust-lineage.md, or (b) drop the entry type from ledger.md (consolidate with `envelope_edit`).

### HIGH-R2-7 — Orphan Ledger entry: `envelope_edit` schema missing

- **Ledger.md row:** `ledger.md:52` — `envelope_edit` claims producer `specs/envelope-model.md §Schema (version bump)`.
- **Reality:** envelope-model.md has no schema for an `envelope_edit` Ledger entry; only `EnvelopeConfig` (the entity, not the audit row). Same failure mode as HIGH-R2-6.
- **Disposition:** Add explicit `envelope_edit` schema block (type, schema_version, prior_version, new_version, diff hash, signed_by). Same applies to other generic ledger types referenced as `specs/X §Schema` without a dedicated entry-schema block.

### HIGH-R2-8 — Orphan Ledger entry: `ritual_completion` schema missing across all three claimed producers

- **Ledger.md row:** `ledger.md:73` — `ritual_completion` claims producers `specs/daily-digest.md + specs/weekly-posture-review.md + specs/monthly-trust-report.md`.
- **Reality:** None of the three specs reference or define a `ritual_completion` Ledger entry. `daily-digest.md`, `weekly-posture-review.md`, `monthly-trust-report.md` describe ritual surfaces but do not declare the entry-type schema or signer.
- **Severity rationale:** Three producers claimed; zero schema definitions. HIGH per `rules/orphan-detection.md` Rule 1.
- **Disposition:** Pick one canonical owner (likely daily-digest.md as the most-frequent producer) and add a `## Ledger record` block defining the schema, or drop the entry type if not load-bearing.

### HIGH-R2-9 — Orphan Ledger entries: `channel_connected`, `channel_disconnected`, `ClockSkewEvent`

- **Ledger.md rows:** lines 77, 78, 82 — `channel_connected`, `channel_disconnected`, `ClockSkewEvent`.
- **Producer claims:** `channel-adapters.md §Lifecycle` and `remote-time-anchor.md §Skew detection`.
- **Reality:** (a) channel-adapters.md has `### Lifecycle methods` (subsection of `## Adapter contract`) but defines no `channel_connected` / `channel_disconnected` Ledger entry schemas; (b) remote-time-anchor.md has no `## Skew detection` heading at all and no `ClockSkewEvent` entry schema (it owns `time_anchor` only).
- **Severity rationale:** Three Ledger entries with no schema definitions. HIGH per orphan-detection.
- **Disposition:** Add explicit entry-schema blocks to the producer specs, or remove from ledger.md if the entry types are not actually emitted.

### MED-R2-1 — `cross-domain-flows.md` algorithm omits imported cross-domain rules path described in envelope-model.md

- **Schema doc:** `envelope-model.md:91` — "Imported cross-domain rules ride in `data_access.imported_constraints` + `communication.imported_constraints` per the cross-domain-flows.md mapping."
- **Algorithm reality:** `cross-domain-flows.md:66-91` `evaluate_cross_domain_rules` reads only `envelope.cross_domain_rules_authored + foundation_defaults(registry_version)`. Never iterates `data_access.imported_constraints` or `communication.imported_constraints`.
- **Severity rationale:** Schema documentation describes a primitive folding behavior that the algorithm does not implement. Cross-spec drift; MED.
- **Disposition:** Either expand `evaluate_cross_domain_rules` to consume the imported lists, or revise the envelope-model.md note to clarify imported rules are NOT consumed by the cross-domain rule engine.

### MED-R2-2 — `session-state.md` `pre_authorized_patterns` membership test inconsistent with schema

- **Schema:** `session-state.md:53-55` declares `pre_authorized_patterns: [{pattern_id, tool_name, args_pattern_ast, authored_at, scope}]` (list of dicts).
- **Algorithm:** `session-state.md:123` checks `if fp_key in session.pre_authorized_patterns` — `in` operator on a list of dicts only matches whole-dict equality, not fingerprint-key membership. Prose at line 61 says "Lookup is structural AST-match against `args_pattern_ast`."
- **Severity rationale:** Pseudocode does not implement the documented semantics. MED (algorithm under-specified).
- **Disposition:** Replace line 123 with explicit AST-match loop: `for p in session.pre_authorized_patterns: if match_ast(p.args_pattern_ast, args): return GateResult.RECOGNIZED`.

### MED-R2-3 — `tool-output-sanitization.md:43` comment misnames field

- **Where:** Algorithm step 2 comment: `# 2. Size budget check — per envelope.semantic_checks.latency_budget_ms;`
- **Reality:** The check at line 45 compares `len(canonical_bytes) > envelope.tool_output_budget_bytes`. The comment refers to `latency_budget_ms` (a time budget) while the actual check is bytes-against-byte-budget.
- **Disposition:** Fix the comment to read `# 2. Size budget check — per envelope.tool_output_budget_bytes;`.

### MED-R2-4 — Broken §-section cross-refs (missing headings)

The following cross-references point to specific `§Heading` sections that do not exist as named headings in the target spec:

| Citing spec               | Reference                                                           | Reality                                                                                  |
| ------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `authorship-score.md:30`  | `specs/foundation-ops.md §Template registry`                        | No `## Template registry` heading; closest is `## Infrastructure inventory` #1           |
| `authorship-score.md:34`  | `specs/foundation-ops.md §Template registry`                        | Same as above                                                                            |
| `cross-domain-flows.md:50`| `specs/foundation-ops.md §Classifier registry #10`                  | #10 is "Cross-domain-flow registry"; classifier registry is #6                           |
| `tool-output-sanitization.md:5,90` | `specs/foundation-ops.md §Classifier registry #11`         | #11 is "Prompt-injection-patterns registry"; foundation-ops has no `§Classifier registry` heading |
| `tool-output-sanitization.md:90` | `§Classifier registry §Phase 01 extension`                  | No such sub-section anywhere                                                             |
| `envelope-library.md:49`  | `specs/foundation-ops.md §Moderator queue`                          | No such heading; closest is `## Spam flood defense (T-092)`                              |
| `envelope-library.md:49`  | `specs/skill-ingest.md §Removal flow`                               | No such heading                                                                          |
| `ledger.md:50`            | `specs/trust-lineage.md §Device-attestation enforcement`            | Paragraph inside `### GenesisRecord`; no top-level heading                               |
| `ledger.md:71`            | `specs/enterprise-deployment.md §Disablement flow`                  | Heading is `## Disablement (T-024 R2-H5)` (no "flow" suffix)                             |
| `ledger.md:74`            | `specs/shamir-recovery.md §Distribution checklist`                  | Heading is `## Distribution guidance (T-006 defense)`                                    |
| `ledger.md:76`            | `specs/skill-ingest.md §Removal`                                    | No `## Removal` heading                                                                  |
| `ledger.md:82`            | `specs/remote-time-anchor.md §Skew detection`                       | No such heading anywhere                                                                 |
| `ledger.md:92`            | `specs/data-model.md §Shadow segment`                               | "Shadow segment" is item #4 inside `## Four physical containers`; no top-level heading   |
| `posture-ladder.md:90`    | `specs/enterprise-deployment.md §AUTONOMOUS carveout`               | No such heading                                                                          |
| `a2a-messaging.md:41`     | `specs/envelope-model.md §5.3`                                      | Source-doc paragraph reference; envelope-model.md uses different section structure       |

- **Severity rationale:** Each ref is independently MED — readers can usually locate the content but mechanical cross-ref validation fails. Aggregated count: 14 broken §-refs. MED for the cluster (vs HIGH if any single reference were load-bearing for a primitive's identification).
- **Disposition:** Either rename the headings in the target specs to match cited form, or update every citing spec to reference the correct heading text. Bulk grep+sed pass should fix these mechanically.

### MED-R2-5 — `T-061` claimed as defended threat in distribution.md but source declares it "reserved"

- **Source:** `09-threat-model.md:671` — "T-061 — (reserved — not currently used; leaves room in the numbering for a future binding-specific threat)".
- **Spec claim:** `distribution.md:87` cross-references list "T-050a, T-050b, T-060, T-061" and `distribution.md:95` declares `tests/regression/test_t061_distribution_attack_n3_mirror.py` — T-061 defense.
- **Drift internal to distribution.md:** Provenance Threats mitigated (line 10) lists "T-050a, T-050b, T-060" — without T-061. Cross-references list (line 87) includes T-061 — without provenance support.
- **Severity rationale:** Test claims to mitigate a reserved (non-existent) threat, and provenance vs cross-references are themselves inconsistent. MED.
- **Disposition:** Either (a) propose T-061 as a real threat in the source anchor and document the mitigation primitive, or (b) drop T-061 from cross-references and rename the test to reference T-060 (to which N=3 mirror divergence properly belongs).

### MED-R2-6 — `is_subset_envelope` invocation vs definition name mismatch

- **Where:** `sub-agent-delegation.md:36` — "Envoy runtime re-computes from scratch on every sub-agent invocation using `is_subset_envelope(sub, parent)`". Function defined at line 41 is `verify_subset_proof_independently(parent, sub)`. Section heading line 38 is `## \`is_subset_envelope\` algorithm`.
- **Severity rationale:** Two function names referenced for the same primitive; argument order reversed (`(sub, parent)` vs `(parent, sub)`). MED.
- **Disposition:** Pick one canonical name; align text + heading + function to use it.

---

## R3 — Orphan detection

Mechanical sweep — every primitive named in cross-references must have a producer-spec owning a schema or algorithm.

### Orphan Ledger entries (already listed above as HIGH-R2-6, R2-7, R2-8, R2-9)

- `RoleEnvelopeCreated` (HIGH-R2-6)
- `envelope_edit` (HIGH-R2-7)
- `ritual_completion` (HIGH-R2-8)
- `channel_connected`, `channel_disconnected`, `ClockSkewEvent` (HIGH-R2-9)

### MED-R3-1 — Schema-thin Ledger entries: `MigrationAnnouncement`, `EntryKeyDestruction`, `shamir_distribution_checklist_update`

- `MigrationAnnouncement` (ledger.md:66 → trust-lineage.md §Algorithm migration): trust-lineage.md:103 mentions the entry but provides no JSON schema. MED.
- `EntryKeyDestruction` (ledger.md:64): mentioned in ledger.md retention section (line 156) but no formal schema block. MED.
- `shamir_distribution_checklist_update` (ledger.md:74 → shamir-recovery.md §Distribution checklist): shamir-recovery.md has no §Distribution checklist heading and no schema for the entry. MED.
- **Disposition:** Add explicit `## Schema` blocks (or `### EntryName` sub-sections under `## Schema`) defining `type`, `schema_version`, payload fields, signer, signing scope.

### LOW-R3-1 — Fuzzy heading matches (canonical-form-vs-fuzzy)

These cross-refs target headings that exist with slightly different naming. Lower priority than R2-4 broken refs because the reader can locate the content from context:

- `ledger.md §Retention` referenced from EntryKeyDestruction row → actual heading `## Retention + GDPR (T-003)`. LOW.
- `ledger.md §Export` referenced from runtime-abstraction.md:57 → actual heading `## Export + independent verifier`. LOW.
- `trust-lineage.md §two-head-commitments` referenced from ledger.md:105 → actual heading `### Two head-commitments (§6.3 H-06 fix)` (capitalization-only drift). LOW.
- `acceptance-metrics.md §Kill criteria` referenced from posture-ladder.md:49 → actual heading `## Kill criteria operationalized`. LOW.
- `skill-ingest.md §Install` referenced from ledger.md:75 → actual heading `## Install flow`. LOW.
- `channel-adapters.md §Lifecycle` referenced from ledger.md:77,78 → actual heading `### Lifecycle methods` (subsection of `## Adapter contract`). LOW.
- **Disposition:** Bulk normalization pass. Either rename headings to omit the trailing words ("Retention", "Export", "Lifecycle", "Install", "Two head-commitments", "Kill criteria") or normalize the citing forms to include them.

---

## R4 — Threat-model coverage

50 threats × {mitigation owner, regression test} matrix. Mechanical sweep against `09-threat-model.md` v3 §3 enumeration.

### MED-R4-1 — Heartbeat T-041 cross-reference broader than provenance claim

- `foundation-health-heartbeat.md:71` cross-references `T-041` — but `:10` Threats mitigated lists T-052/T-054/T-023/T-024 (no T-041). The defensive primitive is `DuressFlagLeakageRefusedError` (line 60) which prevents `duress_unlock_detected` from being added to the payload — a defense-in-depth for T-041, not a primary mitigation.
- **Severity:** MED — provenance under-claims while cross-references over-claim.
- **Disposition:** Either add T-041 to provenance Threats mitigated (defense-in-depth claim is legitimate), or drop T-041 from cross-references and let trust-vault.md / trust-lineage.md / data-model.md own the threat.

### Coverage assertion

All 50 enumerated threats (T-001 through T-107 with documented gaps) carry ≥1 spec claiming the threat AND ≥1 regression test path. Mechanical sweep:
- Every T-NNN appears in some spec's `## Provenance` Threats mitigated.
- Every T-NNN has at least one `tests/regression/test_t<nnn>_*.py` reference (T-011 covered by `test_t010_t011_prompt_injection_structural.py`).

T-031 (HIGH-R2-5) is the inverse failure: a test exists for a threat that does NOT exist in the source enumeration.

T-061 (MED-R2-5) is the borderline failure: a test exists for a reserved (non-defined) threat.

**R4 net:** 1 MED finding above + the cross-listed HIGH-R2-5 / MED-R2-5. No new orphan threat owners.

---

## R5 — Acceptance-criterion traceability

Phase 00–04 exit criteria in `acceptance-metrics.md:22-40` traced to named primitives + test paths.

### MED-R5-1 — Phase 02 criteria not all spec-traced

- "mobile QR-pair <30s" (line 32) — no specific spec owns this; channel-adapters.md mentions QR codes only in the shared-household co-presence ceremony (line 25). MED — under-specified.
- "install-to-first-value <10min mobile" (line 32) — distribution.md doesn't carry an end-to-end timing test; boundary-conversation.md targets ~15min for a different ritual. MED — under-specified.
- "binary <50 MB" (line 32) — no spec owns the size constraint or its test path. MED.
- **Disposition:** Either add owning specs (e.g. distribution.md gets `## Install-to-first-value` with timing test path), or relegate these to `## Open questions` until Phase 02 work begins.

### LOW-R5-1 — Phase 03 criteria mostly traced; "per-dimension posture slider" thin

- `acceptance-metrics.md:36` lists "per-dimension posture slider" as a Phase 03 exit criterion; posture-ladder.md does NOT reference per-dimension sliders (only 5-tier global enum). LOW — Phase 03 deliverable open question, but spec lacks coverage scaffolding.

### Acceptance assertion

- Phase 00 exit criteria → analysis-doc convergence + GH-issue manifest + redteam status: traced to acceptance-metrics.md test path.
- Phase 01 exit criteria → boundary-conversation.md, daily-digest.md, ledger.md export verifier, shamir-recovery.md, channel-adapters.md, authorship-score.md: all traced.
- Phase 02 exit criteria → distribution.md, runtime-abstraction.md conformance vectors, channel-adapters.md, foundation-health-heartbeat.md, foundation-ops.md mirrors: mostly traced. Three under-specified items (R5-1).
- Phase 03 exit criteria → shared-household.md, weekly-posture-review.md, monthly-trust-report.md: traced. Per-dimension slider thin (R5-1).
- Phase 04 exit criteria → enterprise-deployment.md, channel-adapters.md, model-adapter.md, skill-ingest.md WASM, trust-vault.md hidden envelope: traced.

**R5 net:** 1 MED + 1 LOW.

---

## Cross-round patterns

1. **Field-path drift across schemas.** envelope-model.md schema uses `metadata.version`; consumer specs and conformance-vector docs use `envelope_version` as if it were top-level. This is the single most-systemic drift in R3 — touching tool-output-sanitization.md, runtime-abstraction.md (N2 cache invalidation property list), session-state.md, ledger.md (DelegationRecord field). One canonical decision (rename to top-level `envelope_version` OR fix every consumer to dotted path) would close five places.

2. **Ledger entry-type schemas absent from declared producer specs.** Six entry types (RoleEnvelopeCreated, envelope_edit, ritual_completion, channel_connected, channel_disconnected, ClockSkewEvent) lack schema definitions in their declared producer specs. The pattern is "Ledger lists entry → producer spec mentions concept → no schema block." Same failure for three additional schema-thin entries (MigrationAnnouncement, EntryKeyDestruction, shamir_distribution_checklist_update) at MED severity.

3. **R2-HIGH closure verification gap.** Round-2 reported T-022 misclassification removal as closed; Round-3 finds 4 residual references in session-state.md. Pattern: closure markers update one location (Provenance) while leaving cross-references, test descriptions, open-questions, and inline rationale stale. Suggests a closure rubric checklist: for every threat-removal closure, grep the spec for ALL occurrences and patch each.

4. **§-heading cross-ref naming convention drift.** 14 broken §-refs (MED-R2-4) follow predictable patterns: ref omits qualifier ("§Retention" vs "§Retention + GDPR"), ref adds qualifier ("§Removal" vs "§CO validator step 5"), ref points to a sub-bullet rather than a heading ("§Shadow segment" inside `## Four physical containers`), ref preserves source-doc paragraph numbers ("§5.3") rather than spec headings. Bulk normalization pass would fix all 14 mechanically.

5. **Algorithm signatures need a single canonical definition.** `evaluate_cross_domain_rules` (HIGH-R2-1), `tool_output_sanitize` Purpose blurb (HIGH-R2-2), and `is_subset_envelope` (MED-R2-6) all show the same problem: function declared with one parameter list and invoked with another, OR section-heading-name vs function-name mismatch. A spec-level discipline of "function signatures appear once, in their owning spec's `## Algorithm` section, and every cross-ref cites name-only" would close this.

---

## Recommended disposition

### Must fix before convergence (CRIT + HIGH)

1. **CRIT-R2-1** — pick canonical `envelope.envelope_version` location; align every consumer.
2. **CRIT-R2-2** — define `imported_constraints[]` item shape (template_origin, template_hash) in envelope-model.md schema.
3. **HIGH-R2-1** — align `evaluate_cross_domain_rules` parameter names between caller (tool-output-sanitization.md) and callee (cross-domain-flows.md).
4. **HIGH-R2-2** — fix `tool_output_sanitize` Purpose-line signature drift in tool-output-sanitization.md:5.
5. **HIGH-R2-3** — add `## Schema` to grant-moment.md OR fix runtime-abstraction.md:127 cross-ref.
6. **HIGH-R2-4** — strike T-022 from session-state.md lines 65, 199, 211, 217 (4-place residual closure).
7. **HIGH-R2-5** — resolve T-031 orphan (drop test or define threat).
8. **HIGH-R2-6** — define `RoleEnvelopeCreated` Ledger-entry schema.
9. **HIGH-R2-7** — define `envelope_edit` Ledger-entry schema.
10. **HIGH-R2-8** — define `ritual_completion` Ledger-entry schema in chosen owner spec.
11. **HIGH-R2-9** — define `channel_connected` / `channel_disconnected` / `ClockSkewEvent` schemas.

### Should fix in current session (MED)

12. **MED-R2-1** — clarify imported cross-domain rule consumption (algorithm or doc).
13. **MED-R2-2** — replace dict-membership `in` check with explicit AST-match loop in session-state.md:123.
14. **MED-R2-3** — fix tool-output-sanitization.md:43 comment (`latency_budget_ms` → `tool_output_budget_bytes`).
15. **MED-R2-4** — bulk normalization pass on 14 broken §-refs.
16. **MED-R2-5** — resolve T-061 reserved-vs-defended.
17. **MED-R2-6** — pick canonical name for sub-agent-delegation.md primary verifier function.
18. **MED-R3-1** — schema-thin Ledger entries (MigrationAnnouncement, EntryKeyDestruction, shamir_distribution_checklist_update).
19. **MED-R4-1** — foundation-health-heartbeat T-041 provenance vs cross-reference drift.
20. **MED-R5-1** — Phase 02 acceptance-criteria spec coverage (QR-pair, install-to-first-value, binary size).

### Defer (LOW)

21. LOW-R3-1 fuzzy heading drift (six items).
22. LOW-R5-1 per-dimension posture slider Phase 03 placeholder.

---

## Verdict

**NOT CONVERGED.** Round 3 found 2 CRIT + 9 HIGH (plus 13 MED + 6 LOW) findings via full-sibling re-derivation. Convergence requires 0 CRIT + 0 HIGH across two consecutive rounds; this round resets the convergence counter to zero. Round 2 closures that landed are intact (envelope-model new fields, session-state.pre_authorized_patterns schema, ledger.time_anchor row, foundation-health-heartbeat duplicate Purpose, ledger.§Consent layer cross-ref, foundation-ops registry #18, runtime-abstraction.AssembledPrompt, envelope-library + model-adapter spec mints).

A focused remediation pass — concentrated on (a) the envelope_version field-path canonical decision and (b) the six missing Ledger entry-type schemas — would close 1 CRIT + 4 HIGH directly and clear most of the cross-spec drift cluster. After that pass, a clean R4 should land 0 HIGH; then R5 + R6 confirm 2-round convergence.

**Files audited:** all 37 specs in `/Users/esperie/repos/dev/envoy/specs/` plus `_index.md`. Anchor docs (`workspaces/phase-00-alignment/01-analysis/00..11.md`) consulted for threat enumeration and source-of-truth verification. R2-baseline doc (`round-2-specs-comprehensive.md`) NOT trusted; every assertion re-derived from primary sources.
