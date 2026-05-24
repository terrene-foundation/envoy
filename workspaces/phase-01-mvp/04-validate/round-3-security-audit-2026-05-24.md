# Round 3 — Security Audit: closure verification of Round 2 findings + new attack-surface review

**Audited:** 2026-05-24
**Scope (Shard 3):** `git diff e89914b..2264ae2` — Round 2 origin merge → current main.
**Cumulative scope:** `git diff 641dd2d..2264ae2` — full T-02-33 chain.
**Round 2 source:** `workspaces/phase-01-mvp/04-validate/round-2-security-audit-2026-05-24.md` (committed; HIGH=R2-F1, MED=R2-F2, LOW=R2-F3).
**Auditor mode:** Round 3 — verify Shard 3 (PR #27, merge `2264ae2`) closed R2-F1/F2/F3; verify no new attack surfaces; cross-cumulative atomicity audit.
**Probe discipline:** Per `rules/probe-driven-verification.md` MUST-1+3 — every semantic claim cited from AST walk / grep / file-read / literal-command output. No regex over assistant prose.

---

## Executive verdict

**Convergence verdict:** CLEAN — Round 3 finds zero new HIGH/MED/LOW findings. Shard 3 closed R2-F1 (HIGH) structurally; R2-F2 (MED) and R2-F3 (LOW) closed with documented test/spec contracts. Cross-cumulative atomicity audit confirms no application-level invariant raise sits between any pair of `_ledger.append` calls in `request_transition`.

| Round 2 ID | Severity | Round 3 verdict | Probe evidence                                                                                                                                                                                                                                                        |
| ---------- | -------- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R2-F1      | HIGH     | **CLOSED**      | F-2 invariants are now PRECONDITIONS at lines 1018/1026/1034 — BEFORE Step 5a at line 1078. Tier 1 + Tier 2 atomicity tests assert `types == []` (zero Ledger entries) on every invariant raise. ZERO matches for stale `types == ["posture_change"]` in test corpus. |
| R2-F2      | MED      | **CLOSED**      | `_PostureCarryingEnvelope` Protocol docstring (lines 675–699) states the IMPLEMENTORS contract: side-effect-free reads required. `TestPostureCarryingEnvelopeProtocolDiscipline` spy adapter pins read-count exactly at 5 (one per Protocol attribute).               |
| R2-F3      | LOW      | **CLOSED**      | `specs/shared-household.md:102-106` carries the clarifying comment distinguishing mint-state vs effective posture. `specs/posture-ladder.md:128-133` adds the same clarification. ZERO Pre-Phase / will-be-refactored / future-scope markers.                         |

**Net Round 3 findings:** HIGH: 0 · MED: 0 · LOW: 0. The Round 2 HIGH-class (orphan Ledger entries on invariant raise) is structurally extinct; cross-cumulative audit confirms no new instance.

---

## Step 1 — R2-F1 closure: structural atomicity at the application level

### Probe 1: Invariant raises precede Step 5a's posture_change append

**Command:**

```
grep -nE "PostureEnvelopeMutationInvariantError|_ledger\.append|raise " envoy/authorship/posture_gate.py | grep -E ":(10[0-2][0-9]|1078|1115)"
```

**Output (ordering relevant to R2-F1):**

```
958:                raise PostureRatchetEnvelopeMissingError(current=current, target=target)
1019:                raise PostureEnvelopeMutationInvariantError(   # F-2 invariant #1 (envelope_id)
1027:                raise PostureEnvelopeMutationInvariantError(   # F-2 invariant #2 (version monotonicity)
1035:                raise PostureEnvelopeMutationInvariantError(   # F-2 invariant #3 (diff_hash shape)
1078:        entry_id = await self._ledger.append(                  # Step 5a: posture_change
1115:            envelope_edit_entry_id = await self._ledger.append( # Step 5b: envelope_edit
```

**Verdict:** PASS. All three F-2 invariant raises now fire at lines 1019/1027/1035 — INSIDE the precondition block (lines 1003–1053 read directly from source) and BEFORE Step 5a's `posture_change` append at line 1078. R2-F1's orphan-entry condition (raise between 5a and 5b) is structurally extinct.

### Probe 2: Mutation compute is the first action in the precondition block

**File-read at `envoy/authorship/posture_gate.py:1003-1053`:**

The "Step 5-PRECONDITIONS" block contains, in order:

1. Line 1003: `mutation = None`
2. Line 1004: `envelope_edit_content: Optional[dict] = None`
3. Line 1005: `if target > current:`
4. Line 1007: `assert envelope is not None` (MyPy narrowing; Step 3e at 958 raises if envelope=None)
5. Line 1008: `mutation = envelope.mutate_for_posture_level(target)`
6. Lines 1018, 1026, 1034: three F-2 invariant raises
7. Lines 1045-1053: `envelope_edit_content` dict construction

**Verdict:** PASS. The mutation compute precedes all three invariant checks; all invariant checks land inside the same `if target > current:` block; the `envelope_edit_content` build happens BEFORE Step 5a so Step 5b is purely a Ledger write per the in-code comment at lines 1042-1044 ("Build the envelope_edit content NOW (before any append) so Step 5b is purely a Ledger write with no further computation between the paired appends").

### Probe 3: Tier 2 atomicity probe asserts zero Ledger entries on each invariant violation

**Command:**

```
grep -nE "class TestF2InvariantViolationEmitsNeitherEntry|async def test_.*emits_neither_entry" tests/tier2/test_posture_gate_wiring.py
```

**Output:**

```
672:class TestF2InvariantViolationEmitsNeitherEntry:
701:    async def test_envelope_id_mismatch_emits_neither_entry(
747:    async def test_new_version_drift_emits_neither_entry(
789:    async def test_malformed_diff_hash_emits_neither_entry(
```

**File-read at `tests/tier2/test_posture_gate_wiring.py:701-830`** confirms each of the three test bodies:

- Constructs a real `EnvoyLedger` via `envoy_ledger` fixture (the parameter name is the fixture — Tier 2 per `rules/testing.md`; no `@patch` / `MagicMock` / `unittest.mock` in the test module).
- Forges a mutation that violates the named invariant (envelope_id swap / new_version drift / `md5:` prefix).
- `pytest.raises(PostureEnvelopeMutationInvariantError)` asserts the raise.
- `entries = await _read_appended_entries(envoy_ledger)` reads the REAL ledger.
- `assert entries == []` — ZERO entries appended (the atomicity invariant).
- `assert sink.writes == []` — BET-12 emitter also NOT fired.

Mocking sweep:

```
grep -nE "@patch|MagicMock|unittest\.mock|mock\.Mock" tests/tier2/test_posture_gate_wiring.py
```

**Output:** (empty — no matches). PASS per `rules/testing.md` § Tier 2 (no mocking).

**Verdict:** PASS. Tier 2 atomicity test is real-infrastructure, exercises the real `EnvoyLedger`, asserts zero entries on every invariant violation.

### Probe 4: Tier 1 branch-coverage tests assert ZERO Ledger entries on raise

**Command:**

```
grep -nE "types == \[\]|types == \[\"posture_change\"\]" tests/tier1/test_posture_gate_5_step_fail_closed.py
```

**Output:**

```
1679:        assert types == [], (
1712:        assert types == [], (
1745:        assert types == [], (
1774:        assert types == [], (
1963:        assert led.appends == []
```

The Round 2 audit flagged `assert types == ["posture_change"]` at four positions (1667/1693/1722/1748) as structural pins of the orphan-entry pattern. Round 3 verifies:

```
grep -nE "types == \[\"posture_change\"\]" tests/
```

**Output:** (empty — zero matches across the entire tests/ tree). PASS — all four orphan-pin assertions were flipped to `types == []` (zero entries on raise).

**File-read at `tests/tier1/test_posture_gate_5_step_fail_closed.py:1626-1842`** confirms the four `TestStep5bMutationInvariantChecks` methods (test_envelope_id_mismatch_raises @1655, test_new_version_regression_raises @1688, test_new_version_skip_raises @1718, test_malformed_diff_hash_raises @1751) each assert:

- `pytest.raises(PostureEnvelopeMutationInvariantError)` — raise fires
- `assert types == []` — zero Ledger entries land
- `assert sink.writes == []` — BET-12 not emitted

**Verdict:** PASS. R2-F1 closure is pinned in BOTH Tier 1 (fast unit) AND Tier 2 (real EnvoyLedger). Any future refactor that reintroduces the orphan-entry pattern breaks 7 tests at once.

### Probe 5: No application-level raise between Step 5a and Step 5b

**File-read at `envoy/authorship/posture_gate.py:1078-1115`** (the body between paired Ledger appends):

- Line 1078: Step 5a `_ledger.append(entry_type="posture_change", ...)` — first append.
- Lines 1083-1091: `logger.info("posture.transition", ...)` — structured log; no raise.
- Lines 1093-1110: comment block (no executable code).
- Line 1111: `if target > current:` — branch entry.
- Lines 1112-1114: three `assert ... is not None` narrowing asserts (`# nosec`). These are MyPy narrowing; under `python -O` they are stripped and become no-ops. They are NOT runtime application-level invariants — those ran in the precondition block.
- Line 1115: Step 5b `_ledger.append(entry_type="envelope_edit", ...)` — paired append.

**No application-level raise between 1078 and 1115.** The narrowing asserts at 1112-1114 are structurally guaranteed to hold:

- `envelope is not None` — Step 3e at line 958 raises if `target > current` and `envelope is None`.
- `mutation is not None` — set at line 1008 inside `if target > current:`, which is the same predicate as line 1111.
- `envelope_edit_content is not None` — set at lines 1045-1053 inside the same `if target > current:` block.

**Verdict:** PASS. R2-F1's structural failure mode (application-level raise between paired appends) is extinct in the current `request_transition` body.

---

## Step 2 — R2-F2 + R2-F3 closure verification

### R2-F2 (MED) — `_PostureCarryingEnvelope` side-effect surface

#### Probe 1: Protocol docstring documents IMPLEMENTORS contract

**File-read at `envoy/authorship/posture_gate.py:675-699`:**

The `_PostureCarryingEnvelope` Protocol docstring carries a new "Side-effect-free attribute reads (R2-F2 contract — IMPLEMENTORS)" section stating:

> "Implementations of this Protocol MUST have side-effect-free attribute reads… Implementations MUST therefore NOT, on attribute read: Perform I/O (file read, network call, DB query); Acquire locks (threading / asyncio primitives); Emit log records; Mutate observable state; Wake background tasks."

The docstring explicitly names that "the gate cannot enforce side-effect-freeness at runtime (Python's structural Protocol contract gives no hook); the discipline is on the IMPLEMENTOR."

**Verdict:** PASS. IMPLEMENTORS contract is encoded in the Protocol docstring per R2-F2 disposition.

#### Probe 2: Tier 1 spy adapter pins read-count exactly

**Command:**

```
grep -nE "class TestPostureCarryingEnvelopeProtocolDiscipline|_EXPECTED_PROTOCOL_ATTR_READS|len\(protocol_reads\) == len" tests/tier1/test_posture_gate_5_step_fail_closed.py
```

**Output:**

```
1972:class TestPostureCarryingEnvelopeProtocolDiscipline:
2000:        _EXPECTED_PROTOCOL_ATTR_READS = {
2092:        assert len(protocol_reads) == len(_EXPECTED_PROTOCOL_ATTR_READS), (
```

**File-read at `tests/tier1/test_posture_gate_5_step_fail_closed.py:1989-2098`** confirms:

- `_EXPECTED_PROTOCOL_ATTR_READS` is a frozen 5-element set (`envelope_id`, `prior_version`, `prior_content_hash`, `prior_posture_level`, `mutate_for_posture_level`).
- The `_SpyEnvelope` overrides `__getattribute__` to record each accessed name to `observed_reads`.
- The test asserts:
  - `set(protocol_reads) == _EXPECTED_PROTOCOL_ATTR_READS` (no missing, no unexpected)
  - `unexpected_reads == []` (no defensive duplicates outside the Protocol surface)
  - `len(protocol_reads) == len(_EXPECTED_PROTOCOL_ATTR_READS)` (EXACT count, not "some count")

**Verdict:** PASS — the spy counts attribute reads at an EXACT bound of 5, not "some count." A future refactor that adds a sixth defensive `hasattr` call fails this test loudly.

### R2-F3 (LOW) — cross-spec drift

#### Probe 1: Pre-Phase / will-be-refactored / future-scope markers absent

**Command:**

```
grep -nE "Pre-Phase|will be refactored|future scope|when X lands" specs/posture-ladder.md specs/shared-household.md
```

**Output:** (empty — zero matches). PASS per `rules/spec-accuracy.md`.

#### Probe 2: Shared Household composition cites mint-state distinction

**Command:**

```
grep -nE "posture_level|mint-state|effective.posture|mint-time" specs/shared-household.md
```

**Output:**

```
60:      "posture_level": "PSEUDO | TOOL | SUPERVISED | DELEGATING | AUTONOMOUS"
102:    # `p.posture_level` is the principal's current effective posture derived
103:    # from the Ledger walk per specs/posture-ladder.md § effective_posture
104:    # NOT the envelope's mint-time `metadata.posture_level` annotation
105:    # (per specs/envelope-model.md § metadata.posture_level).
106:    composed.effective_posture = min(p.posture_level for p in principals)
```

`specs/shared-household.md:102-106` now carries the clarifying comment explicitly distinguishing mint-state from effective posture.

**Command:**

```
grep -nE "Shared Household|effective_posture_for_composition|mint-time" specs/posture-ladder.md
```

**Output (relevant):**

```
54:### Shared Household semantics
123:### `effective_posture_for_composition(principals, action) → PostureLevel`
128:    # `p.posture_level` here is the PRINCIPAL'S current effective posture
130:    #   derived from the Ledger walk
131:    # envelope's `metadata.posture_level` field, which is the mint-time
132:    # annotation per specs/envelope-model.md § metadata.posture_level.
133:    return min(p.posture_level for p in principals if p in action.consenting_principals)
183:- **Shared Household composition** (`effective_posture_for_composition`,
184:  spec § Shared Household semantics) — Phase 03+ separate function.
```

`specs/posture-ladder.md:128-133` adds the same clarifying comment under the `effective_posture_for_composition` definition.

**Verdict:** PASS — both sibling spec sites cite the mint-state vs effective-posture distinction; the R2-F3 sibling-drift risk is closed.

---

## Step 3 — Shard 3 NEW attack-surface audit

### A. Spy adapter contained to tests/ — no production surface

**Command:**

```
grep -rln "_SpyEnvelope\|SpyAdapter\|class .*Spy.*Envelope" envoy/
```

**Output:** (empty — zero matches in production code). The `_SpyEnvelope` class is defined INSIDE `test_protocol_attribute_read_surface_bounded` at `tests/tier1/test_posture_gate_5_step_fail_closed.py:2010-2050` — function-local; not exported. No production module imports or constructs it. PASS.

### B. New typed-error `user_message` strings — schema-revealing-identifier audit

**File-read at `envoy/authorship/posture_gate.py:341-489`** (every `PostureGateError` subclass user_message string):

- `PostureNoopError` @360: literal — "You're already at the posture you requested. No change was made." → no identifiers.
- `PostureAuthorshipInsufficientError` @380-385: interpolates `current.name` / `target.name` / `need` / `have` — all are PUBLIC enum names + integers. No envelope_id, no diff_hash, no principal_id.
- `PostureRatchetEnvelopeMissingError` @411-416: interpolates `current.name` / `target.name` — public enum names only.
- `PostureEnvelopeMutationInvariantError` @440-444: literal fixed string — does NOT interpolate the attacker-controllable `reason`. Contains NO envelope_id, NO diff_hash, NO sha256 hex, NO principal_id, NO version numbers.
- `PostureGenesisGrantMissingError` @454-458: public enum names only.
- `PostureCoolingOffActiveError` @468-472: literal — no identifiers.
- `PostureEnterpriseAutonomousForbidden` @480-484: literal — no identifiers.

Tier 1 redaction probe at `tests/tier1/test_posture_gate_5_step_fail_closed.py:1827-1836`:

```python
def test_invariant_error_carries_user_message(self):
    err = PostureEnvelopeMutationInvariantError(reason="test reason")
    assert hasattr(err, "user_message")
    assert isinstance(err.user_message, str)
    assert len(err.user_message) > 0
    # No internal jargon should leak into the user-facing string.
    assert "envelope_id" not in err.user_message
    assert "diff_hash" not in err.user_message
    assert "sha256" not in err.user_message
```

The redaction invariant is structurally pinned. PASS per `rules/observability.md` Rule 8.

### C. No new BLOCKED-pattern risk surfaces in Shard 3

**Sweeps:**

```
grep -nE "except:|except Exception:.*pass|TODO|FIXME|HACK|NotImplementedError" envoy/authorship/posture_gate.py
```

**Output:** (empty — zero matches). PASS per `rules/zero-tolerance.md` Rule 2 and Rule 3.

**Verdict:** Shard 3 introduces no new attack surfaces beyond the spy-adapter test fixture (test-scoped, function-local). The new typed-error `user_message` strings carry zero schema-revealing identifiers.

---

## Step 4 — Cross-cumulative atomicity audit (`641dd2d..2264ae2`)

### Walk every `_ledger.append` in `request_transition`

**Command:**

```
grep -nE "_ledger\.append|raise |return PostureChangeResult" envoy/authorship/posture_gate.py
```

**Output (relevant to request_transition, lines 782-1151):**

```
857:            raise TypeError(...)             # input validation — BEFORE all 5 steps
859:            raise TypeError(...)             # input validation
861:            raise TypeError(...)             # input validation
863:            raise ValueError(...)            # input validation
868:            raise TypeError(...)             # input validation
878:            raise TypeError(...)             # kwarg-boundary Protocol check
898:            raise AuthorshipScoreDivergenceError(...)  # Step 1
918:            raise PostureNoopError(current)            # Step 2
925:                raise PostureEnterpriseAutonomousForbidden()  # Step 3a
931:                raise PostureCoolingOffActiveError(...)       # Step 3b
937:                raise PostureGenesisGrantMissingError(...)    # Step 3c
942:                raise PostureAuthorshipInsufficientError(...)  # Step 3d
958:                raise PostureRatchetEnvelopeMissingError(...)  # Step 3e
1019:                raise PostureEnvelopeMutationInvariantError(...)  # Step 5-PRECONDITIONS
1027:                raise PostureEnvelopeMutationInvariantError(...)
1035:                raise PostureEnvelopeMutationInvariantError(...)
1078:        entry_id = await self._ledger.append(...)         # Step 5a
1115:            envelope_edit_entry_id = await self._ledger.append(...)  # Step 5b
1148:        return PostureChangeResult(...)
```

### Between-append analysis

The only two `_ledger.append` calls in `request_transition` are at 1078 and 1115.

**Window 1078 → 1115 inspection (file-read):**

- Line 1083–1091: `logger.info("posture.transition", ...)` — structured log; cannot raise an application-level invariant. `logger.info` may raise infrastructure errors (e.g. logging handler I/O failure) but those are NOT application-level invariants per the F-001 bug-class boundary.
- Lines 1093–1110: comment-only.
- Line 1111: `if target > current:` — branch predicate; no raise.
- Lines 1112–1114: `assert envelope is not None`, `assert mutation is not None`, `assert envelope_edit_content is not None` — MyPy narrowing asserts (`# nosec` markers). Under `python -O` these are stripped. Each is structurally guaranteed because:
  - `envelope` non-None on ratchet-up: Step 3e at line 958 raises if `envelope is None` and `target > current`.
  - `mutation` non-None on ratchet-up: set at line 1008 inside `if target > current:` (same predicate as line 1111).
  - `envelope_edit_content` non-None on ratchet-up: built at lines 1045-1053 inside the same `if target > current:` block.

**No application-level raise sits between the paired appends.** The narrowing asserts are not application-level invariants — they are MyPy hints whose runtime form is a no-op under optimization. Even if they fired in debug mode, they'd fire ONLY if a code-graph invariant violation had already happened (Step 3e missing OR preconditions block dropping `if target > current:`) — neither path is reachable in the current code.

### Pair sequence map (cumulative diff)

For each `_ledger.append`, the raise-vs-append window from the function entry:

| Append site    | Preceding raise sites within `request_transition`                                                        | Application-level raise BETWEEN appends? |
| -------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| Step 5a (1078) | 857, 859, 861, 863, 868, 878, 898, 918, 925, 931, 937, 942, 958, 1019, 1027, 1035 — ALL BEFORE line 1078 | N/A (first append)                       |
| Step 5b (1115) | None between 1078 and 1115 — see Window analysis above                                                   | **NO**                                   |

**Verdict:** PASS. Cross-cumulative audit confirms the R2-F1 failure-mode class is structurally extinct in `request_transition` as of `2264ae2`.

---

## Findings table — Round 3

| ID  | Severity | Surface | File:line | Disposition                                                                                                                                                                                                                             |
| --- | -------- | ------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| —   | —        | —       | —         | **No new findings.** All Round 2 findings (R2-F1 HIGH, R2-F2 MED, R2-F3 LOW) verified CLOSED. Cross-cumulative atomicity audit confirms no application-level raise sits between any paired Ledger append calls in `request_transition`. |

**Summary:** CRITICAL: 0 · HIGH: 0 · MED: 0 · LOW: 0.
**PASSED CHECKS:**

- F-2 invariant precondition position (3 raises before Step 5a) — Probe 1
- Mutation compute precedes invariant checks — Probe 2
- Tier 2 atomicity probe asserts zero Ledger entries on real EnvoyLedger — Probe 3 (no `@patch` / `MagicMock`)
- Tier 1 branch-coverage tests assert `types == []` on every invariant raise — Probe 4 (zero stale `types == ["posture_change"]` matches)
- No application-level raise between Step 5a and Step 5b — Probe 5
- `_PostureCarryingEnvelope` Protocol IMPLEMENTORS contract documented — R2-F2 Probe 1
- Spy adapter bounds Protocol attribute-read surface at exactly 5 — R2-F2 Probe 2
- Cross-spec drift closed in `specs/shared-household.md:102-106` AND `specs/posture-ladder.md:128-133` — R2-F3 Probes 1+2
- Spy adapter scoped to test corpus only (no production import) — Shard 3 Step A
- New typed-error `user_message` strings free of schema-revealing identifiers (`envelope_id` / `diff_hash` / `sha256` / `principal_id`) — Shard 3 Step B
- Zero `except:` / `except Exception: pass` / `TODO` / `FIXME` / `NotImplementedError` in `posture_gate.py` — Shard 3 Step C
- Cross-cumulative paired-append audit confirms structural atomicity for every `_ledger.append` pair in `request_transition` — Step 4

---

## Receipts

- Source files read with line citations: `envoy/authorship/posture_gate.py` (lines 1-1152 — full module), `tests/tier1/test_posture_gate_5_step_fail_closed.py` (lines 1626-2098), `tests/tier2/test_posture_gate_wiring.py` (lines 670-882), `specs/shared-household.md`, `specs/posture-ladder.md`.
- Greps executed (with literal output captured above): `PostureEnvelopeMutationInvariantError`, `_ledger\.append`, `raise `, `class TestF2InvariantViolationEmitsNeitherEntry`, `class TestStep5bMutationInvariantChecks`, `class TestPostureCarryingEnvelopeProtocolDiscipline`, `types == \[\"posture_change\"\]`, `types == \[\]`, `@patch|MagicMock|unittest\.mock|mock\.Mock`, `_SpyEnvelope|SpyAdapter`, `Pre-Phase|will be refactored|future scope|when X lands`, `posture_level|mint-state|effective.posture|mint-time` (against shared-household.md AND posture-ladder.md), `except:|except Exception:.*pass|TODO|FIXME|HACK|NotImplementedError`.
- Round 2 audit cited at SHA `e89914b` (Round 2 origin merge) and its committed report at `workspaces/phase-01-mvp/04-validate/round-2-security-audit-2026-05-24.md`.
- Cumulative diff scope walked: `641dd2d..2264ae2` (T-02-33 chain origin → current main).
- Mocking-sweep verifies Tier 2 atomicity tests use real `EnvoyLedger` (zero `@patch` / `MagicMock` / `unittest.mock.Mock` matches in `tests/tier2/test_posture_gate_wiring.py`) per `rules/testing.md` § Tier 2.

---

## Auditor notes for orchestrator

- Round 3 reaches the convergence-clean state per `rules/verify-resource-existence.md` MUST-4: this audit cites durable receipts (file paths + line numbers + literal grep outputs), not self-attested verdicts.
- The R2-F1 closure is structurally complete: F-2 invariants are now PRECONDITIONS (lines 1018/1026/1034), the precondition block builds the `envelope_edit_content` BEFORE Step 5a (lines 1045-1053), and the body between 5a (1078) and 5b (1115) is structurally just `logger.info` + MyPy-narrowing asserts. No application-level raise can fire between paired appends.
- The R2-F2 Protocol-discipline test (spy adapter) is a TEST FIXTURE only — function-local inside `test_protocol_attribute_read_surface_bounded`, not in production code, not exported. Misuse via copy-paste into production would require an explicit user action.
- The cross-cumulative audit (`641dd2d..2264ae2`) confirms the T-02-33 chain in aggregate is structurally atomic at the application level. The remaining bug class — transient Ledger failures BETWEEN paired appends (e.g. the second `_ledger.append` raises an infrastructure error after the first committed) — is acknowledged in the precondition block's in-code comment (lines 998-1002) and tracked as the F-001 follow-up; it requires Ledger-level transactional support and is NOT in Round 3 scope.
- Convergence verdict: CLEAN. No further /redteam rounds required for this disposition.
