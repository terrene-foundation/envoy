"""Tier 1: T-01-22 — EnvoyModelRouter per-primitive client factory.

Source: T-01-22 per `workspaces/phase-01-mvp/todos/active/01-wave-1-
foundation.md` § T-01-22 + shard 13 (`workspaces/phase-01-mvp/01-analysis/
13-model-adapter-implementation.md`) § 3.2 + § 4 + § 6.

Capacity coverage (5 invariants):

1. Per-primitive env-key resolution (override flips deployment.default_model).
2. Override-absent path (deployment.default_model preserved from from_env).
3. Capability-matrix refusal (Boundary Conversation needs tools=True).
4. PRIMITIVE_MODEL_ENV_KEYS ClassVar shape (4 canonical primitives).
5. required_capabilities() contract (introspectable per zero-tolerance 3c).

Per `rules/testing.md` Tier 1: mocking allowed for upstream LlmDeployment
because spinning a real Ollama daemon in unit tests is heavy. The Tier 2
wiring (T-01-23) exercises real Ollama end-to-end through
``LlmClient.from_env`` per shard 13 § 6.

Per `rules/testing.md` § Env-Var Test Isolation: every test that mutates
``ENVOY_*_MODEL`` or ``KAILASH_*`` env vars uses ``monkeypatch.setenv`` +
the module-scope ``_env_serialized`` fixture so pytest-xdist scheduling
does not race.
"""

from __future__ import annotations

import threading

import pytest
from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.presets import ollama_default_preset, openai_compatible_preset

from envoy.model import EnvoyModelRouter, ProviderSwitchRefusedByEnvelopeError


_ENV_LOCK = threading.Lock()


@pytest.fixture(autouse=False)
def _env_serialized():
    """Serialize env-var-mutating tests per rules/testing.md § Env-Var
    Test Isolation."""
    with _ENV_LOCK:
        yield


@pytest.fixture(autouse=True)
def _clear_envoy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear every ENVOY_*_MODEL + KAILASH_LLM_* env-var before each test.

    The router reads these at every for_primitive() call; leaving stale
    values across tests creates order-dependent results (per rules/testing
    Tier 1 determinism contract).
    """
    for key in [
        "ENVOY_BOUNDARY_MODEL",
        "ENVOY_DIGEST_MODEL",
        "ENVOY_GRANT_MOMENT_MODEL",
        "ENVOY_DEFAULT_MODEL",
        "KAILASH_LLM_DEPLOYMENT",
        "KAILASH_LLM_PROVIDER",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)


def _openai_base_client(monkeypatch: pytest.MonkeyPatch, model: str = "gpt-4o-mini") -> None:
    """Configure the env so LlmClient.from_env resolves to an OpenAI
    deployment with the given default_model via the legacy tier.

    Tier 1 contract: we exercise the router against a real LlmDeployment
    instance produced by from_env(). OpenAI legacy tier (OPENAI_API_KEY
    + OPENAI_PROD_MODEL) is the simplest path — the API key is a
    syntactic placeholder; no network call fires because the router
    only inspects deployment.default_model + deployment.supports().

    Ollama is NOT a selector-tier preset in kaizen.llm.from_env (only
    URI tier or direct preset construction); see shard 13 § 2.5
    three-tier precedence enumeration. T-01-23 Tier 2 wiring against
    real Ollama uses ollama_default_preset() + LlmClient.from_deployment().
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-tier1-placeholder")
    monkeypatch.setenv("OPENAI_PROD_MODEL", model)


class TestPrimitiveModelEnvKeys:
    """Invariant 4: PRIMITIVE_MODEL_ENV_KEYS shape pin."""

    def test_four_canonical_primitives_present(self) -> None:
        assert set(EnvoyModelRouter.PRIMITIVE_MODEL_ENV_KEYS.keys()) == {
            "boundary_conversation",
            "daily_digest",
            "grant_moment_summary",
            "default",
        }

    def test_env_key_names_match_shard_13_section_3_2(self) -> None:
        """Pin the exact env-key names so a rename surfaces as a test
        failure rather than silent drift (shard 13 § 3.2 names the four
        env-keys explicitly)."""
        assert EnvoyModelRouter.PRIMITIVE_MODEL_ENV_KEYS == {
            "boundary_conversation": "ENVOY_BOUNDARY_MODEL",
            "daily_digest": "ENVOY_DIGEST_MODEL",
            "grant_moment_summary": "ENVOY_GRANT_MOMENT_MODEL",
            "default": "ENVOY_DEFAULT_MODEL",
        }


class TestRequiredCapabilities:
    """Invariant 5: required_capabilities() introspectable contract."""

    def test_boundary_conversation_requires_tools(self) -> None:
        router = EnvoyModelRouter()
        assert router.required_capabilities("boundary_conversation") == {"tools": True}

    def test_daily_digest_no_requirements(self) -> None:
        router = EnvoyModelRouter()
        assert router.required_capabilities("daily_digest") == {}

    def test_grant_moment_summary_no_requirements(self) -> None:
        router = EnvoyModelRouter()
        assert router.required_capabilities("grant_moment_summary") == {}

    def test_unknown_primitive_returns_empty(self) -> None:
        """Unknown primitives have no capability requirements (the
        for_primitive resolution falls through to 'default')."""
        router = EnvoyModelRouter()
        assert router.required_capabilities("nonexistent") == {}

    def test_returned_dict_is_a_copy_not_shared_state(self) -> None:
        """Mutating the returned dict MUST NOT mutate the ClassVar
        (defensive contract per rules/zero-tolerance.md Rule 3 — silent
        shared-state leakage would let one test poison the next)."""
        router = EnvoyModelRouter()
        caps = router.required_capabilities("boundary_conversation")
        caps["tools"] = False
        # Re-fetch and confirm the contract is unmodified.
        assert router.required_capabilities("boundary_conversation") == {"tools": True}


class TestPerPrimitiveOverride:
    """Invariants 1 + 2: per-primitive model override resolution."""

    def test_override_env_flips_deployment_default_model(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """ENVOY_DIGEST_MODEL set → for_primitive('daily_digest') returns
        an LlmClient whose deployment.default_model is the override."""
        _openai_base_client(monkeypatch, model="gpt-4o-mini")
        monkeypatch.setenv("ENVOY_DIGEST_MODEL", "gpt-4o-nano")
        router = EnvoyModelRouter()
        client = router.for_primitive("daily_digest")
        assert client.deployment is not None
        assert client.deployment.default_model == "gpt-4o-nano"

    def test_no_override_preserves_from_env_default_model(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """ENVOY_DIGEST_MODEL unset → for_primitive returns the from_env
        baseline default_model."""
        _openai_base_client(monkeypatch, model="gpt-4o-mini")
        router = EnvoyModelRouter()
        client = router.for_primitive("daily_digest")
        assert client.deployment is not None
        assert client.deployment.default_model == "gpt-4o-mini"

    def test_override_for_boundary_conversation(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """ENVOY_BOUNDARY_MODEL is honored for boundary_conversation
        (and the openai preset satisfies tools=True per the kaizen
        capability matrix)."""
        _openai_base_client(monkeypatch, model="gpt-4o-mini")
        monkeypatch.setenv("ENVOY_BOUNDARY_MODEL", "gpt-4o")
        router = EnvoyModelRouter()
        client = router.for_primitive("boundary_conversation")
        assert client.deployment is not None
        assert client.deployment.default_model == "gpt-4o"

    def test_default_primitive_falls_through_when_unknown(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """Unknown primitives use ENVOY_DEFAULT_MODEL as the override
        env-key (per for_primitive's fallback)."""
        _openai_base_client(monkeypatch, model="gpt-4o-mini")
        monkeypatch.setenv("ENVOY_DEFAULT_MODEL", "gpt-3.5-turbo")
        router = EnvoyModelRouter()
        client = router.for_primitive("custom_unknown_primitive")
        assert client.deployment is not None
        assert client.deployment.default_model == "gpt-3.5-turbo"


class TestCapabilityRefusal:
    """Invariant 3: capability-matrix gate raises on mismatch."""

    def test_non_tools_capable_preset_refused_for_boundary_conversation(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """A deployment with tools=False is refused for
        boundary_conversation per shard 13 § 3.2 + spec line 73."""
        # Build a deployment whose supports() reports tools=False, then
        # monkey-patch LlmClient.from_env to return a client wrapping it.
        # Use openai_compatible_preset which is generic OpenAI-wire and
        # ships with tools=True by default; we override supports() via
        # an isinstance-bypassing mock to surface the refusal path.
        from envoy.model import router as router_mod

        class _NoToolsDeployment:
            """Stand-in deployment whose supports() returns tools=False.

            Tier 1 mock per rules/testing.md Tier 1 contract — the real
            tools=False preset enumeration lives in
            kaizen.llm.capabilities; here we pin the router's gate
            independently of that table so a change in the table doesn't
            silently invalidate this test."""

            preset_name = "synthetic-no-tools"
            default_model = "synthetic-model"

            def supports(self) -> dict:
                return {
                    "tools": False,
                    "vision": False,
                    "batch": False,
                    "caching": False,
                    "audio": False,
                }

            def model_copy(self, *, update=None):
                # Apply the update dict to a fresh stand-in copy; the
                # router calls model_copy when an override env-key is
                # set. The override flow MUST still reach the capability
                # gate (override before refusal).
                copy = _NoToolsDeployment()
                if update and "default_model" in update:
                    copy.default_model = update["default_model"]
                return copy

        class _StandinClient:
            def __init__(self, deployment) -> None:
                self._deployment = deployment

            @property
            def deployment(self):
                return self._deployment

            def with_deployment(self, deployment):
                return _StandinClient(deployment)

        def _fake_from_env(*, classification_policy=None, caller_clearance=None):
            return _StandinClient(_NoToolsDeployment())

        monkeypatch.setattr(router_mod.LlmClient, "from_env", staticmethod(_fake_from_env))

        router = EnvoyModelRouter()
        with pytest.raises(ProviderSwitchRefusedByEnvelopeError) as exc:
            router.for_primitive("boundary_conversation")
        # Error message MUST name the primitive + the failed capability
        # per the typed-error contract (rules/observability.md Rule 3).
        assert "boundary_conversation" in str(exc.value)
        assert "tools" in str(exc.value)

    def test_daily_digest_accepts_non_tools_deployment(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """Daily Digest has empty capability requirements → a
        tools=False deployment is accepted."""
        from envoy.model import router as router_mod

        class _NoToolsDeployment:
            preset_name = "synthetic-no-tools"
            default_model = "synthetic-model"

            def supports(self) -> dict:
                return {
                    "tools": False,
                    "vision": False,
                    "batch": False,
                    "caching": False,
                    "audio": False,
                }

            def model_copy(self, *, update=None):
                copy = _NoToolsDeployment()
                if update and "default_model" in update:
                    copy.default_model = update["default_model"]
                return copy

        class _StandinClient:
            def __init__(self, deployment) -> None:
                self._deployment = deployment

            @property
            def deployment(self):
                return self._deployment

            def with_deployment(self, deployment):
                return _StandinClient(deployment)

        def _fake_from_env(*, classification_policy=None, caller_clearance=None):
            return _StandinClient(_NoToolsDeployment())

        monkeypatch.setattr(router_mod.LlmClient, "from_env", staticmethod(_fake_from_env))

        router = EnvoyModelRouter()
        # MUST NOT raise — daily_digest has empty required capabilities.
        client = router.for_primitive("daily_digest")
        assert client.deployment.preset_name == "synthetic-no-tools"


class TestNoDeploymentGuard:
    """Defensive guard: from_env returning a None deployment surfaces as
    a typed RuntimeError per rules/zero-tolerance.md Rule 3a."""

    def test_none_deployment_raises_typed_error(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        from envoy.model import router as router_mod

        class _BadClient:
            @property
            def deployment(self):
                return None

        def _fake_from_env(*, classification_policy=None, caller_clearance=None):
            return _BadClient()

        monkeypatch.setattr(router_mod.LlmClient, "from_env", staticmethod(_fake_from_env))

        router = EnvoyModelRouter()
        with pytest.raises(RuntimeError) as exc:
            router.for_primitive("daily_digest")
        # Error MUST name the resolution path so the operator knows
        # which env-var to set.
        assert "KAILASH_LLM_DEPLOYMENT" in str(exc.value) or "KAILASH_LLM_PROVIDER" in str(
            exc.value
        )


class TestOllamaCapabilityHappyPath:
    """Sanity: a real Ollama preset built via ollama_default_preset
    satisfies boundary_conversation's tools=True contract (the router's
    capability check passes against the real upstream supports()
    table)."""

    def test_real_ollama_deployment_supports_tools(self) -> None:
        deployment: LlmDeployment = ollama_default_preset("llama3.2")
        # If this assertion fails, the upstream kaizen capability matrix
        # changed and the router's Boundary Conversation contract needs
        # re-validation (shard 13 § 3.2).
        assert deployment.supports().get("tools") is True

    def test_openai_compatible_capability_matrix_pin(self) -> None:
        """Pin the openai_compatible preset's supports() row so a
        change to the upstream capability table surfaces here rather
        than at runtime in a downstream consumer.

        Uses ``https://api.openai.com`` as the base URL because kaizen's
        ``openai_compatible_preset`` runs SSRF + DNS-resolution checks
        on the URL at construction time (``kaizen.llm.url_safety``);
        invalid hosts raise ``InvalidEndpoint`` even though the test
        never makes a network call. ``api.openai.com`` resolves
        publicly and satisfies the safety check.
        """
        deployment = openai_compatible_preset(
            base_url="https://api.openai.com", api_key="not-a-real-key"
        )
        supports = deployment.supports()
        # tools key MUST exist; True/False is the assertion contract,
        # not the absence.
        assert "tools" in supports
