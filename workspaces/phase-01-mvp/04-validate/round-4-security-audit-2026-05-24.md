# Round 4 — Security Audit: confirm Round 3 verdict reproduces; fresh-eyes attack-surface re-scan

**Audited:** 2026-05-24
**Scope (this round):** Re-verify Round 3 against current `main = 2264ae2` from scratch — no trust of prior round outputs per `rules/testing.md` § Audit Mode.
**Cumulative scope:** `git diff 641dd2d..2264ae2` — full T-02-33 chain.
**Round 3 source:** `workspaces/phase-01-mvp/04-validate/round-3-security-audit-2026-05-24.md` (CLEAN verdict, 0 findings).
**Auditor mode:** Round 4 — convergence-confirmation pass. Per `rules/probe-driven-verification.md` MUST-1+3, every semantic claim is cited from AST walk / grep / literal-command output / file-read; no regex over assistant prose.

---

## Executive verdict

**Convergence verdict:** CLEAN — Round 4 reproduces Round 3 deterministically. Zero new findings. The Round 2 HIGH-class (orphan Ledger entries on F-2 invariant raise) remains structurally extinct. R2-F2 (MED) and R2-F3 (LOW) closures stable. No new attack surfaces surfaced under fresh attention.

**Stability check:** PASS. Every Round 3 security claim re-derives to the same verdict against `2264ae2` with no drift.

| Round 2 ID | Severity | Round 3 verdict | Round 4 re-verify       | Probe evidence (independent re-derivation)                                                                                                                                                                                                                                                                                                                                              |
| ---------- | -------- | --------------- | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | ------------ | ---------------------------- |
| R2-F1      | HIGH     | CLOSED          | **CLOSED — reproduces** | F-2 invariant raises at lines 1019/1027/1035 PRECEDE Step 5a at line 1078 (Probe 1). Mutation compute + invariant block at 1003-1053 PRECEDES Step 5a (Probe 2). Tier 2 atomicity probe asserts `entries == []` via real `EnvoyLedger` (Probe 3). Tier 1 branch-coverage asserts `types == []` at four positions (Probe 4). No application-level raise between 1078 and 1115 (Probe 5). |
| R2-F2      | MED      | CLOSED          | **CLOSED — reproduces** | `_PostureCarryingEnvelope` Protocol docstring at lines 675-699 carries IMPLEMENTORS contract. Spy-adapter test bounds gate's attribute-read surface at exactly 5. `_SpyEnvelope` function-local at line 2010 of test_posture_gate_5_step_fail_closed.py (NOT exported, NOT production-importable).                                                                                      |
| R2-F3      | LOW      | CLOSED          | **CLOSED — reproduces** | `specs/shared-household.md:102-106` and `specs/posture-ladder.md:128-133` both carry the present-tense mint-state vs effective-posture clarification. Zero matches for `Pre-Phase                                                                                                                                                                                                       | will be refactored | future scope | when X lands`across`specs/`. |

**Net Round 4 findings:** HIGH: 0 · MED: 0 · LOW: 0.

---

## Step 1 — R2-F1 atomicity re-verification (fresh probes against `2264ae2`)

### Probe 1: F-2 invariant raises precede Step 5a's posture_change append

**Command (re-run, fresh):**

```
grep -nE "_ledger\.append" envoy/authorship/posture_gate.py
```

**Output:**

```
envoy/authorship/posture_gate.py:1078:        entry_id = await self._ledger.append(
envoy/authorship/posture_gate.py:1115:            envelope_edit_entry_id = await self._ledger.append(
```

**Command:**

```
grep -nE "PostureEnvelopeMutationInvariantError" envoy/authorship/posture_gate.py
```

**Output (within `request_transition` body, lines 1003-1053):**

- Line 1019: `raise PostureEnvelopeMutationInvariantError(` (envelope_id mismatch)
- Line 1027: `raise PostureEnvelopeMutationInvariantError(` (new_version monotonicity)
- Line 1035: `raise PostureEnvelopeMutationInvariantError(` (diff_hash shape via `_SHA256_HEX_PATTERN.fullmatch`)

**Verdict:** PASS — line numbers, raise sites, and ordering reproduce Round 3 exactly. All three invariant raises fire BEFORE Step 5a at line 1078.

### Probe 2: Mutation compute is the first action in the precondition block

**File-read at `envoy/authorship/posture_gate.py:1003-1053` (lines re-read fresh):**

1. Line 1003: `mutation = None`
2. Line 1004: `envelope_edit_content: Optional[dict] = None`
3. Line 1005: `if target > current:`
4. Line 1007: `assert envelope is not None  # nosec` (MyPy narrowing)
5. Line 1008: `mutation = envelope.mutate_for_posture_level(target)`
6. Lines 1018-1041: three F-2 invariant checks with raises at 1019/1027/1035
7. Lines 1042-1053: `envelope_edit_content` built BEFORE Step 5a (per in-code comment 1042-1044: "Build the envelope_edit content NOW (before any append) so Step 5b is purely a Ledger write with no further computation between the paired appends")

**Verdict:** PASS — reproduces Round 3.

### Probe 3: Tier 2 atomicity probe asserts zero Ledger entries on real `EnvoyLedger`

**Command:**

```
grep -nE "class TestF2InvariantViolationEmitsNeitherEntry|async def test_.*emits_neither_entry" tests/tier2/test_posture_gate_wiring.py
```

**Re-run gives (fresh):**

```
672:class TestF2InvariantViolationEmitsNeitherEntry:
701:    async def test_envelope_id_mismatch_emits_neither_entry(
747:    async def test_new_version_drift_emits_neither_entry(
789:    async def test_malformed_diff_hash_emits_neither_entry(
```

**Mocking sweep (re-run):**

```
grep -nE "@patch|MagicMock|unittest\.mock|mock\.Mock" tests/tier2/test_posture_gate_wiring.py
```

**Output:**

```
15:NO mocking (`@patch`, `MagicMock`, `unittest.mock` — BLOCKED). The
630:    `@patch`/`MagicMock`): this is a REAL adapter — a malicious-shape
```

Both hits are **inside docstrings** (line 15: module docstring stating contract; line 630: class docstring stating contract for `_MaliciousMutationCarrier`). Neither is an actual `@patch` decorator or `MagicMock()` constructor call. **No executable mocking in tests/tier2/test_posture_gate_wiring.py.** PASS per `rules/testing.md` § Tier 2.

**Verdict:** PASS — reproduces Round 3.

### Probe 4: Tier 1 branch-coverage tests assert `types == []` on every invariant raise

**Command (re-run fresh):**

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

**Command (cross-tree re-sweep for stale-orphan pattern):**

```
grep -nE "types == \[\"posture_change\"\]" tests/
```

**Output:** (empty — zero matches across `tests/`). PASS — stale orphan-pin pattern remains structurally extinct.

**Verdict:** PASS — reproduces Round 3.

### Probe 5: No application-level raise between Step 5a (1078) and Step 5b (1115)

**File-read at `envoy/authorship/posture_gate.py:1078-1115` (re-read fresh):**

- Line 1078: Step 5a `_ledger.append(entry_type="posture_change", ...)` — first append.
- Lines 1083-1091: `logger.info("posture.transition", ...)` — structured log; not an application-level raise.
- Lines 1093-1110: comment block (no executable code).
- Line 1111: `if target > current:` — branch predicate; no raise.
- Lines 1112-1114: `assert envelope is not None` / `assert mutation is not None` / `assert envelope_edit_content is not None` — three MyPy narrowing asserts marked `# nosec — narrowing`. Each is structurally guaranteed:
  - `envelope is not None`: Step 3e at line 958 raises if `envelope is None` AND `target > current`.
  - `mutation is not None`: assigned at line 1008 inside `if target > current:` (the same predicate as line 1111).
  - `envelope_edit_content is not None`: assigned at lines 1045-1053 inside the same `if target > current:` block.
- Line 1115: Step 5b `_ledger.append(entry_type="envelope_edit", ...)` — paired append.

**No application-level raise sits between lines 1078 and 1115.** The narrowing asserts at 1112-1114 are MyPy hints; under `python -O` they are stripped to no-ops. Even in non-optimized runs they can only fire if a structural code-graph invariant has already been violated (Step 3e absent OR `if target > current:` predicate dropped) — neither path is reachable.

**Verdict:** PASS — reproduces Round 3.

---

## Step 2 — Cross-cumulative atomicity audit (`641dd2d..2264ae2`) re-walk

### `_ledger.append` enumeration in `envoy/`

**Command:**

```
grep -rn "_ledger\.append\|ledger\.append" envoy/
```

**Output:**

```
envoy/authorship/posture_gate.py:1078:        entry_id = await self._ledger.append(
envoy/authorship/posture_gate.py:1115:            envelope_edit_entry_id = await self._ledger.append(
```

The only two `_ledger.append` call sites under `envoy/` are inside `PostureGate.request_transition` at lines 1078 (Step 5a) and 1115 (Step 5b). There are NO other downstream Ledger append sites in the call graph reachable from `request_transition` that could orphan a prior entry — the BET-12 emit at line 1140 is a downstream call to `BET12CadenceEmitter.emit` (not `_ledger.append`), so a raise inside `bet12_emitter.emit` would NOT orphan a Ledger entry (both posture_change AND envelope_edit have already committed by then). This is the intended atomicity boundary per `journal/0024:64-66` (F-001 is the separate transient-Ledger-failure bug class).

### Window analysis for every paired append

| Pair      | Sites                 | Between-raise audit                                                                                                                                                     |
| --------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 5a → 5b   | 1078 → 1115           | NONE. Comments, `logger.info`, `if target > current:` predicate, three `# nosec` narrowing asserts. No application-level raise.                                         |
| 5b → emit | 1115 → 1140 (BET-12)  | `logger.info("posture.envelope_edit", ...)` at lines 1119-1128. No raise. Even if BET-12 emit raised, both Ledger entries would have already committed — NOT an orphan. |
| Pre-5a    | function-entry → 1078 | 16 raise sites (input validation, kwarg-boundary, Step 1-3 gates, F-2 preconditions). All are PRECONDITIONS — they raise BEFORE any Ledger append.                      |

**Verdict:** PASS. Cross-cumulative audit confirms R2-F1's failure-mode class is structurally extinct across the full `641dd2d..2264ae2` cumulative diff scope.

### Downstream Ledger-append risk (the F-001 boundary)

Per the in-code comment at lines 998-1002:

> "Note: this closure addresses APPLICATION-level invariant violations (mutation result shape). TRANSIENT Ledger failures BETWEEN Step 5a and Step 5b (e.g. the second append raises mid-pair) are a different bug class and require Ledger-level transactional support; tracked at the F-001 follow-up issue."

This is acknowledged as out-of-scope for Round 4 (per `journal/0024:64-66`). Confirmed: NO additional `_ledger.append` call sites exist outside `posture_gate.py` that could orphan paired entries; the Ledger's own `EnvoyLedger.append` is single-row atomic (wrapped in `df.transaction()` per `envoy/ledger/hash_chain.py:11`). The remaining transient-failure bug class is at the per-Ledger-append boundary, NOT the application-pairing boundary.

---

## Step 3 — Stability check (Round 3 claims re-derive deterministically)

Every Round 3 claim re-verified against `2264ae2`:

| Round 3 claim                                                                         | Round 4 re-derivation                                                                                                                     | Reproducible? |
| ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ----------------------- | ------------------- | --- |
| F-2 invariant raises at 1019/1027/1035                                                | Grep confirms exact line nums                                                                                                             | YES           |
| Step 5a at 1078, Step 5b at 1115                                                      | Grep confirms exact line nums                                                                                                             | YES           |
| `_SHA256_HEX_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")` at line 101              | File-read confirms                                                                                                                        | YES           |
| Mutation compute precedes invariant checks at 1008                                    | File-read confirms                                                                                                                        | YES           |
| `envelope_edit_content` built at lines 1045-1053 BEFORE Step 5a                       | File-read confirms                                                                                                                        | YES           |
| Four Tier 1 `assert types == []` at 1679/1712/1745/1774                               | Grep confirms exact line nums                                                                                                             | YES           |
| Zero matches for stale `types == ["posture_change"]` across `tests/`                  | Grep confirms empty                                                                                                                       | YES           |
| Zero `@patch`/`MagicMock` executable calls in tests/tier2/test_posture_gate_wiring.py | Grep confirms (both hits are docstrings)                                                                                                  | YES           |
| `_SpyEnvelope` is function-local at test line 2010                                    | Grep confirms (only match in tests/)                                                                                                      | YES           |
| Zero `_SpyEnvelope` matches in `envoy/`                                               | Grep confirms empty                                                                                                                       | YES           |
| `specs/shared-household.md:102-106` carries mint-state clarification                  | File-read confirms                                                                                                                        | YES           |
| `specs/posture-ladder.md:128-133` carries the same clarification                      | File-read confirms                                                                                                                        | YES           |
| Zero `Pre-Phase                                                                       | will be refactored                                                                                                                        | future scope  | when X lands`in`specs/` | Grep confirms empty | YES |
| Zero `except:`/`except Exception: pass`/`TODO`/`FIXME`/`HACK` in posture_gate.py      | Grep confirms (only one `NotImplementedError` hit at line 51 is in a docstring stating the file MUST NOT contain it — file-read confirms) | YES           |

**Verdict:** PASS. 14/14 claims re-derive deterministically. NO non-determinism finding.

---

## Step 4 — Fresh-eyes attack-surface re-scan

### A. `_SHA256_HEX_PATTERN` regex robustness

**File-read at `envoy/authorship/posture_gate.py:101`:**

```python
_SHA256_HEX_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
```

**Fresh-eyes adversarial review:**

1. **`sha256:` + 64 zeros (`"sha256:" + "0"*64`)** — DOES match the regex. Is this exploitable?
   - The all-zero case is a cryptographically meaningless diff_hash (no known SHA-256 input produces all-zero output with non-negligible probability). However, the regex is a SHAPE check, not a cryptographic content check. The spec at `specs/ledger.md` § envelope_edit defines the shape contract (sha256: prefix + 64 lowercase hex chars). The regex enforces shape only — the cryptographic integrity of the diff_hash is the responsibility of the upstream `mutate_for_posture_level()` producer, which the gate inherits from the Protocol contract. **Not a finding** — the shape contract is correctly implemented; cryptographic content integrity is a separate concern (the device-signed envelope binding closes the forge window per the file-read comment at lines 1009-1017).
   - A test exercising the all-zero case would still PASS the regex (it's a structurally valid sha256: shape). This is correct: the regex enforces shape, not entropy.

2. **`sha256:` + 64 uppercase hex** — DOES NOT match the regex (regex pattern is `[a-f0-9]` lowercase only).
   - Test pinning: `test_diff_hash_uppercase_hex_rejected` at line 1804 of `tests/tier1/test_posture_gate_5_step_fail_closed.py` — passes `diff_hash="sha256:" + ("A" * 64)` and asserts `pytest.raises(PostureEnvelopeMutationInvariantError)`. **PASS** — uppercase case is structurally rejected and pinned.

3. **`sha1:` + 40-hex prefix variant** — DOES NOT match the regex.
   - Test pinning: `test_diff_hash_wrong_prefix_raises` at line 1781 — passes `diff_hash="sha1:" + ("d" * 40)` and asserts the typed raise. **PASS** — wrong-prefix attack is structurally rejected and pinned.

4. **Empty/whitespace/leading-padded `sha256: ` + 64 hex** — DOES NOT match (`^sha256:` requires exact prefix with no space after colon, `$` anchors end).

5. **`fullmatch` vs `match`** — the regex is invoked at line 1034 as `_SHA256_HEX_PATTERN.fullmatch(mutation.diff_hash)`. `fullmatch` (not `match`) — anchors both ends regardless of the `^...$` anchors in the pattern. **Belt-and-suspenders. PASS.**

**Verdict:** No new finding. Regex is correctly bounded; both the uppercase and wrong-prefix variants are pinned by Tier 1 tests.

### B. Spy adapter exploit-via-copy-paste risk

**Command (fresh):**

```
grep -rn "class _SpyEnvelope" /Users/esperie/repos/dev/envoy
```

**Output:**

```
tests/tier1/test_posture_gate_5_step_fail_closed.py:2010:        class _SpyEnvelope:
```

Single match. Single location: `tests/tier1/test_posture_gate_5_step_fail_closed.py:2010`, **defined inside the function body** of `test_protocol_attribute_read_surface_bounded` (line 1989). The class is function-local; it cannot be imported by another module via `from tests.tier1... import _SpyEnvelope` because Python function-local classes are not module-attributes.

**Production code re-sweep:**

```
grep -rln "_SpyEnvelope\|SpyAdapter\|class .*Spy.*Envelope" envoy/
```

**Output:** empty. No production code imports, subclasses, or references the spy adapter. PASS.

**Hypothetical copy-paste scenario:** if an engineer copy-pasted the spy class into a production adapter, it would still satisfy the Protocol structurally (the spy returns hardcoded `prior_version=0`, `envelope_id="sha256:spy-envelope"`, etc.). However:

- The spy's `mutate_for_posture_level` raises `AssertionError` at line 2047 — a production adapter that copy-pasted this would fail loudly on the very first ratchet-up attempt, not silently bypass any check.
- The spy's hardcoded `envelope_id` would fail the F-2 mutation invariant at line 1018 (envelope_id mismatch) — the gate would raise `PostureEnvelopeMutationInvariantError`, not silently sign a forged entry.

**Verdict:** Spy adapter copy-paste is NOT exploitable as a production bypass. The F-2 preconditions block (R2-F1 closure) is the structural defense against any malicious adapter shape, spy or otherwise. No finding.

### C. Journal entries disclosure-via-side-channel review

**Files read:** `journal/0020-DECISION-envelope-edit-deferred-to-tier-2.md`, `0021-DECISION-t-02-33-envelope-edit-pairing-design.md`, `0022-DECISION-posture-level-mint-state-interpretation.md`, `0023-DISCOVERY-envelope-hashes-mint-time-cached-f5-false-positive.md`, `0024-DECISION-precondition-invariants-and-orphan-prevention.md`.

**Disclosure axis:** could an attacker reading the public journal narrow their guess about the gate's exact runtime behavior?

- **0024** describes the precondition restructure: "compute mutation + F-2 invariant checks (raise on violation) → Step 5a → Step 5b. On any F-2 invariant violation ZERO Ledger entries land." This IS the structural invariant the gate enforces. **Disclosure intent is correct** — the spec / journal / code are designed to be transparent about the trust-boundary contract. An attacker knowing the order does NOT gain any bypass: the F-2 invariants (envelope_id match, version monotonicity, sha256 shape) are structural and cannot be sidestepped by knowing they exist. **Not a finding** — the journal describes shipped behavior present-tense per `rules/spec-accuracy.md` Rule 5.

- **0021** describes the T-02-33 pairing design and cites `signed_by="delegation_key"` per spec. This is also a CORRECT structural disclosure — the spec at `specs/ledger.md` is the source of truth; the journal references it.

- **0022, 0023** describe the mint-state vs effective-posture distinction. This is a SEMANTIC clarification, not an implementation hint. **Not a finding.**

**Side-channel risk assessment:** the journal's "precise invariant ordering" disclosure (Step 5a precedes Step 5b; preconditions precede both) does NOT enable timing-attack inference about envelope state because:

1. The gate is synchronous-in-control-flow once `request_transition` is entered (every raise is a typed exception, not a side-channel signal).
2. The Ledger writes are device-signed at the `EnvoyLedger.append` boundary, not at the application-decision boundary.
3. The cooling-off / cascade-revoke timing fields (`days_at_current_posture`, etc.) are PUBLIC inputs from the caller, not gate-side secrets.

**Verdict:** No disclosure finding. Journal entries are within the documented transparency contract of `rules/spec-accuracy.md` Rule 5 (specs/journals describe shipped behavior).

### D. Spec edits cumulative review (envelope-model.md + posture-ladder.md + shared-household.md)

**Sweep:**

```
grep -rln "specs/envelope-model.md\|specs/posture-ladder.md\|specs/shared-household.md" envoy/ tests/
```

**Cross-spec mint-state consistency re-check (fresh):**

| File                                | mint-state vs effective clarification                       |
| ----------------------------------- | ----------------------------------------------------------- |
| `specs/envelope-model.md`           | Authoritative source per `journal/0022` (already shipped).  |
| `specs/posture-ladder.md:128-133`   | Present-tense clarifying comment cites `envelope-model.md`. |
| `specs/shared-household.md:102-106` | Present-tense clarifying comment cites `envelope-model.md`. |

**Adversarial inference:** could the cross-spec disclosure narrow an attacker's guess about behavior? No — the spec describes shipped behavior present-tense; the principal's `posture_level` is Ledger-derived (the attacker needs Ledger read access to compute it, which is itself a privileged operation). The disclosure does NOT enable a bypass because the calculation is structurally bound to Ledger state, not to client-supplied envelope mint-time annotation.

**Verdict:** No finding. Spec edits comply with `rules/spec-accuracy.md` Rules 2/4/5/6 and `rules/specs-authority.md` Rule 9 (reference canonical artifact, not restate).

---

## Findings table — Round 4

| ID  | Severity | Surface | File:line | Disposition                                                                                                                                                                                                                                         |
| --- | -------- | ------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| —   | —        | —       | —         | **No new findings.** Round 3's three closures (R2-F1 HIGH, R2-F2 MED, R2-F3 LOW) reproduce against `2264ae2`. Cross-cumulative atomicity audit confirms structural atomicity. Fresh-eyes attack-surface scan surfaced zero new HIGH/MED/LOW issues. |

**Summary:** CRITICAL: 0 · HIGH: 0 · MED: 0 · LOW: 0.

**PASSED CHECKS (re-verified from scratch against `2264ae2`):**

- F-2 invariant raises at lines 1019/1027/1035 precede Step 5a at line 1078 (Step 1 Probe 1).
- Mutation compute (line 1008) + envelope_edit_content build (lines 1045-1053) BOTH precede Step 5a (Step 1 Probe 2).
- Tier 2 atomicity probe asserts `entries == []` via real `EnvoyLedger`; zero executable mocking in tests/tier2/test_posture_gate_wiring.py (Step 1 Probe 3).
- Tier 1 four-position `types == []` assertion at lines 1679/1712/1745/1774; zero stale `types == ["posture_change"]` matches across `tests/` (Step 1 Probe 4).
- No application-level raise between Step 5a (1078) and Step 5b (1115); narrowing asserts at 1112-1114 are structurally guaranteed (Step 1 Probe 5).
- Cross-cumulative `_ledger.append` enumeration: only two append sites in `envoy/`, both inside `PostureGate.request_transition`; no downstream orphan-risk call graph (Step 2).
- Stability check: 14/14 Round 3 claims re-derive deterministically against `2264ae2` (Step 3).
- `_SHA256_HEX_PATTERN` regex correctly bounds the shape contract; uppercase hex rejected via Tier 1 test_diff_hash_uppercase_hex_rejected at line 1804; `sha1:` prefix rejected via test_diff_hash_wrong_prefix_raises at line 1781; `fullmatch` anchors both ends (Step 4A).
- `_SpyEnvelope` is function-local at `tests/tier1/test_posture_gate_5_step_fail_closed.py:2010` — single grep match; zero production-code imports; copy-paste exploit pre-empted by F-2 preconditions (Step 4B).
- Journal entries 0020-0024 disclose shipped behavior present-tense per `rules/spec-accuracy.md` Rule 5; no side-channel exploitation surface (Step 4C).
- `specs/envelope-model.md` + `specs/posture-ladder.md:128-133` + `specs/shared-household.md:102-106` carry consistent mint-state-vs-effective-posture clarification; zero `Pre-Phase|will be refactored|future scope|when X lands` markers (Step 4D).
- Zero `except:` / `except Exception: pass` / `TODO` / `FIXME` / `HACK` in `envoy/authorship/posture_gate.py` (the single `NotImplementedError` hit at line 51 is inside a docstring stating the file MUST NOT contain it — confirmed via file-read at lines 49-51).

---

## Receipts

- Source files re-read with line citations: `envoy/authorship/posture_gate.py` (lines 45-59, 95-102, 670-715, 990-1152), `tests/tier1/test_posture_gate_5_step_fail_closed.py` (lines 1626-1842, 1955-2098), `tests/tier2/test_posture_gate_wiring.py` (lines 12-25, 625-635), `specs/shared-household.md`, `specs/posture-ladder.md`, `workspaces/phase-01-mvp/journal/0024-DECISION-precondition-invariants-and-orphan-prevention.md`.
- Greps executed (with literal output captured above): `_SHA256_HEX_PATTERN`, `_ledger\.append`, `class TestF2InvariantViolationEmitsNeitherEntry`, `types == \[\]` / `types == \["posture_change"\]`, `@patch|MagicMock|unittest\.mock|mock\.Mock` (against tests/tier2), `class _SpyEnvelope` (against envoy/ and tests/), `_SpyEnvelope|SpyAdapter|class .*Spy.*Envelope` (against envoy/), `Pre-Phase|will be refactored|future scope|when X lands` (against specs/), `posture_level|mint-state|effective.posture|mint-time` (against specs/shared-household.md AND specs/posture-ladder.md), `except:|except Exception:.*pass|TODO|FIXME|HACK|NotImplementedError` (against posture_gate.py), `PostureNoopError|...` typed-error enumeration.
- Round 3 audit at `workspaces/phase-01-mvp/04-validate/round-3-security-audit-2026-05-24.md` is the baseline; Round 4 re-derives every Round 3 claim from scratch per `rules/testing.md` § Audit Mode.
- Cumulative diff scope walked: `641dd2d..2264ae2` (T-02-33 chain origin → current main).

---

## Auditor notes for orchestrator

- Round 4 reproduces Round 3 deterministically; convergence criterion "2 consecutive clean rounds" is MET.
- The R2-F1 structural defense (F-2 invariants as PRECONDITIONS) is robust against the full fresh-eyes attack-surface review: shape-regex bypass attempts (uppercase, sha1:, all-zero) are either rejected by `_SHA256_HEX_PATTERN.fullmatch` (uppercase / wrong-prefix) or are not a finding (all-zero is structurally valid sha256: shape but cryptographically meaningless — the gate's job is shape validation, not entropy validation; cryptographic integrity belongs to `mutate_for_posture_level`'s upstream producer).
- The spy adapter exploit-via-copy-paste vector is closed by two layers: (a) the class is function-local so it cannot be module-imported; (b) even if copy-pasted into production, the F-2 preconditions reject any envelope_id mismatch / version drift / malformed diff_hash before any Ledger entry signs.
- Journal entries 0020-0024 and the spec edits (`shared-household.md:102-106` + `posture-ladder.md:128-133`) describe shipped behavior in present tense per `rules/spec-accuracy.md` Rule 5; no future-tense framings; no side-channel disclosure exploitable for a bypass.
- Per `rules/verify-resource-existence.md` MUST-4, this Round 4 verdict cites durable receipts (file paths + line numbers + literal grep outputs reproduced fresh) — no self-attestation. The Round 3 receipt remains at its committed path; Round 4 receipts are listed above.

---

**Round 4 reproduces Round 3 verdict; convergence criterion MET.**
