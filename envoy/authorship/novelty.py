"""envoy.authorship.novelty — Jaccard near-duplicate gate for user-authored
envelope constraints (T-023: Authorship-Score gaming at authoring time).

Per `specs/boundary-conversation.md` § Novelty feedback (T-023):

    If user-authored answer compiles to near-duplicate (Jaccard > 0.85 or
    adversarial-wording classifier > 0.8) of template constraint, UX prompts
    user to rephrase or re-choose.

Per `workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`
§ 3.5, Phase 01 ships the **Jaccard portion only** — lexical near-duplicate
detection against local-cache template constraints. The adversarial-wording
classifier is a Phase-04 deferral (the spec's OR is permissive — it does NOT
name the classifier as Phase-01 mandatory).

This module is pure, deterministic, dependency-free Python: no LLM, no network,
no envelope/template imports. The caller (a later shard) supplies the
``template_texts`` drawn from the local Foundation-Verified template cache.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "NoveltyChecker",
    "NoveltyFeedbackBlockError",
    "NoveltyResult",
]

# Tokenizer: lowercase, split on any run of non-alphanumeric characters.
# Splitting on whitespace + punctuation means "DROP TABLE users;" and
# "drop table users" tokenize identically — the lexical-overlap measure
# we want for near-duplicate detection of authored constraint text.
_TOKEN_SPLIT_RE = re.compile(r"[^0-9a-z]+")


def _tokenize(text: str) -> frozenset[str]:
    """Return the lowercase token *set* of ``text``.

    Whitespace and punctuation are treated as token separators; empty
    tokens (from leading/trailing/consecutive separators) are dropped.
    A set (not a multiset) is used because Jaccard is a set measure.
    """
    return frozenset(tok for tok in _TOKEN_SPLIT_RE.split(text.lower()) if tok)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Token-set Jaccard similarity in [0.0, 1.0].

    Convention for empty inputs: if BOTH token sets are empty the texts are
    vacuously identical (1.0); if exactly one is empty there is zero overlap
    (0.0). This keeps "two blank strings are duplicates" intuitive while a
    blank authored string never near-matches a non-blank template.
    """
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


@dataclass(frozen=True)
class NoveltyResult:
    """Outcome of a novelty check against a set of template constraints.

    Attributes:
        is_novel: True when the authored text is sufficiently distinct from
            every template (max Jaccard strictly below ``threshold``). False
            signals a blocking near-duplicate.
        max_jaccard: The highest token-set Jaccard similarity observed across
            all templates (0.0 when ``template_texts`` was empty).
        nearest_template_index: Index into the caller's ``template_texts`` of
            the closest match, or None when ``template_texts`` was empty.
        threshold: The Jaccard threshold applied for this check (echoed back
            so callers and logs have the full decision context).
    """

    is_novel: bool
    max_jaccard: float
    nearest_template_index: int | None
    threshold: float


class NoveltyFeedbackBlockError(Exception):
    """Raised when an authored constraint is a near-duplicate of a template.

    Carries the numeric decision context (``max_jaccard`` and ``threshold``)
    so a UX layer can render a progress-style overlap indicator. The message
    is plain-language per `rules/communication.md` and MUST NOT embed the
    matched template text verbatim — the user is told *that* they overlapped
    and *by how much*, not *which* Foundation constraint they nearly copied.
    """

    def __init__(self, message: str, *, max_jaccard: float, threshold: float):
        super().__init__(message)
        self.max_jaccard = max_jaccard
        self.threshold = threshold


class NoveltyChecker:
    """Detects lexical near-duplicates of Foundation-Verified templates.

    Stateless and deterministic: the same inputs always produce the same
    ``NoveltyResult``. Construct once and reuse, or instantiate ad hoc — there
    is no per-instance state.
    """

    def check_against_templates(
        self,
        authored_text: str,
        template_texts: list[str],
        *,
        jaccard_threshold: float = 0.85,
    ) -> NoveltyResult:
        """Compare ``authored_text`` against each template by token-set Jaccard.

        If the maximum Jaccard similarity across ``template_texts`` is at or
        above ``jaccard_threshold``, the authored text is a blocking
        near-duplicate (``is_novel=False``); otherwise it is novel
        (``is_novel=True``).

        Empty ``template_texts`` ⇒ ``is_novel=True``, ``max_jaccard=0.0``,
        ``nearest_template_index=None`` (nothing to be a duplicate of).
        """
        if not template_texts:
            return NoveltyResult(
                is_novel=True,
                max_jaccard=0.0,
                nearest_template_index=None,
                threshold=jaccard_threshold,
            )

        authored_tokens = _tokenize(authored_text)
        max_jaccard = 0.0
        nearest_index = 0
        for index, template in enumerate(template_texts):
            score = _jaccard(authored_tokens, _tokenize(template))
            if score > max_jaccard:
                max_jaccard = score
                nearest_index = index

        return NoveltyResult(
            is_novel=max_jaccard < jaccard_threshold,
            max_jaccard=max_jaccard,
            nearest_template_index=nearest_index,
            threshold=jaccard_threshold,
        )

    def assert_novel(
        self,
        authored_text: str,
        template_texts: list[str],
        *,
        jaccard_threshold: float = 0.85,
    ) -> None:
        """Raise ``NoveltyFeedbackBlockError`` if the authored text is a
        blocking near-duplicate; return None otherwise.

        The error message is plain-language and reports the overlap as a
        percentage without leaking the matched template text.
        """
        result = self.check_against_templates(
            authored_text,
            template_texts,
            jaccard_threshold=jaccard_threshold,
        )
        if not result.is_novel:
            overlap_pct = round(result.max_jaccard * 100)
            raise NoveltyFeedbackBlockError(
                f"This rule is too similar to a built-in template "
                f"({overlap_pct}% overlap). Please rephrase it in your own "
                f"words or pick the template directly.",
                max_jaccard=result.max_jaccard,
                threshold=result.threshold,
            )
