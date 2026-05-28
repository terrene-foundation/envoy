# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-8(b): no double-billing when the same intent_id crosses two channels.

Acceptance gate per `workspaces/phase-01-mvp/02-mvp-objectives.md` line 117 +
`workspaces/phase-01-mvp/02-plans/02-test-strategy.md` § EC-8 line 275:

> Per-channel non-double-billing test: a tool call that touches 2 channels
> (e.g., a Telegram-initiated send through Slack) charges Budget once, not twice.

Semantics (per `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md`
line 460): the shared session ``EnvoyBudgetOrchestrator`` reserves under one
``intent_id`` from the first channel; a sibling channel attempting to record
the SAME ``reservation_id`` raises ``ReservationDoubleRecordError`` via the
``_recorded_reservations`` guard.  The committed total reflects ONE charge.

Per `rules/testing.md` § Tier 2: real ``EnvoyBudgetOrchestrator`` + real
``EnvoyLedger`` over ``InMemoryAuditStore`` + real ``ThresholdDispatcher`` +
``LedgerEmitter``; NO mocking.  Per `rules/probe-driven-verification.md`
MUST-3: every assertion is structural (exception class + numeric equality +
Ledger row count).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from envoy.budget import ReservationDoubleRecordError
from tests.helpers.budget_harness import build_harness, no_op_anomaly_detector

_SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_UNTIL = datetime(2027, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
class TestNoDoubleBillingMultiChannel:
    """EC-8(b) — same intent_id crossing channels charges once."""

    async def test_sibling_channel_record_attempt_raises_double_record(self) -> None:
        """Telegram (channel A) reserves + records under intent_id=X; Slack
        (channel B) — handed the same ReservationHandle through the shared
        session orchestrator — MUST raise ReservationDoubleRecordError on its
        own record_for_call, naming the prior recording's first_recorded_at.
        """
        harness = await build_harness(
            principal_id="alice",
            session_id="session-cross-channel-1",
            anomaly_detector=no_op_anomaly_detector(),
        )

        # Channel A (Telegram) — reserve + record the intended cost.
        handle = harness.orchestrator.reserve_for_call(500_000, intent_id="intent-multi-channel-1")
        harness.orchestrator.record_for_call(handle, 480_000)

        # Channel B (Slack) — re-records the SAME reservation_id from a
        # sibling adapter. The shared orchestrator's _recorded_reservations
        # guard fires; the second charge never reaches the windows.
        with pytest.raises(ReservationDoubleRecordError) as excinfo:
            harness.orchestrator.record_for_call(handle, 480_000)

        # The structured error carries the reservation_id and the
        # first-recorded ISO timestamp so the runtime can surface a
        # cross-channel-confirm-failed receipt to the user.
        assert excinfo.value.reservation_id == handle.reservation_id
        assert excinfo.value.first_recorded_at  # ISO string, non-empty

    async def test_committed_total_reflects_single_charge_across_channels(
        self,
    ) -> None:
        """After Channel A records and Channel B's record-again raises,
        per_session.committed equals the SINGLE charge — never the double.
        """
        harness = await build_harness(
            principal_id="alice",
            session_id="session-cross-channel-2",
            anomaly_detector=no_op_anomaly_detector(),
        )

        handle = harness.orchestrator.reserve_for_call(500_000, intent_id="intent-multi-channel-2")
        harness.orchestrator.record_for_call(handle, 480_000)

        # Sibling-channel double-record attempt — guard raises; no charge.
        with pytest.raises(ReservationDoubleRecordError):
            harness.orchestrator.record_for_call(handle, 480_000)

        snap = harness.orchestrator.snapshot()
        assert snap.per_session.committed == 480_000, (
            "per_session.committed MUST reflect the single charge (480_000), "
            f"not double (960_000); got {snap.per_session.committed}"
        )
        assert snap.per_day.committed == 480_000, (
            "per_day.committed MUST reflect the single charge (480_000); "
            f"got {snap.per_day.committed}"
        )

    async def test_ledger_emits_exactly_one_budget_reservation_record(
        self,
    ) -> None:
        """The externally-observable outcome at the Ledger surface: exactly
        ONE ``budget_reservation_record`` row lands for the intent_id, not
        two, and the chain hash-verifies.
        """
        harness = await build_harness(
            principal_id="alice",
            session_id="session-cross-channel-3",
            anomaly_detector=no_op_anomaly_detector(),
        )

        handle = harness.orchestrator.reserve_for_call(500_000, intent_id="intent-multi-channel-3")
        harness.orchestrator.record_for_call(handle, 420_000)

        with pytest.raises(ReservationDoubleRecordError):
            harness.orchestrator.record_for_call(handle, 420_000)

        # Drain the LedgerEmitter to flush the async budget_reservation_record
        # write (the orchestrator records sync; emission is async per design).
        await harness.emitter.drain()

        entries = await harness.ledger.query(
            filter={"event_type": "budget_reservation_record"},
            since=_SINCE,
            until=_UNTIL,
        )
        # Exactly one row — the failed sibling-channel record never reached
        # the emitter because the guard raised before any window mutation.
        assert len(entries) == 1
        content = entries[0].content
        assert content["intent_id"] == "intent-multi-channel-3"
        assert content["reservation_id"] == handle.reservation_id
        assert content["actual_microdollars"] == 420_000

        # The whole Ledger chain hash-verifies — the failed second record
        # did not leave a torn entry.
        report = await harness.ledger.verify_chain()
        assert report.success is True

    async def test_two_intent_ids_in_same_session_charge_independently(
        self,
    ) -> None:
        """Sanity counter-example: two DISTINCT intent_ids in the same
        session DO accumulate (the dedup is by reservation_id, not by
        session_id).  This isolates the cross-channel guard from any
        unintended session-wide dedup.
        """
        harness = await build_harness(
            principal_id="alice",
            session_id="session-cross-channel-4",
            anomaly_detector=no_op_anomaly_detector(),
        )

        h1 = harness.orchestrator.reserve_for_call(300_000, intent_id="intent-A")
        harness.orchestrator.record_for_call(h1, 280_000)

        h2 = harness.orchestrator.reserve_for_call(300_000, intent_id="intent-B")
        harness.orchestrator.record_for_call(h2, 250_000)

        snap = harness.orchestrator.snapshot()
        assert snap.per_session.committed == 280_000 + 250_000
