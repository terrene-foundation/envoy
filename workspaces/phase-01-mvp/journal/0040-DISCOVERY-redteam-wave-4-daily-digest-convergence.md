# 0040 — DISCOVERY — /redteam Wave-4 daily digest convergence

**Date:** 2026-05-27
**Surface:** Wave-4 daily digest (commits `0a0f961..aa50ef1`; PR #44).
**Posture:** L5_DELEGATED.
**Verdict:** CONVERGED. ≥2 consecutive clean rounds (R2 + R3 by the
0-CRITICAL/0-HIGH bar; R3 fully clean across all severity tiers).

## What converged

Three /redteam rounds, two same-shard closure commits, six unique findings
fixed in-shard per `rules/autonomous-execution.md` Rule 4 (every finding
same-bug-class as another R1 finding, fits one shard budget).

- R1 surfaced 3 HIGH + 3 MED + 1 LOW across security / reviewer / spec-compliance.
- Closures at `fea758c` — T-018 banner suppression, record_success/record_open
  wiring, `event_only` event-gate via `_has_event`, backfill window math, receipt_hash
  docstring, `RedactedFieldRenderError` non-markdown drop path.
- R2 caught one secondary finding: `set_form_preference` was wired into
  `LowEngagementTracker` but had no production write-caller — the F-2 fix had
  delivered only the read-half. R2 also surfaced one spec LOW (silent on
  persistence semantics).
- Closures at `aa50ef1` — `DailyDigestService.set_form_preference` facade +
  `envoy digest form --set` CLI subcommand + spec persistence paragraph.
- R3 reproduced the closure verifications independently (two agents, both
  CLEAN) — receipts in `04-validate/round-3-wave-4-digest-convergence.md`
  cite every agent task ID + commit SHA.

## Why this matters

Two patterns surfaced worth tracking across future waves:

**1. Read-half / write-half asymmetry in user-preference features.** The R1
F-2 fix added the engagement tracker's `set_form_preference` (the WRITE) +
honored a stored preference in `select_form` (the READ). R2 caught that no
production caller ever set the preference — event_only was reachable only
from test code. The closure pattern: when a feature lands a "user picks X"
behavior, the read-side honor AND the write-side surface must both have
production call sites, not just the read. The orphan-detection §1 rule
generalizes to method granularity, and to the WRITE half of a
read-write pair.

**2. R2 code-review agent hit a session-rate-limit and did not report.** The
Round-3 reviewer agent (`ac63370631f0c666d`) was launched with R2-catch-up
mechanical sweeps explicitly in its prompt, and its CLEAN verdict carries
the R2 mechanical-sweep evidence forward. For future waves with parallel
agents on premium models: schedule code-review LAST in the wave-of-3 (or
run it on a different account) so a rate-limit truncation doesn't
silently drop a critical perspective.

## Receipts

- R1 task IDs: `a4cd428c62e479944` (security), `aabe719681bab9c81` (reviewer),
  `a1f386e1bbd141f4a` (analyst).
- R2 task IDs: `af21fb4f5d0888989` (security), `a2dbdd5af1f052df1`
  (reviewer-rate-limited), `a58dfae52cfb412e5` (analyst).
- R3 task IDs: `ac63370631f0c666d` (reviewer), `a68c784dc8a0c563d`
  (analyst+security combined).
- Convergence report: `workspaces/phase-01-mvp/04-validate/round-3-wave-4-digest-convergence.md`.
- Final mechanical: 1533 tests collect, 95 daily_digest tests green, ruff
  clean on every changed file. EC-3 (7-day fire battery) green at
  `tests/e2e/test_daily_digest_morning_delivery.py`.

## Carry-forward

None. PR #44 ready for merge. Next forest pick:
[[01-build-sequence]] § Wave-B caveated channels OR Wave-5 CLI packaging.

Links: [[0038-DISCOVERY-redteam-wave-4-channels-foundation-convergence]] (the
foundation-shard precedent for same-shard closures + Phase-02 deferrals),
[[0039-DISCOVERY-redteam-wave-a-channels-convergence]] (the Wave-A sibling
convergence — note that wave also closed 6 rounds vs this wave's 3, reflecting
the smaller blast radius of a digest-only shard).
