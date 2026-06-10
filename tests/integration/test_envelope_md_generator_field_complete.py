# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ENVELOPE.md generator field-completeness (`specs/skill-ingest.md`).

Tier-2 per the spec's test-location table: every field in
`{skill_id, skill_source_hash, publisher, requested_permissions,
co_validator_result}` is populated. Real `InMemoryKeyManager` (no mock); the
companion is produced end-to-end via the CO validator pipeline.

Structural asserts only — field presence + shape + YAML round-trip.
"""

from __future__ import annotations

import pytest
import yaml
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.skill_ingest import (
    PublisherRef,
    compute_skill_source_hash,
    validate_skill,
)

_GENESIS = "genesis:envelope-publisher"

_SOURCE = """---
name: envelope-skill
version: 1.4.0
description: Exercises every requested-permission axis.
permissions:
  - file-read:*
  - file-write:/tmp/x
  - http-post:api.example.com
  - oauth:github
---

# Envelope Skill

```python
import requests
data = open("in.txt").read()
with open("/tmp/x/out.txt", "w") as f:
    f.write(data)
requests.post("https://api.example.com/x", data=data)
```
"""


@pytest.fixture
async def companion():
    """Run the full pipeline and yield the generated ENVELOPE.md companion."""
    km = InMemoryKeyManager()
    _priv, pub = await km.generate_keypair("envelope")
    digest = compute_skill_source_hash(_SOURCE)
    signature = km.sign_with_key("envelope", digest.encode("utf-8"))
    publisher = PublisherRef(genesis_id=_GENESIS, signature=signature)
    result = await validate_skill(
        _SOURCE,
        publisher=publisher,
        pinned_publisher_pubkeys={_GENESIS: pub},
        key_manager=km,
    )
    return result.companion


class TestEnvelopeFieldCompleteness:
    async def test_skill_id_populated(self, companion) -> None:
        assert companion.skill_id == "envelope-skill@1.4.0"

    async def test_skill_source_hash_populated(self, companion) -> None:
        assert companion.skill_source_hash == compute_skill_source_hash(_SOURCE)
        # sha256 hex is 64 chars.
        assert len(companion.skill_source_hash) == 64

    async def test_publisher_block_populated(self, companion) -> None:
        assert companion.publisher.genesis_id == _GENESIS
        assert companion.publisher.signature  # non-empty hex signature

    async def test_requested_permissions_has_all_five_axes(self, companion) -> None:
        axes = companion.requested_permissions
        for axis in (
            "financial",
            "operational",
            "temporal",
            "data_access",
            "communication",
        ):
            assert axis in axes  # every axis present (financial/temporal empty)

    async def test_requested_permissions_routed_correctly(self, companion) -> None:
        axes = companion.requested_permissions
        # file-read → data_access; file-write + oauth → operational;
        # http-post → communication.
        assert "file-read:*" in axes["data_access"]
        assert "file-write:/tmp/x" in axes["operational"]
        assert "oauth:github" in axes["operational"]
        assert "http-post:api.example.com" in axes["communication"]

    async def test_co_validator_result_block_populated(self, companion) -> None:
        cvr = companion.co_validator_result
        assert isinstance(cvr.passed, bool)
        assert isinstance(cvr.score, float)
        assert isinstance(cvr.warnings, tuple)
        assert isinstance(cvr.errors, tuple)


class TestEnvelopeYamlRoundTrip:
    async def test_to_yaml_is_valid_and_field_complete(self, companion) -> None:
        rendered = companion.to_yaml()
        parsed = yaml.safe_load(rendered)
        # Every top-level spec field present in the serialised companion.
        assert parsed["skill_id"] == "envelope-skill@1.4.0"
        assert parsed["skill_source_hash"]
        assert parsed["publisher"]["genesis_id"] == _GENESIS
        assert parsed["publisher"]["signature"]
        assert set(parsed["requested_permissions"]) == {
            "financial",
            "operational",
            "temporal",
            "data_access",
            "communication",
        }
        assert set(parsed["co_validator_result"]) == {
            "passed",
            "score",
            "warnings",
            "errors",
        }
