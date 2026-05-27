# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.backfill — BackfillTracker.

Per `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
§ 3 step 5 + § 3.4 — per-channel last-successful-emission state. Bounds the
Ledger query window at 7 days to prevent unbounded growth on chronic-offline
principals; implements the EC-3 acceptance gate that skipped days surface in
the next-day digest as back-fill rather than being silently dropped.

Implements the `_BackfillProtocol` surface the `DailyDigestService` facade
depends on. Delegates persistence to `TrustStoreAdapter.digest_backfill_*`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from envoy.channels.envelope import SendReceipt
    from envoy.trust.store import TrustStoreAdapter

logger = logging.getLogger(__name__)


class BackfillTracker:
    """Per-(principal, channel) last-success state with a 7-day query horizon."""

    BACKFILL_HORIZON_DAYS: ClassVar[int] = 7

    def __init__(self, *, trust_store: TrustStoreAdapter) -> None:
        self._trust_store = trust_store

    async def query_window(
        self,
        *,
        principal_id: str,
        channel_id: str,
        scheduled_for: datetime,
    ) -> tuple[datetime, int]:
        """Return `(since, back_fill_days)` for the content-aggregation window.

        `since = max(last_success, scheduled_for - 7d)`. `back_fill_days` is the
        integer count of whole days between `last_success` and `scheduled_for`
        minus 1 (the normal same-day delivery contributes 0 back-fill days),
        clamped to `[0, 7]`. A principal with no prior success gets the full
        7-day horizon and `back_fill_days = 0` (first-ever digest is not a
        back-fill).
        """
        horizon_start = scheduled_for - timedelta(days=self.BACKFILL_HORIZON_DAYS)
        row = await self._trust_store.digest_backfill_get(principal_id, channel_id=channel_id)
        if row is None:
            # First-ever delivery — aggregate the full horizon, no back-fill.
            return (horizon_start, 0)

        last_success, _digest_id = row
        since = max(last_success, horizon_start)
        # Whole days missed since the last success (same-day = 0 back-fill).
        gap_days = (scheduled_for - last_success).days
        back_fill_days = max(0, min(gap_days - 1, self.BACKFILL_HORIZON_DAYS))
        logger.info(
            "daily_digest.backfill.window",
            extra={
                "principal_id_prefix": principal_id[:8],
                "channel_id": channel_id,
                "back_fill_days": back_fill_days,
            },
        )
        return (since, back_fill_days)

    async def record_success(
        self,
        *,
        principal_id: str,
        channel_id: str,
        receipt: SendReceipt,
        digest_id: str,
    ) -> None:
        """Record a successful delivery so the next window starts after it."""
        await self._trust_store.digest_backfill_set(
            principal_id,
            channel_id=channel_id,
            last_success=receipt.delivered_at,
            digest_id=digest_id,
        )
        logger.info(
            "daily_digest.backfill.recorded",
            extra={
                "principal_id_prefix": principal_id[:8],
                "channel_id": channel_id,
                "digest_id": digest_id,
            },
        )


__all__ = ["BackfillTracker"]
