"""Tier 2: T-02-37 — Full Shamir vault-recovery end-to-end.

Per `specs/shamir-recovery.md` § Recovery flow + `specs/trust-vault.md`
§ Recovery. Real Argon2id + real AES-256-GCM container + real SLIP-0039
+ real per-card BIP-39 checksum + real commitment verification. NO
mocking per `rules/testing.md` Tier 2.

The end-to-end flow this test exercises:
1. ORIGINAL device — create vault under a passphrase; write a payload.
2. Backup ritual — export master key; ShamirRitualCoordinator splits;
   shards persisted as paper cards + commitments bound to Genesis.
3. ORIGINAL device discarded (vault file is the only persistent state).
4. RECOVERY device — fresh TrustVault instance against the same vault
   file; presents 3-of-5 shards to recover_master_key; commitments
   verify against the persisted Genesis-side binding.
5. import_master_key_from_shamir installs the reconstructed key.
6. Vault unlocks WITHOUT the original passphrase + reads the payload.

This is the load-bearing acceptance test for the Phase 01 MVP exit
criterion per `briefs/00-phase-01-mvp-scope.md` § Exit criteria:
"Trust Vault backup via SLIP-0039 Shamir works (3-of-5 reconstruct
test)".

Per `rules/orphan-detection.md` Rule 2a (Crypto-Pair Round-Trip Through
Facade): exercises the encrypt/decrypt + ritual/recover pairs through
the same facade callers will use in production (TrustVault +
ShamirRitualCoordinator + recover_master_key).
"""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path

import pytest

from envoy.shamir import (
    PresentedShard,
    ShamirRitualCoordinator,
    TrustVaultChecklistPersister,
    recover_master_key,
)
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.vault import TrustVault


class _InMemoryGenesisBinder:
    """Storage-only binder per `envoy/shamir/types.py:114` contract.

    Stands in for the trust-side T-01-12 Genesis Record write hook (out
    of T-02-37 scope; the load-bearing crypto contract is that the
    backup-side commitments equal the recovery-side commitments, which
    is what the in-memory binder exposes to the test).
    """

    def __init__(self) -> None:
        self.binding: dict[str, list[str]] = {}

    async def bind_to_genesis(self, principal_id: str, commitments: list[str]) -> None:
        self.binding[principal_id] = list(commitments)


class _VaultMasterKeySource:
    def __init__(self, vault: TrustVault) -> None:
        self._vault = vault

    def export_master_key_for_shamir(self) -> Awaitable[bytes]:
        return self._vault.export_master_key_for_shamir()


class TestVaultShamirRecoveryEndToEnd:
    """Full backup → reconstruct → fresh-vault import → unlock chain."""

    async def test_payload_recovered_via_shamir_without_passphrase(self, vault_path: Path) -> None:
        """The load-bearing 3-of-5 reconstruct + vault-unlock test.

        Pass: a fresh TrustVault with no knowledge of the original
        passphrase can recover the payload using only 3 of the 5 cards
        + the published commitments.
        """
        # --- ORIGINAL device ---
        # Phase 01 vault contract per envoy/trust/vault.py:467: payload
        # IS the metadata envelope. User-side state lives INSIDE the
        # envelope alongside the Shamir distribution checklist; the
        # persister's read-modify-write preserves user-side keys.
        original = TrustVault(vault_path, idle_ttl_seconds=60)
        await original.create(b'{"_etmd_v1": {}}', "original-passphrase-12345")
        await original.unlock("original-passphrase-12345")
        await original.write_metadata({"user_payload": "phase-01-mvp-test-payload"})

        # --- Backup ritual ---
        binder = _InMemoryGenesisBinder()
        persister = TrustVaultChecklistPersister(trust_vault=original, principal_id="e2e-principal")
        coordinator = ShamirRitualCoordinator(
            master_key_source=_VaultMasterKeySource(original),
            commitment_binder=binder,
            paper_renderer=PaperShardRenderer(),
            checklist_persister=persister,
            principal_id="e2e-principal",
        )
        ritual = await coordinator.run_first_time_ritual()
        published_commitments = tuple(binder.binding["e2e-principal"])
        published_slot_labels = tuple(card.slot_label for card in ritual.paper_cards)
        await original.lock()
        del original  # original device is gone — vault file is the only state

        # --- RECOVERY device ---
        # Holder presents 3 of 5 cards (any 3, any order per spec
        # § Recovery flow). Whitespace tolerance lives at the CLI layer;
        # the primitive expects clean lists.
        presented_indices = [1, 3, 4]  # any 3 of the 5
        presented = [
            PresentedShard(
                slot_label=published_slot_labels[i],
                words=list(ritual.shards[i]),
                card_index=card_idx,
            )
            for card_idx, i in enumerate(presented_indices)
        ]
        reconstructed = recover_master_key(
            presented,
            commitments=published_commitments,
            checklist_labels=published_slot_labels,
        )

        # --- Fresh device — install reconstructed key, unlock, read ---
        recovery_vault = TrustVault(vault_path, idle_ttl_seconds=60)
        await recovery_vault.import_master_key_from_shamir(reconstructed)
        assert (
            recovery_vault.is_unlocked
        ), "fresh vault MUST be unlocked after Shamir-reconstructed key import"

        metadata = await recovery_vault.read_metadata()
        assert metadata.get("user_payload") == "phase-01-mvp-test-payload", (
            "Phase 01 exit criterion: 3-of-5 reconstruct round-trips the "
            "user-side metadata envelope"
        )
        # The persisted Shamir checklist MUST also round-trip — proves
        # the entire vault state survived the Shamir-only recovery path.
        assert "shamir_distribution_checklists" in metadata
        assert ritual.ritual_id in metadata["shamir_distribution_checklists"]

        await recovery_vault.lock()

        # Caller-side memory hygiene per `rules/trust-plane-security.md`
        # MUST NOT Rule 3 — drop the reconstructed bytes ASAP. bytes is
        # immutable so `del` is the strongest portable defense.
        del reconstructed

    async def test_wrong_passphrase_rejects_even_with_correct_shards(
        self, vault_path: Path
    ) -> None:
        """Defense-in-depth: SLIP-0039 passphrase MUST match.

        A backup created with a non-empty Shamir passphrase produces
        shards whose reconstruction with the WRONG passphrase yields
        bytes that fail AES-GCM tag verification on vault unlock.
        """
        original = TrustVault(vault_path, idle_ttl_seconds=60)
        await original.create(b'{"_etmd_v1": {}}', "vault-passphrase-12345")
        await original.unlock("vault-passphrase-12345")

        binder = _InMemoryGenesisBinder()
        persister = TrustVaultChecklistPersister(
            trust_vault=original, principal_id="passphrase-principal"
        )
        coordinator = ShamirRitualCoordinator(
            master_key_source=_VaultMasterKeySource(original),
            commitment_binder=binder,
            paper_renderer=PaperShardRenderer(),
            checklist_persister=persister,
            principal_id="passphrase-principal",
        )
        ritual = await coordinator.run_first_time_ritual(passphrase=b"shamir-passphrase-AAAA")
        commitments = tuple(binder.binding["passphrase-principal"])
        slot_labels = tuple(card.slot_label for card in ritual.paper_cards)
        await original.lock()

        # Reconstruct with the WRONG Shamir passphrase. The library
        # accepts any passphrase + produces SOME bytes (it's just XORed
        # into the EMS decryption); the bytes will not be the true
        # master key. Vault unlock then fails AES-GCM tag check.
        presented = [
            PresentedShard(
                slot_label=slot_labels[i],
                words=list(ritual.shards[i]),
                card_index=card_idx,
            )
            for card_idx, i in enumerate([0, 1, 2])
        ]
        wrong_key = recover_master_key(
            presented,
            commitments=commitments,
            checklist_labels=slot_labels,
            passphrase=b"WRONG-PASSPHRASE",
        )

        recovery_vault = TrustVault(vault_path, idle_ttl_seconds=60)
        # AES-GCM tag verification under wrong key MUST fail; vault
        # stays sealed per the import_master_key_from_shamir contract.
        with pytest.raises(Exception):  # noqa: BLE001 — vault error class is implementation detail
            await recovery_vault.import_master_key_from_shamir(wrong_key)
        del wrong_key
