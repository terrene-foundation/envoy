# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: T-024 enterprise delegation-upward / abuser-IT vector.

EC-S8e.3 — the T-024 abuser-IT vector (an org admin attempting to deploy an
enterprise envelope overlay onto an affected employee WITHOUT that employee's
signature) is refused at verify time.

`specs/threat-model.md` T-024 + `specs/enterprise-deployment.md` § Provenance
("Threats mitigated: T-024 enterprise delegation-upward + flip-off attack"). The
REQUIRED dual-sign gate is the structural defense: an org admin who controls the
deploying-principal key still cannot import an enterprise overlay onto an
employee, because the verifier refuses any EDR missing the affected employee's
signature.

Tier-2 real crypto (kailash `InMemoryKeyManager`), no mocking. Structural
assertion on the raised type per `rules/probe-driven-verification.md` — the test
CALLS the verifier and asserts the refusal, never greps source.
"""

from __future__ import annotations

import pytest

from envoy.enterprise import (
    EnterpriseDeploymentRecord,
    EnterpriseDeploymentVerifier,
    EnterpriseDualSignMissingError,
)
from tests.helpers.edr_harness import build_edr, mint_edr_keys, reference_now


@pytest.mark.regression
class TestT024EnterpriseDelegationUpward:
    async def test_org_admin_deploy_without_employee_signature_is_refused(
        self,
    ) -> None:
        # T-024: the abuser-IT admin holds the deploying-principal key and signs
        # the EDR, but the affected employee has NOT signed. A valid org-admin
        # signature does NOT make the deployment legitimate — the verifier
        # refuses at import time because the employee never attested.
        keys = await mint_edr_keys(sign_employee=False)
        verifier = EnterpriseDeploymentVerifier(
            key_manager=keys.key_manager,
            known_org_roots=keys.known_org_roots,
            now=reference_now,
        )
        # Org admin signature is genuine + verifies against the org root; only
        # the employee signature is absent — the precise abuser-IT shape.
        edr = build_edr(keys, affected_employee_signature_hex="")
        assert edr["signatures"]["org_admin_signature_hex"]  # admin DID sign
        with pytest.raises(EnterpriseDualSignMissingError):
            await verifier.verify(edr)

    async def test_legitimate_dual_signed_deployment_still_succeeds(self) -> None:
        # Control: when the employee DOES co-sign, the same deployment imports
        # successfully — the gate refuses the abuser vector without blocking the
        # legitimate consented deployment.
        keys = await mint_edr_keys()
        verifier = EnterpriseDeploymentVerifier(
            key_manager=keys.key_manager,
            known_org_roots=keys.known_org_roots,
            now=reference_now,
        )
        record = await verifier.verify(build_edr(keys))
        assert isinstance(record, EnterpriseDeploymentRecord)
