# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-8: session-envelope byte-identity across channels + time.

Acceptance gate per `workspaces/phase-01-mvp/02-mvp-objectives.md` line 116
+ `workspaces/phase-01-mvp/02-plans/02-test-strategy.md` § EC-8 line 254:

> Day-1 envelope compiled on CLI; Day-6 action initiating from Slack reads
> the SAME ``content_hash`` byte-identical.

The byte-identity invariant is the spine of EC-8 sub-condition (a) (zero
state-drift across a 7-day operating window): every channel adapter that
consults the active envelope MUST see the same canonical bytes and the
same ``content_hash``, regardless of (a) which channel context constructed
the compiler, (b) which day the compile is re-run, (c) which compiler
instance computes it.  Without this invariant, the "channel-as-UI" thesis
(`02-mvp-objectives.md` line 116) is broken — different channels see
different envelopes for the same session.

The existing ``test_envelope_compiler_monotonic_tightening_at_compile.py``
covers byte-stability for ONE compiler instance compiling the same input
twice.  This file extends the invariant to the cross-instance, cross-time
shape EC-8 mandates: **two distinct ``EnvelopeCompiler`` instances**
(simulating CLI-context Day-1 and Slack-context Day-6) compiling the same
``EnvelopeConfigInput`` MUST produce byte-identical ``canonical_bytes``
AND byte-identical ``content_hash``.

Per `rules/probe-driven-verification.md` MUST-3 (no LLM): every assertion
is structural byte-equality + sha256 hex-equality.  Per `rules/testing.md`
§ Tier 2: real ``EnvelopeCompiler`` + real canonical-bytes pipeline; NO
mocking.
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

from envoy.boundary_conversation.envelope_assembler import EnvelopeConfigInputAssembler
from envoy.envelope import EnvelopeCompiler, EnvelopeConfig, LocalTemplateResolver
from envoy.envelope.types import AlgorithmIdentifier, EnvelopeMetadata


_FIXED_ENVELOPE_ID = "envelope-ec8-cross-channel-fixture"
PRINCIPAL = "alice@example"


def _feed_canonical_session_inputs(assembler: EnvelopeConfigInputAssembler) -> None:
    """The boundary-conversation extraction set a Day-1 onboarding produces.

    Mirrors `_feed_minimal_set` in the monotonic-tightening sibling test —
    the S1..S5 extractions the BoundaryConversationRuntime feeds the
    assembler at S9 compile.
    """
    assembler.feed(
        "S1_money",
        {"monthly_ceiling_microdollars": 250_000_000},
    )
    assembler.feed(
        "S2_people",
        {"blocked_contacts": ["ex@x.com"]},
    )
    assembler.feed(
        "S3_topics",
        {"blocked_topic_rules": ["no political endorsements"]},
    )
    assembler.feed(
        "S4_hours",
        {"operating_hours": {"days": ["mon", "tue"], "tz": "UTC"}},
    )
    assembler.feed(
        "S5_first_task",
        {"first_task_intent": {"goal": "summarize my unread newsletters"}},
    )


def _compile_with_fresh_instance(*, tmp_path: Path, channel_context: str) -> EnvelopeConfig:
    """Compile the canonical session input with a NEWLY-constructed
    ``EnvelopeCompiler`` instance.

    The ``channel_context`` is intentionally a marker only — the compiler
    does NOT consume it; the parameter exists to make explicit at the
    call-site WHICH channel-context the compile is simulating, so the test
    body reads as "Day-1 from CLI vs Day-6 from Slack" rather than
    "instance 1 vs instance 2".  Per `rules/agent-reasoning.md`: structural
    plumbing — no LLM, no channel-conditional logic.
    """
    del channel_context  # name carries documentation value only
    assembler = EnvelopeConfigInputAssembler()
    _feed_canonical_session_inputs(assembler)
    raw_input = assembler.assemble()
    pinned_metadata = EnvelopeMetadata(envelope_id=_FIXED_ENVELOPE_ID)
    pinned = dataclasses.replace(raw_input, metadata=pinned_metadata)
    # Fresh compiler instance each call — the EC-8 invariant is that
    # instance identity does NOT influence canonical bytes.
    compiler = EnvelopeCompiler(
        template_resolver=LocalTemplateResolver(tmp_path),
        algorithm_identifier=AlgorithmIdentifier(),
    )
    return compiler.compile(pinned, principal_id=PRINCIPAL)


class TestSessionEnvelopeByteIdentityAcrossChannels:
    """EC-8 sub-condition (a): cross-channel state-equivalence at the
    envelope layer."""

    def test_day1_cli_and_day6_slack_canonical_bytes_byte_identical(self, tmp_path: Path) -> None:
        """Day-1 CLI envelope ``canonical_bytes`` == Day-6 Slack envelope
        ``canonical_bytes``, across two distinct ``EnvelopeCompiler``
        instances.  Closes the cross-channel state-drift class for the
        envelope surface."""
        day1_cli = _compile_with_fresh_instance(tmp_path=tmp_path, channel_context="cli")
        day6_slack = _compile_with_fresh_instance(tmp_path=tmp_path, channel_context="slack")

        assert day1_cli.canonical_bytes == day6_slack.canonical_bytes, (
            "Cross-channel envelope drift: Day-1 CLI canonical_bytes "
            f"({len(day1_cli.canonical_bytes)}B) != Day-6 Slack canonical_bytes "
            f"({len(day6_slack.canonical_bytes)}B). "
            "EC-8 channel-as-UI invariant is broken."
        )

    def test_day1_cli_and_day6_slack_content_hash_byte_identical(self, tmp_path: Path) -> None:
        """The Trust Store / Grant Moment surface keys on ``content_hash``;
        a divergent hash routes one channel to a different envelope row
        than another — exactly the EC-8 state-drift failure mode."""
        day1_cli = _compile_with_fresh_instance(tmp_path=tmp_path, channel_context="cli")
        day6_slack = _compile_with_fresh_instance(tmp_path=tmp_path, channel_context="slack")

        assert day1_cli.content_hash == day6_slack.content_hash
        # Defense in depth — explicitly re-derive the hash from the
        # canonical_bytes on both sides; if the compiler somehow stamped
        # different hashes onto identical bytes (bug in content_hash
        # derivation), this catches it.
        rederived_cli = hashlib.sha256(day1_cli.canonical_bytes).hexdigest()
        rederived_slack = hashlib.sha256(day6_slack.canonical_bytes).hexdigest()
        assert day1_cli.content_hash == rederived_cli
        assert day6_slack.content_hash == rederived_slack

    def test_envelope_id_pinned_across_compiler_instances(self, tmp_path: Path) -> None:
        """The fixed ``envelope_id`` we pin on the input metadata MUST
        survive both compile passes — a regression here would shadow the
        byte-identity claim (different ids ⇒ different metadata ⇒
        legitimately different canonical_bytes)."""
        day1_cli = _compile_with_fresh_instance(tmp_path=tmp_path, channel_context="cli")
        day6_slack = _compile_with_fresh_instance(tmp_path=tmp_path, channel_context="slack")

        assert day1_cli.metadata.envelope_id == _FIXED_ENVELOPE_ID
        assert day6_slack.metadata.envelope_id == _FIXED_ENVELOPE_ID

    def test_four_channels_all_byte_identical_to_cli_baseline(self, tmp_path: Path) -> None:
        """The EC-8 acceptance battery touches ≥4 of 8 channels per
        `02-test-strategy.md` line 260. The byte-identity invariant MUST
        hold across the full 5-channel Phase-01 set (CLI + Web + Telegram
        + Slack + Discord per `02-mvp-objectives.md` § 5 EC-7
        DEGRADE-ACCEPTABLE de-scope #1)."""
        baseline = _compile_with_fresh_instance(tmp_path=tmp_path, channel_context="cli")
        for channel in ("web", "telegram", "slack", "discord"):
            other = _compile_with_fresh_instance(tmp_path=tmp_path, channel_context=channel)
            assert (
                other.canonical_bytes == baseline.canonical_bytes
            ), f"{channel} envelope canonical_bytes drift from cli baseline"
            assert (
                other.content_hash == baseline.content_hash
            ), f"{channel} envelope content_hash drift from cli baseline"
