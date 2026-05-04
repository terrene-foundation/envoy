# Phase 01 MVP — Plans Index

**Document role:** Lean lookup table for every Phase 01 `/analyze` plan artifact under `02-plans/`. Per `rules/specs-authority.md` MUST Rule 1, this manifest is one-line descriptions only; the actual plan content lives in the linked files. `/todos` reads ALL four rows at planning time; `/implement` reads rows 01 + 02 + 03 per todo; `/redteam` reads row 04 each round.

**Date:** 2026-05-03 (shard 25 of /analyze; closure).
**Status:** Closed for /analyze; load-bearing for /todos.

---

| File                       | Domain         | Description                                                                                                                                                                                                                                                                                           |
| -------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `01-build-sequence.md`     | Build sequence | Topologically-sorted primitive build order (5 waves Group A→E); per-primitive scaffold step list; integration-test milestones; critical-path identification; per-shard implementation-cycle estimates in autonomous-execution sessions                                                                |
| `02-test-strategy.md`      | Test strategy  | 3-tier per `rules/testing.md` (Tier 1 unit, Tier 2 real-infrastructure integration, Tier 3 real-everything E2E); per-EC test surface; EC-4/EC-9 tampering battery; EC-5 Shamir 10-combinations + cross-tool interop; EC-7 8-channel × N=3 onboarding battery; EC-8 7-day cross-channel coherence test |
| `03-package-skeleton.md`   | Repo layout    | `envoy-agent` PyPI distribution + `envoy/` Python package layout; no `src/` indirection; `pyproject.toml` shape; `NOTICES` aggregation with LGPL-3.0+ python-telegram-bot disclosure; `.env.example` template; `tests/` 3-tier directory layout                                                       |
| `04-redteam-cycle-plan.md` | Redteam        | Phase 01 `/redteam` round structure; 9 mechanical sweeps; convergence gate (0 CRIT + 0 HIGH × 2 consecutive rounds); adversarial framing trigger when round 1 returns 0/0; spec-compliance verification protocol per `skills/spec-compliance/SKILL.md`; counter resets on any new finding or feature  |

---

## Cross-references

- Analysis: `01-analysis/_index.md`
- User flows: `03-user-flows/_index.md`
- Redteam rounds: `04-validate/round-{1,2,3,4}-implementation-comprehensive.md`
- Brief: `briefs/00-phase-01-mvp-scope.md`
