"""`envoy model` click subcommand group — F5.2 Wave-5 CLI surface.

Per `specs/mvp-build-sequence.md` line 128 (shard 19 § 3.4 canonical surface)
+ `DECISIONS.md` ADR-0006 (Model choice: BYOM at install, local default
available) + shard 13 § 3.1 (`byom_picker`) / § 3.2 (`EnvoyModelRouter`). Two
subcommands manage the user's Bring-Your-Own-Model selection:

- ``envoy model show``   — show the currently-configured provider + model
                           (read-only; NEVER prints an API key).
- ``envoy model set``    — run the BYOM picker: write the provider/model
                           selection to ``.env`` and route the API key into
                           the OS-keychain Connection Vault.

Per ADR-0006 the 5 BYOM choices are ``ollama`` (local, no key), ``anthropic``,
``openai``, ``deepseek``, and ``openai_compatible`` (a custom OpenAI-wire
endpoint — MLX, vLLM, OpenRouter, …). The API key is NEVER a CLI argument (it
would leak in shell history and the process table) — it is read from a hidden
prompt, or from stdin with ``--secret-stdin`` for non-interactive use, exactly
as ``envoy connection add`` does (per `rules/security.md` § "No secrets in
logs" + § MUST NOT).

The picker writes only model-name configuration + the ``KAILASH_LLM_PROVIDER``
selector (or ``KAILASH_LLM_DEPLOYMENT`` URI for custom) to ``.env``; the
plaintext key goes to the Connection Vault, never to ``.env`` (per
`rules/security.md` § No .env in Git + `rules/env-models.md`). The vault is
keyed by ``principal_genesis_id = sha256(principal_id)`` — the same 64-hex
identity ``envoy connection`` and the posture store use, so a principal's
model credential and connections share one stable hash namespace.

Per `rules/framework-first.md`: click is the project CLI framework (argparse
BLOCKED). Per `rules/observability.md` MUST Rule 1+2: every invocation logs via
the framework logger.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys

import click

from envoy.connection_vault import ConnectionVault, KeychainUnavailableError
from envoy.model.byom_picker import CHOICE_MODEL_ENV, SUPPORTED_CHOICES, byom_pick
from envoy.model.router import EnvoyModelRouter

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_NO_PRINCIPAL = 20

_DEFAULT_ENV_PATH = ".env"

#: Plain-language one-liner per BYOM choice (per `rules/communication.md`:
#: translate the mechanism into something a non-technical user can act on).
#: The canonical contract lives in ADR-0006 + byom_picker docstring; these
#: strings are the user-facing translation, keyed on the choice value.
_CHOICE_PLAIN_LANGUAGE = {
    "ollama": "Local model on your own machine — no API key, nothing leaves your computer.",
    "anthropic": "Claude models from Anthropic (cloud) — needs an Anthropic API key.",
    "openai": "GPT models from OpenAI (cloud) — needs an OpenAI API key.",
    "deepseek": "DeepSeek models (cloud) — needs a DeepSeek API key.",
    "openai_compatible": (
        "A custom endpoint that speaks the OpenAI format (e.g. MLX, vLLM, "
        "OpenRouter) — needs the endpoint URL and an API key."
    ),
}

#: Per-primitive override env-keys, shown by `model show`, with a
#: plain-language label. Sourced from the router so the two surfaces never
#: drift (per `rules/specs-authority.md` MUST Rule 9).
_PRIMITIVE_LABELS = {
    "boundary_conversation": "First-launch conversation",
    "daily_digest": "Daily digest",
    "grant_moment_summary": "Grant-moment summary",
    "default": "Everything else (default)",
}


def _resolve_principal(principal: str | None) -> str:
    pid = principal or os.environ.get("ENVOY_PRINCIPAL_ID")
    if not pid:
        raise click.ClickException(
            "no principal — pass --principal or set ENVOY_PRINCIPAL_ID",
        )
    return pid


def _principal_genesis_id(principal_id: str) -> str:
    """Derive the vault's 64-hex ``principal_genesis_id`` from the pseudonym.

    Identical derivation to ``envoy.cli.connection._principal_genesis_id`` and
    the posture-store bridge, so a principal's model credential and connections
    target one stable hash identity.
    """
    return hashlib.sha256(principal_id.encode("utf-8")).hexdigest()


def _build_vault(principal_id: str) -> ConnectionVault:
    return ConnectionVault(principal_genesis_id=_principal_genesis_id(principal_id))


@click.group()
def model() -> None:
    """Choose and inspect the AI model envoy uses (Bring Your Own Model)."""


@model.command("show")
@click.option(
    "--env-path",
    default=None,
    help=f"Path to the .env file to read (default {_DEFAULT_ENV_PATH} or ENVOY_ENV_PATH).",
)
def model_show(env_path: str | None) -> None:
    """Show the currently-configured provider and model — never the API key."""
    # Load .env so `show` reflects what `set` wrote, before reading os.environ
    # (per `rules/env-models.md` "ALWAYS Load .env Before Operations").
    from dotenv import load_dotenv

    resolved_env = env_path or os.environ.get("ENVOY_ENV_PATH") or _DEFAULT_ENV_PATH
    load_dotenv(resolved_env, override=False)

    logger.info("envoy.model.show.start", extra={"env_path": resolved_env})

    deployment_uri = os.environ.get("KAILASH_LLM_DEPLOYMENT")
    selector = os.environ.get("KAILASH_LLM_PROVIDER")

    if deployment_uri:
        # URI tier (custom OpenAI-compatible endpoint) wins per kaizen
        # from_env three-tier precedence (shard 13 § 2.5).
        click.echo("Active model provider: custom OpenAI-compatible endpoint")
        click.echo(f"  Endpoint: {deployment_uri}")
    elif selector:
        click.echo(f"Active model provider: {selector}")
        description = _CHOICE_PLAIN_LANGUAGE.get(selector)
        if description:
            click.echo(f"  {description}")
        model_env_key = CHOICE_MODEL_ENV.get(selector)
        if model_env_key:
            model_name = os.environ.get(model_env_key)
            click.echo(f"  Model: {model_name if model_name else '(not set)'}")
    else:
        click.echo("Active model provider: not configured.")
        click.echo("  Run `envoy model set` to pick a provider and model.")

    # Per-task overrides (router PRIMITIVE_MODEL_ENV_KEYS). An unset override
    # means that task uses the global default above.
    click.echo("Per-task model overrides:")
    for primitive, env_key in EnvoyModelRouter.PRIMITIVE_MODEL_ENV_KEYS.items():
        label = _PRIMITIVE_LABELS.get(primitive, primitive)
        override = os.environ.get(env_key)
        click.echo(f"  {label}: {override if override else '(uses default)'}")


@model.command("set")
@click.option(
    "--choice",
    required=True,
    type=click.Choice(sorted(SUPPORTED_CHOICES), case_sensitive=False),
    help="Which model provider to use.",
)
@click.option(
    "--model",
    "model_name",
    required=True,
    help="The model name to use (e.g. llama3.2, claude-3-5-sonnet-20241022, gpt-4o).",
)
@click.option(
    "--base-url",
    default=None,
    help="Endpoint URL — REQUIRED for openai_compatible; optional for a remote ollama.",
)
@click.option(
    "--secret-stdin",
    is_flag=True,
    help="Read the API key from stdin instead of a hidden prompt (non-interactive).",
)
@click.option(
    "--env-path",
    default=None,
    help=f"Path to the .env file to write (default {_DEFAULT_ENV_PATH} or ENVOY_ENV_PATH).",
)
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
def model_set(
    choice: str,
    model_name: str,
    base_url: str | None,
    secret_stdin: bool,
    env_path: str | None,
    principal: str | None,
) -> None:
    """Pick a model provider: write the selection to .env, store the key in your keychain.

    For ``ollama`` (local) no key is needed. For every cloud provider the API
    key is read from a hidden prompt (or stdin with ``--secret-stdin``) and
    stored in the OS keychain — it NEVER lands in .env or your shell history.
    """
    choice = choice.lower()
    pid = _resolve_principal(principal)
    resolved_env = env_path or os.environ.get("ENVOY_ENV_PATH") or _DEFAULT_ENV_PATH

    # Read the API key for cloud choices. ollama has no credential.
    api_key: str | None = None
    if choice != "ollama":
        api_key = (
            sys.stdin.readline().rstrip("\n")
            if secret_stdin
            else click.prompt("API key", hide_input=True)
        )
        if not api_key:
            raise click.ClickException("empty API key — nothing stored.")

    vault = _build_vault(pid)
    logger.info(
        "envoy.model.set.start",
        extra={"principal_id_prefix": pid[:8], "choice": choice, "env_path": resolved_env},
    )
    try:
        result = byom_pick(
            choice=choice,
            model_name=model_name,
            api_key=api_key,
            custom_base_url=base_url,
            env_path=resolved_env,
            vault=vault,
        )
    except ValueError as exc:
        # byom_pick fails loud on shape mismatch (unknown choice, missing
        # base_url for custom, api_key supplied for ollama, blank model) per
        # `rules/zero-tolerance.md` Rule 3a — surface it as a CLI error.
        raise click.ClickException(str(exc)) from exc
    except KeychainUnavailableError as exc:
        raise click.ClickException(f"OS keychain unavailable: {exc}") from exc

    click.echo(f"Model provider set to {result.choice} (model: {model_name}).")
    click.echo(f"  Wrote to {resolved_env}: {', '.join(result.env_keys_written)}")
    if result.vault_import_result is not None:
        click.echo("  API key stored securely in your OS keychain (not in .env).")
    else:
        click.echo("  No API key needed for a local model.")


__all__ = ["model"]
