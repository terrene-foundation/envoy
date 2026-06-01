# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.ledger.bootstrap — durable `EnvoyLedger` construction.

Phase-01 ledger backing was process-local (`InMemoryAuditStore`), lost on
process exit. EC-4 (`envoy ledger export`) + EC-9 (independent verifier)
require a ledger whose entries survive across processes: the digest /
grant-moment *writers* append in one process and the `envoy ledger export`
*reader* opens the same store in a later process. This module is the single
construction point both sides resolve through, so they always agree on the
on-disk file.

`open_durable_ledger` opens the kailash file-backed `SqliteAuditStore` over an
`AsyncSQLitePool`, runs idempotent schema init, constructs the `EnvoyLedger`,
and `rehydrate()`s its chain counters from any persisted tail (so a fresh
process *continues* the chain rather than forking it from genesis).

Scope boundary (T-01-13 / durable-key shard): the *signing key* durability —
so a fresh process's head + entry signatures verify against the persisted key
— and head rehydration land separately. This module is key-agnostic: the
caller injects the `key_manager`. A process-local `InMemoryKeyManager` is
sufficient for the append + query (digest read) path; cross-process
*export / verify_chain* needs the durable key the caller injects once it
exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from kailash.core.pool.sqlite_pool import AsyncSQLitePool, SQLitePoolConfig
from kailash.trust.audit_store import SqliteAuditStore

from envoy.ledger.facade import EnvoyLedger
from envoy.trust.sqlite_perms import chmod_sqlite_family

if TYPE_CHECKING:
    from envoy.ledger.facade import _KeyManagerProtocol

logger = logging.getLogger(__name__)

# ── Production durable-ledger identity ───────────────────────────────────────
# The (signing-key id, device id, algorithm identifier) triple every WRITER
# (the daily digest today; grant / boundary-conversation later) AND the
# `envoy ledger export` READER resolve through, so they all open the SAME
# per-principal durable ledger. A drift between writer and reader would
# silently open a different — or empty — ledger and break cross-process export
# (EC-4) with no error, which is exactly why these live in ONE place.
#
# The string VALUES are retained verbatim from the digest's original wiring so
# existing on-disk ledgers + their keychain key entries stay readable; only the
# home and the names are promoted here. Do NOT change the values — that would
# orphan every ledger already signed under the old key id.
LEDGER_SIGNING_KEY_ID = "envoy-digest-signing-key"
LEDGER_DEVICE_ID = "envoy-digest-device"
# Phase-01 3-key algorithm identifier (sig + hash + shamir) per
# specs/trust-lineage.md — the wire form every EnvoyLedger entry carries.
LEDGER_ALGORITHM_IDENTIFIER: dict[str, str] = {
    "sig": "ed25519",
    "hash": "sha256",
    "shamir": "slip39",
}


def audit_db_path(vault_path: Path | str) -> Path:
    """Resolve the durable ledger's SQLite file for a given vault path.

    The audit DB is a vault *sibling* file — `<stem>.audit.db` next to the
    vault — matching the `.chain.db` / `.posture.db` / `.bc.db` / `.digest.db`
    layout `envoy.trust.store.TrustStoreAdapter` already establishes. Writers
    (`envoy.daily_digest`, grant moments) and the `envoy ledger export` reader
    MUST resolve the path through here so they open the *same* file.
    """
    vp = Path(vault_path)
    return vp.parent / f"{vp.stem}.audit.db"


@dataclass(slots=True)
class DurableLedger:
    """A durable `EnvoyLedger` plus the resources whose lifetime it owns.

    The caller owns teardown: `await durable.aclose()` releases the SQLite
    connection pool — matching the caller-owns-lifecycle contract of
    `envoy.daily_digest.bootstrap.build_digest_service` /
    `envoy.trust.store.TrustStoreAdapter.close`.
    """

    ledger: EnvoyLedger
    _pool: AsyncSQLitePool
    _audit_store: SqliteAuditStore

    async def aclose(self) -> None:
        """Release the SQLite connection pool (caller responsibility)."""
        await self._pool.close()


async def open_durable_ledger(
    *,
    vault_path: Path | str,
    key_manager: _KeyManagerProtocol,
    signing_key_id: str,
    device_id: str,
    algorithm_identifier: dict[str, str],
    tenant_id: str | None = None,
) -> DurableLedger:
    """Construct a file-backed, chain-rehydrated `EnvoyLedger`.

    Steps: resolve the vault-sibling `.audit.db`; open + initialize the
    `AsyncSQLitePool`; initialize the `SqliteAuditStore` schema (idempotent
    `CREATE TABLE IF NOT EXISTS`); construct the `EnvoyLedger`; `rehydrate()`
    its chain counters from any persisted tail. The returned `DurableLedger`
    owns the pool lifetime — the caller MUST `await durable.aclose()`.
    """
    db_path = audit_db_path(vault_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    pool = AsyncSQLitePool(SQLitePoolConfig(db_path=str(db_path)))
    await pool.initialize()
    # Once the pool is live, any failure in the steps below (schema init, chmod,
    # the EnvoyLedger constructor's key/algorithm validation, or `rehydrate()`
    # past the scan cap) MUST release the pool here: on failure we never return a
    # `DurableLedger`, so the caller has no handle to `aclose()` and the SQLite
    # pool + its aiosqlite background thread would leak. Re-raise the original
    # error (fail-loud — cleanup never swallows it).
    try:
        store = SqliteAuditStore(pool)
        await store.initialize()

        # 0o600 on the audit DB *family* per rules/trust-plane-security.md MUST
        # Rule 6 — the ledger holds signed governance records; world-readable
        # would expose them to any local user. `store.initialize()` above ran
        # the first write (CREATE TABLE) which, in WAL mode, materializes
        # `<db>.audit.db-wal` + `-shm`; the pool keeps them for the process
        # lifetime, so committed rows live in `-wal` until checkpoint.
        # `chmod_sqlite_family` tightens the main file AND the WAL/SHM siblings
        # (chmod-the-main-file-only would leave a world-readable `-wal`).
        # FS-without-chmod (Windows) logs, does not fail.
        chmod_sqlite_family(db_path, log_event="ledger.durable.chmod_failed")

        ledger = EnvoyLedger(
            audit_store=store,
            key_manager=key_manager,
            signing_key_id=signing_key_id,
            device_id=device_id,
            algorithm_identifier=algorithm_identifier,
            tenant_id=tenant_id,
        )
        await ledger.rehydrate()
    except Exception:
        await pool.close()
        raise

    logger.info(
        "ledger.durable.opened",
        extra={"audit_db": str(db_path), "restored_sequence": ledger.current_sequence},
    )
    return DurableLedger(ledger=ledger, _pool=pool, _audit_store=store)


__all__ = [
    "LEDGER_ALGORITHM_IDENTIFIER",
    "LEDGER_DEVICE_ID",
    "LEDGER_SIGNING_KEY_ID",
    "DurableLedger",
    "audit_db_path",
    "open_durable_ledger",
]
