"""envoy.trust dataclass types.

Lightweight envoy-side types that wrap `kailash.trust.chain.GenesisRecord`,
`DelegationRecord`, and `TrustLineageChain` with envoy-namespaced aliases —
keeping the envoy import surface stable across kailash-py versions.

Per shard 5 § 4 step 1 + `rules/tenant-isolation.md` Rule 2: every type that
touches per-principal state carries `principal_id` (no defaults).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# `PrincipalId` is the canonical envoy alias for kailash-py's "agent_id" (which
# kailash-py uses generically). The envoy spec uses "principal_id" everywhere
# for `rules/tenant-isolation.md` consistency. We expose both names so callers
# from either spec read cleanly.
PrincipalId = str


@dataclass(frozen=True, slots=True)
class GenesisSeed:
    """Inputs to `TrustStoreAdapter.seed_genesis()`.

    Per `specs/trust-vault.md` § Genesis ritual. The capabilities list seeds
    the principal's initial authority surface; subsequent delegations
    (`TrustStoreAdapter.record_delegation()`) fan out from this Genesis.
    """

    principal_id: PrincipalId
    authority_id: str
    capabilities: tuple[str, ...]
    constraints: tuple[str, ...] = ()
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Output of `TrustStoreAdapter.seed_genesis()`.

    Mirrors a stripped-down view of `kailash.trust.chain.TrustLineageChain` —
    enough for downstream primitives (Boundary Conversation, Grant Moment,
    Daily Digest) to reference the Genesis without importing the full chain
    type.
    """

    principal_id: PrincipalId
    chain_hash: str  # hex sha256
    genesis_signature_algorithm: str  # e.g. "ed25519+sha256"
    capabilities_seeded: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DelegationRequest:
    """Inputs to `TrustStoreAdapter.record_delegation()`.

    Per shard 5 § 4 step 2 (R2-M-04 carry-forward): delegations route through
    `kailash.trust.TrustOperations.delegate(...)` 10-step verification (cycle-
    free, depth ≤ 16). The record produced has its `algorithm_identifier`
    routed through `_with_algorithm_id()` (T-01-15 R2-H-01 LOAD-BEARING) so the
    spec-mandated 3-key wire form lands on disk.
    """

    delegator_id: PrincipalId
    delegatee_id: PrincipalId
    task_id: str
    capabilities: tuple[str, ...]
    additional_constraints: tuple[str, ...] = ()
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
