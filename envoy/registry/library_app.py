# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.registry.library_app — the Envelope Library Nexus handler set.

`specs/foundation-ops.md` registry #1: "Nexus-backed HTTP/CLI/MCP". Per
`rules/framework-first.md`, the registry is ONE Nexus handler set — NOT
hand-written axum/HTTP routes (direct framework use is BLOCKED). Each
`@nexus.handler(name=...)` deploys to HTTP + CLI + MCP from one definition.

The handler set is tier-aware from day one (the tier is a field on every
record), but the Community/Organization PUBLISH path is gated off behind a
feature flag that raises `CommunityPublishingDisabledError` — the Nexus layer
renders this as an HTTP 503 "Community publishing opens Phase-03" refusal
(`specs/envelope-library.md` Community row; deep-dive § 1.1 + gap #2). The
FV read path (`library.fetch` / `library.resolve_tier` / `library.list`) is
LIVE this phase.

The handlers are pure functions over a `ContentAddressedStore` — they NEVER
verify signatures (the consumer re-verifies locally against pinned keys;
`fv_resolver`). This keeps the Nexus transport untrusted by construction: a
compromised registry can only change bytes, and the consumer's re-hash +
quorum-verify catches that.

`build_library_nexus(...)` registers the handler set on a real `Nexus`
instance (the deep-dive's "ONE NexusApp handler set"); `LibraryRegistryHandlers`
exposes the same callables for the Tier-2 harness to drive through the real
registry without binding a port.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from envoy.registry.errors import CommunityPublishingDisabledError
from envoy.registry.storage import ContentAddressedStore, LibraryRecord, Tier

# The Phase at which Community-tier publishing opens (deep-dive § 1.1).
_COMMUNITY_PUBLISH_PHASE = "Phase-03"


def _record_to_wire(record: LibraryRecord) -> dict[str, Any]:
    """Serialize a `LibraryRecord` to the wire shape `library.resolve_tier`
    returns (no content — metadata + steward signatures only)."""
    return {
        "template_id": record.template_id,
        "version": record.version,
        "content_hash": record.content_hash,
        "tier": record.tier.value,
        "steward_signatures": [dict(s) for s in record.steward_signatures],
        "published_at": record.published_at,
    }


@dataclass(slots=True)
class LibraryRegistryHandlers:
    """The Envelope Library registry handler set bound to one content store.

    Each method IS a Nexus handler body. They are exposed as plain callables so
    the Tier-2 harness drives the REAL registry logic (not a mock) and
    `build_library_nexus` wires the SAME callables onto a `Nexus` app for the
    HTTP/CLI/MCP surfaces.
    """

    store: ContentAddressedStore
    community_publish_enabled: bool = False

    def fetch(
        self,
        *,
        template_id_version: str | None = None,
        content_hash: str | None = None,
    ) -> dict[str, Any] | None:
        """`library.fetch` — content-addressed read by `id@version` OR `content_hash`.

        Returns `{content, content_hash, tier, steward_signatures}` or None when
        absent (the resolver maps None to `LibraryUnreachableError` only when
        the cache also misses). The registry returns bytes + the published
        steward signatures; it does NOT assert they are valid — that is the
        consumer's re-verify.
        """
        record: LibraryRecord | None = None
        if content_hash is not None:
            record = self.store.get_by_content_hash(content_hash)
        elif template_id_version is not None:
            record = self.store.get_by_qualified_id(template_id_version)
        if record is None:
            return None
        content = self.store.get_content(record.content_hash)
        if content is None:  # blob/metadata divergence — treat as absent
            return None
        return {
            "content": content,
            "content_hash": record.content_hash,
            "tier": record.tier.value,
            "steward_signatures": [dict(s) for s in record.steward_signatures],
        }

    def resolve_tier(self, *, template_id_version: str) -> dict[str, Any] | None:
        """`library.resolve_tier` — tier + steward signature set, no content."""
        record = self.store.get_by_qualified_id(template_id_version)
        return _record_to_wire(record) if record is not None else None

    def list_catalog(self, *, tier: str = Tier.FOUNDATION_VERIFIED.value) -> list[dict[str, Any]]:
        """`library.list` — catalog browse (FV-only this phase)."""
        tier_enum = Tier(tier)
        return [_record_to_wire(r) for r in self.store.list_records(tier=tier_enum)]

    def publish(
        self,
        *,
        template_id: str,
        version: str,
        content: Mapping[str, Any],
        tier: str,
        steward_signatures: Sequence[Mapping[str, str]],
        published_at: str,
    ) -> dict[str, Any]:
        """`library.publish` — FV ceremony entry; Community/Org typed refusal.

        FV: stores the content-addressed blob + metadata (the published steward
        signatures ride along; they are produced by the offline air-gapped
        ceremony, never by this code). Community/Org: raises
        `CommunityPublishingDisabledError` (rendered HTTP 503) unless the
        feature flag is flipped (Phase-03 enable).
        """
        tier_enum = Tier(tier)
        if tier_enum is not Tier.FOUNDATION_VERIFIED and not self.community_publish_enabled:
            raise CommunityPublishingDisabledError(
                f"{tier_enum.value} publishing opens {_COMMUNITY_PUBLISH_PHASE}"
            )
        record = self.store.put(
            template_id=template_id,
            version=version,
            content=content,
            tier=tier_enum,
            steward_signatures=steward_signatures,
            published_at=published_at,
        )
        return {"content_hash": record.content_hash, "tier": record.tier.value}


def build_library_nexus(
    handlers: LibraryRegistryHandlers,
    *,
    api_port: int = 8000,
    mcp_port: int = 3001,
) -> Any:
    """Register the Envelope Library handler set on a real `Nexus` instance.

    Returns the `Nexus` app with `library.fetch` / `library.resolve_tier` /
    `library.list` / `library.publish` registered across HTTP + CLI + MCP. The
    caller `.start()`s it for a live deployment. The import is lazy because the
    Nexus runtime is heavy and the Tier-2 quorum/resolver tests drive
    `LibraryRegistryHandlers` directly (the real registry logic) without a
    port bind.
    """
    from nexus import Nexus  # noqa: PLC0415 — lazy: heavy Nexus runtime import

    app = Nexus(api_port=api_port, mcp_port=mcp_port)

    @app.handler("library.fetch", description="Content-addressed Envelope Library read")
    def library_fetch(
        template_id_version: str | None = None,
        content_hash: str | None = None,
    ) -> dict[str, Any] | None:
        return handlers.fetch(template_id_version=template_id_version, content_hash=content_hash)

    @app.handler(
        "library.resolve_tier", description="Resolve a template's tier + steward signatures"
    )
    def library_resolve_tier(template_id_version: str) -> dict[str, Any] | None:
        return handlers.resolve_tier(template_id_version=template_id_version)

    @app.handler("library.list", description="Catalog browse (Foundation-Verified)")
    def library_list(tier: str = Tier.FOUNDATION_VERIFIED.value) -> list[dict[str, Any]]:
        return handlers.list_catalog(tier=tier)

    @app.handler("library.publish", description="FV ceremony entry; Community/Org gated off")
    def library_publish(
        template_id: str,
        version: str,
        content: Mapping[str, Any],
        tier: str,
        steward_signatures: Sequence[Mapping[str, str]],
        published_at: str,
    ) -> dict[str, Any]:
        return handlers.publish(
            template_id=template_id,
            version=version,
            content=content,
            tier=tier,
            steward_signatures=steward_signatures,
            published_at=published_at,
        )

    return app


__all__ = ["LibraryRegistryHandlers", "build_library_nexus"]
