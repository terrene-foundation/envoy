"""Tier 2: S8 Shamir pause → suspension shape → resume clears it.

Source: shard 8 § 6.1 row "test_boundary_conversation_pause_resume_shamir"
+ § 3.3 (mid-conversation pause composes with PlanSuspension) + § 5.5
(run_first_time_ritual — NOT the stale start_3_of_5).

Drives the runtime to S8 with REAL infrastructure (real EnvoyLedger, real
TrustStoreAdapter, real EnvelopeCompiler, real ShamirRitualCoordinator over a
real TrustVault, real NoveltyChecker); the BYOM model is a deterministic local
provider (see test_boundary_conversation_per_state_ledger_entries.py rationale).

Asserts:
1. At S8 the Plan suspends; ``Plan.to_dict()["suspension"]["reason"]["kind"]``
   == "explicit_cancellation" and the reason == "shamir_ritual_in_progress".
2. Reaching S9 while still suspended raises ShamirRitualIncompleteError.
3. After the suspension is cleared (physical ritual complete), S9 completes and
   the suspension is None.

Per `rules/probe-driven-verification.md` MUST-3: structural assertions on the
serialized suspension shape + the typed-error raise.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable
from pathlib import Path

import pytest
from kailash.trust.audit_store import AuditFilter, InMemoryAuditStore

from envoy.authorship.novelty import NoveltyChecker
from envoy.boundary_conversation import (
    BoundaryConversationRuntime,
    InvalidStateTransitionError,
    ShamirRitualIncompleteError,
)
from envoy.envelope import EnvelopeCompiler, LocalTemplateResolver
from envoy.ledger import EnvoyLedger
from envoy.shamir import ShamirRitualCoordinator, TrustVaultChecklistPersister
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault

PRINCIPAL = "alice@example"
_ENVELOPE_KEY = "_envoy_envelope_v1"

_STATE_JSON: dict[str, dict] = {
    "S1_money": {"monthly_ceiling_microdollars": 250_000_000},
    "S2_people": {"blocked_contacts": ["ex@x.com"]},
    "S3_topics": {"blocked_topic_rules": ["no medical advice"]},
    "S4_hours": {"operating_hours": {"days": ["mon"], "tz": "UTC"}},
    "S5_first_task": {"first_task_intent": {"goal": "summarize"}},
    "S6_template_offer": {"use_template": False, "template_id": ""},
    "S7_visible_secret": {"icon": "anchor", "color": "#0b6e4f", "phrase": "quiet harbor"},
    "S8_shamir": {"threshold": 3, "total_shards": 5, "distribution_mode": "default"},
    "S9_review_sign": {"plain_language_summary": "ok", "signed": True},
}


class _DeterministicProvider:
    def chat(self, *, messages, model):  # noqa: ANN001
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
        ("tests.tier2.test_boundary_conversation_pause_resume_shamir", "_DeterministicProvider"),
    )
    yield


@pytest.fixture
async def trust_adapter(tmp_path: Path) -> AsyncGenerator[TrustStoreAdapter, None]:
    a = TrustStoreAdapter(vault_path=tmp_path / "alice.vault", principal_id=PRINCIPAL)
    await a.initialize()
    try:
        yield a
    finally:
        await a.close()


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
async def runtime(
    trust_adapter: TrustStoreAdapter,
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
        trust_store=trust_adapter,
        ledger=envoy_ledger,
        envelope_compiler=EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path)),
        shamir_coordinator=shamir,
        novelty_checker=NoveltyChecker(),
    )


async def _drive_to_shamir_pause(runtime: BoundaryConversationRuntime) -> str:
    ritual_id = await runtime.start(principal_id=PRINCIPAL)
    await runtime.advance(ritual_id, "begin")
    for _ in range(7):  # S1..S7
        out = await runtime.advance(ritual_id, "answer")
        assert out.state == "IN_PROGRESS", out.error
    paused = await runtime.advance(ritual_id, "default backup")  # S8
    assert paused.state == "PAUSED"
    return ritual_id


class TestShamirSuspensionShape:
    async def test_suspension_serializes_as_explicit_cancellation(
        self, runtime: BoundaryConversationRuntime
    ) -> None:
        ritual_id = await _drive_to_shamir_pause(runtime)
        plan = runtime.current_plan(ritual_id)
        d = plan.to_dict()
        assert d["suspension"] is not None
        reason = d["suspension"]["reason"]
        assert reason["kind"] == "explicit_cancellation"
        assert reason["reason"] == "shamir_ritual_in_progress"


class TestShamirGateBeforeSign:
    async def test_reaching_s9_while_suspended_raises_incomplete(
        self, runtime: BoundaryConversationRuntime
    ) -> None:
        """If the user tries to sign (S9) before completing the physical ritual
        (suspension still set), ShamirRitualIncompleteError forces back to S8."""
        ritual_id = await _drive_to_shamir_pause(runtime)
        # Suspension is still set — advancing S9 must surface the typed error.
        outcome = await runtime.advance(ritual_id, "yes sign it")
        assert outcome.state == "ERROR"
        assert isinstance(outcome.error, ShamirRitualIncompleteError)
        # Forced back to S8.
        assert runtime.current_state(ritual_id) == "S8_shamir"


class TestResumeClearsSuspension:
    async def test_complete_ritual_then_resume_then_sign(
        self, runtime: BoundaryConversationRuntime
    ) -> None:
        ritual_id = await _drive_to_shamir_pause(runtime)
        # User completes the physical card distribution offline → the resume
        # flow clears the Plan suspension through the PUBLIC clear-path.
        await runtime.resume_from_shamir(ritual_id)
        done = await runtime.advance(ritual_id, "yes, sign it")
        assert done.state == "COMPLETE"
        assert done.envelope_id
        # Suspension cleared on the completed plan.
        assert runtime.current_plan(ritual_id).to_dict()["suspension"] is None


class TestShamirResumeClearPath:
    async def test_boundary_conversation_shamir_resume_clear_path(
        self,
        runtime: BoundaryConversationRuntime,
        audit_store: InMemoryAuditStore,
    ) -> None:
        """R1-HIGH-1: the PUBLIC resume_from_shamir clears the S8 suspension,
        records a `resumed_from:"shamir_ritual"` Ledger entry, and unblocks S9 —
        a real user who gate-locked at S8→S9 can now sign."""
        ritual_id = await _drive_to_shamir_pause(runtime)

        # At S8 the Plan is PAUSED with a suspension set.
        assert runtime.current_plan(ritual_id).suspension is not None

        # PUBLIC clear-path: completion confirmation (offline ritual done).
        resumed = await runtime.resume_from_shamir(ritual_id)
        assert resumed.state == "IN_PROGRESS"
        assert resumed.current_state == "S9_review_sign"
        # Suspension is cleared.
        assert runtime.current_plan(ritual_id).suspension is None

        # A resumed_from:"shamir_ritual" Ledger entry was recorded.
        events = await audit_store.query(AuditFilter(limit=1_000_000))
        envelopes = [
            e.metadata[_ENVELOPE_KEY] for e in events if _ENVELOPE_KEY in (e.metadata or {})
        ]
        resume_entries = [
            env
            for env in envelopes
            if env["type"] == "session_boundary_crossed"
            and env["content"].get("resumed_from") == "shamir_ritual"
        ]
        assert resume_entries, f"no resumed_from:shamir_ritual entry found: {envelopes}"

        # S9 now completes — the user can sign.
        done = await runtime.advance(ritual_id, "yes, sign it")
        assert done.state == "COMPLETE"
        assert done.envelope_id

    async def test_resume_from_shamir_when_not_suspended_raises(
        self, runtime: BoundaryConversationRuntime
    ) -> None:
        """resume_from_shamir on a conversation that is NOT Shamir-suspended
        raises InvalidStateTransitionError rather than silently no-op'ing."""
        ritual_id = await runtime.start(principal_id=PRINCIPAL)
        await runtime.advance(ritual_id, "begin")  # S0 → S1, no suspension
        with pytest.raises(InvalidStateTransitionError):
            await runtime.resume_from_shamir(ritual_id)
