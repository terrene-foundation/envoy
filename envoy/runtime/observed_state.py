# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.observed_state — SessionObservedState gate semantics (WS-6 S5o).

The observed-state half of the persistent-session substrate. S4s
(``envoy.runtime.session.SessionRouter``) ships the durable Region-2 snapshot
home (an opaque canonical-JSON blob keyed by ``session_id``); S5b
(``envoy.runtime.session_boundary``) owns the ``session_boundary_crossed``
signal + the T-013 cache-reset CONTRACT. THIS module owns the gate semantics the
two were waiting on (``specs/session-state.md`` § Algorithm
``first_time_action_gate`` + § ``pre_authorized_patterns`` + goal-reconfirmation):

1. **Fingerprint** — ``sha256(NFC(tool_name) || canonicalize_args(args))`` where
   ``canonicalize_args`` is the envelope-model JCS+NFC pipeline
   (``envoy.envelope.canonical_bytes``). The SAME pipeline both runtimes use, so
   the fingerprint is byte-identical across ``kailash-py`` and
   ``kailash-rs-bindings`` (the N6 conformance invariant).
2. **first_time_action_gate(session, tool_name, args) → GateResult** — the pure,
   deterministic, byte-identical gate both runtime adapters delegate to. RECOGNIZED
   on a fingerprint cache-hit (reusing S5b's ``is_recognized_fingerprint`` — NOT a
   re-derived predicate, per ``rules/specs-authority.md`` Rule 5b) OR a structural
   pre-authorized-pattern AST match; else FIRST_TIME_REQUIRES_GRANT (the caller
   dispatches ``specs/grant-moment.md``).
3. **match_ast** — a FAIL-CLOSED structural matcher for pre-authorized patterns.
   A pattern that bypasses the Grant Moment is a security surface, so the match
   is conservative: every args key MUST be covered by the pattern AND every
   pattern key MUST be present (no unauthorized extra args, no missing required
   args). No regex, no LLM — a deterministic structural walk
   (``rules/probe-driven-verification.md`` Rule 3: structural, not lexical).
4. **goal-reconfirmation** — ``check_goal_reconfirmation`` raises
   ``GoalReconfirmationThresholdExceededError`` when ``tool_calls_since_reconfirm
   ≥ threshold`` (threshold ``0`` = disabled, the genesis default); the
   store-wired gate increments the counter per observed tool call and resets it
   on reconfirmation.

The store-wired orchestration (load the blob from Region-2, run the gate,
persist, consume the S5b boundary reset) is ``SessionObservedStateGate`` below;
the adapters delegate ONLY to the pure ``first_time_action_gate`` so the
byte-identity contract holds without any I/O on the adapter path.

Pattern-AST shape (code-first per ``rules/specs-authority.md`` Rule 5; recorded
in ``specs/session-runtime.md`` § Region 2): each pattern node is matched against
the corresponding args node by ``_match_node``. A node is one of —
``{"match": "exact", "value": <x>}`` (equality), ``{"match": "any"}`` (any value
present), ``{"match": "prefix", "value": "<str>"}`` (raw string ``startswith`` —
NOTE: it does NOT normalize paths, so a ``"/safe/"`` prefix authored to scope a
filesystem tool still matches ``"/safe/../etc/passwd"``; pattern authors MUST
account for traversal when authoring path prefixes),
``{"match": "type", "value": "str|int|float|bool|list|dict"}`` (isinstance), a
nested plain dict (recursive ``match_ast``), a list (elementwise, same length),
or a bare scalar (treated as ``exact``). An unknown ``match`` directive fails
closed.
"""

from __future__ import annotations

import enum
import hashlib
import unicodedata
from datetime import datetime, timezone
from typing import Any

from envoy.envelope.canonical_bytes import canonical_bytes
from envoy.runtime.errors import (
    GoalReconfirmationThresholdExceededError,
)
from envoy.runtime.session_boundary import is_recognized_fingerprint

__all__ = [
    "GateResult",
    "canonicalize_args",
    "check_goal_reconfirmation",
    "fingerprint",
    "first_time_action_gate",
    "match_ast",
    "record_observation",
    "reconfirm_goal",
]


class GateResult(str, enum.Enum):
    """Outcome of ``first_time_action_gate`` (``specs/session-state.md`` § Algorithm).

    A ``str`` enum so the value canonicalizes to a stable string under the BET-6
    byte-identity scorer (``recognized`` / ``first_time_requires_grant``) — both
    runtimes return the SAME member for the SAME input.
    """

    RECOGNIZED = "recognized"
    FIRST_TIME_REQUIRES_GRANT = "first_time_requires_grant"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def canonicalize_args(args: dict[str, Any]) -> bytes:
    """JCS-RFC8785 + NFC canonical bytes of a tool-call args dict.

    Reuses the envelope-model canonical pipeline (``envoy.envelope.canonical_bytes``)
    so the args canonicalization is the SAME contract envelopes use — the property
    ``specs/session-state.md`` § ``tool_calls_made`` fingerprint cites ("JCS per
    specs/envelope-model.md"). Returns bytes; the fingerprint hashes them directly.
    """
    return canonical_bytes(args)


def fingerprint(tool_name: str, args: dict[str, Any]) -> str:
    """``sha256:`` + ``sha256(NFC(tool_name) || canonicalize_args(args))`` hexdigest.

    ``specs/session-state.md`` § ``tool_calls_made`` fingerprint:
    ``sha256(tool_name || canonicalize_args(args))``. ``tool_name`` is NFC-normalized
    (the args canonicalizer already NFC-normalizes every string) so an NFD-authored
    tool name hashes identically to its precomposed sibling — the cross-OS /
    cross-runtime identity the N6 conformance vector pins.
    """
    digest = hashlib.sha256(
        unicodedata.normalize("NFC", tool_name).encode("utf-8") + canonicalize_args(args)
    ).hexdigest()
    return f"sha256:{digest}"


def _match_node(pattern: Any, value: Any) -> bool:
    """Match one pre-authorized-pattern node against one args node. Fail-closed.

    See the module docstring for the node grammar. Any shape the grammar does not
    recognize (an unknown ``match`` directive, a type mismatch, a length mismatch)
    returns ``False`` — a pre-authorized pattern that bypasses the Grant Moment
    MUST never match more than it was authored to.
    """
    if isinstance(pattern, dict) and "match" in pattern:
        directive = pattern["match"]
        if directive == "any":
            return True
        if directive == "exact":
            return bool(value == pattern.get("value"))
        if directive == "prefix":
            prefix = pattern.get("value")
            return isinstance(value, str) and isinstance(prefix, str) and value.startswith(prefix)
        if directive == "type":
            type_map: dict[str, type | tuple[type, ...]] = {
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
            }
            expected = type_map.get(pattern.get("value", ""))
            if expected is None:
                return False  # unknown type name → fail closed
            # bool is a subclass of int; guard so {"type":"int"} does not match True.
            if expected is int and isinstance(value, bool):
                return False
            return isinstance(value, expected)
        return False  # unknown directive → fail closed
    if isinstance(pattern, dict):
        # A plain dict node (no "match" key) → recursive structural match.
        return isinstance(value, dict) and match_ast(pattern, value)
    if isinstance(pattern, list):
        return (
            isinstance(value, list)
            and len(pattern) == len(value)
            and all(_match_node(p, v) for p, v in zip(pattern, value, strict=True))
        )
    # A bare scalar pattern is exact-equality (the common case).
    return bool(value == pattern)


def match_ast(pattern_ast: Any, args: dict[str, Any]) -> bool:
    """Fail-closed structural match of a pre-authorized pattern AST against args.

    Both ``pattern_ast`` and ``args`` MUST be dicts with the EXACT same key set —
    an args key the pattern does not constrain is an unauthorized parameter (a
    ``follow_symlinks: true`` smuggled past a path-only authorization), and a
    pattern key absent from args is an unmet authorization precondition. Either
    fails the match closed. Each shared key's value is matched by ``_match_node``.
    """
    if not isinstance(pattern_ast, dict) or not isinstance(args, dict):
        return False
    if set(pattern_ast.keys()) != set(args.keys()):
        return False
    return all(_match_node(pattern_ast[key], args[key]) for key in pattern_ast)


def first_time_action_gate(
    session: dict[str, Any],
    tool_name: str,
    args: dict[str, Any],
) -> GateResult:
    """The pure first-time-action gate (``specs/session-state.md`` § Algorithm).

    Deterministic + byte-identical — both runtime adapters delegate here, so the
    SAME ``(session, tool_name, args)`` yields the SAME ``GateResult`` and the SAME
    mutation on every runtime. Returns:

    - ``RECOGNIZED`` if the fingerprint is already in ``tool_calls_made`` (cache
      hit; reuses S5b's ``is_recognized_fingerprint`` membership predicate — NOT a
      re-derived check).
    - ``RECOGNIZED`` if a pre-authorized pattern AST-matches (the call is recorded
      into ``tool_calls_made`` with ``last_outcome="pre_authorized"`` so the NEXT
      identical call is a plain cache hit), per spec.
    - ``FIRST_TIME_REQUIRES_GRANT`` otherwise (the caller dispatches a Grant Moment;
      the grant approval records the fingerprint).

    Mutates ``session`` in place ONLY on the pre-authorized-match branch (exactly as
    the spec pseudocode does). The fingerprint-hit and first-time branches are
    read-only.
    """
    fp_key = fingerprint(tool_name, args)

    if is_recognized_fingerprint(session, fp_key):
        return GateResult.RECOGNIZED

    for pattern in session.get("pre_authorized_patterns") or []:
        if not isinstance(pattern, dict):
            continue
        if pattern.get("tool_name") != tool_name:
            continue
        if not match_ast(pattern.get("args_pattern_ast"), args):
            continue
        calls = session.setdefault("tool_calls_made", {})
        if isinstance(calls, dict):
            calls[fp_key] = {
                "tool_name": tool_name,
                "args_canonical_hash": fp_key,
                "first_invoked_at": _now_iso(),
                "invocation_count": 1,
                "last_outcome": "pre_authorized",
            }
        return GateResult.RECOGNIZED

    return GateResult.FIRST_TIME_REQUIRES_GRANT


def check_goal_reconfirmation(session: dict[str, Any]) -> None:
    """Raise ``GoalReconfirmationThresholdExceededError`` when the since-reconfirm
    counter has reached the session's threshold (``specs/session-state.md`` § Error
    taxonomy).

    A ``threshold`` of ``0`` (the genesis default) DISABLES the gate — goal
    reconfirmation is opt-in, configured by the Boundary Conversation / Weekly
    Posture Review. The caller invokes this BEFORE the fingerprint gate so the next
    tool call is held until the user reconfirms goal alignment.
    """
    goal = session.get("goal_reconfirmation")
    if not isinstance(goal, dict):
        return
    threshold = goal.get("threshold", 0)
    since = goal.get("tool_calls_since_reconfirm", 0)
    if isinstance(threshold, int) and threshold > 0 and isinstance(since, int) and since >= threshold:
        raise GoalReconfirmationThresholdExceededError(
            f"tool_calls_since_reconfirm={since} ≥ threshold={threshold}; "
            "next tool call gated — user must reconfirm goal alignment "
            "(Grant Moment dispatch per specs/session-state.md § Error taxonomy)"
        )


def record_observation(
    session: dict[str, Any],
    tool_name: str,
    args: dict[str, Any],
    *,
    outcome: str = "success",
) -> dict[str, Any]:
    """Return a NEW blob recording one tool-call observation (input not mutated).

    Adds the fingerprint to ``tool_calls_made`` (first-seen) or bumps its
    ``invocation_count`` + updates ``last_outcome`` (seen), increments
    ``goal_reconfirmation.tool_calls_since_reconfirm``, and refreshes
    ``last_activity_at``. This is the write that makes a repeated fingerprint
    RECOGNIZED on the next gate call — invoked when a first-time action is
    approved/executed AND on every subsequent recognized call (so the
    snapshot-at-every-Ledger-append crash-safety property has fresh observed
    state to persist).
    """
    blob = dict(session)
    calls = dict(blob.get("tool_calls_made") or {})
    fp_key = fingerprint(tool_name, args)
    now = _now_iso()
    existing = calls.get(fp_key)
    if isinstance(existing, dict):
        updated = dict(existing)
        count = updated.get("invocation_count", 0)
        updated["invocation_count"] = (count if isinstance(count, int) else 0) + 1
        updated["last_outcome"] = outcome
        calls[fp_key] = updated
    else:
        calls[fp_key] = {
            "tool_name": tool_name,
            "args_canonical_hash": fp_key,
            "first_invoked_at": now,
            "invocation_count": 1,
            "last_outcome": outcome,
        }
    blob["tool_calls_made"] = calls

    goal = blob.get("goal_reconfirmation")
    if isinstance(goal, dict):
        new_goal = dict(goal)
        since = new_goal.get("tool_calls_since_reconfirm", 0)
        new_goal["tool_calls_since_reconfirm"] = (since if isinstance(since, int) else 0) + 1
        blob["goal_reconfirmation"] = new_goal

    blob["last_activity_at"] = now
    return blob


def reconfirm_goal(session: dict[str, Any]) -> dict[str, Any]:
    """Return a NEW blob with the goal-reconfirmation counter reset to 0.

    Called when the user reconfirms goal alignment (the
    ``GoalReconfirmationThresholdExceededError`` Grant Moment resolved): resets
    ``tool_calls_since_reconfirm`` to 0 and refreshes ``last_reconfirmed_at``,
    preserving ``threshold``. The input is not mutated.
    """
    blob = dict(session)
    goal = blob.get("goal_reconfirmation")
    base: dict[str, Any] = dict(goal) if isinstance(goal, dict) else {"threshold": 0}
    base["tool_calls_since_reconfirm"] = 0
    base["last_reconfirmed_at"] = _now_iso()
    blob["goal_reconfirmation"] = base
    return blob
