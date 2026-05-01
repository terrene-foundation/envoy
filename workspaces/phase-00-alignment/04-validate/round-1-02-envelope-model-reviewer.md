# Round 1 Review — doc 02 Envelope Model (reviewer)

**Target:** `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/02-envelope-model.md`
**Anchors (frozen):** doc 00 v3, doc 09 v3
**Date:** 2026-04-21
**Reviewer role:** quality / cross-reference / schema-completeness / error-taxonomy / gap-vs-threat-model

Summary verdict: **Issues found — 22 findings.** Doc 02 is structurally sound and the canonical JSON is plausible, BUT there are three classes of gap that block `/redteam` convergence: (a) mitigations doc 09 v3 explicitly names `specs/envelope-model.md` as primitive but doc 02 never defines them (system-prompt pinning, prompt-size budget, per-turn prompt reset, envelope-re-read checkpoint, turn-N goal-reconfirmation, tool-output sanitization, first-time-action gate, velocity-limit session-vs-month scope separation, content-trust-level enum alignment); (b) `intersect_envelopes()` algorithm is underspecified on load-bearing edge cases (commutativity, associativity, empty-dimension handling, versioning-mismatch intersection, schema-version mismatch, composition-rule intersection when one side is absent, subset-proof computation); (c) error taxonomy is incomplete against the actual threat-model surface (no `EnvelopeRollbackError`, no `HaltedByRollbackError`, no `CapabilityDeadCompletionError`, no `TenantRequiredError`-equivalent for Shared Household cross-principal composition, no `ClockSkewBlockError`).

---

## Summary Table

| #    | Severity | Area                                  | Issue (one-liner)                                                                                                                                                                                                                                                                 |
| ---- | -------- | ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F-01 | CRITICAL | Cross-ref gap                         | T-015 system-prompt pinning + prompt-size budget + envelope-re-read checkpoint primitives named in doc 09 v3 but absent from doc 02                                                                                                                                               |
| F-02 | CRITICAL | Cross-ref gap                         | T-014 per-turn prompt reset + structured framing (`<trusted_context>` / `<untrusted_context>`) named in doc 09 v3 but absent from doc 02                                                                                                                                          |
| F-03 | CRITICAL | Cross-ref gap                         | T-013 ReasoningCommit + turn-N goal-reconfirmation named in doc 09 v3 `specs/envelope-model.md` but not defined in doc 02                                                                                                                                                         |
| F-04 | CRITICAL | Schema                                | `SessionObservedState` is load-bearing for composition rules (§5.3) but schema, mutation semantics, and LLM-consumption wrapping are undefined; cross-referenced to doc 04 but doc 04 has not frozen                                                                              |
| F-05 | CRITICAL | Semantics                             | `intersect_envelopes` edge cases (empty envelopes, missing dimension, schema-version mismatch, composition-rules absent on one side, `SessionObservedState` composition) unspecified                                                                                              |
| F-06 | HIGH     | Cross-ref gap                         | T-011 tool-output sanitization named in doc 09 v3 mitigation matrix at `specs/envelope-model.md` but doc 02 does not mention tool-output sanitization surface                                                                                                                     |
| F-07 | HIGH     | Cross-ref gap                         | T-010 first-time-action gate named in doc 09 v3 at `specs/envelope-model.md` but doc 02 does not define "first-time-action" as an envelope concept                                                                                                                                |
| F-08 | HIGH     | Canonical-name drift                  | §3 heading "Data Access" uses "classified field" / "highly_classified" but `rules/terrene-naming.md` and PACT canonically uses exact clearance enum; unclear whether `highly_classified` matches PACT's canonical level names                                                     |
| F-09 | HIGH     | Sub-agent                             | T-105 subset-proof computation belongs in doc 02 (it's an envelope operation — sub ⊆ parent per dimension) but §5 only mentions it in passing; the explicit subset-proof format for all 5 dimensions is in doc 09 v3 but not mirrored as an envelope-level primitive              |
| F-10 | HIGH     | Versioning                            | §6.1 mid-flight tightening cascade specifies the three branches but does NOT specify who signs the SUSPENDED/HALTED record (the runtime? the user? the agent?); Phase B signer identity is underspecified                                                                         |
| F-11 | HIGH     | Error taxonomy                        | Error table missing: `HaltedByRollbackError`, `ClockSkewBlockError` (T-001), `TenantRequiredError`-equivalent for cross-principal composition (T-106), `SemanticCheckBudgetExceededError` vs `LatencyBudgetExceededError` (overlap unclear), `EnvelopeRollbackPendingGrantsError` |
| F-12 | HIGH     | Latency budget                        | §2.2 `latency_budget_ms` has `structural: 5` but §7 table shows some structural classes at <1ms (Temporal comparison); schema cannot express per-class budgets; structural + arithmetic + comparison conflated in `structural: 5` field                                           |
| F-13 | HIGH     | T-093 Budget                          | §3.1 "Velocity-raise ratchet" wording is correct but the canonical JSON in §2.2 does NOT show a `session_scope` vs `month_scope` distinction (per T-093 mitigation: "envelope separates 'this session's budget' from 'this month's budget'")                                      |
| F-14 | HIGH     | T-024 Enterprise                      | §8.3 enterprise-mode `N=5` is specified but `enterprise_deployment_record_hash` in §2.2 metadata is not tied to verification semantics — doc 02 does not describe what Envoy runtime does with this hash (cross-ref only)                                                         |
| F-15 | MEDIUM   | Classifier ensemble                   | §3.4.1 mandates "at least 2 classifiers; disagreement fails CLOSED" but §2.2 sample shows only 3 classifiers with no explicit disagreement-detection policy or quorum threshold in the schema                                                                                     |
| F-16 | MEDIUM   | Authorship Score                      | §8.1 "minimum_impact_passed" mechanics reference "standard action corpus" but §13 open Q#2 admits the corpus is unspecified; minimum-impact is load-bearing for Test-5 posture gate — cannot ship Phase 01                                                                        |
| F-17 | MEDIUM   | Composition DSL                       | §5.3 DSL examples use `session.observed_data.has_classification(...)` but the DSL grammar is never specified — what operators, what types, what halting guarantees                                                                                                                |
| F-18 | MEDIUM   | Canonical form                        | §2.2 "field-ordering rule" says fields are enumerated "in the order they appear in this schema document" — this is fragile; should specify sorted keys OR explicit ordering list in the spec; doc-authored ordering is not machine-enforceable                                    |
| F-19 | MEDIUM   | Linter                                | §9.2 linter warnings include over-broad domain allowlist (T-021) but do NOT include T-023 novelty-classifier-evasion warnings (user authored 3 near-duplicates but each passed Jaccard individually — collectively meaningless)                                                   |
| F-20 | LOW      | Cross-SDK                             | §2.2 canonical-form byte-identity is a BET-6 requirement but §5.1 only mentions it as a "pending" runner (`kailash-py#605`); the canonical-form specification is NOT in doc 02 (would need `canonical_form()` algorithm spec)                                                     |
| F-21 | LOW      | Posture                               | §3.2 ties `sub_agent_spawn_limit.max_depth` to posture levels but the 5-posture enum appears nowhere in doc 02's schema — implied via doc 00 glossary but not locally grounded                                                                                                    |
| F-22 | LOW      | Structural/semantic partition honesty | §7 table claims "Semantic (cached): <50ms" and "Semantic (uncached): <500ms" but the COLD-start case where cache is empty AND the LLM provider is cold (local Ollama not loaded) is not budgeted; first-call latency can be 5–10 seconds                                          |

---

## Detail

### F-01 — CRITICAL — T-015 primitives named by doc 09 v3 absent from doc 02

**Issue:** doc 09 v3 §3.2 T-015 ("Context-window exhaustion attack") lists three MUST-Phase-01 mitigations with primitive location `specs/envelope-model.md` AND `specs/runtime-abstraction.md`:

1. **Envelope pinning in system prompt** — "envelope is in the system prompt; not subject to context-window rotation"
2. **Prompt-size budget** — "untrusted content that exceeds 50% of the context window is summarized"
3. **Envelope-re-read checkpoint** — "every tool-call re-verifies against the canonical envelope (from Trust Vault, not from context)"

Doc 02 does not define any of these. There is no `system_prompt_pinning` field in the schema, no `prompt_size_budget_tokens` field, no envelope-re-read-checkpoint section, no mention of how the envelope reaches the LLM as pinned system content.

**Location:** doc 02 §2.2 (schema), §3.4 / §3.5 (semantic checks), §7 (hot-path shape).

**Fix:**

- Add `metadata.prompt_sizing` subtree to canonical JSON:

  ```json
  "prompt_sizing": {
    "system_prompt_pin_token_budget": 2048,
    "untrusted_context_max_fraction": 0.5,
    "summarization_policy": "summarize_via_separate_llm_call",
    "envelope_reread_checkpoint": "every_tool_call"
  }
  ```

- Add §3.6 (new): "System-prompt pinning + untrusted-context framing" covering the `<trusted_context>` / `<untrusted_context>` tags from doc 09 T-014/T-015 and the runtime's obligation to wrap entries by `content_trust_level`.
- Add to §7 hot-path shape: step 0 "Envelope re-read from Trust Vault (NOT from context) — O(1) hash-set pointer fetch".

---

### F-02 — CRITICAL — T-014 per-turn prompt reset absent from doc 02

**Issue:** doc 09 v3 T-014 MUST-Phase-01 mitigation:

> "Per-turn prompt reset for untrusted-context turns (MUST, Phase 01): turns that ingest `derived-external` content (T-012 content-trust levels) reset the agent's system prompt fragments that describe envelope + guidelines. Agent re-reads canonical envelope on every turn, not accumulated."

And:

> "Context-window structured framing (MUST, Phase 01): LLM context is structured as `<trusted_context>` (envelope, user-authored) + `<untrusted_context>` (derived-external)."

doc 09 matrix row points to `specs/envelope-model.md` as the primary spec. Doc 02 contains zero occurrences of "per-turn", "prompt reset", "trusted_context", or "untrusted_context".

**Location:** doc 02 — missing section.

**Fix:** Add new §3.7 "Context-framing contract" defining:

- The `<trusted_context>` / `<untrusted_context>` wrapper tags
- The per-turn reset policy (triggered when any entry consumed this turn has `content_trust_level` ∈ {tool-output, channel-message, derived-external})
- Mapping from `content_trust_level` (doc 04) to wrapper behavior (doc 09 T-012 mitigation)
- The special `llm-authored` wrapping case per R2-C1

---

### F-03 — CRITICAL — T-013 ReasoningCommit + turn-N goal-reconfirmation absent

**Issue:** doc 09 v3 T-013 MUST Phase-01 cites `specs/envelope-model.md` §composition-aware-constraints AND `specs/ledger.md` §reasoning-commit. Doc 02 §5.3 defines composition-aware constraints (good), BUT:

1. There is no mention of `ReasoningCommit` as a Ledger entry type that composition-rule evaluation consumes.
2. "Turn-N goal-reconfirmation" is referenced in passing at line 446 ("Goal drift (T-016) — turn-N goal-reconfirmation can fire based on composition state") but never defined. doc 09 specifies N=5 default; doc 02 makes no commitment.
3. The composition-rule evaluator's contract with `ReasoningCommit` (does it read `considered_alternatives`? `composition_context`?) is unspecified.

**Location:** doc 02 §5.3.

**Fix:**

- In §5.3, add explicit list of Ledger entry types the composition evaluator reads: `{envelope_edit, tool_call, ReasoningCommit, Message_sent}`.
- Add §5.4 "Turn-N goal-reconfirmation": specify `composition_rules` may include `{rule_id, kind: goal_reconfirmation, every_n_turns: 5, prompt_template: "..."}`. Clarify N=5 is default; envelope can override per the authorship conversation.
- Cross-link to doc 04 `ReasoningCommit` schema.

---

### F-04 — CRITICAL — `SessionObservedState` schema + lifecycle undefined in doc 02, deferred to doc 04 which has not landed

**Issue:** §5.3 line 440: "Session state tracked in `SessionObservedState` (defined in doc 04 Ledger schema). Reset on new session boundary." Also referenced at §12 and §13 Q#8. But:

1. Doc 04 has not frozen — `SessionObservedState` schema is not a stable reference.
2. The mutation semantics ("reset on new session boundary") is stated but "session boundary" is undefined — is it a CLI exit? Channel idle? Time-based? User-explicit?
3. Whether `SessionObservedState` is an envelope field (part of `EffectiveEnvelopeSnapshot`), a Ledger field (append-only), or a runtime mutable is unclear.
4. Sub-agent inheritance of `SessionObservedState` (§13 Q#8) is explicitly open — this is load-bearing for T-106 cross-principal composition. Cannot defer.
5. The LLM-facing wrapping of `SessionObservedState` (is it consumed as `<trusted_context>` or `<untrusted_context>`?) is unspecified.

**Location:** doc 02 §5.3.

**Fix:**

- In doc 02 §5.3, inline the `SessionObservedState` shape that composition rules need, even if it is formally owned by doc 04:

  ```text
  SessionObservedState {
    session_id: UUID,
    session_started_at: timestamp,
    observed_data_classifications: Set[ClassificationLabel],
    tool_calls_made: List[{tool_name, timestamp, capability_ref}],
    recipients_messaged: Set[Recipient],
    composition_flags: Dict[rule_id, bool],
  }
  ```

- Define "session boundary" as either (a) explicit user `envoy session new`, (b) >30min idle on any channel, (c) channel-boundary crossing (new Telegram chat vs old) — pick one and ground it.
- Resolve §13 Q#8: specify transitive inheritance with `compose_state: "inherit" | "isolated"` field on the sub-agent envelope.
- Specify the wrapping: `SessionObservedState` surfaces in context as `<trusted_context source=envoy_runtime>` because it is Envoy-computed, not external.

---

### F-05 — CRITICAL — `intersect_envelopes()` edge cases unspecified

**Issue:** §5.1 specifies per-dimension intersection rules BUT omits multiple load-bearing cases that will surface in production:

| Edge case                                                                                               | Current doc 02 behavior                                                                                                                               | Required                                                                                                                                 |
| ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Empty envelope (no dimensions) ∩ populated envelope                                                     | unspecified                                                                                                                                           | define as "deny-all" or "identity"                                                                                                       |
| Missing dimension key in A but present in B                                                             | §9.1 says "missing dimension key not OK" at validate time, but intersect consumers (sub-agent derivation) cannot assume validation ran                | raise `EnvelopeValidationError` at intersect-entry                                                                                       |
| Schema-version mismatch (A is `envelope/1.0`, B is `envelope/2.0`)                                      | §6.3 says "migration is a one-time code migration" but intersect between pre-migration and post-migration envelopes at the migration boundary is real | raise `SchemaVersionMismatchError` and fail closed                                                                                       |
| `composition_rules` absent on one side                                                                  | unspecified; "UNION" implies empty UNION works, but semantic_rules UNION when one side empty is ambiguous (is empty "no rules" or "unknown")          | document explicitly: absent = empty list for all UNIONed collections                                                                     |
| Commutativity: `intersect(A, B) == intersect(B, A)` byte-identical?                                     | unspecified — required for BET-6 contract parity                                                                                                      | MUST hold; state explicitly                                                                                                              |
| Associativity: `intersect(intersect(A,B), C) == intersect(A, intersect(B,C))`                           | unspecified — required for 3-way sub-agent inheritance chain                                                                                          | MUST hold; state explicitly                                                                                                              |
| Classifier-ensemble UNION when ensembles disagree on provider (A: local_ollama, B: provider.moderation) | unspecified; "concatenated" per §5.1 but double-counts weights                                                                                        | define: ensembles concatenate, weights NORMALIZED post-concat                                                                            |
| `algorithm_identifier` mismatch                                                                         | §5.1 says raise `AlgorithmMismatchError` (good) but the `AlgorithmMismatchError` is not in the §11 error taxonomy table                               | add to §11                                                                                                                               |
| Identity envelope (used for sub-agent when no parent snapshot): what is its shape?                      | §5.2 references `identity_envelope` but doesn't define                                                                                                | define: all allowlists = ALL, all denylists = ∅, all ceilings = ∞, all windows = 24/7 — this is the "permit everything" identity element |

**Location:** doc 02 §5.1, §5.2.

**Fix:** Rewrite §5.1 as a formal algorithm with edge cases enumerated; add an `intersect_envelopes` contract subsection with Commutativity + Associativity + IdentityElement explicit statements; add the identity-envelope definition to §5.2.

---

### F-06 — HIGH — T-011 tool-output sanitization surface missing from doc 02

**Issue:** doc 09 v3 mitigation matrix row T-011: primary mitigation "Tool-output sanitization + cross-domain-flow gate", primitive location `specs/skill-ingest.md` **AND** `specs/envelope-model.md`. Doc 02 contains zero occurrences of "tool-output" or "sanitization" in the context of tool outputs.

**Location:** doc 02 — missing.

**Fix:**

- Add §3.4.2 "Tool-output sanitization" under Data Access: specifies that tool outputs carrying `derived-external` content go through the classifier ensemble before being surfaced to the agent as context, AND carry the `content_trust_level: derived-external` tag on Ledger persistence.
- Cross-domain-flow gate: when a tool output with classification X is about to flow into a tool input of a different domain (e.g. `read_tax_doc` output flowing into `send_email` body), composition-rule evaluation MUST fire.

---

### F-07 — HIGH — T-010 "first-time-action gate" surface missing

**Issue:** doc 09 v3 T-010 mitigation: "Envelope + first-time-action gate", primitive `specs/envelope-model.md`. Doc 02 does not define "first-time-action" as an envelope concept.

**Location:** doc 02 — missing.

**Fix:** Add §3.2 subsection under Operational "First-time-action semantics": any tool-call not yet appearing in `SessionObservedState.tool_calls_made` (or within configurable N-day window from Ledger history) triggers automatic Grant Moment regardless of envelope allow-status. Novelty threshold is per-tool; defaults published in a §3.2 sub-table.

---

### F-08 — HIGH — Classification clearance naming: canonical drift

**Issue:** §3.4 declares the clearance enum as `public, internal, confidential, restricted, highly_classified`. `rules/terrene-naming.md` mandates "Constraint dimensions: **Financial, Operational, Temporal, Data Access, Communication** (these exact five names — no synonyms, no reordering)" but does NOT constrain the clearance level enum within the Data Access dimension. PACT's canonical enum (per kailash-rs `ClassificationLevel`) is typically: `Public, Internal, Confidential, Restricted, HighlyConfidential` (NOT `highly_classified`).

Cross-ref: `rules/dataflow-classification.md` and `rules/security.md` Rust section use `ClassificationLevel::Public / Confidential / HighlyConfidential` — doc 02's `highly_classified` is a drift.

**Location:** doc 02 §3.4, first bullet.

**Fix:** Rename `highly_classified` to `highly_confidential` (or `HighlyConfidential` in code) to match PACT canonical. Add cross-ref to PACT clearance spec at `terrene-foundation/mint` in the sentence.

---

### F-09 — HIGH — Sub-agent subset-proof computation belongs in doc 02

**Issue:** doc 09 v3 T-105 MUST-Phase-03 specifies the subset-proof format per-dimension:

- Financial: sub-budget ≤ parent-budget; sub-velocity ≤ parent-velocity.
- Operational: sub-tool-allowlist ⊆ parent-tool-allowlist.
- Temporal: sub-time-windows ⊆ parent-time-windows.
- Data Access: sub-classification-clearance ≤ parent-clearance; sub-allowlist ⊆ parent-allowlist.
- Communication: sub-recipient-allowlist ⊆ parent-recipient-allowlist; sub-content-constraints ⊇ parent-content-constraints.

This is an envelope operation (subset verification over the 5 dimensions) — it belongs as a first-class algorithm in doc 02 alongside `intersect_envelopes`. Doc 02 mentions it at §5.1 ("Computing sub-agent's effective envelope = intersection of parent's envelope + sub-agent's declared envelope + sub-agent derivation proof (doc 09 T-105)") without specifying the subset-proof structure.

Additionally: R2-H2 says Envoy runtime re-verifies INDEPENDENT of parent claim. That re-verification is an `is_subset_envelope(candidate, parent)` function call — that function must be defined in doc 02.

**Location:** doc 02 §5, add new §5.4.

**Fix:**

- Add `is_subset_envelope(candidate: EnvelopeConfig, parent: EnvelopeConfig) -> SubsetProof` as a first-class doc 02 function; specify return type as `SubsetProof { is_subset: bool, per_dimension_witnesses: {Financial: ..., Operational: ..., Temporal: ..., DataAccess: ..., Communication: ...}, failing_dimension: Optional[DimensionName] }`.
- Add `SubsetProofFailedError` (already in §11) to raise when `is_subset = false`.
- Note that `intersect(A, B) == B` when B ⊆ A — this gives a sanity equivalence that the test suite can exploit.

---

### F-10 — HIGH — Mid-flight tightening SUSPENDED/HALTED record signer identity

**Issue:** §6.1 mid-flight tightening cascade specifies three outcome branches (proceed / SUSPENDED / HALTED) but does not specify who signs the Ledger entry that records the SUSPENDED or HALTED outcome. Per doc 00 §8 Test-2, Phase B signature is on the outcome; but if the action HALTED before execution (branch 3), there is no outcome — only a synthetic "halted" record. Who signs?

Options: (a) the runtime (under what key?), (b) the user (requires interrupt), (c) the system (using a distinguished system-authored key).

**Location:** doc 02 §6.1 branch 3 (HALTED case).

**Fix:** Specify: HALTED records are signed by the **Envoy runtime's own device-key** (from `SubAgentDerivation` T-105 R2-H2 naming — the same key that does independent subset-proof re-verification) with `content_trust_level: system`. Phase B record for branch 2 (SUSPENDED) is signed by the runtime; the subsequent fresh-authorization Grant Moment is signed by the user under the new envelope version. Cross-ref doc 04 §content-trust-level enum.

---

### F-11 — HIGH — Error taxonomy incomplete

**Issue:** §11 table is incomplete against the threat-model mitigations doc 02 inherits:

| Missing error                                      | Mitigation that surfaces it                   | Source                    |
| -------------------------------------------------- | --------------------------------------------- | ------------------------- |
| `HaltedByRollbackError`                            | §6.1 branch 3 HALTED                          | doc 09 T-104 R2-H3        |
| `ClockSkewBlockError`                              | §3.3 Monotonic-time invariant + remote anchor | doc 09 T-001              |
| `CrossPrincipalConsentRequiredError`               | Shared Household dual-signed Grant Moment     | doc 09 T-106              |
| `PromptSizeBudgetExceededError`                    | T-015 prompt-size budget enforcement          | doc 09 T-015              |
| `EnvelopeRollbackPendingGrantsError`               | §6.1 rollback with pending grants             | doc 09 T-104              |
| `SchemaVersionMismatchError`                       | §6.3 schema version                           | F-05 above                |
| `FirstTimeActionError` (or NewActionGrantRequired) | §3.2 first-time-action gate                   | doc 09 T-010 (F-07 above) |
| `CompositionStateCorruptedError`                   | `SessionObservedState` inheritance            | F-04 above                |

Also: `LatencyBudgetExceededError` overlaps with `SemanticCheckFailedError` — both can fire on a slow classifier. Clarify the precedence.

**Location:** doc 02 §11.

**Fix:** Expand §11 with the above errors, specify precedence (latency > semantic), and add cross-ref column to the relevant threat ID.

---

### F-12 — HIGH — Latency-budget schema field conflates structural vs arithmetic vs comparison

**Issue:** §2.2 canonical JSON has:

```json
"latency_budget_ms": {
  "structural": 5,
  "semantic_cached": 50,
  "semantic_uncached": 500
}
```

But §7 table distinguishes four classes: Structural (hash-set) <5ms, Arithmetic <5ms, Comparison <1ms, Semantic cached <50ms, Semantic uncached <500ms. The schema cannot represent the arithmetic / comparison distinction; `"structural": 5` flattens them.

**Location:** doc 02 §2.2, §7.

**Fix:** Expand the schema to match §7:

```json
"latency_budget_ms": {
  "structural_hashset": 5,
  "arithmetic": 5,
  "comparison": 1,
  "semantic_cached": 50,
  "semantic_uncached": 500,
  "semantic_cold_start": 10000
}
```

(Cold-start budget addresses F-22 below.)

---

### F-13 — HIGH — T-093 session-vs-month budget scope not in canonical JSON

**Issue:** doc 09 v3 T-093 MUST-Phase-01 mitigation: "Session budget scope (MUST, Phase 01): envelope separates 'this session's budget' from 'this month's budget'; a compromised session drains session budget but not month budget." But §2.2 Financial dimension has only month/day/hour/per-call ceilings — NO `per_session_ceiling_microdollars`. §3.1 also does not mention session scope.

**Location:** doc 02 §2.2, §3.1.

**Fix:**

- Add `per_session_ceiling_microdollars` field to Financial in §2.2 canonical JSON.
- Add to §3.1 Fields list: "`per_session_ceiling_microdollars` — per-session hard cap; exceeding halts the session."
- Cross-ref doc 09 T-093.

---

### F-14 — HIGH — Enterprise-mode attestation verification semantics absent

**Issue:** §2.2 metadata carries:

```json
"enterprise_mode": {
  "is_enterprise": false,
  "org_genesis_hash": null,
  "enterprise_deployment_record_hash": null
}
```

Per doc 09 v3 T-024 R2-H5: enterprise-mode is a cryptographic attestation verified against the organization's Trust Lineage root at install time. Doc 02 does not specify:

1. What runtime code verifies `enterprise_deployment_record_hash` and when.
2. What happens if verification fails — `EnterpriseDeploymentRecordInvalidError` is in §11 but `§8.3` does not cross-ref.
3. Whether `is_enterprise` can be spoofed (per R2-H5 it MUST NOT — so `is_enterprise: true` without a matching verified `enterprise_deployment_record_hash` must raise).
4. The flip-off protocol requiring affected employee consent — doc 02 does not mention employee consent on flip-off.

**Location:** doc 02 §2.2, §8.3, §11.

**Fix:**

- Add §8.4 "Enterprise-mode verification": specifies runtime MUST verify `enterprise_deployment_record_hash` against org Genesis chain before applying §8.3 posture-gate rules; MUST raise `EnterpriseDeploymentRecordInvalidError` on mismatch; MUST require employee-signed consent record to flip `is_enterprise: true → false`.
- Link §11 `EnterpriseDeploymentRecordInvalidError` to §8.4.

---

### F-15 — MEDIUM — Classifier ensemble disagreement policy not in schema

**Issue:** §3.4.1 mandates "ensemble of at least 2 classifiers; disagreement fails CLOSED" but §2.2 sample:

```json
"data_access_classifier_ensemble": [
  {"classifier": "regex.tax_info", "weight": 0.3},
  {"classifier": "llm.data_access_v2", "weight": 0.5, "provider": "local_ollama:llama-3-70b"},
  {"classifier": "provider.moderation", "weight": 0.2}
]
```

does not express:

- The "fails CLOSED on disagreement" threshold (what delta between min and max classifier scores triggers CLOSED?).
- The quorum required (must all 3 agree? 2 of 3?).
- The behavior when a classifier times out (use cached score? skip? fail CLOSED?).

**Location:** doc 02 §2.2, §3.4.1.

**Fix:** Add schema fields:

```json
"data_access_classifier_ensemble": {
  "classifiers": [...],
  "quorum": "weighted_majority" | "all_agree" | "at_least_2",
  "disagreement_threshold": 0.3,
  "disagreement_action": "fail_closed" | "escalate_grant_moment",
  "timeout_policy": "fail_closed" | "use_remaining" | "cached_fallback"
}
```

---

### F-16 — MEDIUM — Authorship Score minimum-impact corpus unspecified

**Issue:** §8.2 "minimum-impact check": "Check is performed by dry-running the constraint against a standard action corpus AND against the user's recent Ledger history." §13 Q#2 admits corpus identity is open. But minimum-impact is load-bearing for §8.3 posture-ratchet gate (Test-5 per doc 00) — if corpus cannot be defined at Phase 01, the gate cannot be enforced at Phase 01, and §4.1 item 9 of doc 00 v3 (Phase 01 gate) chains to the Authorship Score gate existing at Phase 01.

**Location:** doc 02 §8.2.

**Fix:** Pick a concrete Phase 01 corpus: "Phase 01 ships with a Foundation-curated seed corpus of 500 actions (10 per constraint dimension × 50 template scenarios) at `specs/authorship-score-corpus.md`; Ledger history is included when ≥30 entries exist; below 30 entries, corpus-only dry-run is authoritative." Cross-ref open Q#2 as resolved.

---

### F-17 — MEDIUM — Composition-rule DSL grammar unspecified

**Issue:** §5.3 example shows `session.observed_data.has_classification('tax_info')` and `send_email.body_contains(observed_data)` but §13 Q#3 correctly flags halting-problem concerns. There is no BNF / EBNF / AST shape.

**Location:** doc 02 §5.3.

**Fix:** Specify the DSL as a restricted expression language:

- Allowed operators: `==`, `!=`, `IN`, `NOT IN`, `AND`, `OR`, `NOT`, `MATCHES` (regex with bounded backtracking), `.has_classification()`, `.body_contains()`, `.count()`.
- Forbidden: loops, recursion, lambda, user-defined functions.
- Evaluation: bounded in time (hard timeout 50ms per rule — matches semantic_cached budget), bounded in recursion (no cycles allowed).
- Grounds halting-problem worry and makes the DSL auditable.

---

### F-18 — MEDIUM — Field-ordering rule is fragile; canonical-form algorithm absent

**Issue:** §2.2 "field-ordering rule: within each object, fields are enumerated in the order they appear in this schema document." This is:

1. Not machine-enforceable (document ordering drifts).
2. Not portable (editors re-order fields).
3. Unclear for nested arrays (how are array elements ordered? by `constraint_id`?).
4. No canonical-form algorithm spec — BET-6 byte-identity requires an explicit algorithm.

**Location:** doc 02 §2.2.

**Fix:**

- Specify canonical-form algorithm inline (short form; full at `specs/envelope-canonical-form.md`): "keys sorted lexicographically; arrays preserve author order BUT if `constraint_id` present, sorted by `constraint_id` ascending; strings UTF-8 NFC-normalized; integers in decimal; booleans `true`/`false` literals; no trailing whitespace; no BOM; LF not CRLF".
- Cross-ref pending canonical-form runner `kailash-py#605` + sibling `kailash-rs#520` (or whichever the parity runner issue is).

---

### F-19 — MEDIUM — Linter does not cover T-023 cross-constraint gaming

**Issue:** §9.2 linter warnings include T-021 (over-broad allowlists) and T-023 single-constraint novelty (§8.2 minimum-impact). But it does NOT warn on **cross-constraint gaming**: 3 authored constraints each novel per-Jaccard but collectively meaningless (e.g., denying 3 nonexistent domains).

**Location:** doc 02 §9.2.

**Fix:** Add linter warning: "aggregate constraint set's behavioral delta is below threshold — you added N constraints but the combined effect does not narrow agent behavior against the standard corpus more than X%". Ties to F-16 corpus choice.

---

### F-20 — LOW — Canonical-form specification deferred to kailash-py#605 but BET-6 requires it by Phase 02

**Issue:** §5.1 says: "Reference implementation: kailash-py `src/kailash/trust/pact/envelopes.py::intersect_envelopes`. Rust binding pending `esperie-enterprise/kailash-rs#503`. Contract-parity test per PACT N4/N5 vectors (pending `terrene-foundation/kailash-py#605` runner)."

Doc 00 §5.6 (BET-6) and §10 dependency graph specify the Python runner is a Phase 01 exit OR Phase 02 entry criterion. Doc 02 does not cross-ref this nor state its dependency posture.

**Location:** doc 02 §5.1, §12.

**Fix:** Add explicit Phase-gate paragraph to §12 cross-references: "Phase-gating: `intersect_envelopes` byte-identity (canonical-form algorithm of §2.2 combined with the Rust binding at `kailash-rs#503`) is Phase 01 exit OR Phase 02 entry per doc 00 v3 §5.6. Until closed, Envoy operates on kailash-py only and BET-6 is non-falsifiable."

---

### F-21 — LOW — Posture enum not locally grounded

**Issue:** §3.2 references `PSEUDO / TOOL / SUPERVISED / DELEGATING / AUTONOMOUS` but doc 02 has no schema for `TrustPosture`, no enum definition, no citation to where the enum lives (EATP? doc 01?). A reader starting at doc 02 cannot resolve these names without cross-doc jumps.

**Location:** doc 02 §3.2.

**Fix:** Add one-sentence reference at first usage: "The five postures are canonically specified in EATP Decision 007 + doc 00 §11 glossary: `PSEUDO < TOOL < SUPERVISED < DELEGATING < AUTONOMOUS` ordered by increasing autonomy."

---

### F-22 — LOW — Cold-start semantic latency budget unspecified

**Issue:** §7 table and §2.2 schema specify `semantic_cached: 50ms` and `semantic_uncached: 500ms`. But local-Ollama cold-start (model not loaded) is 5–10s (F-12 above). First-call after boot is uncached AND cold. Users will see 10-second hangs.

**Location:** doc 02 §7, §2.2.

**Fix:** Add `semantic_cold_start: 10000ms` budget (as per F-12 fix). In §3.4.1, specify cold-start fallback: "if semantic check's first-call latency exceeds `semantic_cold_start`, the check degrades to a Grant Moment with explicit rationale 'classifier not yet loaded — approving now will pre-warm for this session.'" Honest framing.

---

## Notes on items that passed

- **License references:** none in doc 02 (doc is not a code file); no CC BY 4.0 / Apache 2.0 license drift. Clean.
- **PACT D/T/R addressing** (§2.1 "Addresses are PACT D/T/R-addressed entities per the Terrene Foundation spec (mint:pact)") — citation is correct per `rules/terrene-naming.md`.
- **CARE planes (Trust + Execution):** doc 02 does not reference CARE planes. No drift.
- **Authorship Score primitive (capability 18 of doc 00):** §8 covers score computation, minimum-impact, posture-ratchet gate — all load-bearing mechanics present (though §8.2 corpus is under-specified per F-16).
- **BET-2 structural/semantic partition:** §7 honors it with 5 check classes (though see F-12 schema drift).
- **Algorithm-identifier Phase 01 gate:** §6.2 correctly states "Phase 01 exit gate: algorithm-identifier schema MUST be implemented" consistent with doc 00 v3 §4.1 item 9 and doc 09 v3 M-10.
- **Five constraint dimensions canonical naming** (§3): "Financial, Operational, Temporal, Data Access, Communication" — exact match to `rules/terrene-naming.md`. Clean.
- **doc 09 T-093 velocity-raise ratchet** (§3.1): correctly states Weekly Posture Review OR 24h-cooling-off Grant Moment — matches R2-H4.
- **doc 09 T-104 mid-flight tightening** (§6.1): three branches match R2-H3 (though F-10 open on signer identity).

---

## Recommended disposition

**Blocking for `/redteam` convergence:** F-01, F-02, F-03, F-04, F-05 — these are primitives doc 09 v3 _named_ in this exact spec but doc 02 does not deliver. Without them, the threat-model / envelope-model interface is inconsistent and `/redteam` Round 1 will surface these as CRITICAL threat-coverage gaps.

**Must fix before doc 02 freeze:** F-06 through F-14.

**Should fix in current session:** F-15 through F-19.

**Can defer to `/redteam`-triggered revisions:** F-20, F-21, F-22.

---

**Total: 22 findings** (5 CRITICAL, 9 HIGH, 5 MEDIUM, 3 LOW).

**Reviewer summary:** Doc 02 is a strong first draft of the schema + canonical data model, and §3–§5 are substantively correct in structure. The primary gap is **completeness against doc 09 v3 mitigation matrix** — 7 threat mitigations point to `specs/envelope-model.md` as primitive location but 5 of those (T-010, T-011, T-013 ReasoningCommit, T-014, T-015) have no corresponding doc 02 section. Closing F-01 through F-05 will bring doc 02 into structural alignment with doc 09 v3 and unblock `/redteam` Round 1.
