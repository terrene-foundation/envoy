"""Tier 1 unit tests for envoy.grant_moment.novelty.NoveltyClassifier.

Per `rules/testing.md` § Tier 1: mocking allowed; <1s per test. The
classifier is a pure structural function (no I/O, no LLM, no infra),
so every rule branch can be exhausted with direct construction.

Covers `specs/grant-moment.md` § Novelty-aware friction (T-019)
invariants for T-03-53:
- HIGH_STAKES override wins regardless of the four novel-axis signals.
- ≥1 novel-axis True (no override) → NOVEL — every axis covered individually.
- ≥2 novel-axes True (no override) → NOVEL (multi-axis combo).
- All four novel-axes False, no override → FAMILIAR_REPEAT.
- NoveltyClass has exactly 3 members with spec-frozen string values.
- NoveltySignals is frozen (assignment raises FrozenInstanceError).
- Classifier is stateless: same input always same output across N calls.
- Total function: 100 randomized signals MUST all map into the 3-class
  set (guards against any future bug where a path returns None or raises).
"""

from __future__ import annotations

import random
from dataclasses import FrozenInstanceError

import pytest

from envoy.grant_moment.novelty import (
    NoveltyClass,
    NoveltyClassifier,
    NoveltySignals,
)


# ---------------------------------------------------------------------------
# Helper — explicit constructor so each test names exactly what it sets.
# ---------------------------------------------------------------------------


def _signals(
    *,
    unseen_recipient: bool = False,
    dollar_range_outside_p50: bool = False,
    tool_unseen_in_7d: bool = False,
    new_ngram_sequence: bool = False,
    high_stakes_override: bool = False,
) -> NoveltySignals:
    """Convenience constructor — keyword-only so test names are self-describing."""
    return NoveltySignals(
        unseen_recipient=unseen_recipient,
        dollar_range_outside_p50=dollar_range_outside_p50,
        tool_unseen_in_7d=tool_unseen_in_7d,
        new_ngram_sequence=new_ngram_sequence,
        high_stakes_override=high_stakes_override,
    )


# ---------------------------------------------------------------------------
# HIGH_STAKES override — wins regardless of other axes.
# ---------------------------------------------------------------------------


class TestHighStakesOverride:
    """Per spec § Novelty-aware friction: HIGH_STAKES override wins regardless."""

    def test_override_only_returns_high_stakes(self) -> None:
        classifier = NoveltyClassifier()
        result = classifier.classify(_signals(high_stakes_override=True))
        assert result is NoveltyClass.HIGH_STAKES

    def test_override_plus_unseen_recipient_returns_high_stakes(self) -> None:
        classifier = NoveltyClassifier()
        result = classifier.classify(_signals(high_stakes_override=True, unseen_recipient=True))
        assert result is NoveltyClass.HIGH_STAKES

    def test_override_with_all_novel_axes_true_returns_high_stakes(self) -> None:
        classifier = NoveltyClassifier()
        result = classifier.classify(
            _signals(
                high_stakes_override=True,
                unseen_recipient=True,
                dollar_range_outside_p50=True,
                tool_unseen_in_7d=True,
                new_ngram_sequence=True,
            )
        )
        assert result is NoveltyClass.HIGH_STAKES

    def test_override_with_all_novel_axes_false_returns_high_stakes(self) -> None:
        """Override fires even when the four novel axes are all False —
        the override is independent of the novel-axis evidence."""
        classifier = NoveltyClassifier()
        result = classifier.classify(_signals(high_stakes_override=True))
        assert result is NoveltyClass.HIGH_STAKES


# ---------------------------------------------------------------------------
# NOVEL — each of the four novel-axes individually flips the verdict.
# ---------------------------------------------------------------------------


class TestSingleNovelAxisReturnsNovel:
    """Per spec § Novelty-aware friction: any of the four novel-axis signals
    True (no override) → NOVEL. Each axis covered individually so a future
    bug that drops one axis from the OR fails one specific test."""

    def test_unseen_recipient_alone_returns_novel(self) -> None:
        classifier = NoveltyClassifier()
        result = classifier.classify(_signals(unseen_recipient=True))
        assert result is NoveltyClass.NOVEL

    def test_dollar_range_outside_p50_alone_returns_novel(self) -> None:
        classifier = NoveltyClassifier()
        result = classifier.classify(_signals(dollar_range_outside_p50=True))
        assert result is NoveltyClass.NOVEL

    def test_tool_unseen_in_7d_alone_returns_novel(self) -> None:
        classifier = NoveltyClassifier()
        result = classifier.classify(_signals(tool_unseen_in_7d=True))
        assert result is NoveltyClass.NOVEL

    def test_new_ngram_sequence_alone_returns_novel(self) -> None:
        classifier = NoveltyClassifier()
        result = classifier.classify(_signals(new_ngram_sequence=True))
        assert result is NoveltyClass.NOVEL


class TestMultipleNovelAxesReturnNovel:
    """Two-or-more novel axes True (no override) → still NOVEL. The OR
    is total over the four axes; this test covers a representative combo."""

    def test_unseen_recipient_plus_dollar_range_returns_novel(self) -> None:
        classifier = NoveltyClassifier()
        result = classifier.classify(_signals(unseen_recipient=True, dollar_range_outside_p50=True))
        assert result is NoveltyClass.NOVEL

    def test_all_four_novel_axes_true_returns_novel(self) -> None:
        """Without the override, four-of-four novel axes is still NOVEL
        (the override is the only path to HIGH_STAKES)."""
        classifier = NoveltyClassifier()
        result = classifier.classify(
            _signals(
                unseen_recipient=True,
                dollar_range_outside_p50=True,
                tool_unseen_in_7d=True,
                new_ngram_sequence=True,
            )
        )
        assert result is NoveltyClass.NOVEL


# ---------------------------------------------------------------------------
# FAMILIAR_REPEAT — the default when every signal is False.
# ---------------------------------------------------------------------------


class TestFamiliarRepeat:
    """Per spec § Novelty-aware friction: all four novel axes False and
    no override → FAMILIAR_REPEAT — the batch-to-envelope conversion path."""

    def test_all_signals_false_returns_familiar_repeat(self) -> None:
        classifier = NoveltyClassifier()
        result = classifier.classify(_signals())
        assert result is NoveltyClass.FAMILIAR_REPEAT


# ---------------------------------------------------------------------------
# Structural invariants — enum shape + dataclass freezeness.
# ---------------------------------------------------------------------------


class TestNoveltyClassEnumShape:
    """The wire-form discriminator MUST stay frozen to the three spec values."""

    def test_novelty_class_has_exactly_three_members(self) -> None:
        members = list(NoveltyClass)
        assert len(members) == 3

    def test_novelty_class_values_match_spec(self) -> None:
        # Spec-frozen string values — DO NOT rename without a deprecation
        # cycle (per rules/zero-tolerance.md Rule 6a).
        assert NoveltyClass.NOVEL.value == "novel"
        assert NoveltyClass.FAMILIAR_REPEAT.value == "familiar_repeat"
        assert NoveltyClass.HIGH_STAKES.value == "high_stakes"

    def test_novelty_class_is_str_subclass(self) -> None:
        """Matches the convention in envoy.grant_moment.state_machine —
        values flow through JSON wire shapes as their declared names."""
        assert isinstance(NoveltyClass.NOVEL, str)


class TestNoveltySignalsImmutable:
    """The dataclass is ``frozen=True`` so callers cannot mutate a signals
    object after construction — guards against accidental aliasing bugs
    when the same signals object is reused across multiple classify calls."""

    def test_assignment_to_field_raises_frozen_instance_error(self) -> None:
        signals = _signals(unseen_recipient=True)
        with pytest.raises(FrozenInstanceError):
            signals.unseen_recipient = False  # type: ignore[misc]

    def test_assignment_to_override_field_raises_frozen_instance_error(
        self,
    ) -> None:
        signals = _signals()
        with pytest.raises(FrozenInstanceError):
            signals.high_stakes_override = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Statelessness — same input, same output across many calls.
# ---------------------------------------------------------------------------


class TestClassifierIsStateless:
    """Per the module docstring: stateless and deterministic. Multiple calls
    on the same instance with the same input MUST return the same output."""

    def test_repeated_classify_returns_same_result(self) -> None:
        classifier = NoveltyClassifier()
        signals = _signals(unseen_recipient=True)
        results = [classifier.classify(signals) for _ in range(50)]
        assert all(r is NoveltyClass.NOVEL for r in results)

    def test_alternating_inputs_each_resolve_independently(self) -> None:
        """A classifier that accidentally stored state between calls would
        leak the prior verdict; alternating inputs catches that."""
        classifier = NoveltyClassifier()
        familiar = _signals()
        novel = _signals(tool_unseen_in_7d=True)
        high = _signals(high_stakes_override=True)
        for _ in range(20):
            assert classifier.classify(familiar) is NoveltyClass.FAMILIAR_REPEAT
            assert classifier.classify(novel) is NoveltyClass.NOVEL
            assert classifier.classify(high) is NoveltyClass.HIGH_STAKES


# ---------------------------------------------------------------------------
# Totality — every possible signals input maps to exactly one class.
# ---------------------------------------------------------------------------


class TestClassifierIsTotal:
    """The classification rules are TOTAL: every NoveltySignals input MUST
    map to exactly one NoveltyClass value; classify MUST NOT raise. This
    guards against any future bug where a code path returns None or
    propagates an exception out of classify."""

    def test_all_thirtytwo_input_combinations_resolve_to_valid_class(
        self,
    ) -> None:
        """Exhaustively exercise the 2^5 = 32 boolean input combinations.
        Pure-function classifier means this is still <1s."""
        classifier = NoveltyClassifier()
        valid = {
            NoveltyClass.NOVEL,
            NoveltyClass.FAMILIAR_REPEAT,
            NoveltyClass.HIGH_STAKES,
        }
        for bitmask in range(32):
            signals = _signals(
                unseen_recipient=bool(bitmask & 1),
                dollar_range_outside_p50=bool(bitmask & 2),
                tool_unseen_in_7d=bool(bitmask & 4),
                new_ngram_sequence=bool(bitmask & 8),
                high_stakes_override=bool(bitmask & 16),
            )
            result = classifier.classify(signals)
            assert (
                result in valid
            ), f"bitmask={bitmask:05b} produced out-of-range result: {result!r}"

    def test_randomized_inputs_resolve_to_valid_class(self) -> None:
        """Hundred deterministic random signals — guards against any future
        non-boolean-input handling that slips a None or unexpected value
        into the classifier. Seeded so failures reproduce."""
        classifier = NoveltyClassifier()
        rng = random.Random(0xCAFEBABE)  # deterministic per rules/testing.md
        valid = {
            NoveltyClass.NOVEL,
            NoveltyClass.FAMILIAR_REPEAT,
            NoveltyClass.HIGH_STAKES,
        }
        for _ in range(100):
            signals = _signals(
                unseen_recipient=rng.choice([True, False]),
                dollar_range_outside_p50=rng.choice([True, False]),
                tool_unseen_in_7d=rng.choice([True, False]),
                new_ngram_sequence=rng.choice([True, False]),
                high_stakes_override=rng.choice([True, False]),
            )
            result = classifier.classify(signals)
            assert result in valid
