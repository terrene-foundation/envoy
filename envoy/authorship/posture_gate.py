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
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


__all__ = [
    "PostureAuthorshipInsufficientError",
    "PostureChangeResult",
    "PostureCoolingOffActiveError",
    "PostureEnterpriseAutonomousForbidden",
    "PostureEvidence",
    "PostureGate",
    "PostureGateError",
    "PostureGenesisGrantMissingError",
    "PostureLevel",
    "PostureMode",
    "PostureNoopError",
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
        content: dict,
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


# ---------------------------------------------------------------------------
# PostureGate — the 5-step gate
# ---------------------------------------------------------------------------


class PostureGate:
    """Posture transition gate — 5-step fail-closed enforcement (T-02-31).

    Per `specs/posture-ladder.md` § Algorithm + the 5 invariants in
    `02-wave-2-...md` § T-02-31. The gate sequence is:

        Step 1 → divergence check (T-023 defense)
        Step 2 → noop check (target == current)
        Step 3 → ratchet-up gates [promotion only]
                 3a. enterprise AUTONOMOUS forbidden
                 3b. cooling-off active
                 3c. genesis-signed grant
                 3d. authorship-score threshold
        Step 4 → cascade-revoke hook [demotion only]
        Step 5 → signed posture_change Ledger entry

    Each step fails closed: the first error short-circuits the rest. The
    Ledger entry only writes when all prior steps passed. This is the
    posture-side defense in depth — `rules/zero-tolerance.md` Rule 2 (no
    fake-classification gates, every accepted dispatch value has a real
    branch) AND Rule 3 (no silent fallbacks).

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
    ) -> None:
        if ledger is None:
            raise ValueError("ledger is required (no None default)")
        if revoke_hook is None:
            raise ValueError("revoke_hook is required (no None default)")
        self._ledger = ledger
        self._revoke_hook = revoke_hook

    async def request_transition(
        self,
        *,
        current: PostureLevel,
        target: PostureLevel,
        evidence: PostureEvidence,
        trigger: str = "user_request",
        revoke_on_demotion: tuple[str, ...] = (),
    ) -> PostureChangeResult:
        """Request a posture transition; raises on any failed gate.

        Args:
            current: present posture level (typically read from envelope or
                Trust Store at request time).
            target: requested posture level.
            evidence: `PostureEvidence` carrying authorship counts, mode,
                grant + cooling-off flags.
            trigger: one of `_VALID_TRIGGERS`. Per `specs/ledger.md`
                § posture_change schema.
            revoke_on_demotion: tuple of `agent_id` strings the cascade-revoke
                hook will revoke on demotion. Empty tuple is permitted (caller
                may decide no delegations need explicit revocation, e.g.
                annual decay where no standing delegations exist).

        Returns:
            `PostureChangeResult(new_level, ledger_entry_id)` on success.

        Raises:
            `AuthorshipScoreDivergenceError` (Step 1).
            `PostureNoopError` (Step 2).
            `PostureEnterpriseAutonomousForbidden` (Step 3a).
            `PostureCoolingOffActiveError` (Step 3b).
            `PostureGenesisGrantMissingError` (Step 3c).
            `PostureAuthorshipInsufficientError` (Step 3d).
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

        # ----- STEP 1: divergence check (T-023 defense) -----
        # Per `specs/authorship-score.md` § Stored vs recomputed: stored at
        # envelope-sign time MUST match runtime recompute; mismatch is an
        # audit alert, never auto-recovered.
        if evidence.authorship_score_stored != evidence.authorship_score_recomputed:
            # Local import to avoid circular dependency at module import.
            from envoy.authorship.score import AuthorshipScoreDivergenceError

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
                if not isinstance(agent_id, str) or not agent_id:
                    raise ValueError(
                        f"revoke_on_demotion entries must be non-empty str, " f"got {agent_id!r}"
                    )
                await self._revoke_hook(
                    agent_id=agent_id,
                    reason=f"posture_demotion:{current.name}->{target.name}",
                    revoked_by="posture_gate",
                )

        # ----- STEP 5: signed posture_change Ledger entry -----
        # Wire shape per `specs/ledger.md` § posture_change schema (lines 243-253):
        # `{type, schema_version, from_posture, to_posture, dimension_scope,
        # trigger, evidence_ref, signed_by}`. The `signed_by` field is
        # APPLICATION-level identifying the authorizing key class (`"genesis_key"`);
        # the Ledger envelope itself adds the runtime device signature
        # at `EnvoyLedger.append` via `EntryEnvelope`.
        content: dict = {
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

        return PostureChangeResult(
            new_level=target,
            ledger_entry_id=entry_id,
        )
