# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.skill_ingest.permission_registry — permission→PACT dimension resolver.

`specs/skill-ingest.md` § Permission → PACT dimension mapping: the
Foundation-curated registry `envoy-registry:permission-to-pact-dimension:v1`.

The pattern grammar is a `<category>:<scope>` form (`bash:*`, `file-read:*`,
`http-post:<domain>`, `mcp:<server>`, `oauth:<service>`, `exec:<pattern>`). The
resolver matches on the CATEGORY prefix (the part before the first `:`) — the
scope is the per-permission argument (a domain, a server name, a glob). A
declared permission whose category is not in the curated table raises
`UnknownPermissionPatternError` — a REAL lookup miss, never a silent default
(`rules/security.md` fail-closed).

The registry data is a pinned in-package data table fronted by the
`resolve_permission` interface. Per the spec, the live Foundation registry entry
`envoy-registry:permission-to-pact-dimension:v1` does not yet exist as a
network-served entry this phase; the pinned table IS the v1 entry's content, and
`resolve_permission` is the real lookup surface. When the live registry ships,
the same interface fronts it — the table becomes the offline-pinned fallback,
not a stub.

Provenance: the table is transcribed verbatim from `specs/skill-ingest.md`
§ Permission → PACT dimension mapping (the spec IS the authority per
`rules/specs-authority.md`). Each row carries the spec's documented PACT
dimensions + clearance / severity annotations.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass

from envoy.skill_ingest.errors import UnknownPermissionPatternError

REGISTRY_ID = "envoy-registry:permission-to-pact-dimension:v1"


class PactDimension(enum.Enum):
    """PACT governance dimensions a permission maps to.

    `specs/skill-ingest.md` § Permission → PACT dimension mapping +
    `specs/envelope-model.md` requested_permissions axes
    (financial / operational / temporal / data_access / communication) plus the
    Connection Vault target for `oauth:`.
    """

    OPERATIONAL = "operational"
    DATA_ACCESS = "data_access"
    COMMUNICATION = "communication"
    CONNECTION_VAULT = "connection_vault"


class Severity(enum.Enum):
    """Permission risk severity (`specs/skill-ingest.md`)."""

    NORMAL = "normal"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class PermissionResolution:
    """The resolved PACT mapping for one declared permission pattern.

    `dimensions` is the ordered tuple of PACT dimensions the permission compiles
    to; `clearance` is the minimum clearance the spec annotates (e.g. `bash:*`
    requires Confidential), `None` when unannotated; `severity` flags HIGH-risk
    categories (`exec:`).
    """

    category: str
    scope: str
    dimensions: tuple[PactDimension, ...]
    clearance: str | None
    severity: Severity


# The pinned `envoy-registry:permission-to-pact-dimension:v1` data table —
# transcribed verbatim from specs/skill-ingest.md § Permission → PACT dimension
# mapping. Keyed by permission CATEGORY (the token before the first ':').
_REGISTRY_TABLE: Mapping[str, tuple[tuple[PactDimension, ...], str | None, Severity]] = {
    # bash:* → Operational + Data Access (Confidential clearance)
    "bash": (
        (PactDimension.OPERATIONAL, PactDimension.DATA_ACCESS),
        "Confidential",
        Severity.NORMAL,
    ),
    # file-read:* → Data Access
    "file-read": ((PactDimension.DATA_ACCESS,), None, Severity.NORMAL),
    # file-write:* → Operational
    "file-write": ((PactDimension.OPERATIONAL,), None, Severity.NORMAL),
    # http-post:<domain> → Communication
    "http-post": ((PactDimension.COMMUNICATION,), None, Severity.NORMAL),
    # http-get:<domain> → Communication (read-side network egress; same dimension)
    "http-get": ((PactDimension.COMMUNICATION,), None, Severity.NORMAL),
    # mcp:<server> → Operational + Communication
    "mcp": (
        (PactDimension.OPERATIONAL, PactDimension.COMMUNICATION),
        None,
        Severity.NORMAL,
    ),
    # oauth:<service> → Connection Vault
    "oauth": ((PactDimension.CONNECTION_VAULT,), None, Severity.NORMAL),
    # exec:<pattern> → Operational (HIGH severity)
    "exec": ((PactDimension.OPERATIONAL,), "Confidential", Severity.HIGH),
}


def split_pattern(pattern: str) -> tuple[str, str]:
    """Split a permission pattern into ``(category, scope)`` on the first ``:``.

    A pattern with no ``:`` separator OR an empty category is malformed for the
    registry grammar — raises `UnknownPermissionPatternError` (the category is
    unrecognizable, so the registry cannot map it).
    """
    if ":" not in pattern:
        raise UnknownPermissionPatternError(
            f"permission pattern {pattern!r} has no '<category>:<scope>' form; "
            f"the registry {REGISTRY_ID} cannot resolve it",
            pattern=pattern,
        )
    category, scope = pattern.split(":", 1)
    if not category:
        raise UnknownPermissionPatternError(
            f"permission pattern {pattern!r} has an empty category; "
            f"the registry {REGISTRY_ID} cannot resolve it",
            pattern=pattern,
        )
    return category, scope


def resolve_permission(pattern: str) -> PermissionResolution:
    """Resolve one declared permission pattern against the curated registry.

    Args:
        pattern: A declared permission string (e.g. ``http-post:api.example.com``).

    Returns:
        The `PermissionResolution` — the PACT dimensions, clearance, and severity
        the registry maps the pattern's category to.

    Raises:
        UnknownPermissionPatternError: the pattern's category is not in the
            curated `envoy-registry:permission-to-pact-dimension:v1` table. This
            is a REAL lookup miss (fail-closed) — the registry never returns a
            default mapping for an unknown category.
    """
    category, scope = split_pattern(pattern)
    row = _REGISTRY_TABLE.get(category)
    if row is None:
        raise UnknownPermissionPatternError(
            f"permission category {category!r} (from {pattern!r}) is not in "
            f"{REGISTRY_ID}; wait for a registry refresh OR contact the "
            "Foundation to add the pattern",
            pattern=pattern,
        )
    dimensions, clearance, severity = row
    return PermissionResolution(
        category=category,
        scope=scope,
        dimensions=dimensions,
        clearance=clearance,
        severity=severity,
    )


def known_categories() -> frozenset[str]:
    """The set of permission categories the curated registry recognizes."""
    return frozenset(_REGISTRY_TABLE)


__all__ = [
    "REGISTRY_ID",
    "PactDimension",
    "PermissionResolution",
    "Severity",
    "known_categories",
    "resolve_permission",
    "split_pattern",
]
