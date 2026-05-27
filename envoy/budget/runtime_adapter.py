# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.budget.runtime_adapter — runtime-abstraction surface for the Budget tracker.

Per `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md`
§ 3.2 item 9. Implements the public runtime contract
(`specs/runtime-abstraction.md` § `budget_reserve/record/snapshot/
velocity_check`) by wrapping `EnvoyBudgetOrchestrator`, so the runtime
substitution boundary (`envoy.runtime.adapters.kailash_py.KailashPyRuntime`)
can delegate the four budget protocol methods to a real implementation —
removing the Phase02-stub `Phase02SubstrateNotWiredError` they previously
raised.

This is the production hot-path landing required by `rules/orphan-detection.md`
Rule 1: the orchestrator is reached through the runtime budget surface that
the Kaizen tool-dispatch interceptor calls (design § 4 order-of-operations:
`budget_reserve` → tool execute → `budget_record`).

The runtime protocol budget methods are SYNC (`specs/runtime-abstraction.md`);
the orchestrator's reserve/record accounting is sync too, so the adapter is a
thin faithful forward. Ledger emission of `budget_reservation_record` is
buffered on the injected `LedgerEmitter` and flushed by the async hot path
(or a Tier-2 test) via `await ledger_emitter.drain()` — the adapter does not
itself await (it stays on the sync protocol surface).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from envoy.budget.types import ReservationHandle, new_reservation_id
from envoy.runtime.errors import BudgetVelocityExceededError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from kailash.trust.constraints.budget_tracker import BudgetCheckResult

    from envoy.budget.orchestrator import EnvoyBudgetOrchestrator
    from envoy.budget.types import MultiWindowSnapshot

__all__ = ["BudgetRuntimeAdapter", "UnknownReservationError"]


class UnknownReservationError(KeyError):
    """`budget_record` was called with a reservation id the adapter never issued.

    Typed (not a bare `KeyError` from a dict lookup) per `rules/zero-tolerance.md`
    Rule 3a — the caller gets an actionable message instead of an opaque miss.
    """

    def __init__(self, reservation_id: str) -> None:
        self.reservation_id = reservation_id
        super().__init__(
            f"no in-flight reservation with id {reservation_id!r} — it was never "
            "issued by this runtime, or was already recorded/expired"
        )


class BudgetRuntimeAdapter:
    """Adapts `EnvoyBudgetOrchestrator` to the runtime-abstraction budget contract.

    Phase-01 single-session: the adapter is bound to one orchestrator (one
    principal + session). The protocol's `session` parameter is advisory — the
    orchestrator already owns its `session_id`; the adapter does not multiplex
    sessions in Phase 01 (Phase 03 multi-principal adds a session→orchestrator
    map at this layer).
    """

    def __init__(self, *, orchestrator: EnvoyBudgetOrchestrator) -> None:
        self._orchestrator = orchestrator
        # reservation_id -> handle, for the record() lookup (the protocol passes
        # back the opaque ReservationID returned by reserve()).
        self._inflight: dict[str, ReservationHandle] = {}

    def budget_reserve(self, session: Any, cost: int) -> str:
        """Reserve `cost` microdollars; return the opaque ReservationID.

        `session` is advisory in Phase 01 (single-session). A fresh `intent_id`
        is minted per reserve to key the per_call window; it is prefixed `rt:`
        to mark a runtime-adapter-generated intent (vs a two-phase-signed
        Phase-A intent).
        """
        intent_id = f"rt:{new_reservation_id()}"
        handle = self._orchestrator.reserve_for_call(cost, intent_id=intent_id)
        self._inflight[handle.reservation_id] = handle
        return handle.reservation_id

    def budget_record(self, reservation: Any, actual: int) -> None:
        """Finalize the reservation identified by `reservation` (a ReservationID)."""
        handle = self._inflight.pop(str(reservation), None)
        if handle is None:
            raise UnknownReservationError(str(reservation))
        self._orchestrator.record_for_call(handle, actual)

    def budget_snapshot(self, session: Any) -> MultiWindowSnapshot:
        """Return the five-window snapshot (integer microdollars per window)."""
        return self._orchestrator.snapshot()

    def budget_velocity_check(self, session: Any) -> BudgetCheckResult:
        """Check the per-hour velocity window; raise if its ceiling is breached.

        Per the runtime protocol docstring: raises `BudgetVelocityExceededError`
        when the velocity ceiling is breached. A zero-cost `check` against the
        binding window returns the current headroom without mutating state.
        """
        snapshot = self._orchestrator.snapshot()
        velocity = snapshot.per_hour_velocity
        if velocity.committed >= velocity.allocated:
            raise BudgetVelocityExceededError(
                f"per-hour velocity ceiling breached: {velocity.committed} of "
                f"{velocity.allocated} microdollars committed this hour"
            )
        return self._orchestrator.check(0, intent_id="velocity_check")
