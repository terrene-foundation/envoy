# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Sync→async event-loop bridge for the cascade-revoke facade (F12-b).

The `KailashRuntime` Protocol declares `trust_cascade_revoke` SYNC
(`specs/runtime-abstraction.md:31` — `(str) -> set[str]`), but the real backing
store `envoy.trust.store.TrustStoreAdapter.revoke` is `async def`. A sync
Protocol method therefore cannot drive the real cascade engine without an
event-loop bridge.

A *naive* ``asyncio.run()`` is NOT a correct bridge: it raises
``RuntimeError: asyncio.run() cannot be called from a running event loop`` when
the cascade fires from inside an async cross-channel flow — the EC-8 hazard the
production adapters (`kailash_py.py`, `kailash_rs_bindings.py`) documented while
this bridge was deferred. ``run_coro_blocking`` is the bridge: it drives the
coroutine to completion on a DEDICATED worker thread that owns its OWN fresh
event loop via ``asyncio.run``. Because the worker loop is unrelated to the
caller's loop (if any), the bridge is deadlock-free whether or not the calling
thread is itself inside a running event loop.

This is a SHARED helper by design: both `KailashPyRuntime.trust_cascade_revoke`
and `KailashRsBindingsRuntime.trust_cascade_revoke` route their coroutine case
through it, so the two adapters cannot drift apart on the sync↔async contract
(per `rules/security.md` § Multi-Site — dual halves of one contract live
together, and `rules/autonomous-execution.md` Rule 4 — the same-bug-class
sibling is fixed in the same shard, not deferred).
"""

from __future__ import annotations

import logging
import time
from asyncio import run as _asyncio_run
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FuturesTimeout
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Bound the cascade-revoke wait. A revocation is a SECURITY operation whose
# purpose is the PROMPT removal of authority; a coroutine that wedges (a SQLite
# lock deadlock, a pathologically large delegation graph) MUST surface a loud
# typed failure rather than block the caller forever — a hung revocation is
# operationally indistinguishable from a revocation that never happened
# (retained authority). Overridable per call for a different cascade SLA.
DEFAULT_BRIDGE_TIMEOUT_SECONDS = 30.0

__all__ = ["run_coro_blocking", "AsyncBridgeTimeoutError", "DEFAULT_BRIDGE_TIMEOUT_SECONDS"]


class AsyncBridgeTimeoutError(TimeoutError):
    """The bridged coroutine did not complete within the wait bound.

    Distinct from a ``TimeoutError`` raised INSIDE the coroutine: this is raised
    only when the worker future is still un-done after ``timeout_seconds`` (the
    ``future.done()`` discriminator below), so a coroutine that itself raises
    ``TimeoutError`` propagates unchanged rather than being mislabelled."""


def run_coro_blocking(
    coro: Coroutine[Any, Any, _T],
    *,
    timeout_seconds: float = DEFAULT_BRIDGE_TIMEOUT_SECONDS,
) -> _T:
    """Drive ``coro`` to completion from sync code, event-loop-safe.

    The coroutine is awaited on a dedicated single-worker thread that runs its
    own ``asyncio.run`` — a fresh event loop created, driven, and torn down
    entirely within that thread. The caller's thread blocks on the worker's
    result (bounded by ``timeout_seconds``). This is safe whether or not the
    caller is inside a running event loop, because the worker loop never touches
    the caller's loop.

    A fresh executor + loop are constructed PER CALL by design — NOT a shared
    module-level executor. The isolation is what makes the bridge re-entrant
    (a coroutine that itself drives another `run_coro_blocking` nests an
    independent worker thread+loop and cannot deadlock); a shared single-worker
    executor would deadlock on that re-entrancy AND serialise all cascades.
    Cascade revocation is a rare user-initiated operation, so the per-call
    construct/teardown cost is negligible against that safety.

    Exceptions raised inside the coroutine propagate to the caller unchanged
    (``Future.result()`` re-raises). The worker loop is always closed by
    ``asyncio.run`` even on exception, so no event loop or unawaited-coroutine
    leaks — fail-loud, never a silent empty result (the EC-2/EC-8(c) cascade
    hard-constraint per `rules/zero-tolerance.md` Rule 3). On timeout a loud
    ``AsyncBridgeTimeoutError`` is raised and the wedged worker is abandoned
    (NOT waited on — waiting would re-hang the caller, defeating the bound).

    NOTE on backing-store thread/loop affinity: the coroutine and any I/O it
    performs (e.g. the trust store's persistence) run on the WORKER thread, NOT
    the caller's thread. A backing store that shares a *live* connection bound
    to a different thread (stdlib ``sqlite3`` is thread-affine) is the caller's
    responsibility to avoid — the store either persists to a file the worker
    reopens, or initialises lazily on first use on the worker thread, per
    ``envoy.trust.store.TrustStoreAdapter.revoke``'s
    ``if not self._initialized: await self.initialize()`` guard. The production
    revoke entrypoint (F12-c) MUST drive a fresh / lazily-initialised adapter
    through this bridge, NOT a pre-initialised one (tracked as an F12-c
    precondition — see the milestone ledger).
    """
    started = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="envoy-cascade-bridge")
    future = pool.submit(_asyncio_run, coro)
    try:
        result = future.result(timeout=timeout_seconds)
    except _FuturesTimeout:
        # The wait bound elapsed. `future.done()` discriminates the genuine
        # wedge from the race where the worker completed exactly at the bound
        # (and from a coroutine that itself raised `TimeoutError`, which leaves
        # the future done): if done, re-derive the true outcome; if not, abandon
        # the wedged worker LOUD — never `shutdown(wait=True)`, which would
        # re-hang the caller on the wedge it is trying to bound.
        if future.done():
            pool.shutdown(wait=False)
            return future.result()  # value, or the coroutine's real exception
        pool.shutdown(wait=False, cancel_futures=True)
        elapsed_ms = round((time.monotonic() - started) * 1000)
        logger.error(
            "async_bridge.timeout",
            extra={"timeout_seconds": timeout_seconds, "elapsed_ms": elapsed_ms},
        )
        raise AsyncBridgeTimeoutError(
            f"bridged coroutine did not complete within {timeout_seconds}s "
            f"(elapsed {elapsed_ms}ms); worker abandoned — a wedged cascade is a "
            f"loud failure, never a silent retained-authority no-op"
        ) from None
    except BaseException:
        # The coroutine raised its OWN exception, which `future.result()`
        # re-raised. Propagate unchanged (worker already finished → shutdown
        # does not block).
        pool.shutdown(wait=False)
        logger.exception("async_bridge.error")
        raise
    pool.shutdown(wait=True)
    logger.info(
        "async_bridge.ok",
        extra={"elapsed_ms": round((time.monotonic() - started) * 1000)},
    )
    return result
