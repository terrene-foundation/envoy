# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared builders for the envoy.budget test suite (shard 12).

Per `rules/testing.md` § Tier 2: real `SQLiteBudgetStore` / `InMemoryAuditStore`
/ `InMemoryKeyManager` / `EnvoyLedger` — NO mocking at the binding boundary.
These builders construct the real composition so each test file stays focused
on the behavior under test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.budget import (
    AnomalyDetector,
    BudgetRuntimeAdapter,
    EnvoyBudgetOrchestrator,
    LedgerEmitter,
    ThresholdDispatcher,
    WindowCeilings,
)
from envoy.ledger import EnvoyLedger


def no_op_anomaly_detector() -> AnomalyDetector:
    """An AnomalyDetector tuned never to fire — isolates ceiling / threshold /
    isolation tests from the single-call >50%-of-session anomaly path (which has
    its own dedicated coverage in `test_t093_budget_exhaustion_fraud`)."""
    # Unreachable threshold (1e18 × remaining always exceeds any int64 estimate)
    # so the single-call anomaly never fires; velocity_count 10**9 → burst never
    # triggers. Isolates ceiling / threshold / isolation behavior under test.
    return AnomalyDetector(
        single_call_session_pct_threshold=1e18,
        velocity_count_threshold=10**9,
    )


ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
SIGNING_KEY_ID = "envoy-budget-test-key"
DEVICE_ID = "device-budget-test"

# Default ceilings sized so each window can be exercised independently:
# per_call < per_hour < per_session < per_day < per_month.
DEFAULT_CEILINGS = WindowCeilings(
    per_call_ceiling_microdollars=1_000_000,
    per_session_ceiling_microdollars=10_000_000,
    per_hour_velocity_microdollars=5_000_000,
    per_day_ceiling_microdollars=50_000_000,
    per_month_ceiling_microdollars=1_000_000_000,
)


class Clock:
    """Mutable injectable clock for deterministic time control in tests."""

    def __init__(self, at: datetime | None = None) -> None:
        self._now = at or datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        self._now = at

    def advance(self, **kwargs: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(**kwargs)


async def build_ledger() -> EnvoyLedger:
    """A real EnvoyLedger backed by InMemory audit store + key manager."""
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(SIGNING_KEY_ID)
    return EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=mgr,
        signing_key_id=SIGNING_KEY_ID,
        device_id=DEVICE_ID,
        algorithm_identifier=ALGO_ID,
    )


@dataclass
class BudgetHarness:
    """Bundle of the wired budget composition for a test."""

    orchestrator: EnvoyBudgetOrchestrator
    ledger: EnvoyLedger
    emitter: LedgerEmitter
    dispatcher: ThresholdDispatcher
    clock: Clock
    store: InMemoryAuditStore


async def build_harness(
    *,
    ceilings: WindowCeilings = DEFAULT_CEILINGS,
    principal_id: str = "alice",
    session_id: str = "session-1",
    reservation_ttl_seconds: int = 60,
    classification_policy: object | None = None,
    on_grant_moment: object | None = None,
    anomaly_detector: AnomalyDetector | None = None,
) -> BudgetHarness:
    """Construct a fully-wired orchestrator + ledger + emitter + dispatcher."""
    clock = Clock()
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(SIGNING_KEY_ID)
    store = InMemoryAuditStore()
    ledger = EnvoyLedger(
        audit_store=store,
        key_manager=mgr,
        signing_key_id=SIGNING_KEY_ID,
        device_id=DEVICE_ID,
        algorithm_identifier=ALGO_ID,
    )
    emitter = LedgerEmitter(ledger=ledger, classification_policy=classification_policy)
    dispatcher = ThresholdDispatcher(ledger_emitter=emitter, on_grant_moment=on_grant_moment)  # type: ignore[arg-type]
    orchestrator = EnvoyBudgetOrchestrator(
        ceilings=ceilings,
        store=None,
        principal_id=principal_id,
        session_id=session_id,
        clock=clock,
        reservation_ttl_seconds=reservation_ttl_seconds,
        anomaly_detector=anomaly_detector,
        ledger_emitter=emitter,
        threshold_sink=dispatcher,
    )
    return BudgetHarness(
        orchestrator=orchestrator,
        ledger=ledger,
        emitter=emitter,
        dispatcher=dispatcher,
        clock=clock,
        store=store,
    )


def runtime_adapter(orchestrator: EnvoyBudgetOrchestrator) -> BudgetRuntimeAdapter:
    """Wrap an orchestrator in the runtime-abstraction adapter."""
    return BudgetRuntimeAdapter(orchestrator=orchestrator)
