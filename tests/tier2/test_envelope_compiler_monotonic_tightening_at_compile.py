"""Tier 2: compile-time monotonic tightening of authored_constraints.

Source: shard 8 § 5.1 + § 6.1 row
"test_envelope_compiler_monotonic_tightening_at_compile" +
`specs/envelope-model.md` § Schema (canonicalized authored_constraints).

T-02-44 prescribed coverage gap: byte-stability + JCS-canonical-order is
covered by `test_boundary_conversation_envelope_config_input_canonical.py`,
and the envelope mint-time hash invariant is pinned by
`test_envelope_hash_mint_time_cached.py`. This dedicated file ADDS the explicit
**monotonic tightening at compile** contract per § 5.1:

> The compiler accepts the fed extractions in any order, but emits a sorted
> ``authored_constraints[]`` per dimension — the canonical order is total and
> ascending by ``constraint_id``. Re-compiling with the SAME inputs MUST
> produce byte-identical canonical_bytes. Re-compiling with a SUPERSET of
> inputs MUST produce a canonical_bytes whose authored_constraints[] is a
> superset (and remains sorted ascending).

Monotonic = "compiles only tighten, never loosen": a later compile with
additional constraints over the same dimension MUST preserve every prior
constraint AND add the new ones AND remain canonically sorted.

Phase 01: Boundary Conversation runs the compile ONCE (S9). The monotonic
contract still applies at the assembler/compiler boundary because the
assembler is append-only and the compiler is deterministic on its input;
Phase 02 will exercise the multi-compile re-tightening path under the
"Envelope edit" flow established by T-02-33.

Per `rules/probe-driven-verification.md` MUST-3 (no LLM here): every
assertion is structural — sorted-equality, sorted-superset, byte-equality.
Per `rules/testing.md` § Tier 2: real ``EnvelopeCompiler`` + real
canonical_bytes pipeline; NO mocking.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from envoy.boundary_conversation.envelope_assembler import EnvelopeConfigInputAssembler
from envoy.envelope import EnvelopeCompiler, EnvelopeConfig, LocalTemplateResolver
from envoy.envelope.types import EnvelopeMetadata


# The compiler mints a random envelope_id when none is supplied; pinning the id
# isolates the assembler+compiler determinism from the uuid mint. The metadata
# shape mirrors what the runtime's S9 path constructs (ritual-stable per
# conversation).
_FIXED_ENVELOPE_ID = "envelope-bc-monotonic-tightening-fixture"

PRINCIPAL = "alice@example"


def _feed_minimal_set(assembler: EnvelopeConfigInputAssembler) -> None:
    """Feed a minimal S1..S5 extraction set with a small communication block."""
    assembler.feed(
        "S1_money",
        {"monthly_ceiling_microdollars": 250_000_000},
    )
    assembler.feed(
        "S2_people",
        {"blocked_contacts": ["ex@x.com"]},
    )
    assembler.feed(
        "S3_topics",
        {"blocked_topic_rules": ["no political endorsements"]},
    )
    assembler.feed(
        "S4_hours",
        {"operating_hours": {"days": ["mon", "tue"], "tz": "UTC"}},
    )
    assembler.feed(
        "S5_first_task",
        {"first_task_intent": {"goal": "summarize my unread newsletters"}},
    )


def _feed_superset(assembler: EnvelopeConfigInputAssembler) -> None:
    """Feed the same minimal extractions PLUS additional blocked-topic entries.

    Tightening means: every constraint in the minimal set survives, AND new
    ones are added; the sorted invariant holds across the superset too.
    """
    assembler.feed(
        "S1_money",
        {"monthly_ceiling_microdollars": 250_000_000},
    )
    assembler.feed(
        "S2_people",
        {"blocked_contacts": ["ex@x.com"]},
    )
    assembler.feed(
        "S3_topics",
        {
            "blocked_topic_rules": [
                "no political endorsements",
                "no medical diagnoses",  # new — must appear in superset
                "no financial advice",  # new — must appear in superset
            ]
        },
    )
    assembler.feed(
        "S4_hours",
        {"operating_hours": {"days": ["mon", "tue"], "tz": "UTC"}},
    )
    assembler.feed(
        "S5_first_task",
        {"first_task_intent": {"goal": "summarize my unread newsletters"}},
    )


def _compile(assembler: EnvelopeConfigInputAssembler, tmp_path: Path) -> EnvelopeConfig:
    raw_input = assembler.assemble()
    fixed_metadata = EnvelopeMetadata(envelope_id=_FIXED_ENVELOPE_ID)
    pinned = dataclasses.replace(raw_input, metadata=fixed_metadata)
    compiler = EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path))
    return compiler.compile(pinned, principal_id=PRINCIPAL)


class TestCanonicalOrderAtCompile:
    def test_authored_constraints_sorted_ascending_per_dimension(self, tmp_path: Path) -> None:
        """Each dimension's ``authored_constraints[]`` is sorted ascending by
        ``constraint_id`` — the JCS canonical order the canonical_bytes hash
        depends on. Re-shuffling the feed order MUST NOT change the compiled
        order."""
        assembler = EnvelopeConfigInputAssembler()
        _feed_minimal_set(assembler)
        config = _compile(assembler, tmp_path)

        for dimension_name in (
            "financial",
            "operational",
            "communication",
            "temporal",
            "data_access",
        ):
            dimension = getattr(config, dimension_name)
            ids = [c.constraint_id for c in dimension.authored_constraints]
            assert ids == sorted(ids), (
                f"{dimension_name}.authored_constraints not in canonical " f"ascending order: {ids}"
            )


class TestByteStableUnderRepeatedCompile:
    def test_same_input_compiles_byte_identical(self, tmp_path: Path) -> None:
        """Two compiles of the SAME assembler state produce byte-identical
        canonical_bytes — the structural pre-condition for monotonic
        tightening (without determinism, "tightening" has no fixed point)."""
        first_assembler = EnvelopeConfigInputAssembler()
        _feed_minimal_set(first_assembler)
        first = _compile(first_assembler, tmp_path)

        second_assembler = EnvelopeConfigInputAssembler()
        _feed_minimal_set(second_assembler)
        second = _compile(second_assembler, tmp_path)

        assert first.canonical_bytes == second.canonical_bytes


class TestMonotonicTightening:
    """The structural tightening invariant: a superset compile's
    authored_constraints[] is a superset of the prior compile's per dimension,
    AND remains canonically sorted ascending — never loosens."""

    def test_superset_compile_preserves_minimal_constraints(self, tmp_path: Path) -> None:
        minimal_assembler = EnvelopeConfigInputAssembler()
        _feed_minimal_set(minimal_assembler)
        minimal = _compile(minimal_assembler, tmp_path)

        superset_assembler = EnvelopeConfigInputAssembler()
        _feed_superset(superset_assembler)
        superset = _compile(superset_assembler, tmp_path)

        # Tightening — every constraint_id present in the minimal compile is
        # present in the superset compile, for every dimension.
        for dimension_name in (
            "financial",
            "operational",
            "communication",
            "temporal",
            "data_access",
        ):
            minimal_ids = {
                c.constraint_id for c in getattr(minimal, dimension_name).authored_constraints
            }
            superset_ids = {
                c.constraint_id for c in getattr(superset, dimension_name).authored_constraints
            }
            assert minimal_ids.issubset(superset_ids), (
                f"{dimension_name}: minimal compile constraints "
                f"{minimal_ids - superset_ids} dropped from superset compile"
            )

    def test_superset_compile_authored_constraints_still_sorted(self, tmp_path: Path) -> None:
        """Tightening preserves canonical sort. Adding more constraints to a
        dimension MUST keep authored_constraints[] sorted ascending."""
        superset_assembler = EnvelopeConfigInputAssembler()
        _feed_superset(superset_assembler)
        superset = _compile(superset_assembler, tmp_path)

        for dimension_name in (
            "financial",
            "operational",
            "communication",
            "temporal",
            "data_access",
        ):
            ids = [c.constraint_id for c in getattr(superset, dimension_name).authored_constraints]
            assert ids == sorted(ids), (
                f"{dimension_name}.authored_constraints lost canonical order "
                f"after tightening: {ids}"
            )

    def test_superset_canonical_bytes_strictly_differ_from_minimal(self, tmp_path: Path) -> None:
        """A superset compile MUST produce DIFFERENT canonical_bytes than the
        minimal compile (the hash is content-addressed; tightening changes the
        content). Same envelope_id + same metadata + more constraints MUST
        not collapse to the same hash — closes the rules/orphan-detection.md
        Rule 2a crypto-pair concern at the compile level."""
        minimal_assembler = EnvelopeConfigInputAssembler()
        _feed_minimal_set(minimal_assembler)
        minimal = _compile(minimal_assembler, tmp_path)

        superset_assembler = EnvelopeConfigInputAssembler()
        _feed_superset(superset_assembler)
        superset = _compile(superset_assembler, tmp_path)

        assert minimal.canonical_bytes != superset.canonical_bytes
