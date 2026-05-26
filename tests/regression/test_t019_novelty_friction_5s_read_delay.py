"""Regression: T-019 novelty friction 5s read-delay (runtime enforcer).

Contract pin: T-019 (novelty-aware friction / habituation defense).

Per `specs/grant-moment.md` § Novelty-aware friction (T-019): novel-pattern
Grant Moments require a 5s read-delay + double-tap; high-stakes adds a
cross-channel confirm leg. The runtime enforces all three; bypass attempts
surface ``NoveltyFrictionRequiredError``.
"""

from __future__ import annotations

import asyncio

import pytest

from envoy.grant_moment import (
    ApproveResolution,
    FRICTION_TOKEN_DOUBLE_TAP,
    FRICTION_TOKEN_READ_DELAY_COMPLETE,
    NoveltyFrictionRequiredError,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_issue_kwargs,
    make_novel_signals,
    make_runtime,
)


@pytest.mark.regression
@pytest.mark.asyncio
class TestT019NoveltyFriction:
    """Contract pin: T-019."""

    async def test_novel_pattern_blocks_immediate_signing(self) -> None:
        # Read-delay window > 0; immediate sign attempt is refused.
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=0.05)
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_novel_signals())
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
        assert outcome.state == "ERROR"
        assert isinstance(outcome.error, NoveltyFrictionRequiredError)
        assert outcome.error.friction_kind == NoveltyFrictionRequiredError.KIND_READ_DELAY_WALLCLOCK

    async def test_novel_pattern_blocks_when_read_delay_token_missing(self) -> None:
        # After the wall-clock read-delay elapses, the token must still be
        # explicitly acknowledged. This ensures the UX actually rendered +
        # waited — wall-clock alone is insufficient.
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=0.01)
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_novel_signals())
        )
        await asyncio.sleep(0.05)  # past the read-delay window

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
        assert outcome.state == "ERROR"
        assert isinstance(outcome.error, NoveltyFrictionRequiredError)
        assert (
            outcome.error.friction_kind
            == NoveltyFrictionRequiredError.KIND_READ_DELAY_TOKEN_MISSING
        )

    async def test_novel_pattern_blocks_when_double_tap_token_missing(self) -> None:
        # Read-delay ack present, but double-tap missing → still blocked.
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=0.0)
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_novel_signals())
        )
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_READ_DELAY_COMPLETE)
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
        assert outcome.state == "ERROR"
        assert isinstance(outcome.error, NoveltyFrictionRequiredError)
        assert outcome.error.friction_kind == NoveltyFrictionRequiredError.KIND_DOUBLE_TAP_MISSING

    async def test_full_friction_sequence_allows_signing(self) -> None:
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=0.0)
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_novel_signals())
        )
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_READ_DELAY_COMPLETE)
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_DOUBLE_TAP)
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

    async def test_familiar_repeat_has_no_friction_requirement(self) -> None:
        # NoveltyClass.FAMILIAR_REPEAT bypasses the friction enforcer
        # entirely — there is no habituation risk on a known-good pattern.
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=5.0)
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
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

    async def test_decline_path_bypasses_friction_check(self) -> None:
        # Decline (refusal) is structurally safe — the friction enforcer
        # exists to slow APPROVAL of novel grants, not refusal. A user
        # declining a suspicious novel grant should not be forced through
        # the full friction sequence.
        from envoy.grant_moment import DeclineResolution

        runtime, *_ = await make_runtime(novelty_read_delay_seconds=5.0)
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_novel_signals())
        )
        runtime.post_decision(
            request.request_id,
            DeclineResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)

        outcome = await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )
        assert outcome.state == "DECLINED"
