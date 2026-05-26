"""envoy.grant_moment.state_machine — the M0→M4 state machine.

Implements the state machine frozen in `specs/grant-moment.md` § State machine:

    M0 construct → M1 render (all active channels) → M2 await decision
    (5min default timeout; per-envelope override) → M3 sign or decline
    → M4 complete.

The state machine is the *structural* skeleton — which transitions are
allowed and which events drive them. The runtime layer (later shards: T-03-51
``ChannelHandoff``, T-03-52 ``CascadeRevocationOrchestrator``,
``EnvoyGrantMomentRuntime`` facade) supplies the *semantic* dispatch (LLM
extraction, channel I/O, signature checks).

Per `rules/agent-reasoning.md`: this module performs ZERO classification or
keyword routing — the structural state machine (which state is next given
an event) is permitted deterministic plumbing.

This module is pure Python; ZERO dependencies on other envoy packages
besides ``envoy.grant_moment.errors``.
"""

from __future__ import annotations

from enum import Enum

from envoy.grant_moment.errors import InvalidGrantMomentTransitionError

__all__ = [
    "GRANT_MOMENT_TRANSITIONS",
    "GrantMomentState",
    "GrantMomentEvent",
    "next_state",
]


class GrantMomentState(str, Enum):
    """The five canonical states (M0..M4) per spec § State machine.

    Inherits from ``str`` so values flow through JSON wire shapes and log
    lines as their declared names ("M0_construct", etc.) without an explicit
    ``.value`` access. Per `rules/cc-artifacts.md`, enum naming uses the
    spec-frozen lexicon — node-id prefixes match the spec's "M0..M4" + the
    state's verb.
    """

    M0_CONSTRUCT = "M0_construct"
    M1_RENDER = "M1_render"
    M2_AWAIT = "M2_await"
    M3_SIGN = "M3_sign"
    M4_COMPLETE = "M4_complete"


class GrantMomentEvent(str, Enum):
    """The discrete events that drive M0→M4 transitions.

    These are the structural transition triggers. They are NOT the spec's
    four ``decision`` values (those live in `envoy.grant_moment.resolution`
    and arrive *with* the ``decision_received`` event). The runtime decides
    which decision shape was returned and what consequences follow; the
    state machine cares only that *some* decision arrived.
    """

    DISPATCH_TO_CHANNELS = "dispatch_to_channels"  # M0 → M1
    RENDERED_AND_AWAITING = "rendered_and_awaiting"  # M1 → M2
    DECISION_RECEIVED = "decision_received"  # M2 → M3
    TIMEOUT_EXPIRED = "timeout_expired"  # M2 → M3 (with deny disposition)
    SIGNATURE_FINALIZED = "signature_finalized"  # M3 → M4


# Transition table: (current_state, event) → next_state.
# Any (state, event) pair NOT in this table raises
# ``InvalidGrantMomentTransitionError`` — the state machine is strict;
# bypass paths (M0 → M3 directly, M4 → anything) are structurally forbidden.
#
# Note on M2 → M3 dual entry: both ``DECISION_RECEIVED`` and
# ``TIMEOUT_EXPIRED`` route to M3. M3 then signs or declines per the
# disposition the runtime computed (decision payload, or auto-deny on timeout).
GRANT_MOMENT_TRANSITIONS: dict[tuple[GrantMomentState, GrantMomentEvent], GrantMomentState] = {
    (GrantMomentState.M0_CONSTRUCT, GrantMomentEvent.DISPATCH_TO_CHANNELS): (
        GrantMomentState.M1_RENDER
    ),
    (GrantMomentState.M1_RENDER, GrantMomentEvent.RENDERED_AND_AWAITING): (
        GrantMomentState.M2_AWAIT
    ),
    (GrantMomentState.M2_AWAIT, GrantMomentEvent.DECISION_RECEIVED): (GrantMomentState.M3_SIGN),
    (GrantMomentState.M2_AWAIT, GrantMomentEvent.TIMEOUT_EXPIRED): (GrantMomentState.M3_SIGN),
    (GrantMomentState.M3_SIGN, GrantMomentEvent.SIGNATURE_FINALIZED): (
        GrantMomentState.M4_COMPLETE
    ),
}


def next_state(
    current: GrantMomentState,
    event: GrantMomentEvent,
) -> GrantMomentState:
    """Resolve ``(current, event) → next`` against the transition table.

    Raises ``InvalidGrantMomentTransitionError`` when no transition is
    declared for the pair — the strict-table design means the only way
    to extend the machine is to add an entry to ``GRANT_MOMENT_TRANSITIONS``.
    """
    try:
        return GRANT_MOMENT_TRANSITIONS[(current, event)]
    except KeyError:
        raise InvalidGrantMomentTransitionError(
            current_state=current.value,
            attempted_event=event.value,
        ) from None
