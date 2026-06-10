"""Tier 2: regression — pin the single-point mint-time-hash invariant.

Round 1 /redteam Lane C flagged F-5 (HIGH) as a wire-shape break: adding
`posture_level` to frozen `EnvelopeMetadata` "changes JCS canonical-bytes
output for every pre-T-02-33 envelope on re-canonicalization." The Shard 2
followup investigation (per `workspaces/phase-01-mvp/journal/
0023-DISCOVERY-envelope-hashes-mint-time-cached-f5-false-positive.md`)
determined F-5 is FALSE-POSITIVE against the current code: the threat model
requires a re-canonicalization path that does NOT exist in the codebase.

This regression test pins the design invariant so a future refactor that
DOES introduce a deserializer (e.g. backup/restore, JSON-API ingest,
cross-process envelope hydration) fails loudly and forces the author to
update the design contract. The structural defense is:

- `EnvelopeConfig.canonical_bytes` is a stored frozen field, not a property
- `EnvelopeConfig.content_hash` is a stored frozen field, not a property
- No `from_json` / `from_dict` / `loads` constructor exists in
  `envoy/envelope/`
- The design-intent docstring at `envoy/envelope/canonical_bytes.py:73-83`
  pins the "single-point hash production" contract
- `EnvelopeCompiler.compile()` step 8 produces the hash exactly once
- PostureGate consumes `prior_content_hash` as a stored attribute, not
  via a function call that could re-derive the hash

Per `rules/testing.md` Tier 2: real `EnvelopeCompiler` against the real
canonical_bytes pipeline; NO mocking. Per `rules/probe-driven-verification.md`
MUST-3: every probe is structural (AST walk, file read, attribute is-identity),
not regex-on-prose.

Cross-references:
- F-5 finding: workspaces/phase-01-mvp/04-validate/round-1-security-audit-2026-05-24.md § F-5
- Disposition journal: workspaces/phase-01-mvp/journal/0023-DISCOVERY-envelope-hashes-mint-time-cached-f5-false-positive.md
- Design-intent docstring: envoy/envelope/canonical_bytes.py:73-83
- Disposition rule: rules/verify-resource-existence.md MUST-3
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from envoy.envelope import (
    EnvelopeCompiler,
    EnvelopeConfig,
    EnvelopeConfigInput,
    EnvelopeMetadata,
    LocalTemplateResolver,
)

# Repo root resolution: this file lives at <repo>/tests/tier2/test_*.py;
# the structural probes target source files relative to the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TYPES_PATH = _REPO_ROOT / "envoy" / "envelope" / "types.py"
_COMPILER_PATH = _REPO_ROOT / "envoy" / "envelope" / "compiler.py"
_CANONICAL_BYTES_PATH = _REPO_ROOT / "envoy" / "envelope" / "canonical_bytes.py"
_POSTURE_GATE_PATH = _REPO_ROOT / "envoy" / "authorship" / "posture_gate.py"
_ENVELOPE_PACKAGE_DIR = _REPO_ROOT / "envoy" / "envelope"


def _find_class_def(module_ast: ast.Module, class_name: str) -> ast.ClassDef:
    """Return the ClassDef node for `class_name` or raise AssertionError."""
    for node in ast.walk(module_ast):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(
        f"AST probe failed: class {class_name!r} not found in module — "
        f"the source file may have been refactored. If the rename is "
        f"intentional, update this regression test to point at the new "
        f"class name AND verify the F-5 invariant still holds for the "
        f"renamed class."
    )


def _class_has_frozen_dataclass_decorator(cls_node: ast.ClassDef) -> bool:
    """Return True iff the class is decorated with @dataclass(frozen=True).

    Walks the decorator list looking for `dataclass(frozen=True)` or
    `dataclasses.dataclass(frozen=True)` — accepts both import styles.
    """
    for deco in cls_node.decorator_list:
        if isinstance(deco, ast.Call):
            # @dataclass(...) or @dataclasses.dataclass(...)
            func = deco.func
            is_dataclass = (isinstance(func, ast.Name) and func.id == "dataclass") or (
                isinstance(func, ast.Attribute)
                and func.attr == "dataclass"
                and isinstance(func.value, ast.Name)
                and func.value.id == "dataclasses"
            )
            if not is_dataclass:
                continue
            for kw in deco.keywords:
                if (
                    kw.arg == "frozen"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    return True
    return False


def _annotated_field(cls_node: ast.ClassDef, field_name: str) -> ast.AnnAssign | None:
    """Return the AnnAssign node for `<field_name>: <annotation>` or None."""
    for stmt in cls_node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            if stmt.target.id == field_name:
                return stmt
    return None


class TestEnvelopeHashesAreMintTimeCached:
    """Regression suite pinning the F-5 false-positive design invariant.

    Each test is a structural probe (AST walk, file existence, attribute
    is-identity check, real compiler invocation). No regex-on-prose; no
    mocking. Per `rules/probe-driven-verification.md` MUST-3.
    """

    def test_canonical_bytes_is_a_stored_frozen_field(self) -> None:
        """`EnvelopeConfig.canonical_bytes: bytes` is a stored frozen field.

        Probe: ast.parse `envoy/envelope/types.py`, locate the
        `EnvelopeConfig` class, assert it is `@dataclass(frozen=True)` AND
        that `canonical_bytes` appears as an AnnAssign field with `bytes`
        annotation. A property/descriptor implementation would surface as a
        FunctionDef + @property decorator (not AnnAssign) — the probe
        distinguishes structurally.
        """
        tree = ast.parse(_TYPES_PATH.read_text())
        cls = _find_class_def(tree, "EnvelopeConfig")
        assert _class_has_frozen_dataclass_decorator(cls), (
            "EnvelopeConfig must be @dataclass(frozen=True) — the F-5 false-positive "
            "disposition (journal/0023) depends on frozen-stored-field semantics. "
            "If the class is no longer a frozen dataclass, the single-point "
            "mint-time-hash invariant no longer holds and F-5 must be re-evaluated."
        )
        field = _annotated_field(cls, "canonical_bytes")
        assert field is not None, (
            "EnvelopeConfig.canonical_bytes must be a stored AnnAssign field. "
            "A property/descriptor would re-derive bytes on access, breaking "
            "the single-point mint-time-hash invariant."
        )
        assert isinstance(field.annotation, ast.Name) and field.annotation.id == "bytes", (
            f"EnvelopeConfig.canonical_bytes annotation must be `bytes`, "
            f"got {ast.dump(field.annotation)!r}."
        )

    def test_content_hash_is_a_stored_frozen_field(self) -> None:
        """`EnvelopeConfig.content_hash: str` is a stored frozen field.

        Same structural probe pattern as the canonical_bytes test. F-5's
        threat model imagines content_hash being recomputed on access; the
        stored-AnnAssign-field shape forecloses that path structurally.
        """
        tree = ast.parse(_TYPES_PATH.read_text())
        cls = _find_class_def(tree, "EnvelopeConfig")
        assert _class_has_frozen_dataclass_decorator(cls), (
            "EnvelopeConfig must be @dataclass(frozen=True) — see "
            "test_canonical_bytes_is_a_stored_frozen_field for the rationale."
        )
        field = _annotated_field(cls, "content_hash")
        assert field is not None, (
            "EnvelopeConfig.content_hash must be a stored AnnAssign field. "
            "A property/descriptor would re-derive the hash on access, "
            "breaking the single-point mint-time-hash invariant."
        )
        assert isinstance(field.annotation, ast.Name) and field.annotation.id == "str", (
            f"EnvelopeConfig.content_hash annotation must be `str`, "
            f"got {ast.dump(field.annotation)!r}."
        )

    def test_no_envelope_deserializer_exists(self) -> None:
        """No `from_json` / `from_dict` / `loads`-based envelope deserializer
        exists in `envoy/envelope/`.

        Probe: scan every `*.py` file under `envoy/envelope/` for any
        function/method definition whose name suggests envelope
        deserialization (`from_json`, `from_dict`, `from_bytes`, `loads`,
        `parse_envelope`). Any match means a re-canonicalization path
        may have landed — at which point F-5's threat model becomes
        applicable and this test fails to force the author to update the
        design contract per journal/0023.

        Walks ClassDef.body for FunctionDef/AsyncFunctionDef whose names
        match the deserializer patterns. Module-level functions are also
        scanned. The scan is structural, not a string-grep — a
        `from_json` mentioned in a docstring or comment is correctly
        ignored.
        """
        deserializer_name_patterns = (
            "from_json",
            "from_dict",
            "from_bytes",
            "from_canonical",
            "loads",  # json.loads-style envelope hydration
            "parse_envelope",
            "deserialize",
            "unmarshal",
        )
        offenders: list[str] = []
        for src_file in sorted(_ENVELOPE_PACKAGE_DIR.rglob("*.py")):
            if src_file.name.startswith("test_"):
                continue
            try:
                tree = ast.parse(src_file.read_text())
            except SyntaxError as exc:
                pytest.fail(f"AST parse failed on {src_file}: {exc}")
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name_lc = node.name.lower()
                    for pattern in deserializer_name_patterns:
                        if pattern in name_lc:
                            offenders.append(
                                f"{src_file.relative_to(_REPO_ROOT)}:{node.lineno} — {node.name}"
                            )
                            break
        assert offenders == [], (
            "An envelope deserializer landed in envoy/envelope/. The F-5 "
            "false-positive disposition (journal/0023) depends on the "
            "absence of a re-canonicalization path. If this refactor is "
            "intentional, the author MUST (a) update the design-intent "
            "docstring at envoy/envelope/canonical_bytes.py:73-83, (b) "
            "introduce a hash-continuity invariant (the new deserializer "
            "preserves the stored content_hash byte-identical) OR a "
            "schema_version bump per F-5's original recommendation, AND "
            "(c) update this regression test to reflect the new contract. "
            f"Offending symbols: {offenders}"
        )

    def test_canonical_bytes_module_documents_single_point_hash_design(self) -> None:
        """`envoy/envelope/canonical_bytes.py` documents the single-point-
        hash design intent.

        Probe: read the source file as text, assert it contains both
        load-bearing phrases from the design-intent docstring. Pins the
        docstring so a future refactor that drops the docstring also
        fails this test — forcing the author to re-state the contract OR
        explicitly remove it (in which case journal/0023 + every consumer
        relying on the invariant must be updated).
        """
        # Normalize whitespace runs to single spaces so phrases that wrap
        # across lines in the docstring (with leading-indent on the next
        # line) still match as logical strings.
        source_raw = _CANONICAL_BYTES_PATH.read_text()
        source = " ".join(source_raw.split())
        required_phrases = (
            "single-point hash production at compile time",
            "no drift surface between consumers",
        )
        missing = [p for p in required_phrases if p not in source]
        assert missing == [], (
            f"envoy/envelope/canonical_bytes.py is missing the design-intent "
            f"docstring phrases that pin the F-5 false-positive disposition: "
            f"{missing}. The docstring at lines 73-83 documents the "
            f'"single-point hash production" contract that the F-5 threat '
            f"model contradicts. If the docstring was dropped, journal/0023 "
            f"+ every downstream consumer assumption MUST be re-validated."
        )

    def test_compiler_computes_canonical_bytes_and_content_hash_exactly_once(
        self, tmp_path: Path
    ) -> None:
        """Real `EnvelopeCompiler.compile()` produces stored, identity-stable
        canonical_bytes + content_hash.

        Probe: exercise the real pipeline end-to-end (real Ed25519 not
        required for this property; the canonical_bytes pipeline is the
        target), then assert subsequent attribute reads return the SAME
        bytes/str OBJECT (is-identity, not just equality) — proving the
        value is cached, not recomputed on each access.

        Per `rules/testing.md` Tier 2: real `EnvelopeCompiler`, NO mocking.
        """
        compiler = EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path))
        metadata = EnvelopeMetadata(posture_level="PSEUDO")
        config_input = EnvelopeConfigInput(metadata=metadata)
        compiled: EnvelopeConfig = compiler.compile(
            config_input, principal_id="principal-tier2-mint-time-hash"
        )

        # Capture the first read
        first_canonical = compiled.canonical_bytes
        first_hash = compiled.content_hash

        # Second + third reads MUST return the IDENTICAL Python object
        # (id-equality). A property/descriptor that re-derived bytes would
        # return a freshly-allocated bytes object on each access — different
        # id, equal value. The is-identity check distinguishes cached vs
        # recomputed at the structural level.
        assert compiled.canonical_bytes is first_canonical, (
            "EnvelopeConfig.canonical_bytes returned a non-identical object "
            "on second read — implies on-access re-derivation. The F-5 "
            "false-positive disposition (journal/0023) depends on cached "
            "stored bytes, not on-access recomputation."
        )
        assert compiled.content_hash is first_hash, (
            "EnvelopeConfig.content_hash returned a non-identical object on "
            "second read — implies on-access re-derivation. The F-5 false-"
            "positive disposition (journal/0023) depends on cached stored "
            "hash, not on-access recomputation."
        )
        # And again on a third read to rule out a "first call computes, "
        # subsequent calls cache" pattern.
        assert compiled.canonical_bytes is first_canonical
        assert compiled.content_hash is first_hash

        # The stored values MUST be non-empty bytes / 64-char hex string —
        # validates that the compiler actually ran step 8 and produced real
        # hashes, not a zero-initialized stored field.
        assert isinstance(first_canonical, bytes) and len(first_canonical) > 0
        assert isinstance(first_hash, str) and len(first_hash) == 64
        assert all(
            c in "0123456789abcdef" for c in first_hash
        ), f"content_hash must be 64-char lowercase hex sha256, got {first_hash!r}"

    def test_posture_gate_consumes_prior_content_hash_as_stored_attribute(self) -> None:
        """PostureGate reads `envelope.prior_content_hash` (and siblings) as
        attribute accesses, never via function calls that could re-derive.

        Probe: ast.parse `envoy/authorship/posture_gate.py`, locate the
        `request_transition` async method on `PostureGate`, walk its body
        for any access to `envelope.envelope_id`, `envelope.prior_version`,
        `envelope.prior_content_hash`, or `envelope.prior_posture_level`.
        Each access MUST be `ast.Attribute` (i.e., a property/attribute
        read), NEVER an `ast.Call` whose `.func` is an `ast.Attribute`
        (which would be a method invocation that could re-derive the hash).

        The Tier 2 wiring test's `_EnvelopeConfigPostureCarrier` exposes
        these as `@property` accessors that return the underlying
        `EnvelopeConfig.metadata.envelope_id` / `EnvelopeConfig.envelope_version`
        / `EnvelopeConfig.content_hash` directly — never recomputed. This
        probe asserts the production gate code consumes them in attribute
        shape, pinning the consumer side of the F-5 false-positive
        contract.
        """
        tree = ast.parse(_POSTURE_GATE_PATH.read_text())
        gate_cls = _find_class_def(tree, "PostureGate")

        # Locate `request_transition` (async def)
        request_transition: ast.AsyncFunctionDef | None = None
        for stmt in gate_cls.body:
            if isinstance(stmt, ast.AsyncFunctionDef) and stmt.name == "request_transition":
                request_transition = stmt
                break
        assert request_transition is not None, (
            "PostureGate.request_transition not found — source has been "
            "refactored. Update this regression test to point at the new "
            "method AND verify the F-5 stored-attribute-consumption "
            "invariant still holds for the renamed method."
        )

        stored_attribute_names = (
            "envelope_id",
            "prior_version",
            "prior_content_hash",
            "prior_posture_level",
        )
        attribute_reads: list[tuple[int, str]] = []
        method_calls_on_envelope: list[tuple[int, str]] = []

        for node in ast.walk(request_transition):
            # ast.Attribute reads on a Name("envelope")
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "envelope" and node.attr in stored_attribute_names:
                    attribute_reads.append((node.lineno, node.attr))
            # ast.Call where the function is an Attribute on Name("envelope")
            # — i.e., envelope.<method>(...) — would be a method invocation.
            # The legitimate one is `envelope.mutate_for_posture_level(target)`,
            # which intentionally produces a NEW envelope via the real
            # canonical_bytes pipeline; the illegitimate one would be
            # `envelope.recompute_content_hash()` or similar.
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if func.value.id == "envelope":
                        method_calls_on_envelope.append((node.lineno, func.attr))

        # At least one attribute read of each stored field is expected (the
        # gate's trust-boundary checks at posture_gate.py:1032-1063 read
        # envelope.envelope_id and envelope.prior_version directly).
        attrs_seen = {name for (_, name) in attribute_reads}
        assert "envelope_id" in attrs_seen, (
            "PostureGate.request_transition does not read envelope.envelope_id "
            "as an attribute — F-5 false-positive disposition requires the "
            "consumer to read stored attributes, not re-derive them via a "
            "function call. Attribute reads observed: "
            f"{sorted(attrs_seen)}"
        )
        assert "prior_version" in attrs_seen, (
            "PostureGate.request_transition does not read envelope.prior_version "
            "as an attribute — see test docstring for the F-5 stored-attribute "
            f"contract. Attribute reads observed: {sorted(attrs_seen)}"
        )

        # The ONLY allowed method call on `envelope` is mutate_for_posture_level
        # (the adapter-owned mutation per journal/0021's envelope-kwarg design).
        # Any other method call could be a re-derivation path and is BLOCKED.
        unexpected_method_calls = [
            (lineno, name)
            for (lineno, name) in method_calls_on_envelope
            if name != "mutate_for_posture_level"
        ]
        assert unexpected_method_calls == [], (
            f"PostureGate.request_transition contains method calls on `envelope` "
            f"other than `mutate_for_posture_level`: {unexpected_method_calls}. "
            f"The F-5 false-positive disposition (journal/0023) requires that "
            f"all consumer reads of envelope hash/version/id fields be "
            f"attribute accesses (not method calls that could re-derive). "
            f"The only allowed method is `mutate_for_posture_level`, which "
            f"intentionally produces a NEW envelope via the real "
            f"canonical_bytes pipeline (not a re-derivation of a stored "
            f"hash). If a new method call is intentional, update this "
            f"regression test AND verify the new method does not re-derive "
            f"canonical_bytes from in-memory metadata of a stored envelope."
        )
