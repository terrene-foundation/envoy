"""Tier-2 regression pins for /redteam R5 same-shard closures.

R5 spec-axis surfaced 2 MED + 1 LOW from R4 spec edits over-promising
hostname-blocklist coverage + Telegram pending-grant cleanup not using
``finally``. The orchestrator closed all 3 as same-shard polish per
``rules/autonomous-execution.md`` MUST Rule 4. These tests pin each fix so
a regression to the old shape fails loudly:

- R5-MED-1: ``_SSRF_BLOCKED_HOSTS`` rejects ``localhost``.
- R5-MED-2: ``_SSRF_BLOCKED_HOSTS`` rejects ``::`` (bracket-stripped IPv6
  unspecified address) — not caught by ``::1/128`` / ``fc00::/7`` /
  ``::ffff:0.0.0.0/96`` networks.
- R5-LOW-1: Telegram ``send_grant_moment`` cleanup uses ``finally`` so a
  ``CancelledError`` during ``response_queue.get()`` does NOT orphan the
  request_id in ``_pending_grants``.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from envoy.channels.envelope import GrantMomentPayload, VisibleSecret
from envoy.channels.errors import ChannelTransportError
from envoy.channels.telegram import TelegramChannelAdapter

# ---------------------------------------------------------------------------
# R5-MED-1 / R5-MED-2 — SSRF hostname blocklist
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_discord_ssrf_blocks_localhost_hostname() -> None:
    """R5-MED-1: ``localhost`` MUST be rejected at the hostname layer.

    Pre-fix the SSRF guard only blocked IP literals at parse time, so
    ``http://localhost/`` passed through to DNS — which resolves to
    127.0.0.1 — bypassing the loopback network block.
    """
    from envoy.channels.discord import DiscordChannelAdapter, DiscordChannelConfig

    config = DiscordChannelConfig(
        primary_channel_id="discord",
        bot_token="test-bot-token",
        application_public_key="a" * 64,  # 32 bytes hex
        webhook_url="https://localhost/webhook/123/abc",
    )
    adapter = DiscordChannelAdapter(config)
    with pytest.raises(ChannelTransportError) as excinfo:
        await adapter.startup()
    assert "localhost" in str(excinfo.value).lower() or "blocked" in str(excinfo.value).lower()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_discord_ssrf_blocks_ipv6_unspecified_bracket_form() -> None:
    """R5-MED-2: ``[::]`` (IPv6 unspecified) MUST be rejected.

    Pre-fix ``urlparse("https://[::]/").hostname == "::"`` was not in any
    blocked network: ``::`` is not in ``::1/128`` (loopback),
    ``fc00::/7`` (ULA), or ``::ffff:0.0.0.0/96`` (mapped). It bypassed
    the guard. Now caught at the hostname-blocklist layer.
    """
    from envoy.channels.discord import DiscordChannelAdapter, DiscordChannelConfig

    config = DiscordChannelConfig(
        primary_channel_id="discord",
        bot_token="test-bot-token",
        application_public_key="a" * 64,
        webhook_url="https://[::]/webhook/123/abc",
    )
    adapter = DiscordChannelAdapter(config)
    with pytest.raises(ChannelTransportError):
        await adapter.startup()


# ---------------------------------------------------------------------------
# R5-LOW-1 — Telegram pending-grant cleanup uses finally
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_telegram_pending_grant_cleaned_up_on_cancel() -> None:
    """R5-LOW-1: ``CancelledError`` during ``response_queue.get()`` MUST
    NOT orphan the request_id in ``_pending_grants``.

    Pre-fix Telegram used explicit branch-pops on the timeout + normal
    paths but no ``finally`` block. A cancellation between the
    ``_register_pending`` write and the queue ``get`` would leak the
    entry indefinitely (consuming a ``_MAX_PENDING_DECISIONS`` slot).
    """
    sent: list[tuple[str, str]] = []

    async def _send_fn(chat_id: str, text: str) -> None:
        sent.append((chat_id, text))

    adapter = TelegramChannelAdapter(secret_token="valid-secret-token", send_fn=_send_fn)
    await adapter.startup()

    grant = GrantMomentPayload(
        request_id="r-cancel-leak-test",
        intent_id="i-1",
        decision_options=("approve_once", "deny"),
        visible_secret=VisibleSecret(icon="bolt", color="amber", phrase="b-a-m"),
        body="Allow the action?",
        high_stakes=False,
    )

    # Launch a grant moment that will block on response_queue.get() with a
    # long timeout (60s). No post_decision() will ever arrive.
    task = asyncio.create_task(adapter.send_grant_moment("principal-1", grant, timeout_seconds=60))
    # Let the task register its pending queue and reach the await.
    await asyncio.sleep(0)
    assert "r-cancel-leak-test" in adapter._pending_grants

    # Cancel the task BEFORE the queue is unblocked. The pre-fix code path
    # would leak the request_id; the post-fix path cleans up via finally.
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert "r-cancel-leak-test" not in adapter._pending_grants, (
        "send_grant_moment MUST clean up _pending_grants on cancellation "
        "(finally block); pre-fix code path would leak the request_id"
    )

    await adapter.shutdown()
