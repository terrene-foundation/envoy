---
type: DISCOVERY
date: 2026-05-24
created_at: 2026-05-24T20:35:00Z
author: agent
session_id: phase-01-codify-2026-05-24
session_turn: 2
project: phase-01-mvp
topic: Three meta-patterns surfaced during T-02-33 RT-1 + RT-2 convergence — generalizable across /redteam cycles
phase: codify
tags:
  - codify
  - discovery
  - redteam
  - meta-pattern
  - same-class-regression
  - lane-disagreement
  - audit-visibility
  - rt-1
  - rt-2
  - convergence
---

# DISCOVERY: Three generalizable patterns from T-02-33 RT-1 + RT-2 convergence

The T-02-33 envelope_edit pairing convergence cycle (PRs #23 → #25 → #26 → #27, 2 round-1 shards + 1 round-2 shard + 4 /redteam rounds, merged at `2264ae2`) surfaced three patterns that apply to ANY /redteam convergence cycle on a kailash-bound project — not envoy-specific. The patterns are recorded here as the durable inheritance surface; propagation upstream into the COC USE template is a human-gated `/sync rs` step (see companion `journal/0025-DECISION-codify-cycle-disposition.md` § Follow-up).

Each pattern is paired with: the literal evidence from this cycle, the rule it generalizes from, and the proposed upstream insertion point.

## Pattern 1: Same-class regression at the fix site

### What it is

When Round-N /redteam closes a HIGH finding via a fix-shard, Round-N+1 MUST specifically scan the NEW code introduced by the fix for **same-class regressions of the original finding**. Verifying the original site is fixed is necessary but not sufficient — the fix itself can reintroduce the same failure-mode class at a new code site.

### Evidence from this cycle

Round 1 F-3 (MED) was: "defensive `if envelope is None: raise` at Step 5b fires AFTER Step 5a's `posture_change` append; if Step 3e is dropped in a future refactor, the result is an orphan `posture_change` entry."

Shard 1 closed F-3 by removing the redundant Step 5b guard (Step 3e at line 933 already raises before any Ledger write).

**But Shard 1 ALSO added F-2 mutation invariants** (per Round 1 HIGH closure) — three invariant raises at lines 1033/1041/1049 in the same Step 5 region. The invariants fired AFTER Step 5a's `posture_change` append. On any invariant violation, the `posture_change` entry committed to the Ledger while the paired `envelope_edit` never appended — **structurally the SAME orphan-`posture_change` failure mode F-3 had named**, reintroduced at a new code site.

Round 2 Lane C (security-reviewer) caught this as R2-F1 HIGH:

> "This is structurally the SAME failure mode Round 1 F-3 named, reintroduced at a new site."

Round 2 Lane B (reviewer) **missed it** — dispositioned R2-F1 as "covered by F-001 issue #24" (Phase 03 Ledger transactional primitive). That disposition conflates bug classes: F-001 addresses TRANSIENT infrastructure failures between Step 5a and Step 5b; R2-F1 addresses APPLICATION-LEVEL invariant violations from code we wrote. Different root causes, different solutions.

Shard 3 (PR #27, merge `2264ae2`) closed R2-F1 by promoting the F-2 invariants from postconditions-of-Step-5a to PRECONDITIONS — on invariant violation, ZERO Ledger entries land (atomic application-level fail-closed). Cost: 1 round + 1 6-commit shard.

### Rule it generalizes from

`rules/autonomous-execution.md` MUST Rule 4 ("Fix-Immediately When Review Surfaces A Same-Class Gap Within Shard Budget") covers the FIX-NOW disposition once same-class is identified. **What's missing** is the upstream mandate that Round-N+1 audits MUST explicitly scan the fix site for same-class regressions.

### Proposed upstream insertion

Add to `.claude/commands/redteam.md` § "Convergence Criteria" (or `.claude/rules/agents.md` § "Quality Gates"):

> ### MUST: Round-N+1 Audits Scan Fix-Site for Same-Class Regressions
>
> When Round-N closes a HIGH or MED finding via a fix-shard, Round-N+1's gate-level reviewers MUST include a mechanical sweep that re-runs the original finding's detection probe AGAINST THE NEW CODE the fix introduced — not just against the original site. Verifying "the original site is fixed" is necessary but not sufficient. Reviewer prompts MUST include the explicit fix-site grep.
>
> **Why:** Round 1 closure can introduce the same failure-mode class at a new code site. The detection probe that caught the original finding will catch the regression IF it scans the fix site. Without the explicit mandate, parallel reviewers may disposition the regression as "covered by an open follow-up issue" (conflating bug classes) and the orchestrator may default to the lower-severity verdict.
>
> **Evidence:** T-02-33 RT-1 → RT-2 convergence — Round 1 F-3 closure (defensive guard removal) reintroduced the orphan-posture_change pattern at the new F-2 invariant raise sites. Lane C caught it as R2-F1 HIGH; Lane B missed it. Cost of the regression cycle: 1 full round + 1 6-commit follow-up shard.

## Pattern 2: Parallel-lane disagreement protocol

### What it is

When two parallel gate-level reviewers disagree on a finding's classification (CLEAN vs NOT CLEAN, MED vs HIGH, "covered by existing issue" vs "new finding"), the orchestrator MUST interrogate the disagreement on bug-class semantics. The disagreement IS the signal. Defaulting to the lower-severity lane's verdict is BLOCKED.

### Evidence from this cycle

Round 2 had three parallel lanes (testing-specialist + reviewer + security-reviewer):

- Lane A (testing-specialist): CLEAN — 605/605 tests, 6/6 Round 1 closures verified
- Lane B (reviewer): CLEAN — 11/11 mechanical sweeps PASS; noted R2-F1 inline as "covered by F-001 #24"
- Lane C (security-reviewer): **NOT CLEAN — 1 HIGH (R2-F1) + 1 MED + 1 LOW**

The orchestrator's tie-breaker reasoning (recorded in the post-Round-2 disposition message):

> "Lane C is right. Lane B's 'covered by F-001 #24' disposition conflates two distinct failure modes: F-001 (#24): transient infrastructure failures — solution is a transactional/compensating-entry Ledger primitive. R2-F1: application-level logic failures — solution is reordering: validate invariants as preconditions. They share the orphan-`posture_change` symptom but a Phase-03 Ledger-atomicity fix wouldn't catch R2-F1 because the raise interrupts the pairing flow BEFORE any compensating entry could fire."

The orchestrator picked Lane C's verdict, spawned Shard 3 per Rule 4, and the fix landed.

### Rule it generalizes from

`rules/agents.md` § "Quality Gates" requires reviewer + security-reviewer parallel dispatch but does not specify orchestrator adjudication when the lanes disagree.

### Proposed upstream insertion

Add to `.claude/rules/agents.md` § "Quality Gates":

> ### MUST: Adjudicate Lane Disagreements on Bug-Class Semantics
>
> When two or more parallel gate-level reviewers return divergent verdicts on the SAME finding (one reports CLEAN, another reports HIGH; or one classifies as MED, another as HIGH; or one disposes as "covered by existing issue", another as "new finding"), the orchestrator MUST:
>
> 1. Surface the disagreement explicitly in the next message (do not silently pick a lane)
> 2. Interrogate the disagreement on bug-class semantics: do the lanes agree on the symptom but disagree on the root cause? On the solution? On the affected blast radius?
> 3. Default to the HIGHER severity verdict when bug-class disagreement isn't resolvable from the lane outputs alone
> 4. If a follow-up issue exists that one lane cites as covering the finding, verify the issue's stated scope MATCHES the disagreed-on bug class — different root causes need different solutions
>
> Silent picking of the lower-severity verdict because it's cheaper to act on is BLOCKED.
>
> **Why:** Parallel lanes catch different failure-mode classes because they read code through different lenses (testing-specialist re-derives test coverage; reviewer scans mechanical sweeps + code judgment; security-reviewer threat-models). Disagreement frequently maps to a real bug-class distinction one lane missed. Resolving by lower-severity default reintroduces the failure mode.
>
> **Evidence:** T-02-33 RT-2 — Lane B (reviewer) returned CLEAN with R2-F1 noted as "covered by F-001 #24"; Lane C (security-reviewer) returned NOT CLEAN with R2-F1 HIGH. The orchestrator interrogated and picked Lane C — F-001 was the wrong bug class. Defaulting to Lane B would have shipped the regression for another full convergence cycle.

## Pattern 3: Audit-corpus visibility in worktree follow-ups

### What it is

When /redteam Round-N produces audit artifacts (Lane A/B/C write to `workspaces/<project>/04-validate/round-N-*-{date}.md`), those files land as **untracked files in the main checkout**. Worktree-isolated follow-up shards branched from `origin/main` cannot see them — the worktree is a fresh checkout that doesn't include the untracked working-tree state. Follow-up shards that cite audit artifact paths in their prompt encounter a `verify-resource-existence.md` MUST-1 failure on first read.

### Evidence from this cycle

Shard 2 (F-5 false-positive disposition) was prompted with a citation:

> "Round 1 audit doc: workspaces/phase-01-mvp/04-validate/round-1-security-audit-2026-05-24.md § F-5"

The Shard 2 agent's pre-flight check found the file absent in the worktree:

> "Audit doc existence check: `ls workspaces/phase-01-mvp/04-validate/round-1-security-audit-2026-05-24.md` → no such file"

Per `rules/verify-resource-existence.md` MUST-1 (existence check precedes permission debugging) and MUST-3 (default to delete-or-stub when threat target doesn't exist), the agent halted at zero commits and surfaced the gap to the orchestrator.

The orchestrator investigation found Lane A/B/C HAD written the files — but to the **main checkout**, as untracked. The chore commit `7598578` then committed the audit corpus, and a continuation agent rebased the worktree onto the new main and shipped the false-positive disposition (PR #26, merge `e89914b`).

Without the existence check, the Shard 2 agent might have proceeded against the prompt's embedded F-5 finding enumeration (the way Shard 1's agent did when facing the same gap) and shipped a phantom 250+ LOC schema-version-bump migration against a non-existent re-canonicalization path.

### Rule it generalizes from

`rules/worktree-isolation.md` MUST Rules 1-6 cover worktree setup, branch naming, deliverable verification, and parallel-launch limits — but do not address the audit-corpus visibility gap between Lane-produced artifacts (untracked in main) and worktree-isolated follow-up shards (don't see untracked files in main).

### Proposed upstream insertion

Add to `.claude/rules/worktree-isolation.md` (or `.claude/commands/redteam.md` § "Convergence"):

> ### MUST: Commit Audit Artifacts to Main Before Spawning Follow-Up Shards
>
> When /redteam Round-N's parallel lanes (testing-specialist + reviewer + security-reviewer) produce audit artifacts under `workspaces/<project>/04-validate/round-N-*-{date}.md`, the orchestrator MUST commit those files to main BEFORE spawning any worktree-isolated follow-up shard whose prompt cites the audit artifact paths.
>
> The pattern:
>
> 1. Round-N parallel lanes complete; audit artifacts land as untracked files in main checkout
> 2. Orchestrator commits the artifacts to main via a chore commit (audit corpus = durable receipts per `rules/verify-resource-existence.md` MUST-4)
> 3. Orchestrator THEN spawns follow-up shard agents in worktrees branched from the new main HEAD
> 4. Follow-up shards' worktrees include the committed audit corpus and pass their pre-flight existence checks
>
> Spawning a follow-up shard agent against an audit citation that hasn't been committed yet is BLOCKED — the shard's worktree won't see the citation; the shard either halts (per `verify-resource-existence.md` MUST-1) or proceeds against the prompt's embedded fallback content (which may be incomplete or stale).
>
> **Why:** Worktrees are fresh git checkouts from `origin/main`. Untracked files in the parent checkout are NOT propagated to worktrees. The audit corpus → worktree-shard chain breaks silently unless the corpus is committed first.
>
> **Evidence:** T-02-33 RT-1 → Shard 2 — agent halted at zero commits when audit doc was absent in worktree; orchestrator chore-committed at `7598578`; continuation agent rebased + shipped PR #26. Shard 1 faced the same gap earlier in the chain and proceeded against the prompt's embedded enumeration as fallback — worked because the enumeration was complete, but the practice is fragile.

## How these patterns interlock

The three patterns are not independent — they form a defense-in-depth around `/redteam` convergence quality:

1. **Pattern 3 (audit visibility)** ensures follow-up shards see the artifacts the previous round produced — without this, they operate against incomplete framings.
2. **Pattern 1 (same-class at fix site)** ensures Round-N+1 doesn't certify the fix shipped without verifying the fix didn't reintroduce the same failure-mode class.
3. **Pattern 2 (lane disagreement adjudication)** ensures the orchestrator's role at gate-level review is to interrogate disagreements, not paper over them with lower-severity defaults.

A `/redteam` convergence cycle missing any one of these three patterns is structurally fragile: it ships orphan ledger entries (Pattern 1 gap), or ships against incomplete audit framings (Pattern 3 gap), or ships with one lane silently overruling another (Pattern 2 gap).

## Why these are journal DISCOVERY rather than rule updates

Per `journal/0025-DECISION-codify-cycle-disposition.md`: envoy is a downstream consumer repo per `rules/artifact-flow.md`; `/codify` stays local. The `.claude/{rules,agents,commands}` directories are upstream-managed (kailash-coc-claude-rs USE template); local edits would be overwritten on next `/sync`. The natural propagation path is upstream via a future `/sync rs` cycle — at which point the user can incorporate these three patterns into the canonical rule set.

The journal entry IS the durable receipt. The next session — and any future upstream proposal — can read it as user-anchored evidence per `rules/value-prioritization.md` MUST Rule 1 (journal DECISION entries are a valid user-anchored source).

## For Discussion

1. **Counterfactual on Pattern 1**: had Shard 1's gate-level review (reviewer + security-reviewer parallel dispatch) included an explicit "grep the fix site for same-class patterns" mechanical sweep, would R2-F1 have been caught BEFORE Shard 1's merge — collapsing the Round 2 → Shard 3 cycle into a single Shard 1 amendment? The marginal cost of the sweep is one extra grep per reviewer; the marginal value is one prevented regression cycle. Net: clear positive.

2. **Data-anchored on Pattern 2**: across the 4 /redteam rounds, Lane B (reviewer) and Lane C (security-reviewer) disagreed exactly once (Round 2 on R2-F1) — and the disagreement was load-bearing. A protocol mandating that orchestrators interrogate disagreements would have negligible cost in the agree case (no extra work) and catches the load-bearing case directly.

3. **Counterfactual on Pattern 3**: had Shard 1's prompt also cited audit artifact paths (the way Shard 2's did), would Shard 1 have halted at zero commits AT THAT POINT and forced the chore commit earlier? In practice Shard 1's prompt embedded the F-1..F-6 / F-002 finding enumeration directly, so the agent proceeded with the embedded content as authority. Both patterns are correct — embed the content for resilience AND commit the artifact for durability — but the durable-commit path is structurally stronger because it survives prompt context loss (e.g. /clear, auto-compaction).

## Cross-references

- **Companion DECISION**: `journal/0025-DECISION-codify-cycle-disposition.md` (why these patterns landed as DISCOVERY rather than rule edits).
- **Pattern 1 evidence**: `journal/0024-DECISION-precondition-invariants-and-orphan-prevention.md` (Shard 3 closure of R2-F1) + `workspaces/phase-01-mvp/04-validate/round-2-security-audit-2026-05-24.md` (Lane C's R2-F1 finding) + `workspaces/phase-01-mvp/04-validate/round-2-code-review-2026-05-24.md` (Lane B's "covered by F-001" disposition).
- **Pattern 2 evidence**: Round 2 audit corpus (Lane A clean / Lane B clean / Lane C 1-HIGH disagreement); orchestrator's tie-breaker recorded in this codify session's transcript.
- **Pattern 3 evidence**: `journal/0023-DISCOVERY-envelope-hashes-mint-time-cached-f5-false-positive.md` (Shard 2 halt and disposition pre-flight); chore commit `7598578` (audit corpus durability fix).
- **Rule extensions to propose upstream**: `rules/agents.md` (Pattern 2), `rules/worktree-isolation.md` or `commands/redteam.md` (Pattern 3), `commands/redteam.md` or `rules/agents.md` (Pattern 1).
- **Authority chain for upstream propagation**: `rules/artifact-flow.md` (downstream → upstream via /sync) + `rules/coc-sync-landing.md` (sync discipline that gates the propagation).
