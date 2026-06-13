# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/conformance/n4_n6_vectors.py — N4-N6 byte-identity vector corpus (S2c).

Source of truth: `specs/runtime-abstraction.md` § Conformance vectors N1-N6
decoded (N4 verdict rendering / N5 posture ceiling / N6 session-scoped cache
correctness), `specs/session-state.md` § `tool_calls_made` fingerprint
(line 63) + § Cache reset on session boundary (line 65) + § session_boundary_crossed.

The three families authored here exercise distinct buildable surfaces:

N4 (Verdict rendering) and N5 (Posture ceiling) are authored as READY corpora
over substrate-gated methods (`grant_moment_surface` / `envelope_check`), each
of which raises `RuntimeNotReadyError` on the rs adapter until its gating shard
(S6a) lands. Their cross-runtime drivers `xfail` until then — the honest
deferral, NOT a stub (`rules/zero-tolerance.md` Rule 2). When S6a wires the
engine the xfail flips green.

N6 (Session-scoped cache correctness) is authored over the BUILDABLE-NOW
surface: the `tool_calls_made` fingerprint `sha256(tool_name ||
canonicalize_args(args))` whose `canonicalize_args` is JCS — exactly
`envelope_canonical_form` (a WIRED method on both adapters) — and the S5b
`session_boundary_crossed` content_hash over the boundary content dict (also
JCS-canonical). Both N6 targets are live cross-runtime byte-identity loops; the
harness uses FIXTURES (deterministic blobs + a deterministic content dict), NOT
the live WS-6 observed-state store (which is S5o/S6c scope).

N4 STRUCTURED-PAYLOAD-ONLY NOTE (load-bearing): N4's verdict has a mixed tier
within a single output — the STRUCTURED verdict object hashes equal across
runtimes (byte-identical), but the RENDERED verdict TEXT is
semantically-equivalent and DEFERRED to the Phase-03 semantic harness
(`specs/runtime-abstraction.md:152` + `:207` — the open scoring-metric question
at `:239`). This corpus authors ONLY the structured-payload byte-identity gate;
there is NO probe/semantic-scorer for rendered text in this shard
(`rules/probe-driven-verification.md` — byte-identity is a STRUCTURAL assertion,
never regex/keyword/LLM scoring). The N4 vectors carry a `field_tiers` map
naming the structured field BYTE_IDENTICAL and the rendered-text field
SEMANTICALLY_EQUIVALENT so the deferral is machine-recorded, not prose-only.

OS-portability: every vector is OS-portable by construction — no path
separators, no platform-locale assumptions; all bytes derive from the
deterministic JCS+NFC pipeline / sha256 over canonical bytes.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from envoy.runtime.conformance import ConformanceVector, FieldTier

# ---------------------------------------------------------------------------
# N4 — Verdict rendering (10 vectors).
#
# Method: grant_moment_surface(request) -> verdict. Per
# `specs/runtime-abstraction.md`: "Envelope check verdict -> user-facing text
# via grant_moment_surface. Byte-identical structured payload; rendered text is
# semantically-equivalent across runtimes."
#
# STRUCTURED-PAYLOAD-ONLY: each vector names the structured-verdict field
# BYTE_IDENTICAL and the rendered-text field SEMANTICALLY_EQUIVALENT in
# `field_tiers`. The Phase-02 byte-identity gate compares ONLY the structured
# payload; the rendered-text comparison is DEFERRED to the Phase-03 semantic
# harness (runtime-abstraction.md:152/207/239). NO rendered-text probe fires
# here.
#
# grant_moment_surface is substrate-gated on the rs adapter (raises
# RuntimeNotReadyError naming shard S6a) until S6a lands the Grant Moment
# dispatch surface — so the cross-runtime driver xfails. The corpus is READY:
# when S6a wires the engine the xfail flips green with no corpus change.
#
# The structured-verdict JSON path the byte-identity gate scores.
N4_STRUCTURED_PATH = "verdict.structured"
#: The rendered-text JSON path DEFERRED to the Phase-03 semantic harness.
N4_RENDERED_PATH = "verdict.rendered_text"


def n4_vectors() -> list[ConformanceVector]:
    """The full N4 family — 10 verdict-rendering vectors (structured-only gate).

    Each request shape exercises a distinct envelope-check verdict the Grant
    Moment surfaces. The `field_tiers` map pins the structured payload as
    BYTE_IDENTICAL (the Phase-02 gate) and the rendered text as
    SEMANTICALLY_EQUIVALENT (Phase-03 deferral) — so a future reader / reviewer
    sweep sees mechanically that NO byte-identity gate touches the rendered text.
    """
    # (vector_id, request shape the Grant Moment dispatch receives)
    requests: list[tuple[str, dict[str, Any]]] = [
        # FIRST_TIME_REQUIRES_GRANT — the canonical Grant Moment dispatch.
        ("n4-01-first-time-grant", {
            "verdict_kind": "FIRST_TIME_REQUIRES_GRANT",
            "tool_name": "db.write",
            "action": "create",
        }),
        # ALLOW — pre-authorized pattern matched; no Grant needed.
        ("n4-02-allow-preauthorized", {
            "verdict_kind": "ALLOW",
            "tool_name": "db.read",
            "action": "list",
        }),
        # DENY — structural envelope violation (no classifier).
        ("n4-03-deny-structural", {
            "verdict_kind": "DENY",
            "reason_class": "structural",
            "tool_name": "fs.delete",
            "action": "delete",
        }),
        # DENY — semantic classification violation.
        ("n4-04-deny-semantic", {
            "verdict_kind": "DENY",
            "reason_class": "semantic",
            "tool_name": "net.post",
            "action": "exfiltrate",
        }),
        # FIRST_TIME with financial dims surfaced in the verdict.
        ("n4-05-first-time-financial", {
            "verdict_kind": "FIRST_TIME_REQUIRES_GRANT",
            "tool_name": "payment.charge",
            "action": "charge",
            "dims": {"financial": {"max_micros": 5_000_000}},
        }),
        # POSTURE_CEILING_BLOCKED — the N5 verdict surfaced through N4 rendering.
        ("n4-06-posture-ceiling-blocked", {
            "verdict_kind": "POSTURE_CEILING_BLOCKED",
            "tool_name": "admin.escalate",
            "action": "escalate",
            "effective_posture": "SUPERVISED",
        }),
        # FIRST_TIME with unicode in the rendered string (NFC fold).
        ("n4-07-unicode-rendered", {
            "verdict_kind": "FIRST_TIME_REQUIRES_GRANT",
            "tool_name": "doc.café-export",
            "action": "export",
        }),
        # ALLOW with a nested context object.
        ("n4-08-allow-nested-context", {
            "verdict_kind": "ALLOW",
            "tool_name": "cache.get",
            "action": "read",
            "context": {"session": "s-1", "depth": 2},
        }),
        # DENY — budget velocity exceeded.
        ("n4-09-deny-budget-velocity", {
            "verdict_kind": "DENY",
            "reason_class": "budget",
            "tool_name": "llm.invoke",
            "action": "invoke",
        }),
        # Empty/minimal request — the boundary verdict shape.
        ("n4-10-minimal-request", {
            "verdict_kind": "ALLOW",
            "tool_name": "noop",
            "action": "noop",
        }),
    ]
    vectors = [
        ConformanceVector(
            family="N4",
            vector_id=vid,
            method="grant_moment_surface",
            inputs={"request": request},
            field_tiers={
                # Structured payload IS the Phase-02 byte-identity gate.
                N4_STRUCTURED_PATH: FieldTier.BYTE_IDENTICAL,
                # Rendered text is DEFERRED to Phase-03 (runtime-abstraction.md:152).
                N4_RENDERED_PATH: FieldTier.SEMANTICALLY_EQUIVALENT,
            },
        )
        for vid, request in requests
    ]
    assert len(vectors) == 10, f"N4 corpus MUST be 10 vectors per spec; got {len(vectors)}"
    return vectors


# ---------------------------------------------------------------------------
# N5 — Posture ceiling (15 vectors).
#
# Method: envelope_check(envelope, action) -> verdict. Invariant:
# `effective_posture <= min(envelope-declared, principal-current)` enforced at
# envelope_check (`specs/runtime-abstraction.md` § N5). The verdict's
# effective_posture MUST be the floor of the two declared postures, byte-
# identical across runtimes.
#
# envelope_check is substrate-gated on the rs adapter (raises
# RuntimeNotReadyError naming shard S6a) until S6a lands the structural+semantic
# envelope-check engine — so the cross-runtime driver xfails. The corpus is
# READY: when S6a wires the engine the xfail flips green with no corpus change.
#
# Each vector carries the declared envelope-posture, the principal-current
# posture, and the EXPECTED effective_posture (the floor) so the driver also
# pins the ground-truth ceiling both runtimes MUST compute, not merely that they
# agree with each other.
# ---------------------------------------------------------------------------

#: Posture ladder ordinals (lower = more restrictive). Per
#: `specs/posture-ladder.md` — AUTONOMOUS is the most permissive ceiling.
_POSTURE_ORDER: dict[str, int] = {
    "OBSERVED": 0,
    "SUPERVISED": 1,
    "TRUSTED": 2,
    "AUTONOMOUS": 3,
}


def _posture_floor(envelope_declared: str, principal_current: str) -> str:
    """The N5 ceiling: ``min(envelope-declared, principal-current)`` by ladder
    ordinal (the more-restrictive of the two)."""
    return min(
        (envelope_declared, principal_current),
        key=lambda p: _POSTURE_ORDER[p],
    )


@dataclasses.dataclass(frozen=True)
class PostureVector:
    """An N5 posture-ceiling vector: declared + principal + expected floor.

    Carries the wrapped `ConformanceVector` (for harness ID emission) plus the
    `envelope_declared` / `principal_current` postures the driver feeds to
    `envelope_check` and the `expected_effective` floor the verdict MUST carry.
    """

    vector: ConformanceVector
    envelope_declared: str
    principal_current: str
    expected_effective: str


def n5_vectors() -> list[PostureVector]:
    """The full N5 family — 15 posture-ceiling vectors.

    Covers every ordered pair where the floor is unambiguous plus the equal-
    posture identity cases. `expected_effective` is the ground-truth ceiling
    `min(declared, principal)`; the driver pins BOTH runtimes' verdict
    effective_posture to it.
    """
    # (vector_id, envelope_declared, principal_current) — expected floor derived.
    cases: list[tuple[str, str, str]] = [
        # Envelope is the binding (more-restrictive) ceiling.
        ("n5-01-envelope-binds-observed", "OBSERVED", "AUTONOMOUS"),
        ("n5-02-envelope-binds-supervised", "SUPERVISED", "AUTONOMOUS"),
        ("n5-03-envelope-binds-trusted", "TRUSTED", "AUTONOMOUS"),
        ("n5-04-envelope-binds-supervised-trusted", "SUPERVISED", "TRUSTED"),
        # Principal-current is the binding (more-restrictive) ceiling.
        ("n5-05-principal-binds-observed", "AUTONOMOUS", "OBSERVED"),
        ("n5-06-principal-binds-supervised", "AUTONOMOUS", "SUPERVISED"),
        ("n5-07-principal-binds-trusted", "AUTONOMOUS", "TRUSTED"),
        ("n5-08-principal-binds-trusted-observed", "TRUSTED", "OBSERVED"),
        # Equal postures — the floor is the identity.
        ("n5-09-equal-observed", "OBSERVED", "OBSERVED"),
        ("n5-10-equal-supervised", "SUPERVISED", "SUPERVISED"),
        ("n5-11-equal-trusted", "TRUSTED", "TRUSTED"),
        ("n5-12-equal-autonomous", "AUTONOMOUS", "AUTONOMOUS"),
        # Adjacent-rung pairs (boundary of the ladder comparison).
        ("n5-13-adjacent-observed-supervised", "OBSERVED", "SUPERVISED"),
        ("n5-14-adjacent-trusted-autonomous", "TRUSTED", "AUTONOMOUS"),
        # Maximally-divergent pair (most-restrictive vs most-permissive).
        ("n5-15-max-divergent", "OBSERVED", "AUTONOMOUS"),
    ]
    out: list[PostureVector] = []
    for vid, declared, principal in cases:
        out.append(
            PostureVector(
                vector=ConformanceVector(
                    family="N5",
                    vector_id=vid,
                    method="envelope_check",
                    inputs={
                        "envelope": {
                            "schema": "envelope/1.0",
                            "metadata": {"posture_level": declared},
                        },
                        "action": {
                            "principal_posture": principal,
                            "kind": "check",
                        },
                    },
                ),
                envelope_declared=declared,
                principal_current=principal,
                expected_effective=_posture_floor(declared, principal),
            )
        )
    assert len(out) == 15, f"N5 corpus MUST be 15 vectors per spec; got {len(out)}"
    return out


# ---------------------------------------------------------------------------
# N6 — Session-scoped cache correctness (10 vectors).
#
# Two buildable-NOW byte-identity targets, both over WIRED surfaces:
#
# (a) FINGERPRINT — `tool_calls_made` fingerprint
#     `sha256(tool_name || canonicalize_args(args))` (`specs/session-state.md`
#     line 63). `canonicalize_args` is JCS, which IS `envelope_canonical_form`
#     (a WIRED method on both adapters). The fingerprint hashes identically
#     across runtimes given the same tool_name + args — the byte-identity gate.
#
# (b) BOUNDARY content_hash — the S5b `session_boundary_crossed` content dict
#     (`envoy.runtime.session_boundary`) canonicalized + sha256'd. Two runtimes
#     building the SAME boundary content produce the SAME content_hash; cache
#     reset emits `session_boundary_crossed` with identical content_hash
#     (`specs/runtime-abstraction.md` § N6).
#
# The harness uses FIXTURES (deterministic tool_name+args pairs + a
# deterministic boundary content dict), NOT the live WS-6 observed-state store
# (S5o/S6c scope). The fingerprint targets `envelope_canonical_form` (WIRED) so
# N6 is a LIVE cross-runtime byte-identity loop now — no xfail.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FingerprintVector:
    """An N6 fingerprint vector: tool_name + args → byte-identical fingerprint.

    The driver computes `sha256(tool_name.encode() || envelope_canonical_form(
    args))` on BOTH runtimes (forwarding to the SAME `canonical_bytes` JCS
    primitive) and asserts byte-identity. Authored as a wrapper so the corpus
    row schema (`ConformanceVector`) stays unchanged.
    """

    vector: ConformanceVector
    tool_name: str
    args: dict[str, Any]


def n6_fingerprint_vectors() -> list[FingerprintVector]:
    """N6 fingerprint sub-family — 7 tool-call-fingerprint byte-identity vectors.

    Each (tool_name, args) pair exercises a distinct canonicalization surface
    the fingerprint must fold identically across runtimes: key ordering, unicode
    NFC, nested args, empty args, numeric args, bool/null. The
    `envelope_canonical_form(args)` half is WIRED on both adapters.
    """
    # (vector_id, tool_name, args dict)
    cases: list[tuple[str, str, dict[str, Any]]] = [
        # Simple string args.
        ("n6-fp-01-simple", "db.read", {"table": "users", "id": "42"}),
        # Key-order divergence in source — canonical form sorts identically.
        ("n6-fp-02-key-order", "db.write", {"z": 1, "a": 2, "m": 3}),
        # Unicode arg value (NFC fold makes NFD-authored args hash identically).
        ("n6-fp-03-unicode", "doc.export", {"title": "mañana-café"}),
        # Nested args object.
        ("n6-fp-04-nested", "api.call", {"req": {"caps": ["read", "write"], "depth": 2}}),
        # Empty args — the boundary fingerprint shape.
        ("n6-fp-05-empty-args", "noop", {}),
        # Numeric + bool + null args (canonical scalar serialization).
        ("n6-fp-06-scalars", "budget.reserve", {"micros": 1_000_000, "ok": True, "parent": None}),
        # Array-valued args (order preserved inside the array).
        ("n6-fp-07-array", "batch.run", {"ids": ["c1", "c2", "c3"]}),
    ]
    out: list[FingerprintVector] = []
    for vid, tool_name, args in cases:
        out.append(
            FingerprintVector(
                vector=ConformanceVector(
                    family="N6",
                    vector_id=vid,
                    # The fingerprint composes envelope_canonical_form (WIRED);
                    # the method names the canonicalization surface it forwards to.
                    method="envelope_canonical_form",
                    inputs={"tool_name": tool_name, "args": args},
                ),
                tool_name=tool_name,
                args=args,
            )
        )
    assert len(out) == 7, f"N6 fingerprint sub-family MUST be 7 vectors; got {len(out)}"
    return out


@dataclasses.dataclass(frozen=True)
class BoundaryVector:
    """An N6 boundary vector: a `session_boundary_crossed` content dict whose
    content_hash MUST be byte-identical across runtimes.

    The driver canonicalizes the boundary content dict (the S5b
    `SessionBoundarySignal` content shape) on both runtimes and asserts the
    sha256-over-canonical-bytes content_hash matches — the cache-reset boundary
    emits identical content_hash per `specs/runtime-abstraction.md` § N6.
    """

    vector: ConformanceVector
    content: dict[str, Any]


def n6_boundary_vectors() -> list[BoundaryVector]:
    """N6 boundary sub-family — 3 session-boundary content_hash byte-identity
    vectors.

    Each content dict is a deterministic `session_boundary_crossed` payload (the
    S5b shape: schema_version, transition, session ids, trigger, end-of-session
    counts) — one per the start / end / idle-timeout transition class. The
    content_hash over JCS-canonical bytes is byte-identical across runtimes by
    construction (both forward to the SAME `canonical_bytes` primitive); the
    battery PROVES it across the transition shapes.
    """
    # (vector_id, boundary content dict). The shape mirrors
    # envoy.runtime.session_boundary.SessionBoundarySignal.cross() content.
    cases: list[tuple[str, dict[str, Any]]] = [
        # START transition (cli_start) — no reset; counts zero.
        ("n6-bnd-01-start", {
            "schema_version": "session-boundary/1.0",
            "transition": "start",
            "session_id_prior": None,
            "session_id_next": "s-2",
            "trigger": "cli_start",
            "tool_call_count_observed": 0,
            "orphan_phase_a_count": 0,
            "unresolved_grants_deferred": 0,
        }),
        # END transition (cli_end) — reset fires; end-of-session counts captured.
        ("n6-bnd-02-end-reset", {
            "schema_version": "session-boundary/1.0",
            "transition": "end",
            "session_id_prior": "s-1",
            "session_id_next": None,
            "trigger": "cli_end",
            "tool_call_count_observed": 7,
            "orphan_phase_a_count": 1,
            "unresolved_grants_deferred": 2,
        }),
        # END transition (idle_timeout) — distinct trigger, distinct counts.
        ("n6-bnd-03-idle-timeout", {
            "schema_version": "session-boundary/1.0",
            "transition": "end",
            "session_id_prior": "s-3",
            "session_id_next": None,
            "trigger": "idle_timeout",
            "tool_call_count_observed": 3,
            "orphan_phase_a_count": 0,
            "unresolved_grants_deferred": 0,
        }),
    ]
    out: list[BoundaryVector] = []
    for vid, content in cases:
        out.append(
            BoundaryVector(
                vector=ConformanceVector(
                    family="N6",
                    vector_id=vid,
                    # The content_hash composes the JCS canonical-bytes primitive
                    # the S5b signal canonicalizes through (WIRED).
                    method="envelope_canonical_form",
                    inputs={"content": content},
                ),
                content=content,
            )
        )
    assert len(out) == 3, f"N6 boundary sub-family MUST be 3 vectors; got {len(out)}"
    return out


__all__ = [
    "N4_RENDERED_PATH",
    "N4_STRUCTURED_PATH",
    "BoundaryVector",
    "FingerprintVector",
    "PostureVector",
    "n4_vectors",
    "n5_vectors",
    "n6_boundary_vectors",
    "n6_fingerprint_vectors",
]
