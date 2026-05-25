"""Tier 2 wiring: KailashPyRuntime adapter + get_runtime() factory.

Closes /redteam Round 1 HIGH-1 + HIGH-2 (six-module runtime orphan)
per `rules/orphan-detection.md` Rule 1 (every facade has a production
call site within 5 commits) + Rule 2 (every wired manager has a Tier
2 integration test). This test IS the first in-package consumer of
`envoy.runtime` AND exercises the wired adapter end-to-end against
real infrastructure.

Source authority:
- Spec: `specs/runtime-abstraction.md` § Lifecycle + § Trust Lineage
  + § Ledger + § Runtime device-key signing.
- Shard 18 § 6.1: `tests/integration/test_envoy_runtime_kailash_py_adapter.py`
  + `test_envoy_runtime_get_runtime_returns_kailash_py.py` +
  `test_envoy_runtime_rs_bindings_blocked_in_phase01.py` — this file
  consolidates the three under envoy's `tests/tier2/` convention.

Per `rules/testing.md` Tier 2: NO mocking. Real Ed25519 sign + verify
via `kailash.trust.signing`; real EnvoyLedger over real
InMemoryAuditStore; real KailashPyRuntime adapter.
"""

from __future__ import annotations

import pytest
from kailash.trust.signing import generate_keypair

from envoy.ledger import EnvoyLedger
from envoy.runtime import (
    KailashRuntime,
    Phase02SubstrateNotWiredError,
    RsBindingsNotAvailableInPhase01Error,
    get_runtime,
)
from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.adapters.kailash_rs_bindings import KailashRsBindingsRuntime
from envoy.runtime.feature_flags import RS_BINDINGS_ENABLED


# ---------------------------------------------------------------------------
# Fixtures — real keypair + real adapter + real Ledger
# ---------------------------------------------------------------------------


@pytest.fixture
def device_keypair() -> tuple[str, str]:
    """Real Ed25519 keypair via `kailash.trust.signing.generate_keypair`.

    `(private_hex, public_hex)` — software-fallback path per spec
    § Runtime device key (Secure Enclave / TPM lands at Phase 02 Rust
    bindings)."""
    return generate_keypair()


@pytest.fixture
async def kailash_py_runtime(
    device_keypair: tuple[str, str],
    envoy_ledger: EnvoyLedger,
) -> KailashPyRuntime:
    """Real KailashPyRuntime with device keypair + injected EnvoyLedger.

    Reuses the tier2 conftest `envoy_ledger` fixture (real
    InMemoryAuditStore + real Ed25519 via InMemoryKeyManager). The
    runtime adapter forwards ledger_* methods to this injected ledger.
    """
    priv_hex, pub_hex = device_keypair
    return KailashPyRuntime(
        device_signing_private_key_hex=priv_hex,
        device_signing_public_key_hex=pub_hex,
        envoy_ledger=envoy_ledger,
    )


# ---------------------------------------------------------------------------
# Section 1 — get_runtime() factory + Phase-01 lock per spec § Security
# gates per phase + shard 18 § 3.3 reconciliation
# ---------------------------------------------------------------------------


class TestGetRuntimeReturnsKailashPy:
    """`get_runtime()` factory contract — Phase 01 always KailashPyRuntime."""

    def test_default_returns_kailash_py(self, device_keypair: tuple[str, str]) -> None:
        """Per shard 18 § 3 + selection.py docstring: with no `family`
        argument, `get_runtime` returns a KailashPyRuntime instance."""
        priv_hex, pub_hex = device_keypair
        rt = get_runtime(
            device_signing_private_key_hex=priv_hex,
            device_signing_public_key_hex=pub_hex,
        )
        assert isinstance(rt, KailashPyRuntime)
        # Protocol-runtime_checkable check — the returned object satisfies
        # the abstract interface contract.
        assert isinstance(rt, KailashRuntime)

    def test_explicit_kailash_py_returns_kailash_py(self, device_keypair: tuple[str, str]) -> None:
        priv_hex, pub_hex = device_keypair
        rt = get_runtime(
            "kailash-py",
            device_signing_private_key_hex=priv_hex,
            device_signing_public_key_hex=pub_hex,
        )
        assert isinstance(rt, KailashPyRuntime)


class TestRsBindingsBlockedInPhase01:
    """Per spec § Runtime picker + shard 18 § 3.3: Rs bindings adapter
    construction is feature-flag gated and MUST raise the typed
    RsBindingsNotAvailableInPhase01Error while flag is False."""

    def test_feature_flag_is_false_in_phase_01(self) -> None:
        """The Phase 01 invariant per shard 18 § 3.3 + feature_flags.py."""
        assert RS_BINDINGS_ENABLED is False

    def test_get_runtime_with_rs_family_raises(self) -> None:
        """Factory MUST gate at the entry point — raises typed error
        BEFORE attempting adapter construction."""
        with pytest.raises(RsBindingsNotAvailableInPhase01Error):
            get_runtime("kailash-rs-bindings")

    def test_direct_construction_also_raises(self) -> None:
        """Belt-and-suspenders: even bypassing the factory, the adapter
        constructor re-checks the feature flag per shard 18 § 3.3."""
        with pytest.raises(RsBindingsNotAvailableInPhase01Error):
            KailashRsBindingsRuntime()

    def test_invalid_family_raises_value_error(self) -> None:
        """selection.py:70 raises ValueError on unknown family."""
        with pytest.raises(ValueError):
            get_runtime("unknown-runtime-family")


# ---------------------------------------------------------------------------
# Section 2 — Lifecycle + runtime_identity wired methods per spec § Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycleAndIdentity:
    """Lifecycle (startup/shutdown) + runtime_identity contract."""

    async def test_startup_marks_adapter_started(
        self, kailash_py_runtime: KailashPyRuntime
    ) -> None:
        await kailash_py_runtime.startup(config=None)
        # The internal flag flips per kailash_py.py:117.
        assert kailash_py_runtime._started is True

    async def test_shutdown_marks_adapter_stopped(
        self, kailash_py_runtime: KailashPyRuntime
    ) -> None:
        await kailash_py_runtime.startup(config=None)
        await kailash_py_runtime.shutdown()
        assert kailash_py_runtime._started is False

    def test_runtime_identity_returns_spec_shape(
        self, kailash_py_runtime: KailashPyRuntime, device_keypair: tuple[str, str]
    ) -> None:
        """Per spec § Lifecycle table: `RuntimeIdentity` carries 5 keys."""
        _, pub_hex = device_keypair
        identity = kailash_py_runtime.runtime_identity()
        assert identity["runtime_family"] == "kailash-py"
        assert identity["device_bound_pubkey_hex"] == pub_hex
        assert identity["binary_hash"].startswith("sha256:")
        assert identity["algorithm_identifier"]["sig"] == "ed25519"
        assert identity["algorithm_identifier"]["hash"] == "sha256"
        assert identity["algorithm_identifier"]["shamir"] == "slip39"
        assert "version" in identity


# ---------------------------------------------------------------------------
# Section 3 — Runtime device-key sign/verify ROUND-TRIP through facade
# (per `rules/orphan-detection.md` Rule 2a — crypto-pair via facade)
# ---------------------------------------------------------------------------


class TestRuntimeDeviceKeySignVerifyRoundTrip:
    """Sign → verify round-trip through the adapter facade — closes
    orphan-detection.md Rule 2a (paired crypto via facade)."""

    def test_sign_then_verify_returns_true(
        self,
        kailash_py_runtime: KailashPyRuntime,
        device_keypair: tuple[str, str],
    ) -> None:
        """The canonical round-trip: payload → sign → verify with pubkey."""
        _, pub_hex = device_keypair
        payload = b"envoy-runtime-tier2-round-trip-payload"
        signature = kailash_py_runtime.runtime_sign(payload)
        assert isinstance(signature, bytes)
        verified = kailash_py_runtime.runtime_verify(payload, signature, pub_hex.encode("ascii"))
        assert verified is True

    def test_verify_rejects_tampered_payload(
        self,
        kailash_py_runtime: KailashPyRuntime,
        device_keypair: tuple[str, str],
    ) -> None:
        """Tampered payload → verify returns False (Ed25519 signature
        binding catches the modification)."""
        _, pub_hex = device_keypair
        payload = b"original-payload"
        signature = kailash_py_runtime.runtime_sign(payload)
        tampered = b"tampered-payload"
        verified = kailash_py_runtime.runtime_verify(tampered, signature, pub_hex.encode("ascii"))
        assert verified is False

    def test_sign_without_device_key_raises_typed_error(self, envoy_ledger: EnvoyLedger) -> None:
        """Per kailash_py.py:416-421: missing device_priv_hex raises typed
        Phase02SubstrateNotWiredError, not bare AttributeError."""
        rt = KailashPyRuntime(envoy_ledger=envoy_ledger)
        with pytest.raises(Phase02SubstrateNotWiredError):
            rt.runtime_sign(b"payload")


# ---------------------------------------------------------------------------
# Section 4 — Ledger wired methods through EnvoyLedger (real audit store)
# Closes the Ledger surface per spec § Ledger + shard 18 § 5.2 (the
# `#596 TieredAuditDispatcher` gap is closed via envoy.ledger.EnvoyLedger).
# ---------------------------------------------------------------------------


class TestLedgerWiringThroughAdapter:
    """ledger_append → ledger_verify_chain end-to-end against real
    EnvoyLedger + real InMemoryAuditStore."""

    async def test_append_then_verify_chain_round_trip(
        self, kailash_py_runtime: KailashPyRuntime
    ) -> None:
        """Adapter forwards to EnvoyLedger; the chain MUST verify clean."""
        result = await kailash_py_runtime.ledger_append(
            {
                "entry_type": "runtime_attestation",
                "content": {"action_id": "tier2-runtime-wiring-001", "kind": "test"},
            }
        )
        assert "entry_id" in result
        assert result["entry_id"].startswith("sha256:")

        report = await kailash_py_runtime.ledger_verify_chain(0, 0)
        assert report.success is True
        assert report.entries_verified >= 1

    async def test_append_without_ledger_raises_typed_error(
        self, device_keypair: tuple[str, str]
    ) -> None:
        """Per kailash_py.py:299-304: missing envoy_ledger raises typed
        Phase02SubstrateNotWiredError (NOT bare AttributeError)."""
        priv_hex, pub_hex = device_keypair
        rt = KailashPyRuntime(
            device_signing_private_key_hex=priv_hex,
            device_signing_public_key_hex=pub_hex,
            envoy_ledger=None,
        )
        with pytest.raises(Phase02SubstrateNotWiredError):
            await rt.ledger_append({"entry_type": "x", "content": {}})

    async def test_head_commitment_returns_after_append(
        self, kailash_py_runtime: KailashPyRuntime
    ) -> None:
        """head_commitment per spec § Ledger MUST reflect the latest
        appended entry (monotonic non-decreasing)."""
        await kailash_py_runtime.ledger_append({"entry_type": "test_entry", "content": {"n": 1}})
        head = await kailash_py_runtime.head_commitment()
        assert head is not None


# ---------------------------------------------------------------------------
# Section 5 — Phase02 stub methods raise typed errors (not bare
# NotImplementedError); audit-trail-anchored per spec § Error taxonomy.
# ---------------------------------------------------------------------------


class TestPhase02StubsRaiseTypedErrors:
    """Per shard 18 § 3.2 + `rules/zero-tolerance.md` Rule 2 (no
    bare NotImplementedError on production paths): un-wired methods
    raise typed Phase02SubstrateNotWiredError with substrate-todo hints."""

    def test_prompt_assemble_raises_typed(self, kailash_py_runtime: KailashPyRuntime) -> None:
        with pytest.raises(Phase02SubstrateNotWiredError):
            kailash_py_runtime.prompt_assemble(
                system=None, envelope=None, context=None, user_message="x"
            )

    def test_classifier_invoke_raises_typed(self, kailash_py_runtime: KailashPyRuntime) -> None:
        with pytest.raises(Phase02SubstrateNotWiredError):
            kailash_py_runtime.classifier_invoke("ref", b"content", ctx=None)

    def test_budget_reserve_raises_typed(self, kailash_py_runtime: KailashPyRuntime) -> None:
        with pytest.raises(Phase02SubstrateNotWiredError):
            kailash_py_runtime.budget_reserve(session="s1", cost=100)

    def test_envelope_check_raises_typed(self, kailash_py_runtime: KailashPyRuntime) -> None:
        with pytest.raises(Phase02SubstrateNotWiredError):
            kailash_py_runtime.envelope_check(envelope=None, action=None)
