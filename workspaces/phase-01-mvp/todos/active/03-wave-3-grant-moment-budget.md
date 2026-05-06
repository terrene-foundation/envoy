# 03 — Wave 3: Grant Moment + Budget

**Purpose:** Build Grant Moment (8 modules) and Budget (multi-window with UTC-only resets per disposition #1). Wave 3 converges on EC-2 (Grant Moment 3 resolution shapes E2E with cascade revocation).

**Source authority:** `02-plans/01-build-sequence.md` § Wave 3 + shards 10 / 12.

**Depends on:** Waves 1 + 2.

---

## T-03-50 — Build envoy/grant_moment/state_machine + signed_consent + resolution

**Implements:** `specs/grant-moment.md`

**Source:** Shard `01-analysis/10-grant-moment-implementation.md` § 3 steps 1-3.

**Steps:**

1. State machine M0→M4 — `GrantMomentState` enum + transition table per spec § State machine.
2. `SignedConsentBuilder` — `GrantMomentRequest` + `GrantMomentResult` JCS+NFC canonicalization; signing via `delegation_key`.
3. `ResolutionShape` × 3 (Approve / Decline / ApproveWithModification) — maps to spec's 4 decisions.

**Capacity check:** ~350 LOC; 6 invariants (M0→M4 transition table; JCS+NFC canonicalization; delegation_key signing; 3-shape resolution mapping; signed-consent 3-artifact wire form; M3 branching by ResolutionShape); 3 call-graph hops.

**Tests added:** `tests/tier1/test_grant_moment_state_machine_transitions.py`.

**Blocks on:** T-01-12 (Trust) + T-01-18 (Ledger) + T-01-10 (Envelope).

**Estimate:** 0.75 session.

---

## T-03-51 — Build envoy/grant_moment/out_of_envelope + channel_handoff

**Source:** Shard 10 § 3 steps 4-5.

**Steps:**

1. `OutOfEnvelopeDetector` — interceptor wrapping every Kaizen tool-call dispatch.
2. `ChannelHandoff.dispatch()` — function-call contract to channel adapters; primary-channel binding check.

**Capacity check:** ~250 LOC; 4 invariants (interceptor wraps every tool-dispatch; primary-channel binding check; channel-handoff function-call contract; idempotent on retry); 3 call-graph hops.

**Blocks on:** T-03-50.

**Estimate:** 0.5 session.

---

## T-03-52 — Build envoy/grant_moment/cascade_orchestrator + plan_suspension_bridge

**Source:** Shard 10 § 3 steps 6-7.

**Steps:**

1. `CascadeRevocationOrchestrator` — wraps upstream `cascade_revoke`; verifies `verify_cascade_complete`. Critical for EC-8 (Day-1 grant revoked from Day-6 child grant on different channel).
2. `PlanSuspensionBridge` — typed-event channel between Boundary Conversation (T-02-43) and Grant Moment.

**Capacity check:** ~200 LOC; 4 invariants (cascade BFS reaches every descendant; verify_cascade_complete contract; bridge event types; replay safety); 3 call-graph hops.

**Tests added:** `tests/tier2/test_cascade_revocation_orchestrator_wiring.py`; `tests/tier2/test_plan_suspension_bridge_wiring.py`.

**Blocks on:** T-03-50 + T-01-14 (Trust cascade) + T-02-43 (Boundary suspension).

**Estimate:** 0.5 session.

---

## T-03-53 — Build envoy/grant_moment/novelty + 10 typed errors

**Source:** Shard 10 § 3 steps 8-9.

**Action:** `NoveltyClassifier` (novel / familiar_repeat / high_stakes); 10 typed errors per spec § Error taxonomy.

**Capacity check:** ~150 LOC; 2 invariants (3-class classification; 10-error taxonomy); 1 call-graph hop.

**Blocks on:** T-03-50.

**Estimate:** 0.25 session.

---

## T-03-54 — Wire envoy/grant_moment/ (Tier 2)

**Action:**

- `tests/tier2/test_grant_moment_orchestrator_wiring.py`.
- `tests/tier2/test_out_of_envelope_detector_wiring.py`.
- `tests/tier2/test_signed_consent_builder_byte_identity.py` — crypto round-trip per `rules/orphan-detection.md` Rule 2a.

**Acceptance:** Green against real Trust store fixtures (cascade BFS verification needs real fixtures). NO mocking.

**Blocks on:** T-03-50 through T-03-53.

**Estimate:** 0.5 session.

---

## T-03-55 — Acceptance EC-2 Tier 3: 3 resolution shapes + cascade

**Implements:** EC-2 acceptance gate per `02-plans/02-test-strategy.md`.

**Action:**

- `tests/tier3/test_grant_moment_three_resolution_shapes.py` — Approve / Decline / ApproveWithModification execute end-to-end.
- `tests/tier3/test_grant_moment_cascade_revocation_cross_channel.py` — Day-1 grant + Day-6 child grant on different channel; revocation reaches descendant.

**Acceptance:** All 3 shapes E2E with cascade revocation. Cascade reaches every descendant in 3-deep delegation tree.

**Blocks on:** T-03-50 through T-03-54.

**Estimate:** 0.5 session.

---

## T-03-60 — Build envoy/budget/multi_window + orchestrator

**Implements:** `specs/budget-tracker.md`

**Source:** Shard `01-analysis/12-budget-tracker-implementation.md` § 3 steps 1-2.

**Steps:**

1. `MultiWindowBudget` — 5 `BudgetTracker` instances per ceiling window (per-call / session / hour / day / month) with `principal_id` keying.
2. `EnvoyBudgetOrchestrator` facade — `reserve_for_call` / `record_for_call` / `check` / `lower_velocity_limit` / `raise_velocity_limit` (refused inline).

**Capacity check:** ~300 LOC; 5 invariants (5-window decomposition; per-call atomicity; reserve-then-record contract; velocity-limit lower-only; principal_id keying); 3 call-graph hops.

**Tests added:** `tests/tier1/test_budget_current_period_key_pure.py`.

**Estimate:** 0.5 session.

---

## T-03-61 — Build envoy/budget/threshold_dispatcher + reset_scheduler (UTC-only)

**Source:** Shard 12 § 3 steps 3-4.

**Steps:**

1. `ThresholdDispatcher` — async task queue; collects under upstream lock, dispatches outside lock; routes through Grant Moment (T-03-50).
2. `BudgetResetScheduler` — pure-function `current_period_key(window, at_time)`; per-call/session/hour/day/month reset semantics. **UTC-only resets** per disposition #1 (`journal/0005`) — IANA timezone fix deferred to Phase 02 (`11-phase-02-handoff.md` T-11-01).

**Capacity check:** ~250 LOC; 5 invariants (collect-under-lock-dispatch-outside; UTC-only reset boundary; reset-key determinism; threshold-fire idempotency; Grant Moment routing); 3 call-graph hops.

**Blocks on:** T-03-60 + T-03-50 (Grant Moment).

**Estimate:** 0.5 session.

---

## T-03-62 — Build envoy/budget/anomaly_detector + ledger_emitter

**Source:** Shard 12 § 3 steps 5-6.

**Steps:**

1. `AnomalyDetector` — single-call > 50% session; 5-calls-at-ceiling-in-1-min.
2. `LedgerEmitter` — single-point filter for `budget_threshold_crossed` + `budget_reservation_record` entries.

**Capacity check:** ~180 LOC; 4 invariants (anomaly thresholds deterministic; emitter single-point; entry types canonical; principal_id propagated); 2 call-graph hops.

**Blocks on:** T-03-60 + T-01-18 (Ledger).

**Estimate:** 0.25 session.

---

## T-03-63 — Wire envoy/budget/ (Tier 2)

**Action:** `tests/tier2/test_envoy_budget_orchestrator_wiring.py` — exercises threshold-fire → Grant Moment → resolution → budget mutation chain end-to-end.

**Acceptance:** Green against real Ledger + real Grant Moment + real Trust store. NO mocking.

**Blocks on:** T-03-60 through T-03-62.

**Estimate:** 0.5 session.

---

## Wave 3 milestone gate

Per `02-plans/01-build-sequence.md` § 3 Milestone 3:

- All 3 resolution shapes execute E2E.
- Cascade revocation reaches every descendant in 3-deep delegation tree.
- EC-4 ledger tampering battery (T-06-103 + T-06-104) green — verifier detects every form.
- EC-9 separate-codebase verifier passes (T-06-105).

**Wall-clock estimate:** ~2 sessions (Grant Moment 2.5 || Budget 1.5 in worktrees).

---

## Cross-references

- Build sequence: `02-plans/01-build-sequence.md` § Wave 3
- Primitive shards: `01-analysis/{10,12}-*-implementation.md`
- Timezone disposition: `journal/0005-DECISION-todos-opening-dispositions.md` § Disposition #1
- Verifier: `06-side-channel-verifier.md`
