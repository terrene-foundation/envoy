"""`.env` first-run import helper — shard 14 § 3.1 step 9.

Phase 01 onboarding (T-02-40 Boundary Conversation runtime) reads API keys
from a freshly-installed `.env` file and writes them into the Connection
Vault. After first-run, the Vault is the source of truth — the `.env` file
is no longer consulted.

This helper is the migration primitive: pure function, no I/O beyond
``os.environ`` (which the project's root ``conftest.py`` + the Boundary
Conversation entry point have already populated from `.env` per
``rules/env-models.md``).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from envoy.connection_vault.adapter import ConnectionVault
from envoy.connection_vault.schema import CredentialType, RotationPolicy
from envoy.envelope.types import EnvelopeScopeRef

logger = logging.getLogger("envoy.connection_vault.env_import")


@dataclass(frozen=True, slots=True)
class EnvCredentialSpec:
    """Per-credential migration spec.

    Boundary Conversation supplies a list of these from its onboarding plan;
    :func:`import_credentials_from_env` reads each from ``os.environ`` and
    writes to the Vault.
    """

    env_var_name: str
    credential_type: CredentialType
    service_identifier: str
    entry_envelope_scope: EnvelopeScopeRef
    rotation_policy: RotationPolicy = RotationPolicy.NEVER


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported_env_var_names: tuple[str, ...]
    skipped_env_var_names: tuple[str, ...]  # env var not set
    entry_ids: tuple[str, ...]


def import_credentials_from_env(
    vault: ConnectionVault,
    specs: tuple[EnvCredentialSpec, ...],
) -> ImportResult:
    """Read each spec's ``env_var_name`` from ``os.environ`` and persist.

    Skips (without raising) any env var that is unset or empty — first-run
    onboarding writes only the credentials the user has actually pasted into
    `.env`. Per `rules/observability.md` Rule 1, each skip + each import
    emits a structured log line.

    Returns:
        ImportResult naming which env vars landed, which were skipped, and
        the resulting entry_ids (as strings, since UUID is opaque to the
        caller logger).
    """
    imported: list[str] = []
    skipped: list[str] = []
    entry_ids: list[str] = []
    for spec in specs:
        raw: Optional[str] = os.environ.get(spec.env_var_name)
        if raw is None or not raw.strip():
            logger.info(
                "connection_vault.env_import.skip",
                extra={"env_var": spec.env_var_name, "reason": "unset_or_empty"},
            )
            skipped.append(spec.env_var_name)
            continue
        entry = vault.set(
            credential_type=spec.credential_type,
            service_identifier=spec.service_identifier,
            entry_envelope_scope=spec.entry_envelope_scope,
            secret=raw,
            rotation_policy=spec.rotation_policy,
        )
        imported.append(spec.env_var_name)
        entry_ids.append(str(entry.entry_id))
        logger.info(
            "connection_vault.env_import.ok",
            extra={
                "env_var": spec.env_var_name,
                "service_identifier": spec.service_identifier,
                "entry_id_hint": str(entry.entry_id)[:8],
            },
        )
    return ImportResult(
        imported_env_var_names=tuple(imported),
        skipped_env_var_names=tuple(skipped),
        entry_ids=tuple(entry_ids),
    )


__all__ = [
    "EnvCredentialSpec",
    "ImportResult",
    "import_credentials_from_env",
]
