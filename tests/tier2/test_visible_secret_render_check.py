"""Tier 2: S7 visible-secret render-check + persistence + Ledger leak guard.

Source: shard 8 § 5.2 + § 5.3 + § 6.1 row "test_visible_secret_render_check" +
`specs/boundary-conversation.md` § Visible secret (PII anti-spoofing).

T-02-44 prescribed coverage gap: visible-secret CRUD round-trip is covered by
`test_envoy_trust_store_boundary.py::TestVisibleSecretRoundTrip`, and the
S9-gate-on-missing-secret is covered by
`test_boundary_conversation_per_state_ledger_entries.py::test_boundary_conversation_visible_secret_missing_raises`.
This dedicated file ADDS the missing contract-edge coverage:

1. Runtime-end-to-end: driving the FULL runtime through S7 actually persists
   the icon/color/phrase via ``trust_store.set_visible_secret`` (the runtime
   wiring under `_handle_visible_secret`) — closes the wiring gap that the
   adapter-direct test cannot catch.
2. Next-session render: after S7 completes and the runtime is dropped, a fresh
   runtime (or any caller using the same TrustStoreAdapter) MUST be able to
   read back the visible secret via ``get_visible_secret`` — this is the
   render contract the duress modal + Grant-Moment surfaces depend on.
3. **Security invariant — phrase NEVER in Ledger entries.** The R1-HIGH-1b
   regression (commit 883e6ba "stop persisting raw reply + S7 secret in
   assembler") established the contract that the phrase never lands in the
   Ledger row content; this test pins it structurally so a future refactor
   cannot re-introduce the leak.

NOT mocking real infrastructure — real TrustStoreAdapter (sqlite + Ed25519) +
real EnvoyLedger + real EnvelopeCompiler + real Shamir + real Novelty. The
BYOM provider is deterministic-JSON per ADR-0006 (NOT a mock of real infra).
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
    VisibleSecretMissingError,
)
from envoy.envelope import EnvelopeCompiler, LocalTemplateResolver
from envoy.ledger import EnvoyLedger
from envoy.shamir import ShamirRitualCoordinator, TrustVaultChecklistPersister
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.types import VisibleSecret
from envoy.trust.vault import TrustVault


PRINCIPAL = "alice@example"
_ENVELOPE_KEY = "_envoy_envelope_v1"

# Canonical per-state extractions — identical to the schedule pinned in
# test_boundary_conversation_per_state_ledger_entries.py.
_VISIBLE_SECRET_PHRASE = "quiet harbor at dawn"
_STATE_JSON: dict[str, dict] = {
    "S1_money": {"monthly_ceiling_microdollars": 250_000_000},
    "S2_people": {"blocked_contacts": ["ex@x.com"]},
    "S3_topics": {"blocked_topic_rules": ["no medical advice", "no political endorsements"]},
    "S4_hours": {"operating_hours": {"days": ["mon", "tue"], "tz": "UTC"}},
    "S5_first_task": {"first_task_intent": {"goal": "summarize my unread newsletters"}},
    "S6_template_offer": {"use_template": False, "template_id": ""},
    "S7_visible_secret": {"icon": "anchor", "color": "#0b6e4f", "phrase": _VISIBLE_SECRET_PHRASE},
    "S8_shamir": {"threshold": 3, "total_shards": 5, "distribution_mode": "default"},
    "S9_review_sign": {"plain_language_summary": "Your boundaries are set.", "signed": True},
}


class _DeterministicProvider:
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
        ("tests.tier2.test_visible_secret_render_check", "_DeterministicProvider"),
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


def _make_runtime(
    *,
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


async def _drive_to_state(runtime: BoundaryConversationRuntime, target_state: str) -> str:
    """Drive a fresh conversation to ``target_state`` along the forward spine."""
    ritual_id = await runtime.start(principal_id=PRINCIPAL)
    if target_state == "S0_greet":
        return ritual_id
    await runtime.advance(ritual_id, "let's begin")
    forward = [
        "S1_money",
        "S2_people",
        "S3_topics",
        "S4_hours",
        "S5_first_task",
        "S6_template_offer",
        "S7_visible_secret",
    ]
    for state in forward:
        if runtime.current_state(ritual_id) == target_state:
            return ritual_id
        out = await runtime.advance(ritual_id, f"answer-{state}")
        assert out.state == "IN_PROGRESS", (state, out.error)
    return ritual_id


class TestRuntimeS7PersistsViaTrustStore:
    async def test_advance_through_S7_persists_secret_to_adapter(
        self,
        trust_adapter: TrustStoreAdapter,
        envoy_ledger: EnvoyLedger,
        unlocked_vault: TrustVault,
        tmp_path: Path,
    ) -> None:
        """Driving the runtime through S7 with the deterministic provider
        MUST cause ``set_visible_secret`` to land the icon/color/phrase in the
        adapter's visible_secret table — closes the wiring gap that direct
        adapter-CRUD tests cannot catch (e.g. a refactor that drops the
        ``_handle_visible_secret`` call site)."""
        runtime = _make_runtime(
            trust_adapter=trust_adapter,
            envoy_ledger=envoy_ledger,
            unlocked_vault=unlocked_vault,
            tmp_path=tmp_path,
        )
        # Drive past S7 (need to ADVANCE through S7 itself to fire the handler).
        ritual_id = await _drive_to_state(runtime, "S7_visible_secret")
        out = await runtime.advance(ritual_id, "anchor teal 'quiet harbor at dawn'")
        # S7 advances to S8_shamir (not PAUSED yet; PAUSED happens AT S8 advance).
        assert out.state == "IN_PROGRESS"
        assert out.current_state == "S8_shamir"

        # Read back via the SAME adapter — the runtime wired the persistence.
        got = await trust_adapter.get_visible_secret(PRINCIPAL)
        assert got == VisibleSecret(icon="anchor", color="#0b6e4f", phrase=_VISIBLE_SECRET_PHRASE)


class TestVisibleSecretSurvivesRuntimeRestart:
    async def test_next_session_render_reads_persisted_secret(
        self,
        trust_adapter: TrustStoreAdapter,
        envoy_ledger: EnvoyLedger,
        unlocked_vault: TrustVault,
        tmp_path: Path,
    ) -> None:
        """After S7 completes and the runtime is dropped, the visible secret is
        persisted in the adapter (the next-session render contract). A fresh
        runtime constructed against the SAME adapter sees the same secret via
        ``get_visible_secret`` — this is what the duress modal + Grant-Moment
        surfaces depend on for next-session anti-spoofing display."""
        runtime_a = _make_runtime(
            trust_adapter=trust_adapter,
            envoy_ledger=envoy_ledger,
            unlocked_vault=unlocked_vault,
            tmp_path=tmp_path,
        )
        ritual_id = await _drive_to_state(runtime_a, "S7_visible_secret")
        await runtime_a.advance(ritual_id, "anchor teal 'quiet harbor at dawn'")
        del runtime_a  # drop the in-memory runtime; the adapter persists.

        # A different runtime instance — modeling a new process / next session.
        runtime_b = _make_runtime(  # noqa: F841 — constructed for symmetry with prod path
            trust_adapter=trust_adapter,
            envoy_ledger=envoy_ledger,
            unlocked_vault=unlocked_vault,
            tmp_path=tmp_path,
        )
        # Render-check: ANY caller using the adapter (the CLI's session greeter
        # at next launch) reads the secret to display before the user types.
        got = await trust_adapter.get_visible_secret(PRINCIPAL)
        assert got is not None
        assert got.icon == "anchor"
        assert got.color == "#0b6e4f"
        assert got.phrase == _VISIBLE_SECRET_PHRASE


class TestVisibleSecretPhraseNeverInLedger:
    async def test_phrase_never_appears_in_any_ledger_entry_content(
        self,
        trust_adapter: TrustStoreAdapter,
        envoy_ledger: EnvoyLedger,
        audit_store: InMemoryAuditStore,
        unlocked_vault: TrustVault,
        tmp_path: Path,
    ) -> None:
        """Security invariant — pin per `883e6ba fix(phase-01-T-02-41): stop
        persisting raw reply + S7 secret in assembler` (R1-HIGH-1b).

        The visible-secret phrase is an anti-spoofing secret (PII per § 5.3).
        It MUST NEVER appear in any Ledger entry's content payload — neither
        as a raw reply, nor inside the assembler dict, nor in any session-
        boundary or posture_change entry. A future refactor that re-inlines
        the phrase into the Ledger MUST trip this assertion.
        """
        runtime = _make_runtime(
            trust_adapter=trust_adapter,
            envoy_ledger=envoy_ledger,
            unlocked_vault=unlocked_vault,
            tmp_path=tmp_path,
        )
        # Drive through S7 so the phrase is in-flight via the runtime path.
        ritual_id = await _drive_to_state(runtime, "S7_visible_secret")
        await runtime.advance(ritual_id, "the phrase 'quiet harbor at dawn'")
        # Advance through S8 (PAUSED), clear, and complete to maximize Ledger
        # coverage — Reasoning + session_boundary + posture_change all flush.
        paused = await runtime.advance(ritual_id, "default 3-of-5")
        assert paused.state == "PAUSED"
        await runtime.resume_from_shamir(ritual_id)
        done = await runtime.advance(ritual_id, "yes confirm and sign")
        assert done.state == "COMPLETE"

        # Sweep every Ledger entry's content for the phrase. Plain-substring
        # check on the JSON-serialised content — if the phrase appears at any
        # depth in any nested structure, the JSON dump will surface it.
        events = await audit_store.query(AuditFilter(limit=1_000_000))
        envelopes = [
            e.metadata[_ENVELOPE_KEY] for e in events if _ENVELOPE_KEY in (e.metadata or {})
        ]
        for env in envelopes:
            content_json = json.dumps(env.get("content", {}), default=str)
            assert _VISIBLE_SECRET_PHRASE not in content_json, (
                f"R1-HIGH-1b regression: phrase {_VISIBLE_SECRET_PHRASE!r} "
                f"leaked into Ledger entry of type {env.get('type')!r}: "
                f"{content_json[:300]}"
            )


class TestS9GateOnMissingSecret:
    async def test_S9_advance_raises_VisibleSecretMissingError_if_unset(
        self,
        trust_adapter: TrustStoreAdapter,
        envoy_ledger: EnvoyLedger,
        unlocked_vault: TrustVault,
        tmp_path: Path,
    ) -> None:
        """S9 hard-gates on `get_visible_secret(principal_id) is None`. The
        runtime's response is to set ``current_state = S7`` and raise
        ``VisibleSecretMissingError`` so the caller re-prompts S7. The S9 gate
        cannot be bypassed by skipping S7."""
        # Manually drive the runtime to S9_review_sign WITHOUT going through
        # S7 (so the visible secret is never set). Simplest path: drive to S7,
        # then mutate current_state directly to S9 — modelling a state-machine
        # corruption that the gate must catch.
        runtime = _make_runtime(
            trust_adapter=trust_adapter,
            envoy_ledger=envoy_ledger,
            unlocked_vault=unlocked_vault,
            tmp_path=tmp_path,
        )
        ritual_id = await _drive_to_state(runtime, "S7_visible_secret")
        # State-machine integrity: jump current_state to S9, simulating a
        # corruption that the runtime's gate must defensively catch.
        runtime._current_state[ritual_id] = "S9_review_sign"

        with pytest.raises(VisibleSecretMissingError):
            await runtime._handle_review_sign(ritual_id, {"signed": True})
        # The gate also corrects current_state back to S7.
        assert runtime.current_state(ritual_id) == "S7_visible_secret"
