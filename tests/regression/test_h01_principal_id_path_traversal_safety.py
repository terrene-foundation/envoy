"""Regression: H-01 — principal_id / authority_id / delegator_id / delegatee_id /
task_id path-traversal safety at every TrustStoreAdapter public boundary.

Source: gate-level security review of PR #3 (Phase 01 Wave 1) finding H-01.

Failure mode being guarded: an externally-sourced identifier flowing into
TrustStoreAdapter that contains `..`, `/`, `\\x00`, control characters, or a
leading `.` would propagate unchanged into kailash-py's SQLite primary key
AND (post-T-01-13) the Trust Vault container's filesystem path. Path-traversal
shapes like `../../etc/passwd` could read or overwrite files outside the trust
store; null-byte shapes truncate credential parsing in C-extensions.

Defense per `rules/trust-plane-security.md` MUST Rule 2: every public boundary
calls the envoy-side validator `_validate_id_safety` which rejects unsafe
shapes BEFORE the identifier reaches kailash-py / SQLite / filesystem.

Per `rules/refactor-invariants.md`: permanent regression marker. Deletion /
silent skip BLOCKED per `rules/testing.md` § Test-Skip Triage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from envoy.trust.errors import PrincipalRequiredError
from envoy.trust.store import TrustStoreAdapter


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "vault.dat"


# ---------------------------------------------------------------------------
# Constructor — principal_id sanitization on every adapter instantiation
# ---------------------------------------------------------------------------


class TestConstructorPrincipalIdSafety:
    """Adapter construction is the FIRST boundary; every test here exercises a
    distinct unsafe shape that path-traversal exploits would use."""

    @pytest.mark.parametrize(
        "unsafe_principal_id",
        [
            "../etc/passwd",
            "../../etc/shadow",
            "agent/with/slashes",
            "agent\\with\\backslashes",
            "..",
            ".hidden",
            "agent\x00bypass",
            "agent\x01ctl",
            "agent\nwith\nnewline",
            "agent\twith\ttab",
            "a" * 257,  # length cap (256)
        ],
    )
    def test_unsafe_principal_id_rejected(self, vault_path: Path, unsafe_principal_id: str) -> None:
        with pytest.raises(PrincipalRequiredError, match="identifier safety"):
            TrustStoreAdapter(vault_path=vault_path, principal_id=unsafe_principal_id)

    @pytest.mark.parametrize(
        "safe_principal_id",
        [
            "alice",
            "alice@example",
            "alice@example.com",
            "agent-001",
            "agent_001",
            "agent.42+ci",
            "principal-with-many-hyphens-and_underscores",
        ],
    )
    def test_safe_principal_id_accepted(self, vault_path: Path, safe_principal_id: str) -> None:
        adapter = TrustStoreAdapter(vault_path=vault_path, principal_id=safe_principal_id)
        assert adapter.principal_id == safe_principal_id


# ---------------------------------------------------------------------------
# Length DoS guard — over-long ID rejected
# ---------------------------------------------------------------------------


class TestLengthCap:
    def test_length_cap_at_256(self, vault_path: Path) -> None:
        # 256 chars accepted (boundary inclusive)
        long_id = "a" * 256
        TrustStoreAdapter(vault_path=vault_path, principal_id=long_id)

    def test_257_chars_rejected(self, vault_path: Path) -> None:
        too_long = "a" * 257
        with pytest.raises(PrincipalRequiredError, match="exceeds max"):
            TrustStoreAdapter(vault_path=vault_path, principal_id=too_long)
