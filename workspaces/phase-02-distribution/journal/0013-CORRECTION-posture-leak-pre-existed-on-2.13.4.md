# 0013 — CORRECTION — the 23 posture-store ResourceWarnings PRE-EXISTED on 2.13.4

**Date:** 2026-06-10 · **Corrects:** journal/0012 (append-only — this entry is the correction, 0012 stays immutable).

## What 0012 claimed (wrong)

journal/0012 Delta 3 + the source comment + PR #90 body stated that kailash **2.29.3 introduced** the eager posture-store connection ("2.13.4's `SQLitePostureStore.__init__` did not open eagerly"), implying the 23 `unclosed database` ResourceWarnings were an **upgrade regression**.

## What is actually true (verified)

The 23 warnings **PRE-EXISTED on main (kailash 2.13.4)**. Evidence, gathered 2026-06-10 while fixing the pre-existing ruff lint (PR #92) on a branch off `main`:

1. The full suite on a **2.13.4** venv (main's `uv.lock`) produces the **identical 23 `unclosed database` warnings**.
2. `import kailash; kailash.__version__` → `2.13.4` on that branch (confirmed the venv was the old family, not 2.29.3).
3. A `PYTHONTRACEMALLOC` run of `test_r2_h_01 ... test_translator_does_not_mutate_input` on 2.13.4 reproduces the **construct-time** posture-store leak: `_get_connection()` → `sqlite3.connect()` fires during `TrustStoreAdapter(...)` construction, with no `initialize()`/`close()` called. So 2.13.4's `SQLitePostureStore.__init__` opens a connection eagerly **too** — not just 2.29.3.

Therefore the leak is **pre-existing test-hygiene debt** (test fixtures `return` a `TrustStoreAdapter` without `await close()`, leaking the construct-time posture-store connection on BOTH kailash versions). The kailash-2.29.3 upgrade's careful full-suite run **surfaced** it; it did not introduce it.

## What stays correct

- The **lazy-init fix is unchanged and still correct** — it defers `_posture_store` construction past construct-only callers, closing a pre-existing leak at root (main inherits it via PR #90). On 2.29.3 + lazy-init the suite is 0-warning.
- The other two deltas (the `[trust]` extra; dataflow 2.7.7→2.11.3) are genuinely upgrade-related and unaffected by this correction.

## Corrected artifacts

- `envoy/trust/store.py` lazy-init comment — commit `4b69ec3` on `chore/kailash-upgrade` (PR #90).
- PR #90 description — edited (delta 3 now reads "pre-existing on 2.13.4; surfaced, not introduced").
- `workspaces/kailash-upgrade/04-validate/redteam-convergence.md` — Correction note appended (row 3 + a post-convergence note).

## Root cause of the error (process note)

The pre-upgrade baseline (journal/0011, Wave-2 batch-1) recorded "1864 passed, coverage 91.24%, mypy+pyright clean" but **no warning count**. When the 23 warnings appeared during the upgrade's suite run, "newly-introduced by the upgrade" was **assumed** rather than verified against the 2.13.4 baseline. This is the inverse of `zero-tolerance.md` Rule 1c's discipline (which requires verifying _before_ claiming "pre-existing"): here a "newly-introduced" claim was made without verification. The cheap check that would have caught it — re-running the suite on the old deps, or a tracemalloc on 2.13.4 — is exactly what surfaced the truth later. Lesson: a warning-count claim about "before vs after" requires running BOTH, not inferring from an unrecorded baseline.
