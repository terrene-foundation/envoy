# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S8.7 — exactly ONE `verify_steward_quorum` definition in the tree.

The WS-4 deep-dive (`01-analysis/01-research/04-ws4-library-skill-ingest.md`
§ 2.2 + gap #1 + § 4.5 cross-cut) mandates a SINGLE 2-of-N steward-quorum
verifier reused by the Envelope Library FV resolver (S8), the EDR verifier
(S8e), and the classifier registry resolver (S9b). No shard may grow a parallel
verifier.

This gate is STRUCTURAL (AST `FunctionDef`/`AsyncFunctionDef` enumeration per
`rules/testing.md` § structural enumeration, NOT grep) so a docstring mention of
`def verify_steward_quorum(` does not inflate the count — only a real definition
does. It walks the whole `envoy/` package tree so a future S8e/S9b shard that
re-implements the verifier fails here loudly.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ENVOY_ROOT = Path(__file__).resolve().parents[2] / "envoy"


def _count_quorum_defs() -> list[str]:
    """Return `<file>:<lineno>` for every real (Async)FunctionDef named
    `verify_steward_quorum` in the envoy package."""
    hits: list[str] = []
    for py in _ENVOY_ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "verify_steward_quorum"
            ):
                hits.append(f"{py.relative_to(_ENVOY_ROOT.parent)}:{node.lineno}")
    return hits


def test_exactly_one_verify_steward_quorum_definition() -> None:
    hits = _count_quorum_defs()
    assert len(hits) == 1, (
        f"verify_steward_quorum must be defined EXACTLY once (the shared "
        f"primitive); found {len(hits)}: {hits}. A second definition means a "
        f"shard grew a parallel verifier — consolidate to "
        f"envoy/registry/steward_quorum.py."
    )
    assert hits[0].startswith("envoy/registry/steward_quorum.py")
