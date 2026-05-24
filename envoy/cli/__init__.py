"""envoy CLI — `envoy <subcommand>` entrypoint.

Per `briefs/00-phase-01-mvp-scope.md` § Surfaces:
> `pipx install envoy-agent`
> `envoy init` / `envoy up` / `envoy boundaries` / (T-02-36) `envoy shamir ...`

This module is the click group root + subcommand registry. T-02-36 ships
the `envoy shamir recover` subcommand; T-02-43 ships `envoy shamir backup`
(currently inside the Boundary Conversation S8 flow); T-02-50+ adds
`envoy init` / `envoy up` / `envoy boundaries`.

The click group is structured so each subcommand owns its own module —
`envoy/cli/shamir.py` for Shamir, future `envoy/cli/init.py` for `envoy
init`, etc. This keeps the CLI surface composable and lets each
subcommand's tests load only the module they exercise.
"""

from envoy.cli.main import cli

__all__ = ["cli"]
