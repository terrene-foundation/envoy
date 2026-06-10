# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.skill_ingest.envelope_md — ENVELOPE.md companion generator.

`specs/skill-ingest.md` § ENVELOPE.md generator: "Produces YAML companion
declaring `{skill_id, skill_source_hash, publisher{genesis_id, signature},
requested_permissions{financial, operational, temporal, data_access,
communication}, co_validator_result{passed, score, warnings, errors}}`."

The generator maps the SKILL.md declared permissions through the
permission→PACT registry to the five `requested_permissions` axes
(financial / operational / temporal / data_access / communication), computes
the `skill_source_hash` over the canonical skill source bytes, and embeds the
CO-validator result. The output is a YAML string + a structured dataclass so a
caller can both persist the companion and assert every field is populated
(EC-S9a / `test_envelope_md_generator_field_complete.py`).

`skill_source_hash` is `sha256` over the raw SKILL.md source bytes (UTF-8). The
hash anchors the `SkillSourceHashMismatchError` check (a fetched skill whose
bytes do not re-hash to the declared companion hash is refused).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import yaml

from envoy.skill_ingest.permission_registry import PactDimension, resolve_permission
from envoy.skill_ingest.skill_md import SkillManifest

# The five requested-permission axes the ENVELOPE.md companion declares
# (`specs/envelope-model.md` requested_permissions). The AST/registry pipeline
# populates operational / data_access / communication directly; financial +
# temporal are present-and-empty for SKILL.md-sourced skills (no SKILL.md
# permission pattern maps to a financial or temporal dimension this phase, so
# they ship as empty lists rather than being omitted — the companion schema is
# fixed-shape).
_AXIS_ORDER = ("financial", "operational", "temporal", "data_access", "communication")

# Map a PACT dimension to its requested_permissions axis key. Connection-Vault
# (`oauth:`) is surfaced under operational (the vault grant is an operational
# capability from the envelope's requested-permission view) AND retained in the
# raw permission list so the Connection-Vault target is not lost.
_DIMENSION_TO_AXIS: Mapping[PactDimension, str] = {
    PactDimension.OPERATIONAL: "operational",
    PactDimension.DATA_ACCESS: "data_access",
    PactDimension.COMMUNICATION: "communication",
    PactDimension.CONNECTION_VAULT: "operational",
}


def compute_skill_source_hash(skill_source: str) -> str:
    """`sha256` hex over the raw SKILL.md source bytes (UTF-8)."""
    return hashlib.sha256(skill_source.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PublisherRef:
    """The ENVELOPE.md ``publisher`` block: ``{genesis_id, signature}``.

    `genesis_id` is the publisher's Foundation genesis identity; `signature` is
    the Ed25519 signature (hex) over the `skill_source_hash` — verified at CO
    validator step 6 against the publisher's pinned public key.
    """

    genesis_id: str
    signature: str


@dataclass(frozen=True, slots=True)
class CoValidatorResult:
    """The ENVELOPE.md ``co_validator_result`` block.

    `{passed, score, warnings, errors}` per the spec. Populated from the CO
    validator pipeline result.
    """

    passed: bool
    score: float
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnvelopeCompanion:
    """The full ENVELOPE.md companion as a structured object.

    Mirrors the spec's YAML shape 1:1 so a caller can assert every field is
    populated (`test_envelope_md_generator_field_complete.py`). `to_yaml`
    serialises it to the canonical YAML companion string.
    """

    skill_id: str
    skill_source_hash: str
    publisher: PublisherRef
    requested_permissions: Mapping[str, tuple[str, ...]]
    co_validator_result: CoValidatorResult
    raw_permissions: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """The companion as a plain dict (YAML-serialisable)."""
        return {
            "skill_id": self.skill_id,
            "skill_source_hash": self.skill_source_hash,
            "publisher": {
                "genesis_id": self.publisher.genesis_id,
                "signature": self.publisher.signature,
            },
            "requested_permissions": {
                axis: list(self.requested_permissions.get(axis, ())) for axis in _AXIS_ORDER
            },
            "co_validator_result": {
                "passed": self.co_validator_result.passed,
                "score": self.co_validator_result.score,
                "warnings": list(self.co_validator_result.warnings),
                "errors": list(self.co_validator_result.errors),
            },
            "raw_permissions": list(self.raw_permissions),
        }

    def to_yaml(self) -> str:
        """Serialise the companion to the canonical ENVELOPE.md YAML string."""
        return yaml.safe_dump(self.to_dict(), sort_keys=True, default_flow_style=False)


def build_requested_permissions(
    declared_permissions: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    """Map declared SKILL.md permissions through the registry to the five axes.

    Each declared permission is resolved to its PACT dimensions; each dimension
    maps to a requested_permissions axis, under which the FULL permission
    pattern is recorded. `financial` / `temporal` ship present-and-empty (no
    SKILL.md pattern maps to them this phase — fixed-shape companion schema).

    Raises:
        UnknownPermissionPatternError: propagated from `resolve_permission` when
            a declared pattern's category is not in the registry (step 2
            fail-closed).
    """
    axes: dict[str, list[str]] = {axis: [] for axis in _AXIS_ORDER}
    for pattern in declared_permissions:
        resolution = resolve_permission(pattern)
        for dimension in resolution.dimensions:
            axis = _DIMENSION_TO_AXIS[dimension]
            if pattern not in axes[axis]:
                axes[axis].append(pattern)
    return {axis: tuple(values) for axis, values in axes.items()}


def generate_envelope_companion(
    manifest: SkillManifest,
    skill_source: str,
    publisher: PublisherRef,
    co_validator_result: CoValidatorResult,
) -> EnvelopeCompanion:
    """Generate the ENVELOPE.md companion for a parsed skill.

    Args:
        manifest: The parsed SKILL.md manifest.
        skill_source: The raw SKILL.md source text (hashed for
            `skill_source_hash`).
        publisher: The publisher genesis-id + signature block.
        co_validator_result: The CO validator outcome to embed.

    Returns:
        A fully-populated `EnvelopeCompanion`. Every field in the spec's shape
        is present (financial/temporal ship empty, never omitted).

    Raises:
        UnknownPermissionPatternError: propagated from registry resolution.
    """
    requested = build_requested_permissions(manifest.declared_permissions)
    return EnvelopeCompanion(
        skill_id=f"{manifest.name}@{manifest.version}",
        skill_source_hash=compute_skill_source_hash(skill_source),
        publisher=publisher,
        requested_permissions=requested,
        co_validator_result=co_validator_result,
        raw_permissions=manifest.declared_permissions,
    )


__all__ = [
    "CoValidatorResult",
    "EnvelopeCompanion",
    "PublisherRef",
    "build_requested_permissions",
    "compute_skill_source_hash",
    "generate_envelope_companion",
]
