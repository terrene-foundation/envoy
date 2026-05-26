"""envoy.boundary_conversation.script — the S0→S10 Plan-DAG construction.

``BoundaryConversationScript`` builds the conversation as a Kaizen L3 ``Plan``:
one ``PlanNode`` per state S0..S10, a mostly-linear forward chain, plus the
two backward/gate-back edge classes the spec mandates:

* **Novelty re-prompt** (self-edges) at S3 (blocked topics) and S5 (first-task
  intent): a ``NoveltyFeedbackBlockError`` re-prompts the SAME state.
* **Gate-back** (self-edges) at S7 (visible secret) and S8 (Shamir): a
  ``VisibleSecretMissingError`` forces back to S7 and a
  ``ShamirRitualIncompleteError`` forces back to S8 — neither can reach S9
  until complete.

The DAG shape is frozen in
`workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`
§ 3.1 and `specs/boundary-conversation.md` § State machine.

Pure Kaizen — ZERO dependencies on sibling envoy packages. A later shard
(``BoundaryConversationRuntime``) composes this Plan with Trust Vault, the
Ledger writer, and the model router.
"""

from __future__ import annotations

from kaizen.l3.plan.types import (
    EdgeType,
    Plan,
    PlanEdge,
    PlanNode,
    PlanNodeState,
    PlanState,
)
from kaizen.signatures.core import Signature

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
    "BoundaryConversationScript",
    "BOUNDARY_CONVERSATION_STATES",
]

# Canonical ordered state node-ids — the S0→S10 spine. Node-ids follow the
# analysis § 3.1 naming (`S0_greet`, `S1_money`, ...). PlanState (the Kaizen
# Plan *lifecycle* enum: DRAFT / VALIDATED / ...) is a DIFFERENT concept from
# these conversation states, which live as PlanNode node-ids.
BOUNDARY_CONVERSATION_STATES: tuple[str, ...] = (
    "S0_greet",
    "S1_money",
    "S2_people",
    "S3_topics",
    "S4_hours",
    "S5_first_task",
    "S6_template_offer",
    "S7_visible_secret",
    "S8_shamir",
    "S9_review_sign",
    "S10_complete",
)

# Per-state Signature subclass binding (S1..S9 only; S0 greet and S10 complete
# take no user answer, so they have no Signature).
_STATE_SIGNATURES: dict[str, type[Signature]] = {
    "S1_money": S1MoneySignature,
    "S2_people": S2PeopleSignature,
    "S3_topics": S3TopicsSignature,
    "S4_hours": S4HoursSignature,
    "S5_first_task": S5FirstTaskSignature,
    "S6_template_offer": S6TemplateSignature,
    "S7_visible_secret": S7VisibleSecretSignature,
    "S8_shamir": S8ShamirSignature,
    "S9_review_sign": S9ReviewSignSignature,
}

# States whose user-authored answer is novelty-checked; failure re-prompts the
# same state (self-edge).
_NOVELTY_REPROMPT_STATES: tuple[str, ...] = ("S3_topics", "S5_first_task")

# States that gate-back to themselves if the in-state ritual is incomplete
# before the user can reach S9.
_GATE_BACK_STATES: tuple[str, ...] = ("S7_visible_secret", "S8_shamir")


class BoundaryConversationScript:
    """Constructs the Boundary Conversation Plan-DAG and resolves Signatures.

    Stateless and dependency-free: ``build_plan()`` returns a fresh ``Plan``
    each call and ``signature_for_state()`` is a pure lookup.
    """

    PLAN_ID = "envoy_boundary_conversation"
    PLAN_NAME = "Envoy Boundary Conversation"

    def build_plan(self) -> Plan:
        """Build the S0→S10 conversation Plan.

        Returns a ``Plan`` in ``PlanState.DRAFT`` whose nodes cover every
        state S0..S10, with the forward chain plus the novelty re-prompt
        (S3, S5) and gate-back (S7, S8) self-edges.
        """
        nodes: dict[str, PlanNode] = {}
        for state in BOUNDARY_CONVERSATION_STATES:
            nodes[state] = PlanNode(
                node_id=state,
                agent_spec_id=state,
                input_mapping={},
                state=PlanNodeState.PENDING,
                instance_id=None,
                optional=False,
                retry_count=0,
                output=None,
                error=None,
            )

        edges: list[PlanEdge] = []

        # Forward chain S0 → S1 → ... → S10.
        for from_state, to_state in zip(
            BOUNDARY_CONVERSATION_STATES, BOUNDARY_CONVERSATION_STATES[1:], strict=False
        ):
            edges.append(
                PlanEdge(
                    from_node=from_state,
                    to_node=to_state,
                    edge_type=EdgeType.COMPLETION_DEPENDENCY,
                )
            )

        # Novelty re-prompt self-edges (S3, S5): NoveltyFeedbackBlockError
        # re-prompts the same state.
        for state in _NOVELTY_REPROMPT_STATES:
            edges.append(
                PlanEdge(
                    from_node=state,
                    to_node=state,
                    edge_type=EdgeType.COMPLETION_DEPENDENCY,
                )
            )

        # Gate-back self-edges (S7, S8): VisibleSecretMissingError forces back
        # to S7; ShamirRitualIncompleteError forces back to S8 before S9.
        for state in _GATE_BACK_STATES:
            edges.append(
                PlanEdge(
                    from_node=state,
                    to_node=state,
                    edge_type=EdgeType.COMPLETION_DEPENDENCY,
                )
            )

        return Plan(
            plan_id=self.PLAN_ID,
            name=self.PLAN_NAME,
            envelope={},
            gradient={},
            nodes=nodes,
            edges=edges,
            state=PlanState.DRAFT,
        )

    def signature_for_state(self, state: str) -> Signature:
        """Return an instance of the Signature subclass bound to ``state``.

        ``state`` is a conversation-state node-id (e.g. ``"S5_first_task"``).
        Raises ``KeyError`` for S0 / S10 (no Signature) or an unknown state.
        """
        return _STATE_SIGNATURES[state]()

    def signature_class_for_state(self, state: str) -> type[Signature]:
        """Return the Signature *class* bound to ``state`` (no instantiation)."""
        return _STATE_SIGNATURES[state]
