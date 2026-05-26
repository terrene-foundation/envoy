"""Tier 2 (NO LLM): EnvelopeConfigInputAssembler canonical-order + compiler-accept.

Source: shard 8 § 6.1 row "test_boundary_conversation_envelope_config_input_canonical"
+ § 3.2 (JCS-canonical authored_constraints) + § 5.1 (assemble() → compile()).

Drives the assembler directly (no conversation, no LLM) and asserts:

1. Every dimension's ``authored_constraints[]`` is sorted by ``constraint_id``
   ascending (the JCS-canonical order the compiler expects).
2. ``EnvelopeCompiler.compile(input, principal_id=...)`` accepts the assembled
   input without raising.
3. The compiled ``EnvelopeConfig.canonical_bytes`` is byte-stable across two
   independent runs of the same fed extractions.

Per `rules/testing.md` Tier 2: real ``EnvelopeCompiler`` against the real
canonical_bytes pipeline; NO mocking. Per
`rules/probe-driven-verification.md` MUST-3: every assertion is structural
(sort-order equality, no-raise, byte-equality), not regex-on-prose.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from envoy.boundary_conversation.envelope_assembler import EnvelopeConfigInputAssembler
from envoy.envelope import EnvelopeCompiler, EnvelopeConfig, LocalTemplateResolver
from envoy.envelope.types import EnvelopeMetadata

# The compiler mints a random envelope_id (uuid4) when none is supplied, so two
# compiles of "the same input" differ only by that random id. To exercise the
# byte-stability invariant — same input → same canonical_bytes — the input MUST
# pin the envelope_id (the conversation runtime mints one ritual-stable id per
# conversation; the random-uuid default is what varies). Pinning it isolates the
# assembler+compiler determinism from the uuid mint.
_FIXED_ENVELOPE_ID = "envelope-bc-byte-stable-fixture"


def _feed_full_conversation(assembler: EnvelopeConfigInputAssembler) -> None:
    """Feed one full set of S1..S5 extractions in deliberately scrambled
    field order so the sort assertion is meaningful."""
    assembler.feed(
        "S1_money",
        {"reply": "about 250 dollars a month", "monthly_ceiling_microdollars": 250_000_000},
    )
    assembler.feed(
        "S2_people",
        {"reply": "don't contact my ex or my boss", "blocked_contacts": ["ex@x.com", "boss@y.com"]},
    )
    assembler.feed(
        "S3_topics",
        {
            "reply": "avoid politics and medical advice",
            "blocked_topic_rules": ["no political endorsements", "no medical diagnoses"],
        },
    )
    assembler.feed(
        "S4_hours",
        {
            "reply": "weekdays nine to five eastern",
            "operating_hours": {
                "days": ["mon", "tue", "wed", "thu", "fri"],
                "tz": "America/New_York",
            },
        },
    )
    assembler.feed(
        "S5_first_task",
        {
            "reply": "summarize my unread newsletters",
            "first_task_intent": {"goal": "summarize unread newsletters", "constraints": []},
        },
    )


class TestAuthoredConstraintsAreCanonicallySorted:
    def test_every_dimension_constraints_sorted_ascending(self) -> None:
        """Each dimension emits authored_constraints sorted by constraint_id asc."""
        assembler = EnvelopeConfigInputAssembler()
        _feed_full_conversation(assembler)
        envelope_input = assembler.assemble()

        for dimension in (
            envelope_input.financial,
            envelope_input.operational,
            envelope_input.temporal,
            envelope_input.data_access,
            envelope_input.communication,
        ):
            ids = [c.constraint_id for c in dimension.authored_constraints]
            assert ids == sorted(ids), (
                f"authored_constraints for {type(dimension).__name__} not sorted "
                f"ascending by constraint_id: {ids}"
            )

    def test_constraint_ids_namespaced_by_state_and_field(self) -> None:
        """constraint_id is <node_id>:<field>; reply is never a constraint."""
        assembler = EnvelopeConfigInputAssembler()
        _feed_full_conversation(assembler)
        envelope_input = assembler.assemble()

        comm_ids = {c.constraint_id for c in envelope_input.communication.authored_constraints}
        assert "S2_people:blocked_contacts" in comm_ids
        # The raw `reply` field must never surface as a constraint.
        all_ids = set()
        for dimension in (
            envelope_input.financial,
            envelope_input.operational,
            envelope_input.temporal,
            envelope_input.data_access,
            envelope_input.communication,
        ):
            all_ids |= {c.constraint_id for c in dimension.authored_constraints}
        assert not any(cid.endswith(":reply") for cid in all_ids), all_ids


class TestCompilerAcceptsAssembledInput:
    def test_compile_accepts_without_raising(self, tmp_path: Path) -> None:
        """assemble() → compile() lands a real EnvelopeConfig (first-time author)."""
        assembler = EnvelopeConfigInputAssembler()
        _feed_full_conversation(assembler)
        envelope_input = assembler.assemble()

        compiler = EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path))
        compiled = compiler.compile(envelope_input, principal_id="alice@example")
        assert isinstance(compiled, EnvelopeConfig)
        assert isinstance(compiled.canonical_bytes, bytes) and len(compiled.canonical_bytes) > 0
        assert isinstance(compiled.content_hash, str) and len(compiled.content_hash) == 64

    def test_empty_conversation_still_compiles(self, tmp_path: Path) -> None:
        """Minimum path: an assembler fed nothing still assembles + compiles
        (defaults per § 34 minima)."""
        envelope_input = EnvelopeConfigInputAssembler().assemble()
        assert envelope_input.tool_output_budget_bytes == 65536
        assert envelope_input.cross_domain_rules_authored == []
        compiler = EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path))
        compiled = compiler.compile(envelope_input, principal_id="bob@example")
        assert isinstance(compiled, EnvelopeConfig)


class TestCanonicalBytesAreStableAcrossRuns:
    def test_byte_stable_across_two_identical_runs(self, tmp_path: Path) -> None:
        """Two independent assembler runs of the same extractions compile to
        byte-identical canonical_bytes (the EC-1 reproducibility invariant)."""
        a1 = EnvelopeConfigInputAssembler()
        _feed_full_conversation(a1)
        a2 = EnvelopeConfigInputAssembler()
        _feed_full_conversation(a2)

        compiler = EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path))
        meta = EnvelopeMetadata(envelope_id=_FIXED_ENVELOPE_ID)
        c1 = compiler.compile(
            dataclasses.replace(a1.assemble(), metadata=meta), principal_id="carol@example"
        )
        c2 = compiler.compile(
            dataclasses.replace(a2.assemble(), metadata=meta), principal_id="carol@example"
        )
        assert c1.canonical_bytes == c2.canonical_bytes
        assert c1.content_hash == c2.content_hash

    def test_feed_order_independence(self, tmp_path: Path) -> None:
        """Feeding the same extractions in a different state order produces the
        same canonical_bytes (the assembler sorts; order is not load-bearing)."""
        a1 = EnvelopeConfigInputAssembler()
        a1.feed("S1_money", {"monthly_ceiling_microdollars": 100_000_000})
        a1.feed("S2_people", {"blocked_contacts": ["x@x.com"]})

        a2 = EnvelopeConfigInputAssembler()
        a2.feed("S2_people", {"blocked_contacts": ["x@x.com"]})
        a2.feed("S1_money", {"monthly_ceiling_microdollars": 100_000_000})

        compiler = EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path))
        meta = EnvelopeMetadata(envelope_id=_FIXED_ENVELOPE_ID)
        c1 = compiler.compile(
            dataclasses.replace(a1.assemble(), metadata=meta), principal_id="dave@example"
        )
        c2 = compiler.compile(
            dataclasses.replace(a2.assemble(), metadata=meta), principal_id="dave@example"
        )
        assert c1.canonical_bytes == c2.canonical_bytes
