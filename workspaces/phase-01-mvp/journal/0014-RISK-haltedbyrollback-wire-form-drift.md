---
type: RISK
date: 2026-05-07
created_at: 2026-05-07T05:30:00Z
author: agent
session_id: redteam-round-2
session_turn: 1
project: phase-01-mvp
topic: HaltedByRollback wire-form drift fixed in /redteam Round 2
phase: redteam
tags:
  [ledger, halt-record, wire-form, spec-compliance, autonomous-execution-rule-4]
---

# RISK: HaltedByRollbackRecord wire-form drift caught + fixed in Round 2

Round 1 of the /implement-cycle redteam (commit `513d35d`) implemented
`_persist_halt_record` — the production path that mints a forensic
HaltedByRollback entry BEFORE re-raising LedgerRollbackDetectedError per
`specs/ledger.md` § Halted state. Round 1 verified the structural
plumbing (call site exists at `facade.py:312`; chain tail advances;
3 regression tests pass).

Round 2's parallel deep-dive (analyst) re-derived the spec assertions
INDEPENDENTLY of the Round-1 report and surfaced what Round-1's own
verification table conflated: the inner JSON content shape mandated by
spec lines 537-548 includes 8 keys (top-level `type` + 7 content keys).
Round 1's `to_dict()` emitted only 4 of the 7 content keys; 3 were
silently missing.

## What was missing

Per `specs/ledger.md` § Halted state JSON (lines 537-548):

| Spec field              | Code at Round 1 end                                                                                                  | Drift class                   |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| `schema_version`        | absent — never declared, never emitted                                                                               | wire-form drift               |
| `runtime_identity`      | absent — no field, no construction                                                                                   | wire-form drift               |
| `halted_at`             | code emitted `detected_at`                                                                                           | spec-vs-code field-name drift |
| `signature_hex` (inner) | spec line 546 had the field on inner content; spec § Entry envelope schema (lines 17-33) places it on outer envelope | spec internal contradiction   |

Each missing field is independently load-bearing for forensic recovery:

- `schema_version="halt/1.0"` lets a future verifier reject a Phase-02+
  halt record encoded under a different schema.
- `runtime_identity = {device_id, signing_key_id, algorithm_identifier}`
  binds the halt to the runtime instance that signed the outer envelope;
  without it, a verifier cannot re-derive canonical bytes for signature
  verification.
- `halted_at` (vs `detected_at`) is the spec-canonical name for the
  temporal-event field; rename closes the spec-vs-wire drift.

## How Round 2 caught what Round 1 missed

Round 1's verification (§ 5 of `round-1-implement-redteam.md`) checked
the OUTER plumbing — call-site exists, regression test exercises the
path, chain tail advances — but did NOT walk the inner `to_dict()`
emission against the spec JSON shape line-by-line. Per
`skills/spec-compliance/SKILL.md` § Step 9 ("self-report trust ban"),
Round 2's analyst treated Round 1's table as INPUT to verify, not
evidence to trust. The independent re-derivation found the gap.

This is exactly the failure mode `rules/specs-authority.md` Rule 5b is
designed to surface: when a spec edits ANY shape, full sibling-spec
re-derivation is mandatory. Round 1 modified `specs/ledger.md` § Halted
state in service of HIGH-4 fix; Round 2's wider sweep caught the
interior shape drift.

## Fix landed in same shard (per `rules/autonomous-execution.md` Rule 4)

Per Rule 4 fix-immediately when same-bug-class within shard budget
(2 HIGH + 1 same-class bonus + 1 MED + 2 same-surface MED + ~25 LOC
load-bearing + ≤4 invariants = within ≤500 LOC / ≤10 invariant threshold):

1. New `RuntimeIdentity` frozen dataclass (`envoy/ledger/head.py:76`),
   stores `algorithm_identifier` as a sorted tuple of `(key, value)`
   pairs so the canonical-dump is deterministic.
2. `HaltedByRollbackRecord` extended: `schema_version: str` field +
   `_SCHEMA_VERSION = "halt/1.0"` constant + `runtime_identity:
RuntimeIdentity` field; `__post_init__` validates both; `to_dict()`
   emits all 6 inner keys in spec order.
3. Field rename `detected_at` → `halted_at` cascaded through facade +
   regression test + tier-1 test.
4. Spec edit per `rules/specs-authority.md` Rule 6: removed inner-content
   `signature_hex` line in `specs/ledger.md` § Halted state and added
   explanatory paragraph clarifying inner-vs-outer envelope responsibility.
5. Test count 454 → 462 (+8: 5 observability + 2 schema_version /
   runtime_identity rejection + 1 wire-form regression).

## Risk that surfaces this entry

The latent risk this RISK entry pins: **a Round 1 redteam that verifies
its own findings can ship "convergence" while leaving secondary drift
in the same surface**. Round 1's verification was correct as far as it
walked, but it did not walk the spec JSON shape end-to-end. Round 2's
parallel-deep-dive structure (3 independent agents re-deriving from
specs) is the structural defense — single-agent verification is
susceptible to the same framing bias as the brief it's verifying.

## For Discussion

1. Round 1's `round-1-implement-redteam.md` § 5 verification claimed
   "PASS — production call site exists at `facade.py:312`; regression
   test exercises the path." That was true but incomplete. Should
   `commands/redteam` § Round 2 verification protocol explicitly
   mandate emitting the dataclass's `to_dict()` output and diffing it
   against the spec JSON shape? (Counterfactual: had Round 1 done that
   diff, R2-H-1 + R2-H-2 + R2-H-bonus would have all surfaced and
   landed in the Round-1 commit.)

2. The spec at `specs/ledger.md:545` says `"runtime_identity": {...}`
   — generic placeholder. The Phase-01 canonical shape we landed
   `{device_id, signing_key_id, algorithm_identifier}` is what the
   runtime knows AND what an external verifier needs. Should the spec
   be tightened to mandate this exact triple (per `rules/spec-accuracy.md`
   Rule 2 — no split-state framings; the spec describes shipped
   behavior), or should the `{...}` placeholder remain so Phase 02+
   can extend without spec edit?

3. The `algorithm_identifier` inside `runtime_identity` is sorted
   alphabetically by key (hash, shamir, sig) at canonical-dump time.
   The spec doesn't define internal ordering. Sorted-by-key is the
   canonical form for any external verifier re-deriving the canonical
   bytes — but a future spec extension that adds an ordered list field
   (e.g. `signature_chain`) would NOT sort alphabetically. Should the
   canonical-ordering policy be documented in `specs/ledger.md`
   explicitly so Phase 02+ contributors don't introduce non-canonical
   ordering by accident?
