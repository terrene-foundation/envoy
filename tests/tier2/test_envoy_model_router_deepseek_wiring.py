"""Tier 2: T-01-23 — EnvoyModelRouter ↔ real DeepSeek provider.

Per shard 13 § 6.1 (`workspaces/phase-01-mvp/01-analysis/13-model-adapter-
implementation.md` lines 282-294): one Tier 2 test per ADR-0006 option.

API key: read from .env via root conftest.py (`DEEPSEEK_API_KEY`) per
`rules/env-models.md` Absolute Directive 2.
Model name: read from `DEEPSEEK_MODEL` env var per shard 13 § 6.1
table (falls back to `DEEPSEEK_PROD_MODEL` per kaizen's env hint).

Phase 01 scope note: kaizen does NOT ship a dedicated
``kaizen.providers.llm.deepseek`` legacy chat surface — DeepSeek uses
the OpenAI-compatible wire (``preset.wire == WireProtocol.OpenAiChat``)
which the new ``LlmClient`` will dispatch via OpenAiChat wire-protocol
adapters once ``complete()`` lands per #740. Until then, the Tier 2
coverage for DeepSeek is the preset construction + risk annotation
structural surface; a live-chat round-trip against the DeepSeek API
will land in T-02-40+ when the chat substrate consolidates.

This is the SAME scope clarification shard 13 § 7.1 records as the
HOLD disposition: legacy chat for proprietary endpoints without a
dedicated provider module is deferred to the LlmClient.complete()
landing.

Per `rules/testing.md` § Test-Skip Triage: when DEEPSEEK_API_KEY +
DEEPSEEK_MODEL are absent, the test SKIPs with infra-conditional
reason (ACCEPTABLE).
"""

from __future__ import annotations

import os
import threading

import pytest

from envoy.model import EnvoyProviderRiskAnnotator


_DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")
_DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL") or os.environ.get("DEEPSEEK_PROD_MODEL")

_ENV_LOCK = threading.Lock()


@pytest.fixture(autouse=False)
def _env_serialized():
    """Serialize env-var-mutating tests per rules/testing.md."""
    with _ENV_LOCK:
        yield


pytestmark = [
    pytest.mark.skipif(
        not _DEEPSEEK_KEY,
        reason=(
            "requires DEEPSEEK_API_KEY in .env "
            "(see https://platform.deepseek.com/); "
            "ACCEPTABLE skip per rules/testing.md test-skip triage"
        ),
    ),
    pytest.mark.skipif(
        not _DEEPSEEK_MODEL,
        reason=(
            "requires DEEPSEEK_MODEL / DEEPSEEK_PROD_MODEL env var per "
            "rules/env-models.md (NEVER hardcoded); ACCEPTABLE skip per "
            "rules/testing.md test-skip triage"
        ),
    ),
]


class TestDeepSeekPresetThroughRouter:
    """Real DeepSeek preset + risk annotation."""

    def test_deepseek_preset_yields_provider_bound_risk(self) -> None:
        """DeepSeek is a Provider-bound preset per shard 13 § 3.3
        until Foundation publishes FV attestations (Phase 02+)."""
        from kaizen.llm.presets import deepseek_preset

        assert _DEEPSEEK_MODEL is not None  # skip guard above
        assert _DEEPSEEK_KEY is not None
        deployment = deepseek_preset(api_key=_DEEPSEEK_KEY, model=_DEEPSEEK_MODEL)
        annotator = EnvoyProviderRiskAnnotator()
        risk = annotator.annotate(deployment)
        assert risk.risk_class == "Provider-bound"
        assert risk.provider_id == "deepseek"
        assert risk.model_family == _DEEPSEEK_MODEL

    def test_deepseek_deployment_carries_openai_compatible_wire(self) -> None:
        """DeepSeek inherits the OpenAI-chat wire per kaizen's preset
        definition. Pin the wire shape so a kaizen upgrade that flips
        the wire (e.g., to a DeepSeek-native wire) surfaces here
        rather than at the first chat call in production."""
        from kaizen.llm.deployment import WireProtocol
        from kaizen.llm.presets import deepseek_preset

        assert _DEEPSEEK_MODEL is not None
        assert _DEEPSEEK_KEY is not None
        deployment = deepseek_preset(api_key=_DEEPSEEK_KEY, model=_DEEPSEEK_MODEL)
        # Pin the wire — DeepSeek's API is OpenAI-compatible at the
        # /v1/chat/completions path.
        assert deployment.wire == WireProtocol.OpenAiChat
