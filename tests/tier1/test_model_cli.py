"""Tier 1 tests for `envoy model` (F5.2 Wave-5 CLI surface).

Pins the invariants of the BYOM model-picker CLI (`DECISIONS.md` ADR-0006 +
shard 13 § 3.1 byom_picker / § 3.2 router):

1. **set → show round-trip** — a picked provider/model surfaces in `show`
   (real `byom_pick` + real `ConnectionVault` + real sha256 genesis id; only
   the OS-keychain boundary is faked; .env is a real tmp file).
2. **API key is never displayed** — `show` shows provider + model, never a key.
3. **API key is never a CLI argument** — `set` exposes no value-bearing secret
   option; the key arrives via hidden prompt or `--secret-stdin`
   (per `rules/security.md`).
4. **API key never lands in .env** — only the selector + model name are written;
   the secret goes to the keychain (per `rules/security.md` § No .env in Git).
5. **ollama needs no key** — the local choice never prompts and writes no vault.
6. **custom requires --base-url** — actionable error when omitted.
7. **Principal required for set** — no `--principal` / `ENVOY_PRINCIPAL_ID`
   exits non-zero with an actionable message.
8. **Choice validation** — an unknown `--choice` exits non-zero (click.Choice).
9. **Surface stability** — `model` registered on the root group with
   `show` + `set` subcommands.

Tier 1 scope: real `ConnectionVault` + real `byom_pick` with the OS-keychain
boundary (`keyring.{set,get,delete}_password`) monkeypatched to a dict — NOT a
mock of the vault itself — plus an in-process click `CliRunner`.
"""

from __future__ import annotations

import hashlib

import keyring
import keyring.errors
import pytest
from click.testing import CliRunner

from envoy.cli.main import cli
from envoy.cli.model import _principal_genesis_id
from envoy.cli.model import model as model_group

_PRINCIPAL = "alice@example"

# Env keys the picker + router + show touch. `load_dotenv` writes straight to
# os.environ (bypassing monkeypatch's restore), so the fixture clears them
# before AND after each test to keep the model env vars isolated per
# `rules/testing.md` § env-var test isolation.
_MODEL_ENV_KEYS = (
    "KAILASH_LLM_PROVIDER",
    "KAILASH_LLM_DEPLOYMENT",
    "OLLAMA_BASE_URL",
    "OLLAMA_DEFAULT_MODEL",
    "ANTHROPIC_MODEL",
    "OPENAI_PROD_MODEL",
    "DEEPSEEK_MODEL",
    "ENVOY_CUSTOM_MODEL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ENVOY_CUSTOM_API_KEY",
    "ENVOY_BOUNDARY_MODEL",
    "ENVOY_DIGEST_MODEL",
    "ENVOY_GRANT_MOMENT_MODEL",
    "ENVOY_DEFAULT_MODEL",
    "ENVOY_ENV_PATH",
    "ENVOY_PRINCIPAL_ID",
)


class _FakeKeyring:
    """Dict-backed stand-in for the OS keychain boundary."""

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


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> _FakeKeyring:
    fake = _FakeKeyring()
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake


@pytest.fixture
def clean_model_env():
    """Clear the model env vars before and after the test (load_dotenv leaks)."""
    import os

    saved = {k: os.environ.pop(k, None) for k in _MODEL_ENV_KEYS}
    yield
    for k in _MODEL_ENV_KEYS:
        os.environ.pop(k, None)
        original = saved.get(k)
        if original is not None:
            os.environ[k] = original


def _env_path(tmp_path) -> str:
    return str(tmp_path / "envoy.env")


def test_model_registered_on_root_group() -> None:
    assert "model" in cli.commands
    assert cli.commands["model"] is model_group


def test_model_has_show_and_set_subcommands() -> None:
    assert set(model_group.commands) == {"show", "set"}


def test_principal_genesis_id_is_sha256_hex() -> None:
    gid = _principal_genesis_id(_PRINCIPAL)
    assert gid == hashlib.sha256(_PRINCIPAL.encode("utf-8")).hexdigest()
    assert len(gid) == 64
    assert all(c in "0123456789abcdef" for c in gid)


def test_set_command_has_no_secret_value_option() -> None:
    """The API key MUST NOT be a value-bearing CLI option (security.md)."""
    params = {p.name for p in model_group.commands["set"].params}
    assert "api_key" not in params
    assert "secret" not in params
    assert "key" not in params
    assert "secret_stdin" in params


def test_show_unconfigured(clean_model_env, tmp_path) -> None:
    result = CliRunner().invoke(cli, ["model", "show", "--env-path", _env_path(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "not configured" in result.output
    assert "Per-task model overrides" in result.output


def test_set_ollama_then_show_roundtrip(clean_model_env, fake_keyring, tmp_path) -> None:
    runner = CliRunner()
    env_path = _env_path(tmp_path)
    set_result = runner.invoke(
        cli,
        [
            "model",
            "set",
            "--choice",
            "ollama",
            "--model",
            "llama3.2",
            "--env-path",
            env_path,
            "--principal",
            _PRINCIPAL,
        ],
    )
    assert set_result.exit_code == 0, set_result.output
    assert "ollama" in set_result.output
    assert "No API key needed" in set_result.output

    show = runner.invoke(cli, ["model", "show", "--env-path", env_path])
    assert show.exit_code == 0, show.output
    assert "ollama" in show.output
    assert "llama3.2" in show.output


def test_set_anthropic_key_to_vault_not_env(clean_model_env, fake_keyring, tmp_path) -> None:
    runner = CliRunner()
    env_path = _env_path(tmp_path)
    secret = "sk-ant-SECRET-do-not-leak"
    set_result = runner.invoke(
        cli,
        [
            "model",
            "set",
            "--choice",
            "anthropic",
            "--model",
            "claude-3-5-sonnet-20241022",
            "--secret-stdin",
            "--env-path",
            env_path,
            "--principal",
            _PRINCIPAL,
        ],
        input=f"{secret}\n",
    )
    assert set_result.exit_code == 0, set_result.output
    assert "keychain" in set_result.output

    # The plaintext key MUST NOT be in .env (security.md § No .env in Git).
    env_contents = (tmp_path / "envoy.env").read_text()
    assert secret not in env_contents
    assert "KAILASH_LLM_PROVIDER=anthropic" in env_contents
    assert "ANTHROPIC_MODEL=claude-3-5-sonnet-20241022" in env_contents

    # show reflects the provider + model, never the key.
    show = runner.invoke(cli, ["model", "show", "--env-path", env_path])
    assert show.exit_code == 0, show.output
    assert "anthropic" in show.output
    assert secret not in show.output


def test_set_secret_stdin_via_prompt(clean_model_env, fake_keyring, tmp_path) -> None:
    """Without --secret-stdin the key is read from a hidden prompt."""
    result = CliRunner().invoke(
        cli,
        [
            "model",
            "set",
            "--choice",
            "openai",
            "--model",
            "gpt-4o",
            "--env-path",
            _env_path(tmp_path),
            "--principal",
            _PRINCIPAL,
        ],
        input="sk-openai-prompt-secret\n",
    )
    assert result.exit_code == 0, result.output
    assert "openai" in result.output


def test_set_custom_requires_base_url(clean_model_env, fake_keyring, tmp_path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "model",
            "set",
            "--choice",
            "openai_compatible",
            "--model",
            "my-model",
            "--secret-stdin",
            "--env-path",
            _env_path(tmp_path),
            "--principal",
            _PRINCIPAL,
        ],
        input="some-key\n",
    )
    assert result.exit_code != 0
    assert "base_url" in result.output.lower() or "base-url" in result.output.lower()


def test_set_requires_principal(clean_model_env, fake_keyring, tmp_path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "model",
            "set",
            "--choice",
            "ollama",
            "--model",
            "llama3.2",
            "--env-path",
            _env_path(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "principal" in result.output.lower()


def test_set_rejects_unknown_choice(clean_model_env, tmp_path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "model",
            "set",
            "--choice",
            "gpt5-magic",
            "--model",
            "x",
            "--env-path",
            _env_path(tmp_path),
            "--principal",
            _PRINCIPAL,
        ],
    )
    assert result.exit_code != 0
    assert "choice" in result.output.lower() or "invalid" in result.output.lower()
