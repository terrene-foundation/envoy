# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression — repeated record of an expired handle MUST NOT over-release siblings.

Surfaced by the reviewer round on `feat/phase-01-shard-12-budget-tracker`
(HIGH-1, confirmed reproduction): the TTL-expiry branch of `record_for_call`
called `_rollback` and raised `ReservationExpiredError` WITHOUT marking the
reservation as consumed in `_recorded_reservations`. A second `record_for_call`
of the same expired handle re-entered the expiry branch and re-ran `_rollback`,
which calls `upstream tracker.record(reserved, 0)` — upstream's saturating
subtract floors at 0, so the second release ate any *sibling* in-flight
reservation's held capacity on the same window. The mirror of the EC-8
no-double-billing invariant: no double-RELEASE either.

Fix: mark the reservation consumed (record-intent-first) BEFORE `_rollback`
in the expiry branch (and before the record loop in the success branch), so
any retry hits the double-record guard instead of re-running the release.

Per `rules/testing.md` § Regression Testing — pinned so this class of
accounting corruption cannot silently reappear.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from envoy.budget import (
    EnvoyBudgetOrchestrator,
    ReservationDoubleRecordError,
    ReservationExpiredError,
    WindowCeilings,
)

# Sized so a sibling reservation has visible headroom against the per_hour
# velocity window — the binding window for the over-release vector.
_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=10_000_000,
    per_session_ceiling_microdollars=100_000_000,
    per_hour_velocity_microdollars=5_000_000,
    per_day_ceiling_microdollars=50_000_000,
    per_month_ceiling_microdollars=1_000_000_000,
)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


@pytest.mark.regression
class TestRepeatedExpiredRecord:
    def test_second_record_of_expired_handle_does_not_over_release_sibling(self) -> None:
        clock = _Clock()
        orch = EnvoyBudgetOrchestrator(
            ceilings=_CEIL,
            store=None,
            principal_id="alice",
            session_id="s1",
            clock=clock,
            reservation_ttl_seconds=60,
        )
        # Reserve 3M (expiring) + 1M sibling on the same per_hour window.
        # per_hour: 4M reserved of 5M; remaining 1M.
        expiring = orch.reserve_for_call(3_000_000, intent_id="expiring")
        orch.reserve_for_call(1_000_000, intent_id="sibling")
        assert orch.window_check("per_hour_velocity").remaining_microdollars == 1_000_000

        # Advance past the 60s TTL.
        clock.now = clock.now + timedelta(seconds=120)

        # First record of the expired handle: releases its 3M; sibling's 1M
        # reservation must remain held.
        with pytest.raises(ReservationExpiredError):
            orch.record_for_call(expiring, 0)
        assert orch.window_check("per_hour_velocity").remaining_microdollars == 4_000_000

        # Second record of the same expired handle: MUST hit the guard, NOT
        # re-run _rollback. The sibling's 1M reservation MUST still be held.
        with pytest.raises(ReservationDoubleRecordError):
            orch.record_for_call(expiring, 0)
        assert orch.window_check("per_hour_velocity").remaining_microdollars == 4_000_000

        # Third and Nth attempts behave the same — the guard is permanent.
        for _ in range(3):
            with pytest.raises(ReservationDoubleRecordError):
                orch.record_for_call(expiring, 0)
        assert orch.window_check("per_hour_velocity").remaining_microdollars == 4_000_000

    def test_expired_handle_release_is_idempotent_under_concurrent_sibling_load(self) -> None:
        # A sibling that proceeds to record (not just hold) is also safe: the
        # repeated expired-record must not re-release into the sibling's
        # post-record committed state.
        clock = _Clock()
        orch = EnvoyBudgetOrchestrator(
            ceilings=_CEIL,
            store=None,
            principal_id="alice",
            session_id="s1",
            clock=clock,
            reservation_ttl_seconds=60,
        )
        expiring = orch.reserve_for_call(3_000_000, intent_id="expiring")
        sibling = orch.reserve_for_call(1_000_000, intent_id="sibling")
        orch.record_for_call(sibling, 1_000_000)  # sibling commits 1M
        assert orch.window_check("per_hour_velocity").committed_microdollars == 1_000_000

        clock.now = clock.now + timedelta(seconds=120)
        with pytest.raises(ReservationExpiredError):
            orch.record_for_call(expiring, 0)
        # sibling committed unchanged after expiring's first release
        assert orch.window_check("per_hour_velocity").committed_microdollars == 1_000_000

        # Repeated expired-record must not corrupt sibling's committed.
        for _ in range(3):
            with pytest.raises(ReservationDoubleRecordError):
                orch.record_for_call(expiring, 0)
        assert orch.window_check("per_hour_velocity").committed_microdollars == 1_000_000
