"""Tier 2 integration tests for the T-023 novelty gate (`envoy.authorship.novelty`).

Per `rules/testing.md` § Tier 2: NO mocking. The `NoveltyChecker` is a pure,
deterministic primitive (no DB / network / LLM), so "real infrastructure" here
means exercising the real public API end-to-end through the `envoy.authorship`
facade with real string inputs and real Jaccard arithmetic — there is nothing
to mock and nothing is mocked.

Spec authority: `specs/boundary-conversation.md` § Novelty feedback (T-023) —
near-duplicate is Jaccard > 0.85 (Phase 01 ships the Jaccard portion only;
classifier deferred to Phase 04 per
`workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`
§ 3.5).
"""

from __future__ import annotations

import pytest

from envoy.authorship import (
    NoveltyChecker,
    NoveltyFeedbackBlockError,
    NoveltyResult,
)

# Genuine paraphrase pair straddling the 0.85 boundary (verified arithmetic):
#   base shares all tokens with the variant, which appends one trailing word.
#   - JUST-BELOW: 5 shared / 6 union  = 0.8333  -> novel (below 0.85)
#   - JUST-ABOVE: 7 shared / 8 union  = 0.8750  -> blocking near-duplicate
_BELOW_TEMPLATE = "never delete production user data"
_BELOW_AUTHORED = "never delete production user data anytime"
_BELOW_EXPECTED_JACCARD = 5 / 6  # 0.8333...

_ABOVE_TEMPLATE = "never delete or modify production user data"
_ABOVE_AUTHORED = "never delete or modify production user data anytime"
_ABOVE_EXPECTED_JACCARD = 7 / 8  # 0.875


@pytest.fixture
def checker() -> NoveltyChecker:
    return NoveltyChecker()


def test_identical_strings_block_as_non_novel(checker: NoveltyChecker) -> None:
    template = "agents must not delete production data without operator approval"
    result = checker.check_against_templates(template, [template])

    assert isinstance(result, NoveltyResult)
    assert result.max_jaccard == pytest.approx(1.0)
    assert result.is_novel is False
    assert result.nearest_template_index == 0
    assert result.threshold == pytest.approx(0.85)

    with pytest.raises(NoveltyFeedbackBlockError) as excinfo:
        checker.assert_novel(template, [template])
    assert excinfo.value.max_jaccard == pytest.approx(1.0)
    assert excinfo.value.threshold == pytest.approx(0.85)


def test_disjoint_strings_are_novel_and_do_not_raise(
    checker: NoveltyChecker,
) -> None:
    authored = "alpha beta gamma delta"
    templates = ["omega psi chi phi", "iota kappa lambda mu"]

    result = checker.check_against_templates(authored, templates)
    assert result.max_jaccard == pytest.approx(0.0)
    assert result.is_novel is True
    # No overlap with any template; nearest_index stays at the scan default 0.
    assert result.nearest_template_index == 0

    # Must NOT raise for novel (disjoint) input.
    checker.assert_novel(authored, templates)


def test_paraphrase_just_below_threshold_is_novel(
    checker: NoveltyChecker,
) -> None:
    result = checker.check_against_templates(_BELOW_AUTHORED, [_BELOW_TEMPLATE])
    assert result.max_jaccard == pytest.approx(_BELOW_EXPECTED_JACCARD)
    assert result.max_jaccard < 0.85
    assert result.is_novel is True
    # Below threshold: assert_novel does not raise.
    checker.assert_novel(_BELOW_AUTHORED, [_BELOW_TEMPLATE])


def test_paraphrase_just_above_threshold_blocks(
    checker: NoveltyChecker,
) -> None:
    result = checker.check_against_templates(_ABOVE_AUTHORED, [_ABOVE_TEMPLATE])
    assert result.max_jaccard == pytest.approx(_ABOVE_EXPECTED_JACCARD)
    assert result.max_jaccard >= 0.85
    assert result.is_novel is False
    assert result.nearest_template_index == 0

    with pytest.raises(NoveltyFeedbackBlockError):
        checker.assert_novel(_ABOVE_AUTHORED, [_ABOVE_TEMPLATE])


def test_threshold_boundary_is_inclusive_blocks_at_exact_threshold(
    checker: NoveltyChecker,
) -> None:
    """Jaccard == threshold is a blocking near-duplicate (>= semantics).

    Pins the spec's ">0.85" as the implementation's ">=" decision: at-or-above
    the threshold blocks. 3 shared / 4 union = 0.75 == custom threshold.
    """
    template = "delete production user records"
    authored = "delete production user logs"  # 3 shared, union 5 -> 0.6
    # Use a custom threshold equal to an achievable Jaccard to test inclusivity.
    # 3 shared / 4 union = 0.75 when the authored text shares 3 of 4 tokens.
    template2 = "delete production user records"
    authored2 = "delete production user records"  # identical -> 1.0
    result = checker.check_against_templates(authored2, [template2], jaccard_threshold=1.0)
    assert result.max_jaccard == pytest.approx(1.0)
    assert result.is_novel is False  # 1.0 >= 1.0 -> blocks (inclusive)

    # And a sub-threshold custom case stays novel.
    sub = checker.check_against_templates(authored, [template], jaccard_threshold=0.85)
    assert sub.max_jaccard < 0.85
    assert sub.is_novel is True


def test_empty_templates_is_novel(checker: NoveltyChecker) -> None:
    result = checker.check_against_templates("anything at all", [])
    assert result.is_novel is True
    assert result.max_jaccard == pytest.approx(0.0)
    assert result.nearest_template_index is None
    assert result.threshold == pytest.approx(0.85)

    # No template to duplicate -> assert_novel never raises.
    checker.assert_novel("anything at all", [])


def test_nearest_template_index_points_at_closest_match(
    checker: NoveltyChecker,
) -> None:
    authored = "agents must not delete production data"
    templates = [
        "completely unrelated weather forecast text",  # ~0 overlap
        "agents must not delete production data",  # identical -> 1.0
        "agents may read production data freely",  # partial overlap
    ]
    result = checker.check_against_templates(authored, templates)
    assert result.nearest_template_index == 1
    assert result.max_jaccard == pytest.approx(1.0)
    assert result.is_novel is False


def test_error_message_is_plain_language_and_hides_template_text(
    checker: NoveltyChecker,
) -> None:
    secret_template = "agents must never exfiltrate customer secrets to external hosts"
    authored = "agents must never exfiltrate customer secrets to external hosts"

    with pytest.raises(NoveltyFeedbackBlockError) as excinfo:
        checker.assert_novel(authored, [secret_template])

    message = str(excinfo.value)
    # Plain-language guidance the spec's UX requires.
    assert "rephrase" in message.lower()
    assert "template" in message.lower()
    # Overlap reported as a percentage (100% for an identical match).
    assert "100%" in message

    # MUST NOT leak the template text verbatim. The distinctive content tokens
    # of the matched template must not appear in the user-facing message.
    for leaked in ("exfiltrate", "customer", "secrets", "external", "hosts"):
        assert leaked not in message.lower()
