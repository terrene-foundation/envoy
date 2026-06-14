# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: the ``chat`` resident receive-loop (WS-6 S6c, LAST shard) on real infra.

`ChatResidentLoop` is a TRANSPORT over the durable store, never the authority.
This suite proves the four load-bearing contracts against real infrastructure
(file-backed `SessionRouter` Region-1 + Region-2, real Ed25519 keychain key via a
dict backend, real `EnvoyLedger`, the REAL grant-moment runtime issue+poll path):

1. **Receive → handle → reply.** A plain conversational message is acked; an
   action message runs the first-time-action gate (S5o).

2. **Drive the Grant Moment via the S4r store-poll rendezvous.** A first-time
   action issues a Grant Moment (durable pending row) and awaits the decision via
   the store poll — NOT an in-process future. A SEPARATE writer resolves the row
   (the cross-process `envoy grant` answer); the loop's poll observes it and
   replies. The approved fingerprint is then RECOGNIZED on a same-session repeat.

3. **A real chat boundary fires the S5b reset (T-013).** When the channel
   disconnects (the receive iterator ends), the loop's `finally` fires
   `SessionBoundarySignal.cross(trigger="channel_disconnect", ...)`; a previously
   recognized fingerprint is first-time-action AGAIN after the boundary, and a
   signed `session_boundary_crossed` entry lands in the Ledger.

4. **Store is authority — crash mid-conversation loses NO pending grant.** A loop
   killed while polling `await_decision` leaves the pending row durable; a FRESH
   router over the same vault sees it and answers it (the S4g path).

Per `rules/testing.md` Tier 2: real infra, NO mocking. The channel adapter is a
deterministic subclass of the REAL `CLIChannelAdapter` overriding only
`receive_message` to yield a scripted message list then END (modelling channel
disconnect) — a Protocol-satisfying deterministic adapter, not a mock (real send
to a captured stream, real lifecycle).
"""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from datetime import datetime, timezone
from pathlib import Path

import keyring.errors
import pytest

from envoy.channels.cli import CLIChannelAdapter, CLIChannelConfig
from envoy.channels.envelope import InboundMessage, MessagePayload
from envoy.grant_moment import ApproveResolution, resolution_to_json
from envoy.runtime import (
    ChatActionSpec,
    ChatResidentLoop,
    GateResult,
    SessionBoundarySignal,
    SessionObservedStateGate,
    SessionRouter,
    fingerprint,
    is_recognized_fingerprint,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_issue_kwargs,
    make_runtime,
)

SESSION_ID = "00000000-0000-7000-8000-0000000000c6"
CLI_CHANNEL_ID = "cli"


class _MemBackend:
    """Pure-dict keyring backend standing in for the OS keychain (no host touch).

    A SHARED instance models the production invariant that two processes open the
    SAME on-disk OS keychain and recover the SAME session signing key.
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


class _ScriptedCLIAdapter(CLIChannelAdapter):
    """Real `CLIChannelAdapter` with a deterministic, TERMINATING inbound stream.

    Overrides ONLY `receive_message` to yield a fixed list then return (the
    iterator ending models a channel disconnect, which the resident loop reacts to
    by firing the S5b boundary). Every other surface — `send_message` to the
    captured `output_stream`, lifecycle, capabilities — is the real CLI adapter.
    """

    def __init__(self, *, output_stream: io.StringIO, scripted: Sequence[InboundMessage]) -> None:
        super().__init__(
            CLIChannelConfig(primary_channel_id=CLI_CHANNEL_ID, output_stream=output_stream)
        )
        self._scripted = list(scripted)

    async def receive_message(self) -> AsyncIterator[InboundMessage]:  # type: ignore[override]
        for msg in self._scripted:
            yield msg
        # Iterator ends → channel disconnect.


def _inbound(body: str) -> InboundMessage:
    return InboundMessage(
        channel_id=CLI_CHANNEL_ID,
        session_id=SESSION_ID,
        principal_genesis_id=DEFAULT_PRINCIPAL_ID,
        direction="inbound",
        content_trust_level="user",
        payload=MessagePayload(kind="text", body=body),
        visible_secret_rendered=None,
        timestamp=datetime(2026, 6, 14, tzinfo=timezone.utc),
    )


def _seed_blob() -> dict[str, object]:
    """A genesis-shaped observed-state blob with no tool calls yet."""
    now = "2026-06-14T00:00:00.000000+00:00"
    return {
        "schema_version": "session-state/1.0",
        "session_id": SESSION_ID,
        "principal_genesis_id": DEFAULT_PRINCIPAL_ID,
        "started_at": now,
        "last_activity_at": now,
        "tool_calls_made": {},
        "goal_reconfirmation": {
            "last_reconfirmed_at": now,
            "tool_calls_since_reconfirm": 0,
            "threshold": 0,
        },
        "reasoning_commits": [],
        "pending_phase_a_orphans": [],
        "pre_authorized_patterns": [],
        "envelope_version_at_session_start": 1,
        "posture_at_session_start": "PSEUDO",
    }


# The action a chat message resolves to. `send_email` matches the harness default
# so the issue kwargs are the production wire form.
_ACTION_BODY = "send an email to ops"
_ACTION_TOOL = "send_email"


class _Harness:
    def __init__(
        self, *, router, runtime, gate, boundary, ledger, audit_store, vault_path, backend
    ):
        self.router = router
        self.runtime = runtime
        self.gate = gate
        self.boundary = boundary
        self.ledger = ledger
        self.audit_store = audit_store
        self.vault_path = vault_path
        self.backend = backend

    def resolver(self, message: InboundMessage) -> ChatActionSpec | None:
        if message.payload.body == _ACTION_BODY:
            return ChatActionSpec(
                issue_kwargs=make_issue_kwargs(tool_name=_ACTION_TOOL, session_id=SESSION_ID)
            )
        return None

    def loop(
        self, *, output: io.StringIO, scripted: Sequence[InboundMessage], grant_timeout: int = 10
    ):
        adapter = _ScriptedCLIAdapter(output_stream=output, scripted=scripted)
        return ChatResidentLoop(
            adapter=adapter,
            runtime=self.runtime,
            gate=self.gate,
            boundary_signal=self.boundary,
            session_id=SESSION_ID,
            resolver=self.resolver,
            grant_timeout_seconds=grant_timeout,
        )


@pytest.fixture
async def harness(tmp_path: Path) -> AsyncGenerator[_Harness, None]:
    vault_path = tmp_path / "trust_vault.dat"
    backend = _MemBackend()
    router = SessionRouter(
        vault_path=vault_path, principal_id=DEFAULT_PRINCIPAL_ID, keyring_backend=backend
    )
    await router.open()
    runtime, _keymgr, ledger, audit_store, _adapters = await make_runtime(
        session_router=router,
        default_timeout_seconds=10,
        poll_interval_start_seconds=0.01,
        poll_interval_cap_seconds=0.02,
    )
    gate = SessionObservedStateGate(router=router)
    boundary = SessionBoundarySignal(ledger=ledger, router=router)
    try:
        yield _Harness(
            router=router,
            runtime=runtime,
            gate=gate,
            boundary=boundary,
            ledger=ledger,
            audit_store=audit_store,
            vault_path=vault_path,
            backend=backend,
        )
    finally:
        await router.close()


async def _seed(harness: _Harness) -> None:
    await harness.router.snapshot_observed_state(
        session_id=SESSION_ID, state_json=json.dumps(_seed_blob())
    )


async def _approve_when_pending(harness: _Harness) -> str:
    """Model the cross-process `envoy grant approve`: wait for the pending row,
    then write a resolution onto it (the S4g WRITE half)."""
    for _ in range(2000):
        if await harness.router.count_pending_grants() > 0:
            break
        await asyncio.sleep(0.005)
    rows = await harness.router.list_pending_grants()
    assert rows, "no pending grant appeared for the loop to await"
    request_id = rows[0].request_id
    await harness.router.resolve_pending_grant(
        request_id=request_id,
        resolution_json=resolution_to_json(
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
        ),
        state="resolved",
    )
    return request_id


# ---------------------------------------------------------------------------
# 1. Receive → handle → reply
# ---------------------------------------------------------------------------


class TestPlainMessage:
    async def test_plain_message_is_acked_no_grant(self, harness: _Harness) -> None:
        await _seed(harness)
        out = io.StringIO()
        loop = harness.loop(output=out, scripted=[_inbound("hello there")])
        results = await loop.run()
        assert [r.kind for r in results] == ["ack"]
        assert await harness.router.count_pending_grants() == 0
        assert "received" in out.getvalue()

    async def test_conversation_only_loop_raises_typed_error_on_action(
        self, harness: _Harness
    ) -> None:
        # A loop with NO grant substrate (runtime/gate omitted) that nonetheless
        # resolves an action surfaces a typed error — NOT a fabricated grant.
        from envoy.runtime import ChatActionUnsupportedError, ChatResidentLoop

        await _seed(harness)
        out = io.StringIO()
        adapter = _ScriptedCLIAdapter(output_stream=out, scripted=[_inbound(_ACTION_BODY)])
        loop = ChatResidentLoop(
            adapter=adapter,
            boundary_signal=harness.boundary,
            session_id=SESSION_ID,
            resolver=harness.resolver,
        )
        with pytest.raises(ChatActionUnsupportedError, match="no grant substrate"):
            await loop.run()


# ---------------------------------------------------------------------------
# 2. Drive the Grant Moment via the S4r store-poll rendezvous
# ---------------------------------------------------------------------------


class TestGrantDriveViaStorePoll:
    async def test_first_time_action_issues_grant_and_resumes_on_store_resolution(
        self, harness: _Harness
    ) -> None:
        await _seed(harness)
        out = io.StringIO()
        loop = harness.loop(output=out, scripted=[_inbound(_ACTION_BODY)])
        # The loop issues + polls; a concurrent writer resolves the durable row
        # (cross-process answer). The poll — NOT an in-process future — resumes.
        results, _request_id = await asyncio.gather(loop.run(), _approve_when_pending(harness))
        assert [r.kind for r in results] == ["grant_approved"]
        assert "approved: send_email" in out.getvalue()

    async def test_approved_fingerprint_recognized_on_same_session_repeat(
        self, harness: _Harness
    ) -> None:
        # Two IDENTICAL action messages in one session: the first is first-time
        # (issues a grant, approved → cached); the second is RECOGNIZED (no second
        # Grant Moment). The approver resolves exactly ONE pending row.
        await _seed(harness)
        out = io.StringIO()
        loop = harness.loop(
            output=out, scripted=[_inbound(_ACTION_BODY), _inbound(_ACTION_BODY)], grant_timeout=10
        )
        results, _ = await asyncio.gather(loop.run(), _approve_when_pending(harness))
        assert [r.kind for r in results] == ["grant_approved", "recognized"]
        # Only ONE grant was ever issued — the repeat short-circuited at the gate.
        assert await harness.router.count_pending_grants() == 0


# ---------------------------------------------------------------------------
# 3. A real chat boundary fires the S5b reset (T-013) — the headline S6c AC
# ---------------------------------------------------------------------------


class TestBoundaryFiresReset:
    async def test_channel_disconnect_fires_t013_reset_and_ledger_entry(
        self, harness: _Harness
    ) -> None:
        # Seed a blob that ALREADY recognizes the action fingerprint, so we can
        # prove the disconnect boundary CLEARS it (T-013).
        fp = fingerprint(
            _ACTION_TOOL, make_issue_kwargs(tool_name=_ACTION_TOOL)["tool_args_canonical"]
        )
        blob = _seed_blob()
        blob["tool_calls_made"] = {fp: {"first_seen_at": "2026-06-14T00:00:00.000000+00:00"}}  # type: ignore[index]
        await harness.router.snapshot_observed_state(
            session_id=SESSION_ID, state_json=json.dumps(blob)
        )
        # Pre-condition: the fingerprint IS recognized before the loop runs.
        raw_before = await harness.router.load_observed_state(SESSION_ID)
        assert raw_before is not None
        assert is_recognized_fingerprint(json.loads(raw_before), fp)

        # Run the loop over a plain message; it ends (disconnect) → boundary fires.
        out = io.StringIO()
        loop = harness.loop(output=out, scripted=[_inbound("just chatting")])
        await loop.run()

        # Post-condition: the disconnect boundary applied the T-013 reset —
        # the fingerprint is no longer recognized (cache cleared).
        raw_after = await harness.router.load_observed_state(SESSION_ID)
        assert raw_after is not None
        assert not is_recognized_fingerprint(json.loads(raw_after), fp), (
            "the channel-disconnect boundary did not clear the observed-state cache"
        )

        # And a signed session_boundary_crossed entry landed with the disconnect trigger.
        boundary_seen = await _boundary_entry_present(harness)
        assert boundary_seen, "no session_boundary_crossed entry was appended by the loop"

    async def test_post_boundary_fresh_gate_sees_first_time_again(self, harness: _Harness) -> None:
        # End-to-end: a fingerprint cached DURING the chat session is first-time
        # again for a FRESH process (fresh router) after the disconnect boundary.
        await _seed(harness)
        out = io.StringIO()
        loop = harness.loop(output=out, scripted=[_inbound(_ACTION_BODY)])
        await asyncio.gather(loop.run(), _approve_when_pending(harness))

        router_b = SessionRouter(
            vault_path=harness.vault_path,
            principal_id=DEFAULT_PRINCIPAL_ID,
            keyring_backend=harness.backend,
        )
        await router_b.open()
        try:
            gate_b = SessionObservedStateGate(router=router_b)
            verdict = await gate_b.evaluate(
                session_id=SESSION_ID,
                tool_name=_ACTION_TOOL,
                args=make_issue_kwargs(tool_name=_ACTION_TOOL)["tool_args_canonical"],
            )
            assert verdict is GateResult.FIRST_TIME_REQUIRES_GRANT
        finally:
            await router_b.close()


# ---------------------------------------------------------------------------
# 4. Store is authority — crash mid-conversation loses NO pending grant
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    async def test_loop_killed_mid_grant_leaves_answerable_pending_row(
        self, harness: _Harness
    ) -> None:
        await _seed(harness)
        out = io.StringIO()
        # No approver — the loop will issue the grant and BLOCK in await_decision.
        loop = harness.loop(output=out, scripted=[_inbound(_ACTION_BODY)], grant_timeout=60)
        task = asyncio.create_task(loop.run())
        # Wait until the pending row is durable (issue happened), then KILL the loop.
        for _ in range(2000):
            if await harness.router.count_pending_grants() > 0:
                break
            await asyncio.sleep(0.005)
        assert await harness.router.count_pending_grants() == 1, "grant was not issued before crash"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Store is authority: a FRESH router sees the pending grant and answers it.
        router_b = SessionRouter(
            vault_path=harness.vault_path,
            principal_id=DEFAULT_PRINCIPAL_ID,
            keyring_backend=harness.backend,
        )
        await router_b.open()
        try:
            rows = await router_b.list_pending_grants()
            assert len(rows) == 1, "pending grant did not survive the loop crash"
            new_version = await router_b.resolve_pending_grant(
                request_id=rows[0].request_id,
                resolution_json=resolution_to_json(
                    ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
                ),
                state="resolved",
            )
            assert new_version >= 1
            # The row is now resolved — answerable post-crash, exactly the S4g path.
            assert await router_b.count_pending_grants() == 0
        finally:
            await router_b.close()


async def _boundary_entry_present(harness: _Harness) -> bool:
    """True iff a session_boundary_crossed entry was appended to the Ledger."""
    from kailash.trust.audit_store import AuditFilter  # noqa: PLC0415

    records = await harness.audit_store.query(AuditFilter())
    for rec in records:
        blob = json.dumps(vars(rec), default=str) if hasattr(rec, "__dict__") else str(rec)
        if "channel_disconnect" in blob or "session_boundary" in blob or "session-boundary" in blob:
            return True
    return False
