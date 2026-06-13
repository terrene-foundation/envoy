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

from envoy.cli.connection import connection as connection_group
from envoy.cli.digest import digest as digest_group
from envoy.cli.grant import grant as grant_group
from envoy.cli.init import init as init_group
from envoy.cli.ledger import ledger as ledger_group
from envoy.cli.model import model as model_group
from envoy.cli.posture import posture as posture_command
from envoy.cli.shamir import shamir as shamir_group
from envoy.cli.version import version as version_command

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

    Currently ships `envoy shamir`, `envoy digest`, `envoy posture`,
    `envoy version`, `envoy connection`, `envoy model`, `envoy ledger`,
    `envoy init`, and `envoy grant` (9 of 10 canonical subcommands); the
    remaining `envoy chat` completes the surface in Phase 02
    (`specs/mvp-build-sequence.md` line 128 + Phase-02 hooks item 9).
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
cli.add_command(posture_command)
cli.add_command(version_command)
cli.add_command(connection_group)
cli.add_command(model_group)
cli.add_command(ledger_group)
cli.add_command(init_group)
cli.add_command(grant_group)


__all__ = ["cli"]
