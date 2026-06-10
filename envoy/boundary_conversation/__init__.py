"""envoy.boundary_conversation — the Boundary Conversation primitive.

Phase 01 implementation of `specs/boundary-conversation.md` per shard
`workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`.

T-02-40 shipped the pure-Kaizen foundation (the 7-error taxonomy, the 9
per-state ``Signature`` subclasses S1..S9, the Plan-DAG construction script
``BoundaryConversationScript``). T-02-41/42 wires that foundation into the
running primitive: the ``EnvelopeConfigInputAssembler`` (per-state extraction →
EnvelopeConfigInput), the ``RitualResumeCoordinator`` (Trust-Vault per-state
persistence), the ``BET12TelemetryHook`` (EC-1 telemetry), and the
``BoundaryConversationRuntime`` facade that orchestrates the S0→S10 flow.

The foundation layer (errors, signatures, script) imports NOTHING from sibling
envoy packages; the runtime layer composes them (trust, ledger, envelope,
shamir, authorship, model) via explicit dependency injection.
"""

from __future__ import annotations

from envoy.boundary_conversation.bet12_telemetry import BET12TelemetryHook
from envoy.boundary_conversation.envelope_assembler import EnvelopeConfigInputAssembler
from envoy.boundary_conversation.errors import (
    BoundaryConversationError,
    DuressBannerUnacknowledgedError,
    InvalidStateTransitionError,
    NoveltyFeedbackBlockError,
    RitualResumeStateMissingError,
    ShamirRitualIncompleteError,
    TemplateNotInLocalCacheError,
    VaultAlreadyInitializedError,
    VisibleSecretMissingError,
)
from envoy.boundary_conversation.init_runtime import (
    BoundaryConversationInitRuntime,
    InitResult,
    build_genesis_session_state,
    build_trust_anchor,
    genesis_session_key,
)
from envoy.boundary_conversation.resume import ResumedRitual, RitualResumeCoordinator
from envoy.boundary_conversation.runtime import (
    BoundaryConversationRuntime,
    ConversationOutcome,
)
from envoy.boundary_conversation.script import (
    BOUNDARY_CONVERSATION_STATES,
    BoundaryConversationScript,
)
from envoy.boundary_conversation.signatures import (
    S1MoneySignature,
    S2PeopleSignature,
    S3TopicsSignature,
    S4HoursSignature,
    S5FirstTaskSignature,
    S6TemplateSignature,
    S7VisibleSecretSignature,
    S8ShamirSignature,
    S9ReviewSignSignature,
)

__all__ = [
    # Runtime
    "BoundaryConversationRuntime",
    "ConversationOutcome",
    # Init bootstrap (envoy init — S4i)
    "BoundaryConversationInitRuntime",
    "InitResult",
    "genesis_session_key",
    "build_genesis_session_state",
    "build_trust_anchor",
    # Assembler
    "EnvelopeConfigInputAssembler",
    # Resume
    "RitualResumeCoordinator",
    "ResumedRitual",
    # Telemetry
    "BET12TelemetryHook",
    # Script
    "BoundaryConversationScript",
    "BOUNDARY_CONVERSATION_STATES",
    # Signatures (S1..S9)
    "S1MoneySignature",
    "S2PeopleSignature",
    "S3TopicsSignature",
    "S4HoursSignature",
    "S5FirstTaskSignature",
    "S6TemplateSignature",
    "S7VisibleSecretSignature",
    "S8ShamirSignature",
    "S9ReviewSignSignature",
    # Errors
    "BoundaryConversationError",
    "RitualResumeStateMissingError",
    "InvalidStateTransitionError",
    "TemplateNotInLocalCacheError",
    "ShamirRitualIncompleteError",
    "NoveltyFeedbackBlockError",
    "VisibleSecretMissingError",
    "DuressBannerUnacknowledgedError",
    "VaultAlreadyInitializedError",
]
