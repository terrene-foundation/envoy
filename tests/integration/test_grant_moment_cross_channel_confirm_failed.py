"""Tier-2: CrossChannelConfirmFailedError runtime raise paths.

Per `specs/grant-moment.md` § Error taxonomy: ``CrossChannelConfirmFailedError``
fires when a high-stakes Grant Moment's cross-channel confirm leg is missing
OR collapsed (same channel as ``decided_on_channel_id`` defeats the defense).

This file covers the 10th error in the spec taxonomy — analyst-R1 HIGH-1
flagged that the contract-pin (wire-shape) test lives in tier-1 but the
runtime raise path was uncovered.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import (
    ApproveResolution,
    CrossChannelConfirmFailedError,
    FRICTION_TOKEN_READ_DELAY_COMPLETE,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_high_stakes_signals,
    make_issue_kwargs,
    make_runtime,
)


@pytest.mark.asyncio
class TestCrossChannelConfirmFailed:
    async def test_high_stakes_without_confirm_call_raises_at_m3(self) -> None:
        runtime, *_ = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web"),
            novelty_read_delay_seconds=0.0,
        )
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_high_stakes_signals())
        )
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_READ_DELAY_COMPLETE)
        # NOTE: no confirm_cross_channel call — the confirm leg is missing.
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
        assert isinstance(outcome.error, CrossChannelConfirmFailedError)

    async def test_confirm_channel_same_as_decided_collapses_defense(self) -> None:
        # Security-R1 MED-2: a confirm leg on the SAME channel as the
        # decided channel defeats the cross-channel intent entirely. The
        # runtime detects + refuses.
        runtime, *_ = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web"),
            novelty_read_delay_seconds=0.0,
        )
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_high_stakes_signals())
        )
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_READ_DELAY_COMPLETE)
        runtime.confirm_cross_channel(request.request_id, confirm_channel_id="cli")  # same!
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
        assert isinstance(outcome.error, CrossChannelConfirmFailedError)
        assert outcome.error.confirm_channel_id == "cli"

    async def test_confirm_channel_unknown_raises_value_error_at_call_time(self) -> None:
        runtime, *_ = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web"),
            novelty_read_delay_seconds=0.0,
        )
        request = await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_high_stakes_signals())
        )
        # 'imessage' is not a configured channel — refuse loudly.
        with pytest.raises(ValueError, match="not one of the configured channels"):
            runtime.confirm_cross_channel(request.request_id, confirm_channel_id="imessage")

    async def test_high_stakes_with_proper_cross_channel_confirm_succeeds(self) -> None:
        runtime, *_ = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web"),
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
            decided_on_channel_id="cli",  # primary, ≠ confirm
        )
        assert outcome.state == "APPROVED"
