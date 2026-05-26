"""Tier 2: CascadeRevocationOrchestrator wiring against a real KailashRuntime-shaped stub.

Per `rules/testing.md` § Tier 2 + `rules/facade-manager-detection.md` Rule 1:
- Wiring test imports the orchestrator through its public module surface.
- Constructs the orchestrator against a real-shape runtime
  (a plain class implementing ``trust_cascade_revoke`` per the
  Phase-01 ``KailashRuntime`` Protocol; NO ``unittest.mock``).
- Asserts externally-observable effects (CascadeResult fields, raised
  exception carries structured info).

The runtime stub here is NOT a mock: it is a plain class satisfying the
``_RuntimeProtocol`` shape. Per the Phase-01 design (T-03-52 prompt),
the orchestrator's contract is solely "call cascade_revoke then verify";
the real Phase-02 substrate behind ``trust_cascade_revoke`` is the
TrustStoreAdapter, which is itself wired in T-01-15. Substituting a
plain class for the runtime here mirrors the same pattern Boundary
Conversation tests use — real-shape collaborators, no ``MagicMock``.

Covers `workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
§ 3 step 6 invariants for T-03-52:

- ``revoke_and_verify`` returns complete CascadeResult when
  ``expected ⊆ revoked``.
- ``revoke_and_verify`` raises CascadeIncompleteError with the
  structured result when ``missing_descendants`` is non-empty.
- ``revoke_lenient`` returns CascadeResult with empty
  ``expected_descendants`` and ``complete=True`` regardless of the
  actual revoked set.
- ``CascadeIncompleteError.result`` carries the populated CascadeResult
  with non-empty ``missing_descendants``.
- Frozen ``CascadeResult`` rejects attribute assignment.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from envoy.grant_moment.cascade_orchestrator import (
    CascadeIncompleteError,
    CascadeResult,
    CascadeRevocationOrchestrator,
)


class _RuntimeStub:
    """Plain-class implementation of the Phase-01 ``_RuntimeProtocol``.

    Records every call to ``trust_cascade_revoke`` so wiring assertions
    can verify the orchestrator forwarded the right ``root_id``. NOT a
    mock — there is no ``unittest.mock`` import on this class; it is a
    real Python object satisfying the structural Protocol shape per
    `rules/testing.md` § Tier 2 (NO mocking on Tier 2).
    """

    def __init__(self, revoked_set: frozenset[str]) -> None:
        self._revoked_set = revoked_set
        self.calls: list[str] = []

    def trust_cascade_revoke(self, root_id: str) -> set[str]:
        self.calls.append(root_id)
        # Return a mutable set per the Protocol signature; the
        # orchestrator normalizes to frozenset on its side.
        return set(self._revoked_set)


# ---------------------------------------------------------------------------
# revoke_and_verify — happy path: expected ⊆ revoked
# ---------------------------------------------------------------------------


class TestRevokeAndVerifyHappyPath:
    def test_returns_complete_result_when_expected_subset_of_revoked(self):
        runtime = _RuntimeStub(revoked_set=frozenset({"agent-A", "agent-B", "agent-C", "agent-D"}))
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        result = orchestrator.revoke_and_verify(
            root_id="agent-A",
            expected_descendants=frozenset({"agent-B", "agent-C"}),
        )

        assert result.complete is True
        assert result.missing_descendants == frozenset()
        assert result.revoked_ids == frozenset({"agent-A", "agent-B", "agent-C", "agent-D"})
        assert result.expected_descendants == frozenset({"agent-B", "agent-C"})
        assert result.root_id == "agent-A"
        # Externally observable: the runtime received the cascade call
        # with the right root_id.
        assert runtime.calls == ["agent-A"]

    def test_complete_when_expected_equals_revoked_exactly(self):
        runtime = _RuntimeStub(revoked_set=frozenset({"agent-X", "agent-Y"}))
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        result = orchestrator.revoke_and_verify(
            root_id="agent-X",
            expected_descendants=frozenset({"agent-X", "agent-Y"}),
        )

        assert result.complete is True
        assert result.missing_descendants == frozenset()

    def test_complete_when_expected_is_empty(self):
        # Empty expectation is trivially a subset of any revoked set.
        runtime = _RuntimeStub(revoked_set=frozenset({"agent-A"}))
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        result = orchestrator.revoke_and_verify(
            root_id="agent-A",
            expected_descendants=frozenset(),
        )

        assert result.complete is True
        assert result.expected_descendants == frozenset()
        assert result.revoked_ids == frozenset({"agent-A"})


# ---------------------------------------------------------------------------
# revoke_and_verify — raise path: missing_descendants non-empty
# ---------------------------------------------------------------------------


class TestRevokeAndVerifyRaisesOnGap:
    def test_raises_cascade_incomplete_when_missing_descendants(self):
        runtime = _RuntimeStub(revoked_set=frozenset({"agent-A", "agent-B"}))
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        with pytest.raises(CascadeIncompleteError) as exc_info:
            orchestrator.revoke_and_verify(
                root_id="agent-A",
                # Expect C+D but neither is in the revoked set.
                expected_descendants=frozenset({"agent-C", "agent-D"}),
            )

        # CascadeIncompleteError.result carries the populated CascadeResult.
        err = exc_info.value
        assert isinstance(err.result, CascadeResult)
        assert err.result.complete is False
        assert err.result.missing_descendants == frozenset({"agent-C", "agent-D"})
        assert err.result.revoked_ids == frozenset({"agent-A", "agent-B"})
        assert err.result.expected_descendants == frozenset({"agent-C", "agent-D"})
        assert err.result.root_id == "agent-A"

    def test_error_message_names_root_and_count(self):
        runtime = _RuntimeStub(revoked_set=frozenset({"agent-A"}))
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        with pytest.raises(CascadeIncompleteError) as exc_info:
            orchestrator.revoke_and_verify(
                root_id="agent-A",
                expected_descendants=frozenset({"agent-missing-1", "agent-missing-2"}),
            )

        # Plain-language message names the root_id + descendant count.
        msg = str(exc_info.value)
        assert "agent-A" in msg
        assert "2" in msg  # the missing count

    def test_partial_overlap_reports_only_missing(self):
        # Revoked has B but not C; expected wants both → only C missing.
        runtime = _RuntimeStub(revoked_set=frozenset({"agent-A", "agent-B"}))
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        with pytest.raises(CascadeIncompleteError) as exc_info:
            orchestrator.revoke_and_verify(
                root_id="agent-A",
                expected_descendants=frozenset({"agent-B", "agent-C"}),
            )

        assert exc_info.value.result.missing_descendants == frozenset({"agent-C"})


# ---------------------------------------------------------------------------
# revoke_lenient — NEVER raises, regardless of actual revoked set
# ---------------------------------------------------------------------------


class TestRevokeLenient:
    def test_lenient_returns_complete_with_empty_expectations(self):
        runtime = _RuntimeStub(revoked_set=frozenset({"agent-A", "agent-B", "agent-C"}))
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        result = orchestrator.revoke_lenient(root_id="agent-A")

        assert result.complete is True
        assert result.expected_descendants == frozenset()
        assert result.missing_descendants == frozenset()
        # The actual revoked set is still surfaced for the caller's
        # inspection — lenient does not throw the info away.
        assert result.revoked_ids == frozenset({"agent-A", "agent-B", "agent-C"})
        assert result.root_id == "agent-A"
        assert runtime.calls == ["agent-A"]

    def test_lenient_complete_even_when_runtime_revokes_nothing(self):
        # No matter what the runtime returns — including empty — lenient
        # is complete by definition (empty expectation is a subset of
        # every set).
        runtime = _RuntimeStub(revoked_set=frozenset())
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        result = orchestrator.revoke_lenient(root_id="agent-orphan")

        assert result.complete is True
        assert result.revoked_ids == frozenset()
        assert result.missing_descendants == frozenset()


# ---------------------------------------------------------------------------
# CascadeResult immutability
# ---------------------------------------------------------------------------


class TestCascadeResultImmutability:
    def test_frozen_cascade_result_rejects_attribute_assignment(self):
        # Construct via the orchestrator (canonical path) so the test
        # exercises the actual production-shaped CascadeResult instance.
        runtime = _RuntimeStub(revoked_set=frozenset({"agent-A"}))
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        result = orchestrator.revoke_lenient(root_id="agent-A")

        with pytest.raises(FrozenInstanceError):
            result.root_id = "tampered"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            result.complete = False  # type: ignore[misc]

    def test_frozen_cascade_result_revoked_ids_is_frozenset(self):
        runtime = _RuntimeStub(revoked_set=frozenset({"agent-A", "agent-B"}))
        orchestrator = CascadeRevocationOrchestrator(runtime=runtime)

        result = orchestrator.revoke_lenient(root_id="agent-A")

        # frozenset is the immutable set type; the result type-pins it
        # so callers cannot .add() / .remove() into the orchestrator's
        # view of the revoked set.
        assert isinstance(result.revoked_ids, frozenset)
        assert isinstance(result.expected_descendants, frozenset)
        assert isinstance(result.missing_descendants, frozenset)
