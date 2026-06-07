# model-adapter

## Purpose

Per-LLM-provider abstraction layer. Owns LLM response filtering, provider-risk annotation, multi-provider verification, model-output classification before tool-output sanitization. The runtime invocation surface is `prompt_send` / `model_invoke` per `specs/runtime-abstraction.md` §Prompt + tool-output; this spec is the integration owner for the provider-side primitives that anchor doc 09 v3 §3 references as `specs/model-adapter.md`.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/05-runtime-abstraction.md v2 §Model adapter` + `workspaces/phase-00-alignment/01-analysis/09-threat-model.md v3 §3 T-014 / T-016 / T-017 / T-030 / T-094`.
- **Threats mitigated:** T-014 multi-turn accumulated injection (model-side residual after tool-output sanitization), T-016 goal drift across provider switches, T-017 training-data extraction defense (response filter + leak-canary), T-030 compromised model provider, T-094 model-response DoS (oversized response + classifier saturation).
- **BETs tested:** BET-2 structural/semantic partition (model output is the boundary between semantic LLM and structural Envoy), BET-6 cross-provider byte-identity for spec paths.

## Provider-risk annotation

Every model-adapter MUST carry a `ProviderRisk` annotation that the runtime persists in the assembled-prompt's response Ledger entry:

```json
{
  "provider_id": "openai | anthropic | google | local-llama | local-ollama | ...",
  "model_family": "<provider's model family identifier>",
  "model_version": "<provider's version string>",
  "risk_class": "FV | Community | Self-hosted | Provider-bound",
  "training_data_leak_class": "high | medium | low | unknown",
  "jurisdiction": "<iso 3166-1 alpha-2 OR 'mixed'>",
  "data_retention_policy_url": "<https://...>",
  "annotated_at": "<iso8601>",
  "foundation_attestation_signature_hex": "<ed25519 OR null for self-hosted>"
}
```

`risk_class` mapping:

- **FV (Foundation-Verified)** — Foundation has signed the provider's annotation; provider has agreed to publish data-retention policies with Foundation-published audit cadence.
- **Community** — community-attested annotation; user assumes risk.
- **Self-hosted** — local model (Ollama, llama.cpp, MLX, GGUF); annotation is user-declared, not Foundation-signed.
- **Provider-bound** — proprietary endpoint with no annotation; runtime fails closed unless envelope explicitly allows `provider_bound: true`.

## Response filter

Every model response MUST pass through:

1. **Token-budget check** — response bytes ≤ envelope `tool_output_budget_bytes`; truncate with sentinel if exceeded (T-094 defense).
2. **Leak-canary scan** — Foundation-published canary corpus (`envoy-registry:training-leak-canaries:v1` — registered via foundation-ops.md by spec freeze N+1) of synthetic-but-distinctive strings the user has NEVER input; substring match → flag the response as potential training-data leak (T-017).
3. **Goal-drift classifier** — comparison of response intent vector against the prompt-assemble's pinned envelope-goal vector; cosine drift > 0.4 → `GoalDriftDetectedError` (T-016).
4. **Multi-turn accumulation check** — sum of session's recent N=10 responses' tokenized-context-overlap; threshold drift detected → `AccumulatedInjectionDetectedError` (T-014).

Output → fed into `tool_output_sanitize` (specs/tool-output-sanitization.md) for the structural-defense pass.

## Multi-provider verification (Phase 04)

For high-stakes prompts (above Financial / Communication / Data Access ceiling), the runtime MAY invoke ≥2 distinct providers and require intent-vector cosine ≥ 0.85 OR refuse the action (T-030 defense). This is the cryptographic counterpart to the runtime's `model_switch` Ledger entry: providers are diverse not just within a session but per-prompt.

## Cross-domain consumer mapping

- specs/runtime-abstraction.md §Prompt + tool-output — `prompt_send` / `model_invoke` runtime methods consume this adapter.
- specs/tool-output-sanitization.md — receives the model-adapter's filtered output as input to structural-pattern + classifier-ensemble pass.
- specs/envelope-model.md — `tool_output_budget_bytes` + `semantic_checks.tool_output_classifier_ensemble` pinning.
- specs/foundation-ops.md — registry-side annotation source (FV provider attestations).
- specs/connection-vault.md — provider API credentials (OpenAI key, Anthropic key, etc.).
- specs/ledger.md — `model_switch` entries record provider transitions.

## Error taxonomy

| Error                                  | Trigger                                                                                                   | User action                                                                               | Retry                      |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | -------------------------- |
| `ProviderUnreachableError`             | Provider endpoint unreachable / 5xx                                                                       | Switch to fallback provider OR pause action                                               | Auto (with backoff)        |
| `ProviderRiskAnnotationMissingError`   | Model invocation against provider lacking annotation AND envelope does not allow `provider_bound: true`   | Surface fail-closed; user opts in via envelope edit                                       | Manual after envelope edit |
| `ResponseTokenBudgetExceededError`     | Response bytes > `tool_output_budget_bytes`                                                               | Truncate with sentinel; emit Ledger entry; refuse downstream feed (T-094)                 | Auto (truncated)           |
| `TrainingDataLeakCanaryHitError`       | Leak-canary substring match in response                                                                   | Halt; surface to user as suspected training-data extraction event (T-017)                 | Never                      |
| `GoalDriftDetectedError`               | Goal-drift classifier cosine drift > 0.4                                                                  | Refuse response; user re-prompts with restated goal (T-016)                               | Manual after re-prompt     |
| `AccumulatedInjectionDetectedError`    | Session multi-turn overlap threshold breached (T-014)                                                     | Force session boundary; recover via specs/session-state.md `session_boundary` algorithm   | Auto after session reset   |
| `MultiProviderConsensusFailedError`    | High-stakes verification: provider intent-vector cosine < 0.85 (T-030)                                    | Refuse high-stakes action; user reduces stakes OR explicitly accepts single-provider risk | Manual after envelope edit |
| `ProviderSwitchRefusedByEnvelopeError` | Runtime `model_switch` blocked by envelope (operational dim. tool-allowlist excludes the target provider) | User updates envelope.operational.tool_allowlist OR uses alternative                      | Manual after envelope edit |

## Cross-references

- specs/runtime-abstraction.md — `prompt_assemble` / `prompt_send` / `model_invoke` runtime methods + `AssembledPrompt` schema.
- specs/tool-output-sanitization.md — downstream sanitizer receives this adapter's output.
- specs/envelope-model.md — `tool_output_budget_bytes` + `tool_output_classifier_ensemble` schema; goal-drift threshold; multi-provider policy.
- specs/foundation-ops.md — provider annotation registry.
- specs/connection-vault.md — provider API credentials.
- specs/ledger.md — `model_switch` entries.
- specs/session-state.md — multi-turn-accumulation tracking via SessionObservedState.
- specs/threat-model.md — T-014, T-016, T-017, T-030, T-094.

## Test location

Phase 01 ships the model router, BYOM picker, provider-risk annotation, and the response token-budget filter. Tested in-repo:

- `tests/tier2/test_envoy_provider_risk_annotation_in_ledger.py` + `tests/tier1/test_envoy_model_risk_annotator.py` — provider-risk annotation persistence in the Ledger across provider switches.
- `tests/tier1/test_envoy_model_byom_picker.py` — BYOM provider/model pick + supported-choices surface.
- `tests/tier1/test_envoy_model_token_budget_filter.py` + `tests/tier2/test_envoy_token_budget_filter_truncation.py` — response token-budget `TRUNCATION_SENTINEL` truncation at the configured budget.

## Out of scope (this phase)

The multi-provider consensus + injection / goal-drift defenses are Phase-04 surfaces; their first `raise` sites land then (typed-error stubs present in Phase 01 per `envoy/model/errors.py`):

- Multi-provider consensus high-stakes (dual-provider intent-vector cosine ≥ 0.85) — Phase 04.
- T-014 multi-turn accumulated injection, T-016 goal-drift across provider switch, T-017 training-data-leak canary, T-030 compromised-provider consensus, T-094 model-response DoS — Phase 04.

## Open questions

1. Goal-drift cosine threshold (currently 0.4) — empirical calibration needed; some legitimate creative-task prompts produce drift > 0.4 that should not be blocked.
2. Leak-canary corpus governance — Foundation publishes canary corpus, but rotation cadence vs leakage-via-publication trade-off is unresolved.
3. Multi-provider verification cost model — Phase 04 high-stakes invocations cost ≥2× per call; per-action ceiling needed in envelope.financial.
4. Self-hosted provider attestation — what is the trust delta between Foundation-signed local-model annotation vs user-declared annotation; should self-hosted require additional posture downgrade?
5. Provider-bound endpoints (no annotation) — should be supported at all in Phase 03+, or should the structural defense be "no annotation = no use" with no opt-out?
