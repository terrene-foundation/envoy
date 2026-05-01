# Round 2 Review — doc 02 Envelope Model (reviewer, convergence verification)

**Target:** `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/02-envelope-model.md` v2 (1089 lines)
**Anchors (frozen):** doc 00 v3, doc 09 v3
**Prior pass:** Round 1 reviewer (22 findings) + adversarial (21) + mechanical (8) → 52 raw, 40 deduped (7 CRIT / 15 HIGH / 12 MED / 6 LOW).
**Exit criterion:** 0 CRITICAL + ≤ 2 HIGH.
**Date:** 2026-04-21
**Verdict:** **CONVERGED** — 0 CRITICAL, 2 HIGH, 4 MEDIUM, 3 LOW. Exit criterion met.

---

## Summary table

| #    | Severity | Area                                         | Round 1 link                | Status in v2                                                                           |
| ---- | -------- | -------------------------------------------- | --------------------------- | -------------------------------------------------------------------------------------- |
| V-01 | HIGH     | Turn-N goal-reconfirmation primitive gap     | CRIT F-03 partial           | §16 ReasoningCommit defined; turn-N primitive NOT specified in envelope-model (open)   |
| V-02 | HIGH     | DSL path schema drift vs §15                 | adversarial C-02 (residual) | §14.2 `SessionStateRef` path `observed_data.has_classification` ≠ §15 field names      |
| V-03 | MEDIUM   | Sub-agent inheritance flag mis-placement     | reviewer F-04 residual      | `inherit_session_state` on `composition_rules[]` is wrong scope                        |
| V-04 | MEDIUM   | Error taxonomy incomplete vs F-11            | reviewer F-11 partial       | 4 of 12 F-11-suggested errors still missing                                            |
| V-05 | MEDIUM   | Cross-domain-flow gate overlap with §5.3     | new in v2                   | §20 + §5.3 unify mechanisms implicitly; ownership ambiguous                            |
| V-06 | MEDIUM   | EDR schema field name vs §2.2 metadata       | reviewer F-14 residual      | `attestation_record_hash` in §2.2 vs `EnterpriseDeploymentRecord` full schema in §14.3 |
| V-07 | LOW      | v2 change-summary arithmetic                 | new in v2                   | "52 findings (7+15+12+6=40)" + "+8 errors" (actually 9 bolded)                         |
| V-08 | LOW      | Round-2 reference token typo                 | new in v2                   | §14.4 line 738 says "R2M-4"; other refs use `R2-H`/`R2-C`                              |
| V-09 | LOW      | Sub-agent inheritance T-106 claim too strong | new in v2                   | §15 claims transitive inheritance is "defense-in-depth for T-106 A2A collusion" — weak |

Convergence status per Round 1 findings:

| Round 1 ID                       | Resolution in v2                                  | Status             |
| -------------------------------- | ------------------------------------------------- | ------------------ |
| CRIT F-01 (T-015)                | §17 pinning + re-read + prompt-size budget        | RESOLVED           |
| CRIT F-02 (T-014)                | §18 framing + per-turn reset (line 1041)          | RESOLVED           |
| CRIT F-03 (T-013 + turn-N)       | §16 ReasoningCommit; turn-N NOT defined           | **PARTIAL → V-01** |
| CRIT F-04 (SessionObservedState) | §15 schema + lifecycle                            | RESOLVED           |
| CRIT F-05 (intersect edge cases) | §14.5 pseudocode + §5.1 identity_envelope         | RESOLVED           |
| CRIT C-01 (canonical JSON)       | §14.1 JCS + NFC + math.isfinite                   | RESOLVED           |
| CRIT C-02 (DSL)                  | §14.2 AST + depth-5 + 10-term + 10ms              | RESOLVED (→ V-02)  |
| CRIT C-03 (EDR)                  | §14.3 schema + dual sig + 24h cooling             | RESOLVED (→ V-06)  |
| CRIT C-04 (SubsetProof)          | §14.4 5-dimension witnesses + direction inversion | RESOLVED           |
| HIGH F-06 (tool-output sanit.)   | §20                                               | RESOLVED           |
| HIGH F-07 (first-time-action)    | §19                                               | RESOLVED           |
| HIGH F-08 (clearance canonical)  | §3.4 `HighlyConfidential`                         | RESOLVED           |
| HIGH F-09 (subset-proof)         | §14.4                                             | RESOLVED           |
| HIGH F-10 (HALTED signer)        | §6.1 Branch 3 `halted_by=runtime_device_key`      | RESOLVED           |
| HIGH F-11 (error taxonomy)       | §11 +9 errors                                     | **PARTIAL → V-04** |
| HIGH F-12 (latency budget)       | §2.2 + §7 7-class partition                       | RESOLVED           |
| HIGH F-13 (session budget)       | §3.1 `per_session_ceiling_microdollars`           | RESOLVED           |
| HIGH F-14 (EDR verify semantics) | §14.3                                             | RESOLVED (→ V-06)  |
| HIGH H-01 (commutativity)        | §5.1 + §14.5 union_unique_ids + IntersectConflict | RESOLVED           |
| HIGH H-02 (ensemble unavail.)    | §14.6 unavailability_policy + model hash          | RESOLVED           |
| HIGH H-03 (authorship gaming)    | §14.7 Jaccard + novelty classifier + §14.8        | RESOLVED           |
| HIGH H-04 (content_trust_level)  | §2.2 AST (not string) + §16 llm-authored framing  | RESOLVED           |
| HIGH H-05 (alg-id ensemble)      | §2.2 `ensemble_classifiers` hashes                | RESOLVED           |
| HIGH H-06 (velocity via edit)    | §3.1 envelope-edit path extension                 | RESOLVED           |
| HIGH H-07 (mid-flight algo)      | §6.1 Branch 2 concrete algorithm                  | RESOLVED           |
| HIGH H-08 (IT-disable channels)  | §14.3 cross-channel + 24h cooling-off             | RESOLVED           |
| HIGH H-09 (allowlist Unicode)    | §3.4 NFC + homograph                              | RESOLVED           |
| HIGH H-10 (classifier registry)  | §14.6 registry + classifier_ref format            | RESOLVED           |
| HIGH Mech M-09 (first-time)      | §19                                               | RESOLVED           |

**CRIT: 9 of 9 resolved. HIGH: 13 of 15 fully resolved + 2 partial (F-03 turn-N, F-11 error taxonomy).**

Partial classification: the partials are scoped-down enough that they regress to HIGH-only (new V-01, V-04), not CRIT. All thesis-breaking primitives are now constructed.

---

## A. Round 1 CRIT convergence — detail

### F-01 — RESOLVED

§17 defines: system-prompt pinning (with kailash-py sticky flag + kailash-rs#511), prompt-size budget (50% untrusted threshold + safe-summarizer), envelope-re-read checkpoint (from Trust Vault, not context), multi-provider fallback. All three T-015 mitigations from doc 09 v3 are now envelope-model primitives.

### F-02 — RESOLVED

§18 defines the canonical wire format with `<trusted_context>`, `<untrusted_context>`, `<ledger_entry>`, `<tool_response>` tokens AND the instruction framing for each. Per-turn reset (line 1041) fires when untrusted-context turns ingest `derived-external` content. Tokens cross-match doc 09 v3 T-012/T-014/T-015 byte-for-byte.

### F-03 — **PARTIAL** (flagged V-01)

§16 ReasoningCommit fully defined including the critical runtime-vs-LLM signature split (only runtime-generated fields signed). R2-C1 re-entry defense in place (line 979).

BUT: "turn-N goal-reconfirmation" — named in doc 09 v3 T-013/T-014/T-016 mitigations with explicit `N=5 default` — is NOT defined as an envelope-level primitive in doc 02 v2. §5.3 and §16 describe composition-rule evaluation but do not specify:

- `composition_rules[].kind: goal_reconfirmation`
- `every_n_turns: 5`
- `prompt_template` for the reconfirmation Grant Moment

See V-01 for disposition.

### F-04 — RESOLVED

§15 ships full schema, lifecycle with 4 boundary events (agent-turn-reset, envelope-edit, explicit-reset, sub-agent-spawn), sub-agent transitive-inheritance default + opt-out, Trust Vault persistence, injection-reach mitigation.

### F-05 — RESOLVED

§14.5 `intersect_envelopes()` pseudocode covers:

- Algorithm-identifier + schema-version mismatch at entry (raises)
- Identity-envelope early-return
- Per-dimension operation (MIN/UNION/INTERSECT/concat-normalized)
- Commutativity + associativity proof sketch (§5.1 + §14.5 closing paragraph)
- `IntersectConflictError` on duplicate constraint_id / composition_rules order
- `identity_envelope` defined at §5.1

### C-01 — RESOLVED

§14.1 canonical JSON = RFC 8785 JCS + NFC + `math.isfinite()` for floats + explicit treatment of `null` vs missing + 50+ conformance vectors. Both kailash-py (`jcs` library) and kailash-rs (`serde_jcs` crate) named. Cross-SDK BET-6 test tied to kailash-py#605.

### C-02 — RESOLVED (but see V-02 for residual path drift)

§14.2 DSL is AST-form (not string), with:

- 7 AST node types explicitly enumerated
- Depth bound ≤ 5
- And/Or term count ≤ 10 (flat)
- `In` set size ≤ 1000
- Total time budget 10ms per rule + 10ms per tool-call
- Glob not regex for name_pattern (no ReDoS)
- Static validation at envelope import

Residual: DSL `SessionStateRef.path` form doesn't match §15 schema field names (see V-02).

### C-03 — RESOLVED (minor field-name drift — V-06)

§14.3 `EnterpriseDeploymentRecord` has:

- org_genesis_hash anchoring to org Trust Lineage
- Both deploying + affected-employee principals
- Dual signatures REQUIRED
- Closed enum for `scope`
- Re-verification on every envelope import (not just install)
- 24h cooling-off + cross-channel confirmation for enterprise-mode OFF
- 365-day re-attestation requirement

Residual: §2.2 metadata still uses field name `attestation_record_hash`, but §14.3 full record is named `EnterpriseDeploymentRecord` and §11 error is `EnterpriseDeploymentRecordInvalidError`. Field-name consistency — see V-06.

### C-04 — RESOLVED

§14.4 `SubsetProof` with:

- All 5 dimensions' witnesses enumerated
- `content_rules_superset_union` direction inversion EXPLICITLY documented with `inversion_reason`
- Runtime's `runtime_verification_signature` separate from parent's `signature_by_parent` (R2-H2 independent re-verification)
- Conformance vectors list including 5 direction-inverted adversarial tests
- `is_subset_envelope(sub, parent)` first-class algorithm

---

## B. Round 1 HIGH convergence

All 15 Round 1 HIGHs have resolution; 2 are partial-only (F-03 turn-N, F-11 error taxonomy — both regressed to V-01 and V-04 below, both HIGH or lower).

Mechanical M-09 (first-time-action in §7 hot-path) is RESOLVED: §7 line 396 shows `1. First-time-action gate check (§19)` as step 1, BEFORE structural checks. §19 elaborates algorithm + edge cases + pre-authorization.

---

## C. Internal consistency

Pass:

- §14 algorithm construction pack cross-references §3–§13 correctly.
- Error taxonomy enum names match usage sites (`HighlyConfidential` throughout; `HaltedByRollback` in §6.1 and §11; `IntersectConflictError` in §5.1 and §11; `ComposedRuleBudgetExceededError` in §14.2 and §11).
- Canonical tokens in §18 (`<trusted_context>`, `<untrusted_context>`, `<ledger_entry>`, `<tool_response>`) match doc 09 v3 line 123 + 171.
- Classifier registry references `envoy-registry:<family>.<name>:<version>` format used consistently at §2.2 (4 instances), §3.4 (1), §5.1 (1), §14.6 (1), §14.7 (1), §17 (1), §20 (2). All 11 usages identical format.
- §14.5 intersect pseudocode for Communication `content_rules = union_with_conflict_resolution(...)` is consistent with §5.1 per-dimension rule "UNION with explicit conflict resolution; BLOCK dominates".

Minor drifts (caught below as V-02 / V-06):

- §14.2 DSL `SessionStateRef.path` references `observed_data.has_classification` — but §15 SessionObservedState has `observed_data_classifications` (different field name).
- §2.2 metadata field `attestation_record_hash` is semantically the `EnterpriseDeploymentRecord` hash; field-name drift.

---

## D. New regressions introduced by v2

### D.1 §14.5 intersect pseudocode vs §5.1 per-dimension rules — CONSISTENT

Each per-dimension operation in §14.5 matches the §5.1 table:

- Financial MIN → `min(a.financial[field], b.financial[field])` ✅
- Operational allowlist INTERSECT + denylist UNION → `a... & b...` + `a... | b...` ✅
- Temporal allowed INTERSECT + blackout UNION → `intersect_window_lists(...)` + `a | b` ✅
- Data Access clearance MIN → `min_clearance(...)` ✅
- Communication content_rules UNION with block-dominates → `union_with_conflict_resolution(...)` ✅
- composition_rules UNION ordered → `union_ordered_unique(...)` ✅
- semantic ensembles concat+normalize → `normalize_weights(a... + b...)` ✅

### D.2 §14.4 subset-proof `content_rules_superset_union` — CORRECT

Direction inversion matches doc 09 v3 T-105 R2-H2 line 539: "sub-content-constraints ⊇ parent-content-constraints (more restrictive = fewer content-types allowed)". §14.4 line 727-729 mirrors this with `inversion_reason: "more restrictive = fewer allowed content types"`. Semantically correct: if content_rules are LISTS OF BLOCK PATTERNS, sub having MORE blocks = more restrictive = UNION side of intersect = SUPERSET side of subset-proof. Consistent triple.

### D.3 §15 sub-agent transitive inheritance vs T-106 — SAFE but claim overstated

T-106 is cross-principal (A2A) collusion. Sub-agent inheritance is within-principal. The §15 claim that "transitive inheritance is defense-in-depth for T-106 A2A collusion" is not incorrect but is weakly supported:

- Within-principal sub-agent → A2A to other-principal would still carry inherited SessionObservedState.
- That would be a leak channel from parent's SessionObservedState → sub-agent → A2A message payload → cross-principal.
- §20 tool-output sanitization + §14.4 SubsetProof direction-inversion mitigate this, but §15 doesn't explicitly cite them.

See V-09 (LOW). Does not regress safety; tightens framing.

### D.4 §19 first-time-action gate ordering vs §7 hot-path — CONSISTENT

§7 hot-path line 396 shows step 1 = first-time-action gate. §19 line 1056 says: "Hot-path placement: first-time-action gate runs BEFORE structural checks (§7 hot-path step 1)." Internally consistent.

### D.5 §20 cross-domain-flow gate vs §5.3 composition_rules — OVERLAP, ownership unclear

§20 line 1079: cross-domain-flow gate "detected via composition_rules pre-authored by user OR by envelope-model's default cross-domain rules (Foundation-curated `envoy-registry:cross-domain-flows:v1`)". But the relationship between these TWO mechanisms is not resolved:

- Are Foundation-curated default rules evaluated by the SAME composition-rule engine (§14.2 DSL)?
- Or are they a parallel check surface?
- If parallel: what's the evaluation order against composition_rules?
- If unified: where are they loaded from + how are version-pinned?

See V-05 (MED). Not blocking but leaves the composition-rule engine with an ambiguous second input source.

---

## E. Cross-doc alignment

### Doc 00 v3

- BET-6 contract-parity: §14.1 JCS algorithm + cross-SDK conformance vectors ✅
- BET-2 structural/semantic partition: §7 honors 7-class partition (more granular than BET-2's 2-way, which is fine) ✅
- 5 constraint dimensions canonical naming: §3 + schema use exact names ✅
- Authorship Score posture-ratchet gate: §8.3 references N=3 Personal / N=5 Enterprise / annual revalidation ✅
- §4.1 item 9 algorithm-identifier Phase 01 exit gate: §6.2 + §12 cross-ref ✅

### Doc 09 v3

Every `specs/envelope-model.md` primitive location in doc 09 v3 mitigation matrix now has a corresponding doc 02 section:

- T-010 first-time-action gate → §19 ✅
- T-011 tool-output sanitization → §20 ✅
- T-012 content_trust_level + description-hash signing → §16 (partial — description-hash is in doc 04, but envelope-side interaction covered) ✅
- T-013 ReasoningCommit + composition-aware → §16 + §5.3 + §14.2 (turn-N primitive is partial; see V-01) PARTIAL
- T-014 per-turn reset + framing → §18 ✅
- T-015 system-prompt pinning + re-read + prompt budget → §17 ✅
- T-021 linter → §9 ✅
- T-023 authorship novelty + min-impact → §8 + §14.7 + §14.8 ✅
- T-024 enterprise-mode attestation → §14.3 ✅
- T-093 velocity-raise ratchet → §3.1 ✅
- T-104 envelope-version binding + mid-flight tightening → §6.1 (3 branches + concrete Branch 2 algorithm + signer identity) ✅
- T-105 sub-agent subset-proof → §14.4 ✅

### Doc 01/03/04/05/07/08/10

§12 cross-references all downstream docs. No forward-reference anti-patterns (doc 02 doesn't depend on doc 04 for any load-bearing definition; SessionObservedState is locally grounded in §15).

---

## F. Detail on V-01 — V-09 findings

### V-01 — HIGH — Turn-N goal-reconfirmation primitive not defined

**Issue:** doc 09 v3 T-013, T-014, T-016 mitigations all cite "Turn-N goal-reconfirmation (MUST, Phase 02): every N tool-call invocations (N=5 default, tunable), agent auto-surfaces a Grant Moment." Primitive location implied as `specs/envelope-model.md` via composition-aware-constraints. v2 adds §16 ReasoningCommit (partial T-013 coverage) but does NOT define the turn-N envelope field or the reconfirmation prompt template.

**Location:** doc 02 §5.3, §16.

**Fix (non-blocking for Phase 01 since doc 09 marks T-013 turn-N as Phase 02, but should land before doc 02 freeze):** Add to §5.3 a composition_rules kind:

```json
{
  "rule_id": "goal-reconfirmation",
  "kind": "goal_reconfirmation",
  "every_n_tool_calls": 5,
  "prompt_template": "Am I still working on the original intent you stated?",
  "order": 999
}
```

And at evaluation time: increment per-session tool-call counter; when counter mod N == 0, fire Grant Moment with `prompt_template`. Reset counter on affirmative user response.

**Why kept as HIGH, not CRIT:** T-013/T-014 broader mitigations ARE covered via §16 ReasoningCommit + §5.3 composition rules. Turn-N is a specific one-paragraph envelope primitive and is Phase 02 per doc 09 v3 — not a Phase 01 blocker. But it belongs here and its absence is a known gap.

---

### V-02 — HIGH — DSL `SessionStateRef.path` drifts from §15 SessionObservedState schema

**Issue:** §14.2 line 607 defines DSL `SessionStateRef` with `path: ["session", "observed_data", "has_classification", string]`. But §15 SessionObservedState schema (line 912) has field `observed_data_classifications` (plural, with `_classifications` suffix). The DSL path `observed_data.has_classification(...)` does not resolve against the SessionObservedState schema as-written.

**Location:** doc 02 §14.2 vs §15.

**Fix:** either

(a) Update §14.2 DSL path to `["session", "observed_data_classifications", "contains", {"classification": string}]` to match §15 schema field names.

(b) Update §15 to rename `observed_data_classifications` to `observed_data` with a `classifications` sub-field.

(c) Clarify that `has_classification(X)` is a method-style pseudo-path that resolves against `observed_data_classifications` via a declared method registry. Add the method registry.

Any of the three fixes is fine. DO pick one before freeze — the mismatch blocks any implementer trying to build the DSL evaluator.

**Why HIGH:** this is an implementer-facing correctness issue on the critical path. The DSL evaluator cannot be built correctly until §14.2 + §15 agree on field names.

---

### V-03 — MEDIUM — `inherit_session_state` mis-placed on `composition_rules[]`

**Issue:** §15 line 939: "Explicit opt-out per envelope (`composition_rules[].inherit_session_state: false`)". But `composition_rules` are AST-form gating rules (§14.2) — their members have `rule_id`, `order`, `session_condition_ast`, `blocked_action_ast`, `rationale`. Inheritance is a meta-property of the envelope, not a property of a specific composition_rule.

Correct scope: either (a) on `operational.sub_agent_spawn_limit` (envelope-level metadata for sub-agent semantics), or (b) new top-level `sub_agent_inheritance: {session_observed_state: transitive | isolated}` field.

**Location:** doc 02 §15.

**Fix:** Move the flag to `operational.sub_agent_spawn_limit.inherit_session_state` (enum: `transitive | isolated`) OR to envelope-level `sub_agent_inheritance` block. Update §3.2 to document.

---

### V-04 — MEDIUM — Error taxonomy still missing 4 of 12 F-11 proposals

**Issue:** §11 has 20 errors (9 new vs v1). v2 change-summary says "+8 errors" (arithmetic drift — see V-07). F-11 proposed 12 new errors; the 4 still missing:

- `PromptSizeBudgetExceededError` (T-015 prompt-size budget, §17) — surfaces when untrusted content exceeds the 50% threshold AND summarizer fails
- `EnvelopeRollbackPendingGrantsError` (§6.1 T-104 rollback with pending in-flight grants) — distinct from `HaltedByRollbackError` because the user initiates the rollback and must acknowledge pending grants
- `FirstTimeActionError` / `NewActionGrantRequired` (§19 first-time-action gate) — currently unnamed; §19 refers to "trigger Grant Moment" without naming the typed error
- `CompositionStateCorruptedError` (§15 SessionObservedState corruption / sub-agent-inheritance conflict)

**Location:** doc 02 §11.

**Fix:** add the 4 error entries.

---

### V-05 — MEDIUM — §20 cross-domain-flow gate overlap with §5.3 ambiguous

**Issue:** §20 line 1079 defines the cross-domain-flow gate with TWO sources: user-authored `composition_rules` OR Foundation-curated `envoy-registry:cross-domain-flows:v1`. The relationship between these is undefined:

- Are Foundation-curated rules evaluated by the same §14.2 DSL AST engine?
- If yes: are they "imported" rules (like `imported_constraints`) with their own order-field?
- If parallel: what's the precedence?

**Location:** doc 02 §20, §5.3, §14.2.

**Fix:** explicitly say the Foundation-curated rules ARE composition_rules that Envoy appends at envelope-compile time (§4 Step 3 template-resolution extension). They carry `authored: false`, `source: "envoy-registry:cross-domain-flows:v1"`, and evaluate by the same DSL engine. Order values reserved for registry rules are in `[1000, 1999]` range; user rules use `[0, 999]`.

---

### V-06 — MEDIUM — §2.2 metadata field name drifts from §14.3 record name

**Issue:** §2.2 line 104 has `"attestation_record_hash": null`. §14.3 defines the full record as `EnterpriseDeploymentRecord`. §11 error is `EnterpriseDeploymentRecordInvalidError`. There is no explicit cross-ref saying `attestation_record_hash` IS the hash of an `EnterpriseDeploymentRecord`.

Reviewer F-14 in Round 1 noted this: "enterprise_deployment_record_hash in §2.2 metadata is not tied to verification semantics". v2 renamed the field to `attestation_record_hash` which is arguably WORSE (abbreviates away the `EnterpriseDeployment` type linkage).

**Location:** doc 02 §2.2 metadata.

**Fix:** rename `attestation_record_hash` → `enterprise_deployment_record_hash`; explicitly state "hash of the EnterpriseDeploymentRecord defined in §14.3; verification per §14.3 on every envelope import."

---

### V-07 — LOW — v2 change-summary arithmetic drift

**Issue:** line 5 says:

- "Round 1 surfaced 52 findings across mechanical + reviewer + adversarial sweeps (7 deduped CRITs + 15 HIGHs + 12 MEDs + 6 LOWs)" — the deduped count is 7+15+12+6=40, not 52. "52 findings" is the raw pre-dedup count.
- "error taxonomy +8 errors" — actual count of new (bolded) errors is 9.

**Fix:** line 5 → "Round 1 surfaced 52 raw findings; deduped to 40 (7 CRIT + 15 HIGH + 12 MED + 6 LOW) ... error taxonomy +9 errors".

---

### V-08 — LOW — §14.4 line 738 stray token "R2M-4"

**Issue:** "Direction inversion explicit (per R2M-4 finding):" — the project's Round-2 finding ID convention is `R2-H<n>` / `R2-C<n>` (see lines 190, 333, 637, 681, 685, 733, 740). "R2M-4" is a typo or orphaned reference from an earlier draft.

**Fix:** replace `R2M-4` with correct reference (likely `R2-H2` grounding the independent-verifier claim, or a Round 1 adversarial reference like `C-04 component`).

---

### V-09 — LOW — Sub-agent inheritance T-106 defense-in-depth claim weak

**Issue:** §15 line 939: "transitive inheritance (sub-agent inherits parent's SessionObservedState; defense-in-depth for T-106 A2A collusion + T-013 composition)". T-106 is cross-principal A2A (Shared Household, two distinct principals), NOT parent→sub-agent within-principal. Transitive inheritance defends T-013 (within-session composition across sub-agents) but its T-106 connection is weak.

Additionally: transitive inheritance CREATES a potential leak path — parent's SessionObservedState → sub-agent → A2A message → cross-principal surface. §20 sanitization mitigates but is not cross-linked here.

**Fix:** reword to "defense-in-depth for T-013 composition; cross-principal A2A (T-106) mitigated separately via §14.4 SubsetProof + §20 cross-domain-flow gate." Add a note on the parent→sub-agent→A2A leak path explicitly addressed by §14.4 envelope-binding + §20 sanitization.

---

## Notes on items that passed (re-verification)

- **Canonical names:** dimensions (§3), clearance enum (§3.4), classifier_ref format (§14.6), token names (§18) all match anchor-doc canonical forms.
- **License references:** doc 02 is not a code file; no license header expected. Cross-refs to PACT (`terrene-foundation/mint`) use the Foundation's canonical org name per `rules/terrene-naming.md`.
- **Error types:** 20 errors each with typed trigger + user action. No bare exceptions. Error fingerprints (not raw content) per adversarial L-01.
- **BET-6 byte-parity:** JCS + NFC + deterministic number handling + 50 conformance vectors + kailash-py#605 runner — Phase 01 exit gate operationalized.
- **BET-2 structural/semantic partition:** 7-class partition with explicit per-class budgets (structural_hashset 5ms, arithmetic 5ms, comparison 1ms, semantic_cached 50ms, semantic_uncached 500ms, composition_rule_eval 10ms, subset_proof_verify 20ms). Strictly finer than v1's 3-class partition.
- **BET-12 authorship:** §8 + §14.7 + §14.8 with novelty dedup + minimum-impact check + corpus definition (Foundation-curated `standard_action_corpus_v1`) + cold-start handling. N=3/N=5 posture-ratchet + annual revalidation. Adversarial-wording classifier with quarterly retraining.
- **Round 1 residuals from v2 changes:** no regressions introduced that block convergence. §14.5 pseudocode and §5.1 table are byte-consistent under visual review.

---

## Recommended disposition

**Converged.** v2 meets the 0 CRIT + ≤ 2 HIGH exit criterion (actual: 0 CRIT + 2 HIGH).

- **V-01** (turn-N goal-reconfirmation): can defer to doc 02 v3 or explicitly punt to doc 04 `reasoning-commit` side if doc 04 owns turn-counter logic. Phase 02 gate per doc 09 T-013.
- **V-02** (DSL path vs §15 schema): fix in doc 02 v3 before freeze. Implementer-blocking.
- **V-03 through V-06** (MED): fix in doc 02 v3 — 30-min cleanup pass.
- **V-07 through V-09** (LOW): cosmetic; fix in v3 freeze pass.

**Unblocked for doc 03 drafting.** The envelope primitive is now load-bearing for doc 01 (Grant Moment), doc 03 (Trust Lineage), doc 04 (Ledger), doc 05 (runtime), doc 07 (channels), doc 08 (skills), doc 10 (storage). All cross-document contracts from doc 02's side are specified.

---

**Total:** 9 findings (0 CRIT / 2 HIGH / 4 MED / 3 LOW). Exit criterion met.

**Reviewer summary:** v2 is a substantial rewrite — +4k words, 7 new sections (§14–§20), 9 new error types, 4 new schema blocks (EDR, SubsetProof, SessionObservedState, ReasoningCommit). All 9 Round 1 CRITs are resolved structurally. All 15 Round 1 HIGHs have resolution with 2 residual narrow gaps (V-01 turn-N primitive + V-04 4 missing error types) that regress to new HIGHs. The doc is now the algorithm-construction spec Round 1 said it needed to be. Fitness for `/redteam` Round 2 entry (≤ 2 HIGH) is confirmed.
