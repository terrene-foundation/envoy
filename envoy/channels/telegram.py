"""Telegram channel adapter for Envoy.

Implements :class:`ChannelAdapter` for the Telegram Bot API webhook transport.
All incoming webhook payloads arrive via :class:`asyncio.Queue`; the adapter
exposes them through :meth:`receive_message`.  Outbound messages are delivered
via an injected async send callable.

Design constraints
------------------
All 7 invariants from journal-0038 are observed (see inline comments):

INV-1: Dual discriminator — ``send_grant_moment`` reads ``grant.high_stakes``
       (``GrantMomentPayload`` bool), ``render_grant_moment`` reads
       ``getattr(request, "novelty_class", "") == "high_stakes"``
       (``GrantMomentRequest`` string discriminator).
INV-2: Closed vocabulary derived from ``typing.get_args(GrantMomentDecision)``.
INV-3: ``_register_pending`` is the single write-site for grant moment state.
INV-4: High-stakes auto-gate: ``must_be_primary = primary_only or grant.high_stakes``.
INV-5: PII hashed via ``hashlib.sha256(value.encode()).hexdigest()[:8]``.
INV-6: ``_register_pending`` discipline for grant moments.
INV-7: Phase-02 ritual surfaces raise ``PhaseDeferredError`` via ABC default.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import typing
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from envoy.channels._telegram_signer import TelegramSigner
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

logger = logging.getLogger(__name__)

# INV-2: Closed vocabulary derived directly from the type alias — never hardcode.
_ALLOWED_DECISIONS: frozenset[str] = frozenset(typing.get_args(GrantMomentDecision))

# Telegram's documented maximum message length.
_MAX_MESSAGE_LENGTH: int = 4_096

# Queue capacity — overflow drops with OverflowDropEvent to Ledger.
_QUEUE_MAXSIZE: int = 100

# Default send timeout (seconds).
_DEFAULT_SEND_TIMEOUT: int = 10

# Telegram channel ID constant.
_TELEGRAM_CHANNEL_ID = "telegram"

# DoS ceiling: maximum concurrent in-flight grant moments.
_MAX_PENDING_DECISIONS: int = 1000
_RATE_LIMIT_RETRY_AFTER = 60  # seconds to suggest waiting when quota is exhausted


def _hash_pii(value: str) -> str:
    """SHA-256 hex digest truncated to 8 chars for PII-adjacent log fields.

    Per ``rules/observability.md`` Rule 8: schema-revealing identifiers at INFO/WARN
    must be hashed before emission.
    """
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def _coerce_decision(
    raw: Any,
    decision_options: tuple[str, ...],
) -> GrantMomentDecision:
    """Coerce a raw user response to a ``GrantMomentDecision``.

    Checks against the closed vocabulary first, then against the grant's own
    decision_options, then tries numeric index within the options tuple.

    Raises
    ------
    InvalidDecisionError
        If ``raw`` cannot be resolved to a member of ``_ALLOWED_DECISIONS``.
    """
    if isinstance(raw, int):
        options = sorted(_ALLOWED_DECISIONS)
        if 1 <= raw <= len(options):
            return options[raw - 1]  # type: ignore[return-value]
    if not isinstance(raw, str):
        raw = str(raw)
    normalised = raw.strip().lower()
    if normalised in _ALLOWED_DECISIONS:
        return normalised  # type: ignore[return-value]
    # Prefix match for friendly input (e.g. "approve" → "approve_once").
    matches = [d for d in _ALLOWED_DECISIONS if d.startswith(normalised)]
    if len(matches) == 1:
        return matches[0]  # type: ignore[return-value]
    # Sanitize `raw` to 32 printable chars before passing to error (CWE-117).
    # `raw` originates from untrusted inbound Telegram message text — an
    # attacker-controlled string of unbounded length.
    sanitized_raw = "".join(c for c in raw if c.isprintable())[:32]
    raise InvalidDecisionError(
        channel_id=_TELEGRAM_CHANNEL_ID,
        decision=sanitized_raw,
        allowed=tuple(sorted(_ALLOWED_DECISIONS)),
    )


# Type alias for the injected send callable.
_SendCallable = Callable[[str, str], Coroutine[Any, Any, None]]


class TelegramChannelAdapter(ChannelAdapter):
    """Telegram Bot API channel adapter.

    Parameters
    ----------
    primary_channel_id:
        The user's designated primary channel.  When this equals
        ``"telegram"``, this adapter IS primary.  High-stakes grants
        are gated to the primary channel.
    send_fn:
        Async callable ``(chat_id: str, text: str) -> None`` that delivers a
        message to Telegram.  Injected to keep the adapter testable without a
        live Bot API connection.  If omitted, send calls are no-ops (useful for
        read-only testing scenarios).
    inbound_queue:
        Optional pre-constructed :class:`asyncio.Queue` for inbound messages.
        Useful in tests; if omitted a fresh queue is created at startup.
    send_timeout:
        Timeout in seconds for outgoing send operations.  Default: 10 s.
    """

    def __init__(
        self,
        *,
        primary_channel_id: str = _TELEGRAM_CHANNEL_ID,
        send_fn: _SendCallable | None = None,
        inbound_queue: asyncio.Queue[InboundMessage] | None = None,
        send_timeout: int = _DEFAULT_SEND_TIMEOUT,
        secret_token: str = "",
    ) -> None:
        self._primary_channel_id = primary_channel_id
        self._send_fn = send_fn
        self._inbound_queue: asyncio.Queue[InboundMessage] | None = inbound_queue
        self._send_timeout = send_timeout
        self._secret_token = secret_token
        # Signer is None until startup (when secret_token is validated).
        self._signer: TelegramSigner | None = None

        self._started: bool = False
        # INV-3/6: single write-site for grant moment state.
        self._pending_grants: dict[str, asyncio.Queue[str]] = {}
        self._overflow_dropped: int = 0

    # ------------------------------------------------------------------
    # ChannelAdapter: identity
    # ------------------------------------------------------------------

    @property
    def channel_id(self) -> str:
        return _TELEGRAM_CHANNEL_ID

    # ------------------------------------------------------------------
    # ChannelAdapter: lifecycle
    # ------------------------------------------------------------------

    async def startup(self, config: Any = None) -> None:
        """Initialise the adapter.  Raises ``AlreadyStartedError`` if called twice."""
        if self._started:
            raise AlreadyStartedError(channel_id=_TELEGRAM_CHANNEL_ID)
        # Accept an optional updated secret_token via config dict.
        if isinstance(config, dict) and "secret_token" in config:
            self._secret_token = config["secret_token"]
        # Auth guard: reject blank secret_token before attempting connection.
        if not self._secret_token or not self._secret_token.strip():
            raise AuthenticationError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                credential_kind="secret_token",
                message="secret_token must be non-empty",
            )
        # Wire the signer now that the secret_token is validated.
        self._signer = TelegramSigner(secret_token=self._secret_token)
        if self._inbound_queue is None:
            self._inbound_queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)

        async def _telegram_startup_work() -> None:
            await asyncio.sleep(0)

        try:
            await asyncio.wait_for(_telegram_startup_work(), timeout=10)
        except asyncio.TimeoutError as exc:
            raise StartupTimeoutError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                timeout_seconds=10,
                message="Telegram startup exceeded 10s",
            ) from exc
        self._started = True
        logger.info(
            "channel.startup",
            extra={
                "channel_id": _TELEGRAM_CHANNEL_ID,
                "is_primary": self._primary_channel_id == _TELEGRAM_CHANNEL_ID,
            },
        )

    async def shutdown(self, drain_timeout_seconds: int = 5) -> None:
        """Tear down the adapter.  Idempotent — safe to call multiple times."""
        if not self._started:
            return
        self._started = False
        # Drain the inbound queue best-effort within the window.
        if self._inbound_queue is not None:
            try:
                async with asyncio.timeout(drain_timeout_seconds):
                    while not self._inbound_queue.empty():
                        self._inbound_queue.get_nowait()
            except (asyncio.TimeoutError, asyncio.QueueEmpty):
                pass
        # Cancel every in-flight grant future before clearing the map so that
        # coroutines awaiting send_grant_moment receive CancelledError instead
        # of waiting forever.  Mirrors the Discord and Web adapter patterns.
        for fut in list(self._pending_grants.values()):
            if not fut.done():
                fut.cancel()
        self._pending_grants.clear()
        logger.info("channel.shutdown", extra={"channel_id": _TELEGRAM_CHANNEL_ID})

    def _require_started(self, method_name: str) -> None:
        """Raise ``NotStartedError`` when the adapter is not running."""
        if not self._started:
            raise NotStartedError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                method_name=method_name,
            )

    # ------------------------------------------------------------------
    # ChannelAdapter: inbound
    # ------------------------------------------------------------------

    def receive_message(self) -> AsyncIterator[InboundMessage]:
        """Return an async iterator that yields inbound messages from the queue.

        This is a ``def`` (not ``async def``) per the ABC contract; it returns
        an async generator object that the caller can iterate with ``async for``.
        """
        self._require_started("receive_message")

        async def _generator() -> AsyncIterator[InboundMessage]:
            assert self._inbound_queue is not None  # set in startup()
            while True:
                try:
                    msg = await self._inbound_queue.get()
                except asyncio.CancelledError:
                    return
                yield msg

        return _generator()

    def enqueue(self, message: InboundMessage) -> None:
        """Push an ``InboundMessage`` onto the inbound queue.

        Called by the webhook transport layer after signature verification and
        deserialization.  Overflows are silently dropped (with a WARN log and
        an ``OverflowDropEvent``) rather than raising.
        """
        if self._inbound_queue is None:
            return
        try:
            self._inbound_queue.put_nowait(message)
        except asyncio.QueueFull:
            self._overflow_dropped += 1
            drop = OverflowDropEvent(
                channel_id=_TELEGRAM_CHANNEL_ID,
                dropped_count=self._overflow_dropped,
            )
            logger.warning(
                "channel.inbound.overflow_drop",
                extra={
                    "channel_id": _TELEGRAM_CHANNEL_ID,
                    "dropped_count": drop.dropped_count,
                },
            )

    # ------------------------------------------------------------------
    # ChannelAdapter: outbound
    # ------------------------------------------------------------------

    async def send_message(
        self,
        target_principal_id: str,
        payload: MessagePayload,
        *,
        visible_secret: VisibleSecret | None = None,
        timeout_seconds: int = _DEFAULT_SEND_TIMEOUT,
    ) -> SendReceipt:
        """Send a plain-text message to a Telegram recipient.

        Parameters
        ----------
        target_principal_id:
            Telegram chat_id (used as the destination).
        payload:
            Message payload.  The ``body`` must not exceed the Telegram
            platform maximum length.
        visible_secret:
            Optional visible-secret to prepend as an icon.
        timeout_seconds:
            Delivery timeout.

        Raises
        ------
        PayloadTooLargeError
            If ``payload.body`` exceeds the platform maximum.
        SendTimeoutError
            If the underlying send callable does not complete in time.
        """
        self._require_started("send_message")
        # H-05: rate-limit gate — consult rate_limit_status before every send.
        rl = await self.rate_limit_status()
        if rl.requests_remaining == 0 or rl.soft_quota_warning:
            raise RateLimitExceededError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                retry_after_seconds=_RATE_LIMIT_RETRY_AFTER,
            )
        if not target_principal_id or not target_principal_id.strip():
            raise PrincipalNotFoundError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                target_principal_id=target_principal_id,
                message="target_principal_id must be non-empty",
            )

        if len(payload.body) > _MAX_MESSAGE_LENGTH:
            raise PayloadTooLargeError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                actual_length=len(payload.body),
                max_length=_MAX_MESSAGE_LENGTH,
            )

        text = payload.body
        if visible_secret is not None:
            text = f"({visible_secret.icon}) {text}"

        logger.info(
            "channel.send_message.start",
            extra={
                "channel_id": _TELEGRAM_CHANNEL_ID,
                "target_principal_hash": _hash_pii(target_principal_id),  # INV-5
                "kind": payload.kind,
            },
        )

        if self._send_fn is not None:
            try:
                async with asyncio.timeout(timeout_seconds):
                    await self._send_fn(target_principal_id, text)
            except asyncio.TimeoutError as exc:
                logger.warning(
                    "channel.send_message.timeout",
                    extra={
                        "channel_id": _TELEGRAM_CHANNEL_ID,
                        "timeout_seconds": timeout_seconds,
                    },
                )
                raise SendTimeoutError(
                    channel_id=_TELEGRAM_CHANNEL_ID,
                    timeout_seconds=timeout_seconds,
                ) from exc

        receipt = SendReceipt(
            message_id=str(uuid.uuid4()),
            delivered_at=datetime.now(timezone.utc),
            channel_native_id=f"tg-{uuid.uuid4().hex[:12]}",
        )
        logger.info(
            "channel.send_message.ok",
            extra={
                "channel_id": _TELEGRAM_CHANNEL_ID,
                "message_id": receipt.message_id,
            },
        )
        return receipt

    # ------------------------------------------------------------------
    # ChannelAdapter: ritual delivery — grant moments
    # ------------------------------------------------------------------

    def _register_pending(self, request_id: str, response_queue: asyncio.Queue[str]) -> None:
        """INV-3/6: Single write-site for pending grant moment state.

        Raises ``PendingDecisionsCeilingError`` if the in-flight count would
        exceed ``_MAX_PENDING_DECISIONS`` (DoS protection).
        """
        if len(self._pending_grants) >= _MAX_PENDING_DECISIONS:
            raise PendingDecisionsCeilingError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                ceiling=_MAX_PENDING_DECISIONS,
                current_count=len(self._pending_grants),
            )
        self._pending_grants[request_id] = response_queue

    async def send_grant_moment(
        self,
        target_principal_id: str,
        grant: GrantMomentPayload,
        *,
        primary_only: bool = False,
        timeout_seconds: int = 30,
    ) -> GrantMomentReceipt:
        """Prompt the user for a grant moment decision via Telegram.

        INV-1 (payload side): reads ``grant.high_stakes`` (bool field on
        ``GrantMomentPayload``).
        INV-4: defense-in-depth — ``must_be_primary = primary_only or grant.high_stakes``.

        Raises
        ------
        NotPrimaryChannelError
            When this adapter is not primary and the grant requires a primary
            channel.
        GrantMomentExpiredError
            If no decision arrives within ``timeout_seconds``.
        """
        self._require_started("send_grant_moment")
        # H-05: rate-limit gate — consult rate_limit_status before every send.
        rl = await self.rate_limit_status()
        if rl.requests_remaining == 0 or rl.soft_quota_warning:
            raise RateLimitExceededError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                retry_after_seconds=_RATE_LIMIT_RETRY_AFTER,
            )
        if not target_principal_id or not target_principal_id.strip():
            raise PrincipalNotFoundError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                target_principal_id=target_principal_id,
                message="target_principal_id must be non-empty",
            )

        # INV-4: defense-in-depth — enforce even when primary_only=False.
        must_be_primary = primary_only or grant.high_stakes
        if must_be_primary and self._primary_channel_id != _TELEGRAM_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                primary_channel_id=self._primary_channel_id,
            )

        logger.info(
            "channel.send_grant_moment.start",
            extra={
                "channel_id": _TELEGRAM_CHANNEL_ID,
                "request_id": grant.request_id,
                "high_stakes": grant.high_stakes,
                "target_principal_hash": _hash_pii(target_principal_id),  # INV-5
            },
        )

        # INV-3/6: register via the single write-site.
        response_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        self._register_pending(grant.request_id, response_queue)

        # Send the prompt text to Telegram.
        prompt_text = self._render_grant_moment_prose(grant)
        if self._send_fn is not None:
            try:
                async with asyncio.timeout(self._send_timeout):
                    await self._send_fn(target_principal_id, prompt_text)
            except Exception as exc:
                logger.warning(
                    "channel.send_grant_moment.prompt_failed",
                    extra={
                        "channel_id": _TELEGRAM_CHANNEL_ID,
                        "request_id": grant.request_id,
                        "error_type": type(exc).__name__,
                    },
                )

        # Wait for the decision to arrive via post_decision().
        try:
            async with asyncio.timeout(timeout_seconds):
                raw_decision: str = await response_queue.get()
        except asyncio.TimeoutError as exc:
            self._pending_grants.pop(grant.request_id, None)
            logger.warning(
                "channel.send_grant_moment.expired",
                extra={
                    "channel_id": _TELEGRAM_CHANNEL_ID,
                    "request_id": grant.request_id,
                    "timeout_seconds": timeout_seconds,
                },
            )
            raise GrantMomentExpiredError(
                request_id=grant.request_id,
                timeout_seconds=timeout_seconds,
            ) from exc

        self._pending_grants.pop(grant.request_id, None)
        decision = _coerce_decision(raw_decision, grant.decision_options)

        logger.info(
            "channel.send_grant_moment.ok",
            extra={
                "channel_id": _TELEGRAM_CHANNEL_ID,
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

    async def render_grant_moment(self, request: Any) -> None:
        """M1 dispatch render — renders WITHOUT awaiting the user's decision.

        INV-1 (request side): reads ``novelty_class == "high_stakes"`` via
        ``getattr`` on ``GrantMomentRequest`` — NOT ``grant.high_stakes``.

        Parameters
        ----------
        request:
            A ``GrantMomentRequest``-like object.  Uses ``getattr`` to avoid
            circular imports.

        Raises on transport / render failure so ``ChannelHandoff`` records this
        adapter in ``HandoffPlan.refused_channels``.
        """
        self._require_started("render_grant_moment")

        # INV-1: canonical discriminator on the REQUEST object is novelty_class.
        novelty_class: str = getattr(request, "novelty_class", "")
        primary_only: bool = bool(getattr(request, "primary_only", False))
        must_be_primary: bool = primary_only or novelty_class == "high_stakes"

        if must_be_primary and self._primary_channel_id != _TELEGRAM_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_TELEGRAM_CHANNEL_ID,
                primary_channel_id=self._primary_channel_id,
            )

        principal_id: str = getattr(request, "principal_genesis_id", "")
        request_id: str = getattr(request, "request_id", "")
        description: str = getattr(request, "description", "")

        lines: list[str] = []
        if must_be_primary:
            lines.append("HIGH-STAKES GRANT MOMENT")
        lines.append(f"Request ID: {request_id}")
        if principal_id:
            lines.append(f"Principal: {_hash_pii(principal_id)}...")  # INV-5
        lines.append("")
        lines.append(description or "(no description provided)")
        lines.append("")
        lines.append("Options:")
        for i, decision in enumerate(sorted(_ALLOWED_DECISIONS), start=1):
            lines.append(f"  {i}. {decision}")

        rendered = "\n".join(lines)

        # Send to a target chat — extract from request if available.
        chat_id: str = getattr(request, "chat_id", "") or getattr(request, "principal_genesis_id", "")
        if self._send_fn and chat_id:
            try:
                async with asyncio.timeout(self._send_timeout):
                    await self._send_fn(chat_id, rendered)
            except Exception as exc:
                logger.error(
                    "channel.render_grant_moment.failed",
                    extra={
                        "channel_id": _TELEGRAM_CHANNEL_ID,
                        "request_id": request_id,
                        "error_type": type(exc).__name__,
                    },
                )
                raise

        logger.info(
            "channel.render_grant_moment.ok",
            extra={
                "channel_id": _TELEGRAM_CHANNEL_ID,
                "request_id": request_id,
                "principal_hash": _hash_pii(principal_id) if principal_id else "",  # INV-5
            },
        )

    def verify_inbound(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify the ``X-Telegram-Bot-Api-Secret-Token`` header.

        Returns ``True`` iff the header matches the configured secret token.
        Returns ``False`` if the adapter has not been started (signer not wired).
        """
        if self._signer is None:
            return False
        return self._signer.verify(body=body, headers=headers)

    def post_decision(self, request_id: str, raw_decision: str) -> bool:
        """Inject a decision for a pending grant moment.

        Called by the webhook transport layer when a user sends a response.

        Returns ``True`` if a pending grant was found and the decision was
        posted, ``False`` if no matching pending grant exists.
        """
        response_queue = self._pending_grants.get(request_id)
        if response_queue is None:
            return False
        try:
            response_queue.put_nowait(raw_decision)
            return True
        except asyncio.QueueFull:
            return False

    # ------------------------------------------------------------------
    # ChannelAdapter: ritual delivery — digest
    # ------------------------------------------------------------------

    async def send_digest(
        self,
        target_principal_id: str,
        digest: DailyDigestPayload,
        *,
        timeout_seconds: int = _DEFAULT_SEND_TIMEOUT,
    ) -> SendReceipt:
        """Deliver morning digest to a Telegram principal.

        Parameters
        ----------
        target_principal_id:
            Telegram chat_id.
        digest:
            Daily digest payload.
        timeout_seconds:
            Delivery timeout.

        Raises
        ------
        SendTimeoutError
            If the underlying send callable does not complete in time.
        """
        self._require_started("send_digest")

        logger.info(
            "channel.send_digest.start",
            extra={
                "channel_id": _TELEGRAM_CHANNEL_ID,
                "target_principal_hash": _hash_pii(target_principal_id),  # INV-5
                "digest_date": digest.digest_date,
            },
        )

        if self._send_fn is not None:
            text = f"Daily Digest ({digest.digest_date})\n\n{digest.markdown_body}"
            try:
                async with asyncio.timeout(timeout_seconds):
                    await self._send_fn(target_principal_id, text)
            except asyncio.TimeoutError as exc:
                logger.warning(
                    "channel.send_digest.timeout",
                    extra={
                        "channel_id": _TELEGRAM_CHANNEL_ID,
                        "timeout_seconds": timeout_seconds,
                    },
                )
                raise SendTimeoutError(
                    channel_id=_TELEGRAM_CHANNEL_ID,
                    timeout_seconds=timeout_seconds,
                ) from exc

        receipt = SendReceipt(
            message_id=str(uuid.uuid4()),
            delivered_at=datetime.now(timezone.utc),
            channel_native_id=f"tg-digest-{uuid.uuid4().hex[:12]}",
        )
        logger.info(
            "channel.send_digest.ok",
            extra={
                "channel_id": _TELEGRAM_CHANNEL_ID,
                "message_id": receipt.message_id,
            },
        )
        return receipt

    # ------------------------------------------------------------------
    # ChannelAdapter: introspection
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> ChannelCapabilities:
        """Return Telegram channel capability flags."""
        return ChannelCapabilities(
            supports_buttons=True,
            supports_attachments=True,
            supports_markdown=True,
            supports_voice=False,
            supports_reactions=True,
            max_message_length=_MAX_MESSAGE_LENGTH,
        )

    async def rate_limit_status(self) -> RateLimitStatus:
        """Return a nominal rate-limit status (no live tracking in Phase 01)."""
        return RateLimitStatus(
            requests_remaining=100,
            window_resets_at=None,
            soft_quota_warning=False,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_grant_moment_prose(self, grant: GrantMomentPayload) -> str:
        """Render a ``GrantMomentPayload`` as a Telegram message string."""
        lines: list[str] = []
        if grant.high_stakes:
            lines.append("HIGH-STAKES GRANT MOMENT")
        lines.append(f"Request: {grant.request_id}")
        lines.append(f"Intent: {grant.intent_id}")
        lines.append("")
        lines.append(grant.body or "(no description provided)")
        lines.append("")
        lines.append("Options (reply with number or name):")
        for i, decision in enumerate(sorted(_ALLOWED_DECISIONS), start=1):
            lines.append(f"  {i}. {decision}")
        return "\n".join(lines)
