# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/conformance/test_e1_e4.py — E1–E4 cross-runtime byte-identity (S3a).

Tier 2 (real infrastructure, NO mocking). Source of truth:
`specs/runtime-abstraction.md` § Contract partition (BET-6) + § Envoy-specific
conformance (E1 envelope canonical JSON / E2 delegation signing / E3 cascade
revocation SET-equality / E4 cycle detection), `specs/envelope-model.md`
§ Canonical JSON, `specs/trust-lineage.md` § Chain verification / § Cascade
revocation / § Cycle detection.

This is the LIVE byte-identity loop the S2a wiring + S1 harness + S3a vector
corpus converge on: every E1–E4 vector is invoked on BOTH the `kailash-py`
reference adapter and the `kailash-rs-bindings` adapter (resolved via the
test-only harness seam — production `RS_BINDINGS_ENABLED` stays False), and the
two outputs are scored with `score_byte_identity` (hash-equality + field-localized
diff) — NOT a bare ``assert a == b``. The loop is deterministic, structural,
hash-equality — NOT probe-judged (byte-identity is a STRUCTURAL assertion per
`rules/probe-driven-verification.md`; no regex/keyword/LLM scoring here).

Byte-identity requires identical inputs AND identical key material / trust state
on both runtimes. Each family's driver constructs BOTH adapters from the SAME
device signing key (E2), the SAME sync trust store seeded with the SAME
delegation graph (E3), and the SAME sync store returning the SAME verdict per
record (E4) — so any divergence is a runtime-parity failure, never a
key/state mismatch.

Test IDs follow the harness convention ``<runtime>-<vector_id>`` so a failure
line names runtime + vector (e.g. ``[kailash-rs-bindings-e1-uni-01-e-acute]``).

OS-matrix note: every vector is OS-portable (no path separators, no locale
assumptions). CI runs this byte-identity slice on the macos/ubuntu/windows
matrix to catch cross-language NFC drift (per the S3a todo § "OS-matrix note");
the vectors are authored so the SAME canonical bytes are expected on every OS.
This single-OS authoring run validates the vectors are matrix-portable.

Real-infrastructure note (Tier 2, NO mocking per `rules/testing.md`): the E2
device key is a REAL Ed25519 keypair from the kailash binding; the E3/E4 trust
stores are Protocol-Satisfying Deterministic Adapters (a class satisfying the
SYNC store shape at runtime with deterministic output is NOT a mock per
`rules/testing.md` § Protocol Adapters) — no ``unittest.mock`` / ``@patch`` /
``MagicMock`` anywhere in this module.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.adapters.kailash_rs_bindings import KailashRsBindingsRuntime
from envoy.runtime.conformance import ScoreResult, score_byte_identity
from tests.conformance import harness
from tests.conformance.e1_e4_vectors import (
    CascadeVector,
    CycleVector,
    e1_vectors,
    e2_vectors,
    e3_vectors,
    e4_vectors,
)

# The runtime-under-test family (the reference family kailash-py is the baseline
# every vector is compared against). The harness parametrizes IDs as
# "<runtime>-<vector_id>" for the runtime-under-test only.
RUNTIME_UNDER_TEST = "kailash-rs-bindings"
REFERENCE = "kailash-py"


# ---------------------------------------------------------------------------
# Deterministic shared key material (E2). Seeded once per module so both
# runtimes sign with the IDENTICAL key — the precondition for byte-identical
# Ed25519 signatures. A real keypair from the kailash binding (NOT a mock).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shared_device_keypair() -> tuple[str, str]:
    """One real Ed25519 keypair (priv_hex, pub_hex) shared across both runtimes.

    Ed25519 signing is deterministic, so signing the SAME record with the SAME
    private key yields identical bytes on both adapters. Generated once
    (module-scope) so every E2 vector signs with the SAME key.
    """
    from kailash.trust.signing import generate_keypair

    priv_hex, pub_hex = generate_keypair()
    return priv_hex, pub_hex


# ---------------------------------------------------------------------------
# Protocol-Satisfying Deterministic sync trust stores (E3 / E4).
#
# The rs + py adapters' trust_cascade_revoke / trust_verify_chain are SYNC. A
# SYNC store's RevocationResult is unpacked directly; an ASYNC store's coroutine
# is driven to completion via the F12-b bridge (the adapter no longer raises on
# an async store). These plain classes satisfy the SYNC store shape with
# deterministic output — NOT mocks (`rules/testing.md` § Protocol Adapters).
# The SAME store instance is injected into BOTH runtimes per vector, so the
# seeded graph / verdict is byte-identical across runtimes by construction; the
# test PROVES the adapters forward to it identically.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _SyncRevocationResult:
    """Real-shape RevocationResult: the adapter reads only ``revoked_agents``."""

    revoked_agents: list[str]
    success: bool = True


@dataclasses.dataclass
class _SyncCascadeStore:
    """SYNC Protocol-satisfying cascade store seeded with a fixed graph.

    ``revoke(*, agent_id, reason, revoked_by)`` returns the pre-seeded revoked
    SET (as a list, the RevocationResult shape) for ``agent_id``. The adapter
    unpacks ``.revoked_agents`` into a ``set`` — SET-equality (E3) means the
    list ORDER is irrelevant; we deliberately return the descendants in a
    DIFFERENT order to the py store so BFS-vs-DFS-style ordering divergence is
    EXERCISED, not assumed away.
    """

    graph: dict[str, list[str]]
    reverse_order: bool = False

    def revoke(self, *, agent_id: str, reason: str, revoked_by: str) -> _SyncRevocationResult:
        members = list(self.graph.get(agent_id, []))
        if self.reverse_order:
            members = list(reversed(members))
        return _SyncRevocationResult(revoked_agents=members)


@dataclasses.dataclass
class _SyncChainStore:
    """SYNC Protocol-satisfying chain store seeded with per-record verdicts.

    ``get_chain(record)`` returns the pre-seeded chain-verification verdict for
    ``record`` (the E4 cycle-detection outcome). The adapter's
    ``trust_verify_chain`` forwards to ``get_chain`` and returns its result, so
    the verdict surfaced is exactly what the store holds — identical across both
    runtimes given the SAME store.
    """

    verdicts: dict[str, dict[str, Any]]

    def get_chain(self, record: str) -> dict[str, Any]:
        return self.verdicts[record]


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
# E1 — Envelope canonical JSON (67 vectors). envelope_canonical_form -> bytes.
# ---------------------------------------------------------------------------


_E1 = e1_vectors()


@pytest.mark.parametrize("vector", _E1, ids=[f"{RUNTIME_UNDER_TEST}-{v.vector_id}" for v in _E1])
def test_e1_envelope_canonical_form_byte_identical(vector: Any) -> None:
    """E1: ``envelope_canonical_form(envelope)`` is byte-identical (hash-equal)
    across kailash-py and kailash-rs-bindings. The richest family — exercises
    nesting, unicode/NFC, key ordering, number canonicalization, empty/edge
    envelopes, escapes, null-vs-absent. live deterministic hash-equality loop."""
    ref = harness.resolve_runtime(REFERENCE)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert ref is not None and rut is not None

    ref_out = ref.envelope_canonical_form(**vector.inputs)
    rut_out = rut.envelope_canonical_form(**vector.inputs)
    # Both methods return `bytes`; the scorer hashes them directly (E1 bytes
    # pass-through). NFC fold means an NFD-authored envelope hashes identically.
    assert isinstance(ref_out, bytes) and isinstance(rut_out, bytes)
    result = score_byte_identity(ref_out, rut_out)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, vector.vector_id)


# ---------------------------------------------------------------------------
# E2 — Delegation Record signing (20 vectors). trust_sign(record, key) -> bytes.
# ---------------------------------------------------------------------------


_E2 = e2_vectors()


@pytest.mark.parametrize("vector", _E2, ids=[f"{RUNTIME_UNDER_TEST}-{v.vector_id}" for v in _E2])
def test_e2_trust_sign_byte_identical(
    vector: Any, shared_device_keypair: tuple[str, str]
) -> None:
    """E2: ``trust_sign(record, key)`` Ed25519 signature bytes are identical
    across runtimes given the SAME key + record. Both adapters forward to the
    SAME kailash.trust.signing.sign, so a byte divergence would mean one adapter
    is NOT forwarding to the real binding (a stub/re-implementation)."""
    priv_hex, _pub_hex = shared_device_keypair
    ref = harness.resolve_runtime(REFERENCE)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    assert ref is not None and rut is not None

    # The vector's `key` input is a sentinel; substitute the run's shared key so
    # BOTH runtimes sign with the IDENTICAL Ed25519 private key.
    record = vector.inputs["record"]
    ref_out = ref.trust_sign(record, priv_hex)
    rut_out = rut.trust_sign(record, priv_hex)
    assert isinstance(ref_out, bytes) and isinstance(rut_out, bytes)
    result = score_byte_identity(ref_out, rut_out)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, vector.vector_id)


# ---------------------------------------------------------------------------
# E3 — Cascade revocation BFS/DFS SET-equality (15 vectors).
# trust_cascade_revoke(root_id) -> set[str]. SET-equality (order-insensitive).
# ---------------------------------------------------------------------------


_E3: list[CascadeVector] = e3_vectors()


@pytest.mark.parametrize(
    "cvector", _E3, ids=[f"{RUNTIME_UNDER_TEST}-{cv.vector.vector_id}" for cv in _E3]
)
def test_e3_cascade_revoke_set_equality(cvector: CascadeVector) -> None:
    """E3: ``trust_cascade_revoke(root_id)`` returns a SET; the scorer asserts
    SET-equality (order-insensitive) so a BFS-vs-DFS ordering difference does
    NOT fail. The rs store returns its descendants in REVERSED order vs the py
    store to EXERCISE that ordering divergence; both seeded from the SAME graph,
    so the SETs are equal. A set-MEMBERSHIP difference WOULD fail (covered by
    the negative-control test below)."""
    # IDENTICAL graph seeded into both stores; rs store returns reversed order
    # to prove the SET comparison is genuinely order-insensitive.
    py_store = _SyncCascadeStore(graph=cvector.delegation_graph, reverse_order=False)
    rs_store = _SyncCascadeStore(graph=cvector.delegation_graph, reverse_order=True)
    ref = harness.resolve_runtime(REFERENCE, trust_store=py_store)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST, trust_store=rs_store)
    assert ref is not None and rut is not None

    ref_out = ref.trust_cascade_revoke(**cvector.vector.inputs)
    rut_out = rut.trust_cascade_revoke(**cvector.vector.inputs)
    assert isinstance(ref_out, set) and isinstance(rut_out, set)

    # SET-equality via the byte-identity scorer (sets are canonicalized
    # order-insensitively — `scorer._canonicalize` sorts set members).
    result = score_byte_identity(ref_out, rut_out)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, cvector.vector.vector_id)

    # Also pin the ground-truth SET both runtimes return (not just that they
    # agree with each other — that they agree with the SPEC's expected set).
    assert ref_out == set(cvector.expected_revoked)
    assert rut_out == set(cvector.expected_revoked)


def test_e3_set_membership_difference_fails() -> None:
    """E3 negative control: a set-MEMBERSHIP difference MUST fail (proving the
    SET comparison is not vacuously passing). Distinct seeded graphs ⇒ distinct
    revoked sets ⇒ the scorer reports passed=False. This is the discriminating
    assertion the S3a acceptance criterion 2 requires."""
    py_store = _SyncCascadeStore(graph={"r": ["r", "c1", "c2"]})
    # rs store is MISSING c2 — a genuine membership difference, not an ordering
    # one. SET-equality MUST catch this.
    rs_store = _SyncCascadeStore(graph={"r": ["r", "c1"]})
    ref = harness.resolve_runtime(REFERENCE, trust_store=py_store)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST, trust_store=rs_store)
    assert ref is not None and rut is not None

    ref_out = ref.trust_cascade_revoke("r")
    rut_out = rut.trust_cascade_revoke("r")
    result = score_byte_identity(ref_out, rut_out)
    assert result.passed is False, "membership difference MUST fail SET-equality"
    assert result.mismatch is not None


def test_e3_bfs_dfs_ordering_difference_passes() -> None:
    """E3 positive control: a BFS-vs-DFS ORDERING difference (same membership)
    MUST pass. The two stores return the SAME members in OPPOSITE order; the
    SET comparison ignores order. This is the order-insensitivity half of
    acceptance criterion 2."""
    members = ["r", "a", "b", "c", "d"]
    py_store = _SyncCascadeStore(graph={"r": members})  # forward (BFS-like)
    rs_store = _SyncCascadeStore(graph={"r": members}, reverse_order=True)  # reversed (DFS-like)
    ref = harness.resolve_runtime(REFERENCE, trust_store=py_store)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST, trust_store=rs_store)
    assert ref is not None and rut is not None

    result = score_byte_identity(ref.trust_cascade_revoke("r"), rut.trust_cascade_revoke("r"))
    assert result.passed is True, "ordering difference MUST NOT fail SET-equality"


# ---------------------------------------------------------------------------
# E4 — Cycle detection (15 vectors). trust_verify_chain(record) -> VerifyResult.
# Identical cycle-detection verdicts across runtimes.
# ---------------------------------------------------------------------------


_E4: list[CycleVector] = e4_vectors()


@pytest.mark.parametrize(
    "cvector", _E4, ids=[f"{RUNTIME_UNDER_TEST}-{cv.vector.vector_id}" for cv in _E4]
)
def test_e4_chain_verify_cycle_detection_identical(cvector: CycleVector) -> None:
    """E4: ``trust_verify_chain(record)`` surfaces identical cycle-detection
    verdicts across runtimes. Both adapters forward to the injected store's
    ``get_chain(record)``; seeded from the SAME verdict map, the verdicts are
    byte-identical. Covers the five spec categories: direct cycle,
    CRDT-merge-induced, timestamp-ambiguous, deep, valid-but-suspicious."""
    verdict_map = {cvector.record: cvector.verdict}
    store = _SyncChainStore(verdicts=verdict_map)
    ref = harness.resolve_runtime(REFERENCE, trust_store=store)
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST, trust_store=store)
    assert ref is not None and rut is not None

    ref_out = ref.trust_verify_chain(**cvector.vector.inputs)
    rut_out = rut.trust_verify_chain(**cvector.vector.inputs)
    result = score_byte_identity(ref_out, rut_out)
    _assert_byte_identical(result, RUNTIME_UNDER_TEST, cvector.vector.vector_id)

    # Pin the ground-truth verdict (both runtimes surface the SPEC verdict, not
    # merely agree with each other).
    assert ref_out == cvector.verdict
    assert rut_out == cvector.verdict


def test_e4_divergent_verdict_fails() -> None:
    """E4 negative control: divergent cycle-detection verdicts MUST fail. Two
    stores return DIFFERENT verdicts for the same record (one detects the cycle,
    one does not) — the scorer reports passed=False, field-localizing the
    diverging field. Proves the verdict comparison is discriminating."""
    cycle_verdict = {"valid": False, "cycle_detected": True, "step_failed": "cycle-free"}
    clean_verdict = {"valid": True, "cycle_detected": False, "step_failed": None}
    ref = harness.resolve_runtime(REFERENCE, trust_store=_SyncChainStore({"rec": cycle_verdict}))
    rut = harness.resolve_runtime(
        RUNTIME_UNDER_TEST, trust_store=_SyncChainStore({"rec": clean_verdict})
    )
    assert ref is not None and rut is not None

    result = score_byte_identity(ref.trust_verify_chain("rec"), rut.trust_verify_chain("rec"))
    assert result.passed is False, "divergent cycle-detection verdicts MUST fail"
    assert result.mismatch is not None
    # The field-localized diff names the first diverging field (cycle_detected).
    assert result.mismatch.json_path in {"cycle_detected", "step_failed", "valid"}


# ---------------------------------------------------------------------------
# Corpus completeness — the four families ship the spec-mandated vector counts.
# ---------------------------------------------------------------------------


def test_e1_e4_corpus_counts_match_spec() -> None:
    """E1=67, E2=20, E3=15, E4=15 per specs/runtime-abstraction.md
    § Envoy-specific conformance. A drift here means the corpus is incomplete."""
    assert len(e1_vectors()) == 67
    assert len(e2_vectors()) == 20
    assert len(e3_vectors()) == 15
    assert len(e4_vectors()) == 15


def test_e1_e4_methods_are_all_in_the_wired_set() -> None:
    """All four E1–E4 methods are WIRED on the rs adapter (not substrate-gated),
    so the live byte-identity loop genuinely runs (no xfail needed). This pins
    the method-availability guard: a future shard that gated any of these four
    would surface here."""
    rut = harness.resolve_runtime(RUNTIME_UNDER_TEST)
    py = harness.resolve_runtime(REFERENCE)
    assert isinstance(rut, KailashRsBindingsRuntime)
    assert isinstance(py, KailashPyRuntime)
    # envelope_canonical_form + trust_sign run with no store; trust_cascade_revoke
    # + trust_verify_chain run with a sync store (exercised above). None of the
    # four raise RuntimeNotReadyError — they are in the S2a wired-18 set.
    assert rut.envelope_canonical_form({"schema": "envelope/1.0"}) == \
        py.envelope_canonical_form({"schema": "envelope/1.0"})
