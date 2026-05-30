"""envoy.channels.adapter — `ChannelAdapter` ABC.

Implements `specs/channel-adapters.md` § Adapter contract (lines 14-130)
verbatim. Every Phase-01 surface (CLI, Web, Telegram, Slack, Discord,
WhatsApp, iMessage, Signal) extends this ABC.

Composition philosophy per `rules/orphan-detection.md` Rule 1 and
`rules/facade-manager-detection.md` Rule 3: dependencies are injected at
construction (no global lookups; no hidden singletons). The runtime's
session router iterates registered adapters and dispatches to them; an
adapter never reaches out to fetch its own collaborators.

Phase-02 ritual surfaces (`send_posture_review`, `send_monthly_report`)
ship as abstract methods raising `PhaseDeferredError` from the default
implementation. Concrete adapters MAY override; Phase 01 surfaces inherit
the default refusal per `rules/zero-tolerance.md` Rule 2 + Rule 6.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from envoy.channels.envelope import (
    ChannelCapabilities,
    DailyDigestPayload,
    GrantMomentPayload,
    GrantMomentReceipt,
    InboundMessage,
    MessagePayload,
    MonthlyTrustReportPayload,
    PostureReviewReceipt,
    RateLimitStatus,
    SendReceipt,
    VisibleSecret,
    WeeklyPostureReviewPayload,
)
from envoy.channels.errors import PhaseDeferredError


class ChannelAdapter(ABC):
    """Abstract unified adapter every channel implements.

    The contract is frozen by `specs/channel-adapters.md` § Adapter contract.
    Subclasses MUST implement the abstract methods; the two Phase-02 ritual
    surfaces have default implementations that raise `PhaseDeferredError`
    so Phase 01 concrete subclasses are not forced to write `pass` bodies.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def channel_id(self) -> str:
        """Stable identifier (e.g. ``"telegram"``, ``"slack"``, ``"cli"``).

        MUST be unique across registered adapters. The runtime keys session
        state, rate-limit buckets, and Connection Vault entries on this
        value.
        """

    @abstractmethod
    async def startup(self, config: Any) -> None:
        """Initialise adapter (open transport, register webhook, authenticate).

        Timeout: 10s; fail-closed → raises `StartupTimeoutError`.
        Idempotent: calling twice MUST raise `AlreadyStartedError`.

        `config` is intentionally typed `Any` at the ABC level — concrete
        adapters declare their own narrowed config dataclass. The runtime
        constructs the per-channel config from the Connection Vault entry
        before calling `startup`.
        """

    @abstractmethod
    async def shutdown(self, drain_timeout_seconds: int = 5) -> None:
        """Drain pending sends, close transports.

        After `drain_timeout_seconds`, force-close. Idempotent: calling on
        an already-shutdown adapter is a no-op (no `AlreadyStopped` error).
        """

    # ------------------------------------------------------------------
    # Receive / send
    # ------------------------------------------------------------------

    @abstractmethod
    def receive_message(self) -> AsyncIterator[InboundMessage]:
        """Yield inbound messages as they arrive.

        Backpressure: bounded queue size 100 per channel; overflow drops
        with `OverflowDropEvent` written to the Ledger (NOT raised).
        Transport failures propagate as `ChannelTransportError`.

        Note: this is `def`, not `async def`. The implementation returns an
        async iterator; the caller iterates with `async for`. Decorating
        with `async def` would force every implementation to yield, which
        we want — but `abstractmethod` + `async def` on an iterator
        protocol confuses pyright. The runtime-side `async for` works the
        same way either way.
        """

    @abstractmethod
    async def send_message(
        self,
        target_principal_id: str,
        payload: MessagePayload,
        *,
        visible_secret: VisibleSecret | None = None,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        """Deliver a structured message.

        Timeout: `timeout_seconds`; on timeout raises `SendTimeoutError`.
        Rate-limit: consults `rate_limit_status()` before send; on quota
        exhaustion raises `RateLimitExceededError` with `retry_after_seconds`.
        Transient errors retried with jitter (max 3 attempts internally);
        permanent failures (auth, principal-not-found) raise immediately.
        """

    # ------------------------------------------------------------------
    # Ritual delivery — Phase 01 wires 2 of 4
    # ------------------------------------------------------------------

    @abstractmethod
    async def send_grant_moment(
        self,
        target_principal_id: str,
        grant: GrantMomentPayload,
        *,
        primary_only: bool = False,
        timeout_seconds: int = 30,
    ) -> GrantMomentReceipt:
        """Render Grant Moment + collect user response (spec § Ritual delivery).

        If `primary_only=True` AND this adapter is not the user's primary
        channel, raises `NotPrimaryChannelError` (H-03 primary-channel
        binding). Defense-in-depth: when `grant.high_stakes is True` the
        adapter MUST also enforce the binding even when `primary_only=False`
        — see concrete adapters' implementations. On `timeout_seconds`
        elapse without response, raises `GrantMomentExpiredError`.

        Distinct from `render_grant_moment` (M1 render-only surface used by
        `envoy.grant_moment.channel_handoff.ChannelHandoff.dispatch`):
        `send_grant_moment` is the full single-channel ritual (render +
        await + receipt); `render_grant_moment` is the multi-channel M1
        dispatch primitive that fires render across every active channel
        without awaiting a decision (the decision arrives async via
        `EnvoyGrantMomentRuntime.post_decision`).
        """

    @abstractmethod
    async def render_grant_moment(self, request: Any, *, visible_secret: Any = None) -> None:
        """M1 dispatch render — invoked by `ChannelHandoff.dispatch`.

        Renders the Grant Moment on this channel WITHOUT awaiting the user's
        decision. The decision flows back through
        `EnvoyGrantMomentRuntime.post_decision` per `specs/grant-moment.md`
        § State machine M1→M2.

        `request` is a `GrantMomentRequest` (from `envoy.grant_moment.runtime`)
        — typed `Any` here to avoid a circular import; concrete adapters
        narrow via local TYPE_CHECKING import.

        `visible_secret` (F15-b) is the runtime-resolved `VisibleSecret`
        (icon + color + phrase) passed SEPARATELY from `request` so the phrase
        never enters the signed request / Phase-A ledger row (R1-HIGH-1b). The
        adapter renders it per `specs/grant-moment.md` § Rendering ("Every
        dialog shows: Visible secret") — the T-018 anti-spoofing surface.
        `None` when no secret is set (Boundary Conversation S7 incomplete).

        Raises on transport / render failure so `ChannelHandoff` records the
        adapter in `HandoffPlan.refused_channels` per its dispatch contract.
        """

    @abstractmethod
    async def send_digest(
        self,
        target_principal_id: str,
        digest: DailyDigestPayload,
        *,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        """Deliver morning digest (specs/daily-digest.md owns payload schema).

        Rate-limit: 1 digest per principal per 24h enforced by the adapter;
        redundant calls return cached `SendReceipt`.
        """

    # Phase 02 ritual surfaces — default refusal so Phase 01 subclasses
    # inherit a typed error rather than a `pass` body.

    async def send_posture_review(
        self,
        target_principal_id: str,
        review: WeeklyPostureReviewPayload,
        *,
        timeout_seconds: int = 15,
    ) -> PostureReviewReceipt:
        """`specs/weekly-posture-review.md` ritual — wired in Phase 02.

        Default raises `PhaseDeferredError`. Concrete adapters MAY override
        when shard 11 lands the runtime side; for Phase 01 the refusal is
        the documented contract.
        """
        raise PhaseDeferredError(
            method_name=f"{type(self).__name__}.send_posture_review",
        )

    async def send_monthly_report(
        self,
        target_principal_id: str,
        report: MonthlyTrustReportPayload,
        *,
        timeout_seconds: int = 30,
    ) -> SendReceipt:
        """`specs/monthly-trust-report.md` ritual — wired in Phase 02.

        Default raises `PhaseDeferredError` per Phase 01 scope.
        """
        raise PhaseDeferredError(
            method_name=f"{type(self).__name__}.send_monthly_report",
        )

    # ------------------------------------------------------------------
    # Capabilities + observability
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def capabilities(self) -> ChannelCapabilities:
        """Static channel capabilities (spec § ChannelCapabilities)."""

    @abstractmethod
    async def rate_limit_status(self) -> RateLimitStatus:
        """Current quota window state (spec lines 124-129).

        Soft warning at 80% utilisation; hard quota raises
        `RateLimitExceededError` from `send_*`.
        """
