"""Tier 2 tests for the Boundary Conversation Plan-DAG script (T-02-40).

No mocking (Tier 2 discipline): exercises the real Kaizen ``Plan`` /
``PlanNode`` / ``PlanEdge`` / ``Signature`` primitives directly.

Verifies the S0→S10 DAG topology frozen in `specs/boundary-conversation.md`
§ State machine and the analysis § 3.1 — the forward chain plus the two
backward edge classes (novelty re-prompt at S3/S5; gate-back at S7/S8) — and
the per-state Signature bindings + their declared input/output fields.
"""

from __future__ import annotations

import pytest

from envoy.boundary_conversation import (
    BOUNDARY_CONVERSATION_STATES,
    BoundaryConversationScript,
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

# Expected forward spine S0 → S1 → ... → S10.
_FORWARD_CHAIN = [
    ("S0_greet", "S1_money"),
    ("S1_money", "S2_people"),
    ("S2_people", "S3_topics"),
    ("S3_topics", "S4_hours"),
    ("S4_hours", "S5_first_task"),
    ("S5_first_task", "S6_template_offer"),
    ("S6_template_offer", "S7_visible_secret"),
    ("S7_visible_secret", "S8_shamir"),
    ("S8_shamir", "S9_review_sign"),
    ("S9_review_sign", "S10_complete"),
]

# Self-edges: novelty re-prompt (S3, S5) + gate-back (S7, S8).
_BACKWARD_SELF_EDGES = {
    ("S3_topics", "S3_topics"),
    ("S5_first_task", "S5_first_task"),
    ("S7_visible_secret", "S7_visible_secret"),
    ("S8_shamir", "S8_shamir"),
}

# Per-state Signature class + (inputs, outputs) declared field names.
_STATE_SIGNATURE_SPEC = {
    "S1_money": (S1MoneySignature, ["reply"], ["monthly_ceiling_microdollars"]),
    "S2_people": (S2PeopleSignature, ["reply"], ["blocked_contacts"]),
    "S3_topics": (S3TopicsSignature, ["reply"], ["blocked_topic_rules"]),
    "S4_hours": (S4HoursSignature, ["reply"], ["operating_hours"]),
    "S5_first_task": (S5FirstTaskSignature, ["reply"], ["first_task_intent"]),
    "S6_template_offer": (
        S6TemplateSignature,
        ["reply"],
        ["use_template", "template_id"],
    ),
    "S7_visible_secret": (
        S7VisibleSecretSignature,
        ["reply"],
        ["icon", "color", "phrase"],
    ),
    "S8_shamir": (
        S8ShamirSignature,
        ["reply"],
        ["threshold", "total_shards", "distribution_mode"],
    ),
    "S9_review_sign": (
        S9ReviewSignSignature,
        ["reply"],
        ["plain_language_summary", "signed"],
    ),
}

# Expected output field name -> declared Python type, asserted structurally
# against the real Signature metaclass field registry.
_OUTPUT_FIELD_TYPES = {
    "monthly_ceiling_microdollars": int,
    "blocked_contacts": list,
    "blocked_topic_rules": list,
    "operating_hours": dict,
    "first_task_intent": dict,
    "use_template": bool,
    "template_id": str,
    "icon": str,
    "color": str,
    "phrase": str,
    "threshold": int,
    "total_shards": int,
    "distribution_mode": str,
    "plain_language_summary": str,
    "signed": bool,
}


@pytest.fixture()
def script() -> BoundaryConversationScript:
    return BoundaryConversationScript()


# --------------------------------------------------------------------------- #
# build_plan() — node coverage + DAG topology                                 #
# --------------------------------------------------------------------------- #


def test_build_plan_covers_all_states_S0_through_S10(script):
    plan = script.build_plan()
    assert set(plan.nodes.keys()) == set(BOUNDARY_CONVERSATION_STATES)
    # Exactly the 11 states S0..S10.
    assert len(plan.nodes) == 11
    for state in BOUNDARY_CONVERSATION_STATES:
        assert plan.nodes[state].node_id == state


def test_build_plan_forward_chain_present(script):
    plan = script.build_plan()
    edge_pairs = {(e.from_node, e.to_node) for e in plan.edges}
    for pair in _FORWARD_CHAIN:
        assert pair in edge_pairs, f"missing forward edge {pair}"


def test_build_plan_novelty_reprompt_self_edges_present(script):
    """S3 and S5 each carry a re-prompt self-edge (NoveltyFeedbackBlockError)."""
    plan = script.build_plan()
    edge_pairs = {(e.from_node, e.to_node) for e in plan.edges}
    assert ("S3_topics", "S3_topics") in edge_pairs
    assert ("S5_first_task", "S5_first_task") in edge_pairs


def test_build_plan_gate_back_self_edges_present(script):
    """S7 (visible secret) and S8 (Shamir) carry gate-back self-edges."""
    plan = script.build_plan()
    edge_pairs = {(e.from_node, e.to_node) for e in plan.edges}
    assert ("S7_visible_secret", "S7_visible_secret") in edge_pairs
    assert ("S8_shamir", "S8_shamir") in edge_pairs


def test_build_plan_exact_edge_set(script):
    """The DAG is mostly-linear: 10 forward edges + 4 backward self-edges."""
    plan = script.build_plan()
    edge_pairs = {(e.from_node, e.to_node) for e in plan.edges}
    expected = set(_FORWARD_CHAIN) | _BACKWARD_SELF_EDGES
    assert edge_pairs == expected
    # No stray edges (every edge endpoint is a real node).
    for e in plan.edges:
        assert e.from_node in plan.nodes
        assert e.to_node in plan.nodes


def test_build_plan_returns_fresh_plan_each_call(script):
    """Stateless: two calls produce independent Plan objects."""
    a = script.build_plan()
    b = script.build_plan()
    assert a is not b
    assert set(a.nodes.keys()) == set(b.nodes.keys())


# --------------------------------------------------------------------------- #
# signature_for_state() — correct subclass + type per S1..S9                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("state", sorted(_STATE_SIGNATURE_SPEC))
def test_signature_for_state_returns_correct_subclass(script, state):
    expected_cls = _STATE_SIGNATURE_SPEC[state][0]
    sig = script.signature_for_state(state)
    assert isinstance(sig, expected_cls)
    assert type(sig) is expected_cls


@pytest.mark.parametrize("state", sorted(_STATE_SIGNATURE_SPEC))
def test_signature_class_for_state_matches(script, state):
    expected_cls = _STATE_SIGNATURE_SPEC[state][0]
    assert script.signature_class_for_state(state) is expected_cls


def test_signature_for_state_rejects_non_answer_states(script):
    """S0 (greet) and S10 (complete) take no user answer -> no Signature."""
    with pytest.raises(KeyError):
        script.signature_for_state("S0_greet")
    with pytest.raises(KeyError):
        script.signature_for_state("S10_complete")


# --------------------------------------------------------------------------- #
# Signature field declarations — structural, against the real Signature API   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("state", sorted(_STATE_SIGNATURE_SPEC))
def test_signature_declares_expected_input_output_fields(state):
    cls, expected_inputs, expected_outputs = _STATE_SIGNATURE_SPEC[state]
    sig = cls()
    assert sig.inputs == expected_inputs
    assert sig.outputs == expected_outputs


@pytest.mark.parametrize("state", sorted(_STATE_SIGNATURE_SPEC))
def test_signature_output_field_types_match_spec(state):
    cls, _expected_inputs, expected_outputs = _STATE_SIGNATURE_SPEC[state]
    # Kaizen's SignatureMeta records the annotated type in _signature_outputs.
    out_fields = cls._signature_outputs
    for field_name in expected_outputs:
        assert field_name in out_fields, f"{cls.__name__} missing output {field_name}"
        assert out_fields[field_name]["type"] is _OUTPUT_FIELD_TYPES[field_name], (
            f"{cls.__name__}.{field_name} declared type "
            f"{out_fields[field_name]['type']!r}, expected "
            f"{_OUTPUT_FIELD_TYPES[field_name]!r}"
        )


def test_s1_money_ceiling_is_int_microdollars():
    """S1's ceiling is integer microdollars (no float in a financial limit)."""
    sig = S1MoneySignature()
    assert sig.outputs == ["monthly_ceiling_microdollars"]
    assert sig._signature_outputs["monthly_ceiling_microdollars"]["type"] is int


def test_all_nine_signatures_instantiate():
    """Every S1..S9 Signature constructs cleanly through the real Kaizen API."""
    for cls, _i, _o in _STATE_SIGNATURE_SPEC.values():
        instance = cls()
        assert instance.inputs  # at least the user reply
        assert instance.outputs  # at least one structured output
