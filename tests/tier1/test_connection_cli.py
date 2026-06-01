"""Tier 1 tests for `envoy connection` (F5.2 Wave-5 CLI surface).

Pins the invariants of the OS-keychain Connection Vault CLI
(`specs/connection-vault.md`):

1. **add → list → remove round-trip** — a stored credential surfaces in
   `list` and is gone after `remove` (real `ConnectionVault` + real
   sha256 `principal_genesis_id`; only the OS-keychain boundary is faked).
2. **Secrets are never displayed** — `list` shows service + type + id, never
   the secret value.
3. **Secrets are never a CLI argument** — the `add` command exposes no
   value-bearing secret option; the secret arrives via hidden prompt or
   `--secret-stdin` (per `rules/security.md`).
4. **Principal required** — no `--principal` / `ENVOY_PRINCIPAL_ID` exits
   non-zero with an actionable message.
5. **Invalid entry id** — `remove` on a non-UUID exits non-zero cleanly.
6. **Surface stability** — `connection` is registered on the root group.

Tier 1 scope: real `ConnectionVault` adapter with the OS-keychain boundary
(`keyring.{set,get,delete}_password`) monkeypatched to a dict — NOT a mock of
the vault itself — plus in-process click `CliRunner`.
"""

from __future__ import annotations

import hashlib

import keyring
import keyring.errors
import pytest
from click.testing import CliRunner

from envoy.cli.connection import _principal_genesis_id
from envoy.cli.connection import connection as connection_group
from envoy.cli.main import cli

_PRINCIPAL = "alice@example"


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
    monkeypatch.delenv("ENVOY_PRINCIPAL_ID", raising=False)
    return fake


def test_connection_registered_on_root_group() -> None:
    assert "connection" in cli.commands
    assert cli.commands["connection"] is connection_group


def test_principal_genesis_id_is_sha256_hex() -> None:
    gid = _principal_genesis_id(_PRINCIPAL)
    assert gid == hashlib.sha256(_PRINCIPAL.encode("utf-8")).hexdigest()
    assert len(gid) == 64
    assert all(c in "0123456789abcdef" for c in gid)


def test_add_command_has_no_secret_value_option() -> None:
    """The secret MUST NOT be a value-bearing CLI option (security.md)."""
    params = {p.name for p in connection_group.commands["add"].params}
    assert "secret" not in params
    assert "secret_value" not in params
    assert "secret_stdin" in params


def test_list_empty(fake_keyring: _FakeKeyring) -> None:
    result = CliRunner().invoke(cli, ["connection", "list", "--principal", _PRINCIPAL])
    assert result.exit_code == 0, result.output
    assert "No stored credentials" in result.output


def test_add_list_remove_roundtrip(fake_keyring: _FakeKeyring) -> None:
    runner = CliRunner()
    add = runner.invoke(
        cli,
        [
            "connection",
            "add",
            "--service",
            "openai",
            "--type",
            "api_key",
            "--secret-stdin",
            "--principal",
            _PRINCIPAL,
        ],
        input="sk-secret-value-123\n",
    )
    assert add.exit_code == 0, add.output
    assert "Stored credential" in add.output

    lst = runner.invoke(cli, ["connection", "list", "--principal", _PRINCIPAL])
    assert lst.exit_code == 0, lst.output
    assert "openai" in lst.output
    assert "api_key" in lst.output
    assert "sk-secret-value-123" not in lst.output  # secret NEVER displayed

    entry_id = lst.output.split()[0]
    rm = runner.invoke(cli, ["connection", "remove", entry_id, "--principal", _PRINCIPAL])
    assert rm.exit_code == 0, rm.output
    assert "Removed credential" in rm.output

    lst2 = runner.invoke(cli, ["connection", "list", "--principal", _PRINCIPAL])
    assert "No stored credentials" in lst2.output


def test_add_via_hidden_prompt(fake_keyring: _FakeKeyring) -> None:
    """Without --secret-stdin the secret is read from a hidden prompt."""
    result = CliRunner().invoke(
        cli,
        [
            "connection",
            "add",
            "--service",
            "telegram-bot",
            "--type",
            "bot_token",
            "--principal",
            _PRINCIPAL,
        ],
        input="prompt-secret\n",
    )
    assert result.exit_code == 0, result.output
    assert "Stored credential" in result.output


def test_remove_invalid_uuid(fake_keyring: _FakeKeyring) -> None:
    result = CliRunner().invoke(
        cli, ["connection", "remove", "not-a-uuid", "--principal", _PRINCIPAL]
    )
    assert result.exit_code != 0
    assert "uuid" in result.output.lower()


def test_requires_principal(fake_keyring: _FakeKeyring) -> None:
    result = CliRunner().invoke(cli, ["connection", "list"])
    assert result.exit_code != 0
    assert "principal" in result.output.lower()
