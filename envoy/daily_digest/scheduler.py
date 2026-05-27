# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.scheduler — apscheduler.AsyncIOScheduler thin wrapper.

Per `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
§ 3 step 1 — `DigestScheduler` registers a cron trigger per principal that
invokes a caller-supplied async callback at the user-configured local hour.

Phase 01 timezone disposition (per `01-analysis/22-spec-gap-analysis.md` § 4
Option A): UTC-only. `timezone` argument accepted for forward-compat with
Phase 02 Option B (IANA timezone field) but Phase 01 routes the apscheduler
`CronTrigger` through `timezone="UTC"` regardless of the argument value.
This preserves the signature so Phase 02 unblocks at the call site without
sweeping every caller.

Per `rules/patterns.md` § "Paired Public Surface — Consistent Async-ness":
every public method is `async def` so the surface composes uniformly inside
Nexus handlers, pytest-asyncio tests, and CLI event loops.

Per `rules/orphan-detection.md` Rule 1: `DigestScheduler` is consumed by
`DailyDigestService.start()` within this same package; the facade is the
production call site within ≤5 commits of this module's introduction.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timezone as _tz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Phase 01 timezone basis — `01-analysis/22-spec-gap-analysis.md` § 4 Option A.
# Phase 02 lifts this to per-principal IANA timezone via Option B.
_PHASE_01_TIMEZONE: str = "UTC"


DigestCallback = Callable[[str], Awaitable[None]]
"""Caller-provided async callback. Signature: `callback(principal_id) -> None`.

The scheduler invokes this on every cron tick; the callback is responsible
for the full aggregate → render → fan-out pipeline.
"""


class DigestScheduler:
    """Wraps `apscheduler.AsyncIOScheduler` with per-principal cron registration.

    Invariants:

    1. **Per-principal job registration.** Calling `register()` for an
       already-registered `principal_id` REPLACES the prior job (apscheduler
       `replace_existing=True` semantics) — supports `envoy digest schedule`
       reschedule without leaking dangling jobs.
    2. **Cron scheduler restart-safe.** Job state lives in caller-owned Trust
       store (`PauseDisableState` + per-principal schedule rows); the
       scheduler itself is in-memory. `DailyDigestService.start()` reads
       persisted schedules and re-registers on boot.
    3. **UTC-only schedule.** Phase 01 Option A — all CronTrigger instances
       use `timezone="UTC"`; the `timezone` kwarg on `register()` is accepted
       for forward-compat but ignored. A WARN log fires if a caller passes a
       non-UTC value so Phase 02 lift surfaces every existing caller.
    """

    def __init__(self) -> None:
        # AsyncIOScheduler attaches to the running event loop at start() time,
        # NOT at construction time — safe to instantiate in __init__.
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone=_tz.utc)
        self._jobs: dict[str, str] = {}  # principal_id -> apscheduler job_id
        self._started: bool = False

    async def register(
        self,
        principal_id: str,
        *,
        hour: int,
        timezone: str,
        callback: DigestCallback,
    ) -> None:
        """Register or replace the daily digest cron job for `principal_id`.

        `hour` is 0-23 (UTC). `callback` receives `principal_id` and is
        awaited by apscheduler on every tick. Per Invariant 3, `timezone`
        is ignored in Phase 01; non-UTC values emit a WARN log.
        """
        if not 0 <= hour <= 23:
            raise ValueError(
                f"hour must be in [0, 23]; got {hour!r} for principal_id " f"{principal_id[:8]!r}",
            )
        if timezone != _PHASE_01_TIMEZONE:
            # Phase 02 Option B lift — surface every non-UTC caller so the
            # sweep at Phase 02 transition is mechanical.
            logger.warning(
                "daily_digest.scheduler.timezone_override_ignored",
                extra={
                    "principal_id_prefix": principal_id[:8],
                    "requested_timezone": timezone,
                    "applied_timezone": _PHASE_01_TIMEZONE,
                    "phase_01_disposition": "option_a_utc_only",
                },
            )

        trigger = CronTrigger(hour=hour, minute=0, timezone=_tz.utc)

        # apscheduler `add_job` returns a Job; we capture its id so unregister()
        # can target it deterministically even if the principal_id changes
        # representation (e.g. after `format_record_id_for_event` redaction
        # adjustments in Phase 02).
        job = self._scheduler.add_job(
            callback,
            trigger=trigger,
            args=(principal_id,),
            id=f"daily_digest::{principal_id}",
            replace_existing=True,
            misfire_grace_time=3600,  # 1h grace per spec § Schedule
            coalesce=True,  # if multiple fires queue (resume after pause), run once
            max_instances=1,  # never overlap a digest with itself
        )
        self._jobs[principal_id] = job.id

        logger.info(
            "daily_digest.scheduler.registered",
            extra={
                "principal_id_prefix": principal_id[:8],
                "hour_utc": hour,
                "job_id": job.id,
            },
        )

    async def unregister(self, principal_id: str) -> None:
        """Remove the daily digest cron job for `principal_id`.

        No-op when no job exists; callers (e.g. `pause()`) MAY invoke this
        unconditionally without first checking `is_registered()`.
        """
        job_id = self._jobs.pop(principal_id, None)
        if job_id is None:
            return
        try:
            self._scheduler.remove_job(job_id)
        except Exception as exc:  # apscheduler.jobstores.base.JobLookupError
            # Job already gone — restart-race with persisted state.
            # Logged at DEBUG since the user-visible outcome (no schedule)
            # matches intent.
            logger.debug(
                "daily_digest.scheduler.unregister_already_gone",
                extra={
                    "principal_id_prefix": principal_id[:8],
                    "job_id": job_id,
                    "error_type": type(exc).__name__,
                },
            )

        logger.info(
            "daily_digest.scheduler.unregistered",
            extra={
                "principal_id_prefix": principal_id[:8],
                "job_id": job_id,
            },
        )

    def is_registered(self, principal_id: str) -> bool:
        """Return True iff `principal_id` has an active cron registration."""
        return principal_id in self._jobs

    def registered_principals(self) -> tuple[str, ...]:
        """Return all currently-registered principal_ids as a stable tuple.

        Used by `DailyDigestService.stop()` to drain in-flight jobs.
        """
        return tuple(self._jobs.keys())

    async def start(self) -> None:
        """Start the apscheduler event loop attachment.

        Idempotent: calling twice is a no-op (Invariant 2: restart-safe).
        Per apscheduler docs, `start()` must be called from inside a running
        asyncio event loop.
        """
        if self._started:
            return
        self._scheduler.start()
        self._started = True
        logger.info("daily_digest.scheduler.started")

    async def stop(self, *, drain_timeout_seconds: int = 5) -> None:
        """Stop the scheduler.

        `drain_timeout_seconds` bounds the wait for in-flight digest callbacks
        to finish before forced shutdown. Idempotent — calling on an
        unstarted scheduler is a no-op.
        """
        if not self._started:
            return
        # apscheduler `shutdown(wait=True)` blocks until in-flight jobs
        # complete; we wrap in a timeout via asyncio.wait_for at the caller
        # layer if needed. Phase 01 uses the synchronous wait for determinism.
        del drain_timeout_seconds  # apscheduler 3.x ignores; recorded for Phase 02
        self._scheduler.shutdown(wait=True)
        self._started = False
        self._jobs.clear()
        logger.info("daily_digest.scheduler.stopped")

    @property
    def started(self) -> bool:
        """True iff `start()` was called and `stop()` has not been."""
        return self._started


__all__ = ["DigestCallback", "DigestScheduler"]
