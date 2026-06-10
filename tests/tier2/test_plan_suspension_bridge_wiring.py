"""Tier 2: PlanSuspensionBridge wiring against real subscriber callables.

Per `rules/testing.md` § Tier 2 + `rules/facade-manager-detection.md` Rule 1:
- Wiring test imports the bridge through its public module surface.
- Subscribers are real Python callables (closures recording deliveries
  into list state); NO ``unittest.mock`` per the Tier 2 contract.
- Asserts externally-observable effects (delivery counts, ordering,
  per-emit failure list, idempotency NOOP).

Covers `workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
§ 3 step 7 invariants for T-03-52:

- subscribe-then-emit fans out to the subscriber.
- multiple subscribers receive in registration order.
- duplicate subscribe raises ValueError.
- unsubscribe with unknown subscriber raises KeyError.
- emit with same (kind, ritual_id) twice → 2nd is NOOP (returns 0).
- subscriber raising does NOT prevent other subscribers from receiving.
- last_failures() captures (subscriber, exception) pairs.
- last_failures() resets on next emit() call.
- all four PlanSuspensionEventKind enum values are valid in
  PlanSuspensionEvent.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment.plan_suspension_bridge import (
    PlanSuspensionBridge,
    PlanSuspensionEvent,
    PlanSuspensionEventKind,
)

# ---------------------------------------------------------------------------
# Helpers — real subscriber factories (no unittest.mock anywhere)
# ---------------------------------------------------------------------------


def _make_recording_subscriber() -> tuple[list[PlanSuspensionEvent], callable]:
    """Return (received_events_list, subscriber_callable) pair.

    Real Python closure — NOT a mock. The list captures every event the
    subscriber received so the test can assert on delivery order +
    payload contents.
    """
    received: list[PlanSuspensionEvent] = []

    def _subscriber(event: PlanSuspensionEvent) -> None:
        received.append(event)

    return received, _subscriber


def _make_raising_subscriber(exc: Exception) -> callable:
    def _subscriber(_event: PlanSuspensionEvent) -> None:
        raise exc

    return _subscriber


def _make_paused_event(
    ritual_id: str = "ritual-001",
    reason: str = "Shamir ritual incomplete at S8",
) -> PlanSuspensionEvent:
    return PlanSuspensionEvent(
        kind=PlanSuspensionEventKind.BOUNDARY_CONVERSATION_PAUSED,
        ritual_id=ritual_id,
        emitted_at="2026-05-26T12:00:00Z",
        reason=reason,
        resume_context={"paused_at_state": "S8"},
    )


# ---------------------------------------------------------------------------
# Subscribe-then-emit basic fan-out
# ---------------------------------------------------------------------------


class TestSubscribeThenEmitFansOut:
    def test_single_subscriber_receives_emitted_event(self):
        bridge = PlanSuspensionBridge()
        received, subscriber = _make_recording_subscriber()
        bridge.subscribe(subscriber)

        event = _make_paused_event()
        delivered = bridge.emit(event)

        assert delivered == 1
        assert received == [event]

    def test_emit_with_no_subscribers_returns_zero(self):
        bridge = PlanSuspensionBridge()
        delivered = bridge.emit(_make_paused_event())
        assert delivered == 0


# ---------------------------------------------------------------------------
# Multiple subscribers — registration-order delivery
# ---------------------------------------------------------------------------


class TestMultipleSubscribersRegistrationOrder:
    def test_subscribers_receive_in_registration_order(self):
        bridge = PlanSuspensionBridge()
        # Use a SHARED log to capture cross-subscriber ordering.
        order_log: list[str] = []

        def subscriber_a(_event):
            order_log.append("A")

        def subscriber_b(_event):
            order_log.append("B")

        def subscriber_c(_event):
            order_log.append("C")

        bridge.subscribe(subscriber_a)
        bridge.subscribe(subscriber_b)
        bridge.subscribe(subscriber_c)

        bridge.emit(_make_paused_event())

        assert order_log == ["A", "B", "C"]

    def test_three_subscribers_all_count_in_delivered(self):
        bridge = PlanSuspensionBridge()
        received_a, sub_a = _make_recording_subscriber()
        received_b, sub_b = _make_recording_subscriber()
        received_c, sub_c = _make_recording_subscriber()
        bridge.subscribe(sub_a)
        bridge.subscribe(sub_b)
        bridge.subscribe(sub_c)

        delivered = bridge.emit(_make_paused_event())

        assert delivered == 3
        assert len(received_a) == 1
        assert len(received_b) == 1
        assert len(received_c) == 1


# ---------------------------------------------------------------------------
# Subscribe / unsubscribe typed exceptions
# ---------------------------------------------------------------------------


class TestSubscribeUnsubscribeTypedErrors:
    def test_duplicate_subscribe_raises_value_error(self):
        bridge = PlanSuspensionBridge()
        _received, subscriber = _make_recording_subscriber()
        bridge.subscribe(subscriber)

        with pytest.raises(ValueError, match="already registered"):
            bridge.subscribe(subscriber)

    def test_unsubscribe_unknown_raises_key_error(self):
        bridge = PlanSuspensionBridge()
        _received, never_registered = _make_recording_subscriber()

        with pytest.raises(KeyError, match="not registered"):
            bridge.unsubscribe(never_registered)

    def test_unsubscribe_then_emit_does_not_deliver(self):
        bridge = PlanSuspensionBridge()
        received, subscriber = _make_recording_subscriber()
        bridge.subscribe(subscriber)
        bridge.unsubscribe(subscriber)

        delivered = bridge.emit(_make_paused_event())

        assert delivered == 0
        assert received == []


# ---------------------------------------------------------------------------
# Idempotency dedupe on (kind, ritual_id)
# ---------------------------------------------------------------------------


class TestIdempotencyDedupe:
    def test_same_kind_and_ritual_id_twice_is_noop(self):
        bridge = PlanSuspensionBridge()
        received, subscriber = _make_recording_subscriber()
        bridge.subscribe(subscriber)

        event1 = _make_paused_event(ritual_id="ritual-001")
        event2 = _make_paused_event(
            ritual_id="ritual-001",
            reason="different reason text, same dedupe key",
        )

        first_delivered = bridge.emit(event1)
        second_delivered = bridge.emit(event2)

        assert first_delivered == 1
        # Second emit with same (kind, ritual_id) is NOOP.
        assert second_delivered == 0
        # Subscriber only saw the first event.
        assert received == [event1]

    def test_different_ritual_id_does_not_dedupe(self):
        bridge = PlanSuspensionBridge()
        received, subscriber = _make_recording_subscriber()
        bridge.subscribe(subscriber)

        event1 = _make_paused_event(ritual_id="ritual-001")
        event2 = _make_paused_event(ritual_id="ritual-002")

        assert bridge.emit(event1) == 1
        assert bridge.emit(event2) == 1
        assert len(received) == 2

    def test_different_kind_same_ritual_id_does_not_dedupe(self):
        # PAUSED and RESUMED for the same ritual_id are distinct events.
        bridge = PlanSuspensionBridge()
        received, subscriber = _make_recording_subscriber()
        bridge.subscribe(subscriber)

        paused = PlanSuspensionEvent(
            kind=PlanSuspensionEventKind.BOUNDARY_CONVERSATION_PAUSED,
            ritual_id="ritual-001",
            emitted_at="2026-05-26T12:00:00Z",
            reason="paused",
        )
        resumed = PlanSuspensionEvent(
            kind=PlanSuspensionEventKind.BOUNDARY_CONVERSATION_RESUMED,
            ritual_id="ritual-001",
            emitted_at="2026-05-26T12:05:00Z",
            reason="resumed",
        )

        assert bridge.emit(paused) == 1
        assert bridge.emit(resumed) == 1
        assert len(received) == 2


# ---------------------------------------------------------------------------
# Subscriber raising — isolation + failure capture
# ---------------------------------------------------------------------------


class TestSubscriberRaisingIsolation:
    def test_raising_subscriber_does_not_prevent_others(self):
        bridge = PlanSuspensionBridge()
        received_before, sub_before = _make_recording_subscriber()
        sub_raising = _make_raising_subscriber(RuntimeError("boom"))
        received_after, sub_after = _make_recording_subscriber()

        # Order: before, raising, after — verify after still fires.
        bridge.subscribe(sub_before)
        bridge.subscribe(sub_raising)
        bridge.subscribe(sub_after)

        event = _make_paused_event()
        delivered = bridge.emit(event)

        # The raising subscriber doesn't count as successful; before+after do.
        assert delivered == 2
        assert received_before == [event]
        assert received_after == [event]

    def test_last_failures_captures_subscriber_and_exception(self):
        bridge = PlanSuspensionBridge()
        boom = RuntimeError("subscriber-boom")
        sub_raising = _make_raising_subscriber(boom)
        bridge.subscribe(sub_raising)

        bridge.emit(_make_paused_event())

        failures = bridge.last_failures()
        assert len(failures) == 1
        captured_subscriber, captured_exc = failures[0]
        assert captured_subscriber is sub_raising
        assert captured_exc is boom

    def test_last_failures_captures_multiple_raisers(self):
        bridge = PlanSuspensionBridge()
        boom_a = ValueError("first")
        boom_b = TypeError("second")
        sub_a = _make_raising_subscriber(boom_a)
        sub_b = _make_raising_subscriber(boom_b)
        bridge.subscribe(sub_a)
        bridge.subscribe(sub_b)

        bridge.emit(_make_paused_event())

        failures = bridge.last_failures()
        assert len(failures) == 2
        assert {fail[1] for fail in failures} == {boom_a, boom_b}


# ---------------------------------------------------------------------------
# last_failures() reset semantics
# ---------------------------------------------------------------------------


class TestLastFailuresResetOnEmit:
    def test_last_failures_resets_on_next_emit(self):
        bridge = PlanSuspensionBridge()
        sub_raising = _make_raising_subscriber(RuntimeError("first-call-boom"))
        _received_clean, sub_clean = _make_recording_subscriber()
        bridge.subscribe(sub_raising)
        bridge.subscribe(sub_clean)

        # First emit: raising subscriber fails.
        bridge.emit(_make_paused_event(ritual_id="ritual-001"))
        assert len(bridge.last_failures()) == 1

        # Unsubscribe the raiser; next emit MUST clear the failure list
        # even though the new emit has zero failures.
        bridge.unsubscribe(sub_raising)
        bridge.emit(_make_paused_event(ritual_id="ritual-002"))
        assert bridge.last_failures() == ()

    def test_last_failures_returns_tuple_not_mutable_list(self):
        bridge = PlanSuspensionBridge()
        sub_raising = _make_raising_subscriber(ValueError("test"))
        bridge.subscribe(sub_raising)
        bridge.emit(_make_paused_event())

        failures = bridge.last_failures()
        # Returned shape is a tuple — callers cannot mutate the bridge's
        # internal record by appending to the returned object.
        assert isinstance(failures, tuple)


# ---------------------------------------------------------------------------
# Enum coverage — all four PlanSuspensionEventKind values
# ---------------------------------------------------------------------------


class TestAllEventKindsValid:
    @pytest.mark.parametrize(
        "kind",
        [
            PlanSuspensionEventKind.BOUNDARY_CONVERSATION_PAUSED,
            PlanSuspensionEventKind.BOUNDARY_CONVERSATION_RESUMED,
            PlanSuspensionEventKind.GRANT_MOMENT_QUEUE_HOLD_REQUESTED,
            PlanSuspensionEventKind.GRANT_MOMENT_QUEUE_RESUME_REQUESTED,
        ],
    )
    def test_each_kind_constructs_and_emits(self, kind):
        bridge = PlanSuspensionBridge()
        received, subscriber = _make_recording_subscriber()
        bridge.subscribe(subscriber)

        event = PlanSuspensionEvent(
            kind=kind,
            ritual_id=f"ritual-{kind.value}",
            emitted_at="2026-05-26T12:00:00Z",
            reason=f"test for {kind.value}",
        )
        delivered = bridge.emit(event)

        assert delivered == 1
        assert received == [event]
        assert received[0].kind == kind

    def test_enum_value_round_trips_through_str(self):
        # Enum is a str subclass — values serialize to bare strings for
        # ledger / telemetry surfaces.
        assert (
            PlanSuspensionEventKind.BOUNDARY_CONVERSATION_PAUSED.value
            == "boundary_conversation_paused"
        )
        assert (
            PlanSuspensionEventKind.GRANT_MOMENT_QUEUE_RESUME_REQUESTED.value
            == "grant_moment_queue_resume_requested"
        )
