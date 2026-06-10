# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""3-adversarial CO-validator corpus refusal (EC-S9a.1 + EC-S9a.2).

Tier-2 per `rules/testing.md`: the Ed25519 verify path is the REAL kailash
`InMemoryKeyManager` (real crypto, no mock); the fixtures are the checked-in
adversarial SKILL.md corpus. `specs/skill-ingest.md` § CO validator + ROADMAP
§108 ("CO validator rejects 3 constructed adversarial skill samples").

This file owns all three adversarial rows:

- EC-S9a.1 — `permission_escalation.md` + `exfiltration.md` each make a LITERAL
  call to an undeclared capability → score <0.5 → `COValidatorRefusedError`.
- EC-S9a.2 — `dynamic_dispatch.md` reaches an undeclared capability via a LITERAL
  `getattr` / `importlib` call site → rejected DIRECTLY by the AST walk (score
  <0.5, `COValidatorRefusedError`), NOT dependent on the S9b ensemble.

Structural asserts only (raised type + score band) — no regex over prose.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.skill_ingest import (
    COValidatorRefusedError,
    PublisherRef,
    compute_skill_source_hash,
    validate_skill,
)

_CORPUS = (
    Path(__file__).resolve().parents[1]
    / "acceptance"
    / "phase_02"
    / "co_validator_corpus"
    / "adversarial"
)


@pytest.fixture
async def signed_publisher():
    """A real Ed25519 publisher keypair + a signer that signs a skill source.

    Yields ``(pinned_pubkeys, key_manager, sign)`` where ``sign(skill_source)``
    returns a `PublisherRef` carrying a valid signature over the source hash, so
    step-6 publisher verification PASSES and the test isolates the step-3/4
    AST-routing refusal. Real crypto — no mock (Tier-2 contract).
    """
    km = InMemoryKeyManager()
    _priv, pub = await km.generate_keypair("adversarial-publisher")
    genesis_id = "genesis:adversarial-publisher"

    def sign(skill_source: str) -> PublisherRef:
        digest = compute_skill_source_hash(skill_source)
        signature = km.sign_with_key("adversarial-publisher", digest.encode("utf-8"))
        return PublisherRef(genesis_id=genesis_id, signature=signature)

    yield {genesis_id: pub}, km, sign


async def _expect_refusal(name: str, signed_publisher) -> COValidatorRefusedError:
    pinned, km, sign = signed_publisher
    source = (_CORPUS / name).read_text(encoding="utf-8")
    publisher = sign(source)
    with pytest.raises(COValidatorRefusedError) as exc_info:
        await validate_skill(
            source,
            publisher=publisher,
            pinned_publisher_pubkeys=pinned,
            key_manager=km,
        )
    return exc_info.value


class TestAdversarialLiteralCalls:
    """EC-S9a.1 — literal undeclared-capability calls drive score <0.5."""

    async def test_permission_escalation_refused_below_threshold(self, signed_publisher) -> None:
        err = await _expect_refusal("permission_escalation.md", signed_publisher)
        assert err.score < 0.5
        # The reject was driven by AST-proven literal evidence, not absence.
        assert err.errors

    async def test_exfiltration_refused_below_threshold(self, signed_publisher) -> None:
        err = await _expect_refusal("exfiltration.md", signed_publisher)
        assert err.score < 0.5
        assert err.errors


class TestAdversarialDynamicDispatch:
    """EC-S9a.2 — literal getattr/importlib reach rejected DIRECTLY by the AST
    walk, independent of the S9b classifier ensemble."""

    async def test_dynamic_dispatch_refused_by_ast_walk(self, signed_publisher) -> None:
        err = await _expect_refusal("dynamic_dispatch.md", signed_publisher)
        assert err.score < 0.5
        # At least one error is the dynamic-dispatch construct the AST flagged.
        assert err.errors
