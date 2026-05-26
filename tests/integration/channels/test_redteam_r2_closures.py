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
    def __init__(
        self,
        *,
        request_id: str = "r-r2",
        high_stakes: bool = False,
        body: str = "",
        visible_secret: object | None = None,
        why_asking: str = "",
        consequence_preview: str = "",
        decision_options: tuple[str, ...] = (),
    ) -> None:
        self.request_id = request_id
        self.high_stakes = high_stakes
        self.body = body
        self.visible_secret = visible_secret
        self.why_asking = why_asking
        self.consequence_preview = consequence_preview
        self.decision_options = decision_options


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
                    _Request(request_id="r-1", high_stakes=True, body="x")
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
