"""Tier 2: T-02-37 — Genesis-Record commitment defeats counterfeit shards.

Per `specs/shamir-recovery.md` § Shard public commitments + § Error
taxonomy `CommitmentVerificationFailedError` ("Refuse unlock; investigate
counterfeit-shard or social-engineering attack").

Real SLIP-0039 ritual (no mocks) generates two parallel ritual sets
("authentic" + "counterfeit") from different master keys. The commitments
bound to the AUTHENTIC Genesis Record MUST reject any counterfeit shard
swapped into the recovery quorum, even though the counterfeit shard's
SLIP-0039 per-card checksum is structurally valid.

This is THE security test for `specs/shamir-recovery.md` line 41
(Phase 01 Wave 2 acceptance gate).
"""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path

import pytest
from kailash.trust.vault.shamir import ShamirRitual, generate

from envoy.shamir import (
    DEFAULT_THRESHOLD,
    PresentedShard,
    ShamirRitualCoordinator,
    TrustVaultChecklistPersister,
    compute_commitment,
    recover_master_key,
)
from envoy.shamir.errors import CommitmentVerificationFailedError
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.vault import TrustVault


class _InMemoryBinder:
    """Storage-only binder per `envoy/shamir/types.py:114`."""

    def __init__(self) -> None:
        self.binding: dict[str, list[str]] = {}

    async def bind_to_genesis(self, principal_id: str, commitments: list[str]) -> None:
        self.binding[principal_id] = list(commitments)


class _VaultBackedSource:
    def __init__(self, vault: TrustVault) -> None:
        self._vault = vault

    def export_master_key_for_shamir(self) -> Awaitable[bytes]:
        return self._vault.export_master_key_for_shamir()


# ---------------------------------------------------------------------------
# Counterfeit-defense Tier 2 — real SLIP-0039 across two parallel rituals.
# ---------------------------------------------------------------------------


class TestGenesisCommitmentDefeatsCounterfeit:
    """Counterfeit shards (constructed from a different secret) MUST fail
    commitment verification even when their SLIP-0039 checksum is valid.

    Per `specs/shamir-recovery.md` line 41:
        Genesis Record carries `shard_public_commitments: [algo:hash]`
        array for recovery verification without shard exposure.
    """

    async def test_counterfeit_shard_swap_is_rejected(self, unlocked_vault: TrustVault) -> None:
        # Authentic ritual against the real vault's master key.
        binder = _InMemoryBinder()
        persister = TrustVaultChecklistPersister(
            trust_vault=unlocked_vault, principal_id="auth-principal"
        )
        coordinator = ShamirRitualCoordinator(
            master_key_source=_VaultBackedSource(unlocked_vault),
            commitment_binder=binder,
            paper_renderer=PaperShardRenderer(),
            checklist_persister=persister,
            principal_id="auth-principal",
        )
        authentic = await coordinator.run_first_time_ritual()
        authentic_commitments = tuple(binder.binding["auth-principal"])
        slot_labels = tuple(card.slot_label for card in authentic.paper_cards)

        # Counterfeit ritual — same 3-of-5 shape, DIFFERENT secret.
        # Uses the real SLIP-0039 generator so the counterfeit shards
        # have structurally valid BIP-39 checksums. Only the COMMITMENT
        # check should reject them.
        counterfeit_secret = bytes(range(32, 64))
        counterfeit_shards = generate(counterfeit_secret, ShamirRitual(threshold=3, total_shards=5))

        # Recovery attempt with 2 authentic + 1 counterfeit. The
        # counterfeit's per-card checksum passes (real SLIP-0039); the
        # commitment verification at Step 5 MUST raise.
        presented = [
            PresentedShard(
                slot_label=slot_labels[0],
                words=list(counterfeit_shards[0]),
                card_index=0,
            ),
            PresentedShard(
                slot_label=slot_labels[1],
                words=list(authentic.shards[1]),
                card_index=1,
            ),
            PresentedShard(
                slot_label=slot_labels[2],
                words=list(authentic.shards[2]),
                card_index=2,
            ),
        ]
        with pytest.raises(CommitmentVerificationFailedError) as exc_info:
            recover_master_key(
                presented,
                commitments=authentic_commitments,
                checklist_labels=slot_labels,
            )
        # Security review F-3 — drop the counterfeit shapes from local
        # scope so a same-process heap dump cannot recover the test's
        # attack-shaped secret. Defensive: counterfeit_secret is a
        # constructed test value, not the production master key.
        del counterfeit_secret
        del counterfeit_shards
        del presented
        # First-failure-wins per envoy/shamir/recover.py contract.
        assert exc_info.value.failing_card_index == 0
        # Plain-language user_message names "fingerprint" + "security incident".
        assert "fingerprint" in exc_info.value.user_message
        assert "security incident" in exc_info.value.user_message

    async def test_authentic_shards_match_published_commitments(
        self, unlocked_vault: TrustVault
    ) -> None:
        """Recovery-side recomputation MUST match backup-side publication.

        compute_commitment is deterministic over the canonical
        paper-print form (per envoy/shamir/commitments.py); each shard
        the coordinator emitted MUST produce a commitment that lies in
        the bound commitments list.
        """
        binder = _InMemoryBinder()
        persister = TrustVaultChecklistPersister(
            trust_vault=unlocked_vault, principal_id="auth-principal"
        )
        coordinator = ShamirRitualCoordinator(
            master_key_source=_VaultBackedSource(unlocked_vault),
            commitment_binder=binder,
            paper_renderer=PaperShardRenderer(),
            checklist_persister=persister,
            principal_id="auth-principal",
        )
        result = await coordinator.run_first_time_ritual()
        bound_commitments = set(binder.binding["auth-principal"])

        for shard in result.shards:
            assert compute_commitment(list(shard)) in bound_commitments, (
                "shard commitment recomputed at recovery time MUST appear in "
                "the commitments bound at backup time — the binding contract"
            )

    async def test_commitment_array_size_matches_total_shards(
        self, unlocked_vault: TrustVault
    ) -> None:
        """Every shard contributes exactly one commitment to Genesis."""
        binder = _InMemoryBinder()
        persister = TrustVaultChecklistPersister(
            trust_vault=unlocked_vault, principal_id="auth-principal"
        )
        coordinator = ShamirRitualCoordinator(
            master_key_source=_VaultBackedSource(unlocked_vault),
            commitment_binder=binder,
            paper_renderer=PaperShardRenderer(),
            checklist_persister=persister,
            principal_id="auth-principal",
        )
        result = await coordinator.run_first_time_ritual()
        assert len(binder.binding["auth-principal"]) == result.total_shards
        # And every commitment is distinct (no collision under real SHA-256).
        assert len(set(binder.binding["auth-principal"])) == result.total_shards
