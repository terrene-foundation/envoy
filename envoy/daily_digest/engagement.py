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

    async def set_form_preference(self, principal_id: str, *, form: str) -> None:
        """Persist the user's explicit form choice after the fallback offer.

        Per spec § Low-engagement fallback: the low-engagement advisory OFFERS
        `compact` OR `event_only`; this records the user's selection (passing
        `rich` clears the downgrade). The selection overrides the automatic
        engagement-based choice in `select_form` — this is how `event_only`
        (event-driven delivery) becomes reachable.
        """
        await self._trust_store.digest_form_preference_set(principal_id, form=form)

    async def select_form(self, principal_id: str, *, now: datetime) -> str:
        """Return the digest form: explicit preference wins, else engagement-auto.

        1. **Explicit user preference** (`compact` / `event_only` / `rich`) set
           via `set_form_preference` after the low-engagement offer — honored
           verbatim. This is how `event_only` becomes reachable.
        2. **Engagement-auto**: fewer than `LOW_OPEN_THRESHOLD_PER_WEEK` opens
           per week across the trailing `LOW_ENGAGEMENT_WEEKS` window
           (2 × 3 = 6 opens in 21 days) → `compact`, emitting the
           `LowEngagementFallbackTriggered` advisory at INFO (NOT raised — the
           advisory structures the log; the form flip is the action).
        3. Otherwise `rich`.
        """
        preference = await self._trust_store.digest_form_preference_get(principal_id)
        if preference is not None:
            return preference

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
