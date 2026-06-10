# /redteam Convergence — kailash upgrade 2.13.4 → 2.29.3 (P8)

**Date:** 2026-06-10 · **Branch:** `chore/kailash-upgrade` (impl commit `a9519d0` + redteam follow-up, uncommitted) · **Posture:** L5_DELEGATED (target is posture-invariant: 2 consecutive clean rounds + Criteria 4-7).

> NOTE: the formal `journal/NNNN-DECISION-…` entry is deferred to `/codify` — the
> integrity-guard hook routes `journal/` writes through the codify-lease flow
> (multi-operator-coc §6.4/§7.1). This `04-validate/` record is the redteam output
> per `commands/redteam.md` Step 2/5. The DECISION content below is ready to lift
> into the journal at `/codify`.

## Outcome: CONVERGED — 0 CRITICAL, 0 HIGH, 2 consecutive clean rounds.

## What landed (3 root-caused behavioral deltas + suppression dispositions)

| #   | Delta                                                    | Root cause                                                                                                                                                                                                                                                                                                           | Fix                                                                                                                                                                                                         |
| --- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | 415 `ImportError: PyNaCl is required`                    | 2.29.3 carved `pynacl`+`cryptography` into a `[trust]` extra (default in 2.13.4)                                                                                                                                                                                                                                     | Add `trust` to envoy's extra set; `[trust]` is the declared `pynacl` provider (`dependencies.md` § Declared=Imported)                                                                                       |
| 2   | Collection blocked: fatal `AggregateNode` name collision | held-back kailash-dataflow 2.7.7 (open `>=2.0.12` floor) had a duplicate registration; 2.29.3 made collisions fatal                                                                                                                                                                                                  | `uv lock --upgrade-package kailash-dataflow` → 2.11.3; family→latest per "Latest Versions Always"                                                                                                           |
| 3   | 23 `ResourceWarning: unclosed database`                  | **PRE-EXISTING on 2.13.4** (NOT upgrade-introduced — corrected; see note below). `SQLitePostureStore.__init__` opens a SQLite conn eagerly on BOTH 2.13.4 and 2.29.3 (`_get_connection()`); envoy's adapter built it in `__init__` → leak on construct-without-initialize. The upgrade's full-suite run SURFACED it. | lazy-init `_posture_store` (construct in `initialize()`, close+reset in `close()`, typed guard per `zero-tolerance.md` Rule 3a); restores "no I/O until initialize()"; closes the pre-existing leak at root |
| F3  | `Instance-based API usage` UserWarning suppression       | FIXED upstream on 2.29.3 (verified 0 occurrences via `-o filterwarnings=default`)                                                                                                                                                                                                                                    | DROPPED (carrying a fixed-issue suppression is BLOCKED, Rule 1)                                                                                                                                             |
| F4  | `Unclosed AsyncLocalRuntime` ResourceWarning suppression | STILL fires on 2.29.3 (verified 1 occurrence on `build_library_nexus`); genuine upstream leak                                                                                                                                                                                                                        | KEPT, scoped; upstream-file candidate (human-gated)                                                                                                                                                         |

Family final: kailash 2.29.3 · dataflow 2.11.3 · nexus 2.9.0 · kaizen 2.24.5 · pact 0.12.0 · mcp 0.2.14. `uv pip check` clean.

> **Correction (2026-06-10, post-convergence — accuracy fix):** Delta 3's original cause column claimed kailash **2.29.3 introduced** the eager-connect / 23 ResourceWarnings ("2.13.4 did not"). **This was wrong.** While resolving the pre-existing ruff lint (PR #92), the full suite was re-run on a **2.13.4** venv (main's deps) and reproduced the **identical 23 `unclosed database` warnings**; a tracemalloc run confirmed `SQLitePostureStore.__init__` opens a connection eagerly on **2.13.4 too** (`_get_connection()` during construct). So the leak **pre-existed on main** and the upgrade's careful full-suite run merely **surfaced** it — it is NOT an upgrade regression. The lazy-init fix is unchanged and still correct (it closes a pre-existing leak at root; main inherits the fix via PR #90). The store.py comment + PR #90 body were corrected; journal/0013 records the correction (journal/0012 is append-only/immutable). Root cause of the error: the pre-upgrade baseline (journal/0011) never recorded a warning count, so "newly-introduced" was assumed rather than verified — the inverse of the `zero-tolerance.md` Rule 1c "verify before claiming pre-existing-status" discipline.

## Verification (re-derived, not self-reported)

- Full suite: **1864 passed, 9 skipped, 3 xfailed, 0 warnings, coverage 91%** (= pre-upgrade baseline). Collection: 1876 collected, 0 errors. mypy + pyright clean (py3.13).
- User-flow walk (`user-flow-validation.md` MUST-1): `envoy posture --principal walk-test-principal` → lifecycle log `SQLitePostureStore initialized → … → SQLitePostureStore closed`, output `Autonomy level: SUPERVISED`. `build_library_nexus` → handlers register HTTP+CLI+MCP, `app closed cleanly`.

## Round log

- **Round 1** (3 parallel agents: reviewer + security-reviewer + spec-compliance analyst): 0 CRITICAL/HIGH. LOWs:
  - reviewer LOW-1 — `assert` stripped under `python -O` → **FIXED** (typed `RuntimeError` guard, Rule 3a; `# pragma: no cover` defensive-unreachable).
  - reviewer LOW-2 — pyproject comment conflated `cryptography` (direct-declared, line 47) with the `[trust]` extra → **FIXED** (comment clarified).
  - analyst LOW-1 — plan's "keep extras unchanged" stale vs `[trust]` → **reconciled** in `01-scope-and-plan.md`.
  - security LOW — `sqlite_perms.py:23-30` WAL/SHM transient world-readable window on the 3 sibling stores → **pre-existing, NOT introduced** (lazy-init touched no query/write path); already tracked in-code; out of scope for this PR (trust-store workstream item).
- **Round 2** (post-fix): full suite green, 0 warnings, marker scrub clean, mypy+pyright clean → **CLEAN**.
- **Round 3** (final mechanical confirmation): collection 0-err, marker scrub clean, lifecycle parity intact → **CLEAN**.

→ 2 consecutive clean rounds. Criteria 4 (spec 100% AST/grep-verified — see `.spec-coverage-v2.md`), 5 (no new modules; changed-module covered), 6 (0 mock data — N/A backend), 7 (no new semantic-harness assertions) all hold.

## Open question for the human

F4: file the `Unclosed AsyncLocalRuntime` upstream issue now (verified current → no staleness) OR keep suppressed? Filing is human-gated (`upstream-issue-hygiene.md` Rule 1; drafting allowed, submission needs approval). Recommend filing — real, reproducible, de-risks Nexus work. Awaiting go/no-go.

## Next (deferred to human gate)

1. Push `chore/kailash-upgrade` + open PR (shared-state action — human-gated per `/autonomize` Prudence). CI: full matrix WILL fire (`pyproject.toml`+`uv.lock` are code-paths); `main` ruleset has empty bypass so even `--admin` can't merge over red CI.
2. `/codify` — lift this into `journal/0012-DECISION-…` via the codify-lease flow.
3. Wave-2 batch-2 value-rank (S8e/S9a vs M1 conformance families vs `init` S4i).
