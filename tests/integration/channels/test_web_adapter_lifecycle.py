"""Tier-2 wiring: `WebChannelAdapter` lifecycle + Origin allowlist defenses.

Per `specs/channel-adapters.md` § Adapter contract + § Primary-channel
binding + § Network security (T-080). The Origin allowlist + loopback bind
together form the DNS-rebind defense per `rules/security.md`
§ "Network Transport Hardening" (#673 in kailash-py).

Per `rules/testing.md` § Tier 2: real construction + real assertions, no
mocks against adapter internals.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from envoy.channels.envelope import (
    GrantMomentPayload,
    InboundMessage,
    MessagePayload,
    VisibleSecret,
)
from envoy.channels.errors import (
    AlreadyStartedError,
    GrantMomentExpiredError,
    NotPrimaryChannelError,
)
from envoy.channels.web import WebChannelAdapter, WebChannelConfig


def _make_grant(request_id: str | None = None) -> GrantMomentPayload:
    return GrantMomentPayload(
        request_id=request_id or f"r-{uuid.uuid4().hex[:8]}",
        intent_id="i-1",
        decision_options=("approve_once", "approve_author", "deny", "modify"),
        visible_secret=VisibleSecret(phrase="cobalt-marshmallow", icon="🦊"),
        body="Allow OAuth read access?",
        high_stakes=True,
    )


def _make_adapter(primary: str = "web") -> WebChannelAdapter:
    return WebChannelAdapter(WebChannelConfig(primary_channel_id=primary))


@pytest.mark.regression
class TestWebOriginAllowlist:
    """Contract pin: T-080 + #673 DNS-rebind defense.

    Reference: `rules/security.md` § "Network Transport Hardening" + kailash-py
    PR #673 (Nexus `register_websocket(..., allowed_origins=...)`).
    """

    def test_non_loopback_bind_host_refused_at_construction(self) -> None:
        """A bind host that isn't `127.0.0.1` / `::1` / `localhost` MUST refuse."""
        with pytest.raises(ValueError, match="loopback"):
            WebChannelAdapter(WebChannelConfig(primary_channel_id="web", bind_host="0.0.0.0"))

    def test_public_ipv4_bind_refused(self) -> None:
        with pytest.raises(ValueError, match="loopback"):
            WebChannelAdapter(WebChannelConfig(primary_channel_id="web", bind_host="192.168.1.10"))

    def test_wildcard_origin_refused(self) -> None:
        with pytest.raises(ValueError, match="wildcard"):
            WebChannelAdapter(
                WebChannelConfig(
                    primary_channel_id="web",
                    allowed_origins=("*",),
                )
            )

    def test_cross_origin_refused(self) -> None:
        with pytest.raises(ValueError, match="match"):
            WebChannelAdapter(
                WebChannelConfig(
                    primary_channel_id="web",
                    allowed_origins=("https://attacker.example.com",),
                )
            )

    def test_empty_origin_allowlist_refused(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            WebChannelAdapter(
                WebChannelConfig(
                    primary_channel_id="web",
                    allowed_origins=(),
                )
            )

    def test_loopback_with_explicit_port_accepted(self) -> None:
        adapter = WebChannelAdapter(
            WebChannelConfig(
                primary_channel_id="web",
                allowed_origins=("http://localhost:3000", "http://127.0.0.1:8765"),
            )
        )
        assert adapter.channel_id == "web"


@pytest.mark.regression
class TestWebLifecycle:
    """Contract pin: spec § Lifecycle methods."""

    @pytest.mark.asyncio
    async def test_startup_then_shutdown_clean_path(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        assert adapter.channel_id == "web"
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_double_startup_raises_already_started(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            with pytest.raises(AlreadyStartedError):
                await adapter.startup()
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_inbound_queue_yields_injected_message(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            msg = InboundMessage(
                channel_id="web",
                session_id="s-1",
                principal_genesis_id="principal-a",
                direction="inbound",
                content_trust_level="user",
                payload=MessagePayload(kind="text", body="hello"),
                visible_secret_rendered=None,
                timestamp=datetime.now(timezone.utc),
            )
            await adapter._inject_inbound(msg)
            async for received in adapter.receive_message():
                assert received.payload.body == "hello"
                break
        finally:
            await adapter.shutdown()


@pytest.mark.regression
class TestWebGrantMoment:
    """Contract pin: spec § Primary-channel binding (H-03)."""

    @pytest.mark.asyncio
    async def test_grant_moment_primary_only_refuses_when_non_primary(self) -> None:
        adapter = _make_adapter(primary="cli")
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError) as excinfo:
                await adapter.send_grant_moment(
                    "principal-a",
                    _make_grant(),
                    primary_only=True,
                    timeout_seconds=1,
                )
            assert excinfo.value.channel_id == "web"
            assert excinfo.value.primary_channel_id == "cli"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_resolves_via_pending_decision_hook(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        grant = _make_grant("r-resolve")
        try:

            async def resolver() -> None:
                # Yield once so the awaiting task registers the future.
                await asyncio.sleep(0.01)
                await adapter._resolve_pending_decision(grant.request_id, "approve_once")

            send_task = asyncio.create_task(
                adapter.send_grant_moment("principal-a", grant, timeout_seconds=5)
            )
            resolver_task = asyncio.create_task(resolver())
            receipt, _ = await asyncio.gather(send_task, resolver_task)
            assert receipt.decision == "approve_once"
            assert receipt.request_id == grant.request_id
            assert receipt.channel_signature.startswith("web-sig-")
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_timeout_raises_expired(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            with pytest.raises(GrantMomentExpiredError) as excinfo:
                await adapter.send_grant_moment("principal-a", _make_grant(), timeout_seconds=1)
            assert excinfo.value.timeout_seconds == 1
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_shutdown_cancels_pending(self) -> None:
        """Shutdown MUST cancel pending decisions (clean drain semantics)."""
        adapter = _make_adapter()
        await adapter.startup()
        grant = _make_grant("r-shutdown")
        send_task = asyncio.create_task(
            adapter.send_grant_moment("principal-a", grant, timeout_seconds=30)
        )
        # Let send_grant_moment register the pending future.
        await asyncio.sleep(0.05)
        await adapter.shutdown()
        with pytest.raises(GrantMomentExpiredError):
            await send_task


@pytest.mark.regression
class TestWebCapabilities:
    """Contract pin: spec § ChannelCapabilities."""

    def test_capabilities_match_phase_01_table(self) -> None:
        adapter = _make_adapter()
        caps = adapter.capabilities
        assert caps.supports_buttons is True
        assert caps.supports_attachments is True
        assert caps.supports_markdown is True
        assert caps.supports_voice is False
        assert caps.max_message_length == 65536
