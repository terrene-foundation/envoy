# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.registry — Foundation registry surface (Phase 02 WS-4, shard S8).

Ships the Foundation-Verified Envelope Library read+verify path:

- ``verify_steward_quorum`` — the SHARED 2-of-N steward-quorum verifier built
  exactly once (reused by S8e EDR + S9b classifier registry).
- ``ContentAddressedStore`` / ``Tier`` — content-addressed blob store + tier model.
- ``LibraryRegistryHandlers`` / ``build_library_nexus`` — the Nexus handler set
  (``library.fetch`` / ``library.resolve_tier`` / ``library.list`` /
  ``library.publish``) deploying to HTTP + CLI + MCP from one definition.
- ``FoundationVerifiedTemplateResolver`` — the consumer-side resolver that
  re-hashes + quorum-verifies LOCALLY against pinned keys (never the transport).

Community/Organization tiers are SHAPE-present but publish-gated (Phase 03/04).
"""

from __future__ import annotations

from envoy.registry.errors import (
    CommunityPublishingDisabledError,
    FVTierMembershipNotProvenError,
    LibraryError,
    LibraryUnreachableError,
    PublisherSignatureInvalidError,
    StewardQuorumError,
    StewardQuorumInputError,
    StewardQuorumReason,
    TemplateHashMismatchError,
)
from envoy.registry.fv_resolver import FoundationVerifiedTemplateResolver
from envoy.registry.library_app import LibraryRegistryHandlers, build_library_nexus
from envoy.registry.steward_quorum import verify_steward_quorum
from envoy.registry.storage import ContentAddressedStore, LibraryRecord, Tier

__all__ = [
    "CommunityPublishingDisabledError",
    "ContentAddressedStore",
    "FVTierMembershipNotProvenError",
    "FoundationVerifiedTemplateResolver",
    "LibraryError",
    "LibraryRecord",
    "LibraryRegistryHandlers",
    "LibraryUnreachableError",
    "PublisherSignatureInvalidError",
    "StewardQuorumError",
    "StewardQuorumInputError",
    "StewardQuorumReason",
    "TemplateHashMismatchError",
    "Tier",
    "build_library_nexus",
    "verify_steward_quorum",
]
