# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — concurrent reservations sum against ceilings + double-record guard.

Spec authority: `specs/budget-tracker.md` § Reserve/record pattern
("Concurrent reservations sum against ceilings"). Pre-declared by spec
§ Test location as `test_reserve_record_concurrency.py`.

Also pins the EC-8 cross-channel no-double-billing guard
(`02-mvp-objectives.md` line 117 / implementation doc line 460): the same
`reservation_id` recorded twice — e.g. from a sibling channel adapter —
raises `ReservationDoubleRecordError` rather than charging the budget twice.
"""

from __future__ import annotations

import pytest

from envoy.budget import (
    BudgetExhaustedError,
    ReservationDoubleRecordError,
    WindowCeilings,
)
from tests.helpers.budget_harness import build_harness, no_op_anomaly_detector

# per_session 1M so concurrent reservations sum visibly against it.
_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=1_000_000,
    per_session_ceiling_microdollars=1_000_000,
    per_hour_velocity_microdollars=1_000_000_000,
    per_day_ceiling_microdollars=1_000_000_000,
    per_month_ceiling_microdollars=1_000_000_000,
)


@pytest.mark.asyncio
class TestConcurrentReservations:
    async def test_outstanding_reservations_sum_against_session_ceiling(self) -> None:
        h = await build_harness(ceilings=_CEIL, anomaly_detector=no_op_anomaly_detector())
        o = h.orchestrator
        # Two outstanding (un-recorded) reservations consume 800k of the 1M
        # session ceiling; a third 400k reservation would total 1.2M > 1M.
        o.reserve_for_call(400_000, intent_id="r1")
        o.reserve_for_call(400_000, intent_id="r2")
        with pytest.raises(BudgetExhaustedError) as ei:
            o.reserve_for_call(400_000, intent_id="r3")
        assert ei.value.window == "per_session"

    async def test_recording_releases_reserved_headroom(self) -> None:
        h = await build_harness(ceilings=_CEIL, anomaly_detector=no_op_anomaly_detector())
        o = h.orchestrator
        handle = o.reserve_for_call(900_000, intent_id="r1")
        # Recording at a lower actual frees headroom (900k reserved -> 100k committed).
        o.record_for_call(handle, 100_000)
        # 900k headroom now available again (1M - 100k committed).
        handle2 = o.reserve_for_call(800_000, intent_id="r2")
        assert handle2.reserved_microdollars == 800_000


@pytest.mark.asyncio
class TestDoubleRecordGuard:
    async def test_same_reservation_recorded_twice_raises(self) -> None:
        h = await build_harness(anomaly_detector=no_op_anomaly_detector())
        o = h.orchestrator
        handle = o.reserve_for_call(500_000, intent_id="intent-x")
        o.record_for_call(handle, 450_000)
        # EC-8b: a sibling channel attempting to record the same reservation
        # is refused — the cost is NOT charged twice.
        with pytest.raises(ReservationDoubleRecordError) as ei:
            o.record_for_call(handle, 450_000)
        assert ei.value.reservation_id == handle.reservation_id

    async def test_double_record_does_not_double_charge(self) -> None:
        h = await build_harness(anomaly_detector=no_op_anomaly_detector())
        o = h.orchestrator
        handle = o.reserve_for_call(500_000, intent_id="intent-y")
        o.record_for_call(handle, 450_000)
        committed_after_first = o.snapshot().per_session.committed
        with pytest.raises(ReservationDoubleRecordError):
            o.record_for_call(handle, 450_000)
        # Committed is unchanged by the refused second record.
        assert o.snapshot().per_session.committed == committed_after_first == 450_000
