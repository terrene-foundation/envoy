"""Tier 1 — T-04-82 — PerChannelFanout (fault-isolated + ritual_completion).

Source: T-04-82 per `workspaces/phase-01-mvp/todos/active/04-wave-4-channels-
digest.md` § T-04-82 + shard 11 § 3 step 4 + § 5.1.

Coverage:
1. all-channels-succeed → receipt dict, one ritual_completion per channel.
2. one-fails-others-succeed → dict carries both shapes, no raise.
3. all-fail → raises DigestDeliveryFailedError.
4. empty active set → raises DigestDeliveryFailedError.
5. DigestPayload → channels DailyDigestPayload translation (markdown_body +
   metrics) crosses the adapter boundary correctly.
6. ritual_completion entries land in the Ledger (queryable for EC-3).

Channel adapters here are minimal in-test ChannelAdapter subclasses (NOT
unittest.mock) that record calls / raise on demand — exercising the real
send_digest signature and the real fault-isolation path. The Ledger is a real
EnvoyLedger over InMemoryAuditStore.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.channels.envelope import DailyDigestPayload, SendReceipt
from envoy.channels.errors import ChannelTransportError
from envoy.daily_digest.errors import DigestDeliveryFailedError
from envoy.daily_digest.fanout import PerChannelFanout
from envoy.daily_digest.payload import (
    DIGEST_SCHEMA_VERSION,
    DigestPayload,
    DigestSummary,
    DuressBanner,
)
from envoy.ledger import EnvoyLedger

_UTC = timezone.utc
_ALGO = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
_SIGNING_KEY = "envoy-signing-key"
_PID = "principal-fanouttest-01"


class _RecordingAdapter:
    """Minimal in-test channel adapter — records send_digest calls.

    Not a unittest.mock: a concrete object exercising the real send_digest
    signature so the fanout's adapter-boundary translation is genuinely tested.
    """

    def __init__(self, channel_id: str, *, fail: bool = False) -> None:
        self.channel_id = channel_id
        self._fail = fail
        self.received: list[DailyDigestPayload] = []

    async def send_digest(
        self, target_principal_id: str, digest: DailyDigestPayload, *, timeout_seconds: int = 10
    ) -> SendReceipt:
        if self._fail:
            raise ChannelTransportError(f"{self.channel_id} transport down")
        self.received.append(digest)
        return SendReceipt(
            message_id=f"{self.channel_id}-msg",
            delivered_at=datetime.now(tz=_UTC),
            channel_native_id=f"{self.channel_id}-native",
        )


async def _ledger() -> EnvoyLedger:
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(_SIGNING_KEY)
    return EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=mgr,
        signing_key_id=_SIGNING_KEY,
        device_id="device-fanout",
        algorithm_identifier=_ALGO,
    )


def _payload() -> DigestPayload:
    return DigestPayload(
        schema_version=DIGEST_SCHEMA_VERSION,
        digest_id="018e7b00-0000-7000-0000-000000000001",
        principal_genesis_id="sha256:" + "a" * 64,
        scheduled_for=datetime(2026, 5, 27, 8, 0, tzinfo=_UTC).isoformat(),
        delivered_at=None,
        channel_id="cli",
        form="rich",
        duress_banner=DuressBanner(present=False, shadow_event_ref=None),
        summary=DigestSummary(
            actions=({"ledger_id": "e1", "summary": "did a thing", "outbox_items": ()},),
            refusals=(),
            spend={"current_microdollars": 2000, "monthly_ceiling_microdollars": 1_000_000},
            pending_grants=(),
            planned_today=(),
        ),
        user_reply=None,
        receipt_hash="sha256:" + "f" * 64,
    )


class TestFanoutSuccess:
    @pytest.mark.asyncio
    async def test_all_channels_succeed(self) -> None:
        ledger = await _ledger()
        adapters = {"cli": _RecordingAdapter("cli"), "web": _RecordingAdapter("web")}
        fanout = PerChannelFanout(channel_adapters=adapters, ledger=ledger)
        outcome = await fanout.emit(
            principal_id=_PID, payload=_payload(), active_channel_ids=["cli", "web"]
        )
        assert set(outcome.keys()) == {"cli", "web"}
        assert all(isinstance(v, SendReceipt) for v in outcome.values())

    @pytest.mark.asyncio
    async def test_ritual_completion_written_per_channel(self) -> None:
        ledger = await _ledger()
        adapters = {"cli": _RecordingAdapter("cli"), "web": _RecordingAdapter("web")}
        fanout = PerChannelFanout(channel_adapters=adapters, ledger=ledger)
        await fanout.emit(principal_id=_PID, payload=_payload(), active_channel_ids=["cli", "web"])
        # EC-3 evidence: ritual_completion entries land in the Ledger.
        now = datetime.now(tz=_UTC)
        entries = await ledger.query(
            filter={"principal_id": _PID, "event_type": "ritual_completion"},
            since=now.replace(year=2020),
            until=now.replace(year=2030),
        )
        assert len(entries) == 2
        kinds = {e.content["ritual_kind"] for e in entries}
        assert kinds == {"daily_digest"}


class TestFanoutTranslation:
    @pytest.mark.asyncio
    async def test_payload_translated_to_channel_wire_shape(self) -> None:
        ledger = await _ledger()
        adapter = _RecordingAdapter("cli")
        fanout = PerChannelFanout(channel_adapters={"cli": adapter}, ledger=ledger)
        await fanout.emit(principal_id=_PID, payload=_payload(), active_channel_ids=["cli"])
        assert len(adapter.received) == 1
        wire = adapter.received[0]
        assert isinstance(wire, DailyDigestPayload)
        assert wire.digest_date == "2026-05-27"
        assert "did a thing" in wire.markdown_body
        # metrics carry the section counts + spend for adapter headline render.
        assert wire.metrics["actions"] == 1
        assert wire.metrics["current_microdollars"] == 2000
        assert wire.metrics["form"] == "rich"


class TestFanoutFaultIsolation:
    @pytest.mark.asyncio
    async def test_one_fails_others_succeed(self) -> None:
        ledger = await _ledger()
        adapters = {
            "cli": _RecordingAdapter("cli"),
            "web": _RecordingAdapter("web", fail=True),
        }
        fanout = PerChannelFanout(channel_adapters=adapters, ledger=ledger)
        outcome = await fanout.emit(
            principal_id=_PID, payload=_payload(), active_channel_ids=["cli", "web"]
        )
        assert isinstance(outcome["cli"], SendReceipt)
        assert isinstance(outcome["web"], ChannelTransportError)
        # ritual_completion only for the success.
        now = datetime.now(tz=_UTC)
        entries = await ledger.query(
            filter={"principal_id": _PID, "event_type": "ritual_completion"},
            since=now.replace(year=2020),
            until=now.replace(year=2030),
        )
        assert len(entries) == 1
        assert entries[0].content["channel_id"] == "cli"

    @pytest.mark.asyncio
    async def test_all_fail_raises(self) -> None:
        ledger = await _ledger()
        adapters = {
            "cli": _RecordingAdapter("cli", fail=True),
            "web": _RecordingAdapter("web", fail=True),
        }
        fanout = PerChannelFanout(channel_adapters=adapters, ledger=ledger)
        with pytest.raises(DigestDeliveryFailedError):
            await fanout.emit(
                principal_id=_PID, payload=_payload(), active_channel_ids=["cli", "web"]
            )

    @pytest.mark.asyncio
    async def test_empty_active_set_raises(self) -> None:
        ledger = await _ledger()
        fanout = PerChannelFanout(channel_adapters={}, ledger=ledger)
        with pytest.raises(DigestDeliveryFailedError):
            await fanout.emit(principal_id=_PID, payload=_payload(), active_channel_ids=[])

    @pytest.mark.asyncio
    async def test_unknown_channel_isolated_as_failure(self) -> None:
        ledger = await _ledger()
        adapters = {"cli": _RecordingAdapter("cli")}
        fanout = PerChannelFanout(channel_adapters=adapters, ledger=ledger)
        outcome = await fanout.emit(
            principal_id=_PID,
            payload=_payload(),
            active_channel_ids=["cli", "ghost"],
        )
        assert isinstance(outcome["cli"], SendReceipt)
        assert isinstance(outcome["ghost"], KeyError)
