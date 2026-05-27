# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression — T-019 velocity-ratchet defense: inline velocity RAISE refused.

Spec authority: `specs/budget-tracker.md` § Velocity-raise ratchet (T-093
R2-H4): "RAISING any velocity limit CANNOT be inline. Requires Weekly Posture
Review OR cross-channel Grant Moment with 24h cooling-off. Lowering allowed
inline." Pre-declared by spec § Test location as
`test_t019_velocity_raise_inline_block.py`.

Per `rules/testing.md` § Regression Testing — pinned so the ratchet cannot
silently regress to allowing inline raises (the T-019 rubber-stamp threat).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from envoy.budget import (
    EnvoyBudgetOrchestrator,
    VelocityRaiseInlineBlockError,
    WindowCeilings,
)

# per_call + per_session sized large so per_hour_velocity (5M) is the clean
# binding window under test — isolates the ratchet from per_call / anomaly guards.
_CEIL = WindowCeilings(10_000_000, 100_000_000, 5_000_000, 50_000_000, 1_000_000_000)


def _orch() -> EnvoyBudgetOrchestrator:
    return EnvoyBudgetOrchestrator(
        ceilings=_CEIL,
        store=None,
        principal_id="alice",
        session_id="s1",
        clock=lambda: datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.mark.regression
class TestVelocityRaiseRatchet:
    def test_inline_raise_without_cooling_off_is_blocked(self) -> None:
        orch = _orch()
        with pytest.raises(VelocityRaiseInlineBlockError) as ei:
            orch.raise_velocity_limit("per_hour_velocity", 8_000_000)
        assert ei.value.window == "per_hour_velocity"
        assert ei.value.current_microdollars == 5_000_000
        assert ei.value.requested_microdollars == 8_000_000

    def test_lower_velocity_limit_is_allowed_inline(self) -> None:
        orch = _orch()
        # Lowering is always permitted inline (spec line 39).
        orch.lower_velocity_limit("per_hour_velocity", 3_000_000)
        # The lowered ceiling now binds: reserving 4M exceeds the new 3M limit.
        with pytest.raises(Exception) as ei:
            orch.reserve_for_call(4_000_000, intent_id="i1")
        assert "per_hour_velocity" in str(ei.value)

    def test_lower_via_raise_api_is_not_a_raise(self) -> None:
        # Calling raise_velocity_limit with a value <= current is a lowering,
        # not a raise — it MUST NOT be blocked.
        orch = _orch()
        orch.raise_velocity_limit("per_hour_velocity", 4_000_000)  # below 5M current
        with pytest.raises(Exception) as ei:
            orch.reserve_for_call(4_500_000, intent_id="i1")
        assert "per_hour_velocity" in str(ei.value)

    def test_raise_with_cooling_off_grant_ref_is_permitted(self) -> None:
        orch = _orch()
        # A 24h-aged cross-channel Grant Moment ref unlocks the raise.
        orch.raise_velocity_limit(
            "per_hour_velocity", 8_000_000, cooling_off_grant_ref="grant-aged-24h"
        )
        # The raised ceiling now allows cumulative spend that previously
        # exceeded the 5M limit: 3 x 2M = 6M committed against the raised 8M.
        for n in range(3):
            h = orch.reserve_for_call(2_000_000, intent_id=f"i{n}")
            orch.record_for_call(h, 2_000_000)
        assert orch.snapshot().per_hour_velocity.committed == 6_000_000
