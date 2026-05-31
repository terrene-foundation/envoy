"""`envoy version` click subcommand — F5.2 Wave-5 CLI surface.

Per `workspaces/phase-01-mvp/02-plans/01-build-sequence.md` shard 19 — the
11-subcommand CLI routes every primitive; `version` is the lowest-invariant
member of that surface.

The version string is `envoy.__version__` — the single in-package literal.
`pyproject.toml::version` is kept in lockstep with it by
`tests/tier1/test_version_cli.py::test_version_consistency_pyproject_vs_dunder`
(per `rules/zero-tolerance.md` Rule 5 — version consistency).

Per `rules/framework-first.md`: click is the project CLI framework (argparse
BLOCKED). Per `rules/observability.md` MUST Rule 1+2: every invocation logs via
the framework logger.
"""

from __future__ import annotations

import logging

import click

import envoy

logger = logging.getLogger(__name__)


@click.command("version")
def version() -> None:
    """Print the installed envoy version and exit."""
    logger.info("envoy.version", extra={"version": envoy.__version__})
    click.echo(f"envoy {envoy.__version__}")


__all__ = ["version"]
