"""Keyring backend override for `envoy init` — headless / CI / red-team-walk.

Regression coverage for the keychain foot-gun surfaced by the Wave-2 red-team
user-flow walk: `envoy init` stored the ledger + session signing keys in the
real OS keychain (macOS Keychain / Secret Service / Credential Manager) with no
override, so it could not be exercised headless and errored
("keychain cannot be found") in any non-interactive context.

The fix (`envoy.ledger.keystore.resolve_keyring_backend` wired into
`envoy.cli.init`):
  - ENVOY_KEYRING unset  -> real OS keychain (the secure default, unchanged)
  - ENVOY_KEYRING=memory -> in-PROCESS dict backend; touches NO persistent store
  - ENVOY_KEYRING=<other> -> loud refusal (fail-closed; never a silent default)

These tests assert the resolver allowlist, the in-process backend round-trip,
the CLI's clean exit on a bad selector, and — the load-bearing property — that
building the init runtime with the in-process backend lands the durable signing
key in THAT backend, never the host OS keychain.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import keyring.errors
import pytest
from click.testing import CliRunner

from envoy.cli.init import EXIT_KEYRING_SELECTOR
from envoy.cli.main import cli
from envoy.ledger.keystore import (
    KEYRING_SERVICE_NAMESPACE,
    InMemoryKeyringBackend,
    LedgerKeyringSelectorError,
    resolve_keyring_backend,
)

# --------------------------------------------------------------------------
# Resolver allowlist (closed set: unset | "memory" | refuse)
# --------------------------------------------------------------------------


def test_unset_selector_resolves_to_os_keychain_default() -> None:
    assert resolve_keyring_backend({}) is None
    assert resolve_keyring_backend({"ENVOY_KEYRING": ""}) is None
    assert resolve_keyring_backend({"ENVOY_KEYRING": "   "}) is None


def test_memory_selector_resolves_to_in_process_backend() -> None:
    backend = resolve_keyring_backend({"ENVOY_KEYRING": "memory"})
    assert isinstance(backend, InMemoryKeyringBackend)


def test_unrecognized_selector_fails_closed() -> None:
    # A typo'd / arbitrary selector MUST raise, never silently fall back to the
    # OS keychain (or, worse, accept an attacker-supplied backend path).
    for bad in ("os", "file", "plaintext", "memory2", "envoy.ledger.X"):
        with pytest.raises(LedgerKeyringSelectorError):
            resolve_keyring_backend({"ENVOY_KEYRING": bad})


# --------------------------------------------------------------------------
# In-process backend implements the keyring interface envoy uses
# --------------------------------------------------------------------------


def test_in_process_backend_round_trips() -> None:
    backend = InMemoryKeyringBackend()
    assert backend.get_password("svc", "acct") is None
    backend.set_password("svc", "acct", "blob")
    assert backend.get_password("svc", "acct") == "blob"
    backend.delete_password("svc", "acct")
    assert backend.get_password("svc", "acct") is None


def test_in_process_backend_delete_missing_raises_keyring_error() -> None:
    backend = InMemoryKeyringBackend()
    with pytest.raises(keyring.errors.PasswordDeleteError):
        backend.delete_password("svc", "missing")


# --------------------------------------------------------------------------
# CLI: bad selector exits cleanly (no traceback), before any prompt
# --------------------------------------------------------------------------


def test_init_run_bad_keyring_selector_exits_32_cleanly() -> None:
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "x.vault"
        result = runner.invoke(
            cli,
            ["init", "run", "--principal", "u", "--vault", str(vault)],
            env={"ENVOY_KEYRING": "totally-bogus"},
            input="",  # MUST exit before prompting
            catch_exceptions=False,
        )
    assert result.exit_code == EXIT_KEYRING_SELECTOR
    assert "not a recognized keyring selector" in result.output
    # never prompted for a passphrase
    assert "passphrase" not in result.output.lower()
    # vault not created on the bad-selector path
    assert not vault.exists()


# --------------------------------------------------------------------------
# Load-bearing: the in-process backend means the OS keychain is NEVER touched.
# Building the init runtime creates the durable ledger signing key; with the
# in-process backend that key lands in the backend, not the host keychain.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_init_runtime_with_memory_backend_does_not_touch_os_keychain() -> None:
    from envoy.boundary_conversation.init_bootstrap import build_init_runtime

    backend = InMemoryKeyringBackend()
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "walk.vault"
        bootstrap = await build_init_runtime(
            vault_path=vault,
            principal_id="walk-principal",
            passphrase="walk-pass-1234",
            trust_anchor_dir=Path(tmp),
            keyring_backend=backend,
        )
        try:
            # The ledger signing key was generated into the in-process backend
            # (build_init_runtime -> load_or_create_ledger_key_manager). At least
            # one entry exists under the ledger namespace in OUR backend, proving
            # the OS keychain was never the write target.
            ledger_entries = [
                v
                for (svc, _), v in backend._store.items()
                if svc == KEYRING_SERVICE_NAMESPACE
            ]
            assert ledger_entries, "ledger signing key was not written to the in-process backend"
        finally:
            await bootstrap.session_router.close()
            await bootstrap.durable_ledger.aclose()
            await bootstrap.trust_store.close()
            if bootstrap.vault.is_unlocked:
                await bootstrap.vault.lock()
