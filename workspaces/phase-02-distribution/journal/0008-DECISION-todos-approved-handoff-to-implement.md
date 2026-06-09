---
type: DECISION
date: 2026-06-08
project: phase-02-distribution
phase: todos
topic: /todos structural gate cleared — co-owner approved; handoff to /implement
tags: [todos, approval-gate, handoff, implement]
---

# 0008 — DECISION: /todos approved — handoff to /implement

The co-owner approved the Phase-02 plan at the `/todos` structural approval gate (in-session, 2026-06-08). The gate covered: the 47-todo plan (33 implementation shards + 14 test/acceptance), the value-ranked milestone ordering, the legal-gate-aware build sequence (Track A buildable now / Track B release-gated), and the value-ranked Wave-1 start (S1 + S4s + S8 over S10, with the named trade-off recorded).

## What was approved

- **Plan (what + why):** `todos/active/_index.md` + `01..07-*.md`. Per `rules/autonomous-execution.md`, the human approves the plan, not the execution; `/implement` now runs autonomously within this envelope.
- **Start order:** Wave 1 = S1 (WS-1 conformance harness, critical-path root), S4s (WS-6 store substrate, long-pole root), S8 (WS-4 steward quorum + registry, headline EC-02.7 root). S10 (WS-5) deferred to Wave 2 per the value-rank trade-off (worktree cap = 3; WS-4 EC-02.7 > WS-5 EC-02.8; WS-5 independent so loses nothing starting one wave later).

## /implement carry-forward obligations (recorded at approval)

- **Worktree orchestration:** Wave 1 compiling shards run worktree-isolated, waves of ≤3 (`rules/worktree-isolation.md`). WS-6 shards are SAME-class serialized (most touch `runtime.py`/the store) — do NOT worktree-parallelize them against each other.
- **Amend-at-launch (`specs-authority.md` Rule 5c):** re-resolve S4r's `runtime.py` sub-line citations at S4r launch; name S7v's split-target repo at S7v launch.
- **Global gates (binding, `_index.md` § Build vs Wire):** every wire todo passes the zero-mock-data grep; every reviewer-sweep acceptance has a mechanical grep backing.
- **Spec-first discipline:** new specs (`session-runtime.md`, etc.) land code-first per `specs-authority.md` Rule 5 / `spec-accuracy.md` Rule 5 as each shard ships.

## State at handoff

Working tree: all `/analyze` + `/todos` artifacts untracked (nothing committed yet — co-owner to authorize the commit). Phase-02 `/analyze` converged (R5 clean, `journal/0006`); `/todos` approved (this entry). Next: commit the planning artifacts (on co-owner go-ahead), then open `/implement` Wave 1.
