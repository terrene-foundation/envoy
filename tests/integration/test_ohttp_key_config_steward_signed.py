# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S10.1 — OHTTP key config published with a 2-of-N steward signature.

Tier-2 per `rules/testing.md`: drives the REAL Key Config Server handler set
(`OhttpKeyConfigServerHandlers`) + the REAL shared steward-quorum verifier
(`verify_key_config_signatures` → `verify_steward_quorum`) against a real
`InMemoryKeyManager` — NOT a mock. A config presented with only 1 valid steward
signature is rejected by the verifying client path (2-of-N gate per
`specs/foundation-ops.md:79`).
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.foundation_ops.errors import KeyConfigSignatureError
from envoy.foundation_ops.hpke import (
    OhttpHpkeKeyConfig,
    generate_keypair,
    key_config_content_hash,
    verify_key_config_signatures,
)
from envoy.foundation_ops.ohttp_server import OhttpKeyConfigServerHandlers


async def _steward(km: InMemoryKeyManager, key_id: str, ch: str) -> tuple[str, str]:
    """Mint a steward keypair + sign the config content-hash. Returns (pub, sig)."""
    _priv, pub = await km.generate_keypair(key_id)
    return pub, km.sign_with_key(key_id, ch.encode("utf-8"))


@pytest.fixture
def hpke_keypair() -> tuple[bytes, bytes]:
    return generate_keypair()


@pytest.fixture
def key_config(hpke_keypair: tuple[bytes, bytes]) -> OhttpHpkeKeyConfig:
    _priv, pub = hpke_keypair
    return OhttpHpkeKeyConfig(key_id=7, public_key=pub, expires_at="2099-01-01T00:00:00+00:00")


class TestKeyConfigStewardSigned:
    async def test_two_of_n_steward_signed_config_verifies(
        self, key_config: OhttpHpkeKeyConfig
    ) -> None:
        km = InMemoryKeyManager()
        ch = key_config_content_hash(key_config)
        pub_a, sig_a = await _steward(km, "steward-a", ch)
        pub_b, sig_b = await _steward(km, "steward-b", ch)
        key_config.steward_signatures = [
            {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
            {"steward_pubkey_hex": pub_b, "signature_hex": sig_b},
        ]
        # The server publishes; the client verifies the 2-of-N quorum locally.
        server = OhttpKeyConfigServerHandlers()
        server.publish_config(key_config)

        assert await verify_key_config_signatures(
            key_config,
            threshold=2,
            pinned_pubkeys=[pub_a, pub_b],
            revocation_list=[],
            key_manager=km,
        )

    async def test_single_steward_signature_rejected(self, key_config: OhttpHpkeKeyConfig) -> None:
        km = InMemoryKeyManager()
        ch = key_config_content_hash(key_config)
        pub_a, sig_a = await _steward(km, "steward-a", ch)
        pub_b, _sig_b = await _steward(km, "steward-b", ch)  # pinned, but did not sign
        key_config.steward_signatures = [
            {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
        ]
        with pytest.raises(KeyConfigSignatureError):
            await verify_key_config_signatures(
                key_config,
                threshold=2,
                pinned_pubkeys=[pub_a, pub_b],
                revocation_list=[],
                key_manager=km,
            )

    async def test_unpinned_signer_does_not_count_toward_quorum(
        self, key_config: OhttpHpkeKeyConfig
    ) -> None:
        """A valid signature by a NON-pinned key is ignored (not a Foundation steward)."""
        km = InMemoryKeyManager()
        ch = key_config_content_hash(key_config)
        pub_a, sig_a = await _steward(km, "steward-a", ch)
        pub_rogue, sig_rogue = await _steward(km, "rogue", ch)  # not pinned
        key_config.steward_signatures = [
            {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
            {"steward_pubkey_hex": pub_rogue, "signature_hex": sig_rogue},
        ]
        with pytest.raises(KeyConfigSignatureError):
            await verify_key_config_signatures(
                key_config,
                threshold=2,
                pinned_pubkeys=[pub_a],  # rogue NOT pinned
                revocation_list=[],
                key_manager=km,
            )
