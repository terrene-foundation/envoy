"""`envoy ledger` click subcommand group — EC-4 / EC-9 export surface.

Per `specs/mvp-build-sequence.md` line 128 (shard 19 § 3.4, canonical:
`ledger {export}`) + `specs/ledger.md` § "Export + independent verifier"
(line 594) + `specs/independent-verifier.md` § "Bundle wire format". One
Phase-01 subcommand:

- ``envoy ledger export [--format json] [--output PATH]`` — open the principal's
  durable ledger (the file-backed store the daily digest and future writers
  append to) and write the signed export bundle the separately-codebased
  Independent Verifier (`envoy-ledger-verifier`, EC-9) consumes.

The verifier interface is unidirectional: the producer writes a file, the
verifier reads it (`specs/independent-verifier.md` — no IPC, no shared library).
With no ``--output`` the bundle goes to stdout while logs go to stderr, so
``envoy ledger export > bundle.json`` yields a clean JSON artifact.

The reader opens the durable ledger through the SAME ledger identity
(signing-key id / device id / algorithm identifier) the writers use — the
shared constants in `envoy.ledger.bootstrap` — so it reads the SAME on-disk
ledger and the re-minted head + entry signatures verify against the SAME
keychain key (the cross-process EC-4 property).

Per `rules/framework-first.md`: click is the project CLI framework (argparse
BLOCKED). Per `rules/observability.md` MUST Rule 1+2: every invocation logs via
the framework logger. Per `rules/security.md`: the bundle carries only public
keys + signatures + content hashes — never private key material.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib

import click

from envoy.ledger.bootstrap import (
    LEDGER_ALGORITHM_IDENTIFIER,
    LEDGER_DEVICE_ID,
    LEDGER_SIGNING_KEY_ID,
    open_durable_ledger,
)
from envoy.ledger.errors import LedgerError
from envoy.ledger.keystore import load_or_create_ledger_key_manager

logger = logging.getLogger(__name__)

_DEFAULT_VAULT = "~/.envoy/trust_vault.db"


def _resolve_principal(principal: str | None) -> str:
    pid = principal or os.environ.get("ENVOY_PRINCIPAL_ID")
    if not pid:
        raise click.ClickException(
            "no principal — pass --principal or set ENVOY_PRINCIPAL_ID",
        )
    return pid


def _resolve_vault(vault: str | None) -> pathlib.Path:
    raw = vault or os.environ.get("ENVOY_VAULT_PATH") or _DEFAULT_VAULT
    path = pathlib.Path(raw).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@click.group()
def ledger() -> None:
    """Audit ledger — export a signed bundle for the independent verifier."""


@ledger.command("export")
@click.option(
    "--format",
    "export_format",
    default="json",
    show_default=True,
    type=click.Choice(["json"], case_sensitive=True),
    help="Bundle format. Phase 01 is JSON-only; the PDF form lands in Phase 02.",
)
@click.option(
    "--output",
    "-o",
    "output",
    default=None,
    help="Write the bundle to this file (default: stdout).",
)
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
def ledger_export(
    export_format: str,
    output: str | None,
    principal: str | None,
    vault: str | None,
) -> None:
    """Write the signed ledger export bundle (EC-4 / EC-9).

    Opens the principal's durable ledger and emits the bundle the
    separately-codebased Independent Verifier consumes. With no ``--output``
    the JSON goes to stdout (logs go to stderr), so
    ``envoy ledger export > bundle.json`` yields a clean bundle file.
    """
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)

    async def _run() -> str:
        # Open the SAME durable ledger the writers append to (shared identity),
        # export, and ALWAYS release the SQLite pool — even if export() raises.
        key_manager = await load_or_create_ledger_key_manager(
            principal_id=pid, signing_key_id=LEDGER_SIGNING_KEY_ID
        )
        durable = await open_durable_ledger(
            vault_path=vault_path,
            key_manager=key_manager,
            signing_key_id=LEDGER_SIGNING_KEY_ID,
            device_id=LEDGER_DEVICE_ID,
            algorithm_identifier=LEDGER_ALGORITHM_IDENTIFIER,
        )
        try:
            bundle = await durable.ledger.export()
        finally:
            await durable.aclose()
        # Pretty, deterministic JSON. The verifier re-canonicalizes on read
        # (JCS RFC 8785), so file formatting is cosmetic — receipt_hash commits
        # to the canonical form, not these bytes.
        return json.dumps(bundle.to_dict(), indent=2, sort_keys=True)

    logger.info(
        "envoy.ledger.export.start",
        extra={"principal_id_prefix": pid[:8], "format": export_format},
    )
    try:
        bundle_json = asyncio.run(_run())
    except LedgerError as exc:
        # Empty ledger: export() refuses because verifier invariant 1 forbids an
        # empty bundle. Clean, actionable CLI error — never a raw traceback.
        raise click.ClickException(
            f"nothing to export — the ledger has no entries yet ({exc}). "
            "Record activity first (e.g. run `envoy digest today`).",
        ) from exc

    if output is None:
        click.echo(bundle_json)
        logger.info("envoy.ledger.export.ok", extra={"sink": "stdout"})
        return

    out_path = pathlib.Path(output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(bundle_json + "\n", encoding="utf-8")
    click.echo(f"Wrote ledger export bundle to {out_path}")
    logger.info("envoy.ledger.export.ok", extra={"sink": str(out_path)})


__all__ = ["ledger"]
