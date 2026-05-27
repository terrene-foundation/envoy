# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.budget.orchestrator — the multi-window Budget tracker facade.

Per `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md`
§ 3.1 + § 3.2 item 1-2 + § 4. `EnvoyBudgetOrchestrator` is the single facade
on the `envoy.budget` namespace (`rules/facade-manager-detection.md` Rule 1);
every other class in the package is reached through it.

It composes the upstream `kailash.trust.constraints.budget_tracker.BudgetTracker`
(verified present in `kailash` at session start) — five instances, one per
ceiling window — and adds the Envoy-new-code surface: multi-window
reserve/record, reset-boundary tracker minting, anomaly detection, velocity
ratchet, and the sync→async Ledger/Grant-Moment emission seams.

## Sync accounting, async emission

`reserve_for_call` / `record_for_call` are SYNC — matching the upstream
`BudgetTracker` (sync), the runtime-abstraction `budget_reserve/record`
contract (sync, `specs/runtime-abstraction.md`), and the consistent-async
pair rule (`rules/patterns.md` § Paired Public Surface). The double-billing
guard (the EC-8 load-bearing invariant, `02-mvp-objectives.md` line 117)
lives in the sync record path.

Ledger emission (`budget_reservation_record`, `budget_threshold_crossed`) is
async (`EnvoyLedger.append` is async) and flows through worker queues fed by
non-blocking sync `enqueue_*` calls on the injected `LedgerEmitter` /
`ThresholdDispatcher`. The upstream threshold callback fires synchronously
OUTSIDE the upstream `_lock` (design § 2.3); the sync enqueue is the only
work done on that callback thread, so re-entrancy / deadlock is structurally
impossible (design § 3.2 item 4).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Protocol

from kailash.trust.constraints.budget_tracker import BudgetTracker

from envoy.budget.anomaly_detector import AnomalyDetector
from envoy.budget.errors import (
    BudgetExhaustedError,
    MicrodollarOverflowError,
    ReservationDoubleRecordError,
    ReservationExpiredError,
    VelocityRaiseInlineBlockError,
)
from envoy.budget.reset_scheduler import BudgetResetScheduler
from envoy.budget.types import (
    INT64_MAX,
    WINDOW_NAMES,
    EnvoyBudgetEvent,
    MultiWindowSnapshot,
    ReservationHandle,
    WindowCeilings,
    WindowName,
    new_reservation_id,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

    from kailash.trust.constraints.budget_store import BudgetStore
    from kailash.trust.constraints.budget_tracker import BudgetCheckResult, BudgetEvent

__all__ = ["EnvoyBudgetOrchestrator", "MultiWindowBudget"]


class _ReservationRecordSink(Protocol):
    """Sink the orchestrator needs from a LedgerEmitter (sync enqueue)."""

    def enqueue_reservation_record(
        self, handle: ReservationHandle, actual_microdollars: int
    ) -> None: ...

    def enqueue_budget_extended(
        self,
        *,
        window: WindowName,
        prior_allocated_microdollars: int,
        new_allocated_microdollars: int,
        grant_moment_ref: str,
    ) -> None: ...


class _ThresholdSink(Protocol):
    """Minimal sink for threshold-cross events (sync enqueue, non-blocking)."""

    def enqueue(self, event: EnvoyBudgetEvent) -> None: ...


def _utcnow() -> datetime:
    """Default clock — UTC. Injectable for deterministic replay tests."""
    return datetime.now(timezone.utc)


class MultiWindowBudget:
    """Holds the five per-window `BudgetTracker` instances for one principal.

    Per design § 3.2 item 2. Trackers are minted lazily per `(window,
    period_key)`; the `tracker_id` carries `principal_id` from day 1 even
    though Phase 01 ships single-principal — the structural defense required
    by `rules/tenant-isolation.md` Rule 1 (cache-key tenant dimension). The
    `principal_id` STAYS in the key even though `period_key` is already
    unique, as defense-in-depth against a future refactor.
    """

    def __init__(
        self,
        *,
        ceilings: WindowCeilings,
        store: BudgetStore | None,
        principal_id: str,
        session_id: str,
    ) -> None:
        self._ceilings = ceilings
        self._store = store
        self._principal_id = principal_id
        self._session_id = session_id
        # (window, period_key) -> live BudgetTracker
        self._trackers: dict[tuple[WindowName, str], BudgetTracker] = {}
        # Inline ceiling overrides (velocity lower/raise). The effective ceiling
        # a tracker is minted with is the override if present, else the envelope
        # value — so a lowered/raised limit actually changes enforcement, not
        # just the reported number.
        self._overrides: dict[WindowName, int] = {}

    def tracker_id(self, window: WindowName, period_key: str) -> str:
        """The persistence key — `principal_id` present per tenant-isolation Rule 1."""
        return f"envoy:v1:{self._principal_id}:{window}:{period_key}"

    def effective_ceiling(self, window: WindowName) -> int:
        """The ceiling in force — the inline override if set, else the envelope value."""
        return self._overrides.get(window, self._ceilings.ceiling_for(window))

    def tracker(self, window: WindowName, period_key: str) -> BudgetTracker:
        """Return the live tracker for `(window, period_key)`, minting on rollover.

        Minted with `effective_ceiling(window)` so an inline override applies to
        freshly-minted period trackers too. `per_call` trackers are transient
        (no store); the other four persist to the shared `SQLiteBudgetStore`
        keyed by `tracker_id` for crash recovery within the period (design
        § 3.2 item 5).
        """
        key = (window, period_key)
        existing = self._trackers.get(key)
        if existing is not None:
            return existing
        tracker = BudgetTracker(
            self.effective_ceiling(window),
            store=None if window == "per_call" else self._store,
            tracker_id=self.tracker_id(window, period_key),
        )
        self._trackers[key] = tracker
        return tracker

    def apply_override(self, window: WindowName, new_ceiling: int, *, period_key: str) -> None:
        """Set an inline ceiling override and re-mint the current-period tracker.

        The upstream `BudgetTracker.allocated` is fixed at construction, so a
        ceiling change requires re-minting with the committed state preserved
        (`record(0, committed)` restores committed without a reserve). In-flight
        reservations on the old tracker are not carried — Phase-01 ceiling
        changes occur at session/Grant-Moment boundaries, not mid-reservation.
        """
        self._overrides[window] = new_ceiling
        old = self._trackers.get((window, period_key))
        committed = old.snapshot().committed if old is not None else 0
        fresh = BudgetTracker(
            new_ceiling,
            store=None if window == "per_call" else self._store,
            tracker_id=self.tracker_id(window, period_key),
        )
        if committed > 0:
            fresh.record(0, committed)
        self._trackers[(window, period_key)] = fresh

    def evict_per_call(self, period_key: str) -> None:
        """Discard the transient per_call tracker once its call has recorded."""
        self._trackers.pop(("per_call", period_key), None)


class EnvoyBudgetOrchestrator:
    """Single facade for the multi-window Budget tracker primitive.

    All dependencies are explicit constructor parameters per
    `rules/facade-manager-detection.md` Rule 3 — no global lookup, no
    self-construction.
    """

    def __init__(
        self,
        *,
        ceilings: WindowCeilings,
        store: BudgetStore | None,
        principal_id: str,
        session_id: str,
        clock: Callable[[], datetime] = _utcnow,
        reservation_ttl_seconds: int = 60,
        anomaly_detector: AnomalyDetector | None = None,
        ledger_emitter: _ReservationRecordSink | None = None,
        threshold_sink: _ThresholdSink | None = None,
        default_threshold_pcts: tuple[float, ...] = (0.50, 0.80, 0.95, 1.00),
    ) -> None:
        self._ceilings = ceilings
        self._principal_id = principal_id
        self._session_id = session_id
        self._clock = clock
        self._ttl = timedelta(seconds=reservation_ttl_seconds)
        self._anomaly = anomaly_detector if anomaly_detector is not None else AnomalyDetector()
        self._ledger_emitter = ledger_emitter
        self._threshold_sink = threshold_sink
        self._default_threshold_pcts = default_threshold_pcts
        self._scheduler = BudgetResetScheduler()
        self._windows = MultiWindowBudget(
            ceilings=ceilings,
            store=store,
            principal_id=principal_id,
            session_id=session_id,
        )
        # reservation_id -> ISO timestamp of first record (double-billing guard).
        self._recorded_reservations: dict[str, str] = {}
        # reservation_id -> handle, for in-flight reservations.
        self._active_reservations: dict[str, ReservationHandle] = {}
        # Threshold callback handles already armed per (window, period_key, pct).
        self._armed_thresholds: set[tuple[WindowName, str, float]] = set()

    # ------------------------------------------------------------------
    # Reserve / record — sync accounting (the EC-8 load-bearing surface)
    # ------------------------------------------------------------------

    def reserve_for_call(
        self,
        estimated_microdollars: int,
        *,
        intent_id: str,
    ) -> ReservationHandle:
        """Reserve `estimated_microdollars` against all five windows.

        Order of checks (fail-fast): microdollar bound → single-call anomaly →
        per-window reserve (rollback + `BudgetExhaustedError` on the first
        window that refuses) → high-velocity-pattern. Returns a
        `ReservationHandle`; the windows that succeeded hold the reservation
        until `record_for_call` finalizes it.
        """
        self._validate_microdollars(estimated_microdollars, "estimated_microdollars")
        now = self._clock()

        # Anomaly: single call > 50% of remaining session budget (T-093).
        session_key = self._scheduler.current_period_key(
            "per_session", at_time=now, session_id=self._session_id, intent_id=intent_id
        )
        session_tracker = self._windows.tracker("per_session", session_key)
        anomaly = self._anomaly.check_single_call(
            estimated_microdollars=estimated_microdollars,
            per_session_remaining_microdollars=session_tracker.remaining_microdollars(),
        )
        if anomaly is not None:
            raise anomaly

        # Reserve across all five windows; track successes for rollback.
        reserved_per_window: dict[WindowName, int] = {}
        consulted: list[WindowName] = []
        period_keys: dict[WindowName, str] = {}
        for window in WINDOW_NAMES:
            period_key = self._scheduler.current_period_key(
                window, at_time=now, session_id=self._session_id, intent_id=intent_id
            )
            period_keys[window] = period_key
            self._arm_thresholds(window, period_key)
            tracker = self._windows.tracker(window, period_key)
            consulted.append(window)
            if not tracker.reserve(estimated_microdollars):
                self._rollback(reserved_per_window, period_keys)
                raise BudgetExhaustedError(
                    window=window,
                    requested_microdollars=estimated_microdollars,
                    remaining_microdollars=tracker.remaining_microdollars(),
                    allocated_microdollars=self._ceiling_for(window),
                )
            reserved_per_window[window] = estimated_microdollars

        # High-velocity pattern: a maximal (>= per_call ceiling) call counts as
        # a ceiling hit; 5 in 60s routes to a Grant Moment (T-093).
        if estimated_microdollars >= self._ceiling_for("per_call"):
            high_velocity = self._anomaly.record_ceiling_hit(now)
            if high_velocity is not None:
                self._rollback(reserved_per_window, period_keys)
                raise high_velocity

        handle = ReservationHandle(
            reservation_id=new_reservation_id(),
            intent_id=intent_id,
            reserved_microdollars=estimated_microdollars,
            reserved_per_window=dict(reserved_per_window),
            expires_at=now + self._ttl,
            ceilings_consulted=consulted,
            created_at=now,
        )
        self._active_reservations[handle.reservation_id] = handle
        return handle

    def record_for_call(self, handle: ReservationHandle, actual_microdollars: int) -> None:
        """Finalize `handle` against all five windows with the actual cost.

        Idempotency: a second record of the same `reservation_id` raises
        `ReservationDoubleRecordError` — the EC-8 cross-channel no-double-
        billing guard (`02-mvp-objectives.md` line 117). A record after the
        reservation TTL raises `ReservationExpiredError`; the held capacity is
        released first so it is not leaked.
        """
        self._validate_microdollars(actual_microdollars, "actual_microdollars")
        now = self._clock()

        prior = self._recorded_reservations.get(handle.reservation_id)
        if prior is not None:
            raise ReservationDoubleRecordError(
                reservation_id=handle.reservation_id, first_recorded_at=prior
            )

        period_keys = self._period_keys_for(handle)
        if now > handle.expires_at:
            # Release the held reservation (record actual=0) so it is not leaked,
            # then refuse the late record.
            self._rollback(handle.reserved_per_window, period_keys)
            self._active_reservations.pop(handle.reservation_id, None)
            raise ReservationExpiredError(
                reservation_id=handle.reservation_id,
                expired_at=handle.expires_at.isoformat(),
                recorded_at=now.isoformat(),
            )

        for window, reserved in handle.reserved_per_window.items():
            tracker = self._windows.tracker(window, period_keys[window])
            tracker.record(reserved, actual_microdollars)

        self._windows.evict_per_call(period_keys["per_call"])
        self._recorded_reservations[handle.reservation_id] = now.isoformat()
        self._active_reservations.pop(handle.reservation_id, None)

        if self._ledger_emitter is not None:
            self._ledger_emitter.enqueue_reservation_record(handle, actual_microdollars)

    # ------------------------------------------------------------------
    # Non-mutating check + snapshot
    # ------------------------------------------------------------------

    def check(self, estimated_microdollars: int, *, intent_id: str = "check") -> BudgetCheckResult:
        """Non-mutating multi-window check; returns the MOST RESTRICTIVE window's
        result (the binding window) per design § 3.2 item 1."""
        self._validate_microdollars(estimated_microdollars, "estimated_microdollars")
        now = self._clock()
        results = []
        for window in WINDOW_NAMES:
            period_key = self._scheduler.current_period_key(
                window, at_time=now, session_id=self._session_id, intent_id=intent_id
            )
            results.append(self._windows.tracker(window, period_key).check(estimated_microdollars))
        # Most restrictive = smallest remaining headroom after the estimate;
        # a disallowed window always binds over an allowed one.
        return min(
            results,
            key=lambda r: (r.allowed, r.remaining_microdollars - estimated_microdollars),
        )

    def snapshot(self) -> MultiWindowSnapshot:
        """Snapshot all five windows at one instant."""
        now = self._clock()
        snaps = {}
        for window in WINDOW_NAMES:
            period_key = self._scheduler.current_period_key(
                window, at_time=now, session_id=self._session_id, intent_id="snapshot"
            )
            snaps[window] = self._windows.tracker(window, period_key).snapshot()
        return MultiWindowSnapshot(
            per_call=snaps["per_call"],
            per_session=snaps["per_session"],
            per_hour_velocity=snaps["per_hour_velocity"],
            per_day=snaps["per_day"],
            per_month=snaps["per_month"],
            captured_at=now,
        )

    # ------------------------------------------------------------------
    # Velocity ratchet (T-093 R2-H4)
    # ------------------------------------------------------------------

    def lower_velocity_limit(self, window: WindowName, new_microdollars: int) -> None:
        """Lower a window ceiling inline — always allowed per spec line 39."""
        self._validate_microdollars(new_microdollars, "new_microdollars")
        current = self._ceiling_for(window)
        if new_microdollars > current:
            raise VelocityRaiseInlineBlockError(
                window=window,
                current_microdollars=current,
                requested_microdollars=new_microdollars,
            )
        self._apply_override(window, new_microdollars)

    def raise_velocity_limit(
        self,
        window: WindowName,
        new_microdollars: int,
        *,
        cooling_off_grant_ref: str | None = None,
    ) -> None:
        """Raise a window ceiling — BLOCKED inline (T-093 R2-H4).

        Without a `cooling_off_grant_ref` (a 24h-aged cross-channel Grant
        Moment), this raises `VelocityRaiseInlineBlockError`. With a valid ref
        the raise is permitted. Phase 01 records the ref; the Weekly Posture
        Review path is Phase 02.
        """
        self._validate_microdollars(new_microdollars, "new_microdollars")
        current = self._ceiling_for(window)
        if new_microdollars <= current:
            # Not a raise — delegate to the inline-lowering path.
            self._apply_override(window, new_microdollars)
            return
        if cooling_off_grant_ref is None:
            raise VelocityRaiseInlineBlockError(
                window=window,
                current_microdollars=current,
                requested_microdollars=new_microdollars,
            )
        self._apply_override(window, new_microdollars)
        # An approved raise mutated the ceiling — record it for the audit trail
        # (Daily Digest consumes budget_extended; the independent verifier
        # hash-checks it). Per design § 3.2 item 7.
        if self._ledger_emitter is not None:
            self._ledger_emitter.enqueue_budget_extended(
                window=window,
                prior_allocated_microdollars=current,
                new_allocated_microdollars=new_microdollars,
                grant_moment_ref=cooling_off_grant_ref,
            )

    def _apply_override(self, window: WindowName, new_microdollars: int) -> None:
        """Apply an inline ceiling override to the window's current-period tracker."""
        now = self._clock()
        period_key = self._scheduler.current_period_key(
            window, at_time=now, session_id=self._session_id, intent_id="ceiling_change"
        )
        self._windows.apply_override(window, new_microdollars, period_key=period_key)

    # ------------------------------------------------------------------
    # Threshold subscription (sync seam onto upstream set_threshold_callback)
    # ------------------------------------------------------------------

    def subscribe_threshold(
        self,
        window: WindowName,
        threshold_pct: float,
        on_cross: Callable[[EnvoyBudgetEvent], None],
    ) -> int:
        """Arm a custom threshold callback on `window`'s current tracker.

        `on_cross` is SYNC — it runs on the upstream callback thread (outside
        the upstream `_lock`). It MUST be non-blocking (e.g.
        `ThresholdDispatcher.enqueue`); the async Grant-Moment / Ledger work
        happens off this thread per design § 3.2 item 4. Returns the upstream
        callback handle (for `unregister`).

        NaN/Inf `threshold_pct` is rejected by the upstream
        `set_threshold_callback` (`budget_tracker.py` finite-guard); Envoy does
        NOT bypass that guard (design § 6.4).
        """
        now = self._clock()
        period_key = self._scheduler.current_period_key(
            window, at_time=now, session_id=self._session_id, intent_id="subscribe"
        )
        tracker = self._windows.tracker(window, period_key)

        def _bridge(event: BudgetEvent) -> None:
            on_cross(self._to_envoy_event(window, period_key, event, now=self._clock()))

        return tracker.set_threshold_callback(threshold_pct, _bridge)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _arm_thresholds(self, window: WindowName, period_key: str) -> None:
        """Arm the default threshold callbacks on a freshly-minted tracker once.

        Idempotent per `(window, period_key, pct)` — re-arming on a tracker
        that already has the callback would double-fire. Only arms when a
        `threshold_sink` is wired (otherwise there is no consumer and arming
        would be an orphan).

        Thresholds are armed ONLY on the cumulative windows (per_session /
        per_hour_velocity / per_day / per_month). The per_call window is
        excluded: a single call near its per-call ceiling is not a
        "budget-approaching-exhaustion" warning (that magnitude check is the
        `AnomalyDetector`'s job per spec § Budget-exhaustion fraud defense);
        arming per_call would fire a Grant-Moment warning on every substantial
        call. Threshold callbacks exist for cumulative-spend surfacing per
        `specs/budget-tracker.md` § Threshold callbacks.
        """
        if self._threshold_sink is None or window == "per_call":
            return
        for pct in self._default_threshold_pcts:
            arm_key = (window, period_key, pct)
            if arm_key in self._armed_thresholds:
                continue
            tracker = self._windows.tracker(window, period_key)

            # Bind window / period_key / sink as defaults so each armed callback
            # captures its own values (not the loop's final iteration).
            def _bridge(
                event: BudgetEvent,
                _w: WindowName = window,
                _pk: str = period_key,
                _sink: _ThresholdSink = self._threshold_sink,
            ) -> None:
                _sink.enqueue(self._to_envoy_event(_w, _pk, event, now=self._clock()))

            tracker.set_threshold_callback(pct, _bridge)
            self._armed_thresholds.add(arm_key)

    def _to_envoy_event(
        self, window: WindowName, period_key: str, event: BudgetEvent, *, now: datetime
    ) -> EnvoyBudgetEvent:
        return EnvoyBudgetEvent(
            principal_id=self._principal_id,
            window=window,
            period_key=period_key,
            threshold_pct=event.threshold_pct if event.threshold_pct is not None else 0.0,
            committed_microdollars=event.committed_microdollars or 0,
            reserved_microdollars=event.reserved_microdollars or 0,
            allocated_microdollars=event.allocated_microdollars,
            observed_at=event.timestamp if event.timestamp is not None else now,
        )

    def _rollback(
        self, reserved_per_window: dict[WindowName, int], period_keys: dict[WindowName, str]
    ) -> None:
        """Release reservations on the windows that already succeeded.

        Upstream has no un-reserve; `record(reserved, 0)` releases the held
        amount and commits nothing — the canonical release path.
        """
        for window, reserved in reserved_per_window.items():
            tracker = self._windows.tracker(window, period_keys[window])
            tracker.record(reserved, 0)

    def _period_keys_for(self, handle: ReservationHandle) -> dict[WindowName, str]:
        """Recompute the period keys a handle reserved against (from created_at).

        Using `created_at` (not now) hits the SAME trackers the reservation
        landed on, so record finalizes the right windows even if a period has
        since rolled over."""
        return {
            window: self._scheduler.current_period_key(
                window,
                at_time=handle.created_at,
                session_id=self._session_id,
                intent_id=handle.intent_id,
            )
            for window in handle.reserved_per_window
        }

    def _ceiling_for(self, window: WindowName) -> int:
        """Effective ceiling — the inline override if set, else the envelope value."""
        return self._windows.effective_ceiling(window)

    @staticmethod
    def _validate_microdollars(value: int, field_name: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise MicrodollarOverflowError(value=value, field_name=field_name)  # type: ignore[arg-type]
        if value < 0 or value > INT64_MAX:
            raise MicrodollarOverflowError(value=value, field_name=field_name)
