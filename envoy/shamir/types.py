"""envoy.shamir Protocols + result dataclasses.

Per shard 15 (`workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md`)
§ 3.1 — `ShamirRitualCoordinator` orchestrates a 6-step ritual whose
collaborators land across two shards:

- **T-02-34 (this shard):** ships the coordinator + Protocol slots for
  every collaborator + the result dataclasses passed between them.
- **T-02-35 (next shard):** implements `CommitmentBinder` (Genesis Record
  binding), `PaperRenderer` (24-word card format), and
  `ChecklistPersister` (opaque-slot-label DistributionChecklist).
- **T-02-37:** Tier 2 wires the real `kailash.trust.vault.shamir`
  generator + real Trust Vault.

Protocol-based injection here serves two purposes:

1. **Testable ritual orchestration** — Tier 1 tests assert step ordering,
   share count = 5, threshold = 3, and zeroize discipline against fake
   collaborators (no `kailash[shamir]` extra needed for the orchestration
   tests; the round-trip lives in T-02-37 Tier 2).
2. **Phase-out path for Phase 02 hardening** — Phase 02 swaps the bytes
   `MasterKeySource` for a Secure-Enclave-bound `Sensitive[bytes]`
   context manager (cf. `envoy/trust/vault.py:572` TODO(T-15)). The
   Protocol surface stays unchanged.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocols — collaborator slots for the 6-step ritual
# ---------------------------------------------------------------------------


@runtime_checkable
class MasterKeySource(Protocol):
    """Step 1 — yields the 32-byte master key for Shamir splitting.

    Implementations MUST return a 32-byte `bytes` object (immutable; AES-256
    key length per `specs/trust-vault.md` § Encryption). The coordinator
    treats the returned value as a sensitive secret and zeroizes it as
    step 6 of the ritual.

    Production implementation: `envoy.trust.TrustStoreAdapter`'s
    `export_master_key_for_shamir()` method
    (`envoy/trust/vault.py:549`). The TrustStoreAdapter satisfies this
    Protocol by virtue of having a method of the same name; the
    coordinator's `__init__` accepts any object that exposes the method.

    Returns: an `Awaitable[bytes]` (kailash-py's TrustStoreAdapter
    surface is async per `journal/0009-DISCOVERY-trust-store-async-deviation.md`
    Option-A).
    """

    def export_master_key_for_shamir(self) -> Awaitable[bytes]: ...


@runtime_checkable
class ShamirGenerator(Protocol):
    """Step 2 — splits the master key into m-of-n shards.

    Production implementation: `kailash.trust.vault.shamir.generate`
    (verified at T-02-34 implementation time via `inspect.signature`,
    streak `journal/0012-METHODOLOGY-inspect-signature-sweep-5-of-5-streak.md`).

    Signature MUST match the kailash wrapper exactly:
    `(secret: bytes, ritual: ShamirRitualSpec, *, passphrase: bytes = b'')
     -> List[List[str]]`

    The coordinator's `__init__` uses the kailash wrapper as the default
    when no generator is injected; tests inject fakes that record arguments
    and return canned shard sets.
    """

    def __call__(
        self,
        secret: bytes,
        ritual: Any,  # kailash.trust.vault.shamir.ShamirRitual
        *,
        passphrase: bytes = b"",
    ) -> list[list[str]]: ...


@runtime_checkable
class CommitmentBinder(Protocol):
    """Step 3 — binds shard public commitments to the user's Genesis Record.

    Production implementation lands in T-02-35 (`envoy/shamir/commitments.py`).
    Per `specs/shamir-recovery.md` § Shard public commitments + line 41 +
    `specs/trust-lineage.md` § Schema GenesisRecord line 27, the binder
    computes `[f"sha256:{sha256(serialize_shard(s)).hexdigest()}"
    for s in shards]` and writes them to `Genesis.shard_public_commitments`.

    For T-02-34 testability: Tier 1 fakes record the shards passed and
    return a placeholder commitment list. Real binding lives in T-02-37.
    """

    def bind_to_genesis(
        self, principal_id: str, shards: list[list[str]]
    ) -> Awaitable[list[str]]: ...


@runtime_checkable
class PaperRenderer(Protocol):
    """Step 4 — renders each shard for human transcription.

    Production implementation lands in T-02-35 (`envoy/shamir/paper.py`).
    Per `specs/shamir-recovery.md` § Card format line 29, NO 'Envoy'
    label, NO real names; opaque slot labels only (H-06 fix).

    For T-02-34 testability: Tier 1 fakes record `(shard, slot_label,
    sequence)` tuples and return placeholder card objects. The concrete
    `PaperShardCard` shape lands in T-02-35.
    """

    def render(self, shard: list[str], slot_label: str, sequence: tuple[int, int]) -> Any: ...


@runtime_checkable
class ChecklistPersister(Protocol):
    """Step 5 — persists the DistributionChecklist to Trust Vault.

    Production implementation lands in T-02-35
    (`envoy/shamir/distribution_checklist.py`). Per
    `specs/shamir-recovery.md` § Card format line 29 (H-06 fix),
    persisted state contains ONLY opaque slot labels — never real holder
    names or the 'Envoy' string.

    For T-02-34 testability: Tier 1 fakes record the
    `DistributionChecklist` passed for assertion of slot-label opacity.
    """

    def persist(self, checklist: DistributionChecklist) -> Awaitable[None]: ...


# ---------------------------------------------------------------------------
# Result + state dataclasses — frozen per rules/eatp.md + trust-plane-security.md
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DistributionChecklist:
    """Persistent opaque-slot-label checklist for the ritual.

    Per `specs/shamir-recovery.md` § Card format line 29 (H-06 fix):
    "Distribution checklist persists only opaque slot labels in Trust
    Vault; real names optional + in hidden envelope (Phase 04) only".

    Phase 04 hidden envelope MAY add real holder names if the user opts
    in; Phase 01 has the field shape but does NOT populate it.
    """

    ritual_id: str
    threshold: int
    total_shards: int
    slot_labels: tuple[str, ...]
    created_at: datetime
    rotation_history: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serializable form per `rules/eatp.md` SDK conventions."""
        return {
            "ritual_id": self.ritual_id,
            "threshold": self.threshold,
            "total_shards": self.total_shards,
            "slot_labels": list(self.slot_labels),
            "created_at": self.created_at.isoformat(),
            "rotation_history": list(self.rotation_history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DistributionChecklist:
        return cls(
            ritual_id=data["ritual_id"],
            threshold=int(data["threshold"]),
            total_shards=int(data["total_shards"]),
            slot_labels=tuple(data["slot_labels"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            rotation_history=tuple(data.get("rotation_history", ())),
        )


@dataclass(frozen=True, slots=True)
class RitualResult:
    """Output of `ShamirRitualCoordinator.run_first_time_ritual()`.

    Carries the artifacts produced by all 6 steps of the ritual. Consumers:

    - Boundary Conversation S8 (per `specs/boundary-conversation.md`) reads
      `paper_cards` to display to the user for transcription.
    - Tier 2 round-trip tests (T-02-37) reconstruct from `shards` and
      verify the SAME secret bytes return.
    - The coordinator NEVER returns the master-key bytes — those are
      zeroized as step 6 before this result is constructed.

    `paper_cards` and `commitments` are typed as opaque `tuple[Any, ...]`
    in T-02-34 since the concrete shapes (`PaperShardCard`, commitment
    string format) land in T-02-35. The coordinator does not inspect
    these values; it only orchestrates collaborator output flow.
    """

    ritual_id: str
    shards: tuple[tuple[str, ...], ...]
    threshold: int
    total_shards: int
    created_at: datetime
    commitments: tuple[Any, ...] = field(default_factory=tuple)
    paper_cards: tuple[Any, ...] = field(default_factory=tuple)
    checklist: DistributionChecklist | None = None


__all__ = [
    "MasterKeySource",
    "ShamirGenerator",
    "CommitmentBinder",
    "PaperRenderer",
    "ChecklistPersister",
    "DistributionChecklist",
    "RitualResult",
]
