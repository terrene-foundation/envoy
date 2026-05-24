---
type: DECISION
date: 2026-05-24
created_at: 2026-05-24T20:30:00Z
author: agent
session_id: phase-01-codify-2026-05-24
session_turn: 1
project: phase-01-mvp
topic: /codify cycle disposition for T-02-33 RT-1 + RT-2 convergence — downstream consumer repo, local-only codification
phase: codify
tags:
  - codify
  - downstream-repo
  - rt-1
  - rt-2
  - convergence-record
  - artifact-flow
  - upstream-managed
---

# DECISION: /codify cycle outputs stay local; upstream-managed `.claude/` surfaces not edited

This `/codify` cycle followed the T-02-33 envelope_edit pairing convergence (PRs #23 → #25 → #26 → #27, merged at `2264ae2`, with Round 3 + Round 4 consecutive-clean verification). The convergence cycle surfaced three generalizable meta-patterns (captured in companion DISCOVERY entry `journal/0026-DISCOVERY-redteam-convergence-meta-patterns.md`) plus closed 7 round-1 + 3 round-2 findings via 3 follow-up shards.

This entry records why those meta-patterns landed as a journal DISCOVERY rather than as rule / agent / skill updates, and what the local-only codification deliverables are.

## What we picked

### Local-only codification, no upstream propagation

This repository is `terrene-foundation/envoy` — a **downstream consumer project** built on the `kailash-coc-claude-rs` USE template (per `CLAUDE.md` line 5 and the migration commits at `1824194` / `5a7b629`). Per `.claude/rules/artifact-flow.md`:

> **Downstream project repos**: SKIP. Changes stay local.

The directories `.claude/rules/`, `.claude/agents/`, `.claude/skills/`, `.claude/commands/`, `.claude/hooks/` are upstream-managed: they are emitted by `kailash-coc-claude-rs` (via the COC sync workflow per `rules/coc-sync-landing.md`). Local edits to those paths would be overwritten on the next `/sync` from the template.

The codification surfaces this `/codify` is permitted to write are therefore:

| Surface                                                | Status                | Why                                                                                                                                                              |
| ------------------------------------------------------ | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `workspaces/phase-01-mvp/journal/*.md`                 | Yes — written         | Project-local, survives across sessions, captures institutional knowledge for next-session inheritance                                                           |
| `workspaces/phase-01-mvp/todos/active/*.md`            | Yes — updated         | Project-local, the wave-2 todo's T-02-33 status block reflects the full convergence chain                                                                        |
| `.claude/learning/learning-codified.json`              | Yes — written         | Closes the observe → digest → codify loop locally per `commands/codify.md` Step 1                                                                                |
| `specs/*.md`                                           | No — frozen           | Phase 00 specs are FROZEN v1; edit only under `rules/specs-authority.md` Rule 5b workflow; no new domain truth surfaced this codify cycle to warrant a spec edit |
| `.claude/rules/`, `.claude/agents/`, `.claude/skills/` | No — upstream-managed | Edits would be overwritten on next `/sync` from `kailash-coc-claude-rs`                                                                                          |

### The three meta-patterns from RT-1 + RT-2

Each is recorded in `journal/0026-DISCOVERY-redteam-convergence-meta-patterns.md` with the literal evidence from this convergence cycle. They are generalizable across `/redteam` cycles on any kailash-bound project, so the natural propagation path is upstream into the COC USE template:

1. **Same-class regression at the fix site** — Round 1 F-3 closure (Shard 1 removed the defensive guard) reintroduced the orphan-`posture_change` pattern at the new F-2 invariant raise sites. Round 2's security audit (Lane C) caught it as R2-F1 HIGH. Round 2's code review (Lane B) missed it (dispositioned as "covered by F-001 #24" — wrong bug class). The meta-pattern: when Round-N closes a HIGH, Round-N+1 MUST scan the fix-site for same-class regressions, not just verify the original site is fixed.

2. **Parallel-lane disagreement protocol** — Round 2 Lane B (reviewer) returned CLEAN; Round 2 Lane C (security-reviewer) returned NOT CLEAN with 1 HIGH. The orchestrator's role is to interrogate the disagreement and adjudicate on bug-class semantics (different solutions for different root causes), not to default to either lane's verdict by lower-severity preference.

3. **Audit-corpus visibility in worktree follow-ups** — Lane A/B/C of /redteam rounds write audit artifacts to the main checkout as untracked files. Worktree-isolated follow-up agents branched from `origin/main` cannot see them. The Shard 2 agent specifically halted at zero commits when it tried to read `round-1-security-audit-2026-05-24.md` and found it absent in the worktree — caught by `rules/verify-resource-existence.md` MUST-1. Resolution: commit audit artifacts to main BEFORE spawning follow-up shards. This codify cycle's predecessor session committed Round 1 audit docs at `7598578` after the existence check failure surfaced the gap; Round 2-4 docs committed at `d780f89` proactively.

### Why these patterns are not codified into local rules

`.claude/rules/agents.md`, `.claude/rules/worktree-isolation.md`, and `.claude/commands/redteam.md` are upstream-managed. Local edits to capture the three meta-patterns would be overwritten on the next `/sync rs` cycle. The patterns can propagate upstream by the user invoking `/sync rs` on `kailash-coc-claude-rs` and incorporating these findings into the upstream rule set; this is a human-gated process per `rules/coc-sync-landing.md` (and per the cross-repo discipline in `rules/repo-scope-discipline.md` that prevents this session from editing the upstream template directly).

### Disposition of two violations.jsonl entries

`.claude/learning/violations.jsonl` carried two entries from 2026-05-10 (`vio_1778436281312_5bf20d4a`, `vio_1778436283547_4c9b3b0c`) — both blocked at write time for `repo-scope-discipline/MUST-NOT-1` (attempting `gh --repo "$REPO"` from CWD basename `envoy`). Both have `addressed_by: null`. Per `commands/codify.md` Step 6b, addressed_by linking applies when authoring a NEW rule whose root cause matches the violation. The existing rule `repo-scope-discipline.md` MUST NOT 1 already addresses the root cause; the violations were correctly blocked. No rule update required; the violations are tracked as evidence the existing rule fires correctly.

## Why this disposition

### Local-only is the contract for downstream repos

`rules/artifact-flow.md` defines the canonical authority chain:

```
atelier/ → /sync-to-coc → loom/ → /sync → USE templates
BUILD repos → /codify → proposal → loom/ → /sync → USE templates
Downstream project repos → /codify stays local only
```

envoy is downstream-only by design. Treating downstream `/codify` as a write-to-upstream path would corrupt the unidirectional artifact flow that the cross-repo discipline depends on.

### Journal DISCOVERY entries are the durable inheritance surface

Per `rules/journal.md`: "Entries MUST be self-contained — readable without other context. Entries referenced months later by a different agent are useless if they depend on session context that no longer exists." The DISCOVERY companion entry (`journal/0026`) is the institutional-knowledge artifact that survives across sessions, project resets, and `/clear` boundaries. A future `/codify` cycle on a BUILD repo OR an upstream `/sync` cycle can read it as evidence for proposing the meta-patterns upstream into the canonical rule set.

### learning-codified.json closes the audit loop

The file records exactly what this `/codify` analyzed (digest hash, journals consumed, violations triaged) so the next `/codify` cycle's Step 1 — "read `learning-codified.json` to avoid re-processing what was already codified" — produces deterministic input. Without this file, every `/codify` cycle would re-analyze the same observations indefinitely.

## Alternatives considered

### Edit `.claude/rules/` directly with a comment that the edits are local-only

Rejected because:

- `coc-sync-landing.md` MUST Rule 1 declares COC drift artifacts land as PR #1 on next session; any local rule edit becomes drift that the next session is obligated to land OR revert. The drift would conflict with the unidirectional sync.
- `cross-cli-artifact-hygiene.md` MUST Rule 3 forbids citing CLI-baseline files as authority; the upstream template files are the authority for these surfaces — overriding them locally would re-introduce the cross-CLI baseline-as-authority anti-pattern.

### File a GH issue against this repo summarizing the three meta-patterns

Rejected because:

- The natural recipient of these meta-patterns is `kailash-coc-claude-rs`, not `envoy`. Filing on `envoy` would be cargo-cult tracking — the issue would never close because envoy has no authority to ship the upstream change.
- `rules/upstream-issue-hygiene.md` MUST Rule 1 (human gate before filing upstream) requires explicit user approval per filing; this `/codify` autonomously cannot file upstream.
- The journal DISCOVERY entry IS the durable receipt; the user can propagate it upstream at `/sync rs` time via their own workflow.

### Update specs/ to capture the mint-state semantics + paired-emission contract

Rejected because Shard 1 + Shard 3 already shipped the necessary spec edits (`specs/envelope-model.md` § Schema mint-state field-semantics; `specs/posture-ladder.md` + `specs/shared-household.md` clarifications). No new domain truth emerged this codify cycle that the specs don't already capture.

## Consequences

- The next `/codify` cycle's Step 1 will read `learning-codified.json` and skip re-processing the 5 journal entries (0020-0024) plus the Round 1-4 audit corpus.
- The next `/wrapup` (whoever invokes it) writes `.session-notes` reflecting the convergence-clean state of Wave-2 PostureGate surface + the next-pick recommendation (T-02-36 Shamir CLI or T-02-37 Tier 2 wiring).
- If/when this repo's owner runs `/sync rs` against the upstream `kailash-coc-claude-rs` template, the three meta-patterns in `journal/0026` are the user-anchored evidence for proposing the corresponding upstream rule changes.
- Issue #24 (Phase 03 Ledger transactional primitive) remains the only open follow-up from the entire T-02-33 chain.

## Follow-up

- **For the user**: when convenient, consider running `/sync rs` against `kailash-coc-claude-rs` AND incorporating the three meta-patterns from `journal/0026` as proposed upstream rule extensions. The natural target rules are `rules/agents.md` (lane-disagreement protocol), `commands/redteam.md` (same-class regression at fix site), `rules/worktree-isolation.md` (audit-corpus visibility).
- **For the next /redteam cycle in this repo**: pre-commit audit artifacts to main BEFORE spawning follow-up worktree shards, OR pass the audit artifact content inline in the shard's prompt as a fallback. This codify cycle's session demonstrated the failure mode at Shard 2's pre-flight investigation.
- **For the wave-2 next-pick**: T-02-36 (Shamir CLI) is unblocked (T-02-34 + T-02-35 closed). T-02-37 (Tier 2 wiring) is unblocked (T-02-34 + T-02-35 + T-02-36 chain). T-02-33's convergence does not gate either pick directly — the choice is independent.

## For Discussion

1. **Counterfactual**: had this `/codify` cycle landed in `kailash-coc-claude-rs` (the upstream template) instead of `envoy` (downstream consumer), would the three meta-patterns have been codified into rules directly OR would the journal DISCOVERY → upstream proposal → human-gated landing protocol still apply? The upstream-vs-downstream distinction is structural here, but the "always journal first, then propose" pattern may be a stronger discipline regardless of which side of the sync boundary the codify runs on.

2. **Data-anchored**: across the 5 journal entries 0020-0024, the convergence cycle spent ~3 rounds + 3 shards closing what started as 7 findings (Round 1) + 3 findings (Round 2). The same-class regression at the fix site (R2-F1) was the costliest finding — it took a full round + a 6-commit shard to close. Would a Round 1 reviewer mandate to "specifically grep the fix site for same-class patterns" have caught it in Shard 1 itself, eliminating the Round 2 → Shard 3 cycle? The cost of adding that mandate (one extra mechanical sweep per gate-level review) vs the cost of the regression cycle (~1 session) is a clear win.

3. **Counterfactual**: the Shard 2 agent halted at zero commits when it discovered the Round 1 audit doc was untracked in the worktree. Had the agent proceeded against the prompt's embedded F-5 finding enumeration (the way Shard 1's agent did when facing the same gap), would F-5 have shipped as a phantom 250-LOC schema-version-bump migration? The "verify resource existence before debugging access" discipline (`rules/verify-resource-existence.md`) directly prevented this — but the rule has a generalization: when an artifact path cited in a prompt is absent on disk, halt and ask before proceeding against the prompt's embedded content as a fallback.

## Cross-references

- **Companion DISCOVERY entry**: `workspaces/phase-01-mvp/journal/0026-DISCOVERY-redteam-convergence-meta-patterns.md` (the three meta-patterns this cycle surfaces).
- **Convergence chain origin**: `workspaces/phase-01-mvp/journal/0020-DECISION-envelope-edit-deferred-to-tier-2.md` (T-02-31 deferral that T-02-33 closed).
- **Convergence chain milestones**: `journal/0021` (DI design) → `journal/0022` (mint-state interpretation) → `journal/0023` (F-5 false-positive disposition) → `journal/0024` (precondition invariants).
- **Round 1 audit corpus**: `workspaces/phase-01-mvp/04-validate/round-1-{code-review,security-audit,spec-compliance}-2026-05-24.md` (committed at `7598578`).
- **Round 2-4 audit corpus**: `workspaces/phase-01-mvp/04-validate/round-{2,3,4}-*-2026-05-24.md` (committed at `d780f89`).
- **Open follow-up**: GH issue #24 (Phase 03 Ledger transactional primitive).
- **Codify learning audit**: `.claude/learning/learning-codified.json` records this cycle's full audit trail.
- **Authority chain**: `.claude/rules/artifact-flow.md` (downstream local-only rule); `.claude/rules/coc-sync-landing.md` (sync discipline that overwrites local edits on `.claude/{rules,agents,skills}`).
