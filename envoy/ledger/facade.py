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
import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol

from kailash.trust.audit_store import AuditEvent, AuditStoreProtocol

if TYPE_CHECKING:
    # Imported lazily inside export() at runtime to avoid a circular import
    # (envoy.ledger.export imports from this module); the TYPE_CHECKING entry
    # gives the return annotation on export() a resolvable name for mypy.
    from envoy.ledger.export import ExportBundle

from envoy.ledger.canonical import canonical_dumps
from envoy.ledger.errors import (
    LedgerHaltedError,
    LedgerRollbackDetectedError,
    LedgerVerificationFailedError,
)
from envoy.ledger.hash_chain import EntryEnvelope, HashChainBuilder
from envoy.ledger.head import HaltedByRollbackRecord, HeadCommitment, RuntimeIdentity
from envoy.ledger.lamport import LamportClock

logger = logging.getLogger(__name__)


# Genesis entry's parent_hash — sha256 of the empty string. Per spec § Entry
# envelope schema, every entry has parent_hash; the Genesis entry uses a
# canonical empty-input hash so verifiers can recognize chain start.
_GENESIS_PARENT_HASH = "sha256:" + hashlib.sha256(b"").hexdigest()

# Sentinel key inside AuditEvent.metadata that carries the full envoy envelope.
# Verifiers find it via `metadata["_envoy_envelope_v1"]`.
_ENVELOPE_METADATA_KEY = "_envoy_envelope_v1"

# Genesis sentinel for the *kailash* audit-store hash chain (raw 64-hex, no
# `sha256:` prefix — distinct from `_GENESIS_PARENT_HASH`, which is the envoy
# envelope chain's genesis). Mirrors kailash's private
# `kailash.trust.audit_store._GENESIS_HASH`; defined locally so we do not import
# an underscore-private upstream symbol. Used to seed the kailash-chain
# `prev_hash` a prev_hash-requiring store (`SqliteAuditStore`) needs at the
# first append over an empty store.
_KAILASH_AUDIT_GENESIS_HASH = "0" * 64

# Phase-01 upper bound on the number of events `rehydrate()` will scan to
# reconstruct chain state. kailash's `AuditFilter` exposes only oldest-first
# `ORDER BY rowid ASC LIMIT` — no descending / tail / offset — so the chain
# *tail* cannot be fetched without materializing the scan set through the
# public store protocol. At Phase-01 (single-principal, single-device) scale
# this set is small (a few MB). A high-volume / multi-tenant ledger (Phase 02+)
# needs a bounded tail query, which depends on an upstream kailash AuditFilter
# descending/tail capability (tracked as a Phase-02 hardening). The guard in
# `rehydrate()` refuses fail-LOUD if the scan hits this cap rather than
# silently restoring chain state from a truncated (wrong) tail.
_REHYDRATE_SCAN_LIMIT = 1_000_000


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

    def get_public_key(self, key_id: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Result of `verify_chain()` per shard 6 § 4 line 213."""

    success: bool
    entries_verified: int
    failed_entry_index: int | None
    failure_reason: str | None


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
        tenant_id: str | None = None,
        classification_policy: Any = None,
        runtime_attestation: dict[str, Any] | None = None,
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
        # S3t: the head-signing runtime's attestation, surfaced in the export
        # bundle's head_commitment.runtime_attestation. `{}` when the ledger was
        # opened without runtime context (a runtime-agnostic open).
        self._runtime_attestation: dict[str, Any] = (
            dict(runtime_attestation) if runtime_attestation else {}
        )
        self._builder = HashChainBuilder()
        # Phase 01 in-memory chain state. Persistence lives in the audit_store;
        # this is the runtime tracking for monotonic guards.
        self._sequence: int = 0
        self._lamport_time: int = 0
        self._local_seq: int = 0
        self._last_entry_id: str = _GENESIS_PARENT_HASH
        self._head: HeadCommitment | None = None
        self._halted: bool = False

        # The kailash audit store keeps its OWN hash chain (raw 64-hex
        # prev_hash/hash, defense-in-depth alongside the envoy envelope chain).
        # The two concrete stores expose that chain differently:
        #   - InMemoryAuditStore.create_event() reads its own `self.last_hash`;
        #     it has NO `prev_hash` parameter.
        #   - SqliteAuditStore.create_event(prev_hash=...) REQUIRES the caller
        #     to supply the chain-tail hash (file-backed: no sync last_hash).
        # Detect which contract this store uses ONCE (also matches test wrapper
        # stores that forward via `**kwargs`), then thread the kailash-chain
        # prev_hash through `_envelope_to_audit_event` only when required.
        # `rehydrate()` restores `_kailash_prev_hash` from a populated store.
        self._store_needs_prev_hash: bool = (
            "prev_hash"
            in inspect.signature(audit_store.create_event).parameters  # type: ignore[attr-defined]
        )
        self._kailash_prev_hash: str = _KAILASH_AUDIT_GENESIS_HASH

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def current_sequence(self) -> int:
        """Highest sequence number this ledger has issued or observed.

        `0` before any append on a fresh chain; after `rehydrate()` it reflects
        the persisted tail. Public read accessor so callers / tests do not have
        to reach into chain-internal state (`head_commitment()` is `None` after
        rehydrate until the first post-rehydrate append, so it cannot serve
        this role).
        """
        return self._sequence

    async def rehydrate(self) -> None:
        """Reconstruct in-memory chain counters from the backing audit store.

        A fresh process that constructs an `EnvoyLedger` over a *populated*
        durable store (e.g. `SqliteAuditStore`) starts with `_sequence = 0`,
        `_last_entry_id = <genesis>`, `_lamport_time = 0`. Appending in that
        state would re-issue sequence 1 with a genesis parent — *forking* the
        chain. `rehydrate()` reads the persisted envelopes and restores the
        counters so the next `append()` continues the existing chain.

        Restores the chain counters AND re-mints the signed head commitment:

        - Counters (`_sequence` / `_last_entry_id` / `_lamport_time` /
          `_local_seq` / the kailash-chain `_kailash_prev_hash`) so the next
          `append()` continues the existing chain instead of forking it.
        - `_head` is re-minted from the persisted tail
          (`_mint_head_commitment(entry_id=<tail>, sequence=<tail>)`),
          re-signing it with the injected signing key. This is what lets
          `export()` run on a fresh process: `export()` reads `self._head` and
          without this would refuse (head `None`) even over a populated store.
          The re-minted head carries a fresh `signed_at` each process — that is
          correct: the head is internally consistent (its signature covers its
          own `signed_at`) and the verifier checks it against the trust-anchor
          public key, not against a fixed timestamp.

        Cross-process *verifiability* of the re-minted head + the persisted
        entries requires a DURABLE signing key (the same key signed both) —
        provided by `envoy.ledger.keystore` and wired in at the digest/export
        bootstrap. With an ephemeral key the re-mint is still well-formed but
        the head and entry signatures would not share a key; that path has no
        cross-process export in production.

        Idempotent; a no-op on an empty store. Safe to call after every
        construction — the durable writers and the `envoy ledger export`
        reader all open through `envoy.ledger.bootstrap.open_durable_ledger`,
        which calls this.

        Scale bound: reconstructs from a scan capped at `_REHYDRATE_SCAN_LIMIT`
        (see that constant — kailash's `AuditFilter` is oldest-first only, so
        the tail needs a full scan). Acceptable at Phase-01 scale; a high-volume
        ledger raises `LedgerError` at the cap (fail-loud) and needs the
        Phase-02 bounded tail query.

        Raises:
            LedgerError: if the persisted ledger exceeds `_REHYDRATE_SCAN_LIMIT`.
        """
        from kailash.trust.audit_store import AuditFilter

        events = await self._audit_store.query(AuditFilter(limit=_REHYDRATE_SCAN_LIMIT))
        if len(events) >= _REHYDRATE_SCAN_LIMIT:
            # The scan hit the Phase-01 cap. kailash's AuditFilter returns
            # oldest-first, so the returned set is NOT the chain tail — restoring
            # from it would silently rebuild chain state from the wrong entry.
            # Refuse fail-LOUD instead. The real fix (a bounded tail query) needs
            # an upstream kailash AuditFilter descending capability; see
            # `_REHYDRATE_SCAN_LIMIT` (tracked Phase-02 hardening).
            from envoy.ledger.errors import LedgerError

            raise LedgerError(
                f"ledger exceeds the Phase-01 rehydrate scan bound "
                f"({_REHYDRATE_SCAN_LIMIT} events); chain-tail reconstruction needs "
                f"the Phase-02 bounded tail query (upstream kailash AuditFilter "
                f"descending support)"
            )
        if events:
            # `query()` returns events in append (rowid) order, so the last
            # element is the kailash-chain tail; its raw 64-hex `hash` is the
            # `prev_hash` the next append must chain onto for a
            # prev_hash-requiring store. Restored regardless of envoy-envelope
            # presence (the kailash chain spans every event type).
            self._kailash_prev_hash = events[-1].hash
        envelopes = [
            e.metadata[_ENVELOPE_METADATA_KEY]
            for e in events
            if _ENVELOPE_METADATA_KEY in (e.metadata or {})
        ]
        if not envelopes:
            return

        envelopes.sort(key=lambda env: env["sequence"])
        tail = envelopes[-1]
        self._sequence = tail["sequence"]
        self._last_entry_id = tail["entry_id"]
        # The Lamport clock advances past every observed event (the next
        # append does max-then-+1), so restore from the global maximum.
        self._lamport_time = max(env["lamport_clock"]["lamport_time"] for env in envelopes)
        # local_seq is a PER-DEVICE monotonic counter — restore it only from
        # THIS device's entries (Phase 01 is single-device; this stays correct
        # when Phase 02 admits multiple devices into one chain).
        this_device = f"device:{self._device_id}"
        local_seqs = [
            env["lamport_clock"]["local_seq"]
            for env in envelopes
            if env.get("signed_by") == this_device
        ]
        self._local_seq = max(local_seqs) if local_seqs else 0

        # Re-mint the signed head from the restored tail so `export()` (which
        # reads `self._head`) works on a fresh process. `_head` is None here
        # (rehydrate runs before any append), so the monotonic guard in
        # `_mint_head_commitment` is skipped — it just signs a head over the
        # tail entry with the injected key.
        self._head = self._mint_head_commitment(
            entry_id=self._last_entry_id, sequence=self._sequence
        )

        logger.info(
            "ledger.rehydrate.ok",
            extra={
                "restored_sequence": self._sequence,
                "restored_lamport_time": self._lamport_time,
                "restored_local_seq": self._local_seq,
                "restored_head": True,
                "entry_count": len(envelopes),
            },
        )

    async def append(
        self,
        *,
        entry_type: str,
        content: dict[str, Any],
        intent_id: str | None = None,
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
        try:
            new_head = self._mint_head_commitment(entry_id=entry_id, sequence=tentative_sequence)
        except LedgerRollbackDetectedError:
            # Per `specs/ledger.md` § Halted state: when the runtime detects
            # a rollback, it appends a HaltedByRollback entry BEFORE halting
            # further Ledger writes. `_mint_head_commitment` set
            # `self._halted = True` before raising; the persist below
            # bypasses the public `append()` halted-gate by calling
            # `self._audit_store.append` directly. The halt record's
            # forensic payload preserves last-known-good vs detected-head
            # so post-mortem recovery can locate the divergence point.
            #
            # Invariant: `self._head` is non-None on this branch — the
            # rollback detection itself requires it (per
            # `_mint_head_commitment` line 577). The assert documents the
            # invariant for static analysis.
            assert self._head is not None
            try:
                await self._persist_halt_record(
                    last_known_good_sequence=self._head.head_sequence,
                    last_known_good_entry_id=self._head.head_entry_id,
                    detected_sequence=tentative_sequence,
                    detected_entry_id=entry_id,
                    detection_reason="sequence_decrease",
                )
            except Exception:
                # Persist failure does NOT suppress the rollback signal —
                # the original LedgerRollbackDetectedError still propagates.
                # Operators that grep for `ledger.halt_record_persist_failed`
                # see the secondary failure alongside the primary halt.
                logger.exception("ledger.halt_record_persist_failed")
            raise

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
        # Advance the kailash-chain tail so the NEXT prev_hash-requiring
        # create_event() chains onto this event. Harmless for in-memory stores
        # (which ignore `_kailash_prev_hash`); only advanced after a successful
        # persist, mirroring the H-1 atomicity invariant above.
        self._kailash_prev_hash = audit_event.hash

        return entry_id

    async def head_commitment(self) -> HeadCommitment | None:
        """Return the latest signed HeadCommitment, or None if no entries appended."""
        return self._head

    async def query(
        self,
        *,
        filter: dict[str, Any],
        since: datetime,
        until: datetime,
    ) -> list[EntryEnvelope]:
        """Return EntryEnvelopes matching `filter` in the `[since, until)` window.

        Per `specs/ledger.md` § Entry types + shard 6 (`01-analysis/
        06-envoy-ledger-implementation.md` § 5.2) — this is the shard-11 Daily
        Digest content source. Shard 11 § 5.1 enumerates the entry types the
        digest reads (post-execution outcomes, refusals, pending grants,
        planned actions, ritual completions); this method is the single query
        primitive every digest section uses.

        Filter keys (all optional; AND semantics):

        - ``principal_id``: matches when the inner envelope ``content`` carries
          a ``principal_id`` equal to the filter value. Post-filtered in-Python
          because the kailash ``AuditFilter`` surface does not index
          envelope-content fields.
        - ``event_type``: single string matching ``envelope.type`` exactly.
        - ``event_types``: iterable of strings; OR semantics across the set.
          Mutually exclusive with ``event_type`` — passing both raises
          ``ValueError``.
        - ``tenant_id``: matches the ``AuditEvent.tenant_id`` column (this
          facade populates it from ``self._tenant_id`` at append time).

        Returns a list of ``EntryEnvelope`` sorted ascending by ``sequence``
        (the same order ``verify_chain()`` walks). Empty list when nothing
        matches.

        Phase 01 narrow scope: in-process query over the local
        ``AuditStoreProtocol`` backend; cross-device CRDT merge is Phase 03+.
        The Phase-01 caller (``LedgerAggregator``) materializes the full window
        in memory — the ``BACKFILL_HORIZON_DAYS=7`` cap from shard 11 § 3.4
        bounds query growth.
        """
        from kailash.trust.audit_store import AuditFilter

        if not isinstance(filter, dict):
            raise ValueError(f"filter must be a dict (got {type(filter).__name__!r})")
        if not isinstance(since, datetime) or not isinstance(until, datetime):
            raise ValueError("since and until MUST be datetime instances")

        event_type = filter.get("event_type")
        event_types = filter.get("event_types")
        if event_type is not None and event_types is not None:
            raise ValueError(
                "filter keys 'event_type' and 'event_types' are mutually exclusive",
            )
        if event_type is not None:
            type_set: set[str] | None = {event_type}
        elif event_types is not None:
            type_set = set(event_types)
        else:
            type_set = None

        principal_id = filter.get("principal_id")
        tenant_id = filter.get("tenant_id")

        logger.info(
            "ledger.query.start",
            extra={
                "principal_id_prefix": (principal_id[:8] if principal_id else None),
                "type_filter": sorted(type_set) if type_set else None,
                "since": since.isoformat(),
                "until": until.isoformat(),
            },
        )

        audit_filter = AuditFilter(since=since, until=until, limit=1_000_000)
        events = await self._audit_store.query(audit_filter)

        envelopes: list[EntryEnvelope] = []
        for event in events:
            envelope_dict = (event.metadata or {}).get(_ENVELOPE_METADATA_KEY)
            if envelope_dict is None:
                # Non-envoy events from sibling kailash subsystems — skip.
                continue
            if type_set is not None and envelope_dict.get("type") not in type_set:
                continue
            if tenant_id is not None and event.tenant_id != tenant_id:
                continue
            if principal_id is not None:
                content = envelope_dict.get("content") or {}
                if content.get("principal_id") != principal_id:
                    continue
            envelopes.append(EntryEnvelope.from_dict(envelope_dict))

        envelopes.sort(key=lambda env: env.sequence)
        logger.info(
            "ledger.query.ok",
            extra={
                "matched_count": len(envelopes),
                "scanned_count": len(events),
            },
        )
        return envelopes

    async def export(self) -> ExportBundle:
        """Produce a signed export bundle for the Independent Verifier.

        Per `specs/independent-verifier.md` § Bundle wire format + EC-4
        Phase 01 acceptance gate. The bundle includes every entry in
        order + the latest head_commitment + the trust_anchor_key_set
        (Phase 01 single-device: just the signing key) + a receipt_hash
        that chains the whole bundle into a single sha256.

        Phase 01 narrow scope:
        - Single segment covering [0, head_sequence] (no
          MigrationAnnouncement records to split on).
        - 4-key segment_boundary algorithm_identifier per
          specs/independent-verifier.md L35 R3-M-02 (3-key trust-lineage
          form promoted via SegmentBoundary.from_trust_lineage_3_key).
        - Empty runtime_attestation + empty attestation_chain (Phase 02).
        - JSON-only (PDF receipt_hash form lands at Wave 5 CLI).

        Raises:
            LedgerError: if no entries have been appended yet (empty
                ledger cannot be exported — would violate verifier
                invariant 1).
        """
        import dataclasses
        import hashlib

        from kailash.trust.audit_store import AuditFilter

        from envoy.ledger.export import (
            _BUNDLE_SCHEMA_VERSION,
            ExportBundle,
            SegmentBoundary,
            TrustAnchorKey,
            compute_receipt_hash,
        )

        if self._head is None:
            from envoy.ledger.errors import LedgerError

            raise LedgerError("cannot export an empty ledger — append at least one entry first")

        events = await self._audit_store.query(AuditFilter(limit=1_000_000))
        envoy_envelopes = [
            e.metadata[_ENVELOPE_METADATA_KEY]
            for e in events
            if _ENVELOPE_METADATA_KEY in (e.metadata or {})
        ]
        # Sort ascending by sequence per verifier invariant 1.
        envoy_envelopes.sort(key=lambda env: env["sequence"])

        # Phase 01: single segment covering [0, head_sequence] with the
        # 4-key segment-boundary algorithm_identifier.
        segment = SegmentBoundary.from_trust_lineage_3_key(
            from_sequence=0,
            to_sequence=self._head.head_sequence,
            trust_lineage_form=self._algorithm_identifier,
        )

        # Phase 01 trust anchor key set: just the signing key. Phase 02
        # adds the device_attestation_chain. Per security review M-2 +
        # gate review M-3: hash the signing_key_id to produce the spec-
        # mandated sha256:<hex> shape (avoids double-prefix hazard if the
        # caller-supplied key_id already has a prefix).
        key_id_hash = hashlib.sha256(self._signing_key_id.encode("utf-8")).hexdigest()
        anchor = TrustAnchorKey(
            key_id=f"sha256:{key_id_hash}",
            public_key_hex=self._signing_pubkey,
            key_class="runtime_device",
            valid_from=self._head.signed_at,
            valid_until=None,
        )

        # Per gate review M-3 + security review M-2: device_id MUST be
        # sha256:<hex> per spec L29. The producer's logical device_id is
        # caller-supplied human-readable; the wire form is its sha256.
        device_id_hash = hashlib.sha256(self._device_id.encode("utf-8")).hexdigest()
        wire_device_id = f"sha256:{device_id_hash}"

        # SECURITY H-1 fix: build the ExportBundle with a placeholder
        # receipt_hash, then compute the real receipt_hash from
        # `bundle.to_dict_minus_receipt()` (the dataclass's own canonical
        # view), then dataclasses.replace to install the real value.
        # This eliminates the parallel-dict byte-identity hazard — the
        # receipt commits to the SAME canonical bytes the verifier
        # reconstructs from the bundle.
        placeholder_receipt = "sha256:" + ("0" * 64)
        interim_bundle = ExportBundle(
            schema_version=_BUNDLE_SCHEMA_VERSION,
            exported_at=_now_canonical(),
            device_id=wire_device_id,
            tenant_id=self._tenant_id,
            segment_boundaries=(segment,),
            entries=tuple(dict(e) for e in envoy_envelopes),
            head_commitment=self._head,
            trust_anchor_key_set=(anchor,),
            runtime_attestation=self._runtime_attestation,
            receipt_hash=placeholder_receipt,
        )
        receipt_hash = compute_receipt_hash(interim_bundle.to_dict_minus_receipt())
        return dataclasses.replace(interim_bundle, receipt_hash=receipt_hash)

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
        # kailash's AuditStoreProtocol stub declares only append/close/query/
        # verify_chain; create_event() is the concrete store's factory (see
        # docstring above). Annotate the result so dataclasses.replace() below
        # round-trips the AuditEvent type instead of leaking Any.
        create_kwargs: dict[str, Any] = {
            "actor": envelope.signed_by,
            "action": envelope.type,
            "resource": "ledger.entry",
            "outcome": "success",
            "metadata": {_ENVELOPE_METADATA_KEY: envelope_dict},
            "event_id": envelope.entry_id,
            "timestamp": envelope.timestamp,
        }
        # A file-backed store (`SqliteAuditStore`) cannot read a sync
        # `last_hash`, so it requires the kailash-chain `prev_hash` explicitly;
        # the in-memory store reads its own `last_hash` and rejects the kwarg.
        # `_store_needs_prev_hash` (resolved at construction) selects the path.
        if self._store_needs_prev_hash:
            create_kwargs["prev_hash"] = self._kailash_prev_hash
        event: AuditEvent = self._audit_store.create_event(  # type: ignore[attr-defined]
            **create_kwargs,
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
    # Internal: HaltedByRollback persistence
    # ------------------------------------------------------------------

    async def _persist_halt_record(
        self,
        *,
        last_known_good_sequence: int,
        last_known_good_entry_id: str,
        detected_sequence: int,
        detected_entry_id: str,
        detection_reason: str,
    ) -> None:
        """Mint + sign + append a HaltedByRollback entry to the audit_store.

        Per `specs/ledger.md` § Halted state, the entry is appended BEFORE
        halting further Ledger writes. The caller (`append()` rollback
        handler) MUST have already set `self._halted = True` (via
        `_mint_head_commitment`) so that any concurrent caller hitting the
        public `append()` entrypoint is rejected with `LedgerHaltedError`
        rather than racing this persist.

        The halt record uses `self._sequence + 1` as its own envelope
        sequence (the rejected tentative slot is now the halt-record's
        slot). After persistence, chain state advances so `verify_chain()`
        walks the halt record correctly; further appends are blocked by
        the halted-gate at the public `append()` entrypoint.

        Detection reasons are restricted to the spec-mandated set:
        - `sequence_decrease` — head_sequence non-monotonic (Phase 01 path)
        - `head_signature_mismatch` — HeadCommitment signature failed (Phase 02+)
        - `algorithm_identifier_downgrade` — entry algorithm regressed (Phase 02+)
        """
        runtime_identity = RuntimeIdentity.from_runtime(
            device_id=self._device_id,
            signing_key_id=self._signing_key_id,
            algorithm_identifier=self._algorithm_identifier,
        )
        halt_record = HaltedByRollbackRecord(
            last_known_good_sequence=last_known_good_sequence,
            last_known_good_entry_id=last_known_good_entry_id,
            detected_sequence=detected_sequence,
            detected_entry_id=detected_entry_id,
            detection_reason=detection_reason,
            halted_at=_now_canonical(),
            schema_version=HaltedByRollbackRecord._SCHEMA_VERSION,
            runtime_identity=runtime_identity,
        )

        halt_content = halt_record.to_dict()
        halt_content_hash = "sha256:" + hashlib.sha256(canonical_dumps(halt_content)).hexdigest()
        halt_sequence = self._sequence + 1
        halt_lamport = LamportClock(
            lamport_time=self._lamport_time + 1,
            device_id=self._device_id,
            local_seq=self._local_seq + 1,
        )
        halt_timestamp = halt_record.halted_at

        canonical_bytes, halt_entry_id = self._builder.build_unsigned(
            prev_entry_id=self._last_entry_id,
            sequence=halt_sequence,
            lamport=halt_lamport,
            timestamp=halt_timestamp,
            type_="HaltedByRollback",
            content=halt_content,
            intent_id=None,
            content_trust_level="system",
            description_content_hash=halt_content_hash,
            signed_by=f"device:{self._device_id}",
            algorithm_identifier=self._algorithm_identifier,
        )
        halt_signature = self._key_manager.sign_with_key(self._signing_key_id, canonical_bytes)
        halt_envelope = self._builder.seal(
            entry_id=halt_entry_id,
            signature_hex=halt_signature,
            prev_entry_id=self._last_entry_id,
            sequence=halt_sequence,
            lamport=halt_lamport,
            timestamp=halt_timestamp,
            type_="HaltedByRollback",
            content=halt_content,
            intent_id=None,
            content_trust_level="system",
            description_content_hash=halt_content_hash,
            signed_by=f"device:{self._device_id}",
            algorithm_identifier=self._algorithm_identifier,
        )
        halt_audit_event = self._envelope_to_audit_event(halt_envelope)
        await self._audit_store.append(halt_audit_event)

        # Advance chain state so verify_chain() walks the halt record correctly.
        # Per spec, no further appends occur (halted-gate blocks them), so
        # these advances are terminal — the halt record IS the chain tail.
        self._lamport_time += 1
        self._local_seq += 1
        self._sequence = halt_sequence
        self._last_entry_id = halt_entry_id
        self._kailash_prev_hash = halt_audit_event.hash

        logger.warning(
            "ledger.halted_by_rollback",
            extra={
                "halt_entry_id": halt_entry_id,
                "detection_reason": detection_reason,
                "detected_sequence": detected_sequence,
                "last_known_good_sequence": last_known_good_sequence,
            },
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
