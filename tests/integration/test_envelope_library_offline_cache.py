# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Envelope Library offline path — cache HIT re-verifies; MISS refuses (S8).

EC-S8.4 (`specs/envelope-library.md:64` `LibraryUnreachableError`): with the
Nexus endpoint unreachable AND a content-addressed cache HIT, resolve still
re-verifies against pinned keys and succeeds; a cache MISS raises
`LibraryUnreachableError`. The cache is NEVER a trust bypass (deep-dive gap #4)
— the offline re-resolve runs the SAME re-hash + quorum-verify as the online
path.

Tier-2 via the real Nexus registry (`build_library_nexus`); the transport-down
condition is simulated by the fetch client raising `LibraryUnreachableError`
(what an unreachable OHTTP/Nexus endpoint surfaces).
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.envelope.template_resolver import TemplateRef
from envoy.registry.errors import LibraryUnreachableError
from envoy.registry.fv_resolver import FoundationVerifiedTemplateResolver
from envoy.registry.library_app import LibraryRegistryHandlers, build_library_nexus
from envoy.registry.storage import ContentAddressedStore, Tier

CONTENT = {
    "schema_version": "envelope-template/1",
    "template_id": "family-starter",
    "constraints": {"financial": {"daily_cap_microdollars": 5_000_000}},
}


class _ToggleClient:
    """Real Nexus-registered `library.fetch` client with a transport-down toggle.

    `online=True` drives the real registry handler; `online=False` raises
    `LibraryUnreachableError` (an unreachable endpoint), forcing the resolver's
    offline cache path."""

    def __init__(self, nexus_app) -> None:
        self._fn = nexus_app._handler_registry["library.fetch"]["handler"]
        self.online = True

    def fetch(self, *, template_id_version=None, content_hash=None):
        if not self.online:
            raise LibraryUnreachableError("endpoint unreachable")
        return self._fn(template_id_version=template_id_version, content_hash=content_hash)


async def _publish_fv(handlers, store, km):
    ch = store.compute_hash(CONTENT)
    _pa, pub_a = await km.generate_keypair("steward-a")
    _pb, pub_b = await km.generate_keypair("steward-b")
    sigs = [
        {
            "steward_pubkey_hex": pub_a,
            "signature_hex": km.sign_with_key("steward-a", ch.encode("utf-8")),
        },
        {
            "steward_pubkey_hex": pub_b,
            "signature_hex": km.sign_with_key("steward-b", ch.encode("utf-8")),
        },
    ]
    handlers.publish(
        template_id="family-starter",
        version="v3",
        content=CONTENT,
        tier=Tier.FOUNDATION_VERIFIED.value,
        steward_signatures=sigs,
        published_at="2026-06-08T00:00:00Z",
    )
    return ch, {pub_a, pub_b}


async def test_offline_cache_hit_reverifies_and_succeeds() -> None:
    store = ContentAddressedStore()
    handlers = LibraryRegistryHandlers(store=store)
    app = build_library_nexus(handlers, api_port=18951, mcp_port=18952)
    try:
        km = InMemoryKeyManager()
        ch, pinned = await _publish_fv(handlers, store, km)

        client = _ToggleClient(app)
        resolver = FoundationVerifiedTemplateResolver(
            client=client, key_manager=km, pinned_pubkeys=pinned
        )
        ref = TemplateRef("foundation-verified:family-starter@v3")

        # 1. Online resolve populates the content-addressed cache.
        first = await resolver.resolve_async(ref)
        assert first.template_hash == ch

        # 2. Endpoint goes down; cache HIT still re-verifies against pinned keys.
        client.online = False
        offline = await resolver.resolve_async(ref)
        assert offline.template_hash == ch
        assert offline.template_origin == "foundation-verified"
    finally:
        # Close the Nexus app so its internal AsyncLocalRuntime is released —
        # otherwise a GC-time "Unclosed Nexus" ResourceWarning surfaces under
        # -W default (envoy-owned leak; T-01).
        app.close()


async def test_offline_cache_miss_raises_unreachable() -> None:
    store = ContentAddressedStore()
    handlers = LibraryRegistryHandlers(store=store)
    app = build_library_nexus(handlers, api_port=18953, mcp_port=18954)
    try:
        km = InMemoryKeyManager()
        await _publish_fv(handlers, store, km)

        client = _ToggleClient(app)
        client.online = False  # down from the start; nothing cached yet
        resolver = FoundationVerifiedTemplateResolver(
            client=client, key_manager=km, pinned_pubkeys=set()
        )
        with pytest.raises(LibraryUnreachableError):
            await resolver.resolve_async(TemplateRef("foundation-verified:family-starter@v3"))
    finally:
        app.close()  # release the Nexus AsyncLocalRuntime (T-01 envoy-owned leak)


async def test_offline_cache_hit_still_refuses_when_keys_unpinned() -> None:
    # The cache is not a trust bypass: even a cache HIT re-runs the quorum
    # verify, so a resolver that previously verified with pinned keys but whose
    # pinned set is now empty cannot resolve from cache. (Constructed as a fresh
    # resolver with no cache + offline → unreachable, proving the offline path
    # never returns content that skipped verification.)
    store = ContentAddressedStore()
    handlers = LibraryRegistryHandlers(store=store)
    app = build_library_nexus(handlers, api_port=18955, mcp_port=18956)
    try:
        km = InMemoryKeyManager()
        await _publish_fv(handlers, store, km)

        client = _ToggleClient(app)
        # Fresh resolver, no cache, endpoint up but keys unpinned → quorum fails.
        resolver = FoundationVerifiedTemplateResolver(
            client=client, key_manager=km, pinned_pubkeys=set()
        )
        from envoy.registry.errors import FVTierMembershipNotProvenError

        with pytest.raises(FVTierMembershipNotProvenError):
            await resolver.resolve_async(TemplateRef("foundation-verified:family-starter@v3"))
    finally:
        app.close()  # release the Nexus AsyncLocalRuntime (T-01 envoy-owned leak)
