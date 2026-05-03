# 12 — Budget Tracker Implementation

**Document role:** Phase 01 implementation deep-dive for the Budget tracker primitive (shard 12 of /analyze; Group D per `01-shard-plan.md` § 5; depends on shards 4, 5, 6, 8, 10). Establishes the verified upstream provider, the Envoy-new-code orchestrator surface, the threshold-callback → Grant Moment dispatcher, the Ledger-emission contract on threshold crossings, the per-principal partitioning hook for Phase 03 multi-principal, and the budget-reset boundary scheduling. The Budget tracker is the **financial constraint dimension** owner per `02-mvp-objectives.md` § 3 cross-cutting deliverables and the **primary upstream consumer of `set_threshold_callback`** per `specs/budget-tracker.md` § Threshold callbacks.

**Date:** 2026-05-03 (shard 12 of /analyze).
**Status:** DRAFT — load-bearing for shards 11 (Daily Digest aggregates budget velocity history), 13 (Model adapter emits per-call cost from Kaizen `usage_metrics`), 16 (Channel adapters surface budget-warning UX before exhaustion).
**Discipline:** Cite, do not paraphrase frozen specs. Per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, Phase 01 /analyze MUST cite Phase 00 artifacts by path + section, never paraphrase. The shard's question is NEVER "is this spec right?"; it is "given this spec is frozen, how do I wire `kailash-py` to deliver it?" Per `rules/specs-authority.md` MUST Rule 4 + Rule 5b (no spec edits at this shard).

**Capacity check:** 1 primitive, 1 source spec (`budget-tracker.md`), ~6 invariants tracked (microdollar integer-only arithmetic; rising-edge one-shot semantics on custom thresholds; reserve→record atomicity vs threshold-callback ordering; per-principal cache key shape with `tenant_id` placeholder; Ledger atomicity on threshold-crossing emit; reset-boundary FSM determinism), ≤4 cross-primitive references (Grant Moment, Ledger, Boundary Conversation, Model adapter). Within `rules/autonomous-execution.md` budget.

---

## 1. Source spec citation

Frozen spec the Budget tracker implements against (cited; not edited):

- `specs/budget-tracker.md` § Purpose (lines 3–5) — "Financial-dimension ceilings + velocity + session scope + threshold callbacks."
- `specs/budget-tracker.md` § Provenance (lines 7–11) — Source `02-envelope-model.md v3 §3.1 + 05-runtime-abstraction.md v2 §2.1`; threats mitigated `T-093 budget-exhaustion fraud, T-019 velocity-ratchet rubber-stamp`; BETs tested `BET-2 performance through structural governance`.
- `specs/budget-tracker.md` § Data unit (lines 13–15) — "Integer microdollars (1 dollar = 1,000,000 microdollars). No float accumulation." Confirms key design question #1 is a structural invariant, not a design choice.
- `specs/budget-tracker.md` § Ceilings (lines 17–23) — five ceilings keyed in microdollars: `per_call_ceiling_microdollars`, `per_session_ceiling_microdollars` (added per reviewer F-13), `per_hour_velocity_microdollars`, `per_day_ceiling_microdollars`, `per_month_ceiling_microdollars`.
- `specs/budget-tracker.md` § Check shape (lines 25–27) — "100% structural. O(1) to O(log n) sliding-window sum. <5ms target." Implementation MUST NOT regress to O(n) wall-time per check.
- `specs/budget-tracker.md` § Reserve/record pattern (lines 29–31) — `budget_reserve(amount)` before call; `budget_record(reservation, actual)` after. Concurrent reservations sum against ceilings.
- `specs/budget-tracker.md` § Threshold callbacks (lines 33–35) — "`BudgetTracker.set_threshold_callback(threshold_pct, callback)` — invoke when `(committed + reserved) / allocated ≥ threshold`. Used for Grant Moment surfacing. kailash-rs#518 + kailash-py#603." Spec line 35 directly cross-files to the closed kailash-py issue.
- `specs/budget-tracker.md` § Velocity-raise ratchet (T-093 R2-H4, lines 37–39) — "RAISING any velocity limit CANNOT be inline. Requires Weekly Posture Review OR cross-channel Grant Moment with 24h cooling-off. Lowering allowed inline."
- `specs/budget-tracker.md` § Budget-exhaustion fraud defense (T-093, lines 41–45) — per-call ceiling + velocity-limit + session-scope; anomaly detection (single call > 50% of session budget → pause for confirmation); high-velocity pattern detection (5 calls at ceiling in 1min → Grant Moment).
- `specs/budget-tracker.md` § Error taxonomy (lines 47–57) — 7 typed errors: `BudgetExhaustedError`, `VelocityRaiseInlineBlockError`, `AnomalyDetectedError`, `HighVelocityPatternError`, `ReservationExpiredError`, `MicrodollarOverflowError`, `ReservationDoubleRecordError`.
- `specs/budget-tracker.md` § Cross-references (lines 59–66) — explicit forwards to `envelope-model.md` (Financial dimension schema), `runtime-abstraction.md` (`budget_reserve/record/snapshot/velocity_check`), `grant-moment.md` (velocity-raise ratchet flow), `weekly-posture-review.md` (velocity-raise approval ritual), `threat-model.md` (T-019, T-093), `ledger.md` (budget reservation + record entries).
- `specs/budget-tracker.md` § Test location (lines 68–76) — seven test files pre-declared by the spec; binding implementation MUST land all seven in tests/ with the exact names.
- `specs/budget-tracker.md` § Open questions (lines 78–84) — 5 OPEN questions: anomaly threshold calibration (50%); high-velocity 5-calls-in-1-min threshold; non-USD currency precision (Phase 02 i18n); reservation TTL (default 60s? 5min?); cross-session vs intra-session aggregate ceiling rounding (month-boundary handling).

Cross-spec citations (not Budget tracker-owned, but the Budget tracker consumes/emits/reads them):

- `specs/grant-moment.md` § Schema § `GrantMomentRequest` (lines 15–47, cited in shard 10 § 1) — the wire format constructed by the threshold-callback → Grant Moment dispatcher when `claimed/allocated ≥ threshold` fires; signed by `delegation_key` over JCS+NFC canonical form.
- `specs/grant-moment.md` § Velocity-raise ratchet (T-093 R2-H4, lines 94–96) — "velocity-raise CANNOT be approved inline; requires Weekly Posture Review OR cross-channel Grant Moment with 24h cooling-off." The Budget tracker raises `VelocityRaiseInlineBlockError` per `specs/budget-tracker.md` line 52; the Grant Moment receives the ratchet enforcement contract from this spec.
- `specs/envelope-model.md` § Schema § Financial dimension — the envelope-side ceiling values the Budget tracker is constructed from at session start. Per the Envelope compiler (shard 4 § 4), the `EffectiveEnvelope.financial.{per_call,per_session,per_hour,per_day,per_month}_ceiling_microdollars` is the Budget tracker's `allocated_microdollars` source.
- `specs/ledger.md` § Entry envelope schema (lines 14–34, cited in shard 6 § 1.1) — every threshold-crossing emit becomes a Ledger entry; the entry envelope schema is locked at the Ledger layer, not the Budget tracker layer.
- `specs/ledger.md` § Ledger entry schemas (lines 47–91 enumerate 35 types) — Phase 01 emits two new types from the Budget tracker:
  1. `budget_threshold_crossed` — emitted at every `BudgetEvent` (4 cases: `threshold_80`, `threshold_95`, `exhausted`, `custom_threshold`).
  2. `budget_reservation_record` (= reservation + record pair) — emitted at every successful `record()` call so the Ledger captures actual committed spend per intent.
- `specs/runtime-abstraction.md` § `budget_reserve/record/snapshot/velocity_check` — the runtime-side public API the Boundary Conversation, Model adapter, and any Kaizen agent loop all call. The Budget tracker IS the implementation of this runtime contract.

---

## 2. Verified provider citation

Per `03-kailash-py-mvp-readiness.md` § 5 verification protocol — the Budget tracker is **A-grade upstream** at the 2026-04-21 baseline (per § 3 row 9); the freshness gate confirmed ISS-29 / GH#603 closed 2026-04-25T09:16:38Z with PR ref `1b164d93 feat(trust): add BudgetTracker threshold-breach callback API (#603)` and predecessor WIP commits `433bf3dc` (set_threshold_callback API), `17d4305a` (Tier 1 + Tier 2 tests), `eab3d2e0` (CHANGELOG fragment).

### 2.1 Direct providers (verified via path-and-symbol read at `~/repos/loom/kailash-py/`)

| Capability the Budget tracker requires                                         | Provider module                                                                                        | Verified path / lines                                     | Closed ISS / PR                                                                         |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Atomic reserve/record with int microdollars                                    | `kailash.trust.constraints.budget_tracker.BudgetTracker(allocated_microdollars, *, store, tracker_id)` | `src/kailash/trust/constraints/budget_tracker.py:289-399` | n/a (pre-Phase-00)                                                                      |
| Two-phase `reserve(microdollars) → bool` / `record(reserved, actual) → None`   | `BudgetTracker.reserve(...)` lines 405-487; `BudgetTracker.record(...)` lines 489-607                  | same file                                                 | n/a                                                                                     |
| Saturating arithmetic + thread-safe `_lock`                                    | `threading.Lock` line 360; `max(0, ...)` saturating subtract line 530                                  | same file                                                 | n/a                                                                                     |
| Hardcoded 80%/95%/100% threshold callbacks                                     | `BudgetTracker.on_threshold(callback)` lines 681-705                                                   | same file                                                 | n/a                                                                                     |
| **Custom threshold callbacks (the Grant Moment dispatcher hook)**              | **`BudgetTracker.set_threshold_callback(threshold_pct, callback) → handle`** lines 733-839             | same file                                                 | **ISS-29 / GH#603 — closed 2026-04-25; PR commit `1b164d93`**                           |
| Symmetric unregister                                                           | `BudgetTracker.unregister_threshold_callback(handle) → bool` lines 841-872                             | same file                                                 | ISS-29 / GH#603                                                                         |
| Per-record callback (composability hook)                                       | `BudgetTracker.on_record(callback)` lines 707-731                                                      | same file                                                 | n/a                                                                                     |
| Non-mutating `check(estimated_microdollars) → BudgetCheckResult`               | `BudgetTracker.check(...)` lines 620-640                                                               | same file                                                 | n/a                                                                                     |
| Snapshot/restore                                                               | `BudgetTracker.snapshot()` lines 642-656; `from_snapshot(...)` lines 658-679                           | same file                                                 | n/a                                                                                     |
| **SQLite-backed persistence**                                                  | **`kailash.trust.constraints.budget_store.SQLiteBudgetStore`** + `BudgetStore` ABC                     | `src/kailash/trust/constraints/budget_store.py:1-80+`     | n/a                                                                                     |
| Path-validation + 0o600 perms + parameterized SQL                              | `SQLiteBudgetStore` security fields, `budget_store.py:13-22` docstring                                 | same file                                                 | n/a                                                                                     |
| `BudgetEvent` wire format (timestamped, threshold_pct, committed, reserved)    | `BudgetEvent` dataclass lines 175-278 with `to_dict` / `from_dict`                                     | `budget_tracker.py:175-278`                               | ISS-29 / GH#603 (extended `committed`/`reserved` fields per crossing-snapshot contract) |
| `usd_to_microdollars` / `microdollars_to_usd` conversion helpers (NaN-guarded) | `usd_to_microdollars(amount)` lines 1055-1071; `microdollars_to_usd(amount)` lines 1074-1083           | same file                                                 | n/a                                                                                     |

### 2.2 The "rising-edge one-shot" semantics — load-bearing for Grant Moment dispatch

Per `budget_tracker.py:744-751`:

> "The callback fires once -- and only once -- per registration when the predicate `(committed + reserved) / allocated >= threshold_pct` first becomes true after a successful `record()` or `reserve()` call. State oscillation (committed/reserved decreasing below the threshold and crossing it again) does NOT re-fire the callback."

This contract is the structural defense against Grant Moment storm. If a user oscillates around the threshold (e.g. a budget release after a `record()` releases reservations), the callback does NOT re-fire — `_fired_custom_handles` (line 374) is the one-shot guard. **Cross-shard implication for shard 10**: the Grant Moment orchestrator MUST tolerate at most one Grant Moment per (tracker, threshold) per session; subsequent crossings of the same threshold do NOT re-Grant-Moment. The next crossing requires either (a) a reset (next budget reset boundary) or (b) a `unregister_threshold_callback(handle)` + `set_threshold_callback(threshold_pct, new_cb)` to mint a fresh handle and re-arm.

### 2.3 Lock discipline — load-bearing for ordering vs Ledger

Per `budget_tracker.py:528-584`, the `record()` method:

1. Acquires `self._lock` (line 528).
2. Saturating subtract reserved + commit actual (lines 530-533).
3. Append transaction log entry (lines 535-544).
4. **Collect** threshold events under lock (lines 556-560) — does NOT fire callbacks.
5. Capture snapshot under lock if `_store` is set (lines 562-567).
6. Release lock.
7. **Dispatch** threshold callbacks OUTSIDE lock (lines 571-579, 582-584).
8. Save snapshot OUTSIDE lock (lines 587-598).
9. Fire `on_record` callbacks OUTSIDE lock (lines 600-607).

This collapses key design question #4 (threshold-fire vs Ledger-emit ordering). The collect-under-lock + dispatch-outside-lock pattern is the structural defense against deadlock when callbacks re-enter the tracker. **Envoy-side requirement**: the threshold-callback → Grant Moment dispatcher (§ 3.2 below) MUST NOT re-enter `BudgetTracker.reserve/record/check` from within the callback body — it MUST defer the Grant Moment orchestration to an async task or the next Kaizen turn. Re-entrant calls are tolerated by the lock (RLock would be required), but the `_lock` is `threading.Lock`, not `threading.RLock` (line 360), so a re-entrant call would deadlock. This is the primary correctness invariant for the Envoy dispatcher.

### 2.4 What `kailash-py` does NOT provide — Envoy-new-code surface preview

`kailash-py` does NOT provide:

1. The threshold-callback → Grant Moment dispatcher (the one-shot crossing → `OutOfEnvelopeDetector`-style violation construction → Grant Moment orchestrator dispatch chain).
2. The Ledger entry emission on threshold crossing (`budget_threshold_crossed` and `budget_reservation_record` types per `specs/ledger.md`).
3. The per-principal partitioning of BudgetTracker instances (Phase 03 multi-principal hook).
4. The budget-reset boundary scheduler (when does `allocated` reset for `per_hour` / `per_day` / `per_month` ceilings — the upstream `BudgetTracker` is a **single-allocation** primitive; multi-window reset is Envoy orchestration).
5. The five-window ceiling decomposition (per_call vs per_session vs per_hour_velocity vs per_day vs per_month — the upstream `BudgetTracker` accepts ONE `allocated_microdollars`).
6. The anomaly-detection hooks for T-093 (single call > 50% of session budget; 5 calls at ceiling in 1min).
7. The reservation TTL enforcement (`ReservationExpiredError` per `specs/budget-tracker.md` line 55) — upstream tracks reservation amounts but does NOT track reservation **identifiers** with TTLs.
8. The `MicrodollarOverflowError` int64-bound check at reservation construction time (upstream uses Python `int` which is unbounded; Envoy MUST validate against int64 to match cross-SDK contract per `specs/budget-tracker.md` line 56).
9. The `ReservationDoubleRecordError` idempotency check per reservation_id.

These nine items are the Envoy-new-code surface; § 3 below itemises them.

### 2.5 Indirect-closure PR refs that improve Budget tracker determinism

- **#736** — Kaizen `_calculate_usage_metrics` None prompt_tokens fix (closed in shard 13 dependency chain). Effect: the Model adapter (shard 13) emits per-call cost via Kaizen `usage_metrics` without None-tripping; this is the Budget tracker's primary input source.
- **#707 / #711** — `df.transaction()` context manager (closed; cited in shards 6 and 10). Effect: the (`record()` call + `budget_reservation_record` Ledger row + `budget_threshold_crossed` Ledger row + Grant Moment orchestrator wakeup) tuple can be wrapped atomically by Envoy. A power-loss between these leaves the system in an all-or-none state.
- **#757 / #756** — Unicode byte-vector pinning (closed; cited in shard 6 § 2.2). Effect: Budget tracker JSON snapshots and threshold-event payloads are canonicalized identically Python ↔ Rust, satisfying cross-SDK byte-identity per BET-6.

---

## 3. Envoy-new-code surface

The Envoy-new-code surface is the gap between (a) the upstream `kailash-py` `BudgetTracker` + `SQLiteBudgetStore` primitives and (b) the `specs/budget-tracker.md` 5-window ceiling + reset-boundary + threshold-callback → Grant Moment dispatcher contract.

### 3.1 Module shape: `envoy.budget` composing upstream

The Phase 01 Envoy-new-code surface is a Python package `envoy.budget` exposing the facade `EnvoyBudgetOrchestrator`. The package composes:

- `kailash.trust.constraints.budget_tracker.BudgetTracker` (verified § 2.1) — one instance per (principal_id, ceiling_window) pair (so up to 5 × N_principals trackers in steady state; Phase 01 single-principal collapses to 5 trackers per session).
- `kailash.trust.constraints.budget_store.SQLiteBudgetStore` (verified § 2.1) — single shared store; per-tracker keying via `tracker_id = f"envoy:v1:{principal_id}:{ceiling_window}:{period_key}"`.
- `envoy.ledger.EnvoyLedger.append(...)` (Shard 6 § 4) — single-point write boundary for `budget_threshold_crossed` and `budget_reservation_record` Ledger rows.
- `envoy.grant_moment.GrantMomentOrchestrator.request_grant_moment(...)` (Shard 10 § 3.2 item 1) — invoked from the threshold-callback → Grant Moment dispatcher when a custom threshold fires.
- `envoy.envelope.compiler.EnvelopeCompiler.compile(...)` (Shard 4) — re-pinned at session start to extract financial-dimension ceilings; re-pinned at any envelope mutation (Grant Moment `approve_and_author` / `modify`).

Per `rules/orphan-detection.md` Rule 1 + Rule 3 + `rules/facade-manager-detection.md` Rule 1, `EnvoyBudgetOrchestrator` is the single facade exposed on the `envoy.budget` namespace; every other class in the module is reached through it. The orchestrator is invoked from a production hot path within the Kaizen tool-dispatch interceptor (next to `OutOfEnvelopeDetector` per shard 10 § 3.2 item 4) — every tool call passes through `EnvoyBudgetOrchestrator.reserve_for_call(...)` BEFORE `OutOfEnvelopeDetector.evaluate(...)` to ensure budget-exhaustion fires Grant Moment ahead of envelope-violation Grant Moment when both apply.

### 3.2 Surface to be built (Envoy-new-code)

1. **`envoy.budget.EnvoyBudgetOrchestrator`** — facade with:
   - `.reserve_for_call(estimated_microdollars, *, intent_id) → ReservationHandle | BudgetExhaustedError` — checks all 5 ceilings; returns a `ReservationHandle(reservation_id, expires_at, ceilings_consulted)`.
   - `.record_for_call(handle, actual_microdollars) → None` — finalizes against all 5 ceilings; raises `ReservationExpiredError` / `ReservationDoubleRecordError` per `specs/budget-tracker.md` lines 55-57.
   - `.check(estimated_microdollars) → BudgetCheckResult` — non-mutating multi-window check; returns the **most restrictive** ceiling's check result (the binding window).
   - `.lower_velocity_limit(window, new_microdollars) → None` — inline lowering allowed per spec line 39.
   - `.raise_velocity_limit(window, new_microdollars) → VelocityRaiseInlineBlockError` — inline raising BLOCKED; the orchestrator routes to Weekly Posture Review (Phase 02) OR cross-channel Grant Moment + 24h cooling-off.
   - `.snapshot() → MultiWindowSnapshot` — returns 5 BudgetSnapshots keyed by window.
   - `.subscribe_threshold(window, threshold_pct, on_cross) → handle` — Envoy-side wrapper around `BudgetTracker.set_threshold_callback`; the `on_cross` callback receives an `EnvoyBudgetEvent` extending `BudgetEvent` with `principal_id`, `window`, `period_key`.

2. **`envoy.budget.MultiWindowBudget`** — per-principal struct holding 5 `BudgetTracker` instances:

   ```
   {
     "per_call":           BudgetTracker(per_call_ceiling_microdollars,      tracker_id="envoy:v1:{p}:per_call:{call_id}"),
     "per_session":        BudgetTracker(per_session_ceiling_microdollars,   tracker_id="envoy:v1:{p}:per_session:{session_id}"),
     "per_hour_velocity":  BudgetTracker(per_hour_velocity_microdollars,     tracker_id="envoy:v1:{p}:per_hour:{YYYY-MM-DDTHH}"),
     "per_day":            BudgetTracker(per_day_ceiling_microdollars,       tracker_id="envoy:v1:{p}:per_day:{YYYY-MM-DD}"),
     "per_month":          BudgetTracker(per_month_ceiling_microdollars,     tracker_id="envoy:v1:{p}:per_month:{YYYY-MM}"),
   }
   ```

   The `tracker_id` shape is the **structural defense** required by `rules/tenant-isolation.md` Rule 1 (cache-key tenant-dimension): `principal_id` is in the key from day 1 even though Phase 01 ships single-principal. Per the rule's anti-optimization note: the `principal_id` STAYS in the key even though the `period_key` is unique per period; this is defense-in-depth against a future refactor that replaces the period_key with a tenant-local identifier.

3. **`envoy.budget.ReservationHandle`** — opaque dataclass:

   ```python
   @dataclass(frozen=True)
   class ReservationHandle:
       reservation_id: str          # UUIDv7
       intent_id: str               # links to PhaseARecord (specs/ledger.md two-phase signing)
       reserved_microdollars: int
       reserved_per_window: dict[str, int]   # per-window reservation amount; usually identical, but per_call may differ
       expires_at: datetime         # spec § Open question 4 — Phase 01 disposition: 60s default, configurable
       ceilings_consulted: list[str] # which windows were checked (for audit trail)
       created_at: datetime
   ```

   The `reservation_id` is recorded in the `_recorded_reservations: set[str]` on the orchestrator; double-record raises `ReservationDoubleRecordError` per `specs/budget-tracker.md` line 57.

4. **`envoy.budget.threshold_dispatcher.ThresholdDispatcher`** — the **load-bearing primitive** from key design question #2. Subscribes to the upstream `BudgetTracker.set_threshold_callback` for each (window, default-thresholds=[0.50, 0.80, 0.95, 1.00]) pair; on fire:
   1. Constructs an `EnvoyBudgetEvent(principal_id, window, period_key, threshold_pct, committed_microdollars, reserved_microdollars, allocated_microdollars, observed_at)` from the upstream `BudgetEvent`.
   2. Emits a `budget_threshold_crossed` Ledger entry via `EnvoyLedger.append(...)`.
   3. **Schedules** (does NOT directly call) a Grant Moment fire by enqueuing onto an asyncio task queue. The Grant Moment fire happens in a separate task to avoid deadlocking the upstream `BudgetTracker._lock` (per § 2.3 lock discipline). The async task:
      - Constructs an `EnvelopeViolation(violated_dimension="financial", violated_constraint_id=f"{window}_ceiling", why_asking="budget_threshold_crossed", ...)` per shard 10 § 3.2 item 4 wire shape.
      - Calls `GrantMomentOrchestrator.request_grant_moment(violation, channel)` per shard 10 § 3.2 item 5.
      - Awaits the resolution.
      - On `Approve`: writes a `DelegationRecord` extending the budget OR allowing the violating call (per the resolution shape from shard 10 § 3.2 item 3); IF the user chose "extend budget", a `budget_extended` Ledger entry is emitted alongside the `grant_moment` entry, and `MultiWindowBudget` is reconstructed with the new ceiling.
      - On `Decline`: no budget mutation; a `grant_moment` Ledger entry with `decision="deny"` is the only persistent effect.
      - On `ApproveWithModification`: the user lowered the requested amount inline; the dispatcher reissues `reserve_for_call(modified_amount)` on the multi-window budget.

   This collapses key design question #2 (threshold-callback firing → Grant Moment): the dispatcher is an **async task queue with one-shot crossing predicates upstream**. Re-entrancy is structurally impossible because the Grant Moment orchestration does NOT execute on the upstream callback thread.

5. **`envoy.budget.reset_scheduler.BudgetResetScheduler`** — the **load-bearing primitive** from key design question #5 (reset boundary). Per `specs/budget-tracker.md` § Ceilings (lines 17-23) the five windows have **different reset semantics** that the spec does NOT define explicitly:
   - **`per_call`** — resets at every `record()` for the call. Implementation: a fresh `BudgetTracker(per_call_ceiling_microdollars)` instance is constructed at every `reserve_for_call(...)` invocation; discarded after `record_for_call(...)` completes. NO persistence in `SQLiteBudgetStore` (transient).
   - **`per_session`** — resets at session boundary. Implementation: a fresh tracker per session_id; persisted to `SQLiteBudgetStore` keyed by `tracker_id="envoy:v1:{p}:per_session:{session_id}"` for crash-recovery within session.
   - **`per_hour_velocity`** — resets at the top of every clock hour (UTC). Implementation: `tracker_id` includes `{YYYY-MM-DDTHH}`; on `EnvoyBudgetOrchestrator.reserve_for_call(...)` the scheduler computes the current hour key and either reuses the existing tracker or constructs a fresh one if the hour has rolled over.
   - **`per_day`** — resets at midnight local time (or UTC; see HIGH ambiguity in § 7).
   - **`per_month`** — resets at midnight on the 1st of each month (timezone-disputed; see HIGH ambiguity in § 7).

   The scheduler's `current_period_key(window, *, at_time=None) → str` is a pure function over `at_time`; the orchestrator calls it lazily (at `reserve_for_call(...)` time, not on a wall-clock timer) so reset is event-driven, not threaded. **Determinism on replay** is preserved because the period_key is derived from the call's `intent_id` issued-at timestamp (not wall-clock now) — a Tier 2 replay test can re-execute a 2-day session and recompute identical ledger entries.

6. **`envoy.budget.anomaly_detector.AnomalyDetector`** — implements `specs/budget-tracker.md` § Budget-exhaustion fraud defense (lines 41-45):
   - **Single-call > 50% session budget**: when `reserve_for_call(estimated)` would consume > 50% of `per_session.remaining_microdollars()`, raise `AnomalyDetectedError` and route to Grant Moment with `why_asking="anomaly_detected"`.
   - **5-calls-at-ceiling-in-1-min**: maintains a ring buffer of the last N call timestamps where the call hit the per_call ceiling; if 5 such hits in a 60s window, raise `HighVelocityPatternError` and route to Grant Moment with `why_asking="high_velocity_pattern"`.

   Both thresholds (50%, 5/min) are spec-OPEN-question constants (`specs/budget-tracker.md` § Open questions 1 + 2); Phase 01 implements with the spec defaults and surfaces telemetry counters via `envoy.observability` for empirical calibration in Phase 02.

7. **`envoy.budget.ledger_emitter.LedgerEmitter`** — single-point filter at the threshold-fire and record-finalize sites (per `rules/event-payload-classification.md` Rule 1 single-emitter discipline). Responsibilities:
   - Emit `budget_reservation_record` Ledger entry on every `record_for_call(handle, actual)` success — payload `{intent_id, reserved_microdollars, actual_microdollars, per_window_committed: {window: committed}, recorded_at}`.
   - Emit `budget_threshold_crossed` Ledger entry on every `EnvoyBudgetEvent` from `ThresholdDispatcher` — payload `{principal_id_redacted, window, period_key, threshold_pct, committed_microdollars, reserved_microdollars, allocated_microdollars, observed_at}`.
   - On `principal_id_redacted`: route through `dataflow.classification.event_payload.format_record_id_for_event(policy, "Principal", principal_id)` per `rules/event-payload-classification.md` Rule 1 + Rule 2; the 8-hex SHA-256 prefix shape is identical Python ↔ Rust per `rules/event-payload-classification.md` Rule 2.
   - Emit `budget_extended` Ledger entry on every `Approve` Grant Moment resolution that mutated a window ceiling — payload `{prior_allocated, new_allocated, window, grant_moment_ref}`.
   - Per `rules/event-payload-classification.md` Rule 4: a Tier 2 integration test MUST exercise the end-to-end emit through the real bus and assert the captured payload contains `"sha256:"`-prefixed `principal_id` AND the raw value does NOT appear anywhere in `repr(payload)`.

8. **`envoy.budget.errors`** — the 7 typed errors per `specs/budget-tracker.md` lines 47-57 + `MicrodollarOverflowError` (line 56). All subclass a base `EnvoyBudgetError`. Each maps to a `system_error` Ledger entry per `specs/ledger.md` § System error.

9. **`envoy.budget.runtime_adapter.BudgetRuntimeAdapter`** — implements the public runtime contract per `specs/runtime-abstraction.md` § `budget_reserve/record/snapshot/velocity_check`. Wraps `EnvoyBudgetOrchestrator` with the runtime-abstraction interface so shard 18's runtime stub can receive the public-API methods. Phase 01 wires the kailash-py path; Phase 02 wires kailash-rs at the same interface.

### 3.3 What is explicitly NOT Envoy-new-code

- **Atomic int-microdollar arithmetic** — `kailash.trust.constraints.budget_tracker.BudgetTracker` only. No re-implementation.
- **`set_threshold_callback` rising-edge one-shot logic** — upstream provides; Envoy MUST NOT re-implement the predicate.
- **`BudgetSnapshot` / `BudgetCheckResult` / `BudgetEvent` wire formats** — upstream defines; Envoy `EnvoyBudgetEvent` extends via composition, NOT subclassing.
- **`SQLiteBudgetStore` SQLite schema, WAL mode, 0o600 perms, path validation** — upstream provides.
- **`usd_to_microdollars` / `microdollars_to_usd` conversion** — upstream provides with `math.isfinite()` NaN guards.
- **Threading lock discipline** — upstream `threading.Lock` is correct; Envoy MUST NOT introduce a second lock that orders against the upstream lock (deadlock risk).

---

## 4. Class structure sketch (interfaces only)

Module path (Envoy-side, proposed): `envoy.budget`.

```python
# envoy/budget/types.py
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

WindowName = Literal["per_call", "per_session", "per_hour_velocity", "per_day", "per_month"]

@dataclass(frozen=True)
class WindowCeilings:
    """Five financial-dimension ceilings extracted from EffectiveEnvelope.financial.
    Source: specs/envelope-model.md § Financial dimension."""
    per_call_ceiling_microdollars: int
    per_session_ceiling_microdollars: int
    per_hour_velocity_microdollars: int
    per_day_ceiling_microdollars: int
    per_month_ceiling_microdollars: int

@dataclass(frozen=True)
class ReservationHandle:
    reservation_id: str          # UUIDv7
    intent_id: str               # links to PhaseARecord (specs/ledger.md two-phase signing)
    reserved_microdollars: int
    reserved_per_window: dict[WindowName, int]
    expires_at: datetime
    ceilings_consulted: list[WindowName]
    created_at: datetime

@dataclass(frozen=True)
class EnvoyBudgetEvent:
    """Extends upstream BudgetEvent with principal/window/period_key dimensions."""
    principal_id: str            # raw value held in-memory only; redacted at Ledger emit
    window: WindowName
    period_key: str              # e.g. "2026-05-03T10" (per_hour) | "2026-05-03" (per_day) | "2026-05" (per_month)
    threshold_pct: float
    committed_microdollars: int
    reserved_microdollars: int
    allocated_microdollars: int
    observed_at: datetime

@dataclass(frozen=True)
class MultiWindowSnapshot:
    """All 5 windows snapshotted at one instant."""
    per_call: "kailash.trust.constraints.budget_tracker.BudgetSnapshot"
    per_session: "BudgetSnapshot"
    per_hour_velocity: "BudgetSnapshot"
    per_day: "BudgetSnapshot"
    per_month: "BudgetSnapshot"
    captured_at: datetime

# envoy/budget/orchestrator.py
class EnvoyBudgetOrchestrator:
    """Single facade for the Budget tracker primitive.

    Composes:
      - kailash.trust.constraints.budget_tracker.BudgetTracker (5x — one per window)
      - kailash.trust.constraints.budget_store.SQLiteBudgetStore (1x — shared)
      - envoy.ledger.EnvoyLedger (shard 6) — for Ledger emission on threshold + record
      - envoy.grant_moment.GrantMomentOrchestrator (shard 10) — for threshold→Grant dispatch
      - envoy.budget.threshold_dispatcher.ThresholdDispatcher
      - envoy.budget.reset_scheduler.BudgetResetScheduler
      - envoy.budget.anomaly_detector.AnomalyDetector
      - envoy.budget.ledger_emitter.LedgerEmitter

    Per rules/facade-manager-detection.md Rule 3, all dependencies are explicit
    constructor parameters — no global lookup, no self-construction.
    """

    def __init__(
        self,
        *,
        ceilings: WindowCeilings,
        store: "kailash.trust.constraints.budget_store.SQLiteBudgetStore",
        principal_id: str,                 # rules/tenant-isolation.md Rule 1 — present from day 1
        session_id: str,
        ledger: "envoy.ledger.EnvoyLedger",
        grant_moment: "envoy.grant_moment.GrantMomentOrchestrator",
        clock: "Callable[[], datetime]",   # injectable for deterministic testing
        default_threshold_pcts: tuple[float, ...] = (0.50, 0.80, 0.95, 1.00),
        reservation_ttl_seconds: int = 60, # specs/budget-tracker.md § Open question 4
    ) -> None: ...

    def reserve_for_call(
        self,
        estimated_microdollars: int,
        *,
        intent_id: str,
    ) -> ReservationHandle: ...
        # Reserves against all 5 windows; raises BudgetExhaustedError on any ceiling
        # Returns ReservationHandle with reservation_id (UUIDv7) and ceilings_consulted

    def record_for_call(
        self,
        handle: ReservationHandle,
        actual_microdollars: int,
    ) -> None: ...
        # Finalizes against all 5 windows; raises ReservationExpiredError /
        # ReservationDoubleRecordError per specs/budget-tracker.md lines 55-57.
        # Emits budget_reservation_record Ledger entry.

    def check(self, estimated_microdollars: int) -> "BudgetCheckResult": ...
        # Non-mutating multi-window check; returns the most restrictive window's result

    def lower_velocity_limit(self, window: WindowName, new_microdollars: int) -> None: ...
        # Inline lowering allowed per specs/budget-tracker.md line 39

    def raise_velocity_limit(
        self,
        window: WindowName,
        new_microdollars: int,
        *,
        cooling_off_grant_ref: str | None = None,
    ) -> None: ...
        # Inline RAISE without cooling_off_grant_ref → VelocityRaiseInlineBlockError
        # With valid cooling_off_grant_ref (24h-aged Grant Moment) → permitted

    def snapshot(self) -> MultiWindowSnapshot: ...

    def subscribe_threshold(
        self,
        window: WindowName,
        threshold_pct: float,
        on_cross: "Callable[[EnvoyBudgetEvent], Awaitable[None]]",
    ) -> int: ...
        # Wraps BudgetTracker.set_threshold_callback; returns handle.

# envoy/budget/threshold_dispatcher.py
class ThresholdDispatcher:
    """Async task queue between upstream BudgetTracker callbacks and Grant Moment.

    Per § 2.3 lock discipline: callbacks fire OUTSIDE the upstream _lock, but still
    in a position that should not re-enter reserve/record/check. The dispatcher
    enqueues the EnvoyBudgetEvent onto an asyncio.Queue; a worker task drains the
    queue and constructs/dispatches the EnvelopeViolation → GrantMomentOrchestrator
    path off the upstream callback thread.
    """

    def __init__(
        self,
        *,
        ledger: "envoy.ledger.EnvoyLedger",
        grant_moment: "envoy.grant_moment.GrantMomentOrchestrator",
        primary_channel: "envoy.channels.ChannelAdapterRef",
    ) -> None: ...

    def enqueue(self, event: EnvoyBudgetEvent) -> None: ...
        # Called from upstream BudgetTracker callback; non-blocking.

    async def run(self) -> None: ...
        # Worker loop: drain queue, construct EnvelopeViolation, request Grant Moment.

# envoy/budget/reset_scheduler.py
class BudgetResetScheduler:
    """Pure function over (window, at_time) → period_key.

    Lazy/event-driven: NO wall-clock timer. The orchestrator calls
    current_period_key(window, at_time=now) at every reserve_for_call(...) entry
    and either reuses the existing per-window tracker or mints a fresh one
    when the period has rolled over.
    """

    @staticmethod
    def current_period_key(window: WindowName, *, at_time: datetime, tz: "tzinfo") -> str: ...
        # per_hour_velocity → "YYYY-MM-DDTHH" UTC
        # per_day → "YYYY-MM-DD" in tz (HIGH ambiguity — see § 7)
        # per_month → "YYYY-MM" in tz (HIGH ambiguity — see § 7)
        # per_session → session_id (no time-based reset)
        # per_call → call's intent_id

# envoy/budget/anomaly_detector.py
class AnomalyDetector:
    """T-093 fraud defense: single-call > 50% session + 5-calls-at-ceiling-in-1min."""

    def __init__(
        self,
        *,
        single_call_session_pct_threshold: float = 0.50,
        velocity_window_seconds: int = 60,
        velocity_count_threshold: int = 5,
    ) -> None: ...

    def check_single_call(
        self,
        estimated_microdollars: int,
        per_session_remaining_microdollars: int,
    ) -> "AnomalyDetectedError | None": ...

    def record_ceiling_hit(self, at_time: datetime) -> "HighVelocityPatternError | None": ...

# envoy/budget/ledger_emitter.py
class LedgerEmitter:
    """Single-point Ledger emission with classified-PK redaction.

    Per rules/event-payload-classification.md Rule 1, Rule 2, Rule 4.
    """

    def __init__(
        self,
        *,
        ledger: "envoy.ledger.EnvoyLedger",
        classification_policy: "Optional[ClassificationPolicy]",
    ) -> None: ...

    def emit_threshold_crossed(self, event: EnvoyBudgetEvent) -> None: ...
    def emit_reservation_record(self, handle: ReservationHandle, actual: int) -> None: ...
    def emit_budget_extended(
        self,
        window: WindowName,
        prior_allocated: int,
        new_allocated: int,
        grant_moment_ref: str,
    ) -> None: ...
```

Per `rules/orphan-detection.md` Rule 1, `EnvoyBudgetOrchestrator` MUST be invoked from a production hot path within 5 commits of landing. The hot path is `kailash.kaizen.BaseAgent.tool_dispatch_interceptor → reserve_for_call(...) → tool execute → record_for_call(...)` — the same Kaizen tool-dispatch interceptor that hosts `OutOfEnvelopeDetector` (shard 10 § 3.2 item 4). Order of operations per call: (a) `reserve_for_call(...)` — fail-fast on `BudgetExhaustedError`; (b) `OutOfEnvelopeDetector.evaluate(...)` — fail on envelope violation; (c) Tool execution; (d) `record_for_call(handle, actual_cost_from_kaizen_usage_metrics)` — finalize.

---

## 5. Integration points

The Budget tracker composes 5 neighbouring primitives. Each is a clean unidirectional or bidirectional hop.

| Neighbouring primitive (shard)  | Hook                                                                                                                                                                                                                  | Direction               | Spec citation                                                                |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ---------------------------------------------------------------------------- |
| Envelope compiler (shard 4)     | At session start, the compiler emits `EffectiveEnvelope.financial.{per_call,per_session,per_hour,per_day,per_month}_ceiling_microdollars`; orchestrator constructs `MultiWindowBudget` from these.                    | inbound                 | `specs/envelope-model.md` § Schema § Financial dimension                     |
| Boundary Conversation (shard 8) | Boundary Conversation outputs the initial 5 ceilings via `EnvelopeConfig` → compiler → orchestrator. Subsequent Grant Moments may extend ceilings; the orchestrator re-pins on `budget_extended` Ledger entry.        | inbound (initial setup) | `specs/boundary-conversation.md` § Output                                    |
| Grant Moment (shard 10)         | Threshold-callback dispatch: `ThresholdDispatcher.enqueue(EnvoyBudgetEvent)` → async task → `GrantMomentOrchestrator.request_grant_moment(EnvelopeViolation, primary_channel)` per shard 10 § 3.2 item 1.             | bidirectional           | `specs/budget-tracker.md` line 35; `specs/grant-moment.md` § Schema          |
| Envoy Ledger (shard 6)          | `LedgerEmitter` writes `budget_threshold_crossed`, `budget_reservation_record`, `budget_extended` entries via `EnvoyLedger.append(...)`. Per `rules/event-payload-classification.md` Rule 1: single-emitter-point.    | outbound                | `specs/ledger.md` § Entry envelope schema; `specs/budget-tracker.md` line 66 |
| Model adapter (shard 13)        | Per-call cost arrives as Kaizen `usage_metrics.cost_microdollars` from the LLM provider response; orchestrator's `record_for_call(handle, actual_microdollars=usage_metrics.cost_microdollars)` is the consumer hop.  | inbound                 | shard 13 § 5 (Model adapter emits cost) + `specs/budget-tracker.md` line 31  |
| Channel adapters (shard 16)     | `ThresholdDispatcher.primary_channel` is the channel where the budget-warning Grant Moment surfaces. The 80%/95% threshold-cross events MAY produce a non-Grant-Moment "soft warning" UX in the Daily Digest channel. | outbound                | `specs/grant-moment.md` § Rendering line 92 (primary-channel binding)        |

### 5.1 Specific hooks for Phase 01 exit criteria

- **EC-2 (3 Grant Moments triggered and resolved)**: A budget-threshold Grant Moment is one of the three resolution shapes per `02-mvp-objectives.md` line 38. Tier 2 test: reserve/record sequence pushes a 0.80 threshold cross → Grant Moment fires → resolved with `Approve` extending budget → `budget_extended` Ledger entry verifiable by independent verifier.
- **EC-4 (Envoy Ledger exports a verifiable hash-chained log)**: every `budget_*` Ledger entry is hash-chained per `specs/ledger.md` § Entry envelope schema; a tampering attempt on a `budget_threshold_crossed` entry's `committed_microdollars` payload field MUST be detected by the EC-9 independent verifier.
- **EC-8 (User operates for a week across channels)**: `02-mvp-objectives.md` line 117 acceptance gate "no double-billing in Budget tracker against multi-channel actions" — tested by Tier 2: same `intent_id` reserved on Telegram, action-confirmed on Slack, recorded on the original tracker; the `_recorded_reservations: set[str]` set guarantees `ReservationDoubleRecordError` if double-record is attempted from a sibling channel adapter.

### 5.2 Shard 11 (Daily Digest) consumer hop

The Daily Digest (shard 11) reads `budget_threshold_crossed` and `budget_reservation_record` Ledger entries to render daily spend summaries. The Budget tracker emits these entries via `LedgerEmitter` (§ 3.2 item 7); shard 11 consumes via `EnvoyLedger.query(filter={types: ["budget_threshold_crossed", "budget_reservation_record", "budget_extended"], since: yesterday_local_morning})`. No tight coupling — the integration is via the Ledger query interface.

### 5.3 Shard 9 (Authorship Score) hop

Authorship Score (shard 9) is a stateless pure function over the Ledger slice (per shard 9 finding). It reads `budget_extended` Ledger entries to assess whether the user is authoring (extending budget rules with intent) or rubber-stamping (auto-approving repeated extensions). No code-level integration; data-flow only via Ledger.

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/orphan-detection.md` MUST Rule 1 + `rules/facade-manager-detection.md` MUST Rule 1, the Tier 2 wiring tests are mandatory. Per `rules/testing.md` § 3-Tier Testing, Tier 2 uses real infrastructure (real `SQLiteBudgetStore`, real `BudgetTracker`, real `EnvoyLedger`).

### 6.1 Tier 2 wiring tests (required by `rules/orphan-detection.md` MUST Rule 1)

File naming per `rules/facade-manager-detection.md` MUST Rule 2: `test_envoy_budget_orchestrator_wiring.py`, `test_threshold_dispatcher_wiring.py`, `test_ledger_emitter_wiring.py`. Each imports the framework facade (`envoy.budget`), not the manager class directly.

1. **`test_envoy_budget_orchestrator_wiring.py`** — exercises the orchestrator's `reserve_for_call → record_for_call` round-trip end-to-end against real `SQLiteBudgetStore` + real `EnvoyLedger`; asserts the `budget_reservation_record` Ledger entry exists and is hash-chain-verifiable.

2. **`test_threshold_dispatcher_wiring.py`** — exercises a 0.80 threshold cross under real `BudgetTracker.set_threshold_callback`; asserts:
   - `budget_threshold_crossed` Ledger entry written (external observable per `rules/orphan-detection.md` MUST Rule 1).
   - `GrantMomentOrchestrator.request_grant_moment(...)` was invoked with `EnvelopeViolation.violated_dimension == "financial"` (verified via test-double channel adapter that records the request).
   - The async task fires OUTSIDE the upstream `BudgetTracker._lock` (verified by attempting a re-entrant `tracker.reserve(...)` from inside the test-double's `render_grant_moment` — must not deadlock).

3. **`test_threshold_one_shot_semantics.py`** — exercises rising-edge semantics across `reserve` + `record` + oscillation:

   ```python
   orchestrator.subscribe_threshold("per_session", 0.80, on_cross)
   orchestrator.reserve_for_call(8_500_000, intent_id="i1")  # crosses 0.80 — fires
   orchestrator.record_for_call(handle1, 1_000_000)          # back to 10% — does NOT re-arm
   orchestrator.reserve_for_call(9_500_000, intent_id="i2")  # back to 95% — STILL no re-fire
   assert fire_count == 1                                     # specs/budget-tracker.md line 35 contract
   ```

4. **`test_per_principal_partitioning.py`** — exercises `rules/tenant-isolation.md` Rule 1: two trackers with `principal_id="alice"` and `principal_id="bob"` MUST have distinct cache keys; reserving against alice MUST NOT consume bob's allocation. (Phase 01 ships single-principal but the test asserts the structural defense from day 1.)

5. **`test_reset_boundary_determinism.py`** — replays a 2-day session with deterministic clock; asserts the per_day / per_hour_velocity boundary computations are identical across replays. Specifically, `current_period_key("per_day", at_time=2026-05-03T23:59:59Z)` returns `"2026-05-03"` and `at_time=2026-05-04T00:00:00Z` returns `"2026-05-04"` — boundary determinism.

6. **`test_ledger_emitter_classified_redaction.py`** — per `rules/event-payload-classification.md` Rule 4: emit a threshold-crossing event with classified principal_id; subscribe a real DomainEvent handler; assert captured payload has `"sha256:"`-prefixed `principal_id` AND raw value does NOT appear in `repr(payload)`.

7. **`test_ec2_grant_moment_extends_budget.py`** — full EC-2 path: reserve consumes 80% → Grant Moment fires → user approves with budget extension → `budget_extended` Ledger entry written → reconstructed orchestrator with new ceiling → next `reserve_for_call(...)` succeeds. Asserts Ledger entries are hash-chain-verifiable by EC-9 verifier (shard 7).

### 6.2 Tier 1 unit tests (per `specs/budget-tracker.md` § Test location)

The spec pre-declares 7 test files; the Phase 01 implementation MUST land all 7 with the exact names:

- `tests/unit/test_microdollar_arithmetic.py` — integer-only, no float drift, overflow detection.
- `tests/unit/test_sliding_window_velocity.py` — O(log n) sliding-window sum correctness.
- `tests/integration/test_reserve_record_concurrency.py` — concurrent reservations sum against ceilings (Tier 2; the tracker is `threading.Lock`-guarded, but the orchestrator wraps it; concurrency invariants MUST hold).
- `tests/integration/test_threshold_callback_invocation.py` — `set_threshold_callback` fires at correct % thresholds.
- `tests/regression/test_t019_velocity_raise_inline_block.py` — T-019 defense; inline raise refused.
- `tests/regression/test_t093_budget_exhaustion_fraud.py` — T-093 anomaly + high-velocity-pattern detection.
- `tests/integration/test_velocity_raise_24h_cooling_off.py` — Sunday→Monday effect window.

### 6.3 Tier 3 E2E test surface

Per `rules/testing.md` § Tier 3 E2E:

- **`tests/e2e/test_budget_threshold_grant_moment_full_flow.py`** — real Boundary Conversation seeds 5 ceilings → real Kaizen agent loop runs → real LLM provider returns `usage_metrics` → real Budget tracker records → real threshold cross at 0.80 → real Grant Moment renders on real CLI channel adapter → user approves via real CLI input → real budget extension → real Ledger persistence → real EC-9 independent verifier (shard 7) verifies the entire chain.

### 6.4 NaN/Inf invariant test

Per `rules/zero-tolerance.md` Rule 4 + cross-SDK security invariants: `EnvoyBudgetEvent.threshold_pct` MUST be `math.isfinite()`-validated. Test: pass `float('nan')` and `float('inf')` to `subscribe_threshold` — MUST raise `BudgetTrackerError`. Upstream `BudgetTracker.set_threshold_callback` already enforces this at `budget_tracker.py:813-817`; Envoy `subscribe_threshold` MUST NOT bypass.

---

## 7. Frozen-spec ambiguity

Per `01-shard-plan.md` § 4 failure-mode protocol: HIGH ambiguities trigger a STOP + MUST-Rule-5b sweep. Below are the ambiguities surfaced during this shard's deep-dive reasoning.

### 7.1 HIGH — Reset boundary timezone semantics

**Spec gap:** `specs/budget-tracker.md` § Ceilings (lines 17-23) names `per_day_ceiling_microdollars` and `per_month_ceiling_microdollars` but does NOT specify the timezone basis for the day / month boundary. Open question 5 ("Cross-session vs intra-session aggregate ceiling rounding — month-boundary handling on month-end actions") gestures at the issue but does NOT resolve it.

**Why HIGH:** A user in `Pacific/Auckland` whose `per_day_ceiling = $50` would experience the per-day budget reset at UTC midnight if implemented naively, which is **noon local time** in Auckland — the user has effectively two budget-reset events per local day instead of one. Conversely, basing on local-time produces ambiguity around DST transitions (the 25-hour day in US/Pacific spring-forward).

**Phase 01 disposition options:**

- **Option A (UTC-only)**: simplest; reset at UTC midnight regardless of user timezone. Acceptable for MVP but produces a subtly-wrong UX for non-UTC users (user observed reset at noon local time).
- **Option B (User local time, IANA tz)**: reset at midnight in the user's IANA timezone (set during Boundary Conversation). DST-correct. More complex; requires storing `user_timezone` in `MultiWindowBudget`.
- **Option C (Defer to per-envelope config)**: `EffectiveEnvelope.financial.per_day_ceiling_timezone: "UTC" | iana_string` — user authors the timezone explicitly during Boundary Conversation.

**Recommendation:** Option B with `user_timezone` collected at Boundary Conversation entry; stored in `EffectiveEnvelope.financial`; Budget tracker reads it at session start. This requires an additive spec edit — `specs/envelope-model.md § Financial dimension` adds `per_day_ceiling_timezone: str` field; `specs/budget-tracker.md § Ceilings` adds explicit "reset at local midnight in `EffectiveEnvelope.financial.per_day_ceiling_timezone`" sentence.

**Escalation per `01-shard-plan.md` §4:** This shard records the ambiguity; the shard does NOT edit the spec inline (per `rules/specs-authority.md` MUST Rule 4 + Rule 5b, spec edits trigger full sibling re-derivation). Escalated to shard 22 (spec gap analysis) for additive-spec disposition. Per the shard plan §2 "MUST Rule 5b discipline: new spec files do NOT trigger sibling re-derivation. Edits to existing specs DO. Phase 01 should land additive specs only" — the timezone field would be an EDIT to `specs/envelope-model.md`, not an additive spec; this triggers full-sibling re-derivation. Disposition: shard 22 either drafts the edit (and accepts the re-derivation cost) OR proposes a Phase 01-only Option A (UTC-only) defer with a Phase 02 ticket for Option B.

### 7.2 MEDIUM — Reservation TTL default value

**Spec gap:** `specs/budget-tracker.md` § Open question 4 — "Reservation TTL — how long can a reservation hold capacity before timeout (default 60s? 5min?)."

**Why MEDIUM (not HIGH):** The spec acknowledges the question explicitly and lists two candidate defaults; neither candidate is wrong. Phase 01 implementation MUST pick one and document the choice. A 60s default is consistent with typical LLM tool-call latency budgets; 5min is more permissive but creates capacity-leak risk if a tool call hangs.

**Phase 01 disposition:** 60s default; configurable via `EnvoyBudgetOrchestrator(..., reservation_ttl_seconds=60)`. Tier 2 test `test_reservation_expires_at_ttl.py` asserts the TTL fires `ReservationExpiredError` on `record_for_call(handle, ...)` after `expires_at`.

**No spec edit needed** — Phase 01 picks a default within the spec's pre-declared options; not a contract change.

### 7.3 LOW — Anomaly detection 50% threshold + 5-calls-in-1min

**Spec gap:** `specs/budget-tracker.md` § Open questions 1 + 2 — "Anomaly threshold (50% session budget) — empirical calibration; some workflows have legitimate burst patterns." + "High-velocity 5-calls-in-1-min threshold — Phase 01 telemetry will inform tuning."

**Why LOW:** Spec acknowledges the constants are calibration-defaults; Phase 01 implements with the defaults and emits telemetry (`envoy.observability` counters) for Phase 02 tuning. No structural ambiguity.

**Phase 01 disposition:** Implement with spec defaults; emit per-call telemetry; surface in Daily Digest "anomalies blocked this week: N" line.

### 7.4 LOW — Microdollar precision for non-USD currencies

**Spec gap:** `specs/budget-tracker.md` § Open question 3 — "Microdollar precision sufficiency for non-USD currencies (yen, satoshi-equivalents) — Phase 02 i18n concern."

**Why LOW:** Spec explicitly flags as Phase 02 i18n concern; Phase 01 ships USD-only.

**Phase 01 disposition:** USD-only; the `usd_to_microdollars` upstream helper is the only conversion path; YEN/satoshi support deferred to Phase 02.

---

## 8. Cross-references

- Frozen specs: `specs/budget-tracker.md`; cross-spec `specs/envelope-model.md` § Financial dimension; `specs/ledger.md` § Entry envelope schema + per-type schemas; `specs/grant-moment.md` § Schema + § Velocity-raise ratchet; `specs/runtime-abstraction.md` § `budget_reserve/record/snapshot/velocity_check`; `specs/threat-model.md` T-019 + T-093.
- Wave-A neighbours: `01-analysis/04-envelope-compiler-implementation.md` (financial-dimension extraction); `01-analysis/05-trust-store-implementation.md` (`principal_id` keying pattern); `01-analysis/06-envoy-ledger-implementation.md` (Ledger emit contract).
- Wave-C neighbour: `01-analysis/10-grant-moment-implementation.md` § 3.2 item 1 (`request_grant_moment(...)` contract); § 3.2 item 5 (channel-handoff dispatch).
- Wave-D peer (this shard): `01-analysis/11-daily-digest-implementation.md` (downstream consumer of `budget_*` Ledger entries; Wave-D parallel).
- Wave-D peer: `01-analysis/13-model-adapter-implementation.md` § 5 (Kaizen `usage_metrics.cost_microdollars` provider).
- Wave-D peer: `01-analysis/16-channel-adapters-implementation.md` (primary-channel binding; soft-warning UX surface).
- Phase 00 inheritance: `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` item 16 (BudgetTracker A grade) + reconciliation row 16; verified at `~/repos/loom/kailash-py/src/kailash/trust/constraints/budget_tracker.py:289-1083` + `budget_store.py:1-80+`.
- Phase 01 readiness: `01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 9 + § 5 verification protocol.
- Phase 01 objectives: `01-analysis/02-mvp-objectives.md` § 3 cross-cutting deliverables row "Budget tracker"; EC-2 (Grant Moment); EC-4 (Ledger verifier); EC-8 (week-long cross-channel coherence; no double-billing).
- Phase 01 sharding: `01-analysis/01-shard-plan.md` § 5 Group D (Daily Digest, Budget tracker, Channel adapters).
- Phase 01 methodology: `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` (cite-not-paraphrase; freshness-gate discipline).
- Closed kailash-py issue: `terrene-foundation/kailash-py#603` ISS-29 closed 2026-04-25T09:16:38Z; PR commit `1b164d93 feat(trust): add BudgetTracker threshold-breach callback API (#603)`; predecessor WIP commits `433bf3dc` + `17d4305a` + `eab3d2e0`.
- Rules cited: `rules/orphan-detection.md` MUST Rule 1 + Rule 2 (Tier 2 wiring); `rules/facade-manager-detection.md` MUST Rule 1 + Rule 2 + Rule 3 (manager-shape facade contract); `rules/tenant-isolation.md` Rule 1 (cache-key tenant dimension); `rules/event-payload-classification.md` Rule 1 + Rule 2 + Rule 4 (single-emitter classified redaction); `rules/zero-tolerance.md` Rule 4 (no upstream workarounds — Envoy uses upstream `set_threshold_callback` directly, no re-implementation); `rules/specs-authority.md` MUST Rule 4 + Rule 5b (no spec edits at this shard); `rules/autonomous-execution.md` (capacity budget); `rules/testing.md` § Tier 2 + § Tier 3.
