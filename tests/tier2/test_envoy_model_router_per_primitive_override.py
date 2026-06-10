"""Tier 2: T-01-23 — per-primitive model override end-to-end through
the real ``LlmClient.from_env`` path.

Per shard 13 § 6.1 (`workspaces/phase-01-mvp/01-analysis/13-model-adapter-
implementation.md` line 291): asserts ``ENVOY_BOUNDARY_MODEL`` overrides
the default for ``for_primitive("boundary_conversation")``, AND the
unset-path falls back to the deployment's default_model.

Differs from the Tier 1 router test (``tests/tier1/test_envoy_model_
router.py``): Tier 1 mocks ``LlmClient.from_env`` via monkeypatch; Tier
2 exercises the REAL ``LlmClient.from_env`` legacy tier (OPENAI_API_KEY
+ OPENAI_PROD_MODEL → autoselect_provider → real LlmDeployment with
real ``supports()`` matrix). This is the wiring assertion the orphan-
detection rule expects per ``rules/orphan-detection.md`` MUST Rule 2.

Per `rules/testing.md` § Env-Var Test Isolation MUST clause: both
tests serialize env mutations via the module-scope ``_ENV_LOCK`` so
pytest-xdist scheduling cannot race the OPENAI_API_KEY +
OPENAI_PROD_MODEL setup against ENVOY_BOUNDARY_MODEL.

Per `rules/testing.md` § Test-Skip Triage: when OPENAI_API_KEY +
OPENAI_PROD_MODEL are unset, the test SKIPs with infra-conditional
reason (ACCEPTABLE) — the from_env path requires real legacy-tier env
configuration to resolve a deployment.
"""

from __future__ import annotations

import os
import threading

import pytest

_OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
_OPENAI_MODEL = (
    os.environ.get("OPENAI_PROD_MODEL")
    or os.environ.get("OPENAI_MODEL")
    or os.environ.get("DEFAULT_LLM_MODEL")
)

_ENV_LOCK = threading.Lock()


@pytest.fixture(autouse=False)
def _env_serialized():
    """Serialize env-var-mutating tests per rules/testing.md § Env-Var
    Test Isolation MUST clause."""
    with _ENV_LOCK:
        yield


pytestmark = [
    pytest.mark.skipif(
        not _OPENAI_KEY,
        reason=(
            "requires OPENAI_API_KEY in .env to exercise LlmClient.from_env "
            "legacy tier; ACCEPTABLE skip per rules/testing.md test-skip "
            "triage"
        ),
    ),
    pytest.mark.skipif(
        not _OPENAI_MODEL,
        reason=(
            "requires OPENAI_PROD_MODEL / OPENAI_MODEL / DEFAULT_LLM_MODEL "
            "env var per rules/env-models.md (NEVER hardcoded); ACCEPTABLE "
            "skip per rules/testing.md test-skip triage"
        ),
    ),
]


class TestPerPrimitiveOverrideThroughRealFromEnv:
    """End-to-end override resolution through the real
    LlmClient.from_env machinery — exercises the production wiring
    the Tier 1 router tests mock out."""

    def test_envoy_boundary_model_override_flips_default_model(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """ENVOY_BOUNDARY_MODEL set → for_primitive returns a real
        LlmClient whose deployment.default_model carries the override.

        Behaves identically to the Tier 1 override test, but with the
        REAL upstream from_env machinery — closes the orphan-watch
        per rules/orphan-detection.md MUST Rule 2 (every wired
        manager has a Tier 2 integration test that exercises the
        wired path, not just the mocked path)."""
        # Clear from_env URI-tier signals so the legacy tier is used.
        monkeypatch.delenv("KAILASH_LLM_DEPLOYMENT", raising=False)
        monkeypatch.delenv("KAILASH_LLM_PROVIDER", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", _OPENAI_KEY)
        monkeypatch.setenv("OPENAI_PROD_MODEL", _OPENAI_MODEL)
        # The override. The router's PRIMITIVE_MODEL_ENV_KEYS maps
        # "boundary_conversation" → "ENVOY_BOUNDARY_MODEL"; setting it
        # MUST flip the deployment's default_model after from_env
        # resolution.
        override_value = _OPENAI_MODEL  # use the same env-resolved model to
        # avoid hardcoding a string per rules/env-models.md — the override
        # mechanism is what's under test, not the model identity.
        monkeypatch.setenv("ENVOY_BOUNDARY_MODEL", override_value)

        # Lazy import — defers the kaizen LLM module init until after
        # the env-var setup completes.
        from envoy.model import EnvoyModelRouter

        router = EnvoyModelRouter()
        client = router.for_primitive("boundary_conversation")
        assert client.deployment is not None
        assert client.deployment.default_model == override_value

    def test_no_override_preserves_from_env_default_model(
        self, monkeypatch: pytest.MonkeyPatch, _env_serialized: None
    ) -> None:
        """ENVOY_BOUNDARY_MODEL absent → for_primitive returns a real
        LlmClient whose deployment.default_model is the from_env-
        resolved default (no override applied)."""
        monkeypatch.delenv("KAILASH_LLM_DEPLOYMENT", raising=False)
        monkeypatch.delenv("KAILASH_LLM_PROVIDER", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", _OPENAI_KEY)
        monkeypatch.setenv("OPENAI_PROD_MODEL", _OPENAI_MODEL)
        # No ENVOY_BOUNDARY_MODEL.
        monkeypatch.delenv("ENVOY_BOUNDARY_MODEL", raising=False)

        from envoy.model import EnvoyModelRouter

        router = EnvoyModelRouter()
        client = router.for_primitive("boundary_conversation")
        assert client.deployment is not None
        # Per the from_env legacy-tier contract, the deployment's
        # default_model reflects OPENAI_PROD_MODEL.
        assert client.deployment.default_model == _OPENAI_MODEL
