"""Tier 1: T-01-18 — EnvoyLedger facade (append + head_commitment + verify_chain).

Source: T-01-18 per `01-wave-1-foundation.md` line 282 + spec authority
`specs/ledger.md` § Entry envelope schema + § Head commitment + shard
`01-analysis/06-envoy-ledger-implementation.md` § 4 step 3.

Closes both orphan-watch grace windows from prior shards:
- T-01-15 `_with_algorithm_id` is invoked transitively via the
  `algorithm_identifier` flow into every `append()` call.
- T-01-17 `EntryEnvelope` + `HashChainBuilder` are invoked at every
  `append()`.

Capacity coverage (5 invariants):
1. Atomicity (sign-then-append; refuse on signing failure)
2. Head commitment monotonic
3. Halt-before-refuse (LedgerHaltedError after rollback detection)
4. Genesis chain shape (parent_hash = sha256(empty) for first entry)
5. Round-trip verify (every appended entry verifies)

Per `rules/testing.md` Tier 1: real `InMemoryAuditStore` + real
`InMemoryKeyManager` (kailash provides both as zero-dep test fixtures).
The Tier 2 wiring (T-01-21) repeats these tests against `SqliteAuditStore`.
"""

from __future__ import annotations

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.ledger import (
    EnvoyLedger,
    LedgerHaltedError,
    LedgerRollbackDetectedError,
    VerificationReport,
)


VALID_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
DEVICE_ID = "device-test-01"
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


# ---------------------------------------------------------------------------
# Construction — fail-loud on misconfig
# ---------------------------------------------------------------------------


class TestConstruction:
    async def test_valid_ledger_constructs(
        self, audit_store: InMemoryAuditStore, keymgr: InMemoryKeyManager
    ) -> None:
        ledger = EnvoyLedger(
            audit_store=audit_store,
            key_manager=keymgr,
            signing_key_id=SIGNING_KEY_ID,
            device_id=DEVICE_ID,
            algorithm_identifier=VALID_ALGO_ID,
        )
        assert ledger.device_id == DEVICE_ID
        assert ledger.is_halted is False

    async def test_missing_key_raises(
        self, audit_store: InMemoryAuditStore, keymgr: InMemoryKeyManager
    ) -> None:
        with pytest.raises(ValueError, match="not registered"):
            EnvoyLedger(
                audit_store=audit_store,
                key_manager=keymgr,
                signing_key_id="never-registered-key",
                device_id=DEVICE_ID,
                algorithm_identifier=VALID_ALGO_ID,
            )

    async def test_one_key_algorithm_id_rejected(
        self, audit_store: InMemoryAuditStore, keymgr: InMemoryKeyManager
    ) -> None:
        """T-01-15 R2-H-01 wire-form contract enforced at construction."""
        with pytest.raises(ValueError, match="3-key"):
            EnvoyLedger(
                audit_store=audit_store,
                key_manager=keymgr,
                signing_key_id=SIGNING_KEY_ID,
                device_id=DEVICE_ID,
                algorithm_identifier={"algorithm": "ed25519+sha256"},  # 1-key form
            )

    async def test_empty_signing_key_id_rejected(
        self, audit_store: InMemoryAuditStore, keymgr: InMemoryKeyManager
    ) -> None:
        with pytest.raises(ValueError, match="signing_key_id"):
            EnvoyLedger(
                audit_store=audit_store,
                key_manager=keymgr,
                signing_key_id="",
                device_id=DEVICE_ID,
                algorithm_identifier=VALID_ALGO_ID,
            )

    async def test_empty_device_id_rejected(
        self, audit_store: InMemoryAuditStore, keymgr: InMemoryKeyManager
    ) -> None:
        with pytest.raises(ValueError, match="device_id"):
            EnvoyLedger(
                audit_store=audit_store,
                key_manager=keymgr,
                signing_key_id=SIGNING_KEY_ID,
                device_id="",
                algorithm_identifier=VALID_ALGO_ID,
            )


# ---------------------------------------------------------------------------
# append() — produces entry_id; chain links via parent_hash
# ---------------------------------------------------------------------------


class TestAppend:
    async def test_append_returns_sha256_prefixed_entry_id(self, ledger: EnvoyLedger) -> None:
        entry_id = await ledger.append(
            entry_type="RoleEnvelopeCreated", content={"envelope_version": 1}
        )
        assert entry_id.startswith("sha256:")
        assert len(entry_id) == len("sha256:") + 64

    async def test_append_increments_sequence(self, ledger: EnvoyLedger) -> None:
        e1 = await ledger.append(entry_type="t1", content={"v": 1})
        e2 = await ledger.append(entry_type="t2", content={"v": 2})
        head = await ledger.head_commitment()
        assert head is not None
        assert head.head_sequence == 2
        assert head.head_entry_id == e2
        assert e1 != e2

    async def test_append_chains_via_parent_hash(self, ledger: EnvoyLedger) -> None:
        """The Nth entry's parent_hash MUST equal the (N-1)th entry's
        entry_id; the 1st entry's parent_hash is the canonical empty-input
        sha256 (the Genesis sentinel for envoy's chain)."""
        e1 = await ledger.append(entry_type="t1", content={"v": 1})
        e2 = await ledger.append(entry_type="t2", content={"v": 2})
        # Walk the audit_store and inspect the envelope chain.
        from kailash.trust.audit_store import AuditFilter

        events = await ledger._audit_store.query(AuditFilter(limit=100))
        envelopes = [e.metadata["_envoy_envelope_v1"] for e in events]
        envelopes.sort(key=lambda x: x["sequence"])
        assert envelopes[0]["entry_id"] == e1
        assert envelopes[1]["entry_id"] == e2
        assert envelopes[1]["parent_hash"] == e1
        # Genesis chain link
        import hashlib

        assert envelopes[0]["parent_hash"] == "sha256:" + hashlib.sha256(b"").hexdigest()

    async def test_empty_entry_type_rejected(self, ledger: EnvoyLedger) -> None:
        with pytest.raises(ValueError, match="entry_type"):
            await ledger.append(entry_type="", content={})

    async def test_non_dict_content_rejected(self, ledger: EnvoyLedger) -> None:
        with pytest.raises(ValueError, match="content"):
            await ledger.append(entry_type="t", content="not-a-dict")  # type: ignore[arg-type]

    async def test_append_persists_full_envelope_in_metadata(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """The full envoy envelope persists under
        `metadata["_envoy_envelope_v1"]` so a future verifier can
        reconstruct the canonical bytes byte-identically."""
        await ledger.append(entry_type="t1", content={"v": 1})
        from kailash.trust.audit_store import AuditFilter

        events = await audit_store.query(AuditFilter(limit=10))
        assert len(events) == 1
        envelope_dict = events[0].metadata["_envoy_envelope_v1"]
        # 14 envelope fields per spec § Entry envelope schema
        expected_keys = {
            "entry_id",
            "parent_hash",
            "sequence",
            "lamport_clock",
            "timestamp",
            "type",
            "intent_id",
            "content",
            "content_trust_level",
            "description_content_hash",
            "description_content_hash_algorithm",
            "signed_by",
            "signature_hex",
            "algorithm_identifier",
            "schema_version",
        }
        assert set(envelope_dict.keys()) == expected_keys


# ---------------------------------------------------------------------------
# head_commitment() — monotonic guard + signed
# ---------------------------------------------------------------------------


class TestHeadCommitment:
    async def test_initial_head_is_none(self, ledger: EnvoyLedger) -> None:
        head = await ledger.head_commitment()
        assert head is None

    async def test_head_updates_after_each_append(self, ledger: EnvoyLedger) -> None:
        e1 = await ledger.append(entry_type="t1", content={"v": 1})
        head_after_1 = await ledger.head_commitment()
        assert head_after_1 is not None
        assert head_after_1.head_sequence == 1
        assert head_after_1.head_entry_id == e1

        e2 = await ledger.append(entry_type="t2", content={"v": 2})
        head_after_2 = await ledger.head_commitment()
        assert head_after_2 is not None
        assert head_after_2.head_sequence == 2
        assert head_after_2.head_entry_id == e2

    async def test_head_carries_canonical_timestamp(self, ledger: EnvoyLedger) -> None:
        await ledger.append(entry_type="t1", content={"v": 1})
        head = await ledger.head_commitment()
        # 27-char microsecond-padded ISO 8601 UTC per #731
        from envoy.ledger.canonical import is_canonical_timestamp

        assert is_canonical_timestamp(head.signed_at)

    async def test_head_carries_signature(self, ledger: EnvoyLedger) -> None:
        await ledger.append(entry_type="t1", content={"v": 1})
        head = await ledger.head_commitment()
        assert head.signature_hex
        assert isinstance(head.signature_hex, str)


# ---------------------------------------------------------------------------
# verify_chain() — round-trip integrity
# ---------------------------------------------------------------------------


class TestVerifyChain:
    async def test_verify_empty_chain_succeeds(self, ledger: EnvoyLedger) -> None:
        report = await ledger.verify_chain()
        assert report.success is True
        assert report.entries_verified == 0
        assert report.failed_entry_index is None

    async def test_verify_appended_chain_succeeds(self, ledger: EnvoyLedger) -> None:
        await ledger.append(entry_type="t1", content={"v": 1})
        await ledger.append(entry_type="t2", content={"v": 2})
        await ledger.append(entry_type="t3", content={"v": 3})
        report = await ledger.verify_chain()
        assert report.success is True
        assert report.entries_verified == 3
        assert report.failed_entry_index is None

    async def test_verify_returns_verification_report_dataclass(self, ledger: EnvoyLedger) -> None:
        report = await ledger.verify_chain()
        assert isinstance(report, VerificationReport)

    async def test_verify_detects_tampered_content(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """Inject a tamper inside metadata and confirm verify_chain catches
        it via signature mismatch."""
        await ledger.append(entry_type="t1", content={"original": "value"})
        # Mutate the in-memory event's envelope content.
        from kailash.trust.audit_store import AuditFilter

        events = await audit_store.query(AuditFilter(limit=10))
        events[0].metadata["_envoy_envelope_v1"]["content"] = {"tampered": "yes"}
        report = await ledger.verify_chain()
        assert report.success is False
        # Either entry_id mismatch or signature failure — both surface the tamper.
        assert report.failed_entry_index == 0
        assert report.failure_reason is not None

    async def test_verify_detects_tampered_algorithm_identifier(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """M-2 (security review): tamper on algorithm_identifier field MUST
        be caught — the field is part of the canonical bytes hashed into
        entry_id, so any mutation breaks the recomputed_id check."""
        from kailash.trust.audit_store import AuditFilter

        await ledger.append(entry_type="t1", content={"v": 1})
        events = await audit_store.query(AuditFilter(limit=10))
        # Replace the 3-key form with a different (still valid-looking) 3-key form.
        events[0].metadata["_envoy_envelope_v1"]["algorithm_identifier"] = {
            "sig": "ed448",
            "hash": "sha512",
            "shamir": "slip39",
        }
        report = await ledger.verify_chain()
        assert report.success is False
        assert report.failed_entry_index == 0

    async def test_verify_detects_tampered_lamport_clock(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """M-2 (security review): tamper on lamport_clock fields MUST be
        caught — lamport_time / device_id / local_seq are all in the
        canonical bytes."""
        from kailash.trust.audit_store import AuditFilter

        await ledger.append(entry_type="t1", content={"v": 1})
        events = await audit_store.query(AuditFilter(limit=10))
        events[0].metadata["_envoy_envelope_v1"]["lamport_clock"]["lamport_time"] = 999
        report = await ledger.verify_chain()
        assert report.success is False
        assert report.failed_entry_index == 0

    async def test_verify_detects_tampered_signature_hex(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """M-2 (security review): tamper on signature_hex MUST be caught
        via verify(payload, signature, public_key) returning False —
        signature_hex is NOT in canonical bytes (excluded from hash input)
        but IS verified against the public key on the entry's canonical
        bytes."""
        from kailash.trust.audit_store import AuditFilter

        await ledger.append(entry_type="t1", content={"v": 1})
        events = await audit_store.query(AuditFilter(limit=10))
        # Flip one byte of the base64-encoded signature.
        original = events[0].metadata["_envoy_envelope_v1"]["signature_hex"]
        flipped = ("Z" if original[5] != "Z" else "Y") + original[1:]
        events[0].metadata["_envoy_envelope_v1"]["signature_hex"] = flipped[0] + flipped[1:]
        # Actually flip a meaningful byte: replace the 3rd char.
        char = original[3]
        new_char = "B" if char != "B" else "C"
        events[0].metadata["_envoy_envelope_v1"]["signature_hex"] = (
            original[:3] + new_char + original[4:]
        )
        report = await ledger.verify_chain()
        assert report.success is False
        assert report.failed_entry_index == 0
        # Should be signature failure since entry_id derivation excludes signature_hex.
        assert "signature" in (report.failure_reason or "").lower()


# ---------------------------------------------------------------------------
# LedgerHaltedError — halt-before-refuse contract
# ---------------------------------------------------------------------------


class TestHaltedState:
    async def test_halted_ledger_refuses_append(self, ledger: EnvoyLedger) -> None:
        # Manually halt the ledger to simulate a post-rollback state.
        ledger._halted = True
        with pytest.raises(LedgerHaltedError, match="halted"):
            await ledger.append(entry_type="t1", content={"v": 1})

    async def test_failing_audit_store_append_rolls_back_chain_state(
        self, audit_store: InMemoryAuditStore, keymgr: InMemoryKeyManager
    ) -> None:
        """H-1 (security): audit_store.append() failure MUST NOT leave the
        ledger with advanced counters or stale last_entry_id. The next
        successful append MUST resume from the same baseline as before
        the failed call. Atomicity invariant per shard 6 § 4 step 3."""

        class FailingStore:
            """Wraps a real audit store; raises on append the first N times."""

            def __init__(self, real, fail_count: int):
                self._real = real
                self._fail_count = fail_count
                self._calls = 0
                self.last_hash = real.last_hash

            def create_event(self, **kwargs):
                return self._real.create_event(**kwargs)

            async def append(self, event):
                self._calls += 1
                if self._calls <= self._fail_count:
                    raise RuntimeError(f"injected disk-full failure #{self._calls}")
                await self._real.append(event)
                self.last_hash = self._real.last_hash

            async def query(self, f):
                return await self._real.query(f)

            async def verify_chain(self):
                return await self._real.verify_chain()

            async def close(self):
                await self._real.close()

        failing = FailingStore(audit_store, fail_count=1)
        ledger = EnvoyLedger(
            audit_store=failing,
            key_manager=keymgr,
            signing_key_id=SIGNING_KEY_ID,
            device_id=DEVICE_ID,
            algorithm_identifier=VALID_ALGO_ID,
        )
        # Snapshot baseline state pre-call.
        before_seq = ledger._sequence
        before_lamport = ledger._lamport_time
        before_local = ledger._local_seq
        before_last = ledger._last_entry_id
        before_head = ledger._head

        with pytest.raises(RuntimeError, match="injected"):
            await ledger.append(entry_type="t1", content={"v": 1})

        # Counters MUST be unchanged after the failed append.
        assert ledger._sequence == before_seq
        assert ledger._lamport_time == before_lamport
        assert ledger._local_seq == before_local
        assert ledger._last_entry_id == before_last
        assert ledger._head is before_head  # head_commitment also unchanged
        assert ledger.is_halted is False

        # Next append MUST succeed using the same baseline (sequence still 1
        # — nothing leaked from the failed call).
        eid = await ledger.append(entry_type="t1", content={"v": 1})
        head = await ledger.head_commitment()
        assert head is not None
        assert head.head_sequence == 1  # NOT 2 — failed call didn't advance.
        assert head.head_entry_id == eid

    async def test_rollback_detection_halts_on_decreasing_sequence(
        self, ledger: EnvoyLedger
    ) -> None:
        """The HeadCommitment monotonic guard MUST detect a sequence-
        decrease (defensive against future bugs that would mutate the
        chain state) and halt the ledger via LedgerRollbackDetectedError."""
        await ledger.append(entry_type="t1", content={"v": 1})
        # Inject an artificial backward sequence directly through the
        # internal _mint_head_commitment to exercise the guard.
        with pytest.raises(LedgerRollbackDetectedError, match="monotonic guard"):
            ledger._mint_head_commitment(entry_id="sha256:" + "f" * 64, sequence=0)
        assert ledger.is_halted is True
        with pytest.raises(LedgerHaltedError):
            await ledger.append(entry_type="t2", content={"v": 2})


# ---------------------------------------------------------------------------
# Orphan-watch closure — T-01-15 + T-01-17 producers now have a consumer
# ---------------------------------------------------------------------------


class TestOrphanWatchClosure:
    """Per `rules/orphan-detection.md` Rule 1, EntryEnvelope + HashChainBuilder
    + TrustStoreAdapter._with_algorithm_id need a production hot-path
    consumer within the 5-commit grace window. EnvoyLedger.append() IS that
    consumer. These tests verify the production wiring exists."""

    async def test_append_produces_3_key_algorithm_identifier_in_envelope(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """T-01-15 _with_algorithm_id contract: every persisted record
        carries the spec-mandated 3-key {sig, hash, shamir} form."""
        await ledger.append(entry_type="t1", content={"v": 1})
        from kailash.trust.audit_store import AuditFilter

        events = await audit_store.query(AuditFilter(limit=10))
        envelope = events[0].metadata["_envoy_envelope_v1"]
        assert envelope["algorithm_identifier"] == VALID_ALGO_ID
        assert set(envelope["algorithm_identifier"].keys()) == {
            "sig",
            "hash",
            "shamir",
        }

    async def test_append_invokes_hashchainbuilder_pure_path(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """T-01-17 HashChainBuilder.build_unsigned + seal contract:
        entry_id MUST be reproducible by canonical_dumps(envelope_minus_sig
        _and_id) hashed to sha256."""
        import hashlib

        from envoy.ledger.canonical import canonical_dumps

        eid = await ledger.append(entry_type="t1", content={"v": 1})
        from kailash.trust.audit_store import AuditFilter

        events = await audit_store.query(AuditFilter(limit=10))
        envelope = events[0].metadata["_envoy_envelope_v1"]
        # Reconstruct the unsigned canonical bytes
        unsigned = {k: v for k, v in envelope.items() if k not in ("entry_id", "signature_hex")}
        recomputed = "sha256:" + hashlib.sha256(canonical_dumps(unsigned)).hexdigest()
        assert recomputed == eid
