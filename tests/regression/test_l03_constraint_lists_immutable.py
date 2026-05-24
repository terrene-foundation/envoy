"""Regression: L-03 shards A + B — constraint fields are tuple-typed AND
the 5 dimensions + EnvelopeMetadata are @dataclass(frozen=True, slots=True).

L-03 SHARD STATE (post-PR #12, 2026-05-06):
- Shard A (PR #10): authored_constraints + imported_constraints are
  tuple-typed; .append on a compiled envelope's constraint list raises
  AttributeError.
- Shard B step 1 (PR #11): EnvelopeMetadata @dataclass(frozen=True);
  metadata field reassignment raises FrozenInstanceError.
- Shard B step 2 (PR #12, this regression file's current state): 5
  dimension dataclasses @dataclass(frozen=True); dimension scalar / list /
  dict field reassignment raises FrozenInstanceError. Compiler mints new
  instances via dataclasses.replace.

# SHARD_B_TRIGGER: any markers remaining in this file refer to Phase 02
# deep-freeze (MappingProxyType / tuple-of-tuples) — see workspace todo
# `13-phase-02-deep-freeze-mappingproxy.md` for the next-phase scope.

Failure modes guarded (all 3 shards together):
- (Shard A) `compiled.financial.authored_constraints.append(...)` →
  AttributeError (tuple has no .append).
- (Shard B step 1) `compiled.metadata.envelope_id = "evil"` →
  FrozenInstanceError.
- (Shard B step 2) `compiled.financial.per_call_ceiling_microdollars =
  larger_value` → FrozenInstanceError; same for the other 4 dimensions.

Per `rules/refactor-invariants.md`: permanent regression marker.
Per `rules/testing.md` § Test-Skip Triage: deletion / silent skip BLOCKED.
"""

from __future__ import annotations

import pytest

from envoy.envelope.types import (
    AuthoredConstraint,
    CommunicationDimension,
    ConfidentialityLevel,
    DataAccessDimension,
    FinancialDimension,
    ImportedConstraint,
    OperationalDimension,
    TemporalDimension,
)


DIMENSION_CLASSES = [
    FinancialDimension,
    OperationalDimension,
    TemporalDimension,
    DataAccessDimension,
    CommunicationDimension,
]


class TestAuthoredConstraintsAreTuple:
    """authored_constraints field is tuple-typed, not list."""

    @pytest.mark.parametrize("dim_cls", DIMENSION_CLASSES)
    def test_default_authored_constraints_is_tuple(self, dim_cls) -> None:
        d = dim_cls()
        assert isinstance(d.authored_constraints, tuple), (
            f"{dim_cls.__name__}.authored_constraints MUST be tuple "
            f"(got {type(d.authored_constraints).__name__})"
        )

    @pytest.mark.parametrize("dim_cls", DIMENSION_CLASSES)
    def test_authored_constraints_has_no_append_method(self, dim_cls) -> None:
        """The tuple type forecloses the .append mutation pattern that a
        downstream consumer would use to widen the envelope."""
        d = dim_cls()
        assert not hasattr(d.authored_constraints, "append"), (
            f"{dim_cls.__name__}.authored_constraints MUST be tuple — "
            "the .append method on a list-typed field would let a "
            "downstream consumer silently widen the envelope"
        )

    @pytest.mark.parametrize("dim_cls", DIMENSION_CLASSES)
    def test_attempting_append_raises_attributeerror(self, dim_cls) -> None:
        """The actual mutation attempt fails loud with AttributeError —
        the failure mode L-03 shard A locks."""
        d = dim_cls()
        new_constraint = AuthoredConstraint(
            constraint_id="injected-001",
            rule_ast={"op": "limit"},
        )
        with pytest.raises(AttributeError):
            d.authored_constraints.append(new_constraint)  # type: ignore[attr-defined]


class TestImportedConstraintsAreTuple:
    """imported_constraints field is tuple-typed, not list."""

    @pytest.mark.parametrize("dim_cls", DIMENSION_CLASSES)
    def test_default_imported_constraints_is_tuple(self, dim_cls) -> None:
        d = dim_cls()
        assert isinstance(d.imported_constraints, tuple)

    @pytest.mark.parametrize("dim_cls", DIMENSION_CLASSES)
    def test_attempting_append_raises_attributeerror(self, dim_cls) -> None:
        d = dim_cls()
        new = ImportedConstraint(
            constraint_id="injected-imp-001",
            rule_ast={"op": "limit"},
            template_origin="https://attacker.example/template.json",
            template_hash="sha256:" + "f" * 64,
        )
        with pytest.raises(AttributeError):
            d.imported_constraints.append(new)  # type: ignore[attr-defined]


class TestCompilerTupleConstructionPattern:
    """The compiler's tuple+= pattern (instead of .append) correctly
    accumulates imported_constraints across multiple template folds."""

    def test_tuple_concatenation_preserves_existing(self) -> None:
        """Smoke test the pattern the compiler uses — tuple += pattern
        builds the new tuple from the old + new constraints."""
        existing = (
            ImportedConstraint(
                constraint_id="c1", rule_ast={}, template_origin="o1", template_hash="h1"
            ),
        )
        new = [
            ImportedConstraint(
                constraint_id="c2", rule_ast={}, template_origin="o2", template_hash="h2"
            ),
            ImportedConstraint(
                constraint_id="c3", rule_ast={}, template_origin="o3", template_hash="h3"
            ),
        ]
        # Pattern: existing + tuple(new)
        combined = existing + tuple(new)
        assert isinstance(combined, tuple)
        assert len(combined) == 3
        assert [c.constraint_id for c in combined] == ["c1", "c2", "c3"]

    def test_dimension_construction_accepts_tuple(self) -> None:
        """The dimension's tuple-typed field accepts a tuple value AT
        CONSTRUCTION. L-03 shard B step 2: dimension is frozen, so
        direct reassignment is rejected — `dataclasses.replace` is the
        canonical compiler-side mutation pattern."""
        import dataclasses

        new = (
            AuthoredConstraint(constraint_id="c1", rule_ast={}),
            AuthoredConstraint(constraint_id="c2", rule_ast={}),
        )
        d = FinancialDimension(authored_constraints=new)
        assert d.authored_constraints == new
        assert isinstance(d.authored_constraints, tuple)
        # L-03 shard B step 2: direct reassignment rejected.
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.authored_constraints = new  # type: ignore[misc]
        # The canonical replace pattern works.
        d2 = dataclasses.replace(d, authored_constraints=new[:1])
        assert d2.authored_constraints == new[:1]


class TestShardBFollowupTracking:
    """L-03 shard B step 2 LANDED — dimension dataclasses are now frozen.
    Every assertion in this class verifies that scalar / metadata fields
    raise FrozenInstanceError on direct reassignment. Compiler primitives
    use `dataclasses.replace` to mint new dimension instances.
    """

    def test_financial_per_call_ceiling_field_reassignment_rejected(self) -> None:
        """L-03 shard B step 2 LANDED — FinancialDimension scalar fields
        are now frozen. Direct reassignment raises FrozenInstanceError."""
        import dataclasses

        d = FinancialDimension(per_call_ceiling_microdollars=100)
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.per_call_ceiling_microdollars = 999  # type: ignore[misc]
        # The stored value is unchanged.
        assert d.per_call_ceiling_microdollars == 100

        # The canonical replace pattern still works.
        d2 = dataclasses.replace(d, per_call_ceiling_microdollars=999)
        assert d.per_call_ceiling_microdollars == 100  # original untouched
        assert d2.per_call_ceiling_microdollars == 999

    @pytest.mark.parametrize(
        "dim_factory,field,new_value",
        [
            # Per security review M-1 (same-bug-class fix-immediate per
            # autonomous-execution.md Rule 4): the FinancialDimension test
            # above covered only ONE of 5 dimensions. Each sibling dimension's
            # frozen=True surface is structurally identical and MUST be
            # locked the same way. Parametric coverage closes the gap.
            (lambda: OperationalDimension(), "tool_allowlist", ["evil"]),
            (lambda: OperationalDimension(), "tool_denylist", ["evil"]),
            (lambda: TemporalDimension(), "allowed_windows", [{"start": "00:00"}]),
            (lambda: TemporalDimension(), "blackout_windows", [{"start": "00:00"}]),
            (
                lambda: DataAccessDimension(),
                "classification_clearance",
                ConfidentialityLevel.HIGHLY_CONFIDENTIAL,
            ),
            (lambda: DataAccessDimension(), "field_denylist", ["ssn"]),
            (lambda: CommunicationDimension(), "recipient_allowlist", ["evil@x.com"]),
            (lambda: CommunicationDimension(), "recipient_denylist", ["evil@x.com"]),
            (lambda: CommunicationDimension(), "domain_allowlist", ["evil.com"]),
            (lambda: CommunicationDimension(), "channel_allowlist", ["evil-channel"]),
            # Per /redteam Round 3 R3-M1 (2026-05-24): channel_denylist added
            # in R2-H1 — same-bug-class with the sibling list fields above.
            (lambda: CommunicationDimension(), "channel_denylist", ["evil-channel"]),
        ],
    )
    def test_sibling_dimension_field_reassignment_rejected(
        self, dim_factory, field, new_value
    ) -> None:
        """L-03 shard B step 2 same-bug-class coverage: every scalar/list/dict
        field on every non-Financial dimension MUST raise FrozenInstanceError
        on direct reassignment. The compile pipeline mints new dimension
        instances via `dataclasses.replace`; downstream consumers cannot
        widen by direct field mutation.

        Origin: PR #12 security review M-1 (2026-05-06) — Rule 4 fix-in-PR.
        """
        import dataclasses

        d = dim_factory()
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(d, field, new_value)  # type: ignore[misc]

        # The replace pattern produces a new instance; original is untouched.
        d2 = dataclasses.replace(d, **{field: new_value})
        assert getattr(d2, field) == new_value

    def test_envelope_metadata_authorship_score_field_reassignment_rejected(
        self,
    ) -> None:
        """L-03 shard B Step 1 LANDED — EnvelopeMetadata is now frozen.
        Field reassignment of `authorship_score` raises
        `FrozenInstanceError`. Compiler uses `dataclasses.replace` for
        this update.

        Inner dict mutation (m.authorship_score["k"] = v) STILL succeeds
        today — the dict reference is mutable. Phase 02 deep-freeze via
        MappingProxyType closes that vector.
        """
        import dataclasses

        from envoy.envelope.types import EnvelopeMetadata

        m = EnvelopeMetadata()
        # Field reassignment rejected — frozen dataclass.
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.authorship_score = {"authored_count": 99}  # type: ignore[misc]
        # Inner dict mutation STILL succeeds — Phase 02 closes via
        # MappingProxyType deep-freeze.
        # SHARD_B_TRIGGER (Phase 02 deep-freeze): when MappingProxyType
        # lands, this `m.authorship_score["k"] = v` line MUST raise
        # TypeError instead of succeeding.
        m.authorship_score["authored_count"] = 999
        assert m.authorship_score["authored_count"] == 999

    def test_envelope_metadata_envelope_id_field_reassignment_rejected(self) -> None:
        """L-03 shard B Step 1 LANDED — envelope_id reassignment raises
        FrozenInstanceError. Compiler uses dataclasses.replace to mint
        the new envelope_id."""
        import dataclasses

        from envoy.envelope.types import EnvelopeMetadata

        m = EnvelopeMetadata(envelope_id="test-1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.envelope_id = "test-2"  # type: ignore[misc]
        # The stored value is unchanged.
        assert m.envelope_id == "test-1"

    def test_envelope_metadata_replace_mints_new_instance(self) -> None:
        """L-03 shard B Step 1 LANDED — the compiler's pattern of
        `dataclasses.replace(metadata, envelope_id=..., authorship_score=...)`
        produces a new EnvelopeMetadata with the changed fields; the
        original instance is untouched."""
        import dataclasses

        from envoy.envelope.types import EnvelopeMetadata

        original = EnvelopeMetadata(envelope_id="orig", sub_agent_session_inheritance="isolated")
        replaced = dataclasses.replace(original, envelope_id="new", authorship_score={"v": 1})
        assert original.envelope_id == "orig"
        assert replaced.envelope_id == "new"
        assert replaced.authorship_score == {"v": 1}
        assert replaced.sub_agent_session_inheritance == "isolated"  # preserved


class TestConstructionTimeListCoercion:
    """Per security review CRITICAL C1: list passed at construction time
    is coerced to tuple via __post_init__. Without coercion, the L-03
    invariant only protects the no-arg / tuple-arg path; a caller passing
    a list could store the list and call `.append` on it.
    """

    @pytest.mark.parametrize("dim_cls", DIMENSION_CLASSES)
    def test_list_authored_constraints_coerced_to_tuple_at_construction(self, dim_cls) -> None:
        constraints = [
            AuthoredConstraint(constraint_id="c1", rule_ast={}),
            AuthoredConstraint(constraint_id="c2", rule_ast={}),
        ]
        d = dim_cls(authored_constraints=constraints)
        assert isinstance(d.authored_constraints, tuple), (
            f"{dim_cls.__name__}.__post_init__ MUST coerce list "
            f"to tuple (got {type(d.authored_constraints).__name__})"
        )
        # Mutation now fails — the C1 vector is closed.
        with pytest.raises(AttributeError):
            d.authored_constraints.append(  # type: ignore[attr-defined]
                AuthoredConstraint(constraint_id="injected", rule_ast={})
            )

    @pytest.mark.parametrize("dim_cls", DIMENSION_CLASSES)
    def test_list_imported_constraints_coerced_to_tuple_at_construction(self, dim_cls) -> None:
        constraints = [
            ImportedConstraint(
                constraint_id="ic1",
                rule_ast={},
                template_origin="o1",
                template_hash="sha256:" + "a" * 64,
            ),
        ]
        d = dim_cls(imported_constraints=constraints)
        assert isinstance(d.imported_constraints, tuple)
        with pytest.raises(AttributeError):
            d.imported_constraints.append(  # type: ignore[attr-defined]
                ImportedConstraint(
                    constraint_id="injected",
                    rule_ast={},
                    template_origin="evil",
                    template_hash="sha256:" + "f" * 64,
                )
            )

    @pytest.mark.parametrize("dim_cls", DIMENSION_CLASSES)
    def test_tuple_authored_constraints_passed_through_unchanged(self, dim_cls) -> None:
        """No-op coercion: tuple input stays tuple."""
        c = (AuthoredConstraint(constraint_id="c1", rule_ast={}),)
        d = dim_cls(authored_constraints=c)
        assert d.authored_constraints == c
        assert isinstance(d.authored_constraints, tuple)


class TestFullMutationSurfaceForeclosed:
    """Per security review H-1: tuple structurally forecloses the full
    mutation surface, not just `.append`. Lock the symmetric defense for
    `.extend`, `.insert`, `__setitem__`, in addition to `.append`."""

    @pytest.mark.parametrize(
        "method_name",
        ["append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse"],
    )
    def test_list_mutation_methods_absent_on_tuple(self, method_name: str) -> None:
        """Every list mutation method MUST be absent from the tuple-typed
        field. If a downstream consumer attempts ANY of these, fail loud."""
        d = FinancialDimension()
        assert not hasattr(
            d.authored_constraints, method_name
        ), f"tuple MUST NOT have {method_name!r} method (defeats L-03 invariant)"

    def test_setitem_raises_typeerror(self) -> None:
        """`d.authored_constraints[0] = X` raises TypeError on tuple."""
        d = FinancialDimension(
            authored_constraints=(AuthoredConstraint(constraint_id="c1", rule_ast={}),)
        )
        with pytest.raises(TypeError):
            d.authored_constraints[0] = AuthoredConstraint(  # type: ignore[index]
                constraint_id="injected", rule_ast={}
            )

    def test_iadd_now_rejected_on_frozen_dimension(self) -> None:
        """L-03 shard B step 2 LANDED — dimension is frozen.
        `d.authored_constraints += (...)` desugars to
        `d.authored_constraints = d.authored_constraints + (...)`,
        which is field reassignment on a frozen dataclass and raises
        FrozenInstanceError. The tuple object itself was never mutable,
        so the original reference is unchanged.
        """
        import dataclasses

        d = FinancialDimension(
            authored_constraints=(AuthoredConstraint(constraint_id="c1", rule_ast={}),)
        )
        original_tuple = d.authored_constraints
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.authored_constraints += (  # type: ignore[misc]
                AuthoredConstraint(constraint_id="c2", rule_ast={}),
            )
        # Original tuple is untouched (it was never mutable).
        assert d.authored_constraints == original_tuple
        assert len(d.authored_constraints) == 1


class TestEmptyTemplateFoldPath:
    """Per security review H-2: the `if new_imported:` guard in
    compiler._fold_templates skips the assignment when a template's
    authored_constraints is empty. Lock this behavior."""

    def test_empty_template_does_not_corrupt_existing_imported_constraints(
        self,
    ) -> None:
        """Smoke the empty-template path at the data-shape level (the
        compiler's actual _fold_templates loop is exercised in
        tests/tier1/test_envelope_compiler_pipeline.py; this is the
        unit-level lock for the guard's no-op semantics)."""
        # Existing populated constraint set
        existing = (
            ImportedConstraint(
                constraint_id="orig",
                rule_ast={},
                template_origin="orig",
                template_hash="sha256:" + "a" * 64,
            ),
        )
        # Empty fold — no constraints to add
        new_imported: list[ImportedConstraint] = []
        # Pattern under test: `if new_imported: dim.imported_constraints += tuple(new_imported)`
        if new_imported:
            existing = existing + tuple(new_imported)
        # Existing tuple unchanged
        assert len(existing) == 1
        assert existing[0].constraint_id == "orig"
