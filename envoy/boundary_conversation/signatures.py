"""envoy.boundary_conversation.signatures — per-state Kaizen Signatures S1..S9.

Each Boundary Conversation state that takes a user answer (S1..S9) has a
dedicated Kaizen ``Signature`` subclass declaring the user's reply as an
input field and the structured, validated result as output field(s). The
state machine and field semantics are frozen in
`specs/boundary-conversation.md` § "Questions per state".

These are pure Kaizen primitives (the class-based / "Option 3" declarative
form: ``name: type = InputField(...) / OutputField(...)``, where the
``SignatureMeta`` metaclass populates ``inputs`` / ``outputs`` /
``_signature_inputs`` / ``_signature_outputs`` from the annotated fields).
ZERO dependencies on other envoy packages.

S0 (greet) and S10 (complete) take no user answer, so they have no Signature.

NOTE: this module deliberately does NOT use ``from __future__ import
annotations``. Kaizen's ``SignatureMeta`` reads each field's class-level
annotation at class-creation time and records it in ``_signature_inputs`` /
``_signature_outputs``. Under PEP 563 (string annotations) the metaclass would
record the annotation as the *string* ``"int"`` rather than the real ``int``
type, defeating downstream type-aware compilation. Keeping eager annotations
preserves precise field types (all annotations here are builtins).
"""

# pyright: reportAssignmentType=false
# Kaizen Signature DSL: fields are declared `name: type = InputField(...)` /
# `OutputField(...)` (upstream's own canonical form — see
# kaizen.signatures.core docstring). The SignatureMeta metaclass reads each
# field's annotation for the type and the descriptor for config, so the
# `descriptor assigned to a typed annotation` shape pyright flags is the
# intended idiom, not a bug. Scoped to this declarations-only module.

from kaizen.signatures.core import InputField, OutputField, Signature

__all__ = [
    "S1MoneySignature",
    "S2PeopleSignature",
    "S3TopicsSignature",
    "S4HoursSignature",
    "S5FirstTaskSignature",
    "S6TemplateSignature",
    "S7VisibleSecretSignature",
    "S8ShamirSignature",
    "S9ReviewSignSignature",
]


class S1MoneySignature(Signature):
    """S1 — monthly spending ceiling.

    Spec: "S1: monthly ceiling USD." The user states a monthly cap in plain
    dollars; the structured output is the ceiling in integer microdollars
    (1 USD = 1_000_000 microdollars) so no floating-point rounding can leak
    into a financial limit.
    """

    reply: str = InputField(desc="User's stated monthly spending ceiling, e.g. '500 USD'.")
    monthly_ceiling_microdollars: int = OutputField(
        desc="Monthly ceiling in integer microdollars (1 USD = 1_000_000).",
    )


class S2PeopleSignature(Signature):
    """S2 — blocked contacts.

    Spec: "S2: blocked contacts." The agent must never reach out to these
    people; the structured output is the list of contact identifiers to block.
    """

    reply: str = InputField(desc="User's description of people the agent must not contact.")
    blocked_contacts: list = OutputField(
        desc="List of blocked contact identifiers (names / emails / handles).",
    )


class S3TopicsSignature(Signature):
    """S3 — blocked topics as semantic rules.

    Spec: "S3: blocked topics (semantic rules)." Output is a list of
    semantic rule strings (not raw keywords) so the boundary survives
    paraphrase. Subject to novelty checking (S3 backward edge).
    """

    reply: str = InputField(desc="User's description of subjects the agent must avoid.")
    blocked_topic_rules: list = OutputField(
        desc="List of semantic rule strings describing forbidden topics.",
    )


class S4HoursSignature(Signature):
    """S4 — operating hours.

    Spec: "S4: operating hours." Output is a structured operating-hours
    description (e.g. per-day windows + timezone) the runtime can enforce.
    """

    reply: str = InputField(desc="User's description of when the agent may operate.")
    operating_hours: dict = OutputField(
        desc="Structured operating hours: per-day windows plus timezone.",
    )


class S5FirstTaskSignature(Signature):
    """S5 — first-task intent.

    Spec: "S5: first-task intent." Output is the structured intent of the
    first task the user wants the agent to perform. Subject to novelty
    checking (S5 backward edge).
    """

    reply: str = InputField(desc="User's description of the first task for the agent.")
    first_task_intent: dict = OutputField(
        desc="Structured first-task intent (goal + constraints).",
    )


class S6TemplateSignature(Signature):
    """S6 — template choice.

    Spec: "S6: template import (Foundation-Verified only in Phase 01 local
    cache) OR from-scratch." Output discriminates the two paths: whether a
    template was chosen and, if so, which template id.
    """

    reply: str = InputField(desc="User's choice: import a named template, or build from scratch.")
    use_template: bool = OutputField(
        desc="True if the user chose to import a template; False for from-scratch.",
    )
    template_id: str = OutputField(
        desc="The chosen template id when use_template is True; empty otherwise.",
    )


class S7VisibleSecretSignature(Signature):
    """S7 — visible secret setup.

    Spec: "S7: visible secret (icon + color + phrase)." All three components
    are required; absence at S9 raises ``VisibleSecretMissingError``.
    """

    reply: str = InputField(desc="User's chosen icon, color, and secret phrase.")
    icon: str = OutputField(desc="Chosen visible-secret icon identifier.")
    color: str = OutputField(desc="Chosen visible-secret color.")
    phrase: str = OutputField(desc="Chosen visible-secret phrase.")


class S8ShamirSignature(Signature):
    """S8 — Shamir backup configuration.

    Spec: "S8: Shamir 3-of-5 default; 5-in-safes alternative; custom."
    Output is the threshold / total-shard configuration plus a distribution
    mode discriminator.
    """

    reply: str = InputField(desc="User's choice of Shamir backup scheme.")
    threshold: int = OutputField(desc="Number of shards required to recover (default 3).")
    total_shards: int = OutputField(desc="Total number of shards produced (default 5).")
    distribution_mode: str = OutputField(
        desc="Distribution mode: 'default', '5-in-safes', or 'custom'.",
    )


class S9ReviewSignSignature(Signature):
    """S9 — review and sign.

    Spec: "S9: plain-language envelope summary + sign." Output carries the
    plain-language summary shown to the user and the boolean sign confirmation
    that gates completion (S10).
    """

    reply: str = InputField(desc="User's confirmation to sign after reviewing the summary.")
    plain_language_summary: str = OutputField(
        desc="Plain-language summary of the compiled envelope shown for review.",
    )
    signed: bool = OutputField(desc="True when the user confirms and signs the envelope.")
