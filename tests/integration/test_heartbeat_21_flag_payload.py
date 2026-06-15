# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S11.4/5/6/8 — STAR round-trip, low-population withhold, 21-flag payload,
HPKE info-binding.

Tier-2 per `rules/testing.md`: drives the REAL STAR share producer, the REAL
aggregator recovery, and the REAL OHTTP client encapsulation through S10's HPKE
primitives + registry handshake — no mocks. Covers:

- EC-S11.4: split_into_shares over the 21-flag boolean payload produces
  combinable shares; ≥100 identical-measurement clients recover the cohort;
  a malformed share raises STARShardCorruptError. Encapsulation routes through
  S10's verified key; a tampered/expired config is rejected at fetch/verify.
- EC-S11.5: a rare flag never reaching k=100 is structurally withheld and its
  ABSENCE is auditable — cohort padding is BLOCKED (we never pad).
- EC-S11.6: exactly 21 flags; `duress_unlock_detected` never present.
- EC-S11.8: the encapsulation `info` is non-empty and binds the key_id.
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.foundation_ops.hpke import (
    OhttpHpkeKeyConfig,
    decapsulate_request,
    generate_keypair,
    key_config_content_hash,
)
from envoy.heartbeat.errors import (
    STARShardCorruptError,
    kAnonymityFloorViolatedError,
)
from envoy.heartbeat.ohttp import OhttpClient, build_ohttp_info
from envoy.heartbeat.payload import ALLOWED_FLAGS, DURESS_FLAG_NEVER_REPORTED
from envoy.heartbeat.registry import HeartbeatRegistryClient
from envoy.heartbeat.star_prio import (
    K_ANONYMITY_FLOOR,
    StarPrioClient,
    StarShare,
    recover_cohort,
)


def _flag_measurement(flag: str, value: bool) -> bytes:
    """Cohort key for one boolean flag report — identical across clients."""
    return f"{flag}={int(value)}".encode()


async def _signed_config(key_id: int = 7) -> tuple[OhttpHpkeKeyConfig, InMemoryKeyManager, list[str]]:
    _priv, pub = generate_keypair()
    config = OhttpHpkeKeyConfig(key_id=key_id, public_key=pub, expires_at="2099-01-01T00:00:00+00:00")
    km = InMemoryKeyManager()
    ch = key_config_content_hash(config)
    sigs = []
    pinned = []
    for name in ("steward-a", "steward-b"):
        _p, p = await km.generate_keypair(name)
        sigs.append({"steward_pubkey_hex": p, "signature_hex": km.sign_with_key(name, ch.encode("utf-8"))})
        pinned.append(p)
    config.steward_signatures = sigs
    return config, km, pinned


class TestStarRoundTripAndPayload:
    def test_exactly_21_flags(self) -> None:
        assert len(ALLOWED_FLAGS) == 21

    def test_duress_flag_never_in_allowed_set(self) -> None:
        assert DURESS_FLAG_NEVER_REPORTED not in ALLOWED_FLAGS

    def test_star_shares_over_21_flag_payload_combine(self) -> None:
        """100 clients report the same flag value; the cohort recovers (EC-S11.4)."""
        flag = "completed_boundary_conversation"
        measurement = _flag_measurement(flag, True)
        shares = []
        for i in range(K_ANONYMITY_FLOOR):
            client = StarPrioClient(submitter_id=f"install-{i:04d}")
            shares.append(client.build_share(flag, measurement, (1).to_bytes(4, "big")))
        revelation = recover_cohort(shares)
        assert revelation.revealed is True
        # 100 clients each contributed value 1 → cohort aggregate 100.
        assert revelation.aggregate == 100
        # The recovered secret proves the cohort shares ONE measurement.
        assert revelation.recovered_secret is not None

    def test_malformed_share_raises_star_shard_corrupt(self) -> None:
        """A malformed share (empty measurement) raises STARShardCorruptError."""
        client = StarPrioClient(submitter_id="install-bad")
        with pytest.raises(STARShardCorruptError):
            client.build_share("channel_slack_active", b"", (1).to_bytes(4, "big"))

    def test_mixed_commitment_cohort_raises(self) -> None:
        """Aggregation rejects shares from different measurements (EC-S11.4)."""
        a = StarPrioClient(submitter_id="a").build_share(
            "channel_slack_active", b"channel_slack_active=1", (1).to_bytes(4, "big")
        )
        b = StarPrioClient(submitter_id="b").build_share(
            "channel_slack_active", b"channel_slack_active=0", (1).to_bytes(4, "big")
        )
        with pytest.raises(STARShardCorruptError):
            recover_cohort([a, b])

    def test_rare_flag_below_floor_structurally_withheld(self) -> None:
        """EC-S11.5: a rare flag never reaching k=100 is withheld, NOT padded.

        Only 5 clients ever report `channel_imessage_active` — far below the
        floor. The aggregate is structurally withheld; the withholding event is
        the auditable signal. We assert NO padding occurs (the cohort size in
        the error is the TRUE 5, not a padded 100).
        """
        flag = "channel_imessage_active"
        measurement = _flag_measurement(flag, True)
        shares = [
            StarPrioClient(submitter_id=f"rare-{i}").build_share(flag, measurement, (1).to_bytes(4, "big"))
            for i in range(5)
        ]
        with pytest.raises(kAnonymityFloorViolatedError) as exc:
            recover_cohort(shares)
        # The withholding event names the TRUE cohort size (5) — no padding.
        assert "5 < k-floor 100" in str(exc.value)

    async def test_encapsulation_routes_through_verified_key(self) -> None:
        """EC-S11.4: encapsulation routes through S10's operator-verified key."""
        config, km, pinned = await _signed_config(key_id=7)
        registry = HeartbeatRegistryClient(
            pinned_steward_pubkeys=pinned, revocation_list=[], key_manager=km
        )
        client = OhttpClient(registry=registry)
        # Wire form as S10's handler returns it.
        wire = {
            "key_id": config.key_id,
            "public_key_hex": config.public_key.hex(),
            "expires_at": config.expires_at,
            "steward_signatures": config.steward_signatures,
        }
        # fetch_key_configuration only returns after the operator signature
        # re-verifies; a tampered config would have raised before this point.
        verified = await client.fetch_key_configuration(wire)
        assert verified.key_id == 7
        # Build a STAR-share payload and encapsulate it under the verified key.
        share: StarShare = StarPrioClient(submitter_id="x").build_share(
            "enterprise_mode_active", b"enterprise_mode_active=1", (1).to_bytes(4, "big")
        )
        payload = share.secret_share.to_bytes(16, "big")
        encapsulated = client.encapsulate_request(verified, payload)
        assert isinstance(encapsulated, bytes)
        assert len(encapsulated) > 32  # enc(32) || ciphertext (round-trip below)

    async def test_tampered_config_rejected_at_fetch(self) -> None:
        """EC-S11.4: a tampered key config fails operator-signature re-verification."""
        from envoy.foundation_ops.errors import KeyConfigSignatureError

        config, km, pinned = await _signed_config(key_id=8)
        registry = HeartbeatRegistryClient(
            pinned_steward_pubkeys=pinned, revocation_list=[], key_manager=km
        )
        client = OhttpClient(registry=registry)
        # Tamper: swap the public key for a fresh one — the steward signatures no
        # longer verify over the mutated config bytes.
        _priv2, pub2 = generate_keypair()
        tampered_wire = {
            "key_id": config.key_id,
            "public_key_hex": pub2.hex(),  # mutated — signatures no longer match
            "expires_at": config.expires_at,
            "steward_signatures": config.steward_signatures,
        }
        with pytest.raises(KeyConfigSignatureError):
            await client.fetch_key_configuration(tampered_wire)

    async def test_none_config_maps_to_existence_check_failed(self) -> None:
        """EC-S11.4: a None fetch (empty registry) refuses, not retries."""
        client = OhttpClient(registry=HeartbeatRegistryClient(key_manager=InMemoryKeyManager()))
        with pytest.raises(ValueError, match="existence check failed"):
            await client.fetch_key_configuration(None)

    async def test_encapsulation_info_binds_key_id(self) -> None:
        """EC-S11.8: the encapsulation info is non-empty and includes the key_id."""
        config, _km, _pinned = await _signed_config(key_id=9)
        info = build_ohttp_info(config)
        assert info != b""
        # The key_id byte appears in the info (after the label + 0x00 separator).
        assert b"\x00" + (9).to_bytes(1, "big") in info
        # A different key_id yields a DIFFERENT info (binding is real).
        other, _k, _p = await _signed_config(key_id=10)
        assert build_ohttp_info(other) != info

    async def test_round_trip_seal_open_with_bound_info(self) -> None:
        """EC-S11.8: seal with the bound info; the recipient opens with the SAME info."""
        priv, pub = generate_keypair()
        config = OhttpHpkeKeyConfig(key_id=5, public_key=pub, expires_at="2099-01-01T00:00:00+00:00")
        client = OhttpClient()
        plaintext = b'{"shares": [1,2,3]}'
        encapsulated = client.encapsulate_request(config, plaintext)
        info = build_ohttp_info(config)
        recovered = decapsulate_request(config, priv, encapsulated, info=info)
        assert recovered == plaintext

    async def test_open_with_wrong_info_fails(self) -> None:
        """A ciphertext sealed for key_id=5 cannot be opened under key_id=6's info."""
        from cryptography.exceptions import InvalidTag

        priv, pub = generate_keypair()
        config5 = OhttpHpkeKeyConfig(key_id=5, public_key=pub, expires_at="2099-01-01T00:00:00+00:00")
        config6 = OhttpHpkeKeyConfig(key_id=6, public_key=pub, expires_at="2099-01-01T00:00:00+00:00")
        client = OhttpClient()
        encapsulated = client.encapsulate_request(config5, b"secret")
        wrong_info = build_ohttp_info(config6)
        with pytest.raises(InvalidTag):
            decapsulate_request(config5, priv, encapsulated, info=wrong_info)
