# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S11.6 — maybe_record_flag hot-path swap + L-01 24h ritual-coupling debounce.

Tier-2 per `rules/testing.md`: drives the REAL `HeartbeatClient` pipeline with a
deterministic injected clock (a Protocol-adapter, NOT a mock). Asserts:

- maybe_record_flag validates -> consent-checks -> increments the per-week
  counter (the Phase-01 `pass` is gone);
- counters reset on a successful weekly send;
- a send overlapping a ritual within 24h defers (RitualCouplingDebounceTriggered);
- a send > 24h after the last ritual proceeds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from envoy.heartbeat.client import HeartbeatClient, OptOutConsentGate
from envoy.heartbeat.errors import RitualCouplingDebounceTriggered
from envoy.heartbeat.star_prio import StarPrioClient


class _Clock:
    """A deterministic, advanceable clock — a Protocol adapter, not a mock."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


class TestL01RitualDebounce:
    def _client(self, clock: _Clock) -> HeartbeatClient:
        return HeartbeatClient(
            consent_gate=OptOutConsentGate(granted=True),
            star_client=StarPrioClient(submitter_id="install-l01"),
            now=clock,
        )

    def test_maybe_record_flag_increments_per_week_counter(self) -> None:
        clock = _Clock(datetime(2026, 6, 15, tzinfo=timezone.utc))
        client = self._client(clock)
        client.maybe_record_flag("completed_boundary_conversation")
        client.maybe_record_flag("completed_boundary_conversation")
        client.maybe_record_flag("opened_daily_digest_this_week")
        assert client._counters["completed_boundary_conversation"] == 2
        assert client._counters["opened_daily_digest_this_week"] == 1

    def test_counters_reset_on_successful_send(self) -> None:
        clock = _Clock(datetime(2026, 6, 15, tzinfo=timezone.utc))
        client = self._client(clock)
        client.maybe_record_flag("completed_weekly_posture_review")
        assert client._counters
        client.emit_weekly()
        # Counters reset on a successful send (`spec § Cadence`).
        assert client._counters == {}

    def test_send_within_24h_of_ritual_defers(self) -> None:
        ritual_at = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        clock = _Clock(ritual_at)
        client = self._client(clock)
        client.record_ritual(ritual_at)
        client.maybe_record_flag("grant_moment_novelty_approved")
        # Advance 12h — still inside the 24h debounce window.
        clock.advance(timedelta(hours=12))
        with pytest.raises(RitualCouplingDebounceTriggered) as exc:
            client.emit_weekly()
        assert "24h" in str(exc.value)
        # Counters are RETAINED for the next cycle (the whole cycle deferred).
        assert client._counters["grant_moment_novelty_approved"] == 1

    def test_send_after_24h_proceeds(self) -> None:
        ritual_at = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        clock = _Clock(ritual_at)
        client = self._client(clock)
        client.record_ritual(ritual_at)
        client.maybe_record_flag("posture_delegating_active")
        # Advance 25h — past the debounce window.
        clock.advance(timedelta(hours=25))
        shares = client.emit_weekly()
        assert {s.metric for s in shares} == {"posture_delegating_active"}
        assert client._counters == {}

    def test_opt_out_user_is_effective_no_op(self) -> None:
        """An opt-out user (default consent gate) accrues nothing — Phase-01 contract."""
        clock = _Clock(datetime(2026, 6, 15, tzinfo=timezone.utc))
        client = HeartbeatClient(
            consent_gate=OptOutConsentGate(granted=False),
            star_client=StarPrioClient(submitter_id="install-optout"),
            now=clock,
        )
        result = client.maybe_record_flag("enterprise_mode_active")
        assert result is None
        assert client._counters == {}
        assert client.emit_weekly() == []

    def test_unknown_flag_is_silent_no_op(self) -> None:
        """An out-of-schema flag never crashes the emit site and is never counted."""
        clock = _Clock(datetime(2026, 6, 15, tzinfo=timezone.utc))
        client = self._client(clock)
        assert client.maybe_record_flag("not_a_real_flag") is None
        assert client._counters == {}
