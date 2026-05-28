# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.budget.errors — the Budget tracker error taxonomy.

Implements the 7 typed errors frozen in `specs/budget-tracker.md`
§ Error taxonomy (lines 47-57) plus `MicrodollarOverflowError` (line 56).
All subclass the package base `EnvoyBudgetError` per design § 3.2 item 8.

Each error carries a plain-language default message (non-technical users may
read these through Boundary Conversation / Grant Moment surfaces per
`rules/communication.md`) plus structured attributes the orchestrator and
runtime adapter act on.

Layer note: `BudgetExhaustedError` ALSO subclasses the runtime-protocol
contract error `envoy.runtime.errors.BudgetExhaustedError` so existing
`except` handlers written against the protocol surface catch the concrete
budget error. Single concrete implementation per `rules/zero-tolerance.md`
Rule 4 — the budget package owns the raised error; the runtime module keeps
the abstract protocol-contract base (budget→runtime is a downward import,
correct for the composition layering in design § 3.1).
"""

from __future__ import annotations

from envoy.runtime.errors import (
    BudgetExhaustedError as _RuntimeBudgetExhaustedError,
)

__all__ = [
    "EnvoyBudgetError",
    "BudgetExhaustedError",
    "VelocityRaiseInlineBlockError",
    "AnomalyDetectedError",
    "HighVelocityPatternError",
    "ReservationExpiredError",
    "MicrodollarOverflowError",
    "ReservationDoubleRecordError",
]


class EnvoyBudgetError(Exception):
    """Base for every error raised by the `envoy.budget` primitive."""


class BudgetExhaustedError(EnvoyBudgetError, _RuntimeBudgetExhaustedError):
    """A reservation was refused because a ceiling would be breached.

    Names the most-restrictive (binding) window so the operator and the
    Grant Moment surface can explain WHICH limit was hit, not just THAT one
    was. Per `specs/budget-tracker.md` § Error taxonomy.
    """

    def __init__(
        self,
        *,
        window: str,
        requested_microdollars: int,
        remaining_microdollars: int,
        allocated_microdollars: int,
    ) -> None:
        self.window = window
        self.requested_microdollars = requested_microdollars
        self.remaining_microdollars = remaining_microdollars
        self.allocated_microdollars = allocated_microdollars
        super().__init__(
            f"Budget limit reached for the {window!r} window — this action "
            f"needs {requested_microdollars} microdollars but only "
            f"{remaining_microdollars} remain of {allocated_microdollars}."
        )


class VelocityRaiseInlineBlockError(EnvoyBudgetError):
    """An attempt to RAISE a velocity limit inline was refused (T-093 R2-H4).

    Per `specs/budget-tracker.md` § Velocity-raise ratchet: raising any
    velocity limit requires a Weekly Posture Review OR a cross-channel Grant
    Moment with a 24h cooling-off. Lowering is allowed inline.
    """

    def __init__(
        self, *, window: str, current_microdollars: int, requested_microdollars: int
    ) -> None:
        self.window = window
        self.current_microdollars = current_microdollars
        self.requested_microdollars = requested_microdollars
        super().__init__(
            f"Raising the {window!r} spending limit from {current_microdollars} "
            f"to {requested_microdollars} can't be done on the spot. It needs a "
            "Weekly Posture Review or an approval that has aged 24 hours. "
            "Lowering the limit is allowed immediately."
        )


class AnomalyDetectedError(EnvoyBudgetError):
    """A single call would consume more than 50% of the remaining session budget.

    T-093 fraud defense per `specs/budget-tracker.md` § Budget-exhaustion
    fraud defense. The call is paused for confirmation, not silently allowed.
    """

    def __init__(
        self,
        *,
        requested_microdollars: int,
        session_remaining_microdollars: int,
        threshold_pct: float,
    ) -> None:
        self.requested_microdollars = requested_microdollars
        self.session_remaining_microdollars = session_remaining_microdollars
        self.threshold_pct = threshold_pct
        super().__init__(
            f"This single action would use {requested_microdollars} microdollars — "
            f"more than {int(threshold_pct * 100)}% of the "
            f"{session_remaining_microdollars} left for this session. Pausing for "
            "your confirmation before spending that much at once."
        )


class HighVelocityPatternError(EnvoyBudgetError):
    """Five calls hit the per-call ceiling within a 60s window (T-093).

    Per `specs/budget-tracker.md` § Budget-exhaustion fraud defense — a
    high-velocity pattern routes to a Grant Moment rather than continuing.
    """

    def __init__(self, *, hits: int, window_seconds: int) -> None:
        self.hits = hits
        self.window_seconds = window_seconds
        super().__init__(
            f"{hits} maximum-cost actions happened in {window_seconds} seconds. "
            "That's an unusual burst, so it's being held for your confirmation."
        )


class ReservationExpiredError(EnvoyBudgetError):
    """A `record_for_call` arrived after the reservation's TTL elapsed.

    Per `specs/budget-tracker.md` § Error taxonomy (line 55). The held
    capacity is released; the caller must re-reserve.
    """

    def __init__(self, *, reservation_id: str, expired_at: str, recorded_at: str) -> None:
        self.reservation_id = reservation_id
        self.expired_at = expired_at
        self.recorded_at = recorded_at
        super().__init__(
            f"The budget hold for this action expired at {expired_at} (recorded "
            f"at {recorded_at}). The held amount was released; please request the "
            "action again."
        )


class MicrodollarOverflowError(EnvoyBudgetError):
    """A microdollar value exceeded the signed 64-bit cross-SDK bound.

    Per `specs/budget-tracker.md` line 56. Upstream Python `int` is unbounded;
    Envoy validates against int64 so the Rust binding agrees on the boundary.
    """

    def __init__(self, *, value: int, field_name: str) -> None:
        self.value = value
        self.field_name = field_name
        super().__init__(
            f"The amount for {field_name!r} ({value}) is too large to represent "
            "consistently across systems (it exceeds the 64-bit limit)."
        )


class ReservationDoubleRecordError(EnvoyBudgetError):
    """A reservation was recorded twice — the idempotency guard for double-billing.

    Per `specs/budget-tracker.md` line 57. This is the EC-8 cross-channel
    no-double-billing defense (`02-mvp-objectives.md` line 117): the same
    `reservation_id` recorded from a sibling channel adapter raises here
    rather than charging the budget twice.
    """

    def __init__(self, *, reservation_id: str, first_recorded_at: str) -> None:
        self.reservation_id = reservation_id
        self.first_recorded_at = first_recorded_at
        super().__init__(
            f"This action's cost was already recorded at {first_recorded_at}; "
            "it will not be charged again."
        )
