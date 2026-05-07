"""envoy.trust — TrustStoreAdapter + lineage primitives.

Implements `specs/trust-vault.md` + `specs/trust-lineage.md`. Per shard 5
(`workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md`),
this module composes `kailash.trust.chain_store.sqlite.SqliteTrustStore` and
`kailash.trust.posture.posture_store.SQLitePostureStore` behind a
principal-id-keyed adapter — the integration boundary between envoy primitives
(Boundary Conversation, Grant Moment, Daily Digest, etc.) and the kailash-py
trust persistence layer.

Public facade per `rules/orphan-detection.md` Rule 6.
"""

from envoy.trust.errors import (
    GenesisAlreadySeededError,
    PrincipalRequiredError,
    TrustStoreError,
)
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.types import (
    DelegationRequest,
    GenesisSeed,
    PrincipalId,
    SeedResult,
)
from envoy.trust.vault import DEFAULT_IDLE_TTL_SECONDS, TrustVault

__all__ = [
    # Facade
    "TrustStoreAdapter",
    "TrustVault",
    "DEFAULT_IDLE_TTL_SECONDS",
    # Errors (re-exported per package skeleton § 2.2 typed-error import contract)
    "GenesisAlreadySeededError",
    "PrincipalRequiredError",
    "TrustStoreError",
    # Types
    "DelegationRequest",
    "GenesisSeed",
    "PrincipalId",
    "SeedResult",
]
