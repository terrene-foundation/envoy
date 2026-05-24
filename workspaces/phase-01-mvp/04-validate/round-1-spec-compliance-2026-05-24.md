# Round 1 — Spec Compliance + Test Verification

**Date:** 2026-05-24
**Subject:** T-02-33 envelope_edit pairing on PostureGate ratchet-up
**PR / commits audited:** PR #23 merged at `641dd2d`; commits `1e6b256, 7a8d62a, fe1b982, 71199d4, 3ad3fc4`
**Audit-mode contract:** re-derive everything; do NOT trust `.test-results`; do NOT trust PR description.
**Methodology:** `skills/spec-compliance/SKILL.md` + `.claude/rules/probe-driven-verification.md` (structural-probe verification — AST/grep/pytest commands, no prose).

## Verdict

**APPROVE.** All 23 assertion rows PASS. All 579 tests PASS. Zero CRIT / HIGH / MED / LOW findings.

Spec contract for T-02-33 is delivered to spec — every promise in `specs/posture-ladder.md` § Ratchet-up #3, `specs/ledger.md` § envelope_edit (lines 107-114), `specs/envelope-model.md` § `metadata.posture_level`, and `workspaces/phase-01-mvp/journal/0020-DECISION-envelope-edit-deferred-to-tier-2.md` (closure) resolves against a literal AST/grep verification command.

## Spec-compliance assertion table results

Full table with command + literal output: see `workspaces/phase-01-mvp/.spec-coverage-t02-33-round1.md`.

| Spec source                                                      | Promises verified                                                                                    | Pass      |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | --------- |
| `specs/posture-ladder.md` § Ratchet-up #3                        | 4 (emission, asymmetry, typed error, idempotent path)                                                | 4/4       |
| `specs/ledger.md` § envelope_edit (107-114)                      | 6 (wire shape, schema_version, signed_by, prior+1, diff_hash, rollback_grace_window)                 | 6/6       |
| `specs/envelope-model.md` § metadata.posture_level               | 2 (field declared, field-semantics documented)                                                       | 2/2       |
| `journal/0020-DECISION-...md` deferral closure                   | 2 (module docstring updated, spec § Out of scope updated)                                            | 2/2       |
| `workspaces/phase-01-mvp/todos/active/02-wave-2-...md` § T-02-33 | 1 (CLOSED-with-SHAs format matches T-02-34/T-02-35)                                                  | 1/1       |
| `rules/testing.md` Audit Mode                                    | 3 (new error has importing tests; Tier 2 has ≥3 positive + ≥1 negative; collect-only clean)          | 3/3       |
| Defense-in-depth / regression checks                             | 5 (asymmetric signed_by, defensive Step 5b guard, Optional kwarg, no mocks in Tier 2, no inline DDL) | 5/5       |
| **TOTAL**                                                        | **23**                                                                                               | **23/23** |

Pass rate: **23/23 (100%)**.

## Test re-derivation results (Audit Mode — Re-Derived, NOT Trusted)

```text
$ .venv/bin/pytest --collect-only -q tests/tier2/test_posture_gate_wiring.py
8 tests collected in 0.01s

$ .venv/bin/pytest tests/tier2/test_posture_gate_wiring.py -v --tb=short
8 passed in 0.03s

$ .venv/bin/pytest tests/tier1/test_posture_gate_5_step_fail_closed.py -v --tb=short
92 passed in 0.05s    (includes TestStep3eEnvelopeMissingOnRatchetUp × 5 cases)

$ .venv/bin/pytest tests/ -q --tb=line
579 passed in 17.96s
```

- Tier 2 wiring tests (8): 3 positive ratchet-up cases (PSEUDO→TOOL, TOOL→SUPERVISED, multi-step PSEUDO→DELEGATING) + 1 content-hash positive case + 1 fail-closed negative (Step 3d insufficient authorship) + 1 ratchet-down asymmetry + 2 typed-error contract cases. All pass.
- Tier 1 regression (92): includes the new `TestStep3eEnvelopeMissingOnRatchetUp` class (5 cases) plus the pre-existing 87 cases for the 5-step gate. All pass.
- Full suite (579): no regressions introduced.
- New-module check (per `rules/testing.md` Audit Mode): `PostureRatchetEnvelopeMissingError` has 12 references across two test files (`tests/tier1/test_posture_gate_5_step_fail_closed.py` × 6, `tests/tier2/test_posture_gate_wiring.py` × 6) — well above the ≥1 importing-test threshold.

## Spec-promise traceability matrix (literal anchors)

### 1. `specs/posture-ladder.md:41` — Ratchet-up requirement #3

> "Envelope version bump (specs/envelope-model.md) — new posture is part of the envelope schema; any posture change is an `envelope_edit`."

Production site: `envoy/authorship/posture_gate.py:914-964` Step 5b. Emission guarded by `target > current` (AST extraction confirmed; see assertion 2). The dict at `envelope_edit_content` has all 7 inner spec fields; `entry_type="envelope_edit"` carries the outer `type` per `EnvoyLedger.append` contract.

### 2. `specs/ledger.md:107-114` — envelope_edit wire shape

```json
{"type": "envelope_edit", "schema_version": "1.0",
 "envelope_id": "uuid-v7", "prior_version": <int>, "new_version": <int>,
 "diff_hash": "sha256:...", "rollback_grace_window_seconds": <int>,
 "signed_by": "delegation_key"}
```

AST-derived keys on `envelope_edit_content`:

```
['schema_version', 'envelope_id', 'prior_version', 'new_version', 'diff_hash', 'rollback_grace_window_seconds', 'signed_by']
```

7 inner fields match spec exactly. `signed_by` literal is `"delegation_key"` (matches spec; distinct from posture_change's `"genesis_key"` at L897 — asymmetry preserved).

### 3. `specs/envelope-model.md:34,96` — `metadata.posture_level`

AST-derived: `EnvelopeMetadata.posture_level: type='str', default="'PSEUDO'"`. Field at `envoy/envelope/types.py:340`. Spec line 96 carries the field-semantics block describing wire form (canonical PostureLevel enum NAME), default ("PSEUDO" at first Boundary Conversation entry), and pairing semantics (ratchet-up emits envelope_edit; demotion does NOT bump the envelope — asymmetric).

### 4. Deferral closure (journal 0020 → T-02-33)

`envoy/authorship/posture_gate.py:34-47` — module docstring carries the closure narrative: "**`envelope_edit` Ledger entry pairing shipped at T-02-33 (Tier 2 wiring).** Spec line 41 mandates that ratchet-up writes BOTH a `posture_change` entry AND an `envelope_edit` entry..." plus citation of both journals (`0020-...md` for the deferral, `0021-...md` for the design choice).

`specs/posture-ladder.md:163-165` (§ Out of scope intro) explicitly: "T-02-33 (Tier 2 wiring) closed the prior envelope_edit pairing deferral; ratchet-up now emits paired `posture_change` + `envelope_edit` Ledger entries per spec § Ratchet-up #3." envelope_edit is NOT listed as a deferral bullet (verified by full grep).

### 5. Todo closure formatting (T-02-33 matches T-02-34/T-02-35 shape)

`workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md:78`:

```
## T-02-33 — Wire envoy/authorship/ (Tier 2) ✅ CLOSED 2026-05-24
```

Format aligns with T-02-31 (line 33: `✅ CLOSED 2026-05-10 (PR #19)`), T-02-34 (line 111: `✅ CLOSED 2026-05-07 (PR #13)`), T-02-35 (line 138: `✅ CLOSED 2026-05-07 (PR #15)`). T-02-33 cites four commit SHAs inline (planning `1e6b256`, RED BAR `7a8d62a`, GREEN BAR `fe1b982`, spec sweep `71199d4`) which is the merged-PR variant of the same format.

## Findings

**CRIT: 0 · HIGH: 0 · MED: 0 · LOW: 0.**

No findings. No same-bug-class gaps to flag for `rules/autonomous-execution.md` Rule 4 (in-shard fix-immediately).

### Defense-in-depth notes (non-findings, observational)

These are NOT findings — they're positive observations that the production code goes beyond the spec's minimum mandate. Recording them for institutional memory:

- **Step 5b carries a defensive `raise PostureRatchetEnvelopeMissingError` at line 940** even though Step 3e (line 853) already raises on the same condition. Per `rules/zero-tolerance.md` Rule 3a (typed delegate guards for None backing objects). Comment at L931-938 documents the rationale: "a future refactor that accidentally drops Step 3e fails loudly at this site rather than producing a NoneType.mutate_for_posture_level() crash downstream". This is the correct shape for the Rule 3a contract.
- **`PostureRatchetEnvelopeMissingError` carries a `user_message` field** (line 402-407) per `rules/communication.md` plain-language requirement. Tested at `tests/tier2/test_posture_gate_wiring.py::TestPostureRatchetEnvelopeMissingError::test_error_has_user_message`.
- **Asymmetric pairing is pinned by a dedicated test class** (`TestPostureChangeOnRatchetDownNoEnvelopeEdit`) at `tests/tier2/test_posture_gate_wiring.py:618-662`. Per the test's docstring: "pins the asymmetry so a future refactor that 'symmetrizes' the pairing without a spec edit fails loudly." Structural defense against future drift.
- **The `_PostureCarryingEnvelope` Protocol is narrow (5 methods/properties)** — `envelope_id`, `prior_version`, `prior_content_hash`, `prior_posture_level`, `mutate_for_posture_level`. Per `journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md`, the kwarg-on-call DI shape over a constructor-time DI surface keeps PostureGate stateless. This is the correct choice for per-transition data.
- **Tier 2 NO-mocking discipline verified** — `grep -nE 'unittest\.mock|MagicMock|@patch' tests/tier2/test_posture_gate_wiring.py` returns empty. The `_TrustStoreRevokeHookAdapter`, `_RecordingBET12Sink`, and `_EnvelopeConfigPostureCarrier` are real adapters with their own state, not mocks. Verified via real `EnvoyLedger` + real `EnvelopeCompiler` + real Ed25519 throughout.

## Log triage gate scan (per `rules/observability.md` Rule 5)

```text
$ .venv/bin/pytest tests/ -q --tb=line 2>&1 | grep -iE 'warn|deprec|error' | sort -u
(empty)

$ .venv/bin/python -W error -c "import envoy.authorship.posture_gate; import tests.tier2.test_posture_gate_wiring"
(no warnings)
```

No WARN+ entries to acknowledge. Gate clean.

## Probe-driven verification discipline (per `rules/probe-driven-verification.md`)

This audit's semantic claims were all converted to **structural probes** per MUST-3:

- "Emits envelope_edit" → AST extraction of `entry_type="envelope_edit"` literal + dict-keys enumeration.
- "Raises typed error" → grep for `raise PostureRatchetEnvelopeMissingError` site + AST class-existence check.
- "Field is documented" → spec-line extraction via `sed -n '96p'` + grep for the field name in spec prose.
- "Asymmetric pairing" → AST extraction of the `if target > current:` guard wrapping Step 5b.
- "Test pass" → `pytest --collect-only` exit 0 + `pytest -v` exit 0.

Zero regex/keyword scoring of agent prose. Per MUST-3 (structural-only when no LLM access): every probe is file-existence, AST shape, byte-equality, or exit-code based.

## Disposition

**Round 1 verdict: APPROVE — no further rounds required from a spec-compliance + test-verification standpoint.**

The next-round disposition is the human's call. No CRIT/HIGH/MED/LOW findings require resolution; no same-bug-class gaps surface for in-shard sweep per `rules/autonomous-execution.md` Rule 4. The shipped surface is byte-traceable to spec promises; the test layer re-derives clean.

If the human elects to run additional rounds, the suggested focus areas (NOT findings — possible deeper investigations):

1. **Cross-spec consistency sweep** per `rules/specs-authority.md` Rule 5b — sibling specs referencing `envelope_edit` (e.g. `specs/envelope-model.md:158` `EnvelopeVersionMismatchError`) could be re-derived for terminology/wire-shape drift. Likely no findings (specs were updated as part of PR #23 commit `71199d4`), but the structural sweep is the canonical defense.
2. **Trust-Store integration sanity** — Tier 2 test uses a `_TrustStoreRevokeHookAdapter` recorder that does not exercise the production `TrustStoreAdapter.revoke` path; ratchet-down cascade-revoke happens against the recorder. A Tier 3 (e2e) wiring test that pipes ratchet-down through the real `TrustStoreAdapter` would close the last DI-shaped gap. This is NOT a finding — Tier 2 contract is fully satisfied; Tier 3 is a phase-04 surface per the spec's narrow scope.

## Artifacts

- Assertion table (Round 1, this audit): `workspaces/phase-01-mvp/.spec-coverage-t02-33-round1.md`
- This findings doc: `workspaces/phase-01-mvp/04-validate/round-1-spec-compliance-2026-05-24.md`
- Prior unrelated assertion file (NOT this audit; Wave-2 2026-05-07): `workspaces/phase-01-mvp/.spec-coverage-v2.md` — left untouched.
