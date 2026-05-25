"""envoy.boundary_conversation.envelope_assembler — per-state extraction → EnvelopeConfigInput.

``EnvelopeConfigInputAssembler`` accumulates the structured extraction produced
at each envelope-dimension conversation state (S1..S5) and, at S9 sign-step,
assembles a single ``EnvelopeConfigInput`` for the Envelope Compiler. S6/S7/S8/S9
are NOT recorded — they feed the template cache / Trust Vault / Shamir backup,
not the envelope dimensions.

Per `workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`
§ 3.2 + § 4 + § 5.1, the assembler MUST:

* emit each dimension's ``authored_constraints[]`` sorted by ``constraint_id``
  ascending (the JCS canonical order the compiler expects — answers Key Design
  Question 6 + the shard-9 Authorship-Score cross-invariant);
* default ``tool_output_budget_bytes``, ``semantic_checks``, and
  ``cross_domain_rules_authored=[]`` per the envelope-model minima (the
  conversation does NOT prompt the user for these directly per § 34).

The accumulation is deterministic: the same fed extractions always assemble to
the same ``EnvelopeConfigInput``, so the compiled ``canonical_bytes`` are
byte-stable across runs.

Pure-Python: imports only the envelope types + structured logging. ZERO LLM,
ZERO network.
"""

from __future__ import annotations

import logging
from typing import Any

from envoy.envelope.types import (
    AuthoredConstraint,
    CommunicationDimension,
    DataAccessDimension,
    EnvelopeConfigInput,
    FinancialDimension,
    OperationalDimension,
    TemporalDimension,
)

__all__ = ["EnvelopeConfigInputAssembler"]

logger = logging.getLogger(__name__)

# Conversation-state node-ids whose extractions the assembler consumes — the
# FIVE envelope-dimension states ONLY. S0/S10 carry no user answer; S6 (template
# offer) feeds the runtime template cache; S7 (visible secret) is stored via
# `trust_store.set_visible_secret` — recording it here serialized the secret
# phrase as plaintext into assembler_json (R1-HIGH-1b); S8 (Shamir) configures
# backup, not the envelope; S9 (review/sign) carries no authored dimension.
# None of S6/S7/S8/S9 contribute an authored_constraint dimension, so the
# assembler must NOT record them. The dimensions are authored from S1 (money),
# S2 (people), S3 (topics), S4 (hours), S5 (first task).
_FED_STATES: frozenset[str] = frozenset(
    {
        "S1_money",
        "S2_people",
        "S3_topics",
        "S4_hours",
        "S5_first_task",
    }
)

# Envelope-model minima (per § 34) the conversation does NOT prompt for but MUST
# emit populated. The EnvelopeConfigInput dataclass already defaults
# tool_output_budget_bytes=65536, semantic_checks=SemanticChecks(),
# cross_domain_rules_authored=[]; the assembler keeps that default explicitly so
# a future EnvelopeConfigInput default change does not silently alter the
# conversation's output contract.
_DEFAULT_TOOL_OUTPUT_BUDGET_BYTES = 65536


class EnvelopeConfigInputAssembler:
    """Accumulate per-state extractions; assemble a canonical EnvelopeConfigInput.

    Stateful within one conversation: ``feed(node_id, extraction)`` records each
    state's structured output; ``assemble()`` builds the EnvelopeConfigInput from
    the accumulated extractions with constraints sorted JCS-canonically.

    Serializable for resume: ``to_dict()`` / ``from_dict()`` round-trip the
    accumulated extractions so the resume coordinator can persist + rehydrate the
    in-flight assembler state alongside the Plan.
    """

    def __init__(self) -> None:
        # node_id -> extraction dict (the Signature's structured output).
        self._extractions: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Accumulation
    # ------------------------------------------------------------------

    def feed(self, node_id: str, extraction: dict[str, Any]) -> None:
        """Record the structured extraction produced at ``node_id``.

        Only the five envelope-dimension states (S1..S5) are recorded; every
        other state (S0/S6/S7/S8/S9/S10) is ignored. S7's visible-secret phrase
        is stored via `trust_store.set_visible_secret`, NOT here — recording it
        here would serialize the secret as plaintext into assembler_json. A raw
        ``reply`` key is defensively stripped before storage (the runtime no
        longer feeds it, but the assembler owns the storage contract).

        Re-feeding the same ``node_id`` overwrites the prior extraction (a
        novelty re-prompt at S3/S5 replaces the rejected answer). Unknown /
        no-answer states are ignored rather than raising — the runtime calls
        ``feed`` uniformly per transition and the assembler owns the
        which-states-count decision.
        """
        if not isinstance(extraction, dict):
            raise TypeError(
                f"extraction for {node_id!r} must be a dict (got {type(extraction).__name__})"
            )
        if node_id not in _FED_STATES:
            logger.debug(
                "envelope_assembler.feed.ignored_state",
                extra={"node_id": node_id},
            )
            return
        # Defensively drop a verbatim ``reply`` key — it is not an authored
        # dimension and must never be serialized into assembler_json.
        self._extractions[node_id] = {k: v for k, v in extraction.items() if k != "reply"}
        logger.debug(
            "envelope_assembler.feed.recorded",
            extra={"node_id": node_id, "field_count": len(extraction)},
        )

    @property
    def fed_states(self) -> frozenset[str]:
        """The set of states whose extractions have been recorded so far."""
        return frozenset(self._extractions)

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def assemble(self) -> EnvelopeConfigInput:
        """Build the EnvelopeConfigInput from accumulated extractions.

        Each dimension's ``authored_constraints[]`` is emitted sorted by
        ``constraint_id`` ascending (JCS-canonical). Dimensions for which no
        extraction was fed fall to their dataclass defaults. Top-level minima
        (tool_output_budget_bytes, semantic_checks, cross_domain_rules_authored)
        are emitted per § 34.
        """
        financial = self._build_financial()
        operational = self._build_operational()
        temporal = self._build_temporal()
        data_access = self._build_data_access()
        communication = self._build_communication()

        envelope_input = EnvelopeConfigInput(
            financial=financial,
            operational=operational,
            temporal=temporal,
            data_access=data_access,
            communication=communication,
            # § 34 minima — emitted populated even though the conversation does
            # not prompt for them. cross_domain_rules_authored=[] is the
            # first-time-author Phase-01 path; tool_output_budget_bytes +
            # semantic_checks default per the envelope-model minimum.
            cross_domain_rules_authored=[],
            tool_output_budget_bytes=_DEFAULT_TOOL_OUTPUT_BUDGET_BYTES,
        )
        logger.info(
            "envelope_assembler.assembled",
            extra={
                "fed_states": sorted(self._extractions),
                "financial_constraints": len(financial.authored_constraints),
                "operational_constraints": len(operational.authored_constraints),
                "data_access_constraints": len(data_access.authored_constraints),
                "communication_constraints": len(communication.authored_constraints),
                "temporal_constraints": len(temporal.authored_constraints),
            },
        )
        return envelope_input

    # ------------------------------------------------------------------
    # Per-dimension builders
    # ------------------------------------------------------------------

    def _build_financial(self) -> FinancialDimension:
        extraction = self._extractions.get("S1_money", {})
        ceiling = extraction.get("monthly_ceiling_microdollars", 0)
        # Defensive coercion: the Signature declares int, but a resume round-trip
        # through JSON may surface a numeric-string. int() raises loudly on a
        # non-numeric value rather than silently dropping the ceiling.
        try:
            ceiling_int = int(ceiling)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"S1 monthly_ceiling_microdollars must be an integer (got {ceiling!r})"
            ) from exc
        constraints = self._authored_constraints_for("S1_money")
        return FinancialDimension(
            per_month_ceiling_microdollars=ceiling_int,
            authored_constraints=constraints,
        )

    def _build_operational(self) -> OperationalDimension:
        # S5 first-task intent contributes operational authored constraints
        # (the first task the user wants the agent to perform). The intent
        # body is opaque to the assembler — it is carried as the constraint's
        # rule_ast for the compiler to canonicalize.
        constraints = self._authored_constraints_for("S5_first_task")
        return OperationalDimension(authored_constraints=constraints)

    def _build_temporal(self) -> TemporalDimension:
        extraction = self._extractions.get("S4_hours", {})
        operating_hours = extraction.get("operating_hours")
        allowed_windows: list[dict[str, Any]] = []
        if isinstance(operating_hours, dict) and operating_hours:
            allowed_windows = [operating_hours]
        constraints = self._authored_constraints_for("S4_hours")
        return TemporalDimension(
            allowed_windows=allowed_windows,
            authored_constraints=constraints,
        )

    def _build_data_access(self) -> DataAccessDimension:
        # S3 blocked topics become semantic rules on the data-access dimension.
        extraction = self._extractions.get("S3_topics", {})
        topic_rules = extraction.get("blocked_topic_rules")
        semantic_rules: list[dict[str, Any]] = []
        if isinstance(topic_rules, list):
            for idx, rule in enumerate(topic_rules):
                semantic_rules.append({"rule": rule, "order": idx})
        constraints = self._authored_constraints_for("S3_topics")
        return DataAccessDimension(
            semantic_rules=semantic_rules,
            authored_constraints=constraints,
        )

    def _build_communication(self) -> CommunicationDimension:
        # S2 blocked contacts become the recipient denylist.
        extraction = self._extractions.get("S2_people", {})
        blocked = extraction.get("blocked_contacts")
        recipient_denylist: list[str] = []
        if isinstance(blocked, list):
            recipient_denylist = [str(c) for c in blocked]
        constraints = self._authored_constraints_for("S2_people")
        return CommunicationDimension(
            recipient_denylist=recipient_denylist,
            authored_constraints=constraints,
        )

    # ------------------------------------------------------------------
    # Constraint synthesis (JCS-canonical ordering)
    # ------------------------------------------------------------------

    def _authored_constraints_for(self, node_id: str) -> tuple[AuthoredConstraint, ...]:
        """Synthesize the authored constraints for one state's extraction.

        Each non-``reply`` field of the extraction becomes one
        ``AuthoredConstraint`` whose ``constraint_id`` is ``<node_id>:<field>``.
        The tuple is sorted by ``constraint_id`` ascending so the compiler's
        pre-canonicalization-equality assertion (§ 3.2) never has to reorder.
        """
        extraction = self._extractions.get(node_id, {})
        constraints: list[AuthoredConstraint] = []
        for field_name in extraction:
            # ``reply`` is the raw user input echoed by the Signature; it is not
            # an authored constraint (the structured outputs are).
            if field_name == "reply":
                continue
            constraint_id = f"{node_id}:{field_name}"
            constraints.append(
                AuthoredConstraint(
                    constraint_id=constraint_id,
                    rule_ast={"field": field_name, "value": extraction[field_name]},
                    authored=True,
                )
            )
        # JCS-canonical: lexicographic ascending by constraint_id.
        constraints.sort(key=lambda c: c.constraint_id)
        return tuple(constraints)

    # ------------------------------------------------------------------
    # Serialization (for the resume coordinator)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON-round-trippable view of the accumulated extractions.

        Persisted by the resume coordinator alongside ``Plan.to_dict()`` so a
        ``envoy init --resume <ritual_id>`` rehydrates the in-flight assembler.
        """
        return {"extractions": {k: dict(v) for k, v in self._extractions.items()}}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvelopeConfigInputAssembler:
        """Reconstruct an assembler from a persisted ``to_dict()`` payload."""
        assembler = cls()
        extractions = data.get("extractions", {}) if isinstance(data, dict) else {}
        if isinstance(extractions, dict):
            for node_id, extraction in extractions.items():
                if node_id in _FED_STATES and isinstance(extraction, dict):
                    assembler._extractions[node_id] = dict(extraction)
        return assembler
