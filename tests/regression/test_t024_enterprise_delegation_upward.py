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
    EnterpriseDeploymentRecordInvalidError,
    EnterpriseDeploymentVerifier,
    EnterpriseDualSignMissingError,
    EnterpriseScope,
)
from tests.helpers.edr_harness import (
    TEMPLATE_ENVELOPE_HASH,
    build_edr,
    mint_edr_keys,
    reference_now,
    transplant_signatures,
)


@pytest.mark.regression
class TestT024EnterpriseDelegationUpward:
    async def test_org_admin_deploy_without_employee_signature_is_refused(
        self,
    ) -> None:
        # T-024: the abuser-IT admin holds the deploying-principal key and signs
        # the EDR, but the affected employee has NOT signed. A valid org-admin
        # signature does NOT make the deployment legitimate — the verifier
        # refuses at import time because the employee never attested.
        keys = await mint_edr_keys()
        verifier = EnterpriseDeploymentVerifier(
            key_manager=keys.key_manager,
            known_org_roots=keys.known_org_roots,
            now=reference_now,
        )
        # Org admin signature is genuine + verifies against the org root; only
        # the employee signature is absent — the precise abuser-IT shape.
        edr = build_edr(keys, sign_employee=False)
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


@pytest.mark.regression
class TestT024SignatureTransplant:
    """E-1: a dual-signed EDR's signatures cannot be transplanted onto a record
    with a mutated field set (different scope / different affected employee).

    The signed payload binds the FULL canonical record, not just the
    `template_envelope_hash`. A malicious IT operator who reads a legitimately
    dual-signed EDR-A and builds EDR-B carrying the same envelope hash + the same
    signature pair but a widened scope (or a different employee) MUST be refused:
    the transplanted signatures verify over EDR-A's record, not EDR-B's.
    """

    async def _verifier(self, keys) -> EnterpriseDeploymentVerifier:
        return EnterpriseDeploymentVerifier(
            key_manager=keys.key_manager,
            known_org_roots=keys.known_org_roots,
            now=reference_now,
        )

    async def test_scope_mutated_transplant_is_refused(self) -> None:
        # EDR-A: legitimately dual-signed at employee-personal scope.
        keys = await mint_edr_keys()
        verifier = await self._verifier(keys)
        edr_a = build_edr(
            keys,
            scope=EnterpriseScope.EMPLOYEE_PERSONAL_ENVELOPE_OVERLAY.value,
        )
        # Confirm EDR-A is itself valid (the transplant source is genuine).
        await verifier.verify(edr_a)

        # EDR-B: same envelope hash, scope WIDENED to agent-fleet, but carrying
        # EDR-A's signatures verbatim. Build a clean EDR-B (which re-signs at the
        # new scope), then OVERWRITE its signatures with EDR-A's.
        edr_b_clean = build_edr(
            keys,
            scope=EnterpriseScope.AGENT_FLEET_ENVELOPE_OVERLAY.value,
        )
        assert edr_b_clean["template_envelope_hash"] == edr_a["template_envelope_hash"]
        edr_b = transplant_signatures(edr_a, edr_b_clean)
        # Sanity: the transplanted signatures ARE EDR-A's, byte-for-byte.
        assert edr_b["signatures"] == edr_a["signatures"]
        assert edr_b["scope"] != edr_a["scope"]

        with pytest.raises(EnterpriseDeploymentRecordInvalidError):
            await verifier.verify(edr_b)

    async def test_employee_principal_mutated_transplant_is_refused(self) -> None:
        # EDR-A: legitimately dual-signed for employee Jane.
        keys = await mint_edr_keys()
        verifier = await self._verifier(keys)
        edr_a = build_edr(keys)
        await verifier.verify(edr_a)

        # A DIFFERENT employee's Genesis key.
        from kailash.trust.key_manager import InMemoryKeyManager

        other = InMemoryKeyManager()
        _priv, other_pubkey = await other.generate_keypair("other-employee")

        # EDR-B: same envelope hash, affected-employee principal SWAPPED to the
        # other employee, carrying EDR-A's signatures verbatim.
        edr_b_clean = build_edr(keys, employee_public_key_hex=other_pubkey)
        assert edr_b_clean["template_envelope_hash"] == edr_a["template_envelope_hash"]
        edr_b = transplant_signatures(edr_a, edr_b_clean)
        assert edr_b["signatures"] == edr_a["signatures"]
        assert (
            edr_b["affected_employee_principal"]["public_key_hex"]
            != edr_a["affected_employee_principal"]["public_key_hex"]
        )

        with pytest.raises(EnterpriseDeploymentRecordInvalidError):
            await verifier.verify(edr_b)

    async def test_original_edr_a_still_verifies(self) -> None:
        # Control: the transplant defense does NOT break a genuine record.
        keys = await mint_edr_keys()
        verifier = await self._verifier(keys)
        record = await verifier.verify(build_edr(keys))
        assert isinstance(record, EnterpriseDeploymentRecord)
        # The harness constant is the shared envelope hash both records reference.
        assert record.template_envelope_hash == TEMPLATE_ENVELOPE_HASH
