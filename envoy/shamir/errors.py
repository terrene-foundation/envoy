"""envoy.shamir typed errors.

Per `specs/shamir-recovery.md` § Error taxonomy. T-02-34 ships the
errors raised by `ShamirRitualCoordinator` (ritual-orchestration scope).
T-02-35 adds `ChecklistPersisterError`. T-02-36 (recovery CLI) extends
this set with the recovery-side taxonomy: `ShardChecksumFailedError`,
`InsufficientSharesError`, `CommitmentVerificationFailedError`,
`ShardSlotLabelMismatchError`, `ShardPublicCommitmentMissingError`.

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


class EnvoyLabelOnCardError(ShamirRitualError):
    """H-06 violation — the supplied slot label contains 'Envoy' or a real name.

    Per `specs/shamir-recovery.md` § Card format (line 29):
    > NO "Envoy" label; NO name. Distribution checklist persists only opaque
    > slot labels in Trust Vault; real names optional + in hidden envelope
    > (Phase 04) only (H-06 fix).

    The error fires from the paper renderer (`envoy/shamir/paper.py`) when
    the supplied `slot_label` contains a forbidden token. T-02-35 also reuses
    this error class for shape-validation failures inside the renderer
    (malformed shard / sequence) so callers handle a single typed error
    surface for "card cannot be printed" scenarios.

    Phase 01 enforces the H-06 fix structurally — a malicious or careless
    caller cannot bypass the check by constructing a `PaperShardCard`
    directly because the dataclass is frozen and the renderer is the only
    public construction path mandated by the `PaperRenderer` Protocol.
    """


class ChecklistPersisterError(ShamirRitualError):
    """The DistributionChecklist could not be persisted to the Trust Vault.

    Wraps lower-level `VaultLockedError` / `VaultUnlockFailedError` /
    `OSError` (atomic-write failure) into a single typed error the
    coordinator surfaces to the boundary-conversation channel.

    Per `rules/communication.md`, the user_message is plain-language: "We
    couldn't save the backup checklist. Re-unlock the vault and try again."
    """


class ShamirRecoveryError(ShamirRitualError):
    """Base class for recovery-side errors raised by T-02-36 `envoy shamir recover`.

    Inherits from `ShamirRitualError` so the existing channel adapter
    catch sites (`except ShamirRitualError`) keep covering recovery
    failures without extra wiring. Per `specs/shamir-recovery.md`
    § Error taxonomy — the recovery-side errors live here so the CLI,
    Boundary Conversation S8, and future channel-adapter recovery flows
    all surface the same typed contract.
    """


class ShardChecksumFailedError(ShamirRecoveryError):
    """SLIP-0039 per-card BIP-39 checksum invalid at entry (L-03 fix).

    Per `specs/shamir-recovery.md` § Recovery flow:
    > Enter words from any 3 cards (any order). Per-card checksum
    > validation at entry (L-03 fix).

    Raised BEFORE reconstruction is attempted, so the user knows
    which specific card failed (not "combine failed somewhere"). The
    `card_index` attribute identifies the 0-indexed card; the
    `.user_message` names the slot label the holder transcribed.

    The L-03 carry-forward originally targeted `shamir_mnemonic`'s
    `MnemonicError` raised by `combine_mnemonics` — which fires at
    threshold-time and cannot name the offending card. Per-card
    validation via `shamir_mnemonic.share.Share.from_mnemonic` catches
    the same checksum failure earlier and binds it to the specific card.
    """

    def __init__(
        self,
        message: str,
        *,
        card_index: int,
        slot_label: str,
        user_message: str | None = None,
    ) -> None:
        super().__init__(message, user_message=user_message)
        self.card_index = card_index
        self.slot_label = slot_label


class InsufficientSharesError(ShamirRecoveryError):
    """Recovery attempted with fewer than threshold (default 3) valid shards.

    Per `specs/shamir-recovery.md` § Error taxonomy. Raised by the
    recovery primitive at entry validation — BEFORE any commitment
    verification or reconstruction call. The `presented` and `threshold`
    attributes let channel adapters render "need 3, have 2" UX.
    """

    def __init__(
        self,
        message: str,
        *,
        presented: int,
        threshold: int,
        user_message: str | None = None,
    ) -> None:
        super().__init__(message, user_message=user_message)
        self.presented = presented
        self.threshold = threshold


class TooManySharesError(ShamirRecoveryError):
    """Recovery attempted with more than threshold valid shards.

    SLIP-0039 is strict about share count — `combine_mnemonics` requires
    EXACTLY threshold mnemonics. The library raises an opaque
    `MnemonicError` ("Wrong number of mnemonics. Expected 3 ... but 4
    were provided") which `rules/communication.md` MUST NOT (raw error
    messages) requires us to translate at the boundary.

    The recovery primitive validates `len(presented) == threshold` at
    entry, raising this typed error with plain-language `.user_message`
    so the user knows to pick exactly threshold cards (rather than
    "provide all the cards you have"). Distinct from
    `InsufficientSharesError` so channel adapters can render direction-
    specific UX ("you have too many, pick 3" vs "you have too few,
    retrieve more").

    Spec-extension note: T-02-36 extended `specs/shamir-recovery.md`
    § Error taxonomy in the same PR to enumerate this case per
    `rules/specs-authority.md` MUST Rule 5 — the row makes the typed
    error part of the canonical taxonomy. The implementation discovered
    the library's strict-count behavior; the typed envoy error is the
    user-friendly translation per `rules/communication.md` MUST NOT
    (raw error messages).
    """

    def __init__(
        self,
        message: str,
        *,
        presented: int,
        threshold: int,
        user_message: str | None = None,
    ) -> None:
        super().__init__(message, user_message=user_message)
        self.presented = presented
        self.threshold = threshold


class CommitmentVerificationFailedError(ShamirRecoveryError):
    """Presented shard's commitment is not in `Genesis.shard_public_commitments`.

    This is a SECURITY EVENT per `specs/shamir-recovery.md` § Error
    taxonomy ("Retry: Never"). A counterfeit shard — constructed from a
    different secret — produces a commitment that does NOT appear in the
    Genesis Record's commitment array. The recovery primitive refuses to
    install the reconstructed master key.

    The `failing_card_index` and `failing_slot_label` attributes identify
    which presented card failed verification. The recovery primitive
    fails FAST on the first mismatch — it does not enumerate all
    mismatching cards (a second mismatch would leak the same security
    signal).
    """

    def __init__(
        self,
        message: str,
        *,
        failing_card_index: int,
        failing_slot_label: str,
        user_message: str | None = None,
    ) -> None:
        super().__init__(message, user_message=user_message)
        self.failing_card_index = failing_card_index
        self.failing_slot_label = failing_slot_label


class ShardSlotLabelMismatchError(ShamirRecoveryError):
    """A presented slot label does not appear in the DistributionChecklist.

    Per `specs/shamir-recovery.md` § Error taxonomy. Surface as
    wrong-card; user retrieves the correct slot OR investigates checklist
    drift. The opaque-label whitelist (`^slot-\\d+$`) per
    `envoy/shamir/distribution_checklist.py` constrains the surface to
    a small, structurally-validated set.
    """

    def __init__(
        self,
        message: str,
        *,
        presented_label: str,
        checklist_labels: tuple[str, ...],
        user_message: str | None = None,
    ) -> None:
        super().__init__(message, user_message=user_message)
        self.presented_label = presented_label
        self.checklist_labels = checklist_labels


class ShardPublicCommitmentMissingError(ShamirRecoveryError):
    """Genesis Record lacks `shard_public_commitments` (pre-Phase-01 vault).

    Per `specs/shamir-recovery.md` § Error taxonomy + `specs/trust-lineage.md`
    § GenesisRecord schema. A Phase-01 vault MUST carry the commitment
    array; an absent array means the vault was created before T-02-35
    landed and cannot be recovered safely (counterfeit shards cannot be
    detected). The user MUST migrate the vault to the current schema OR
    re-shard from a fresh ritual.

    This error is raised BEFORE per-shard commitment verification fires —
    it is the precondition that the verification step exists at all.
    """


__all__ = [
    "ShamirRitualError",
    "RitualPreconditionError",
    "MasterKeyZeroizationError",
    "EnvoyLabelOnCardError",
    "ChecklistPersisterError",
    # Recovery-side taxonomy (T-02-36)
    "ShamirRecoveryError",
    "ShardChecksumFailedError",
    "InsufficientSharesError",
    "TooManySharesError",
    "CommitmentVerificationFailedError",
    "ShardSlotLabelMismatchError",
    "ShardPublicCommitmentMissingError",
]
