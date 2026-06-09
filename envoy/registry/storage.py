# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.registry.storage — content-addressed Envelope Library blob store.

`specs/foundation-ops.md` registry #1: "Content-addressed storage." The storage
key IS `sha256(canonical_bytes(content))` over the existing
`envoy.envelope.canonical_bytes` pipeline (`01-analysis/...04-ws4...` § 1.3), so
cross-SDK byte-identity holds and the same hash anchors the Trust store, Ledger,
and the resolver's re-verify.

This module is the FOUNDATION-OPERATED registry's in-process storage: a
content-addressed blob store keyed by `content_hash`, plus a metadata table
mapping `template_id@version → content_hash + tier + steward_signatures[] +
published_at`. The deep-dive's DataFlow `@db.model` recommendation is the
persistence target for a multi-process Foundation deployment; this phase ships
the in-process store the Nexus handler set serves and the Tier-2 harness
exercises end-to-end. The blob/metadata SHAPE matches the `@db.model` columns
1:1 so the persistence swap is a backing-store change, not an API change.

The store NEVER verifies signatures — verification is the CONSUMER's job
against pinned keys (`fv_resolver`). Storage only addresses + retrieves.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from envoy.envelope.canonical_bytes import canonical_bytes, content_hash


class Tier(enum.Enum):
    """Envelope Library trust tier (`specs/envelope-library.md` § Trust tiers).

    SHAPE-present for all three tiers this phase; only FOUNDATION_VERIFIED
    resolves + publishes. COMMUNITY/ORGANIZATION publish is gated off (Phase 03
    / Phase 04) — the enum exists so the Phase-03 enable is a flag flip, not a
    new tier.
    """

    FOUNDATION_VERIFIED = "FV"
    COMMUNITY = "community"
    ORGANIZATION = "organization"


@dataclass(frozen=True, slots=True)
class LibraryRecord:
    """Metadata row mapping a `template_id@version` to its content-addressed blob.

    Mirrors the deep-dive's `@db.model` column set: `template_id@version →
    content_hash + tier + steward_signatures[] + published_at`.
    """

    template_id: str
    version: str
    content_hash: str
    tier: Tier
    steward_signatures: tuple[Mapping[str, str], ...]
    published_at: str

    @property
    def qualified_id(self) -> str:
        """`<template_id>@<version>` — the catalog lookup key."""
        return f"{self.template_id}@{self.version}"


@dataclass(slots=True)
class ContentAddressedStore:
    """In-process content-addressed blob store + metadata index.

    `content_hash → canonical content bytes` for the blob half; `qualified_id →
    LibraryRecord` + `content_hash → LibraryRecord` for the metadata half.
    Content is addressed by `sha256(canonical_bytes(content))`, computed here at
    publish time so the address is the SAME hash the consumer re-derives.
    """

    _blobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _by_qualified_id: dict[str, LibraryRecord] = field(default_factory=dict)
    _by_content_hash: dict[str, LibraryRecord] = field(default_factory=dict)

    def compute_hash(self, content: Mapping[str, Any]) -> str:
        """`sha256(canonical_bytes(content))` — the content address."""
        return content_hash(canonical_bytes(dict(content)))

    def put(
        self,
        *,
        template_id: str,
        version: str,
        content: Mapping[str, Any],
        tier: Tier,
        steward_signatures: Sequence[Mapping[str, str]],
        published_at: str,
    ) -> LibraryRecord:
        """Store content addressed by its canonical hash + index the metadata.

        Returns the `LibraryRecord`. The blob is stored under its content hash;
        the metadata is indexed by both `template_id@version` and `content_hash`
        so `library.fetch` can resolve by either key.
        """
        ch = self.compute_hash(content)
        record = LibraryRecord(
            template_id=template_id,
            version=version,
            content_hash=ch,
            tier=tier,
            steward_signatures=tuple(dict(s) for s in steward_signatures),
            published_at=published_at,
        )
        self._blobs[ch] = dict(content)
        self._by_qualified_id[record.qualified_id] = record
        self._by_content_hash[ch] = record
        return record

    def get_by_qualified_id(self, qualified_id: str) -> LibraryRecord | None:
        """Look up a record by `<template_id>@<version>`."""
        return self._by_qualified_id.get(qualified_id)

    def get_by_content_hash(self, ch: str) -> LibraryRecord | None:
        """Look up a record by `content_hash`."""
        return self._by_content_hash.get(ch)

    def get_content(self, ch: str) -> dict[str, Any] | None:
        """Fetch the canonical content blob for a `content_hash`."""
        blob = self._blobs.get(ch)
        return dict(blob) if blob is not None else None

    def list_records(self, tier: Tier | None = None) -> list[LibraryRecord]:
        """Catalog browse; optionally filtered to one tier (FV-only this phase)."""
        records = list(self._by_qualified_id.values())
        if tier is not None:
            records = [r for r in records if r.tier is tier]
        return records


__all__ = ["ContentAddressedStore", "LibraryRecord", "Tier"]
