"""Tier 2: T-01-23 — EnvoyModelRouter ↔ real Anthropic provider.

Per shard 13 § 6.1 (`workspaces/phase-01-mvp/01-analysis/13-model-adapter-
implementation.md` lines 282-294): one Tier 2 test per ADR-0006 option.
This file exercises the Anthropic path end-to-end.

API key: read from .env via root conftest.py (`ANTHROPIC_API_KEY`) per
`rules/env-models.md` Absolute Directive 2 (NEVER hardcoded).
Model name: read from `ANTHROPIC_MODEL` env var (per shard 13 § 6.1 table).

Per `rules/testing.md` § Test-Skip Triage Decision Tree: when the key
is absent (developer machine without Anthropic budget, CI without
secret provisioning), the test SKIPs with an infra-conditional reason
— the ACCEPTABLE path, NOT BLOCKED. NO mocking — Tier 2 contract per
`rules/testing.md` § Tier 2.

Cost guard: we use the cheapest Anthropic model the developer configures
via `ANTHROPIC_MODEL` (typically `claude-3-5-haiku-latest` or
`claude-haiku-4-5`), cap max_tokens to ≤ 32, and send a single short
prompt. Per-test cost is well under $0.01.
"""

from __future__ import annotations

import os
import threading

import pytest

from envoy.model import EnvoyProviderRiskAnnotator

_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
_ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL")

_ENV_LOCK = threading.Lock()


@pytest.fixture(autouse=False)
def _env_serialized():
    """Serialize env-var-mutating tests per rules/testing.md."""
    with _ENV_LOCK:
        yield


pytestmark = [
    pytest.mark.skipif(
        not _ANTHROPIC_KEY,
        reason=(
            "requires ANTHROPIC_API_KEY in .env "
            "(see https://console.anthropic.com/settings/keys); "
            "ACCEPTABLE skip per rules/testing.md test-skip triage"
        ),
    ),
    pytest.mark.skipif(
        not _ANTHROPIC_MODEL,
        reason=(
            "requires ANTHROPIC_MODEL env var per rules/env-models.md "
            "(NEVER hardcoded — set e.g. ANTHROPIC_MODEL=claude-haiku-4-5); "
            "ACCEPTABLE skip per rules/testing.md test-skip triage"
        ),
    ),
]


class TestAnthropicPresetThroughRouter:
    """Real Anthropic preset + real LlmClient construction (no chat call
    yet — the chat-call test is separate to keep the cheap structural
    assertions independent of the network round-trip)."""

    def test_anthropic_preset_yields_provider_bound_risk(self) -> None:
        """Anthropic is a Provider-bound preset per shard 13 § 3.3
        until Foundation publishes FV attestations (Phase 02+). The
        runtime must fail-closed unless the envelope opts in via
        ``provider_bound: true`` per spec line 36 + line 67."""
        from kaizen.llm.presets import anthropic_preset

        assert _ANTHROPIC_MODEL is not None  # skip guard above
        assert _ANTHROPIC_KEY is not None
        deployment = anthropic_preset(api_key=_ANTHROPIC_KEY, model=_ANTHROPIC_MODEL)
        annotator = EnvoyProviderRiskAnnotator()
        risk = annotator.annotate(deployment)
        # Provider-bound is the fail-closed-without-opt-in branch per
        # shard 13 § 3.3.
        assert risk.risk_class == "Provider-bound"
        assert risk.provider_id == "anthropic"
        # Model family carries the env-configured model name (NOT a
        # hardcoded string — pinned to whatever the developer's
        # ANTHROPIC_MODEL resolves to).
        assert risk.model_family == _ANTHROPIC_MODEL


class TestAnthropicLiveChat:
    """End-to-end chat against the real Anthropic API. Validates that
    the Provider-bound preset's wire-send substrate (the legacy
    ``kaizen.providers.llm.anthropic.AnthropicProvider.chat_async``
    surface per shard 13 § 7.1) ACTUALLY WORKS."""

    async def test_live_chat_returns_non_empty_response(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """Send one short chat exchange to the real Anthropic API.

        Probe-driven assertion per `rules/probe-driven-verification.md`
        MUST Rule 1: we verify the BEHAVIOR ("the live API returned a
        non-empty assistant message") via structural checks
        (dict-shape + len>0), NOT regex over response text.

        Cost: ≤ 32 max_tokens × cheapest configured model ≈ << $0.01
        per call. Pinned to the user's ANTHROPIC_MODEL choice.
        """
        assert _ANTHROPIC_MODEL is not None
        assert _ANTHROPIC_KEY is not None

        # Ensure the legacy provider sees the env key — kaizen's
        # AnthropicProvider reads ANTHROPIC_API_KEY at chat time.
        monkeypatch.setenv("ANTHROPIC_API_KEY", _ANTHROPIC_KEY)

        from kaizen.providers.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider()
        if not provider.is_available():  # pragma: no cover (infra)
            pytest.skip("AnthropicProvider.is_available() returned False")

        result = await provider.chat_async(
            messages=[{"role": "user", "content": "Reply with the single word: hello"}],
            model=_ANTHROPIC_MODEL,
            generation_config={"max_tokens": 16, "temperature": 0.0},
        )
        # Structural assertions: response is a dict carrying assistant
        # content. Anthropic's wire shape uses ``content`` as a list of
        # blocks; the legacy provider normalizes this. We accept any
        # non-empty stringified content.
        assert isinstance(
            result, dict
        ), f"chat_async returned {type(result).__name__}, expected dict"
        # Try multiple known content paths — Anthropic returns
        # ``content`` as a list of ``{"type": "text", "text": "..."}``
        # blocks; the legacy provider may flatten or pass through.
        content_text = ""
        content = result.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    content_text += block["text"]
                elif isinstance(block, str):
                    content_text += block
        elif isinstance(content, str):
            content_text = content
        else:
            # Fallback: some normalizers route assistant text under
            # ``message.content`` or ``text``.
            msg = result.get("message")
            if isinstance(msg, dict):
                inner = msg.get("content", "")
                content_text = inner if isinstance(inner, str) else str(inner)
            else:
                content_text = str(result.get("text", ""))

        assert len(content_text.strip()) > 0, (
            f"live Anthropic chat returned an empty content string " f"(full response: {result!r})"
        )
