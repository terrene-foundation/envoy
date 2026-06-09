# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.contract_tier — machine-readable contract-tier metadata.

Source of truth: `specs/runtime-abstraction.md` § Contract partition (BET-6).

The BET-6 cross-runtime conformance harness (`tests/conformance/`) must pick the
right scorer per Protocol method: a **byte-identical** method is scored by
hash-equality of canonical output across runtimes; a **semantically-equivalent**
method is scored by an LLM-judge probe (Phase-03). The harness MUST learn each
method's tier *programmatically* — a hand-maintained method→tier map drifts the
moment a method is added without updating the map (Spec-gap-2,
`workspaces/phase-02-distribution/01-analysis/01-research/01-ws1-runtime-pluggability.md`
§ Gap 2).

This module provides method-co-located decorators (`@byte_identical`,
`@semantically_equivalent`) that stamp a `__contract_tier__` attribute onto the
Protocol method. `tier_of()` reads it back; `assert_all_methods_tagged()` is the
authoring-time gate — a Protocol method missing its tier decorator fails loudly
(`MissingContractTierError`) instead of silently defaulting, so adding a method
without a tier is a loud authoring error (S1 acceptance criterion 1).

Per-field tier (Spec-gap-3): N3 and N4 are mixed-tier *within* one vector — N3's
structural slice is byte-identical, its semantic slice dispatches the classifier;
N4's structured payload is byte-identical, its rendered verdict TEXT is
semantically-equivalent (DEFERRED to Phase-03 per `runtime-abstraction.md:152`).
A single per-method tier cannot express this, so the corpus row schema (consumed
by the harness in `tests/conformance/`) carries an OPTIONAL per-field
`field_tiers` map; `ContractTier` is the shared enum both the method decorator
and the per-field tag use.
"""

from __future__ import annotations

import enum
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable[..., object])

#: The attribute name stamped onto a decorated Protocol method.
CONTRACT_TIER_ATTR = "__contract_tier__"


class ContractTier(enum.Enum):
    """The two conformance tiers per `specs/runtime-abstraction.md` § Contract
    partition (BET-6).

    - ``BYTE_IDENTICAL`` — output hashes equal across runtimes (hash-equality
      scorer; the live deterministic loop). E1–E7 + N1–N6-structured.
    - ``SEMANTICALLY_EQUIVALENT`` — output is equivalent but not byte-equal
      (LLM-judge probe scorer; Phase-03). The ONLY Phase-02 semantic slice is
      N4's rendered verdict TEXT, which is DEFERRED to Phase-03; the
      ``grant_moment_surface`` rendered text is the method that carries it.
    """

    BYTE_IDENTICAL = "byte_identical"
    SEMANTICALLY_EQUIVALENT = "semantically_equivalent"


class MissingContractTierError(TypeError):
    """A Protocol method was declared without a contract-tier decorator.

    Raised at authoring time by `assert_all_methods_tagged()`. The message names
    the offending method so the fix is a one-line decorator addition — there is
    NO silent default tier (defaulting to byte_identical would weaken a security
    gate by scoring a semantic method with the wrong scorer; defaulting to
    semantic would skip the byte-identity gate entirely).
    """


def byte_identical(fn: F) -> F:
    """Mark a Protocol method as ``BYTE_IDENTICAL`` (hash-equality scored).

    Output MUST hash-equal across `kailash-py` and `kailash-rs-bindings`. Demoting
    a byte-identical method to semantic is BLOCKED (`zero-tolerance.md` Rule 4):
    it weakens a security gate by allowing a runtime to produce *equivalent* but
    not *identical* crypto/canonical output.
    """
    setattr(fn, CONTRACT_TIER_ATTR, ContractTier.BYTE_IDENTICAL)
    return fn


def semantically_equivalent(fn: F) -> F:
    """Mark a Protocol method as ``SEMANTICALLY_EQUIVALENT`` (probe scored).

    Output is equivalent but not byte-equal across runtimes (rendered verdict
    text, agent LLM responses, Grant Moment prompt text). Scored by an LLM-judge
    probe per `rules/probe-driven-verification.md`; the harness for this tier
    lands in Phase-03 with the semantic-equivalence corpus.
    """
    setattr(fn, CONTRACT_TIER_ATTR, ContractTier.SEMANTICALLY_EQUIVALENT)
    return fn


def tier_of(fn: object) -> ContractTier:
    """Return the `ContractTier` stamped on a method, or raise if absent.

    Reads the `__contract_tier__` attribute set by the decorators. Raising on
    absence (rather than returning a default) is the loud-authoring-error
    contract — the harness uses this to select a scorer, and a wrong default
    would silently score with the wrong scorer.
    """
    tier = getattr(fn, CONTRACT_TIER_ATTR, None)
    if tier is None:
        name = getattr(fn, "__name__", repr(fn))
        raise MissingContractTierError(
            f"method {name!r} has no contract-tier decorator; add "
            f"@byte_identical or @semantically_equivalent (no silent default — "
            f"see envoy/runtime/contract_tier.py docstring)"
        )
    return tier


def assert_all_methods_tagged(protocol: type) -> dict[str, ContractTier]:
    """Authoring-time gate: every public method on ``protocol`` carries a tier.

    Returns the ``{method_name: ContractTier}`` map on success. Raises
    `MissingContractTierError` naming the FIRST untagged method on failure. The
    conformance harness calls this at import time so a method added to the
    Protocol without a tier decorator fails collection loudly — there is no
    hand-maintained method→tier map to drift out of sync (S1 acceptance
    criterion 1).
    """
    import inspect

    tiers: dict[str, ContractTier] = {}
    for name, member in inspect.getmembers(protocol, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        tier = getattr(member, CONTRACT_TIER_ATTR, None)
        if tier is None:
            raise MissingContractTierError(
                f"{protocol.__name__}.{name} has no contract-tier decorator; "
                f"add @byte_identical or @semantically_equivalent in "
                f"envoy/runtime/protocol.py (no silent default tier)"
            )
        tiers[name] = tier
    return tiers


__all__ = [
    "ContractTier",
    "MissingContractTierError",
    "CONTRACT_TIER_ATTR",
    "byte_identical",
    "semantically_equivalent",
    "tier_of",
    "assert_all_methods_tagged",
]
