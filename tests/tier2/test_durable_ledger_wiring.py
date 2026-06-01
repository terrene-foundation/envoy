# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: durable `EnvoyLedger` persistence + cross-process chain rehydration.

Source: T-01-21 (file-backed audit store) + the EC-4 / EC-9 durable-export
slice. Per `rules/facade-manager-detection.md` Rule 1, the manager-shape
`open_durable_ledger` / `DurableLedger` builder has a Tier-2 wiring test that
asserts an externally-observable effect — here, that entries written by one
`EnvoyLedger` instance survive to a *fresh* instance opened over the SAME
on-disk SQLite file, and that the fresh instance *continues* the existing
chain (rehydration) rather than forking it from genesis.

Per `rules/testing.md` Tier 2: real infrastructure — real `SqliteAuditStore`
over a real `AsyncSQLitePool` (file-backed aiosqlite), real Ed25519 signing,
real canonical-JSON byte-pinning. NO mocking.

Key-durability scope boundary: these tests reuse ONE `InMemoryKeyManager`
across both instances to stand in for the durable signing key that lands at
T-01-13 / the durable-key shard. That isolates THIS shard's concern (durable
store + counter rehydration) from the key-durability concern: with a stable
key, `verify_chain()` over the rehydrated chain passes. In production a fresh
process gets a fresh in-memory key until the durable-key shard lands, at which
point head rehydration + export-signature verification become cross-process.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.ledger import ExportBundle, canonical_dumps, compute_receipt_hash
from envoy.ledger.bootstrap import DurableLedger, audit_db_path, open_durable_ledger


SIGNING_KEY_ID = "envoy-durable-signing-key"
DEVICE_ID = "device-durable-test"
VALID_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}


@pytest.fixture
async def shared_keymgr() -> AsyncGenerator[InMemoryKeyManager, None]:
    """One key manager reused across instances — stands in for the durable
    signing key (T-01-13). See the module docstring for the scope boundary."""
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(SIGNING_KEY_ID)
    yield mgr
    keys = getattr(mgr, "_keys", None)
    if isinstance(keys, dict):
        keys.clear()


async def _open(vault_path: Path, keymgr: InMemoryKeyManager) -> DurableLedger:
    return await open_durable_ledger(
        vault_path=vault_path,
        key_manager=keymgr,
        signing_key_id=SIGNING_KEY_ID,
        device_id=DEVICE_ID,
        algorithm_identifier=VALID_ALGO_ID,
    )


class TestDurableLedgerPersistence:
    """`open_durable_ledger` / `DurableLedger` — the Tier-2 wiring test."""

    async def test_audit_db_path_is_vault_sibling(self, tmp_path: Path) -> None:
        """The durable ledger file is a `<stem>.audit.db` vault sibling — the
        same layout the chain / posture / bc / digest sub-stores use, so the
        writer and the `envoy ledger export` reader resolve the same file."""
        vp = tmp_path / "trust_vault.dat"
        assert audit_db_path(vp) == tmp_path / "trust_vault.audit.db"

    async def test_entries_persist_and_chain_rehydrates_across_instances(
        self, tmp_path: Path, shared_keymgr: InMemoryKeyManager
    ) -> None:
        """Append in one instance; a fresh instance over the SAME file sees the
        entries AND continues the chain at the right sequence (no fork)."""
        vault_path = tmp_path / "trust_vault.dat"

        # Instance 1 — append 3 entries, then close (releasing the pool).
        dl1 = await _open(vault_path, shared_keymgr)
        await dl1.ledger.append(entry_type="action", content={"i": 0})
        await dl1.ledger.append(entry_type="action", content={"i": 1})
        await dl1.ledger.append(entry_type="action", content={"i": 2})
        assert dl1.ledger.current_sequence == 3
        await dl1.aclose()

        # External effect: the SQLite file exists on disk after the pool closed.
        assert audit_db_path(vault_path).exists()

        # Instance 2 — a FRESH ledger over the SAME file. Rehydration restores
        # the chain tail BEFORE any append.
        dl2 = await _open(vault_path, shared_keymgr)
        assert dl2.ledger.current_sequence == 3  # rehydrated — no fork

        # Appends continue the existing chain (sequence 4, 5) instead of
        # re-issuing sequence 1 with a genesis parent.
        await dl2.ledger.append(entry_type="action", content={"i": 3})
        e5 = await dl2.ledger.append(entry_type="action", content={"i": 4})

        # verify_chain walks all 5 persisted entries: parent_hash linkage +
        # per-entry Ed25519 signature. Passing proves (a) the entries
        # persisted across the process boundary, and (b) the chain did NOT
        # fork — a fork would surface as a parent_hash mismatch / duplicate
        # sequence at index 3.
        report = await dl2.ledger.verify_chain()
        assert report.success is True
        assert report.entries_verified == 5

        head = await dl2.ledger.head_commitment()
        assert head is not None
        assert head.head_sequence == 5
        assert head.head_entry_id == e5

        await dl2.aclose()

    async def test_export_succeeds_and_verifies_after_rehydrate(
        self, tmp_path: Path, shared_keymgr: InMemoryKeyManager
    ) -> None:
        """A FRESH process can `export()` a populated durable ledger — the EC-4
        cross-process proof. `rehydrate()` re-mints the signed head (without it,
        `export()` refuses because `self._head` is None even over a populated
        store), and the bundle's head + entry signatures verify under the same
        (durable, here shared) key."""
        vault_path = tmp_path / "trust_vault.dat"

        # Writer process: append 3 entries, then close.
        dl1 = await _open(vault_path, shared_keymgr)
        for i in range(3):
            await dl1.ledger.append(entry_type="action", content={"i": i})
        await dl1.aclose()

        # Reader process: a FRESH ledger that did NOT append anything — only
        # rehydrate() ran. Before B2 this raised LedgerError (head was None).
        dl2 = await _open(vault_path, shared_keymgr)
        bundle = await dl2.ledger.export()
        assert isinstance(bundle, ExportBundle)
        assert len(bundle.entries) == 3

        # Head matches the persisted tail (verifier invariant 6).
        head = bundle.head_commitment
        assert head.head_sequence == 3
        assert head.head_entry_id == bundle.entries[-1]["entry_id"]

        # The re-minted head signature verifies under the durable key — the
        # EC-4 invariant 7 the head rehydration exists to satisfy.
        pub = shared_keymgr.get_public_key(SIGNING_KEY_ID)
        assert pub is not None
        head_payload = canonical_dumps(
            {
                "head_sequence": head.head_sequence,
                "head_entry_id": head.head_entry_id,
                "signed_at": head.signed_at,
            }
        )
        assert await shared_keymgr.verify(head_payload, head.signature_hex, pub) is True

        # Bundle self-integrity (invariant 8) + every entry signature
        # (verify_chain) hold over the cross-process bundle.
        assert compute_receipt_hash(bundle.to_dict_minus_receipt()) == bundle.receipt_hash
        report = await dl2.ledger.verify_chain()
        assert report.success is True
        assert report.entries_verified == 3

        await dl2.aclose()

    async def test_verify_fails_when_rehydrate_key_differs_from_entry_key(
        self, tmp_path: Path, shared_keymgr: InMemoryKeyManager
    ) -> None:
        """The security boundary this shard establishes: a fresh process whose
        signing key DIFFERS from the key that signed the persisted entries
        (the pre-B3 ephemeral-key state) MUST fail verification LOUD — never
        silently 'verify' a head it re-minted under the wrong key. This is the
        fail-loud property the durable keychain key (B1+B3) later closes by
        making the two keys identical across processes."""
        vault_path = tmp_path / "trust_vault.dat"

        # Writer: 3 entries signed by key A.
        dl1 = await _open(vault_path, shared_keymgr)
        for i in range(3):
            await dl1.ledger.append(entry_type="action", content={"i": i})
        await dl1.aclose()

        # Reader: a FRESH, DIFFERENT keypair (same key_id, different key bytes).
        keymgr_b = InMemoryKeyManager()
        await keymgr_b.generate_keypair(SIGNING_KEY_ID)
        dl2 = await _open(vault_path, keymgr_b)

        # rehydrate re-minted the head under key B, but the entries carry key A
        # signatures → verify_chain checks them against key B's pubkey and MUST
        # report failure (no spoof, no silent pass).
        report = await dl2.ledger.verify_chain()
        assert report.success is False

        await dl2.aclose()
        keys = getattr(keymgr_b, "_keys", None)
        if isinstance(keys, dict):
            keys.clear()

    async def test_rehydrate_is_noop_on_empty_store(
        self, tmp_path: Path, shared_keymgr: InMemoryKeyManager
    ) -> None:
        """A first-ever open finds no tail; counters stay at genesis and the
        first append issues sequence 1."""
        dl = await _open(tmp_path / "empty_vault.dat", shared_keymgr)
        assert dl.ledger.current_sequence == 0
        await dl.ledger.append(entry_type="action", content={"i": 0})
        assert dl.ledger.current_sequence == 1
        await dl.aclose()
