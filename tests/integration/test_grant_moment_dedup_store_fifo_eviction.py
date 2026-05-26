"""Tier-2: dedup-store FIFO eviction bounds memory under sustained load.

Per `rules/trust-plane-security.md` Rule 4 (Bounded Collections): the
runtime's ``_seen_nonces`` / ``_seen_intent_ids`` stores are bounded via
``dedup_store_ceiling`` with FIFO eviction. T-008 replay defense remains
in force for the most-recent ``ceiling`` entries; the oldest are evicted.

This regression file (security-R2 LOW-3) closes the test coverage gap on
the bounded-collection invariant.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import GrantMomentReplayError
from tests.helpers.grant_moment_harness import make_issue_kwargs, make_runtime


@pytest.mark.regression
@pytest.mark.asyncio
class TestDedupStoreFifoEviction:
    """Bounded-collection invariant per trust-plane-security.md Rule 4."""

    async def test_eviction_at_ceiling_releases_oldest_nonce(self) -> None:
        # Ceiling 3 — the 4th issued nonce evicts the 1st.
        runtime, *_ = await make_runtime(dedup_store_ceiling=3, queue_ceiling=10)

        nonces = [f"nonce-{i:04d}" for i in range(4)]
        for nonce in nonces:
            await runtime.issue_grant_moment(**make_issue_kwargs(nonce=nonce))

        # First-issued nonce was evicted at the 4th insert; re-using it
        # MUST succeed (no GrantMomentReplayError).
        await runtime.issue_grant_moment(**make_issue_kwargs(nonce=nonces[0]))

    async def test_non_evicted_nonces_still_replay_defended(self) -> None:
        # Ceiling 3 — entries [-1, -2, -3] retained; entries [-4, -5, ...]
        # evicted. The MOST RECENT three must still raise on re-use.
        runtime, *_ = await make_runtime(dedup_store_ceiling=3, queue_ceiling=10)

        nonces = [f"nonce-{i:04d}" for i in range(4)]
        for nonce in nonces:
            await runtime.issue_grant_moment(**make_issue_kwargs(nonce=nonce))

        # Most-recent 3 (indices 1, 2, 3) are still in the store.
        for idx in (1, 2, 3):
            with pytest.raises(GrantMomentReplayError):
                await runtime.issue_grant_moment(**make_issue_kwargs(nonce=nonces[idx]))

    async def test_intent_id_axis_evicts_independently_of_nonce(self) -> None:
        # The intent_id axis is a separate dedup store with its own
        # ceiling. Filling one axis must not impact the other.
        runtime, *_ = await make_runtime(dedup_store_ceiling=2, queue_ceiling=10)

        # Issue 3 grants → both axes evict their oldest entries (idx 0).
        for i in range(3):
            await runtime.issue_grant_moment(
                **make_issue_kwargs(nonce=f"nonce-{i}", intent_id=f"sha256:intent-{i}")
            )

        # The 0th intent_id should be evicted from intent-axis store.
        # Re-using it must succeed (with a fresh nonce so the nonce axis
        # is also unique).
        await runtime.issue_grant_moment(
            **make_issue_kwargs(nonce="nonce-fresh", intent_id="sha256:intent-0")
        )

    async def test_invalid_ceiling_at_construction_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="dedup_store_ceiling"):
            await make_runtime(dedup_store_ceiling=0)
        with pytest.raises(ValueError, match="dedup_store_ceiling"):
            await make_runtime(dedup_store_ceiling=-1)
