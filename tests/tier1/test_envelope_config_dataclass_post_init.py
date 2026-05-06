"""Tier 1 unit tests for envoy.envelope.types dataclass invariants.

Per `rules/testing.md` § Tier 1: mocking allowed; <1s per test. Dataclass
__post_init__ guards from `specs/envelope-model.md` § Algorithms § "NaN/Inf
guard" + V-06 (classification clearance enum).
"""

from __future__ import annotations

import pytest

from envoy.envelope.types import (
    AlgorithmIdentifier,
    AuthoredConstraint,
    ConfidentialityLevel,
    DataAccessDimension,
    EnvelopeConfigInput,
    FinancialDimension,
    ImportedConstraint,
)


class TestFinancialDimensionPostInit:
    """`__post_init__` enforces NaN/Inf + non-negative ceilings."""

    def test_default_zero_values_pass_post_init(self) -> None:
        f = FinancialDimension()
        assert f.per_call_ceiling_microdollars == 0

    def test_negative_ceiling_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            FinancialDimension(per_call_ceiling_microdollars=-1)

    def test_float_ceiling_raises(self) -> None:
        # Spec mandates integer microdollars; float types are blocked.
        with pytest.raises(ValueError, match="finite integer"):
            FinancialDimension(per_call_ceiling_microdollars=1.5)  # type: ignore[arg-type]

    def test_bool_passes_isinstance_int_but_post_init_allows(self) -> None:
        # `bool` IS a subclass of `int` in Python; we accept it because the
        # canonical_bytes pipeline serializes True/False distinctly anyway.
        # Documented quirk; downstream callers should not pass bools but
        # we don't add a reject branch.
        f = FinancialDimension(per_call_ceiling_microdollars=True)
        assert f.per_call_ceiling_microdollars is True


class TestConfidentialityLevelEnum:
    """V-06 fix: canonical clearance names per `specs/envelope-model.md` § Schema L86."""

    def test_canonical_names_are_pact_aligned(self) -> None:
        assert ConfidentialityLevel.PUBLIC.value == "Public"
        assert ConfidentialityLevel.HIGHLY_CONFIDENTIAL.value == "HighlyConfidential"

    def test_no_legacy_highly_classified_alias(self) -> None:
        # The pre-V-06 name `highly_classified` is BLOCKED — only HighlyConfidential.
        with pytest.raises(ValueError):
            ConfidentialityLevel("highly_classified")

    def test_data_access_default_is_public(self) -> None:
        # Fail-closed default per `rules/security.md` § "Fail-Closed Security Defaults".
        d = DataAccessDimension()
        assert d.classification_clearance == ConfidentialityLevel.PUBLIC


class TestAuthoredAndImportedConstraint:
    def test_authored_constraint_default_authored_true(self) -> None:
        c = AuthoredConstraint(constraint_id="rule-001")
        assert c.authored is True

    def test_imported_constraint_default_authored_false(self) -> None:
        c = ImportedConstraint(constraint_id="rule-002", template_origin="local")
        # Per `specs/envelope-library.md` — imported constraints never count
        # toward Authorship Score.
        assert c.authored is False


class TestAlgorithmIdentifierDefaults:
    """The 4-key form per R3-M-02 (specs/independent-verifier.md L35)."""

    def test_default_4_key_form(self) -> None:
        a = AlgorithmIdentifier()
        assert a.sig == "ed25519"
        assert a.hash == "sha256"
        assert a.shamir == "slip39"
        assert a.canonical_json == "jcs-rfc8785"
        assert a.cross_domain_rules.startswith("envoy-registry:cross-domain-flows:")

    def test_algorithm_identifier_is_frozen(self) -> None:
        a = AlgorithmIdentifier()
        with pytest.raises((AttributeError, TypeError)):
            a.sig = "rsa"  # type: ignore[misc]


class TestEnvelopeConfigInputDefaults:
    """Default-constructed input is a valid (if minimal) authoring shape."""

    def test_default_schema_version(self) -> None:
        e = EnvelopeConfigInput()
        assert e.schema_version == "envelope/1.0"

    def test_default_tool_output_budget_is_positive(self) -> None:
        e = EnvelopeConfigInput()
        assert e.tool_output_budget_bytes > 0

    def test_default_metadata_has_4_key_algorithm_identifier(self) -> None:
        e = EnvelopeConfigInput()
        assert e.metadata.algorithm_identifier.canonical_json == "jcs-rfc8785"
