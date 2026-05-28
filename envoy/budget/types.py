# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.budget.types — value objects for the multi-window Budget tracker.

Per `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md`
§ 4 (class structure sketch). These are the Envoy-new-code value objects that
compose around the upstream `kailash.trust.constraints.budget_tracker`
primitives (`BudgetTracker`, `BudgetSnapshot`, `BudgetEvent`).

Frozen dataclasses per `rules/zero-tolerance.md` Rule 3a — the structured
carriers MUST NOT be mutated by callers after construction.

Source spec: `specs/budget-tracker.md` § Data unit (integer microdollars,
no float accumulation) + § Ceilings (five windows).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # pragma: no cover - typing only
    from kailash.trust.constraints.budget_tracker import BudgetSnapshot

__all__ = [
    "WindowName",
    "WINDOW_NAMES",
    "WindowCeilings",
    "ReservationHandle",
    "EnvoyBudgetEvent",
    "MultiWindowSnapshot",
    "new_reservation_id",
    "INT64_MAX",
]

# The five financial-dimension ceiling windows per `specs/budget-tracker.md`
# § Ceilings (lines 17-23). Order is the reserve/record consultation order.
WindowName = Literal[
    "per_call",
    "per_session",
    "per_hour_velocity",
    "per_day",
    "per_month",
]

WINDOW_NAMES: tuple[WindowName, ...] = (
    "per_call",
    "per_session",
    "per_hour_velocity",
    "per_day",
    "per_month",
)

# Cross-SDK contract bound per `specs/budget-tracker.md` line 56
# (`MicrodollarOverflowError`). Upstream Python `int` is unbounded; Envoy
# validates against the signed 64-bit ceiling so the Rust binding (Phase 02)
# and the Python path agree on the overflow boundary.
INT64_MAX: int = 2**63 - 1


def new_reservation_id() -> str:
    """Return a time-ordered opaque reservation id (UUIDv7-style).

    Python 3.13 has no `uuid.uuid7`; this produces the same sortable shape —
    a 48-bit millisecond timestamp prefix followed by 80 random bits, hex —
    so reservation ids sort by creation time without a 3.14 dependency. The
    id is opaque to callers; only uniqueness + sortability are load-bearing.
    """
    ms = int(time.time() * 1000)
    return f"{ms:012x}{os.urandom(10).hex()}"


@dataclass(frozen=True, slots=True)
class WindowCeilings:
    """Five financial-dimension ceilings extracted from `EffectiveEnvelope.financial`.

    Source: `specs/envelope-model.md` § Financial dimension; consumed at
    session start by `EnvoyBudgetOrchestrator` to construct the five
    per-window `BudgetTracker` instances. All values are integer microdollars
    (1 dollar = 1,000,000 microdollars) per `specs/budget-tracker.md`
    § Data unit.
    """

    per_call_ceiling_microdollars: int
    per_session_ceiling_microdollars: int
    per_hour_velocity_microdollars: int
    per_day_ceiling_microdollars: int
    per_month_ceiling_microdollars: int

    def ceiling_for(self, window: WindowName) -> int:
        """Return the microdollar ceiling for `window`."""
        return {
            "per_call": self.per_call_ceiling_microdollars,
            "per_session": self.per_session_ceiling_microdollars,
            "per_hour_velocity": self.per_hour_velocity_microdollars,
            "per_day": self.per_day_ceiling_microdollars,
            "per_month": self.per_month_ceiling_microdollars,
        }[window]


@dataclass(frozen=True, slots=True)
class ReservationHandle:
    """Opaque handle returned by `reserve_for_call`; consumed by `record_for_call`.

    Per design § 3.2 item 3. `reservation_id` is the idempotency key tracked
    in the orchestrator's `_recorded_reservations` set — a second
    `record_for_call` with the same id raises `ReservationDoubleRecordError`
    (`specs/budget-tracker.md` line 57), which is the structural defense
    against EC-8 cross-channel double-billing (`02-mvp-objectives.md`
    line 117 / line 460 of the implementation doc).
    """

    reservation_id: str
    intent_id: str
    reserved_microdollars: int
    reserved_per_window: dict[WindowName, int]
    expires_at: datetime
    ceilings_consulted: list[WindowName]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EnvoyBudgetEvent:
    """Extends the upstream `BudgetEvent` with principal/window/period dimensions.

    Composition, NOT subclassing, per design § 3.3. `principal_id` is held in
    memory only; it is redacted to a `sha256:`-prefixed form by `LedgerEmitter`
    before any Ledger write (`rules/event-payload-classification.md` Rule 1/2).
    """

    principal_id: str
    window: WindowName
    period_key: str
    threshold_pct: float
    committed_microdollars: int
    reserved_microdollars: int
    allocated_microdollars: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class MultiWindowSnapshot:
    """All five windows snapshotted at one instant per design § 4."""

    per_call: BudgetSnapshot
    per_session: BudgetSnapshot
    per_hour_velocity: BudgetSnapshot
    per_day: BudgetSnapshot
    per_month: BudgetSnapshot
    captured_at: datetime

    def snapshot_for(self, window: WindowName) -> BudgetSnapshot:
        """Return the `BudgetSnapshot` for `window`."""
        return {
            "per_call": self.per_call,
            "per_session": self.per_session,
            "per_hour_velocity": self.per_hour_velocity,
            "per_day": self.per_day,
            "per_month": self.per_month,
        }[window]
