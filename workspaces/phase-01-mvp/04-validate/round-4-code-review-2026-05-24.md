# Round 4 Code Review — T-02-33 Shard 3 Convergence Confirmation

- **Date:** 2026-05-24
- **Scope:** Reproduce Round 3 verdict against unchanged HEAD; satisfy convergence criterion "2 consecutive clean rounds"
- **HEAD:** `2264ae2` (unchanged since Round 3)
- **Cumulative diff:** `641dd2d..2264ae2` (entire T-02-33 follow-up chain)
- **Round 3 baseline:** `round-3-code-review-2026-05-24.md` — 11/11 sweeps PASS, 0 findings, CONVERGED
- **Round 4 verdict:** **REPRODUCES** — 11/11 sweeps PASS byte-identically; 2 new stability checks PASS; 0 new findings

---

## Summary

- **Overall status:** Clean — Round 3 results reproduce; convergence criterion MET
- **Tests:** 609/609 pass (matches Round 3); `pytest --collect-only` exit 0
- **Critical issues:** 0
- **Important improvements:** 0
- **Minor improvements:** 0
- **Probe stability:** PASS — all 11 sweeps produced identical results
- **Cumulative orphan sweep:** PASS — every new symbol has callers/importers

---

## Mechanical sweeps (Round 3 reproduction + 2 stability checks)

### Sweep 1 — AST step ordering reproduction

Re-grep on `envoy/authorship/posture_gate.py`:

| Step                                                        | Round 3 line | Round 4 line | Match |
| ----------------------------------------------------------- | ------------ | ------------ | ----- |
| `mutation = envelope.mutate_for_posture_level(target)`      | 1008         | 1008         | ✓     |
| `raise PostureEnvelopeMutationInvariantError` (envelope_id) | 1019         | 1019         | ✓     |
| `raise PostureEnvelopeMutationInvariantError` (new_version) | 1027         | 1027         | ✓     |
| `raise PostureEnvelopeMutationInvariantError` (diff_hash)   | 1035         | 1035         | ✓     |
| Step 5a `_ledger.append(entry_type="posture_change", ...)`  | 1078         | 1078         | ✓     |
| Step 5b `_ledger.append(entry_type="envelope_edit", ...)`   | 1115         | 1115         | ✓     |

Ordering: mutate (1008) → invariants (1019, 1027, 1035) → 5a (1078) → 5b (1115). Byte-identical to Round 3. **PASS.**

### Sweep 2 — Tier 1 R2-F1 test flip reproduction

`grep -nE 'types == \[\]' tests/tier1/test_posture_gate_5_step_fail_closed.py`:

- 4 hits at lines 1679, 1712, 1745, 1775 — same lines as Round 3 (all in `TestStep5bMutationInvariantChecks`). **PASS.**

### Sweep 3 — Tier 2 zero-Ledger-entries case reproduction

`TestF2InvariantViolationEmitsNeitherEntry` at line 672 (same as Round 3); 3 methods present:

- `test_envelope_id_mismatch_emits_neither_entry` (line 701)
- `test_new_version_drift_emits_neither_entry` (line 747)
- `test_malformed_diff_hash_emits_neither_entry` (line 789)

Each consumes the real `EnvoyLedger` fixture per `rules/testing.md` Tier 2. **PASS.**

### Sweep 4 — Protocol docstring contract reproduction

`grep -nE "side-effect|side effect" envoy/authorship/posture_gate.py`:

- Line 677: "Implementations of this Protocol MUST have side-effect-free attribute"
- Line 693: "The gate cannot enforce side-effect-freeness at runtime"

Same line numbers as Round 3. The contract block (lines 675-699) is intact. **PASS.**

### Sweep 5 — Spy adapter test reproduction

`TestPostureCarryingEnvelopeProtocolDiscipline` at line 1972 (same as Round 3). `_EXPECTED_PROTOCOL_ATTR_READS` (line 2000) bounds the 5 Protocol-declared attributes; `_SpyEnvelope` (line 2010) records reads; the three assertions (set equality, no-leakage, exact count) survive. **PASS.**

### Sweep 6 — R2-F3 present-tense audit reproduction

`grep -E "Pre-Phase|will be refactored|future scope|when X lands|future-tense|TBD|TODO" specs/posture-ladder.md specs/shared-household.md`:

- Single hit: `specs/shared-household.md:165` — pre-existing `## Open questions` line ("cross-principal duress coupling TBD")

Identical to Round 3. The TBD predates Shard 3 (not introduced) and lives in the documented out-of-scope `## Open questions` section; per `rules/spec-accuracy.md` Exception 1 + `rules/zero-tolerance.md` Rule 1c (pre-existing requires SHA pre-dating session) it is correctly out of scope. **PASS.**

### Sweep 7 — `__all__` discipline reproduction

`envoy/authorship/__init__.py` (69 LOC):

- 13 Posture\* symbols in `__all__`
- All 13 have eager `from envoy.authorship.posture_gate import ...` imports
- No `__getattr__` lazy resolution

Matches Round 3. **PASS.**

### Sweep 8 — Cross-CLI hygiene reproduction

`grep -nE 'Agent\(subagent_type=|Claude Code|CLAUDE\.md|PascalCase|SessionStart|PreToolUse|PostToolUse|UserPromptSubmit' workspaces/phase-01-mvp/journal/002[1234]*.md specs/posture-ladder.md specs/shared-household.md`:

- 0 hits across all 6 files

Matches Round 3. Per `rules/cross-cli-artifact-hygiene.md` MUST Rules 1-5 — workspace artifacts CLI-neutral. **PASS.**

### Sweep 9 — Specs-authority Rule 5b sibling sweep reproduction

`posture_level` references across `specs/*.md`:

- `specs/envelope-model.md:34, 96` — mint-state semantics + canonical enum (authoritative, predates Shard 3)
- `specs/posture-ladder.md:128, 131, 132, 133, 208` — Shard 3 clarification (citing canonical source `envelope-model.md § metadata.posture_level`)
- `specs/runtime-abstraction.md:150, 221` — N2 cache invalidation (5-property list, orthogonal axis)
- `specs/shared-household.md:60, 102, 104, 105, 106` — Shard 3 clarification (citing canonical source)

Cross-spec consistency holds: Shard 3 edits cite `envelope-model.md` as canonical; `runtime-abstraction.md` references are on an orthogonal cache-invalidation axis. Matches Round 3 — no sibling drift. **PASS.**

### Sweep 10 — pytest --collect-only exit 0 reproduction

`.venv/bin/pytest --collect-only -q tests/`:

- **609 tests collected** in 0.40s (Round 3: 609 in 0.39s — same count, identical scope)
- Exit code 0

Matches Round 3. **PASS.**

### Sweep 11 — LOC trajectory reproduction

- `envoy/authorship/posture_gate.py`: 1151 LOC (Round 3: 1151) ✓
- `envoy/authorship/__init__.py`: 69 LOC ✓
- `tests/tier1/test_posture_gate_5_step_fail_closed.py`: 2161 LOC ✓
- `tests/tier2/test_posture_gate_wiring.py`: 1053 LOC ✓

`posture_gate.py` GREW by 50 LOC across Shard 3 (1101 → 1151) — no reduction occurred, `rules/refactor-invariants.md` MUST Rule 1 does not trigger. Matches Round 3 disposition. **N/A — rule does not trigger.**

### Sweep 12 (NEW) — Probe-stability check

Per `rules/probe-driven-verification.md` MUST-4: if any sweep diverges from Round 3 output, that's a HIGH non-determinism finding.

All 11 sweeps reproduced byte-identical results (same line numbers, same counts, same matches, same exit codes). Zero divergence from Round 3 documented output. **PASS — no non-determinism.**

### Sweep 13 (NEW) — Cumulative orphan-detection sweep

Per `rules/orphan-detection.md`: enumerate new public/private symbols across `641dd2d..2264ae2` and verify each has callers/importers.

New symbols across cumulative chain:

| Symbol                                          | Definition            | Callers / Importers                                                                                                                                                                         |
| ----------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PostureEnvelopeMutationInvariantError` (class) | `posture_gate.py:423` | `posture_gate.py:1019/1027/1035` (3 raise sites); `posture_gate.py:152` (`__all__`); `__init__.py:33/59` (re-export); `tests/tier1/...` (10+ test sites); `tests/tier2/...` (2+ test sites) |
| `_is_posture_carrying_envelope` (helper)        | `posture_gate.py:619` | `posture_gate.py:877` (kwarg-boundary check); `tests/tier1/...:2054/2058` (spy test)                                                                                                        |

Every new symbol has ≥1 production caller AND ≥1 test caller. No orphans. **PASS.**

---

## LLM judgment — Round 3 scope re-walk

### `PostureEnvelopeMutationInvariantError` docstring + user_message

Per `rules/observability.md` Rule 8 (schema-revealing field names MUST be DEBUG or hashed).

The class lives at `posture_gate.py:423-445`. Reviewed both surfaces:

- **Docstring (lines 424-436):** Names "envelope_id", "new_version", "diff_hash" — these are PROTOCOL FIELD NAMES (Round 1 F-2 disposition discusses them by name), NOT schema-revealing column names from a customer-facing table. The docstring is developer documentation, not log output; `rules/observability.md` Rule 8 governs structured log lines emitted at runtime, not type docstrings.
- **`user_message` (lines 441-444):** "There was a problem confirming the envelope update for this posture change. The change has not been recorded — please re-open Weekly Posture Review and try again."
  - Plain-language per `rules/communication.md` — no jargon, no schema identifiers, no internal field names exposed
  - No leakage of which specific invariant failed (envelope_id mismatch vs version drift vs malformed diff_hash) — user sees one generic message; the operator-facing log captures the `reason` parameter
- **`__str__` form (line 445):** `f"PostureEnvelopeMutationInvariantError: {reason}"` — emitted on `raise` for stack traces; `reason` is operator-facing detail and goes only to error logs, never to user-facing surfaces.

**Verdict: PASS.** The user_message is plain-language; the docstring describes the failure-mode class for developers; no schema-revealing identifiers leak to user-facing logs.

### `_is_posture_carrying_envelope` helper — side-effect surface

Reviewed `posture_gate.py:619-644`:

```python
def _is_posture_carrying_envelope(obj: object) -> bool:
    return (
        hasattr(obj, "envelope_id")
        and hasattr(obj, "prior_version")
        and hasattr(obj, "prior_content_hash")
        and hasattr(obj, "prior_posture_level")
        and callable(getattr(obj, "mutate_for_posture_level", None))
    )
```

- Five attribute reads via `hasattr` (4) + `getattr` (1) — exactly matches `_EXPECTED_PROTOCOL_ATTR_READS` count of 5 in the spy test.
- No I/O. No lock acquisition. No log emission. No state mutation. The function reads attributes and returns a bool.
- The `getattr(..., None)` form is the standard PEP-544 Protocol conformance idiom — `None` default eliminates the `AttributeError` branch.
- Side-channel exposure: the helper is called on ALL `request_transition` paths (`posture_gate.py:877`) including ratchet-down paths where envelope is supplied informationally. The Protocol docstring (lines 675-699) explicitly pins the IMPLEMENTOR contract that attribute reads must be side-effect-free.

**Verdict: PASS.** No side-channel attack surface; gate's attribute-read footprint exactly matches the bounding test.

### Spy-adapter test pattern — production-misuse risk

Reviewed `tests/tier1/test_posture_gate_5_step_fail_closed.py:1972-2098`:

- `_SpyEnvelope` uses `__getattribute__` instrumentation to record every attribute access into a per-instance `_observed_reads` list.
- The pattern is test-only — production envelopes never override `__getattribute__` for observation purposes.
- Misuse risk if copy-pasted into production: a class with `__getattribute__` override that records reads to an unbounded list IS a memory-leak vector AND would violate the Protocol's side-effect-free contract (writing to a list IS observable state mutation).
- However: the spy lives inside a `class TestPostureCarryingEnvelopeProtocolDiscipline` test class, instantiated only inside the test function, and is freed when the test returns. The class is also defined inside the test function body (line 2010-2049), so it's a function-local class with no module-level export — explicitly NOT reachable from production import paths.

**Verdict: PASS.** The spy is test-scoped, function-local, not exported; copy-paste into production is contained by the structural defense that the class is unreachable from any non-test import.

---

## Log triage gate (`rules/observability.md` MUST Rule 5)

### Default `pytest tests/`:

```
609 passed in 18.29s
```

No WARN/ERROR/DEPRECATION lines in default output. **PASS.**

### Escalated `pytest -W error::DeprecationWarning -W error::ResourceWarning -W error::RuntimeWarning`:

```
609 passed, 29 warnings in 18.71s
```

All 29 warnings localized to a SINGLE test file:

```
tests/regression/test_round1_observability_log_keys.py::
    TestRound1TrustVaultReadMetadataParseFailedWarn::
        test_read_metadata_logs_parse_failed_on_non_json_payload
```

Source: `ResourceWarning: unclosed database in <sqlite3.Connection object at 0x...>` raised through `PytestUnraisableExceptionWarning`. The warning fires when the test simulates an unparseable JSON payload by destructively manipulating a TrustVault SQLite handle.

**Pre-existing disposition:** The test was added in commit `efa3b2f` (2026-05-23) — this commit is **outside the T-02-33 cumulative chain** (`641dd2d..2264ae2`). Per `rules/zero-tolerance.md` Rule 1c, the SHA pre-dates the cumulative chain start; the warning is pre-existing and out of Round 4's scope.

**Round 3 reconciliation:** Round 3 reported "no WARN/ERROR/DEPRECATION lines" — that statement was true for **default pytest output** (which is what Round 3's scan command produced). The 29 ResourceWarnings surface ONLY under `-W error::ResourceWarning` escalation, which neither Round 3 nor Round 4's mission specifies as the trigger condition. Round 4's default-pytest scan reproduces Round 3's clean result exactly. The escalated scan was performed defensively in Round 4 and surfaces a pre-existing warning source uncoupled from the T-02-33 chain.

**Not a new finding for Round 4.** Tracking note: if the next /codify cycle wants to drive ResourceWarnings to zero, the test (`test_round1_observability_log_keys.py`) needs a `with closing(sqlite3.connect(...))` or fixture-scoped teardown — that is independent Phase 01 hygiene work, separately scoped from the convergence claim here.

---

## New findings (Round 4)

NONE.

The diff is unchanged from Round 3 (`2264ae2` HEAD is byte-identical to Round 3's audit target). Every mechanical sweep reproduces; the two new stability checks pass; the LLM-judgment re-walk on the three Round-3-explicit scope items (typed error, helper, spy pattern) surfaces no missed concerns.

---

## Round 3 → Round 4 probe stability summary

| Sweep                                 | Round 3 result                                           | Round 4 result    | Stable |
| ------------------------------------- | -------------------------------------------------------- | ----------------- | ------ |
| 1 — AST step ordering                 | mutate@1008, invariants@1019/1027/1035, 5a@1078, 5b@1115 | identical         | ✓      |
| 2 — Tier 1 `types == []`              | 4 hits @ 1679/1712/1745/1775                             | identical         | ✓      |
| 3 — Tier 2 F2InvariantViolation class | class@672, 3 methods                                     | identical         | ✓      |
| 4 — Protocol docstring side-effect    | lines 677, 693                                           | identical         | ✓      |
| 5 — Spy adapter test                  | class@1972, exact-set assertions                         | identical         | ✓      |
| 6 — Present-tense audit               | 1 hit (pre-existing TBD at shared-household:165)         | identical         | ✓      |
| 7 — `__all__` discipline              | 13 Posture\* symbols, all eager                          | identical         | ✓      |
| 8 — Cross-CLI hygiene                 | 0 hits                                                   | identical         | ✓      |
| 9 — Sibling spec sweep                | `envelope-model.md § metadata.posture_level` canonical   | identical         | ✓      |
| 10 — `pytest --collect-only`          | 609 tests, exit 0                                        | 609 tests, exit 0 | ✓      |
| 11 — LOC trajectory                   | posture_gate.py 1151 (grew 50)                           | identical         | ✓      |
| 12 (NEW) — probe stability            | —                                                        | all 11 reproduce  | ✓      |
| 13 (NEW) — cumulative orphan          | —                                                        | 0 orphans         | ✓      |

Probe-driven verification per `rules/probe-driven-verification.md` MUST-4: every probe is structural (file existence, AST line numbers, grep counts, exit codes, set equality). No regex-for-semantic-claims used. Determinism: every probe re-ran with identical input (unchanged SHA) and produced byte-identical output.

---

## Convergence verdict

**Round 4 reproduces Round 3 verdict; convergence criterion (2 consecutive clean rounds) MET.**

Receipts:

- Round 3 baseline: `workspaces/phase-01-mvp/04-validate/round-3-code-review-2026-05-24.md`
- Cumulative chain: `git diff 641dd2d..2264ae2`
- Merged main: `2264ae2` (PR #27)
- Test gate: 609/609 pass; collect-only exit 0; default-output WARN/ERROR clean
- Pre-existing escalated-output ResourceWarning source: `tests/regression/test_round1_observability_log_keys.py` (commit `efa3b2f`, pre-dates cumulative chain)

Recommend `/codify` for T-02-33 closure-of-record (Tier 2 envelope_edit pairing).
