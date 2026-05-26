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
import sys
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TextIO

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


_CLI_CHANNEL_ID = "cli"
_CLI_MAX_MESSAGE_LENGTH = 4096
_RATE_LIMIT_NEVER_RESETS = datetime(9999, 12, 31, tzinfo=timezone.utc)


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
        if isinstance(config, CLIChannelConfig):
            self._config = config
        self._started = True
        self._closed = False

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
        """
        await self._inbound_queue.put(msg)

    async def send_message(
        self,
        target_principal_id: str,
        payload: MessagePayload,
        *,
        visible_secret: VisibleSecret | None = None,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        self._require_started()
        if len(payload.body) > _CLI_MAX_MESSAGE_LENGTH:
            raise PayloadTooLargeError(
                channel_id=_CLI_CHANNEL_ID,
                actual_length=len(payload.body),
                max_length=_CLI_MAX_MESSAGE_LENGTH,
            )
        out = self._config.output_stream or sys.stdout
        line = f"[{payload.kind}] {payload.body}\n"
        if visible_secret is not None:
            line = f"({visible_secret.icon}) {line}"
        try:
            async with asyncio.timeout(timeout_seconds):
                # stdout writes are sync but quick; the timeout exists so a
                # stuck pipe (e.g., orphaned terminal) raises loudly rather
                # than hanging the runtime.
                await asyncio.to_thread(out.write, line)
                await asyncio.to_thread(out.flush)
        except asyncio.TimeoutError as exc:
            raise SendTimeoutError(
                channel_id=_CLI_CHANNEL_ID,
                timeout_seconds=timeout_seconds,
            ) from exc
        return SendReceipt(
            message_id=str(uuid.uuid4()),
            delivered_at=datetime.now(timezone.utc),
            channel_native_id=f"cli-{uuid.uuid4().hex[:12]}",
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
        if primary_only and self._config.primary_channel_id != _CLI_CHANNEL_ID:
            raise NotPrimaryChannelError(
                channel_id=_CLI_CHANNEL_ID,
                primary_channel_id=self._config.primary_channel_id,
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
            raise GrantMomentExpiredError(
                request_id=grant.request_id,
                timeout_seconds=timeout_seconds,
            ) from exc
        decision = self._coerce_decision(response, grant.decision_options)
        return GrantMomentReceipt(
            request_id=grant.request_id,
            grant_id=str(uuid.uuid4()),
            decision=decision,
            decided_at=datetime.now(timezone.utc),
            channel_signature="",
        )

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
        # CLI has no upstream quota; report unbounded remaining + sentinel reset.
        return RateLimitStatus(
            requests_remaining=10**9,
            window_resets_at=_RATE_LIMIT_NEVER_RESETS,
            soft_quota_warning=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_started(self) -> None:
        if not self._started or self._closed:
            # Programming error — call startup() first. Surfaces as a typed
            # error rather than `AttributeError` per `rules/zero-tolerance.md`
            # Rule 3a (typed delegate guards for None backing objects).
            raise RuntimeError(f"{type(self).__name__} not started; call startup() before send_*.")

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
    def _coerce_decision(response: str, options: tuple[str, ...]) -> str:
        # Accept either the literal option name OR a 1-based index.
        if response in options:
            return response
        if response.isdigit():
            idx = int(response) - 1
            if 0 <= idx < len(options):
                return options[idx]
        # Unknown response — coerce to a "modify" decision so the runtime
        # routes through the modification path rather than treating an
        # unparseable line as a silent approval (security default).
        if "modify" in options:
            return "modify"
        if "deny" in options:
            return "deny"
        # Fall back to the first option; should never happen because every
        # GrantMomentPayload carries at least one option by construction.
        return options[0]
