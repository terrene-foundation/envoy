# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.adapters.kailash_rs_bindings — Phase 02 deferred slot.

Per shard 18 § 3.3 and § 7 frozen-spec disposition 3: the Rust-bindings
adapter MUST exist as a structural file in Phase 01 so the Phase 02 entry is
a one-flag-flip (`feature_flags.RS_BINDINGS_ENABLED = True`) + per-method
body fill — NOT a "introduce new package and re-route every import" refactor.

Construction is gated behind the feature flag: while
`envoy.runtime.feature_flags.RS_BINDINGS_ENABLED == False` (the Phase 01
default), `KailashRsBindingsRuntime(...)` raises
`RsBindingsNotAvailableInPhase01Error` at the constructor — every Protocol
method body is unreachable, so no Phase02SubstrateNotWiredError ever leaks
from this module in Phase 01.

Per `rules/zero-tolerance.md` Rule 2 reconciliation: the typed
constructor-time error replaces the `NotImplementedError` pattern shard 18
called out as the tension surface; bodies still need to exist so the Protocol
shape is auditable BEFORE Phase 02 begins.
"""

from __future__ import annotations

import logging
from typing import Any

from envoy.runtime.errors import (
    Phase02SubstrateNotWiredError,
    RsBindingsNotAvailableInPhase01Error,
)
from envoy.runtime.feature_flags import RS_BINDINGS_ENABLED

logger = logging.getLogger(__name__)


_RS_BINDINGS_GUARD_MSG = (
    "KailashRsBindingsRuntime cannot be instantiated while "
    "envoy.runtime.feature_flags.RS_BINDINGS_ENABLED == False. "
    "Phase 02 entry flips the flag in envoy/runtime/feature_flags.py and "
    "fills the Protocol method bodies in this module; tracked at "
    "workspaces/phase-02-trust-plane/ (not yet authored)."
)


class KailashRsBindingsRuntime:
    """Phase 02 deferred slot — Rust-bindings adapter.

    Construction enforces the Phase-01 feature-flag guard. Each Protocol
    method body raises `Phase02SubstrateNotWiredError` so the surface is
    auditable IF the flag is ever flipped without filling bodies (regression
    detection — Phase 02 entry sees typed errors per method, NOT silent
    no-ops or NotImplementedError).
    """

    def __init__(self, **kwargs: Any) -> None:
        if not RS_BINDINGS_ENABLED:
            raise RsBindingsNotAvailableInPhase01Error(_RS_BINDINGS_GUARD_MSG)
        # Phase 02 introduces real constructor wiring against the Rust
        # binding's KailashRsRuntime handle. Kwargs are accepted (so future
        # callers can pass `binary_hash`, `device_attestation_handle`, etc.)
        # but currently inert — they land with Phase 02 implementation.
        self._kwargs = dict(kwargs)
        logger.info("envoy.runtime.kailash_rs_bindings.constructed")

    # The Phase02-stub body shape per method. Every body raises the typed
    # substrate error so flipping the flag without filling bodies produces a
    # loud, grep-able failure mode — NOT silent no-op behavior.

    async def startup(self, config: Any) -> None:
        raise Phase02SubstrateNotWiredError(
            "startup: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    async def shutdown(self) -> None:
        raise Phase02SubstrateNotWiredError(
            "shutdown: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def runtime_identity(self) -> Any:
        raise Phase02SubstrateNotWiredError(
            "runtime_identity: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def trust_sign(self, record: Any, key: Any) -> bytes:
        raise Phase02SubstrateNotWiredError(
            "trust_sign: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def trust_verify_chain(self, record: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "trust_verify_chain: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def trust_cascade_revoke(self, root_id: str) -> set[str]:
        raise Phase02SubstrateNotWiredError(
            "trust_cascade_revoke: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def trust_verify_subset_proof(self, parent: Any, sub: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "trust_verify_subset_proof: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def envelope_canonical_form(self, envelope: Any) -> bytes:
        raise Phase02SubstrateNotWiredError(
            "envelope_canonical_form: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def envelope_intersect(self, a: Any, b: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "envelope_intersect: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def envelope_check(self, envelope: Any, action: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "envelope_check: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def envelope_re_read_checkpoint(self, envelope: Any, depth: int) -> Any:
        raise Phase02SubstrateNotWiredError(
            "envelope_re_read_checkpoint: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def phase_a_sign_intent(self, intent: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "phase_a_sign_intent: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def phase_b_sign_outcome(self, outcome: Any, intent_id: str) -> Any:
        raise Phase02SubstrateNotWiredError(
            "phase_b_sign_outcome: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def phase_a_orphan_resolve(self, intent_id: str, resolution: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "phase_a_orphan_resolve: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    async def ledger_append(self, entry: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "ledger_append: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    async def ledger_query(self, filter: Any) -> list[Any]:
        raise Phase02SubstrateNotWiredError(
            "ledger_query: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    async def ledger_verify_chain(self, from_: int, to: int) -> Any:
        raise Phase02SubstrateNotWiredError(
            "ledger_verify_chain: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    async def head_commitment(self) -> Any:
        raise Phase02SubstrateNotWiredError(
            "head_commitment: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def classifier_invoke(self, ref: str, content: bytes, ctx: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "classifier_invoke: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def ensemble_aggregate(self, verdicts: list[Any], policy: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "ensemble_aggregate: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def classifier_registry_resolve(self, registry_id: str) -> Any:
        raise Phase02SubstrateNotWiredError(
            "classifier_registry_resolve: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def budget_reserve(self, session: Any, cost: int) -> Any:
        raise Phase02SubstrateNotWiredError(
            "budget_reserve: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def budget_record(self, reservation: Any, actual: int) -> None:
        raise Phase02SubstrateNotWiredError(
            "budget_record: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def budget_snapshot(self, session: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "budget_snapshot: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def budget_velocity_check(self, session: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "budget_velocity_check: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def runtime_sign(self, payload: bytes) -> bytes:
        raise Phase02SubstrateNotWiredError(
            "runtime_sign: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def runtime_verify(self, payload: bytes, sig: bytes, pubkey: bytes) -> bool:
        raise Phase02SubstrateNotWiredError(
            "runtime_verify: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def prompt_assemble(
        self,
        system: Any,
        envelope: Any,
        context: Any,
        user_message: str,
    ) -> Any:
        raise Phase02SubstrateNotWiredError(
            "prompt_assemble: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def tool_output_sanitize(
        self,
        output: bytes,
        tool_name: str,
        envelope: Any,
    ) -> Any:
        raise Phase02SubstrateNotWiredError(
            "tool_output_sanitize: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def first_time_action_gate(
        self,
        session: Any,
        tool_name: str,
        args: dict[str, Any],
    ) -> Any:
        raise Phase02SubstrateNotWiredError(
            "first_time_action_gate: kailash_rs_bindings runtime body Phase-02 deferred"
        )

    def grant_moment_surface(self, request: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "grant_moment_surface: kailash_rs_bindings runtime body Phase-02 deferred"
        )


__all__ = ["KailashRsBindingsRuntime"]
