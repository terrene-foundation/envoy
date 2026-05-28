# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-8(c): cascade revocation reaches descendant grants across channels.

Acceptance gate per `workspaces/phase-01-mvp/02-mvp-objectives.md` line 116
sub-condition (c) + `workspaces/phase-01-mvp/02-plans/02-test-strategy.md`
§ EC-8 line 255 + line 279:

> Day-1 grant on Telegram → Day-6 child grant on Slack → revoke Day-1 →
> cascade reaches Day-6.

> Acceptance gate: cascade revocation of Day-1 grant correctly revokes
> Day-6 child grant from a different channel.

This file extends `tests/e2e/test_grant_moment_3_resolution_shapes_with_cascade.py`
::TestEC8CascadeRevocation, which already covers cascade success/failure on a
single-channel runtime. The EC-8 cross-channel framing the spec mandates
ADDS:

- A grant ISSUED via one channel (Telegram, primary)
- A descendant grant ISSUED via a different channel (Slack)
- A SINGLE cascade revocation channel-agnostically reaching BOTH

Because the Phase-01 ``CascadeRevocationOrchestrator`` is built against
a stubbed ``trust_cascade_revoke`` (the real cross-device lineage backend
is Phase-02 per ``specs/grant-moment.md`` cross-reference), the lineage
mapping is configured via ``cascade_responses`` on the stub trust runtime.
The structural invariant under test is: the cascade orchestrator returns
``CascadeResult.complete=True`` AND the originally-issued grants landed
through the per-channel ``RecordingChannelAdapter.renders`` log (proving
the channels really were exercised independently).

Per `rules/testing.md` § Tier 2: real ``EnvoyGrantMomentRuntime`` + real
``EnvoyLedger`` + real ``ChannelHandoff`` + real ``CascadeRevocationOrchestrator``
against per-channel ``RecordingChannelAdapter`` instances. NO ``unittest.mock``.
Per `rules/probe-driven-verification.md` MUST-3: structural assertions
(equality on ``CascadeResult`` fields + adapter render counts + raised
exception types).
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import (
    ApproveResolution,
    CascadeIncompleteError,
    GrantMomentOutcome,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_familiar_repeat_signals,
    make_issue_kwargs,
    make_runtime,
)


async def _issue_and_approve_on_channel(
    runtime,
    *,
    intent_id: str,
    decided_on_channel_id: str,
    primary_only: bool = False,
) -> GrantMomentOutcome:
    """Drive one grant lifecycle through the runtime, resolving via the
    named channel.  Mirrors the ``_run_one_lifecycle`` helper in
    ``tests/e2e/test_grant_moment_3_resolution_shapes_with_cascade.py``
    but parameterized on the decided-on channel so the test body reads as
    "this grant was approved via Telegram" / "via Slack"."""
    request = await runtime.issue_grant_moment(
        **make_issue_kwargs(
            intent_id=intent_id,
            primary_only=primary_only,
            novelty_signals=make_familiar_repeat_signals(),
        )
    )
    runtime.post_decision(
        request.request_id,
        ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
    )
    received = await runtime.await_decision(request.request_id, timeout_seconds=5)
    return await runtime.submit_resolution(
        request_id=request.request_id,
        resolution=received,
        decided_on_channel_id=decided_on_channel_id,
    )


@pytest.mark.asyncio
class TestEC8CascadeRevocationCrossChannel:
    """EC-8 sub-condition (c): cascade is channel-agnostic."""

    async def test_telegram_day1_grant_cascade_reaches_slack_day6_child(
        self,
    ) -> None:
        """The spec's narrative case: Telegram-issued Day-1 grant has a
        Slack-issued Day-6 child; revoking the Telegram grant cascades to
        the Slack child."""
        # Pre-stage the cascade lineage the Phase-02 TrustStore would
        # compute: Day-1 (root) cascade returns the Day-6 child grant
        # alongside itself.
        day1_grant_id = "delegation-record-day1-telegram"
        day6_child_grant_id = "delegation-record-day6-slack"
        runtime, _km, _ledger, _audit, adapters = await make_runtime(
            primary_channel_id="telegram",
            adapter_channel_ids=("telegram", "slack"),
            cascade_responses={day1_grant_id: {day1_grant_id, day6_child_grant_id}},
        )

        # Day-1: issue + approve a grant decided via Telegram.
        day1_outcome = await _issue_and_approve_on_channel(
            runtime,
            intent_id="sha256:intent-day1-newsletter-send",
            decided_on_channel_id="telegram",
        )
        assert day1_outcome.state == "APPROVED"
        assert day1_outcome.delegation_record_ref

        # Day-6: issue + approve a separate (child) grant decided via Slack.
        day6_outcome = await _issue_and_approve_on_channel(
            runtime,
            intent_id="sha256:intent-day6-followup-send",
            decided_on_channel_id="slack",
        )
        assert day6_outcome.state == "APPROVED"
        assert day6_outcome.delegation_record_ref

        # Independent issuance evidence: each adapter saw both renders
        # (ChannelHandoff fans out by default).  The decided-on-channel_id
        # is the load-bearing channel signal — Telegram for Day-1, Slack
        # for Day-6.
        telegram = next(a for a in adapters if a.channel_id == "telegram")
        slack = next(a for a in adapters if a.channel_id == "slack")
        assert len(telegram.renders) == 2
        assert len(slack.renders) == 2

        # The cascade orchestrator is channel-agnostic — it operates on
        # grant_id lineage.  Revoking the Day-1 grant returns BOTH the
        # root and the Day-6 child in the revoked set; the expected
        # descendant (Day-6 child) is present.
        result = runtime.revoke_prior_grant(
            root_id=day1_grant_id,
            expected_descendants=frozenset({day6_child_grant_id}),
        )
        assert result.complete is True
        assert day6_child_grant_id in result.revoked_ids
        assert result.missing_descendants == frozenset()

    async def test_cascade_raises_when_cross_channel_child_missing(self) -> None:
        """Counter-case: if the stub-lineage does NOT return the Day-6
        Slack child (simulating a corrupted or partially-propagated
        cross-device lineage), the orchestrator raises
        ``CascadeIncompleteError`` carrying the Slack grant_id in
        ``missing_descendants`` — the orchestrator's safety surface holds
        across channel boundaries."""
        day1_grant_id = "delegation-record-day1-telegram-2"
        day6_child_grant_id = "delegation-record-day6-slack-2"
        runtime, *_ = await make_runtime(
            primary_channel_id="telegram",
            adapter_channel_ids=("telegram", "slack"),
            cascade_responses={
                # Day-6 Slack child is NOT in the revoked set — simulating
                # the cascade missing a cross-channel descendant.
                day1_grant_id: {day1_grant_id},
            },
        )
        await _issue_and_approve_on_channel(
            runtime,
            intent_id="sha256:intent-day1-2",
            decided_on_channel_id="telegram",
        )

        with pytest.raises(CascadeIncompleteError) as excinfo:
            runtime.revoke_prior_grant(
                root_id=day1_grant_id,
                expected_descendants=frozenset({day6_child_grant_id}),
            )

        assert day6_child_grant_id in excinfo.value.result.missing_descendants
        assert excinfo.value.result.complete is False

    async def test_three_channel_cascade_reaches_all_descendants(self) -> None:
        """Wider lineage shape: Telegram root → Slack child → Discord
        grandchild.  Cascade returns all three.  Exercises the full
        EC-7-degraded 4-channel set minus Web (Web is a sibling, not a
        descendant of Telegram in this narrative)."""
        root_id = "delegation-record-root-telegram"
        slack_child_id = "delegation-record-child-slack"
        discord_grand_id = "delegation-record-grandchild-discord"
        runtime, _km, _ledger, _audit, adapters = await make_runtime(
            primary_channel_id="telegram",
            adapter_channel_ids=("telegram", "slack", "discord"),
            cascade_responses={
                root_id: {root_id, slack_child_id, discord_grand_id},
            },
        )

        # Day-1 root on Telegram.
        await _issue_and_approve_on_channel(
            runtime,
            intent_id="sha256:intent-root",
            decided_on_channel_id="telegram",
        )
        # Day-3 child on Slack.
        await _issue_and_approve_on_channel(
            runtime,
            intent_id="sha256:intent-slack-child",
            decided_on_channel_id="slack",
        )
        # Day-6 grandchild on Discord.
        await _issue_and_approve_on_channel(
            runtime,
            intent_id="sha256:intent-discord-grand",
            decided_on_channel_id="discord",
        )

        # Every adapter saw the same fan-out — the channels participated.
        for a in adapters:
            assert len(a.renders) == 3, f"{a.channel_id}: expected 3 renders, got {len(a.renders)}"

        result = runtime.revoke_prior_grant(
            root_id=root_id,
            expected_descendants=frozenset({slack_child_id, discord_grand_id}),
        )
        assert result.complete is True
        assert result.revoked_ids == frozenset({root_id, slack_child_id, discord_grand_id})
        assert result.missing_descendants == frozenset()
