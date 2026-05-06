"""JCS+NFC canonicalization pipeline.

Implements `specs/envelope-model.md` § Algorithms § "Canonical JSON (§14.1)":
- RFC 8785 JCS (JSON Canonicalization Scheme).
- Unicode NFC normalization on all string values.
- Integer microdollars (already enforced by FinancialDimension type).
- Lexicographic key ordering throughout (RFC 8785 mandate).

Cross-runtime byte-identity per BET-6 — the same envelope content compiled by
the kailash-py runtime and the kailash-rs binding (Phase 02) must produce
byte-identical canonical_bytes + content_hash.

This module is pure-function; no side effects, no I/O.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any


def _nfc_normalize(value: Any) -> Any:
    """Recursively NFC-normalize every string in a JSON-able structure.

    NFC = Normalization Form Canonical Composition (Unicode TR15). Required
    so envelope authoring on different OSes (macOS HFS+ uses NFD by default)
    produces byte-identical canonical bytes.
    """
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {_nfc_normalize(k): _nfc_normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_nfc_normalize(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_nfc_normalize(v) for v in value)
    return value


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Produce JCS-RFC8785 canonical bytes for a JSON-able dict.

    Pipeline:
    1. NFC-normalize every string value (recursive).
    2. JSON-serialize with `sort_keys=True` + `separators=(",", ":")` +
       `ensure_ascii=False` to match RFC 8785's lexicographic-key + no-whitespace +
       UTF-8-encoded output.
    3. UTF-8 encode.

    The combination of `sort_keys=True` + `separators=(",", ":")` matches
    RFC 8785's canonical form for dicts; numerics produced by Python's
    `json.dumps` match RFC 8785 for the integer + simple-float cases this
    spec actually uses (integer microdollars + bounded floats in
    classifier weights).

    For full RFC 8785 conformance on the rare cases where Python's `json`
    diverges (e.g., `0.0` vs `-0.0`, exponent formatting on large floats),
    Phase 02 swaps in a JCS library bound by the cross-SDK fixture battery
    per `specs/envelope-model.md` § Test location T-005 + T-013.
    """
    normalized = _nfc_normalize(payload)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")


def content_hash(canonical: bytes) -> str:
    """SHA-256 hex digest over canonical bytes.

    The single-point hash production at compile time means the Trust store
    (`DelegationRecord.effective_envelope_hash`), Ledger (`envelope_edit`
    entries), and SubsetProof verifier (`parent_envelope_hash` /
    `sub_envelope_hash`) all agree on the same canonical bytes — no drift
    surface between consumers per shard 4 § 3 step 5.
    """
    return hashlib.sha256(canonical).hexdigest()


def _json_default(obj: Any) -> Any:
    """Fallback serializer for non-stdlib JSON types we use in the schema.

    - Enum subclasses (ConfidentialityLevel) → their `.value`.
    - Frozen dataclasses → `__dict__` (handled by caller; this fallback
      exists for defensive reasons only — the caller is expected to convert
      dataclasses to plain dicts before calling canonical_bytes).
    """
    import enum
    from dataclasses import asdict, is_dataclass

    if isinstance(obj, enum.Enum):
        return obj.value
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"canonical_bytes: unhashable type {type(obj).__name__}")
