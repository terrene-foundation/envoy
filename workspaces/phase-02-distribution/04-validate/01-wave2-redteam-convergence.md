# Phase-02 Wave-2 `/redteam` — Validation Report + Convergence Receipt

**Date:** 2026-06-11. **Phase:** redteam. **Posture:** L5_DELEGATED.
**Scope:** the Phase-02 IMPLEMENTED shards on `main` as of session start —
S1 (conformance harness), S2a (kailash-rs-bindings adapter), S4s/S4r/S4i
(durable store + store-poll rendezvous + `envoy init`), S8/S8e (FV registry +
EnterpriseDeploymentRecord), S9a (SKILL→envelope CO validator), S10 (OHTTP
key-config server + relay). NOT-yet-implemented shards were explicitly
out-of-scope.

**Branch:** `test/redteam-phase02-wave2-gate` (off `main` @ 84742b2). All fixes
committed here; awaiting human authorization for the PR to protected `main`.

## Convergence verdict — CONVERGED

All `commands/redteam.md` § Convergence Criteria met:

| #   | Criterion                         | Status                                                                         |
| --- | --------------------------------- | ------------------------------------------------------------------------------ |
| 1   | 0 CRITICAL                        | ✅ (R1 0, R2 0, R3 0, R4 0)                                                    |
| 2   | 0 HIGH                            | ✅ (R1 8 → all fixed; R2/R3/R4 0)                                              |
| 3   | 2 consecutive clean rounds        | ✅ Round 3 (delta) + Round 4 (full-scope) both 0/0/0/0                         |
| 4   | Spec compliance AST/grep verified | ✅ every cited symbol/test-path resolves; closure-parity ran the literal greps |
| 5   | New code has new tests            | ✅ every fix carries a regression test (`pytest --collect` verified)           |
| 6   | 0 mock data                       | ✅ `grep MOCK_/FAKE_/DUMMY_/SAMPLE_` in non-test prod code = 0                 |
| 7   | Eval-harness green + accreted     | ✅ for this wave — see note below                                              |

**Criterion-7 note:** this wave's findings were code-correctness / spec-accuracy
/ resource-lifecycle (NOT LLM-output semantic properties), so the accretion role
is served by the per-finding Tier-1/2/3 **regression tests** (the semantic
twin — a dedicated `tests/redteam-evals/` probe harness — adds value only when a
finding asserts an intent/refusal/hallucination property, which none here did).
A standing `tests/redteam-evals/` harness is flagged as a forest item for the
first wave that ships an LLM-output semantic surface (the BC ritual extraction
is the candidate when its prompt/refusal contracts are validated).

## Round-by-round

| Round  | Lenses                                                                                      | CRIT | HIGH | MED | LOW | Disposition                    |
| ------ | ------------------------------------------------------------------------------------------- | ---- | ---- | --- | --- | ------------------------------ |
| **R1** | spec-compliance (M1+M2, M3+M4), test-verification, security                                 | 0    | 8    | 5   | 9   | all 22 fixed (clusters A–D)    |
| **R2** | closure-parity, code-quality, user-flow walk, security                                      | 0    | 0    | 1   | 1   | both fixed (R2-Q-01, UF-R2-L1) |
| **R3** | closure-verify, adversarial security (delta surface)                                        | 0    | 0    | 0   | 0   | clean #1                       |
| **R4** | spec-compliance + code-quality + security (full-scope; agents throttled → completed inline) | 0    | 0    | 0   | 0   | clean #2                       |

(R1 code-quality + user-flow lenses were lost to a session limit and re-run in
R2; R4's parallel agents hit the server-side concurrency throttle
[`not your usage limit`] twice, so the deterministic full-scope sweep was
completed inline — mechanical sweeps + full suite + gates, the core of
criteria 4–6, after three rounds of expert-lens judgment.)

## Findings + fixes (24 total: 8 HIGH / 7 MED / 9 LOW)

### HIGH (Round 1)

- **W2G-001** `envoy init` re-run UX was a spec lie: `clean exit 30` unreachable
  because `TrustVault.create` raised `FileExistsError` before the write-once
  gate, after the user re-typed passphrase + 9 ritual answers. **Fix:** CLI
  vault-existence pre-check → exit 30 before prompting; `build_init_runtime`
  translates `FileExistsError` → `VaultAlreadyInitializedError`. (RISK)
- **W2G-002** rs adapter: 13 substrate-gated methods "forwarded" to a phantom
  `self._trust_store.<name>` surface (untyped `AttributeError` under DI).
  **Fix:** raise typed `RuntimeNotReadyError` naming the gating shard; workspace
  claim corrected to 18/31 wired + 13 gated. (GAP)
- **W2G-003** cross-spec contradiction: `session-state.md` promised
  "snapshot to Trust Vault **encrypted**"; shipped store is 0o600 plaintext.
  **Fix:** specs amended to the actual signed-not-encrypted posture +
  threat-model residual + owned value-anchored S5o-enc follow-up. (RISK)
- **W2G-004** grant-moment timeout never wrote the durable `expired` row →
  `count_pending_grants` over-counted; a late answerer could flip a dead grant
  to `resolved`. **Fix:** timeout writes `resolve_pending_grant(state="expired")`
  before raising; late-resolve refused. (RISK)
- **W2G-005** inline `TBD` markers in `independent-verifier.md` (spec-accuracy
  Rule 2). **Fix:** removed; decision lives in the S7v workspace todo. (GAP)
- **F1** HSTS was a dead config field (`require_hsts`/`hsts_offered` never read).
  **Fix:** `enforce_tls_policy` consumes both; advisory `HSTSPreloadMissingWarning`
  per network-security.md. (RISK)
- **F2** cert-pin mismatch raised the wrong type (`SNIStrippingDetectedError`);
  spec-mandated `CertPinMismatchError` unimplemented + untested. **Fix:** added
  the typed error + raise + behavioral test; None-default documented. (RISK)
- **F3** 7 phantom spec test-location citations for implemented behavior.
  **Fix:** repointed each to the resolvable real file. (GAP)

### MEDIUM

- **W2G-006** rs `trust_sign`/`envelope_intersect` zero direct tests + false
  coverage comment → direct-call tests added.
- **W2G-007** dispatch-observation docstring signature drift + present-tense
  claim with no call site → docstring fixed, claim softened to name S2b/S6a.
- **F4** S8 in-process-dict vs promised DataFlow `@db.model`, ownerless → owned
  value-anchored **S8-persist** follow-up gating network exposure.
- **F5** missing S8/S10 verification records + stale S8e t024 count (2→5) → added.
- **T-01** envoy-owned `Unclosed Nexus` ResourceWarning (tests didn't close
  built apps) → fixture close + pyproject comment corrected.
- **T-02** upstream kaizen `LlmClient` Ollama socket leak (no `close()`) →
  port-11434-scoped ResourceWarning filter (fail-safe; upstream-file candidate).
- **R2-Q-01** `build_init_runtime` partial-construction leak: vault left
  **unlocked** (master key in memory) if `trust_store.initialize`/
  `session_router.open` raised. **Fix:** acquisitions moved inside the cleanup
  try; innermost `finally` guarantees `vault.lock()`; 2 Tier-3 leak tests. (RISK)

### LOW

- **W2G-008** Region-1 spec table missing `resolution_sig` column → added.
- **W2G-009** stale phase/deferred anchors (feature_flags, runtime `__init__`,
  CLI help, "30 methods" → 31) → reworded.
- **W2G-010** `anchor_minted_at` not microsecond-padded → `timespec="microseconds"`.
- **F6** `skill-ingest.md` step-5 S9b forward-ref → reworded to shipped surface.
- **F7** S9a todo overstated "install flow §69" → scoped to the shipped validator
  library; `envoy skill install` CLI noted as not-yet-shipped.
- **SEC-LOW-1** key-config expiry lexicographic ISO compare (Z vs +00:00) →
  parsed-instant compare; fail-closed on malformed.
- **SEC-LOW-2** `verify_key_config_signatures` dropped `StewardQuorumInputError`
  → both quorum errors map to `KeyConfigSignatureError`, neither fails open.
- **T-03** deepseek skip mislabeled → names the upstream kaizen packaging gap.
- **UF-R2-L1** `python -m envoy` failed (no `__main__`) → added re-export. (GAP)

## New deliverable surfaced by the user-flow walk (security-adjacent)

The Wave-2 user-flow walk surfaced a **keychain foot-gun**: `envoy init` stored
the ledger + session signing keys in the real OS keychain with no override, so
it could not run headless / in CI / under a non-interactive agent (it errored
"keychain cannot be found"). Per the co-owner's choice, the **root-cause fix**
landed: `ENVOY_KEYRING` closed-allowlist resolver (unset → OS keychain default;
`memory` → in-process ephemeral backend with a loud warning; any other value →
fail-closed refusal), wired into `envoy init` (clean exit 32 on a bad selector).
The real OS keychain stays the secure default; verified untouched by the walk.
7 regression tests. (RISK — closed.)

## Gate receipts (final, on the branch HEAD)

- Full suite: **2098 passed, 9 skipped (infra-conditional), 2 xfailed
  (chat/grant tripwires)** — `uv run pytest -q`.
- `uv run mypy envoy` → no issues (161 files); `uv run pyright envoy` → 0/0/0;
  `uv run ruff check .` → all checks passed.
- Log triage: **0 WARN+** in the shipped pytest config (the Nexus + Ollama leaks
  are closed / port-scoped; the only upstream residual `Unclosed AsyncLocalRuntime`
  stays scoped-filtered with a tracked upstream note).
- Spec-accuracy scan: 0 split-state/TBD in any implemented-shard spec; all cited
  symbols/test-paths resolve.

## Pre-existing items noted (NOT wave-2 blockers, out of validated scope)

- 3 inline `TBD`s in Phase-03 / future-cadence specs (`shared-household.md:165`,
  `tool-output-sanitization.md:172`, `acceptance-metrics.md:90`) — pre-existing
  spec-accuracy debt in specs for unimplemented behavior; fix when those phases
  are validated.
- Queued/bounded (unchanged, owners assigned): P7 (S10 M2/L1/L2 → S11), P9
  (sqlite WAL/SHM window), P11 (genesis TOCTOU bounded by `TrustVault.create`),
  S8-persist (DataFlow swap before network exposure), S5o-enc (encryption-at-rest
  with S5o).
