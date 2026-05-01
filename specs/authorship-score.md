# authorship-score

## Purpose

BET-12 structural enforcement primitive. Semantic de-dup + minimum-impact + posture-ratchet gate.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 §8 + §14.7 + §14.8`.
- **Threats mitigated:** T-023 score inflation, T-024 enterprise delegation-upward.
- **BETs tested:** BET-12 governance-primary-surface, BET-1 authorship.

## Score computation

```
AuthorshipScore = count of envelope.*.authored_constraints where:
  - authored: true
  - novelty_check_passed: true (Jaccard < 0.85 on AST canonical form + adversarial-wording classifier < 0.8)
  - minimum_impact_check_passed: true (dry-run corpus + user's 30-day Ledger history)
```

## Stored counters (envelope.metadata.authorship_score schema)

Per specs/envelope-model.md §Schema, the envelope metadata carries three signed counters. All three are canonical + signed at envelope-sign time; runtime recomputes from the Ledger at verify time and raises `AuthorshipScoreDivergenceError` on mismatch (§Stored vs recomputed below).

| Field                 | Type                                 | Semantics                                                                                                                                                                                                                                                                                                        |
| --------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `authored_count`      | `int`                                | Count of constraints with `authored=true` that pass novelty + minimum-impact. Only this counter gates posture ratchet (§Posture-ratchet gate).                                                                                                                                                                   |
| `imported_count`      | `int`                                | Count of constraints with `authored=false` — imported wholesale from a Foundation template, organizational policy, skill ENVELOPE.md (specs/skill-ingest.md), or another principal's envelope. Does NOT count toward posture ratchet — imported constraints are not authored.                                    |
| `template_provenance` | `list[{template_id, template_hash}]` | Ordered list of templates the imported constraints originate from. Each entry `{template_id: "envoy-registry:family-starter:v1", template_hash: "sha256:..."}` binds the envelope to specific template versions per specs/foundation-ops.md §Infrastructure inventory #1 (Envelope Library + template registry). |

**Why `imported_count` is separate:** BET-12 requires posture ratchet to be gated by the user's own authoring, not by the convenience of importing a stranger's template. A user who imports a 50-constraint enterprise template and authors nothing has `authored_count=0` and remains at `TOOL` posture (specs/posture-ladder.md). `imported_count` is tracked separately so UX can nudge ("your envelope is imported; author your first constraint to progress").

**Why `template_provenance` is ordered + hashed:** templates evolve. A principal who imported `family-starter:v1` must verify later that their imported constraints still correspond to v1 bytes, not a silently-upgraded v2. Hash binding per specs/foundation-ops.md §Infrastructure inventory #1 (Envelope Library + template registry).

### Re-derivation from the Ledger

```python
def rederive_authorship_counters(envelope, ledger_slice):
    authored = 0
    imported = 0
    template_provenance = []
    for dim in ("financial", "operational", "temporal", "data_access", "communication"):
        for c in getattr(envelope, dim).authored_constraints:
            if c.authored and novelty_check(c, envelope, ledger_slice) and minimum_impact_check(c, envelope, ledger_slice):
                authored += 1
        for c in getattr(envelope, dim).imported_constraints:
            imported += 1
            origin = (c.template_origin, c.template_hash)
            if origin[0] and origin not in {(t["template_id"], t["template_hash"]) for t in template_provenance}:
                template_provenance.append({"template_id": origin[0], "template_hash": origin[1]})
    return AuthorshipCounters(authored_count=authored, imported_count=imported, template_provenance=template_provenance)
```

## Novelty de-duplication algorithm

1. Canonicalize proposed constraint AST (tree-normalize: sort sibling terms lexicographically, constant-fold).
2. Tree-Jaccard similarity against each existing constraint's canonicalized AST. Threshold 0.85.
3. `envoy-registry:novelty.adversarial-wording:v1` classifier check (catches LLM-assisted gaming). Threshold 0.8.
4. Distinct iff both checks pass.
5. Quarterly retrain of adversarial-wording classifier on user-submitted attempts.

## Minimum-impact check algorithm

1. Dry-run corpus: Foundation-curated `standard_action_corpus_v1` (10k actions across 5 dimensions) + user's 30-day Ledger history.
2. For each action: evaluate under current envelope vs current + proposed. Distinct decision on ≥1 action → proposed has behavioral impact.
3. No decision change → `MinimumImpactCheckFailedError`; UX surfaces "here's what would narrow me."

## Cold-start

If user history <30 days, synthetic corpus only. Implicit "trust user intent" with warning.

## Posture-ratchet gate

- **Personal mode:** N=3 for DELEGATING; N=5 for AUTONOMOUS.
- **Enterprise mode (cryptographically attested):** N=5 DELEGATING; AUTONOMOUS NOT reachable on shared templates.
- **Shared Household:** per-principal scores; household-wide actions require composition.
- **Annual revalidation:** posture decays 1 level at 12mo; user re-authors ≥1 to restore.

## Stored vs recomputed (M-05 fix from doc 02 R1)

`metadata.authorship_score.authored_count` signed at sign time. Runtime recomputes at verify. Mismatch → `AuthorshipScoreDivergenceError` audit alert.

## Error taxonomy

| Error                                 | Trigger                                                                                      | User action                                                                                                       | Retry                    |
| ------------------------------------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------ |
| `NoveltyCheckFailedError`             | Tree-Jaccard ≥ 0.85 OR adversarial-wording classifier ≥ 0.8 against existing constraints     | Re-author with substantive AST difference; or accept template attribution and skip authorship credit              | Manual after re-author   |
| `MinimumImpactCheckFailedError`       | Proposed constraint produces no decision change on dry-run corpus + 30-day Ledger            | UX surfaces "here's what would narrow me"; user broadens scope or removes redundancy                              | Manual after re-author   |
| `AuthorshipScoreDivergenceError`      | `metadata.authorship_score.authored_count` signed value diverges from runtime re-derivation  | Halt posture ratchet; investigate Ledger replay; surface to user as audit alert                                   | Never (T-023 defense)    |
| `ClassifierRegistryMissError`         | `envoy-registry:novelty.adversarial-wording:v1` not resolvable at check time                 | Refuse novelty check fail-closed per envelope-model.md unavailability_policy; user re-prompts after registry sync | Auto after registry sync |
| `TemplateProvenanceHashMismatchError` | `template_hash` in `template_provenance` no longer matches `envoy-registry:*` template entry | Surface to user; user re-imports template explicitly OR pins to old version                                       | Manual                   |
| `EnterprisePostureCeilingError`       | Enterprise-mode user attempts AUTONOMOUS posture on shared template                          | Refuse posture raise; per-employee envelope required (specs/enterprise-deployment.md)                             | Never (T-024 defense)    |
| `ColdStartInsufficientHistoryError`   | User Ledger history <30d and synthetic corpus refuses minimum-impact check                   | UX surfaces cold-start advisory; allow with warning per §Cold-start                                               | Manual                   |

## Cross-references

- specs/envelope-model.md — authored_constraints storage.
- specs/grant-moment.md — Approve+author path gates via this spec.
- specs/boundary-conversation.md — authorship nudge at novelty-failed constraint.
- specs/weekly-posture-review.md — score progression ritual.
- specs/posture-ladder.md — ratchet target enum (PSEUDO/TOOL/SUPERVISED/DELEGATING/AUTONOMOUS).
- specs/foundation-ops.md — `envoy-registry:novelty.adversarial-wording:v1` classifier registry + `standard_action_corpus_v1` corpus.
- specs/threat-model.md — T-023, T-024.

## Test location

- `tests/unit/test_novelty_jaccard_threshold.py` — Jaccard 0.85 boundary cases.
- `tests/unit/test_adversarial_wording_classifier_threshold.py` — 0.8 boundary on registry-curated samples.
- `tests/integration/test_minimum_impact_dry_run.py` — `standard_action_corpus_v1` + 30-day Ledger replay (Tier 2, real Ledger).
- `tests/integration/test_authorship_score_rederivation.py` — sign+recompute round-trip; mismatch → `AuthorshipScoreDivergenceError`.
- `tests/regression/test_t023_score_inflation.py` — T-023 defense; LLM-assisted authoring caught by adversarial classifier.
- `tests/regression/test_t024_enterprise_delegation_upward.py` — T-024 enterprise N=5 DELEGATING ceiling on shared templates.
- `tests/integration/test_template_provenance_hash_binding.py` — template version drift detected at re-derivation.
- `tests/regression/test_cold_start_synthetic_corpus.py` — <30-day history fall-through.

## Open questions

1. Jaccard 0.85 + adversarial 0.8 thresholds — empirical calibration via Phase 01 user research.
2. `standard_action_corpus_v1` curation cadence — Foundation quarterly refresh vs event-driven.
3. Annual posture decay (-1 level at 12mo) — too aggressive vs too lenient pending Phase 03 telemetry.
4. Cross-principal authorship credit in Shared Household — does household member's authoring count toward another member's score.
5. Re-derivation cost on long Ledger histories — caching strategy to keep verify <50ms latency budget.
