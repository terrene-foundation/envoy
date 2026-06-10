# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.service — DailyDigestService facade.

Per `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
§ 3 step 1 — the facade is the single public surface for Wave 4 Daily Digest.
Every CLI subcommand (`envoy digest today / pause / resume / schedule`)
routes through this class; per `rules/orphan-detection.md` Rule 1, the CLI
(landing in T-04-83 within this same PR) is the hot-path production call
site.

Per `rules/facade-manager-detection.md` Rule 3: every dependency is injected
explicitly through the constructor; no global lookups, no self-construction
of collaborators. Protocols pin the dependency contracts so T-04-81 / T-04-82
can land concrete classes in parallel without rewriting this facade.

Per `rules/agents.md` Specialist Delegation: this facade is consumed by
nexus-bound CLI subcommands but does NOT itself open channels. Channel
fan-out lives in `PerChannelFanout` (T-04-82), wrapped behind the
`_FanoutProtocol` below.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

from envoy.daily_digest.errors import (
    DigestDeliveryFailedError,
    DigestSkippedTooLongWarning,
    LowEngagementFallbackTriggered,
)
from envoy.daily_digest.payload import DigestForm, DigestPayload
from envoy.daily_digest.scheduler import DigestScheduler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency protocols
# ---------------------------------------------------------------------------
# Each protocol below pins the surface the facade depends on. Concrete
# implementations land in T-04-81 (aggregator + renderer) and T-04-82
# (fanout + backfill + pause + low_engagement). Protocols let those shards
# proceed in parallel worktrees without coordinating on the facade signature.


class _AggregatorProtocol(Protocol):
    """Surface implemented by `LedgerAggregator` (T-04-81)."""

    async def aggregate(
        self,
        *,
        principal_id: str,
        since: datetime,
        until: datetime,
    ) -> Any: ...


class _RendererProtocol(Protocol):
    """Surface implemented by `DigestRenderer` (T-04-81)."""

    async def render(
        self,
        *,
        principal_id: str,
        channel_id: str,
        summary: Any,
        duress_banner: Any,
        form: DigestForm,
        scheduled_for: datetime,
        back_fill_days: int,
    ) -> DigestPayload: ...


class _FanoutProtocol(Protocol):
    """Surface implemented by `PerChannelFanout` (T-04-82)."""

    async def emit(
        self,
        *,
        principal_id: str,
        payload: DigestPayload,
        active_channel_ids: list[str],
        timeout_seconds: int = 10,
    ) -> dict[str, Any]: ...


class _BackfillProtocol(Protocol):
    """Surface implemented by `BackfillTracker` (T-04-82)."""

    async def query_window(
        self,
        *,
        principal_id: str,
        channel_id: str,
        scheduled_for: datetime,
    ) -> tuple[datetime, int]: ...

    async def record_success(
        self,
        *,
        principal_id: str,
        channel_id: str,
        receipt: Any,
        digest_id: str,
    ) -> None: ...


class _PauseProtocol(Protocol):
    """Surface implemented by `PauseDisableState` (T-04-82)."""

    async def is_paused(self, principal_id: str, *, now: datetime) -> bool: ...

    async def is_skip_too_long(
        self,
        principal_id: str,
        *,
        now: datetime,
    ) -> bool: ...

    async def pause(
        self,
        principal_id: str,
        *,
        duration_days: int = 7,
        reason: str = "user_requested",
    ) -> None: ...

    async def resume(self, principal_id: str) -> None: ...


class _LowEngagementProtocol(Protocol):
    """Surface implemented by `LowEngagementTracker` (T-04-82)."""

    async def select_form(
        self,
        principal_id: str,
        *,
        now: datetime,
    ) -> DigestForm: ...

    async def record_open(self, principal_id: str, *, opened_at: datetime) -> None: ...

    async def set_form_preference(self, principal_id: str, *, form: str) -> None: ...


class _DuressReaderProtocol(Protocol):
    """Surface implemented by `DuressBannerReader` (T-04-83)."""

    async def check(
        self,
        *,
        principal_id: str,
        channel_id: str,
        since: datetime,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# Service facade
# ---------------------------------------------------------------------------


class DailyDigestService:
    """Daily Digest facade — owns scheduler lifecycle + per-principal dispatch.

    Per `rules/orphan-detection.md` Rule 1, every public attribute below has
    or will have a hot-path call site within ≤5 commits (the CLI lands in
    T-04-83; Tier-2 wiring in T-04-84 — same PR).

    Per spec § Interaction (lines 22-25): CLI reply parsing belongs to the
    inbound channel adapter (per channel-adapters.md § Adapter contract),
    not to this facade. This facade is the producer + scheduler; consumption
    is the adapter's job.
    """

    def __init__(
        self,
        *,
        scheduler: DigestScheduler,
        aggregator: _AggregatorProtocol,
        renderer: _RendererProtocol,
        fanout: _FanoutProtocol,
        backfill: _BackfillProtocol,
        pause_state: _PauseProtocol,
        low_engagement: _LowEngagementProtocol,
        duress_reader: _DuressReaderProtocol,
        schedule_registry: _ScheduleRegistryProtocol,
    ) -> None:
        self._scheduler = scheduler
        self._aggregator = aggregator
        self._renderer = renderer
        self._fanout = fanout
        self._backfill = backfill
        self._pause_state = pause_state
        self._low_engagement = low_engagement
        self._duress_reader = duress_reader
        self._schedule_registry = schedule_registry
        self._started: bool = False

    # ---- Lifecycle ------------------------------------------------------

    async def start(self) -> None:
        """Initialize scheduler and re-register every persisted schedule.

        Restart-safe per scheduler Invariant 2: paused principals are NOT
        registered (`PauseDisableState.is_paused()` checked); the user's
        next explicit `resume()` re-registers them.

        Idempotent: calling twice is a no-op.
        """
        if self._started:
            return

        # Start the scheduler attachment to the event loop FIRST so the
        # subsequent register() calls run against a live scheduler.
        await self._scheduler.start()

        now = _utc_now()
        registered = 0
        skipped_paused = 0
        for principal_id, schedule in await self._schedule_registry.list_all():
            if await self._pause_state.is_paused(principal_id, now=now):
                skipped_paused += 1
                continue
            await self._scheduler.register(
                principal_id,
                hour=schedule.hour,
                timezone=schedule.timezone,
                callback=self._fire,
            )
            registered += 1

        self._started = True
        logger.info(
            "daily_digest.service.started",
            extra={
                "registered_count": registered,
                "skipped_paused_count": skipped_paused,
            },
        )

    async def stop(self, *, drain_timeout_seconds: int = 5) -> None:
        """Stop the scheduler, draining in-flight digests up to the timeout.

        Idempotent — calling on an unstarted service is a no-op.
        """
        if not self._started:
            return
        await self._scheduler.stop(drain_timeout_seconds=drain_timeout_seconds)
        self._started = False
        logger.info("daily_digest.service.stopped")

    @property
    def started(self) -> bool:
        return self._started

    # ---- User-facing commands ------------------------------------------

    async def schedule(
        self,
        principal_id: str,
        *,
        hour: int,
        timezone: str = "UTC",
    ) -> None:
        """Set or update the principal's daily digest schedule.

        Persists the schedule to the Trust-store-backed registry AND, if the
        principal is not paused, registers the cron job immediately. Per
        scheduler Invariant 1, an existing job for the same principal is
        replaced atomically.
        """
        await self._schedule_registry.set(principal_id, hour=hour, timezone=timezone)
        now = _utc_now()
        if not await self._pause_state.is_paused(principal_id, now=now):
            await self._scheduler.register(
                principal_id,
                hour=hour,
                timezone=timezone,
                callback=self._fire,
            )

    async def pause(
        self,
        principal_id: str,
        *,
        duration_days: int = 7,
        reason: str = "user_requested",
    ) -> None:
        """Pause the principal's digest for `duration_days` (default 7).

        Per spec § Interaction line 25 ("Reply 'skip digest': temporarily
        disable"). Removes the active cron job; resume is via `resume()` OR
        automatic via `is_paused()` time-out at the end of `duration_days`.
        """
        await self._pause_state.pause(
            principal_id,
            duration_days=duration_days,
            reason=reason,
        )
        await self._scheduler.unregister(principal_id)

    async def set_form_preference(self, principal_id: str, *, form: str) -> None:
        """Persist the user's explicit digest-form choice (spec § Low-engagement).

        The low-engagement advisory OFFERS `compact` OR `event_only`; this is
        the WRITE half — the user records their choice and the next digest
        honors it verbatim (overriding the engagement-auto form). Passing
        `rich` clears the downgrade.

        Routed to the underlying `LowEngagementTracker` so the
        `select_form`-honored preference is updated atomically.
        """
        await self._low_engagement.set_form_preference(principal_id, form=form)

    async def resume(self, principal_id: str) -> None:
        """End pause early and re-register the digest schedule.

        If no schedule was previously set (`schedule_registry.get()` returns
        None), `resume()` is a no-op on the scheduler — the user must call
        `schedule()` first.
        """
        await self._pause_state.resume(principal_id)
        schedule = await self._schedule_registry.get(principal_id)
        if schedule is None:
            return
        await self._scheduler.register(
            principal_id,
            hour=schedule.hour,
            timezone=schedule.timezone,
            callback=self._fire,
        )

    async def trigger_now(self, principal_id: str) -> DigestPayload:
        """Run the aggregate → render → fan-out pipeline immediately.

        CLI hook for `envoy digest today`. Bypasses cron AND pause-state
        (the user explicitly asked). Returns the rendered payload for CLI
        display. Running `today` IS the user opening the digest, so it records
        an engagement open (the scheduled push in `_fire` does NOT — the system
        sent it; the user has not necessarily opened it).
        """
        now = _utc_now()
        payload = await self._run_pipeline(principal_id, scheduled_for=now, event_gated=False)
        await self._low_engagement.record_open(principal_id, opened_at=now)
        return payload

    # ---- Internal pipeline ---------------------------------------------

    async def _fire(self, principal_id: str) -> None:
        """Scheduler callback. Invoked by apscheduler at the user's cron hour."""
        now = _utc_now()

        # Pause-state check at fire time covers the race between user pause()
        # and an already-queued apscheduler tick. The scheduler `coalesce=True`
        # collapses queued ticks but does not retroactively cancel pre-pause
        # firings.
        if await self._pause_state.is_paused(principal_id, now=now):
            logger.info(
                "daily_digest.service.fire_skipped_paused",
                extra={"principal_id_prefix": principal_id[:8]},
            )
            # Skip-too-long advisory surfaces here so the next un-pause cycle
            # picks up the warning per spec § Error taxonomy `DigestSkippedTooLongWarning`.
            if await self._pause_state.is_skip_too_long(principal_id, now=now):
                logger.warning(
                    "daily_digest.service.skip_too_long",
                    extra={
                        "principal_id_prefix": principal_id[:8],
                        "error": DigestSkippedTooLongWarning.__name__,
                    },
                )
            return

        try:
            await self._run_pipeline(principal_id, scheduled_for=now, event_gated=True)
        except DigestDeliveryFailedError:
            # Per spec § Error taxonomy L72: retry auto next morning.
            # The error is logged at WARN in PerChannelFanout; here the
            # facade swallows so apscheduler does not raise out of the
            # event loop (which would drop the job).
            logger.warning(
                "daily_digest.service.delivery_failed",
                extra={"principal_id_prefix": principal_id[:8]},
            )
        except LowEngagementFallbackTriggered:
            # Advisory — already logged by LowEngagementTracker. Re-raise
            # would drop the apscheduler job; swallow here.
            logger.info(
                "daily_digest.service.low_engagement_advisory_observed",
                extra={"principal_id_prefix": principal_id[:8]},
            )

    async def _run_pipeline(
        self,
        principal_id: str,
        *,
        scheduled_for: datetime,
        event_gated: bool = True,
    ) -> DigestPayload:
        """The aggregate → render → fan-out happy path.

        Single function so `trigger_now()` and `_fire()` share identical
        sequencing — drift between the CLI path and the cron path is the
        failure mode this collapse prevents.

        `event_gated` (True on scheduled `_fire`, False on manual
        `trigger_now`): when the selected form is `event_only` (spec
        § Low-engagement fallback — "event-driven-only delivery (fires on Grant
        Moment pending or budget > 80%)"), a scheduled fire delivers ONLY when
        there is a pending Grant Moment OR spend has crossed 80% of the monthly
        ceiling. A manual `today` always delivers (the user explicitly asked).

        On every successful per-channel delivery, `BackfillTracker.record_success`
        advances the last-success watermark so the next fire's back-fill window
        starts after this delivery (the EC-3 carry-over contract).
        """
        # 1. Engagement form selection (rich / compact / event_only).
        form = await self._low_engagement.select_form(
            principal_id,
            now=scheduled_for,
        )

        # 2. Determine active channels + the per-channel back-fill window.
        active_channels = await self._schedule_registry.active_channels(
            principal_id,
        )
        primary_channel = await self._schedule_registry.primary_channel(
            principal_id,
        )
        # Use the primary channel's back-fill window as the canonical content
        # window — spec § Schedule says delivery is "user-chosen channel";
        # back-fill state per channel ensures missed days surface but the
        # aggregated content is single per principal/day.
        since, back_fill_days = await self._backfill.query_window(
            principal_id=principal_id,
            channel_id=primary_channel,
            scheduled_for=scheduled_for,
        )

        # 3. Aggregate ledger entries (T-04-81).
        summary = await self._aggregator.aggregate(
            principal_id=principal_id,
            since=since,
            until=scheduled_for,
        )

        # 4. Duress banner — primary-channel-only per spec § DuressBannerSuppressedError.
        duress_banner = await self._duress_reader.check(
            principal_id=principal_id,
            channel_id=primary_channel,
            since=since,
        )

        # 5. Render canonical payload.
        payload = await self._renderer.render(
            principal_id=principal_id,
            channel_id=primary_channel,
            summary=summary,
            duress_banner=duress_banner,
            form=form,
            scheduled_for=scheduled_for,
            back_fill_days=back_fill_days,
        )

        # 5a. event_only gate: a scheduled fire for an event_only principal
        # delivers ONLY when there's something event-worthy (pending Grant
        # Moment OR spend > 80% of ceiling) per spec § Low-engagement fallback.
        # A manual `today` (event_gated=False) always delivers.
        if event_gated and form == "event_only" and not _has_event(summary):
            logger.info(
                "daily_digest.service.event_only_skipped_no_event",
                extra={"principal_id_prefix": principal_id[:8]},
            )
            return payload

        # 6. Fan out across active channels.
        outcome = await self._fanout.emit(
            principal_id=principal_id,
            payload=payload,
            active_channel_ids=list(active_channels),
        )

        # 6a. Advance the per-channel back-fill watermark for each successful
        # delivery so the next fire's window starts after it (EC-3 carry-over).
        for channel_id, result in outcome.items():
            if not isinstance(result, BaseException):
                await self._backfill.record_success(
                    principal_id=principal_id,
                    channel_id=channel_id,
                    receipt=result,
                    digest_id=payload.digest_id,
                )

        return payload


# ---------------------------------------------------------------------------
# Schedule registry protocol — implemented in T-04-82 alongside PauseDisableState
# ---------------------------------------------------------------------------


class _ScheduleRow(Protocol):
    @property
    def hour(self) -> int: ...
    @property
    def timezone(self) -> str: ...


class _ScheduleRegistryProtocol(Protocol):
    """Trust-store-backed per-principal digest schedule + channel binding."""

    async def list_all(self) -> Sequence[tuple[str, _ScheduleRow]]: ...

    async def get(self, principal_id: str) -> _ScheduleRow | None: ...

    async def set(
        self,
        principal_id: str,
        *,
        hour: int,
        timezone: str,
    ) -> None: ...

    async def active_channels(self, principal_id: str) -> tuple[str, ...]: ...

    async def primary_channel(self, principal_id: str) -> str: ...


# ---------------------------------------------------------------------------
# Internal utility
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    """Single seam for now() so test fixtures can monkeypatch deterministically.

    Per `rules/testing.md` § "Tests MUST be deterministic": tests use
    `freezegun.freeze_time` to control this; production reads the wall
    clock via `datetime.now(timezone.utc)`.
    """
    return datetime.now(timezone.utc)


# Spend-ratio threshold above which an event_only digest fires anyway, per
# spec § Low-engagement fallback ("fires on Grant Moment pending or budget > 80%").
_EVENT_ONLY_BUDGET_RATIO = 0.8


def _has_event(summary: Any) -> bool:
    """True iff the digest carries something event-worthy for event_only delivery.

    Per spec § Low-engagement fallback, an event_only digest fires when there's
    a pending Grant Moment OR spend has crossed 80% of the monthly ceiling.
    """
    if getattr(summary, "pending_grants", ()):
        return True
    spend = getattr(summary, "spend", {}) or {}
    ceiling = spend.get("monthly_ceiling_microdollars", 0)
    current = spend.get("current_microdollars", 0)
    return bool(ceiling > 0 and current / ceiling > _EVENT_ONLY_BUDGET_RATIO)


__all__ = [
    "DailyDigestService",
]
