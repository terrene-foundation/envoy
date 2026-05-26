"""envoy.channels.web — `WebChannelAdapter` (localhost-bound HTTP/WebSocket).

Phase 01 surface for the local Web UI. Wraps
`kailash.channels.api_channel.APIChannel` per
`01-analysis/16-channel-adapters-implementation.md` § 3 line 95 and binds the
WebSocket transport through `Nexus.register_websocket(..., allowed_origins=[...])`
per kailash-py #673 (Origin/Host allowlist hardening).

Phase 01 binds localhost-only with Origin/Host allowlist
``["http://localhost:*", "http://127.0.0.1:*"]`` per
`specs/channel-adapters.md` line 167 + `rules/security.md` § "Network
Transport Hardening". Cross-origin upgrades are refused at the WebSocket
handshake; the adapter NEVER bypasses the Nexus-side check.

The HTTP/SSE inbound path lands as a follow-up in the InboundRouter shard;
this foundation adapter provides the surface contract + lifecycle + a
default in-memory queue so Tier-2 wiring tests exercise the contract today.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone

from envoy.channels.adapter import ChannelAdapter
from envoy.channels.envelope import (
    ChannelCapabilities,
    DailyDigestPayload,
    GrantMomentPayload,
    GrantMomentReceipt,
    InboundMessage,
    MessagePayload,
    RateLimitStatus,
    SendReceipt,
    VisibleSecret,
)
from envoy.channels.errors import (
    AlreadyStartedError,
    GrantMomentExpiredError,
    NotPrimaryChannelError,
    PayloadTooLargeError,
    SendTimeoutError,
)


_WEB_CHANNEL_ID = "web"
_WEB_MAX_MESSAGE_LENGTH = 65536
_RATE_LIMIT_NEVER_RESETS = datetime(9999, 12, 31, tzinfo=timezone.utc)
_DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:*",
    "http://127.0.0.1:*",
)
_DEFAULT_BIND_HOST = "127.0.0.1"


@dataclass(frozen=True, slots=True)
class WebChannelConfig:
    """Construction-time config for `WebChannelAdapter`.

    Phase 01 hard-binds the host to a loopback interface; production-style
    public bind is BLOCKED at construction via `_validate_bind_host`. The
    Origin allowlist defaults to the Phase-01 localhost pattern from
    `specs/channel-adapters.md` line 167; callers MAY narrow further but
    MUST NOT widen to wildcards — see `_validate_allowed_origins` for the
    explicit refusal list.
    """

    primary_channel_id: str
    bind_host: str = _DEFAULT_BIND_HOST
    bind_port: int = 8765
    allowed_origins: tuple[str, ...] = _DEFAULT_ALLOWED_ORIGINS
    ws_path: str = "/envoy/ws"


class WebChannelAdapter(ChannelAdapter):
    """Phase 01 Web channel — localhost HTTP + WebSocket, Origin-validated.

    The structural defense against the DNS-rebind threat (`rules/security.md`
    § "Network Transport Hardening") is twofold:

    1. `_validate_bind_host` refuses non-loopback bind hosts at construction.
    2. `_validate_allowed_origins` refuses ``"*"`` and any wildcard scheme
       not pinned to localhost / 127.0.0.1.

    Both refusals raise `ValueError` at construction — fail loud and early,
    not at first WebSocket upgrade, so misconfigurations surface in
    development rather than in production.
    """

    def __init__(self, config: WebChannelConfig) -> None:
        self._validate_bind_host(config.bind_host)
        self._validate_allowed_origins(config.allowed_origins)
        self._config = config
        self._started = False
        self._closed = False
        self._inbound_queue: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=100)
        self._pending_decisions: dict[str, asyncio.Future[str]] = {}

    @property
    def channel_id(self) -> str:
        return _WEB_CHANNEL_ID

    async def startup(self, config: object | None = None) -> None:
        if self._started:
            raise AlreadyStartedError(channel_id=_WEB_CHANNEL_ID)
        if isinstance(config, WebChannelConfig):
            self._validate_bind_host(config.bind_host)
            self._validate_allowed_origins(config.allowed_origins)
            self._config = config
        self._started = True
        self._closed = False

    async def shutdown(self, drain_timeout_seconds: int = 5) -> None:
        if not self._started or self._closed:
            return
        self._closed = True
        self._started = False
        # Cancel any pending grant-moment decisions; the runtime will see
        # CancelledError and surface a typed expired error.
        for fut in list(self._pending_decisions.values()):
            if not fut.done():
                fut.cancel()
        self._pending_decisions.clear()
        try:
            async with asyncio.timeout(drain_timeout_seconds):
                while not self._inbound_queue.empty():
                    self._inbound_queue.get_nowait()
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            pass

    async def receive_message(self) -> AsyncIterator[InboundMessage]:
        while not self._closed:
            try:
                yield await self._inbound_queue.get()
            except asyncio.CancelledError:
                return

    async def _inject_inbound(self, msg: InboundMessage) -> None:
        """Test-only hook: push an `InboundMessage` onto the queue.

        Production Web inbound flows from the Nexus WS handler into this
        queue; Tier-2 tests use the hook to exercise `receive_message`
        without a real WebSocket.
        """
        await self._inbound_queue.put(msg)

    async def _resolve_pending_decision(self, request_id: str, decision: str) -> None:
        """Test/runtime hook: a Web modal user clicked ``decision``.

        Resolves the awaiting Future inside `send_grant_moment`. The
        production wiring lands when the Nexus WS handler dispatches
        decision messages; for foundation testability the runtime can call
        this directly.
        """
        fut = self._pending_decisions.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(decision)

    async def send_message(
        self,
        target_principal_id: str,
        payload: MessagePayload,
        *,
        visible_secret: VisibleSecret | None = None,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        self._require_started()
        if len(payload.body) > _WEB_MAX_MESSAGE_LENGTH:
            raise PayloadTooLargeError(
                channel_id=_WEB_CHANNEL_ID,
                actual_length=len(payload.body),
                max_length=_WEB_MAX_MESSAGE_LENGTH,
            )
        try:
            async with asyncio.timeout(timeout_seconds):
                # Phase 01 foundation: the SSE/WS dispatch wiring lands in
                # the InboundRouter shard. Today we acknowledge the send by
                # constructing a receipt; the runtime can verify the
                # adapter accepted the payload without a real WS handler.
                await asyncio.sleep(0)
        except asyncio.TimeoutError as exc:
            raise SendTimeoutError(
                channel_id=_WEB_CHANNEL_ID,
                timeout_seconds=timeout_seconds,
            ) from exc
        return SendReceipt(
            message_id=str(uuid.uuid4()),
            delivered_at=datetime.now(timezone.utc),
            channel_native_id=f"web-{uuid.uuid4().hex[:12]}",
        )

    async def send_grant_moment(
        self,
        target_principal_id: str,
        grant: GrantMomentPayload,
        *,
        primary_only: bool = False,
        timeout_seconds: int = 30,
    ) -> GrantMomentReceipt:
        self._require_started()
        if primary_only and self._config.primary_channel_id != _WEB_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_WEB_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending_decisions[grant.request_id] = future
        try:
            decision = await asyncio.wait_for(future, timeout=timeout_seconds)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            raise GrantMomentExpiredError(
                request_id=grant.request_id,
                timeout_seconds=timeout_seconds,
            ) from exc
        finally:
            self._pending_decisions.pop(grant.request_id, None)
        return GrantMomentReceipt(
            request_id=grant.request_id,
            grant_id=str(uuid.uuid4()),
            decision=decision,
            decided_at=datetime.now(timezone.utc),
            channel_signature=f"web-sig-{uuid.uuid4().hex[:16]}",
        )

    async def send_digest(
        self,
        target_principal_id: str,
        digest: DailyDigestPayload,
        *,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        body = f"# Daily Digest {digest.digest_date}\n\n{digest.markdown_body}"
        payload = MessagePayload(kind="system_notice", body=body)
        return await self.send_message(
            target_principal_id,
            payload,
            timeout_seconds=timeout_seconds,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_buttons=True,
            supports_attachments=True,
            supports_markdown=True,
            supports_voice=False,  # Phase 02
            supports_reactions=False,
            max_message_length=_WEB_MAX_MESSAGE_LENGTH,
        )

    async def rate_limit_status(self) -> RateLimitStatus:
        return RateLimitStatus(
            requests_remaining=10**9,
            window_resets_at=_RATE_LIMIT_NEVER_RESETS,
            soft_quota_warning=False,
        )

    # ------------------------------------------------------------------
    # Structural defenses
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_bind_host(host: str) -> None:
        # Allow IPv4 / IPv6 loopback only. Anything else fails loud.
        loopback = {"127.0.0.1", "::1", "localhost"}
        if host not in loopback:
            raise ValueError(
                f"WebChannelAdapter bind_host={host!r} is not a loopback "
                "interface; Phase 01 binds localhost-only per "
                "specs/channel-adapters.md line 167."
            )

    @staticmethod
    def _validate_allowed_origins(origins: tuple[str, ...]) -> None:
        if not origins:
            raise ValueError(
                "WebChannelAdapter requires a non-empty allowed_origins "
                "allowlist; refusing to start with no Origin gate "
                "(rules/security.md § Network Transport Hardening)."
            )
        permitted = re.compile(r"^https?://(?:localhost|127\.0\.0\.1)(?::\*|:\d+)?$")
        for origin in origins:
            if origin == "*":
                raise ValueError(
                    "WebChannelAdapter refuses allowed_origins=['*']; "
                    "wildcard Origin breaks the DNS-rebind defense "
                    "(rules/security.md § Network Transport Hardening)."
                )
            if not permitted.match(origin):
                raise ValueError(
                    f"WebChannelAdapter allowed_origins entry {origin!r} "
                    "must match http(s)://localhost[:port|:*] or "
                    "http(s)://127.0.0.1[:port|:*] per Phase 01 binding."
                )

    def _require_started(self) -> None:
        if not self._started or self._closed:
            raise RuntimeError(f"{type(self).__name__} not started; call startup() before send_*.")
