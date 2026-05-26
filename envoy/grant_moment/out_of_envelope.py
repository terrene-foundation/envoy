"""envoy.grant_moment.out_of_envelope — OutOfEnvelopeDetector.

Implements the envelope-violation classifier per
`workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
§ 3 step 4 ("interceptor wrapping every Kaizen tool-call dispatch") and
`specs/grant-moment.md` § "Why asking" — the ``why_asking`` discriminator
takes one of six closed-vocabulary values:

    envelope_violation | composition_rule | first_time |
    velocity_raise    | cross_principal  | data_access_classifier

The detector classifies four of the six values structurally
(``envelope_violation``, ``first_time``, ``velocity_raise``,
``composition_rule``); every classification rule is a set-membership
or callable check against the caller-supplied ``EnvelopeContext``.
``cross_principal`` and ``data_access_classifier`` are NOT implemented
in this module — they need additional context the dispatch surface
(Daily Digest data-access surface, cross-principal request manifest)
provides; the classifier here returns ``in_envelope=True`` for those
patterns and the dispatch surface that owns the additional context
raises the appropriate Grant Moment from its own observation site.

Per `rules/agent-reasoning.md`: this module is structural plumbing
(envelope set-membership + caller-supplied composition_rule_check).
ZERO LLM calls, ZERO keyword routing, ZERO if/elif on dispatch content
beyond declared-membership tests. The caller's
``composition_rule_check`` may itself be LLM-driven; the detector does
not care.

This module is pure Python; ZERO dependencies on other envoy packages.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "EnvelopeContext",
    "OutOfEnvelopeDetectionResult",
    "OutOfEnvelopeDetector",
    "ToolDispatch",
]


# Closed vocabulary per spec § "Why asking". The detector wires the four
# values listed here; ``cross_principal`` and ``data_access_classifier``
# are emitted from the dispatch surfaces that hold the additional
# context they need (cross-principal request manifest; data-access
# classifier output) — NOT from this module.
_WHY_ASKING_ENVELOPE_VIOLATION = "envelope_violation"
_WHY_ASKING_FIRST_TIME = "first_time"
_WHY_ASKING_VELOCITY_RAISE = "velocity_raise"
_WHY_ASKING_COMPOSITION_RULE = "composition_rule"


@dataclass(frozen=True, slots=True)
class ToolDispatch:
    """The runtime's intent-to-call shape the detector inspects.

    ``tool_args_canonical`` is JCS+NFC-canonicalized at the runtime layer
    before reaching the detector (see ``envoy.envelope.canonical_bytes``);
    the detector itself does NOT canonicalize, it only inspects.
    """

    tool_name: str
    tool_args_canonical: dict[str, Any]
    principal_genesis_id: str
    envelope_id: str


@dataclass(frozen=True, slots=True)
class EnvelopeContext:
    """The active envelope's structural surface the detector classifies against.

    Per spec § Schema (``GrantMomentRequest.envelope_id``,
    ``envelope_version``, ``envelope_hash``) the detector pins all three
    so post-incident audits can replay the classification against the
    exact envelope state at dispatch time.

    The three ``frozenset`` fields are the envelope's explicit whitelists.
    ``composition_rules`` is the named rule-id corpus (rule firing logic
    is caller-supplied via ``composition_rule_check`` in the detector
    constructor) per
    `workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
    § 3 step 4.
    """

    envelope_id: str
    envelope_version: int
    envelope_hash: str
    allowed_tools: frozenset[str]
    allowed_recipients: frozenset[str] = field(default_factory=frozenset)
    composition_rules: tuple[str, ...] = ()
    first_time_tools: frozenset[str] = field(default_factory=frozenset)
    velocity_raise_tools: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class OutOfEnvelopeDetectionResult:
    """The detector's verdict.

    ``in_envelope=True`` → ``why_asking`` is None and ``triggered_rule`` is
    None; the runtime proceeds without a Grant Moment.

    ``in_envelope=False`` → ``why_asking`` carries one of the four
    Phase-01 closed-vocabulary values; ``triggered_rule`` is the rule_id
    when ``why_asking == "composition_rule"``, else None.
    """

    in_envelope: bool
    why_asking: str | None = None
    triggered_rule: str | None = None


# Type alias for caller-supplied composition-rule firing logic.
# Returns the rule_id (a string from ``EnvelopeContext.composition_rules``)
# when a rule fires; returns None when no rule applies. The detector
# does NOT inspect the rule_id beyond passing it through to the verdict
# — runtime + ledger are the rule_id-aware consumers.
_CompositionRuleCheck = Callable[[ToolDispatch], str | None]


def _default_composition_rule_check(_dispatch: ToolDispatch) -> str | None:
    """Default: no composition rules fire.

    Callers who want composition-rule classification supply their own
    callable to ``OutOfEnvelopeDetector(composition_rule_check=...)``.
    The default is a no-op (returns None) so the four structural rules
    (envelope-violation / first-time / velocity-raise / in-envelope)
    cover every dispatch unless the caller opts in.
    """
    return None


class OutOfEnvelopeDetector:
    """Classifies a proposed ``ToolDispatch`` against an ``EnvelopeContext``.

    Construct one detector per active envelope. The classification
    order is FIRST-MATCH-WINS — when a tool is in BOTH
    ``allowed_tools`` (passing the envelope-violation check) AND
    ``first_time_tools``, the ``first_time`` path wins because the
    envelope-violation check runs first and exits early without flagging.

    First-match-wins order (documented invariant for callers):

    1. ``dispatch.envelope_id != context.envelope_id`` → ValueError
       (the runtime MUST scope the dispatch to the active envelope before
       calling the detector; mismatch is a programming bug, not a user
       decision).
    2. tool NOT in ``allowed_tools`` → ``envelope_violation``.
    3. tool in ``first_time_tools`` → ``first_time``.
    4. tool in ``velocity_raise_tools`` → ``velocity_raise``.
    5. ``composition_rule_check(dispatch)`` returns a non-None rule_id
       → ``composition_rule`` with ``triggered_rule = rule_id``.
    6. otherwise → in-envelope (no Grant Moment needed).
    """

    def __init__(
        self,
        *,
        envelope_context: EnvelopeContext,
        composition_rule_check: _CompositionRuleCheck | None = None,
    ) -> None:
        self._envelope_context = envelope_context
        self._composition_rule_check = (
            composition_rule_check
            if composition_rule_check is not None
            else _default_composition_rule_check
        )

    def classify(self, dispatch: ToolDispatch) -> OutOfEnvelopeDetectionResult:
        """Apply the first-match-wins rules; return the verdict.

        Raises ``ValueError`` ONLY when the dispatch's envelope_id does
        not match the active envelope — per `rules/communication.md`
        plain-language error message names what the caller should do.
        """
        context = self._envelope_context

        if dispatch.envelope_id != context.envelope_id:
            raise ValueError(
                "dispatch envelope mismatch: the proposed tool call points "
                f"at envelope {dispatch.envelope_id!r} but the detector is "
                f"scoped to envelope {context.envelope_id!r}. The runtime "
                "must scope each dispatch to the active envelope before "
                "calling classify()."
            )

        # Rule 2: envelope_violation — tool not in the whitelist.
        if dispatch.tool_name not in context.allowed_tools:
            return OutOfEnvelopeDetectionResult(
                in_envelope=False,
                why_asking=_WHY_ASKING_ENVELOPE_VIOLATION,
            )

        # Rule 3: first_time — novel tool requires user re-grant.
        if dispatch.tool_name in context.first_time_tools:
            return OutOfEnvelopeDetectionResult(
                in_envelope=False,
                why_asking=_WHY_ASKING_FIRST_TIME,
            )

        # Rule 4: velocity_raise — tool whose call would raise a limit.
        if dispatch.tool_name in context.velocity_raise_tools:
            return OutOfEnvelopeDetectionResult(
                in_envelope=False,
                why_asking=_WHY_ASKING_VELOCITY_RAISE,
            )

        # Rule 5: composition_rule — caller-supplied callable fires.
        rule_id = self._composition_rule_check(dispatch)
        if rule_id is not None:
            return OutOfEnvelopeDetectionResult(
                in_envelope=False,
                why_asking=_WHY_ASKING_COMPOSITION_RULE,
                triggered_rule=rule_id,
            )

        # Rule 6: in-envelope — no Grant Moment needed.
        return OutOfEnvelopeDetectionResult(in_envelope=True)
