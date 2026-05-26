"""envoy.grant_moment.errors — the 10-error taxonomy + state-machine plumbing.

Implements the error taxonomy frozen in `specs/grant-moment.md`
§ "Error taxonomy". Each error carries a plain-language default message
(non-technical users read these directly per `rules/communication.md`)
plus structured attributes the runtime acts on.

The taxonomy has 10 entries from the spec table; this module also exposes
``InvalidGrantMomentTransitionError`` for state-machine internal plumbing
(callers asking the M0→M4 machine for forbidden transitions). The
state-machine plumbing error is NOT in the spec § Error taxonomy table —
it is internal-API hygiene.

This module is pure Python; ZERO dependencies on other envoy packages.
"""

from __future__ import annotations

__all__ = [
    "GrantMomentError",
    # Spec § Error taxonomy (10 entries)
    "GrantMomentExpiredError",
    "GrantMomentTimeoutError",
    "DualSignatureRequiredError",
    "NotPrimaryChannelError",
    "VelocityRaiseCoolingOffError",
    "GrantMomentReplayError",
    "VisibleSecretMismatchError",
    "NoveltyFrictionRequiredError",
    "BackPressureQueueFullError",
    "CrossChannelConfirmFailedError",
    # State-machine internal plumbing
    "InvalidGrantMomentTransitionError",
]


class GrantMomentError(Exception):
    """Base class for every Grant Moment error.

    Catching this covers the whole taxonomy without naming each member.
    """


class GrantMomentExpiredError(GrantMomentError):
    """User did not respond within ``timeout_seconds``; M2 reached expiry.

    Carries ``request_id`` and ``timeout_seconds`` so the runtime can
    re-issue (cooldown applies if repeated within session).
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
                f"This request waited {timeout_seconds} seconds without a "
                "decision and has been cancelled. You can ask again when ready."
            )
        super().__init__(message)


class GrantMomentTimeoutError(GrantMomentError):
    """Channel transport hung mid-render before reaching M2 await.

    Carries ``request_id`` and ``channel_id`` so the user can re-issue on
    an alternate channel.
    """

    def __init__(
        self,
        request_id: str,
        channel_id: str,
        message: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.channel_id = channel_id
        if message is None:
            message = (
                f"The {channel_id} channel didn't respond in time. "
                "Try approving on a different channel."
            )
        super().__init__(message)


class DualSignatureRequiredError(GrantMomentError):
    """Cross-principal action: first signature in, second pending (Phase 03).

    Carries ``request_id`` and the ``awaiting_co_signer`` principal id.
    """

    def __init__(
        self,
        request_id: str,
        awaiting_co_signer: str,
        message: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.awaiting_co_signer = awaiting_co_signer
        if message is None:
            message = (
                "This action needs approval from another person before it "
                f"can proceed (waiting on {awaiting_co_signer})."
            )
        super().__init__(message)


class NotPrimaryChannelError(GrantMomentError):
    """High-stakes Grant Moment routed to a non-primary channel (H-03).

    Carries the routed-to ``channel_id`` and the user's ``primary_channel_id``.
    Structurally never auto-retryable — the user must approve on their
    designated primary channel.
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
                f"This decision can only be made on your main channel "
                f"({primary_channel_id}), not on {channel_id}."
            )
        super().__init__(message)


class VelocityRaiseCoolingOffError(GrantMomentError):
    """Velocity-raise approval attempted before 24h cooling-off (T-093 R2-H4).

    Carries ``elapsed_seconds`` and ``required_seconds`` so the runtime UX
    can render the wait window.
    """

    REQUIRED_COOLING_OFF_SECONDS = 24 * 60 * 60

    def __init__(
        self,
        elapsed_seconds: int,
        required_seconds: int | None = None,
        message: str | None = None,
    ) -> None:
        if required_seconds is None:
            required_seconds = self.REQUIRED_COOLING_OFF_SECONDS
        self.elapsed_seconds = elapsed_seconds
        self.required_seconds = required_seconds
        if message is None:
            remaining = max(0, required_seconds - elapsed_seconds)
            hours = remaining // 3600
            message = (
                "Raising limits needs a 24-hour pause first. "
                f"About {hours} hours left, or use Weekly Posture Review."
            )
        super().__init__(message)


class GrantMomentReplayError(GrantMomentError):
    """Same nonce or ``intent_id`` observed twice (T-008 nonce defense).

    Carries the duplicated ``nonce`` (or ``intent_id``) and the prior
    ``request_id`` it was first seen with. Structurally never retryable.
    """

    def __init__(
        self,
        duplicate_value: str,
        duplicate_kind: str,
        prior_request_id: str,
        message: str | None = None,
    ) -> None:
        self.duplicate_value = duplicate_value
        self.duplicate_kind = duplicate_kind
        self.prior_request_id = prior_request_id
        if message is None:
            message = (
                "We've already seen this request before. Refusing to "
                "process it again as a safety measure."
            )
        super().__init__(message)


class VisibleSecretMismatchError(GrantMomentError):
    """Rendered visible-secret bytes diverge from Trust-Vault stored secret.

    Carries the ``expected_phrase_hash`` and ``rendered_phrase_hash`` (NOT
    the phrase content itself — never leak the secret into log lines).
    """

    def __init__(
        self,
        expected_phrase_hash: str,
        rendered_phrase_hash: str,
        message: str | None = None,
    ) -> None:
        self.expected_phrase_hash = expected_phrase_hash
        self.rendered_phrase_hash = rendered_phrase_hash
        if message is None:
            message = (
                "The safety icon and phrase don't match what you set up. "
                "Please re-pair your channel via Boundary Conversation."
            )
        super().__init__(message)


class NoveltyFrictionRequiredError(GrantMomentError):
    """Caller attempted to bypass 5s read-delay / double-tap on novel pattern.

    Carries the ``required_friction`` description and ``request_id``.
    """

    def __init__(
        self,
        request_id: str,
        required_friction: str,
        message: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.required_friction = required_friction
        if message is None:
            message = (
                "This is a new kind of request. Please complete the "
                f"safety steps: {required_friction}."
            )
        super().__init__(message)


class BackPressureQueueFullError(GrantMomentError):
    """N parallel Grant Moments exceeded queue ceiling.

    Carries the ``queue_ceiling`` and current ``queue_depth`` so the UX
    can render the "too many concurrent grants" banner accurately.
    """

    def __init__(
        self,
        queue_ceiling: int,
        queue_depth: int,
        message: str | None = None,
    ) -> None:
        self.queue_ceiling = queue_ceiling
        self.queue_depth = queue_depth
        if message is None:
            message = (
                f"Too many requests waiting for your decision ({queue_depth} "
                f"of {queue_ceiling}). Please resolve some before new ones."
            )
        super().__init__(message)


class CrossChannelConfirmFailedError(GrantMomentError):
    """High-stakes Grant Moment cross-channel confirm leg failed.

    Carries ``request_id`` and the failed ``confirm_channel_id``.
    """

    def __init__(
        self,
        request_id: str,
        confirm_channel_id: str,
        message: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.confirm_channel_id = confirm_channel_id
        if message is None:
            message = (
                f"The confirmation on {confirm_channel_id} didn't go through. "
                "Please complete it before this can proceed."
            )
        super().__init__(message)


class InvalidGrantMomentTransitionError(GrantMomentError):
    """Caller asked the M0→M4 state machine for a forbidden transition.

    Carries the ``current_state`` and ``attempted_event``. NOT in the spec
    § Error taxonomy table — this is internal-API hygiene that surfaces
    state-machine misuse to the runtime.
    """

    def __init__(
        self,
        current_state: str,
        attempted_event: str,
        message: str | None = None,
    ) -> None:
        self.current_state = current_state
        self.attempted_event = attempted_event
        if message is None:
            message = (
                f"Cannot move from {current_state} via {attempted_event!r}: "
                "the Grant Moment state machine does not allow that transition."
            )
        super().__init__(message)
