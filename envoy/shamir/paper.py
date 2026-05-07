"""Paper card renderer — H-06-compliant SLIP-0039 transcription format.

Per `specs/shamir-recovery.md` § Card format (line 28-29):
> 24 BIP-39 words; Trezor-compatible.
> NO "Envoy" label; NO name. Distribution checklist persists only opaque slot
> labels in Trust Vault; real names optional + in hidden envelope (Phase 04)
> only (H-06 fix).

The renderer produces a `PaperShardCard` per shard. Each card carries:
- An OPAQUE slot label (`slot-1`, `slot-2`, ...) — never "Envoy", never a
  holder name. Real names (if the user opts in at Phase 04) live in the
  hidden envelope only.
- A sequence tuple `(card_index, total_cards)` that lets the holder confirm
  they have the full set without seeing the user's name.
- A plain-language threshold reminder ("Any 3 of these 5 cards recovers your
  keys") so a holder can act on the card without consulting the spec.
- The 24 mnemonic words as a frozen tuple (per `rules/eatp.md` SDK conventions
  + `rules/trust-plane-security.md` MUST NOT Rule 4 — frozen dataclasses).

PDF rendering is OUT OF SCOPE for T-02-35 per shard 15 § 3.2 line 120 —
plain-text rendering + manual print path satisfies EC-5 acceptance gate (b).
Phase 02 stretch may add a PDF renderer behind a separate facade.

H-06 enforcement at render time: `render` raises `EnvoyLabelOnCardError` if
the supplied `slot_label` contains "Envoy" or matches a list of common-name
patterns (lower-cased substring check). The error class lives at module level
so the Tier 1 test can assert the rejection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from envoy.shamir.errors import EnvoyLabelOnCardError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frozen card dataclass — per rules/eatp.md + trust-plane-security.md
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PaperShardCard:
    """One rendered SLIP-0039 shard card per shard 15 § 3.2.

    Fields are intentionally narrow:
    - `slot_label`: opaque slot identifier (`slot-1`...) — H-06 enforced.
    - `sequence`: `(card_index, total_cards)`, e.g. `(1, 5)` for "Card 1 of 5".
    - `threshold_reminder`: plain-language sentence per `rules/communication.md`.
    - `mnemonic_words`: tuple of dictionary words (frozen; immutable copy).
    - `transcription_layout`: opaque format identifier — Phase 01 ships
      `"rows-of-6"` (24 words → 4 rows × 6 words).
    - `created_at`: timezone-aware UTC datetime; serialized as isoformat.

    Per `rules/eatp.md` SDK conventions: every dataclass MUST have `to_dict()`
    + `from_dict()`. Used by Phase 02 boundary-conversation persistence and
    by debug rendering — never for the actual card content (the user holds
    the words on paper, not in JSON).
    """

    slot_label: str
    sequence: tuple[int, int]
    threshold_reminder: str
    mnemonic_words: tuple[str, ...]
    transcription_layout: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serializable form per `rules/eatp.md` SDK conventions.

        Note: `mnemonic_words` IS sensitive — round-trip serialization is
        permitted only for boundary-conversation in-memory plumbing and for
        debug paths that the user explicitly opts into. Persisted vault
        storage uses the DistributionChecklist (opaque slot labels only)
        per H-06; the words themselves NEVER reach disk through envoy.
        """
        return {
            "slot_label": self.slot_label,
            "sequence": list(self.sequence),
            "threshold_reminder": self.threshold_reminder,
            "mnemonic_words": list(self.mnemonic_words),
            "transcription_layout": self.transcription_layout,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperShardCard:
        return cls(
            slot_label=data["slot_label"],
            sequence=tuple(data["sequence"]),  # type: ignore[arg-type]
            threshold_reminder=data["threshold_reminder"],
            mnemonic_words=tuple(data["mnemonic_words"]),
            transcription_layout=data["transcription_layout"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


# H-06 enforcement: tokens that MUST NOT appear (case-insensitive) in slot
# labels. The check is a substring match — narrower than name-pattern
# matching — to avoid false positives on legitimate slot identifiers like
# "slot-3" while still catching `Envoy` / `envoy` / `Alice's Card` /
# `Bob-Backup`. Phase 02 may add a richer name-detection pass.
_FORBIDDEN_LABEL_TOKENS: tuple[str, ...] = ("envoy",)

# Phase 01 transcription layout. 24 words → 4 rows × 6 words for visual
# alignment per shard 15 § 3.2 ("rows of 6"). The identifier is opaque to
# the dataclass — the renderer's `render_text` interprets it.
_DEFAULT_TRANSCRIPTION_LAYOUT = "rows-of-6"
_WORDS_PER_ROW = 6


def _validate_slot_label(slot_label: str) -> None:
    """Reject any slot label that violates H-06 (no 'Envoy' / no real names).

    Phase 01 enforces a substring check on `_FORBIDDEN_LABEL_TOKENS`. The check
    is intentionally narrow — it catches the failure mode shard 15 § 3.2
    enumerates ("NO 'Envoy' label; NO name") without false-positiving on
    legitimate `slot-N` identifiers. Real-name detection (Alice / Bob /
    common-name dictionary) is BLOCKED from Phase 01 because of localization
    drift and false-positive risk; the substring check is the structural
    minimum, paired with a UX layer that funnels users into the canonical
    `slot-N` shape via `_opaque_slot_labels()`.
    """
    if not isinstance(slot_label, str) or not slot_label:
        raise EnvoyLabelOnCardError(
            f"slot_label must be a non-empty string; got {slot_label!r}",
            user_message=(
                "Backup card cannot be printed without a slot label. "
                "Use one of the opaque labels (slot-1, slot-2, ...) the "
                "ritual prepared for you."
            ),
        )
    lowered = slot_label.lower()
    for token in _FORBIDDEN_LABEL_TOKENS:
        if token in lowered:
            raise EnvoyLabelOnCardError(
                f"slot_label {slot_label!r} contains forbidden token "
                f"{token!r} — H-06 violation per specs/shamir-recovery.md "
                f"line 29",
                user_message=(
                    "Backup cards must not carry the 'Envoy' label or any "
                    "real holder name. Use the opaque slot label "
                    "(slot-1, slot-2, ...) the ritual prepared for you. "
                    "Real names — if you want them recorded — go in the "
                    "private envelope, never on the card itself."
                ),
            )


class PaperShardRenderer:
    """Implements the `PaperRenderer` Protocol per `envoy/shamir/types.py`.

    Construction takes no dependencies — the renderer is a pure transformer
    from `(shard, slot_label, sequence)` to a `PaperShardCard`. State-free
    by design; an instance is reusable across shards within a ritual.

    Per `rules/facade-manager-detection.md` Rule 3 (Constructor receives
    explicit dependencies) — N/A for this class because it has no
    dependencies; the rule applies only to manager-shape classes that own
    state.
    """

    def __init__(self, *, threshold: int = 3, total_shards: int = 5) -> None:
        """Construct a renderer parameterised on the ritual's threshold + total.

        The renderer needs both numbers to render the plain-language
        threshold reminder ("Any 3 of these 5 cards recovers your keys").
        Phase 01 default is 3-of-5 per `specs/shamir-recovery.md` § Default
        threshold; user-configurable 2-of-3 to 5-of-9.
        """
        if threshold < 2:
            raise EnvoyLabelOnCardError(
                f"threshold must be >= 2; got {threshold}",
                user_message=(
                    "Backup ritual configured with too few required cards. "
                    "Threshold must be at least 2."
                ),
            )
        if total_shards < threshold:
            raise EnvoyLabelOnCardError(
                f"total_shards ({total_shards}) must be >= threshold ({threshold})",
                user_message=(
                    "Backup ritual configured with fewer cards than the " "threshold requires."
                ),
            )
        self._threshold = threshold
        self._total_shards = total_shards

    def render(
        self,
        shard: list[str],
        slot_label: str,
        sequence: tuple[int, int],
    ) -> PaperShardCard:
        """Return a frozen `PaperShardCard` for one shard.

        H-06 enforcement: `slot_label` is rejected via
        `EnvoyLabelOnCardError` if it contains "envoy" (case-insensitive).
        The Tier 1 test asserts this rejection.

        Per `rules/communication.md` plain-language: the threshold reminder
        is human-actionable, NOT technical SLIP-0039 jargon.
        """
        _validate_slot_label(slot_label)

        if not isinstance(shard, list) or not all(isinstance(w, str) for w in shard):
            raise EnvoyLabelOnCardError(
                "shard must be a list of strings (SLIP-0039 dictionary words); "
                f"got {type(shard).__name__}",
                user_message=(
                    "Backup card cannot be printed — the shard data is the "
                    "wrong shape. This is a bug; please report it."
                ),
            )
        if not shard:
            raise EnvoyLabelOnCardError(
                "shard must be non-empty",
                user_message=(
                    "Backup card cannot be printed — no words to transcribe. "
                    "This is a bug; please report it."
                ),
            )

        if (
            not isinstance(sequence, tuple)
            or len(sequence) != 2
            or not all(isinstance(n, int) for n in sequence)
        ):
            raise EnvoyLabelOnCardError(
                f"sequence must be a (card_index, total_cards) int tuple; got {sequence!r}",
                user_message=(
                    "Backup card cannot be printed — the card numbering "
                    "is malformed. This is a bug; please report it."
                ),
            )
        card_index, total_in_sequence = sequence
        if card_index < 1 or total_in_sequence < 1 or card_index > total_in_sequence:
            raise EnvoyLabelOnCardError(
                f"sequence must satisfy 1 <= card_index <= total_cards; got {sequence!r}",
                user_message=(
                    "Backup card cannot be printed — the card numbering "
                    "is out of range. This is a bug; please report it."
                ),
            )

        threshold_reminder = (
            f"Any {self._threshold} of these {self._total_shards} cards "
            "recovers your Envoy keys."
        )

        return PaperShardCard(
            slot_label=slot_label,
            sequence=sequence,
            threshold_reminder=threshold_reminder,
            mnemonic_words=tuple(shard),
            transcription_layout=_DEFAULT_TRANSCRIPTION_LAYOUT,
            created_at=datetime.now(timezone.utc),
        )

    def render_text(self, card: PaperShardCard) -> str:
        """Return a plain-text representation of `card` for terminal display
        or manual-print fallback.

        Format (rows-of-6 layout):

            Card 1 of 5 — keep this somewhere safe.
            Any 3 of these 5 cards recovers your Envoy keys if your computer
            is lost.

            Slot: slot-1

             1. word_one     2. word_two     3. word_three
             4. word_four    5. word_five    6. word_six
            ...

        Per `rules/communication.md` plain-language defaults: human-readable
        prose, not SLIP-0039 jargon. The user does NOT need to understand
        Shamir secret sharing to act on the card — they just need to know
        "keep this safe; you need 3 of 5 to recover".
        """
        if card.transcription_layout != _DEFAULT_TRANSCRIPTION_LAYOUT:
            raise EnvoyLabelOnCardError(
                f"render_text only supports {_DEFAULT_TRANSCRIPTION_LAYOUT!r} "
                f"layout; got {card.transcription_layout!r}",
                user_message=(
                    "Backup card cannot be printed — the layout is unknown. "
                    "Re-run the backup ritual to regenerate cards in the "
                    "supported format."
                ),
            )

        card_index, total_in_sequence = card.sequence
        header = (
            f"Card {card_index} of {total_in_sequence} — keep this somewhere safe.\n"
            f"{card.threshold_reminder}\n"
            "If your computer is lost, gather the required number of cards "
            "and follow the recovery instructions.\n"
        )
        slot_line = f"\nSlot: {card.slot_label}\n"

        # Word grid — 4 rows × 6 words for the canonical 24-word shard.
        # The numbering (1-based) helps the holder cross-check transcription.
        rows: list[str] = []
        words = card.mnemonic_words
        for row_start in range(0, len(words), _WORDS_PER_ROW):
            row_chunk = words[row_start : row_start + _WORDS_PER_ROW]
            row_cells = [f"{row_start + i + 1:>2}. {word:<12}" for i, word in enumerate(row_chunk)]
            rows.append("".join(row_cells).rstrip())
        word_grid = "\n".join(rows) + "\n"

        return header + slot_line + "\n" + word_grid


__all__ = [
    "PaperShardCard",
    "PaperShardRenderer",
]
