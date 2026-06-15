# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Foundation Health Heartbeat client — consent-gated counter + weekly emit (S11).

Phase 02 (S11) swaps the Phase-01 ``maybe_record_flag`` no-op for the real
pipeline the 21 emit-site primitives drive on the hot path:

    validate flag -> consent-check -> increment per-week counter -> weekly
    STAR/OHTTP emit (counters reset on send)

The pipeline holds the S11 invariants:

- **Client-side DP BEFORE share-split (EC-S11.3).** Each per-counter value is
  perturbed by local differential privacy noise BEFORE :func:`split_into_shares`
  is called — so the share-split input is the noised value and a fully
  compromised aggregator never observes a true per-client value.
- **Total ε over the weekly window, per metric (EC-S11.2).** Each of the 21
  flags has a published per-metric ε. The budget tracks ε-spent vs the published
  budget over the weekly reporting window; per-counter ε does NOT compose across
  the 21 counters × M heartbeats. Exhausting one metric's budget drops ONLY that
  metric for the cycle (``DPBudgetExceededError``); non-affected metrics report
  normally.
- **k≥100 reads the TRUE cohort (EC-S11.1).** The k-floor gate operates on the
  true distinct-submitter cardinality (``star_prio``), never the DP-noised
  value. DP perturbs the per-counter VALUE; the k-floor gates on the cohort SIZE.
- **L-01 24h ritual-coupling debounce (EC-S11.6).** A send whose window overlaps
  a ritual within 24h is deferred (``RitualCouplingDebounceTriggered``) so
  user-observable ritual timing is never coupled to network payload timing.
- **Consent gate (S12 seam).** The FIRST guard inside the real
  ``maybe_record_flag`` body is the consent check. For S11 the seam delegates to
  a ``ConsentGate`` interface (default: never-granted, opt-OUT, matching the
  Phase-01 no-op behavior); S12 fills the load-bearing
  ``SignedConsentRecorder``-backed implementation. The seam EXISTS in S11; S12
  makes it load-bearing.
"""

from __future__ import annotations

import math
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from envoy.heartbeat.errors import (
    ConsentRevokedError,
    DPBudgetExceededError,
    RitualCouplingDebounceTriggered,
)
from envoy.heartbeat.payload import ALLOWED_FLAGS
from envoy.heartbeat.star_prio import StarPrioClient, StarShare

# L-01 ritual-coupling debounce window: a heartbeat send MUST NOT fire within
# 24h of a ritual (`specs/foundation-health-heartbeat.md` § "Payload" L-01 fix).
RITUAL_DEBOUNCE = timedelta(hours=24)

# Default published per-metric DP epsilon budget over the weekly window. The
# Foundation publishes one ε per flag (`specs/foundation-health-heartbeat.md`
# § "Design stack" item 2 — "ε per-metric published"); this is the default the
# transparency report names. The budget is the TOTAL ε spendable on a metric
# across the weekly window, NOT a per-emit value.
DEFAULT_METRIC_EPSILON: float = 1.0

# Per-emit ε cost charged against a metric's window budget each time its counter
# is reported. With DEFAULT_METRIC_EPSILON=1.0 and this cost, a metric can be
# reported once per weekly window before the budget is exhausted.
_PER_EMIT_EPSILON_COST: float = 1.0


@runtime_checkable
class ConsentGate(Protocol):
    """The consent-check seam wired load-bearing in S12.

    ``is_granted`` returns True only when the user has affirmatively granted
    Foundation Health Heartbeat consent AND has not cascade-revoked it. For S11
    the default implementation (:class:`OptOutConsentGate`) returns False (the
    Phase-01 opt-OUT no-op); S12 supplies the signed-Delegation-Record-backed
    implementation that consults the real consent state.
    """

    def is_granted(self) -> bool: ...

    def is_revoked(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class OptOutConsentGate:
    """Default S11 consent gate — never granted (opt-OUT, the Phase-01 contract).

    S12 replaces this with the ``signed_consent``-backed gate. Until then the
    client is an effective no-op for telemetry: a user who never granted consent
    sees exactly the Phase-01 behavior (nothing leaves the device).
    """

    granted: bool = False
    revoked: bool = False

    def is_granted(self) -> bool:
        return self.granted and not self.revoked

    def is_revoked(self) -> bool:
        return self.revoked


@dataclass(slots=True)
class DPBudget:
    """Per-metric ε accounting over the weekly reporting window (EC-S11.2).

    ``published`` is the per-metric ε the Foundation publishes (the privacy
    claim). ``spent`` accumulates over the window; ``charge`` raises
    ``DPBudgetExceededError`` for THIS metric when the next emit would exceed the
    published budget — other metrics are unaffected. The window resets when the
    weekly counters reset on a successful send.
    """

    published: float = DEFAULT_METRIC_EPSILON
    spent: float = 0.0

    def charge(self, metric: str, cost: float) -> None:
        """Charge ``cost`` ε against this metric's window budget, or refuse.

        Raises:
            DPBudgetExceededError: the charge would push ``spent`` past
                ``published`` — the metric is dropped for this cycle; the caller
                catches this per-metric and continues with non-affected metrics.
        """
        if self.spent + cost > self.published:
            raise DPBudgetExceededError(
                f"metric {metric!r} DP epsilon budget exhausted: "
                f"spent {self.spent} + {cost} > published {self.published} over "
                "the weekly window; dropping this metric for the cycle "
                "(non-affected metrics report normally)"
            )
        self.spent += cost

    def reset(self) -> None:
        """Reset ε-spent (called when the weekly counters reset on send)."""
        self.spent = 0.0


def add_laplace_noise(value: int, *, epsilon: float, sensitivity: float = 1.0) -> int:
    """Add Laplace DP noise to an integer counter value (client-side, EC-S11.3).

    The noise is drawn from Laplace(0, sensitivity/epsilon) using a
    cryptographically-strong uniform source (``secrets``) — NOT
    ``random`` (which is not suitable for a privacy mechanism). The noised value
    is clamped at 0 (a counter is non-negative) and returned as an int. This is
    the value the caller share-splits; the TRUE value never leaves the client.

    Raises:
        ValueError: ``epsilon <= 0`` (a non-positive ε is not a valid privacy
            parameter — would imply infinite or undefined noise scale).
    """
    if epsilon <= 0:
        raise ValueError(f"epsilon must be > 0 for Laplace DP noise, got {epsilon}")
    scale = sensitivity / epsilon
    # Inverse-CDF Laplace sampling from a uniform in (-0.5, 0.5).
    # secrets.randbits → uniform in [0, 1); shift to (-0.5, 0.5).
    u = (secrets.randbits(53) / (1 << 53)) - 0.5
    sign = -1.0 if u < 0 else 1.0
    noise = -scale * sign * math.log(1 - 2 * abs(u))
    noised = round(value + noise)
    return max(0, noised)


@dataclass(slots=True)
class HeartbeatClient:
    """Hot-path consumer for the 21 emit-site primitives (S11 real pipeline).

    The 21 emit-site primitives (Boundary Conversation, Daily Digest, Grant
    Moment, etc.) call :meth:`maybe_record_flag` on the hot path. In S11 it
    validates the flag, checks consent (the S12 seam), increments a per-week
    counter, and — on the weekly cadence — emits via the STAR/OHTTP pipeline with
    DP-before-split + total-ε-over-window + k≥100 true-cohort.

    Collaborators are injected so the Tier-2 harness drives the REAL pipeline:
        - ``consent_gate``: the S12 seam (default opt-OUT no-op).
        - ``star_client``: the STAR share producer (``star_prio``).
        - ``now``: an injectable clock for deterministic debounce/window tests.
    """

    consent_gate: ConsentGate = field(default_factory=OptOutConsentGate)
    star_client: StarPrioClient | None = None
    now: Callable[[], datetime] = field(
        default=lambda: datetime.now(timezone.utc)
    )
    # Per-week counters keyed by flag name. Reset on a successful send.
    _counters: dict[str, int] = field(default_factory=dict)
    # Per-metric DP budget over the weekly window.
    _budgets: dict[str, DPBudget] = field(default_factory=dict)
    # The most recent ritual timestamp the client observed (L-01 debounce).
    _last_ritual_at: datetime | None = None

    def _clock(self) -> datetime:
        return self.now()

    def record_ritual(self, at: datetime) -> None:
        """Record a ritual occurrence for the L-01 24h debounce window."""
        self._last_ritual_at = at

    def maybe_record_flag(self, flag_name: str) -> None:
        """Hot-path flag recorder — validate, consent-check, increment counter.

        The S11 real body (was a Phase-01 ``pass``):

        1. **Validate** ``flag_name`` against ``ALLOWED_FLAGS`` (the fixed
           21-flag schema). An unknown flag is silently ignored — the emit-site
           primitives MUST NOT crash, and an out-of-schema flag is never counted
           (the T-054 schema defense already refuses it at the payload boundary).
        2. **Consent gate (S12 seam)** — the FIRST guard. If consent is NOT
           granted (the default opt-OUT), this is an effective no-op: nothing is
           counted, nothing is sent (the Phase-01 contract for opt-out users).
           If consent was REVOKED, raise ``ConsentRevokedError``.
        3. **Increment** the per-week counter for the flag.

        The weekly emit is driven separately by :meth:`emit_weekly` on the
        cadence; this method only accrues. Returns None on every path.

        Raises:
            ConsentRevokedError: consent was cascade-revoked but a record was
                attempted (S12 wires the revoke path; the guard exists in S11).
        """
        # 1. Validate against the fixed 21-flag schema. Unknown flag → no-op
        # (never crash an emit site; the schema defense owns the refusal path).
        if flag_name not in ALLOWED_FLAGS:
            return None

        # 2. Consent gate — the FIRST load-bearing guard (S12 fills it).
        if self.consent_gate.is_revoked():
            raise ConsentRevokedError(
                "Foundation Health Heartbeat consent was cascade-revoked; "
                "runtime attempted to record a flag — stop sends, clear pending "
                "counters, re-opt-in required"
            )
        if not self.consent_gate.is_granted():
            # Opt-OUT user — effective no-op (Phase-01 behavior).
            return None

        # 3. Increment the per-week counter.
        self._counters[flag_name] = self._counters.get(flag_name, 0) + 1
        return None

    def _check_ritual_debounce(self) -> None:
        """Raise if the send window overlaps a ritual within 24h (L-01)."""
        if self._last_ritual_at is None:
            return
        now = self._clock()
        if now - self._last_ritual_at < RITUAL_DEBOUNCE:
            raise RitualCouplingDebounceTriggered(
                f"heartbeat send window overlaps a ritual within 24h "
                f"(ritual at {self._last_ritual_at.isoformat()}, now "
                f"{now.isoformat()}); deferring send to avoid coupling "
                "user-observable ritual timing to network payload (L-01 fix)"
            )

    def emit_weekly(self) -> list[StarShare]:
        """Build the weekly STAR shares for the accrued counters, then reset.

        Pipeline per counter:
            1. L-01 debounce check (raises before ANY emit if a ritual is within
               24h — the whole cycle defers).
            2. Charge the per-metric DP ε budget for the weekly window. A metric
               whose budget is exhausted is DROPPED for this cycle (caught
               per-metric); non-affected metrics continue.
            3. DP-noise the counter value BEFORE the share-split (EC-S11.3).
            4. Split the noised value into a STAR share keyed by the measurement.

        Counters + budgets reset on a successful emit (the weekly window rolls;
        `specs/foundation-health-heartbeat.md` § "Cadence" — "Counters reset on
        successful send").

        Requires consent to be granted (an opt-out client never accrues a
        counter, so this returns an empty list for opt-out users).

        Raises:
            RitualCouplingDebounceTriggered: a ritual is within the 24h window —
                the whole cycle defers (counters retained for the next cycle).
        """
        if self.star_client is None:
            raise ValueError(
                "HeartbeatClient.emit_weekly requires a star_client to build "
                "shares; none was supplied"
            )
        # 1. L-01 debounce — defers the WHOLE cycle (counters retained).
        self._check_ritual_debounce()

        shares: list[StarShare] = []
        for metric, count in self._counters.items():
            budget = self._budgets.setdefault(metric, DPBudget())
            # 2. Charge the per-metric ε budget; drop ONLY this metric on
            # exhaustion (EC-S11.2 — non-affected metrics report normally).
            try:
                budget.charge(metric, _PER_EMIT_EPSILON_COST)
            except DPBudgetExceededError:
                continue
            # 3. DP noise BEFORE share-split (EC-S11.3) — the share-split input
            # is the noised value; the true count never leaves the client.
            noised = add_laplace_noise(count, epsilon=budget.published)
            # 4. Split the NOISED value into a measurement-keyed STAR share. The
            # measurement (the cohort key) is the metric name — clients reporting
            # the same active flag share a cohort; the k-floor gates on the TRUE
            # distinct-submitter count, never on `noised`.
            measurement = metric.encode("utf-8")
            share = self.star_client.build_share(
                metric, measurement, noised.to_bytes(4, "big")
            )
            shares.append(share)

        # Counters + budgets reset on successful send (weekly window rolls).
        self._counters.clear()
        for budget in self._budgets.values():
            budget.reset()
        return shares


__all__ = [
    "HeartbeatClient",
    "ConsentGate",
    "OptOutConsentGate",
    "DPBudget",
    "DEFAULT_METRIC_EPSILON",
    "RITUAL_DEBOUNCE",
    "add_laplace_noise",
]
