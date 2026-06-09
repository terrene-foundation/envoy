# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: cross-process Grant Moment decision rendezvous via store-poll (S4r).

Source: WS-6 S4r — the load-bearing rendezvous redesign. A
``decision_future: asyncio.Future`` cannot be ``set_result``-ed across two OS
processes, which is exactly the ``grant`` flow (request issued in one CLI
invocation, answered in another). This suite proves the store-poll-with-
monotonic-version-re-check rendezvous:

1. **Cross-process resume** — process A issues + polls; a SEPARATE
   ``SessionRouter`` instance (the fresh-process model, exactly as the S4s
   wiring test simulates a new process) writes the resolution to the sub-store;
   A's ``await_decision`` poll observes ``state=resolved`` and resumes. This is
   NOT a same-event-loop ``post_decision``/``set_result`` — the answer crosses a
   store boundary written by a different router.

2. **Monotonic-version lost-update guard** — a writer that bumps ``version``
   between issue and the first poll is still observed; a stale read
   (``version <= store_version_at_issue``) is NOT treated as a resolution.

3. **Timeout-audit-row byte-identity** — a poll-timeout drives the SAME
   ``next_state(.., TIMEOUT_EXPIRED)`` M2 → M3 transition and raises the SAME
   ``GrantMomentExpiredError`` (request_id + timeout_seconds) as the Phase-01
   ``asyncio.Future`` path, so the timeout audit trail is unchanged by the
   rendezvous rewrite (zero-tolerance Rule 1 — no behavioral regression).

Per ``rules/testing.md`` Tier 2: real file-backed SQLite ``SessionRouter`` (NOT
``:memory:``), real Ed25519 keychain key via a dependency-injected dict backend
(no OS-keychain touch, no mocking of the store). The store IS the real S4s
sub-store; the resolution is a real serialized ``ResolutionShape``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncGenerator
from pathlib import Path

import keyring.errors
import pytest

from envoy.grant_moment import (
    ApproveResolution,
    DeclineResolution,
    GrantMomentExpiredError,
    GrantMomentResolutionUnauthenticatedError,
    GrantMomentState,
    resolution_from_json,
    resolution_to_json,
)
from envoy.grant_moment.resolution import resolution_signing_payload
from envoy.runtime import SessionRouter
from envoy.runtime.session import SESSION_SIGNING_KEY_ID, session_db_path
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    _list_events,
    make_issue_kwargs,
    make_runtime,
)


class _MemBackend:
    """Pure-dict keyring backend standing in for the OS keychain.

    The SAME backend instance is shared across the 'two processes' (router A
    issuing + router B answering) so both reload the SAME session signing key —
    the cross-process keychain-key lifecycle, mirroring the S4s wiring test.
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


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "alice.vault"


@pytest.fixture
def backend() -> _MemBackend:
    return _MemBackend()


async def _open_router(vault_path: Path, backend: _MemBackend) -> SessionRouter:
    # principal_id must match DEFAULT_PRINCIPAL_ID so the runtime's pending-row
    # writes and the answering router's reads agree on the principal key shape.
    router = SessionRouter(
        vault_path=vault_path, principal_id=DEFAULT_PRINCIPAL_ID, keyring_backend=backend
    )
    await router.open()
    return router


@pytest.fixture
async def router_a(vault_path: Path, backend: _MemBackend) -> AsyncGenerator[SessionRouter, None]:
    """Process A's router (the requesting process — issues + polls)."""
    r = await _open_router(vault_path, backend)
    yield r
    await r.close()


@pytest.mark.asyncio
class TestCrossProcessResume:
    async def test_await_decision_resumes_from_store_written_resolution(
        self, vault_path: Path, backend: _MemBackend, router_a: SessionRouter
    ) -> None:
        """Process A issues + polls; a SEPARATE router (process B) writes the
        resolution to the sub-store; A's poll resumes on the store-written row.

        NOT a same-event-loop set_result — the answer is written by a distinct
        SessionRouter instance opened over the same on-disk vault (the
        fresh-process model). This is the S4r acceptance gate.
        """
        runtime, *_ = await make_runtime(session_router=router_a, default_timeout_seconds=10)
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        assert runtime.current_state(request.request_id) == GrantMomentState.M2_AWAIT

        # The pending row is durably visible to a SEPARATE process (router_b)
        # opened over the SAME vault — the cross-process precondition.
        router_b = await _open_router(vault_path, backend)
        try:
            row = await router_b.get_pending_grant(request.request_id)
            assert row is not None and row.state == "pending"

            # Process B writes the resolution directly into the sub-store. This
            # is the cross-process WRITE half (the S4g surface); router_b is a
            # different instance from the runtime's router_a.
            approve = ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
            await router_b.resolve_pending_grant(
                request_id=request.request_id,
                resolution_json=resolution_to_json(approve),
                state="resolved",
            )
        finally:
            await router_b.close()

        # Process A's poll observes state=resolved + version bump and resumes —
        # reconstructing the EXACT ResolutionShape subclass process B wrote.
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=10)
        assert isinstance(resolution, ApproveResolution)
        assert resolution.decided_by_principal_genesis_id == DEFAULT_PRINCIPAL_ID
        assert runtime.current_state(request.request_id) == GrantMomentState.M3_SIGN

    async def test_cross_process_decline_round_trips_exact_subclass(
        self, vault_path: Path, backend: _MemBackend, router_a: SessionRouter
    ) -> None:
        """A Decline written by process B reconstructs as a DeclineResolution
        (not silently as an Approve) in process A — the codec preserves the
        concrete subclass + the reason field across the boundary."""
        runtime, *_ = await make_runtime(session_router=router_a, default_timeout_seconds=10)
        request = await runtime.issue_grant_moment(**make_issue_kwargs())

        router_b = await _open_router(vault_path, backend)
        try:
            decline = DeclineResolution(
                decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID, reason="not now"
            )
            await router_b.resolve_pending_grant(
                request_id=request.request_id,
                resolution_json=resolution_to_json(decline),
                state="resolved",
            )
        finally:
            await router_b.close()

        resolution = await runtime.await_decision(request.request_id, timeout_seconds=10)
        assert isinstance(resolution, DeclineResolution)
        assert resolution.reason == "not now"

    async def test_resolution_already_in_store_before_first_poll_is_observed(
        self, vault_path: Path, backend: _MemBackend, router_a: SessionRouter
    ) -> None:
        """A writer that resolves BETWEEN issue and the first poll is still
        observed — the version-re-check compares against the issue-time version,
        not the prior poll's, so the resolution is not missed."""
        runtime, *_ = await make_runtime(session_router=router_a, default_timeout_seconds=10)
        request = await runtime.issue_grant_moment(**make_issue_kwargs())

        # Resolve BEFORE await_decision is ever called (the race the lost-update
        # guard must survive).
        router_b = await _open_router(vault_path, backend)
        try:
            await router_b.resolve_pending_grant(
                request_id=request.request_id,
                resolution_json=resolution_to_json(
                    ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
                ),
                state="resolved",
            )
        finally:
            await router_b.close()

        resolution = await runtime.await_decision(request.request_id, timeout_seconds=10)
        assert isinstance(resolution, ApproveResolution)


@pytest.mark.asyncio
class TestMonotonicVersionGuard:
    async def test_stale_version_not_treated_as_resolution(self, router_a: SessionRouter) -> None:
        """A pending row whose version was NOT bumped past issue-time is never
        read as resolved — the version-re-check rejects a stale read.

        We re-put the same request_id (bumping version) but keep state=pending;
        the poll must NOT mistake a version bump alone for a resolution. The
        signal is state in {resolved,expired} AND version > issue.
        """
        runtime, *_ = await make_runtime(session_router=router_a, default_timeout_seconds=1)
        request = await runtime.issue_grant_moment(**make_issue_kwargs())

        # Bump the version WITHOUT resolving (re-put keeps state=pending).
        await router_a.put_pending_grant(
            request_id=request.request_id,
            session_id=request.session_id,
            request_json='{"re":"put"}',
            ttl_expires_at="2099-01-01T00:00:00+00:00",
        )
        bumped = await router_a.get_pending_grant(request.request_id)
        assert bumped is not None and bumped.state == "pending" and bumped.version >= 2

        # The poll must still time out — a version bump on a pending row is NOT
        # a resolution. (If the guard checked version alone, this would resume.)
        with pytest.raises(GrantMomentExpiredError):
            await runtime.await_decision(request.request_id, timeout_seconds=0)

    async def test_writer_bumps_version_mid_poll_reader_observes_new_value(
        self, vault_path: Path, backend: _MemBackend, router_a: SessionRouter
    ) -> None:
        """Regression (acceptance): writer resolves (bumping version) WHILE the
        reader polls; the reader observes the new value, not a cached stale one.

        Each poll opens a fresh SQLite connection (WAL), so a concurrent
        committed write is visible on the next poll tick — no stale snapshot.
        """
        runtime, *_ = await make_runtime(
            session_router=router_a,
            default_timeout_seconds=10,
            poll_interval_start_seconds=0.02,
            poll_interval_cap_seconds=0.05,
        )
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        issue_row = await router_a.get_pending_grant(request.request_id)
        assert issue_row is not None
        version_at_issue = issue_row.version

        import asyncio

        async def _resolve_after_a_few_polls() -> None:
            await asyncio.sleep(0.1)  # let A poll a few times first
            router_b = await _open_router(vault_path, backend)
            try:
                new_version = await router_b.resolve_pending_grant(
                    request_id=request.request_id,
                    resolution_json=resolution_to_json(
                        ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
                    ),
                    state="resolved",
                )
                # version strictly increased past the issue-time value.
                assert new_version > version_at_issue
            finally:
                await router_b.close()

        writer = asyncio.create_task(_resolve_after_a_few_polls())
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=10)
        await writer
        assert isinstance(resolution, ApproveResolution)


@pytest.mark.asyncio
class TestTimeoutAuditRowByteIdentity:
    async def test_store_poll_timeout_matches_phase01_future_timeout_byte_identically(
        self, router_a: SessionRouter
    ) -> None:
        """A poll-timeout (store-poll path) emits the IDENTICAL terminal
        behavior as the Phase-01 in-process future-timeout path: same M2 → M3
        state transition, same GrantMomentExpiredError (request_id +
        timeout_seconds), same in-flight cleanup.

        Both runtimes issue the SAME request, time out, and the two
        GrantMomentExpiredError instances are compared field-by-field. The only
        difference between the runtimes is the rendezvous mechanism (store-poll
        vs future); the audit-emitting timeout behavior MUST be byte-identical
        (zero-tolerance Rule 1).
        """
        # Fixed identifiers so the two paths' Phase-A ledger rows differ ONLY
        # by the rendezvous mechanism, not by per-request uuids — making the
        # durable audit row directly byte-comparable.
        fixed_kwargs = dict(
            nonce="fixed-nonce-deadbeef",
            intent_id="sha256:fixed-intent-cafe",
        )

        # --- Phase-01 path: no session_router → in-process future rendezvous.
        runtime_phase01, _km01, _l01, audit01, _a01 = await make_runtime(default_timeout_seconds=1)
        req01 = await runtime_phase01.issue_grant_moment(**make_issue_kwargs(**fixed_kwargs))
        with pytest.raises(GrantMomentExpiredError) as exc01:
            await runtime_phase01.await_decision(req01.request_id, timeout_seconds=0)
        assert runtime_phase01.inflight_count() == 0
        rows01 = await _list_events(audit01)

        # --- S4r path: session_router wired → store-poll rendezvous.
        runtime_s4r, _kms, _ls, audits, _as = await make_runtime(
            session_router=router_a, default_timeout_seconds=1
        )
        req_s4r = await runtime_s4r.issue_grant_moment(**make_issue_kwargs(**fixed_kwargs))
        with pytest.raises(GrantMomentExpiredError) as exc_s4r:
            await runtime_s4r.await_decision(req_s4r.request_id, timeout_seconds=0)
        assert runtime_s4r.inflight_count() == 0
        rows_s4r = await _list_events(audits)

        # Byte-identity of the audit-bearing error: same type + same kwargs.
        assert type(exc_s4r.value) is type(exc01.value) is GrantMomentExpiredError
        assert exc_s4r.value.timeout_seconds == exc01.value.timeout_seconds == 0
        # Construct both errors with the SAME request_id to prove the str/repr
        # form is byte-identical (the only per-request variation is request_id).
        err01 = GrantMomentExpiredError(request_id="fixed-id", timeout_seconds=0)
        err_s4r = GrantMomentExpiredError(request_id="fixed-id", timeout_seconds=0)
        assert str(err01) == str(err_s4r)
        assert repr(err01) == repr(err_s4r)
        # And the live errors' str forms, with request_id substituted, match.
        assert str(exc01.value).replace(req01.request_id, "X") == str(exc_s4r.value).replace(
            req_s4r.request_id, "X"
        )

        # The DURABLE audit trail: the ONLY ledger row a timed-out grant emits
        # is the Phase-A row written at issue (the timeout path drives the
        # M2 → M3 transition + raises, but appends NO ledger row). Both paths
        # MUST emit EXACTLY ONE PhaseARecord and nothing else — byte-identical.
        actions01 = [getattr(e, "action", "") for e in rows01]
        actions_s4r = [getattr(e, "action", "") for e in rows_s4r]
        assert actions01 == actions_s4r == ["PhaseARecord"], (
            f"timeout must emit exactly the Phase-A row on both paths; "
            f"phase01={actions01} s4r={actions_s4r}"
        )
        # The Phase-A envelope content is byte-identical given identical inputs
        # (request_id is the ONLY request-scoped field that varies; normalize
        # it before comparing). issued_at / phase_a_at are wall-clock and
        # normalized too — every OTHER field MUST match exactly.
        env01 = dict(rows01[0].metadata["_envoy_envelope_v1"]["content"])
        env_s4r = dict(rows_s4r[0].metadata["_envoy_envelope_v1"]["content"])
        # request_id / session_id are per-request uuids; phase_a_at / issued_at
        # / ttl_expires_at are wall-clock; signature + pubkey are keypair-scoped
        # (each make_runtime() mints an independent InMemoryKeyManager). None of
        # these are rendezvous-PATH-scoped — normalize them; every remaining
        # field MUST match exactly between the store-poll and future paths.
        for k in (
            "request_id",
            "session_id",
            "phase_a_at",
            "ttl_expires_at",
            "issued_at",
            "signature_by_delegator_hex",
            "delegation_key_pubkey_hex",
        ):
            env01.pop(k, None)
            env_s4r.pop(k, None)
        assert env01 == env_s4r, (
            "Phase-A audit-row content diverged between the store-poll and "
            f"Phase-01 future paths:\nphase01={env01}\ns4r={env_s4r}"
        )

    async def test_store_poll_timeout_drives_m2_to_m3_transition(
        self, router_a: SessionRouter
    ) -> None:
        """The poll-timeout drives the M2 → M3 TIMEOUT_EXPIRED transition before
        raising (the same transition the Phase-01 path drives), so the timeout
        is recorded as an M3-reaching event, not a silent drop."""
        runtime, *_ = await make_runtime(session_router=router_a, default_timeout_seconds=1)
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        # Before timeout, the grant is at M2_AWAIT.
        assert runtime.current_state(request.request_id) == GrantMomentState.M2_AWAIT
        with pytest.raises(GrantMomentExpiredError):
            await runtime.await_decision(request.request_id, timeout_seconds=0)
        # The in-flight row is dropped (state machine reached M3 then cleaned
        # up) — same terminal as the Phase-01 path.
        assert runtime.inflight_count() == 0


@pytest.mark.asyncio
class TestResolutionCodec:
    async def test_codec_round_trips_all_three_shapes(self) -> None:
        """resolution_to_json / resolution_from_json round-trip every concrete
        ResolutionShape subclass with its discriminating payload intact."""
        from envoy.grant_moment import ApproveWithModificationResolution

        approve = ApproveResolution(
            decided_by_principal_genesis_id="p", author_payload={"new_constraint": {"x": 1}}
        )
        decline = DeclineResolution(decided_by_principal_genesis_id="p", reason="r")
        modify = ApproveWithModificationResolution(
            decided_by_principal_genesis_id="p",
            modify_payload={"new_args_canonical": {"a": 2}},
        )

        for original in (approve, decline, modify):
            blob = resolution_to_json(original)
            recovered = resolution_from_json(blob)
            assert type(recovered) is type(original)
            assert (
                recovered.decided_by_principal_genesis_id
                == original.decided_by_principal_genesis_id
            )

        assert resolution_from_json(resolution_to_json(approve)).author_payload == {
            "new_constraint": {"x": 1}
        }
        assert resolution_from_json(resolution_to_json(decline)).reason == "r"
        assert resolution_from_json(resolution_to_json(modify)).modify_payload == {
            "new_args_canonical": {"a": 2}
        }

    async def test_codec_rejects_unknown_shape_discriminator(self) -> None:
        """A corrupt resolution blob with an unknown shape fails loud at the
        read boundary rather than mis-reconstructing into a wrong decision."""
        with pytest.raises(ValueError, match="unknown shape discriminator"):
            resolution_from_json('{"shape":"bogus","decided_by_principal_genesis_id":"p"}')


@pytest.mark.asyncio
class TestResolutionAuthenticity:
    """S4r security H1: a cross-process resolution row is consumed only after
    its detached signature verifies against the session signing key. A row a
    same-UID process forged by writing the vault sqlite directly (no valid
    signature), a tampered resolution, or a signature replayed from a different
    request_id are all REFUSED fail-closed — the human-authority grant gate
    never executes a decision it cannot attribute to a session-key holder.
    """

    async def test_forged_directly_written_row_is_refused_fail_closed(
        self, vault_path: Path, backend: _MemBackend, router_a: SessionRouter
    ) -> None:
        """A resolved row written DIRECTLY to the sqlite file (bypassing
        resolve_pending_grant, so carrying a bogus signature) is refused —
        await_decision raises GrantMomentResolutionUnauthenticatedError, NOT
        the forged ApproveResolution. This is the literal H1 exploit: a
        same-UID process flips a pending grant to a forged APPROVE."""
        runtime, *_ = await make_runtime(session_router=router_a, default_timeout_seconds=10)
        request = await runtime.issue_grant_moment(**make_issue_kwargs())

        forged = resolution_to_json(
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
        )
        # Direct sqlite write — the attacker has filesystem access to the vault
        # db but produces no valid session-key signature.
        conn = sqlite3.connect(session_db_path(vault_path))
        try:
            conn.execute(
                "UPDATE pending_grant SET state='resolved', resolution_json=?, "
                "resolution_sig=?, version=version + 1 WHERE request_id=?",
                (forged, "00" * 64, request.request_id),  # bogus 64-byte sig
            )
            conn.commit()
        finally:
            conn.close()

        with pytest.raises(GrantMomentResolutionUnauthenticatedError):
            await runtime.await_decision(request.request_id, timeout_seconds=10)

    async def test_null_signature_row_is_refused(
        self, vault_path: Path, backend: _MemBackend, router_a: SessionRouter
    ) -> None:
        """A resolved row with a NULL signature (e.g. a pre-H1 row, or a writer
        that skipped signing) is refused fail-closed."""
        runtime, *_ = await make_runtime(session_router=router_a, default_timeout_seconds=10)
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        forged = resolution_to_json(
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
        )
        conn = sqlite3.connect(session_db_path(vault_path))
        try:
            conn.execute(
                "UPDATE pending_grant SET state='resolved', resolution_json=?, "
                "resolution_sig=NULL, version=version + 1 WHERE request_id=?",
                (forged, request.request_id),
            )
            conn.commit()
        finally:
            conn.close()
        with pytest.raises(GrantMomentResolutionUnauthenticatedError):
            await runtime.await_decision(request.request_id, timeout_seconds=10)

    async def test_verify_rejects_tamper_replay_and_absent_signature(
        self, vault_path: Path, backend: _MemBackend
    ) -> None:
        """verify_resolution_signature is fail-closed on every non-authentic
        input: a valid signature verifies; the SAME signature is rejected when
        the request_id changes (replay binding) or the resolution_json is
        tampered; an absent signature is rejected."""
        router = await _open_router(vault_path, backend)
        try:
            approve_json = resolution_to_json(
                ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
            )
            # A real signature over request "X"'s resolution, signed with the
            # session key (the same surface resolve_pending_grant uses).
            sig_for_x = router._key_manager.sign_with_key(  # type: ignore[union-attr]
                SESSION_SIGNING_KEY_ID, resolution_signing_payload("req-X", approve_json)
            )
            # Valid for X.
            assert (
                await router.verify_resolution_signature(
                    request_id="req-X", resolution_json=approve_json, resolution_sig=sig_for_x
                )
                is True
            )
            # Replay onto a DIFFERENT request_id is rejected (request_id binding).
            assert (
                await router.verify_resolution_signature(
                    request_id="req-Y", resolution_json=approve_json, resolution_sig=sig_for_x
                )
                is False
            )
            # A tampered resolution (Approve → Decline) under the same sig fails.
            tampered = resolution_to_json(
                DeclineResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
            )
            assert (
                await router.verify_resolution_signature(
                    request_id="req-X", resolution_json=tampered, resolution_sig=sig_for_x
                )
                is False
            )
            # An absent signature is rejected.
            assert (
                await router.verify_resolution_signature(
                    request_id="req-X", resolution_json=approve_json, resolution_sig=None
                )
                is False
            )
        finally:
            await router.close()
