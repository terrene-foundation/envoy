# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression — T-093 budget-exhaustion fraud defense.

Spec authority: `specs/budget-tracker.md` § Budget-exhaustion fraud defense:
"anomaly detection (single call > 50% of session budget → pause for
confirmation); high-velocity pattern detection (5 calls at ceiling in 1min →
Grant Moment)." Pre-declared by spec § Test location as
`test_t093_budget_exhaustion_fraud.py`.

Per `rules/testing.md` § Regression Testing — pinned so the two fraud
detectors cannot silently regress.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from envoy.budget import (
    AnomalyDetectedError,
    EnvoyBudgetOrchestrator,
    HighVelocityPatternError,
    WindowCeilings,
)

# Anomaly path: per_call large so multi-million-microdollar calls exercise the
# single-call >50%-of-session detector without tripping the per_call ceiling.
_ANOMALY_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=10_000_000,
    per_session_ceiling_microdollars=10_000_000,
    per_hour_velocity_microdollars=1_000_000_000,
    per_day_ceiling_microdollars=1_000_000_000,
    per_month_ceiling_microdollars=10_000_000_000,
)

# Velocity-burst path: per_call == 1M so a maximal call hits the per_call
# ceiling (the ceiling-hit the high-velocity detector counts). Session large
# so the burst is not pre-empted by the anomaly detector.
_VELOCITY_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=1_000_000,
    per_session_ceiling_microdollars=1_000_000_000,
    per_hour_velocity_microdollars=1_000_000_000,
    per_day_ceiling_microdollars=1_000_000_000,
    per_month_ceiling_microdollars=10_000_000_000,
)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def _orch(clock: _Clock, ceilings: WindowCeilings) -> EnvoyBudgetOrchestrator:
    return EnvoyBudgetOrchestrator(
        ceilings=ceilings, store=None, principal_id="alice", session_id="s1", clock=clock
    )


@pytest.mark.regression
class TestSingleCallAnomaly:
    def test_call_over_50pct_of_session_remaining_raises(self) -> None:
        orch = _orch(_Clock(), _ANOMALY_CEIL)
        # Session fresh at 10M; a 6M call is > 50% (5M) of remaining → anomaly.
        with pytest.raises(AnomalyDetectedError) as ei:
            orch.reserve_for_call(6_000_000, intent_id="i1")
        assert ei.value.session_remaining_microdollars == 10_000_000
        assert ei.value.threshold_pct == 0.50

    def test_call_under_50pct_is_allowed(self) -> None:
        orch = _orch(_Clock(), _ANOMALY_CEIL)
        # 4M < 50% of 10M — allowed (no anomaly).
        handle = orch.reserve_for_call(4_000_000, intent_id="i1")
        assert handle.reserved_microdollars == 4_000_000

    def test_anomaly_is_relative_to_remaining_not_total(self) -> None:
        orch = _orch(_Clock(), _ANOMALY_CEIL)
        # Ramp the session down to 3M remaining WITHOUT any single call
        # exceeding 50% of remaining-at-that-time (so no premature anomaly):
        # 10M -> 8M -> 6M -> 4M -> 3M.
        for n, cost in enumerate((2_000_000, 2_000_000, 2_000_000, 1_000_000)):
            h = orch.reserve_for_call(cost, intent_id=f"ramp{n}")
            orch.record_for_call(h, cost)
        # 3M remaining; a 2M call is > 50% (1.5M) of REMAINING → anomaly,
        # even though 2M is only 20% of the 10M session TOTAL.
        with pytest.raises(AnomalyDetectedError) as ei:
            orch.reserve_for_call(2_000_000, intent_id="i-anomaly")
        assert ei.value.session_remaining_microdollars == 3_000_000


@pytest.mark.regression
class TestHighVelocityPattern:
    def test_five_ceiling_hits_in_60s_raises(self) -> None:
        clock = _Clock()
        orch = _orch(clock, _VELOCITY_CEIL)
        # Five maximal (== per_call ceiling) calls within 60s → high-velocity.
        # First four reserve+record; the fifth reserve trips the pattern.
        for n in range(4):
            clock.now = clock.now + timedelta(seconds=5)
            h = orch.reserve_for_call(1_000_000, intent_id=f"i{n}")
            orch.record_for_call(h, 1_000_000)
        clock.now = clock.now + timedelta(seconds=5)  # still within 60s of first
        with pytest.raises(HighVelocityPatternError) as ei:
            orch.reserve_for_call(1_000_000, intent_id="i4")
        assert ei.value.hits == 5
        assert ei.value.window_seconds == 60

    def test_ceiling_hits_spread_beyond_window_do_not_fire(self) -> None:
        clock = _Clock()
        orch = _orch(clock, _VELOCITY_CEIL)
        # Five maximal calls spaced 20s apart span 80s > 60s window → no fire.
        for n in range(5):
            h = orch.reserve_for_call(1_000_000, intent_id=f"i{n}")
            orch.record_for_call(h, 1_000_000)
            clock.now = clock.now + timedelta(seconds=20)
        # A 6th maximal call: the oldest of the last 5 hits is now 80s back → safe.
        handle = orch.reserve_for_call(1_000_000, intent_id="i5")
        assert handle.reserved_microdollars == 1_000_000
