"""envoy.grant_moment.runtime — the EnvoyGrantMomentRuntime facade.

``EnvoyGrantMomentRuntime`` composes the Wave-3 structural primitives across
the M0→M4 lifecycle frozen in ``specs/grant-moment.md`` § State machine:

    M0 construct → M1 render (all active channels) → M2 await decision
    (5min default timeout; per-envelope override) → M3 sign or decline
    → M4 complete.

The facade is the **runtime** layer; the structural primitives
(``state_machine``, ``signed_consent``, ``resolution``, ``channel_handoff``,
``cascade_orchestrator``, ``plan_suspension_bridge``, ``novelty``,
``out_of_envelope``) ship in Wave 3 and are composed here without
reimplementation. Per ``rules/facade-manager-detection.md`` Rule 3 (and the
``BoundaryConversationRuntime`` analog at ``envoy/boundary_conversation/runtime.py``):
every dependency is injected explicitly. The runtime owns no global state and
no hidden singletons.

## Layer responsibilities (per ``specs/grant-moment.md`` § Test location
   "Runtime layer (deferred to Wave-4 facade)")

The facade owns the following surfaces — the structural primitives delegate
their per-state work and the runtime sequences them:

1. **M0 construct** — assembles a signed ``GrantMomentRequest``; records
   ``(nonce, intent_id)`` for T-008 replay defense (``GrantMomentReplayError``);
   emits a ``PhaseARecord`` ledger entry capturing intent (the "Phase A"
   half of ``specs/ledger.md`` § two-phase signing); enforces the queue
   ceiling (``BackPressureQueueFullError``); checks velocity-raise cooling-off
   (``VelocityRaiseCoolingOffError`` per T-093 R2-H4).

2. **M1 render** — drives ``ChannelHandoff.dispatch`` with the high-stakes
   flag derived from the novelty classification + the ``primary_only``
   request bit. The dispatch surface itself enforces primary-binding via
   ``HandoffPlan.refused_channels`` per spec § Rendering.

3. **M2 await decision** — exposes a poll-and-timeout loop the caller drives
   via ``await_decision`` (caller-driven so tests can simulate timeouts
   without sleeping 5 minutes). The default 5-minute window matches
   ``specs/grant-moment.md`` § Timeout; per-request override is honored.
   Timeout raises ``GrantMomentExpiredError``; a parallel honeypot-path test
   verifies the no-distinguisher invariant (``specs/grant-moment.md``
   § Timeout "Identical behavior between real + honeypot paths").

4. **M3 sign-or-decline** — accepts a ``ResolutionShape``; enforces the four
   raise-path defenses:

   - ``NotPrimaryChannelError`` (H-03) — high-stakes resolution decided on a
     non-primary channel.
   - ``NoveltyFrictionRequiredError`` (T-019) — novel-pattern grant with
     bypass attempt (missing read-delay window or required ack tokens).
   - ``CrossChannelConfirmFailedError`` — high-stakes confirm leg missing.
   - ``DualSignatureRequiredError`` (Phase 03 contract pin) — cross-principal
     resolution arrives without the co-signer's signature.

   On Approve / Approve+author / Modify: builds a signed ``GrantMomentResult``
   via ``SignedConsentBuilder.build_signed_result`` and emits the matching
   ``DelegationRecord`` ledger entry with ``phase_a_ref`` linking back to
   the Phase A intent (specs/ledger.md § two-phase signing). On Decline:
   emits a signed ``deny`` ledger entry; the Result wire form carries the
   ``DENY_SIGNED_BY_LEDGER_ONLY`` sentinel per ``signed_consent`` spec.

5. **M4 complete** — drops the in-flight tracking; the request is now
   replay-protected via the persisted ``nonce`` + ``intent_id`` only.

## Cascade revocation surface

``revoke_prior_grant`` exposes ``CascadeRevocationOrchestrator.revoke_and_verify``
for EC-8 ("cascade revocation of Day-1 grant correctly revokes Day-6 child
grant initiated from a different channel"). Cascade is NOT auto-triggered
on Decline — the Decline path produces a signed Ledger entry; cascade is a
deliberate retroactive revocation initiated by the user via a separate
Grant Moment OR by the Weekly Posture Review.

## Friction enforcer (T-019)

The runtime tracks a per-request monotonic-clock start time AND a set of
acknowledged friction tokens. ``acknowledge_friction(request_id, token)``
is the caller-driven primitive that records each completion step. A
``submit_resolution`` on a ``NoveltyClass.NOVEL`` request that has either
(a) elapsed less than ``novelty_read_delay_seconds`` since M1 dispatch, OR
(b) missing required friction tokens, raises ``NoveltyFrictionRequiredError``
naming the bypass.

## Per-channel timeout vs M2 timeout

``GrantMomentTimeoutError`` is raised at M1 when every adapter's
``render_grant_moment`` raised — the dispatch surface caught each
exception and the ``HandoffPlan.channels_dispatched`` is empty. The
error names the primary channel as the failing channel since it is
the high-stakes contract anchor. ``GrantMomentExpiredError`` is the
M2 user-non-response timeout. Both are wire-shape-distinct.

This module is pure Python; depends on the eight structural primitives in
``envoy.grant_moment`` and on the ledger facade shape via ``Any``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from envoy.grant_moment.cascade_orchestrator import (
    CascadeRevocationOrchestrator,
    CascadeResult,
)
from envoy.grant_moment.channel_handoff import ChannelHandoff, HandoffPlan
from envoy.grant_moment.errors import (
    BackPressureQueueFullError,
    CrossChannelConfirmFailedError,
    DualSignatureRequiredError,
    GrantMomentExpiredError,
    GrantMomentReplayError,
    GrantMomentTimeoutError,
    InvalidGrantMomentTransitionError,
    NotPrimaryChannelError,
    NoveltyFrictionRequiredError,
    VelocityRaiseCoolingOffError,
)
from envoy.grant_moment.novelty import (
    NoveltyClass,
    NoveltyClassifier,
    NoveltySignals,
)
from envoy.grant_moment.plan_suspension_bridge import (
    PlanSuspensionBridge,
    PlanSuspensionEvent,
    PlanSuspensionEventKind,
)
from envoy.grant_moment.resolution import (
    ApproveResolution,
    ApproveWithModificationResolution,
    DeclineResolution,
    ResolutionShape,
)
from envoy.grant_moment.signed_consent import (
    ConsequencePreview,
    GrantMomentRequest,
    GrantMomentResult,
    SignedConsentBuilder,
)
from envoy.grant_moment.state_machine import (
    GrantMomentEvent,
    GrantMomentState,
    next_state,
)

__all__ = [
    "EnvoyGrantMomentRuntime",
    "GrantMomentOutcome",
    "FRICTION_TOKEN_READ_DELAY_COMPLETE",
    "FRICTION_TOKEN_DOUBLE_TAP",
    "FRICTION_TOKEN_CROSS_CHANNEL_CONFIRM",
]

logger = logging.getLogger(__name__)

# Ledger entry types per ``specs/ledger.md`` § Entry types. The runtime
# emits the two-phase pair ``PhaseARecord`` (M0 intent) + ``grant_moment``
# (M3 outcome — per ledger.md § grant_moment); the Decline path emits a
# ``grant_moment`` row with ``decision = "deny"`` since spec § ``GrantMomentResult``
# mandates a signed Ledger entry for Deny (not a delegation_key-signed Result).
# The ``DelegationRecord`` type tag is reserved for capability-delegation chains
# per specs/trust-lineage.md § DelegationRecord, NOT per-action grant rows.
_ENTRY_PHASE_A = "PhaseARecord"
_ENTRY_GRANT_MOMENT = "grant_moment"
_ENTRY_GRANT_MOMENT_DISPATCH_FAILED = "grant_moment_dispatch_failed"

# Friction token vocabulary per spec § "Novelty-aware friction (T-019)" —
# the caller-driven runtime exposes these as named tokens so tests + UX can
# audit which friction was acknowledged.
FRICTION_TOKEN_READ_DELAY_COMPLETE = "read_delay_complete"
FRICTION_TOKEN_DOUBLE_TAP = "double_tap"
FRICTION_TOKEN_CROSS_CHANNEL_CONFIRM = "cross_channel_confirm"

# Closed vocabulary of friction tokens the runtime accepts via
# ``acknowledge_friction``. Per security-reviewer Round-1 MED-1:
# typos like "read_delay_complte" must be rejected loudly so the
# enforcer can rely on the token set as a closed signal.
_VALID_FRICTION_TOKENS: frozenset[str] = frozenset(
    {
        FRICTION_TOKEN_READ_DELAY_COMPLETE,
        FRICTION_TOKEN_DOUBLE_TAP,
        FRICTION_TOKEN_CROSS_CHANNEL_CONFIRM,
    }
)

# Default ceilings + windows per spec. Open question #1 (5min calibration)
# and open question #3 (queue ceiling) are recorded in spec § Open questions;
# Phase 01 ships the spec defaults.
_DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes per spec § Timeout
_DEFAULT_NOVELTY_READ_DELAY_SECONDS = 5.0  # spec § Novelty-aware friction
_DEFAULT_QUEUE_CEILING = 5  # spec § Timeout "back-pressure after N parallel"
_DEFAULT_VELOCITY_COOLING_OFF_SECONDS = 24 * 60 * 60  # spec § Velocity-raise ratchet T-093

# Phase A intent TTL — bounds how long a Phase A row stays valid for
# matching with its Phase B (grant_moment) outcome. Per
# ``specs/ledger.md`` § Two-phase signing: orphan Phase A rows beyond
# the TTL surface in the Grant Moment orphan-resolution flow.
_DEFAULT_PHASE_A_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days per ledger spec § orphan resolution

# Bounded dedup-store ceiling per ``rules/trust-plane-security.md`` Rule 4
# (Bounded collections; default maxlen=10000) — the runtime is a
# long-lived process; the unbounded nonce/intent_id dedup stores would
# accumulate indefinitely. T-008 replay defense is preserved because
# each successful issue rolls the eviction window forward in FIFO order.
_DEFAULT_DEDUP_CEILING = 100_000  # 100k pairs per principal; honest about Phase 01 memory budget


class _LedgerProtocol(Protocol):
    """Subset of ``envoy.ledger.facade.EnvoyLedger`` we depend on.

    Phase 01 narrow scope: the runtime emits Phase A + DelegationRecord
    entries through ``append``. The protocol shape lets Tier-1 tests use
    an in-memory stub satisfying the same surface; Tier-2 wiring uses the
    real ``EnvoyLedger`` against an ``InMemoryAuditStore``.
    """

    async def append(
        self,
        *,
        entry_type: str,
        content: dict[str, Any],
        intent_id: str | None = ...,
        content_trust_level: str = ...,
    ) -> str: ...


class _VisibleSecretShape(Protocol):
    """Structural shape the runtime reads off a VisibleSecret.

    Only ``phrase`` is consumed — the runtime hashes it for T-018 plumbing
    and never reads icon/color (those are channel-adapter concerns).
    """

    phrase: str


class _VisibleSecretProviderProtocol(Protocol):
    """Subset of ``envoy.trust.store.TrustStore`` we depend on.

    The runtime asks the trust store for the principal's current
    ``VisibleSecret`` so it can populate the per-render hashes the channel
    adapters compare against the user's stored phrase (T-018 defense
    raise site lives in the adapter, not here — but the hash plumbing
    needs the trust store).
    """

    async def get_visible_secret(self, principal_id: str) -> _VisibleSecretShape | None: ...


@dataclass(frozen=True, slots=True)
class GrantMomentOutcome:
    """The terminal state of one M0→M4 lifecycle.

    Mirrors the ``ConversationOutcome`` shape in
    ``envoy.boundary_conversation.runtime`` — frozen so callers cannot
    mutate the recorded result after the runtime returns it.

    ``state`` is one of "APPROVED", "DECLINED", "MODIFIED", "EXPIRED",
    "ERROR" — the four spec ``decision`` values map to APPROVED (both
    approve_once and approve_and_author) / DECLINED / MODIFIED, plus the
    two non-decision terminal states (timeout, raise-path).
    """

    state: str  # "APPROVED" | "DECLINED" | "MODIFIED" | "EXPIRED" | "ERROR"
    request_id: str
    result: GrantMomentResult | None = None
    delegation_record_ref: str | None = None
    phase_a_record_ref: str | None = None
    error: Exception | None = None
    handoff_plan: HandoffPlan | None = None


@dataclass
class _PendingGrant:
    """In-flight tracking row per request_id (M0 → M4).

    Held in ``EnvoyGrantMomentRuntime._inflight`` for the duration of the
    M0→M4 lifecycle; dropped on M4 complete OR on terminal error.
    """

    request: GrantMomentRequest
    novelty_class: NoveltyClass
    high_stakes: bool
    is_velocity_raise: bool
    is_cross_principal: bool
    phase_a_record_ref: str
    dispatched_at_monotonic: float
    state: GrantMomentState = GrantMomentState.M0_CONSTRUCT
    handoff_plan: HandoffPlan | None = None
    friction_acks: set[str] = field(default_factory=set)
    cross_channel_confirmed: bool = False
    confirm_channel_id: str | None = None
    decision_future: asyncio.Future[ResolutionShape] | None = None
    decided_on_channel_id: str | None = None


class EnvoyGrantMomentRuntime:
    """The M0→M4 facade composing the eight grant_moment structural primitives.

    Constructor injects every dependency explicitly; the runtime owns NO
    globals + NO hidden singletons. ``await issue_grant_moment(...)``
    drives M0+M1; ``await await_decision(...)`` drives M2; the channel
    adapter calls ``await submit_resolution(...)`` when the user signs;
    M4 completes inside ``submit_resolution`` (or ``await_decision`` on
    timeout).

    Per ``rules/agent-reasoning.md``: this runtime performs ZERO content
    classification + ZERO keyword routing. Every decision (novelty class,
    envelope violation, composition rule, primary-channel binding) comes
    from a structural primitive the caller injected; the runtime sequences
    them.
    """

    def __init__(
        self,
        *,
        key_manager: Any,
        delegation_key_id: str,
        principal_id: str,
        device_id: str,
        ledger: _LedgerProtocol,
        channel_handoff: ChannelHandoff,
        trust_store: _VisibleSecretProviderProtocol | None = None,
        cascade_orchestrator: CascadeRevocationOrchestrator | None = None,
        plan_suspension_bridge: PlanSuspensionBridge | None = None,
        novelty_classifier: NoveltyClassifier | None = None,
        default_timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        novelty_read_delay_seconds: float = _DEFAULT_NOVELTY_READ_DELAY_SECONDS,
        queue_ceiling: int = _DEFAULT_QUEUE_CEILING,
        velocity_raise_cooling_off_seconds: int = _DEFAULT_VELOCITY_COOLING_OFF_SECONDS,
        phase_a_ttl_seconds: int = _DEFAULT_PHASE_A_TTL_SECONDS,
        dedup_store_ceiling: int = _DEFAULT_DEDUP_CEILING,
    ) -> None:
        if not delegation_key_id:
            raise ValueError("delegation_key_id is required")
        if not principal_id:
            raise ValueError("principal_id is required")
        if not device_id:
            raise ValueError("device_id is required")
        if not key_manager.has_key(delegation_key_id):
            raise ValueError(
                f"delegation_key_id={delegation_key_id!r} not registered with "
                "key_manager — register the keypair before constructing "
                "EnvoyGrantMomentRuntime"
            )
        if default_timeout_seconds <= 0:
            raise ValueError("default_timeout_seconds must be positive")
        if novelty_read_delay_seconds < 0:
            raise ValueError("novelty_read_delay_seconds must be non-negative")
        if queue_ceiling <= 0:
            raise ValueError("queue_ceiling must be positive")
        if dedup_store_ceiling <= 0:
            raise ValueError("dedup_store_ceiling must be positive")
        if phase_a_ttl_seconds <= 0:
            raise ValueError("phase_a_ttl_seconds must be positive")

        self._key_manager = key_manager
        self._delegation_key_id = delegation_key_id
        self._principal_id = principal_id
        self._device_id = device_id
        self._ledger = ledger
        self._channel_handoff = channel_handoff
        self._trust_store = trust_store
        self._cascade_orchestrator = cascade_orchestrator
        self._plan_suspension_bridge = plan_suspension_bridge
        self._novelty_classifier = novelty_classifier or NoveltyClassifier()
        self._signed_consent = SignedConsentBuilder(key_manager=key_manager)
        self._default_timeout_seconds = default_timeout_seconds
        self._novelty_read_delay_seconds = novelty_read_delay_seconds
        self._queue_ceiling = queue_ceiling
        self._velocity_raise_cooling_off_seconds = velocity_raise_cooling_off_seconds
        self._phase_a_ttl_seconds = phase_a_ttl_seconds
        self._dedup_store_ceiling = dedup_store_ceiling

        # The H-03 enforcer needs the primary channel id; ChannelHandoff
        # exposes a public ``primary_channel_id`` property (reviewer-R1
        # MED-2: do not reach into the private attribute).
        self._primary_channel_id: str = channel_handoff.primary_channel_id

        # T-008 replay defense: nonce + intent_id dedup stores. Phase 01
        # narrow scope — per-runtime-instance lifetime, not persisted across
        # restarts. Phase 02 lifts this into a TrustVault sub-store.
        # Bounded per ``rules/trust-plane-security.md`` Rule 4 — FIFO
        # eviction via OrderedDict.popitem(last=False) when the ceiling
        # is exceeded keeps memory bounded; the most-recent ``ceiling``
        # nonces are always replay-defended.
        self._seen_nonces: OrderedDict[str, str] = OrderedDict()  # nonce → first request_id
        self._seen_intent_ids: OrderedDict[str, str] = OrderedDict()  # intent_id → first request_id

        # In-flight grants (M0 → M4 lifetime). Empty after M4 complete.
        self._inflight: dict[str, _PendingGrant] = {}

        # Velocity-raise registry: last-approved wall-clock timestamp per
        # principal. T-093 R2-H4 cooling-off ratchet. Wall-clock (time.time())
        # rather than monotonic — the 24h window is a user-facing claim
        # bound to calendar time; monotonic resets to 0 on process
        # restart, which would silently advance the ratchet (security-R1
        # HIGH-3). Phase 02 persists this into the TrustVault so the
        # invariant survives restart.
        self._velocity_raise_last_approved_wallclock: dict[str, float] = {}

    # ------------------------------------------------------------------
    # M0 + M1 — construct + dispatch
    # ------------------------------------------------------------------

    async def issue_grant_moment(
        self,
        *,
        intent_id: str,
        nonce: str,
        tool_name: str,
        tool_args_canonical: dict[str, Any],
        tool_args_canonical_hash: str,
        envelope_id: str,
        envelope_version: int,
        envelope_hash: str,
        why_asking: str,
        consequence_preview: ConsequencePreview,
        novelty_signals: NoveltySignals,
        session_id: str | None = None,
        primary_only: bool = False,
        timeout_seconds: int | None = None,
        is_velocity_raise: bool = False,
        is_cross_principal: bool = False,
    ) -> GrantMomentRequest:
        """M0 construct → M1 render. Returns the signed dispatched request.

        Raises ``GrantMomentReplayError`` (T-008) on a repeat ``nonce`` OR
        ``intent_id``. Raises ``BackPressureQueueFullError`` when the
        in-flight queue is at ceiling. Raises ``VelocityRaiseCoolingOffError``
        (T-093) on a velocity-raise within the 24h cooling-off window.

        The runtime tracks the request in ``_inflight``; the caller drives
        M2 via ``await_decision`` and M3 via ``submit_resolution``.
        """
        # Phase-01 cross-principal disposition (security-R1 MED-4): the
        # full dual-sign + 24h cool-off flow is Phase 03 scope. Phase 01
        # ships the wire-shape contract only and MUST refuse cross-principal
        # issues at the runtime boundary so a single principal cannot
        # produce a "cross-principal grant" by populating
        # ``co_signer_principal_genesis_id`` without an actual co-signature
        # (which Phase 01 has no path to verify). Phase 03 lifts this.
        if is_cross_principal:
            raise DualSignatureRequiredError(
                request_id="<not-yet-issued>",
                awaiting_co_signer="<phase-03-cross-principal-not-implemented>",
            )

        # T-008 nonce / intent_id defense — both fire ``GrantMomentReplayError``.
        if nonce in self._seen_nonces:
            raise GrantMomentReplayError(
                duplicate_value=nonce,
                duplicate_kind="nonce",
                prior_request_id=self._seen_nonces[nonce],
            )
        if intent_id in self._seen_intent_ids:
            raise GrantMomentReplayError(
                duplicate_value=intent_id,
                duplicate_kind="intent_id",
                prior_request_id=self._seen_intent_ids[intent_id],
            )

        # Back-pressure ceiling per spec § Timeout.
        if len(self._inflight) >= self._queue_ceiling:
            raise BackPressureQueueFullError(
                queue_ceiling=self._queue_ceiling,
                queue_depth=len(self._inflight),
            )

        # T-093 velocity-raise cooling-off ratchet — fired BEFORE we mint a
        # nonce reservation so a refused velocity raise does not leak the
        # nonce into the dedup store (the user re-issues with a fresh nonce
        # after the cooling-off window). Wall-clock (time.time()) so the
        # 24h window aligns with the user-facing claim — security-R1 HIGH-3.
        if is_velocity_raise:
            last = self._velocity_raise_last_approved_wallclock.get(self._principal_id)
            if last is not None:
                elapsed = int(time.time() - last)
                if elapsed < self._velocity_raise_cooling_off_seconds:
                    raise VelocityRaiseCoolingOffError(
                        elapsed_seconds=elapsed,
                        required_seconds=self._velocity_raise_cooling_off_seconds,
                    )

        # Reserve the nonce + intent_id BEFORE signing so a concurrent
        # second-arrival sees the dedup hit even if signing is slow.
        # FIFO eviction at the ceiling keeps memory bounded (security-R1
        # HIGH-1; rules/trust-plane-security.md Rule 4).
        provisional_request_id = f"gm-{uuid.uuid4()}"
        self._remember_nonce(nonce, provisional_request_id)
        self._remember_intent_id(intent_id, provisional_request_id)

        # Classify novelty. The classifier is pure-functional per
        # ``envoy.grant_moment.novelty`` — same input → same output.
        novelty_class = self._novelty_classifier.classify(novelty_signals)
        high_stakes = novelty_class == NoveltyClass.HIGH_STAKES

        effective_timeout = (
            timeout_seconds if timeout_seconds is not None else self._default_timeout_seconds
        )

        # Build the unsigned wire-form Request. The SignedConsentBuilder
        # canonicalizes + signs.
        unsigned_request = GrantMomentRequest(
            request_id=provisional_request_id,
            session_id=session_id or provisional_request_id,
            principal_genesis_id=self._principal_id,
            envelope_id=envelope_id,
            envelope_version=envelope_version,
            envelope_hash=envelope_hash,
            intent_id=intent_id,
            nonce=nonce,
            tool_name=tool_name,
            tool_args_canonical=tool_args_canonical,
            tool_args_canonical_hash=tool_args_canonical_hash,
            why_asking=why_asking,
            consequence_preview=consequence_preview,
            novelty_class=novelty_class.value,
            primary_only=primary_only,
            timeout_seconds=effective_timeout,
            issued_at=_now_iso(),
            delegation_key_pubkey_hex=self._resolve_delegation_pubkey_hex(),
        )
        signed_request = self._signed_consent.build_signed_request(
            request=unsigned_request, delegation_key_id=self._delegation_key_id
        )

        # Phase A intent — first half of two-phase signing per
        # ``specs/ledger.md`` § two-phase signing + § PhaseARecord. Emitted
        # BEFORE M1 dispatch so a render failure still leaves the intent
        # recorded. Payload shape matches the canonical PhaseARecord
        # schema (envelope_check_passed + phase_a_at + ttl_expires_at +
        # signed_by) per analyst-R1 MED-2.
        phase_a_issued_at = _now_iso()
        phase_a_ttl = (
            datetime.now(timezone.utc) + timedelta(seconds=self._phase_a_ttl_seconds)
        ).isoformat(timespec="microseconds")
        phase_a_ref = await self._ledger.append(
            entry_type=_ENTRY_PHASE_A,
            content={
                "schema_version": "1.0",
                "intent_id": signed_request.intent_id,
                "tool_name": signed_request.tool_name,
                "tool_args_canonical_hash": signed_request.tool_args_canonical_hash,
                "envelope_version": signed_request.envelope_version,
                "envelope_check_passed": True,
                "phase_a_at": phase_a_issued_at,
                "ttl_expires_at": phase_a_ttl,
                "signed_by": "delegation_key",
                # Phase-01 additive context (not in spec schema but useful
                # for the audit chain; the canonical 9 fields above stay
                # in the front of the dict for grep-able schema matching).
                "request_id": signed_request.request_id,
                "session_id": signed_request.session_id,
                "principal_genesis_id": signed_request.principal_genesis_id,
                "nonce": signed_request.nonce,
                "envelope_id": signed_request.envelope_id,
                "envelope_hash": signed_request.envelope_hash,
                "why_asking": signed_request.why_asking,
                "novelty_class": signed_request.novelty_class,
                "primary_only": signed_request.primary_only,
                "timeout_seconds": signed_request.timeout_seconds,
                "issued_at": signed_request.issued_at,
                "delegation_key_pubkey_hex": signed_request.delegation_key_pubkey_hex,
                "signature_by_delegator_hex": signed_request.signature_by_delegator_hex,
            },
            intent_id=signed_request.intent_id,
            content_trust_level="user-authored",
        )

        # Register the in-flight grant. Decision future is created lazily by
        # ``await_decision`` so callers that drive submit_resolution directly
        # (synchronous tests) do not pay the future-creation cost.
        pending = _PendingGrant(
            request=signed_request,
            novelty_class=novelty_class,
            high_stakes=high_stakes,
            is_velocity_raise=is_velocity_raise,
            is_cross_principal=is_cross_principal,
            phase_a_record_ref=phase_a_ref,
            dispatched_at_monotonic=time.monotonic(),
        )
        self._inflight[signed_request.request_id] = pending

        # M0 → M1 transition via the state machine. The transition is
        # strictly enforced; any subsequent state mutation reuses ``next_state``.
        pending.state = next_state(pending.state, GrantMomentEvent.DISPATCH_TO_CHANNELS)

        # M1 dispatch through ChannelHandoff. The dispatch surface enforces
        # primary-binding for high_stakes / primary_only routes; refusal
        # records land in the returned HandoffPlan.
        handoff_plan = await self._channel_handoff.dispatch(
            request=signed_request, high_stakes=high_stakes
        )
        pending.handoff_plan = handoff_plan

        # If no channel actually rendered (every adapter raised), surface the
        # channel-render hang as a typed error so the caller can switch
        # channels. Per spec error taxonomy ``GrantMomentTimeoutError``
        # carries channel_id; we name the primary as the failing channel
        # since it is the high-stakes contract anchor. The (nonce,
        # intent_id) reservations are released so the user can retry with
        # the same identifiers — the grant never actually rendered, so it
        # cannot be a "replay" of an executed action (reviewer-R1 MED-4).
        # An audit row records the dispatch failure so the orphan-Phase-A
        # surface stays clean (security-R1 MED-3).
        if not handoff_plan.channels_dispatched:
            del self._inflight[signed_request.request_id]
            self._seen_nonces.pop(signed_request.nonce, None)
            self._seen_intent_ids.pop(signed_request.intent_id, None)
            await self._ledger.append(
                entry_type=_ENTRY_GRANT_MOMENT_DISPATCH_FAILED,
                content={
                    "schema_version": "1.0",
                    "request_id": signed_request.request_id,
                    "intent_id": signed_request.intent_id,
                    "phase_a_ref": phase_a_ref,
                    "refused_channels": [
                        {"channel_id": c, "reason": r} for c, r in handoff_plan.refused_channels
                    ],
                    "failed_at": _now_iso(),
                    "signed_by": "device_key",
                },
                intent_id=signed_request.intent_id,
                content_trust_level="system",
            )
            raise GrantMomentTimeoutError(
                request_id=signed_request.request_id, channel_id=self._primary_channel_id
            )

        pending.state = next_state(pending.state, GrantMomentEvent.RENDERED_AND_AWAITING)
        logger.info(
            "grant_moment.issued",
            extra={
                "request_id": signed_request.request_id,
                "novelty_class": novelty_class.value,
                "high_stakes": high_stakes,
                "channels_dispatched": list(handoff_plan.channels_dispatched),
                "channels_refused": [c for c, _ in handoff_plan.refused_channels],
            },
        )
        return signed_request

    # ------------------------------------------------------------------
    # M2 — await decision with timeout
    # ------------------------------------------------------------------

    async def await_decision(
        self,
        request_id: str,
        *,
        timeout_seconds: int | None = None,
    ) -> ResolutionShape:
        """M2 await: block until the channel adapter posts a decision OR the
        timeout elapses. Returns the user's ``ResolutionShape``; raises
        ``GrantMomentExpiredError`` on timeout (the M2 → M3 transition is
        recorded so the timeout's audit row matches a successful path's).
        """
        pending = self._require_inflight(request_id)
        if pending.state != GrantMomentState.M2_AWAIT:
            # State-machine misuse — typed as InvalidGrantMomentTransitionError
            # so callers can catch the right class. Earlier draft used
            # NoveltyFrictionRequiredError (reviewer-R1 HIGH-1); friction
            # was the wrong error class for a state-machine misuse.
            raise InvalidGrantMomentTransitionError(
                current_state=pending.state.value,
                attempted_event="await_decision",
            )
        if pending.decision_future is None:
            pending.decision_future = asyncio.get_running_loop().create_future()

        effective_timeout = (
            timeout_seconds if timeout_seconds is not None else pending.request.timeout_seconds
        )
        try:
            resolution = await asyncio.wait_for(pending.decision_future, timeout=effective_timeout)
        except asyncio.TimeoutError:
            # M2 → M3 (with timeout disposition) — the state machine routes
            # ``TIMEOUT_EXPIRED`` to M3 sign per the transition table.
            pending.state = next_state(pending.state, GrantMomentEvent.TIMEOUT_EXPIRED)
            self._inflight.pop(request_id, None)
            raise GrantMomentExpiredError(
                request_id=request_id, timeout_seconds=effective_timeout
            ) from None
        else:
            pending.state = next_state(pending.state, GrantMomentEvent.DECISION_RECEIVED)
            return resolution

    def post_decision(self, request_id: str, resolution: ResolutionShape) -> None:
        """Adapter-side push: deliver the user's decision to ``await_decision``.

        Adapters call this when the user signs in their channel UI. The
        ``await_decision`` coroutine resumes with the supplied resolution.
        Calling ``post_decision`` for an unknown request_id raises
        ``GrantMomentReplayError`` only if the request was previously
        completed; a never-seen request_id raises ``KeyError`` (programming
        error, not a security event).
        """
        pending = self._require_inflight(request_id)
        if pending.decision_future is None:
            pending.decision_future = asyncio.get_running_loop().create_future()
        if not pending.decision_future.done():
            pending.decision_future.set_result(resolution)

    # ------------------------------------------------------------------
    # Friction acknowledgement (T-019)
    # ------------------------------------------------------------------

    def acknowledge_friction(self, request_id: str, token: str) -> None:
        """Record one friction completion step. ``token`` MUST be one of the
        runtime's closed vocabulary (``FRICTION_TOKEN_READ_DELAY_COMPLETE``
        / ``_DOUBLE_TAP`` / ``_CROSS_CHANNEL_CONFIRM``). Unknown tokens are
        rejected loudly per security-R1 + reviewer-R1 MED-5 — silent
        accumulation of typo'd tokens would not satisfy the enforcer and
        would surface as a confusing ``NoveltyFrictionRequiredError`` on
        ``submit_resolution``.

        ``submit_resolution`` checks the accumulated set against the
        per-novelty-class requirement.
        """
        if not token:
            raise ValueError("friction token must be non-empty")
        if token not in _VALID_FRICTION_TOKENS:
            raise ValueError(
                f"unknown friction token {token!r}; "
                f"expected one of {sorted(_VALID_FRICTION_TOKENS)}"
            )
        pending = self._require_inflight(request_id)
        pending.friction_acks.add(token)

    def confirm_cross_channel(self, request_id: str, *, confirm_channel_id: str) -> None:
        """Mark the cross-channel confirm leg complete for a high-stakes
        grant. ``confirm_channel_id`` MUST be one of the configured adapter
        channels AND MUST differ from the eventual ``decided_on_channel_id``
        (the latter check fires at submit-resolution time since the M3
        channel is not yet known). Caller (the confirm-channel adapter)
        is responsible for verifying the user's identity on the second
        channel before calling.

        Records ``FRICTION_TOKEN_CROSS_CHANNEL_CONFIRM`` so the friction
        enforcer sees the leg without a separate accounting path.
        """
        valid_channels = self._channel_handoff.adapter_channel_ids
        if confirm_channel_id not in valid_channels:
            raise ValueError(
                f"confirm_channel_id {confirm_channel_id!r} is not one of the "
                f"configured channels {sorted(valid_channels)!r}"
            )
        pending = self._require_inflight(request_id)
        pending.cross_channel_confirmed = True
        pending.confirm_channel_id = confirm_channel_id
        pending.friction_acks.add(FRICTION_TOKEN_CROSS_CHANNEL_CONFIRM)
        logger.info(
            "grant_moment.cross_channel_confirmed",
            extra={
                "request_id": request_id,
                "confirm_channel_id": confirm_channel_id,
            },
        )

    # ------------------------------------------------------------------
    # M3 + M4 — sign or decline + complete
    # ------------------------------------------------------------------

    async def submit_resolution(
        self,
        *,
        request_id: str,
        resolution: ResolutionShape,
        decided_on_channel_id: str,
        friction_acks: set[str] | None = None,
    ) -> GrantMomentOutcome:
        """M3 sign-or-decline → M4 complete. Returns the terminal outcome.

        Validates the four raise-path defenses (H-03 primary-channel,
        T-019 novelty friction, cross-channel confirm, cross-principal
        dual-signature) BEFORE building the signed Result. On Approve /
        Modify: builds the signed ``GrantMomentResult`` + emits the matching
        ``DelegationRecord`` ledger entry. On Decline: emits a signed
        ``DelegationRecord`` with ``decision="deny"`` (the wire-form Result
        carries the DENY sentinel per ``signed_consent``).
        """
        pending = self._require_inflight(request_id)
        if friction_acks:
            pending.friction_acks.update(friction_acks)
        pending.decided_on_channel_id = decided_on_channel_id

        # Move state to M3 if we are still in M2_await (caller may have
        # used the adapter-push path which completes the future without
        # transitioning). State-machine misuse outside {M2_await, M3_sign}
        # returns a typed-error outcome rather than relying on next_state
        # to raise (security-R1 HIGH-2: previous code let
        # InvalidGrantMomentTransitionError escape unhandled).
        if pending.state == GrantMomentState.M2_AWAIT:
            pending.state = next_state(pending.state, GrantMomentEvent.DECISION_RECEIVED)
        elif pending.state != GrantMomentState.M3_SIGN:
            outcome = GrantMomentOutcome(
                state="ERROR",
                request_id=request_id,
                error=InvalidGrantMomentTransitionError(
                    current_state=pending.state.value,
                    attempted_event="submit_resolution",
                ),
            )
            self._inflight.pop(request_id, None)
            self._log_refusal(
                pending,
                rejection_class="invalid_state_transition",
                decided_on_channel_id=decided_on_channel_id,
            )
            return outcome

        # H-03 — high-stakes resolution decided on a non-primary channel.
        if pending.high_stakes and decided_on_channel_id != self._primary_channel_id:
            err = NotPrimaryChannelError(
                channel_id=decided_on_channel_id,
                primary_channel_id=self._primary_channel_id,
            )
            self._inflight.pop(request_id, None)
            self._log_refusal(
                pending,
                rejection_class="h03_non_primary_channel",
                decided_on_channel_id=decided_on_channel_id,
            )
            return GrantMomentOutcome(state="ERROR", request_id=request_id, error=err)

        # T-019 novelty friction enforcer (only for ApproveResolution /
        # ApproveWithModificationResolution paths on NOVEL / HIGH_STAKES
        # novelty classes — Decline never requires friction, since the user
        # is refusing the action). The 5s read-delay is wall-clock-based
        # against ``dispatched_at_monotonic``; the read-delay ack token is
        # the caller's confirmation the UX actually rendered + waited.
        if not isinstance(resolution, DeclineResolution) and pending.novelty_class in (
            NoveltyClass.NOVEL,
            NoveltyClass.HIGH_STAKES,
        ):
            err_or_none = self._check_novelty_friction(pending)
            if err_or_none is not None:
                self._inflight.pop(request_id, None)
                self._log_refusal(
                    pending,
                    rejection_class="t019_friction_required",
                    decided_on_channel_id=decided_on_channel_id,
                )
                return GrantMomentOutcome(state="ERROR", request_id=request_id, error=err_or_none)

        # High-stakes cross-channel confirm leg — required for HIGH_STAKES
        # resolution paths per spec § Novelty-aware friction. The
        # confirm channel id MUST differ from the decided-on channel
        # (single-channel-confirm defeats the defense — security-R1 MED-2).
        if (
            pending.high_stakes
            and not isinstance(resolution, DeclineResolution)
            and not pending.cross_channel_confirmed
        ):
            err = CrossChannelConfirmFailedError(
                request_id=request_id,
                confirm_channel_id=self._primary_channel_id,
            )
            self._inflight.pop(request_id, None)
            self._log_refusal(
                pending,
                rejection_class="cross_channel_confirm_missing",
                decided_on_channel_id=decided_on_channel_id,
            )
            return GrantMomentOutcome(state="ERROR", request_id=request_id, error=err)
        if (
            pending.high_stakes
            and not isinstance(resolution, DeclineResolution)
            and pending.confirm_channel_id is not None
            and pending.confirm_channel_id == decided_on_channel_id
        ):
            err = CrossChannelConfirmFailedError(
                request_id=request_id,
                confirm_channel_id=pending.confirm_channel_id,
            )
            self._inflight.pop(request_id, None)
            self._log_refusal(
                pending,
                rejection_class="cross_channel_same_as_decided",
                decided_on_channel_id=decided_on_channel_id,
            )
            return GrantMomentOutcome(state="ERROR", request_id=request_id, error=err)

        # Build the signed Result. Decline produces an unsigned-by-delegation
        # Result with the DENY sentinel; Approve / Approve+author / Modify
        # produce delegation_key-signed Results.
        delegation_record_ref_provisional = f"dr-pending-{uuid.uuid4()}"
        result = self._signed_consent.build_signed_result(
            request_id=request_id,
            result_id=f"gmr-{uuid.uuid4()}",
            decided_at=_now_iso(),
            decided_on_channel_id=decided_on_channel_id,
            delegation_record_ref=delegation_record_ref_provisional,
            phase_a_record_ref=pending.phase_a_record_ref,
            resolution=resolution,
            delegation_key_id=(
                None if isinstance(resolution, DeclineResolution) else self._delegation_key_id
            ),
        )

        # Emit the Phase B ledger row tagged ``grant_moment`` per
        # ``specs/ledger.md`` § grant_moment (NOT ``DelegationRecord``,
        # which is the capability-delegation chain row per
        # ``specs/trust-lineage.md`` § DelegationRecord — analyst-R1 HIGH-3).
        # ``phase_a_ref`` links it back to the Phase A intent.
        delegation_record_ref = await self._ledger.append(
            entry_type=_ENTRY_GRANT_MOMENT,
            content={
                "schema_version": "1.0",
                "request_ref": pending.request.request_id,
                "result_ref": result.result_id,
                "intent_id": pending.request.intent_id,
                "decision": result.decision,
                "decided_at": result.decided_at,
                "envelope_version_at_decision": pending.request.envelope_version,
                "novelty_class": pending.novelty_class.value,
                "signed_by": (
                    "device_key" if isinstance(resolution, DeclineResolution) else "delegation_key"
                ),
                # Phase-01 audit context (canonical 9 fields above stay in
                # the front of the dict for grep-able schema matching).
                "phase_a_ref": pending.phase_a_record_ref,
                "decided_on_channel_id": result.decided_on_channel_id,
                "decided_by_principal_genesis_id": result.decided_by_principal_genesis_id,
                "modify_payload": result.modify_payload,
                "author_payload": result.author_payload,
                "co_signer_principal_genesis_id": result.co_signer_principal_genesis_id,
                "signature_by_delegator_hex": result.signature_by_delegator_hex,
                "co_signature_hex": result.co_signature_hex,
            },
            intent_id=pending.request.intent_id,
            content_trust_level="user-authored",
        )

        # Velocity-raise registry update — only on successful Approve paths.
        # Wall-clock (time.time()) so the 24h window matches the user-facing
        # claim (security-R1 HIGH-3).
        if pending.is_velocity_raise and isinstance(
            resolution, (ApproveResolution, ApproveWithModificationResolution)
        ):
            self._velocity_raise_last_approved_wallclock[self._principal_id] = time.time()

        # M3 → M4 transition + cleanup. The dedup stores keep the nonce /
        # intent_id (replay safety survives M4 cleanup); only the in-flight
        # row is dropped.
        pending.state = next_state(pending.state, GrantMomentEvent.SIGNATURE_FINALIZED)
        self._inflight.pop(request_id, None)

        terminal_state = self._terminal_state_from_resolution(resolution)
        logger.info(
            "grant_moment.completed",
            extra={
                "request_id": request_id,
                "decision": result.decision,
                "decided_on_channel_id": decided_on_channel_id,
                "terminal_state": terminal_state,
                "delegation_record_ref": delegation_record_ref,
            },
        )
        return GrantMomentOutcome(
            state=terminal_state,
            request_id=request_id,
            result=result,
            delegation_record_ref=delegation_record_ref,
            phase_a_record_ref=pending.phase_a_record_ref,
            handoff_plan=pending.handoff_plan,
        )

    # ------------------------------------------------------------------
    # Cascade revocation (EC-8)
    # ------------------------------------------------------------------

    def revoke_prior_grant(
        self, *, root_id: str, expected_descendants: frozenset[str]
    ) -> CascadeResult:
        """Cascade-revoke a previously approved grant per EC-8.

        Delegates to the injected ``CascadeRevocationOrchestrator``; raises
        if no orchestrator was configured. Raises
        ``CascadeIncompleteError`` from the orchestrator when one or more
        expected descendants are missing from the upstream's revoked-set.
        """
        if self._cascade_orchestrator is None:
            raise ValueError(
                "revoke_prior_grant called but no CascadeRevocationOrchestrator "
                "was injected at runtime construction; supply one via the "
                "cascade_orchestrator= kwarg"
            )
        return self._cascade_orchestrator.revoke_and_verify(
            root_id=root_id, expected_descendants=expected_descendants
        )

    # ------------------------------------------------------------------
    # Suspension bridge fan-out (cross-runtime)
    # ------------------------------------------------------------------

    def emit_queue_hold(self, *, reason: str, session_id: str) -> None:
        """Emit a ``GRANT_MOMENT_QUEUE_HOLD_REQUESTED`` event when the
        runtime needs the queue paused (e.g. while a Boundary Conversation
        re-pair completes after a ``VisibleSecretMismatchError``).
        """
        if self._plan_suspension_bridge is None:
            return
        self._plan_suspension_bridge.emit(
            PlanSuspensionEvent(
                kind=PlanSuspensionEventKind.GRANT_MOMENT_QUEUE_HOLD_REQUESTED,
                ritual_id=session_id,
                emitted_at=_now_iso(),
                reason=reason,
            )
        )

    def emit_queue_resume(self, *, reason: str, session_id: str) -> None:
        """Emit a ``GRANT_MOMENT_QUEUE_RESUME_REQUESTED`` event after the
        upstream pause-cause clears.
        """
        if self._plan_suspension_bridge is None:
            return
        self._plan_suspension_bridge.emit(
            PlanSuspensionEvent(
                kind=PlanSuspensionEventKind.GRANT_MOMENT_QUEUE_RESUME_REQUESTED,
                ritual_id=session_id,
                emitted_at=_now_iso(),
                reason=reason,
            )
        )

    # ------------------------------------------------------------------
    # Visible-secret hash plumbing (T-018 raise-site lives in adapter)
    # ------------------------------------------------------------------

    async def visible_secret_hash_for(self, principal_id: str) -> str | None:
        """Return the SHA-256 hex of the stored visible-secret phrase, or
        None when no secret has been set.

        Channel adapters call this to compare against the rendered phrase
        they would surface; mismatch raises ``VisibleSecretMismatchError``
        at adapter level. The runtime exposes only the HASH (never the
        phrase) per ``rules/security.md`` § "No secrets in logs".
        """
        if self._trust_store is None:
            return None
        secret = await self._trust_store.get_visible_secret(principal_id)
        if secret is None:
            return None
        return hashlib.sha256(secret.phrase.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Inspection helpers (tests + UX)
    # ------------------------------------------------------------------

    def inflight_count(self) -> int:
        """Number of M0 → M4 grants currently in-flight."""
        return len(self._inflight)

    def current_state(self, request_id: str) -> GrantMomentState:
        """The Grant Moment state machine position for ``request_id``."""
        return self._require_inflight(request_id).state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_inflight(self, request_id: str) -> _PendingGrant:
        try:
            return self._inflight[request_id]
        except KeyError:
            raise KeyError(
                f"request_id {request_id!r} is not in-flight; either it never "
                "issued, it already completed, or it timed out."
            ) from None

    def _remember_nonce(self, nonce: str, request_id: str) -> None:
        """Insert into the FIFO-bounded nonce dedup store.

        Evicts the oldest entry when the ceiling is exceeded so memory
        stays bounded (security-R1 HIGH-1; rules/trust-plane-security.md
        Rule 4). The most-recent ``dedup_store_ceiling`` nonces remain
        replay-defended.
        """
        self._seen_nonces[nonce] = request_id
        self._seen_nonces.move_to_end(nonce)
        while len(self._seen_nonces) > self._dedup_store_ceiling:
            self._seen_nonces.popitem(last=False)

    def _remember_intent_id(self, intent_id: str, request_id: str) -> None:
        """Insert into the FIFO-bounded intent_id dedup store.

        Same semantics as ``_remember_nonce`` but on the intent_id axis.
        """
        self._seen_intent_ids[intent_id] = request_id
        self._seen_intent_ids.move_to_end(intent_id)
        while len(self._seen_intent_ids) > self._dedup_store_ceiling:
            self._seen_intent_ids.popitem(last=False)

    def _log_refusal(
        self,
        pending: _PendingGrant,
        *,
        rejection_class: str,
        decided_on_channel_id: str,
    ) -> None:
        """Emit a WARN line for every security-relevant rejection at M3.

        Per ``rules/observability.md`` Mandatory Log Points 1 + 4: auth /
        rejection events MUST emit a structured log line. Reviewer-R1
        HIGH-4 surfaced that the five ERROR-outcome paths were silent
        from the audit-aggregator view. Field names are operational
        identifiers (rejection_class is a closed enum, novelty_class is
        the spec discriminator) — no secrets or PII.
        """
        logger.warning(
            "grant_moment.refused",
            extra={
                "request_id": pending.request.request_id,
                "rejection_class": rejection_class,
                "decided_on_channel_id": decided_on_channel_id,
                "novelty_class": pending.novelty_class.value,
                "high_stakes": pending.high_stakes,
                "is_velocity_raise": pending.is_velocity_raise,
            },
        )

    def _check_novelty_friction(
        self, pending: _PendingGrant
    ) -> NoveltyFrictionRequiredError | None:
        """Validate the friction sequence for novel/high_stakes paths.

        Returns the typed error when friction is incomplete; None when the
        path is clear. The read-delay check uses monotonic clock so the
        elapsed time cannot be manipulated by wall-clock changes.
        """
        elapsed = time.monotonic() - pending.dispatched_at_monotonic
        if elapsed < self._novelty_read_delay_seconds:
            return NoveltyFrictionRequiredError(
                request_id=pending.request.request_id,
                required_friction=(
                    f"wait at least {self._novelty_read_delay_seconds:g}s after "
                    f"the dialog appears before signing (waited {elapsed:.1f}s)"
                ),
                friction_kind=NoveltyFrictionRequiredError.KIND_READ_DELAY_WALLCLOCK,
            )
        if FRICTION_TOKEN_READ_DELAY_COMPLETE not in pending.friction_acks:
            return NoveltyFrictionRequiredError(
                request_id=pending.request.request_id,
                required_friction=(
                    "acknowledge the read-delay step before signing "
                    f"(call acknowledge_friction({FRICTION_TOKEN_READ_DELAY_COMPLETE!r}))"
                ),
                friction_kind=NoveltyFrictionRequiredError.KIND_READ_DELAY_TOKEN_MISSING,
            )
        if pending.novelty_class == NoveltyClass.NOVEL:
            # Novel pattern → 5s read-delay + double-tap (high-stakes adds
            # cross-channel confirm; covered separately above).
            if FRICTION_TOKEN_DOUBLE_TAP not in pending.friction_acks:
                return NoveltyFrictionRequiredError(
                    request_id=pending.request.request_id,
                    required_friction=(
                        "complete the double-tap confirmation "
                        f"(call acknowledge_friction({FRICTION_TOKEN_DOUBLE_TAP!r}))"
                    ),
                    friction_kind=NoveltyFrictionRequiredError.KIND_DOUBLE_TAP_MISSING,
                )
        return None

    def _resolve_delegation_pubkey_hex(self) -> str:
        """Return the delegation key's public-key hex from the key manager.

        The wire-form Request carries the pubkey so verifiers can confirm
        the signature without a separate key-discovery hop. Phase 01 keys
        live in kailash's InMemoryKeyManager which exposes ``get_public_key``.
        Raises ``ValueError`` when the key manager surface is missing or
        the key has no public material — Phase 02 Trust Vault wrappers
        MUST expose the canonical interface (security-R1 MED-5: silent
        empty fallback ships unverifiable signed requests).
        """
        getter = getattr(self._key_manager, "get_public_key", None)
        if getter is None:
            raise ValueError(
                "key_manager does not expose get_public_key — Phase 01 cannot ship "
                "a verifiable GrantMomentRequest without a public-key resolver. "
                "Wrap the key manager with a compatible Trust Vault surface."
            )
        result = getter(self._delegation_key_id)
        if result is None:
            return ""
        if isinstance(result, bytes):
            return result.hex()
        return str(result)

    @staticmethod
    def _terminal_state_from_resolution(resolution: ResolutionShape) -> str:
        """Map ``ResolutionShape`` to ``GrantMomentOutcome.state``.

        ``ApproveResolution`` (both single + author variants) → APPROVED.
        ``ApproveWithModificationResolution`` → MODIFIED.
        ``DeclineResolution`` → DECLINED.
        """
        if isinstance(resolution, ApproveWithModificationResolution):
            return "MODIFIED"
        if isinstance(resolution, ApproveResolution):
            return "APPROVED"
        if isinstance(resolution, DeclineResolution):
            return "DECLINED"
        # Defensive — subclassing is not part of the public API but a
        # fail-loud branch surfaces the misuse rather than mis-categorizing.
        raise ValueError(f"Unknown ResolutionShape subclass: {type(resolution).__name__}")


def _now_iso() -> str:
    """ISO-8601 timestamp with explicit UTC zone (matches the ledger's
    ``_now_canonical`` shape for wire-form parity).
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
