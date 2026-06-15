# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.runtime_attestation — RuntimeAttestation entry + real binary_hash (S3t).

Implements `specs/runtime-abstraction.md` § Runtime attestation: the
`RuntimeAttestation` Ledger entry attesting the runtime's binary hash +
device-bound key + algorithm_identifier, emitted at every `startup()`, at every
`runtime_switch` (before the switch record), and on-demand via
`envoy runtime attest`.

## Spec-gap-1 — two distinct RuntimeIdentity shapes

This module defines :class:`AttestedRuntimeIdentity`, the **5-field** identity
the attestation entry uses (`runtime_family`, `version`, `binary_hash`,
`device_bound_pubkey_hex`, `algorithm_identifier`). It is DELIBERATELY distinct
from `envoy.ledger.head.RuntimeIdentity`, the **3-field** identity
(`device_id`, `signing_key_id`, `algorithm_identifier`) bound into a
`HaltedByRollback` record. The two serve different purposes: the 3-field halt
identity binds a halt event to a signing instance; the 5-field attestation
identity binds the running BINARY to its reproducible-build hash. The attestation
vector uses the 5-field shape; this docstring is the Spec-gap-1 resolution.

## Real binary_hash (S3t scope)

`compute_runtime_binary_hash` replaces the Phase-01 sentinel
(`"sha256:phase-01-software-fallback"`) with a real, deterministic sha256 over
the installed runtime package's file bytes (sorted by relative path). Cached
per package root — the installed artifact does not change within a process.

## What lands with S16 (release-gated WS-2 distribution), NOT here

The T-060 **verification gate** — comparing this `binary_hash` against the
Foundation's reproducible-build manifest fetched via N=3 mirrors, plus the
`RevokedSigningKeyError` revocation-list check — depends on the manifest +
mirror + revocation infrastructure produced by S16 (`specs/distribution.md`
§27/§39/§94-97), which is unbuilt and release-gated. This module RECORDS the
attestation (real binary_hash, entries at all three moments); the
manifest-mismatch REFUSAL is the S16 follow-up. `envoy.runtime.runtime_switch`
already fails closed when attestation cannot be COMPUTED (unconstructable
runtime); the manifest-mismatch refusal extends that seam when S16 lands.
"""

from __future__ import annotations

import hashlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: Wire-form entry type. The spec's § Entry types names this `RuntimeAttestation`
#: (PascalCase — distinct from the lower_snake `runtime_switch` action entry).
RUNTIME_ATTESTATION_ENTRY_TYPE: Final[str] = "RuntimeAttestation"

#: Pinned attestation schema version per `specs/runtime-abstraction.md`.
RUNTIME_ATTESTATION_SCHEMA_VERSION: Final[str] = "runtime-attest/1.0"

#: `signed_by` key-class literal per the spec's RuntimeAttestation shape.
SIGNED_BY_RUNTIME_DEVICE_KEY: Final[str] = "runtime_device_key"

#: Runtime family → the installed Python package whose bytes are the binary.
#: Both Kailash runtimes ship in the single `kailash` wheel (`pip install
#: kailash`), so both attest the same installed artifact; S16's per-family
#: manifest verification distinguishes them when separate artifacts ship.
_PACKAGE_FOR_FAMILY: Final[dict[str, str]] = {
    "kailash-py": "kailash",
    "kailash-rs-bindings": "kailash",
}

#: Process-lifetime cache: package-root path → computed "sha256:<hex>".
_BINARY_HASH_CACHE: dict[str, str] = {}


class RuntimeAttestationError(RuntimeError):
    """The runtime's binary could not be located/hashed for attestation. Raised
    loud (fail-closed) rather than emitting a fake/sentinel hash."""


@dataclass(frozen=True, slots=True)
class AttestedRuntimeIdentity:
    """5-field runtime identity for the `RuntimeAttestation` entry (Spec-gap-1).

    Distinct from `envoy.ledger.head.RuntimeIdentity` (3-field halt identity).
    """

    runtime_family: str
    version: str
    binary_hash: str
    device_bound_pubkey_hex: str | None
    algorithm_identifier: dict[str, str]

    @classmethod
    def from_identity_dict(cls, identity: dict[str, Any]) -> AttestedRuntimeIdentity:
        """Build from a runtime adapter's `runtime_identity()` dict (the
        5-field shape `kailash_py` / `kailash_rs_bindings` return)."""
        return cls(
            runtime_family=str(identity["runtime_family"]),
            version=str(identity["version"]),
            binary_hash=str(identity["binary_hash"]),
            device_bound_pubkey_hex=(
                str(identity["device_bound_pubkey_hex"])
                if identity.get("device_bound_pubkey_hex") is not None
                else None
            ),
            algorithm_identifier={
                str(k): str(v)
                for k, v in dict(identity.get("algorithm_identifier", {})).items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_family": self.runtime_family,
            "version": self.version,
            "binary_hash": self.binary_hash,
            "device_bound_pubkey_hex": self.device_bound_pubkey_hex,
            "algorithm_identifier": dict(self.algorithm_identifier),
        }


def _resolve_package_root(package_name: str) -> Path:
    spec = importlib.util.find_spec(package_name)
    if spec is None:
        raise RuntimeAttestationError(
            f"runtime package {package_name!r} is not importable — cannot "
            f"compute a real binary_hash for attestation."
        )
    # Prefer the package directory (submodule_search_locations) so the hash
    # covers the whole installed artifact (Python + any compiled extension);
    # fall back to the module origin file for a single-file module.
    if spec.submodule_search_locations:
        return Path(next(iter(spec.submodule_search_locations)))
    if spec.origin and spec.origin not in ("built-in", "frozen"):
        return Path(spec.origin).parent
    raise RuntimeAttestationError(
        f"runtime package {package_name!r} has no locatable on-disk root "
        f"(origin={spec.origin!r}) — cannot compute a real binary_hash."
    )


def compute_runtime_binary_hash(
    family: str, *, package_root: Path | None = None
) -> str:
    """Return a real `"sha256:<hex>"` over the installed runtime package bytes.

    Deterministic: hashes each file's POSIX relative path + its bytes, walked in
    sorted path order, so the digest is stable across runs and machines for the
    same installed artifact. Cached per resolved package root (the artifact does
    not change within a process). Raises :class:`RuntimeAttestationError` when
    the package cannot be located (fail-loud, never a sentinel).
    """
    if package_root is None:
        package_name = _PACKAGE_FOR_FAMILY.get(family)
        if package_name is None:
            raise RuntimeAttestationError(
                f"no package mapping for runtime family {family!r}; known "
                f"families: {sorted(_PACKAGE_FOR_FAMILY)}."
            )
        package_root = _resolve_package_root(package_name)

    cache_key = str(package_root)
    cached = _BINARY_HASH_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if not package_root.exists():
        raise RuntimeAttestationError(
            f"runtime package root {package_root} does not exist on disk."
        )

    digest = hashlib.sha256()
    files = sorted(
        (p for p in package_root.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(package_root).as_posix(),
    )
    for path in files:
        rel = path.relative_to(package_root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    result = "sha256:" + digest.hexdigest()
    _BINARY_HASH_CACHE[cache_key] = result
    return result


def build_runtime_attestation(
    identity: AttestedRuntimeIdentity,
    *,
    attested_at: str,
    device_attestation_type: str = "software",
    device_attestation_hash: str | None = None,
    reproducible_build_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the `RuntimeAttestation` entry content per
    `specs/runtime-abstraction.md` § Runtime attestation.

    `device_attestation_type` is `software` in Phase-02 (no Secure Enclave / TPM
    binding yet); `reproducible_build_refs` is empty here — S16's
    reproducible-build stream populates it. The entry is signed by the device
    key via the ledger facade's per-entry signing (`signed_by` names the class).
    """
    return {
        "schema_version": RUNTIME_ATTESTATION_SCHEMA_VERSION,
        "runtime_identity": identity.to_dict(),
        "device_attestation": {
            "attestation_type": device_attestation_type,
            "attestation_hash": (
                device_attestation_hash
                if device_attestation_hash is not None
                else identity.binary_hash
            ),
        },
        "reproducible_build_refs": reproducible_build_refs or [],
        "attested_at": attested_at,
        "signed_by": SIGNED_BY_RUNTIME_DEVICE_KEY,
    }


def _canonical_now(now: Any = None) -> str:
    """Canonical microsecond-padded UTC timestamp for `attested_at`."""
    from datetime import datetime, timezone  # noqa: PLC0415

    from envoy.ledger.canonical import _format_timestamp  # noqa: PLC0415

    return _format_timestamp(now or datetime.now(tz=timezone.utc))


def attestation_for_runtime(runtime_adapter: Any, *, now: Any = None) -> dict[str, Any]:
    """Build a `RuntimeAttestation` content dict from a runtime adapter's
    `runtime_identity()` (without appending). Used by `envoy ledger export` to
    populate the export bundle's `head_commitment.runtime_attestation` with the
    active runtime's real attestation."""
    identity = AttestedRuntimeIdentity.from_identity_dict(
        runtime_adapter.runtime_identity()
    )
    return build_runtime_attestation(identity, attested_at=_canonical_now(now))


async def append_runtime_attestation(
    ledger: Any, identity: AttestedRuntimeIdentity, *, now: Any = None
) -> str:
    """Build a `RuntimeAttestation` entry for `identity` and append it to
    `ledger` (any object with `append(entry_type=, content=) -> entry_id`).
    Returns the new entry_id. The single helper behind all three attestation
    moments — startup, runtime_switch (before record), and `envoy runtime
    attest` — so the entry shape is identical everywhere.
    """
    content = build_runtime_attestation(identity, attested_at=_canonical_now(now))
    entry_id: str = await ledger.append(
        entry_type=RUNTIME_ATTESTATION_ENTRY_TYPE, content=content
    )
    return entry_id


__all__ = [
    "RUNTIME_ATTESTATION_ENTRY_TYPE",
    "RUNTIME_ATTESTATION_SCHEMA_VERSION",
    "SIGNED_BY_RUNTIME_DEVICE_KEY",
    "AttestedRuntimeIdentity",
    "RuntimeAttestationError",
    "append_runtime_attestation",
    "attestation_for_runtime",
    "build_runtime_attestation",
    "compute_runtime_binary_hash",
]
