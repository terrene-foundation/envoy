"""Tier 2 wiring: EnvoyModelRouter through the facade (orphan-detection
Rule 2 closure).

Closes /redteam Round 1 LOW-1 per shard 13 § 6.1 + `rules/facade-
manager-detection.md` Rule 2 (every manager-shape class has a Tier 2
test named `test_<lowercase_manager_name>_wiring.py`). The per-provider
Tier 2 tests cover specific BYOM paths; this consolidated wiring test
asserts the EnvoyModelRouter facade end-to-end through `for_primitive`.

Per `rules/testing.md` Tier 2: NO mocking. Real `LlmClient.from_env`
via real OpenAI legacy tier; no real LLM invocation (structural pin).
"""

from __future__ import annotations

import pytest


class TestEnvoyModelRouterFacadeWiring:
    """`EnvoyModelRouter` facade reachable + returns LlmClient per shard
    13 § 4 contract."""

    def test_for_primitive_returns_llm_client_through_real_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The router's `for_primitive` MUST flow through the REAL
        `LlmClient.from_env()` resolver — pinning the orphan-detection
        Rule 2 contract (Tier 1 mocks LlmDeployment; Tier 2 hits real
        upstream resolver)."""
        # Synthetic OPENAI legacy-tier env (no real API call).
        monkeypatch.delenv("KAILASH_LLM_DEPLOYMENT", raising=False)
        monkeypatch.delenv("KAILASH_LLM_PROVIDER", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-tier2-structural-only")
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-structural-only")

        try:
            from envoy.model import EnvoyModelRouter
            from kaizen.llm.client import LlmClient
        except ImportError as exc:
            pytest.skip(f"kaizen unavailable: {exc}")

        router = EnvoyModelRouter()
        client = router.for_primitive("boundary_conversation")
        assert isinstance(client, LlmClient)
        assert client.deployment is not None
        # The deployment surface is reachable through the facade.
        assert client.deployment.default_model is not None
