---
type: DISCOVERY
date: 2026-06-09
project: phase-02-distribution
phase: implement
topic: /implement Wave-1 baseline green; tests MUST run via `uv run` (.venv 3.13), not the global pyenv
tags: [implement, baseline, environment, uv, test-once]
---

# 0009 — DISCOVERY: /implement baseline green; the `uv run` environment requirement

## Baseline (test-once protocol)

Established the pre-Wave-1 baseline on the Phase-01 codebase (HEAD `57ab529`): **collection clean (1717 tests collected)**, **tier1 872 passed in 15s**. The codebase is in a good state to build Wave 1 (S1/S4s/S8) on top of. This is the single baseline per `rules/testing.md` § Test-Once Protocol.

## Critical environment finding (institutional knowledge)

`pytest` MUST run via **`uv run pytest`** — the project's `uv`-managed `.venv` (Python **3.13**, with the `kailash[...,dataflow,...]` extras installed). The global pyenv interpreter (3.12.9) has `kailash` 2.29.3 but NOT the top-level `dataflow` module, so a bare `python -m pytest` fails at collection with `ModuleNotFoundError: No module named 'dataflow'` (`envoy/daily_digest/aggregator.py:41`, `renderer.py:43`, `budget/ledger_emitter.py:38` all import `from dataflow.classification.event_payload import …`).

- **DO:** `uv run pytest tests/...`
- **DO NOT:** `python -m pytest` (wrong interpreter; false-red collection error).

This is NOT a code bug (the imports are correct — `dataflow` is the `kailash[dataflow]` extra per `pyproject.toml:32`); it's an interpreter-selection gotcha. Every `/implement` shard agent + every acceptance gate MUST use `uv run`.

## Disposition

Baseline green → Wave 1 proceeds. S1 (WS-1 conformance harness, critical-path root) launches first as a focused worktree implementation; S4s + S8 follow. The `uv run` requirement is propagated into every shard agent's prompt.

## For Discussion

1. **Counterfactual:** had the baseline been run only via the global pyenv and taken at face value, the `dataflow` collection error would have been "fixed" as a phantom code bug (e.g. rewriting the import) — corrupting working Phase-01 code. What stops a future session from making that exact mistake? (Answer: this entry + the `uv run` propagation; consider a `conftest.py` guard that asserts `dataflow` importability with a pointer to `uv run`.)
2. **Data:** 1717 tests now vs the session-notes' 1705 at Phase-01 convergence — what added the 12? (Likely the F8/F9/F19 redteam-followup tests in PR #83/#85.) Worth confirming none are flaky before Wave-1 churn.
