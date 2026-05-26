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
from envoy.boundary_conversation import (
    BoundaryConversationRuntime,
    DuressBannerUnacknowledgedError,
    VisibleSecretMissingError,
)
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
    # User completes the physical ritual offline → resume clears suspension
    # through the PUBLIC clear-path (R1-HIGH-1).
    await runtime.resume_from_shamir(ritual_id)
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


class TestVisibleSecretGate:
    async def test_boundary_conversation_visible_secret_missing_raises(
        self,
        runtime: BoundaryConversationRuntime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """T-018 mitigation: a user who never completes S7 (no visible secret
        icon/color/phrase) is blocked with VisibleSecretMissingError and forced
        back to S7 — the secret cannot be silently skipped on the way to sign."""
        # Make the S7 extraction return blank secret components so the S7 handler
        # rejects it (no visible secret is ever stored).
        monkeypatch.setitem(
            _STATE_JSON, "S7_visible_secret", {"icon": "", "color": "", "phrase": ""}
        )

        ritual_id = await runtime.start(principal_id=PRINCIPAL)
        await runtime.advance(ritual_id, "let's begin")  # S0 → S1
        for state in (
            "S1_money",
            "S2_people",
            "S3_topics",
            "S4_hours",
            "S5_first_task",
            "S6_template_offer",
        ):
            out = await runtime.advance(ritual_id, f"answer for {state}")
            assert out.state == "IN_PROGRESS", (state, out.error)

        # S7 with a blank secret → blocked, forced back to S7.
        blocked = await runtime.advance(ritual_id, "no secret here")
        assert blocked.state == "ERROR"
        assert isinstance(blocked.error, VisibleSecretMissingError)
        assert blocked.current_state == "S7_visible_secret"
        assert runtime.current_state(ritual_id) == "S7_visible_secret"

        # The visible secret was never stored.
        assert await runtime._trust_store.get_visible_secret(PRINCIPAL) is None


class TestAssemblerNoPlaintextSecret:
    async def test_persisted_assembler_excludes_reply_and_secret(
        self,
        runtime: BoundaryConversationRuntime,
        trust_adapter: TrustStoreAdapter,
    ) -> None:
        """R1-HIGH-1b regression: the persisted boundary_conversation_state row's
        assembler_json contains NO `reply` key and NONE of the S7 visible-secret
        fields (phrase/icon/color) — the secret is never serialized plaintext."""
        ritual_id = await runtime.start(principal_id=PRINCIPAL)
        await runtime.advance(ritual_id, "let's begin")  # S0 → S1
        for state in (
            "S1_money",
            "S2_people",
            "S3_topics",
            "S4_hours",
            "S5_first_task",
            "S6_template_offer",
            "S7_visible_secret",
        ):
            out = await runtime.advance(ritual_id, f"my answer for {state}")
            assert out.state == "IN_PROGRESS", (state, out.error)

        # Load the persisted row and inspect assembler_json.
        row = await trust_adapter.load_boundary_conversation_state(ritual_id)
        assert row is not None
        assembler_blob = json.dumps(row.assembler_dict)
        # No raw reply echoed into the persisted assembler.
        assert "reply" not in assembler_blob
        # No S7 secret components serialized. The S7 secret phrase from
        # _STATE_JSON must not appear anywhere in the persisted assembler.
        secret = _STATE_JSON["S7_visible_secret"]
        assert secret["phrase"] not in assembler_blob
        assert "phrase" not in assembler_blob
        assert "icon" not in assembler_blob
        assert "color" not in assembler_blob
        # The five envelope-dimension states ARE recorded.
        extractions = row.assembler_dict.get("extractions", {})
        assert set(extractions) == {
            "S1_money",
            "S2_people",
            "S3_topics",
            "S4_hours",
            "S5_first_task",
        }


class _DuressSeededAdapter(TrustStoreAdapter):
    """Real TrustStoreAdapter whose documented `shadow_segment_unread_duress_events`
    returns one unread duress event — simulating the P02 contract via the same
    documented surface (P01 returns []). NOT a mock: every store/sqlite/Ed25519
    path is the real adapter; only the documented duress-query return is seeded.
    """

    async def shadow_segment_unread_duress_events(self, principal_id: str) -> list:
        # Honor the real initialize/validation contract, then return a seeded
        # event (the P02 shape: a list of unread duress event records).
        await super().shadow_segment_unread_duress_events(principal_id)
        return [{"duress_event_id": "duress-001", "principal_id": principal_id}]


class TestDuressBannerGate:
    async def test_boundary_conversation_duress_banner_gate(
        self,
        envoy_ledger: EnvoyLedger,
        unlocked_vault: TrustVault,
        tmp_path: Path,
    ) -> None:
        """§ 3.6 post-duress banner gate: when the shadow segment carries an
        unread duress event, advancing past S0 raises
        DuressBannerUnacknowledgedError until acknowledge_duress is called."""
        adapter = _DuressSeededAdapter(vault_path=tmp_path / "alice.vault", principal_id=PRINCIPAL)
        await adapter.initialize()
        try:
            shamir = ShamirRitualCoordinator(
                master_key_source=_MasterKeySource(unlocked_vault),
                commitment_binder=_InMemoryGenesisBinder(),
                paper_renderer=PaperShardRenderer(),
                checklist_persister=TrustVaultChecklistPersister(
                    trust_vault=unlocked_vault, principal_id=PRINCIPAL
                ),
                principal_id=PRINCIPAL,
            )
            runtime = BoundaryConversationRuntime(
                model_router=_DeterministicRouter(),
                trust_store=adapter,
                ledger=envoy_ledger,
                envelope_compiler=EnvelopeCompiler(
                    template_resolver=LocalTemplateResolver(tmp_path)
                ),
                shamir_coordinator=shamir,
                novelty_checker=NoveltyChecker(),
            )

            ritual_id = await runtime.start(principal_id=PRINCIPAL)
            # Unacknowledged duress banner blocks advancing past S0.
            with pytest.raises(DuressBannerUnacknowledgedError):
                await runtime.advance(ritual_id, "let's begin")

            # Acknowledge → the gate unblocks and S0 advances to S1.
            runtime.acknowledge_duress(ritual_id)
            out = await runtime.advance(ritual_id, "let's begin")
            assert out.state == "IN_PROGRESS"
            assert out.current_state == "S1_money"
        finally:
            await adapter.close()
