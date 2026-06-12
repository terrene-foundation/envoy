"""`python -m envoy` entrypoint.

Re-exports the root click group so the intuitive package-name module form
(`python -m envoy`) works alongside the canonical `envoy` console script and the
`python -m envoy.cli` fallback. All three resolve to the same CLI; this module
exists only so a user who guesses `python -m envoy` is not met with
"'envoy' is a package and cannot be directly executed" (UF-R2-L1).
"""

from envoy.cli.main import cli

if __name__ == "__main__":
    cli()
