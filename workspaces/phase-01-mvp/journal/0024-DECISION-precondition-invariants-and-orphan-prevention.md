---
type: DECISION
date: 2026-05-24
created_at: 2026-05-24T18:30:00Z
author: co-authored
session_id: phase-01-rt2-shard3-precondition-invariants
session_turn: 1
project: phase-01-mvp
topic: R2-F1 closure — promote F-2 mutation invariants to preconditions; R2-F2 + R2-F3 disposition
phase: redteam
tags:
  [
    posture-gate,
    redteam,
    round-2,
    r2-f1,
    r2-f2,
    r2-f3,
    orphan-prevention,
    fail-closed,
    precondition-invariants,
    rule-4-fix-immediately,
    spec-accuracy,
  ]
---

# DECISION: F-2 mutation invariants run as preconditions; the paired-emission contract is application-level atomic

Closes Round 2 /redteam Finding R2-F1 (HIGH), R2-F2 (MED), and R2-F3 (LOW) in one shard. R2-F1 is a same-bug-class regression of Round 1 F-3, caught at the gate-level security review after PR #25 (Shard 1) landed. Per `rules/autonomous-execution.md` MUST Rule 4 (fix-immediately when a gate-level review surfaces a same-class gap within the shard budget), the fix shipped in this shard rather than as a follow-up issue.

## What we picked

### R2-F1 (HIGH) — Orphan posture_change on F-2 invariant violation

**Before:** Step 5 ran in the order: Step 5a (`posture_change` append) → compute mutation → F-2 invariant checks (raise on violation) → Step 5b (`envelope_edit` append). On any F-2 invariant violation the `posture_change` entry committed to the Ledger while the paired `envelope_edit` never appended. Result: an orphan `posture_change` entry violating `specs/posture-ladder.md` § Ratchet-up requirement #3 ("any posture change is an `envelope_edit`") and `rules/zero-tolerance.md` Rule 3 (no silent fallbacks at the contract level).

**After:** Step 5 now runs in the order: compute mutation + F-2 invariant checks (raise on violation) → Step 5a (`posture_change` append) → Step 5b (`envelope_edit` append). On any F-2 invariant violation ZERO Ledger entries land — the application-level paired-emission contract is atomic and fail-closed.

The four Tier 1 tests in `tests/tier1/test_posture_gate_5_step_fail_closed.py::TestStep5bMutationInvariantChecks` previously asserted `types == ["posture_change"]` post-raise, which STRUCTURALLY PINNED the orphan as if it were correct behavior. They are flipped to assert `types == []` with descriptive failure messages so a future refactor that re-introduces the orphan fires the test with a clear delta.

### R2-F2 (MED) — `_is_posture_carrying_envelope` side-effect surface

The Protocol docstring for `_PostureCarryingEnvelope` is extended with an explicit "IMPLEMENTORS" contract paragraph stating that attribute reads MUST be side-effect-free (no I/O, no lock acquisition, no log emission, no observable-state mutation, no background-task wakeups). Python's structural Protocol contract gives no runtime hook to enforce side-effect-freeness on implementors; the discipline is documented at the contract surface.

A new Tier 1 test class `TestPostureCarryingEnvelopeProtocolDiscipline` (one method, `test_protocol_attribute_read_surface_bounded`) bounds the GATE-side attribute-read surface. A spy adapter recording every `__getattribute__` call confirms `_is_posture_carrying_envelope()` reads exactly the 5 Protocol-declared attributes — no more, no fewer, no duplicates. A future refactor that adds defensive duplicate reads or extends the Protocol surface fires the assertion with a clear delta.

### R2-F3 (LOW) — Cross-spec drift on Shared Household composition

Both `specs/posture-ladder.md:128` and `specs/shared-household.md:102` compute `min(p.posture_level for p in principals)` as if `p.posture_level` were the effective posture. Per `specs/envelope-model.md § metadata.posture_level` (the authoritative source — already shipped per `journal/0022-DECISION-posture-level-mint-state-interpretation.md`), the envelope's `metadata.posture_level` field is the mint-time annotation; the principal's CURRENT effective posture is derived from that principal's Ledger `posture_change` chain.

The cited lines are clarified with present-tense comments naming `p.posture_level` as the PRINCIPAL'S current effective posture (Ledger-derived) and citing `envelope-model.md § metadata.posture_level` as the canonical source distinguishing it from the envelope's mint-time field.

## Why this disposition

### R2-F1 fix-immediately under Rule 4

Per `rules/autonomous-execution.md` MUST Rule 4, when a gate-level review surfaces a latent gap in the SAME BUG CLASS as the in-flight PR AND the gap fits within one remaining shard budget, the session MUST spawn the fix immediately rather than filing a follow-up issue. R2-F1 is a same-class regression of Round 1 F-3 (orphan posture_change on a defensive Step-5b raise). Shard 1 closed F-3 by removing the defensive guard; the F-2 mutation invariants — added in the same commit — reintroduced the same orphan pattern at a new site. The fix (~85 LOC restructure + 4 test flips + 1 new test) fits comfortably within the ≤500 LOC load-bearing / ≤10 invariants / ≤4 call-graph hops shard budget.

Filing R2-F1 as a follow-up issue was the originally drafted disposition. Per Rule 4 BLOCKED rationalizations ("That's the next session's work", "A separate PR is cleaner for review", "The follow-up issue captures it"), that disposition is BLOCKED when the fix is same-class and shard-fit.

### R2-F1 distinct from F-001 (issue #24)

R2-F1 addresses APPLICATION-level invariant violations — the mutation result shape failing one of the three F-2 checks (envelope_id mismatch / new_version drift / malformed diff_hash). The fix moves these checks to PRECONDITIONS so violations preempt the paired emission entirely.

F-001 (issue #24) addresses TRANSIENT Ledger failures BETWEEN Step 5a and Step 5b — the second `_ledger.append()` call raising mid-pair (e.g. backing store outage). That's a different bug class requiring Ledger-level transactional support (atomic batch append). The fix shipped here does NOT close F-001; F-001 remains open for the Phase 03 Ledger transactional primitive.

### R2-F2 contract-on-implementor with gate-side bound

Python's structural Protocol contract gives no runtime hook to enforce side-effect-freeness on attribute reads. The gate's `_is_posture_carrying_envelope()` invokes `hasattr()` / `getattr()` on every kwarg passed to `request_transition()` (including ratchet-down paths where the envelope is supplied informationally but never mutated). An implementation whose attribute reads perform I/O / log / mutate / acquire locks would fire those side effects on every conformance check.

The contract is on the implementor; the docstring is the contract surface. The gate-side bound (spy adapter test) is the structural defense: a future refactor that adds defensive duplicate reads or extends the Protocol surface fires the test with a named delta, preventing silent expansion of the attribute-read surface that all implementors are exposed to.

### R2-F3 — present-tense clarification, not future-tense planning

The originally drafted R2-F3 disposition used "Pre-Phase-03 implementations using `min(...)` describe a future composition rule that will be refactored against the Ledger-derived authority when Shared Household composition lands" framing. Per `rules/spec-accuracy.md`:

- Rule 2 (no split-state framings) — "Pre-Phase-03 / Phase-03" is the textbook violation
- Rule 4 (work trackers live outside specs) — "will be refactored ... when X lands" is a work tracker
- Rule 5 (specs describe shipped behavior only) — future-tense framing converts truth surface into roadmap surface
- Rule 6 (historical change logs permitted in past tense only) — future-tense is BLOCKED

The compliant alternative is present-tense: name the semantic layer (principal's current effective posture vs envelope's mint-time annotation) and cite the canonical source (`envelope-model.md § metadata.posture_level`). The cross-spec consistency is maintained by `rules/specs-authority.md` Rule 9 (reference canonical artifacts, not restate) — pointing at the authoritative spec rather than duplicating the mint-state semantics.

## Alternatives considered

### R2-F1: wrap Steps 5a + 5b in a Ledger transaction

Round 1 audit suggested this as the F-3 alternative ("either remove the guard OR wrap Steps 5a + 5b in a single transactional boundary"). Picked the precondition restructure over the transactional wrapper because:

- The transactional wrapper requires Ledger-level support that does not exist in Phase 01.
- The precondition restructure closes the APPLICATION-level orphan class without changing the Ledger contract.
- F-001 (issue #24) tracks the transactional wrapper as a separate workstream — picking it here would conflate two bug classes and exceed the shard budget.

### R2-F2: enforce side-effect-freeness via Protocol metaclass

Could in principle wire a `__init_subclass__` hook that intercepts attribute access and refuses descriptors with side effects. Rejected because:

- Structural Protocols do not support metaclass enforcement (PEP 544 leaves runtime conformance to the consumer).
- The runtime cost of intercepting every attribute access on every envelope kwarg would dwarf the actual side-effect risk.
- The gate-side bound (spy adapter test) catches the gate-side amplification, which is the actual risk surface — implementors with non-trivial descriptor logic are responsible for their own discipline.

### R2-F3: rewrite the composition functions to dispatch on Ledger walk

The narrow fix (present-tense comment) was chosen over a rewrite because:

- The composition functions (`effective_posture_for_composition`, `compose_cross_principal_action`) are themselves unshipped — they live in spec form only. Rewriting them now violates `rules/spec-accuracy.md` Rule 5 (specs describe shipped behavior; design work belongs in `briefs/` or `02-plans/`).
- The actual drift surface is internal to the spec content — two lines whose semantic layer is ambiguous given the envelope-model.md mint-state contract. A present-tense comment closes the ambiguity without changing the function's contract.
- When Shared Household composition lands as code, the spec edits in that PR will replace these comments with the shipped semantics.

## Consequences

- Every future Tier 1 / Tier 2 test that exercises the F-2 invariant path observes the atomic fail-closed contract: invariant violation → zero Ledger entries, typed error raised.
- Implementors of `_PostureCarryingEnvelope` (current: `_EnvelopeConfigPostureCarrier` in `tests/tier2/test_posture_gate_wiring.py`, future: production adapters wrapping real envelopes) are bound by the docstring contract to keep attribute reads side-effect-free.
- The 5-attribute bound on `_is_posture_carrying_envelope()` is now a structural invariant — a future refactor that extends the Protocol or adds defensive reads requires updating both the helper AND the spy test in the same commit.
- The cross-spec cross-reference pattern (clarifying semantic layer + citing canonical source) is the template for closing internal-to-spec inconsistencies without violating `rules/spec-accuracy.md` Rule 2.

## Follow-up

- F-001 (issue #24) remains OPEN — transactional pairing of Step 5a + Step 5b for Ledger-level resilience. Scope: Phase 03 Ledger transactional primitive.
- When Shared Household composition lands as code (Phase 03+), the spec comments added in this shard should be replaced with the shipped semantics per the standard `rules/spec-accuracy.md` Rule 5 workflow (code first, spec describes what landed).

## For Discussion

1. **Counterfactual:** had Round 2 audit landed AFTER Phase 03's Ledger transactional primitive shipped, would R2-F1 still have required the precondition restructure, OR would the transactional wrapper have closed both the application-level orphan class AND the transient-failure class in one commit? Specifically: is the precondition restructure load-bearing in a transactional world, or is it redundant defense-in-depth that adds friction (one extra failure path) for callers?

2. **Data-anchored:** the four flipped `TestStep5bMutationInvariantChecks` test methods previously pinned `types == ["posture_change"]` post-raise. How many other test files in the repo currently pin BROKEN behavior via post-raise Ledger assertions? A grep for `assert types ==` across `tests/tier1/` + `tests/tier2/` would surface the same pattern at sibling sites.

3. **Counterfactual:** if a future implementor of `_PostureCarryingEnvelope` violates the side-effect-free contract (e.g. acquires an asyncio lock on `prior_version` read for cache coherence), the docstring catches it at code review BUT the gate ships the side effects in production. Should the `_is_posture_carrying_envelope()` helper be extended to wrap attribute reads in a check that detects async-context state mutation — OR is the docstring + spy bound + Tier 2 wiring test the right defense-in-depth, and runtime enforcement would be overengineering?

## Cross-references

- **R2-F1 same-class predecessor:** `workspaces/phase-01-mvp/04-validate/round-1-security-audit-2026-05-24.md` § F-3 (defensive Step-5b re-raise).
- **R2-F1 closes the F-3 gap class:** PR #25 (Shard 1) removed the F-3 defensive guard; this PR closes the new F-2-invariant-raise variant that reintroduced the orphan pattern.
- **F-001 / issue #24:** TRANSIENT Ledger failure between Step 5a and Step 5b — distinct bug class, still open.
- **journal/0022:** mint-state interpretation that R2-F3 references.
- **journal/0021:** envelope_edit pairing design (`_PostureCarryingEnvelope` Protocol).
- **`rules/autonomous-execution.md` MUST Rule 4:** the fix-immediately authority for R2-F1.
- **`rules/spec-accuracy.md` Rules 2/4/5/6:** the structural rationale for the present-tense R2-F3 disposition.
- **`rules/zero-tolerance.md` Rule 3:** the no-silent-fallback principle R2-F1 closure pins.
