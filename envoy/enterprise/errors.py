# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.enterprise.errors — typed errors for the EnterpriseDeploymentRecord verifier.

Every error here is an IMPORT-TIME refusal: the EDR verifier runs at
envelope-import time (`specs/enterprise-deployment.md` § Verification) and each
failure path raises the mapped error rather than returning a default. Fail-closed
per `rules/zero-tolerance.md` Rule 3 — no silent fallbacks, every failure path is
a typed raise.

Taxonomy mapping (`specs/enterprise-deployment.md` § Error taxonomy):

- `EnterpriseDeploymentRecordInvalidError` — the EDR fails ANY verifier step
  whose root cause is "the record itself is invalid": unknown org_genesis_hash,
  an invalid signature (org-admin or employee), schema_version drift, or a
  structurally malformed record. This is the catch-all import-time refusal.
- `EnterpriseDualSignMissingError` — the EDR carries one signature but not the
  other (org-admin present, employee absent — or vice versa). Distinct from
  `...RecordInvalidError` because BOTH parties must sign before the record is
  even eligible for the six verifier steps.
- `EnterpriseModeRevokedError` — `enabled_at` is older than 365 days (annual
  re-attestation expired). The record was once valid; it has aged out.
- `EnterpriseAlgorithmMigrationRequiredError` — `verification_algorithm` is
  outside the current-session-compatible AND migration-compatible sets.
- `EnterpriseScopeMismatchError` — `scope` is outside the closed enum.

Error messages MUST NOT echo signature material or raw key bytes
(log/exception-poisoning hygiene, matching `envoy.registry.errors` +
`rules/observability.md` Rule 4 + `rules/security.md` § "No secrets in logs").
"""

from __future__ import annotations


class EnterpriseDeploymentError(Exception):
    """Base class for every EnterpriseDeploymentRecord verifier error."""


class EnterpriseDeploymentRecordInvalidError(EnterpriseDeploymentError):
    """The EDR fails a verifier step whose root cause is record invalidity.

    Raised for: an `org_genesis_hash` that does not resolve to a known org Trust
    Lineage root (step 1), a deploying-principal signature that does not verify
    against the org Trust Lineage root (step 2), an affected-employee signature
    that does not verify against the employee's Genesis (step 3), a
    `schema_version` other than the supported `edr/1.0`, or a structurally
    malformed record (missing required field, wrong `type`).

    `specs/enterprise-deployment.md` § Error taxonomy: surface failure detail;
    user contacts org admin to re-issue EDR. Never auto-retry.
    """


class EnterpriseDualSignMissingError(EnterpriseDeploymentError):
    """The EDR carries one required signature but not the other.

    Raised when `org_admin_signature_hex` is present but
    `affected_employee_signature_hex` is empty/missing (or vice versa). The EDR
    is REQUIRED dual-signed (`specs/enterprise-deployment.md` schema comment
    `// REQUIRED dual-signed`): a deployment binding both the org and the
    affected employee is only legitimate when BOTH have signed. This is the
    structural defense against the T-024 abuser-IT vector — an org admin cannot
    deploy an enterprise overlay onto an employee without that employee's
    signature.

    `specs/enterprise-deployment.md` § Error taxonomy: both parties must sign;
    refused until dual-signed.
    """


class EnterpriseModeRevokedError(EnterpriseDeploymentError):
    """`enabled_at` is older than the 365-day annual re-attestation window.

    `specs/enterprise-deployment.md` § Error taxonomy: org admin re-issues EDR
    with a current `enabled_at`. The record was once valid; the annual
    re-attestation lapsed.
    """


class EnterpriseAlgorithmMigrationRequiredError(EnterpriseDeploymentError):
    """`verification_algorithm` is in neither the current nor migration set.

    `specs/enterprise-deployment.md` § Error taxonomy: org admin re-issues under
    a migration-allowlisted algorithm. Distinct from `...RecordInvalidError`
    because the record may be otherwise well-formed and validly signed — the
    algorithm itself is simply not one this session can verify under.
    """


class EnterpriseScopeMismatchError(EnterpriseDeploymentError):
    """`scope` is outside the closed enum.

    The scope enum is CLOSED (`specs/enterprise-deployment.md` § Scope closed
    enum — any other value rejected). `specs/enterprise-deployment.md` § Error
    taxonomy: refuse action; org admin issues a new EDR with a correct scope.
    Never auto-retry.
    """


__all__ = [
    "EnterpriseAlgorithmMigrationRequiredError",
    "EnterpriseDeploymentError",
    "EnterpriseDeploymentRecordInvalidError",
    "EnterpriseDualSignMissingError",
    "EnterpriseModeRevokedError",
    "EnterpriseScopeMismatchError",
]
