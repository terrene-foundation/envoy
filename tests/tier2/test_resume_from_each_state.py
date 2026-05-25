"""Tier 2 (NO LLM): RitualResumeCoordinator persist → reconstruct each state.

Source: shard 8 § 6.1 row "test_resume_from_each_state" + spec
`Test location` line 70 + § 3.3 (per-state Trust-Vault persistence).

Drives the resume coordinator directly against a REAL tempfile-backed
TrustStoreAdapter (real sqlite3, real store composition) — NO LLM, NO
conversation. For each conversation state S0..S9, the test:

1. builds the Plan-DAG + feeds the assembler up to that state,
2. persists via the coordinator,
3. reconstructs via ``load_state`` on a SECOND coordinator (fresh process
   simulation — the store is the only shared state),
4. asserts the rehydrated Plan + assembler + current_state match.

Plus the absent-ritual path: ``load_state`` on an unknown ritual_id raises
``RitualResumeStateMissingError`` carrying the offending id.

Per `rules/testing.md` Tier 2: real store, NO mocking. Every write verified by
a read-back through a fresh coordinator (Tier-3 read-back discipline).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from envoy.boundary_conversation import (
    BOUNDARY_CONVERSATION_STATES,
    BoundaryConversationScript,
    RitualResumeStateMissingError,
)
from envoy.boundary_conversation.envelope_assembler import EnvelopeConfigInputAssembler
from envoy.boundary_conversation.resume import RitualResumeCoordinator
from envoy.trust.store import TrustStoreAdapter


PRINCIPAL = "alice@example"

# A representative extraction per state, used to feed the assembler so the
# round-trip exercises non-trivial accumulated content.
_STATE_EXTRACTIONS: dict[str, dict] = {
    "S1_money": {"monthly_ceiling_microdollars": 250_000_000},
    "S2_people": {"blocked_contacts": ["ex@x.com"]},
    "S3_topics": {"blocked_topic_rules": ["no medical advice"]},
    "S4_hours": {"operating_hours": {"days": ["mon"], "tz": "UTC"}},
    "S5_first_task": {"first_task_intent": {"goal": "summarize"}},
    "S6_template_offer": {"use_template": False, "template_id": ""},
    "S7_visible_secret": {"icon": "anchor", "color": "#0b6e4f", "phrase": "quiet harbor"},
    "S8_shamir": {"threshold": 3, "total_shards": 5, "distribution_mode": "default"},
}


@pytest.fixture
async def adapter(tmp_path: Path) -> AsyncGenerator[TrustStoreAdapter, None]:
    a = TrustStoreAdapter(vault_path=tmp_path / "alice.vault", principal_id=PRINCIPAL)
    await a.initialize()
    try:
        yield a
    finally:
        await a.close()


def _plan_and_assembler_up_to(state: str) -> tuple:
    """Build a Plan and assembler with extractions fed up to (and including)
    ``state`` along the canonical S0→S10 spine."""
    plan = BoundaryConversationScript().build_plan()
    assembler = EnvelopeConfigInputAssembler()
    for s in BOUNDARY_CONVERSATION_STATES:
        if s in _STATE_EXTRACTIONS:
            assembler.feed(s, _STATE_EXTRACTIONS[s])
        if s == state:
            break
    return plan, assembler


class TestResumeFromEachState:
    @pytest.mark.parametrize("state", list(BOUNDARY_CONVERSATION_STATES[:-1]))
    async def test_persist_then_reconstruct_each_state(
        self, adapter: TrustStoreAdapter, state: str
    ) -> None:
        """For each state S0..S9: persist via one coordinator, reconstruct via a
        fresh coordinator, assert plan + assembler + current_state survive."""
        plan, assembler = _plan_and_assembler_up_to(state)
        ritual_id = f"ritual-{state}"

        writer = RitualResumeCoordinator(trust_store=adapter)
        await writer.persist_state(
            ritual_id,
            plan=plan,
            assembler=assembler,
            principal_id=PRINCIPAL,
            current_state=state,
        )

        # Fresh coordinator = process-restart simulation; the store is the only
        # shared state.
        reader = RitualResumeCoordinator(trust_store=adapter)
        resumed = await reader.load_state(ritual_id)

        assert resumed.ritual_id == ritual_id
        assert resumed.principal_id == PRINCIPAL
        assert resumed.current_state == state
        # Plan survived the to_dict/from_dict round-trip: same nodes + edges.
        assert set(resumed.plan.nodes) == set(plan.nodes)
        assert len(resumed.plan.edges) == len(plan.edges)
        # Assembler survived: same fed states + same accumulated extractions.
        assert resumed.assembler.fed_states == assembler.fed_states
        assert resumed.assembler.to_dict() == assembler.to_dict()

    async def test_reconstructed_assembler_assembles_identically(
        self, adapter: TrustStoreAdapter
    ) -> None:
        """A reconstructed assembler at S8 assembles to the same
        EnvelopeConfigInput shape as the pre-persist assembler."""
        plan, assembler = _plan_and_assembler_up_to("S8_shamir")
        writer = RitualResumeCoordinator(trust_store=adapter)
        await writer.persist_state(
            "ritual-s8",
            plan=plan,
            assembler=assembler,
            principal_id=PRINCIPAL,
            current_state="S8_shamir",
        )
        resumed = await RitualResumeCoordinator(trust_store=adapter).load_state("ritual-s8")
        before = assembler.assemble()
        after = resumed.assembler.assemble()
        assert before.financial.per_month_ceiling_microdollars == 250_000_000
        assert after.financial.per_month_ceiling_microdollars == 250_000_000
        assert [c.constraint_id for c in after.communication.authored_constraints] == [
            c.constraint_id for c in before.communication.authored_constraints
        ]


class TestResumeStateMissing:
    async def test_absent_ritual_raises_typed_error(self, adapter: TrustStoreAdapter) -> None:
        """load_state on an unknown ritual_id raises RitualResumeStateMissingError
        carrying the offending id (the store's None is mapped here, not in the
        store)."""
        coordinator = RitualResumeCoordinator(trust_store=adapter)
        with pytest.raises(RitualResumeStateMissingError) as exc_info:
            await coordinator.load_state("never-persisted-ritual")
        assert exc_info.value.ritual_id == "never-persisted-ritual"


class TestListPendingRituals:
    async def test_lists_rituals_persisted_this_session(self, adapter: TrustStoreAdapter) -> None:
        """list_pending_rituals returns the rituals persisted for the principal,
        sorted."""
        coordinator = RitualResumeCoordinator(trust_store=adapter)
        plan, assembler = _plan_and_assembler_up_to("S1_money")
        for rid in ("ritual-b", "ritual-a"):
            await coordinator.persist_state(
                rid,
                plan=plan,
                assembler=assembler,
                principal_id=PRINCIPAL,
                current_state="S1_money",
            )
        assert coordinator.list_pending_rituals(PRINCIPAL) == ["ritual-a", "ritual-b"]
        assert coordinator.list_pending_rituals("someone-else@example") == []
