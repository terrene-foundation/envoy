# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.conformance.corpus — conformance-vector row schema.

Source of truth: `specs/runtime-abstraction.md` § Conformance vectors N1–N6 +
§ Envoy-specific conformance E1–E7.

A conformance vector is one cross-runtime byte-identity (or, Phase-03, semantic)
gate: a method invocation whose canonical output must match across `kailash-py`
and `kailash-rs-bindings`. This module defines the ROW SCHEMA the corpus uses; the
actual vector data (N1 Knowledge Filter, E1 canonical JSON, …) is authored in
S2b/S2c/S3a/S3b — S1 only ships the schema the harness loads.

Per-field tier (Spec-gap-3,
`workspaces/phase-02-distribution/01-analysis/01-research/01-ws1-runtime-pluggability.md`
§ Gap 3): N3 and N4 are mixed-tier WITHIN a single vector — part of the output is
byte-identical, part is semantically-equivalent. A single per-method tier cannot
express this, so a vector carries an OPTIONAL `field_tiers` map keyed by JSON path
(e.g. ``{"verdict.structured": BYTE_IDENTICAL, "verdict.rendered_text":
SEMANTICALLY_EQUIVALENT}``). When `field_tiers` is empty the vector is scored
wholesale at the method's `__contract_tier__`; when present, each named field is
scored at its own tier and unnamed fields default to the method tier.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from envoy.runtime.contract_tier import ContractTier

#: Re-export so corpus authors import the tier enum from one place.
FieldTier = ContractTier


@dataclasses.dataclass(frozen=True)
class ConformanceVector:
    """One conformance-vector row.

    Fields:

    - ``family`` — vector family identifier (``"N1"``…``"N6"``, ``"E1"``…``"E7"``).
    - ``vector_id`` — unique within the family (e.g. ``"N2-007"``). Used as the
      pytest parametrize ID so a failure line names the exact vector:
      ``test_n2_envelope_cache[kailash-rs-bindings-N2-007]``.
    - ``method`` — the `KailashRuntime` method this vector exercises (e.g.
      ``"envelope_canonical_form"``). The method's `__contract_tier__` is the
      default scoring tier.
    - ``inputs`` — kwargs forwarded to the method under test.
    - ``field_tiers`` — OPTIONAL per-field tier overrides keyed by JSON path
      (Spec-gap-3). Empty ⇒ score the whole output at the method tier.
    - ``expected_dispatch`` — OPTIONAL N3 invariant: ``False`` for a structural-
      slice vector (classifier MUST NOT be dispatched), ``True`` for a semantic-
      slice vector (classifier MUST be dispatched). ``None`` ⇒ dispatch is not
      asserted for this vector.
    """

    family: str
    vector_id: str
    method: str
    inputs: dict[str, Any] = dataclasses.field(default_factory=dict)
    field_tiers: dict[str, FieldTier] = dataclasses.field(default_factory=dict)
    expected_dispatch: bool | None = None

    def __post_init__(self) -> None:
        if not self.family:
            raise ValueError("ConformanceVector.family must be non-empty")
        if not self.vector_id:
            raise ValueError("ConformanceVector.vector_id must be non-empty")
        if not self.method:
            raise ValueError("ConformanceVector.method must be non-empty")

    @property
    def test_id(self) -> str:
        """The parametrize ID component for this vector (the ``<vector_id>``
        half of ``test_<family>[<runtime>-<vector_id>]``)."""
        return self.vector_id


__all__ = ["ConformanceVector", "FieldTier"]
