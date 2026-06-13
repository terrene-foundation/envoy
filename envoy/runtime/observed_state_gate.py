# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.observed_state_gate — store-wired SessionObservedState gate (WS-6 S5o).

The orchestration layer that wires the PURE gate semantics
(``envoy.runtime.observed_state``) to the durable Region-2 store
(``envoy.runtime.session.SessionRouter``). Kept SEPARATE from the pure module so
the runtime adapters (which delegate to the pure ``first_time_action_gate``)
never transitively import the keystore / SQLite / ledger machinery the store
pulls in — the byte-identical adapter path stays I/O-free.

Responsibilities (the "Wire" half of S5o):

- ``evaluate`` — load the session's observed-state blob from Region-2, enforce the
  goal-reconfirmation threshold, run the pure gate, and persist when the gate
  recorded a pre-authorized-pattern match (so the next identical call is a plain
  cache hit). Returns the ``GateResult``.
- ``observe`` — record a tool-call observation (the fingerprint write that makes a
  repeated call RECOGNIZED) and snapshot it to the durable region. This is the
  "snapshot at every Ledger append" crash-safety write
  (``specs/session-state.md`` § Persistence).
- ``reconfirm`` — reset the goal-reconfirmation counter (user reconfirmed goal
  alignment) and persist.

The T-013 boundary RESET is NOT re-implemented here:
``envoy.runtime.session_boundary.SessionBoundarySignal.cross()`` already applies
``reset_session_observed_state`` to the durable region on an END transition. S5o
CONSUMES that signal — the integration is proven (no duplicate reset logic) by
the shared invariant at ``tests/support/t013.py``: after a boundary crossing,
``evaluate`` on a previously-RECOGNIZED fingerprint returns
FIRST_TIME_REQUIRES_GRANT.

Explicit dependency injection per ``rules/facade-manager-detection.md`` Rule 3:
the ``SessionRouter`` is passed in — no global lookup, no self-constructed
parallel store.
"""

from __future__ import annotations

import json
from typing import Any

from envoy.ledger.canonical import canonical_dumps
from envoy.runtime.observed_state import (
    GateResult,
    check_goal_reconfirmation,
    fingerprint,
    first_time_action_gate,
    reconfirm_goal,
    record_observation,
)
from envoy.runtime.session import SessionRouter
from envoy.runtime.session_boundary import is_recognized_fingerprint

__all__ = ["SessionObservedStateGate"]


class SessionObservedStateGate:
    """Store-backed first-time-action gate over the durable SessionObservedState
    region.

    Construct with a ``SessionRouter`` whose ``open()`` has been awaited (the gate
    reads/writes Region-2 through it). All methods are ``async`` because the store
    surface is async.
    """

    def __init__(self, *, router: SessionRouter) -> None:
        self._router = router

    async def _load_or_raise(self, session_id: str) -> dict[str, Any]:
        """Load the session's observed-state blob, or raise if none exists.

        A session ALWAYS has an observed-state blob once ``init`` (S4i) has written
        the genesis. A missing blob means the gate was invoked for a session that
        never started — a programming error, surfaced loudly rather than silently
        treating every call as first-time.
        """
        raw = await self._router.load_observed_state(session_id)
        if raw is None:
            raise RuntimeError(
                f"no SessionObservedState for session_id {session_id!r}; a session "
                "genesis (envoy init / session start) must write the observed-state "
                "region before the first-time-action gate can evaluate"
            )
        blob: dict[str, Any] = json.loads(raw)
        return blob

    async def _persist(self, session_id: str, blob: dict[str, Any]) -> None:
        await self._router.snapshot_observed_state(
            session_id=session_id,
            state_json=canonical_dumps(blob).decode("utf-8"),
        )

    async def evaluate(
        self,
        *,
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> GateResult:
        """Gate a tool call against the durable session state.

        Order (``specs/session-state.md`` § Algorithm + § Error taxonomy):

        1. Enforce the goal-reconfirmation threshold (raises
           ``GoalReconfirmationThresholdExceededError`` when due — the next tool
           call is held until the user reconfirms).
        2. Run the pure ``first_time_action_gate``: RECOGNIZED on a fingerprint
           cache-hit or a pre-authorized-pattern match; else
           FIRST_TIME_REQUIRES_GRANT.
        3. If the gate recorded a NEW pre-authorized-pattern match (RECOGNIZED for a
           fingerprint that was NOT previously cached), persist the updated blob so
           the next identical call is a plain cache hit.

        The fingerprint cache-hit and first-time branches are read-only (no write).
        """
        blob = await self._load_or_raise(session_id)
        check_goal_reconfirmation(blob)

        fp_key = fingerprint(tool_name, args)
        was_cached = is_recognized_fingerprint(blob, fp_key)
        result = first_time_action_gate(blob, tool_name, args)

        if result is GateResult.RECOGNIZED and not was_cached:
            # The only way RECOGNIZED arises for a non-cached fingerprint is a
            # pre-authorized-pattern match, which the pure gate recorded into the
            # blob — persist so the recognition survives + the next call is a hit.
            await self._persist(session_id, blob)
        return result

    async def observe(
        self,
        *,
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
        outcome: str = "success",
    ) -> dict[str, Any]:
        """Record a tool-call observation and snapshot it to the durable region.

        The fingerprint write that makes a repeated call RECOGNIZED on its next
        ``evaluate`` — invoked when a first-time action is approved/executed AND on
        every subsequent recognized call. Increments the goal-reconfirmation
        counter. Returns the persisted blob.
        """
        blob = await self._load_or_raise(session_id)
        updated = record_observation(blob, tool_name, args, outcome=outcome)
        await self._persist(session_id, updated)
        return updated

    async def reconfirm(self, *, session_id: str) -> dict[str, Any]:
        """Reset the goal-reconfirmation counter (user reconfirmed goal alignment)
        and persist. Returns the persisted blob."""
        blob = await self._load_or_raise(session_id)
        updated = reconfirm_goal(blob)
        await self._persist(session_id, updated)
        return updated
