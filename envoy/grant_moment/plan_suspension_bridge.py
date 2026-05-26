"""envoy.grant_moment.plan_suspension_bridge — typed event channel.

Per `workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
§ 3 step 7: "typed-event channel between Boundary Conversation (T-02-43)
and Grant Moment."

The Boundary Conversation runtime can suspend at S8 (Shamir ritual
incomplete) per ``envoy.boundary_conversation.runtime``; the Grant
Moment runtime needs a typed event surface to know that a Boundary
Conversation in flight has paused so it can defer dispatching new
Grant Moments OR re-enable them on resume.

The upstream suspension primitive is
``kaizen.l3.plan.suspension.SuspensionRecord``; this bridge does NOT
re-import it (the bridge surface is a typed-event dispatcher decoupled
from the kaizen shape — both directions need the same channel without
either side depending on the other's record type).

Idempotency: replay safety per spec cross-reference to
``specs/ledger.md`` § two-phase signing — the same ``(kind, ritual_id)``
event delivered twice is a NOOP. This mirrors the ``intent_id`` /
``nonce`` defense in the Grant Moment Request signing path.

Thread-safety is NOT a Phase-01 concern (single-threaded asyncio
runtime); subscribers are called synchronously in registration order.

This module is pure Python; ZERO dependencies on other envoy packages
and ZERO dependencies on kaizen or upstream suspension primitives.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "PlanSuspensionEventKind",
    "PlanSuspensionEvent",
    "Subscriber",
    "PlanSuspensionBridge",
]


class PlanSuspensionEventKind(str, Enum):
    """Typed-event discriminator for plan-suspension fan-out.

    The four kinds form two pairs:

    - BOUNDARY_CONVERSATION_PAUSED / BOUNDARY_CONVERSATION_RESUMED — emitted
      by the Boundary Conversation runtime when its plan suspends/resumes
      (S8 Shamir-ritual pause is the Phase-01 trigger).

    - GRANT_MOMENT_QUEUE_HOLD_REQUESTED / GRANT_MOMENT_QUEUE_RESUME_REQUESTED
      — emitted by the Grant Moment dispatch surface when it wants the
      queue paused/resumed (for example, while a Boundary Conversation
      re-pair completes after a VisibleSecretMismatchError).

    Subclassing ``str`` keeps the enum JSON-serializable for ledger /
    telemetry surfaces without a custom encoder.
    """

    BOUNDARY_CONVERSATION_PAUSED = "boundary_conversation_paused"
    BOUNDARY_CONVERSATION_RESUMED = "boundary_conversation_resumed"
    GRANT_MOMENT_QUEUE_HOLD_REQUESTED = "grant_moment_queue_hold_requested"
    GRANT_MOMENT_QUEUE_RESUME_REQUESTED = "grant_moment_queue_resume_requested"


@dataclass(frozen=True, slots=True)
class PlanSuspensionEvent:
    """Typed event payload fan-out across the bridge.

    Fields:

    - ``kind``: discriminator from ``PlanSuspensionEventKind``.
    - ``ritual_id``: the boundary conversation ``ritual_id`` (for
      BOUNDARY_CONVERSATION_* kinds) OR the grant moment ``session_id``
      (for GRANT_MOMENT_QUEUE_* kinds). Identity field for idempotency
      dedupe per spec § replay safety.
    - ``emitted_at``: ISO-8601 timestamp. Recorded for ledger entries +
      operator triage; NOT used in idempotency dedupe (the same logical
      event re-emitted at a later time MUST still NOOP).
    - ``reason``: plain-language description; consumed by UX surfaces
      per `rules/communication.md`.
    - ``resume_context``: free-form dict carrying handoff data the
      receiver may need (e.g. the kaizen ``SuspensionRecord``'s
      ``resume_context`` field, or a Grant Moment queue depth).
    """

    kind: PlanSuspensionEventKind
    ritual_id: str
    emitted_at: str
    reason: str
    resume_context: dict[str, Any] = field(default_factory=dict)


Subscriber = Callable[[PlanSuspensionEvent], None]


class PlanSuspensionBridge:
    """Typed-event fan-out with idempotency dedupe + per-subscriber
    failure capture.

    Subscribe/unsubscribe + emit-with-failure-capture is the typed
    event-channel pattern. Subscribers raising do NOT prevent siblings
    from receiving; the exception is captured into a per-emit failure
    list available via ``last_failures()``.

    Idempotency dedupe key is ``(event.kind, event.ritual_id)`` — replay
    safety guarantees same event delivered twice is a NOOP per spec
    cross-reference to ``specs/ledger.md`` § two-phase signing.

    ``emit`` returns the count of NEW (subscriber-successful) deliveries;
    returns 0 on duplicate event OR when every subscriber raised.

    Subscribe with same callable twice → ValueError; unsubscribe with
    unknown callable → KeyError. Per `rules/zero-tolerance.md` Rule 3a
    — typed exceptions, not silent overwrites / silent no-ops.
    """

    def __init__(self) -> None:
        # Subscribers held in registration order; sync delivery preserves
        # that ordering (test asserts this explicitly).
        self._subscribers: list[Subscriber] = []
        # Idempotency dedupe key per spec § replay safety. Set per
        # bridge-instance lifetime; production lifetime is the runtime's
        # asyncio loop scope.
        self._delivered_event_keys: set[tuple[str, str]] = set()
        # Failures from the most recent emit() call. Reset on EVERY emit.
        self._last_failures: list[tuple[Subscriber, Exception]] = []

    def subscribe(self, subscriber: Subscriber) -> None:
        """Register a subscriber; raise ValueError on duplicate registration.

        Identity dedupe (``is``-equality via ``in``): the same callable
        cannot register twice. This prevents accidental double-delivery
        when a subsystem re-runs its setup path.
        """
        if subscriber in self._subscribers:
            raise ValueError(
                "subscriber already registered; cannot subscribe the same " "callable twice"
            )
        self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Remove a subscriber; raise KeyError if not registered.

        KeyError (not ValueError) so callers can distinguish "wrong
        registration state" from the subscribe-side "duplicate
        registration" failure mode.
        """
        if subscriber not in self._subscribers:
            raise KeyError(
                "subscriber not registered; cannot unsubscribe a callable "
                "that was never subscribe()'d"
            )
        self._subscribers.remove(subscriber)

    def emit(self, event: PlanSuspensionEvent) -> int:
        """Fan-out the event to every subscriber.

        Returns the count of subscribers that successfully received.

        Idempotency: if ``(event.kind, event.ritual_id)`` was already
        delivered, NOOP — return 0 without re-fanning-out. Subscribers
        that raise are caught; the exception is captured into the
        per-emit failure list available via ``last_failures()``.
        Subscribers are called synchronously in registration order.
        """
        # Reset failure list on every emit per the contract documented
        # in last_failures(). Done BEFORE the dedupe check so even a
        # NOOP emit clears the prior call's failures (the caller's
        # follow-up last_failures() call reflects THIS emit, not the
        # previous one).
        self._last_failures = []

        # `kind` is an Enum subclass of str — its .value is the
        # underlying string, which is the stable dedupe key (an enum
        # member reference would still dedupe correctly, but .value
        # round-trips through JSON / ledger / persistence layers).
        dedupe_key = (event.kind.value, event.ritual_id)
        if dedupe_key in self._delivered_event_keys:
            return 0

        # Mark BEFORE fan-out so a subscriber that re-emits the same
        # event recursively (pathological but possible) cannot infinite-
        # loop. Once marked, the event is considered "delivered" even
        # if every subscriber raises — replay safety per spec § two-
        # phase signing trumps delivery completeness.
        self._delivered_event_keys.add(dedupe_key)

        successful_deliveries = 0
        for subscriber in self._subscribers:
            try:
                subscriber(event)
                successful_deliveries += 1
            except Exception as exc:  # noqa: BLE001 — see docstring
                # Per-subscriber failure isolation is the documented
                # contract — sibling subscribers MUST still receive
                # even when one raises. The exception is captured
                # into _last_failures (NOT silently swallowed per
                # rules/zero-tolerance.md Rule 3 — the structured
                # carrier IS the visible action).
                self._last_failures.append((subscriber, exc))
        return successful_deliveries

    def last_failures(self) -> tuple[tuple[Subscriber, Exception], ...]:
        """Return the (subscriber, exception) tuples from the most recent
        ``emit()`` call. Reset on each ``emit()``.

        Returned as a tuple (immutable) so callers cannot mutate the
        bridge's internal record by appending to a returned list.
        """
        return tuple(self._last_failures)
