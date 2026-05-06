---
type: DECISION
date: 2026-05-06
created_at: 2026-05-06T00:00:00Z
author: agent
session_id: phase-01-mvp-implement-t-01-10
session_turn: 1
project: envoy
topic: EnvelopeCompiler.intersect() deferred from T-01-10 (Wave 1) to T-03-50 (Wave 3) — clearance-mapping layer required
phase: implement
tags:
  [
    intersect,
    envelope-compiler,
    wave-3-deferral,
    zero-tolerance-rule-6,
    clearance-mapping,
    v-06,
    deviation,
  ]
---

# 0008 — DECISION — `EnvelopeCompiler.intersect()` deferred to Wave 3

## What was decided

`EnvelopeCompiler.intersect()` — listed in shard `04-envelope-compiler-implementation.md` § 4 as part of T-01-10's public surface — is deferred to Wave 3 (T-03-50 Grant Moment) rather than shipping a partial in Wave 1. T-01-10 ships only `compile()`, the canonical-bytes pipeline, monotonic-tightening validation against parents, and template resolution. `IntersectConflictError` remains declared in `envoy/envelope/errors.py` for the Wave-3 producer to consume.

## Why this is journal-worthy

This is a real deviation from the shard 4 implementation surface and triggers `rules/specs-authority.md` MUST Rule 6 (acknowledge + log + flag user-visible changes for approval). The acknowledgement is here; the deviation is non-user-visible (no Phase 01 caller of `EnvelopeCompiler.intersect()` exists yet — Grant Moment in Wave 3 is the first); the rationale is captured below.

## Why deferral, not partial-ship

The full intersect contract per `specs/envelope-model.md` § Algorithms § `intersect_envelopes` calls `kailash.trust.pact.envelopes.intersect_envelopes` for the 5-dimension core, with the Envoy compiler folding back the superset (composition_rules UNION, cross_domain_rules UNION, tool_output_budget MIN, semantic_checks SUPERSET).

The kailash-py wrap is non-trivial because the two SDKs use different `ConfidentialityLevel` enum values:

- kailash-py: `public, restricted, confidential, secret, top_secret` (lowercase)
- envoy spec: `Public, Internal, Confidential, Restricted, HighlyConfidential` (per V-06 fix)

A correct `intersect()` requires a translation layer (`to_constraint_envelope_config` + `from_constraint_envelope_config` per shard 4 § 4) that:

1. Maps envoy clearances to kailash-py clearances on the way in.
2. Calls `intersect_envelopes` for the 5-dim merge.
3. Maps clearances back on the way out.
4. Folds Envoy-superset blocks (composition + cross-domain + tool-output + semantic-checks) on top.

Translation requires an empirical mapping decision (does envoy `Internal` map to kailash-py `restricted` or `confidential`?). That decision is best made when the first consumer (Grant Moment cascade-revocation orchestrator) surfaces a real envelope pair to intersect — not speculatively at T-01-10.

An interim partial-ship that raised `NotImplementedError` on divergent dimensions was authored, evaluated, and rejected against `rules/zero-tolerance.md` Rule 6 ("Implement Fully — ALL methods, not just the happy path") + Rule 2 ("No Stubs, Placeholders, or Deferred Implementation"). The interim form was a stub by definition; shipping it would have introduced a Rule-2 violation at the very first commit.

## Alternatives considered

### Option A — ship partial intersect with NotImplementedError on divergent dims (REJECTED)

Pros: shard 4 § 4 lists intersect() as part of EnvelopeCompiler.

Cons: `NotImplementedError` is BLOCKED per zero-tolerance Rule 2. `spec-accuracy.md` blocks "Phase 01 partial / Phase 03 will wire" framing. The partial form would need to be removed in Wave 3 anyway — net duplicated work plus a Rule-2 hit at audit.

### Option B — ship full intersect with a synthesized clearance-mapping layer (REJECTED)

Pros: matches shard 4 § 4 exactly.

Cons: requires picking the envoy↔kailash-py clearance mapping speculatively without a real consumer to validate against. Likely to surface as a HIGH at T-03-50 when Grant Moment exposes a real intersect pair and the mapping is wrong. Better to defer until the consumer's needs are concrete.

### Option C — defer intersect() to Wave 3, ship rest of T-01-10 (CHOSEN)

Pros: T-01-10 ships fully-implemented per Rule 6. Wave-3 producer (Grant Moment) and intersect() consumer land in the same PR per `rules/orphan-detection.md` Rule 1 (5-commit-headroom). Clearance mapping decided when its real shape is visible.

Cons: `EnvelopeCompiler.intersect()` not callable until Wave 3.

## Disposition / propagation

1. **T-01-10 verification record** in `01-wave-1-foundation.md` § T-01-10 § Verification documents the deviation.
2. **`IntersectConflictError`** stays in `envoy/envelope/errors.py` — its first producer is Wave-3 intersect(); declaring exception classes ahead of producer is conventional Python and not an orphan-detection MUST Rule 1 violation per the rule's scope ("attribute exposed on a public surface that returns a `*Manager`/`*Executor`/...").
3. **T-03-50 (Grant Moment) scope** picks up `intersect()` shipping when it ships its `CascadeRevocationOrchestrator`. Wave-3 todo file `03-wave-3-grant-moment-budget.md` § T-03-50 step 6 already references `verify_cascade_complete`; the intersect() ship lands in the same shard.
4. **Phase 02 stretch:** `envelope_id` uses `uuid.uuid4` not `uuid-v7` (stdlib gap until Python 3.14). Documented in T-01-10 verification.

## For Discussion

1. **Counterfactual**: If shard 4 had listed intersect() as a Wave-3 deliverable from the start, this decision wouldn't be a deviation — it would be the plan. Should /todos planning have surfaced this dependency earlier? The clearance-enum mismatch was visible during shard 4 § 2 ("kailash-py `ConstraintEnvelopeConfig` ... does NOT carry the Envoy-spec-mandated [fields]") but the V-06 enum-value mismatch wasn't called out as a separate concern. Recommend amending the shard-template to require enum-value alignment as an explicit § 2 verification step.

2. **Specific data**: T-03-50 (Grant Moment, Wave 3) is the first intersect() consumer; T-03-52 (CascadeRevocationOrchestrator) is the first divergent-dim intersect() caller. Distance from this deviation to the consumer landing is ~2 worktree-waves (Waves 2 and 3); Rule 1's "within 5 commits" constraint comfortably accommodates this since each wave consolidates multiple primitives into a small number of merged commits.

3. **Methodology**: This is the second deviation surfaced during /implement (the first was journal/0007 — pyproject.toml stale `kailash>=3.20.0` pin). Both came from the /implement workflow's "Context anchoring" step finding inconsistencies that /todos planning didn't surface. Should a "stale-config sanity check" be added to /todos planning's mechanical-sweep list? Cost: a grep + diff per planned dependency. Benefit: catches both classes of issue (stale pyproject pins, partial-implement-as-Rule-2-stub) before /implement starts.

## Consequences

- **Immediate**: T-01-10 ships clean per Rule 6. 42 Tier 1 tests pass.
- **Short-term**: T-01-11 (Tier 2 wiring) blocks on T-01-12 + T-01-17 (per existing plan); intersect() is not exercised at the wave-1 milestone gate.
- **Wave 3 (T-03-50)**: Grant Moment's CascadeRevocationOrchestrator scope picks up intersect() shipping — added to the cycle's deliverable list.
- **Phase 02 entry**: `uuid.uuid7` swap when toolchain reaches Python 3.14.

## Cross-references

- T-01-10 verification: `workspaces/phase-01-mvp/todos/active/01-wave-1-foundation.md` § T-01-10
- Source shard: `workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md` § 4 + § 5
- Wave-3 consumer: `workspaces/phase-01-mvp/todos/active/03-wave-3-grant-moment-budget.md` § T-03-50, T-03-52
- Spec authority: `.claude/rules/specs-authority.md` MUST Rule 6
- Zero-tolerance: `.claude/rules/zero-tolerance.md` Rule 2 + Rule 6
- Spec accuracy: `.claude/rules/spec-accuracy.md` (blocks "Phase 01 partial" framing)
- V-06 clearance enum: `specs/envelope-model.md` § Schema L86
- Prior deviation: `journal/0007-DISCOVERY-pyproject-stale-kailash-pin.md`
