"""envoy.connection_vault — OS-keychain-backed credential adapter.

Implements `specs/connection-vault.md` per shard 14
(`workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md`).

Phase 01 minimum: ``set`` / ``get`` / ``delete`` / ``list_by_principal`` /
``is_available`` on top of the cross-platform ``keyring`` library
(MIT-licensed; macOS Keychain + Linux Secret Service + Windows Credential
Manager). Phase 02 adds rotation execution + OAuth refresh dance. Phase 03
adds per-principal isolation gating via Grant Moment.

Public facade per `rules/orphan-detection.md` Rule 6 — every module-scope
import in this file appears in ``__all__``.
"""

from envoy.connection_vault.adapter import (
    KEYRING_SERVICE_NAMESPACE,
    ActiveEnvelope,
    ConnectionVault,
)
from envoy.connection_vault.env_import import (
    EnvCredentialSpec,
    ImportResult,
    import_credentials_from_env,
)
from envoy.connection_vault.errors import (
    ConnectionVaultError,
    CrossPrincipalAccessRefusedError,
    EntryExpiredError,
    EntryNotFoundError,
    EnvelopeScopeMismatchError,
    InvalidServiceIdentifierError,
    KeychainUnavailableError,
    PrincipalRequiredError,
    UsageCounterOverflowError,
)
from envoy.connection_vault.schema import (
    USAGE_COUNTER_MAX,
    CredentialEntry,
    CredentialType,
    RotationPolicy,
    validate_service_identifier,
)

__all__ = [
    # Adapter
    "ConnectionVault",
    "KEYRING_SERVICE_NAMESPACE",
    "ActiveEnvelope",
    # Schema
    "CredentialEntry",
    "CredentialType",
    "RotationPolicy",
    "USAGE_COUNTER_MAX",
    "validate_service_identifier",
    # `.env` first-run import
    "EnvCredentialSpec",
    "ImportResult",
    "import_credentials_from_env",
    # Errors
    "ConnectionVaultError",
    "CrossPrincipalAccessRefusedError",
    "EntryExpiredError",
    "EntryNotFoundError",
    "EnvelopeScopeMismatchError",
    "InvalidServiceIdentifierError",
    "KeychainUnavailableError",
    "PrincipalRequiredError",
    "UsageCounterOverflowError",
]
