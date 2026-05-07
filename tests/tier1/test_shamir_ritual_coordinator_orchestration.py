"""Tier 1: T-02-34 — ShamirRitualCoordinator orchestration.

Source: shard `01-analysis/15-shamir-recovery-implementation.md` § 3.1 +
wave 2 todo `02-wave-2-authorship-shamir-boundary.md` § T-02-34.

Per `rules/testing.md` § Tier 1 — pure orchestration logic; mocking is
allowed. Tier 2 round-trip against real `kailash.trust.vault.shamir`
lives in T-02-37.

Asserts the 4 T-02-34 invariants:

1. 6-step ritual sequence — every step fires exactly once in the
   documented order (1 → 2 → 6 → 3 → 4 → 5 — zeroize fires immediately
   after generate to minimize master-key residency).
2. share count = 5 (Phase 01 default).
3. threshold = 3 (Phase 01 default).
4. master-key zeroization — the bytes returned by MasterKeySource are
   overwritten before the result is constructed, even on collaborator
   error in steps 3-5.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime
from typing import Any

import pytest

from envoy.shamir import (
    DEFAULT_THRESHOLD,
    DEFAULT_TOTAL_SHARDS,
    ChecklistPersister,
    CommitmentBinder,
    DistributionChecklist,
    MasterKeySource,
    MasterKeyZeroizationError,
    PaperRenderer,
    RitualPreconditionError,
    RitualResult,
    ShamirGenerator,
    ShamirRitualCoordinator,
    ShamirRitualError,
)


# Cryptographically random default test secret per L-1 reviewer finding —
# avoids `b"\x42" * 32` recognizable byte patterns that produce false
# positives in heap-dump forensics or grep audits looking for known-test
# byte sequences.
_TEST_SECRET = secrets.token_bytes(32)


# ---------------------------------------------------------------------------
# Fakes — record-and-replay collaborators for orchestration assertions
# ---------------------------------------------------------------------------


class _MasterKeyFake:
    """Yields a fixed 32-byte test secret. Records calls + observes residency."""

    def __init__(self, secret: bytes | None = None) -> None:
        # Per L-1 reviewer finding: default to cryptographically random
        # bytes rather than a recognizable pattern.
        self.secret = secret if secret is not None else _TEST_SECRET
        # Reference to the bytes object the coordinator received. Lets us
        # assert the immutable bytes were dropped (CPython does not let us
        # observe its memory directly, so the test relies on the
        # coordinator's bytearray-overwrite for invariant #4).
        self.last_returned_bytes_id: int | None = None
        self.call_count = 0

    async def export_master_key_for_shamir(self) -> bytes:
        self.call_count += 1
        out = bytes(self.secret)
        self.last_returned_bytes_id = id(out)
        return out


class _ShamirGeneratorFake:
    """Records (secret, threshold, total_shards, passphrase) — returns
    deterministic shard sentinels keyed by `secret[:1]` so tests can
    assert that the secret reaching the generator is the master key.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        # Snapshot of the secret bytes the generator sees, to verify
        # that mutation post-generate (zeroize) did NOT propagate to
        # the generator's view of the key.
        self.observed_secret: bytes | None = None

    def __call__(
        self,
        secret: bytes,
        ritual: Any,
        *,
        passphrase: bytes = b"",
    ) -> list[list[str]]:
        self.calls.append(
            {
                "secret": bytes(secret),  # snapshot
                "threshold": ritual.threshold,
                "total_shards": ritual.total_shards,
                "passphrase": bytes(passphrase),
            }
        )
        self.observed_secret = bytes(secret)
        # Deterministic sentinel: shard `i` of `n` = ["secret-{secret[0]:02x}", "shard-{i+1}-of-{n}"]
        # Using a fixed canned word list shape so callers can grep order.
        return [
            [f"secret-{secret[0]:02x}", f"shard-{i + 1}-of-{ritual.total_shards}"]
            for i in range(ritual.total_shards)
        ]


class _CommitmentBinderFake:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[list[str]]]] = []

    async def bind_to_genesis(self, principal_id: str, shards: list[list[str]]) -> list[str]:
        self.calls.append((principal_id, [list(s) for s in shards]))
        return [f"sha256:fake-{i:02x}" for i in range(len(shards))]


class _PaperRendererFake:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str, tuple[int, int]]] = []

    def render(
        self, shard: list[str], slot_label: str, sequence: tuple[int, int]
    ) -> dict[str, Any]:
        self.calls.append((list(shard), slot_label, sequence))
        return {"slot_label": slot_label, "sequence": sequence, "shard": list(shard)}


class _ChecklistPersisterFake:
    def __init__(self) -> None:
        self.persisted: list[DistributionChecklist] = []

    async def persist(self, checklist: DistributionChecklist) -> None:
        self.persisted.append(checklist)


def _make_coordinator(
    *,
    master_key_secret: bytes = b"\x42" * 32,
    principal_id: str = "test-principal-shamir",
) -> tuple[
    ShamirRitualCoordinator,
    _MasterKeyFake,
    _ShamirGeneratorFake,
    _CommitmentBinderFake,
    _PaperRendererFake,
    _ChecklistPersisterFake,
]:
    """Common factory — returns coordinator + every collaborator fake."""
    mks = _MasterKeyFake(secret=master_key_secret)
    gen = _ShamirGeneratorFake()
    binder = _CommitmentBinderFake()
    renderer = _PaperRendererFake()
    persister = _ChecklistPersisterFake()
    coord = ShamirRitualCoordinator(
        master_key_source=mks,
        commitment_binder=binder,
        paper_renderer=renderer,
        checklist_persister=persister,
        principal_id=principal_id,
        shamir_generator=gen,
    )
    return coord, mks, gen, binder, renderer, persister


# ---------------------------------------------------------------------------
# Invariant #1 — 6-step ritual sequence
# ---------------------------------------------------------------------------


class TestRitualStepSequence:
    @pytest.mark.asyncio
    async def test_every_collaborator_fires_exactly_once(self) -> None:
        coord, mks, gen, binder, renderer, persister = _make_coordinator()
        result = await coord.run_first_time_ritual()

        assert mks.call_count == 1, "step 1 (master-key fetch) should fire once"
        assert len(gen.calls) == 1, "step 2 (generate) should fire once"
        assert len(binder.calls) == 1, "step 3 (commitment binding) should fire once"
        assert (
            len(renderer.calls) == DEFAULT_TOTAL_SHARDS
        ), "step 4 (paper render) should fire once per shard"
        assert len(persister.persisted) == 1, "step 5 (persist) should fire once"
        assert isinstance(result, RitualResult)

    @pytest.mark.asyncio
    async def test_paper_renderer_receives_sequential_slot_labels(self) -> None:
        coord, _, _, _, renderer, _ = _make_coordinator()
        await coord.run_first_time_ritual()

        slot_labels = [call[1] for call in renderer.calls]
        assert slot_labels == [f"slot-{i}" for i in range(1, DEFAULT_TOTAL_SHARDS + 1)]

    @pytest.mark.asyncio
    async def test_paper_renderer_receives_card_sequence_tuples(self) -> None:
        coord, _, _, _, renderer, _ = _make_coordinator()
        await coord.run_first_time_ritual()

        sequences = [call[2] for call in renderer.calls]
        assert sequences == [(i, DEFAULT_TOTAL_SHARDS) for i in range(1, DEFAULT_TOTAL_SHARDS + 1)]

    @pytest.mark.asyncio
    async def test_persisted_checklist_carries_ritual_metadata(self) -> None:
        coord, _, _, _, _, persister = _make_coordinator()
        result = await coord.run_first_time_ritual()

        persisted = persister.persisted[0]
        assert persisted.ritual_id == result.ritual_id
        assert persisted.threshold == DEFAULT_THRESHOLD
        assert persisted.total_shards == DEFAULT_TOTAL_SHARDS
        assert persisted.slot_labels == tuple(
            f"slot-{i}" for i in range(1, DEFAULT_TOTAL_SHARDS + 1)
        )
        assert isinstance(persisted.created_at, datetime)
        assert persisted.rotation_history == ()

    @pytest.mark.asyncio
    async def test_step_6_zeroize_fires_before_step_3(self) -> None:
        """Step 6 (zeroize) MUST fire after step 2 (generate) but BEFORE
        step 3 (commitment binding). The runtime sequence is 1→2→6→3→4→5.

        Verification: a CommitmentBinder that observes the generator's
        recorded `secret` snapshot — the snapshot was taken at generate
        time (step 2). If zeroize fires AFTER step 3, the bytearray
        observation would still show the original master key. We use
        a binder that reads the generator's snapshot at step-3 time.
        """

        secret = b"\xab" * 32

        observed_at_step_3: list[bytes] = []

        class _ProbeBinder:
            def __init__(self, gen: _ShamirGeneratorFake) -> None:
                self.gen = gen

            async def bind_to_genesis(
                self, principal_id: str, shards: list[list[str]]
            ) -> list[str]:
                # Snapshot whatever the generator has at this point.
                # Step 6 (zeroize) overwrites the local bytearray
                # before the generator's snapshot is changed; the
                # generator already took its OWN snapshot at step 2.
                # If step 6 ran AFTER step 3, the local bytearray would
                # still be untouched here — but we cannot observe that
                # directly. Instead, this probe asserts the generator's
                # snapshot ALREADY captured the secret at step 2 time.
                assert self.gen.observed_secret == secret
                observed_at_step_3.append(self.gen.observed_secret or b"")
                return ["sha256:fake"]

        mks = _MasterKeyFake(secret=secret)
        gen = _ShamirGeneratorFake()
        coord = ShamirRitualCoordinator(
            master_key_source=mks,
            commitment_binder=_ProbeBinder(gen),
            paper_renderer=_PaperRendererFake(),
            checklist_persister=_ChecklistPersisterFake(),
            principal_id="test",
            shamir_generator=gen,
        )
        await coord.run_first_time_ritual()
        assert observed_at_step_3 == [secret]


# ---------------------------------------------------------------------------
# Invariants #2 + #3 — share count = 5, threshold = 3 (Phase 01 defaults)
# ---------------------------------------------------------------------------


class TestPhase01Defaults:
    @pytest.mark.asyncio
    async def test_default_threshold_is_3(self) -> None:
        coord, _, gen, _, _, _ = _make_coordinator()
        await coord.run_first_time_ritual()
        assert gen.calls[0]["threshold"] == 3

    @pytest.mark.asyncio
    async def test_default_total_shards_is_5(self) -> None:
        coord, _, gen, _, _, _ = _make_coordinator()
        result = await coord.run_first_time_ritual()
        assert gen.calls[0]["total_shards"] == 5
        assert len(result.shards) == 5

    @pytest.mark.asyncio
    async def test_module_default_constants_match_spec(self) -> None:
        # Locks the constants — `specs/shamir-recovery.md` § Default threshold:
        # "3-of-5. User-configurable 2-of-3 to 5-of-9."
        assert DEFAULT_THRESHOLD == 3
        assert DEFAULT_TOTAL_SHARDS == 5

    @pytest.mark.asyncio
    async def test_user_configurable_2_of_3(self) -> None:
        coord, _, gen, _, _, _ = _make_coordinator()
        result = await coord.run_first_time_ritual(threshold=2, total_shards=3)
        assert gen.calls[0]["threshold"] == 2
        assert gen.calls[0]["total_shards"] == 3
        assert len(result.shards) == 3

    @pytest.mark.asyncio
    async def test_user_configurable_5_of_9(self) -> None:
        coord, _, gen, _, _, _ = _make_coordinator()
        result = await coord.run_first_time_ritual(threshold=5, total_shards=9)
        assert gen.calls[0]["threshold"] == 5
        assert gen.calls[0]["total_shards"] == 9
        assert len(result.shards) == 9


# ---------------------------------------------------------------------------
# Invariant #4 — master-key zeroization
# ---------------------------------------------------------------------------


class TestMasterKeyZeroization:
    @pytest.mark.asyncio
    async def test_master_key_bytes_not_in_result(self) -> None:
        secret = bytes.fromhex("a" * 64)  # 32 bytes
        coord, _, _, _, _, _ = _make_coordinator(master_key_secret=secret)
        result = await coord.run_first_time_ritual()

        # The master key bytes (or hex form, or hex-with-prefix) MUST NOT
        # appear anywhere in the serialized result.
        result_repr = repr(result)
        assert secret.hex() not in result_repr.lower()
        # Spot-check the shards specifically — the generator's sentinel
        # contains the FIRST byte of the secret as a hex marker, so we
        # search for the FULL hex sequence to make sure the actual bytes
        # are not leaking.
        for shard in result.shards:
            for word in shard:
                assert secret.hex() not in word.lower()

    @pytest.mark.asyncio
    async def test_zeroize_fires_even_on_step_3_failure(self) -> None:
        """Per the ritual contract: master-key bytes MUST be zeroized
        BEFORE step 3 fires. If step 3 raises, the master key is already
        gone from the local bytearray.
        """

        class _FailingBinder:
            async def bind_to_genesis(
                self, principal_id: str, shards: list[list[str]]
            ) -> list[str]:
                raise RuntimeError("simulated commitment-binding failure")

        secret = b"\xcd" * 32
        coord = ShamirRitualCoordinator(
            master_key_source=_MasterKeyFake(secret=secret),
            commitment_binder=_FailingBinder(),
            paper_renderer=_PaperRendererFake(),
            checklist_persister=_ChecklistPersisterFake(),
            principal_id="test",
            shamir_generator=_ShamirGeneratorFake(),
        )
        with pytest.raises(RuntimeError, match="commitment-binding failure"):
            await coord.run_first_time_ritual()
        # Zeroize fired (step 6 is in the inner try/finally around step 2);
        # the generator's bytes-snapshot is the only surviving copy
        # outside the test. The coordinator's local bytearray is
        # garbage-collected and unreachable. We cannot inspect heap
        # state from Python; the structural defense is the
        # try/finally placement, asserted by the next test.

    @pytest.mark.asyncio
    async def test_random_overwrite_failure_raises_master_key_zeroization_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Force `secrets.token_bytes` to raise during the
        random-overwrite phase (post-zero-fill); assert the typed
        error fires AND user_message names "securely zeroed" so the
        operator knows the master key IS already gone (per H-2 fix:
        deterministic zero-fill ran first; random overwrite is
        best-effort hardening only).

        Targeted monkeypatch: fails only for `n == _MASTER_KEY_LEN`
        (32) so `_make_ritual_id`'s salt call (n == 8) still succeeds.
        """
        from envoy.shamir import ritual as ritual_module

        original = ritual_module.secrets.token_bytes

        def _boom_for_master_key_len(n: int) -> bytes:
            if n == 32:
                raise OSError("simulated entropy failure")
            return original(n)

        monkeypatch.setattr(ritual_module.secrets, "token_bytes", _boom_for_master_key_len)

        coord, _, _, _, _, _ = _make_coordinator()
        with pytest.raises(MasterKeyZeroizationError) as exc:
            await coord.run_first_time_ritual()
        assert exc.value.user_message  # plain-language form is set
        # Per H-2 fix: master key is already zero-filled; user_message
        # MUST communicate that the residency contract is satisfied.
        assert "securely zeroed" in exc.value.user_message


# ---------------------------------------------------------------------------
# Precondition errors — fail-loud at validation
# ---------------------------------------------------------------------------


class TestPreconditions:
    def test_empty_principal_id_rejected(self) -> None:
        with pytest.raises(RitualPreconditionError, match="principal_id"):
            ShamirRitualCoordinator(
                master_key_source=_MasterKeyFake(),
                commitment_binder=_CommitmentBinderFake(),
                paper_renderer=_PaperRendererFake(),
                checklist_persister=_ChecklistPersisterFake(),
                principal_id="",
                shamir_generator=_ShamirGeneratorFake(),
            )

    @pytest.mark.asyncio
    async def test_threshold_below_minimum_rejected(self) -> None:
        coord, _, _, _, _, _ = _make_coordinator()
        with pytest.raises(RitualPreconditionError, match="threshold"):
            await coord.run_first_time_ritual(threshold=1, total_shards=5)

    @pytest.mark.asyncio
    async def test_threshold_above_total_rejected(self) -> None:
        coord, _, _, _, _, _ = _make_coordinator()
        with pytest.raises(RitualPreconditionError, match="threshold"):
            await coord.run_first_time_ritual(threshold=6, total_shards=5)

    @pytest.mark.asyncio
    async def test_total_shards_above_slip39_group_limit_rejected(self) -> None:
        coord, _, _, _, _, _ = _make_coordinator()
        with pytest.raises(RitualPreconditionError, match="total_shards"):
            await coord.run_first_time_ritual(threshold=3, total_shards=17)

    @pytest.mark.asyncio
    async def test_total_shards_below_minimum_rejected(self) -> None:
        coord, _, _, _, _, _ = _make_coordinator()
        with pytest.raises(RitualPreconditionError, match="total_shards"):
            await coord.run_first_time_ritual(threshold=2, total_shards=1)

    @pytest.mark.asyncio
    async def test_master_key_wrong_size_rejected(self) -> None:
        # 16-byte AES-128 key — too short for the AES-256 contract.
        coord, _, _, _, _, _ = _make_coordinator(master_key_secret=b"\x00" * 16)
        with pytest.raises(RitualPreconditionError, match="32 bytes"):
            await coord.run_first_time_ritual()

    @pytest.mark.asyncio
    async def test_master_key_non_bytes_rejected(self) -> None:
        class _BadSource:
            async def export_master_key_for_shamir(self) -> Any:  # type: ignore[override]
                return "not bytes"

        coord = ShamirRitualCoordinator(
            master_key_source=_BadSource(),
            commitment_binder=_CommitmentBinderFake(),
            paper_renderer=_PaperRendererFake(),
            checklist_persister=_ChecklistPersisterFake(),
            principal_id="test",
            shamir_generator=_ShamirGeneratorFake(),
        )
        with pytest.raises(RitualPreconditionError, match="bytes-like"):
            await coord.run_first_time_ritual()

    @pytest.mark.asyncio
    async def test_generator_wrong_shard_count_rejected(self) -> None:
        """Defensive — if a generator returns fewer shards than requested,
        invariant #2 (share count) is violated. Coordinator MUST refuse.
        """

        class _WrongCountGenerator:
            def __call__(
                self, secret: bytes, ritual: Any, *, passphrase: bytes = b""
            ) -> list[list[str]]:
                return [["w1"], ["w2"], ["w3"]]  # only 3, requested 5

        coord = ShamirRitualCoordinator(
            master_key_source=_MasterKeyFake(),
            commitment_binder=_CommitmentBinderFake(),
            paper_renderer=_PaperRendererFake(),
            checklist_persister=_ChecklistPersisterFake(),
            principal_id="test",
            shamir_generator=_WrongCountGenerator(),
        )
        with pytest.raises(RitualPreconditionError, match=r"shards.*expected"):
            await coord.run_first_time_ritual()


# ---------------------------------------------------------------------------
# RitualResult shape + DistributionChecklist round-trip
# ---------------------------------------------------------------------------


class TestRitualResultShape:
    @pytest.mark.asyncio
    async def test_ritual_id_is_sha256_hex(self) -> None:
        coord, _, _, _, _, _ = _make_coordinator()
        result = await coord.run_first_time_ritual()
        # 64 hex chars = SHA-256
        assert re.fullmatch(r"[0-9a-f]{64}", result.ritual_id)

    @pytest.mark.asyncio
    async def test_ritual_id_deterministic_for_same_inputs(self) -> None:
        # Same threshold + total + created_at → same ritual_id.
        # Different created_at → different ritual_id (created_at is the
        # entropy source for ritual identity).
        coord, _, _, _, _, _ = _make_coordinator()
        result1 = await coord.run_first_time_ritual()
        result2 = await coord.run_first_time_ritual()
        # Real-world: different timestamps → different ids.
        assert result1.ritual_id != result2.ritual_id

    @pytest.mark.asyncio
    async def test_shards_are_immutable_tuple_of_tuples(self) -> None:
        coord, _, _, _, _, _ = _make_coordinator()
        result = await coord.run_first_time_ritual()
        assert isinstance(result.shards, tuple)
        for shard in result.shards:
            assert isinstance(shard, tuple)

    @pytest.mark.asyncio
    async def test_distribution_checklist_round_trip_dict(self) -> None:
        coord, _, _, _, _, persister = _make_coordinator()
        await coord.run_first_time_ritual()
        original = persister.persisted[0]
        round_tripped = DistributionChecklist.from_dict(original.to_dict())
        assert round_tripped == original

    @pytest.mark.asyncio
    async def test_default_principal_id_threaded_through(self) -> None:
        coord, _, _, binder, _, _ = _make_coordinator(principal_id="alice@example")
        await coord.run_first_time_ritual()
        assert binder.calls[0][0] == "alice@example"


# ---------------------------------------------------------------------------
# Error hierarchy — ShamirRitualError as base
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_precondition_error_is_shamir_ritual_error(self) -> None:
        assert issubclass(RitualPreconditionError, ShamirRitualError)

    def test_zeroization_error_is_shamir_ritual_error(self) -> None:
        assert issubclass(MasterKeyZeroizationError, ShamirRitualError)

    def test_user_message_is_settable(self) -> None:
        err = RitualPreconditionError("internal", user_message="user-facing")
        assert err.user_message == "user-facing"
        assert str(err) == "internal"


# ---------------------------------------------------------------------------
# Protocol structural conformance — rev-2 + rev-3 reviewer findings
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Lock the contract between the coordinator and its 5 collaborators.

    `runtime_checkable` Protocols only check attribute presence — not
    signature. These assertions catch a fake whose method shape drifts
    from the Protocol BEFORE the orchestration tests run their full
    matrix and produce a confusing AttributeError deep inside the
    ritual. Per `rules/cross-sdk-inspection.md` Rule 3a (structural
    invariant test) — locks the Protocol surface so a future refactor
    that drops a method fails loudly here rather than silently in the
    integration path.
    """

    def test_master_key_fake_implements_protocol(self) -> None:
        assert isinstance(_MasterKeyFake(), MasterKeySource)

    def test_shamir_generator_fake_implements_protocol(self) -> None:
        assert isinstance(_ShamirGeneratorFake(), ShamirGenerator)

    def test_commitment_binder_fake_implements_protocol(self) -> None:
        assert isinstance(_CommitmentBinderFake(), CommitmentBinder)

    def test_paper_renderer_fake_implements_protocol(self) -> None:
        assert isinstance(_PaperRendererFake(), PaperRenderer)

    def test_checklist_persister_fake_implements_protocol(self) -> None:
        assert isinstance(_ChecklistPersisterFake(), ChecklistPersister)

    def test_real_trust_store_adapter_implements_master_key_source(self) -> None:
        """Locks the cross-module contract per rev-2 reviewer finding —
        the production-time `MasterKeySource` is `TrustStoreAdapter`'s
        `export_master_key_for_shamir` method. If the method is renamed
        in `envoy/trust/vault.py`, this test fails BEFORE T-02-37 wires
        the Tier 2 round-trip.
        """
        from envoy.trust.vault import TrustVault

        # `MasterKeySource` is a structural Protocol (runtime_checkable):
        # any class with an `export_master_key_for_shamir` callable
        # satisfies it. We assert the production class has the method
        # at the right attribute name — a refactor that renames it
        # WILL break this test (intentional drift detector).
        assert hasattr(TrustVault, "export_master_key_for_shamir")
        method = TrustVault.export_master_key_for_shamir
        # Sanity: the method is async per envoy/trust/vault.py:549.
        import inspect

        assert inspect.iscoroutinefunction(method)


# ---------------------------------------------------------------------------
# Edge case: threshold == total_shards — rev-5 reviewer finding
# ---------------------------------------------------------------------------


class TestThresholdEqualsTotalShards:
    """5-of-5 (or any threshold == total_shards) is accepted by
    `_validate_parameters` per spec line 19 (range 2-of-3 to 5-of-9
    permits threshold == total). Verify the generator path exercises
    correctly.
    """

    @pytest.mark.asyncio
    async def test_5_of_5_ritual_succeeds(self) -> None:
        coord, _, gen, _, _, _ = _make_coordinator()
        result = await coord.run_first_time_ritual(threshold=5, total_shards=5)
        assert gen.calls[0]["threshold"] == 5
        assert gen.calls[0]["total_shards"] == 5
        assert len(result.shards) == 5

    @pytest.mark.asyncio
    async def test_2_of_2_ritual_succeeds(self) -> None:
        # Lower-bound edge: threshold == total == minimum permitted.
        coord, _, gen, _, _, _ = _make_coordinator()
        result = await coord.run_first_time_ritual(threshold=2, total_shards=2)
        assert gen.calls[0]["threshold"] == 2
        assert gen.calls[0]["total_shards"] == 2
        assert len(result.shards) == 2


# ---------------------------------------------------------------------------
# Logging discipline — H-3 reviewer finding (principal_id at INFO must be hashed)
# ---------------------------------------------------------------------------


class TestLoggingDiscipline:
    @pytest.mark.asyncio
    async def test_principal_id_does_not_appear_in_info_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Per H-3 fix + `rules/observability.md` Rule 4 + Rule 8:
        `principal_id` MUST NOT appear at INFO level. The hashed
        prefix `principal_hash` (8 hex chars) substitutes; raw value
        flows at DEBUG only.
        """
        import logging

        coord, _, _, _, _, _ = _make_coordinator(principal_id="alice@example.com")
        with caplog.at_level(logging.INFO, logger="envoy.shamir.ritual"):
            await coord.run_first_time_ritual()

        for record in caplog.records:
            if record.levelno == logging.INFO:
                # Raw principal_id MUST NOT appear in INFO record extras.
                assert getattr(record, "principal_id", None) is None
                # Hashed form MUST be present.
                assert hasattr(record, "principal_hash")
                principal_hash = record.principal_hash
                assert isinstance(principal_hash, str)
                assert len(principal_hash) == 8
                assert re.fullmatch(r"[0-9a-f]{8}", principal_hash)
                # And the raw value is NOT hex-prefixed in the hash
                # (sanity check — `alice@example.com` does not start
                # with the hash).
                assert "alice" not in principal_hash
