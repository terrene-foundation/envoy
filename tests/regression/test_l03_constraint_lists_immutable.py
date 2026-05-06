"""Regression: L-03 shard A — authored/imported constraint fields are
tuple-typed, preventing in-place mutation of the constraint set.

Source: gate-level security review of PR #3 finding L-03 — out-of-shard
for T-01-15. Original todo at
`workspaces/phase-01-mvp/todos/active/12-followup-l03-frozen-dimension-dataclasses.md`
specifies a full freeze of the 5 dimension dataclasses + EnvelopeMetadata
+ SemanticChecks. Shard A (this PR) ships the lower-risk piece: tuple
typing on the constraint list fields. Shard B will land the full
dimension freeze (preventing scalar mutation of e.g.
`per_call_ceiling_microdollars` post-compile).

Failure mode being guarded: a downstream consumer with a reference to a
compiled `EnvelopeConfig.financial` could call
`compiled.financial.authored_constraints.append(...)` to silently widen
the envelope, breaking content_hash byte-identity. Shard A makes the
field a tuple; `tuple.append` does not exist; the mutation pattern fails
with AttributeError.

Per `rules/refactor-invariants.md`: permanent regression marker.
Per `rules/testing.md` § Test-Skip Triage: deletion / silent skip BLOCKED.
"""

from __future__ import annotations

import pytest

from envoy.envelope.types import (
    AuthoredConstraint,
    CommunicationDimension,
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

    def test_dimension_assignment_accepts_tuple(self) -> None:
        """The dimension's tuple-typed field accepts a tuple value."""
        d = FinancialDimension()
        new = (
            AuthoredConstraint(constraint_id="c1", rule_ast={}),
            AuthoredConstraint(constraint_id="c2", rule_ast={}),
        )
        d.authored_constraints = new
        assert d.authored_constraints == new
        assert isinstance(d.authored_constraints, tuple)


class TestSharddBFollowupTracking:
    """Shard B (full dimension freeze) defers — verify the SCALAR fields
    are still mutable today (locking the current behavior so shard B's
    flip is detectable)."""

    def test_financial_per_call_ceiling_still_mutable_pre_shard_b(self) -> None:
        """Once shard B lands, this MUST flip to assert FrozenInstanceError.
        Today: scalar mutation succeeds; the L-03 vector remains open
        for the dimension's scalar fields. Shard B closes it."""
        d = FinancialDimension(per_call_ceiling_microdollars=100)
        # CURRENT BEHAVIOR — pre-shard-B. Shard B converts this to a
        # pytest.raises(FrozenInstanceError).
        d.per_call_ceiling_microdollars = 999
        assert d.per_call_ceiling_microdollars == 999
