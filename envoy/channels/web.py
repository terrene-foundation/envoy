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
import hashlib
import logging
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, cast

from envoy.channels.adapter import ChannelAdapter
from envoy.channels.envelope import (
    ChannelCapabilities,
    DailyDigestPayload,
    GrantMomentDecision,
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
    InvalidDecisionError,
    NotPrimaryChannelError,
    NotStartedError,
    OverflowDropEvent,
    PayloadTooLargeError,
    PendingDecisionsCeilingError,
    PhaseDeferredError,
)

if TYPE_CHECKING:
    from envoy.grant_moment.runtime import GrantMomentRequest

logger = logging.getLogger(__name__)


_WEB_CHANNEL_ID = "web"
_WEB_MAX_MESSAGE_LENGTH = 65536
_MAX_PENDING_DECISIONS = 1000
_DEFAULT_DEV_PORTS: tuple[int, ...] = (3000, 5173, 8000, 8080, 8765)
_DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = tuple(
    f"{scheme}://{host}:{port}"
    for scheme in ("http",)
    for host in ("localhost", "127.0.0.1")
    for port in _DEFAULT_DEV_PORTS
)
# Module-load assertion per /redteam R2 MED-R2-04: if a future maintainer
# empties `_DEFAULT_DEV_PORTS` the validation would still catch the empty
# allowlist at construction, but the failure would surface to every consumer.
# Fail loudly at import-time instead.
assert _DEFAULT_ALLOWED_ORIGINS, (
    "_DEFAULT_DEV_PORTS produced an empty _DEFAULT_ALLOWED_ORIGINS tuple; "
    "WebChannelAdapter would refuse to start with the default config."
)
_DEFAULT_BIND_HOST = "127.0.0.1"

# Closed vocabulary for `GrantMomentDecision` Literal — enforced at the
# adapter boundary on every decision crossing into the M2→M3 flow per
# /redteam R2 HIGH-R2-03 closure. Synchronised with
# `envoy.channels.envelope.GrantMomentDecision`.
_ALLOWED_DECISIONS: frozenset[str] = frozenset(
    {"approve_once", "approve_and_author", "approve_author", "deny", "modify"}
)


def _hash_pii(value: str) -> str:
    """SHA-256 hex digest truncated to 8 chars for PII-adjacent log fields.

    Per /redteam R2 MED-R2-07/08: `session_id` + `target_principal_id` are
    principal-correlatable; log aggregators have broader access than the
    production database, so the raw values MUST NOT bleed into WARN/INFO
    log lines (`rules/observability.md` Rule 8 + `rules/security.md`
    § "No secrets in logs").
    """
    return hashlib.sha256(value.encode()).hexdigest()[:8]


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
        # Per /redteam R2 MED-R2-05: a non-`WebChannelConfig` config arg
        # is loud-refused. The pre-R2 path silently dropped non-matching
        # types, letting callers think they had updated config when the
        # adapter still ran with __init__-time values.
        if config is not None and not isinstance(config, WebChannelConfig):
            raise TypeError(
                f"WebChannelAdapter.startup expected WebChannelConfig "
                f"(or None to reuse construction config), got "
                f"{type(config).__name__}."
            )
        if isinstance(config, WebChannelConfig):
            self._validate_bind_host(config.bind_host)
            self._validate_allowed_origins(config.allowed_origins)
            self._config = config
        self._started = True
        self._closed = False
        logger.info("channel.startup", extra={"channel_id": _WEB_CHANNEL_ID})

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
        # In-flight `send_grant_moment` tasks observe their futures cancelled
        # above; they will raise `GrantMomentExpiredError` cleanly. The
        # InboundRouter shard adds a separate drain for SSE/WS outbound
        # tasks when `send_message` is wired (today it raises PhaseDeferredError
        # so no outbound task can be in flight).
        try:
            async with asyncio.timeout(drain_timeout_seconds):
                while not self._inbound_queue.empty():
                    self._inbound_queue.get_nowait()
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            pass
        logger.info("channel.shutdown", extra={"channel_id": _WEB_CHANNEL_ID})

    async def receive_message(self) -> AsyncIterator[InboundMessage]:
        while not self._closed:
            try:
                yield await self._inbound_queue.get()
            except asyncio.CancelledError:
                return

    async def _inject_inbound(self, msg: InboundMessage) -> None:
        """Test/runtime hook: push an `InboundMessage` onto the queue.

        Production Web inbound flows from the Nexus WS handler into this
        queue; Tier-2 tests use the hook to exercise `receive_message`
        without a real WebSocket. On queue overflow, the message is dropped
        and an `OverflowDropEvent` WARN log fires per spec line 46.
        """
        try:
            self._inbound_queue.put_nowait(msg)
        except asyncio.QueueFull:
            drop = OverflowDropEvent(channel_id=_WEB_CHANNEL_ID, dropped_count=1)
            logger.warning(
                "channel.inbound.overflow_drop",
                extra={
                    "channel_id": _WEB_CHANNEL_ID,
                    "session_hash": _hash_pii(msg.session_id),
                    "dropped_count": drop.dropped_count,
                },
            )

    async def _resolve_pending_decision(self, request_id: str, decision: str) -> None:
        """Test/runtime hook: a Web modal user clicked ``decision``.

        Resolves the awaiting Future inside `send_grant_moment` or
        `render_grant_moment`. The production wiring lands when the Nexus
        WS handler dispatches decision messages; for foundation testability
        the runtime can call this directly.

        Per /redteam R2 HIGH-R2-03 closure: `decision` is validated against
        `_ALLOWED_DECISIONS` BEFORE the future resolves. Out-of-vocabulary
        decisions raise `InvalidDecisionError` so a misconfigured WS handler
        / injected message / runtime bug cannot inject `"force_approve"` or
        any prose string into the M2→M3 flow.
        """
        if decision not in _ALLOWED_DECISIONS:
            raise InvalidDecisionError(
                channel_id=_WEB_CHANNEL_ID,
                decision=decision,
                allowed=tuple(sorted(_ALLOWED_DECISIONS)),
            )
        fut = self._pending_decisions.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(decision)

    def _register_pending(self, request_id: str) -> asyncio.Future[str]:
        """Single write site for `_pending_decisions` (ceiling-enforced).

        Both `send_grant_moment` and `render_grant_moment` write to
        `_pending_decisions`; the pre-R2 path ceiling-checked only the
        former. The helper consolidates the check so the bound applies
        to every write site uniformly (per /redteam R2 HIGH-R2-01 closure).
        Idempotent: re-registering the same `request_id` returns the
        existing Future without re-counting.
        """
        existing = self._pending_decisions.get(request_id)
        if existing is not None:
            return existing
        if len(self._pending_decisions) >= _MAX_PENDING_DECISIONS:
            raise PendingDecisionsCeilingError(
                channel_id=_WEB_CHANNEL_ID,
                ceiling=_MAX_PENDING_DECISIONS,
                current_count=len(self._pending_decisions),
            )
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending_decisions[request_id] = future
        return future

    async def send_message(
        self,
        target_principal_id: str,
        payload: MessagePayload,
        *,
        visible_secret: VisibleSecret | None = None,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        # Phase 01 deferral per `rules/zero-tolerance.md` Rule 2 (no fake
        # dispatch). The SSE/WS dispatch hook lands in the InboundRouter
        # shard; until then this surface MUST refuse with a typed error
        # rather than return a success receipt for a no-op send. Both args
        # are inspected so the refusal is callable-shape-compatible: the
        # caller cannot mistake `PhaseDeferredError` for "delivered."
        self._require_started("send_message")
        if len(payload.body) > _WEB_MAX_MESSAGE_LENGTH:
            raise PayloadTooLargeError(
                channel_id=_WEB_CHANNEL_ID,
                actual_length=len(payload.body),
                max_length=_WEB_MAX_MESSAGE_LENGTH,
            )
        _ = (target_principal_id, visible_secret, timeout_seconds)
        raise PhaseDeferredError(
            method_name="WebChannelAdapter.send_message",
            deferred_to_phase="Wave-4 InboundRouter shard",
        )

    async def send_grant_moment(
        self,
        target_principal_id: str,
        grant: GrantMomentPayload,
        *,
        primary_only: bool = False,
        timeout_seconds: int = 30,
    ) -> GrantMomentReceipt:
        self._require_started("send_grant_moment")
        # H-03 primary-channel binding (spec lines 183-185) — defense-in-depth:
        # `grant.high_stakes is True` MUST ALSO require the primary channel
        # even when `primary_only=False`.
        must_be_primary = primary_only or grant.high_stakes
        if must_be_primary and self._config.primary_channel_id != _WEB_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_WEB_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )
        # Bounded in-flight pending-decision map per /redteam R1 M3 + R2 HIGH-R2-01:
        # routed through `_register_pending` so the ceiling enforces on every
        # write site (this method AND `render_grant_moment`).
        future = self._register_pending(grant.request_id)
        logger.info(
            "channel.send_grant_moment.start",
            extra={
                "channel_id": _WEB_CHANNEL_ID,
                "request_id": grant.request_id,
                "high_stakes": grant.high_stakes,
            },
        )
        try:
            decision = await asyncio.wait_for(future, timeout=timeout_seconds)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            logger.warning(
                "channel.send_grant_moment.expired",
                extra={
                    "channel_id": _WEB_CHANNEL_ID,
                    "request_id": grant.request_id,
                    "timeout_seconds": timeout_seconds,
                },
            )
            raise GrantMomentExpiredError(
                request_id=grant.request_id,
                timeout_seconds=timeout_seconds,
            ) from exc
        finally:
            self._pending_decisions.pop(grant.request_id, None)
        return GrantMomentReceipt(
            request_id=grant.request_id,
            grant_id=str(uuid.uuid4()),
            decision=cast("GrantMomentDecision", decision),
            decided_at=datetime.now(timezone.utc),
            channel_signature=f"web-sig-{uuid.uuid4().hex[:16]}",
        )

    async def render_grant_moment(self, request: "GrantMomentRequest") -> None:
        """M1 render-only — satisfies `ChannelAdapterProtocol`.

        Foundation shard: registers a pending-decision Future and returns;
        the WS handler resolves the future via `_resolve_pending_decision`
        when the user clicks the modal. Distinct from `send_grant_moment`
        (which awaits the decision inline).

        Per /redteam R2 HIGH-R2-02 closure: H-03 primary-channel binding
        is enforced HERE too — `request.high_stakes is True` on a non-primary
        adapter raises `NotPrimaryChannelError`. Pre-R2 the check lived only
        on `send_grant_moment`; the asymmetry meant the M1 dispatch path
        could land high-stakes renders on non-primary adapters whenever the
        external `ChannelHandoff.dispatch` guard was bypassed or buggy.
        """
        self._require_started("render_grant_moment")
        request_id = getattr(request, "request_id", None)
        if request_id is None:
            # No correlation key — cannot register a pending decision; the
            # runtime guarantees `request_id` is present per spec, so this
            # is structural defense, not user-input handling.
            raise ValueError("GrantMomentRequest is missing request_id; cannot dispatch.")
        high_stakes = bool(getattr(request, "high_stakes", False))
        if high_stakes and self._config.primary_channel_id != _WEB_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_WEB_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )
        # Per /redteam R2 HIGH-R2-01 closure: registration goes through the
        # ceiling-enforced helper, NOT direct dict assignment.
        self._register_pending(request_id)
        logger.info(
            "channel.render_grant_moment",
            extra={
                "channel_id": _WEB_CHANNEL_ID,
                "request_id": request_id,
                "high_stakes": high_stakes,
            },
        )

    async def send_digest(
        self,
        target_principal_id: str,
        digest: DailyDigestPayload,
        *,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        # send_digest delegates to send_message which currently raises
        # PhaseDeferredError until the InboundRouter shard wires SSE/WS.
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
            window_resets_at=None,
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
        # Per H4 (R1 audit closure 2026-05-26): `:*` port wildcards are
        # refused — the kailash-py #673 matcher's glob-vs-literal semantics
        # are not pinned in our boundary contract, so we conservatively
        # enforce explicit numeric ports. Defaults ship dev ports
        # (3000/5173/8000/8080/8765) covering Vite, CRA, Next, common
        # dev-server configs.
        if not origins:
            raise ValueError(
                "WebChannelAdapter requires a non-empty allowed_origins "
                "allowlist; refusing to start with no Origin gate "
                "(rules/security.md § Network Transport Hardening)."
            )
        permitted = re.compile(r"^https?://(?:localhost|127\.0\.0\.1):\d+$")
        for origin in origins:
            if origin == "*":
                raise ValueError(
                    "WebChannelAdapter refuses allowed_origins=['*']; "
                    "wildcard Origin breaks the DNS-rebind defense "
                    "(rules/security.md § Network Transport Hardening)."
                )
            if "*" in origin:
                raise ValueError(
                    f"WebChannelAdapter allowed_origins entry {origin!r} "
                    "contains a wildcard. Phase 01 requires explicit "
                    "numeric ports; the kailash-py Nexus matcher's "
                    "glob semantics are not pinned by this contract."
                )
            if not permitted.match(origin):
                raise ValueError(
                    f"WebChannelAdapter allowed_origins entry {origin!r} "
                    "must match http(s)://localhost:<port> or "
                    "http(s)://127.0.0.1:<port> per Phase 01 binding."
                )

    def _require_started(self, method_name: str = "send_*") -> None:
        if not self._started or self._closed:
            raise NotStartedError(channel_id=_WEB_CHANNEL_ID, method_name=method_name)
