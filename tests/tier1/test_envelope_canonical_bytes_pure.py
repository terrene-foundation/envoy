"""Tier 1 unit tests for envoy.envelope.canonical_bytes.

Per `rules/testing.md` § Tier 1: mocking allowed; <1s per test. Pure-function
surface — no infrastructure dependency.

Covers `specs/envelope-model.md` § Algorithms § "Canonical JSON" invariants:
- JCS lexicographic key ordering (RFC 8785).
- NFC normalization (TR15) on string values.
- SHA-256 hex digest correctness.
- Cross-OS byte-identity (NFC defends against macOS HFS+ NFD storage).
"""

from __future__ import annotations

import hashlib
import unicodedata

import pytest

from envoy.envelope.canonical_bytes import canonical_bytes, content_hash


class TestCanonicalBytesKeyOrdering:
    """JCS RFC 8785 mandates lexicographic key ordering at every dict level."""

    def test_key_order_is_lexicographic_at_top_level(self) -> None:
        assert canonical_bytes({"b": 1, "a": 2}) == canonical_bytes({"a": 2, "b": 1})
        assert canonical_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'

    def test_key_order_is_lexicographic_in_nested_dicts(self) -> None:
        a = {"outer": {"z": 1, "a": 2}}
        b = {"outer": {"a": 2, "z": 1}}
        assert canonical_bytes(a) == canonical_bytes(b)

    def test_key_order_is_recursive_through_lists_of_dicts(self) -> None:
        a = {"items": [{"y": 1, "x": 2}, {"b": 3, "a": 4}]}
        b = {"items": [{"x": 2, "y": 1}, {"a": 4, "b": 3}]}
        assert canonical_bytes(a) == canonical_bytes(b)


class TestCanonicalBytesNfcNormalization:
    """NFC normalization defends cross-OS byte-identity (HFS+ uses NFD by default)."""

    def test_nfc_normalizes_combining_diacritics(self) -> None:
        # "café" — composed (NFC: 4 codepoints) vs decomposed (NFD: 5 codepoints)
        nfc = "café"  # é as single codepoint U+00E9
        nfd = "café"  # e + combining acute U+0301
        assert nfd != nfc
        assert unicodedata.normalize("NFC", nfd) == nfc
        # canonical_bytes MUST collapse both to identical bytes
        assert canonical_bytes({"name": nfc}) == canonical_bytes({"name": nfd})

    def test_nfc_normalizes_keys_too(self) -> None:
        nfc_key = {"café": "x"}
        nfd_key = {"café": "x"}
        assert canonical_bytes(nfc_key) == canonical_bytes(nfd_key)


class TestCanonicalBytesSeparators:
    """JCS forbids whitespace between tokens (most-compact form)."""

    def test_no_whitespace_between_tokens(self) -> None:
        out = canonical_bytes({"a": 1, "b": [2, 3], "c": {"d": 4}})
        assert b" " not in out
        assert out == b'{"a":1,"b":[2,3],"c":{"d":4}}'

    def test_unicode_passes_through_as_utf8_not_escaped(self) -> None:
        out = canonical_bytes({"name": "café"})
        # ensure_ascii=False per RFC 8785 — UTF-8 bytes, not \uXXXX escapes
        assert "café".encode() in out


class TestContentHash:
    def test_content_hash_is_sha256_hex_of_canonical_bytes(self) -> None:
        cb = canonical_bytes({"a": 1})
        assert content_hash(cb) == hashlib.sha256(cb).hexdigest()

    def test_content_hash_is_64_hex_chars(self) -> None:
        h = content_hash(canonical_bytes({"x": 1}))
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_content_hash_byte_identity_across_input_orderings(self) -> None:
        # Same content compiled from two different input dict orderings MUST
        # produce identical hashes — the cross-runtime parity invariant.
        h1 = content_hash(canonical_bytes({"b": 1, "a": 2, "c": [{"y": 3, "x": 4}]}))
        h2 = content_hash(canonical_bytes({"c": [{"x": 4, "y": 3}], "a": 2, "b": 1}))
        assert h1 == h2


class TestCanonicalBytesEdgeCases:
    def test_empty_dict(self) -> None:
        assert canonical_bytes({}) == b"{}"

    def test_empty_list_in_dict(self) -> None:
        assert canonical_bytes({"x": []}) == b'{"x":[]}'

    def test_nested_empty(self) -> None:
        assert canonical_bytes({"x": {}, "y": []}) == b'{"x":{},"y":[]}'

    def test_integers_serialize_without_decimals(self) -> None:
        # Integer microdollars per spec — never as floats with .0 suffix
        out = canonical_bytes({"micro": 1500000})
        assert out == b'{"micro":1500000}'

    def test_unsupported_type_raises_type_error(self) -> None:
        class CustomThing:
            pass

        with pytest.raises(TypeError):
            canonical_bytes({"x": CustomThing()})
