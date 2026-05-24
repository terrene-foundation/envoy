# Round 3 Code Review — T-02-33 Shard 3 Closure Verification

- **Date:** 2026-05-24
- **Scope:** Shard 3 `e89914b..2264ae2` (PR #27 merged at `2264ae2`)
- **Cumulative diff:** `641dd2d..2264ae2` (entire T-02-33 follow-up chain)
- **Reviewer mission:** verify Round 2 findings R2-F1 (HIGH), R2-F2 (MED), R2-F3 (LOW) are closed; flag any new findings
- **Convergence verdict:** CONVERGED — all 3 Round 2 findings closed; no new findings; 609/609 tests pass

---

## Summary

- **Overall status:** Clean — Round 2 findings closed; no new findings introduced
- **Tests:** 609/609 pass; pytest --collect-only exit 0; log triage clean (no WARN+)
- **Files changed in Shard 3:** 6 files, +648/-72 LOC
- **Critical issues:** 0
- **Important improvements:** 0
- **Minor improvements:** 0

---

## Mechanical sweeps (run BEFORE LLM judgment)

### Sweep 1 — R2-F1 AST verification of step ordering

Grep on `envoy/authorship/posture_gate.py` line numbers:

| Step                                                        | Pre-Shard-3 line | Post-Shard-3 line | Order |
| ----------------------------------------------------------- | ---------------- | ----------------- | ----- |
| `mutation = envelope.mutate_for_posture_level(target)`      | 1023             | 1008              | (1)   |
| `raise PostureEnvelopeMutationInvariantError` (envelope_id) | 1033             | 1019              | (2)   |
| `raise PostureEnvelopeMutationInvariantError` (new_version) | 1041             | 1027              | (3)   |
| `raise PostureEnvelopeMutationInvariantError` (diff_hash)   | 1049             | 1035              | (4)   |
| Step 5a `_ledger.append(entry_type="posture_change", ...)`  | 979              | 1078              | (5)   |
| Step 5b `_ledger.append(entry_type="envelope_edit", ...)`   | 1065             | 1115              | (6)   |

Pre-Shard-3 ordering: 5a (979) → mutate (1023) → invariants (1033, 1041, 1049) → 5b (1065) — the R2-F1 bug (invariant violation between 5a and 5b → orphan posture_change).

Post-Shard-3 ordering: mutate (1008) → invariants (1019, 1027, 1035) → 5a (1078) → 5b (1115) — atomic fail-closed.

The "Step 5-PRECONDITIONS" block (lines 981-1053) is structurally distinct from Step 5a — `mutation` and `envelope_edit_content` are built before any `_ledger.append`. **PASS.**

### Sweep 2 — R2-F1 test flip

`grep "types == \[\]" tests/tier1/test_posture_gate_5_step_fail_closed.py`:

- 4 hits — lines 1679, 1712, 1745, 1775 (all in `TestStep5bMutationInvariantChecks`)

`grep 'types == \["posture_change"\]' tests/tier1/test_posture_gate_5_step_fail_closed.py`:

- 0 hits (the pre-Shard-3 expectation that pinned the orphan as if correct)

**PASS.** The four flipped methods now assert atomicity (`types == []`) rather than the orphan.

### Sweep 3 — R2-F1 Tier 2 case

`grep "TestF2InvariantViolationEmitsNeitherEntry" tests/tier2/test_posture_gate_wiring.py`:

- Class at line 672 with 3 methods:
  - `test_envelope_id_mismatch_emits_neither_entry`
  - `test_new_version_drift_emits_neither_entry`
  - `test_malformed_diff_hash_emits_neither_entry`

Each test injects `envoy_ledger: EnvoyLedger` (real Ledger fixture, per `rules/testing.md` Tier 2 § "Real infrastructure recommended"), constructs a forged `_PostureMutationOutcome`, and asserts `entries == []` AND `sink.writes == []`. No `MagicMock`, no `@patch`, no test-double of the Ledger. **PASS.**

### Sweep 4 — R2-F2 Protocol docstring

`grep -n "side-effect\|side effect" envoy/authorship/posture_gate.py`:

- line 677: "Implementations of this Protocol MUST have side-effect-free attribute reads"
- line 693: "The gate cannot enforce side-effect-freeness at runtime"

Located in `_PostureCarryingEnvelope` Protocol docstring (lines 675-699). Contract explicit: no I/O, no lock acquisition, no log emission, no observable state mutation, no background-task wakeups. **PASS.**

### Sweep 5 — R2-F2 spy test

`grep "TestPostureCarryingEnvelopeProtocolDiscipline"` returns line 1972. Test method `test_protocol_attribute_read_surface_bounded` uses `_SpyEnvelope` with `__getattribute__` instrumentation, then asserts:

1. `set(protocol_reads) == _EXPECTED_PROTOCOL_ATTR_READS` — exact set equality (5 attrs)
2. `unexpected_reads == []` — no non-Protocol attribute leakage
3. `len(protocol_reads) == len(_EXPECTED_PROTOCOL_ATTR_READS)` — exact count, catches duplicate reads

A future refactor adding a sixth `hasattr` or duplicating an existing `hasattr` fails the assertion with a named delta. **PASS.**

### Sweep 6 — R2-F3 present-tense audit

`grep -E "Pre-Phase|will be refactored|when X lands|future-tense|future scope|TBD|TODO" specs/posture-ladder.md specs/shared-household.md`:

- Single hit: `specs/shared-household.md:165` — `4. Shared-household duress interplay — each principal has distinct duress honeypot; cross-principal duress coupling TBD.`

Context: line 165 is inside the existing `## Open questions` section (line 160), which predates Shard 3 (NOT introduced in this diff). Per `rules/spec-accuracy.md` Exception 1 (out-of-scope sections that bound coverage) `## Open questions` is conventionally an acceptable carve-out when content names domain-level unresolved questions rather than a gap tracker. The TBD predates Shard 3's edits (not introduced here) and is out of Round 3 scope; flagging it as a finding would violate `rules/repo-scope-discipline.md` / `rules/zero-tolerance.md` 1c (pre-existing claims must cite a SHA pre-dating the session). The Shard 3 edits themselves (line 102 + 125 inserts) are present-tense semantic clarifications. **PASS.**

### Sweep 7 — `__all__` discipline

`envoy/authorship/__init__.py`:

- 13 Posture\* symbols in `__all__` (lines 55-67)
- All 13 have eager `from envoy.authorship.posture_gate import ...` imports (lines 28-42)
- No `__getattr__` lazy resolution
- Per `rules/orphan-detection.md` Rule 6 — every public module-scope import appears in `__all__`. **PASS.**

### Sweep 8 — Cross-CLI hygiene

`grep -nE "Agent\(subagent_type=|Claude Code|CLAUDE\.md|PascalCase" workspaces/phase-01-mvp/journal/0024-DECISION-precondition-invariants-and-orphan-prevention.md specs/posture-ladder.md specs/shared-household.md`:

- 0 hits across all 3 files

Per `rules/cross-cli-artifact-hygiene.md` MUST Rules 1, 3, 4 — workspace artifacts MUST use CLI-neutral delegation phrasing, conceptual baseline references, and neutral hook event names. **PASS.**

### Sweep 9 — Specs-authority Rule 5b sibling re-derivation

Spec files referencing `posture_level`:

- `specs/envelope-model.md:96` — mint-state semantics (authoritative source, predates Shard 3)
- `specs/posture-ladder.md` — edited in Shard 3 (line 125 comment)
- `specs/runtime-abstraction.md:150,221` — N2 envelope cache invalidation (5-property invalidation list)
- `specs/shared-household.md` — edited in Shard 3 (line 102 comment)

The Shard 3 clarifications in `posture-ladder.md` and `shared-household.md` cite `envelope-model.md § metadata.posture_level` as the canonical source — consistent with the authoritative spec at `envelope-model.md:96` ("mint-state audit annotation; no production read consumer dispatches on its value"). `runtime-abstraction.md:150/221` references `posture_level` as one of 5 cache-invalidation properties — orthogonal to the mint-state vs. effective-posture distinction the Shard 3 edits clarify. No sibling drift introduced. **PASS.**

### Sweep 10 — pytest --collect-only exit 0

`.venv/bin/pytest --collect-only -q tests/`:

- 609 tests collected in 0.39s, exit 0
- Includes the 3 new Tier 2 methods + 4 flipped Tier 1 methods + 1 new Tier 1 spy method

Per `rules/orphan-detection.md` Rule 5 — collect-only is a merge gate. **PASS.**

### Sweep 11 — Refactor invariants (LOC trajectory)

`envoy/authorship/posture_gate.py`: pre-Shard-3 1101 LOC → post-Shard-3 1151 LOC (file GREW by 50 LOC).

Per `rules/refactor-invariants.md` MUST Rule 1 — LOC invariant test required ONLY when a refactor REDUCES file line count. Shard 3 added the Step-5-PRECONDITIONS block AND test classes; no reduction occurred. **N/A — rule does not trigger.**

---

## LLM judgment

### Atomicity at application level

Walked the code path end-to-end:

1. Step 1 (divergence) → Step 2 (noop) → Step 3 (ratchet-up gates 3a–3e) → Step 4 (cascade-revoke on demotion) all RUN BEFORE Step 5-PRECONDITIONS. On any failure here, no mutation is computed and no `_ledger.append` fires.
2. Step 5-PRECONDITIONS (lines 981–1053): runs ONLY on `target > current` (ratchet-up). Sequence:
   - `mutation = envelope.mutate_for_posture_level(target)` — pure compute, no Ledger touch
   - Three invariant checks — each raises `PostureEnvelopeMutationInvariantError` on violation; raise preempts Step 5a entirely
   - `envelope_edit_content` built in memory (dict literal at lines 1045–1053), still no Ledger touch
3. Step 5a (lines 1055–1091): `_ledger.append(entry_type="posture_change", ...)` — the FIRST Ledger write. Reached ONLY when preconditions passed.
4. Step 5b (lines 1093–1128): `_ledger.append(entry_type="envelope_edit", ...)` — pair of Step 5a. Reached on success path only.

No branch exists where Step 5a fires BEFORE the invariant checks. No branch exists where the mutation can side-effect before invariants validate (the `mutate_for_posture_level` call is the side-effecting Protocol method, but its result is bound to a local; nothing publishes until Step 5a). The application-level paired-emission contract is atomic and fail-closed on F-2 invariant violations.

Note (correctly scoped in the journal at line 65): TRANSIENT Ledger failures BETWEEN Step 5a and Step 5b (the second `_ledger.append` raises mid-pair, e.g. backing store outage) are a distinct bug class. R2-F1 closure addresses APPLICATION-level violations only; F-001 (issue #24) tracks the transactional pairing as open Phase 03 work. The disposition is honest and correctly bounded.

### Spy-adapter test correctness

`tests/tier1/test_posture_gate_5_step_fail_closed.py:1989-2098`:

- The spy records every attribute access via `__getattribute__` override.
- Test filters `__`-prefixed dunder noise + underscore-prefixed helper names (`_record`).
- Three independent assertions on the recorded surface:
  - Set equality: `set(protocol_reads) == _EXPECTED_PROTOCOL_ATTR_READS` (5 attrs: `envelope_id`, `prior_version`, `prior_content_hash`, `prior_posture_level`, `mutate_for_posture_level`)
  - No non-Protocol leakage: `unexpected_reads == []`
  - Exact count: `len(protocol_reads) == 5`

A future helper refactor that adds a sixth `hasattr` (e.g. defensive `hasattr(obj, "envelope_version")`) fails both set-equality AND count-equality. A duplicate `hasattr` followed by `getattr` on the same name (e.g. accidental hasattr-then-getattr pair) fails count-equality. The test catches both expansion classes.

The test is structural, not probe-driven semantic — it asserts COUNT and SET MEMBERSHIP, not response shape. Per `rules/probe-driven-verification.md` MUST Rule 3 (structural probes are acceptable when LLM access is unnecessary) this is the correct shape — it answers "did the helper read these 5 attributes exactly?" via deterministic enumeration, not regex over assistant prose. **PASS.**

### Spec edit rule compliance

Compared the Shard 3 spec inserts to `rules/spec-accuracy.md` Rules 2/4/5/6:

| Rule                                               | Test                                                                                                                                                                                                                                                                                                                                                                                                                | Disposition |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| Rule 2 (no split-state framings)                   | No "Pre-Phase-03 / Phase-03" / "Promised / Current" / "Scaffold / Live" / "Now / Later"                                                                                                                                                                                                                                                                                                                             | PASS        |
| Rule 4 (work trackers outside specs)               | No "BE follow-up" / "Phase 3 will refactor" / "TBD this line"                                                                                                                                                                                                                                                                                                                                                       | PASS        |
| Rule 5 (specs describe shipped behavior)           | Comment describes the SEMANTIC layer of the data being read (Ledger-derived effective posture vs. envelope mint-state) — both halves shipped (envelope mint-state at `envelope-model.md § metadata.posture_level`; Ledger `posture_change` chain wired by T-02-31). The composition function itself is unshipped pseudocode, but the comments describe what `p.posture_level` IS (semantic layer), not future work. | PASS        |
| Rule 6 (historical change logs in past tense only) | N/A — no change log section in this edit                                                                                                                                                                                                                                                                                                                                                                            | N/A         |

The journal at `workspaces/phase-01-mvp/journal/0024-DECISION-precondition-invariants-and-orphan-prevention.md` § "R2-F3 — present-tense clarification, not future-tense planning" (lines 73–82) correctly identifies the rule-compliance trade-off: the originally-drafted Pre-Phase-03/Phase-03 framing would have been Rule 2 + Rule 4 + Rule 5 + Rule 6 violations. The substitution to present-tense semantic clarification + canonical-source citation (`envelope-model.md § metadata.posture_level`) is genuinely rule-compliant.

The substitution is substantive (not cosmetic): it changes the framing axis from "future migration plan" to "present semantic layer + canonical source" — preserving the disambiguation value while satisfying `spec-accuracy.md`. **PASS.**

---

## Round 2 closure summary

| ID    | Severity | Round 2 description                                                                                                                                                      | Shard 3 closure                                                                                                                                                                                    | Verification                                                                                      |
| ----- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| R2-F1 | HIGH     | Orphan posture_change on F-2 invariant violation (5a → invariants → 5b ordering committed the posture_change before the invariant raise)                                 | Step 5-PRECONDITIONS block promotes mutation + invariants BEFORE Step 5a; atomic fail-closed on invariant violation                                                                                | Sweeps 1+2+3 PASS; 12/12 R2-closure tests pass                                                    |
| R2-F2 | MED      | `_is_posture_carrying_envelope` side-effect surface (Protocol docstring did not pin side-effect-free contract; gate's attribute-read surface was unbounded by any test)  | Docstring contract paragraph + Tier 1 spy-adapter test bounding exactly 5 Protocol-declared attribute reads                                                                                        | Sweeps 4+5 PASS; spy test catches both expansion AND duplication                                  |
| R2-F3 | LOW      | Cross-spec drift on Shared Household composition (`min(p.posture_level for p in principals)` ambiguous between envelope mint-state and Ledger-derived effective posture) | Present-tense semantic-layer clarification + citation of canonical source (`envelope-model.md § metadata.posture_level`) at both `specs/posture-ladder.md:128` and `specs/shared-household.md:102` | Sweep 6 PASS; substitution is substantive and rule-compliant per `spec-accuracy.md` Rules 2/4/5/6 |

---

## New findings (Round 3)

NONE.

The diff is bounded: `bf1f66f` (precondition restructure), `e21d67f` (test flip), `eb72777` (Protocol docstring + spy test), `58a3b78` (spec clarifications), `eee0901` (journal 0024), `a8a4fdb` (Tier 2 zero-Ledger-entries case). Each commit is small and focused on its R2 finding. No drive-by changes, no scope creep, no orphan code introduced.

`/redteam` mechanical grep for inline DDL outside migrations: N/A — Shard 3 touched no DDL.
`/redteam` `pytest --collect-only` gate: PASS, exit 0, 609 tests.
`/redteam` log triage gate (`rules/observability.md` MUST Rule 5): full test suite output scanned, no WARN/ERROR/DEPRECATION lines.

---

## Same-bug-class sibling sweep (`rules/autonomous-execution.md` MUST Rule 4)

R2-F1 closure addresses application-level paired-emission atomicity. Audited the repo for sibling sites that might exhibit the same bug class:

- `envoy/authorship/posture_gate.py` is the ONLY 5-step gate in the codebase
- No other public module performs paired `_ledger.append` calls with intermediate validation that could orphan the first entry
- The transient-Ledger-failure variant (F-001 / issue #24) IS the cross-class extension; correctly scoped as open Phase 03 work per Ledger transactional primitive

No same-bug-class sibling site remains uncovered within Shard 3's call-graph reach. **PASS.**

---

## Convergence verdict

**CONVERGED.** All three Round 2 findings closed; no new findings introduced; 609/609 tests pass; mechanical sweeps clean; LLM judgment confirms structural atomicity, spy test catches both expansion and duplication failure modes, spec edit substitution is substantive and rule-compliant.

Recommend `/codify` for T-02-33 closure-of-record (Tier 2 envelope_edit pairing).

---

## Receipts

- Round 2 audit corpus: `workspaces/phase-01-mvp/04-validate/round-2-{code-review,security-audit,spec-compliance}-2026-05-24.md`
- Round 3 disposition journal: `workspaces/phase-01-mvp/journal/0024-DECISION-precondition-invariants-and-orphan-prevention.md`
- Shard 3 commits: `bf1f66f` (R2-F1 fix), `e21d67f` (R2-F1 test flip), `eb72777` (R2-F2 docstring + spy), `58a3b78` (R2-F3 spec), `eee0901` (journal), `a8a4fdb` (R2-F1 Tier 2)
- Merged main: `2264ae2`
- Test gate: 609/609 pass; collect-only exit 0; zero WARN+
