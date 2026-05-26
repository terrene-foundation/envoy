"""Tier-2 wiring: `CLIChannelAdapter` lifecycle + send-path contract pins.

Per `specs/channel-adapters.md` § Adapter contract (lines 14-130) and
§ Test location line 230. Exercises startup/shutdown idempotency, the
double-startup `AlreadyStartedError` refusal, send_message payload-too-large
boundary, and the CLI Grant Moment rendering + decision-coercion path.

Per `rules/testing.md` § Tier 2: real I/O via StringIO — no `mock.patch` /
`MagicMock` against adapter internals.
"""

from __future__ import annotations

import io

import pytest

from envoy.channels.cli import CLIChannelAdapter, CLIChannelConfig
from envoy.channels.envelope import (
    GrantMomentPayload,
    MessagePayload,
    VisibleSecret,
)
from envoy.channels.errors import (
    AlreadyStartedError,
    GrantMomentExpiredError,
    NotPrimaryChannelError,
    PayloadTooLargeError,
)


def _make_adapter(
    primary: str = "cli",
    *,
    stdin_text: str = "",
) -> CLIChannelAdapter:
    stdin = io.StringIO(stdin_text)
    stdout = io.StringIO()
    return CLIChannelAdapter(
        CLIChannelConfig(
            primary_channel_id=primary,
            output_stream=stdout,
            input_stream=stdin,
        )
    )


def _make_grant(
    request_id: str = "r-1",
    options: tuple[str, ...] = ("approve_once", "approve_author", "deny", "modify"),
    high_stakes: bool = False,
) -> GrantMomentPayload:
    return GrantMomentPayload(
        request_id=request_id,
        intent_id="i-1",
        decision_options=options,
        visible_secret=VisibleSecret(
            icon="thunderclap", color="amber", phrase="thunderclap-tangerine"
        ),
        body="Allow draft 3 hour focus block?",
        high_stakes=high_stakes,
    )


@pytest.mark.regression
class TestCLILifecycle:
    """Contract pin: spec § Lifecycle methods (lines 20-38)."""

    @pytest.mark.asyncio
    async def test_startup_then_shutdown_clean_path(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        assert adapter.channel_id == "cli"
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_double_startup_raises_already_started(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            with pytest.raises(AlreadyStartedError) as excinfo:
                await adapter.startup()
            assert excinfo.value.channel_id == "cli"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_double_shutdown_is_noop(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        await adapter.shutdown()
        # Second call MUST NOT raise.
        await adapter.shutdown()


@pytest.mark.regression
class TestCLISendMessage:
    """Contract pin: spec § Receive / send (lines 50-62)."""

    @pytest.mark.asyncio
    async def test_send_message_writes_to_output_stream(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            payload = MessagePayload(kind="text", body="hello")
            receipt = await adapter.send_message("principal-a", payload)
            assert receipt.channel_native_id.startswith("cli-")
            assert (adapter._config.output_stream).getvalue().startswith("[text] hello")  # type: ignore[union-attr]
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_send_message_payload_too_large_raises(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            too_big = MessagePayload(kind="text", body="x" * 5000)
            with pytest.raises(PayloadTooLargeError) as excinfo:
                await adapter.send_message("principal-a", too_big)
            assert excinfo.value.channel_id == "cli"
            assert excinfo.value.actual_length == 5000
            assert excinfo.value.max_length == 4096
        finally:
            await adapter.shutdown()


@pytest.mark.regression
class TestCLIGrantMoment:
    """Contract pins: spec § Ritual delivery (lines 68-79) + § Primary-channel binding."""

    @pytest.mark.asyncio
    async def test_grant_moment_accepts_literal_option_name(self) -> None:
        adapter = _make_adapter(stdin_text="approve_once\n")
        await adapter.startup()
        try:
            grant = _make_grant()
            receipt = await adapter.send_grant_moment("principal-a", grant, timeout_seconds=5)
            assert receipt.decision == "approve_once"
            assert receipt.request_id == grant.request_id
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_accepts_numeric_option(self) -> None:
        adapter = _make_adapter(stdin_text="3\n")
        await adapter.startup()
        try:
            receipt = await adapter.send_grant_moment(
                "principal-a", _make_grant(), timeout_seconds=5
            )
            # 1-based index 3 = "deny"
            assert receipt.decision == "deny"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_unknown_response_coerces_to_modify(self) -> None:
        """Security default: an unparseable response MUST NOT silently approve."""
        adapter = _make_adapter(stdin_text="¿qué?\n")
        await adapter.startup()
        try:
            receipt = await adapter.send_grant_moment(
                "principal-a", _make_grant(), timeout_seconds=5
            )
            assert receipt.decision == "modify"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_primary_only_refuses_when_non_primary(self) -> None:
        """H-03 primary-channel binding (spec § Primary-channel binding)."""
        adapter = _make_adapter(primary="web", stdin_text="approve_once\n")
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError) as excinfo:
                await adapter.send_grant_moment(
                    "principal-a", _make_grant(), primary_only=True, timeout_seconds=5
                )
            assert excinfo.value.channel_id == "cli"
            assert excinfo.value.primary_channel_id == "web"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_timeout_raises_expired(self) -> None:
        """Spec line 78: M2-equivalent expiry timeout → GrantMomentExpiredError."""

        class BlockingStream(io.StringIO):
            def readline(self) -> str:  # type: ignore[override]
                # Block forever to force the timeout path.
                import time

                time.sleep(10)
                return ""

        adapter = CLIChannelAdapter(
            CLIChannelConfig(
                primary_channel_id="cli",
                output_stream=io.StringIO(),
                input_stream=BlockingStream(),
            )
        )
        await adapter.startup()
        try:
            with pytest.raises(GrantMomentExpiredError) as excinfo:
                await adapter.send_grant_moment("principal-a", _make_grant(), timeout_seconds=1)
            assert excinfo.value.timeout_seconds == 1
        finally:
            await adapter.shutdown()


@pytest.mark.regression
class TestCLICapabilities:
    """Contract pin: spec § ChannelCapabilities (lines 132-143)."""

    @pytest.mark.asyncio
    async def test_capabilities_match_phase_01_table(self) -> None:
        adapter = _make_adapter()
        caps = adapter.capabilities
        assert caps.supports_buttons is False
        assert caps.supports_attachments is False
        assert caps.supports_markdown is True
        assert caps.supports_voice is False
        assert caps.supports_reactions is False
        assert caps.max_message_length == 4096

    @pytest.mark.asyncio
    async def test_rate_limit_status_reports_unbounded(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            status = await adapter.rate_limit_status()
            assert status.requests_remaining > 0
            assert status.soft_quota_warning is False
        finally:
            await adapter.shutdown()
