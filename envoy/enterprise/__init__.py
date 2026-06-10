# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.enterprise — EnterpriseDeploymentRecord schema + 6-step verifier (S8e).

Phase 02 delivery (`specs/enterprise-deployment.md` § Phase delivery): the
EnterpriseDeploymentRecord schema + the 6-step envelope-import-time verifier +
the REQUIRED dual-sign gate, shipped as part of the runtime
cross-runtime-conformance landing. Mitigates T-024 (enterprise
delegation-upward / abuser-IT-deploys-onto-victim).

OUT OF SCOPE this phase (Phase 03): the disablement flow, the 24h cooling-off,
cross-channel confirmation, and the N=5 posture ratchet.

Signature verification reuses the SHARED `verify_steward_quorum` primitive from
`envoy.registry.steward_quorum` (1-of-1 quorum) — there is exactly one
quorum/verify implementation in the tree (EC-S8e.4).
"""

from __future__ import annotations

from envoy.enterprise.errors import (
    EnterpriseAlgorithmMigrationRequiredError,
    EnterpriseDeploymentError,
    EnterpriseDeploymentRecordInvalidError,
    EnterpriseDualSignMissingError,
    EnterpriseModeRevokedError,
    EnterpriseScopeMismatchError,
)
from envoy.enterprise.schema import (
    EDR_SCHEMA_VERSION,
    EDR_TYPE,
    EnterpriseDeploymentRecord,
    EnterprisePrincipal,
    EnterpriseScope,
)
from envoy.enterprise.verifier import (
    REATTESTATION_WINDOW_DAYS,
    EnterpriseDeploymentVerifier,
)

__all__ = [
    "EDR_SCHEMA_VERSION",
    "EDR_TYPE",
    "REATTESTATION_WINDOW_DAYS",
    "EnterpriseAlgorithmMigrationRequiredError",
    "EnterpriseDeploymentError",
    "EnterpriseDeploymentRecord",
    "EnterpriseDeploymentVerifier",
    "EnterpriseDeploymentRecordInvalidError",
    "EnterpriseDualSignMissingError",
    "EnterpriseModeRevokedError",
    "EnterprisePrincipal",
    "EnterpriseScope",
    "EnterpriseScopeMismatchError",
]
