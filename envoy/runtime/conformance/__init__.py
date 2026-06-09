# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.conformance — BET-6 cross-runtime conformance harness substrate.

Source of truth: `specs/runtime-abstraction.md` § Contract partition (BET-6),
§ Conformance vectors N1–N6, § Envoy-specific conformance E1–E7.

Phase 02 S1 ships the SKELETON only (per
`workspaces/phase-02-distribution/todos/active/01-m1-ws1-runtime-pluggability.md`
§ S1): the byte-identity scorer with field-localized diff, the corpus-row schema
with per-field tier tags (closes Spec-gap-3), and the parametrized pytest harness
in `tests/conformance/`. The vector CORPUS (N1–N6, E1–E7) lands in
S2b/S2c/S3a/S3b; the rs-bindings runtime wiring lands in S2a.
"""

from __future__ import annotations

from envoy.runtime.conformance.corpus import ConformanceVector, FieldTier
from envoy.runtime.conformance.scorer import (
    ByteIdentityMismatch,
    ScoreResult,
    canonical_hash,
    score_byte_identity,
)

__all__ = [
    "ConformanceVector",
    "FieldTier",
    "ByteIdentityMismatch",
    "ScoreResult",
    "canonical_hash",
    "score_byte_identity",
]
