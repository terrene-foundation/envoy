# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 — HPKE (RFC 9180 base mode) crypto core for S10.

Pure crypto, no infrastructure (<1s). Covers the seal/open round-trip
(orphan-detection.md § 2a crypto-pair round-trip), tamper detection, the pinned
RFC-9458 ciphersuite contract, and the stable RFC 9458 §3 wire encoding S11's
client re-encodes to verify steward signatures over.
"""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from envoy.foundation_ops.hpke import (
    RFC9458_CIPHERSUITE,
    HpkeCiphersuite,
    OhttpHpkeKeyConfig,
    decapsulate_request,
    encapsulate_to_config,
    encode_key_config,
    generate_keypair,
    key_config_content_hash,
)


@pytest.fixture
def config_and_priv() -> tuple[OhttpHpkeKeyConfig, bytes]:
    priv, pub = generate_keypair()
    return (
        OhttpHpkeKeyConfig(key_id=5, public_key=pub, expires_at="2099-01-01T00:00:00+00:00"),
        priv,
    )


class TestHpkeRoundTrip:
    def test_seal_open_round_trips(self, config_and_priv: tuple[OhttpHpkeKeyConfig, bytes]) -> None:
        config, priv = config_and_priv
        plaintext = b'{"21 flags": "..."}'
        enc = encapsulate_to_config(config, plaintext)
        assert decapsulate_request(config, priv, enc) == plaintext

    def test_seal_open_round_trips_with_info_and_aad(
        self, config_and_priv: tuple[OhttpHpkeKeyConfig, bytes]
    ) -> None:
        config, priv = config_and_priv
        pt, info, aad = b"shares", b"ohttp-req", b"hdr"
        enc = encapsulate_to_config(config, pt, info=info, aad=aad)
        assert decapsulate_request(config, priv, enc, info=info, aad=aad) == pt

    def test_tampered_ciphertext_rejected(
        self, config_and_priv: tuple[OhttpHpkeKeyConfig, bytes]
    ) -> None:
        config, priv = config_and_priv
        enc = bytearray(encapsulate_to_config(config, b"hello"))
        enc[-1] ^= 0x01  # flip a ciphertext byte
        with pytest.raises(InvalidTag):
            decapsulate_request(config, priv, bytes(enc))

    def test_wrong_aad_rejected(self, config_and_priv: tuple[OhttpHpkeKeyConfig, bytes]) -> None:
        config, priv = config_and_priv
        enc = encapsulate_to_config(config, b"hello", aad=b"a")
        with pytest.raises(InvalidTag):
            decapsulate_request(config, priv, enc, aad=b"b")

    def test_truncated_encapsulation_rejected(
        self, config_and_priv: tuple[OhttpHpkeKeyConfig, bytes]
    ) -> None:
        config, priv = config_and_priv
        with pytest.raises(ValueError, match="too short"):
            decapsulate_request(config, priv, b"\x00" * 8)


class TestCiphersuiteContract:
    def test_default_ciphersuite_is_rfc9458_default(self) -> None:
        # DHKEM(X25519, HKDF-SHA256) + HKDF-SHA256 + AES-128-GCM.
        assert RFC9458_CIPHERSUITE.kem_id == 0x0020
        assert RFC9458_CIPHERSUITE.kdf_id == 0x0001
        assert RFC9458_CIPHERSUITE.aead_id == 0x0001

    def test_non_default_ciphersuite_encap_refused(self) -> None:
        priv, pub = generate_keypair()
        weird = HpkeCiphersuite(kem_id=0x0020, kdf_id=0x0003, aead_id=0x0002)
        config = OhttpHpkeKeyConfig(
            key_id=1,
            public_key=pub,
            expires_at="2099-01-01T00:00:00+00:00",
            ciphersuite=weird,
        )
        with pytest.raises(ValueError, match="non-default"):
            encapsulate_to_config(config, b"x")


class TestKeyConfigEncoding:
    def test_encoding_is_deterministic(self) -> None:
        _priv, pub = generate_keypair()
        c1 = OhttpHpkeKeyConfig(key_id=9, public_key=pub, expires_at="2099-01-01T00:00:00+00:00")
        c2 = OhttpHpkeKeyConfig(key_id=9, public_key=pub, expires_at="2099-01-01T00:00:00+00:00")
        assert encode_key_config(c1) == encode_key_config(c2)
        assert key_config_content_hash(c1) == key_config_content_hash(c2)

    def test_encoding_carries_key_id_kem_and_pubkey(self) -> None:
        _priv, pub = generate_keypair()
        config = OhttpHpkeKeyConfig(
            key_id=0x2A, public_key=pub, expires_at="2099-01-01T00:00:00+00:00"
        )
        encoded = encode_key_config(config)
        assert encoded[0] == 0x2A  # key_id (1 octet)
        assert encoded[1:3] == (0x0020).to_bytes(2, "big")  # kem_id
        assert encoded[3:35] == pub  # 32-byte X25519 pubkey

    def test_rejects_wrong_pubkey_length(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            OhttpHpkeKeyConfig(
                key_id=1, public_key=b"short", expires_at="2099-01-01T00:00:00+00:00"
            )

    def test_rejects_out_of_range_key_id(self) -> None:
        _priv, pub = generate_keypair()
        with pytest.raises(ValueError, match="single octet"):
            OhttpHpkeKeyConfig(key_id=256, public_key=pub, expires_at="2099-01-01T00:00:00+00:00")
