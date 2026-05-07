---
type: DECISION
date: 2026-05-07
created_at: 2026-05-07T05:35:00Z
author: agent
session_id: redteam-round-2
session_turn: 1
project: phase-01-mvp
topic: spec § Test location phantom citations deferred to next /todos cycle
phase: redteam
tags:
  [
    spec-accuracy,
    phantom-citations,
    autonomous-execution-rule-4-bounded-budget,
    deferral,
  ]
---

# DECISION: ~50 spec § Test location phantom citations deferred to next /todos as new HIGH-class todo

## Finding

Round 2's testing-specialist deep-dive re-derived test coverage and
mapped every spec § Test location citation to actual files in `tests/`.
Result:

| Spec file                                | Cited test paths                                         | Files that exist on `main`                                                                 |
| ---------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `specs/shamir-recovery.md` (lines 77-84) | 8 paths under `tests/integration/` + `tests/regression/` | 0 (`tests/integration/` has only legacy `.js` files)                                       |
| `specs/trust-vault.md` (lines 75-92)     | 18 paths                                                 | 0                                                                                          |
| `specs/ledger.md` (lines 620-637)        | 17 paths                                                 | 1 (`tests/regression/test_haltedbyrollback_record_minted_on_rollback.py` — landed Round 1) |

**Total: ~50 phantom citations across 3 specs.** Per
`rules/spec-accuracy.md` Rule 1 ("every citation MUST resolve against
working code... phantom citations are CRITICAL"), this is a
CRITICAL-class spec hygiene gap.

## Why deferred (vs fix-immediately per Rule 4)

`rules/autonomous-execution.md` MUST Rule 4 (fix-immediately when
same-bug-class within shard budget) is **bounded by the shard budget**:

> If the surfaced gap exceeds ≤500 LOC load-bearing / ≤5–10 invariants
> / ≤3–4 call-graph hops, filing the follow-up issue IS the correct
> disposition — the gap is a new shard, not a continuation of the
> current one.

Audit of the budget:

- **3 spec files × ~17 citations each = ~51 invariants** to re-derive.
  Each citation needs an independent disposition decision: (a) delete
  (test was never planned), (b) reword to "scheduled in T-NN-NN"
  with explicit phase tag (per `rules/spec-accuracy.md` Exception 3
  "[reserved for future work]"), or (c) keep when test lands. The
  decision depends on the wave-2 / wave-4 / wave-7 todo state.
- **Sibling-spec re-derivation per `rules/specs-authority.md` Rule 5b**
  is mandatory: editing `specs/shamir-recovery.md` § Test location
  triggers a sweep of every other spec that cross-references the
  affected tests. This expands the invariant count further.
- **Cross-cutting concern**: many cited tests are scheduled in
  `todos/active/02-wave-2-authorship-shamir-boundary.md` (T-02-37
  Shamir Tier 2 + 10-combo reconstruct), `08-tests-tier3-acceptance.md`,
  `09-tests-regression.md`. The right-time for spec hygiene is
  AFTER /todos has classified each citation as planned-vs-unplanned;
  doing it inside this redteam-round shard would re-litigate the
  /todos disposition.

## Disposition: new HIGH-class todo

Filed at `workspaces/phase-01-mvp/todos/active/12-spec-citation-hygiene.md`.
Per `rules/zero-tolerance.md` Rule 1b legitimate-deferral protocol:

1. ✅ **Runtime-safety proof**: phantom citations are spec-prose drift,
   not runtime defects. `pytest --collect-only` exits 0 cleanly; the
   suite's 462 passing tests cover the actually-shipped Phase-01
   surface. The drift is documentation hygiene, not security exposure.
2. ✅ **Tracking todo**: filed at the path above with explicit
   acceptance criteria.
3. ✅ **04-validate report link**: `round-2-implement-redteam.md` § 2.3
   links to this journal entry and the new todo.
4. **User-on-the-loop**: this DECISION is the human-visible record;
   user can override "fix immediately" at any subsequent session by
   moving the todo into the active wave.

## Why this isn't a R1c "pre-existing" silent dismissal

Per `rules/zero-tolerance.md` Rule 1c, "pre-existing" claims need
SHA-grounding. Provenance:

- `specs/shamir-recovery.md` § Test location entries are present in
  HEAD as of `c4e0ada` (current main, 2026-05-07).
- `git blame specs/shamir-recovery.md | grep -E '^[a-f0-9]+.*tests/'`
  shows these lines were authored at /analyze time (commit `7faf06fd`,
  2026-04-26 — "feat(phase-01-T-01-01): /analyze deliverables").
- Today's Round 2 session's first tool call: 2026-05-07T05:00:00Z.
  Authoring is 11 days before session start. → CLAIM GROUNDED.

The deferral is NOT "pre-existing, out of scope" silent dismissal. It
is a budget-bounded shard-split decision with a tracking todo and an
explicit re-disposition protocol.

## Alternatives considered

1. **Fix-immediately in this shard** — rejected per Rule 4 bounded-budget
   clause. The 3-spec re-derivation + sibling-sweep would balloon the
   shard to ~50 invariants × spec-by-spec disposition decisions. Test
   count delta would be 0 (this is a docs/hygiene fix); complexity
   delta is high. Splitting it out is the right structural move.
2. **Delete all § Test location sections** — rejected. Some citations
   are correct (e.g., `tests/regression/test_haltedbyrollback_record_minted_on_rollback.py`
   exists). Wholesale delete loses the load-bearing entries. Per-citation
   triage is the right protocol.
3. **Leave the spec lines, file no todo** — REJECTED. That IS silent
   dismissal per Rule 1c. The new todo is the structural defense
   against the gap drifting out of attention.

## Consequences

- Next /todos cycle picks up `12-spec-citation-hygiene.md` as a
  HIGH-class workstream.
- `commands/redteam` will continue to surface this gap on every
  Round 1 mechanical sweep (`rules/spec-accuracy.md` audit protocol's
  Rule-1 grep) until the todo lands.
- The deferral does NOT block /redteam Round 2 + Round 3 convergence
  for the wave-2 shipped surface — convergence is per-shard, not
  per-project. Phase 01 has more shards landing; each closes its own
  acceptance window.

## For Discussion

1. Counterfactual: had Round 2's analyst NOT had the spec-citation
   sandbox-tooling gap (Cov-1..8), would the phantom-citation issue
   still have been caught? (Yes — `rules/spec-accuracy.md` Rule 1's
   audit-protocol grep `rg '...phase-?1.*phase-?2|TBD|...'` runs in
   /redteam and would have hit the citations on a different sweep
   axis. The sandbox gap was actually the trigger that surfaced this
   sooner.)

2. Should `commands/redteam` prepend the spec-citation grep audit
   (the bash one-liner at `rules/spec-accuracy.md` § Audit Protocol)
   to **every** /redteam round, not just the round that runs the
   `skills/spec-compliance/SKILL.md` deep-dive? (The bash check is
   ~1 second; running it every round catches drift earlier in the
   wave's lifecycle.)

3. Specifically for the 50 deferred citations — what's the right
   default disposition rule? Three candidates: (a) all citations
   pointing to non-existent files MUST be re-tagged as
   `[reserved for future work]` per `rules/spec-accuracy.md`
   Exception 3 OR deleted; (b) citations whose tests are mapped to
   open `todos/active/` workstreams may be reworded with
   `(scheduled in T-NN-NN)` annotations per Exception 1
   ("Out of scope" / future-work disposition); (c) decision per
   spec, no global rule. The choice affects whether `/codify`
   should encode the policy as a new rule or leave it
   project-specific.
