"""Tier 1: T-02-35 — `PaperShardRenderer` H-06 enforcement + plain-language output.

Source: shard `01-analysis/15-shamir-recovery-implementation.md` § 3.2 +
`specs/shamir-recovery.md` § Card format (line 28-29).

H-06: NO 'Envoy' label, NO real names; opaque slot labels only. The renderer
raises `EnvoyLabelOnCardError` if the supplied `slot_label` violates this
constraint. `render_text` produces plain-language output per
`rules/communication.md` (no SLIP-0039 jargon).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from envoy.shamir import (
    EnvoyLabelOnCardError,
    PaperShardCard,
    PaperShardRenderer,
)

# A representative 24-word SLIP-0039 mnemonic shape. The renderer treats
# the words as opaque strings — dictionary membership is enforced by the
# kailash.trust.vault.shamir layer.
_SAMPLE_24_WORDS = [
    "academic",
    "acid",
    "acne",
    "acquire",
    "acrobat",
    "active",
    "actress",
    "adapt",
    "adequate",
    "adjust",
    "admit",
    "adorn",
    "adult",
    "advance",
    "advocate",
    "afraid",
    "again",
    "agency",
    "agree",
    "aide",
    "aircraft",
    "airline",
    "airport",
    "ajar",
]


class TestPaperShardCardDataclass:
    def test_card_is_frozen(self) -> None:
        card = PaperShardCard(
            slot_label="slot-1",
            sequence=(1, 5),
            threshold_reminder="Any 3 of these 5 cards recovers your Envoy keys.",
            mnemonic_words=tuple(_SAMPLE_24_WORDS),
            transcription_layout="rows-of-6",
            created_at=datetime.now(timezone.utc),
        )
        with pytest.raises((FrozenInstanceError, AttributeError)):
            card.slot_label = "slot-2"  # type: ignore[misc]

    def test_card_round_trip_dict(self) -> None:
        original = PaperShardCard(
            slot_label="slot-3",
            sequence=(3, 5),
            threshold_reminder="Any 3 of these 5 cards recovers your Envoy keys.",
            mnemonic_words=tuple(_SAMPLE_24_WORDS),
            transcription_layout="rows-of-6",
            created_at=datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc),
        )
        round_tripped = PaperShardCard.from_dict(original.to_dict())
        assert round_tripped == original


class TestRendererBasicOutput:
    def test_renders_paper_shard_card(self) -> None:
        renderer = PaperShardRenderer(threshold=3, total_shards=5)
        card = renderer.render(_SAMPLE_24_WORDS, "slot-1", (1, 5))
        assert isinstance(card, PaperShardCard)
        assert card.slot_label == "slot-1"
        assert card.sequence == (1, 5)
        assert card.mnemonic_words == tuple(_SAMPLE_24_WORDS)
        assert card.transcription_layout == "rows-of-6"
        assert card.created_at.tzinfo is not None  # timezone-aware

    def test_threshold_reminder_uses_configured_values(self) -> None:
        renderer = PaperShardRenderer(threshold=4, total_shards=7)
        card = renderer.render(_SAMPLE_24_WORDS, "slot-2", (2, 7))
        assert "Any 4 of these 7" in card.threshold_reminder

    def test_mnemonic_words_stored_as_tuple(self) -> None:
        """Per `rules/eatp.md` + `rules/trust-plane-security.md` MUST NOT
        Rule 4 (frozen constraint dataclasses): the mnemonic words are an
        immutable tuple, not a mutable list.
        """
        renderer = PaperShardRenderer()
        card = renderer.render(_SAMPLE_24_WORDS, "slot-1", (1, 5))
        assert isinstance(card.mnemonic_words, tuple)


class TestH06SlotLabelEnforcement:
    """H-06 fix per `specs/shamir-recovery.md` line 29: NO 'Envoy' label;
    NO name. The renderer rejects any slot_label containing the forbidden
    token at render time.
    """

    def test_render_rejects_envoy_label(self) -> None:
        """Per security review M-1 on PR #15, the validator now applies a
        whitelist regex `^slot-\\d+$` BEFORE the substring blacklist —
        "Envoy Backup" fails the whitelist (contains uppercase + space).
        """
        renderer = PaperShardRenderer()
        with pytest.raises(EnvoyLabelOnCardError, match="opaque pattern"):
            renderer.render(_SAMPLE_24_WORDS, "Envoy Backup", (1, 5))

    def test_render_rejects_envoy_label_case_insensitive(self) -> None:
        renderer = PaperShardRenderer()
        with pytest.raises(EnvoyLabelOnCardError):
            renderer.render(_SAMPLE_24_WORDS, "envoy-1", (1, 5))
        with pytest.raises(EnvoyLabelOnCardError):
            renderer.render(_SAMPLE_24_WORDS, "ENVOY", (1, 5))

    def test_render_rejects_unicode_confusable(self) -> None:
        """Per security review M-1 on PR #15: Unicode confusables
        (`ＥＮＶＯＹ` fullwidth U+FF25... or `еnvoy` Cyrillic) lower-case
        to non-`envoy` and bypass the substring blacklist alone. The
        ASCII-only check + whitelist regex defeat them.
        """
        renderer = PaperShardRenderer()
        with pytest.raises(EnvoyLabelOnCardError, match="non-ASCII"):
            renderer.render(_SAMPLE_24_WORDS, "ＥＮＶＯＹ", (1, 5))
        # Cyrillic look-alike — `е` is U+0435, NOT ASCII `e`.
        with pytest.raises(EnvoyLabelOnCardError, match="non-ASCII"):
            renderer.render(_SAMPLE_24_WORDS, "еnvoy", (1, 5))

    def test_render_rejects_control_char_injection(self) -> None:
        """Per security review M-2 on PR #15: control chars in slot
        labels corrupt the rendered card layout AND can hide injected
        names from a substring-only check (`slot-1\\nEnvoy`,
        `slot-1\\x00Alice`). Whitelist `^slot-\\d+$` rejects.
        """
        renderer = PaperShardRenderer()
        with pytest.raises(EnvoyLabelOnCardError, match="opaque pattern"):
            renderer.render(_SAMPLE_24_WORDS, "slot-1\nEnvoy", (1, 5))
        with pytest.raises(EnvoyLabelOnCardError, match="opaque pattern"):
            renderer.render(_SAMPLE_24_WORDS, "slot-1\x00Alice", (1, 5))
        with pytest.raises(EnvoyLabelOnCardError, match="opaque pattern"):
            renderer.render(_SAMPLE_24_WORDS, "slot-1\rBob", (1, 5))

    def test_render_accepts_canonical_slot_label(self) -> None:
        """Whitelist regex `^slot-\\d+$` accepts the canonical opaque
        form — exact ASCII `slot-` prefix + ≥1 ASCII digits.
        """
        renderer = PaperShardRenderer()
        for n in (1, 5, 9, 99, 1000):
            card = renderer.render(_SAMPLE_24_WORDS, f"slot-{n}", (1, 5))
            assert card.slot_label == f"slot-{n}"

    def test_render_rejects_custom_label_form(self) -> None:
        """Whitelist regex rejects any non-canonical form — Phase 04
        relaxation MUST explicitly opt-in via spec extension."""
        renderer = PaperShardRenderer()
        for label in ("backup-1", "card_1", "1", "slot-", "slot-A1", "Slot-1"):
            with pytest.raises(EnvoyLabelOnCardError, match="opaque pattern"):
                renderer.render(_SAMPLE_24_WORDS, label, (1, 5))

    def test_render_rejects_empty_slot_label(self) -> None:
        renderer = PaperShardRenderer()
        with pytest.raises(EnvoyLabelOnCardError):
            renderer.render(_SAMPLE_24_WORDS, "", (1, 5))

    def test_envoy_label_error_carries_user_message(self) -> None:
        renderer = PaperShardRenderer()
        try:
            renderer.render(_SAMPLE_24_WORDS, "Envoy", (1, 5))
        except EnvoyLabelOnCardError as exc:
            assert exc.user_message  # plain-language form is set
            # Per `rules/communication.md`: the message must explain WHY
            # in user terms — not just echo the technical violation.
            assert (
                "private envelope" in exc.user_message.lower()
                or "real name" in exc.user_message.lower()
                or "opaque" in exc.user_message.lower()
            )


class TestRenderTextPlainLanguage:
    """Per `rules/communication.md`: render_text output is plain-language,
    NOT SLIP-0039 jargon. The user does not need to understand Shamir
    secret sharing to act on the card.
    """

    def test_render_text_contains_card_sequence(self) -> None:
        renderer = PaperShardRenderer(threshold=3, total_shards=5)
        card = renderer.render(_SAMPLE_24_WORDS, "slot-1", (1, 5))
        text = renderer.render_text(card)
        assert "Card 1 of 5" in text

    def test_render_text_contains_threshold_reminder(self) -> None:
        renderer = PaperShardRenderer(threshold=3, total_shards=5)
        card = renderer.render(_SAMPLE_24_WORDS, "slot-1", (1, 5))
        text = renderer.render_text(card)
        assert "Any 3 of these 5" in text
        assert "recover" in text.lower()

    def test_render_text_does_not_contain_slip39_jargon(self) -> None:
        """Plain-language defaults: avoid 'SLIP-0039', 'Shamir', 'mnemonic',
        'threshold', 'shard' as user-facing terms.
        """
        renderer = PaperShardRenderer()
        card = renderer.render(_SAMPLE_24_WORDS, "slot-1", (1, 5))
        text = renderer.render_text(card)
        for jargon in ["SLIP-0039", "Shamir", "shard", "mnemonic", "threshold"]:
            assert jargon.lower() not in text.lower(), (
                f"render_text contained jargon term {jargon!r}; "
                "use plain-language phrasing per rules/communication.md"
            )

    def test_render_text_contains_slot_label(self) -> None:
        renderer = PaperShardRenderer()
        card = renderer.render(_SAMPLE_24_WORDS, "slot-3", (3, 5))
        text = renderer.render_text(card)
        assert "slot-3" in text

    def test_render_text_contains_all_mnemonic_words(self) -> None:
        renderer = PaperShardRenderer()
        card = renderer.render(_SAMPLE_24_WORDS, "slot-1", (1, 5))
        text = renderer.render_text(card)
        for word in _SAMPLE_24_WORDS:
            assert word in text


class TestRendererInputValidation:
    def test_render_rejects_malformed_shard(self) -> None:
        renderer = PaperShardRenderer()
        with pytest.raises(EnvoyLabelOnCardError, match="shard"):
            renderer.render([1, 2, 3], "slot-1", (1, 5))  # type: ignore[list-item]

    def test_render_rejects_empty_shard(self) -> None:
        renderer = PaperShardRenderer()
        with pytest.raises(EnvoyLabelOnCardError, match="non-empty"):
            renderer.render([], "slot-1", (1, 5))

    def test_render_rejects_malformed_sequence(self) -> None:
        renderer = PaperShardRenderer()
        with pytest.raises(EnvoyLabelOnCardError, match="sequence"):
            renderer.render(_SAMPLE_24_WORDS, "slot-1", (0, 5))
        with pytest.raises(EnvoyLabelOnCardError, match="sequence"):
            renderer.render(_SAMPLE_24_WORDS, "slot-1", (6, 5))

    def test_renderer_rejects_threshold_below_minimum(self) -> None:
        with pytest.raises(EnvoyLabelOnCardError, match="threshold"):
            PaperShardRenderer(threshold=1, total_shards=5)

    def test_renderer_rejects_total_below_threshold(self) -> None:
        with pytest.raises(EnvoyLabelOnCardError, match="total_shards"):
            PaperShardRenderer(threshold=5, total_shards=3)
