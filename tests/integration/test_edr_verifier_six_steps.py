# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2: every EnterpriseDeploymentRecord verifier step, green + targeted fail.

EC-S8e.1 — a fully-valid dual-signed EDR passes all 6 steps; each targeted
single-step failure raises its mapped error from `envoy.enterprise.errors`.

Tier 2 per `rules/testing.md`: REAL crypto via the kailash `InMemoryKeyManager`
(no `@patch`/`MagicMock`). Every signature is a real Ed25519 signature; the
365-day window uses an injected deterministic clock (no wall-clock assertion).
Assertions are structural — `pytest.raises(<MappedError>)` — per
`rules/probe-driven-verification.md` (no regex over prose).

`specs/enterprise-deployment.md` § Verification:
  1. org_genesis_hash resolves to a known org Trust Lineage root.
  2. deploying-principal signature valid against org Trust Lineage.
  3. affected-employee signature valid against employee's Genesis.
  4. scope in the closed enum.
  5. enabled_at within 365 days.
  6. verification_algorithm current OR migration compatible.
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.enterprise import (
    EnterpriseAlgorithmMigrationRequiredError,
    EnterpriseDeploymentRecord,
    EnterpriseDeploymentRecordInvalidError,
    EnterpriseDeploymentVerifier,
    EnterpriseModeRevokedError,
    EnterpriseScope,
    EnterpriseScopeMismatchError,
)
from tests.helpers.edr_harness import (
    ORG_GENESIS_HASH,
    TEMPLATE_ENVELOPE_HASH,
    build_edr,
    iso_days_ago,
    mint_edr_keys,
    reference_now,
)


async def _verifier(keys, **overrides):
    """A verifier wired with the scenario's known org root + injected clock."""
    return EnterpriseDeploymentVerifier(
        key_manager=keys.key_manager,
        known_org_roots=keys.known_org_roots,
        now=reference_now,
        **overrides,
    )


class TestGreenPath:
    async def test_fully_valid_dual_signed_edr_passes_all_six_steps(self) -> None:
        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        record = await verifier.verify(build_edr(keys))
        # Returns the parsed record on success (all six steps passed).
        assert isinstance(record, EnterpriseDeploymentRecord)
        assert record.scope is EnterpriseScope.EMPLOYEE_PERSONAL_ENVELOPE_OVERLAY
        assert record.org_genesis_hash == ORG_GENESIS_HASH
        assert record.template_envelope_hash == TEMPLATE_ENVELOPE_HASH

    @pytest.mark.parametrize(
        "scope_value",
        [
            EnterpriseScope.EMPLOYEE_PERSONAL_ENVELOPE_OVERLAY.value,
            EnterpriseScope.HOUSEHOLD_MEMBER_ENVELOPE_OVERLAY.value,
            EnterpriseScope.AGENT_FLEET_ENVELOPE_OVERLAY.value,
        ],
    )
    async def test_every_closed_enum_scope_passes(self, scope_value: str) -> None:
        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        record = await verifier.verify(build_edr(keys, scope=scope_value))
        assert record.scope.value == scope_value


class TestStep1OrgGenesisRoot:
    async def test_unknown_org_genesis_hash_raises_record_invalid(self) -> None:
        # Step 1: org_genesis_hash that resolves to NO known org Trust Lineage
        # root → EnterpriseDeploymentRecordInvalidError.
        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        edr = build_edr(keys, org_genesis_hash="sha256:deadbeef-unknown-root")
        with pytest.raises(EnterpriseDeploymentRecordInvalidError):
            await verifier.verify(edr)


class TestStep2DeployingSignature:
    async def test_org_admin_signature_from_wrong_key_raises_record_invalid(
        self,
    ) -> None:
        # Step 2: a deploying-principal signature that does NOT verify against the
        # org Trust Lineage root (signed by a foreign key) → record invalid.
        keys = await mint_edr_keys()
        foreign = InMemoryKeyManager()
        await foreign.generate_keypair("attacker")
        forged_sig = foreign.sign_with_key("attacker", TEMPLATE_ENVELOPE_HASH.encode("utf-8"))
        verifier = await _verifier(keys)
        edr = build_edr(keys, org_admin_signature_hex=forged_sig)
        with pytest.raises(EnterpriseDeploymentRecordInvalidError):
            await verifier.verify(edr)

    async def test_org_admin_signature_over_wrong_payload_raises_record_invalid(
        self,
    ) -> None:
        # Org root key signs the WRONG payload (a different envelope hash) → the
        # signature does not verify against template_envelope_hash.
        keys = await mint_edr_keys()
        wrong_payload_sig = keys.key_manager.sign_with_key(
            "edr-org-root", b"sha256:some-other-envelope"
        )
        verifier = await _verifier(keys)
        edr = build_edr(keys, org_admin_signature_hex=wrong_payload_sig)
        with pytest.raises(EnterpriseDeploymentRecordInvalidError):
            await verifier.verify(edr)


class TestStep3EmployeeSignature:
    async def test_employee_signature_from_wrong_key_raises_record_invalid(
        self,
    ) -> None:
        # Step 3: an affected-employee signature that does NOT verify against the
        # employee's Genesis key → record invalid.
        keys = await mint_edr_keys()
        foreign = InMemoryKeyManager()
        await foreign.generate_keypair("not-the-employee")
        forged_sig = foreign.sign_with_key(
            "not-the-employee", TEMPLATE_ENVELOPE_HASH.encode("utf-8")
        )
        verifier = await _verifier(keys)
        edr = build_edr(keys, affected_employee_signature_hex=forged_sig)
        with pytest.raises(EnterpriseDeploymentRecordInvalidError):
            await verifier.verify(edr)


class TestStep4ScopeClosedEnum:
    async def test_scope_outside_closed_enum_raises_scope_mismatch(self) -> None:
        # Step 4: scope value outside the closed enum → EnterpriseScopeMismatchError.
        # An out-of-enum scope is a wire-level corruption: build a valid signed
        # EDR, then mutate the wire `scope` string to an unsupported value. The
        # verifier's parse step rejects it before any signature check.
        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        edr = build_edr(keys)
        edr["scope"] = "org-wide-surveillance-overlay"
        with pytest.raises(EnterpriseScopeMismatchError):
            await verifier.verify(edr)


class TestStep5ReattestationWindow:
    async def test_enabled_at_older_than_365_days_raises_revoked(self) -> None:
        # Step 5: enabled_at older than 365 days → EnterpriseModeRevokedError.
        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        edr = build_edr(keys, enabled_at=iso_days_ago(366))
        with pytest.raises(EnterpriseModeRevokedError):
            await verifier.verify(edr)

    async def test_enabled_at_exactly_inside_window_passes(self) -> None:
        # Boundary: 365 days ago is within the window (age == 365d is not > 365d).
        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        record = await verifier.verify(build_edr(keys, enabled_at=iso_days_ago(365)))
        assert isinstance(record, EnterpriseDeploymentRecord)

    @pytest.mark.regression
    async def test_future_dated_enabled_at_raises_record_invalid(self) -> None:
        # Step 5 lower bound: a FUTURE-dated enabled_at (negative days-ago) yields
        # a negative age that would silently pass an upper-bound-only check,
        # letting a forged record post-dating attestation evade expiry. The
        # two-sided window rejects it as EnterpriseDeploymentRecordInvalidError.
        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        # 30 days in the future — well beyond the 5-minute skew tolerance.
        edr = build_edr(keys, enabled_at=iso_days_ago(-30))
        with pytest.raises(EnterpriseDeploymentRecordInvalidError):
            await verifier.verify(edr)

    async def test_enabled_at_within_skew_tolerance_passes(self) -> None:
        # A timestamp a few seconds in the future (benign clock skew) is accepted:
        # it falls within the documented FUTURE_DATED_SKEW_TOLERANCE.
        from datetime import timedelta

        from tests.helpers.edr_harness import REFERENCE_NOW

        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        near_future = (
            (REFERENCE_NOW + timedelta(seconds=30))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        record = await verifier.verify(build_edr(keys, enabled_at=near_future))
        assert isinstance(record, EnterpriseDeploymentRecord)


class TestStep6AlgorithmCompatibility:
    async def test_algorithm_outside_sets_raises_migration_required(self) -> None:
        # Step 6: an algorithm in neither the current nor migration set →
        # EnterpriseAlgorithmMigrationRequiredError. The signatures are still
        # valid Ed25519 (the harness signs ed25519); only the declared algorithm
        # field is out-of-set, so this isolates step 6.
        keys = await mint_edr_keys()
        verifier = await _verifier(keys)
        edr = build_edr(keys, verification_algorithm="rsa-pkcs1-sha1")
        with pytest.raises(EnterpriseAlgorithmMigrationRequiredError):
            await verifier.verify(edr)

    async def test_migration_compatible_algorithm_passes(self) -> None:
        # An algorithm outside the current set BUT inside the injected
        # migration-compatible set passes step 6.
        keys = await mint_edr_keys()
        verifier = await _verifier(keys, migration_compatible_algorithms={"ed25519-legacy"})
        edr = build_edr(keys, verification_algorithm="ed25519-legacy")
        record = await verifier.verify(edr)
        assert record.verification_algorithm == "ed25519-legacy"
