"""Tier 2 — T-04-84 — digest form selection + per-channel wire translation.

Source: `specs/daily-digest.md` § Channel-adaptive rendering (line 33) +
§ Low-engagement fallback (line 29) + shard 11 § 5.2.

Verifies (against a real EnvoyLedger + real renderer + real fanout):
1. A low-engagement principal renders the `compact` form (T-019 fallback).
2. An engaged principal renders the `rich` form.
3. The fanout translates the structured payload to the channels-side
   `DailyDigestPayload` wire shape (digest_date + markdown_body + metrics)
   regardless of form — per-channel native rendering is the adapter's job;
   the digest layer produces one canonical body + a metrics dict.

No mocks (`rules/testing.md` Tier 2): concrete in-test ChannelAdapter, real
Trust store, real ledger.
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
_PID = "principal-formtest-01"


class _CollectingAdapter:
    def __init__(self) -> None:
        self.delivered: list[DailyDigestPayload] = []

    async def send_digest(
        self, target_principal_id: str, digest: DailyDigestPayload, *, timeout_seconds: int = 10
    ) -> SendReceipt:
        self.delivered.append(digest)
        return SendReceipt(
            message_id="m1", delivered_at=datetime.now(tz=_UTC), channel_native_id="n1"
        )


async def _build(vault_path):
    trust_store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
    await trust_store.initialize()
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair("form-key")
    ledger = EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=mgr,
        signing_key_id="form-key",
        device_id="device-form",
        algorithm_identifier=_ALGO,
    )
    registry = ScheduleRegistry(trust_store=trust_store)
    await registry.set_active_channels(_PID, channel_ids=["cli"], primary="cli")
    adapter = _CollectingAdapter()
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


class TestFormSelection:
    @pytest.mark.asyncio
    async def test_low_engagement_renders_compact(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await service.start()
            # No recorded opens → below the 6-in-21-days threshold → compact.
            payload = await service.trigger_now(_PID)
            assert payload.form == "compact"
        finally:
            await service.stop()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_engaged_renders_rich(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            tracker = LowEngagementTracker(trust_store=trust_store)
            now = datetime.now(tz=_UTC)
            for d in range(1, 7):
                await tracker.record_open(_PID, opened_at=now - timedelta(days=d))
            await service.start()
            payload = await service.trigger_now(_PID)
            assert payload.form == "rich"
        finally:
            await service.stop()
            await trust_store.close()


class TestWireTranslation:
    @pytest.mark.asyncio
    async def test_wire_shape_carries_body_and_metrics(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await ledger.append(
                entry_type="PhaseBRecord",
                content={
                    "principal_id": _PID,
                    "summary": "shipped report",
                    "cost_microdollars": 50,
                },
            )
            await service.start()
            await service.trigger_now(_PID)
            wire = adapter.delivered[0]
            assert isinstance(wire, DailyDigestPayload)
            assert "shipped report" in wire.markdown_body
            assert wire.metrics["actions"] == 1
            assert wire.metrics["form"] in {"rich", "compact", "event_only"}
        finally:
            await service.stop()
            await trust_store.close()
