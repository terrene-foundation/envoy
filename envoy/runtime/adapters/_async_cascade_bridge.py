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

import concurrent.futures
import logging
from asyncio import run as _asyncio_run
from collections.abc import Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

__all__ = ["run_coro_blocking"]


def run_coro_blocking(coro: Coroutine[Any, Any, _T]) -> _T:
    """Drive ``coro`` to completion from sync code, event-loop-safe.

    The coroutine is awaited on a dedicated single-worker thread that runs its
    own ``asyncio.run`` — a fresh event loop created, driven, and torn down
    entirely within that thread. The caller's thread blocks on the worker's
    result. This is safe whether or not the caller is inside a running event
    loop, because the worker loop never touches the caller's loop.

    Exceptions raised inside the coroutine propagate to the caller unchanged
    (``Future.result()`` re-raises). The worker loop is always closed by
    ``asyncio.run`` even on exception, so no event loop or unawaited-coroutine
    leaks — fail-loud, never a silent empty result (the EC-2/EC-8(c) cascade
    hard-constraint per `rules/zero-tolerance.md` Rule 3).

    NOTE on backing-store loop affinity: the coroutine and any I/O it performs
    (e.g. the trust store's persistence) run on the worker loop, NOT the
    caller's loop. A backing store that shares a *live* connection bound to a
    different loop is the caller's responsibility to avoid — the store either
    persists to a file the worker reopens, or initializes lazily on first use
    (the worker loop), per `envoy.trust.store.TrustStoreAdapter.revoke`'s
    ``if not self._initialized: await self.initialize()`` guard.
    """
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="envoy-cascade-bridge"
    ) as pool:
        future = pool.submit(_asyncio_run, coro)
        return future.result()
