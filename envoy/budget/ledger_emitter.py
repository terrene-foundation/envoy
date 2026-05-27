# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.budget.ledger_emitter — single-point Ledger emission for budget events.

Per `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md`
§ 3.2 item 7, implementing the single-emitter discipline of
`rules/event-payload-classification.md` Rule 1. Emits three Ledger entry
types per `specs/ledger.md` § Ledger entry schemas:

- `budget_reservation_record` — on every `record_for_call` success.
- `budget_threshold_crossed` — on every threshold-cross `EnvoyBudgetEvent`.
- `budget_extended` — on every Grant-Moment `Approve` that raised a ceiling.

`principal_id` is redacted through
`dataflow.classification.event_payload.format_record_id_for_event` BEFORE the
content dict is built (Phase-01 narrow per `envoy.ledger` facade docstring;
same pattern as `envoy.daily_digest.aggregator`). With no policy wired
(Phase 01 default) the helper passes the value through; a wired policy
produces the `sha256:`-prefixed form (`rules/event-payload-classification.md`
Rule 2) identical Python ↔ Rust.

## Sync enqueue, async drain

`EnvoyLedger.append` is async; the budget orchestrator's `record_for_call` is
sync. The emitter bridges with a sync `enqueue_*` buffer + an async `drain()`
that flushes to the Ledger. The async hot path (and Tier-2 tests) `await
drain()` after the sync accounting completes. This keeps the
reserve/record pair sync (matching the upstream `BudgetTracker` and the
runtime-abstraction contract) without losing the emission.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from dataflow.classification.event_payload import format_record_id_for_event

from envoy.budget.types import EnvoyBudgetEvent, ReservationHandle, WindowName

if TYPE_CHECKING:  # pragma: no cover - typing only
    from envoy.ledger.facade import EnvoyLedger

__all__ = ["LedgerEmitter"]

# Model name passed to format_record_id_for_event for budget-event principal ids;
# matches the classification-model convention used across envoy event payloads.
_PRINCIPAL_MODEL = "Principal"


class _PendingEmit(NamedTuple):
    entry_type: str
    content: dict[str, Any]


class LedgerEmitter:
    """Buffers budget Ledger entries (sync enqueue) and flushes them (async drain).

    The buffer preserves enqueue order so the hash chain reflects the real
    emission sequence. `drain()` is idempotent — draining an empty buffer is a
    no-op returning an empty list.
    """

    def __init__(
        self,
        *,
        ledger: EnvoyLedger,
        classification_policy: Any | None = None,
    ) -> None:
        self._ledger = ledger
        self._policy = classification_policy
        self._pending: list[_PendingEmit] = []

    # ------------------------------------------------------------------
    # Sync enqueue (called from sync accounting + the upstream callback thread)
    # ------------------------------------------------------------------

    def enqueue_reservation_record(
        self, handle: ReservationHandle, actual_microdollars: int
    ) -> None:
        """Buffer a `budget_reservation_record` entry for `handle`.

        Payload captures the reserved/actual split + per-window reserved map so
        the Daily Digest (shard 11) can render committed spend per intent. The
        entry is timestamped by `EnvoyLedger.append`'s entry envelope; no
        separate `recorded_at` is duplicated into the content.
        """
        self._pending.append(
            _PendingEmit(
                "budget_reservation_record",
                {
                    "intent_id": handle.intent_id,
                    "reservation_id": handle.reservation_id,
                    "reserved_microdollars": handle.reserved_microdollars,
                    "actual_microdollars": actual_microdollars,
                    "per_window_reserved": {
                        str(w): v for w, v in handle.reserved_per_window.items()
                    },
                },
            )
        )

    def enqueue_threshold_crossed(self, event: EnvoyBudgetEvent) -> None:
        """Buffer a `budget_threshold_crossed` entry with the principal redacted."""
        self._pending.append(
            _PendingEmit(
                "budget_threshold_crossed",
                {
                    "principal_id": self._redact_principal(event.principal_id),
                    "window": str(event.window),
                    "period_key": event.period_key,
                    # The Phase-01 Ledger is int-only (`canonical_dumps` rejects
                    # floats per `specs/ledger.md`); the threshold fraction is
                    # encoded as integer basis points (0.80 -> 8000), lossless
                    # for the spec's 0.50/0.80/0.95/1.00 thresholds.
                    "threshold_bps": round(event.threshold_pct * 10000),
                    "committed_microdollars": event.committed_microdollars,
                    "reserved_microdollars": event.reserved_microdollars,
                    "allocated_microdollars": event.allocated_microdollars,
                    "observed_at": event.observed_at.isoformat(),
                },
            )
        )

    def enqueue_budget_extended(
        self,
        *,
        window: WindowName,
        prior_allocated_microdollars: int,
        new_allocated_microdollars: int,
        grant_moment_ref: str,
    ) -> None:
        """Buffer a `budget_extended` entry for a Grant-Moment-approved raise."""
        self._pending.append(
            _PendingEmit(
                "budget_extended",
                {
                    "window": str(window),
                    "prior_allocated_microdollars": prior_allocated_microdollars,
                    "new_allocated_microdollars": new_allocated_microdollars,
                    "grant_moment_ref": grant_moment_ref,
                },
            )
        )

    # ------------------------------------------------------------------
    # Async drain (flushes to the real Ledger)
    # ------------------------------------------------------------------

    async def drain(self) -> list[str]:
        """Flush every buffered entry to the Ledger in enqueue order.

        Returns the list of new entry ids. Pops each entry only after a
        successful append so a mid-drain failure leaves the unflushed tail in
        the buffer (no silent loss per `rules/zero-tolerance.md` Rule 3).
        """
        entry_ids: list[str] = []
        while self._pending:
            emit = self._pending[0]
            entry_id = await self._ledger.append(entry_type=emit.entry_type, content=emit.content)
            self._pending.pop(0)
            entry_ids.append(entry_id)
        return entry_ids

    @property
    def pending_count(self) -> int:
        """Number of buffered entries not yet flushed."""
        return len(self._pending)

    def _redact_principal(self, principal_id: str) -> str:
        """Route the principal id through the classification helper.

        Phase-01 default (no policy) passes the value through; a wired policy
        produces the `sha256:`-prefixed form. The fallback `<redacted>` covers
        the helper returning `None` (defensive; the helper returns a string for
        non-None inputs)."""
        return (
            format_record_id_for_event(self._policy, _PRINCIPAL_MODEL, principal_id) or "<redacted>"
        )
