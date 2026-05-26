"""envoy.grant_moment.resolution — the three user-action ResolutionShapes.

Implements the three ``ResolutionShape`` classes per
`workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
§ 3 step 3, which map to the four ``decision`` values in
`specs/grant-moment.md` § ``GrantMomentResult`` schema:

    ResolutionShape           → spec decision discriminator(s)
    -------------------------------------------------------
    ApproveResolution         → "approve_once" | "approve_and_author"
    DeclineResolution         → "deny"
    ApproveWithModificationResolution → "modify"

The shape captures the user-action *class* (Approve / Decline / Approve-with-
modification); the wire-form ``decision`` discriminator records which of the
four spec-frozen verbs the runtime emits. ``ApproveResolution`` carries an
``author_payload`` flag — when set, the wire discriminator is
``"approve_and_author"`` and the result is enriched with a new constraint;
otherwise the discriminator is ``"approve_once"``.

These shapes are pure dataclasses; ZERO dependencies on other envoy packages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ResolutionShape",
    "ApproveResolution",
    "DeclineResolution",
    "ApproveWithModificationResolution",
]


@dataclass(frozen=True, slots=True)
class ResolutionShape:
    """Base ResolutionShape — never instantiated directly.

    Subclasses each carry the discriminator that drives the spec's
    ``decision`` field in ``GrantMomentResult``. The base class fixes the
    common ``decided_by_principal_genesis_id`` + ``co_signer_principal_genesis_id``
    fields (Phase 03 cross-principal dual-signed grants).
    """

    decided_by_principal_genesis_id: str
    co_signer_principal_genesis_id: str | None = None

    def to_decision(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError("ResolutionShape subclasses must override to_decision()")


@dataclass(frozen=True, slots=True)
class ApproveResolution(ResolutionShape):
    """User approved the request.

    When ``author_payload`` is None → wire discriminator ``"approve_once"``
    (one-off authorization, no constraint added to the envelope).

    When ``author_payload`` is a dict → wire discriminator
    ``"approve_and_author"`` and the payload carries the new constraint per
    spec § ``GrantMomentResult.author_payload`` shape:
    ``{"new_constraint": {...}, "novelty_check_passed": bool, "minimum_impact_passed": bool}``.
    """

    author_payload: dict[str, Any] | None = None

    def to_decision(self) -> str:
        return "approve_and_author" if self.author_payload is not None else "approve_once"


@dataclass(frozen=True, slots=True)
class DeclineResolution(ResolutionShape):
    """User declined — wire discriminator ``"deny"``.

    ``reason`` is a plain-language string captured for the Ledger entry per
    spec § "Phase A intent per specs/ledger.md §two-phase signing" — the
    decline is itself a signed event (signed only by the runtime, not the
    delegation_key, per spec § ``GrantMomentResult`` "Deny — signed Ledger
    entry only").
    """

    reason: str = ""

    def to_decision(self) -> str:
        return "deny"


@dataclass(frozen=True, slots=True)
class ApproveWithModificationResolution(ResolutionShape):
    """User approved with modified args — wire discriminator ``"modify"``.

    ``modify_payload`` carries the spec's
    ``{"new_args_canonical": {...}, "new_args_canonical_hash": "sha256:..."}``
    shape; the runtime re-canonicalizes the args before signing so the
    M3 signature scope covers the modification.
    """

    modify_payload: dict[str, Any] = field(default_factory=dict)

    def to_decision(self) -> str:
        return "modify"
