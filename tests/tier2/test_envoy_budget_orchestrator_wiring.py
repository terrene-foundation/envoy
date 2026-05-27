# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — EnvoyBudgetOrchestrator end-to-end against real Ledger.

Per `rules/orphan-detection.md` Rule 1/2 + `rules/facade-manager-detection.md`
Rule 1: the manager-shape facade (`EnvoyBudgetOrchestrator`) MUST have a Tier-2
test that exercises the production path against real infrastructure (real
`EnvoyLedger` + `LedgerEmitter`) and asserts the externally-observable effect
(a `budget_reservation_record` Ledger entry that is hash-chain-verifiable).

Design § 6.1 test 1. NO mocking per `rules/testing.md` Tier 2.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.helpers.budget_harness import build_harness

_SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_UNTIL = datetime(2027, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
class TestOrchestratorLedgerWiring:
    async def test_reserve_record_emits_verifiable_reservation_record(self) -> None:
        h = await build_harness()
        handle = h.orchestrator.reserve_for_call(500_000, intent_id="intent-1")
        h.orchestrator.record_for_call(handle, 420_000)
        entry_ids = await h.emitter.drain()

        # External observable: exactly one budget_reservation_record landed.
        assert len(entry_ids) == 1
        entries = await h.ledger.query(filter={}, since=_SINCE, until=_UNTIL)
        records = [e for e in entries if e.type == "budget_reservation_record"]
        assert len(records) == 1
        content = records[0].content
        assert content["intent_id"] == "intent-1"
        assert content["reserved_microdollars"] == 500_000
        assert content["actual_microdollars"] == 420_000
        assert content["reservation_id"] == handle.reservation_id

        # The whole chain (including the budget entry) hash-verifies.
        report = await h.ledger.verify_chain()
        assert report.success is True
        assert report.entries_verified == 1

    async def test_actual_committed_reflected_in_snapshot(self) -> None:
        h = await build_harness()
        handle = h.orchestrator.reserve_for_call(800_000, intent_id="intent-2")
        h.orchestrator.record_for_call(handle, 650_000)
        snap = h.orchestrator.snapshot()
        # The actual (not the reserved estimate) is committed to every window.
        assert snap.per_session.committed == 650_000
        assert snap.per_day.committed == 650_000

    async def test_runtime_adapter_drives_the_same_path(self) -> None:
        # The runtime-abstraction surface (the production hot path the Kaizen
        # interceptor calls) reaches the same orchestrator.
        from tests.helpers.budget_harness import runtime_adapter

        h = await build_harness()
        adapter = runtime_adapter(h.orchestrator)
        reservation_id = adapter.budget_reserve("session-1", 300_000)
        adapter.budget_record(reservation_id, 250_000)
        await h.emitter.drain()
        entries = await h.ledger.query(filter={}, since=_SINCE, until=_UNTIL)
        records = [e for e in entries if e.type == "budget_reservation_record"]
        assert len(records) == 1
        assert records[0].content["actual_microdollars"] == 250_000
