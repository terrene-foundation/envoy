# Round 1 Mechanical Sweep — Doc 02 Envelope Model

**Date:** 2026-04-21
**Scope:** Mechanical sweeps — constraint-dimension canonical-name compliance, doc-09 mitigation-to-spec-section parity, cross-doc consistency, error-taxonomy enumeration.
**Input:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md` + doc 00 v3 FROZEN + doc 09 v3 FROZEN.

## Summary

| ID   | Severity | One-liner                                                                                                                                                                                                                                     |
| ---- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M-01 | MEDIUM   | Composition-rule DSL §5.3 lacks operational-dimension coverage example — attacker scenarios in doc 09 T-013 (subtle compositional attacks) need more concrete DSL coverage                                                                    |
| M-02 | MEDIUM   | §8.2 Minimum-impact check corpus is under-specified; "last-30-day Ledger history" raises cold-start problem (first-month user has no history)                                                                                                 |
| M-03 | MEDIUM   | `SessionObservedState` referenced in §5.3 but only defined in doc 04 forward-reference — no schema stub in doc 02                                                                                                                             |
| M-04 | MEDIUM   | §5.1 per-dimension intersection rules for Communication: `content_rules` UNION. But if two envelopes have conflicting content_rules (one says "block attachments", one says "allow attachments"), the UNION is ambiguous. Need tie-break spec |
| M-05 | MEDIUM   | Sub-agent subset-proof format from T-105 R2-H2 is not fully specified in doc 02 §5.1; it is referenced but needs own subsection with the 5-dimension witness structure                                                                        |
| M-06 | LOW      | §2.2 canonical JSON says "field-ordered for deterministic serialization" but doesn't define the full ordering algorithm; risk of drift across SDK implementations                                                                             |
| M-07 | LOW      | §11 error taxonomy lists 11 error types; doc 09 T-104 `capability_dead` is mentioned but is a field flag, not an error — confirm if `CapabilityDeadError` is raised on attempt to execute or on retrieval                                     |
| M-08 | LOW      | §6.2 Algorithm-identifier migration: `Trust Vault encryption — re-encrypt on migration event under new algorithm` — re-encryption of what key? Explicit naming needed (Master vault key? Per-entry?)                                          |

## Verifications (passed)

### ✅ Canonical name compliance

5 constraint dimensions named correctly per `rules/terrene-naming.md`:

- §2.2 JSON schema uses `financial`, `operational`, `temporal`, `data_access`, `communication` — exact names.
- §3 subsections use Financial / Operational / Temporal / Data Access / Communication — proper case, exact names.
- No synonyms ("spend" / "cost" / "budget" used contextually but never as dimension names).

### ✅ Doc-09 mitigation coverage

Every `specs/envelope-model.md` reference in doc 09 v3 has a corresponding doc 02 section:

- T-005 classifier ensemble → §3.4.1 ✅
- T-010 first-time-action gate → §7 hot-path + §11 error taxonomy (needs explicit first-time-action check mention — M-09 LOW)
- T-011 cross-domain-flow gating → §3.5 Communication content_rules + §5.3 composition_rules ✅
- T-013 composition-aware envelope → §5.3 ✅
- T-014 per-turn prompt reset → not in doc 02 (lives in `runtime-abstraction.md` per doc 09 T-014 mitigation). No doc 02 gap.
- T-015 system-prompt pinning + prompt-size budget → not in doc 02 (runtime-abstraction + envelope-re-read-checkpoint). No doc 02 gap.
- T-021 linter → §9.2 linter warnings ✅ (gmail.com etc)
- T-023 authorship score → §8 ✅ (with novelty + minimum-impact)
- T-024 enterprise mode → §8.3 posture-ratchet gate ✅
- T-041 high-stakes time-delay — not a primary doc 02 feature; lives in doc 03 / runtime. No doc 02 gap.
- T-090 operational-dimension / sandbox limits → §3.2 sub_agent_spawn_limit + §9.2 (max_depth warning) ✅
- T-093 financial-velocity + velocity-raise ratchet → §3.1 velocity fields + §8.3 Velocity-raise ratchet defense ✅
- T-094 variant of T-015 — no doc 02 gap.
- T-104 envelope-version binding → §6.1 full coverage + mid-flight tightening cascade ✅
- T-105 sub-agent subset-proof → §5.1 intersection + §11 SubsetProofFailedError + M-05 finding for full spec

**9 HIGH, 3 LOW:** one HIGH implicit gap (M-09: first-time-action gate not explicitly specced in §7 hot-path).

### ✅ Error taxonomy

11 error types in §11, each maps to specific trigger + user action. 1 LOW (M-07: `capability_dead` field vs `CapabilityDeadError` raising).

### ✅ BET-2 structural/semantic partition honored

§7 partitions 5 check classes with explicit latency budgets (<1ms, <5ms, <50ms, <500ms). Aligned with doc 00 v3 BET-2.

### ✅ Algorithm-identifier Phase 01 exit gate

§6.2 final paragraph: _"Phase 01 exit gate: algorithm-identifier schema MUST be implemented and signed artifacts MUST carry the tag."_ Consistent with doc 00 v3 §4.1 item 9. Consistent with doc 09 v3 §7 Phase 01 gate (moved from v2 Phase 02 per M-10).

### ✅ Cross-SDK primitive references (§12)

- `RoleEnvelope` / `TaskEnvelope` / `intersect_envelopes` cited with kailash-py + kailash-rs locations + GH issue refs.
- Algorithm-identifier tied to kailash-py#604 + kailash-rs#519 + mint#6.

## Additional findings

### M-09 (HIGH) — First-time-action gate not explicitly in §7 hot-path

T-010 direct prompt injection mitigation promises "first-time-action gate" but §7 hot-path shape doesn't mention novelty check for tool-calls. The hot-path lists structural → arithmetic → semantic checks; "novel tool-call pattern" isn't one of them. Either (a) add as a fourth class of check (novelty-aware friction, covered by `specs/grant-moment.md` per T-010 mitigation), or (b) explicitly note that first-time-action gating is a Grant-Moment-layer defense, not an envelope-check defense.

## Resolution summary

- **1 HIGH** (M-09 first-time-action gate cross-ref).
- **5 MEDIUM** (M-01 DSL coverage, M-02 corpus cold-start, M-03 SessionObservedState stub, M-04 content_rules tie-break, M-05 subset-proof full spec).
- **3 LOW** (M-06 ordering algorithm, M-07 capability_dead, M-08 re-encrypt what).

All fixable inline. No CRITICAL findings in mechanical sweep.
