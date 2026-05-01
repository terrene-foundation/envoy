# Round 1 — specs/ Comprehensive Review (30 files × 5 rounds collapsed)

**Target:** `/Users/esperie/repos/dev/envoy/specs/` (30 spec files + `_index.md`)
**Authority:** `rules/specs-authority.md` — full-sibling re-derivation (MUST Rule 5b); specs conventions (MUST Rules 1, 3).
**Anchors:** 12 analysis docs in `workspaces/phase-00-alignment/01-analysis/` (treated FROZEN per `_index.md`).
**Exit criterion:** 0 CRIT + 0 HIGH across all five rounds.
**Date:** 2026-04-21
**Verdict:** **NOT CONVERGED** — 7 CRIT, 23 HIGH, 27 MED, 9 LOW (66 findings total).

All findings below are ABSOLUTE (recomputed from specs/ + analysis/), not diff-scoped. Evidence cited by file + line.

---

## Severity distribution

| Round                                | CRIT  | HIGH   | MED    | LOW   |
| ------------------------------------ | ----- | ------ | ------ | ----- |
| R1 Completeness                      | 0     | 6      | 12     | 4     |
| R2 Full-sibling re-derivation        | 3     | 9      | 5      | 1     |
| R3 Orphan detection                  | 3     | 6      | 4      | 1     |
| R4 Threat-model coverage             | 1     | 1      | 3      | 1     |
| R5 Acceptance-criterion traceability | 0     | 1      | 3      | 2     |
| **Total**                            | **7** | **23** | **27** | **9** |

---

## Round 1 — Completeness

- {MED, ALL 27 specs except envelope-model/trust-lineage/ledger, missing mandatory `## Open questions` section per `_index.md` §Spec file conventions — 27/30 non-compliant}
- {MED, ALL 26 specs except envelope-model/trust-lineage/ledger/runtime-abstraction, missing `## Error taxonomy` — 26/30 lacking structured error list}
- {HIGH, threat-model.md, file missing both `## Error taxonomy` AND `## Schema` AND `## Algorithm` — only has Purpose+Provenance+Cross-references; threat matrix itself is NOT reproduced in the spec (§"50 threats × 4 columns" explicitly punted to doc 09 v3 §4); downstream specs cannot reference the mitigation-test matrix from within specs/}
- {HIGH, runtime-abstraction.md, §Conformance vectors N1-N6 contains "N3 Reserved placeholder" + "N6 Sixth pattern placeholder" — empty sections without content, violating `_index.md` MUST Rule 3 "sections complete"}
- {HIGH, runtime-abstraction.md, `## Abstract interface` enumerates 25+ methods in one paragraph but no individual method signature/semantics (compare to envelope-model.md §Algorithms which breaks out each algorithm) — fails MUST Rule 3 "detailed not summary"}
- {HIGH, foundation-ops.md, no `## Schema` for any of the 13 registries (#1-13) despite them being load-bearing named primitives — each registry's data shape is undefined}
- {HIGH, sub-agent-delegation.md §`is_subset_envelope` algorithm, references `verify_dimension_subset`, `composition_rules_are_superset`, `classifier_ensemble_is_superset` — three functions called in algorithm without definition anywhere in specs/}
- {HIGH, envelope-model.md §Error taxonomy, 26 error types listed one-line but zero description of trigger conditions / user action / retry semantics — fails doc 02 §11 error-surface contract}
- {MED, channel-adapters.md, `ChannelAdapter` ABC contract gives method names only — no per-method signature, return types, timeout / rate-limit / failure semantics; downstream channels cannot be implemented from spec}
- {MED, daily-digest.md, no schema for the digest payload structure (content template is listed narratively but no JSON/dataclass)}
- {MED, weekly-posture-review.md, same: only state-machine outline, no rendered content schema}
- {MED, monthly-trust-report.md, same: bullet-list content items without schema; `receipt_hash` cited but not schema'd}
- {MED, boundary-conversation.md, S1-S8 state machine lacks per-state input validation / error-transition rules / resume-from-state semantics; only §Persistence+resume mentions resume}
- {MED, grant-moment.md, M0-M4 state machine but no schema for the dialog payload or timeout-behaviour spec (just "5min default")}
- {MED, trust-vault.md §Encryption, `m=2^17, t=3, p=1` Argon2 params declared but no crypto-suite rationale, no threat-model link for parameter choice}
- {MED, connection-vault.md, per-entry schema is a one-line tuple; no field types / enum constraints / key derivation details}
- {MED, shamir-recovery.md, no schema for `shard_public_commitments` or the distribution-checklist struct; §Card format only describes physical properties}
- {MED, network-security.md, no pinned-cert format, no rotation cadence, no revocation protocol, no failure-mode on pin mismatch}
- {MED, ui-platform.md, §Accessibility is bullets of features; no per-platform API contract / conformance targets}
- {LOW, data-model.md, `## Four physical containers` not numbered to match `_index.md` claim "Trust Vault + Connection Vault + Ledger + shadow segment" — shadow segment in lowercase is a capitalization drift}
- {LOW, classification-policy.md, §`apply_read_classification` mentions `MaskingStrategy (Redact / LastFour / Hash / NullOut)` but no spec defines the strategy enum; cross-SDK contract ambiguous}
- {LOW, foundation-health-heartbeat.md §Payload, "~20 boolean flags" listed as 21 flags — arithmetic drift "~20" → actual 21}
- {LOW, envelope-model.md §Error taxonomy, `PromptSizeBudgetExceededError` listed but `prompt_size_budget` field not in schema section §2.2 — field/error mismatch}

---

## Round 2 — Full-sibling re-derivation (cross-spec drift)

### CRIT — field-shape divergence

- {CRIT, ledger.md vs ledger-merge.md, `lamport_clock` schema: ledger.md line 18 declares `{device_id, local_seq}` (2 fields) but ledger-merge.md line 15 sort key references `lamport_clock.lamport_time` + `lamport_clock.device_id` + `lamport_clock.local_seq` (3 fields) — `lamport_time` is NOT in the ledger.md schema; merge algorithm reads a field that doesn't exist}
- {CRIT, ledger.md vs ledger-merge.md, `intent_id` used in ledger.md §Two-phase signing ("Phase B linked by `intent_id`") and ledger-merge.md §Conflict types ("IntentIdConflict — same intent_id Phase A on different devices") — but `intent_id` is NOT declared in ledger.md §Entry envelope schema; orphan field referenced by two specs}
- {CRIT, envelope-model.md vs authorship-score.md, `metadata.authorship_score` schema in envelope-model.md line 29 declares `{authored_count, imported_count, template_provenance}` — authorship-score.md §Score computation + §Stored vs recomputed only describes `authored_count`, never defines `imported_count` or `template_provenance` semantics; downstream signer drift}

### HIGH — cross-spec terminology drift

- {HIGH, trust-lineage.md vs runtime-abstraction.md vs ledger.md, key-rotation primitive named THREE ways: trust-lineage.md §Key rotation says `KeyRotationRecord`; runtime-abstraction.md §Runtime device key says `RuntimeKeyRotationRecord`; ledger.md §Entry types lists `KeyRotationRecord` — three specs, two names, one primitive}
- {HIGH, runtime-abstraction.md vs ledger.md, runtime-switch record named inconsistently: runtime-abstraction.md line 46 says `RuntimeSwitchRecord` (CamelCase); ledger.md entry types line 32 says `runtime_switch` (snake_case) — cross-spec naming convention violation}
- {HIGH, trust-lineage.md vs sub-agent-delegation.md, envelope-hash field naming: trust-lineage.md DelegationRecord schema uses `effective_envelope_hash`; sub-agent-delegation.md §`is_subset_envelope` algorithm reads `parent.effective_envelope` (no \_hash suffix) — algorithm reads a different field name than the schema declares}
- {HIGH, classification-policy.md vs envelope-model.md, classification enum contradiction: envelope-model.md line 56 declares clearance enum `Public | Internal | Confidential | Restricted | HighlyConfidential`; classification-policy.md line 17 `@classify(email=PII)` example uses `PII` — `PII` is NOT in the canonical 5-value enum; decorator example uses a different enum from the clearance enum, breaking the BET-2 contract parity}
- {HIGH, classification-policy.md vs ledger.md, classification-policy.md §Cross-references says "specs/ledger.md — `format_record_id_for_event` at event emission" but ledger.md does NOT reference `format_record_id_for_event` anywhere — stale downstream consumer reference}
- {HIGH, envelope-model.md vs data-model.md, envelope-model.md §First-time-action gate line 126 says "Cache reset on session boundary (see specs/data-model.md)" but data-model.md has no session-boundary content anywhere — broken cross-ref}
- {HIGH, trust-vault.md vs data-model.md, trust-vault.md §Duress support line 29 says "Shadow segment (§data-model.md §10) encrypted with real-passphrase-only key" — data-model.md has 8 sections, no §10; stale section number}
- {HIGH, envelope-model.md vs authorship-score.md, authorship-score.md §Minimum-impact check line 27 references `standard_action_corpus_v1` as "Foundation-curated" — corpus not in foundation-ops.md's registry list (13 items), not defined elsewhere}
- {HIGH, foundation-health-heartbeat.md cross-ref, line 21 references "specs/ux-rituals L-01 fix" — `specs/ux-rituals.md` does not exist; analysis doc is `01-ux-rituals.md`, no spec with that name; stale cross-ref}
- {HIGH, \_index.md vs filesystem, `_index.md` line 74 claims "all 29 specs at draft v1" but filesystem has 30 spec files (`_index.md` table has 30 rows too) — count drift}

### MED — downstream consumer drift

- {MED, authorship-score.md vs envelope-model.md, envelope-model.md §Schema declares `goal_reconfirmation: {enabled, N_tool_calls, scope, per_posture_overrides}` but no spec (including authorship-score.md or envelope-model.md §Algorithms) describes the algorithm consuming this field — dead configuration surface}
- {MED, sub-agent-delegation.md vs envelope-model.md, envelope-model.md §Schema declares `sub_agent_session_inheritance: "transitive | isolated"` but sub-agent-delegation.md (the domain-owning spec) does not reference the field or describe transitive-vs-isolated semantics}
- {MED, foundation-ops.md vs (multiple), foundation-ops.md line 20 references `specs/public-email-providers.yml` — no `.yml` file exists in `specs/`; dangling external-file reference}
- {MED, authorship-score.md vs foundation-ops.md, authorship-score.md references `envoy-registry:novelty.adversarial-wording:v1` classifier; foundation-ops.md §Classifier registry #6 uses `envoy-registry:*` pattern but specific novelty classifier not enumerated in the 13-item registry list}
- {MED, skill-ingest.md vs foundation-ops.md, skill-ingest.md references `envoy-registry:adversarial-skill-patterns:v1` — foundation-ops.md classifier registry #6 generic pattern covers it but specific classifier not listed in the 13-registry inventory (which IS exhaustive per its enumeration)}

### LOW — prose drift

- {LOW, channel-adapters.md §Phase 01 surfaces, table shows 8 channels; prose §4 says "6 messaging channels" — numerically consistent (CLI+Web+6 msg=8) but inconsistent phrasing between Phase 01 acceptance-metrics.md "6 messaging channels E2E" and channel-adapters.md title "8 Phase-01 surface"}

---

## Round 3 — Orphan detection

### CRIT — named primitive without definition

- {CRIT, envelope-model.md line 124, `SessionObservedState.tool_calls_made` referenced in §First-time-action gate algorithm — `SessionObservedState` dataclass is NOT defined in any spec; algorithm reads from an undefined type (matches Round 2 V-02 residual from round-2-02-envelope-model-reviewer.md)}
- {CRIT, ledger.md entry types §Entry types, `ReasoningCommit` entry listed but no spec (not envelope-model.md §14 / §16, not authorship-score.md) defines its schema, its producer, or its verification — key T-013 defense per doc 02 v3 §16 (per round-2 review) is structurally orphan}
- {CRIT, ledger.md entry types, six orphan entry types with no producer-spec or schema: `RuntimeAttestation`, `FoundationAllowlistOverrideRecord`, `HaltedByRollback`, `ClockSkewEvent`, `session_boundary_crossed`, `system_error`, `PhaseAOrphanResolution` — listed as Ledger types but no spec describes who writes them, when, or with what payload}

### HIGH — orphan reference

- {HIGH, trust-lineage.md §Device-attestation enforcement line 33, `GenesisDeviceTransferRecord` referenced but NOT defined in any schema (not in trust-lineage.md §Schema, not in ledger.md entry-types list) — stolen-Genesis defense primitive is cited without definition}
- {HIGH, trust-vault.md line 32 + trust-lineage.md line 123, `KeyDestructionEvent` referenced but NOT in ledger.md §Entry types list (which enumerates all entry types exhaustively) — key-destruction Ledger record is producer-orphan}
- {HIGH, foundation-ops.md §Infrastructure inventory, registry #10 `envoy-registry:cross-domain-flows:v1` and #11 `envoy-registry:prompt-injection-patterns:v1` declared but no spec consumes them — no "safety-default cross-domain rules" spec exists; no tool-output-sanitizer spec exists; two registries without consumers}
- {HIGH, runtime-abstraction.md line 12, `KailashRuntime` interface enumerates `prompt_assemble`, `tool_output_sanitize`, `classifier_registry_resolve`, `first_time_action_gate`, `grant_moment_surface` — FIVE runtime methods no other spec references; their wiring / invocation sites / return contracts nowhere in specs/}
- {HIGH, channel-adapters.md contract, `ChannelAdapter` ABC has `send_grant_moment` + `send_digest` — weekly-posture-review.md and monthly-trust-report.md both describe ritual delivery ("rendered in every channel") but no `send_posture_review` / `send_monthly_report` adapter method; Phase 03 rituals cannot route through the Phase-01 adapter surface without contract extension}
- {HIGH, specs/ (whole tree), "Shared Household" primitive referenced in a2a-messaging.md, authorship-score.md, threat-model.md, acceptance-metrics.md (5-person Shared Household E2E Phase 03 gate) — but no dedicated `shared-household.md` spec; Shared Household schema, invite flow, principal lifecycle, exit flow, abuse-survivor review scope all missing}

### MED — orphan cross-domain

- {MED, \_index.md table, 3 of 12 analysis docs (01-kailash-rs-deep-audit.md, 02-kailash-py-survey.md, 03-primitive-reconciliation.md) are NOT cited by ANY spec's Provenance; primitive-reconciliation.md in particular carries the parity grid + master GH issue list — downstream spec updates won't trigger its re-derivation}
- {MED, primitive-reconciliation analysis, `PostureStore` / `SQLitePostureStore` / `PostureEvidence` named as functional kailash-py primitives in analysis doc 03 parity grid — no spec in specs/ references or consumes them; weekly-posture-review.md and authorship-score.md posture-ratchet gate both plausibly depend on them but wiring spec missing}
- {MED, primitive-reconciliation analysis, `TieredAuditDispatcher`, `Audit Anchor`, SIEM export — flagged as "new primitive needed" in analysis doc (ISS-06 mint / ISS-07 kailash-py / ISS-08 kailash-rs) — no spec yet describes what Envoy's audit surface is on top of the Ledger; gap}
- {MED, posture-level enum, full enum `{PSEUDO, TOOL, SUPERVISED, DELEGATING, AUTONOMOUS}` used by envelope-model.md / authorship-score.md / sub-agent-delegation.md / enterprise-deployment.md — but NO spec owns the canonical enum definition; the 5-tier posture ladder is a load-bearing primitive referenced everywhere and defined nowhere}

### LOW

- {LOW, foundation-ops.md §Infrastructure inventory #8, registry file `specs/public-email-providers.yml` — no spec owns the data shape / maintenance cadence; file-level reference with zero consuming spec referencing the format}

---

## Round 4 — Threat-model coverage

Per `threat-model.md` §Threats (50 threats catalogued in doc 09 v3 §3). `threat-model.md` itself does NOT reproduce the mitigation-to-primitive matrix (punts to doc 09 v3 §4 — outside specs/). Round 4 therefore checks: for each threat, does at least one spec claim to mitigate it?

### CRIT

- {CRIT, threat-model.md §Threats + all specs, ZERO specs reference `test location` anywhere in specs/ — `rules/testing.md` MUST rule "every documented threat has a test function" cannot be satisfied from specs/ alone; threat-to-test traceability is structurally impossible within spec authority}

### HIGH

- {HIGH, threat-model.md line 17 vs other specs, T-008 "Grant Moment replay" listed in threat inventory — NO spec's Provenance claims mitigation of T-008 (grant-moment.md threats are T-018/T-019/T-093; nonce-partitioning in trust-lineage.md addresses T-102 replay, not T-008 specifically); coverage gap}

### MED — threat-to-primitive gaps

- {MED, threat-model.md line 18, T-010 through T-017 enumerated as "prompt injection + context-window + feedback-loop + goal drift + training-data extraction" — envelope-model.md claims T-010/T-011/T-013/T-015 only; T-012 claimed by classification-policy.md; T-014 (goal drift) and T-016/T-017 (training-data extraction + context-window) NOT claimed by any spec}
- {MED, threat-model.md line 21, T-030 "compromised model provider" — no spec claims mitigation; runtime-abstraction.md addresses T-050a/b/T-060 binary threats but not T-030 (provider-side model compromise). Could be intentional ("out of scope" per threat-model.md line 37-38) but not explicitly declared}
- {MED, threat-model.md line 25, T-061 "runtime binary poisoning" paired with T-060 in threat inventory — distribution.md + runtime-abstraction.md both claim T-060; NO spec claims T-061 separately}
- {MED, threat-model.md line 28, T-090-T-094 DoS variants — T-090 (skill-ingest.md sandbox DoS), T-092 (skill-ingest.md spam), T-093 (budget-tracker.md), T-091 (foundation-ops.md spam flood) — T-094 unmapped to any spec}

### LOW

- {LOW, threat-model.md §Phase gates line 41-46, Phase 00/01/02/03/04 + Ongoing security review items are narrative bullets — no traceability to individual threats; Phase 01 "threat-model test suite green" cannot be verified from specs alone}

---

## Round 5 — Acceptance-criterion traceability

For each phase exit criterion in acceptance-metrics.md, verify the criterion traces to named primitives in other specs + test location.

### HIGH

- {HIGH, acceptance-metrics.md vs enterprise-deployment.md, acceptance-metrics.md Phase 04 line 32 says "2 enterprise pilots"; enterprise-deployment.md line 11 says "Phase 03 deliverable" — spec phase (03) and acceptance phase (04) disagree by one phase; pilot gate unclear which phase owns it}

### MED — criterion traces to concept but not named primitive

- {MED, acceptance-metrics.md Phase 01 line 23, "algorithm-identifier tagged signatures" — envelope-model.md §Schema has `algorithm_identifier` nested struct; trust-lineage.md DelegationRecord has same; but no single spec describes the "tagged signatures" output format or the test fixture to verify byte-identity; acceptance criterion under-specified}
- {MED, acceptance-metrics.md Phase 02 line 26, "cross-runtime conformance vectors (N1-N6 + E1-E7)" — runtime-abstraction.md §Conformance vectors lists N1-N6 with "N3 reserved" + "N6 placeholder"; E1-E7 vector counts given (67/20/15/15/20/orphan-resolve/monotonicity) but corpus files not enumerated; test location missing}
- {MED, acceptance-metrics.md Phase 02 line 26, "CO validator accepts 100 benign + rejects 3 adversarial" — skill-ingest.md §CO validator references `envoy-registry:adversarial-skill-patterns:v1` but 100-benign/3-adversarial corpus not referenced in any spec; test fixture ghost}

### LOW

- {LOW, acceptance-metrics.md §BET-falsification thresholds line 38, "Full catalog in doc 11 v1 §8" — spec punts to analysis doc; per `rules/specs-authority.md` MUST Rule 3, this is the spec's authoritative content being outsourced}
- {LOW, acceptance-metrics.md §Kill criteria line 41-46, kill-criteria operationalization — "3 BETs disconfirmed" etc. — BETs enumerated by ID (BET-1 through BET-12) but no spec maps BET-N → measurement substrate → disconfirmation threshold in one place; BET-5 never appears in any spec (BET-1, -2, -3, -4, -6, -7, -8, -9, -10, -11, -12 each appear at least once; BET-5 absent — undefined, withdrawn, or drift)}

---

## Cross-round patterns (failure modes)

1. **Ledger entry type inventory is the #1 orphan source.** `ledger.md` line 32 enumerates 25+ entry types; at least 7 have no producer-spec (R3-CRIT bundle). Every future schema mutation on these types has no place to land.

2. **Error taxonomy + Open Questions conventions are near-universally ignored.** 27/30 specs missing `## Open questions`; 26/30 missing `## Error taxonomy`. `_index.md` conventions are aspirational, not enforced.

3. **Cross-spec `§N source`-style section-number references drift silently.** trust-vault.md §10, foundation-health-heartbeat.md §ux-rituals, envelope-model.md "see data-model.md for session boundary" — three broken cross-refs; none of the target specs have the claimed sections.

4. **Anchor analysis docs 01-kailash-rs-deep-audit / 02-kailash-py-survey / 03-primitive-reconciliation never feed specs.** The parity grid (doc 03) carries `PostureStore`, `TieredAuditDispatcher`, `Audit Anchor` primitives that specs should either own or explicitly punt — currently neither.

5. **"Shared Household" is a full domain with four-spec span and no owning spec file.** 5-person Shared Household is a Phase 03 gate in acceptance-metrics.md. Missing `shared-household.md` is the single biggest structural gap.

6. **Posture ladder {PSEUDO, TOOL, SUPERVISED, DELEGATING, AUTONOMOUS} is fully load-bearing and undefined.** Five specs consume it; zero specs own it. Canonical enum plus per-tier semantics + transition contract need a spec.

---

## Recommended disposition (not prescriptive)

The 7 CRIT + 23 HIGH findings concentrate along three axes:

- **Ledger schema completeness** — add missing fields (`lamport_time`, `intent_id`) to schema; land producer-specs for 7 orphan entry types OR delete from entry-types list.
- **Missing domain specs** — `posture-ladder.md`, `shared-household.md`, `tool-output-sanitization.md`, `cross-domain-flows.md`, `session-state.md` (owning `SessionObservedState` + session-boundary semantics + `ReasoningCommit`).
- **Cross-spec ref hygiene** — sweep every `§N source` / `specs/X.md §N` reference for validity; consolidate all orphan primitive names into a single "needs-producer-spec" list.

Per `rules/specs-authority.md` MUST Rule 5b, any spec edit made in response must trigger full-sibling re-derivation against all 30 spec files.

**Exit criterion NOT met: 7 CRIT + 23 HIGH > 0/0 target.**
