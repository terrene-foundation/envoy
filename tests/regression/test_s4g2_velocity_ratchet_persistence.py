# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: S4g-2 — durable + skew-immune velocity-raise cooling-off ratchet.

Contract pin: T-093 R2-H4 velocity-raise ratchet, Phase-02 hardening
(`specs/grant-moment.md` § Velocity-raise ratchet).

Phase-01 kept the last-approved timestamp in an in-memory dict, so a process
restart SILENTLY RESET the ratchet (a restart bought a free velocity raise) and a
forward wall-clock jump could shorten the 24h window. S4g-2 persists the record
in the session store with a monotonic baseline + per-process boot id:

1. **Durable across restart** — a fresh runtime+router over the same store still
   sees the ratchet (the in-memory dict would have reset).
2. **Forward-wall-clock-skew immune (same boot)** — when the persisted record was
   stamped by the live process, the monotonic delta is authoritative; a wall-clock
   that claims 25h elapsed cannot shorten a window monotonic says is ~0.
3. **Cross-boot wall-clock fallback** — across a restart (monotonic not
   comparable) the check falls back to the wall-clock delta; the ratchet survives,
   accepting that cross-restart forward skew is the documented narrower residual.

Tier-2: real on-disk SessionRouter store + real `cryptography`/keychain backend
(`InMemoryKeyringBackend` is the headless seam, not a mock).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from envoy.grant_moment import ApproveResolution, VelocityRaiseCoolingOffError
from envoy.grant_moment.runtime import _PROCESS_BOOT_ID
from envoy.ledger.keystore import InMemoryKeyringBackend
from envoy.runtime.session import SessionRouter
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_issue_kwargs,
    make_runtime,
)

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]

_DAY = 24 * 60 * 60


async def _open_router(vault_path: Path, backend: InMemoryKeyringBackend) -> SessionRouter:
    router = SessionRouter(
        vault_path=vault_path, principal_id=DEFAULT_PRINCIPAL_ID, keyring_backend=backend
    )
    await router.open()
    return router


def _vr_kwargs() -> dict:
    return make_issue_kwargs(
        is_velocity_raise=True, why_asking="velocity_raise", tool_name="raise_limit"
    )


async def _approve_velocity_raise(runtime) -> None:
    """Drive a full velocity-raise approval through the router-backed runtime so
    the ratchet record is persisted via the real `record_velocity_approval`."""
    req = await runtime.issue_grant_moment(**_vr_kwargs())
    runtime.post_decision(
        req.request_id,
        ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
    )
    resolution = await runtime.await_decision(req.request_id, timeout_seconds=5)
    outcome = await runtime.submit_resolution(
        request_id=req.request_id, resolution=resolution, decided_on_channel_id="cli"
    )
    assert outcome.state == "APPROVED"


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "ratchet.vault"


@pytest.fixture
def backend() -> InMemoryKeyringBackend:
    return InMemoryKeyringBackend()


class TestDurableAcrossRestart:
    async def test_ratchet_survives_a_fresh_runtime_over_the_same_store(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """Approve a velocity-raise via runtime1, then a FRESH runtime2+router2
        over the SAME store still blocks the next raise — the persisted ratchet
        survived (the Phase-01 in-memory dict would have reset to empty)."""
        router1 = await _open_router(vault_path, backend)
        try:
            runtime1, *_ = await make_runtime(
                session_router=router1, velocity_raise_cooling_off_seconds=_DAY
            )
            await _approve_velocity_raise(runtime1)
        finally:
            await router1.close()

        # "Restart": fresh router + runtime over the same on-disk store.
        router2 = await _open_router(vault_path, backend)
        try:
            runtime2, *_ = await make_runtime(
                session_router=router2, velocity_raise_cooling_off_seconds=_DAY
            )
            with pytest.raises(VelocityRaiseCoolingOffError) as exc:
                await runtime2.issue_grant_moment(**_vr_kwargs())
            assert exc.value.required_seconds == _DAY
        finally:
            await router2.close()

    async def test_no_router_falls_back_to_in_memory_ratchet(self) -> None:
        """With NO router wired (Tier-1 / legacy), the in-memory fallback still
        enforces the cooling-off within the process (Phase-01 behavior intact)."""
        runtime, *_ = await make_runtime(velocity_raise_cooling_off_seconds=_DAY)
        await _approve_velocity_raise(runtime)
        with pytest.raises(VelocityRaiseCoolingOffError):
            await runtime.issue_grant_moment(**_vr_kwargs())


class TestForwardSkewImmuneSameBoot:
    async def test_forward_wallclock_jump_cannot_shorten_window_same_boot(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """Craft a same-boot record whose WALL-CLOCK claims 25h elapsed but whose
        MONOTONIC baseline is ~now: the check uses the monotonic delta (~0) and
        STILL blocks — a forward wall-clock jump cannot shorten the window."""
        router = await _open_router(vault_path, backend)
        try:
            await router.record_velocity_approval(
                principal_id=DEFAULT_PRINCIPAL_ID,
                wallclock=time.time() - 25 * 60 * 60,  # wall says 25h ago (> 24h window)
                monotonic=time.monotonic(),  # but monotonic says ~now
                boot_id=_PROCESS_BOOT_ID,  # SAME boot → monotonic authoritative
            )
            runtime, *_ = await make_runtime(
                session_router=router, velocity_raise_cooling_off_seconds=_DAY
            )
            with pytest.raises(VelocityRaiseCoolingOffError) as exc:
                await runtime.issue_grant_moment(**_vr_kwargs())
            # Elapsed measured by monotonic (~0), NOT the 25h wall-clock skew.
            assert exc.value.elapsed_seconds < _DAY
        finally:
            await router.close()


class TestCrossBootWallclockFallback:
    async def test_cross_boot_uses_wallclock_and_allows_after_window(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """A record from a DIFFERENT boot (monotonic not comparable) falls back to
        the wall-clock delta: 25h wall-clock ago + a different boot_id → the window
        has genuinely elapsed → the next raise is ALLOWED."""
        router = await _open_router(vault_path, backend)
        try:
            await router.record_velocity_approval(
                principal_id=DEFAULT_PRINCIPAL_ID,
                wallclock=time.time() - 25 * 60 * 60,
                monotonic=12345.0,  # stale monotonic from a prior boot — ignored
                boot_id="boot-from-a-prior-process",  # DIFFERENT boot → wall-clock path
            )
            runtime, *_ = await make_runtime(
                session_router=router, velocity_raise_cooling_off_seconds=_DAY
            )
            # No error — wall-clock says the 24h window elapsed.
            req = await runtime.issue_grant_moment(**_vr_kwargs())
            assert req.request_id
        finally:
            await router.close()

    async def test_cross_boot_within_window_still_blocks(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """Cross-boot but the wall-clock window has NOT elapsed (~now) → still
        blocks — the restart did not reset the ratchet (the Phase-01 hole)."""
        router = await _open_router(vault_path, backend)
        try:
            await router.record_velocity_approval(
                principal_id=DEFAULT_PRINCIPAL_ID,
                wallclock=time.time(),  # just now
                monotonic=999.0,  # stale prior-boot monotonic
                boot_id="boot-from-a-prior-process",
            )
            runtime, *_ = await make_runtime(
                session_router=router, velocity_raise_cooling_off_seconds=_DAY
            )
            with pytest.raises(VelocityRaiseCoolingOffError):
                await runtime.issue_grant_moment(**_vr_kwargs())
        finally:
            await router.close()
