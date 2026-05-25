"""envoy.boundary_conversation — the Boundary Conversation primitive.

Phase 01 implementation of `specs/boundary-conversation.md` per shard
`workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`.

T-02-40 ships the pure-Kaizen foundation: the 7-error taxonomy, the 9
per-state ``Signature`` subclasses (S1..S9), and the Plan-DAG construction
script (``BoundaryConversationScript``) that lays out the S0→S10 state
machine with its two novelty re-prompt edges (S3, S5) and two gate-back
edges (S7 visible-secret, S8 Shamir). A later shard wires this into the
runtime.

This layer is pure Kaizen + this package's own internals — it imports
NOTHING from sibling envoy packages (authorship, trust, model, etc.).
"""

from __future__ import annotations

from envoy.boundary_conversation.errors import (
    BoundaryConversationError,
    DuressBannerUnacknowledgedError,
    InvalidStateTransitionError,
    NoveltyFeedbackBlockError,
    RitualResumeStateMissingError,
    ShamirRitualIncompleteError,
    TemplateNotInLocalCacheError,
    VisibleSecretMissingError,
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
]
