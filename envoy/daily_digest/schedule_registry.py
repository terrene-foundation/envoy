# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.schedule_registry — ScheduleRegistry.

Implements the `_ScheduleRegistryProtocol` surface the `DailyDigestService`
facade depends on: per-principal digest schedule (hour + timezone) plus the
active-channel binding (which channels receive the fan-out, and which is the
primary channel for duress-banner routing).

Backed by `TrustStoreAdapter.digest_schedule_*` + `digest_active_channels_*`.
Per shard 11 § 5.2, active-channel discovery happens at fire time (not cached
at scheduler-register time) so a channel connected after the schedule was set
still participates in the next fire.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from envoy.trust.store import TrustStoreAdapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScheduleRow:
    """Concrete `_ScheduleRow` — per-principal cron schedule.

    `hour` is 0-23 UTC (Phase-01 Option A); `timezone` is retained for the
    Phase-02 Option B (IANA) lift but is always "UTC" in Phase 01.
    """

    hour: int
    timezone: str


class ScheduleRegistry:
    """Trust-store-backed per-principal schedule + active-channel registry."""

    # Phase-01 default delivery hour when a principal has a schedule row absent
    # an explicit hour (spec § Schedule: "default 8am local" → 8 UTC under
    # Option A). Used only as the active-channels-without-schedule fallback.
    DEFAULT_HOUR_UTC: int = 8

    def __init__(self, *, trust_store: TrustStoreAdapter) -> None:
        self._trust_store = trust_store

    async def list_all(self) -> list[tuple[str, ScheduleRow]]:
        """Return `(principal_id, ScheduleRow)` for every persisted schedule."""
        rows = await self._trust_store.digest_schedule_list_all()
        return [(pid, ScheduleRow(hour=hour, timezone=tz)) for pid, hour, tz in rows]

    async def get(self, principal_id: str) -> ScheduleRow | None:
        """Return the principal's schedule, or None if unset."""
        row = await self._trust_store.digest_schedule_get(principal_id)
        if row is None:
            return None
        hour, tz = row
        return ScheduleRow(hour=hour, timezone=tz)

    async def set(self, principal_id: str, *, hour: int, timezone: str) -> None:
        """Persist/update the principal's schedule."""
        await self._trust_store.digest_schedule_set(principal_id, hour=hour, timezone=timezone)

    async def active_channels(self, principal_id: str) -> tuple[str, ...]:
        """Return the principal's active channel ids (empty if none bound)."""
        row = await self._trust_store.digest_active_channels_get(principal_id)
        if row is None:
            return ()
        active, _primary = row
        return tuple(active)

    async def primary_channel(self, principal_id: str) -> str:
        """Return the principal's primary channel id.

        Raises `ValueError` when no active-channel binding exists — the
        primary channel is required for duress-banner routing (spec
        § DuressBannerSuppressedError) and back-fill window computation, so a
        missing binding is a fail-loud condition, not a silent default.
        """
        row = await self._trust_store.digest_active_channels_get(principal_id)
        if row is None:
            raise ValueError(
                f"no active-channel binding for principal {principal_id[:8]!r}; "
                "call set_active_channels() before scheduling the digest",
            )
        _active, primary = row
        return primary

    async def set_active_channels(
        self, principal_id: str, *, channel_ids: list[str], primary: str
    ) -> None:
        """Bind the principal's active channels + primary channel."""
        await self._trust_store.digest_active_channels_set(
            principal_id, channel_ids=channel_ids, primary=primary
        )


__all__ = ["ScheduleRow", "ScheduleRegistry"]
