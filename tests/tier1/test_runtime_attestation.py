# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1: S3t runtime attestation — real binary_hash + 5-field identity + entry.

Covers the buildable-now S3t core (the manifest/mirror VERIFICATION gate is the
S16 follow-up): the real binary_hash replacing the Phase-01 sentinel, the
5-field `AttestedRuntimeIdentity` (Spec-gap-1, distinct from the 3-field halt
identity), and the `RuntimeAttestation` entry shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from envoy.ledger.head import RuntimeIdentity as HaltRuntimeIdentity
from envoy.runtime.runtime_attestation import (
    RUNTIME_ATTESTATION_SCHEMA_VERSION,
    AttestedRuntimeIdentity,
    RuntimeAttestationError,
    build_runtime_attestation,
    compute_runtime_binary_hash,
)


def _write(root: Path, rel: str, data: bytes) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


# --------------------------------------------------------------------------
# Real binary_hash — deterministic, cached, fail-loud
# --------------------------------------------------------------------------


def test_binary_hash_is_real_sha256_for_installed_kailash() -> None:
    h = compute_runtime_binary_hash("kailash-py")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64
    # The Phase-01 sentinel is gone.
    assert h != "sha256:phase-01-software-fallback"


def test_binary_hash_deterministic_and_order_independent(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    _write(root_a, "z.py", b"zzz")
    _write(root_a, "pkg/m.py", b"mmm")
    _write(root_a, "a.py", b"aaa")
    h1 = compute_runtime_binary_hash("kailash-py", package_root=root_a)
    # Same content under a different root path → same digest (path-relative).
    root_b = tmp_path / "b"
    _write(root_b, "a.py", b"aaa")
    _write(root_b, "pkg/m.py", b"mmm")
    _write(root_b, "z.py", b"zzz")
    h2 = compute_runtime_binary_hash("kailash-py", package_root=root_b)
    assert h1 == h2


def test_binary_hash_changes_with_content(tmp_path: Path) -> None:
    root = tmp_path / "pkg1"
    _write(root, "m.py", b"original")
    h1 = compute_runtime_binary_hash("kailash-py", package_root=root)
    other = tmp_path / "pkg2"
    _write(other, "m.py", b"tampered")
    h2 = compute_runtime_binary_hash("kailash-py", package_root=other)
    assert h1 != h2


def test_binary_hash_cached_per_root(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    _write(root, "m.py", b"v1")
    h1 = compute_runtime_binary_hash("kailash-py", package_root=root)
    # Mutate the file AFTER the first (cached) hash — the cache returns the
    # original digest for the same root (process-lifetime artifact assumption).
    (root / "m.py").write_bytes(b"v2-mutated")
    h2 = compute_runtime_binary_hash("kailash-py", package_root=root)
    assert h1 == h2


def test_binary_hash_unknown_family_raises() -> None:
    with pytest.raises(RuntimeAttestationError, match="no package mapping"):
        compute_runtime_binary_hash("kailash-julia")


def test_binary_hash_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeAttestationError, match="does not exist"):
        compute_runtime_binary_hash(
            "kailash-py", package_root=tmp_path / "nonexistent"
        )


# --------------------------------------------------------------------------
# Spec-gap-1 — 5-field attestation identity, distinct from 3-field halt identity
# --------------------------------------------------------------------------


def test_attested_identity_roundtrip() -> None:
    identity_dict = {
        "runtime_family": "kailash-py",
        "version": "envoy-runtime-kailash-py/0.1.0",
        "binary_hash": "sha256:abc",
        "device_bound_pubkey_hex": "deadbeef",
        "algorithm_identifier": {"sig": "ed25519", "hash": "sha256"},
    }
    identity = AttestedRuntimeIdentity.from_identity_dict(identity_dict)
    assert identity.runtime_family == "kailash-py"
    assert identity.binary_hash == "sha256:abc"
    assert identity.to_dict() == identity_dict


def test_attested_identity_handles_none_pubkey() -> None:
    identity = AttestedRuntimeIdentity.from_identity_dict(
        {
            "runtime_family": "kailash-py",
            "version": "v",
            "binary_hash": "sha256:x",
            "device_bound_pubkey_hex": None,
            "algorithm_identifier": {},
        }
    )
    assert identity.device_bound_pubkey_hex is None
    assert identity.to_dict()["device_bound_pubkey_hex"] is None


def test_spec_gap_1_attested_identity_distinct_from_halt_identity() -> None:
    # The 5-field attestation identity and the 3-field halt identity are
    # DELIBERATELY distinct types with disjoint field sets (Spec-gap-1).
    attested_fields = set(
        AttestedRuntimeIdentity.from_identity_dict(
            {
                "runtime_family": "kailash-py",
                "version": "v",
                "binary_hash": "sha256:x",
                "device_bound_pubkey_hex": None,
                "algorithm_identifier": {},
            }
        ).to_dict()
    )
    halt = HaltRuntimeIdentity.from_runtime(
        device_id="dev",
        signing_key_id="key",
        algorithm_identifier={"sig": "ed25519"},
    )
    halt_fields = set(halt.to_dict())
    assert attested_fields == {
        "runtime_family",
        "version",
        "binary_hash",
        "device_bound_pubkey_hex",
        "algorithm_identifier",
    }
    assert halt_fields == {"device_id", "signing_key_id", "algorithm_identifier"}
    # The only shared field is algorithm_identifier; the identities are distinct.
    assert attested_fields != halt_fields


# --------------------------------------------------------------------------
# RuntimeAttestation entry shape
# --------------------------------------------------------------------------


def test_build_runtime_attestation_shape() -> None:
    identity = AttestedRuntimeIdentity.from_identity_dict(
        {
            "runtime_family": "kailash-py",
            "version": "v",
            "binary_hash": "sha256:bh",
            "device_bound_pubkey_hex": "pk",
            "algorithm_identifier": {"sig": "ed25519"},
        }
    )
    content = build_runtime_attestation(
        identity, attested_at="2026-06-15T00:00:00.000000+00:00"
    )
    assert content["schema_version"] == RUNTIME_ATTESTATION_SCHEMA_VERSION
    assert content["runtime_identity"]["binary_hash"] == "sha256:bh"
    assert content["device_attestation"]["attestation_type"] == "software"
    # Default device attestation_hash falls back to the binary_hash.
    assert content["device_attestation"]["attestation_hash"] == "sha256:bh"
    assert content["reproducible_build_refs"] == []
    assert content["attested_at"] == "2026-06-15T00:00:00.000000+00:00"
    assert content["signed_by"] == "runtime_device_key"
