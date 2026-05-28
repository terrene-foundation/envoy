# budget-tracker

## Purpose

Financial-dimension ceilings + velocity + session scope + threshold callbacks.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 §3.1 + 05-runtime-abstraction.md v2 §2.1`.
- **Threats mitigated:** T-093 budget-exhaustion fraud, T-019 velocity-ratchet rubber-stamp.
- **BETs tested:** BET-2 performance through structural governance.

## Data unit

Integer microdollars (1 dollar = 1,000,000 microdollars). No float accumulation.

## Ceilings (doc 02 §3.1 + C-02 v3 fix)

- `per_call_ceiling_microdollars`
- `per_session_ceiling_microdollars` (added per reviewer F-13)
- `per_hour_velocity_microdollars`
- `per_day_ceiling_microdollars`
- `per_month_ceiling_microdollars`

## Check shape

100% structural. O(1) to O(log n) sliding-window sum. <5ms target.

## Reserve/record pattern

`budget_reserve(amount)` before call; `budget_record(reservation, actual)` after. Concurrent reservations sum against ceilings.

## Threshold callbacks

`BudgetTracker.set_threshold_callback(threshold_pct, callback)` — invoke when (committed + reserved) / allocated ≥ threshold. Used for Grant Moment surfacing. kailash-rs#518 + kailash-py#603.

## Velocity-raise ratchet (T-093 R2-H4)

RAISING any velocity limit CANNOT be inline. Requires Weekly Posture Review OR cross-channel Grant Moment with 24h cooling-off. Lowering allowed inline.

## Budget-exhaustion fraud defense (T-093)

- Per-call ceiling + velocity-limit + session-scope.
- Anomaly detection: single call > 50% of session budget → pause for confirmation.
- High-velocity pattern detection (5 calls at ceiling in 1min → Grant Moment).

## Error taxonomy

| Error                           | Trigger                                                                              | User action                                                                                              | Retry                |
| ------------------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- | -------------------- |
| `BudgetExhaustedError`          | Reserve+committed sum exceeds any ceiling (per_call/session/hour-velocity/day/month) | Surface ceiling type to user; user raises ceiling via Weekly Posture Review (velocity-raise)             | Manual after raise   |
| `VelocityRaiseInlineBlockError` | Inline attempt to RAISE any velocity limit                                           | Raise refused inline; user goes to Weekly Posture Review OR cross-channel Grant Moment + 24h cooling-off | Never inline         |
| `AnomalyDetectedError`          | Single call > 50% of session budget                                                  | Pause for confirmation; user explicitly approves via Grant Moment                                        | Manual after confirm |
| `HighVelocityPatternError`      | 5 calls at ceiling within 1 minute                                                   | Surface Grant Moment with anomaly summary; user approves or rejects pattern                              | Manual after Grant   |
| `ReservationExpiredError`       | `budget_record(reservation, actual)` called after reservation TTL                    | Refuse record; cleanup orphan reservations; alert on lost capacity                                       | Auto cleanup         |
| `MicrodollarOverflowError`      | Reservation amount overflows int64 microdollar range                                 | Refuse reservation; this is a programming error or hostile input                                         | Never                |
| `ReservationDoubleRecordError`  | Same `reservation_id` recorded twice                                                 | Refuse duplicate; surface to runtime as a programming error                                              | Never                |

## Cross-references

- specs/envelope-model.md — Financial dimension schema.
- specs/runtime-abstraction.md — `budget_reserve/record/snapshot/velocity_check`.
- specs/grant-moment.md — velocity-raise ratchet Grant Moment flow.
- specs/weekly-posture-review.md — velocity-raise approval ritual.
- specs/threat-model.md — T-019, T-093.
- specs/ledger.md — budget reservation + record entries.

## Ledger entries emitted

The Budget tracker emits three Ledger entry types via `envoy.budget.ledger_emitter.LedgerEmitter`, appended through `envoy.ledger.EnvoyLedger.append`. Numeric fields are integer microdollars; the threshold fraction is encoded as integer basis points (`threshold_bps`, 0.80 → 8000) because the Phase-01 Ledger is int-only (`envoy.ledger.canonical.canonical_dumps` rejects floats). `principal_id` is redacted through `dataflow.classification.event_payload.format_record_id_for_event` before the content is built.

- `budget_reservation_record` — emitted on every `EnvoyBudgetOrchestrator.record_for_call`. Content: `intent_id`, `reservation_id`, `reserved_microdollars`, `actual_microdollars`, `per_window_reserved`.
- `budget_threshold_crossed` — emitted on every threshold-cross `EnvoyBudgetEvent` drained by `envoy.budget.threshold_dispatcher.ThresholdDispatcher`. Content: redacted `principal_id`, `window`, `period_key`, `threshold_bps`, `committed_microdollars`, `reserved_microdollars`, `allocated_microdollars`, `observed_at`.
- `budget_extended` — emitted on every `EnvoyBudgetOrchestrator.raise_velocity_limit` approved with a cooling-off Grant-Moment ref. Content: `window`, `prior_allocated_microdollars`, `new_allocated_microdollars`, `grant_moment_ref`.

## Test location

- `tests/tier1/test_microdollar_arithmetic.py` — integer-only, no float drift, overflow detection.
- `tests/tier1/test_sliding_window_velocity.py` — multi-window accumulation + per-hour velocity ceiling.
- `tests/tier2/test_reserve_record_concurrency.py` — concurrent reservations sum against ceilings + double-record guard (EC-8).
- `tests/tier2/test_threshold_callback_invocation.py` — `set_threshold_callback` fires at correct % thresholds + rising-edge one-shot.
- `tests/regression/test_t019_velocity_raise_inline_block.py` — T-019 defense; inline raise refused.
- `tests/regression/test_t093_budget_exhaustion_fraud.py` — T-093 anomaly + high-velocity-pattern detection.
- `tests/tier2/test_velocity_raise_24h_cooling_off.py` — cooling-off Grant-Moment ref unlocks the raise + `budget_extended` emit.
- `tests/tier2/test_envoy_budget_orchestrator_wiring.py` — orchestrator reserve→record round-trip against real Ledger (hash-chain-verifiable).
- `tests/tier2/test_threshold_dispatcher_wiring.py` — threshold cross → `budget_threshold_crossed` Ledger entry + Grant-Moment seam.
- `tests/tier2/test_per_principal_partitioning.py` — tenant-isolation cache-key shape; no cross-principal consumption.
- `tests/tier2/test_reset_boundary_determinism.py` — period-key boundary determinism + replay equivalence.
- `tests/tier2/test_ledger_emitter_classified_redaction.py` — single-point principal-id redaction.

> Test-location paths reconciled to the project's tier-based layout (`tests/tier1/`, `tests/tier2/`, `tests/regression/`) per `rules/spec-accuracy.md` Rule 1; the prior `tests/unit/` / `tests/integration/` citations named a layout the project does not use.

## Open questions

1. Anomaly threshold (50% session budget) — empirical calibration; some workflows have legitimate burst patterns.
2. High-velocity 5-calls-in-1-min threshold — Phase 01 telemetry will inform tuning.
3. Microdollar precision sufficiency for non-USD currencies (yen, satoshi-equivalents) — Phase 02 i18n concern.
4. Reservation TTL — how long can a reservation hold capacity before timeout (default 60s? 5min?).
5. Cross-session vs intra-session aggregate ceiling rounding — month-boundary handling on month-end actions.
