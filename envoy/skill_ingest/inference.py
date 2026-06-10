# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.skill_ingest.inference — conservative AST permission-inference walk.

`specs/skill-ingest.md` CO validator step 3 ("Declared = inferred; code
analysis"). This is the LOAD-BEARING asymmetric-routing design: a CONSERVATIVE
Python `ast` static walk that infers the permissions a skill's inline code
ACTUALLY reaches, split into two tiers:

  1. **Literal-call evidence** (high confidence) — a call whose target + literal
     args prove a capability reach: `subprocess.*` / `os.system` → bash/exec;
     `open(..., "w"/"a"/"x")` → file-write, read-modes → file-read;
     `requests.post` / `httpx.post` with a literal URL → http-post:<host>.
     A LITERAL dynamic-dispatch construct (`getattr` / `eval` / `exec` /
     `importlib.import_module` CALL SITE) is itself flagged as an
     undeclared-capability reach — the construct is visible in the AST.

  2. **Import-graph second opinion** (low confidence) — an import of a
     capability-bearing module (`subprocess`, `requests`, `socket`, ...) that is
     NOT covered by a literal-call match. This can ONLY raise a WARNING, never
     an AST-proven reject.

The asymmetry is the whole point: a LITERAL undeclared call (the AST PROVES the
reach) routes to score < 0.5 → REJECT; an import-graph-only extra (the AST sees
the import but no literal call confirming the reach) routes to the warning band
→ pass-WITH-WARNING.

Security (`rules/security.md`): static analysis ONLY. The validator NEVER
`eval`s, `exec`s, `compile`-and-runs, or `import`s the fixture code. It parses
to an `ast` tree and walks nodes. Unparseable code is fail-closed — the caller
surfaces `SkillCodeUnparseableError` rather than silently passing un-analyzed
code.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from envoy.skill_ingest.errors import SkillCodeUnparseableError

# Modules whose mere import signals a capability-bearing dependency. An import
# of one of these that is NOT confirmed by a literal call is the import-graph
# second opinion (WARNING-only, never auto-reject).
_CAPABILITY_MODULES: dict[str, str] = {
    "subprocess": "bash",
    "os": "bash",  # os.system / os.popen — import-graph signal for shell exec
    "requests": "http-post",
    "httpx": "http-post",
    "urllib": "http-post",
    "socket": "http-post",
    "shutil": "file-write",
    "pathlib": "file-write",
    "ftplib": "http-post",
    "smtplib": "http-post",
}

# Dynamic-dispatch call targets. A LITERAL call site to any of these is an
# undeclared-capability reach by construction — the skill is using runtime
# dispatch the static declared-permission set cannot bound.
_DYNAMIC_DISPATCH_CALLS: frozenset[str] = frozenset(
    {"getattr", "eval", "exec", "compile", "__import__"}
)
# importlib.import_module is the dotted-form dynamic dispatch.
_IMPORTLIB_DYNAMIC: frozenset[str] = frozenset({"import_module", "__import__"})

_WRITE_MODES: frozenset[str] = frozenset({"w", "a", "x", "w+", "a+", "x+", "wb", "ab", "xb"})


@dataclass(frozen=True, slots=True)
class InferredCapability:
    """One inferred capability reach.

    `category` is the permission category (`bash`, `exec`, `file-read`,
    `file-write`, `http-post`); `scope` is the literal scope when derivable (a
    host for http-post, ``*`` otherwise). `literal` distinguishes AST-PROVEN
    literal-call evidence (True) from import-graph-only second opinions (False).
    `evidence` is a short human-readable note (the call shape that produced it).
    `dynamic_dispatch` flags a literal dynamic-dispatch construct (getattr/eval/
    importlib) — these are always literal + always undeclared-capability reaches.
    """

    category: str
    scope: str
    literal: bool
    evidence: str
    dynamic_dispatch: bool = False

    @property
    def pattern(self) -> str:
        """The `<category>:<scope>` permission pattern this reach implies."""
        return f"{self.category}:{self.scope}"


@dataclass(slots=True)
class InferredPermissionSet:
    """The full result of the inference walk over a skill's inline code.

    `literal_calls` are the AST-PROVEN capability reaches (drive the <0.5
    reject decision when undeclared). `import_graph` are the WARNING-only
    second-opinion reaches. `dynamic_dispatch` are the literal getattr/eval/
    importlib call sites (a non-empty set is itself an AST-visible
    undeclared-capability reach per the spec).
    """

    literal_calls: list[InferredCapability] = field(default_factory=list)
    import_graph: list[InferredCapability] = field(default_factory=list)
    dynamic_dispatch: list[InferredCapability] = field(default_factory=list)

    @property
    def literal_patterns(self) -> set[str]:
        """The set of `<category>:<scope>` patterns proven by literal calls.

        Includes dynamic-dispatch constructs — they are literal, AST-visible
        capability reaches.
        """
        out = {c.pattern for c in self.literal_calls}
        out |= {c.pattern for c in self.dynamic_dispatch}
        return out

    @property
    def literal_categories(self) -> set[str]:
        """The set of permission CATEGORIES proven by literal calls."""
        out = {c.category for c in self.literal_calls}
        out |= {c.category for c in self.dynamic_dispatch}
        return out

    @property
    def import_categories(self) -> set[str]:
        """The set of permission CATEGORIES seen in the import graph."""
        return {c.category for c in self.import_graph}


def infer_permissions(skill_code: str) -> InferredPermissionSet:
    """Conservatively infer the permissions a skill's inline code reaches.

    Args:
        skill_code: The concatenated inline Python code blocks from the SKILL.md.
            An EMPTY string is valid (a skill with no inline code reaches no
            capability) — returns an empty `InferredPermissionSet`.

    Returns:
        An `InferredPermissionSet` partitioned into literal-call evidence
        (AST-proven), import-graph second opinions (warning-only), and
        literal dynamic-dispatch constructs.

    Raises:
        SkillCodeUnparseableError: `ast.parse` fails. Fail-closed
            (`rules/security.md`) — the validator surfaces this rather than
            silently passing un-analyzable code. The code is NEVER executed;
            only `ast.parse` (a static parse) is attempted.
    """
    if not skill_code.strip():
        return InferredPermissionSet()

    try:
        tree = ast.parse(skill_code)
    except SyntaxError as exc:
        raise SkillCodeUnparseableError(
            f"SKILL.md inline code is not parseable Python (line {exc.lineno}): "
            f"{exc.msg}; refusing to pass un-analyzable code (fail-closed)"
        ) from exc

    walker = _InferenceWalker()
    walker.visit(tree)
    return walker.result


class _InferenceWalker(ast.NodeVisitor):
    """Walks the AST collecting literal-call + import-graph + dynamic-dispatch
    capability evidence. Pure static traversal — no node is ever executed."""

    def __init__(self) -> None:
        self.result = InferredPermissionSet()

    # --- import graph (second opinion) -----------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            self._note_capability_import(top, f"import {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            top = node.module.split(".")[0]
            self._note_capability_import(top, f"from {node.module} import ...")
        self.generic_visit(node)

    def _note_capability_import(self, top_module: str, evidence: str) -> None:
        category = _CAPABILITY_MODULES.get(top_module)
        if category is not None:
            self.result.import_graph.append(
                InferredCapability(
                    category=category,
                    scope="*",
                    literal=False,
                    evidence=evidence,
                )
            )

    # --- literal calls (AST-proven evidence) -----------------------------

    def visit_Call(self, node: ast.Call) -> None:
        self._inspect_call(node)
        self.generic_visit(node)

    def _inspect_call(self, node: ast.Call) -> None:
        func = node.func

        # Bare-name calls: getattr/eval/exec/compile/__import__/open.
        if isinstance(func, ast.Name):
            name = func.id
            if name in _DYNAMIC_DISPATCH_CALLS:
                self._note_dynamic_dispatch(name)
                return
            if name == "open":
                self._note_open_call(node)
                return
            return

        # Attribute calls: subprocess.run, os.system, requests.post,
        # importlib.import_module, etc.
        if isinstance(func, ast.Attribute):
            self._inspect_attribute_call(func, node)
            return

    def _inspect_attribute_call(self, func: ast.Attribute, node: ast.Call) -> None:
        attr = func.attr
        root = _attribute_root(func)

        # importlib.import_module(...) / importlib.__import__(...) — literal
        # dynamic dispatch.
        if root == "importlib" and attr in _IMPORTLIB_DYNAMIC:
            self._note_dynamic_dispatch(f"importlib.{attr}")
            return

        # subprocess.* → bash (the subprocess module IS the shell-exec surface).
        if root == "subprocess":
            self.result.literal_calls.append(
                InferredCapability(
                    category="bash",
                    scope="*",
                    literal=True,
                    evidence=f"subprocess.{attr}(...)",
                )
            )
            return

        # os.system / os.popen / os.exec* → exec (direct process exec surface).
        if root == "os" and (attr == "system" or attr == "popen" or attr.startswith("exec")):
            self.result.literal_calls.append(
                InferredCapability(
                    category="exec",
                    scope="*",
                    literal=True,
                    evidence=f"os.{attr}(...)",
                )
            )
            return

        # requests/httpx/urllib .post/.get/.put/.patch/.delete → http-* with a
        # literal host when the first arg is a literal URL.
        if root in ("requests", "httpx") or attr in ("urlopen",):
            if attr in ("post", "put", "patch", "delete"):
                self._note_http_call("http-post", node, f"{root}.{attr}(...)")
                return
            if attr == "get" or attr == "urlopen":
                self._note_http_call("http-get", node, f"{root}.{attr}(...)")
                return

        # <file>.write(...) is NOT a reliable file-write signal (could be any
        # object); file-write is inferred from the open(..., mode) call instead.

    def _note_open_call(self, node: ast.Call) -> None:
        """`open(path, mode)` — file-write if mode is a write-mode literal,
        else file-read. A non-literal mode defaults to file-read (the
        conservative read-only assumption); a write reach requires a LITERAL
        write-mode so we never over-claim file-write on an ambiguous mode."""
        mode = _literal_open_mode(node)
        if mode is not None and any(m in _WRITE_MODES for m in (mode,)):
            self.result.literal_calls.append(
                InferredCapability(
                    category="file-write",
                    scope="*",
                    literal=True,
                    evidence=f"open(..., {mode!r})",
                )
            )
        else:
            self.result.literal_calls.append(
                InferredCapability(
                    category="file-read",
                    scope="*",
                    literal=True,
                    evidence="open(...)",
                )
            )

    def _note_http_call(self, category: str, node: ast.Call, evidence: str) -> None:
        host = _literal_url_host(node)
        scope = host if host is not None else "*"
        self.result.literal_calls.append(
            InferredCapability(
                category=category,
                scope=scope,
                literal=True,
                evidence=evidence,
            )
        )

    def _note_dynamic_dispatch(self, name: str) -> None:
        self.result.dynamic_dispatch.append(
            InferredCapability(
                category="dynamic-dispatch",
                scope=name,
                literal=True,
                evidence=f"{name}(...) — runtime dispatch visible in AST",
                dynamic_dispatch=True,
            )
        )


def _attribute_root(func: ast.Attribute) -> str | None:
    """The leftmost Name of a (possibly dotted) attribute chain.

    ``subprocess.run`` → ``subprocess``; ``os.path.join`` → ``os``; a chain
    rooted in a non-Name (e.g. ``obj().attr``) → None.
    """
    cur: ast.expr = func
    while isinstance(cur, ast.Attribute):
        cur = cur.value
    if isinstance(cur, ast.Name):
        return cur.id
    return None


def _literal_open_mode(node: ast.Call) -> str | None:
    """The literal mode string passed to ``open`` — positional arg 1 or the
    ``mode=`` kwarg. Returns None when the mode is absent or non-literal."""
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        value = node.args[1].value
        if isinstance(value, str):
            return value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            value = kw.value.value
            if isinstance(value, str):
                return value
    return None


def _literal_url_host(node: ast.Call) -> str | None:
    """Extract the host from a literal URL passed as the first positional arg
    (or a ``url=`` kwarg). Returns None when the URL is non-literal."""
    from urllib.parse import urlparse  # noqa: PLC0415 — local, static-analysis only

    url_value: str | None = None
    if node.args and isinstance(node.args[0], ast.Constant):
        value = node.args[0].value
        if isinstance(value, str):
            url_value = value
    if url_value is None:
        for kw in node.keywords:
            if kw.arg == "url" and isinstance(kw.value, ast.Constant):
                value = kw.value.value
                if isinstance(value, str):
                    url_value = value
                    break
    if url_value is None:
        return None
    parsed = urlparse(url_value)
    return parsed.hostname or None


__all__ = [
    "InferredCapability",
    "InferredPermissionSet",
    "infer_permissions",
]
