# Round 2 — specs/ Comprehensive Review (35 files × 5 sub-rounds, full-sibling re-derivation)

**Target:** `/Users/esperie/repos/dev/envoy/specs/` (35 spec files + `_index.md`)
**Authority:** `rules/specs-authority.md` MUST Rule 5b — full-sibling re-derivation against ALL 35 spec files.
**Anchors (FROZEN):** 12 analysis docs in `workspaces/phase-00-alignment/01-analysis/`.
**Round-1 baseline (NOT trusted):** `round-1-specs-comprehensive.md` — 7 CRIT + 23 HIGH + 27 MED + 9 LOW (66 findings).
**Date:** 2026-04-29
**Verdict:** **NOT CONVERGED** — 4 CRIT + 11 HIGH + 14 MED + 6 LOW (35 findings).

All findings recomputed from scratch from the current state of `specs/`. Many R1 findings are now resolved (lamport_time + intent_id + duplicate-name fixes landed; posture-ladder/shared-household/session-state/tool-output-sanitization/cross-domain-flows specs minted; ledger.md §Entry types now enumerates producers; Open Questions sections added everywhere). Remaining findings concentrate on (a) envelope-schema fields read by descendant specs but never declared in envelope-model.md schema, (b) one duplicated `## Purpose` heading, (c) a misclassified threat ID, (d) a small set of cross-spec naming-drift residuals, (e) helper-function definitions still implicit.

---

## Severity distribution

| Round                                | CRIT  | HIGH   | MED    | LOW   |
| ------------------------------------ | ----- | ------ | ------ | ----- |
| R1 Completeness                      | 0     | 1      | 4      | 1     |
| R2 Full-sibling re-derivation        | 3     | 5      | 4      | 3     |
| R3 Orphan detection                  | 1     | 3      | 3      | 1     |
| R4 Threat-model coverage             | 0     | 2      | 2      | 1     |
| R5 Acceptance-criterion traceability | 0     | 0      | 1      | 0     |
| **Total**                            | **4** | **11** | **14** | **6** |

---

## R1 — Completeness (mandatory sections per `_index.md` §Spec file conventions)

All 35 specs now carry `## Purpose / ## Provenance / ## Error taxonomy / ## Cross-references / ## Test location / ## Open questions`. `## Schema` and `## Algorithm` are present where the spec owns one. R1 is largely converged from the R1-baseline 6 HIGH + 12 MED.

### HIGH

- {HIGH, foundation-health-heartbeat.md:3 + foundation-health-heartbeat.md:13, duplicated `## Purpose` heading. The file has `## Purpose` at line 3 (one-paragraph telemetry summary) AND `## Purpose` at line 13 (narrow §4.1 carveout summary). Two H2 headings with identical text break Markdown TOC tooling, downstream `_index.md` cross-ref by `§Purpose`, and the `_index.md` §Spec file conventions ordering rule. Second occurrence should be `## Scope` or `## Carveout rationale`.}

### MED

- {MED, runtime-abstraction.md:14, `## Abstract interface` (the file's load-bearing `## Schema`-equivalent section) is structured as a method table per Lifecycle / Trust Lineage / Envelope / Two-phase / Ledger / Classifier / Budget / Runtime device-key / Prompt+tool-output, but each method's row is a one-line natural-language semantics description. Per `_index.md` §Spec file conventions and MUST Rule 3 ("detailed not summary"), the abstract-interface contract should declare per-method (a) preconditions, (b) postconditions, (c) side-effects, (d) idempotency. Currently a downstream implementer can't tell whether `phase_a_sign_intent` is idempotent on retry or whether `ledger_append` is allowed to mutate the input entry.}
- {MED, threat-model.md, `## Mitigation-to-primitive matrix` body line 38 says "Full matrix in doc 09 v3 §4" — punts the load-bearing 50-threats × 4-columns matrix to the analysis doc. Per specs-authority.md MUST Rule 3, the spec MUST be the authority. Acknowledged as `_index.md`-conformant in spirit (specs reference threats which reference doc 09), but a downstream consumer reading specs/ alone cannot answer "for T-NNN, what's the test path?" without leaving specs/. Either reproduce the matrix in threat-model.md or formally re-classify the spec as a passive index file (same disposition as Round-1).}
- {MED, channel-adapters.md:14, `ChannelAdapter` ABC contract was substantially expanded in Round-1 fix to include per-method signatures, timeout, rate-limit, failure semantics — good. But `MessagePayload`, `VisibleSecret`, `GrantMomentPayload`, `DailyDigestPayload`, `WeeklyPostureReviewPayload`, `MonthlyTrustReportPayload`, `SendReceipt`, `GrantMomentReceipt`, `PostureReviewReceipt`, `RateLimitStatus`, `InboundMessage`, `EnvelopeScopeRef` are all type-name-only without schema. Each is a load-bearing struct passed across the adapter contract; missing per-type schema means cross-runtime / cross-channel interop is ambiguous.}
- {MED, foundation-ops.md:35, `## Registry schemas` declares one canonical envelope shape but does NOT specify which of the 17 registries owns which `content_type`. Registry #6 is "Classifier registry (envoy-registry:* namespace)" with `content_type: classifier`; Registry #14 standard-action-corpus is `corpus`; Registry #17 adversarial-skill-patterns is `classifier`. The 17-item table only enumerates IDs + consumer; a per-registry `content_type` column would close the ambiguity.}

### LOW

- {LOW, _index.md:82, "35 specs total at draft v1 (30 original + 5 minted 2026-04-21 …)" — arithmetic check: filesystem has 36 .md files in specs/ (including `_index.md`), and the table lines 17-51 enumerates 35 spec rows. Count is consistent with the description. Round-1 R2-HIGH "30 specs claimed but 30-row table" is RESOLVED. Minor: line 82's "30 original + 5 minted" should reference the 5 minted specs by file name (posture-ladder, shared-household, session-state, tool-output-sanitization, cross-domain-flows) for forensic traceability.}

---

## R2 — Full-sibling re-derivation (cross-spec drift)

### CRIT — algorithm reads field that doesn't exist in envelope-model.md schema

- {CRIT, tool-output-sanitization.md:43-44 + tool-output-sanitization.md:147 vs envelope-model.md:14-78, `tool_output_sanitize` algorithm reads `envelope.tool_output_budget_bytes` (line 43, 44) and `envelope.semantic_checks.tool_output_classifier_ensemble` (line 53). Cross-references section line 147 declares envelope-model.md owns these fields. `envelope-model.md` §Schema (lines 14-78) does NOT declare either field — the closest fields are `envelope.semantic_checks.data_access_classifier_ensemble` and `envelope.semantic_checks.communication_content_classifier_ensemble` + `latency_budget_ms` map. The sanitizer algorithm reads two undeclared fields; fail mode is identical to Round-1 R2-CRIT lamport_time which was fixed by adding to schema. Fix: either add `tool_output_classifier_ensemble` + `tool_output_budget_bytes` to envelope-model.md §Schema, OR change the sanitizer algorithm to consume an existing field.}
- {CRIT, cross-domain-flows.md:68 + cross-domain-flows.md:65 vs envelope-model.md:14-78, `evaluate_cross_domain_rules` algorithm reads `envelope.cross_domain_rules_authored` (line 68) and `envelope.metadata.algorithm_identifier.cross_domain_rules` (line 65). Neither field is declared in envelope-model.md §Schema. The envelope-model.md schema declares `composition_rules` at top level + `metadata.algorithm_identifier {sig, hash, shamir, canonical_json, ensemble_classifiers}` — no `cross_domain_rules` member of `algorithm_identifier`, no top-level `cross_domain_rules_authored`. Same orphan-field shape as the previous CRIT.}
- {CRIT, session-state.md:118 vs envelope-model.md:122-126 + session-state.md:23-56, `first_time_action_gate` algorithm at line 118 reads `session.pre_authorized_patterns` — but `SessionObservedState` schema (session-state.md lines 23-56) does NOT declare a `pre_authorized_patterns` field. envelope-model.md §First-time-action gate (line 125) says "No match AND not in pre-authorized patterns → Grant Moment" but does not say where pre-authorized patterns live. Algorithm reads an undeclared field on the spec's own schema.}

### HIGH — cross-spec naming/drift

- {HIGH, envelope-model.md:101 vs runtime-abstraction.md:39 + runtime-abstraction.md:109, primitive named two ways across two specs. envelope-model.md §Algorithms calls it `intersect_envelopes(a, b)` (line 101); runtime-abstraction.md §Envelope §Lifecycle calls the abstract method `envelope_intersect(a, b)` (line 39, 109). Cross-spec consumers `posture-ladder.md:56`, `shared-household.md:97`, `shared-household.md:100`, `shared-household.md:134` all use `intersect_envelopes`. Naming drift between envelope-model (the owning spec) and runtime-abstraction (the runtime ABC). Fix: pick one — likely `envelope_intersect` in runtime ABC + `intersect_envelopes` in envelope-model is intentional ABC-vs-impl, but should be documented inline as such, otherwise downstream implementers ship divergent symbol names.}
- {HIGH, session-state.md:10 vs anchor doc 09-threat-model.md:297, T-022 misclassified. session-state.md `## Provenance` line 10 claims "T-022 first-time-action injection" as one of its threats mitigated. Anchor doc 09 v3 line 297 defines T-022 as "Envelope Library Sybil (NEW, Cluster E HIGH)" — a supply-chain attack on the Envelope Library, not a session-state concern. skill-ingest.md:10 correctly references T-022 as Sybil. Two specs claim T-022 with two different definitions; only skill-ingest.md is right per the anchor. Fix: session-state.md should reference the actual threat (likely T-013 already covered + T-022 should be removed; or filed as a new threat ID for first-time-action injection).}
- {HIGH, tool-output-sanitization.md:65 vs envelope-model.md:24-28, `evaluate_cross_domain_rules` reads `envelope.metadata.algorithm_identifier.cross_domain_rules` as a sub-field of algorithm_identifier. envelope-model.md schema line 24-28 declares `algorithm_identifier: {sig, hash, shamir, canonical_json, ensemble_classifiers}` — five fields, not six. The cross_domain_rules version-pinning sub-field does not exist. Same family as the R2-CRIT findings; flagged HIGH because the spec is consuming a versioned-registry version pin from the wrong place in the envelope.}
- {HIGH, foundation-health-heartbeat.md:11 + ledger.md:72 vs foundation-health-heartbeat.md (whole file), ledger.md §Entry types row 72 says producer is "specs/foundation-health-heartbeat.md §Consent record" — but foundation-health-heartbeat.md has NO §Consent record section. The heartbeat spec has `## Consent layer` (line 37). Section name drift; downstream consumer can't follow the cross-ref to a non-existent section.}
- {HIGH, channel-adapters.md:145 + channel-adapters.md:226 vs foundation-ops.md:28, channel-adapters.md says "`foundation-ops.md` registry #12 (channel-capability registry, signed Foundation key)" twice. foundation-ops.md numbered list line 28 says registry #12 is "N=3 mirror coordination — Foundation GitHub + IPFS pinned + community redistributor". Wrong registry number — channel-capabilities is NOT in the 17-item registry list at all. Either add registry #18 "channel-capability registry" to foundation-ops.md, or fix the channel-adapters cross-ref.}

### MED — downstream consumer drift

- {MED, sub-agent-delegation.md:65 + sub-agent-delegation.md:84-87, three helper functions still partial. Round-1 R1-HIGH flagged `verify_dimension_subset` / `composition_rules_are_superset` / `classifier_ensemble_is_superset` as undefined. Round-2 fix (sub-agent-delegation.md:84-87) added §Helper functions sub-section with one-paragraph natural-language definitions. Per `_index.md` MUST Rule 3 "detailed not summary", these should be promoted to dedicated `## Algorithm` sub-sections with pseudocode (sub-agent-delegation.md `## Open questions` line 146 explicitly logs this disposition as a downstream-refinement question). Disposition acknowledged but not closed.}
- {MED, cross-domain-flows.md:71-90, `infer_source_domain`, `infer_sink_domain`, `classify`, `match_ast`, `aggregate_verdicts`, `now_ms` all referenced in the algorithm body but not defined inline. `aggregate_verdicts` has a one-line description at line 93; the other 5 are entirely implicit. Mirrors the sub-agent-delegation pattern.}
- {MED, posture-ladder.md:99 + session-state.md:141, multiple specs reference helpers without owning them. posture-ladder.md `posture_change` algorithm at line 99 calls `posture_up_authorship_threshold(current, target, evidence.mode)` and inline-comments "table above" — the table is in §State-transition contract §Ratchet-up §1 with N=0/1/3-or-5/5 thresholds, but no helper function specifies the lookup. session-state.md `session_boundary` calls `count_deferred()` (line 141) — defined nowhere. Pattern: pseudocode helpers stub-named without inline definition.}
- {MED, tool-output-sanitization.md:19-25 vs runtime-abstraction.md:89, contract signature drift. runtime-abstraction.md ABC method line 89 declares `tool_output_sanitize(output, tool_name, envelope) → SanitizeResult`. tool-output-sanitization.md §Surface line 19-25 declares `tool_output_sanitize(output, tool_name, classifier_ensemble, envelope) → SanitizeResult` — 4 parameters vs 3. The owning spec adds `classifier_ensemble` as a separate parameter; the runtime ABC says it's resolved from `envelope`. Cross-spec contract divergence.}

### LOW — prose drift

- {LOW, channel-adapters.md:5, "8 Phase-01 surface" in title; line 162 lists 8 channels (CLI / Web / Telegram / Slack / Discord / WhatsApp / Signal / iMessage). acceptance-metrics.md line 28 says "6 messaging channels E2E" for Phase 01 exit. Internal arithmetic (CLI + Web + 6 messaging = 8) is consistent but the differing nomenclature ("8 surfaces" vs "6 messaging channels") may confuse first-time readers.}
- {LOW, foundation-health-heartbeat.md:28-29, `21 boolean flags` listed: `completed_boundary_conversation, opened_daily_digest_this_week, completed_weekly_posture_review, opened_monthly_trust_report, grant_moment_novelty_approved, grant_moment_novelty_denied, force_install_used_skill, authorship_score_reached_3, authorship_score_reached_5, posture_delegating_active, posture_autonomous_active, budget_monthly_exceeded_50pct, budget_monthly_exceeded_80pct, channel_telegram_active, channel_slack_active, channel_discord_active, channel_whatsapp_active, channel_signal_active, channel_imessage_active, runtime_kailash_rs_active, enterprise_mode_active`. Count: I count 21. Round-1 R1-LOW "~20 listed as 21" is closed.}
- {LOW, _index.md:5 + spec-freeze line 82, "30 original + 5 minted 2026-04-21" — arithmetic 30+5 = 35 specs. R1-LOW count drift in baseline closed. Minor wording: `_index.md` line 82 reads "Current spec freeze state: 35 specs total at draft v1" — the 5 minted specs should be enumerated for forensic traceability (Round-1 LOW carry-forward).}

---

## R3 — Orphan detection

### CRIT — orphan named primitive

- {CRIT, remote-time-anchor.md:23 vs ledger.md:43-90, `time_anchor` Ledger entry type. remote-time-anchor.md §Anchor record line 23 declares `"type": "time_anchor"` as a Ledger entry. ledger.md §Entry types table (lines 47-90) does NOT include `time_anchor`. ledger.md `## Entry types` opening sentence: "Every entry type MUST have a named producer spec that owns its schema, producer context, and verification semantics. Types without a producer spec are BLOCKED from appearing in this list." Conversely, an entry type defined in a producer spec MUST appear in ledger.md's enumerated list. `time_anchor` violates that contract — producer spec exists (remote-time-anchor.md), table-of-types does not list it. Same orphan failure mode as R1's 6+ orphan types pre-fix.}

### HIGH — orphan reference

- {HIGH, anchor doc 09-threat-model.md:778-799 references `specs/envelope-library.md`, no such spec exists. Doc 09 maps T-020 / T-021 / T-022 / T-024 / T-051 / T-092 to `specs/envelope-library.md` (Sybil, FV tier, identity-proofing, fork-tracking, publisher reputation). The Foundation publishing surface lives partly in foundation-ops.md (§Envelope Library registry #1) and partly in skill-ingest.md (publisher Ed25519, Community tier, force_install). No dedicated `envelope-library.md`. Either rename one of the two existing specs OR mint envelope-library.md.}
- {HIGH, anchor doc 09-threat-model.md:775 references `specs/model-adapter.md` for T-017 (training-data extraction), no such spec exists. T-017 mitigation primitive is "LLM response filter + provider-risk annotations" — not in any current spec. Coverage gap on the anchor side becomes a producer-orphan on the spec side.}
- {HIGH, runtime-abstraction.md:88 + envelope-model.md cross-references vs envelope-model.md:14-78, `prompt_assemble` method declared at runtime-abstraction.md line 88 produces an `AssembledPrompt`. The output type `AssembledPrompt` is referenced as a return type but no spec defines its shape. T-015 defense and the system-prompt-pinning contract depend on the canonical form of `AssembledPrompt`; cross-runtime byte-identity is not verifiable without it. envelope-model.md cross-references runtime-abstraction.md but no `## Schema` for `AssembledPrompt` lives in either spec.}

### MED — orphan cross-domain

- {MED, none of 35 specs cite `01-kailash-rs-deep-audit.md`, `02-kailash-py-survey.md`, or `03-primitive-reconciliation.md` in `## Provenance`. The parity grid in `03-primitive-reconciliation.md` carries `PostureStore` / `SQLitePostureStore` / `PostureEvidence` / `TieredAuditDispatcher` primitives. posture-ladder.md:12 references `PostureStore` / `PostureEvidence` / `SQLitePostureStore` in `## Provenance` ("mirrors kailash-py PostureStore / PostureEvidence / SQLitePostureStore") but cites only `00-thesis-and-scope` + `02-envelope-model` + `03-trust-lineage` as source. Audit doc 03 is the authoritative source for those primitives; not citing it in Provenance means cross-SDK parity drift across `kailash-rs-deep-audit` will not trigger a re-derivation of posture-ladder.md. Round-1 R3-MED carry-forward.}
- {MED, foundation-ops.md:31 + skill-ingest.md (whole), `envoy-registry:standard-action-corpus:v1` (foundation-ops.md registry #14) is consumer-named in authorship-score.md:65 (`standard_action_corpus_v1`) but skill-ingest.md `100-benign-corpus` (acceptance-metrics.md:32 + skill-ingest.md test test_co_validator_100_benign_corpus.py + test_co_validator_3_adversarial_corpus.py at lines 109-110) is a different corpus. The 100-benign + 3-adversarial corpus is referenced by acceptance-metrics.md and skill-ingest.md but not registered as a Foundation registry. foundation-ops.md only registers `adversarial-skill-patterns` (#17), not the 100-benign corpus. Either register or document the corpus as out-of-registry.}
- {MED, sub-agent-delegation.md:78 + runtime-abstraction.md:100, `runtime_sign(canonical_form_triple(proof, parent, sub))` reads two helpers — `runtime_sign` (declared in runtime-abstraction.md §Runtime device-key signing line 81 as `runtime_sign(payload) → bytes`) and `canonical_form_triple` (referenced nowhere else). The triple-canonicalization rule is the byte-identity gate for SubsetProof verification across runtimes; without a definition, BET-6 cross-SDK byte-identity for SubsetProof is ambiguous.}

### LOW

- {LOW, foundation-ops.md:24, `Public-email-provider registry` (registry #8) — the YAML data file's schema/cadence remains a downstream-refinement question per foundation-ops.md `## Open questions` line 147. Registry exists in inventory but no schema; explicit deferral, not a blocker. Round-1 LOW carry-forward.}

---

## R4 — Threat-model coverage

`threat-model.md` itself does not reproduce the 50-threat × 4-column matrix (punts to doc 09 v3 §4). Round-2 checks: each threat T-NNN per anchor doc, does at least one spec claim it in `## Provenance` § `Threats mitigated:`?

### HIGH

- {HIGH, threat-model.md `## Open questions` line 80 acknowledges T-014 / T-016 / T-017 unmapped. Same threats unclaimed in any spec's Provenance — `tool-output-sanitization.md:10` mitigates T-010/T-011/T-013 but NOT T-014/T-016/T-017. envelope-model.md mitigates T-013 + T-015 but not T-014/T-016/T-017. session-state.md mitigates T-013/T-015/T-019/T-022 but not T-014/T-016/T-017. T-014 (multi-turn accumulated injection), T-016 (goal drift), T-017 (training-data extraction) — none have a producer spec; tests/regression/test_t014_*.py / test_t016_*.py / test_t017_*.py are absent. Coverage is a documented Open Question in threat-model.md but is also a HIGH threat-coverage finding in absolute terms.}
- {HIGH, threat-model.md line 79 + envelope-model.md:10, T-094 unmapped to any owning spec. Anchor doc 09 line 801 maps T-094 to `specs/envelope-model.md` ("variant of T-015; shared mitigations"). envelope-model.md `## Provenance` Threats mitigated does NOT list T-094 — only T-015 is named. T-094 inherits T-015's regression test path. Per `_index.md` MUST Rule 7 "every documented threat has a test", the threat-coverage gate fails on T-094 + T-014/T-016/T-017. Either add to envelope-model.md's Threats mitigated, or formally declare T-094 = T-015 (variant) such that the variant aliasing is structural.}

### MED

- {MED, threat-model.md ${T-070, T-071}, ui-platform.md:10 mitigates T-070 / T-071. channel-adapters.md:10 also mitigates T-070. data-model.md and trust-vault.md mitigate T-071. T-070 has 3 spec claimants; T-071 has 3 spec claimants. Multiple-spec-claims-same-threat is acceptable for orthogonal defenses, but creates duplicated regression-test trees. Disposition is structural ("which spec owns the test fixture for T-070?") — currently each spec writes its own test, threat-model.md `## Test location` line 70-75 says coverage tests aggregate via `tests/coverage/test_every_threat_has_test.py`.}
- {MED, threat-model.md T-008 mitigation. T-008 = Grant Moment replay. grant-moment.md:73 + ledger.md:207 + ledger-merge.md:84 all reference T-008 in test paths. grant-moment.md error taxonomy at line 58 declares `GrantMomentReplayError` ("Same nonce or intent_id observed twice (T-008 nonce defense)"). But grant-moment.md `## Provenance` line 10 lists Threats mitigated as T-018/T-019/T-093 only — T-008 is NOT in the line. T-008 is therefore claimed in the test path but not in the Provenance threat list. Round-1 R4-HIGH was T-008 not claimed by any spec — partially resolved (claim exists in test path) but `## Provenance` line is still incomplete. Disposition: line-edit grant-moment.md provenance to include T-008.}

### LOW

- {LOW, threat-model.md `## Phase gates` (lines 50-55), Phase 00/01/02/03/04 + Ongoing security review items are narrative bullets, no traceability to individual threats. Round-1 carryover; explicit threat-to-gate mapping would close it (e.g. "Phase 01: threat-model test suite green covers T-001 through T-104 except T-094, T-014, T-016, T-017").}

---

## R5 — Acceptance-criterion traceability

For each Phase exit criterion in acceptance-metrics.md, does the criterion trace to named primitives in other specs + a Tier-3 test path?

### MED

- {MED, acceptance-metrics.md Phase 03 line 36, "5-person Shared Household E2E" — traces to `tests/acceptance/phase_03/test_5_person_shared_household.py` (line 80) + shared-household.md owning spec (✅ exists). Per-criterion trace works. But "P50 latency <10ms Rust / <80ms Python" target has no test path in any spec; no `tests/performance/test_p50_latency_*.py` referenced anywhere. Acceptance criterion under-instrumented at the spec level.}

---

## Cross-round patterns (failure modes)

1. **Envelope-schema fields read by descendant specs but not declared.** Round-1 fixed `lamport_time` + `intent_id` in ledger.md schema; Round-2 finds the same pattern in tool-output-sanitization.md (`tool_output_budget_bytes`, `tool_output_classifier_ensemble`) + cross-domain-flows.md (`cross_domain_rules_authored`, `algorithm_identifier.cross_domain_rules`) + session-state.md (`pre_authorized_patterns`). The two newly-minted specs (tool-output-sanitization, cross-domain-flows) added algorithm bodies that read fields the parent schema (envelope-model.md) never published. Same R2-CRIT class as the lamport_time fix; mechanically identical.

2. **`time_anchor` is the new lamport_time/intent_id pattern at the Ledger-types layer.** The newly-minted remote-time-anchor.md adds a Ledger entry type that ledger.md §Entry types doesn't enumerate. The R1 fix added 6+ types to ledger.md but didn't include `time_anchor`.

3. **Cross-spec helper-function definitions remain implicit in three specs.** sub-agent-delegation.md (3 helpers), cross-domain-flows.md (5 helpers), session-state.md (`count_deferred`), posture-ladder.md (`posture_up_authorship_threshold`) — all reference helpers without owning their pseudocode. This is an `_index.md` MUST Rule 3 "detailed not summary" gap inherited from analysis-doc style.

4. **Threat-ID classification drift and naming-drift residuals.** session-state.md misclassifies T-022 (Sybil) as "first-time-action injection". `intersect_envelopes` vs `envelope_intersect` named two ways. `## Consent record` (in ledger.md cross-ref) vs `## Consent layer` (foundation-health-heartbeat.md actual section). These are mechanical fixes; surface-area for re-occurrence is high without a structural enforcement.

5. **Anchor doc 09 references two non-existent specs (`envelope-library.md`, `model-adapter.md`).** Spec authority is canonical specs/, but anchors are FROZEN — so the inconsistency is on the spec side. Either mint the two specs, or upstream a doc-09 fix to redirect to existing specs (foundation-ops.md, skill-ingest.md).

6. **Audit analysis docs 01-kailash-rs-deep-audit / 02-kailash-py-survey / 03-primitive-reconciliation never feed specs (Round-1 R3-MED carry-forward).** posture-ladder.md mirrors primitives from doc 03 in body but cites docs 00 + 02 + 03-trust-lineage in Provenance — not 03-primitive-reconciliation. Drift signal lost.

---

## Recommended disposition (not prescriptive)

The 4 CRIT findings concentrate on R2 envelope-schema field omissions (3 of 4) plus R3 time_anchor Ledger orphan (1 of 4). All four are mechanical fixes (1-line schema additions) and should be closeable in a single follow-up edit. The 11 HIGH findings cluster around (a) terminology drift on `intersect_envelopes` / `envelope_intersect` (1), (b) section-ref drift (`## Consent record` vs `## Consent layer`) (1), (c) wrong registry-number cross-ref (channel-adapters → foundation-ops #12) (1), (d) misclassified T-022 (1), (e) two missing specs `envelope-library.md` + `model-adapter.md` (2 + 1 missing return type AssembledPrompt = 3), (f) two threat-coverage gaps (T-014/T-016/T-017 + T-094) (2). Single-session work.

**Per `rules/specs-authority.md` MUST Rule 5b**, any spec edit made in response MUST trigger full-sibling re-derivation against all 35 spec files.

**Exit criterion NOT met:** 4 CRIT + 11 HIGH > 0/0 target. **R2 NOT CONVERGED.**

Round 2 has reduced findings from 7 CRIT + 23 HIGH (Round 1) to 4 CRIT + 11 HIGH (Round 2) — 43% CRIT reduction, 52% HIGH reduction. Continued application of the same fix pattern (schema-add when an algorithm reads it; ledger-types-add when a Ledger record is declared elsewhere; rename-or-redirect for naming drift) should drive a Round 3 to 0 CRIT + 0 HIGH and converge.
