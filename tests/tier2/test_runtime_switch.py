# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2: S3p Wire — the `envoy runtime switch` state machine over real infra.

Real `TrustVault` (cold-unlock gate), real durable `EnvoyLedger` (the signed
`runtime_switch` entry), real ledger key manager over the `InMemoryKeyringBackend`
headless seam (NOT a mock — real Ed25519). Covers the Wire-gate acceptance of
`01-m1-ws1-runtime-pluggability.md` § S3p:

- `switch` runs the state machine in order and writes a Genesis-signed
  `runtime_switch` Ledger entry, then flips the durable runtime-choice default.
- A warm-only vault session refuses the switch (cold unlock required); a warm
  vault does NOT let a wrong passphrase through (re-seal-then-unlock).
- The `runtime_switch` entry is written ONLY after target attestation succeeds
  (attestation-before-record): an attestation failure writes no record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from envoy.ledger.bootstrap import (
    LEDGER_ALGORITHM_IDENTIFIER,
    LEDGER_DEVICE_ID,
    LEDGER_SIGNING_KEY_ID,
    open_durable_ledger,
)
from envoy.ledger.keystore import (
    InMemoryKeyringBackend,
    load_or_create_ledger_key_manager,
    principal_genesis_id,
)
from envoy.runtime.runtime_attestation import RUNTIME_ATTESTATION_ENTRY_TYPE
from envoy.runtime.runtime_picker import read_runtime_choice
from envoy.runtime.runtime_switch import (
    RUNTIME_SWITCH_ENTRY_TYPE,
    RuntimeAttestation,
    RuntimeSwitchAttestationError,
    WarmVaultSwitchRefusedError,
    perform_runtime_switch,
)
from envoy.trust.vault import TrustVault, VaultUnlockFailedError

_PRINCIPAL_ID = "s3p-switch-principal"
_GENESIS_ID = principal_genesis_id(_PRINCIPAL_ID)
_PASSPHRASE = "correct horse battery staple"


@dataclass
class _Stack:
    vault: TrustVault
    durable: Any
    key_manager: Any


async def _build_stack(tmp_path: Path) -> _Stack:
    vault_path = tmp_path / "trust_vault.db"
    vault = TrustVault(vault_path, idle_ttl_seconds=900)
    await vault.create(b"envoy-genesis-install", _PASSPHRASE)  # sealed after create
    key_manager = await load_or_create_ledger_key_manager(
        principal_id=_PRINCIPAL_ID,
        signing_key_id=LEDGER_SIGNING_KEY_ID,
        keyring_backend=InMemoryKeyringBackend(),
    )
    durable = await open_durable_ledger(
        vault_path=vault_path,
        key_manager=key_manager,
        signing_key_id=LEDGER_SIGNING_KEY_ID,
        device_id=LEDGER_DEVICE_ID,
        algorithm_identifier=LEDGER_ALGORITHM_IDENTIFIER,
    )
    return _Stack(vault=vault, durable=durable, key_manager=key_manager)


async def _runtime_switch_entries(durable: Any) -> list[Any]:
    """Query the ledger for `runtime_switch` entries (works on an empty ledger,
    unlike `export()` which refuses an empty chain)."""
    return await durable.ledger.query(
        filter={"event_type": RUNTIME_SWITCH_ENTRY_TYPE},
        since=datetime(2000, 1, 1, tzinfo=timezone.utc),
        until=datetime(2100, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def choice_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "runtime-choice.json"
    monkeypatch.setenv("ENVOY_RUNTIME_CHOICE_PATH", str(target))
    return target


async def _switch(
    stack: _Stack, *, target: str, current: str, passphrase: str, attest: Any = None
) -> Any:
    kwargs: dict[str, Any] = {
        "target_family": target,
        "current_family": current,
        "vault": stack.vault,
        "passphrase": passphrase,
        "ledger": stack.durable.ledger,
        "key_manager": stack.key_manager,
        "signing_key_id": LEDGER_SIGNING_KEY_ID,
        "genesis_id": _GENESIS_ID,
    }
    if attest is not None:
        kwargs["attest"] = attest
    return await perform_runtime_switch(**kwargs)


# --------------------------------------------------------------------------
# Happy path — signed entry + config flip + chain verifies
# --------------------------------------------------------------------------


async def test_switch_writes_signed_entry_and_flips_config(
    tmp_path: Path, choice_path: Path
) -> None:
    stack = await _build_stack(tmp_path)
    try:
        result = await _switch(
            stack, target="kailash-py", current="kailash-py", passphrase=_PASSPHRASE
        )
        # A runtime_switch entry landed with the Spec-gap-4 schema.
        entries = await _runtime_switch_entries(stack.durable)
        assert len(entries) == 1
        content = entries[0].content
        assert content["from_family"] == "kailash-py"
        assert content["to_family"] == "kailash-py"
        assert content["target_attestation_hash"].startswith("sha256:")
        assert content["signed_by"] == "runtime_device_key"
        assert "re_read_checkpoint_result" in content
        assert content["target_attestation_hash"] == result.target_attestation_hash
        assert (
            content["runtime_attestation_entry_id"]
            == result.runtime_attestation_entry_id
        )

        # Moment 2: a RuntimeAttestation entry was emitted BEFORE the switch
        # record (attestation-before-record), pinning the target's real binary
        # hash; its sequence precedes the runtime_switch entry's sequence.
        attest_entries = await stack.durable.ledger.query(
            filter={"event_type": RUNTIME_ATTESTATION_ENTRY_TYPE},
            since=datetime(2000, 1, 1, tzinfo=timezone.utc),
            until=datetime(2100, 1, 1, tzinfo=timezone.utc),
        )
        assert len(attest_entries) == 1
        assert attest_entries[0].content["runtime_identity"]["binary_hash"].startswith(
            "sha256:"
        )
        assert attest_entries[0].sequence < entries[0].sequence

        # The chain still verifies (the entries are Ed25519-signed by the device key).
        report = await stack.durable.ledger.verify_chain()
        assert report.entries_verified >= 2

        # The durable default flipped to the attested target.
        choice = read_runtime_choice()
        assert choice is not None
        assert choice.runtime_family == "kailash-py"
    finally:
        await stack.durable.aclose()
        if stack.vault.is_unlocked:
            await stack.vault.lock()


async def test_switch_records_re_read_checkpoint_on_algorithm_change(
    tmp_path: Path, choice_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # rs-bindings is the only family with a distinct algorithm identifier here;
    # flipping to it requires the conformance flag on (the config-flip step
    # refuses an unavailable runtime otherwise).
    from envoy.runtime import feature_flags

    monkeypatch.setattr(feature_flags, "RS_BINDINGS_ENABLED", True)

    # Inject an attestation seam returning DIFFERENT algorithm identifiers for
    # the two families so the T-015 checkpoint records invalidated=True.
    def attest(family: str) -> RuntimeAttestation:
        algo = (
            {"sig": "ed25519", "rev": "1"}
            if family == "kailash-py"
            else {"sig": "ed25519", "rev": "2"}
        )
        return RuntimeAttestation(
            runtime_family=family,
            attestation_hash=f"sha256:fake-{family}",
            algorithm_identifier=algo,
            runtime_identity={
                "runtime_family": family,
                "version": "test-runtime/0.1",
                "binary_hash": f"sha256:fake-{family}",
                "device_bound_pubkey_hex": None,
                "algorithm_identifier": algo,
            },
        )

    stack = await _build_stack(tmp_path)
    try:
        result = await _switch(
            stack,
            target="kailash-rs-bindings",
            current="kailash-py",
            passphrase=_PASSPHRASE,
            attest=attest,
        )
        rr = result.re_read_checkpoint_result
        assert rr["invalidated"] is True
        assert rr["from_algorithm_identifier"] == {"sig": "ed25519", "rev": "1"}
        assert rr["to_algorithm_identifier"] == {"sig": "ed25519", "rev": "2"}
        # The transition is pinned into the signed ledger entry.
        entries = await _runtime_switch_entries(stack.durable)
        assert entries[0].content["re_read_checkpoint_result"]["invalidated"] is True
    finally:
        await stack.durable.aclose()
        if stack.vault.is_unlocked:
            await stack.vault.lock()


# --------------------------------------------------------------------------
# Cold-unlock gate
# --------------------------------------------------------------------------


async def test_warm_only_vault_refuses_switch(
    tmp_path: Path, choice_path: Path
) -> None:
    stack = await _build_stack(tmp_path)
    try:
        # No passphrase supplied (a warm session is not sufficient).
        with pytest.raises(WarmVaultSwitchRefusedError):
            await _switch(
                stack, target="kailash-py", current="kailash-py", passphrase=""
            )
        # No record written, default not flipped.
        assert await _runtime_switch_entries(stack.durable) == []
        assert read_runtime_choice() is None
    finally:
        await stack.durable.aclose()
        if stack.vault.is_unlocked:
            await stack.vault.lock()


async def test_warm_vault_does_not_bypass_wrong_passphrase(
    tmp_path: Path, choice_path: Path
) -> None:
    stack = await _build_stack(tmp_path)
    try:
        # Warm the vault with the correct passphrase first.
        await stack.vault.unlock(_PASSPHRASE)
        assert stack.vault.is_unlocked
        # A switch with the WRONG passphrase must still fail — the state machine
        # re-seals the warm vault then performs a real cold unlock.
        with pytest.raises(VaultUnlockFailedError):
            await _switch(
                stack,
                target="kailash-py",
                current="kailash-py",
                passphrase="wrong-passphrase",
            )
        assert await _runtime_switch_entries(stack.durable) == []
    finally:
        await stack.durable.aclose()
        if stack.vault.is_unlocked:
            await stack.vault.lock()


# --------------------------------------------------------------------------
# Attestation-before-record
# --------------------------------------------------------------------------


async def test_attestation_failure_writes_no_record(
    tmp_path: Path, choice_path: Path
) -> None:
    def failing_attest(family: str) -> RuntimeAttestation:
        raise RuntimeSwitchAttestationError(
            f"binary_hash for {family} does not match manifest (simulated T-060)"
        )

    stack = await _build_stack(tmp_path)
    try:
        with pytest.raises(RuntimeSwitchAttestationError):
            await _switch(
                stack,
                target="kailash-py",
                current="kailash-py",
                passphrase=_PASSPHRASE,
                attest=failing_attest,
            )
        # Attestation-before-record: NO runtime_switch entry, default NOT flipped.
        assert await _runtime_switch_entries(stack.durable) == []
        assert read_runtime_choice() is None
    finally:
        await stack.durable.aclose()
        if stack.vault.is_unlocked:
            await stack.vault.lock()


async def test_unknown_target_family_rejected(
    tmp_path: Path, choice_path: Path
) -> None:
    stack = await _build_stack(tmp_path)
    try:
        with pytest.raises(ValueError, match="not in"):
            await _switch(
                stack,
                target="kailash-julia",
                current="kailash-py",
                passphrase=_PASSPHRASE,
            )
        assert await _runtime_switch_entries(stack.durable) == []
    finally:
        await stack.durable.aclose()
        if stack.vault.is_unlocked:
            await stack.vault.lock()
