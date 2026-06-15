# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2: S3t attestation wiring — startup emission (moment 1) + export population.

Real durable `EnvoyLedger` over the `InMemoryKeyringBackend` headless seam.
Covers the two attestation moments not exercised by the switch tests:

- **Moment 1 (startup):** a `KailashPyRuntime` constructed WITH a ledger emits a
  `RuntimeAttestation` entry at `startup()`; one constructed without a ledger
  does not (forwarding-only).
- **Export population:** a durable ledger opened with `runtime_attestation`
  surfaces it in the export bundle's `head_commitment.runtime_attestation`
  (replacing the Phase-01 `{}`), preserving the receipt-hash invariant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from envoy.ledger.bootstrap import (
    LEDGER_ALGORITHM_IDENTIFIER,
    LEDGER_DEVICE_ID,
    LEDGER_SIGNING_KEY_ID,
    open_durable_ledger,
)
from envoy.ledger.export import compute_receipt_hash
from envoy.ledger.keystore import (
    InMemoryKeyringBackend,
    load_or_create_ledger_key_manager,
)
from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.runtime_attestation import (
    RUNTIME_ATTESTATION_ENTRY_TYPE,
    attestation_for_runtime,
)

_PID = "s3t-wiring-principal"


async def _key_manager() -> Any:
    return await load_or_create_ledger_key_manager(
        principal_id=_PID,
        signing_key_id=LEDGER_SIGNING_KEY_ID,
        keyring_backend=InMemoryKeyringBackend(),
    )


async def _open(vault_path: Path, key_manager: Any, **extra: Any) -> Any:
    return await open_durable_ledger(
        vault_path=vault_path,
        key_manager=key_manager,
        signing_key_id=LEDGER_SIGNING_KEY_ID,
        device_id=LEDGER_DEVICE_ID,
        algorithm_identifier=LEDGER_ALGORITHM_IDENTIFIER,
        **extra,
    )


async def _attestation_entries(durable: Any) -> list[Any]:
    return await durable.ledger.query(
        filter={"event_type": RUNTIME_ATTESTATION_ENTRY_TYPE},
        since=datetime(2000, 1, 1, tzinfo=timezone.utc),
        until=datetime(2100, 1, 1, tzinfo=timezone.utc),
    )


# --------------------------------------------------------------------------
# Moment 1 — startup() emits a RuntimeAttestation entry when a ledger is wired
# --------------------------------------------------------------------------


async def test_startup_emits_attestation_when_ledger_wired(tmp_path: Path) -> None:
    km = await _key_manager()
    durable = await _open(tmp_path / "v.db", km)
    try:
        runtime = KailashPyRuntime(envoy_ledger=durable.ledger)
        await runtime.startup(None)
        entries = await _attestation_entries(durable)
        assert len(entries) == 1
        ident = entries[0].content["runtime_identity"]
        assert ident["runtime_family"] == "kailash-py"
        assert ident["binary_hash"].startswith("sha256:")
        assert entries[0].content["signed_by"] == "runtime_device_key"
    finally:
        await durable.aclose()


async def test_startup_without_ledger_emits_nothing(tmp_path: Path) -> None:
    # A forwarding-only adapter (no ledger) starts up without writing anything.
    km = await _key_manager()
    durable = await _open(tmp_path / "v.db", km)
    try:
        runtime = KailashPyRuntime()  # no envoy_ledger
        await runtime.startup(None)
        assert await _attestation_entries(durable) == []
    finally:
        await durable.aclose()


# --------------------------------------------------------------------------
# Export population — head_commitment.runtime_attestation is no longer {}
# --------------------------------------------------------------------------


async def test_export_carries_populated_runtime_attestation(tmp_path: Path) -> None:
    km = await _key_manager()
    runtime_attestation = attestation_for_runtime(KailashPyRuntime())
    durable = await _open(
        tmp_path / "v.db", km, runtime_attestation=runtime_attestation
    )
    try:
        await durable.ledger.append(entry_type="action", content={"i": 0})
        bundle = await durable.ledger.export()
        # The bundle field + the wire-shape head_commitment section are populated.
        assert bundle.runtime_attestation == runtime_attestation
        head = bundle.to_dict()["head_commitment"]
        assert head["runtime_attestation"] != {}
        assert head["runtime_attestation"]["runtime_identity"]["binary_hash"].startswith(
            "sha256:"
        )
        # Receipt-hash invariant still holds (the populated attestation is
        # covered by the canonical view the receipt commits to).
        recomputed = compute_receipt_hash(bundle.to_dict_minus_receipt())
        assert recomputed == bundle.receipt_hash
    finally:
        await durable.aclose()


async def test_export_default_attestation_is_empty(tmp_path: Path) -> None:
    # A ledger opened WITHOUT runtime context preserves the {} default.
    km = await _key_manager()
    durable = await _open(tmp_path / "v.db", km)
    try:
        await durable.ledger.append(entry_type="action", content={"i": 0})
        bundle = await durable.ledger.export()
        assert bundle.to_dict()["head_commitment"]["runtime_attestation"] == {}
    finally:
        await durable.aclose()
