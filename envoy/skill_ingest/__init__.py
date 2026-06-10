# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.skill_ingest — SKILL.md translator + CO validator (Phase 02, S9a).

Ships the install-time governance gate for ingesting external-ecosystem
`SKILL.md`-format skills into the Foundation-Verified tier:

- ``parse_skill_md`` — the canonical SKILL.md parser (name/version/description/
  permissions array + inline code blocks).
- ``generate_envelope_companion`` — the ENVELOPE.md YAML companion generator.
- ``resolve_permission`` — the permission→PACT dimension registry resolver
  (`envoy-registry:permission-to-pact-dimension:v1`).
- ``infer_permissions`` — the CONSERVATIVE Python ``ast`` static permission
  inference walk (literal-call evidence + import-graph second opinion +
  literal dynamic-dispatch flagging).
- ``compare_declared_inferred`` — the ASYMMETRIC declared-vs-inferred score
  routing (literal-undeclared → <0.5 reject; import-graph-only → warn;
  over-declaration → OverPrivilegeWarning).
- ``verify_publisher_signature`` — CO validator step 6 (REUSES the kailash
  Ed25519 verify primitive — no second verifier).
- ``validate_skill`` — the CO validator pipeline (steps 1-4, 6 + the typed
  step-5 ``AdversarialCheckPending`` surface; step 5's classifier ensemble
  ships in S9b).

T-020 (malicious skill author) + T-021 (envelope publisher compromise) defense;
ROADMAP §108 2-of-3-adversarial + 100-benign accountability.
"""

from __future__ import annotations

from envoy.skill_ingest.co_validator import (
    AdversarialCheckPending,
    COValidationResult,
    WaiverPayload,
    validate_skill,
)
from envoy.skill_ingest.comparison import ComparisonResult, compare_declared_inferred
from envoy.skill_ingest.envelope_md import (
    CoValidatorResult,
    EnvelopeCompanion,
    PublisherRef,
    build_requested_permissions,
    compute_skill_source_hash,
    generate_envelope_companion,
)
from envoy.skill_ingest.errors import (
    COValidatorRefusedError,
    EnvelopeCompanionMissingError,
    ForceInstallWaiverRequiredError,
    OverPrivilegeWarning,
    PublisherSignatureInvalidError,
    SkillCodeUnparseableError,
    SkillIngestError,
    SkillManifestParseError,
    SkillSourceHashMismatchError,
    UnknownPermissionPatternError,
)
from envoy.skill_ingest.inference import (
    InferredCapability,
    InferredPermissionSet,
    infer_permissions,
)
from envoy.skill_ingest.permission_registry import (
    REGISTRY_ID,
    PactDimension,
    PermissionResolution,
    Severity,
    known_categories,
    resolve_permission,
)
from envoy.skill_ingest.publisher_signature import verify_publisher_signature
from envoy.skill_ingest.skill_md import SkillManifest, parse_skill_md

__all__ = [
    "REGISTRY_ID",
    "AdversarialCheckPending",
    "COValidationResult",
    "COValidatorRefusedError",
    "CoValidatorResult",
    "ComparisonResult",
    "EnvelopeCompanion",
    "EnvelopeCompanionMissingError",
    "ForceInstallWaiverRequiredError",
    "InferredCapability",
    "InferredPermissionSet",
    "OverPrivilegeWarning",
    "PactDimension",
    "PermissionResolution",
    "PublisherRef",
    "PublisherSignatureInvalidError",
    "Severity",
    "SkillCodeUnparseableError",
    "SkillIngestError",
    "SkillManifest",
    "SkillManifestParseError",
    "SkillSourceHashMismatchError",
    "UnknownPermissionPatternError",
    "WaiverPayload",
    "build_requested_permissions",
    "compare_declared_inferred",
    "compute_skill_source_hash",
    "generate_envelope_companion",
    "infer_permissions",
    "known_categories",
    "parse_skill_md",
    "resolve_permission",
    "validate_skill",
    "verify_publisher_signature",
]
