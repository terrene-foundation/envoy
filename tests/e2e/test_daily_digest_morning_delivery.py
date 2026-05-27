"""E2E (Tier 3) — EC-3 acceptance: Daily Digest fires 7 consecutive days.

Per `specs/daily-digest.md` § Test location line 88 +
`workspaces/phase-01-mvp/todos/active/04-wave-4-channels-digest.md` § T-04-84
+ `02-plans/01-build-sequence.md` § Milestone 4 (EC-3 digest 7-day green).

EC-3 disposition (Option A, UTC-only — `01-analysis/22-spec-gap-analysis.md`
§ 4): "the scheduled Daily Digest fires at the scheduled hour for ≥7
consecutive days" (the local-morning qualifier is the Phase-02 Option-B lift).

Time compression: the `DailyDigestService` exposes `_utc_now()` as its single
wall-clock seam precisely so this battery needs no `freezegun` / no real
7-day wait. Monkeypatching that seam to return 7 successive 08:00-UTC days and
driving the scheduled-callback path (`service._fire`) once per day produces 7
`ritual_completion` ledger entries with 7 distinct consecutive dates — the
durable EC-3 evidence (shard 11 § 5.1 write pattern). This exercises the full
fire → aggregate → render → fan-out → ledger path 7 times against real
infrastructure (real TrustStoreAdapter on-disk vault, real EnvoyLedger, a
concrete in-test ChannelAdapter).

Per `rules/probe-driven-verification.md`: assertions are structural (count of
ledger rows, distinct-date set, per-day delivery count), never regex over the
rendered digest prose.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

import envoy.daily_digest.service as service_mod
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
_PID = "principal-ec3-01"
_DAY0 = datetime(2026, 5, 1, 8, 0, tzinfo=_UTC)


class _DeliveringAdapter:
    """Concrete in-test adapter recording one delivery per fire."""

    def __init__(self) -> None:
        self.deliveries: list[DailyDigestPayload] = []
        self._counter = 0

    async def send_digest(
        self,
        target_principal_id: str,
        digest: DailyDigestPayload,
        *,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        self._counter += 1
        self.deliveries.append(digest)
        return SendReceipt(
            message_id=f"cli-{self._counter}",
            delivered_at=datetime.now(tz=_UTC),
            channel_native_id=f"cli-native-{self._counter}",
        )


async def _build(vault_path):
    trust_store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
    await trust_store.initialize()

    mgr = InMemoryKeyManager()
    await mgr.generate_keypair("ec3-key")
    ledger = EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=mgr,
        signing_key_id="ec3-key",
        device_id="device-ec3",
        algorithm_identifier=_ALGO,
    )

    registry = ScheduleRegistry(trust_store=trust_store)
    await registry.set_active_channels(_PID, channel_ids=["cli"], primary="cli")
    adapter = _DeliveringAdapter()

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


class TestEC3SevenDayFire:
    @pytest.mark.asyncio
    async def test_seven_consecutive_days_fire(self, vault_path, monkeypatch) -> None:
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await service.start()

            for day in range(7):
                fire_time = _DAY0 + timedelta(days=day)
                # Seed one action on this day so the digest has content.
                await ledger.append(
                    entry_type="PhaseBRecord",
                    content={
                        "principal_id": _PID,
                        "summary": f"day-{day} action",
                        "cost_microdollars": 100,
                        "monthly_ceiling_microdollars": 1_000_000,
                    },
                )
                # Compress time via the service's single now-seam.
                monkeypatch.setattr(service_mod, "_utc_now", lambda ft=fire_time: ft)
                await service._fire(_PID)

            # EC-3 evidence: 7 ritual_completion entries, 7 distinct scheduled
            # days. The ledger entry's append timestamp is real wall-clock, so
            # the query window brackets real-now; the consecutive-day key is
            # the compressed `scheduled_for` carried in the entry content.
            now = datetime.now(tz=_UTC)
            entries = await ledger.query(
                filter={"principal_id": _PID, "event_type": "ritual_completion"},
                since=now - timedelta(days=1),
                until=now + timedelta(days=1),
            )
            assert len(entries) == 7, f"expected 7 daily fires, got {len(entries)}"

            scheduled_dates = {e.content["scheduled_for"][:10] for e in entries}
            assert (
                len(scheduled_dates) == 7
            ), f"expected 7 distinct scheduled days, got {sorted(scheduled_dates)}"
            assert scheduled_dates == {
                (_DAY0 + timedelta(days=d)).date().isoformat() for d in range(7)
            }
            # The adapter received exactly one delivery per day.
            assert len(adapter.deliveries) == 7
        finally:
            await service.stop()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_pause_midweek_then_resume_skips_paused_days(
        self, vault_path, monkeypatch
    ) -> None:
        """A pause on day 3 skips delivery until resume — EC-3 pause interaction."""
        service, ledger, adapter, trust_store = await _build(vault_path)
        try:
            await service.start()
            for day in range(7):
                fire_time = _DAY0 + timedelta(days=day)
                monkeypatch.setattr(service_mod, "_utc_now", lambda ft=fire_time: ft)
                if day == 2:
                    # Pause for 2 days starting day 2 → days 2,3 skipped.
                    await service.pause(_PID, duration_days=2)
                if day == 4:
                    await service.resume(_PID)
                await service._fire(_PID)

            now = datetime.now(tz=_UTC)
            entries = await ledger.query(
                filter={"principal_id": _PID, "event_type": "ritual_completion"},
                since=now - timedelta(days=1),
                until=now + timedelta(days=1),
            )
            # Days 0,1 fired; 2,3 paused; 4,5,6 fired → 5 deliveries.
            assert len(entries) == 5
        finally:
            await service.stop()
            await trust_store.close()
