# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.session — store-backed ``SessionRouter`` (WS-6 S4s).

The persistent-session substrate. Phase-01 kept the last long-lived session
state — pending Grant Moments + observed tool-call fingerprints — ONLY in
process memory (``EnvoyGrantMomentRuntime._inflight`` + ``decision_future:
asyncio.Future``; ``runtime.py:403,305``), lost on process exit. That is why
``init`` / ``grant`` / ``chat`` are not buildable as one-shot CLIs: a fresh
``grant`` process cannot see a pending request a prior process issued.

``SessionRouter`` is the durability substrate that closes that gap. It re-opens
TWO durable projections per process invocation, exactly as
``envoy.daily_digest.bootstrap`` re-opens the ledger (``daily_digest/
bootstrap.py:108,116`` → ``ledger/bootstrap.py:100``):

1. **pending-grant TrustVault sub-store** — the durable ``state=pending`` queue
   the ``runtime.py:393-394`` comment promised ("Phase 02 lifts this into a
   TrustVault sub-store"). A fresh ``grant`` process opens the SAME on-disk
   sibling SQLite file and reads the persisted pending rows.
2. **SessionObservedState region** — the durable snapshot of
   ``specs/session-state.md`` § Persistence ("snapshot to Trust Vault encrypted
   at every Ledger append, so a crash mid-session preserves orphan-phase-A
   tracking"). Stored as an opaque canonical-JSON blob keyed by ``session_id``.

The router is SHORT-LIVED, not a daemon — no socket, no PID, no lockfile
lifecycle. Continuity comes from the on-disk projection, not a resident
process. This mirrors ``ledger export``'s cross-process re-openability and is
replay-native for the Phase-02 multi-device index rebuild (deep-dive Q4).

Scope boundary (S4s — STORE ONLY): this shard delivers the empty-but-openable
store + the re-open router skeleton + the raw region read/write surface. It
does NOT build:

- the cross-process decision rendezvous (``await_decision`` poll rewrite) — S4r.
- the ``grant`` pending-grant read surface / CLI — S4g.
- the ``init`` / Boundary-Conversation genesis write — S4i.
- the SessionObservedState first-time-action gate writes — S5o.

Those shards consume the store this module opens. The monotonic ``version``
column on every pending-grant row is the lost-update primitive S4r's poll
re-checks; it is written here but polled there.

Persistence idiom (matches ``envoy.trust.store.TrustStoreAdapter``): one 0o600
sibling SQLite db file (``<stem>.session.db``), a fresh connection per
operation under ``asyncio.to_thread`` (so the async public surface never blocks
the event loop, per ``rules/patterns.md`` § Paired Public Surface), WAL mode,
parameterized queries throughout (``rules/trust-plane-security.md`` MUST Rule
5), ``_validate_id_safety`` on every identifier reaching a SQLite primary key
(MUST Rule 2), 0o600 on the db family (MUST Rule 6).

Keychain-gating: the router re-opens an OS-keychain Ed25519 signing key per
process via ``envoy.ledger.keystore.load_or_create_ledger_key_manager`` (under a
DISTINCT ``signing_key_id`` namespace from the ledger), so the keychain-key
lifecycle invariant the substrate requires (a fresh process recovers the SAME
device key, never a silent ephemeral one) is exercised by this shard. The key
is the trust anchor S4r's signed-resolution rows and S5o's snapshot signatures
will use; S4s opens it and proves it survives restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kailash.trust.key_manager import InMemoryKeyManager

from envoy.grant_moment.resolution import resolution_signing_payload
from envoy.ledger.keystore import load_or_create_ledger_key_manager
from envoy.trust.sqlite_perms import chmod_sqlite_family

logger = logging.getLogger(__name__)

# ── Durable session-store identity ───────────────────────────────────────────
# The signing key the SessionRouter re-opens per process. Namespaced DISTINCTLY
# from the ledger signing key (``envoy-digest-signing-key``) so the two never
# collide in the OS keychain — the session store's resolution/snapshot
# signatures (landed by S4r / S5o) are a separate trust surface from the ledger
# chain. The value is a FIXED constant (matching the ledger's "do NOT change the
# value, it would orphan signed state" discipline at ``ledger/bootstrap.py:57``).
SESSION_SIGNING_KEY_ID = "envoy-session-signing-key"


def session_db_path(vault_path: Path | str) -> Path:
    """Resolve the session store's SQLite file for a given vault path.

    A vault *sibling* file — ``<stem>.session.db`` next to the vault — matching
    the ``.chain.db`` / ``.posture.db`` / ``.bc.db`` / ``.digest.db`` /
    ``.audit.db`` layout the Trust store + durable ledger already establish.
    Every writer (S4i ``init`` genesis, S4g ``grant`` pending rows, S5o
    observed-state snapshots) AND every reader (the cross-process ``grant``
    poll, a fresh ``chat`` process) MUST resolve the path through here so they
    open the SAME file.
    """
    vp = Path(vault_path)
    return vp.parent / f"{vp.stem}.session.db"


# Pending-grant ``state`` enum (deep-dive spec-gap #2 / open-question #2). A
# pending row is the durable form of ``runtime.py:403``'s in-memory
# ``_inflight`` entry; ``resolved`` carries the answer S4r's poll resumes on;
# ``expired`` is the timeout terminal driven by S4r's M2→M3 transition.
PENDING_GRANT_STATES: frozenset[str] = frozenset({"pending", "resolved", "expired"})


def _validate_session_id(identifier: str, *, field: str) -> None:
    """Reject identifiers that could enable path-traversal / null-byte attacks
    before they reach a SQLite primary key.

    Mirrors ``envoy.trust.store._validate_id_safety`` (the same boundary guard
    the Trust store applies to every principal_id / ritual_id) — kept local so
    the session store module has no import-cycle dependency on the trust store.
    Per ``rules/trust-plane-security.md`` MUST Rule 2.
    """
    if not isinstance(identifier, str):
        raise ValueError(f"{field} must be str (got {type(identifier).__name__})")
    if not identifier:
        raise ValueError(f"{field} must not be empty")
    if len(identifier) > 256:
        raise ValueError(f"{field} length {len(identifier)} exceeds max 256")
    if identifier.startswith("."):
        raise ValueError(f"{field} must not start with '.' (hidden-file shape)")
    if any(ch == "\x00" for ch in identifier):
        raise ValueError(f"{field} contains null byte")
    if any(ord(ch) < 0x20 or 0x7F <= ord(ch) < 0xA0 for ch in identifier):
        raise ValueError(f"{field} contains control character")
    if "/" in identifier or "\\" in identifier:
        raise ValueError(f"{field} contains path separator")
    if ".." in identifier:
        raise ValueError(f"{field} contains '..' (path traversal)")


@dataclass(slots=True, frozen=True)
class PendingGrantRow:
    """One durable pending-grant queue row (read-back shape).

    The opaque ``request_json`` is the canonical-JSON ``GrantMomentRequest``
    (S4g writes it; this shard stores + returns it verbatim — S4s does NOT
    parse the wire format). ``version`` is the monotonic lost-update primitive
    S4r's poll re-checks: a writer bumping the row to ``resolved`` increments
    ``version``, so a concurrent reader observes a strictly-newer value.
    """

    request_id: str
    state: str
    request_json: str
    version: int
    created_at: str
    updated_at: str
    resolution_json: str | None = None
    # Detached Ed25519 signature (hex) over ``resolution_signing_payload`` —
    # the cross-process authenticity anchor verified before a resolution is
    # treated as a decision (S4r). NULL on an unresolved (``pending``) row.
    resolution_sig: str | None = None


class SessionRouter:
    """Store-backed session substrate — re-opens two durable projections per
    process invocation.

    Construct synchronously (no I/O). ``await router.open()`` re-opens the
    on-disk store + re-loads the keychain signing key. ``await router.close()``
    when done. A fresh process constructing a new ``SessionRouter`` over the
    same ``vault_path`` re-opens the SAME projections and sees the persisted
    tail — exactly the cross-process re-openability ``ledger export`` proved.

    Per ``rules/facade-manager-detection.md`` Rule 3, the dependencies are
    injected explicitly: ``vault_path`` + ``principal_id`` (keying the keychain
    key) + an optional ``keyring_backend`` (dependency-injectable for tests,
    matching ``TrustStoreAdapter`` / ``build_digest_service``). No global-state
    lookups, no self-construction of a parallel framework.
    """

    def __init__(
        self,
        *,
        vault_path: Path | str,
        principal_id: str,
        keyring_backend: Any = None,
    ) -> None:
        _validate_session_id(principal_id, field="principal_id")
        self._principal_id = principal_id
        self._vault_path = Path(vault_path)
        self._keyring_backend = keyring_backend
        self._db_path = str(session_db_path(self._vault_path))
        self._key_manager: InMemoryKeyManager | None = None
        self._opened = False

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    # Region 1 — pending-grant TrustVault sub-store. ``state`` constrained to
    # PENDING_GRANT_STATES via a CHECK so a malformed write fails loud rather
    # than silently storing an unrecognised state. ``version`` is the monotonic
    # lost-update primitive (S4r poll re-check); ``ttl_expires_at`` bounds queue
    # growth (S4g back-pressure).
    _CREATE_PENDING_GRANT_SQL = """
    CREATE TABLE IF NOT EXISTS pending_grant (
        request_id     TEXT PRIMARY KEY,
        principal_id   TEXT NOT NULL,
        session_id     TEXT NOT NULL,
        state          TEXT NOT NULL CHECK (state IN ('pending','resolved','expired')),
        request_json   TEXT NOT NULL,
        resolution_json TEXT,
        resolution_sig TEXT,
        version        INTEGER NOT NULL DEFAULT 1,
        ttl_expires_at TEXT NOT NULL,
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
    """
    # Fast-lookup index for the ``grant list`` read surface (S4g) + the S4r poll:
    # "give me pending rows for this principal, newest first".
    _CREATE_PENDING_GRANT_INDEX_SQL = """
    CREATE INDEX IF NOT EXISTS ix_pending_grant_principal_state
        ON pending_grant (principal_id, state, updated_at)
    """

    # Region 2 — SessionObservedState. One opaque canonical-JSON blob per
    # session_id (specs/session-state.md § Schema). S5o owns the fingerprint /
    # first-time-action gate semantics; S4s stores + returns the blob verbatim
    # so the snapshot-at-every-Ledger-append crash-safety property
    # (session-state.md:182) has a durable home.
    _CREATE_SESSION_OBSERVED_STATE_SQL = """
    CREATE TABLE IF NOT EXISTS session_observed_state (
        session_id     TEXT PRIMARY KEY,
        principal_id   TEXT NOT NULL,
        state_json     TEXT NOT NULL,
        version        INTEGER NOT NULL DEFAULT 1,
        updated_at     TEXT NOT NULL
    )
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """Re-open the durable store + re-load the keychain signing key.

        Idempotent. Re-loads the OS-keychain Ed25519 key (fail-loud: a missing
        keychain / corrupt record raises the keystore's typed errors, never a
        silent ephemeral fallback), then initialises the SQLite schema. A fresh
        process calling ``open()`` over the same ``vault_path`` recovers the
        SAME key AND the SAME on-disk projections.
        """
        if self._opened:
            return
        # Keychain key FIRST — fail-loud before touching the store, so a
        # keychain-down condition surfaces as the keystore's typed error rather
        # than a half-open store. Same fail-loud discipline as
        # ``build_digest_service`` (daily_digest/bootstrap.py:108).
        self._key_manager = await load_or_create_ledger_key_manager(
            principal_id=self._principal_id,
            signing_key_id=SESSION_SIGNING_KEY_ID,
            keyring_backend=self._keyring_backend,
        )
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._sync_init_store)
        self._opened = True
        logger.info(
            "session.router.opened",
            extra={"session_db": self._db_path, "principal_hint": self._principal_id[:8]},
        )

    async def close(self) -> None:
        """Zeroize the in-memory key material (caller responsibility).

        No SQLite handle is held open between operations — every op opens a
        fresh connection under ``asyncio.to_thread`` and closes it — so there is
        no pool to release. The keychain key's in-memory copy IS cleared to
        minimise residency per ``rules/trust-plane-security.md`` MUST NOT Rule 3.
        """
        if self._key_manager is not None:
            keys = getattr(self._key_manager, "_keys", None)
            if isinstance(keys, dict):
                keys.clear()
            self._key_manager = None
        self._opened = False

    def _sync_init_store(self) -> None:
        """Create both region tables + the pending-grant index. 0o600 on the db
        family per ``rules/trust-plane-security.md`` MUST Rule 6 — the session
        store holds pending governance grants + observed-state snapshots."""
        db_file = Path(self._db_path)
        if not db_file.exists():
            db_file.touch(mode=0o600)
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(self._CREATE_PENDING_GRANT_SQL)
            conn.execute(self._CREATE_PENDING_GRANT_INDEX_SQL)
            conn.execute(self._CREATE_SESSION_OBSERVED_STATE_SQL)
            conn.commit()
        finally:
            conn.close()
        # WAL mode materialises ``-wal`` / ``-shm`` siblings after the first
        # write; tighten the whole family (chmod-the-main-file-only would leave
        # a world-readable ``-wal``).
        chmod_sqlite_family(db_file, log_event="session.store.chmod_failed")

    def _connect(self) -> sqlite3.Connection:
        """Short-lived SQLite connection (fresh per op on the to_thread worker).

        A fresh connection per operation avoids the cross-thread reuse error
        sqlite3 raises by default — matching ``TrustStoreAdapter._bc_connect``.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _require_open(self) -> None:
        if not self._opened:
            raise RuntimeError(
                "SessionRouter used before open() — call `await router.open()` "
                "to re-open the durable store + keychain key first"
            )

    @property
    def vault_path(self) -> Path:
        return self._vault_path

    @property
    def principal_id(self) -> str:
        return self._principal_id

    @property
    def db_path(self) -> str:
        return self._db_path

    # ------------------------------------------------------------------
    # Region 1 — pending-grant TrustVault sub-store (raw store surface)
    # ------------------------------------------------------------------
    #
    # S4s ships the empty-but-openable store + the raw put/get the durability
    # property needs (write in one process, read in a fresh one). The
    # SEMANTIC surface — the cross-process poll rendezvous (S4r), the
    # ``grant list`` / sign-resolution flow (S4g), nonce-dedup — lives in the
    # shards that consume this store. This module does NOT interpret the
    # GrantMomentRequest wire format; it stores the canonical-JSON verbatim.

    async def put_pending_grant(
        self,
        *,
        request_id: str,
        session_id: str,
        request_json: str,
        ttl_expires_at: str,
    ) -> None:
        """Durably enqueue a pending Grant Moment row (state=pending, version=1).

        The durable form of ``runtime.py:403``'s in-memory ``_inflight`` entry.
        Re-putting the same ``request_id`` overwrites and bumps ``version`` (so
        a re-issue is observable to a poller) but keeps ``created_at``.
        ``request_json`` MUST be the caller's canonical-JSON GrantMomentRequest;
        S4s validates it is a JSON object (fail-loud on a malformed blob) but
        does NOT interpret its fields.
        """
        self._require_open()
        _validate_session_id(request_id, field="request_id")
        _validate_session_id(session_id, field="session_id")
        _require_json_object(request_json, field="request_json")
        now = _now_iso()
        await asyncio.to_thread(
            self._sync_put_pending_grant, request_id, session_id, request_json, ttl_expires_at, now
        )

    def _sync_put_pending_grant(
        self,
        request_id: str,
        session_id: str,
        request_json: str,
        ttl_expires_at: str,
        now: str,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO pending_grant
                    (request_id, principal_id, session_id, state, request_json,
                     resolution_json, version, ttl_expires_at, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, NULL, 1, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    state='pending',
                    request_json=excluded.request_json,
                    resolution_json=NULL,
                    version=pending_grant.version + 1,
                    ttl_expires_at=excluded.ttl_expires_at,
                    updated_at=excluded.updated_at
                """,
                (
                    request_id,
                    self._principal_id,
                    session_id,
                    request_json,
                    ttl_expires_at,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_pending_grant(self, request_id: str) -> PendingGrantRow | None:
        """Read one pending-grant row by ``request_id``, or None if absent.

        The cross-process durability read-back: a fresh process opening the same
        store sees the row a prior process wrote. Returns the ``version`` S4r's
        poll re-checks. Does NOT raise on absence.
        """
        self._require_open()
        _validate_session_id(request_id, field="request_id")
        row = await asyncio.to_thread(self._sync_get_pending_grant, request_id)
        if row is None:
            return None
        return PendingGrantRow(
            request_id=row["request_id"],
            state=row["state"],
            request_json=row["request_json"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            resolution_json=row["resolution_json"],
            resolution_sig=row["resolution_sig"],
        )

    def _sync_get_pending_grant(self, request_id: str) -> sqlite3.Row | None:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT request_id, state, request_json, resolution_json, "
                "resolution_sig, version, created_at, updated_at "
                "FROM pending_grant WHERE request_id = ?",
                (request_id,),
            )
            row: sqlite3.Row | None = cur.fetchone()
            return row
        finally:
            conn.close()

    async def resolve_pending_grant(
        self,
        *,
        request_id: str,
        resolution_json: str,
        state: str = "resolved",
    ) -> int:
        """Durably write a resolution onto a pending row and bump ``version``.

        This is the cross-process rendezvous WRITE half (S4r): process B
        (the answering CLI invocation) calls this to flip a ``pending`` row to
        ``state=resolved`` (or ``expired``), persisting ``resolution_json`` and
        incrementing the monotonic ``version`` so process A's poll observes a
        strictly-newer value (the lost-update guard). Returns the new
        ``version`` after the bump.

        ``state`` MUST be ``resolved`` or ``expired`` (a writer never reverts a
        row to ``pending`` via this path — that is the issue path's job). The
        target row MUST exist and be in ``state=pending``; resolving an absent
        or already-terminal row raises ``KeyError`` so a double-resolve / lost
        row surfaces loudly rather than silently no-op'ing (the cross-process
        equivalent of the in-process ``decision_future.done()`` guard).

        ``resolution_json`` MUST be a parseable JSON object (fail-loud at the
        write boundary, same discipline as ``request_json`` — S4r writes the
        canonical-JSON resolution wire form; S4s stores it verbatim).
        """
        self._require_open()
        _validate_session_id(request_id, field="request_id")
        if state not in ("resolved", "expired"):
            raise ValueError(
                f"resolve_pending_grant state must be 'resolved' or 'expired' (got {state!r})"
            )
        _require_json_object(resolution_json, field="resolution_json")
        # Authenticate the resolution at the write boundary (S4r): the answering
        # process signs the request_id-bound canonical payload with the session
        # signing key, so the requesting process's poll can REFUSE a row that
        # was not produced by a session-key holder (forge / tamper / replay
        # defense — verified in SessionRouter.verify_resolution_signature). A
        # session row can only be resolved by a process that opened the same
        # keystore-backed session key; a direct sqlite write is rejected on read.
        if self._key_manager is None:
            raise RuntimeError(
                "resolve_pending_grant requires the session signing key; call open() first"
            )
        resolution_sig = self._key_manager.sign_with_key(
            SESSION_SIGNING_KEY_ID,
            resolution_signing_payload(request_id, resolution_json),
        )
        now = _now_iso()
        new_version = await asyncio.to_thread(
            self._sync_resolve_pending_grant,
            request_id,
            resolution_json,
            resolution_sig,
            state,
            now,
        )
        return new_version

    def _sync_resolve_pending_grant(
        self,
        request_id: str,
        resolution_json: str,
        resolution_sig: str,
        state: str,
        now: str,
    ) -> int:
        conn = self._connect()
        try:
            # Single atomic UPDATE gated on state='pending': the WHERE clause is
            # the cross-process compare-and-set. Two writers racing the same row
            # leave exactly one with rowcount=1 (it flipped pending→terminal);
            # the loser sees rowcount=0 and raises below — no lost write, no
            # silent double-resolve. ``resolution_sig`` lands atomically with
            # ``resolution_json`` so a resolved row never carries a payload
            # without its authenticating signature.
            cur = conn.execute(
                """
                UPDATE pending_grant
                   SET state=?, resolution_json=?, resolution_sig=?,
                       version=version + 1, updated_at=?
                 WHERE request_id=? AND state='pending'
                """,
                (state, resolution_json, resolution_sig, now, request_id),
            )
            if cur.rowcount != 1:
                conn.rollback()
                # Distinguish absent from already-terminal for a clearer error.
                probe = conn.execute(
                    "SELECT state FROM pending_grant WHERE request_id=?",
                    (request_id,),
                ).fetchone()
                if probe is None:
                    raise KeyError(
                        f"resolve_pending_grant: request_id {request_id!r} is not in the "
                        "pending-grant store — it never issued, or the row was reaped"
                    )
                raise KeyError(
                    f"resolve_pending_grant: request_id {request_id!r} is already in "
                    f"state={probe['state']!r}, not 'pending' — refusing to re-resolve "
                    "(cross-process double-resolve / lost-update guard)"
                )
            new_version_row = conn.execute(
                "SELECT version FROM pending_grant WHERE request_id=?",
                (request_id,),
            ).fetchone()
            conn.commit()
            return int(new_version_row["version"])
        finally:
            conn.close()

    async def verify_resolution_signature(
        self,
        *,
        request_id: str,
        resolution_json: str,
        resolution_sig: str | None,
    ) -> bool:
        """Fail-closed authenticity check for a cross-process resolution row (S4r).

        Verifies the detached Ed25519 ``resolution_sig`` over the
        ``request_id``-bound canonical payload against the session signing key's
        public key. Returns ``False`` on a missing signature, an unopened key
        manager, OR a signature that does not verify — the caller (the requesting
        process's poll in ``GrantMomentRuntime._poll_store_for_resolution``)
        REFUSES the resolution on ``False`` rather than executing a row it cannot
        attribute to a session-key holder. This rejects a resolution written by
        direct sqlite tampering or by a process lacking the keystore-backed
        session key, and the ``request_id`` binding rejects a signature captured
        for a different pending row. Cross-PRINCIPAL co-signature verification (a
        distinct answerer key) remains Phase-03 scope.
        """
        self._require_open()
        if not resolution_sig or self._key_manager is None:
            return False
        public_key = self._key_manager.get_public_key(SESSION_SIGNING_KEY_ID)
        if not public_key:
            return False
        try:
            return await self._key_manager.verify(
                resolution_signing_payload(request_id, resolution_json),
                resolution_sig,
                public_key,
            )
        except Exception:
            # A malformed / wrong-length / non-decodable signature is exactly the
            # forge case this gate exists to reject — the key manager RAISES on
            # garbage signature bytes rather than returning False. Fail closed:
            # any verification error is treated as NOT authentic, so the caller
            # refuses the row. This is a definitive security refusal, not
            # error-hiding (the resolution is rejected, never executed).
            logger.debug(
                "session.resolution_signature_verify_failed",
                extra={"request_id": request_id},
            )
            return False

    async def count_pending_grants(self) -> int:
        """Count rows still in ``state=pending`` for this principal.

        The primitive S4g's queue back-pressure check (BackPressureQueueFullError)
        reads to bound queue growth. S4s exposes the count; S4g enforces the
        ceiling.
        """
        self._require_open()
        return await asyncio.to_thread(self._sync_count_pending_grants)

    def _sync_count_pending_grants(self) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT COUNT(*) AS n FROM pending_grant "
                "WHERE principal_id = ? AND state = 'pending'",
                (self._principal_id,),
            )
            row = cur.fetchone()
            return int(row["n"]) if row is not None else 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Region 2 — SessionObservedState (raw snapshot surface)
    # ------------------------------------------------------------------
    #
    # S4s ships the durable snapshot home; S5o owns the fingerprint /
    # first-time-action gate / goal-reconfirmation semantics that derive the
    # blob. This module stores + returns the canonical-JSON verbatim so the
    # "snapshot at every Ledger append" crash-safety property
    # (session-state.md:182) has a place to land.

    async def snapshot_observed_state(self, *, session_id: str, state_json: str) -> None:
        """Durably snapshot a SessionObservedState blob for ``session_id``.

        Upsert: re-snapshotting the same session_id overwrites and bumps
        ``version`` (so a reader can detect a newer snapshot). ``state_json``
        MUST be a canonical-JSON object (fail-loud on a malformed blob). The
        snapshot is the crash-safety primitive specs/session-state.md § Persistence
        promises; S5o calls this at every Ledger append.
        """
        self._require_open()
        _validate_session_id(session_id, field="session_id")
        _require_json_object(state_json, field="state_json")
        now = _now_iso()
        await asyncio.to_thread(self._sync_snapshot_observed_state, session_id, state_json, now)

    def _sync_snapshot_observed_state(self, session_id: str, state_json: str, now: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO session_observed_state
                    (session_id, principal_id, state_json, version, updated_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    principal_id=excluded.principal_id,
                    state_json=excluded.state_json,
                    version=session_observed_state.version + 1,
                    updated_at=excluded.updated_at
                """,
                (session_id, self._principal_id, state_json, now),
            )
            conn.commit()
        finally:
            conn.close()

    async def load_observed_state(self, session_id: str) -> str | None:
        """Return the durable SessionObservedState blob for ``session_id``, or
        None if no snapshot exists.

        The cross-process re-hydration read-back: a fresh process opening the
        same store re-loads the snapshot a prior process took. Does NOT raise on
        absence (a fresh session has no snapshot yet).
        """
        self._require_open()
        _validate_session_id(session_id, field="session_id")
        row = await asyncio.to_thread(self._sync_load_observed_state, session_id)
        if row is None:
            return None
        return str(row["state_json"])

    def _sync_load_observed_state(self, session_id: str) -> sqlite3.Row | None:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT state_json FROM session_observed_state WHERE session_id = ?",
                (session_id,),
            )
            row: sqlite3.Row | None = cur.fetchone()
            return row
        finally:
            conn.close()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _require_json_object(blob: str, *, field: str) -> None:
    """Fail-loud if ``blob`` is not a parseable JSON object.

    S4s stores the GrantMomentRequest / SessionObservedState wire forms verbatim
    (it does NOT interpret their fields — that is S4g / S5o), but it MUST reject
    a structurally-invalid blob at the write boundary so a malformed snapshot
    never lands silently. Same boundary-validation discipline as the trust
    store's identifier guards; a corrupt blob is a programming error, not data.
    """
    try:
        parsed = json.loads(blob)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field} must be a JSON object (got {type(parsed).__name__})")


__all__ = [
    "PENDING_GRANT_STATES",
    "SESSION_SIGNING_KEY_ID",
    "PendingGrantRow",
    "SessionRouter",
    "session_db_path",
]
