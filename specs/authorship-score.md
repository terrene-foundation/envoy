# authorship-score

## Purpose

BET-12 structural enforcement primitive. Counts authored vs imported constraints across the 5-dim envelope; the count is the substrate the posture-ratchet gate consumes (`specs/posture-ladder.md` § State-transition contract).

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 §8 + §14.7 + §14.8`.
- **Threats mitigated:** T-023 score inflation, T-024 enterprise delegation-upward.
- **BETs tested:** BET-12 governance-primary-surface, BET-1 authorship.

## Score computation

Stored counters re-derived from the 5-dim envelope per § Re-derivation from the Ledger. The novelty + minimum-impact gates are pre-set on stored constraints by the input pipeline; T-02-30 implements the count-only recompute (the gates themselves are out of scope — see § Out of scope).

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

T-02-30 ships the count-only recompute at `envoy/authorship/score.py::recompute_authorship_counters`. The function gates `authored` on `c.authored` and forward-compat on `getattr(c, "novelty_check_passed", True)` / `getattr(c, "minimum_impact_check_passed", True)` so a Phase-04 dataclass extension automatically gates on the new flags. The in-memory `template_provenance` is a tuple-of-tuples (L-03 immutability); the wire shape via `AuthorshipCounters.to_dict()` is the spec-canonical list-of-dicts.

## Posture-ratchet gate

- **Personal mode:** N=3 for DELEGATING; N=5 for AUTONOMOUS.
- **Enterprise mode (cryptographically attested):** N=5 DELEGATING; AUTONOMOUS NOT reachable on shared templates.
- **Shared Household:** per-principal scores; household-wide actions require composition.
- **Annual revalidation:** posture decays 1 level at 12mo; user re-authors ≥1 to restore.

## Stored vs recomputed (M-05 fix from doc 02 R1)

`metadata.authorship_score.authored_count` signed at sign time. Runtime recomputes at verify. Mismatch → `AuthorshipScoreDivergenceError` audit alert.

## Error taxonomy

| Error                            | Trigger                                                                                     | User action                                                                     | Retry                 |
| -------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | --------------------- |
| `AuthorshipScoreDivergenceError` | `metadata.authorship_score.authored_count` signed value diverges from runtime re-derivation | Halt posture ratchet; investigate Ledger replay; surface to user as audit alert | Never (T-023 defense) |

## Cross-references

- specs/envelope-model.md — authored_constraints storage.
- specs/grant-moment.md — Approve+author path gates via this spec.
- specs/boundary-conversation.md — authorship nudge at novelty-failed constraint.
- specs/weekly-posture-review.md — score progression ritual.
- specs/posture-ladder.md — ratchet target enum (PSEUDO/TOOL/SUPERVISED/DELEGATING/AUTONOMOUS).
- specs/foundation-ops.md — Phase-04 classifier registry + standard-action corpus dependencies (out of Phase-01 scope; see § Out of scope below).
- specs/threat-model.md — T-023, T-024.

## Test location

- `tests/tier1/test_authorship_score_recompute_pure.py` — count-only recompute determinism, 5-dim canonical iteration order, construction-order invariance, immutability, round-trip dict, cold-start (T-02-30).

## Out of scope (Phase 01)

These behaviors are documented in this spec's intent but NOT implemented on main as of T-02-30:

- Novelty de-duplication algorithm (Tree-Jaccard + adversarial-wording classifier) — Phase 04 hardening; tracked in `workspaces/phase-01-mvp/todos/` for the Phase 02→04 handoff plan (`11-phase-02-handoff.md`).
- Minimum-impact dry-run against `standard_action_corpus_v1` — Phase 04; same handoff.
- Cold-start synthetic corpus — depends on Phase 04 minimum-impact.
- Annual posture decay (-1 level at 12mo) — Phase 03 telemetry calibration.
- Cross-principal authorship credit (Shared Household) — Phase 03.
