# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.ledger.keystore — durable ledger signing key via the OS keychain.

The Envoy Ledger signs every entry + the head commitment with an Ed25519 key.
A process-local ``InMemoryKeyManager`` loses that key on process exit, so a
fresh process re-mints a *random* key and the independent verifier's
cross-process signature check (EC-4 invariant 5/7) fails. This module persists
the signing keypair in the OS keychain (macOS Keychain / Linux Secret Service /
Windows Credential Manager via ``keyring``) — device-bound, OS/Secure-Enclave
protected, and readable by the principal's own background processes *without* a
typed passphrase. It is NOT a plaintext file.

Why the keychain (and not a vault region): the autonomous Daily Digest fires on
an in-process cron schedule (EC-3) and signs ledger entries with no human at the
keyboard. A keychain-stored device key is headless-native — the daemon reads it
with no passphrase and no vault unlock — and reuses the exact pattern the
Connection Vault (``envoy.connection_vault``) already uses for connection/model
secrets. The ledger is per-device; the independent verifier trusts the *public*
key (its trust anchor), so a per-device signing key in the keychain is the
correct root-of-protection for this surface.

Crypto stays in kailash: generation + ``sign``/``verify``/``get_public_key`` are
``InMemoryKeyManager``'s. This module only *persists* the key material and
re-loads it into a fresh manager on the next process.

Failure taxonomy (all fail-LOUD — a missing/corrupt key MUST never silently
degrade to an ephemeral key, which would make cross-process signatures
unverifiable without a trace):

- ``LedgerKeyUnavailableError`` — the OS keychain itself is down / locked.
  Transport-level and *retryable* after the device is unlocked.
- ``LedgerKeyCorruptError`` — a record is present but unparseable / not an
  object / missing a key half. A durable data problem; NOT retryable.
  Regenerating is REFUSED (a new key would orphan every prior-signed entry).
- ``LedgerKeySchemaVersionError`` — a record is present and parses, but carries
  an unrecognized ``schema`` version (e.g. written by a newer Envoy). The
  operator action is "upgrade Envoy", distinct from "re-pair".
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

import keyring
import keyring.errors
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.connection_vault.schema import validate_principal_genesis_id

logger = logging.getLogger(__name__)

# Headless / CI / red-team-walk backend selector. UNSET (the default) keeps the
# real OS keychain (macOS Keychain / Linux Secret Service / Windows Credential
# Manager). The ONLY recognized override value is "memory" — an in-PROCESS dict
# backend that touches NO persistent store. The override is a closed allowlist:
# unset → OS keychain; "memory" → in-process dict; ANY other value → loud refusal
# (fail-closed — a typo'd selector MUST NOT silently fall back to a different
# backend, and an arbitrary backend class path is NOT accepted, so the override
# cannot be a backend-downgrade / injection vector).
ENVOY_KEYRING_ENV = "ENVOY_KEYRING"
_KEYRING_MEMORY = "memory"

# Distinct keyring service namespace so the ledger signing key never collides
# with the Connection Vault's credential entries (`envoy.connection-vault`).
KEYRING_SERVICE_NAMESPACE = "envoy.ledger-signing-key"
_BLOB_SCHEMA = "envoy-ledger-key/1"

# `signing_key_id` is the right half of the keyring account `genesis_id:key_id`.
# A `:` in it would shift the per-principal namespace boundary, so it is
# constrained to a `:`-free charset (the production value is the fixed constant
# `envoy-digest-signing-key`; this enforces the "fixed constant" assumption
# structurally rather than by comment).
_SIGNING_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


class LedgerKeystoreError(Exception):
    """Base for ledger signing-key persistence failures."""


class LedgerKeyUnavailableError(LedgerKeystoreError):
    """The OS keychain is unavailable/locked (transport-level; retryable)."""


class LedgerKeyCorruptError(LedgerKeystoreError):
    """A keychain record is present but unparseable / malformed (NOT retryable)."""


class LedgerKeySchemaVersionError(LedgerKeystoreError):
    """A keychain record carries an unrecognized schema version (upgrade Envoy)."""


class LedgerKeyringSelectorError(LedgerKeystoreError):
    """The ``ENVOY_KEYRING`` env value is not a recognized backend selector.

    Fail-closed: an unrecognized selector raises rather than silently picking the
    OS-keychain default (a typo'd selector must be loud, not a security surprise).
    """


class InMemoryKeyringBackend:
    """In-PROCESS dict keyring backend — headless / CI / red-team-walk ONLY.

    Implements the subset of the ``keyring`` backend interface envoy's keystore,
    session-signing-key store, and connection vault use (``get_password`` /
    ``set_password`` / ``delete_password``). It persists NOTHING to disk and is
    process-local — keys vanish on exit. NEVER the production default: it is
    reachable only via an explicit ``ENVOY_KEYRING=memory`` opt-in, which logs a
    loud warning (see :func:`resolve_keyring_backend`). Mirrors the test backend
    at ``tests/tier3/test_init_bootstrap_full_path.py`` so a walked CLI behaves
    identically to the dependency-injected test path.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._store:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._store[key]


def resolve_keyring_backend(env: dict[str, str] | None = None) -> Any | None:
    """Resolve the keyring backend from ``ENVOY_KEYRING`` (closed allowlist).

    Returns ``None`` (→ the real OS keychain, the secure default) when the env
    var is unset/empty; an :class:`InMemoryKeyringBackend` when it is exactly
    ``"memory"`` (with a loud warning, since an in-process ephemeral key store is
    test/headless-only); and raises :class:`LedgerKeyringSelectorError` for any
    other value. The strict allowlist is the fail-closed guarantee: the override
    can ONLY ever select the known-safe in-process backend, never an attacker-
    supplied backend class or a silent downgrade.
    """
    environ = os.environ if env is None else env
    selector = (environ.get(ENVOY_KEYRING_ENV) or "").strip()
    if not selector:
        return None
    if selector == _KEYRING_MEMORY:
        logger.warning(
            "envoy.keyring.memory_backend_selected",
            extra={"reason": f"{ENVOY_KEYRING_ENV}=memory — in-process ephemeral "
                   "key store; keys are NOT persisted to the OS keychain. "
                   "Headless/CI/walk use only, never production."},
        )
        return InMemoryKeyringBackend()
    raise LedgerKeyringSelectorError(
        f"{ENVOY_KEYRING_ENV}={selector!r} is not a recognized keyring selector; "
        f"unset it for the OS keychain (default) or set {ENVOY_KEYRING_ENV}=memory "
        f"for the in-process headless backend"
    )


def principal_genesis_id(principal_id: str) -> str:
    """``sha256(principal_id)`` — the keychain account, matching the Connection
    Vault + posture-store keying convention (``envoy/trust/store.py``)."""
    return hashlib.sha256(principal_id.encode("utf-8")).hexdigest()


def _account(genesis_id: str, signing_key_id: str) -> str:
    # genesis_id is validated sha256-hex; signing_key_id is `:`-free-validated.
    # The colon mirrors the Connection Vault keyring key shape
    # (`__index__:{genesis_id}`).
    return f"{genesis_id}:{signing_key_id}"


def _get(account: str, backend: Any) -> str | None:
    try:
        if backend is not None:
            return backend.get_password(KEYRING_SERVICE_NAMESPACE, account)  # type: ignore[no-any-return]
        return keyring.get_password(KEYRING_SERVICE_NAMESPACE, account)
    except keyring.errors.KeyringError as exc:
        raise LedgerKeyUnavailableError(f"OS keychain unavailable (get): {exc}") from exc


def _set(account: str, blob: str, backend: Any) -> None:
    try:
        if backend is not None:
            backend.set_password(KEYRING_SERVICE_NAMESPACE, account, blob)
        else:
            keyring.set_password(KEYRING_SERVICE_NAMESPACE, account, blob)
    except keyring.errors.KeyringError as exc:
        raise LedgerKeyUnavailableError(f"OS keychain unavailable (set): {exc}") from exc


def _decode_keypair(blob: str, hint: str) -> tuple[str, str]:
    """Parse a stored keychain blob into ``(private_key, public_key)``.

    Fail-loud on every malformed shape (see the module-level taxonomy). The
    ``schema`` version is checked BEFORE the key halves so a forward/legacy
    record raises the schema-version error rather than being silently loaded
    under a contract this build does not understand.
    """
    try:
        record = json.loads(blob)
    except (ValueError, TypeError) as exc:
        raise LedgerKeyCorruptError(
            f"ledger signing-key record for {hint}… is unparseable: {exc}"
        ) from exc
    if not isinstance(record, dict):
        raise LedgerKeyCorruptError(f"ledger signing-key record for {hint}… is not a JSON object")
    if record.get("schema") != _BLOB_SCHEMA:
        raise LedgerKeySchemaVersionError(
            f"ledger signing-key record for {hint}… has schema "
            f"{record.get('schema')!r}, expected {_BLOB_SCHEMA!r} — upgrade Envoy"
        )
    try:
        return record["private_key"], record["public_key"]
    except KeyError as exc:
        raise LedgerKeyCorruptError(
            f"ledger signing-key record for {hint}… is missing a key half: {exc}"
        ) from exc


async def load_or_create_ledger_key_manager(
    *,
    principal_id: str,
    signing_key_id: str,
    keyring_backend: Any = None,
) -> InMemoryKeyManager:
    """Return an ``InMemoryKeyManager`` whose ``signing_key_id`` is durably
    backed by the OS keychain — the SAME key across process restarts.

    The first call for a principal generates the Ed25519 keypair and stores
    both halves in the keychain; subsequent calls (including a fresh process)
    reload them. The returned manager is otherwise a normal
    ``InMemoryKeyManager`` (full crypto surface), so every existing consumer
    (the ledger facade, ``verify_chain``, ``export``) works unchanged.

    Raises (all fail-loud; never a silent ephemeral-key fallback):
    ``LedgerKeyUnavailableError`` (keychain down), ``LedgerKeyCorruptError``
    (malformed record), ``LedgerKeySchemaVersionError`` (unknown record
    version). ``keyring_backend`` is dependency-injectable for tests (matching
    ``envoy.connection_vault.ConnectionVault``); production uses the OS-selected
    backend.
    """
    if not _SIGNING_KEY_ID_RE.match(signing_key_id):
        # `:`-free + control-char-free so it cannot shift the keyring account
        # namespace. Do NOT echo the raw value (log/exception-poisoning hygiene).
        raise LedgerKeystoreError(
            f"signing_key_id must match {_SIGNING_KEY_ID_RE.pattern} "
            "(notably no ':', which separates the keyring account namespace)"
        )
    genesis_id = principal_genesis_id(principal_id)
    validate_principal_genesis_id(genesis_id)
    account = _account(genesis_id, signing_key_id)
    hint = genesis_id[:8]

    blob = _get(account, keyring_backend)
    mgr = InMemoryKeyManager()  # type: ignore[no-untyped-call]  # kailash ctor untyped

    if blob is None:
        # First use for this principal: generate the keypair and persist BOTH
        # halves (register_key restores only the private half — see below).
        private_key, public_key = await mgr.generate_keypair(signing_key_id)
        _set(
            account,
            json.dumps(
                {"schema": _BLOB_SCHEMA, "private_key": private_key, "public_key": public_key},
                sort_keys=True,
            ),
            keyring_backend,
        )
        logger.info("ledger.keystore.created", extra={"principal_hint": hint})
        return mgr

    private_key, public_key = _decode_keypair(blob, hint)
    mgr.register_key(signing_key_id, private_key)
    # kailash `register_key` restores only the PRIVATE half; the facade caches
    # `get_public_key(signing_key_id)` at construction and RAISES if it is None,
    # so the public half MUST be restored. kailash exposes no public API for
    # this, so we write the internal `_public_keys` dict directly. This is a
    # LOAD-BEARING restore — unlike `trust/store.py`'s defensive best-effort
    # `getattr` on `_keys` (a zeroize that may safely no-op), a bare write here
    # would silently create a NEW instance attribute on a kailash rename and
    # surface as an opaque None-pubkey failure several call hops away. So we
    # guard it and fail LOUD at this line with an actionable message.
    pubkeys = getattr(mgr, "_public_keys", None)
    if not isinstance(pubkeys, dict):
        raise LedgerKeystoreError(
            "kailash InMemoryKeyManager._public_keys internal dict not found — "
            "envoy.ledger.keystore must be updated to restore the public key half"
        )
    pubkeys[signing_key_id] = public_key
    logger.info("ledger.keystore.loaded", extra={"principal_hint": hint})
    return mgr


__all__ = [
    "KEYRING_SERVICE_NAMESPACE",
    "LedgerKeyCorruptError",
    "LedgerKeySchemaVersionError",
    "LedgerKeyUnavailableError",
    "LedgerKeystoreError",
    "load_or_create_ledger_key_manager",
    "principal_genesis_id",
]
