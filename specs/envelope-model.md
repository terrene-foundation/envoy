# envelope-model

## Purpose

Canonical envelope primitive — the declarative statement of what Envoy may do across 5 constraint dimensions (Financial, Operational, Temporal, Data Access, Communication). Load-bearing for every action signing, Grant Moment, posture ratchet, and cross-runtime parity claim.

## Provenance

- **Source analysis doc:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md` v3 FROZEN (12k words, full algorithm construction pack).
- **Threats mitigated:** T-005 (classifier ensemble), T-010/T-011 (prompt injection structural defense), T-013 (composition-aware), T-015 (system-prompt pinning + envelope re-read checkpoint), T-019 (velocity-raise ratchet), T-021 (linter), T-023 (Authorship Score), T-024 (enterprise-mode), T-093 (budget velocity), T-094 (variant of T-015; shared mitigations — system-prompt pinning + prompt-size-budget enforcement), T-104 (envelope-version binding), T-105 (SubsetProof schema).
- **BETs tested:** BET-2 structural/semantic partition, BET-6 contract-parity via JCS, BET-12 governance-primary-surface.
- **Cross-SDK:** kailash-py ✅ functional at `src/kailash/trust/pact/envelopes.py`; kailash-rs `ConstraintEnvelope::intersect` at `crates/eatp/src/constraints/mod.rs:356` (binding kailash-rs#503); `RoleEnvelope`/`TaskEnvelope` binding kailash-rs#504; algorithm-identifier schema mint#6 + kailash-py#604 + kailash-rs#519 (Phase 01 gate).

## Schema

Top-level `EnvelopeConfig` JSON wire format per doc 02 §2.2:

```json
{
  "schema_version": "envelope/1.0",
  "envelope_version": <int>,
  "metadata": {
    "envelope_id": "uuid-v7",
    "algorithm_identifier": {
      "sig": "ed25519", "hash": "sha256", "shamir": "slip39",
      "canonical_json": "jcs-rfc8785",
      "ensemble_classifiers": ["registry:name:sha256-hash"],
      "cross_domain_rules": "envoy-registry:cross-domain-flows:v1@sha256-hash"
    },
    "authorship_score": {"authored_count": <int>, "imported_count": <int>, "template_provenance": [...]},
    "enterprise_mode": {"is_enterprise": <bool>, "enterprise_deployment_record_hash": <sha256|null>},
    "sub_agent_session_inheritance": "transitive | isolated",
    "goal_reconfirmation": {"enabled": <bool>, "N_tool_calls": 5, "scope": "session | cross_session", "per_posture_overrides": {...}},
    "posture_level": "PSEUDO | TOOL | SUPERVISED | DELEGATING | AUTONOMOUS"
  },
  "financial": {
    "per_call_ceiling_microdollars": <int>,
    "per_session_ceiling_microdollars": <int>,
    "per_hour_velocity_microdollars": <int>,
    "per_day_ceiling_microdollars": <int>,
    "per_month_ceiling_microdollars": <int>,
    "authored_constraints": [{"constraint_id": <str>, "rule_ast": {...}, "authored": <bool>}],
    "imported_constraints": [{"constraint_id": <str>, "rule_ast": {...}, "authored": false, "template_origin": <str>, "template_hash": <sha256>}]
  },
  "operational": {
    "tool_allowlist": [<tool_name>],
    "tool_denylist": [<tool_name>],
    "rate_limits": {<tool>: {"per_minute": <int>, "per_hour": <int>, "per_day": <int>}},
    "sub_agent_spawn_limit": {"max_concurrent": <int>, "max_per_session": <int>, "max_depth": <int>},
    "authored_constraints": [...], "imported_constraints": [{"constraint_id": <str>, "rule_ast": {...}, "authored": false, "template_origin": <str>, "template_hash": <sha256>}]
  },
  "temporal": {
    "allowed_windows": [{"days": [...], "from": "HH:MM", "to": "HH:MM", "timezone": <str>}],
    "blackout_windows": [...],
    "authored_constraints": [...], "imported_constraints": [{"constraint_id": <str>, "rule_ast": {...}, "authored": false, "template_origin": <str>, "template_hash": <sha256>}]
  },
  "data_access": {
    "classification_clearance": "Public | Internal | Confidential | Restricted | HighlyConfidential",
    "field_allowlist_per_model": {<model>: [<field>]},
    "field_denylist": [<field>],
    "semantic_rules": [{"rule_id": <str>, "classifier_ref": "envoy-registry:X:v1", "threshold": <float>, "action": "block | block+grant_moment | flag+allow"}],
    "authored_constraints": [...], "imported_constraints": [{"constraint_id": <str>, "rule_ast": {...}, "authored": false, "template_origin": <str>, "template_hash": <sha256>}]
  },
  "communication": {
    "recipient_allowlist": [...], "recipient_denylist": [...],
    "domain_allowlist": [...], "channel_allowlist": [...], "channel_denylist": [...],
    "content_rules": [{"rule_id": <str>, "order": <int>, "when_ast": {...}, "content_types_forbidden": [...]}],
    "authored_constraints": [...], "imported_constraints": [{"constraint_id": <str>, "rule_ast": {...}, "authored": false, "template_origin": <str>, "template_hash": <sha256>}]
  },
  "composition_rules": [
    {"rule_id": <str>, "order": <int>, "session_condition_ast": {...}, "blocked_action_ast": {...}, "rationale": <str>}
  ],
  "cross_domain_rules_authored": [
    {"rule_id": <str>, "order": <int>, "source_domain_ast": {...}, "sink_domain_ast": {...}, "verdict": "block | block+grant_moment | flag+allow", "rationale": <str>}
  ],
  "tool_output_budget_bytes": <int>,
  "semantic_checks": {
    "data_access_classifier_ensemble": [{"classifier_ref": <str>, "weight": <float>}],
    "communication_content_classifier_ensemble": [...],
    "tool_output_classifier_ensemble": [{"classifier_ref": <str>, "weight": <float>}],
    "latency_budget_ms": {"structural_hashset": 5, "arithmetic": 5, "comparison": 1, "semantic_cached": 50, "semantic_uncached": 500, "composition_rule_eval": 10, "subset_proof_verify": 20, "tool_output_sanitize": 50, "cross_domain_rules_eval": 10},
    "unavailability_policy": "fail-closed | fail-flag | fail-open"
  }
}
```

Classification clearance canonical enum: `Public | Internal | Confidential | Restricted | HighlyConfidential` (NOT `highly_classified` — aligned with PACT canonical naming per V-06 fix).

**Field semantics for late-added fields (Round 2 R2-CRIT closure):**

- `metadata.algorithm_identifier.cross_domain_rules` — version pin for the `envoy-registry:cross-domain-flows:v1` registry that owns the cross-domain rule grammar. Cross-runtime byte-identity per BET-6 requires this pin to match the registry version actually loaded.
- `cross_domain_rules_authored` — top-level array of authored cross-domain rules consumed by `specs/cross-domain-flows.md` `evaluate_cross_domain_rules` algorithm. Imported cross-domain rules are NOT separately stored — they fold into `cross_domain_rules_authored` at template-import time with `authored=false` semantics (the import process copies the template's cross-domain rules into this top-level list). Per-dimension `imported_constraints[]` lists carry dimension-scoped imported constraints (financial / operational / temporal / data_access / communication); cross-domain rules specifically operate across dimensions and live only at the top level.
- `tool_output_budget_bytes` — top-level byte ceiling on a tool's return payload, consumed by `specs/tool-output-sanitization.md` `tool_output_sanitize` algorithm. T-010/T-011 structural defense: sanitizer truncates output above this ceiling and fails closed.
- `semantic_checks.tool_output_classifier_ensemble` — minimum-2-classifier ensemble vote applied to tool output before runtime feeds it to the next prompt. Same fail-closed unavailability policy as `data_access_classifier_ensemble`.
- `semantic_checks.latency_budget_ms.tool_output_sanitize` (50ms) and `cross_domain_rules_eval` (10ms) — fail-closed budgets for the two new check paths.
- `metadata.posture_level` — the envelope-side pin of the current posture per `specs/posture-ladder.md` § Canonical enum. Wire form is the canonical `PostureLevel` enum NAME (`"PSEUDO" | "TOOL" | "SUPERVISED" | "DELEGATING" | "AUTONOMOUS"`) so JCS canonicalization produces cross-runtime byte-identical bytes per BET-6. Default at first Boundary Conversation entry is `"PSEUDO"`. PostureGate's ratchet-up path emits an `envelope_edit` Ledger entry per `specs/ledger.md` § envelope_edit (T-02-33) — the entry's `new_version` reflects the bump and the mutated envelope's `posture_level` reflects the new level. Demotion does NOT bump the envelope (asymmetric pairing per `specs/posture-ladder.md` § Ratchet-down). **Mint-state semantics:** `metadata.posture_level` reflects the envelope's mint-time posture and is immutable after the `envelope_edit` emission that minted this envelope version. The current effective posture for a principal is derived by walking the Ledger's `posture_change` entries (the audit chain); the envelope's `posture_level` field is the mint-time annotation pinning what posture was active when this envelope version was created. Ratchet-down does NOT mutate this field (per `specs/posture-ladder.md` § Ratchet-down: demotion emits `posture_change` only, NOT `envelope_edit`); the field stays at the mint-time value, and the next ratchet-up mints a NEW envelope version whose `posture_level` reflects the new mint state. **Audit-only role:** `metadata.posture_level` is a mint-state audit annotation; the effective-posture derivation walks the Ledger's `posture_change` entries — no production read consumer dispatches on the envelope field's value.

## Algorithms

### Canonical JSON (§14.1 of source)

- **Algorithm:** RFC 8785 JCS (JSON Canonicalization Scheme).
- **Unicode:** NFC normalization applied to all string values.
- **Numbers:** integers as JSON numbers (no leading zeros, no scientific notation); floats rejected unless `math.isfinite()`; Envoy uses integer microdollars for financial quantities.
- **Escapes:** per RFC 8785 — minimal escapes only.
- **Field ordering:** lexicographic Unicode code-point ordering on NFC-normalized keys.
- **Conformance corpus:** 67 test vectors enumerated in 6 categories (Unicode, integers, numbers/floats, escapes, empty-vs-null, nested ordering). Cross-SDK byte-identity per BET-6.

### Composition-rule DSL (§14.2 of source)

- Total-bounded grammar — AST form, not string.
- Depth ≤ 5, And/Or terms ≤ 10, In set ≤ 1000.
- Per-rule budget: 5ms fail-closed.
- Total composition-rule budget: 10ms per tool-call fail-closed.
- No loops, no recursion. Single-pass tree walk.

### `intersect_envelopes(a, b)` (§14.5 of source)

- Per-dimension rules: ceilings/velocity MIN; allowlists INTERSECTION; denylists UNION; authored/imported constraints UNION with unique-ID requirement.
- Commutative + associative under distinct constraint_id + composition_rule.order.
- Raises `AlgorithmMismatchError` on algorithm_identifier mismatch; `SchemaVersionMismatchError` on schema drift; `IntersectConflictError` on duplicate IDs.
- Identity envelope (maximally-permissive) for sub-agent spawns without parent restriction.

**Naming convention (Round 2 R2-HIGH closure):** the algorithm is named `intersect_envelopes(a, b)` in this owning spec; the runtime ABC method (`specs/runtime-abstraction.md` §Envelope §Lifecycle) is named `envelope_intersect(a, b)`. The two names are intentional:

- `intersect_envelopes` = the algorithm specification — verb-first form per doc 02 §14 algorithm-naming convention.
- `envelope_intersect` = the runtime-method namespace prefix — every envelope-related ABC method is named `envelope_<verb>` for grep-ability and IDE autocomplete.

Cross-spec consumers (`specs/posture-ladder.md`, `specs/shared-household.md`, `specs/sub-agent-delegation.md`) MAY use either name when the call-site context disambiguates (algorithm reference vs runtime invocation). Both names refer to the same canonical algorithm; cross-runtime byte-identity per BET-6 holds for both names.

### Semantic classifier ensemble (§3.4.1 of source)

- Minimum 2 classifiers per semantic check.
- Weighted vote; disagreement fails closed by default.
- Cache key: `(content_hash, classifier_ref, classifier_model_hash, weight)`-tuple.
- Unavailability policy: fail-closed (default), fail-flag, fail-open (FV tier forbids fail-open).

### Authorship Score (§8, §14.7, §14.8 of source — see specs/authorship-score.md)

- Count of authored constraints with `authored=true`. Per `specs/authorship-score.md § Re-derivation from the Ledger`, T-02-30 implements the count-only recompute over the 5 canonical dimensions.
- Personal mode: N=3 for DELEGATING, N=5 for AUTONOMOUS.
- Enterprise mode: N=5 DELEGATING; AUTONOMOUS requires per-employee envelope (not shared template).

### First-time-action gate (§19 of source)

- Action fingerprint = hash(tool_name || canonicalize_args(args)).
- Lookup in `SessionObservedState.tool_calls_made` fingerprint cache (specs/session-state.md §Schema owns `SessionObservedState`).
- No match AND not in pre-authorized patterns → Grant Moment.
- Cache reset on session boundary → `session_boundary_crossed` Ledger entry (specs/session-state.md §Schema + specs/ledger.md §Entry types).

## Error taxonomy

Per doc 02 §11. Every error logged as Ledger entry with `content_trust_level: system`; error messages MUST NOT echo raw envelope content.

| Error                                    | Trigger                                                                                                  | User action                                                                          | Retry                       |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | --------------------------- |
| `EnvelopeValidationError`                | Schema-shape failure (missing required field, wrong type) at compile or load                             | Fix the offending field via Boundary Conversation re-prompt or `envoy envelope edit` | Manual after fix            |
| `EnvelopeVersionMismatchError`           | Action signed against `version=N` while live envelope is `version=M`, M>N                                | Re-sign at current version; or roll back via specs/ledger.md `envelope_edit`         | Manual                      |
| `SchemaVersionMismatchError`             | `schema_version` field disagrees between two envelopes being intersected                                 | Migrate older envelope via Foundation-published schema migration script              | Manual                      |
| `AlgorithmMismatchError`                 | `algorithm_identifier` differs between intersected envelopes (sig/hash/canonical_json/ensemble)          | Refuse intersect; user must rotate keys or run migration                             | Never (fail-closed)         |
| `CapabilityDeadError`                    | Action references tool / channel that has been declared dead in operational dimension                    | Re-check tool allowlist; re-prompt user if the action is still required              | Manual                      |
| `HaltedByRollbackError`                  | Action signed during pending envelope rollback grace window                                              | Wait for rollback grace window to close; resume action                               | Auto after window           |
| `ClockSkewBlockError`                    | Local clock vs remote-time-anchor diverges beyond tolerance                                              | Surface to user; pause Temporal-dimension actions until anchor recovers              | Auto after anchor           |
| `CrossPrincipalConsentRequiredError`     | A2A-messaging action lacks dual-signature from co-principal                                              | Surface Grant Moment to second principal; await dual-sign                            | Auto after dual-sign        |
| `CompositionRuleBlockError`              | A composition_rule's session_condition_ast matched and blocked_action_ast applied                        | Refuse action; user can edit composition rule via weekly review                      | Never (rule binds)          |
| `StructuralCheckFailedError`             | Hash-set / arithmetic / comparison structural check failed within latency budget                         | Refuse action; investigate Ledger-correlated structural-check trace                  | Never (structural defense)  |
| `SemanticCheckFailedError`               | Classifier ensemble vote crossed threshold for "block" or "block+grant_moment"                           | Surface Grant Moment OR refuse per ensemble action                                   | Manual after Grant          |
| `LatencyBudgetExceededError`             | Per-check latency exceeded budget (5/5/1/50/500/10/20ms)                                                 | Refuse fail-closed; investigate classifier slowdown                                  | Auto after classifier ready |
| `SubsetProofFailedError`                 | Sub-agent's SubsetProof failed `is_subset_envelope` against parent                                       | Sub-agent spawn refused; fix parent envelope or restrict sub-agent intent            | Never                       |
| `EnterpriseDeploymentRecordInvalidError` | Enterprise-mode envelope cites `enterprise_deployment_record_hash` that fails verification               | Surface to enterprise admin; refuse all enterprise-mode actions                      | Never (T-024 defense)       |
| `AuthorshipScoreDivergenceError`         | Cross-runtime authorship score disagreement (BET-2 violation)                                            | Halt posture ratchet; investigate runtime divergence                                 | Never                       |
| `ClassifierRegistryMissError`            | `classifier_ref` not resolvable in `envoy-registry:*` (Data Access dimension classifier ensemble)        | Refuse action per `unavailability_policy`; user re-prompts after registry sync       | Auto after registry sync    |
| `IntersectConflictError`                 | Duplicate `constraint_id` or `composition_rule.order` collision during intersect                         | Surface conflict; user resolves via envelope edit                                    | Manual                      |
| `ComposedRuleBudgetExceededError`        | Single composition_rule eval exceeded 5ms                                                                | Refuse rule fail-closed; flag rule for review                                        | Never (DSL bound)           |
| `ComposedRuleTotalBudgetExceededError`   | Total composition_rule eval exceeded 10ms per tool-call                                                  | Refuse all rules fail-closed; reduce ruleset complexity                              | Never (DSL bound)           |
| `PromptSizeBudgetExceededError`          | Compiled prompt exceeds `prompt_size_budget` (envelope-level pin per T-015)                              | Refuse send fail-closed; runtime trims context-window or splits action               | Auto after trim             |
| `EnvelopeRollbackPendingGrantsError`     | Envelope rollback attempted while pending Grant Moments exist                                            | Resolve pending grants OR explicitly abort grants; then retry rollback               | Manual                      |
| `FirstTimeActionError`                   | Action fingerprint absent from `SessionObservedState.tool_calls_made` AND not in pre-authorized patterns | Surface Grant Moment; cache fingerprint after approval                               | Manual after Grant          |
| `CompositionStateCorruptedError`         | `SessionObservedState` state corruption detected at session boundary                                     | Reset session; re-load envelope from Trust Vault                                     | Auto after reset            |

## Cross-references

- **specs/trust-lineage.md** — RoleEnvelope + TaskEnvelope signed into Trust Vault; envelope_version binding.
- **specs/ledger.md** — `envelope_edit` entries; Ledger records envelope version history.
- **specs/runtime-abstraction.md** — `envelope_check()` + `envelope_canonical_form()` + `envelope_intersect()` + `envelope_re_read_checkpoint()`.
- **specs/authorship-score.md** — count-only recompute + posture-ratchet gate in detail.
- **specs/sub-agent-delegation.md** — SubsetProof schema + verifier.
- **specs/grant-moment.md** — Grant Moment surfaces on envelope-check failures.
- **specs/threat-model.md** — T-005, T-013, T-019, T-023, T-024, T-093, T-104 mitigations housed here.
- **specs/enterprise-deployment.md** — `enterprise_deployment_record_hash` consumer.
- **specs/classification-policy.md** — Data Access dimension classifier integration.

## Test location

- `tests/integration/test_envelope_canonical_jcs_corpus_67.py` — 67 JCS test vectors across 6 categories (Tier 2; cross-SDK byte-identity per BET-6).
- `tests/integration/test_envelope_intersect_commutative.py` — `intersect_envelopes` commutativity + associativity under distinct constraint_id.
- `tests/integration/test_envelope_classifier_ensemble.py` — minimum-2 classifiers, weighted vote, fail-closed unavailability.
- `tests/integration/test_envelope_first_time_action_gate.py` — fingerprint cache + session-boundary reset (cross-ref specs/session-state.md).
- `tests/regression/test_t005_classifier_ensemble_bypass.py` — T-005 defense.
- `tests/regression/test_t010_t011_prompt_injection_structural.py` — T-010/T-011 structural defense at envelope boundary.
- `tests/regression/test_t013_composition_aware.py` — T-013 ReasoningCommit composition awareness.
- `tests/regression/test_t015_system_prompt_pinning.py` — T-015 prompt-size budget + envelope re-read checkpoint.
- `tests/regression/test_t019_velocity_raise_ratchet.py` — T-019 batch-to-envelope conversion.
- `tests/regression/test_t021_linter.py` — T-021 envelope linter catches malformed AST.
- `tests/regression/test_t023_authorship_score.py` — T-023 score-inflation defense.
- `tests/regression/test_t024_enterprise_mode_attestation.py` — T-024 EnterpriseDeploymentRecord verify.
- `tests/regression/test_t093_budget_velocity.py` — T-093 budget-exhaustion-fraud.
- `tests/regression/test_t104_envelope_version_binding.py` — T-104 envelope_version + composed-action binding.
- `tests/regression/test_t105_subset_proof_schema.py` — T-105 sub-agent envelope-downgrade defense.

## §X Change log

- 2026-05-24 — Added `channel_denylist: list[<str>]` field to `communication` block (line 66). Per /redteam Round 3 (T-01-24 Connection Vault) sibling re-derivation: `envoy.envelope.envelope_contains_scope` checks `channel_denylist` as a deny-veto distinct from `recipient_denylist` (channels are transports; recipients are entities). The schema-level addition aligns `specs/envelope-model.md` with `specs/connection-vault.md` § "Envelope-scope membership semantics" landed in the same PR.

## Open questions

1. Classifier registry governance — Foundation-curated; community contributions via mint process.
2. Composition DSL expressiveness — Phase 04 may relax some bounds based on user patterns.
3. Migration cadence for algorithm-identifier — quarterly review vs on-demand.
4. `goal_reconfirmation` schema is declared but no spec describes the algorithm consuming it (Round 1 R2-MED) — needs algorithm spec or removal.
5. `sub_agent_session_inheritance: "transitive | isolated"` semantics owner — where does the transitive vs isolated runtime-decision algorithm live (Round 1 R2-MED).
