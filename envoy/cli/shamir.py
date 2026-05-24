"""`envoy shamir` click subcommand group — T-02-36.

Per `specs/shamir-recovery.md` § Recovery flow. Wraps the pure
`envoy.shamir.recover.recover_master_key` primitive with click prompts
+ file-based input + structured error rendering.

Three top-level invariants per T-02-36 capacity check
(`workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md`):

1. Commitment verification — enforced inside the primitive.
2. Threshold reconstruction — enforced inside the primitive.
3. CLI surface stability — the click group + command names + option
   names are AST-locked at
   `tests/tier1/test_shamir_recover_cli.py::TestRecoverCliSurface`.

The CLI does NOT install the recovered master key into a vault — vault
wiring lands in T-02-37 (Tier 2 wiring) when the real Trust Vault
integration tests run. T-02-36 ships the primitive + CLI surface; the
CLI exits 0 on successful recovery + prints a success message that names
the next step ("vault unlock wiring lands in T-02-37"). The recovered
bytes are zeroized via `del recovered` in the finally clause.
"""

from __future__ import annotations

import json
import logging
import pathlib
import sys

import click

from envoy.shamir.errors import (
    CommitmentVerificationFailedError,
    InsufficientSharesError,
    ShamirRecoveryError,
    ShardChecksumFailedError,
    ShardPublicCommitmentMissingError,
    ShardSlotLabelMismatchError,
    TooManySharesError,
)
from envoy.shamir.recover import (
    DEFAULT_THRESHOLD,
    PresentedShard,
    recover_master_key,
)

logger = logging.getLogger(__name__)


# Exit codes per `specs/shamir-recovery.md` § Error taxonomy. The CLI
# maps each typed error to a stable numeric exit code so shell scripts
# and channel adapters can dispatch on outcome without parsing stderr.
EXIT_OK = 0
EXIT_USAGE = 2  # click default for usage errors
EXIT_INSUFFICIENT_SHARES = 10
EXIT_SHARD_CHECKSUM_FAILED = 11
EXIT_SLOT_LABEL_MISMATCH = 12
EXIT_COMMITMENT_VERIFICATION_FAILED = 13
EXIT_COMMITMENT_MISSING = 14
EXIT_RECONSTRUCT_FAILED = 15
EXIT_TOO_MANY_SHARES = 16


@click.group()
def shamir() -> None:
    """Shamir 3-of-5 vault backup + recovery rituals."""


def _read_genesis_inputs(
    genesis_path: pathlib.Path,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Read commitments + checklist labels from the Genesis Record file.

    Phase 01 Genesis Record format (per `specs/trust-lineage.md`
    § GenesisRecord schema):

        {
          "principal_id": "...",
          "shard_public_commitments": ["sha256:...", "sha256:..."],
          "shamir_distribution_checklist": {
            "ritual_id": "...",
            "slot_labels": ["slot-0", "slot-1", ...]
          }
        }

    Either key may be absent for pre-Phase-01 vaults; missing commitments
    triggers `ShardPublicCommitmentMissingError` inside
    `recover_master_key`. Missing slot_labels collapses to an empty tuple
    which causes every presented label to mismatch — surfaced with the
    standard `ShardSlotLabelMismatchError` message.

    Raises:
        click.BadParameter: file does not exist or is not valid JSON.
    """
    if not genesis_path.exists():
        raise click.BadParameter(
            f"genesis file not found at {genesis_path}",
            param_hint="--genesis",
        )
    try:
        data = json.loads(genesis_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.BadParameter(
            f"genesis file at {genesis_path} is not valid JSON: {exc}",
            param_hint="--genesis",
        ) from exc

    commitments = tuple(data.get("shard_public_commitments", []) or [])
    checklist = data.get("shamir_distribution_checklist", {}) or {}
    slot_labels = tuple(checklist.get("slot_labels", []) or [])
    return commitments, slot_labels


def _read_shards_from_file(path: pathlib.Path) -> list[PresentedShard]:
    """Read presented shards from a JSON file (non-interactive recovery).

    File format:

        [
          {"slot_label": "slot-0", "words": ["word1", "word2", ...]},
          {"slot_label": "slot-2", "words": ["word1", "word2", ...]},
          {"slot_label": "slot-4", "words": ["word1", "word2", ...]}
        ]

    The CLI assigns `card_index` from the file's array order. Empty array
    raises `click.BadParameter`; per-card validation defers to the
    primitive.
    """
    if not path.exists():
        raise click.BadParameter(
            f"shards file not found at {path}",
            param_hint="--shards-from",
        )
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.BadParameter(
            f"shards file at {path} is not valid JSON: {exc}",
            param_hint="--shards-from",
        ) from exc
    if not isinstance(entries, list) or not entries:
        raise click.BadParameter(
            f"shards file at {path} must contain a non-empty JSON array",
            param_hint="--shards-from",
        )

    presented: list[PresentedShard] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise click.BadParameter(
                f"shards file at {path}: entry {idx} must be an object",
                param_hint="--shards-from",
            )
        slot_label = entry.get("slot_label")
        words = entry.get("words")
        if not isinstance(slot_label, str) or not slot_label:
            raise click.BadParameter(
                f"shards file at {path}: entry {idx} missing slot_label",
                param_hint="--shards-from",
            )
        if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
            raise click.BadParameter(
                f"shards file at {path}: entry {idx} words must be list[str]",
                param_hint="--shards-from",
            )
        presented.append(PresentedShard(slot_label=slot_label, words=list(words), card_index=idx))
    return presented


def _prompt_shards_interactive(threshold: int) -> list[PresentedShard]:
    """Prompt the user for `threshold` cards interactively.

    The prompt sequence per `specs/shamir-recovery.md` § Recovery flow:
    > Enter words from any 3 cards (any order).

    For each card we ask for the opaque slot label, then the 24 words
    on a single line (whitespace-tolerant — multiple spaces / tab / etc.
    collapse to a single separator). The primitive validates per-card
    checksum after all cards are collected so the user sees one
    transcription pass before being told which card failed.
    """
    click.echo(
        f"\nEntering recovery — you need {threshold} cards. " "Cards may be entered in any order.\n"
    )
    presented: list[PresentedShard] = []
    for idx in range(threshold):
        click.echo(f"--- Card {idx + 1} of {threshold} ---")
        slot_label = click.prompt(
            "  Slot label (e.g. slot-0)",
            type=str,
        ).strip()
        words_line = click.prompt(
            "  24 words from the card (space-separated)",
            type=str,
        )
        # SLIP-0039 paper-print form: split on any whitespace per
        # kailash.trust.vault.shamir.deserialize_shard.
        words = words_line.split()
        presented.append(PresentedShard(slot_label=slot_label, words=words, card_index=idx))
    return presented


def _render_error(error: ShamirRecoveryError) -> None:
    """Render a typed recovery error to stderr in plain language.

    Per `rules/communication.md` MUST NOT (raw error messages): every
    `ShamirRecoveryError` carries a `.user_message` for direct user
    rendering. The class name is included on a second line as a stable
    machine-parseable identifier for downstream tooling.
    """
    click.echo(f"\n{error.user_message or str(error)}\n", err=True)
    click.echo(f"[error_class={type(error).__name__}]", err=True)


@shamir.command(name="recover")
@click.option(
    "--genesis",
    "genesis_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=pathlib.Path),
    help=(
        "Path to the Genesis Record JSON file. The CLI reads "
        "shard_public_commitments and shamir_distribution_checklist.slot_labels "
        "from this file."
    ),
)
@click.option(
    "--shards-from",
    "shards_from",
    default=None,
    type=click.Path(dir_okay=False, path_type=pathlib.Path),
    help=(
        "Optional: read presented shards from a JSON file instead of "
        "prompting interactively. Useful for scripted recovery and tests."
    ),
)
@click.option(
    "--threshold",
    default=DEFAULT_THRESHOLD,
    show_default=True,
    type=click.IntRange(min=2, max=16),
    help="SLIP-0039 reconstruction threshold. Default 3 per specs/shamir-recovery.md.",
)
@click.option(
    "--passphrase",
    default="",
    show_default=False,
    help=(
        "SLIP-0039 passphrase used at backup ritual time. MUST match the "
        "passphrase passed to envoy shamir backup. Default empty."
    ),
)
def recover(
    genesis_path: pathlib.Path,
    shards_from: pathlib.Path | None,
    threshold: int,
    passphrase: str,
) -> None:
    """Recover the vault master key from threshold-many Shamir cards.

    Per `specs/shamir-recovery.md` § Recovery flow. Validates per-card
    BIP-39 checksum at entry (L-03 fix), verifies each presented shard's
    commitment against the Genesis Record (counterfeit-shard defense),
    and reconstructs the master key via SLIP-0039.

    T-02-36 ships the primitive + CLI surface; vault unlock wiring lands
    in T-02-37. On successful recovery the CLI prints a confirmation +
    the next step. The recovered master key is zeroized via `del`
    immediately after the print (Python's `bytes` is immutable so this
    is the strongest portable defense per
    rules/trust-plane-security.md MUST NOT Rule 3).
    """
    commitments, checklist_labels = _read_genesis_inputs(genesis_path)

    if shards_from is not None:
        presented = _read_shards_from_file(shards_from)
    else:
        presented = _prompt_shards_interactive(threshold)

    recovered: bytes | None = None
    try:
        recovered = recover_master_key(
            presented,
            commitments=commitments,
            checklist_labels=checklist_labels,
            threshold=threshold,
            passphrase=passphrase.encode("utf-8"),
        )
        click.echo(
            f"\nRecovery succeeded — reconstructed {len(recovered)} bytes "
            "of master key.\n"
            "\nNext step: vault unlock wiring lands in T-02-37. Until then "
            "the recovered key is held only in this process and discarded "
            "on exit.\n"
        )
        sys.exit(EXIT_OK)
    except InsufficientSharesError as exc:
        _render_error(exc)
        sys.exit(EXIT_INSUFFICIENT_SHARES)
    except TooManySharesError as exc:
        _render_error(exc)
        sys.exit(EXIT_TOO_MANY_SHARES)
    except ShardPublicCommitmentMissingError as exc:
        _render_error(exc)
        sys.exit(EXIT_COMMITMENT_MISSING)
    except ShardSlotLabelMismatchError as exc:
        _render_error(exc)
        sys.exit(EXIT_SLOT_LABEL_MISMATCH)
    except ShardChecksumFailedError as exc:
        _render_error(exc)
        sys.exit(EXIT_SHARD_CHECKSUM_FAILED)
    except CommitmentVerificationFailedError as exc:
        _render_error(exc)
        sys.exit(EXIT_COMMITMENT_VERIFICATION_FAILED)
    except (ValueError, TypeError) as exc:
        # ValueError / TypeError propagated from kailash.trust.vault.shamir.reconstruct
        # — mixed identifiers across rituals, library-level malformed input.
        click.echo(
            f"\nWe couldn't put your cards back together. The cards may be "
            f"from different backups, or one is structurally damaged. "
            f"\nDetails: {exc}\n",
            err=True,
        )
        sys.exit(EXIT_RECONSTRUCT_FAILED)
    finally:
        # Per rules/trust-plane-security.md MUST NOT Rule 3 — drop the
        # reference to the recovered bytes ASAP. Python's `bytes` is
        # immutable so in-place zeroize is not portable; reference drop
        # is the strongest portable defense.
        if recovered is not None:
            del recovered


__all__ = ["shamir", "recover"]
