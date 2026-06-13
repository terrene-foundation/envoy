# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1: pure SessionObservedState gate semantics (WS-6 S5o).

Offline, deterministic — no store, no I/O. Exercises the pure gate
(`envoy.runtime.observed_state`): the `first_time_action_gate` recognition
algorithm, the fail-closed `match_ast` pre-authorized-pattern matcher, the
fingerprint canonicalization + NFC stability, the goal-reconfirmation threshold
gate + reset, and the observation recorder. The store-wired orchestration +
cross-restart persistence + the T-013 boundary-reset integration are Tier 2
(`tests/tier2/test_observed_state_gate_wiring.py`).

Source of truth: `specs/session-state.md` § Algorithm `first_time_action_gate`
+ § `pre_authorized_patterns` semantics + § Error taxonomy.
"""

from __future__ import annotations

from typing import Any

import pytest

from envoy.runtime.errors import GoalReconfirmationThresholdExceededError
from envoy.runtime.observed_state import (
    GateResult,
    canonicalize_args,
    check_goal_reconfirmation,
    fingerprint,
    first_time_action_gate,
    match_ast,
    reconfirm_goal,
    record_observation,
)


def _fresh(**overrides: Any) -> dict[str, Any]:
    """A minimal genesis-shaped SessionObservedState blob (specs/session-state.md
    § Schema)."""
    blob: dict[str, Any] = {
        "schema_version": "session-state/1.0",
        "session_id": "00000000-0000-7000-8000-000000000001",
        "principal_genesis_id": "sha256:" + "ab" * 32,
        "started_at": "2026-06-13T00:00:00.000000+00:00",
        "last_activity_at": "2026-06-13T00:00:00.000000+00:00",
        "tool_calls_made": {},
        "goal_reconfirmation": {
            "last_reconfirmed_at": "2026-06-13T00:00:00.000000+00:00",
            "tool_calls_since_reconfirm": 0,
            "threshold": 0,
        },
        "reasoning_commits": [],
        "pending_phase_a_orphans": [],
        "pre_authorized_patterns": [],
        "envelope_version_at_session_start": 1,
        "posture_at_session_start": "PSEUDO",
    }
    blob.update(overrides)
    return blob


# ---------------------------------------------------------------------------
# Fingerprint — canonicalization + NFC stability + collision discrimination
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_fingerprint_is_sha256_prefixed_hex(self) -> None:
        fp = fingerprint("fs.read", {"path": "/a"})
        assert fp.startswith("sha256:")
        assert len(fp) == len("sha256:") + 64

    def test_args_canonicalization_is_key_order_insensitive(self) -> None:
        # JCS sorts keys, so arg dict ordering cannot change the fingerprint.
        assert fingerprint("t", {"a": 1, "b": 2}) == fingerprint("t", {"b": 2, "a": 1})

    def test_distinct_args_distinct_fingerprint(self) -> None:
        assert fingerprint("t", {"path": "/a"}) != fingerprint("t", {"path": "/b"})

    def test_distinct_tool_name_distinct_fingerprint(self) -> None:
        assert fingerprint("fs.read", {"k": "v"}) != fingerprint("fs.write", {"k": "v"})

    def test_tool_name_nfc_stability(self) -> None:
        # An NFD-decomposed tool name MUST hash identically to its precomposed
        # sibling (cross-OS / cross-runtime identity — the N6 invariant).
        nfd = "café.read"  # café (NFD: e + combining acute)
        nfc = "café.read"  # café (NFC: precomposed é)
        assert nfd != nfc  # the source strings differ byte-wise
        assert fingerprint(nfd, {"k": "v"}) == fingerprint(nfc, {"k": "v"})

    def test_args_value_nfc_stability(self) -> None:
        assert fingerprint("t", {"name": "café"}) == fingerprint("t", {"name": "café"})

    def test_canonicalize_args_returns_bytes(self) -> None:
        assert isinstance(canonicalize_args({"k": "v"}), bytes)


# ---------------------------------------------------------------------------
# first_time_action_gate — recognition algorithm
# ---------------------------------------------------------------------------


class TestFirstTimeActionGate:
    def test_novel_call_requires_grant(self) -> None:
        assert (
            first_time_action_gate(_fresh(), "fs.read", {"path": "/a"})
            is GateResult.FIRST_TIME_REQUIRES_GRANT
        )

    def test_cached_fingerprint_recognized(self) -> None:
        blob = _fresh()
        fp = fingerprint("fs.read", {"path": "/a"})
        blob["tool_calls_made"][fp] = {
            "tool_name": "fs.read",
            "args_canonical_hash": fp,
            "first_invoked_at": "2026-06-13T00:01:00+00:00",
            "invocation_count": 1,
            "last_outcome": "success",
        }
        assert (
            first_time_action_gate(blob, "fs.read", {"path": "/a"}) is GateResult.RECOGNIZED
        )

    def test_cache_hit_does_not_mutate(self) -> None:
        blob = _fresh()
        fp = fingerprint("fs.read", {"path": "/a"})
        blob["tool_calls_made"][fp] = {"tool_name": "fs.read", "invocation_count": 1}
        before = dict(blob["tool_calls_made"])
        first_time_action_gate(blob, "fs.read", {"path": "/a"})
        assert blob["tool_calls_made"] == before  # read-only branch

    def test_first_time_branch_does_not_mutate(self) -> None:
        blob = _fresh()
        first_time_action_gate(blob, "fs.read", {"path": "/a"})
        assert blob["tool_calls_made"] == {}  # no recording on first-time


# ---------------------------------------------------------------------------
# Pre-authorized pattern matching — RECOGNIZED + records the call
# ---------------------------------------------------------------------------


class TestPreAuthorizedPatterns:
    def _blob_with_pattern(self, ast: dict[str, Any], tool: str = "fs.read") -> dict[str, Any]:
        return _fresh(
            pre_authorized_patterns=[{"tool_name": tool, "args_pattern_ast": ast}]
        )

    def test_prefix_pattern_matches_and_records(self) -> None:
        blob = self._blob_with_pattern({"path": {"match": "prefix", "value": "/home/u/"}})
        result = first_time_action_gate(blob, "fs.read", {"path": "/home/u/x.txt"})
        assert result is GateResult.RECOGNIZED
        # The pre-authorized match RECORDS the call so the next one is a cache hit.
        fp = fingerprint("fs.read", {"path": "/home/u/x.txt"})
        assert fp in blob["tool_calls_made"]
        assert blob["tool_calls_made"][fp]["last_outcome"] == "pre_authorized"

    def test_exact_pattern_matches(self) -> None:
        blob = self._blob_with_pattern({"path": {"match": "exact", "value": "/etc/hosts"}})
        assert (
            first_time_action_gate(blob, "fs.read", {"path": "/etc/hosts"})
            is GateResult.RECOGNIZED
        )

    def test_any_pattern_matches_any_value(self) -> None:
        blob = self._blob_with_pattern({"path": {"match": "any"}})
        assert (
            first_time_action_gate(blob, "fs.read", {"path": "/whatever"})
            is GateResult.RECOGNIZED
        )

    def test_type_pattern_matches(self) -> None:
        blob = self._blob_with_pattern({"limit": {"match": "type", "value": "int"}})
        assert (
            first_time_action_gate(blob, "fs.read", {"limit": 10}) is GateResult.RECOGNIZED
        )

    def test_nested_dict_pattern_matches(self) -> None:
        blob = self._blob_with_pattern(
            {"opts": {"mode": {"match": "exact", "value": "ro"}}}
        )
        assert (
            first_time_action_gate(blob, "fs.read", {"opts": {"mode": "ro"}})
            is GateResult.RECOGNIZED
        )

    # ----- fail-closed cases (a pre-authorized pattern must never over-match) -----

    def test_extra_unauthorized_arg_fails_closed(self) -> None:
        # path is authorized; follow_symlinks is NOT — the call must require a grant.
        blob = self._blob_with_pattern({"path": {"match": "prefix", "value": "/home/"}})
        assert (
            first_time_action_gate(blob, "fs.read", {"path": "/home/x", "follow_symlinks": True})
            is GateResult.FIRST_TIME_REQUIRES_GRANT
        )

    def test_missing_required_arg_fails_closed(self) -> None:
        blob = self._blob_with_pattern(
            {"path": {"match": "any"}, "mode": {"match": "exact", "value": "ro"}}
        )
        assert (
            first_time_action_gate(blob, "fs.read", {"path": "/x"})
            is GateResult.FIRST_TIME_REQUIRES_GRANT
        )

    def test_wrong_tool_name_does_not_match(self) -> None:
        blob = self._blob_with_pattern({"path": {"match": "any"}}, tool="fs.read")
        assert (
            first_time_action_gate(blob, "fs.write", {"path": "/x"})
            is GateResult.FIRST_TIME_REQUIRES_GRANT
        )

    def test_prefix_non_match_fails_closed(self) -> None:
        blob = self._blob_with_pattern({"path": {"match": "prefix", "value": "/home/"}})
        assert (
            first_time_action_gate(blob, "fs.read", {"path": "/etc/passwd"})
            is GateResult.FIRST_TIME_REQUIRES_GRANT
        )

    def test_type_int_does_not_match_bool(self) -> None:
        # bool is a subclass of int; {"type":"int"} MUST NOT match True (fail-closed).
        blob = self._blob_with_pattern({"limit": {"match": "type", "value": "int"}})
        assert (
            first_time_action_gate(blob, "fs.read", {"limit": True})
            is GateResult.FIRST_TIME_REQUIRES_GRANT
        )

    def test_unknown_directive_fails_closed(self) -> None:
        blob = self._blob_with_pattern({"path": {"match": "regex", "value": ".*"}})
        assert (
            first_time_action_gate(blob, "fs.read", {"path": "/x"})
            is GateResult.FIRST_TIME_REQUIRES_GRANT
        )


class TestMatchAstDirect:
    def test_keyset_mismatch_is_false(self) -> None:
        assert match_ast({"a": {"match": "any"}}, {"a": 1, "b": 2}) is False
        assert match_ast({"a": {"match": "any"}, "b": {"match": "any"}}, {"a": 1}) is False

    def test_non_dict_inputs_false(self) -> None:
        assert match_ast(["a"], {"a": 1}) is False
        assert match_ast({"a": {"match": "any"}}, ["a"]) is False

    def test_list_node_elementwise_same_length(self) -> None:
        assert match_ast({"xs": [{"match": "any"}, {"match": "exact", "value": 2}]}, {"xs": [1, 2]})
        assert not match_ast({"xs": [{"match": "any"}]}, {"xs": [1, 2]})  # length mismatch

    def test_bare_scalar_is_exact(self) -> None:
        assert match_ast({"mode": "ro"}, {"mode": "ro"})
        assert not match_ast({"mode": "ro"}, {"mode": "rw"})


# ---------------------------------------------------------------------------
# Goal-reconfirmation threshold gate + reset
# ---------------------------------------------------------------------------


class TestGoalReconfirmation:
    def test_threshold_zero_is_disabled(self) -> None:
        # genesis default threshold=0 → never gates regardless of count.
        blob = _fresh()
        blob["goal_reconfirmation"] = {"tool_calls_since_reconfirm": 999, "threshold": 0}
        check_goal_reconfirmation(blob)  # no raise

    def test_below_threshold_passes(self) -> None:
        blob = _fresh()
        blob["goal_reconfirmation"] = {"tool_calls_since_reconfirm": 9, "threshold": 10}
        check_goal_reconfirmation(blob)  # no raise

    def test_at_threshold_raises(self) -> None:
        blob = _fresh()
        blob["goal_reconfirmation"] = {"tool_calls_since_reconfirm": 10, "threshold": 10}
        with pytest.raises(GoalReconfirmationThresholdExceededError):
            check_goal_reconfirmation(blob)

    def test_reconfirm_resets_counter(self) -> None:
        blob = _fresh()
        blob["goal_reconfirmation"] = {"tool_calls_since_reconfirm": 10, "threshold": 10}
        reset = reconfirm_goal(blob)
        assert reset["goal_reconfirmation"]["tool_calls_since_reconfirm"] == 0
        assert reset["goal_reconfirmation"]["threshold"] == 10  # threshold preserved
        check_goal_reconfirmation(reset)  # no longer gated
        # input not mutated
        assert blob["goal_reconfirmation"]["tool_calls_since_reconfirm"] == 10


# ---------------------------------------------------------------------------
# record_observation — fingerprint write + invocation_count bump + counter
# ---------------------------------------------------------------------------


class TestRecordObservation:
    def test_first_observation_records_fingerprint(self) -> None:
        blob = _fresh()
        out = record_observation(blob, "fs.read", {"path": "/a"})
        fp = fingerprint("fs.read", {"path": "/a"})
        assert out["tool_calls_made"][fp]["invocation_count"] == 1
        assert out["tool_calls_made"][fp]["last_outcome"] == "success"
        # makes the next gate call RECOGNIZED
        assert first_time_action_gate(out, "fs.read", {"path": "/a"}) is GateResult.RECOGNIZED

    def test_repeat_observation_bumps_count(self) -> None:
        blob = record_observation(_fresh(), "fs.read", {"path": "/a"})
        blob2 = record_observation(blob, "fs.read", {"path": "/a"}, outcome="failure")
        fp = fingerprint("fs.read", {"path": "/a"})
        assert blob2["tool_calls_made"][fp]["invocation_count"] == 2
        assert blob2["tool_calls_made"][fp]["last_outcome"] == "failure"

    def test_observation_increments_goal_counter(self) -> None:
        blob = _fresh()
        out = record_observation(blob, "fs.read", {"path": "/a"})
        assert out["goal_reconfirmation"]["tool_calls_since_reconfirm"] == 1

    def test_observation_does_not_mutate_input(self) -> None:
        blob = _fresh()
        record_observation(blob, "fs.read", {"path": "/a"})
        assert blob["tool_calls_made"] == {}


# ---------------------------------------------------------------------------
# Dual-adapter parity — both runtimes delegate to the SAME pure gate, so the
# GateResult is byte-identical by construction (the S5o cross-runtime invariant;
# specs/runtime-abstraction.md: first_time_action_gate is @byte_identical).
# ---------------------------------------------------------------------------


class TestDualAdapterParity:
    @pytest.mark.parametrize(
        ("tool_name", "args", "seed"),
        [
            ("fs.read", {"path": "/a"}, False),  # first-time on both
            ("net.fetch", {"url": "http://x"}, True),  # recognized on both
        ],
    )
    def test_both_adapters_return_identical_gate_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tool_name: str,
        args: dict[str, Any],
        seed: bool,
    ) -> None:
        import envoy.runtime.adapters.kailash_rs_bindings as rs_mod
        from envoy.runtime.adapters.kailash_py import KailashPyRuntime
        from envoy.runtime.adapters.kailash_rs_bindings import KailashRsBindingsRuntime

        # Flip ONLY the adapter-module flag (production flag untouched) so the rs
        # adapter can be constructed in-test — the same test-only seam the
        # conformance harness uses.
        monkeypatch.setattr(rs_mod, "RS_BINDINGS_ENABLED", True)
        py = KailashPyRuntime()
        rs = KailashRsBindingsRuntime()

        # IDENTICAL but independent session blobs (the gate may mutate on a
        # pre-authorized match; here neither case is pre-authorized, so both
        # branches are read-only — but copy anyway to prove independence).
        blob_a = _fresh()
        blob_b = _fresh()
        if seed:
            fp = fingerprint(tool_name, args)
            entry = {"tool_name": tool_name, "args_canonical_hash": fp, "invocation_count": 1}
            blob_a["tool_calls_made"][fp] = dict(entry)
            blob_b["tool_calls_made"][fp] = dict(entry)

        result_py = py.first_time_action_gate(blob_a, tool_name, args)
        result_rs = rs.first_time_action_gate(blob_b, tool_name, args)
        assert result_py == result_rs
        assert isinstance(result_py, GateResult)
        expected = GateResult.RECOGNIZED if seed else GateResult.FIRST_TIME_REQUIRES_GRANT
        assert result_py is expected
