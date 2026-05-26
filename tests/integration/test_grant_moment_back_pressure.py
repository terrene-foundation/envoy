"""Tier-2: N-parallel queue ceiling behavior per spec § Timeout.

"Queue back-pressure after N parallel Grant Moments" — when concurrent
in-flight grants exceed the configured ceiling, ``issue_grant_moment`` raises
``BackPressureQueueFullError`` rather than dispatching the (N+1)th grant.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import (
    ApproveResolution,
    BackPressureQueueFullError,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_issue_kwargs,
    make_runtime,
)


@pytest.mark.asyncio
class TestQueueCeiling:
    async def test_first_N_grants_fit_under_ceiling(self) -> None:
        runtime, *_ = await make_runtime(queue_ceiling=3)
        for _ in range(3):
            await runtime.issue_grant_moment(**make_issue_kwargs())
        assert runtime.inflight_count() == 3

    async def test_ceiling_plus_one_raises_back_pressure_error(self) -> None:
        runtime, *_ = await make_runtime(queue_ceiling=2)
        await runtime.issue_grant_moment(**make_issue_kwargs())
        await runtime.issue_grant_moment(**make_issue_kwargs())

        with pytest.raises(BackPressureQueueFullError) as exc:
            await runtime.issue_grant_moment(**make_issue_kwargs())

        assert exc.value.queue_ceiling == 2
        assert exc.value.queue_depth == 2
        # The refused grant did NOT pollute the dedup store — the nonce
        # remains available so the user can re-issue after a slot opens.
        assert runtime.inflight_count() == 2

    async def test_completing_a_grant_frees_a_queue_slot(self) -> None:
        runtime, *_ = await make_runtime(queue_ceiling=2)
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        await runtime.issue_grant_moment(**make_issue_kwargs())
        assert runtime.inflight_count() == 2

        # Complete the first grant; the slot should free.
        runtime.post_decision(
            request.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)
        await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )
        assert runtime.inflight_count() == 1

        # A third issue should now fit under the ceiling.
        await runtime.issue_grant_moment(**make_issue_kwargs())
        assert runtime.inflight_count() == 2

    async def test_invalid_ceiling_at_construction_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="queue_ceiling"):
            await make_runtime(queue_ceiling=0)
        with pytest.raises(ValueError, match="queue_ceiling"):
            await make_runtime(queue_ceiling=-1)
