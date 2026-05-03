---
type: GAP
date: 2026-05-03
created_at: 2026-05-03T00:00:00Z
author: agent
session_id: phase-01-mvp-wave-D
session_turn: 1
project: envoy
topic: per_day_ceiling_microdollars timezone basis unspecified in budget-tracker spec
phase: analyze
tags:
  [spec-gap, budget-tracker, envelope-model, MUST-rule-5b, shard-22-escalation]
---

# 0003 — GAP — Budget ceiling timezone basis unspecified

## What was discovered

Shard 12 (Budget tracker) surfaced the **first HIGH-severity frozen-spec ambiguity** in /analyze: `specs/budget-tracker.md` § Ceilings (lines 17–23) names `per_day_ceiling_microdollars` and `per_month_ceiling_microdollars` but does NOT specify the timezone basis for the reset boundary. Open Question 5 in the spec gestures at the issue but does not resolve it.

The two viable dispositions:

- **Option A (UTC-only)** — Phase 01 minimum. Resets fire at UTC midnight regardless of user location. Produces a noon-local-time reset for users in non-UTC timezones (visible UX surprise — e.g., a user in Singapore sees their daily budget reset at 8 AM local time). Phase 02 ticket carries the user-local-time fix.
- **Option B (user-local-time IANA timezone)** — Phase 01 ideal. Adds `per_day_ceiling_timezone: str` field to `EffectiveEnvelope.financial` in `specs/envelope-model.md`. Reset fires at the user's local midnight per their declared timezone. Matches user mental models.

## Why this is journal-worthy

Option B requires **EDITING `specs/envelope-model.md`** — a frozen spec. Per `rules/specs-authority.md` MUST Rule 5b, any edit triggers the **full-sibling re-derivation across all 37 frozen specs** (6 historical convergence rounds in Phase 00). The cost of Option B is therefore not just the field addition but the multi-session redteam-convergence work to confirm no cross-spec drift in 36 sibling specs.

Option A is the Phase 01 zero-cost disposition; the timezone-correctness regression is observable at user level but does not break any Phase 01 EC-1..EC-9 acceptance gate (budget tracking still works, just on a non-user-local clock).

## What it changes for downstream shards

1. **Shard 22 (spec gap analysis)** is the venue for this disposition decision. The shard 22 doc must enumerate Option A vs Option B with their costs, recommend, and surface the decision to the human at the /analyze closure gate (shard 25). This is precisely what shard 22 is for per `01-shard-plan.md` §4.
2. **Wave D and remaining shards continue without blocking.** The shard 12 doc captures the ambiguity in §7 + recommends Option A as the Phase 01-safe default. Other primitives (Daily Digest, Channel adapters, etc.) do not depend on the timezone basis.
3. **If the human selects Option B at shard 22**, the MUST Rule 5b 37-sibling sweep adds ~1–3 sessions to /analyze. This is a known cost; do not surprise the human with it.

## Why this is GAP, not RISK or DECISION

Per `rules/journal.md` § Entry Types:

- **GAP** = "Missing data, untested assumptions, unresolved questions" ← matches: spec is silent on timezone basis
- DECISION would be premature; the human owns this disposition at shard 22
- RISK would imply the gap creates a vulnerability; it doesn't (worst case is UX surprise)

## For Discussion

1. **Counterfactual**: If the user in Singapore sees their daily budget reset at 8 AM local time (Option A), does that break BET-12 (governance-primary-surface palatability)? Specifically: does a user who hits the budget ceiling at 9 AM local-time (right after the reset they didn't notice) experience the Grant Moment as agency or as friction? This is empirically falsifiable in EC-7 8-channel onboarding, but not at MVP cohort scale (N=24 onboardings).

2. **Specific data**: The 6-round Phase 00 redteam convergence on `specs/envelope-model.md` cost ~6 sessions. Adding a timezone field is a small addition, but the sweep cost is bounded by the spec's surface area, not by the size of the addition. A reasonable estimate is 2–3 sessions for the additive edit; if any sibling spec surfaces a HIGH cross-reference (e.g., `specs/ledger.md` audit-row timestamp encoding), that adds another round. Should shard 22's recommendation include a budget for Option B (3 sessions) vs Option A (0 sessions, Phase 02 deferred)?

3. **Methodology**: Shard 12's agent COMPLETED the analysis doc and escalated to shard 22 rather than halting per `01-shard-plan.md` §4 strict reading. This is the right behavior because the HIGH ambiguity has a Phase 01-acceptable disposition (Option A); halting would have stalled wave D for no benefit. Should §4 of the shard plan be amended to distinguish "STOP and convene MUST Rule 5b" (when no Phase 01-acceptable disposition exists) from "complete-and-escalate-to-shard-22" (when Option A is acceptable)?

## Cross-references

- Shard 12 doc: `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md` § 7 (frozen-spec ambiguity)
- Source spec: `specs/budget-tracker.md` § Ceilings + Open Question 5
- Affected sibling spec (if Option B): `specs/envelope-model.md` § financial dimension
- Sharding plan: `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` §4 failure-mode mitigations
- Spec authority rule: `.claude/rules/specs-authority.md` MUST Rule 5b
- Shard 22 (spec gap analysis): pending; this entry is its primary input
