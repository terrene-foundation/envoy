# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: the `envoy grant` answer-in-a-later-command CLI surface (WS-6 S4g-1).

`envoy grant` is the human-answering half of the cross-process Grant Moment
flow: Envoy issues a Grant Moment in one process (writes a ``state=pending`` row
to the durable S4s sub-store), and the user answers it in a SEPARATE `envoy
grant approve/deny` invocation. This suite proves:

1. **`SessionRouter.list_pending_grants`** — the read surface `grant list`
   consumes: a FRESH router over the same on-disk vault sees the pending rows a
   prior (requesting) process wrote, newest-first, excluding resolved/expired.

2. **`grant list` / `approve` / `deny` CLI** — against a real file-backed store
   with the headless `ENVOY_KEYRING=memory` seam (journal/0017 Pattern 1): list
   renders pending requests with their answer commands; approve/deny flip the
   durable row to ``resolved`` carrying the correct ResolutionShape; an
   unknown / already-answered request is REFUSED loudly (exit 40), never a
   silent re-flip (the store's ``state='pending'`` compare-and-set guard).

3. **Cross-process resume through the CLI's answer helper** — a resolution
   written by ``grant``'s ``_answer_pending_grant`` (sharing the session key, as
   a shared OS keychain provides in production) is picked up by the requesting
   runtime's S4r poll, verified fail-closed, and resumes with the EXACT shape.

Per `rules/testing.md` Tier 2: real file-backed SQLite ``SessionRouter`` (NOT
``:memory:``), real Ed25519 session keys via a dict keyring backend (no
OS-keychain touch, no mocking of the store). The pending rows are written by the
REAL grant-moment runtime issue path (`make_runtime` + `issue_grant_moment`), so
``request_json`` is exactly the production wire form the CLI reads.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from pathlib import Path
from typing import TypeVar

import keyring.errors
import pytest
from click.testing import CliRunner

from envoy.cli.grant import _answer_pending_grant
from envoy.cli.main import cli
from envoy.grant_moment import (
    ApproveResolution,
    DeclineResolution,
    GrantMomentState,
    resolution_from_json,
    resolution_to_json,
)
from envoy.runtime import SessionRouter
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_issue_kwargs,
    make_runtime,
)

T = TypeVar("T")


class _MemBackend:
    """Pure-dict keyring backend standing in for the OS keychain.

    A SHARED instance models the production invariant that two processes open
    the SAME on-disk OS keychain and recover the SAME session signing key — the
    precondition the cross-process resolution signature verifies against.
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


def _sync(coro: Awaitable[T]) -> T:
    """Run a coroutine to completion from a sync test (CliRunner is sync, and the
    grant CLI calls ``asyncio.run`` internally — so the test body MUST NOT itself
    be inside a running loop)."""
    return asyncio.run(coro)  # type: ignore[arg-type]


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "alice.vault"


@pytest.fixture
def backend() -> _MemBackend:
    return _MemBackend()


async def _open_router(vault_path: Path, backend: _MemBackend) -> SessionRouter:
    router = SessionRouter(
        vault_path=vault_path, principal_id=DEFAULT_PRINCIPAL_ID, keyring_backend=backend
    )
    await router.open()
    return router


async def _issue_n_pending(
    vault_path: Path, backend: _MemBackend, n: int
) -> list[str]:
    """Issue ``n`` real Grant Moments into the on-disk store; return request_ids
    in issue order. Uses the real runtime so ``request_json`` is the production
    wire form (`tool_name`, `principal_genesis_id`, `why_asking`, …)."""
    router = await _open_router(vault_path, backend)
    try:
        runtime, *_ = await make_runtime(session_router=router, default_timeout_seconds=600)
        ids: list[str] = []
        for _ in range(n):
            req = await runtime.issue_grant_moment(**make_issue_kwargs())
            assert runtime.current_state(req.request_id) == GrantMomentState.M2_AWAIT
            ids.append(req.request_id)
        return ids
    finally:
        await router.close()


def _cli_env(vault_path: Path) -> dict[str, str]:
    return {
        "ENVOY_KEYRING": "memory",
        "ENVOY_VAULT_PATH": str(vault_path),
        "ENVOY_PRINCIPAL_ID": DEFAULT_PRINCIPAL_ID,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 1. SessionRouter.list_pending_grants — the read surface grant list consumes
# ──────────────────────────────────────────────────────────────────────────────


class TestListPendingGrantsStoreMethod:
    # Sync tests using `asyncio.run` (via `_sync`) — the whole file stays
    # all-sync, matching the proven-clean `test_ledger_cli_export.py` pattern.
    # Mixing `@pytest.mark.asyncio` tests with the sync CliRunner tests below in
    # one session leaks the pytest-asyncio loop's self-pipe socketpair at GC
    # (surfaces as an unraisable ResourceWarning attributed to a later test).

    def test_lists_only_pending_rows_for_principal(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        """list_pending_grants returns the pending rows a prior process wrote and
        EXCLUDES a row that was resolved — a fresh router (cross-process model)
        sees the durable tail."""
        ids = _sync(_issue_n_pending(vault_path, backend, 3))

        async def _body() -> set[str]:
            # Resolve ONE of them — it must drop out of the pending listing.
            writer = await _open_router(vault_path, backend)
            try:
                await writer.resolve_pending_grant(
                    request_id=ids[0],
                    resolution_json=resolution_to_json(
                        ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
                    ),
                    state="resolved",
                )
            finally:
                await writer.close()

            reader = await _open_router(vault_path, backend)
            try:
                rows = await reader.list_pending_grants()
            finally:
                await reader.close()
            assert all(r.state == "pending" for r in rows)
            return {r.request_id for r in rows}

        listed = _sync(_body())
        assert ids[0] not in listed, "a resolved grant must not appear in the pending listing"
        assert {ids[1], ids[2]} <= listed

    def test_empty_store_lists_nothing(self, vault_path: Path, backend: _MemBackend) -> None:
        async def _body() -> list:
            router = await _open_router(vault_path, backend)
            try:
                return await router.list_pending_grants()
            finally:
                await router.close()

        assert _sync(_body()) == []


# ──────────────────────────────────────────────────────────────────────────────
# 2. The grant CLI surface (list / approve / deny) via CliRunner
# ──────────────────────────────────────────────────────────────────────────────


class TestGrantCliList:
    def test_list_empty_exits_clean(self, vault_path: Path) -> None:
        result = CliRunner().invoke(cli, ["grant", "list"], env=_cli_env(vault_path))
        assert result.exit_code == 0, result.output
        assert "Nothing is waiting" in result.output

    def test_list_renders_pending_with_answer_commands(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        ids = _sync(_issue_n_pending(vault_path, backend, 2))
        result = CliRunner().invoke(cli, ["grant", "list"], env=_cli_env(vault_path))
        assert result.exit_code == 0, result.output
        assert "2 request(s) waiting" in result.output
        for rid in ids:
            assert rid in result.output
            assert f"envoy grant approve {rid}" in result.output
            assert f"envoy grant deny {rid}" in result.output
        # The real wire form's tool_name is rendered (make_issue_kwargs default).
        assert "send_email" in result.output


class TestGrantCliApproveDeny:
    def test_approve_flips_row_to_resolved_with_approve_shape(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        [rid] = _sync(_issue_n_pending(vault_path, backend, 1))
        result = CliRunner().invoke(cli, ["grant", "approve", rid], env=_cli_env(vault_path))
        assert result.exit_code == 0, result.output
        assert "Recorded your decision" in result.output

        async def _readback() -> None:
            r = await _open_router(vault_path, backend)
            try:
                row = await r.get_pending_grant(rid)
                assert row is not None and row.state == "resolved"
                assert row.resolution_json is not None
                assert isinstance(resolution_from_json(row.resolution_json), ApproveResolution)
                # The store signed the resolution at write — the cross-process
                # authenticity anchor is present (not NULL).
                assert row.resolution_sig is not None
            finally:
                await r.close()

        _sync(_readback())

    def test_deny_flips_row_to_resolved_with_decline_shape_and_reason(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        [rid] = _sync(_issue_n_pending(vault_path, backend, 1))
        result = CliRunner().invoke(
            cli, ["grant", "deny", rid, "--reason", "not now"], env=_cli_env(vault_path)
        )
        assert result.exit_code == 0, result.output

        async def _readback() -> None:
            r = await _open_router(vault_path, backend)
            try:
                row = await r.get_pending_grant(rid)
                assert row is not None and row.state == "resolved"
                assert row.resolution_json is not None
                shape = resolution_from_json(row.resolution_json)
                assert isinstance(shape, DeclineResolution)
                assert shape.reason == "not now"
            finally:
                await r.close()

        _sync(_readback())

    def test_approve_unknown_request_id_refused_exit_40(self, vault_path: Path) -> None:
        result = CliRunner().invoke(
            cli, ["grant", "approve", "gm-does-not-exist"], env=_cli_env(vault_path)
        )
        assert result.exit_code == 40, result.output
        assert "No request with id" in result.output

    def test_approve_already_resolved_refused_exit_40(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        """The cross-process double-resolve guard: a second answer on an
        already-resolved request is REFUSED (exit 40), the settled decision is
        immutable — never a silent re-flip."""
        [rid] = _sync(_issue_n_pending(vault_path, backend, 1))

        async def _pre_resolve() -> None:
            r = await _open_router(vault_path, backend)
            try:
                await r.resolve_pending_grant(
                    request_id=rid,
                    resolution_json=resolution_to_json(
                        DeclineResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
                    ),
                    state="resolved",
                )
            finally:
                await r.close()

        _sync(_pre_resolve())

        result = CliRunner().invoke(cli, ["grant", "approve", rid], env=_cli_env(vault_path))
        assert result.exit_code == 40, result.output
        assert "already resolved" in result.output

        # The pre-existing Decline is still the terminal — the refused approve
        # did NOT flip it to an Approve.
        async def _readback() -> None:
            r = await _open_router(vault_path, backend)
            try:
                row = await r.get_pending_grant(rid)
                assert row is not None and row.state == "resolved"
                assert row.resolution_json is not None
                assert isinstance(resolution_from_json(row.resolution_json), DeclineResolution)
            finally:
                await r.close()

        _sync(_readback())


class TestGrantCliKeyringAndPrincipalGuards:
    def test_bad_keyring_selector_exits_32(self, vault_path: Path) -> None:
        env = _cli_env(vault_path)
        env["ENVOY_KEYRING"] = "not-a-backend"
        result = CliRunner().invoke(cli, ["grant", "list"], env=env)
        assert result.exit_code == 32, result.output
        assert "not a recognized keyring selector" in result.output

    def test_missing_principal_exits_nonzero_with_actionable_message(
        self, vault_path: Path
    ) -> None:
        env = _cli_env(vault_path)
        del env["ENVOY_PRINCIPAL_ID"]
        result = CliRunner().invoke(cli, ["grant", "list"], env=env)
        assert result.exit_code != 0
        assert "no principal" in result.output


# ──────────────────────────────────────────────────────────────────────────────
# 3. Cross-process resume — the CLI answer helper produces a verifiable signature
# ──────────────────────────────────────────────────────────────────────────────


class TestCliAnswerResumesRequester:
    def test_answer_helper_resolution_resumes_polling_requester(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        """A resolution written by grant's `_answer_pending_grant` (process B,
        sharing the session key) is picked up by the requesting runtime's S4r
        poll, passes the fail-closed signature verify, and resumes with the EXACT
        ApproveResolution shape — the end-to-end cross-process answer path."""

        async def _body() -> None:
            router_a = await _open_router(vault_path, backend)
            try:
                runtime, *_ = await make_runtime(
                    session_router=router_a, default_timeout_seconds=10
                )
                request = await runtime.issue_grant_moment(**make_issue_kwargs())

                # Process B answers via the CLI's core helper over a SEPARATE
                # router sharing the same on-disk vault + the same session key
                # (shared backend = shared OS keychain in production).
                router_b = await _open_router(vault_path, backend)
                try:
                    ok, message = await _answer_pending_grant(
                        router=router_b,
                        request_id=request.request_id,
                        build_resolution=lambda decided_by: ApproveResolution(
                            decided_by_principal_genesis_id=decided_by
                        ),
                    )
                finally:
                    await router_b.close()
                assert ok, message

                # Process A's poll resumes on the store-written, session-key-
                # signed resolution — verified fail-closed, reconstructed exactly.
                resolution = await runtime.await_decision(request.request_id, timeout_seconds=10)
                assert isinstance(resolution, ApproveResolution)
                assert runtime.current_state(request.request_id) == GrantMomentState.M3_SIGN
            finally:
                await router_a.close()

        _sync(_body())

    def test_answer_helper_refuses_unknown_request(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        async def _body() -> None:
            router = await _open_router(vault_path, backend)
            try:
                ok, message = await _answer_pending_grant(
                    router=router,
                    request_id="gm-nope",
                    build_resolution=lambda decided_by: ApproveResolution(
                        decided_by_principal_genesis_id=decided_by
                    ),
                )
                assert ok is False
                assert "No request with id" in message
            finally:
                await router.close()

        _sync(_body())
