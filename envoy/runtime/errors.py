# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.errors — typed error taxonomy for the abstract runtime.

Source of truth: `specs/runtime-abstraction.md` § Error taxonomy.

Every error class on the spec's published taxonomy MUST appear here so adapters
and consumers raise typed exceptions instead of generic Exception. Two Envoy-
internal additions (`RsBindingsNotAvailableInPhase01Error`,
`Phase02SubstrateNotWiredError`) carry the Phase-01 deferral discipline per
shard 18 § 3.3 (typed errors instead of bare `NotImplementedError`, per
`rules/zero-tolerance.md` Rule 2).
"""

from __future__ import annotations


class RuntimeError(Exception):
    """Base class for every envoy.runtime error."""


# ----------------------------------------------------------------------------
# Spec § Error taxonomy (canonical taxa)
# ----------------------------------------------------------------------------


class RuntimeNotReadyError(RuntimeError):
    """Runtime startup() has not completed; method invoked before ready."""


class RuntimeShutdownError(RuntimeError):
    """Runtime shutdown() in progress or completed; further calls rejected."""


class AlgorithmIdentifierMismatchError(RuntimeError):
    """algorithm_identifier on wire ≠ expected runtime algorithm_identifier."""


class PhaseAIntentSigningFailedError(RuntimeError):
    """Phase-A intent signing failed at envelope_check, delegation-key sign, or
    Ledger write boundary."""


class PhaseBOrphanError(RuntimeError):
    """Phase-A intent never produced a matching Phase-B outcome before session
    boundary; orphan resolution required via Grant Moment."""


class LedgerRollbackDetectedError(RuntimeError):
    """Head sequence decreased OR head signature mismatch; chain halted."""


class LedgerVerificationFailedError(RuntimeError):
    """Ledger chain walk surfaced a parent_hash, entry_id, or signature
    mismatch on a previously-appended entry."""


class ClassifierUnavailableError(RuntimeError):
    """Classifier ensemble did not produce a verdict (network / model down);
    fail-closed disposition required."""


class RuntimeSignatureVerificationFailedError(RuntimeError):
    """Ed25519 signature verification with the device-bound public key failed."""


class BudgetExhaustedError(RuntimeError):
    """Reservation refused — per-call / per-session / per-day budget breached."""


class BudgetVelocityExceededError(RuntimeError):
    """Per-hour velocity ceiling breached even though absolute budget remains."""


# ----------------------------------------------------------------------------
# specs/session-state.md § Error taxonomy (first-time-action gate / goal-reconfirm)
# ----------------------------------------------------------------------------


class GoalReconfirmationThresholdExceededError(RuntimeError):
    """`tool_calls_since_reconfirm` reached the session's threshold; the next tool
    call is gated until the user reconfirms goal alignment (Grant Moment dispatch).

    Per `specs/session-state.md` § Error taxonomy. Raised by
    `envoy.runtime.observed_state.check_goal_reconfirmation`. A threshold of 0
    (the genesis default) disables the gate — reconfirmation is opt-in.
    """


class FirstTimeActionGateBypassAttemptError(RuntimeError):
    """The first-time-action gate was invoked with an unsigned / unauthenticated
    caller — a runtime bug, not a user-actionable condition.

    Per `specs/session-state.md` § Error taxonomy. Reserved for the caller-side
    authentication guard around the gate; the pure gate itself is deterministic.
    """


# ----------------------------------------------------------------------------
# Envoy-internal Phase-01 deferral discipline
# ----------------------------------------------------------------------------


class RsBindingsNotAvailableInPhase01Error(RuntimeError):
    """kailash_rs_bindings adapter cannot be instantiated while
    `envoy.runtime.feature_flags.RS_BINDINGS_ENABLED == False`.

    Phase 02 flips the flag and fills the adapter methods. Until then, the
    Rust-bindings runtime exists as a structurally-present module so the
    Phase-02 substitution is a one-flag-flip + method-fill, not a refactor
    (per shard 18 § 3.3).
    """


class Phase02SubstrateNotWiredError(RuntimeError):
    """A KailashRuntime Protocol method whose upstream substrate genuinely
    does not exist in Phase 01 was invoked on the kailash_py adapter.

    The message MUST cite the method name AND the workspace todo tracking
    the substrate-landing shard, so a future session can grep the message to
    find where the wiring lands. This is the iterative-TODO pattern explicitly
    permitted by `rules/zero-tolerance.md` Rule 6 (actively tracked workspace
    todos).
    """


__all__ = [
    "RuntimeError",
    "RuntimeNotReadyError",
    "RuntimeShutdownError",
    "AlgorithmIdentifierMismatchError",
    "PhaseAIntentSigningFailedError",
    "PhaseBOrphanError",
    "LedgerRollbackDetectedError",
    "LedgerVerificationFailedError",
    "ClassifierUnavailableError",
    "RuntimeSignatureVerificationFailedError",
    "BudgetExhaustedError",
    "BudgetVelocityExceededError",
    "GoalReconfirmationThresholdExceededError",
    "FirstTimeActionGateBypassAttemptError",
    "RsBindingsNotAvailableInPhase01Error",
    "Phase02SubstrateNotWiredError",
]
