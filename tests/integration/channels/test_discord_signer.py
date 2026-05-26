"""Tier-2 tests for DiscordSigner Ed25519 verification.

Tests use a real Ed25519 keypair generated in-process (no mocking of
``cryptography`` internals) per ``rules/testing.md`` Tier 2 guidance
(real infrastructure, no ``@patch`` / ``MagicMock``).

Coverage:
  - Valid signature: returns True.
  - Bad signature (single bit flip): returns False.
  - Wrong public key: returns False.
  - Missing headers: returns False for each missing header individually.
  - Malformed hex in signature header: returns False (no exception leak).
  - Empty body: signature over empty body still verifies correctly.
  - Exception containment: no exceptions leak to the caller.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from envoy.channels._discord_signer import DiscordSigner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Generate a fresh Ed25519 keypair for this test module."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture(scope="module")
def hex_public_key(keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey]) -> str:
    """Hex-encoded public key ready for DiscordSigner construction."""
    _, public_key = keypair
    return public_key.public_bytes_raw().hex()


@pytest.fixture(scope="module")
def signer(hex_public_key: str) -> DiscordSigner:
    """DiscordSigner constructed with the module-level public key."""
    return DiscordSigner(hex_public_key)


def _sign(
    private_key: Ed25519PrivateKey,
    timestamp: str,
    body: bytes,
) -> dict[str, str]:
    """Helper: produce valid Discord signature headers for a body."""
    message = timestamp.encode() + body
    sig_bytes = private_key.sign(message)
    return {
        "X-Signature-Ed25519": sig_bytes.hex(),
        "X-Signature-Timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_signature_returns_true(
    keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey],
    signer: DiscordSigner,
) -> None:
    private_key, _ = keypair
    body = b'{"type": 1}'
    timestamp = "1700000000"
    headers = _sign(private_key, timestamp, body)
    assert signer.verify(headers, body) is True


def test_valid_signature_empty_body(
    keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey],
    signer: DiscordSigner,
) -> None:
    private_key, _ = keypair
    body = b""
    timestamp = "1700000001"
    headers = _sign(private_key, timestamp, body)
    assert signer.verify(headers, body) is True


def test_valid_signature_header_keys_case_insensitive(
    keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey],
    signer: DiscordSigner,
) -> None:
    """Verify the signer handles mixed-case header keys per HTTP spec."""
    private_key, _ = keypair
    body = b'{"type": 2}'
    timestamp = "1700000002"
    headers = _sign(private_key, timestamp, body)
    # Uppercase the header keys.
    upper_headers = {k.upper(): v for k, v in headers.items()}
    assert signer.verify(upper_headers, body) is True


# ---------------------------------------------------------------------------
# Invalid signature
# ---------------------------------------------------------------------------


def test_bit_flip_returns_false(
    keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey],
    signer: DiscordSigner,
) -> None:
    private_key, _ = keypair
    body = b'{"type": 1}'
    timestamp = "1700000003"
    headers = _sign(private_key, timestamp, body)
    # Flip the first nibble of the hex signature.
    sig_hex = headers["X-Signature-Ed25519"]
    flipped = format(int(sig_hex[0], 16) ^ 0xF, "x") + sig_hex[1:]
    headers["X-Signature-Ed25519"] = flipped
    assert signer.verify(headers, body) is False


def test_modified_body_returns_false(
    keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey],
    signer: DiscordSigner,
) -> None:
    private_key, _ = keypair
    body = b'{"type": 1}'
    timestamp = "1700000004"
    headers = _sign(private_key, timestamp, body)
    # Deliver a different body — signature mismatch.
    assert signer.verify(headers, b'{"type": 2}') is False


def test_modified_timestamp_returns_false(
    keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey],
    signer: DiscordSigner,
) -> None:
    private_key, _ = keypair
    body = b'{"type": 1}'
    timestamp = "1700000005"
    headers = _sign(private_key, timestamp, body)
    # Change the timestamp in the header — message to verify changes.
    headers["X-Signature-Timestamp"] = "9999999999"
    assert signer.verify(headers, body) is False


def test_wrong_public_key_returns_false(
    keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey],
) -> None:
    private_key, _ = keypair
    body = b'{"type": 1}'
    timestamp = "1700000006"
    headers = _sign(private_key, timestamp, body)
    # Build a signer with a DIFFERENT public key.
    other_key = Ed25519PrivateKey.generate()
    other_hex = other_key.public_key().public_bytes_raw().hex()
    wrong_signer = DiscordSigner(other_hex)
    assert wrong_signer.verify(headers, body) is False


# ---------------------------------------------------------------------------
# Missing headers
# ---------------------------------------------------------------------------


def test_missing_signature_header_returns_false(
    keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey],
    signer: DiscordSigner,
) -> None:
    private_key, _ = keypair
    body = b'{"type": 1}'
    timestamp = "1700000007"
    headers = _sign(private_key, timestamp, body)
    del headers["X-Signature-Ed25519"]
    assert signer.verify(headers, body) is False


def test_missing_timestamp_header_returns_false(
    keypair: tuple[Ed25519PrivateKey, Ed25519PublicKey],
    signer: DiscordSigner,
) -> None:
    private_key, _ = keypair
    body = b'{"type": 1}'
    timestamp = "1700000008"
    headers = _sign(private_key, timestamp, body)
    del headers["X-Signature-Timestamp"]
    assert signer.verify(headers, body) is False


def test_empty_headers_returns_false(signer: DiscordSigner) -> None:
    assert signer.verify({}, b'{"type": 1}') is False


# ---------------------------------------------------------------------------
# Malformed input — no exception leakage
# ---------------------------------------------------------------------------


def test_malformed_hex_signature_returns_false(signer: DiscordSigner) -> None:
    """Non-hex data in the signature header MUST return False, not raise."""
    headers = {
        "X-Signature-Ed25519": "NOT-HEX!!!",
        "X-Signature-Timestamp": "1700000009",
    }
    result = signer.verify(headers, b'{"type": 1}')
    assert result is False


def test_truncated_signature_returns_false(signer: DiscordSigner) -> None:
    """Signature that's only 32 bytes (not 64) returns False without crash."""
    headers = {
        "X-Signature-Ed25519": "aabbcc" * 5,  # 30 hex chars = 15 bytes < 64 required
        "X-Signature-Timestamp": "1700000010",
    }
    result = signer.verify(headers, b"test")
    assert result is False


def test_verify_never_raises(signer: DiscordSigner) -> None:
    """Verify that any pathological input silently returns False."""
    pathological_inputs: list[tuple[dict[str, str], bytes]] = [
        ({}, b""),
        ({"x-signature-ed25519": "", "x-signature-timestamp": ""}, b""),
        ({"x-signature-ed25519": "\x00\xff", "x-signature-timestamp": "ts"}, b"\x00"),
        ({"X-Signature-Ed25519": "gg", "X-Signature-Timestamp": "ts"}, b"body"),
    ]
    for headers, body in pathological_inputs:
        result = signer.verify(headers, body)
        assert result is False, f"Expected False for headers={headers!r}, body={body!r}"


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


def test_empty_public_key_raises_at_construction() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        DiscordSigner("")


def test_non_hex_public_key_raises_at_construction() -> None:
    with pytest.raises((ValueError, Exception)):
        # 64-char non-hex string should fail `bytes.fromhex`
        DiscordSigner("NOT-HEX-DATA-AT-ALL-REALLY-TRULY-NOT-HEX-DATA-AT-ALL-NOPE")


def test_wrong_key_length_raises_at_construction() -> None:
    """A 16-byte key (too short for Ed25519) should fail construction."""
    with pytest.raises(ValueError):
        DiscordSigner("aabbccdd" * 4)  # 16 bytes, Ed25519 requires 32
