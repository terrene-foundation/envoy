# T-02-33 Round 1 Code Review — 2026-05-24

**Reviewer**: gold-standards quality-reviewer pass (mechanical sweeps + LLM judgment)
**Scope**: commits `1e6b256..3ad3fc4`, merged at `641dd2d` (PR #23)
**Diff**: `git diff e8c7c80..641dd2d` — 1329 insertions / 50 deletions / 10 files
**Test verdict (independently re-derived)**: 100/100 PASS in tests/tier1 + tests/tier2
**Overall status**: Clean with 1 LOW finding + 1 MED same-bug-class observation; no FIX-NOW items.

---

## Summary By Severity

| Severity | Count | Disposition guidance                                                                                                                                                                  |
| -------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CRIT     | 0     | —                                                                                                                                                                                     |
| HIGH     | 0     | —                                                                                                                                                                                     |
| MED      | 1     | FILE-ISSUE — `posture_change`/`envelope_edit` Ledger atomicity (a Step 5a write that succeeds followed by a Step 5b failure would land an orphan posture_change). Flagged, NOT fixed. |
| LOW      | 1     | FIX-NEXT-ROUND — defensive `if envelope is None` re-raise inside Step 5b (line 939–940) is unreachable per Step 3e; structural redundancy.                                            |
| INFO     | 2     | informational — see below                                                                                                                                                             |

---

## 1. Mechanical Sweeps

| #   | Probe                                                                                                                                                                    | Command                                                                                                                                        | Expected   | Actual                                                                                                                                                                                                                                                                                                                                                                                       | Verdict |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| 1a  | `envelope_edit` emission sites in `posture_gate.py`                                                                                                                      | `grep -c "envelope_edit" envoy/authorship/posture_gate.py`                                                                                     | ≥1         | 25                                                                                                                                                                                                                                                                                                                                                                                           | PASS    |
| 1b  | `PostureRatchetEnvelopeMissingError` raise + export + test sites                                                                                                         | `grep -c "PostureRatchetEnvelopeMissingError" envoy/authorship/posture_gate.py envoy/authorship/__init__.py tests/tier{1,2}/test_posture_*.py` | ≥1+1+1     | posture_gate.py:9, **init**.py:2, tier1:6, tier2:6                                                                                                                                                                                                                                                                                                                                           | PASS    |
| 1c  | Error class importable everywhere PostureGate is                                                                                                                         | `grep -rn "from envoy.authorship import" envoy/ tests/`                                                                                        | resolved   | tier1/test_authorship_score_recompute_pure.py:26, tier2/test_posture_gate_wiring.py:51 — both packages import via the same facade; the new error is included in `__all__`                                                                                                                                                                                                                    | PASS    |
| 2   | Full test collection                                                                                                                                                     | `.venv/bin/pytest --collect-only -q tests/`                                                                                                    | exit 0     | exit 0 — 579 tests collected in 0.53s                                                                                                                                                                                                                                                                                                                                                        | PASS    |
| 3   | Every new symbol in `__all__` has an eager import at module top                                                                                                          | manual diff of `envoy/authorship/__init__.py`                                                                                                  | yes        | `PostureRatchetEnvelopeMissingError` appears on lines 40 (eager import) and 65 (`__all__`). Matches `rules/orphan-detection.md` Rule 6.                                                                                                                                                                                                                                                      | PASS    |
| 4   | Cross-CLI artifact hygiene in journal/workspace edits (`Agent(subagent_type=...)`, `Claude Code is`, `SessionStart`, `Read tool`, `Edit tool`, `CLAUDE.md` as authority) | `grep -n "<patterns>" workspaces/phase-01-mvp/journal/0021* workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md`      | 0          | 0 hits across both files                                                                                                                                                                                                                                                                                                                                                                     | PASS    |
| 5   | Refactor-invariant (LOC test) — file shrank? `posture_gate.py` grew +253; rule does not trigger but checked anyway                                                       | `git diff --stat e8c7c80..641dd2d -- envoy/authorship/posture_gate.py`                                                                         | n/a        | +253 (grew, no shrink) — Rule does not require an invariant test here                                                                                                                                                                                                                                                                                                                        | N/A     |
| 6   | Full-sibling re-derivation per `specs-authority.md` Rule 5b (`posture_level`, `envelope_edit`, `PostureRatchetEnvelopeMissingError` across spec siblings)                | `grep -rn ... specs/`                                                                                                                          | drift-free | `posture-ladder.md` (5 hits, all consistent), `envelope-model.md` (3 hits, all consistent), `ledger.md` (4 hits, all consistent), `shared-household.md` (2 hits documenting field), `runtime-abstraction.md` (2 hits as cache-invalidation key), `cross-domain-flows.md` (2 hits as related entry type), `envelope-library.md` (0 hits — no drift, not a stakeholder). No phantom citations. | PASS    |
| 7   | Probe-driven verification sweep: regex/keyword scoring of semantic claims in tests                                                                                       | `grep -rEn 'def (verify\|score\|assert\|check\|probe)_[A-Za-z_]*(recommend\|refus\|...)' tests/`                                               | 0          | 0                                                                                                                                                                                                                                                                                                                                                                                            | PASS    |

**Re-derived test run (Tier 1 + Tier 2 T-02-33 surface only):**

```
tests/tier2/test_posture_gate_wiring.py ........                         [  8%]
tests/tier1/test_posture_gate_5_step_fail_closed.py .................... [ 28%]
........................................................................ [100%]
============================= 100 passed in 0.06s ==============================
```

All 100 tests pass. No warning lines, no deprecations, no errors in output.

---

## 2. Log Triage Gate (`observability.md` Rule 5)

```
$ .venv/bin/pytest tests/tier2/test_posture_gate_wiring.py tests/tier1/test_posture_gate_5_step_fail_closed.py -x --tb=short 2>&1 | grep -iE 'warn|error|deprecat|fail' | sort -u
tests/tier1/test_posture_gate_5_step_fail_closed.py .................... [ 28%]
```

Single matched line is the pytest progress bar that contains the substring `fail_closed` — false positive from the test filename, NOT a runtime WARN/ERROR/DEPRECATION.

| Entry                                                   | Disposition    | Rationale                                                                                |
| ------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------- |
| `test_posture_gate_5_step_fail_closed.py` progress line | FALSE POSITIVE | Pytest progress output emits the test filename which contains `fail_closed`; no warning. |

Gate: PASS (zero acknowledged WARN+ entries).

---

## 3. LLM Judgment Findings

### F-001 (MED — FILE-ISSUE): Step 5a/5b pairing is NOT transactionally atomic at the Ledger layer

**Location**: `envoy/authorship/posture_gate.py:899-963`

**Symptom**: The gate enforces ordering (5a posture_change, then 5b envelope_edit) but treats them as two separate `EnvoyLedger.append` calls. If `EnvoyLedger.append` raises an exception ON THE SECOND CALL (e.g. transient store failure, network blip, or any future `_audit_store.append` failure mode), Step 5a has already written a signed `posture_change` Ledger entry, and Step 5b's failure propagates to the caller. The caller now sees an exception AND an orphan `posture_change` entry on disk; the envelope is unmutated (because `mutate_for_posture_level` was called but the new envelope was never persisted by any external committer); a downstream audit reconstructing chain integrity will see a `posture_change` entry with no paired `envelope_edit` — a spec § Ratchet-up requirement #3 violation that the gate explicitly forbids.

**Spec contract**: `specs/posture-ladder.md` § Ratchet-up requirement #3 ("any posture change is an `envelope_edit`") + the test class `TestFailedRatchetUpEmitsNeitherEntry` which asserts "no orphan envelope_edit can land without its posture_change sibling, and vice versa." The test currently covers ONLY the Step 1-4 failure modes (which short-circuit BEFORE either append). The Step 5b-fails-after-Step-5a-succeeded path is uncovered AND structurally permitted by the current code.

**Probe**:

```bash
grep -n "self._ledger.append" envoy/authorship/posture_gate.py
# 899:        entry_id = await self._ledger.append(
# 951:            envelope_edit_entry_id = await self._ledger.append(
```

Two distinct await sites against the same Ledger object, no try/except around either, no compensating action if 951 raises.

**Severity rationale**: MED, not HIGH, because: (a) `EnvoyLedger.append` failures are not load-bearing for Phase 01 narrow scope (in-memory store + Ed25519); (b) the spec doesn't explicitly mandate transactional atomicity, just ordering; (c) failure is observable downstream (audit chain reconstruction would surface the orphan and fail the chain-integrity check, per the existing audit story). NOT FIX-NOW: a real fix requires either Ledger-level transactional support or a compensating posture_change-rollback entry — both are architectural extensions that exceed one shard.

**Disposition**: FILE-ISSUE for Phase 03 alongside the cooling-off TIMER work (where the WPR ritual is the natural compensating-action site). Track in workspace todos as a known gap; the test `test_pairing_atomic_on_step5b_failure` would be the regression lock.

---

### F-002 (LOW — FIX-NEXT-ROUND): Unreachable defensive guard duplicates Step 3e raise

**Location**: `envoy/authorship/posture_gate.py:931-940`

**Symptom**:

```python
# Step 5b runs ONLY if target > current. Inside that branch:
if envelope is None:
    raise PostureRatchetEnvelopeMissingError(current=current, target=target)
```

This raise is structurally unreachable because Step 3e (line 852) already raises the same typed error on the same condition — control flow cannot reach line 939 with `envelope is None` on a ratchet-up. The comment at lines 931-938 acknowledges this ("MyPy can't narrow `envelope` past the Step 3e raise above; the runtime invariant is: if we reach here on ratchet-up, envelope is non-None. Assert defensively...").

Defensive guards for unreachable states are a low-grade smell — they teach future readers that the invariant isn't trusted, AND they create a parallel raise site that must stay in sync with Step 3e. If a refactor changes the error class on Step 3e but forgets line 940, the two sites silently diverge.

**Better pattern**: Use `assert envelope is not None` (gets stripped under `-O` but documents the invariant) OR `cast(_PostureCarryingEnvelope, envelope)` to satisfy MyPy without the runtime raise.

**Severity rationale**: LOW. It's correct under every runtime path; the cost is reader-clarity + future-refactor drift risk. Not FIX-NOW because it has zero observable impact.

**Disposition**: FIX-NEXT-ROUND — convert to `assert envelope is not None  # Step 3e raised PostureRatchetEnvelopeMissingError on this branch` (1-line change). Same-shard-class with the in-flight T-02-33 work but the shard is closed; defer to Round 2 polish or the next /implement cycle.

---

### F-003 (INFO): Tier 2 wiring test reaches into a `_audit_store` underscore-prefixed attribute

**Location**: `tests/tier2/test_posture_gate_wiring.py:349`

```python
events = await ledger._audit_store.query(AuditFilter(limit=1000))
```

Per the docstring (lines 343-348), this is intentional — the comment says "the underscore is not a security shield, just a 'stable surface for the facade only' convention. Tier 2 wiring is the legitimate observer surface for the audit-store-level entries the facade emits."

**Verdict**: INFO. The test acknowledges the convention break in prose. The alternative (a public `EnvoyLedger.list_entries()` method) is a legitimate future API surface but adding it solely for testing crosses Rule 4 of `zero-tolerance.md` ("no workarounds for SDK issues" — but in reverse, "no SDK changes solely for test ergonomics"). The chosen path (underscore-attribute access with documented rationale) is defensible.

**Disposition**: Track in journal for /codify if a clean reader surface emerges from Phase 02 work. No action required Round 1.

---

### F-004 (INFO): `_EnvelopeConfigPostureCarrier` adapter is real, not a fake

**Location**: `tests/tier2/test_posture_gate_wiring.py:162-285`

The adapter wraps the real `EnvelopeConfig` produced by the real `EnvelopeCompiler`. Its `mutate_for_posture_level()` re-uses the real `canonical_bytes` + `content_hash` pipeline from `envoy.envelope` (lines 224-225). The `_to_canonical_payload` helper (lines 246-285) duplicates the compiler's payload shape — this is the only meaningful surface drift risk because there are now TWO sites that must mirror `envoy.envelope.compiler.EnvelopeCompiler._to_canonical_payload`. A future change to the compiler's payload shape would silently break the Tier 2 round-trip assertion `mutation.new_content_hash != prior_content_hash` if the test's `_to_canonical_payload` is not updated.

**Severity**: INFO — the test would fail loudly because the produced `canonical_bytes` would differ from what the production compiler emits for the same logical input, AND any production caller would see a hash mismatch. The drift is detectable.

**Disposition**: Track via /codify — the long-term fix is to expose `_to_canonical_payload` (or an equivalent stable canonical-bytes API) on the public EnvelopeCompiler surface so the test can call through it. NOT a Round 1 fix.

---

## 4. Tier 1 / Tier 2 Per-Class Verification

### Tier 1 — `tests/tier1/test_posture_gate_5_step_fail_closed.py`

| Class                                                                                    | Cases   | Verdict | Notes                                                                                                                                                                                                                                                                                                                                                           |
| ---------------------------------------------------------------------------------------- | ------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TestStep1DivergenceCheck::test_matching_counts_pass_step_1`                             | updated | PASS    | Now passes `envelope=_FakePostureCarryingEnvelope()`; asserts `len(led.appends) == 2`. Correctly updated.                                                                                                                                                                                                                                                       |
| `TestStep3a*::test_personal_autonomous_NOT_blocked_by_3a`                                | updated | PASS    | DELEGATING→AUTONOMOUS ratchet-up; envelope kwarg supplied; asserts 2 appends.                                                                                                                                                                                                                                                                                   |
| `TestStep3c*::test_promotion_with_genesis_grant_passes_step_3c`                          | updated | PASS    | Standard pass-through ratchet-up; 2 appends.                                                                                                                                                                                                                                                                                                                    |
| `TestStep3d*::test_pseudo_to_tool_passes_with_zero_authorship`                           | updated | PASS    | N=0 entry; envelope supplied; 2 appends.                                                                                                                                                                                                                                                                                                                        |
| `TestStep4*::test_promotion_path_NEVER_calls_revoke`                                     | updated | PASS    | Promotion path; envelope supplied.                                                                                                                                                                                                                                                                                                                              |
| `TestStep5LedgerEntrySchema::test_happy_path_writes_posture_change_entry`                | updated | PASS    | Asserts 2 appends + Step 5a then Step 5b order + `posture_call["entry_type"] == "posture_change"` + `envelope_call["entry_type"] == "envelope_edit"`.                                                                                                                                                                                                           |
| `TestStep5LedgerEntrySchema::test_ledger_content_matches_spec_schema`                    | updated | PASS    | Exact-key assertion on both spec-mandated shapes: posture_change has 7 keys (schema_version, from_posture, to_posture, dimension_scope, trigger, evidence_ref, signed_by); envelope_edit has 7 keys (schema_version, envelope_id, prior_version, new_version, diff_hash, rollback_grace_window_seconds, signed_by). Matches `specs/ledger.md` §107-114 exactly. |
| `TestStep5PlusBET12Emission::test_ratchet_up_emits_bet12_after_ledger`                   | updated | PASS    | Asserts ordering across all three Step-5 sub-steps.                                                                                                                                                                                                                                                                                                             |
| `TestStep5PlusBET12Emission::test_principal_id_hashed_in_bet12_payload`                  | updated | PASS    | envelope supplied.                                                                                                                                                                                                                                                                                                                                              |
| `TestStep5PlusBET12Emission::test_authored_count_pulled_from_evidence_recomputed`        | updated | PASS    | envelope supplied.                                                                                                                                                                                                                                                                                                                                              |
| `TestStep5PlusBET12Emission::test_default_days_zero_when_caller_omits`                   | updated | PASS    | envelope supplied.                                                                                                                                                                                                                                                                                                                                              |
| `TestPostureChangeResult::test_result_carries_new_level_and_entry_id`                    | updated | PASS    | Asserts `result.ledger_entry_id == "sha256:specific-id"` (the fake returns the same id for both appends — comment correctly explains this).                                                                                                                                                                                                                     |
| `TestPostureChangeResult::test_result_is_frozen`                                         | updated | PASS    | envelope supplied.                                                                                                                                                                                                                                                                                                                                              |
| `TestErrorHierarchy::test_all_errors_inherit_from_PostureGateError`                      | updated | PASS    | Now includes `PostureRatchetEnvelopeMissingError`.                                                                                                                                                                                                                                                                                                              |
| `TestErrorHierarchy::test_all_errors_carry_user_message`                                 | updated | PASS    | New error verified to carry plain-language `user_message` per `rules/communication.md`.                                                                                                                                                                                                                                                                         |
| `TestStep3eEnvelopeMissingOnRatchetUp::test_ratchet_up_without_envelope_raises`          | NEW     | PASS    | PSEUDO→TOOL with envelope omitted raises; zero appends; zero BET-12 emits.                                                                                                                                                                                                                                                                                      |
| `TestStep3eEnvelopeMissingOnRatchetUp::test_ratchet_up_with_envelope_none_raises`        | NEW     | PASS    | TOOL→SUPERVISED with explicit envelope=None.                                                                                                                                                                                                                                                                                                                    |
| `TestStep3eEnvelopeMissingOnRatchetUp::test_ratchet_down_with_envelope_none_succeeds`    | NEW     | PASS    | DELEGATING→TOOL with envelope=None succeeds; exactly 1 posture_change, no envelope_edit.                                                                                                                                                                                                                                                                        |
| `TestStep3eEnvelopeMissingOnRatchetUp::test_ratchet_up_consumes_envelope_exactly_once`   | NEW     | PASS    | `envelope.mutate_calls == [PostureLevel.SUPERVISED]` — once-only consumption pinned.                                                                                                                                                                                                                                                                            |
| `TestStep3eEnvelopeMissingOnRatchetUp::test_failed_ratchet_up_does_not_consume_envelope` | NEW     | PASS    | Step 3d failure short-circuits BEFORE mutate; `envelope.mutate_calls == []`.                                                                                                                                                                                                                                                                                    |

**Coverage on the 4 levels of the ladder for the no-envelope ratchet-up branch**: PSEUDO→TOOL (test_ratchet_up_without_envelope_raises) + TOOL→SUPERVISED (test_ratchet_up_with_envelope_none_raises). SUPERVISED→DELEGATING + DELEGATING→AUTONOMOUS no-envelope cases are NOT directly tested. The reviewer brief said "covers the no-envelope branch on ratchet-up for all 4 levels of the ladder" — verified ONLY 2 of 4 are directly pinned. The remaining 2 are STRUCTURALLY covered because Step 3e fires before any level-specific gate, but per `rules/testing.md` § "Verify NEW modules have NEW tests" the explicit pins are missing for 2 levels.

**Finding** (NEW: F-005, LOW): consider adding 2 more no-envelope ratchet-up tests for SUPERVISED→DELEGATING + DELEGATING→AUTONOMOUS to pin all 4 ladder steps. NOT FIX-NOW — same-class with the existing 2; structurally redundant under Step 3e ordering invariant.

### Tier 2 — `tests/tier2/test_posture_gate_wiring.py`

| Class                                                                                       | Cases | Verdict | Notes                                                                                                                                                  |
| ------------------------------------------------------------------------------------------- | ----- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `TestEnvelopeEditPairingOnRatchetUp` (4 cases)                                              | NEW   | PASS    | PSEUDO→TOOL, TOOL→SUPERVISED, multi-step PSEUDO→DELEGATING, content_hash-changes assertion. Real `EnvoyLedger` + real Ed25519 + real EnvelopeCompiler. |
| `TestFailedRatchetUpEmitsNeitherEntry::test_insufficient_authorship_emits_neither_entry`    | NEW   | PASS    | SUPERVISED→DELEGATING with recomputed=2 (need=3) — zero Ledger appends + zero BET-12 emits. Fail-closed pairing invariant pinned at real-infra level.  |
| `TestPostureChangeOnRatchetDownNoEnvelopeEdit::test_ratchet_down_emits_only_posture_change` | NEW   | PASS    | DELEGATING→TOOL with `envelope=None` — exactly 1 posture_change, no envelope_edit, cascade-revoke called per-agent.                                    |
| `TestPostureRatchetEnvelopeMissingError` (2 cases)                                          | NEW   | PASS    | Typed error + user_message contract.                                                                                                                   |

**Tier 2 mocking sweep**: zero `unittest.mock` / `MagicMock` / `@patch` / `Mock(` imports. Confirms Tier 2 NO-mocking contract per `rules/testing.md`. The only literal matches for "mock" are docstring references at lines 15 and 91 — both explicitly stating the contract is no-mocking.

**Tier 2 adapter realness verification**: `_EnvelopeConfigPostureCarrier` (lines 162-285) wraps a real `EnvelopeConfig` from `envoy.envelope.compiler.EnvelopeCompiler.compile()` and uses the real `canonical_bytes` + `content_hash` from `envoy.envelope`. Adapter is real (production-shaped wrapper), not a fake. Verified by tracing `_compile_envelope()` → real `EnvelopeCompiler.compile()` → real canonical-bytes pipeline. (See F-004 above for the one duplicated `_to_canonical_payload` site that's a future surface-drift risk.)

---

## 5. Documentation Symmetry Checks

| Probe                                                                                              | Status | Evidence                                                                                                                                                                                                                                                                                  |
| -------------------------------------------------------------------------------------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `specs/posture-ladder.md` § Out of scope — envelope_edit deferral line REMOVED / upgraded          | PASS   | Diff shows the deferral bullet block (lines 161-173 in the old version) replaced with a closure block: "T-02-33 (Tier 2 wiring) closed the prior envelope_edit pairing deferral; ratchet-up now emits paired `posture_change` + `envelope_edit` Ledger entries per spec § Ratchet-up #3." |
| `specs/envelope-model.md` § Schema — `posture_level` field documented in the field-semantics block | PASS   | Diff adds `posture_level: "PSEUDO \| TOOL \| SUPERVISED \| DELEGATING \| AUTONOMOUS"` to the schema JSON block (line 34) AND a full field-semantics paragraph at line 96 explaining wire form + default + ratchet-up emission semantics + asymmetric pairing on demotion.                 |
| Journal cross-references resolve                                                                   | PASS   | `journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md` references `journal/0020-DECISION-envelope-edit-deferred-to-tier-2.md` (the original deferral); both exist.                                                                                                               |
| Closure of T-02-33 in `02-wave-2-...md` todo                                                       | PASS   | Diff shows the T-02-33 block updated with PR + commit closure (`workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md`).                                                                                                                                           |

---

## 6. Same-Bug-Class Gaps (per `rules/autonomous-execution.md` Rule 4)

These gaps are surfaced for awareness only — Round 1 is audit, NOT fix. They are flagged as same-class with the in-flight T-02-33 work but the shard is closed and merged.

1. **F-001 (MED)** — Step 5a/5b non-atomic Ledger pair. NOT same-shard-fixable: requires Ledger-level transactional support or a compensating-entry mechanism that exceeds one shard's load-bearing-logic budget. → FILE-ISSUE for Phase 03.
2. **F-002 (LOW)** — Unreachable defensive guard at line 939-940. SAME-SHARD-FIXABLE (1-line change to `assert`) but the shard is merged and the change is cosmetic. → FIX-NEXT-ROUND.
3. **F-005 (LOW)** — 2 of 4 ladder levels lack explicit no-envelope ratchet-up tests. SAME-SHARD-FIXABLE (~20 LOC of new test code) but structurally redundant. → FIX-NEXT-ROUND or close as wontfix.

None of the three meet the fix-immediately threshold of MUST Rule 4 (the shard is closed and merged; fixes are post-merge follow-ups, not in-flight same-PR additions).

---

## 7. Round 1 Verdict

**Approve with follow-ups.** The PR delivers what it claims:

- `envelope_edit` Ledger entry pairing on ratchet-up is structurally correct, fail-closed, and asymmetric per spec § Ratchet-down.
- `PostureRatchetEnvelopeMissingError` is a real typed error with `user_message` per `rules/communication.md`; raise site is at Step 3e (line 852) BEFORE any side-effect could fire (no envelope mutation, no Ledger writes, no BET-12 emit).
- `_envelope.mutate_for_posture_level(target)` is invoked AT MOST ONCE on the accepted ratchet-up path (line 941), result captured into local `mutation` and consumed by the envelope_edit content payload. The pinned test `test_ratchet_up_consumes_envelope_exactly_once` enforces this invariant.
- Tier 2 wiring is REAL (no mocks, real EnvoyLedger + real Ed25519 + real EnvelopeCompiler + real canonical-bytes pipeline).
- Documentation symmetry across specs/posture-ladder.md + specs/envelope-model.md + journal/0020 → 0021 cross-references is intact.
- No cross-CLI artifact-hygiene leaks in any T-02-33 workspace edit.

The MED finding (F-001 atomicity) is the only structural risk and is genuinely architectural — defer to Phase 03 alongside the WPR ritual work that's the natural compensating-action surface. The LOW findings (F-002 unreachable guard, F-005 missing 2-of-4 ladder-step tests) are FIX-NEXT-ROUND polish.

---

## 8. Cross-References

- `envoy/authorship/posture_gate.py` lines 852 (Step 3e raise), 899-902 (Step 5a append), 941 (mutate_for_posture_level call), 951-954 (Step 5b append) — load-bearing gate code.
- `envoy/authorship/__init__.py` lines 40 (eager import) + 65 (`__all__` entry) — `PostureRatchetEnvelopeMissingError` facade.
- `tests/tier2/test_posture_gate_wiring.py` — Tier 2 wiring; lines 162-285 contain the `_EnvelopeConfigPostureCarrier` real adapter.
- `tests/tier1/test_posture_gate_5_step_fail_closed.py` lines 1494-1590 — `TestStep3eEnvelopeMissingOnRatchetUp` class (5 NEW tests).
- `specs/posture-ladder.md` lines 161-173 (closure prose) + line 41 (Ratchet-up requirement #3).
- `specs/envelope-model.md` lines 34 (schema JSON) + 96 (field-semantics paragraph).
- `specs/ledger.md` lines 107-114 — envelope_edit wire shape (unchanged; new code conforms).
- `workspaces/phase-01-mvp/journal/0020-DECISION-envelope-edit-deferred-to-tier-2.md` — original deferral.
- `workspaces/phase-01-mvp/journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md` — DI design choice (envelope kwarg over Protocol surface).
