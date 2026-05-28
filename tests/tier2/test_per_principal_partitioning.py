# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — per-principal partitioning (tenant-isolation Rule 1).

Design § 6.1 test 4. The `tracker_id` carries `principal_id` from day 1 (even
though Phase 01 ships single-principal) per `rules/tenant-isolation.md` Rule 1
(cache-key tenant dimension). Two orchestrators with different principals MUST
have distinct tracker keys and MUST NOT consume each other's allocation.
"""

from __future__ import annotations

import pytest

from envoy.budget import MultiWindowBudget, WindowCeilings
from tests.helpers.budget_harness import build_harness, no_op_anomaly_detector

_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=1_000_000,
    per_session_ceiling_microdollars=1_000_000,
    per_hour_velocity_microdollars=1_000_000_000,
    per_day_ceiling_microdollars=1_000_000_000,
    per_month_ceiling_microdollars=1_000_000_000,
)


class TestTrackerIdShape:
    def test_principal_id_present_in_tracker_key(self) -> None:
        budget = MultiWindowBudget(
            ceilings=_CEIL, store=None, principal_id="alice", session_id="s1"
        )
        key = budget.tracker_id("per_day", "2026-05-03")
        # principal_id is in the key even though period_key is already unique —
        # defense-in-depth per tenant-isolation Rule 1.
        assert key == "envoy:v1:alice:per_day:2026-05-03"
        assert "alice" in key

    def test_distinct_principals_distinct_keys(self) -> None:
        alice = MultiWindowBudget(ceilings=_CEIL, store=None, principal_id="alice", session_id="s1")
        bob = MultiWindowBudget(ceilings=_CEIL, store=None, principal_id="bob", session_id="s1")
        assert alice.tracker_id("per_session", "s1") != bob.tracker_id("per_session", "s1")


@pytest.mark.asyncio
class TestNoCrossPrincipalConsumption:
    async def test_reserving_against_alice_does_not_consume_bob(self) -> None:
        alice = await build_harness(ceilings=_CEIL, principal_id="alice", session_id="sa", anomaly_detector=no_op_anomaly_detector())
        bob = await build_harness(ceilings=_CEIL, principal_id="bob", session_id="sb", anomaly_detector=no_op_anomaly_detector())
        # Exhaust alice's 1M session.
        handle = alice.orchestrator.reserve_for_call(1_000_000, intent_id="a1")
        alice.orchestrator.record_for_call(handle, 1_000_000)
        # bob's session is untouched — a full 1M reservation still succeeds.
        bob_handle = bob.orchestrator.reserve_for_call(1_000_000, intent_id="b1")
        assert bob_handle.reserved_microdollars == 1_000_000
        assert bob.orchestrator.snapshot().per_session.committed == 0
