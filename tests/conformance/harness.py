# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/conformance/harness.py — the ONE parametrized BET-6 harness.

Source of truth: `specs/runtime-abstraction.md` § Contract partition (BET-6);
harness design (one parametrized harness, single `get_runtime()` seam, two
pluggable scorers) from
`workspaces/phase-02-distribution/todos/active/01-m1-ws1-runtime-pluggability.md`
§ S1 + the deep-dive § 1.5 recommendation.

This is the SKELETON the vector-family shards (S2b/S2c/S3a/S3b) plug into. It
provides:

- `RUNTIME_FAMILIES` — the runtime axis the harness parametrizes over.
- `resolve_runtime(family)` — the SINGLE seam: every runtime is obtained via
  `envoy.runtime.get_runtime(family=...)` and nothing else (honors the
  `selection.py` "one seam" invariant). Returns `None` when the family is not
  yet wired (rs-bindings before S2a flips `RS_BINDINGS_ENABLED`) so the harness
  SKIPS that lane with an explicit reason rather than failing.
- `parametrize_runtime_x_vectors(vectors)` — the parametrize decorator that
  emits IDs of the form ``<runtime>-<vector_id>`` so a failure line reads
  ``test_<family>[kailash-rs-bindings-N2-007]`` (the runtime axis is visible in
  the failure line, S1 acceptance criterion 3).
- `run_byte_identity(runtime, vector)` — invoke the vector's method on the
  resolved runtime and score the output against the reference (`kailash-py`)
  output via the byte-identity scorer, returning a `ScoreResult`.

S1 scope: the skeleton + scorer wiring. The corpus (`load_vectors()`) is empty
until S2b/S2c/S3a/S3b author it; the harness collects, parametrizes, and proves
the byte-identity scorer asserts hash-equality — that is the S1 deliverable.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from envoy.runtime import get_runtime
from envoy.runtime.conformance import (
    ConformanceVector,
    ScoreResult,
    score_byte_identity,
)
from envoy.runtime.errors import RsBindingsNotAvailableInPhase01Error
from envoy.runtime.protocol import KailashRuntime

#: The runtime axis. `kailash-py` is the reference (always wired);
#: `kailash-rs-bindings` is the runtime-under-test (wired in S2a).
RUNTIME_FAMILIES: tuple[str, ...] = ("kailash-py", "kailash-rs-bindings")

#: The reference runtime family. Byte-identity scoring compares every other
#: runtime's output against this one's.
REFERENCE_FAMILY = "kailash-py"


def resolve_runtime(family: str, **kwargs: Any) -> KailashRuntime | None:
    """Resolve a runtime via the single `get_runtime()` seam.

    Returns the adapter, or ``None`` when the family is not yet wired in this
    phase (the rs-bindings runtime before S2a flips ``RS_BINDINGS_ENABLED`` —
    `get_runtime` raises `RsBindingsNotAvailableInPhase01Error`). A ``None``
    return tells the harness to SKIP that lane with an explicit reason
    (`rules/testing.md` § Test-Skip Triage: infra-unavailable = ACCEPTABLE),
    NOT to fail — the rs lane goes green automatically once S2a wires it.
    """
    try:
        return get_runtime(family=family, **kwargs)
    except RsBindingsNotAvailableInPhase01Error:
        return None


def load_vectors() -> Sequence[ConformanceVector]:
    """Load the conformance-vector corpus.

    S1 ships an EMPTY corpus — the families (N1–N6, E1–E7) are authored in
    S2b/S2c/S3a/S3b. The skeleton's own unit test (`test_harness_skeleton.py`)
    exercises the parametrization + scorer against a synthetic vector, so the
    skeleton is proven independently of the corpus.
    """
    return ()


def parametrize_runtime_x_vectors(vectors: Sequence[ConformanceVector]):
    """Parametrize a test over (runtime-under-test × vector).

    Emits IDs of the form ``<runtime>-<vector_id>`` so a parametrized test named
    ``test_n2_envelope_cache`` produces failure lines like
    ``test_n2_envelope_cache[kailash-rs-bindings-N2-007]`` — the runtime axis is
    visible in the failure line (S1 acceptance criterion 3). The reference
    family is NOT in the axis: it is the comparison baseline, not a
    runtime-under-test.
    """
    families_under_test = [f for f in RUNTIME_FAMILIES if f != REFERENCE_FAMILY]
    params = [
        pytest.param(family, vector, id=f"{family}-{vector.vector_id}")
        for family in families_under_test
        for vector in vectors
    ]
    return pytest.mark.parametrize(("runtime_family", "vector"), params)


def _invoke(runtime: KailashRuntime, vector: ConformanceVector) -> Any:
    """Invoke the vector's method on ``runtime`` with the vector's inputs."""
    method = getattr(runtime, vector.method)
    return method(**vector.inputs)


def run_byte_identity(runtime_family: str, vector: ConformanceVector) -> ScoreResult:
    """Run one byte-identity vector against the runtime-under-test.

    Resolves both the reference runtime (`kailash-py`) and the runtime-under-test
    via `resolve_runtime`, invokes the vector's method on each, and scores the
    two outputs with the byte-identity scorer. Raises `pytest.skip` when the
    runtime-under-test is not yet wired.

    The returned `ScoreResult` carries the field-localized diff on mismatch; the
    test asserts ``result.passed`` so the failure line names the field that
    diverged (the scorer, not a bare ``assert a == b``).
    """
    runtime = resolve_runtime(runtime_family)
    if runtime is None:
        pytest.skip(
            f"runtime {runtime_family!r} not wired in this phase "
            f"(RS_BINDINGS_ENABLED is False; S2a wires it)"
        )
    reference = resolve_runtime(REFERENCE_FAMILY)
    assert reference is not None, "reference runtime kailash-py must always wire"

    reference_output = _invoke(reference, vector)
    runtime_output = _invoke(runtime, vector)
    return score_byte_identity(reference_output, runtime_output)


__all__ = [
    "RUNTIME_FAMILIES",
    "REFERENCE_FAMILY",
    "resolve_runtime",
    "load_vectors",
    "parametrize_runtime_x_vectors",
    "run_byte_identity",
]
