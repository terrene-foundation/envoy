# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""RFC 9180 HPKE (base mode) + RFC 9458 OHTTP key-config encoding (S10).

This module pins the RFC-9458-DEFAULT HPKE ciphersuite so S11's client
encapsulation has a FIXED contract:

  ``DHKEM(X25519, HKDF-SHA256) [0x0020] + HKDF-SHA256 [0x0001] + AES-128-GCM [0x0001]``

It implements HPKE base mode (``mode_base = 0x00``) single-shot seal / open per
RFC 9180 §5.1.1 + §6.1, built from `cryptography` primitives (X25519 + HKDF +
AES-GCM — there is no `hpke` package in the dependency set, and
`rules/zero-tolerance.md` Rule 4 forbids working around a missing dep with a
naive re-implementation that diverges; this IS the spec algorithm, built on
the audited `cryptography` primitives, not a shortcut). The Foundation operates
the recipient (it holds the HPKE private key); S11's client is the sender.

The key-config wire format follows RFC 9458 §3 (Key Configuration Encoding):
``key_id (1) || kem_id (2) || pk (Npk) || cipher_suites_len (2) || (kdf_id (2)
|| aead_id (2))+``. The Foundation publishes this config signed 2-of-N by
stewards (Ed25519) so the client can verify operator authenticity before
encapsulating (`specs/foundation-ops.md:79`).

No network code lives here — this is pure crypto + encoding. The Nexus handler
set (`ohttp_server.py`) wraps it for transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

# --- RFC 9180 ciphersuite identifiers (the RFC-9458 default) ----------------

_KEM_ID_X25519_SHA256 = 0x0020  # DHKEM(X25519, HKDF-SHA256)
_KDF_ID_HKDF_SHA256 = 0x0001  # HKDF-SHA256
_AEAD_ID_AES_128_GCM = 0x0001  # AES-128-GCM

# KEM lengths for DHKEM(X25519) per RFC 9180 §7.1.
_NSECRET = 32  # KEM shared-secret length
_NENC = 32  # length of an X25519 encapsulated key (public key)
_NPK = 32  # X25519 public-key length

# AEAD parameters for AES-128-GCM per RFC 9180 §7.3.
_NK = 16  # key length
_NN = 12  # nonce length

# KDF hash length for HKDF-SHA256.
_NH = 32


@dataclass(frozen=True, slots=True)
class HpkeCiphersuite:
    """The pinned HPKE ciphersuite tuple (RFC 9458 default).

    Frozen so S11's client cannot silently negotiate a weaker suite; the wire
    encoding pins the exact ``(kem_id, kdf_id, aead_id)`` and any config the
    client fetches advertising a different triple is rejected.
    """

    kem_id: int = _KEM_ID_X25519_SHA256
    kdf_id: int = _KDF_ID_HKDF_SHA256
    aead_id: int = _AEAD_ID_AES_128_GCM

    @property
    def kem_suite_id(self) -> bytes:
        """``"KEM" || I2OSP(kem_id, 2)`` per RFC 9180 §4.1."""
        return b"KEM" + self.kem_id.to_bytes(2, "big")

    @property
    def hpke_suite_id(self) -> bytes:
        """``"HPKE" || kem_id || kdf_id || aead_id`` per RFC 9180 §5.1."""
        return (
            b"HPKE"
            + self.kem_id.to_bytes(2, "big")
            + self.kdf_id.to_bytes(2, "big")
            + self.aead_id.to_bytes(2, "big")
        )


RFC9458_CIPHERSUITE = HpkeCiphersuite()
"""The single canonical ciphersuite instance S10 publishes and S11 must use."""


# --- RFC 9180 §4 labeled KDF (HKDF-SHA256) ----------------------------------

_HPKE_V1 = b"HPKE-v1"


def _labeled_extract(salt: bytes, label: bytes, ikm: bytes, suite_id: bytes) -> bytes:
    """``LabeledExtract`` per RFC 9180 §4.

    HKDF-Extract over ``labeled_ikm = "HPKE-v1" || suite_id || label || ikm``.
    """
    labeled_ikm = _HPKE_V1 + suite_id + label + ikm
    # HKDF-Extract == HMAC(salt, labeled_ikm). `cryptography` exposes Extract
    # only as part of HKDF(extract+expand); we want Extract alone, so use HMAC.
    from cryptography.hazmat.primitives import hmac

    if not salt:
        salt = b"\x00" * _NH
    h = hmac.HMAC(salt, hashes.SHA256())
    h.update(labeled_ikm)
    return h.finalize()


def _labeled_expand(prk: bytes, label: bytes, info: bytes, length: int, suite_id: bytes) -> bytes:
    """``LabeledExpand`` per RFC 9180 §4."""
    labeled_info = length.to_bytes(2, "big") + _HPKE_V1 + suite_id + label + info
    return HKDFExpand(algorithm=hashes.SHA256(), length=length, info=labeled_info).derive(prk)


def _extract_and_expand(dh: bytes, kem_context: bytes, suite_id: bytes) -> bytes:
    """DHKEM ``ExtractAndExpand`` per RFC 9180 §4.1."""
    eae_prk = _labeled_extract(b"", b"eae_prk", dh, suite_id)
    return _labeled_expand(eae_prk, b"shared_secret", kem_context, _NSECRET, suite_id)


# --- DHKEM(X25519) encap / decap per RFC 9180 §4.1 --------------------------


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate an X25519 recipient keypair.

    Returns ``(private_bytes, public_bytes)`` — raw 32-byte little-endian
    encodings per RFC 7748. The Foundation holds the private key (recipient);
    the public key is published in the signed key config.
    """
    priv = x25519.X25519PrivateKey.generate()
    pub = priv.public_key()
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    priv_raw = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_raw = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv_raw, pub_raw


def _encap(pk_recipient: bytes, suite: HpkeCiphersuite) -> tuple[bytes, bytes]:
    """DHKEM ``Encap`` — returns ``(shared_secret, enc)``."""
    eph = x25519.X25519PrivateKey.generate()
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    enc = eph.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    pub_r = x25519.X25519PublicKey.from_public_bytes(pk_recipient)
    dh = eph.exchange(pub_r)
    kem_context = enc + pk_recipient
    shared_secret = _extract_and_expand(dh, kem_context, suite.kem_suite_id)
    return shared_secret, enc


def _decap(enc: bytes, sk_recipient: bytes, suite: HpkeCiphersuite) -> bytes:
    """DHKEM ``Decap`` — returns ``shared_secret``."""
    priv_r = x25519.X25519PrivateKey.from_private_bytes(sk_recipient)
    pub_e = x25519.X25519PublicKey.from_public_bytes(enc)
    dh = priv_r.exchange(pub_e)
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    pk_recipient = priv_r.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    kem_context = enc + pk_recipient
    return _extract_and_expand(dh, kem_context, suite.kem_suite_id)


# --- HPKE base-mode key schedule per RFC 9180 §5.1 --------------------------

_MODE_BASE = 0x00


def _key_schedule(shared_secret: bytes, info: bytes, suite: HpkeCiphersuite) -> tuple[bytes, bytes]:
    """Base-mode ``KeySchedule`` — returns ``(key, base_nonce)``.

    The base mode has no PSK; ``psk_id_hash`` and ``info_hash`` are over empty
    psk_id and the application ``info``.
    """
    suite_id = suite.hpke_suite_id
    psk_id_hash = _labeled_extract(b"", b"psk_id_hash", b"", suite_id)
    info_hash = _labeled_extract(b"", b"info_hash", info, suite_id)
    key_schedule_context = bytes([_MODE_BASE]) + psk_id_hash + info_hash
    # base mode: psk == b"", secret = LabeledExtract(shared_secret, "secret", psk)
    secret = _labeled_extract(shared_secret, b"secret", b"", suite_id)
    key = _labeled_expand(secret, b"key", key_schedule_context, _NK, suite_id)
    base_nonce = _labeled_expand(secret, b"base_nonce", key_schedule_context, _NN, suite_id)
    return key, base_nonce


def encapsulate_to_config(
    config: OhttpHpkeKeyConfig,
    plaintext: bytes,
    *,
    info: bytes = b"",
    aad: bytes = b"",
) -> bytes:
    """Seal ``plaintext`` to ``config``'s public key (sender / client side).

    Returns the OHTTP encapsulated request wire form: ``enc || ciphertext``
    (the encapsulated KEM key concatenated with the single-shot AEAD
    ciphertext). The Foundation recipient recovers it via
    ``decapsulate_request``.

    Raises:
        ValueError: the config advertises a ciphersuite other than the pinned
            RFC-9458 default (the client MUST NOT downgrade).
    """
    suite = config.ciphersuite
    if (suite.kem_id, suite.kdf_id, suite.aead_id) != (
        RFC9458_CIPHERSUITE.kem_id,
        RFC9458_CIPHERSUITE.kdf_id,
        RFC9458_CIPHERSUITE.aead_id,
    ):
        raise ValueError(
            "key config advertises a non-default HPKE ciphersuite; S11 client "
            "MUST use the pinned RFC-9458 default (no downgrade)"
        )
    shared_secret, enc = _encap(config.public_key, suite)
    key, base_nonce = _key_schedule(shared_secret, info, suite)
    # Single-shot Seal: sequence number 0 → nonce == base_nonce.
    ct = AESGCM(key).encrypt(base_nonce, plaintext, aad)
    return enc + ct


def decapsulate_request(
    config: OhttpHpkeKeyConfig,
    private_key: bytes,
    encapsulated: bytes,
    *,
    info: bytes = b"",
    aad: bytes = b"",
) -> bytes:
    """Open an encapsulated request (Foundation recipient side).

    Inverse of ``encapsulate_to_config``. ``encapsulated`` is ``enc || ct``.

    Raises:
        ValueError: malformed encapsulated message (too short to carry ``enc``).
        cryptography.exceptions.InvalidTag: AEAD authentication failed (tamper).
    """
    if len(encapsulated) < _NENC:
        raise ValueError(
            f"encapsulated request too short: {len(encapsulated)} bytes < "
            f"Nenc={_NENC} (cannot contain the KEM encapsulated key)"
        )
    enc, ct = encapsulated[:_NENC], encapsulated[_NENC:]
    suite = config.ciphersuite
    shared_secret = _decap(enc, private_key, suite)
    key, base_nonce = _key_schedule(shared_secret, info, suite)
    return AESGCM(key).decrypt(base_nonce, ct, aad)


# --- RFC 9458 §3 OHTTP key-config encoding + 2-of-N steward signing ----------


@dataclass(slots=True)
class OhttpHpkeKeyConfig:
    """An OHTTP (RFC 9458) HPKE key configuration published by the Foundation.

    Carries the recipient public key + the pinned ciphersuite + rotation
    metadata + the 2-of-N steward signatures over the canonical config bytes.
    The client fetches this, verifies the steward quorum (Ed25519) against
    pinned Foundation keys, checks expiry, then encapsulates under
    ``public_key``.

    ``steward_signatures`` is the ``[{"steward_pubkey_hex", "signature_hex"}]``
    array verified by the SHARED ``verify_steward_quorum`` primitive
    (`envoy.registry.steward_quorum`) — S10 does NOT grow a parallel quorum
    verifier (`rules/orphan-detection.md` single-helper cross-cut).
    """

    key_id: int
    public_key: bytes
    expires_at: str
    ciphersuite: HpkeCiphersuite = field(default_factory=lambda: RFC9458_CIPHERSUITE)
    steward_signatures: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0 <= self.key_id <= 0xFF:
            raise ValueError(f"key_id must be a single octet (0..255), got {self.key_id}")
        if len(self.public_key) != _NPK:
            raise ValueError(
                f"public_key must be {_NPK} bytes (X25519), got {len(self.public_key)}"
            )


def encode_key_config(config: OhttpHpkeKeyConfig) -> bytes:
    """Encode the RFC 9458 §3 key-config wire form (the signed payload).

    ``key_id (1) || kem_id (2) || pk (Npk) || cipher_suites_len (2) ||
    (kdf_id (2) || aead_id (2))`` — plus the ``expires_at`` rotation marker
    appended as a length-prefixed UTF-8 field (S10 extension: RFC 9458 does not
    carry expiry on the wire, but the Foundation registry's rotation contract
    requires the stewards to sign OVER the expiry so a relay cannot strip it).

    This byte string is what the 2-of-N stewards sign; the client re-encodes
    the fetched config and verifies the signatures over THESE bytes.
    """
    suite = config.ciphersuite
    cipher_suites = suite.kdf_id.to_bytes(2, "big") + suite.aead_id.to_bytes(2, "big")
    expires_bytes = config.expires_at.encode("utf-8")
    return (
        config.key_id.to_bytes(1, "big")
        + suite.kem_id.to_bytes(2, "big")
        + config.public_key
        + len(cipher_suites).to_bytes(2, "big")
        + cipher_suites
        + len(expires_bytes).to_bytes(2, "big")
        + expires_bytes
    )


async def verify_key_config_signatures(
    config: OhttpHpkeKeyConfig,
    *,
    threshold: int,
    pinned_pubkeys: list[str],
    revocation_list: list[str],
    key_manager: object,
) -> bool:
    """Verify the 2-of-N steward quorum over the encoded key config.

    Delegates to the SHARED ``verify_steward_quorum`` primitive — the signed
    payload is ``sha256(encode_key_config(config))`` in hex (the same
    content-hash shape every Foundation registry signs). Raises
    ``KeyConfigSignatureError`` when the quorum is not met (mapping the shared
    verifier's ``StewardQuorumError``).

    Args:
        threshold: 2 for the 2-of-N Foundation steward gate.
        pinned_pubkeys: client-pinned Foundation stewardship Ed25519 public keys.
        revocation_list: cached revoked steward keys (subtractive hard-fail).
        key_manager: a kailash ``InMemoryKeyManager`` (or any object exposing
            the async ``verify(payload, signature, public_key)`` surface).
    """
    import hashlib

    from envoy.foundation_ops.errors import KeyConfigSignatureError
    from envoy.registry.errors import StewardQuorumError
    from envoy.registry.steward_quorum import verify_steward_quorum

    content_hash_hex = hashlib.sha256(encode_key_config(config)).hexdigest()
    try:
        return await verify_steward_quorum(
            threshold,
            content_hash_hex,
            config.steward_signatures,
            pinned_pubkeys,
            revocation_list,
            key_manager=key_manager,  # type: ignore[arg-type]
        )
    except StewardQuorumError as exc:
        raise KeyConfigSignatureError(
            f"OHTTP key config (key_id={config.key_id}) failed the 2-of-N "
            f"steward quorum (distinct_valid={exc.distinct_valid}, "
            f"threshold={exc.threshold})"
        ) from exc


def key_config_content_hash(config: OhttpHpkeKeyConfig) -> str:
    """Hex ``sha256`` of the encoded key config — the payload the stewards sign.

    Exposed so the Foundation's offline signing ceremony and the client's
    verify path hash the SAME bytes.
    """
    import hashlib

    return hashlib.sha256(encode_key_config(config)).hexdigest()


__all__ = [
    "RFC9458_CIPHERSUITE",
    "HpkeCiphersuite",
    "OhttpHpkeKeyConfig",
    "encode_key_config",
    "key_config_content_hash",
    "encapsulate_to_config",
    "decapsulate_request",
    "generate_keypair",
    "verify_key_config_signatures",
]
