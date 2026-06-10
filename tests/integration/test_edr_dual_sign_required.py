# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2: EnterpriseDeploymentRecord is REQUIRED dual-signed.

EC-S8e.2 — a single-signed EDR (org-admin-only OR employee-only) raises
`EnterpriseDualSignMissingError`; a dual-signed EDR is accepted.

Tier 2 per `rules/testing.md`: REAL crypto via the kailash `InMemoryKeyManager`,
no mocking. Structural assertions on the raised type per
`rules/probe-driven-verification.md`.
"""

from __future__ import annotations

import pytest

from envoy.enterprise import (
    EnterpriseDeploymentRecord,
    EnterpriseDeploymentVerifier,
    EnterpriseDualSignMissingError,
)
from tests.helpers.edr_harness import build_edr, mint_edr_keys, reference_now


async def _verifier(keys):
    return EnterpriseDeploymentVerifier(
        key_manager=keys.key_manager,
        known_org_roots=keys.known_org_roots,
        now=reference_now,
    )


class TestDualSignRequired:
    async def test_org_admin_only_signature_raises_dual_sign_missing(self) -> None:
        # Org admin signed; employee did NOT → dual-sign gate refuses.
        keys = await mint_edr_keys(sign_employee=False)
        verifier = await _verifier(keys)
        edr = build_edr(keys, affected_employee_signature_hex="")
        with pytest.raises(EnterpriseDualSignMissingError):
            await verifier.verify(edr)

    async def test_employee_only_signature_raises_dual_sign_missing(self) -> None:
        # Employee signed; org admin did NOT → dual-sign gate refuses.
        keys = await mint_edr_keys(sign_org_admin=False)
        verifier = await _verifier(keys)
        edr = build_edr(keys, org_admin_signature_hex="")
        with pytest.raises(EnterpriseDualSignMissingError):
            await verifier.verify(edr)

    async def test_neither_signature_raises_dual_sign_missing(self) -> None:
        # No signature at all is also a dual-sign failure (neither party attested).
        keys = await mint_edr_keys(sign_org_admin=False, sign_employee=False)
        verifier = await _verifier(keys)
        edr = build_edr(keys, org_admin_signature_hex="", affected_employee_signature_hex="")
        with pytest.raises(EnterpriseDualSignMissingError):
            await verifier.verify(edr)

    async def test_dual_signed_edr_is_accepted(self) -> None:
        # Both parties signed → the EDR is accepted (returns the parsed record).
        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        record = await verifier.verify(build_edr(keys))
        assert isinstance(record, EnterpriseDeploymentRecord)
        assert record.org_admin_signature_hex
        assert record.affected_employee_signature_hex
