"""Tier 1: T-01-22 — BYOM first-launch picker (.env write + vault import).

Source: T-01-22 per shard 13 § 3.1 + ADR-0006 + shard 14 § 3.1 step 9.

Capacity coverage (7 invariants):

1. Ollama choice writes KAILASH_LLM_PROVIDER + OLLAMA_BASE_URL +
   OLLAMA_DEFAULT_MODEL; performs NO vault write (Ollama has no key).
2. Anthropic / OpenAI / DeepSeek choices write the selector env-key +
   model name; route the API key into the Connection Vault.
3. openai_compatible writes KAILASH_LLM_DEPLOYMENT URI form + model
   name; routes the key into the vault.
4. API key NEVER lands in .env (rules/security.md § No Hardcoded
   Secrets) — vault import is the only persistence path.
5. Unknown choice raises ValueError (fail-loud per
   rules/zero-tolerance.md Rule 3a).
6. Empty model_name raises ValueError.
7. Ollama + accidental api_key raises ValueError (shape guard per
   rules/ui-backend-defense.md Rule 2 — local choice has no key).

Per `rules/testing.md` Tier 1: real ConnectionVault using a pure-dict
keyring backend (the same pattern T-01-24 connection-vault tests use at
`tests/tier1/test_connection_vault_adapter.py::_MemBackend`).
"""

from __future__ import annotations

import threading
from pathlib import Path

import keyring.errors
import pytest

from envoy.connection_vault import ConnectionVault
from envoy.envelope import (
    CommunicationDimension,
    EnvelopeConfigInput,
    EnvelopeScopeRef,
    OperationalDimension,
)
from envoy.model import PickResult, SUPPORTED_CHOICES, byom_pick


class _MemBackend:
    """Pure-dict keyring backend for Tier 1 tests (mirrors the T-01-24
    test fixture at tests/tier1/test_connection_vault_adapter.py)."""

    def __init__(self) -> None:
        self._d: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._d[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._d.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._d:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._d[key]


_ENV_LOCK = threading.Lock()


@pytest.fixture(autouse=False)
def _env_serialized():
    """Serialize env-var-mutating tests per rules/testing.md."""
    with _ENV_LOCK:
        yield


@pytest.fixture(autouse=True)
def _clear_byom_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear every env-var the picker might inject."""
    for key in [
        "KAILASH_LLM_PROVIDER",
        "KAILASH_LLM_DEPLOYMENT",
        "OLLAMA_BASE_URL",
        "OLLAMA_DEFAULT_MODEL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_PROD_MODEL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "ENVOY_CUSTOM_API_KEY",
        "ENVOY_CUSTOM_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def tmp_env(tmp_path: Path) -> str:
    """Empty .env path under tmp_path. The picker creates the file on
    first write."""
    env_path = tmp_path / ".env"
    env_path.write_text("# pre-existing comment\n")
    return str(env_path)


@pytest.fixture
def vault(tmp_path: Path) -> ConnectionVault:
    """Build a ConnectionVault backed by the in-memory test keyring so
    the picker's vault-import path runs against a real keyring backend
    (no OS keychain dependency).

    The vault uses an EnvelopeConfigInput as its active envelope
    (ActiveEnvelope is a Union alias of EnvelopeConfig |
    EnvelopeConfigInput per envoy/envelope/scope.py line 23). The
    tool_allowlist permits every service-identifier the picker writes
    to so envelope_contains_scope() returns True at vault.set() time;
    the picker itself only writes (never reads), so this only matters
    for downstream consumers.
    """
    backend = _MemBackend()
    envelope = EnvelopeConfigInput(
        operational=OperationalDimension(
            tool_allowlist=[
                "anthropic.api",
                "openai.api",
                "deepseek.api",
                "openai-compatible.api",
            ],
        ),
        communication=CommunicationDimension(),
    )
    # principal_genesis_id MUST be a 64-char lowercase hex string per
    # specs/connection-vault.md § Per-entry schema (validated by
    # envoy.connection_vault.schema.validate_principal_genesis_id).
    v = ConnectionVault(
        principal_genesis_id="a" * 64,
        active_envelope=envelope,
        keyring_backend=backend,
    )
    return v


def _read_env(env_path: str) -> dict[str, str]:
    """Parse .env into a dict for assertions (key → value)."""
    entries: dict[str, str] = {}
    for line in Path(env_path).read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        k, v = stripped.split("=", 1)
        entries[k.strip()] = v.strip()
    return entries


class TestSupportedChoicesContract:
    """Pin the 5 enumerated choices per ADR-0006."""

    def test_five_canonical_choices(self) -> None:
        assert SUPPORTED_CHOICES == frozenset(
            {"ollama", "anthropic", "openai", "deepseek", "openai_compatible"}
        )


class TestOllamaChoice:
    """Invariant 1: ollama writes the three Ollama env vars + no vault
    write."""

    def test_ollama_writes_provider_base_url_and_model(
        self,
        tmp_env: str,
        vault: ConnectionVault,
        _env_serialized: None,
    ) -> None:
        result = byom_pick(
            choice="ollama",
            model_name="llama3.2",
            api_key=None,
            custom_base_url=None,
            env_path=tmp_env,
            vault=vault,
        )
        assert isinstance(result, PickResult)
        assert result.choice == "ollama"
        assert result.vault_import_result is None
        entries = _read_env(tmp_env)
        assert entries["KAILASH_LLM_PROVIDER"] == "ollama"
        assert entries["OLLAMA_BASE_URL"] == "http://localhost:11434"
        assert entries["OLLAMA_DEFAULT_MODEL"] == "llama3.2"

    def test_ollama_with_custom_base_url(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        """Custom Ollama base-url (e.g. remote workstation) is honored."""
        result = byom_pick(
            choice="ollama",
            model_name="qwen2.5:7b",
            api_key=None,
            custom_base_url="http://ollama.lan:11434",
            env_path=tmp_env,
            vault=vault,
        )
        assert result.choice == "ollama"
        entries = _read_env(tmp_env)
        assert entries["OLLAMA_BASE_URL"] == "http://ollama.lan:11434"

    def test_ollama_with_api_key_raises(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        """Invariant 7: ollama + accidental api_key MUST raise (shape
        guard — local choice has no credential surface)."""
        with pytest.raises(ValueError) as exc:
            byom_pick(
                choice="ollama",
                model_name="llama3.2",
                api_key="sk-shouldnt-be-here",
                custom_base_url=None,
                env_path=tmp_env,
                vault=vault,
            )
        assert "ollama" in str(exc.value).lower()
        assert "api_key" in str(exc.value)


class TestCloudChoices:
    """Invariants 2 + 4: cloud choices write selector + model;
    route key to vault; never write the key to .env."""

    @pytest.mark.parametrize(
        "choice,selector_env,model_env,api_key_env",
        [
            ("anthropic", "anthropic", "ANTHROPIC_MODEL", "ANTHROPIC_API_KEY"),
            ("openai", "openai", "OPENAI_PROD_MODEL", "OPENAI_API_KEY"),
            ("deepseek", "deepseek", "DEEPSEEK_MODEL", "DEEPSEEK_API_KEY"),
        ],
    )
    def test_cloud_choice_writes_env_and_routes_key_to_vault(
        self,
        choice: str,
        selector_env: str,
        model_env: str,
        api_key_env: str,
        tmp_env: str,
        vault: ConnectionVault,
        _env_serialized: None,
    ) -> None:
        api_key_value = f"sk-{choice}-test-key"
        model_name = f"{choice}-test-model"
        result = byom_pick(
            choice=choice,
            model_name=model_name,
            api_key=api_key_value,
            custom_base_url=None,
            env_path=tmp_env,
            vault=vault,
        )
        # .env carries selector + model only.
        entries = _read_env(tmp_env)
        assert entries["KAILASH_LLM_PROVIDER"] == selector_env
        assert entries[model_env] == model_name
        # Invariant 4: api key is NEVER persisted to .env.
        assert api_key_env not in entries
        assert api_key_value not in Path(tmp_env).read_text()
        # Vault import succeeded — the env-var name landed in the
        # ImportResult.imported_env_var_names tuple.
        assert result.vault_import_result is not None
        assert api_key_env in result.vault_import_result.imported_env_var_names

    def test_cloud_choice_with_blank_api_key_raises(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        with pytest.raises(ValueError) as exc:
            byom_pick(
                choice="anthropic",
                model_name="claude-3-5-sonnet",
                api_key="   ",  # blank
                custom_base_url=None,
                env_path=tmp_env,
                vault=vault,
            )
        assert "non-empty" in str(exc.value) or "blank" in str(exc.value)

    def test_cloud_choice_without_api_key_or_env_var_raises(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        """If neither api_key nor the pre-set env-var is supplied, the
        picker has nothing to import → fail-loud per zero-tolerance 3a."""
        with pytest.raises(ValueError) as exc:
            byom_pick(
                choice="openai",
                model_name="gpt-4o",
                api_key=None,
                custom_base_url=None,
                env_path=tmp_env,
                vault=vault,
            )
        assert "OPENAI_API_KEY" in str(exc.value)


class TestOpenAICompatibleChoice:
    """Invariant 3: openai_compatible writes URI tier + routes key to
    vault."""

    def test_openai_compatible_writes_uri_and_vault(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        result = byom_pick(
            choice="openai_compatible",
            model_name="mixtral-8x7b",
            api_key="sk-custom-test",
            custom_base_url="https://mlx-server.example.com",
            env_path=tmp_env,
            vault=vault,
        )
        entries = _read_env(tmp_env)
        # URI tier per kaizen #498 / S7.
        assert "KAILASH_LLM_DEPLOYMENT" in entries
        assert entries["KAILASH_LLM_DEPLOYMENT"].startswith("openai-compat://")
        assert "mlx-server.example.com" in entries["KAILASH_LLM_DEPLOYMENT"]
        assert "mixtral-8x7b" in entries["KAILASH_LLM_DEPLOYMENT"]
        assert entries["ENVOY_CUSTOM_MODEL"] == "mixtral-8x7b"
        # Key never in .env.
        assert "ENVOY_CUSTOM_API_KEY" not in entries
        assert "sk-custom-test" not in Path(tmp_env).read_text()
        # Vault imported.
        assert result.vault_import_result is not None
        assert "ENVOY_CUSTOM_API_KEY" in result.vault_import_result.imported_env_var_names

    def test_openai_compatible_without_base_url_raises(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        with pytest.raises(ValueError) as exc:
            byom_pick(
                choice="openai_compatible",
                model_name="model",
                api_key="sk-test",
                custom_base_url=None,
                env_path=tmp_env,
                vault=vault,
            )
        assert "custom_base_url" in str(exc.value)

    def test_openai_compatible_with_malformed_base_url_raises(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        with pytest.raises(ValueError) as exc:
            byom_pick(
                choice="openai_compatible",
                model_name="model",
                api_key="sk-test",
                custom_base_url="not-a-url",  # missing scheme / netloc
                env_path=tmp_env,
                vault=vault,
            )
        assert "URL" in str(exc.value) or "url" in str(exc.value)


class TestInputGuards:
    """Invariants 5 + 6: fail-loud guards per rules/zero-tolerance.md
    Rule 3a + rules/ui-backend-defense.md Rule 2 (shape rejection)."""

    def test_unknown_choice_raises(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        with pytest.raises(ValueError) as exc:
            byom_pick(
                choice="unknown-provider",
                model_name="x",
                api_key="k",
                custom_base_url=None,
                env_path=tmp_env,
                vault=vault,
            )
        assert "supported" in str(exc.value).lower() or "ADR" in str(exc.value)

    def test_empty_model_name_raises(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        with pytest.raises(ValueError) as exc:
            byom_pick(
                choice="ollama",
                model_name="   ",
                api_key=None,
                custom_base_url=None,
                env_path=tmp_env,
                vault=vault,
            )
        assert "model_name" in str(exc.value)


class TestPreservesExistingEnv:
    """The picker MUST preserve pre-existing .env content (comments +
    unrelated keys) — additive write per shard 13 § 3.1 onboarding."""

    def test_pre_existing_comment_preserved(
        self, tmp_env: str, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        # tmp_env fixture writes "# pre-existing comment".
        byom_pick(
            choice="ollama",
            model_name="llama3.2",
            api_key=None,
            custom_base_url=None,
            env_path=tmp_env,
            vault=vault,
        )
        text = Path(tmp_env).read_text()
        assert "# pre-existing comment" in text

    def test_unrelated_key_preserved(
        self, tmp_path: Path, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text("UNRELATED_KEY=preserved-value\n")
        byom_pick(
            choice="ollama",
            model_name="llama3.2",
            api_key=None,
            custom_base_url=None,
            env_path=str(env_path),
            vault=vault,
        )
        entries = _read_env(str(env_path))
        assert entries["UNRELATED_KEY"] == "preserved-value"
        assert entries["KAILASH_LLM_PROVIDER"] == "ollama"

    def test_replaced_key_does_not_duplicate(
        self, tmp_path: Path, vault: ConnectionVault, _env_serialized: None
    ) -> None:
        """When the picker writes a key that's already in .env, the
        new value overwrites the old (no duplicate lines)."""
        env_path = tmp_path / ".env"
        env_path.write_text("OLLAMA_DEFAULT_MODEL=old-model\n")
        byom_pick(
            choice="ollama",
            model_name="new-model",
            api_key=None,
            custom_base_url=None,
            env_path=str(env_path),
            vault=vault,
        )
        # Count occurrences of the key — MUST be exactly 1.
        text = Path(env_path).read_text()
        key_count = sum(1 for line in text.splitlines() if line.startswith("OLLAMA_DEFAULT_MODEL="))
        assert key_count == 1
        entries = _read_env(str(env_path))
        assert entries["OLLAMA_DEFAULT_MODEL"] == "new-model"
