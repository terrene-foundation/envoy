# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1: S3p Build half — first-run runtime picker + config + resolution.

Covers the Build-gate acceptance of `01-m1-ws1-runtime-pluggability.md` § S3p:

- Picker writes a SIGNED runtime-choice config (`runtime-choice/1.0`).
- `get_runtime(family=None)` resolves the chosen family from that config.
- Presented default is `kailash-rs-bindings` (ADR-0001) when the conformance
  flag is on, else `kailash-py`.
- rs-bindings is refused at write time while the flag is off (fail-loud — the
  picker never persists a runtime `get_runtime` cannot honor).
- Corrupt config raises loud (never a silent fallback); a tampered config
  fails signature verification (fail-closed).

The `InMemoryKeyringBackend` is the headless signing seam (per the repo's
Tier-1 convention — `tests/tier1/test_init_keyring_backend_override.py`), NOT a
mock: real Ed25519 sign/verify runs through the real key manager.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from envoy.ledger.keystore import (
    InMemoryKeyringBackend,
    load_or_create_ledger_key_manager,
    principal_genesis_id,
)
from envoy.runtime import feature_flags
from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.errors import RsBindingsNotAvailableInPhase01Error
from envoy.runtime.runtime_picker import (
    RUNTIME_CHOICE_SCHEMA_VERSION,
    RuntimeChoice,
    RuntimeChoiceCorruptError,
    RuntimeChoiceSignatureError,
    presented_default_family,
    read_runtime_choice,
    resolve_runtime_choice_path,
    verify_runtime_choice,
    write_runtime_choice,
)

_PRINCIPAL_ID = "s3p-test-principal"
_SIGNING_KEY_ID = "envoy-digest-signing-key"
_GENESIS_ID = principal_genesis_id(_PRINCIPAL_ID)


async def _key_manager() -> Any:
    """A real ledger key manager over the in-memory keyring seam."""
    return await load_or_create_ledger_key_manager(
        principal_id=_PRINCIPAL_ID,
        signing_key_id=_SIGNING_KEY_ID,
        keyring_backend=InMemoryKeyringBackend(),
    )


@pytest.fixture
def choice_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the picker config at a tmp path via the env override so no test
    ever touches the operator's real ~/.envoy/runtime-choice.json."""
    target = tmp_path / "runtime-choice.json"
    monkeypatch.setenv("ENVOY_RUNTIME_CHOICE_PATH", str(target))
    return target


# --------------------------------------------------------------------------
# Build gate — write a signed config + resolution + presented default
# --------------------------------------------------------------------------


async def test_write_runtime_choice_writes_signed_config(choice_path: Path) -> None:
    km = await _key_manager()
    choice = write_runtime_choice(
        family="kailash-py",
        genesis_id=_GENESIS_ID,
        key_manager=km,
        signing_key_id=_SIGNING_KEY_ID,
    )
    assert choice_path.exists()
    assert choice.runtime_family == "kailash-py"
    assert choice.chosen_by_genesis_id == _GENESIS_ID
    assert choice.schema_version == RUNTIME_CHOICE_SCHEMA_VERSION
    assert choice.signature_hex  # non-empty

    # The signature verifies against the Genesis public key (real Ed25519).
    pubkey = km.get_public_key(_SIGNING_KEY_ID)
    assert pubkey is not None
    await verify_runtime_choice(choice, key_manager=km, expected_pubkey=pubkey)

    # On-disk wire shape carries exactly the 5 schema fields.
    wire = json.loads(choice_path.read_text())
    assert set(wire) == {
        "schema_version",
        "runtime_family",
        "chosen_at",
        "chosen_by_genesis_id",
        "signature_hex",
    }


async def test_write_does_not_follow_symlink_at_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A pre-planted symlink at the config path MUST NOT redirect the write to an
    # attacker sink — the atomic temp+os.replace defeats the symlink (it is
    # replaced by the real file, not followed). Mirrors the F53 witness-write
    # symlink-defense regression.
    target = tmp_path / "runtime-choice.json"
    sink = tmp_path / "attacker-sink.json"
    sink.write_text("ATTACKER-OWNED — MUST NOT BE OVERWRITTEN\n")
    target.symlink_to(sink)
    monkeypatch.setenv("ENVOY_RUNTIME_CHOICE_PATH", str(target))

    km = await _key_manager()
    write_runtime_choice(
        family="kailash-py",
        genesis_id=_GENESIS_ID,
        key_manager=km,
        signing_key_id=_SIGNING_KEY_ID,
    )
    # The symlink was replaced by a real regular file carrying the choice...
    assert not target.is_symlink()
    assert read_runtime_choice() is not None
    # ...and the attacker sink was never written through.
    assert sink.read_text() == "ATTACKER-OWNED — MUST NOT BE OVERWRITTEN\n"


async def test_written_config_is_0600(choice_path: Path) -> None:
    km = await _key_manager()
    write_runtime_choice(
        family="kailash-py",
        genesis_id=_GENESIS_ID,
        key_manager=km,
        signing_key_id=_SIGNING_KEY_ID,
    )
    mode = stat.S_IMODE(choice_path.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


async def test_read_runtime_choice_roundtrip(choice_path: Path) -> None:
    km = await _key_manager()
    written = write_runtime_choice(
        family="kailash-py",
        genesis_id=_GENESIS_ID,
        key_manager=km,
        signing_key_id=_SIGNING_KEY_ID,
    )
    loaded = read_runtime_choice()
    assert loaded == written


async def test_verify_succeeds_with_fresh_key_manager_over_persistent_backend(
    choice_path: Path,
) -> None:
    # The production OS-keychain scenario: the `switch` process and a later
    # `show` process each build their OWN key manager, but over the SAME
    # persistent backend, so the signing key reloads and the signature verifies.
    backend = InMemoryKeyringBackend()
    km_writer = await load_or_create_ledger_key_manager(
        principal_id=_PRINCIPAL_ID,
        signing_key_id=_SIGNING_KEY_ID,
        keyring_backend=backend,
    )
    choice = write_runtime_choice(
        family="kailash-py",
        genesis_id=_GENESIS_ID,
        key_manager=km_writer,
        signing_key_id=_SIGNING_KEY_ID,
    )
    km_reader = await load_or_create_ledger_key_manager(
        principal_id=_PRINCIPAL_ID,
        signing_key_id=_SIGNING_KEY_ID,
        keyring_backend=backend,
    )
    pubkey = km_reader.get_public_key(_SIGNING_KEY_ID)
    assert pubkey is not None
    # Does not raise — the fresh-manager-over-persistent-backend signature verifies.
    await verify_runtime_choice(choice, key_manager=km_reader, expected_pubkey=pubkey)


async def test_read_runtime_choice_absent_returns_none(choice_path: Path) -> None:
    # choice_path points at a tmp file that does not exist yet.
    assert not choice_path.exists()
    assert read_runtime_choice() is None


def test_get_runtime_no_config_defaults_kailash_py(choice_path: Path) -> None:
    from envoy.runtime.selection import get_runtime

    runtime = get_runtime()
    assert isinstance(runtime, KailashPyRuntime)


async def test_get_runtime_resolves_kailash_py_from_config(choice_path: Path) -> None:
    from envoy.runtime.selection import get_runtime

    km = await _key_manager()
    write_runtime_choice(
        family="kailash-py",
        genesis_id=_GENESIS_ID,
        key_manager=km,
        signing_key_id=_SIGNING_KEY_ID,
    )
    runtime = get_runtime()  # family=None → resolves from config
    assert isinstance(runtime, KailashPyRuntime)


async def test_resolve_selected_family_reads_config(
    choice_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With the flag flipped on, the picker may persist rs-bindings; the resolver
    # then reports that family (adapter construction is a separate concern).
    monkeypatch.setattr(feature_flags, "RS_BINDINGS_ENABLED", True)
    from envoy.runtime import selection

    km = await _key_manager()
    write_runtime_choice(
        family="kailash-rs-bindings",
        genesis_id=_GENESIS_ID,
        key_manager=km,
        signing_key_id=_SIGNING_KEY_ID,
    )
    assert selection._resolve_selected_family() == "kailash-rs-bindings"


def test_presented_default_family_flag_aware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(feature_flags, "RS_BINDINGS_ENABLED", False)
    assert presented_default_family() == "kailash-py"
    monkeypatch.setattr(feature_flags, "RS_BINDINGS_ENABLED", True)
    assert presented_default_family() == "kailash-rs-bindings"


# --------------------------------------------------------------------------
# Availability gate — fail-loud, no silent fallback
# --------------------------------------------------------------------------


async def test_write_rs_bindings_refused_while_flag_false(choice_path: Path) -> None:
    km = await _key_manager()
    with pytest.raises(RsBindingsNotAvailableInPhase01Error):
        write_runtime_choice(
            family="kailash-rs-bindings",
            genesis_id=_GENESIS_ID,
            key_manager=km,
            signing_key_id=_SIGNING_KEY_ID,
        )
    # Nothing was persisted — the refusal is before any write.
    assert not choice_path.exists()


async def test_write_rs_bindings_allowed_when_flag_true(
    choice_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(feature_flags, "RS_BINDINGS_ENABLED", True)
    km = await _key_manager()
    choice = write_runtime_choice(
        family="kailash-rs-bindings",
        genesis_id=_GENESIS_ID,
        key_manager=km,
        signing_key_id=_SIGNING_KEY_ID,
    )
    assert choice.runtime_family == "kailash-rs-bindings"
    assert read_runtime_choice() == choice


async def test_unknown_family_rejected(choice_path: Path) -> None:
    km = await _key_manager()
    with pytest.raises(ValueError, match="not in"):
        write_runtime_choice(
            family="kailash-julia",
            genesis_id=_GENESIS_ID,
            key_manager=km,
            signing_key_id=_SIGNING_KEY_ID,
        )


async def test_malformed_genesis_id_rejected(choice_path: Path) -> None:
    km = await _key_manager()
    with pytest.raises(ValueError, match="64-hex|not hex"):
        write_runtime_choice(
            family="kailash-py",
            genesis_id="not-a-genesis-id",
            key_manager=km,
            signing_key_id=_SIGNING_KEY_ID,
        )


# --------------------------------------------------------------------------
# Integrity — corrupt config loud, tampered config fail-closed
# --------------------------------------------------------------------------


def test_corrupt_config_raises_loud(choice_path: Path) -> None:
    choice_path.write_text('{"schema_version": "runtime-choice/1.0"}\n')
    with pytest.raises(RuntimeChoiceCorruptError):
        read_runtime_choice()


def test_unknown_family_on_disk_is_corrupt(choice_path: Path) -> None:
    choice_path.write_text(
        json.dumps(
            {
                "schema_version": RUNTIME_CHOICE_SCHEMA_VERSION,
                "runtime_family": "kailash-julia",
                "chosen_at": "2026-06-15T00:00:00.000000+00:00",
                "chosen_by_genesis_id": _GENESIS_ID,
                "signature_hex": "deadbeef",
            }
        )
    )
    with pytest.raises(RuntimeChoiceCorruptError, match="runtime_family"):
        read_runtime_choice()


def test_non_json_config_raises_loud(choice_path: Path) -> None:
    choice_path.write_text("this is not json at all")
    with pytest.raises(RuntimeChoiceCorruptError):
        read_runtime_choice()


async def test_tampered_config_fails_signature(choice_path: Path) -> None:
    km = await _key_manager()
    write_runtime_choice(
        family="kailash-py",
        genesis_id=_GENESIS_ID,
        key_manager=km,
        signing_key_id=_SIGNING_KEY_ID,
    )
    # Attacker flips the family on disk, keeping the old signature.
    wire = json.loads(choice_path.read_text())
    monkeypatched_family = (
        "kailash-rs-bindings"
        if wire["runtime_family"] == "kailash-py"
        else "kailash-py"
    )
    wire["runtime_family"] = monkeypatched_family
    choice_path.write_text(json.dumps(wire))

    tampered = read_runtime_choice()
    assert tampered is not None
    pubkey = km.get_public_key(_SIGNING_KEY_ID)
    assert pubkey is not None
    with pytest.raises(RuntimeChoiceSignatureError):
        await verify_runtime_choice(tampered, key_manager=km, expected_pubkey=pubkey)


# --------------------------------------------------------------------------
# Path resolution
# --------------------------------------------------------------------------


def test_resolve_path_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # explicit arg wins
    explicit = tmp_path / "explicit.json"
    assert resolve_runtime_choice_path(explicit) == explicit
    # else env var
    env_target = tmp_path / "env.json"
    monkeypatch.setenv("ENVOY_RUNTIME_CHOICE_PATH", str(env_target))
    assert resolve_runtime_choice_path() == env_target
    # else default under ~/.envoy
    monkeypatch.delenv("ENVOY_RUNTIME_CHOICE_PATH", raising=False)
    default = resolve_runtime_choice_path()
    assert default == Path("~/.envoy/runtime-choice.json").expanduser()


def test_runtime_choice_signing_payload_excludes_signature() -> None:
    choice = RuntimeChoice(
        runtime_family="kailash-py",
        chosen_at="2026-06-15T00:00:00.000000+00:00",
        chosen_by_genesis_id=_GENESIS_ID,
        signature_hex="abc123",
    )
    assert "signature_hex" not in choice.signing_payload()
    assert choice.to_wire()["signature_hex"] == "abc123"
    assert os.fspath  # sanity: import used
