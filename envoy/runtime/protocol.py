# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.protocol — `KailashRuntime` runtime-checkable Protocol.

Source of truth: `specs/runtime-abstraction.md` § Abstract interface tables
(Lifecycle, Trust Lineage, Envelope, Two-phase signing, Ledger, Classifier,
Budget, Runtime device-key signing, Prompt + tool-output). Every method on the
spec's abstract-interface tables appears below; Phase 02 wires kailash-rs
bindings against this same Protocol.

Phase 01 narrow scope (per shard 18 § 4 narrowing decision):

- Signatures only. NO @byte_identical / @semantically_equivalent decorators
  (`__contract_tier__` machinery deferred to a follow-up shard).
- NO __conformance_vectors__ attribute. The conformance runner per
  `specs/runtime-abstraction.md` § Test location lands in Phase 01b.
- NO return-type wrappers (envoy.runtime.types deferred).

The shard 18 design describes the fuller surface; this narrow Protocol IS the
Phase-01 contract — every method declared here MUST be implemented by both
the kailash_py adapter (now) and the kailash_rs_bindings adapter (Phase 02).

Type aliases use `Any` where the upstream type lives in `kailash` (the wired
adapter forwards real types; the Protocol is structurally typed so the call
sites do not need to cross-import every kailash type).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class KailashRuntime(Protocol):
    """Abstract runtime interface every Envoy primitive programs against.

    Per shard 18 § 3.1, Protocol (PEP 544) is preferred over `abc.ABC` because
    adapters from kailash-py and kailash-rs-bindings are already-typed objects
    that we wrap at composition time, not Envoy-derived subclasses. The
    spec's "(ABC)" wording in `specs/runtime-abstraction.md` is a generic
    abstract-interface noun, not a literal `abc.ABC` mandate — disposition 1
    in shard 18 § 7 frozen-spec ambiguity.

    `@runtime_checkable` lets `isinstance(adapter, KailashRuntime)` succeed
    against an adapter that "happens to satisfy" the structural shape, which
    is the desired Phase-02 substitution semantics.
    """

    # ------------------------------------------------------------------
    # Lifecycle (spec § Lifecycle)
    # ------------------------------------------------------------------

    async def startup(self, config: Any) -> None:
        """Load device key, verify binary hash vs manifest, prepare classifier
        cache. Per spec § Lifecycle."""
        ...

    async def shutdown(self) -> None:
        """Flush Ledger pending writes, zero in-memory secrets, release file
        handles. Per spec § Lifecycle."""
        ...

    def runtime_identity(self) -> Any:
        """Return `{runtime_family, version, binary_hash,
        device_bound_pubkey_hex, algorithm_identifier}` per spec § Lifecycle."""
        ...

    # ------------------------------------------------------------------
    # Trust Lineage (spec § Trust Lineage)
    # ------------------------------------------------------------------

    def trust_sign(self, record: Any, key: Any) -> bytes:
        """JCS + Ed25519 signature over record's canonical form per
        specs/envelope-model.md § Canonical JSON. Byte-identical."""
        ...

    def trust_verify_chain(self, record: Any) -> Any:
        """10-step chain verification per specs/trust-lineage.md
        § Chain verification. Byte-identical."""
        ...

    def trust_cascade_revoke(self, root_id: str) -> set[str]:
        """BFS/DFS-equivalent set of revoked delegation_ids. Byte-identical
        SET equality; ordering may differ between runtimes."""
        ...

    def trust_verify_subset_proof(self, parent: Any, sub: Any) -> Any:
        """Runtime-signed subset-proof verification per
        specs/sub-agent-delegation.md § `is_subset_envelope` algorithm."""
        ...

    # ------------------------------------------------------------------
    # Envelope (spec § Envelope)
    # ------------------------------------------------------------------

    def envelope_canonical_form(self, envelope: Any) -> bytes:
        """JCS-RFC8785 + NFC per specs/envelope-model.md § Canonical JSON.
        Byte-identical."""
        ...

    def envelope_intersect(self, a: Any, b: Any) -> Any:
        """specs/envelope-model.md § `intersect_envelopes`. Byte-identical."""
        ...

    def envelope_check(self, envelope: Any, action: Any) -> Any:
        """Structural + semantic check; may dispatch Grant Moment on
        FIRST_TIME_REQUIRES_GRANT verdict."""
        ...

    def envelope_re_read_checkpoint(self, envelope: Any, depth: int) -> Any:
        """T-015 defense: re-read envelope from Trust Vault every N
        composition-rule evaluations."""
        ...

    # ------------------------------------------------------------------
    # Two-phase signing (spec § Two-phase signing)
    # ------------------------------------------------------------------

    def phase_a_sign_intent(self, intent: Any) -> Any:
        """Delegation-key-signed; envelope_check runs pre-sign; writes to
        Ledger. Returns PhaseARecord per spec § Two-phase signing."""
        ...

    def phase_b_sign_outcome(self, outcome: Any, intent_id: str) -> Any:
        """Runtime-device-key-signed; linked to intent_id. Returns
        PhaseBRecord."""
        ...

    def phase_a_orphan_resolve(self, intent_id: str, resolution: Any) -> Any:
        """User-chosen resolution (retry / failed / investigate); Genesis-
        signed via Grant Moment."""
        ...

    # ------------------------------------------------------------------
    # Ledger (spec § Ledger)
    # ------------------------------------------------------------------

    async def ledger_append(self, entry: Any) -> Any:
        """Byte-identical hash chain; parent_hash + entry_id computed over
        canonical form. Returns the entry with `entry_id` populated."""
        ...

    async def ledger_query(self, filter: Any) -> list[Any]:
        """Read-path; applies specs/classification-policy.md
        `apply_read_classification`."""
        ...

    async def ledger_verify_chain(self, from_: int, to: int) -> Any:
        """Byte-identical chain verify per specs/ledger.md § Export +
        independent verifier."""
        ...

    async def head_commitment(self) -> Any:
        """Byte-identical; monotonic non-decreasing per specs/ledger.md
        § Head commitment."""
        ...

    # ------------------------------------------------------------------
    # Classifier (spec § Classifier)
    # ------------------------------------------------------------------

    def classifier_invoke(self, ref: str, content: bytes, ctx: Any) -> Any:
        """Semantically-equivalent; 2+ classifiers per ensemble mandatory."""
        ...

    def ensemble_aggregate(self, verdicts: list[Any], policy: Any) -> Any:
        """Byte-identical aggregation; disagreement fails CLOSED by default."""
        ...

    def classifier_registry_resolve(self, registry_id: str) -> Any:
        """Fetches, verifies 2-of-N steward signatures, hash-matches; per
        specs/foundation-ops.md § Registry schemas."""
        ...

    # ------------------------------------------------------------------
    # Budget (spec § Budget)
    # ------------------------------------------------------------------

    def budget_reserve(self, session: Any, cost: int) -> Any:
        """Byte-identical; integer microdollars per
        specs/budget-tracker.md. Returns ReservationID."""
        ...

    def budget_record(self, reservation: Any, actual: int) -> None:
        """Finalize; surplus/deficit reconciled."""
        ...

    def budget_snapshot(self, session: Any) -> Any:
        """`{per_call, per_session, per_hour_velocity, per_day, per_month}`
        integer microdollars."""
        ...

    def budget_velocity_check(self, session: Any) -> Any:
        """Raises `BudgetVelocityExceededError` if any ceiling breached."""
        ...

    # ------------------------------------------------------------------
    # Runtime device-key signing (spec § Runtime device-key signing)
    # ------------------------------------------------------------------

    def runtime_sign(self, payload: bytes) -> bytes:
        """Ed25519 signature with device-bound key (Secure Enclave / TPM /
        software-fallback). Phase 01 ships software-fallback only; Phase 02
        introduces Secure Enclave + TPM via the Rust binding."""
        ...

    def runtime_verify(self, payload: bytes, sig: bytes, pubkey: bytes) -> bool:
        """Byte-identical Ed25519 verification."""
        ...

    # ------------------------------------------------------------------
    # Prompt + tool-output (spec § Prompt + tool-output)
    # ------------------------------------------------------------------

    def prompt_assemble(
        self,
        system: Any,
        envelope: Any,
        context: Any,
        user_message: str,
    ) -> Any:
        """Envelope-pinned system prompt (T-015 defense); consumer of
        specs/envelope-model.md. Returns AssembledPrompt per spec §
        AssembledPrompt."""
        ...

    def tool_output_sanitize(
        self,
        output: bytes,
        tool_name: str,
        envelope: Any,
    ) -> Any:
        """specs/tool-output-sanitization.md § Algorithm; fail-closed on
        classifier unavailability."""
        ...

    def first_time_action_gate(
        self,
        session: Any,
        tool_name: str,
        args: dict[str, Any],
    ) -> Any:
        """specs/session-state.md § `first_time_action_gate`."""
        ...

    def grant_moment_surface(self, request: Any) -> Any:
        """specs/grant-moment.md dispatch; channel-adapter routing."""
        ...


__all__ = ["KailashRuntime"]


# Suppress unused-import warning while keeping the typing.Optional symbol
# available for downstream files that re-import from this module's namespace.
_ = Optional
