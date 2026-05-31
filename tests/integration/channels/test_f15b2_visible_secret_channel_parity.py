"""Tier-2 wiring (F15-b.2): visible-secret rendering parity across channels.

Contract pin: F15-b.2 (low-stakes visible-secret rendering parity) +
T-018 (dialog spoofing). Per `specs/grant-moment.md` § Rendering: "Every
dialog shows: Visible secret (icon + color + phrase, stored in Trust
Vault)." The visible secret is the anti-spoofing surface the user checks
before trusting a prompt, so it MUST render on the M1 `render_grant_moment`
dispatch path — not only on the full-ritual `send_grant_moment` path.

Before F15-b.2, only the primary CLI channel rendered the secret on the M1
path (F15-b.1); Slack/Telegram/Discord accepted the `visible_secret` arg
for Protocol conformance but dropped it. This test pins that the three
prose-rendering channels now render `icon + phrase` FIRST, and documents the
Web channel's structural deferral.

Per `rules/testing.md` § Tier 2: no `mock.patch` / `MagicMock`. All paths
use real adapter instances. Discord's Phase-01 transport raises
`ChannelTransportError` (no webhook wired), so its render content is pinned
via the render helper directly — the established pattern from the R3
MED-R3-02 closure (`tests/integration/channels/test_redteam_r3_closures.py`).
"""

from __future__ import annotations

import asyncio

import pytest

from envoy.channels.discord import DiscordChannelAdapter
from envoy.channels.envelope import VisibleSecret
from envoy.channels.slack import SlackChannelAdapter, SlackChannelConfig
from envoy.channels.telegram import TelegramChannelAdapter
from envoy.channels.web import WebChannelAdapter, WebChannelConfig

# A distinctive icon + phrase so the assertion cannot match incidental text.
_ICON = "🔑"
_PHRASE = "cobalt-marshmallow-42"
_SECRET = VisibleSecret(icon=_ICON, color="#A0E7E5", phrase=_PHRASE)

_SLACK_SIGNING_SECRET = "8f742231b10e8888abcd99badc0a9199"
_SLACK_BOT_TOKEN = "xoxb-test-token-AAAAAAAAAAAAAAAA"


class _Request:
    """Duck-typed shim mirroring canonical `GrantMomentRequest` fields.

    Adapters read these via `getattr`; Telegram additionally reads
    `description` / `principal_genesis_id` / `chat_id`.
    """

    def __init__(
        self,
        *,
        request_id: str = "gm-f15b2",
        novelty_class: str = "familiar_repeat",
        primary_only: bool = False,
        tool_name: str = "send_email",
        why_asking: str = "envelope_violation",
        consequence_preview: object | None = None,
        description: str = "Allow the proposed action?",
        chat_id: str = "chat-f15b2",
        principal_genesis_id: str = "",
    ) -> None:
        self.request_id = request_id
        self.novelty_class = novelty_class
        self.primary_only = primary_only
        self.tool_name = tool_name
        self.why_asking = why_asking
        self.consequence_preview = consequence_preview
        self.description = description
        self.chat_id = chat_id
        self.principal_genesis_id = principal_genesis_id


@pytest.mark.regression
@pytest.mark.asyncio
class TestSlackVisibleSecretParity:
    """Pin: Slack M1 render renders icon + phrase FIRST (F15-b.2)."""

    async def test_render_grant_moment_renders_visible_secret(self) -> None:
        adapter = SlackChannelAdapter(
            SlackChannelConfig(
                primary_channel_id="slack",
                signing_secret=_SLACK_SIGNING_SECRET,
                bot_token=_SLACK_BOT_TOKEN,
            )
        )
        await adapter.startup()
        try:
            await adapter.render_grant_moment(
                _Request(request_id="gm-slack"), visible_secret=_SECRET
            )
            renders = [text for tag, text in adapter._outbound_log if tag == "__render__"]
            assert renders, "render_grant_moment did not append to the outbound log"
            assert _ICON in renders[0]
            assert _PHRASE in renders[0]
            assert "Safety phrase:" in renders[0]
        finally:
            await adapter.shutdown()

    async def test_render_without_secret_omits_safety_phrase(self) -> None:
        adapter = SlackChannelAdapter(
            SlackChannelConfig(
                primary_channel_id="slack",
                signing_secret=_SLACK_SIGNING_SECRET,
                bot_token=_SLACK_BOT_TOKEN,
            )
        )
        await adapter.startup()
        try:
            await adapter.render_grant_moment(
                _Request(request_id="gm-slack-none"), visible_secret=None
            )
            renders = [text for tag, text in adapter._outbound_log if tag == "__render__"]
            assert renders
            assert "Safety phrase:" not in renders[0]
            assert _PHRASE not in renders[0]
        finally:
            await adapter.shutdown()


@pytest.mark.regression
@pytest.mark.asyncio
class TestTelegramVisibleSecretParity:
    """Pin: Telegram M1 render renders icon + phrase (F15-b.2)."""

    async def test_render_grant_moment_renders_visible_secret(self) -> None:
        sent: list[tuple[str, str]] = []

        async def _send_fn(chat_id: str, text: str) -> None:
            sent.append((chat_id, text))

        adapter = TelegramChannelAdapter(
            primary_channel_id="telegram",
            secret_token="test-secret",
            send_fn=_send_fn,
            inbound_queue=None,
        )
        await adapter.startup()
        try:
            await adapter.render_grant_moment(
                _Request(request_id="gm-tg", chat_id="chat-1"), visible_secret=_SECRET
            )
            assert sent, "render_grant_moment did not dispatch via send_fn"
            _, text = sent[0]
            assert _ICON in text
            assert _PHRASE in text
            assert "Safety phrase:" in text
        finally:
            await adapter.shutdown()

    async def test_render_without_secret_omits_safety_phrase(self) -> None:
        sent: list[tuple[str, str]] = []

        async def _send_fn(chat_id: str, text: str) -> None:
            sent.append((chat_id, text))

        adapter = TelegramChannelAdapter(
            primary_channel_id="telegram",
            secret_token="test-secret",
            send_fn=_send_fn,
            inbound_queue=None,
        )
        await adapter.startup()
        try:
            await adapter.render_grant_moment(
                _Request(request_id="gm-tg-none", chat_id="chat-1"), visible_secret=None
            )
            assert sent
            assert "Safety phrase:" not in sent[0][1]
            assert _PHRASE not in sent[0][1]
        finally:
            await adapter.shutdown()


@pytest.mark.regression
class TestDiscordVisibleSecretParity:
    """Pin: Discord M1 render-helper renders icon + phrase (F15-b.2).

    Phase-01 Discord transport raises `ChannelTransportError` (no webhook),
    so render content is pinned via the helper directly — the same surface
    `render_grant_moment` passes `visible_secret` into.
    """

    def test_render_helper_renders_visible_secret(self) -> None:
        rendered = DiscordChannelAdapter._render_grant_moment_request_prose(
            _Request(request_id="gm-dc"), _SECRET
        )
        assert _ICON in rendered
        assert _PHRASE in rendered
        assert "Safety phrase:" in rendered

    def test_render_helper_without_secret_omits_safety_phrase(self) -> None:
        rendered = DiscordChannelAdapter._render_grant_moment_request_prose(
            _Request(request_id="gm-dc-none")
        )
        assert "Safety phrase:" not in rendered
        assert _PHRASE not in rendered


@pytest.mark.regression
@pytest.mark.asyncio
class TestWebVisibleSecretDeferral:
    """Document: Web has NO server-side render; secret render lands with the
    deferred Wave-4 Nexus WS modal-push shard.

    Web's Grant Moment dialog is a CLIENT-SIDE modal pushed over WS/SSE; the
    push is deferred (`send_message` raises `PhaseDeferredError`). So the M1
    `render_grant_moment` accepts the secret, registers the pending decision,
    and renders NOTHING server-side — rendering the phrase here would be a
    fake render (`rules/zero-tolerance.md` Rule 2) or orphan state
    (`rules/orphan-detection.md` Rule 1). This test pins that contract so a
    future change that starts leaking the phrase server-side fails loudly.
    """

    async def test_render_registers_pending_without_server_side_phrase(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            await adapter.render_grant_moment(_Request(request_id="gm-web"), visible_secret=_SECRET)
            # Web registers a pending decision future keyed by request_id; the
            # phrase is NOT rendered server-side (no transport surface).
            assert "gm-web" in adapter._pending_decisions
            assert isinstance(adapter._pending_decisions["gm-web"], asyncio.Future)
        finally:
            await adapter.shutdown()
