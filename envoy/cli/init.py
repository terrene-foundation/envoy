"""`envoy init` click subcommand group — S4i.

Per `specs/session-state.md` § Session definition ("Start: user unlock ceremony
OR explicit `envoy session start` CLI") + `specs/boundary-conversation.md`
(first-install ritual) + `specs/independent-verifier.md` § "Trust anchor file
format" (install emits `trust-anchor.json` alongside the Shamir ceremony).

`envoy init` is the first-time install ritual: it runs the Boundary
Conversation S0→S10 end-to-end (producing the signed Genesis Record + the
GENESIS_BARE→PSEUDO posture ratchet), writes a durable WRITE-ONCE session
genesis into the S4s store so a fresh process reads it back, and emits
`trust-anchor.json` (public verification material only) alongside the user's
Shamir 3-of-5 paper-shard ritual.

Per `rules/framework-first.md`: click is the project CLI framework (argparse
BLOCKED). Per `rules/observability.md` MUST Rule 1+2: every invocation logs via
the framework logger bound to the root group's `cli_session_id`. Per
`rules/agent-reasoning.md`: the per-state extraction is LLM-first inside the BC
runtime — the CLI collects the user's free-form answers and pumps them through;
it never keyword-routes the content.

Write-once idempotency: re-running `init` on an initialized vault surfaces the
typed `VaultAlreadyInitializedError` as a clean exit (code 30) with an explicit
plain-language message — never a silent overwrite of the durable genesis.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib

import click

from envoy.boundary_conversation.errors import VaultAlreadyInitializedError

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_PRINCIPAL = 20
EXIT_ALREADY_INITIALIZED = 30
EXIT_INIT_FAILED = 31

_DEFAULT_VAULT = "~/.envoy/trust_vault.db"
_DEFAULT_TRUST_ANCHOR_DIR = "~/.envoy/trust-anchor"

# The Boundary Conversation states the user answers (S1..S9). The CLI prompts
# for each; the BC runtime's LLM extracts the structured envelope dimensions
# from the free-form replies (LLM-first per rules/agent-reasoning.md).
_RITUAL_PROMPTS: tuple[tuple[str, str], ...] = (
    ("S1_money", "Spending boundaries (e.g. 'cap at $250 a month, no exceptions')"),
    ("S2_people", "People Envoy must never contact (e.g. 'never email my ex')"),
    ("S3_topics", "Topics to avoid (e.g. 'no medical advice, no political endorsements')"),
    ("S4_hours", "Operating hours (e.g. 'weekdays 9am-5pm UTC only')"),
    ("S5_first_task", "First task you want Envoy to do (e.g. 'summarize my newsletters')"),
    ("S6_template_offer", "Use a starter template, or build from scratch?"),
    ("S7_visible_secret", "Your visible secret — icon, color, and phrase (anti-spoofing)"),
    ("S8_shamir", "Backup ritual (e.g. 'use the default 3-of-5 backup')"),
    ("S9_review_sign", "Review and sign your boundaries (e.g. 'yes, I confirm and sign')"),
)


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


def _resolve_trust_anchor_dir(trust_anchor_dir: str | None) -> pathlib.Path:
    raw = trust_anchor_dir or os.environ.get("ENVOY_TRUST_ANCHOR_DIR") or _DEFAULT_TRUST_ANCHOR_DIR
    return pathlib.Path(raw).expanduser()


@click.group()
def init() -> None:
    """First-time setup — author your boundaries and back up your keys."""


@init.command("run")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
@click.option(
    "--trust-anchor-dir",
    default=None,
    help=(
        "Where trust-anchor.json is emitted (or ENVOY_TRUST_ANCHOR_DIR). Store "
        "this alongside your Shamir paper shards."
    ),
)
def init_run(
    principal: str | None,
    vault: str | None,
    trust_anchor_dir: str | None,
) -> None:
    """Run the Boundary Conversation setup and back up your keys.

    Prompts for a vault passphrase, then walks the boundary-setup questions.
    On success: a durable session genesis is written (so future sessions
    re-anchor to this setup) and trust-anchor.json is emitted for you to store
    with your backup cards.

    Re-running on an already-set-up vault exits cleanly (code 30) without
    re-running setup or overwriting your genesis.
    """
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)
    anchor_dir = _resolve_trust_anchor_dir(trust_anchor_dir)

    passphrase = click.prompt(
        "Choose a vault passphrase (you'll need it to unlock Envoy)",
        hide_input=True,
        confirmation_prompt=True,
    )

    replies: dict[str, str] = {}
    click.echo("\nLet's set up your boundaries.\n")
    for state, prompt_text in _RITUAL_PROMPTS:
        replies[state] = click.prompt(f"  {prompt_text}", type=str)

    async def _run() -> int:
        from envoy.boundary_conversation.init_bootstrap import build_init_runtime

        bootstrap = await build_init_runtime(
            vault_path=vault_path,
            principal_id=pid,
            passphrase=passphrase,
            trust_anchor_dir=anchor_dir,
        )
        try:
            result = await bootstrap.init_runtime.run_first_time_bootstrap(
                principal_id=pid, replies=replies
            )
            click.echo("\nSetup complete.")
            click.echo(f"  Boundaries signed (envelope {result.envelope_id}).")
            click.echo(f"  Durable session genesis written ({result.genesis_store_key}).")
            click.echo(f"  Trust anchor saved to: {result.trust_anchor_path}")
            click.echo(
                "\nStore your trust-anchor.json in the SAME place as your "
                "backup cards — it lets you verify your records later.\n"
            )
            return EXIT_OK
        finally:
            await bootstrap.session_router.close()
            await bootstrap.durable_ledger.aclose()
            await bootstrap.trust_store.close()
            if bootstrap.vault.is_unlocked:
                await bootstrap.vault.lock()

    logger.info("envoy.init.run.start", extra={"principal_id_prefix": pid[:8]})
    try:
        exit_code = asyncio.run(_run())
    except VaultAlreadyInitializedError as exc:
        # Clean, typed already-initialized path — NEVER a silent overwrite.
        click.echo(f"\n{exc}\n", err=True)
        raise SystemExit(EXIT_ALREADY_INITIALIZED) from exc
    raise SystemExit(exit_code)


__all__ = ["init"]
