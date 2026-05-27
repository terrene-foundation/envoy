"""Tier 2 — /redteam Round-1 closures for the Wave-4 daily digest (PR #44).

Regression coverage for the five R1 findings (per rules/testing.md — every fix
ships with a reproducing test):

- HIGH-1 (T-018): the duress banner is stripped for non-primary channels in
  BOTH the markdown body AND the metrics (the shared-payload leak).
- HIGH-2: `record_success` advances the per-channel back-fill watermark in the
  production pipeline (was never called); `record_open` fires on `trigger_now`.
- HIGH-3: `event_only` form is reachable (preference) AND the scheduled fire is
  event-gated (skips when no pending grant / budget < 80%; delivers otherwise).
- MED-3: a non-markdown channel drops classified rows + reports a hidden count
  (`RedactedFieldRenderError` disposition).

Real TrustStoreAdapter (on-disk) + real EnvoyLedger; concrete in-test adapters.
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
from envoy.daily_digest.payload import (
    DIGEST_SCHEMA_VERSION,
    DigestPayload,
    DigestSummary,
    DuressBanner,
)
from envoy.daily_digest.renderer import DigestRenderer
from envoy.daily_digest.schedule_registry import ScheduleRegistry
from envoy.daily_digest.scheduler import DigestScheduler
from envoy.daily_digest.service import DailyDigestService
from envoy.ledger import EnvoyLedger
from envoy.model.router import EnvoyModelRouter
from envoy.trust.store import TrustStoreAdapter

_UTC = timezone.utc
_ALGO = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
_PID = "principal-r1-01"
_NOW = datetime(2026, 5, 27, 8, 0, tzinfo=_UTC)


class _Caps:
    def __init__(self, *, markdown: bool) -> None:
        self.supports_markdown = markdown


class _Adapter:
    def __init__(self, channel_id: str, *, markdown: bool = True) -> None:
        self.channel_id = channel_id
        self._markdown = markdown
        self.received: list[DailyDigestPayload] = []

    @property
    def capabilities(self) -> _Caps:
        return _Caps(markdown=self._markdown)

    async def send_digest(
        self, target_principal_id: str, digest: DailyDigestPayload, *, timeout_seconds: int = 10
    ) -> SendReceipt:
        self.received.append(digest)
        return SendReceipt(
            message_id=f"{self.channel_id}-1",
            delivered_at=datetime.now(tz=_UTC),
            channel_native_id=f"{self.channel_id}-n",
        )


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "trust_vault.db"


async def _ledger() -> EnvoyLedger:
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair("r1-key")
    return EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=mgr,
        signing_key_id="r1-key",
        device_id="device-r1",
        algorithm_identifier=_ALGO,
    )


def _payload(*, duress: bool = False, actions: tuple = (), form: str = "rich") -> DigestPayload:
    return DigestPayload(
        schema_version=DIGEST_SCHEMA_VERSION,
        digest_id="018e7b00-0000-7000-0000-000000000001",
        principal_genesis_id="sha256:" + "a" * 64,
        scheduled_for=_NOW.isoformat(),
        delivered_at=None,
        channel_id="cli",  # primary
        form=form,
        duress_banner=DuressBanner(
            present=duress, shadow_event_ref=("sha256:d1" if duress else None)
        ),
        summary=DigestSummary(
            actions=actions,
            refusals=(),
            spend={"current_microdollars": 0, "monthly_ceiling_microdollars": 0},
            pending_grants=(),
            planned_today=(),
        ),
        user_reply=None,
        receipt_hash="sha256:" + "f" * 64,
    )


# ---------------------------------------------------------------------------
# HIGH-1 (T-018) — banner stripped on non-primary channel (body + metrics)
# ---------------------------------------------------------------------------


class TestDuressBannerNonPrimaryStrip:
    @pytest.mark.asyncio
    async def test_banner_only_on_primary(self) -> None:
        ledger = await _ledger()
        primary = _Adapter("cli")
        secondary = _Adapter("web")
        fanout = PerChannelFanout(
            channel_adapters={"cli": primary, "web": secondary}, ledger=ledger
        )
        await fanout.emit(
            principal_id=_PID,
            payload=_payload(duress=True),  # channel_id="cli" is primary
            active_channel_ids=["cli", "web"],
        )
        primary_wire = primary.received[0]
        secondary_wire = secondary.received[0]
        # Primary sees the banner; secondary never does (body AND metrics).
        assert "Review duress event" in primary_wire.markdown_body
        assert primary_wire.metrics["duress_banner_present"] is True
        assert "Review duress event" not in secondary_wire.markdown_body
        assert secondary_wire.metrics["duress_banner_present"] is False


# ---------------------------------------------------------------------------
# HIGH-2 — record_success advances watermark; record_open on trigger_now
# ---------------------------------------------------------------------------


async def _build(vault_path):
    trust_store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
    await trust_store.initialize()
    ledger = await _ledger()
    registry = ScheduleRegistry(trust_store=trust_store)
    await registry.set_active_channels(_PID, channel_ids=["cli"], primary="cli")
    adapter = _Adapter("cli")
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


class TestStateWritersWired:
    @pytest.mark.asyncio
    async def test_trigger_now_advances_backfill_watermark(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await service.start()
            # No prior success → None.
            assert await trust_store.digest_backfill_get(_PID, channel_id="cli") is None
            await service.trigger_now(_PID)
            # record_success ran in the pipeline → watermark now set.
            row = await trust_store.digest_backfill_get(_PID, channel_id="cli")
            assert row is not None
        finally:
            await service.stop()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_trigger_now_records_engagement_open(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await service.start()
            await service.trigger_now(_PID)
            now = datetime.now(tz=_UTC)
            opens = await trust_store.digest_engagement_opens_in_window(
                _PID, since=now - timedelta(minutes=5), until=now + timedelta(minutes=5)
            )
            assert opens == 1
        finally:
            await service.stop()
            await trust_store.close()


# ---------------------------------------------------------------------------
# HIGH-3 — event_only reachable + event-gated
# ---------------------------------------------------------------------------


class TestEventOnlyForm:
    @pytest.mark.asyncio
    async def test_preference_makes_event_only_reachable(self, vault_path) -> None:
        store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
        await store.initialize()
        try:
            tracker = LowEngagementTracker(trust_store=store)
            await tracker.set_form_preference(_PID, form="event_only")
            assert await tracker.select_form(_PID, now=_NOW) == "event_only"
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_event_only_scheduled_fire_skips_when_no_event(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await LowEngagementTracker(trust_store=trust_store).set_form_preference(
                _PID, form="event_only"
            )
            await service.start()
            # Scheduled fire, no pending grant + no spend → event_only skips delivery.
            await service._fire(_PID)
            assert len(adapter.received) == 0
        finally:
            await service.stop()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_event_only_delivers_on_pending_grant(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await LowEngagementTracker(trust_store=trust_store).set_form_preference(
                _PID, form="event_only"
            )
            await ledger.append(
                entry_type="grant_moment",
                content={
                    "principal_id": _PID,
                    "state": "pending",
                    "grant_id": "g1",
                    "summary": "approve",
                },
            )
            await service.start()
            await service._fire(_PID)
            # Pending grant present → event_only fires.
            assert len(adapter.received) == 1
        finally:
            await service.stop()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_event_only_manual_today_always_delivers(self, vault_path) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await LowEngagementTracker(trust_store=trust_store).set_form_preference(
                _PID, form="event_only"
            )
            await service.start()
            # Manual `today` is NOT event-gated — always delivers.
            await service.trigger_now(_PID)
            assert len(adapter.received) == 1
        finally:
            await service.stop()
            await trust_store.close()


# ---------------------------------------------------------------------------
# MED-3 — non-markdown channel drops classified rows + hidden count
# ---------------------------------------------------------------------------


class TestRedactedFieldRender:
    @pytest.mark.asyncio
    async def test_non_markdown_channel_drops_classified_rows(self) -> None:
        ledger = await _ledger()
        sms = _Adapter("sms", markdown=False)
        fanout = PerChannelFanout(channel_adapters={"sms": sms}, ledger=ledger)
        # One classified action (sha256: ledger_id) + one cleartext action.
        actions = (
            {"ledger_id": "sha256:" + "c" * 8, "summary": "classified op", "outbox_items": ()},
            {"ledger_id": "plain-1", "summary": "public op", "outbox_items": ()},
        )
        import dataclasses

        # sms is the only (hence primary) channel here, so channel_id matches.
        payload = dataclasses.replace(_payload(actions=actions), channel_id="sms")
        await fanout.emit(principal_id=_PID, payload=payload, active_channel_ids=["sms"])
        wire = sms.received[0]
        assert wire.metrics["classified_hidden"] == 1
        assert wire.metrics["actions"] == 1  # only the cleartext row remains
        assert "classified op" not in wire.markdown_body
        assert "public op" in wire.markdown_body
        assert "1 classified entries hidden" in wire.markdown_body

    @pytest.mark.asyncio
    async def test_markdown_channel_keeps_classified_rows(self) -> None:
        ledger = await _ledger()
        cli = _Adapter("cli", markdown=True)
        fanout = PerChannelFanout(channel_adapters={"cli": cli}, ledger=ledger)
        actions = (
            {"ledger_id": "sha256:" + "c" * 8, "summary": "classified op", "outbox_items": ()},
        )
        await fanout.emit(
            principal_id=_PID, payload=_payload(actions=actions), active_channel_ids=["cli"]
        )
        wire = cli.received[0]
        assert wire.metrics["classified_hidden"] == 0
        assert wire.metrics["actions"] == 1
