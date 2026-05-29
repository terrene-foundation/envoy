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

The async-store behavior pinned here (raise typed error, NEVER silent-empty)
is the F10 fix: the sync Protocol method cannot drive the async
``TrustStoreAdapter.revoke`` without an event-loop bridge that is itself the
Phase-02 substrate; the honest disposition is a loud typed error, because a
silent empty revoked-set invisibly violates the EC-2 + EC-8(c) cascade
hard-constraint (a revoked parent leaving its children alive).
"""

from __future__ import annotations

import warnings
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.errors import Phase02SubstrateNotWiredError
from envoy.trust.store import TrustStoreAdapter


@pytest.fixture
async def real_trust_store(
    tmp_path: Path,
) -> AsyncGenerator[TrustStoreAdapter, None]:
    """Real kailash-backed TrustStoreAdapter (async ``revoke``). NO mock."""
    adapter = TrustStoreAdapter(
        vault_path=tmp_path / "f10-vault.dat",
        principal_id="f10-cascade-principal",
    )
    await adapter.initialize()
    yield adapter
    await adapter.close()


# ---------------------------------------------------------------------------
# Protocol-Satisfying Deterministic Adapter — sync store (NOT a mock)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SyncRevocationResult:
    """Real-shape RevocationResult: the production binding reads only
    ``revoked_agents``. Frozen so the test cannot mutate it post-construction."""

    revoked_agents: list[str]
    success: bool = True


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
# Async-store path — the F10 fix: honest typed error, NEVER silent-empty
# ---------------------------------------------------------------------------


class TestAsyncStoreHonestDefer:
    async def test_async_store_raises_typed_error_not_silent_empty(
        self, real_trust_store: TrustStoreAdapter
    ) -> None:
        """The only real backing store is async. Driving it from the sync
        Protocol method MUST raise the typed error — NOT return an empty set
        (the pre-fix bug, which silently violated EC-8(c))."""
        runtime = KailashPyRuntime(trust_store=real_trust_store)
        with pytest.raises(Phase02SubstrateNotWiredError) as exc_info:
            runtime.trust_cascade_revoke("agent-root")
        msg = str(exc_info.value)
        # The error names the sync<->async bridge as the Phase-02 substrate.
        assert "async" in msg
        assert "specs/runtime-abstraction.md" in msg

    async def test_async_store_does_not_leak_unawaited_coroutine_warning(
        self, real_trust_store: TrustStoreAdapter
    ) -> None:
        """Regression guard: the pre-fix code called the async ``revoke``
        without awaiting it, leaking a 'coroutine was never awaited'
        RuntimeWarning at GC. The fix closes the coroutine before raising."""
        runtime = KailashPyRuntime(trust_store=real_trust_store)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pytest.raises(Phase02SubstrateNotWiredError):
                runtime.trust_cascade_revoke("agent-root")
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
