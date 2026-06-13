# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime — abstract runtime interface + Phase-01 production adapter.

Per shard 18 (`workspaces/phase-01-mvp/01-analysis/18-runtime-abstraction-stub.md`):

- `KailashRuntime` — runtime-checkable Protocol declaring every method on
  `specs/runtime-abstraction.md` § Abstract interface tables.
- `KailashPyRuntime` — Phase 01 production adapter forwarding to upstream
  `kailash` and to Envoy primitives. Wired methods do real work;
  Phase02-deferred methods raise typed `Phase02SubstrateNotWiredError` with
  grep-able substrate hints.
- `KailashRsBindingsRuntime` — the Rust-bindings runtime, feature-flagged off
  via `RS_BINDINGS_ENABLED` until Phase 02 entry. 18/31 Protocol methods are
  genuinely wired; the remaining 13 are substrate-gated and raise a typed
  `RuntimeNotReadyError` naming their gating shard (S5o/S6a/S6c) until wired.
- `get_runtime()` — single factory entry point; primitives import THIS, never
  the adapter classes directly. The Phase 02 mechanicality lock.

Public surface per `rules/orphan-detection.md` Rule 6 (every module-scope
public import appears in `__all__`).
"""

from __future__ import annotations

from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.adapters.kailash_rs_bindings import KailashRsBindingsRuntime
from envoy.runtime.errors import (
    AlgorithmIdentifierMismatchError,
    BudgetExhaustedError,
    BudgetVelocityExceededError,
    ClassifierUnavailableError,
    FirstTimeActionGateBypassAttemptError,
    GoalReconfirmationThresholdExceededError,
    LedgerRollbackDetectedError,
    LedgerVerificationFailedError,
    Phase02SubstrateNotWiredError,
    PhaseAIntentSigningFailedError,
    PhaseBOrphanError,
    RsBindingsNotAvailableInPhase01Error,
    RuntimeError,
    RuntimeNotReadyError,
    RuntimeShutdownError,
    RuntimeSignatureVerificationFailedError,
)
from envoy.runtime.feature_flags import RS_BINDINGS_ENABLED
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
from envoy.runtime.observed_state_gate import SessionObservedStateGate
from envoy.runtime.protocol import KailashRuntime
from envoy.runtime.selection import get_runtime
from envoy.runtime.session import (
    PENDING_GRANT_STATES,
    SESSION_SIGNING_KEY_ID,
    PendingGrantRow,
    SessionRouter,
    session_db_path,
)
from envoy.runtime.session_boundary import (
    ALL_TRIGGERS,
    END_TRIGGERS,
    SESSION_BOUNDARY_ENTRY_TYPE,
    SESSION_BOUNDARY_SCHEMA_VERSION,
    START_TRIGGERS,
    SessionBoundaryResult,
    SessionBoundarySignal,
    boundary_transition,
    is_recognized_fingerprint,
    reset_session_observed_state,
)

__all__ = [
    # Protocol + adapters
    "KailashRuntime",
    "KailashPyRuntime",
    "KailashRsBindingsRuntime",
    # Factory
    "get_runtime",
    # Feature flag
    "RS_BINDINGS_ENABLED",
    # WS-6 S4s — store-backed session substrate
    "SessionRouter",
    "PendingGrantRow",
    "PENDING_GRANT_STATES",
    "SESSION_SIGNING_KEY_ID",
    "session_db_path",
    # WS-6 S5b — session-lifecycle boundary signal + T-013 reset
    "SessionBoundarySignal",
    "SessionBoundaryResult",
    "reset_session_observed_state",
    "is_recognized_fingerprint",
    "boundary_transition",
    "START_TRIGGERS",
    "END_TRIGGERS",
    "ALL_TRIGGERS",
    "SESSION_BOUNDARY_ENTRY_TYPE",
    "SESSION_BOUNDARY_SCHEMA_VERSION",
    # WS-6 S5o — SessionObservedState first-time-action gate
    "GateResult",
    "first_time_action_gate",
    "fingerprint",
    "canonicalize_args",
    "match_ast",
    "check_goal_reconfirmation",
    "record_observation",
    "reconfirm_goal",
    "SessionObservedStateGate",
    # Errors (spec § Error taxonomy + Envoy-internal)
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
