# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.skill_ingest.comparison — asymmetric declared-vs-inferred score routing.

`specs/skill-ingest.md` CO validator steps 3 + 4. This is the LOAD-BEARING
asymmetric routing the design rests on. `compare_declared_inferred` consumes the
declared permission categories (from the SKILL.md manifest) and the
`InferredPermissionSet` (from the conservative AST walk) and returns a SCORE
plus the structured findings, routed asymmetrically:

  - **AST-proven literal undeclared-capability reach** (`inferred ⊋ declared` via
    a LITERAL call, OR any literal dynamic-dispatch construct) → score < 0.5 →
    the pipeline REJECTS with `COValidatorRefusedError`. The AST PROVED the
    reach; a literal undeclared capability is a hard fail.

  - **import-graph-only extra** (a capability-bearing import not confirmed by a
    literal call AND not declared) → score in the 0.5–0.8 warning band →
    pass-WITH-WARNING. The import is a second opinion, never an auto-reject.

  - **`declared ⊋ inferred` over-declaration** (the author declared MORE than the
    code reaches) → an `OverPrivilegeWarning` (step 4) carried in the result —
    NOT a reject. The score stays in the pass band; the warning surfaces at the
    Grant Moment so the user may downscope.

The score is a deterministic function of the finding classes (no randomness):

  - any AST-proven literal undeclared reach → 0.3 (below the 0.5 reject floor)
  - else any import-graph-only extra → 0.65 (within the 0.5–0.8 warning band)
  - else (declared ⊇ inferred-literal, no import surprises) → 1.0 (clean pass),
    minus a small notch to 0.85 when an over-declaration warning is present
    (still ≥0.8 pass band — over-declaration is advisory, not penalising).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from envoy.skill_ingest.errors import OverPrivilegeWarning
from envoy.skill_ingest.inference import InferredCapability, InferredPermissionSet

# Score anchors (`specs/skill-ingest.md` § Score thresholds: ≥0.8 pass;
# 0.5–0.8 warning; <0.5 fail).
_SCORE_CLEAN = 1.0
_SCORE_OVER_DECLARED = 0.85  # still ≥0.8 pass band — over-declaration is advisory
_SCORE_IMPORT_WARNING = 0.65  # within the 0.5–0.8 warning band
_SCORE_LITERAL_UNDECLARED = 0.3  # below the 0.5 reject floor

_THRESHOLD_PASS = 0.8
_THRESHOLD_FAIL = 0.5


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """The outcome of comparing declared vs inferred permissions.

    `score` drives the pipeline's routing decision (≥0.8 pass; 0.5–0.8 warning;
    <0.5 reject). `errors` are the AST-proven literal undeclared reaches (the
    reject drivers). `warnings` are the import-graph second opinions. The
    over-declaration finding is surfaced as a typed `OverPrivilegeWarning`
    instance in `over_privilege` (step 4), distinct from the import warnings.
    """

    score: float
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    over_privilege: OverPrivilegeWarning | None = None
    literal_undeclared: tuple[str, ...] = field(default_factory=tuple)
    import_only_extra: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        """True when the score is at or above the reject floor (≥0.5).

        A score in [0.5, 0.8) passes WITH warnings; ≥0.8 passes clean; <0.5
        fails. `passed` is False ONLY for the <0.5 reject band.
        """
        return self.score >= _THRESHOLD_FAIL

    @property
    def clean(self) -> bool:
        """True when the score is in the ≥0.8 clean-pass band."""
        return self.score >= _THRESHOLD_PASS


def compare_declared_inferred(
    declared: Iterable[str],
    inferred: InferredPermissionSet,
) -> ComparisonResult:
    """Compare declared permission categories against the inferred set.

    Args:
        declared: The declared permission CATEGORIES (e.g. ``{"http-post",
            "file-read"}``) — the categories extracted from the SKILL.md
            manifest's permission patterns.
        inferred: The `InferredPermissionSet` from the conservative AST walk.

    Returns:
        A `ComparisonResult` carrying the routed score + structured findings.

    The routing is ASYMMETRIC by construction:
      - literal undeclared reach (incl. dynamic dispatch) → <0.5 (reject)
      - import-graph-only extra → 0.5–0.8 (warn)
      - over-declaration → typed `OverPrivilegeWarning`, score stays in pass band
    """
    declared_set = set(declared)

    # --- literal undeclared reaches (the reject drivers) ------------------
    # A literal call category not in the declared set is AST-PROVEN
    # over-reach. Dynamic-dispatch constructs are ALWAYS undeclared reaches
    # (no manifest can declare "I use getattr to reach arbitrary capability").
    literal_categories = inferred.literal_categories
    literal_undeclared = sorted(literal_categories - declared_set)
    has_dynamic_dispatch = bool(inferred.dynamic_dispatch)

    errors: list[str] = []
    for cat in literal_undeclared:
        if cat == "dynamic-dispatch":
            continue  # reported via the dynamic-dispatch branch below
        evidence = _evidence_for(inferred.literal_calls, cat)
        errors.append(
            f"AST-proven undeclared capability {cat!r}: the inline code makes a "
            f"literal call ({evidence}) but {cat!r} is not in the declared "
            "permissions — over-reach"
        )
    for dyn in inferred.dynamic_dispatch:
        errors.append(
            f"AST-visible dynamic-dispatch construct ({dyn.evidence}): runtime "
            "dispatch the declared-permission set cannot bound — treated as an "
            "undeclared-capability reach"
        )

    # --- import-graph-only extras (warning band) --------------------------
    # A capability-bearing import whose category is NOT declared AND NOT already
    # confirmed by a literal call is a second-opinion WARNING (never a reject).
    import_only_extra = sorted(inferred.import_categories - declared_set - literal_categories)
    warnings: list[str] = [
        f"import-graph second opinion: module imported implying capability "
        f"{cat!r} but no literal call confirms the reach and {cat!r} is "
        "undeclared — surfaced as a warning, not a reject"
        for cat in import_only_extra
    ]

    # --- over-declaration (step 4 — OverPrivilegeWarning, NOT a reject) ----
    # The author declared categories the code never reaches (neither literal
    # nor import-graph). Surfaced as a typed warning at the Grant Moment.
    reached_categories = literal_categories | inferred.import_categories
    over_declared = sorted(declared_set - reached_categories)
    over_privilege: OverPrivilegeWarning | None = None
    if over_declared:
        over_privilege = OverPrivilegeWarning(
            f"declared permissions exceed inferred reach: {over_declared!r} "
            "declared but the inline code does not reach them — the user may "
            "downscope or accept at the Grant Moment",
            excess=tuple(over_declared),
        )

    # --- score routing (deterministic) ------------------------------------
    if errors:
        # Any AST-proven literal undeclared reach (incl. dynamic dispatch)
        # routes below the 0.5 reject floor.
        score = _SCORE_LITERAL_UNDECLARED
    elif import_only_extra:
        # Import-graph-only extras route into the 0.5–0.8 warning band.
        score = _SCORE_IMPORT_WARNING
    elif over_privilege is not None:
        # Clean reach, but the author over-declared — advisory notch, still
        # in the ≥0.8 pass band.
        score = _SCORE_OVER_DECLARED
    else:
        score = _SCORE_CLEAN

    return ComparisonResult(
        score=score,
        errors=tuple(errors),
        warnings=tuple(warnings),
        over_privilege=over_privilege,
        literal_undeclared=tuple(c for c in literal_undeclared if c != "dynamic-dispatch")
        + (("dynamic-dispatch",) if has_dynamic_dispatch else ()),
        import_only_extra=tuple(import_only_extra),
    )


def _evidence_for(literal_calls: list[InferredCapability], category: str) -> str:
    """The first literal-call evidence string for a category (for the message)."""
    for cap in literal_calls:
        if cap.category == category:
            return cap.evidence
    return "<literal call>"


__all__ = ["ComparisonResult", "compare_declared_inferred"]
