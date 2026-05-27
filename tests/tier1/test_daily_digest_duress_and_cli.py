"""Tier 1 — T-04-83 — DuressBannerReader + `envoy digest` CLI surface.

Source: T-04-83 per `workspaces/phase-01-mvp/todos/active/04-wave-4-channels-
digest.md` § T-04-83 + shard 11 § 3 step 6 + `specs/daily-digest.md`
§ Shadow-segment post-duress surface (V2 C-02) + § Error taxonomy
`DuressBannerSuppressedError` (T-018).

Coverage — DuressBannerReader:
1. No unread duress event → present=False (Phase-01 default path).
2. Unread event on PRIMARY channel → present=True (banner rendered).
3. Unread event on NON-primary channel → present=False (T-018 suppression).
4. Unread event with no channel binding → present=False (fail-safe).

Coverage — CLI surface (AST-locked per the shamir-CLI precedent):
5. `envoy digest` group exposes today / pause / resume / schedule.
6. schedule rejects --hour out of [0,23].

DuressBannerReader runs against a REAL TrustStoreAdapter; the unread-event
cases monkeypatch `shadow_segment_unread_duress_events` (Phase-01 it returns
`[]`; the gate logic is exercised by injecting an event the Phase-02 detector
would produce). CLI surface uses click's CliRunner — no subprocess.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from envoy.cli.digest import digest as digest_group
from envoy.daily_digest.duress import DuressBannerReader
from envoy.daily_digest.payload import DuressBanner
from envoy.daily_digest.schedule_registry import ScheduleRegistry
from envoy.trust.store import TrustStoreAdapter

_PID = "principal-duresstest-01"


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "trust_vault.db"


async def _store(vault_path) -> TrustStoreAdapter:
    store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
    await store.initialize()
    return store


from datetime import datetime, timezone  # noqa: E402

_NOW = datetime(2026, 5, 27, 8, 0, tzinfo=timezone.utc)


class TestDuressBannerReader:
    @pytest.mark.asyncio
    async def test_no_event_no_banner(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            registry = ScheduleRegistry(trust_store=store)
            await registry.set_active_channels(_PID, channel_ids=["cli"], primary="cli")
            reader = DuressBannerReader(trust_store=store, schedule_registry=registry)
            banner = await reader.check(principal_id=_PID, channel_id="cli", since=_NOW)
            assert banner == DuressBanner(present=False, shadow_event_ref=None)
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_event_on_primary_renders_banner(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            registry = ScheduleRegistry(trust_store=store)
            await registry.set_active_channels(_PID, channel_ids=["cli"], primary="cli")
            reader = DuressBannerReader(trust_store=store, schedule_registry=registry)

            async def _fake_events(principal_id):
                return [{"ledger_id": "sha256:duress01"}]

            store.shadow_segment_unread_duress_events = _fake_events  # type: ignore[assignment]
            banner = await reader.check(principal_id=_PID, channel_id="cli", since=_NOW)
            assert banner.present is True
            assert banner.shadow_event_ref == "sha256:duress01"
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_event_on_non_primary_suppressed(self, vault_path) -> None:
        """T-018: a non-primary channel never sees the banner."""
        store = await _store(vault_path)
        try:
            registry = ScheduleRegistry(trust_store=store)
            await registry.set_active_channels(_PID, channel_ids=["cli", "web"], primary="cli")
            reader = DuressBannerReader(trust_store=store, schedule_registry=registry)

            async def _fake_events(principal_id):
                return [{"ledger_id": "sha256:duress01"}]

            store.shadow_segment_unread_duress_events = _fake_events  # type: ignore[assignment]
            # web is NOT the primary → suppressed.
            banner = await reader.check(principal_id=_PID, channel_id="web", since=_NOW)
            assert banner.present is False
            assert banner.shadow_event_ref is None
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_event_with_no_binding_fails_safe(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            registry = ScheduleRegistry(trust_store=store)
            reader = DuressBannerReader(trust_store=store, schedule_registry=registry)

            async def _fake_events(principal_id):
                return [{"ledger_id": "sha256:duress01"}]

            store.shadow_segment_unread_duress_events = _fake_events  # type: ignore[assignment]
            # No channel binding → cannot determine primary → fail-safe no-banner.
            banner = await reader.check(principal_id=_PID, channel_id="cli", since=_NOW)
            assert banner.present is False
        finally:
            await store.close()


class TestDigestCliSurface:
    """AST-style surface lock — command names + option presence are contract."""

    def test_group_exposes_five_subcommands(self) -> None:
        assert set(digest_group.commands.keys()) == {
            "today",
            "pause",
            "resume",
            "schedule",
            "form",
        }

    def test_form_rejects_unknown_value(self) -> None:
        runner = CliRunner()
        result = runner.invoke(digest_group, ["form", "--set", "weird", "--principal", "x@y"])
        # click Choice rejects values outside the allowlist.
        assert result.exit_code != 0

    def test_form_requires_set(self) -> None:
        runner = CliRunner()
        result = runner.invoke(digest_group, ["form", "--principal", "x@y"])
        assert result.exit_code != 0

    def test_schedule_rejects_out_of_range_hour(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            digest_group,
            ["schedule", "--hour", "25", "--principal", "x@y", "--vault", "/tmp/none.db"],
        )
        assert result.exit_code != 0
        assert "hour" in result.output.lower()

    def test_schedule_requires_hour(self) -> None:
        runner = CliRunner()
        result = runner.invoke(digest_group, ["schedule", "--principal", "x@y"])
        # click usage error for the missing required --hour.
        assert result.exit_code != 0
