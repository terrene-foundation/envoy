"""EnvelopeCompiler — the integration boundary primitive.

Implements `specs/envelope-model.md` § Schema + § Algorithms (Canonical JSON,
intersect_envelopes, monotonic-tightening) + carry-forward MED dispositions
R2-M-03 (sort authored_constraints) + R2-M-05 (IntersectConflictError propagate).

Per shard 4 § 4 step list:
1. Validate schema_version + algorithm_identifier match
2. Resolve template imports (publisher sig + reputation; local-only P01)
3. NFC-normalize all string values (handled by canonical_bytes pipeline)
4. Validate every numeric field via math.isfinite (NaN/Inf guard — done in dimension __post_init__)
5. If parent: RoleEnvelope.validate_tightening(parent, child)
6. Sort `authored_constraints` lexicographically (R2-M-03 carry-forward)
7. Compute authorship_score (delegated to AuthorshipScorer protocol — Wave 2 fills concrete impl)
8. JCS canonicalize → canonical_bytes + content_hash
9. Emit Ledger entry (delegated to LedgerWriter protocol — Wave 1 T-01-18 fills concrete impl)
10. Return EnvelopeConfig

Wave 1 ships the compile pipeline against protocol-typed dependencies for
AuthorshipScorer + LedgerWriter; concrete implementations land in Wave 2 + 1
respectively. This satisfies `rules/orphan-detection.md` Rule 1 (every facade
has a hot-path call site within 5 commits — the compiler IS the call site;
the protocol guarantees the wiring contract is testable now).
"""

from __future__ import annotations

import math
import uuid
import dataclasses
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from envoy.envelope.canonical_bytes import canonical_bytes as _canonical_bytes
from envoy.envelope.canonical_bytes import content_hash as _content_hash
from envoy.envelope.errors import (
    EnvelopeCompilationError,
    EnvelopeValidationError,
    MonotonicTighteningError,
    SchemaVersionMismatchError,
)
from envoy.envelope.template_resolver import (
    EnvelopeTemplate,
    EnvelopeTemplateResolver,
    TemplateRef,
)
from envoy.envelope.types import (
    AlgorithmIdentifier,
    AuthoredConstraint,
    EnvelopeConfig,
    EnvelopeConfigInput,
    ImportedConstraint,
)

SUPPORTED_SCHEMA_VERSION = "envelope/1.0"


class AuthorshipScorer(Protocol):
    """Protocol satisfied by `envoy.authorship.score.AuthorshipScore` (Wave 2)."""

    def score_input(self, config_input: EnvelopeConfigInput) -> dict[str, Any]:
        """Return {authored_count, imported_count, template_provenance}.

        Ordering invariant (compile pipeline step 7): this method is called
        BEFORE `metadata.algorithm_identifier` and `metadata.envelope_id` are
        pinned. Concrete implementations MUST NOT consume those fields from
        `config_input.metadata` — they are not canonical at this point in
        the pipeline. Consume `metadata.authorship_score`, the dimension
        `authored_constraints` / `imported_constraints` tuples, and
        `template_refs` only.
        """
        ...


class LedgerWriter(Protocol):
    """Protocol satisfied by `envoy.ledger.facade.EnvoyLedger` (Wave 1 T-01-18)."""

    def append(
        self,
        *,
        principal_id: str,
        entry_type: str,
        payload: dict[str, Any],
    ) -> None: ...


class _NoopAuthorshipScorer:
    """Phase 01 placeholder until Wave 2 ships shard 9.

    Returns the input's existing authorship_score block verbatim. Tests that
    need a real score can substitute a fake or wait for T-02-30.
    """

    def score_input(self, config_input: EnvelopeConfigInput) -> dict[str, Any]:
        return dict(config_input.metadata.authorship_score)


class _NoopLedgerWriter:
    """Phase 01 placeholder until Wave 1 T-01-18 ships shard 6.

    Compiles produce no Ledger entry. Tier 2 wiring tests substitute a real
    writer (T-01-21).
    """

    def append(self, *, principal_id: str, entry_type: str, payload: dict[str, Any]) -> None:
        return None


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


class EnvelopeCompiler:
    """Compile `EnvelopeConfigInput` → canonical `EnvelopeConfig`.

    Per shard 4 § 4 + carry-forward dispositions:
    - R2-M-03: sort `authored_constraints` lexicographically by constraint_id
      at construction (BEFORE authorship-score + JCS canonicalize so both
      surfaces see the canonical ordering).
    - R2-M-05: `IntersectConflictError` propagates verbatim; never silently
      fall back to a "best-effort" intersection.

    Per `rules/tenant-isolation.md` Rule 2: compile() takes `principal_id`
    keyword arg (no default); raises if missing.
    """

    def __init__(
        self,
        *,
        template_resolver: EnvelopeTemplateResolver,
        authorship_scorer: AuthorshipScorer | None = None,
        ledger_writer: LedgerWriter | None = None,
        algorithm_identifier: AlgorithmIdentifier | None = None,
    ) -> None:
        self._template_resolver = template_resolver
        self._authorship_scorer: AuthorshipScorer = (
            authorship_scorer if authorship_scorer is not None else _NoopAuthorshipScorer()
        )
        self._ledger_writer: LedgerWriter = (
            ledger_writer if ledger_writer is not None else _NoopLedgerWriter()
        )
        self._algorithm_identifier = (
            algorithm_identifier if algorithm_identifier is not None else AlgorithmIdentifier()
        )

    # ------------------------------------------------------------------
    # Compile pipeline
    # ------------------------------------------------------------------

    def compile(
        self,
        config_input: EnvelopeConfigInput,
        *,
        principal_id: str,
        parent: EnvelopeConfig | None = None,
        envelope_version: int = 1,
    ) -> EnvelopeConfig:
        """Compile authored input into a canonical envelope.

        Per `rules/tenant-isolation.md` Rule 2, `principal_id` is required (no
        default). The compiler does not persist `principal_id` on the envelope
        itself (the envelope is principal-agnostic; binding happens at the
        Trust store DelegationRecord layer). It IS persisted on the Ledger
        entry the compile emits.
        """
        if not principal_id or not isinstance(principal_id, str):
            raise EnvelopeValidationError(
                "principal_id is required (per rules/tenant-isolation.md Rule 2)",
                field="principal_id",
            )

        # Step 1 — schema version + algorithm identifier validation
        if config_input.schema_version != SUPPORTED_SCHEMA_VERSION:
            raise SchemaVersionMismatchError(
                f"unsupported schema_version (expected {SUPPORTED_SCHEMA_VERSION!r})",
                field="schema_version",
            )

        # Step 2 — resolve template imports (Phase 01: local-only)
        templates = [
            self._template_resolver.resolve(TemplateRef(uri=ref))
            for ref in config_input.template_refs
        ]
        config_input = self._fold_templates(config_input, templates)

        # Step 3 — NFC normalization is done by canonical_bytes pipeline (step 8)

        # Step 4 — NaN/Inf guard already enforced by FinancialDimension.__post_init__
        # Re-check for any non-FinancialDimension numeric fields:
        if not (
            isinstance(config_input.tool_output_budget_bytes, int)
            and math.isfinite(config_input.tool_output_budget_bytes)
        ):
            raise EnvelopeValidationError(
                "tool_output_budget_bytes must be a finite integer",
                field="tool_output_budget_bytes",
            )
        if config_input.tool_output_budget_bytes <= 0:
            raise EnvelopeValidationError(
                "tool_output_budget_bytes must be positive",
                field="tool_output_budget_bytes",
            )

        # Step 5 — monotonic tightening if parent supplied
        if parent is not None:
            self._validate_monotonic_tightening(parent, config_input)

        # Step 6 — R2-M-03: sort authored_constraints lexicographically
        config_input = self._sort_authored_constraints(config_input)

        # Step 7 — authorship score (delegated) + algorithm pin + envelope_id
        # mint. L-03 shard B: EnvelopeMetadata is now frozen; we build a new
        # metadata via dataclasses.replace and assign to the (still-mutable)
        # config_input.metadata field. Three field updates collapse into
        # ONE atomic replace per Phase 01 simplicity.
        #
        # Ordering invariant: score_input is called BEFORE algorithm_identifier
        # and envelope_id are pinned (the new pinned values land in the SAME
        # dataclasses.replace that consumes authorship). Real Wave 2
        # AuthorshipScorer impls MUST NOT consume metadata.algorithm_identifier
        # or metadata.envelope_id from the input — those fields are not yet
        # canonical at this point in the pipeline.
        authorship = self._authorship_scorer.score_input(config_input)
        new_envelope_id = config_input.metadata.envelope_id or str(uuid.uuid4())
        # uuid-v7 isn't in stdlib pre-3.14; uuid-v4 is the Phase 01
        # disposition — registry-safe and crypto-random. Phase 02 entry
        # can swap to uuid-v7 for time-orderable IDs.
        config_input.metadata = dataclasses.replace(
            config_input.metadata,
            authorship_score=dict(authorship),
            algorithm_identifier=self._algorithm_identifier,
            envelope_id=new_envelope_id,
        )

        # Step 8 — JCS canonicalize → canonical_bytes + content_hash
        payload = self._to_canonical_payload(config_input, envelope_version=envelope_version)
        cb = _canonical_bytes(payload)
        ch = _content_hash(cb)

        compiled = EnvelopeConfig(
            schema_version=config_input.schema_version,
            envelope_version=envelope_version,
            metadata=config_input.metadata,
            financial=config_input.financial,
            operational=config_input.operational,
            temporal=config_input.temporal,
            data_access=config_input.data_access,
            communication=config_input.communication,
            composition_rules=tuple(config_input.composition_rules),
            cross_domain_rules_authored=tuple(config_input.cross_domain_rules_authored),
            tool_output_budget_bytes=config_input.tool_output_budget_bytes,
            semantic_checks=config_input.semantic_checks,
            canonical_bytes=cb,
            content_hash=ch,
            compiled_at=datetime.now(tz=timezone.utc),
        )

        # Step 9 — Ledger entry (delegated)
        self._ledger_writer.append(
            principal_id=principal_id,
            entry_type="envelope_compile" if parent is None else "envelope_edit",
            payload={
                "envelope_id": compiled.metadata.envelope_id,
                "envelope_version": envelope_version,
                "content_hash": ch,
                "parent_content_hash": parent.content_hash if parent is not None else None,
            },
        )

        return compiled

    # ------------------------------------------------------------------
    # Note: `intersect()` is intentionally NOT shipped in T-01-10.
    # ------------------------------------------------------------------
    # Per `rules/zero-tolerance.md` Rule 6 (Implement Fully) + Rule 2 (No
    # Stubs): the full `kailash.trust.pact.envelopes.intersect_envelopes`
    # wrap requires a clearance-mapping translation layer (kailash-py uses
    # `public/restricted/confidential/secret/top_secret`; envoy spec uses
    # `Public/Internal/Confidential/Restricted/HighlyConfidential` per V-06).
    # That translation belongs in Wave 3 where Grant Moment (T-03-50) surfaces
    # the first divergent-dim intersect consumer. Shipping a partial intersect
    # here would be a Rule-2 stub.
    #
    # `IntersectConflictError` (in errors.py) IS retained — it's a typed-error
    # declaration consumed by the Wave-3 producer; declaring exception classes
    # ahead of their producer is the conventional Python idiom and not an
    # orphan-detection violation per `rules/orphan-detection.md` § scope.

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_monotonic_tightening(
        self, parent: EnvelopeConfig, child: EnvelopeConfigInput
    ) -> None:
        """Enforce monotonic tightening on the 5-dimension surface.

        Phase 01 disposition: the compile-time enforcement covers the four
        cases where a child config widens a parent ceiling (financial) or
        denylist (operational). Full kailash-py
        `RoleEnvelope.validate_tightening` integration lands when Grant Moment
        surfaces approve+author exception flows in Wave 3 (T-03-50 ChannelHandoff
        + T-03-52 CascadeRevocationOrchestrator).
        """
        # Financial: every child ceiling MUST be ≤ parent
        for attr in (
            "per_call_ceiling_microdollars",
            "per_session_ceiling_microdollars",
            "per_hour_velocity_microdollars",
            "per_day_ceiling_microdollars",
            "per_month_ceiling_microdollars",
        ):
            p_val = getattr(parent.financial, attr)
            c_val = getattr(child.financial, attr)
            # 0 means unconfigured (open) — child=0 with parent>0 is widening.
            if p_val > 0 and (c_val == 0 or c_val > p_val):
                raise MonotonicTighteningError(
                    f"financial.{attr} widens parent (parent={p_val}, child={c_val})",
                    envelope_id=parent.metadata.envelope_id,
                )

        # Operational: child tool_allowlist MUST be subset of parent's allowlist
        # (when parent has a non-empty allowlist).
        if parent.operational.tool_allowlist:
            for tool in child.operational.tool_allowlist:
                if tool not in parent.operational.tool_allowlist:
                    raise MonotonicTighteningError(
                        f"operational.tool_allowlist widens parent (tool={tool!r})",
                        envelope_id=parent.metadata.envelope_id,
                    )

    def _sort_authored_constraints(self, config_input: EnvelopeConfigInput) -> EnvelopeConfigInput:
        """R2-M-03: sort authored_constraints lexicographically.

        JCS canonicalization (RFC 8785) requires stable iteration order. Python
        dict iteration order is insertion-stable but the upstream input may
        have been deserialized from a non-deterministic source. Single-point
        sort here means downstream surfaces (authorship-score + JCS) see the
        canonical ordering.
        """

        def _sort_dim(
            constraints: tuple[AuthoredConstraint, ...],
        ) -> tuple[AuthoredConstraint, ...]:
            # L-03 shard A: returns tuple to match the dimension's
            # tuple-typed authored_constraints field.
            return tuple(sorted(constraints, key=lambda c: c.constraint_id))

        # L-03 shard B step 2: dimensions are now frozen; mint new instances
        # via dataclasses.replace and re-assign to the (still-mutable)
        # config_input. Five replace calls — one per dimension.
        config_input.financial = dataclasses.replace(
            config_input.financial,
            authored_constraints=_sort_dim(config_input.financial.authored_constraints),
        )
        config_input.operational = dataclasses.replace(
            config_input.operational,
            authored_constraints=_sort_dim(config_input.operational.authored_constraints),
        )
        config_input.temporal = dataclasses.replace(
            config_input.temporal,
            authored_constraints=_sort_dim(config_input.temporal.authored_constraints),
        )
        config_input.data_access = dataclasses.replace(
            config_input.data_access,
            authored_constraints=_sort_dim(config_input.data_access.authored_constraints),
        )
        config_input.communication = dataclasses.replace(
            config_input.communication,
            authored_constraints=_sort_dim(config_input.communication.authored_constraints),
        )
        return config_input

    def _fold_templates(
        self,
        config_input: EnvelopeConfigInput,
        templates: list[EnvelopeTemplate],
    ) -> EnvelopeConfigInput:
        """Fold resolved templates into per-dimension imported_constraints[].

        Phase 01 ships the minimum: copy template's per-dimension constraints
        into `imported_constraints[]` with `authored=false` + `template_origin`
        + `template_hash`. Cross-domain rule folding lands when shard 16
        + 22 surface real cross-domain consumers.
        """
        for tmpl in templates:
            content = tmpl.content
            for dim_name in (
                "financial",
                "operational",
                "temporal",
                "data_access",
                "communication",
            ):
                dim = getattr(config_input, dim_name)
                tmpl_dim = content.get(dim_name, {})
                # L-03 shard A: tuple += instead of .append since
                # imported_constraints is now a tuple. Build a list of new
                # constraints, then assign as a tuple-extension of the
                # existing field.
                new_imported: list[ImportedConstraint] = []
                for raw in tmpl_dim.get("authored_constraints", []):
                    # Imported constraints carry over the template's authored
                    # rule but flip `authored=False` so Authorship Score doesn't
                    # credit them per `specs/authorship-score.md` § Field
                    # semantics for late-added fields.
                    new_imported.append(
                        ImportedConstraint(
                            constraint_id=raw["constraint_id"],
                            rule_ast=raw.get("rule_ast", {}),
                            template_origin=tmpl.template_origin,
                            template_hash=tmpl.template_hash,
                        )
                    )
                if new_imported:
                    # L-03 shard B step 2: dimension is frozen; mint a new
                    # instance via dataclasses.replace and re-assign to the
                    # (still-mutable) config_input slot.
                    setattr(
                        config_input,
                        dim_name,
                        dataclasses.replace(
                            dim,
                            imported_constraints=dim.imported_constraints + tuple(new_imported),
                        ),
                    )
            # Provenance trail in metadata. L-03 shard B step 1 pinned this
            # ordering (provenance MUST be appended BEFORE step 7's metadata
            # replace) — see TestPipelineOrderingInvariant in tier1.
            config_input.metadata.authorship_score.setdefault("template_provenance", []).append(
                {"uri": tmpl.ref.uri, "hash": tmpl.template_hash}
            )
        return config_input

    def _to_canonical_payload(
        self, config_input: EnvelopeConfigInput, *, envelope_version: int
    ) -> dict[str, Any]:
        """Convert the (sorted) input into a JSON-able dict for canonical_bytes."""
        return {
            "schema_version": config_input.schema_version,
            "envelope_version": envelope_version,
            "metadata": _enum_safe(asdict(config_input.metadata)),
            "financial": _enum_safe(asdict(config_input.financial)),
            "operational": _enum_safe(asdict(config_input.operational)),
            "temporal": _enum_safe(asdict(config_input.temporal)),
            "data_access": _enum_safe(asdict(config_input.data_access)),
            "communication": _enum_safe(asdict(config_input.communication)),
            "composition_rules": [_enum_safe(asdict(r)) for r in config_input.composition_rules],
            "cross_domain_rules_authored": [
                _enum_safe(asdict(r)) for r in config_input.cross_domain_rules_authored
            ],
            "tool_output_budget_bytes": config_input.tool_output_budget_bytes,
            "semantic_checks": _enum_safe(asdict(config_input.semantic_checks)),
        }


def _enum_safe(value: Any) -> Any:
    """Recursively convert Enum values to their .value for JSON serialization."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _enum_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_enum_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_enum_safe(v) for v in value]
    return value


# Surface the EnvelopeCompilationError import so it's reachable via re-export
__all__ = [
    "EnvelopeCompiler",
    "EnvelopeCompilationError",
    "AuthorshipScorer",
    "LedgerWriter",
    "SUPPORTED_SCHEMA_VERSION",
]
