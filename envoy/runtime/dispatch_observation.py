# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.dispatch_observation — cross-runtime classifier-dispatch hook.

Source of truth: `specs/runtime-abstraction.md` § Conformance vectors N3
("Structural-vs-semantic partition").

N3 asserts a behavioral invariant the byte-identity scorer alone cannot see:
*every envelope check that reports a `structural`-class error MUST NOT invoke the
classifier ensemble; every check reporting a `semantic`-class error MUST dispatch
to it.* Whether a call dispatched the classifier is not visible in the call's
*output* — it is a side-effect of *how* the verdict was reached. The conformance
harness therefore needs a deterministic, runtime-agnostic way to observe "did
this call dispatch to the classifier?" so N3 can assert structural→no-dispatch
and semantic→dispatch identically on both runtimes (S1 acceptance criterion 4;
the N3 family in S2b consumes this hook).

The hook is a thread-safe in-process recorder. A runtime adapter calls
`record_dispatch(ref, content_kind=...)` at the moment it actually invokes the
classifier ensemble; the harness wraps a method call in `observe()` and reads
back `DispatchObservation.dispatched`. The recorder is deterministic — it counts
real dispatch calls, it does NOT infer dispatch from output heuristics (which
would be the regex-NLP failure mode `rules/probe-driven-verification.md` blocks).
A structural-class check that never calls `record_dispatch` yields
`dispatched == False`; a semantic-class check that calls it once yields
`dispatched == True` with `dispatch_count == 1`.

Determinism contract: the observation is scoped to a single `observe()` context
via a `contextvars.ContextVar`, so concurrent harness workers (pytest-xdist) and
nested calls do not cross-contaminate counts.
"""

from __future__ import annotations

import contextlib
import contextvars
import dataclasses
from collections.abc import Iterator
from typing import Optional


@dataclasses.dataclass(frozen=True)
class DispatchObservation:
    """The deterministic record produced by one `observe()` context.

    - ``dispatched`` — True iff the classifier ensemble was invoked at least once.
    - ``dispatch_count`` — exact number of `record_dispatch` calls (an N3 semantic
      vector asserts ≥1; the count localizes a runtime that dispatches the wrong
      number of times).
    - ``refs`` — the classifier refs dispatched, in call order (for failure
      localization: which classifier the runtime invoked).
    """

    dispatched: bool
    dispatch_count: int
    refs: tuple[str, ...]


@dataclasses.dataclass
class _DispatchAccumulator:
    """Mutable per-context accumulator. Internal; not part of the public API."""

    count: int = 0
    refs: list[str] = dataclasses.field(default_factory=list)


# One accumulator per `observe()` context. `None` outside any context — a
# `record_dispatch` call outside `observe()` is a no-op (the production hot path
# dispatches the classifier without the harness watching; only the harness opens
# an observation context).
_active: contextvars.ContextVar[Optional[_DispatchAccumulator]] = contextvars.ContextVar(
    "envoy_dispatch_observation", default=None
)


def record_dispatch(ref: str) -> None:
    """Record that the classifier ensemble was dispatched for ``ref``.

    Called by a runtime adapter at the exact site where it invokes the classifier
    ensemble (`classifier_invoke` / the semantic branch of `envelope_check`).
    Outside an `observe()` context this is a no-op, so the production path is
    unaffected when the harness is not watching.
    """
    acc = _active.get()
    if acc is None:
        return
    acc.count += 1
    acc.refs.append(ref)


@contextlib.contextmanager
def observe() -> Iterator["_ObservationHandle"]:
    """Open a dispatch-observation context.

    Usage in the harness::

        with observe() as handle:
            runtime.envelope_check(envelope, action)
        obs = handle.result()
        assert obs.dispatched is expected_dispatch  # N3 invariant

    The context is isolated via a `ContextVar` token so nested or concurrent
    observations do not cross-contaminate. `handle.result()` is valid only after
    the context exits (the accumulator is sealed into a frozen
    `DispatchObservation` on exit).
    """
    acc = _DispatchAccumulator()
    token = _active.set(acc)
    handle = _ObservationHandle(acc)
    try:
        yield handle
    finally:
        _active.reset(token)
        handle._seal()


class _ObservationHandle:
    """Handle returned by `observe()`; yields the sealed observation on exit."""

    def __init__(self, acc: _DispatchAccumulator) -> None:
        self._acc = acc
        self._sealed: Optional[DispatchObservation] = None

    def _seal(self) -> None:
        self._sealed = DispatchObservation(
            dispatched=self._acc.count > 0,
            dispatch_count=self._acc.count,
            refs=tuple(self._acc.refs),
        )

    def result(self) -> DispatchObservation:
        """Return the sealed observation. Valid only after the context exits."""
        if self._sealed is None:
            raise RuntimeError(
                "DispatchObservation is not available until the observe() " "context has exited"
            )
        return self._sealed


__all__ = [
    "DispatchObservation",
    "record_dispatch",
    "observe",
]
