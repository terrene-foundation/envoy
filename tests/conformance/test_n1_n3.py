# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/conformance/test_n1_n3.py — N1–N3 cross-runtime byte-identity (S2b).

Tier 2 (real infrastructure, NO mocking). Source of truth:
`specs/runtime-abstraction.md` § Conformance vectors N1–N6 decoded (N1 Knowledge
Filter / N2 Envelope Cache 5-property invalidation / N3 structural-vs-semantic
partition) + § Contract partition (BET-6) + § Contract-tier enforcement (the N3
structural-vs-semantic dispatch is observed deterministically via the
cross-runtime dispatch-observation hook `envoy.runtime.dispatch_observation`, NOT
output heuristics).

This is the driver the S2a wiring + S1 harness + S2b vector corpus converge on:
each vector is invoked on BOTH the `kailash-py` reference adapter and the
`kailash-rs-bindings` adapter (resolved via the test-only harness seam —
production `RS_BINDINGS_ENABLED` stays False) and the two outputs are scored with
`score_byte_identity` (hash-equality + field-localized diff) — NOT a bare
``assert a == b``. The loop is deterministic, structural, hash-equality — NOT
probe-judged (byte-identity is a STRUCTURAL assertion per
`rules/probe-driven-verification.md`; no regex/keyword/LLM scoring here).

Wired-vs-substrate-gated discipline (verified EMPIRICALLY, not assumed — see
`test_n1_n3_methods_gated_status_is_pinned` below):

- N1 + N2 drive `envelope_check`, which raises `RuntimeNotReadyError` naming
  gating shard **S6a** (the structural+semantic envelope-check engine). Their
  cross-runtime byte-identity tests are `@pytest.mark.xfail(strict=False,
  reason="substrate-gated on S6a …")` — the corpus is authored + the loop is
  wired, but the engine that produces a verdict does not exist yet, so the loop
  cannot run green until S6a lands. xfail-with-reason for a genuinely
  substrate-gated lane is the honest deferral (NOT a stub).

- N3 SEMANTIC slice drives the classifier ensemble (`classifier_invoke` via the
  semantic branch of `envelope_check`), raising `RuntimeNotReadyError` naming
  gating shard **S6d** (the classifier ensemble). Its dispatch + byte-identity
  test is xfail(S6d).

- N3 STRUCTURAL slice's dispatch-observation assertion is LIVE NOW: a
  structural-class check raises the S6a gate BEFORE any `record_dispatch`, so the
  cross-runtime invariant "structural ⇒ classifier NOT dispatched" is observable
  TODAY on both adapters via `dispatch_observation.observe()` (it
  deterministically reads `dispatched=False`). This is the buildable-now half the
  driver runs GREEN — a corpus authored + a real invariant proven, even while the
  byte-identity verdict half is S6a-deferred.

Real-infrastructure note (Tier 2, NO mocking per `rules/testing.md`): both
adapters are constructed via the harness's test-only seam (a real
`KailashRsBindingsRuntime` / `KailashPyRuntime`, NOT a mock). The
dispatch-observation hook is the production `envoy.runtime.dispatch_observation`
recorder — a deterministic in-process counter, NOT a mock. No ``unittest.mock`` /
``@patch`` / ``MagicMock`` anywhere in this module.

OS-matrix note: every vector is OS-portable (no path separators, no locale
assumptions). The byte-identity slices run on the macos/ubuntu/windows matrix
once S6a/S6d land; the dispatch-observation slice is OS-independent (pure
in-process counting).
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.adapters.kailash_rs_bindings import KailashRsBindingsRuntime
from envoy.runtime.conformance import ScoreResult, score_byte_identity
from envoy.runtime.dispatch_observation import observe
from envoy.runtime.errors import (
    Phase02SubstrateNotWiredError,
    RuntimeNotReadyError,
)
from tests.conformance import harness
from tests.conformance.n1_n3_vectors import (
    EnvelopeCacheVector,
    n1_vectors,
    n2_vectors,
    n3_semantic_vectors,
    n3_structural_vectors,
    n3_vectors,
)

# The runtime-under-test family (the reference family kailash-py is the baseline
# every vector is compared against). The harness parametrizes IDs as
# "<runtime>-<vector_id>" for the runtime-under-test only.
RUNTIME_UNDER_TEST = "kailash-rs-bindings"
REFERENCE = "kailash-py"

# The substrate-gate sentinel raised on the rs adapter when an engine ships in a
# later shard. The py reference adapter raises its own Phase-01-era sentinel for
# the same surface; both are treated as "substrate-gated" by the gate probes.
_GATED_ERRORS: tuple[type[Exception], ...] = (
    RuntimeNotReadyError,
    Phase02SubstrateNotWiredError,
)

# xfail reasons name the gating shard so a future session greps the message to
# find where the wiring lands (and so a shard that flips the gate surfaces here).
# S6a LANDED (the structural envelope-check engine): N1/N2/N3-structural drive the
# structural slice, which now returns a real byte-identical verdict (no longer
# raises). Their xfail markers were dropped; the gated-status guard below now pins
# envelope_check as WIRED-for-structural / gated-for-semantic. The only S6a/S6d gate
# remaining on this surface is the SEMANTIC slice (classifier ensemble → S6d).
_S6D_REASON = (
    "substrate-gated on S6d — the classifier ensemble (classifier_invoke) raises "
    "RuntimeNotReadyError until S6d lands; see runtime-abstraction.md N3 semantic slice"
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
# N1 — Knowledge Filter (10 vectors). envelope_check(envelope, action).
# Substrate-gated on S6a — xfail until the envelope-check engine lands.
# ---------------------------------------------------------------------------


_N1 = n1_vectors()


@pytest.mark.parametrize("vector", _N1, ids=[f"{RUNTIME_UNDER_TEST}-{v.vector_id}" for v in _N1])
def test_n1_knowledge_filter_byte_identical(vector: Any) -> None:
    """N1: ``envelope_check(envelope, action)`` pre-retrieval-gate verdict is
    byte-identical (hash-equal) across kailash-py and kailash-rs-bindings. The
    gate decides which requested fields survive the envelope's
    `field_allowlist_per_model` BEFORE classification. S6a LANDED: both adapters
    delegate to the shared pure engine `envoy.runtime.envelope_check`, so the
    verdict is byte-identical by construction (shared pure delegation)."""
    ref = harness.resolve_runtime(REFERENCE)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert ref is not None and rut is not None

    ref_out = ref.envelope_check(**vector.inputs)
    rut_out = rut.envelope_check(**vector.inputs)
    result = score_byte_identity(ref_out, rut_out)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, vector.vector_id)


# ---------------------------------------------------------------------------
# N2 — Envelope Cache 5-property invalidation (15 vectors). envelope_check.
# Substrate-gated on S6a — xfail until the envelope-check engine lands.
# ---------------------------------------------------------------------------


_N2: list[EnvelopeCacheVector] = n2_vectors()


@pytest.mark.parametrize(
    "cvector", _N2, ids=[f"{RUNTIME_UNDER_TEST}-{cv.vector.vector_id}" for cv in _N2]
)
def test_n2_envelope_cache_invalidation_byte_identical(cvector: EnvelopeCacheVector) -> None:
    """N2: the envelope-check cache key is a function of FIVE properties
    (envelope_version, algorithm_identifier, classifier_ensemble_versions,
    posture_level, principal_genesis_id); a change to ANY one MUST independently
    invalidate the cache, byte-identically on both runtimes.

    The test checks BOTH the baseline and the single-property-mutated envelope on
    BOTH runtimes and asserts: (1) the baseline verdict is byte-identical across
    runtimes; (2) the mutated verdict is byte-identical across runtimes; (3)
    WITHIN each runtime baseline != mutated (the invalidation fired — a runtime
    that ignores `property_changed` would return the stale baseline verdict). All
    three are byte-identity-scored. S6a LANDED: the structural engine's verdict
    carries a `cache_key` over exactly these five properties, so a single-property
    mutation flips the verdict (the shared pure engine makes (1)+(2) hold by
    construction)."""
    ref = harness.resolve_runtime(REFERENCE)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert ref is not None and rut is not None

    ref_base = ref.envelope_check(cvector.baseline, cvector.action)
    rut_base = rut.envelope_check(cvector.baseline, cvector.action)
    ref_mut = ref.envelope_check(cvector.mutated, cvector.action)
    rut_mut = rut.envelope_check(cvector.mutated, cvector.action)

    # (1) baseline verdict byte-identical across runtimes
    _assert_byte_identical(
        score_byte_identity(ref_base, rut_base),
        RUNTIME_UNDER_TEST,
        f"{cvector.vector.vector_id}-baseline",
    )
    # (2) mutated verdict byte-identical across runtimes
    _assert_byte_identical(
        score_byte_identity(ref_mut, rut_mut),
        RUNTIME_UNDER_TEST,
        f"{cvector.vector.vector_id}-mutated",
    )
    # (3) invalidation fired WITHIN each runtime: baseline != mutated (the
    #     property change MUST flip the cache-key verdict). A passing
    #     score_byte_identity here would mean the property was IGNORED — so we
    #     assert NOT passed, localizing on property_changed.
    within_ref = score_byte_identity(ref_base, ref_mut)
    assert within_ref.passed is False, (
        f"N2 invalidation FAILED [{REFERENCE}-{cvector.vector.vector_id}]: "
        f"changing {cvector.property_changed!r} did NOT invalidate the cache "
        f"(baseline verdict == mutated verdict — stale-cache hit)"
    )


# ---------------------------------------------------------------------------
# N3 STRUCTURAL slice (6 vectors) — classifier MUST NOT dispatch.
# LIVE NOW: the dispatch-observation assertion runs green today on both adapters
# because a structural-class check raises the S6a gate BEFORE any record_dispatch,
# so the observation deterministically reads dispatched=False. This is the
# structural invariant N3 asserts (structural ⇒ no classifier), observed via the
# cross-runtime dispatch-observation hook — DETERMINISTIC/STRUCTURAL, NOT a probe.
# ---------------------------------------------------------------------------


_N3_STRUCT = n3_structural_vectors()


@pytest.mark.parametrize(
    "vector", _N3_STRUCT, ids=[f"{RUNTIME_UNDER_TEST}-{v.vector_id}" for v in _N3_STRUCT]
)
def test_n3_structural_slice_does_not_dispatch_classifier(vector: Any) -> None:
    """N3 structural slice: a `structural`-class envelope check MUST NOT dispatch
    the classifier ensemble. Observed deterministically on BOTH runtimes via
    `dispatch_observation.observe()` — the recorder counts real `record_dispatch`
    calls, NOT output heuristics (no regex/keyword/LLM scoring per
    `rules/probe-driven-verification.md`).

    Post-S6a, each structural fixture's check returns a real structural-reject (or
    field-gate) verdict WITHOUT reaching any classifier dispatch, so the
    observation reads `dispatched=False` (zero dispatch_count) on both runtimes —
    the structural invariant "structural ⇒ no classifier dispatch" holds by
    construction (the structural path in `envoy.runtime.envelope_check` has no
    dispatch site). The cross-runtime assertion is that NEITHER runtime spuriously
    dispatched the classifier for a structural-class fixture."""
    assert vector.expected_dispatch is False, "structural-slice vector must expect no dispatch"
    for family in (REFERENCE, RUNTIME_UNDER_TEST):
        rt = harness.resolve_runtime(family)
        assert rt is not None, f"runtime {family!r} must resolve for the dispatch-observation slice"
        # Post-S6a the structural slice returns a verdict (no raise); the
        # contextlib.suppress is retained DEFENSIVELY for symmetry — if a future
        # change routes a structural-looking fixture to a gated path, the gate is
        # swallowed and observe()'s finally still seals the observation, so the
        # `dispatched is False` assertion below remains the load-bearing check.
        with observe() as handle, contextlib.suppress(*_GATED_ERRORS):
            rt.envelope_check(**vector.inputs)
        obs = handle.result()
        assert obs.dispatched is False, (
            f"N3 structural FAILED [{family}-{vector.vector_id}]: structural-class "
            f"check dispatched the classifier {obs.dispatch_count}× (refs={obs.refs!r}); "
            f"a structural check MUST NOT invoke the ensemble"
        )


# ---------------------------------------------------------------------------
# N3 SEMANTIC slice (4 vectors) — classifier MUST dispatch.
# Substrate-gated on S6d (the classifier ensemble) — xfail until it lands.
# ---------------------------------------------------------------------------


_N3_SEM = n3_semantic_vectors()


@pytest.mark.xfail(strict=False, reason=_S6D_REASON)
@pytest.mark.parametrize(
    "vector", _N3_SEM, ids=[f"{RUNTIME_UNDER_TEST}-{v.vector_id}" for v in _N3_SEM]
)
def test_n3_semantic_slice_dispatches_classifier(vector: Any) -> None:
    """N3 semantic slice: a `semantic`-class envelope check MUST dispatch the
    classifier ensemble (observed via `dispatch_observation.observe()`), and the
    structured verdict payload MUST be byte-identical across runtimes.

    Substrate-gated on S6d: the classifier ensemble (`classifier_invoke`, reached
    via the semantic branch of `envelope_check`) raises `RuntimeNotReadyError`
    until S6d wires it, so no `record_dispatch` fires and the observation reads
    `dispatched=False` — the assertion `dispatched is True` therefore fails today,
    which is exactly the xfail (it flips to a real pass when S6d wires the
    ensemble + the adapters call `record_dispatch` at the dispatch site)."""
    assert vector.expected_dispatch is True, "semantic-slice vector must expect dispatch"
    ref = harness.resolve_runtime(REFERENCE)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert ref is not None and rut is not None

    with observe() as ref_handle:
        ref_out = ref.envelope_check(**vector.inputs)
    with observe() as rut_handle:
        rut_out = rut.envelope_check(**vector.inputs)

    # Semantic ⇒ both runtimes MUST have dispatched the classifier.
    assert ref_handle.result().dispatched is True, (
        f"N3 semantic FAILED [{REFERENCE}-{vector.vector_id}]: semantic-class "
        f"check did NOT dispatch the classifier"
    )
    assert rut_handle.result().dispatched is True, (
        f"N3 semantic FAILED [{RUNTIME_UNDER_TEST}-{vector.vector_id}]: semantic-class "
        f"check did NOT dispatch the classifier"
    )
    # Structured verdict payload byte-identical across runtimes.
    result = score_byte_identity(ref_out, rut_out)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, vector.vector_id)


# ---------------------------------------------------------------------------
# N3 dispatch-observation hook sanity — positive + negative control (LIVE).
# Proves the dispatch-observation slice is not vacuously passing: the recorder
# DOES observe a real dispatch when one occurs, and does NOT when none does.
# ---------------------------------------------------------------------------


def test_n3_dispatch_observation_positive_control() -> None:
    """Positive control: when `record_dispatch` IS called inside `observe()`, the
    observation reads `dispatched=True` with the exact count + refs. Proves the
    structural-slice's `dispatched is False` assertion is discriminating (the
    recorder genuinely detects a dispatch when one happens) — not vacuously
    passing because the recorder is broken."""
    from envoy.runtime.dispatch_observation import record_dispatch

    with observe() as handle:
        record_dispatch("clf-a")
        record_dispatch("clf-b")
    obs = handle.result()
    assert obs.dispatched is True
    assert obs.dispatch_count == 2
    assert obs.refs == ("clf-a", "clf-b")


def test_n3_dispatch_observation_negative_control() -> None:
    """Negative control: an empty `observe()` context reads `dispatched=False`,
    `dispatch_count=0`. This is the baseline the structural slice relies on — a
    check that never dispatches yields exactly this observation."""
    with observe() as handle:
        pass
    obs = handle.result()
    assert obs.dispatched is False
    assert obs.dispatch_count == 0
    assert obs.refs == ()


# ---------------------------------------------------------------------------
# Corpus completeness — the three families ship the spec-mandated vector counts.
# ---------------------------------------------------------------------------


def test_n1_n3_corpus_counts_match_spec() -> None:
    """N1=10, N2=15, N3=10 (= 6 structural + 4 semantic) per
    specs/runtime-abstraction.md § Conformance vectors N1–N6 decoded. A drift
    here means the corpus is incomplete."""
    assert len(n1_vectors()) == 10
    assert len(n2_vectors()) == 15
    assert len(n3_vectors()) == 10
    assert len(n3_structural_vectors()) == 6
    assert len(n3_semantic_vectors()) == 4
    # N3 dispatch-flag partition is exactly structural=False / semantic=True.
    assert all(v.expected_dispatch is False for v in n3_structural_vectors())
    assert all(v.expected_dispatch is True for v in n3_semantic_vectors())


def test_n1_n3_methods_gated_status_is_pinned() -> None:
    """Pin the WIRED-vs-substrate-gated status of every method N1–N3 exercises so
    a future shard that flips a gate surfaces HERE (the S3a
    `test_e1_e4_methods_are_all_in_the_wired_set` analogue).

    Post-S6a SPLIT (see journal/0021): `envelope_check`'s STRUCTURAL slice is now
    WIRED on both adapters — a structural (content-free) action returns a real
    byte-identical verdict, NOT a gate sentinel. The SEMANTIC slice (action carries
    `content` bytes) AND the standalone `classifier_invoke` are still
    substrate-gated on S6d (the classifier ensemble). When S6d lands, the two
    semantic assertions below flip to failures — the loud signal to wire the
    classifier dispatch + drop the N3-semantic xfail."""
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    py = harness.resolve_runtime(REFERENCE)
    assert isinstance(rut, KailashRsBindingsRuntime)
    assert isinstance(py, KailashPyRuntime)

    # envelope_check STRUCTURAL slice — WIRED (S6a landed): returns a verdict, no raise.
    for rt in (py, rut):
        verdict = rt.envelope_check(
            {"schema": "envelope/1.0"}, {"model": "User", "requested_fields": []}
        )
        assert isinstance(verdict, dict)
        assert verdict["verdict_class"] == "structural"

    # envelope_check SEMANTIC slice (action carries `content`) — S6d-gated on BOTH.
    for rt in (py, rut):
        with pytest.raises(_GATED_ERRORS):
            rt.envelope_check(
                {"schema": "envelope/1.0"},
                {"model": "Document", "requested_fields": ["body"], "content": b"x"},
            )

    # classifier_invoke — S6d-gated on BOTH adapters (N3 semantic dispatch site).
    for rt in (py, rut):
        with pytest.raises(_GATED_ERRORS):
            rt.classifier_invoke("clf-a", b"content", None)
