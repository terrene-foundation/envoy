# Wave 1 follow-up — L-03: frozen dimension dataclasses

Origin: gate-level security review of PR #3 (Phase 01 Wave 1) finding L-03 — out-of-shard for T-01-15's budget.

## Problem

`envoy/envelope/types.py` ships these dataclasses with `slots=True` only (NOT `frozen=True`):

- `FinancialDimension` (line ~92)
- `OperationalDimension` (line ~129)
- `TemporalDimension` (line ~141)
- `DataAccessDimension` (line ~151)
- `CommunicationDimension` (line ~163)
- `EnvelopeMetadata` (line ~236)
- `SemanticChecks` (referenced by EnvelopeMetadata)

`EnvelopeConfig` IS `frozen=True` (line ~294), but holds references to the still-mutable nested dimensions. Per `rules/trust-plane-security.md` MUST NOT Rule 4: every constraint dataclass MUST be `@dataclass(frozen=True)`. The current shape lets a downstream consumer mutate `compiled.financial.per_call_ceiling_microdollars` after compile, breaking `content_hash` integrity.

## Why deferred from T-01-15

T-01-15's shard budget is ≤500 LOC load-bearing + ≤5 invariants + ≤3 call-graph hops. Frozen-dataclass conversion crosses 7 dataclasses + the EnvelopeCompiler.compile() flow (which mutates dimension fields via `dim.imported_constraints.append(...)`, `dim.authored_constraints.extend(...)`, etc.). Frozen would require:

1. `object.__setattr__` shims in every `__post_init__` for in-place defaulting.
2. Compiler refactor to construct new dimension instances instead of mutating existing ones (10+ mutation sites in `compiler.py`).
3. `imported_constraints` / `authored_constraints` lists held inside frozen dataclasses need either `tuple` conversion (canonical) or a sealed-builder pattern.
4. Test fixtures that construct EnvelopeConfig step-by-step need the same builder pattern.

That's a separate shard's worth of invariants — exceeds T-01-15's budget per `rules/autonomous-execution.md` Per-Session Capacity Budget.

## Action

**Capacity check**: ~200 LOC type changes + ~150 LOC compiler refactor + ~50 LOC test fixture updates + ~20 LOC builder pattern; 4 invariants (post-init validation; in-place mutation→re-construction; tuple-vs-list payload field types; content_hash byte-identity preservation). Within budget.

**Steps**:

1. Convert `FinancialDimension`, `OperationalDimension`, `TemporalDimension`, `DataAccessDimension`, `CommunicationDimension`, `EnvelopeMetadata`, `SemanticChecks` to `@dataclass(slots=True, frozen=True)`. Use `object.__setattr__` in `__post_init__` for any in-place defaulting.
2. Convert `imported_constraints` / `authored_constraints` to `tuple[ImportedConstraint, ...]` / `tuple[AuthoredConstraint, ...]` since lists are mutable and would defeat the frozen semantics.
3. Refactor `EnvelopeCompiler._fold_templates` to construct new dimension instances rather than mutating existing ones. Same pattern for `_apply_authored` / `_apply_intersect_inputs` / `_compose_metadata`.
4. Update `EnvelopeConfigInput` — likely also needs frozen treatment OR explicit "input is the mutable builder, output is frozen" docstring per `rules/specs-authority.md` MUST Rule 6.
5. Update `EnvelopeConfig.content_hash` invariant test to verify nested-dimension immutability (mutation attempt raises `FrozenInstanceError`).
6. Tier 1 regression test: `test_compiled_dimension_mutation_raises_frozen_error.py`.

**Tests added**:

- `tests/regression/test_l03_frozen_dimension_invariants.py` — 5 cases (one per dimension) asserting `with pytest.raises(FrozenInstanceError): config.financial.per_call_ceiling_microdollars = 999` (etc).
- Updated `tests/tier1/test_envelope_compiler_pipeline.py` for the new constructor pattern.

**Blocks on**: nothing (independent of T-01-13/14/15/17).

**Blocks**: nothing critical, but lands ahead of T-02-31 (PostureGate consumes EnvelopeConfig — must not be able to widen its own envelope at runtime).

**Estimate**: 0.5 session.

## Verification (when shipped)

- `pytest tests/regression/test_l03_frozen_dimension_invariants.py` — 5/5 green.
- Full Tier 1 + regression suite green.
- `EnvelopeConfig` round-trip: compile → mutation attempt on any nested dimension → `FrozenInstanceError`.
- `content_hash` byte-identity unchanged (compile of equivalent input produces equivalent canonical bytes).

## Cross-references

- Rule: `rules/trust-plane-security.md` MUST NOT Rule 4 (frozen constraint dataclasses).
- Spec: `specs/envelope-model.md` § content_hash byte-identity invariant.
- Origin: PR #3 gate-level security review L-03 (2026-05-06).
