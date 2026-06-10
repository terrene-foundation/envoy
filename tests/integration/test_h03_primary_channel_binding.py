"""Tier-2: H-03 primary-channel binding raised at M3 sign-or-decline.

Per `specs/grant-moment.md` § Error taxonomy: ``NotPrimaryChannelError`` fires
when a high-stakes ``GrantMomentResult`` arrives from a non-primary
``decided_on_channel_id``. This is the M3 raise path; the M1 dispatch surface
uses structural ``HandoffPlan.refused_channels`` records instead (covered in
``tests/tier1/test_grant_moment_channel_handoff.py``).

Layer attribution per `envoy/grant_moment/errors.py` § "Layer attribution".
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import (
    FRICTION_TOKEN_READ_DELAY_COMPLETE,
    ApproveResolution,
    NotPrimaryChannelError,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_high_stakes_signals,
    make_issue_kwargs,
    make_runtime,
)


@pytest.mark.asyncio
class TestH03PrimaryChannelBinding:
    async def test_high_stakes_decided_on_non_primary_raises_at_m3(self) -> None:
        runtime, *_ = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web"),  # web is the confirm-leg channel
            novelty_read_delay_seconds=0.0,
        )
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_high_stakes_signals())
        )

        # Acknowledge friction so the H-03 check is the load-bearing barrier.
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_READ_DELAY_COMPLETE)
        runtime.confirm_cross_channel(request.request_id, confirm_channel_id="web")

        runtime.post_decision(
            request.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)

        outcome = await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="web",  # NOT the primary
        )
        assert outcome.state == "ERROR"
        assert isinstance(outcome.error, NotPrimaryChannelError)
        assert outcome.error.channel_id == "web"
        assert outcome.error.primary_channel_id == "cli"

    async def test_high_stakes_decided_on_primary_succeeds(self) -> None:
        runtime, *_ = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web"),  # web is the confirm-leg channel
            novelty_read_delay_seconds=0.0,
        )
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_high_stakes_signals())
        )
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_READ_DELAY_COMPLETE)
        runtime.confirm_cross_channel(request.request_id, confirm_channel_id="web")
        runtime.post_decision(
            request.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)

        outcome = await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )
        assert outcome.state == "APPROVED"
        assert outcome.error is None

    async def test_low_stakes_decided_on_non_primary_is_allowed(self) -> None:
        # H-03 is high-stakes-only; low-stakes grants may be approved on
        # any active channel.
        runtime, *_ = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web"),
            novelty_read_delay_seconds=0.0,
        )
        request = await runtime.issue_grant_moment(**make_issue_kwargs())

        runtime.post_decision(
            request.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)

        outcome = await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="web",
        )
        assert outcome.state == "APPROVED"
