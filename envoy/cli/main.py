"""`envoy` click group root.

Per `rules/framework-first.md`: click is the project's CLI framework (in
`pyproject.toml::dependencies` since envoy/cli/ inception). Direct
argparse is BLOCKED — click handles subcommand composition, --help
generation, and structured exit codes uniformly across the surface.

Per `rules/observability.md` MUST Rule 1: every CLI invocation MUST log
via the framework logger. The root group binds a `cli_session_id`
correlation ID per `rules/observability.md` MUST Rule 2 so the recovery
flow's `shamir.recover.start` / `shamir.recover.ok` log lines correlate
with the invoking shell session.
"""

from __future__ import annotations

import logging
import os
import uuid

import click

from envoy.cli.digest import digest as digest_group
from envoy.cli.shamir import shamir as shamir_group

logger = logging.getLogger(__name__)


@click.group()
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Logging verbosity for this CLI invocation.",
)
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """envoy — Autonomous AI where you set the boundaries.

    Phase 01 ships `envoy shamir recover` (T-02-36); upcoming shards add
    `envoy init`, `envoy up`, and `envoy boundaries` (T-02-50+).
    """
    cli_session_id = os.environ.get("ENVOY_CLI_SESSION_ID") or uuid.uuid4().hex
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["cli_session_id"] = cli_session_id
    logger.info(
        "envoy.cli.start",
        extra={"cli_session_id": cli_session_id, "log_level": log_level.upper()},
    )


cli.add_command(shamir_group)
cli.add_command(digest_group)


__all__ = ["cli"]
