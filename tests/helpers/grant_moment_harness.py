"""tests.helpers.grant_moment_harness — shared Grant Moment runtime fixtures.

Per `rules/testing.md` § Tier 2: real InMemoryKeyManager + real EnvoyLedger
over InMemoryAuditStore + real ChannelHandoff with structural adapter stubs
(no ``unittest.mock``). Per `rules/agent-reasoning.md`: structural plumbing
only — adapter stubs record what they received; no LLM, no keyword routing.

The harness lives under ``tests/helpers/`` so both ``tests/integration/`` and
``tests/e2e/`` can import it without conftest sibling-discovery dependencies.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from kailash.trust.audit_store import AuditFilter, InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager


async def _list_events(audit_store: InMemoryAuditStore) -> list:
    """Helper: query all events via the AuditFilter surface."""
    return await audit_store.query(AuditFilter())


from envoy.grant_moment import (
    CascadeRevocationOrchestrator,
    ChannelHandoff,
    ConsequencePreview,
    EnvoyGrantMomentRuntime,
    GrantMomentRequest,
    NoveltyClassifier,
    NoveltySignals,
    PlanSuspensionBridge,
)
from envoy.ledger import EnvoyLedger

DEFAULT_PRINCIPAL_ID = "sha256:test-principal-genesis-id"
DEFAULT_DEVICE_ID = "device-test"
DEFAULT_DELEGATION_KEY = "envoy-test-delegation-key"
DEFAULT_LEDGER_SIGNING_KEY = "envoy-test-ledger-signing-key"
DEFAULT_ENVELOPE_ID = "env-test-001"
DEFAULT_ENVELOPE_HASH = "sha256:env-hash"
DEFAULT_INTENT_PREFIX = "sha256:intent-"
DEFAULT_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}


@dataclass
class RecordingChannelAdapter:
    """Real adapter implementation; records every render call."""

    channel_id: str
    renders: list[GrantMomentRequest] = field(default_factory=list)
    raise_on_render: type[Exception] | None = None
    render_delay_seconds: float = 0.0

    async def render_grant_moment(self, request: GrantMomentRequest) -> None:
        if self.render_delay_seconds > 0:
            await asyncio.sleep(self.render_delay_seconds)
        if self.raise_on_render is not None:
            raise self.raise_on_render(f"{self.channel_id}: stub render raised")
        self.renders.append(request)


@dataclass
class StubVisibleSecret:
    icon: str = "shield"
    color: str = "blue"
    phrase: str = "test-visible-phrase-correct-horse-battery"


@dataclass
class StubTrustStore:
    """Minimal trust store satisfying the runtime's visible-secret protocol."""

    secret: StubVisibleSecret | None = field(default_factory=StubVisibleSecret)

    async def get_visible_secret(self, _principal_id: str) -> StubVisibleSecret | None:
        return self.secret


@dataclass
class StubTrustRuntime:
    """Satisfies cascade_orchestrator's _RuntimeProtocol."""

    cascade_responses: dict[str, set[str]] = field(default_factory=dict)

    def trust_cascade_revoke(self, root_id: str) -> set[str]:
        return self.cascade_responses.get(root_id, set())


async def make_runtime(
    *,
    primary_channel_id: str = "cli",
    adapter_channel_ids: tuple[str, ...] = ("cli",),
    queue_ceiling: int = 5,
    default_timeout_seconds: int = 300,
    novelty_read_delay_seconds: float = 0.0,
    velocity_raise_cooling_off_seconds: int = 24 * 60 * 60,
    dedup_store_ceiling: int = 100_000,
    cascade_responses: dict[str, set[str]] | None = None,
    trust_store: StubTrustStore | None = None,
    plan_suspension_bridge: PlanSuspensionBridge | None = None,
) -> tuple[
    EnvoyGrantMomentRuntime,
    InMemoryKeyManager,
    EnvoyLedger,
    InMemoryAuditStore,
    list[RecordingChannelAdapter],
]:
    """Spin up a real-infra runtime for tier-2 / tier-3 tests.

    Returns ``(runtime, key_manager, ledger, audit_store, adapters)`` so
    callers can assert on each layer's externally-observable effects.
    """
    key_manager = InMemoryKeyManager()
    await key_manager.generate_keypair(DEFAULT_DELEGATION_KEY)
    await key_manager.generate_keypair(DEFAULT_LEDGER_SIGNING_KEY)

    audit_store = InMemoryAuditStore()
    ledger = EnvoyLedger(
        audit_store=audit_store,
        key_manager=key_manager,
        signing_key_id=DEFAULT_LEDGER_SIGNING_KEY,
        device_id=DEFAULT_DEVICE_ID,
        algorithm_identifier=DEFAULT_ALGO_ID,
    )

    adapters = tuple(RecordingChannelAdapter(channel_id=cid) for cid in adapter_channel_ids)
    handoff = ChannelHandoff(adapters=adapters, primary_channel_id=primary_channel_id)

    cascade = CascadeRevocationOrchestrator(
        runtime=StubTrustRuntime(cascade_responses=cascade_responses or {})
    )

    runtime = EnvoyGrantMomentRuntime(
        key_manager=key_manager,
        delegation_key_id=DEFAULT_DELEGATION_KEY,
        principal_id=DEFAULT_PRINCIPAL_ID,
        device_id=DEFAULT_DEVICE_ID,
        ledger=ledger,
        channel_handoff=handoff,
        trust_store=trust_store,
        cascade_orchestrator=cascade,
        plan_suspension_bridge=plan_suspension_bridge,
        novelty_classifier=NoveltyClassifier(),
        default_timeout_seconds=default_timeout_seconds,
        novelty_read_delay_seconds=novelty_read_delay_seconds,
        queue_ceiling=queue_ceiling,
        velocity_raise_cooling_off_seconds=velocity_raise_cooling_off_seconds,
        dedup_store_ceiling=dedup_store_ceiling,
    )
    return runtime, key_manager, ledger, audit_store, list(adapters)


def make_familiar_repeat_signals() -> NoveltySignals:
    """All-False novel axes + no override → NoveltyClass.FAMILIAR_REPEAT."""
    return NoveltySignals(
        unseen_recipient=False,
        dollar_range_outside_p50=False,
        tool_unseen_in_7d=False,
        new_ngram_sequence=False,
        high_stakes_override=False,
    )


def make_novel_signals() -> NoveltySignals:
    """One novel axis True → NoveltyClass.NOVEL."""
    return NoveltySignals(
        unseen_recipient=True,
        dollar_range_outside_p50=False,
        tool_unseen_in_7d=False,
        new_ngram_sequence=False,
        high_stakes_override=False,
    )


def make_high_stakes_signals() -> NoveltySignals:
    """High-stakes override True → NoveltyClass.HIGH_STAKES."""
    return NoveltySignals(
        unseen_recipient=False,
        dollar_range_outside_p50=False,
        tool_unseen_in_7d=False,
        new_ngram_sequence=False,
        high_stakes_override=True,
    )


def make_consequence_preview() -> ConsequencePreview:
    """Standard low-stakes preview for tests that don't care about details."""
    return ConsequencePreview(
        budget_microdollars=1_000,
        reversibility="reversible",
        recipient="test@example.com",
        data_classification="Internal",
    )


def make_issue_kwargs(
    *,
    nonce: str | None = None,
    intent_id: str | None = None,
    tool_name: str = "send_email",
    primary_only: bool = False,
    novelty_signals: NoveltySignals | None = None,
    consequence_preview: ConsequencePreview | None = None,
    why_asking: str = "envelope_violation",
    timeout_seconds: int | None = None,
    is_velocity_raise: bool = False,
    is_cross_principal: bool = False,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Build the issue_grant_moment kwargs with sane defaults."""
    return {
        "intent_id": intent_id or (DEFAULT_INTENT_PREFIX + uuid.uuid4().hex),
        "nonce": nonce or uuid.uuid4().hex,
        "tool_name": tool_name,
        "tool_args_canonical": {"to": "ops@example.com", "subject": "test"},
        "tool_args_canonical_hash": "sha256:test-args-hash",
        "envelope_id": DEFAULT_ENVELOPE_ID,
        "envelope_version": 1,
        "envelope_hash": DEFAULT_ENVELOPE_HASH,
        "why_asking": why_asking,
        "consequence_preview": consequence_preview or make_consequence_preview(),
        "novelty_signals": novelty_signals or make_familiar_repeat_signals(),
        "primary_only": primary_only,
        "timeout_seconds": timeout_seconds,
        "is_velocity_raise": is_velocity_raise,
        "is_cross_principal": is_cross_principal,
        "session_id": session_id,
    }
