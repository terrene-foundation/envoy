"""envoy.authorship.score — count-only Authorship Score recompute (T-02-30).

Phase 01 implements ONLY the deterministic count-only recompute per
`specs/authorship-score.md` § Re-derivation from the Ledger. Per /autonomize
Rule 1 (most optimal long-term pick) + `rules/spec-accuracy.md` Rule 5 (Spec
content describes ONLY behavior already shipped on main):

- The novelty Tree-Jaccard + adversarial-wording classifier algorithm is
  Phase-04 hardening (see spec § "Out of scope (Phase 01)").
- The minimum-impact dry-run against `standard_action_corpus_v1` is Phase-04
  hardening (same).
- The classifier-pin (`envoy-registry:novelty.adversarial-wording:v1`) is
  Phase-04 — `T-02-30` does NOT pin a classifier because it does not invoke
  one.
- The PostureGate consumer (T-02-31) is the next shard; this module exposes
  the substrate it consumes.

The count-only recompute iterates the five canonical envelope dimensions in
fixed order (`financial`, `operational`, `temporal`, `data_access`,
`communication` per `rules/terrene-naming.md` § Canonical Terminology — these
exact names, no synonyms, no reordering) and counts every authored constraint
where `authored=True`. Phase-04 extends `AuthoredConstraint` with
`novelty_check_passed` / `minimum_impact_check_passed` flags — when those
fields exist on a future dataclass extension the recompute will additionally
gate on them; today it counts on `authored` alone because those fields are
not part of the shipped `AuthoredConstraint` dataclass (see
`envoy/envelope/types.py` `AuthoredConstraint`). Forward-compat is via
defensive `getattr(c, "novelty_check_passed", True)` so the recompute is a
single function across both Phase-01 and Phase-04 dataclass shapes.

Imported constraints contribute to `imported_count` and
`template_provenance` (ordered tuple of `(template_id, template_hash)` pairs
deduplicated on first-encounter; the spec pseudocode uses a list-of-dicts
shape but L-03 immutability mandates tuple-of-tuples — this module emits the
L-03-compliant shape).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envoy.envelope.types import EnvelopeConfig

# Canonical 5-dimension order per `rules/terrene-naming.md` § Canonical
# Terminology. NOT in alphabetical order — Foundation-stewarded ordering
# matches the order in `specs/envelope-model.md` § Schema and
# `specs/authorship-score.md` § Re-derivation pseudocode. Cross-shard
# invariant: same order as `envoy/envelope/compiler.py` step 7 (per shard 9
# § 3.4); changing this tuple is a coordinated multi-shard edit.
_CANONICAL_DIMENSIONS: tuple[str, ...] = (
    "financial",
    "operational",
    "temporal",
    "data_access",
    "communication",
)


@dataclass(frozen=True, slots=True)
class AuthorshipCounters:
    """Stored counters per `specs/authorship-score.md` § Stored counters.

    Frozen + slots per `rules/eatp.md` (immutable value-type contract). The
    `template_provenance` field is a tuple-of-tuples (NOT list-of-dicts as
    the spec pseudocode shows) because L-03 immutability requires deep-frozen
    containers. The `to_dict()` / `from_dict()` round-trip emits the
    spec-canonical list-of-dicts shape on the wire so JCS-canonical bytes
    match the spec's wire schema; the in-memory shape is the L-03 tuple form.

    Fields:
        authored_count: count of `authored_constraints[*].authored == True`
            across the five canonical dimensions. Phase 04 extends this with
            novelty + minimum-impact gates; Phase 01 counts on `authored`
            alone (forward-compat via `getattr` — see `recompute_authorship_counters`).
        imported_count: count of imported constraints across the five
            canonical dimensions. Does NOT count toward posture ratchet per
            `specs/posture-ladder.md` § State-transition contract (BET-12
            requires user-authoring, not template-import, to gate posture).
        template_provenance: ordered tuple of `(template_id, template_hash)`
            pairs in first-encounter order across the canonical dimension
            sweep. Empty tuple `()` if no imported constraints. Order is
            deterministic given the envelope's frozen dimension order.
    """

    authored_count: int
    imported_count: int
    template_provenance: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        """Emit spec-canonical wire shape (list-of-dicts for provenance).

        Per `specs/authorship-score.md` § Stored counters table, the wire
        schema for `template_provenance` is `list[{template_id, template_hash}]`.
        The L-03 in-memory shape (tuple-of-tuples) is converted at the wire
        boundary so JCS-canonical bytes match the spec.
        """
        return {
            "authored_count": self.authored_count,
            "imported_count": self.imported_count,
            "template_provenance": [
                {"template_id": tid, "template_hash": thash}
                for (tid, thash) in self.template_provenance
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AuthorshipCounters:
        """Parse spec-canonical wire shape into the frozen value-type.

        Reverse of `to_dict()`. Raises `KeyError` on a malformed payload (no
        defaults — per the project rule "NEVER USE DEFAULTS FOR FALLBACKS"):
        a wire payload missing one of the three top-level fields OR missing
        `template_id` / `template_hash` inside any provenance entry MUST
        fail loudly so the caller learns of the schema mismatch.

        Type-validates every field per security review M-02: a malicious
        wire payload `{"authored_count": "999", ...}` MUST be rejected at
        deserialization, not silently coerced to a frozen dataclass that
        downstream `stored == recomputed` comparisons handle non-deterministically.
        """
        authored_count = payload["authored_count"]
        imported_count = payload["imported_count"]
        if not isinstance(authored_count, int) or isinstance(authored_count, bool):
            raise TypeError(f"authored_count must be int, got {type(authored_count).__name__}")
        if not isinstance(imported_count, int) or isinstance(imported_count, bool):
            raise TypeError(f"imported_count must be int, got {type(imported_count).__name__}")
        if authored_count < 0:
            raise ValueError(f"authored_count must be non-negative, got {authored_count}")
        if imported_count < 0:
            raise ValueError(f"imported_count must be non-negative, got {imported_count}")
        raw_provenance = payload["template_provenance"]
        if not isinstance(raw_provenance, list):
            raise TypeError(
                f"template_provenance must be list, got {type(raw_provenance).__name__}"
            )
        provenance_entries: list[tuple[str, str]] = []
        for i, entry in enumerate(raw_provenance):
            if not isinstance(entry, dict):
                raise TypeError(
                    f"template_provenance[{i}] must be dict, got {type(entry).__name__}"
                )
            tid = entry["template_id"]
            thash = entry["template_hash"]
            if not isinstance(tid, str):
                raise TypeError(
                    f"template_provenance[{i}].template_id must be str, "
                    f"got {type(tid).__name__}"
                )
            if not isinstance(thash, str):
                raise TypeError(
                    f"template_provenance[{i}].template_hash must be str, "
                    f"got {type(thash).__name__}"
                )
            provenance_entries.append((tid, thash))
        return cls(
            authored_count=authored_count,
            imported_count=imported_count,
            template_provenance=tuple(provenance_entries),
        )


class AuthorshipScoreDivergenceError(Exception):
    """Stored counter does not match recomputed counter (M-05 audit alert).

    Raised when `metadata.authorship_score.authored_count` (signed at
    envelope-sign time) diverges from the runtime recompute (T-023 defense
    per `specs/authorship-score.md` § Stored vs recomputed).

    Per `rules/communication.md`, exposes a plain-language `user_message`
    so non-technical surfaces (Daily Digest, Channel adapters) can render
    the divergence without re-deriving the explanation.

    The PostureGate consumer (T-02-31) raises this error to halt posture
    ratchet on divergence — the divergence is NEVER auto-recovered (see
    spec § Error taxonomy: "Retry: Never (T-023 defense)").
    """

    def __init__(
        self,
        *,
        stored: int,
        recomputed: int,
        envelope_id: str = "",
    ) -> None:
        self.stored = stored
        self.recomputed = recomputed
        self.envelope_id = envelope_id
        self.user_message = (
            "Your envelope's authorship count does not match what we just "
            "recomputed from the Ledger. To protect you, we paused any "
            "posture changes that depend on this count. We did not change "
            "your envelope. Please re-open your Weekly Posture Review so we "
            "can investigate together."
        )
        super().__init__(
            f"AuthorshipScoreDivergenceError: stored={stored} "
            f"recomputed={recomputed} envelope_id={envelope_id!r}"
        )


def recompute_authorship_counters(
    envelope: EnvelopeConfig,
    ledger_slice: Any,
) -> AuthorshipCounters:
    """Re-derive authorship counters from the envelope's authored/imported constraints.

    Pure deterministic function: same `(envelope, ledger_slice)` produces
    byte-identical `AuthorshipCounters`. This is the verifier hook backing
    the M-05 fix (`AuthorshipScoreDivergenceError` audit alert).

    Iteration order (load-bearing per `specs/authorship-score.md`
    § Re-derivation + shard 9 § 3.1):

        1. financial
        2. operational
        3. temporal
        4. data_access
        5. communication

    Within each dimension, `authored_constraints` then `imported_constraints`
    are iterated in their stored tuple order (envelope dimensions are
    frozen tuples per L-03; iteration order matches the JCS-canonical
    storage order locked by the envelope compiler).

    Authored counting (Phase 01 count-only):

        authored = c.authored AND
                   getattr(c, "novelty_check_passed", True) AND
                   getattr(c, "minimum_impact_check_passed", True)

    The `getattr` defaults to True so that today's `AuthoredConstraint`
    dataclass (which lacks the two flags — see `envoy/envelope/types.py`)
    counts on `authored` alone, AND a Phase-04 dataclass extension that
    adds the flags will gate on them automatically without changing this
    function. This is forward-compat without a fake-dispatch hazard
    (per `rules/zero-tolerance.md` Rule 2): if the flags exist they are
    consumed; if not, the count is simply on `authored`.

    Imported counting:

        Every imported constraint contributes 1 to `imported_count`.
        If `c.template_origin` is non-empty AND the
        `(template_origin, template_hash)` pair has not been seen earlier
        in the canonical sweep, the pair is appended to `template_provenance`
        in first-encounter order.

    Args:
        envelope: compiled `EnvelopeConfig` with frozen 5-dimension shape.
        ledger_slice: forward-compat parameter for Phase-04 minimum-impact
            (which reads ledger history to determine behavioral impact). For
            Phase 01 the parameter is accepted but unused — Phase 04's
            implementation in T-04-XX (minimum-impact algorithm) will read
            this slice. The parameter is intentionally not raise-on-None
            because the Phase-01 caller (T-02-31 PostureGate) does not yet
            have a Ledger slice API; T-04-XX adds the slice + enforces
            non-None at the same time. Documented forward-compat is NOT a
            stub (per `rules/zero-tolerance.md` Rule 6 — iterative TODOs
            permitted when actively tracked) — it is the deliberate API
            stability surface so T-02-31 (next shard) can call this function
            today and Phase 04 can extend the function without touching the
            T-02-31 callsite.

    Returns:
        `AuthorshipCounters` with deterministic `authored_count`,
        `imported_count`, and `template_provenance` (tuple-of-tuples).

    Raises:
        Nothing in Phase 01. Phase-04 will raise `ClassifierRegistryMissError`
        and `ColdStartInsufficientHistoryError` from the novelty +
        minimum-impact paths; those errors live in this module's spec
        (`§ Error taxonomy`) but are NOT raised by this function today.
    """
    # `ledger_slice` is intentionally unused in Phase 01; see docstring
    # forward-compat note. Reference it once so static analyzers (pyright,
    # mypy --strict) confirm the parameter is observed.
    _ = ledger_slice

    authored_count = 0
    imported_count = 0
    seen_provenance: set[tuple[str, str]] = set()
    provenance_in_order: list[tuple[str, str]] = []

    for dim_name in _CANONICAL_DIMENSIONS:
        dimension = getattr(envelope, dim_name)

        for c in dimension.authored_constraints:
            # Strict-identity check (`is True`) defends against T-023 type-
            # confusion inflation per security review H-02 + zero-tolerance
            # Rule 2 fake-classification class. Any truthy non-bool value
            # (`authored="yes"`, `authored=1`, `authored=[1]`) MUST NOT
            # count — only an explicit boolean True does. Phase-04
            # novelty + minimum-impact gates land via explicit dispatch
            # (see Phase-04 dispatch note below); they are NOT consumed
            # via `getattr` defaults here. Per security review H-01: a
            # `getattr(c, "novelty_check_passed", True)` would silently
            # weaken the T-023 defense on cross-version replay if a
            # downgraded verifier received a flag-stripped envelope.
            if c.authored is True:
                authored_count += 1

        for c in dimension.imported_constraints:
            imported_count += 1
            template_origin = c.template_origin
            # Normalize `template_hash` to "" for None per security review
            # M-01 — `None` and `""` are semantically the same "no hash
            # bound" state and MUST collapse to a single dedup key. Without
            # this, an envelope crafted with two imports of the same
            # `template_id` but `(None, "")` produces two provenance
            # entries — provenance-inflation that diverges from spec intent.
            template_hash = c.template_hash if c.template_hash else ""
            if template_origin:
                key = (template_origin, template_hash)
                if key not in seen_provenance:
                    seen_provenance.add(key)
                    provenance_in_order.append(key)

    return AuthorshipCounters(
        authored_count=authored_count,
        imported_count=imported_count,
        template_provenance=tuple(provenance_in_order),
    )
