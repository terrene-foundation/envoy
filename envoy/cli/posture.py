"""`envoy posture` click subcommand — F5.2 Wave-5 CLI surface.

Per `workspaces/phase-01-mvp/02-plans/01-build-sequence.md` shard 19 (the
11-subcommand CLI routes every primitive) + `specs/posture-ladder.md`.

Phase-01 ships the READ half — show the principal's current autonomy-ladder
posture and, in plain language, what that level lets envoy do. The signed
ratchet-down (`envoy posture --set TOOL`, Genesis-signed per
`specs/posture-ladder.md` § Ratchet-down) lands with the init/up signing CLI
shard; this command deliberately exposes no `--set` so it makes no claim it
cannot back.

The posture is read from the SQLite-backed `SQLitePostureStore` via
`envoy.trust.store.TrustStoreAdapter.current_posture()`. A principal with no
recorded transition yet resolves to the safe default (SUPERVISED), so the
command works on first run before any Genesis seeding.

Per `rules/framework-first.md`: click is the project CLI framework (argparse
BLOCKED). Per `rules/observability.md` MUST Rule 1+2: every invocation logs via
the framework logger. The principal is resolved from `ENVOY_PRINCIPAL_ID` (or
`--principal`); the vault path from `ENVOY_VAULT_PATH` (or `--vault`), matching
the `envoy digest` idiom.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib

import click

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_NO_PRINCIPAL = 20

_DEFAULT_VAULT = "~/.envoy/trust_vault.db"

# Plain-language one-liner per tier (per `rules/communication.md`: translate
# the spec's mechanism into something a non-technical user can act on). The
# canonical mechanism lives in `specs/posture-ladder.md` § Per-tier semantics;
# these strings are the user-facing translation, keyed on `TrustPosture.value`.
_TIER_PLAIN_LANGUAGE = {
    "pseudo": (
        "Read-only. envoy can look things up but takes no real actions — "
        "every step is simulated and then discarded."
    ),
    "tool": "envoy asks you to approve each individual action before it runs.",
    "supervised": (
        "envoy shows you a whole plan up front; you approve it once and the "
        "steps inside run without asking again."
    ),
    "delegating": (
        "envoy acts on its own within the boundaries you set, and only checks "
        "in when it would cross one."
    ),
    "autonomous": (
        "Like delegating, but with wider boundaries and fewer check-ins — the "
        "most independent level."
    ),
}


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


@click.command("posture")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
def posture(principal: str | None, vault: str | None) -> None:
    """Show your current autonomy level and what it lets envoy do."""
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)

    async def _run() -> str:
        from envoy.trust.store import TrustStoreAdapter

        adapter = TrustStoreAdapter(vault_path=vault_path, principal_id=pid)
        try:
            await adapter.initialize()
            current = await adapter.current_posture()
        finally:
            await adapter.close()
        return current.value

    logger.info("envoy.posture.show.start", extra={"principal_id_prefix": pid[:8]})
    tier = asyncio.run(_run())
    description = _TIER_PLAIN_LANGUAGE.get(tier, "")
    click.echo(f"Autonomy level: {tier.upper()}")
    if description:
        click.echo(f"  {description}")


__all__ = ["posture"]
