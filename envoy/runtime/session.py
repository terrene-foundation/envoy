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
   tracking"). Stored keyed by ``session_id``.

Encryption-at-rest (S5o-enc): the payload columns — ``request_json`` /
``resolution_json`` (Region 1) and ``state_json`` (Region 2) — are AES-256-GCM
ciphertext on disk under a keychain-gated key (``SESSION_ENCRYPTION_KEY_ID`` via
``load_or_create_session_encryption_key``), NOT canonical-JSON plaintext. A
local-file read recovers only ciphertext; the key lives in the OS keychain, not
the file. The key is keychain-gated (NOT vault-passphrase-gated) so the
short-lived one-shot CLI processes (``grant approve`` in a fresh process) decrypt
with no typed passphrase, exactly as the Ed25519 ``resolution_sig`` signing key
is keychain-gated. Index/key columns (``request_id`` / ``session_id`` /
``principal_id`` / ``state`` / ``version`` / timestamps / ``ttl_expires_at``)
stay cleartext so lookups, the ``CHECK`` constraint, and the lost-update
``version`` re-check keep working. Encryption is transparent at the public API —
callers pass/receive plaintext canonical JSON; the ``resolution_sig`` is signed
over (and verified against) that plaintext, layered over encryption as
complementary defense-in-depth (tamper-evidence + confidentiality), not a swap.

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
import base64
import json
import logging
import math
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.grant_moment.resolution import resolution_signing_payload
from envoy.ledger.keystore import (
    load_or_create_ledger_key_manager,
    load_or_create_session_encryption_key,
)
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

# The AES-256 encryption key the SessionRouter re-opens per process to
# encrypt-at-rest the payload columns (S5o-enc). Namespaced DISTINCTLY from the
# signing key so encryption and signing never share key material in the keychain
# (key separation) and so the encryption key has its own rotation/destroy
# surface. Like the signing key, the value is a FIXED constant — changing it
# would orphan every encrypted-at-rest row.
SESSION_ENCRYPTION_KEY_ID = "envoy-session-encryption-key"

# On-disk ciphertext token format for the encrypted payload columns. A versioned
# prefix so a future format migration is detectable, followed by
# base64(nonce ‖ AES-256-GCM ciphertext ‖ tag). The prefix also makes the
# read path REFUSE a non-encrypted (legacy plaintext) value loudly rather than
# silently accepting it — no plaintext-acceptance downgrade (zero-tolerance Rule 3).
_ENC_PREFIX = "enc:v1:"
_ENC_NONCE_LEN = 12  # AES-256-GCM standard 96-bit nonce

# Surfaced in the read-back ``request_json`` of a row whose encrypted payload
# could not be decrypted, ONLY on the tolerant listing path (``grant list``).
# It is deliberately NOT valid JSON so the CLI's wire-format reader treats the
# row as malformed and renders a loud "inspect before approving" marker rather
# than silently displaying attacker-controlled or corrupt content. The strict
# read path (``get_pending_grant``, used by the security-critical poll) does NOT
# substitute this — it raises ``SessionStoreEncryptionError`` (fail-closed).
_UNDECRYPTABLE_PAYLOAD_SENTINEL = "<undecryptable: session-store payload did not verify>"


class SessionStoreEncryptionError(Exception):
    """A session-store payload column could not be encrypted/decrypted.

    Raised on: a payload-column read that is NOT in the ``enc:v1:`` format
    (legacy-plaintext row or tampered prefix — fail-loud, never silently treat
    raw bytes as plaintext), a base64-decode failure, or an AES-256-GCM tag
    verification failure (wrong key / tampered ciphertext / wrong AAD binding).
    All three are definitive security refusals: the row is rejected, never
    returned as if intact.
    """


class SessionStoreCorruptError(Exception):
    """A session-store row holds a structurally-invalid value a tamperer (or a
    bug) wrote around the validating writer.

    Raised on read when a numeric column that MUST be finite (the velocity-raise
    ratchet's wall-clock / monotonic timestamps) holds ``NaN`` / ``±inf``. The
    velocity table is cleartext operational metadata (no encryption/signature
    layer), so a direct-sqlite tamperer can poison these columns; an unguarded
    ``int(time.x() - NaN)`` would raise an OPAQUE ``ValueError`` / ``OverflowError``
    deep in the cooling-off gate. Surfacing a typed corruption error instead keeps
    the gate FAIL-CLOSED (no velocity raise is issued) AND actionable. Mirrors the
    ``math.isfinite()`` boundary-guard discipline (``rules/trust-plane-security.md``
    MUST Rule 3).
    """


def _enc_aad(*, table: str, key: str, column: str) -> bytes:
    """Additional-authenticated-data binding a ciphertext to (table, row-key,
    column). AES-256-GCM verifies the AAD on decrypt, so a ciphertext lifted from
    one column/row and pasted into another (same key, same row) fails the tag
    check — preventing intra-store ciphertext-shuffling. The AAD is NOT secret;
    it is reconstructed from the row's cleartext primary key on read."""
    return f"{table}:{key}:{column}".encode()


def _encrypt_payload(enc_key: bytes, plaintext: str, *, aad: bytes) -> str:
    """AES-256-GCM-encrypt ``plaintext`` under ``enc_key`` with a fresh random
    nonce, returning the ``enc:v1:`` token. The nonce is prepended to the
    ciphertext+tag and the whole is base64'd into the TEXT column."""
    nonce = secrets.token_bytes(_ENC_NONCE_LEN)
    ciphertext = AESGCM(enc_key).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return _ENC_PREFIX + base64.b64encode(nonce + ciphertext).decode("ascii")


def _decrypt_payload(enc_key: bytes, token: str, *, aad: bytes) -> str:
    """Decrypt an ``enc:v1:`` token produced by :func:`_encrypt_payload`.

    Fail-loud (``SessionStoreEncryptionError``) on a missing/wrong prefix, a
    base64-decode failure, a too-short token, OR an AES-256-GCM tag failure
    (wrong key, tampered ciphertext, or AAD mismatch). Never returns the raw
    bytes as plaintext on failure.
    """
    if not token.startswith(_ENC_PREFIX):
        raise SessionStoreEncryptionError(
            "session-store payload is not in the enc:v1: format — refusing to "
            "treat it as plaintext (legacy-plaintext row, or tampered prefix)"
        )
    try:
        raw = base64.b64decode(token[len(_ENC_PREFIX):], validate=True)
    except (ValueError, TypeError) as exc:
        raise SessionStoreEncryptionError(
            f"session-store payload base64 decode failed: {exc}"
        ) from exc
    if len(raw) <= _ENC_NONCE_LEN:
        raise SessionStoreEncryptionError(
            "session-store payload too short to contain a nonce + ciphertext"
        )
    nonce, ciphertext = raw[:_ENC_NONCE_LEN], raw[_ENC_NONCE_LEN:]
    try:
        return AESGCM(enc_key).decrypt(nonce, ciphertext, aad).decode("utf-8")
    except (InvalidTag, ValueError) as exc:
        raise SessionStoreEncryptionError(
            "session-store payload AES-256-GCM verification failed — wrong key, "
            "tampered ciphertext, or AAD mismatch (row rejected)"
        ) from exc


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


@dataclass(slots=True, frozen=True)
class VelocityRatchetRow:
    """The durable last-velocity-raise-approval record for one principal (S4g-2).

    ``last_approved_wallclock`` (``time.time()``) anchors the 24h cooling-off to
    calendar time and survives process restart. ``last_approved_monotonic``
    (``time.monotonic()``) + ``boot_id`` (the per-process uuid that captured it)
    let a same-boot check measure elapsed time IMMUNE to forward wall-clock skew:
    when ``boot_id`` matches the live process, the monotonic delta is
    authoritative; across a restart (``boot_id`` differs, monotonic resets) the
    check falls back to the wall-clock delta.
    """

    principal_id: str
    last_approved_wallclock: float
    last_approved_monotonic: float
    boot_id: str
    updated_at: str


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
        # AES-256 payload-column encryption key (S5o-enc). Held as a mutable
        # bytearray so close() can zeroize it (memory-residency hygiene, per
        # rules/trust-plane-security.md MUST NOT Rule 3), matching the vault's
        # master-key handling.
        self._enc_key: bytearray | None = None
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

    # Velocity-raise cooling-off ratchet (S4g-2). One row per principal recording
    # the last successful velocity-raise approval. Phase-01 kept this in an
    # in-memory dict that a process restart SILENTLY RESET (a restart bought a
    # free velocity raise — security-R1 HIGH-3); persisting it here closes that.
    # Each row carries BOTH a wall-clock timestamp (the 24h window is a calendar-
    # time user-facing claim, and survives restart) AND a monotonic baseline +
    # the per-process ``boot_id`` that captured it: within the SAME boot the
    # monotonic delta is authoritative and IMMUNE to forward wall-clock skew
    # (NTP catch-up / admin clock change), so the gate can no longer be shortened
    # by moving the clock forward. Columns are operational metadata (timestamps +
    # a boot uuid), NOT user content — cleartext, like the other index/key
    # columns (S5o-enc encrypts only the JSON payload columns).
    _CREATE_VELOCITY_RATCHET_SQL = """
    CREATE TABLE IF NOT EXISTS velocity_raise_ratchet (
        principal_id            TEXT PRIMARY KEY,
        last_approved_wallclock REAL NOT NULL,
        last_approved_monotonic REAL NOT NULL,
        boot_id                 TEXT NOT NULL,
        updated_at              TEXT NOT NULL
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
        # Payload-column encryption key (S5o-enc) — same keychain-gated, fail-loud
        # lifecycle as the signing key above. A fresh process recovers the SAME
        # key, so a row encrypted in process A decrypts in process B; a process
        # without keychain access cannot obtain it and so cannot decrypt the store.
        self._enc_key = bytearray(
            await load_or_create_session_encryption_key(
                principal_id=self._principal_id,
                key_id=SESSION_ENCRYPTION_KEY_ID,
                keyring_backend=self._keyring_backend,
            )
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
        # Zeroize the AES key bytes before releasing the reference (best-effort
        # residency minimization, matching TrustVault._zeroize on lock()).
        if self._enc_key is not None:
            for i in range(len(self._enc_key)):
                self._enc_key[i] = 0
            self._enc_key = None
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
            conn.execute(self._CREATE_VELOCITY_RATCHET_SQL)
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

    def _require_enc_key(self) -> bytes:
        """Return the AES-256 payload-encryption key bytes, or raise if the
        router was not opened (open() loads the key). Centralises the None-guard
        so every encrypt/decrypt site fails with one clear message rather than an
        opaque AttributeError on ``None`` (zero-tolerance Rule 3a).

        Residency caveat (honest): this returns an IMMUTABLE ``bytes`` copy, and
        ``AESGCM`` copies the key again into the OpenSSL context. Those copies
        cannot be zeroized (Python ``bytes`` are immutable; the OpenSSL copy is
        opaque), so ``close()``'s zeroize of the backing ``bytearray`` minimises
        but does NOT fully eliminate key residency — it matches the vault's
        best-effort master-key handling, not a hard guarantee. A heap-reading
        attacker (kernel/hypervisor memory compromise) is explicitly out of scope
        per ``specs/threat-model.md`` § Out of scope; the threat this key closes
        is local-FILE read, where the key never touches the file."""
        if self._enc_key is None:
            raise RuntimeError(
                "SessionRouter payload encryption key unavailable — call "
                "`await router.open()` to load the keychain encryption key first"
            )
        return bytes(self._enc_key)

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
        # Encrypt-at-rest (S5o-enc): the column stores ciphertext; the JSON-object
        # validation above ran on the plaintext. AAD binds the ciphertext to this
        # row + column so it cannot be shuffled into another row/column.
        enc_request = _encrypt_payload(
            self._require_enc_key(),
            request_json,
            aad=_enc_aad(table="pending_grant", key=request_id, column="request_json"),
        )
        now = _now_iso()
        await asyncio.to_thread(
            self._sync_put_pending_grant, request_id, session_id, enc_request, ttl_expires_at, now
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
        return self._row_to_pending_grant(row)

    def _row_to_pending_grant(
        self, row: sqlite3.Row, *, tolerate_corrupt: bool = False
    ) -> PendingGrantRow:
        """Build a read-back ``PendingGrantRow`` from a raw DB row, decrypting the
        encrypted-at-rest payload columns (``request_json`` always; ``resolution_json``
        when the row is resolved). Decryption is transparent at the store boundary
        — callers (S4r poll, ``grant list``) see plaintext canonical JSON, and the
        ``resolution_sig`` they verify was signed over that same plaintext.

        ``tolerate_corrupt`` selects the failure mode for an undecryptable payload:

        - ``False`` (default — the strict read path ``get_pending_grant`` consumes,
          which the security-critical poll drives): re-raise ``SessionStoreEncryptionError``
          so a forged / corrupt row fails CLOSED.
        - ``True`` (the ``grant list`` UI path): substitute
          ``_UNDECRYPTABLE_PAYLOAD_SENTINEL`` for the undecryptable payload so a
          single bad row is surfaced as malformed (the CLI renders a loud marker)
          WITHOUT aborting the whole listing. A read-only UI never executes a
          decision, so resilience-over-fail-closed is correct here; the security
          gate stays on the strict poll path.
        """
        enc_key = self._require_enc_key()
        request_id = row["request_id"]

        def _decrypt_col(value: str, column: str) -> str:
            try:
                return _decrypt_payload(
                    enc_key,
                    value,
                    aad=_enc_aad(table="pending_grant", key=request_id, column=column),
                )
            except SessionStoreEncryptionError:
                if tolerate_corrupt:
                    return _UNDECRYPTABLE_PAYLOAD_SENTINEL
                raise

        request_json = _decrypt_col(row["request_json"], "request_json")
        resolution_json = row["resolution_json"]
        if resolution_json is not None:
            resolution_json = _decrypt_col(resolution_json, "resolution_json")
        return PendingGrantRow(
            request_id=request_id,
            state=row["state"],
            request_json=request_json,
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            resolution_json=resolution_json,
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
        # Sign over the PLAINTEXT (above), THEN encrypt-at-rest (S5o-enc): the
        # signature anchors the plaintext a reader recovers after decrypt, so the
        # encryption layer is transparent to signature verification. The sig +
        # ciphertext land atomically in the single UPDATE below.
        enc_resolution = _encrypt_payload(
            self._require_enc_key(),
            resolution_json,
            aad=_enc_aad(table="pending_grant", key=request_id, column="resolution_json"),
        )
        now = _now_iso()
        new_version = await asyncio.to_thread(
            self._sync_resolve_pending_grant,
            request_id,
            enc_resolution,
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

    async def list_pending_grants(self) -> list[PendingGrantRow]:
        """List every row still in ``state=pending`` for this principal, newest first.

        The read surface ``envoy grant list`` (S4g) consumes: a SEPARATE CLI
        invocation opens a fresh router over the same on-disk vault and sees the
        pending rows a prior (requesting) process wrote via ``put_pending_grant``.
        Returns ``[]`` when nothing is pending. Uses the
        ``ix_pending_grant_principal_state (principal_id, state, updated_at)``
        index so the listing is an index scan, not a table scan. Resolved
        (``resolved`` / ``expired``) rows are excluded — only requests actually
        waiting for the user's decision are surfaced.

        Trust boundary: the displayed ``request_json`` is confidentiality-protected
        (encrypted-at-rest) but NOT authenticity-protected. The AAD binds a
        ciphertext to its (table, row, column) so it cannot be SHUFFLED within the
        store, but a writer who ALSO holds the encryption key (a co-resident
        process that read the keychain) can craft a valid ``request_json``
        ciphertext with arbitrary plaintext — only ``resolution_json`` is signed
        (``resolution_sig``). This listing is therefore ADVISORY: the actual
        decision is gated on the signed resolution verified on the strict poll path
        (``GrantMomentRuntime`` § Resolution authenticity), never on the displayed
        request. A caller MUST NOT treat a listed grant as authorized without that
        signed-resolution gate.
        """
        self._require_open()
        rows = await asyncio.to_thread(self._sync_list_pending_grants)
        # Tolerant build: a single undecryptable row is surfaced as malformed
        # (sentinel request_json → CLI marker) rather than aborting the whole
        # listing. The security gate is the strict poll path, not this UI read.
        return [self._row_to_pending_grant(row, tolerate_corrupt=True) for row in rows]

    def _sync_list_pending_grants(self) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT request_id, state, request_json, resolution_json, "
                "resolution_sig, version, created_at, updated_at "
                "FROM pending_grant WHERE principal_id = ? AND state = 'pending' "
                "ORDER BY updated_at DESC, request_id ASC",
                (self._principal_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()

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
        # Encrypt-at-rest (S5o-enc): AAD binds the ciphertext to this session row.
        enc_state = _encrypt_payload(
            self._require_enc_key(),
            state_json,
            aad=_enc_aad(table="session_observed_state", key=session_id, column="state_json"),
        )
        now = _now_iso()
        await asyncio.to_thread(self._sync_snapshot_observed_state, session_id, enc_state, now)

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
        # Decrypt-at-rest (S5o-enc): transparent to callers — S5o sees plaintext
        # canonical JSON, exactly as the pre-encryption store returned.
        return _decrypt_payload(
            self._require_enc_key(),
            str(row["state_json"]),
            aad=_enc_aad(table="session_observed_state", key=session_id, column="state_json"),
        )

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

    # ------------------------------------------------------------------
    # Velocity-raise cooling-off ratchet (S4g-2)
    # ------------------------------------------------------------------
    #
    # Durable replacement for the runtime's in-memory last-approved dict, which a
    # process restart silently reset. The runtime (``EnvoyGrantMomentRuntime``)
    # owns the SEMANTICS — when a velocity-raise approval fires, and how elapsed
    # time is compared against the 24h window (incl. the same-boot monotonic
    # skew-immunity). This store only persists + returns the raw record verbatim.

    async def record_velocity_approval(
        self,
        *,
        principal_id: str,
        wallclock: float,
        monotonic: float,
        boot_id: str,
    ) -> None:
        """Durably record (upsert) the principal's last velocity-raise approval.

        Called by the runtime only on a SUCCESSFUL Approve of a velocity-raise.
        ``wallclock`` = ``time.time()`` at approval, ``monotonic`` =
        ``time.monotonic()`` at the same instant, ``boot_id`` = the per-process
        uuid that captured them (so a later check knows whether the monotonic
        baseline is comparable). Overwrites any prior row for the principal — the
        ratchet tracks only the most-recent approval."""
        self._require_open()
        _validate_session_id(principal_id, field="principal_id")
        _validate_session_id(boot_id, field="boot_id")
        # Finiteness guard at the write boundary (defense-in-depth): never persist
        # a NaN/inf timestamp a later cooling-off check would choke on.
        if not math.isfinite(wallclock):
            raise ValueError(f"wallclock must be finite (got {wallclock!r})")
        if not math.isfinite(monotonic):
            raise ValueError(f"monotonic must be finite (got {monotonic!r})")
        now = _now_iso()
        await asyncio.to_thread(
            self._sync_record_velocity_approval, principal_id, wallclock, monotonic, boot_id, now
        )

    def _sync_record_velocity_approval(
        self,
        principal_id: str,
        wallclock: float,
        monotonic: float,
        boot_id: str,
        now: str,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO velocity_raise_ratchet
                    (principal_id, last_approved_wallclock, last_approved_monotonic,
                     boot_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(principal_id) DO UPDATE SET
                    last_approved_wallclock=excluded.last_approved_wallclock,
                    last_approved_monotonic=excluded.last_approved_monotonic,
                    boot_id=excluded.boot_id,
                    updated_at=excluded.updated_at
                """,
                (principal_id, wallclock, monotonic, boot_id, now),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_velocity_ratchet(self, principal_id: str) -> VelocityRatchetRow | None:
        """Return the principal's last velocity-raise approval record, or None if
        no velocity-raise has ever been approved (a fresh process opening the same
        store re-hydrates the persisted ratchet — the cross-restart durability
        that closes the in-memory-dict reset hole). Does NOT raise on absence."""
        self._require_open()
        _validate_session_id(principal_id, field="principal_id")
        row = await asyncio.to_thread(self._sync_get_velocity_ratchet, principal_id)
        if row is None:
            return None
        wallclock = row["last_approved_wallclock"]
        monotonic = row["last_approved_monotonic"]
        # Read-boundary finiteness guard (load-bearing): the velocity table is
        # cleartext, so a direct-sqlite tamperer can write NaN/inf here. Reject a
        # non-finite value as a corrupt/forged row — fail CLOSED with a typed
        # error (the cooling-off gate refuses to issue) rather than crashing the
        # gate with an opaque int(NaN)/int(inf) arithmetic error downstream.
        if not math.isfinite(wallclock) or not math.isfinite(monotonic):
            raise SessionStoreCorruptError(
                f"velocity_raise_ratchet row for principal {principal_id!r} has a "
                "non-finite timestamp (wallclock/monotonic) — corrupt or forged; "
                "refusing to compute the cooling-off window"
            )
        return VelocityRatchetRow(
            principal_id=row["principal_id"],
            last_approved_wallclock=wallclock,
            last_approved_monotonic=monotonic,
            boot_id=row["boot_id"],
            updated_at=row["updated_at"],
        )

    def _sync_get_velocity_ratchet(self, principal_id: str) -> sqlite3.Row | None:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT principal_id, last_approved_wallclock, last_approved_monotonic, "
                "boot_id, updated_at FROM velocity_raise_ratchet WHERE principal_id = ?",
                (principal_id,),
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
    "SESSION_ENCRYPTION_KEY_ID",
    "SESSION_SIGNING_KEY_ID",
    "PendingGrantRow",
    "SessionRouter",
    "SessionStoreCorruptError",
    "SessionStoreEncryptionError",
    "VelocityRatchetRow",
    "session_db_path",
]
