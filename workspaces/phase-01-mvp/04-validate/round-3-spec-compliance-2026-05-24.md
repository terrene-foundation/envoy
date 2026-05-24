# Round 3 — Spec Compliance + Test Verification (T-02-33 RT-2 closure)

**Audit date:** 2026-05-24
**Round:** 3 of /redteam
**Diff scope (Shard 3 only):** `git diff e89914b..2264ae2`
**Cumulative diff (T-02-33 + all 3 shards):** `git diff 641dd2d..2264ae2`
**Current main:** `2264ae2`
**Methodology:** per `skills/spec-compliance/SKILL.md` § Audit Protocol + `rules/probe-driven-verification.md` § Structural-Probes-Required + `rules/testing.md` § Audit Mode Rules. NO trust of `.test-results` or Round 2's assertion table. Every claim re-derived from scratch via fresh AST / grep / pytest commands.

**Companion artifact:** `workspaces/phase-01-mvp/.spec-coverage-round-3-2026-05-24.md` (fresh assertion table; 18 rows across 4 sections — Round 2 closure, test-coverage re-derivation, new-finding sweeps, convergence verdict).

---

## 1. Convergence verdict

**CLEAN.** Shard 3 (PR #27, merge commit `2264ae2`, four implementation commits `bf1f66f` + `e21d67f` + `eb72777` + `58a3b78` + `a8a4fdb` + journal `eee0901`) closes every Round 2 finding (R2-F1 HIGH, R2-F2 MED, R2-F3 LOW). No new findings introduced. T-02-33 RT-2 closure complete.

## 2. Total tests collected + total green

| Metric                                                    | Value          |
| --------------------------------------------------------- | -------------- |
| Tests collected (re-derived from `pytest --collect-only`) | **609**        |
| Tests passing (re-derived from `pytest tests/ -q`)        | **609**        |
| Tier 1 posture-gate suite                                 | 110 / 110 PASS |
| Tier 2 posture-gate wiring                                | 14 / 14 PASS   |
| Tier 2 envelope-hash-mint-time-cached                     | 6 / 6 PASS     |
| Full suite wall-time                                      | 17.65s         |
| Log-triage scan (WARN / ERROR / DEPRECATION)              | empty — clean  |

**Delta vs Round 2:** +4 tests (609 vs 605). Shard 3 introduced: 1 Tier 1 spy-adapter test (R2-F2) + 3 Tier 2 real-EnvoyLedger tests (R2-F1). Tier 1 count rose 109 → 110 (+1); Tier 2 wiring rose 11 → 14 (+3); full suite 605 → 609 (+4).

## 3. Round 2 closure verification table

Each row verifies Round 2 closure with a FRESH command (not reusing Shard 3's PR description). Full assertion table with raw AST output is in `.spec-coverage-round-3-2026-05-24.md` rows R3-1 through R3-5.

| Finding   | Sev (Round 2)                                                                                                                             | Closure status (Round 3)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Verification command                                                                                                                                                                                                                                                                               | Verdict |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| **R2-F1** | HIGH — F-2 invariants raised BETWEEN Step 5a and Step 5b → orphan posture_change risk                                                     | **CLOSED** — Shard 3 commit `bf1f66f` promoted the 3 F-2 invariant checks to PRECONDITIONS (Step 5-PRECONDITIONS block at posture_gate.py:981-1053) that fire BEFORE Step 5a's posture_change append. AST verifies `mutate_for_posture_level` call (line 1008) + all 3 `PostureEnvelopeMutationInvariantError` raises (lines 1019, 1027, 1035) precede the first `_ledger.append(entry_type="posture_change", ...)` at line 1078. Commit `e21d67f` flipped 4 `TestStep5bMutationInvariantChecks` methods to assert `types == []`. Commit `a8a4fdb` adds 3 Tier 2 real-EnvoyLedger methods asserting `entries == []` after each invariant violation. | AST extract: `raise_lines = [1019, 1027, 1035]`; `posture_change append = 1078`; `all_invariant_raises_BEFORE_append = True`. Grep: `assert types == \[\]` hits 1679, 1712, 1744, 1774 (4 Tier 1 methods). `class TestF2InvariantViolationEmitsNeitherEntry` at tier2 line 672 with 3 async tests. | PASS    |
| **R2-F2** | MED — Protocol contract not pinned + gate attribute-read surface unbounded                                                                | **CLOSED** — Shard 3 commit `eb72777` adds "Side-effect-free attribute reads (R2-F2 contract — IMPLEMENTORS)" section to `_PostureCarryingEnvelope` Protocol docstring (posture_gate.py:675-700) enumerating what implementors MUST NOT do on attribute read (I/O, locks, log emission, observable state mutation, background-task wakeup). `TestPostureCarryingEnvelopeProtocolDiscipline::test_protocol_attribute_read_surface_bounded` (test_posture_gate_5_step_fail_closed.py:1989) pins the gate's read surface to exactly 5 names via a spy adapter that counts `__getattribute__` calls.                                                    | `grep -n "side-effect-free\|Side-effect-free\|R2-F2 contract" envoy/authorship/posture_gate.py` → 675, 677, 693. `grep -n "TestPostureCarryingEnvelopeProtocolDiscipline" tests/tier1/...` → 1972.                                                                                                 | PASS    |
| **R2-F3** | LOW — `effective_posture_for_composition` + `compose_cross_principal_action` reference `p.posture_level` ambiguously vs. mint-state field | **CLOSED** — Shard 3 commit `58a3b78` adds clarification notes at `specs/posture-ladder.md:128-132` + `specs/shared-household.md:102-105`. Both notes cite `specs/envelope-model.md § metadata.posture_level` (Round 1 F-4 disposition), use present-tense only, and contain no "Pre-Phase-03 / will be refactored / Phase-N planning" framings per `rules/spec-accuracy.md`.                                                                                                                                                                                                                                                                       | `git diff e89914b..2264ae2 -- specs/posture-ladder.md specs/shared-household.md \| grep -iE "will be\|phase[-_ ]?0?3\|pre-phase\|todo\|tbd\|fixme\|future\|scaffold\|promised\|target\|pending\|to be wired"` → empty.                                                                             | PASS    |

**Round 2 finding totals:**

- HIGH (Lane C) — 1 closed (R2-F1)
- MED (Lane C) — 1 closed (R2-F2)
- LOW (Lane C) — 1 closed (R2-F3)

**Closure rate: 3/3 = 100%.**

## 4. NEW findings introduced by Shard 3

**ZERO.**

8-row sweep across mechanical / structural surfaces produced no findings:

| Sweep                                                                  | Outcome                                                                                                                                                                                                                                                                                                         |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cross-CLI artifact hygiene on journal/0024 + spec edits                | PASS — no `Agent(subagent_type=)`, no `CLAUDE.md`-as-authority, no PascalCase hook event names, no `the Read tool` / `the Bash tool` prescriptive prose                                                                                                                                                         |
| Spec-accuracy compliance on Shard 3 spec diffs                         | PASS — no `will be refactored` / `Pre-Phase-03` / `Phase-1 / Phase-2` / `TBD` / `pending` / `scaffold` framings; present-tense only                                                                                                                                                                             |
| Silent fallback patterns (`except: pass` etc.) in posture_gate.py diff | PASS — empty                                                                                                                                                                                                                                                                                                    |
| Probe-driven discipline (no regex-on-semantic-claims in new tests)     | PASS — Shard 3 tests use AST extraction (`ast.parse`), direct row-shape assertions on real Ledger, structural `set(observed) == expected` for spy adapter — no `re.search`/`re.match`                                                                                                                           |
| LOC growth check / shrink-requiring-invariant test                     | PASS — no file shrank (posture_gate.py +50; specs +5 / +4; tier1 +163; tier2 +215)                                                                                                                                                                                                                              |
| Log triage scan on full suite output                                   | PASS — empty (no WARN / ERROR / DEPRECATION / FAIL entries)                                                                                                                                                                                                                                                     |
| Orphan check on new symbols                                            | PASS — no new manager-shape classes, no new facade attributes, no new `__all__` entries                                                                                                                                                                                                                         |
| Pre-existing TBD on `specs/shared-household.md:165`                    | NOTED — introduced in Phase-00 commit `3c496f9`, predates T-02-33; NOT introduced by Shard 3 (`git diff e89914b..2264ae2 -- specs/shared-household.md \| grep TBD` empty); outside session scope per `rules/zero-tolerance.md` Rule 1c (existence pre-dates session's first tool call, verifiable from git log) |

## 5. Atomicity assertion table (R2-F1 deep-dive)

The R2-F1 closure is the load-bearing structural change in Shard 3. Three layers of evidence verify the fail-closed contract holds at AST, Tier 1, and Tier 2 levels.

### Layer 1: AST ordering (structural code-level)

| Probe                                                     | Result             | Pass condition                                |
| --------------------------------------------------------- | ------------------ | --------------------------------------------- |
| `mutate_for_posture_level` call line                      | 1008               | < first posture_change append (1078)          |
| `raise PostureEnvelopeMutationInvariantError` raise lines | [1019, 1027, 1035] | all < first posture_change append (1078)      |
| First `_ledger.append(entry_type="posture_change")` line  | 1078               | > all 3 raise lines + mutate call             |
| First `_ledger.append(entry_type="envelope_edit")` line   | 1115               | > posture_change append (spec-mandated order) |

**Verdict:** PASS — the precondition gate is structurally in place; invariant violations CANNOT reach line 1078.

### Layer 2: Tier 1 fail-closed pin (in-memory fake Ledger)

| Tier 1 method                               | Invariant violated    | Assertion                 |
| ------------------------------------------- | --------------------- | ------------------------- |
| `test_envelope_id_mismatch_raises` (1655)   | envelope_id swap      | `types == []` (line 1679) |
| `test_new_version_regression_raises` (1688) | new_version == prior  | `types == []` (line 1712) |
| `test_new_version_skip_raises` (1718)       | new_version > prior+1 | `types == []` (line 1744) |
| `test_malformed_diff_hash_raises` (1751)    | diff_hash malformed   | `types == []` (line 1774) |

Every method also asserts `sink.writes == []` (BET-12 emission is Step 5+; MUST NOT fire).

**Verdict:** PASS — Tier 1 fast-feedback contract pinned.

### Layer 3: Tier 2 real-EnvoyLedger pin

| Tier 2 method                                         | Invariant violated  | Assertion                                                    |
| ----------------------------------------------------- | ------------------- | ------------------------------------------------------------ |
| `test_envelope_id_mismatch_emits_neither_entry` (701) | envelope_id swap    | `entries == []` after `_read_appended_entries(envoy_ledger)` |
| `test_new_version_drift_emits_neither_entry` (747)    | new_version skip    | `entries == []`                                              |
| `test_malformed_diff_hash_emits_neither_entry` (789)  | diff_hash malformed | `entries == []`                                              |

Tests use real `EnvoyLedger` fixture (no `MagicMock` / `@patch` / `unittest.mock` imports in module). FFI/persistence path exercised, not in-memory fake.

**Verdict:** PASS — Tier 2 real-infrastructure contract pinned per `rules/testing.md` Tier 2 NO mocking.

## 6. Convergence + saved artifacts

**Convergence: CLEAN.** All 3 Round 2 findings closed with structural defenses verified across 3 layers (AST + Tier 1 + Tier 2). No new findings introduced by Shard 3. Full test suite green (609/609). Cross-CLI artifact hygiene + spec-accuracy + probe-driven + observability sweeps all PASS.

**Saved artifacts:**

- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/.spec-coverage-round-3-2026-05-24.md` — Round 3 fresh assertion table (18 rows; 4 sections: Round 2 closure, test-coverage re-derivation, new-finding sweeps, convergence verdict) with AST extraction transcripts and full pytest output
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/04-validate/round-3-spec-compliance-2026-05-24.md` — this document

**Recommended next step:** T-02-33 RT-2 is fully closed. The F-001 deferred item (Ledger transactional support for Step 5a/5b non-atomicity at the persistence layer) remains tracked at GH issue #24 per Round 2 disposition (`rules/autonomous-execution.md` § Per-Session Capacity Budget exceeded → next-phase shard). Proceed to `/codify` or next workspace task per orchestrator selection.
