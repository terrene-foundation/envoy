# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""T-020 envelope-template supply-chain — content tamper hard-refuses (S8).

`specs/envelope-library.md` threat T-020 (envelope-template supply chain). The
consumer re-hashes fetched bytes against the declared `content_hash`; a 1-byte
content tamper makes the re-hash diverge and the resolver raises
`TemplateHashMismatchError` (EC-S8.3) — the registry transport is never trusted.

Regression test per `rules/testing.md` § Regression Testing: behavioral, calls
the resolver, asserts the raised type. NEVER deleted.
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.envelope.template_resolver import TemplateRef
from envoy.registry.errors import TemplateHashMismatchError
from envoy.registry.fv_resolver import FoundationVerifiedTemplateResolver
from envoy.registry.storage import ContentAddressedStore

CLEAN_CONTENT = {
    "schema_version": "envelope-template/1",
    "template_id": "family-starter",
    "constraints": {"financial": {"daily_cap_microdollars": 5_000_000}},
}


class _TamperingClient:
    """A registry client whose returned BYTES are tampered after the
    `content_hash` was computed — exactly the T-020 supply-chain vector. The
    consumer must catch it via local re-hashing, not trust the transport."""

    def __init__(self, *, content, content_hash, signatures) -> None:
        self._content = content
        self._content_hash = content_hash
        self._signatures = signatures

    def fetch(self, *, template_id_version=None, content_hash=None):
        return {
            "content": self._content,
            "content_hash": self._content_hash,  # declared hash of the CLEAN content
            "tier": "FV",
            "steward_signatures": self._signatures,
        }


@pytest.mark.regression
async def test_t020_one_byte_tamper_raises_hash_mismatch() -> None:
    km = InMemoryKeyManager()
    store = ContentAddressedStore()
    clean_hash = store.compute_hash(CLEAN_CONTENT)

    # Two valid steward signatures over the CLEAN content_hash (so the only
    # failing gate is the re-hash, isolating the supply-chain defense).
    _priv_a, pub_a = await km.generate_keypair("steward-a")
    _priv_b, pub_b = await km.generate_keypair("steward-b")
    sigs = [
        {
            "steward_pubkey_hex": pub_a,
            "signature_hex": km.sign_with_key("steward-a", clean_hash.encode("utf-8")),
        },
        {
            "steward_pubkey_hex": pub_b,
            "signature_hex": km.sign_with_key("steward-b", clean_hash.encode("utf-8")),
        },
    ]

    # The registry serves TAMPERED content but the CLEAN content_hash + valid
    # steward signatures — a mirror/transit compromise (T-050a / T-020).
    tampered = dict(CLEAN_CONTENT)
    tampered["constraints"] = {"financial": {"daily_cap_microdollars": 5_000_001}}  # +1 microdollar
    client = _TamperingClient(content=tampered, content_hash=clean_hash, signatures=sigs)
    resolver = FoundationVerifiedTemplateResolver(
        client=client,
        key_manager=km,
        pinned_pubkeys={pub_a, pub_b},
    )

    with pytest.raises(TemplateHashMismatchError):
        await resolver.resolve_async(TemplateRef("foundation-verified:family-starter@v3"))


@pytest.mark.regression
async def test_t020_untampered_content_resolves() -> None:
    # Control: the SAME signatures + the CLEAN (untampered) content resolve, so
    # the mismatch test above fails for the tamper, not for a broken fixture.
    km = InMemoryKeyManager()
    store = ContentAddressedStore()
    clean_hash = store.compute_hash(CLEAN_CONTENT)
    _priv_a, pub_a = await km.generate_keypair("steward-a")
    _priv_b, pub_b = await km.generate_keypair("steward-b")
    sigs = [
        {
            "steward_pubkey_hex": pub_a,
            "signature_hex": km.sign_with_key("steward-a", clean_hash.encode("utf-8")),
        },
        {
            "steward_pubkey_hex": pub_b,
            "signature_hex": km.sign_with_key("steward-b", clean_hash.encode("utf-8")),
        },
    ]
    client = _TamperingClient(content=CLEAN_CONTENT, content_hash=clean_hash, signatures=sigs)
    resolver = FoundationVerifiedTemplateResolver(
        client=client,
        key_manager=km,
        pinned_pubkeys={pub_a, pub_b},
    )
    result = await resolver.resolve_async(TemplateRef("foundation-verified:family-starter@v3"))
    assert result.template_hash == clean_hash
