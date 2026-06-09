# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.conformance.scorer — byte-identity (hash-equality) scorer.

Source of truth: `specs/runtime-abstraction.md` § Contract partition (BET-6);
scorer design from
`workspaces/phase-02-distribution/01-analysis/01-research/01-ws1-runtime-pluggability.md`
§ "A conformance failure must answer THREE questions mechanically: which method,
which vector, which field".

A byte-identical conformance failure MUST localize the divergence — a bare
`assert a == b` on a 4 KB canonical blob is unactionable. `score_byte_identity`
canonicalizes each side, hashes both, and on hash-mismatch walks the canonical
bytes to emit BOTH sides + the first differing byte offset + the JSON path of the
divergence (e.g. ``entries[3].timestamp``). The JSON path is the one-line fix
instruction ("producer microsecond-padded, rs truncated").

Canonicalization here is the SCORER's deterministic serialization (sorted keys,
no whitespace, UTF-8) — it is NOT the runtime's JCS-RFC8785 canonical form (that
is `envelope_canonical_form`, a method UNDER test). The scorer canonicalizes the
two runtimes' *outputs* so the comparison is shape-stable; if both runtimes return
already-`bytes` canonical output (E1), the scorer hashes those bytes directly.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any


@dataclasses.dataclass(frozen=True)
class ByteIdentityMismatch:
    """Field-localized description of a byte-identity divergence.

    - ``json_path`` — dotted/indexed path to the first differing element
      (``entries[3].timestamp``), or ``"<root>"`` when the values differ at the
      top level or have incompatible shapes.
    - ``byte_offset`` — first differing byte offset in the canonical serialization
      of the two sides (``-1`` if one side is a strict prefix of the other —
      then ``byte_offset`` is the length of the shorter side).
    - ``left_canonical`` / ``right_canonical`` — the canonical serializations of
      each side (truncated for display by the harness, never here).
    """

    json_path: str
    byte_offset: int
    left_canonical: bytes
    right_canonical: bytes


@dataclasses.dataclass(frozen=True)
class ScoreResult:
    """Outcome of one byte-identity scoring.

    - ``passed`` — hashes equal.
    - ``left_hash`` / ``right_hash`` — sha256 hex of each canonical side.
    - ``mismatch`` — populated iff ``not passed``: the field-localized diff.
    """

    passed: bool
    left_hash: str
    right_hash: str
    mismatch: ByteIdentityMismatch | None = None


def _canonicalize(value: Any) -> bytes:
    """Deterministic, shape-stable serialization of a scorer input.

    `bytes`/`bytearray` pass through unchanged (the runtime already produced
    canonical bytes, e.g. E1). Everything else is JSON-serialized with sorted
    keys, compact separators, and `default=str` so non-JSON scalars (Decimal,
    datetime, sets rendered as sorted lists) serialize deterministically.
    """
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, (set, frozenset)):
        # SET-equality (E3 cascade-revoke): order-insensitive — sort the members'
        # canonical forms so two runtimes that return the same set in different
        # order hash identically.
        members = sorted(_canonicalize(m) for m in value)
        return b"[" + b",".join(members) + b"]"
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    """Return the sha256 hex of ``value``'s canonical serialization."""
    return hashlib.sha256(_canonicalize(value)).hexdigest()


def _first_differing_offset(left: bytes, right: bytes) -> int:
    """First byte offset at which ``left`` and ``right`` differ.

    Returns the length of the shorter side when one is a strict prefix of the
    other (the divergence is "one side is longer").
    """
    limit = min(len(left), len(right))
    for i in range(limit):
        if left[i] != right[i]:
            return i
    return limit


def _localize_json_path(left: Any, right: Any, path: str = "<root>") -> str:
    """Walk two decoded structures to the first divergent JSON path.

    Best-effort: returns the deepest path where the two structures first differ.
    Falls back to ``path`` when the structures have incompatible types/shapes.
    """
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            base = "<root>" if path == "<root>" else path
            child = f"{key}" if base == "<root>" else f"{base}.{key}"
            if key not in left or key not in right:
                return child
            if _canonicalize(left[key]) != _canonicalize(right[key]):
                return _localize_json_path(left[key], right[key], child)
        return path
    if isinstance(left, list) and isinstance(right, list):
        for idx in range(min(len(left), len(right))):
            child = f"{path}[{idx}]" if path != "<root>" else f"[{idx}]"
            if _canonicalize(left[idx]) != _canonicalize(right[idx]):
                return _localize_json_path(left[idx], right[idx], child)
        if len(left) != len(right):
            return f"{path}[{min(len(left), len(right))}]"
        return path
    return path


def score_byte_identity(left: Any, right: Any) -> ScoreResult:
    """Score two runtime outputs for byte-identity.

    Returns a `ScoreResult`; on mismatch the `mismatch` field carries the
    field-localized diff (JSON path + first differing byte offset + both
    canonical sides) so the failure names *which field* diverged — NOT a bare
    `assert a == b`.
    """
    left_bytes = _canonicalize(left)
    right_bytes = _canonicalize(right)
    left_hash = hashlib.sha256(left_bytes).hexdigest()
    right_hash = hashlib.sha256(right_bytes).hexdigest()

    if left_hash == right_hash:
        return ScoreResult(passed=True, left_hash=left_hash, right_hash=right_hash)

    # Localize. Prefer a JSON-path walk on the decoded structures; fall back to
    # raw-byte offset when either side is opaque bytes.
    json_path = "<root>"
    if not isinstance(left, (bytes, bytearray)) and not isinstance(right, (bytes, bytearray)):
        try:
            json_path = _localize_json_path(left, right)
        except (TypeError, ValueError):
            json_path = "<root>"

    return ScoreResult(
        passed=False,
        left_hash=left_hash,
        right_hash=right_hash,
        mismatch=ByteIdentityMismatch(
            json_path=json_path,
            byte_offset=_first_differing_offset(left_bytes, right_bytes),
            left_canonical=left_bytes,
            right_canonical=right_bytes,
        ),
    )


__all__ = [
    "ByteIdentityMismatch",
    "ScoreResult",
    "canonical_hash",
    "score_byte_identity",
]
