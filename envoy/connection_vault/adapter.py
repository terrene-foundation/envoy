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
from typing import Any, Optional
from uuid import UUID, uuid4

import keyring
import keyring.errors

from envoy.connection_vault.errors import (
    CorruptedRecordError,
    CrossPrincipalAccessRefusedError,
    EntryExpiredError,
    EntryNotFoundError,
    EnvelopeScopeMismatchError,
    InvalidServiceIdentifierError,
    KeychainUnavailableError,
    PrincipalRequiredError,
    RecordSchemaVersionError,
    UsageCounterOverflowError,
)
from envoy.connection_vault.schema import (
    USAGE_COUNTER_MAX,
    CredentialEntry,
    CredentialType,
    RotationPolicy,
    utcnow,
    validate_principal_genesis_id,
    validate_service_identifier,
)
from envoy.envelope import (
    ActiveEnvelope,
    EnvelopeScopeRef,
    envelope_contains_scope,
)

KEYRING_SERVICE_NAMESPACE = "envoy.connection-vault"
"""Single keyring `service` namespace per shard 14 § 3.1 step 1 — the
per-platform OS keychain entries are keyed by this string + the entry_id."""

_RECORD_SCHEMA_VERSION = 1

# Sentinel for `_log_error` calls on the set / list_by_principal paths
# that raise BEFORE an entry_id is generated or when no specific entry
# is responsible (e.g. the index payload itself is corrupted). Centralized
# per /redteam R2-N1 (2026-05-24) so log readers grep one symbol.
_NIL_ENTRY_ID = UUID(int=0)

logger = logging.getLogger("envoy.connection_vault")


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
    """Inverse of :func:`_serialize_record`.

    Per security-reviewer M2 (2026-05-24): any malformed payload (JSON decode
    failure, missing required key, wrong type, unparseable UUID/enum/datetime)
    raises :class:`CorruptedRecordError` — NOT a raw ``json.JSONDecodeError``
    / ``KeyError`` / ``ValueError`` — so the caller sees the typed taxonomy
    contract per ``rules/zero-tolerance.md`` Rule 3a.
    """
    try:
        payload = json.loads(blob)
    except (json.JSONDecodeError, TypeError) as exc:
        raise CorruptedRecordError(f"connection-vault record JSON decode failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise CorruptedRecordError(
            f"connection-vault record top-level must be JSON object, "
            f"got {type(payload).__name__}"
        )
    if payload.get("schema_version") != _RECORD_SCHEMA_VERSION:
        raise RecordSchemaVersionError(
            f"unsupported connection-vault record schema_version="
            f"{payload.get('schema_version')!r} (this build expects "
            f"{_RECORD_SCHEMA_VERSION}); upgrade Envoy or re-pair credential"
        )
    try:
        scope_payload = payload["entry_envelope_scope"]
        if not isinstance(scope_payload, dict):
            raise CorruptedRecordError("entry_envelope_scope must be JSON object")
        # Per R1-F5 (2026-05-24): tampered scope fields must raise typed
        # CorruptedRecordError. EnvelopeScopeRef itself has no __post_init__,
        # so type-check at the deserialization boundary.
        scope_service = scope_payload["service_identifier"]
        if not isinstance(scope_service, str):
            raise CorruptedRecordError(
                f"entry_envelope_scope.service_identifier must be str, "
                f"got {type(scope_service).__name__}"
            )
        scope_channel = scope_payload.get("channel")
        if scope_channel is not None and not isinstance(scope_channel, str):
            raise CorruptedRecordError(
                f"entry_envelope_scope.channel must be str or null, "
                f"got {type(scope_channel).__name__}"
            )
        scope = EnvelopeScopeRef(
            service_identifier=scope_service,
            channel=scope_channel,
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
        secret = payload["secret"]
        if not isinstance(secret, str):
            raise CorruptedRecordError(
                f"connection-vault record `secret` must be str, " f"got {type(secret).__name__}"
            )
    except CorruptedRecordError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise CorruptedRecordError(f"connection-vault record shape invalid: {exc}") from exc
    except (PrincipalRequiredError, InvalidServiceIdentifierError) as exc:
        # Per R1-F2 (2026-05-24): CredentialEntry.__post_init__ invokes
        # validate_principal_genesis_id + validate_service_identifier, which
        # raise PrincipalRequiredError / InvalidServiceIdentifierError. These
        # do NOT inherit from (KeyError, TypeError, ValueError), so without
        # this branch they'd leak past the typed-taxonomy contract the
        # spec § Change log advertises. Wrap into CorruptedRecordError so
        # callers see the uniform "tampered record" surface.
        raise CorruptedRecordError(
            f"connection-vault record contains invalid validator-rejected field: {exc}"
        ) from exc
    return entry, secret


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
        # Full shape validation per security-reviewer M3 (2026-05-24):
        # the principal_genesis_id flows into the keychain key namespace via
        # `_index_key()`; control chars / colons / newlines would collide
        # with the `__index__:{principal}` convention.
        validate_principal_genesis_id(principal_genesis_id)
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
        # Per security-reviewer M2 (2026-05-24): malformed / tampered index
        # payload raises `CorruptedRecordError` rather than letting raw stdlib
        # exceptions propagate.
        try:
            ids_raw = json.loads(payload)
        except (json.JSONDecodeError, TypeError) as exc:
            raise CorruptedRecordError(
                f"connection-vault index JSON decode failed for principal "
                f"{self._principal_genesis_id[:8]}…: {exc}"
            ) from exc
        if not isinstance(ids_raw, list):
            raise CorruptedRecordError(
                f"connection-vault index payload must be JSON list, "
                f"got {type(ids_raw).__name__}"
            )
        try:
            return [UUID(id_) for id_ in ids_raw]
        except (ValueError, AttributeError, TypeError) as exc:
            raise CorruptedRecordError(
                f"connection-vault index contains non-UUID entries: {exc}"
            ) from exc

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
        # Per R1-F1 (2026-05-24): every typed-error raise on the set path
        # MUST emit a warning log symmetric with get/delete. The
        # NIL_ENTRY_ID sentinel below stands in for "raised before
        # entry_id was generated" so the log line still carries a hint
        # field per `rules/observability.md` Rule 1.
        try:
            validate_service_identifier(service_identifier)
            validate_service_identifier(entry_envelope_scope.service_identifier)
        except InvalidServiceIdentifierError:
            self._log_error("set", _NIL_ENTRY_ID, "invalid_service_identifier")
            raise

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
        try:
            self._set_password(entry.entry_id, blob)
        except KeychainUnavailableError:
            self._log_error("set", entry.entry_id, "keychain_unavailable")
            raise
        try:
            index = self._read_index()
            if entry.entry_id not in index:
                index.append(entry.entry_id)
                self._write_index(index)
        except (KeychainUnavailableError, CorruptedRecordError):
            # Partial-write recovery surface per `rules/observability.md`
            # Rule 7: the entry IS in the keychain but the index update
            # failed. Caller sees the typed raise; logs name the in-flight
            # entry_id so operators can recover via direct keychain inspection.
            self._log_error("set", entry.entry_id, "index_update_failed_after_write")
            raise
        logger.info(
            "connection_vault.set.ok",
            extra={
                "entry_id_hint": str(entry.entry_id)[:8],
                "service_identifier": service_identifier,
            },
        )
        return entry

    def _log_error(self, op: str, entry_id: UUID, reason: str) -> None:
        """Structured error log per `rules/observability.md` Rule 1 + Rule 8.

        Hashed-prefix only on principal + entry id; raw reason name (not
        value) per Rule 8 schema-revealing field-name discipline.
        """
        logger.warning(
            f"connection_vault.{op}.error",
            extra={
                "principal_hint": self._principal_genesis_id[:8],
                "entry_id_hint": str(entry_id)[:8],
                "reason": reason,
            },
        )

    def get(self, entry_id: UUID) -> tuple[CredentialEntry, str]:
        """Retrieve a credential entry + plaintext secret.

        Raises (per `specs/connection-vault.md` § Error taxonomy):
            EntryNotFoundError, EntryExpiredError, CrossPrincipalAccessRefusedError,
            EnvelopeScopeMismatchError, KeychainUnavailableError,
            UsageCounterOverflowError.

        On success: updates ``last_used_at`` and increments ``usage_counter``;
        persists the updated record back to the keychain.
        """
        logger.info(
            "connection_vault.get.start",
            extra={
                "principal_hint": self._principal_genesis_id[:8],
                "entry_id_hint": str(entry_id)[:8],
            },
        )
        if self._active_envelope is None:
            self._log_error("get", entry_id, "no_active_envelope")
            raise EnvelopeScopeMismatchError(
                "ConnectionVault.get called without an active envelope — "
                "set one via `with_active_envelope(...)` before retrieval "
                "(fail-closed default per shard 14 § 3.1 #7)"
            )

        blob = self._get_password(entry_id)
        if blob is None:
            self._log_error("get", entry_id, "entry_not_found")
            raise EntryNotFoundError(f"entry_id {entry_id} not found")

        entry, secret = _deserialize_record(blob)

        if entry.principal_genesis_id != self._principal_genesis_id:
            self._log_error("get", entry_id, "cross_principal_refused")
            raise CrossPrincipalAccessRefusedError(
                f"entry_id {entry_id} owned by a different principal — "
                f"cross-principal access requires Grant Moment (Phase 03)"
            )

        if entry.expires_at is not None and entry.expires_at <= utcnow():
            self._log_error("get", entry_id, "entry_expired")
            raise EntryExpiredError(
                f"entry_id {entry_id} expired at {entry.expires_at.isoformat()}; "
                f"re-authenticate via Grant Moment"
            )

        if not envelope_contains_scope(self._active_envelope, entry.entry_envelope_scope):
            self._log_error("get", entry_id, "envelope_scope_mismatch")
            raise EnvelopeScopeMismatchError(
                f"entry_id {entry_id} envelope_scope "
                f"(service={entry.entry_envelope_scope.service_identifier}, "
                f"channel={entry.entry_envelope_scope.channel}) "
                "is not included in the active session envelope"
            )

        if entry.usage_counter >= USAGE_COUNTER_MAX:
            self._log_error("get", entry_id, "usage_counter_overflow")
            raise UsageCounterOverflowError(
                f"entry_id {entry_id} usage_counter reached the int64 ceiling — "
                "investigate hostile-usage / programming bug; reset via re-pair"
            )

        updated = replace(entry, last_used_at=utcnow(), usage_counter=entry.usage_counter + 1)
        self._set_password(updated.entry_id, _serialize_record(updated, secret))
        logger.info(
            "connection_vault.get.ok",
            extra={
                "principal_hint": self._principal_genesis_id[:8],
                "entry_id_hint": str(entry_id)[:8],
                "usage_counter": updated.usage_counter,
            },
        )
        return updated, secret

    def delete(self, entry_id: UUID) -> None:
        """Delete an entry. Raises EntryNotFoundError if absent."""
        logger.info(
            "connection_vault.delete.start",
            extra={
                "principal_hint": self._principal_genesis_id[:8],
                "entry_id_hint": str(entry_id)[:8],
            },
        )
        # Defensive principal check via metadata before deletion: a caller
        # holding only an entry_id must not delete another principal's entry.
        blob = self._get_password(entry_id)
        if blob is None:
            self._log_error("delete", entry_id, "entry_not_found")
            raise EntryNotFoundError(f"entry_id {entry_id} not found")
        entry, _secret = _deserialize_record(blob)
        if entry.principal_genesis_id != self._principal_genesis_id:
            self._log_error("delete", entry_id, "cross_principal_refused")
            raise CrossPrincipalAccessRefusedError(
                f"entry_id {entry_id} owned by a different principal — "
                f"cross-principal delete refused"
            )
        self._delete_password(entry_id)
        index = self._read_index()
        if entry_id in index:
            index.remove(entry_id)
            self._write_index(index)
        logger.info(
            "connection_vault.delete.ok",
            extra={
                "principal_hint": self._principal_genesis_id[:8],
                "entry_id_hint": str(entry_id)[:8],
            },
        )

    def list_by_principal(self) -> tuple[CredentialEntry, ...]:
        """Return all entries owned by this vault's principal.

        Phase 01: returns the metadata-only view (no secrets). The secret
        plaintext is retrievable only via :meth:`get`.
        """
        logger.info(
            "connection_vault.list_by_principal.start",
            extra={"principal_hint": self._principal_genesis_id[:8]},
        )
        # Per R1-F1 (2026-05-24): KeychainUnavailableError + CorruptedRecordError
        # on the index-read path must emit a symmetric warning log before
        # propagating. UUID(int=0) sentinel because no specific entry_id
        # caused the failure — the index itself did.
        try:
            index_ids = self._read_index()
        except KeychainUnavailableError:
            self._log_error("list_by_principal", _NIL_ENTRY_ID, "keychain_unavailable")
            raise
        except CorruptedRecordError:
            self._log_error("list_by_principal", _NIL_ENTRY_ID, "corrupted_index")
            raise
        out: list[CredentialEntry] = []
        stale_count = 0
        for entry_id in index_ids:
            try:
                blob = self._get_password(entry_id)
            except KeychainUnavailableError:
                self._log_error("list_by_principal", entry_id, "keychain_unavailable")
                raise
            if blob is None:
                # Stale index entry — happens if the OS keychain was wiped
                # outside the adapter. Skip rather than raise; the next
                # `set` will re-write the index.
                stale_count += 1
                continue
            try:
                entry, _secret = _deserialize_record(blob)
            except CorruptedRecordError:
                self._log_error("list_by_principal", entry_id, "corrupted_record")
                raise
            if entry.principal_genesis_id == self._principal_genesis_id:
                out.append(entry)
        if stale_count > 0:
            logger.warning(
                "connection_vault.list_by_principal.stale_index_entries",
                extra={
                    "principal_hint": self._principal_genesis_id[:8],
                    "stale_count": stale_count,
                },
            )
        logger.info(
            "connection_vault.list_by_principal.ok",
            extra={
                "principal_hint": self._principal_genesis_id[:8],
                "returned_count": len(out),
            },
        )
        return tuple(out)


__all__ = [
    "ConnectionVault",
    "KEYRING_SERVICE_NAMESPACE",
]
# `ActiveEnvelope` canonical home is `envoy.envelope.scope` per code-reviewer
# MED-5; this module only consumes it. Removed from `__all__` per R1-F6 to
# eliminate facade-vs-module export drift.
