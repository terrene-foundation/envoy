# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for ``envoy.trust.sqlite_perms.chmod_sqlite_family``.

Security-relevant code under test: ``chmod_sqlite_family`` applies ``0o600`` to a
SQLite DB AND its WAL-mode ``-wal`` / ``-shm`` siblings, so freshly-written
governance rows are not left world-readable in the write-ahead-log file. It is
wired into the durable-ledger bootstrap (``envoy/ledger/bootstrap.py``). These
are its first behavioral tests — the helper previously had zero importing tests
(/redteam Round 1 TEST-01).

Per ``rules/trust-plane-security.md`` MUST Rule 6 (SQLite file permissions incl.
WAL/SHM). The ``0o600`` permission-bit assertions are POSIX-only; the failure
path (chmod refused → log, don't raise) is exercised on every platform.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import stat
import sys

import pytest

from envoy.trust.sqlite_perms import chmod_sqlite_family

_POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="chmod is best-effort on Windows; 0o600 permission bits are POSIX-only",
)


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.fixture
def wal_db(tmp_path):
    """A SQLite DB opened in WAL mode with a committed write.

    The ``-wal`` / ``-shm`` siblings exist for as long as a connection is held
    open (the realistic pool-backed-store scenario the helper targets), so the
    connection is kept open across the test body and closed in teardown.
    """
    path = tmp_path / "trust.db"
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('secret-governance-row')")
    conn.commit()
    yield path
    conn.close()


@_POSIX_ONLY
def test_chmod_applies_0o600_to_full_wal_family(wal_db):
    """Every existing file in the WAL family ends owner-rw-only after chmod."""
    family = {
        suffix: (wal_db.with_name(wal_db.name + suffix) if suffix else wal_db)
        for suffix in ("", "-wal", "-shm")
    }
    existing = {s: p for s, p in family.items() if p.exists()}
    # Confirm the WAL scenario is actually exercised: main + the -wal sibling.
    assert (
        "" in existing and "-wal" in existing
    ), f"WAL family not materialized; existing={sorted(existing)}"
    # Make them group/other-readable first so the chmod is observable.
    for p in existing.values():
        os.chmod(p, 0o644)

    chmod_sqlite_family(wal_db)

    for suffix, p in existing.items():
        assert _mode(p) == 0o600, f"{suffix or 'main'} ({p.name}) is {oct(_mode(p))}, not 0o600"


@_POSIX_ONLY
def test_chmod_is_idempotent(wal_db):
    """A second call neither raises nor relaxes the permissions."""
    chmod_sqlite_family(wal_db)
    chmod_sqlite_family(wal_db)
    assert _mode(wal_db) == 0o600


@_POSIX_ONLY
def test_chmod_skips_absent_siblings(tmp_path):
    """A DB with no WAL family chmods the main file and skips absent siblings."""
    path = tmp_path / "plain.db"
    path.touch()
    os.chmod(path, 0o644)

    chmod_sqlite_family(path)  # must not raise on absent -wal/-shm

    assert _mode(path) == 0o600
    assert not path.with_name(path.name + "-wal").exists()
    assert not path.with_name(path.name + "-shm").exists()


def test_chmod_failure_logs_warning_does_not_raise(tmp_path, monkeypatch, caplog):
    """A chmod that the filesystem refuses logs at WARNING but never raises.

    Platform-independent: ``os.chmod`` is monkeypatched to raise ``OSError`` so
    the Windows / no-chmod-filesystem branch is exercised everywhere.
    """
    path = tmp_path / "plain.db"
    path.touch()

    def _boom(*_a, **_k):
        raise OSError("filesystem does not support chmod")

    monkeypatch.setattr(os, "chmod", _boom)

    with caplog.at_level(logging.WARNING):
        chmod_sqlite_family(path, log_event="sqlite_perms.chmod_failed")

    # Did not raise (we got here), and the failure is on the WARN+ scan surface.
    assert any(
        r.msg == "sqlite_perms.chmod_failed" and r.levelno == logging.WARNING
        for r in caplog.records
    ), f"expected a WARNING under sqlite_perms.chmod_failed; got {[r.msg for r in caplog.records]}"
