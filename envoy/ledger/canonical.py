"""Canonical JSON encoding for Ledger entry hashing.

Per `specs/ledger.md` BET-6 (head-commitment byte identity) + shard 6 § 4
sketch (`workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md`
lines 130 + 226-228) + the kailash-py byte-pinning closures #757/#756/#731:

The canonical-JSON byte vector is the cross-SDK byte-identity contract.
Every Ledger entry's `entry_id = sha256(canonical_dumps(envelope))` —
without byte-vector pinning, a Python emitter and a Rust verifier of the
same logical entry would produce different `entry_id` values silently.

Phase 01 invariants (the 7 invariants in T-01-17's capacity check):

1. **Sorted keys** — every dict key sorts ASCII-lexicographically (matches
   `json.dumps(sort_keys=True)` on the recursive walk).
2. **No insignificant whitespace** — `separators=(",", ":")`; matches the
   spec's "no insignificant whitespace" clause.
3. **Unicode NFC normalization** (#757) — every string value normalized
   via `unicodedata.normalize("NFC", s)` BEFORE encoding. Without this,
   `é` (NFC, single codepoint U+00E9) and `é` (NFD, U+0065 + U+0301)
   produce different byte vectors despite being the same logical string.
4. **`ensure_ascii=False`** (#756) — emit raw UTF-8 bytes, NOT `\\u00XX`
   escapes. Matches the kailash-py emitter so a Rust verifier reads the
   same bytes Python wrote.
5. **Microsecond-padded ISO 8601 timestamps** (#731) — every datetime
   value padded to `YYYY-MM-DDTHH:MM:SS.NNNNNNZ` (6-digit microsecond
   precision). Without padding, `2026-05-03T10:00:00Z` and
   `2026-05-03T10:00:00.000000Z` produce different bytes despite being
   the same instant.
6. **Numeric format pinning** — Python's `json.dumps` emits `1` for
   `int(1)`, `1.0` for `float(1.0)`, and `true/false/null` for booleans
   and None. We rely on this default; floats are NOT used in Ledger
   entries (all numeric fields are `int` per spec).
7. **No mutation of input** — `canonical_dumps` does not mutate the input
   dict; the recursive transform produces a new normalized structure.

Pre-encode transform (recursive):
- `str` → NFC-normalize
- `datetime` → microsecond-padded ISO 8601 with explicit `Z` suffix (UTC)
- `date` → ISO 8601 (`YYYY-MM-DD`)
- `bytes` → hex-encoded str
- `dict` → recursive transform on values, sorted keys
- `list` / `tuple` → recursive transform on elements
- `int` / `float` / `bool` / `None` → unchanged

Phase 02+ (out of T-01-17 scope):

- Per-region HKDF-derived per-entry keys (specs/ledger.md § Per-entry encryption)
- `Decimal` support if Phase 02 introduces money values into entry content
- Cross-language reference test corpus pinning bytes byte-for-byte against
  a kailash-rs verifier
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Any

# Phase 01 microsecond-padded ISO 8601 UTC shape per #731 byte pinning.
# Exactly 27 chars: YYYY-MM-DDTHH:MM:SS.NNNNNNZ.
_ISO_8601_MICRO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def is_canonical_timestamp(value: str) -> bool:
    """Return True if `value` matches the Phase 01 27-char microsecond-padded
    ISO 8601 UTC shape (`YYYY-MM-DDTHH:MM:SS.NNNNNNZ`).

    Public predicate so producer-side validation in
    `EntryEnvelope.__post_init__`, `HeadCommitment.__post_init__`, and
    `HaltedByRollbackRecord.__post_init__` all share the same definition.
    A pre-formatted timestamp string passing `canonical_dumps` unchanged
    MUST already match this shape — otherwise the canonical bytes silently
    violate the cross-SDK BET-6 byte-identity contract.
    """
    return isinstance(value, str) and bool(_ISO_8601_MICRO_UTC_RE.match(value))


def canonical_dumps(obj: Any) -> bytes:
    """Encode `obj` to a deterministic UTF-8 byte vector.

    Returns: bytes (UTF-8 encoded canonical JSON; no insignificant whitespace,
    sorted dict keys, NFC-normalized strings, microsecond-padded timestamps).

    Raises: TypeError on values whose canonical encoding is not pinned by
    this Phase 01 module (e.g., float, set, custom dataclass without
    `to_dict()`). Per `rules/zero-tolerance.md` Rule 3 — silent fallback
    is BLOCKED; unsupported types fail loudly so the caller normalizes
    them at the producer boundary.
    """
    normalized = _normalize(obj)
    text = json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,  # #756 — emit raw UTF-8, not \\u escapes
        separators=(",", ":"),  # no insignificant whitespace
        allow_nan=False,  # NaN / Inf produce non-portable bytes
    )
    return text.encode("utf-8")


def _normalize(value: Any) -> Any:
    """Recursive pre-encode transform; pure (no mutation of input)."""
    # Booleans must precede int (bool subclasses int in Python).
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        # #757 — NFC-normalize every string before encoding.
        return unicodedata.normalize("NFC", value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # Phase 01 entries do NOT use float (all numeric fields are int per
        # spec). Reject loudly rather than silently encoding non-portable
        # IEEE-754 representations.
        raise TypeError(
            "canonical_dumps does not accept float values — Phase 01 Ledger "
            "uses int-only numeric fields per specs/ledger.md. Use int "
            "(microdollars / microseconds) at the producer boundary."
        )
    if isinstance(value, datetime):
        return _format_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        # NFC-normalize dict KEYS too — without this, a key like `é` (NFC,
        # U+00E9) and `é` (NFD, U+0065+U+0301) would sort differently under
        # `json.dumps(sort_keys=True)` (raw codepoint sort), producing
        # different canonical bytes for the same logical entry. Phase 01
        # narrow scope: envelope keys are ASCII so the gap doesn't bite
        # NOW, but Phase 02+ entries whose `content: dict` carries
        # user-supplied non-ASCII keys would silently violate cross-SDK
        # byte-identity. Closing the gap structurally per security
        # review H-1.
        # Non-str keys are rejected loudly (JSON requires string keys;
        # silent str() coercion would mask producer bugs).
        normalized: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(
                    f"canonical_dumps requires str dict keys (got "
                    f"{type(k).__name__!r}); JSON does not allow non-string "
                    "keys."
                )
            normalized[unicodedata.normalize("NFC", k)] = _normalize(v)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    raise TypeError(
        f"canonical_dumps received unsupported type {type(value).__name__!r} — "
        "the Ledger byte-pinning contract requires a deterministic encoding "
        "for every type. Add a producer-side normalization or extend "
        "envoy.ledger.canonical._normalize."
    )


def _format_timestamp(dt: datetime) -> str:
    """Format `dt` as microsecond-padded ISO 8601 in UTC, suffix `Z`.

    Per #731 byte pinning: every Ledger timestamp MUST be exactly 27 chars
    `YYYY-MM-DDTHH:MM:SS.NNNNNNZ`. This is the cross-SDK contract — without
    the explicit microsecond padding, Python's default would emit
    `2026-05-03T10:00:00Z` for whole-second instants and
    `2026-05-03T10:00:00.123Z` for 3-digit truncation, producing 3
    different byte vectors for the same logical instant.

    Naive datetimes (no tzinfo) are REJECTED loudly per
    `rules/zero-tolerance.md` Rule 3 (no silent fallback). Silent UTC
    coercion would mask producer bugs where the runtime forgot to set
    tzinfo and inadvertently encodes a local-time value as if it were UTC.
    Caller MUST pass tzinfo-aware datetime; `datetime.now(tz=timezone.utc)`
    is the canonical producer pattern.
    """
    if dt.tzinfo is None:
        raise TypeError(
            "canonical_dumps does not accept naive datetime (no tzinfo) — "
            "pass a timezone-aware UTC datetime at the producer boundary "
            "(e.g., datetime.now(tz=timezone.utc)). Silent local-as-UTC "
            "coercion would mask producer-side timezone bugs."
        )
    dt = dt.astimezone(timezone.utc)
    # `isoformat(timespec="microseconds")` produces 6-digit microsecond
    # padding. We strip the `+00:00` UTC offset and replace with literal `Z`
    # to match the kailash-py / kailash-rs emitter.
    iso = dt.isoformat(timespec="microseconds")
    if iso.endswith("+00:00"):
        iso = iso[:-6] + "Z"
    elif not iso.endswith("Z"):
        # Defensive — shouldn't happen after astimezone(utc).
        iso = iso + "Z"
    return iso


class CanonicalJsonEncoder(json.JSONEncoder):
    """Streaming variant of canonical_dumps for use with `json.dump` (file IO).

    Phase 01 narrow scope: this encoder applies the same Phase 01
    invariants as `canonical_dumps()` but supports incremental file
    writing. Callers typically prefer `canonical_dumps()` for entry hashing
    (which produces a complete byte vector); the streaming encoder is for
    bulk export bundles (T-01-18 `EnvoyLedger.export()`).

    Symmetric with `canonical_dumps`: float is rejected loudly (the
    `default()` method raises TypeError); NFC normalization on dict KEYS
    is applied via the same `_normalize` pre-pass; naive datetime is
    rejected (via `_format_timestamp`).
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("sort_keys", True)
        kwargs.setdefault("ensure_ascii", False)
        kwargs.setdefault("separators", (",", ":"))
        kwargs.setdefault("allow_nan", False)
        super().__init__(**kwargs)

    def default(self, o: Any) -> Any:  # type: ignore[override]
        # Symmetric with canonical_dumps: float is rejected loudly per
        # Phase 01 int-only contract.
        if isinstance(o, float):
            raise TypeError(
                "CanonicalJsonEncoder does not accept float values — Phase 01 "
                "Ledger uses int-only numeric fields per specs/ledger.md."
            )
        if isinstance(o, datetime):
            return _format_timestamp(o)
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, bytes):
            return o.hex()
        return super().default(o)

    def encode(self, o: Any) -> str:  # type: ignore[override]
        # Pre-normalize so NFC + datetime + bytes get the same treatment
        # as canonical_dumps (json.JSONEncoder.encode bypasses default()
        # for natively-encodable types like str).
        return super().encode(_normalize(o))


__all__ = ["CanonicalJsonEncoder", "canonical_dumps", "is_canonical_timestamp"]
