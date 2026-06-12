# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.protocol — `KailashRuntime` runtime-checkable Protocol.

Source of truth: `specs/runtime-abstraction.md` § Abstract interface tables
(Lifecycle, Trust Lineage, Envelope, Two-phase signing, Ledger, Classifier,
Budget, Runtime device-key signing, Prompt + tool-output). Every method on the
spec's abstract-interface tables appears below; Phase 02 wires kailash-rs
bindings against this same Protocol.

Phase 02 S1 — contract-tier metadata landed (per
`workspaces/phase-02-distribution/todos/active/01-m1-ws1-runtime-pluggability.md`
§ S1):

- Every method carries an `@byte_identical` / `@semantically_equivalent`
  decorator from `envoy.runtime.contract_tier` (the `__contract_tier__`
  machinery). The decorator is the SINGLE source of truth the BET-6 conformance
  harness reads to pick a scorer; there is no hand-maintained method→tier map.
- A method declared without a tier decorator fails
  `assert_all_methods_tagged(KailashRuntime)` at harness-import time — a loud
  authoring error, not a silent default (S1 acceptance criterion 1).

Tier assignment per `specs/runtime-abstraction.md` § Contract partition (BET-6):
the canonical/crypto/ledger surface (`envelope_canonical_form`, `trust_sign`,
ledger hash chain, `trust_cascade_revoke` SET-equality, `envelope_intersect`,
subset-proof, `head_commitment`) is byte-identical. The ONE Phase-02 semantic
slice is `grant_moment_surface`'s rendered verdict TEXT (the structured payload
is byte-identical; only the user-facing string is semantically-equivalent —
`runtime-abstraction.md:152`, DEFERRED to the Phase-03 semantic harness).
Demoting a byte-identical method to semantic is BLOCKED (`zero-tolerance.md`
Rule 4) — it weakens a security gate.

Still deferred:

- NO __conformance_vectors__ attribute. The vector corpus per
  `specs/runtime-abstraction.md` lands in S2b/S2c/S3a/S3b.
- NO return-type wrappers (envoy.runtime.types deferred).

The shard 18 design describes the fuller surface; this Protocol IS the
contract — every method declared here MUST be implemented by both
the kailash_py adapter (now) and the kailash_rs_bindings adapter (S2a).

Type aliases use `Any` where the upstream type lives in `kailash` (the wired
adapter forwards real types; the Protocol is structurally typed so the call
sites do not need to cross-import every kailash type).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from envoy.runtime.contract_tier import byte_identical, semantically_equivalent


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

    @byte_identical
    async def startup(self, config: Any) -> None:
        """Load device key, verify binary hash vs manifest, prepare classifier
        cache. Per spec § Lifecycle. No cross-runtime divergent output —
        byte-identical (lifecycle side-effects only)."""
        ...

    @byte_identical
    async def shutdown(self) -> None:
        """Flush Ledger pending writes, zero in-memory secrets, release file
        handles. Per spec § Lifecycle. Byte-identical (lifecycle side-effects
        only)."""
        ...

    @byte_identical
    def runtime_identity(self) -> Any:
        """Return `{runtime_family, version, binary_hash,
        device_bound_pubkey_hex, algorithm_identifier}` per spec § Lifecycle.
        Byte-identical — the attestation vector hashes this structure."""
        ...

    # ------------------------------------------------------------------
    # Trust Lineage (spec § Trust Lineage)
    # ------------------------------------------------------------------

    @byte_identical
    def trust_sign(self, record: Any, key: Any) -> bytes:
        """JCS + Ed25519 signature over record's canonical form per
        specs/envelope-model.md § Canonical JSON. Byte-identical."""
        ...

    @byte_identical
    def trust_verify_chain(self, record: Any) -> Any:
        """10-step chain verification per specs/trust-lineage.md
        § Chain verification. Byte-identical."""
        ...

    @byte_identical
    def trust_cascade_revoke(self, root_id: str) -> set[str]:
        """BFS/DFS-equivalent set of revoked delegation_ids. Byte-identical
        SET equality; ordering may differ between runtimes (E3)."""
        ...

    @byte_identical
    def trust_verify_subset_proof(self, parent: Any, sub: Any) -> Any:
        """Runtime-signed subset-proof verification per
        specs/sub-agent-delegation.md § `is_subset_envelope` algorithm.
        Byte-identical — E5 hashes the runtime_verification_signature."""
        ...

    # ------------------------------------------------------------------
    # Envelope (spec § Envelope)
    # ------------------------------------------------------------------

    @byte_identical
    def envelope_canonical_form(self, envelope: Any) -> bytes:
        """JCS-RFC8785 + NFC per specs/envelope-model.md § Canonical JSON.
        Byte-identical — E1 hashes this canonical form."""
        ...

    @byte_identical
    def envelope_intersect(self, a: Any, b: Any) -> Any:
        """specs/envelope-model.md § `intersect_envelopes`. Byte-identical."""
        ...

    @byte_identical
    def envelope_check(self, envelope: Any, action: Any) -> Any:
        """Structural + semantic check; may dispatch Grant Moment on
        FIRST_TIME_REQUIRES_GRANT verdict. The verdict's STRUCTURED payload is
        byte-identical (N3 structural slice never dispatches the classifier;
        the semantic slice dispatches it — observed via
        `envoy.runtime.dispatch_observation`). The rendered verdict text is
        owned by `grant_moment_surface` (the semantic slice)."""
        ...

    @byte_identical
    def envelope_re_read_checkpoint(self, envelope: Any, depth: int) -> Any:
        """T-015 defense: re-read envelope from Trust Vault every N
        composition-rule evaluations. Byte-identical."""
        ...

    # ------------------------------------------------------------------
    # Two-phase signing (spec § Two-phase signing)
    # ------------------------------------------------------------------

    @byte_identical
    def phase_a_sign_intent(self, intent: Any) -> Any:
        """Delegation-key-signed; envelope_check runs pre-sign; writes to
        Ledger. Returns PhaseARecord per spec § Two-phase signing.
        Byte-identical."""
        ...

    @byte_identical
    def phase_b_sign_outcome(self, outcome: Any, intent_id: str) -> Any:
        """Runtime-device-key-signed; linked to intent_id. Returns
        PhaseBRecord. Byte-identical."""
        ...

    @byte_identical
    def phase_a_orphan_resolve(self, intent_id: str, resolution: Any) -> Any:
        """User-chosen resolution (retry / failed / investigate); Genesis-
        signed via Grant Moment. Byte-identical — E6 hashes the orphan-
        resolution record."""
        ...

    # ------------------------------------------------------------------
    # Ledger (spec § Ledger)
    # ------------------------------------------------------------------

    @byte_identical
    async def ledger_append(self, entry: Any) -> Any:
        """Byte-identical hash chain; parent_hash + entry_id computed over
        canonical form. Returns the entry with `entry_id` populated."""
        ...

    @byte_identical
    async def ledger_query(self, filter: Any) -> list[Any]:
        """Read-path; applies specs/classification-policy.md
        `apply_read_classification`. Byte-identical (deterministic read of the
        canonical chain)."""
        ...

    @byte_identical
    async def ledger_verify_chain(self, from_: int, to: int) -> Any:
        """Byte-identical chain verify per specs/ledger.md § Export +
        independent verifier."""
        ...

    @byte_identical
    async def head_commitment(self) -> Any:
        """Byte-identical; monotonic non-decreasing per specs/ledger.md
        § Head commitment. E7 asserts BOTH byte-identity AND monotonicity."""
        ...

    # ------------------------------------------------------------------
    # Classifier (spec § Classifier)
    # ------------------------------------------------------------------

    @semantically_equivalent
    def classifier_invoke(self, ref: str, content: bytes, ctx: Any) -> Any:
        """Semantically-equivalent; 2+ classifiers per ensemble mandatory. The
        classifier verdict is an LLM-class output — equivalent but not byte-
        equal across runtimes, scored by an LLM-judge probe (Phase-03). This is
        the method N3's semantic slice expects to dispatch; it WILL be observed
        via `envoy.runtime.dispatch_observation.record_dispatch` once S2b/S6a wire
        the real classifier path (no adapter calls `record_dispatch` yet — the
        hook + its observe() harness exist; the production call site lands with
        the classifier wiring)."""
        ...

    @byte_identical
    def ensemble_aggregate(self, verdicts: list[Any], policy: Any) -> Any:
        """Byte-identical aggregation; disagreement fails CLOSED by default.
        The aggregation RULE over verdicts is deterministic and byte-identical
        even though individual classifier verdicts are semantic."""
        ...

    @byte_identical
    def classifier_registry_resolve(self, registry_id: str) -> Any:
        """Fetches, verifies 2-of-N steward signatures, hash-matches; per
        specs/foundation-ops.md § Registry schemas. Byte-identical (signature
        verification + hash match are deterministic)."""
        ...

    # ------------------------------------------------------------------
    # Budget (spec § Budget)
    # ------------------------------------------------------------------

    @byte_identical
    def budget_reserve(self, session: Any, cost: int) -> Any:
        """Byte-identical; integer microdollars per
        specs/budget-tracker.md. Returns ReservationID."""
        ...

    @byte_identical
    def budget_record(self, reservation: Any, actual: int) -> None:
        """Finalize; surplus/deficit reconciled. Byte-identical (integer
        microdollar arithmetic)."""
        ...

    @byte_identical
    def budget_snapshot(self, session: Any) -> Any:
        """`{per_call, per_session, per_hour_velocity, per_day, per_month}`
        integer microdollars. Byte-identical."""
        ...

    @byte_identical
    def budget_velocity_check(self, session: Any) -> Any:
        """Raises `BudgetVelocityExceededError` if any ceiling breached.
        Byte-identical (deterministic ceiling comparison)."""
        ...

    # ------------------------------------------------------------------
    # Runtime device-key signing (spec § Runtime device-key signing)
    # ------------------------------------------------------------------

    @byte_identical
    def runtime_sign(self, payload: bytes) -> bytes:
        """Ed25519 signature with device-bound key (Secure Enclave / TPM /
        software-fallback). Phase 01 ships software-fallback only; Phase 02
        introduces Secure Enclave + TPM via the Rust binding. Byte-identical —
        the conformance harness proves signature-byte equality across runtimes."""
        ...

    @byte_identical
    def runtime_verify(self, payload: bytes, sig: bytes, pubkey: bytes) -> bool:
        """Byte-identical Ed25519 verification."""
        ...

    # ------------------------------------------------------------------
    # Prompt + tool-output (spec § Prompt + tool-output)
    # ------------------------------------------------------------------

    @byte_identical
    def prompt_assemble(
        self,
        system: Any,
        envelope: Any,
        context: Any,
        user_message: str,
    ) -> Any:
        """Envelope-pinned system prompt (T-015 defense); consumer of
        specs/envelope-model.md. Returns AssembledPrompt per spec §
        AssembledPrompt. Byte-identical — the assembly is a deterministic
        template fill (the LLM's *response* to the prompt is semantic, but
        prompt assembly itself is not)."""
        ...

    @byte_identical
    def tool_output_sanitize(
        self,
        output: bytes,
        tool_name: str,
        envelope: Any,
    ) -> Any:
        """specs/tool-output-sanitization.md § Algorithm; fail-closed on
        classifier unavailability. Byte-identical (deterministic sanitizer)."""
        ...

    @byte_identical
    def first_time_action_gate(
        self,
        session: Any,
        tool_name: str,
        args: dict[str, Any],
    ) -> Any:
        """specs/session-state.md § `first_time_action_gate`. Byte-identical
        (deterministic first-seen check over SessionObservedState)."""
        ...

    @semantically_equivalent
    def grant_moment_surface(self, request: Any) -> Any:
        """specs/grant-moment.md dispatch; channel-adapter routing. The
        rendered verdict TEXT is the ONE Phase-02 semantic slice (N4): the
        structured payload is byte-identical, but the user-facing rendered
        string is semantically-equivalent across runtimes
        (`runtime-abstraction.md:152`). Scored by an LLM-judge probe in the
        Phase-03 semantic-equivalence harness; NOT collected as a Phase-02
        byte-identity gate."""
        ...


__all__ = ["KailashRuntime"]


# Suppress unused-import warning while keeping the typing.Optional symbol
# available for downstream files that re-import from this module's namespace.
_ = Optional
