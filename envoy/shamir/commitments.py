"""Shard public commitments — sha256 over canonical SLIP-0039 paper-print form.

Per `specs/shamir-recovery.md` § Shard public commitments + line 41:
> Genesis Record carries `shard_public_commitments: [algo:hash]` array for
> recovery verification without shard exposure.

The commitment IS the cryptographic binding between the user's Genesis Record
and the shard set. At recovery time (T-02-36), the verifier recomputes the
commitment for each presented shard and confirms it lies in the
`shard_public_commitments` array stored on Genesis. If a counterfeit shard is
presented, its commitment will NOT match — the recovery refuses.

**Trust-boundary note (L-2 review):** the coordinator computes commitments
LOCALLY before passing them to the binder. Per
`workspaces/phase-01-mvp/journal/.pending/...-RISK-T-02-35-binder-trust.md`,
the prior shape (`bind_to_genesis(principal_id, shards) -> list[str]`) let a
malicious binder substitute commitments for a different secret without
coordinator detection. The current shape (`bind_to_genesis(principal_id,
commitments) -> None`) restricts the binder to STORAGE-ONLY: the binder cannot
forge a commitment that survives the coordinator's local recomputation.

Per `rules/orphan-detection.md` Rule 2a (Crypto-Pair Round-Trip): the
compute / verify pair MUST round-trip through a Tier 1 test —
`tests/tier1/test_shamir_commitments.py::TestCommitmentRoundTrip`.
"""

from __future__ import annotations

import hashlib
import logging

from kailash.trust.vault.shamir import serialize_shard

logger = logging.getLogger(__name__)

# Algorithm identifier prefix per `specs/trust-lineage.md` § Schema
# GenesisRecord — `shard_public_commitments: [algo:hash]`. Phase 01 uses
# sha256; Phase 02+ may add blake3 / sha3 alternatives behind a discriminator.
_COMMITMENT_ALGO = "sha256"


def compute_commitment(shard: list[str]) -> str:
    """Return the canonical commitment string for a SLIP-0039 shard.

    The commitment is `f"{algo}:{hexdigest}"` where:
    - `algo = "sha256"` (Phase 01 fixed; Phase 02+ adds discriminator support)
    - `hexdigest` is sha256 of `serialize_shard(shard).encode("utf-8")`

    `kailash.trust.vault.shamir.serialize_shard` is the cross-SDK canonical
    paper-print form — single-space-separated dictionary words. This is the
    SAME form a holder writes on a card; sha256 over the holder's transcribed
    form (after `deserialize_shard` strips any extra whitespace) is what
    the recovery verifier will recompute.

    Raises:
        TypeError: shard is not a list of strings (propagated from
            `serialize_shard`).
        ValueError: shard is empty (propagated from `serialize_shard`).
    """
    paper_form = serialize_shard(shard)
    digest = hashlib.sha256(paper_form.encode("utf-8")).hexdigest()
    return f"{_COMMITMENT_ALGO}:{digest}"


def verify_commitment(shard: list[str], commitments: list[str]) -> bool:
    """Return True iff `compute_commitment(shard)` lies in `commitments`.

    Used at recovery time (T-02-36) to verify a presented shard against the
    Genesis Record's `shard_public_commitments` array. If the shard is a
    counterfeit (constructed from a different secret) its commitment will NOT
    appear in the array — the verifier returns False and the recovery refuses
    to install the reconstructed master key.

    The comparison is a plain `in`-check rather than `hmac.compare_digest`
    because the input is a *digest* (already public via Genesis Record) being
    compared against a *known set of digests*. The timing-attack class that
    `compare_digest` defends against (extracting an unknown secret one byte
    at a time) does not apply: there is no unknown secret on either side of
    this comparison. Phase 02 may strengthen this for membership-witness
    constructions where the commitment IS the secret.

    Raises:
        TypeError: shard is not a list of strings.
        ValueError: shard is empty.
    """
    expected = compute_commitment(shard)
    return expected in commitments


__all__ = [
    "compute_commitment",
    "verify_commitment",
]
