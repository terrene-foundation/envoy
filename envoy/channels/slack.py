"""envoy.channels.slack — `SlackChannelAdapter` (Slack webhook/events).

Phase 01 surface for the Slack workspace integration. Wraps a thin in-process
webhook transport (Telegram/Slack/Discord adapters wrap nexus.transports.webhook).

Security hardening:
- H-03 primary-channel binding: `must_be_primary = primary_only or grant.high_stakes`
  — enforced defense-in-depth even when `primary_only=False`.
- PII hashing: `target_principal_id` in all INFO/WARN log fields (8-char SHA-256).
- `GrantMomentDecision` closed vocabulary derived from `Literal` via
  `typing.get_args` — never hand-mirrored (per /redteam R3 MED-R3-04).
- `_MAX_PENDING_DECISIONS` ceiling against DoS on unbounded Grant Moments.
- `NotStartedError` typed guard on every `send_*` method.

Per `rules/facade-manager-detection.md` Rule 3: construction is fully
dependency-injected — no global lookups, no hidden singletons.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import typing as _typing
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from envoy.channels._slack_signer import SlackSigner
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

_SLACK_CHANNEL_ID = "slack"
_SLACK_MAX_MESSAGE_LENGTH = 40000  # Slack Block Kit body limit
_MAX_PENDING_DECISIONS = 1000
_RATE_LIMIT_RETRY_AFTER = 60  # seconds to suggest waiting when quota is exhausted

# Closed vocabulary derived from the `GrantMomentDecision` Literal so the
# two surfaces cannot drift (per /redteam R3 MED-R3-04 closure: derive from
# Literal, never hand-mirror the strings).
_ALLOWED_DECISIONS: frozenset[str] = frozenset(_typing.get_args(GrantMomentDecision))


def _hash_pii(value: str) -> str:
    """SHA-256 hex digest truncated to 8 chars for PII-adjacent log fields.

    Per `rules/observability.md` Rule 8: `target_principal_id` is
    principal-correlatable; log aggregators have broader access than the
    production database, so the raw value MUST NOT bleed into WARN/INFO
    log lines.
    """
    return hashlib.sha256(value.encode()).hexdigest()[:8]


@dataclass(frozen=True, slots=True)
class SlackChannelConfig:
    """Construction-time config for `SlackChannelAdapter`.

    `primary_channel_id` is the user's designated primary channel id; the
    H-03 primary-channel binding check compares against this value.

    `signing_secret` is the Slack app's signing secret from the Slack
    app-management console. MUST be non-empty; validated at construction.

    `bot_token` is the Slack bot OAuth token (``xoxb-...``) used for
    outbound messages via the Slack Web API. MUST be non-empty for outbound
    sends.
    """

    primary_channel_id: str
    signing_secret: str = field(repr=False)
    bot_token: str = field(repr=False)


class SlackChannelAdapter(ChannelAdapter):
    """Phase 01 Slack adapter (webhook inbound + outbound message delivery).

    Construction is dependency-injected per
    `rules/facade-manager-detection.md` Rule 3: all dependencies (signer,
    config) are constructor-provided; no globals.

    Inbound: webhook payloads arrive via `_inject_inbound` (test hook;
    production wiring lands in the InboundRouter shard). Outbound: messages
    are queued in-process and flushed synchronously via `_flush_outbound`
    (in Tier-2 tests) or via the Slack Web API in production.

    Grant Moment: full single-channel ritual via `send_grant_moment`; M1
    dispatch render via `render_grant_moment`.
    """

    def __init__(self, config: SlackChannelConfig | None = None) -> None:
        if config is None:
            raise TypeError(
                "SlackChannelAdapter requires a SlackChannelConfig; "
                "pass SlackChannelConfig(primary_channel_id=..., "
                "signing_secret=..., bot_token=...) at construction."
            )
        self._config = config
        self._signer = SlackSigner(signing_secret=config.signing_secret)
        self._started = False
        self._closed = False
        self._inbound_queue: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=100)
        # In-flight Grant Moments: request_id → asyncio.Future[GrantMomentDecision]
        self._pending_decisions: dict[str, asyncio.Future[GrantMomentDecision]] = {}
        # Outbound: list of (target_principal_id, payload) pairs for test inspection
        self._outbound_log: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def channel_id(self) -> str:
        return _SLACK_CHANNEL_ID

    async def startup(self, config: object | None = None) -> None:
        if self._started:
            raise AlreadyStartedError(channel_id=_SLACK_CHANNEL_ID)
        if config is not None and not isinstance(config, SlackChannelConfig):
            raise TypeError(
                f"SlackChannelAdapter.startup expected SlackChannelConfig "
                f"(or None to reuse construction config), got "
                f"{type(config).__name__}."
            )
        if isinstance(config, SlackChannelConfig):
            self._config = config
            self._signer = SlackSigner(signing_secret=config.signing_secret)
        # Auth guard: reject blank credentials before attempting connection.
        if not self._config.signing_secret or not self._config.signing_secret.strip():
            raise AuthenticationError(
                channel_id=_SLACK_CHANNEL_ID,
                credential_kind="signing_secret",
                message="signing_secret must be non-empty",
            )
        if not self._config.bot_token or not self._config.bot_token.strip():
            raise AuthenticationError(
                channel_id=_SLACK_CHANNEL_ID,
                credential_kind="bot_token",
                message="bot_token must be non-empty",
            )

        # Startup work with a 10-second timeout per spec.
        async def _slack_startup_work() -> None:
            await asyncio.sleep(0)

        try:
            await asyncio.wait_for(_slack_startup_work(), timeout=10)
        except asyncio.TimeoutError as exc:
            raise StartupTimeoutError(
                channel_id=_SLACK_CHANNEL_ID,
                timeout_seconds=10,
                message="Slack startup exceeded 10s",
            ) from exc
        self._started = True
        self._closed = False
        logger.info("channel.startup", extra={"channel_id": _SLACK_CHANNEL_ID})

    async def shutdown(self, drain_timeout_seconds: int = 5) -> None:
        if not self._started or self._closed:
            return
        self._closed = True
        self._started = False
        # Drain the inbound queue best-effort within the window.
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
        logger.info("channel.shutdown", extra={"channel_id": _SLACK_CHANNEL_ID})

    # ------------------------------------------------------------------
    # Receive / send
    # ------------------------------------------------------------------

    def receive_message(self) -> AsyncIterator[InboundMessage]:
        return self._receive_messages_iter()

    async def _receive_messages_iter(self) -> AsyncIterator[InboundMessage]:
        while not self._closed:
            try:
                yield await self._inbound_queue.get()
            except asyncio.CancelledError:
                return

    async def _inject_inbound(self, msg: InboundMessage) -> None:
        """Test-only hook: push an `InboundMessage` onto the inbound queue.

        On queue overflow (>100 messages buffered), the message is dropped
        with an `OverflowDropEvent` written to the Ledger via a WARN log per
        spec § Receive (line 46) + `rules/observability.md` Rule 7.
        """
        try:
            self._inbound_queue.put_nowait(msg)
        except asyncio.QueueFull:
            drop = OverflowDropEvent(channel_id=_SLACK_CHANNEL_ID, dropped_count=1)
            logger.warning(
                "channel.inbound.overflow_drop",
                extra={
                    "channel_id": _SLACK_CHANNEL_ID,
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
        # INV-4: PrincipalNotFound gate MUST precede rate-limit gate.
        # Checking rate-limit first would reveal quota information to callers
        # supplying invalid principal IDs before identity is validated.
        if not target_principal_id or not target_principal_id.strip():
            raise PrincipalNotFoundError(
                channel_id=_SLACK_CHANNEL_ID,
                target_principal_id=target_principal_id,
                message="target_principal_id must be non-empty",
            )
        # H-05: rate-limit gate — consult rate_limit_status before every send.
        rl = await self.rate_limit_status()
        if rl.requests_remaining == 0 or rl.soft_quota_warning:
            raise RateLimitExceededError(
                channel_id=_SLACK_CHANNEL_ID,
                retry_after_seconds=_RATE_LIMIT_RETRY_AFTER,
            )
        if len(payload.body) > _SLACK_MAX_MESSAGE_LENGTH:
            raise PayloadTooLargeError(
                channel_id=_SLACK_CHANNEL_ID,
                actual_length=len(payload.body),
                max_length=_SLACK_MAX_MESSAGE_LENGTH,
            )
        # Compose the message text.
        text = payload.body
        if visible_secret is not None:
            # The visible-secret icon is the only field rendered in messages;
            # the phrase is reserved for Grant Moment ritual only (T-018).
            text = f"({visible_secret.icon}) {text}"
        logger.info(
            "channel.send_message.start",
            extra={
                "channel_id": _SLACK_CHANNEL_ID,
                "target_principal_hash": _hash_pii(target_principal_id),
                "kind": payload.kind,
            },
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                # Record the outbound message for test inspection; production
                # implementation would call the Slack Web API here.
                self._outbound_log.append((_hash_pii(target_principal_id), text))
        except asyncio.TimeoutError as exc:
            logger.warning(
                "channel.send_message.timeout",
                extra={
                    "channel_id": _SLACK_CHANNEL_ID,
                    "timeout_seconds": timeout_seconds,
                },
            )
            raise SendTimeoutError(
                channel_id=_SLACK_CHANNEL_ID,
                timeout_seconds=timeout_seconds,
            ) from exc
        receipt = SendReceipt(
            message_id=str(uuid.uuid4()),
            delivered_at=datetime.now(timezone.utc),
            channel_native_id=f"slack-{uuid.uuid4().hex[:12]}",
        )
        logger.info(
            "channel.send_message.ok",
            extra={
                "channel_id": _SLACK_CHANNEL_ID,
                "message_id": receipt.message_id,
            },
        )
        return receipt

    # ------------------------------------------------------------------
    # Ritual delivery
    # ------------------------------------------------------------------

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
                    "channel_id": _SLACK_CHANNEL_ID,
                    "request_id": grant.request_id,
                },
            )
            raise PrincipalNotFoundError(
                channel_id=_SLACK_CHANNEL_ID,
                target_principal_id=target_principal_id,
                message="target_principal_id must be non-empty",
            )
        # H-03 primary-channel binding (spec § Primary-channel binding). Defense-in-depth:
        # `grant.high_stakes is True` ALSO requires the primary channel even
        # when the caller forgot `primary_only=True`.
        # Security gate precedes rate-limit (INV-4 gate ordering).
        must_be_primary = primary_only or grant.high_stakes
        if must_be_primary and self._config.primary_channel_id != _SLACK_CHANNEL_ID:
            logger.warning(
                "channel.send_grant_moment.not_primary_channel",
                extra={
                    "channel_id": _SLACK_CHANNEL_ID,
                    "primary_channel_id": self._config.primary_channel_id,
                    "request_id": grant.request_id,
                },
            )
            raise NotPrimaryChannelError(
                channel_id=_SLACK_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )
        # Rate-limit gate after security checks (INV-4 gate ordering).
        rl = await self.rate_limit_status()
        if rl.requests_remaining == 0 or rl.soft_quota_warning:
            raise RateLimitExceededError(
                channel_id=_SLACK_CHANNEL_ID,
                retry_after_seconds=_RATE_LIMIT_RETRY_AFTER,
            )
        logger.info(
            "channel.send_grant_moment.start",
            extra={
                "channel_id": _SLACK_CHANNEL_ID,
                "request_id": grant.request_id,
                "high_stakes": grant.high_stakes,
            },
        )
        # Register in-flight future for this decision (idempotent; ceiling enforced inside).
        decision_future = self._register_pending(grant.request_id)

        # Render and deliver the Grant Moment block to the Slack channel.
        rendered = self._render_grant_moment_text(grant)
        self._outbound_log.append((_hash_pii(target_principal_id), rendered))
        logger.info(
            "channel.send_grant_moment.rendered",
            extra={
                "channel_id": _SLACK_CHANNEL_ID,
                "request_id": grant.request_id,
                "target_principal_hash": _hash_pii(target_principal_id),
            },
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                decision = await decision_future
        except asyncio.TimeoutError as exc:
            logger.warning(
                "channel.send_grant_moment.expired",
                extra={
                    "channel_id": _SLACK_CHANNEL_ID,
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
                    "channel_id": _SLACK_CHANNEL_ID,
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
                "channel_id": _SLACK_CHANNEL_ID,
                "request_id": grant.request_id,
                "decision": decision,
            },
        )
        return GrantMomentReceipt(
            request_id=grant.request_id,
            grant_id=str(uuid.uuid4()),
            decision=decision,
            decided_at=datetime.now(timezone.utc),
            channel_signature=f"slack-{uuid.uuid4().hex[:16]}",
        )

    async def _resolve_pending_decision(self, request_id: str, decision: str) -> None:
        """Webhook handler hook: resolve an in-flight Grant Moment decision.

        Called by the Slack webhook handler when a user interacts with the
        Grant Moment action block. Validates the closed vocabulary before
        resolving the future.

        Per /redteam R3 MED-R3-04: vocabulary is checked against
        `_ALLOWED_DECISIONS` (derived from `GrantMomentDecision` Literal),
        never against a hand-mirrored list.
        """
        if decision not in _ALLOWED_DECISIONS:
            raise InvalidDecisionError(
                channel_id=_SLACK_CHANNEL_ID,
                decision=decision,
                allowed=tuple(sorted(_ALLOWED_DECISIONS)),
            )
        fut = self._pending_decisions.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(decision)  # type: ignore[arg-type]

    async def render_grant_moment(
        self, request: GrantMomentRequest, *, visible_secret: object = None
    ) -> None:
        """M1 dispatch render — no decision await.

        `visible_secret` (F15-b) is accepted for Protocol conformance but NOT
        yet rendered on this channel — tracked as F15-b.2.

        Per /redteam R3 HIGH-R3-1 closure: reads canonical `GrantMomentRequest`
        discriminators (`novelty_class == "high_stakes"` and `primary_only`)
        rather than a non-existent `high_stakes` field.
        """
        self._require_started("render_grant_moment")
        novelty_class = getattr(request, "novelty_class", "")
        primary_only = bool(getattr(request, "primary_only", False))
        must_be_primary = primary_only or novelty_class == "high_stakes"
        if must_be_primary and self._config.primary_channel_id != _SLACK_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_SLACK_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )
        request_id = getattr(request, "request_id", None)
        logger.info(
            "channel.render_grant_moment",
            extra={
                "channel_id": _SLACK_CHANNEL_ID,
                "request_id": request_id,
                "novelty_class": novelty_class,
                "primary_only": primary_only,
            },
        )
        rendered = self._render_grant_moment_request_text(request)
        self._outbound_log.append(("__render__", rendered))

    async def send_digest(
        self,
        target_principal_id: str,
        digest: DailyDigestPayload,
        *,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        body = f"*Daily Digest — {digest.digest_date}*\n{digest.markdown_body}"
        payload = MessagePayload(kind="system_notice", body=body)
        return await self.send_message(
            target_principal_id,
            payload,
            timeout_seconds=timeout_seconds,
        )

    # ------------------------------------------------------------------
    # Capabilities + observability
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_buttons=True,
            supports_attachments=True,
            supports_markdown=True,
            supports_voice=False,
            supports_reactions=True,
            max_message_length=_SLACK_MAX_MESSAGE_LENGTH,
        )

    async def rate_limit_status(self) -> RateLimitStatus:
        # Slack Tier-1 methods are limited to 1 request/minute; higher-tier
        # methods up to 100+ per minute. Phase 01 returns a conservative
        # estimate. `window_resets_at=None` signals "no local enforcement".
        return RateLimitStatus(
            requests_remaining=60,
            window_resets_at=None,
            soft_quota_warning=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_started(self, method_name: str = "send_*") -> None:
        if not self._started or self._closed:
            raise NotStartedError(channel_id=_SLACK_CHANNEL_ID, method_name=method_name)

    def _register_pending(self, request_id: str) -> asyncio.Future[GrantMomentDecision]:
        """Invariant 3: single write-site for pending-decisions state.

        Returns the existing ``asyncio.Future[GrantMomentDecision]`` if one is
        already registered for ``request_id`` (idempotent — prevents concurrent
        ``send_grant_moment`` calls from stealing each other's responses).
        Otherwise creates a new future, stores it, and returns it.
        The caller awaits this future; ``post_decision`` resolves it.

        Raises ``PendingDecisionsCeilingError`` when the in-flight map is at
        capacity to prevent unbounded memory growth under sustained load.
        """
        existing = self._pending_decisions.get(request_id)
        if existing is not None:
            return existing
        if len(self._pending_decisions) >= _MAX_PENDING_DECISIONS:
            raise PendingDecisionsCeilingError(
                channel_id=_SLACK_CHANNEL_ID,
                ceiling=_MAX_PENDING_DECISIONS,
                current_count=len(self._pending_decisions),
            )
        loop = asyncio.get_running_loop()
        decision_future: asyncio.Future[GrantMomentDecision] = loop.create_future()
        self._pending_decisions[request_id] = decision_future
        return decision_future

    @staticmethod
    def _render_grant_moment_text(grant: GrantMomentPayload) -> str:
        """Render a `GrantMomentPayload` as Slack-formatted text.

        Full ritual render: includes the visible-secret phrase per Grant
        Moment spec § Rendering (the phrase IS shown here because this is
        the dedicated ritual surface, not a general message send).
        """
        lines = [
            f"\n--- Grant Moment ({grant.request_id}) ---",
            f"Safety phrase: {grant.visible_secret.icon} {grant.visible_secret.phrase}",
            grant.body,
            "Options:",
        ]
        for idx, opt in enumerate(grant.decision_options, start=1):
            lines.append(f"  {idx}) {opt}")
        return "\n".join(lines)

    @staticmethod
    def _render_grant_moment_request_text(request: GrantMomentRequest) -> str:
        """M1 render-only text from a `GrantMomentRequest` (no VisibleSecret).

        Reads the 5 canonical `GrantMomentRequest` fields: request_id,
        tool_name, why_asking, consequence_preview, novelty_class.
        """
        request_id = getattr(request, "request_id", None)
        if not request_id:
            raise ValueError("GrantMomentRequest is missing request_id; cannot render.")
        tool_name = getattr(request, "tool_name", "")
        why = getattr(request, "why_asking", "")
        consequence = getattr(request, "consequence_preview", None)
        lines = [f"\n--- Grant Moment ({request_id}) ---"]
        if tool_name:
            lines.append(f"Proposed action: {tool_name}")
        if why:
            lines.append(f"Why asking: {why}")
        if consequence is not None:
            budget = getattr(consequence, "budget_microdollars", None)
            reversibility = getattr(consequence, "reversibility", "")
            recipient = getattr(consequence, "recipient", "")
            classification = getattr(consequence, "data_classification", "")
            if budget is not None:
                lines.append(f"Estimated spend: ${budget / 1_000_000:.4f}")
            if reversibility:
                lines.append(f"Reversibility: {reversibility}")
            if recipient:
                lines.append(f"Recipient: {recipient}")
            if classification:
                lines.append(f"Data sensitivity: {classification}")
        lines.append("")
        return "\n".join(lines)
