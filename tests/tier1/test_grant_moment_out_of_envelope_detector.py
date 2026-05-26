"""Tier 1 unit tests for envoy.grant_moment.out_of_envelope.

Per `rules/testing.md` § Tier 1: mocking allowed, <1s per test. Pure-
dataclass + pure-function surface — no infrastructure dependency.

Covers `specs/grant-moment.md` § "Why asking" classification invariants
for T-03-51:
- in-envelope dispatch returns in_envelope=True, why_asking=None.
- envelope_id mismatch raises ValueError.
- tool not in allowed_tools → envelope_violation.
- tool in first_time_tools → first_time.
- tool in velocity_raise_tools → velocity_raise.
- caller-supplied composition_rule_check returning a rule_id →
  composition_rule + triggered_rule.
- first-match-wins precedence: when a tool is in BOTH allowed_tools and
  first_time_tools, the first_time path wins (envelope-violation passes
  the membership check, then first_time fires).
- ToolDispatch + EnvelopeContext are frozen dataclasses (assignment raises
  FrozenInstanceError).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from envoy.grant_moment.out_of_envelope import (
    EnvelopeContext,
    OutOfEnvelopeDetectionResult,
    OutOfEnvelopeDetector,
    ToolDispatch,
)


# ---------------------------------------------------------------------------
# Fixtures: a baseline EnvelopeContext + a baseline ToolDispatch
# ---------------------------------------------------------------------------


def _make_context(
    *,
    allowed_tools: frozenset[str] = frozenset({"send_email"}),
    first_time_tools: frozenset[str] = frozenset(),
    velocity_raise_tools: frozenset[str] = frozenset(),
    composition_rules: tuple[str, ...] = (),
) -> EnvelopeContext:
    return EnvelopeContext(
        envelope_id="env-abc-123",
        envelope_version=1,
        envelope_hash="sha256:" + ("0" * 64),
        allowed_tools=allowed_tools,
        allowed_recipients=frozenset({"alice@example.com"}),
        composition_rules=composition_rules,
        first_time_tools=first_time_tools,
        velocity_raise_tools=velocity_raise_tools,
    )


def _make_dispatch(
    *,
    tool_name: str = "send_email",
    envelope_id: str = "env-abc-123",
    tool_args: dict | None = None,
) -> ToolDispatch:
    return ToolDispatch(
        tool_name=tool_name,
        tool_args_canonical=tool_args if tool_args is not None else {"to": "alice@example.com"},
        principal_genesis_id="principal-jane",
        envelope_id=envelope_id,
    )


# ---------------------------------------------------------------------------
# In-envelope (happy path)
# ---------------------------------------------------------------------------


class TestInEnvelope:
    """Tool in allowed_tools, not in any flag set → no Grant Moment needed."""

    def test_in_envelope_returns_true_and_no_why_asking(self) -> None:
        detector = OutOfEnvelopeDetector(envelope_context=_make_context())
        result = detector.classify(_make_dispatch())
        assert result == OutOfEnvelopeDetectionResult(
            in_envelope=True,
            why_asking=None,
            triggered_rule=None,
        )

    def test_in_envelope_result_is_dataclass_shape(self) -> None:
        """The verdict dataclass exposes the three documented fields."""
        detector = OutOfEnvelopeDetector(envelope_context=_make_context())
        result = detector.classify(_make_dispatch())
        assert result.in_envelope is True
        assert result.why_asking is None
        assert result.triggered_rule is None


# ---------------------------------------------------------------------------
# Envelope ID mismatch → ValueError (caller programming bug)
# ---------------------------------------------------------------------------


class TestEnvelopeIdMismatch:
    """The detector is scoped to one envelope; mismatched dispatch IS a bug."""

    def test_mismatch_raises_value_error(self) -> None:
        detector = OutOfEnvelopeDetector(envelope_context=_make_context())
        dispatch = _make_dispatch(envelope_id="env-DIFFERENT-456")
        with pytest.raises(ValueError, match="dispatch envelope mismatch"):
            detector.classify(dispatch)

    def test_mismatch_message_names_both_envelope_ids(self) -> None:
        """The error message MUST name both ids so the runtime can fix the bug."""
        detector = OutOfEnvelopeDetector(envelope_context=_make_context())
        dispatch = _make_dispatch(envelope_id="env-DIFFERENT-456")
        with pytest.raises(ValueError) as excinfo:
            detector.classify(dispatch)
        msg = str(excinfo.value)
        assert "env-abc-123" in msg
        assert "env-DIFFERENT-456" in msg


# ---------------------------------------------------------------------------
# why_asking == envelope_violation
# ---------------------------------------------------------------------------


class TestEnvelopeViolation:
    """Tool NOT in allowed_tools → envelope_violation."""

    def test_tool_not_in_allowed_tools_triggers_envelope_violation(self) -> None:
        detector = OutOfEnvelopeDetector(
            envelope_context=_make_context(allowed_tools=frozenset({"send_email"})),
        )
        dispatch = _make_dispatch(tool_name="execute_shell")
        result = detector.classify(dispatch)
        assert result.in_envelope is False
        assert result.why_asking == "envelope_violation"
        assert result.triggered_rule is None


# ---------------------------------------------------------------------------
# why_asking == first_time
# ---------------------------------------------------------------------------


class TestFirstTime:
    """Tool in allowed_tools AND first_time_tools → first_time path wins."""

    def test_tool_in_first_time_tools_triggers_first_time(self) -> None:
        detector = OutOfEnvelopeDetector(
            envelope_context=_make_context(
                allowed_tools=frozenset({"send_email", "send_telegram"}),
                first_time_tools=frozenset({"send_telegram"}),
            ),
        )
        dispatch = _make_dispatch(tool_name="send_telegram")
        result = detector.classify(dispatch)
        assert result.in_envelope is False
        assert result.why_asking == "first_time"
        assert result.triggered_rule is None


# ---------------------------------------------------------------------------
# why_asking == velocity_raise
# ---------------------------------------------------------------------------


class TestVelocityRaise:
    """Tool in allowed_tools AND velocity_raise_tools → velocity_raise."""

    def test_tool_in_velocity_raise_tools_triggers_velocity_raise(self) -> None:
        detector = OutOfEnvelopeDetector(
            envelope_context=_make_context(
                allowed_tools=frozenset({"send_email", "wire_transfer"}),
                velocity_raise_tools=frozenset({"wire_transfer"}),
            ),
        )
        dispatch = _make_dispatch(tool_name="wire_transfer")
        result = detector.classify(dispatch)
        assert result.in_envelope is False
        assert result.why_asking == "velocity_raise"
        assert result.triggered_rule is None


# ---------------------------------------------------------------------------
# why_asking == composition_rule
# ---------------------------------------------------------------------------


class TestCompositionRule:
    """Caller-supplied composition_rule_check returning a rule_id fires."""

    def test_composition_rule_check_returning_rule_id_triggers_composition_rule(self) -> None:
        def _check(dispatch: ToolDispatch) -> str | None:
            # Fire when sending to an off-whitelist recipient (the runtime's
            # business rule; the detector merely passes through the verdict).
            if dispatch.tool_args_canonical.get("to") == "evil@example.com":
                return "rule:no-external-recipients"
            return None

        detector = OutOfEnvelopeDetector(
            envelope_context=_make_context(
                allowed_tools=frozenset({"send_email"}),
                composition_rules=("rule:no-external-recipients",),
            ),
            composition_rule_check=_check,
        )
        dispatch = _make_dispatch(tool_args={"to": "evil@example.com"})
        result = detector.classify(dispatch)
        assert result.in_envelope is False
        assert result.why_asking == "composition_rule"
        assert result.triggered_rule == "rule:no-external-recipients"

    def test_composition_rule_check_returning_none_does_not_fire(self) -> None:
        """The composition_rule_check returning None falls through to in-envelope."""

        def _check(_dispatch: ToolDispatch) -> str | None:
            return None

        detector = OutOfEnvelopeDetector(
            envelope_context=_make_context(),
            composition_rule_check=_check,
        )
        result = detector.classify(_make_dispatch())
        assert result.in_envelope is True

    def test_default_composition_rule_check_is_noop(self) -> None:
        """Without an explicit check, in-envelope dispatch passes through."""
        detector = OutOfEnvelopeDetector(envelope_context=_make_context())
        result = detector.classify(_make_dispatch())
        assert result.in_envelope is True


# ---------------------------------------------------------------------------
# First-match-wins precedence
# ---------------------------------------------------------------------------


class TestFirstMatchWinsPrecedence:
    """When a tool matches multiple buckets, the documented order wins.

    Order (per module docstring): envelope_id mismatch → envelope_violation
    → first_time → velocity_raise → composition_rule → in-envelope.
    """

    def test_first_time_wins_over_velocity_raise_when_both_set(self) -> None:
        """Same tool in BOTH first_time_tools AND velocity_raise_tools → first_time."""
        detector = OutOfEnvelopeDetector(
            envelope_context=_make_context(
                allowed_tools=frozenset({"send_telegram"}),
                first_time_tools=frozenset({"send_telegram"}),
                velocity_raise_tools=frozenset({"send_telegram"}),
            ),
        )
        result = detector.classify(_make_dispatch(tool_name="send_telegram"))
        assert result.why_asking == "first_time"

    def test_first_time_wins_over_composition_rule_when_both_apply(self) -> None:
        """Tool in first_time_tools short-circuits before composition_rule_check."""
        invoked = {"value": False}

        def _check(_dispatch: ToolDispatch) -> str | None:
            invoked["value"] = True
            return "rule:should-not-fire"

        detector = OutOfEnvelopeDetector(
            envelope_context=_make_context(
                allowed_tools=frozenset({"send_telegram"}),
                first_time_tools=frozenset({"send_telegram"}),
            ),
            composition_rule_check=_check,
        )
        result = detector.classify(_make_dispatch(tool_name="send_telegram"))
        assert result.why_asking == "first_time"
        assert (
            invoked["value"] is False
        ), "composition_rule_check MUST NOT be invoked when first_time wins"

    def test_envelope_violation_wins_over_first_time_when_tool_not_allowed(self) -> None:
        """A tool absent from allowed_tools cannot reach the first_time check."""
        detector = OutOfEnvelopeDetector(
            envelope_context=_make_context(
                allowed_tools=frozenset({"send_email"}),  # send_telegram absent
                first_time_tools=frozenset({"send_telegram"}),
            ),
        )
        result = detector.classify(_make_dispatch(tool_name="send_telegram"))
        assert result.why_asking == "envelope_violation"


# ---------------------------------------------------------------------------
# Dataclass invariants (frozen)
# ---------------------------------------------------------------------------


class TestDataclassFrozenInvariants:
    """ToolDispatch + EnvelopeContext + DetectionResult are immutable."""

    def test_tool_dispatch_is_frozen(self) -> None:
        dispatch = _make_dispatch()
        with pytest.raises(FrozenInstanceError):
            dispatch.tool_name = "other_tool"  # type: ignore[misc]

    def test_envelope_context_is_frozen(self) -> None:
        ctx = _make_context()
        with pytest.raises(FrozenInstanceError):
            ctx.envelope_id = "env-other"  # type: ignore[misc]

    def test_detection_result_is_frozen(self) -> None:
        result = OutOfEnvelopeDetectionResult(in_envelope=True)
        with pytest.raises(FrozenInstanceError):
            result.in_envelope = False  # type: ignore[misc]
