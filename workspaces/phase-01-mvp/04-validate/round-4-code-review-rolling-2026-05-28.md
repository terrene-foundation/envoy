# /redteam Round-4 — Rolling code review (PR #47 + PR #48 + PR #49)

**Findings: 0 CRIT + 0 HIGH + 2 MED + 1 LOW**

**Status:** Banked round. Zero CRIT + zero HIGH on the ~915 LOC delta `aa50ef1..HEAD` (`5b93856`). All 8 mechanical sweeps clean. All 6 Round-3 closures still intact at HEAD. EC-7 5-channel × N=3 (15 onboardings) + EC-8(a)+(b)+(c) batteries pass; F5.1 packaging-shape gate passes with the documented 9-subcommand xfail list as Milestone-5 progress signal.

**Scope:** commits `528da54..b02c9b7` (EC-8 PR #47) + `48ceac0..c9b8698` (EC-7 PR #48) + `d293963..8b33ed2` (F5.1 PR #49). Files in delta:

- `tests/e2e/test_envoy_cli_packaging_acceptance.py` (PR #49, 205 LOC)
- `tests/e2e/test_session_continuity_5_channels.py` (PR #48, 464 LOC)
- `tests/helpers/deterministic_llm_provider.py` (PR #48, 217 LOC)
- `tests/e2e/test_envoy_7_day_cross_channel_coherence.py` (PR #47, 287 LOC)
- `tests/tier2/test_grant_moment_cascade_cross_channel.py` (PR #47, 239 LOC)
- `tests/tier2/test_envelope_compiler_session_envelope_byte_identity.py` (PR #47, 165 LOC)
- `tests/tier2/test_budget_no_double_billing_multi_channel.py` (PR #47, 160 LOC)

---

## Findings

| ID    | Sev | File:Line                                                                            | Claim                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Evidence command                                                                                                               |
| ----- | --- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| MED-1 | MED | `tests/e2e/test_session_continuity_5_channels.py:27-33` + workspace `.session-notes` | EC-7 acceptance gate spec (`01-analysis/02-mvp-objectives.md` line 104) MANDATES "per-channel deviation from CLI baseline (in completion time, in message count) MUST stay within 2×." The test scopes this out citing "requires real vendor sandboxes" but the gap is NOT tracked in the workspace outstanding ledger as a deferred shard with a value-anchor.                                                                                                                                                                                  | `grep -nE "timing\|2×\|≤2×\|baseline" tests/e2e/test_session_continuity_5_channels.py workspaces/phase-01-mvp/.session-notes`  |
| MED-2 | MED | `envoy/runtime/adapters/kailash_py.py:188-211`                                       | The production runtime adapter's `KailashPyRuntime.trust_cascade_revoke` (the cross-channel cascade path EC-8(c) acceptance claims to verify) has NO direct Tier-2 test calling it through the production facade. The new EC-8(c) cross-channel test uses `StubTrustRuntime` (test helper); the existing orchestrator-wiring test also uses a stub. Per `facade-manager-detection.md` MUST-1 + `orphan-detection.md` Rule 2: every wired manager needs Tier 2 through the framework's hot path.                                                  | `grep -rn "trust_cascade_revoke" tests/` (no production-adapter test) + read of `envoy/runtime/adapters/kailash_py.py:188-211` |
| LOW-1 | LOW | `envoy/trust/store.py:733,743,1023,1032,1041,1051,1059,1066`                         | 8 `CREATE TABLE IF NOT EXISTS` statements in application code (NOT in a `migrations/` directory, NOT in the SDK dialect helper layer). Pre-existing at baseline `aa50ef1` and persisted through Round-3 unflagged. Per `rules/schema-migration.md` MUST Rule 1 + Rule 1a (the `/redteam` mechanical sweep MUST flag) + `rules/zero-tolerance.md` Rule 1a (scanner-surface symmetry — "same on main, therefore not introduced here" is BLOCKED). NOT touched in this round's delta but surfaced by the same mechanical sweep this round mandates. | `grep -RInE 'CREATE\s+TABLE\|ALTER\s+TABLE\|DROP\s+TABLE' --include='*.py' envoy/ \| grep -vE '/(migrations\|tests)/'`         |

Findings rationale (per the prompt: report findings + evidence, do NOT propose fixes):

- **MED-1** is a partial-acceptance gap, not a code defect. EC-7's full spec gate is 2-axis (15 structural completions + ≤2× CLI-baseline parity); the test ships the first axis with the second axis explicitly scoped out. The scope-out is documented IN the test docstring but not in `.session-notes` outstanding ledger as a separate F-N value-anchored deferral. The risk is the standard deferral-as-forgetting pattern this rolling round is intended to surface.
- **MED-2** is the cross-product of `facade-manager-detection.md` + `orphan-detection.md` + `rules/testing.md` § 3-Tier. The orchestrator's `revoke_and_verify` IS tested through real harness wiring; the runtime adapter's `trust_cascade_revoke` (which is the production code path the EC-8(c) gate's "cascade revocation" claim consumes in deployment) is not. The test verifies the `CascadeRevocationOrchestrator` semantics against a Protocol-Satisfying Deterministic Adapter (not a mock — acceptable per `rules/testing.md` Protocol Adapters exception); the gap is the binding between orchestrator and adapter is unverified.
- **LOW-1** is a Rule-1a scanner-surface symmetry finding. The same sweep this round runs flags it; Round-3 closed clean without flagging because the schema-migration grep was not yet in the rolling sweep set. Per Rule 1a "Same on main, therefore not introduced here" is BLOCKED — the disposition obligation lives on this round.

---

## Closure-parity verification — Round-3 findings against HEAD `5b93856`

| Round-3 finding ID                                           | Status   | Evidence command + outcome                                                                                                                                                                                                         |
| ------------------------------------------------------------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| HIGH-1 — T-018 duress banner leaked to secondary channels    | VERIFIED | `grep -rn "duress" envoy/daily_digest/` → `duress.py:41` "Primary-channel-only duress banner gate" + `duress.py:76` "Unread duress event(s) exist — gate on primary-channel match" + `renderer.py:18` strip-for-non-primary cited. |
| HIGH-2 — `record_success` / `record_open` never called       | VERIFIED | `grep -rn "record_success\|record_open" envoy/daily_digest/` → `service.py:491` calls `_backfill.record_success`; `service.py:348` calls `_low_engagement.record_open`; backing methods at `backfill.py:77` + `engagement.py:41`.  |
| HIGH-3 — `event_only` form advertised but never returned     | VERIFIED | `grep -rn "event_only" envoy/daily_digest/ envoy/cli/` → `service.py:469-475` event_only event-gate via `_has_event(summary)`; `cli/digest.py:198` exposes `digest form --set event_only` Click choice.                            |
| MED-1 — receipt_hash docstring vs inputs                     | VERIFIED | `grep -rn "receipt_hash" envoy/daily_digest/payload.py` → `payload.py:8-9,22,87` docstring + field declaration align as "sha256 over canonical_dumps(payload minus receipt_hash)".                                                 |
| MED-2 — backfill `back_fill_days` off-by-one                 | VERIFIED | `grep -rn "back_fill_days\|clamped" envoy/daily_digest/backfill.py` → `backfill.py:46,63,66` derives `back_fill_days = max(0, covered_days - 1)` from the clamped window — off-by-one closed.                                      |
| MED-3 — `RedactedFieldRenderError` defined but no raise site | VERIFIED | `grep -rn "RedactedFieldRenderError\|sha256:" envoy/daily_digest/` → `errors.py:42` defined; `fanout.py:31,46-47,57` `_partition_classified` drops `sha256:`-prefixed classified markers; `aggregator.py:156` produces them.       |

All 6 closures intact at HEAD. No regressions surfaced; the closures' implementations remain in their Round-3-landed locations.

---

## Mechanical sweep results

### Sweep 1 — Round-3 closure re-grep

Performed inline as the closure-parity table above. All 6 closures (3 HIGH + 3 MED) re-greppable at HEAD with the documented behavior.

### Sweep 2 — `pytest --collect-only -q tests/e2e/ tests/helpers/`

```
$ .venv/bin/python -m pytest --collect-only -q tests/e2e/ tests/helpers/ tests/tier2/ 2>&1 | tail -3
[...]
328 tests collected in 1.80s
```

Exit 0. No import errors, no missing fixtures.

### Sweep 3 — `grep -c REGISTERED_AS_OF_F5 tests/e2e/test_envoy_cli_packaging_acceptance.py`

```
$ grep -c REGISTERED_AS_OF_F5 tests/e2e/test_envoy_cli_packaging_acceptance.py
3
```

Confirmed 3 references: declaration line 99 + reference at line 164 (top-level help registered-subcommand assertion loop) + reference at line 186 (xfail predicate). The frozenset IS the toggle the `.session-notes` Read-first #1 describes; xfail-list-as-Milestone-5-progress-signal is operative.

### Sweep 4 — Channel-count sweep on EC-7 file

```
$ grep -nE "8\s*channels|channels\s*=\s*\[" tests/e2e/test_session_continuity_5_channels.py
(no matches — the test only references 5 channels)

$ grep -nE "_FIVE_CHANNELS|five_channels|5.channel|de-scope" tests/e2e/test_session_continuity_5_channels.py | head -5
3:"""EC-7 acceptance battery (de-scope #1 — 5 channels × N=3 onboardings).
13:This file is the de-scope #1 implementation (per
17:to Phase-02, the Phase-01 EC-7 acceptance becomes 5 channels × N=3 = 15
87:# Phase-01 de-scope-#1 channel set per `01-analysis/02-mvp-objectives.md` line 171.
88:_FIVE_CHANNELS = ("cli", "web", "telegram", "slack", "discord")
```

De-scope #1 invocation IS intentional + documented in module docstring + module-level constant. Citation to `01-analysis/02-mvp-objectives.md` line 171 (the de-scope #1 fallback row) verified at line 87. Tests are deterministic (Protocol-Satisfying Deterministic Adapter dispatch on schema-fingerprint substrings, no time-of-day or wall-clock-dependent assertions).

### Sweep 5 — No-mock sweep on EC-7 deterministic LLM stub

```
$ grep -nE "MagicMock|unittest\.mock|@patch|mock\.patch" tests/helpers/deterministic_llm_provider.py
198:    ``unittest.mock``, no network — counts as a Protocol-Satisfying
```

The single match is a NEGATIVE assertion in a docstring claiming "no `unittest.mock`, no network — counts as a Protocol-Satisfying Adapter". File reviewed at lines 1-217: a clean Protocol-Satisfying Deterministic Adapter — three classes (`DeterministicProvider`, `_StubDeployment`/`_StubLlmClient`, `DeterministicModelRouter`) that satisfy the runtime's read-only attribute access pattern (`provider.chat`, `client.deployment.preset_name`, `client.deployment.default_model`, `router.for_primitive`). Dispatch is structural (substring scan on output-field-name fingerprints from `envoy/boundary_conversation/signatures.py`). Per `rules/testing.md` § "Protocol Adapters" exception this is NOT a mock. The shape matches the prior round's Daily Digest convergence template; usable for future EC-N tests requiring offline CI execution.

### Sweep 6 — Cascade-revocation real-infra check

```
$ grep -nE "MagicMock|unittest\.mock|@patch|mock\.patch" tests/tier2/test_grant_moment_cascade_cross_channel.py tests/tier2/test_envelope_compiler_session_envelope_byte_identity.py tests/tier2/test_budget_no_double_billing_multi_channel.py tests/e2e/test_envoy_7_day_cross_channel_coherence.py
tests/tier2/test_grant_moment_cascade_cross_channel.py:47:against per-channel ``RecordingChannelAdapter`` instances. NO ``unittest.mock``.
(only match is the NEGATIVE assertion in a docstring)
```

Zero `MagicMock` / `unittest.mock` / `@patch` usage in the EC-8 test set. The cross-channel cascade test uses real `EnvoyGrantMomentRuntime` + real `EnvoyLedger` + real `ChannelHandoff` over per-channel `RecordingChannelAdapter` instances. The `StubTrustRuntime` (test harness) satisfies `CascadeRevocationOrchestrator._RuntimeProtocol` deterministically — a Protocol Adapter, NOT a mock. **Caveat (MED-2 above):** the test does NOT exercise the production `KailashPyRuntime.trust_cascade_revoke` adapter path; the cascade-orchestrator semantics are verified but the runtime-adapter wiring is not.

### Sweep 7 — xfail discipline sweep

```
$ grep -nE "request\.applymarker|pytest\.mark\.xfail|reason=" tests/e2e/test_envoy_cli_packaging_acceptance.py
187:        request.applymarker(
188:            pytest.mark.xfail(
190:                reason=(
```

Single xfail block at `test_envoy_cli_packaging_acceptance.py:187-198`. Reason is the verbatim 5-line string citing `envoy/cli/main.py` (the unwired-subcommand site) + workspace plan anchor `workspaces/phase-01-mvp/02-plans/01-build-sequence.md § Wave 5` + the flip predicate ("xfail flips to passing once shard 19 registers"). `strict=False` per `rules/test-skip-discipline.md` BORDERLINE tier (real library / framework limitation pending shard 19). No bare xfails, no `xfail("TODO")` patterns. F-N follow-up tracking via `REGISTERED_AS_OF_F5` set membership instead of a per-test `@pytest.mark.xfail` — the test-strategy compresses 9 separate trackers into one frozenset toggle. Acceptable.

Other test files in the EC-7 + EC-8 + F5.1 delta: zero `pytest.mark.xfail` / zero `pytest.xfail` calls — all assertions are unconditional.

### Sweep 8 — Spec-citation grep

```
$ grep -nE "EC-7|EC-8|F5\.1|Wave 5|Milestone 5" tests/e2e/test_envoy_cli_packaging_acceptance.py tests/e2e/test_session_continuity_5_channels.py tests/e2e/test_envoy_7_day_cross_channel_coherence.py tests/tier2/test_grant_moment_cascade_cross_channel.py tests/tier2/test_envelope_compiler_session_envelope_byte_identity.py tests/tier2/test_budget_no_double_billing_multi_channel.py | head -10
tests/tier2/test_grant_moment_cascade_cross_channel.py:3:"""EC-8(c): cascade revocation reaches descendant grants across channels.
tests/tier2/test_grant_moment_cascade_cross_channel.py:7:§ EC-8 line 255 + line 279:
tests/e2e/test_envoy_cli_packaging_acceptance.py:6:§ Wave 5 line 264 + § Milestone 5 line 329 + ``workspaces/phase-01-mvp/
tests/e2e/test_envoy_cli_packaging_acceptance.py:15:- ``workspaces/phase-01-mvp/02-plans/01-build-sequence.md`` Wave 5 line
tests/e2e/test_envoy_cli_packaging_acceptance.py:20:- ``workspaces/phase-01-mvp/02-plans/01-build-sequence.md`` Milestone 5
tests/e2e/test_envoy_7_day_cross_channel_coherence.py:3:"""EC-8 7-day cross-channel coherence battery.
[...]
```

Every new test file carries an EC-N or Milestone-5 spec-anchor in its module docstring's first 10 lines. Anchor lines map to verbatim file:line citations in `01-analysis/02-mvp-objectives.md` + `02-plans/01-build-sequence.md` + `02-plans/02-test-strategy.md`. No orphan acceptance tests — every assertion traces back to a spec § success criterion.

### Additional sweep — Probe-driven regex-for-semantic (per `/codify` validation gate)

```
$ grep -rEn 'def (verify|score|assert|check|probe)_[A-Za-z_]*(recommend|refus|complian|respons|intent|semantic|quality|outcome|narrative|reasoning)' --include='*.py' --include='*.mjs' --include='*.js' tests/ .claude/test-harness/ 2>/dev/null | xargs -I {} grep -lE '(re\.(search|match|findall)|str\.contains|grep -E|\.test\(|\.match\()' {} 2>/dev/null
(no output — no regex-for-semantic verifier functions)
```

Clean. The EC-7 + EC-8 + F5.1 batteries do not author any LLM-judge-without-schema, regex-on-prose, or bag-of-words scoring patterns. All assertions are structural per `rules/probe-driven-verification.md` MUST-3 (exit codes, byte-equality, sha256 hex-equality, raised exception types, integer counts, set equality).

### Additional sweep — Test execution

```
$ .venv/bin/python -m pytest tests/e2e/test_envoy_cli_packaging_acceptance.py -v 2>&1 | tail -5
========================= 3 passed, 9 xfailed in 2.28s =========================

$ .venv/bin/python -m pytest tests/e2e/test_session_continuity_5_channels.py -v 2>&1 | tail -3
============================== 21 passed in 6.93s ==============================

$ .venv/bin/python -m pytest tests/e2e/test_envoy_7_day_cross_channel_coherence.py tests/tier2/test_grant_moment_cascade_cross_channel.py tests/tier2/test_envelope_compiler_session_envelope_byte_identity.py tests/tier2/test_budget_no_double_billing_multi_channel.py -v 2>&1 | tail -3
============================== 14 passed in 0.66s ==============================
```

All 38 EC-7 / EC-8 / F5.1 test cases pass at HEAD (`5b93856`). The F5.1 xfail list (9 of 11 subcommands) is the documented Milestone-5 progress signal.

---

## Receipts

- **Task ID:** Round-4 rolling /redteam single quality-reviewer agent (this transcript).
- **SHA range scanned:** `aa50ef1` (Round-3 wave-4 digest convergence baseline, 2026-05-27) → `5b93856` (HEAD, 2026-05-28; merge commit of PR #50 chore-notes-F5).
- **Commits inspected (delta):** `528da54`, `53b13fa`, `c4f7500`, `68e0edf`, `b02c9b7` (PR #47); `48ceac0`, `c9b8698` (PR #48); `d293963`, `8b33ed2` (PR #49); plus chore commits `1505362`, `7d9f78a`, `c90f470`, `253d321` (session-notes + COC sync; not behavioral).
- **File paths read:**
  - `/Users/esperie/repos/dev/envoy/tests/e2e/test_envoy_cli_packaging_acceptance.py`
  - `/Users/esperie/repos/dev/envoy/tests/e2e/test_session_continuity_5_channels.py`
  - `/Users/esperie/repos/dev/envoy/tests/helpers/deterministic_llm_provider.py`
  - `/Users/esperie/repos/dev/envoy/tests/tier2/test_grant_moment_cascade_cross_channel.py`
  - `/Users/esperie/repos/dev/envoy/tests/tier2/test_envelope_compiler_session_envelope_byte_identity.py` (first 90 lines)
  - `/Users/esperie/repos/dev/envoy/tests/tier2/test_budget_no_double_billing_multi_channel.py` (first 80 lines)
  - `/Users/esperie/repos/dev/envoy/tests/e2e/test_envoy_7_day_cross_channel_coherence.py` (grep-only)
  - `/Users/esperie/repos/dev/envoy/tests/helpers/grant_moment_harness.py` (lines 75-135 — `StubTrustRuntime` + `make_runtime`)
  - `/Users/esperie/repos/dev/envoy/envoy/grant_moment/cascade_orchestrator.py` (lines 100-160 — orchestrator contract)
  - `/Users/esperie/repos/dev/envoy/envoy/grant_moment/runtime.py` (lines 1005-1030 — `revoke_prior_grant`)
  - `/Users/esperie/repos/dev/envoy/envoy/runtime/adapters/kailash_py.py` (lines 180-220 — production `trust_cascade_revoke`)
  - `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` (lines 90-125 — EC-7/EC-8 acceptance gates)
  - `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/02-plans/02-test-strategy.md` (lines 215-290 — EC-7/EC-8 test-strategy + de-scope #1)
  - `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/.session-notes` (lines 1-37 — outstanding ledger + read-first list)
  - `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/04-validate/round-3-wave-4-digest-convergence.md` (baseline reference)
- **Mechanical sweep commands run (8 + 2 additional):** verbatim outputs above.
- **Test execution receipts:** 3 passed + 9 xfailed (F5.1); 21 passed (EC-7); 14 passed (EC-8).

---

## EC-6 banking note

This round produces 0 CRIT + 0 HIGH on the rolling delta. Combined with Round-3 (`aa50ef1`, also 0 CRIT + 0 HIGH), the EC-6 "≥ 2 consecutive `/redteam` rounds at 0 CRIT + 0 HIGH" criterion has been met FOR THE ROLLING-ROUND SUBSCOPE (Wave-4 daily digest + EC-7 + EC-8 + F5.1). The full-Phase-01 EC-6 acceptance gate (per `01-analysis/02-mvp-objectives.md` line 92 + workspace outstanding ledger row F4) remains BLOCKED on F2 (independent ledger verifier, separate repo) per the cross-repo scope discipline in `.session-notes` line 18.

The 2 MED + 1 LOW findings are disposed in this report (per `commands/redteam.md` MEDIUM-disposition discipline): orchestrator's call after aggregation across wave-1 agents.
