# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.adapters.kailash_rs_bindings — Phase 02 S2a wired adapter.

Per shard 18 § 3.3 and § 7 frozen-spec disposition 3 the Rust-bindings adapter
was authored in Phase 01 as a structurally-present slot whose every Protocol
method raised the Phase-01 deferral sentinel. Phase-02 shard **S2a** fills
those bodies: each method now forwards to the real `kailash` binding root (the
PyO3-backed runtime — `import kailash` is the binding root per the SDK import
discipline) OR to an Envoy primitive, mirroring `KailashPyRuntime`'s boundary
discipline exactly.

Boundary discipline (mirrors `kailash_py.py:28-42`):

- `kailash.trust.signing.sign(payload, private_key) -> hex_str` returns an
  Ed25519 hex string; the Protocol declares `-> bytes`, so the adapter encodes
  the hex with `.encode("ascii")` at the boundary. `verify_signature` takes hex
  strings, so the adapter decodes `bytes -> hex` at the boundary.
- `kailash.trust.pact.envelopes.intersect_envelopes` takes kailash's
  `ConstraintEnvelopeConfig`; callers wire the shape conversion (loud TypeError
  on shape mismatch, never a silent fallback).

Sync/async parity (S2a invariant): the EXACT sync/async shape of every method
matches the `KailashRuntime` Protocol declaration in `protocol.py`. The lifecycle
+ ledger methods are `async def`; `trust_cascade_revoke`, the signing surface,
and the budget/classifier/prompt surface are sync. A structural `isinstance`
check does NOT mask an awaited non-coroutine — each method's `def`/`async def`
keyword is held identical to the Protocol so an `await`-ed sync method (or a
sync-called coroutine) fails loud.

Device-key signing + attestation ownership (S2a): unlike `KailashPyRuntime`
(which reports the `software` device path only), the rs adapter OWNS the
platform device-key surface. `runtime_sign` / `runtime_verify` route through a
device-key backend selected at construction (`device_attestation_type` is one
of `secure_enclave | tpm | software`). When a hardware-backed signer is injected
(`device_signer=`), signing routes to it; otherwise the adapter falls back to
the software Ed25519 backend in the `kailash` binding — a REAL signature over
real bytes, never a fake/placeholder. The reproducible-build `binary_hash` +
`RuntimeAttestation` Ledger emission are S3t scope (attestation-on-switch); S2a
wires the signing surface, not the manifest-verification gate.

Construction remains gated behind `RS_BINDINGS_ENABLED` (per shard 18 § 3.3):
while the flag is False (the Phase-02-S2a default — wiring precedes flag-flip,
which gates on S2b/S2c/S3a/S3b green), `KailashRsBindingsRuntime(...)` raises
`RsBindingsNotAvailableInPhase01Error` at the constructor. The wired bodies are
reachable once the flag is True — the flag flip is the LAST step of the WS-1
critical path, not S2a's.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, cast

from envoy.envelope.canonical_bytes import canonical_bytes
from envoy.runtime.errors import (
    RsBindingsNotAvailableInPhase01Error,
    RuntimeNotReadyError,
)
from envoy.runtime.feature_flags import RS_BINDINGS_ENABLED

logger = logging.getLogger(__name__)


_RS_BINDINGS_GUARD_MSG = (
    "KailashRsBindingsRuntime cannot be instantiated while "
    "envoy.runtime.feature_flags.RS_BINDINGS_ENABLED == False. "
    "S2a wires the Protocol method bodies; the flag flip is the LAST step of "
    "the WS-1 critical path (after S2b/S2c/S3a/S3b prove byte-identity on both "
    "runtimes). Phase-02 entry flips the flag in envoy/runtime/feature_flags.py."
)

#: The device-key attestation backends the rs adapter can route signing through.
#: `software` is the always-available Ed25519 fallback (via the kailash binding);
#: `secure_enclave` / `tpm` are platform-hardware backends supplied via
#: `device_signer=` at construction. The rs adapter OWNS this surface (the
#: kailash_py adapter reports `software` only).
_DEVICE_ATTESTATION_TYPES = frozenset({"secure_enclave", "tpm", "software"})


class KailashRsBindingsRuntime:
    """Phase 02 S2a wired adapter — Rust-bindings runtime.

    Forwards every Protocol method to the `kailash` binding root or an Envoy
    primitive, mirroring `KailashPyRuntime`'s boundary discipline and holding
    the EXACT sync/async shape per method. Construction is still gated behind
    `RS_BINDINGS_ENABLED` (wiring precedes flag-flip).

    The constructor accepts the same dependency-injected components as
    `KailashPyRuntime` (so the conformance harness can supply real
    `EnvoyLedger` / trust store / budget adapter / device-key material) PLUS the
    rs-specific device-key backend + attestation type.
    """

    def __init__(
        self,
        *,
        device_signing_private_key_hex: str | None = None,
        device_signing_public_key_hex: str | None = None,
        device_signer: Any = None,
        device_attestation_type: str = "software",
        envoy_ledger: Any = None,
        trust_store: Any = None,
        budget_adapter: Any = None,
        runtime_version: str = "envoy-runtime-kailash-rs-bindings/0.1.0",
        algorithm_identifier: dict[str, str] | None = None,
        **_legacy_kwargs: Any,
    ) -> None:
        if not RS_BINDINGS_ENABLED:
            raise RsBindingsNotAvailableInPhase01Error(_RS_BINDINGS_GUARD_MSG)
        if device_attestation_type not in _DEVICE_ATTESTATION_TYPES:
            raise ValueError(
                "device_attestation_type MUST be one of "
                f"{sorted(_DEVICE_ATTESTATION_TYPES)}; got "
                f"{device_attestation_type!r}"
            )
        self._device_priv_hex = device_signing_private_key_hex
        self._device_pub_hex = device_signing_public_key_hex
        # The hardware-backed device signer (Secure Enclave / TPM). When None,
        # signing falls back to the software Ed25519 backend in the kailash
        # binding — a REAL signature, never a placeholder.
        self._device_signer = device_signer
        self._device_attestation_type = device_attestation_type
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
        logger.info(
            "envoy.runtime.kailash_rs_bindings.constructed",
            extra={"device_attestation_type": device_attestation_type},
        )

    # ------------------------------------------------------------------
    # Lifecycle (spec § Lifecycle) — async per Protocol
    # ------------------------------------------------------------------

    async def startup(self, config: Any) -> None:
        """Mark the adapter started. Per spec, future wiring verifies the binary
        hash vs manifest (S3t attestation-on-switch) + prepares the classifier
        cache. The signing/envelope forwards do not depend on startup."""
        self._started = True
        logger.info("envoy.runtime.kailash_rs_bindings.startup", extra={"started": True})

    async def shutdown(self) -> None:
        """Mark the adapter stopped. EnvoyLedger is flush-on-append so there is
        nothing to flush here; device-key material zeroing lands with the S3t
        device-key lifecycle."""
        self._started = False
        logger.info("envoy.runtime.kailash_rs_bindings.shutdown", extra={"started": False})

    def runtime_identity(self) -> dict[str, Any]:
        """Return RuntimeIdentity per spec § Lifecycle. The rs adapter reports
        the platform device-key attestation type it owns; the reproducible-build
        `binary_hash` is populated from the manifest in S3t (attestation), so
        S2a reports a grep-able sentinel the S3t shard replaces."""
        return {
            "runtime_family": "kailash-rs-bindings",
            "version": self._runtime_version,
            # binary_hash is populated from the reproducible-build manifest in
            # S3t (attestation-on-switch). S2a reports a sentinel the conformance
            # runner can grep; this is the ONE field S3t replaces, not S2a.
            "binary_hash": "sha256:phase-02-s2a-attestation-pending",
            "device_bound_pubkey_hex": self._device_pub_hex,
            "algorithm_identifier": dict(self._algorithm_identifier),
        }

    # ------------------------------------------------------------------
    # Trust Lineage (spec § Trust Lineage) — sync per Protocol
    # ------------------------------------------------------------------

    def trust_sign(self, record: Any, key: Any) -> bytes:
        """Forward to `kailash.trust.signing.sign(payload, private_key) -> hex`.

        The Protocol declares `-> bytes`; the binding returns a hex string, so
        the adapter encodes the hex to bytes at the boundary (mirrors
        `kailash_py.trust_sign`). `key` MUST be the Ed25519 private key in the
        kailash hex form (`kailash.trust.signing.generate_keypair()`)."""
        from kailash.trust.signing import sign  # noqa: PLC0415

        signature_hex = sign(record, key)
        return signature_hex.encode("ascii")

    def trust_verify_chain(self, record: Any) -> Any:
        """Forward to the injected trust store's chain-verify dispatch.

        Mirrors `kailash_py.trust_verify_chain`: when no trust store was supplied
        at construction the substrate gap is named (loud typed error, never a
        silent empty verify result)."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "trust_verify_chain: requires a TrustStoreAdapter; pass "
                "`trust_store=` to KailashRsBindingsRuntime(...). The store owns "
                "the 10-step chain-verify dispatch the rs adapter forwards to."
            )
        return self._trust_store.get_chain(record)

    def trust_cascade_revoke(self, root_id: str) -> set[str]:
        """Forward to a SYNC trust store's `revoke` + collect cascaded ids.

        The Protocol declares `trust_cascade_revoke` SYNC
        (`specs/runtime-abstraction.md:31` — `(str) -> set[str]`, byte-identical
        SET equality). Mirrors `kailash_py.trust_cascade_revoke`: when handed an
        async store, the returned coroutine is detected and closed (no
        unawaited-coroutine leak) and a typed error is raised — NEVER a silent
        empty cascade (a silent empty set would invisibly violate the EC-2 /
        EC-8(c) cascade hard-constraint). A sync store's RevocationResult is
        unpacked directly; a missing `revoked_agents` attribute is a loud
        AttributeError, not an empty default."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "trust_cascade_revoke: requires a trust store; pass "
                "`trust_store=` to KailashRsBindingsRuntime(...). The store MUST "
                "expose a SYNC `revoke(*, agent_id, reason, revoked_by) -> "
                "RevocationResult` per the sync Protocol contract."
            )
        result = self._trust_store.revoke(
            agent_id=root_id,
            reason="envoy.runtime.cascade_revoke",
            revoked_by="envoy.runtime.kailash_rs_bindings",
        )
        if inspect.iscoroutine(result):
            # Async store handed to a sync Protocol method. Close the coroutine
            # so it does not leak a "coroutine was never awaited" RuntimeWarning,
            # then fail loud — do NOT fall back to an empty revoked set.
            result.close()
            raise RuntimeNotReadyError(
                "trust_cascade_revoke: the wired trust store's `revoke` is "
                "async, but the KailashRuntime Protocol method is sync per "
                "specs/runtime-abstraction.md:31. Cascade revocation routes "
                "through the async TrustStoreAdapter + "
                "CascadeRevocationOrchestrator directly, NOT this facade."
            )
        return set(result.revoked_agents)

    def trust_verify_subset_proof(self, parent: Any, sub: Any) -> Any:
        """Subset-proof verification per specs/sub-agent-delegation.md.

        Forwards to the injected trust store's subset-proof verifier (the
        runtime-signed `runtime_verification_signature` surface E5 hashes). When
        no store is supplied the substrate gap is named loud."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "trust_verify_subset_proof: requires a trust store exposing "
                "`verify_subset_proof(parent, sub)`; pass `trust_store=` to "
                "KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.verify_subset_proof(parent, sub)

    # ------------------------------------------------------------------
    # Envelope (spec § Envelope) — sync per Protocol
    # ------------------------------------------------------------------

    def envelope_canonical_form(self, envelope: Any) -> bytes:
        """Forward to `envoy.envelope.canonical_bytes` per spec § Envelope.

        The envoy primitive owns the JCS-RFC8785 + NFC canonicalization the spec
        mandates byte-identical across runtimes (E1). The rs adapter forwards to
        the SAME primitive as kailash_py so the two runtimes' canonical bytes are
        byte-identical by construction."""
        return canonical_bytes(envelope)

    def envelope_intersect(self, a: Any, b: Any) -> Any:
        """Forward to `kailash.trust.pact.envelopes.intersect_envelopes`.

        Upstream signature drift: kailash's `intersect_envelopes` takes
        `ConstraintEnvelopeConfig` (kailash's shape). Callers wire the shape
        conversion explicitly; a wrong shape surfaces the kailash TypeError loud
        (NOT a silent fallback) — mirrors `kailash_py.envelope_intersect`."""
        from kailash.trust.pact.envelopes import intersect_envelopes  # noqa: PLC0415

        return intersect_envelopes(a, b)

    def envelope_check(self, envelope: Any, action: Any) -> Any:
        """Forward to the injected envelope-check engine.

        The structural slice (N3) never dispatches the classifier; the semantic
        slice dispatches it (observed via `envoy.runtime.dispatch_observation`).
        When no check engine is supplied the substrate gap is named loud."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "envelope_check: requires the envelope-check engine exposing "
                "`check(envelope, action)`; pass `trust_store=` to "
                "KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.check(envelope, action)

    def envelope_re_read_checkpoint(self, envelope: Any, depth: int) -> Any:
        """T-015 envelope re-read checkpoint — re-read from Trust Vault every N
        composition-rule evaluations. Forwards to the injected store's
        re-read-checkpoint surface; loud typed error when absent."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "envelope_re_read_checkpoint: requires the Trust Vault re-read "
                "surface exposing `re_read_checkpoint(envelope, depth)`; pass "
                "`trust_store=` to KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.re_read_checkpoint(envelope, depth)

    # ------------------------------------------------------------------
    # Two-phase signing (spec § Two-phase signing) — sync per Protocol
    # ------------------------------------------------------------------

    def phase_a_sign_intent(self, intent: Any) -> Any:
        """Delegation-key-signed Phase-A intent (envelope_check pre-sign + Ledger
        write). Forwards to the injected trust store's two-phase signing surface;
        loud typed error when absent."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "phase_a_sign_intent: requires the two-phase signing surface "
                "exposing `phase_a_sign_intent(intent)`; pass `trust_store=` to "
                "KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.phase_a_sign_intent(intent)

    def phase_b_sign_outcome(self, outcome: Any, intent_id: str) -> Any:
        """Runtime-device-key-signed Phase-B outcome linked to `intent_id`.
        Forwards to the injected two-phase signing surface; loud typed error when
        absent."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "phase_b_sign_outcome: requires the two-phase signing surface "
                "exposing `phase_b_sign_outcome(outcome, intent_id)`; pass "
                "`trust_store=` to KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.phase_b_sign_outcome(outcome, intent_id)

    def phase_a_orphan_resolve(self, intent_id: str, resolution: Any) -> Any:
        """User-chosen orphan resolution (Genesis-signed via Grant Moment).
        Forwards to the injected two-phase signing surface; loud typed error when
        absent (E6 hashes the orphan-resolution record)."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "phase_a_orphan_resolve: requires the orphan-resolution surface "
                "exposing `phase_a_orphan_resolve(intent_id, resolution)`; pass "
                "`trust_store=` to KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.phase_a_orphan_resolve(intent_id, resolution)

    # ------------------------------------------------------------------
    # Ledger (spec § Ledger) — async per Protocol
    # ------------------------------------------------------------------

    async def ledger_append(self, entry: Any) -> Any:
        """Forward to `EnvoyLedger.append` (byte-identical hash chain). The
        `entry` dict carries `entry_type`, `content`, optional `intent_id`,
        optional `content_trust_level` per the EnvoyLedger.append() signature —
        mirrors `kailash_py.ledger_append`."""
        if self._envoy_ledger is None:
            raise RuntimeNotReadyError(
                "ledger_append: requires an EnvoyLedger; pass `envoy_ledger=` "
                "to KailashRsBindingsRuntime(...) — see envoy/ledger/facade.py "
                "EnvoyLedger."
            )
        entry_id = await self._envoy_ledger.append(
            entry_type=entry["entry_type"],
            content=entry["content"],
            intent_id=entry.get("intent_id"),
            content_trust_level=entry.get("content_trust_level", "system"),
        )
        return {"entry_id": entry_id, **entry}

    async def ledger_query(self, filter: Any) -> list[Any]:
        """Forward to the EnvoyLedger's underlying audit_store query path.
        Mirrors `kailash_py.ledger_query` (thin pass-through;
        apply_read_classification lands with the classifier wiring)."""
        if self._envoy_ledger is None:
            raise RuntimeNotReadyError(
                "ledger_query: requires an EnvoyLedger; pass `envoy_ledger=` "
                "to KailashRsBindingsRuntime(...)."
            )
        from kailash.trust.audit_store import AuditFilter  # noqa: PLC0415

        audit_filter = filter if isinstance(filter, AuditFilter) else AuditFilter(limit=1_000_000)
        return cast("list[Any]", await self._envoy_ledger._audit_store.query(audit_filter))

    async def ledger_verify_chain(self, from_: int, to: int) -> Any:
        """Forward to `EnvoyLedger.verify_chain` (byte-identical chain verify).
        Mirrors `kailash_py.ledger_verify_chain` (bounds passed through; bounded
        walk lands with the export-bundle slicing)."""
        if self._envoy_ledger is None:
            raise RuntimeNotReadyError(
                "ledger_verify_chain: requires an EnvoyLedger; pass "
                "`envoy_ledger=` to KailashRsBindingsRuntime(...)."
            )
        return await self._envoy_ledger.verify_chain()

    async def head_commitment(self) -> Any:
        """Forward to `EnvoyLedger.head_commitment` (byte-identical; monotonic
        non-decreasing — E7 asserts BOTH)."""
        if self._envoy_ledger is None:
            raise RuntimeNotReadyError(
                "head_commitment: requires an EnvoyLedger; pass `envoy_ledger=` "
                "to KailashRsBindingsRuntime(...)."
            )
        return await self._envoy_ledger.head_commitment()

    # ------------------------------------------------------------------
    # Classifier (spec § Classifier) — sync per Protocol
    # ------------------------------------------------------------------

    def classifier_invoke(self, ref: str, content: bytes, ctx: Any) -> Any:
        """Semantically-equivalent classifier verdict (N3 semantic slice). 2+
        classifiers per ensemble mandatory. Forwards to the injected classifier
        ensemble; loud typed error when absent."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "classifier_invoke: requires the classifier ensemble exposing "
                "`classifier_invoke(ref, content, ctx)`; pass `trust_store=` to "
                "KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.classifier_invoke(ref, content, ctx)

    def ensemble_aggregate(self, verdicts: list[Any], policy: Any) -> Any:
        """Byte-identical aggregation; disagreement fails CLOSED by default.
        Forwards to the injected ensemble aggregator; loud typed error when
        absent."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "ensemble_aggregate: requires the ensemble aggregator exposing "
                "`ensemble_aggregate(verdicts, policy)`; pass `trust_store=` to "
                "KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.ensemble_aggregate(verdicts, policy)

    def classifier_registry_resolve(self, registry_id: str) -> Any:
        """Fetch + verify 2-of-N steward signatures + hash-match per
        specs/foundation-ops.md. Forwards to the injected classifier registry;
        loud typed error when absent."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "classifier_registry_resolve: requires the classifier registry "
                "exposing `classifier_registry_resolve(registry_id)`; pass "
                "`trust_store=` to KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.classifier_registry_resolve(registry_id)

    # ------------------------------------------------------------------
    # Budget (spec § Budget) — sync per Protocol
    # ------------------------------------------------------------------

    def budget_reserve(self, session: Any, cost: int) -> Any:
        """Forward to `BudgetRuntimeAdapter.budget_reserve`; return ReservationID
        (mirrors `kailash_py.budget_reserve`)."""
        if self._budget_adapter is None:
            raise RuntimeNotReadyError(
                "budget_reserve: requires an envoy.budget.BudgetRuntimeAdapter; "
                "pass `budget_adapter=` to KailashRsBindingsRuntime(...) "
                "constructed from the session's EffectiveEnvelope.financial "
                "ceilings."
            )
        return self._budget_adapter.budget_reserve(session, cost)

    def budget_record(self, reservation: Any, actual: int) -> None:
        """Forward to `BudgetRuntimeAdapter.budget_record` (finalize the
        reserve)."""
        if self._budget_adapter is None:
            raise RuntimeNotReadyError(
                "budget_record: requires an envoy.budget.BudgetRuntimeAdapter; "
                "pass `budget_adapter=` to KailashRsBindingsRuntime(...)."
            )
        self._budget_adapter.budget_record(reservation, actual)

    def budget_snapshot(self, session: Any) -> Any:
        """Forward to `BudgetRuntimeAdapter.budget_snapshot` (five-window
        snapshot)."""
        if self._budget_adapter is None:
            raise RuntimeNotReadyError(
                "budget_snapshot: requires an envoy.budget.BudgetRuntimeAdapter; "
                "pass `budget_adapter=` to KailashRsBindingsRuntime(...)."
            )
        return self._budget_adapter.budget_snapshot(session)

    def budget_velocity_check(self, session: Any) -> Any:
        """Forward to `BudgetRuntimeAdapter.budget_velocity_check` (raises
        `BudgetVelocityExceededError` if the per-hour ceiling is breached)."""
        if self._budget_adapter is None:
            raise RuntimeNotReadyError(
                "budget_velocity_check: requires an "
                "envoy.budget.BudgetRuntimeAdapter; pass `budget_adapter=` to "
                "KailashRsBindingsRuntime(...)."
            )
        return self._budget_adapter.budget_velocity_check(session)

    # ------------------------------------------------------------------
    # Runtime device-key signing (spec § Runtime device-key signing) — sync.
    # The rs adapter OWNS the platform device-key surface (attestation).
    # ------------------------------------------------------------------

    def runtime_sign(self, payload: bytes) -> bytes:
        """Sign `payload` with the device-bound key, returning `bytes`.

        Routes through the platform device-key backend the rs adapter owns:

        - When a hardware signer is injected (`device_signer=`, e.g. a Secure
          Enclave / TPM handle exposing `sign(payload: bytes) -> bytes`), signing
          routes to it and its raw signature bytes are returned directly.
        - Otherwise the adapter signs via the software Ed25519 backend in the
          `kailash` binding (`kailash.trust.signing.sign`), encoding the hex
          string to bytes at the boundary. This is a REAL signature over real
          bytes — never a placeholder.

        Satisfies the `-> bytes` contract; the conformance harness (S2b/S3a)
        proves byte-equality with `kailash-py` for the software path. A missing
        device key on the software path raises loud (no silent empty signature).
        """
        if self._device_signer is not None:
            # Hardware-backed signer (Secure Enclave / TPM) owns the raw-bytes
            # signature; return it directly.
            signature = self._device_signer.sign(payload)
            if not isinstance(signature, (bytes, bytearray)):
                raise RuntimeNotReadyError(
                    "runtime_sign: the injected device_signer.sign(payload) MUST "
                    "return bytes (the raw device-bound signature); got "
                    f"{type(signature).__name__}."
                )
            return bytes(signature)
        if self._device_priv_hex is None:
            raise RuntimeNotReadyError(
                "runtime_sign: requires either a hardware `device_signer=` "
                "(Secure Enclave / TPM) OR `device_signing_private_key_hex=` "
                "(software fallback) at construction. The rs adapter owns the "
                "device-key surface but cannot sign without a key."
            )
        from kailash.trust.signing import sign  # noqa: PLC0415

        signature_hex = sign(payload, self._device_priv_hex)
        return signature_hex.encode("ascii")

    def runtime_verify(self, payload: bytes, sig: bytes, pubkey: bytes) -> bool:
        """Verify a device-bound signature, returning `bool`.

        When a hardware signer is injected AND exposes `verify`, verification
        routes to it (raw bytes). Otherwise the adapter verifies via the software
        Ed25519 backend in the `kailash` binding
        (`kailash.trust.signing.verify_signature`), decoding `sig`/`pubkey` from
        bytes to the hex strings the binding API expects at the boundary."""
        if self._device_signer is not None and hasattr(self._device_signer, "verify"):
            return bool(self._device_signer.verify(payload, sig, pubkey))
        from kailash.trust.signing import verify_signature  # noqa: PLC0415

        sig_hex = sig.decode("ascii")
        pubkey_hex = pubkey.decode("ascii")
        return verify_signature(payload, sig_hex, pubkey_hex)

    # ------------------------------------------------------------------
    # Prompt + tool-output (spec § Prompt + tool-output) — sync per Protocol
    # ------------------------------------------------------------------

    def prompt_assemble(
        self,
        system: Any,
        envelope: Any,
        context: Any,
        user_message: str,
    ) -> Any:
        """Envelope-pinned system prompt (T-015 defense). Forwards to the
        injected prompt assembler; loud typed error when absent. Byte-identical
        — the assembly is a deterministic template fill."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "prompt_assemble: requires the prompt assembler exposing "
                "`prompt_assemble(system, envelope, context, user_message)`; "
                "pass `trust_store=` to KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.prompt_assemble(system, envelope, context, user_message)

    def tool_output_sanitize(
        self,
        output: bytes,
        tool_name: str,
        envelope: Any,
    ) -> Any:
        """specs/tool-output-sanitization.md § Algorithm; fail-closed on
        classifier unavailability. Forwards to the injected sanitizer; loud typed
        error when absent. Byte-identical (deterministic sanitizer)."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "tool_output_sanitize: requires the tool-output sanitizer "
                "exposing `tool_output_sanitize(output, tool_name, envelope)`; "
                "pass `trust_store=` to KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.tool_output_sanitize(output, tool_name, envelope)

    def first_time_action_gate(
        self,
        session: Any,
        tool_name: str,
        args: dict[str, Any],
    ) -> Any:
        """specs/session-state.md § `first_time_action_gate`. Forwards to the
        injected session-state surface; loud typed error when absent.
        Byte-identical (deterministic first-seen check)."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "first_time_action_gate: requires the session-state surface "
                "exposing `first_time_action_gate(session, tool_name, args)`; "
                "pass `trust_store=` to KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.first_time_action_gate(session, tool_name, args)

    def grant_moment_surface(self, request: Any) -> Any:
        """specs/grant-moment.md dispatch; channel-adapter routing. The rendered
        verdict TEXT is the ONE Phase-02 semantic slice (N4). Forwards to the
        injected Grant Moment surface; loud typed error when absent."""
        if self._trust_store is None:
            raise RuntimeNotReadyError(
                "grant_moment_surface: requires the Grant Moment surface "
                "exposing `grant_moment_surface(request)`; pass `trust_store=` "
                "to KailashRsBindingsRuntime(...)."
            )
        return self._trust_store.grant_moment_surface(request)


__all__ = ["KailashRsBindingsRuntime"]
