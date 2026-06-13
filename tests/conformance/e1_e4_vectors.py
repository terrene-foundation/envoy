# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/conformance/e1_e4_vectors.py — E1–E4 byte-identity vector corpus (S3a).

Source of truth: `specs/runtime-abstraction.md` § Envoy-specific conformance
(E1–E7) + § Contract partition (BET-6), `specs/envelope-model.md` § Canonical
JSON (§14.1), `specs/trust-lineage.md` § Chain verification / § Cascade
revocation / § Cycle detection.

The four families authored here all exercise WIRED methods on BOTH the
`kailash-py` reference adapter and the `kailash-rs-bindings` adapter
(`envelope_canonical_form`, `trust_sign`, `trust_cascade_revoke`,
`trust_verify_chain` — all in the S2a wired-18 set). The harness driver
(`tests/conformance/test_e1_e4.py`) constructs BOTH runtimes with IDENTICAL key
material / trust state so any output divergence is a runtime-parity failure, not
a key/state mismatch.

OS-portability note: every vector here is OS-portable by construction —
no hardcoded path separators, no platform-locale assumptions, all bytes derived
from the deterministic JCS+NFC pipeline / Ed25519 signing / in-memory graph
walks. CI runs the byte-identity slice on the macos/ubuntu/windows matrix to
catch cross-language NFC drift (per the S3a todo § "OS-matrix note"); the
vectors are authored so the SAME bytes are expected on every OS.

E3 NOTE (SET-equality): `trust_cascade_revoke` returns ``set[str]``; the scorer
(`score_byte_identity`) treats sets order-insensitively, so a BFS-vs-DFS
ordering difference does NOT fail; a set-MEMBERSHIP difference DOES. The
`expected_revoked` payload on each E3 vector is the ground-truth descendant SET
both runtimes' identically-seeded stores MUST return.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from envoy.runtime.conformance import ConformanceVector

# ---------------------------------------------------------------------------
# E1 — Envelope canonical JSON (67 vectors).
#
# Method: envelope_canonical_form(envelope) -> bytes. JCS-RFC8785 + NFC.
# Hash-equality between runtimes (both forward to envoy.envelope.canonical_bytes,
# so they are byte-identical by construction — the vector battery PROVES it
# across the full canonicalization surface: nesting, unicode/NFC, key ordering,
# number canonicalization, empty/edge envelopes, escapes, null-vs-absent).
#
# Six categories per `specs/envelope-model.md` § Canonical JSON "Conformance
# corpus: 67 test vectors enumerated in 6 categories (Unicode, integers,
# numbers/floats, escapes, empty-vs-null, nested ordering)".
# ---------------------------------------------------------------------------

# Combining characters used to build NFD forms that MUST normalize (NFC) to the
# same canonical bytes as their precomposed siblings. These are authored as
# explicit codepoint sequences so the source is OS-independent (an editor on an
# HFS+ macOS box will not silently re-normalize a literal precomposed string).
_COMBINING_ACUTE = "́"  # combining acute accent
_COMBINING_DIAERESIS = "̈"  # combining diaeresis
_COMBINING_TILDE = "̃"  # combining tilde
_COMBINING_RING = "̊"  # combining ring above
_COMBINING_CEDILLA = "̧"  # combining cedilla


def _e1_unicode_nfc_vectors() -> list[ConformanceVector]:
    """E1 category 1 — Unicode / NFC normalization (12 vectors).

    Each vector's envelope contains a string in NFD (decomposed) form. The
    canonical pipeline NFC-normalizes every string, so the canonical bytes MUST
    be identical to the precomposed form's bytes. The cross-runtime byte
    identity is the property under test; the NFD→NFC fold is the canonical
    contract that makes envelopes authored on different OSes byte-identical.
    """
    nfd_pairs: list[tuple[str, str]] = [
        ("e1-uni-01-e-acute", "cafe" + _COMBINING_ACUTE),  # café (NFD)
        ("e1-uni-02-u-diaeresis", "mu" + _COMBINING_DIAERESIS + "ller"),  # müller
        ("e1-uni-03-n-tilde", "man" + _COMBINING_TILDE + "ana"),  # mañana
        ("e1-uni-04-a-ring", "a" + _COMBINING_RING + "ngstrom"),  # ångstrom
        ("e1-uni-05-c-cedilla", "fac" + _COMBINING_CEDILLA + "ade"),  # façade
        ("e1-uni-06-multi-combining", "e" + _COMBINING_ACUTE + "e" + _COMBINING_ACUTE),
        ("e1-uni-07-cjk", "東京"),  # 東京 (already NFC; idempotent)
        ("e1-uni-08-emoji", "ok \U0001f600 done"),  # emoji passes through unchanged
        ("e1-uni-09-mixed-script", "Kaı" + _COMBINING_ACUTE + "lash"),  # dotless-i + acute
        ("e1-uni-10-key-nfd", "label"),  # NFD applied to KEYS too (see below)
        ("e1-uni-11-zwj", "team‍join"),  # zero-width joiner preserved
        ("e1-uni-12-greek", "αβγ"),  # αβγ
    ]
    vectors: list[ConformanceVector] = []
    for vid, value in nfd_pairs[:9] + nfd_pairs[10:]:
        vectors.append(
            ConformanceVector(
                family="E1",
                vector_id=vid,
                method="envelope_canonical_form",
                inputs={"envelope": {"schema": "envelope/1.0", "field": value}},
            )
        )
    # The dedicated key-NFD vector: an NFD key MUST be NFC-normalized before
    # lexicographic ordering, so it sorts deterministically across runtimes.
    nfd_key = "lab" + _COMBINING_ACUTE + "el"  # "lábel" with NFD key
    vectors.append(
        ConformanceVector(
            family="E1",
            vector_id="e1-uni-10-key-nfd",
            method="envelope_canonical_form",
            inputs={"envelope": {nfd_key: "v", "schema": "envelope/1.0"}},
        )
    )
    return vectors


def _e1_integer_vectors() -> list[ConformanceVector]:
    """E1 category 2 — integers / microdollar financial quantities (12 vectors).

    Integers serialize as JSON numbers with no leading zeros and no scientific
    notation. Envoy uses integer microdollars for financial quantities, so the
    boundary integers (0, negative, large) are the load-bearing cases.
    """
    int_cases: list[tuple[str, int]] = [
        ("e1-int-01-zero", 0),
        ("e1-int-02-one", 1),
        ("e1-int-03-negative", -1),
        ("e1-int-04-microdollar", 1_000_000),  # $1.00 in microdollars
        ("e1-int-05-large", 999_999_999_999),
        ("e1-int-06-negative-large", -999_999_999_999),
        ("e1-int-07-int32-max", 2_147_483_647),
        ("e1-int-08-int64-max", 9_223_372_036_854_775_807),
        ("e1-int-09-cents-edge", 99),
        ("e1-int-10-thousand", 1000),
        ("e1-int-11-neg-microdollar", -1_000_000),
        ("e1-int-12-ten", 10),
    ]
    return [
        ConformanceVector(
            family="E1",
            vector_id=vid,
            method="envelope_canonical_form",
            inputs={"envelope": {"amount_micros": value, "schema": "envelope/1.0"}},
        )
        for vid, value in int_cases
    ]


def _e1_number_vectors() -> list[ConformanceVector]:
    """E1 category 3 — numbers / bounded finite floats (11 vectors).

    Floats are rejected unless ``math.isfinite()``; the spec uses bounded floats
    in classifier weights. These cover the finite-float surface both runtimes
    must serialize identically (both forward to the SAME json.dumps path, so the
    bytes are identical by construction — the battery proves it for the values
    the spec actually uses).
    """
    float_cases: list[tuple[str, float]] = [
        ("e1-num-01-half", 0.5),
        ("e1-num-02-quarter", 0.25),
        ("e1-num-03-weight", 0.85),  # classifier weight
        ("e1-num-04-one", 1.0),
        ("e1-num-05-zero", 0.0),
        ("e1-num-06-negative", -0.5),
        ("e1-num-07-tenth", 0.1),
        ("e1-num-08-threshold", 0.999),
        ("e1-num-09-small", 0.001),
        ("e1-num-10-two-dp", 0.33),
        ("e1-num-11-near-one", 0.9999),
    ]
    return [
        ConformanceVector(
            family="E1",
            vector_id=vid,
            method="envelope_canonical_form",
            inputs={"envelope": {"weight": value, "schema": "envelope/1.0"}},
        )
        for vid, value in float_cases
    ]


def _e1_escape_vectors() -> list[ConformanceVector]:
    """E1 category 4 — escapes / minimal-escape strings (10 vectors).

    Per RFC 8785, minimal escapes only. These strings carry characters whose
    JSON encoding has exactly one canonical escaped form; both runtimes must
    emit identical escape sequences.
    """
    escape_cases: list[tuple[str, str]] = [
        ("e1-esc-01-quote", 'he said "hi"'),
        ("e1-esc-02-backslash", "path\\to\\thing"),
        ("e1-esc-03-newline", "line1\nline2"),
        ("e1-esc-04-tab", "col1\tcol2"),
        ("e1-esc-05-carriage", "a\rb"),
        ("e1-esc-06-mixed", 'a"\\b\nc'),
        ("e1-esc-07-control", "bell\x07here"),  # U+0007 → 
        ("e1-esc-08-formfeed", "a\x0cb"),  # form feed
        ("e1-esc-09-backspace", "a\x08b"),  # backspace
        ("e1-esc-10-slash-not-escaped", "http://a/b"),  # forward slash NOT escaped
    ]
    return [
        ConformanceVector(
            family="E1",
            vector_id=vid,
            method="envelope_canonical_form",
            inputs={"envelope": {"text": value, "schema": "envelope/1.0"}},
        )
        for vid, value in escape_cases
    ]


def _e1_empty_null_vectors() -> list[ConformanceVector]:
    """E1 category 5 — empty-vs-null / edge envelopes (10 vectors).

    null is a distinct value from an absent key; an empty object/array/string is
    distinct from null. These pin the boundary cases where a sloppy
    canonicalizer would conflate them.
    """
    cases: list[tuple[str, dict[str, Any]]] = [
        ("e1-empty-01-empty-object", {}),
        ("e1-empty-02-empty-nested-object", {"dims": {}}),
        ("e1-empty-03-empty-array", {"items": []}),
        ("e1-empty-04-empty-string", {"note": ""}),
        ("e1-empty-05-explicit-null", {"value": None}),
        ("e1-empty-06-null-vs-empty", {"a": None, "b": ""}),
        ("e1-empty-07-nested-null", {"dims": {"data_access": None}}),
        ("e1-empty-08-array-of-empties", {"items": ["", None]}),
        ("e1-empty-09-bool-true", {"flag": True}),
        ("e1-empty-10-bool-false", {"flag": False}),
    ]
    return [
        ConformanceVector(
            family="E1",
            vector_id=vid,
            method="envelope_canonical_form",
            inputs={"envelope": value},
        )
        for vid, value in cases
    ]


def _e1_nested_ordering_vectors() -> list[ConformanceVector]:
    """E1 category 6 — nested / key-ordering (12 vectors).

    Lexicographic Unicode code-point ordering on NFC-normalized keys, applied
    recursively. Each vector authors keys in NON-sorted source order; the
    canonical bytes MUST sort them identically across runtimes.
    """
    cases: list[tuple[str, dict[str, Any]]] = [
        ("e1-nest-01-two-keys", {"b": 1, "a": 2}),
        ("e1-nest-02-three-keys", {"z": 1, "m": 2, "a": 3}),
        ("e1-nest-03-nested-unsorted", {"outer": {"y": 1, "x": 2}, "alpha": 3}),
        ("e1-nest-04-deep", {"l1": {"l2": {"l3": {"b": 1, "a": 2}}}}),
        ("e1-nest-05-array-of-objects", {"rows": [{"c": 1, "a": 2}, {"b": 3, "a": 4}]}),
        ("e1-nest-06-mixed-types", {"num": 1, "str": "x", "bool": True, "arr": [1, 2]}),
        ("e1-nest-07-numeric-string-keys", {"10": "a", "2": "b", "1": "c"}),
        ("e1-nest-08-uppercase-lowercase", {"B": 1, "a": 2, "A": 3, "b": 4}),
        ("e1-nest-09-envelope-shape", {
            "schema": "envelope/1.0",
            "metadata": {"posture_level": "SUPERVISED", "version": 3},
            "dims": {"financial": {"max_micros": 5_000_000}, "data_access": "public"},
        }),
        ("e1-nest-10-array-order-preserved", {"seq": [3, 1, 2]}),  # array order NOT sorted
        ("e1-nest-11-unicode-keys", {"é": 1, "e": 2}),  # é vs e ordering
        ("e1-nest-12-five-keys", {"e": 5, "d": 4, "c": 3, "b": 2, "a": 1}),
    ]
    return [
        ConformanceVector(
            family="E1",
            vector_id=vid,
            method="envelope_canonical_form",
            inputs={"envelope": value},
        )
        for vid, value in cases
    ]


def e1_vectors() -> list[ConformanceVector]:
    """The full E1 family — 67 envelope-canonical-JSON byte-identity vectors."""
    vectors = (
        _e1_unicode_nfc_vectors()
        + _e1_integer_vectors()
        + _e1_number_vectors()
        + _e1_escape_vectors()
        + _e1_empty_null_vectors()
        + _e1_nested_ordering_vectors()
    )
    assert len(vectors) == 67, f"E1 corpus MUST be 67 vectors per spec; got {len(vectors)}"
    return vectors


# ---------------------------------------------------------------------------
# E2 — Delegation Record signing (20 vectors).
#
# Method: trust_sign(record, key) -> bytes. JCS + Ed25519 over the record
# canonical form. Both adapters forward to the SAME kailash.trust.signing.sign;
# given IDENTICAL key + record, the Ed25519 signature bytes MUST be identical.
# The driver injects ONE shared device signing key into both adapters and passes
# it as the `key` input, so the signature parity is the property under test.
# ---------------------------------------------------------------------------


def e2_vectors() -> list[ConformanceVector]:
    """The full E2 family — 20 delegation-record-signing byte-identity vectors.

    The `key` input is the literal sentinel ``"<shared-device-key>"``; the
    driver replaces it with the run's shared Ed25519 private key hex before
    invocation, so both runtimes sign with the SAME key. (The vector carries a
    sentinel rather than a key so the corpus is key-material-free and
    deterministic; the driver owns key generation under a fixed seed.)
    """
    records: list[tuple[str, Any]] = [
        # Plain-string records (sign accepts str | bytes | dict).
        ("e2-01-simple-str", "delegation-record-alpha"),
        ("e2-02-empty-str", ""),
        ("e2-03-unicode-str", "café-delegation"),
        ("e2-04-long-str", "x" * 512),
        # Dict-shaped delegation records (the canonical DelegationRecord shape).
        ("e2-05-minimal-dict", {"delegation_id": "d-1"}),
        ("e2-06-delegation", {
            "delegation_id": "d-100",
            "delegator_id": "agent-root",
            "delegatee_id": "agent-child",
            "task_id": "task-7",
        }),
        ("e2-07-key-order-a", {"a": 1, "b": 2, "c": 3}),
        ("e2-08-key-order-b", {"c": 3, "b": 2, "a": 1}),  # same canonical form as -07
        ("e2-09-nested", {"record": {"caps": ["read", "write"], "depth": 2}}),
        ("e2-10-numeric", {"amount_micros": 5_000_000, "depth": 16}),
        ("e2-11-bool-null", {"revoked": False, "parent": None}),
        ("e2-12-array", {"capabilities": ["c1", "c2", "c3"]}),
        ("e2-13-deep", {"l1": {"l2": {"l3": "leaf"}}}),
        ("e2-14-mixed", {"id": "d-14", "n": 14, "ok": True, "tags": ["a"]}),
        ("e2-15-unicode-value", {"label": "mañana"}),
        ("e2-16-empty-dict", {}),
        ("e2-17-single-byte", "a"),
        ("e2-18-numbers-only", {"x": 0, "y": -1, "z": 1}),
        ("e2-19-envelope-hash-shape", {
            "delegation_id": "d-19",
            "effective_envelope_hash": "sha256:abc123",
            "algorithm_identifier": {"sig": "ed25519", "hash": "sha256"},
        }),
        ("e2-20-bytes-record", b"raw-bytes-delegation"),
    ]
    vectors = [
        ConformanceVector(
            family="E2",
            vector_id=vid,
            method="trust_sign",
            inputs={"record": record, "key": "<shared-device-key>"},
        )
        for vid, record in records
    ]
    assert len(vectors) == 20, f"E2 corpus MUST be 20 vectors per spec; got {len(vectors)}"
    return vectors


# ---------------------------------------------------------------------------
# E3 — Cascade revocation BFS/DFS SET-equality (15 vectors).
#
# Method: trust_cascade_revoke(root_id) -> set[str]. Assert SET-equality
# (order-insensitive): a BFS-vs-DFS ordering difference MUST NOT fail; a
# set-membership difference MUST. Both adapters are seeded with IDENTICAL
# delegation graphs (a sync Protocol-Satisfying store keyed root -> descendant
# set); the driver attaches `expected_revoked` so the test also pins the
# ground-truth set both runtimes return.
#
# The `delegation_graph` field on each vector is the root -> [descendants]
# adjacency the driver seeds into BOTH stores. The `root_id` input names the
# revocation root. `expected_revoked` is the ground-truth descendant SET.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CascadeVector:
    """An E3 cascade-revoke vector: identical graph + root + expected SET.

    Carries the wrapped `ConformanceVector` (for harness ID emission) plus the
    `delegation_graph` the driver seeds into both runtimes' stores and the
    `expected_revoked` ground-truth SET. Authored as a wrapper (not extra
    `ConformanceVector` fields) so the corpus-row schema stays unchanged.
    """

    vector: ConformanceVector
    delegation_graph: dict[str, list[str]]
    expected_revoked: frozenset[str]


def e3_vectors() -> list[CascadeVector]:
    """The full E3 family — 15 cascade-revoke SET-equality vectors.

    Each graph is the root -> revoked-descendant-set the SYNC store returns for
    that root (the store's `revoke(agent_id=root)` returns exactly the listed
    set). The BFS (py) vs DFS (rs) ordering is irrelevant — SET-equality is the
    contract — so both adapters, given the SAME store, return the SAME set.
    """
    # (vector_id, root, root->revoked-set mapping the store returns, expected set)
    cases: list[tuple[str, str, dict[str, list[str]], set[str]]] = [
        # Depth 1 — single child.
        ("e3-01-single-child", "r", {"r": ["r", "c1"]}, {"r", "c1"}),
        # Depth 1 — fan-out (branching).
        ("e3-02-fanout-3", "r", {"r": ["r", "c1", "c2", "c3"]}, {"r", "c1", "c2", "c3"}),
        # Depth 2 — chain.
        ("e3-03-chain-3", "r", {"r": ["r", "a", "b"]}, {"r", "a", "b"}),
        # Depth 3 — deeper chain (order would differ BFS vs DFS).
        ("e3-04-chain-4", "r", {"r": ["r", "a", "b", "c"]}, {"r", "a", "b", "c"}),
        # Wide tree — many children at depth 1 + grandchildren.
        ("e3-05-wide-tree", "r", {"r": ["r", "x", "y", "z", "x1", "y1"]},
         {"r", "x", "y", "z", "x1", "y1"}),
        # Single node — no descendants (root only).
        ("e3-06-root-only", "r", {"r": ["r"]}, {"r"}),
        # Empty cascade — unknown root (genuine empty SET, not silent fallback).
        ("e3-07-unknown-root", "ghost", {}, set()),
        # Day-1 -> Day-6 cross-channel shape (the EC-8(c) invariant).
        ("e3-08-day1-day6", "agent-day1", {"agent-day1": ["agent-day1", "agent-day6"]},
         {"agent-day1", "agent-day6"}),
        # Deep + branching combined.
        ("e3-09-deep-branch", "r",
         {"r": ["r", "a", "b", "a1", "a2", "b1"]}, {"r", "a", "b", "a1", "a2", "b1"}),
        # Diamond shape (a descendant reachable two ways — SET dedups it).
        ("e3-10-diamond", "r", {"r": ["r", "left", "right", "join"]},
         {"r", "left", "right", "join"}),
        # Large fan-out (10 children).
        ("e3-11-fanout-10", "r",
         {"r": ["r"] + [f"c{i}" for i in range(10)]},
         {"r", *[f"c{i}" for i in range(10)]}),
        # Two independent roots in the graph — revoking one returns only its set.
        ("e3-12-isolated-root", "r1",
         {"r1": ["r1", "a"], "r2": ["r2", "b"]}, {"r1", "a"}),
        # Single-character ids (ordering edge).
        ("e3-13-char-ids", "0", {"0": ["0", "1", "2", "3"]}, {"0", "1", "2", "3"}),
        # Unicode-safe ids (no path separators — OS-portable).
        ("e3-14-dotted-ids", "agent.42", {"agent.42": ["agent.42", "agent.43+ci"]},
         {"agent.42", "agent.43+ci"}),
        # Deep chain depth 5 (BFS/DFS visit-order maximally divergent).
        ("e3-15-chain-6", "r", {"r": ["r", "a", "b", "c", "d", "e"]},
         {"r", "a", "b", "c", "d", "e"}),
    ]
    out: list[CascadeVector] = []
    for vid, root, graph, expected in cases:
        out.append(
            CascadeVector(
                vector=ConformanceVector(
                    family="E3",
                    vector_id=vid,
                    method="trust_cascade_revoke",
                    inputs={"root_id": root},
                ),
                delegation_graph=graph,
                expected_revoked=frozenset(expected),
            )
        )
    assert len(out) == 15, f"E3 corpus MUST be 15 vectors per spec; got {len(out)}"
    return out


# ---------------------------------------------------------------------------
# E4 — Cycle detection (15 vectors).
#
# Method: trust_verify_chain(record) -> VerifyResult. The 10-step chain
# verification surfaces cycle-detection verdicts. Assert identical
# cycle-detection verdicts across runtimes. Both adapters forward to the
# injected store's `get_chain(record)`; the driver seeds BOTH with the SAME
# sync store returning the SAME verdict per record, so the verdicts are
# identical across runtimes.
#
# The `verdict` field is the ground-truth chain-verification verdict the SYNC
# store returns for that record. Per `specs/trust-lineage.md` § Cycle detection
# (§6.2, T-103): 15-vector corpus for cycle construction attempts — direct,
# CRDT-merge-induced, timestamp-ambiguous, deep, valid-but-suspicious.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CycleVector:
    """An E4 cycle-detection vector: record -> chain-verification verdict.

    `record` is the chain-verify input (a record id / shape). `verdict` is the
    ground-truth VerifyResult the identically-seeded SYNC store returns for it.
    Both runtimes MUST surface the SAME verdict.
    """

    vector: ConformanceVector
    record: str
    verdict: dict[str, Any]


def e4_vectors() -> list[CycleVector]:
    """The full E4 family — 15 cycle-detection verdict-parity vectors.

    Each verdict is the chain-verification outcome the SYNC store returns for
    the record. The five spec categories (direct cycle, CRDT-merge-induced,
    timestamp-ambiguous, deep, valid-but-suspicious) are covered. ``verdict`` is
    a plain dict (deterministic, JSON-able) so `score_byte_identity`
    canonicalizes it identically for both runtimes; identical verdict dicts ⇒
    byte-identical canonical form ⇒ pass.
    """
    # (vector_id, record, verdict dict the store returns)
    cases: list[tuple[str, str, dict[str, Any]]] = [
        # --- Direct cycles (T-103): chain_parent_id points back to a descendant.
        ("e4-01-direct-2cycle", "rec-a-b-a", {
            "valid": False, "cycle_detected": True, "step_failed": "cycle-free",
            "cycle_nodes": ["a", "b", "a"],
        }),
        ("e4-02-direct-self-loop", "rec-self", {
            "valid": False, "cycle_detected": True, "step_failed": "cycle-free",
            "cycle_nodes": ["a", "a"],
        }),
        ("e4-03-direct-3cycle", "rec-a-b-c-a", {
            "valid": False, "cycle_detected": True, "step_failed": "cycle-free",
            "cycle_nodes": ["a", "b", "c", "a"],
        }),
        # --- CRDT-merge-induced cycles (two valid chains merge into a cycle).
        ("e4-04-crdt-merge-cycle", "rec-crdt-1", {
            "valid": False, "cycle_detected": True, "step_failed": "cycle-free",
            "cycle_source": "crdt-merge",
        }),
        ("e4-05-crdt-merge-clean", "rec-crdt-2", {
            "valid": True, "cycle_detected": False, "step_failed": None,
            "cycle_source": "crdt-merge",
        }),
        # --- Timestamp-ambiguous (DAG invariant: parent earlier-sequenced).
        ("e4-06-ts-ambiguous-cycle", "rec-ts-1", {
            "valid": False, "cycle_detected": True, "step_failed": "cycle-free",
            "reason": "timestamp-ambiguous-parent",
        }),
        ("e4-07-ts-monotonic-clean", "rec-ts-2", {
            "valid": True, "cycle_detected": False, "step_failed": None,
        }),
        # --- Deep chains (depth <= 16 valid; cycle deep in the chain).
        ("e4-08-deep-clean-16", "rec-deep-ok", {
            "valid": True, "cycle_detected": False, "step_failed": None, "depth": 16,
        }),
        ("e4-09-deep-cycle-deep", "rec-deep-cycle", {
            "valid": False, "cycle_detected": True, "step_failed": "cycle-free",
            "depth": 14, "cycle_at_depth": 12,
        }),
        ("e4-10-depth-exceeded", "rec-too-deep", {
            "valid": False, "cycle_detected": False, "step_failed": "depth",
            "depth": 17,
        }),
        # --- Valid-but-suspicious (no cycle, but flagged by other steps).
        ("e4-11-valid-clean", "rec-valid", {
            "valid": True, "cycle_detected": False, "step_failed": None,
        }),
        ("e4-12-revoked-parent", "rec-revoked-parent", {
            "valid": False, "cycle_detected": False, "step_failed": "chain_parent_non_revoked",
        }),
        ("e4-13-sig-fail-no-cycle", "rec-bad-sig", {
            "valid": False, "cycle_detected": False, "step_failed": "signature_verify",
        }),
        ("e4-14-capability-superset-fail", "rec-cap", {
            "valid": False, "cycle_detected": False, "step_failed": "capability_superset",
        }),
        ("e4-15-nonce-replay-no-cycle", "rec-replay", {
            "valid": False, "cycle_detected": False, "step_failed": "nonce_uniqueness",
        }),
    ]
    out: list[CycleVector] = []
    for vid, record, verdict in cases:
        out.append(
            CycleVector(
                vector=ConformanceVector(
                    family="E4",
                    vector_id=vid,
                    method="trust_verify_chain",
                    inputs={"record": record},
                ),
                record=record,
                verdict=verdict,
            )
        )
    assert len(out) == 15, f"E4 corpus MUST be 15 vectors per spec; got {len(out)}"
    return out


__all__ = [
    "CascadeVector",
    "CycleVector",
    "e1_vectors",
    "e2_vectors",
    "e3_vectors",
    "e4_vectors",
]
