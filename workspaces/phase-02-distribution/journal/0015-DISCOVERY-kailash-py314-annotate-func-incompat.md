---
type: DISCOVERY
date: 2026-06-10
created_at: 2026-06-10T16:25:00Z
author: co-authored
session_id: continue-from-upgrade
project: phase-02-distribution
topic: kailash 2.29.3 Kaizen Signature breaks on Python 3.14.3 (__annotate_func__ rename)
phase: implement
tags: [environment, kailash, python-3.14, pep-749, upstream-candidate, ci]
---

# DISCOVERY — kailash 2.29.3 breaks on Python 3.14.3 (`__annotate_func__`)

## What happened

During the S4i shard, the worktree's `uv sync` built its venv on Python
3.14.3 (newest available; the repo had no `.python-version` pin). Every
class-based Kaizen `Signature` then failed at `__init__` with
`ValueError: Either define fields as class attributes or provide
inputs/outputs` — including the PRE-EXISTING regression canary
`tests/tier2/test_boundary_conversation_per_state_ledger_entries.py`,
which proved the breakage was environmental, not the shard's code.

## Root cause

`kailash.utils.annotations.get_namespace_annotations` looks up the PEP 749
class-namespace annotations callable under the name `__annotate__`. Python
3.14 final renamed that callable to `__annotate_func__` (and the dict form to
`__annotations_cache__`). On 3.14.3 the helper finds nothing, returns `{}`,
and every class-based Kaizen `Signature` silently loses its declared fields —
the loud `ValueError` only fires at first instantiation.

## Fixes shipped (PR #93)

1. `.python-version` pinned to `3.13` — an unpinned `uv sync` on a machine
   where 3.14 is newest silently builds a broken venv.
2. CI: the pin then broke the test matrix in a second-order way — the
   matrix's `uv sync --extra dev --python 3.11` built a 3.11 venv, but the
   next bare `uv run mypy` step read `.python-version` (3.13), re-synced the
   venv to 3.13 WITHOUT dev extras, and failed with `Failed to spawn: mypy`.
   Fixed with job-level `UV_PYTHON: ${{ matrix.python-version }}` in
   `.github/workflows/tests.yml` so the matrix interpreter wins over the pin
   for every uv invocation.

## Trap (for future sessions)

`uv run` without an explicit interpreter RE-SYNCS the project venv to
`.python-version` — including dropping extras the previous sync installed.
Any workflow or script that syncs with one `--python` and then runs bare
`uv run` steps is exposed. `UV_PYTHON` (env) or `--python` (flag) on every
invocation is the structural defense.

## Upstream disposition (human-gated)

This is a real kailash-py defect (Python 3.14 support). RECOMMENDATION:
file an upstream issue against the kailash-py SDK repo — affected API
surface `kailash.utils.annotations.get_namespace_annotations` /
Kaizen class-based `Signature`; minimal repro is a 5-line class-based
Signature under Python 3.14.3; severity HIGH on 3.14 (every class-based
Signature unusable), NONE ≤3.13. Per `rules/upstream-issue-hygiene.md`
MUST-1 the filing requires explicit user approval in-session and a
Rule-3-shaped body (no downstream context). NOT filed this session — no
approval yet. Tracked as ledger item P10.

## Pre-existing failure discipline note

The 3.14 breakage was found via zero-tolerance Rule 1 (the regression canary
failed in the worktree; the agent diagnosed root cause rather than skipping).
The fix was environment alignment + pin, not a code workaround — kailash
itself is pinned at 2.29.3 and the upstream fix is kailash's to ship.
