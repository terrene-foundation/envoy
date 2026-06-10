# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""100-benign CO-validator corpus acceptance (EC-S9a.3).

Tier-2 per `rules/testing.md`: real `InMemoryKeyManager` Ed25519 verify (no
mock). `specs/skill-ingest.md` + ROADMAP §108 ("... and accepts 100 benign
ones").

EC-S9a.3: all 100 benign skills accept (score ≥0.8 OR warning band; ZERO
`COValidatorRefusedError`). Any single false-reject is build-blocking — the fix
is to the inference, NOT the fixture (`rules/testing.md` — never change a test
to fit the code).

Structural asserts only — raised type (none expected) + score band.
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

_BENIGN_DIR = (
    Path(__file__).resolve().parents[1]
    / "acceptance"
    / "phase_02"
    / "co_validator_corpus"
    / "benign"
)

_BENIGN_FIXTURES = sorted(_BENIGN_DIR.glob("skill_*.md"))


@pytest.fixture
async def signed_publisher():
    """Real Ed25519 publisher keypair + per-source signer (Tier-2, no mock)."""
    km = InMemoryKeyManager()
    _priv, pub = await km.generate_keypair("benign-publisher")
    genesis_id = "genesis:benign-publisher"

    def sign(skill_source: str) -> PublisherRef:
        digest = compute_skill_source_hash(skill_source)
        signature = km.sign_with_key("benign-publisher", digest.encode("utf-8"))
        return PublisherRef(genesis_id=genesis_id, signature=signature)

    yield {genesis_id: pub}, km, sign


def test_corpus_has_exactly_100_benign_fixtures() -> None:
    """EC-S9a.3 precondition: the corpus contains exactly 100 benign fixtures."""
    assert len(_BENIGN_FIXTURES) == 100


@pytest.mark.parametrize("fixture", _BENIGN_FIXTURES, ids=lambda p: p.name)
async def test_benign_skill_accepts(fixture: Path, signed_publisher) -> None:
    """Every benign skill validates WITHOUT a refusal and lands ≥0.5 (pass or
    warning band). A false-reject here is a build-blocking inference bug."""
    pinned, km, sign = signed_publisher
    source = fixture.read_text(encoding="utf-8")
    publisher = sign(source)

    try:
        result = await validate_skill(
            source,
            publisher=publisher,
            pinned_publisher_pubkeys=pinned,
            key_manager=km,
        )
    except COValidatorRefusedError as exc:  # pragma: no cover - failure path
        pytest.fail(
            f"benign fixture {fixture.name} was FALSE-REJECTED "
            f"(score={exc.score}, errors={exc.errors}); fix the inference, "
            "not the fixture"
        )

    assert result.passed is True
    assert result.score >= 0.5
    assert result.force_install_used is False


async def test_all_benign_accept_aggregate(signed_publisher) -> None:
    """Aggregate guard: ZERO refusals across the full benign corpus, and the
    accepted count equals the fixture count."""
    pinned, km, sign = signed_publisher
    accepted = 0
    rejected: list[str] = []
    for fixture in _BENIGN_FIXTURES:
        source = fixture.read_text(encoding="utf-8")
        publisher = sign(source)
        try:
            await validate_skill(
                source,
                publisher=publisher,
                pinned_publisher_pubkeys=pinned,
                key_manager=km,
            )
            accepted += 1
        except COValidatorRefusedError:  # pragma: no cover - failure path
            rejected.append(fixture.name)
    assert rejected == []
    assert accepted == 100
