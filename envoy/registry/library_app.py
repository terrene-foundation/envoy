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

**Publish is an air-gapped-ceremony-only entry, NOT network-exposed this phase.**
FV `library.publish` records bytes + steward signatures produced offline by the
Foundation's air-gapped signing ceremony; the Nexus `publish` handler is NOT a
network-writable surface in Phase-02 (the FV read path — `fetch` / `resolve_tier`
/ `list` — is the only live network surface; Community/Org publish is gated off
behind `CommunityPublishingDisabledError`). There is no authenticated-publish
seam to gate on yet, so the publish handler hardens its UNTRUSTED inputs
defensively (strict `template_id` / `version` charset + length validation +
bounded `steward_signatures`) so that even if a garbage / unauthenticated
publish reaches it, it cannot fill the store with junk or shadow a legitimate
`template_id@version`. When an auth seam lands (Phase-03+), gate the handler on
it; until then, input-bounds hardening is the structural defense.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from envoy.registry.errors import (
    CommunityPublishingDisabledError,
    PublishInputError,
)
from envoy.registry.steward_quorum import MAX_STEWARD_SIGNATURES
from envoy.registry.storage import ContentAddressedStore, LibraryRecord, Tier

# The Phase at which Community-tier publishing opens (deep-dive § 1.1).
_COMMUNITY_PUBLISH_PHASE = "Phase-03"

# Max length for a `template_id` / `version` identifier on the publish path.
# Mirrors the S4 `_validate_id_safety` 256-char DoS guard; identifiers feed
# content-store metadata keys, never raw filesystem paths, but the same bound
# blocks a memory-DoS via a multi-megabyte identifier.
_MAX_IDENTIFIER_LEN = 256


def _validate_publish_identifier(value: object, *, field: str) -> str:
    """Validate a `template_id` / `version` from the UNTRUSTED publish surface.

    Mirrors S4's `_validate_id_safety` (`envoy/trust/store.py`): reject inputs
    that could enable path-traversal, null-byte, or control-character attacks,
    or a memory-DoS via an oversized identifier. Returns the validated `str`.

    Raises `PublishInputError` on:
      - non-`str`
      - empty
      - length > 256 (DoS guard)
      - leading `.` (hidden-file shape)
      - null byte (`\\x00`) or any C0/C1 control character
      - `/` or `\\` (path separator)
      - `..` (path traversal)

    These identifiers index content-store metadata (`template_id@version`); a
    crafted value MUST NOT be able to shadow another entry's key or smuggle a
    traversal component into a future filesystem-backed persistence target.
    """
    if not isinstance(value, str):
        raise PublishInputError(f"{field} must be str (got {type(value).__name__})")
    if not value:
        raise PublishInputError(f"{field} must not be empty")
    if len(value) > _MAX_IDENTIFIER_LEN:
        raise PublishInputError(f"{field} length {len(value)} exceeds max {_MAX_IDENTIFIER_LEN}")
    if value.startswith("."):
        raise PublishInputError(f"{field} must not start with '.' (hidden-file shape)")
    if "\x00" in value:
        raise PublishInputError(f"{field} contains null byte")
    if any(unicodedata.category(ch) == "Cc" or 0x7F <= ord(ch) < 0xA0 for ch in value):
        raise PublishInputError(f"{field} contains control character")
    if "/" in value or "\\" in value:
        raise PublishInputError(f"{field} contains path separator")
    if ".." in value:
        raise PublishInputError(f"{field} contains '..' (path traversal)")
    return value


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
            # `published_at` rides along as the freshness marker the offline
            # resolver uses to refuse a cached entry that a newer (supersedes)
            # publish has rolled forward past (pin-rollback defense).
            "published_at": record.published_at,
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

        Defensive input hardening (this surface is air-gapped-ceremony-only and
        NOT network-writable this phase — see module docstring): `template_id`
        and `version` are validated against a strict charset + length, and
        `steward_signatures` is bounded by `MAX_STEWARD_SIGNATURES`, so an
        unauthenticated / garbage publish cannot fill the store or shadow a
        `template_id@version`. Validation runs BEFORE the tier gate so a
        malformed identifier is rejected regardless of tier.
        """
        validated_id = _validate_publish_identifier(template_id, field="template_id")
        validated_version = _validate_publish_identifier(version, field="version")
        n_sigs = len(steward_signatures)
        if n_sigs > MAX_STEWARD_SIGNATURES:
            raise PublishInputError(
                f"steward_signatures length {n_sigs} exceeds max "
                f"{MAX_STEWARD_SIGNATURES} (verify-cost DoS guard)"
            )
        tier_enum = Tier(tier)
        if tier_enum is not Tier.FOUNDATION_VERIFIED and not self.community_publish_enabled:
            raise CommunityPublishingDisabledError(
                f"{tier_enum.value} publishing opens {_COMMUNITY_PUBLISH_PHASE}"
            )
        record = self.store.put(
            template_id=validated_id,
            version=validated_version,
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
