"""`envoy connection` click subcommand group — F5.2 Wave-5 CLI surface.

Per `specs/mvp-build-sequence.md` line 128 (shard 19 § 3.4) +
`specs/connection-vault.md`. Three subcommands manage the OS-keychain-backed
Connection Vault:

- ``envoy connection list``           — list stored credentials (NEVER secrets)
- ``envoy connection add``            — store a new credential (secret via prompt)
- ``envoy connection remove <id>``    — delete a credential by entry id

The vault is keyed by ``principal_genesis_id = sha256(principal_id)`` — the
64-char lowercase-hex shape the vault requires (``validate_principal_genesis_id``),
matching the vault tests' ``_hex_principal`` helper and the posture-store
derivation (``_posture_store_agent_id``), so a principal's connections and
posture share one stable hash identity. There is no ``--vault`` path:
credentials live in the OS keychain (``keyring``), not a file vault.

Per `rules/framework-first.md`: click is the project CLI framework (argparse
BLOCKED). Per `rules/observability.md` MUST Rule 1+2: every invocation logs via
the framework logger. Per `rules/security.md` § "No secrets in logs" + § MUST
NOT: the secret is NEVER a CLI argument (it would leak in shell history and the
process table) — it is read from a hidden prompt, or from stdin with
``--secret-stdin`` for non-interactive use.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from uuid import UUID

import click

from envoy.connection_vault import (
    ConnectionVault,
    CredentialType,
    EntryNotFoundError,
    InvalidServiceIdentifierError,
    KeychainUnavailableError,
    RotationPolicy,
)
from envoy.envelope import EnvelopeScopeRef

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_NO_PRINCIPAL = 20


def _resolve_principal(principal: str | None) -> str:
    pid = principal or os.environ.get("ENVOY_PRINCIPAL_ID")
    if not pid:
        raise click.ClickException(
            "no principal — pass --principal or set ENVOY_PRINCIPAL_ID",
        )
    return pid


def _principal_genesis_id(principal_id: str) -> str:
    """Derive the vault's 64-hex ``principal_genesis_id`` from the pseudonym.

    The Connection Vault keys its OS-keychain namespace by a sha256-hex
    ``principal_genesis_id`` (``^[0-9a-f]{64}$`` per
    ``validate_principal_genesis_id``). We derive it from the principal
    pseudonym exactly as the vault tests (``_hex_principal``) and the
    posture-store bridge (``_posture_store_agent_id``) do, so a principal's
    connections and posture target one stable hash identity.
    """
    return hashlib.sha256(principal_id.encode("utf-8")).hexdigest()


def _build_vault(principal_id: str) -> ConnectionVault:
    return ConnectionVault(principal_genesis_id=_principal_genesis_id(principal_id))


@click.group()
def connection() -> None:
    """Manage stored service credentials in your OS keychain."""


@connection.command("list")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
def connection_list(principal: str | None) -> None:
    """List stored credentials — service, type, and id; never the secret."""
    pid = _resolve_principal(principal)
    vault = _build_vault(pid)
    logger.info("envoy.connection.list.start", extra={"principal_id_prefix": pid[:8]})
    try:
        entries = vault.list_by_principal()
    except KeychainUnavailableError as exc:
        raise click.ClickException(f"OS keychain unavailable: {exc}") from exc
    if not entries:
        click.echo("No stored credentials.")
        return
    for e in entries:
        expires = e.expires_at.isoformat() if e.expires_at else "never"
        click.echo(
            f"{e.entry_id}  {e.service_identifier}  [{e.credential_type.value}]  "
            f"created={e.created_at.date()}  expires={expires}  uses={e.usage_counter}"
        )


@connection.command("add")
@click.option("--service", required=True, help="Service identifier (e.g. openai, telegram-bot).")
@click.option(
    "--type",
    "credential_type",
    type=click.Choice([t.value for t in CredentialType], case_sensitive=False),
    default=CredentialType.API_KEY.value,
    show_default=True,
    help="Credential type.",
)
@click.option("--channel", default=None, help="Channel scope (optional; e.g. cli, telegram).")
@click.option(
    "--rotation",
    type=click.Choice([r.value for r in RotationPolicy], case_sensitive=False),
    default=RotationPolicy.NEVER.value,
    show_default=True,
    help="Rotation policy.",
)
@click.option(
    "--secret-stdin",
    is_flag=True,
    help="Read the secret from stdin instead of a hidden prompt (non-interactive).",
)
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
def connection_add(
    service: str,
    credential_type: str,
    channel: str | None,
    rotation: str,
    secret_stdin: bool,
    principal: str | None,
) -> None:
    """Store a new credential.

    The secret is read from a hidden prompt (or stdin with ``--secret-stdin``)
    — NEVER passed as a command argument, so it never lands in shell history or
    the process table.
    """
    pid = _resolve_principal(principal)
    vault = _build_vault(pid)
    secret = (
        sys.stdin.readline().rstrip("\n")
        if secret_stdin
        else click.prompt("Secret", hide_input=True)
    )
    if not secret:
        raise click.ClickException("empty secret — nothing stored.")
    logger.info(
        "envoy.connection.add.start",
        extra={
            "principal_id_prefix": pid[:8],
            "service": service,
            "credential_type": credential_type,
        },
    )
    try:
        entry = vault.set(
            credential_type=CredentialType(credential_type),
            service_identifier=service,
            entry_envelope_scope=EnvelopeScopeRef(service_identifier=service, channel=channel),
            secret=secret,
            rotation_policy=RotationPolicy(rotation),
        )
    except InvalidServiceIdentifierError as exc:
        raise click.ClickException(f"invalid service identifier: {exc}") from exc
    except KeychainUnavailableError as exc:
        raise click.ClickException(f"OS keychain unavailable: {exc}") from exc
    click.echo(f"Stored credential {entry.entry_id} for {service}.")


@connection.command("remove")
@click.argument("entry_id")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
def connection_remove(entry_id: str, principal: str | None) -> None:
    """Delete a stored credential by its entry id (a UUID from `list`)."""
    pid = _resolve_principal(principal)
    try:
        uid = UUID(entry_id)
    except ValueError as exc:
        raise click.ClickException(f"invalid entry id (not a UUID): {entry_id}") from exc
    vault = _build_vault(pid)
    logger.info(
        "envoy.connection.remove.start",
        extra={"principal_id_prefix": pid[:8], "entry_id": str(uid)},
    )
    try:
        vault.delete(uid)
    except EntryNotFoundError as exc:
        raise click.ClickException(f"no credential with id {uid}") from exc
    except KeychainUnavailableError as exc:
        raise click.ClickException(f"OS keychain unavailable: {exc}") from exc
    click.echo(f"Removed credential {uid}.")


__all__ = ["connection"]
