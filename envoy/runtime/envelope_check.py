# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Structural envelope-check engine (WS-6 S6a — structural slice).

Produces the byte-identical STRUCTURAL verdict for ``KailashRuntime.envelope_check``.
Both runtime adapters (``kailash-py`` reference + ``kailash-rs-bindings``) delegate
to the one pure function here, so cross-runtime byte-identity is a STRUCTURAL
guarantee — the two runtimes execute the same code path — rather than a property
tested into existence across two independent implementations (the shared-pure-
delegation pattern, journal/0019 Pattern 1; the same shape ``first_time_action_gate``
uses).

Scope (the S6a SPLIT — see workspaces/phase-02-distribution/journal/0021):

- This module owns the STRUCTURAL slice only: the N1 knowledge-filter field-allowlist
  gate, the N2 envelope-cache 5-property cache-key, and the N3 structural-reject
  classes (malformed/missing schema, type mismatch, dimension-out-of-range, unknown
  action verb, allowlist-shape violation). NONE of these dispatch the classifier
  ensemble (``expected_dispatch=False`` in the N3 corpus).
- The SEMANTIC slice — an action carrying ``content`` bytes that must be classified —
  is NOT handled here. It dispatches the classifier ensemble in shard S6d; the
  adapters route a semantic action to the S6d substrate gate. Partition predicate:
  :func:`is_semantic_action`.

Source of truth: ``specs/runtime-abstraction.md`` § Conformance vectors N1-N3 +
§ Contract partition (BET-6). Verdicts are plain dicts serialized through the
``envoy.envelope.canonical_bytes`` JCS-RFC8785 + NFC pipeline at scoring time
(``envoy.runtime.conformance.score_byte_identity``), so every field is deterministic
(sorted field lists, stable keys) and OS-portable (no path separators, no locale
assumptions).
"""

from __future__ import annotations

import re
from typing import Any

from envoy.envelope.canonical_bytes import canonical_bytes, content_hash

# Verdict schema identifier — bumped if the verdict shape changes (a shape change
# is a cross-runtime byte-identity break, so it is a deliberate, versioned event).
VERDICT_SCHEMA = "envoy.envelope-check-verdict/1.0"

# A well-formed envelope schema marker: ``envelope/<major>.<minor>``. The N3
# structural corpus rejects ``envelope/0.0-INVALID`` (trailing marker) and a
# missing ``schema`` key.
_SCHEMA_RE = re.compile(r"^envelope/\d+\.\d+$")

# Structural action-grammar: a present ``verb`` MUST be one of these. Absent verb
# is the default data-access read (N1/N2 actions carry no verb).
_KNOWN_ACTION_VERBS = frozenset(
    {"read", "list", "query", "write", "create", "update", "delete", "append"}
)

# Composition-rule depth bound (structural). ``dims.max_depth`` above this is an
# out-of-range structural reject (N3-struct-04 carries 999).
_MAX_ENVELOPE_DEPTH = 64

# The five envelope properties whose change MUST independently invalidate the
# envelope-check cache (N2). The cache key is a deterministic hash over exactly
# these five, read off the envelope (missing → ``None``, deterministic).
_CACHE_KEY_PROPERTIES = (
    "envelope_version",
    "algorithm_identifier",
    "classifier_ensemble_versions",
    "posture_level",
    "principal_genesis_id",
)

# Posture-ceiling ladder ordinals (N5). Lower = more restrictive; the effective
# posture is the floor (more-restrictive) of the envelope-declared ceiling and the
# principal-current posture. This 4-level ceiling ladder
# (OBSERVED<SUPERVISED<TRUSTED<AUTONOMOUS) is defined by the N5 conformance corpus
# (`specs/runtime-abstraction.md` § N5 + `tests/conformance/n4_n6_vectors.py`
# `_POSTURE_ORDER`) — it is DELIBERATELY distinct from the 5-level session-posture
# ladder in `specs/posture-ladder.md` (PSEUDO/TOOL/SUPERVISED/DELEGATING/AUTONOMOUS).
# A posture string outside this ceiling ladder yields `effective_posture=None`
# (fail-closed — never a permissive default). Also distinct from the N2 cache-key
# `posture_level` property (top-level) — the ceiling reads the envelope's
# `metadata.posture_level` (declared) against the action's `principal_posture`.
_POSTURE_CEILING_ORDER = {
    "OBSERVED": 0,
    "SUPERVISED": 1,
    "TRUSTED": 2,
    "AUTONOMOUS": 3,
}


def _effective_posture(envelope: Any, action: Any) -> str | None:
    """The N5 posture ceiling: ``min(envelope-declared, principal-current)`` by
    ladder ordinal, or ``None`` when either posture is absent / off-ladder.

    Declared ceiling = ``envelope.metadata.posture_level``; principal-current =
    ``action.principal_posture``. Returning ``None`` (not a default) when a posture
    is missing keeps the verdict honest — a check with no posture inputs (N1/N2/N3)
    carries ``effective_posture: null``, byte-identically on both runtimes.
    """
    env = envelope if isinstance(envelope, dict) else {}
    act = action if isinstance(action, dict) else {}
    meta = env.get("metadata")
    declared = meta.get("posture_level") if isinstance(meta, dict) else None
    principal = act.get("principal_posture")
    if (
        isinstance(declared, str)
        and isinstance(principal, str)
        and declared in _POSTURE_CEILING_ORDER
        and principal in _POSTURE_CEILING_ORDER
    ):
        return (
            declared
            if _POSTURE_CEILING_ORDER[declared] <= _POSTURE_CEILING_ORDER[principal]
            else principal
        )
    return None


def is_semantic_action(action: Any) -> bool:
    """True iff ``action`` is a SEMANTIC-class check (requires classifier dispatch).

    The partition is structural: a semantic check carries ``content`` (bytes) to be
    classified by the ensemble; a structural check does not. This is the predicate
    the adapters use to route semantic actions to the S6d classifier gate and
    structural actions to :func:`envelope_check_structural`. N3 semantic vectors all
    carry ``content`` bytes; N1/N2/N3-structural vectors never do.
    """
    return (
        isinstance(action, dict)
        and isinstance(action.get("content"), (bytes, bytearray))
    )


def _cache_key(envelope: Any) -> str:
    """Deterministic cache key over the five N2 invalidation properties.

    A change to ANY of the five flips this hash; everything else in the envelope is
    excluded so an unrelated edit does NOT spuriously invalidate. Computed through
    the canonical (JCS+NFC) pipeline so the key is byte-identical across runtimes.
    """
    env = envelope if isinstance(envelope, dict) else {}
    props = {k: env.get(k) for k in _CACHE_KEY_PROPERTIES}
    return content_hash(canonical_bytes(props))


def _structural_reject(
    reason: str, envelope: Any, action: Any, model: Any
) -> dict[str, Any]:
    """Build a structural-reject verdict (no fields admitted, classifier untouched)."""
    return {
        "schema": VERDICT_SCHEMA,
        "verdict_class": "structural",
        "outcome": "structural_reject",
        "model": model if isinstance(model, str) else None,
        "allowed_fields": [],
        "denied_fields": [],
        "reject_reason": reason,
        "cache_key": _cache_key(envelope),
        "effective_posture": _effective_posture(envelope, action),
    }


def _validate_structure(envelope: Any, action: Any) -> str | None:
    """Return the first structural-violation class, or ``None`` if well-formed.

    Order is fixed so the reject reason is deterministic across runtimes (the
    reason string is part of the byte-identical verdict). Covers the six N3
    structural classes.
    """
    if not isinstance(envelope, dict):
        return "malformed_envelope"
    if "schema" not in envelope:
        return "missing_schema"
    schema = envelope.get("schema")
    if not isinstance(schema, str) or not _SCHEMA_RE.match(schema):
        return "malformed_schema"
    # envelope_version, when present, MUST be an int (N3-struct-03 carries "three").
    if "envelope_version" in envelope and not isinstance(
        envelope["envelope_version"], int
    ):
        return "type_mismatch"
    # field_allowlist_per_model, when present, MUST be a map (N3-struct-06: a list).
    if "field_allowlist_per_model" in envelope and not isinstance(
        envelope["field_allowlist_per_model"], dict
    ):
        return "allowlist_shape"
    # dims.max_depth, when present, MUST be within the structural depth bound.
    dims = envelope.get("dims")
    if isinstance(dims, dict):
        max_depth = dims.get("max_depth")
        if isinstance(max_depth, int) and max_depth > _MAX_ENVELOPE_DEPTH:
            return "dimension_out_of_range"
    # A present action verb MUST be in the known grammar (N3-struct-05: TELEPORT).
    if isinstance(action, dict):
        verb = action.get("verb")
        if verb is not None and verb not in _KNOWN_ACTION_VERBS:
            return "unknown_action_verb"
        # A present `content` of the WRONG type fails closed (security review
        # MED-1). The adapters route bytes-`content` to the S6d classifier gate
        # via is_semantic_action; non-bytes `content` reaching the structural
        # engine signals an intended-but-malformed classification action and MUST
        # NOT receive a free structural allow — reject it like any type mismatch.
        if "content" in action and not isinstance(
            action["content"], (bytes, bytearray)
        ):
            return "content_type_mismatch"
    return None


def envelope_check_structural(envelope: Any, action: Any) -> dict[str, Any]:
    """The byte-identical STRUCTURAL envelope-check verdict.

    1. Structural validation — first violation (per :func:`_validate_structure`)
       yields a ``structural_reject`` verdict; the classifier is never consulted.
    2. Well-formed → the N1 knowledge-filter gate: the action's ``requested_fields``
       are partitioned against ``field_allowlist_per_model[model]`` into
       ``allowed_fields`` / ``denied_fields`` (the pre-retrieval over-fetch gate).
       ``outcome`` is ``allow`` (none denied), ``deny`` (none allowed), or
       ``partial_deny`` (mixed). Empty request → ``allow`` (vacuous).
    3. ``cache_key`` (N2) is attached to every verdict; a change to any of the five
       cache-key properties flips it, so a check against a mutated envelope yields a
       distinct verdict (cache invalidation), byte-identically on both runtimes.

    MUST NOT be called for a semantic action (:func:`is_semantic_action`) — the
    adapters route those to the S6d classifier gate before reaching here.
    """
    model = action.get("model") if isinstance(action, dict) else None

    reason = _validate_structure(envelope, action)
    if reason is not None:
        return _structural_reject(reason, envelope, action, model)

    allowlist = envelope.get("field_allowlist_per_model", {})
    requested = action.get("requested_fields", []) if isinstance(action, dict) else []
    requested = requested if isinstance(requested, list) else []
    allowed_for_model = allowlist.get(model, []) if isinstance(model, str) else []
    allowed_set = set(allowed_for_model) if isinstance(allowed_for_model, list) else set()

    allowed = sorted(f for f in requested if f in allowed_set)
    denied = sorted(f for f in requested if f not in allowed_set)

    if not denied:
        outcome = "allow"
    elif not allowed:
        outcome = "deny"
    else:
        outcome = "partial_deny"

    return {
        "schema": VERDICT_SCHEMA,
        "verdict_class": "structural",
        "outcome": outcome,
        "model": model if isinstance(model, str) else None,
        "allowed_fields": allowed,
        "denied_fields": denied,
        "reject_reason": None,
        "cache_key": _cache_key(envelope),
        "effective_posture": _effective_posture(envelope, action),
    }


__all__ = [
    "VERDICT_SCHEMA",
    "envelope_check_structural",
    "is_semantic_action",
]
