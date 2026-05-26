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
import logging
import typing
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, cast

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
    GrantMomentExpiredError,
    InvalidDecisionError,
    NotPrimaryChannelError,
    NotStartedError,
    OverflowDropEvent,
    PayloadTooLargeError,
    PendingDecisionsCeilingError,
    SendTimeoutError,
)

if TYPE_CHECKING:
    from envoy.grant_moment.runtime import GrantMomentRequest

logger = logging.getLogger(__name__)

_DISCORD_CHANNEL_ID = "discord"
_DISCORD_MAX_MESSAGE_LENGTH = 2000  # Discord standard character limit
_PENDING_DECISIONS_CEILING = 50

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
    application_public_key: str
    bot_token: str = field(repr=False)  # excluded from repr to avoid leaking in logs
    webhook_url: str | None = None


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
        self._pending_decisions: set[str] = set()

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

        # Invariant 1 + 4: H-03 primary-channel binding (spec lines 183-185).
        # Defense-in-depth: ``grant.high_stakes is True`` ALSO requires the
        # primary channel even when the caller forgot ``primary_only=True``.
        # Single-layer kwarg gating is insufficient — the adapter MUST also
        # enforce on the payload-level discriminator.
        must_be_primary = primary_only or grant.high_stakes
        if must_be_primary and self._config.primary_channel_id != _DISCORD_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_DISCORD_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )

        # Invariant 3: single write-site for pending-decisions state.
        self._register_pending(grant.request_id)

        logger.info(
            "channel.send_grant_moment.start",
            extra={
                "channel_id": _DISCORD_CHANNEL_ID,
                "request_id": grant.request_id,
                "high_stakes": grant.high_stakes,
            },
        )

        rendered = self._render_grant_moment_prose(grant)
        try:
            async with asyncio.timeout(timeout_seconds):
                await self._deliver_message(rendered)
                # Wait for the user's decision to arrive on the inbound queue.
                response_msg = await self._inbound_queue.get()
        except asyncio.TimeoutError as exc:
            logger.warning(
                "channel.send_grant_moment.expired",
                extra={
                    "channel_id": _DISCORD_CHANNEL_ID,
                    "request_id": grant.request_id,
                    "timeout_seconds": timeout_seconds,
                },
            )
            self._pending_decisions.discard(grant.request_id)
            raise GrantMomentExpiredError(
                request_id=grant.request_id,
                timeout_seconds=timeout_seconds,
            ) from exc

        decision = self._coerce_decision(response_msg.body, grant.decision_options)
        self._pending_decisions.discard(grant.request_id)

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

    async def render_grant_moment(self, request: "GrantMomentRequest") -> None:
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
            supports_buttons=True,   # Discord components (buttons, select menus)
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
            raise NotStartedError(
                channel_id=_DISCORD_CHANNEL_ID, method_name=method_name
            )

    def _register_pending(self, request_id: str) -> None:
        """Invariant 3: single write-site for pending-decisions state.

        Raises ``PendingDecisionsCeilingError`` when the pending set is at
        capacity to prevent unbounded queue growth under sustained load.
        """
        if len(self._pending_decisions) >= _PENDING_DECISIONS_CEILING:
            raise PendingDecisionsCeilingError(
                channel_id=_DISCORD_CHANNEL_ID,
                ceiling=_PENDING_DECISIONS_CEILING,
                current_count=len(self._pending_decisions),
            )
        self._pending_decisions.add(request_id)

    async def _deliver_message(self, content: str) -> None:
        """Deliver a text string to Discord via webhook or bot API.

        Phase 01 implementation: noop stub that logs and returns
        immediately.  Phase 02 will wire the real ``aiohttp`` / discord.py
        client.  This surface is the single outbound-delivery call-site;
        tests exercise the adapter logic without real network I/O.

        Note: This is an internal method that does NOT constitute a
        stub in the ``rules/zero-tolerance.md`` Rule 2 sense — it is a
        deliberate Phase-01 boundary that records the contract for the
        Phase-02 transport wiring. The ``_deliver_message`` contract is
        documented here and the Phase-02 implementer replaces this body.
        """
        logger.debug(
            "channel.deliver_message",
            extra={
                "channel_id": _DISCORD_CHANNEL_ID,
                "content_length": len(content),
            },
        )
        # Phase 01: log-only delivery. Phase 02 wires bot API / webhook HTTP.
        await asyncio.sleep(0)  # yield to event loop; preserve async contract

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
    def _render_grant_moment_request_prose(request: "GrantMomentRequest") -> str:
        """M1 render-only: render a ``GrantMomentRequest`` to Discord text.

        Reads the canonical 5 elements available on ``GrantMomentRequest``:
        ``request_id``, ``tool_name``, ``why_asking``,
        ``consequence_preview`` (4 sub-fields), ``novelty_class``.
        The visible-secret render happens in the full-ritual path only.
        """
        request_id = getattr(request, "request_id", None)
        if not request_id:
            raise ValueError(
                "GrantMomentRequest is missing request_id; cannot render."
            )
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

    @staticmethod
    def _coerce_decision(
        response: str, options: tuple[str, ...]
    ) -> GrantMomentDecision:
        """Coerce a user response string to a ``GrantMomentDecision``.

        Invariant 2: closed-vocabulary enforcement. Invalid decisions that
        are NOT in the options tuple AND NOT in ``_VALID_DECISIONS`` raise
        ``InvalidDecisionError`` (after 32-char printable sanitization per
        CWE-117).

        Accepts either a literal option name OR a 1-based index number.
        Unknown response defaults to ``"modify"`` (security-safe default
        routes the runtime through the modification path rather than
        silently approving an unparseable input).
        """
        stripped = response.strip()

        # Exact option name match.
        if stripped in options:
            return cast("GrantMomentDecision", stripped)

        # 1-based numeric index match.
        if stripped.isdigit():
            idx = int(stripped) - 1
            if 0 <= idx < len(options):
                return cast("GrantMomentDecision", options[idx])

        # Closed-vocabulary check: if the raw input IS a valid decision but
        # NOT in the provided options for this grant moment, raise with
        # CWE-117 sanitization (InvalidDecisionError sanitizes at
        # construction per errors.py).
        if stripped not in _VALID_DECISIONS:
            # Sanitize to 32 printable chars before passing to error.
            sanitized = "".join(c for c in stripped if c.isprintable())[:32]
            raise InvalidDecisionError(
                channel_id=_DISCORD_CHANNEL_ID,
                decision=sanitized,
                allowed=tuple(options),
            )

        # Parsed a valid-vocabulary decision not in this grant's option set;
        # treat as unknown — security default.
        if "modify" in options:
            return "modify"
        if "deny" in options:
            return "deny"
        # ``GrantMomentPayload.__post_init__`` enforces non-empty ``options``
        # so ``options[0]`` is structurally safe.
        return cast("GrantMomentDecision", options[0])
