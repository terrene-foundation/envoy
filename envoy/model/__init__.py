"""envoy.model — model adapter primitive (T-01-22, Phase 01).

Implements `specs/model-adapter.md` per shard 13
(`workspaces/phase-01-mvp/01-analysis/13-model-adapter-implementation.md`).

Phase 01 Envoy-new-code surface (~330 LOC per shard 13 § 3.6):

* :class:`EnvoyModelRouter` — per-primitive :class:`LlmClient` factory
  with capability-aware refusal. Wraps :meth:`LlmClient.from_env` from
  kaizen-py.
* :class:`ProviderRisk` + :class:`EnvoyProviderRiskAnnotator` — the
  9-field annotation per spec lines 17-29 + the preset→annotation map
  per shard 13 § 3.3 (ollama/llama_cpp/lm_studio/docker_model_runner →
  Self-hosted; openai_compatible/anthropic_compatible → Community;
  anthropic/openai/deepseek/etc → Provider-bound until Foundation
  Verified attestation lands in Phase 02+).
* :class:`TokenBudgetFilter` — Stage 1 of the 4-stage response filter
  pipeline per spec lines 39-47. Stages 2-4 are Phase 04 per shard 13
  § 3.4 (leak-canary corpus, goal-drift classifier, multi-turn
  accumulation — each requires Phase 04-only infrastructure).
* :func:`byom_pick` — first-launch BYOM picker per ADR-0006 + shard 13
  § 3.1. Routes API keys to the Connection Vault per shard 14 § 3.1
  step 9; never writes plaintext keys to ``.env``.
* 8 typed errors per spec § Error taxonomy (lines 62-73). Phase 01
  actively raises 4 (:class:`ProviderUnreachableError` at chat-call
  sites, :class:`ProviderRiskAnnotationMissingError`,
  :class:`ResponseTokenBudgetExceededError`,
  :class:`ProviderSwitchRefusedByEnvelopeError`); the remaining 4 are
  defined for ``except``-taxonomy stability and raised at Phase 04
  filter / multi-provider sites.

Tier 2 wiring (real Ollama / cassette-recorded Anthropic+OpenAI+
DeepSeek) lands in T-01-23 per the workspace todo and shard 13 § 6.

Public facade per `rules/orphan-detection.md` Rule 6 — every module-
scope import in this file appears in ``__all__``.
"""

from envoy.model.byom_picker import (
    SUPPORTED_CHOICES,
    PickResult,
    byom_pick,
)
from envoy.model.errors import (
    AccumulatedInjectionDetectedError,
    GoalDriftDetectedError,
    ModelAdapterError,
    MultiProviderConsensusFailedError,
    ProviderRiskAnnotationMissingError,
    ProviderSwitchRefusedByEnvelopeError,
    ProviderUnreachableError,
    ResponseTokenBudgetExceededError,
    TrainingDataLeakCanaryHitError,
)
from envoy.model.response_filter import TRUNCATION_SENTINEL, TokenBudgetFilter
from envoy.model.risk import (
    EnvoyProviderRiskAnnotator,
    ProviderRisk,
    RiskClass,
    TrainingDataLeakClass,
)
from envoy.model.router import EnvoyModelRouter

__all__ = [
    # Router
    "EnvoyModelRouter",
    # Risk annotation
    "EnvoyProviderRiskAnnotator",
    "ProviderRisk",
    "RiskClass",
    "TrainingDataLeakClass",
    # Response filter (Stage 1)
    "TRUNCATION_SENTINEL",
    "TokenBudgetFilter",
    # BYOM picker
    "PickResult",
    "SUPPORTED_CHOICES",
    "byom_pick",
    # Errors (8 spec-defined + base)
    "AccumulatedInjectionDetectedError",
    "GoalDriftDetectedError",
    "ModelAdapterError",
    "MultiProviderConsensusFailedError",
    "ProviderRiskAnnotationMissingError",
    "ProviderSwitchRefusedByEnvelopeError",
    "ProviderUnreachableError",
    "ResponseTokenBudgetExceededError",
    "TrainingDataLeakCanaryHitError",
]
