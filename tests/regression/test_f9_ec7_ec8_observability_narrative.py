"""Regression: F9 — EC-7 + EC-8 observability-narrative extension.

Extends the R1 observability surface (``test_round1_observability_log_keys.py``)
from the four R1 WARN keys to the structured INFO log keys the runtime emits
across the EC-7 (onboarding) and EC-8 (cross-channel) acceptance narratives.

Value-anchor (per `rules/value-prioritization.md` MUST-1, source (e) spec §
success criterion): `01-analysis/02-mvp-objectives.md` line 104 (EC-7 —
first-time onboarding from each channel) + line 116 (EC-8 — 7-day operating
window + cross-channel state coherence + cascade revocation). Catches silent
runtime-log regressions at acceptance time: a refactor that renames or drops
``channel.startup`` / ``grant_moment.issued`` / ``grant_moment.completed``
would break the operator's INFO/state-transition audit (`rules/observability.md`
Rule 4 state-transition logging + Rule 5 WARN+ scan) with no test signal.

This is a regression-LOCK, not a new-capability test: every asserted key is a
key the runtime emits TODAY (grounded against the live emit sites cited inline).
Per `rules/testing.md` § Regression Testing this test is permanent and MUST NOT
be deleted.
"""

from __future__ import annotations

import io
import logging

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from envoy.channels.adapter import ChannelAdapter
from envoy.channels.cli import CLIChannelAdapter, CLIChannelConfig
from envoy.channels.discord import DiscordChannelAdapter, DiscordChannelConfig
from envoy.channels.slack import SlackChannelAdapter, SlackChannelConfig
from envoy.channels.telegram import TelegramChannelAdapter
from envoy.channels.web import WebChannelAdapter, WebChannelConfig
from envoy.grant_moment import ApproveResolution
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_familiar_repeat_signals,
    make_issue_kwargs,
    make_runtime,
)

# The five Phase-01 channel adapters (PR #48 EC-7 surface). The spec names 8
# logical channels (02-mvp-objectives.md:98); the implemented onboarding surface
# today is these five, which is exactly the EC-7 subscope the round-4 + round-5
# convergence banked (04-validate/round-4-rolling-convergence-2026-05-28.md).
# Each adapter emits ``channel.startup`` / ``channel.shutdown`` under its own
# ``envoy.channels.*`` module logger (grounded: cli.py:137/151, web.py:171/195,
# telegram.py:241/272, slack.py:189/208, discord.py:354/372).
_CHANNEL_LOGGER_PREFIX = "envoy.channels"
_EXPECTED_CHANNEL_IDS = {"cli", "web", "telegram", "slack", "discord"}


def _build_channel_adapters() -> list[tuple[str, ChannelAdapter]]:
    """Construct one adapter per Phase-01 channel with deterministic test
    fixtures (mirrors each adapter's own lifecycle test construction)."""
    priv = Ed25519PrivateKey.generate()
    discord_pubkey_hex = priv.public_key().public_bytes_raw().hex()
    return [
        (
            "cli",
            CLIChannelAdapter(
                CLIChannelConfig(
                    primary_channel_id="cli",
                    output_stream=io.StringIO(),
                    input_stream=io.StringIO(),
                )
            ),
        ),
        ("web", WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))),
        (
            "telegram",
            TelegramChannelAdapter(primary_channel_id="telegram", secret_token="test-secret"),
        ),
        (
            "slack",
            SlackChannelAdapter(
                SlackChannelConfig(
                    primary_channel_id="slack",
                    signing_secret="8f742231b10e8888abcd99badc0a9199",
                    bot_token="xoxb-test-token-AAAAAAAAAAAAAAAA",
                )
            ),
        ),
        (
            "discord",
            DiscordChannelAdapter(
                DiscordChannelConfig(
                    primary_channel_id="discord",
                    application_public_key=discord_pubkey_hex,
                    bot_token="test-bot-token-not-real",  # noqa: S106 — test fixture
                )
            ),
        ),
    ]


@pytest.mark.regression
class TestEC7OnboardingObservabilityNarrative:
    """EC-7 — first-time onboarding from each of the 5 Phase-01 channels emits
    the ``channel.startup`` lifecycle key with a ``channel_id`` field, and
    ``channel.shutdown`` on teardown. The per-channel symmetry of these keys IS
    the operator-visible onboarding-narrative contract: an operator scanning the
    INFO stream MUST see one startup line per channel, tagged by channel_id."""

    async def test_each_channel_emits_startup_and_shutdown_with_channel_id(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        adapters = _build_channel_adapters()

        with caplog.at_level(logging.INFO, logger=_CHANNEL_LOGGER_PREFIX):
            for _channel_id, adapter in adapters:
                await adapter.startup()
                await adapter.shutdown()

        startup_records = [r for r in caplog.records if r.message == "channel.startup"]
        shutdown_records = [r for r in caplog.records if r.message == "channel.shutdown"]

        # One startup + one shutdown per channel — the EC-7 symmetry contract.
        assert len(startup_records) == len(adapters)
        assert len(shutdown_records) == len(adapters)

        # Every startup line is tagged with its channel_id (operator audit key)
        # and the full set of channel_ids matches the Phase-01 onboarding surface.
        startup_channel_ids = {getattr(r, "channel_id", None) for r in startup_records}
        assert startup_channel_ids == _EXPECTED_CHANNEL_IDS
        assert None not in startup_channel_ids

        # The startup keys fire under the per-channel module loggers (not a single
        # shared logger) — proves the channels are independently observable.
        startup_loggers = {r.name for r in startup_records}
        assert len(startup_loggers) == len(adapters)
        assert all(name.startswith(_CHANNEL_LOGGER_PREFIX + ".") for name in startup_loggers)


@pytest.mark.regression
class TestEC8CrossChannelObservabilityNarrative:
    """EC-8 — the cross-channel grant narrative emits ``grant_moment.issued`` on
    issue and ``grant_moment.completed`` on resolution, under the
    ``envoy.grant_moment.runtime`` logger (grounded: runtime.py:673 + :1008).
    These are the state-transition keys (`rules/observability.md` Rule 4) an
    operator relies on to reconstruct cross-channel grant flow over the operating
    window; N=3 grants across 3 channels MUST produce N issued + N completed."""

    async def _issue_and_approve(self, runtime, *, intent_id: str, decided_on_channel_id: str):
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

    async def test_cross_channel_grant_narrative_emits_issued_and_completed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Day-1 Telegram, Day-3 Slack, Day-6 Discord cascade lineage — the same
        # day-by-day shape as the EC-8 Tier-3 battery
        # (tests/e2e/test_envoy_7_day_cross_channel_coherence.py).
        day1 = "delegation-record-day1-telegram-primary"
        day3 = "delegation-record-day3-slack-out-of-envelope"
        day6 = "delegation-record-day6-discord-child"
        runtime, _km, _ledger, _audit, _adapters = await make_runtime(
            primary_channel_id="telegram",
            adapter_channel_ids=("cli", "telegram", "slack", "discord"),
            cascade_responses={day1: {day1, day3, day6}},
        )

        with caplog.at_level(logging.INFO, logger="envoy.grant_moment.runtime"):
            await self._issue_and_approve(
                runtime, intent_id="sha256:intent-day1", decided_on_channel_id="telegram"
            )
            await self._issue_and_approve(
                runtime, intent_id="sha256:intent-day3", decided_on_channel_id="slack"
            )
            await self._issue_and_approve(
                runtime, intent_id="sha256:intent-day6", decided_on_channel_id="discord"
            )

        keys = {r.message for r in caplog.records}
        assert "grant_moment.issued" in keys
        assert "grant_moment.completed" in keys

        issued = [r for r in caplog.records if r.message == "grant_moment.issued"]
        completed = [r for r in caplog.records if r.message == "grant_moment.completed"]

        # N=3 grants → 3 issued + 3 completed (the cross-channel narrative count).
        assert len(issued) == 3
        assert len(completed) == 3

        # issued carries the operator's triage fields (request_id + novelty_class);
        # completed carries decided_on_channel_id — the cross-channel breadcrumb.
        for record in issued:
            assert getattr(record, "request_id", None) is not None
            assert getattr(record, "novelty_class", None) is not None
        decided_channels = {getattr(r, "decided_on_channel_id", None) for r in completed}
        assert decided_channels == {"telegram", "slack", "discord"}
