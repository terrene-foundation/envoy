"""Tier 1 unit tests for envoy.envelope.compiler.EnvelopeCompiler.

Pipeline-level tests with stub dependencies (per Tier 1 rule, mocking allowed).
The Tier 2 wiring test (T-01-11, deferred to wave-1 milestone) exercises the
compile pipeline against real Trust + Ledger fixtures.

Covers carry-forward dispositions:
- R2-M-03: authored_constraints sort at construction.
- R2-M-05: IntersectConflictError propagates verbatim.
- principal_id discipline per `rules/tenant-isolation.md` Rule 2.
"""

from __future__ import annotations

import pytest

from envoy.envelope.compiler import EnvelopeCompiler
from envoy.envelope.errors import (
    EnvelopeValidationError,
    MonotonicTighteningError,
    SchemaVersionMismatchError,
    TemplateResolutionError,
)
from envoy.envelope.template_resolver import LocalTemplateResolver
from envoy.envelope.types import (
    AuthoredConstraint,
    EnvelopeConfigInput,
    FinancialDimension,
)


@pytest.fixture
def resolver(tmp_path):
    return LocalTemplateResolver(root=tmp_path)


@pytest.fixture
def compiler(resolver):
    return EnvelopeCompiler(template_resolver=resolver)


class TestCompilePrincipalIdDiscipline:
    """rules/tenant-isolation.md Rule 2: principal_id required, no default."""

    def test_missing_principal_id_raises(self, compiler) -> None:
        with pytest.raises(EnvelopeValidationError, match="principal_id"):
            compiler.compile(EnvelopeConfigInput(), principal_id="")

    def test_non_string_principal_id_raises(self, compiler) -> None:
        with pytest.raises(EnvelopeValidationError, match="principal_id"):
            compiler.compile(EnvelopeConfigInput(), principal_id=None)  # type: ignore[arg-type]

    def test_valid_principal_id_succeeds(self, compiler, principal_id) -> None:
        env = compiler.compile(EnvelopeConfigInput(), principal_id=principal_id)
        assert env.metadata.envelope_id  # auto-assigned uuid


class TestCompileSchemaVersion:
    def test_unsupported_schema_version_raises(self, compiler, principal_id) -> None:
        bad = EnvelopeConfigInput(schema_version="envelope/0.9")
        with pytest.raises(SchemaVersionMismatchError):
            compiler.compile(bad, principal_id=principal_id)


class TestCompileToolOutputBudget:
    def test_zero_budget_raises(self, compiler, principal_id) -> None:
        bad = EnvelopeConfigInput(tool_output_budget_bytes=0)
        with pytest.raises(EnvelopeValidationError, match="positive"):
            compiler.compile(bad, principal_id=principal_id)

    def test_negative_budget_raises(self, compiler, principal_id) -> None:
        bad = EnvelopeConfigInput(tool_output_budget_bytes=-1)
        with pytest.raises(EnvelopeValidationError, match="positive"):
            compiler.compile(bad, principal_id=principal_id)


class TestR2M03AuthoredConstraintsSort:
    """R2-M-03: lexicographic sort by constraint_id at construction."""

    def test_authored_constraints_sorted_at_compile_time(self, compiler, principal_id) -> None:
        ci = EnvelopeConfigInput(
            financial=FinancialDimension(
                authored_constraints=[
                    AuthoredConstraint(constraint_id="rule-z"),
                    AuthoredConstraint(constraint_id="rule-a"),
                    AuthoredConstraint(constraint_id="rule-m"),
                ]
            )
        )
        env = compiler.compile(ci, principal_id=principal_id)
        ids = [c.constraint_id for c in env.financial.authored_constraints]
        assert ids == ["rule-a", "rule-m", "rule-z"]

    def test_authored_sort_produces_deterministic_canonical_bytes(
        self, compiler, principal_id
    ) -> None:
        # The same content from two different input orderings produces the
        # same content_hash AFTER R2-M-03 sort.
        ci_a = EnvelopeConfigInput(
            financial=FinancialDimension(
                authored_constraints=[
                    AuthoredConstraint(constraint_id="rule-a"),
                    AuthoredConstraint(constraint_id="rule-b"),
                ]
            )
        )
        ci_b = EnvelopeConfigInput(
            financial=FinancialDimension(
                authored_constraints=[
                    AuthoredConstraint(constraint_id="rule-b"),
                    AuthoredConstraint(constraint_id="rule-a"),
                ]
            )
        )
        # Pin envelope_id so the hashes are comparable. L-03 shard B:
        # EnvelopeMetadata is frozen; use dataclasses.replace to mint
        # a new metadata instance with the pinned envelope_id.
        import dataclasses

        ci_a.metadata = dataclasses.replace(ci_a.metadata, envelope_id="env-test-001")
        ci_b.metadata = dataclasses.replace(ci_b.metadata, envelope_id="env-test-001")
        env_a = compiler.compile(ci_a, principal_id=principal_id)
        env_b = compiler.compile(ci_b, principal_id=principal_id)
        # canonical_bytes/content_hash include `compiled_at` indirectly only if
        # the helper put it in the payload. Our pipeline does NOT include
        # compiled_at in the canonical payload (it's on the EnvelopeConfig
        # frame for forensics, not the canonical content). Both compiles
        # therefore produce byte-identical canonical bytes.
        assert env_a.canonical_bytes == env_b.canonical_bytes
        assert env_a.content_hash == env_b.content_hash


class TestMonotonicTightening:
    def test_widened_financial_ceiling_raises(self, compiler, principal_id) -> None:
        parent_input = EnvelopeConfigInput(
            financial=FinancialDimension(per_day_ceiling_microdollars=10_000)
        )
        parent = compiler.compile(parent_input, principal_id=principal_id)

        # Child widens parent's ceiling (10K → 20K)
        child = EnvelopeConfigInput(
            financial=FinancialDimension(per_day_ceiling_microdollars=20_000)
        )
        with pytest.raises(MonotonicTighteningError, match="widens parent"):
            compiler.compile(child, principal_id=principal_id, parent=parent)

    def test_zero_child_ceiling_when_parent_set_raises(self, compiler, principal_id) -> None:
        # Zero == "open" in our model; a 0-child against a >0-parent is widening.
        parent_input = EnvelopeConfigInput(
            financial=FinancialDimension(per_day_ceiling_microdollars=10_000)
        )
        parent = compiler.compile(parent_input, principal_id=principal_id)
        child = EnvelopeConfigInput(financial=FinancialDimension())
        with pytest.raises(MonotonicTighteningError):
            compiler.compile(child, principal_id=principal_id, parent=parent)

    def test_tightened_child_succeeds(self, compiler, principal_id) -> None:
        parent_input = EnvelopeConfigInput(
            financial=FinancialDimension(per_day_ceiling_microdollars=10_000)
        )
        parent = compiler.compile(parent_input, principal_id=principal_id)
        child = EnvelopeConfigInput(
            financial=FinancialDimension(per_day_ceiling_microdollars=5_000)
        )
        env = compiler.compile(child, principal_id=principal_id, parent=parent)
        assert env.financial.per_day_ceiling_microdollars == 5_000


class TestTemplateResolution:
    def test_unknown_uri_scheme_raises(self, compiler, principal_id) -> None:
        ci = EnvelopeConfigInput(template_refs=["foundation-verified:family-budget@1"])
        with pytest.raises(TemplateResolutionError, match="local:"):
            compiler.compile(ci, principal_id=principal_id)

    def test_missing_local_template_raises(self, compiler, principal_id) -> None:
        ci = EnvelopeConfigInput(template_refs=["local:does-not-exist.json"])
        with pytest.raises(TemplateResolutionError, match="not found"):
            compiler.compile(ci, principal_id=principal_id)


class TestPipelineOrderingInvariant:
    """L-03 shard B step 1 / security review M-1: lock the
    `_fold_templates` → step 7 ordering so a future refactor that
    re-orders the pipeline silently dropping `template_provenance`
    fails loudly.

    Threat: step 7 minted a fresh `metadata.authorship_score` via
    `dataclasses.replace`. If a future agent moves step 7 BEFORE
    `_fold_templates`'s in-place `setdefault("template_provenance",
    []).append(...)`, the provenance entry would land on the OLD
    metadata and be discarded by replace. This test asserts the
    survival contract end-to-end.
    """

    def test_template_provenance_survives_compile_pipeline(
        self, compiler, principal_id, tmp_path
    ) -> None:
        import json

        # Author a minimal local template under the resolver root.
        template_path = tmp_path / "tier1-prov-test.json"
        template_path.write_text(
            json.dumps(
                {
                    "financial": {
                        "authored_constraints": [
                            {"constraint_id": "tier1-prov-rule", "rule_ast": {"op": "noop"}}
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        ci = EnvelopeConfigInput(template_refs=[f"local:{template_path.name}"])
        env = compiler.compile(ci, principal_id=principal_id)

        # The fold step must have appended a provenance entry, and
        # step 7's dataclasses.replace must have preserved it.
        provenance = env.metadata.authorship_score.get("template_provenance")
        assert isinstance(provenance, list)
        assert len(provenance) == 1
        assert provenance[0]["uri"] == f"local:{template_path.name}"
        assert provenance[0]["hash"]  # template_hash is non-empty hex digest

        # And the imported constraint itself round-tripped (defense-in-depth).
        imported_ids = [c.constraint_id for c in env.financial.imported_constraints]
        assert "tier1-prov-rule" in imported_ids
