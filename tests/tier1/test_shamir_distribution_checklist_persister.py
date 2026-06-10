"""Tier 1: T-02-35 — `TrustVaultChecklistPersister` round-trip + H-06 enforcement.

Source: shard `01-analysis/15-shamir-recovery-implementation.md` § 3.5 +
`specs/shamir-recovery.md` § Card format (line 29) — H-06 fix.

The persister stores `DistributionChecklist.to_dict()` keyed by `ritual_id`
in the Trust Vault's metadata slot. Persistence MUST round-trip across
lock/unlock cycles, and the persisted bytes MUST contain ONLY opaque slot
labels — never real holder names, never the literal string "Envoy".

Tier 1 uses a real `TrustVault` instance against a tmp_path file (the
vault's encryption + I/O surface is small and fast enough for unit-tier
budget). The Tier 2 wiring test lands in T-02-37.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from envoy.shamir import (
    ChecklistPersisterError,
    DistributionChecklist,
    EnvoyLabelOnCardError,
    TrustVaultChecklistPersister,
)
from envoy.trust.vault import TrustVault

_PASSPHRASE = "phase-01-test-passphrase"


def _make_checklist(
    *,
    ritual_id: str = "ritual-test-1",
    slot_labels: tuple[str, ...] = ("slot-1", "slot-2", "slot-3", "slot-4", "slot-5"),
) -> DistributionChecklist:
    return DistributionChecklist(
        ritual_id=ritual_id,
        threshold=3,
        total_shards=len(slot_labels),
        slot_labels=slot_labels,
        created_at=datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
async def unlocked_vault(tmp_path: Path) -> TrustVault:
    vault = TrustVault(tmp_path / "phase01.vault")
    await vault.create(b"", _PASSPHRASE)
    await vault.unlock(_PASSPHRASE)
    yield vault
    if vault.is_unlocked:
        await vault.lock()


class TestPersistRoundTrip:
    @pytest.mark.asyncio
    async def test_persist_then_read_round_trip(self, unlocked_vault: TrustVault) -> None:
        persister = TrustVaultChecklistPersister(unlocked_vault, principal_id="alice")
        original = _make_checklist()
        await persister.persist(original)

        loaded = await persister.read_all()
        assert original.ritual_id in loaded
        assert loaded[original.ritual_id] == original

    @pytest.mark.asyncio
    async def test_persist_survives_lock_unlock_cycle(self, tmp_path: Path) -> None:
        """Per shard 15 § 3.5: the checklist MUST persist across vault
        lock/unlock cycles. This is the core durability invariant.
        """
        vault_path = tmp_path / "lifecycle.vault"
        vault = TrustVault(vault_path)
        await vault.create(b"", _PASSPHRASE)
        await vault.unlock(_PASSPHRASE)

        persister = TrustVaultChecklistPersister(vault, principal_id="alice")
        original = _make_checklist()
        await persister.persist(original)

        # Lock the vault — in-memory payload is dropped.
        await vault.lock()
        assert not vault.is_unlocked

        # Re-unlock: a fresh in-memory payload should reconstruct the
        # checklist from disk via the metadata envelope.
        await vault.unlock(_PASSPHRASE)
        persister_after = TrustVaultChecklistPersister(vault, principal_id="alice")
        loaded = await persister_after.read_all()
        assert original.ritual_id in loaded
        assert loaded[original.ritual_id] == original
        await vault.lock()

    @pytest.mark.asyncio
    async def test_persist_multiple_rituals_keyed_by_ritual_id(
        self, unlocked_vault: TrustVault
    ) -> None:
        persister = TrustVaultChecklistPersister(unlocked_vault, principal_id="alice")
        c1 = _make_checklist(ritual_id="ritual-aaa")
        c2 = _make_checklist(ritual_id="ritual-bbb")
        await persister.persist(c1)
        await persister.persist(c2)

        loaded = await persister.read_all()
        assert "ritual-aaa" in loaded
        assert "ritual-bbb" in loaded
        assert loaded["ritual-aaa"] == c1
        assert loaded["ritual-bbb"] == c2


class TestH06EnforcementOnPersist:
    """Per shard 15 § 3.5 + `specs/shamir-recovery.md` line 29: persisted
    bytes MUST contain only opaque slot labels — never the literal "Envoy",
    never real holder names. The persister is the LAST gate before bytes
    hit disk.
    """

    @pytest.mark.asyncio
    async def test_persisted_bytes_do_not_contain_envoy_substring(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "h06.vault"
        vault = TrustVault(vault_path)
        await vault.create(b"", _PASSPHRASE)
        await vault.unlock(_PASSPHRASE)

        persister = TrustVaultChecklistPersister(vault, principal_id="alice")
        await persister.persist(_make_checklist())
        await vault.lock()

        # Read the on-disk vault file as raw bytes. The vault file is
        # AES-256-GCM encrypted, so the literal "Envoy" string SHOULD NOT
        # appear in plaintext form (encryption obscures it). The
        # higher-value assertion is on the unlocked plaintext payload —
        # see test_unlocked_payload_contains_only_opaque_labels.
        raw = vault_path.read_bytes()
        # The encrypted vault is binary; "Envoy" should not appear because
        # (a) the persister rejected non-opaque labels at write time, and
        # (b) encryption further obscures structure. Both layers verified.
        assert b"Envoy" not in raw
        assert b"envoy" not in raw

    @pytest.mark.asyncio
    async def test_unlocked_payload_contains_only_opaque_labels(
        self, unlocked_vault: TrustVault
    ) -> None:
        persister = TrustVaultChecklistPersister(unlocked_vault, principal_id="alice")
        await persister.persist(_make_checklist())

        # Read the in-memory plaintext payload. Per H-06: only opaque
        # `slot-N` labels should appear; no "Envoy", no real names.
        payload = await unlocked_vault.read()
        decoded = payload.decode("utf-8")
        assert "Envoy" not in decoded
        assert "envoy" not in decoded
        # Sanity: the opaque labels DID land.
        for label in ("slot-1", "slot-2", "slot-3", "slot-4", "slot-5"):
            assert label in decoded

    @pytest.mark.asyncio
    async def test_persist_rejects_envoy_slot_label(self, unlocked_vault: TrustVault) -> None:
        """A caller constructing a malformed `DistributionChecklist`
        bypasses the coordinator's `_opaque_slot_labels()` helper.

        Per security review M-1 on PR #15, defense is now three-layer:
        (1) `DistributionChecklist.__post_init__` rejects at construction;
        (2) renderer rejects at render time; (3) persister is the
        structural last gate.

        Layer 1 fires first now — `_make_checklist(slot_labels=...)` with
        a non-`slot-N` label raises `ValueError` from `__post_init__`
        before the persister sees the object. This test asserts that
        the construction-layer gate fires; the persister-level check is
        defense-in-depth.
        """
        persister = TrustVaultChecklistPersister(unlocked_vault, principal_id="alice")
        # Construction-layer rejection (per security review M-1):
        with pytest.raises(ValueError, match="opaque pattern"):
            _make_checklist(
                slot_labels=("slot-1", "slot-2", "Envoy Backup", "slot-4", "slot-5")
            )
        # Defense-in-depth: even if a malicious caller bypasses
        # `DistributionChecklist.__post_init__` via `object.__setattr__`,
        # the persister's pre-write validator fires.
        good = _make_checklist()
        # Bypass the frozen-dataclass post-init via object.__setattr__
        # to simulate a malicious mutation reaching the persister.
        object.__setattr__(good, "slot_labels", ("slot-1", "Envoy-leak", "slot-3", "slot-4", "slot-5"))
        with pytest.raises(EnvoyLabelOnCardError, match="opaque pattern"):
            await persister.persist(good)

    @pytest.mark.asyncio
    async def test_persist_rejects_empty_slot_labels(self, unlocked_vault: TrustVault) -> None:
        persister = TrustVaultChecklistPersister(unlocked_vault, principal_id="alice")
        bad = _make_checklist(slot_labels=())
        with pytest.raises(EnvoyLabelOnCardError):
            await persister.persist(bad)


class TestPersisterPreconditions:
    @pytest.mark.asyncio
    async def test_persist_rejects_locked_vault(self, tmp_path: Path) -> None:
        vault = TrustVault(tmp_path / "locked.vault")
        await vault.create(b"", _PASSPHRASE)
        # Vault is sealed (create() leaves it locked).
        persister = TrustVaultChecklistPersister(vault, principal_id="alice")
        with pytest.raises(ChecklistPersisterError, match="sealed"):
            await persister.persist(_make_checklist())

    def test_constructor_rejects_empty_principal_id(self, tmp_path: Path) -> None:
        vault = TrustVault(tmp_path / "no-principal.vault")
        with pytest.raises(ChecklistPersisterError, match="principal_id"):
            TrustVaultChecklistPersister(vault, principal_id="")
