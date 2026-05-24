"""Envelope-compiler dataclass types.

Implements `specs/envelope-model.md` § Schema (top-level `EnvelopeConfig` JSON
wire format). Phase 01 superset over kailash-py's `ConstraintEnvelopeConfig`
(5 dimensions + clearance) — adds metadata.algorithm_identifier, composition,
cross-domain, tool-output, semantic-checks blocks.

Two parallel hierarchies:
- `*Input` (authored — un-canonicalized; what Boundary Conversation emits)
- `EnvelopeConfig` (compiled — canonicalized; emitted by EnvelopeCompiler)

Per shard 4 § 4 step list, the compiler validates the *Input → emits the
canonicalized EnvelopeConfig.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConfidentialityLevel(str, Enum):
    """Per `specs/envelope-model.md` § Schema § data_access (canonical naming)."""

    PUBLIC = "Public"
    INTERNAL = "Internal"
    CONFIDENTIAL = "Confidential"
    RESTRICTED = "Restricted"
    HIGHLY_CONFIDENTIAL = "HighlyConfidential"


# ---------------------------------------------------------------------------
# Algorithm identifier (metadata.algorithm_identifier per spec L24)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AlgorithmIdentifier:
    """Pin every cryptographic + canonicalization algorithm at envelope-construction.

    Per `specs/envelope-model.md` § Schema lines 24-29, the canonical 4-key
    form (R2-H-01 + R3-M-02): sig, hash, shamir, canonical_json + ensemble
    classifiers + cross_domain_rules registry version. The `_to_spec_wire_form()`
    helper at the trust-store boundary emits this shape for record persistence.
    """

    sig: str = "ed25519"
    hash: str = "sha256"
    shamir: str = "slip39"
    canonical_json: str = "jcs-rfc8785"
    ensemble_classifiers: tuple[str, ...] = ()
    cross_domain_rules: str = "envoy-registry:cross-domain-flows:v1"


# ---------------------------------------------------------------------------
# Authored / Imported constraints
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthoredConstraint:
    """User-authored constraint (counts toward Authorship Score per BET-12)."""

    constraint_id: str
    rule_ast: dict[str, Any] = field(default_factory=dict)
    authored: bool = True


@dataclass(frozen=True, slots=True)
class ImportedConstraint:
    """Template-imported constraint (does NOT count toward Authorship Score).

    Carries template_origin + template_hash for provenance per
    `specs/envelope-library.md` § "Cross-domain consumer mapping".
    """

    constraint_id: str
    rule_ast: dict[str, Any] = field(default_factory=dict)
    template_origin: str = ""
    template_hash: str = ""
    authored: bool = False


# ---------------------------------------------------------------------------
# Five dimensions (canonical names per `rules/terrene-naming.md`)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FinancialDimension:
    """Per `specs/envelope-model.md` § Schema § financial.

    Phase 01 disposition #1: UTC-only resets (`per_day_ceiling_microdollars`
    fires at UTC midnight). Phase 02 entry adds IANA timezone field per
    `journal/0003-GAP-budget-ceiling-timezone.md`.

    All ceiling values are integer microdollars (per spec § Algorithms §
    "Canonical JSON" — integer microdollars + lexicographic ordering).

    L-03 shard B step 2: now `frozen=True`. Compiler mints new dimension
    instances via `dataclasses.replace`. `__post_init__` uses
    `object.__setattr__` for the C1 list→tuple coercion (the only
    field-write a frozen __post_init__ is allowed to perform).
    Mutable container fields (rate_limits, sub_agent_spawn_limit, etc.)
    on sibling dimensions still permit IN-PLACE mutation of their
    contents — Phase 02 deep-freeze closes that vector.
    """

    per_call_ceiling_microdollars: int = 0
    per_session_ceiling_microdollars: int = 0
    per_hour_velocity_microdollars: int = 0
    per_day_ceiling_microdollars: int = 0
    per_month_ceiling_microdollars: int = 0
    authored_constraints: tuple[AuthoredConstraint, ...] = ()
    imported_constraints: tuple[ImportedConstraint, ...] = ()

    def __post_init__(self) -> None:
        # NaN/Inf guard per pact-governance.md § "_validate_finite()"
        for f in (
            self.per_call_ceiling_microdollars,
            self.per_session_ceiling_microdollars,
            self.per_hour_velocity_microdollars,
            self.per_day_ceiling_microdollars,
            self.per_month_ceiling_microdollars,
        ):
            if not isinstance(f, int) or not math.isfinite(f):
                raise ValueError(
                    f"financial ceiling must be a finite integer (got {type(f).__name__})"
                )
            if f < 0:
                raise ValueError("financial ceiling must be non-negative")
        # L-03 shard A C1 fix (security review CRITICAL): coerce
        # list-passed-at-construction to tuple. Without this, callers
        # passing `authored_constraints=[c1]` would store a list (Python
        # dataclasses don't enforce the tuple annotation), defeating the
        # immutability invariant for that instance. Coerce defensively at
        # construction so the invariant holds regardless of input shape.
        # L-03 shard B step 2: frozen=True requires object.__setattr__.
        if not isinstance(self.authored_constraints, tuple):
            object.__setattr__(self, "authored_constraints", tuple(self.authored_constraints))
        if not isinstance(self.imported_constraints, tuple):
            object.__setattr__(self, "imported_constraints", tuple(self.imported_constraints))


@dataclass(frozen=True, slots=True)
class OperationalDimension:
    """Per spec § Schema § operational.

    L-03 shard B step 2: see FinancialDimension docstring.
    """

    tool_allowlist: list[str] = field(default_factory=list)
    tool_denylist: list[str] = field(default_factory=list)
    rate_limits: dict[str, dict[str, int]] = field(default_factory=dict)
    sub_agent_spawn_limit: dict[str, int] = field(default_factory=dict)
    authored_constraints: tuple[AuthoredConstraint, ...] = ()
    imported_constraints: tuple[ImportedConstraint, ...] = ()

    def __post_init__(self) -> None:
        # L-03 shard A C1 fix: coerce list-passed-at-construction to tuple.
        # L-03 shard B step 2: frozen=True requires object.__setattr__.
        if not isinstance(self.authored_constraints, tuple):
            object.__setattr__(self, "authored_constraints", tuple(self.authored_constraints))
        if not isinstance(self.imported_constraints, tuple):
            object.__setattr__(self, "imported_constraints", tuple(self.imported_constraints))


@dataclass(frozen=True, slots=True)
class TemporalDimension:
    """Per spec § Schema § temporal.

    L-03 shard B step 2: see FinancialDimension docstring.
    """

    allowed_windows: list[dict[str, Any]] = field(default_factory=list)
    blackout_windows: list[dict[str, Any]] = field(default_factory=list)
    authored_constraints: tuple[AuthoredConstraint, ...] = ()
    imported_constraints: tuple[ImportedConstraint, ...] = ()

    def __post_init__(self) -> None:
        # L-03 shard A C1 fix: coerce list-passed-at-construction to tuple.
        # L-03 shard B step 2: frozen=True requires object.__setattr__.
        if not isinstance(self.authored_constraints, tuple):
            object.__setattr__(self, "authored_constraints", tuple(self.authored_constraints))
        if not isinstance(self.imported_constraints, tuple):
            object.__setattr__(self, "imported_constraints", tuple(self.imported_constraints))


@dataclass(frozen=True, slots=True)
class DataAccessDimension:
    """Per spec § Schema § data_access. Classification clearance per V-06 fix.

    L-03 shard B step 2: see FinancialDimension docstring.
    """

    classification_clearance: ConfidentialityLevel = ConfidentialityLevel.PUBLIC
    field_allowlist_per_model: dict[str, list[str]] = field(default_factory=dict)
    field_denylist: list[str] = field(default_factory=list)
    semantic_rules: list[dict[str, Any]] = field(default_factory=list)
    authored_constraints: tuple[AuthoredConstraint, ...] = ()
    imported_constraints: tuple[ImportedConstraint, ...] = ()

    def __post_init__(self) -> None:
        # L-03 shard A C1 fix: coerce list-passed-at-construction to tuple.
        # L-03 shard B step 2: frozen=True requires object.__setattr__.
        if not isinstance(self.authored_constraints, tuple):
            object.__setattr__(self, "authored_constraints", tuple(self.authored_constraints))
        if not isinstance(self.imported_constraints, tuple):
            object.__setattr__(self, "imported_constraints", tuple(self.imported_constraints))


@dataclass(frozen=True, slots=True)
class CommunicationDimension:
    """Per spec § Schema § communication.

    L-03 shard B step 2: see FinancialDimension docstring.
    """

    recipient_allowlist: list[str] = field(default_factory=list)
    recipient_denylist: list[str] = field(default_factory=list)
    domain_allowlist: list[str] = field(default_factory=list)
    channel_allowlist: list[str] = field(default_factory=list)
    content_rules: list[dict[str, Any]] = field(default_factory=list)
    authored_constraints: tuple[AuthoredConstraint, ...] = ()
    imported_constraints: tuple[ImportedConstraint, ...] = ()

    def __post_init__(self) -> None:
        # L-03 shard A C1 fix: coerce list-passed-at-construction to tuple.
        # L-03 shard B step 2: frozen=True requires object.__setattr__.
        if not isinstance(self.authored_constraints, tuple):
            object.__setattr__(self, "authored_constraints", tuple(self.authored_constraints))
        if not isinstance(self.imported_constraints, tuple):
            object.__setattr__(self, "imported_constraints", tuple(self.imported_constraints))


# ---------------------------------------------------------------------------
# Top-level cross-cutting fields
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompositionRule:
    """Per spec § Schema § composition_rules (top-level array)."""

    rule_id: str
    order: int
    session_condition_ast: dict[str, Any] = field(default_factory=dict)
    blocked_action_ast: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class CrossDomainRule:
    """Per spec § Schema § cross_domain_rules_authored (top-level array).

    Imported cross-domain rules fold into this list at template-import time
    with `authored=false` semantics per `specs/cross-domain-flows.md` § Algorithm.
    """

    rule_id: str
    order: int
    source_domain_ast: dict[str, Any] = field(default_factory=dict)
    sink_domain_ast: dict[str, Any] = field(default_factory=dict)
    verdict: str = "block"  # block | block+grant_moment | flag+allow
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class SemanticChecks:
    """Per spec § Schema § semantic_checks. Phase 01 ships minimum classifier set."""

    data_access_classifier_ensemble: tuple[dict[str, Any], ...] = ()
    communication_content_classifier_ensemble: tuple[dict[str, Any], ...] = ()
    tool_output_classifier_ensemble: tuple[dict[str, Any], ...] = ()
    latency_budget_ms: dict[str, int] = field(
        default_factory=lambda: {
            "structural_hashset": 5,
            "arithmetic": 5,
            "comparison": 1,
            "semantic_cached": 50,
            "semantic_uncached": 500,
            "composition_rule_eval": 10,
            "subset_proof_verify": 20,
            "tool_output_sanitize": 50,
            "cross_domain_rules_eval": 10,
        }
    )
    unavailability_policy: str = "fail-closed"


# ---------------------------------------------------------------------------
# Envelope-scope reference (per specs/envelope-model.md § Operational +
# Communication dimensions; consumed by `envoy.connection_vault` per
# shard 14 § 3.3 step 3 — "Envelope-scope enforcement").
#
# Phase 01 minimum: narrow operational-service + communication-channel
# tuple. Phase 02 full envelope intersection lives in
# `kailash.trust.pact.envelopes.intersect_envelopes` (deferred at T-01-10
# per envoy/envelope/compiler.py line 296-308). The membership predicate
# is `envoy.envelope.scope.envelope_contains_scope()` — set-membership,
# not the full intersection algorithm.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EnvelopeScopeRef:
    """Narrow scope tuple for credential / tool / channel use.

    Per `specs/connection-vault.md` § Per-entry schema row "entry_envelope_scope".
    Phase 01 minimum: a credential is reachable only when the active envelope
    permits BOTH (a) the service via `operational.tool_allowlist` AND (b) the
    channel via `communication.channel_allowlist` (when `channel` is set).

    Phase 02 promotion: when `kailash.trust.pact.envelopes.intersect_envelopes`
    ships, this dataclass moves to richer semantics; the current narrow shape
    is forward-compatible.
    """

    service_identifier: str
    channel: str | None = None


# ---------------------------------------------------------------------------
# Authored input (pre-canonicalization)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EnvelopeMetadata:
    """Per spec § Schema § metadata.

    L-03 shard B (frozen=True): once constructed, the metadata fields
    cannot be reassigned. Compiler builds new metadata via
    `dataclasses.replace(metadata, envelope_id=..., authorship_score=...)`.
    Note: dict fields (authorship_score, enterprise_mode, goal_reconfirmation)
    are still mutable IN-PLACE via .setdefault / .__setitem__ — Phase 02
    deep-freeze via MappingProxyType closes that vector.
    """

    envelope_id: str = ""
    algorithm_identifier: AlgorithmIdentifier = field(default_factory=AlgorithmIdentifier)
    authorship_score: dict[str, Any] = field(
        default_factory=lambda: {
            "authored_count": 0,
            "imported_count": 0,
            "template_provenance": [],
        }
    )
    enterprise_mode: dict[str, Any] = field(
        default_factory=lambda: {"is_enterprise": False, "enterprise_deployment_record_hash": None}
    )
    sub_agent_session_inheritance: str = "isolated"
    goal_reconfirmation: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "N_tool_calls": 5,
            "scope": "session",
            "per_posture_overrides": {},
        }
    )
    # Per `specs/posture-ladder.md` § Ratchet-up #3 + `journal/0021-DECISION-...md`
    # (T-02-33): the envelope's posture_level is the load-bearing field that
    # binds posture transitions to envelope_edit Ledger entries. Wire-form is
    # the canonical PostureLevel enum NAME (`"PSEUDO" | "TOOL" | "SUPERVISED"
    # | "DELEGATING" | "AUTONOMOUS"`) so JCS canonicalization produces
    # cross-runtime byte-identical bytes (spec line 27 — wire format is the
    # string name). Default is `"PSEUDO"` per `specs/posture-ladder.md` § TOOL
    # / PSEUDO semantics ("Default tier at first Boundary Conversation entry").
    posture_level: str = "PSEUDO"


@dataclass(slots=True)
class EnvelopeConfigInput:
    """Authored envelope before validation/canonicalization.

    Boundary Conversation (shard 8) emits this; EnvelopeCompiler.compile()
    consumes it and produces an `EnvelopeConfig`.

    Per `rules/tenant-isolation.md` Rule 2 (and package-skeleton § 5.1
    consolidated rule), the compiler ALSO requires `principal_id` at compile()
    time — it is not a field on the envelope itself, but on the call.
    """

    schema_version: str = "envelope/1.0"
    metadata: EnvelopeMetadata = field(default_factory=EnvelopeMetadata)
    financial: FinancialDimension = field(default_factory=FinancialDimension)
    operational: OperationalDimension = field(default_factory=OperationalDimension)
    temporal: TemporalDimension = field(default_factory=TemporalDimension)
    data_access: DataAccessDimension = field(default_factory=DataAccessDimension)
    communication: CommunicationDimension = field(default_factory=CommunicationDimension)
    composition_rules: list[CompositionRule] = field(default_factory=list)
    cross_domain_rules_authored: list[CrossDomainRule] = field(default_factory=list)
    tool_output_budget_bytes: int = 65536
    semantic_checks: SemanticChecks = field(default_factory=SemanticChecks)
    template_refs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiled envelope (post-canonicalization)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EnvelopeConfig:
    """Compiled envelope per `specs/envelope-model.md` § Schema.

    Frozen because every downstream consumer (Trust store DelegationRecord,
    Ledger envelope_edit entry, SubsetProof verifier) reads `content_hash`
    as identity; mutability would invalidate the cross-consumer contract.
    """

    schema_version: str
    envelope_version: int
    metadata: EnvelopeMetadata
    financial: FinancialDimension
    operational: OperationalDimension
    temporal: TemporalDimension
    data_access: DataAccessDimension
    communication: CommunicationDimension
    composition_rules: tuple[CompositionRule, ...]
    cross_domain_rules_authored: tuple[CrossDomainRule, ...]
    tool_output_budget_bytes: int
    semantic_checks: SemanticChecks
    canonical_bytes: bytes
    content_hash: str  # sha256 hex over canonical_bytes
    compiled_at: datetime
