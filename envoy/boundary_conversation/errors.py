"""envoy.boundary_conversation.errors — the 7-error taxonomy.

Implements the error taxonomy frozen in `specs/boundary-conversation.md`
§ "Error taxonomy". Each error carries a plain-language default message
(non-technical users read these directly per `rules/communication.md`)
plus structured attributes the conversation runtime acts on.

This module is pure Python + Kaizen-adjacent; it has ZERO dependencies on
other envoy packages.
"""

from __future__ import annotations

__all__ = [
    "BoundaryConversationError",
    "RitualResumeStateMissingError",
    "InvalidStateTransitionError",
    "TemplateNotInLocalCacheError",
    "ShamirRitualIncompleteError",
    "NoveltyFeedbackBlockError",
    "VisibleSecretMissingError",
    "DuressBannerUnacknowledgedError",
]


class BoundaryConversationError(Exception):
    """Base class for every Boundary Conversation error.

    Catching this covers the whole taxonomy without naming each member.
    """


class RitualResumeStateMissingError(BoundaryConversationError):
    """`envoy init --resume <ritual_id>` named a ritual absent from the Trust Vault.

    User action: restart from S0, or Shamir-recover the Trust Vault.
    """

    def __init__(self, ritual_id: str, message: str | None = None) -> None:
        self.ritual_id = ritual_id
        if message is None:
            message = (
                f"We could not find a saved setup to resume (id {ritual_id!r}). "
                "Start a fresh setup, or recover your Trust Vault using your "
                "backup cards."
            )
        super().__init__(message)


class InvalidStateTransitionError(BoundaryConversationError):
    """The user's answer did not satisfy the current state's validation rules.

    Carries the offending ``state`` (e.g. ``"S1"``) and a plain-language
    ``reason``. User action: re-prompt at the current state with guidance.
    """

    def __init__(self, state: str, reason: str, message: str | None = None) -> None:
        self.state = state
        self.reason = reason
        if message is None:
            message = f"That answer can't be used at {state}: {reason}"
        super().__init__(message)


class TemplateNotInLocalCacheError(BoundaryConversationError):
    """S6 offered a template that is not present in the Phase 01 local cache.

    Carries the requested ``template_id``. User action: skip the template and
    use the from-scratch path (or sync online in Phase 02).
    """

    def __init__(self, template_id: str, message: str | None = None) -> None:
        self.template_id = template_id
        if message is None:
            message = (
                f"The template {template_id!r} isn't available offline yet. "
                "You can build your boundaries from scratch instead."
            )
        super().__init__(message)


class ShamirRitualIncompleteError(BoundaryConversationError):
    """S8 Shamir card distribution was not finished by the time S9 tried to sign.

    Carries ``distributed`` and ``required`` card counts. User action: forced
    back to S8 — the envelope cannot be signed without a complete backup.
    """

    def __init__(
        self,
        distributed: int,
        required: int,
        message: str | None = None,
    ) -> None:
        self.distributed = distributed
        self.required = required
        if message is None:
            message = (
                f"Your backup isn't finished yet ({distributed} of {required} "
                "cards handed out). We need to complete it before you can sign."
            )
        super().__init__(message)


class NoveltyFeedbackBlockError(BoundaryConversationError):
    """A user-authored answer was too close to an existing template constraint.

    Triggered at S3 / S5 when Jaccard >= 0.85 or the adversarial-wording
    classifier scores >= 0.8. Carries the offending ``state``, the measured
    ``jaccard`` and ``adversarial`` scores, and their thresholds. User action:
    rephrase or re-choose a template.
    """

    JACCARD_THRESHOLD = 0.85
    ADVERSARIAL_THRESHOLD = 0.8

    def __init__(
        self,
        state: str,
        jaccard: float,
        adversarial: float,
        message: str | None = None,
    ) -> None:
        self.state = state
        self.jaccard = jaccard
        self.adversarial = adversarial
        if message is None:
            message = (
                f"Your answer at {state} is almost identical to a template rule. "
                "Please reword it in your own way, or pick the template instead."
            )
        super().__init__(message)


class VisibleSecretMissingError(BoundaryConversationError):
    """S7 visible-secret setup was not completed before the S9 sign step.

    User action: forced back to S7 to choose icon, color, and phrase.
    """

    def __init__(self, message: str | None = None) -> None:
        if message is None:
            message = (
                "You haven't set up your visible secret yet (icon, color, and "
                "phrase). We'll take you back to do that before signing."
            )
        super().__init__(message)


class DuressBannerUnacknowledgedError(BoundaryConversationError):
    """A post-duress review banner was not acknowledged before advancing past S0.

    Carries the ``duress_event_id`` of the unread event. User action:
    acknowledge the duress event and review the recommended immediate actions.
    """

    def __init__(self, duress_event_id: str, message: str | None = None) -> None:
        self.duress_event_id = duress_event_id
        if message is None:
            message = (
                "There's an unread emergency alert that needs your attention "
                "before you continue. Please review it now."
            )
        super().__init__(message)
