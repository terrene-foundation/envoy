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
        # by qualified id so an OFFLINE re-resolve can re-verify the same
        # (content, content_hash, signatures) against pinned keys without the
        # registry (deep-dive gap #4 — the cache is never a trust bypass).
        self._cache_by_id: dict[str, tuple[dict[str, Any], str, list[Mapping[str, str]]]] = {}

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
        fetched, declared_hash, signatures = await self._fetch_or_cache(id_version)

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

        # (d) cache the verified (content, hash, signatures) under the qualified
        # id so an offline re-resolve re-verifies it against pinned keys; return.
        self._cache_by_id[id_version] = (
            dict(fetched),
            declared_hash,
            [dict(s) for s in signatures],
        )
        return EnvelopeTemplate(
            ref=ref,
            content=fetched,
            template_hash=declared_hash,
            template_origin="foundation-verified",
        )

    async def _fetch_or_cache(
        self, id_version: str
    ) -> tuple[dict[str, Any], str, list[Mapping[str, str]]]:
        """Fetch from the Nexus client; fall back to the content-addressed cache
        on transport failure. Raises `LibraryUnreachableError` when the endpoint
        is unreachable AND no cache entry exists."""
        try:
            result = self._client.fetch(template_id_version=id_version)
        except LibraryUnreachableError:
            result = None
            transport_down = True
        else:
            transport_down = False

        if result is not None:
            return (
                dict(result["content"]),
                result["content_hash"],
                list(result["steward_signatures"]),
            )

        # Network miss/none → fall back to the content-addressed cache. The
        # cache holds the LAST verified (content, content_hash, signatures) for
        # this qualified id; the caller still re-hashes + re-quorum-verifies it
        # against pinned keys (steps b+c), so the cache is never a trust bypass.
        cached = self._cache_by_id.get(id_version)
        if cached is not None:
            content, declared_hash, signatures = cached
            return dict(content), declared_hash, list(signatures)

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
