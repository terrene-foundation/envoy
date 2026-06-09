# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Steward-quorum verifier — 2-of-N threshold + revocation vs rotation (S8).

Covers EC-S8.1 (threshold) + EC-S8.2 (revocation hard-fail / rotation additive)
for the SHARED `verify_steward_quorum` primitive — the single 2-of-N verifier
reused by the Envelope Library FV resolver, the EDR verifier (S8e), and the
classifier registry resolver (S9b).

Behavioral tests per `rules/testing.md` — call the verifier, assert the
raise/return verdict. The crypto is real (kailash `InMemoryKeyManager` Ed25519
sign + verify), not mocked.
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.registry.errors import (
    StewardQuorumError,
    StewardQuorumInputError,
    StewardQuorumReason,
)
from envoy.registry.steward_quorum import verify_steward_quorum

CONTENT_HASH = "a" * 64  # a stand-in sha256 hex; the payload each steward signs


async def _mint_steward(km: InMemoryKeyManager, key_id: str) -> tuple[str, str]:
    """Generate an Ed25519 steward keypair; return (pubkey_hex, signature_hex)
    over CONTENT_HASH. The signature is what the offline ceremony publishes."""
    _priv, pubkey = await km.generate_keypair(key_id)
    signature = km.sign_with_key(key_id, CONTENT_HASH.encode("utf-8"))
    return pubkey, signature


class TestStewardQuorumThreshold:
    """EC-S8.1 — 2-of-N threshold semantics."""

    async def test_two_distinct_pinned_signers_meets_quorum(self) -> None:
        km = InMemoryKeyManager()
        pub_a, sig_a = await _mint_steward(km, "steward-a")
        pub_b, sig_b = await _mint_steward(km, "steward-b")

        ok = await verify_steward_quorum(
            2,
            CONTENT_HASH,
            [
                {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
                {"steward_pubkey_hex": pub_b, "signature_hex": sig_b},
            ],
            pinned_pubkeys={pub_a, pub_b},
            revocation_list=set(),
            key_manager=km,
        )
        assert ok is True

    async def test_single_valid_signer_raises_threshold_not_met(self) -> None:
        km = InMemoryKeyManager()
        pub_a, sig_a = await _mint_steward(km, "steward-a")
        pub_b, _sig_b = await _mint_steward(km, "steward-b")

        with pytest.raises(StewardQuorumError) as exc_info:
            await verify_steward_quorum(
                2,
                CONTENT_HASH,
                [{"steward_pubkey_hex": pub_a, "signature_hex": sig_a}],
                pinned_pubkeys={pub_a, pub_b},
                revocation_list=set(),
                key_manager=km,
            )
        assert exc_info.value.reason is StewardQuorumReason.THRESHOLD_NOT_MET
        assert exc_info.value.distinct_valid == 1
        assert exc_info.value.threshold == 2

    async def test_duplicate_signature_by_same_key_does_not_inflate_count(self) -> None:
        # A malicious registry that replays one steward's signature twice MUST
        # NOT reach a 2-of-N quorum from a single distinct key.
        km = InMemoryKeyManager()
        pub_a, sig_a = await _mint_steward(km, "steward-a")
        pub_b, _ = await _mint_steward(km, "steward-b")

        with pytest.raises(StewardQuorumError) as exc_info:
            await verify_steward_quorum(
                2,
                CONTENT_HASH,
                [
                    {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
                    {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
                ],
                pinned_pubkeys={pub_a, pub_b},
                revocation_list=set(),
                key_manager=km,
            )
        assert exc_info.value.distinct_valid == 1

    async def test_unpinned_signer_is_ignored_not_counted(self) -> None:
        # A valid signature by a key OUTSIDE the pinned Foundation set is not a
        # steward; it must not contribute to the quorum.
        km = InMemoryKeyManager()
        pub_a, sig_a = await _mint_steward(km, "steward-a")
        pub_rogue, sig_rogue = await _mint_steward(km, "rogue")

        with pytest.raises(StewardQuorumError) as exc_info:
            await verify_steward_quorum(
                2,
                CONTENT_HASH,
                [
                    {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
                    {"steward_pubkey_hex": pub_rogue, "signature_hex": sig_rogue},
                ],
                pinned_pubkeys={pub_a},  # rogue NOT pinned
                revocation_list=set(),
                key_manager=km,
            )
        assert exc_info.value.distinct_valid == 1

    async def test_no_pinned_signer_raises_no_pinned_signers(self) -> None:
        km = InMemoryKeyManager()
        pub_rogue, sig_rogue = await _mint_steward(km, "rogue")
        pub_pinned, _ = await _mint_steward(km, "real-steward")

        with pytest.raises(StewardQuorumError) as exc_info:
            await verify_steward_quorum(
                2,
                CONTENT_HASH,
                [{"steward_pubkey_hex": pub_rogue, "signature_hex": sig_rogue}],
                pinned_pubkeys={pub_pinned},
                revocation_list=set(),
                key_manager=km,
            )
        assert exc_info.value.reason is StewardQuorumReason.NO_PINNED_SIGNERS

    async def test_tampered_signature_does_not_count(self) -> None:
        # A signature over a DIFFERENT content_hash must not verify against this
        # content_hash (supply-chain tamper on the signed payload).
        km = InMemoryKeyManager()
        pub_a, _ = await _mint_steward(km, "steward-a")
        # steward-a signs a DIFFERENT payload — this signature must not verify
        # against CONTENT_HASH.
        wrong_sig = km.sign_with_key("steward-a", b"different-content")
        pub_b, sig_b = await _mint_steward(km, "steward-b")

        with pytest.raises(StewardQuorumError):
            await verify_steward_quorum(
                2,
                CONTENT_HASH,
                [
                    {"steward_pubkey_hex": pub_a, "signature_hex": wrong_sig},
                    {"steward_pubkey_hex": pub_b, "signature_hex": sig_b},
                ],
                pinned_pubkeys={pub_a, pub_b},
                revocation_list=set(),
                key_manager=km,
            )

    async def test_zero_threshold_is_input_error_not_silent_pass(self) -> None:
        km = InMemoryKeyManager()
        with pytest.raises(StewardQuorumInputError):
            await verify_steward_quorum(
                0,
                CONTENT_HASH,
                [],
                pinned_pubkeys=set(),
                revocation_list=set(),
                key_manager=km,
            )


class TestRevocationVersusRotation:
    """EC-S8.2 — revocation = subtractive hard-fail; rotation = additive."""

    async def test_revoked_key_is_hard_rejected_even_when_present(self) -> None:
        # Two valid signatures, but one signer is revoked -> only 1 distinct
        # valid signer -> 2-of-N quorum NOT met.
        km = InMemoryKeyManager()
        pub_a, sig_a = await _mint_steward(km, "steward-a")
        pub_compromised, sig_compromised = await _mint_steward(km, "steward-compromised")

        with pytest.raises(StewardQuorumError) as exc_info:
            await verify_steward_quorum(
                2,
                CONTENT_HASH,
                [
                    {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
                    {
                        "steward_pubkey_hex": pub_compromised,
                        "signature_hex": sig_compromised,
                    },
                ],
                pinned_pubkeys={pub_a, pub_compromised},
                revocation_list={pub_compromised},
                key_manager=km,
            )
        assert exc_info.value.reason is StewardQuorumReason.REVOKED_KEY_PRESENT
        assert exc_info.value.distinct_valid == 1

    async def test_rotated_out_but_not_revoked_key_still_validates(self) -> None:
        # Rotation is ADDITIVE: a key from a prior generation that signed BEFORE
        # rotation still validates templates signed then, as long as it remains
        # pinned and is NOT on the revocation list. Here the "old" key + a new
        # key together meet the 2-of-N quorum.
        km = InMemoryKeyManager()
        pub_old, sig_old = await _mint_steward(km, "steward-prev-quarter")
        pub_new, sig_new = await _mint_steward(km, "steward-this-quarter")

        ok = await verify_steward_quorum(
            2,
            CONTENT_HASH,
            [
                {"steward_pubkey_hex": pub_old, "signature_hex": sig_old},
                {"steward_pubkey_hex": pub_new, "signature_hex": sig_new},
            ],
            # both still pinned (additive enrollment); NEITHER revoked
            pinned_pubkeys={pub_old, pub_new},
            revocation_list=set(),
            key_manager=km,
        )
        assert ok is True

    async def test_revocation_and_rotation_are_distinct_branches(self) -> None:
        # Same fixture, two revocation states, opposite verdicts — proves the
        # verifier treats revocation (subtractive) and rotation (additive) as
        # genuinely distinct, not conflated.
        km = InMemoryKeyManager()
        pub_old, sig_old = await _mint_steward(km, "old")
        pub_new, sig_new = await _mint_steward(km, "new")
        sigs = [
            {"steward_pubkey_hex": pub_old, "signature_hex": sig_old},
            {"steward_pubkey_hex": pub_new, "signature_hex": sig_new},
        ]
        pinned = {pub_old, pub_new}

        # Rotation only (no revocation) -> passes.
        assert await verify_steward_quorum(2, CONTENT_HASH, sigs, pinned, set(), key_manager=km)

        # Revoke the old key -> same signatures now fail (subtractive).
        with pytest.raises(StewardQuorumError):
            await verify_steward_quorum(2, CONTENT_HASH, sigs, pinned, {pub_old}, key_manager=km)
