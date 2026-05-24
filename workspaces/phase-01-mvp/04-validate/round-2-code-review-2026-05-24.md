# T-02-33 Round 2 Code Review — 2026-05-24

**Reviewer**: quality-reviewer Round 2 pass (mechanical sweeps + LLM judgment, full re-derivation)
**Scope**: commits `641dd2d..e89914b` — PR #25 (Shard 1 — F-1/F-2/F-3/F-4 + F-002) and PR #26 (Shard 2 — F-5 regression).
**Files audited**: `envoy/authorship/posture_gate.py` (+134 lines), `envoy/authorship/__init__.py` (+2), `specs/envelope-model.md` (mint-state language), `tests/tier1/test_posture_gate_5_step_fail_closed.py` (+411), `tests/tier2/test_posture_gate_wiring.py` (+123), `tests/tier2/test_envelope_hash_mint_time_cached.py` (NEW, 419 LOC), 2 new journals (0022, 0023).
**Test verdict (independently re-derived)**: 605 tests collect; 126 pass across the T-02-33 surface (Tier 1 fail-closed + Tier 2 wiring + Tier 2 mint-time-cached).
**Overall status**: **Convergence — clean.** Every Round 1 finding closed with structural defense. No NEW findings introduced by Shard 1 or Shard 2. One follow-up observation (F-001 still open per issue #24 — by design, deferred to Phase 03).

---

## 1. Round 1 Closure Status — Re-Derived From Scratch

| Round 1 ID                                   | Sev      | Disposition | Closure evidence (re-verified)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Verdict                                                     |
| -------------------------------------------- | -------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| **F-001** (code review) / **F-3** (security) | MED      | FILE-ISSUE  | `gh issue view 24` returns OPEN Phase-03 issue titled "Phase 03: Ledger transactional / compensating-entry mechanism for paired posture_change + envelope_edit emission" with full acceptance criteria (architecture decision + EnvoyLedger surface + Tier 2 atomicity test + regression test).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | **CLOSED via FILE-ISSUE**                                   |
| **F-002**                                    | LOW      | FIX         | `grep -c "envelope is None" envoy/authorship/posture_gate.py` returns 3, but `grep -n` shows the 3 hits are: line 932 (Step 3e raise — load-bearing), line 999 (docstring comment), line 1012 (descriptive comment in the closure block explaining the removal). The redundant Step 5b `if envelope is None` guard at the old lines 939-940 is GONE; `assert envelope is not None` on line 1022 narrows MyPy without runtime ladder duplication.                                                                                                                                                                                                                                                                                                                                                                                                                                               | **CLOSED via REMOVAL**                                      |
| **F-1** (security)                           | HIGH     | FIX         | `_is_posture_carrying_envelope()` at line 619; Protocol check at line 852 fires BEFORE Step 1, BEFORE Step 5a, BEFORE any side-effect. 6 dedicated tests in `TestEnvelopeKwargProtocolCheck` (string / dict / partial / non-callable / None-on-ratchet-down accepted / no-side-effect verification).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | **CLOSED**                                                  |
| **F-2** (security)                           | HIGH     | FIX         | `PostureEnvelopeMutationInvariantError` declared lines 423-445 (with `user_message` per `communication.md`); 3 invariant raises at lines 1033/1041/1049 (envelope_id mismatch / new_version != prior+1 / diff_hash not `sha256:<64-hex>`); `_SHA256_HEX_PATTERN` constant line 99. 8 tests in `TestStep5bMutationInvariantChecks` (envelope_id mismatch, version regression, version skip, malformed diff_hash, wrong-prefix sha1, uppercase rejected, user_message contract, subclass contract).                                                                                                                                                                                                                                                                                                                                                                                              | **CLOSED**                                                  |
| **F-4** (security)                           | HIGH     | FIX         | `specs/envelope-model.md` updated with **mint-state semantics** + **audit-only role** paragraphs explicitly stating "no production read consumer dispatches on the envelope field's value." 2 Tier 2 tests in `TestPostureChangeOnRatchetDownNoEnvelopeEdit::test_ratchet_down_does_not_mutate_envelope_posture_level` (asserts `envelope.metadata.posture_level == "DELEGATING"` unchanged after demotion — UNCHANGED-VALUE, not merely "envelope_edit not emitted") + `TestEnvelopePostureLevelIsMintStateOnRatchetUp` (2 tests pinning new envelope object identity + version-bump + posture_level differs). Journal `0022-DECISION-posture-level-mint-state-interpretation.md` captures rationale.                                                                                                                                                                                         | **CLOSED**                                                  |
| **F-5** (security)                           | HIGH     | FIX         | NEW file `tests/tier2/test_envelope_hash_mint_time_cached.py` (419 LOC, 6 tests in `TestEnvelopeHashesAreMintTimeCached`): (1) `canonical_bytes` is `@dataclass(frozen=True)` AnnAssign field — not property/descriptor; (2) `content_hash` same shape; (3) AST walk of `envoy/envelope/*.py` rejects any deserializer (`from_json`, `from_dict`, `loads`, `deserialize`, etc.); (4) design-intent docstring phrases pinned at `canonical_bytes.py:73-83`; (5) real `EnvelopeCompiler.compile()` — `is`-identity check on canonical_bytes + content_hash across 3 reads (NOT equality — identity proves cached, not recomputed); (6) AST walk on `posture_gate.py::request_transition` confirms `envelope.prior_content_hash` consumed as `ast.Attribute` not `ast.Call`. Journal `0023-DISCOVERY-envelope-hashes-mint-time-cached-f5-false-positive.md` records the false-positive rationale. | **CLOSED via FALSE-POSITIVE + REGRESSION LOCK**             |
| **F-6** (security)                           | INFO/LOW | FIX         | `TestPostureLevelMintStateRead` (3 tests in Tier 1) exercises read path of `EnvelopeMetadata.posture_level` (default = "PSEUDO", round-trip for all 5 canonical names, enum-name parity). Satisfies `orphan-detection.md` Rule 1: field is reachable from at least one test.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | **CLOSED**                                                  |
| **F-003** (code review INFO)                 | INFO     | TRACK       | `_audit_store` underscore-attribute access at `tests/tier2/test_posture_gate_wiring.py:349` is unchanged. INFO only; documented in test docstring.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | **No regression**                                           |
| **F-004** (code review INFO)                 | INFO     | TRACK       | `_EnvelopeConfigPostureCarrier._to_canonical_payload` adapter at `tests/tier2/test_posture_gate_wiring.py:246-285` still duplicates the compiler payload shape. INFO only; deferred via /codify.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | **No regression**                                           |
| **F-005** (code review LOW)                  | LOW      | TRACK       | The "missing 2 of 4 ladder-step no-envelope-ratchet-up tests" finding is unchanged; structurally redundant under Step 3e ordering invariant. The new Round 2 fixture set adds 4 more Tier 1 cases (`TestEnvelopeKwargProtocolCheck` × 6 + `TestStep5bMutationInvariantChecks` × 8 + `TestPostureLevelMintStateRead` × 3) but does NOT specifically backfill the SUPERVISED→DELEGATING + DELEGATING→AUTONOMOUS no-envelope cases.                                                                                                                                                                                                                                                                                                                                                                                                                                                               | **TRACK** — no severity escalation; structurally redundant. |

**Convergence verdict**: Every Round 1 HIGH, MED, LOW is structurally closed via fix or formally accepted via FILE-ISSUE (F-001 only). No Round 1 finding remains "addressed without resolution".

---

## 2. Mechanical Sweeps (Re-Derived From Scratch, Not Trusting Round 1)

| #   | Probe                                                                                                                                                   | Command                                                                                                                                                                                            | Expected                                      | Actual                                                                                                                                                                                                                                                                                                                                                                          | Verdict |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| 1   | F-001 closure — gh issue 24 exists + acceptance criteria present                                                                                        | `gh issue view 24 --json number,title,state,body`                                                                                                                                                  | OPEN with 5-item acceptance                   | OPEN. Title: "Phase 03: Ledger transactional / compensating-entry mechanism for paired posture_change + envelope_edit emission". Body: full acceptance criteria + related artifacts (R1 reports, PR #23, specs/ledger.md, specs/posture-ladder.md).                                                                                                                             | PASS    |
| 2   | F-002 closure — redundant Step 5b `envelope is None` guard removed                                                                                      | `grep -c "envelope is None" envoy/authorship/posture_gate.py`                                                                                                                                      | ≤1 raise                                      | 3 hits total; only line 932 is a `raise` (Step 3e); 999 + 1012 are comments. Old lines 939-940 raise GONE.                                                                                                                                                                                                                                                                      | PASS    |
| 3   | F-2 closure — `PostureEnvelopeMutationInvariantError` declaration + 3 raises + ≥3 tests                                                                 | `grep -rn "PostureEnvelopeMutationInvariantError" envoy/authorship/ tests/`                                                                                                                        | ≥1 class def + 3 raises + 3 tests + 2 exports | Class lines 423-445; raises at lines 1033 / 1041 / 1049; **11 test sites** in test_posture_gate_5_step_fail_closed.py (envelope_id mismatch, new_version regression, new_version skip, malformed diff_hash, sha1-prefix, uppercase hex, user_message, subclass); 2 exports (`__init__.py:33` + `__all__:59`, `posture_gate.py::__all__:152`).                                   | PASS    |
| 4   | F-4 closure — mint-state language in spec + 2 test classes                                                                                              | `grep -A5 "posture_level" specs/envelope-model.md` + `grep "TestEnvelopePostureLevelIsMintStateOnRatchetUp\|TestPostureChangeOnRatchetDownNoEnvelopeEdit" tests/tier2/test_posture_gate_wiring.py` | both present                                  | spec line 96 carries `**Mint-state semantics:**` + `**Audit-only role:**` paragraphs. test_posture_gate_wiring.py lines 623 + 717 have both classes.                                                                                                                                                                                                                            | PASS    |
| 5   | F-5 closure — regression file exists + ≥6 tests                                                                                                         | `ls tests/tier2/test_envelope_hash_mint_time_cached.py && grep -c "def test_" ...`                                                                                                                 | ≥6                                            | 21136 bytes; 6 tests (canonical_bytes frozen, content_hash frozen, no deserializer, design-intent docstring, identity-stable compile, posture_gate attribute consumption).                                                                                                                                                                                                      | PASS    |
| 6   | `__all__` discipline — every new public symbol has eager import                                                                                         | manual diff of `envoy/authorship/__init__.py`                                                                                                                                                      | yes                                           | `PostureEnvelopeMutationInvariantError` lines 33 (eager import) + 59 (`__all__`). `PostureRatchetEnvelopeMissingError` lines 41 (eager) + 67 (`__all__`). 20 entries total, all eager.                                                                                                                                                                                          | PASS    |
| 7   | Cross-CLI artifact hygiene — no `Agent(subagent_type=` / `CLAUDE.md` / `SessionStart` / `Read tool` / `Edit tool` in journals 0022, 0023, or spec edits | `grep -nE "Agent\(subagent_type=\|Claude Code\|CLAUDE\.md\|SessionStart\|Read tool\|Edit tool\|Bash tool" workspaces/.../0022* 0023* specs/envelope-model.md`                                      | 0                                             | 0 hits                                                                                                                                                                                                                                                                                                                                                                          | PASS    |
| 8   | Refactor-invariants — file shrink?                                                                                                                      | `git diff --stat 641dd2d..e89914b -- envoy/authorship/posture_gate.py`                                                                                                                             | n/a                                           | +127 / -11 (net grew). LOC invariant test NOT required.                                                                                                                                                                                                                                                                                                                         | N/A     |
| 9   | Specs-authority Rule 5b — sibling re-derivation on changed terms (`posture_level`, `schema_version`, `PostureEnvelopeMutationInvariantError`)           | `grep -rn ... specs/posture-ladder.md specs/ledger.md specs/shared-household.md specs/runtime-abstraction.md specs/cross-domain-flows.md specs/envelope-library.md`                                | drift-free                                    | `posture_level`: 2 hits ladder + 2 hits shared-household + 2 hits runtime (cache invalidation key — consistent) + 0 envelope-library. `schema_version`: 39 hits in ledger.md (all entry types consistent at `"1.0"` form). `PostureEnvelopeMutationInvariantError`: 0 hits in siblings — correct (defensive internal invariant; not part of documented public schema contract). | PASS    |
| 10  | Probe-driven verification sweep                                                                                                                         | `grep -rEn 'def (verify\|score\|assert\|check\|probe)_[A-Za-z_]*(recommend\|refus\|complian\|respons\|intent\|semantic\|quality\|outcome\|narrative\|reasoning)' tests/ .claude/test-harness/`     | 0                                             | 0                                                                                                                                                                                                                                                                                                                                                                               | PASS    |
| 11  | Test collection across all of `tests/`                                                                                                                  | `.venv/bin/pytest --collect-only -q tests/`                                                                                                                                                        | exit 0                                        | exit 0 — 605 tests collected                                                                                                                                                                                                                                                                                                                                                    | PASS    |

**Re-derived test run (full T-02-33 surface):**

```
tests/tier1/test_posture_gate_5_step_fail_closed.py ................................... [ 73%]
tests/tier2/test_posture_gate_wiring.py ........... [ 95%]
tests/tier2/test_envelope_hash_mint_time_cached.py ...... [100%]
============================= 126 passed in 0.08s ==============================
```

126 tests pass. Zero warnings, zero deprecations, zero errors.

---

## 3. Log Triage Gate (`observability.md` Rule 5)

```
$ .venv/bin/pytest tests/tier1/test_posture_gate_5_step_fail_closed.py \
                   tests/tier2/test_posture_gate_wiring.py \
                   tests/tier2/test_envelope_hash_mint_time_cached.py -x --tb=short 2>&1 \
                   | grep -iE 'warn|error|deprecat|fail' | sort -u
tests/tier1/test_posture_gate_5_step_fail_closed.py .................... [ 15%]
```

| Entry                                                   | Disposition    | Rationale                                                                                               |
| ------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------- |
| `test_posture_gate_5_step_fail_closed.py` progress line | FALSE POSITIVE | Pytest progress output contains test filename `fail_closed`; not a runtime WARN/ERROR. Same as Round 1. |

Gate: **PASS** — zero acknowledged WARN+ entries.

---

## 4. LLM Judgment Findings (Round 2)

### F-2 invariants — implemented correctly, fire BEFORE the envelope_edit append

**Verdict**: Structurally correct. Three invariants fire at lines 1032/1040/1048, immediately after `mutation = envelope.mutate_for_posture_level(target)` (line 1023) and BEFORE the envelope_edit `EnvoyLedger.append` at line 1065. Each invariant raises `PostureEnvelopeMutationInvariantError` with a descriptive `reason`. No silent fallback. Per `zero-tolerance.md` Rule 3 the structural defense holds.

**Observation (NOT a new finding)**: The invariants fire AFTER Step 5a's `posture_change` append at line 979. This means an invariant violation produces the same orphan-`posture_change` state that F-001 already documented — the failure trigger surface for F-001 is now broader (it includes "buggy/malicious adapter that violates invariants" alongside "transient Ledger error"). Issue #24's acceptance criteria explicitly covers this: the regression test it mandates — "simulate Step 5b failure post-Step 5a; verify Ledger consistency invariant (either both entries absent OR both present OR compensating entry binds them)" — covers BOTH triggers (Ledger transient error AND invariant violation). The Round 2 test suite already exercises invariant-violation orphan-posture_change paths (`types == ["posture_change"]` assertion in 4 invariant-violation tests). Disposition: **no new finding**; the test scaffold for Phase 03 is partly in place.

### F-1 Protocol check — correctly placed BEFORE Step 1

**Verdict**: `_is_posture_carrying_envelope` defined at line 619; the call site at line 852 fires AFTER the basic-type kwarg validation (string `principal_id`, `evidence`, `trigger`, `revoke_on_demotion` tuple) AND BEFORE Step 1's divergence check. Crucially, it fires BEFORE Step 5a — so a structurally-malformed envelope kwarg raises `TypeError` with zero side-effects (no Ledger append, no envelope mutation, no BET-12 emission). `test_fail_closed_on_kwarg_check` directly asserts `led.appends == [] and sink.writes == []`.

**The check correctly preserves `envelope=None`** on ratchet-down paths (line 852: `if envelope is not None and not _is_posture_carrying_envelope(envelope)`).

### F-3 + F-002 — exactly ONE `envelope is None` raise, at Step 3e

**Verdict**: Only line 932 is a raise; lines 999 + 1012 are comments. The redundant defensive guard at the old lines 939-940 is GONE. `assert envelope is not None  # nosec — narrowing assertion, Step 3e enforces` at line 1022 narrows MyPy without duplicating the raise ladder. The closure comment at lines 1011-1021 explicitly cites both the unreachability (Step 3e raises first) AND the original mis-ordering (the old guard fired AFTER Step 5a, exactly the orphan-posture_change pattern F-001 documents).

### F-4 mint-state — Tier 2 tests are robust; ratchet-down test asserts UNCHANGED value

**Verdict**: `TestPostureChangeOnRatchetDownNoEnvelopeEdit::test_ratchet_down_does_not_mutate_envelope_posture_level` at lines 669-708:

1. Captures `mint_state_value = envelope.metadata.posture_level` BEFORE the demotion (line 691).
2. Asserts the captured value `== "DELEGATING"` (line 692, baseline pin).
3. Calls `gate.request_transition(... target=PostureLevel.TOOL ...)` with `envelope=None` (demotion path).
4. Asserts `envelope.metadata.posture_level == mint_state_value` (line 708, unchanged-value invariant).
5. Asserts `== "DELEGATING"` (line 709, redundant literal pin).

This is exactly the "asserts posture_level UNCHANGED, not just 'envelope_edit not emitted'" Round 1 prescribed.

`TestEnvelopePostureLevelIsMintStateOnRatchetUp::test_ratchet_up_returns_new_mint_state_original_untouched` (lines 731-762) pins:

- ORIGINAL envelope's `posture_level` unchanged after the gate accepts ratchet-up.
- Mutation result's `new_envelope.metadata.posture_level == "TOOL"` (the NEW mint state).
- Original `!=` new (explicit asymmetric pin).

`test_mutation_returns_new_envelope_object_not_in_place` (line 764): asserts `mutation.new_envelope is not envelope` (distinct Python object) + `envelope_version + 1` (monotonic bump) + `metadata.envelope_id` continuity (same envelope chain).

### F-5 regression test — structurally sound AST walks + identity check + design-intent pin

**Verdict**: All 6 tests will FAIL LOUDLY on the threat-model regressions Round 1 prescribed:

1. `test_canonical_bytes_is_a_stored_frozen_field` — AST `@dataclass(frozen=True)` check + AnnAssign field with `bytes` annotation. Fails if `canonical_bytes` becomes a `@property`.
2. `test_content_hash_is_a_stored_frozen_field` — same pattern. Fails if `content_hash` becomes a recomputed property.
3. `test_no_envelope_deserializer_exists` — AST walk of every `*.py` under `envoy/envelope/` rejects function/method names containing `from_json`, `from_dict`, `from_bytes`, `from_canonical`, `loads`, `parse_envelope`, `deserialize`, `unmarshal`. Fails the moment any deserializer lands.
4. `test_canonical_bytes_module_documents_single_point_hash_design` — substring pin on two load-bearing docstring phrases at `envoy/envelope/canonical_bytes.py:73-83`. Fails if either phrase is dropped.
5. `test_compiler_computes_canonical_bytes_and_content_hash_exactly_once` — real `EnvelopeCompiler.compile()`, then `is`-identity (NOT equality) across 3 reads. Fails if any read returns a freshly-allocated value (= recomputation).
6. `test_posture_gate_consumes_prior_content_hash_as_stored_attribute` — AST walk of `request_transition` body; every access to `envelope.envelope_id`, `envelope.prior_version`, `envelope.prior_content_hash`, `envelope.prior_posture_level` MUST be `ast.Attribute` not `ast.Call`. Fails if any becomes a method call that could re-derive.

Per `rules/probe-driven-verification.md`: each is a structural probe with a deterministic verdict. No regex on prose, no bag-of-words scoring, no LLM-judge surface.

### `PostureEnvelopeMutationInvariantError` — has `user_message`; plain-language

**Verdict**: Lines 440-444:

```python
self.user_message = (
    "There was a problem confirming the envelope update for this "
    "posture change. The change has not been recorded — please "
    "re-open Weekly Posture Review and try again."
)
```

`test_invariant_error_carries_user_message` (lines 1798-1807) explicitly asserts:

- `hasattr(err, "user_message")`
- `isinstance(err.user_message, str)`
- `len(err.user_message) > 0`
- `"envelope_id" not in err.user_message` (no jargon leak)
- `"diff_hash" not in err.user_message`
- `"sha256" not in err.user_message`

Matches `rules/communication.md` § "Report in Outcomes, Not Implementation" — the user-facing message frames the failure as "envelope update problem" + actionable recovery ("re-open Weekly Posture Review") without exposing the trust-boundary primitives.

---

## 5. NEW Findings Introduced By Shard 1 + Shard 2

**None.** Every Round 1 finding is closed. No new code paths introduced beyond the F-1/F-2/F-3/F-4/F-5 closure scope. No collateral regressions detected.

---

## 6. Same-Bug-Class Sweep — Round 1 Findings Carry-Forward

| Round 1 ID                                      | Carry-forward status                                                                                                                                                      |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F-001                                           | OPEN as Phase-03 issue #24 — by design. Round 2 confirms acceptance criteria are correctly scoped (covers both Ledger-transient and invariant-violation orphan triggers). |
| F-002                                           | CLOSED by removal + nosec assert.                                                                                                                                         |
| F-003 (test reaches `_audit_store`)             | Unchanged; INFO-only per Round 1 acceptance.                                                                                                                              |
| F-004 (test duplicates `_to_canonical_payload`) | Unchanged; INFO-only.                                                                                                                                                     |
| F-005 (2-of-4 ladder no-envelope tests missing) | Unchanged; tracked.                                                                                                                                                       |

---

## 7. Convergence Verdict

**APPROVE — convergence achieved on Round 2.**

- All 5 Round 1 HIGH findings (F-1, F-2, F-4, F-5, plus F-3 disposition) are structurally closed with regression-test locks.
- The 1 Round 1 MED (F-001) is correctly deferred via GitHub issue #24 with explicit acceptance criteria — the only structurally legitimate path because the fix exceeds one shard's load-bearing-logic budget per `autonomous-execution.md` § Per-Session Capacity Budget.
- The 1 Round 1 LOW (F-002) is closed structurally.
- The F-2 implementation is correct, well-tested, and fail-closed; the broader F-001 orphan-trigger surface it expands is already captured in issue #24's acceptance criteria.
- All 6 F-5 regression tests are probe-driven (AST walk + identity check + spec-text pin), not regex/keyword. They will catch the threat-model regressions Round 1 prescribed.
- 605 tests collect cleanly; 126 T-02-33-surface tests pass with zero WARN+ output.
- No cross-CLI artifact hygiene leaks in new journals 0022 / 0023 or in the `specs/envelope-model.md` edit.
- Cross-spec sibling re-derivation (`posture-ladder.md`, `ledger.md`, `shared-household.md`, `runtime-abstraction.md`, `cross-domain-flows.md`, `envelope-library.md`) shows zero drift on changed terms.
- `__all__` discipline maintained: `PostureEnvelopeMutationInvariantError` lands with both eager import AND `__all__` entry in `envoy/authorship/__init__.py`.

The 7-commit Shard 1 + Shard 2 delivery is **clean and may be considered the canonical closure of Round 1 /redteam**.

---

## 8. Cross-References

- `envoy/authorship/posture_gate.py` — lines 423-445 (`PostureEnvelopeMutationInvariantError`), 619-643 (`_is_posture_carrying_envelope`), 852-858 (Protocol check call site), 932-933 (Step 3e raise — sole envelope-None raise), 1022 (narrowing assert), 1032-1054 (F-2 invariants), 1065 (Step 5b append).
- `envoy/authorship/__init__.py` lines 33 (eager import) + 59 (`__all__` entry).
- `specs/envelope-model.md` line 96 (mint-state semantics + audit-only role paragraphs).
- `tests/tier1/test_posture_gate_5_step_fail_closed.py` — lines 1604-1623 (`_MutationOverrideEnvelope`), 1626-1813 (`TestStep5bMutationInvariantChecks`, 8 tests), 1821-1935 (`TestEnvelopeKwargProtocolCheck`, 6 tests), 1943-1998 (`TestPostureLevelMintStateRead`, 3 tests).
- `tests/tier2/test_posture_gate_wiring.py` lines 623-708 (`TestPostureChangeOnRatchetDownNoEnvelopeEdit`), 717-785 (`TestEnvelopePostureLevelIsMintStateOnRatchetUp`).
- `tests/tier2/test_envelope_hash_mint_time_cached.py` lines 115-358 (6 probe-driven regression tests).
- `workspaces/phase-01-mvp/journal/0022-DECISION-posture-level-mint-state-interpretation.md` — F-4 disposition.
- `workspaces/phase-01-mvp/journal/0023-DISCOVERY-envelope-hashes-mint-time-cached-f5-false-positive.md` — F-5 disposition.
- GitHub issue #24 — F-001 Phase-03 deferral with full acceptance criteria.
- `workspaces/phase-01-mvp/04-validate/round-1-code-review-2026-05-24.md` — origin findings.
- `workspaces/phase-01-mvp/04-validate/round-1-security-audit-2026-05-24.md` — F-1 through F-6 security disposition.
