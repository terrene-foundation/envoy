"""Tier 1: T-02-35 — `compute_commitment` / `verify_commitment` round-trip.

Source: shard `01-analysis/15-shamir-recovery-implementation.md` § 3 step 4
+ `specs/shamir-recovery.md` § Shard public commitments + line 41.

Per `rules/orphan-detection.md` Rule 2a (Crypto-Pair Round-Trip): paired
crypto operations MUST round-trip — call one half, feed its output to the
other, assert equality. Isolated unit tests per half can drift silently.
This file is the structural defense against compute / verify drifting
(e.g. one switches algo prefix, the other doesn't).
"""

from __future__ import annotations

import re

import pytest

from envoy.shamir import compute_commitment, verify_commitment

# Realistic SLIP-0039 mnemonic-shaped sample. The real generator emits
# 24-word lists from a fixed dictionary; these stand-ins exercise the
# shape only — the commitment function does not validate dictionary
# membership (that lives in `kailash.trust.vault.shamir.serialize_shard`).
_SAMPLE_SHARD_A = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
_SAMPLE_SHARD_B = ["one", "two", "three", "four", "five", "six"]


class TestCommitmentShape:
    def test_compute_returns_sha256_prefixed_hex(self) -> None:
        c = compute_commitment(_SAMPLE_SHARD_A)
        assert isinstance(c, str)
        # "sha256:" + 64 hex chars
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", c)

    def test_compute_is_deterministic(self) -> None:
        c1 = compute_commitment(_SAMPLE_SHARD_A)
        c2 = compute_commitment(list(_SAMPLE_SHARD_A))  # fresh list, same content
        assert c1 == c2

    def test_compute_distinguishes_distinct_shards(self) -> None:
        ca = compute_commitment(_SAMPLE_SHARD_A)
        cb = compute_commitment(_SAMPLE_SHARD_B)
        assert ca != cb


class TestCommitmentRoundTrip:
    """Per `rules/orphan-detection.md` Rule 2a — compute / verify round-trip
    is the structural defense against the two halves drifting.
    """

    def test_verify_accepts_own_commitment(self) -> None:
        commitments = [compute_commitment(_SAMPLE_SHARD_A)]
        assert verify_commitment(_SAMPLE_SHARD_A, commitments) is True

    def test_verify_accepts_membership_in_full_array(self) -> None:
        commitments = [
            compute_commitment(_SAMPLE_SHARD_A),
            compute_commitment(_SAMPLE_SHARD_B),
        ]
        assert verify_commitment(_SAMPLE_SHARD_A, commitments) is True
        assert verify_commitment(_SAMPLE_SHARD_B, commitments) is True

    def test_verify_rejects_counterfeit_shard(self) -> None:
        """A shard whose commitment is NOT in the array is a counterfeit
        per `specs/shamir-recovery.md` § Error taxonomy
        `CommitmentVerificationFailedError` — verify returns False so the
        recovery flow can refuse the unlock.
        """
        # Genesis records commitments for shards A and B; an attacker
        # presents a different shard (say C) whose commitment was never
        # bound to the user's Genesis Record.
        committed = [
            compute_commitment(_SAMPLE_SHARD_A),
            compute_commitment(_SAMPLE_SHARD_B),
        ]
        counterfeit_shard = ["counterfeit", "seed", "values", "x", "y", "z"]
        assert verify_commitment(counterfeit_shard, committed) is False

    def test_verify_against_empty_array_returns_false(self) -> None:
        # Edge case: no commitments persisted (pre-Phase-01 vault per
        # `ShardPublicCommitmentMissingError`). Verify MUST return False
        # — recovery refuses rather than silently passes.
        assert verify_commitment(_SAMPLE_SHARD_A, []) is False


class TestCommitmentInputValidation:
    def test_compute_rejects_non_list(self) -> None:
        with pytest.raises(TypeError):
            compute_commitment("alpha beta gamma")  # type: ignore[arg-type]

    def test_compute_rejects_empty_list(self) -> None:
        with pytest.raises(ValueError):
            compute_commitment([])
