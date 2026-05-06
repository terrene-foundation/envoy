"""EnvoyLedger — Phase 01 ledger facade.

Per `specs/ledger.md` § Purpose + shard `01-analysis/06-envoy-ledger-implementation.md`
§ 4 step 3 (interfaces). This is the production call site that closes both
orphan-watch grace windows from prior shards:

- T-01-15 `TrustStoreAdapter._with_algorithm_id` is consumed transitively
  via `algorithm_identifier` flowing into every `EnvoyLedger.append()` call.
- T-01-17 `EntryEnvelope` + `HashChainBuilder` are consumed at `append()`
  time to construct + sign + persist every entry.

Phase 01 narrow scope:

- `append()` wires HashChainBuilder.build_unsigned + sign + seal +
  AuditEvent translation + AuditStoreProtocol.append + head update.
- `head_commitment()` returns the latest signed HeadCommitment.
- `verify_chain()` walks every entry and verifies parent_hash + signature.
- Single-device, single-principal — no CRDT merge, no cross-device sync.

Phase 02+ extends:

- Two-phase signing (`PhaseARecord` / `PhaseBRecord`) wired through runtime
  per `specs/ledger.md` § Two-phase signing (Wave 3 Grant Moment).
- Orphan resolution + 30-day TTL sweep (Wave 3).
- Export bundle (T-01-19).
- HaltedByRollback emission on cross-device sync rollback detection.
- Multi-principal query filtering per `rules/tenant-isolation.md` Rule 5.

Translation contract (envoy → kailash):

The kailash `AuditStoreProtocol` consumes `AuditEvent` records (26 fields).
Envoy entries carry an `EntryEnvelope` (14 fields). The translation:

- envoy.entry_id        → kailash.event_id (sha256: prefix retained)
- envoy.timestamp       → kailash.timestamp
- envoy.signed_by       → kailash.actor
- envoy.type            → kailash.action AND kailash.event_type
- envoy.parent_hash     → kailash.prev_hash
- envoy.entry_id        → kailash.hash (the chain hash)
- (envoy envelope dict) → kailash.metadata under `_envoy_envelope_v1` key
- envoy.tenant_id       → kailash.tenant_id (if multi-tenant)

The full envoy envelope persists inside `metadata["_envoy_envelope_v1"]`
so a future verifier can reconstruct the canonical bytes byte-identically.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from kailash.trust.audit_store import AuditEvent, AuditStoreProtocol

from envoy.ledger.canonical import canonical_dumps
from envoy.ledger.errors import (
    LedgerHaltedError,
    LedgerRollbackDetectedError,
    LedgerVerificationFailedError,
)
from envoy.ledger.hash_chain import EntryEnvelope, HashChainBuilder
from envoy.ledger.head import HeadCommitment
from envoy.ledger.lamport import LamportClock

logger = logging.getLogger(__name__)


# Genesis entry's parent_hash — sha256 of the empty string. Per spec § Entry
# envelope schema, every entry has parent_hash; the Genesis entry uses a
# canonical empty-input hash so verifiers can recognize chain start.
_GENESIS_PARENT_HASH = "sha256:" + hashlib.sha256(b"").hexdigest()

# Sentinel key inside AuditEvent.metadata that carries the full envoy envelope.
# Verifiers find it via `metadata["_envoy_envelope_v1"]`.
_ENVELOPE_METADATA_KEY = "_envoy_envelope_v1"


class _KeyManagerProtocol(Protocol):
    """Subset of `kailash.trust.key_manager.InMemoryKeyManager` we depend on.

    The Phase 01 facade does NOT require the full kailash KeyManager surface
    — only sync sign + async verify + get_public_key per the actual kailash
    2.13.4 shape discovered via inspect.signature sweep. Note: kailash's
    `verify(payload, signature, public_key)` takes the public key DIRECTLY,
    not a key_id — the facade resolves the public key at construction
    time via `get_public_key(signing_key_id)` and stores it for use during
    `verify_chain()`.
    """

    def sign_with_key(self, key_id: str, payload: Any) -> str: ...

    async def verify(self, payload: Any, signature: str, public_key: str) -> bool: ...

    def has_key(self, key_id: str) -> bool: ...

    def get_public_key(self, key_id: str) -> Optional[str]: ...


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Result of `verify_chain()` per shard 6 § 4 line 213."""

    success: bool
    entries_verified: int
    failed_entry_index: Optional[int]
    failure_reason: Optional[str]


class EnvoyLedger:
    """Phase 01 ledger facade producing signed hash-chain entries.

    Per shard 6 § 4: every Wave 1+ primitive that needs an audit row goes
    through `EnvoyLedger.append()`. The facade handles:

    1. Lamport clock tick (per-call monotonic).
    2. Canonical-bytes derivation via HashChainBuilder.build_unsigned.
    3. Ed25519 signature via key_manager.sign_with_key.
    4. EntryEnvelope sealing.
    5. AuditEvent translation + AuditStoreProtocol.append.
    6. HeadCommitment update + signing.
    7. Halted-state guard — if the facade was halted by a prior rollback,
       refuse further writes per `LedgerHaltedError`.

    Constructor takes an AuditStoreProtocol-shaped backend (caller provides
    `InMemoryAuditStore` for Tier 1 tests, `SqliteAuditStore` for T-01-21
    Tier 2 + production), a key_manager (kailash InMemoryKeyManager satisfies
    the Phase 01 protocol), and the device + signing identity.
    """

    def __init__(
        self,
        *,
        audit_store: AuditStoreProtocol,
        key_manager: _KeyManagerProtocol,
        signing_key_id: str,
        device_id: str,
        algorithm_identifier: dict[str, str],
        tenant_id: Optional[str] = None,
        classification_policy: Any = None,
    ) -> None:
        if not signing_key_id:
            raise ValueError("signing_key_id is required")
        if not device_id:
            raise ValueError("device_id is required")
        # Verify the key exists at construction so a misconfigured ledger
        # fails loud at init rather than at first append.
        if not key_manager.has_key(signing_key_id):
            raise ValueError(
                f"signing_key_id={signing_key_id!r} not registered with key_manager — "
                "register the keypair before constructing EnvoyLedger"
            )
        # Resolve public key once at construction. kailash's verify() takes
        # the public key directly (not a key_id); caching here avoids
        # repeated lookups on every verify_chain() entry.
        signing_pubkey = key_manager.get_public_key(signing_key_id)
        if signing_pubkey is None:
            raise ValueError(f"key_manager.get_public_key({signing_key_id!r}) returned None")
        # Validate algorithm_identifier wire shape per T-01-15 R2-H-01 contract
        # (fail-loud here so EnvoyLedger.append() doesn't have to check on
        # every call).
        expected = {"sig", "hash", "shamir"}
        if set(algorithm_identifier.keys()) != expected:
            raise ValueError(
                f"algorithm_identifier MUST be the 3-key {{sig, hash, shamir}} "
                f"wire form per specs/trust-lineage.md L24 (got "
                f"{sorted(algorithm_identifier.keys())})"
            )

        self._audit_store = audit_store
        self._key_manager = key_manager
        self._signing_key_id = signing_key_id
        self._signing_pubkey = signing_pubkey  # cached for verify_chain()
        self._device_id = device_id
        self._algorithm_identifier = dict(algorithm_identifier)
        self._tenant_id = tenant_id
        self._classification_policy = classification_policy
        self._builder = HashChainBuilder()
        # Phase 01 in-memory chain state. Persistence lives in the audit_store;
        # this is the runtime tracking for monotonic guards.
        self._sequence: int = 0
        self._lamport_time: int = 0
        self._local_seq: int = 0
        self._last_entry_id: str = _GENESIS_PARENT_HASH
        self._head: Optional[HeadCommitment] = None
        self._halted: bool = False

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def is_halted(self) -> bool:
        return self._halted

    async def append(
        self,
        *,
        entry_type: str,
        content: dict[str, Any],
        intent_id: Optional[str] = None,
        content_trust_level: str = "system",
    ) -> str:
        """Sign + append a new entry. Returns the new entry_id.

        Closes the T-01-17 orphan-watch grace window for EntryEnvelope +
        HashChainBuilder by invoking them on the production hot path.

        Args:
            entry_type: One of the entry types per `specs/ledger.md` § Entry types.
            content: Per-type content dict; opaque to the facade. The producer
                primitive owns the schema.
            intent_id: Phase A intent hash for two-phase-signed entries (Phase 03+);
                None on Phase 01 single-phase records.
            content_trust_level: One of `user-authored | tool-output | channel-message
                | derived-external | heartbeat | system | sub-agent | llm-authored`.

        Note: classified-PK record_id filtering via `format_record_id_for_event`
        per `rules/event-payload-classification.md` Rule 1 is explicitly
        deferred to T-01-21 Tier 2 wiring (where a real ClassificationPolicy
        from kailash-dataflow lands). Phase 01 narrow scope: producers that
        need redaction call `format_record_id_for_event` before constructing
        `content` and pass the redacted record_id directly. The facade does
        NOT accept a `record_id_model` kwarg in Phase 01 to avoid the Rule 3c
        "documented kwarg accepted but unused" anti-pattern; the kwarg
        re-enters when a real consumer wires it.

        Raises:
            LedgerHaltedError: if a prior `HaltedByRollback` halted the chain.
            ValueError: on shape mismatch (entry_type empty, content non-dict, etc.).
        """
        if self._halted:
            raise LedgerHaltedError(
                "EnvoyLedger is halted — a prior rollback detection wrote a "
                "HaltedByRollback entry; investigate via envoy ledger audit "
                "before further writes."
            )
        if not entry_type or not isinstance(entry_type, str):
            raise ValueError(f"entry_type must be non-empty str (got {entry_type!r})")
        if not isinstance(content, dict):
            raise ValueError(f"content must be a dict (got {type(content).__name__!r})")

        # Compute TENTATIVE counter values without mutating chain state.
        # Atomicity invariant per security review H-1: counters advance ONLY
        # after audit_store.append() succeeds AND the head commitment is
        # minted. A failure at any step leaves chain state unchanged so the
        # next append retries from the same baseline.
        tentative_lamport_time = self._lamport_time + 1
        tentative_local_seq = self._local_seq + 1
        tentative_sequence = self._sequence + 1
        lamport = LamportClock(
            lamport_time=tentative_lamport_time,
            device_id=self._device_id,
            local_seq=tentative_local_seq,
        )

        timestamp = _now_canonical()

        # Compute description_content_hash from canonical-encoded content.
        # The producer MAY pre-compute this and pass via content; Phase 01
        # default is sha256 of the canonical content bytes.
        description_content_hash = "sha256:" + hashlib.sha256(canonical_dumps(content)).hexdigest()

        canonical_bytes, entry_id = self._builder.build_unsigned(
            prev_entry_id=self._last_entry_id,
            sequence=tentative_sequence,
            lamport=lamport,
            timestamp=timestamp,
            type_=entry_type,
            content=content,
            intent_id=intent_id,
            content_trust_level=content_trust_level,
            description_content_hash=description_content_hash,
            signed_by=f"device:{self._device_id}",
            algorithm_identifier=self._algorithm_identifier,
        )

        signature_hex = self._key_manager.sign_with_key(self._signing_key_id, canonical_bytes)

        envelope = self._builder.seal(
            entry_id=entry_id,
            signature_hex=signature_hex,
            prev_entry_id=self._last_entry_id,
            sequence=tentative_sequence,
            lamport=lamport,
            timestamp=timestamp,
            type_=entry_type,
            content=content,
            intent_id=intent_id,
            content_trust_level=content_trust_level,
            description_content_hash=description_content_hash,
            signed_by=f"device:{self._device_id}",
            algorithm_identifier=self._algorithm_identifier,
        )

        # Mint + sign the new head commitment BEFORE persisting the entry.
        # Atomicity invariant per security review H-2: signing the head is
        # cheap + reversible; if audit_store.append fails we discard the
        # head locally. If we instead persisted the entry first and then
        # the head signing failed (e.g., transient key_manager error), the
        # entry would be persisted with stale head — chain ahead of head.
        new_head = self._mint_head_commitment(entry_id=entry_id, sequence=tentative_sequence)

        # Translate envoy envelope → kailash AuditEvent.
        audit_event = self._envelope_to_audit_event(envelope)
        # AuditStoreProtocol declares append() sync, but the kailash 2.13.4
        # InMemoryAuditStore + SqliteAuditStore implementations are async
        # (deviation pattern documented in journal/0009 — same as kailash
        # TrustOperations). Discovered via inspect.signature sweep.
        await self._audit_store.append(audit_event)

        # SUCCESS — atomically commit the tentative state. Per security
        # review H-1, only past this point are counters advanced;
        # audit_store.append failure above leaves chain state unchanged.
        self._lamport_time = tentative_lamport_time
        self._local_seq = tentative_local_seq
        self._sequence = tentative_sequence
        self._last_entry_id = entry_id
        self._head = new_head

        return entry_id

    async def head_commitment(self) -> Optional[HeadCommitment]:
        """Return the latest signed HeadCommitment, or None if no entries appended."""
        return self._head

    async def verify_chain(self) -> VerificationReport:
        """Walk every entry in the audit store and verify parent_hash chain
        + Ed25519 signature on each entry's canonical bytes.

        Phase 01 narrow scope: walks the local audit_store via query() and
        verifies in append-order. T-01-19 export bundle adds the cross-process
        verifier (envoy-ledger-verify); Phase 02 adds the cross-device CRDT
        merge integrity check.
        """
        from kailash.trust.audit_store import AuditFilter

        events = await self._audit_store.query(AuditFilter(limit=1_000_000))
        # Filter to envoy-envelope-bearing events only (the audit_store may
        # contain non-envoy events from sibling kailash subsystems).
        envoy_events = [e for e in events if _ENVELOPE_METADATA_KEY in (e.metadata or {})]
        envoy_events.sort(key=lambda e: e.metadata[_ENVELOPE_METADATA_KEY]["sequence"])

        prev_entry_id = _GENESIS_PARENT_HASH
        for idx, event in enumerate(envoy_events):
            envelope_dict = event.metadata[_ENVELOPE_METADATA_KEY]
            if envelope_dict["parent_hash"] != prev_entry_id:
                return VerificationReport(
                    success=False,
                    entries_verified=idx,
                    failed_entry_index=idx,
                    failure_reason=(
                        f"parent_hash mismatch at index {idx}: expected "
                        f"{prev_entry_id!r}, got {envelope_dict['parent_hash']!r}"
                    ),
                )

            # Reconstruct canonical bytes from the unsigned envelope shape.
            unsigned = {
                k: v for k, v in envelope_dict.items() if k not in ("entry_id", "signature_hex")
            }
            canonical_bytes = canonical_dumps(unsigned)
            recomputed_id = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
            if recomputed_id != envelope_dict["entry_id"]:
                return VerificationReport(
                    success=False,
                    entries_verified=idx,
                    failed_entry_index=idx,
                    failure_reason=(
                        f"entry_id mismatch at index {idx}: recomputed "
                        f"{recomputed_id!r} != stored {envelope_dict['entry_id']!r}"
                    ),
                )

            # Verify signature via key_manager.verify(payload, signature, public_key)
            # — note kailash takes the public_key directly, not a key_id; we
            # cached the public key at construction time.
            sig_ok = await self._key_manager.verify(
                canonical_bytes,
                envelope_dict["signature_hex"],
                self._signing_pubkey,
            )
            if not sig_ok:
                return VerificationReport(
                    success=False,
                    entries_verified=idx,
                    failed_entry_index=idx,
                    failure_reason=f"signature verification failed at index {idx}",
                )

            prev_entry_id = envelope_dict["entry_id"]

        return VerificationReport(
            success=True,
            entries_verified=len(envoy_events),
            failed_entry_index=None,
            failure_reason=None,
        )

    # ------------------------------------------------------------------
    # Internal: envelope → AuditEvent translation
    # ------------------------------------------------------------------

    def _envelope_to_audit_event(self, envelope: EntryEnvelope) -> AuditEvent:
        """Translate envoy EntryEnvelope into kailash AuditEvent.

        The full envoy envelope is persisted under
        `metadata["_envoy_envelope_v1"]` so a verifier can reconstruct the
        canonical bytes byte-identically.

        Two distinct chains live in this translation:

        - **Envoy's envelope chain** (load-bearing): SHA-256-prefixed
          (`sha256:<hex>`) parent_hash linkage stored INSIDE the envelope
          dict under `metadata["_envoy_envelope_v1"]`. This is what
          `verify_chain()` walks and what the cross-SDK byte-identity
          verifier (T-01-19 export bundle) reconstructs.

        - **Kailash's audit_store chain** (defense-in-depth): raw 64-hex
          (no prefix) `prev_hash` + `hash` fields the kailash store
          maintains via its own `create_event()` factory. We delegate
          chain-shape construction to kailash so its internal integrity
          check (`append()` recomputes hash from event fields) accepts
          the event. Calling the factory is the only safe way to feed
          AuditStoreProtocol per inspect.signature sweep — manual
          construction trips ChainIntegrityError on hash-mismatch.
        """
        import dataclasses

        envelope_dict = envelope.to_dict()
        event = self._audit_store.create_event(
            actor=envelope.signed_by,
            action=envelope.type,
            resource="ledger.entry",
            outcome="success",
            metadata={_ENVELOPE_METADATA_KEY: envelope_dict},
            event_id=envelope.entry_id,
            timestamp=envelope.timestamp,
        )
        # Per security review L-1: propagate tenant_id to AuditEvent so a
        # multi-tenant query (Phase 03) can filter by it. Phase 01 single-
        # principal: tenant_id is None, the kailash field stays None, the
        # query returns the same shape — no behavior change.
        # AuditEvent is frozen; dataclasses.replace() returns a new
        # instance with the patched fields.
        return dataclasses.replace(
            event,
            tenant_id=self._tenant_id,
            agent_id=self._device_id,
        )

    # ------------------------------------------------------------------
    # Internal: HeadCommitment monotonic guard + minting
    # ------------------------------------------------------------------

    def _mint_head_commitment(self, *, entry_id: str, sequence: int) -> HeadCommitment:
        """Mint + sign a new HeadCommitment WITHOUT installing it.

        Per spec § Head commitment, the head_sequence is monotonic
        non-decreasing. A decrease (which Phase 01 single-device flow
        cannot produce, but defensive against future bugs) raises
        `LedgerRollbackDetectedError` AND halts the chain BEFORE the raise
        so the halt persists even if the caller catches the exception.

        Returns the new HeadCommitment for the caller to install on the
        success path. This decoupling enables the atomicity invariant per
        security review H-2: head commitment is minted + signed before
        audit_store.append; if the persistence fails, no head was
        installed; if the persistence succeeds, the caller installs the
        head atomically with the counter advance.
        """
        if self._head is not None and sequence < self._head.head_sequence:
            self._halted = True
            raise LedgerRollbackDetectedError(
                f"HeadCommitment monotonic guard: new sequence {sequence} < "
                f"current head_sequence {self._head.head_sequence}",
                entry_id=entry_id,
            )
        signed_at = _now_canonical()
        # Sign the head tuple (head_sequence, head_entry_id, signed_at).
        head_payload = canonical_dumps(
            {
                "head_sequence": sequence,
                "head_entry_id": entry_id,
                "signed_at": signed_at,
            }
        )
        signature_hex = self._key_manager.sign_with_key(self._signing_key_id, head_payload)
        return HeadCommitment(
            head_sequence=sequence,
            head_entry_id=entry_id,
            signed_at=signed_at,
            signature_hex=signature_hex,
        )

    # ------------------------------------------------------------------
    # Verification helper — used by tests + verify_chain
    # ------------------------------------------------------------------

    async def _raise_on_chain_failure(self) -> None:
        """Internal: convert verify_chain() failure into
        LedgerVerificationFailedError per shard 6 § 4 line 215."""
        report = await self.verify_chain()
        if not report.success:
            raise LedgerVerificationFailedError(
                f"chain verification failed at index {report.failed_entry_index}: "
                f"{report.failure_reason}"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_canonical() -> str:
    """Current UTC time in canonical 27-char ISO 8601 microsecond shape."""
    from envoy.ledger.canonical import _format_timestamp  # noqa: PLC0415

    return _format_timestamp(datetime.now(tz=timezone.utc))


__all__ = ["EnvoyLedger", "VerificationReport"]
