# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.registry.steward_quorum — the SHARED 2-of-N steward-quorum verifier.

`specs/foundation-ops.md` § Signing ceremonies: Foundation-Verified signatures
require 2-of-N Foundation stewards. `specs/envelope-library.md` § Trust tiers
FV row: Foundation steward Ed25519, key-rotation quarterly.

This module ships `verify_steward_quorum(...)` — built EXACTLY ONCE per the
WS-4 deep-dive cross-cut (`01-analysis/01-research/04-ws4-library-skill-ingest.md`
§ 2.2 + § 4.1). It is the single 2-of-N verify primitive shared by:

- the Envelope Library FV resolver (S8, this milestone),
- the EnterpriseDeploymentRecord verifier (S8e),
- the classifier registry resolver (S9b, `classifier_registry_resolve` step b).

No consumer may grow a parallel quorum-verify (EC-S8.7 / EC-S8e.4 / EC-S9b.3
structural grep gate: exactly one `def verify_steward_quorum(` in the tree).

Trust model (client-side only — Envoy NEVER signs; the Foundation signs offline
in an air-gapped ceremony). The consumer holds the PINNED Foundation stewardship
PUBLIC key set + the cached revocation list and verifies:

  1. Each signature's `steward_pubkey_hex` is in the client-pinned key set
     (un-pinned signers are ignored — they are not Foundation stewards).
  2. The pinned signer is NOT on the revocation list (revocation = subtractive
     HARD-FAIL: a present-but-revoked key is rejected even if it validly signs).
  3. The Ed25519 signature verifies over the `content_hash` via the kailash
     `InMemoryKeyManager.verify(payload, signature, public_key)` primitive
     (the SAME primitive the Ledger facade and keystore use).
  4. ≥ `threshold` DISTINCT pinned, non-revoked keys validly signed.

Rotation vs revocation (the invariant the verifier MUST hold distinctly):

  - **Rotation is additive.** A new quarterly steward generation enrolls new
    keys into the pinned set; old (rotated-out but NOT revoked) keys still
    validate signatures made before rotation. The verifier does NOT reject a
    signature merely because the key is "old" — only pinned-membership +
    revocation + crypto-validity + distinctness gate the verdict.
  - **Revocation is subtractive.** A compromised key on the revocation list is
    a HARD-FAIL: its signatures never count toward the quorum, even if the key
    is still in the pinned set.

The verdict is a base `True` / `StewardQuorumError`; each consumer maps the
error to its own spec taxonomy (`errors.py`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol

from envoy.registry.errors import (
    StewardQuorumError,
    StewardQuorumInputError,
    StewardQuorumReason,
)


class _VerifyKeyManager(Protocol):
    """The single method `verify_steward_quorum` needs from a key manager.

    Matches `kailash.trust.key_manager.InMemoryKeyManager.verify`, which is
    async and takes the public key hex DIRECTLY (not a key_id) — the same
    surface `envoy.ledger.facade._KeyManagerProtocol` depends on.
    """

    async def verify(self, payload: Any, signature: str, public_key: str) -> bool: ...


async def verify_steward_quorum(
    threshold: int,
    content_hash: str,
    signatures: Sequence[Mapping[str, str]],
    pinned_pubkeys: Iterable[str],
    revocation_list: Iterable[str],
    *,
    key_manager: _VerifyKeyManager,
) -> bool:
    """Verify a 2-of-N (or N-of-M) Foundation steward quorum over `content_hash`.

    Args:
        threshold: Minimum number of DISTINCT valid, pinned, non-revoked
            steward keys required (2 for the Foundation-Verified tier). MUST be
            ≥ 1 — a `threshold < 1` is a `StewardQuorumInputError` (a degenerate
            zero-threshold would silently "pass" any content, the exact
            fail-open this verifier exists to prevent).
        content_hash: The hex `sha256(canonical_bytes(content))` that each
            steward signed. This is the signed payload — the verifier signs
            NOTHING; it only checks signatures already produced offline.
        signatures: The published steward-signature array; each entry is a
            mapping with `steward_pubkey_hex` + `signature_hex`
            (`specs/foundation-ops.md` § Registry schemas).
        pinned_pubkeys: The client-pinned Foundation stewardship PUBLIC key set
            (the trust anchor — NOT the Nexus transport). Signatures by keys
            outside this set are ignored.
        revocation_list: Hex public keys the client has cached as REVOKED. A
            revoked key's signatures are hard-rejected (subtractive).
        key_manager: A kailash `InMemoryKeyManager` (or any object exposing the
            async `verify(payload, signature, public_key)` surface).

    Returns:
        True when ≥ `threshold` distinct pinned, non-revoked keys validly
        signed `content_hash`.

    Raises:
        StewardQuorumInputError: `threshold < 1` (caller programming error).
        StewardQuorumError: the quorum is not met. Carries a structured
            `reason` (`StewardQuorumReason`) + `distinct_valid` + `threshold`
            so consumers map to their own taxonomy structurally.
    """
    if threshold < 1:
        raise StewardQuorumInputError(
            f"threshold must be >= 1 (got {threshold}); a zero threshold would "
            "fail-open and accept unsigned content"
        )

    pinned = set(pinned_pubkeys)
    revoked = set(revocation_list)
    payload = content_hash.encode("utf-8")

    distinct_valid: set[str] = set()
    saw_pinned_signer = False
    saw_revoked_signer = False

    for sig in signatures:
        pubkey = sig.get("steward_pubkey_hex")
        signature_hex = sig.get("signature_hex")
        if not pubkey or not signature_hex:
            # A malformed entry contributes nothing — it cannot be a valid,
            # pinned, distinct signer. Do not raise: a single junk row in an
            # otherwise-valid array must not deny a legitimate quorum.
            continue
        if pubkey not in pinned:
            # Not a Foundation steward (un-pinned). Ignored, never counted.
            continue
        saw_pinned_signer = True
        if pubkey in revoked:
            # Revocation = subtractive HARD-FAIL. A revoked key's signature
            # never counts, even though it is pinned and may crypto-verify.
            saw_revoked_signer = True
            continue
        if pubkey in distinct_valid:
            # Already counted this distinct key — a duplicated signature by the
            # same key cannot inflate the distinct count toward the quorum.
            continue
        if await key_manager.verify(payload, signature_hex, pubkey):
            distinct_valid.add(pubkey)

    if len(distinct_valid) >= threshold:
        return True

    # Quorum not met — classify the reason structurally for the consumer.
    if not saw_pinned_signer:
        reason = StewardQuorumReason.NO_PINNED_SIGNERS
        detail = "no signature was made by a client-pinned Foundation stewardship key"
    elif saw_revoked_signer and len(distinct_valid) < threshold:
        reason = StewardQuorumReason.REVOKED_KEY_PRESENT
        detail = (
            "a revoked steward key was present; valid non-revoked distinct "
            "signers below threshold"
        )
    else:
        reason = StewardQuorumReason.THRESHOLD_NOT_MET
        detail = "fewer than the required number of distinct valid steward signatures"

    raise StewardQuorumError(
        f"steward quorum not met: {detail} "
        f"(distinct_valid={len(distinct_valid)}, threshold={threshold})",
        reason=reason,
        distinct_valid=len(distinct_valid),
        threshold=threshold,
    )


__all__ = ["verify_steward_quorum"]
