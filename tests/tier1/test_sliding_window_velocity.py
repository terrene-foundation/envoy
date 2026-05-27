# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — multi-window sliding accumulation + velocity ceiling enforcement.

Spec authority: `specs/budget-tracker.md` § Ceilings (five windows) + § Check
shape ("O(1) to O(log n) sliding-window sum"). Pre-declared by spec
§ Test location as `test_sliding_window_velocity.py` (reconciled to
`tests/tier1/`).

The upstream `BudgetTracker` owns the sliding-window sum; these tests verify
the Envoy multi-window orchestration: each window accumulates independently,
the per-hour velocity ceiling binds before the absolute session/day/month
ceilings, and the binding window is correctly identified.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from envoy.budget import BudgetExhaustedError, EnvoyBudgetOrchestrator, WindowCeilings

_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=2_000_000,
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


def _orch(clock: _Clock) -> EnvoyBudgetOrchestrator:
    return EnvoyBudgetOrchestrator(
        ceilings=_CEIL, store=None, principal_id="alice", session_id="s1", clock=clock
    )


class TestMultiWindowAccumulation:
    def test_each_window_accumulates_committed_independently(self) -> None:
        orch = _orch(_Clock())
        for n in range(3):
            h = orch.reserve_for_call(1_000_000, intent_id=f"i{n}")
            orch.record_for_call(h, 1_000_000)
        snap = orch.snapshot()
        # Cumulative windows all reflect 3M committed; per_call is transient (0).
        assert snap.per_session.committed == 3_000_000
        assert snap.per_hour_velocity.committed == 3_000_000
        assert snap.per_day.committed == 3_000_000
        assert snap.per_month.committed == 3_000_000


class TestVelocityCeilingBinds:
    def test_per_hour_velocity_binds_before_session(self) -> None:
        # per_hour=5M is the binding window; session=100M has ample headroom.
        orch = _orch(_Clock())
        for n in range(5):
            h = orch.reserve_for_call(1_000_000, intent_id=f"i{n}")
            orch.record_for_call(h, 1_000_000)
        # 6th call (would be 6M > 5M per_hour) refused on the velocity window,
        # even though the session window (100M) has plenty left.
        with pytest.raises(BudgetExhaustedError) as ei:
            orch.reserve_for_call(1_000_000, intent_id="i6")
        assert ei.value.window == "per_hour_velocity"

    def test_velocity_window_resets_next_hour(self) -> None:
        clock = _Clock()
        orch = _orch(clock)
        for n in range(5):
            h = orch.reserve_for_call(1_000_000, intent_id=f"i{n}")
            orch.record_for_call(h, 1_000_000)
        # Roll the clock to the next UTC hour — the per_hour window mints fresh.
        clock.now = datetime(2026, 5, 3, 11, 0, 0, tzinfo=timezone.utc)
        h = orch.reserve_for_call(1_000_000, intent_id="i-next-hour")
        orch.record_for_call(h, 1_000_000)
        snap = orch.snapshot()
        # New hour window committed only the post-rollover call; the day window
        # still carries the full cumulative spend (does not reset hourly).
        assert snap.per_hour_velocity.committed == 1_000_000
        assert snap.per_day.committed == 6_000_000


class TestBindingWindowReporting:
    def test_check_reports_most_restrictive_window(self) -> None:
        orch = _orch(_Clock())
        # Consume 4M of the 5M per_hour window.
        for n in range(4):
            h = orch.reserve_for_call(1_000_000, intent_id=f"i{n}")
            orch.record_for_call(h, 1_000_000)
        # A 1.5M estimate: per_hour has 1M left (disallowed); session has 98.5M
        # (allowed). The binding result is the disallowed per_hour window.
        result = orch.check(1_500_000)
        assert result.allowed is False
        assert result.remaining_microdollars == 1_000_000
