"""envoy.shamir typed errors.

Per `specs/shamir-recovery.md` § Error taxonomy. T-02-34 ships only the
errors raised by `ShamirRitualCoordinator` (ritual-orchestration scope).
T-02-35 (paper / commitments / distribution_checklist) and T-02-36
(reconstruct CLI) extend this set with the recovery-side taxonomy
(`ShardChecksumFailedError`, `CommitmentVerificationFailedError`,
`RecoveryRateLimitedError`, etc.).

Per `rules/communication.md`, every error carries a plain-language
`.user_message` attribute that the channel adapters render directly.
"""

from __future__ import annotations


class ShamirRitualError(Exception):
    """Base class for ShamirRitualCoordinator-side errors.

    Every subclass MUST set `.user_message` to a plain-language string
    suitable for direct rendering through any channel adapter
    (CLI / Telegram / Slack / Discord / etc.) per
    `rules/communication.md` MUST NOT (raw error messages).
    """

    user_message: str = ""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        if user_message is not None:
            self.user_message = user_message


class RitualPreconditionError(ShamirRitualError):
    """Ritual cannot run — caller-side precondition violated.

    Examples (raised at `run_first_time_ritual` entry):
    - threshold < 2 or threshold > total_shards
    - total_shards < 2 or total_shards > 16 (SLIP-0039 group limit)
    - master-key bytes are wrong size (not 32) or empty

    The ritual NEVER reaches `kailash.trust.vault.shamir.generate(...)`
    when this error fires — fail-loud at validation, before any
    collaborator side-effect.
    """


class MasterKeyZeroizationError(ShamirRitualError):
    """The post-generate zeroize step failed.

    This is a non-recoverable state for the running coordinator: the
    master key may still be resident in the Python heap, and the ritual
    has already produced shards that callers may have started to
    persist. The error MUST be raised loudly so the operator can take
    follow-up action (lock + restart the vault host process).

    Per `rules/trust-plane-security.md` MUST NOT Rule 3 (Private Key
    Material in Memory): zeroize is the structural defense; failing it
    silently would leave key bytes resident across the entire process
    lifetime.
    """


__all__ = [
    "ShamirRitualError",
    "RitualPreconditionError",
    "MasterKeyZeroizationError",
]
