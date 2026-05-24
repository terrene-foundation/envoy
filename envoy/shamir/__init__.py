"""envoy.shamir — Trust Vault Shamir 3-of-5 backup ritual.

Phase 01 implementation of `specs/shamir-recovery.md` per shard 15
(`workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md`).

T-02-34 ships the orchestration coordinator + Protocol slots for every
collaborator. T-02-35 adds concrete implementations (commitments + paper
renderer + checklist persister) plus the L-2 re-architecture making the
commitment binder storage-only. T-02-36 lands the recovery CLI; T-02-37
wires the Tier 2 round-trip.

Per `rules/orphan-detection.md` Rule 6, this facade re-exports the public
surface so callers import from one stable place.
"""

from envoy.shamir.commitments import (
    compute_commitment,
    verify_commitment,
)
from envoy.shamir.distribution_checklist import (
    TrustVaultChecklistPersister,
)
from envoy.shamir.errors import (
    ChecklistPersisterError,
    CommitmentVerificationFailedError,
    EnvoyLabelOnCardError,
    InsufficientSharesError,
    MasterKeyZeroizationError,
    RitualPreconditionError,
    ShamirRecoveryError,
    ShamirRitualError,
    ShardChecksumFailedError,
    ShardPublicCommitmentMissingError,
    ShardSlotLabelMismatchError,
    TooManySharesError,
)
from envoy.shamir.paper import (
    PaperShardCard,
    PaperShardRenderer,
)
from envoy.shamir.recover import (
    PresentedShard,
    recover_master_key,
)
from envoy.shamir.ritual import (
    DEFAULT_THRESHOLD,
    DEFAULT_TOTAL_SHARDS,
    ShamirRitualCoordinator,
)
from envoy.shamir.types import (
    ChecklistPersister,
    CommitmentBinder,
    DistributionChecklist,
    MasterKeySource,
    PaperRenderer,
    RitualResult,
    ShamirGenerator,
)

__all__ = [
    # Coordinator
    "ShamirRitualCoordinator",
    "DEFAULT_THRESHOLD",
    "DEFAULT_TOTAL_SHARDS",
    # Protocols
    "MasterKeySource",
    "ShamirGenerator",
    "CommitmentBinder",
    "PaperRenderer",
    "ChecklistPersister",
    # Concrete collaborators (T-02-35)
    "PaperShardCard",
    "PaperShardRenderer",
    "TrustVaultChecklistPersister",
    "compute_commitment",
    "verify_commitment",
    # Result + state
    "RitualResult",
    "DistributionChecklist",
    # Recovery primitive (T-02-36)
    "PresentedShard",
    "recover_master_key",
    # Errors — ritual side
    "ShamirRitualError",
    "RitualPreconditionError",
    "MasterKeyZeroizationError",
    "EnvoyLabelOnCardError",
    "ChecklistPersisterError",
    # Errors — recovery side (T-02-36)
    "ShamirRecoveryError",
    "ShardChecksumFailedError",
    "InsufficientSharesError",
    "TooManySharesError",
    "CommitmentVerificationFailedError",
    "ShardSlotLabelMismatchError",
    "ShardPublicCommitmentMissingError",
]
