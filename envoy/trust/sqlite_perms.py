# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.trust.sqlite_perms — owner-only permissions for SQLite-family files.

A SQLite database opened in WAL mode (every envoy trust-plane / ledger store)
is not one file but up to three: the main ``<name>.db`` plus ``<name>.db-wal``
(the write-ahead log) and ``<name>.db-shm`` (the shared-memory index). Newly
committed rows live in the ``-wal`` file until a checkpoint folds them into the
main DB, so applying ``0o600`` to only the main file leaves freshly-written
records readable from a world-readable ``-wal`` by any local user. This helper
applies ``0o600`` to the whole family.

Per ``rules/trust-plane-security.md`` MUST Rule 6 (SQLite file permissions,
including WAL/SHM). Best-effort on filesystems without ``chmod`` (e.g. Windows):
logs at WARNING rather than failing the caller, consistent with
``envoy.trust.vault``'s post-write chmod idiom.

Call AFTER the store has run its first write (in WAL mode the first write is
what materializes ``-wal``/``-shm``). A connection-pool-backed store (e.g. the
durable ledger's ``SqliteAuditStore``) keeps those files for the whole process
lifetime, so a single post-init call covers the exposure window.

NOTE (tracked follow-up): the three ``TrustStoreAdapter`` sibling stores
(``.chain.db`` / ``.bc.db`` / ``.digest.db``) open a *fresh connection per
operation*, so their ``-wal``/``-shm`` exist only transiently during a write
and are checkpointed away on connection close — a much narrower window than the
pool-backed ledger. Retrofitting them to call this helper after each write is a
separate trust-store-workstream change (multiple write sites across
``envoy/trust/store.py``); see the EC-4/EC-9 ledger PR body for the tracking
note.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

# 0o600 — owner read/write only.
_OWNER_RW = stat.S_IRUSR | stat.S_IWUSR
_WAL_FAMILY_SUFFIXES = ("", "-wal", "-shm")


def chmod_sqlite_family(
    db_path: Path | str,
    *,
    log_event: str = "sqlite_perms.chmod_failed",
) -> None:
    """Set ``0o600`` on a SQLite DB and its existing ``-wal`` / ``-shm`` siblings.

    Idempotent. Siblings that do not exist yet are skipped — call after the
    store's first write so the WAL family is present. A ``chmod`` failure
    (Windows / FS-without-chmod) is logged at WARNING under ``log_event`` and
    does not raise: never silently leave a governance file world-readable
    without a trace, but never fail the caller on a platform that cannot chmod.
    """
    base = Path(db_path)
    for suffix in _WAL_FAMILY_SUFFIXES:
        target = base if suffix == "" else base.with_name(base.name + suffix)
        if not target.exists():
            continue
        try:
            os.chmod(target, _OWNER_RW)
        except OSError:
            logger.warning(log_event, extra={"path": str(target)})


__all__ = ["chmod_sqlite_family"]
