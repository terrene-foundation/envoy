"""Regression: T-093 velocity-raise 24h cooling-off (R2-H4 ratchet).

Contract pin: T-093 R2-H4 (velocity-raise ratchet).

Per `specs/grant-moment.md` § Velocity-raise ratchet (T-093 R2-H4): raising
velocity limits CANNOT be approved inline. The runtime enforces a 24h
cooling-off window between velocity-raise approvals; in-window attempts
raise ``VelocityRaiseCoolingOffError``.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import (
    ApproveResolution,
    VelocityRaiseCoolingOffError,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_issue_kwargs,
    make_runtime,
)


@pytest.mark.regression
@pytest.mark.asyncio
class TestT093VelocityRaiseCoolingOff:
    """Contract pin: T-093 R2-H4."""

    async def test_first_velocity_raise_succeeds(self) -> None:
        # No prior velocity-raise approval → no cooling-off block on the
        # first one. Sanity check that the gate fires only on REPEAT.
        runtime, *_ = await make_runtime()
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(
                is_velocity_raise=True, why_asking="velocity_raise", tool_name="raise_limit"
            )
        )
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

    async def test_second_velocity_raise_within_cooling_off_raises(self) -> None:
        # First velocity-raise approval registers the cool-off start; the
        # second attempt within the window raises.
        runtime, *_ = await make_runtime(velocity_raise_cooling_off_seconds=3600)

        first = await runtime.issue_grant_moment(
            **make_issue_kwargs(
                is_velocity_raise=True, why_asking="velocity_raise", tool_name="raise_limit"
            )
        )
        runtime.post_decision(
            first.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        first_resolution = await runtime.await_decision(first.request_id, timeout_seconds=5)
        await runtime.submit_resolution(
            request_id=first.request_id,
            resolution=first_resolution,
            decided_on_channel_id="cli",
        )

        with pytest.raises(VelocityRaiseCoolingOffError) as exc:
            await runtime.issue_grant_moment(
                **make_issue_kwargs(
                    is_velocity_raise=True,
                    why_asking="velocity_raise",
                    tool_name="raise_limit",
                )
            )

        # Plain-language message names the wait window + alternative.
        assert "Posture Review" in str(exc.value)
        # Required-seconds matches the configured cooling-off.
        assert exc.value.required_seconds == 3600

    async def test_velocity_raise_after_cooling_off_succeeds(self) -> None:
        # Configure cooling-off as 0 seconds so the second raise lands.
        runtime, *_ = await make_runtime(velocity_raise_cooling_off_seconds=0)

        first = await runtime.issue_grant_moment(
            **make_issue_kwargs(
                is_velocity_raise=True, why_asking="velocity_raise", tool_name="raise_limit"
            )
        )
        runtime.post_decision(
            first.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        resolution = await runtime.await_decision(first.request_id, timeout_seconds=5)
        await runtime.submit_resolution(
            request_id=first.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )

        # Second raise — cooling-off elapsed (0s).
        second = await runtime.issue_grant_moment(
            **make_issue_kwargs(
                is_velocity_raise=True, why_asking="velocity_raise", tool_name="raise_limit"
            )
        )
        runtime.post_decision(
            second.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        resolution = await runtime.await_decision(second.request_id, timeout_seconds=5)
        outcome = await runtime.submit_resolution(
            request_id=second.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )
        assert outcome.state == "APPROVED"

    async def test_non_velocity_raise_does_not_trigger_cooling_off(self) -> None:
        # The cooling-off ratchet fires ONLY on the velocity_raise axis.
        # Regular grants approved adjacent to a velocity-raise must still
        # land cleanly.
        runtime, *_ = await make_runtime(velocity_raise_cooling_off_seconds=3600)

        # First, a velocity-raise to seed the cool-off start.
        vr = await runtime.issue_grant_moment(
            **make_issue_kwargs(
                is_velocity_raise=True, why_asking="velocity_raise", tool_name="raise_limit"
            )
        )
        runtime.post_decision(
            vr.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        await runtime.submit_resolution(
            request_id=vr.request_id,
            resolution=await runtime.await_decision(vr.request_id, timeout_seconds=5),
            decided_on_channel_id="cli",
        )

        # Now a normal grant — cool-off is velocity-raise-axis-only; this
        # MUST succeed.
        regular = await runtime.issue_grant_moment(**make_issue_kwargs())
        runtime.post_decision(
            regular.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        outcome = await runtime.submit_resolution(
            request_id=regular.request_id,
            resolution=await runtime.await_decision(regular.request_id, timeout_seconds=5),
            decided_on_channel_id="cli",
        )
        assert outcome.state == "APPROVED"

    async def test_declined_velocity_raise_does_not_advance_the_ratchet(self) -> None:
        # Spec invariant: the ratchet's start point is the APPROVED
        # velocity-raise, not the attempted one. A user who DECLINES a
        # velocity-raise can immediately re-attempt without cooling-off.
        from envoy.grant_moment import DeclineResolution

        runtime, *_ = await make_runtime(velocity_raise_cooling_off_seconds=3600)

        first = await runtime.issue_grant_moment(
            **make_issue_kwargs(
                is_velocity_raise=True, why_asking="velocity_raise", tool_name="raise_limit"
            )
        )
        runtime.post_decision(
            first.request_id,
            DeclineResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        await runtime.submit_resolution(
            request_id=first.request_id,
            resolution=await runtime.await_decision(first.request_id, timeout_seconds=5),
            decided_on_channel_id="cli",
        )

        # Second raise — ratchet should NOT be engaged because the first
        # was declined.
        await runtime.issue_grant_moment(
            **make_issue_kwargs(
                is_velocity_raise=True, why_asking="velocity_raise", tool_name="raise_limit"
            )
        )
