# 0032 — DISCOVERY: /redteam T-02-44 + T-02-45 EC-1 acceptance — CLEAN×2 across 3 axes

**Date:** 2026-05-26
**Branch:** `feat/phase-01-T-02-44-T-02-45-ec-1-acceptance`
**Posture:** L5_DELEGATED
**Commits (in order):**

- `2b89993 feat(phase-01-T-02-44): close prescribed Tier-2 BC gap tests + ollama dep`
- `2a54483 feat(phase-01-T-02-45): EC-1 Tier 3 acceptance — N=3 sessions ≤25min, minimum-path ≤8min`
- `8716aad fix(phase-01-T-02-44): RT-1 round-1 findings — sweep widening + regression marker + citation`

**Forest pick rationale:** session 2026-05-26 wrapup (`.session-notes`) set T-02-44 → T-02-45 as the
next forest pick, value-anchored to `briefs/00-phase-01-mvp-scope.md § Surfaces` — empirical proof
BET-1 + BET-12 are falsifiable within the 25-min ceiling for first-time users. T-02-45 is the
load-bearing acceptance gate; T-02-44 unblocks it.

## Discovery — T-02-44 was much closer to "done" than the todo prescribed

The todo prescribed 5 Tier-2 files for T-02-44; reality on `main` already covered 4 of them under
different file names. The genuine remaining gaps were three filename-level holes that ALSO needed
additive coverage:

| Prescribed name                                           | Existing coverage                               | Gap closed this PR |
| --------------------------------------------------------- | ----------------------------------------------- | ------------------ |
| test_boundary_conversation_runtime_wiring.py              | EXISTS — real Ollama S0→S10                     | —                  |
| test_resume_from_each_state.py                            | EXISTS — coordinator-level                      | —                  |
| test_envelope_compiler_monotonic_tightening_at_compile.py | NEW                                             | 5 tests            |
| test_post_duress_banner.py                                | NEW (partial overlap with TestDuressBannerGate) | 4 tests            |
| test_visible_secret_render_check.py                       | NEW (partial overlap with adapter CRUD)         | 4 tests            |

T-02-45 was entirely greenfield: `tests/tier3/` did not exist; 5 new tests added (3 full-path + 1
chain-integrity + 1 minimum-path).

## Critical hidden gap surfaced and closed

The existing `test_boundary_conversation_runtime_wiring.py` had been silently SKIPPED because
the `ollama` Python client lib was not declared as a runtime dep — the `skipif(not OLLAMA_AVAILABLE)`
gate was masking the fact that the real-Ollama wiring test had NEVER actually run. Adding
`ollama>=0.4` to `pyproject.toml` runtime deps and re-running surfaced the test passes in 11.3s
against the live daemon — the production LLM path is empirically verified for the first time.

## /redteam round-by-round trajectory

| Round | CRIT | HIGH | MED | LOW | Verdict   | Findings                                                                              | Closure                       |
| ----- | ---: | ---: | --: | --: | --------- | ------------------------------------------------------------------------------------- | ----------------------------- |
| 1     |    0 |    1 |   1 |   1 | NOT CLEAN | sec RT1-H1 (sweep scope), gold-std LOW (broken cite), testing MED (regression marker) | All 3 same-shard at `8716aad` |
| 2     |    0 |    0 |   0 |   0 | CLEAN     | sec + analyst + reviewer                                                              | (first of 2)                  |
| 3     |    0 |    0 |   0 |   0 | CLEAN     | sec + reviewer                                                                        | (convergence MET)             |

Per brief § Exit criteria: 2 consecutive CLEAN rounds achieved (R2 + R3).

### RT-1 findings closed same-shard (autonomous-execution.md MUST Rule 4)

**RT1-H1 (security HIGH)** — `test_visible_secret_render_check.py::TestVisibleSecretPhraseNeverInLedger`
sweep scope filtered to `_envoy_envelope_v1`-keyed metadata, narrower than the docstring's promise
"phrase MUST NEVER appear in ANY Ledger entry content". A future refactor writing the phrase to
`event.description` / `event.action` / metadata-direct would silently pass. **Fix**: widened to
`dataclasses.asdict(event) + json.dumps + substring` sweep across every audit event field.

**RT1-LOW (gold-standards)** — `test_envelope_compiler_monotonic_tightening_at_compile.py` cited
`specs/envelope-compiler.md` which does not exist in `specs/`. **Fix**: dropped the broken citation.

**RT1-MED-1 (testing-specialist MED)** — `TestVisibleSecretPhraseNeverInLedger` pinned commit
`883e6ba` (R1-HIGH-1b) in docstring but lacked `@pytest.mark.regression` decorator. **Fix**: added
the class-level marker; `pytest -m regression` now collects 10 tests (was 9).

### Round 2 advisory note (NOT a finding against this PR)

The R2 reviewer surfaced an advisory observation: `test_boundary_conversation_runtime_wiring.py` is
random-order-dependent under `pytest-randomly` (real-Ollama network test; gate-back error class not
in the existing helper's parse-retryable set). Verified out-of-PR-scope: passes in isolation,
passes with stash applied to base, the failing line is unchanged from PR #38. Filed as RISK in
journal entry `0033` for future cleanup.

## EC-1 empirical proof — the value anchor

Three independent first-time-user sessions drove real Ollama (`qwen2.5:0.5b`) through the full
S0→S10 ritual. Observed wall-clock on this hardware:

| Session | Principal            | Elapsed | 25-min ship gate       | 15-min UX target |
| ------- | -------------------- | ------: | ---------------------- | ---------------- |
| 0       | alice@example        |   1.80s | ✓ ≤ 1500s              | ✓ MET            |
| 1       | bob@example          |   1.59s | ✓ ≤ 1500s              | ✓ MET            |
| 2       | carol@example        |   1.81s | ✓ ≤ 1500s              | ✓ MET            |
| min     | minimum-path@example |   1.70s | ✓ ≤ 480s (8-min floor) | n/a              |

Each session produced a parseable EnvelopeConfig (non-empty `envelope_id` from S9 sign) AND seeded a
Genesis Record AND the Ed25519-signed Ledger chain verified end-to-end. The 15-min UX target is
surfaced via stdout `print` for `/codify` scraping per `journal/0005` Disposition #3.

## Carry-forward dispositions

- **MED — R2-flake on test_boundary_conversation_runtime_wiring.py** (out-of-PR-scope per evidence):
  filed as RISK in journal `0033`; structurally fixable by mirroring T-02-45's parse-retryable error
  set widening + retry budget bump from 4 to 8 (matches the same-bug-class pattern). Owner: next
  session continuing Wave-2 cleanup.
- **`.spec-coverage-v2.md` M-state on main**: unchanged from prior session's note. Orchestrator's
  call deferred to next wrapup per the standing carry.

## Receipts

- Pytest full suite at HEAD `8716aad`: 994 passed / 9 acceptable infra-conditional skips / 0 failed
  in deterministic ordering (`pytest -p no:randomly`).
- Tier 3 EC-1 acceptance suite: 5/5 passed in 11.06s.
- Regression suite (`pytest -m regression`): 10/1003 collected (was 9 — `+1` from this PR).
- All 6 RT-1 agents reported (security-reviewer / reviewer / analyst / gold-standards-validator /
  value-auditor / testing-specialist). All 5 RT-2/RT-3 agents reported (security-reviewer / reviewer
  / analyst — analyst run in R2 only).

## Cross-references

- T-02-44 prescribed acceptance: `todos/active/02-wave-2-authorship-shamir-boundary.md:312-326`
- T-02-45 prescribed acceptance: `todos/active/02-wave-2-authorship-shamir-boundary.md:330-344`
- EC-1 value anchor: `briefs/00-phase-01-mvp-scope.md § Surfaces`
- 25-min ship gate disposition: `journal/0005-DECISION-todos-opening-dispositions.md § Disposition #3`
- Sibling RT-1 same-shard sweep pattern: `journal/0028-DISCOVERY-redteam-wave-1-r1-sameshard-sweep.md`
- Sibling convergence record: `journal/0031-DISCOVERY-redteam-t-02-40-boundary-conversation-convergence.md`
