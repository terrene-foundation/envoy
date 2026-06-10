# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1: pure surfaces of the ``envoy init`` bootstrap (S4i).

Source: WS-6 S4i. The trust-anchor payload builder, the genesis
SessionObservedState builder, the deterministic genesis-key derivation, and the
typed ``VaultAlreadyInitializedError`` are pure functions / data — no infra.
Per `rules/testing.md` § Tier 1: <1s, no real infrastructure.

Per `rules/probe-driven-verification.md` MUST-3: structural assertions on the
emitted JSON shape (schema_version, field presence, hex-decodability), not
regex-on-prose.
"""

from __future__ import annotations

import pytest

from envoy.boundary_conversation import (
    VaultAlreadyInitializedError,
    build_genesis_session_state,
    build_trust_anchor,
    genesis_session_key,
)
from envoy.boundary_conversation.init_runtime import (
    SESSION_STATE_SCHEMA_VERSION,
    TRUST_ANCHOR_SCHEMA_VERSION,
)

# A real ed25519 public key is 32 bytes → 64 hex chars. Use a fixed valid hex.
_VALID_PUBKEY_HEX = "ab" * 32
_GENESIS_ID = "sha256:" + "cd" * 32


class TestGenesisSessionKey:
    def test_key_is_principal_scoped(self) -> None:
        assert genesis_session_key("alice@example") == "genesis:alice@example"

    def test_key_distinct_per_principal(self) -> None:
        assert genesis_session_key("a") != genesis_session_key("b")

    def test_empty_principal_raises(self) -> None:
        with pytest.raises(ValueError, match="principal_id is required"):
            genesis_session_key("")


class TestBuildGenesisSessionState:
    def test_shape_matches_session_state_schema(self) -> None:
        state = build_genesis_session_state(
            session_id="0190a1b2-c3d4-e5f6-0708-090a0b0c0d0e",
            principal_genesis_id=_GENESIS_ID,
            envelope_version_at_session_start=1,
        )
        assert state["schema_version"] == SESSION_STATE_SCHEMA_VERSION
        assert state["session_id"] == "0190a1b2-c3d4-e5f6-0708-090a0b0c0d0e"
        assert state["principal_genesis_id"] == _GENESIS_ID
        assert state["posture_at_session_start"] == "PSEUDO"
        assert state["envelope_version_at_session_start"] == 1
        # Genesis session: present-but-empty caches (canonical schema shape).
        assert state["tool_calls_made"] == {}
        assert state["reasoning_commits"] == []
        assert state["pending_phase_a_orphans"] == []
        assert state["pre_authorized_patterns"] == []
        assert state["goal_reconfirmation"]["tool_calls_since_reconfirm"] == 0
        # started_at / last_activity_at are present + identical at genesis.
        assert state["started_at"] == state["last_activity_at"]


class TestBuildTrustAnchor:
    def test_shape_matches_trust_anchor_schema(self) -> None:
        anchor = build_trust_anchor(
            principal_genesis_id=_GENESIS_ID,
            principal_genesis_pubkey_hex=_VALID_PUBKEY_HEX,
        )
        assert anchor["schema_version"] == TRUST_ANCHOR_SCHEMA_VERSION
        assert anchor["principal_genesis_id"] == _GENESIS_ID
        assert anchor["principal_genesis_pubkey_hex"] == _VALID_PUBKEY_HEX
        assert anchor["device_attestation_chain"] == []
        assert anchor["anchor_minted_at"]

    def test_pubkey_must_be_hex(self) -> None:
        """A non-hex pubkey (e.g. the base64 form forwarded straight through)
        is a programming error caught loud — never silently embedded."""
        with pytest.raises(ValueError, match="must be hex-encoded"):
            build_trust_anchor(
                principal_genesis_id=_GENESIS_ID,
                principal_genesis_pubkey_hex="not-hex-base64==",
            )

    def test_missing_genesis_id_raises(self) -> None:
        with pytest.raises(ValueError, match="principal_genesis_id is required"):
            build_trust_anchor(
                principal_genesis_id="", principal_genesis_pubkey_hex=_VALID_PUBKEY_HEX
            )

    def test_missing_pubkey_raises(self) -> None:
        with pytest.raises(ValueError, match="principal_genesis_pubkey_hex is required"):
            build_trust_anchor(principal_genesis_id=_GENESIS_ID, principal_genesis_pubkey_hex="")

    def test_anchor_carries_no_private_material(self) -> None:
        import json

        anchor = build_trust_anchor(
            principal_genesis_id=_GENESIS_ID,
            principal_genesis_pubkey_hex=_VALID_PUBKEY_HEX,
        )
        raw = json.dumps(anchor).lower()
        for forbidden in ("private", "secret", "passphrase", "master_key"):
            assert forbidden not in raw


class TestVaultAlreadyInitializedError:
    def test_carries_principal_and_store_key(self) -> None:
        exc = VaultAlreadyInitializedError(
            principal_id="alice@example", genesis_store_key="genesis:alice@example"
        )
        assert exc.principal_id == "alice@example"
        assert exc.genesis_store_key == "genesis:alice@example"
        # Plain-language message (non-technical user reads it directly).
        assert "already set up" in str(exc)
