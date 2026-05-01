---
status: active
priority: medium
wave: phase-01-followup
source: workspaces/phase-00-alignment/04-validate/round-6-specs-comprehensive.md
created: 2026-05-01
---

# Phase-00 residual MEDs (deferred from R6)

Three MED-severity findings surfaced in `round-6-specs-comprehensive.md` that did NOT block Phase-00 convergence (CRIT + HIGH at zero × 2 consecutive rounds is the freeze gate; MED is informational). Captured here so Phase 01 picks them up — they touch specs that are FROZEN v1, so any edit re-triggers `rules/specs-authority.md` MUST Rule 5b (full-sibling re-derivation).

Disposition: file-as-todo (chosen over handle-as-encountered) because Phase 01 implementation may not directly touch all three affected specs, and "as-encountered" risks rotting them.

## MED-R6-1 — `original_parent_hash` / `merged_parent_hash` field documentation

**Source:** `round-6-specs-comprehensive.md` MED-R6-1 (= LOW-R5-1 escalated for symmetry)

**Gap:** `ledger-merge.md:25-33` algorithm references `entry.merged_parent_hash` (derived) + `entry.original_parent_hash` (signed). `ledger.md:13-34` Entry envelope schema declares only `parent_hash`, with no annotation of the derived/signed pair as post-merge fields. Algorithm reads consistently within `ledger-merge.md`, but the broader `ledger.md` audience reading the canonical schema will not reach the merge algorithm.

**Fix:** Add a `## Post-merge derived fields` subsection to `ledger.md` documenting:

- `original_parent_hash` (signed at write time, immutable)
- `merged_parent_hash` (derived during ledger-merge, may differ from `original_parent_hash` after merge)

**Why deferred:** documentation-only; algorithm self-references; no semantic ambiguity at the merge layer.

**Re-derivation cost:** edit to `ledger.md` re-triggers full-sibling redteam per MUST Rule 5b. Bundle with other ledger edits if Phase 01 produces them.

- [ ] Draft the `## Post-merge derived fields` block in `specs/ledger.md`
- [ ] Cross-ref from `specs/ledger-merge.md:25-33` to the new `ledger.md` subsection
- [ ] Run full-sibling specs-comprehensive redteam round (MUST Rule 5b)
- [ ] If 0 CRIT + 0 HIGH × 2 consecutive — re-freeze; else iterate

## MED-R6-2 — Phase 02 "CO validator accepts 100 benign + rejects 3 adversarial" sub-trace incomplete

**Source:** `round-6-specs-comprehensive.md` MED-R6-2

**Gap:** Phase 02 exit criterion at `acceptance-metrics.md:32` references "CO validator accepts 100 benign + rejects 3 adversarial." Test path declared in `skill-ingest.md:109-110` (`tests/integration/test_co_validator_100_benign_corpus.py` + `tests/integration/test_co_validator_3_adversarial_corpus.py`). Owning spec section `skill-ingest.md §CO validator` (`:36-46`) describes the 6-step validator + score thresholds (≥0.8 / 0.5–0.8 / <0.5) but does NOT cite the 100-benign + 3-adversarial corpus targets numerically.

**Fix:** Add a `### Corpus governance` subsection to `skill-ingest.md §CO validator` declaring:

- Corpus size targets (100 benign, 3 adversarial)
- Acceptance threshold (100% of benign cleared, 100% of adversarial caught)
- Where the corpora live (paths in repo)
- How they evolve (who curates, when)

**Why deferred:** acceptance criterion exists; test path declared; corpus governance is the missing link, but tests can be authored from the criterion alone.

**Re-derivation cost:** edit to `skill-ingest.md` re-triggers full-sibling redteam.

- [ ] Draft `### Corpus governance` in `specs/skill-ingest.md §CO validator`
- [ ] Decide corpus location (likely `tests/corpora/co-validator/{benign,adversarial}/`)
- [ ] Run full-sibling specs-comprehensive redteam
- [ ] Re-freeze on 0 CRIT + 0 HIGH × 2 consecutive

## MED-R6-3 — Phase 03 "per-dimension posture slider" still not spec-traced

**Source:** `round-6-specs-comprehensive.md` MED-R6-3 (= LOW-R5-2 escalated for symmetry)

**Gap:** `acceptance-metrics.md:36` lists "per-dimension posture slider" as Phase 03 exit criterion. `posture-ladder.md` (canonical 5-tier autonomy enum owner) describes only a global posture, not a per-dimension slider. `ledger.md:249` `posture_change` schema has a `dimension_scope` field (matching the slider concept) but `posture-ladder.md §Algorithm` (`:97-129`) implements only global ratchet, not per-dimension UX. Mechanical grep returns zero hits for "per-dimension posture slider" outside `acceptance-metrics.md:36`.

**Fix options (pick one in Phase 01):**

1. Promote `dimension_scope` from `ledger.md:249` to first-class in `posture-ladder.md` — add per-dimension slider state machine + UX
2. Drop "per-dimension posture slider" from `acceptance-metrics.md:36` if scope-trimmed in Phase 01 planning (decision: not all 5 dimensions need independent UX in v1)

**Why deferred:** Phase 03 exit criterion, not Phase 00 blocker. The acceptance gate exists; the owning spec primitive does not. Phase 01 architecture work will likely settle which option above is right.

**Re-derivation cost:** option 1 edits `posture-ladder.md` + maybe `ledger.md`; option 2 edits `acceptance-metrics.md`. Both re-trigger full-sibling redteam.

- [ ] Phase 01 architecture decision: promote `dimension_scope` to first-class OR scope-trim the criterion
- [ ] Apply chosen edit
- [ ] Run full-sibling specs-comprehensive redteam
- [ ] Re-freeze on 0 CRIT + 0 HIGH × 2 consecutive

## Trap

Per `rules/specs-authority.md` MUST Rule 5b: any spec edit re-triggers full-sibling re-derivation. Convergence is a snapshot, not permanent. Three sequential MED fixes = three full redteam rounds (or one round if bundled). Bundle if possible.
