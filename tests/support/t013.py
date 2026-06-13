# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared T-013 session-boundary reset invariant (WS-6 S5b owns; S5o + S6c reuse).

The reset CONTRACT itself lives in production
(``envoy.runtime.session_boundary.reset_session_observed_state``); this module
provides the reusable ASSERTION so the downstream shards do NOT re-derive the
invariant:

- **S5o** (the SessionObservedState gate) calls
  ``assert_t013_reset_clears_cache`` to prove its gate-reset consumes the S5b
  signal — "post-boundary, an identical fingerprint is first-time-action again".
- **S6c** (the ``chat`` resident loop) calls it after driving a REAL channel
  boundary to prove the boundary fires the reset end-to-end.

Per the S5b todo: "the reset-invariant test is exported/importable as the SHARED
contract S5o and S6c reuse (no re-derivation per shard)."

The assertion is BEHAVIORAL, not field-grep: it uses the same fingerprint
recognition predicate the gate uses (``is_recognized_fingerprint``,
``specs/session-state.md`` line 120), so a previously-RECOGNIZED fingerprint
must become FIRST_TIME after the reset.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from envoy.runtime.session_boundary import (
    is_recognized_fingerprint,
    reset_session_observed_state,
)

#: A canonical example fingerprint key (``sha256:`` prefix per
#: ``specs/session-state.md`` § Algorithm); the value is opaque to the reset.
EXAMPLE_FINGERPRINT_KEY = "sha256:" + "ab" * 32


def make_observed_state_with_call(
    fingerprint_key: str = EXAMPLE_FINGERPRINT_KEY,
    *,
    tool_calls_since_reconfirm: int = 3,
    pre_authorized_patterns: list[dict[str, Any]] | None = None,
    session_id: str = "00000000-0000-7000-8000-000000000001",
) -> dict[str, Any]:
    """Build a minimal SessionObservedState blob that RECOGNIZES ``fingerprint_key``.

    The blob carries one ``tool_calls_made`` entry (so the fingerprint is a cache
    hit), a non-zero ``tool_calls_since_reconfirm``, and whatever
    ``pre_authorized_patterns`` the caller supplies (used to assert the
    session-scoped patterns reset while ``cross_session`` ones survive). The
    shape follows ``specs/session-state.md`` § Schema.
    """
    return {
        "schema_version": "session-state/1.0",
        "session_id": session_id,
        "principal_genesis_id": "sha256:" + "cd" * 32,
        "started_at": "2026-06-13T00:00:00.000000+00:00",
        "last_activity_at": "2026-06-13T00:05:00.000000+00:00",
        "tool_calls_made": {
            fingerprint_key: {
                "tool_name": "fs.read",
                "args_canonical_hash": fingerprint_key,
                "first_invoked_at": "2026-06-13T00:01:00.000000+00:00",
                "invocation_count": 1,
                "last_outcome": "success",
            }
        },
        "goal_reconfirmation": {
            "last_reconfirmed_at": "2026-06-13T00:00:00.000000+00:00",
            "tool_calls_since_reconfirm": tool_calls_since_reconfirm,
            "threshold": 10,
        },
        "reasoning_commits": [],
        "pending_phase_a_orphans": [],
        "pre_authorized_patterns": list(pre_authorized_patterns or []),
        "envelope_version_at_session_start": 1,
        "posture_at_session_start": "PSEUDO",
    }


def assert_t013_reset_clears_cache(
    blob_with_calls: dict[str, Any],
    fingerprint_key: str = EXAMPLE_FINGERPRINT_KEY,
    *,
    reset_fn: Callable[[Any], dict[str, Any]] = reset_session_observed_state,
    recognized_fn: Callable[[dict[str, Any], str], bool] = is_recognized_fingerprint,
) -> dict[str, Any]:
    """Assert the T-013 boundary-reset property; return the reset blob.

    1. **Precondition** — ``fingerprint_key`` IS recognized before the boundary.
    2. **Post-reset** — ``fingerprint_key`` is NOT recognized (first-time again).
    3. **Post-reset** — ``tool_calls_made`` is empty AND
       ``goal_reconfirmation.tool_calls_since_reconfirm`` is 0.

    ``reset_fn`` / ``recognized_fn`` default to the production S5b contract; S5o
    / S6c may inject their own wired-gate equivalents to prove the live path
    honors the same invariant.
    """
    assert recognized_fn(blob_with_calls, fingerprint_key), (
        "precondition violated: the fingerprint MUST be recognized BEFORE the "
        "boundary (otherwise the reset assertion is vacuous)"
    )
    reset = reset_fn(blob_with_calls)
    assert not recognized_fn(reset, fingerprint_key), (
        "T-013: a previously-recognized fingerprint MUST be first-time-action "
        "again after a session boundary (per-session fingerprint scope)"
    )
    assert reset.get("tool_calls_made") == {}, (
        "T-013: tool_calls_made MUST clear at a session boundary"
    )
    goal = reset.get("goal_reconfirmation") or {}
    assert goal.get("tool_calls_since_reconfirm") == 0, (
        "T-013: goal_reconfirmation.tool_calls_since_reconfirm MUST reset to 0"
    )
    return reset


__all__ = [
    "EXAMPLE_FINGERPRINT_KEY",
    "assert_t013_reset_clears_cache",
    "make_observed_state_with_call",
]
