# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1: the T-013 session-boundary reset CONTRACT + trigger taxonomy (S5b).

Offline, deterministic, <1s. Exercises the pure pieces of
``envoy.runtime.session_boundary`` — the ``reset_session_observed_state`` reset,
the ``is_recognized_fingerprint`` membership predicate, and the trigger→transition
mapping — in isolation. The live store/ledger wiring (all 6 triggers emit a
signed entry; the reset fires against the real durable region) is the Tier-2
``test_session_boundary_signal_wiring.py`` companion.

Per ``specs/session-state.md`` § "Cache reset on session boundary" (line 65) +
§ session_boundary_crossed (line 67); the reset is the SHARED T-013 contract S5o
and S6c reuse (``tests.support.t013``).
"""

from __future__ import annotations

import pytest

from envoy.runtime.session_boundary import (
    ALL_TRIGGERS,
    END_TRIGGERS,
    START_TRIGGERS,
    boundary_transition,
    is_recognized_fingerprint,
    reset_session_observed_state,
)
from tests.support.t013 import (
    EXAMPLE_FINGERPRINT_KEY,
    assert_t013_reset_clears_cache,
    make_observed_state_with_call,
)


class TestResetClearsSessionScopedState:
    def test_reset_empties_tool_calls_made(self) -> None:
        blob = make_observed_state_with_call()
        assert blob["tool_calls_made"], "precondition: blob has a recorded call"
        reset = reset_session_observed_state(blob)
        assert reset["tool_calls_made"] == {}

    def test_reset_zeroes_since_reconfirm_preserving_threshold(self) -> None:
        blob = make_observed_state_with_call(tool_calls_since_reconfirm=7)
        reset = reset_session_observed_state(blob)
        goal = reset["goal_reconfirmation"]
        assert goal["tool_calls_since_reconfirm"] == 0
        # threshold + last_reconfirmed_at survive (only the counter resets).
        assert goal["threshold"] == 10
        assert goal["last_reconfirmed_at"] == blob["goal_reconfirmation"]["last_reconfirmed_at"]

    def test_reset_drops_session_scoped_patterns_keeps_cross_session(self) -> None:
        patterns = [
            {"pattern_id": "sha256:s", "tool_name": "fs.read", "scope": "session"},
            {"pattern_id": "sha256:x", "tool_name": "fs.write", "scope": "cross_session"},
        ]
        blob = make_observed_state_with_call(pre_authorized_patterns=patterns)
        reset = reset_session_observed_state(blob)
        kept = reset["pre_authorized_patterns"]
        assert len(kept) == 1
        assert kept[0]["scope"] == "cross_session"

    def test_reset_does_not_mutate_input(self) -> None:
        blob = make_observed_state_with_call()
        original_calls = dict(blob["tool_calls_made"])
        reset_session_observed_state(blob)
        # The input blob is untouched — the reset returns a NEW blob.
        assert blob["tool_calls_made"] == original_calls
        assert blob["goal_reconfirmation"]["tool_calls_since_reconfirm"] == 3

    def test_reset_preserves_unrelated_fields(self) -> None:
        blob = make_observed_state_with_call()
        reset = reset_session_observed_state(blob)
        for field in (
            "schema_version",
            "session_id",
            "principal_genesis_id",
            "envelope_version_at_session_start",
            "posture_at_session_start",
        ):
            assert reset[field] == blob[field]

    def test_reset_rejects_non_dict_blob(self) -> None:
        with pytest.raises(ValueError, match="expects a dict blob"):
            reset_session_observed_state(["not", "a", "dict"])  # type: ignore[arg-type]


class TestRecognitionPredicate:
    def test_recognized_when_fingerprint_present(self) -> None:
        blob = make_observed_state_with_call()
        assert is_recognized_fingerprint(blob, EXAMPLE_FINGERPRINT_KEY) is True

    def test_not_recognized_when_absent(self) -> None:
        blob = make_observed_state_with_call()
        assert is_recognized_fingerprint(blob, "sha256:" + "ff" * 32) is False

    def test_not_recognized_when_no_calls_field(self) -> None:
        assert is_recognized_fingerprint({}, EXAMPLE_FINGERPRINT_KEY) is False


class TestTriggerTaxonomy:
    def test_six_canonical_triggers(self) -> None:
        assert ALL_TRIGGERS == START_TRIGGERS | END_TRIGGERS
        assert len(ALL_TRIGGERS) == 6
        assert {"unlock", "cli_start"} == START_TRIGGERS
        assert {"cli_end", "idle_timeout", "user_lock", "channel_disconnect"} == END_TRIGGERS

    @pytest.mark.parametrize("trigger", sorted(START_TRIGGERS))
    def test_start_triggers_map_to_start(self, trigger: str) -> None:
        assert boundary_transition(trigger) == "start"

    @pytest.mark.parametrize("trigger", sorted(END_TRIGGERS))
    def test_end_triggers_map_to_end(self, trigger: str) -> None:
        assert boundary_transition(trigger) == "end"

    def test_unknown_trigger_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown session-boundary trigger"):
            boundary_transition("logout")


class TestSharedInvariantHelper:
    def test_shared_t013_invariant_holds_on_reset(self) -> None:
        blob = make_observed_state_with_call()
        # The shared helper S5o + S6c reuse — asserts the behavioral property.
        reset = assert_t013_reset_clears_cache(blob, EXAMPLE_FINGERPRINT_KEY)
        assert reset["tool_calls_made"] == {}
