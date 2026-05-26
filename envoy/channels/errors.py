"""envoy.channels.errors — 11 typed errors per spec § Error taxonomy.

Implements `specs/channel-adapters.md` § Error taxonomy (lines 199-214). Each
error subclasses `ChannelAdapterError` so callers can catch the whole family
without naming each member. Plain-language default messages per
`rules/communication.md` (non-technical users read these directly).

Phase-02 ritual-delivery surfaces (`send_posture_review`,
`send_monthly_report`) raise `PhaseDeferredError` per
`rules/zero-tolerance.md` Rule 2 — no `pass`-bodied stubs, no
`NotImplementedError` without provenance.
"""

from __future__ import annotations

__all__ = [
    "ChannelAdapterError",
    # 11 entries per spec § Error taxonomy table
    "StartupTimeoutError",
    "AlreadyStartedError",
    "ChannelTransportError",
    "OverflowDropEvent",
    "SendTimeoutError",
    "RateLimitExceededError",
    "NotPrimaryChannelError",
    "GrantMomentExpiredError",
    "PrincipalNotFoundError",
    "AuthenticationError",
    "PayloadTooLargeError",
    # Phase-02-defer hygiene (NOT a runtime channel-traffic error;
    # raised by abstract methods Phase 01 hasn't wired yet)
    "PhaseDeferredError",
]


class ChannelAdapterError(Exception):
    """Base class for every channel-adapter error.

    Catching this covers the spec's 11-entry taxonomy without naming each
    member. The phase-defer hygiene error also subclasses this so callers
    can catch the family uniformly.
    """


class StartupTimeoutError(ChannelAdapterError):
    """`startup(config)` exceeded the 10s budget (spec line 26).

    Carries the `channel_id` and the configured `timeout_seconds` so the
    runtime's retry/backoff loop can report which channel failed.
    """

    def __init__(
        self,
        channel_id: str,
        timeout_seconds: int = 10,
        message: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.timeout_seconds = timeout_seconds
        if message is None:
            message = (
                f"The {channel_id} channel didn't finish connecting within "
                f"{timeout_seconds} seconds. Check your credentials and try again."
            )
        super().__init__(message)


class AlreadyStartedError(ChannelAdapterError):
    """`startup` called on a running adapter (spec line 29; programming error).

    No retry path — the caller forgot to call `shutdown` first. Carries the
    `channel_id` so the runtime can name the offending adapter.
    """

    def __init__(self, channel_id: str, message: str | None = None) -> None:
        self.channel_id = channel_id
        if message is None:
            message = (
                f"The {channel_id} channel is already running. Stop it before " "starting again."
            )
        super().__init__(message)


class ChannelTransportError(ChannelAdapterError):
    """WebSocket / HTTP transport failure during `receive_message` (spec line 47).

    Carries `channel_id` and the underlying transport-layer exception so the
    runtime's reconnection backoff can log the root cause without leaking
    raw stack frames to the user.
    """

    def __init__(
        self,
        channel_id: str,
        underlying: BaseException | None = None,
        message: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.underlying = underlying
        if message is None:
            message = (
                f"Lost connection to {channel_id}. We'll try to reconnect; "
                "if it keeps failing, check your network."
            )
        super().__init__(message)


class OverflowDropEvent(ChannelAdapterError):
    """Inbound queue exceeded the 100-message ceiling (spec line 46).

    Per the spec table line 205 ("Ledger only, not raised") the runtime does
    NOT raise this to user code; the adapter writes the drop event to the
    Ledger and continues. The class exists so the Ledger emit-site has a
    typed envelope to construct.
    """

    def __init__(
        self,
        channel_id: str,
        dropped_count: int,
        message: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.dropped_count = dropped_count
        if message is None:
            message = (
                f"Dropped {dropped_count} message(s) from {channel_id} " "(inbound queue full)."
            )
        super().__init__(message)


class SendTimeoutError(ChannelAdapterError):
    """`send_*` exceeded its method timeout (spec line 57).

    Carries `channel_id` and the configured `timeout_seconds`. Distinguished
    from `GrantMomentExpiredError` (which is M2-await expiry on the runtime
    side); this is transport-layer hang on the adapter side.
    """

    def __init__(
        self,
        channel_id: str,
        timeout_seconds: int,
        message: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.timeout_seconds = timeout_seconds
        if message is None:
            message = (
                f"The {channel_id} channel didn't acknowledge in "
                f"{timeout_seconds} seconds. Try again or use a different channel."
            )
        super().__init__(message)


class RateLimitExceededError(ChannelAdapterError):
    """Channel quota exhausted (spec line 58).

    Carries `retry_after_seconds` so the caller can render the wait window.
    The runtime routes high-stakes payloads to the user's primary channel
    when this fires on a non-primary adapter.
    """

    def __init__(
        self,
        channel_id: str,
        retry_after_seconds: int,
        message: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.retry_after_seconds = retry_after_seconds
        if message is None:
            message = (
                f"{channel_id} is rate-limiting us. Try again in about "
                f"{retry_after_seconds} seconds."
            )
        super().__init__(message)


class NotPrimaryChannelError(ChannelAdapterError):
    """High-stakes Grant Moment routed to non-primary channel (spec line 208; H-03).

    Structurally never auto-retryable — the user MUST approve on their
    designated primary channel. Carries the routed-to `channel_id` and the
    user's `primary_channel_id` so the UX can render the redirect prompt.

    Note: this error subclasses `ChannelAdapterError` AND mirrors the
    `envoy.grant_moment.errors.NotPrimaryChannelError` defined in the
    grant_moment package — the two namespaces coexist because they raise
    at distinct layers (grant_moment at M3 runtime; channels at adapter
    boundary). Callers catching `envoy.grant_moment.errors.NotPrimaryChannelError`
    do NOT catch this class; explicit by design.
    """

    def __init__(
        self,
        channel_id: str,
        primary_channel_id: str,
        message: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.primary_channel_id = primary_channel_id
        if message is None:
            message = (
                f"High-stakes decisions can only be made on your main channel "
                f"({primary_channel_id}), not on {channel_id}."
            )
        super().__init__(message)


class GrantMomentExpiredError(ChannelAdapterError):
    """User did not respond within `timeout_seconds` (spec line 209).

    Same wire-name as `envoy.grant_moment.errors.GrantMomentExpiredError`
    but raised at the adapter boundary (channel transport-layer wait) rather
    than the runtime M2-await boundary. Carries `request_id` so the runtime
    cooldown ratchet can correlate.
    """

    def __init__(
        self,
        request_id: str,
        timeout_seconds: int,
        message: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.timeout_seconds = timeout_seconds
        if message is None:
            message = (
                f"Request {request_id} expired after {timeout_seconds} seconds "
                "without a decision. You can re-issue it when you're ready."
            )
        super().__init__(message)


class PrincipalNotFoundError(ChannelAdapterError):
    """`target_principal_id` not registered with the adapter (spec line 210).

    Raised by `send_*` when the principal-to-channel mapping in the
    Connection Vault has no entry for `target_principal_id`. The fix is
    re-pairing via Boundary Conversation; no auto-retry path.
    """

    def __init__(
        self,
        channel_id: str,
        target_principal_id: str,
        message: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.target_principal_id = target_principal_id
        if message is None:
            message = (
                f"{channel_id} isn't paired with the person you're trying to "
                "reach. Re-pair the channel via Boundary Conversation."
            )
        super().__init__(message)


class AuthenticationError(ChannelAdapterError):
    """Bot token / OAuth token expired or revoked (spec line 211).

    Carries `channel_id` and the credential-kind (`"bot_token" |
    "oauth_access_token" | "signing_secret"`) so the user can locate the
    right re-authentication entry-point.
    """

    def __init__(
        self,
        channel_id: str,
        credential_kind: str,
        message: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.credential_kind = credential_kind
        if message is None:
            message = (
                f"{channel_id}'s {credential_kind} isn't valid anymore. " "Please re-authenticate."
            )
        super().__init__(message)


class PayloadTooLargeError(ChannelAdapterError):
    """Payload exceeded `capabilities.max_message_length` (spec line 212).

    Caller's responsibility to split or summarise; no auto-retry. Carries
    the payload `actual_length` and `max_length` so the runtime can render
    "split into N messages" guidance.
    """

    def __init__(
        self,
        channel_id: str,
        actual_length: int,
        max_length: int,
        message: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.actual_length = actual_length
        self.max_length = max_length
        if message is None:
            message = (
                f"This message is too long for {channel_id} "
                f"({actual_length} chars; limit is {max_length}). "
                "Please shorten or split it."
            )
        super().__init__(message)


class PhaseDeferredError(ChannelAdapterError):
    """A ritual-delivery surface defined by the spec is deferred to Phase 02.

    Phase 01 ships `send_grant_moment` + `send_digest` wired; `send_posture_review`
    and `send_monthly_report` raise this error per
    `rules/zero-tolerance.md` Rule 2 (no `pass` bodies; document the deferral
    via a typed error naming the deferring phase). Carries the `method_name`
    and `deferred_to_phase` so callers see exactly which surface is unwired.
    """

    def __init__(
        self,
        method_name: str,
        deferred_to_phase: str = "Phase 02",
        message: str | None = None,
    ) -> None:
        self.method_name = method_name
        self.deferred_to_phase = deferred_to_phase
        if message is None:
            message = (
                f"`{method_name}` is not wired in Phase 01 — it ships in "
                f"{deferred_to_phase}. Use the available ritual surfaces "
                "(`send_grant_moment`, `send_digest`) until then."
            )
        super().__init__(message)
