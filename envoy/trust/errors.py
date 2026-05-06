"""Typed errors for envoy.trust.

Per `specs/trust-lineage.md` § Error taxonomy + `rules/tenant-isolation.md`
Rule 2 (PrincipalRequiredError). Errors emitted on the trust-store path MUST
NOT echo raw secrets / vault contents / private keys (PII + secret-leakage
defense per `rules/security.md`).
"""

from __future__ import annotations


class TrustStoreError(Exception):
    """Base class for every trust-store error."""

    def __init__(self, message: str, *, principal_id: str | None = None) -> None:
        super().__init__(message)
        self.principal_id = principal_id


class PrincipalRequiredError(TrustStoreError):
    """Raised when a TrustStoreAdapter operation is invoked without a principal_id.

    Per `rules/tenant-isolation.md` Rule 2: every operation that touches
    per-principal state MUST require principal_id explicitly. Defaulting to
    "default" or "" is BLOCKED — silent merging of multi-tenant data into a
    shared slot is the failure mode this error prevents.
    """


class GenesisAlreadySeededError(TrustStoreError):
    """Raised when seed_genesis() is called for a principal_id that already has Genesis.

    Genesis is the cryptographic root of the principal's trust lineage; re-seeding
    would silently invalidate every descendant DelegationRecord. The fix is
    cascade revocation (envoy.trust.cascade — Wave 1 T-01-14), not re-seeding.
    """


class TrustChainNotFoundError(TrustStoreError):
    """Raised when get_chain() finds no chain for the given principal_id.

    Wraps `kailash.trust.exceptions.TrustChainNotFoundError` so envoy callers
    catch the envoy-side hierarchy.
    """
