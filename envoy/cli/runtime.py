# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""`envoy runtime` click subcommand group — WS-1 S3p Wire surface.

Two subcommands manage which Kailash runtime Envoy programs against (ADR-0001
runtime pluggability; ADR-0009 item 4 transparent disclosure — no hidden
defaults):

- ``envoy runtime show``   — report the active runtime from the durable
                             runtime-choice config (read-only; verifies the
                             config signature when a principal is resolvable).
- ``envoy runtime switch`` — switch the active runtime: cold passphrase unlock
                             → target attestation → T-015 re-read checkpoint →
                             Genesis-signed ``runtime_switch`` Ledger entry →
                             flip the durable default → confirm copy.

The switch state machine lives in ``envoy.runtime.runtime_switch``; this CLI
wires it to the real ``TrustVault`` + durable ``EnvoyLedger`` + key manager
exactly as ``envoy init`` assembles them, and prints the user-facing copy.

Per `rules/framework-first.md`: click is the project CLI framework (argparse
BLOCKED). Per `rules/observability.md` MUST Rule 1+2: every invocation logs via
the framework logger with the CLI session correlation id. The vault passphrase
is read from a hidden prompt or ``--passphrase-stdin`` — NEVER a CLI argument
(it would leak in shell history + the process table), exactly as
`envoy init` / `envoy connection add` handle secrets (`rules/security.md`).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

import click

from envoy.ledger.bootstrap import (
    LEDGER_ALGORITHM_IDENTIFIER,
    LEDGER_DEVICE_ID,
    LEDGER_SIGNING_KEY_ID,
    open_durable_ledger,
)
from envoy.ledger.keystore import (
    LedgerKeyringSelectorError,
    load_or_create_ledger_key_manager,
    resolve_keyring_backend,
)
from envoy.runtime.errors import RsBindingsNotAvailableInPhase01Error
from envoy.runtime.runtime_picker import (
    RuntimeChoiceSignatureError,
    presented_default_family,
    read_runtime_choice,
    verify_runtime_choice,
)
from envoy.runtime.runtime_switch import (
    RuntimeSwitchAttestationError,
    WarmVaultSwitchRefusedError,
    perform_runtime_switch,
)
from envoy.trust.errors import VaultUnlockFailedError
from envoy.trust.vault import TrustVault

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_NO_PRINCIPAL = 20
EXIT_KEYRING_SELECTOR = 32
EXIT_NO_VAULT = 50
EXIT_UNLOCK_FAILED = 51
EXIT_ATTESTATION_FAILED = 52
EXIT_RS_UNAVAILABLE = 53

_DEFAULT_VAULT = "~/.envoy/trust_vault.db"
_VALID_TARGETS = ("kailash-rs-bindings", "kailash-py")


def _cli_session_id() -> str:
    return os.environ.get("ENVOY_CLI_SESSION_ID", "")


def _resolve_principal(principal: str | None) -> str:
    pid = principal or os.environ.get("ENVOY_PRINCIPAL_ID")
    if not pid:
        raise click.ClickException(
            "no principal — pass --principal or set ENVOY_PRINCIPAL_ID"
        )
    return pid


def _principal_genesis_id(principal_id: str) -> str:
    """Derive the 64-hex ``principal_genesis_id`` — identical derivation to
    `envoy connection` / `envoy model` so a principal's runtime choice shares
    the one stable hash identity."""
    return hashlib.sha256(principal_id.encode("utf-8")).hexdigest()


def _resolve_vault_path(vault: str | None) -> Path:
    raw = vault or os.environ.get("ENVOY_VAULT_PATH") or _DEFAULT_VAULT
    return Path(raw).expanduser()


def _resolve_keyring_backend_or_exit(log_extra: dict[str, Any]) -> Any:
    """Resolve the ENVOY_KEYRING backend, exiting cleanly (32) on a bad selector
    — mirrors `envoy init` / `envoy grant` so every keychain-touching verb
    threads the SAME headless override seam."""
    try:
        return resolve_keyring_backend()
    except LedgerKeyringSelectorError as exc:
        logger.warning("envoy.runtime.bad_keyring_selector", extra=log_extra)
        click.echo(f"\n{exc}\n", err=True)
        raise SystemExit(EXIT_KEYRING_SELECTOR) from exc


@click.group()
def runtime() -> None:
    """Choose and inspect which Kailash runtime envoy programs against."""


@runtime.command("show")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
def runtime_show(principal: str | None) -> None:
    """Show the active runtime — and, when a principal is resolvable, whether the
    runtime-choice config's signature verifies (tamper detection)."""
    log_extra = {"cli_session_id": _cli_session_id()}
    logger.info("envoy.runtime.show.start", extra=log_extra)

    choice = read_runtime_choice()
    if choice is None:
        default_family = presented_default_family()
        click.echo("Active runtime: kailash-py (no explicit choice yet).")
        click.echo(
            f"  The first-run picker has not run; the default offered is "
            f"{default_family}."
        )
        click.echo("  Run `envoy runtime switch <target>` to choose a runtime.")
        return

    click.echo(f"Active runtime: {choice.runtime_family}")
    click.echo(f"  Chosen at: {choice.chosen_at}")
    click.echo(f"  Chosen by genesis: {choice.chosen_by_genesis_id[:8]}…")

    # Signature verification is a real tamper check — but it needs the signing
    # key, so it is only attempted when a principal is resolvable. Never print a
    # fake "verified" (per rules/zero-tolerance.md Rule 2): say plainly when the
    # signature was not checked.
    pid = principal or os.environ.get("ENVOY_PRINCIPAL_ID")
    if not pid:
        click.echo(
            "  Signature: not checked (pass --principal or set "
            "ENVOY_PRINCIPAL_ID to verify the config has not been tampered)."
        )
        return

    backend = _resolve_keyring_backend_or_exit(log_extra)
    try:
        verified = asyncio.run(_verify_choice_signature(pid, choice, backend))
    except RuntimeChoiceSignatureError:
        # A signature mismatch means the config bytes do not verify under this
        # principal's CURRENT signing key. On a persistent OS keychain that
        # indicates tampering; under an ephemeral keyring (ENVOY_KEYRING=memory,
        # headless/CI) the key is regenerated per process, so a mismatch is
        # expected, not tampering. Report the ambiguity honestly — never a bare
        # "verified", never a false "tampered" alarm.
        click.echo(
            "  Signature: ⚠ could not be verified with this principal's current "
            "signing key."
        )
        click.echo(
            "    On the OS keychain this indicates the config was changed without "
            "re-signing (re-run `envoy runtime switch`). Under a memory/ephemeral "
            "keyring it is expected (the signing key is per-process)."
        )
        return
    if verified:
        click.echo("  Signature: ✓ verified (config is authentic).")


async def _verify_choice_signature(
    principal_id: str, choice: Any, backend: Any
) -> bool:
    key_manager = await load_or_create_ledger_key_manager(
        principal_id=principal_id,
        signing_key_id=LEDGER_SIGNING_KEY_ID,
        keyring_backend=backend,
    )
    pubkey = key_manager.get_public_key(LEDGER_SIGNING_KEY_ID)
    if pubkey is None:
        raise click.ClickException(
            f"no signing public key for principal {principal_id[:8]}… — cannot "
            f"verify the runtime-choice signature."
        )
    await verify_runtime_choice(choice, key_manager=key_manager, expected_pubkey=pubkey)
    return True


@runtime.command("switch")
@click.argument("target", type=click.Choice(_VALID_TARGETS, case_sensitive=False))
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
@click.option(
    "--passphrase-stdin",
    is_flag=True,
    default=False,
    help="Read the vault passphrase from stdin (non-interactive) instead of a hidden prompt.",
)
def runtime_switch(
    target: str, principal: str | None, vault: str | None, passphrase_stdin: bool
) -> None:
    """Switch the active runtime to TARGET (kailash-rs-bindings | kailash-py).

    Runs the full state machine: cold passphrase unlock → target attestation →
    T-015 envelope re-read checkpoint → Genesis-signed `runtime_switch` Ledger
    entry → flip the durable default. The `runtime_switch` record is written
    ONLY after the target attests (attestation-before-record).
    """
    log_extra = {"cli_session_id": _cli_session_id(), "target": target}
    logger.info("envoy.runtime.switch.start", extra=log_extra)

    try:
        pid = _resolve_principal(principal)
    except click.ClickException as exc:
        click.echo(f"\n{exc.message}\n", err=True)
        raise SystemExit(EXIT_NO_PRINCIPAL) from exc

    vault_path = _resolve_vault_path(vault)
    if not vault_path.exists():
        click.echo(
            f"\nNo vault at {vault_path}. Run `envoy init` first to set up your "
            f"vault before switching runtimes.\n",
            err=True,
        )
        raise SystemExit(EXIT_NO_VAULT)

    backend = _resolve_keyring_backend_or_exit(log_extra)

    # Read the passphrase from stdin or a hidden prompt — NEVER a CLI argument.
    if passphrase_stdin:
        passphrase = sys.stdin.readline().rstrip("\n")
    else:
        passphrase = click.prompt(
            "Vault passphrase (required — switching runtimes needs a cold unlock)",
            hide_input=True,
        )

    try:
        result = asyncio.run(
            _run_switch(
                target_family=target,
                principal_id=pid,
                vault_path=vault_path,
                passphrase=passphrase,
                backend=backend,
            )
        )
    except WarmVaultSwitchRefusedError as exc:
        click.echo(f"\n{exc}\n", err=True)
        raise SystemExit(EXIT_UNLOCK_FAILED) from exc
    except VaultUnlockFailedError as exc:
        click.echo(
            "\nVault unlock failed — wrong passphrase. The runtime was NOT "
            "switched.\n",
            err=True,
        )
        raise SystemExit(EXIT_UNLOCK_FAILED) from exc
    except RsBindingsNotAvailableInPhase01Error as exc:
        click.echo(
            f"\nThe Rust runtime (kailash-rs-bindings) is not available yet — its "
            f"byte-identical conformance is not green on both runtimes. The "
            f"runtime was NOT switched.\n  ({exc})\n",
            err=True,
        )
        raise SystemExit(EXIT_RS_UNAVAILABLE) from exc
    except RuntimeSwitchAttestationError as exc:
        click.echo(
            f"\nTarget runtime attestation failed — the runtime was NOT switched "
            f"(no record written).\n  ({exc})\n",
            err=True,
        )
        raise SystemExit(EXIT_ATTESTATION_FAILED) from exc

    # Confirm copy — transparent disclosure of exactly what changed (ADR-0009 item 4).
    click.echo("")
    click.echo(f"Runtime switched: {result.from_family} → {result.to_family}")
    click.echo(f"  Target attested: {result.target_attestation_hash}")
    invalidated = result.re_read_checkpoint_result["invalidated"]
    if invalidated:
        click.echo(
            "  Envelope re-read checkpoint forced (T-015): algorithm identifier "
            "changed, so cached envelopes are re-read under the new runtime."
        )
    else:
        click.echo(
            "  Envelope re-read checkpoint: algorithm identifier unchanged "
            "(no cached envelopes needed re-reading)."
        )
    click.echo(f"  Ledger entry: {result.runtime_switch_entry_id}")
    click.echo(f"  Active runtime is now {result.to_family}.")


async def _run_switch(
    *,
    target_family: str,
    principal_id: str,
    vault_path: Path,
    passphrase: str,
    backend: Any,
) -> Any:
    """Open the real vault + ledger + key manager and run the switch.

    Mirrors `envoy.boundary_conversation.init_bootstrap` assembly: a sealed
    `TrustVault` (the switch state machine performs the cold unlock), the durable
    ledger over the same vault path, and the keychain-backed key manager.
    """
    genesis_id = _principal_genesis_id(principal_id)
    current_choice = read_runtime_choice()
    current_family = (
        current_choice.runtime_family if current_choice is not None else "kailash-py"
    )

    vault = TrustVault(vault_path, idle_ttl_seconds=900)
    key_manager = await load_or_create_ledger_key_manager(
        principal_id=principal_id,
        signing_key_id=LEDGER_SIGNING_KEY_ID,
        keyring_backend=backend,
    )
    durable = await open_durable_ledger(
        vault_path=vault_path,
        key_manager=key_manager,
        signing_key_id=LEDGER_SIGNING_KEY_ID,
        device_id=LEDGER_DEVICE_ID,
        algorithm_identifier=LEDGER_ALGORITHM_IDENTIFIER,
    )
    try:
        return await perform_runtime_switch(
            target_family=target_family,
            current_family=current_family,
            vault=vault,
            passphrase=passphrase,
            ledger=durable.ledger,
            key_manager=key_manager,
            signing_key_id=LEDGER_SIGNING_KEY_ID,
            genesis_id=genesis_id,
        )
    finally:
        await durable.aclose()
        if vault.is_unlocked:
            await vault.lock()


__all__ = ["runtime"]
