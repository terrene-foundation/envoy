"""Tier 1 unit tests for envoy.authorship.score (T-02-30 count-only recompute).

Per `rules/testing.md` § Tier 1 (mocking allowed; <1s per test).

Covers:
- 5-dim canonical iteration order (financial → operational → temporal →
  data_access → communication per `rules/terrene-naming.md`).
- Count-only gating: `authored=True` AND any future
  `novelty_check_passed`/`minimum_impact_check_passed` flags (forward-compat
  via `getattr`).
- Imported-constraint counting + template-provenance dedup + ordering.
- Cross-shard JCS-canonical-order invariant: construction-order independence.
- Deterministic replay (M-05 fix substrate).
- L-03 immutability (frozen dataclass + tuple-of-tuples shape).
- to_dict/from_dict round-trip per `rules/eatp.md`.
- Cold-start (empty envelope) does NOT error.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pytest

from envoy.authorship import (
    AuthorshipCounters,
    AuthorshipScoreDivergenceError,
    recompute_authorship_counters,
)
from envoy.envelope.types import (
    AuthoredConstraint,
    CommunicationDimension,
    DataAccessDimension,
    EnvelopeConfig,
    EnvelopeMetadata,
    FinancialDimension,
    ImportedConstraint,
    OperationalDimension,
    SemanticChecks,
    TemporalDimension,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_envelope_config(
    *,
    financial_authored: tuple[AuthoredConstraint, ...] = (),
    financial_imported: tuple[ImportedConstraint, ...] = (),
    operational_authored: tuple[AuthoredConstraint, ...] = (),
    operational_imported: tuple[ImportedConstraint, ...] = (),
    temporal_authored: tuple[AuthoredConstraint, ...] = (),
    temporal_imported: tuple[ImportedConstraint, ...] = (),
    data_access_authored: tuple[AuthoredConstraint, ...] = (),
    data_access_imported: tuple[ImportedConstraint, ...] = (),
    communication_authored: tuple[AuthoredConstraint, ...] = (),
    communication_imported: tuple[ImportedConstraint, ...] = (),
) -> EnvelopeConfig:
    """Build a minimal compiled `EnvelopeConfig` for tier-1 tests.

    Tier 1 (mocks allowed). The envelope is constructed bypassing the
    compiler — only the dimension authored/imported tuples need to be
    populated for `recompute_authorship_counters` to work.
    """
    from datetime import datetime, timezone

    fin = FinancialDimension(
        authored_constraints=financial_authored,
        imported_constraints=financial_imported,
    )
    op = OperationalDimension(
        authored_constraints=operational_authored,
        imported_constraints=operational_imported,
    )
    tmp = TemporalDimension(
        authored_constraints=temporal_authored,
        imported_constraints=temporal_imported,
    )
    da = DataAccessDimension(
        authored_constraints=data_access_authored,
        imported_constraints=data_access_imported,
    )
    cm = CommunicationDimension(
        authored_constraints=communication_authored,
        imported_constraints=communication_imported,
    )

    return EnvelopeConfig(
        schema_version="envelope/1.0",
        envelope_version=1,
        metadata=EnvelopeMetadata(envelope_id="test-env-1"),
        financial=fin,
        operational=op,
        temporal=tmp,
        data_access=da,
        communication=cm,
        composition_rules=(),
        cross_domain_rules_authored=(),
        tool_output_budget_bytes=65536,
        semantic_checks=SemanticChecks(),
        canonical_bytes=b"",
        content_hash="",
        compiled_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
    )


def _ac(cid: str, *, authored: bool = True) -> AuthoredConstraint:
    return AuthoredConstraint(constraint_id=cid, rule_ast={}, authored=authored)


def _ic(
    cid: str,
    *,
    template_origin: str = "",
    template_hash: str = "",
) -> ImportedConstraint:
    return ImportedConstraint(
        constraint_id=cid,
        rule_ast={},
        template_origin=template_origin,
        template_hash=template_hash,
        authored=False,
    )


# ---------------------------------------------------------------------------
# 5-dim canonical iteration order
# ---------------------------------------------------------------------------


class TestRecomputeFiveDimCanonicalOrder:
    """Per `specs/authorship-score.md` § Re-derivation: iterate financial →
    operational → temporal → data_access → communication."""

    def test_recompute_5_dim_canonical_order(self) -> None:
        """One authored constraint per dimension; total = 5."""
        env = _make_envelope_config(
            financial_authored=(_ac("f1"),),
            operational_authored=(_ac("o1"),),
            temporal_authored=(_ac("t1"),),
            data_access_authored=(_ac("d1"),),
            communication_authored=(_ac("c1"),),
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        assert c.authored_count == 5
        assert c.imported_count == 0
        assert c.template_provenance == ()

    def test_iteration_order_is_canonical_terrene_order(self) -> None:
        """Verify dimensions visited in `(financial, operational, temporal,
        data_access, communication)` order via template-provenance ordering.

        Each dimension carries one imported constraint with a distinct
        template_origin; provenance order MUST be the canonical dim order.
        """
        env = _make_envelope_config(
            financial_imported=(_ic("fi", template_origin="t-fin", template_hash="h-fin"),),
            operational_imported=(_ic("oi", template_origin="t-op", template_hash="h-op"),),
            temporal_imported=(_ic("ti", template_origin="t-tmp", template_hash="h-tmp"),),
            data_access_imported=(_ic("di", template_origin="t-da", template_hash="h-da"),),
            communication_imported=(_ic("ci", template_origin="t-cm", template_hash="h-cm"),),
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        assert c.template_provenance == (
            ("t-fin", "h-fin"),
            ("t-op", "h-op"),
            ("t-tmp", "h-tmp"),
            ("t-da", "h-da"),
            ("t-cm", "h-cm"),
        )


# ---------------------------------------------------------------------------
# Authored counting: only authored=True counts; future flags gated via getattr
# ---------------------------------------------------------------------------


class TestAuthoredCountingFlags:
    """Phase 01 count-only: `c.authored is True` is the SOLE gate.

    Per security review (PR #14) H-01 + H-02 + reviewer M-2:
    - `is True` strict-identity check (not `if c.authored`) defends against
      T-023 type-confusion inflation: `authored="yes"`, `authored=1`,
      `authored=[1]` MUST NOT count.
    - The function does NOT consult Phase-04 `novelty_check_passed` /
      `minimum_impact_check_passed` flags via `getattr`: those flags do
      not exist on `AuthoredConstraint` today (verified at
      `envoy/envelope/types.py`), and a `getattr(_, _, True)` default
      would silently weaken the T-023 defense on a downgraded verifier
      receiving a flag-stripped envelope.

    Phase 04 will add the flags via schema extension AND extend this
    recompute via explicit dispatch (NOT via `getattr` defaults) in the
    same shard that lands the schema. The Phase-01-on-Phase-04-envelope
    backward-compat path is documented as out-of-scope per
    `specs/authorship-score.md § Out of scope (Phase 01)`.
    """

    def test_recompute_only_counts_authored_when_authored_true(self) -> None:
        """`authored=False` does NOT count toward `authored_count`."""
        env = _make_envelope_config(
            financial_authored=(_ac("a-true", authored=True), _ac("a-false", authored=False)),
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        assert c.authored_count == 1

    def test_recompute_strict_identity_rejects_truthy_string(self) -> None:
        """Per security review H-02: `if c.authored is True` strict-identity
        check rejects truthy non-bool values that previous `if c.authored`
        would have accepted as authored. T-023 type-confusion defense.
        """

        @dataclass(frozen=True)
        class TruthyAuthoredConstraint:
            constraint_id: str
            rule_ast: dict
            authored: object  # type: ignore[assignment]

        # Truthy non-bool values that `if c.authored:` would accept.
        c_yes_string = TruthyAuthoredConstraint("a1", {}, "yes")
        c_one_int = TruthyAuthoredConstraint("a2", {}, 1)
        c_list_with_item = TruthyAuthoredConstraint("a3", {}, [1])
        c_truthy_string_false = TruthyAuthoredConstraint("a4", {}, "false")  # truthy!
        c_actually_true = TruthyAuthoredConstraint("a5", {}, True)
        c_actually_false = TruthyAuthoredConstraint("a6", {}, False)

        env = _make_envelope_config(
            financial_authored=(  # type: ignore[arg-type]
                c_yes_string,
                c_one_int,
                c_list_with_item,
                c_truthy_string_false,
                c_actually_true,
                c_actually_false,
            ),
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        # Only c_actually_true (the literal True) counts. The 4 truthy non-bool
        # values do NOT count, even though `if c.authored:` would accept them.
        assert c.authored_count == 1

    def test_recompute_phase04_flags_not_consumed_by_phase01(self) -> None:
        """Per security review H-01 + reviewer M-2: T-02-30 (Phase 01)
        does NOT consume Phase-04 `novelty_check_passed` /
        `minimum_impact_check_passed` flags. Even if a future Phase-04
        envelope is presented today (with the flags set to False), the
        Phase 01 count-only gate counts every `authored is True`
        constraint. Phase 04 will extend this function via explicit
        dispatch when the schema lands; the deferral is documented in
        `specs/authorship-score.md § Out of scope (Phase 01)`.

        This test locks the Phase-01 contract: the spec edit removed
        the novelty + minimum-impact algorithms; the implementation
        matches what ships, no more.
        """

        @dataclass(frozen=True)
        class Phase04AuthoredConstraint:
            constraint_id: str
            rule_ast: dict
            authored: bool
            novelty_check_passed: bool
            minimum_impact_check_passed: bool

        c_all_true = Phase04AuthoredConstraint("a1", {}, True, True, True)
        c_novelty_false = Phase04AuthoredConstraint("a2", {}, True, False, True)
        c_min_impact_false = Phase04AuthoredConstraint("a3", {}, True, True, False)
        c_authored_false = Phase04AuthoredConstraint("a4", {}, False, True, True)

        env = _make_envelope_config(
            financial_authored=(c_all_true, c_novelty_false, c_min_impact_false, c_authored_false),  # type: ignore[arg-type]
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        # All 3 with authored=True count (regardless of Phase-04 flags).
        # Only c_authored_false is excluded.
        assert c.authored_count == 3


# ---------------------------------------------------------------------------
# Imported counting + template provenance dedup + ordering
# ---------------------------------------------------------------------------


class TestImportedCountingAndProvenance:
    def test_recompute_imported_count_excludes_authored(self) -> None:
        """Imported constraints contribute ONLY to `imported_count`."""
        env = _make_envelope_config(
            operational_imported=(
                _ic("oi-1", template_origin="t-op", template_hash="h-op"),
                _ic("oi-2", template_origin="t-op", template_hash="h-op"),
            ),
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        assert c.authored_count == 0
        assert c.imported_count == 2

    def test_template_provenance_dedup_across_dimensions(self) -> None:
        """Same `(template_id, template_hash)` pair appearing across
        multiple imported constraints AND across multiple dimensions
        appears once in provenance."""
        env = _make_envelope_config(
            financial_imported=(
                _ic("fi-1", template_origin="t-shared", template_hash="h-shared"),
                _ic("fi-2", template_origin="t-shared", template_hash="h-shared"),
            ),
            operational_imported=(
                _ic("oi-1", template_origin="t-shared", template_hash="h-shared"),
            ),
            communication_imported=(
                _ic("ci-1", template_origin="t-other", template_hash="h-other"),
            ),
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        assert c.imported_count == 4
        assert c.template_provenance == (
            ("t-shared", "h-shared"),
            ("t-other", "h-other"),
        )

    def test_template_provenance_ordered_by_first_occurrence(self) -> None:
        """Provenance order matches first-encounter order across the
        canonical 5-dim sweep."""
        env = _make_envelope_config(
            data_access_imported=(_ic("di-1", template_origin="t-c", template_hash="h-c"),),
            financial_imported=(_ic("fi-1", template_origin="t-a", template_hash="h-a"),),
            communication_imported=(_ic("ci-1", template_origin="t-b", template_hash="h-b"),),
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        # Iteration is canonical dim order:
        # financial first → ("t-a", "h-a")
        # data_access next (4th) → ("t-c", "h-c")
        # communication last (5th) → ("t-b", "h-b")
        assert c.template_provenance == (
            ("t-a", "h-a"),
            ("t-c", "h-c"),
            ("t-b", "h-b"),
        )

    def test_imported_constraint_with_empty_template_origin_does_not_appear_in_provenance(
        self,
    ) -> None:
        """Imported constraints with empty `template_origin` count toward
        `imported_count` but DO NOT add a provenance entry (Phase 04 will
        require non-empty origin; today the empty-origin path is silent)."""
        env = _make_envelope_config(
            financial_imported=(
                _ic("fi-1", template_origin="", template_hash=""),
                _ic("fi-2", template_origin="t-real", template_hash="h-real"),
            ),
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        assert c.imported_count == 2
        assert c.template_provenance == (("t-real", "h-real"),)


# ---------------------------------------------------------------------------
# Determinism + replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    """Per `specs/authorship-score.md` § Stored vs recomputed (M-05 fix)."""

    def test_recompute_deterministic_replay(self) -> None:
        """Same inputs produce byte-identical `AuthorshipCounters`."""
        env = _make_envelope_config(
            financial_authored=(_ac("f1"), _ac("f2")),
            operational_authored=(_ac("o1"),),
            data_access_imported=(_ic("di", template_origin="t-tmpl", template_hash="h-tmpl"),),
        )
        c1 = recompute_authorship_counters(env, ledger_slice=None)
        c2 = recompute_authorship_counters(env, ledger_slice=None)
        c3 = recompute_authorship_counters(env, ledger_slice=None)
        assert c1 == c2 == c3
        # Stronger byte-identity check via serialization.
        assert c1.to_dict() == c2.to_dict() == c3.to_dict()

    def test_recompute_construction_order_invariance(self) -> None:
        """Cross-shard JCS-canonical-order invariant per shard 9 § 3.4.

        Two envelopes carrying the SAME 5-dim authored constraints
        (constructed in different per-dimension order in the test) produce
        identical counters because the recompute iterates dimensions in
        the canonical order regardless of envelope-construction order."""
        # Build envelope A: populate financial, then communication, then operational.
        env_a = _make_envelope_config(
            financial_authored=(_ac("f1"),),
            communication_authored=(_ac("c1"),),
            operational_authored=(_ac("o1"),),
        )
        # Build envelope B: populate the SAME constraints but pass kwargs in
        # different order. Python preserves keyword-order for the helper but
        # the underlying EnvelopeConfig stores per-dimension; the recompute
        # MUST iterate canonical order regardless.
        env_b = _make_envelope_config(
            operational_authored=(_ac("o1"),),
            communication_authored=(_ac("c1"),),
            financial_authored=(_ac("f1"),),
        )
        c_a = recompute_authorship_counters(env_a, ledger_slice=None)
        c_b = recompute_authorship_counters(env_b, ledger_slice=None)
        assert c_a == c_b
        assert c_a.authored_count == 3


# ---------------------------------------------------------------------------
# AuthorshipCounters round-trip + immutability (rules/eatp.md + L-03)
# ---------------------------------------------------------------------------


class TestAuthorshipCountersDataClassInvariants:
    def test_authorship_counters_round_trip_dict(self) -> None:
        """`from_dict(to_dict(c)) == c` for any constructed counter."""
        c = AuthorshipCounters(
            authored_count=3,
            imported_count=5,
            template_provenance=(
                ("t-a", "h-a"),
                ("t-b", "h-b"),
            ),
        )
        round_tripped = AuthorshipCounters.from_dict(c.to_dict())
        assert round_tripped == c

    def test_authorship_counters_round_trip_empty_provenance(self) -> None:
        """Round-trip with empty template_provenance."""
        c = AuthorshipCounters(authored_count=0, imported_count=0, template_provenance=())
        assert AuthorshipCounters.from_dict(c.to_dict()) == c

    def test_authorship_counters_immutable(self) -> None:
        """L-03 immutability: dataclass is frozen."""
        c = AuthorshipCounters(authored_count=1, imported_count=0, template_provenance=())
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.authored_count = 99  # type: ignore[misc]

    def test_template_provenance_is_tuple_of_tuples(self) -> None:
        """L-03 deep-freeze: provenance MUST be tuple-of-tuples (NOT
        list-of-dicts as the spec pseudocode shows). The wire form is
        list-of-dicts via `to_dict()`; the in-memory form is tuple-of-tuples."""
        c = AuthorshipCounters(
            authored_count=0,
            imported_count=2,
            template_provenance=(("t-1", "h-1"), ("t-2", "h-2")),
        )
        assert isinstance(c.template_provenance, tuple)
        for entry in c.template_provenance:
            assert isinstance(entry, tuple)
            assert len(entry) == 2
            assert all(isinstance(x, str) for x in entry)

    def test_from_dict_raises_on_missing_field(self) -> None:
        """No defaults — `from_dict` raises `KeyError` on a malformed
        payload (per project rule "NEVER USE DEFAULTS FOR FALLBACKS")."""
        with pytest.raises(KeyError):
            AuthorshipCounters.from_dict(
                {"authored_count": 0, "imported_count": 0}
            )  # missing template_provenance
        with pytest.raises(KeyError):
            AuthorshipCounters.from_dict(
                {
                    "authored_count": 0,
                    "imported_count": 0,
                    "template_provenance": [{"template_id": "t"}],  # missing template_hash
                }
            )


# ---------------------------------------------------------------------------
# Edge cases — cold-start + empty
# ---------------------------------------------------------------------------


class TestColdStartAndEmptyCases:
    def test_recompute_empty_envelope_returns_zeros(self) -> None:
        """Cold-start: envelope with no constraints produces (0, 0, ())."""
        env = _make_envelope_config()
        c = recompute_authorship_counters(env, ledger_slice=None)
        assert c == AuthorshipCounters(
            authored_count=0,
            imported_count=0,
            template_provenance=(),
        )

    def test_recompute_per_dim_empty_authored_counted_as_zero(self) -> None:
        """A dimension with empty `authored_constraints` contributes 0
        without raising."""
        env = _make_envelope_config(
            # Only operational has data; the other 4 dimensions are empty
            # (default `authored_constraints=()`).
            operational_authored=(_ac("o1"),),
        )
        c = recompute_authorship_counters(env, ledger_slice=None)
        assert c.authored_count == 1
        assert c.imported_count == 0


# ---------------------------------------------------------------------------
# AuthorshipScoreDivergenceError surface
# ---------------------------------------------------------------------------


class TestAuthorshipScoreDivergenceError:
    def test_divergence_error_carries_stored_recomputed_envelope_id(self) -> None:
        err = AuthorshipScoreDivergenceError(stored=5, recomputed=3, envelope_id="env-abc")
        assert err.stored == 5
        assert err.recomputed == 3
        assert err.envelope_id == "env-abc"

    def test_divergence_error_user_message_is_plain_language(self) -> None:
        """Per `rules/communication.md`: `user_message` MUST be plain language
        for non-technical surfaces (Daily Digest, Channel adapters)."""
        err = AuthorshipScoreDivergenceError(stored=5, recomputed=3)
        # Plain-language message MUST NOT mention "ledger" / "diverge" /
        # "stored count" / etc. — it MUST describe outcome + next action
        # in user-actionable terms.
        msg = err.user_message.lower()
        assert "envelope" in msg
        assert "weekly posture review" in msg
        assert "paused" in msg or "we did not change" in msg
