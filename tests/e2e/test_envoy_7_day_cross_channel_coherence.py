# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-8 7-day cross-channel coherence battery.

Acceptance gate per `workspaces/phase-01-mvp/02-mvp-objectives.md` line 116
+ `workspaces/phase-01-mvp/02-plans/02-test-strategy.md` § EC-8 Tier-3 line
260 (day-by-day table) + line 273 (daily cross-channel state-equivalence)
+ line 279 (the three sub-condition acceptance gates a/b/c).

The day-by-day narrative under test (compressed from the spec's 7-day table):

| Day | Action                                          | Channel     | EC-8 assertion                                           |
| --- | ----------------------------------------------- | ----------- | -------------------------------------------------------- |
| 1   | Envelope compiled; grant issued                 | CLI/Telegram | Ledger has 1 ``grant_moment`` row                       |
| 2   | (digest day — state-equivalence query)          | All         | Day-1 grant visible to every channel's query             |
| 3   | Out-of-envelope grant fires + resolved          | Slack       | Ledger has 2 ``grant_moment`` rows                       |
| 4   | (offline; no actions)                           | —           | State preserves; no drift                                |
| 5   | (digest day with back-fill — still queryable)   | All         | All prior rows still in Ledger.query for the full window |
| 6   | Child grant under Day-3                         | Discord     | Ledger has 3 ``grant_moment`` rows                       |
| 7   | Revoke Day-1 via cascade                        | Telegram    | Cascade returns {Day-1, Day-3, Day-6} from the trust runtime |

This battery does NOT re-litigate the daily-digest fire path (covered by
EC-3 in ``test_daily_digest_morning_delivery.py``); it focuses on the
EC-8 invariants the digest path consumes — channel-independent state
equivalence at the Ledger and channel-agnostic cascade across the
7-day operating window.

EC-8(b) no-double-billing is covered by
``tests/tier2/test_budget_no_double_billing_multi_channel.py``; this file
exercises (a) state-equivalence and (c) cross-channel cascade in the
day-by-day shape.

**Scope partitioning (per the security gate-review for shard 13):** the
load-bearing byte-identity assertion (EC-8(a) at the envelope layer) is
in ``tests/tier2/test_envelope_compiler_session_envelope_byte_identity.py``;
the cascade-orchestrator verify-half contract (EC-8(c)) is in
``tests/tier2/test_grant_moment_cascade_cross_channel.py``.  This
battery's per-adapter render-count assertions (~line 195) prove
``ChannelHandoff`` fan-out only — NOT byte-identity of the rendered
surfaces (which is the envelope-layer test's job).  The Day-7 cascade
assertion verifies the orchestrator's verify half given the stub-staged
revoked set; the lineage-graph BFS derivation itself is Phase-02
TrustStore territory and is NOT under test here.

Per `rules/testing.md` § Tier 3: real ``EnvoyGrantMomentRuntime`` + real
``EnvoyLedger`` + real ``ChannelHandoff`` over multiple per-channel
``RecordingChannelAdapter`` instances; every write is verified with a
read-back via ``Ledger.query()`` + ``Ledger.verify_chain()``. Per
`rules/probe-driven-verification.md` MUST-3: structural assertions only
(entry-count integers, frozenset equality, exception types).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from envoy.grant_moment import ApproveResolution, GrantMomentOutcome
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_familiar_repeat_signals,
    make_issue_kwargs,
    make_runtime,
)

_UTC = timezone.utc
_QUERY_SINCE = datetime(2026, 1, 1, tzinfo=_UTC)
_QUERY_UNTIL = datetime(2027, 1, 1, tzinfo=_UTC)
_GRANT_MOMENT_TYPE = "grant_moment"


async def _issue_and_approve(
    runtime,
    *,
    intent_id: str,
    decided_on_channel_id: str,
) -> GrantMomentOutcome:
    """Drive one grant lifecycle through the runtime.

    Mirrors the same shape as ``tests/tier2/test_grant_moment_cascade_cross_channel.py``
    so an audit of the EC-8 surface reads consistently across the Tier-2
    cascade test and this Tier-3 battery.
    """
    request = await runtime.issue_grant_moment(
        **make_issue_kwargs(
            intent_id=intent_id,
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


async def _count_grant_moment_entries(ledger) -> int:
    """The single state-equivalence read every channel performs.

    Returns the total ``grant_moment`` Ledger rows in the 7-day window.
    """
    entries = await ledger.query(
        filter={"event_type": _GRANT_MOMENT_TYPE},
        since=_QUERY_SINCE,
        until=_QUERY_UNTIL,
    )
    return len(entries)


@pytest.mark.asyncio
class TestEC8SevenDayCrossChannelCoherence:
    """The full 7-day battery — state-equivalence + cascade across 7 days
    and 4 channels."""

    async def test_seven_day_grant_lifecycle_with_day7_cross_channel_cascade(
        self,
    ) -> None:
        """The narrative under test (see module docstring table)."""
        # Pre-stage Day-7 cascade lineage: revoking Day-1 returns the
        # full set across channels (this is the Phase-02 TrustStore's
        # job; Phase-01 stubs it via cascade_responses).
        day1_grant_id = "delegation-record-day1-telegram-primary"
        day3_grant_id = "delegation-record-day3-slack-out-of-envelope"
        day6_grant_id = "delegation-record-day6-discord-child"
        runtime, _km, ledger, _audit, adapters = await make_runtime(
            primary_channel_id="telegram",
            adapter_channel_ids=("cli", "telegram", "slack", "discord"),
            cascade_responses={
                day1_grant_id: {day1_grant_id, day3_grant_id, day6_grant_id},
            },
        )

        # === Day 1 — onboarding completes; first grant on Telegram ===
        day1_outcome = await _issue_and_approve(
            runtime,
            intent_id="sha256:intent-day1-onboarding-send",
            decided_on_channel_id="telegram",
        )
        assert day1_outcome.state == "APPROVED"
        assert day1_outcome.delegation_record_ref

        # === Day 2 — digest day; state-equivalence read ===
        # Every channel performing the same Ledger query observes the same
        # 1-row state — the channel-independence invariant.
        assert await _count_grant_moment_entries(ledger) == 1

        # === Day 3 — out-of-envelope grant decided on Slack ===
        day3_outcome = await _issue_and_approve(
            runtime,
            intent_id="sha256:intent-day3-out-of-envelope",
            decided_on_channel_id="slack",
        )
        assert day3_outcome.state == "APPROVED"

        # === Day 4 — offline; no actions; state preserves ===
        # No state-mutating call; the state-equivalence read returns the
        # SAME count it would on Day-3 evening.  This is the EC-8(a)
        # zero-drift invariant under inactivity.
        count_before_offline = await _count_grant_moment_entries(ledger)
        count_after_offline = await _count_grant_moment_entries(ledger)
        assert count_before_offline == count_after_offline == 2

        # === Day 5 — digest day with back-fill; all prior rows queryable ===
        # The back-fill horizon is 7 days per shard 11 § 3.4; on Day-5
        # querying the [Day-1, Day-5+] window MUST return both Day-1 and
        # Day-3 entries (no horizon truncation in this 5-day reach).
        entries_day5 = await ledger.query(
            filter={"event_type": _GRANT_MOMENT_TYPE},
            since=_QUERY_SINCE,
            until=_QUERY_UNTIL,
        )
        assert len(entries_day5) == 2

        # === Day 6 — child grant on Discord ===
        day6_outcome = await _issue_and_approve(
            runtime,
            intent_id="sha256:intent-day6-discord-child",
            decided_on_channel_id="discord",
        )
        assert day6_outcome.state == "APPROVED"
        assert await _count_grant_moment_entries(ledger) == 3

        # === Day 7 — revoke Day-1 via cascade; reach Day-3 + Day-6 ===
        # The cascade orchestrator is channel-agnostic; the request goes
        # via Telegram but the descendant set spans Slack + Discord.
        result = runtime.revoke_prior_grant(
            root_id=day1_grant_id,
            expected_descendants=frozenset({day3_grant_id, day6_grant_id}),
        )
        assert result.complete is True
        assert result.revoked_ids == frozenset({day1_grant_id, day3_grant_id, day6_grant_id})
        assert result.missing_descendants == frozenset()

        # === Battery close: full Ledger chain verifies ===
        report = await ledger.verify_chain()
        assert (
            report.success is True
        ), f"Ledger chain verification failed after 7-day battery: {report!r}"

        # Per-channel adapter fan-out evidence: every adapter saw every
        # grant — the channels participated in the dispatch surface.
        for adapter in adapters:
            assert len(adapter.renders) == 3, (
                f"{adapter.channel_id}: expected 3 renders across the 7-day "
                f"battery, got {len(adapter.renders)}"
            )

    async def test_offline_day_does_not_drift_state_across_channels(self) -> None:
        """Isolation of the Day-4 invariant: inactivity preserves state
        equivalence across every channel's view of the Ledger.

        Sibling assertion to the main battery — proves that the
        state-equivalence read is genuinely passive (no Ledger mutation
        as a side-effect of querying), so an offline day cannot
        retroactively desynchronize channels."""
        runtime, _km, ledger, _audit, _adapters = await make_runtime(
            primary_channel_id="telegram",
            adapter_channel_ids=("cli", "telegram", "slack", "discord"),
        )
        await _issue_and_approve(
            runtime,
            intent_id="sha256:intent-pre-offline",
            decided_on_channel_id="telegram",
        )
        baseline = await _count_grant_moment_entries(ledger)

        # Simulate Day-4 with 8 independent state-equivalence reads from
        # different channel contexts — the channel-independence invariant
        # means none of them mutate state.
        for _ in range(8):
            assert await _count_grant_moment_entries(ledger) == baseline

        # The chain remains verifiable after a flurry of read-only
        # queries — `verify_chain` is also non-mutating.
        report = await ledger.verify_chain()
        assert report.success is True

    async def test_cross_channel_query_returns_identical_entry_set(self) -> None:
        """The Ledger is the single source of truth; channels are
        renderers, not databases.  Three independent queries with the
        same filter from three "channel contexts" return the SAME
        entry list (byte-identical entry_ids)."""
        runtime, _km, ledger, _audit, _adapters = await make_runtime(
            primary_channel_id="telegram",
            adapter_channel_ids=("cli", "telegram", "slack", "discord"),
        )

        # Stage 3 grants across 3 channels.
        await _issue_and_approve(
            runtime,
            intent_id="sha256:intent-state-equiv-a",
            decided_on_channel_id="telegram",
        )
        await _issue_and_approve(
            runtime,
            intent_id="sha256:intent-state-equiv-b",
            decided_on_channel_id="slack",
        )
        await _issue_and_approve(
            runtime,
            intent_id="sha256:intent-state-equiv-c",
            decided_on_channel_id="discord",
        )

        # Three independent queries — one per "channel context".  Each
        # returns the same 3-entry set in the same order (Ledger ordering
        # is the canonical cross-channel order).
        query_kwargs = {
            "filter": {"event_type": _GRANT_MOMENT_TYPE},
            "since": _QUERY_SINCE,
            "until": _QUERY_UNTIL,
        }
        view_a = await ledger.query(**query_kwargs)
        view_b = await ledger.query(**query_kwargs)
        view_c = await ledger.query(**query_kwargs)

        ids_a = [e.entry_id for e in view_a]
        ids_b = [e.entry_id for e in view_b]
        ids_c = [e.entry_id for e in view_c]
        assert ids_a == ids_b == ids_c
        assert len(ids_a) == 3
