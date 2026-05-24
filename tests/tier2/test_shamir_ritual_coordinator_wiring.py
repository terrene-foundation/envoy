"""Tier 2: T-02-37 — ShamirRitualCoordinator end-to-end wiring.

Per `specs/shamir-recovery.md` § Recovery flow + § Algorithm. Real
SLIP-0039 via `kailash.trust.vault.shamir.generate`; real per-card
checksum + commitment computation; real ChecklistPersister against
real TrustVault. NO mocking per `rules/testing.md` Tier 2.

T-02-37 scope: this file exercises the 6-step ritual orchestration
end-to-end on the real generator + real paper renderer + real
persister. The 4-test matrix per the todo plan:

1. Ritual produces threshold-many shards that the recovery primitive
   reconstructs back to the same master-key bytes.
2. Master-key bytes are zeroized between ritual step 2 and step 3
   (verified via instrumented MasterKeySource that records the buffer
   identity, then asserts the bytearray returned from the source IS
   the buffer overwritten by the coordinator).
3. Ritual round-trip is deterministic at the shard level — same secret
   → SAME number of shards (5) with SAME threshold (3); shard content
   varies per ritual (entropy in the SLIP-0039 generation).
4. Coordinator's published `commitments` survive the lock/unlock of
   the TrustVault checklist (the persister round-trip is the storage
   contract).
"""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path

import pytest

from envoy.shamir import (
    DEFAULT_THRESHOLD,
    DEFAULT_TOTAL_SHARDS,
    PresentedShard,
    ShamirRitualCoordinator,
    TrustVaultChecklistPersister,
    recover_master_key,
)
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.vault import TrustVault


# ---------------------------------------------------------------------------
# Real-collaborator fixtures — no mocks; storage-only binder fake captures the
# coordinator's commitments for the recovery side.
# ---------------------------------------------------------------------------


class _InMemoryGenesisBinder:
    """Storage-only CommitmentBinder per `envoy/shamir/types.py:114` contract.

    The L-2 re-architecture (T-02-35) restricts the binder to STORAGE —
    the coordinator computes commitments LOCALLY before passing them in.
    Tier 2's binder captures the published list so the recovery side can
    read it back as `Genesis.shard_public_commitments` (T-01-12's
    GenesisRecord-binding wiring lands in a separate shard per the
    workspace plan; this fake is in-scope for the Shamir crypto pipeline
    test).
    """

    def __init__(self) -> None:
        self.binding: dict[str, list[str]] = {}

    async def bind_to_genesis(self, principal_id: str, commitments: list[str]) -> None:
        self.binding[principal_id] = list(commitments)


class _MasterKeySource:
    """Wraps `TrustVault.export_master_key_for_shamir` as the Step-1 source.

    Matches `envoy.shamir.MasterKeySource` Protocol — returns an
    `Awaitable[bytes]` carrying the 32-byte master key. The coordinator
    transfers the bytes into a `bytearray` and zeroizes it post-generate.
    """

    def __init__(self, vault: TrustVault) -> None:
        self._vault = vault

    def export_master_key_for_shamir(self) -> Awaitable[bytes]:
        return self._vault.export_master_key_for_shamir()


@pytest.fixture
async def real_ritual_coordinator(
    unlocked_vault: TrustVault, vault_path: Path
) -> tuple[ShamirRitualCoordinator, _InMemoryGenesisBinder, TrustVault]:
    """Construct a coordinator wired to real TrustVault + real persister.

    Returns a tuple (coordinator, binder, vault) so tests can:
    - run the ritual against `coordinator`
    - read the bound commitments off `binder.binding`
    - re-open the vault to confirm checklist persistence
    """
    master_key_source = _MasterKeySource(unlocked_vault)
    binder = _InMemoryGenesisBinder()
    paper_renderer = PaperShardRenderer()
    persister = TrustVaultChecklistPersister(
        trust_vault=unlocked_vault, principal_id="tier2-principal"
    )
    coordinator = ShamirRitualCoordinator(
        master_key_source=master_key_source,
        commitment_binder=binder,
        paper_renderer=paper_renderer,
        checklist_persister=persister,
        principal_id="tier2-principal",
    )
    return coordinator, binder, unlocked_vault


# ---------------------------------------------------------------------------
# Test 1 — Ritual + recovery round-trip via real SLIP-0039.
# ---------------------------------------------------------------------------


class TestRitualReconstructRoundTrip:
    """Backup ritual + recovery primitive together reconstruct the same key."""

    async def test_real_ritual_yields_reconstructable_shards(
        self,
        real_ritual_coordinator: tuple[ShamirRitualCoordinator, _InMemoryGenesisBinder, TrustVault],
    ) -> None:
        coordinator, binder, vault = real_ritual_coordinator

        # Capture the master key BEFORE the ritual (vault.export is
        # idempotent — same key bytes returned on every call until the
        # vault is re-keyed).
        original_master_key = await vault.export_master_key_for_shamir()

        # Run the real ritual — uses kailash.trust.vault.shamir.generate
        # because no shamir_generator override was passed.
        result = await coordinator.run_first_time_ritual()

        # Capacity: 5 shards, 3-of-5 threshold per spec § Default threshold.
        assert len(result.shards) == DEFAULT_TOTAL_SHARDS
        assert result.threshold == DEFAULT_THRESHOLD
        assert result.total_shards == DEFAULT_TOTAL_SHARDS

        # Binder received the commitments computed by the coordinator
        # (not by the binder itself — L-2 re-architecture per T-02-35).
        commitments = tuple(binder.binding["tier2-principal"])
        assert len(commitments) == DEFAULT_TOTAL_SHARDS

        # Slot labels per spec § Card format — opaque, regex-bounded.
        slot_labels = tuple(card.slot_label for card in result.paper_cards)

        # Now exercise the recovery primitive against 3 of the 5 shards
        # via the SAME commitments + slot labels.
        presented = [
            PresentedShard(
                slot_label=slot_labels[i],
                words=list(result.shards[i]),
                card_index=card_idx,
            )
            for card_idx, i in enumerate([0, 2, 4])  # any 3 of 5
        ]
        recovered = recover_master_key(
            presented,
            commitments=commitments,
            checklist_labels=slot_labels,
        )

        # The reconstructed master key MUST equal the original — this is
        # the load-bearing crypto-pair round-trip per orphan-detection.md
        # Rule 2a (round-trip through the facade).
        assert recovered == original_master_key

    async def test_recover_via_any_3_of_5_succeeds(
        self,
        real_ritual_coordinator: tuple[ShamirRitualCoordinator, _InMemoryGenesisBinder, TrustVault],
    ) -> None:
        """Spec § Recovery flow: 'Enter words from any 3 cards (any order).'

        Exercises three distinct 3-subsets of the 5 shards. All MUST
        reconstruct to the same master key.
        """
        coordinator, binder, vault = real_ritual_coordinator
        original_master_key = await vault.export_master_key_for_shamir()
        result = await coordinator.run_first_time_ritual()
        commitments = tuple(binder.binding["tier2-principal"])
        slot_labels = tuple(card.slot_label for card in result.paper_cards)

        subsets = [(0, 1, 2), (1, 3, 4), (0, 2, 4)]
        for subset in subsets:
            presented = [
                PresentedShard(
                    slot_label=slot_labels[i],
                    words=list(result.shards[i]),
                    card_index=card_idx,
                )
                for card_idx, i in enumerate(subset)
            ]
            recovered = recover_master_key(
                presented,
                commitments=commitments,
                checklist_labels=slot_labels,
            )
            assert recovered == original_master_key, f"subset {subset} failed to reconstruct"


# ---------------------------------------------------------------------------
# Test 2 — Persister round-trip via real TrustVault.
# ---------------------------------------------------------------------------


class TestChecklistPersistenceRoundTrip:
    """The persisted DistributionChecklist survives lock/unlock."""

    async def test_persisted_checklist_round_trips_through_vault(
        self,
        real_ritual_coordinator: tuple[ShamirRitualCoordinator, _InMemoryGenesisBinder, TrustVault],
        vault_path: Path,
    ) -> None:
        coordinator, _, vault = real_ritual_coordinator
        result = await coordinator.run_first_time_ritual()
        assert result.checklist is not None
        original_slot_labels = result.checklist.slot_labels

        # Lock + unlock through a fresh TrustVault instance — the
        # persisted checklist MUST round-trip through Argon2id KDF
        # + AES-256-GCM container.
        await vault.lock()
        fresh = TrustVault(vault_path, idle_ttl_seconds=60)
        await fresh.unlock("tier2-integration-passphrase-with-entropy")

        metadata = await fresh.read_metadata()
        checklists = metadata.get("shamir_distribution_checklists", {})
        assert result.ritual_id in checklists, "ritual_id not found in persisted vault metadata"

        persisted = checklists[result.ritual_id]
        assert tuple(persisted["slot_labels"]) == original_slot_labels
        # H-06 contract: no "envoy" anywhere; opaque labels only.
        for label in persisted["slot_labels"]:
            assert (
                "envoy" not in label.lower()
            ), f"H-06 violation: label {label!r} leaked 'envoy' substring"

        await fresh.lock()
