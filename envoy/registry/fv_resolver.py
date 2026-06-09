# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.registry.fv_resolver — Foundation-Verified template resolver (S8).

Implements `FoundationVerifiedTemplateResolver`, the Phase-02 resolver named in
the frozen Protocol docstring at `envoy/envelope/template_resolver.py:52-53`. It
is a thin Nexus-client + local-verify + content-addressed-cache wrapper around
the existing `canonical_bytes`/`content_hash` + the shared
`verify_steward_quorum` primitives (deep-dive § 1.4 + § 2.2).

The consumer NEVER trusts the Nexus transport. The trust anchor is the PINNED
Foundation stewardship key set + the cached revocation list. The read path
(`specs/envelope-library.md` § Trust tiers FV + § Error taxonomy):

  resolve("foundation-verified:family-starter@v3"):
    a. library.fetch over the Nexus client → {content, content_hash, tier,
       steward_signatures}.  Endpoint unreachable + cache MISS → LibraryUnreachableError.
    b. re-hash sha256(canonical_bytes(content)) == content_hash
       → else TemplateHashMismatchError  (supply-chain tamper).
    c. verify ≥2 distinct steward signatures over content_hash against the
       client-pinned Foundation stewardship key set + revocation list via the
       SHARED verify_steward_quorum → else FVTierMembershipNotProvenError /
       PublisherSignatureInvalidError.
    d. cache the verified content addressed by content_hash; return
       EnvelopeTemplate(template_origin="foundation-verified").

Offline (`LibraryUnreachableError` row): a content-addressed cache HIT is STILL
re-hashed + quorum-verified against pinned keys before return — the cache is
never a trust bypass (deep-dive gap #4). A cache MISS while offline raises
`LibraryUnreachableError`.

Offline freshness / pin-rollback (gap #1): the cache is keyed by
`(id_version, content_hash)` — NOT `id_version` alone — and the resolver tracks
the highest `published_at` it has ever observed for each `id_version`. A cached
entry whose `published_at` is OLDER than that high-water mark is a SUPERSEDED
version that is still validly signed; serving it offline would be a silent
pin-rollback. The resolver refuses such an entry with `StaleOfflineTemplateError`
rather than returning stale-but-signed content. This is in addition to (not
instead of) the re-hash + re-quorum-verify on every cache hit.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from envoy.envelope.canonical_bytes import canonical_bytes, content_hash
from envoy.envelope.template_resolver import EnvelopeTemplate, TemplateRef
from envoy.registry.errors import (
    FVTierMembershipNotProvenError,
    LibraryUnreachableError,
    PublisherSignatureInvalidError,
    StaleOfflineTemplateError,
    StewardQuorumError,
    StewardQuorumReason,
    TemplateHashMismatchError,
)
from envoy.registry.steward_quorum import verify_steward_quorum

_FV_SCHEME = "foundation-verified:"
_FV_THRESHOLD = 2  # 2-of-N Foundation steward signing (specs/envelope-library.md)


class _LibraryFetchClient(Protocol):
    """The Nexus-client surface the resolver needs: a `library.fetch` call.

    Returns the fetch wire shape (`{content, content_hash, tier,
    steward_signatures}`) or None when the registry has no such entry, and
    RAISES `LibraryUnreachableError` when the transport itself is down. In the
    Tier-2 harness this is the real `LibraryRegistryHandlers.fetch`; in
    production it is the OHTTP/Nexus read-through client.
    """

    def fetch(
        self,
        *,
        template_id_version: str | None = ...,
        content_hash: str | None = ...,
    ) -> dict[str, Any] | None: ...


class _VerifyKeyManager(Protocol):
    async def verify(self, payload: Any, signature: str, public_key: str) -> bool: ...


class FoundationVerifiedTemplateResolver:
    """Resolve `foundation-verified:<id>@<version>` with LOCAL re-verification.

    Satisfies the frozen `EnvelopeTemplateResolver` Protocol
    (`envoy/envelope/template_resolver.py`). Holds the client-pinned Foundation
    stewardship key set + revocation list as the trust anchor — NOT the Nexus
    transport.
    """

    def __init__(
        self,
        *,
        client: _LibraryFetchClient,
        key_manager: _VerifyKeyManager,
        pinned_pubkeys: Iterable[str],
        revocation_list: Iterable[str] | None = None,
    ) -> None:
        self._client = client
        self._key_manager = key_manager
        self._pinned = set(pinned_pubkeys)
        self._revoked = set(revocation_list or ())
        # Content-addressed local cache populated on a successful verify, keyed
        # by (id_version, content_hash) so an OFFLINE re-resolve can re-verify
        # the same (content, content_hash, signatures, published_at) against
        # pinned keys without the registry (deep-dive gap #4 — the cache is never
        # a trust bypass). Keying on the content_hash (not id_version alone)
        # means a superseded version is a DISTINCT cache slot, never overwriting
        # the current one.
        self._cache_by_id: dict[
            tuple[str, str],
            tuple[dict[str, Any], str, list[Mapping[str, str]], str | None],
        ] = {}
        # Highest `published_at` ever observed per id_version — the freshness
        # high-water mark used to refuse a stale (pin-rollback) cached entry.
        self._highest_published_at: dict[str, str] = {}

    def resolve(self, ref: TemplateRef) -> EnvelopeTemplate:
        """Resolve an FV template; re-hash + quorum-verify locally.

        Sync per the frozen `EnvelopeTemplateResolver` Protocol. Drives the
        async quorum verify: directly via `asyncio.run` when no loop is running,
        or on a worker thread with its own loop when called from inside an
        already-running loop (so an async caller can still use the sync surface).
        `resolve_async` is the native path for async callers.
        """
        id_version = self._parse_uri(ref)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._resolve_async(ref, id_version))
        # A loop is already running on this thread — run the coroutine to
        # completion on a separate thread with its own event loop.
        import concurrent.futures  # noqa: PLC0415

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(self._resolve_async(ref, id_version))).result()

    async def resolve_async(self, ref: TemplateRef) -> EnvelopeTemplate:
        """Async-native resolve for callers already inside an event loop."""
        return await self._resolve_async(ref, self._parse_uri(ref))

    @staticmethod
    def _parse_uri(ref: TemplateRef) -> str:
        if not ref.uri.startswith(_FV_SCHEME):
            raise ValueError(
                f"FoundationVerifiedTemplateResolver only supports "
                f"'foundation-verified:' URIs (got {ref.uri!r})"
            )
        return ref.uri[len(_FV_SCHEME) :]

    async def _resolve_async(self, ref: TemplateRef, id_version: str) -> EnvelopeTemplate:
        fetched, declared_hash, signatures, published_at = await self._fetch_or_cache(id_version)

        # (b) re-hash before trust — the cache is re-verified the same way the
        # network fetch is, so an offline consumer is not a less-secure consumer.
        recomputed = content_hash(canonical_bytes(fetched))
        if recomputed != declared_hash:
            raise TemplateHashMismatchError(
                f"fetched template re-hash {recomputed!r} != declared "
                f"content_hash {declared_hash!r} (uri={ref.uri!r}) — suspected "
                "supply-chain tamper"
            )

        # (c) verify the 2-of-N steward quorum over the content_hash against the
        # client-pinned keys + revocation list. Map the base quorum error to the
        # Envelope Library FV taxonomy.
        try:
            await verify_steward_quorum(
                _FV_THRESHOLD,
                declared_hash,
                signatures,
                self._pinned,
                self._revoked,
                key_manager=self._key_manager,
            )
        except StewardQuorumError as exc:
            if exc.reason is StewardQuorumReason.REVOKED_KEY_PRESENT:
                # A revoked steward signature is a compromise signal, not just a
                # count shortfall — surface as a signature-invalid refusal.
                raise PublisherSignatureInvalidError(
                    f"FV steward quorum includes a revoked key (uri={ref.uri!r}); "
                    "refuse install — possible supply-chain compromise"
                ) from exc
            raise FVTierMembershipNotProvenError(
                f"FV-tier 2-of-N steward signing chain incomplete (uri={ref.uri!r}; "
                f"distinct_valid={exc.distinct_valid}, required={exc.threshold})"
            ) from exc

        # (d) cache the verified (content, hash, signatures, published_at) keyed
        # by (id_version, content_hash) so an offline re-resolve re-verifies it
        # against pinned keys; advance the per-id freshness high-water so a later
        # superseded cache hit is refused. Return.
        self._cache_by_id[(id_version, declared_hash)] = (
            dict(fetched),
            declared_hash,
            [dict(s) for s in signatures],
            published_at,
        )
        self._note_published_at(id_version, published_at)
        return EnvelopeTemplate(
            ref=ref,
            content=fetched,
            template_hash=declared_hash,
            template_origin="foundation-verified",
        )

    def _note_published_at(self, id_version: str, published_at: str | None) -> None:
        """Advance the per-id freshness high-water mark (lexicographic max).

        A `None` `published_at` (client/fixture on the pre-freshness wire shape)
        is a no-op: there is no freshness signal to advance the high-water with.

        `published_at` is an ISO-8601 UTC timestamp (`...Z`); ISO-8601 in UTC
        sorts lexicographically in chronological order, so `max(...)` over the
        string form is a correct freshness comparison without parsing.
        """
        if published_at is None:
            return
        prior = self._highest_published_at.get(id_version)
        if prior is None or published_at > prior:
            self._highest_published_at[id_version] = published_at

    async def _fetch_or_cache(
        self, id_version: str
    ) -> tuple[dict[str, Any], str, list[Mapping[str, str]], str | None]:
        """Fetch from the Nexus client; fall back to the content-addressed cache
        on transport failure. Raises `LibraryUnreachableError` when the endpoint
        is unreachable AND no cache entry exists; raises
        `StaleOfflineTemplateError` when the only available cache entry is a
        superseded (pin-rollback) version."""
        try:
            result = self._client.fetch(template_id_version=id_version)
        except LibraryUnreachableError:
            result = None
            transport_down = True
        else:
            transport_down = False

        if result is not None:
            # `published_at` is the freshness marker the FV registry emits; a
            # client/fixture on the pre-freshness wire shape may omit it, in
            # which case we degrade gracefully (cache keyed by content_hash,
            # no freshness refusal) rather than hard-failing the resolve.
            published_at = result.get("published_at")
            # An online fetch is authoritative for freshness — advance the
            # high-water mark so a subsequent OFFLINE hit on a superseded
            # cache slot is recognised as stale.
            self._note_published_at(id_version, published_at)
            return (
                dict(result["content"]),
                result["content_hash"],
                list(result["steward_signatures"]),
                published_at,
            )

        # Network miss/none → fall back to the content-addressed cache. The
        # cache holds verified (content, content_hash, signatures, published_at)
        # slots for this qualified id keyed by content_hash; the caller still
        # re-hashes + re-quorum-verifies (steps b+c), so the cache is never a
        # trust bypass. Among the cached slots for this id, prefer the freshest
        # by published_at and refuse it if it is OLDER than the high-water mark
        # (a superseded version → silent pin-rollback).
        candidates = [
            (entry, ch) for (cid, ch), entry in self._cache_by_id.items() if cid == id_version
        ]
        if candidates:
            high_water = self._highest_published_at.get(id_version)
            (content, declared_hash, signatures, published_at), _ = max(
                candidates, key=lambda c: (c[0][3] is not None, c[0][3] or "")
            )
            if high_water is not None and published_at is not None and published_at < high_water:
                raise StaleOfflineTemplateError(
                    f"offline cache for {id_version!r} holds only a superseded "
                    f"version (cached published_at {published_at!r} < highest "
                    f"seen {high_water!r}); refuse offline pin-rollback — reach "
                    "the network for the current version"
                )
            return dict(content), declared_hash, list(signatures), published_at

        # Endpoint unreachable / no entry AND no cache → offline notice.
        if transport_down:
            raise LibraryUnreachableError(
                f"Foundation Envelope Library unreachable and no local cache "
                f"entry for {id_version!r}"
            )
        # The registry is reachable but has no such template — also surfaced as
        # unreachable-class per the spec's "no local cache entry" row.
        raise LibraryUnreachableError(
            f"Envelope Library has no entry for {id_version!r} and no local cache"
        )


__all__ = ["FoundationVerifiedTemplateResolver"]
