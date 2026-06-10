"""Tier 2: post-duress banner gate — multi-event + idempotent-ack + S0-scope.

Source: shard 8 § 3.6 + § 6.1 row "test_post_duress_banner" +
`specs/boundary-conversation.md` § Post-duress review step (lines 41–43).

T-02-44 prescribed coverage gap: the core duress-gate behavior (gate fires at
S0, acknowledge unblocks S0→S1) is covered by
`test_boundary_conversation_per_state_ledger_entries.py::TestDuressBannerGate`.
This dedicated file ADDS the missing contract-edge coverage:

1. Multi-event: when the shadow segment reports MULTIPLE unread duress events,
   the gate still blocks (one event is enough; more events do not relax the
   gate). The CLI/UI is the natural surfacing layer — this test pins that the
   adapter contract surfaces the full event list to the caller.
2. Idempotent ack: calling ``acknowledge_duress`` more than once does not
   raise and does not re-arm the gate.
3. Gate-scope-S0-only: once acknowledged at S0, the gate does NOT fire when
   advancing past S1+ — the banner is a session-entry gate, not a per-state
   re-prompt. (Existing test asserted only the S0→S1 unblock; this asserts
   forward states stay unblocked.)

NOT mocking real infrastructure — real `TrustStoreAdapter` (sqlite + Ed25519) +
real EnvoyLedger + real EnvelopeCompiler + real ShamirRitualCoordinator + real
NoveltyChecker; only the documented ``shadow_segment_unread_duress_events``
return is seeded via a real-adapter subclass (the P02 contract via the same
surface, per `_DuressSeededAdapter` pattern established in the sibling test).
The BYOM provider is deterministic-JSON (ADR-0006) — NOT a mock of real infra.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable
from pathlib import Path

import pytest

from envoy.authorship.novelty import NoveltyChecker
from envoy.boundary_conversation import (
    BoundaryConversationRuntime,
    DuressBannerUnacknowledgedError,
)
from envoy.envelope import EnvelopeCompiler, LocalTemplateResolver
from envoy.ledger import EnvoyLedger
from envoy.shamir import ShamirRitualCoordinator, TrustVaultChecklistPersister
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault

PRINCIPAL = "alice@example"

# Canonical per-state extractions — identical to the schedule pinned in
# test_boundary_conversation_per_state_ledger_entries.py so determinism stays
# in lock-step with the sibling tests.
_STATE_JSON: dict[str, dict] = {
    "S1_money": {"monthly_ceiling_microdollars": 250_000_000},
    "S2_people": {"blocked_contacts": ["ex@x.com"]},
    "S3_topics": {"blocked_topic_rules": ["no medical advice", "no political endorsements"]},
    "S4_hours": {"operating_hours": {"days": ["mon", "tue"], "tz": "UTC"}},
    "S5_first_task": {"first_task_intent": {"goal": "summarize my unread newsletters"}},
    "S6_template_offer": {"use_template": False, "template_id": ""},
    "S7_visible_secret": {"icon": "anchor", "color": "#0b6e4f", "phrase": "quiet harbor at dawn"},
    "S8_shamir": {"threshold": 3, "total_shards": 5, "distribution_mode": "default"},
    "S9_review_sign": {"plain_language_summary": "Your boundaries are set.", "signed": True},
}


class _DeterministicProvider:
    """BYOM provider returning canned JSON for whichever state's schema the
    prompt names (structural dispatch on rendered output fields)."""

    def chat(self, *, messages, model):  # noqa: ANN001 — provider duck-type
        prompt = messages[-1]["content"]
        for _state, payload in _STATE_JSON.items():
            if all(field in prompt for field in payload):
                return {"message": {"content": json.dumps(payload)}}
        return {"message": {"content": "{}"}}


class _DeterministicDeployment:
    preset_name = "ollama"
    default_model = "deterministic-byom"


class _DeterministicClient:
    deployment = _DeterministicDeployment()


class _DeterministicRouter:
    def for_primitive(self, primitive: str):  # noqa: ANN001
        return _DeterministicClient()


@pytest.fixture(autouse=True)
def _patch_provider(monkeypatch: pytest.MonkeyPatch):
    import envoy.boundary_conversation.runtime as rt_mod

    monkeypatch.setitem(
        rt_mod._PRESET_PROVIDER,
        "ollama",
        ("tests.tier2.test_post_duress_banner", "_DeterministicProvider"),
    )
    yield


class _MultiEventDuressAdapter(TrustStoreAdapter):
    """Real adapter with the P02-shape `shadow_segment_unread_duress_events`
    returning THREE unread events (the gate fires regardless of event count)."""

    EVENTS = [
        {"duress_event_id": "duress-001", "principal_id": PRINCIPAL, "kind": "session_takeover"},
        {"duress_event_id": "duress-002", "principal_id": PRINCIPAL, "kind": "device_lost"},
        {"duress_event_id": "duress-003", "principal_id": PRINCIPAL, "kind": "credentials_rotated"},
    ]

    async def shadow_segment_unread_duress_events(self, principal_id: str) -> list:
        await super().shadow_segment_unread_duress_events(principal_id)
        return list(self.EVENTS)


class _MasterKeySource:
    def __init__(self, vault: TrustVault) -> None:
        self._vault = vault

    def export_master_key_for_shamir(self) -> Awaitable[bytes]:
        return self._vault.export_master_key_for_shamir()


class _InMemoryGenesisBinder:
    def __init__(self) -> None:
        self.binding: dict[str, list[str]] = {}

    async def bind_to_genesis(self, principal_id: str, commitments: list[str]) -> None:
        self.binding[principal_id] = list(commitments)


@pytest.fixture
async def multi_event_adapter(
    tmp_path: Path,
) -> AsyncGenerator[_MultiEventDuressAdapter, None]:
    a = _MultiEventDuressAdapter(vault_path=tmp_path / "alice.vault", principal_id=PRINCIPAL)
    await a.initialize()
    try:
        yield a
    finally:
        await a.close()


def _make_runtime(
    *,
    adapter: TrustStoreAdapter,
    envoy_ledger: EnvoyLedger,
    unlocked_vault: TrustVault,
    tmp_path: Path,
) -> BoundaryConversationRuntime:
    shamir = ShamirRitualCoordinator(
        master_key_source=_MasterKeySource(unlocked_vault),
        commitment_binder=_InMemoryGenesisBinder(),
        paper_renderer=PaperShardRenderer(),
        checklist_persister=TrustVaultChecklistPersister(
            trust_vault=unlocked_vault, principal_id=PRINCIPAL
        ),
        principal_id=PRINCIPAL,
    )
    return BoundaryConversationRuntime(
        model_router=_DeterministicRouter(),
        trust_store=adapter,
        ledger=envoy_ledger,
        envelope_compiler=EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path)),
        shamir_coordinator=shamir,
        novelty_checker=NoveltyChecker(),
    )


class TestPostDuressBannerMultiEvent:
    async def test_multi_event_shadow_segment_surfaces_full_list(
        self, multi_event_adapter: _MultiEventDuressAdapter
    ) -> None:
        """The adapter surface returns the full event list to the caller (CLI/UI
        renders each event — runtime only gates on presence)."""
        events = await multi_event_adapter.shadow_segment_unread_duress_events(PRINCIPAL)
        assert len(events) == 3
        ids = {e["duress_event_id"] for e in events}
        assert ids == {"duress-001", "duress-002", "duress-003"}

    async def test_multi_event_gate_blocks_S0_advance(
        self,
        multi_event_adapter: _MultiEventDuressAdapter,
        envoy_ledger: EnvoyLedger,
        unlocked_vault: TrustVault,
        tmp_path: Path,
    ) -> None:
        """Three unread events still block S0→S1 advance with the SAME typed
        error as one event (count does not relax the gate)."""
        runtime = _make_runtime(
            adapter=multi_event_adapter,
            envoy_ledger=envoy_ledger,
            unlocked_vault=unlocked_vault,
            tmp_path=tmp_path,
        )
        ritual_id = await runtime.start(principal_id=PRINCIPAL)
        with pytest.raises(DuressBannerUnacknowledgedError):
            await runtime.advance(ritual_id, "let's begin")


class TestAcknowledgeDuressIdempotent:
    async def test_acknowledge_twice_does_not_raise(
        self,
        multi_event_adapter: _MultiEventDuressAdapter,
        envoy_ledger: EnvoyLedger,
        unlocked_vault: TrustVault,
        tmp_path: Path,
    ) -> None:
        """Calling acknowledge_duress more than once is a no-op (the UI may
        ack on every banner-dismiss render; the contract MUST be idempotent)."""
        runtime = _make_runtime(
            adapter=multi_event_adapter,
            envoy_ledger=envoy_ledger,
            unlocked_vault=unlocked_vault,
            tmp_path=tmp_path,
        )
        ritual_id = await runtime.start(principal_id=PRINCIPAL)
        runtime.acknowledge_duress(ritual_id)
        runtime.acknowledge_duress(ritual_id)  # second call MUST NOT raise
        runtime.acknowledge_duress(ritual_id)  # third — still a no-op
        # Gate stays unblocked after repeated acks.
        out = await runtime.advance(ritual_id, "let's begin")
        assert out.state == "IN_PROGRESS"
        assert out.current_state == "S1_money"


class TestDuressGateScopeS0Only:
    async def test_advance_past_S1_does_not_re_block_after_ack(
        self,
        multi_event_adapter: _MultiEventDuressAdapter,
        envoy_ledger: EnvoyLedger,
        unlocked_vault: TrustVault,
        tmp_path: Path,
    ) -> None:
        """The duress banner is a session-entry gate, NOT a per-state re-prompt.
        Once acknowledged at S0, subsequent advances (S1→S2, S2→S3, …) MUST NOT
        re-trigger the gate even though the shadow segment still reports the
        unread events (acknowledgement is in-session-only in Phase 01)."""
        runtime = _make_runtime(
            adapter=multi_event_adapter,
            envoy_ledger=envoy_ledger,
            unlocked_vault=unlocked_vault,
            tmp_path=tmp_path,
        )
        ritual_id = await runtime.start(principal_id=PRINCIPAL)
        runtime.acknowledge_duress(ritual_id)

        # S0 → S1 (the previously-blocked transition; now passes).
        out = await runtime.advance(ritual_id, "let's begin")
        assert out.current_state == "S1_money"

        # S1..S6 forward — each advance MUST NOT raise DuressBannerUnacknowledgedError.
        for state in ("S1_money", "S2_people", "S3_topics", "S4_hours", "S5_first_task"):
            out = await runtime.advance(ritual_id, f"my answer for {state}")
            assert out.state == "IN_PROGRESS", (state, out.error)
            # Gate is structurally NOT re-checked at S1+ — confirm by absence
            # of the error and forward progress.

        # Final check: we reached S6, not stuck at S1.
        assert runtime.current_state(ritual_id) == "S6_template_offer"
