# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: S8 security-review MED-1/2/3 — untrusted-input bounds hardening.

Source: gate-level security review of the S8 WS-4 steward-quorum / Envelope
Library FV registry shard. Three same-bug-class (untrusted-input-bounds)
findings, all fixed in the same session per `rules/autonomous-execution.md`
Rule 4:

- **MED-2 (verify-cost DoS)** — `verify_steward_quorum` iterated an unbounded
  `signatures` array, forcing one Ed25519 verify per pinned/distinct entry. The
  transport is untrusted, so an oversized array is a verify-cost DoS. Fix:
  reject `len(signatures) > MAX_STEWARD_SIGNATURES` (64) BEFORE the loop.

- **MED-3 (publish input validation)** — the `library.publish` handler accepted
  any `template_id` / `version` and an unbounded `steward_signatures` array. The
  publish surface is air-gapped-ceremony-only this phase (NOT network-writable);
  the guard hardens it so a garbage / unauthenticated publish cannot fill the
  store or shadow a `template_id@version`. Fix: strict charset + length
  validation (null byte, control char, path separator, `..`, leading `.`,
  >256 len, non-str) + signature-count cap → `PublishInputError`.

- **MED-1 (offline cache pin-rollback)** — the offline cache was keyed by
  `id_version` only, so a superseded-but-validly-signed version could be served
  offline with NO rollback signal. Fix: key by `(id_version, content_hash)` AND
  track the highest-seen `published_at` per `id_version`, refusing a cached
  entry older than the highest seen with `StaleOfflineTemplateError`.

Per `rules/testing.md` § Regression Testing: behavioral assertions (call the
function, assert raise/return), permanent marker, never deleted / silently
skipped.
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.envelope.template_resolver import TemplateRef
from envoy.registry.errors import (
    LibraryUnreachableError,
    PublishInputError,
    StaleOfflineTemplateError,
    StewardQuorumInputError,
)
from envoy.registry.fv_resolver import FoundationVerifiedTemplateResolver
from envoy.registry.library_app import LibraryRegistryHandlers, build_library_nexus
from envoy.registry.steward_quorum import MAX_STEWARD_SIGNATURES, verify_steward_quorum
from envoy.registry.storage import ContentAddressedStore, Tier

CONTENT = {
    "schema_version": "envelope-template/1",
    "template_id": "family-starter",
    "constraints": {"financial": {"daily_cap_microdollars": 5_000_000}},
}


class _ToggleClient:
    """Real Nexus-registered `library.fetch` client with a transport-down toggle."""

    def __init__(self, nexus_app) -> None:
        self._fn = nexus_app._handler_registry["library.fetch"]["handler"]
        self.online = True

    def fetch(self, *, template_id_version=None, content_hash=None):
        if not self.online:
            raise LibraryUnreachableError("endpoint unreachable")
        return self._fn(template_id_version=template_id_version, content_hash=content_hash)


# --------------------------------------------------------------------------
# MED-2 — verify-cost DoS: oversized signature array rejected before verify
# --------------------------------------------------------------------------


@pytest.mark.regression
async def test_med2_oversized_signature_array_rejected_before_verify() -> None:
    km = InMemoryKeyManager()
    content_hash = "deadbeef" * 8

    class _CountingKeyManager:
        """Fails loudly if verify() is ever reached — proves the cap fires first."""

        verify_calls = 0

        async def verify(self, payload, signature, public_key) -> bool:
            type(self).verify_calls += 1
            raise AssertionError("verify() must NOT be reached past the size cap")

    # One more than the bound — the array never has to be cryptographically valid
    # because the cap rejects it before a single verify.
    oversized = [
        {"steward_pubkey_hex": f"k{i}", "signature_hex": f"s{i}"}
        for i in range(MAX_STEWARD_SIGNATURES + 1)
    ]
    with pytest.raises(StewardQuorumInputError, match="verify-cost DoS"):
        await verify_steward_quorum(
            2,
            content_hash,
            oversized,
            pinned_pubkeys=set(),
            revocation_list=set(),
            key_manager=_CountingKeyManager(),
        )
    assert _CountingKeyManager.verify_calls == 0
    # Sanity: an at-the-bound array does NOT trip the size guard (it fails the
    # quorum normally, not the input bound) — proves the cap is a ceiling, not a
    # floor.
    _priv, pub = await km.generate_keypair("steward-a")
    at_bound = [
        {"steward_pubkey_hex": pub, "signature_hex": "x"} for _ in range(MAX_STEWARD_SIGNATURES)
    ]
    with pytest.raises(Exception) as exc_info:
        await verify_steward_quorum(
            2, content_hash, at_bound, pinned_pubkeys={pub}, revocation_list=set(), key_manager=km
        )
    assert not isinstance(exc_info.value, StewardQuorumInputError)


# --------------------------------------------------------------------------
# MED-3 — publish input validation: malformed / oversized publish rejected
# --------------------------------------------------------------------------


@pytest.fixture
def handlers() -> LibraryRegistryHandlers:
    return LibraryRegistryHandlers(store=ContentAddressedStore())


@pytest.mark.regression
@pytest.mark.parametrize(
    "bad_id",
    [
        "",  # empty
        "..",  # path traversal
        "a/b",  # path separator
        "a\\b",  # backslash separator
        "with\x00null",  # null byte
        "with\x01ctrl",  # control char
        ".hidden",  # leading dot
        "x" * 257,  # over length
    ],
)
def test_med3_malformed_template_id_rejected(handlers, bad_id) -> None:
    with pytest.raises(PublishInputError):
        handlers.publish(
            template_id=bad_id,
            version="v3",
            content=CONTENT,
            tier=Tier.FOUNDATION_VERIFIED.value,
            steward_signatures=[],
            published_at="2026-06-08T00:00:00Z",
        )


@pytest.mark.regression
def test_med3_malformed_version_rejected(handlers) -> None:
    with pytest.raises(PublishInputError, match="version"):
        handlers.publish(
            template_id="family-starter",
            version="../etc/passwd",
            content=CONTENT,
            tier=Tier.FOUNDATION_VERIFIED.value,
            steward_signatures=[],
            published_at="2026-06-08T00:00:00Z",
        )


@pytest.mark.regression
def test_med3_non_str_template_id_rejected(handlers) -> None:
    with pytest.raises(PublishInputError, match="must be str"):
        handlers.publish(
            template_id=12345,  # type: ignore[arg-type]
            version="v3",
            content=CONTENT,
            tier=Tier.FOUNDATION_VERIFIED.value,
            steward_signatures=[],
            published_at="2026-06-08T00:00:00Z",
        )


@pytest.mark.regression
def test_med3_oversized_steward_signatures_rejected(handlers) -> None:
    oversized = [
        {"steward_pubkey_hex": f"k{i}", "signature_hex": f"s{i}"}
        for i in range(MAX_STEWARD_SIGNATURES + 1)
    ]
    with pytest.raises(PublishInputError, match="exceeds max"):
        handlers.publish(
            template_id="family-starter",
            version="v3",
            content=CONTENT,
            tier=Tier.FOUNDATION_VERIFIED.value,
            steward_signatures=oversized,
            published_at="2026-06-08T00:00:00Z",
        )


@pytest.mark.regression
def test_med3_valid_publish_still_succeeds(handlers) -> None:
    # The guard must not reject a legitimate FV publish.
    out = handlers.publish(
        template_id="family-starter",
        version="v3",
        content=CONTENT,
        tier=Tier.FOUNDATION_VERIFIED.value,
        steward_signatures=[],
        published_at="2026-06-08T00:00:00Z",
    )
    assert out["tier"] == Tier.FOUNDATION_VERIFIED.value


# --------------------------------------------------------------------------
# MED-1 — offline cache pin-rollback: stale version refused offline
# --------------------------------------------------------------------------


async def _publish_fv(handlers, store, km, *, version: str, content, published_at: str):
    ch = store.compute_hash(content)
    _pa, pub_a = await km.generate_keypair("steward-a")
    _pb, pub_b = await km.generate_keypair("steward-b")
    sigs = [
        {
            "steward_pubkey_hex": pub_a,
            "signature_hex": km.sign_with_key("steward-a", ch.encode()),
        },
        {
            "steward_pubkey_hex": pub_b,
            "signature_hex": km.sign_with_key("steward-b", ch.encode()),
        },
    ]
    handlers.publish(
        template_id="family-starter",
        version=version,
        content=content,
        tier=Tier.FOUNDATION_VERIFIED.value,
        steward_signatures=sigs,
        published_at=published_at,
    )
    return ch, {pub_a, pub_b}


@pytest.mark.regression
async def test_med1_stale_offline_pin_rollback_refused() -> None:
    """An offline resolve must refuse a superseded-but-signed cached version.

    Sequence: resolve the published version online (caches it + sets the
    freshness high-water at its published_at) → a NEWER published_at is observed
    for the same id (high-water advances past the cached slot's timestamp) → go
    offline with only the OLD cache slot → the resolver refuses the stale slot
    with `StaleOfflineTemplateError` rather than silently serving the
    rolled-back version.
    """
    store = ContentAddressedStore()
    handlers = LibraryRegistryHandlers(store=store)
    app = build_library_nexus(handlers, api_port=18961, mcp_port=18962)
    try:
        km = InMemoryKeyManager()

        ch, pinned = await _publish_fv(
            handlers,
            store,
            km,
            version="v3",
            content=dict(CONTENT),
            published_at="2026-06-08T00:00:00Z",
        )
        client = _ToggleClient(app)
        resolver = FoundationVerifiedTemplateResolver(
            client=client, key_manager=km, pinned_pubkeys=pinned
        )
        ref = TemplateRef("foundation-verified:family-starter@v3")

        # 1. Online resolve caches the version + sets the freshness high-water at its
        #    published_at (2026-06-08).
        first = await resolver.resolve_async(ref)
        assert first.template_hash == ch
        assert resolver._highest_published_at["family-starter@v3"] == "2026-06-08T00:00:00Z"

        # 2. The resolver observes a NEWER published_at for the same id (a superseding
        #    publish was seen online) — the freshness high-water advances PAST the
        #    cached slot's timestamp. This is the exact state the guard defends.
        resolver._note_published_at("family-starter@v3", "2026-06-09T00:00:00Z")

        # 3. Endpoint down; the only cache slot is the OLD (2026-06-08) version, but
        #    the high-water is 2026-06-09 → stale pin-rollback refused, NOT served.
        client.online = False
        with pytest.raises(StaleOfflineTemplateError, match="superseded"):
            await resolver.resolve_async(ref)
    finally:
        # Release the Nexus AsyncLocalRuntime — otherwise a GC-time "Unclosed
        # Nexus" ResourceWarning surfaces under -W default (envoy-owned leak; T-01).
        app.close()


@pytest.mark.regression
async def test_med1_offline_current_version_still_served() -> None:
    """The freshness guard must NOT refuse the CURRENT cached version offline."""
    store = ContentAddressedStore()
    handlers = LibraryRegistryHandlers(store=store)
    app = build_library_nexus(handlers, api_port=18963, mcp_port=18964)
    try:
        km = InMemoryKeyManager()

        ch, pinned = await _publish_fv(
            handlers,
            store,
            km,
            version="v3",
            content=dict(CONTENT),
            published_at="2026-06-08T00:00:00Z",
        )
        client = _ToggleClient(app)
        resolver = FoundationVerifiedTemplateResolver(
            client=client, key_manager=km, pinned_pubkeys=pinned
        )
        ref = TemplateRef("foundation-verified:family-starter@v3")

        online = await resolver.resolve_async(ref)
        assert online.template_hash == ch

        # Offline hit on the SAME (current) version: published_at == high-water,
        # not less-than → served, not refused.
        client.online = False
        offline = await resolver.resolve_async(ref)
        assert offline.template_hash == ch
        assert offline.template_origin == "foundation-verified"
    finally:
        app.close()  # release the Nexus AsyncLocalRuntime (T-01 envoy-owned leak)
