# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — velocity raise unlocked by a 24h-aged cooling-off Grant Moment.

Spec authority: `specs/budget-tracker.md` § Velocity-raise ratchet — raising a
velocity limit requires "Weekly Posture Review OR cross-channel Grant Moment
with 24h cooling-off." Pre-declared by spec § Test location as
`test_velocity_raise_24h_cooling_off.py`.

Asserts the approved raise (a) takes effect on enforcement and (b) writes a
`budget_extended` Ledger entry for the audit trail (design § 3.2 item 7).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from envoy.budget import WindowCeilings
from tests.helpers.budget_harness import build_harness

_SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_UNTIL = datetime(2027, 1, 1, tzinfo=timezone.utc)

# per_call + session large so per_hour_velocity (5M) is the window under raise.
_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=10_000_000,
    per_session_ceiling_microdollars=100_000_000,
    per_hour_velocity_microdollars=5_000_000,
    per_day_ceiling_microdollars=50_000_000,
    per_month_ceiling_microdollars=1_000_000_000,
)


@pytest.mark.asyncio
class TestVelocityRaiseCoolingOff:
    async def test_approved_raise_takes_effect_and_emits_budget_extended(self) -> None:
        h = await build_harness(ceilings=_CEIL)
        o = h.orchestrator
        # Spend 4M of the 5M per_hour window.
        for n in range(2):
            handle = o.reserve_for_call(2_000_000, intent_id=f"pre{n}")
            o.record_for_call(handle, 2_000_000)
        # Raise per_hour 5M -> 9M via a 24h-aged cooling-off Grant Moment ref.
        o.raise_velocity_limit(
            "per_hour_velocity", 9_000_000, cooling_off_grant_ref="gm-aged-24h-001"
        )
        # The raise took effect: a further 4M (total 8M) now fits under the 9M
        # ceiling — which would have exceeded the original 5M.
        handle = o.reserve_for_call(4_000_000, intent_id="post")
        o.record_for_call(handle, 4_000_000)
        assert o.snapshot().per_hour_velocity.committed == 8_000_000

        # budget_extended Ledger entry recorded the raise.
        await h.emitter.drain()
        entries = await h.ledger.query(filter={}, since=_SINCE, until=_UNTIL)
        extended = [e for e in entries if e.type == "budget_extended"]
        assert len(extended) == 1
        assert extended[0].content["window"] == "per_hour_velocity"
        assert extended[0].content["prior_allocated_microdollars"] == 5_000_000
        assert extended[0].content["new_allocated_microdollars"] == 9_000_000
        assert extended[0].content["grant_moment_ref"] == "gm-aged-24h-001"
