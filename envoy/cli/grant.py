# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""`envoy grant` click subcommand group — WS-6 S4g-1.

The human-answering half of the cross-process Grant Moment flow. When Envoy
hits a first-time / out-of-envelope action it issues a Grant Moment (M0/M1),
writes a ``state=pending`` row to the durable S4s sub-store, and polls (S4r) for
the answer. ``envoy grant`` is the SEPARATE CLI invocation the user runs to see
those pending requests and answer them:

    envoy grant list                 → show requests waiting for your decision
    envoy grant approve <request-id> → approve (the waiting Envoy resumes)
    envoy grant deny <request-id>    → decline (with an optional --reason)

The answer is written into the sub-store as a session-key-signed resolution row
(``SessionRouter.resolve_pending_grant``); the requesting process's poll observes
the bumped monotonic version, verifies the detached signature fail-closed, and
resumes. This CLI NEVER produces the delegation-key-signed ``GrantMomentResult``
— that is the requesting process's M3 job. The answering CLI only records WHICH
decision shape the user chose (Approve / Decline); the requester reconstructs the
exact shape and finalizes the signed Ledger entry.

Cross-process replay/double-resolve defense is the store's compare-and-set: the
``resolve_pending_grant`` UPDATE is gated on ``state='pending'`` (session.py),
so a second ``approve`` on an already-answered (or timed-out) request is REFUSED
loudly (exit 40), never a silent re-flip.

Per `rules/framework-first.md`: click is the project CLI framework (argparse
BLOCKED). Per `rules/observability.md` MUST Rule 1+2: every invocation logs via
the framework logger bound to the root group's `cli_session_id`. Keyring backend
selection mirrors `envoy init` (journal/0017 Pattern 1): unset → the real OS
keychain (secure default); ``ENVOY_KEYRING=memory`` → an in-process ephemeral
backend for headless / CI / red-team-walk use; any other value exits 32.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
from typing import Any

import click

from envoy.grant_moment.resolution import (
    ApproveResolution,
    DeclineResolution,
    ResolutionShape,
    resolution_to_json,
)
from envoy.ledger.keystore import (
    LedgerKeyringSelectorError,
    resolve_keyring_backend,
)
from envoy.runtime.session import PendingGrantRow, SessionRouter

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_PRINCIPAL = 20
EXIT_KEYRING_SELECTOR = 32
EXIT_GRANT_NOT_PENDING = 40

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


def _resolve_keyring_backend_or_exit(log_extra: dict[str, Any]) -> Any:
    """Resolve the ENVOY_KEYRING backend, exiting cleanly (32) on a bad selector.

    Unset → the real OS keychain (secure default); ``memory`` → an in-process
    ephemeral backend; any other value → a clean exit 32 (never a traceback).
    Mirrors `envoy init` (journal/0017 Pattern 1) so every keychain-touching CLI
    verb threads the SAME headless override seam.
    """
    try:
        return resolve_keyring_backend()
    except LedgerKeyringSelectorError as exc:
        logger.warning("envoy.grant.bad_keyring_selector", extra=log_extra)
        click.echo(f"\n{exc}\n", err=True)
        raise SystemExit(EXIT_KEYRING_SELECTOR) from exc


def _request_field(row: PendingGrantRow, field: str, default: str = "") -> str:
    """Read one field out of a pending row's canonical-JSON GrantMomentRequest.

    The store holds ``request_json`` verbatim (``asdict(GrantMomentRequest)``);
    this CLI is the wire-format reader. Returns ``default`` if the blob is
    malformed or the field is absent — a corrupt row must not crash the listing.
    """
    try:
        data = json.loads(row.request_json)
    except (ValueError, TypeError):
        return default
    if not isinstance(data, dict):
        return default
    value = data.get(field, default)
    return str(value) if value is not None else default


def _cli_session_id() -> str:
    ctx = click.get_current_context(silent=True)
    obj = (ctx.obj if ctx is not None else None) or {}
    return obj.get("cli_session_id", "") if isinstance(obj, dict) else ""


@click.group()
def grant() -> None:
    """Review and answer requests Envoy is waiting on.

    When Envoy needs your go-ahead for something new or outside your set
    boundaries, it pauses and records the request. List what's waiting with
    `envoy grant list`, then `approve` or `deny` each one — Envoy resumes the
    moment you answer.
    """


@grant.command("list")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
def grant_list(principal: str | None, vault: str | None) -> None:
    """Show the requests waiting for your decision.

    Lists every pending Grant Moment for your principal, newest first, with the
    one-line `approve` / `deny` command to answer each. Exits 0 with a friendly
    note when nothing is waiting.
    """
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)
    log_extra = {"principal_id_prefix": pid[:8], "cli_session_id": _cli_session_id()}
    keyring_backend = _resolve_keyring_backend_or_exit(log_extra)

    async def _run() -> list[PendingGrantRow]:
        router = SessionRouter(
            vault_path=vault_path, principal_id=pid, keyring_backend=keyring_backend
        )
        await router.open()
        try:
            return await router.list_pending_grants()
        finally:
            await router.close()

    logger.info("envoy.grant.list.start", extra=log_extra)
    rows = asyncio.run(_run())
    if not rows:
        click.echo("\nNothing is waiting for your decision right now.\n")
        logger.info("envoy.grant.list.ok", extra={**log_extra, "pending_count": 0})
        raise SystemExit(EXIT_OK)

    click.echo(f"\n{len(rows)} request(s) waiting for your decision:\n")
    for row in rows:
        tool = _request_field(row, "tool_name", "(unknown action)")
        why = _request_field(row, "why_asking", "")
        novelty = _request_field(row, "novelty_class", "")
        issued = _request_field(row, "issued_at", row.created_at)
        click.echo(f"  [{row.request_id}]  {tool}")
        if why:
            click.echo(f"      Why: {why}")
        if novelty:
            click.echo(f"      Kind: {novelty}")
        click.echo(f"      Asked: {issued}")
        click.echo(f"      Approve:  envoy grant approve {row.request_id}")
        click.echo(f"      Deny:     envoy grant deny {row.request_id}\n")
    logger.info("envoy.grant.list.ok", extra={**log_extra, "pending_count": len(rows)})
    raise SystemExit(EXIT_OK)


async def _answer_pending_grant(
    *,
    router: SessionRouter,
    request_id: str,
    build_resolution: Any,
) -> tuple[bool, str]:
    """Record a decision onto a pending row. Returns (ok, message).

    Reads the row first (to recover the requesting principal's genesis id for the
    resolution AND to give a precise not-pending message), then writes the
    session-key-signed resolution via ``resolve_pending_grant``. The store's
    ``state='pending'`` compare-and-set is the cross-process double-resolve guard:
    a row that is absent or already terminal returns ``ok=False`` with a precise
    reason rather than re-flipping a settled decision.
    """
    row = await router.get_pending_grant(request_id)
    if row is None:
        return False, (
            f"No request with id {request_id!r} is waiting for your decision. "
            "Run `envoy grant list` to see the current ones."
        )
    if row.state != "pending":
        return False, (
            f"Request {request_id!r} is already {row.state} — there's nothing to "
            "answer. (A request can only be decided once.)"
        )
    # The answer is decided BY the same principal who owns the request
    # (cross-principal dual-sign is Phase-03); recover its genesis id from the
    # stored request so the resolution shape is correctly attributed.
    decided_by = _request_field(row, "principal_genesis_id", router.principal_id)
    resolution: ResolutionShape = build_resolution(decided_by)
    try:
        await router.resolve_pending_grant(
            request_id=request_id,
            resolution_json=resolution_to_json(resolution),
            state="resolved",
        )
    except KeyError:
        # Raced: another answerer (or a timeout) flipped the row terminal between
        # our read and our write. The store CAS refused the double-resolve — a
        # settled decision is immutable. Surface it, never silently re-flip.
        return False, (
            f"Request {request_id!r} was just answered (or expired) by another "
            "step before this one landed. Nothing changed."
        )
    return True, f"Recorded your decision on {request_id!r}. Envoy will resume."


def _run_answer(
    *,
    pid: str,
    vault_path: pathlib.Path,
    keyring_backend: Any,
    request_id: str,
    build_resolution: Any,
) -> tuple[bool, str]:
    async def _run() -> tuple[bool, str]:
        router = SessionRouter(
            vault_path=vault_path, principal_id=pid, keyring_backend=keyring_backend
        )
        await router.open()
        try:
            return await _answer_pending_grant(
                router=router, request_id=request_id, build_resolution=build_resolution
            )
        finally:
            await router.close()

    return asyncio.run(_run())


@grant.command("approve")
@click.argument("request_id")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
def grant_approve(request_id: str, principal: str | None, vault: str | None) -> None:
    """Approve a pending request so Envoy can proceed.

    Records your approval; the waiting Envoy picks it up and continues. If the
    request was already answered or has expired, this exits cleanly (code 40)
    without changing the settled decision.
    """
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)
    log_extra = {
        "principal_id_prefix": pid[:8],
        "cli_session_id": _cli_session_id(),
        "request_id": request_id,
    }
    keyring_backend = _resolve_keyring_backend_or_exit(log_extra)

    logger.info("envoy.grant.approve.start", extra=log_extra)
    ok, message = _run_answer(
        pid=pid,
        vault_path=vault_path,
        keyring_backend=keyring_backend,
        request_id=request_id,
        build_resolution=lambda decided_by: ApproveResolution(
            decided_by_principal_genesis_id=decided_by
        ),
    )
    click.echo(f"\n{message}\n", err=not ok)
    if not ok:
        logger.warning("envoy.grant.approve.not_pending", extra=log_extra)
        raise SystemExit(EXIT_GRANT_NOT_PENDING)
    logger.info("envoy.grant.approve.ok", extra=log_extra)
    raise SystemExit(EXIT_OK)


@grant.command("deny")
@click.argument("request_id")
@click.option("--reason", default="", help="Optional plain-language reason for the record.")
@click.option("--principal", default=None, help="Principal id (or ENVOY_PRINCIPAL_ID).")
@click.option("--vault", default=None, help="Trust vault path (or ENVOY_VAULT_PATH).")
def grant_deny(
    request_id: str, reason: str, principal: str | None, vault: str | None
) -> None:
    """Decline a pending request so Envoy stands down.

    Records your decline (with an optional reason for your records); the waiting
    Envoy picks it up and does not proceed. If the request was already answered
    or has expired, this exits cleanly (code 40) without changing it.
    """
    pid = _resolve_principal(principal)
    vault_path = _resolve_vault(vault)
    log_extra = {
        "principal_id_prefix": pid[:8],
        "cli_session_id": _cli_session_id(),
        "request_id": request_id,
    }
    keyring_backend = _resolve_keyring_backend_or_exit(log_extra)

    logger.info("envoy.grant.deny.start", extra=log_extra)
    ok, message = _run_answer(
        pid=pid,
        vault_path=vault_path,
        keyring_backend=keyring_backend,
        request_id=request_id,
        build_resolution=lambda decided_by: DeclineResolution(
            decided_by_principal_genesis_id=decided_by, reason=reason
        ),
    )
    click.echo(f"\n{message}\n", err=not ok)
    if not ok:
        logger.warning("envoy.grant.deny.not_pending", extra=log_extra)
        raise SystemExit(EXIT_GRANT_NOT_PENDING)
    logger.info("envoy.grant.deny.ok", extra=log_extra)
    raise SystemExit(EXIT_OK)


__all__ = ["grant"]
