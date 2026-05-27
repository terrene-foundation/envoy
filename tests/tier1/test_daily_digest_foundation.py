"""Tier 1 — T-04-80 — envoy.daily_digest foundation.

Source: T-04-80 per `workspaces/phase-01-mvp/todos/active/04-wave-4-channels-
digest.md` § T-04-80 + shard 11
(`workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`).

Foundation surface tested in this file:

1. ``DigestPayload`` 11-field schema/1.0 dataclass construction + frozenness.
2. ``DuressBanner`` + ``DigestSummary`` nested-dataclass shapes.
3. ``DIGEST_SCHEMA_VERSION`` literal pin.
4. 5 typed errors + base class per spec § Error taxonomy.
5. ``DigestScheduler`` register / unregister / start / stop invariants.
6. ``DailyDigestService`` facade construction with Protocol-typed deps.

Per `rules/testing.md` Tier 1: mocking allowed; this exercise the foundation's
internal shape without crossing the channel-adapter or ledger boundary. The
Tier 2 wiring test (T-04-84) drives the full aggregate → render → fan-out
pipeline against real infrastructure.

Per `rules/probe-driven-verification.md`: every semantic assertion below is
structural (field count, type-check, exception subclass, registered set), not
regex over rendered prose. Structural probes are the canonical Tier-1 shape
when no LLM judge is needed.
"""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import datetime, timezone

import pytest

from envoy.daily_digest import (
    DIGEST_SCHEMA_VERSION,
    DailyDigestError,
    DailyDigestService,
    DigestDeliveryFailedError,
    DigestPayload,
    DigestScheduler,
    DigestSkippedTooLongWarning,
    DigestSummary,
    DuressBanner,
    DuressBannerSuppressedError,
    LowEngagementFallbackTriggered,
    RedactedFieldRenderError,
)

# ---------------------------------------------------------------------------
# § 1 — DigestPayload schema/1.0 invariants
# ---------------------------------------------------------------------------


class TestDigestPayloadSchemaInvariants:
    """Spec § Schema lines 39-64 — 11 fields exactly, schema_version pinned."""

    def test_payload_is_frozen_dataclass(self) -> None:
        """Frozen so canonical-JSON byte-identity is stable across mutations."""
        assert is_dataclass(DigestPayload)
        # Frozen dataclasses raise FrozenInstanceError on attribute set.
        payload = _build_payload()
        with pytest.raises(FrozenInstanceError):
            payload.digest_id = "mutated"  # type: ignore[misc]

    def test_payload_has_exactly_11_fields(self) -> None:
        """Spec § Schema enumerates 11 fields; any drift fails this probe."""
        field_names = {f.name for f in fields(DigestPayload)}
        expected = {
            "schema_version",
            "digest_id",
            "principal_genesis_id",
            "scheduled_for",
            "delivered_at",
            "channel_id",
            "form",
            "duress_banner",
            "summary",
            "user_reply",
            "receipt_hash",
        }
        assert field_names == expected
        assert len(field_names) == 11

    def test_schema_version_literal_is_digest_1_0(self) -> None:
        assert DIGEST_SCHEMA_VERSION == "digest/1.0"

    def test_duress_banner_two_fields(self) -> None:
        """Spec § Schema lines 50-53."""
        assert is_dataclass(DuressBanner)
        assert {f.name for f in fields(DuressBanner)} == {
            "present",
            "shadow_event_ref",
        }

    def test_digest_summary_five_fields(self) -> None:
        """Spec § Schema lines 54-60 — 5 sections."""
        assert is_dataclass(DigestSummary)
        assert {f.name for f in fields(DigestSummary)} == {
            "actions",
            "refusals",
            "spend",
            "pending_grants",
            "planned_today",
        }

    def test_payload_construction_round_trip(self) -> None:
        """Constructing with the canonical 11 args yields a usable payload."""
        payload = _build_payload()
        assert payload.schema_version == DIGEST_SCHEMA_VERSION
        assert payload.form in {"rich", "compact", "event_only"}
        assert isinstance(payload.summary, DigestSummary)
        assert isinstance(payload.duress_banner, DuressBanner)


# ---------------------------------------------------------------------------
# § 2 — Error taxonomy (5 typed + base) per spec § Error taxonomy
# ---------------------------------------------------------------------------


class TestErrorTaxonomy:
    """Spec § Error taxonomy lines 68-76 — 5 typed errors + advisory."""

    def test_base_is_runtime_error_subclass(self) -> None:
        assert issubclass(DailyDigestError, RuntimeError)

    @pytest.mark.parametrize(
        "exc_cls",
        [
            DigestDeliveryFailedError,
            DuressBannerSuppressedError,
            RedactedFieldRenderError,
            LowEngagementFallbackTriggered,
            DigestSkippedTooLongWarning,
        ],
    )
    def test_every_error_subclasses_base(self, exc_cls: type) -> None:
        assert issubclass(exc_cls, DailyDigestError)

    def test_taxonomy_size_is_5_plus_base(self) -> None:
        """Spec § Error taxonomy has 5 rows; the base is implementation glue.

        Any addition to the taxonomy requires both a spec edit and an error
        class — this probe catches drift.
        """
        from envoy.daily_digest import errors as _errors

        leaf_errors = {name for name in _errors.__all__ if name != "DailyDigestError"}
        assert leaf_errors == {
            "DigestDeliveryFailedError",
            "DuressBannerSuppressedError",
            "RedactedFieldRenderError",
            "LowEngagementFallbackTriggered",
            "DigestSkippedTooLongWarning",
        }


# ---------------------------------------------------------------------------
# § 3 — DigestScheduler invariants (apscheduler wrapper)
# ---------------------------------------------------------------------------


class TestDigestScheduler:
    """T-04-80 § 3 invariants — per-principal registration, restart-safe, UTC."""

    @pytest.mark.asyncio
    async def test_register_then_unregister_round_trip(self) -> None:
        scheduler = DigestScheduler()
        await scheduler.start()
        try:
            assert not scheduler.is_registered("p1")
            await scheduler.register(
                "p1",
                hour=8,
                timezone="UTC",
                callback=_noop_async,
            )
            assert scheduler.is_registered("p1")
            assert scheduler.registered_principals() == ("p1",)

            await scheduler.unregister("p1")
            assert not scheduler.is_registered("p1")
            assert scheduler.registered_principals() == ()
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_register_replaces_existing_job_for_same_principal(self) -> None:
        """Invariant 1: per-principal register() replaces prior job."""
        scheduler = DigestScheduler()
        await scheduler.start()
        try:
            await scheduler.register(
                "p1",
                hour=8,
                timezone="UTC",
                callback=_noop_async,
            )
            await scheduler.register(
                "p1",
                hour=14,
                timezone="UTC",
                callback=_noop_async,
            )
            # Still exactly one registration — replacement, not stacking.
            assert scheduler.registered_principals() == ("p1",)
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self) -> None:
        """Invariant 2: restart-safe — start() twice is a no-op."""
        scheduler = DigestScheduler()
        await scheduler.start()
        try:
            await scheduler.start()  # second call MUST NOT raise
            assert scheduler.started is True
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self) -> None:
        scheduler = DigestScheduler()
        # stop() on unstarted scheduler is a no-op.
        await scheduler.stop()
        assert scheduler.started is False

    @pytest.mark.asyncio
    async def test_hour_out_of_range_raises(self) -> None:
        scheduler = DigestScheduler()
        await scheduler.start()
        try:
            with pytest.raises(ValueError, match="hour"):
                await scheduler.register(
                    "p1",
                    hour=24,
                    timezone="UTC",
                    callback=_noop_async,
                )
            with pytest.raises(ValueError, match="hour"):
                await scheduler.register(
                    "p1",
                    hour=-1,
                    timezone="UTC",
                    callback=_noop_async,
                )
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_unregister_unknown_principal_is_noop(self) -> None:
        scheduler = DigestScheduler()
        await scheduler.start()
        try:
            await scheduler.unregister("never-registered")  # MUST NOT raise
            assert not scheduler.is_registered("never-registered")
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_non_utc_timezone_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Invariant 3: UTC-only; non-UTC requests are logged for Phase-02 sweep."""
        import logging

        scheduler = DigestScheduler()
        await scheduler.start()
        try:
            with caplog.at_level(logging.WARNING, logger="envoy.daily_digest.scheduler"):
                await scheduler.register(
                    "p1",
                    hour=8,
                    timezone="America/New_York",
                    callback=_noop_async,
                )
            # The WARN log surfaces every non-UTC caller — grep-able for
            # Phase-02 Option-B lift.
            warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert any(
                "timezone_override_ignored" in r.message
                or "timezone_override_ignored" in getattr(r, "event", "")
                or "timezone_override_ignored" in r.getMessage()
                for r in warn_records
            )
        finally:
            await scheduler.stop()


# ---------------------------------------------------------------------------
# § 4 — DailyDigestService facade construction
# ---------------------------------------------------------------------------


class TestDailyDigestServiceConstruction:
    """Facade construction with Protocol-typed dependencies.

    Proves the facade signature accepts the seven collaborators by keyword
    only — the explicit-dependency-injection contract from
    `rules/facade-manager-detection.md` Rule 3.
    """

    def test_construct_with_protocol_typed_deps(self) -> None:
        service = _build_service_with_stubs()
        assert isinstance(service, DailyDigestService)
        assert service.started is False

    @pytest.mark.asyncio
    async def test_start_then_stop_round_trip(self) -> None:
        service = _build_service_with_stubs()
        await service.start()
        assert service.started is True
        await service.stop()
        assert service.started is False

    @pytest.mark.asyncio
    async def test_pause_unregisters_scheduler_job(self) -> None:
        service = _build_service_with_stubs(
            schedules=[("p1", _StubSchedule(hour=8, timezone="UTC"))],
        )
        await service.start()
        try:
            # After start with a schedule registered, the principal is
            # registered in the scheduler.
            assert service._scheduler.is_registered("p1")  # type: ignore[attr-defined]
            await service.pause("p1")
            assert not service._scheduler.is_registered("p1")  # type: ignore[attr-defined]
        finally:
            await service.stop()


# ---------------------------------------------------------------------------
# § 5 — LOC invariant per `rules/refactor-invariants.md`
# ---------------------------------------------------------------------------


class TestFoundationLOCInvariant:
    """Guard the foundation surface stays bounded.

    Per `rules/refactor-invariants.md` MUST Rule 1: every refactor that
    reduces a file's line count needs a corresponding invariant. The same
    principle applies to a new module: cap the foundation size now so a
    future merge cannot silently re-inline parallel-worktree shards back
    into this module.

    Caps are 1.15× the post-T-04-80 line counts, leaving room for spec
    citation updates without burning the budget. Increase only when a real
    foundation extension lands (not when T-04-81/T-04-82 add their own
    modules — those are siblings, not extensions).
    """

    def test_foundation_files_under_loc_cap(self) -> None:
        from pathlib import Path

        pkg = Path("envoy/daily_digest")
        caps = {
            "__init__.py": 100,
            "errors.py": 100,
            "payload.py": 120,
            "scheduler.py": 260,
            "service.py": 560,
        }
        for fname, cap in caps.items():
            path = pkg / fname
            line_count = len(path.read_text().splitlines())
            assert line_count <= cap, (
                f"{path} has {line_count} lines (cap {cap}). "
                f"If a sibling module was inlined here, split it out. "
                f"If a foundation extension genuinely needs more room, "
                f"raise the cap deliberately."
            )


# ---------------------------------------------------------------------------
# Fixtures + stubs
# ---------------------------------------------------------------------------


async def _noop_async(*_args, **_kwargs) -> None:
    await asyncio.sleep(0)


def _build_payload() -> DigestPayload:
    return DigestPayload(
        schema_version=DIGEST_SCHEMA_VERSION,
        digest_id="018e7b00-0000-7000-0000-000000000001",
        principal_genesis_id="sha256:" + "0" * 64,
        scheduled_for=datetime(2026, 5, 27, 8, 0, tzinfo=timezone.utc).isoformat(),
        delivered_at=None,
        channel_id="cli",
        form="rich",
        duress_banner=DuressBanner(present=False, shadow_event_ref=None),
        summary=DigestSummary(
            actions=(),
            refusals=(),
            spend={"current_microdollars": 0, "monthly_ceiling_microdollars": 1_000_000},
            pending_grants=(),
            planned_today=(),
        ),
        user_reply=None,
        receipt_hash="sha256:" + "f" * 64,
    )


class _StubSchedule:
    def __init__(self, *, hour: int, timezone: str) -> None:
        self.hour = hour
        self.timezone = timezone


class _StubScheduleRegistry:
    def __init__(
        self,
        *,
        schedules: list[tuple[str, _StubSchedule]] | None = None,
    ) -> None:
        self._schedules: dict[str, _StubSchedule] = {
            pid: sched for (pid, sched) in (schedules or [])
        }

    async def list_all(self) -> list[tuple[str, _StubSchedule]]:
        return list(self._schedules.items())

    async def get(self, principal_id: str) -> _StubSchedule | None:
        return self._schedules.get(principal_id)

    async def set(self, principal_id: str, *, hour: int, timezone: str) -> None:
        self._schedules[principal_id] = _StubSchedule(hour=hour, timezone=timezone)

    async def active_channels(self, principal_id: str) -> tuple[str, ...]:
        return ("cli",)

    async def primary_channel(self, principal_id: str) -> str:
        return "cli"


class _StubPauseState:
    def __init__(self) -> None:
        self._paused: set[str] = set()

    async def is_paused(self, principal_id: str, *, now: datetime) -> bool:
        return principal_id in self._paused

    async def is_skip_too_long(self, principal_id: str, *, now: datetime) -> bool:
        return False

    async def pause(
        self,
        principal_id: str,
        *,
        duration_days: int = 7,
        reason: str = "user_requested",
    ) -> None:
        self._paused.add(principal_id)

    async def resume(self, principal_id: str) -> None:
        self._paused.discard(principal_id)


class _StubAggregator:
    async def aggregate(
        self, *, principal_id: str, since: datetime, until: datetime
    ) -> DigestSummary:
        return DigestSummary(
            actions=(),
            refusals=(),
            spend={"current_microdollars": 0, "monthly_ceiling_microdollars": 0},
            pending_grants=(),
            planned_today=(),
        )


class _StubRenderer:
    async def render(
        self,
        *,
        principal_id: str,
        channel_id: str,
        summary,
        duress_banner,
        form: str,
        scheduled_for: datetime,
        back_fill_days: int,
    ) -> DigestPayload:
        return _build_payload()


class _StubFanout:
    async def emit(
        self,
        *,
        principal_id: str,
        payload: DigestPayload,
        active_channel_ids: list[str],
        timeout_seconds: int = 10,
    ) -> dict:
        return {channel_id: "ok" for channel_id in active_channel_ids}


class _StubBackfill:
    async def query_window(
        self,
        *,
        principal_id: str,
        channel_id: str,
        scheduled_for: datetime,
    ) -> tuple[datetime, int]:
        return (scheduled_for, 0)

    async def record_success(
        self, *, principal_id: str, channel_id: str, receipt, digest_id: str
    ) -> None:
        return None


class _StubLowEngagement:
    async def select_form(self, principal_id: str, *, now: datetime) -> str:
        return "rich"

    async def record_open(self, principal_id: str, *, opened_at: datetime) -> None:
        return None


class _StubDuressReader:
    async def check(
        self,
        *,
        principal_id: str,
        channel_id: str,
        since: datetime,
    ) -> DuressBanner:
        return DuressBanner(present=False, shadow_event_ref=None)


def _build_service_with_stubs(
    *,
    schedules: list[tuple[str, _StubSchedule]] | None = None,
) -> DailyDigestService:
    return DailyDigestService(
        scheduler=DigestScheduler(),
        aggregator=_StubAggregator(),
        renderer=_StubRenderer(),
        fanout=_StubFanout(),
        backfill=_StubBackfill(),
        pause_state=_StubPauseState(),
        low_engagement=_StubLowEngagement(),
        duress_reader=_StubDuressReader(),
        schedule_registry=_StubScheduleRegistry(schedules=schedules),
    )
