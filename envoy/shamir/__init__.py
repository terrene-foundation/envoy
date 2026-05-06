"""envoy.shamir — Trust Vault Shamir 3-of-5 backup ritual.

Phase 01 implementation of `specs/shamir-recovery.md` per shard 15
(`workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md`).

T-02-34 ships the orchestration coordinator + Protocol slots for every
collaborator. T-02-35 (paper / commitments / distribution_checklist) and
T-02-36 (reconstruct CLI) extend this surface; T-02-37 wires the Tier 2
round-trip.

Per `rules/orphan-detection.md` Rule 6, this facade re-exports the public
surface so callers import from one stable place.
"""

from envoy.shamir.errors import (
    MasterKeyZeroizationError,
    RitualPreconditionError,
    ShamirRitualError,
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
    # Result + state
    "RitualResult",
    "DistributionChecklist",
    # Errors
    "ShamirRitualError",
    "RitualPreconditionError",
    "MasterKeyZeroizationError",
]
