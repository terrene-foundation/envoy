"""envoy.channels.cli — `CLIChannelAdapter` wrapping kailash CLI channel.

Phase 01 surface for the developer / power-user / first-time-installer
onboarding path. No credentials (spec line 165). Wraps
`kailash.channels.cli_channel.CLIChannel` per
`01-analysis/16-channel-adapters-implementation.md` § 3 line 92.

Renders Grant Moment as a 4-option prompt (Approve once / Approve+author /
Deny / Modify) per `specs/grant-moment.md` § Rendering (lines 78-86).

Per `rules/framework-first.md` Engine→Primitive hierarchy: this adapter is
the Primitive layer; the Engine layer (`envoy.runtime.session.SessionRouter`,
landing in a sibling Wave-4 shard) dispatches across registered adapters.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, TextIO, cast

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
    NotPrimaryChannelError,
    NotStartedError,
    OverflowDropEvent,
    PayloadTooLargeError,
    SendTimeoutError,
)

if TYPE_CHECKING:
    from envoy.grant_moment.runtime import GrantMomentRequest

logger = logging.getLogger(__name__)


_CLI_CHANNEL_ID = "cli"
_CLI_MAX_MESSAGE_LENGTH = 4096


def _hash_pii(value: str) -> str:
    """SHA-256 hex digest truncated to 8 chars for PII-adjacent log fields.

    Per `rules/observability.md` Rule 8 (schema/identifier names at INFO/WARN
    bleed to aggregators with broader access than the production database).
    Used for `session_id` + `target_principal_id` in adapter log emissions.
    """
    return hashlib.sha256(value.encode()).hexdigest()[:8]


@dataclass(frozen=True, slots=True)
class CLIChannelConfig:
    """Construction-time config for `CLIChannelAdapter`.

    `primary_channel_id` is the user's designated primary channel id; the
    H-03 primary-channel binding check compares against this value. For
    the CLI adapter, the typical Phase-01 configuration is
    ``primary_channel_id="cli"`` (CLI IS the primary on a developer
    machine), but explicit construction makes the binding auditable.
    """

    primary_channel_id: str
    output_stream: TextIO | None = None
    input_stream: TextIO | None = None


class CLIChannelAdapter(ChannelAdapter):
    """Phase 01 CLI adapter (terminal prompt I/O substrate).

    Construction is dependency-injected per
    `rules/facade-manager-detection.md` Rule 3: streams default to `stdin`
    / `stdout` but are explicit-overridable for Tier-2 tests.

    Renders Grant Moment by writing the visible secret + body + numbered
    options to `output_stream`, then reads one line from `input_stream` and
    matches it against `GrantMomentPayload.decision_options`. Unknown
    response raises `GrantMomentExpiredError` after `timeout_seconds`
    (no retry loop — Phase 01 single-attempt; Phase 02 wires the retry UX).

    **TTY caveat (per /redteam R2 M-R2-2 closure):** when `output_stream` is
    the real `sys.stdout` connected to a terminal, writes are line-buffered;
    when piped (CI, headless), stdout becomes block-buffered until newline
    or `flush()`. The send path always calls `flush` so the modal renders
    promptly. When `input_stream` is `sys.stdin` connected to a non-terminal
    (closed pipe, EOF), `readline()` returns `""` immediately — the coercion
    fall-through routes that through `"modify"` per the unparseable-response
    security default. The `asyncio.to_thread` wrap is what makes the
    `asyncio.timeout` cancellation possible on a stuck synchronous read.
    """

    def __init__(self, config: CLIChannelConfig | None = None) -> None:
        self._config = config or CLIChannelConfig(primary_channel_id=_CLI_CHANNEL_ID)
        self._started = False
        self._closed = False
        self._inbound_queue: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=100)

    @property
    def channel_id(self) -> str:
        return _CLI_CHANNEL_ID

    async def startup(self, config: object | None = None) -> None:
        if self._started:
            raise AlreadyStartedError(channel_id=_CLI_CHANNEL_ID)
        # Per /redteam R2 MED-R2-05: a non-`CLIChannelConfig` config arg is
        # loud-refused so callers can't silently pass dicts/JSON that the
        # adapter would drop on the floor.
        if config is not None and not isinstance(config, CLIChannelConfig):
            raise TypeError(
                f"CLIChannelAdapter.startup expected CLIChannelConfig "
                f"(or None to reuse construction config), got "
                f"{type(config).__name__}."
            )
        if isinstance(config, CLIChannelConfig):
            self._config = config
        self._started = True
        self._closed = False
        logger.info("channel.startup", extra={"channel_id": _CLI_CHANNEL_ID})

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
        logger.info("channel.shutdown", extra={"channel_id": _CLI_CHANNEL_ID})

    async def receive_message(self) -> AsyncIterator[InboundMessage]:
        # The CLI adapter's inbound stream is driven by external test harnesses
        # injecting via `_inject_inbound`; production CLI inbound is the
        # interactive prompt loop owned by `envoy.cli`.
        while not self._closed:
            try:
                yield await self._inbound_queue.get()
            except asyncio.CancelledError:
                return

    async def _inject_inbound(self, msg: InboundMessage) -> None:
        """Test-only hook: push an `InboundMessage` onto the queue.

        Production CLI inbound flows through `envoy.cli` ↔ `_inbound_queue`;
        Tier-2 tests use this hook to exercise `receive_message` without an
        actual terminal.

        On queue overflow (>100 messages buffered), the message is dropped
        with an `OverflowDropEvent` written to the Ledger via a WARN log
        per spec § Receive (line 46 — "overflow drops with `OverflowDropEvent`
        to Ledger") + `rules/observability.md` Rule 7 (bulk-op partial-failure
        WARN). The producer does NOT block — Phase 01 contract is drop-with-audit,
        NOT backpressure-block.
        """
        try:
            self._inbound_queue.put_nowait(msg)
        except asyncio.QueueFull:
            drop = OverflowDropEvent(channel_id=_CLI_CHANNEL_ID, dropped_count=1)
            logger.warning(
                "channel.inbound.overflow_drop",
                extra={
                    "channel_id": _CLI_CHANNEL_ID,
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
        if len(payload.body) > _CLI_MAX_MESSAGE_LENGTH:
            raise PayloadTooLargeError(
                channel_id=_CLI_CHANNEL_ID,
                actual_length=len(payload.body),
                max_length=_CLI_MAX_MESSAGE_LENGTH,
            )
        out = self._config.output_stream or sys.stdout
        line = f"[{payload.kind}] {payload.body}\n"
        # Per T-018 + `rules/security.md` § "No secrets in logs":
        # `visible_secret.phrase` MUST NEVER appear in send_message output —
        # the icon-only render is intentional (Grant Moment is the ONLY surface
        # that renders the phrase; messages render the icon as a visual
        # provenance hint without leaking the secret). The asymmetry is pinned
        # by `tests/integration/channels/test_visible_secret_redaction.py`.
        if visible_secret is not None:
            line = f"({visible_secret.icon}) {line}"
        logger.info(
            "channel.send_message.start",
            extra={
                "channel_id": _CLI_CHANNEL_ID,
                "target_principal_hash": _hash_pii(target_principal_id),
                "kind": payload.kind,
            },
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                # stdout writes are sync but quick; the timeout exists so a
                # stuck pipe (e.g., orphaned terminal) raises loudly rather
                # than hanging the runtime.
                await asyncio.to_thread(out.write, line)
                await asyncio.to_thread(out.flush)
        except asyncio.TimeoutError as exc:
            logger.warning(
                "channel.send_message.timeout",
                extra={
                    "channel_id": _CLI_CHANNEL_ID,
                    "timeout_seconds": timeout_seconds,
                },
            )
            raise SendTimeoutError(
                channel_id=_CLI_CHANNEL_ID,
                timeout_seconds=timeout_seconds,
            ) from exc
        receipt = SendReceipt(
            message_id=str(uuid.uuid4()),
            delivered_at=datetime.now(timezone.utc),
            channel_native_id=f"cli-{uuid.uuid4().hex[:12]}",
        )
        logger.info(
            "channel.send_message.ok",
            extra={
                "channel_id": _CLI_CHANNEL_ID,
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
        # H-03 primary-channel binding (spec lines 183-185). Defense-in-depth:
        # `grant.high_stakes is True` ALSO requires the primary channel even
        # when the caller forgot `primary_only=True`. Single-layer kwarg
        # gating is insufficient — the adapter MUST also enforce on the
        # payload-level discriminator.
        must_be_primary = primary_only or grant.high_stakes
        if must_be_primary and self._config.primary_channel_id != _CLI_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_CLI_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )
        # Per /redteam R2 MED M-R2-1 (reviewer): mirror Web's structured-log
        # shape on the start/expired/ok transitions.
        logger.info(
            "channel.send_grant_moment.start",
            extra={
                "channel_id": _CLI_CHANNEL_ID,
                "request_id": grant.request_id,
                "high_stakes": grant.high_stakes,
            },
        )
        out = self._config.output_stream or sys.stdout
        inp = self._config.input_stream or sys.stdin
        rendered = self._render_grant_moment_prose(grant)
        try:
            async with asyncio.timeout(timeout_seconds):
                await asyncio.to_thread(out.write, rendered)
                await asyncio.to_thread(out.flush)
                response = (await asyncio.to_thread(inp.readline)).strip()
        except asyncio.TimeoutError as exc:
            logger.warning(
                "channel.send_grant_moment.expired",
                extra={
                    "channel_id": _CLI_CHANNEL_ID,
                    "request_id": grant.request_id,
                    "timeout_seconds": timeout_seconds,
                },
            )
            raise GrantMomentExpiredError(
                request_id=grant.request_id,
                timeout_seconds=timeout_seconds,
            ) from exc
        decision = self._coerce_decision(response, grant.decision_options)
        logger.info(
            "channel.send_grant_moment.ok",
            extra={
                "channel_id": _CLI_CHANNEL_ID,
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
        """M1 render-only — satisfies `envoy.grant_moment.channel_handoff.ChannelAdapterProtocol`.

        Writes the rendering prose to the output stream WITHOUT awaiting a
        user decision; the decision arrives async via
        `EnvoyGrantMomentRuntime.post_decision`. Returns on successful render;
        raises on transport / IO failure so `ChannelHandoff` records the
        adapter in `HandoffPlan.refused_channels`.

        Distinct from `send_grant_moment` (the full ritual; collects the
        decision inline). The two surfaces coexist because the spec mandates
        a full-ritual surface (`send_grant_moment` per spec line 69) AND the
        runtime mandates an M1-only surface (`render_grant_moment` per
        `envoy.grant_moment.channel_handoff` Protocol).

        Per /redteam R3 HIGH-R3-1 closure: H-03 binding reads the canonical
        `GrantMomentRequest` discriminators (`novelty_class == "high_stakes"`
        and `primary_only is True`) rather than the pre-R3 `high_stakes`
        field that does not exist on the real dataclass.
        """
        self._require_started("render_grant_moment")
        novelty_class = getattr(request, "novelty_class", "")
        primary_only = bool(getattr(request, "primary_only", False))
        must_be_primary = primary_only or novelty_class == "high_stakes"
        if must_be_primary and self._config.primary_channel_id != _CLI_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_CLI_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
            )
        request_id = getattr(request, "request_id", None)
        logger.info(
            "channel.render_grant_moment",
            extra={
                "channel_id": _CLI_CHANNEL_ID,
                "request_id": request_id,
                "novelty_class": novelty_class,
                "primary_only": primary_only,
            },
        )
        out = self._config.output_stream or sys.stdout
        rendered = self._render_grant_moment_request_prose(request)
        await asyncio.to_thread(out.write, rendered)
        await asyncio.to_thread(out.flush)

    async def send_digest(
        self,
        target_principal_id: str,
        digest: DailyDigestPayload,
        *,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        # Daily digest renders as a single multi-line message at the CLI;
        # the per-principal 24h cache is the Engine layer's concern
        # (`envoy.daily_digest`) — adapters faithfully deliver whatever the
        # runtime hands them.
        body = f"=== Daily Digest {digest.digest_date} ===\n{digest.markdown_body}"
        payload = MessagePayload(kind="system_notice", body=body)
        return await self.send_message(
            target_principal_id,
            payload,
            timeout_seconds=timeout_seconds,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_buttons=False,
            supports_attachments=False,
            supports_markdown=True,  # terminal-rendered markdown via downstream renderer
            supports_voice=False,
            supports_reactions=False,
            max_message_length=_CLI_MAX_MESSAGE_LENGTH,
        )

    async def rate_limit_status(self) -> RateLimitStatus:
        # CLI has no upstream quota; `window_resets_at=None` signals "no
        # enforced rate limit applies" per `RateLimitStatus` docstring.
        return RateLimitStatus(
            requests_remaining=10**9,
            window_resets_at=None,
            soft_quota_warning=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_started(self, method_name: str = "send_*") -> None:
        if not self._started or self._closed:
            # Surfaces as a typed `ChannelAdapterError` subclass so callers
            # catching the family don't miss this case. Replaces the pre-R1
            # bare `RuntimeError` per `rules/zero-tolerance.md`
            # Rule 3a (typed delegate guards for None backing objects).
            raise NotStartedError(channel_id=_CLI_CHANNEL_ID, method_name=method_name)

    @staticmethod
    def _render_grant_moment_prose(grant: GrantMomentPayload) -> str:
        lines = [
            f"\n--- Grant Moment ({grant.request_id}) ---",
            f"Safety phrase: {grant.visible_secret.icon} {grant.visible_secret.phrase}",
            grant.body,
            "Options:",
        ]
        for idx, opt in enumerate(grant.decision_options, start=1):
            lines.append(f"  {idx}) {opt}")
        lines.append("> ")
        return "\n".join(lines)

    @staticmethod
    def _render_grant_moment_request_prose(request: "GrantMomentRequest") -> str:
        # M1 render-only — reads the canonical `GrantMomentRequest` shape
        # from `envoy.grant_moment.signed_consent` (per /redteam R3 MED-R3-02
        # closure: pre-R3 the renderer read `visible_secret`/`body`/
        # `decision_options` which do NOT exist on the dataclass, silently
        # falling through to empty defaults — the silent-fallback pattern in
        # `rules/zero-tolerance.md` Rule 3). The canonical 5 elements
        # available on `GrantMomentRequest` are: request_id + tool_name +
        # why_asking + consequence_preview (4 sub-fields) + novelty_class.
        # The visible-secret render happens in the full-ritual
        # `_render_grant_moment_prose` path (consumes the runtime-resolved
        # `VisibleSecret`); the M1 dispatch surface does not carry it.
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
            # Render each `ConsequencePreview` field explicitly per
            # /redteam R3 MED-R3-03 closure (avoid bare dataclass repr
            # interpolation that would leak schema-level fields wholesale).
            # Per /redteam R4 MED-R4-1 closure: render the 4th canonical
            # field `recipient` too — `specs/grant-moment.md` § Rendering
            # enumerates "budget, reversibility, recipient, data" as the
            # 4-field preview shown to the user.
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

    @staticmethod
    def _coerce_decision(response: str, options: tuple[str, ...]) -> GrantMomentDecision:
        # Accept either the literal option name OR a 1-based index.
        if response in options:
            return cast("GrantMomentDecision", response)
        if response.isdigit():
            idx = int(response) - 1
            if 0 <= idx < len(options):
                return cast("GrantMomentDecision", options[idx])
        # Unknown response — coerce to a "modify" decision so the runtime
        # routes through the modification path rather than treating an
        # unparseable line as a silent approval (security default).
        if "modify" in options:
            return "modify"
        if "deny" in options:
            return "deny"
        # `GrantMomentPayload.__post_init__` enforces non-empty `options` so
        # `options[0]` is structurally safe.
        return cast("GrantMomentDecision", options[0])
