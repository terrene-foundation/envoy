---
type: DECISION
date: 2026-05-05
created_at: 2026-05-05T00:00:00Z
author: human
session_id: phase-01-mvp-todos-opening
session_turn: 1
project: envoy
topic: 4 human-owned dispositions resolved at /todos opening — timezone, heartbeat, boundary timing, verifier language
phase: todos
tags:
  [
    todos-opening,
    timezone-disposition,
    heartbeat-de-scope,
    boundary-conversation-timing,
    verifier-language,
    phase-02-handoff,
  ]
---

# 0005 — DECISION — /todos opening human dispositions (4 questions resolved)

## What was decided

At the /todos opening gate (2026-05-05 session start), the 4 open questions left by /analyze closure (`workspaces/phase-01-mvp/.session-notes` § "Open questions for the human") were resolved by the human as: **all defaults**.

| #   | Question                       | Disposition                                                                                                                                                |
| --- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Timezone HIGH (`journal/0003`) | **Option A** — UTC-only resets in Phase 01. Phase 02 entry checklist carries the IANA-timezone fix (Option B) per `journal/0003` § Why journal-worthy.     |
| 2   | Foundation Health Heartbeat    | **DE-SCOPE confirmed** — 5 stubs only in Phase 01 per shard 17 disposition. Phase 02 entry checklist owns the re-entry.                                    |
| 3   | Boundary Conversation timing   | **Both** the 15-min target AND the 25-min EC-1 ship gate per shard 8 disposition (c). 15min = aspirational user-experience target; 25min = pass-fail gate. |
| 4   | Independent verifier language  | **Python first** as Phase 01 EC-9 minimum + **Rust sibling stretch**. Ships in separate repo `terrene-foundation/envoy-ledger-verifier` per shard 7.       |

## Why this is journal-worthy

These 4 dispositions are LOAD-BEARING for the /todos plan structure:

1. **Disposition #1 (timezone Option A)** removes a frozen-spec edit and its MUST Rule 5b 37-sibling re-derivation cost from Phase 01. The cost moves to Phase 02 entry as a single ticket.
2. **Disposition #2 (heartbeat de-scope confirmed)** keeps shard 17's 5-stub partition (R2-H-02 fix) load-bearing for the build sequence. Without confirmation, shard 17 would have re-opened to a full-implementation deep-dive (~3 sessions of work).
3. **Disposition #3 (both 15+25min)** locks the boundary conversation EC-1 acceptance gate at 25min wall-clock with 15min as aspirational. The Tier 3 acceptance test (`tests/tier3/test_boundary_conversation_full_path.py`) MUST allocate ≤25min budget per session.
4. **Disposition #4 (Python first + Rust stretch)** disambiguates the side-channel verifier scope: the Phase 01 EC-9 acceptance gate is met by the Python verifier alone; Rust is value-add for the BET-3 source-isolation argument but does NOT block Phase 01 release.

## What it changes for /todos

- **Phase 02 entry checklist (capture todo)** — at minimum 3 carry-forward items: IANA timezone + Heartbeat re-entry + ConnectionVault third-party OAuth full integration. /todos creates a single Phase-02-handoff todo capturing all three with `journal/0003` and shard 17 cited.
- **Verifier side-channel todos** — split into "Python verifier (gates EC-9; required)" and "Rust verifier (stretch; non-blocking)". Both are separate-repo work; the Rust track is parallel.
- **Boundary Conversation Tier 3 acceptance** — the test budget is 25min per N=3 session run, not 15min. The 15min aspirational is a UX-evaluation observation surfaced in /codify, not a /redteam pass-fail gate.

## Alternatives considered

For #1 (timezone): Option B (IANA timezone field added to `EffectiveEnvelope.financial`) was the alternative. Rejected on cost (3-session MUST Rule 5b sweep across 37 frozen specs) when Option A is acceptable per `journal/0003` § "What it changes for downstream shards" (no EC-1..EC-9 acceptance gate breaks under Option A; only UX surprise for non-UTC users).

For #4 (Rust verifier): Option C (Rust verifier blocking Phase 01) was the alternative. Rejected because Phase 01 thesis (per `briefs/00-phase-01-mvp-scope.md`) is pure-Python runtime; introducing Rust into the EC-9 gate widens Phase 01 scope into Phase 02 territory.

## For Discussion

1. **Counterfactual #1**: If the human had selected Option B for the timezone, /todos would have surfaced a 3-session pre-implement spec-edit todo (`Add per_day_ceiling_timezone field to EnvelopeConfig.financial; re-derive 36 sibling specs`). What's the right escape hatch if Phase 02 entry confirms Option B is needed urgently — re-open Phase 01 or add the field as a non-breaking spec extension? The MUST Rule 5b sweep cost is the same either way; the question is whether Phase 02 schedule absorbs it cleanly.

2. **Specific data**: The Rust verifier stretch has zero impact on Phase 01 EC-9 acceptance (Python alone meets it). However, BET-3 (source-isolation argument as falsifiability surface) is materially STRONGER with two-language verification. Should the Rust stretch promote to "must-ship before BET-3 is publicly evaluated" even though it's not in Phase 01? Concretely: if Phase 01 ships with only the Python verifier and BET-3 is challenged by an external reviewer pre-Phase-02, do we have a credible defense?

3. **Methodology**: The 4 questions were enumerated in `.session-notes` so the next session could resolve them in one prompt. This worked — disposition took one user turn. Should `/wrapup` always pin "open questions for the human" in `.session-notes` as a class-level discipline, or is this Phase 01-specific because the /analyze closure was unusually decision-heavy?

## Consequences

- **Immediate**: 4 dispositions seed the todo structure (group 0 = pre-implement clarifications + Phase 02 handoff capture).
- **Short-term**: All 12 MED carry-forward items are convertible to todos without further human input.
- **Phase 02**: 3 carry-forward items (timezone, heartbeat, OAuth) bundled into Phase 02 entry checklist; one DECISION journal entry at Phase 02 opening will reference this entry.

## Follow-up actions

- [x] Convert the 4 dispositions into todo metadata (Phase 02 entry checklist todo + verifier-language split + boundary 25min budget pin).
- [ ] Confirm at /redteam (Phase 01 implementation rounds) that the 25min budget is being honored.
- [ ] Carry timezone Option A → Option B fix into Phase 02 entry checklist.

## Cross-references

- Open questions: `workspaces/phase-01-mvp/.session-notes` § "Open questions for the human"
- Timezone gap: `workspaces/phase-01-mvp/journal/0003-GAP-budget-ceiling-timezone.md`
- Shard 17 (heartbeat): `workspaces/phase-01-mvp/01-analysis/17-foundation-health-heartbeat-decision.md`
- Shard 7 (verifier): `workspaces/phase-01-mvp/01-analysis/07-independent-verifier-design.md`
- Shard 8 (boundary timing): `workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md` § 7
- Brief: `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md` § Surfaces
- Spec authority: `.claude/rules/specs-authority.md` MUST Rule 5b
