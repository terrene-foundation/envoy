# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/tier1/test_kailash_rs_bindings_shape_parity.py — S2a sync/async parity.

Tier 1 (offline, deterministic, <1s). Proves the Phase-02 S2a wiring of
`KailashRsBindingsRuntime`
(`workspaces/phase-02-distribution/todos/active/01-m1-ws1-runtime-pluggability.md`
§ S2a):

1. Every `async def` Protocol method on the rs adapter is genuinely awaitable
   (its `def`/`async def` keyword matches the Protocol) — and awaiting it does
   NOT surface a coroutine-wrapping-coroutine. Every sync Protocol method
   executes synchronously (calling it returns a value / raises directly, never a
   coroutine object).
2. Structural `isinstance(adapter, KailashRuntime)` is explicitly NOT treated as
   a completion signal (`zero-tolerance.md` Rule 3d): the harness gates
   completion, NOT structural typing. This file asserts the shape contract and
   the real device-key signature, never "isinstance succeeded → done".
3. `runtime_sign` returns `bytes` (the `-> bytes` Protocol contract) for the
   software device-key path, and `runtime_verify` round-trips that signature —
   a REAL Ed25519 signature over real bytes via the kailash binding, NOT a
   placeholder.

The rs adapter construction is feature-flag gated (`RS_BINDINGS_ENABLED`). S2a
wires the bodies but does NOT flip the flag (the flip is the LAST step of the
WS-1 critical path). This test flips the module-level flag via monkeypatch so
the wired bodies are reachable, exercising the S2a deliverable directly while
leaving the production default (False) untouched.
"""

from __future__ import annotations

import inspect

import pytest

from envoy.runtime.adapters import kailash_rs_bindings as rs_mod
from envoy.runtime.adapters.kailash_rs_bindings import KailashRsBindingsRuntime
from envoy.runtime.errors import RuntimeNotReadyError
from envoy.runtime.protocol import KailashRuntime

# Methods whose Protocol declaration is `async def` (spec § Lifecycle + § Ledger).
ASYNC_METHODS: tuple[str, ...] = (
    "startup",
    "shutdown",
    "ledger_append",
    "ledger_query",
    "ledger_verify_chain",
    "head_commitment",
)

# The 13 substrate-gated methods (ENVOY-P2-W2G-002): their backing engine ships
# in a later shard (S5o / S6a / S6c), so each raises RuntimeNotReadyError
# UNCONDITIONALLY (regardless of whether trust_store= is injected), naming the
# gating shard in the message. Genuinely-wired methods (trust_sign,
# envelope_intersect, runtime_sign/verify, envelope_canonical_form, ledger_*,
# budget_*, trust_verify_chain, trust_cascade_revoke) are NOT in this set.
SUBSTRATE_GATED_METHODS: tuple[str, ...] = (
    "envelope_check",
    "envelope_re_read_checkpoint",
    "trust_verify_subset_proof",
    "phase_a_sign_intent",
    "phase_b_sign_outcome",
    "phase_a_orphan_resolve",
    "classifier_invoke",
    "ensemble_aggregate",
    "classifier_registry_resolve",
    "prompt_assemble",
    "tool_output_sanitize",
    "first_time_action_gate",
    "grant_moment_surface",
)

# The set of shard tokens any substrate-gated message is allowed to name. The
# W2G-002 contract is "the message names a gating shard" — assert membership,
# not a single hardcoded value, so a shard re-assignment does not falsely fail.
_VALID_SHARD_TOKENS: frozenset[str] = frozenset({"S5o", "S6a", "S6c"})


# Methods whose Protocol declaration is sync `def`.
SYNC_METHODS: tuple[str, ...] = (
    "runtime_identity",
    "trust_sign",
    "trust_verify_chain",
    "trust_cascade_revoke",
    "trust_verify_subset_proof",
    "envelope_canonical_form",
    "envelope_intersect",
    "envelope_check",
    "envelope_re_read_checkpoint",
    "phase_a_sign_intent",
    "phase_b_sign_outcome",
    "phase_a_orphan_resolve",
    "classifier_invoke",
    "ensemble_aggregate",
    "classifier_registry_resolve",
    "budget_reserve",
    "budget_record",
    "budget_snapshot",
    "budget_velocity_check",
    "runtime_sign",
    "runtime_verify",
    "prompt_assemble",
    "tool_output_sanitize",
    "first_time_action_gate",
    "grant_moment_surface",
)


@pytest.fixture
def rs_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flip the rs-bindings feature flag for the duration of one test.

    The adapter reads the module-level `RS_BINDINGS_ENABLED` name imported into
    `kailash_rs_bindings`, so patching THAT name reaches the constructor guard.
    The production default (False) is restored at teardown — S2a wires bodies
    but does not flip the flag.
    """
    monkeypatch.setattr(rs_mod, "RS_BINDINGS_ENABLED", True)


@pytest.fixture
def device_keypair() -> tuple[str, str]:
    """A real Ed25519 keypair from the kailash binding (priv_hex, pub_hex)."""
    from kailash.trust.signing import generate_keypair

    return generate_keypair()


@pytest.fixture
def adapter(rs_enabled: None, device_keypair: tuple[str, str]) -> KailashRsBindingsRuntime:
    """A wired rs adapter with real device-key material, no other substrate.

    Trust-store / ledger / budget dependencies are intentionally absent so the
    parity test proves the sync/async SHAPE without fabricating substrate — the
    forwarding methods raise the typed `RuntimeNotReadyError` (named dependency)
    when called, which is itself a shape proof: a sync method raises directly, an
    async method raises only when awaited.
    """
    priv_hex, pub_hex = device_keypair
    return KailashRsBindingsRuntime(
        device_signing_private_key_hex=priv_hex,
        device_signing_public_key_hex=pub_hex,
    )


# ---------------------------------------------------------------------------
# 1. Construction gating — flag must be flipped to reach the wired bodies.
# ---------------------------------------------------------------------------


def test_construction_requires_flag_flip() -> None:
    """Without the flag flip the constructor refuses (S2a does NOT flip it)."""
    from envoy.runtime.errors import RsBindingsNotAvailableInPhase01Error

    with pytest.raises(RsBindingsNotAvailableInPhase01Error):
        KailashRsBindingsRuntime()


def test_flag_default_is_false() -> None:
    """The production default stays False: wiring precedes flag-flip."""
    from envoy.runtime.feature_flags import RS_BINDINGS_ENABLED

    assert RS_BINDINGS_ENABLED is False


# ---------------------------------------------------------------------------
# 2. Sync/async shape parity — adapter keyword matches Protocol keyword.
# ---------------------------------------------------------------------------


def test_async_methods_match_protocol_shape(adapter: KailashRsBindingsRuntime) -> None:
    """Every ASYNC_METHODS entry is `async def` on BOTH Protocol and adapter."""
    for name in ASYNC_METHODS:
        proto_fn = getattr(KailashRuntime, name)
        adapter_fn = getattr(type(adapter), name)
        assert inspect.iscoroutinefunction(proto_fn), f"{name} not async on Protocol"
        assert inspect.iscoroutinefunction(adapter_fn), f"{name} not async on adapter"


def test_sync_methods_match_protocol_shape(adapter: KailashRsBindingsRuntime) -> None:
    """Every SYNC_METHODS entry is sync `def` on BOTH Protocol and adapter."""
    for name in SYNC_METHODS:
        proto_fn = getattr(KailashRuntime, name)
        adapter_fn = getattr(type(adapter), name)
        assert not inspect.iscoroutinefunction(proto_fn), f"{name} is async on Protocol"
        assert not inspect.iscoroutinefunction(adapter_fn), f"{name} is async on adapter"


def test_method_inventory_covers_every_protocol_method(
    adapter: KailashRsBindingsRuntime,
) -> None:
    """ASYNC_METHODS + SYNC_METHODS together enumerate EVERY Protocol method —
    no method is silently un-asserted (mechanical completeness sweep)."""
    proto_methods = {
        n
        for n, _ in inspect.getmembers(KailashRuntime, predicate=inspect.isfunction)
        if not n.startswith("_")
    }
    asserted = set(ASYNC_METHODS) | set(SYNC_METHODS)
    assert asserted == proto_methods, (
        "shape-parity inventory drifted from the Protocol: "
        f"missing={proto_methods - asserted}, extra={asserted - proto_methods}"
    )


# ---------------------------------------------------------------------------
# 3. Await every async method; call every sync method — no shape mismatch.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ASYNC_METHODS)
async def test_async_method_is_genuinely_awaitable(
    adapter: KailashRsBindingsRuntime, name: str
) -> None:
    """Calling an async method returns a coroutine; awaiting it runs the body.

    For `startup`/`shutdown` the body completes (no substrate dependency). For
    the ledger methods (no `envoy_ledger` injected) the body raises
    `RuntimeNotReadyError` — but ONLY when awaited. The coroutine returned by the
    call is NOT itself a coroutine-wrapping-coroutine (awaiting once reaches the
    body), which is the exact structural failure mode S2a must avoid.
    """
    method = getattr(adapter, name)
    coro = (
        method(config=None)
        if name == "startup"
        else (
            method(entry={})
            if name == "ledger_append"
            else (
                method(filter=None)
                if name == "ledger_query"
                else method(from_=0, to=0) if name == "ledger_verify_chain" else method()
            )
        )
    )
    assert inspect.iscoroutine(coro), f"{name} did not return a coroutine"
    if name in ("startup", "shutdown"):
        # Bodies complete: await returns None, NOT another coroutine.
        result = await coro
        assert result is None
        assert not inspect.iscoroutine(result), f"{name} double-wrapped a coroutine"
    else:
        # Ledger methods need an EnvoyLedger; awaiting surfaces the typed error.
        with pytest.raises(RuntimeNotReadyError):
            await coro


@pytest.mark.parametrize("name", SYNC_METHODS)
def test_sync_method_executes_without_await(adapter: KailashRsBindingsRuntime, name: str) -> None:
    """Calling a sync method returns a value / raises directly — NEVER a coroutine.

    A sync method that accidentally became `async def` would return a coroutine
    object here (no exception, no value) — the structural mask
    `zero-tolerance.md` Rule 3d warns about. This asserts the method body runs
    synchronously: `runtime_identity` returns a dict; the device-key methods run
    real crypto; the substrate-forwarding methods raise `RuntimeNotReadyError`
    directly (proving they are sync).
    """
    method = getattr(adapter, name)
    if name == "runtime_identity":
        result = method()
        assert not inspect.iscoroutine(result)
        assert result["runtime_family"] == "kailash-rs-bindings"
        return
    if name in (
        "runtime_sign",
        "runtime_verify",
        "trust_sign",
        "envelope_canonical_form",
        "envelope_intersect",
    ):
        # Non-substrate-gated forwards (real primitive / binding) + device-key
        # crypto — they do NOT raise RuntimeNotReadyError, so the generic
        # substrate-error path below does not apply. Each is exercised by a
        # dedicated direct-call test by name:
        #   runtime_sign / runtime_verify → test_runtime_sign_returns_real_bytes,
        #       test_runtime_sign_verify_round_trip, test_runtime_sign_without_key_raises
        #   trust_sign → test_trust_sign_round_trip_and_py_byte_identity
        #   envelope_canonical_form → test_envelope_canonical_form_forwards_to_primitive
        #   envelope_intersect → test_envelope_intersect_forwards_loud_on_shape_mismatch
        # The shape parity for these is already proven by
        # test_sync_methods_match_protocol_shape.
        return
    # Substrate-forwarding sync methods raise the typed error synchronously
    # (no coroutine returned) when their backing dependency is absent.
    args = _benign_args(name)
    with pytest.raises(RuntimeNotReadyError):
        result = method(**args)
        assert not inspect.iscoroutine(result), f"{name} returned a coroutine (async leak)"


def _benign_args(name: str) -> dict[str, object]:
    """Minimal kwargs to invoke each substrate-forwarding sync method."""
    table: dict[str, dict[str, object]] = {
        "trust_verify_chain": {"record": object()},
        "trust_cascade_revoke": {"root_id": "agent-0"},
        "trust_verify_subset_proof": {"parent": object(), "sub": object()},
        "envelope_check": {"envelope": object(), "action": object()},
        "envelope_re_read_checkpoint": {"envelope": object(), "depth": 1},
        "phase_a_sign_intent": {"intent": object()},
        "phase_b_sign_outcome": {"outcome": object(), "intent_id": "i-0"},
        "phase_a_orphan_resolve": {"intent_id": "i-0", "resolution": object()},
        "classifier_invoke": {"ref": "r", "content": b"", "ctx": object()},
        "ensemble_aggregate": {"verdicts": [], "policy": object()},
        "classifier_registry_resolve": {"registry_id": "reg-0"},
        "budget_reserve": {"session": object(), "cost": 1},
        "budget_record": {"reservation": object(), "actual": 1},
        "budget_snapshot": {"session": object()},
        "budget_velocity_check": {"session": object()},
        "prompt_assemble": {
            "system": object(),
            "envelope": object(),
            "context": object(),
            "user_message": "hi",
        },
        "tool_output_sanitize": {
            "output": b"",
            "tool_name": "t",
            "envelope": object(),
        },
        "first_time_action_gate": {
            "session": object(),
            "tool_name": "t",
            "args": {},
        },
        "grant_moment_surface": {"request": object()},
    }
    # envelope_canonical_form + envelope_intersect are NOT substrate-gated:
    # they forward to a real primitive / binding. Excluded from this table so
    # the dedicated tests below cover them.
    return table[name]


# ---------------------------------------------------------------------------
# 4. Real device-key signing — runtime_sign returns bytes; round-trip verifies.
# ---------------------------------------------------------------------------


def test_runtime_sign_returns_real_bytes(
    adapter: KailashRsBindingsRuntime,
) -> None:
    """`runtime_sign(payload)` returns `bytes` (the `-> bytes` contract) — a REAL
    Ed25519 signature over the payload, not a placeholder."""
    payload = b"envoy-rs-runtime-device-key-payload"
    sig = adapter.runtime_sign(payload)
    assert isinstance(sig, bytes), "runtime_sign MUST return bytes"
    assert not inspect.iscoroutine(sig)
    assert len(sig) > 0
    # Real signature: re-signing the same payload is deterministic for Ed25519.
    assert adapter.runtime_sign(payload) == sig


def test_runtime_sign_verify_round_trip(
    adapter: KailashRsBindingsRuntime, device_keypair: tuple[str, str]
) -> None:
    """The signature `runtime_sign` produces verifies via `runtime_verify` with
    the device-bound public key — a real crypto round-trip, both halves sync."""
    _priv_hex, pub_hex = device_keypair
    payload = b"round-trip-payload"
    sig = adapter.runtime_sign(payload)
    ok = adapter.runtime_verify(payload, sig, pub_hex.encode("ascii"))
    assert ok is True
    # A tampered payload MUST fail verification (real crypto, not a stub).
    assert adapter.runtime_verify(b"tampered", sig, pub_hex.encode("ascii")) is False


def test_runtime_sign_without_key_raises(rs_enabled: None) -> None:
    """No device key + no hardware signer → loud typed error, never an empty or
    placeholder signature."""
    no_key = KailashRsBindingsRuntime()
    with pytest.raises(RuntimeNotReadyError):
        no_key.runtime_sign(b"payload")


def test_hardware_device_signer_routes_signing(rs_enabled: None) -> None:
    """When a hardware signer (Secure Enclave / TPM stand-in) is injected, signing
    routes to it and its raw bytes are returned — the rs adapter OWNS the
    device-key surface (attestation). This is a deterministic Protocol-satisfying
    signer, NOT a mock of crypto (`rules/testing.md` § Protocol Adapters)."""

    class _DeviceSigner:
        """Deterministic device-bound signer satisfying the signer protocol."""

        def sign(self, payload: bytes) -> bytes:
            import hashlib

            return hashlib.sha256(b"device-key::" + payload).digest()

        def verify(self, payload: bytes, sig: bytes, pubkey: bytes) -> bool:
            import hashlib

            return sig == hashlib.sha256(b"device-key::" + payload).digest()

    rt = KailashRsBindingsRuntime(
        device_signer=_DeviceSigner(),
        device_attestation_type="secure_enclave",
    )
    payload = b"enclave-signed"
    sig = rt.runtime_sign(payload)
    assert isinstance(sig, bytes)
    assert rt.runtime_verify(payload, sig, b"") is True
    assert rt.runtime_verify(b"other", sig, b"") is False


def test_invalid_attestation_type_rejected(rs_enabled: None) -> None:
    """`device_attestation_type` is validated against the closed allowlist."""
    with pytest.raises(ValueError, match="device_attestation_type"):
        KailashRsBindingsRuntime(device_attestation_type="not-a-real-backend")


# ---------------------------------------------------------------------------
# 5. Non-substrate-gated forwards run real code (envelope_canonical_form).
# ---------------------------------------------------------------------------


def test_envelope_canonical_form_forwards_to_primitive(
    adapter: KailashRsBindingsRuntime,
) -> None:
    """`envelope_canonical_form` forwards to the SAME envoy primitive as
    kailash_py, so the two runtimes' canonical bytes are byte-identical by
    construction. Returns `bytes` synchronously."""
    from envoy.runtime.adapters.kailash_py import KailashPyRuntime

    envelope = {"schema": "envelope/1.0", "dims": {"data_access": "public"}}
    rs_bytes = adapter.envelope_canonical_form(envelope)
    py_bytes = KailashPyRuntime().envelope_canonical_form(envelope)
    assert isinstance(rs_bytes, bytes)
    assert not inspect.iscoroutine(rs_bytes)
    # Cross-runtime byte-identity (E1): both forward to envoy.envelope.canonical.
    assert rs_bytes == py_bytes


# ---------------------------------------------------------------------------
# 6. isinstance is NOT a completion signal (zero-tolerance Rule 3d).
# ---------------------------------------------------------------------------


def test_isinstance_is_not_treated_as_completion(
    adapter: KailashRsBindingsRuntime,
) -> None:
    """`isinstance(adapter, KailashRuntime)` succeeds structurally, but this test
    does NOT treat that as 'done' — completion is gated by the conformance
    harness (byte-identity), not structural typing. This asserts the structural
    fact AND that a wired method actually executes (real bytes), so the two are
    never conflated."""
    assert isinstance(adapter, KailashRuntime)
    # Structural typing is necessary but NOT sufficient: prove a real method runs.
    sig = adapter.runtime_sign(b"x")
    assert isinstance(sig, bytes) and len(sig) > 0


# ---------------------------------------------------------------------------
# 7. Substrate-gated methods raise typed not-ready, naming a shard —
#    UNCONDITIONALLY, even when the documented trust_store= DI is injected
#    (ENVOY-P2-W2G-002). The pre-fix bug forwarded to self._trust_store.<name>,
#    a surface no shipped class provides: with trust_store=None it raised
#    RuntimeNotReadyError, but with the documented DI it raised an OPAQUE
#    AttributeError from a phantom attribute. These tests pin that every gated
#    method raises the typed, shard-naming error regardless of DI.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SUBSTRATE_GATED_METHODS)
def test_substrate_gated_method_raises_typed_not_ready_with_shard(
    adapter: KailashRsBindingsRuntime, name: str
) -> None:
    """Each substrate-gated method raises `RuntimeNotReadyError` and the message
    names the gating engine-shard (S5o / S6a / S6c) so the gap is discoverable.

    `adapter` has NO trust_store injected. The message MUST name BOTH the method
    and a valid shard token so a future `grep` enumerates the unwired surface.
    """
    method = getattr(adapter, name)
    with pytest.raises(RuntimeNotReadyError) as exc_info:
        method(**_benign_args(name))
    msg = str(exc_info.value)
    assert name in msg, f"{name}: error message does not name the method ({msg!r})"
    assert any(shard in msg for shard in _VALID_SHARD_TOKENS), (
        f"{name}: error message names no gating shard {sorted(_VALID_SHARD_TOKENS)} "
        f"({msg!r})"
    )


@pytest.mark.parametrize("name", SUBSTRATE_GATED_METHODS)
def test_substrate_gated_method_raises_even_with_trust_store_injected(
    rs_enabled: None, device_keypair: tuple[str, str], name: str
) -> None:
    """The fix's load-bearing invariant: a gated method raises the SAME typed
    `RuntimeNotReadyError` even when the documented `trust_store=` DI is supplied.

    Pre-fix, injecting a real backing object that LACKS the phantom method
    surfaced an untyped `AttributeError` (`'X' object has no attribute
    'envelope_check'`). The deterministic stand-in below exposes NONE of the 13
    gated names, so the pre-fix code would raise AttributeError; the fixed code
    raises RuntimeNotReadyError UNCONDITIONALLY (it never forwards).

    The stand-in is a deterministic Protocol-shaped object, NOT a mock of a
    behavior under test — it exists only to prove the gated methods never touch
    it (`rules/testing.md` § Protocol Adapters).
    """

    class _TrustStoreWithoutGatedSurface:
        """A trust-store stand-in exposing only the genuinely-wired surface
        (get_chain / revoke / check). It deliberately exposes NONE of the 13
        substrate-gated method names, so any attempt to forward to it would
        raise AttributeError — which the fix MUST NOT do."""

        def get_chain(self, record: object) -> object:  # pragma: no cover - never called
            raise AssertionError("gated method forwarded to trust_store.get_chain")

    priv_hex, pub_hex = device_keypair
    adapter = KailashRsBindingsRuntime(
        device_signing_private_key_hex=priv_hex,
        device_signing_public_key_hex=pub_hex,
        trust_store=_TrustStoreWithoutGatedSurface(),
    )
    method = getattr(adapter, name)
    with pytest.raises(RuntimeNotReadyError):
        method(**_benign_args(name))


# ---------------------------------------------------------------------------
# 8. Genuinely-wired sync forwards get DIRECT-CALL tests (ENVOY-P2-W2G-006).
#    The generic loop skips trust_sign/envelope_intersect with "exercised in
#    dedicated tests below" — these ARE those dedicated tests.
# ---------------------------------------------------------------------------


def test_trust_sign_round_trip_and_py_byte_identity(
    adapter: KailashRsBindingsRuntime, device_keypair: tuple[str, str]
) -> None:
    """`trust_sign(record, key)` returns a REAL Ed25519 signature (bytes), it
    verifies via `kailash.trust.signing.verify_signature`, AND it is byte-equal
    to the kailash_py adapter's `trust_sign` for the SAME record+key.

    The byte-equality is the E2 cross-runtime byte-identity invariant: both
    adapters forward to the SAME `kailash.trust.signing.sign`, so the signatures
    MUST be identical bytes. A drift here would mean the rs adapter is NOT
    forwarding to the real binding (a stub / re-implementation)."""
    from kailash.trust.signing import verify_signature

    from envoy.runtime.adapters.kailash_py import KailashPyRuntime

    priv_hex, pub_hex = device_keypair
    record = "envoy-rs-trust-sign-record"

    rs_sig = adapter.trust_sign(record, priv_hex)
    assert isinstance(rs_sig, bytes), "trust_sign MUST return bytes"
    assert not inspect.iscoroutine(rs_sig)

    # The signature verifies against the real kailash binding (hex round-trip).
    assert verify_signature(record, rs_sig.decode("ascii"), pub_hex) is True
    assert verify_signature("tampered", rs_sig.decode("ascii"), pub_hex) is False

    # E2 byte-identity: rs and py forward to the SAME sign() → identical bytes.
    py_sig = KailashPyRuntime().trust_sign(record, priv_hex)
    assert rs_sig == py_sig, "rs trust_sign drifted from py trust_sign (E2 byte-identity)"


def test_envelope_intersect_forwards_loud_on_shape_mismatch(
    adapter: KailashRsBindingsRuntime,
) -> None:
    """`envelope_intersect` is GENUINELY wired (forwards to
    `kailash.trust.pact.envelopes.intersect_envelopes`), so a wrong-shaped input
    surfaces the kailash binding's loud error — NEVER a silent fallback — and the
    rs adapter behaves IDENTICALLY to the kailash_py adapter at that boundary.

    Per the rs adapter boundary discipline + `rules/zero-tolerance.md` Rule 3:
    callers wire the kailash-shaped ConstraintEnvelopeConfig conversion; an
    envoy-shaped dict that the binding does not accept raises loudly. This proves
    the method is a real forward (not a stub) AND the rs/py boundary behavior is
    the same class of loud failure — without depending on the exact kailash
    ConstraintEnvelopeConfig constructor (which lives in the binding)."""
    from envoy.runtime.adapters.kailash_py import KailashPyRuntime

    # An envoy-shaped dict pair — NOT a kailash ConstraintEnvelopeConfig. The
    # binding rejects it loudly (TypeError / AttributeError / ValueError class),
    # never returning a silent empty/None intersection.
    bad_a = {"schema": "envelope/1.0", "dims": {"data_access": "public"}}
    bad_b = {"schema": "envelope/1.0", "dims": {"data_access": "internal"}}

    with pytest.raises(Exception) as rs_exc:  # noqa: PT011 - binding error class varies
        adapter.envelope_intersect(bad_a, bad_b)
    # NOT a RuntimeNotReadyError: envelope_intersect is wired, so the error comes
    # from the real binding's shape rejection, not the substrate-gated path.
    assert not isinstance(rs_exc.value, RuntimeNotReadyError), (
        "envelope_intersect is genuinely wired — a wrong shape MUST surface the "
        "binding's loud error, not the substrate-not-ready error"
    )

    # The py adapter forwards to the SAME binding; it MUST raise the SAME error
    # type on the SAME bad input (boundary-behavior parity, never a silent fork).
    with pytest.raises(type(rs_exc.value)):
        KailashPyRuntime().envelope_intersect(bad_a, bad_b)
