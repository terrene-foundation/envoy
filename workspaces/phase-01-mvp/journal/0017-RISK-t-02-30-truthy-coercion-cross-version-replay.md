---
type: RISK
date: 2026-05-07
created_at: 2026-05-10T00:00:00Z
author: agent
session_id: phase-01-wave-2-implement
session_turn: 2
project: phase-01-mvp
topic: T-02-30 truthy-coercion + getattr-default vectors fixed in gate review
phase: implement
tags:
  [
    authorship-score,
    t-023,
    type-confusion,
    cross-version-replay,
    security-review,
    autonomous-execution-rule-4,
    wave-2,
  ]
---

# RISK: T-02-30 had two T-023 type-confusion vectors caught in gate review (commit `9ecbcb20`)

The shipped T-02-30 implementation (commit `cd75810b`) passed self-verification and the implementer's gate review. The security-reviewer's parallel pass surfaced two latent vectors that would have shipped to `main` had the gate been a single-agent review.

Both findings consolidate as one bug class — **type-confusion at the authored-flag boundary** — and were fixed in the same shard per `rules/autonomous-execution.md` Rule 4 (same-bug-class within shard budget).

## Vector 1: truthy coercion on `c.authored`

The original code:

```python
if c.authored and ...:
    authored_count += 1
```

Python's truthy coercion accepts ANY non-empty/non-zero value as `True`:

| Wire payload value     | Python truthiness       | Counted as authored? |
| ---------------------- | ----------------------- | -------------------- |
| `authored=True`        | True                    | ✅ correct           |
| `authored=False`       | False                   | ✅ correct           |
| `authored="yes"`       | True (non-empty string) | ❌ counted           |
| `authored="false"`     | True (non-empty string) | ❌ counted           |
| `authored=1`           | True                    | ❌ counted           |
| `authored=[1]`         | True (non-empty list)   | ❌ counted           |
| `authored={"v":False}` | True (non-empty dict)   | ❌ counted           |

A malicious upstream node passing `{"authored": "false"}` (truthy non-empty string!) would inflate the authorship score by 1 per constraint without surfacing any error.

**Fix:** strict-identity check `if c.authored is True:`. Rejects every non-`True` value, including the truthy strings/ints/lists/dicts above.

## Vector 2: `getattr(_, _, True)` silent inflation on cross-version replay

The original code (forward-compat scaffold for Phase-04 flags that don't yet exist on Phase-01 `AuthoredConstraint`):

```python
novelty_passed = getattr(c, "novelty_check_passed", True)
min_impact_passed = getattr(c, "minimum_impact_check_passed", True)
if c.authored and novelty_passed and min_impact_passed:
    authored_count += 1
```

The default `True` makes this forward-compat. But it ALSO silently inflates the count when a Phase-04 envelope (with the flags set explicitly to `False`) is replayed against a downgraded Phase-01 verifier:

- Phase-04 envelope: `AuthoredConstraint(authored=True, novelty_check_passed=False, minimum_impact_check_passed=False)`.
- Phase-01 verifier reads the envelope. The `getattr` calls return... the actual values from the dataclass (since the fields exist on the wire-form payload).
- BUT if the wire-form payload was stripped of those fields by an attacker MITM-ing the cross-version replay, `getattr` returns `True` (the default), and the count silently inflates.

This is the textbook **T-023 cross-version replay** vector: the verifier accepts an attacker-stripped envelope and treats stripped-fields as default-pass.

**Fix:** removed both `getattr` calls. T-02-30 ships count-only on `c.authored is True` alone. The Phase-04 flags will be added via **explicit dispatch** (not `getattr` defaults) when the schema lands — documented in `specs/authorship-score.md` § Out of scope (Phase 01).

## How gate review caught what self-review missed

Per `rules/agents.md` § Quality Gates, `/implement` MUST run reviewer + security-reviewer in parallel as background agents. The implementer's self-verification claimed "all branches covered, count is correct on canonical inputs." That was true for the canonical-input case. The gate-review agents independently re-derived the function's contract against the threat model (rules/security.md § Input Validation, T-023 cross-version replay) and found the truthy-coercion gap (security-reviewer H-02) AND the getattr-default gap (security-reviewer H-01 + reviewer M-2).

This is the structural defense `rules/agents.md` MUST gate is designed to enforce: the implementer's self-review cannot resist its own framing; the parallel security pass produces an independent reading.

## Tests added (regression locks per `rules/testing.md` § Regression Testing)

Test count: 19 → 20.

- `test_recompute_strict_identity_rejects_truthy_string` — asserts `authored="yes"`, `authored=1`, `authored=[1]`, `authored="false"` (truthy!) all FAIL the gate; only literal `True` counts.
- `test_recompute_phase04_flags_not_consumed_by_phase01` (renamed + rewritten) — locks the Phase-01 contract: even if a future Phase-04 envelope is presented today (with novelty/min-impact flags set False), the count-only gate counts every `authored is True` constraint. Phase 04 will extend via explicit dispatch.

## Risk that surfaces this entry

The latent risk this RISK entry pins: **forward-compat `getattr` defaults are a silent T-023 inflation surface**. The pattern is seductive — it lets future schemas extend without callsite migration — but the default-True choice is exactly the failure mode an attacker exploits via field-stripping. Any Phase-04 contributor adding a similar forward-compat scaffold MUST default fail-closed (default-False or explicit raise on absent), not default-pass.

## For Discussion

1. The truthy-coercion fix landed in the SAME PR as the implementation (per Rule 4). But the gate-review-finding-driven fix-immediately discipline is only invoked WHEN the gate review fires. If `/implement` had skipped the security-reviewer gate (e.g., "the changes are straightforward, no review needed" — a BLOCKED rationalization per `rules/agents.md`), this would have shipped to main and surfaced only at /redteam Round 1. Should `rules/agents.md` MUST gate be promoted from RECOMMENDED to MUST at every primitive-shard boundary in Phase 01 specifically, given that Phase-01's verifier is the load-bearing surface for cross-version replay defense?

2. The `getattr(_, _, True)` forward-compat default-True was ALSO captured in `rules/zero-tolerance.md` Rule 6 iterative-TODO exception. The exception authorizes "accept-but-unused" parameters when the consumer is in-flight. But the default-True policy is NOT spelled out in that exception. Should Rule 6 be tightened with a sub-clause: "forward-compat parameter defaults MUST default fail-closed (not default-pass) when the parameter gates a security-relevant decision"? (Counterfactual: had Rule 6 mandated default-False for security-relevant defaults, the original `getattr(c, "novelty_check_passed", True)` would have been default-False, and the strip-attack would have surfaced as a missing-field error rather than a silent inflation.)

3. The strict-identity check `if c.authored is True` is the right defense for the Python type system. But the wire-form payload ARRIVES as JSON; `from_dict` is the entry boundary. The fix to `from_dict` (M-02 strict isinstance + non-negative validation on every field) is the parallel defense at the wire boundary. Should `rules/security.md` § Input Validation be augmented with a "boundary symmetry" sub-rule: "every type-confusion-relevant strict check at the use-site MUST have a parallel strict check at the wire boundary"? Without symmetry, an attacker can either strip the field or pass it as a truthy non-bool — both vectors require defenses at both layers.
