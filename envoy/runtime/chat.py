# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.chat — the ``chat`` resident receive-loop (WS-6 S6c, LAST shard).

The minimal resident loop that completes the 10th canonical CLI command
(``envoy chat``). It is a TRANSPORT/CACHE, never the authority: the durable S4s
store (Region 1 pending-grant sub-store + Region 2 SessionObservedState) is the
single source of truth. The loop holds NO authoritative state, so a crash
mid-conversation loses nothing — a pending Grant Moment issued before the crash
survives in the store and is still answerable via ``envoy grant approve`` (S4g).

Per ``specs/session-runtime.md`` § "chat resident loop contract":

1. **Receive → handle → reply.** The loop iterates ``adapter.receive_message()``.
   For each inbound message the injected ``resolver`` decides whether the message
   carries an action that must pass the first-time-action gate (S5o). Plain
   conversational messages are acked; an action message runs the gate.

2. **Drive the Grant Moment via the S4r store-poll rendezvous.** On a
   ``FIRST_TIME_REQUIRES_GRANT`` verdict the loop issues a Grant Moment through
   the runtime (which writes the pending row to the durable store) and awaits the
   decision via ``await_decision`` — the store-poll rendezvous, NOT an in-process
   future. The human answers in a SEPARATE ``envoy grant`` invocation; the loop's
   poll observes the resolution. A ``RECOGNIZED`` verdict proceeds without a grant
   and the loop replies immediately.

3. **Boundary-fires-reset on disconnect.** When the receive iterator ends
   (channel disconnect) OR ``stop()`` is called, the loop fires
   ``SessionBoundarySignal.cross(trigger="channel_disconnect", ...)`` — the S5b
   signal that applies the T-013 reset to the session's observed-state cache, so
   the next session's first identical tool call is first-time-action again.

The message→action mapping (the ``resolver``) is INJECTED, not hardcoded: Phase-02
ships a structural resolver (a message naming a tool dispatch); a future agent
layer supplies an LLM-driven resolver without touching the loop. Dependencies are
injected at construction per ``rules/orphan-detection.md`` Rule 1 + ``rules/
facade-manager-detection.md`` Rule 3 — the loop never reaches out for its own
collaborators.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from envoy.channels.envelope import InboundMessage, MessagePayload
from envoy.channels.errors import AlreadyStartedError
from envoy.grant_moment import ApproveResolution, DeclineResolution
from envoy.grant_moment.errors import GrantMomentExpiredError
from envoy.runtime.observed_state import GateResult

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from envoy.channels.adapter import ChannelAdapter
    from envoy.grant_moment.runtime import EnvoyGrantMomentRuntime
    from envoy.runtime.observed_state_gate import SessionObservedStateGate
    from envoy.runtime.session_boundary import SessionBoundarySignal

__all__ = [
    "ChatActionSpec",
    "ChatActionUnsupportedError",
    "ChatMessageResolver",
    "ChatResidentLoop",
    "ChatTurnResult",
]


class ChatActionUnsupportedError(RuntimeError):
    """Raised when a resolver yields an action but the grant substrate is absent.

    The conversation-only loop (no ``runtime`` / ``gate`` wired) is a first-class
    mode — many chat sessions are pure conversation. But an action spec demands the
    first-time-action gate + grant runtime; surfacing this typed error (per
    ``rules/zero-tolerance.md`` Rule 3a — typed guard for a None backing object) is
    the honest failure, NOT a fabricated grant outcome.
    """


logger = logging.getLogger(__name__)

# The default per-turn grant-await budget mirrors `specs/grant-moment.md`
# § Timeout (5 minutes). The store-poll rendezvous (S4r) honours this as the
# poll deadline; on expiry the loop replies with the typed timeout, never a
# silent hang.
_DEFAULT_GRANT_TIMEOUT_SECONDS = 300

# The S5b end-trigger the loop fires when the channel disconnects. `cross`
# maps it to an "end" transition and applies the T-013 reset.
_DISCONNECT_TRIGGER = "channel_disconnect"


@dataclass(frozen=True, slots=True)
class ChatActionSpec:
    """A resolved action a chat message carries.

    ``issue_kwargs`` is the COMPLETE keyword set the loop forwards verbatim to
    :meth:`EnvoyGrantMomentRuntime.issue_grant_moment` on a first-time verdict.
    ``tool_name`` / ``tool_args_canonical`` are read back from it for the
    first-time-action gate, so there is a single source of truth (no field can
    drift between the gate check and the grant issue).
    """

    issue_kwargs: Mapping[str, Any]

    @property
    def tool_name(self) -> str:
        return str(self.issue_kwargs["tool_name"])

    @property
    def tool_args_canonical(self) -> dict[str, Any]:
        return dict(self.issue_kwargs["tool_args_canonical"])


# A resolver maps an inbound message to an action spec (the message carries a
# tool dispatch that must pass the gate) or ``None`` (a plain conversational
# message the loop simply acks). Injected; Phase-02 ships a structural resolver,
# a future agent layer supplies an LLM-driven one.
ChatMessageResolver = Callable[[InboundMessage], "ChatActionSpec | None"]


@dataclass(frozen=True, slots=True)
class ChatTurnResult:
    """The terminal outcome of one inbound message's handling.

    ``kind`` is one of ``"ack"`` (plain message), ``"recognized"`` (action gate
    cache-hit, no grant needed), ``"grant_approved"`` / ``"grant_declined"`` /
    ``"grant_modified"`` (a Grant Moment was issued + answered via the store-poll
    rendezvous), or ``"grant_expired"`` (the await deadline elapsed). ``request_id``
    is the Grant Moment id when one was issued, else ``None``.
    """

    kind: str
    reply_body: str
    request_id: str | None = None


@dataclass(slots=True)
class ChatResidentLoop:
    """The ``chat`` resident receive-loop. Transport over the durable store.

    Construct with the injected channel adapter, the grant-moment runtime (wired
    with a ``SessionRouter`` so ``await_decision`` polls the durable store), the
    S5o observed-state gate, and the S5b boundary signal. Call :meth:`run` to
    drain the channel's inbound stream until disconnect; the boundary reset fires
    in ``finally`` so an exception or a normal disconnect both reset the session.
    """

    adapter: ChannelAdapter
    boundary_signal: SessionBoundarySignal
    session_id: str
    resolver: ChatMessageResolver
    # The grant substrate is OPTIONAL: a conversation-only loop wires neither and
    # acks plain messages with real session-boundary semantics. An action spec
    # requires both; the typed guard in `handle_turn` enforces it (Rule 3a).
    runtime: EnvoyGrantMomentRuntime | None = None
    gate: SessionObservedStateGate | None = None
    grant_timeout_seconds: int = _DEFAULT_GRANT_TIMEOUT_SECONDS
    _stopped: bool = field(default=False, init=False)

    async def run(self) -> list[ChatTurnResult]:
        """Drain inbound messages until the channel disconnects, then reset.

        Returns the per-turn results in receive order (used by tests + the CLI
        transcript). The S5b boundary reset fires in ``finally`` — a normal
        disconnect (iterator exhausted) AND an exception both cross the boundary,
        so the next session's observed-state cache is always cleared.
        """
        results: list[ChatTurnResult] = []
        logger.info(
            "chat.loop.start",
            extra={"session_id_prefix": self.session_id[:8], "channel_id": self.adapter.channel_id},
        )
        # The resident loop owns the channel transport lifecycle: start it,
        # drain it, shut it down. `startup` is tolerated as idempotent (a
        # caller that pre-started the adapter is fine).
        with contextlib.suppress(AlreadyStartedError):
            await self.adapter.startup(None)
        try:
            async for message in self.adapter.receive_message():
                if self._stopped:
                    break
                results.append(await self.handle_turn(message))
        finally:
            # Session-end boundary FIRST (the T-013 reset is session semantics),
            # then channel transport teardown.
            await self._fire_disconnect_boundary()
            await self.adapter.shutdown()
            logger.info(
                "chat.loop.end",
                extra={"session_id_prefix": self.session_id[:8], "turns": len(results)},
            )
        return results

    def stop(self) -> None:
        """Request a graceful stop after the current in-flight turn completes."""
        self._stopped = True

    async def handle_turn(self, message: InboundMessage) -> ChatTurnResult:
        """Handle one inbound message: ack, recognize, or drive a Grant Moment.

        The store is authority throughout: the gate reads/writes Region 2 and the
        grant issue writes the Region 1 pending row BEFORE the await begins, so a
        crash anywhere after issue leaves an answerable pending grant in the store.
        """
        spec = self.resolver(message)
        if spec is None:
            return await self._reply(message, "ack", "received", kind="ack")

        if self.gate is None or self.runtime is None:
            raise ChatActionUnsupportedError(
                f"resolver produced an action ({spec.tool_name!r}) but this chat "
                "loop has no grant substrate wired (runtime + gate). Conversation-"
                "only loops cannot drive a Grant Moment."
            )

        verdict = await self.gate.evaluate(
            session_id=self.session_id,
            tool_name=spec.tool_name,
            args=spec.tool_args_canonical,
        )
        if verdict is GateResult.RECOGNIZED:
            return await self._reply(
                message,
                "ack",
                f"recognized: {spec.tool_name}; proceeding",
                kind="recognized",
            )

        # FIRST_TIME_REQUIRES_GRANT — issue a Grant Moment + await the decision
        # via the store-poll rendezvous (S4r). The pending row is durable the
        # instant `issue_grant_moment` returns; the human answers in a separate
        # `envoy grant` process. The loop owns NO copy of that state.
        request = await self.runtime.issue_grant_moment(**dict(spec.issue_kwargs))
        logger.info(
            "chat.grant.issued",
            extra={"session_id_prefix": self.session_id[:8], "request_id_prefix": request.request_id[:8]},
        )
        try:
            resolution = await self.runtime.await_decision(
                request.request_id, timeout_seconds=self.grant_timeout_seconds
            )
        except GrantMomentExpiredError:
            logger.warning(
                "chat.grant.expired",
                extra={"session_id_prefix": self.session_id[:8], "request_id_prefix": request.request_id[:8]},
            )
            return await self._reply(
                message,
                "error_notice",
                f"grant {request.request_id} expired without a decision",
                kind="grant_expired",
                request_id=request.request_id,
            )

        if isinstance(resolution, ApproveResolution):
            # Cache the now-approved fingerprint so an identical repeat THIS
            # session is RECOGNIZED (no second Grant Moment). The boundary reset
            # clears this at session end (T-013).
            await self.gate.observe(
                session_id=self.session_id,
                tool_name=spec.tool_name,
                args=spec.tool_args_canonical,
            )
            return await self._reply(
                message,
                "text",
                f"approved: {spec.tool_name}",
                kind="grant_approved",
                request_id=request.request_id,
            )
        if isinstance(resolution, DeclineResolution):
            return await self._reply(
                message,
                "text",
                f"declined: {spec.tool_name}",
                kind="grant_declined",
                request_id=request.request_id,
            )
        # ModifyResolution (or any future shape) — the action proceeds under the
        # modified terms; the loop surfaces the modification, the runtime owns the
        # modified envelope binding.
        return await self._reply(
            message,
            "text",
            f"modified: {spec.tool_name}",
            kind="grant_modified",
            request_id=request.request_id,
        )

    async def _reply(
        self,
        message: InboundMessage,
        payload_kind: str,
        body: str,
        *,
        kind: str,
        request_id: str | None = None,
    ) -> ChatTurnResult:
        await self.adapter.send_message(
            message.principal_genesis_id,
            MessagePayload(kind=payload_kind, body=body),  # type: ignore[arg-type]
        )
        return ChatTurnResult(kind=kind, reply_body=body, request_id=request_id)

    async def _fire_disconnect_boundary(self) -> None:
        """Fire the S5b channel-disconnect boundary (applies the T-013 reset).

        Best-effort: a boundary-emit failure MUST NOT mask the loop's own exit
        path, but it is surfaced loudly (never silently swallowed per
        ``rules/zero-tolerance.md`` Rule 3) so the next session can detect a
        stale cache.
        """
        try:
            await self.boundary_signal.cross(
                trigger=_DISCONNECT_TRIGGER, session_id_prior=self.session_id
            )
        except Exception:
            logger.exception(
                "chat.boundary.cross_failed",
                extra={"session_id_prefix": self.session_id[:8], "trigger": _DISCONNECT_TRIGGER},
            )
            raise
