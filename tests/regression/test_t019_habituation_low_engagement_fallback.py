"""Regression — T-019 habituation defense via low-engagement fallback.

Per `specs/daily-digest.md` § Provenance ("Threats mitigated: T-019
habituation defense via low-engagement fallback") + § Low-engagement fallback
(line 29) + `specs/threat-model.md` T-019.

Threat T-019: a user habituates to the daily digest and stops engaging, so a
malicious or noisy digest stream goes unread — notification fatigue erodes the
ritual's value. The defense: when opens fall below 2/week sustained over 3
weeks, the digest downgrades to the `compact` form (and Phase-02 offers
event-only delivery), reducing the cadence's noise.

This regression pins the threshold boundary so a future refactor of
`LowEngagementTracker` cannot silently widen the engagement window or lower
the threshold (which would re-expose the habituation surface).

Per `rules/testing.md` § Regression Testing: never deleted; reproduces the
mitigation contract. Real TrustStoreAdapter (no mocks).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from envoy.daily_digest.engagement import LowEngagementTracker
from envoy.trust.store import TrustStoreAdapter

_UTC = timezone.utc
_PID = "principal-t019-01"
_NOW = datetime(2026, 5, 27, 8, 0, tzinfo=_UTC)


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "trust_vault.db"


async def _tracker(vault_path) -> tuple[LowEngagementTracker, TrustStoreAdapter]:
    store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
    await store.initialize()
    return LowEngagementTracker(trust_store=store), store


@pytest.mark.regression
@pytest.mark.asyncio
async def test_t019_below_threshold_downgrades_to_compact(vault_path) -> None:
    """<2 opens/week × 3 weeks (i.e. <6 in 21 days) → compact (T-019)."""
    tracker, store = await _tracker(vault_path)
    try:
        # 5 opens in the window — one short of the 6-open threshold.
        for d in range(1, 6):
            await tracker.record_open(_PID, opened_at=_NOW - timedelta(days=d))
        assert await tracker.select_form(_PID, now=_NOW) == "compact"
    finally:
        await store.close()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_t019_at_threshold_stays_rich(vault_path) -> None:
    """Exactly 6 opens in 21 days meets the threshold → rich (no over-trigger)."""
    tracker, store = await _tracker(vault_path)
    try:
        for d in range(1, 7):
            await tracker.record_open(_PID, opened_at=_NOW - timedelta(days=d * 3))
        assert await tracker.select_form(_PID, now=_NOW) == "rich"
    finally:
        await store.close()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_t019_opens_older_than_window_do_not_count(vault_path) -> None:
    """Opens >21 days ago MUST NOT count — the window cannot silently widen."""
    tracker, store = await _tracker(vault_path)
    try:
        # 10 opens, all older than 21 days → none count → compact.
        for d in range(10):
            await tracker.record_open(_PID, opened_at=_NOW - timedelta(days=22 + d))
        assert await tracker.select_form(_PID, now=_NOW) == "compact"
    finally:
        await store.close()


@pytest.mark.regression
def test_t019_threshold_constants_pinned() -> None:
    """Pin the threshold constants — a refactor lowering them re-exposes T-019."""
    assert LowEngagementTracker.LOW_OPEN_THRESHOLD_PER_WEEK == 2
    assert LowEngagementTracker.LOW_ENGAGEMENT_WEEKS == 3
