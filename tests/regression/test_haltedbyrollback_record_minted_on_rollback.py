"""Regression: per `specs/ledger.md` § Halted state, the runtime appends
a HaltedByRollback entry BEFORE halting further Ledger writes.

This regression test pins the contract that `EnvoyLedger.append()` MUST
persist a `HaltedByRollback` entry into the audit_store BEFORE re-raising
`LedgerRollbackDetectedError`. Prior to redteam Round 1, the code halted
on rollback detection without minting the spec-mandated forensic record
— `HaltedByRollbackRecord` was an orphan (declared + re-exported, never
constructed at any production site). See `04-validate/round-1-implement-redteam.md`
finding HIGH-4.

The Phase 01 single-device flow cannot organically produce a rollback
condition (every append's `tentative_sequence` is `self._sequence + 1`,
strictly greater than `self._head.head_sequence`). To exercise the
forensic-record contract, this test forces the rollback by mutating
`ledger._head` to a synthetic future-head with a higher sequence — the
Phase 02+ cross-device-sync condition that legitimately produces this
scenario in production.

Per `rules/testing.md` § Regression Testing: this test is permanent and
MUST NOT be deleted.
"""

from __future__ import annotations

import pytest
from kailash.trust.audit_store import AuditFilter, InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.ledger import (
    EnvoyLedger,
    LedgerHaltedError,
    LedgerRollbackDetectedError,
)
from envoy.ledger.facade import _ENVELOPE_METADATA_KEY
from envoy.ledger.head import HeadCommitment

VALID_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
DEVICE_ID = "device-redteam-r1"
SIGNING_KEY_ID = "envoy-signing-key"


@pytest.fixture
async def keymgr() -> InMemoryKeyManager:
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(SIGNING_KEY_ID)
    return mgr


@pytest.fixture
def audit_store() -> InMemoryAuditStore:
    return InMemoryAuditStore()


@pytest.fixture
async def ledger(audit_store: InMemoryAuditStore, keymgr: InMemoryKeyManager) -> EnvoyLedger:
    return EnvoyLedger(
        audit_store=audit_store,
        key_manager=keymgr,
        signing_key_id=SIGNING_KEY_ID,
        device_id=DEVICE_ID,
        algorithm_identifier=VALID_ALGO_ID,
    )


@pytest.mark.regression
class TestHaltedByRollbackForensicRecordMinted:
    """Per `specs/ledger.md` § Halted state — the spec promise is:
    rollback detection appends HaltedByRollback BEFORE halting writes."""

    async def test_haltedbyrollback_entry_persisted_before_halt_via_append(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """Synthetic future-head triggers the rollback gate via the public
        `append()` path; the HaltedByRollback entry MUST land in the
        audit_store before LedgerRollbackDetectedError propagates."""
        # Step 1 — establish a real chain tail at sequence=1.
        first_entry_id = await ledger.append(entry_type="ritual_completion", content={"phase": 1})
        head_after_first = await ledger.head_commitment()
        assert head_after_first is not None
        assert head_after_first.head_sequence == 1
        assert head_after_first.head_entry_id == first_entry_id

        # Step 2 — install a synthetic FUTURE head (head_sequence=10) to
        # simulate a Phase 02 cross-device-sync state where the local head
        # was advanced by a remote sync. Phase 01 can't produce this
        # organically; the mutation is the test seam that exercises the
        # production contract for the rollback path.
        future_head = HeadCommitment(
            head_sequence=10,
            head_entry_id="sha256:" + "f" * 64,
            signed_at=head_after_first.signed_at,
            signature_hex=head_after_first.signature_hex,
        )
        ledger._head = future_head

        # Step 3 — next append's tentative_sequence will be 2 (= self._sequence
        # + 1 = 1 + 1). 2 < 10 → rollback detected. The error MUST propagate
        # AND the halt record MUST land before the error reaches the caller.
        with pytest.raises(LedgerRollbackDetectedError, match="monotonic guard"):
            await ledger.append(entry_type="ritual_completion", content={"phase": 2})

        # Step 4 — verify the HaltedByRollback entry is in the audit_store.
        events = await audit_store.query(AuditFilter(limit=100))
        halt_events = [e for e in events if e.action == "HaltedByRollback"]
        assert (
            len(halt_events) == 1
        ), f"expected exactly 1 HaltedByRollback entry, got {len(halt_events)}"

        halt_event = halt_events[0]
        halt_envelope = halt_event.metadata[_ENVELOPE_METADATA_KEY]
        assert halt_envelope["type"] == "HaltedByRollback"
        halt_content = halt_envelope["content"]
        assert halt_content["last_known_good_head"]["sequence"] == 10
        assert halt_content["last_known_good_head"]["entry_id"] == future_head.head_entry_id
        assert halt_content["detected_head"]["sequence"] == 2
        assert halt_content["detection_reason"] == "sequence_decrease"
        # `detected_at` is canonical-format ISO 8601; just confirm it's there.
        assert "detected_at" in halt_content
        assert halt_content["detected_at"].endswith("Z")

        # Step 5 — verify ledger is halted; subsequent appends raise
        # LedgerHaltedError (NOT LedgerRollbackDetectedError — the halt-gate
        # at append() entry blocks before re-reaching the rollback check).
        assert ledger.is_halted is True
        with pytest.raises(LedgerHaltedError, match="halted"):
            await ledger.append(entry_type="ritual_completion", content={"phase": 3})

    async def test_halt_record_chain_tail_advances_for_verify_chain(
        self, ledger: EnvoyLedger
    ) -> None:
        """After the halt record persists, `_last_entry_id` MUST point to
        the halt entry so a subsequent `verify_chain()` walks the halt
        record's parent_hash linkage correctly. This is the structural
        defense against the audit-trail-with-orphaned-tail failure mode."""
        first_entry_id = await ledger.append(entry_type="ritual_completion", content={"phase": 1})

        head_after_first = await ledger.head_commitment()
        assert head_after_first is not None
        future_head = HeadCommitment(
            head_sequence=10,
            head_entry_id="sha256:" + "f" * 64,
            signed_at=head_after_first.signed_at,
            signature_hex=head_after_first.signature_hex,
        )
        ledger._head = future_head

        with pytest.raises(LedgerRollbackDetectedError):
            await ledger.append(entry_type="ritual_completion", content={"phase": 2})

        # The halt record's entry_id MUST be the new chain tail, NOT the
        # last successful regular entry. _sequence advanced from 1 → 2
        # (the halt record's own sequence).
        assert ledger._last_entry_id != first_entry_id
        assert ledger._last_entry_id.startswith("sha256:")
        assert ledger._sequence == 2  # halt record occupies the rejected slot

    async def test_halt_record_includes_canonical_detection_reason(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """The Phase 01 rollback path detects sequence_decrease specifically;
        future Phase 02+ paths can also detect head_signature_mismatch and
        algorithm_identifier_downgrade. The halt record's detection_reason
        MUST be one of the canonical three values per
        `HaltedByRollbackRecord._VALID_REASONS`."""
        await ledger.append(entry_type="ritual_completion", content={"phase": 1})
        head = await ledger.head_commitment()
        assert head is not None
        ledger._head = HeadCommitment(
            head_sequence=10,
            head_entry_id="sha256:" + "f" * 64,
            signed_at=head.signed_at,
            signature_hex=head.signature_hex,
        )

        with pytest.raises(LedgerRollbackDetectedError):
            await ledger.append(entry_type="ritual_completion", content={"phase": 2})

        events = await audit_store.query(AuditFilter(limit=100))
        halt_events = [e for e in events if e.action == "HaltedByRollback"]
        assert len(halt_events) == 1
        halt_content = halt_events[0].metadata[_ENVELOPE_METADATA_KEY]["content"]
        assert halt_content["detection_reason"] in {
            "sequence_decrease",
            "head_signature_mismatch",
            "algorithm_identifier_downgrade",
        }
        # Phase 01 produces only sequence_decrease.
        assert halt_content["detection_reason"] == "sequence_decrease"
