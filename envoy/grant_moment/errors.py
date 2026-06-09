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

## Layer attribution — which surface raises each error

The error taxonomy IS the consumer-facing contract; raise sites land
alongside the runtime surfaces that detect each condition. The dispatch
+ classifier surfaces in this package (``ChannelHandoff``,
``OutOfEnvelopeDetector``, ``CascadeRevocationOrchestrator``,
``PlanSuspensionBridge``) handle the structural layer; the per-error
raise sites distribute across the structural + runtime surfaces:

- ``InvalidGrantMomentTransitionError`` — raised here, by
  ``envoy.grant_moment.state_machine.next_state`` at every forbidden
  ``(state, event)`` pair.
- ``CascadeIncompleteError`` (defined in
  ``envoy.grant_moment.cascade_orchestrator``, not this module) —
  raised by ``CascadeRevocationOrchestrator.revoke_and_verify`` when
  the runtime's ``trust_cascade_revoke`` returned a set missing one
  or more expected descendants.
- ``GrantMomentExpiredError`` — raised by the M2-await timeout path of
  the future ``EnvoyGrantMomentRuntime`` facade (the M0→M4 driver that
  composes Trust Vault + Ledger + ChannelHandoff). Wired as a wire-shape
  contract in this PR; raised when the runtime layer that owns the
  timeout loop lands.
- ``GrantMomentTimeoutError`` — raised by the runtime channel-render
  path when a channel adapter's ``render_grant_moment`` exceeds its
  per-channel timeout budget.
- ``DualSignatureRequiredError`` — raised by the Phase-03 cross-principal
  decision pipeline when the first principal signed and the second is
  pending. Phase 01 does not exercise this path (single principal); the
  contract carries because the wire shape supports it.
- ``NotPrimaryChannelError`` — raised at M3 sign-or-decline by the
  runtime when a high-stakes ``GrantMomentResult`` arrives from a
  ``decided_on_channel_id`` that does not match the principal's
  designated primary channel. NOT raised at M1 dispatch (the
  ``ChannelHandoff`` M1 layer uses structural refusal via
  ``HandoffPlan.refused_channels`` because at M1 no decision exists yet
  to check).
- ``VelocityRaiseCoolingOffError`` — raised by the runtime when a
  velocity-raise request arrives before 24h have elapsed since the
  prior velocity raise (per T-093 R2-H4); structural ratchet enforced
  at the budget-tracker integration layer.
- ``GrantMomentReplayError`` — raised by the runtime nonce-or-intent_id
  deduplication store on a second observation of an already-seen value
  (per T-008 nonce defense). The wire shape supports detection
  (``nonce`` + ``intent_id`` pinned in canonical bytes); the dedup
  store is the runtime layer.
- ``VisibleSecretMismatchError`` — raised by the channel-adapter render
  path when the secret it would render does not match the Trust-Vault
  stored secret (per T-018 dialog-spoofing defense). The error carries
  only hashes (never the phrase) per ``rules/security.md`` § "No secrets
  in logs".
- ``NoveltyFrictionRequiredError`` — raised by the runtime when a caller
  attempts to bypass the 5s read-delay or double-tap friction on a
  novel-pattern Grant Moment (per T-019 habituation defense).
- ``BackPressureQueueFullError`` — raised by the runtime grant-queue
  manager when concurrent grants exceed the configured ceiling.
- ``CrossChannelConfirmFailedError`` — raised by the runtime when a
  high-stakes cross-channel confirm leg fails to complete on the
  designated confirm channel.

The Wave-3 PR ships the ENTIRE error taxonomy as the consumer-facing
contract so downstream catch sites compile and type-check today; the
per-error raise sites live with the runtime-facade shard that composes
the structural primitives this PR ships.

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
    "GrantMomentResolutionUnauthenticatedError",
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


class GrantMomentResolutionUnauthenticatedError(GrantMomentError):
    """A cross-process resolution row failed signature verification (fail-closed).

    The store-poll rendezvous (S4r) reads a resolution another OS process wrote
    to the durable sub-store. Before that row is treated as the user's decision,
    its detached Ed25519 signature — over the ``request_id``-bound canonical
    payload, produced with the session signing key — MUST verify. A missing or
    invalid signature means the row was NOT produced by a holder of the session
    key (a forged / tampered decision, or a signature captured for a different
    request and replayed here), so the human-authority grant gate REFUSES it
    rather than executing it. Carries only ``request_id`` — never the resolution
    content. Cross-PRINCIPAL co-signature verification (a distinct answerer key)
    remains Phase-03 scope; this gate closes the unauthenticated-trust hole.
    """

    def __init__(self, *, request_id: str, message: str | None = None) -> None:
        self.request_id = request_id
        if message is None:
            message = (
                "We could not verify who answered this permission request, so "
                "we're refusing it as a safety measure."
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

    ``friction_kind`` is the structural discriminator for which friction
    branch fired — one of:

    - ``"read_delay_wallclock"`` — wall-clock elapsed below the configured
      read-delay window.
    - ``"read_delay_token_missing"`` — wall-clock window elapsed but the
      ``FRICTION_TOKEN_READ_DELAY_COMPLETE`` ack token was never recorded.
    - ``"double_tap_missing"`` — novel-class grant attempted without the
      ``FRICTION_TOKEN_DOUBLE_TAP`` ack token.

    Tests assert on this discriminator (structural) rather than substring
    matching on the user-facing prose (semantic; would be
    ``rules/probe-driven-verification.md`` MUST-1 violation).
    """

    KIND_READ_DELAY_WALLCLOCK = "read_delay_wallclock"
    KIND_READ_DELAY_TOKEN_MISSING = "read_delay_token_missing"
    KIND_DOUBLE_TAP_MISSING = "double_tap_missing"

    def __init__(
        self,
        request_id: str,
        required_friction: str,
        friction_kind: str | None = None,
        message: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.required_friction = required_friction
        self.friction_kind = friction_kind
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
