"""Typed errors for envoy.ledger.

Per `specs/ledger.md` § Error taxonomy. Phase 01 ships the 8 load-bearing
errors that the foundation (T-01-17) + facade (T-01-18) emit; Phase 02+
extends with two-phase signing + CRDT merge specific errors as those
features ship.

Per `rules/security.md` § "No secrets in logs" — error messages MUST NOT
echo entry payloads, signing keys, or canonical-JSON byte vectors that
include user content.
"""

from __future__ import annotations


class LedgerError(Exception):
    """Base class for every envoy.ledger error."""

    def __init__(self, message: str, *, entry_id: str | None = None) -> None:
        super().__init__(message)
        self.entry_id = entry_id


class LedgerHaltedError(LedgerError):
    """Raised when an append() / verify() is attempted on a Ledger that has
    been halted by a `HaltedByRollback` record.

    Per `specs/ledger.md` § Halted state: once the runtime appends a
    `HaltedByRollback` record (rollback or signature divergence detected),
    further writes are BLOCKED until forensic recovery. The runtime MUST
    surface this error rather than silently allowing a write that would
    invalidate the divergence audit trail.
    """


class LedgerRollbackDetectedError(LedgerError):
    """Raised when `HeadCommitment.head_sequence` decreases between syncs OR
    the head signature fails verification.

    Per `specs/ledger.md` § Head commitment: rollback detection is the
    primary defense against T-100 (rollback attack). On detection, the
    runtime appends a `HaltedByRollback` record before halting (see
    `LedgerHaltedError`).
    """


class LedgerVerificationFailedError(LedgerError):
    """Raised by `EnvoyLedger.verify_chain()` on the FIRST entry whose
    parent_hash, signature, or algorithm_identifier fails verification.

    The error includes the failing entry's `entry_id` AND the failure
    reason (parent-hash mismatch, signature invalid, algorithm-identifier
    drift across a `MigrationAnnouncement` boundary, etc.). Per
    `specs/ledger.md` § Chain verification — operators run
    `envoy ledger verify` to surface forensic divergence.
    """


class LedgerSyncConflictError(LedgerError):
    """Raised by the CRDT merge protocol when conflicting entries cannot be
    resolved per the Lamport-clock + entry-id-tiebreaker rule.

    Per `specs/ledger-merge.md` § Conflict types — the merge produces a
    `LedgerConflictEntry` for forensic record AND raises this error if
    operator action is required. Phase 01 narrow scope: the foundation
    declares the error type; Wave 2+ wires the merge protocol.
    """


class LedgerConflictFloodError(LedgerError):
    """Raised when CRDT merge conflict rate exceeds the per-spec rate limit.

    Per `specs/ledger-merge.md` § Conflict-flood rate-limit — a malicious
    co-principal cannot evict legitimate entries by flooding the merge
    queue with synthetic conflicts. Phase 01 declares the error type;
    Wave 2+ wires the rate limiter.
    """


class EntryKeyDestroyedError(LedgerError):
    """Raised when a Ledger entry whose per-entry key has been destroyed is
    accessed for read.

    Per `specs/ledger.md` § Per-entry encryption + § Tombstone: T-003
    (retention + GDPR) mitigation requires per-entry keys whose destruction
    renders the entry's content unrecoverable while preserving the chain
    structure (parent_hash, signature). Phase 02 wires this; Phase 01
    declares the error type.
    """


class PhaseAOrphanDetectedError(LedgerError):
    """Raised when a `PhaseARecord` (intent) lacks a corresponding
    `PhaseBRecord` (commit) within the orphan-resolution window.

    Per `specs/ledger.md` § Two-phase signing — the runtime detects orphan
    Phase A records during sync and either resolves them via
    `PhaseAOrphanResolution` OR escalates to user via Grant Moment
    (specs/grant-moment.md § Orphan UI). Phase 01 declares the error type;
    Wave 3 (Grant Moment) wires the resolution path.
    """


class LedgerAlgorithmMismatchError(LedgerError):
    """Raised when an entry's `algorithm_identifier` differs from the
    segment's expected algorithm.

    Per `specs/ledger.md` § Chain verification + `specs/trust-lineage.md`
    § Algorithm migration: chain segments are bounded by
    `MigrationAnnouncement` records. An entry whose `algorithm_identifier`
    does not match the segment MUST be rejected by the verifier — defense
    against algorithm-downgrade attacks.
    """
