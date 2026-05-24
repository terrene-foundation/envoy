"""ConnectionVault — OS-keychain-backed credential adapter.

Per `specs/connection-vault.md` + shard 14 § 3.1
(`workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md`).

Phase 01 minimum: ``get`` / ``set`` / ``delete`` / ``list_by_principal`` /
``is_available``. Phase 02 adds rotation execution + OAuth refresh dance.
Phase 03 adds per-principal isolation gating via Grant Moment.

Fail-closed defaults:

* Vault constructed without ``principal_genesis_id`` raises
  :class:`PrincipalRequiredError` at ``set`` / ``get`` / ``delete``.
* Vault constructed without ``active_envelope`` raises
  :class:`EnvelopeScopeMismatchError` at every ``get`` (until the caller
  swaps in an envelope via ``with_active_envelope``).
* All scope-membership misses translate to
  :class:`EnvelopeScopeMismatchError` (no silent skips per
  ``rules/zero-tolerance.md`` Rule 3).
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional, Union
from uuid import UUID, uuid4

import keyring
import keyring.errors

from envoy.connection_vault.errors import (
    CrossPrincipalAccessRefusedError,
    EntryExpiredError,
    EntryNotFoundError,
    EnvelopeScopeMismatchError,
    KeychainUnavailableError,
    PrincipalRequiredError,
    UsageCounterOverflowError,
)
from envoy.connection_vault.schema import (
    USAGE_COUNTER_MAX,
    CredentialEntry,
    CredentialType,
    RotationPolicy,
    utcnow,
    validate_service_identifier,
)
from envoy.envelope import (
    EnvelopeConfig,
    EnvelopeConfigInput,
    EnvelopeScopeRef,
    envelope_contains_scope,
)

KEYRING_SERVICE_NAMESPACE = "envoy.connection-vault"
"""Single keyring `service` namespace per shard 14 § 3.1 step 1 — the
per-platform OS keychain entries are keyed by this string + the entry_id."""

_RECORD_SCHEMA_VERSION = 1

logger = logging.getLogger("envoy.connection_vault")


# Type alias for "any envelope shape that has operational + communication
# dimensions" — Phase 01 the two `Envelope*` dataclasses are the canonical
# carriers per shard 14 § 5.5. Phase 02 may add `SessionEnvelope`.
ActiveEnvelope = Union[EnvelopeConfig, EnvelopeConfigInput]


def _serialize_record(entry: CredentialEntry, secret: str) -> str:
    """Canonical JSON payload stored in the OS keychain `password` slot.

    Per shard 14 § 3.1 step 1: the 11-field record + the secret bytes are
    serialized together into the single 3-tuple slot ``keyring`` exposes.
    """
    payload: dict[str, Any] = {
        "schema_version": _RECORD_SCHEMA_VERSION,
        "entry_id": str(entry.entry_id),
        "principal_genesis_id": entry.principal_genesis_id,
        "credential_type": entry.credential_type.value,
        "service_identifier": entry.service_identifier,
        "entry_envelope_scope": {
            "service_identifier": entry.entry_envelope_scope.service_identifier,
            "channel": entry.entry_envelope_scope.channel,
        },
        "created_at": entry.created_at.isoformat(),
        "last_used_at": entry.last_used_at.isoformat(),
        "expires_at": entry.expires_at.isoformat() if entry.expires_at is not None else None,
        "usage_counter": entry.usage_counter,
        "rotation_policy": entry.rotation_policy.value,
        # The secret lives inline in the keychain ciphertext slot. The OS
        # keychain provides the encryption-at-rest contract.
        "secret": secret,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _deserialize_record(blob: str) -> tuple[CredentialEntry, str]:
    """Inverse of :func:`_serialize_record`."""
    payload = json.loads(blob)
    if payload.get("schema_version") != _RECORD_SCHEMA_VERSION:
        raise EntryNotFoundError(
            f"unsupported connection-vault record schema_version={payload.get('schema_version')}"
        )
    scope_payload = payload["entry_envelope_scope"]
    scope = EnvelopeScopeRef(
        service_identifier=scope_payload["service_identifier"],
        channel=scope_payload.get("channel"),
    )
    expires_at_raw = payload.get("expires_at")
    expires_at = datetime.fromisoformat(expires_at_raw) if expires_at_raw is not None else None
    entry = CredentialEntry(
        entry_id=UUID(payload["entry_id"]),
        principal_genesis_id=payload["principal_genesis_id"],
        credential_type=CredentialType(payload["credential_type"]),
        service_identifier=payload["service_identifier"],
        entry_envelope_scope=scope,
        created_at=datetime.fromisoformat(payload["created_at"]),
        last_used_at=datetime.fromisoformat(payload["last_used_at"]),
        expires_at=expires_at,
        usage_counter=int(payload["usage_counter"]),
        rotation_policy=RotationPolicy(payload["rotation_policy"]),
    )
    return entry, payload["secret"]


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ConnectionVault:
    """OS-keychain-backed credential store.

    Per `specs/connection-vault.md` + shard 14 § 3.1.
    """

    def __init__(
        self,
        principal_genesis_id: str,
        active_envelope: Optional[ActiveEnvelope] = None,
        *,
        keyring_backend: Any = None,
    ) -> None:
        if not principal_genesis_id or not isinstance(principal_genesis_id, str):
            raise PrincipalRequiredError(
                "ConnectionVault requires a non-empty principal_genesis_id "
                "(see rules/tenant-isolation.md Rule 2)"
            )
        self._principal_genesis_id = principal_genesis_id
        self._active_envelope: Optional[ActiveEnvelope] = active_envelope
        # Allow dependency-injection of a custom backend (tests use the
        # `keyrings.alt` file-backed backend; default is keyring's
        # auto-selected best backend).
        self._keyring_backend = keyring_backend

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    @property
    def principal_genesis_id(self) -> str:
        return self._principal_genesis_id

    @property
    def active_envelope(self) -> Optional[ActiveEnvelope]:
        return self._active_envelope

    def with_active_envelope(self, envelope: ActiveEnvelope) -> "ConnectionVault":
        """Return a new vault bound to ``envelope`` (no in-place mutation).

        The vault holds the active envelope as a discriminator for the
        envelope-scope membership check in :meth:`get`. Swapping envelopes
        is a session-level operation; the vault is the per-principal
        container.
        """
        return ConnectionVault(
            principal_genesis_id=self._principal_genesis_id,
            active_envelope=envelope,
            keyring_backend=self._keyring_backend,
        )

    # ------------------------------------------------------------------
    # Keyring boundary helpers
    # ------------------------------------------------------------------
    def _set_password(self, entry_id: UUID, blob: str) -> None:
        try:
            if self._keyring_backend is not None:
                self._keyring_backend.set_password(KEYRING_SERVICE_NAMESPACE, str(entry_id), blob)
            else:
                keyring.set_password(KEYRING_SERVICE_NAMESPACE, str(entry_id), blob)
        except keyring.errors.KeyringError as exc:
            raise KeychainUnavailableError(
                f"OS keychain unavailable for set_password: {exc}"
            ) from exc

    def _get_password(self, entry_id: UUID) -> Optional[str]:
        try:
            if self._keyring_backend is not None:
                return self._keyring_backend.get_password(KEYRING_SERVICE_NAMESPACE, str(entry_id))
            return keyring.get_password(KEYRING_SERVICE_NAMESPACE, str(entry_id))
        except keyring.errors.KeyringError as exc:
            raise KeychainUnavailableError(
                f"OS keychain unavailable for get_password: {exc}"
            ) from exc

    def _delete_password(self, entry_id: UUID) -> None:
        try:
            if self._keyring_backend is not None:
                self._keyring_backend.delete_password(KEYRING_SERVICE_NAMESPACE, str(entry_id))
            else:
                keyring.delete_password(KEYRING_SERVICE_NAMESPACE, str(entry_id))
        except keyring.errors.PasswordDeleteError as exc:
            # Map the absent-entry case to typed EntryNotFoundError; everything
            # else is a keychain availability issue.
            raise EntryNotFoundError(f"entry_id {entry_id} not found for delete: {exc}") from exc
        except keyring.errors.KeyringError as exc:
            raise KeychainUnavailableError(
                f"OS keychain unavailable for delete_password: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Index: principal_genesis_id → set[entry_id]
    # ------------------------------------------------------------------
    # `keyring` lacks a portable "enumerate entries by service" API across
    # backends — macOS Keychain has SecItemCopyMatching, SecretService has
    # Collection.search_items, Windows has CredEnumerate, the auto-selected
    # backend is opaque to a portable wrapper. Phase 01 maintains a per-
    # principal index entry that records the active entry_ids; the index
    # itself is a separate keyring record keyed by a predictable string.
    # Phase 02 may replace this with backend-specific enumeration.

    def _index_key(self) -> str:
        return f"__index__:{self._principal_genesis_id}"

    def _read_index(self) -> list[UUID]:
        try:
            if self._keyring_backend is not None:
                payload = self._keyring_backend.get_password(
                    KEYRING_SERVICE_NAMESPACE, self._index_key()
                )
            else:
                payload = keyring.get_password(KEYRING_SERVICE_NAMESPACE, self._index_key())
        except keyring.errors.KeyringError as exc:
            raise KeychainUnavailableError(
                f"OS keychain unavailable for index read: {exc}"
            ) from exc
        if payload is None:
            return []
        ids = json.loads(payload)
        return [UUID(id_) for id_ in ids]

    def _write_index(self, entry_ids: list[UUID]) -> None:
        payload = json.dumps([str(eid) for eid in entry_ids], separators=(",", ":"))
        try:
            if self._keyring_backend is not None:
                self._keyring_backend.set_password(
                    KEYRING_SERVICE_NAMESPACE, self._index_key(), payload
                )
            else:
                keyring.set_password(KEYRING_SERVICE_NAMESPACE, self._index_key(), payload)
        except keyring.errors.KeyringError as exc:
            raise KeychainUnavailableError(
                f"OS keychain unavailable for index write: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        """Diagnostic: is the OS keychain reachable?

        Returns True if a probe round-trip succeeds; False on any keyring
        error. Per `rules/observability.md` MUST Rule 1, raw exceptions
        are NOT swallowed — they are translated into a typed boolean signal
        the caller can branch on.
        """
        probe_id = uuid4()
        try:
            self._set_password(probe_id, "__probe__")
            value = self._get_password(probe_id)
            self._delete_password(probe_id)
            return value == "__probe__"
        except KeychainUnavailableError:
            return False
        except EntryNotFoundError:
            # delete_password on a just-written probe failing means the
            # backend write didn't persist — treat as unavailable.
            return False

    def set(
        self,
        *,
        credential_type: CredentialType,
        service_identifier: str,
        entry_envelope_scope: EnvelopeScopeRef,
        secret: str,
        expires_at: Optional[datetime] = None,
        rotation_policy: RotationPolicy = RotationPolicy.NEVER,
    ) -> CredentialEntry:
        """Write a new credential entry per `specs/connection-vault.md`.

        Raises:
            PrincipalRequiredError: vault has no principal_genesis_id (caught
                at __init__; defensive raise if constructor was bypassed).
            InvalidServiceIdentifierError: service_identifier fails Phase 01
                validation (delegated to ``validate_service_identifier``).
            KeychainUnavailableError: OS keychain locked / unavailable.

        On success, emits an INFO log per `rules/observability.md` Rule 1
        (entry intent + outcome).
        """
        logger.info(
            "connection_vault.set.start",
            extra={
                "principal_hint": self._principal_genesis_id[:8],  # hash prefix only per Rule 8
                "service_identifier": service_identifier,
                "credential_type": credential_type.value,
            },
        )
        validate_service_identifier(service_identifier)
        validate_service_identifier(entry_envelope_scope.service_identifier)

        if expires_at is not None:
            expires_at = _ensure_utc(expires_at)
        now = utcnow()
        entry = CredentialEntry(
            entry_id=uuid4(),
            principal_genesis_id=self._principal_genesis_id,
            credential_type=credential_type,
            service_identifier=service_identifier,
            entry_envelope_scope=entry_envelope_scope,
            created_at=now,
            last_used_at=now,
            expires_at=expires_at,
            usage_counter=0,
            rotation_policy=rotation_policy,
        )
        blob = _serialize_record(entry, secret)
        self._set_password(entry.entry_id, blob)
        index = self._read_index()
        if entry.entry_id not in index:
            index.append(entry.entry_id)
            self._write_index(index)
        logger.info(
            "connection_vault.set.ok",
            extra={
                "entry_id_hint": str(entry.entry_id)[:8],
                "service_identifier": service_identifier,
            },
        )
        return entry

    def get(self, entry_id: UUID) -> tuple[CredentialEntry, str]:
        """Retrieve a credential entry + plaintext secret.

        Raises (per `specs/connection-vault.md` § Error taxonomy):
            EntryNotFoundError, EntryExpiredError, CrossPrincipalAccessRefusedError,
            EnvelopeScopeMismatchError, KeychainUnavailableError,
            UsageCounterOverflowError.

        On success: updates ``last_used_at`` and increments ``usage_counter``;
        persists the updated record back to the keychain.
        """
        if self._active_envelope is None:
            raise EnvelopeScopeMismatchError(
                "ConnectionVault.get called without an active envelope — "
                "set one via `with_active_envelope(...)` before retrieval "
                "(fail-closed default per shard 14 § 3.1 #7)"
            )

        blob = self._get_password(entry_id)
        if blob is None:
            raise EntryNotFoundError(f"entry_id {entry_id} not found")

        entry, secret = _deserialize_record(blob)

        if entry.principal_genesis_id != self._principal_genesis_id:
            raise CrossPrincipalAccessRefusedError(
                f"entry_id {entry_id} owned by a different principal — "
                f"cross-principal access requires Grant Moment (Phase 03)"
            )

        if entry.expires_at is not None and entry.expires_at <= utcnow():
            raise EntryExpiredError(
                f"entry_id {entry_id} expired at {entry.expires_at.isoformat()}; "
                f"re-authenticate via Grant Moment"
            )

        if not envelope_contains_scope(self._active_envelope, entry.entry_envelope_scope):
            raise EnvelopeScopeMismatchError(
                f"entry_id {entry_id} envelope_scope "
                f"(service={entry.entry_envelope_scope.service_identifier}, "
                f"channel={entry.entry_envelope_scope.channel}) "
                "is not included in the active session envelope"
            )

        if entry.usage_counter >= USAGE_COUNTER_MAX:
            raise UsageCounterOverflowError(
                f"entry_id {entry_id} usage_counter reached the int64 ceiling — "
                "investigate hostile-usage / programming bug; reset via re-pair"
            )

        updated = replace(entry, last_used_at=utcnow(), usage_counter=entry.usage_counter + 1)
        self._set_password(updated.entry_id, _serialize_record(updated, secret))
        return updated, secret

    def delete(self, entry_id: UUID) -> None:
        """Delete an entry. Raises EntryNotFoundError if absent."""
        # Defensive principal check via metadata before deletion: a caller
        # holding only an entry_id must not delete another principal's entry.
        blob = self._get_password(entry_id)
        if blob is None:
            raise EntryNotFoundError(f"entry_id {entry_id} not found")
        entry, _secret = _deserialize_record(blob)
        if entry.principal_genesis_id != self._principal_genesis_id:
            raise CrossPrincipalAccessRefusedError(
                f"entry_id {entry_id} owned by a different principal — "
                f"cross-principal delete refused"
            )
        self._delete_password(entry_id)
        index = self._read_index()
        if entry_id in index:
            index.remove(entry_id)
            self._write_index(index)

    def list_by_principal(self) -> tuple[CredentialEntry, ...]:
        """Return all entries owned by this vault's principal.

        Phase 01: returns the metadata-only view (no secrets). The secret
        plaintext is retrievable only via :meth:`get`.
        """
        out: list[CredentialEntry] = []
        for entry_id in self._read_index():
            blob = self._get_password(entry_id)
            if blob is None:
                # Stale index entry — happens if the OS keychain was wiped
                # outside the adapter. Skip rather than raise; the next
                # `set` will re-write the index.
                continue
            entry, _secret = _deserialize_record(blob)
            if entry.principal_genesis_id == self._principal_genesis_id:
                out.append(entry)
        return tuple(out)


__all__ = [
    "ConnectionVault",
    "KEYRING_SERVICE_NAMESPACE",
    "ActiveEnvelope",
]
