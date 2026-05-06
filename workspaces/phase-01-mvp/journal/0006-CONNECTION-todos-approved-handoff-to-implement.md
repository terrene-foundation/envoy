---
type: CONNECTION
date: 2026-05-06
created_at: 2026-05-06T00:00:00Z
author: human
session_id: phase-01-mvp-todos-closure
session_turn: 1
project: envoy
topic: /todos structural gate passed — handoff from planning to implementation
phase: todos
tags: [todos-closure, approval-gate, implement-handoff, structural-gate]
---

# 0006 — CONNECTION — /todos approved; handoff to /implement

## The connection

Phase 01 /todos opened on 2026-05-05 with 4 human-disposition baselines and 12 MED carry-forward items, produced a 71-todo plan across 12 topical files (1 index + 11 grouped) at `workspaces/phase-01-mvp/todos/active/`, ran self-audit (mechanical sweeps confirmed 15/15 primitives, 9/9 ECs, 12/12 MEDs, 8/8 channel adapters, 13/13 cross-reference sections, 46 spec citations on 44 build todos), and was APPROVED by the human at /todos closure (2026-05-06).

The connection is that /todos is now CLOSED. The structural approval gate has passed. /implement may open and execute autonomously per `rules/autonomous-execution.md` § Structural vs Execution Gates: humans observe, do not block. Material scope changes during /implement (new primitives, dropped acceptance gates, EC reframing) re-trigger the structural gate.

## Why this is journal-worthy

The /todos approval gate is the second-most-important structural gate in the COC phase model (after release authorization). Recording it as a CONNECTION entry establishes:

1. **Audit trail** — the next session reads this entry and knows exactly which todos are sanctioned for /implement.
2. **Scope freeze** — anything not in the 71-todo set requires re-opening the /todos gate; this is the structural defense against scope mutation per `rules/specs-authority.md` MUST Rule 6.
3. **Resumability** — if a /implement session is interrupted, the next session reads the todo files + this entry + `_index.md` and resumes mid-wave without re-deriving the plan.

## What it changes for downstream

- **/implement** opens at `01-wave-1-foundation.md` (Wave 1 = 7 parallelizable foundation primitives).
- **Worktree isolation** mandated per `rules/agents.md` § "Worktree Isolation for Compiling Agents" for any todos that compile or run tests in parallel.
- **Per-package ownership coordination** mandated per `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination" — one agent owns the `pyproject.toml` + `__version__` + CHANGELOG bump for each parallel-worktree wave.
- **Freshness gate** per `journal/0001` Pattern 4 — re-check upstream `kailash-py` HEAD at the start of each /implement session.
- **Adversarial /redteam trigger** per `journal/0004` Pattern 2 — when /implement /redteam round 1 returns 0/0, MANDATORY adversarial pass.

## For Discussion

1. **Counterfactual**: If /todos had surfaced a primitive that was NOT in `02-plans/01-build-sequence.md`, would that retroactively invalidate `/analyze` closure? The build sequence frozen at /analyze shard 25 is the authority; /todos extends it via additive todos but cannot mutate it. Any /implement-time discovery of a missing primitive should re-open /analyze, not /todos. The 71-todo plan covers every primitive named in the build sequence; the test passed.

2. **Specific data**: The plan estimates ~11 wall-clock orchestrator sessions for Phase 01 implementation (per `02-plans/01-build-sequence.md` § 4.1 parallel scheduling), consistent with the 8–12 session thesis estimate. With autonomous execution multiplier (`rules/autonomous-execution.md` § "10x Throughput Multiplier"), this maps to ~80–120 human-day equivalent traditional execution. If /implement actually takes >15 sessions, that's a 35%+ overrun signal that the build sequence misjudged sharding; the next /redteam should examine which todos overflowed their capacity check.

3. **Methodology**: This is the second time in two phases (/analyze closure 2026-05-04 + /todos closure 2026-05-06) that the closure produced a manifest + a CONNECTION entry. Should this be canonized as the closure-discipline pattern for ALL phase commands, or is it Phase 01-specific because the plan complexity is unusually high? The cost is one entry per phase closure; the benefit is mechanical audit-trail consumability. Recommend canonizing.

## Consequences

- **Immediate**: /implement may open at the next session start. Wave 1 launches with 7 parallelizable primitives.
- **Short-term**: Wave-by-wave milestone gates per `02-plans/01-build-sequence.md` § 3 govern wave transitions. EC-1 acceptance (T-02-45 Boundary Conversation 25min × N=3) is the first major /redteam-gate.
- **Phase 02**: 7 Phase 02 entry-checklist items captured in `11-phase-02-handoff.md` are ready for Phase 02 opening.

## Follow-up actions

- [x] /todos closure: 71 todos in 12 files at `todos/active/` with this entry tying back to `journal/0005`.
- [ ] /implement: open at next session; read `_index.md` first; load Wave 1 file; pick first available todo by ID.
- [ ] /implement: apply Pattern 3 (per-field wire-shape sweeps) at every primitive-to-primitive integration point.
- [ ] /implement: apply Pattern 4 (per-session freshness gate) before consuming any upstream pre-condition.
- [ ] /redteam (at /implement-time): apply Pattern 2 (adversarial trigger on 0/0 rounds) per `02-plans/04-redteam-cycle-plan.md` § 3.

## Cross-references

- /todos manifest: `workspaces/phase-01-mvp/todos/active/_index.md`
- /todos opening dispositions: `workspaces/phase-01-mvp/journal/0005-DECISION-todos-opening-dispositions.md`
- /analyze closure: `workspaces/phase-01-mvp/journal/0004-CONNECTION-analyze-to-todos-handoff.md`
- Build sequence authority: `workspaces/phase-01-mvp/02-plans/01-build-sequence.md`
- Phase 02 handoff: `workspaces/phase-01-mvp/todos/active/11-phase-02-handoff.md`
- Autonomous execution rule: `.claude/rules/autonomous-execution.md`
- Specs authority: `.claude/rules/specs-authority.md`
