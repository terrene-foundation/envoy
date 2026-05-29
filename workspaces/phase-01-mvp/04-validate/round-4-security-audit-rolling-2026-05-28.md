# Round-4 Security Audit (Rolling) — 2026-05-28

Baseline: `aa50ef1` (Round-3 wave-4 digest convergence — clean)
HEAD: `5b93856`
Auditor: security-reviewer
Delta scope: PRs #47, #48, #49 (commits `528da54..68e0edf`)

---

## 1. Verdict

**Findings: 0 CRIT + 0 HIGH + 0 MED + 2 LOW**

The delta is test-code-only (no production source changes) and ships:

1. F5.1 CLI packaging acceptance test (Tier 3 subprocess against `.venv/bin/envoy`)
2. EC-7 5-channel session continuity battery + Protocol-Satisfying Deterministic LLM Adapter
3. EC-8 7-day cross-channel coherence battery + Tier-2 cascade tests

No hardcoded secrets, no unparameterized SQL (no SQL at all in this delta), no
`shell=True`, no `eval`/`exec`/`__import__`, no `unittest.mock` usage in
Tier-2/Tier-3 paths under audit, no wall-clock-dependent assertions, no `.env`
file references, no privilege-escalation paths exposed by the cascade test, no
verifier-source-shared shim that would defeat EC-4/EC-9.

Two LOW informational findings are forensic — not security failures — recorded
to keep the audit-trail honest.

---

## 2. Findings table

| ID  | Severity | File:Line                                               | Threat class         | Claim                                                                                                                                                                                                                                                                                                                                                             | Evidence command                                                                                    |
| --- | -------- | ------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| L-1 | LOW      | tests/e2e/test_session_continuity_5_channels.py:170,179 | Test-fixture secrets | `passphrase = f"phase01-ec7-passphrase-{principal_id}"` is a deterministic, in-test-built passphrase for an in-`tmp_path` vault. NOT a production key. Pattern is clear from prefix + format-string + tmp_path-scoped vault file. No production exposure. Informational only — confirms the audit reviewed and dispositioned the literal string.                  | `grep -n 'passphrase' tests/e2e/test_session_continuity_5_channels.py`                              |
| L-2 | LOW      | tests/e2e/test_session_continuity_5_channels.py:383-457 | Test-fixture secrets | Channel adapter constructor placeholders use prefix `placeholder-` and constructor docstring (line 352-355) explicitly documents these as placeholder values that "the secret material only fires on outbound API calls, which are not exercised here." No real Telegram/Slack/Discord secrets. Informational disposition confirming the prefix discipline holds. | `grep -nE 'placeholder-(telegram\|slack\|discord)' tests/e2e/test_session_continuity_5_channels.py` |

No CRIT, HIGH, or MED. All five threat categories named in the task brief are
CLEAN — see § 4.

---

## 3. Mechanical sweeps (verbatim output)

### Sweep 1 — Secrets / API-key/token patterns in test sources under audit

```
$ grep -rEn 'api_key|secret|password|token|sk-[a-zA-Z0-9]{20,}' \
    tests/e2e/test_envoy_cli_packaging_acceptance.py \
    tests/e2e/test_session_continuity_5_channels.py \
    tests/e2e/test_envoy_7_day_cross_channel_coherence.py \
    tests/helpers/deterministic_llm_provider.py \
    tests/tier2/test_grant_moment_cascade_cross_channel.py \
    tests/integration/test_grant_moment_cross_channel_confirm_failed.py
```

Hits (all dispositioned):

- `tests/e2e/test_session_continuity_5_channels.py:48` — docstring word "secrets" (prose).
- `tests/e2e/test_session_continuity_5_channels.py:112,242` — `_CANNED_REPLIES["S7_visible_secret"]` — boundary-conversation prompt-reply test fixture; the literal `"open sky"` is the boundary-conversation "visible secret" feature ITSELF (S7 in the spec), not a production secret. Disposition: by design, see specs/boundary-conversation S7VisibleSecretSignature.
- `tests/e2e/test_session_continuity_5_channels.py:170,179` — `passphrase = f"phase01-ec7-passphrase-{principal_id}"` — Finding L-1.
- `tests/e2e/test_session_continuity_5_channels.py:352-355` — docstring explicitly naming "placeholder" discipline.
- `tests/e2e/test_session_continuity_5_channels.py:383,396-397,417,444,449-450,457` — channel-adapter placeholder fixtures — Finding L-2.
- `tests/helpers/deterministic_llm_provider.py:96,113` — comment + canned summary referencing the S7 visible-secret extraction shape. Not a credential.

No sk- prefixes, no `password = "..."` assignments, no real channel tokens, no
Bearer tokens, no API keys. Filed two LOW informational findings (L-1, L-2)
solely to record explicit disposition per `rules/zero-tolerance.md` Rule 1c
discipline (every "looks like a secret" hit gets dispositioned, not
silently skipped).

### Sweep 2 — Shell execution in F5.1 packaging test

```
$ grep -rEn 'shell\s*=\s*True|os\.system|subprocess\.(call|run|Popen)' \
    tests/e2e/test_envoy_cli_packaging_acceptance.py
3:"""F5 Wave-5 CLI packaging acceptance test (Tier 3 in-process subprocess).
46:- This is the in-process subprocess shape (Option A per F5 session-start
48:  as a real child process via ``subprocess.run``, asserts exit 0 + non-
69:import subprocess
136:def _run_help(envoy_bin: Path, *args: str) -> subprocess.CompletedProcess[str]:
141:    return subprocess.run(
```

`subprocess.run([str(envoy_bin), *args], capture_output=True, text=True,
timeout=30, check=False)` — list-form argv, NO `shell=True`, NO
shell-metacharacter exposure. The only argv elements are
`str(envoy_bin)` (resolved from `_repo_root()` via `__file__` — no user
input) plus literal strings `subcommand` + `"--help"` from the
`ELEVEN_SUBCOMMANDS` and `REGISTERED_AS_OF_F5` frozensets. Neither set
is parameterized from external input. **Clean.**

### Sweep 3 — Mocks in Tier-2/Tier-3 acceptance paths

```
$ grep -rEn 'MagicMock|unittest\.mock|@mock\.' tests/e2e/ tests/helpers/
tests/helpers/grant_moment_harness.py:5:(no ``unittest.mock``).
tests/helpers/deterministic_llm_provider.py:198:    ``unittest.mock``, no network — counts as a Protocol-Satisfying
```

Both hits are DOCSTRING references explicitly DISCLAIMING `unittest.mock`
usage (the helpers exist BECAUSE they're not mocks). No `MagicMock(...)`
construction, no `@patch` decorators, no `mock.Mock(...)` instantiation
anywhere in `tests/e2e/` or `tests/helpers/`. **Clean — Tier 3 + Protocol
Adapter contract held per `rules/testing.md` § "Protocol Adapters" exception.**

### Sweep 4 — Wall-clock-dependent assertions in EC-7 5-channel test

```
$ grep -rEn '\bsleep\(|time\.time\(\)\s*[<>=]|datetime\.now\(\)\s*[<>=]' \
    tests/e2e/test_session_continuity_5_channels.py
(no output)
```

EC-7 5-channel test has zero `sleep()`, zero `time.time()` comparison, zero
`datetime.now()` comparison. State transitions are driven by canned replies

- a bounded `for _ in range(32)` loop. **Clean — deterministic.**

Adjacent sweep against EC-8 7-day test:

```
$ grep -nE '\bsleep\(|time\.time\(\)|datetime\.now\(\)|timeout_seconds' \
    tests/e2e/test_envoy_7_day_cross_channel_coherence.py
95:    received = await runtime.await_decision(request.request_id, timeout_seconds=5)
```

Single hit: `timeout_seconds=5` is a generous async-await budget for the
in-process `await_decision` primitive (the spec test does NOT depend on
real wall-clock elapsing); the canned cascade resolves immediately. No
TOCTOU window — `post_decision` lands before `await_decision`. **Clean.**

### Sweep 5 — Dynamic-import / eval / exec surface

```
$ grep -rEn '__import__|exec\(|eval\(' tests/e2e/ tests/helpers/
(no output)
```

Zero hits across e2e + helpers. The `_PRESET_PROVIDER` monkeypatch in EC-7
uses `monkeypatch.setitem(...)` with a string-pair tuple that the runtime
itself resolves via its declared loader (`bc_runtime_mod._PRESET_PROVIDER`
dispatch); not an in-test dynamic import. **Clean.**

### Sweep 6 — `.env` file references / credentials inclusion

```
$ grep -rEn '\.env|\.env\.local|credentials' tests/e2e/ -i
tests/e2e/test_daily_digest_morning_delivery.py:35: (envelope module — not .env)
tests/e2e/test_session_continuity_5_channels.py:77: (envelope module — not .env)
tests/e2e/test_session_continuity_5_channels.py:319: (assertion text mentioning EnvelopeConfig)
```

All hits are `envelope` (the envelope-compiler module), NOT `.env`. No test
file under audit reads or writes a `.env` / `.env.local` / `credentials.json`.
**Clean.**

---

## 4. Threat-model coverage statement

### Category 1 — Secrets in test fixtures

**CLEAN.**

- F5.1 packaging test: no secret material at all (subprocess argv against `--help` only).
- EC-7 deterministic provider helper: no API keys, no models that require keys (returns canned JSON locally).
- EC-7 5-channel battery: per-principal passphrase pattern `phase01-ec7-passphrase-{principal_id}` is in-test-deterministic against a fresh `tmp_path/{principal_id}.vault` file; cannot be reused against a production vault (per-principal scope + tmp_path scope). Channel adapter constructors use explicit `placeholder-` prefixes documented in the constructor docstring (line 352-355). Both filed as LOW (L-1, L-2) for audit-trail completeness only.
- EC-8 7-day battery + Tier-2 cascade: no secrets; uses in-memory `InMemoryKeyManager` + `InMemoryAuditStore` per the existing `grant_moment_harness` helper.
- The pre-existing Tier-2 wiring tests (`test_envoy_model_router_*.py`) DO use real `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` from `os.environ.get(...)` per `rules/env-models.md` Absolute Directive 2; they predate baseline `aa50ef1` and are out of delta scope — flagged here only to confirm scope boundary held.

### Category 2 — Deterministic LLM stub injection surface

**CLEAN.**

`tests/helpers/deterministic_llm_provider.py` reviewed line-by-line:

- **No live LLM call**: `DeterministicProvider.chat()` does NOT import any provider SDK, does NOT touch any HTTP client, does NOT read env vars. Returns canned JSON from `_CANNED_EXTRACTIONS` based on substring-match dispatch on the prompt body (closed-vocab field-name set).
- **No log/persist of prompt content**: `chat()` reads `messages[-1].get("content", "")` for the substring dispatch and discards it. No logger, no file write, no network. The fingerprint dispatch table is `dict[str, dict]` static at module load; no mutation in `_pick_extraction`.
- **Protocol surface match**: `chat(messages, model=None, **kwargs) -> dict[str, Any]` matches the legacy kaizen provider surface the runtime invokes at `runtime._chat` (line 415-424 per docstring); `DeterministicModelRouter.for_primitive(name) -> LlmClient` matches the `EnvoyModelRouter.for_primitive` surface (line 382 per docstring). `_StubDeployment` exposes only `preset_name` + `default_model` (the two attributes the runtime reads via `getattr`). Duck-typing is documented; no production-drift risk because the runtime's access pattern is read-only via `getattr` against a closed two-attribute namespace.
- **Dispatch is structural, not LLM-routed**: per the helper's own contract (and `rules/agent-reasoning.md` permitted-exception #5 — Configuration branching), the fingerprint table is a substring-match on closed-vocab schema field names, NOT keyword-routing of LLM prose. This is precisely the Protocol-Satisfying Deterministic Adapter that `rules/testing.md` § "Protocol Adapters" exception permits.

### Category 3 — EC-8 cross-channel state coherence test (cascade revocation)

**CLEAN.**

- **No skipped-descendant privilege-retention path**: the EC-8 7-day battery's Day-7 cascade asserts `result.revoked_ids == frozenset({day1_grant_id, day3_grant_id, day6_grant_id})` (line 197) AND `result.missing_descendants == frozenset()` (line 198). The Tier-2 sibling test (`test_grant_moment_cascade_cross_channel.py`) explicitly covers the counter-case (line 161-192) where the cascade is incomplete: `CascadeIncompleteError` raises and `excinfo.value.result.missing_descendants` is asserted non-empty (line 191). Both halves of the cascade contract are pinned — the no-double-billing assertion (`tests/tier2/test_budget_no_double_billing_multi_channel.py`) is the third leg.
- **Multi-channel grant identity check**: per Tier-2 confirm-failed test (`test_grant_moment_cross_channel_confirm_failed.py`), the runtime explicitly refuses a confirm leg on the SAME channel as the decided channel (test `test_confirm_channel_same_as_decided_collapses_defense`, line 56-83). The "same-channel identity collision" failure mode the task brief named is structurally fenced AT THE RUNTIME, with the test pinning the defense.
- **No wall-clock TOCTOU**: assertions on cascade fire AFTER `submit_resolution()` awaits the resolution synchronously; there's no `sleep(); assert(...)` sequence that could race. The 8-iteration "offline day" loop at line 236 is also read-only (`_count_grant_moment_entries` only calls `ledger.query`, no mutation). The Ledger's `query()` is documented (and asserted at line 286) as deterministic-order, so the cross-channel state-equivalence claim (three queries from three "channel contexts" return identical entry ID lists) does NOT depend on wall-clock ordering.
- **Distinct cryptographic identities** (per task brief's `multi-operator-coordination.md` MUST-3 spirit): each session in EC-7 uses an INDEPENDENT `signing_key_id=f"ec7-key-{principal_id}"` + INDEPENDENT `device_id=f"device-ec7-{principal_id}"` (lines 184-191). No two sessions share a keypair; the Ledger chain hash-verifies per-principal (assertion at line 328). Same-principal collision is not possible because `principal_id = f"ec7-{channel_id}-session-{session_index}@example"` is unique per parametrized test case (line 308).

### Category 4 — F5.1 packaging acceptance

**CLEAN.**

- **No `shell=True`**: `subprocess.run([str(envoy_bin), *args], ..., timeout=30, check=False)` is list-form argv. Sweep 2 confirms zero `shell=True` / `os.system` / un-listed-argv calls.
- **No attacker-controllable input**: `envoy_bin` is resolved from `Path(__file__).resolve().parent.parent.parent / ".venv" / "bin" / "envoy"`. `__file__` is the test file's own path (not user input); `.resolve()` canonicalizes; the resulting path is then bound to a fixture and never re-constructed. `*args` are literal strings from the `ELEVEN_SUBCOMMANDS` and `REGISTERED_AS_OF_F5` frozensets at module scope — closed-set, no user input, no environment interpolation.
- **Path-traversal check**: `_repo_root()` walks UP 3 levels from `tests/e2e/test_envoy_cli_packaging_acceptance.py` per session-notes Trap #2 — that lands on the repo root deterministically. The `.. .. ..` chain is hard-coded (no `..` concatenated with user input). The Path is `.resolve()`-d once (line 104) so any future symlink in the parent chain is normalized; the path is then read-only thereafter. No write to or above this path. No `os.path.join(user_input, "..", ...)`-style traversal vector.
- **Windows scope-out documentation**: the test docstring lines 54-59 explicitly document the Windows scope-out (`The Option-B release smoke check exercises the .venv/Scripts/envoy.exe layout on a real Windows runner, not this per-PR gate.`). This is NOT a silent skip — the scope-out is explicitly in the test docstring AND the session-notes Trap #3. Per `rules/test-skip-discipline.md` ACCEPTABLE-tier: the Windows path lives in F5.3 by docstring scope-out, not a `pytest.mark.skip`-with-no-reason silent dismissal.
- **`envoy_bin` skip path**: when `.venv/bin/envoy` is absent, the fixture skips with `pytest.skip(...)` naming the operator's action (`uv sync`). This is the ACCEPTABLE-tier skip per `rules/test-skip-discipline.md` — names the constraint + action. Not a security defect.

### Category 5 — Verifier-related leakage / EC-4 + EC-9 boundary

**CLEAN.**

None of the test files in the delta import from a verifier package, expose a
`Ledger._private_for_verifier` shim, or share source with the verifier (the
verifier lives in a SEPARATE repository per session-notes F2 / blocked status).
All EC-8 tests in this delta:

- Use the `EnvoyLedger.verify_chain()` PUBLIC API only (line 328 EC-7, line 201 EC-8).
- Read Ledger state via the public `ledger.query(filter=..., since=..., until=...)` surface only.
- Do NOT inspect Ledger internals (e.g., `ledger._chain_root`, `ledger._verifier_pubkey`, or any underscore-prefixed accessor).

The "verifier shares zero source with producer" EC-4 / EC-9 invariant is held
trivially because the verifier source lives in a separate repository (F2 in
`.session-notes`). This delta does NOT introduce a test-shim that imports from
the verifier package or exposes producer internals via a sidecar API.

---

## 5. Receipts

### Files read

- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/.session-notes` (full, 36 lines)
- `/Users/esperie/repos/dev/envoy/tests/e2e/test_envoy_cli_packaging_acceptance.py` (full, 205 lines)
- `/Users/esperie/repos/dev/envoy/tests/helpers/deterministic_llm_provider.py` (full, 217 lines)
- `/Users/esperie/repos/dev/envoy/tests/e2e/test_session_continuity_5_channels.py` (full, 464 lines)
- `/Users/esperie/repos/dev/envoy/tests/e2e/test_envoy_7_day_cross_channel_coherence.py` (full, 288 lines)
- `/Users/esperie/repos/dev/envoy/tests/tier2/test_grant_moment_cascade_cross_channel.py` (lines 1-240)
- `/Users/esperie/repos/dev/envoy/tests/integration/test_grant_moment_cross_channel_confirm_failed.py` (lines 1-120)
- `/Users/esperie/repos/dev/envoy/tests/tier2/test_envoy_model_router_openai_wiring.py` (lines 1-90, scope-boundary confirmation)

### SHA range scanned

- Baseline: `aa50ef1` (Round-3 wave-4 digest convergence, clean)
- HEAD: `5b93856`
- Delta commits: `528da54..68e0edf` (per task brief)

### Mechanical sweeps run

- Sweep 1 (secrets/tokens) — 6 paths, all hits dispositioned (L-1, L-2 informational only)
- Sweep 2 (shell execution) — `tests/e2e/test_envoy_cli_packaging_acceptance.py` — list-form argv, no `shell=True`
- Sweep 3 (mocks in Tier 2/3) — `tests/e2e/`, `tests/helpers/` — 2 hits, both docstring disclaimers
- Sweep 4 (wall-clock assertions) — EC-7 + EC-8 e2e — zero blocking hits; single `timeout_seconds=5` async budget is non-flake-vector
- Sweep 5 (dynamic-import / eval / exec) — `tests/e2e/`, `tests/helpers/` — zero hits
- Sweep 6 (`.env` references) — `tests/e2e/` — zero `.env` hits; only `envelope` module imports

### Round-4 disposition

Test-code-only delta. No production source changed; therefore no production
security surface changed. The two LOW findings (L-1, L-2) are informational
audit-trail entries confirming that the literal strings matching the secret
regex were reviewed and confirmed safe (in-test deterministic passphrase
scoped to tmp_path; channel-adapter placeholder values explicitly documented
as such). Both are below the gate-block threshold per `rules/zero-tolerance.md`
Rule 1 — they are not deferred findings, they are dispositioned-as-not-defects
with evidence command attached.

Round-4 security gate: **PASS**. Proceed to next gate.
