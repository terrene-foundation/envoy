# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SEC-LOW-2 — quorum INPUT-bound errors map to the foundation_ops taxonomy.

`verify_key_config_signatures` previously caught only `StewardQuorumError` (the
verdict failure), letting `StewardQuorumInputError` escape unmapped.
`StewardQuorumInputError` is raised by `verify_steward_quorum` for `threshold <
1` OR `len(signatures) > MAX_STEWARD_SIGNATURES` (an oversized signature array —
a verify-cost DoS bound). The enterprise verifier (`verifier.py:250`) correctly
catches BOTH; foundation_ops now does too, mapping both to
`KeyConfigSignatureError`. Neither path fails open — the config is still
REFUSED.

Tier-2 per `rules/testing.md`: REAL `verify_key_config_signatures` →
`verify_steward_quorum` against a real `InMemoryKeyManager` (NOT a mock).
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
from envoy.registry.steward_quorum import MAX_STEWARD_SIGNATURES


def _config() -> OhttpHpkeKeyConfig:
    _priv, pub = generate_keypair()
    return OhttpHpkeKeyConfig(
        key_id=7, public_key=pub, expires_at="2099-01-01T00:00:00+00:00"
    )


class TestQuorumInputErrorMapping:
    async def test_oversized_signature_array_maps_to_key_config_signature_error(
        self,
    ) -> None:
        """An array beyond MAX_STEWARD_SIGNATURES (verify-cost DoS bound) raises
        StewardQuorumInputError internally → mapped to KeyConfigSignatureError
        (still REFUSED — never fails open)."""
        km = InMemoryKeyManager()
        cfg = _config()
        ch = key_config_content_hash(cfg)
        _priv, pub = await km.generate_keypair("steward-a")
        sig = km.sign_with_key("steward-a", ch.encode("utf-8"))
        # One MORE than the allowed bound → input-bound rejection.
        cfg.steward_signatures = [
            {"steward_pubkey_hex": pub, "signature_hex": sig}
            for _ in range(MAX_STEWARD_SIGNATURES + 1)
        ]
        with pytest.raises(KeyConfigSignatureError):
            await verify_key_config_signatures(
                cfg,
                threshold=2,
                pinned_pubkeys=[pub],
                revocation_list=[],
                key_manager=km,
            )

    async def test_degenerate_threshold_maps_to_key_config_signature_error(
        self,
    ) -> None:
        """threshold < 1 would fail-open (accept unsigned content) — the verifier
        raises StewardQuorumInputError; it MUST surface as KeyConfigSignatureError,
        not escape as a bare ValueError, and MUST refuse."""
        km = InMemoryKeyManager()
        cfg = _config()
        ch = key_config_content_hash(cfg)
        _priv, pub = await km.generate_keypair("steward-a")
        sig = km.sign_with_key("steward-a", ch.encode("utf-8"))
        cfg.steward_signatures = [{"steward_pubkey_hex": pub, "signature_hex": sig}]
        with pytest.raises(KeyConfigSignatureError):
            await verify_key_config_signatures(
                cfg,
                threshold=0,  # degenerate — would fail-open if not refused
                pinned_pubkeys=[pub],
                revocation_list=[],
                key_manager=km,
            )
