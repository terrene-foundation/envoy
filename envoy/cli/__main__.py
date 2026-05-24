"""`python -m envoy.cli` entrypoint.

Equivalent to `envoy` when the `pipx install envoy-agent` console script
is not on PATH (dev environments, CI). Per `briefs/00-phase-01-mvp-scope.md`
§ Surfaces — `envoy` is the canonical surface; `python -m envoy.cli` is
the fallback.
"""

from envoy.cli.main import cli

if __name__ == "__main__":
    cli()
