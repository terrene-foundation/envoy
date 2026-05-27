"""`envoy digest` click subcommand group — T-04-83.

Per `specs/daily-digest.md` § Interaction + § Schedule. Four subcommands:

- `envoy digest today`   — run the aggregate → render → fan-out pipeline now
                            and print the rendered digest (CLI delivery).
- `envoy digest pause`   — temporarily disable the digest (`--days N`).
- `envoy digest resume`  — re-enable a paused digest.
- `envoy digest schedule --hour H [--tz IANA]` — set the daily delivery hour.

Per `rules/framework-first.md`: click is the project CLI framework (argparse
BLOCKED). Per `rules/observability.md` MUST Rule 1+2: every invocation logs via
the framework logger bound to the root group's `cli_session_id`.

All four commands wire a real `DailyDigestService` via
`envoy.daily_digest.bootstrap.build_digest_service` — the orphan-detection
Rule 1 production call site. `pause`/`resume`/`schedule` persist to the
Trust-store-backed digest state (survives restart). `today` runs the real
pipeline; cross-process ledger aggregation arrives with the T-01-21 file-backed
audit store (the project-wide Phase-01 in-memory-ledger boundary).

The principal is resolved from `ENVOY_PRINCIPAL_ID`; the vault path from
`ENVOY_VAULT_PATH` (default `~/.envoy/trust_vault.db`). Both are also
`--principal` / `--vault` overridable per command.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib

import click

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_PRINCIPAL = 20
EXIT_NO_SCHEDULE = 21
EXIT_DELIVERY_FAILED = 22

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
def digest() -> None:
    """Morning digest — 2-minute summary of yesterday's actions + approvals."""


@digest.command("today")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
def digest_today(principal: str | None, vault: str | None) -> None:
    """Run the digest pipeline now and print the rendered summary."""
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)

    async def _run() -> None:
        from envoy.daily_digest.bootstrap import build_digest_service

        service, trust_store, channel_adapters = await build_digest_service(
            vault_path=vault_path, principal_id=pid
        )
        cli_adapter = channel_adapters["cli"]
        try:
            await cli_adapter.startup()
            await service.start()
            payload = await service.trigger_now(pid)
            click.echo(f"Digest {payload.digest_id} (form={payload.form})")
            click.echo(f"  actions:        {len(payload.summary.actions)}")
            click.echo(f"  refusals:       {len(payload.summary.refusals)}")
            click.echo(f"  pending grants: {len(payload.summary.pending_grants)}")
            click.echo(f"  planned today:  {len(payload.summary.planned_today)}")
            spend = payload.summary.spend
            click.echo(
                f"  spend:          {spend['current_microdollars']} / "
                f"{spend['monthly_ceiling_microdollars']} microdollars"
            )
            if payload.duress_banner.present:
                click.echo("  ⚠️  duress event — review on your primary channel")
        finally:
            await service.stop()
            await cli_adapter.shutdown()
            await trust_store.close()

    logger.info("envoy.digest.today.start", extra={"principal_id_prefix": pid[:8]})
    asyncio.run(_run())


@digest.command("pause")
@click.option("--days", default=7, show_default=True, help="Pause duration in days.")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
def digest_pause(days: int, principal: str | None, vault: str | None) -> None:
    """Temporarily disable the digest for --days (default 7)."""
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)

    async def _run() -> None:
        from envoy.daily_digest.bootstrap import build_digest_service

        service, trust_store, _channels = await build_digest_service(
            vault_path=vault_path, principal_id=pid
        )
        try:
            await service.pause(pid, duration_days=days)
            click.echo(f"Digest paused for {days} day(s).")
        finally:
            await trust_store.close()

    logger.info(
        "envoy.digest.pause.start",
        extra={"principal_id_prefix": pid[:8], "days": days},
    )
    asyncio.run(_run())


@digest.command("resume")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
def digest_resume(principal: str | None, vault: str | None) -> None:
    """Re-enable a paused digest."""
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)

    async def _run() -> None:
        from envoy.daily_digest.bootstrap import build_digest_service

        service, trust_store, _channels = await build_digest_service(
            vault_path=vault_path, principal_id=pid
        )
        try:
            await service.resume(pid)
            click.echo("Digest resumed.")
        finally:
            await trust_store.close()

    logger.info("envoy.digest.resume.start", extra={"principal_id_prefix": pid[:8]})
    asyncio.run(_run())


@digest.command("schedule")
@click.option("--hour", required=True, type=int, help="Delivery hour 0-23 (UTC).")
@click.option(
    "--tz", "timezone", default="UTC", show_default=True, help="Timezone (Phase-01: UTC only)."
)
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
def digest_schedule(hour: int, timezone: str, principal: str | None, vault: str | None) -> None:
    """Set the daily digest delivery hour."""
    if not 0 <= hour <= 23:
        raise click.ClickException(f"--hour must be in [0, 23] (got {hour})")
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)

    async def _run() -> None:
        from envoy.daily_digest.bootstrap import build_digest_service

        service, trust_store, _channels = await build_digest_service(
            vault_path=vault_path, principal_id=pid
        )
        try:
            await service.schedule(pid, hour=hour, timezone=timezone)
            click.echo(f"Digest scheduled for {hour:02d}:00 {timezone}.")
        finally:
            await trust_store.close()

    logger.info(
        "envoy.digest.schedule.start",
        extra={"principal_id_prefix": pid[:8], "hour": hour, "timezone": timezone},
    )
    asyncio.run(_run())


__all__ = ["digest"]
