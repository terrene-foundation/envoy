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

import json
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ResolutionShape",
    "ApproveResolution",
    "DeclineResolution",
    "ApproveWithModificationResolution",
    "resolution_to_json",
    "resolution_from_json",
    "resolution_signing_payload",
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


# Cross-process resolution codec (S4r). A ``ResolutionShape`` cannot be
# ``set_result``-ed across two OS processes; the cross-process rendezvous
# serializes the shape to canonical JSON, the answering process writes it into
# the pending-grant sub-store's ``resolution_json`` column, and the requesting
# process's poll reconstructs the exact same shape. The codec is the
# wire-format bridge — the ``shape`` discriminator names which of the three
# ResolutionShape subclasses to reconstruct, so the polling process recovers
# the SAME concrete type the answering process signed.
_SHAPE_APPROVE = "approve"
_SHAPE_DECLINE = "decline"
_SHAPE_MODIFY = "modify"


def resolution_to_json(resolution: ResolutionShape) -> str:
    """Serialize a ``ResolutionShape`` to canonical JSON for the sub-store.

    Sorted keys + no whitespace so the stored bytes are deterministic
    (cross-process byte-parity, same discipline as the GrantMomentResult wire
    form). The ``shape`` discriminator preserves the concrete subclass so
    ``resolution_from_json`` reconstructs the exact type — an Approve does not
    silently round-trip into a Decline.
    """
    base: dict[str, Any] = {
        "decided_by_principal_genesis_id": resolution.decided_by_principal_genesis_id,
        "co_signer_principal_genesis_id": resolution.co_signer_principal_genesis_id,
    }
    if isinstance(resolution, ApproveWithModificationResolution):
        # ApproveWithModification is a subclass of ApproveResolution-sibling
        # branch; check it FIRST so the modify shape is not mis-tagged.
        base["shape"] = _SHAPE_MODIFY
        base["modify_payload"] = resolution.modify_payload
    elif isinstance(resolution, ApproveResolution):
        base["shape"] = _SHAPE_APPROVE
        base["author_payload"] = resolution.author_payload
    elif isinstance(resolution, DeclineResolution):
        base["shape"] = _SHAPE_DECLINE
        base["reason"] = resolution.reason
    else:  # pragma: no cover - defensive; base class is never instantiated
        raise ValueError(f"unknown ResolutionShape subclass: {type(resolution).__name__}")
    return json.dumps(base, sort_keys=True, separators=(",", ":"))


def resolution_from_json(blob: str) -> ResolutionShape:
    """Reconstruct the exact ``ResolutionShape`` subclass from its JSON form.

    Inverse of ``resolution_to_json``. Fail-loud on an unknown / missing
    discriminator so a corrupt resolution row surfaces at the read boundary
    rather than mis-reconstructing into the wrong decision class.
    """
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError(f"resolution blob must be a JSON object (got {type(data).__name__})")
    shape = data.get("shape")
    if "decided_by_principal_genesis_id" not in data:
        # Fail loud with the module's intended ValueError taxonomy (matching the
        # unknown-shape branch below) rather than a bare KeyError — a resolution
        # blob missing its required decider field is corrupt, surface it clearly.
        raise ValueError("resolution blob missing decided_by_principal_genesis_id")
    decided_by = data["decided_by_principal_genesis_id"]
    co_signer = data.get("co_signer_principal_genesis_id")
    if shape == _SHAPE_APPROVE:
        return ApproveResolution(
            decided_by_principal_genesis_id=decided_by,
            co_signer_principal_genesis_id=co_signer,
            author_payload=data.get("author_payload"),
        )
    if shape == _SHAPE_DECLINE:
        return DeclineResolution(
            decided_by_principal_genesis_id=decided_by,
            co_signer_principal_genesis_id=co_signer,
            reason=data.get("reason", ""),
        )
    if shape == _SHAPE_MODIFY:
        return ApproveWithModificationResolution(
            decided_by_principal_genesis_id=decided_by,
            co_signer_principal_genesis_id=co_signer,
            modify_payload=data.get("modify_payload", {}),
        )
    raise ValueError(f"resolution blob has unknown shape discriminator: {shape!r}")


def resolution_signing_payload(request_id: str, resolution_json: str) -> str:
    """Canonical signing input the cross-process resolution signature covers (S4r).

    Binds the ``request_id`` to the serialized resolution so the detached
    signature authenticates BOTH which decision was made AND which pending row
    it answers. The ``request_id`` binding defeats replay: a signature captured
    for one request cannot be lifted onto a different pending row whose shape
    happens to match. Sorted keys + no whitespace so the signer (the answering
    process, in ``SessionRouter.resolve_pending_grant``) and the verifier (the
    requesting process's poll, via ``SessionRouter.verify_resolution_signature``)
    produce byte-identical input. ``resolution_json`` is already the canonical
    ``resolution_to_json`` form, embedded here as an opaque string. Returned as a
    ``str`` (not bytes) to match the key manager's ``sign_with_key(key_id, str)``
    / ``verify(str, sig, pubkey)`` surface; the manager encodes it identically on
    both halves.
    """
    return json.dumps(
        {"request_id": request_id, "resolution": resolution_json},
        sort_keys=True,
        separators=(",", ":"),
    )
