"""Tier 2 — daily-digest bootstrap wiring (production call site).

Source: T-04-83 `build_digest_service` + `rules/orphan-detection.md` Rule 1 —
the bootstrap is the production call site the CLI uses; it MUST have automated
coverage (the EC-3 / service-wiring tests build the service manually, so the
actual bootstrap assembly path was previously exercised only by manual CLI
smoke-testing).

Verifies the real `build_digest_service` assembles a fully-wired, runnable
service against a real on-disk Trust vault: it starts, binds the cli channel,
drives `trigger_now` end-to-end, and tears down cleanly.

No mocks (`rules/testing.md` Tier 2).
"""

from __future__ import annotations

import pytest

from envoy.daily_digest import DailyDigestService
from envoy.daily_digest.bootstrap import build_digest_service
from envoy.trust.store import TrustStoreAdapter

_PID = "principal-bootstrap-01"


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "trust_vault.db"


class TestBootstrapWiring:
    @pytest.mark.asyncio
    async def test_returns_wired_service_and_store(self, vault_path) -> None:
        service, trust_store, channels = await build_digest_service(
            vault_path=vault_path, principal_id=_PID
        )
        try:
            assert isinstance(service, DailyDigestService)
            assert isinstance(trust_store, TrustStoreAdapter)
            assert "cli" in channels
        finally:
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_binds_cli_channel_as_primary(self, vault_path) -> None:
        service, trust_store, _channels = await build_digest_service(
            vault_path=vault_path, principal_id=_PID
        )
        try:
            # The bootstrap idempotently binds cli as active+primary so the
            # duress reader + back-fill window have a primary to resolve.
            row = await trust_store.digest_active_channels_get(_PID)
            assert row is not None
            active, primary = row
            assert active == ["cli"]
            assert primary == "cli"
        finally:
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_trigger_now_runs_through_bootstrap_path(self, vault_path) -> None:
        service, trust_store, channels = await build_digest_service(
            vault_path=vault_path, principal_id=_PID
        )
        cli_adapter = channels["cli"]
        try:
            await cli_adapter.startup()
            await service.start()
            payload = await service.trigger_now(_PID)
            # End-to-end through the real bootstrap-assembled pipeline.
            assert payload.schema_version == "digest/1.0"
            assert payload.channel_id == "cli"
        finally:
            await service.stop()
            await cli_adapter.shutdown()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_existing_binding_not_overwritten(self, vault_path) -> None:
        """Idempotency: a pre-existing channel binding survives bootstrap."""
        store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
        await store.initialize()
        from envoy.daily_digest.schedule_registry import ScheduleRegistry

        await ScheduleRegistry(trust_store=store).set_active_channels(
            _PID, channel_ids=["cli", "web"], primary="web"
        )
        await store.close()

        service, trust_store, _channels = await build_digest_service(
            vault_path=vault_path, principal_id=_PID
        )
        try:
            row = await trust_store.digest_active_channels_get(_PID)
            assert row is not None
            active, primary = row
            # Bootstrap MUST NOT clobber the pre-existing web-primary binding.
            assert primary == "web"
            assert set(active) == {"cli", "web"}
        finally:
            await trust_store.close()
