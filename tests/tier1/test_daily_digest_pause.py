"""Tier 1 — T-04-82 — PauseDisableState (Trust-store-backed, restart-safe).

Source: T-04-82 per `workspaces/phase-01-mvp/todos/active/04-wave-4-channels-
digest.md` § T-04-82 + shard 11 § 3 step 5.

Coverage:
1. pause / is_paused / resume round-trip.
2. Pause auto-lifts after the window (expired window → is_paused False).
3. Restart-safety: a fresh TrustStoreAdapter against the same vault path
   reads the persisted pause state (state survives close-and-reopen).
4. skip-too-long boundary (>30 days since paused_at).

Per `rules/testing.md` Tier 2 contract for the persistence path: this uses a
REAL TrustStoreAdapter against a real on-disk SQLite vault (tmp_path), not a
mock — the restart-safety invariant can only be verified against real
persistence. Tier-1-located because it needs no external network/daemon.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from envoy.daily_digest.pause import PauseDisableState
from envoy.trust.store import TrustStoreAdapter

_UTC = timezone.utc
_PID = "principal-pausetest-01"


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "trust_vault.db"


async def _store(vault_path) -> TrustStoreAdapter:
    store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
    await store.initialize()
    return store


class TestPauseRoundTrip:
    @pytest.mark.asyncio
    async def test_pause_then_is_paused(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            state = PauseDisableState(trust_store=store)
            now = datetime.now(tz=_UTC)
            assert await state.is_paused(_PID, now=now) is False
            await state.pause(_PID, duration_days=7)
            assert await state.is_paused(_PID, now=now) is True
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_resume_clears_pause(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            state = PauseDisableState(trust_store=store)
            now = datetime.now(tz=_UTC)
            await state.pause(_PID, duration_days=7)
            await state.resume(_PID)
            assert await state.is_paused(_PID, now=now) is False
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_pause_auto_lifts_after_window(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            state = PauseDisableState(trust_store=store)
            await state.pause(_PID, duration_days=7)
            # 8 days later — the 7-day window has expired.
            future = datetime.now(tz=_UTC) + timedelta(days=8)
            assert await state.is_paused(_PID, now=future) is False
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_zero_duration_rejected(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            state = PauseDisableState(trust_store=store)
            with pytest.raises(ValueError, match="duration_days"):
                await state.pause(_PID, duration_days=0)
        finally:
            await store.close()


class TestRestartSafety:
    @pytest.mark.asyncio
    async def test_pause_survives_store_reopen(self, vault_path) -> None:
        """The defining T-04-82 invariant: pause persists across restart."""
        store1 = await _store(vault_path)
        try:
            await PauseDisableState(trust_store=store1).pause(_PID, duration_days=7)
        finally:
            await store1.close()

        # Fresh adapter against the SAME vault path — simulates process restart.
        store2 = await _store(vault_path)
        try:
            state2 = PauseDisableState(trust_store=store2)
            now = datetime.now(tz=_UTC)
            assert await state2.is_paused(_PID, now=now) is True
        finally:
            await store2.close()


class TestSkipTooLong:
    @pytest.mark.asyncio
    async def test_skip_too_long_boundary(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            state = PauseDisableState(trust_store=store)
            await state.pause(_PID, duration_days=7)
            now = datetime.now(tz=_UTC)
            # Just paused — not skip-too-long.
            assert await state.is_skip_too_long(_PID, now=now) is False
            # 31 days later — exceeds the 30-day threshold.
            future = now + timedelta(days=31)
            assert await state.is_skip_too_long(_PID, now=future) is True
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_not_paused_is_not_skip_too_long(self, vault_path) -> None:
        store = await _store(vault_path)
        try:
            state = PauseDisableState(trust_store=store)
            now = datetime.now(tz=_UTC)
            assert await state.is_skip_too_long(_PID, now=now) is False
        finally:
            await store.close()
