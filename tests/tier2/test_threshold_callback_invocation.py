# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — set_threshold_callback fires at the correct % + rising-edge one-shot.

Spec authority: `specs/budget-tracker.md` § Threshold callbacks ("invoke when
`(committed + reserved) / allocated >= threshold`"). Pre-declared by spec
§ Test location as `test_threshold_callback_invocation.py`. Also covers the
rising-edge one-shot semantics (design § 2.2 / § 6.1 test 3): a threshold fires
once per registration and does NOT re-fire on oscillation.
"""

from __future__ import annotations

import pytest

from envoy.budget import EnvoyBudgetEvent, WindowCeilings
from tests.helpers.budget_harness import build_harness, no_op_anomaly_detector

# per_session 1M, isolated so a custom threshold on it is easy to cross.
_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=1_000_000,
    per_session_ceiling_microdollars=1_000_000,
    per_hour_velocity_microdollars=1_000_000_000,
    per_day_ceiling_microdollars=1_000_000_000,
    per_month_ceiling_microdollars=1_000_000_000,
)


@pytest.mark.asyncio
class TestThresholdCallbackInvocation:
    async def test_custom_threshold_fires_when_crossed(self) -> None:
        h = await build_harness(ceilings=_CEIL, anomaly_detector=no_op_anomaly_detector())
        fired: list[EnvoyBudgetEvent] = []
        h.orchestrator.subscribe_threshold("per_session", 0.80, fired.append)
        # Cross 80% of the 1M session ceiling.
        handle = h.orchestrator.reserve_for_call(850_000, intent_id="i1")
        h.orchestrator.record_for_call(handle, 850_000)
        assert len(fired) == 1
        assert fired[0].window == "per_session"
        assert fired[0].threshold_pct == pytest.approx(0.80)

    async def test_below_threshold_does_not_fire(self) -> None:
        h = await build_harness(ceilings=_CEIL, anomaly_detector=no_op_anomaly_detector())
        fired: list[EnvoyBudgetEvent] = []
        h.orchestrator.subscribe_threshold("per_session", 0.80, fired.append)
        handle = h.orchestrator.reserve_for_call(500_000, intent_id="i1")  # 50% < 80%
        h.orchestrator.record_for_call(handle, 500_000)
        assert fired == []

    async def test_rising_edge_one_shot_no_refire_on_oscillation(self) -> None:
        h = await build_harness(ceilings=_CEIL, anomaly_detector=no_op_anomaly_detector())
        fired: list[EnvoyBudgetEvent] = []
        h.orchestrator.subscribe_threshold("per_session", 0.80, fired.append)
        # Cross 80% (reserve 850k) — fires once.
        handle1 = h.orchestrator.reserve_for_call(850_000, intent_id="i1")
        assert len(fired) == 1
        # Record low (release most of the reservation) — back below threshold.
        h.orchestrator.record_for_call(handle1, 100_000)
        # Cross 80% again — the rising-edge one-shot does NOT re-fire.
        handle2 = h.orchestrator.reserve_for_call(850_000, intent_id="i2")
        h.orchestrator.record_for_call(handle2, 850_000)
        assert len(fired) == 1  # still one — spec § Threshold callbacks contract
