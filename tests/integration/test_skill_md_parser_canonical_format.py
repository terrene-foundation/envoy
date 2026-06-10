# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SKILL.md canonical-format parser round-trip (`specs/skill-ingest.md`).

Tier-2 per the spec's test-location table. The parser reads the external
ecosystem's canonical SKILL.md format (YAML frontmatter: name/version/
description/permissions array + fenced inline code blocks) and the test asserts
every field round-trips, plus the fail-closed parse errors.

Structural asserts only — parsed field values + raised type.
"""

from __future__ import annotations

import pytest

from envoy.skill_ingest import SkillManifestParseError, parse_skill_md

_CANONICAL = """---
name: data-pipeline
version: 2.3.1
description: Ingests and transforms data.
permissions:
  - file-read:*
  - file-write:/tmp/out
  - http-post:api.example.com
---

# Data Pipeline

Some prose.

```python
import requests
data = open("in.csv").read()
requests.post("https://api.example.com/ingest", data=data)
```

More prose.

```python
with open("/tmp/out/result.json", "w") as f:
    f.write("{}")
```
"""


class TestCanonicalParse:
    def test_declared_fields_round_trip(self) -> None:
        manifest = parse_skill_md(_CANONICAL)
        assert manifest.name == "data-pipeline"
        assert manifest.version == "2.3.1"
        assert manifest.description == "Ingests and transforms data."

    def test_permissions_array_round_trips_in_order(self) -> None:
        manifest = parse_skill_md(_CANONICAL)
        assert manifest.declared_permissions == (
            "file-read:*",
            "file-write:/tmp/out",
            "http-post:api.example.com",
        )

    def test_every_python_code_block_captured(self) -> None:
        manifest = parse_skill_md(_CANONICAL)
        assert len(manifest.code_blocks) == 2
        assert "requests.post" in manifest.code_blocks[0]
        assert 'open("/tmp/out/result.json", "w")' in manifest.code_blocks[1]

    def test_joined_code_contains_both_blocks(self) -> None:
        manifest = parse_skill_md(_CANONICAL)
        joined = manifest.joined_code
        assert "requests.post" in joined
        assert "result.json" in joined


class TestParserEdgeCases:
    def test_empty_permissions_array_is_empty_tuple(self) -> None:
        source = "---\nname: n\nversion: 1.0.0\ndescription: d\npermissions: []\n---\n\n# n\n"
        manifest = parse_skill_md(source)
        assert manifest.declared_permissions == ()

    def test_omitted_permissions_is_empty_tuple(self) -> None:
        source = "---\nname: n\nversion: 1.0.0\ndescription: d\n---\n\n# n\n"
        manifest = parse_skill_md(source)
        assert manifest.declared_permissions == ()

    def test_no_code_blocks_is_empty_tuple(self) -> None:
        source = "---\nname: n\nversion: 1.0.0\ndescription: d\n---\n\n# n\n\nProse only.\n"
        manifest = parse_skill_md(source)
        assert manifest.code_blocks == ()


class TestParserFailClosed:
    def test_missing_frontmatter_raises(self) -> None:
        with pytest.raises(SkillManifestParseError):
            parse_skill_md("# just a heading, no frontmatter\n")

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(SkillManifestParseError):
            parse_skill_md("---\nname: n\nversion: 1.0.0\n---\n\n# n\n")

    def test_malformed_permissions_not_a_list_raises(self) -> None:
        source = (
            "---\nname: n\nversion: 1.0.0\ndescription: d\npermissions: not-a-list\n---\n\n# n\n"
        )
        with pytest.raises(SkillManifestParseError):
            parse_skill_md(source)

    def test_non_string_permission_entry_raises(self) -> None:
        source = (
            "---\nname: n\nversion: 1.0.0\ndescription: d\n" "permissions:\n  - 42\n---\n\n# n\n"
        )
        with pytest.raises(SkillManifestParseError):
            parse_skill_md(source)
