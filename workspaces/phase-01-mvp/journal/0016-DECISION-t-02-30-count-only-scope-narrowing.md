---
type: DECISION
date: 2026-05-07
created_at: 2026-05-10T00:00:00Z
author: agent
session_id: phase-01-wave-2-implement
session_turn: 1
project: phase-01-mvp
topic: T-02-30 ships count-only authorship recompute; Phase-04 algorithms removed from spec
phase: implement
tags:
  [
    authorship-score,
    scope-narrowing,
    spec-accuracy,
    autonomize-rule-1,
    sibling-spec-sweep,
    wave-2,
  ]
---

# DECISION: T-02-30 ships count-only Authorship Score recompute (commit `cd75810b`)

Wave 2 shard T-02-30 lands `recompute_authorship_counters(envelope, ledger_slice) -> AuthorshipCounters` as a pure deterministic function over the 5 canonical dimensions in fixed order (financial → operational → temporal → data_access → communication per `rules/terrene-naming.md`). The function counts authored constraints with `c.authored == True` and accumulates `imported_count` + ordered `template_provenance`.

The decision under discussion was NOT what the function does — that is mechanical. It was what the **spec** describes the function as doing. The pre-edit `specs/authorship-score.md` promised Phase-04 hardening: Tree-Jaccard novelty, adversarial-wording classifier ensemble, minimum-impact dry-run against `standard_action_corpus_v1`, classifier registry pin, cold-start synthetic corpus. None of those ship in T-02-30.

## What was decided

Per `/autonomize` Rule 1 (recommend optimal long-term root-cause fix with evidence; do not question-spam) AND `rules/spec-accuracy.md` Rule 5 (the spec MUST describe behavior shippable today on `main`):

- **Spec narrowed:** `specs/authorship-score.md` § Score computation trimmed to "count-only" pseudocode. § Error taxonomy reduced from 6 errors to 1 (`AuthorshipScoreDivergenceError` only). § Test location pinned to the one Tier-1 file shipped today. § Out of scope (Phase 01) added per `rules/spec-accuracy.md` Rule 3 Exception 1, naming the Phase-04 hardening surfaces explicitly.
- **`ledger_slice` parameter retained** as accepted-but-unused for forward-compat (Phase-04 minimum-impact algorithm consumer); permitted per `rules/zero-tolerance.md` Rule 6 because T-02-31 PostureGate is the in-flight consumer that shapes the callsite TODAY.
- **`getattr(c, "novelty_check_passed", True)` forward-compat** — flags don't exist on Phase-01 `AuthoredConstraint` schema (3 fields: `constraint_id`, `rule_ast`, `authored`). The default-True forward-compat lets Phase-04 dataclass extensions add the flags and gate on them WITHOUT touching the recompute body.

## Alternatives considered

| Alternative                                                            | Why rejected                                                                                                                                                                                                 |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Implement Phase-04 algorithms now (Tree-Jaccard + classifier ensemble) | Out of capacity budget per `rules/autonomous-execution.md` MUST Rule 1 — classifier registry alone is one shard; novelty corpus is another. Spec-vs-code drift would compound across multiple sessions.      |
| Keep spec as-is, ship count-only behind a feature flag                 | Violates `rules/spec-accuracy.md` Rule 1 (no aspirational spec text on main). Feature flags hide split-state framings (Rule 2).                                                                              |
| Delete `ledger_slice` parameter; re-add at Phase-04                    | T-02-31 PostureGate consumer would need a callsite migration in the same PR cycle that adds Phase-04 logic; net more churn. Iterative TODO permitted because the consumer is in-flight per Rule 6 exception. |

## Sibling-spec sweep findings

Per `rules/specs-authority.md` Rule 5b, the spec edit triggered a sibling-spec re-derivation. **Initial narrow-scope sweep at implementation time reported "0 edits needed"** — this was wrong. The reviewer caught the drift in gate review:

- `specs/envelope-model.md:138` — "novelty de-dup (Jaccard < 0.85 ...)" still cited Phase-04 algorithm.
- `specs/envelope-model.md:168-172` — Phase-04 errors (`NoveltyCheckFailedError`, `MinimumImpactCheckFailedError`) still in error taxonomy.
- `specs/envelope-model.md:186` — cross-ref pointed to "novelty + minimum-impact algorithms in detail".
- `specs/envelope-model.md:213` — "Jaccard 0.85 threshold" open question (Phase-04 calibration concern).
- `specs/posture-ladder.md:37` — "(one authored constraint survives novelty + minimum-impact)" cited Phase-04 gate.

All 5 edited in the same PR per `rules/autonomous-execution.md` Rule 4 (same-bug-class within shard budget).

## Consequences

- **Phase 02 / 04 ports:** Phase-04 will RE-add the trimmed sections via explicit dispatch (NOT `getattr` defaults) when the schema lands. The trimmed § Out of scope (Phase 01) section names the surfaces and points to the Phase-02→04 handoff plan.
- **Cross-spec terminology lock:** The 5-dimension canonical iteration order (financial → operational → temporal → data_access → communication) is now spec-locked across `authorship-score.md` + `envelope-model.md` + `posture-ladder.md`. Phase-04 dispatch contributors MUST preserve this order.
- **Audit-mode test gap:** Spec § Test location now pins exactly ONE Tier-1 file. The Tier-2 wiring tests for T-02-33 will RE-add citations when those tests land in the next wave; today they would be phantom citations per the deferred `12-spec-citation-hygiene.md` todo.

## For Discussion

1. The narrow-scope sibling-spec sweep at implementation time MISSED 5 cross-spec drift sites. Per `rules/specs-authority.md` Rule 5b, full-sibling re-derivation is mandatory on every spec edit — but the implementation agent's own self-report ("0 edits needed") is what the gate review had to override. Should `commands/implement` add a Rule-5b-specific "list every sibling spec touched + show the diff or `(unchanged)` per file" requirement to make the sibling sweep auditable, rather than relying on the reviewer to catch the silent miss?

2. The `ledger_slice` accepted-but-unused parameter (Rule 6 iterative TODO) creates a surface where the Phase-04 minimum-impact algorithm will plug in WITHOUT a callsite migration. But it also means today's `T-02-31` PostureGate caller passes a `ledger_slice` that the function ignores — a future maintainer reading the call could reasonably wonder why. Should the parameter be renamed `_phase04_ledger_slice` (underscore-prefix Python convention for "intentionally unused at this binding") so the unused-ness is visible at every callsite, or kept as-is so Phase-04 can rename without callsite churn?

3. The `getattr(c, "novelty_check_passed", True)` forward-compat default is **True** (so absent flags don't fail the gate). In Phase 04, when the schema adds the flags, what should the default be on a flag-stripped envelope received from a downgraded verifier? Per `rules/zero-tolerance.md` Rule 1 (no silent fallbacks), the right answer is probably to **fail closed** on flag-strip — but Phase-01 cannot enforce this because the schema doesn't yet have the flags. Should the spec's § Out of scope section explicitly mandate "Phase-04 hardens to fail-closed on absent flag"? (Counterfactual: had Phase-04 inherited Phase-01's default-True forward-compat unchanged, T-023 cross-version replay would silently inflate the authorship score for any downgraded-verifier envelope.)
