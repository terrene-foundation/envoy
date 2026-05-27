"""Tier 2 — T-04-84 — DailyDigestService end-to-end wiring.

Source: T-04-84 per `workspaces/phase-01-mvp/todos/active/04-wave-4-channels-
digest.md` § T-04-84 + shard 11 § 5.

Exercises the full aggregate → render → fan-out → ritual_completion path
through `DailyDigestService.trigger_now` against REAL infrastructure: a real
`TrustStoreAdapter` (on-disk SQLite vault), a real `EnvoyLedger`
(InMemoryAuditStore — the Phase-01 project-wide backing per
`tests/tier2/conftest.py`), real state trackers, and a concrete in-test
`ChannelAdapter` exercising the real `send_digest` signature. No mocks
(`rules/testing.md` Tier 2).

Per `rules/facade-manager-detection.md` Rule 1: this is the manager-shape
wiring test for `DailyDigestService` — it drives the service through its
public surface and asserts the externally-observable effects (ledger rows,
delivered payload).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.channels.envelope import DailyDigestPayload, SendReceipt
from envoy.daily_digest.aggregator import LedgerAggregator
from envoy.daily_digest.backfill import BackfillTracker
from envoy.daily_digest.duress import DuressBannerReader
from envoy.daily_digest.engagement import LowEngagementTracker
from envoy.daily_digest.fanout import PerChannelFanout
from envoy.daily_digest.pause import PauseDisableState
from envoy.daily_digest.renderer import DigestRenderer
from envoy.daily_digest.schedule_registry import ScheduleRegistry
from envoy.daily_digest.scheduler import DigestScheduler
from envoy.daily_digest.service import DailyDigestService
from envoy.ledger import EnvoyLedger
from envoy.model.router import EnvoyModelRouter
from envoy.trust.store import TrustStoreAdapter

_UTC = timezone.utc
_ALGO = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
_PID = "principal-svcwiring-01"


class _CollectingAdapter:
    """Concrete in-test channel adapter (real send_digest signature)."""

    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id
        self.delivered: list[DailyDigestPayload] = []

    async def send_digest(
        self,
        target_principal_id: str,
        digest: DailyDigestPayload,
        *,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        self.delivered.append(digest)
        return SendReceipt(
            message_id=f"{self.channel_id}-1",
            delivered_at=datetime.now(tz=_UTC),
            channel_native_id=f"{self.channel_id}-native-1",
        )


async def _build(
    vault_path,
) -> tuple[DailyDigestService, EnvoyLedger, _CollectingAdapter, TrustStoreAdapter]:
    """Mirror of bootstrap that also returns the ledger + adapter for assertions."""
    trust_store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
    await trust_store.initialize()

    mgr = InMemoryKeyManager()
    await mgr.generate_keypair("svc-key")
    ledger = EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=mgr,
        signing_key_id="svc-key",
        device_id="device-svcwiring",
        algorithm_identifier=_ALGO,
    )

    registry = ScheduleRegistry(trust_store=trust_store)
    await registry.set_active_channels(_PID, channel_ids=["cli"], primary="cli")
    adapter = _CollectingAdapter("cli")

    service = DailyDigestService(
        scheduler=DigestScheduler(),
        aggregator=LedgerAggregator(ledger=ledger),
        renderer=DigestRenderer(model_router=EnvoyModelRouter(), ledger=ledger),
        fanout=PerChannelFanout(channel_adapters={"cli": adapter}, ledger=ledger),
        backfill=BackfillTracker(trust_store=trust_store),
        pause_state=PauseDisableState(trust_store=trust_store),
        low_engagement=LowEngagementTracker(trust_store=trust_store),
        duress_reader=DuressBannerReader(trust_store=trust_store, schedule_registry=registry),
        schedule_registry=registry,
    )
    return service, ledger, adapter, trust_store


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "trust_vault.db"


async def _seed_action(ledger: EnvoyLedger, summary: str) -> None:
    await ledger.append(
        entry_type="PhaseBRecord",
        content={
            "principal_id": _PID,
            "summary": summary,
            "cost_microdollars": 1000,
            "monthly_ceiling_microdollars": 1_000_000,
        },
    )


class TestServiceWiring:
    @pytest.mark.asyncio
    async def test_trigger_now_aggregates_renders_delivers(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await _seed_action(ledger, "sent the welcome email")
            await service.start()
            payload = await service.trigger_now(_PID)

            # Aggregated: the seeded action surfaces in the payload.
            assert len(payload.summary.actions) == 1
            assert payload.summary.spend["current_microdollars"] == 1000
            # Delivered: the adapter received the translated wire shape.
            assert len(adapter.delivered) == 1
            assert isinstance(adapter.delivered[0], DailyDigestPayload)
            assert "sent the welcome email" in adapter.delivered[0].markdown_body
        finally:
            await service.stop()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_ritual_completion_row_after_delivery(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await _seed_action(ledger, "did a thing")
            await service.start()
            await service.trigger_now(_PID)

            now = datetime.now(tz=_UTC)
            entries = await ledger.query(
                filter={"principal_id": _PID, "event_type": "ritual_completion"},
                since=now - timedelta(days=1),
                until=now + timedelta(days=1),
            )
            assert len(entries) == 1
            assert entries[0].content["ritual_kind"] == "daily_digest"
            assert entries[0].content["channel_id"] == "cli"
        finally:
            await service.stop()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_paused_fire_skips_delivery(self, vault_path) -> None:
        """A paused principal's scheduled fire delivers nothing (no ritual row)."""
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await _seed_action(ledger, "should not deliver")
            await service.start()
            await service.pause(_PID, duration_days=7)
            # Drive the scheduled-callback path directly.
            await service._fire(_PID)
            assert len(adapter.delivered) == 0
        finally:
            await service.stop()
            await trust_store.close()
