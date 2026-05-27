# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.engagement — LowEngagementTracker.

Per `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
§ 3 step 5 + `specs/daily-digest.md` § Low-engagement fallback (line 29) —
"<2 Digest opens/week for 3 weeks → offer 3-line compact form or event-driven-
only delivery". T-019 habituation defense.

Implements the `_LowEngagementProtocol` surface the `DailyDigestService`
facade depends on. Delegates persistence to
`TrustStoreAdapter.digest_engagement_*`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from envoy.trust.store import TrustStoreAdapter

logger = logging.getLogger(__name__)


class LowEngagementTracker:
    """Rolling 3-week opens-per-week tracker driving the form downgrade.

    T-019 defense: a user who stops engaging with the digest gets a quieter
    form (compact) rather than the full rich digest, reducing habituation /
    notification fatigue. The threshold is per spec § Low-engagement fallback.
    """

    LOW_OPEN_THRESHOLD_PER_WEEK: ClassVar[int] = 2
    LOW_ENGAGEMENT_WEEKS: ClassVar[int] = 3

    def __init__(self, *, trust_store: TrustStoreAdapter) -> None:
        self._trust_store = trust_store

    async def record_open(self, principal_id: str, *, opened_at: datetime) -> None:
        """Record a digest-open event."""
        await self._trust_store.digest_engagement_record_open(principal_id, opened_at=opened_at)

    async def select_form(self, principal_id: str, *, now: datetime) -> str:
        """Return "rich" normally; "compact" when engagement is low.

        Low engagement = fewer than `LOW_OPEN_THRESHOLD_PER_WEEK` opens per
        week sustained across the trailing `LOW_ENGAGEMENT_WEEKS` window
        (total threshold = 2 × 3 = 6 opens in 21 days). When the threshold is
        not met, emit the `LowEngagementFallbackTriggered` advisory at INFO
        (NOT raised — the advisory class structures the log; the form flip is
        the action) and return "compact".
        """
        window_days = self.LOW_ENGAGEMENT_WEEKS * 7
        since = now - timedelta(days=window_days)
        opens = await self._trust_store.digest_engagement_opens_in_window(
            principal_id, since=since, until=now
        )
        threshold = self.LOW_OPEN_THRESHOLD_PER_WEEK * self.LOW_ENGAGEMENT_WEEKS
        if opens < threshold:
            logger.info(
                "daily_digest.engagement.low_engagement_fallback_triggered",
                extra={
                    "principal_id_prefix": principal_id[:8],
                    "opens_in_window": opens,
                    "threshold": threshold,
                    "window_days": window_days,
                    "selected_form": "compact",
                },
            )
            return "compact"
        return "rich"


__all__ = ["LowEngagementTracker"]
