# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""CO validator six-step exercise (EC-S9a.4 + EC-S9a.5).

Tier-2 per `rules/testing.md`: real `InMemoryKeyManager` Ed25519 verify (no
mock). `specs/skill-ingest.md` § CO validator: every step (1 schema, 2 registry,
3 declared=inferred, 4 over-privilege, 5 typed-pending surface, 6 publisher
signature) exercised on known-good + targeted-bad skills.

Covers:
- EC-S9a.4: `declared ⊋ inferred` → `OverPrivilegeWarning` in the result (NOT a
  reject) + the step-5 typed-pending assertion.
- EC-S9a.5: step-2 unknown pattern → `UnknownPermissionPatternError`; step-6
  signature failure → `PublisherSignatureInvalidError`; `skill_source_hash`
  mismatch → `SkillSourceHashMismatchError`.

Structural asserts only — raised type / returned field shapes.
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.skill_ingest import (
    AdversarialCheckPending,
    OverPrivilegeWarning,
    PublisherRef,
    PublisherSignatureInvalidError,
    SkillManifestParseError,
    SkillSourceHashMismatchError,
    UnknownPermissionPatternError,
    compute_skill_source_hash,
    validate_skill,
)

_GENESIS = "genesis:six-steps-publisher"


@pytest.fixture
async def publisher_env():
    """Real Ed25519 keypair + signer; yields ``(pinned, km, sign)``."""
    km = InMemoryKeyManager()
    _priv, pub = await km.generate_keypair("six-steps")

    def sign(skill_source: str, *, genesis_id: str = _GENESIS) -> PublisherRef:
        digest = compute_skill_source_hash(skill_source)
        signature = km.sign_with_key("six-steps", digest.encode("utf-8"))
        return PublisherRef(genesis_id=genesis_id, signature=signature)

    yield {_GENESIS: pub}, km, sign


def _skill(name: str, permissions: tuple[str, ...], code: str) -> str:
    perm = "".join(f"  - {p}\n" for p in permissions) or ""
    perm_block = f"permissions:\n{perm}" if permissions else "permissions: []\n"
    body = f"```python\n{code}\n```" if code else ""
    return f"---\nname: {name}\nversion: 1.0.0\ndescription: A skill.\n{perm_block}---\n\n# {name}\n\n{body}\n"


# --- happy path: all six steps on a known-good skill -------------------------


class TestSixStepsHappyPath:
    async def test_known_good_skill_exercises_all_steps(self, publisher_env) -> None:
        pinned, km, sign = publisher_env
        # Declares file-read + http-post; code reaches BOTH literally → clean.
        source = _skill(
            "good",
            ("file-read:*", "http-post:api.example.com"),
            "import requests\n"
            'with open("in.txt") as f:\n'
            "    body = f.read()\n"
            'requests.post("https://api.example.com/x", data=body)',
        )
        result = await validate_skill(
            source,
            publisher=sign(source),
            pinned_publisher_pubkeys=pinned,
            key_manager=km,
        )
        # Step 1: parsed manifest present.
        assert result.manifest.name == "good"
        # Step 2: registry resolution populated the PACT dimensions.
        assert "data_access" in result.resolved_dimensions
        assert "communication" in result.resolved_dimensions
        # Steps 3+4: clean reach → ≥0.8, no over-privilege.
        assert result.clean is True
        assert result.over_privilege is None
        # Step 5: typed pending surface (NOT a silent pass, NOT implemented).
        assert isinstance(result.adversarial_pending, AdversarialCheckPending)
        assert result.adversarial_pending.pending is True
        # Step 6: companion publisher block carries the verified signature.
        assert result.companion.publisher.genesis_id == _GENESIS


# --- step 4: over-privilege → OverPrivilegeWarning, NOT a reject -------------


class TestStep4OverPrivilege:
    async def test_over_declaration_surfaces_warning_not_reject(self, publisher_env) -> None:
        pinned, km, sign = publisher_env
        # Declares file-read + http-post; code only reaches file-read.
        source = _skill(
            "over",
            ("file-read:*", "http-post:api.example.com"),
            'with open("only.txt") as f:\n    data = f.read()',
        )
        result = await validate_skill(
            source,
            publisher=sign(source),
            pinned_publisher_pubkeys=pinned,
            key_manager=km,
        )
        # Accepted (NOT refused) + a typed OverPrivilegeWarning surfaced.
        assert result.passed is True
        assert isinstance(result.over_privilege, OverPrivilegeWarning)
        assert "http-post" in result.over_privilege.excess


# --- step 5: typed pending surface -------------------------------------------


class TestStep5TypedPending:
    async def test_step5_emits_typed_pending_marker(self, publisher_env) -> None:
        pinned, km, sign = publisher_env
        source = _skill("p5", ("file-read:*",), 'open("x.txt").read()')
        result = await validate_skill(
            source,
            publisher=sign(source),
            pinned_publisher_pubkeys=pinned,
            key_manager=km,
        )
        pending = result.adversarial_pending
        assert isinstance(pending, AdversarialCheckPending)
        assert pending.pending is True
        # Structured marker names the S9b registry dependency (not a bare pass).
        assert pending.registry_id == "envoy-registry:adversarial-skill-patterns:v1"


# --- step 2: unknown pattern → UnknownPermissionPatternError ------------------


class TestStep2UnknownPattern:
    async def test_unknown_permission_category_raises(self, publisher_env) -> None:
        pinned, km, sign = publisher_env
        source = _skill("unk", ("quantum-teleport:*",), "x = 1")
        with pytest.raises(UnknownPermissionPatternError) as exc_info:
            await validate_skill(
                source,
                publisher=sign(source),
                pinned_publisher_pubkeys=pinned,
                key_manager=km,
            )
        assert exc_info.value.pattern == "quantum-teleport:*"


# --- step 1: malformed manifest → SkillManifestParseError --------------------


class TestStep1SchemaValidation:
    async def test_missing_required_field_raises(self, publisher_env) -> None:
        pinned, km, sign = publisher_env
        # No 'version' field.
        source = "---\nname: bad\ndescription: missing version.\n---\n\n# bad\n"
        with pytest.raises(SkillManifestParseError):
            await validate_skill(
                source,
                publisher=sign(source),
                pinned_publisher_pubkeys=pinned,
                key_manager=km,
            )


# --- step 6: signature failure → PublisherSignatureInvalidError --------------


class TestStep6PublisherSignature:
    async def test_bad_signature_raises(self, publisher_env) -> None:
        pinned, km, _sign = publisher_env
        source = _skill("sig", ("file-read:*",), 'open("x.txt").read()')
        # A garbage signature that will not verify against the pinned key.
        bad_publisher = PublisherRef(genesis_id=_GENESIS, signature="00" * 32)
        with pytest.raises(PublisherSignatureInvalidError):
            await validate_skill(
                source,
                publisher=bad_publisher,
                pinned_publisher_pubkeys=pinned,
                key_manager=km,
            )

    async def test_unpinned_publisher_raises(self, publisher_env) -> None:
        pinned, km, sign = publisher_env
        source = _skill("sig2", ("file-read:*",), 'open("x.txt").read()')
        # Sign correctly but claim an UNPINNED genesis_id.
        publisher = sign(source, genesis_id="genesis:not-pinned")
        with pytest.raises(PublisherSignatureInvalidError):
            await validate_skill(
                source,
                publisher=publisher,
                pinned_publisher_pubkeys=pinned,
                key_manager=km,
            )


# --- skill_source_hash mismatch → SkillSourceHashMismatchError ---------------


class TestSkillSourceHashIntegrity:
    async def test_hash_mismatch_raises(self, publisher_env) -> None:
        pinned, km, sign = publisher_env
        source = _skill("hash", ("file-read:*",), 'open("x.txt").read()')
        with pytest.raises(SkillSourceHashMismatchError) as exc_info:
            await validate_skill(
                source,
                publisher=sign(source),
                pinned_publisher_pubkeys=pinned,
                key_manager=km,
                expected_skill_source_hash="deadbeef" * 8,
            )
        assert exc_info.value.computed == compute_skill_source_hash(source)
