"""Tier-2: pins for /redteam R2 same-shard closures (PR #42).

Round-2 audit surfaced 3 HIGH + 7 MED + 2 LOW where the R1 closures landed
the original failure mode on `send_grant_moment` but introduced sibling
sites (`render_grant_moment` + `_resolve_pending_decision`) with the same
bypass class. Per `rules/autonomous-execution.md` MUST Rule 4 the same-shard
closures landed in commit ``<HEAD>``.

Each test docstring names the R2 finding it pins (e.g. ``HIGH-R2-01``).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pytest

from envoy.channels import (
    CLIChannelAdapter,
    InvalidDecisionError,
    NotPrimaryChannelError,
    PendingDecisionsCeilingError,
    WebChannelAdapter,
)
from envoy.channels.cli import CLIChannelConfig
from envoy.channels.web import WebChannelConfig


# Minimal duck-typed request shim — mirrors the GrantMomentRequest fields
# the adapter reads via getattr. Avoids importing the heavy runtime type.
class _Request:
    """Duck-typed shim mirroring the canonical `GrantMomentRequest` fields.

    Per /redteam R3 H-R3-1 closure: the adapter reads `novelty_class` +
    `primary_only` (the actual `GrantMomentRequest` discriminators), NOT a
    non-existent `high_stakes` field. The shim accepts `high_stakes=True`
    as a convenience flag that sets `novelty_class="high_stakes"` so test
    callsites stay readable.
    """

    def __init__(
        self,
        *,
        request_id: str = "r-r2",
        high_stakes: bool = False,
        novelty_class: str | None = None,
        primary_only: bool = False,
        tool_name: str = "",
        why_asking: str = "",
        consequence_preview: object | None = None,
    ) -> None:
        self.request_id = request_id
        # Translate the test convenience flag to the canonical discriminator.
        self.novelty_class = novelty_class or ("high_stakes" if high_stakes else "familiar_repeat")
        self.primary_only = primary_only
        self.tool_name = tool_name
        self.why_asking = why_asking
        self.consequence_preview = consequence_preview


# ---------------------------------------------------------------------------
# HIGH-R2-01 — render_grant_moment honors _MAX_PENDING_DECISIONS ceiling
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRenderGrantMomentBounded:
    """Pin: `render_grant_moment` write site enforces the in-flight ceiling.

    Pre-R2 only `send_grant_moment` checked the cap; the new
    `render_grant_moment` (added in R1 closures) wrote directly to the
    dict and bypassed the check entirely.
    """

    @pytest.mark.asyncio
    async def test_render_grant_moment_refuses_past_ceiling(self) -> None:
        from envoy.channels import web as web_mod

        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            loop = asyncio.get_running_loop()
            for i in range(web_mod._MAX_PENDING_DECISIONS):
                adapter._pending_decisions[f"pre-{i}"] = loop.create_future()
            with pytest.raises(PendingDecisionsCeilingError) as excinfo:
                await adapter.render_grant_moment(_Request(request_id="over-cap"))
            assert excinfo.value.channel_id == "web"
            assert excinfo.value.ceiling == web_mod._MAX_PENDING_DECISIONS
        finally:
            for fut in adapter._pending_decisions.values():
                if not fut.done():
                    fut.cancel()
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# HIGH-R2-02 — render_grant_moment enforces H-03 primary-channel binding
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRenderGrantMomentH03:
    """Pin: `render_grant_moment` refuses high-stakes on non-primary adapter.

    Pre-R2 the H-03 binding was enforced only on `send_grant_moment`; the
    M1 dispatch surface trusted the caller. The R2 closure makes the
    payload-level discriminator the structural defense on BOTH surfaces.
    """

    @pytest.mark.asyncio
    async def test_cli_render_grant_moment_refuses_non_primary_for_high_stakes(
        self,
    ) -> None:
        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError) as excinfo:
                await adapter.render_grant_moment(
                    _Request(request_id="r-1", high_stakes=True, tool_name="x")
                )
            assert excinfo.value.channel_id == "cli"
            assert excinfo.value.primary_channel_id == "web"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_web_render_grant_moment_refuses_non_primary_for_high_stakes(
        self,
    ) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="cli"))
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError) as excinfo:
                await adapter.render_grant_moment(_Request(request_id="r-1", high_stakes=True))
            assert excinfo.value.channel_id == "web"
            assert excinfo.value.primary_channel_id == "cli"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_render_grant_moment_non_high_stakes_accepted_on_non_primary(
        self,
    ) -> None:
        """Non-high-stakes renders proceed even on a non-primary channel."""
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="cli"))
        await adapter.startup()
        try:
            # Should NOT raise — the multi-channel low-stakes dispatch path.
            await adapter.render_grant_moment(_Request(request_id="r-lowstakes", high_stakes=False))
            assert "r-lowstakes" in adapter._pending_decisions
        finally:
            for fut in adapter._pending_decisions.values():
                if not fut.done():
                    fut.cancel()
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# HIGH-R2-03 — _resolve_pending_decision validates closed vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestResolvePendingDecisionClosedVocabulary:
    """Pin: `_resolve_pending_decision` raises on out-of-vocab decisions.

    Pre-R2 the future resolved with arbitrary strings, bypassing the
    `GrantMomentDecision` Literal contract at the M2→M3 boundary.
    """

    @pytest.mark.asyncio
    async def test_resolve_pending_decision_rejects_out_of_vocabulary(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            with pytest.raises(InvalidDecisionError) as excinfo:
                await adapter._resolve_pending_decision("r-1", "force_approve")
            assert excinfo.value.channel_id == "web"
            assert excinfo.value.decision == "force_approve"
            assert "approve_once" in excinfo.value.allowed
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_resolve_pending_decision_accepts_canonical_vocabulary(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            from envoy.channels.envelope import (
                GrantMomentPayload,
                VisibleSecret,
            )

            grant = GrantMomentPayload(
                request_id="r-canonical",
                intent_id="i-1",
                decision_options=("approve_once", "deny"),
                visible_secret=VisibleSecret(icon="i", color="c", phrase="p"),
                body="b",
                high_stakes=False,
            )

            async def resolver() -> None:
                await asyncio.sleep(0.01)
                await adapter._resolve_pending_decision("r-canonical", "approve_once")

            send_task = asyncio.create_task(
                adapter.send_grant_moment("p", grant, timeout_seconds=5)
            )
            resolver_task = asyncio.create_task(resolver())
            receipt, _ = await asyncio.gather(send_task, resolver_task)
            assert receipt.decision == "approve_once"
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# MED-R2-05 — startup() refuses non-Config arg types
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestStartupConfigTypeCheck:
    """Pin: passing a dict / wrong-type config to startup raises TypeError."""

    @pytest.mark.asyncio
    async def test_cli_startup_refuses_dict_config(self) -> None:
        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="cli"))
        with pytest.raises(TypeError, match="CLIChannelConfig"):
            await adapter.startup({"primary_channel_id": "cli"})  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_web_startup_refuses_dict_config(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        with pytest.raises(TypeError, match="WebChannelConfig"):
            await adapter.startup({"primary_channel_id": "web"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MED-R2-06 — typed PendingDecisionsCeilingError (not bare RuntimeError)
# ---------------------------------------------------------------------------


def test_pending_decisions_ceiling_error_is_channel_adapter_error() -> None:
    """Pin: ceiling refusal subclasses `ChannelAdapterError`."""
    from envoy.channels.errors import ChannelAdapterError

    err = PendingDecisionsCeilingError(channel_id="web", ceiling=1000, current_count=1000)
    assert isinstance(err, ChannelAdapterError)
    assert err.channel_id == "web"
    assert err.ceiling == 1000
    assert err.current_count == 1000


# ---------------------------------------------------------------------------
# MED-R2-07 / MED-R2-08 — PII fields hashed in log emissions
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestPIIHashInLogs:
    """Pin: `session_id` + `target_principal_id` hashed in log emissions.

    Pre-R2 these PII-adjacent identifiers were emitted in plain to log
    aggregators where access is broader than the production database.
    """

    @pytest.mark.asyncio
    async def test_cli_send_message_does_not_log_raw_principal_id(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import io

        adapter = CLIChannelAdapter(
            CLIChannelConfig(
                primary_channel_id="cli",
                output_stream=io.StringIO(),
                input_stream=io.StringIO(),
            )
        )
        await adapter.startup()
        try:
            from envoy.channels.envelope import MessagePayload

            sentinel = "principal-genesis-id-DO-NOT-LEAK-7c0ffee"
            with caplog.at_level(logging.INFO, logger="envoy.channels.cli"):
                await adapter.send_message(sentinel, MessagePayload(kind="text", body="hi"))
            for record in caplog.records:
                assert sentinel not in record.getMessage()
                assert sentinel not in str(record.__dict__)
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_cli_inbound_overflow_does_not_log_raw_session_id(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from envoy.channels.envelope import InboundMessage, MessagePayload

        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="cli"))
        await adapter.startup()
        try:
            sentinel = "session-DO-NOT-LEAK-fee1dead"
            msg = InboundMessage(
                channel_id="cli",
                session_id=sentinel,
                principal_genesis_id="p",
                direction="inbound",
                content_trust_level="user",
                payload=MessagePayload(kind="text", body="x"),
                visible_secret_rendered=None,
                timestamp=datetime.now(timezone.utc),
            )
            for _ in range(100):
                await adapter._inject_inbound(msg)
            with caplog.at_level(logging.WARNING, logger="envoy.channels.cli"):
                await adapter._inject_inbound(msg)
            for record in caplog.records:
                assert sentinel not in record.getMessage()
                assert sentinel not in str(record.__dict__)
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# M-R2-1 (reviewer) — CLI send_grant_moment emits structured log lines
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestCLISendGrantMomentLogging:
    """Pin: CLI send_grant_moment mirrors Web's start/expired/ok log shape."""

    @pytest.mark.asyncio
    async def test_cli_send_grant_moment_emits_start_and_ok_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import io

        from envoy.channels.envelope import GrantMomentPayload, VisibleSecret

        adapter = CLIChannelAdapter(
            CLIChannelConfig(
                primary_channel_id="cli",
                output_stream=io.StringIO(),
                input_stream=io.StringIO("deny\n"),
            )
        )
        await adapter.startup()
        try:
            grant = GrantMomentPayload(
                request_id="r-cli-log",
                intent_id="i-1",
                decision_options=("approve_once", "deny"),
                visible_secret=VisibleSecret(icon="i", color="c", phrase="p"),
                body="b",
                high_stakes=False,
            )
            with caplog.at_level(logging.INFO, logger="envoy.channels.cli"):
                await adapter.send_grant_moment("p", grant, timeout_seconds=5)
            events = [r.message for r in caplog.records]
            assert any("channel.send_grant_moment.start" in e for e in events)
            assert any("channel.send_grant_moment.ok" in e for e in events)
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# MED-R2-04 — default origins assertion at module load
# ---------------------------------------------------------------------------


def test_default_allowed_origins_not_empty_at_module_load() -> None:
    """Pin: the module-load assertion fires loudly on empty dev-port set."""
    from envoy.channels import web as web_mod

    assert web_mod._DEFAULT_ALLOWED_ORIGINS
    assert all(":" in o for o in web_mod._DEFAULT_ALLOWED_ORIGINS)


# ---------------------------------------------------------------------------
# H-1 / H-2 — Future idempotency: _register_pending returns same Future
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_discord_register_pending_idempotent() -> None:
    """H-1: Discord._register_pending("same-id") twice returns identical Future.

    Guard: concurrent callers racing on the same request_id MUST receive
    the same asyncio.Future so that resolving it from inbound webhook wakes
    every waiter, not just the first.
    """
    from envoy.channels.discord import DiscordChannelAdapter, DiscordChannelConfig

    cfg = DiscordChannelConfig(
        primary_channel_id="discord",
        application_public_key="a" * 64,
        bot_token="Bot test-token-discord",
    )
    adapter = DiscordChannelAdapter(cfg)
    fut1 = adapter._register_pending("req-idem-001")
    fut2 = adapter._register_pending("req-idem-001")
    assert fut1 is fut2, (
        "Two calls with the same request_id MUST return the identical Future; "
        "got two distinct objects — duplicate-request stealing regression."
    )
    # Clean up: cancel the pending future so the adapter can GC cleanly.
    fut1.cancel()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_slack_register_pending_idempotent() -> None:
    """H-2: Slack._register_pending("same-id") twice returns identical Future.

    Guard: mirrors H-1 for the Slack adapter. Both adapters use the same
    single-write-site invariant via _register_pending.
    """
    from envoy.channels.slack import SlackChannelAdapter, SlackChannelConfig

    cfg = SlackChannelConfig(
        primary_channel_id="slack",
        signing_secret="slack-signing-secret-32bytes!!!",
        bot_token="xoxb-test-token",
    )
    adapter = SlackChannelAdapter(cfg)
    fut1 = adapter._register_pending("req-idem-002")
    fut2 = adapter._register_pending("req-idem-002")
    assert fut1 is fut2, (
        "Two calls with the same request_id MUST return the identical Future; "
        "got two distinct objects — duplicate-request stealing regression."
    )
    fut1.cancel()


# ---------------------------------------------------------------------------
# H-5 — Rate limit gate: all three Wave-A adapters raise when quota exhausted
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_discord_rate_limit_gate_raises_when_quota_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-5 Discord: send_message raises RateLimitExceededError when requests_remaining==0.

    Guard: the rate-limit check MUST fire before any outbound HTTP attempt,
    ensuring a saturated quota never results in an uncontrolled burst.
    """
    import io

    from envoy.channels import RateLimitExceededError
    from envoy.channels.discord import DiscordChannelAdapter, DiscordChannelConfig
    from envoy.channels.envelope import MessagePayload, RateLimitStatus

    cfg = DiscordChannelConfig(
        primary_channel_id="discord",
        application_public_key="a" * 64,
        bot_token="Bot test-token-discord",
    )
    adapter = DiscordChannelAdapter(cfg)
    # Manually mark adapter as started so _require_started passes.
    adapter._started = True  # bypass startup I/O for unit-style probe

    async def _zero_rl(self: object) -> RateLimitStatus:
        return RateLimitStatus(
            requests_remaining=0,
            window_resets_at=None,
            soft_quota_warning=False,
        )

    monkeypatch.setattr(type(adapter), "rate_limit_status", _zero_rl)

    with pytest.raises(RateLimitExceededError):
        await adapter.send_message(
            "principal", MessagePayload(kind="text", body="hello")
        )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_slack_rate_limit_gate_raises_when_quota_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-5 Slack: send_message raises RateLimitExceededError when requests_remaining==0."""
    from envoy.channels import RateLimitExceededError
    from envoy.channels.envelope import MessagePayload, RateLimitStatus
    from envoy.channels.slack import SlackChannelAdapter, SlackChannelConfig

    cfg = SlackChannelConfig(
        primary_channel_id="slack",
        signing_secret="slack-signing-secret-32bytes!!!",
        bot_token="xoxb-test-token",
    )
    adapter = SlackChannelAdapter(cfg)
    adapter._started = True

    async def _zero_rl(self: object) -> RateLimitStatus:
        return RateLimitStatus(
            requests_remaining=0,
            window_resets_at=None,
            soft_quota_warning=False,
        )

    monkeypatch.setattr(type(adapter), "rate_limit_status", _zero_rl)

    with pytest.raises(RateLimitExceededError):
        await adapter.send_message(
            "principal", MessagePayload(kind="text", body="hello")
        )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_telegram_rate_limit_gate_raises_when_quota_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-5 Telegram: send_message raises RateLimitExceededError when requests_remaining==0."""
    from envoy.channels import RateLimitExceededError
    from envoy.channels.envelope import MessagePayload, RateLimitStatus
    from envoy.channels.telegram import TelegramChannelAdapter

    adapter = TelegramChannelAdapter(secret_token="valid-secret-token")
    adapter._started = True

    async def _zero_rl(self: object) -> RateLimitStatus:
        return RateLimitStatus(
            requests_remaining=0,
            window_resets_at=None,
            soft_quota_warning=False,
        )

    monkeypatch.setattr(type(adapter), "rate_limit_status", _zero_rl)

    with pytest.raises(RateLimitExceededError):
        await adapter.send_message(
            "principal", MessagePayload(kind="text", body="hello")
        )


# ---------------------------------------------------------------------------
# M-1 — SSRF decimal IP bypass: Discord startup raises ChannelTransportError
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_discord_ssrf_decimal_ip_blocked_at_startup() -> None:
    """M-1: DiscordChannelAdapter startup MUST block decimal-encoded IPs in webhook_url.

    Guard: ``http://2130706433/path`` decodes to 127.0.0.1 — the SSRF guard
    MUST recognise integer-form hostnames and block them unconditionally before
    any outbound connection attempt.
    """
    from envoy.channels.discord import DiscordChannelAdapter, DiscordChannelConfig
    from envoy.channels.errors import ChannelTransportError

    cfg = DiscordChannelConfig(
        primary_channel_id="discord",
        application_public_key="a" * 64,
        bot_token="Bot test-token-discord",
        webhook_url="http://2130706433/hook",  # decimal-encoded 127.0.0.1
    )
    adapter = DiscordChannelAdapter(cfg)
    with pytest.raises(ChannelTransportError):
        await adapter.startup()


# ---------------------------------------------------------------------------
# M-2 — Telegram shutdown clears _pending_grants dict
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_telegram_shutdown_clears_pending_grants() -> None:
    """M-2: TelegramChannelAdapter.shutdown() MUST clear _pending_grants.

    Structural probe: insert a Queue entry, call shutdown(), assert the
    dict is empty. This confirms the cleanup path drains the pending-grant
    registry regardless of Queue state.
    """
    from envoy.channels.telegram import TelegramChannelAdapter

    adapter = TelegramChannelAdapter(secret_token="valid-secret-token")
    adapter._started = True

    # Plant a pending grant entry using a Future (shutdown iterates values
    # and calls .done() / .cancel(); Queue objects lack these methods — the
    # _pending_grants values must be Future-compatible).  The structural
    # probe only cares that the dict is empty after shutdown.
    loop = asyncio.get_event_loop()
    fut: asyncio.Future[str] = loop.create_future()
    adapter._pending_grants["r-pending-shutdown"] = fut  # type: ignore[assignment]

    assert "r-pending-shutdown" in adapter._pending_grants

    await adapter.shutdown()

    assert "r-pending-shutdown" not in adapter._pending_grants
    assert len(adapter._pending_grants) == 0, (
        "shutdown() MUST clear all pending grants; dict is non-empty — "
        "shutdown cleanup regression."
    )


# ---------------------------------------------------------------------------
# M-5 — Startup auth guard: blank credentials raise AuthenticationError
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_discord_blank_bot_token_raises_at_startup() -> None:
    """M-5 Discord: startup() with blank bot_token MUST raise AuthenticationError.

    Guard: empty credentials MUST be rejected before any I/O so an
    improperly-configured adapter cannot silently send unauthenticated
    requests.
    """
    from envoy.channels import AuthenticationError
    from envoy.channels.discord import DiscordChannelAdapter, DiscordChannelConfig

    cfg = DiscordChannelConfig(
        primary_channel_id="discord",
        application_public_key="a" * 64,
        bot_token="",  # blank — MUST raise
    )
    adapter = DiscordChannelAdapter(cfg)
    with pytest.raises(AuthenticationError):
        await adapter.startup()


@pytest.mark.regression
def test_discord_blank_application_public_key_raises_at_construction() -> None:
    """M-5 Discord (application_public_key): blank key is caught at construction time.

    DiscordSigner validates application_public_key at DiscordChannelAdapter.__init__
    time (before startup()), raising ValueError.  This is an earlier-is-better guard —
    misconfigured adapters fail before any object state is established.
    """
    from envoy.channels.discord import DiscordChannelAdapter, DiscordChannelConfig

    cfg = DiscordChannelConfig(
        primary_channel_id="discord",
        application_public_key="",  # blank — MUST raise at construction
        bot_token="Bot test-token-discord",
    )
    with pytest.raises(ValueError, match="application_public_key"):
        DiscordChannelAdapter(cfg)


@pytest.mark.regression
def test_slack_blank_signing_secret_raises_at_construction() -> None:
    """M-5 Slack (signing_secret): blank secret is caught at construction time.

    SlackSigner validates signing_secret at SlackChannelAdapter.__init__ time
    (before startup()), raising ValueError.  Earlier-is-better guard — mirrors
    the Discord application_public_key pattern.
    """
    from envoy.channels.slack import SlackChannelAdapter, SlackChannelConfig

    cfg = SlackChannelConfig(
        primary_channel_id="slack",
        signing_secret="",  # blank — MUST raise at construction
        bot_token="xoxb-test-token",
    )
    with pytest.raises(ValueError, match="signing_secret"):
        SlackChannelAdapter(cfg)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_slack_blank_bot_token_raises_at_startup() -> None:
    """M-5 Slack (bot_token): startup() with blank bot_token MUST raise AuthenticationError."""
    from envoy.channels import AuthenticationError
    from envoy.channels.slack import SlackChannelAdapter, SlackChannelConfig

    cfg = SlackChannelConfig(
        primary_channel_id="slack",
        signing_secret="slack-signing-secret-32bytes!!!",
        bot_token="",  # blank — MUST raise
    )
    adapter = SlackChannelAdapter(cfg)
    with pytest.raises(AuthenticationError):
        await adapter.startup()


@pytest.mark.regression
def test_telegram_blank_secret_token_raises_at_construction() -> None:
    """M-5 Telegram: constructor with blank secret_token MUST raise AuthenticationError.

    Telegram validates secret_token at construction time (not startup) because
    it is the only inbound-webhook authenticator and must be present before any
    object state is established.
    """
    from envoy.channels import AuthenticationError
    from envoy.channels.telegram import TelegramChannelAdapter

    with pytest.raises(AuthenticationError):
        TelegramChannelAdapter(secret_token="")


@pytest.mark.regression
def test_telegram_whitespace_only_secret_token_raises_at_construction() -> None:
    """M-5 Telegram (whitespace): constructor with whitespace-only secret_token MUST raise."""
    from envoy.channels import AuthenticationError
    from envoy.channels.telegram import TelegramChannelAdapter

    with pytest.raises(AuthenticationError):
        TelegramChannelAdapter(secret_token="   ")
