# 13 — Model adapter — Phase 01 implementation deep-dive

**Document role:** Per the per-shard structure in `01-shard-plan.md` § 2 ("Per-shard structure"), this is the implementation deep-dive for the model-adapter primitive (shard 13 of /analyze). It cites frozen specs by path + section per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` ("citation by path + section is mandatory; paraphrase is forbidden"). It does NOT re-derive frozen specs.

**Date:** 2026-05-03 (shard 13).
**Status:** DRAFT — load-bearing for shard 8 (Boundary Conversation), shard 11 (Daily Digest), shard 10 (Grant Moment), shard 12 (Budget tracker), shard 14 (Connection Vault).
**Owning primitive:** Model adapter — the LLM substrate that every LLM-backed primitive depends on.

---

## 1. Source spec citation (frozen — DO NOT EDIT)

The model-adapter primitive is governed by:

- **`specs/model-adapter.md` § Purpose (lines 3–5)** — "Per-LLM-provider abstraction layer. Owns LLM response filtering, provider-risk annotation, multi-provider verification, model-output classification before tool-output sanitization. The runtime invocation surface is `prompt_send` / `model_invoke` per `specs/runtime-abstraction.md` §Prompt + tool-output."
- **`specs/model-adapter.md` § Provider-risk annotation (lines 14–36)** — `ProviderRisk` annotation schema (provider_id, model_family, model_version, risk_class ∈ {FV, Community, Self-hosted, Provider-bound}, training_data_leak_class, jurisdiction, data_retention_policy_url, annotated_at, foundation_attestation_signature_hex). The runtime persists this in the assembled-prompt's response Ledger entry.
- **`specs/model-adapter.md` § Response filter (lines 39–47)** — every model response MUST pass through (1) token-budget check, (2) leak-canary scan, (3) goal-drift classifier, (4) multi-turn accumulation check.
- **`specs/model-adapter.md` § Multi-provider verification (lines 49–51)** — Phase 04 high-stakes prompts MAY invoke ≥2 distinct providers and require intent-vector cosine ≥ 0.85 (T-030 defense). **Explicitly Phase 04, not Phase 01.**
- **`specs/model-adapter.md` § Cross-domain consumer mapping (lines 53–60)** — runtime-abstraction (`prompt_send` / `model_invoke`), tool-output-sanitization (consumes filtered output), envelope-model (token budgets + classifier ensemble pinning), foundation-ops (FV registry), connection-vault (provider credentials), ledger (`model_switch` entries).
- **`specs/model-adapter.md` § Error taxonomy (lines 62–73)** — 8 typed errors: ProviderUnreachable, ProviderRiskAnnotationMissing, ResponseTokenBudgetExceeded, TrainingDataLeakCanaryHit, GoalDriftDetected, AccumulatedInjectionDetected, MultiProviderConsensusFailed, ProviderSwitchRefusedByEnvelope.
- **`DECISIONS.md` § ADR-0006 — Model choice: BYOM at install, local default available (lines 210–229)** — "User picks at install. Options: local (Ollama / llama.cpp / MLX), Anthropic Claude, OpenAI GPT, DeepSeek, custom OpenAI-compatible endpoint. Routed through Kaizen `Delegate` provider abstraction. No lock-in."

These artifacts are frozen per Phase 00 closure. Per `journal/0001` and `rules/specs-authority.md` MUST Rule 5b, this shard MUST NOT propose edits to `specs/model-adapter.md`. If a HIGH-severity gap surfaces, escalate via `01-shard-plan.md` § 4 failure-mode protocol (§ 7 below).

## 2. Verified provider citation — Kaizen `LlmDeployment` + legacy provider surface

### 2.1 Verification protocol (per `03-kailash-py-mvp-readiness.md` § 5)

The Phase 00 survey (2026-04-21) graded the model-adapter row A/A. The `03-kailash-py-mvp-readiness.md` § 3 freshness delta lists 11 closed issues touching this surface (#791 #790 #788 #762 #763 #764 #761 #740 #736 #734 #735). Per § 5 verification protocol, this shard fetched issue-close metadata and inspected upstream code at `~/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/`.

Issue closure verification (state + closed-at, queried 2026-05-03):

| GH#  | Title                                                                                                     | Closed at  | Upstream landing point                                                                |
| ---- | --------------------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------- |
| #791 | feat(kaizen): cross-SDK parity for 12 Rust zero-arg `<provider>()` constructors (auth-strategy design)    | 2026-05-02 | `kaizen/llm/presets.py` lines 211, 833, 944, 1240, 1717 (preset registration)         |
| #790 | feat(kaizen): add CapabilityMatrix rows for 7 Python-only presets (cross-SDK alignment)                   | 2026-05-02 | `kaizen/llm/capabilities.py` (229 LOC); `LlmDeployment.supports()` line 358           |
| #788 | feat(kaizen): LlmDeployment.mock() cross-SDK parity with kailash-rs (test-utils gating design)            | 2026-05-02 | `kaizen/llm/testing/__init__.py` — `mock_preset` is test-only, NOT on production path |
| #762 | feat(kaizen): LlmDeployment.anthropic_compatible(base_url, api_key) escape hatch                          | 2026-05-03 | `kaizen/llm/presets.py` line 1775 (`anthropic_compatible_preset`)                     |
| #763 | feat(kaizen): LlmDeployment.supports() capability negotiation matrix                                      | 2026-05-01 | `kaizen/llm/deployment.py` line 358 (`supports()` returns 5-key dict, fail-closed)    |
| #764 | feat(kaizen): LlmDeployment.register_bedrock_region() runtime override (opt-in)                           | 2026-05-01 | `kaizen/llm/auth/aws.py` line 251 (`register_bedrock_region`)                         |
| #761 | feat(kaizen): LlmDeployment.openai_compatible(base_url, api_key) escape hatch                             | 2026-05-01 | `kaizen/llm/presets.py` line 1732 (`openai_compatible_preset`)                        |
| #740 | spec(kaizen): LlmClient.complete / .stream_completion missing — kaizen-llm-deployments.md vs code drift   | 2026-04-30 | **CLOSED AS SPEC-CORRECTION, NOT CODE-LANDING** — see § 7.1 ambiguity below           |
| #736 | bug(kaizen): \_calculate_usage_metrics crashes on None prompt_tokens from custom providers                | 2026-04-30 | usage-metrics defensive null-handling fix                                             |
| #735 | bug(kaizen): \_execute_strategy ThreadPoolExecutor drops contextvars                                      | 2026-04-30 | contextvars propagation fix                                                           |
| #734 | FallbackRouter.**init** silently inherits OPENAI_PROD_MODEL as default_model, leaking OpenAI-specific env | 2026-04-30 | env-leakage cleanup                                                                   |

11/11 verified closed. Per `03-kailash-py-mvp-readiness.md` § 2.1 ("closed-status ≠ landed-feature"), each closure was treated as a "look here" pointer; the corresponding code landing point is named above.

### 2.2 The `LlmDeployment` 4-axis abstraction

**Module path:** `kaizen.llm.deployment` (`packages/kailash-kaizen/src/kaizen/llm/deployment.py`, 410 LOC).

The four axes are: **wire protocol** (`WireProtocol` enum: 11 members including `OpenAiChat`, `AnthropicMessages`, `OllamaNative`, `BedrockInvoke`, `VertexGenerateContent`, `AzureOpenAi`, `CohereGenerate`, `MistralChat`, `HuggingFaceInference`), **endpoint** (`Endpoint` Pydantic model with SSRF-checked `base_url`, `path_prefix`, `required_headers`), **auth strategy** (`AuthStrategy` Protocol: `AwsBearerToken`, `ApiKeyBearer`, `GcpOauth`, `StaticNone`, `Custom`), and **resolved model** (`ResolvedModel` carries `default_model` + `streaming` + `retry`).

`LlmDeployment` is `frozen=True, extra="forbid"` per Pydantic v2 — no field writes after construction, no silent acceptance of unknown fields. `Endpoint.base_url` is validated `mode="before"` against `check_url()` (SSRF + IDN homograph defense per Round-1 redteam M2).

### 2.3 The 18+ presets

**Module path:** `kaizen.llm.presets` (`packages/kailash-kaizen/src/kaizen/llm/presets.py`, 2136 LOC). Verified preset factories registered via `register_preset(name, factory)`:

Direct providers: `openai`, `anthropic`, `google`, `cohere`, `mistral`, `perplexity`, `huggingface`, `ollama`, `docker_model_runner`, `groq`, `together`, `fireworks`, `openrouter`, `deepseek`, `lm_studio`, `llama_cpp`. Bedrock variants: `bedrock_claude`, `bedrock_llama`, `bedrock_titan`, `bedrock_mistral`, `bedrock_cohere`. Vertex variants: `vertex_claude`, `vertex_gemini`. Azure: `azure_openai`, `azure_entra`. Escape hatches (#761/#762): `openai_compatible`, `anthropic_compatible`. Default-model factories: `ollama_default_preset`, `lm_studio_default_preset`, `llama_cpp_default_preset`, `docker_model_runner_default_preset`. Test-only: `mock_preset` at `kaizen.llm.testing` (production import is BLOCKED per `rules/zero-tolerance.md` Rule 2).

Cross-coverage of ADR-0006's 5 enumerated options:

| ADR-0006 option          | Upstream preset(s)                                                                                                                       | Status                    |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| Local: Ollama            | `ollama`, `ollama_default_preset` (localhost:11434)                                                                                      | Verified                  |
| Local: llama.cpp         | `llama_cpp`, `llama_cpp_default_preset`                                                                                                  | Verified                  |
| Local: MLX               | (no first-class MLX preset; consumed via `openai_compatible` escape hatch when MLX serves OpenAI-compatible endpoint, e.g. `mlx-server`) | Adequate via escape hatch |
| Anthropic Claude         | `anthropic`, `bedrock_claude`, `vertex_claude`, `anthropic_compatible`                                                                   | Verified                  |
| OpenAI GPT               | `openai`, `azure_openai`, `azure_entra`                                                                                                  | Verified                  |
| DeepSeek                 | `deepseek`                                                                                                                               | Verified                  |
| Custom OpenAI-compatible | `openai_compatible(base_url, api_key)` (#761)                                                                                            | Verified                  |

### 2.4 `LlmDeployment.supports()` capability matrix (#763)

`deployment.py` line 358: `supports() -> Dict[str, bool]` returns 5 keys (`tools`, `vision`, `batch`, `caching`, `audio`). Fail-closed per `rules/security.md` § Fail-Closed Defaults: manual constructions with `preset_name=None` AND any unknown future preset return all-False. Cross-SDK parity with kailash-rs `LlmDeployment::supports()`. Per-preset rows live in `kaizen.llm.capabilities.for_preset(preset_name)`.

This is load-bearing for Envoy: per-channel default-model selection (§ 3.2 below) needs capability-aware routing — Daily Digest may pick a fast/cheap preset; Boundary Conversation may pick a tools-capable preset.

### 2.5 `LlmClient.from_env()` three-tier precedence (#498 / S7)

**Module path:** `kaizen.llm.client.LlmClient.from_env()` (line 164) + `kaizen.llm.from_env.resolve_env_deployment()`. Three-tier resolution:

1. **URI tier** — `KAILASH_LLM_DEPLOYMENT` holds a deployment URI (`bedrock://us-east-1/<model>`, `vertex://<project>/<region>/<model>`, `azure://<resource>/<model>?api-version=...`, `openai-compat://<host>/<model>`).
2. **Selector tier** — `KAILASH_LLM_PROVIDER` holds a preset name; required env vars resolved per preset.
3. **Legacy tier** — per-provider `*_API_KEY` autoselect (OpenAI > Azure > Anthropic > Google).

Coexistence emits `WARNING llm_client.migration.legacy_and_deployment_both_configured`; deployment tier wins. This satisfies `.claude/rules/env-models.md` Absolute Directive 2 — Envoy never reaches into `os.environ` for credentials; it constructs `LlmClient.from_env()` and lets the upstream resolver do the work.

### 2.6 Wire-send surface — `embed()` only on `LlmClient`; chat via legacy provider classes

**This is the load-bearing finding for Phase 01 (see § 7.1 ambiguity).**

`LlmClient.embed()` (`client.py` line 232) is the ONLY wire-send method on the new `LlmClient`. The docstring (lines 28–34) is explicit: "The wire-layer `complete()` send-path is deliberately NOT exposed here until every wire-protocol adapter has its dispatch function landed and exercised by a Tier 2 end-to-end test. Shipping a public `complete()` that raises `NotImplementedError` is BLOCKED per `rules/zero-tolerance.md` Rule 2 and `rules/orphan-detection.md` Rule 3 (Removed = Deleted, Not Deprecated)."

Issue #740 was closed as a **spec-correction**, not a code-landing — the spec mandate for `LlmClient.complete()` was the drift; the deferred implementation is the truth.

The chat-completion path Envoy actually needs (Boundary Conversation conversational turn, Daily Digest text rendering, Grant Moment summarization) is currently served by the **legacy provider surface** at `kaizen.providers.llm.{openai,anthropic,ollama,deepseek,google,...}`. Each exposes `chat(messages, **kwargs)`, `chat_async(...)`, `stream_chat(...)`. Verified at:

- `kaizen/providers/llm/openai.py` line 177 (`chat`), 312 (`chat_async`), 449 (`stream_chat`)
- `kaizen/providers/llm/anthropic.py` line 138 (`chat`), 211 (`chat_async`), 282 (`stream_chat`)
- `kaizen/providers/llm/ollama.py` line 107 (`chat`), 184 (`stream_chat`)

These remain functional and are the Phase 01 chat-completion substrate.

### 2.7 Ollama / llama.cpp / MLX (per Phase 00 survey item 25)

Per `phase-00-alignment/01-analysis/02-kailash-py-survey.md` item 25 (lines 780–802): grade A — `OllamaProvider` + `OllamaVisionProvider` at `packages/kailash-kaizen/src/kaizen/providers/ollama.py`. llama.cpp consumed via Ollama API compatibility. MLX consumed via `openai_compatible` escape hatch (§ 2.3 above).

### 2.8 Cross-reconciliation row 9 status

Per `phase-00-alignment/01-analysis/03-primitive-reconciliation.md` row 9 (`Delegate` provider abstraction): the Phase 00 disposition was "Use kailash-py for Phase 01. Issue on kailash-rs for full surface exposure" — issue tracked separately as ISS-16 (kailash-rs binding, Phase 02 concern). Phase 01 confirms this disposition holds: `kailash-py` is the wired substrate; `kailash-rs` binding consumption is deferred to Phase 02 per `DECISIONS.md` ADR-0001 phase migration.

## 3. Envoy-new-code surface

The model-adapter primitive's surface is materially split between **upstream-provided** (LlmDeployment + 18+ presets + auth + capabilities + `LlmClient.from_env`) and **Envoy-new-code** (the spec-defined response-filter pipeline + provider-risk annotation + Boundary-Conversation-grade chat wrapper). Phase 01 ships the BYOM glue + a thin chat shim; the response-filter pipeline (T-014, T-016, T-017) is **partially Phase 01 / partially Phase 04** per the spec text itself.

### 3.1 BYOM provider switching UX (per ADR-0006)

The first-launch picker presents the user with 5 options (local-Ollama / Anthropic / OpenAI / DeepSeek / custom-OpenAI-compatible) and writes the selection into `.env` keys consumed by `LlmClient.from_env()`. The picker writes:

- For local-Ollama: `KAILASH_LLM_PROVIDER=ollama`, plus `OLLAMA_BASE_URL` (default `http://localhost:11434/v1`) and a default `OLLAMA_DEFAULT_MODEL` env key the user fills with their pulled model name (e.g. `llama3.2`, `qwen2.5:7b`).
- For Anthropic: `KAILASH_LLM_PROVIDER=anthropic`, plus `ANTHROPIC_API_KEY` (sourced from the Connection Vault per shard 14, NOT written to `.env` in plaintext) and `ANTHROPIC_MODEL`.
- For OpenAI: `KAILASH_LLM_PROVIDER=openai`, plus `OPENAI_API_KEY` (Connection Vault) and `OPENAI_PROD_MODEL`.
- For DeepSeek: `KAILASH_LLM_PROVIDER=deepseek`, plus `DEEPSEEK_API_KEY` (Connection Vault) and `DEEPSEEK_MODEL`.
- For custom-OpenAI-compatible: `KAILASH_LLM_DEPLOYMENT=openai-compat://<host>/<model>` URI tier + the API key into the Connection Vault under a per-endpoint name.

Envoy MUST NOT hardcode model strings (`rules/env-models.md` Absolute Directive 2); the picker only writes the env-key NAMES + user-supplied model-string values. Default model values come from the user, not from Envoy code.

### 3.2 Per-channel default-model override

The spec is silent on per-channel model selection, but ADR-0006 ("BYOM at install") + the cost asymmetry between Boundary Conversation (high-quality multi-turn) and Daily Digest (cheap render-from-Ledger) implies a per-primitive override hook. Envoy-new-code provides:

- `EnvoyModelRouter` — a thin wrapper over `LlmClient.from_env()` that consults a primitive-keyed override map. Map keys: `boundary_conversation`, `daily_digest`, `grant_moment_summary`, `default`. Map values: env-key strings (e.g. `ENVOY_BOUNDARY_MODEL`, `ENVOY_DIGEST_MODEL`, `ENVOY_DEFAULT_MODEL`). When the env key is unset, falls back to the deployment's `default_model`.
- `EnvoyModelRouter.for_primitive("daily_digest")` returns an `LlmClient` whose `deployment.default_model` reflects the per-primitive override OR the global default. `LlmClient.with_deployment(d)` already exists upstream (line 215) for this exact pattern — no upstream change required.

Capability-aware routing uses `deployment.supports()` (#763) — e.g. if the user picked a non-tools-capable cheap preset for Daily Digest but the digest wants to call a tool, `EnvoyModelRouter.for_primitive("daily_digest")` raises `ProviderSwitchRefusedByEnvelopeError` (per `specs/model-adapter.md` § Error taxonomy line 73).

### 3.3 ProviderRisk annotation (Envoy-new-code, Phase 01)

`specs/model-adapter.md` § Provider-risk annotation (lines 14–36) is **NOT** in upstream `kaizen.llm.deployment` — verified by grep on `~/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/` for `ProviderRisk`, `risk_class`, `provider_risk` (zero matches). This is Envoy-new-code.

Phase 01 ships `EnvoyProviderRiskAnnotator`:

- Maps each `LlmDeployment.preset_name` to a `ProviderRisk` annotation per the schema in `specs/model-adapter.md` lines 17–29.
- `risk_class` for the 5 ADR-0006 options: `ollama` / `llama_cpp` / `lm_studio` / `docker_model_runner` → `Self-hosted`; `openai_compatible` / `anthropic_compatible` → `Community` (user-declared); `anthropic` / `openai` / `deepseek` / etc. → `Provider-bound` until Foundation publishes FV attestations (Phase 02+ via `specs/foundation-ops.md` registry).
- Persisted into the Ledger entry alongside every model invocation per `specs/model-adapter.md` line 16. Connects to shard 6 (Envoy Ledger) via the `model_switch` entry type.
- Phase 01 fail-closed default: provider-bound endpoints lacking Foundation attestation MUST be allowed by an explicit `provider_bound: true` flag in the envelope's operational dimension (per `specs/model-adapter.md` line 36); otherwise the runtime fails closed with `ProviderRiskAnnotationMissingError`. Phase 01 envelope-compiler shard 4 wires this flag into the operational dimension.

### 3.4 Response filter (Envoy-new-code; T-014/T-017 Phase 04, T-094 Phase 01)

Per `specs/model-adapter.md` § Response filter (lines 39–47), every response MUST pass 4 stages. Phase 01 partition:

| Stage                              | Spec line | Phase 01? | Disposition                                                                                                                                                                                |
| ---------------------------------- | --------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1. Token-budget check (T-094)      | 41        | Phase 01  | Implement against envelope `tool_output_budget_bytes`; truncate with sentinel; emit Ledger entry. Cheap, structural, Phase 01-feasible.                                                    |
| 2. Leak-canary scan (T-017)        | 42–43     | Phase 04  | Foundation MUST publish `envoy-registry:training-leak-canaries:v1` first (`specs/model-adapter.md` line 43 says "registered via foundation-ops.md by spec freeze N+1" — Phase 04 by spec). |
| 3. Goal-drift classifier (T-016)   | 44        | Phase 04  | Requires intent-vector embedding + cosine threshold calibration (open question in spec line 99). Not feasible without empirical calibration cohort.                                        |
| 4. Multi-turn accumulation (T-014) | 45        | Phase 04  | Requires session-state-tracked tokenized-context-overlap; depends on `specs/session-state.md` SessionObservedState wiring not yet in scope for Phase 01.                                   |

Phase 01 ships **Stage 1 only** (token-budget truncation). Stages 2–4 are pre-declared Phase 04 deferrals because the spec itself names Phase 04 dependencies (canary corpus governance, classifier calibration, session-state). This is NOT a workaround per `rules/zero-tolerance.md` Rule 4 — the spec defers them.

### 3.5 Multi-provider verification — DEFERRED to Phase 04

Per `specs/model-adapter.md` § Multi-provider verification (line 49): "Phase 04". Phase 01 does NOT ship this. The error class `MultiProviderConsensusFailedError` is defined but never raised in Phase 01.

### 3.6 Net Envoy-new-code surface (Phase 01)

Three modules under `envoy-agent/src/envoy/model/`:

1. `envoy.model.router.EnvoyModelRouter` — per-primitive `LlmClient` factory; ~100 LOC.
2. `envoy.model.risk.EnvoyProviderRiskAnnotator` + `ProviderRisk` dataclass — ~150 LOC + a preset→annotation map.
3. `envoy.model.response_filter.TokenBudgetFilter` (Stage 1 only) — ~80 LOC; rejects `ResponseTokenBudgetExceededError` and emits Ledger entry.

Total Envoy-new-code: ~330 LOC. Within shard budget per `rules/autonomous-execution.md` § Per-Session Capacity Budget.

## 4. Class structure sketch (interfaces only)

```python
# envoy/model/router.py
class EnvoyModelRouter:
    """Per-primitive LlmClient factory. Reads .env via LlmClient.from_env()."""

    PRIMITIVE_MODEL_ENV_KEYS: ClassVar[Dict[str, str]] = {
        "boundary_conversation": "ENVOY_BOUNDARY_MODEL",
        "daily_digest": "ENVOY_DIGEST_MODEL",
        "grant_moment_summary": "ENVOY_GRANT_MOMENT_MODEL",
        "default": "ENVOY_DEFAULT_MODEL",
    }

    def __init__(self, *, classification_policy: Optional[object] = None) -> None: ...

    def for_primitive(self, primitive: str) -> LlmClient:
        """Return an LlmClient whose deployment.default_model is the
        per-primitive override (from env) or the global default.
        Raises ProviderSwitchRefusedByEnvelopeError if the deployment's
        capability matrix does not satisfy the primitive's required caps."""

    def required_capabilities(self, primitive: str) -> Dict[str, bool]: ...

# envoy/model/risk.py
@dataclass(frozen=True)
class ProviderRisk:
    """Per spec model-adapter.md § Provider-risk annotation lines 17-29."""
    provider_id: str
    model_family: str
    model_version: str
    risk_class: Literal["FV", "Community", "Self-hosted", "Provider-bound"]
    training_data_leak_class: Literal["high", "medium", "low", "unknown"]
    jurisdiction: str  # ISO 3166-1 alpha-2 OR "mixed"
    data_retention_policy_url: str
    annotated_at: str  # ISO-8601
    foundation_attestation_signature_hex: Optional[str]  # ed25519 or None

class EnvoyProviderRiskAnnotator:
    """Maps LlmDeployment.preset_name to a ProviderRisk per ADR-0006 + spec."""

    def annotate(self, deployment: LlmDeployment) -> ProviderRisk: ...
    def emit_ledger_entry(self, ledger: EnvoyLedger, risk: ProviderRisk, action_id: str) -> None: ...
    def fail_closed_check(self, risk: ProviderRisk, envelope: RoleEnvelope) -> None:
        """Raise ProviderRiskAnnotationMissingError if risk_class is
        Provider-bound and envelope.operational does not allow provider_bound: true."""

# envoy/model/response_filter.py
class TokenBudgetFilter:
    """Stage 1 of spec § Response filter. Phase 01 ships this stage only."""

    def __init__(self, ledger: EnvoyLedger) -> None: ...

    def check(self, response_bytes: bytes, *, tool_output_budget_bytes: int,
              action_id: str) -> bytes:
        """Return response_bytes truncated to budget if exceeded; emit
        Ledger entry; raise ResponseTokenBudgetExceededError per spec
        line 68 if downstream consumption is forbidden by the envelope."""
```

Interfaces only. No production logic in this shard.

## 5. Integration points

### 5.1 With Boundary Conversation (shard 8)

Boundary Conversation (`specs/boundary-conversation.md`) generates conversational turns via `EnvoyModelRouter.for_primitive("boundary_conversation").chat(messages)`. The `chat()` call routes to the legacy `kaizen.providers.llm.<provider>.chat_async()` path (§ 2.6 above) until upstream `LlmClient.complete()` lands (Phase 02+). Each turn emits a `model_invoke` Ledger entry carrying the `ProviderRisk` annotation per § 3.3.

The EC-1 acceptance gate (per `02-mvp-objectives.md` § EC-1: "≥3 distinct first-time-user sessions complete BoundaryConversation in ≤25 minutes") depends on the model adapter delivering reliable conversational quality. Per-primitive override (`ENVOY_BOUNDARY_MODEL`) lets the user select a higher-capability model for this primitive.

### 5.2 With Daily Digest (shard 11)

Daily Digest renders text via `EnvoyModelRouter.for_primitive("daily_digest").chat(messages)`. The override env key (`ENVOY_DIGEST_MODEL`) typically points to a fast/cheap model since the digest is high-frequency (per `02-mvp-objectives.md` § EC-3: "scheduled Daily Digest fires at the user's local morning hour for ≥7 consecutive days"). Cost per digest × 7 days × N channels is the cost-control surface; capability matrix from `supports()` determines whether the picked preset is adequate.

### 5.3 With Grant Moment (shard 10)

Grant Moment summarizes the out-of-envelope request in plain language for the user-facing consent UI via `EnvoyModelRouter.for_primitive("grant_moment_summary")`. The summary is short — `ENVOY_GRANT_MOMENT_MODEL` may default to the same as Daily Digest. Cascade-revocation Ledger entries DO NOT need LLM rendering — only the human-facing summary does.

### 5.4 With Budget tracker (shard 12)

Per `specs/budget-tracker.md` (referenced by `03-kailash-py-mvp-readiness.md` row 12) and #603 (BudgetTracker threshold-callback API closed Apr 25), every `chat_async()` invocation produces a usage-metrics dict via `kaizen.providers.cost` infrastructure. #736 (closed Apr 30) fixed `_calculate_usage_metrics` crashing on `None prompt_tokens` from custom providers — a load-bearing robustness fix for `openai_compatible` / `anthropic_compatible` paths where token counts may be absent.

Envoy hooks the usage-metrics callback into the Budget tracker's per-action ceiling. Threshold breach fires a Grant Moment per shard 12 ↔ shard 10 wiring.

### 5.5 With Connection Vault (shard 14)

API keys (Anthropic, OpenAI, DeepSeek) come from the Connection Vault per `specs/connection-vault.md`. The first-launch picker writes the key under a per-provider name (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `<custom-endpoint-name>_API_KEY`); the EnvoyModelRouter retrieves it via the keychain wrapper at construction time and passes it into `LlmClient.from_env()` via the legacy-tier env-var contract.

`.env` itself MUST NOT carry plaintext keys (per `rules/security.md` § No Hardcoded Secrets + § No .env in Git). The Connection Vault is the actual storage; `.env` carries only model-name configuration and the `KAILASH_LLM_PROVIDER` selector.

### 5.6 With Envoy Ledger (shard 6)

Every model invocation produces three Ledger entry classes per `specs/model-adapter.md` line 60 + § Error taxonomy:

- `model_invoke` — successful invocation; payload includes `ProviderRisk` annotation, prompt hash, response hash (NOT raw text — privacy), token usage.
- `model_switch` — provider changed mid-session; payload includes prior + new `ProviderRisk`.
- `model_response_filter_<reason>` — token-budget truncation, leak-canary hit (Phase 04), goal-drift (Phase 04), accumulated-injection (Phase 04). Phase 01 ships only `model_response_filter_token_budget`.

The Ledger writer (per shard 6, the open #596 dependency) consumes these entries via the hash-chain primitive defined there.

## 6. Tier 2 / Tier 3 test surface

Per `rules/orphan-detection.md` MUST Rule 1 ("Every `db.*` / `app.*` Facade Has a Production Call Site") and `rules/testing.md` § "Tier 2 (Integration): Real infrastructure recommended", every adapter Envoy ships MUST have a Tier 2 wiring test that exercises the full chat loop end-to-end against a real provider.

### 6.1 Tier 2 wiring tests (one per ADR-0006 option)

| Test file                                                               | Provider     | Model env key          | Real call required?                                                                                                                                                                  |
| ----------------------------------------------------------------------- | ------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/integration/test_envoy_model_router_ollama_wiring.py`            | local-Ollama | `OLLAMA_DEFAULT_MODEL` | Yes — real Ollama at localhost:11434, no API key required                                                                                                                            |
| `tests/integration/test_envoy_model_router_anthropic_wiring.py`         | Anthropic    | `ANTHROPIC_MODEL`      | Yes — `ANTHROPIC_API_KEY` from .env; gate with `pytest.mark.skipif` if absent (per `rules/testing.md` § Test-Skip Triage Decision Tree, this is ACCEPTABLE — infra-conditional skip) |
| `tests/integration/test_envoy_model_router_openai_wiring.py`            | OpenAI       | `OPENAI_PROD_MODEL`    | Yes — `OPENAI_API_KEY` from .env; same skip discipline                                                                                                                               |
| `tests/integration/test_envoy_model_router_deepseek_wiring.py`          | DeepSeek     | `DEEPSEEK_MODEL`       | Yes — `DEEPSEEK_API_KEY` from .env; same skip discipline                                                                                                                             |
| `tests/integration/test_envoy_model_router_openai_compatible_wiring.py` | custom       | `ENVOY_CUSTOM_MODEL`   | Yes — caller-supplied base URL (test against local mock-OpenAI server, not external; cassette-recordable)                                                                            |
| `tests/integration/test_envoy_model_router_per_primitive_override.py`   | any          | various                | Asserts `ENVOY_BOUNDARY_MODEL` overrides the default for `for_primitive("boundary_conversation")`                                                                                    |
| `tests/integration/test_envoy_provider_risk_annotation_in_ledger.py`    | any          | any                    | Asserts the `model_invoke` Ledger entry carries the ProviderRisk annotation                                                                                                          |
| `tests/integration/test_envoy_token_budget_filter_truncation.py`        | any          | any                    | Asserts oversized responses produce `ResponseTokenBudgetExceededError` AND a Ledger `model_response_filter_token_budget` entry (Stage 1 only)                                        |

Each test loads `.env` via root `conftest.py` per `rules/env-models.md` ("ALWAYS Load .env Before Operations" + "For pytest: root `conftest.py` auto-loads `.env`"). Each test reads its model name from the env key — never hardcoded.

### 6.2 Tier 3 cassette test for CI

Tier 3 against real Anthropic / OpenAI / DeepSeek is cost-bearing and rate-limited. Phase 01 ships **one** Tier 3 cassette test per provider that records a single Boundary-Conversation-shaped exchange against the real provider (run once locally, recorded via `vcrpy` / `respx`) and replayed in CI. Cassettes pin the provider's exact response wire format — protecting against silent provider API drift.

Cassette files at `tests/e2e/cassettes/<provider>_boundary_conversation_v1.yaml`. Cassette refresh is a manual ritual at each release gate (per `rules/release.md`).

### 6.3 Local-Ollama tier (no API key required)

The Ollama Tier 2 path is the ONLY one that runs unconditionally in CI without secret-key provisioning. Per ADR-0006's "local default available" rationale, this is the structurally-most-important Tier 2 test: it proves the BYOM degraded-mode path (no cloud, no key, no payment) actually works. Per `rules/orphan-detection.md` Rule 2a "Crypto-Pair Round-Trip MUST Be Tested Through The Facade" — applied analogously here: the BYOM-pair (local-default + cloud-default) MUST be tested end-to-end through `EnvoyModelRouter`, not just through the upstream `LlmClient`.

### 6.4 Pytest plugin + marker discipline

Per `rules/testing.md` § "MUST: Pytest Plugin + Marker Declaration Pair": if any test uses `@pytest.mark.integration` or `vcrpy` cassettes, the package's `pyproject.toml` MUST declare the plugin in `[dev]` extras AND register the marker in `[tool.pytest.ini_options].markers` in the same commit shard 19 (pipx distribution) lands.

### 6.5 Env-var test isolation

The model-name env vars (`ENVOY_BOUNDARY_MODEL`, `ENVOY_DIGEST_MODEL`, etc.) are mutated across tests. Per `rules/testing.md` § "MUST: Serialize Env-Var-Mutating Tests Via Test-Module Lock": the integration tests above MUST share a module-scoped `threading.Lock` if any pair mutates the same env var. Use `monkeypatch.setenv` + `_env_serialized` fixture pattern per the rule's example.

## 7. Frozen-spec ambiguity (escalation candidates)

Per `01-shard-plan.md` § 4: HIGH-severity gaps trigger "STOP the deep-dive; convene MUST-Rule-5b sweep before continuing; spec edit goes through full-sibling redteam economics." The shard surfaces ONE ambiguity that may rise to HIGH and TWO that are LOW.

### 7.1 HIGH candidate — chat-completion wire-send substrate not on `LlmClient`

**Status:** HIGH candidate. Discussed below; recommendation is **HOLD**, not escalate, because the resolution is upstream-orthogonal and Phase 01 has a working substrate (legacy `kaizen.providers.llm.<provider>.chat_async()`).

**Observation:** `specs/model-adapter.md` § Purpose (line 5) cites "the runtime invocation surface is `prompt_send` / `model_invoke` per `specs/runtime-abstraction.md` §Prompt + tool-output". Upstream `LlmClient.complete()` was the natural Python landing point for `prompt_send`, but per § 2.6 above the upstream BLOCK on shipping a `complete()` stub means the new `LlmClient` exposes only `embed()` today.

The chat-completion path Boundary Conversation depends on is currently served by `kaizen.providers.llm.<provider>.chat_async()` — the legacy provider surface that pre-dates the `LlmDeployment` 4-axis design. This works, but means Envoy crosses TWO upstream surfaces in Phase 01: `LlmDeployment` for configuration + `kaizen.providers.llm.<provider>` for chat invocation.

**Why not HIGH-escalate:** The spec at `specs/model-adapter.md` does not name `LlmClient.complete()` specifically — it names "`prompt_send` / `model_invoke`" as runtime methods, which can be served by either surface. The two-surface Phase 01 wiring is consistent with the spec; the consolidation onto a single `LlmClient.complete()` is a Phase 02+ refactor when upstream lands the wire-protocol dispatchers. Per `rules/zero-tolerance.md` Rule 4 ("No Workarounds for Core SDK Issues"): we are NOT working around the upstream gap — we are using the supported alternative pattern (legacy provider chat) that exists. Filing an upstream issue for `LlmClient.complete()` to land is appropriate; gating Phase 01 on it is not.

**Disposition:** Note in shard 8 (Boundary Conversation) implementation that it uses the legacy `chat_async()` path; document the future migration to `LlmClient.complete()` when upstream ships it. No spec edit; no MUST-Rule-5b sweep.

### 7.2 LOW — leak-canary corpus governance (spec open-question 2)

`specs/model-adapter.md` § Open questions line 100: "Leak-canary corpus governance — Foundation publishes canary corpus, but rotation cadence vs leakage-via-publication trade-off is unresolved." This is the spec's own open question; Phase 04 (per § 3.4 above) deferral is the spec-acknowledged disposition. No escalation.

### 7.3 LOW — local-Ollama provider risk classification

`specs/model-adapter.md` § Open questions line 102: "Self-hosted provider attestation — what is the trust delta between Foundation-signed local-model annotation vs user-declared annotation; should self-hosted require additional posture downgrade?" This is the spec's own open question; § 3.3 above pre-declares Phase 01 disposition (`Self-hosted` risk class for local providers, no posture downgrade in Phase 01). No escalation.

## 8. Cross-references

### Frozen spec sources (DO NOT EDIT — `journal/0001` discipline)

- `specs/model-adapter.md` (lines 1–104) — primary spec
- `specs/runtime-abstraction.md` § Prompt + tool-output — `prompt_send` / `model_invoke` runtime methods (referenced)
- `specs/tool-output-sanitization.md` — receives this adapter's filtered output (downstream consumer)
- `specs/envelope-model.md` — `tool_output_budget_bytes` + `tool_output_classifier_ensemble` schema + `provider_bound: true` operational flag (referenced)
- `specs/foundation-ops.md` — provider annotation registry (Phase 02+ FV attestations)
- `specs/connection-vault.md` — provider API credentials (shard 14 dependency)
- `specs/ledger.md` — `model_switch` entries record provider transitions (shard 6 dependency)
- `specs/session-state.md` — multi-turn-accumulation tracking via SessionObservedState (Phase 04)
- `specs/threat-model.md` — T-014, T-016, T-017, T-030, T-094 (referenced)
- `DECISIONS.md` § ADR-0006 — Model choice: BYOM at install, local default available (lines 210–229)

### Phase 00 inheritance

- `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` item 25 (lines 780–802) — Ollama / llama.cpp / MLX adapter via Kaizen Delegate, A grade
- `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` row 9 — Delegate provider abstraction; Phase 01 disposition: use kailash-py
- `workspaces/phase-00-alignment/issues/manifest.md` — Phase 00 ISS manifest (no model-adapter ISS; #791 etc. are post-survey)

### Phase 01 sibling shards

- `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 10 (Model adapter A/A) + § 5 verification protocol
- `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` § EC-1 (Boundary Conversation) + § EC-3 (Daily Digest) — downstream EC dependents
- `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (shard 13 placement) + § 4 (failure-mode protocol) + § 5 (sequencing — model adapter has no Phase 01 primitive deps; gates Boundary Conversation LLM calls)
- `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` — re-derivation discipline

### Verified upstream code (`~/repos/loom/kailash-py/`, 2026-05-03)

- `packages/kailash-kaizen/src/kaizen/llm/deployment.py` (410 LOC) — LlmDeployment 4-axis abstraction
- `packages/kailash-kaizen/src/kaizen/llm/presets.py` (2136 LOC) — 18+ preset factories
- `packages/kailash-kaizen/src/kaizen/llm/capabilities.py` (229 LOC) — capability matrix per #790
- `packages/kailash-kaizen/src/kaizen/llm/client.py` — LlmClient.from_deployment / from_env / embed (complete deferred per #740 spec-correction)
- `packages/kailash-kaizen/src/kaizen/llm/from_env.py` — three-tier env precedence resolver
- `packages/kailash-kaizen/src/kaizen/llm/auth/aws.py` line 251 — register_bedrock_region (#764)
- `packages/kailash-kaizen/src/kaizen/llm/testing/__init__.py` — mock_preset (test-utils only)
- `packages/kailash-kaizen/src/kaizen/providers/llm/{openai,anthropic,ollama,deepseek}.py` — legacy provider surface with `chat`, `chat_async`, `stream_chat`

### Closed upstream issues (verified 2026-05-03 via `gh issue view --json closedAt,state,title`)

- terrene-foundation/kailash-py #791 — cross-SDK parity for 12 zero-arg `<provider>()` constructors (closed 2026-05-02)
- terrene-foundation/kailash-py #790 — CapabilityMatrix rows for 7 Python-only presets (closed 2026-05-02)
- terrene-foundation/kailash-py #788 — LlmDeployment.mock() cross-SDK parity (closed 2026-05-02)
- terrene-foundation/kailash-py #762 — anthropic_compatible escape hatch (closed 2026-05-03)
- terrene-foundation/kailash-py #763 — supports() capability matrix (closed 2026-05-01)
- terrene-foundation/kailash-py #764 — register_bedrock_region (closed 2026-05-01)
- terrene-foundation/kailash-py #761 — openai_compatible escape hatch (closed 2026-05-01)
- terrene-foundation/kailash-py #740 — LlmClient.complete spec-correction (closed 2026-04-30)
- terrene-foundation/kailash-py #736 — \_calculate_usage_metrics None handling (closed 2026-04-30)
- terrene-foundation/kailash-py #735 — \_execute_strategy contextvars (closed 2026-04-30)
- terrene-foundation/kailash-py #734 — FallbackRouter env leakage (closed 2026-04-30)

### Rule citations

- `.claude/rules/env-models.md` Absolute Directive 2 — `.env` is single source of truth for model names + API keys
- `.claude/rules/orphan-detection.md` MUST Rule 1 — every adapter has production call site + Tier 2 wiring test
- `.claude/rules/zero-tolerance.md` Rule 4 — no workarounds for SDK; legacy `chat_async()` is the supported alternative pattern, not a workaround
- `.claude/rules/testing.md` § Tier 2 + § Test-Skip Triage + § Env-Var Test Isolation
- `.claude/rules/security.md` § Fail-Closed Defaults — applied to `LlmDeployment.supports()` capability semantics
- `.claude/rules/specs-authority.md` MUST Rule 5b — narrow-scope edits BLOCKED; this shard does NOT propose spec edits

---

**Shard 13 closure:** This deep-dive identifies ~330 LOC of Envoy-new-code (router + risk annotator + Stage-1 token-budget filter), serving downstream EC-1 (Boundary Conversation onboarding) and EC-3 (Daily Digest 7-day cadence). Phase 01 implementation depends on `kaizen.llm.LlmDeployment` + `LlmClient.from_env()` + the legacy `kaizen.providers.llm.<provider>.chat_async()` surface; no upstream blockers; no HIGH spec ambiguities (one HIGH-candidate held, two LOWs spec-acknowledged).
