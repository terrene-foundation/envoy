"""envoy.shamir.recover — pure recovery primitive (T-02-36).

Per `specs/shamir-recovery.md` § Recovery flow:
> Enter words from any 3 cards (any order). Per-card checksum validation
> at entry (L-03 fix). Reconstruction; vault unlock.

This module ships the pure primitive — no CLI plumbing, no I/O, no
prompts. The CLI shell in `envoy/cli/shamir.py` wraps `recover_master_key`
with argparse / click plumbing; the Boundary Conversation S8 recovery
flow (T-08-130, Phase 03+) wraps it with conversational prompts.
Boundary Conversation reuses the SAME primitive so the contract is
single-sourced.

T-02-36 invariants (3 invariants, per
`workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md`
§ T-02-36 capacity check):

1. **Commitment verification** — `verify_commitment(shard, commitments)`
   MUST return True for every presented shard. First failure aborts
   recovery with `CommitmentVerificationFailedError` naming the offending
   card. Tested at `tests/tier1/test_shamir_recover_cli.py::TestCommitmentVerificationGate`.

2. **Threshold reconstruction** — presented-share count < threshold
   raises `InsufficientSharesError` BEFORE any other check (cheapest
   precondition). Tested at
   `tests/tier1/test_shamir_recover_cli.py::TestInsufficientShares`.

3. **CLI surface stability** — `recover_master_key()` signature
   (positional `presented`, keyword `commitments`, `checklist_labels`,
   `threshold`, `passphrase`) is AST-locked at
   `tests/tier1/test_shamir_recover_cli.py::TestRecoverMasterKeySignature`.
   Future signature changes MUST update the AST lock + spec.

Per `rules/trust-plane-security.md` MUST NOT Rule 3 (Private Key Material
in Memory): the reconstructed `bytes` MUST be deleted by callers
immediately after use. This primitive does NOT zeroize because Python's
`bytes` is immutable; the comment above the return statement names the
contract and the CLI's `finally: del recovered` clause is the structural
enforcement.

Per `rules/specs-authority.md` MUST Rule 5: the recovery flow's contract
is `specs/shamir-recovery.md` § Recovery flow + § Error taxonomy. Any
change to the order of validation steps OR the taxonomy MUST update both.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from envoy.shamir.commitments import verify_commitment
from envoy.shamir.errors import (
    CommitmentVerificationFailedError,
    InsufficientSharesError,
    ShardChecksumFailedError,
    ShardPublicCommitmentMissingError,
    ShardSlotLabelMismatchError,
    TooManySharesError,
)

logger = logging.getLogger(__name__)


# Default threshold per `specs/shamir-recovery.md` § Default threshold.
DEFAULT_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class PresentedShard:
    """One transcribed paper card presented at recovery time.

    Three fields per `specs/shamir-recovery.md` § Recovery flow:

    - `slot_label` — the opaque label the holder reads off the card
      (matches `^slot-\\d+$`; whitelist enforced upstream by the
      DistributionChecklist persister).
    - `words` — the 24 BIP-39 dictionary words the holder transcribed
      from the card. Whitespace tolerance lives at the CLI parsing layer
      (`envoy/cli/shamir.py`); this primitive expects a clean list.
    - `card_index` — 0-indexed position in the order the holder entered
      cards (NOT the SLIP-0039 share index; that's encoded inside the
      mnemonic). Used by `ShardChecksumFailedError.card_index` and
      `CommitmentVerificationFailedError.failing_card_index` so error
      messages can name which transcription failed.
    """

    slot_label: str
    words: list[str]
    card_index: int


def _validate_card_checksum(presented: PresentedShard) -> None:
    """Raise `ShardChecksumFailedError` if SLIP-0039 per-card checksum is invalid.

    Per `specs/shamir-recovery.md` § Recovery flow (L-03 fix):
    > Per-card checksum validation at entry.

    Uses `shamir_mnemonic.share.Share.from_mnemonic` — the canonical
    SLIP-0039 decoder. On bad checksum it raises `MnemonicError` which
    we re-raise as the typed `ShardChecksumFailedError` carrying the
    offending card's `card_index` + `slot_label`.

    Per `rules/zero-tolerance.md` Rule 3a: typed delegate guard before
    `from_mnemonic` is called — empty words list short-circuits to a
    typed error (`from_mnemonic` would raise an opaque error otherwise).
    """
    from shamir_mnemonic import MnemonicError
    from shamir_mnemonic.share import Share

    if not presented.words:
        raise ShardChecksumFailedError(
            f"card {presented.card_index} ({presented.slot_label}): " f"no words presented",
            card_index=presented.card_index,
            slot_label=presented.slot_label,
            user_message=(
                f"Card {presented.slot_label} has no words on it. "
                "Re-enter the 24 words from the card."
            ),
        )

    mnemonic_str = " ".join(presented.words)
    try:
        Share.from_mnemonic(mnemonic_str)
    except MnemonicError as exc:
        raise ShardChecksumFailedError(
            f"card {presented.card_index} ({presented.slot_label}): "
            f"SLIP-0039 checksum invalid: {exc}",
            card_index=presented.card_index,
            slot_label=presented.slot_label,
            user_message=(
                f"The words on card {presented.slot_label} don't pass the "
                "built-in spell-check. Re-enter the card carefully — one "
                "word is probably misread or transcribed wrong. If you "
                "still see this after retyping, the card itself may be "
                "transcription-damaged."
            ),
        ) from exc


def recover_master_key(
    presented: list[PresentedShard],
    *,
    commitments: tuple[str, ...],
    checklist_labels: tuple[str, ...],
    threshold: int = DEFAULT_THRESHOLD,
    passphrase: bytes = b"",
) -> bytes:
    """Recover the master key from `presented` shards.

    Implements `specs/shamir-recovery.md` § Recovery flow as a pure
    primitive. The CLI shell (`envoy/cli/shamir.py`) wraps this with
    user prompts; Boundary Conversation S8 wraps this with conversational
    prompts. Both reuse the SAME validation order.

    Validation order (cheapest precondition first; security-relevant
    checks before any reconstruction attempt):

    1. `InsufficientSharesError` — `len(presented) < threshold`.
    2. `ShardPublicCommitmentMissingError` — `commitments` is empty
       (pre-Phase-01 vault; recovery cannot detect counterfeit shards).
    3. `ShardSlotLabelMismatchError` — any presented slot label is NOT
       in `checklist_labels`.
    4. `ShardChecksumFailedError` — any presented card's SLIP-0039
       per-card checksum is invalid (L-03 fix).
    5. `CommitmentVerificationFailedError` — any presented shard's
       commitment is NOT in `commitments`. First-failure-wins: the
       primitive does NOT enumerate all mismatches (would leak the
       same security signal twice).
    6. Reconstruction via `kailash.trust.vault.shamir.reconstruct` —
       any `ValueError` / `TypeError` from the underlying library
       propagates with its native type so callers can distinguish
       reconstruction failures (mixed identifiers, etc.) from the
       envoy-side typed errors above.

    Args:
        presented: list of `PresentedShard`. Order is the order the
            holder entered cards (any order acceptable per spec
            § Recovery flow). Length MUST be >= threshold.
        commitments: tuple of `algo:hexdigest` commitments from
            `Genesis.shard_public_commitments`. Empty tuple raises
            `ShardPublicCommitmentMissingError`.
        checklist_labels: tuple of opaque slot labels from the
            `DistributionChecklist`. Any presented label not in this
            tuple raises `ShardSlotLabelMismatchError`.
        threshold: SLIP-0039 reconstruction threshold (default 3 per
            spec § Default threshold).
        passphrase: SLIP-0039 passphrase used at ritual time. MUST
            match the bytes passed at backup. Default empty per spec.

    Returns:
        The 32-byte master key.

    Memory hygiene:
        Per `rules/trust-plane-security.md` MUST NOT Rule 3 (Private
        Key Material in Memory): the caller MUST `del recovered`
        immediately after installing the key into the vault. The
        primitive does NOT zeroize because Python's `bytes` is immutable
        in-place clearing is not portable. The CLI shell's
        `try ... finally: del recovered` clause is the structural
        enforcement.

    Raises:
        InsufficientSharesError: presented count < threshold.
        TooManySharesError: presented count > threshold (SLIP-0039 is
            strict — exactly threshold cards required).
        ShardPublicCommitmentMissingError: commitments tuple is empty.
        ShardSlotLabelMismatchError: presented slot label not in
            checklist_labels.
        ShardChecksumFailedError: SLIP-0039 per-card checksum invalid
            (L-03 fix).
        CommitmentVerificationFailedError: presented shard's commitment
            not in commitments (counterfeit shard — security event).
        ValueError, TypeError: propagated from
            `kailash.trust.vault.shamir.reconstruct` for reconstruction
            failures (mixed identifiers, etc.) outside the envoy-side
            taxonomy.
    """
    # Lazy import — keeps `from envoy.shamir.recover import recover_master_key`
    # cheap and lets the test layer monkeypatch the reconstruct surface
    # without dragging the kailash extras at primitive import time.
    from kailash.trust.vault.shamir import reconstruct

    # Step 1 — threshold precondition (cheapest). SLIP-0039 is strict:
    # exactly threshold cards required. Both below-threshold and
    # above-threshold raise typed envoy errors so the CLI / channel
    # adapter renders direction-specific UX instead of the library's
    # opaque "Wrong number of mnemonics" message.
    if len(presented) < threshold:
        raise InsufficientSharesError(
            f"recover_master_key: presented {len(presented)} shards, " f"threshold {threshold}",
            presented=len(presented),
            threshold=threshold,
            user_message=(
                f"We need {threshold} cards to put the vault back together. "
                f"You've entered {len(presented)} so far. Retrieve the "
                "remaining cards from your safes or holders, then try "
                "recovery again."
            ),
        )
    if len(presented) > threshold:
        raise TooManySharesError(
            f"recover_master_key: presented {len(presented)} shards, "
            f"threshold {threshold} — SLIP-0039 requires exactly threshold",
            presented=len(presented),
            threshold=threshold,
            user_message=(
                f"You've entered {len(presented)} cards but the vault only "
                f"needs {threshold} to recover. Pick exactly {threshold} of "
                "your cards and try again — the others stay safe in their "
                "holders / safes."
            ),
        )

    # Step 2 — Genesis must carry the commitment array, else counterfeit
    # shards are undetectable. Refuse rather than proceed with reduced
    # safety guarantees.
    if not commitments:
        raise ShardPublicCommitmentMissingError(
            "recover_master_key: Genesis Record lacks "
            "shard_public_commitments — pre-Phase-01 vault cannot be "
            "safely recovered",
            user_message=(
                "This vault was created before the current safety check "
                "was added. We can't safely recover it without first "
                "migrating the vault to the current schema. Run "
                "`envoy vault migrate` and then try recovery again."
            ),
        )

    # Step 3 — slot-label whitelist (catches wrong-card UX before
    # checksum work). `checklist_labels` is the canonical list from
    # the DistributionChecklist.
    checklist_set = frozenset(checklist_labels)
    for shard in presented:
        if shard.slot_label not in checklist_set:
            raise ShardSlotLabelMismatchError(
                f"recover_master_key: card {shard.card_index} slot label "
                f"{shard.slot_label!r} not in DistributionChecklist labels "
                f"{checklist_labels!r}",
                presented_label=shard.slot_label,
                checklist_labels=checklist_labels,
                user_message=(
                    f"The card labeled {shard.slot_label} isn't one we're "
                    "expecting for this vault. Either you have the wrong "
                    "card (re-check the distribution list) or your records "
                    "have drifted. Stop and check before continuing — this "
                    "is the kind of mistake recovery is designed to catch."
                ),
            )

    # Step 4 — per-card BIP-39 checksum (L-03 fix). Validates each
    # presented card before we attempt reconstruction so we can name
    # which card failed (combine_mnemonics would only say "combine
    # failed somewhere").
    for shard in presented:
        _validate_card_checksum(shard)

    # Step 5 — commitment verification against Genesis. Counterfeit
    # shards fail here even if their SLIP-0039 checksum is structurally
    # valid (the attacker would have to know the original secret to
    # forge a matching commitment — by construction impossible).
    commitments_list = list(commitments)
    for shard in presented:
        if not verify_commitment(shard.words, commitments_list):
            raise CommitmentVerificationFailedError(
                f"recover_master_key: card {shard.card_index} "
                f"({shard.slot_label}) commitment not in Genesis.shard_public_commitments",
                failing_card_index=shard.card_index,
                failing_slot_label=shard.slot_label,
                user_message=(
                    f"The card labeled {shard.slot_label} passes the "
                    "built-in spell-check but it doesn't match the vault's "
                    "recorded fingerprint. This usually means the card is "
                    "a counterfeit OR someone substituted a different "
                    "card. Recovery has been refused. Treat this as a "
                    "security incident — investigate before retrying."
                ),
            )

    # Step 6 — reconstruction. ValueError / TypeError propagate with
    # their native types so callers can distinguish reconstruction
    # failures (mixed identifiers from different rituals, library-level
    # malformed input) from the envoy-side typed errors above.
    shards = [shard.words for shard in presented]
    logger.info(
        "shamir.recover.start",
        extra={
            "presented_count": len(presented),
            "threshold": threshold,
        },
    )
    secret = reconstruct(shards, passphrase=passphrase)
    logger.info(
        "shamir.recover.ok",
        extra={"recovered_bytes": len(secret)},
    )
    return secret


__all__ = [
    "DEFAULT_THRESHOLD",
    "PresentedShard",
    "recover_master_key",
]
