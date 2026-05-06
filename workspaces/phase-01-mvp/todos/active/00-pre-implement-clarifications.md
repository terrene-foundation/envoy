# 00 — Pre-implement clarifications

**Purpose:** Capture the 12 MED carry-forward items + 4 human-disposition baselines as todos consumed BEFORE any /implement primitive opens. Most items here are already applied as doc edits at /todos opening (delegated to a background agent); this file is the canonical record of what was applied and where the remaining work is owned.

**Source authority:**

- `04-validate/round-4-implementation-comprehensive.md` § 13 (12 MED carry-forward table)
- `journal/0005-DECISION-todos-opening-dispositions.md` (4 human dispositions)
- `journal/0003-GAP-budget-ceiling-timezone.md` (timezone HIGH disposition)

---

## T-00-01 — Apply 12 MED doc edits (PRE-IMPLEMENT)

**Status:** IN PROGRESS — delegated to background agent at /todos opening (2026-05-05).

**Dispositions** (per round-4 § 13):

| MED ID  | File                                                           | Edit                                                                                                                                                                                |
| ------- | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1-M-01 | `specs/mvp-build-sequence.md` L128                             | Reconcile 11-subcommand list to match shard 19 § 3.4 (`init,chat,ledger,shamir,digest,grant,posture,connection,model,version` + Phase 02 stubs `upgrade,uninstall --destroy-vault`) |
| R1-M-02 | `02-plans/02-test-strategy.md`                                 | Add Tier 2 test entry `test_envoy_model_router_chat_async_routing.py` asserting `LlmDeployment.chat_async()` route per shard 13 § 7.1 HOLD                                          |
| R1-M-03 | `02-plans/03-package-skeleton.md` § 2.2                        | Pin typed-error import contract: every primitive's `errors.py` re-exports types at package facade                                                                                   |
| R1-M-04 | `02-plans/03-package-skeleton.md` § 5                          | Add §5.1 tenant-isolation consolidated rule citing `rules/tenant-isolation.md` Rules 1+2                                                                                            |
| R1-M-05 | `02-plans/03-package-skeleton.md` § 2                          | Add `envoy/observability/` directory with `metrics.py` + `tracing.py`                                                                                                               |
| R2-M-01 | `01-analysis/17-foundation-health-heartbeat-decision.md` § 7.2 | Fix BET-tag factual error: heartbeat de-scope falsifies BET-5 (cohort-floor mechanic), not BET-3/12; rename misnamed BET-5                                                          |
| R2-M-02 | `01-analysis/05-trust-store-implementation.md` § 4             | Add explicit vault lifecycle: `unlock(passphrase)` / `lock()` / `__aexit__` / `_idle_timer_reset()` / `VaultLockedError`                                                            |
| R2-M-03 | `01-analysis/04-envelope-compiler-implementation.md` § 4       | Add explicit "sort `authored_constraints` lexicographically at construction" step                                                                                                   |
| R2-M-04 | `01-analysis/05-trust-store-implementation.md` § 4             | Add explicit "route delegation through `TrustOperations.delegate(...)` 10-step verification" callout                                                                                |
| R2-M-05 | `01-analysis/04-envelope-compiler-implementation.md` § 4       | Add explicit "propagate `IntersectConflictError` to caller; never silently fall back" disposition                                                                                   |
| R3-M-01 | `02-plans/02-test-strategy.md` § EC-4                          | Add non-adjacent (i, j) reorder case to mutation-battery parametrize                                                                                                                |
| R3-M-02 | `specs/independent-verifier.md` L35                            | Reconcile segment-boundary `algorithm_identifier` to 4-key form; shard 6 serializer extension tracked in T-01-21                                                                    |

**Acceptance:**

- Background agent returns confirmation list with each MED ID + edited file path.
- Re-grep on `~/repos/dev/envoy/workspaces/phase-01-mvp/04-validate/round-4-implementation-comprehensive.md` produces no carry-forward residual after edits land.

**Blocks:** All Wave 1 implementation todos (the corrected docs are read by every Wave 1 todo).

---

## T-00-02 — Capture 4 human dispositions in build-sequence plan

**Status:** APPLIED at /todos opening — see `journal/0005-DECISION-todos-opening-dispositions.md`.

**Dispositions:**

1. **Timezone Option A** — UTC-only resets in Phase 01; IANA fix deferred to Phase 02 entry checklist (`11-phase-02-handoff.md`).
2. **Heartbeat de-scope confirmed** — 5 stubs only (R2-H-02 partition); shard 17 § 7.3 lines 224-230 is canonical.
3. **Boundary Conversation timing** — 25min EC-1 ship gate (acceptance pass-fail); 15min target (UX aspirational; surfaced in /codify).
4. **Independent verifier language** — Python first (Phase 01 EC-9 minimum); Rust sibling stretch (BET-3 strengthening; non-blocking).

**Acceptance:**

- Journal entry `0005-DECISION-todos-opening-dispositions.md` exists.
- Disposition #1 propagates to `04-wave-4-channels-digest.md` budget-tracker todo (UTC-only reset_scheduler).
- Disposition #3 propagates to `02-wave-2-authorship-shamir-boundary.md` Boundary Conversation Tier 3 acceptance (25min budget, 15min surfaced).
- Disposition #4 propagates to `06-side-channel-verifier.md` (Python required + Rust stretch sections).

---

## T-00-03 — Confirm Phase 02 entry-checklist scope

**Status:** PENDING — produces input to `11-phase-02-handoff.md`.

**Action:** Enumerate Phase 02 entry-checklist items inherited from Phase 01:

1. **IANA timezone fix** (Option B) — adds `per_day_ceiling_timezone: str` field to `EffectiveEnvelope.financial`; triggers MUST Rule 5b 37-sibling re-derivation.
2. **Foundation Health Heartbeat full impl** — un-stub the 4 PhaseDeferredError modules; STAR/Prio + OHTTP + signed-consent + registry handshake.
3. **Connection Vault third-party OAuth** — full OAuth flows (currently direct API-key paste only).
4. **kailash-rs-bindings adapter wiring** — wire the runtime adapter slot per ADR-0001 phase migration table; `envoy/runtime/kailash_rs_bindings.py` from `RuntimeBackendNotWired` to active.
5. **Foundation board + counsel + trademark gates** — external (per `briefs/00-phase-01-mvp-scope.md` § "External-gate carryover").

**Acceptance:** `11-phase-02-handoff.md` lists each item with rationale, originating Phase 01 source, and pre-condition for Phase 02 unfreeze.

---

## Capacity check

This file = 3 todos, all administrative/clarification. Each ≤50 LOC of edits. Within budget by every axis.

---

## Cross-references

- 12 MED carry-forward: `04-validate/round-4-implementation-comprehensive.md` § 13
- 4 human dispositions: `journal/0005-DECISION-todos-opening-dispositions.md`
- Timezone GAP: `journal/0003-GAP-budget-ceiling-timezone.md`
- Phase 02 handoff: `11-phase-02-handoff.md` (this directory)
