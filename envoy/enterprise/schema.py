# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.enterprise.schema — EnterpriseDeploymentRecord schema + CLOSED scope enum.

Mirrors `specs/enterprise-deployment.md` § EnterpriseDeploymentRecord schema
verbatim. The schema is `edr/1.0`; `scope` is a CLOSED enum (`EnterpriseScope`)
— any value outside the three members is rejected at parse time with
`EnterpriseScopeMismatchError`, never silently coerced (`rules/zero-tolerance.md`
Rule 3 — no silent fallback).

`EnterpriseDeploymentRecord.from_dict` is the single parse boundary: it raises
`EnterpriseDeploymentRecordInvalidError` for a wrong `type` / `schema_version` /
missing-required-field / malformed-principal, `EnterpriseScopeMismatchError` for
a scope outside the closed enum, and `EnterpriseDualSignMissingError` for a
record carrying exactly one of the two required signatures. Construction never
returns a partially-populated record.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from envoy.enterprise.errors import (
    EnterpriseDeploymentRecordInvalidError,
    EnterpriseDualSignMissingError,
    EnterpriseScopeMismatchError,
)
from envoy.envelope.canonical_bytes import canonical_bytes, content_hash

EDR_TYPE = "EnterpriseDeploymentRecord"
EDR_SCHEMA_VERSION = "edr/1.0"


class EnterpriseScope(enum.Enum):
    """The CLOSED scope enum (`specs/enterprise-deployment.md` § Scope closed enum).

    Any value outside these three members is rejected — `from_value` raises
    `EnterpriseScopeMismatchError` rather than returning a default member.
    """

    EMPLOYEE_PERSONAL_ENVELOPE_OVERLAY = "employee-personal-envelope-overlay"
    HOUSEHOLD_MEMBER_ENVELOPE_OVERLAY = "household-member-envelope-overlay"
    AGENT_FLEET_ENVELOPE_OVERLAY = "agent-fleet-envelope-overlay"

    @classmethod
    def from_value(cls, value: Any) -> EnterpriseScope:
        """Resolve a wire `scope` string to a member, or raise on any other value.

        Closed-enum membership is verifier step 4
        (`specs/enterprise-deployment.md` § Verification step 4). A non-`str` or
        an out-of-enum string is an `EnterpriseScopeMismatchError`, never a
        silent fall-through to a default scope.
        """
        if not isinstance(value, str):
            raise EnterpriseScopeMismatchError(
                f"scope must be a string drawn from the closed enum; got " f"{type(value).__name__}"
            )
        for member in cls:
            if member.value == value:
                return member
        raise EnterpriseScopeMismatchError(
            f"scope {value!r} is outside the closed enum " f"{{{', '.join(m.value for m in cls)}}}"
        )


@dataclass(frozen=True)
class EnterprisePrincipal:
    """A signing principal block (`deploying_principal` / `affected_employee_principal`).

    `address` is the PACT address; `public_key_hex` is the principal's Ed25519
    public key the corresponding signature verifies against.
    """

    address: str
    public_key_hex: str

    @classmethod
    def from_dict(cls, raw: Any, *, field_name: str) -> EnterprisePrincipal:
        if not isinstance(raw, dict):
            raise EnterpriseDeploymentRecordInvalidError(
                f"{field_name} must be an object with 'address' + 'public_key_hex'"
            )
        address = raw.get("address")
        public_key_hex = raw.get("public_key_hex")
        if not isinstance(address, str) or not address:
            raise EnterpriseDeploymentRecordInvalidError(
                f"{field_name}.address must be a non-empty PACT address string"
            )
        if not isinstance(public_key_hex, str) or not public_key_hex:
            raise EnterpriseDeploymentRecordInvalidError(
                f"{field_name}.public_key_hex must be a non-empty hex string"
            )
        return cls(address=address, public_key_hex=public_key_hex)


@dataclass(frozen=True)
class EnterpriseDeploymentRecord:
    """A parsed, structurally-valid EnterpriseDeploymentRecord (`edr/1.0`).

    Construction via `from_dict` guarantees: `type == EnterpriseDeploymentRecord`,
    `schema_version == edr/1.0`, both principal blocks present and well-formed,
    `scope` inside the closed enum, and BOTH required signatures present (a
    single-signed record raises `EnterpriseDualSignMissingError` at parse time).
    Semantic verification (known org root, signature validity, freshness window,
    algorithm compatibility) is the verifier's job — see `verifier.py`.
    """

    org_genesis_hash: str
    org_id: str
    deploying_principal: EnterprisePrincipal
    affected_employee_principal: EnterprisePrincipal
    template_envelope_hash: str
    template_envelope_ref: str
    enabled_at: str
    scope: EnterpriseScope
    verification_algorithm: str
    org_admin_signature_hex: str
    affected_employee_signature_hex: str

    def signing_payload(self) -> str:
        """The canonical digest BOTH the org admin and the employee sign over.

        Binds the FULL security-relevant field set — everything EXCEPT the
        `signatures` block — so a signature cannot be transplanted from one EDR
        onto another that shares only the `template_envelope_hash`. The digest
        covers `type`, `schema_version`, `org_genesis_hash`, `org_id`, both
        principal blocks (`address` + `public_key_hex`), `template_envelope_hash`,
        `template_envelope_ref`, `enabled_at`, `scope`, and
        `verification_algorithm`. Mutating ANY of these (e.g. widening `scope`
        from employee-personal to agent-fleet, or swapping the affected-employee
        principal) changes the digest, so the transplanted signature no longer
        verifies (transplant defense — E-1).

        REUSES the shared `envoy.envelope.canonical_bytes` JCS+NFC pipeline (the
        same canonicalization the Envelope Library + Ledger use) — there is NO
        parallel canonicalization implementation here. The `scope` enum is
        rendered as its wire `.value` string so the payload is plain-JSON-able and
        byte-identical to what an offline signer canonicalizes.
        """
        canonical_record = {
            "type": EDR_TYPE,
            "schema_version": EDR_SCHEMA_VERSION,
            "org_genesis_hash": self.org_genesis_hash,
            "org_id": self.org_id,
            "deploying_principal": {
                "address": self.deploying_principal.address,
                "public_key_hex": self.deploying_principal.public_key_hex,
            },
            "affected_employee_principal": {
                "address": self.affected_employee_principal.address,
                "public_key_hex": self.affected_employee_principal.public_key_hex,
            },
            "template_envelope_hash": self.template_envelope_hash,
            "template_envelope_ref": self.template_envelope_ref,
            "enabled_at": self.enabled_at,
            "scope": self.scope.value,
            "verification_algorithm": self.verification_algorithm,
        }
        return content_hash(canonical_bytes(canonical_record))

    @classmethod
    def from_dict(cls, raw: Any) -> EnterpriseDeploymentRecord:
        """Parse + structurally validate a wire EDR. Raises on any malformation.

        Raises:
            EnterpriseDeploymentRecordInvalidError: wrong `type`, unsupported
                `schema_version`, missing/empty required scalar field, or
                malformed principal block.
            EnterpriseScopeMismatchError: `scope` outside the closed enum.
            EnterpriseDualSignMissingError: exactly one of the two required
                signatures present.
        """
        if not isinstance(raw, dict):
            raise EnterpriseDeploymentRecordInvalidError(
                "EnterpriseDeploymentRecord must be a JSON object"
            )

        record_type = raw.get("type")
        if record_type != EDR_TYPE:
            raise EnterpriseDeploymentRecordInvalidError(
                f"type must be {EDR_TYPE!r}; got {record_type!r}"
            )

        schema_version = raw.get("schema_version")
        if schema_version != EDR_SCHEMA_VERSION:
            # schema_version drift is an explicit § Error taxonomy trigger for
            # EnterpriseDeploymentRecordInvalidError.
            raise EnterpriseDeploymentRecordInvalidError(
                f"schema_version must be {EDR_SCHEMA_VERSION!r}; got "
                f"{schema_version!r} (schema_version drift)"
            )

        deploying_principal = EnterprisePrincipal.from_dict(
            raw.get("deploying_principal"), field_name="deploying_principal"
        )
        affected_employee_principal = EnterprisePrincipal.from_dict(
            raw.get("affected_employee_principal"),
            field_name="affected_employee_principal",
        )

        # Scope is validated against the CLOSED enum BEFORE the dual-sign check
        # so a structurally-invalid scope surfaces as the scope error, not a
        # signature error.
        scope = EnterpriseScope.from_value(raw.get("scope"))

        org_genesis_hash = _require_nonempty_str(raw, "org_genesis_hash")
        org_id = _require_nonempty_str(raw, "org_id")
        template_envelope_hash = _require_nonempty_str(raw, "template_envelope_hash")
        template_envelope_ref = _require_nonempty_str(raw, "template_envelope_ref")
        enabled_at = _require_nonempty_str(raw, "enabled_at")
        verification_algorithm = _require_nonempty_str(raw, "verification_algorithm")

        signatures = raw.get("signatures")
        if not isinstance(signatures, dict):
            raise EnterpriseDeploymentRecordInvalidError(
                "signatures must be an object carrying org_admin_signature_hex "
                "and affected_employee_signature_hex"
            )
        raw_org_admin_sig = signatures.get("org_admin_signature_hex")
        raw_employee_sig = signatures.get("affected_employee_signature_hex")
        org_admin_present = isinstance(raw_org_admin_sig, str) and bool(raw_org_admin_sig)
        employee_present = isinstance(raw_employee_sig, str) and bool(raw_employee_sig)

        # REQUIRED dual-signed: both signatures MUST be present non-empty strings.
        # Exactly-one-present is the dual-sign gap; both absent is also a
        # dual-sign failure (no party attested at all).
        if not (org_admin_present and employee_present):
            which_present = (
                "org-admin only"
                if org_admin_present
                else ("employee only" if employee_present else "neither")
            )
            raise EnterpriseDualSignMissingError(
                "EnterpriseDeploymentRecord is REQUIRED dual-signed; both "
                "org_admin_signature_hex and affected_employee_signature_hex "
                f"must be present (present: {which_present})"
            )
        # Past the guard both are non-empty `str` (narrowed for the typed fields).
        assert isinstance(raw_org_admin_sig, str)
        assert isinstance(raw_employee_sig, str)
        org_admin_sig = raw_org_admin_sig
        employee_sig = raw_employee_sig

        return cls(
            org_genesis_hash=org_genesis_hash,
            org_id=org_id,
            deploying_principal=deploying_principal,
            affected_employee_principal=affected_employee_principal,
            template_envelope_hash=template_envelope_hash,
            template_envelope_ref=template_envelope_ref,
            enabled_at=enabled_at,
            scope=scope,
            verification_algorithm=verification_algorithm,
            org_admin_signature_hex=org_admin_sig,
            affected_employee_signature_hex=employee_sig,
        )


def _require_nonempty_str(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value:
        raise EnterpriseDeploymentRecordInvalidError(f"{field} must be a non-empty string")
    return value


__all__ = [
    "EDR_SCHEMA_VERSION",
    "EDR_TYPE",
    "EnterpriseDeploymentRecord",
    "EnterprisePrincipal",
    "EnterpriseScope",
]
