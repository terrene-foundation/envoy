"""envoy.channels.discord — `DiscordChannelAdapter` wrapping Discord webhooks.

Phase 01 surface for Discord bot interaction delivery.  Implements
Ed25519 signature verification via `DiscordSigner` and exposes the
full 7-invariant adapter contract established by /redteam R1-R5 on the
channels foundation (journal/0038).

Key invariants implemented at design time (see
`workspaces/phase-01-mvp/journal/0038-DISCOVERY-redteam-wave-4-channels-
foundation-convergence.md`):

  1. Canonical discriminators: `render_grant_moment` reads
     ``novelty_class == "high_stakes"`` from `GrantMomentRequest`; and
     `send_grant_moment` reads ``grant.high_stakes`` from
     `GrantMomentPayload`.
  2. Closed-vocabulary: `frozenset(typing.get_args(GrantMomentDecision))`.
  3. Single write-site: ``_register_pending(request_id)`` is the sole
     state-mutation point for pending-decisions bookkeeping.
  4. High_stakes auto-gate: defense-in-depth even when
     ``primary_only=False`` — same as CLI/Web adapters.
  5. PII hash: SHA-256 hex[:8] for ``principal_id`` in log emissions
     (per ``rules/observability.md`` Rule 8).
  6. ``_register_pending`` discipline: pending set updated atomically
     before any network call.
  7. Phase-02 ritual surfaces inherit default `PhaseDeferredError`.

Discord-specific:
- Supports buttons (Discord components), attachments, markdown, and
  reactions; no voice.
- Max message length: 2000 characters (Discord standard text limit).
- Inbound queue: ``asyncio.Queue[InboundMessage](maxsize=100)`` with
  ``OverflowDropEvent`` on full (non-raising WARN-only).
- Application public key is injected at construction (never hardcoded).
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import typing
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from envoy.channels._discord_signer import DiscordSigner
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
    AuthenticationError,
    ChannelTransportError,
    GrantMomentExpiredError,
    InvalidDecisionError,
    NotPrimaryChannelError,
    NotStartedError,
    OverflowDropEvent,
    PayloadTooLargeError,
    PendingDecisionsCeilingError,
    PrincipalNotFoundError,
    RateLimitExceededError,
    SendTimeoutError,
    StartupTimeoutError,
)

if TYPE_CHECKING:
    from envoy.grant_moment.runtime import GrantMomentRequest

logger = logging.getLogger(__name__)

_DISCORD_CHANNEL_ID = "discord"
_DISCORD_MAX_MESSAGE_LENGTH = 2000  # Discord standard character limit
_PENDING_DECISIONS_CEILING = 50
_RATE_LIMIT_RETRY_AFTER = 60  # seconds to suggest waiting when quota is exhausted

# Closed-vocabulary for GrantMomentDecision — derived structurally per
# invariant 2 so the set automatically tracks future spec additions.
_VALID_DECISIONS: frozenset[str] = frozenset(typing.get_args(GrantMomentDecision))


def _hash_pii(value: str) -> str:
    """SHA-256 hex digest truncated to 8 chars for PII-adjacent log fields.

    Per ``rules/observability.md`` Rule 8 (schema/identifier names at
    INFO/WARN bleed to aggregators with broader access than the production
    database). Used for ``principal_id`` + ``session_id`` in adapter log
    emissions.
    """
    return hashlib.sha256(value.encode()).hexdigest()[:8]


# SSRF-blocked prefixes and hostnames (stdlib-only, no new deps).
_SSRF_BLOCKED_HOSTS: frozenset[str] = frozenset(
    {
        "metadata.google.internal",
        "metadata.internal",
        "169.254.169.254",  # AWS / GCP IMDSv1
    }
)
_SSRF_BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),         # "this" network (RFC 1122); never a valid dest
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("10.0.0.0/8"),        # RFC-1918 private A
    ipaddress.ip_network("172.16.0.0/12"),     # RFC-1918 private B
    ipaddress.ip_network("192.168.0.0/16"),    # RFC-1918 private C
    ipaddress.ip_network("169.254.0.0/16"),    # link-local / IMDS
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA (unique-local; NOT private in RFC-1918 sense)
    ipaddress.ip_network("::ffff:0.0.0.0/96"), # IPv6-mapped IPv4 (covers ::ffff:127.0.0.1 etc.)
)


def _validate_webhook_url_ssrf(url: str, channel_id: str) -> None:
    """Reject webhook URLs that point at loopback, private, or IMDS addresses.

    Uses stdlib ``urllib.parse.urlparse`` + ``ipaddress`` only — no new deps.
    Raises ``ChannelTransportError`` if the URL fails the SSRF guard.
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ChannelTransportError(
            channel_id=channel_id,
            message=f"webhook_url has no hostname: {url!r}",
        )
    if hostname in _SSRF_BLOCKED_HOSTS:
        raise ChannelTransportError(
            channel_id=channel_id,
            message=f"webhook_url targets blocked host (SSRF guard): {hostname!r}",
        )
    # Normalise decimal and hex integer literals to dotted-quad before calling
    # ipaddress.ip_address, which would raise ValueError for those forms.
    # Examples: "2130706433" == 127.0.0.1, "0x7f000001" == 127.0.0.1.
    #
    # Octal-dotted notation ("0177.0.0.1" == 127.0.0.1) must be detected
    # BEFORE ip_address() is called because ip_address() raises ValueError for
    # octal notation rather than interpreting it — allowing it through as a
    # "hostname" and deferring to DNS lookup is an SSRF bypass.
    _hostname_for_ip = hostname
    if hostname.isdigit():
        # Pure decimal integer — convert via int first.
        try:
            _hostname_for_ip = str(ipaddress.ip_address(int(hostname)))
        except (ValueError, OverflowError):
            _hostname_for_ip = hostname  # fall through to the except below
    elif hostname.lower().startswith("0x") and "." not in hostname:
        # Hex integer literal (no dots) e.g. "0x7f000001" == 127.0.0.1.
        # Dotted-hex like "0x7f.0.0.1" falls through to the dotted-notation
        # branch below (startswith("0x") with dots is NOT a pure integer).
        try:
            _hostname_for_ip = str(ipaddress.ip_address(int(hostname, 16)))
        except (ValueError, OverflowError):
            _hostname_for_ip = hostname  # fall through to the except below
    elif "." in hostname and all(
        c in "0123456789abcdefABCDEFxXoO." for c in hostname
    ):
        # Potentially octal-dotted or hex-dotted notation.
        # Examples: "0177.0.0.1" == 127.0.0.1 (octal),
        #           "0x7f.0.0.1" == 127.0.0.1 (hex-dotted).
        # ``ipaddress.ip_address`` raises ValueError for both forms rather
        # than interpreting them, so we must normalise first.
        parts = hostname.split(".")
        if len(parts) == 4:
            try:
                decimal_parts = []
                has_normalized = False
                for p in parts:
                    if p.lower().startswith("0x"):
                        # Hex-dotted component (e.g. "0x7f" == 127)
                        decimal_parts.append(str(int(p, 16)))
                        has_normalized = True
                    elif len(p) > 1 and p.startswith("0"):
                        # Octal component (e.g. "0177" == 127).
                        # ``int("08", 8)`` raises ValueError — detect invalid
                        # octal digits (8, 9) before converting to avoid
                        # silent pass-through of malformed addresses.
                        if any(d in "89" for d in p):
                            raise ChannelTransportError(
                                channel_id=channel_id,
                                message=(
                                    f"webhook_url contains malformed octal component "
                                    f"{p!r} in hostname (SSRF guard): {hostname!r}"
                                ),
                            )
                        decimal_parts.append(str(int(p, 8)))
                        has_normalized = True
                    else:
                        decimal_parts.append(str(int(p, 0)))
                if has_normalized:
                    _hostname_for_ip = ".".join(decimal_parts)
            except ChannelTransportError:
                raise
            except (ValueError, OverflowError):
                pass  # not parseable; fall through to ipaddress below
    try:
        ip = ipaddress.ip_address(_hostname_for_ip)
        for net in _SSRF_BLOCKED_NETWORKS:
            if ip in net:
                raise ChannelTransportError(
                    channel_id=channel_id,
                    message=(
                        f"webhook_url targets blocked IP range (SSRF guard): "
                        f"{hostname!r} is in {net}"
                    ),
                )
    except ValueError:
        # Not an IP literal — hostname only; DNS lookup deferred to transport.
        pass


async def _discord_startup_work() -> None:
    """Async startup coroutine for ``asyncio.wait_for`` timeout wrapping.

    Phase 01: no real I/O; yields to the event loop once to preserve async
    contract.  Phase 02 replaces this body with actual Discord API health
    check (e.g. GET /gateway or validate bot token via /users/@me).
    """
    await asyncio.sleep(0)


@dataclass(frozen=True, slots=True)
class DiscordChannelConfig:
    """Construction-time config for `DiscordChannelAdapter`.

    Args:
        primary_channel_id: The user's designated primary channel id.
            H-03 primary-channel binding compares the running adapter's
            channel id (``"discord"``) against this value at grant-moment
            time.
        application_public_key: Hex-encoded Ed25519 public key from the
            Discord Developer Portal.  Injected at construction; NEVER
            hardcoded.  Required for signature verification on inbound
            interaction payloads.
        bot_token: Discord bot token for outbound API calls.  MUST be
            read from an env var by the caller; never logged.
        webhook_url: Discord webhook URL for outbound message delivery.
            Optional; if absent, outbound messages MUST be routed via
            the bot API (not implemented in Phase 01 — raises
            ``ChannelTransportError``).
    """

    primary_channel_id: str
    application_public_key: str = field(repr=False)  # excluded from repr to avoid leaking in logs
    bot_token: str = field(repr=False)  # excluded from repr to avoid leaking in logs
    webhook_url: str | None = field(default=None, repr=False)  # contains auth token — excluded from repr


class DiscordChannelAdapter(ChannelAdapter):
    """Phase 01 Discord channel adapter (webhook + bot API substrate).

    Construction is dependency-injected per
    ``rules/facade-manager-detection.md`` Rule 3.

    Renders Grant Moment by composing a Discord embed-style text block
    with numbered options.  Awaits the user's interaction callback from
    the inbound queue (via ``_inject_inbound``); the full timeout raises
    ``GrantMomentExpiredError``.

    Signature verification (inbound): ``DiscordSigner.verify(headers, body)``
    is the caller's responsibility BEFORE constructing an ``InboundMessage``
    and injecting it via ``_inject_inbound``.  The adapter itself does not
    own the HTTP transport layer.
    """

    def __init__(self, config: DiscordChannelConfig) -> None:
        self._config = config
        # Validate key at construction time so misconfigured deployments
        # fail loudly rather than at first request.
        self._signer = DiscordSigner(config.application_public_key)
        self._started = False
        self._closed = False
        self._inbound_queue: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=100)
        # Single write-site invariant (invariant 3): all pending-decision
        # registration goes through ``_register_pending``.
        # request_id → asyncio.Future[GrantMomentDecision] (CRIT-1 closure:
        # per-request isolation so concurrent send_grant_moment calls do not
        # steal each other's responses from the shared inbound queue).
        self._pending_decisions: dict[str, asyncio.Future[GrantMomentDecision]] = {}

    @property
    def channel_id(self) -> str:
        return _DISCORD_CHANNEL_ID

    @property
    def signer(self) -> DiscordSigner:
        """Expose the signer so webhook-transport callers can verify signatures."""
        return self._signer

    async def startup(self, config: object | None = None) -> None:
        if self._started:
            raise AlreadyStartedError(channel_id=_DISCORD_CHANNEL_ID)
        if config is not None and not isinstance(config, DiscordChannelConfig):
            raise TypeError(
                f"DiscordChannelAdapter.startup expected DiscordChannelConfig "
                f"(or None to reuse construction config), got "
                f"{type(config).__name__}."
            )
        if isinstance(config, DiscordChannelConfig):
            self._config = config
            # Re-create signer when config is replaced.
            self._signer = DiscordSigner(config.application_public_key)
        # AUTH check: blank credentials → AuthenticationError before any I/O.
        if not self._config.bot_token or not self._config.bot_token.strip():
            raise AuthenticationError(
                channel_id=_DISCORD_CHANNEL_ID,
                credential_kind="bot_token",
                message="bot_token must not be blank",
            )
        if not self._config.application_public_key or not self._config.application_public_key.strip():
            raise AuthenticationError(
                channel_id=_DISCORD_CHANNEL_ID,
                credential_kind="application_public_key",
                message="application_public_key must not be blank",
            )
        # SSRF guard for webhook_url (stdlib-only, no new deps).
        if self._config.webhook_url is not None:
            _validate_webhook_url_ssrf(self._config.webhook_url, _DISCORD_CHANNEL_ID)
        try:
            await asyncio.wait_for(_discord_startup_work(), timeout=10)
        except asyncio.TimeoutError as exc:
            raise StartupTimeoutError(
                channel_id=_DISCORD_CHANNEL_ID,
                timeout_seconds=10,
                message="Discord adapter startup timed out after 10 seconds",
            ) from exc
        self._started = True
        self._closed = False
        logger.info("channel.startup", extra={"channel_id": _DISCORD_CHANNEL_ID})

    async def shutdown(self, drain_timeout_seconds: int = 5) -> None:
        if not self._started or self._closed:
            return
        self._closed = True
        self._started = False
        try:
            async with asyncio.timeout(drain_timeout_seconds):
                while not self._inbound_queue.empty():
                    self._inbound_queue.get_nowait()
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            pass
        # Cancel any in-flight Grant Moment futures cleanly.
        for fut in self._pending_decisions.values():
            if not fut.done():
                fut.cancel()
        self._pending_decisions.clear()
        logger.info("channel.shutdown", extra={"channel_id": _DISCORD_CHANNEL_ID})

    def receive_message(self) -> AsyncIterator[InboundMessage]:  # type: ignore[override]
        """Return an async generator yielding inbound messages.

        The generator runs until the adapter is shut down.  Production
        inbound flows through ``_inject_inbound`` (called by the
        webhook-transport layer after signature verification); Tier-2
        tests use the same hook.
        """
        return self._receive_message_impl()

    async def _receive_message_impl(self) -> AsyncIterator[InboundMessage]:
        while not self._closed:
            try:
                yield await self._inbound_queue.get()
            except asyncio.CancelledError:
                return

    async def _inject_inbound(self, msg: InboundMessage) -> None:
        """Inject a verified ``InboundMessage`` onto the inbound queue.

        Production callers MUST verify the Discord Ed25519 signature via
        ``self.signer.verify(headers, body)`` BEFORE calling this method.

        On queue overflow (>100 messages buffered), the message is dropped
        with an ``OverflowDropEvent`` WARN log per spec § Receive +
        ``rules/observability.md`` Rule 7 (bulk-op partial-failure WARN).
        The producer does NOT block — drop-with-audit is the Phase 01
        contract.
        """
        try:
            self._inbound_queue.put_nowait(msg)
        except asyncio.QueueFull:
            drop = OverflowDropEvent(channel_id=_DISCORD_CHANNEL_ID, dropped_count=1)
            logger.warning(
                "channel.inbound.overflow_drop",
                extra={
                    "channel_id": _DISCORD_CHANNEL_ID,
                    "session_hash": _hash_pii(msg.session_id),
                    "dropped_count": drop.dropped_count,
                },
            )

    async def send_message(
        self,
        target_principal_id: str,
        payload: MessagePayload,
        *,
        visible_secret: VisibleSecret | None = None,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        self._require_started("send_message")
        # L-1: PrincipalNotFound guard — parity with Telegram and Slack adapters.
        if not target_principal_id or not target_principal_id.strip():
            logger.warning(
                "channel.send_message.principal_not_found",
                extra={
                    "channel_id": _DISCORD_CHANNEL_ID,
                },
            )
            raise PrincipalNotFoundError(
                channel_id=_DISCORD_CHANNEL_ID,
                target_principal_id=target_principal_id,
                message="target_principal_id must not be blank",
            )
        # Rate-limit gate.
        rl = await self.rate_limit_status()
        if rl.requests_remaining == 0 or rl.soft_quota_warning:
            raise RateLimitExceededError(
                channel_id=_DISCORD_CHANNEL_ID,
                retry_after_seconds=_RATE_LIMIT_RETRY_AFTER,
            )
        if len(payload.body) > _DISCORD_MAX_MESSAGE_LENGTH:
            raise PayloadTooLargeError(
                channel_id=_DISCORD_CHANNEL_ID,
                actual_length=len(payload.body),
                max_length=_DISCORD_MAX_MESSAGE_LENGTH,
            )
        # Compose the Discord-formatted text. The visible_secret icon is
        # rendered as a visual provenance hint; the phrase is NEVER
        # included in send_message output (only Grant Moment surfaces the
        # phrase per T-018 + ``rules/security.md`` § "No secrets in logs").
        content = payload.body
        if visible_secret is not None:
            content = f"{visible_secret.icon} {content}"

        logger.info(
            "channel.send_message.start",
            extra={
                "channel_id": _DISCORD_CHANNEL_ID,
                "target_principal_hash": _hash_pii(target_principal_id),
                "kind": payload.kind,
            },
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                await self._deliver_message(content)
        except asyncio.TimeoutError as exc:
            logger.warning(
                "channel.send_message.timeout",
                extra={
                    "channel_id": _DISCORD_CHANNEL_ID,
                    "timeout_seconds": timeout_seconds,
                },
            )
            raise SendTimeoutError(
                channel_id=_DISCORD_CHANNEL_ID,
                timeout_seconds=timeout_seconds,
            ) from exc

        receipt = SendReceipt(
            message_id=str(uuid.uuid4()),
            delivered_at=datetime.now(timezone.utc),
            channel_native_id=f"discord-{uuid.uuid4().hex[:12]}",
        )
        logger.info(
            "channel.send_message.ok",
            extra={
                "channel_id": _DISCORD_CHANNEL_ID,
                "message_id": receipt.message_id,
            },
        )
        return receipt

    async def send_grant_moment(
        self,
        target_principal_id: str,
        grant: GrantMomentPayload,
        *,
        primary_only: bool = False,
        timeout_seconds: int = 30,
    ) -> GrantMomentReceipt:
        self._require_started("send_grant_moment")
        # M-3 gate ordering: PrincipalNotFound guard precedes security and
        # availability gates — identity errors are always caller faults.
        if not target_principal_id or not target_principal_id.strip():
            logger.warning(
                "channel.send_grant_moment.principal_not_found",
                extra={
                    "channel_id": _DISCORD_CHANNEL_ID,
                    "request_id": grant.request_id,
                },
            )
            raise PrincipalNotFoundError(
                channel_id=_DISCORD_CHANNEL_ID,
                target_principal_id=target_principal_id,
                message="target_principal_id must not be blank",
            )

        # Invariant 1 + 4: H-03 primary-channel binding (spec § Primary-channel binding).
        # Defense-in-depth: ``grant.high_stakes is True`` ALSO requires the
        # primary channel even when the caller forgot ``primary_only=True``.
        # Security gate precedes rate-limit (INV-4 gate ordering).
        must_be_primary = primary_only or grant.high_stakes
        if must_be_primary and self._config.primary_channel_id != _DISCORD_CHANNEL_ID:
            logger.warning(
                "channel.send_grant_moment.not_primary_channel",
                extra={
                    "channel_id": _DISCORD_CHANNEL_ID,
                    "primary_channel_id": self._config.primary_channel_id,
                    "request_id": grant.request_id,
                },
            )
            raise NotPrimaryChannelError(
                channel_id=_DISCORD_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )

        # Rate-limit gate after security checks (INV-4 gate ordering).
        rl = await self.rate_limit_status()
        if rl.requests_remaining == 0 or rl.soft_quota_warning:
            raise RateLimitExceededError(
                channel_id=_DISCORD_CHANNEL_ID,
                retry_after_seconds=_RATE_LIMIT_RETRY_AFTER,
            )

        # Invariant 3: single write-site for pending-decisions state.
        # _register_pending creates and stores the per-request Future (CRIT-1).
        decision_future = self._register_pending(grant.request_id)

        logger.info(
            "channel.send_grant_moment.start",
            extra={
                "channel_id": _DISCORD_CHANNEL_ID,
                "request_id": grant.request_id,
                "high_stakes": grant.high_stakes,
                "target_principal_hash": _hash_pii(target_principal_id),
            },
        )

        rendered = self._render_grant_moment_prose(grant)
        try:
            async with asyncio.timeout(timeout_seconds):
                await self._deliver_message(rendered)
                # Await the per-request Future resolved by post_decision().
                # CRIT-1: using a Future instead of reading from the shared
                # inbound queue prevents concurrent send_grant_moment calls from
                # stealing each other's responses.
                decision = await decision_future
        except asyncio.TimeoutError as exc:
            logger.warning(
                "channel.send_grant_moment.expired",
                extra={
                    "channel_id": _DISCORD_CHANNEL_ID,
                    "request_id": grant.request_id,
                    "timeout_seconds": timeout_seconds,
                },
            )
            self._pending_decisions.pop(grant.request_id, None)
            raise GrantMomentExpiredError(
                request_id=grant.request_id,
                timeout_seconds=timeout_seconds,
            ) from exc
        except asyncio.CancelledError as exc:
            logger.warning(
                "channel.send_grant_moment.cancelled",
                extra={
                    "channel_id": _DISCORD_CHANNEL_ID,
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

        logger.info(
            "channel.send_grant_moment.ok",
            extra={
                "channel_id": _DISCORD_CHANNEL_ID,
                "request_id": grant.request_id,
                "decision": decision,
            },
        )
        return GrantMomentReceipt(
            request_id=grant.request_id,
            grant_id=str(uuid.uuid4()),
            decision=decision,
            decided_at=datetime.now(timezone.utc),
            channel_signature="",
        )

    async def render_grant_moment(self, request: GrantMomentRequest) -> None:
        """M1 render-only dispatch per `ChannelAdapterProtocol`.

        Renders the ``GrantMomentRequest`` to Discord as an embed-style text
        block WITHOUT awaiting a user decision; the decision arrives async
        via ``EnvoyGrantMomentRuntime.post_decision``.

        H-03 binding reads the canonical ``GrantMomentRequest`` discriminators
        (``novelty_class == "high_stakes"`` and ``primary_only is True``)
        per /redteam R3 HIGH-R3-1 closure — NOT a ``high_stakes`` field that
        does not exist on the real dataclass.
        """
        self._require_started("render_grant_moment")

        # Invariant 1: canonical discriminators from GrantMomentRequest.
        novelty_class = getattr(request, "novelty_class", "")
        primary_only = bool(getattr(request, "primary_only", False))
        must_be_primary = primary_only or novelty_class == "high_stakes"
        if must_be_primary and self._config.primary_channel_id != _DISCORD_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_DISCORD_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )
        request_id = getattr(request, "request_id", None)
        logger.info(
            "channel.render_grant_moment",
            extra={
                "channel_id": _DISCORD_CHANNEL_ID,
                "request_id": request_id,
                "novelty_class": novelty_class,
                "primary_only": primary_only,
            },
        )
        rendered = self._render_grant_moment_request_prose(request)
        await self._deliver_message(rendered)

    async def send_digest(
        self,
        target_principal_id: str,
        digest: DailyDigestPayload,
        *,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        body = f"**Daily Digest — {digest.digest_date}**\n\n{digest.markdown_body}"
        # Trim to Discord max length to avoid PayloadTooLargeError.
        if len(body) > _DISCORD_MAX_MESSAGE_LENGTH:
            body = body[: _DISCORD_MAX_MESSAGE_LENGTH - 3] + "..."
        payload = MessagePayload(kind="system_notice", body=body)
        return await self.send_message(
            target_principal_id,
            payload,
            timeout_seconds=timeout_seconds,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_buttons=True,  # Discord components (buttons, select menus)
            supports_attachments=True,
            supports_markdown=True,  # Discord markdown subset
            supports_voice=False,
            supports_reactions=True,  # Discord reaction API
            max_message_length=_DISCORD_MAX_MESSAGE_LENGTH,
        )

    async def rate_limit_status(self) -> RateLimitStatus:
        # Discord's REST API enforces per-route rate limits; the adapter
        # surfaces ``window_resets_at=None`` (Phase 01: no quota tracking
        # implemented — adapter defers to Discord's 429 responses).
        # ``soft_quota_warning=False`` until quota tracking is wired.
        return RateLimitStatus(
            requests_remaining=10**9,
            window_resets_at=None,
            soft_quota_warning=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_started(self, method_name: str = "send_*") -> None:
        """Guard every send path against pre-startup calls."""
        if not self._started or self._closed:
            raise NotStartedError(channel_id=_DISCORD_CHANNEL_ID, method_name=method_name)

    def _register_pending(self, request_id: str) -> asyncio.Future[GrantMomentDecision]:
        """Invariant 3: single write-site for pending-decisions state.

        Returns the existing ``asyncio.Future[GrantMomentDecision]`` if one is
        already registered for ``request_id`` (idempotent — prevents concurrent
        ``send_grant_moment`` calls from stealing each other's responses).
        Otherwise creates a new future, stores it, and returns it.
        The caller awaits this future; ``post_decision`` resolves it.

        CRIT-1 closure: per-request futures prevent concurrent
        ``send_grant_moment`` calls from stealing each other's responses from
        a shared inbound queue.

        Raises ``PendingDecisionsCeilingError`` when the in-flight map is at
        capacity to prevent unbounded memory growth under sustained load.
        """
        existing = self._pending_decisions.get(request_id)
        if existing is not None:
            return existing
        if len(self._pending_decisions) >= _PENDING_DECISIONS_CEILING:
            raise PendingDecisionsCeilingError(
                channel_id=_DISCORD_CHANNEL_ID,
                ceiling=_PENDING_DECISIONS_CEILING,
                current_count=len(self._pending_decisions),
            )
        loop = asyncio.get_running_loop()
        decision_future: asyncio.Future[GrantMomentDecision] = loop.create_future()
        self._pending_decisions[request_id] = decision_future
        return decision_future

    def post_decision(self, request_id: str, decision: str) -> None:
        """Resolve an in-flight Grant Moment decision by ``request_id``.

        Called by the Discord interaction handler (webhook route) when the
        user submits a button click or reply.  Validates the closed vocabulary
        before resolving the future so ``send_grant_moment`` never sees an
        invalid ``GrantMomentDecision``.

        Mirrors ``TelegramChannelAdapter.post_decision`` in naming so the
        framework layer can call the same method name on every adapter.

        Silently ignores unknown ``request_id`` values (the grant may have
        already expired or been cancelled).
        """
        if decision not in _VALID_DECISIONS:
            # Sanitize to 32 printable chars (CWE-117 defence).
            sanitized = "".join(c for c in decision if c.isprintable())[:32]
            raise InvalidDecisionError(
                channel_id=_DISCORD_CHANNEL_ID,
                decision=sanitized,
                allowed=tuple(sorted(_VALID_DECISIONS)),
            )
        fut = self._pending_decisions.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(decision)  # type: ignore[arg-type]

    async def _deliver_message(self, content: str) -> None:
        """Deliver a text string to Discord via webhook or bot API.

        Phase 01 implementation: raises ``ChannelTransportError`` to signal
        that the transport is not yet wired.  Phase 02 will replace this body
        with a real ``aiohttp`` / discord.py HTTP call.

        Per ``rules/zero-tolerance.md`` Rule 2, a noop ``asyncio.sleep(0)``
        is NOT acceptable as a Phase-01 delivery stub — callers must know
        that delivery failed so they can surface the error rather than
        silently dropping messages.
        """
        logger.debug(
            "channel.deliver_message",
            extra={
                "channel_id": _DISCORD_CHANNEL_ID,
                "content_length": len(content),
            },
        )
        raise ChannelTransportError(
            channel_id=_DISCORD_CHANNEL_ID,
            message="Phase 01 transport not implemented — Discord delivery not wired",
        )

    @staticmethod
    def _render_grant_moment_prose(grant: GrantMomentPayload) -> str:
        """Render the full grant-moment ritual text for Discord."""
        lines = [
            f"\n**Grant Moment** (`{grant.request_id}`)",
            f"Safety phrase: {grant.visible_secret.icon} **{grant.visible_secret.phrase}**",
            grant.body,
            "\n**Options:**",
        ]
        for idx, opt in enumerate(grant.decision_options, start=1):
            lines.append(f"> {idx}) `{opt}`")
        lines.append("\n_Reply with the option number or name._")
        return "\n".join(lines)

    @staticmethod
    def _render_grant_moment_request_prose(request: GrantMomentRequest) -> str:
        """M1 render-only: render a ``GrantMomentRequest`` to Discord text.

        Reads the canonical 5 elements available on ``GrantMomentRequest``:
        ``request_id``, ``tool_name``, ``why_asking``,
        ``consequence_preview`` (4 sub-fields), ``novelty_class``.
        The visible-secret render happens in the full-ritual path only.
        """
        request_id = getattr(request, "request_id", None)
        if not request_id:
            raise ValueError("GrantMomentRequest is missing request_id; cannot render.")
        tool_name = getattr(request, "tool_name", "")
        why = getattr(request, "why_asking", "")
        consequence = getattr(request, "consequence_preview", None)
        lines = [f"\n**Grant Moment** (`{request_id}`)"]
        if tool_name:
            lines.append(f"**Proposed action:** `{tool_name}`")
        if why:
            lines.append(f"**Why asking:** {why}")
        if consequence is not None:
            budget = getattr(consequence, "budget_microdollars", None)
            reversibility = getattr(consequence, "reversibility", "")
            recipient = getattr(consequence, "recipient", "")
            classification = getattr(consequence, "data_classification", "")
            if budget is not None:
                lines.append(f"**Estimated spend:** ${budget / 1_000_000:.4f}")
            if reversibility:
                lines.append(f"**Reversibility:** {reversibility}")
            if recipient:
                lines.append(f"**Recipient:** {recipient}")
            if classification:
                lines.append(f"**Data sensitivity:** {classification}")
        lines.append("")
        return "\n".join(lines)

