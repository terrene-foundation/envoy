# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.duress — DuressBannerReader.

Per `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
§ 3 step 6 + `specs/daily-digest.md` § Shadow-segment post-duress surface
(V2 C-02 fix, lines 35-37) + § Error taxonomy `DuressBannerSuppressedError`
(L73, T-018 defense).

Reads the local-only shadow segment via
`TrustStoreAdapter.shadow_segment_unread_duress_events` and routes the duress
banner to the PRIMARY CHANNEL ONLY. A non-primary channel never sees the
banner (T-018: an attacker who compromised a secondary channel must not learn
that a duress event was recorded).

Phase-01 status: `shadow_segment_unread_duress_events` returns `[]` (no
duress-detection mechanism is wired until Phase 02 — see its docstring). The
primary-channel gate logic is fully implemented and tested; it stays inert
(present=False) until the shadow segment populates in Phase 02+.

Implements the `_DuressReaderProtocol` surface the `DailyDigestService` facade
depends on.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from envoy.daily_digest.payload import DuressBanner

if TYPE_CHECKING:
    from envoy.daily_digest.schedule_registry import ScheduleRegistry
    from envoy.trust.store import TrustStoreAdapter

logger = logging.getLogger(__name__)


class DuressBannerReader:
    """Primary-channel-only duress banner gate over the local shadow segment."""

    def __init__(
        self,
        *,
        trust_store: TrustStoreAdapter,
        schedule_registry: ScheduleRegistry,
    ) -> None:
        self._trust_store = trust_store
        self._schedule_registry = schedule_registry

    async def check(
        self,
        *,
        principal_id: str,
        channel_id: str,
        since: datetime,
    ) -> DuressBanner:
        """Return a `DuressBanner` for `channel_id`.

        `present=True` ONLY when (a) an unread duress event exists in the
        shadow segment AND (b) `channel_id` is the principal's primary
        channel. Any non-primary channel — or no unread event — yields
        `present=False` (T-018 defense: the banner is invisible on secondary
        channels regardless of the shadow-segment state).

        `since` is accepted for the Phase-02 windowed read; the Phase-01
        shadow-segment read returns all unread events (it returns `[]`).
        """
        del since  # Phase-02 windowing hook; unused in the Phase-01 read.

        events = await self._trust_store.shadow_segment_unread_duress_events(principal_id)
        if not events:
            return DuressBanner(present=False, shadow_event_ref=None)

        # Unread duress event(s) exist — gate on primary-channel match.
        try:
            primary = await self._schedule_registry.primary_channel(principal_id)
        except ValueError:
            # No channel binding — cannot determine primary; fail safe to
            # no-banner (the banner has no authorized surface to render on).
            logger.warning(
                "daily_digest.duress.no_primary_channel",
                extra={"principal_id_prefix": principal_id[:8]},
            )
            return DuressBanner(present=False, shadow_event_ref=None)

        if channel_id != primary:
            # T-018: non-primary channel never sees the banner.
            logger.info(
                "daily_digest.duress.suppressed_non_primary",
                extra={
                    "principal_id_prefix": principal_id[:8],
                    "channel_id": channel_id,
                },
            )
            return DuressBanner(present=False, shadow_event_ref=None)

        # Primary channel + unread event → render the banner. The shadow
        # event ref is redaction-safe (it is a ledger-entry id, not the
        # duress content).
        shadow_event_ref = _extract_event_ref(events[0])
        logger.info(
            "daily_digest.duress.banner_rendered",
            extra={"principal_id_prefix": principal_id[:8]},
        )
        return DuressBanner(present=True, shadow_event_ref=shadow_event_ref)


def _extract_event_ref(event: object) -> str | None:
    """Pull a ledger-entry ref out of a shadow-segment event record.

    Phase 02 fixes the event record shape; Phase 01 accepts either a dict
    with an `id`/`ledger_id` key or an object with that attribute, falling
    back to `str(event)` so the banner always carries a non-None ref when an
    event exists.
    """
    if isinstance(event, dict):
        return event.get("ledger_id") or event.get("id") or str(event)
    for attr in ("ledger_id", "id"):
        if hasattr(event, attr):
            return str(getattr(event, attr))
    return str(event)


__all__ = ["DuressBannerReader"]
