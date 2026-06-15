# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.runtime_switch — the `envoy runtime switch` state machine (S3p Wire).

Implements `specs/runtime-abstraction.md` § Runtime picker (`:202-204`): a
runtime switch requires, in order, (a) a cold passphrase unlock (NOT a warm
vault session), (b) target runtime attestation, (c) a T-015 envelope re-read
checkpoint, (d) a Genesis-signed `runtime_switch` Ledger entry, (e) flipping the
durable runtime-choice default. The CLI (`envoy/cli/runtime.py`) wires this to a
real `TrustVault` + durable `EnvoyLedger` + key manager and prints the confirm
copy; this module is the testable state-machine core with injected dependencies.

## `runtime_switch` Ledger entry schema (Spec-gap-4)

```json
{
  "from_family": "<previous runtime family>",
  "to_family": "<new runtime family>",
  "target_attestation_hash": "sha256:<hash of target runtime_identity>",
  "re_read_checkpoint_result": {
    "from_algorithm_identifier": {...},
    "to_algorithm_identifier": {...},
    "invalidated": true
  },
  "signed_by": "runtime_device_key"
}
```

The entry is signed by the device key via the ledger facade's own per-entry
signing (every `EnvoyLedger.append` Ed25519-signs canonical entry bytes), so
"Genesis-signed" is satisfied structurally; `signed_by` names the key class per
the `RuntimeAttestation` spec shape.

## Ordering invariant (attestation-before-record)

Target attestation runs BEFORE the ledger entry is written. If attestation
raises (unknown family, rs-bindings while the conformance flag is off, or — once
S3t lands — a binary_hash that does not match the reproducible-build manifest),
NO `runtime_switch` record is written and the default is NOT flipped. This is
the structural defense against recording a switch to a poisoned/absent runtime
(T-060). S3t replaces the identity-only attestation seam below with manifest +
N=3 mirror verification, keeping this ordering invariant.

## T-015 re-read checkpoint

`algorithm_identifier` is one of N2's five envelope-cache invalidation
properties (`runtime-abstraction.md:150`). A switch that crosses an
`algorithm_identifier` boundary therefore invalidates every envelope pinned
under the old runtime's identifier — the next `envelope_check` re-reads under
the new key. The checkpoint records the from→to `algorithm_identifier`
transition and whether it forced invalidation, pinning the evidence into the
signed `runtime_switch` entry.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from envoy.ledger.canonical import canonical_dumps
from envoy.runtime.runtime_attestation import (
    AttestedRuntimeIdentity,
    append_runtime_attestation,
)
from envoy.runtime.runtime_picker import (
    KNOWN_FAMILIES,
    RuntimeChoice,
    write_runtime_choice,
)
from envoy.runtime.selection import get_runtime

logger = logging.getLogger(__name__)

#: Wire-form entry type (V-05 canonical naming: lower_snake_case).
RUNTIME_SWITCH_ENTRY_TYPE = "runtime_switch"

#: `signed_by` key-class literal per the `RuntimeAttestation` spec shape.
_SIGNED_BY_RUNTIME_DEVICE_KEY = "runtime_device_key"


class WarmVaultSwitchRefusedError(RuntimeError):
    """A runtime switch was attempted without a cold passphrase unlock — a warm
    (already-unlocked / cached) vault session is not sufficient. The user MUST
    re-supply the vault passphrase so the switch forces a real Argon2id derive +
    decrypt + verify (`specs/runtime-abstraction.md:200` "passphrase unlock, not
    warm")."""


class RuntimeSwitchAttestationError(RuntimeError):
    """Target runtime attestation failed — the switch is refused fail-closed and
    NO `runtime_switch` record is written (attestation-before-record). S3t raises
    this for a binary_hash/manifest mismatch (T-060); S3p raises it when the
    target runtime cannot be constructed/identified at all."""


@dataclass(frozen=True, slots=True)
class RuntimeAttestation:
    """The attestation of a runtime family at switch time.

    S3p populates this from the runtime's live `runtime_identity()`; S3t hardens
    `attestation_hash` to incorporate the reproducible-build manifest + N=3
    mirror verdict and refuses (raises :class:`RuntimeSwitchAttestationError`)
    on a poisoned binary.
    """

    runtime_family: str
    attestation_hash: str
    algorithm_identifier: dict[str, str]
    runtime_identity: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RuntimeSwitchResult:
    """Outcome of a completed :func:`perform_runtime_switch`."""

    from_family: str
    to_family: str
    target_attestation_hash: str
    re_read_checkpoint_result: dict[str, Any]
    runtime_switch_entry_id: str
    runtime_attestation_entry_id: str
    runtime_choice: RuntimeChoice


class _VaultProtocol(Protocol):
    """The minimal `TrustVault` surface the switch needs for the cold-unlock
    gate (`envoy/trust/vault.py`)."""

    @property
    def is_unlocked(self) -> bool: ...

    async def lock(self) -> None: ...

    async def unlock(self, passphrase: str) -> None: ...


class _LedgerProtocol(Protocol):
    """The minimal durable-ledger surface — `EnvoyLedger.append` signs every
    entry with the device key (`envoy/ledger/facade.py:append`)."""

    async def append(
        self, *, entry_type: str, content: dict[str, Any]
    ) -> str: ...


def attest_runtime_via_identity(family: str, **runtime_kwargs: Any) -> RuntimeAttestation:
    """S3p attestation seam: attest a runtime family from its live identity.

    Constructs the runtime via `get_runtime(family)` and reads its
    `runtime_identity()` (real binary_hash + algorithm_identifier +
    device-bound pubkey). The attestation hash is the sha256 of the canonical
    identity bytes. Raises :class:`RuntimeSwitchAttestationError` when the
    runtime cannot be constructed (e.g. rs-bindings while the conformance flag
    is off, or an unknown family) — so a switch to an unbuildable target never
    reaches the record step.

    S3t REPLACES/WRAPS this seam with reproducible-build manifest verification +
    N=3 mirror cross-check + fail-closed-on-mismatch (T-060), preserving the
    attestation-before-record ordering.
    """
    try:
        runtime = get_runtime(family=family, **runtime_kwargs)
        identity = runtime.runtime_identity()
    except Exception as exc:  # noqa: BLE001 — re-raised as a typed attestation failure
        raise RuntimeSwitchAttestationError(
            f"runtime attestation for family={family!r} failed: {exc}"
        ) from exc
    if not isinstance(identity, dict):
        raise RuntimeSwitchAttestationError(
            f"runtime_identity() for family={family!r} returned "
            f"{type(identity).__name__!r}, expected a dict"
        )
    attestation_hash = (
        "sha256:" + hashlib.sha256(canonical_dumps(identity)).hexdigest()
    )
    raw_algo = identity.get("algorithm_identifier", {})
    algorithm_identifier = {str(k): str(v) for k, v in dict(raw_algo).items()}
    return RuntimeAttestation(
        runtime_family=family,
        attestation_hash=attestation_hash,
        algorithm_identifier=algorithm_identifier,
        runtime_identity=identity,
    )


async def perform_runtime_switch(
    *,
    target_family: str,
    current_family: str,
    vault: _VaultProtocol,
    passphrase: str,
    ledger: _LedgerProtocol,
    key_manager: Any,
    signing_key_id: str,
    genesis_id: str,
    attest: Any = attest_runtime_via_identity,
    runtime_choice_path: Any = None,
    now: datetime | None = None,
) -> RuntimeSwitchResult:
    """Run the runtime-switch state machine. Returns the switch result.

    Order (each step gates the next):

    1. **Cold-unlock gate** — a non-empty `passphrase` is required; a warm vault
       is re-sealed then unlocked so a real passphrase verification runs. A
       missing passphrase raises :class:`WarmVaultSwitchRefusedError`; a wrong
       passphrase raises `VaultUnlockFailedError` from the vault.
    2. **Attest target** (attestation-before-record) — `attest(target_family)`
       must succeed before anything is written.
    3. **T-015 re-read checkpoint** — record the from→to `algorithm_identifier`
       transition (drives N2 cache invalidation).
    4. **Genesis-signed `runtime_switch` entry** — written via the ledger's
       per-entry device-key signing.
    5. **Flip default** — persist the new signed runtime-choice config.

    Args:
        target_family / current_family: members of `KNOWN_FAMILIES`.
        vault: a `TrustVault`-shaped object for the cold-unlock gate.
        passphrase: the vault passphrase (cold-unlock proof).
        ledger: a durable ledger whose `append` signs entries.
        key_manager / signing_key_id / genesis_id: Genesis signing material for
            the runtime-choice config flip.
        attest: the attestation seam (S3p identity-based; S3t manifest-verified).
        runtime_choice_path / now: forwarded to `write_runtime_choice`.
    """
    if target_family not in KNOWN_FAMILIES:
        raise ValueError(
            f"target_family={target_family!r} not in {sorted(KNOWN_FAMILIES)}."
        )

    # 1. Cold-unlock gate — re-seal a warm vault so unlock performs a real verify.
    if not isinstance(passphrase, str) or not passphrase:
        raise WarmVaultSwitchRefusedError(
            "runtime switch requires a cold passphrase unlock; a warm vault "
            "session is not sufficient (re-enter your vault passphrase)."
        )
    if vault.is_unlocked:
        await vault.lock()
    await vault.unlock(passphrase)  # VaultUnlockFailedError on wrong passphrase

    # 2. Attest the target BEFORE any record is written (attestation-before-record).
    target_attestation = attest(target_family)
    current_attestation = attest(current_family)

    # 3. Emit the target's RuntimeAttestation entry BEFORE the switch record —
    #    the "every runtime_switch, before the switch record" moment
    #    (specs/runtime-abstraction.md § Runtime attestation). Signed by the
    #    device key via the ledger's per-entry signing.
    attestation_entry_id = await append_runtime_attestation(
        ledger,
        AttestedRuntimeIdentity.from_identity_dict(
            target_attestation.runtime_identity
        ),
        now=now,
    )

    # 4. T-015 re-read checkpoint — algorithm_identifier transition.
    re_read_checkpoint_result: dict[str, Any] = {
        "from_algorithm_identifier": current_attestation.algorithm_identifier,
        "to_algorithm_identifier": target_attestation.algorithm_identifier,
        "invalidated": (
            current_attestation.algorithm_identifier
            != target_attestation.algorithm_identifier
        ),
    }

    # 5. Genesis-signed runtime_switch entry (device-key signed by the ledger).
    content: dict[str, Any] = {
        "from_family": current_family,
        "to_family": target_family,
        "target_attestation_hash": target_attestation.attestation_hash,
        "runtime_attestation_entry_id": attestation_entry_id,
        "re_read_checkpoint_result": re_read_checkpoint_result,
        "signed_by": _SIGNED_BY_RUNTIME_DEVICE_KEY,
    }
    entry_id = await ledger.append(
        entry_type=RUNTIME_SWITCH_ENTRY_TYPE, content=content
    )

    # 5. Flip the durable default to the attested target.
    choice = write_runtime_choice(
        family=target_family,
        genesis_id=genesis_id,
        key_manager=key_manager,
        signing_key_id=signing_key_id,
        path=runtime_choice_path,
        now=now,
    )

    logger.info(
        "runtime.switch.ok",
        extra={
            "from_family": current_family,
            "to_family": target_family,
            "runtime_switch_entry_id": entry_id,
            "re_read_invalidated": re_read_checkpoint_result["invalidated"],
        },
    )
    return RuntimeSwitchResult(
        from_family=current_family,
        to_family=target_family,
        target_attestation_hash=target_attestation.attestation_hash,
        re_read_checkpoint_result=re_read_checkpoint_result,
        runtime_switch_entry_id=entry_id,
        runtime_attestation_entry_id=attestation_entry_id,
        runtime_choice=choice,
    )


__all__ = [
    "RUNTIME_SWITCH_ENTRY_TYPE",
    "RuntimeAttestation",
    "RuntimeSwitchAttestationError",
    "RuntimeSwitchResult",
    "WarmVaultSwitchRefusedError",
    "attest_runtime_via_identity",
    "perform_runtime_switch",
]
