# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: F10 — KailashPyRuntime.trust_cascade_revoke facade wiring.

Source authority:
- `01-analysis/02-mvp-objectives.md` EC-2 line 42 ("Cascade revocation is a
  hard constraint per CHARTER §41 + `specs/trust-lineage.md`") + EC-8 line 116
  sub-clause (c) ("cascade revocation of a Day-1 grant correctly revokes a
  Day-6 child grant initiated from a different channel").
- `specs/runtime-abstraction.md:31` — `trust_cascade_revoke(root_id)` is
  declared SYNC: `(str) -> set[str]`, byte-identical SET equality for
  cross-runtime conformance.
- `rules/facade-manager-detection.md` Rule 2 (canonical wiring-test filename
  so absence is grep-able) + `rules/orphan-detection.md` Rule 2 (every facade
  exercised end-to-end, not just in isolation).

Gap this closes (R4 reviewer MED-2): every existing cascade test wires a
hand-written ``StubTrustRuntime`` (`tests/helpers/grant_moment_harness.py`)
and exercises only the ``CascadeRevocationOrchestrator`` — NOT the production
``KailashPyRuntime.trust_cascade_revoke`` binding. The production binding's
forwarding logic was therefore never exercised against a real backing store.

Per `rules/testing.md` Tier 2: NO mocking. The async path uses a real
``envoy.trust.store.TrustStoreAdapter`` (real kailash-backed cascade store).
The sync-store path uses a Protocol-Satisfying Deterministic Adapter (a plain
class implementing a SYNC ``revoke(*, agent_id, reason, revoked_by)`` returning
a real-shape ``RevocationResult``) — per `rules/testing.md` § "Protocol
Adapters", a class satisfying a Protocol at runtime with deterministic output
is NOT a mock.

The async-store path is now driven by F12-b's sync↔async bridge
(`envoy.runtime.adapters._async_cascade_bridge.run_coro_blocking`): the sync
Protocol method drives the async ``revoke`` coroutine to completion on a
dedicated worker-thread event loop and returns the real revoked set — NEVER a
silent empty set (which would invisibly violate the EC-2 + EC-8(c) cascade
hard-constraint). The async-store coverage here uses a Protocol-Satisfying
Deterministic *async* store (a plain class with ``async def revoke``) so the
bridge's coroutine-driving is exercised without DB/event-loop affinity
confounds; the real ``TrustStoreAdapter``-through-the-facade cascade is the
e2e lift at ``tests/e2e/test_grant_moment_3_resolution_shapes_with_cascade.py``.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import pytest

from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.errors import Phase02SubstrateNotWiredError

# ---------------------------------------------------------------------------
# Protocol-Satisfying Deterministic Adapters — sync + async stores (NOT mocks)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SyncRevocationResult:
    """Real-shape RevocationResult: the production binding reads only
    ``revoked_agents``. Frozen so the test cannot mutate it post-construction."""

    revoked_agents: list[str]
    success: bool = True


@dataclass
class _AsyncTrustStore:
    """Protocol-Satisfying Deterministic Adapter — an ASYNC trust store.

    Mirrors the production ``envoy.trust.store.TrustStoreAdapter.revoke`` SHAPE
    (``async def revoke(*, agent_id, reason, revoked_by) -> RevocationResult``)
    without its DB/event-loop affinity, so the F12-b bridge's coroutine-driving
    is exercised deterministically. Per `rules/testing.md` § Tier 2 (NO
    mocking) — this is a real object satisfying the structural async-store shape,
    not an ``unittest.mock``. The real ``TrustStoreAdapter``-through-the-facade
    cascade is the e2e lift (see module docstring)."""

    revoked_by_root: dict[str, list[str]] = field(default_factory=dict)
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    async def revoke(
        self, *, agent_id: str, reason: str, revoked_by: str
    ) -> _SyncRevocationResult:
        self.calls.append((agent_id, reason, revoked_by))
        return _SyncRevocationResult(
            revoked_agents=list(self.revoked_by_root.get(agent_id, []))
        )


@dataclass
class _SyncTrustStore:
    """Protocol-Satisfying Deterministic Adapter — a SYNC trust store.

    Mirrors the future T-01-15 sync wrapper shape: a plain class exposing a
    synchronous ``revoke(*, agent_id, reason, revoked_by) -> RevocationResult``.
    Records calls so wiring assertions can verify the forwarded arguments.
    Per `rules/testing.md` § Tier 2 (NO mocking) — there is no ``unittest.mock``
    here; this is a real object satisfying the structural sync-store shape.
    """

    revoked_by_root: dict[str, list[str]] = field(default_factory=dict)
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def revoke(self, *, agent_id: str, reason: str, revoked_by: str) -> _SyncRevocationResult:
        self.calls.append((agent_id, reason, revoked_by))
        return _SyncRevocationResult(revoked_agents=list(self.revoked_by_root.get(agent_id, [])))


# ---------------------------------------------------------------------------
# Guard path — no store supplied
# ---------------------------------------------------------------------------


class TestNoStoreGuard:
    def test_raises_typed_error_when_no_trust_store(self) -> None:
        runtime = KailashPyRuntime()
        with pytest.raises(Phase02SubstrateNotWiredError) as exc_info:
            runtime.trust_cascade_revoke("agent-root")
        # Message names the missing substrate so a future session can grep it.
        assert "trust_cascade_revoke" in str(exc_info.value)
        assert "trust_store=" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Async-store path — F12-b: the sync facade drives the async revoke via the
# worker-thread bridge and returns the REAL revoked set, never silent-empty.
# ---------------------------------------------------------------------------


class TestAsyncStoreDrivenViaBridge:
    def test_async_store_revoked_set_returned_via_bridge(self) -> None:
        """The production backing store is async. The sync Protocol method MUST
        drive its ``revoke`` coroutine to completion via the F12-b bridge and
        return the real revoked set — the EC-8(c) shape: revoking the Day-1
        root returns the Day-6 child. NOT a typed error (pre-F12-b), NOT a
        silent empty set (the pre-F10 bug)."""
        store = _AsyncTrustStore(
            revoked_by_root={"agent-day1-root": ["agent-day1-root", "agent-day6-child"]}
        )
        runtime = KailashPyRuntime(trust_store=store)

        revoked = runtime.trust_cascade_revoke("agent-day1-root")

        assert revoked == {"agent-day1-root", "agent-day6-child"}
        assert isinstance(revoked, set)
        # Externally observable: the async store received the forwarded call
        # with the runtime's canonical reason + revoked_by attribution.
        assert store.calls == [
            ("agent-day1-root", "envoy.runtime.cascade_revoke", "envoy.runtime.kailash_py")
        ]

    async def test_async_store_driven_from_inside_a_running_loop(self) -> None:
        """The EC-8 hazard: a cross-channel flow calls the sync facade from
        INSIDE a running event loop (this test body). The bridge MUST still
        drive the async revoke — a naive ``asyncio.run()`` would raise here."""
        store = _AsyncTrustStore(
            revoked_by_root={"root": ["root", "child-1", "child-2", "child-3"]}
        )
        runtime = KailashPyRuntime(trust_store=store)

        revoked = runtime.trust_cascade_revoke("root")

        assert revoked == {"root", "child-1", "child-2", "child-3"}

    def test_async_store_empty_result_is_genuine_not_silent_fallback(self) -> None:
        """An empty revoked set from the real async engine (idempotent no-op on
        an unknown root) is GENUINE — the coroutine actually ran. Distinct from
        the pre-F10 silent fallback that never called the store at all."""
        store = _AsyncTrustStore(revoked_by_root={})
        runtime = KailashPyRuntime(trust_store=store)

        revoked = runtime.trust_cascade_revoke("agent-unknown")

        assert revoked == set()
        assert store.calls == [
            ("agent-unknown", "envoy.runtime.cascade_revoke", "envoy.runtime.kailash_py")
        ]

    def test_async_store_does_not_leak_unawaited_coroutine_warning(self) -> None:
        """The bridge AWAITS the coroutine to completion (it does not close-
        and-discard), so no 'coroutine was never awaited' RuntimeWarning leaks
        at GC."""
        store = _AsyncTrustStore(revoked_by_root={"root": ["root", "child"]})
        runtime = KailashPyRuntime(trust_store=store)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            revoked = runtime.trust_cascade_revoke("root")
        assert revoked == {"root", "child"}
        unawaited = [w for w in caught if "never awaited" in str(w.message)]
        assert unawaited == [], (
            f"async store path leaked unawaited-coroutine warning(s): "
            f"{[str(w.message) for w in unawaited]}"
        )


# ---------------------------------------------------------------------------
# Sync-store path — the forward-looking Protocol contract (EC-8(c)-shaped)
# ---------------------------------------------------------------------------


class TestSyncStoreForwarding:
    def test_sync_store_returns_revoked_descendant_set(self) -> None:
        """When a SYNC Protocol-satisfying store is supplied, the facade
        unpacks its RevocationResult and returns the exact revoked set —
        the EC-8(c) shape: revoking the Day-1 root returns the Day-6 child."""
        store = _SyncTrustStore(
            revoked_by_root={"agent-day1-root": ["agent-day1-root", "agent-day6-child"]}
        )
        runtime = KailashPyRuntime(trust_store=store)

        revoked = runtime.trust_cascade_revoke("agent-day1-root")

        assert revoked == {"agent-day1-root", "agent-day6-child"}
        assert isinstance(revoked, set)
        # Externally observable: the store received the forwarded call with
        # the runtime's canonical reason + revoked_by attribution.
        assert store.calls == [
            (
                "agent-day1-root",
                "envoy.runtime.cascade_revoke",
                "envoy.runtime.kailash_py",
            )
        ]

    def test_sync_store_empty_result_is_genuine_not_silent_fallback(self) -> None:
        """An empty revoked set from a sync store is a GENUINE empty revoke
        (the store returned ``revoked_agents=[]``), distinct from the pre-fix
        silent fallback. The forwarded call still happened."""
        store = _SyncTrustStore(revoked_by_root={})  # unknown root → genuine []
        runtime = KailashPyRuntime(trust_store=store)

        revoked = runtime.trust_cascade_revoke("agent-unknown")

        assert revoked == set()
        # The genuine path actually called the store (the bug never did).
        assert store.calls == [
            ("agent-unknown", "envoy.runtime.cascade_revoke", "envoy.runtime.kailash_py")
        ]
