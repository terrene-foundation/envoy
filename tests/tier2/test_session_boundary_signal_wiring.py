# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: ``SessionBoundarySignal`` — all 6 triggers + T-013 reset against real infra (S5b).

Per ``rules/facade-manager-detection.md`` Rule 1 + ``rules/orphan-detection.md``
Rule 2, ``SessionBoundarySignal`` (a manager-shape emitter exposed on
``envoy.runtime``) has a Tier-2 wiring test asserting an externally-observable
effect: every one of the six session-lifecycle triggers appends a SIGNED
``session_boundary_crossed`` entry to a real file-backed ``EnvoyLedger`` (chain
verifies end-to-end), and an END trigger RESETS the prior session's durable
``SessionObservedState`` region so a previously-recognized fingerprint is
first-time-action again (T-013).

Per ``rules/testing.md`` Tier 2: real infrastructure — real ``EnvoyLedger`` over
a real file-backed ``SqliteAuditStore``, real ``SessionRouter`` over a real
vault-sibling SQLite store, real Ed25519 keychain keys (dependency-injected dict
backend, no OS-keychain touch). NO mocking. Every write is verified by a
read-back: the emitted entries are queried from the ledger; the reset is
confirmed by re-loading the observed-state region.

The T-013 assertion reuses the SHARED invariant helper (``tests.support.t013``)
that S5o and S6c also consume — no re-derivation per shard.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path

import keyring.errors
import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.ledger.bootstrap import DurableLedger, open_durable_ledger
from envoy.runtime import (
    END_TRIGGERS,
    SESSION_BOUNDARY_SCHEMA_VERSION,
    SessionBoundarySignal,
    SessionRouter,
    is_recognized_fingerprint,
    reset_session_observed_state,
)
from tests.support.t013 import (
    EXAMPLE_FINGERPRINT_KEY,
    assert_t013_reset_clears_cache,
    make_observed_state_with_call,
)

PRINCIPAL = "alice@example.com"
LEDGER_SIGNING_KEY_ID = "envoy-durable-signing-key"
DEVICE_ID = "device-s5b-test"
VALID_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
_SINCE = datetime(2000, 1, 1, tzinfo=timezone.utc)
_UNTIL = datetime(2100, 1, 1, tzinfo=timezone.utc)


class _MemBackend:
    """Pure-dict keyring backend standing in for the OS keychain (no host touch)."""

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


class _Harness:
    """The opened ledger + router + signal, plus their teardown handles."""

    def __init__(
        self,
        *,
        signal: SessionBoundarySignal,
        router: SessionRouter,
        durable: DurableLedger,
    ) -> None:
        self.signal = signal
        self.router = router
        self.durable = durable

    @property
    def ledger(self):  # type: ignore[no-untyped-def]
        return self.durable.ledger


@pytest.fixture
async def harness(tmp_path: Path) -> AsyncGenerator[_Harness, None]:
    vault_path = tmp_path / "trust_vault.dat"

    keymgr = InMemoryKeyManager()
    await keymgr.generate_keypair(LEDGER_SIGNING_KEY_ID)
    durable = await open_durable_ledger(
        vault_path=vault_path,
        key_manager=keymgr,
        signing_key_id=LEDGER_SIGNING_KEY_ID,
        device_id=DEVICE_ID,
        algorithm_identifier=VALID_ALGO_ID,
    )

    router = SessionRouter(
        vault_path=vault_path,
        principal_id=PRINCIPAL,
        keyring_backend=_MemBackend(),
    )
    await router.open()

    signal = SessionBoundarySignal(ledger=durable.ledger, router=router)
    try:
        yield _Harness(signal=signal, router=router, durable=durable)
    finally:
        await router.close()
        await durable.aclose()
        ledger_keys = getattr(keymgr, "_keys", None)
        if isinstance(ledger_keys, dict):
            ledger_keys.clear()


async def _boundary_entries(harness: _Harness) -> list:
    return await harness.ledger.query(
        filter={"event_type": "session_boundary_crossed"},
        since=_SINCE,
        until=_UNTIL,
    )


class TestAllSixTriggersEmitSignedEntry:
    async def test_every_trigger_appends_a_chain_verifying_entry(
        self, harness: _Harness
    ) -> None:
        triggers = ["unlock", "cli_start", "cli_end", "idle_timeout", "user_lock", "channel_disconnect"]
        results = []
        for i, trigger in enumerate(triggers):
            result = await harness.signal.cross(
                trigger=trigger,
                session_id_prior=f"00000000-0000-7000-8000-00000000000{i}",
                session_id_next=None,
            )
            results.append(result)

        # Every cross() returns a non-empty entry_id with the right transition.
        for result, trigger in zip(results, triggers, strict=True):
            assert result.entry_id, f"{trigger} produced no entry_id"
            expected = "end" if trigger in END_TRIGGERS else "start"
            assert result.transition == expected, (trigger, result.transition)

        # External effect: exactly 6 signed boundary entries landed, and the
        # whole chain verifies (every entry's Ed25519 signature + hash link).
        entries = await _boundary_entries(harness)
        assert len(entries) == 6
        report = await harness.ledger.verify_chain()
        assert report.success is True

        # Read-back: each entry's content carries the full session-boundary/1.0
        # schema with the matching trigger + transition.
        by_trigger = {e.content["trigger"]: e for e in entries}
        assert set(by_trigger) == set(triggers)
        for trigger, env in by_trigger.items():
            content = env.content
            assert content["schema_version"] == SESSION_BOUNDARY_SCHEMA_VERSION
            assert content["transition"] == ("end" if trigger in END_TRIGGERS else "start")
            for field in (
                "session_id_prior",
                "session_id_next",
                "tool_call_count_observed",
                "orphan_phase_a_count",
                "unresolved_grants_deferred",
            ):
                assert field in content, (trigger, field)


class TestEndTriggerResetsObservedStateCache:
    async def test_end_trigger_clears_prior_session_cache(self, harness: _Harness) -> None:
        session_prior = "00000000-0000-7000-8000-0000000000aa"
        blob = make_observed_state_with_call(session_id=session_prior)
        # Seed the durable region with a populated observed-state.
        await harness.router.snapshot_observed_state(
            session_id=session_prior, state_json=json.dumps(blob)
        )
        # Sanity: the fingerprint is recognized BEFORE the boundary.
        assert is_recognized_fingerprint(blob, EXAMPLE_FINGERPRINT_KEY)

        result = await harness.signal.cross(
            trigger="idle_timeout", session_id_prior=session_prior
        )
        assert result.transition == "end"
        assert result.reset_applied is True

        # Read-back: the durable region now holds the RESET blob.
        raw = await harness.router.load_observed_state(session_prior)
        assert raw is not None
        persisted = json.loads(raw)
        assert persisted["tool_calls_made"] == {}
        assert persisted["goal_reconfirmation"]["tool_calls_since_reconfirm"] == 0
        # The previously-recognized fingerprint is first-time-action again.
        assert not is_recognized_fingerprint(persisted, EXAMPLE_FINGERPRINT_KEY)

    async def test_shared_t013_invariant_against_persisted_reset(
        self, harness: _Harness
    ) -> None:
        # Drive the live reset, then assert the SHARED invariant S5o/S6c reuse
        # against the persisted-and-reloaded blob (proves the durable round-trip
        # honors the same contract, not just the in-memory pure function).
        session_prior = "00000000-0000-7000-8000-0000000000bb"
        blob = make_observed_state_with_call(session_id=session_prior)
        await harness.router.snapshot_observed_state(
            session_id=session_prior, state_json=json.dumps(blob)
        )
        # The pure-function invariant holds on the seed blob...
        assert_t013_reset_clears_cache(blob, EXAMPLE_FINGERPRINT_KEY)
        # ...and the live store round-trip produces the same cleared shape.
        await harness.signal.cross(trigger="user_lock", session_id_prior=session_prior)
        raw = await harness.router.load_observed_state(session_prior)
        assert raw is not None
        assert reset_session_observed_state(blob) == json.loads(raw)


class TestBoundaryEntryCarriesDerivedCounts:
    async def test_counts_reflect_prior_blob_and_pending_queue(
        self, harness: _Harness
    ) -> None:
        session_prior = "00000000-0000-7000-8000-0000000000cc"
        # Two pending grants in the queue → unresolved_grants_deferred == 2.
        for n in range(2):
            await harness.router.put_pending_grant(
                request_id=f"req-{n}",
                session_id=session_prior,
                request_json=json.dumps({"request_id": f"req-{n}"}),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
        # A blob with two recorded calls + one orphan Phase-A.
        blob = make_observed_state_with_call(session_id=session_prior)
        blob["tool_calls_made"]["sha256:" + "11" * 32] = {
            "tool_name": "fs.write",
            "args_canonical_hash": "sha256:" + "11" * 32,
            "first_invoked_at": "2026-06-13T00:02:00.000000+00:00",
            "invocation_count": 1,
            "last_outcome": "success",
        }
        blob["pending_phase_a_orphans"] = [
            {
                "intent_id": "sha256:orphan",
                "phase_a_at": "2026-06-13T00:03:00.000000+00:00",
                "ttl_expires_at": "2026-07-13T00:03:00.000000+00:00",
            }
        ]
        await harness.router.snapshot_observed_state(
            session_id=session_prior, state_json=json.dumps(blob)
        )

        result = await harness.signal.cross(
            trigger="cli_end", session_id_prior=session_prior
        )
        assert result.tool_call_count_observed == 2
        assert result.orphan_phase_a_count == 1
        assert result.unresolved_grants_deferred == 2

        # Read-back: the SIGNED entry carries the same counts (captured BEFORE
        # the reset, so the audit row keeps the end-of-session totals).
        entries = await _boundary_entries(harness)
        assert len(entries) == 1
        content = entries[0].content
        assert content["tool_call_count_observed"] == 2
        assert content["orphan_phase_a_count"] == 1
        assert content["unresolved_grants_deferred"] == 2


class TestStartTriggerDoesNotReset:
    async def test_start_with_no_prior_session_emits_without_reset(
        self, harness: _Harness
    ) -> None:
        result = await harness.signal.cross(
            trigger="unlock",
            session_id_prior=None,
            session_id_next="00000000-0000-7000-8000-0000000000dd",
        )
        assert result.transition == "start"
        assert result.reset_applied is False
        assert result.tool_call_count_observed == 0
        entries = await _boundary_entries(harness)
        assert len(entries) == 1
        assert entries[0].content["session_id_prior"] is None
        assert entries[0].content["session_id_next"] == "00000000-0000-7000-8000-0000000000dd"

    async def test_unknown_trigger_raises(self, harness: _Harness) -> None:
        with pytest.raises(ValueError, match="unknown session-boundary trigger"):
            await harness.signal.cross(trigger="logout", session_id_prior=None)
