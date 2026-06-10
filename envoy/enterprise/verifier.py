# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.enterprise.verifier — the 6-step EnterpriseDeploymentRecord verifier.

Runs at envelope-import time (`specs/enterprise-deployment.md` § Verification).
Each of the six steps is fail-closed: a failed step raises the mapped error from
`envoy.enterprise.errors` rather than returning a default
(`rules/zero-tolerance.md` Rule 3).

The six steps, in order:

  1. `org_genesis_hash` resolves to a known org Trust Lineage root.
  2. deploying-principal signature valid against the org Trust Lineage root.
  3. affected-employee signature valid against the employee's Genesis.
  4. `scope` in the closed enum.
  5. `enabled_at` within 365 days (annual re-attestation).
  6. `verification_algorithm` current-session-compatible OR migration-compatible.

Load-bearing reuse (EC-S8e.4): steps 2 + 3 route the Ed25519 signature check
through the SHARED `envoy.registry.steward_quorum.verify_steward_quorum` — the
single 2-of-N verify primitive built once per the WS-4 cross-cut. For an EDR
each signature is a SINGLE pinned key, so the call is `threshold=1` with a
one-key pinned set. This is NOT a second verify implementation; it is the same
helper invoked with a 1-of-1 quorum (`grep -rc "def verify_steward_quorum(" .`
stays 1).

Injected trust anchors (open design — see module-level constructor docs):
  - `known_org_roots`: maps `org_genesis_hash -> org_trust_lineage_root_pubkey_hex`.
    Step 1 resolves the hash through this map; an absent hash is an unknown root.
    The resolved pubkey is the trust anchor step 2 verifies the deploying-
    principal signature against (NOT the `deploying_principal.public_key_hex` in
    the record — a self-asserted key would defeat the lineage check).
  - `revocation_list`: optional set of revoked pubkeys (subtractive hard-fail,
    inherited from the shared quorum verifier's revocation semantics).
  - `current_compatible_algorithms` / `migration_compatible_algorithms`: the two
    algorithm sets step 6 tests membership against. Defaults: current
    `{"ed25519"}`, migration empty.
  - `now`: a zero-arg callable returning the current `datetime` (injected so the
    365-day window in step 5 is deterministic under test — no wall-clock
    assertion per `rules/testing.md`).

The signed payload for BOTH signatures is `template_envelope_hash` — the
canonical artifact both the org admin and the affected employee attest to
deploying. Both signatures are Ed25519 over `template_envelope_hash.encode()`,
matching the `verify_steward_quorum` `content_hash` contract.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from envoy.enterprise.errors import (
    EnterpriseAlgorithmMigrationRequiredError,
    EnterpriseDeploymentRecordInvalidError,
    EnterpriseModeRevokedError,
)
from envoy.enterprise.schema import EnterpriseDeploymentRecord
from envoy.registry.errors import StewardQuorumError, StewardQuorumInputError
from envoy.registry.steward_quorum import verify_steward_quorum

# Annual re-attestation window (`specs/enterprise-deployment.md` § Verification
# step 5 — `enabled_at` within 365 days).
REATTESTATION_WINDOW_DAYS = 365

# Default current-session-compatible algorithm set. The schema declares
# `verification_algorithm: "ed25519"`, and the shared quorum verifier verifies
# Ed25519 — so `ed25519` is the sole current default. Migration-compatible
# algorithms are injected by the caller (empty by default).
_DEFAULT_CURRENT_ALGORITHMS = frozenset({"ed25519"})


class _VerifyKeyManager(Protocol):
    """The single async-verify surface the verifier forwards to the quorum helper.

    Matches `kailash.trust.key_manager.InMemoryKeyManager.verify` — the same
    surface `verify_steward_quorum` consumes.
    """

    async def verify(self, payload: Any, signature: str, public_key: str) -> bool: ...


class EnterpriseDeploymentVerifier:
    """Verify an EnterpriseDeploymentRecord at envelope-import time.

    Holds the injected trust anchors (known org Trust Lineage roots, the
    algorithm sets, the clock) and the kailash key manager used for the Ed25519
    signature checks. `verify` runs the six fail-closed steps in spec order and
    returns the parsed `EnterpriseDeploymentRecord` on success.
    """

    def __init__(
        self,
        *,
        key_manager: _VerifyKeyManager,
        known_org_roots: Mapping[str, str],
        revocation_list: Iterable[str] | None = None,
        current_compatible_algorithms: Iterable[str] | None = None,
        migration_compatible_algorithms: Iterable[str] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._key_manager = key_manager
        # Copy the injected map so a later caller mutation cannot retro-change the
        # known-roots trust anchor mid-flight.
        self._known_org_roots = dict(known_org_roots)
        self._revocation_list = set(revocation_list or ())
        self._current_algorithms = (
            frozenset(current_compatible_algorithms)
            if current_compatible_algorithms is not None
            else _DEFAULT_CURRENT_ALGORITHMS
        )
        self._migration_algorithms = frozenset(migration_compatible_algorithms or ())
        # Default clock is timezone-aware UTC; injected for deterministic tests.
        self._now = now if now is not None else (lambda: datetime.now(timezone.utc))

    async def verify(self, raw_record: Any) -> EnterpriseDeploymentRecord:
        """Run the six fail-closed verifier steps; return the parsed record.

        `raw_record` may be a wire dict or an already-parsed
        `EnterpriseDeploymentRecord`. Parsing (which enforces schema_version,
        closed-enum scope, and the REQUIRED dual-sign gate) happens first; the
        six steps then run in spec order.

        Raises:
            EnterpriseDeploymentRecordInvalidError: steps 1-3 (unknown org root,
                invalid org-admin or employee signature) + schema malformation.
            EnterpriseScopeMismatchError: step 4 (scope outside the closed enum;
                raised during parse).
            EnterpriseDualSignMissingError: single-signed record (raised during
                parse).
            EnterpriseModeRevokedError: step 5 (`enabled_at` older than 365 days).
            EnterpriseAlgorithmMigrationRequiredError: step 6 (algorithm outside
                current + migration sets).
        """
        record = (
            raw_record
            if isinstance(raw_record, EnterpriseDeploymentRecord)
            else EnterpriseDeploymentRecord.from_dict(raw_record)
        )
        # Step 4 (scope in closed enum) is enforced structurally during parse —
        # an out-of-enum scope never reaches here (EnterpriseScopeMismatchError
        # raised in EnterpriseDeploymentRecord.from_dict). Steps 1-3, 5, 6 below.

        org_root_pubkey = self._step1_resolve_org_root(record)
        await self._step2_verify_deploying_signature(record, org_root_pubkey)
        await self._step3_verify_employee_signature(record)
        self._step5_check_reattestation_window(record)
        self._step6_check_algorithm_compatibility(record)
        return record

    def _step1_resolve_org_root(self, record: EnterpriseDeploymentRecord) -> str:
        """Step 1 — `org_genesis_hash` resolves to a known org Trust Lineage root."""
        org_root_pubkey = self._known_org_roots.get(record.org_genesis_hash)
        if not org_root_pubkey:
            raise EnterpriseDeploymentRecordInvalidError(
                f"org_genesis_hash {record.org_genesis_hash!r} does not resolve "
                "to a known org Trust Lineage root"
            )
        return org_root_pubkey

    async def _step2_verify_deploying_signature(
        self, record: EnterpriseDeploymentRecord, org_root_pubkey: str
    ) -> None:
        """Step 2 — deploying-principal signature valid against org Trust Lineage.

        Verified against the org Trust Lineage ROOT pubkey resolved in step 1 —
        NOT the self-asserted `deploying_principal.public_key_hex` (verifying
        against a record-supplied key would let any principal claim org
        authority). Routed through the shared 1-of-1 `verify_steward_quorum`.
        """
        await self._verify_single_signature(
            content_hash=record.template_envelope_hash,
            signature_hex=record.org_admin_signature_hex,
            pinned_pubkey=org_root_pubkey,
            failure_detail="deploying-principal signature does not verify against "
            "the org Trust Lineage root",
        )

    async def _step3_verify_employee_signature(self, record: EnterpriseDeploymentRecord) -> None:
        """Step 3 — affected-employee signature valid against employee's Genesis.

        The employee's Genesis public key is carried in the record's
        `affected_employee_principal.public_key_hex`; the employee signs the
        same `template_envelope_hash`. Routed through the shared 1-of-1
        `verify_steward_quorum`.
        """
        await self._verify_single_signature(
            content_hash=record.template_envelope_hash,
            signature_hex=record.affected_employee_signature_hex,
            pinned_pubkey=record.affected_employee_principal.public_key_hex,
            failure_detail="affected-employee signature does not verify against "
            "the employee's Genesis key",
        )

    async def _verify_single_signature(
        self,
        *,
        content_hash: str,
        signature_hex: str,
        pinned_pubkey: str,
        failure_detail: str,
    ) -> None:
        """Reuse the SHARED quorum verifier as a 1-of-1 single-key check.

        EC-S8e.4: there is exactly one quorum/verify implementation in the tree.
        A single-key EDR signature is a 1-of-1 quorum — `threshold=1`, a one-key
        pinned set, the shared revocation list. A failed quorum (no valid pinned
        signer, or a revoked key) maps to the EDR taxonomy as a record-invalid
        signature refusal.
        """
        try:
            await verify_steward_quorum(
                1,
                content_hash,
                [{"steward_pubkey_hex": pinned_pubkey, "signature_hex": signature_hex}],
                {pinned_pubkey},
                self._revocation_list,
                key_manager=self._key_manager,
            )
        except (StewardQuorumError, StewardQuorumInputError) as exc:
            # Both the verdict failure (StewardQuorumError) and the degenerate
            # input bound (StewardQuorumInputError) map to a record-invalid
            # signature refusal — the EDR is not importable. Chain the cause but
            # do NOT echo signature material (log-poisoning hygiene).
            raise EnterpriseDeploymentRecordInvalidError(failure_detail) from exc

    def _step5_check_reattestation_window(self, record: EnterpriseDeploymentRecord) -> None:
        """Step 5 — `enabled_at` within 365 days (annual re-attestation)."""
        enabled_at = _parse_iso8601(record.enabled_at)
        now = self._now()
        # Compare in a common awareness: if the parsed timestamp is naive, treat
        # `now` as naive too (both UTC); the injected clock is timezone-aware by
        # default so a tz-aware enabled_at compares directly.
        if enabled_at.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        elif enabled_at.tzinfo is not None and now.tzinfo is None:
            enabled_at = enabled_at.replace(tzinfo=None)
        age = now - enabled_at
        if age > timedelta(days=REATTESTATION_WINDOW_DAYS):
            raise EnterpriseModeRevokedError(
                f"enabled_at {record.enabled_at!r} is older than "
                f"{REATTESTATION_WINDOW_DAYS} days (annual re-attestation "
                "expired); org admin must re-issue the EDR"
            )

    def _step6_check_algorithm_compatibility(self, record: EnterpriseDeploymentRecord) -> None:
        """Step 6 — `verification_algorithm` current OR migration compatible."""
        algorithm = record.verification_algorithm
        if (
            algorithm not in self._current_algorithms
            and algorithm not in self._migration_algorithms
        ):
            raise EnterpriseAlgorithmMigrationRequiredError(
                f"verification_algorithm {algorithm!r} is in neither the "
                "current-session-compatible nor the migration-compatible set; "
                "org admin must re-issue under a migration-allowlisted algorithm"
            )


def _parse_iso8601(value: str) -> datetime:
    """Parse an ISO-8601 timestamp (accepts a trailing `Z` as UTC).

    A malformed `enabled_at` is a structurally-invalid record — raises
    `EnterpriseDeploymentRecordInvalidError` rather than letting `ValueError`
    propagate opaquely.
    """
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EnterpriseDeploymentRecordInvalidError(
            f"enabled_at {value!r} is not a valid ISO-8601 timestamp"
        ) from exc


__all__ = [
    "REATTESTATION_WINDOW_DAYS",
    "EnterpriseDeploymentVerifier",
]
