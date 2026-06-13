# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/conformance/e5_e7_vectors.py — E5/E6/E7 byte-identity vector corpus (S3b).

Source of truth: ``specs/runtime-abstraction.md`` § Envoy-specific conformance
(E5 subset-proof verification / E6 two-phase signing orphan resolution / E7
ledger head-commitment monotonicity), ``specs/sub-agent-delegation.md``
§ ``is_subset_envelope`` (E5), ``specs/ledger.md`` § Two-phase signing (E6) +
§ Head commitment (E7), ``specs/independent-verifier.md`` ~198-200 (E7 shared
corpus, reused by the S7v Rust verifier).

This module is the S3b sibling of ``e1_e4_vectors.py`` (S3a). The three families
split along the wired-vs-substrate-gated boundary the S2a rs adapter draws:

- **E5 — subset-proof verification** (``trust_verify_subset_proof(parent, sub)``).
  20 ADVERSARIAL vectors: each is a FORGED subset-proof a correct verifier MUST
  reject. The ``runtime_verification_signature`` bytes E5 hashes are produced by
  the sub-agent-delegation subset-proof verifier, which is **substrate-gated on
  shard S6c** (the rs adapter raises ``RuntimeNotReadyError`` naming S6c — see
  ``kailash_rs_bindings.trust_verify_subset_proof``). The full adversarial corpus
  is authored NOW so it is ready the moment the S6c engine lands; the
  cross-runtime byte-identity test is ``xfail(strict=False)`` until then.

- **E6 — two-phase signing orphan resolution** (``phase_a_sign_intent`` /
  ``phase_b_sign_outcome`` / ``phase_a_orphan_resolve``). Identical Phase-A
  intent / Phase-B outcome linkage records. The two-phase signing engine is
  **substrate-gated on shard S6a** (the rs adapter raises ``RuntimeNotReadyError``
  naming S6a). Corpus authored NOW; cross-runtime test ``xfail`` until S6a lands.

- **E7 — ledger head-commitment monotonicity** (``head_commitment()``, async).
  ``head_commitment`` is **WIRED** in S2a (forwards to the injected
  ``EnvoyLedger.head_commitment``); it is gated ONLY when no ledger is injected.
  The S3b driver injects ONE shared ``EnvoyLedger`` into both runtimes, so the
  commitment is byte-identical by construction, AND asserts ``head_sequence`` is
  monotonic non-decreasing across the append sequence — this is the LIVE
  buildable core of S3b.

E7 SHARED-CORPUS DECISION (open question #2, resolved at authoring time)
-----------------------------------------------------------------------
The E7 vectors live in ONE separately-consumable JSON fixture —
``tests/fixtures/conformance/e7/head_commitment_vectors.json`` — that this Python
harness loads AND the S7v Rust independent verifier
(``terrene-foundation/envoy-ledger-verifier``) will vendor. We chose the
**vendored versioned-fixture (JSON data file)** packaging over a git-submodule
pin because (a) the corpus is small, pure data (append sequences + expected
sequence progression), so a submodule's network/auth/ref-pinning machinery buys
nothing; (b) a JSON data file is language-neutral — the Rust verifier reads the
identical bytes with no Python dependency; (c) versioning is the file's git
history in this repo, which S7v vendors at a known commit. The fixture is the
SINGLE source of truth so the two corpora never diverge (the
``specs/independent-verifier.md`` ~275 + M1-todo open question #2 concern).
E7 vectors are NOT hardcoded inline here — they are loaded from the fixture, so
S7v never has to re-author them.

Real-infrastructure note (Tier 2, NO mocking per ``rules/testing.md``): E7 uses a
real ``EnvoyLedger`` backed by kailash's ``InMemoryAuditStore`` +
``InMemoryKeyManager`` (kailash's own zero-dependency test fixtures — real
crypto, NOT mocks). E5/E6 vectors are pure deterministic data (no key material;
the adversarial subset-proofs and two-phase records are plain dicts). No
``unittest.mock`` / ``@patch`` / ``MagicMock`` anywhere in this module.

CLI-neutral prose per ``rules/cross-cli-artifact-hygiene.md``.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from envoy.runtime.conformance import ConformanceVector

# ---------------------------------------------------------------------------
# E5 — Subset-proof verification (20 ADVERSARIAL vectors).
#
# Method: trust_verify_subset_proof(parent, sub) -> VerifyResult carrying the
# runtime_verification_signature E5 hashes. Per specs/sub-agent-delegation.md
# § is_subset_envelope: a sub-agent's envelope MUST be a subset of (no wider
# than) the parent's along EVERY dimension. A FORGED subset-proof claims a
# sub-envelope that is actually a SUPERSET (or otherwise escalates) along some
# dimension; a correct verifier MUST reject it, and MUST reject it
# BYTE-IDENTICALLY on both runtimes (the rejection verdict + the
# runtime_verification_signature are byte-identical).
#
# Each vector is the (parent, sub) input pair plus the dimension the forgery
# escalates (carried for the ground-truth assertion + human auditing). The
# corpus is authored against the subset-proof verifier that ships in shard S6c;
# the cross-runtime test is xfail(strict=False) until S6c wires the engine.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class SubsetProofVector:
    """An E5 adversarial subset-proof vector.

    Carries the wrapped ``ConformanceVector`` (for harness ID emission) plus the
    ``escalated_dimension`` the forged ``sub`` envelope widens beyond ``parent``
    (the ground-truth a correct verifier rejects on) and ``expect_valid`` — the
    ground-truth verdict (always ``False`` for the adversarial corpus: every
    vector here is a forgery that MUST fail). Authored as a wrapper (not extra
    ``ConformanceVector`` fields) so the corpus-row schema stays unchanged —
    mirrors S3a's ``CascadeVector`` / ``CycleVector`` pattern.
    """

    vector: ConformanceVector
    escalated_dimension: str
    expect_valid: bool = False


def e5_vectors() -> list[SubsetProofVector]:
    """The full E5 family — 20 ADVERSARIAL subset-proof byte-identity vectors.

    Each ``sub`` envelope escalates ONE (or more) dimension beyond ``parent``:
    financial ceilings, data-access scope, tool allowlist, capability set,
    posture level, delegation depth, time/expiry, or tenant scope. A correct
    subset-proof verifier rejects every one, byte-identically across runtimes.
    The ``escalated_dimension`` is the spec dimension the forgery widens.
    """
    # A baseline parent envelope every forged sub is compared against. The shape
    # mirrors the envelope dimensions specs/envelope-model.md enumerates; the
    # subset-proof verifier (S6c) reads these dimensions.
    parent: dict[str, Any] = {
        "schema": "envelope/1.0",
        "financial": {"max_micros": 5_000_000},
        "data_access": ["public", "internal"],
        "tools": ["read", "list"],
        "capabilities": ["c.read", "c.list"],
        "posture_level": "SUPERVISED",
        "delegation_depth": 2,
        "expiry": "2026-12-31T23:59:59.000000Z",
        "tenant": "tenant-a",
    }

    # (vector_id, escalated_dimension, sub-envelope forgery)
    cases: list[tuple[str, str, dict[str, Any]]] = [
        # --- Financial-ceiling escalations.
        ("e5-01-financial-higher-ceiling", "financial",
         {**parent, "financial": {"max_micros": 10_000_000}}),  # > parent 5M
        ("e5-02-financial-negative-bypass", "financial",
         {**parent, "financial": {"max_micros": -1}}),  # negative ⇒ unbounded-bypass attempt
        ("e5-03-financial-missing-ceiling", "financial",
         {**parent, "financial": {}}),  # no ceiling ⇒ unbounded
        # --- Data-access scope widening.
        ("e5-04-data-access-add-confidential", "data_access",
         {**parent, "data_access": ["public", "internal", "confidential"]}),
        ("e5-05-data-access-replace-broader", "data_access",
         {**parent, "data_access": ["restricted"]}),  # scope not in parent
        ("e5-06-data-access-wildcard", "data_access",
         {**parent, "data_access": ["*"]}),  # wildcard escalation
        # --- Tool allowlist widening.
        ("e5-07-tools-add-write", "tools",
         {**parent, "tools": ["read", "list", "write"]}),  # write not in parent
        ("e5-08-tools-add-delete", "tools",
         {**parent, "tools": ["read", "delete"]}),  # delete not in parent
        ("e5-09-tools-wildcard", "tools",
         {**parent, "tools": ["*"]}),
        # --- Capability-set widening.
        ("e5-10-cap-add-write", "capabilities",
         {**parent, "capabilities": ["c.read", "c.list", "c.write"]}),
        ("e5-11-cap-add-admin", "capabilities",
         {**parent, "capabilities": ["c.admin"]}),  # admin not in parent
        # --- Posture-level escalation (less restrictive than parent).
        ("e5-12-posture-autonomous", "posture_level",
         {**parent, "posture_level": "AUTONOMOUS"}),  # weaker than SUPERVISED
        ("e5-13-posture-delegated", "posture_level",
         {**parent, "posture_level": "DELEGATED"}),
        # --- Delegation-depth escalation (deeper than parent allows).
        ("e5-14-depth-deeper", "delegation_depth",
         {**parent, "delegation_depth": 5}),  # > parent 2
        ("e5-15-depth-unbounded", "delegation_depth",
         {**parent, "delegation_depth": -1}),  # negative ⇒ unbounded-depth attempt
        # --- Expiry extension (later than parent).
        ("e5-16-expiry-extended", "expiry",
         {**parent, "expiry": "2027-12-31T23:59:59.000000Z"}),  # beyond parent
        ("e5-17-expiry-removed", "expiry",
         {k: v for k, v in parent.items() if k != "expiry"}),  # no expiry ⇒ never expires
        # --- Tenant-scope crossing (different tenant than parent).
        ("e5-18-tenant-crossing", "tenant",
         {**parent, "tenant": "tenant-b"}),  # cross-tenant escalation
        ("e5-19-tenant-wildcard", "tenant",
         {**parent, "tenant": "*"}),
        # --- Multi-dimension simultaneous escalation (the compound forgery).
        ("e5-20-multi-dimension", "financial+tools+posture",
         {**parent,
          "financial": {"max_micros": 50_000_000},
          "tools": ["read", "list", "write", "delete"],
          "posture_level": "AUTONOMOUS"}),
    ]
    out: list[SubsetProofVector] = []
    for vid, dim, sub in cases:
        out.append(
            SubsetProofVector(
                vector=ConformanceVector(
                    family="E5",
                    vector_id=vid,
                    method="trust_verify_subset_proof",
                    inputs={"parent": parent, "sub": sub},
                ),
                escalated_dimension=dim,
                expect_valid=False,
            )
        )
    assert len(out) == 20, f"E5 corpus MUST be 20 adversarial vectors per spec; got {len(out)}"
    return out


# ---------------------------------------------------------------------------
# E6 — Two-phase signing orphan resolution.
#
# Methods: phase_a_sign_intent(intent) / phase_b_sign_outcome(outcome, intent_id)
# / phase_a_orphan_resolve(intent_id, resolution). Per specs/ledger.md
# § Two-phase signing: a Phase-A intent is delegation-key-signed BEFORE an
# action; a Phase-B outcome is runtime-device-key-signed AFTER, linked to the
# intent_id. An ORPHAN is a Phase-A intent with no matching Phase-B outcome
# (the action started but never reported); phase_a_orphan_resolve records the
# user-chosen resolution (retry / failed / investigate). E6 hashes the
# orphan-resolution record — it MUST be byte-identical across runtimes.
#
# Each vector carries the identical Phase-A intent / Phase-B outcome / resolution
# inputs both runtimes are handed. The two-phase signing engine ships in shard
# S6a, so the cross-runtime test is xfail(strict=False) until S6a wires it.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class TwoPhaseVector:
    """An E6 two-phase-signing vector.

    Carries the wrapped ``ConformanceVector`` (the method this row exercises —
    one of ``phase_a_sign_intent`` / ``phase_b_sign_outcome`` /
    ``phase_a_orphan_resolve``) plus the ``phase`` label (``"A"`` / ``"B"`` /
    ``"orphan"``) for human auditing + grouping. The vector's ``inputs`` are the
    identical kwargs both runtimes receive, so any byte divergence is a
    runtime-parity failure once S6a wires the engine.
    """

    vector: ConformanceVector
    phase: str


def e6_vectors() -> list[TwoPhaseVector]:
    """The full E6 family — two-phase signing + orphan-resolution byte-identity
    vectors.

    Covers all three methods across the linkage lifecycle: Phase-A intents
    (signed pre-action), Phase-B outcomes (signed post-action, linked to an
    intent_id), and orphan resolutions (the three spec resolution shapes —
    retry / failed / investigate). Authored as identical inputs both runtimes
    receive so the cross-runtime byte-identity holds once S6a lands.
    """
    out: list[TwoPhaseVector] = []

    # --- Phase-A intents (phase_a_sign_intent). Delegation-key-signed; the
    # intent record carries the action + envelope + a deterministic intent_id.
    phase_a_cases: list[tuple[str, dict[str, Any]]] = [
        ("e6-a-01-read-intent", {
            "intent_id": "intent-001", "action": "read", "resource": "doc-1",
            "envelope_hash": "sha256:aaa", "principal_id": "agent-root",
        }),
        ("e6-a-02-write-intent", {
            "intent_id": "intent-002", "action": "write", "resource": "doc-2",
            "envelope_hash": "sha256:bbb", "principal_id": "agent-root",
        }),
        ("e6-a-03-delegated-intent", {
            "intent_id": "intent-003", "action": "list", "resource": "collection-1",
            "envelope_hash": "sha256:ccc", "principal_id": "agent-child",
            "delegator_id": "agent-root",
        }),
        ("e6-a-04-financial-intent", {
            "intent_id": "intent-004", "action": "spend", "amount_micros": 1_000_000,
            "envelope_hash": "sha256:ddd", "principal_id": "agent-root",
        }),
    ]
    for vid, intent in phase_a_cases:
        out.append(
            TwoPhaseVector(
                vector=ConformanceVector(
                    family="E6", vector_id=vid,
                    method="phase_a_sign_intent", inputs={"intent": intent},
                ),
                phase="A",
            )
        )

    # --- Phase-B outcomes (phase_b_sign_outcome). Runtime-device-key-signed;
    # linked to the Phase-A intent_id. The outcome record carries the result.
    phase_b_cases: list[tuple[str, dict[str, Any], str]] = [
        ("e6-b-01-read-success", {"result": "success", "bytes_read": 1024}, "intent-001"),
        ("e6-b-02-write-success", {"result": "success", "bytes_written": 512}, "intent-002"),
        ("e6-b-03-list-success", {"result": "success", "count": 7}, "intent-003"),
        ("e6-b-04-spend-success", {"result": "success", "actual_micros": 999_999}, "intent-004"),
        ("e6-b-05-read-failure", {"result": "failure", "error": "not_found"}, "intent-001"),
    ]
    for vid, outcome, intent_id in phase_b_cases:
        out.append(
            TwoPhaseVector(
                vector=ConformanceVector(
                    family="E6", vector_id=vid,
                    method="phase_b_sign_outcome",
                    inputs={"outcome": outcome, "intent_id": intent_id},
                ),
                phase="B",
            )
        )

    # --- Orphan resolutions (phase_a_orphan_resolve). Genesis-signed via Grant
    # Moment; the three spec resolution shapes (retry / failed / investigate)
    # plus an intent_id that never got a Phase-B outcome.
    orphan_cases: list[tuple[str, str, dict[str, Any]]] = [
        ("e6-orphan-01-retry", "intent-005",
         {"resolution": "retry", "reason": "transient_network", "resolved_by": "user"}),
        ("e6-orphan-02-failed", "intent-006",
         {"resolution": "failed", "reason": "action_aborted", "resolved_by": "user"}),
        ("e6-orphan-03-investigate", "intent-007",
         {"resolution": "investigate", "reason": "ambiguous_state", "resolved_by": "user"}),
        ("e6-orphan-04-retry-deep", "intent-008",
         {"resolution": "retry", "reason": "downstream_timeout", "resolved_by": "user",
          "attempt": 2}),
    ]
    for vid, intent_id, resolution in orphan_cases:
        out.append(
            TwoPhaseVector(
                vector=ConformanceVector(
                    family="E6", vector_id=vid,
                    method="phase_a_orphan_resolve",
                    inputs={"intent_id": intent_id, "resolution": resolution},
                ),
                phase="orphan",
            )
        )

    # 4 Phase-A + 5 Phase-B + 4 orphan = 13 two-phase-signing vectors covering
    # the full intent→outcome→orphan-resolution lifecycle.
    assert len(out) == 13, f"E6 corpus MUST be 13 two-phase vectors; got {len(out)}"
    return out


# ---------------------------------------------------------------------------
# E7 — Ledger head-commitment monotonicity (≥10 vectors, SHARED corpus).
#
# Method: head_commitment() -> HeadCommitment | None (async). WIRED in S2a;
# forwards to the injected EnvoyLedger.head_commitment. The E7 vectors live in
# tests/fixtures/conformance/e7/head_commitment_vectors.json — the SINGLE source
# of truth the S7v Rust verifier also vendors (see module docstring + PR body for
# the shared-corpus decision). Each vector is an ordered append sequence; the
# driver replays it into ONE shared EnvoyLedger and snapshots head_commitment()
# after each append, asserting byte-identity across runtimes AND monotonic
# non-decreasing head_sequence.
# ---------------------------------------------------------------------------


#: The single shared E7 fixture both the Python harness and the S7v Rust verifier
#: consume. Resolved relative to this module so the path is OS-portable.
E7_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "conformance"
    / "e7"
    / "head_commitment_vectors.json"
)


@dataclasses.dataclass(frozen=True)
class HeadCommitmentVector:
    """An E7 head-commitment vector loaded from the shared JSON fixture.

    - ``vector_id`` — unique within E7.
    - ``description`` — human-readable summary (from the fixture).
    - ``appends`` — ordered list of ``{"entry_type", "content"}`` dicts replayed
      into ONE shared ``EnvoyLedger``.
    - ``expected_head_sequence_progression`` — ``head_sequence`` after each
      append (1-indexed count); the driver asserts the snapshot matches AND that
      the progression is monotonic non-decreasing.
    """

    vector_id: str
    description: str
    appends: list[dict[str, Any]]
    expected_head_sequence_progression: list[int]


def e7_vectors() -> list[HeadCommitmentVector]:
    """The full E7 family — head-commitment monotonicity vectors.

    Loaded from the SHARED JSON fixture (``E7_FIXTURE_PATH``) so the S7v Rust
    verifier vendors the IDENTICAL corpus — there is exactly one source of truth
    for E7, never two divergent copies. Asserts ≥10 vectors per spec.
    """
    raw = json.loads(E7_FIXTURE_PATH.read_text(encoding="utf-8"))
    out: list[HeadCommitmentVector] = []
    for entry in raw["vectors"]:
        out.append(
            HeadCommitmentVector(
                vector_id=entry["vector_id"],
                description=entry["description"],
                appends=entry["appends"],
                expected_head_sequence_progression=entry[
                    "expected_head_sequence_progression"
                ],
            )
        )
    assert len(out) >= 10, f"E7 corpus MUST be >=10 vectors per spec; got {len(out)}"
    return out


__all__ = [
    "SubsetProofVector",
    "TwoPhaseVector",
    "HeadCommitmentVector",
    "E7_FIXTURE_PATH",
    "e5_vectors",
    "e6_vectors",
    "e7_vectors",
]
