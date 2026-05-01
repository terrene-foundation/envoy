# Round 4 — Specs Comprehensive Audit

**Scope:** Full re-derivation against `/Users/esperie/repos/dev/envoy/specs/` (37 spec files + `_index.md`) and 12 frozen analysis docs in `workspaces/phase-00-alignment/01-analysis/`. R1 + R2 + R3 outputs explicitly NOT trusted; every assertion re-derived per `rules/specs-authority.md` MUST Rule 5b.

**Methodology:** R1 completeness, R2 full-sibling re-derivation, R3 orphan detection, R4 threat-model coverage, R5 acceptance-criterion traceability. Mechanical sweeps (`grep` per-section, per-field, per-threat) + LLM judgment.

---

## Severity distribution

| Severity     | Count |
| ------------ | ----- |
| **CRIT**     | 0     |
| **HIGH**     | 1     |
| **MED**      | 12    |
| **LOW**      | 4     |
| **Total**    | 17    |

**Verdict:** NOT CONVERGED. R3-CRIT (×2) and R3-HIGH (×7 of 9) closures landed cleanly and are confirmed intact; HIGH-R2-3 (grant-moment §Schema), HIGH-R2-4 (session-state T-022 residuals), HIGH-R2-5 (T-031 orphan threat), HIGH-R2-6/7/8/9 (Ledger entry schemas) all closed structurally. Round-4 surfaces 1 net-new HIGH (`skill_removal` Ledger entry has no producer §Removal section in skill-ingest.md AND no schema, violating `_index.md:72` mandate — same orphan-Ledger-entry failure class as the closed R3 set, missed in the R3 sweep). 12 MED findings persist from R3 (most §-heading drift in MED-R2-4; algorithm/comment/threat-coverage drifts in MED-R2-2/3/5/6 + MED-R4-1 + MED-R5-1) — none of these were dispositioned in the R3-fix pass between R3 and R4. The convergence counter remains at zero; R4 fails the 0-HIGH threshold.

---

## R1 — Completeness sweep

Every spec MUST carry `## Purpose / ## Provenance / ## Schema (if owns one) / ## Algorithm (if owns one) / ## Error taxonomy / ## Cross-references / ## Test location / ## Open questions`. Mechanical grep across all 36 non-index specs confirms every mandatory heading present (Purpose=1, Provenance=1, Error taxonomy=1, Cross-references=1, Test location=1, Open questions=1 across all 36 files). **R1: 0 findings.**

---

## R2 — Full-sibling re-derivation (cross-spec drift)

### Round-3 closure verification (all confirmed landed)

- **CRIT-R2-1** (envelope_version field-path): closed. `envelope-model.md:21` declares `envelope_version` as top-level int; consumer reads at `tool-output-sanitization.md:58` (`envelope.envelope_version`), `runtime-abstraction.md:106,150,221`, `session-state.md:56,97,166`, `grant-moment.md:26`, `ledger.md:102`, `trust-lineage.md:45,56,204` all align with top-level field name. Mechanical grep against `metadata.version` returns zero hits. **VERIFIED.**
- **CRIT-R2-2** (`imported_constraints[]` shape): closed. `envelope-model.md:42, 49, 54, 61, 67` declare item shape `{constraint_id, rule_ast, authored, template_origin, template_hash}`. Consumer `authorship-score.md:49-51` reads `c.template_origin` + `c.template_hash` against the now-defined shape. **VERIFIED.**
- **HIGH-R2-1** (`evaluate_cross_domain_rules` kwargs): closed. `tool-output-sanitization.md:65,67` uses `output_bytes=` + `registry_version=`; matches callee `cross-domain-flows.md:66` `def evaluate_cross_domain_rules(output_bytes, tool_name, envelope, registry_version)`. **VERIFIED.**
- **HIGH-R2-2** (`tool_output_sanitize` Purpose blurb): closed. `tool-output-sanitization.md:5` reads `tool_output_sanitize(output, tool_name, envelope)` matching the surface table at line 18-22 + algorithm signature at line 33 + runtime ABC at `runtime-abstraction.md:89`. **VERIFIED.**
- **HIGH-R2-3** (grant-moment §Schema): closed. `grant-moment.md:13-72` introduces `## Schema` with `GrantMomentRequest` (line 15) + `GrantMomentResult` (line 49) JSON schemas. Cross-ref from `runtime-abstraction.md:127` resolves. **VERIFIED.**
- **HIGH-R2-4** (T-022 session-state residuals): closed. `session-state.md:65` rewrites rationale to "intentional per the T-013 composition-aware defense"; `:199` reads `T-013, T-015, T-019`; `:211` reads `T-013/T-015/T-019`; `:217` rewrites. Mechanical grep confirms zero T-022 references in session-state.md. **VERIFIED.**
- **HIGH-R2-5** (T-031 orphan threat): closed. `trust-lineage.md:198` test path renamed to `test_t030_response_key_rotation_migration.py`. Mechanical grep `T-031|T031|t031` across all specs returns zero hits. **VERIFIED.**
- **HIGH-R2-6** (`RoleEnvelopeCreated` schema): closed. `ledger.md:51` producer ref updated to `§Ledger entry schemas §RoleEnvelopeCreated`; schema block at `ledger.md:98-105`. **VERIFIED.**
- **HIGH-R2-7** (`envelope_edit` schema): closed. `ledger.md:52` producer ref updated; schema block at `ledger.md:107-114`. **VERIFIED.**
- **HIGH-R2-8** (`ritual_completion` schema): closed. `ledger.md:73` producer ref updated; schema block at `ledger.md:116-133`. **VERIFIED.**
- **HIGH-R2-9** (`channel_connected/disconnected/ClockSkewEvent` schemas): closed. `ledger.md:77,78,82` producer refs updated; schema blocks at `ledger.md:135-150` (channel_*) and `:152-166` (ClockSkewEvent). **VERIFIED.**

### Findings persisting from R3 (not dispositioned in R3-fix pass)

#### MED-R4-1 — `tool-output-sanitization.md:43` comment misnames field

- **Where:** Algorithm step 2 comment `# 2. Size budget check — per envelope.semantic_checks.latency_budget_ms;`
- **Reality:** The check at line 45 compares `len(canonical_bytes) > envelope.tool_output_budget_bytes`. The comment refers to `latency_budget_ms` (a time budget) while the actual check is bytes-against-byte-budget. Same finding as R3 MED-R2-3. **NOT FIXED between R3 and R4.**
- **Disposition:** Fix the comment to read `# 2. Size budget check — per envelope.tool_output_budget_bytes;`.

#### MED-R4-2 — `session-state.md:123` membership test inconsistent with schema

- **Schema:** `session-state.md:53-55` declares `pre_authorized_patterns: [{pattern_id, tool_name, args_pattern_ast, authored_at, scope}]` (list of dicts).
- **Algorithm:** `session-state.md:123` `if fp_key in session.pre_authorized_patterns:` — `in` operator on a list of dicts only matches whole-dict equality, not fingerprint-key membership. Prose at line 61 says "Lookup is structural AST-match against `args_pattern_ast`."
- **Severity rationale:** Pseudocode does not implement the documented semantics. Same finding as R3 MED-R2-2. **NOT FIXED between R3 and R4.**
- **Disposition:** Replace line 123 with explicit AST-match loop: `for p in session.pre_authorized_patterns: if match_ast(p["args_pattern_ast"], args): return GateResult.RECOGNIZED`.

#### MED-R4-3 — `T-061` reserved-vs-defended drift in distribution.md

- **Source:** `01-analysis/09-threat-model.md:671` — "T-061 — (reserved — not currently used; leaves room in the numbering for a future binding-specific threat)".
- **Spec claim:** `distribution.md:87` cross-references list "T-050a, T-050b, T-060, T-061" and `distribution.md:95` declares `tests/regression/test_t061_distribution_attack_n3_mirror.py` — T-061 defense.
- **Drift internal to distribution.md:** Provenance Threats mitigated (line 10) lists "T-050a, T-050b, T-060" — without T-061. Cross-references list (line 87) includes T-061 — without provenance support.
- **Severity rationale:** Same finding as R3 MED-R2-5. **NOT FIXED between R3 and R4.**
- **Disposition:** Either (a) propose T-061 as a real threat in the source anchor and document the mitigation primitive, or (b) drop T-061 from cross-references and rename the test to reference T-060 (to which N=3 mirror divergence properly belongs).

#### MED-R4-4 — `is_subset_envelope` invocation vs definition name+arg-order mismatch

- **Where:** `sub-agent-delegation.md:36` reads "Envoy runtime re-computes from scratch on every sub-agent invocation using `is_subset_envelope(sub, parent)`". Section heading line 38 is `## \`is_subset_envelope\` algorithm`. Function defined at line 41 is `verify_subset_proof_independently(parent: EnvelopeConfig, sub: EnvelopeConfig)`.
- **Drift:** Two function names referenced for the same primitive (`is_subset_envelope` vs `verify_subset_proof_independently`); argument order also reversed (`(sub, parent)` at the invocation reference vs `(parent, sub)` in the definition).
- **Severity rationale:** Same finding as R3 MED-R2-6. **NOT FIXED between R3 and R4.**
- **Disposition:** Pick one canonical name; align text + heading + function to use it.

#### MED-R4-5 — Heartbeat T-041 cross-reference broader than provenance claim

- **Where:** `foundation-health-heartbeat.md:71` cross-references `T-041` in addition to T-052/T-054/T-023/T-024. Provenance line 10 Threats mitigated lists `T-052, T-054, T-023/T-024 falsifiability measurement` — no T-041.
- **Severity rationale:** Cross-references over-claim relative to provenance. Same finding as R3 MED-R4-1. **NOT FIXED between R3 and R4.**
- **Disposition:** Either add T-041 to provenance Threats mitigated (defense-in-depth claim is legitimate via the `DuressFlagLeakageRefusedError` at line 60), or drop T-041 from cross-references.

#### MED-R4-6 — Phase 02 acceptance criteria not all spec-traced

- **Where:** `acceptance-metrics.md:32` lists Phase 02 exit criteria including "mobile QR-pair <30s", "install-to-first-value <10min mobile", "binary <50 MB". Same finding as R3 MED-R5-1.
- **Trace gap:**
  - "mobile QR-pair <30s" — `channel-adapters.md` mentions QR codes only in shared-household context.
  - "install-to-first-value <10min mobile" — `distribution.md` carries no end-to-end timing test path; `boundary-conversation.md:30` targets ~15min for a different ritual.
  - "binary <50 MB" — no spec owns the size constraint or its verification path.
- **Severity rationale:** **NOT FIXED between R3 and R4.**
- **Disposition:** Either add owning specs (e.g. `distribution.md` gets `## Install-to-first-value` with timing test path + binary-size verification), or relegate these to `## Open questions` until Phase 02 work begins.

#### MED-R4-7 — Broken §-section cross-refs (still 8 of original 14 unfixed)

The following cross-references point to specific `§Heading` sections that do not exist as named headings in the target spec. Persistent subset of R3 MED-R2-4. **NOT FIXED between R3 and R4.**

| Citing spec                          | Reference                                                | Reality                                                                                            |
| ------------------------------------ | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `authorship-score.md:30`             | `specs/foundation-ops.md §Template registry`             | No `## Template registry` heading; closest is `## Infrastructure inventory` #1 "Envelope Library registry" |
| `authorship-score.md:34`             | `specs/foundation-ops.md §Template registry`             | Same as above                                                                                      |
| `cross-domain-flows.md:50`           | `specs/foundation-ops.md §Classifier registry #10`       | No `## Classifier registry` heading; #10 lives inside `## Infrastructure inventory`               |
| `tool-output-sanitization.md:90`     | `specs/foundation-ops.md §Classifier registry §Phase 01 extension` | No `## Classifier registry` heading; no `§Phase 01 extension` sub-section                         |
| `envelope-library.md:49`             | `specs/foundation-ops.md §Moderator queue`               | No such heading; closest is `## Spam flood defense (T-092)`                                       |
| `ledger.md:50`                       | `specs/trust-lineage.md §Device-attestation enforcement` | Paragraph inside `### GenesisRecord` (line 33); no top-level heading                              |
| `ledger.md:71`                       | `specs/enterprise-deployment.md §Disablement flow`       | Heading is `## Disablement (T-024 R2-H5)` (no "flow" suffix)                                      |
| `posture-ladder.md:90`               | `specs/enterprise-deployment.md §AUTONOMOUS carveout`    | No such heading; relevant content is at `## Posture-ratchet under enterprise mode` (line 62)     |
| `a2a-messaging.md:41`                | `specs/envelope-model.md §5.3`                           | Source-doc paragraph reference; envelope-model.md uses different section structure                |

- **Severity rationale:** Each ref independently MED — readers can usually locate the content but mechanical cross-ref validation fails. Counted as one cluster MED (R3 reduced from 14 to 9 broken refs after partial closures landed; remainder persist).
- **Disposition:** Bulk normalization pass. Either rename headings in target specs to match cited form, or update citing specs to reference correct heading text.

### New finding — emerged from R3-fix-pass-completeness check

#### HIGH-R4-1 — Orphan Ledger entry: `skill_removal` schema missing AND producer §-section absent

- **Ledger.md row:** `ledger.md:76` — `skill_removal` claims producer `specs/skill-ingest.md §Removal` (Genesis-key-signed).
- **Reality:** `skill-ingest.md` has NO `## Removal` heading. Mechanical grep across the file for `removal|uninstall|Uninstall|Removal` returns one hit at line 121 (open question about "auto-uninstall"), no schema, no algorithm, no producer section. The `## Install flow` (line 67) covers install only.
- **Severity rationale:** Per `_index.md:72`: "Every Ledger entry type listed in specs/ledger.md §Entry types MUST have a named producer spec owning its schema (per `rules/orphan-detection.md`)." `skill_removal` violates this on both counts — no producer §-section AND no schema. This is the same orphan-Ledger-entry failure class as R3 HIGH-R2-6/7/8/9 (which were closed) — missed in the R3 sweep because the §-ref drifts at MED-R2-4 obscured the fact that the underlying section did not exist at all. **HIGH per `rules/orphan-detection.md` Rule 1.**
- **Disposition:** Either (a) add `## Removal` (or `## Uninstall flow`) to skill-ingest.md with schema for `skill_removal` Ledger entry (type, schema_version, skill_id, removal_reason ∈ {user_action, registry_revocation, abuse_flag_resolved, force_uninstall_on_pattern_match}, signed_by, signature_hex), or (b) consolidate into ledger.md §Ledger entry schemas with cross-ref preserved, mirroring the R3 closure pattern for the other six entry types.

### MED-R4-8 cluster — Schema-thin Ledger entries (no formal JSON schema in producer spec)

The following entry types have a named producer spec section, but the section provides only prose / one-line descriptions, NOT a formal JSON schema block. Same orphan-detection-Rule-1 failure class as R3 MED-R3-1 (which was closed for the three named entries). **NOT FIXED between R3 and R4 for the remaining cases:**

| Entry type                       | Producer claimed                              | Schema status                                                                          |
| -------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------- |
| `unlock_event`                   | `specs/trust-lineage.md §Duress honeypot`     | trust-lineage.md:133-138 prose; no JSON schema                                         |
| `posture_change`                 | `specs/posture-ladder.md §Algorithm`          | posture-ladder.md:95-121 has `posture_change()` Python function but no entry-type JSON |
| `model_switch`                   | `specs/runtime-abstraction.md §Runtime picker` | runtime-abstraction.md:198-200 prose; no JSON schema                                   |
| `runtime_switch`                 | `specs/runtime-abstraction.md §Runtime picker` | Same — prose; no JSON schema                                                           |
| `HouseholdInviteAcceptedRecord`  | `specs/shared-household.md §Schema`           | shared-household.md:79-87 one-line bullet only; no JSON schema                         |
| `HouseholdExitRecord`            | `specs/shared-household.md §Schema`           | Same — bullet only                                                                     |
| `HouseholdAbuseFlaggedRecord`    | `specs/shared-household.md §Schema`           | Same — bullet only                                                                     |
| `HouseholdAbuseResolvedRecord`   | `specs/shared-household.md §Schema`           | Same — bullet only                                                                     |
| `CoPresenceVerifiedRecord`       | `specs/shared-household.md §Co-presence verification` | shared-household.md:23-27 prose; no JSON schema                                  |

- **Severity rationale:** Per `_index.md:72` strict reading these would be HIGH; pragmatic disposition (matching R3-MED-R3-1 disposition for the now-closed MigrationAnnouncement / EntryKeyDestruction / shamir_distribution_checklist_update) is MED — schema exists implicitly via context but the formal block is absent. Counted as one cluster MED.
- **Disposition:** Mirror the R3 closure pattern: consolidate the missing schemas into `ledger.md §Ledger entry schemas` with concise JSON blocks declaring `type`, `schema_version`, payload fields, signer, signing scope; OR add the schemas inline under the named producer §-section.

#### MED-R4-9 — Imported cross-domain rules path described in envelope-model.md not consumed by `evaluate_cross_domain_rules`

- **Schema doc:** `envelope-model.md:91` — "Imported cross-domain rules ride in `data_access.imported_constraints` + `communication.imported_constraints` per the cross-domain-flows.md mapping."
- **Algorithm reality:** `cross-domain-flows.md:66-91` `evaluate_cross_domain_rules` reads only `envelope.cross_domain_rules_authored + foundation_defaults(registry_version)`. Never iterates `data_access.imported_constraints` or `communication.imported_constraints`.
- **Severity rationale:** Same finding as R3 MED-R2-1. **NOT FIXED between R3 and R4.**
- **Disposition:** Either expand `evaluate_cross_domain_rules` to consume the imported lists, or revise the envelope-model.md note to clarify imported rules are NOT consumed by the cross-domain rule engine.

---

## R3 — Orphan detection

### HIGH-R4-1 (counted above)

`skill_removal` orphan — entire §-section missing in producer spec.

### MED-R4-8 cluster (counted above)

9 schema-thin Ledger entries with prose-only producer sections.

### Algorithm-internal orphans (LOW, no severity bump)

#### LOW-R4-1 — `ledger-merge.md:27` references signed `original_parent_hash` field absent from ledger.md envelope schema

- **Where:** `ledger-merge.md:25-33` algorithm declares `entry.merged_parent_hash` (derived) and `entry.original_parent_hash` (signed); line 33 reiterates "Each entry carries `original_parent_hash` (signed) + `merged_parent_hash` (derived)."
- **Schema reality:** `ledger.md:14-34` Entry envelope schema does NOT declare these fields. Field naming in the schema is `parent_hash` only.
- **Severity rationale:** The two fields are merge-time-only (post-merge derivations carrying provenance); arguably out of scope of the canonical entry envelope. LOW because the algorithm reads consistently within ledger-merge.md, but cross-spec readers cannot trace where these fields are persisted.
- **Disposition:** Add a `## Post-merge derived fields` section to ledger.md noting the two fields, or document in ledger-merge.md as algorithm-internal only.

---

## R4 — Threat-model coverage

50 threats × {mitigation owner, regression test} matrix. Mechanical sweep against `09-threat-model.md` v3 §3 enumeration.

### Coverage assertion

All 50 enumerated threats (T-001 through T-107 with documented gaps T-009, T-025-T-029, T-032-T-039, T-043-T-049, T-055-T-059, T-062-T-069, T-072-T-079, T-081-T-089, T-095-T-099) carry ≥1 spec claiming the threat AND ≥1 regression test path. Mechanical sweep:
- Every T-NNN appears in some spec's `## Provenance` Threats mitigated.
- Every T-NNN has at least one `tests/regression/test_t<nnn>_*.py` reference (T-011 covered by `test_t010_t011_prompt_injection_structural.py`).

T-031 orphan threat: now eradicated (HIGH-R2-5 closed; mechanical grep zero hits across all specs).

T-061 borderline: still flagged at MED-R4-3 — provenance vs cross-references self-inconsistency in distribution.md persists.

T-041 over-claim: still flagged at MED-R4-5 — foundation-health-heartbeat.md cross-references list T-041 but provenance doesn't.

**R4 net:** carried forward from R3 as MED-R4-3 + MED-R4-5 above; no new threat-coverage findings.

---

## R5 — Acceptance-criterion traceability

Phase 00–04 exit criteria in `acceptance-metrics.md:22-40` traced to named primitives + test paths.

### MED-R4-6 (counted above)

Phase 02 criteria not all spec-traced (mobile QR-pair, install-to-first-value, binary <50 MB) — same R3 MED-R5-1 finding, persisted unfixed.

### LOW-R4-2 — Phase 03 "per-dimension posture slider" thin

- `acceptance-metrics.md:36` lists "per-dimension posture slider" as a Phase 03 exit criterion; `posture-ladder.md` does NOT reference per-dimension sliders (only 5-tier global enum). Same finding as R3 LOW-R5-1, **NOT FIXED**. LOW.

### Acceptance assertion

- Phase 00 exit criteria → analysis-doc convergence + GH-issue manifest + redteam status: traced to `acceptance-metrics.md` test path. ✓
- Phase 01 exit criteria → boundary-conversation.md, daily-digest.md, ledger.md export verifier, shamir-recovery.md, channel-adapters.md, authorship-score.md: all traced. ✓
- Phase 02 exit criteria → distribution.md, runtime-abstraction.md conformance vectors, channel-adapters.md, foundation-health-heartbeat.md, foundation-ops.md mirrors: mostly traced. Three under-specified items (MED-R4-6).
- Phase 03 exit criteria → shared-household.md, weekly-posture-review.md, monthly-trust-report.md: traced. Per-dimension slider thin (LOW-R4-2).
- Phase 04 exit criteria → enterprise-deployment.md, channel-adapters.md, model-adapter.md, skill-ingest.md WASM, trust-vault.md hidden envelope: traced. ✓

**R5 net:** 1 MED + 1 LOW (both carried from R3 unfixed).

---

## Cross-round patterns

1. **R3 closures landed cleanly across the board.** Both R3-CRITs and 7 of 9 R3-HIGHs closed structurally, cross-spec consumers re-aligned, no regressions introduced. The closure pattern (consolidate Ledger schemas at ledger.md §Ledger entry schemas; rename test files; strike residual threat references; promote envelope_version to top-level) was executed consistently. Round-3-fix discipline was high-quality.

2. **R3 MEDs were not dispositioned in the fix-pass.** All R3 MED findings (R2-1, R2-2, R2-3, R2-4, R2-5, R2-6, R3-1 partial, R4-1, R5-1, LOW-R3-1, LOW-R5-1) appear unchanged at R4. The R3-fix-pass scope was limited to CRIT + HIGH; MED + LOW were deferred. R4 confirms the MED bucket persists as a 12-finding shelf that will need a dedicated bulk pass.

3. **§-heading cross-ref drift is the largest single MED cluster.** 9 broken §-refs (down from 14 at R3 due to the partial closure of ledger.md § references in the HIGH-R2-6/7/8/9 fixes). All 9 follow predictable patterns: ref omits qualifier ("§Disablement flow" vs "§Disablement (T-024 R2-H5)"), ref points to a non-heading concept name ("§Classifier registry" vs item #6 inside `## Infrastructure inventory`), ref preserves source-doc paragraph numbers ("§5.3"). Bulk normalization pass would close all 9 mechanically.

4. **Schema-thin Ledger entries are the second largest cluster.** 9 entry types (unlock_event, posture_change, model_switch, runtime_switch, 4 Household*Records, CoPresenceVerifiedRecord) have producer-spec sections that describe the entry in prose but never declare the formal JSON schema. R3 closed three of these (MigrationAnnouncement, EntryKeyDestruction, shamir_distribution_checklist_update) by consolidating into ledger.md §Ledger entry schemas — a clean precedent. The remaining 9 await the same treatment.

5. **One orphan-Ledger-entry slipped past R3.** `skill_removal` (HIGH-R4-1) is the same failure class as the R3 HIGH-R2-6/7/8/9 set — Ledger entry with a producer-spec ref pointing at a §-section that does not exist. The R3 sweep against MED-R2-4 broken §-refs would have surfaced it had the sweep been completed; the R3-fix-pass focused on the 4 R3-HIGH orphan entries with §-refs into ledger.md and missed the 1 entry with a §-ref into skill-ingest.md. Lesson for future audit rounds: orphan detection MUST grep both directions (entry-types-without-schema AND producer-spec-§-refs-without-target).

6. **CRIT-class findings have stabilized.** Two consecutive rounds (R3 surfaced 2 CRIT, R4 finds 0 CRIT) suggests the CRIT bucket is empty given the current spec set. The remaining work to converge is HIGH (1) + MED (12) + LOW (4).

---

## Recommended disposition

### Must fix before convergence (HIGH)

1. **HIGH-R4-1** — Resolve `skill_removal` orphan. Either (a) add `## Removal` (or `## Uninstall flow`) section to skill-ingest.md with formal JSON schema for the entry type, or (b) consolidate into ledger.md §Ledger entry schemas mirroring the R3 closure pattern. Producer-spec reference at ledger.md:76 must be updated to match the chosen disposition.

### Should fix in current session (MED) — bulk pass recommended

2. **MED-R4-1** — fix tool-output-sanitization.md:43 comment (`latency_budget_ms` → `tool_output_budget_bytes`).
3. **MED-R4-2** — replace dict-membership `in` check with explicit AST-match loop in session-state.md:123.
4. **MED-R4-3** — resolve T-061 reserved-vs-defended (define threat OR drop test claim and rename to T-060).
5. **MED-R4-4** — pick canonical name for sub-agent-delegation.md primary verifier function (align text @line 36, heading @line 38, function @line 41).
6. **MED-R4-5** — foundation-health-heartbeat.md T-041 provenance vs cross-reference drift (add T-041 to provenance OR drop from xrefs).
7. **MED-R4-6** — Phase 02 acceptance-criteria spec coverage (mobile QR-pair, install-to-first-value, binary <50 MB).
8. **MED-R4-7** — bulk normalization pass on 9 broken §-refs (rename headings or update citations).
9. **MED-R4-8** — schema-thin Ledger entries: 9 entry types await schema consolidation per R3 closure pattern.
10. **MED-R4-9** — clarify imported cross-domain rule consumption (algorithm or doc).

### Defer (LOW)

11. **LOW-R4-1** — ledger-merge.md `original_parent_hash` / `merged_parent_hash` field documentation.
12. **LOW-R4-2** — Phase 03 per-dimension posture slider — relegate to open question or scaffold spec coverage.
13. **LOW-R4-3** (carried from R3) — fuzzy heading drift remaining: `ledger.md §Retention`, `ledger.md §Export`, `trust-lineage.md §two-head-commitments`, `acceptance-metrics.md §Kill criteria`, `skill-ingest.md §Install`, `channel-adapters.md §Lifecycle`, `shamir-recovery.md §Distribution checklist` (now §Distribution guidance). Bulk normalization sufficient.
14. **LOW-R4-4** — enterprise-deployment.md schema-version field naming (`edr_schema_version` in DelegationRecord at trust-lineage.md:51 vs `schema_version: "edr/1.0"` in EnterpriseDeploymentRecord at enterprise-deployment.md:23 — naming OK but cross-ref alignment could be tightened).

---

## Verdict

**NOT CONVERGED.** Round 4 found 0 CRIT + 1 HIGH (plus 12 MED + 4 LOW) findings via full-sibling re-derivation. Convergence requires 0 CRIT + 0 HIGH across two consecutive rounds; this round finds 1 net-new HIGH (HIGH-R4-1 `skill_removal` orphan), so the convergence counter resets to zero.

R3 closure quality was high — both R3-CRITs and 7 of 9 R3-HIGHs closed structurally with no regressions. The single net-new HIGH at R4 is the same orphan-Ledger-entry class the R3-fix-pass closed for 4 other entries, missed because the R3 sweep was scoped to the §-refs that pointed into ledger.md (where the closures consolidated) and did not extend to §-refs into skill-ingest.md.

A focused remediation pass — concentrated on (a) HIGH-R4-1 `skill_removal` schema consolidation (mirroring R3 closure pattern: 1 schema block + 1 producer ref update; ~10 LOC), and (b) the 12 MED bulk findings (most are mechanical: §-ref renaming, comment-line text fix, threat list alignment, schema block additions) — would close 1 HIGH + 9 MED in a single session. After that pass, a clean R5 should land 0 HIGH and start the 2-round convergence count from one. R5 + R6 would then confirm 2-round convergence per `_index.md:84` discipline.

**Files audited:** all 37 specs in `/Users/esperie/repos/dev/envoy/specs/` plus `_index.md`. Anchor docs (`workspaces/phase-00-alignment/01-analysis/00..11.md`) consulted for threat enumeration and source-of-truth verification. R3-baseline doc (`round-3-specs-comprehensive.md`) NOT trusted; every assertion re-derived from primary sources. Closure verification of R3 fixes: 11 of 11 confirmed intact via mechanical sweep against the post-fix spec contents.
