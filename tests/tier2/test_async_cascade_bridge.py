# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: F12-b — `run_coro_blocking` sync↔async event-loop bridge.

Source authority:
- `specs/runtime-abstraction.md:31` — `trust_cascade_revoke(root_id) -> set[str]`
  is declared SYNC, but the real backing store
  `envoy.trust.store.TrustStoreAdapter.revoke` is `async def`.
- `specs/grant-moment.md` § cascade revocation (EC-8(c) hard constraint).

The bridge's load-bearing invariant is event-loop SAFETY: it MUST drive a
coroutine to completion whether or not the calling thread is already inside a
running event loop. A naive `asyncio.run()` raises `RuntimeError` in the
inside-a-loop case (the EC-8 cross-channel hazard the production adapters
documented while F12-b was deferred). These tests pin that invariant directly
on the bridge primitive, before the adapter + facade tests exercise it through
the cascade path.

Per `rules/testing.md` § Tier 2 — no mocking; the coroutines under test are
real, deterministic coroutines.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from envoy.runtime.adapters._async_cascade_bridge import run_coro_blocking


class _BridgeError(RuntimeError):
    """Distinct error type so propagation assertions cannot false-match."""


async def _echo(value: int) -> int:
    # A genuine await point so the coroutine actually suspends/resumes on the
    # worker loop (not a trivially-synchronous coroutine).
    await asyncio.sleep(0)
    return value * 2


async def _boom() -> None:
    await asyncio.sleep(0)
    raise _BridgeError("cascade engine failed")


class TestRunCoroBlocking:
    def test_returns_coroutine_result_from_sync_context(self) -> None:
        """Called from a plain sync context (no running loop), the bridge runs
        the coroutine and returns its result."""
        assert run_coro_blocking(_echo(21)) == 42

    def test_propagates_exception_unchanged(self) -> None:
        """An exception raised inside the coroutine propagates to the caller
        unchanged — fail-loud, never swallowed into a silent default."""
        with pytest.raises(_BridgeError, match="cascade engine failed"):
            run_coro_blocking(_boom())

    async def test_drives_coroutine_from_inside_a_running_loop(self) -> None:
        """THE event-loop-safety invariant (the EC-8 hazard): this test body
        runs inside the pytest-asyncio event loop, so the bridge is called from
        a thread that ALREADY has a running loop. A naive `asyncio.run()` would
        raise `RuntimeError: cannot be called from a running event loop` here;
        the worker-thread bridge MUST succeed."""
        # Sanity: we really are inside a running loop on this thread.
        assert asyncio.get_running_loop() is not None
        result = run_coro_blocking(_echo(50))
        assert result == 100

    async def test_propagates_exception_from_inside_a_running_loop(self) -> None:
        """Exception propagation holds in the inside-a-loop case too."""
        with pytest.raises(_BridgeError, match="cascade engine failed"):
            run_coro_blocking(_boom())

    def test_runs_on_a_distinct_worker_thread(self) -> None:
        """The coroutine executes on a dedicated worker thread, not the caller's
        thread — the structural reason the bridge is loop-safe (the worker loop
        never touches the caller's loop)."""
        caller_thread = threading.get_ident()

        async def _capture_thread() -> int:
            await asyncio.sleep(0)
            return threading.get_ident()

        worker_thread = run_coro_blocking(_capture_thread())
        assert worker_thread != caller_thread

    def test_does_not_leave_unawaited_coroutine_warning(
        self, recwarn: pytest.WarningsRecorder
    ) -> None:
        """The bridge awaits the coroutine to completion; no
        'coroutine was never awaited' RuntimeWarning leaks at GC."""
        run_coro_blocking(_echo(1))
        unawaited = [w for w in recwarn.list if "never awaited" in str(w.message)]
        assert unawaited == [], (
            f"bridge leaked unawaited-coroutine warning(s): "
            f"{[str(w.message) for w in unawaited]}"
        )
