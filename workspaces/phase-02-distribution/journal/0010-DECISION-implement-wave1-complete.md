---
type: DECISION
date: 2026-06-09
project: phase-02-distribution
phase: implement
topic: /implement Wave-1 complete — S1 + S4s + S8 landed; reviews APPROVE; full suite green
tags:
  [
    implement,
    wave-1,
    verification,
    review-gates,
    conformance,
    substrate,
    registry,
  ]
---

# 0010 — DECISION: /implement Wave-1 complete (S1 + S4s + S8)

The three dependency-free Wave-1 roots were implemented in parallel worktrees, reviewed (both gates APPROVE, 0 CRIT/0 HIGH), merged into the integration branch `feat/phase-02-wave-1`, and verified green against the full suite in the complete `.venv` env.

## Per-shard verification records (per /implement Step 7)

### S1 — WS-1 conformance harness skeleton (`feat/s1-ws1-conformance-harness`, 3 commits)

- **Plan ref:** `todos/active/01-m1-ws1-runtime-pluggability.md` §S1 — all 4 acceptance criteria met.
- **Shipped:** `envoy/runtime/contract_tier.py` (`@byte_identical`/`@semantically_equivalent` decorators + `assert_all_methods_tagged` fail-closed gate; all 31 Protocol methods tagged — 29 byte-identical, 2 semantic), `envoy/runtime/dispatch_observation.py` (deterministic cross-runtime hook), `envoy/runtime/conformance/` + `tests/conformance/harness.py` (parametrized over `get_runtime()`, byte-identity hash-equality scorer with field-localized diff).
- **Journal constraints:** E1–E7 + N1–N6-structured = byte-identical (journal/0004 R3); N4 rendered-text = semantic, Phase-03 — honored (S2c scorer forbids N4-text probe in Phase-02).
- **Scope:** did NOT wire rs-bindings (S2a). **Tests:** 18/18.
- **Spec:** orchestrator added "Contract-tier enforcement (machine-readable)" subsection to `specs/runtime-abstraction.md` (code-first, describes shipped mechanism).

### S4s — WS-6 store-backed SessionRouter (`feat/s4s-ws6-store-substrate`, 3 commits)

- **Plan ref:** `02-m2-ws6-durable-substrate.md` §S4s — Build + Wire criteria met.
- **Shipped:** `envoy/runtime/session.py` (greenfield `SessionRouter` re-opening two durable projections — pending-grant sub-store + SessionObservedState region — file-backed SQLite + OS-keychain Ed25519 key, mirroring `ledger/bootstrap.py`; monotonic `version` column for S4r; 0o600 + WAL-sibling perms; parameterized SQL; typed fail-closed guards).
- **Scope:** STORE only — did NOT build rendezvous (S4r)/init (S4i)/grant (S4g). **Tests:** 17/17 (cross-process read-back for both regions, real SQLite CHECK constraint).
- **Spec:** S4s agent landed `specs/session-runtime.md` code-first (deep-dive open-Q2 decision: dedicated keychain-gated sub-store, NOT materialized-index-over-ledger) + registered in `_index.md`.

### S8 — WS-4 steward quorum + FV registry (`feat/s8-ws4-steward-quorum-registry`, 4 commits)

- **Plan ref:** `03-m3-ws4-library-skill-ingest.md` §S8 — EC-S8.1–8.7 met.
- **Shipped:** `envoy/registry/steward_quorum.py` (`verify_steward_quorum` built ONCE — single-helper grep gate; 2-of-N Ed25519, distinct keys, subtractive revocation, fail-closed), `storage.py`/`library_app.py` (Nexus FV registry, content-addressed by `sha256(canonical_bytes())`, framework-first `@app.handler`), `fv_resolver.py` (re-hash + re-quorum-verify locally against pinned keys; cache never a trust bypass).
- **Scope:** did NOT build S8e/S9. **Tests:** 24/24 (real Nexus registry, no transport mocking).

## Review gates (MANDATORY, per agents.md)

- **reviewer:** APPROVE — 0 CRIT/0 HIGH. Branches merge clean (zero conflicts). The 2 reported "diagnostics" verified NON-ISSUES (bytes/str coerces in the Rust binding; `session.py:121` is legitimate defensive validation).
- **security-reviewer:** APPROVE — 0 CRIT/0 HIGH. S8 quorum sound on all 5 audited properties; no fail-open anywhere. Surfaced 3 MED untrusted-input-bounds hardening items.

## Same-session hardening + post-merge fixes (zero-tolerance / Rule 4)

- **S8 sec-hardening (Rule 4, same-bug-class, fixed pre-merge, commit `0d43008`):** MED-2 verify-cost cap (≤64 sigs), MED-3 publish input-validation + air-gapped-only doc, MED-1 offline freshness `(id_version, content_hash)` keying + `published_at` high-water + `StaleOfflineTemplateError`. +15 regression tests.
- **Post-merge regression fix (commit `be9922e`):** the MED-1 fix hard-required `published_at`, KeyError-ing clients on the prior wire shape (broke `test_t020_envelope_template_supply_chain`). Fixed to degrade gracefully when absent (per MED-1 design intent); all None-comparisons guarded.
- **Upstream warning disposition (commit, pyproject):** scoped-suppressed the kailash `Instance-based API usage` UserWarning (SDK-internal, from framework-first `@app.handler`); upstream-file candidate (human-gated).

## Final verification (complete `.venv` env, `uv run pytest`)

- **tier1/2/integration/regression/sdk:** 1707 passed, 9 skipped, **0 warnings, 0 failed**.
- **tier3/e2e:** 51 passed, 3 xfailed.
- **Total: 1758 passed, 9 skipped, 3 xfailed, 0 failed.** mypy + ruff clean on all new modules.

## Env discovery (institutional — journal/0009)

Tests MUST run via `uv run pytest` / `.venv/bin/python -m pytest` (Python 3.13 with `dataflow`/`pytest`/`nexus`). The global pyenv lacks the `kailash[dataflow]` extra → false-red collection. Per `rules/python-environment.md` MUST-1.

## Disposition

Wave 1 landed on the integration branch + full suite green + both gates APPROVE. Next: PR `feat/phase-02-wave-1` → main + admin-merge; then Wave 2 (S2a rs-bindings adapter, S4r rendezvous, S4i init, etc.) per the DAG.

## For Discussion

1. **Counterfactual:** had the post-merge full-suite run been skipped (trusting the agents' green slice-tests), the T-020 regression from the MED-1 hardening would have shipped to main — the slice-tests didn't exercise the prior-wire-shape client. What makes the post-merge full-suite run non-skippable as a gate? (It's the only run in the complete env over the merged tree.)
2. **Data:** S8's `ContentAddressedStore` is an in-process dict (reviewer MED, deferred-by-design) vs the DataFlow `@db.model` the framework-first mandate names — confirm the phase boundary (Foundation-operated registry server state, multi-process deferred) before the registry is network-exposed.
