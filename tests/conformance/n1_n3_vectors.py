# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/conformance/n1_n3_vectors.py — N1–N3 byte-identity vector corpus (S2b).

Source of truth: `specs/runtime-abstraction.md` § Conformance vectors N1–N6
decoded (lines ~149-158) + § Contract partition (BET-6) + § Contract-tier
enforcement (the N3 structural-vs-semantic dispatch is observed deterministically
via the cross-runtime dispatch-observation hook
`envoy.runtime.dispatch_observation`, NOT output heuristics).

The three families authored here exercise the envelope-check / classifier
surface of the `KailashRuntime` Protocol:

- **N1 — Knowledge Filter** (10 vectors). Pre-retrieval gate: the envelope's
  `field_allowlist_per_model` gates which fields the runtime fetches BEFORE
  classification, preventing over-fetch of classified data. Exercises
  `envelope_check(envelope, action)`.
- **N2 — Envelope Cache** (15 vectors). 5-property invalidation: any change to
  `envelope_version`, `algorithm_identifier`, `classifier_ensemble_versions`,
  `posture_level`, or `principal_genesis_id` MUST invalidate the cache,
  byte-identically on both runtimes. Exercises `envelope_check` (the cache key
  is a function of these five properties; a check against a mutated envelope
  yields a distinct cache-key verdict from the baseline).
- **N3 — Structural-vs-semantic partition** (10 vectors). Every `structural`-class
  envelope check MUST NOT invoke the classifier ensemble; every `semantic`-class
  check MUST dispatch to it. Split into a STRUCTURAL slice (classification-only
  fixtures, zero classifier dispatch — observed via the dispatch-observation
  hook) and a SEMANTIC slice (the dispatching half). The structural slice's
  dispatch assertion is DETERMINISTIC/STRUCTURAL (it counts real `record_dispatch`
  calls via `envoy.runtime.dispatch_observation`), NOT a probe.

Wired-vs-substrate-gated status (verified empirically against the rs adapter via
`harness.resolve_runtime("kailash-rs-bindings")`, NOT assumed):

- `envelope_check` raises `RuntimeNotReadyError` naming gating shard **S6a** —
  the structural+semantic envelope-check engine ships there. N1, N2, and the N3
  byte-identity loops that drive `envelope_check` are therefore authored in full
  but their cross-runtime byte-identity tests are marked
  `@pytest.mark.xfail(strict=False, reason="substrate-gated on S6a …")` in the
  driver (`tests/conformance/test_n1_n3.py`).
- `classifier_invoke` / `ensemble_aggregate` raise `RuntimeNotReadyError` naming
  gating shard **S6c** — the classifier ensemble ships there. The N3 SEMANTIC
  slice (which dispatches the classifier) is gated on S6c.
- The N3 STRUCTURAL slice's dispatch-observation assertion is LIVE NOW: a
  structural-class check raises the S6a gate BEFORE any `record_dispatch`, so the
  cross-runtime invariant "structural ⇒ no classifier dispatch" is observable
  today on both adapters via `dispatch_observation.observe()` — this is the
  buildable-now half the driver runs green.

OS-portability note: every vector here is OS-portable by construction — no
hardcoded path separators, no platform-locale assumptions; all inputs are
plain dicts/strings the canonicalization pipeline folds identically on every OS.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from envoy.runtime.conformance import ConformanceVector

# ---------------------------------------------------------------------------
# N1 — Knowledge Filter (10 vectors).
#
# Method: envelope_check(envelope, action) -> verdict. The envelope's
# `field_allowlist_per_model` is the pre-retrieval gate: only the listed fields
# may be fetched from DataFlow BEFORE classification. The verdict's structured
# payload (the allowed/denied field set + the gate decision) MUST be
# byte-identical across runtimes. Substrate-gated on S6a (the envelope-check
# engine); the corpus is authored in full so it is ready the moment S6a lands.
#
# Each vector's `envelope` carries a `field_allowlist_per_model` map (model ->
# allowed-field list); the `action` names the model being read + the fields the
# action requests. The gate decision (which requested fields survive the
# allowlist) is the byte-identical surface.
# ---------------------------------------------------------------------------


def n1_vectors() -> list[ConformanceVector]:
    """The full N1 family — 10 Knowledge-Filter pre-retrieval-gate vectors.

    Cases span: empty allowlist (deny-all), single-model single-field, multi-model,
    request-subset-of-allowlist (all allowed), request-superset (some denied),
    request-disjoint (all denied), wildcard-model, nested-field path, unicode
    field name (NFC-fold parity), and a financial-microdollar field (the
    classified-data over-fetch case the gate exists to prevent).
    """
    cases: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        # Empty allowlist — deny every requested field (deny-all gate).
        (
            "n1-01-deny-all-empty-allowlist",
            {"schema": "envelope/1.0", "field_allowlist_per_model": {}},
            {"model": "User", "requested_fields": ["name", "email"]},
        ),
        # Single model, single allowed field, request matches exactly.
        (
            "n1-02-single-field-exact",
            {"schema": "envelope/1.0", "field_allowlist_per_model": {"User": ["name"]}},
            {"model": "User", "requested_fields": ["name"]},
        ),
        # Request is a SUBSET of the allowlist — all allowed.
        (
            "n1-03-request-subset-allowed",
            {
                "schema": "envelope/1.0",
                "field_allowlist_per_model": {"User": ["name", "email", "tier"]},
            },
            {"model": "User", "requested_fields": ["name", "email"]},
        ),
        # Request is a SUPERSET — some fields denied (the over-fetch prevention).
        (
            "n1-04-request-superset-partial-deny",
            {"schema": "envelope/1.0", "field_allowlist_per_model": {"User": ["name"]}},
            {"model": "User", "requested_fields": ["name", "ssn", "salary"]},
        ),
        # Request is DISJOINT from the allowlist — all denied.
        (
            "n1-05-request-disjoint-all-deny",
            {"schema": "envelope/1.0", "field_allowlist_per_model": {"User": ["name"]}},
            {"model": "User", "requested_fields": ["ssn", "salary"]},
        ),
        # Multi-model allowlist — the gate keys on the action's model.
        (
            "n1-06-multi-model",
            {
                "schema": "envelope/1.0",
                "field_allowlist_per_model": {
                    "User": ["name", "email"],
                    "Account": ["balance_micros"],
                },
            },
            {"model": "Account", "requested_fields": ["balance_micros", "owner_ssn"]},
        ),
        # Model absent from the allowlist entirely — deny-all for that model.
        (
            "n1-07-model-not-in-allowlist",
            {"schema": "envelope/1.0", "field_allowlist_per_model": {"User": ["name"]}},
            {"model": "Document", "requested_fields": ["body"]},
        ),
        # Nested-field-path allowlist (dotted path; no OS path separators).
        (
            "n1-08-nested-field-path",
            {
                "schema": "envelope/1.0",
                "field_allowlist_per_model": {"User": ["profile.public_bio"]},
            },
            {"model": "User", "requested_fields": ["profile.public_bio", "profile.private_notes"]},
        ),
        # Unicode field name — NFC fold parity (café authored NFC).
        (
            "n1-09-unicode-field",
            {"schema": "envelope/1.0", "field_allowlist_per_model": {"User": ["café_label"]}},
            {"model": "User", "requested_fields": ["café_label"]},
        ),
        # Financial microdollar field — the classified-data over-fetch case.
        (
            "n1-10-financial-microdollar-gate",
            {
                "schema": "envelope/1.0",
                "field_allowlist_per_model": {"Account": ["display_name"]},
            },
            {"model": "Account", "requested_fields": ["display_name", "balance_micros"]},
        ),
    ]
    vectors = [
        ConformanceVector(
            family="N1",
            vector_id=vid,
            method="envelope_check",
            inputs={"envelope": envelope, "action": action},
        )
        for vid, envelope, action in cases
    ]
    assert len(vectors) == 10, f"N1 corpus MUST be 10 vectors per spec; got {len(vectors)}"
    return vectors


# ---------------------------------------------------------------------------
# N2 — Envelope Cache (15 vectors).
#
# Method: envelope_check(envelope, action). The envelope-check cache key is a
# function of FIVE properties; a change to ANY one MUST independently invalidate
# the cache. This corpus pins the 5-property invalidation as a PAIR of envelopes
# per property: a baseline + a mutated-on-that-one-property variant. A correct
# runtime returns a DISTINCT cache-key verdict for the mutated envelope (cache
# miss / invalidation); an incorrect runtime that ignores the property returns
# the baseline verdict (silent stale-cache hit). Byte-identity across runtimes
# is the property under test for BOTH the baseline and the mutated verdict.
#
# The five properties (per spec § N2):
#   1. envelope_version
#   2. algorithm_identifier
#   3. classifier_ensemble_versions
#   4. posture_level
#   5. principal_genesis_id
#
# Substrate-gated on S6a (envelope_check). Authored in full; cross-runtime test
# xfail(S6a).
#
# Each N2 vector carries the `EnvelopeCacheVector` wrapper: `baseline` + `mutated`
# envelopes + the `property_changed` name (for failure localization). The driver
# runs envelope_check on BOTH envelopes on BOTH runtimes and asserts the four
# verdicts agree cross-runtime AND that baseline != mutated (the invalidation
# fired) within each runtime.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class EnvelopeCacheVector:
    """An N2 cache-invalidation vector: baseline + single-property-mutated pair.

    `vector` is the wrapped `ConformanceVector` (the baseline check, for harness
    ID emission). `baseline` and `mutated` are the two envelopes differing on
    exactly ONE of the five cache-key properties; `property_changed` names which
    one (for failure localization). `action` is shared across both checks.
    """

    vector: ConformanceVector
    baseline: dict[str, Any]
    mutated: dict[str, Any]
    property_changed: str
    action: dict[str, Any]


def _base_envelope() -> dict[str, Any]:
    """The canonical baseline envelope carrying all five cache-key properties."""
    return {
        "schema": "envelope/1.0",
        "envelope_version": 3,
        "algorithm_identifier": {"sig": "ed25519", "hash": "sha256"},
        "classifier_ensemble_versions": {"clf-a": "1.0.0", "clf-b": "2.1.0"},
        "posture_level": "SUPERVISED",
        "principal_genesis_id": "genesis:agent-root",
    }


def n2_vectors() -> list[EnvelopeCacheVector]:
    """The full N2 family — 15 envelope-cache 5-property-invalidation vectors.

    Three vectors per property (5 × 3 = 15): a minimal single-bit change, a
    structurally-larger change, and a boundary change — each independently
    triggering invalidation. Every vector mutates EXACTLY ONE property off the
    shared baseline so the test localizes which property failed to invalidate.
    """
    action = {"model": "User", "requested_fields": ["name"]}

    # (vector_id, property_changed, mutate fn applied to a fresh baseline copy)
    def _mut(prop: str, **changes: Any) -> dict[str, Any]:
        env = _base_envelope()
        env.update(changes)
        return env

    cases: list[tuple[str, str, dict[str, Any]]] = [
        # --- Property 1: envelope_version ---
        ("n2-01-version-bump", "envelope_version", _mut("envelope_version", envelope_version=4)),
        ("n2-02-version-jump", "envelope_version", _mut("envelope_version", envelope_version=99)),
        ("n2-03-version-to-one", "envelope_version", _mut("envelope_version", envelope_version=1)),
        # --- Property 2: algorithm_identifier ---
        (
            "n2-04-algo-sig-change",
            "algorithm_identifier",
            _mut("algorithm_identifier", algorithm_identifier={"sig": "ed448", "hash": "sha256"}),
        ),
        (
            "n2-05-algo-hash-change",
            "algorithm_identifier",
            _mut("algorithm_identifier", algorithm_identifier={"sig": "ed25519", "hash": "sha512"}),
        ),
        (
            "n2-06-algo-add-field",
            "algorithm_identifier",
            _mut(
                "algorithm_identifier",
                algorithm_identifier={"sig": "ed25519", "hash": "sha256", "shamir": "slip39"},
            ),
        ),
        # --- Property 3: classifier_ensemble_versions ---
        (
            "n2-07-ensemble-version-bump",
            "classifier_ensemble_versions",
            _mut(
                "classifier_ensemble_versions",
                classifier_ensemble_versions={"clf-a": "1.0.1", "clf-b": "2.1.0"},
            ),
        ),
        (
            "n2-08-ensemble-add-classifier",
            "classifier_ensemble_versions",
            _mut(
                "classifier_ensemble_versions",
                classifier_ensemble_versions={"clf-a": "1.0.0", "clf-b": "2.1.0", "clf-c": "0.9.0"},
            ),
        ),
        (
            "n2-09-ensemble-drop-classifier",
            "classifier_ensemble_versions",
            _mut(
                "classifier_ensemble_versions",
                classifier_ensemble_versions={"clf-a": "1.0.0"},
            ),
        ),
        # --- Property 4: posture_level ---
        (
            "n2-10-posture-tighten",
            "posture_level",
            _mut("posture_level", posture_level="RESTRICTED"),
        ),
        (
            "n2-11-posture-loosen",
            "posture_level",
            _mut("posture_level", posture_level="AUTONOMOUS"),
        ),
        (
            "n2-12-posture-to-public",
            "posture_level",
            _mut("posture_level", posture_level="PUBLIC"),
        ),
        # --- Property 5: principal_genesis_id ---
        (
            "n2-13-principal-change",
            "principal_genesis_id",
            _mut("principal_genesis_id", principal_genesis_id="genesis:agent-other"),
        ),
        (
            "n2-14-principal-rotation",
            "principal_genesis_id",
            _mut("principal_genesis_id", principal_genesis_id="genesis:agent-root-gen2"),
        ),
        (
            "n2-15-principal-empty-to-set",
            "principal_genesis_id",
            _mut("principal_genesis_id", principal_genesis_id="genesis:delegate-7"),
        ),
    ]
    out: list[EnvelopeCacheVector] = []
    for vid, prop, mutated in cases:
        out.append(
            EnvelopeCacheVector(
                vector=ConformanceVector(
                    family="N2",
                    vector_id=vid,
                    method="envelope_check",
                    inputs={"envelope": _base_envelope(), "action": action},
                ),
                baseline=_base_envelope(),
                mutated=mutated,
                property_changed=prop,
                action=action,
            )
        )
    assert len(out) == 15, f"N2 corpus MUST be 15 vectors per spec; got {len(out)}"
    return out


# ---------------------------------------------------------------------------
# N3 — Structural-vs-semantic partition (10 vectors).
#
# Every `structural`-class envelope check MUST NOT invoke the classifier
# ensemble; every `semantic`-class check MUST dispatch to it. Observed
# deterministically via the cross-runtime dispatch-observation hook
# (`envoy.runtime.dispatch_observation`) — NOT output heuristics, NOT a probe.
#
# The family is SPLIT into two slices (per the S2b todo + the dispatch-observation
# hook's design docstring):
#
#   - STRUCTURAL slice (6 vectors, `expected_dispatch=False`): classification-only
#     fixtures whose envelope-check verdict is reached WITHOUT the classifier. The
#     dispatch-observation assertion (the check dispatched the classifier ZERO
#     times) is LIVE NOW — `envelope_check` raises the S6a gate BEFORE any
#     `record_dispatch`, so on both adapters the observation deterministically
#     reads `dispatched=False`. This is the buildable-now half.
#
#   - SEMANTIC slice (4 vectors, `expected_dispatch=True`): fixtures whose verdict
#     REQUIRES dispatching the classifier ensemble (`classifier_invoke`). This
#     half is substrate-gated on S6c (the classifier ensemble); the driver marks
#     its dispatch + byte-identity test xfail(S6c).
#
# Each N3 vector carries `expected_dispatch` (True ⇒ semantic, False ⇒ structural)
# directly on the ConformanceVector row (the schema's N3 field, see
# envoy/runtime/conformance/corpus.py). The driver partitions on that flag.
# ---------------------------------------------------------------------------


def _n3_structural_vectors() -> list[ConformanceVector]:
    """N3 structural slice — 6 vectors, classifier MUST NOT dispatch.

    Structural-class checks are reached by structure alone: malformed schema,
    missing required field, type mismatch, dimension out of declared range,
    unknown action verb, allowlist-shape violation. None require an LLM-class
    classifier verdict; `expected_dispatch=False`.
    """
    cases: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        # Malformed schema marker — structural reject, no classifier.
        (
            "n3-struct-01-bad-schema",
            {"schema": "envelope/0.0-INVALID"},
            {"model": "User", "requested_fields": ["name"]},
        ),
        # Missing required `schema` field — structural reject.
        (
            "n3-struct-02-missing-schema",
            {"envelope_version": 3},
            {"model": "User", "requested_fields": ["name"]},
        ),
        # Type mismatch — envelope_version is a string, not an int.
        (
            "n3-struct-03-type-mismatch",
            {"schema": "envelope/1.0", "envelope_version": "three"},
            {"model": "User", "requested_fields": ["name"]},
        ),
        # Dimension out of declared range — structural bound check, no classifier.
        (
            "n3-struct-04-dimension-out-of-range",
            {"schema": "envelope/1.0", "dims": {"max_depth": 999}},
            {"model": "User", "requested_fields": ["name"]},
        ),
        # Unknown action verb — structural action-grammar reject.
        (
            "n3-struct-05-unknown-action-verb",
            {"schema": "envelope/1.0"},
            {"model": "User", "requested_fields": ["name"], "verb": "TELEPORT"},
        ),
        # Allowlist-shape violation — field_allowlist_per_model is a list, not a map.
        (
            "n3-struct-06-allowlist-shape",
            {"schema": "envelope/1.0", "field_allowlist_per_model": ["name", "email"]},
            {"model": "User", "requested_fields": ["name"]},
        ),
    ]
    return [
        ConformanceVector(
            family="N3",
            vector_id=vid,
            method="envelope_check",
            inputs={"envelope": envelope, "action": action},
            expected_dispatch=False,
        )
        for vid, envelope, action in cases
    ]


def _n3_semantic_vectors() -> list[ConformanceVector]:
    """N3 semantic slice — 4 vectors, classifier MUST dispatch.

    Semantic-class checks REQUIRE an LLM-class classifier verdict over content:
    free-text data-access reads, content-classification of an attached payload,
    a redaction decision, and an ambiguous data-sensitivity boundary. Each
    `expected_dispatch=True`; substrate-gated on S6c (the classifier ensemble).
    """
    cases: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        # Free-text data-access read — content must be classified.
        (
            "n3-sem-01-free-text-read",
            {"schema": "envelope/1.0", "posture_level": "SUPERVISED"},
            {"model": "Document", "requested_fields": ["body"], "content": b"free-text payload"},
        ),
        # Content-classification of an attached payload.
        (
            "n3-sem-02-content-classify",
            {"schema": "envelope/1.0", "posture_level": "SUPERVISED"},
            {"model": "Message", "requested_fields": ["text"], "content": b"classify me"},
        ),
        # Redaction decision — semantic, needs the ensemble verdict.
        (
            "n3-sem-03-redaction-decision",
            {"schema": "envelope/1.0", "posture_level": "RESTRICTED"},
            {"model": "Record", "requested_fields": ["notes"], "content": b"maybe-PII text"},
        ),
        # Ambiguous data-sensitivity boundary — the canonical semantic case.
        (
            "n3-sem-04-ambiguous-sensitivity",
            {"schema": "envelope/1.0", "posture_level": "SUPERVISED"},
            {"model": "Note", "requested_fields": ["content"], "content": b"ambiguous"},
        ),
    ]
    return [
        ConformanceVector(
            family="N3",
            vector_id=vid,
            method="envelope_check",
            inputs={"envelope": envelope, "action": action},
            expected_dispatch=True,
        )
        for vid, envelope, action in cases
    ]


def n3_structural_vectors() -> list[ConformanceVector]:
    """The N3 structural slice — 6 vectors (classifier MUST NOT dispatch)."""
    vectors = _n3_structural_vectors()
    assert len(vectors) == 6, f"N3 structural slice MUST be 6 vectors; got {len(vectors)}"
    return vectors


def n3_semantic_vectors() -> list[ConformanceVector]:
    """The N3 semantic slice — 4 vectors (classifier MUST dispatch; S6c-gated)."""
    vectors = _n3_semantic_vectors()
    assert len(vectors) == 4, f"N3 semantic slice MUST be 4 vectors; got {len(vectors)}"
    return vectors


def n3_vectors() -> list[ConformanceVector]:
    """The full N3 family — 10 structural-vs-semantic-partition vectors.

    6 structural (`expected_dispatch=False`) + 4 semantic (`expected_dispatch=True`).
    """
    vectors = n3_structural_vectors() + n3_semantic_vectors()
    assert len(vectors) == 10, f"N3 corpus MUST be 10 vectors per spec; got {len(vectors)}"
    return vectors


__all__ = [
    "EnvelopeCacheVector",
    "n1_vectors",
    "n2_vectors",
    "n3_vectors",
    "n3_structural_vectors",
    "n3_semantic_vectors",
]
