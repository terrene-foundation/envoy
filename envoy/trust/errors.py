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


# ---------------------------------------------------------------------------
# Trust Vault errors (T-01-13) — mirror specs/trust-vault.md § Error taxonomy.
# Phase 01 covers a subset; Phase 02+ extends with duress / shadow-segment /
# key-destruction errors as those features ship.
# ---------------------------------------------------------------------------


class VaultError(TrustStoreError):
    """Base class for every vault-touching error.

    Per `rules/security.md` § "No secrets in logs", error messages MUST NOT
    echo passphrases, derived keys, or plaintext region content.
    """


class VaultLockedError(VaultError):
    """Raised when a vault-touching operation fires while the vault is locked.

    Every TrustStoreAdapter method that reads/writes the vault region MUST
    check `vault.is_unlocked` and raise this error if the vault is sealed.
    Callers re-unlock via `await vault.unlock(passphrase)` per
    `specs/trust-vault.md` § Error taxonomy `AutoLockIdleTimeoutError`.
    """


class VaultUnlockFailedError(VaultError):
    """Raised when passphrase Argon2id derivation produces a key that fails
    AES-256-GCM tag verification (i.e., wrong passphrase).

    Per `specs/trust-vault.md` § Error taxonomy: re-enter passphrase; if
    persistent, run Shamir recovery (T-15 ShamirRitualCoordinator).
    """


class VaultMACVerificationFailedError(VaultError):
    """Raised when the outer AES-256-GCM tag verification fails on a vault that
    SHOULD decrypt cleanly (i.e., file-level tamper or container corruption,
    not wrong passphrase).

    Per `specs/trust-vault.md` § Error taxonomy: refuse unlock; restore from
    backup or run Shamir recovery. Distinguishes file-level corruption from
    passphrase-mismatch — the verifier (shard 7) treats this as evidence of
    targeted tamper.
    """


class Argon2ParameterMismatchError(VaultError):
    """Raised when stored vault Argon2id parameters (m, t, p) differ from the
    binary's expected values (m=2^17, t=3, p=1).

    Phase 01 hard-codes the canonical parameters. A vault file with different
    parameters MUST NOT be silently re-derived — the Foundation publishes
    parameter migrations explicitly. Per `specs/trust-vault.md` § Error
    taxonomy: run vault migration; backup before.
    """


class AutoLockIdleTimeoutError(VaultError):
    """Raised by a vault-touching operation that fires AFTER the idle-lock timer
    has fired and re-sealed the vault.

    Per `specs/trust-vault.md` § Memory hygiene "Auto-lock after 15min idle";
    the operation MUST re-unlock before retrying. Distinct from
    `VaultLockedError` (vault was already locked) — this signals "vault was
    unlocked, then auto-locked between this operation's start and access".
    """


class MasterKeySizeError(VaultError):
    """Raised when `import_master_key_from_shamir()` receives bytes that are
    not exactly the 32-byte AES-256 key shape.

    Per `specs/shamir-recovery.md` § Recovery flow: Shamir reconstruction
    produces the SAME 32-byte master key the original Argon2id would have
    derived. Anything else is corruption — refuse the import rather than
    silently truncate / pad to fit.
    """


# ---------------------------------------------------------------------------
# Cascade revocation errors (T-01-14) — mirror specs/trust-lineage.md
# § Cascade revocation contract (BFS walker + snapshot-and-rollback).
# ---------------------------------------------------------------------------


class RevocationError(TrustStoreError):
    """Base class for cascade-revocation errors emitted by the Envoy adapter."""


class RevocationNotFoundError(RevocationError):
    """Raised when `verify_cascade_complete(revocation_id=...)` is called with
    a revocation_id that no prior `revoke()` call produced.

    Phase 01 caches the latest RevocationResult per principal_id keyed by
    revocation_id; lookup miss = the caller is asking about a revocation
    this adapter never executed (test artifact, off-by-one principal,
    forged revocation_id).
    """


class CascadeIncompleteError(RevocationError):
    """Raised when `verify_cascade_complete()` finds a descendant in the
    Trust Lineage's chain_parent_id graph that is NOT in the
    `RevocationResult.revoked_agents` set.

    This is the EC-8 cross-channel-cascade defense per shard 5 § 3.3 — a
    malformed delegation_registry that under-reports descendants would
    silently leave a Day-6 child grant alive after the Day-1 root was
    revoked. The verifier reports the gap so the caller can re-revoke
    explicitly.
    """
