"""Connection Vault per-entry schema.

Per `specs/connection-vault.md` § Per-entry schema (11 fields).

Frozen dataclass for immutability after construction (the entry is the
identity record; mutation would break the keychain key → record binding).
The `ciphertext` field is NOT stored on the Python object — the secret bytes
live in the OS keychain via `keyring.set_password()` and are never copied
into adapter-layer memory beyond the active retrieval call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from envoy.envelope.types import EnvelopeScopeRef


class CredentialType(str, Enum):
    """Per `specs/connection-vault.md` § Per-entry schema row `credential_type`."""

    API_KEY = "api_key"
    BOT_TOKEN = "bot_token"
    OAUTH_REFRESH = "oauth_refresh"
    BASIC_AUTH = "basic_auth"
    WEBHOOK_SECRET = "webhook_secret"


class RotationPolicy(str, Enum):
    """Per `specs/connection-vault.md` § Per-entry schema row `rotation_policy`."""

    NEVER = "never"
    YEARLY = "yearly"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    ON_EVENT = "on_event"


_SERVICE_IDENTIFIER_RE = re.compile(r"^[a-z0-9._-]+$")
_SERVICE_IDENTIFIER_MAX_LEN = 256
USAGE_COUNTER_MAX = 2**63 - 1  # int64 ceiling per spec Error taxonomy row


def validate_service_identifier(value: str) -> None:
    """Phase 01 validation per shard 14 § 7.2 disposition.

    Non-empty, ≤256 chars, matches ``^[a-z0-9._-]+$``. The Foundation registry
    per ``specs/foundation-ops.md`` is a Phase 02 concern; Phase 01 is
    defensive-only against accidental URL-confusing characters that would
    break downstream channel-adapter URL construction.

    Raises:
        InvalidServiceIdentifierError: validation failed.
    """
    from envoy.connection_vault.errors import InvalidServiceIdentifierError

    if not isinstance(value, str):  # defensive; type checker enforces but runtime caller may bypass
        raise InvalidServiceIdentifierError(
            f"service_identifier must be str, got {type(value).__name__}"
        )
    if not value:
        raise InvalidServiceIdentifierError("service_identifier must be non-empty")
    if len(value) > _SERVICE_IDENTIFIER_MAX_LEN:
        raise InvalidServiceIdentifierError(
            f"service_identifier exceeds {_SERVICE_IDENTIFIER_MAX_LEN} chars (got {len(value)})"
        )
    if not _SERVICE_IDENTIFIER_RE.match(value):
        raise InvalidServiceIdentifierError(
            f"service_identifier {value!r} must match ^[a-z0-9._-]+$ "
            f"(lower-case alphanumeric, dot, underscore, hyphen)"
        )


@dataclass(frozen=True, slots=True)
class CredentialEntry:
    """Per `specs/connection-vault.md` § Per-entry schema.

    The 10 fields tracked on the Python object (the 11th field, `ciphertext`,
    lives in the OS keychain and is fetched via `ConnectionVault.get()` —
    plaintext bytes never persist in adapter-layer Python state beyond the
    active retrieval).

    Frozen because every retrieval that updates `last_used_at` /
    `usage_counter` MUST construct a new CredentialEntry via
    `dataclasses.replace`; mutating in-place would race with concurrent
    retrievals (Phase 01 single-task, but the frozen contract is the
    structural defense against Phase 02 concurrency).
    """

    entry_id: UUID
    principal_genesis_id: str
    credential_type: CredentialType
    service_identifier: str
    entry_envelope_scope: EnvelopeScopeRef
    created_at: datetime
    last_used_at: datetime
    expires_at: Optional[datetime]
    usage_counter: int
    rotation_policy: RotationPolicy = field(default=RotationPolicy.NEVER)

    def __post_init__(self) -> None:
        # Defensive: spec mandates UTC datetimes ("created_at — datetime UTC").
        # Naive datetimes silently break cross-runtime comparison.
        if (
            self.created_at.tzinfo is None
            or self.created_at.tzinfo.utcoffset(self.created_at) is None
        ):
            raise ValueError("CredentialEntry.created_at must be timezone-aware UTC")
        if (
            self.last_used_at.tzinfo is None
            or self.last_used_at.tzinfo.utcoffset(self.last_used_at) is None
        ):
            raise ValueError("CredentialEntry.last_used_at must be timezone-aware UTC")
        if self.expires_at is not None and (
            self.expires_at.tzinfo is None
            or self.expires_at.tzinfo.utcoffset(self.expires_at) is None
        ):
            raise ValueError("CredentialEntry.expires_at must be timezone-aware UTC (or None)")
        if self.usage_counter < 0:
            raise ValueError(
                f"CredentialEntry.usage_counter must be non-negative (got {self.usage_counter})"
            )
        # principal_genesis_id is a sha256 hex string per spec; defensive shape check
        if not self.principal_genesis_id or not isinstance(self.principal_genesis_id, str):
            raise ValueError("CredentialEntry.principal_genesis_id must be a non-empty string")
        validate_service_identifier(self.service_identifier)


def utcnow() -> datetime:
    """Single-source UTC clock (timezone-aware) — kept narrow for monkeypatch."""
    return datetime.now(timezone.utc)
