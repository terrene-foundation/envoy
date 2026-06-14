# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""`envoy chat` — the resident chat-session loop (WS-6 S6c; 10th of 10 commands).

`envoy chat` starts a resident session that reads messages from stdin (one per
line) and replies to stdout, until end-of-input (Ctrl-D) disconnects the channel.
On disconnect the session boundary fires — the S5b `session_boundary_crossed`
signal that applies the T-013 reset — so the next session's first identical tool
call is first-time-action again.

This Phase-02 surface is the CONVERSATION loop: every message is acknowledged.
The first-time-action gate + Grant Moment drive (proven end-to-end at the
`ChatResidentLoop` layer in `tests/tier2/test_chat_resident_loop.py`) activates
when an agent layer injects an action `resolver` + the grant runtime; the bare CLI
wires neither, so it never fabricates a Grant Moment from a plain text line
(`rules/zero-tolerance.md` Rule 2 — no fake consequence/novelty data). The loop is
a TRANSPORT over the durable store; a crash mid-session loses nothing.

Keyring backend per the shared headless seam (journal/0017 Pattern 1): unset →
the real OS keychain (secure default); ``ENVOY_KEYRING=memory`` → an in-process
ephemeral backend; any other value → a clean exit 32.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, TextIO

import click

from envoy.channels.cli import CLIChannelAdapter, CLIChannelConfig
from envoy.channels.envelope import InboundMessage, MessagePayload
from envoy.ledger.bootstrap import (
    LEDGER_ALGORITHM_IDENTIFIER,
    LEDGER_DEVICE_ID,
    LEDGER_SIGNING_KEY_ID,
    open_durable_ledger,
)
from envoy.ledger.keystore import (
    LedgerKeyringSelectorError,
    load_or_create_ledger_key_manager,
    resolve_keyring_backend,
)
from envoy.runtime import ChatResidentLoop, SessionBoundarySignal, SessionRouter

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_NO_PRINCIPAL = 20
EXIT_KEYRING_SELECTOR = 32

_DEFAULT_VAULT = "~/.envoy/trust_vault.db"
_CLI_CHANNEL_ID = "cli"


def _resolve_principal(principal: str | None) -> str:
    pid = principal or os.environ.get("ENVOY_PRINCIPAL_ID")
    if not pid:
        raise click.ClickException("no principal — pass --principal or set ENVOY_PRINCIPAL_ID")
    return pid


def _resolve_vault(vault: str | None) -> pathlib.Path:
    raw = vault or os.environ.get("ENVOY_VAULT_PATH") or _DEFAULT_VAULT
    path = pathlib.Path(raw).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_session_id(session_id: str | None) -> str:
    return session_id or os.environ.get("ENVOY_SESSION_ID") or uuid.uuid4().hex


def _resolve_keyring_backend_or_exit() -> Any:
    try:
        return resolve_keyring_backend()
    except LedgerKeyringSelectorError as exc:
        click.echo(f"\n{exc}\n", err=True)
        raise SystemExit(EXIT_KEYRING_SELECTOR) from exc


def _conversation_resolver(_message: InboundMessage) -> None:
    """Phase-02 CLI resolver: every message is plain conversation (acked).

    Returns ``None`` for every message so the loop acks rather than driving a
    Grant Moment. An agent layer supplies an action-producing resolver (+ the
    grant runtime) to activate the gate/grant path — the CLI does NOT synthesize
    consequence/novelty signals a user never provided.
    """
    return None


class _StdinChatAdapter(CLIChannelAdapter):
    """CLI adapter whose inbound stream is real stdin, terminating on EOF.

    Overrides only ``receive_message`` to yield one `InboundMessage` per stdin
    line (blocking ``readline`` off the event loop), ending the iterator on EOF
    (Ctrl-D) — which the resident loop reacts to by firing the disconnect
    boundary. Every other surface (``send_message`` to stdout, lifecycle) is the
    real `CLIChannelAdapter`.
    """

    def __init__(
        self, *, principal_id: str, session_id: str, input_stream: TextIO, output_stream: TextIO
    ) -> None:
        super().__init__(
            CLIChannelConfig(primary_channel_id=_CLI_CHANNEL_ID, output_stream=output_stream)
        )
        self._principal_id = principal_id
        self._session_id = session_id
        self._input = input_stream

    async def receive_message(self) -> AsyncIterator[InboundMessage]:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, self._input.readline)
            if not line:  # EOF → channel disconnect
                return
            body = line.rstrip("\r\n")
            if not body:
                continue
            yield InboundMessage(
                channel_id=_CLI_CHANNEL_ID,
                session_id=self._session_id,
                principal_genesis_id=self._principal_id,
                direction="inbound",
                content_trust_level="user",
                payload=MessagePayload(kind="text", body=body),
                visible_secret_rendered=None,
                timestamp=datetime.now(timezone.utc),
            )


@click.command("chat")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
@click.option(
    "--session-id", default=None, help="Session id (or ENVOY_SESSION_ID; fresh if unset)."
)
def chat(principal: str | None, vault: str | None, session_id: str | None) -> None:
    """Start a resident chat session (reads stdin, replies to stdout).

    Each message is acknowledged; on Ctrl-D the session boundary fires (the
    T-013 reset). The durable store is the authority — a crash mid-session loses
    no pending grant.
    """
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)
    sid = _resolve_session_id(session_id)
    backend = _resolve_keyring_backend_or_exit()
    out = click.get_text_stream("stdout")
    inp = click.get_text_stream("stdin")

    async def _run() -> int:
        key_manager = await load_or_create_ledger_key_manager(
            principal_id=pid, signing_key_id=LEDGER_SIGNING_KEY_ID
        )
        durable = await open_durable_ledger(
            vault_path=vault_path,
            key_manager=key_manager,
            signing_key_id=LEDGER_SIGNING_KEY_ID,
            device_id=LEDGER_DEVICE_ID,
            algorithm_identifier=LEDGER_ALGORITHM_IDENTIFIER,
        )
        router = SessionRouter(vault_path=vault_path, principal_id=pid, keyring_backend=backend)
        await router.open()
        try:
            boundary = SessionBoundarySignal(ledger=durable.ledger, router=router)
            adapter = _StdinChatAdapter(
                principal_id=pid, session_id=sid, input_stream=inp, output_stream=out
            )
            loop = ChatResidentLoop(
                adapter=adapter,
                boundary_signal=boundary,
                session_id=sid,
                resolver=_conversation_resolver,
            )
            results = await loop.run()
            logger.info(
                "envoy.chat.session_complete",
                extra={"session_id_prefix": sid[:8], "turns": len(results)},
            )
            return EXIT_OK
        finally:
            await router.close()
            await durable.aclose()

    logger.info(
        "envoy.chat.start", extra={"principal_id_prefix": pid[:8], "session_id_prefix": sid[:8]}
    )
    raise SystemExit(asyncio.run(_run()))


__all__ = ["chat"]
