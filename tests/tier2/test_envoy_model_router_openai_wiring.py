"""Tier 2: T-01-23 — EnvoyModelRouter ↔ real OpenAI provider.

Per shard 13 § 6.1 (`workspaces/phase-01-mvp/01-analysis/13-model-adapter-
implementation.md` lines 282-294): one Tier 2 test per ADR-0006 option.

API key: read from .env via root conftest.py (`OPENAI_API_KEY`) per
`rules/env-models.md` Absolute Directive 2 (NEVER hardcoded).
Model name: read from `OPENAI_PROD_MODEL` env var (per shard 13 § 6.1
table; falls back to `OPENAI_MODEL` then `DEFAULT_LLM_MODEL`).

Per `rules/testing.md` § Test-Skip Triage Decision Tree: when the key
is absent (developer machine without OpenAI budget, CI without secret
provisioning), the test SKIPs with an infra-conditional reason — the
ACCEPTABLE path, NOT BLOCKED. NO mocking — Tier 2 contract per
`rules/testing.md` § Tier 2.

Cost guard: cap max_tokens to ≤ 32 and rely on the developer's
choice of cheap model (typically gpt-4o-mini or gpt-5-nano). Per-test
cost is well under $0.01.
"""

from __future__ import annotations

import os
import threading

import pytest

from envoy.model import EnvoyProviderRiskAnnotator

_OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
# Resolution order per rules/env-models.md guidance — OPENAI_PROD_MODEL is
# the canonical Kailash env-key; OPENAI_MODEL is the second-choice; the
# project-wide DEFAULT_LLM_MODEL is the final fallback.
_OPENAI_MODEL = (
    os.environ.get("OPENAI_PROD_MODEL")
    or os.environ.get("OPENAI_MODEL")
    or os.environ.get("DEFAULT_LLM_MODEL")
)

_ENV_LOCK = threading.Lock()


@pytest.fixture(autouse=False)
def _env_serialized():
    """Serialize env-var-mutating tests per rules/testing.md."""
    with _ENV_LOCK:
        yield


pytestmark = [
    pytest.mark.skipif(
        not _OPENAI_KEY,
        reason=(
            "requires OPENAI_API_KEY in .env "
            "(see https://platform.openai.com/api-keys); "
            "ACCEPTABLE skip per rules/testing.md test-skip triage"
        ),
    ),
    pytest.mark.skipif(
        not _OPENAI_MODEL,
        reason=(
            "requires OPENAI_PROD_MODEL / OPENAI_MODEL / DEFAULT_LLM_MODEL "
            "env var per rules/env-models.md (NEVER hardcoded); "
            "ACCEPTABLE skip per rules/testing.md test-skip triage"
        ),
    ),
]


class TestOpenAIPresetThroughRouter:
    """Real OpenAI preset + real LlmClient construction."""

    def test_openai_preset_yields_provider_bound_risk(self) -> None:
        """OpenAI is a Provider-bound preset per shard 13 § 3.3 until
        Foundation publishes FV attestations (Phase 02+). Runtime fail-
        closes unless envelope opts in via ``provider_bound: true``."""
        from kaizen.llm.presets import openai_preset

        assert _OPENAI_MODEL is not None  # skip guard above
        assert _OPENAI_KEY is not None
        deployment = openai_preset(api_key=_OPENAI_KEY, model=_OPENAI_MODEL)
        annotator = EnvoyProviderRiskAnnotator()
        risk = annotator.annotate(deployment)
        assert risk.risk_class == "Provider-bound"
        assert risk.provider_id == "openai"
        assert risk.model_family == _OPENAI_MODEL


class TestOpenAILiveChat:
    """End-to-end chat against the real OpenAI API. Validates the
    Provider-bound preset's wire-send substrate (legacy
    ``kaizen.providers.llm.openai.OpenAIProvider.chat_async`` per
    shard 13 § 7.1)."""

    async def test_live_chat_returns_non_empty_response(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """Send one short chat exchange. Probe-driven structural
        assertion per `rules/probe-driven-verification.md` MUST Rule 1
        (no regex over response text).

        Cost: ≤ 32 max_tokens × cheapest configured model << $0.01.
        """
        assert _OPENAI_MODEL is not None
        assert _OPENAI_KEY is not None

        monkeypatch.setenv("OPENAI_API_KEY", _OPENAI_KEY)

        from kaizen.providers.llm.openai import OpenAIProvider

        provider = OpenAIProvider()
        if not provider.is_available():  # pragma: no cover (infra)
            pytest.skip("OpenAIProvider.is_available() returned False")

        result = await provider.chat_async(
            messages=[{"role": "user", "content": "Reply with the single word: hello"}],
            model=_OPENAI_MODEL,
            generation_config={"max_tokens": 16, "temperature": 0.0},
        )
        assert isinstance(
            result, dict
        ), f"chat_async returned {type(result).__name__}, expected dict"
        # OpenAI chat completion wire: ``choices[0].message.content`` is
        # the canonical assistant text path. The legacy provider may
        # normalize this; accept multiple shapes.
        content_text = ""
        choices = result.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict):
                    content_text = msg.get("content", "") or ""
                else:
                    content_text = first.get("text", "") or ""
        if not content_text:
            # Fallback: normalized shape.
            msg = result.get("message")
            if isinstance(msg, dict):
                inner = msg.get("content", "")
                content_text = inner if isinstance(inner, str) else str(inner)
            else:
                content_text = str(result.get("content", "") or result.get("text", ""))

        assert len(content_text.strip()) > 0, (
            f"live OpenAI chat returned an empty content string " f"(full response: {result!r})"
        )
