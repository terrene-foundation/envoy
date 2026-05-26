"""Tier-2: pins for /redteam R1 same-shard closures (PR #42).

Round-1 audit (3 axes — security + reviewer + spec-compliance) surfaced 1
CRITICAL + 8 HIGH + 15 MEDIUM + 8 LOW findings. Per `rules/autonomous-execution.md`
MUST Rule 4 the closures landed same-shard; these tests pin the structural
defenses introduced by that fix so they cannot regress silently.

Each test docstring names the R1 finding it pins (e.g. ``H1-security``).
"""

from __future__ import annotations

import asyncio
import ast
import io
import logging
import pathlib

import pytest

from envoy.channels import (
    ChannelAdapter,
    CLIChannelAdapter,
    InvalidDecisionError,
    NotStartedError,
    OverflowDropEvent,
    PendingDecisionsCeilingError,
    PhaseDeferredError,
    WebChannelAdapter,
)
from envoy.channels.cli import CLIChannelConfig
from envoy.channels.envelope import (
    GrantMomentPayload,
    InboundMessage,
    MessagePayload,
    SendReceipt,
    VisibleSecret,
)
from envoy.channels.errors import (
    AlreadyStartedError,
    AuthenticationError,
    ChannelTransportError,
    GrantMomentExpiredError,
    NotPrimaryChannelError,
    PrincipalNotFoundError,
    RateLimitExceededError,
    SendTimeoutError,
    StartupTimeoutError,
)
from envoy.channels.web import WebChannelConfig
from envoy.trust.types import VisibleSecret as TrustVisibleSecret


def _make_grant(
    request_id: str = "r-1",
    *,
    high_stakes: bool = False,
    options: tuple[str, ...] = ("approve_once", "approve_author", "deny", "modify"),
) -> GrantMomentPayload:
    return GrantMomentPayload(
        request_id=request_id,
        intent_id="i-1",
        decision_options=options,
        visible_secret=VisibleSecret(icon="bolt", color="amber", phrase="bolt-amber-mango"),
        body="Allow the action?",
        high_stakes=high_stakes,
    )


# ---------------------------------------------------------------------------
# H1-security / M5-reviewer — high_stakes defense-in-depth on primary binding
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestHighStakesDefenseInDepth:
    """Pin: high_stakes=True auto-gates the primary-channel binding.

    Spec lines 183-185 mandate that high-stakes Grant Moments are approvable
    ONLY on the user's primary channel. R1 found the adapter relied entirely
    on the caller passing `primary_only=True`; if the runtime forgot, a
    non-primary channel could collect the decision. The closure makes the
    adapter ALSO refuse when `grant.high_stakes is True`, regardless of the
    kwarg.
    """

    @pytest.mark.asyncio
    async def test_cli_high_stakes_refuses_non_primary_even_without_primary_only(
        self,
    ) -> None:
        adapter = CLIChannelAdapter(
            CLIChannelConfig(
                primary_channel_id="web",  # CLI is NOT primary
                output_stream=io.StringIO(),
                input_stream=io.StringIO("approve_once\n"),
            )
        )
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError) as excinfo:
                await adapter.send_grant_moment(
                    "principal-a",
                    _make_grant(high_stakes=True),
                    primary_only=False,  # caller "forgot" the kwarg
                    timeout_seconds=5,
                )
            assert excinfo.value.channel_id == "cli"
            assert excinfo.value.primary_channel_id == "web"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_web_high_stakes_refuses_non_primary_even_without_primary_only(
        self,
    ) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="cli"))
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError):
                await adapter.send_grant_moment(
                    "principal-a",
                    _make_grant(high_stakes=True),
                    primary_only=False,
                    timeout_seconds=1,
                )
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# H2-security — OverflowDropEvent on inbound queue overflow
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestInboundOverflowDropsAndAudits:
    """Pin: queue overflow drops the message and emits a WARN log.

    Pre-fix the inbound queue path was `await queue.put(msg)` which blocked
    indefinitely at the 100-msg ceiling — silent backpressure + no audit
    trail. Per spec line 46 the contract is drop-with-`OverflowDropEvent`,
    not block.
    """

    @pytest.mark.asyncio
    async def test_cli_inbound_overflow_drops_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="cli"))
        await adapter.startup()
        try:
            base = InboundMessage(
                channel_id="cli",
                session_id="s-overflow",
                principal_genesis_id="p",
                direction="inbound",
                content_trust_level="user",
                payload=MessagePayload(kind="text", body="x"),
                visible_secret_rendered=None,
                timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )
            # Fill the queue to its 100-msg ceiling.
            for _ in range(100):
                await adapter._inject_inbound(base)
            # The 101st injection MUST NOT block AND MUST emit a WARN.
            with caplog.at_level(logging.WARNING, logger="envoy.channels.cli"):
                await asyncio.wait_for(adapter._inject_inbound(base), timeout=2)
            assert any(
                "overflow_drop" in rec.message for rec in caplog.records
            ), "WARN log MUST fire on overflow_drop"
        finally:
            await adapter.shutdown()

    def test_overflow_drop_event_carries_dropped_count(self) -> None:
        evt = OverflowDropEvent(channel_id="cli", dropped_count=5)
        assert evt.dropped_count == 5
        assert evt.channel_id == "cli"


# ---------------------------------------------------------------------------
# H3-security / H3-reviewer — Web send_message raises PhaseDeferredError
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestWebSendMessageRefuses:
    """Pin: `WebChannelAdapter.send_message` raises `PhaseDeferredError`.

    Pre-fix the method returned a `SendReceipt` for a no-op send — the
    "fake dispatch" pattern explicitly listed in `rules/zero-tolerance.md`
    Rule 2's BLOCKED corpus. The InboundRouter shard wires the SSE/WS
    dispatch; until then the surface MUST refuse with a typed error.
    """

    @pytest.mark.asyncio
    async def test_web_send_message_raises_phase_deferred(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            with pytest.raises(PhaseDeferredError) as excinfo:
                await adapter.send_message(
                    "principal-a",
                    MessagePayload(kind="text", body="hi"),
                    timeout_seconds=1,
                )
            assert excinfo.value.method_name == "WebChannelAdapter.send_message"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_web_send_digest_raises_phase_deferred_via_delegation(
        self,
    ) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            from envoy.channels.envelope import DailyDigestPayload

            digest = DailyDigestPayload(digest_date="2026-05-26", markdown_body="body")
            with pytest.raises(PhaseDeferredError):
                await adapter.send_digest("principal-a", digest)
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# H4-security — wildcard ports refused
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestPortWildcardRefusal:
    """Pin: `:*` port wildcards refused at construction.

    Pre-fix the default Origin allowlist used `http://localhost:*` which
    relied on the kailash-py #673 matcher's glob semantics — unaudited.
    The closure refuses wildcards and ships explicit dev ports.
    """

    def test_star_port_wildcard_origin_refused(self) -> None:
        with pytest.raises(ValueError, match="wildcard"):
            WebChannelAdapter(
                WebChannelConfig(
                    primary_channel_id="web",
                    allowed_origins=("http://localhost:*",),
                )
            )

    def test_default_origins_contain_no_wildcards(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        # All defaults MUST be literal `<scheme>://<host>:<port>` strings.
        from envoy.channels.web import _DEFAULT_ALLOWED_ORIGINS

        for origin in _DEFAULT_ALLOWED_ORIGINS:
            assert "*" not in origin, (
                f"default origin {origin!r} contains a wildcard; "
                "kailash-py #673 matcher semantics not pinned by this contract"
            )
        # Sanity: every default starts with http:// + a loopback host + a port.
        for origin in _DEFAULT_ALLOWED_ORIGINS:
            assert origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")
        assert adapter.channel_id == "web"

    def test_explicit_numeric_port_accepted(self) -> None:
        adapter = WebChannelAdapter(
            WebChannelConfig(
                primary_channel_id="web",
                allowed_origins=("http://localhost:5173", "http://127.0.0.1:3000"),
            )
        )
        assert adapter.channel_id == "web"


# ---------------------------------------------------------------------------
# H1-spec — VisibleSecret canonicalised on envoy.trust.types
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestVisibleSecretCanonical:
    """Pin: channels envelope re-exports `envoy.trust.types.VisibleSecret`.

    Pre-fix the channels envelope shipped a 2-field duplicate. The closure
    drops the duplicate and re-exports the canonical 3-field shape.
    """

    def test_visible_secret_is_canonical_trust_type(self) -> None:
        assert VisibleSecret is TrustVisibleSecret

    def test_visible_secret_carries_icon_color_phrase(self) -> None:
        vs = VisibleSecret(icon="i", color="c", phrase="p")
        assert vs.icon == "i"
        assert vs.color == "c"
        assert vs.phrase == "p"


# ---------------------------------------------------------------------------
# H-1/H-2-reviewer — render_grant_moment satisfies ChannelAdapterProtocol
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRenderGrantMomentBridge:
    """Pin: every adapter implements `render_grant_moment` (M1 dispatch surface).

    Pre-fix the new `ChannelAdapter` ABC exposed only `send_grant_moment`;
    the pre-existing `ChannelAdapterProtocol` in `envoy.grant_moment` required
    `render_grant_moment`. The closure adds `render_grant_moment` as an
    abstract method so both surfaces co-exist (one full ritual + one M1
    render-only).
    """

    def test_channel_adapter_abc_has_render_grant_moment(self) -> None:
        assert hasattr(ChannelAdapter, "render_grant_moment")
        assert callable(ChannelAdapter.render_grant_moment)

    def test_cli_satisfies_channel_adapter_protocol_shape(self) -> None:
        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="cli"))
        from envoy.grant_moment.channel_handoff import ChannelAdapterProtocol

        # Protocol structural check — `isinstance` against runtime_checkable.
        assert isinstance(adapter, ChannelAdapterProtocol)

    def test_web_satisfies_channel_adapter_protocol_shape(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        from envoy.grant_moment.channel_handoff import ChannelAdapterProtocol

        assert isinstance(adapter, ChannelAdapterProtocol)


# ---------------------------------------------------------------------------
# M-3-spec / M-2-reviewer — NotStartedError replaces RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestNotStartedTyped:
    """Pin: `_require_started` raises typed `NotStartedError`."""

    @pytest.mark.asyncio
    async def test_cli_send_before_startup_raises_not_started(self) -> None:
        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="cli"))
        with pytest.raises(NotStartedError) as excinfo:
            await adapter.send_message("principal-a", MessagePayload(kind="text", body="hi"))
        assert excinfo.value.channel_id == "cli"
        assert excinfo.value.method_name == "send_message"

    @pytest.mark.asyncio
    async def test_web_send_before_startup_raises_not_started(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        with pytest.raises(NotStartedError):
            await adapter.send_grant_moment("p", _make_grant(), timeout_seconds=1)


# ---------------------------------------------------------------------------
# M1-reviewer — GrantMomentPayload empty options rejected at construction
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestGrantMomentPayloadValidation:
    """Pin: empty `decision_options` raises `ValueError` at construction."""

    def test_empty_decision_options_refused(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            GrantMomentPayload(
                request_id="r-1",
                intent_id="i-1",
                decision_options=(),
                visible_secret=VisibleSecret(icon="i", color="c", phrase="p"),
                body="b",
                high_stakes=False,
            )


# ---------------------------------------------------------------------------
# M1-security — visible-secret never appears in send_message log/output
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestVisibleSecretLogRedaction:
    """Pin: T-018 visible-secret never leaks via send_message log/output.

    Per `rules/security.md` § "No secrets in logs" + spec lines 188-192.
    """

    @pytest.mark.asyncio
    async def test_send_message_does_not_render_visible_secret_phrase(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        stdout = io.StringIO()
        adapter = CLIChannelAdapter(
            CLIChannelConfig(
                primary_channel_id="cli",
                output_stream=stdout,
                input_stream=io.StringIO(),
            )
        )
        await adapter.startup()
        try:
            secret = VisibleSecret(icon="totem", color="indigo", phrase="quasar-mojito")
            with caplog.at_level(logging.DEBUG, logger="envoy.channels.cli"):
                await adapter.send_message(
                    "principal-a",
                    MessagePayload(kind="text", body="hello"),
                    visible_secret=secret,
                )
            # The icon MAY appear (it's the visual provenance hint); the
            # phrase MUST NOT.
            assert "quasar-mojito" not in stdout.getvalue()
            for record in caplog.records:
                assert "quasar-mojito" not in record.getMessage()
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# M-5-spec / L-4-reviewer — __all__ AST count pin
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestAllInvariant:
    """Pin: `__all__` counts derived structurally — not via grep."""

    @staticmethod
    def _all_len(path: str) -> int:
        tree = ast.parse(pathlib.Path(path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
            ):
                value = node.value
                assert isinstance(value, ast.List)
                return len(value.elts)
        raise AssertionError(f"__all__ not found in {path}")

    def test_channels_init_all_count(self) -> None:
        # 3 ABC/concrete + 12 envelope payloads/dataclasses + 16 errors = 31
        # (R2 closures: PendingDecisionsCeilingError + InvalidDecisionError
        # added on top of the R1 NotStartedError + PhaseDeferredError hygiene.)
        assert self._all_len("envoy/channels/__init__.py") == 31

    def test_errors_module_all_count(self) -> None:
        # 1 base + 11 spec errors + 4 hygiene
        # (NotStartedError + PendingDecisionsCeilingError +
        #  InvalidDecisionError + PhaseDeferredError) = 16
        assert self._all_len("envoy/channels/errors.py") == 16


# ---------------------------------------------------------------------------
# M-4-spec — smoke tests for error classes that have no test exposure
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestErrorTaxonomySmoke:
    """Pin: every spec § Error taxonomy class is constructable + carries fields."""

    def test_startup_timeout_carries_channel_id_and_timeout(self) -> None:
        err = StartupTimeoutError(channel_id="telegram", timeout_seconds=10)
        assert err.channel_id == "telegram"
        assert err.timeout_seconds == 10

    def test_already_started_carries_channel_id(self) -> None:
        err = AlreadyStartedError(channel_id="slack")
        assert err.channel_id == "slack"

    def test_channel_transport_carries_channel_id(self) -> None:
        underlying = ConnectionError("boom")
        err = ChannelTransportError(channel_id="discord", underlying=underlying)
        assert err.channel_id == "discord"
        assert err.underlying is underlying

    def test_send_timeout_carries_timeout_seconds(self) -> None:
        err = SendTimeoutError(channel_id="cli", timeout_seconds=30)
        assert err.timeout_seconds == 30

    def test_rate_limit_carries_retry_after(self) -> None:
        err = RateLimitExceededError(channel_id="telegram", retry_after_seconds=42)
        assert err.retry_after_seconds == 42

    def test_principal_not_found_carries_target(self) -> None:
        err = PrincipalNotFoundError(channel_id="slack", target_principal_id="user-7")
        assert err.target_principal_id == "user-7"

    def test_authentication_carries_credential_kind(self) -> None:
        err = AuthenticationError(channel_id="slack", credential_kind="bot_token")
        assert err.credential_kind == "bot_token"

    def test_grant_moment_expired_carries_request_id(self) -> None:
        err = GrantMomentExpiredError(request_id="r-7", timeout_seconds=30)
        assert err.request_id == "r-7"


# ---------------------------------------------------------------------------
# M-4-reviewer — RateLimitStatus.window_resets_at is Optional[datetime]
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_rate_limit_status_window_is_none_when_unlimited() -> None:
    cli = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="cli"))
    web = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
    await cli.startup()
    await web.startup()
    try:
        assert (await cli.rate_limit_status()).window_resets_at is None
        assert (await web.rate_limit_status()).window_resets_at is None
    finally:
        await cli.shutdown()
        await web.shutdown()


# ---------------------------------------------------------------------------
# M3-security — _pending_decisions bounded
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestPendingDecisionsBounded:
    """Pin: `_pending_decisions` enforces a hard ceiling.

    Pre-fix the dict was unbounded — a runtime that fires `send_grant_moment`
    faster than decisions resolve grows it without bound. Ceiling refuses
    new sends until existing ones drain.
    """

    @pytest.mark.asyncio
    async def test_send_grant_moment_refuses_past_ceiling(self) -> None:
        from envoy.channels import web as web_mod

        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            # Pre-load the dict to one-shy-of-ceiling.
            loop = asyncio.get_running_loop()
            for i in range(web_mod._MAX_PENDING_DECISIONS):
                adapter._pending_decisions[f"pre-{i}"] = loop.create_future()
            with pytest.raises(PendingDecisionsCeilingError) as excinfo:
                await adapter.send_grant_moment("p", _make_grant("over-ceiling"), timeout_seconds=1)
            assert excinfo.value.channel_id == "web"
            assert excinfo.value.ceiling == web_mod._MAX_PENDING_DECISIONS
        finally:
            # Cancel all pre-loaded futures so shutdown doesn't hang.
            for fut in adapter._pending_decisions.values():
                if not fut.done():
                    fut.cancel()
            await adapter.shutdown()
