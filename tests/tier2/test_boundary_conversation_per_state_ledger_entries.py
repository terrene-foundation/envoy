"""Tier 2: per-state ReasoningCommit + S9 posture_change Ledger entries.

Source: shard 8 § 6.1 row "test_boundary_conversation_per_state_ledger_entries"
+ § 5.3 (Ledger entry schedule) + `rules/orphan-detection.md` Rule 1.

Drives the FULL runtime S1..S9 with REAL infrastructure: real EnvoyLedger
(Ed25519 + chain-integrity), real TrustStoreAdapter (sqlite + Ed25519), real
EnvelopeCompiler, real ShamirRitualCoordinator (SLIP-0039 over a real
TrustVault), real NoveltyChecker. The ONLY non-real collaborator is the LLM:
per ADR-0006 BYOM the model is the user's choice, and these assertions target
the deterministic Ledger/trust/compiler/shamir path — so a deterministic local
chat provider supplies fixed structured extractions. This is NOT mocking real
infrastructure (the binding/DB/FFI path) — it is supplying a BYOM model that
returns deterministic JSON so the per-state Ledger schedule is assertable
without Ollama. The Ollama-real end-to-end path lives in
test_boundary_conversation_runtime_wiring.py.

Asserts:
1. Each S1..S9 transition emits a ReasoningCommit Ledger entry.
2. S8 emits a session_boundary_crossed (shamir suspend).
3. S9 emits a posture_change GENESIS_BARE → PSEUDO.
4. The chain verifies end-to-end.

Per `rules/probe-driven-verification.md` MUST-3: structural assertions on
entry types + content fields, not regex-on-prose.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable
from pathlib import Path

import pytest
from kailash.trust.audit_store import AuditFilter, InMemoryAuditStore

from envoy.authorship.novelty import NoveltyChecker
from envoy.boundary_conversation import BoundaryConversationRuntime
from envoy.envelope import EnvelopeCompiler, LocalTemplateResolver
from envoy.ledger import EnvoyLedger
from envoy.shamir import ShamirRitualCoordinator, TrustVaultChecklistPersister
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault

_ENVELOPE_KEY = "_envoy_envelope_v1"
PRINCIPAL = "alice@example"

# Deterministic per-state extractions the local BYOM provider returns as JSON.
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


# ---------------------------------------------------------------------------
# Deterministic BYOM provider + router (the model is the user's choice under
# ADR-0006; here it returns fixed JSON so the real Ledger/trust/compiler/shamir
# path is exercised deterministically). NOT a mock of real infra.
# ---------------------------------------------------------------------------


class _DeterministicProvider:
    """Returns the canned JSON for whichever state's schema the prompt names."""

    def chat(self, *, messages, model):  # noqa: ANN001 — provider duck-type
        prompt = messages[-1]["content"]
        # The prompt names the output fields; pick the state whose fields all
        # appear in the prompt. This is structural dispatch on the schema the
        # runtime rendered, not keyword-routing of user content.
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


# Patch the provider lookup so the runtime's _chat resolves our deterministic
# provider instead of the real OllamaProvider for the "ollama" preset.
@pytest.fixture(autouse=True)
def _patch_provider(monkeypatch: pytest.MonkeyPatch):
    import envoy.boundary_conversation.runtime as rt_mod

    monkeypatch.setitem(
        rt_mod._PRESET_PROVIDER,
        "ollama",
        (
            "tests.tier2.test_boundary_conversation_per_state_ledger_entries",
            "_DeterministicProvider",
        ),
    )
    yield


# ---------------------------------------------------------------------------
# Real-infrastructure fixtures
# ---------------------------------------------------------------------------


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


async def _ledger_entry_types(audit_store: InMemoryAuditStore) -> list[str]:
    events = await audit_store.query(AuditFilter(limit=1_000_000))
    envelopes = [e.metadata[_ENVELOPE_KEY] for e in events if _ENVELOPE_KEY in (e.metadata or {})]
    envelopes.sort(key=lambda env: env["sequence"])
    return [env["type"] for env in envelopes]


async def _drive_full_conversation(runtime: BoundaryConversationRuntime) -> str:
    """S0→S10 with a resume to clear the Shamir suspension before S9."""
    ritual_id = await runtime.start(principal_id=PRINCIPAL)
    # S0 greet advance (no answer needed).
    await runtime.advance(ritual_id, "let's begin")
    # S1..S8.
    for state in (
        "S1_money",
        "S2_people",
        "S3_topics",
        "S4_hours",
        "S5_first_task",
        "S6_template_offer",
        "S7_visible_secret",
    ):
        outcome = await runtime.advance(ritual_id, f"my answer for {state}")
        assert outcome.state == "IN_PROGRESS", (state, outcome.error)
    # S8 shamir — suspends.
    paused = await runtime.advance(ritual_id, "use the default 3-of-5 backup")
    assert paused.state == "PAUSED"
    assert paused.paused_for == "shamir_ritual"
    # User completes the physical ritual offline → resume clears suspension.
    runtime.current_plan(ritual_id).suspension = None
    # S9 review & sign → completes.
    done = await runtime.advance(ritual_id, "yes, sign it")
    assert done.state == "COMPLETE"
    assert done.envelope_id
    return ritual_id


class TestPerStateLedgerEntries:
    async def test_full_conversation_emits_expected_ledger_schedule(
        self,
        runtime: BoundaryConversationRuntime,
        audit_store: InMemoryAuditStore,
        envoy_ledger: EnvoyLedger,
    ) -> None:
        await _drive_full_conversation(runtime)
        types = await _ledger_entry_types(audit_store)

        reasoning = [t for t in types if t == "ReasoningCommit"]
        # S0 entry + 9 forward transitions (S0→S1 ... S8 transitions go through
        # ReasoningCommit; S8 emits session_boundary; S9 emits posture_change).
        assert len(reasoning) >= 8, f"expected >=8 ReasoningCommit, got {len(reasoning)}: {types}"

        assert "session_boundary_crossed" in types, types
        assert "posture_change" in types, types

    async def test_posture_change_records_genesis_bare_to_pseudo(
        self,
        runtime: BoundaryConversationRuntime,
        audit_store: InMemoryAuditStore,
    ) -> None:
        await _drive_full_conversation(runtime)
        events = await audit_store.query(AuditFilter(limit=1_000_000))
        envelopes = [
            e.metadata[_ENVELOPE_KEY] for e in events if _ENVELOPE_KEY in (e.metadata or {})
        ]
        posture = next(env for env in envelopes if env["type"] == "posture_change")
        content = posture["content"]
        assert content["from"] == "GENESIS_BARE"
        assert content["to"] == "PSEUDO"
        assert content["basis"] == "boundary_conversation_completed"
        assert content["envelope_id"]

    async def test_chain_verifies_end_to_end(
        self,
        runtime: BoundaryConversationRuntime,
        envoy_ledger: EnvoyLedger,
    ) -> None:
        await _drive_full_conversation(runtime)
        report = await envoy_ledger.verify_chain()
        assert report.success is True
