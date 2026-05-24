"""Connection Vault typed error taxonomy.

Per `specs/connection-vault.md` § Error taxonomy — 7 typed exceptions sharing
a `ConnectionVaultError` base for try/except ergonomics.

`RotationOverdueWarn` is documented in the spec as **advisory** (not raised);
it is surfaced via UX nudge from `ConnectionVault.list_by_principal()` rather
than thrown. The class is omitted from this module because raising-shape is
the contract; advisory hints live in the adapter's return values per
`rules/zero-tolerance.md` Rule 2 (no stubs / fake-raise shapes).
"""

from __future__ import annotations


class ConnectionVaultError(Exception):
    """Base for all Connection Vault errors."""


class KeychainUnavailableError(ConnectionVaultError):
    """OS keychain locked or service unavailable.

    User action: unlock keychain (Touch ID / passphrase / device unlock).
    Recovery: auto after unlock.
    """


class EntryNotFoundError(ConnectionVaultError):
    """`entry_id` absent — deleted, never existed, or wrong principal.

    User action: re-pair the channel / re-issue the credential.
    """


class EntryExpiredError(ConnectionVaultError):
    """Retrieval after `expires_at` per Per-entry schema.

    User action: re-authenticate via Grant Moment; rotation_policy hint surfaces.
    """


class CrossPrincipalAccessRefusedError(ConnectionVaultError):
    """Principal A retrieved entry owned by Principal B without Grant Moment.

    Phase 03 surface; Phase 01 is single-principal but the error class exists
    as the multi-principal hook per shard 14 § 5.6.
    """


class EnvelopeScopeMismatchError(ConnectionVaultError):
    """Caller's session envelope does not include entry's `entry_envelope_scope`.

    User action: widen envelope (Grant Moment) OR use a different credential.
    Fail-closed by construction — set-membership check via
    `envoy.envelope.envelope_contains_scope`.
    """


class UsageCounterOverflowError(ConnectionVaultError):
    """`usage_counter` reached the int64 ceiling.

    Defensive guard. Programming bug / hostile-usage indicator.
    User action: investigate; reset counter via re-pair.
    """


class PrincipalRequiredError(ConnectionVaultError):
    """Vault initialised without a `principal_genesis_id`.

    Fail-closed default per shard 14 § 3.1 #7 — a vault without a principal
    refuses every `set()` call. Mirrors `envoy.trust.errors.PrincipalRequiredError`
    contract per `rules/tenant-isolation.md` Rule 2.
    """


class InvalidServiceIdentifierError(ConnectionVaultError):
    """`service_identifier` failed Phase 01 validation.

    Phase 01 validation (per shard 14 § 7.2 disposition): non-empty, UTF-8,
    ≤256 chars, matches `^[a-z0-9._-]+$`. The Foundation `service_identifier`
    registry per `specs/foundation-ops.md` is a Phase 02 concern.
    """


class RecordSchemaVersionError(ConnectionVaultError):
    """Keychain record schema_version differs from this Envoy build's contract.

    Distinct from :class:`EntryNotFoundError` (the entry IS present) and from
    :class:`CorruptedRecordError` (the bytes parsed cleanly — they're just at
    a version this build does not understand). Per code-reviewer MED-1
    (2026-05-24): conflating "absent" with "present-but-incompatible-version"
    misleads downstream UX (re-pair vs upgrade Envoy).
    """


class CorruptedRecordError(ConnectionVaultError):
    """Keychain record / index entry failed deserialization.

    Raised when ``_deserialize_record`` or ``_read_index`` encounters a payload
    that fails JSON decode, lacks required fields, or has shape-incompatible
    values (UUID/enum/datetime parsing failures). Phase 01 security disposition
    (per security-reviewer M2, 2026-05-24): a tampered or accidentally-malformed
    keychain entry MUST translate to a typed envoy error rather than letting
    a raw stdlib ``json.JSONDecodeError`` / ``KeyError`` / ``ValueError``
    propagate to the caller — typed taxonomy is the contract per
    ``rules/zero-tolerance.md`` Rule 3a.
    """
