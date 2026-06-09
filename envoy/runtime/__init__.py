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
- `KailashRsBindingsRuntime` — Phase 02 deferred slot, structurally present
  but feature-flagged off via `RS_BINDINGS_ENABLED`.
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
from envoy.runtime.protocol import KailashRuntime
from envoy.runtime.selection import get_runtime
from envoy.runtime.session import (
    PENDING_GRANT_STATES,
    SESSION_SIGNING_KEY_ID,
    PendingGrantRow,
    SessionRouter,
    session_db_path,
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
    "RsBindingsNotAvailableInPhase01Error",
    "Phase02SubstrateNotWiredError",
]
