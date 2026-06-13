# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.session_boundary — session-lifecycle boundary signal + T-013 reset (WS-6 S5b).

The SHARED owner of the ``session_boundary_crossed`` signal that S5o (the
observed-state gate) AND S6c (the ``chat`` resident loop) both consume. Owning
it once prevents two shards from independently re-deriving the reset semantics —
a divergence failure per ``rules/specs-authority.md`` Rule 5b.

Phase-01 emitted ``session_boundary_crossed`` ONLY at the Boundary-Conversation
shamir-suspend checkpoint (``envoy/boundary_conversation/runtime.py``), a
ritual-internal marker. This module lands the general SESSION-LIFECYCLE emitter
for ALL SIX triggers under the multi-process model
(``specs/session-state.md`` § session_boundary_crossed line 76 + the
Phase-02 deferral at line 223):

    unlock | cli_start  → transition "start"
    cli_end | idle_timeout | user_lock | channel_disconnect → transition "end"

Two load-bearing pieces, both reused downstream:

1. ``reset_session_observed_state(blob)`` — the T-013 cache-reset CONTRACT
   (``specs/session-state.md`` § "Cache reset on session boundary" line 65).
   Crossing a session boundary clears ``tool_calls_made`` and
   ``goal_reconfirmation.tool_calls_since_reconfirm`` (and drops session-scoped
   ``pre_authorized_patterns``, keeping ``cross_session`` ones — line 61), so the
   first tool call in the next session is first-time-action even if an identical
   call happened minutes earlier in the prior session. Per-session fingerprint
   scope is the structural T-013 composition-aware defense (cross-session state
   injection cannot amortize the first-time-action gate). S5o consumes this when
   it wires the gate; S6c proves a real ``chat`` boundary fires it.

2. ``SessionBoundarySignal`` — the emitter. ``cross()`` derives the boundary
   counts from the prior session's observed-state blob + the store, appends the
   signed ``session_boundary_crossed`` Ledger entry (runtime device key, via the
   ``EnvoyLedger`` envelope), and on an END transition applies the reset to the
   prior session's durable observed-state region.

This module owns the SIGNAL + the reset contract ONLY. The observed-state gate
semantics (fingerprint canonicalization, AST pre-authorized-pattern match,
goal-reconfirmation threshold) are S5o; the resident ``chat`` loop is S6c.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from envoy.ledger.canonical import canonical_dumps
from envoy.runtime.session import SessionRouter

# ── Trigger taxonomy (specs/session-state.md § session_boundary_crossed) ──────
#: Triggers that OPEN a session — emit transition "start".
START_TRIGGERS: frozenset[str] = frozenset({"unlock", "cli_start"})
#: Triggers that CLOSE a session — emit transition "end" AND fire the T-013 reset.
END_TRIGGERS: frozenset[str] = frozenset(
    {"cli_end", "idle_timeout", "user_lock", "channel_disconnect"}
)
#: The full canonical 6-trigger set. A trigger outside this set is a programming
#: error (fail-loud per ``rules/zero-tolerance.md`` Rule 3 — no silent default).
ALL_TRIGGERS: frozenset[str] = START_TRIGGERS | END_TRIGGERS

SESSION_BOUNDARY_ENTRY_TYPE = "session_boundary_crossed"
SESSION_BOUNDARY_SCHEMA_VERSION = "session-boundary/1.0"


def boundary_transition(trigger: str) -> str:
    """Map a trigger to its ``transition`` ("start" | "end").

    Per ``specs/session-state.md`` § Algorithm ``session_boundary``:
    ``"end" if trigger in END_TRIGGERS else "start"``. Raises ``ValueError`` on
    an unknown trigger so a typo never silently defaults to "start".
    """
    if trigger in END_TRIGGERS:
        return "end"
    if trigger in START_TRIGGERS:
        return "start"
    raise ValueError(
        f"unknown session-boundary trigger {trigger!r}; "
        f"expected one of {sorted(ALL_TRIGGERS)}"
    )


def reset_session_observed_state(blob: Any) -> dict[str, Any]:
    """T-013 cache-reset CONTRACT — clear per-session state on a boundary crossing.

    Returns a NEW blob (the input is not mutated) in which:

    - ``tool_calls_made`` → ``{}`` (the fingerprint cache clears).
    - ``goal_reconfirmation.tool_calls_since_reconfirm`` → ``0`` (the
      since-reconfirm counter resets; ``threshold`` + ``last_reconfirmed_at`` are
      preserved).
    - ``pre_authorized_patterns`` → only the ``scope == "cross_session"`` entries
      survive; ``scope: session`` patterns reset (``specs/session-state.md`` line 61).

    Every other field (``schema_version``, ``session_id``,
    ``principal_genesis_id``, ``reasoning_commits``, ``pending_phase_a_orphans``,
    ``envelope_version_at_session_start``, ``posture_at_session_start``, …) is
    carried through unchanged. This is the SHARED contract S5o (gate reset) and
    S6c (chat-boundary reset) both reuse — neither re-derives the field set.

    Raises ``ValueError`` on a non-dict blob (fail-loud; a corrupt blob is a
    programming error, not data — ``rules/zero-tolerance.md`` Rule 3).
    """
    if not isinstance(blob, dict):
        raise ValueError(
            f"reset_session_observed_state expects a dict blob "
            f"(got {type(blob).__name__})"
        )
    reset = dict(blob)
    reset["tool_calls_made"] = {}

    goal = blob.get("goal_reconfirmation")
    if isinstance(goal, dict):
        new_goal = dict(goal)
        new_goal["tool_calls_since_reconfirm"] = 0
        reset["goal_reconfirmation"] = new_goal

    patterns = blob.get("pre_authorized_patterns")
    if isinstance(patterns, list):
        reset["pre_authorized_patterns"] = [
            p
            for p in patterns
            if isinstance(p, dict) and p.get("scope") == "cross_session"
        ]
    return reset


def is_recognized_fingerprint(blob: dict[str, Any], fingerprint_key: str) -> bool:
    """The fingerprint-MEMBERSHIP branch of ``first_time_action_gate``.

    ``specs/session-state.md`` § Algorithm line 120: a tool call is RECOGNIZED
    iff its ``fp_key`` is already in ``tool_calls_made``. This is ONLY the
    membership branch — S5o owns the full gate (the AST pre-authorized-pattern
    match + goal-reconfirmation). It is exported here so the T-013 reset's
    BEHAVIORAL consequence ("a previously-recognized fingerprint is first-time
    again after a boundary") is asserted with the exact same predicate S5o's
    gate uses, not a re-derived one.
    """
    calls = blob.get("tool_calls_made")
    return isinstance(calls, dict) and fingerprint_key in calls


@dataclass(frozen=True, slots=True)
class SessionBoundaryResult:
    """The outcome of one boundary crossing (the emitted entry + derived counts)."""

    entry_id: str
    transition: str
    trigger: str
    tool_call_count_observed: int
    orphan_phase_a_count: int
    unresolved_grants_deferred: int
    #: True iff an END transition applied the T-013 reset to a prior blob.
    reset_applied: bool


class SessionBoundarySignal:
    """Emit ``session_boundary_crossed`` + apply the T-013 reset — the shared
    signal S5o and S6c consume.

    Explicit dependency injection per ``rules/facade-manager-detection.md``
    Rule 3: the ``EnvoyLedger`` (the signed-entry sink) and the ``SessionRouter``
    (the durable observed-state region) are passed in — no global lookup, no
    self-constructed parallel framework.
    """

    def __init__(self, *, ledger: Any, router: SessionRouter) -> None:
        self._ledger = ledger
        self._router = router

    async def cross(
        self,
        *,
        trigger: str,
        session_id_prior: str | None,
        session_id_next: str | None = None,
    ) -> SessionBoundaryResult:
        """Cross a session boundary: emit the signed entry, and on END reset the
        prior session's durable observed-state cache.

        The counts (``tool_call_count_observed`` / ``orphan_phase_a_count`` /
        ``unresolved_grants_deferred``) are derived from the prior session's
        observed-state blob and the store's pending-grant count and captured in
        the Ledger entry BEFORE the reset — so the audit row records the true
        end-of-session counts even though the reset then clears the cache.
        """
        if trigger not in ALL_TRIGGERS:
            raise ValueError(
                f"unknown session-boundary trigger {trigger!r}; "
                f"expected one of {sorted(ALL_TRIGGERS)}"
            )
        transition = boundary_transition(trigger)

        prior_blob: dict[str, Any] | None = None
        if session_id_prior is not None:
            raw = await self._router.load_observed_state(session_id_prior)
            if raw is not None:
                prior_blob = json.loads(raw)

        tool_call_count = len((prior_blob or {}).get("tool_calls_made") or {})
        orphan_count = len((prior_blob or {}).get("pending_phase_a_orphans") or [])
        unresolved = await self._router.count_pending_grants()

        content: dict[str, Any] = {
            "schema_version": SESSION_BOUNDARY_SCHEMA_VERSION,
            "transition": transition,
            "session_id_prior": session_id_prior,
            "session_id_next": session_id_next,
            "trigger": trigger,
            "tool_call_count_observed": tool_call_count,
            "orphan_phase_a_count": orphan_count,
            "unresolved_grants_deferred": unresolved,
        }
        entry_id = await self._ledger.append(
            entry_type=SESSION_BOUNDARY_ENTRY_TYPE, content=content
        )

        # T-013 reset: an END trigger clears the prior session's per-session
        # cache so the next session's first identical tool call is first-time
        # again. The counts above are already captured in the signed entry, so
        # the audit trail keeps the end-of-session totals.
        reset_applied = False
        if (
            transition == "end"
            and session_id_prior is not None
            and prior_blob is not None
        ):
            reset_blob = reset_session_observed_state(prior_blob)
            await self._router.snapshot_observed_state(
                session_id=session_id_prior,
                state_json=canonical_dumps(reset_blob).decode("utf-8"),
            )
            reset_applied = True

        return SessionBoundaryResult(
            entry_id=entry_id,
            transition=transition,
            trigger=trigger,
            tool_call_count_observed=tool_call_count,
            orphan_phase_a_count=orphan_count,
            unresolved_grants_deferred=unresolved,
            reset_applied=reset_applied,
        )


__all__ = [
    "ALL_TRIGGERS",
    "END_TRIGGERS",
    "START_TRIGGERS",
    "SESSION_BOUNDARY_ENTRY_TYPE",
    "SESSION_BOUNDARY_SCHEMA_VERSION",
    "SessionBoundaryResult",
    "SessionBoundarySignal",
    "boundary_transition",
    "is_recognized_fingerprint",
    "reset_session_observed_state",
]
