"""Tier 2: R1-M-02 — model router consumes the legacy chat_async surface.

T-01-23 per shard 13 § 7.1 HOLD + the workspace todo line 619
(R1-M-02 chat_async route test): until upstream `LlmClient.complete()`
lands (per #740 spec-correction; deferred to Phase 02+), the chat-
completion path Envoy depends on is served by the legacy provider
surface at `kaizen.providers.llm.<provider>.chat_async()`.

This is the structural assertion that the disposition documented in
shard 13 § 7.1 ("no MUST-Rule-5b sweep — use the supported alternative
pattern") is reachable through the router. NO real LLM call —
verifying the chat substrate is callable via the legacy provider
import path Envoy ships against.

Per `rules/probe-driven-verification.md` MUST Rule 3: no-LLM probes
MUST be structural. The asserts here are structural (`hasattr`,
`callable`, `inspect.iscoroutinefunction`) — they verify the API
surface contract, not the runtime semantics of chat.
"""

from __future__ import annotations

import inspect

import pytest


class TestLegacyProviderChatAsyncSurface:
    """Every provider Envoy targets via BYOM exposes the legacy
    `chat_async()` callable (the substrate shard 13 § 7.1 documents)."""

    # Per shard 13 § 2.6: OpenAI / Anthropic / DeepSeek expose `chat_async`;
    # Ollama exposes only `chat` (sync) + `stream_chat` — NO `chat_async`.
    # Pinning the per-provider substrate so a future upstream rename fires.
    @pytest.mark.parametrize(
        "module_path,class_name,method_name,must_be_async",
        [
            ("kaizen.providers.llm.openai", "OpenAIProvider", "chat_async", True),
            ("kaizen.providers.llm.anthropic", "AnthropicProvider", "chat_async", True),
            ("kaizen.providers.llm.deepseek", "DeepSeekProvider", "chat_async", True),
            ("kaizen.providers.llm.ollama", "OllamaProvider", "chat", False),
        ],
    )
    def test_legacy_provider_class_exposes_chat_surface(
        self,
        module_path: str,
        class_name: str,
        method_name: str,
        must_be_async: bool,
    ) -> None:
        """Per shard 13 § 2.6 verified upstream finding: the legacy
        provider's chat substrate is reachable through the documented
        method name. The router drives chat through this surface until
        upstream `LlmClient.complete()` lands (#740 spec-correction)."""
        import importlib

        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            pytest.skip(
                f"legacy provider module {module_path} not installed "
                f"(upstream kaizen build): {exc}"
            )
        provider_cls = getattr(module, class_name, None)
        if provider_cls is None:
            pytest.skip(
                f"legacy provider class {class_name} not exposed by "
                f"{module_path} in this upstream build"
            )
        method = getattr(provider_cls, method_name, None)
        assert method is not None, (
            f"{class_name}.{method_name} absent — shard 13 § 7.1 HOLD "
            f"surface drifted in upstream kaizen; re-derive the model "
            f"adapter chat substrate per MUST-Rule-5b sweep."
        )
        assert callable(method), f"{class_name}.{method_name} not callable"
        if must_be_async:
            assert inspect.iscoroutinefunction(method), (
                f"{class_name}.{method_name} must be async per " f"shard 13 § 2.6"
            )
        else:
            assert not inspect.iscoroutinefunction(method), (
                f"{class_name}.{method_name} must be sync per "
                f"shard 13 § 2.6 line 103 (Ollama upstream contract)"
            )


class TestRouterReturnsClientWithChatPath:
    """Router's per-primitive client is reachable via the chat surface
    spec § Purpose line 5 names (`prompt_send` / `model_invoke`)."""

    def test_for_primitive_returns_client_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Per shard 13 § 4 sketch + § 3.2: `for_primitive` returns
        an `LlmClient` instance. The structural assertion stops at the
        type — verifying the chat semantics is the per-provider real-
        Ollama / cassette wiring tests in this same Tier 2 directory."""
        # Clear from_env signals; use OpenAI legacy tier with a synthetic
        # key (no network call here).
        monkeypatch.delenv("KAILASH_LLM_DEPLOYMENT", raising=False)
        monkeypatch.delenv("KAILASH_LLM_PROVIDER", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-tier2-structural-only")
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-structural-only")

        try:
            from envoy.model import EnvoyModelRouter
            from kaizen.llm.client import LlmClient
        except ImportError as exc:
            pytest.skip(f"kaizen LlmClient unavailable: {exc}")

        router = EnvoyModelRouter()
        client = router.for_primitive("boundary_conversation")
        assert isinstance(
            client, LlmClient
        ), "for_primitive MUST return an LlmClient per shard 13 § 4"
        # Deployment present — required for any downstream chat path
        # whether through legacy provider surface (Phase 01) OR through
        # LlmClient.complete() (Phase 02+).
        assert client.deployment is not None
