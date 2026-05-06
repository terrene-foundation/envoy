"""envoy.ledger — hash-chained append-only audit record.

Per `specs/ledger.md` § Purpose: every grant, action, refusal, posture change,
ritual event lands here as a signed entry whose `entry_id` is the SHA-256 of
the canonical-JSON-encoded envelope. Phase 01 ships the foundation (this
package); Phase 01 facade (T-01-18 EnvoyLedger) wraps the foundation in
sign-then-append semantics over `kailash.trust.audit.AuditStore`.

Public surface (T-01-17):

- `EntryEnvelope` — frozen dataclass; the on-wire shape every entry shares.
- `LamportClock` — frozen dataclass; (lamport_time, device_id, local_seq).
- `HeadCommitment` — frozen dataclass; signed (head_sequence, head_entry_id).
- `HaltedByRollbackRecord` — frozen dataclass; mint at rollback detection.
- `canonical_dumps(obj)` — deterministic JSON byte-vector matching
  kailash-py #757/#756/#731 byte pinning. The cross-SDK byte-identity
  contract per `specs/ledger.md` BET-6.
- `CanonicalJsonEncoder` — streaming/incremental variant of canonical_dumps.
- `HashChainBuilder` — pure function (envelope_dict, prev_entry_id, signing_key)
  → (entry_id, parent_hash, signature_hex). T-01-18 facade calls this inside a
  `df.transaction()` to wire append + audit_store.append + head.update.
- 8 typed errors per spec § Error taxonomy.

Phase 02+ extends:

- Per-region HKDF-derived per-entry keys (specs/ledger.md § Per-entry encryption)
- Two-phase signing (PhaseARecord + PhaseBRecord) wired through the runtime
- CRDT merge protocol (specs/ledger-merge.md)
- Foreign-key tombstones + key destruction (T-042 mitigation)
"""

from envoy.ledger.canonical import CanonicalJsonEncoder, canonical_dumps
from envoy.ledger.errors import (
    EntryKeyDestroyedError,
    LedgerAlgorithmMismatchError,
    LedgerConflictFloodError,
    LedgerError,
    LedgerHaltedError,
    LedgerRollbackDetectedError,
    LedgerSyncConflictError,
    LedgerVerificationFailedError,
    PhaseAOrphanDetectedError,
)
from envoy.ledger.hash_chain import EntryEnvelope, HashChainBuilder
from envoy.ledger.head import HaltedByRollbackRecord, HeadCommitment
from envoy.ledger.lamport import LamportClock

__all__ = [
    "CanonicalJsonEncoder",
    "EntryEnvelope",
    "EntryKeyDestroyedError",
    "HaltedByRollbackRecord",
    "HashChainBuilder",
    "HeadCommitment",
    "LamportClock",
    "LedgerAlgorithmMismatchError",
    "LedgerConflictFloodError",
    "LedgerError",
    "LedgerHaltedError",
    "LedgerRollbackDetectedError",
    "LedgerSyncConflictError",
    "LedgerVerificationFailedError",
    "PhaseAOrphanDetectedError",
    "canonical_dumps",
]
