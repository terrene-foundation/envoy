"""Tier 1 — T-04-82 — LowEngagementTracker (T-019) + BackfillTracker.

Source: T-04-82 per `workspaces/phase-01-mvp/todos/active/04-wave-4-channels-
digest.md` § T-04-82 + shard 11 § 3 steps 4-5.

Coverage — LowEngagementTracker:
1. select_form returns "rich" when opens >= threshold (2/week × 3 weeks = 6).
2. select_form returns "compact" below threshold (T-019 fallback).
3. Opens outside the 21-day window do NOT count toward the threshold.

Coverage — BackfillTracker:
4. First-ever delivery → full 7-day horizon, 0 back-fill days.
5. Recent same-day success → window starts at last_success, 0 back-fill.
6. Multi-day gap → back_fill_days reflects missed days, capped at horizon.

Real TrustStoreAdapter against on-disk SQLite (no mocks) — the window math
depends on real persisted timestamps.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from envoy.channels.envelope import SendReceipt
from envoy.daily_digest.backfill import BackfillTracker
from envoy.daily_digest.engagement import LowEngagementTracker
from envoy.trust.store import TrustStoreAdapter

_UTC = timezone.utc
_PID = "principal-engtest-01"
_NOW = datetime(2026, 5, 27, 8, 0, tzinfo=_UTC)


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "trust_vault.db"


async def _store(vault_path) -> TrustStoreAdapter:
    store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
    await store.initialize()
    return store


class TestLowEngagement:
    @pytest.mark.asyncio
    async def test_rich_when_engaged(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            tracker = LowEngagementTracker(trust_store=store)
            # 6 opens within the 21-day window == threshold → rich. Days 1..6×3
            # ago are all strictly inside [now-21d, now) (the window's `until`
            # is exclusive, so an open exactly at `now` would not count).
            for d in range(1, 7):
                await tracker.record_open(_PID, opened_at=_NOW - timedelta(days=d * 3))
            assert await tracker.select_form(_PID, now=_NOW) == "rich"
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_compact_when_low_engagement(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            tracker = LowEngagementTracker(trust_store=store)
            # Only 2 opens in the window — below the 6-open threshold → compact.
            await tracker.record_open(_PID, opened_at=_NOW - timedelta(days=1))
            await tracker.record_open(_PID, opened_at=_NOW - timedelta(days=5))
            assert await tracker.select_form(_PID, now=_NOW) == "compact"
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_opens_outside_window_excluded(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            tracker = LowEngagementTracker(trust_store=store)
            # 6 opens but all > 21 days ago — none count → compact (T-019).
            for d in range(6):
                await tracker.record_open(_PID, opened_at=_NOW - timedelta(days=30 + d))
            assert await tracker.select_form(_PID, now=_NOW) == "compact"
        finally:
            await store.close()


class TestBackfill:
    @pytest.mark.asyncio
    async def test_first_ever_full_horizon_no_backfill(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            tracker = BackfillTracker(trust_store=store)
            since, back_fill_days = await tracker.query_window(
                principal_id=_PID, channel_id="cli", scheduled_for=_NOW
            )
            assert since == _NOW - timedelta(days=7)
            assert back_fill_days == 0
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_recent_success_zero_backfill(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            tracker = BackfillTracker(trust_store=store)
            yesterday = _NOW - timedelta(days=1)
            receipt = SendReceipt(
                message_id="m1",
                delivered_at=yesterday,
                channel_native_id="n1",
            )
            await tracker.record_success(
                principal_id=_PID, channel_id="cli", receipt=receipt, digest_id="d1"
            )
            since, back_fill_days = await tracker.query_window(
                principal_id=_PID, channel_id="cli", scheduled_for=_NOW
            )
            assert since == yesterday  # window starts at last success
            assert back_fill_days == 0  # same-day cadence, no missed days
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_multiday_gap_backfill(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            tracker = BackfillTracker(trust_store=store)
            four_days_ago = _NOW - timedelta(days=4)
            receipt = SendReceipt(
                message_id="m1",
                delivered_at=four_days_ago,
                channel_native_id="n1",
            )
            await tracker.record_success(
                principal_id=_PID, channel_id="cli", receipt=receipt, digest_id="d1"
            )
            since, back_fill_days = await tracker.query_window(
                principal_id=_PID, channel_id="cli", scheduled_for=_NOW
            )
            assert since == four_days_ago
            # 4-day gap → 3 missed days back-filled (today is the normal delivery).
            assert back_fill_days == 3
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_backfill_capped_at_horizon(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            tracker = BackfillTracker(trust_store=store)
            long_ago = _NOW - timedelta(days=30)
            receipt = SendReceipt(
                message_id="m1",
                delivered_at=long_ago,
                channel_native_id="n1",
            )
            await tracker.record_success(
                principal_id=_PID, channel_id="cli", receipt=receipt, digest_id="d1"
            )
            since, back_fill_days = await tracker.query_window(
                principal_id=_PID, channel_id="cli", scheduled_for=_NOW
            )
            # since clamps to the 7-day horizon, not 30 days back; back_fill_days
            # is derived from the clamped window (7-day span → 6 back-filled
            # prior days + today), NOT the raw 30-day gap.
            assert since == _NOW - timedelta(days=7)
            assert back_fill_days == 6  # covered_days(7) - 1; consistent with window
        finally:
            await store.close()
