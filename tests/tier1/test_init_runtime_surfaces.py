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

    def test_anchor_minted_at_is_microsecond_padded(self) -> None:
        """`anchor_minted_at` ALWAYS carries a 6-digit microsecond fraction
        (ENVOY-P2-W2G-010) — `specs/independent-verifier.md` mandates
        `<iso8601 microsecond-padded>`. The default-arg path (`_now_iso()`) MUST
        NOT drop the fraction when the wall-clock microseconds happen to be 0."""
        import re

        anchor = build_trust_anchor(
            principal_genesis_id=_GENESIS_ID,
            principal_genesis_pubkey_hex=_VALID_PUBKEY_HEX,
        )
        minted = anchor["anchor_minted_at"]
        # ...T..:..:..[.NNNNNN]+00:00 — exactly 6 fractional digits, always.
        assert re.search(r"T\d{2}:\d{2}:\d{2}\.\d{6}", minted), (
            f"anchor_minted_at {minted!r} is not microsecond-padded (6 digits)"
        )

    def test_anchor_minted_at_padded_even_at_zero_microseconds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure case the bug hid: when the wall-clock's microseconds are
        EXACTLY 0, `datetime.isoformat()` (no timespec) drops `.000000`. Pin a
        zero-microsecond clock and assert the fraction is STILL present."""
        import datetime as _dt

        import envoy.boundary_conversation.init_runtime as init_mod

        fixed = _dt.datetime(2026, 6, 11, 9, 53, 0, 0, tzinfo=_dt.timezone.utc)

        class _FixedDateTime(_dt.datetime):
            @classmethod
            def now(cls, tz: object = None) -> _dt.datetime:  # type: ignore[override]
                return fixed

        monkeypatch.setattr(init_mod, "datetime", _FixedDateTime)

        anchor = build_trust_anchor(
            principal_genesis_id=_GENESIS_ID,
            principal_genesis_pubkey_hex=_VALID_PUBKEY_HEX,
        )
        # The zero-microsecond instant MUST still render the .000000 fraction.
        assert anchor["anchor_minted_at"] == "2026-06-11T09:53:00.000000+00:00"


class TestVaultAlreadyInitializedError:
    def test_carries_principal_and_store_key(self) -> None:
        exc = VaultAlreadyInitializedError(
            principal_id="alice@example", genesis_store_key="genesis:alice@example"
        )
        assert exc.principal_id == "alice@example"
        assert exc.genesis_store_key == "genesis:alice@example"
        # Plain-language message (non-technical user reads it directly).
        assert "already set up" in str(exc)
