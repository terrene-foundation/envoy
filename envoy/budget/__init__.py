# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.budget — multi-window financial-constraint enforcement (shard 12).

The financial-constraint-dimension owner per `02-mvp-objectives.md` § 3
cross-cutting deliverables. Composes the upstream
`kailash.trust.constraints.budget_tracker.BudgetTracker` +
`budget_store.SQLiteBudgetStore` primitives into the five-window ceiling +
reset-boundary + threshold-callback → Grant Moment contract frozen in
`specs/budget-tracker.md`.

Framework-first (`rules/framework-first.md` + `rules/zero-tolerance.md`
Rule 4): the integer-microdollar arithmetic, rising-edge one-shot threshold
predicate, saturating subtract, and `SQLiteBudgetStore` persistence are
UPSTREAM; this package composes them and adds the Envoy-new-code surface
(multi-window decomposition, reset scheduler, anomaly detection, Ledger
emission, Grant Moment dispatch) per design § 2.4 + § 3.

Public surface
--------------

- :class:`EnvoyBudgetOrchestrator` — the single facade (`rules/facade-manager-detection.md`).
- :class:`WindowCeilings`, :class:`ReservationHandle`, :class:`EnvoyBudgetEvent`,
  :class:`MultiWindowSnapshot` — value objects (`specs/budget-tracker.md` § Data unit).
- :class:`BudgetResetScheduler` — pure period-key derivation (Phase-01 UTC).
- :class:`AnomalyDetector` — T-093 fraud defense.
- :class:`ThresholdDispatcher` — async threshold-cross → Grant Moment queue.
- :class:`LedgerEmitter` — single-point classified Ledger emission.
- :class:`BudgetRuntimeAdapter` — runtime-abstraction contract impl.
- Error taxonomy (`EnvoyBudgetError` base + 7 typed errors per
  `specs/budget-tracker.md` § Error taxonomy).
"""

from __future__ import annotations

from envoy.budget.anomaly_detector import AnomalyDetector
from envoy.budget.errors import (
    AnomalyDetectedError,
    BudgetExhaustedError,
    EnvoyBudgetError,
    HighVelocityPatternError,
    MicrodollarOverflowError,
    ReservationDoubleRecordError,
    ReservationExpiredError,
    VelocityRaiseInlineBlockError,
)
from envoy.budget.ledger_emitter import LedgerEmitter
from envoy.budget.orchestrator import EnvoyBudgetOrchestrator, MultiWindowBudget
from envoy.budget.reset_scheduler import BudgetResetScheduler
from envoy.budget.runtime_adapter import BudgetRuntimeAdapter, UnknownReservationError
from envoy.budget.threshold_dispatcher import ThresholdDispatcher
from envoy.budget.types import (
    WINDOW_NAMES,
    EnvoyBudgetEvent,
    MultiWindowSnapshot,
    ReservationHandle,
    WindowCeilings,
    WindowName,
    new_reservation_id,
)

__all__ = [
    # facade
    "EnvoyBudgetOrchestrator",
    "MultiWindowBudget",
    # value objects
    "WindowCeilings",
    "WindowName",
    "WINDOW_NAMES",
    "ReservationHandle",
    "EnvoyBudgetEvent",
    "MultiWindowSnapshot",
    "new_reservation_id",
    # primitives
    "BudgetResetScheduler",
    "AnomalyDetector",
    "ThresholdDispatcher",
    "LedgerEmitter",
    "BudgetRuntimeAdapter",
    "UnknownReservationError",
    # errors
    "EnvoyBudgetError",
    "BudgetExhaustedError",
    "VelocityRaiseInlineBlockError",
    "AnomalyDetectedError",
    "HighVelocityPatternError",
    "ReservationExpiredError",
    "MicrodollarOverflowError",
    "ReservationDoubleRecordError",
]
