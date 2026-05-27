# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.budget.threshold_dispatcher — async queue between threshold crossings
and the Ledger / Grant Moment.

Per `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md`
§ 3.2 item 4 + § 4. The dispatcher is the structural defense against
deadlocking the upstream `BudgetTracker._lock` (design § 2.3): the upstream
custom-threshold callback fires synchronously OUTSIDE its lock, but a callback
that re-entered `reserve/record/check` would deadlock (the lock is a plain
`threading.Lock`, not reentrant). So the only work done on the callback thread
is the non-blocking `enqueue`; an async worker drains the queue and does the
Ledger emit + Grant-Moment dispatch off that thread.

## Non-orphan contract

Per `rules/orphan-detection.md` Rule 1, the dispatcher's external observable
is the `budget_threshold_crossed` Ledger entry (design § 6.1 test 2) — emitted
by the worker via the injected `LedgerEmitter` on every dequeued event,
independent of whether a Grant-Moment consumer is wired. The Grant-Moment
dispatch is an injected async `on_grant_moment` seam (the heavy
`issue_grant_moment` wiring — `ConsequencePreview` / `NoveltySignals` /
envelope context — is owned by the async Kaizen hot-path interceptor that has
the envelope, and EC-2's Grant-Moment resolution path is already met). When no
seam is wired the dispatcher still emits the Ledger row.

## Threading note (Phase 01)

`enqueue` uses `asyncio.Queue.put_nowait`, which is correct when the upstream
callback fires on the same thread as the event loop — the Phase-01 model
(reserve/record are driven from the async hot path's thread). A Phase-02
multi-thread executor would route enqueue through `loop.call_soon_threadsafe`;
that is out of Phase-01 scope (single-thread asyncio).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from envoy.budget.types import EnvoyBudgetEvent

if TYPE_CHECKING:  # pragma: no cover - typing only
    from envoy.budget.ledger_emitter import LedgerEmitter

__all__ = ["ThresholdDispatcher"]


class ThresholdDispatcher:
    """Async worker queue: threshold-cross `EnvoyBudgetEvent` → Ledger + Grant Moment."""

    def __init__(
        self,
        *,
        ledger_emitter: LedgerEmitter,
        on_grant_moment: Callable[[EnvoyBudgetEvent], Awaitable[None]] | None = None,
    ) -> None:
        self._emitter = ledger_emitter
        self._on_grant_moment = on_grant_moment
        self._queue: asyncio.Queue[EnvoyBudgetEvent] = asyncio.Queue()
        self._processed = 0

    def enqueue(self, event: EnvoyBudgetEvent) -> None:
        """Non-blocking enqueue — the ONLY work done on the upstream callback thread.

        Satisfies the orchestrator's `_ThresholdSink` protocol.
        """
        self._queue.put_nowait(event)

    async def run(self) -> None:
        """Production worker loop — drains the queue forever.

        Cancel the task to stop. Each event is handled then marked done so a
        caller can `await queue.join()` for graceful shutdown.
        """
        while True:
            event = await self._queue.get()
            try:
                await self._handle(event)
            finally:
                self._queue.task_done()

    async def drain_once(self) -> int:
        """Process every currently-queued event and return how many were handled.

        Deterministic for tests — does NOT loop forever waiting for new events.
        """
        handled = 0
        while not self._queue.empty():
            event = self._queue.get_nowait()
            try:
                await self._handle(event)
            finally:
                self._queue.task_done()
            handled += 1
        return handled

    @property
    def processed_count(self) -> int:
        """Total events handled (across `run` and `drain_once`)."""
        return self._processed

    @property
    def pending_count(self) -> int:
        """Events enqueued but not yet handled."""
        return self._queue.qsize()

    async def _handle(self, event: EnvoyBudgetEvent) -> None:
        # 1. Always emit the Ledger row (the external observable — non-orphan).
        self._emitter.enqueue_threshold_crossed(event)
        await self._emitter.drain()
        # 2. Dispatch to the Grant-Moment seam if a consumer is wired.
        if self._on_grant_moment is not None:
            await self._on_grant_moment(event)
        self._processed += 1
