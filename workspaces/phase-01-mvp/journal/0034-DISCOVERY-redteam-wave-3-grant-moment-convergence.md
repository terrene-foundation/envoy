---
type: DISCOVERY
date: 2026-05-26
created_at: 2026-05-26T07:00:00Z
author: agent
session_id: 8d16380b-9f76-422c-aef7-8d805d4d19e3
project: phase-01-mvp
topic: Wave-3 Grant Moment /redteam convergence — 4-round parallel multi-agent audit
phase: redteam
tags: [wave-3, grant-moment, redteam, convergence, CLEAN×2]
---

# /redteam Wave-3 Grant Moment — CONVERGED (4 rounds across 3 axes)

PR #40 (`feat/phase-01-wave-3-grant-moment`) reached the brief's Exit
criterion ("0 CRITICAL/HIGH findings, 2 clean rounds") via four rounds
of parallel multi-agent audit. Convergence trajectory:

| Axis              | R1             | R2             | R3      | R4    | 2-CLEAN met at |
| ----------------- | -------------- | -------------- | ------- | ----- | -------------- |
| Security          | CLEAN (1 LOW)  | CLEAN          | —       | —     | R1 + R2        |
| Code/Architecture | NEEDS_FOLLOWUP | CLEAN (1 LOW)  | CLEAN   | —     | R2 + R3        |
| Spec compliance   | NEEDS_FOLLOWUP | NEEDS_FOLLOWUP | NEEDS_F | CLEAN | R3 + R4        |

## Round trajectory

### Round 1 (HEAD `31e000b`)

- **Security** (security-reviewer): CLEAN. 1 LOW awareness-only — `DeclineResolution.co_signature_hex` is set None on Decline path (correct per spec); the canonical-bytes function never runs on Decline path so no signing accident. Surfaced for awareness, no fix required.
- **Code/Architecture** (reviewer): NEEDS_FOLLOWUP. 4 findings:
  - F-C1 [HIGH]: 10 spec error classes defined but never raised in package
  - F-C2 [HIGH]: ChannelHandoff uses string refusal sentinels instead of typed NotPrimaryChannelError
  - F-C3 [MEDIUM]: production module docstrings carry split-state framings ("Phase 01 / Wave-4 scope")
  - F-C4 [MEDIUM]: no @pytest.mark.regression coverage for spec error taxonomy
- **Spec compliance** (analyst): NEEDS_FOLLOWUP. 2 findings:
  - F-SP1 [HIGH]: 10 spec-named regression test files in `tests/regression/test_t008_*.py`-style do not exist on disk
  - F-SP2 [LOW]: claimed attribute naming drift (`channel` vs `channel_id`)

### Round 1 → R1-fix commit `3fdda24`

- F-C1: errors.py module docstring now carries § "Layer attribution" enumerating which surface raises each error. Runtime-raised errors clearly attributed to the future EnvoyGrantMomentRuntime facade (Wave-4 scope).
- F-C2: REJECTED as reviewer misclassification. Per spec § Error taxonomy table prose, `NotPrimaryChannelError` fires at M3 sign-or-decline (approval-receive), NOT at M1 dispatch-out. ChannelHandoff implements M1 dispatch; the layer split is structurally correct. channel_handoff.py docstring documents the split.
- F-C3: out_of_envelope.py docstring rewritten to drop "Phase 01 / Wave-4 scope" framings; present-tense description with explicit "NOT implemented in this module" delegation.
- F-C4 + F-SP1 PARTIAL: tests/tier1/test_grant_moment_state_machine_transitions.py TestErrorTaxonomy class now carries @pytest.mark.regression on the 10 spec-taxonomy threat-coverage tests with "Contract pin: <threat ID>" docstrings.
- F-SP2: REJECTED — spec § Error taxonomy table is prose-only with no attribute-name commitment to drift from.

### Round 2 (HEAD `3fdda24`)

- **Security**: CLEAN — all 11 axes independently verified at file:line. No new findings. 2 clean rounds (R1+R2) met for security axis.
- **Code/Architecture**: CLEAN with 1 LOW — F-C-R2-1 in-source comment residue at out_of_envelope.py:47-49 carrying "Phase 01 wires four of six" framing that the F-C3 docstring rewrite missed (grep was scoped to docstrings).
- **Spec compliance**: NEEDS_FOLLOWUP. F-SP-R2-1 [HIGH] surfaced the deeper issue under F-SP1: spec § Test location named 10 phantom test files (zero existed on disk); F-SP1's regression-marker fix closed the marker-and-citation sub-axis but the spec citation itself remained a `rules/spec-accuracy.md` MUST Rule 1 violation. F-SP-R2-2 [LOW] surfaced pre-existing `phase_a_record_ref` vs `phase_a_ref` cross-spec drift (carried-forward to /codify).

### Round 2 → R2-fix commit `7a6b0ea`

- F-C-R2-1: 3 in-source comment blocks in out_of_envelope.py rewritten (lines 47-49, 85, 126). Other Phase-N references in errors.py/channel_handoff.py/novelty.py/signed_consent.py/cascade_orchestrator.py left as legitimate architectural-roadmap (Phase-02 binding migration is a frozen Phase-00 boundary, not gap framing).
- F-SP-R2-1: specs/grant-moment.md § Test location rewritten to (a) reference 6 actual Wave-3 structural-layer test files (4 tier-1 + 2 tier-2) + the 10 @pytest.mark.regression Contract pins under TestErrorTaxonomy as the Wave-3 surface, AND (b) explicitly acknowledge 10 runtime-facade test files as Wave-4 deferred per `rules/specs-authority.md` Rule 6 with cross-references to briefs/00-phase-01-mvp-scope.md § Surfaces and 02-plans/01-build-sequence.md § Wave 4.
- F-SP-R2-2: NOT addressed in this PR; carry-forward to /codify pass for cross-spec terminology reconciliation.

### Round 3 (HEAD `7a6b0ea`)

- **Code/Architecture**: CLEAN. F-C-R2-1 confirmed CLOSED. Other Phase-N references confirmed as legitimate architectural-roadmap classification (no gap framing remains in production code). 2 clean rounds (R2+R3) met for code axis.
- **Spec compliance**: NEEDS_FOLLOWUP. F-SP-R3-1 [LOW] surfaced a path-prefix typo I introduced in the R2 spec fix itself — `specs/grant-moment.md:174` cited `briefs/00-phase-01-mvp-scope.md` (root-level `briefs/` does not exist; correct path is `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`).

### Round 3 → R3-fix commit `1ffb61c`

- F-SP-R3-1: single-line spec edit at specs/grant-moment.md:174 adding the `workspaces/phase-01-mvp/` path prefix.

### Round 4 (HEAD `1ffb61c`)

- **Spec compliance**: CLEAN. F-SP-R3-1 confirmed CLOSED via grep + ls. All 14 spec sections PASS. All 6 Wave-3 structural-layer test files exist; all 10 Wave-4 deferred files explicitly noted with cross-reference to brief + plan. F-SP-R2-2 carried-forward unchanged (out of Wave-3 scope, surfaces to /codify). 2 clean rounds (R3+R4) met for spec axis.

## Convergence verdict

Brief Exit criterion ("0 CRITICAL/HIGH findings, 2 clean rounds") is MET for
all three audit axes:

- 0 CRITICAL findings across 4 rounds.
- 0 HIGH findings standing (F-C1, F-C2, F-SP1, F-SP-R2-1 all closed by
  same-shard fixes per `rules/autonomous-execution.md` MUST Rule 4).
- 2 consecutive clean rounds per axis.

## Carry-forward (not Wave-3 scope)

- **F-SP-R2-2** (`phase_a_record_ref` vs `phase_a_ref` cross-spec drift between
  `specs/grant-moment.md` and `specs/ledger.md`): pre-existing, surfaces to
  `/codify` for cross-spec terminology reconciliation per
  `rules/specs-authority.md` Rule 5b sibling-spec re-derivation. Does NOT
  block PR #40.

## Test status (post-R3 fix, HEAD `1ffb61c`)

- tier-1: 758 passed
- tier-2: 211 passed, 9 skipped
- tier-3: 5 passed (T-02-45 EC-1 acceptance)
- Total: 974 passed, 9 skipped
- New Wave-3 tests: 36 + 28 + 30 + 20 = 114, all passing.
- `pytest -m regression`: 10 grant_moment threat-coverage Contract pins added
  to the regression sweep (T-008, T-018, T-019, T-093, H-03, back-pressure,
  cross-channel-confirm, dual-signature, novelty-friction, channel-timeout).

## Workflow + agent observations

- **Parallel multi-agent audit cost**: 4 rounds × up to 3 specialists per round
  = ~10 specialist invocations across the full convergence cycle.
  Same-shard fix-immediately per `rules/autonomous-execution.md` MUST Rule 4
  consistently closed findings within budget (R1 fix ~140 LOC; R2 fix ~90 LOC;
  R3 fix 1 LOC).
- **Worktree harness drift**: 2 of 3 parallel worktree agents reported branch-
  drift recovery (harness checked out `worktree-agent-<hash>` at main-tip
  rather than the prompt-declared `feat/phase-01-T-03-XX-...` from the
  prompted base SHA). Each agent recovered by `git checkout -b <branch>
<base-SHA>` per `rules/worktree-isolation.md` MUST-6. Worth investigating
  why the harness doesn't honor `isolation: "worktree"` + base-SHA pinning
  consistently.
- **F-SP1 sub-axis split** caught a real institutional gap: the R1 fix
  legitimately closed the marker-and-citation sub-axis but the spec citation
  itself remained a phantom — only the R2 audit's deeper re-derivation
  surfaced the broader F-SP-R2-1 finding. The convergence loop catches what
  any single round cannot.

## For Discussion

1. **Same-shard fix-immediately discipline worked**: every R-N finding was
   addressed in the same session as a tiny fix commit. The 4-round cycle
   would have collapsed to 2 if the agents had been asked to run all axes
   in a single round first; the structural defense here is that running
   each axis as an independent specialist call produces independent
   re-derivation, which is what catches the sub-axis-restated findings.
   Counter-factual: had we filed F-C1+F-C2+F-SP1 as follow-up issues per
   the rejected disposition (`rules/autonomous-execution.md` Rule 4
   BLOCKED rationalization "A separate PR is cleaner for review"),
   Wave-4 would have started with a broken contract surface and the
   threat-mitigation citations would have stayed phantom-cited.

2. **Worktree harness reliability**: 2 of 3 agents had to recover from
   branch drift; what's the structural fix? Options: (a) tighten the
   harness's `isolation: "worktree"` semantics to honor base-SHA pinning;
   (b) add a pre-launch verification in the orchestrator that confirms
   the worktree's branch matches the prompt before delegating; (c) accept
   the recovery cost and add it to per-shard budget. The agents did
   recover correctly via `rules/worktree-isolation.md` MUST-6 — but the
   recovery cost ~3-5 tool calls per agent.

3. **F-SP-R2-2 cross-spec drift disposition**: `phase_a_record_ref` vs
   `phase_a_ref` between grant-moment.md and ledger.md. Pre-existing,
   not Wave-3 scope per `rules/value-prioritization.md` MUST-2
   (value-anchor: spec terminology consistency; deferred to /codify). Is
   this the right disposition, or should the next session pick it up as
   a dedicated cross-spec cleanup shard?
