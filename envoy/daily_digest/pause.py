# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.pause — PauseDisableState.

Per `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
§ 3 step 5 — Trust-store-backed pause state that survives process restart
(spec § Interaction line 25: "Reply 'skip digest': temporarily disable").

Implements the `_PauseProtocol` surface the `DailyDigestService` facade
depends on. Delegates persistence to `TrustStoreAdapter.digest_pause_*`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from envoy.trust.store import TrustStoreAdapter

logger = logging.getLogger(__name__)

_UTC = timezone.utc


class PauseDisableState:
    """Pause/resume persistence backed by the Trust store.

    Restart-safe: pause windows live in the digest-state SQLite region, so a
    `DailyDigestService.start()` after a restart reads the same pause state
    and skips re-registering paused principals.
    """

    DEFAULT_PAUSE_DAYS: ClassVar[int] = 7
    SKIP_TOO_LONG_THRESHOLD_DAYS: ClassVar[int] = 30

    def __init__(self, *, trust_store: TrustStoreAdapter) -> None:
        self._trust_store = trust_store

    async def pause(
        self,
        principal_id: str,
        *,
        duration_days: int = DEFAULT_PAUSE_DAYS,
        reason: str = "user_requested",
    ) -> None:
        """Persist a pause window of `duration_days` from now."""
        if duration_days <= 0:
            raise ValueError(f"duration_days must be positive (got {duration_days})")
        now = datetime.now(tz=_UTC)
        paused_until = now + timedelta(days=duration_days)
        await self._trust_store.digest_pause_set(
            principal_id, paused_until=paused_until, reason=reason
        )
        logger.info(
            "daily_digest.pause.set",
            extra={
                "principal_id_prefix": principal_id[:8],
                "duration_days": duration_days,
                "reason": reason,
            },
        )

    async def resume(self, principal_id: str) -> None:
        """Clear the pause window (no-op if not paused)."""
        await self._trust_store.digest_pause_clear(principal_id)
        logger.info(
            "daily_digest.pause.cleared",
            extra={"principal_id_prefix": principal_id[:8]},
        )

    async def is_paused(self, principal_id: str, *, now: datetime) -> bool:
        """True iff a pause window exists AND `now` is before `paused_until`.

        Expired windows return False — the pause auto-lifts at the end of
        `duration_days` without requiring an explicit `resume()`.
        """
        row = await self._trust_store.digest_pause_get(principal_id)
        if row is None:
            return False
        paused_until, _reason, _paused_at = row
        return now < paused_until

    async def is_skip_too_long(self, principal_id: str, *, now: datetime) -> bool:
        """True iff the pause has been active longer than the 30-day threshold.

        Per spec § Error taxonomy `DigestSkippedTooLongWarning` (L76): a
        skip-digest mode exceeding 30 days prompts re-engagement. Measured
        from `paused_at` (when the pause was set), not `paused_until`.
        """
        row = await self._trust_store.digest_pause_get(principal_id)
        if row is None:
            return False
        _paused_until, _reason, paused_at = row
        return (now - paused_at) > timedelta(days=self.SKIP_TOO_LONG_THRESHOLD_DAYS)


__all__ = ["PauseDisableState"]
