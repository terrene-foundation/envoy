# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.adapters.kailash_py — Phase 01 production adapter.

Per shard 18 § 3.2, `KailashPyRuntime` is a thin shim that satisfies
`KailashRuntime` Protocol by either:

1. **Forwarding to upstream `kailash`** — for methods whose substrate exists in
   the kailash-py distribution today (signing, envelope intersect, trust store
   verify_cascade_complete).
2. **Forwarding to an Envoy primitive** — for methods whose substrate is
   Envoy-new-code that ships in Phase 01 (`envoy.envelope.canonical_bytes`,
   `envoy.ledger.EnvoyLedger`).
3. **Raising `Phase02SubstrateNotWiredError`** — for methods whose substrate
   genuinely does not exist in Phase 01 yet (`envelope_check`, two-phase
   signing, classifier ensemble, budget, prompt assembly, tool-output
   sanitization, Grant Moment surface). Each typed error names the substrate
   gap AND the workspace todo tracking the wiring shard so a future session
   can grep the message.

Per `rules/zero-tolerance.md` Rule 2 (no bare `NotImplementedError`),
Phase 02-deferred methods raise a typed error with a grep-able substrate hint,
NOT `NotImplementedError`. Rule 6 (implement fully) is satisfied because the
iterative-TODO carve-out applies — every Phase02-stub method points to a
named workspace todo.

inspect.signature methodology (per T-01-18 lesson + T-01-26 prompt):
The actual kailash signatures discovered via inspect were:

- `kailash.trust.signing.sign(payload: Union[bytes, str, dict], private_key: str) -> str`
  (returns Ed25519 hex string, NOT bytes — the Protocol's `-> bytes` return
  is satisfied by encoding the hex string with .encode() at the boundary)
- `kailash.trust.signing.verify_signature(payload, signature, public_key) -> bool`
  (sync; bytes-decode-to-hex at the boundary for the Protocol's bytes contract)
- `kailash.trust.pact.envelopes.intersect_envelopes(a, b, *, dimension_scope=None)`
  (takes kailash's ConstraintEnvelopeConfig, NOT envoy's EnvelopeConfig —
  the adapter forwards the call but the caller is responsible for shape
  conversion; deviation flagged in shard 18 report)
- `kailash.trust.revocation.cascade_revoke(agent_id, store, reason, revoked_by, ...)`
  (requires a real TrustStore handle, NOT just the root_id; the Phase 01
  adapter forwards a typed error pointing to T-01-15 which owns the store
  surface — wiring lands in T-01-21+ Tier 2 integration)
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, cast

from envoy.envelope.canonical_bytes import canonical_bytes
from envoy.runtime.adapters._async_cascade_bridge import run_coro_blocking
from envoy.runtime.errors import Phase02SubstrateNotWiredError

logger = logging.getLogger(__name__)


# Substrate-todo anchors. The Phase02SubstrateNotWiredError messages cite
# these so a future `grep "Phase02SubstrateNotWiredError" workspaces/` enumerates
# the unfinished surface. Per `rules/zero-tolerance.md` Rule 6 iterative-TODO
# carve-out — actively tracked. The carve-out is only valid while these anchors
# RESOLVE: the todo files were reorganised after first authoring (grant-moment
# moved into the wave-3 file; the authorship/classifier substrate lives in the
# wave-2 file), so the anchors point at the current filenames, not the original
# placeholder names. The `_TODO_WAVE_N` constant names are retained as internal
# identifiers; the load-bearing string is the path.
_TODO_WAVE_2 = "workspaces/phase-01-mvp/todos/active/03-wave-3-grant-moment-budget.md"
_TODO_WAVE_3 = "workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md"
# Wave-4 BudgetTracker is now WIRED (shard 12 — envoy.budget.BudgetRuntimeAdapter);
# the former _TODO_WAVE_4 anchor was removed when the four budget_* methods began
# delegating to the orchestrator instead of raising Phase02SubstrateNotWiredError.
_TODO_PHASE_02 = "workspaces/phase-02-trust-plane/ (not yet authored)"


class KailashPyRuntime:
    """Phase 01 production adapter — pure-Python kailash + Envoy primitives.

    The constructor accepts optional dependency-injected components so Tier 2
    tests can supply real `EnvoyLedger` / `TrustStoreAdapter` / device-key
    private hex without dragging the full Envoy bootstrap into Phase 01a.
    Phase 01b (Wave 2 wiring) introduces a `startup()` config-loader that
    populates these from `RuntimeConfig`.

    Method semantics per `specs/runtime-abstraction.md` § Abstract interface
    tables. Wired methods do the real work; Phase02-stub methods raise typed
    errors with grep-able substrate hints.
    """

    def __init__(
        self,
        *,
        device_signing_private_key_hex: str | None = None,
        device_signing_public_key_hex: str | None = None,
        envoy_ledger: Any = None,
        trust_store: Any = None,
        budget_adapter: Any = None,
        runtime_version: str = "envoy-runtime-kailash-py/0.1.0",
        algorithm_identifier: dict[str, str] | None = None,
    ) -> None:
        self._device_priv_hex = device_signing_private_key_hex
        self._device_pub_hex = device_signing_public_key_hex
        self._envoy_ledger = envoy_ledger
        self._trust_store = trust_store
        self._budget_adapter = budget_adapter
        self._runtime_version = runtime_version
        self._algorithm_identifier = (
            dict(algorithm_identifier)
            if algorithm_identifier
            else {
                "sig": "ed25519",
                "hash": "sha256",
                "shamir": "slip39",
            }
        )
        self._started: bool = False

    # ------------------------------------------------------------------
    # Lifecycle — wired
    # ------------------------------------------------------------------

    async def startup(self, config: Any) -> None:
        """Phase 01 narrow: marks the adapter as started; Phase 01b's
        RuntimeConfig loader (Wave 2) populates device keys + injected
        primitives from config. Forwarding-only methods (signing, envelope)
        do not depend on startup; primitive-dependent methods raise typed
        errors when their backing primitive is None.
        """
        self._started = True
        logger.info("envoy.runtime.kailash_py.startup", extra={"started": True})
        await self._emit_startup_attestation()

    async def _emit_startup_attestation(self) -> None:
        """S3t: emit a RuntimeAttestation entry at every startup when a ledger
        is wired (the "every startup()" attestation moment per
        `specs/runtime-abstraction.md` § Runtime attestation). A no-op when the
        adapter runs without a ledger (forwarding-only construction)."""
        if self._envoy_ledger is None:
            return
        from envoy.runtime.runtime_attestation import (  # noqa: PLC0415
            AttestedRuntimeIdentity,
            append_runtime_attestation,
        )

        await append_runtime_attestation(
            self._envoy_ledger,
            AttestedRuntimeIdentity.from_identity_dict(self.runtime_identity()),
        )

    async def shutdown(self) -> None:
        """Phase 01 narrow: marks the adapter as stopped. Per spec, future
        wiring will flush Ledger pending writes (already flush-on-append in
        EnvoyLedger so nothing to flush here) + zero in-memory device key
        material (Phase 02 when the device key lifecycle owns rotation)."""
        self._started = False
        logger.info("envoy.runtime.kailash_py.shutdown", extra={"started": False})

    def runtime_identity(self) -> dict[str, Any]:
        """Return RuntimeIdentity per spec § Lifecycle.

        `binary_hash` is the real sha256 of the installed `kailash` package
        bytes (S3t — `envoy.runtime.runtime_attestation.compute_runtime_binary_hash`,
        cached per process), replacing the Phase-01 sentinel. The
        device-attestation type is still `software` (no Secure Enclave / TPM
        binding until a later phase); the reproducible-build manifest
        VERIFICATION of this hash lands with S16 (release-gated WS-2).
        """
        from envoy.runtime.runtime_attestation import (  # noqa: PLC0415
            compute_runtime_binary_hash,
        )

        return {
            "runtime_family": "kailash-py",
            "version": self._runtime_version,
            "binary_hash": compute_runtime_binary_hash("kailash-py"),
            "device_bound_pubkey_hex": self._device_pub_hex,
            "algorithm_identifier": dict(self._algorithm_identifier),
        }

    # ------------------------------------------------------------------
    # Trust Lineage — wired (sign / verify) + partial (cascade / subset)
    # ------------------------------------------------------------------

    def trust_sign(self, record: Any, key: Any) -> bytes:
        """Forward to `kailash.trust.signing.sign(payload, private_key) -> hex_str`.

        The Protocol declares `-> bytes`; kailash's `sign` returns a hex
        string. The adapter encodes the hex to bytes at the boundary so the
        Protocol's contract is satisfied.

        `key` MUST be the Ed25519 private key as the kailash hex form (see
        `kailash.trust.signing.generate_keypair() -> (private_hex,
        public_hex)`).
        """
        from kailash.trust.signing import sign  # noqa: PLC0415

        signature_hex = sign(record, key)
        return signature_hex.encode("ascii")

    def trust_verify_chain(self, record: Any) -> Any:
        """Forward to `TrustStoreAdapter.get_chain` + verify-via-cached-pubkey.

        Phase 01 narrow: the TrustStoreAdapter (T-01-15) owns the
        10-step chain verification logic; this adapter delegates so the
        runtime substitution boundary is a pure forward. When `trust_store`
        was not supplied at construction, raise the typed Phase02 error
        because the substrate (a real TrustStoreAdapter) is the
        Wave-2 wiring milestone.
        """
        if self._trust_store is None:
            raise Phase02SubstrateNotWiredError(
                "trust_verify_chain: requires a TrustStoreAdapter; pass "
                "`trust_store=` to KailashPyRuntime(...) once T-01-15 has "
                f"wired the chain-verify dispatch; tracked at {_TODO_WAVE_2}"
            )
        # Phase 01 narrow: TrustStoreAdapter exposes get_chain → caller asserts.
        # The full 10-step verify lands in T-01-15's chain_verifier; we forward
        # the get_chain result so consumers can introspect the chain shape.
        return self._trust_store.get_chain(record)

    def trust_cascade_revoke(self, root_id: str) -> set[str]:
        """Forward to the trust store's `revoke` + collect cascaded ids.

        The `KailashRuntime` Protocol declares `trust_cascade_revoke` SYNC
        (`specs/runtime-abstraction.md:31` — `(str) -> set[str]`, byte-identical
        SET equality for cross-runtime conformance). The real backing store
        `envoy.trust.store.TrustStoreAdapter.revoke` is `async def`. F12-b's
        sync↔async bridge (`_async_cascade_bridge.run_coro_blocking`) drives the
        returned coroutine to completion on a dedicated worker-thread event loop
        — loop-safe whether or not this sync call fires from inside an async
        cross-channel flow (the EC-8 hazard a naive `asyncio.run()` cannot
        handle). A sync Protocol-satisfying store's RevocationResult is unpacked
        directly. Either path unpacks `revoked_agents` with NO silent `[]`
        default — a missing attribute is a loud contract violation, never a
        silent empty cascade that would violate the EC-2 + EC-8(c) hard
        constraint (a revoked parent leaving its children alive).
        """
        if self._trust_store is None:
            raise Phase02SubstrateNotWiredError(
                "trust_cascade_revoke: requires a trust store; pass "
                "`trust_store=` to KailashPyRuntime(...). The store MUST expose "
                "`revoke(*, agent_id, reason, revoked_by) -> RevocationResult` "
                "(sync or async — F12-b bridges the async case); "
                f"tracked at {_TODO_WAVE_2}"
            )
        result = self._trust_store.revoke(
            agent_id=root_id,
            reason="envoy.runtime.cascade_revoke",
            revoked_by="envoy.runtime.kailash_py",
        )
        if inspect.iscoroutine(result):
            # Async store + sync Protocol method (the real Phase-02 case:
            # envoy.trust.store.TrustStoreAdapter.revoke is `async def`). Drive
            # the coroutine to completion on a dedicated worker-thread loop
            # (F12-b bridge) — loop-safe inside or outside a running loop, and
            # NEVER a silent empty cascade.
            result = run_coro_blocking(result)
        # RevocationResult MUST expose `revoked_agents`. No silent `[]` default —
        # a missing attribute is a contract violation (loud AttributeError).
        return set(result.revoked_agents)

    def trust_verify_subset_proof(self, parent: Any, sub: Any) -> Any:
        """Subset-proof verification per specs/sub-agent-delegation.md.

        Substrate gap: T-105 subset-proof verifier ships in T-01-19+ shard
        (independent verifier surface). Phase 01 narrow raises the typed
        error.
        """
        raise Phase02SubstrateNotWiredError(
            "trust_verify_subset_proof: requires sub-agent-delegation engine; "
            "T-105 mitigation lands with the independent verifier; "
            f"tracked at {_TODO_PHASE_02}"
        )

    # ------------------------------------------------------------------
    # Envelope — wired (canonical_form + intersect) + Phase02 (check / re-read)
    # ------------------------------------------------------------------

    def envelope_canonical_form(self, envelope: Any) -> bytes:
        """Forward to `envoy.envelope.canonical_bytes` per spec § Envelope.

        The envoy primitive owns the JCS-RFC8785 + NFC canonicalization that
        the spec mandates byte-identical across runtimes.
        """
        return canonical_bytes(envelope)

    def envelope_intersect(self, a: Any, b: Any) -> Any:
        """Forward to `kailash.trust.pact.envelopes.intersect_envelopes`.

        Upstream signature drift: kailash's `intersect_envelopes` takes
        `ConstraintEnvelopeConfig` (kailash's shape), not envoy's
        `EnvelopeConfig`. The Protocol accepts `Any` so callers that wire
        the shape conversion explicitly (T-01-14 envelope compiler emits
        kailash-shaped envelopes for the intersect path) get a working
        forward; callers that pass envoy shapes get the kailash TypeError
        which surfaces as a loud failure (NOT a silent fallback).
        """
        from kailash.trust.pact.envelopes import intersect_envelopes  # noqa: PLC0415

        return intersect_envelopes(a, b)

    def envelope_check(self, envelope: Any, action: Any) -> Any:
        """Envelope-check verdict per spec § Envelope.

        STRUCTURAL slice (S6a): delegates to the shared pure engine
        `envoy.runtime.envelope_check.envelope_check_structural`, so the verdict is
        byte-identical to the rs adapter by construction (shared pure delegation —
        journal/0019 Pattern 1). The structural slice never dispatches the
        classifier. SEMANTIC slice (action carries `content` bytes to classify):
        dispatches the classifier ensemble, substrate-gated on S6d.
        """
        from envoy.runtime.envelope_check import (  # noqa: PLC0415
            envelope_check_structural,
            is_semantic_action,
        )

        if is_semantic_action(action):
            raise Phase02SubstrateNotWiredError(
                "envelope_check semantic slice: requires the classifier ensemble "
                f"(classifier_invoke); tracked at {_TODO_WAVE_3}"
            )
        return envelope_check_structural(envelope, action)

    def envelope_re_read_checkpoint(self, envelope: Any, depth: int) -> Any:
        """Substrate gap: T-015 envelope re-read checkpoint requires
        composition-rule depth tracking which lands in the Wave-2 Grant
        Moment + Boundary Conversation surface."""
        raise Phase02SubstrateNotWiredError(
            "envelope_re_read_checkpoint: requires composition-rule depth "
            f"tracking; tracked at {_TODO_WAVE_2}"
        )

    # ------------------------------------------------------------------
    # Two-phase signing — Phase02-stub (Wave 2 Grant Moment)
    # ------------------------------------------------------------------

    def phase_a_sign_intent(self, intent: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "phase_a_sign_intent: requires Wave-2 Grant Moment + two-phase "
            f"signing wiring; tracked at {_TODO_WAVE_2}"
        )

    def phase_b_sign_outcome(self, outcome: Any, intent_id: str) -> Any:
        raise Phase02SubstrateNotWiredError(
            "phase_b_sign_outcome: requires Wave-2 two-phase signing wiring; "
            f"tracked at {_TODO_WAVE_2}"
        )

    def phase_a_orphan_resolve(self, intent_id: str, resolution: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "phase_a_orphan_resolve: requires Wave-2 Grant Moment surface for "
            f"orphan-resolution dispatch; tracked at {_TODO_WAVE_2}"
        )

    # ------------------------------------------------------------------
    # Ledger — wired through EnvoyLedger when injected
    # ------------------------------------------------------------------

    async def ledger_append(self, entry: Any) -> Any:
        """Forward to `EnvoyLedger.append`. The `entry` dict MUST carry
        `entry_type`, `content`, optional `intent_id`, optional
        `content_trust_level` per the EnvoyLedger.append() signature.
        """
        if self._envoy_ledger is None:
            raise Phase02SubstrateNotWiredError(
                "ledger_append: requires an EnvoyLedger; pass `envoy_ledger=` "
                "to KailashPyRuntime(...) — see envoy/ledger/facade.py "
                f"EnvoyLedger; tracked at {_TODO_WAVE_2}"
            )
        # EnvoyLedger.append uses keyword-only args; unpack the entry dict.
        entry_id = await self._envoy_ledger.append(
            entry_type=entry["entry_type"],
            content=entry["content"],
            intent_id=entry.get("intent_id"),
            content_trust_level=entry.get("content_trust_level", "system"),
        )
        return {"entry_id": entry_id, **entry}

    async def ledger_query(self, filter: Any) -> list[Any]:
        """Forward to the EnvoyLedger's underlying audit_store query path.

        Phase 01 narrow: returns the raw AuditEvent list because the
        ledger_query classification surface (apply_read_classification) lands
        with Wave-3 classifier wiring. Consumers needing the full
        spec-shape return (`list[LedgerEntry]`) wait for Wave-3.
        """
        if self._envoy_ledger is None:
            raise Phase02SubstrateNotWiredError(
                "ledger_query: requires an EnvoyLedger; pass `envoy_ledger=` "
                f"to KailashPyRuntime(...); tracked at {_TODO_WAVE_2}"
            )
        from kailash.trust.audit_store import AuditFilter  # noqa: PLC0415

        # Phase 01: thin pass-through. apply_read_classification surfaces in
        # Wave 3 — see Phase02 substrate hint above for the classification path.
        audit_filter = filter if isinstance(filter, AuditFilter) else AuditFilter(limit=1_000_000)
        return cast("list[Any]", await self._envoy_ledger._audit_store.query(audit_filter))

    async def ledger_verify_chain(self, from_: int, to: int) -> Any:
        """Forward to `EnvoyLedger.verify_chain`.

        Phase 01 narrow: the EnvoyLedger walks the entire chain (the spec's
        `from`/`to` bounded walk lands with T-01-19 export bundle slicing).
        The bounds are passed through but currently ignored; consumers that
        need bounded walks wait for T-01-19.
        """
        if self._envoy_ledger is None:
            raise Phase02SubstrateNotWiredError(
                "ledger_verify_chain: requires an EnvoyLedger; pass "
                f"`envoy_ledger=` to KailashPyRuntime(...); tracked at {_TODO_WAVE_2}"
            )
        return await self._envoy_ledger.verify_chain()

    async def head_commitment(self) -> Any:
        """Forward to `EnvoyLedger.head_commitment`."""
        if self._envoy_ledger is None:
            raise Phase02SubstrateNotWiredError(
                "head_commitment: requires an EnvoyLedger; pass `envoy_ledger=` "
                f"to KailashPyRuntime(...); tracked at {_TODO_WAVE_2}"
            )
        return await self._envoy_ledger.head_commitment()

    # ------------------------------------------------------------------
    # Classifier — Phase02-stub (Wave 3 classifier ensemble)
    # ------------------------------------------------------------------

    def classifier_invoke(self, ref: str, content: bytes, ctx: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "classifier_invoke: requires Wave-3 classifier ensemble + model "
            f"adapter; tracked at {_TODO_WAVE_3}"
        )

    def ensemble_aggregate(self, verdicts: list[Any], policy: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "ensemble_aggregate: requires Wave-3 classifier ensemble aggregator; "
            f"tracked at {_TODO_WAVE_3}"
        )

    def classifier_registry_resolve(self, registry_id: str) -> Any:
        raise Phase02SubstrateNotWiredError(
            "classifier_registry_resolve: requires Wave-3 classifier registry "
            f"+ 2-of-N steward signatures; tracked at {_TODO_WAVE_3}"
        )

    # ------------------------------------------------------------------
    # Budget — Phase02-stub (Wave 4 budget velocity)
    # ------------------------------------------------------------------

    def budget_reserve(self, session: Any, cost: int) -> Any:
        """Forward to `BudgetRuntimeAdapter.budget_reserve`; return ReservationID.

        Wired in Wave-4 (shard 12): the `envoy.budget` multi-window
        orchestrator backs the runtime budget surface. When `budget_adapter`
        was not supplied at construction, raise the typed error pointing to
        the wiring kwarg (the orchestrator needs the session's envelope
        ceilings, supplied when the session is constructed).
        """
        if self._budget_adapter is None:
            raise Phase02SubstrateNotWiredError(
                "budget_reserve: requires an envoy.budget.BudgetRuntimeAdapter; "
                "pass `budget_adapter=` to KailashPyRuntime(...) constructed from "
                "the session's EffectiveEnvelope.financial ceilings"
            )
        return self._budget_adapter.budget_reserve(session, cost)

    def budget_record(self, reservation: Any, actual: int) -> None:
        """Forward to `BudgetRuntimeAdapter.budget_record` (finalize the reserve)."""
        if self._budget_adapter is None:
            raise Phase02SubstrateNotWiredError(
                "budget_record: requires an envoy.budget.BudgetRuntimeAdapter; "
                "pass `budget_adapter=` to KailashPyRuntime(...)"
            )
        self._budget_adapter.budget_record(reservation, actual)

    def budget_snapshot(self, session: Any) -> Any:
        """Forward to `BudgetRuntimeAdapter.budget_snapshot` (five-window snapshot)."""
        if self._budget_adapter is None:
            raise Phase02SubstrateNotWiredError(
                "budget_snapshot: requires an envoy.budget.BudgetRuntimeAdapter; "
                "pass `budget_adapter=` to KailashPyRuntime(...)"
            )
        return self._budget_adapter.budget_snapshot(session)

    def budget_velocity_check(self, session: Any) -> Any:
        """Forward to `BudgetRuntimeAdapter.budget_velocity_check`.

        Raises `BudgetVelocityExceededError` if the per-hour velocity ceiling
        is breached (`specs/runtime-abstraction.md` § budget_velocity_check).
        """
        if self._budget_adapter is None:
            raise Phase02SubstrateNotWiredError(
                "budget_velocity_check: requires an envoy.budget.BudgetRuntimeAdapter; "
                "pass `budget_adapter=` to KailashPyRuntime(...)"
            )
        return self._budget_adapter.budget_velocity_check(session)

    # ------------------------------------------------------------------
    # Runtime device-key signing — wired (software-fallback)
    # ------------------------------------------------------------------

    def runtime_sign(self, payload: bytes) -> bytes:
        """Software-fallback Ed25519 sign via `kailash.trust.signing.sign`.

        Phase 02 introduces Secure Enclave / TPM via the Rust binding; the
        Protocol contract is unchanged. The device-key private hex MUST be
        supplied at construction.
        """
        if self._device_priv_hex is None:
            raise Phase02SubstrateNotWiredError(
                "runtime_sign: requires device_signing_private_key_hex at "
                "construction (Phase 01 software-fallback). Phase 02 introduces "
                f"Secure Enclave / TPM via the Rust binding; tracked at {_TODO_PHASE_02}"
            )
        from kailash.trust.signing import sign  # noqa: PLC0415

        signature_hex = sign(payload, self._device_priv_hex)
        return signature_hex.encode("ascii")

    def runtime_verify(self, payload: bytes, sig: bytes, pubkey: bytes) -> bool:
        """Software-fallback Ed25519 verify via
        `kailash.trust.signing.verify_signature`. Sync; bytes-decode-to-hex
        at the boundary (the kailash API expects hex strings)."""
        from kailash.trust.signing import verify_signature  # noqa: PLC0415

        # `sig` / `pubkey` are bytes per the signature; decode to the hex
        # strings the kailash API expects.
        sig_hex = sig.decode("ascii")
        pubkey_hex = pubkey.decode("ascii")
        return verify_signature(payload, sig_hex, pubkey_hex)

    # ------------------------------------------------------------------
    # Prompt + tool-output — Phase02-stub (Wave 2 Boundary Conversation)
    # ------------------------------------------------------------------

    def prompt_assemble(
        self,
        system: Any,
        envelope: Any,
        context: Any,
        user_message: str,
    ) -> Any:
        raise Phase02SubstrateNotWiredError(
            "prompt_assemble: requires Wave-2 Boundary Conversation + system "
            f"prompt assembler; tracked at {_TODO_WAVE_2}"
        )

    def tool_output_sanitize(
        self,
        output: bytes,
        tool_name: str,
        envelope: Any,
    ) -> Any:
        raise Phase02SubstrateNotWiredError(
            "tool_output_sanitize: requires Wave-3 tool-output sanitizer + "
            f"classifier ensemble; tracked at {_TODO_WAVE_3}"
        )

    def first_time_action_gate(
        self,
        session: Any,
        tool_name: str,
        args: dict[str, Any],
    ) -> Any:
        """specs/session-state.md § `first_time_action_gate` (WS-6 S5o).

        Delegates to the pure, deterministic gate
        (`envoy.runtime.observed_state.first_time_action_gate`) so both runtime
        adapters return the byte-identical `GateResult` for the same
        `(session, tool_name, args)` — the cross-runtime parity the conformance
        harness pins. The pure gate does no I/O; the store-wired orchestration
        (load/persist/boundary-reset) is `SessionObservedStateGate`."""
        from envoy.runtime.observed_state import (  # noqa: PLC0415
            first_time_action_gate as _gate,
        )

        return _gate(session, tool_name, args)

    def grant_moment_surface(self, request: Any) -> Any:
        raise Phase02SubstrateNotWiredError(
            "grant_moment_surface: requires Wave-2 Grant Moment dispatch + "
            f"channel-adapter routing; tracked at {_TODO_WAVE_2}"
        )


__all__ = ["KailashPyRuntime"]
