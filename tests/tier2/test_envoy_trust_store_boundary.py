"""Tier 2: Boundary Conversation persistence + visible-secret round-trips.

Source: shard 8 § 5.2 (`01-analysis/08-boundary-conversation-implementation.md`)
+ `specs/boundary-conversation.md` § Persistence + resume (lines 33–35) +
§ Post-duress review step (lines 41–43).

Exercises the four Boundary-Conversation support methods added to
`TrustStoreAdapter` against a REAL tempfile-backed encrypted Trust Vault store
(real `sqlite3`, real `SqliteTrustStore`/`SQLitePostureStore` composition, real
Ed25519 key manager) — NO mocking per `rules/testing.md` § Tier 2. Every write
is verified by a read-back (Tier-3 discipline carried into Tier 2 for the
state-persistence surface per `rules/testing.md` § Tier 3 read-back contract).

The adapter is constructed exactly as the Tier 1 trust-store tests construct it
(`vault_path=` + `principal_id=`, then `await initialize()`); the persistence
flows through the same store the adapter owns (a dedicated SQLite region wrapped
into the Trust Vault container at T-01-13), not a parallel path.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from envoy.trust.store import TrustStoreAdapter
from envoy.trust.types import BoundaryConversationStateRow, VisibleSecret


PRINCIPAL = "alice@example"


@pytest.fixture
async def adapter(tmp_path: Path) -> AsyncGenerator[TrustStoreAdapter, None]:
    """Real initialized TrustStoreAdapter against a tempfile-backed store.

    Matches the Tier 1 trust-store fixture idiom (`vault_path=` + `principal_id=`)
    so the persistence surface is exercised against the SAME store composition
    production uses. `initialize()` creates the real SQLite tables.
    """
    a = TrustStoreAdapter(vault_path=tmp_path / "alice.vault", principal_id=PRINCIPAL)
    await a.initialize()
    try:
        yield a
    finally:
        await a.close()


class TestVisibleSecretRoundTrip:
    async def test_set_then_get_round_trip_equality(self, adapter: TrustStoreAdapter) -> None:
        """S7 set_visible_secret → get_visible_secret read-back equality."""
        await adapter.set_visible_secret(
            PRINCIPAL, icon="anchor", color="#0b6e4f", phrase="quiet harbor at dawn"
        )
        got = await adapter.get_visible_secret(PRINCIPAL)
        assert got == VisibleSecret(icon="anchor", color="#0b6e4f", phrase="quiet harbor at dawn")

    async def test_get_unset_returns_none(self, adapter: TrustStoreAdapter) -> None:
        """No visible secret set → get returns None (no raise)."""
        assert await adapter.get_visible_secret(PRINCIPAL) is None

    async def test_set_twice_overwrites(self, adapter: TrustStoreAdapter) -> None:
        """Upsert semantics: re-setting overwrites the prior visible secret."""
        await adapter.set_visible_secret(PRINCIPAL, icon="anchor", color="#0b6e4f", phrase="first")
        await adapter.set_visible_secret(PRINCIPAL, icon="kite", color="#c2410c", phrase="second")
        got = await adapter.get_visible_secret(PRINCIPAL)
        assert got == VisibleSecret(icon="kite", color="#c2410c", phrase="second")


class TestBoundaryConversationStateRoundTrip:
    async def test_persist_then_load_preserves_dicts_byte_for_byte(
        self, adapter: TrustStoreAdapter
    ) -> None:
        """persist → load: plan_dict + assembler_dict survive; state preserved."""
        plan = {
            "plan_id": "p-001",
            "state": "RUNNING",
            "nodes": [{"id": "S4", "kind": "question", "answered": True}],
            "suspension": None,
            "nested": {"unicode": "café", "n": 42, "flag": False},
        }
        assembler = {
            "financial": {"monthly_ceiling_usd": 250},
            "operational": {"blocked_topics": ["politics", "medical"]},
            "tool_output_budget_bytes": 4096,
        }
        await adapter.persist_boundary_conversation_state(
            "ritual-abc",
            plan_dict=plan,
            assembler_dict=assembler,
            principal_id=PRINCIPAL,
            current_state="S4",
        )
        row = await adapter.load_boundary_conversation_state("ritual-abc")
        assert isinstance(row, BoundaryConversationStateRow)
        assert row.ritual_id == "ritual-abc"
        assert row.principal_id == PRINCIPAL
        assert row.current_state == "S4"
        # Byte-for-byte (value-for-value) survival of both dicts.
        assert row.plan_dict == plan
        assert row.assembler_dict == assembler
        assert row.updated_at  # ISO timestamp populated

    async def test_persist_twice_same_ritual_loads_latest(self, adapter: TrustStoreAdapter) -> None:
        """Upsert: re-persisting same ritual_id with a new state loads latest."""
        await adapter.persist_boundary_conversation_state(
            "ritual-xyz",
            plan_dict={"state": "S2"},
            assembler_dict={"step": 2},
            principal_id=PRINCIPAL,
            current_state="S2",
        )
        await adapter.persist_boundary_conversation_state(
            "ritual-xyz",
            plan_dict={"state": "S5"},
            assembler_dict={"step": 5},
            principal_id=PRINCIPAL,
            current_state="S5",
        )
        row = await adapter.load_boundary_conversation_state("ritual-xyz")
        assert row is not None
        assert row.current_state == "S5"
        assert row.plan_dict == {"state": "S5"}
        assert row.assembler_dict == {"step": 5}

    async def test_load_absent_ritual_returns_none(self, adapter: TrustStoreAdapter) -> None:
        """Absent ritual_id → load returns None (no raise; runtime maps to
        its own RitualResumeStateMissingError)."""
        assert await adapter.load_boundary_conversation_state("never-persisted") is None


class TestShadowSegmentDuressEvents:
    async def test_returns_empty_list_in_phase_01(self, adapter: TrustStoreAdapter) -> None:
        """Phase 01 complete behavior: no duress detection wired → []."""
        assert await adapter.shadow_segment_unread_duress_events(PRINCIPAL) == []
