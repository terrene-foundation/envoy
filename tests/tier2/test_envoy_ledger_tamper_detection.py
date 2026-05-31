# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: F16 — ledger tamper-detection for insert / delete / reorder (EC-4).

Source authority — `01-analysis/02-mvp-objectives.md` EC-4 line 66 verbatim:

> The verifier MUST detect any tampering attempt (single-bit flip in any
> payload field; insertion / deletion / reorder of any entry).

Gap this closes (journal/0044 F16): the bit-flip vector is exercised against
the real verifier in `tests/tier1/test_envoy_ledger_facade.py`, but
**insert / delete / reorder — named verbatim in the acceptance gate — had ZERO
coverage**. This file exercises all three against a real `EnvoyLedger` +
`InMemoryAuditStore` (real kailash code path, real Ed25519 + SHA-256 canonical
hashing), asserting `verify_chain().success is False`.

How each vector is detected (`envoy/ledger/facade.py` verify_chain):
- verify_chain sorts entries by the envelope `sequence` field, then walks
  checking (1) parent_hash == prev entry_id (chain linkage), (2) recomputed
  entry_id == stored entry_id (content integrity, `sequence` is IN the
  canonical bytes), (3) Ed25519 signature.
- **delete** a middle entry → the successor's parent_hash points to the
  deleted entry's id while prev_entry_id is the entry-before-deleted → parent_hash
  mismatch.
- **insert** a duplicate entry → the second copy's parent_hash points to the
  real predecessor while prev_entry_id is now the first copy's id → parent_hash
  mismatch.
- **reorder** is only achievable against the verified walk by tampering the
  `sequence` field (a physical list reshuffle is canonicalized away by the
  sort); `sequence` is in the canonical bytes, so the recomputed entry_id no
  longer matches → entry_id mismatch (and/or parent_hash break at the new
  order).

Per `rules/testing.md` Tier 2: NO mocking. Real EnvoyLedger over real
InMemoryAuditStore (the `envoy_ledger` + `audit_store` fixtures from
`tests/tier2/conftest.py`).
"""

from __future__ import annotations

from kailash.trust.audit_store import InMemoryAuditStore

from envoy.ledger import EnvoyLedger

# The metadata key under which EnvoyLedger stores the signed envelope on each
# AuditEvent (the canonical content verify_chain walks).
_ENVELOPE_KEY = "_envoy_envelope_v1"


async def _append_three(ledger: EnvoyLedger) -> None:
    await ledger.append(entry_type="t1", content={"v": 1})
    await ledger.append(entry_type="t2", content={"v": 2})
    await ledger.append(entry_type="t3", content={"v": 3})


class TestLedgerTamperDetection:
    async def test_clean_chain_verifies(self, envoy_ledger: EnvoyLedger) -> None:
        """Baseline: an untampered 3-entry chain verifies (so the tamper
        assertions below prove DETECTION, not a always-False verifier)."""
        await _append_three(envoy_ledger)
        report = await envoy_ledger.verify_chain()
        assert report.success is True
        assert report.entries_verified == 3
        assert report.failed_entry_index is None

    async def test_detects_deletion_of_middle_entry(
        self, envoy_ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """EC-4 'deletion of any entry': removing the middle entry breaks the
        parent_hash linkage of its successor."""
        await _append_three(envoy_ledger)
        assert (await envoy_ledger.verify_chain()).success is True

        # Delete the middle stored entry (index 1) from the audit store.
        del audit_store._events[1]

        report = await envoy_ledger.verify_chain()
        assert report.success is False, "deletion of a middle entry was NOT detected"
        assert report.failed_entry_index is not None
        assert report.failure_reason is not None

    async def test_detects_insertion_of_duplicate_entry(
        self, envoy_ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """EC-4 'insertion of any entry': inserting an extra (duplicate) entry
        mid-chain breaks parent_hash linkage — the second copy's parent_hash no
        longer matches the running prev entry_id."""
        await _append_three(envoy_ledger)
        assert (await envoy_ledger.verify_chain()).success is True

        # Insert a duplicate of the last entry into the middle of the store.
        duplicate = audit_store._events[2]
        audit_store._events.insert(1, duplicate)

        report = await envoy_ledger.verify_chain()
        assert report.success is False, "insertion of a duplicate entry was NOT detected"
        assert report.failed_entry_index is not None
        assert report.failure_reason is not None

    async def test_detects_reorder_via_sequence_tamper(
        self, envoy_ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """EC-4 'reorder of any entry': verify_chain canonicalizes physical
        order by sorting on `sequence`, so the only way to reorder the verified
        walk is to tamper the `sequence` field — which is in the canonical
        bytes, so the recomputed entry_id no longer matches the stored id."""
        await _append_three(envoy_ledger)
        assert (await envoy_ledger.verify_chain()).success is True

        # Swap the sequence numbers of entries 1 and 2 (an attempt to reorder
        # history). Both envelopes' canonical bytes now diverge from their
        # stored entry_id.
        env1 = audit_store._events[1].metadata[_ENVELOPE_KEY]
        env2 = audit_store._events[2].metadata[_ENVELOPE_KEY]
        env1["sequence"], env2["sequence"] = env2["sequence"], env1["sequence"]

        report = await envoy_ledger.verify_chain()
        assert report.success is False, "reorder via sequence tamper was NOT detected"
        assert report.failed_entry_index is not None
        assert report.failure_reason is not None
