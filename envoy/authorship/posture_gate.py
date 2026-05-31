"""envoy.authorship.posture_gate — 5-step fail-closed posture transition gate (T-02-31).

Per `specs/posture-ladder.md` § State-transition contract + § Algorithm. The gate
is the single bottleneck for every posture transition (ratchet-up, ratchet-down,
annual decay). It enforces the 5 invariants captured in `02-wave-2-...md` § T-02-31:

1. **5-step gate sequence** — divergence → noop → ratchet-up gates → cascade-revoke →
   signed Ledger entry. Each step fails closed; the first error short-circuits.
2. **Fail-closed default** — every check raises a typed error; the Ledger entry
   writes ONLY when steps 1-4 all pass. There is no silent-pass branch.
3. **Cascade-on-demotion** — every demotion path runs the cascade-revoke hook
   per agent_id provided by the caller, before the Ledger entry. The TrustStore
   adapter's `revoke()` is the production hook (T-01-14 cascade infrastructure).
4. **Signed posture_change Ledger entry** — wire shape per `specs/ledger.md`
   § posture_change (lines 239-253): `{type, schema_version, from_posture,
   to_posture, dimension_scope, trigger, evidence_ref, signed_by}`. The
   `signed_by` field is APPLICATION-level (`"genesis_key"`); the Ledger envelope
   itself carries the runtime device signature via `EnvoyLedger.append`.
5. **Posture-ratchet enforcement** — the per-transition authorship-threshold
   table per spec lines 35-39 is the load-bearing gate; `_required_authorship`
   is the single source of truth, not duplicated in tests.

Phase 01 narrow scope:

- The `cooling_off_active` boolean is INPUT to the gate; the cooling-off TIMER
  + window-management logic is Phase 03 (ritual surface in Weekly Posture Review).
- The `annual_decay` trigger is accepted in the trigger taxonomy (per spec line
  250) but NO Phase-01 caller emits it; Phase 03 implements the decay scheduler.
- Multi-step transitions (e.g. PSEUDO → DELEGATING in one call) are permitted but
  use the highest-threshold-on-path requirement; the spec does not forbid them.
- Shared Household composition per `specs/posture-ladder.md` § Shared Household
  semantics is OUT OF SCOPE — that's `effective_posture_for_composition` (a
  separate function, Phase 03+).
- **`envelope_edit` Ledger entry pairing shipped at T-02-33 (Tier 2 wiring).**
  Spec line 41 mandates that ratchet-up writes BOTH a `posture_change` entry
  AND an `envelope_edit` entry (because new posture is part of the envelope
  schema). T-02-33 closes the T-02-31 deferral via the `envelope` kwarg on
  `request_transition()` (typed as the `_PostureCarryingEnvelope` Protocol
  below) and Step 5b emission. Per `journal/0021-DECISION-t-02-33-envelope-
  edit-pairing-design.md`: kwarg-on-call (not constructor DI) — envelope is
  per-transition data, not gate-owned state. Ratchet-up with `envelope=None`
  raises `PostureRatchetEnvelopeMissingError` (no silent fallback per
  `rules/zero-tolerance.md` Rule 3). Pairing is asymmetric per spec § Ratchet-
  down lines 47-52: demotion emits ONLY `posture_change`, NOT `envelope_edit`.
  Original deferral journal: `journal/0020-DECISION-envelope-edit-deferred-
  to-tier-2.md`. Closure journal: `journal/0021-DECISION-t-02-33-envelope-
  edit-pairing-design.md`.

Rule mapping:
- `rules/zero-tolerance.md` Rule 2 — every typed error has a real raise site;
  no `NotImplementedError`; no silent pass; no fake-classification gate.
- `rules/zero-tolerance.md` Rule 3a — the `_revoke_hook` and `_ledger` accessors
  raise typed `RuntimeError` if missing rather than returning None silently.
- `rules/observability.md` Rule 8 — schema-revealing identifiers
  (`envelope_id_hash`) are at DEBUG; operational signals at INFO via counter-style
  log keys; divergence at WARN.
- `rules/security.md` § Multi-Site Kwarg Plumbing — every kwarg in
  `request_transition` is consumed inside the function body; none are
  accept-but-drop (Rule 3c discipline).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any, Optional, Protocol

# Module-scope import (security-reviewer F-5): the prior local-import inside
# the divergence branch was unnecessary defensive — `score.py` does NOT import
# from `posture_gate.py`, so module-scope import is structurally safe.
from envoy.authorship.score import AuthorshipScoreDivergenceError

if TYPE_CHECKING:
    # `bet12_emitter` imports `PostureLevel` from THIS module, so the forward
    # reference here is required to break the static-import cycle. Runtime
    # access is via the DI-supplied instance (`self._bet12_emitter`); no
    # runtime import of the class is needed.
    from envoy.authorship.bet12_emitter import BET12CadenceEmitter

logger = logging.getLogger(__name__)


# Bounds on `envelope_id_hash` per security-reviewer F-2 — the field is
# attacker-controlled (flows from a wire-form envelope's metadata) and lands
# in `extra=` keys on every divergence WARN + recompute DEBUG log line. Cap
# length to defend against log-volume amplification; restrict charset to
# alphanumeric + `:_-` to defend against log-injection / aggregator-side
# parser confusion. Matches the canonical hash shapes the project uses
# (`sha256:<hex>` family).
_ENVELOPE_ID_HASH_MAX_LEN = 128
_ENVELOPE_ID_HASH_PATTERN = re.compile(r"^[a-zA-Z0-9:_-]*$")


# Trust-boundary invariant: every `mutation.diff_hash` consumed verbatim into
# a device-signed envelope_edit Ledger entry MUST match `sha256:<64-hex>` per
# `specs/ledger.md` § envelope_edit § diff_hash. Validated at Step 5b before
# the gate signs the entry; rejects malformed values a malicious
# `_PostureCarryingEnvelope` adapter might try to inject (Round 1 /redteam F-2).
_SHA256_HEX_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


# Agent-id safety bounds for `revoke_on_demotion` per security-reviewer F-1 —
# matches the canonical defense `_validate_id_safety` at
# `envoy/trust/store.py:55` (intentionally NOT imported because that helper is
# `_`-prefixed module-private; replicating the contract here keeps PostureGate
# the boundary-of-record per `rules/security.md` § Multi-Site Kwarg Plumbing).
# Threats blocked: path traversal (`..`, `/`, `\`), null-byte truncation,
# control-character log injection, hidden-file shape (leading `.`), DoS via
# oversize identifier.
_AGENT_ID_MAX_LEN = 256


def _validate_agent_id(agent_id: str) -> None:
    """Reject agent_id strings that could enable path-traversal, null-byte,
    or log-injection attacks against the cascade-revoke hook surface.

    Mirrors `envoy/trust/store.py::_validate_id_safety` contract; replicated
    here because PostureGate is the gate boundary per `rules/security.md`
    § Multi-Site Kwarg Plumbing — defense-in-depth requires the gate to NOT
    rely on the downstream `_RevokeHook` implementation to validate. Any
    future caller wiring an alternative `_RevokeHook` (Tier 1 fakes,
    audit-only proxies, alternative Trust Stores) inherits the boundary
    check unconditionally.
    """
    if not isinstance(agent_id, str):
        raise ValueError(f"revoke_on_demotion entry must be str, got {type(agent_id).__name__}")
    if not agent_id:
        raise ValueError("revoke_on_demotion entry must be non-empty str")
    if len(agent_id) > _AGENT_ID_MAX_LEN:
        raise ValueError(
            f"revoke_on_demotion entry length {len(agent_id)} exceeds " f"max {_AGENT_ID_MAX_LEN}"
        )
    if agent_id.startswith("."):
        raise ValueError("revoke_on_demotion entry must not start with '.' (hidden-file shape)")
    if "\x00" in agent_id:
        raise ValueError("revoke_on_demotion entry contains null byte")
    if any(ord(ch) < 0x20 or 0x7F <= ord(ch) < 0xA0 for ch in agent_id):
        raise ValueError("revoke_on_demotion entry contains control character")
    if "/" in agent_id or "\\" in agent_id:
        raise ValueError("revoke_on_demotion entry contains path separator")
    if ".." in agent_id:
        raise ValueError("revoke_on_demotion entry contains '..' (path traversal)")


__all__ = [
    "PostureAuthorshipInsufficientError",
    "PostureChangeResult",
    "PostureCoolingOffActiveError",
    "PostureEnterpriseAutonomousForbidden",
    "PostureEnvelopeMutationInvariantError",
    "PostureEvidence",
    "PostureGate",
    "PostureGateError",
    "PostureGenesisGrantMissingError",
    "PostureLevel",
    "PostureMode",
    "PostureNoopError",
    "PostureRatchetEnvelopeMissingError",
]


# ---------------------------------------------------------------------------
# Canonical enums
# ---------------------------------------------------------------------------


class PostureLevel(IntEnum):
    """Canonical 5-tier autonomy ladder per `specs/posture-ladder.md` § Canonical enum.

    Integer ordering is LOAD-BEARING — `AUTONOMOUS > DELEGATING > SUPERVISED >
    TOOL > PSEUDO`. The `>=` comparisons appear in composition rules and
    posture-ratchet gates throughout the codebase. Wire format is the string
    name (e.g. `"DELEGATING"`); integer value is for internal comparisons only.
    """

    PSEUDO = 0
    TOOL = 1
    SUPERVISED = 2
    DELEGATING = 3
    AUTONOMOUS = 4


class PostureMode(str, Enum):
    """Personal vs enterprise posture-ratchet thresholds.

    Personal: N=3 for SUPERVISED→DELEGATING, N=5 for DELEGATING→AUTONOMOUS.
    Enterprise: N=5 for SUPERVISED→DELEGATING; AUTONOMOUS NOT reachable on
    shared templates per `specs/posture-ladder.md` line 39 +
    `specs/enterprise-deployment.md` § Posture-ratchet under enterprise mode.

    `str`-backed Enum for JSON-friendly serialization per `rules/eatp.md`
    § Module Structure.
    """

    PERSONAL = "personal"
    ENTERPRISE = "enterprise"


# Posture-change trigger values per `specs/ledger.md` § posture_change schema
# (lines 243-253). The Ledger entry's `trigger` field MUST be one of these.
_VALID_TRIGGERS: frozenset[str] = frozenset(
    {
        "user_request",
        "annual_decay",
        "enterprise_attestation",
        "weekly_review",
        "authorship_threshold",
    }
)


# Spec posture_change entry schema_version. Bump when the spec wire shape
# changes (parallel to `HaltedByRollbackRecord._SCHEMA_VERSION`).
_POSTURE_CHANGE_SCHEMA_VERSION = "1.0"


# Spec envelope_edit entry schema_version per `specs/ledger.md` § envelope_edit
# (lines 107-114). Wire shape: {type, schema_version, envelope_id, prior_version,
# new_version, diff_hash, rollback_grace_window_seconds, signed_by}.
_ENVELOPE_EDIT_SCHEMA_VERSION = "1.0"


# Default rollback grace window per `specs/envelope-model.md` § Error taxonomy
# § HaltedByRollbackError — the window during which an envelope_edit can be
# rolled back before downstream consumers commit to the new version. Phase 01
# narrow scope: fixed at 24 hours (86400 seconds). Phase 03 Weekly Posture
# Review ritual may override per-transition.
_DEFAULT_ROLLBACK_GRACE_WINDOW_SECONDS = 86400


# ---------------------------------------------------------------------------
# Evidence + result value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PostureEvidence:
    """Evidence consumed by the posture-ratchet gate.

    `authorship_score_stored` is the int signed at envelope-sign time
    (`metadata.authorship_score.authored_count` per `specs/envelope-model.md`
    § Schema). `authorship_score_recomputed` is the int produced by
    `recompute_authorship_counters(envelope, ledger_slice).authored_count` at
    request time. Mismatch raises `AuthorshipScoreDivergenceError` per spec
    § Stored vs recomputed (T-023 defense, retry: never).

    `envelope_id_hash` carries the envelope's content_hash truncated to the
    first 16 chars for log correlation per `rules/observability.md` Rule 8
    (schema-revealing identifiers redacted from operational logs). Empty
    string when the caller does not have an envelope_id (e.g. annual decay,
    where the gate fires without a specific envelope).
    """

    authorship_score_recomputed: int
    authorship_score_stored: int
    mode: PostureMode = PostureMode.PERSONAL
    genesis_signed_grant: bool = False
    cooling_off_active: bool = False
    envelope_id_hash: str = ""

    def __post_init__(self) -> None:
        # Strict type validation per security review M-02 / `rules/security.md`
        # § Multi-Site Kwarg Plumbing — wire-form payload coerced from JSON
        # MUST fail at the boundary, not silently downstream. Same defense as
        # `AuthorshipCounters.from_dict`.
        if not isinstance(self.authorship_score_recomputed, int) or isinstance(
            self.authorship_score_recomputed, bool
        ):
            raise TypeError(
                f"authorship_score_recomputed must be int, got "
                f"{type(self.authorship_score_recomputed).__name__}"
            )
        if not isinstance(self.authorship_score_stored, int) or isinstance(
            self.authorship_score_stored, bool
        ):
            raise TypeError(
                f"authorship_score_stored must be int, got "
                f"{type(self.authorship_score_stored).__name__}"
            )
        if self.authorship_score_recomputed < 0:
            raise ValueError(
                f"authorship_score_recomputed must be non-negative, got "
                f"{self.authorship_score_recomputed}"
            )
        if self.authorship_score_stored < 0:
            raise ValueError(
                f"authorship_score_stored must be non-negative, got "
                f"{self.authorship_score_stored}"
            )
        if not isinstance(self.mode, PostureMode):
            raise TypeError(f"mode must be PostureMode, got {type(self.mode).__name__}")
        if self.genesis_signed_grant is not True and self.genesis_signed_grant is not False:
            raise TypeError(
                f"genesis_signed_grant must be bool, got "
                f"{type(self.genesis_signed_grant).__name__}"
            )
        if self.cooling_off_active is not True and self.cooling_off_active is not False:
            raise TypeError(
                f"cooling_off_active must be bool, got " f"{type(self.cooling_off_active).__name__}"
            )
        if not isinstance(self.envelope_id_hash, str):
            raise TypeError(
                f"envelope_id_hash must be str, got {type(self.envelope_id_hash).__name__}"
            )
        # Bounds + charset check per security-reviewer F-2: prevents log-volume
        # amplification + log-injection through the structured `extra=` keys
        # at the divergence WARN + recompute DEBUG sites. Empty string remains
        # permitted (callers without an envelope context — e.g. annual decay).
        if len(self.envelope_id_hash) > _ENVELOPE_ID_HASH_MAX_LEN:
            raise ValueError(
                f"envelope_id_hash length {len(self.envelope_id_hash)} exceeds "
                f"max {_ENVELOPE_ID_HASH_MAX_LEN}"
            )
        if self.envelope_id_hash and not _ENVELOPE_ID_HASH_PATTERN.fullmatch(self.envelope_id_hash):
            raise ValueError(
                "envelope_id_hash must match [a-zA-Z0-9:_-]+ "
                "(canonical hash shape, e.g. 'sha256:<hex>')"
            )


@dataclass(frozen=True, slots=True)
class PostureChangeResult:
    """Result of a successful posture transition.

    `new_level` is the resulting posture (ratchet-up: `target`; ratchet-down:
    `target`). `ledger_entry_id` is the `entry_id` returned by `EnvoyLedger.append`
    — the SHA-256 hash chain entry id of the signed posture_change record.
    """

    new_level: PostureLevel
    ledger_entry_id: str


# ---------------------------------------------------------------------------
# Typed errors (per `specs/posture-ladder.md` § Error taxonomy)
# ---------------------------------------------------------------------------


class PostureGateError(Exception):
    """Base class for all posture-gate errors. Subclasses carry a plain-language
    `user_message` per `rules/communication.md` so non-technical surfaces
    (Daily Digest, Channel adapters, Weekly Posture Review) can render the
    error without re-deriving the explanation.
    """


class PostureNoopError(PostureGateError):
    """Target == current — no-op transition rejected.

    Per `specs/posture-ladder.md` § Error taxonomy: "User action: None; silent
    on CLI, suppress on surface." The raise is structurally meaningful (the
    gate refuses to write a no-op Ledger entry) but the surface should not
    treat this as a user-facing failure.
    """

    def __init__(self, level: PostureLevel) -> None:
        self.level = level
        self.user_message = "You're already at the posture you requested. No change was made."
        super().__init__(f"PostureNoopError: target == current ({level.name})")


class PostureAuthorshipInsufficientError(PostureGateError):
    """Ratchet-up requested but AuthorshipScore below threshold (T-023 defense)."""

    def __init__(
        self,
        *,
        current: PostureLevel,
        target: PostureLevel,
        have: int,
        need: int,
    ) -> None:
        self.current = current
        self.target = target
        self.have = have
        self.need = need
        plural = "s" if need != 1 else ""
        self.user_message = (
            f"To move from {current.name} to {target.name}, you need at least "
            f"{need} authored constraint{plural}. You currently have {have}. "
            "You can author more during your next Grant Moment to unlock this "
            "transition."
        )
        super().__init__(
            f"PostureAuthorshipInsufficientError: {current.name}->{target.name} "
            f"have={have} need={need}"
        )


class PostureRatchetEnvelopeMissingError(PostureGateError):
    """Ratchet-up requested without an envelope to bump.

    Per `specs/posture-ladder.md` § Ratchet-up requirement #3, every
    ratchet-up MUST emit a paired `envelope_edit` Ledger entry binding
    the new posture to a specific envelope version bump. A caller that
    invokes `request_transition()` with `target > current` and
    `envelope=None` is structurally incomplete — the gate cannot mint
    the `envelope_edit` entry. Per `rules/zero-tolerance.md` Rule 3
    (no silent fallbacks), the gate raises this typed error rather than
    silently skipping Step 5b.

    Ratchet-down paths legitimately pass `envelope=None` — demotion
    emits ONLY `posture_change` per spec § Ratchet-down lines 47-52.
    """

    def __init__(self, *, current: PostureLevel, target: PostureLevel) -> None:
        self.current = current
        self.target = target
        self.user_message = (
            f"Moving from {current.name} to {target.name} needs the current "
            "envelope to bind the new posture to. The session that triggered "
            "this transition didn't supply one — please re-open Weekly Posture "
            "Review and try again from there."
        )
        super().__init__(
            f"PostureRatchetEnvelopeMissingError: {current.name}->{target.name} "
            "ratchet-up requires envelope=... (spec line 41 + T-02-33)"
        )


class PostureEnvelopeMutationInvariantError(PostureGateError):
    """Mutation result violated a Step 5b trust-boundary invariant.

    Per Round 1 /redteam F-2: PostureGate device-signs the envelope_edit
    Ledger entry by consuming mutation fields (`envelope_id`, `new_version`,
    `diff_hash`) verbatim. A malicious or buggy `_PostureCarryingEnvelope`
    adapter could otherwise inject forged values (mismatched envelope_id,
    regressed/skipped version, malformed diff_hash) into the device-signed
    entry. Step 5b validates these invariants BEFORE the gate signs.

    The runtime check is the structural defense per `rules/zero-tolerance.md`
    Rule 3 — no silent fallback path where a malformed mutation lands as
    a signed Ledger entry.
    """

    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        self.user_message = (
            "There was a problem confirming the envelope update for this "
            "posture change. The change has not been recorded — please "
            "re-open Weekly Posture Review and try again."
        )
        super().__init__(f"PostureEnvelopeMutationInvariantError: {reason}")


class PostureGenesisGrantMissingError(PostureGateError):
    """Ratchet-up ceremony not co-signed by Genesis key."""

    def __init__(self, *, current: PostureLevel, target: PostureLevel) -> None:
        self.current = current
        self.target = target
        self.user_message = (
            f"Moving from {current.name} to {target.name} needs your Genesis-key "
            "co-signature. Please re-open Weekly Posture Review and unlock with "
            "your passphrase to confirm."
        )
        super().__init__(f"PostureGenesisGrantMissingError: {current.name}->{target.name}")


class PostureCoolingOffActiveError(PostureGateError):
    """Ratchet-up within cooling-off window (24h after demotion per spec)."""

    def __init__(self, *, current: PostureLevel, target: PostureLevel) -> None:
        self.current = current
        self.target = target
        self.user_message = (
            "There's a cool-off window after a recent posture demotion. The "
            "window will expire and let you re-promote — your Daily Digest "
            "shows when it's available."
        )
        super().__init__(f"PostureCoolingOffActiveError: {current.name}->{target.name}")


class PostureEnterpriseAutonomousForbidden(PostureGateError):
    """Ratchet to AUTONOMOUS under enterprise-shared template (spec line 39)."""

    def __init__(self) -> None:
        self.user_message = (
            "Your enterprise template doesn't allow AUTONOMOUS posture on shared "
            "templates. This is enterprise policy; ask your administrator if the "
            "policy can change."
        )
        super().__init__(
            "PostureEnterpriseAutonomousForbidden: AUTONOMOUS forbidden under "
            "enterprise mode (spec line 39)"
        )


# ---------------------------------------------------------------------------
# Posture-ratchet authorship-threshold table
# ---------------------------------------------------------------------------


def _required_authorship(
    current: PostureLevel,
    target: PostureLevel,
    mode: PostureMode,
) -> int:
    """Return the authored-constraint count required for `current → target`.

    Per `specs/posture-ladder.md` § Ratchet-up:

    - PSEUDO → TOOL: N=0 (no authorship required; default entry).
    - TOOL → SUPERVISED: N=1.
    - SUPERVISED → DELEGATING: N=3 personal, N=5 enterprise.
    - DELEGATING → AUTONOMOUS: N=5 (personal only — enterprise raises
      `PostureEnterpriseAutonomousForbidden` BEFORE this lookup).

    Multi-step transitions (e.g. PSEUDO → DELEGATING in one call) require the
    HIGHEST single-step threshold along the path: the sum of "each step
    requires its own threshold" is achieved by gating on the highest one
    because each lower-step threshold is structurally subsumed (TOOL→SUPERVISED
    needs N=1, SUPERVISED→DELEGATING needs N=3, so PSEUDO→DELEGATING needs
    max(0,1,3)=3 personal / max(0,1,5)=5 enterprise). This matches spec
    intent line 31 "ratchet-up requires ALL of" — the highest threshold is
    the binding one.

    Same target, different paths produce the same requirement (path-independence
    is a structural invariant the test pins).

    Precondition: callers gate on `target > current` (ratchet-up) before
    invoking. The function is also tested directly with single-step pairs
    that match the explicit table at the top.
    """
    # Single-step deltas first (most common).
    if (current, target) == (PostureLevel.PSEUDO, PostureLevel.TOOL):
        return 0
    if (current, target) == (PostureLevel.TOOL, PostureLevel.SUPERVISED):
        return 1
    if (current, target) == (PostureLevel.SUPERVISED, PostureLevel.DELEGATING):
        return 5 if mode is PostureMode.ENTERPRISE else 3
    if (current, target) == (PostureLevel.DELEGATING, PostureLevel.AUTONOMOUS):
        return 5

    # Multi-step paths: highest single-step threshold along the path. Only
    # SUPERVISED/DELEGATING/AUTONOMOUS targets are reachable here — TOOL/PSEUDO
    # targets cannot satisfy `target > current` for any current not already
    # handled by the single-step branches above.
    if target is PostureLevel.AUTONOMOUS:
        return 5
    if target is PostureLevel.DELEGATING:
        return 5 if mode is PostureMode.ENTERPRISE else 3
    if target is PostureLevel.SUPERVISED:
        return 1
    # Defensive guard for completeness; structurally unreachable under the
    # `target > current` precondition.
    raise ValueError(f"_required_authorship: unreachable {current.name}->{target.name}")


# ---------------------------------------------------------------------------
# Collaborator Protocols (DI surfaces — no concrete dep on EnvoyLedger / TrustStoreAdapter)
# ---------------------------------------------------------------------------


class _LedgerProtocol(Protocol):
    """Minimum Ledger surface PostureGate consumes — `EnvoyLedger.append`."""

    async def append(
        self,
        *,
        entry_type: str,
        content: dict[str, Any],
        intent_id: Optional[str] = None,
        content_trust_level: str = "system",
    ) -> str: ...


class _RevokeHook(Protocol):
    """Cascade-revoke hook signature — matches `TrustStoreAdapter.revoke`."""

    async def __call__(
        self,
        *,
        agent_id: str,
        reason: str,
        revoked_by: str,
    ) -> object: ...


class _PostureMutationResult(Protocol):
    """The structural shape `_PostureCarryingEnvelope.mutate_for_posture_level()`
    returns. Carried as a Protocol so any same-shaped value type satisfies it
    (real `EnvelopeConfig`-wrapping adapters; Tier 1 frozen-dataclass fakes).

    Per `specs/ledger.md` § envelope_edit (lines 107-114):
    - `envelope_id` — the uuid of the envelope this mutation belongs to.
      PostureGate verifies it matches the input envelope's envelope_id at
      Step 5b per Round 1 /redteam F-2 (trust-boundary invariant).
    - `new_version` — the envelope_version after the bump (= prior_version + 1).
    - `new_content_hash` — sha256 over the new canonical_bytes.
    - `diff_hash` — sha256 binding prior canonical bytes to new canonical
      bytes; the field name is per spec.
    - `new_posture_level` — the canonical PostureLevel enum NAME (wire form).
    - `new_envelope` — the mutated envelope object (opaque to PostureGate;
      the caller consumes it on success to advance its own envelope reference).
    """

    @property
    def envelope_id(self) -> str: ...

    @property
    def new_version(self) -> int: ...

    @property
    def new_content_hash(self) -> str: ...

    @property
    def diff_hash(self) -> str: ...

    @property
    def new_posture_level(self) -> str: ...

    @property
    def new_envelope(self) -> object: ...


def _is_posture_carrying_envelope(obj: object) -> bool:
    """Structural Protocol conformance check for the `envelope` kwarg per
    Round 1 /redteam F-1 (MED).

    `_PostureCarryingEnvelope` is a structural (PEP-544) Protocol — any
    duck-typed object that exposes the read state + mutate operation
    satisfies it at static-checking time, but Python's runtime never
    enforces structural Protocols by default. A caller that hands the
    gate a wrong-shape object (a string, a dict, an arbitrary value
    missing the required attributes) would otherwise produce a deep
    `AttributeError` at Step 5b's `envelope.mutate_for_posture_level(...)`
    call site — blocking the request mid-Ledger-sequence with an opaque
    stack trace.

    The runtime check converts that into a loud `TypeError` raised at
    the kwarg boundary BEFORE any of the 5-step sequence runs. Same
    failure-mode class as the existing `PostureEvidence.__post_init__`
    type validation (`rules/security.md` § Multi-Site Kwarg Plumbing).
    """
    return (
        hasattr(obj, "envelope_id")
        and hasattr(obj, "prior_version")
        and hasattr(obj, "prior_content_hash")
        and hasattr(obj, "prior_posture_level")
        and callable(getattr(obj, "mutate_for_posture_level", None))
    )


class _PostureCarryingEnvelope(Protocol):
    """Minimum envelope surface PostureGate consumes on ratchet-up.

    Per `journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md`, the
    Protocol is narrow so any envelope implementation (real `EnvelopeConfig`
    + adapter, Tier-1 frozen-dataclass fake, Tier-2 wrapper around the real
    `EnvelopeCompiler` output) satisfies it without inheritance.

    Read state — what the gate consumes BEFORE the mutation:
    - `envelope_id` — uuid; persisted in the envelope_edit entry.
    - `prior_version` — int; the version BEFORE the bump.
    - `prior_content_hash` — sha256 hex; used in audit chain reconstruction.
    - `prior_posture_level` — canonical enum NAME ("PSEUDO" / etc.); pinned
      so a future audit can verify the transition matches the envelope-side
      state at the moment of mutation.

    Mutate operation — what the gate calls ONCE per accepted ratchet-up:
    - `mutate_for_posture_level(new_level)` returns a `_PostureMutationResult`
      with the new version, new content hash, diff hash, and new envelope.
      The gate consumes the result's fields verbatim for the envelope_edit
      entry; it does NOT introspect the new envelope itself.

    Per `rules/zero-tolerance.md` Rule 2 (no stubs): the Protocol is
    structural, so a fake `mutate_for_posture_level` returning bogus values
    would deceive PostureGate — but Tier 2 wiring tests (T-02-33) verify
    the real adapter against real canonical-bytes pipeline, closing the
    deceit window structurally.

    Side-effect-free attribute reads (R2-F2 contract — IMPLEMENTORS):

    Implementations of this Protocol MUST have side-effect-free attribute
    reads. The gate's runtime conformance check (`_is_posture_carrying_envelope`)
    inspects this Protocol's attributes via `hasattr()` / `getattr()` —
    operations that invoke each attribute's descriptor / `__getattribute__`
    path on every kwarg-boundary check (every `request_transition()` call,
    including ratchet-down paths where the envelope is supplied
    informationally but never mutated).

    Implementations MUST therefore NOT, on attribute read:

    - Perform I/O (file read, network call, DB query)
    - Acquire locks (threading / asyncio primitives)
    - Emit log records
    - Mutate observable state
    - Wake background tasks

    The gate cannot enforce side-effect-freeness at runtime (Python's
    structural Protocol contract gives no hook); the discipline is on the
    IMPLEMENTOR. The Tier 1 spy-adapter test
    (`TestPostureCarryingEnvelopeProtocolDiscipline`) bounds the gate's
    attribute-read surface so a future refactor that adds spurious
    `hasattr()` / `getattr()` calls fails loudly.
    """

    @property
    def envelope_id(self) -> str: ...

    @property
    def prior_version(self) -> int: ...

    @property
    def prior_content_hash(self) -> str: ...

    @property
    def prior_posture_level(self) -> str: ...

    def mutate_for_posture_level(self, new_level: "PostureLevel") -> _PostureMutationResult: ...


# ---------------------------------------------------------------------------
# PostureGate — the 5-step gate
# ---------------------------------------------------------------------------


class PostureGate:
    """Posture transition gate — 5-step fail-closed enforcement (T-02-31).

    Per `specs/posture-ladder.md` § Algorithm + the 5 invariants in
    `02-wave-2-...md` § T-02-31. The gate sequence is:

        Step 1  → divergence check (T-023 defense)
        Step 2  → noop check (target == current)
        Step 3  → ratchet-up gates [promotion only]
                  3a. enterprise AUTONOMOUS forbidden
                  3b. cooling-off active
                  3c. genesis-signed grant
                  3d. authorship-score threshold
                  3e. envelope present (T-02-33) — typed error
                      `PostureRatchetEnvelopeMissingError` if absent
        Step 4  → cascade-revoke hook [demotion only]
        Step 5a → signed posture_change Ledger entry
        Step 5b → signed envelope_edit Ledger entry [ratchet-up only,
                  T-02-33] — paired with Step 5a via append order
        Step 5+ → BET-12 cadence emission (T-02-32)

    Each step fails closed: the first error short-circuits the rest. The
    Ledger entries only write when all prior steps passed. This is the
    posture-side defense in depth — `rules/zero-tolerance.md` Rule 2 (no
    fake-classification gates, every accepted dispatch value has a real
    branch) AND Rule 3 (no silent fallbacks).

    Pairing asymmetry: Step 5b runs on ratchet-up ONLY. Per spec § Ratchet-
    down lines 47-52, demotion emits ONLY `posture_change`. The asymmetry
    is intentional — envelope_edit binds new posture to a new envelope
    version; demotion doesn't bump the envelope (spec doesn't mandate it).

    Construction (DI):

        gate = PostureGate(
            ledger=envoy_ledger,             # implements `_LedgerProtocol`
            revoke_hook=trust_store.revoke,  # implements `_RevokeHook`
        )

    The DI surfaces (Protocol-typed) keep this module independent of the
    concrete `EnvoyLedger` / `TrustStoreAdapter` import graph — Tier 1 tests
    pass in fakes; Tier 2 wiring (T-02-33) runs against real instances.
    """

    def __init__(
        self,
        *,
        ledger: _LedgerProtocol,
        revoke_hook: _RevokeHook,
        bet12_emitter: "BET12CadenceEmitter",
    ) -> None:
        if ledger is None:
            raise ValueError("ledger is required (no None default)")
        if revoke_hook is None:
            raise ValueError("revoke_hook is required (no None default)")
        if bet12_emitter is None:
            raise ValueError("bet12_emitter is required (no None default)")
        self._ledger = ledger
        self._revoke_hook = revoke_hook
        self._bet12_emitter = bet12_emitter

    async def request_transition(
        self,
        *,
        current: PostureLevel,
        target: PostureLevel,
        evidence: PostureEvidence,
        principal_id: str,
        trigger: str = "user_request",
        revoke_on_demotion: tuple[str, ...] = (),
        days_at_current_posture: float = 0.0,
        envelope: Optional[_PostureCarryingEnvelope] = None,
    ) -> PostureChangeResult:
        """Request a posture transition; raises on any failed gate.

        Args:
            current: present posture level (typically read from envelope or
                Trust Store at request time).
            target: requested posture level.
            evidence: `PostureEvidence` carrying authorship counts, mode,
                grant + cooling-off flags.
            principal_id: subject of the transition; hashed by
                `BET12CadenceEmitter` per `rules/event-payload-classification.md`
                Rule 2 before the cohort cadence event is emitted (T-02-32).
            trigger: one of `_VALID_TRIGGERS`. Per `specs/ledger.md`
                § posture_change schema.
            revoke_on_demotion: tuple of `agent_id` strings the cascade-revoke
                hook will revoke on demotion. Empty tuple is permitted (caller
                may decide no delegations need explicit revocation, e.g.
                annual decay where no standing delegations exist). Per
                security-reviewer F-3: caller MUST treat retry as idempotent —
                if the revoke hook raises mid-iteration, prior agent_ids in
                the tuple have ALREADY been revoked (no rollback). On retry,
                those agent_ids will be revoked again. The downstream
                `TrustStoreAdapter.revoke` is itself idempotent (dedup by
                cached `RevocationResult` per agent_id) so retry is safe at
                the Trust Store layer.
            days_at_current_posture: time at `current` level for the BET-12
                cadence event. Phase 03 Weekly Posture Review computes from
                PostureStore history; Phase 01 callers may pass 0.0 if not
                tracked (the emitter rejects negative values).
            envelope: REQUIRED on ratchet-up; ignored on ratchet-down /
                annual-decay paths. Per `specs/posture-ladder.md` § Ratchet-
                up requirement #3 + T-02-33 (per `journal/0021-DECISION-...md`),
                every accepted ratchet-up emits a paired `envelope_edit`
                Ledger entry binding the new posture to a specific envelope
                version bump. Caller passing `envelope=None` on a ratchet-up
                raises `PostureRatchetEnvelopeMissingError` (Step 3e). Per
                `rules/zero-tolerance.md` Rule 3 — no silent fallback to
                "skip Step 5b" because the runtime gate is the structural
                defense.

        Returns:
            `PostureChangeResult(new_level, ledger_entry_id)` on success.
            `ledger_entry_id` is the entry_id of the `posture_change` entry
            (Step 5a); the paired `envelope_edit` (Step 5b) has its own
            entry_id which a future API may surface — Phase 01 narrow scope
            returns only the posture_change id as the canonical handle.

        Raises:
            `AuthorshipScoreDivergenceError` (Step 1).
            `PostureNoopError` (Step 2).
            `PostureEnterpriseAutonomousForbidden` (Step 3a).
            `PostureCoolingOffActiveError` (Step 3b).
            `PostureGenesisGrantMissingError` (Step 3c).
            `PostureAuthorshipInsufficientError` (Step 3d).
            `PostureRatchetEnvelopeMissingError` (Step 3e — ratchet-up
                with envelope=None).
            `TypeError` / `ValueError` on shape-invalid inputs.
        """
        # Input validation — typed errors per `rules/security.md` § Input Validation
        # AND `rules/zero-tolerance.md` Rule 2 (every accepted dispatch value
        # has a real branch — `trigger` is a `str` here but membership-checked
        # against `_VALID_TRIGGERS`, so an invalid trigger fails loudly rather
        # than silently writing a non-spec wire-form).
        if not isinstance(current, PostureLevel):
            raise TypeError(f"current must be PostureLevel, got {type(current).__name__}")
        if not isinstance(target, PostureLevel):
            raise TypeError(f"target must be PostureLevel, got {type(target).__name__}")
        if not isinstance(evidence, PostureEvidence):
            raise TypeError(f"evidence must be PostureEvidence, got {type(evidence).__name__}")
        if trigger not in _VALID_TRIGGERS:
            raise ValueError(
                f"trigger must be one of {sorted(_VALID_TRIGGERS)} per "
                f"specs/ledger.md § posture_change schema, got {trigger!r}"
            )
        if not isinstance(revoke_on_demotion, tuple):
            raise TypeError(
                f"revoke_on_demotion must be tuple of str, got "
                f"{type(revoke_on_demotion).__name__}"
            )

        # Round 1 /redteam F-1 (MED): _PostureCarryingEnvelope is a structural
        # Protocol; Python doesn't enforce it at runtime. A duck-typed object
        # missing required attributes would otherwise crash mid-Step-5b with
        # an opaque AttributeError. Reject at the kwarg boundary instead.
        if envelope is not None and not _is_posture_carrying_envelope(envelope):
            raise TypeError(
                "envelope must conform to _PostureCarryingEnvelope Protocol "
                "(must expose envelope_id, prior_version, prior_content_hash, "
                "prior_posture_level, and a callable mutate_for_posture_level); "
                f"got {type(envelope).__name__}"
            )

        # ----- STEP 1: divergence check (T-023 defense) -----
        # Per `specs/authorship-score.md` § Stored vs recomputed: stored at
        # envelope-sign time MUST match runtime recompute; mismatch is an
        # audit alert, never auto-recovered.
        if evidence.authorship_score_stored != evidence.authorship_score_recomputed:
            logger.warning(
                "authorship.divergence",
                extra={
                    "envelope_id_hash": evidence.envelope_id_hash,
                    "stored": evidence.authorship_score_stored,
                    "recomputed": evidence.authorship_score_recomputed,
                },
            )
            raise AuthorshipScoreDivergenceError(
                stored=evidence.authorship_score_stored,
                recomputed=evidence.authorship_score_recomputed,
                envelope_id=evidence.envelope_id_hash,
            )

        # Normal recompute path at DEBUG (schema-revealing identifier — `rules/observability.md`
        # Rule 8). Operators get the operational signal at the divergence WARN
        # above when something is wrong; the per-request DEBUG line is for
        # triage when DEBUG sampling is enabled.
        logger.debug(
            "authorship.recompute",
            extra={
                "envelope_id_hash": evidence.envelope_id_hash,
                "authored_count": evidence.authorship_score_recomputed,
            },
        )

        # ----- STEP 2: noop check -----
        if target == current:
            raise PostureNoopError(current)

        # ----- STEP 3: ratchet-up gates (promotion only) -----
        if target > current:
            # 3a: enterprise AUTONOMOUS forbidden FIRST so we don't call the
            # threshold lookup with a target the spec forbids outright.
            if target is PostureLevel.AUTONOMOUS and evidence.mode is PostureMode.ENTERPRISE:
                raise PostureEnterpriseAutonomousForbidden()

            # 3b: cooling-off check. Cool-off is a state attribute the caller
            # supplies; this gate enforces it without owning the timer (Phase 03
            # owns the cool-off window calculation).
            if evidence.cooling_off_active:
                raise PostureCoolingOffActiveError(current=current, target=target)

            # 3c: genesis-signed grant check. Ratchet-up MUST be co-signed by
            # Genesis (spec line 40). The boolean is set True ONLY by the
            # Weekly Posture Review ritual after passphrase unlock.
            if not evidence.genesis_signed_grant:
                raise PostureGenesisGrantMissingError(current=current, target=target)

            # 3d: authorship-score threshold (the load-bearing posture-ratchet gate).
            need = _required_authorship(current, target, evidence.mode)
            if evidence.authorship_score_recomputed < need:
                raise PostureAuthorshipInsufficientError(
                    current=current,
                    target=target,
                    have=evidence.authorship_score_recomputed,
                    need=need,
                )

            # 3e: envelope-present check (T-02-33). Per `specs/posture-ladder.md`
            # § Ratchet-up requirement #3 + `journal/0021-DECISION-...md`,
            # every ratchet-up MUST emit a paired `envelope_edit` Ledger
            # entry. The gate fails closed (typed error, no silent skip) if
            # the caller didn't supply an envelope to bump. Per
            # `rules/zero-tolerance.md` Rule 3, the runtime check is the
            # structural defense — Optional kwarg + runtime fail-closed is
            # the documented "kwarg-on-call" disposition from journal/0021.
            if envelope is None:
                raise PostureRatchetEnvelopeMissingError(current=current, target=target)

        # ----- STEP 4: cascade-revoke hook (demotion only) -----
        # Per `specs/posture-ladder.md` § Ratchet-down: "Demotion may happen:
        # User-initiated; Automatic on kill-criterion hit; Automatic on annual
        # decay" — demotion never raises, but the standing delegations issued
        # under the higher posture MUST be revoked. The caller passes the list
        # of agent_ids (typically: every agent under standing delegation that
        # exceeded the new posture's authority). PostureGate iterates the
        # supplied tuple and calls the cascade-revoke hook per-agent; the hook
        # itself (TrustStoreAdapter.revoke) cascades to descendants.
        if target < current:
            for agent_id in revoke_on_demotion:
                # Identifier-safety check at the gate boundary per
                # security-reviewer F-1 — defense-in-depth: do NOT rely on
                # the downstream `_RevokeHook` implementation to validate.
                _validate_agent_id(agent_id)
                await self._revoke_hook(
                    agent_id=agent_id,
                    reason=f"posture_demotion:{current.name}->{target.name}",
                    revoked_by="posture_gate",
                )

        # ----- STEP 5-PRECONDITIONS (ratchet-up only, R2-F1 closure) -----
        # Per Round 2 /redteam F-1 (HIGH): the F-2 trust-boundary invariant
        # checks were previously interleaved BETWEEN Step 5a's posture_change
        # append and Step 5b's envelope_edit append. On any invariant
        # violation the posture_change committed to the Ledger while the
        # paired envelope_edit never appended — an orphan entry violating
        # `specs/posture-ladder.md` § Ratchet-up requirement #3 ("any
        # posture change is an `envelope_edit`") and `rules/zero-tolerance.md`
        # Rule 3 (no silent fallbacks at the contract level). Same failure
        # mode class as Round 1 F-3, reintroduced when the F-2 invariants
        # landed.
        #
        # Structural defense: compute the mutation AND validate every F-2
        # invariant BEFORE Step 5a appends anything. On invariant violation
        # zero Ledger entries land — the application-level pairing
        # contract is atomic and fail-closed.
        #
        # Note: this closure addresses APPLICATION-level invariant
        # violations (mutation result shape). TRANSIENT Ledger failures
        # BETWEEN Step 5a and Step 5b (e.g. the second append raises
        # mid-pair) are a different bug class and require Ledger-level
        # transactional support; tracked at the F-001 follow-up issue.
        mutation = None
        envelope_edit_content: Optional[dict[str, Any]] = None
        if target > current:
            # MyPy narrows `envelope` to non-None via the Step 3e raise.
            assert envelope is not None  # nosec — narrowing assertion, Step 3e enforces
            mutation = envelope.mutate_for_posture_level(target)
            # Trust-boundary invariants per Round 1 /redteam F-2: PostureGate
            # device-signs the envelope_edit Ledger entry by consuming the
            # mutation fields verbatim. Without these checks, a malicious
            # `_PostureCarryingEnvelope` adapter could inject (a) a swapped
            # envelope_id, (b) a regressed/skipped version, OR (c) a
            # malformed diff_hash — all forwarded straight into the
            # device-signed entry. Validation BEFORE Step 5a's posture_change
            # append closes both the forge window AND the orphan-
            # posture_change window per `rules/zero-tolerance.md` Rule 3.
            if mutation.envelope_id != envelope.envelope_id:
                raise PostureEnvelopeMutationInvariantError(
                    reason=(
                        f"mutation.envelope_id mismatch: "
                        f"expected {envelope.envelope_id!r}, "
                        f"got {mutation.envelope_id!r}"
                    )
                )
            if mutation.new_version != envelope.prior_version + 1:
                raise PostureEnvelopeMutationInvariantError(
                    reason=(
                        f"mutation.new_version must be prior_version+1: "
                        f"prior={envelope.prior_version}, "
                        f"new={mutation.new_version}"
                    )
                )
            if not _SHA256_HEX_PATTERN.fullmatch(mutation.diff_hash):
                raise PostureEnvelopeMutationInvariantError(
                    reason=(
                        f"mutation.diff_hash must match 'sha256:<64-hex>' per "
                        f"specs/ledger.md § envelope_edit, got "
                        f"{mutation.diff_hash!r}"
                    )
                )
            # Build the envelope_edit content NOW (before any append) so
            # Step 5b is purely a Ledger write with no further computation
            # between the paired appends.
            envelope_edit_content = {
                "schema_version": _ENVELOPE_EDIT_SCHEMA_VERSION,
                "envelope_id": envelope.envelope_id,
                "prior_version": envelope.prior_version,
                "new_version": mutation.new_version,
                "diff_hash": mutation.diff_hash,
                "rollback_grace_window_seconds": _DEFAULT_ROLLBACK_GRACE_WINDOW_SECONDS,
                "signed_by": "delegation_key",
            }

        # ----- STEP 5a: signed posture_change Ledger entry -----
        # Wire shape per `specs/ledger.md` § posture_change schema (lines 243-253):
        # `{type, schema_version, from_posture, to_posture, dimension_scope,
        # trigger, evidence_ref, signed_by}`. The `signed_by` field is
        # APPLICATION-level identifying the authorizing key class (`"genesis_key"`);
        # the Ledger envelope itself adds the runtime device signature
        # at `EnvoyLedger.append` via `EntryEnvelope`.
        content: dict[str, Any] = {
            "schema_version": _POSTURE_CHANGE_SCHEMA_VERSION,
            "from_posture": current.name,
            "to_posture": target.name,
            # Phase 01 narrow scope: only `global` dimension transitions ship.
            # Per-dimension scoping (e.g. promote operational only) is Phase 03
            # per `specs/posture-ladder.md` § Per-tier semantics.
            "dimension_scope": "global",
            "trigger": trigger,
            # `evidence_ref` is a future-phase pointer (Ledger entry id of
            # the supporting evidence; e.g. the Weekly Posture Review ritual
            # entry that authorized this transition). Phase 01 leaves it null
            # — Phase 03 wires WPR ritual records.
            "evidence_ref": None,
            "signed_by": "genesis_key",
        }
        entry_id = await self._ledger.append(
            entry_type="posture_change",
            content=content,
        )

        logger.info(
            "posture.transition",
            extra={
                "from_posture": current.name,
                "to_posture": target.name,
                "trigger": trigger,
                "ledger_entry_id": entry_id,
            },
        )

        # ----- STEP 5b: signed envelope_edit Ledger entry (ratchet-up only, T-02-33) -----
        # Per `specs/posture-ladder.md` § Ratchet-up requirement #3 + `specs/
        # ledger.md` § envelope_edit (lines 107-114) + `journal/0021-DECISION-
        # t-02-33-envelope-edit-pairing-design.md`. The pairing is asymmetric:
        # envelope_edit fires ONLY on ratchet-up. Demotion paths skip Step 5b
        # cleanly because envelope is None (and the gate already raised Step
        # 3e if a caller passed envelope=None on a ratchet-up).
        #
        # Wire shape per spec L107-114: {type, schema_version, envelope_id,
        # prior_version, new_version, diff_hash, rollback_grace_window_seconds,
        # signed_by}. signed_by="delegation_key" per spec L113 — envelope_edit
        # entries are application-signed by the delegation key (the gate's
        # entry envelope itself is device-signed by EnvoyLedger.append).
        #
        # R2-F1 closure: the mutation compute + F-2 invariant validation
        # ran as PRECONDITIONS above (Step 5-PRECONDITIONS). By the time
        # control reaches here, `envelope_edit_content` is fully built and
        # Step 5b is purely the paired Ledger append.
        if target > current:
            assert envelope is not None  # nosec — narrowing, Step 3e enforces
            assert mutation is not None  # nosec — set in the preconditions block
            assert envelope_edit_content is not None  # nosec — set in preconditions
            envelope_edit_entry_id = await self._ledger.append(
                entry_type="envelope_edit",
                content=envelope_edit_content,
            )
            logger.info(
                "posture.envelope_edit",
                extra={
                    "envelope_id": envelope.envelope_id,
                    "prior_version": envelope.prior_version,
                    "new_version": mutation.new_version,
                    "ledger_entry_id": envelope_edit_entry_id,
                    "posture_change_ledger_entry_id": entry_id,
                },
            )

        # ----- STEP 5+: BET-12 cadence emission (T-02-32) -----
        # Per `01-analysis/09-authorship-score-implementation.md` § 3.3 +
        # `briefs/00-phase-01-mvp-scope.md` § Phase 01 invariants #3,
        # the BET-12 emitter fires on every transition the gate accepts.
        # Per `rules/orphan-detection.md` Rule 1, this IS the production
        # call site that prevents the emitter from being an orphan facade.
        # Cohort cadence carries (from, to, hashed principal_id, days at
        # current posture, authored count at transition) — NOT envelope
        # hash, NOT authored_constraints names, per
        # `rules/event-payload-classification.md` Rule 3.
        await self._bet12_emitter.emit(
            principal_id=principal_id,
            from_level=current,
            to_level=target,
            days_at_current_posture=days_at_current_posture,
            authored_count_at_transition=evidence.authorship_score_recomputed,
        )

        return PostureChangeResult(
            new_level=target,
            ledger_entry_id=entry_id,
        )
