---
type: CONNECTION
date: 2026-05-03
created_at: 2026-05-03T00:00:00Z
author: agent
session_id: phase-01-mvp-shard-25
session_turn: 1
project: envoy
topic: /analyze closure — patterns surfaced across 25 shards that /todos and /implement must inherit
phase: analyze
tags:
  [
    analyze-closure,
    sharding,
    redteam,
    adversarial-trigger,
    cross-shard-consistency,
    freshness-gate,
    med-carry-forward,
    todos-handoff,
  ]
---

# 0004 — CONNECTION — /analyze to /todos handoff

## The connection

Phase 01 `/analyze` ran 25 shards across 7 waves (A=7 / B=3 / C=2 / D=3 / E=1 / F=3 / G=4 redteam) over 2 sessions. EC-6 (the redteam cycle gate) MET on round 4. Five non-obvious patterns surfaced that `/todos` and `/implement` must inherit; this entry is the bridge.

The connection is that the 25-shard /analyze produced a corpus (17 analysis docs + 4 plans + 8 user flows + 4 redteam rounds + 4 journal entries + 2 additive specs) that is **mechanically auditable** — every claim cites a path + section, every primitive has a §7 ambiguity inventory, every redteam round re-derives from scratch. The handoff to `/todos` is therefore not a paraphrase of findings; it is a set of pre-pinned mechanical operations the `/todos` planner can execute directly. The trap is treating the corpus as discursive analysis rather than a query surface.

## Pattern 1 — Sharding scaled cleanly

The 25-shard /analyze respected the per-session capacity budget (`rules/autonomous-execution.md` § Per-Session Capacity Budget) for every shard. Maximum-parallelization waves (A=7, B=3, C=2, D=3, F=3, G=4 redteam) were the empirically optimal sequencing — each wave committed before the next launched, surfacing cross-shard invariants between waves rather than within waves.

**Empirical evidence:** shard 9 (Authorship Score) surfaced a JCS-canonical-order invariant for shard 4 (Envelope compiler) that ONLY became visible when shard 9 deep-dived into deterministic-replay scoring. Had shards 4 + 9 been merged into one shard, the invariant would have been buried in the prose; sharding turned it into an explicit cross-shard finding (per `01-analysis/01-shard-plan.md` wave-B headline).

**Implication for /todos:** Plan implementation in shards of similar scope (~1 analysis doc + ~5–10 invariants per todo). Resist the temptation to merge "obviously related" todos.

## Pattern 2 — Adversarial round-2 trigger fired exactly as designed

Round 1 returned 0 CRIT + 0 HIGH (clean). Per `02-plans/04-redteam-cycle-plan.md` § 3, the "round-1-too-clean" trigger MANDATED round 2 with adversarial framing on shards 4 + 5 + 17 (the three shards round 1 had not stress-tested). Round 2 surfaced **2 HIGH findings** (R2-H-01 algorithm_id wire shape + R2-H-02 heartbeat stub partition) that round 1's mechanical sweeps had missed. Both fixed in commit `f690cb0`; round 3 + 4 verified clean.

The trigger's structural justification (per `02-plans/04-redteam-cycle-plan.md` § 3.3) is vindicated: a 0/0 round-1 result is a signal of under-audit, not over-quality. Without the trigger, both R2-H findings would have shipped to /implement; both would have compounded across every downstream record-persistence and heartbeat emit-site primitive.

**Implication for /todos:** Carry the same pattern forward. When `/redteam` rounds 1+ at /implement-time return 0/0 quickly, run an adversarial pass on the shard or todo that looks "too clean."

## Pattern 3 — Cross-shard wire-shape consistency is the recurring failure pattern

Round 2 caught algorithm_id wire-shape mismatch across shards 5 + 6 + 7 (Trust store + Ledger + Verifier all referenced the field but with subtly-different shapes). Round 3 caught a residual 4-key vs 3-key wire form in `specs/independent-verifier.md` line 35 vs shard 6's segment-boundary structure (R3-M-02; not yet reconciled).

The same pattern recurred at three levels: between sibling primitives (R2-H-01), between an additive spec and the primitive it derived from (R3-M-02), and between the package-skeleton plan and the source primitive shard (R1-M-01 11-subcommand drift).

**Implication for /implement:** Apply per-field wire-shape sweeps continuously. Every time a primitive references a field that another primitive also references, grep both surfaces and assert byte-equivalence at the wire layer. This is `rules/security.md` § Multi-Site Kwarg Plumbing applied to data shapes, not just kwargs.

## Pattern 4 — The freshness gate methodology was load-bearing

`journal/0001` and `journal/0002` established a "re-check upstream every shard" discipline. Shard 3 alone surfaced 12-of-13 ISS closures since the Phase 00 baseline (#594..#606 mostly closed Apr 24–26). The freshness gate was re-applied at shard 19 (pipx distribution), at every redteam round, and at this closure shard.

**Empirical evidence:** without the gate, shard 6's TieredAuditDispatcher analysis would have planned around the OPEN status of #596 — but the gate confirmed at HEAD that #596 IS still OPEN, validating the sunset clause Envoy-new-code path. Shard 13's chat-completion HOLD survives only because the gate confirmed the legacy provider chat path still EXISTS at upstream HEAD.

**Implication for /todos and /implement:** Adopt the same per-session freshness discipline. Before consuming any upstream-claimed pre-condition, re-derive against `gh issue view` + the upstream source at HEAD. The cost is one tool call; the failure mode without it is an entire shard built on a stale assumption.

## Pattern 5 — The 12 MED carry-forward is the /todos planning baseline

Each MED in the redteam carry-forward (R1-M-01..M-05 + R2-M-01..M-05 + R3-M-01..M-02) maps to a specific edit at a specific file with a specific rule citation. The `/todos` planner can mechanically expand the 12 items into 12+ todos without re-deriving the analysis.

Examples:

- R1-M-04 → "Add §5.1 tenant-isolation consolidated rule to `02-plans/03-package-skeleton.md`" (cites `rules/tenant-isolation.md` Rules 1+2)
- R1-M-05 → "Add `envoy/observability/` to `02-plans/03-package-skeleton.md` §2 with `metrics.py` + `tracing.py`" (cites `rules/observability.md`)
- R3-M-02 → "Reconcile 4-key vs 3-key wire form at `specs/independent-verifier.md` line 35 vs shard 6 segment-boundary"

**Implication for /todos:** Open the round-1 + round-2 + round-3 + round-4 docs at planning time and convert MED carry-forward to todos directly. Do NOT re-derive; cite the audit docs by path + line.

## Bridges to prior journal entries

- `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` established "cite Phase 00, never paraphrase" — this entry extends to "cite shards by NN, never paraphrase" for the /todos handoff.
- `journal/0002-DISCOVERY-upstream-readiness-improved.md` established the freshness-gate methodology — Pattern 4 generalizes it.
- `journal/0003-GAP-budget-ceiling-timezone.md` established the timezone HIGH escalation — surfaced again here as the primary open question for the human at /todos opening (it is the only HIGH that does NOT have an automatic disposition).

## For Discussion

1. **Did the 25-shard plan over- or under-shard?** Empirically, the per-shard capacity budget held for every shard — but 7 of the 25 shards (the redteam rounds + closure + objectives) were lighter-weight than the primitive deep-dives. Counterfactual: would consolidating the 4 redteam rounds into 2 deeper rounds have surfaced fewer or more findings? Round 1 was 0/0 at 10 findings; round 2 was 2 HIGH + further findings; rounds 3 + 4 were clean. The 4-round structure surfaced the R3-M-02 4-key/3-key residual that a 2-round structure would likely have missed.
2. **The adversarial trigger surfaced 2 HIGHs; without it, /implement would have committed both.** Should the adversarial trigger be MANDATORY for ALL /redteam phases (analyze + implement + codify), or only at /redteam? The trigger's cost is one extra round; the failure mode without it is HIGH findings shipping. The argument against universal application is that adversarial framing on a fast feedback loop (e.g., a small /implement todo) may be heavy-handed; the argument for is that the cost asymmetry favors over-auditing.
3. **The 12 MED carry-forward is significant.** Is the /todos planner equipped to handle them, or should some be promoted to /implement-time fix-immediately scope per `rules/autonomous-execution.md` MUST Rule 4 (same-bug-class fix-immediately)? Specifically R1-M-01 (11-subcommand drift), R1-M-04 (consolidated tenant-isolation rule), and R1-M-05 (envoy/observability/) are package-skeleton edits that any single /implement session can land in one shard — they could be addressed BEFORE /todos opens its first task.

## Consequences

- **Immediate:** The 5 closure deliverables (3 indexes + .session-notes + this journal entry) are the entry surface for `/todos`. The next session opens by reading them in order.
- **Short-term:** The 12 MED carry-forward + the timezone HIGH human decision are the first 13 items the /todos planner addresses.
- **Phase 02:** The R3-M-02 4-key/3-key residual + the Foundation Health Heartbeat de-scope confirmation + the Connection Vault third-party-OAuth deferral are the Phase 02 entry-checklist items inherited from Phase 01 /analyze.

## Follow-up actions

- [ ] /todos: address the 12 MED carry-forward + the timezone HIGH human decision before opening any implementation todo.
- [ ] /todos: confirm the 4 open questions in `.session-notes` § "Open questions for the human" before sequencing implementation.
- [ ] /implement: apply Pattern 3 (per-field wire-shape sweeps) continuously, especially at primitive-to-primitive integration points.
- [ ] /implement: apply Pattern 4 (per-session freshness gate) before consuming any upstream pre-condition.
- [ ] /redteam (at /implement-time): apply Pattern 2 (adversarial trigger on 0/0 rounds) verbatim from `02-plans/04-redteam-cycle-plan.md` § 3.

## Cross-references

- /analyze closure: `workspaces/phase-01-mvp/01-analysis/_index.md` + `02-plans/_index.md` + `03-user-flows/_index.md`
- Redteam history: `workspaces/phase-01-mvp/04-validate/round-{1,2,3,4}-implementation-comprehensive.md`
- Prior journal: `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` + `0002-DISCOVERY-upstream-readiness-improved.md` + `0003-GAP-budget-ceiling-timezone.md`
- Capacity rule: `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget
- Spec rule: `.claude/rules/specs-authority.md` MUST Rules 1 + 5b
