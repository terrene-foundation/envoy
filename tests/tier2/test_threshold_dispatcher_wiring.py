# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — ThresholdDispatcher: threshold cross → Ledger + Grant-Moment seam.

Design § 6.1 test 2. Asserts:
- a `budget_threshold_crossed` Ledger entry is written (the external observable
  per `rules/orphan-detection.md` Rule 1) on a real threshold crossing;
- the injected `on_grant_moment` seam receives the `EnvoyBudgetEvent`;
- the async dispatch runs OUTSIDE the upstream `BudgetTracker._lock` — a
  re-entrant `reserve_for_call` from inside the seam does NOT deadlock
  (design § 2.3 lock discipline).

NO mocking per `rules/testing.md` Tier 2 — real Ledger, real BudgetTracker.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from envoy.budget import EnvoyBudgetEvent
from tests.helpers.budget_harness import build_harness

_SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_UNTIL = datetime(2027, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
class TestThresholdDispatcherWiring:
    async def test_threshold_cross_emits_ledger_entry_and_invokes_seam(self) -> None:
        seen: list[EnvoyBudgetEvent] = []

        async def on_grant_moment(event: EnvoyBudgetEvent) -> None:
            seen.append(event)

        h = await build_harness(on_grant_moment=on_grant_moment)
        # Cross the per_hour_velocity 0.80 threshold (4M of 5M) with sub-per_call
        # calls so no per_call ceiling / anomaly interference.
        for n in range(5):
            handle = h.orchestrator.reserve_for_call(800_000, intent_id=f"c{n}")
            h.orchestrator.record_for_call(handle, 800_000)
        await h.emitter.drain()  # flush reservation_records
        await h.dispatcher.drain_once()  # process queued threshold events

        # External observable: budget_threshold_crossed entries exist for
        # per_hour_velocity at the 0.50 and 0.80 thresholds.
        entries = await h.ledger.query(filter={}, since=_SINCE, until=_UNTIL)
        crossings = [e for e in entries if e.type == "budget_threshold_crossed"]
        windows_pcts = {(e.content["window"], e.content["threshold_bps"]) for e in crossings}
        assert ("per_hour_velocity", 5000) in windows_pcts
        assert ("per_hour_velocity", 8000) in windows_pcts
        # The Grant-Moment seam received the events too.
        assert any(e.window == "per_hour_velocity" for e in seen)
        # Ledger threshold rows carry the redacted principal + int basis points.
        assert all(isinstance(e.content["threshold_bps"], int) for e in crossings)

    async def test_per_call_window_does_not_arm_thresholds(self) -> None:
        # A single large call near the per_call ceiling MUST NOT generate a
        # per_call threshold crossing (per_call is excluded from arming — the
        # anomaly detector owns single-call magnitude, not threshold warnings).
        seen: list[EnvoyBudgetEvent] = []

        async def on_grant_moment(event: EnvoyBudgetEvent) -> None:
            seen.append(event)

        h = await build_harness(on_grant_moment=on_grant_moment)
        handle = h.orchestrator.reserve_for_call(950_000, intent_id="big")  # 95% of per_call
        h.orchestrator.record_for_call(handle, 950_000)
        await h.dispatcher.drain_once()
        assert all(e.window != "per_call" for e in seen)

    async def test_grant_moment_seam_can_reenter_without_deadlock(self) -> None:
        # The seam runs in the async worker, off the upstream callback thread,
        # so a re-entrant reserve_for_call is safe (no _lock deadlock).
        reentry_ok: list[bool] = []

        async def on_grant_moment(event: EnvoyBudgetEvent) -> None:
            # Re-enter the orchestrator from inside the seam.
            handle = h.orchestrator.reserve_for_call(1_000, intent_id="reentrant")
            h.orchestrator.record_for_call(handle, 1_000)
            reentry_ok.append(True)

        h = await build_harness(on_grant_moment=on_grant_moment)
        for n in range(5):
            handle = h.orchestrator.reserve_for_call(800_000, intent_id=f"c{n}")
            h.orchestrator.record_for_call(handle, 800_000)
        await h.emitter.drain()
        # If the seam deadlocked on the upstream lock, drain_once would hang;
        # reaching the assertion proves the off-thread dispatch contract holds.
        await h.dispatcher.drain_once()
        assert reentry_ok and all(reentry_ok)
