---
type: DECISION
date: 2026-06-02
created_at: 2026-06-02T02:30:00Z
author: co-authored
session_id: envoy-2026-06-01
session_turn: post-PR73-ci-hardening
project: phase-01-mvp
topic: "CI test gate (mypy + pyright + full pytest + coverage floor) + main ruleset making tests-gate hard-block even --admin"
phase: implement
tags:
  [
    ci,
    test-gate,
    branch-protection,
    ruleset,
    root-cause,
    supply-chain,
    coverage,
    user-gated,
  ]
---

# 0050 — DECISION: CI runs the test gate; `tests-gate` hard-blocks `main` via ruleset

## Context

The shard-C gate review surfaced that the `model` e2e acceptance test had been
**red on `main` for a full PR cycle** (PR #66 wired `model` but never updated the
strict-xfail `REGISTERED_AS_OF_F5` set). Root cause: **GitHub CI never ran the
Python suite** — only `validate.yml` (COC `.claude/` structure) + a Discord
notification. The entire correctness contract (1693 tests, mypy, pyright, the
strict-xfail tripwire) ran ONLY when a human/agent remembered to, with the right
scope. A backstop that only fires when someone pulls the trigger is not a backstop.

User directive (this session): "resolve the caveat properly and also all the
deferred, get them done properly."

## Decision

**The test+type+coverage suite is now an automatic CI gate, hard-required on
`main`.** Delivered across PR #72 (gate) + PR #73 (hardening) + a branch ruleset.

1. **`.github/workflows/tests.yml`** runs on every code PR + push to `main`:
   `uv sync --extra dev` → `mypy envoy/` → `pyright envoy/` →
   `pytest tests/ --collect-only` (orphan Rule 5) →
   `pytest tests/ --cov=envoy --cov-fail-under=90` (all tiers incl. e2e), matrix
   Python 3.11 (floor) + 3.13 (dev latest).

2. **Skip-sentinel required-check pattern.** Jobs: `changes` (path filter) →
   `test` (matrix, runs only when code paths changed) → `tests-gate` (ALWAYS
   runs + reports; passes immediately on doc-only PRs, else asserts the matrix
   succeeded). `tests-gate` is the single stable required-check name — because it
   always reports, a doc-only PR never stalls on a never-reported required check
   (the classic `paths-ignore` + required-check trap).

3. **Ruleset `Require tests-gate on main` (id 17145354, active).** Requires the
   `tests-gate` status check on `refs/heads/main` with **`bypass_actors: []`** —
   so even `gh pr merge --admin` cannot merge over red/absent CI. The classic
   branch protection (`required_pull_request_reviews: 1`, `enforce_admins:false`)
   is UNCHANGED, so `--admin` still bypasses the _review_ requirement. Net:
   **solo-merge is preserved (no second human reviewer needed); only CI is hard.**

4. **Supply-chain + coverage (the deferred items).** Third-party actions
   SHA-pinned (`actions/checkout` v6.0.2, `astral-sh/setup-uv` v8.1.0,
   `dorny/paths-filter` v4.0.1). `pyright` added to the dev extra
   (locked 1.1.410) so `uv run pyright` resolves imports against the project venv
   locally + in CI. Coverage floor 90% (current 90.88%, ratchet 1pt under).

## Alternatives considered

- **`enforce_admins: true` on classic protection** — REJECTED. It would make the
  _review_ requirement apply to admins too, breaking the owner's solo-merge
  (every PR would need a second human approval). The ruleset gives per-rule
  bypass granularity classic protection cannot.
- **Required check on classic protection's `required_status_checks`** — REJECTED.
  Governed by `enforce_admins:false`, so `--admin` would bypass it — no hard block.
- **`paths-ignore` at the trigger + matrix legs as required checks** — REJECTED.
  Doc-only PRs would stall on never-reported required checks. The skip-sentinel
  `tests-gate` aggregator is the structural fix.

## Consequences & follow-up

- Every test + tripwire is now automatically load-bearing; "wired-but-unregistered"
  / "forgot tier-X" / "pre-existing red on main" all surface at the PR.
- **Behavior change for the owner:** code PRs now require `tests-gate` green before
  merge even with `--admin`. Doc-only PRs merge immediately (sentinel passes).
- The ruleset is owner-editable via `gh api repos/<owner>/<repo>/rulesets/17145354`
  if CI is ever broken and an emergency merge is needed.
- **Open follow-up:** 23 pre-existing test warnings surfaced by `--cov` (suite
  hygiene; not made CI-fatal to avoid breaking the gate at introduction). Belongs
  with the F6 redteam-follow-up bucket.

## For Discussion

1. **Counterfactual:** had this gate existed at PR #66, the `model` strict-xpass
   would have blocked that PR — confirming the gate closes the exact class that
   motivated it. Is there any OTHER undetected-red surface on `main` today that a
   first full-suite run would reveal? (The PR #72/#73 runs were green, so: no.)
2. **Data-referencing:** the coverage floor is 90% against 90.88% measured. Should
   the floor ratchet upward automatically (e.g., a periodic bump toward 95%), or
   stay a fixed regression-guard? `rules/testing.md` sets 80% general / 100%
   security-critical — is per-module enforcement (security paths at 100%) worth
   wiring beyond the single global floor?
3. **Should the 23 test warnings be made CI-fatal** (`-W error` with a curated
   allowlist) once triaged, closing the observability-Rule-5 gap at the gate?
