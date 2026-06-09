# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.registry — typed errors for the Foundation registry surface.

The Foundation registry family (Envelope Library #1, classifier registry #6,
migration-allowlist #7 — all under `envoy-registry:*`) shares ONE 2-of-N
steward-quorum verifier (`verify_steward_quorum`). That verifier raises a
single *base* error, `StewardQuorumError`, with a structured `reason` so each
consumer maps it to its OWN spec taxonomy:

- Envelope Library FV resolver maps to `FVTierMembershipNotProvenError` /
  `PublisherSignatureInvalidError` / `TemplateHashMismatchError`
  (`specs/envelope-library.md` § Error taxonomy).
- The classifier registry resolver (S9b) maps to `RegistryThresholdNotMetError`
  / `RegistrySignatureMismatchError` / `RegistryArtifactHashMismatchError` /
  `RegistryEntryExpiredError` (`specs/foundation-ops.md` § Error taxonomy).

Building the verifier ONCE behind this base error is the §4.5 single-helper
cross-cut: there is exactly one quorum-verify implementation and every consumer
re-maps from the same base. Error messages MUST NOT echo signature material or
raw content (log/exception-poisoning hygiene, matching
`envoy.ledger.keystore`).
"""

from __future__ import annotations

import enum


class StewardQuorumReason(enum.Enum):
    """Why a steward-quorum verification failed.

    The base `StewardQuorumError` carries one of these so a consumer can map to
    its own taxonomy WITHOUT string-matching the message.
    """

    THRESHOLD_NOT_MET = "threshold_not_met"
    """Fewer than `threshold` DISTINCT valid, pinned, non-revoked keys signed."""

    REVOKED_KEY_PRESENT = "revoked_key_present"
    """A signature was made by a key on the revocation list (hard-fail)."""

    NO_PINNED_SIGNERS = "no_pinned_signers"
    """No signature was made by any client-pinned stewardship key."""


class StewardQuorumError(Exception):
    """Base error raised by `verify_steward_quorum` when the quorum is not met.

    Carries a structured `reason` (`StewardQuorumReason`) plus the distinct
    valid-signer count actually achieved (`distinct_valid`) and the required
    `threshold`, so a consumer's taxonomy mapping is structural, not lexical.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: StewardQuorumReason,
        distinct_valid: int,
        threshold: int,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.distinct_valid = distinct_valid
        self.threshold = threshold


class StewardQuorumInputError(ValueError):
    """A malformed input to `verify_steward_quorum` (e.g. threshold < 1, or an
    oversized signature array beyond `MAX_STEWARD_SIGNATURES`).

    Distinct from `StewardQuorumError` — this is a programming error in the
    CALLER (or an untrusted-input bound violation), not a failed-verification
    verdict. Raising rather than returning False prevents a degenerate
    `threshold=0` from silently "passing" and bounds the verify-cost DoS surface
    of an unbounded signature array.
    """


class PublishInputError(ValueError):
    """A malformed / out-of-bounds input to the `library.publish` handler.

    Raised when `template_id` / `version` fail strict charset + length
    validation (null byte, control char, path separator, `..`, leading `.`,
    >256 len, non-`str`) OR `steward_signatures` exceeds `MAX_STEWARD_SIGNATURES`.
    The publish surface is air-gapped-ceremony-only this phase (NOT
    network-writable); this guard hardens it so an unauthenticated / garbage
    publish cannot fill the store or shadow a `template_id@version`.
    """


# --- Envelope Library FV-tier taxonomy (specs/envelope-library.md) ---------


class LibraryError(Exception):
    """Base class for Envelope Library resolver errors."""


class LibraryUnreachableError(LibraryError):
    """Foundation Nexus endpoint unreachable AND no local cache entry.

    `specs/envelope-library.md` § Error taxonomy: surface offline notice; the
    user retries when the network returns.
    """


class TemplateHashMismatchError(LibraryError):
    """Fetched template bytes do not re-hash to the declared `content_hash`.

    `specs/foundation-ops.md` + `specs/envelope-library.md`: suspected
    supply-chain tamper. Never auto-retry.
    """


class PublisherSignatureInvalidError(LibraryError):
    """A claimed FV steward signature does not verify (Ed25519).

    `specs/envelope-library.md` § Error taxonomy: refuse install; surface
    publisher-key-rotation possibility OR potential supply-chain compromise.
    """


class FVTierMembershipNotProvenError(LibraryError):
    """Template claims FV tier but the 2-of-N steward signing chain is incomplete.

    `specs/envelope-library.md` § Error taxonomy: refuse FV-tier rendering.
    This is the consumer-side mapping of `StewardQuorumError`
    (THRESHOLD_NOT_MET / NO_PINNED_SIGNERS) for the Envelope Library FV path.
    """


class StaleOfflineTemplateError(LibraryError):
    """An offline (cached) resolve would serve a SUPERSEDED template version.

    The offline content-addressed cache is keyed by `(id_version, content_hash)`
    and the resolver tracks the highest `published_at` it has ever observed for
    each `id_version`. A cached entry whose `published_at` is OLDER than that
    high-water mark is a pin-rollback: a still-validly-signed but superseded
    version that an offline consumer would otherwise accept with no rollback
    signal. Refuse it — the consumer must reach the network for the current
    version (or pin the expected `content_hash` explicitly).

    `specs/envelope-library.md` § Error taxonomy (offline freshness): distinct
    from `LibraryUnreachableError` (no entry at all) — here an entry EXISTS but
    is known-stale.
    """


class CommunityPublishingDisabledError(LibraryError):
    """Community-tier publish attempted while the tier is frozen (Phase 03).

    `specs/envelope-library.md` Community row: the registry surface is
    SHAPE-present this phase but the publish handler returns a typed refusal.
    Carries the spec phase so the Nexus handler can render an HTTP 503.
    """


__all__ = [
    "CommunityPublishingDisabledError",
    "FVTierMembershipNotProvenError",
    "LibraryError",
    "LibraryUnreachableError",
    "PublishInputError",
    "PublisherSignatureInvalidError",
    "StaleOfflineTemplateError",
    "StewardQuorumError",
    "StewardQuorumInputError",
    "StewardQuorumReason",
    "TemplateHashMismatchError",
]
