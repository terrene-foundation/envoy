"""envoy.grant_moment.cascade_orchestrator — verified cascade revocation.

Per `workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
§ 3 step 6: "wraps upstream ``cascade_revoke``; verifies
``verify_cascade_complete``. Critical for EC-8 (Day-1 grant revoked from
Day-6 child grant on different channel)."

Spec source: `specs/grant-moment.md` cross-reference to
`specs/trust-lineage.md` § Cascade revocation BFS semantics.

The upstream cascade is surfaced via the runtime abstraction at
``envoy.runtime.protocol.KailashRuntime.trust_cascade_revoke(root_id) ->
set[str]`` — the Phase-01 narrow returns the set of revoked agent ids.
The orchestrator's job is the verification half of the contract: call the
runtime, then check that every expected descendant id is present in the
returned set. That verification is "verify_cascade_complete" at this
shard's surface — the BFS itself lives upstream.

This module is pure Python; ZERO dependencies on other envoy packages
besides the runtime ``Protocol`` shape (structurally typed; no import
required at construction time because we accept any object satisfying
``_RuntimeProtocol``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

__all__ = [
    "CascadeResult",
    "CascadeIncompleteError",
    "CascadeRevocationOrchestrator",
]


class _RuntimeProtocol(Protocol):
    """Subset of ``envoy.runtime.protocol.KailashRuntime`` we depend on.

    Mirrors the ``_KeyManagerProtocol`` pattern in
    ``envoy.grant_moment.signed_consent`` — keep the dependency surface
    minimal so the Phase 02 runtime adapter (Rust binding) can satisfy
    the same shape without re-importing through envoy.runtime.
    """

    def trust_cascade_revoke(self, root_id: str) -> set[str]: ...


@dataclass(frozen=True, slots=True)
class CascadeResult:
    """Structured outcome of a cascade revocation.

    - ``root_id``: the revocation root the orchestrator was asked to cascade.
    - ``revoked_ids``: every id the upstream runtime reports as revoked.
    - ``expected_descendants``: the set the caller asserted MUST be revoked
      (empty for the lenient API).
    - ``missing_descendants``: ``expected_descendants - revoked_ids``;
      empty on success.
    - ``complete``: True iff ``missing_descendants`` is empty.

    Frozen per `rules/zero-tolerance.md` Rule 3a — the result is the
    structured failure carrier and MUST NOT be mutated by callers after
    the orchestrator returns it.
    """

    root_id: str
    revoked_ids: frozenset[str]
    expected_descendants: frozenset[str]
    missing_descendants: frozenset[str]
    complete: bool


class CascadeIncompleteError(Exception):
    """Raised when ``verify_cascade_complete`` found expected descendants
    absent from the runtime's revoked-set.

    Carries the ``CascadeResult`` so callers can inspect ``missing_descendants``
    + the full ``revoked_ids`` set without re-running the cascade. Per
    `rules/zero-tolerance.md` Rule 3a (typed delegate guards with structured
    failure info) — opaque exceptions hide the gap; the structured carrier
    surfaces it for ledger entries + operator triage.

    Plain-language message per `rules/communication.md` — users may see this
    surfaced through Boundary Conversation re-pair flows; the message names
    the gap without leaking internal identifiers as the headline.
    """

    def __init__(self, result: CascadeResult) -> None:
        self.result = result
        missing_count = len(result.missing_descendants)
        # Surface the count + root for operator triage; full id set lives on
        # `result` for programmatic inspection. Plain wording per
        # rules/communication.md — the user-facing surface should not lead
        # with raw set notation.
        message = (
            f"Cascade revocation for root {result.root_id!r} did not reach "
            f"{missing_count} expected descendant(s). Inspect "
            "CascadeIncompleteError.result.missing_descendants for the "
            "missing ids."
        )
        super().__init__(message)


class CascadeRevocationOrchestrator:
    """Wraps the runtime's ``trust_cascade_revoke`` with a verify-or-raise
    contract (``revoke_and_verify``) plus an ad-hoc lenient form
    (``revoke_lenient``).

    Per spec § Cascade revocation BFS semantics — the upstream
    ``cascade_revoke`` performs the BFS; the orchestrator's responsibility
    is verification, NOT BFS reimplementation. ``revoke_lenient`` exists
    because not every caller has a precomputed ``expected_descendants``
    set (e.g. an ad-hoc CLI invocation); the orchestrator does not invent
    one (would be silent guessing per `rules/zero-tolerance.md` Rule 3).
    """

    def __init__(self, *, runtime: _RuntimeProtocol) -> None:
        self._runtime = runtime

    def revoke_and_verify(
        self,
        *,
        root_id: str,
        expected_descendants: frozenset[str],
    ) -> CascadeResult:
        """Call ``runtime.trust_cascade_revoke(root_id)``, build the
        structured ``CascadeResult``, and raise ``CascadeIncompleteError``
        when ``missing_descendants`` is non-empty.

        Always invokes the upstream cascade; the verification is the
        POST-call check. The runtime's revoked-set is normalized to
        ``frozenset[str]`` so callers cannot mutate the orchestrator's
        view of the result after return.
        """
        revoked = frozenset(self._runtime.trust_cascade_revoke(root_id))
        missing = expected_descendants - revoked
        result = CascadeResult(
            root_id=root_id,
            revoked_ids=revoked,
            expected_descendants=expected_descendants,
            missing_descendants=missing,
            complete=len(missing) == 0,
        )
        if not result.complete:
            raise CascadeIncompleteError(result)
        return result

    def revoke_lenient(self, *, root_id: str) -> CascadeResult:
        """Call ``runtime.trust_cascade_revoke(root_id)`` with NO
        expectation set; returns a ``CascadeResult`` with
        ``expected_descendants=frozenset()`` and ``complete=True``
        regardless of the actual revoked set.

        Used when the caller has no precomputed expectation (e.g. ad-hoc
        revocation from CLI). The lenient API NEVER raises
        ``CascadeIncompleteError`` — by definition the empty expectation
        set is always a subset of the revoked set.
        """
        revoked = frozenset(self._runtime.trust_cascade_revoke(root_id))
        return CascadeResult(
            root_id=root_id,
            revoked_ids=revoked,
            expected_descendants=frozenset(),
            missing_descendants=frozenset(),
            complete=True,
        )
