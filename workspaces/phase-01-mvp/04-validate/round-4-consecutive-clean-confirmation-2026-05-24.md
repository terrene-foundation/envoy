# Round 4 — Consecutive Clean Confirmation (T-02-33 Convergence)

**Audit date:** 2026-05-24
**Round:** 4 of /redteam — second of 2 consecutive clean rounds (convergence run)
**Current main:** `2264ae2` (unchanged since Round 3)
**Cumulative T-02-33 + Shards 1-3 diff:** `git diff 641dd2d..2264ae2`
**Working tree:** clean (only untracked workspace redteam artifacts; no modified tracked files)

**Methodology:** per `skills/spec-compliance/SKILL.md` § Audit Protocol + `rules/probe-driven-verification.md` § Structural-Probes-Required + `rules/testing.md` § Audit Mode Rules. All probes re-derived from scratch; NO trust of Round 3 outputs. Same SHA + deterministic AST/grep/pytest probes → same structural outputs.

---

## Round 3 baseline (already clean)

All three lanes returned CLEAN at Round 3:

- Lane A spec-compliance: `workspaces/phase-01-mvp/04-validate/round-3-spec-compliance-2026-05-24.md`
- Lane B code-review: `workspaces/phase-01-mvp/04-validate/round-3-code-review-2026-05-24.md`
- Lane C security-audit: `workspaces/phase-01-mvp/04-validate/round-3-security-audit-2026-05-24.md`
- Test coverage: 609/609 passing, 0 new findings

## Round 4 mission

Confirm Round 3's clean verdict reproduces against the same SHA. Same probes against the same code MUST produce the same structural answers; any divergence is a HIGH non-determinism finding per `rules/probe-driven-verification.md`.

---

## Step 1 — Round 3 closure-probe reproduction

| Row  | Round 3 finding closure        | Reproduced structurally? | Notes                                                                                            |
| ---- | ------------------------------ | ------------------------ | ------------------------------------------------------------------------------------------------ |
| R4-1 | R2-F1 AST atomicity ordering   | YES — identical          | mutate=1008 / raises=[1019,1027,1035] / posture_change=1078 / envelope_edit=1115                 |
| R4-2 | R2-F1 Tier 1 `types == []` × 4 | YES — identical          | Lines 1679 / 1712 / 1745 / 1775 (Round 3 doc had transcription typo 1744; structural claim same) |
| R4-3 | R2-F1 Tier 2 real-Ledger × 3   | YES — identical          | Class @ 672, methods @ 701/747/789; zero mocking imports                                         |
| R4-4 | R2-F2 Protocol + spy           | YES — identical          | Docstring contract @ 675-693; test class @ 1972, method @ 1989                                   |
| R4-5 | R2-F3 spec clarifications      | YES — identical          | posture-ladder.md:128, shared-household.md:102; refined ADDED-lines probe empty                  |

Full assertion table at: `workspaces/phase-01-mvp/.spec-coverage-round-4-2026-05-24.md`

---

## Step 2 — Test counts re-derived

```text
$ .venv/bin/pytest --collect-only -q tests/
... 609 tests collected in 0.39s (exit 0)

$ .venv/bin/pytest tests/ -x -q --tb=short
... 609 passed in 18.10s
```

Round 3 baseline was 609 collected / 609 passing / 17.65s. Round 4 reproduction: 609 / 609 / 18.10s. Wall-time variance (~3%) is OS-level (filesystem cache / runner state) and does not affect the structural claim.

---

## Step 3 — Stability / non-determinism sweep

| Probe                                            | Round 3 output                         | Round 4 output                         | Determinism                                                  |
| ------------------------------------------------ | -------------------------------------- | -------------------------------------- | ------------------------------------------------------------ |
| AST: posture_gate.py request_transition ordering | (1008, [1019,1027,1035], 1078, 1115)   | (1008, [1019,1027,1035], 1078, 1115)   | DETERMINISTIC                                                |
| grep: `assert types == \[\]` count               | 4 hits                                 | 4 hits                                 | DETERMINISTIC (line numbers identical; Round 3 doc had typo) |
| grep: TestF2 class + 3 methods                   | 672 / 701 / 747 / 789                  | 672 / 701 / 747 / 789                  | DETERMINISTIC                                                |
| grep: Protocol docstring + spy test              | 675-693 / 1972 / 1989                  | 675-693 / 1972 / 1989                  | DETERMINISTIC                                                |
| grep: spec clarification anchors                 | posture-ladder.md:128, shared-h.md:102 | posture-ladder.md:128, shared-h.md:102 | DETERMINISTIC                                                |
| pytest --collect-only count                      | 609                                    | 609                                    | DETERMINISTIC                                                |
| pytest -x full suite                             | 609 passed                             | 609 passed                             | DETERMINISTIC                                                |
| log triage (`warn\|error\|deprecat\|fail`)       | empty                                  | empty                                  | DETERMINISTIC                                                |

**No probe produced a different STRUCTURAL output in Round 4 against the same SHA. No HIGH non-determinism finding.**

Notes on the two recorded deltas:

1. **Round 3 doc said line 1744; actual grep output was line 1745.** This is a transcription typo in the Round 3 artifact. The probe (grep) ran identically; the doc author transcribed one digit incorrectly. The structural claim ("4 methods, all assert `types == []`") is unchanged. The R4-2 assertion table records the actual grep output (1745) per `rules/probe-driven-verification.md` MUST-1+2 — the schema-conformant probe answer is the load-bearing claim, not the prose transcription.

2. **Round 3 R3-5 broad-grep returned a false-positive on the diff hunk header containing the literal token `target`** (a function parameter name in spec pseudocode `def posture_change(current: PostureLevel, target: PostureLevel, ...)`). Round 3 documented `[empty]` after manual triage. Round 4 sharpened the probe to grep only `^[+]` ADDED lines, structurally eliminating the false-positive class. Refined probe returns genuinely empty.

Neither delta indicates non-determinism — both are pre-existing audit-trail clarifications.

---

## Step 4 — Cumulative sweep (641dd2d..2264ae2 — T-02-33 + 3 shards)

Re-walked the cumulative diff with fresh attention:

| Sweep                                 | Result                                                                                                                                                                                                     |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Silent-fallback patterns (envoy/)     | NONE introduced cumulatively                                                                                                                                                                               |
| Inline DDL (envoy/)                   | NONE introduced cumulatively                                                                                                                                                                               |
| New `__all__` block additions         | NONE; `PostureEnvelopeMutationInvariantError` was added to `envoy/authorship/__init__.py::__all__` (single-entry, not new block); exercised by production + Tier 1 (4) + Tier 2 (3) methods — not orphaned |
| Cross-CLI hygiene on journals 0021-24 | CLEAN — zero `Agent(subagent_type=)`, `run_in_background=true`, `TaskCreate`/`TaskUpdate`, `per CLAUDE.md`, CC tool-noun, hook-name leakage                                                                |
| Unreachable code                      | NONE — Step 5a `posture_change` append (1078) and Step 5b `envelope_edit` append (1115) both reachable along the success path                                                                              |

**Cumulative LOC growth** (15 files, +3,210 / -26 across T-02-33 + 3 shards):

| File path                                               | Net delta                    |
| ------------------------------------------------------- | ---------------------------- |
| envoy/authorship/**init**.py                            | +2                           |
| envoy/authorship/posture_gate.py                        | +212                         |
| specs/envelope-model.md                                 | +2/-1                        |
| specs/posture-ladder.md                                 | +5                           |
| specs/shared-household.md                               | +4                           |
| tests/tier1/test_posture_gate_5_step_fail_closed.py     | +574                         |
| tests/tier2/test_envelope_hash_mint_time_cached.py      | +419 (new file)              |
| tests/tier2/test_posture_gate_wiring.py                 | +338                         |
| workspaces/phase-01-mvp/.spec-coverage-t02-33-round1.md | +157 (new)                   |
| workspaces/phase-01-mvp/04-validate/round-1-\*          | +1,147 (3 new files)         |
| workspaces/phase-01-mvp/journal/0022/0023/0024          | +376 (3 new journal entries) |

All growth is additive (production code: +214 LOC; tests: +1,331 LOC; specs: +10 LOC; workspace artifacts: +1,655 LOC). No `rules/refactor-invariants.md` MUST-1 LOC-invariant-test trigger (no file shrank).

**Verdict: no overlooked findings emerge under fresh attention.**

---

## Step 5 — Log triage gate

```text
$ .venv/bin/pytest tests/ -q --tb=short 2>&1 | grep -iE "warn|error|deprecat|fail" | sort -u
[empty]
```

Per `rules/observability.md` MUST Rule 5: zero WARN+/ERROR/DEPRECATION/FAIL entries in the most-recent full-suite run.

**Verdict: PASS.**

---

## Convergence summary

| Dimension                    | Round 3      | Round 4                      | Convergence |
| ---------------------------- | ------------ | ---------------------------- | ----------- |
| Test count (collected)       | 609          | 609                          | YES         |
| Test count (passing)         | 609          | 609                          | YES         |
| WARN+ / ERROR / DEPRECATION  | 0            | 0                            | YES         |
| R2-F1 atomicity AST ordering | PASS         | PASS                         | YES         |
| R2-F1 Tier 1 fail-closed × 4 | PASS         | PASS                         | YES         |
| R2-F1 Tier 2 real-Ledger × 3 | PASS         | PASS                         | YES         |
| R2-F2 Protocol + spy         | PASS         | PASS                         | YES         |
| R2-F3 spec clarifications    | PASS         | PASS                         | YES         |
| New findings introduced      | 0            | 0                            | YES         |
| Probe-stability (R3 → R4)    | n/a baseline | all 5 reproduce structurally | YES         |

**Convergence criterion met: 2 consecutive clean rounds (Round 3 + Round 4).**

T-02-33 is convergence-clean and ready for the next gate per `commands/redteam.md` § Convergence.

---

## Artifacts

- `workspaces/phase-01-mvp/.spec-coverage-round-4-2026-05-24.md` — fresh assertion table (5 closure rows + 8 sweep rows + probe-stability summary)
- `workspaces/phase-01-mvp/04-validate/round-4-consecutive-clean-confirmation-2026-05-24.md` — this disposition
