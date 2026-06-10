# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.skill_ingest.skill_md — the SKILL.md canonical-format parser.

`specs/skill-ingest.md` § SKILL.md parser: "Parses the external ecosystem's
canonical format: name, version, description, permissions array, inline code
blocks."

The canonical SKILL.md format is a YAML-frontmatter markdown document:

    ---
    name: my-skill
    version: 1.2.0
    description: Does a thing.
    permissions:
      - file-read:*
      - http-post:api.example.com
    ---

    # My Skill

    ```python
    import requests
    requests.post("https://api.example.com/ingest", json={...})
    ```

The parser extracts the four declared fields + every fenced ``python`` code
block (the inline code the CO validator's AST walk analyzes). It is pure-function
+ fail-closed: a missing required field, malformed frontmatter, or a malformed
``permissions`` array raises `SkillManifestParseError` — never a silent default.

The parser does NOT execute or import the code blocks — it only captures them as
source strings for the static `ast`-based inference walk (`rules/security.md`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

from envoy.skill_ingest.errors import SkillManifestParseError

# Frontmatter is the leading ``---``-delimited YAML block. ``re.DOTALL`` so the
# body spans newlines; non-greedy so the FIRST closing ``---`` ends the block.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<yaml>.*?)\n---\s*\n?(?P<body>.*)\Z", re.DOTALL)

# Fenced code blocks tagged ``python`` (or ``py``). The CO validator only
# analyzes Python — a non-Python fence is captured-but-ignored by the inference
# walk (it cannot be ast.parse'd as Python and is not declared analyzable).
_PYTHON_FENCE_RE = re.compile(
    r"^```(?:python|py)[ \t]*\n(?P<code>.*?)\n```[ \t]*$",
    re.DOTALL | re.MULTILINE,
)

_REQUIRED_FIELDS = ("name", "version", "description")


@dataclass(frozen=True, slots=True)
class SkillManifest:
    """Parsed SKILL.md — the four declared fields + the inline code blocks.

    `code_blocks` is the ordered tuple of ``python``-fenced source strings; the
    CO validator concatenates them for the single `ast` walk (each block is an
    independent module-scope snippet).
    """

    name: str
    version: str
    description: str
    declared_permissions: tuple[str, ...]
    code_blocks: tuple[str, ...]
    body: str

    @property
    def joined_code(self) -> str:
        """All inline code blocks joined into one analyzable source string.

        Two newlines between blocks so each block keeps its own module-scope
        statements without accidental line-continuation across the join.
        """
        return "\n\n".join(self.code_blocks)


def parse_skill_md(text: str) -> SkillManifest:
    """Parse a canonical SKILL.md document into a `SkillManifest`.

    Args:
        text: The raw SKILL.md document bytes decoded as UTF-8 text.

    Returns:
        A `SkillManifest` with the four declared fields, the declared-permission
        tuple, and every ``python``-fenced inline code block.

    Raises:
        SkillManifestParseError: missing/empty frontmatter, malformed YAML, a
            missing required field (name/version/description), a non-string
            scalar field, or a malformed ``permissions`` array (not a list, or
            a non-string entry). Fail-closed — never returns a defaulted field.
    """
    if not isinstance(text, str):
        raise SkillManifestParseError(f"SKILL.md source must be str, got {type(text).__name__}")

    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise SkillManifestParseError(
            "SKILL.md missing YAML frontmatter (expected a leading '---' "
            "delimited block); cannot extract name/version/description/permissions"
        )

    raw_yaml = match.group("yaml")
    body = match.group("body")

    try:
        meta = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:  # malformed frontmatter — fail closed
        raise SkillManifestParseError(f"SKILL.md frontmatter is not valid YAML: {exc}") from exc

    if not isinstance(meta, dict):
        raise SkillManifestParseError(
            "SKILL.md frontmatter must be a YAML mapping of fields, got " f"{type(meta).__name__}"
        )

    fields: dict[str, str] = {}
    for key in _REQUIRED_FIELDS:
        if key not in meta:
            raise SkillManifestParseError(f"SKILL.md frontmatter missing required field {key!r}")
        value = meta[key]
        if not isinstance(value, str) or not value.strip():
            raise SkillManifestParseError(
                f"SKILL.md field {key!r} must be a non-empty string, got " f"{type(value).__name__}"
            )
        fields[key] = value

    declared_permissions = _parse_permissions(meta.get("permissions", []))
    code_blocks = tuple(m.group("code") for m in _PYTHON_FENCE_RE.finditer(body))

    return SkillManifest(
        name=fields["name"],
        version=fields["version"],
        description=fields["description"],
        declared_permissions=declared_permissions,
        code_blocks=code_blocks,
        body=body,
    )


def _parse_permissions(raw: object) -> tuple[str, ...]:
    """Validate + normalize the declared ``permissions`` array.

    The array is OPTIONAL (a skill may declare zero permissions), but when
    present it MUST be a list of non-empty strings. Anything else is a
    `SkillManifestParseError` (a malformed permissions array per the spec's
    `SkillManifestParseError` trigger row).
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise SkillManifestParseError(
            f"SKILL.md 'permissions' must be a YAML list, got {type(raw).__name__}"
        )
    out: list[str] = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            raise SkillManifestParseError(
                f"SKILL.md 'permissions' entries must be non-empty strings, got " f"{entry!r}"
            )
        out.append(entry.strip())
    return tuple(out)


__all__ = ["SkillManifest", "parse_skill_md"]
