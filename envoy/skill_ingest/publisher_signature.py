# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.skill_ingest.publisher_signature — CO validator step 6 verify.

`specs/skill-ingest.md` CO validator step 6 ("Publisher signature verifies").
The publisher signs the `skill_source_hash` with their Ed25519 key; the CO
validator re-verifies that signature against the publisher's PINNED public key.

This module REUSES the existing Ed25519 verify primitive — the kailash
`InMemoryKeyManager.verify(payload, signature, public_key)` surface that
`envoy.registry.steward_quorum` and `envoy.ledger.facade` already depend on. It
does NOT roll a second signature verifier (the S8 quorum primitive is the
canonical Ed25519 verify; this is the single-signature publisher equivalent).

The verifier is fail-closed: a signature that does not verify raises
`PublisherSignatureInvalidError`; an absent pinned key for the declared
`genesis_id` is also a hard refusal (the publisher is not pinned → cannot be
trusted).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from envoy.skill_ingest.errors import PublisherSignatureInvalidError


class _VerifyKeyManager(Protocol):
    """The single async `verify` method step 6 needs.

    Matches `kailash.trust.key_manager.InMemoryKeyManager.verify` — the SAME
    surface `envoy.registry.steward_quorum.verify_steward_quorum` consumes. The
    payload is the `skill_source_hash` bytes; the public key is the publisher's
    pinned Ed25519 public key hex.
    """

    async def verify(self, payload: Any, signature: str, public_key: str) -> bool: ...


async def verify_publisher_signature(
    skill_source_hash: str,
    genesis_id: str,
    signature_hex: str,
    pinned_publisher_pubkeys: Mapping[str, str],
    *,
    key_manager: _VerifyKeyManager,
) -> bool:
    """Verify the publisher's Ed25519 signature over the `skill_source_hash`.

    Args:
        skill_source_hash: The hex `sha256` the publisher signed (the signed
            payload — the verifier signs NOTHING; it only checks an existing
            signature).
        genesis_id: The publisher's Foundation genesis identity (the lookup key
            into the pinned-publisher key set).
        signature_hex: The Ed25519 signature hex from the ENVELOPE.md
            ``publisher.signature`` block.
        pinned_publisher_pubkeys: The client-pinned ``genesis_id → public_key
            hex`` map (the trust anchor — NOT the transport).
        key_manager: A kailash `InMemoryKeyManager` (or any object exposing the
            async `verify(payload, signature, public_key)` surface). REUSED, not
            re-implemented.

    Returns:
        True when the signature verifies against the pinned publisher key.

    Raises:
        PublisherSignatureInvalidError: the publisher's `genesis_id` is not in
            the pinned key set (un-pinned publisher — cannot be trusted), OR the
            Ed25519 signature does not verify. Fail-closed — never returns False
            silently.
    """
    pinned_pubkey = pinned_publisher_pubkeys.get(genesis_id)
    if pinned_pubkey is None:
        raise PublisherSignatureInvalidError(
            f"publisher genesis_id {genesis_id!r} is not in the pinned publisher "
            "key set; refuse install — the publisher is not a trusted, pinned "
            "Foundation identity"
        )

    payload = skill_source_hash.encode("utf-8")
    # The key manager returns False for a well-formed-but-wrong signature and
    # MAY raise for a malformed signature (wrong length / bad base64). Both are
    # verification failures from the validator's view — map either to the typed
    # refusal (fail-closed) rather than letting a raw crypto exception escape.
    try:
        verified = await key_manager.verify(payload, signature_hex, pinned_pubkey)
    except Exception as exc:
        raise PublisherSignatureInvalidError(
            f"publisher Ed25519 signature for genesis_id {genesis_id!r} could not "
            "be verified (malformed signature material); refuse install — "
            "possible supply-chain tamper"
        ) from exc
    if not verified:
        raise PublisherSignatureInvalidError(
            f"publisher Ed25519 signature for genesis_id {genesis_id!r} does not "
            "verify over the skill_source_hash; refuse install — possible "
            "publisher-key rotation OR supply-chain tamper"
        )
    return True


__all__ = ["verify_publisher_signature"]
