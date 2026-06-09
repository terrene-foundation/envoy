# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: store-backed ``SessionRouter`` cross-process durable substrate (S4s).

Source: WS-6 S4s (store-only) — the persistent-session substrate root. Per
``rules/facade-manager-detection.md`` Rule 1 + ``rules/orphan-detection.md``
Rule 2, ``SessionRouter`` (a ``*Router`` manager-shape class) has a Tier-2
wiring test asserting an externally-observable effect: rows written by ONE
router instance survive to a FRESH instance opened over the SAME vault path —
the new-process model that makes ``grant`` / ``init`` / ``chat`` buildable.

Per ``rules/testing.md`` Tier 2 + § State Persistence Verification: real
file-backed SQLite (NOT ``:memory:``), real Ed25519 keychain key via the real
``load_or_create_ledger_key_manager`` persistence path. NO mocking — the
keychain backend is dependency-injected (a pure-dict backend, mirroring
``test_ledger_keystore_wiring.py``) so the test exercises the real persistence
path without touching the host's OS keychain. Every write is verified by a
read-back through a SEPARATE router instance (the fresh-process model).
"""

from __future__ import annotations

import json
import sqlite3
import stat
from collections.abc import AsyncGenerator
from pathlib import Path

import keyring.errors
import pytest

from envoy.runtime import (
    PENDING_GRANT_STATES,
    PendingGrantRow,
    SessionRouter,
    session_db_path,
)

PRINCIPAL = "alice@example.com"


class _MemBackend:
    """Pure-dict keyring backend shared across both 'process' instances.

    The SAME backend instance stands in for the OS keychain that persists across
    process restarts: process A generates the session signing key into it;
    process B (a fresh router) reloads the SAME key from it — exactly the
    cross-process keychain-key lifecycle invariant S4s exercises.
    """

    def __init__(self) -> None:
        self._d: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._d[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._d.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._d:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._d[key]


def _grant_request_json(request_id: str) -> str:
    """A minimal canonical-JSON GrantMomentRequest blob (S4s stores it verbatim;
    it does NOT interpret the wire format — that is S4g)."""
    return json.dumps(
        {"schema_version": "grant-moment/1.0", "request_id": request_id, "tool_name": "send"},
        sort_keys=True,
        separators=(",", ":"),
    )


def _observed_state_json(session_id: str) -> str:
    return json.dumps(
        {"schema_version": "session-state/1.0", "session_id": session_id, "tool_calls_made": {}},
        sort_keys=True,
        separators=(",", ":"),
    )


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "alice.vault"


@pytest.fixture
def backend() -> _MemBackend:
    """One keychain backend shared across both process instances in a test."""
    return _MemBackend()


async def _open_router(vault_path: Path, backend: _MemBackend) -> SessionRouter:
    router = SessionRouter(vault_path=vault_path, principal_id=PRINCIPAL, keyring_backend=backend)
    await router.open()
    return router


@pytest.fixture
async def router(vault_path: Path, backend: _MemBackend) -> AsyncGenerator[SessionRouter, None]:
    r = await _open_router(vault_path, backend)
    yield r
    await r.close()


class TestStoreLayout:
    """The store opens as a 0o600 vault-sibling SQLite file."""

    def test_session_db_path_is_vault_sibling(self, vault_path: Path) -> None:
        assert session_db_path(vault_path) == vault_path.parent / "alice.session.db"

    async def test_open_creates_sibling_db_file(
        self, router: SessionRouter, vault_path: Path
    ) -> None:
        db = session_db_path(vault_path)
        assert db.exists()
        # 0o600 per rules/trust-plane-security.md MUST Rule 6 (POSIX only).
        mode = stat.S_IMODE(db.stat().st_mode)
        assert mode == 0o600, f"session db should be 0o600, got {oct(mode)}"

    async def test_open_is_idempotent(self, router: SessionRouter) -> None:
        await router.open()  # second open is a no-op, must not raise
        await router.open()


class TestPendingGrantCrossProcess:
    """Region 1 — pending-grant sub-store survives a fresh-process re-open."""

    async def test_put_then_get_same_instance(self, router: SessionRouter) -> None:
        await router.put_pending_grant(
            request_id="req-1",
            session_id="sess-1",
            request_json=_grant_request_json("req-1"),
            ttl_expires_at="2099-01-01T00:00:00+00:00",
        )
        row = await router.get_pending_grant("req-1")
        assert row is not None
        assert isinstance(row, PendingGrantRow)
        assert row.state == "pending"
        assert row.version == 1
        assert json.loads(row.request_json)["request_id"] == "req-1"

    async def test_pending_grant_survives_fresh_process(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        """THE S4s durability property: write in process A, read in fresh B."""
        # Process A — write + close (drops the in-memory key, mirrors exit).
        router_a = await _open_router(vault_path, backend)
        await router_a.put_pending_grant(
            request_id="req-cross",
            session_id="sess-cross",
            request_json=_grant_request_json("req-cross"),
            ttl_expires_at="2099-01-01T00:00:00+00:00",
        )
        await router_a.close()

        # Process B — a brand-new router over the SAME vault path + SAME keychain
        # backend re-opens the SAME on-disk store and re-loads the SAME key.
        router_b = await _open_router(vault_path, backend)
        try:
            row = await router_b.get_pending_grant("req-cross")
            assert row is not None, "pending grant did not survive process restart"
            assert row.state == "pending"
            assert json.loads(row.request_json)["request_id"] == "req-cross"
        finally:
            await router_b.close()

    async def test_reput_bumps_version(self, router: SessionRouter) -> None:
        """The monotonic version S4r's poll re-checks increments on re-put."""
        for _ in range(3):
            await router.put_pending_grant(
                request_id="req-v",
                session_id="sess-v",
                request_json=_grant_request_json("req-v"),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
        row = await router.get_pending_grant("req-v")
        assert row is not None
        assert row.version == 3

    async def test_get_absent_returns_none(self, router: SessionRouter) -> None:
        assert await router.get_pending_grant("nope") is None

    async def test_count_pending_grants(self, router: SessionRouter) -> None:
        assert await router.count_pending_grants() == 0
        for i in range(4):
            await router.put_pending_grant(
                request_id=f"req-{i}",
                session_id="sess",
                request_json=_grant_request_json(f"req-{i}"),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
        assert await router.count_pending_grants() == 4


class TestObservedStateCrossProcess:
    """Region 2 — SessionObservedState snapshot survives a fresh-process re-open."""

    async def test_snapshot_then_load_same_instance(self, router: SessionRouter) -> None:
        await router.snapshot_observed_state(
            session_id="sess-os", state_json=_observed_state_json("sess-os")
        )
        loaded = await router.load_observed_state("sess-os")
        assert loaded is not None
        assert json.loads(loaded)["session_id"] == "sess-os"

    async def test_observed_state_survives_fresh_process(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        """Crash-safety property: a snapshot taken in one process re-hydrates in
        a fresh process (specs/session-state.md:182)."""
        router_a = await _open_router(vault_path, backend)
        await router_a.snapshot_observed_state(
            session_id="sess-durable", state_json=_observed_state_json("sess-durable")
        )
        await router_a.close()

        router_b = await _open_router(vault_path, backend)
        try:
            loaded = await router_b.load_observed_state("sess-durable")
            assert loaded is not None, "observed state did not survive process restart"
            assert json.loads(loaded)["session_id"] == "sess-durable"
        finally:
            await router_b.close()

    async def test_load_absent_returns_none(self, router: SessionRouter) -> None:
        assert await router.load_observed_state("fresh-session") is None


class TestBoundaryValidation:
    """The store is REAL — it fails loud on malformed input rather than storing
    silently (zero-tolerance Rule 2 / trust-plane-security MUST Rule 2)."""

    async def test_put_rejects_malformed_json(self, router: SessionRouter) -> None:
        with pytest.raises(ValueError, match="request_json"):
            await router.put_pending_grant(
                request_id="bad",
                session_id="sess",
                request_json="not json",
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )

    async def test_snapshot_rejects_non_object_json(self, router: SessionRouter) -> None:
        with pytest.raises(ValueError, match="state_json"):
            await router.snapshot_observed_state(session_id="sess", state_json="[1,2,3]")

    async def test_put_rejects_path_traversal_request_id(self, router: SessionRouter) -> None:
        with pytest.raises(ValueError, match="path"):
            await router.put_pending_grant(
                request_id="sub/../escape",
                session_id="sess",
                request_json=_grant_request_json("x"),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )

    def test_construct_rejects_empty_principal(self, vault_path: Path) -> None:
        with pytest.raises(ValueError, match="principal_id"):
            SessionRouter(vault_path=vault_path, principal_id="")

    async def test_use_before_open_raises(self, vault_path: Path, backend: _MemBackend) -> None:
        r = SessionRouter(vault_path=vault_path, principal_id=PRINCIPAL, keyring_backend=backend)
        with pytest.raises(RuntimeError, match="before open"):
            await r.get_pending_grant("x")


class TestStoreIsRealNotMock:
    """The store returns data from the real file-backed source — the state
    enum is enforced by a real SQLite CHECK constraint, not an in-memory dict."""

    async def test_state_check_constraint_is_real(
        self, router: SessionRouter, vault_path: Path
    ) -> None:
        # A direct write of an out-of-enum state must be rejected by the DB's
        # CHECK — proving the durable backing enforces PENDING_GRANT_STATES.
        assert frozenset({"pending", "resolved", "expired"}) == PENDING_GRANT_STATES
        conn = sqlite3.connect(str(session_db_path(vault_path)))
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO pending_grant (request_id, principal_id, session_id, "
                    "state, request_json, version, ttl_expires_at, created_at, updated_at) "
                    "VALUES ('x','p','s','bogus','{}',1,'t','t','t')"
                )
                conn.commit()
        finally:
            conn.close()
