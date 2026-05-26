"""envoy.grant_moment — the per-action consent state machine.

Phase 01 implementation of `specs/grant-moment.md` per
`workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`.

T-03-50 shipped the foundation: the M0→M4 state machine, the JCS+NFC-canonicalized
``GrantMomentRequest`` + ``GrantMomentResult`` wire shapes, the
``SignedConsentBuilder`` that signs them via the delegation_key, the three
``ResolutionShape`` classes that wrap the spec's four ``decision`` values, and
the 10-error taxonomy from ``specs/grant-moment.md`` § Error taxonomy.

T-03-51 layered on the dispatch surfaces: ``OutOfEnvelopeDetector`` (the
in-envelope vs out-of-envelope classifier producing the spec's `why_asking`
discriminator) and ``ChannelHandoff`` (the primary-channel-binding fan-out
to channel adapters).

T-03-52 layered on the cross-grant orchestration: ``CascadeRevocationOrchestrator``
(wraps upstream ``trust_cascade_revoke`` + verifies completeness for EC-8) and
``PlanSuspensionBridge`` (typed-event channel between Boundary Conversation
and Grant Moment).

T-03-53 layered on the friction classifier: ``NoveltyClassifier`` (three-class
``novel | familiar_repeat | high_stakes`` per spec § Novelty-aware friction).

Per `rules/orphan-detection.md` Rule 6, every module-scope import in this file
appears in ``__all__``.
"""

from __future__ import annotations

from envoy.grant_moment.cascade_orchestrator import (
    CascadeIncompleteError,
    CascadeResult,
    CascadeRevocationOrchestrator,
)
from envoy.grant_moment.channel_handoff import (
    ChannelAdapterProtocol,
    ChannelHandoff,
    HandoffPlan,
)
from envoy.grant_moment.errors import (
    BackPressureQueueFullError,
    CrossChannelConfirmFailedError,
    DualSignatureRequiredError,
    GrantMomentError,
    GrantMomentExpiredError,
    GrantMomentReplayError,
    GrantMomentTimeoutError,
    InvalidGrantMomentTransitionError,
    NotPrimaryChannelError,
    NoveltyFrictionRequiredError,
    VelocityRaiseCoolingOffError,
    VisibleSecretMismatchError,
)
from envoy.grant_moment.novelty import (
    NoveltyClass,
    NoveltyClassifier,
    NoveltySignals,
)
from envoy.grant_moment.out_of_envelope import (
    EnvelopeContext,
    OutOfEnvelopeDetectionResult,
    OutOfEnvelopeDetector,
    ToolDispatch,
)
from envoy.grant_moment.plan_suspension_bridge import (
    PlanSuspensionBridge,
    PlanSuspensionEvent,
    PlanSuspensionEventKind,
    Subscriber,
)
from envoy.grant_moment.resolution import (
    ApproveResolution,
    ApproveWithModificationResolution,
    DeclineResolution,
    ResolutionShape,
)
from envoy.grant_moment.signed_consent import (
    ConsequencePreview,
    GrantMomentRequest,
    GrantMomentResult,
    SignedConsentBuilder,
)
from envoy.grant_moment.runtime import (
    FRICTION_TOKEN_CROSS_CHANNEL_CONFIRM,
    FRICTION_TOKEN_DOUBLE_TAP,
    FRICTION_TOKEN_READ_DELAY_COMPLETE,
    EnvoyGrantMomentRuntime,
    GrantMomentOutcome,
)  # noqa: F401  — runtime + friction tokens land via __all__
from envoy.grant_moment.state_machine import (
    GRANT_MOMENT_TRANSITIONS,
    GrantMomentEvent,
    GrantMomentState,
    next_state,
)

__all__ = [
    # Errors (specs/grant-moment.md § Error taxonomy + state-machine plumbing)
    "BackPressureQueueFullError",
    "CrossChannelConfirmFailedError",
    "DualSignatureRequiredError",
    "GrantMomentError",
    "GrantMomentExpiredError",
    "GrantMomentReplayError",
    "GrantMomentTimeoutError",
    "InvalidGrantMomentTransitionError",
    "NotPrimaryChannelError",
    "NoveltyFrictionRequiredError",
    "VelocityRaiseCoolingOffError",
    "VisibleSecretMismatchError",
    # Resolution shapes (Approve / Decline / ApproveWithModification → 4 spec decisions)
    "ApproveResolution",
    "ApproveWithModificationResolution",
    "DeclineResolution",
    "ResolutionShape",
    # Signed-consent wire shapes (JCS+NFC canonicalized; delegation_key signed)
    "ConsequencePreview",
    "GrantMomentRequest",
    "GrantMomentResult",
    "SignedConsentBuilder",
    # State machine (T-03-50)
    "GRANT_MOMENT_TRANSITIONS",
    "GrantMomentEvent",
    "GrantMomentState",
    "next_state",
    # Dispatch surfaces (T-03-51)
    "ChannelAdapterProtocol",
    "ChannelHandoff",
    "EnvelopeContext",
    "HandoffPlan",
    "OutOfEnvelopeDetectionResult",
    "OutOfEnvelopeDetector",
    "ToolDispatch",
    # Cross-grant orchestration (T-03-52)
    "CascadeIncompleteError",
    "CascadeResult",
    "CascadeRevocationOrchestrator",
    "PlanSuspensionBridge",
    "PlanSuspensionEvent",
    "PlanSuspensionEventKind",
    "Subscriber",
    # Friction classifier (T-03-53)
    "NoveltyClass",
    "NoveltyClassifier",
    "NoveltySignals",
    # Runtime facade (Wave-4 — composes M0→M4)
    "EnvoyGrantMomentRuntime",
    "GrantMomentOutcome",
    "FRICTION_TOKEN_READ_DELAY_COMPLETE",
    "FRICTION_TOKEN_DOUBLE_TAP",
    "FRICTION_TOKEN_CROSS_CHANNEL_CONFIRM",
]
