# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Envelope Library FV-tier end-to-end via a REAL Nexus registry (S8).

Tier-2 per `rules/testing.md`: the registry transport is a real `Nexus` app
(`build_library_nexus`) with the `library.*` handler set registered across
HTTP/CLI/MCP — NOT a mock. The consumer (`FoundationVerifiedTemplateResolver`)
fetches through the Nexus-registered handler, re-hashes locally, and
re-verifies the 2-of-N steward quorum against client-pinned keys.

Covers EC-S8.5 (Community publish 503 refusal), EC-S8.6 (publish→fetch byte
round-trip), and the FV resolver happy + sad paths (EC-S8.3 hash-mismatch is in
`tests/regression/test_t020_envelope_template_supply_chain.py`; EC-S8.4 offline
in `test_envelope_library_offline_cache.py`).
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.envelope.canonical_bytes import canonical_bytes, content_hash
from envoy.envelope.template_resolver import TemplateRef
from envoy.registry.errors import (
    CommunityPublishingDisabledError,
    FVTierMembershipNotProvenError,
)
from envoy.registry.fv_resolver import FoundationVerifiedTemplateResolver
from envoy.registry.library_app import (
    LibraryRegistryHandlers,
    build_library_nexus,
)
from envoy.registry.storage import ContentAddressedStore, Tier

TEMPLATE_CONTENT = {
    "schema_version": "envelope-template/1",
    "template_id": "family-starter",
    "constraints": {"financial": {"daily_cap_microdollars": 5_000_000}},
}


class _NexusFetchClient:
    """A `library.fetch` client that drives the REAL Nexus-registered handler.

    Invokes the function registered on the Nexus app's handler registry — the
    same callable Nexus exposes over HTTP/CLI/MCP — so the consumer fetches
    through the real registry transport, not a mock. `raise_unreachable`
    simulates a down endpoint (the transport raising, which the resolver maps
    to the offline path)."""

    def __init__(self, nexus_app, *, raise_unreachable: bool = False) -> None:
        self._fn = nexus_app._handler_registry["library.fetch"]["handler"]
        self._raise_unreachable = raise_unreachable

    def fetch(self, *, template_id_version=None, content_hash=None):
        if self._raise_unreachable:
            from envoy.registry.errors import LibraryUnreachableError

            raise LibraryUnreachableError("simulated endpoint down")
        return self._fn(template_id_version=template_id_version, content_hash=content_hash)


async def _mint(km: InMemoryKeyManager, key_id: str, ch: str) -> tuple[str, str]:
    _priv, pub = await km.generate_keypair(key_id)
    return pub, km.sign_with_key(key_id, ch.encode("utf-8"))


@pytest.fixture
def store() -> ContentAddressedStore:
    return ContentAddressedStore()


@pytest.fixture
def handlers(store: ContentAddressedStore) -> LibraryRegistryHandlers:
    return LibraryRegistryHandlers(store=store)


@pytest.fixture
def nexus_app(handlers: LibraryRegistryHandlers):
    # Real Nexus app; high port numbers, never started (we drive the registered
    # handler in-process, which IS the real registry transport).
    app = build_library_nexus(handlers, api_port=18931, mcp_port=18932)
    yield app
    # Close so the internal AsyncLocalRuntime is released — otherwise a GC-time
    # "Unclosed Nexus" ResourceWarning surfaces under -W default (envoy-owned
    # leak; T-01). Fixtures yield + cleanup, never bare-return (rules/testing.md).
    app.close()


class TestFvReadPath:
    async def test_publish_then_resolve_round_trips_with_quorum(
        self, store, handlers, nexus_app
    ) -> None:
        km = InMemoryKeyManager()
        ch = store.compute_hash(TEMPLATE_CONTENT)
        pub_a, sig_a = await _mint(km, "steward-a", ch)
        pub_b, sig_b = await _mint(km, "steward-b", ch)
        sigs = [
            {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
            {"steward_pubkey_hex": pub_b, "signature_hex": sig_b},
        ]
        # FV publish (ceremony entry) through the handler set.
        handlers.publish(
            template_id="family-starter",
            version="v3",
            content=TEMPLATE_CONTENT,
            tier=Tier.FOUNDATION_VERIFIED.value,
            steward_signatures=sigs,
            published_at="2026-06-08T00:00:00Z",
        )

        resolver = FoundationVerifiedTemplateResolver(
            client=_NexusFetchClient(nexus_app),
            key_manager=km,
            pinned_pubkeys={pub_a, pub_b},
        )
        result = await resolver.resolve_async(TemplateRef("foundation-verified:family-starter@v3"))

        assert result.template_origin == "foundation-verified"
        assert result.content == TEMPLATE_CONTENT
        assert result.template_hash == ch

    async def test_single_steward_signature_refused(self, store, handlers, nexus_app) -> None:
        km = InMemoryKeyManager()
        ch = store.compute_hash(TEMPLATE_CONTENT)
        pub_a, sig_a = await _mint(km, "steward-a", ch)
        pub_b, _ = await _mint(km, "steward-b", ch)
        handlers.publish(
            template_id="family-starter",
            version="v3",
            content=TEMPLATE_CONTENT,
            tier=Tier.FOUNDATION_VERIFIED.value,
            steward_signatures=[{"steward_pubkey_hex": pub_a, "signature_hex": sig_a}],
            published_at="2026-06-08T00:00:00Z",
        )
        resolver = FoundationVerifiedTemplateResolver(
            client=_NexusFetchClient(nexus_app),
            key_manager=km,
            pinned_pubkeys={pub_a, pub_b},
        )
        with pytest.raises(FVTierMembershipNotProvenError):
            await resolver.resolve_async(TemplateRef("foundation-verified:family-starter@v3"))


class TestPublishReadBack:
    """EC-S8.6 — read-back byte fidelity via the real registry."""

    def test_fetch_by_content_hash_returns_byte_identical_content(self, store, handlers) -> None:
        ch = handlers.publish(
            template_id="family-starter",
            version="v3",
            content=TEMPLATE_CONTENT,
            tier=Tier.FOUNDATION_VERIFIED.value,
            steward_signatures=[],
            published_at="2026-06-08T00:00:00Z",
        )["content_hash"]

        fetched = handlers.fetch(content_hash=ch)
        assert fetched is not None
        # Byte-identical: re-canonicalizing the fetched content reproduces the
        # same content_hash the registry addressed it by.
        assert content_hash(canonical_bytes(fetched["content"])) == ch


class TestCommunityPublishGate:
    """EC-S8.5 — Community publish returns a typed Phase-03 refusal."""

    def test_community_publish_raises_typed_phase03_refusal(self, handlers) -> None:
        with pytest.raises(CommunityPublishingDisabledError) as exc_info:
            handlers.publish(
                template_id="anyone-skill",
                version="v1",
                content=TEMPLATE_CONTENT,
                tier=Tier.COMMUNITY.value,
                steward_signatures=[],
                published_at="2026-06-08T00:00:00Z",
            )
        assert "Phase-03" in str(exc_info.value)

    def test_fv_publish_is_not_gated(self, handlers) -> None:
        # FV publish must succeed — only Community/Org are gated.
        out = handlers.publish(
            template_id="family-starter",
            version="v3",
            content=TEMPLATE_CONTENT,
            tier=Tier.FOUNDATION_VERIFIED.value,
            steward_signatures=[],
            published_at="2026-06-08T00:00:00Z",
        )
        assert out["tier"] == Tier.FOUNDATION_VERIFIED.value
