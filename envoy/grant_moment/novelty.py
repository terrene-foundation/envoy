"""envoy.grant_moment.novelty — three-class friction classifier for Grant
Moment requests (T-019 / spec § Novelty-aware friction).

Implements the ``NoveltyClassifier`` per `specs/grant-moment.md` § Novelty-aware
friction (T-019):

    - **Novel pattern** (unseen recipient, new dollar range outside ±25% of
      30-day P50, tool unseen in last 7 days, new N-gram sequence) →
      5s read-delay + double-tap + cross-channel confirm for high-stakes.
    - **Familiar repeat** → batch-to-envelope conversion offer at Weekly
      Posture Review.
    - Primary-channel binding — high-stakes Grant Moments render ONLY on
      user's designated primary channel.

Per `workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
§ 3 step 8, Phase 01 ships the classifier as a **pure structural function**:
the caller (later shard: ``EnvoyGrantMomentRuntime``) computes the per-axis
history signals (Ledger queries, P50 rolling-window math, N-gram cache
lookups) and feeds them in as ``NoveltySignals``. This module rolls the
four novel-axis bools + one high-stakes override into one of three
``NoveltyClass`` values.

This separation lets Tier-1 tests exhaust every rule branch with zero
infra deps. Per `rules/agent-reasoning.md`: NO LLM/keyword routing —
the classifier is pure structural rules; LLM-or-history work happens
in the caller, not here.

DISTINCT from ``envoy.authorship.novelty.NoveltyChecker`` (T-023 Jaccard
near-duplicate gate for user-AUTHORED CONSTRAINTS at Boundary Conversation
S3/S5). That primitive is a binary check; this classifier is ternary.
Different packages, different APIs, no shared code.

This module is pure Python; ZERO dependencies on other envoy packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "NoveltyClass",
    "NoveltyClassifier",
    "NoveltySignals",
]


class NoveltyClass(str, Enum):
    """The three friction classes per spec § Novelty-aware friction.

    Inherits from ``str`` so values flow through JSON wire shapes and
    log lines as their declared names ("novel", "familiar_repeat",
    "high_stakes") without an explicit ``.value`` access — matches the
    convention in ``envoy.grant_moment.state_machine.GrantMomentState``.

    Spec-frozen values (do NOT rename — wire-form discriminator):

    - ``NOVEL`` — at least one of the four novel-axis signals fired;
      runtime applies the 5s read-delay + double-tap friction.
    - ``FAMILIAR_REPEAT`` — every novel-axis signal is False; runtime
      offers batch-to-envelope conversion at Weekly Posture Review.
    - ``HIGH_STAKES`` — explicit override (e.g. dollar amount above
      microdollar threshold OR data_classification in
      {"Restricted","HighlyConfidential"}); runtime adds primary-channel
      binding (ChannelHandoff consumes ``request.primary_only=True``).
    """

    NOVEL = "novel"
    FAMILIAR_REPEAT = "familiar_repeat"
    HIGH_STAKES = "high_stakes"


@dataclass(frozen=True, slots=True)
class NoveltySignals:
    """Per-axis observations the caller has already computed.

    The classifier is pure-functional; it does NOT itself compute history,
    reach into the Ledger, or query a feature store. The caller (later
    shard: ``EnvoyGrantMomentRuntime``) supplies the per-axis signals;
    this classifier rolls them up into one of three ``NoveltyClass`` values.

    Each axis is a boolean: True means "this signal contributes evidence
    toward NOVEL". ``high_stakes_override`` is an explicit high-stakes
    flag (dollar+classification threshold) supplied independently.

    Attributes:
        unseen_recipient: axis 1 — recipient not seen in caller's history
            window (per spec § "unseen recipient").
        dollar_range_outside_p50: axis 2 — request amount falls outside
            ±25% of the 30-day P50 dollar band (per spec § "new dollar
            range outside ±25% of 30-day P50").
        tool_unseen_in_7d: axis 3 — tool name not invoked in the last
            7 days of caller's history (per spec § "tool unseen in last
            7 days").
        new_ngram_sequence: axis 4 — textual N-gram of request payload
            unseen in caller's N-gram cache (per spec § "new N-gram
            sequence").
        high_stakes_override: explicit high-stakes flag computed by the
            caller from dollar amount + data_classification (per spec §
            "high-stakes Grant Moments render ONLY on user's designated
            primary channel"). Overrides the four novel-axis signals.
    """

    unseen_recipient: bool
    dollar_range_outside_p50: bool
    tool_unseen_in_7d: bool
    new_ngram_sequence: bool
    high_stakes_override: bool


class NoveltyClassifier:
    """Three-class classifier per spec § Novelty-aware friction (T-019).

    Stateless and deterministic: the same ``NoveltySignals`` input always
    produces the same ``NoveltyClass`` output. Construct once and reuse,
    or instantiate ad hoc — there is no per-instance state.

    Classification rules (evaluated in order — first match wins):

    1. ``high_stakes_override=True`` → ``NoveltyClass.HIGH_STAKES``
       (regardless of the four novel-axis signals).
    2. Any of the four novel-axis signals True
       (``unseen_recipient`` / ``dollar_range_outside_p50`` /
       ``tool_unseen_in_7d`` / ``new_ngram_sequence``) →
       ``NoveltyClass.NOVEL``.
    3. All four novel-axis signals False and no override →
       ``NoveltyClass.FAMILIAR_REPEAT``.

    The rules are TOTAL: every possible ``NoveltySignals`` input maps to
    exactly one ``NoveltyClass``. ``classify`` does NOT raise.
    """

    def classify(self, signals: NoveltySignals) -> NoveltyClass:
        """Roll ``signals`` into one of three ``NoveltyClass`` values.

        See class docstring for the three-rule evaluation order.
        """
        if signals.high_stakes_override:
            return NoveltyClass.HIGH_STAKES
        if (
            signals.unseen_recipient
            or signals.dollar_range_outside_p50
            or signals.tool_unseen_in_7d
            or signals.new_ngram_sequence
        ):
            return NoveltyClass.NOVEL
        return NoveltyClass.FAMILIAR_REPEAT
