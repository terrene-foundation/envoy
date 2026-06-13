# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/conformance/test_n4_n6.py — N4-N6 cross-runtime byte-identity (S2c).

Tier 2 (real infrastructure, NO mocking). Source of truth:
`specs/runtime-abstraction.md` § Conformance vectors N1-N6 decoded (N4 verdict
rendering / N5 posture ceiling / N6 session-scoped cache correctness),
`specs/session-state.md` § `tool_calls_made` fingerprint + § session_boundary_crossed.

Three families, two distinct buildable slices:

LIVE (N6) — `tool_calls_made` fingerprint `sha256(tool_name ||
canonicalize_args(args))` whose `canonicalize_args` is JCS = the WIRED
`envelope_canonical_form` on BOTH adapters, plus the S5b `session_boundary_crossed`
content_hash over a deterministic boundary content dict. Both are live
cross-runtime byte-identity loops NOW — invoked on `kailash-py` AND
`kailash-rs-bindings` (resolved via the test-only harness seam; production
`RS_BINDINGS_ENABLED` stays False), scored with `score_byte_identity`
(hash-equality + field-localized diff) — NOT a bare `assert a == b`. The harness
uses FIXTURES, not the live WS-6 observed-state store.

DEFERRED (N4 + N5) — `grant_moment_surface` (N4) and `envelope_check` (N5) are
substrate-gated on the rs adapter: both raise `RuntimeNotReadyError` naming
shard S6a until that shard lands the engine. The corpora are READY (authored in
full); the cross-runtime drivers `xfail(strict=False)` naming the gating shard +
spec ref — the honest deferral per `rules/zero-tolerance.md` Rule 2, NOT a stub.
When S6a wires the engine the xfail flips green with no corpus change. The
substrate-gated state is PROVEN by `test_n4_n5_methods_are_substrate_gated`
(mirrors S3a's wired-set guard).

N4 STRUCTURED-PAYLOAD-ONLY (load-bearing): N4's byte-identity gate compares ONLY
the structured verdict payload. The rendered verdict TEXT is
semantically-equivalent and DEFERRED to the Phase-03 semantic harness
(`runtime-abstraction.md:152/207`; scoring metric is the open question at
`:239`). This module authors NO rendered-text probe — byte-identity is a
STRUCTURAL hash-equality assertion per `rules/probe-driven-verification.md`
(no regex / keyword / LLM scoring anywhere). The N4 vectors' `field_tiers` map
records the rendered-text field as SEMANTICALLY_EQUIVALENT so the deferral is
machine-verifiable; `test_n4_is_structured_payload_only` asserts no vector
declares the rendered-text field byte-identical.

Real-infrastructure note (Tier 2, NO mocking per `rules/testing.md`): the N6
fingerprint + boundary content_hash both forward to the REAL
`envoy.envelope.canonical_bytes` JCS primitive through the adapters — no
`unittest.mock` / `@patch` / `MagicMock` anywhere. The N5 PostureVector / N6
FingerprintVector / BoundaryVector wrappers are plain deterministic
dataclasses (NOT mocks).
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.adapters.kailash_rs_bindings import KailashRsBindingsRuntime
from envoy.runtime.conformance import ScoreResult, score_byte_identity
from envoy.runtime.contract_tier import ContractTier
from envoy.runtime.errors import RuntimeNotReadyError
from tests.conformance import harness
from tests.conformance.n4_n6_vectors import (
    N4_RENDERED_PATH,
    BoundaryVector,
    FingerprintVector,
    PostureVector,
    n4_vectors,
    n5_vectors,
    n6_boundary_vectors,
    n6_fingerprint_vectors,
)

# The runtime-under-test family (kailash-py is the reference baseline every
# vector is compared against). IDs are emitted as "<runtime>-<vector_id>".
RUNTIME_UNDER_TEST = "kailash-rs-bindings"
REFERENCE = "kailash-py"

#: The gating shard for the N4/N5 substrate-gated methods + the spec anchor; the
#: xfail reason names both so a reader knows exactly what unblocks the lane.
_N4_XFAIL_REASON = (
    "substrate-gated on S6a (Grant Moment dispatch surface) — "
    "runtime-abstraction.md:152 N4 structured-payload byte-identity flips green "
    "when S6a wires grant_moment_surface"
)
_N5_XFAIL_REASON = (
    "substrate-gated on S6a (structural+semantic envelope-check engine) — "
    "runtime-abstraction.md § N5 posture-ceiling byte-identity flips green "
    "when S6a wires envelope_check"
)


# ---------------------------------------------------------------------------
# Generic scorer assertion — names runtime + vector + field-localized diff.
# ---------------------------------------------------------------------------


def _assert_byte_identical(result: ScoreResult, runtime: str, vector_id: str) -> None:
    """Assert the byte-identity ScoreResult passed; on failure, surface BOTH
    canonical sides + the field-localized diff (NOT a bare assert a == b)."""
    if result.passed:
        return
    assert result.mismatch is not None
    raise AssertionError(
        f"byte-identity FAILED [{runtime}-{vector_id}]: "
        f"field={result.mismatch.json_path} "
        f"byte_offset={result.mismatch.byte_offset}\n"
        f"  {REFERENCE} (left):  {result.mismatch.left_canonical!r}\n"
        f"  {runtime} (right): {result.mismatch.right_canonical!r}\n"
        f"  left_hash={result.left_hash} right_hash={result.right_hash}"
    )


# ---------------------------------------------------------------------------
# N4 — Verdict rendering (10 vectors). grant_moment_surface(request) -> verdict.
# Substrate-gated on S6a → cross-runtime byte-identity xfails until S6a lands.
# STRUCTURED-PAYLOAD-ONLY: NO rendered-text probe.
# ---------------------------------------------------------------------------


_N4 = n4_vectors()


@pytest.mark.xfail(strict=False, reason=_N4_XFAIL_REASON)
@pytest.mark.parametrize("vector", _N4, ids=[f"{RUNTIME_UNDER_TEST}-{v.vector_id}" for v in _N4])
def test_n4_verdict_structured_payload_byte_identical(vector: Any) -> None:
    """N4: ``grant_moment_surface(request)`` STRUCTURED verdict payload is
    byte-identical (hash-equal) across runtimes. The rendered verdict TEXT is
    Phase-03-deferred (semantically-equivalent) and is NOT scored here — this
    gate compares only the structured payload.

    Substrate-gated: both adapters raise RuntimeNotReadyError (S6a) until the
    Grant Moment dispatch surface lands; the xfail flips green then. When wired,
    the driver scores ONLY ``verdict["structured"]`` with score_byte_identity —
    never the rendered text (byte-identity is structural, never probe-judged)."""
    ref = harness.resolve_runtime(REFERENCE)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert ref is not None and rut is not None

    ref_verdict = ref.grant_moment_surface(**vector.inputs)
    rut_verdict = rut.grant_moment_surface(**vector.inputs)
    # Structured-payload-ONLY: extract the structured slice; the rendered text is
    # DEFERRED to Phase-03 and is deliberately NOT compared (no rendered-text
    # probe — byte-identity is a STRUCTURAL hash-equality assertion).
    ref_structured = ref_verdict["structured"]
    rut_structured = rut_verdict["structured"]
    result = score_byte_identity(ref_structured, rut_structured)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, vector.vector_id)


# ---------------------------------------------------------------------------
# N5 — Posture ceiling (15 vectors). envelope_check(envelope, action) -> verdict.
# Substrate-gated on S6a → cross-runtime byte-identity xfails until S6a lands.
# ---------------------------------------------------------------------------


_N5: list[PostureVector] = n5_vectors()


@pytest.mark.xfail(strict=False, reason=_N5_XFAIL_REASON)
@pytest.mark.parametrize(
    "pvector", _N5, ids=[f"{RUNTIME_UNDER_TEST}-{pv.vector.vector_id}" for pv in _N5]
)
def test_n5_posture_ceiling_byte_identical(pvector: PostureVector) -> None:
    """N5: ``envelope_check(envelope, action)`` verdict effective_posture is the
    floor ``min(envelope-declared, principal-current)``, byte-identical across
    runtimes. The driver also pins the ground-truth floor (both runtimes surface
    the SPEC ceiling, not merely agree with each other).

    Substrate-gated: both adapters raise RuntimeNotReadyError (S6a) until the
    structural+semantic envelope-check engine lands; the xfail flips green then."""
    ref = harness.resolve_runtime(REFERENCE)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert ref is not None and rut is not None

    ref_verdict = ref.envelope_check(**pvector.vector.inputs)
    rut_verdict = rut.envelope_check(**pvector.vector.inputs)
    result = score_byte_identity(ref_verdict, rut_verdict)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, pvector.vector.vector_id)

    # Pin the ground-truth ceiling both runtimes MUST compute.
    assert ref_verdict["effective_posture"] == pvector.expected_effective
    assert rut_verdict["effective_posture"] == pvector.expected_effective


# ---------------------------------------------------------------------------
# N6 — Session-scoped cache correctness (10 vectors). LIVE byte-identity loop.
#
# (a) FINGERPRINT (7 vectors): sha256(tool_name || canonicalize_args(args)),
#     canonicalize_args = WIRED envelope_canonical_form.
# (b) BOUNDARY content_hash (3 vectors): sha256 over the JCS-canonical
#     session_boundary_crossed content dict.
# ---------------------------------------------------------------------------


_N6_FP: list[FingerprintVector] = n6_fingerprint_vectors()
_N6_BND: list[BoundaryVector] = n6_boundary_vectors()


def _fingerprint(runtime: Any, tool_name: str, args: dict[str, Any]) -> bytes:
    """Compute the `tool_calls_made` fingerprint on ``runtime``.

    Per `specs/session-state.md` line 63: ``sha256(tool_name ||
    canonicalize_args(args))``. ``canonicalize_args`` is JCS — the runtime's
    WIRED ``envelope_canonical_form``. Returns the raw sha256 digest bytes so the
    scorer hashes them directly (bytes pass-through)."""
    args_canonical = runtime.envelope_canonical_form(args)
    return hashlib.sha256(tool_name.encode("utf-8") + args_canonical).digest()


@pytest.mark.parametrize(
    "fvector", _N6_FP, ids=[f"{RUNTIME_UNDER_TEST}-{fv.vector.vector_id}" for fv in _N6_FP]
)
def test_n6_tool_call_fingerprint_byte_identical(fvector: FingerprintVector) -> None:
    """N6 (a): the `tool_calls_made` fingerprint hashes identically across
    runtimes given the same tool_name + args. The `canonicalize_args` half is
    the WIRED `envelope_canonical_form` (both adapters forward to the SAME
    `canonical_bytes` JCS primitive), so a fingerprint divergence would mean one
    adapter is NOT forwarding to the real primitive. live deterministic loop."""
    ref = harness.resolve_runtime(REFERENCE)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert ref is not None and rut is not None

    ref_fp = _fingerprint(ref, fvector.tool_name, fvector.args)
    rut_fp = _fingerprint(rut, fvector.tool_name, fvector.args)
    assert isinstance(ref_fp, bytes) and isinstance(rut_fp, bytes)
    result = score_byte_identity(ref_fp, rut_fp)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, fvector.vector.vector_id)


@pytest.mark.parametrize(
    "bvector", _N6_BND, ids=[f"{RUNTIME_UNDER_TEST}-{bv.vector.vector_id}" for bv in _N6_BND]
)
def test_n6_boundary_content_hash_byte_identical(bvector: BoundaryVector) -> None:
    """N6 (b): the `session_boundary_crossed` content_hash is byte-identical
    across runtimes. Cache reset emits the boundary with identical content_hash
    (`runtime-abstraction.md` § N6); both runtimes canonicalize the S5b content
    dict through the SAME WIRED JCS primitive, so the sha256-over-canonical
    content_hash matches by construction. live deterministic loop."""
    ref = harness.resolve_runtime(REFERENCE)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert ref is not None and rut is not None

    # content_hash = sha256(envelope_canonical_form(content)) on each runtime.
    ref_hash = hashlib.sha256(ref.envelope_canonical_form(bvector.content)).digest()
    rut_hash = hashlib.sha256(rut.envelope_canonical_form(bvector.content)).digest()
    result = score_byte_identity(ref_hash, rut_hash)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, bvector.vector.vector_id)


def test_n6_fingerprint_distinct_args_differ() -> None:
    """N6 negative control: distinct args produce a DISTINCT fingerprint (proving
    the byte-identity loop is not vacuously passing on a degenerate constant).
    Both runtimes agree per-input, but two DIFFERENT inputs hash differently."""
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert rut is not None
    fp_a = _fingerprint(rut, "db.read", {"id": "1"})
    fp_b = _fingerprint(rut, "db.read", {"id": "2"})
    result = score_byte_identity(fp_a, fp_b)
    assert result.passed is False, "distinct args MUST produce distinct fingerprints"
    assert result.mismatch is not None


# ---------------------------------------------------------------------------
# Corpus completeness — the three families ship the spec-mandated vector counts.
# ---------------------------------------------------------------------------


def test_n4_n6_corpus_counts_match_spec() -> None:
    """N4=10, N5=15, N6=10 (7 fingerprint + 3 boundary) per
    specs/runtime-abstraction.md § Conformance vectors N1-N6 decoded. A drift
    here means the corpus is incomplete."""
    assert len(n4_vectors()) == 10
    assert len(n5_vectors()) == 15
    assert len(n6_fingerprint_vectors()) + len(n6_boundary_vectors()) == 10


def test_n4_is_structured_payload_only() -> None:
    """N4 STRUCTURED-PAYLOAD-ONLY guard: every N4 vector declares the rendered-
    text field SEMANTICALLY_EQUIVALENT (Phase-03-deferred) — NO vector declares
    it byte-identical, and NO rendered-text byte-identity gate exists in this
    module. This is the mechanical assertion a reviewer sweep confirms: the N4
    byte-identity gate touches ONLY the structured payload."""
    for vector in n4_vectors():
        rendered_tier = vector.field_tiers.get(N4_RENDERED_PATH)
        assert rendered_tier is ContractTier.SEMANTICALLY_EQUIVALENT, (
            f"N4 vector {vector.vector_id} MUST declare rendered text "
            f"SEMANTICALLY_EQUIVALENT (Phase-03-deferred); got {rendered_tier}"
        )


def test_n4_n5_methods_are_substrate_gated() -> None:
    """N4's grant_moment_surface + N5's envelope_check are SUBSTRATE-GATED on the
    rs adapter (raise RuntimeNotReadyError naming the gating shard) — so the
    cross-runtime byte-identity drivers above xfail. This pins the gated state:
    if a future shard WIRES either method, the xfail flips to an unexpected pass
    (xfail strict=False) AND this guard's RuntimeNotReadyError expectation fails,
    surfacing the wiring loudly. Mirrors S3a's wired-set guard, inverted."""
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    py = harness.resolve_runtime(REFERENCE)
    assert isinstance(rut, KailashRsBindingsRuntime)
    assert isinstance(py, KailashPyRuntime)

    # grant_moment_surface (N4) — gated on S6a.
    with pytest.raises(RuntimeNotReadyError) as n4_exc:
        rut.grant_moment_surface({"verdict_kind": "ALLOW"})
    assert "S6a" in str(n4_exc.value)

    # envelope_check (N5) — gated on S6a.
    with pytest.raises(RuntimeNotReadyError) as n5_exc:
        rut.envelope_check({"schema": "envelope/1.0"}, {"kind": "check"})
    assert "S6a" in str(n5_exc.value)


def test_n6_fingerprint_surface_is_wired() -> None:
    """N6's fingerprint + boundary content_hash compose envelope_canonical_form,
    which is WIRED on the rs adapter (not substrate-gated) — so the N6 live
    byte-identity loop genuinely runs (no xfail). This pins the
    method-availability guard: a future shard that gated envelope_canonical_form
    would surface here. Mirrors S3a's wired-set guard."""
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    py = harness.resolve_runtime(REFERENCE)
    assert isinstance(rut, KailashRsBindingsRuntime)
    assert isinstance(py, KailashPyRuntime)
    # envelope_canonical_form runs with no store and does NOT raise
    # RuntimeNotReadyError — it is in the S2a wired set.
    assert rut.envelope_canonical_form({"schema": "envelope/1.0"}) == \
        py.envelope_canonical_form({"schema": "envelope/1.0"})
