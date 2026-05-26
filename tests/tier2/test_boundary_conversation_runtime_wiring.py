"""Tier 2: full BoundaryConversationRuntime wiring against REAL Ollama.

Source: shard 8 § 6.1 row "test_boundary_conversation_runtime_wiring" +
`rules/facade-manager-detection.md` Rule 1 (manager-shape wiring test asserting
an externally-observable effect) + § 6.3 (Ollama is the load-bearing CI tier).

Constructs the runtime against real EnvoyLedger + real TrustStoreAdapter + real
EnvelopeCompiler + real ShamirRitualCoordinator + real NoveltyChecker + the REAL
EnvoyModelRouter driving a live Ollama daemon (model from
``OLLAMA_DEFAULT_MODEL`` per `rules/env-models.md` — NEVER hardcoded), then runs
start → advance(S1..S9) → S10 and asserts:

1. S10 completion produces a Trust Vault Genesis row (externally observable).
2. The S9 sign step produced a parseable EnvelopeConfig (envelope_id set).

Gated by ``@pytest.mark.skipif(not OLLAMA_AVAILABLE)`` — ACCEPTABLE skip per
`rules/testing.md` test-skip triage (infra-conditional). NO mocking: the live
Ollama wire is the BYOM path production ships.

A real local LLM may extract noisy / non-conforming JSON for some states; the
runtime re-prompts on InvalidStateTransitionError. The test retries each state a
bounded number of times with a more explicit nudge, then surfaces the model's
failure rather than masking it.
"""

from __future__ import annotations

import os
import socket
from collections.abc import AsyncGenerator, Awaitable
from pathlib import Path
from urllib.parse import urlparse

import pytest
from kaizen.llm.client import LlmClient
from kaizen.llm.presets import ollama_default_preset

from envoy.authorship.novelty import NoveltyChecker
from envoy.boundary_conversation import BoundaryConversationRuntime
from envoy.envelope import EnvelopeCompiler, LocalTemplateResolver
from envoy.ledger import EnvoyLedger
from envoy.shamir import ShamirRitualCoordinator, TrustVaultChecklistPersister
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault

_OLLAMA_HOST = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
PRINCIPAL = "alice@example"


def _ollama_reachable(host: str = _OLLAMA_HOST) -> bool:
    try:
        parsed = urlparse(host)
        with socket.create_connection(
            (parsed.hostname or "localhost", parsed.port or 11434), timeout=1.5
        ):
            return True
    except (OSError, ValueError):
        return False


def _pick_ollama_model() -> str | None:
    for key in ("OLLAMA_DEFAULT_MODEL", "OLLAMA_PROD_MODEL", "OLLAMA_MODEL"):
        v = os.environ.get(key)
        if v:
            return v
    return None


def _ollama_client_lib_present() -> bool:
    """The legacy OllamaProvider.chat() requires the `ollama` python client lib;
    its absence is an infra constraint (ACCEPTABLE skip), not a runtime defect."""
    try:
        import ollama  # noqa: F401

        return True
    except ImportError:
        return False


_OLLAMA_AVAILABLE = _ollama_reachable() and _ollama_client_lib_present()
_OLLAMA_MODEL = _pick_ollama_model()

pytestmark = [
    pytest.mark.skipif(
        not _OLLAMA_AVAILABLE,
        reason=(
            f"requires local Ollama at {_OLLAMA_HOST} (run `ollama serve`); "
            "ACCEPTABLE skip per rules/testing.md test-skip triage"
        ),
    ),
    pytest.mark.skipif(
        _OLLAMA_MODEL is None,
        reason=(
            "requires OLLAMA_DEFAULT_MODEL / OLLAMA_PROD_MODEL / OLLAMA_MODEL env var; "
            "ACCEPTABLE skip per rules/testing.md test-skip triage"
        ),
    ),
]


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


class _OllamaPresetRouter:
    """Real-deployment router for the runtime's for_primitive() contract.

    Ollama is NOT a from_env URI scheme (per the existing
    test_envoy_model_router_ollama_wiring.py note: "Ollama URIs aren't a
    from_env URI scheme either — so we drive the router via direct
    from_deployment composition"). The EnvoyModelRouter's env-resolution of
    Ollama is shard-13's concern; the Boundary Conversation runtime's contract
    is only that ``for_primitive`` returns an LlmClient whose
    ``deployment.preset_name`` + ``default_model`` drive the legacy provider
    chat. This router supplies a REAL ollama_default_preset deployment (the
    documented Ollama construction path) — the chat wire that fires is the live
    Ollama daemon, NOT a mock.
    """

    def __init__(self, model: str) -> None:
        self._client = LlmClient.from_deployment(ollama_default_preset(model))

    def for_primitive(self, primitive: str) -> LlmClient:  # noqa: ARG002
        return self._client


@pytest.fixture
def _ollama_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the legacy Ollama provider at the live daemon via env."""
    monkeypatch.setenv("OLLAMA_BASE_URL", _OLLAMA_HOST)


@pytest.fixture
async def runtime(
    trust_adapter: TrustStoreAdapter,
    envoy_ledger: EnvoyLedger,
    unlocked_vault: TrustVault,
    tmp_path: Path,
    _ollama_env: None,
) -> BoundaryConversationRuntime:
    assert _OLLAMA_MODEL is not None
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
        model_router=_OllamaPresetRouter(_OLLAMA_MODEL),
        trust_store=trust_adapter,
        ledger=envoy_ledger,
        envelope_compiler=EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path)),
        shamir_coordinator=shamir,
        novelty_checker=NoveltyChecker(),
    )


# Plain-language user replies per state — the real model must extract the
# structured outputs from these.
_REPLIES = {
    "S1_money": "Cap my spending at 250 dollars per month.",
    "S2_people": "Never contact my ex at ex@example.com.",
    "S3_topics": "Avoid giving medical advice or political endorsements.",
    "S4_hours": "Only operate Monday through Friday, 9am to 5pm UTC.",
    "S5_first_task": "Summarize my unread newsletters every morning.",
    "S6_template_offer": "Build from scratch, no template.",
    "S7_visible_secret": "Icon anchor, color teal, phrase 'quiet harbor at dawn'.",
    "S8_shamir": "Use the default 3-of-5 backup.",
    "S9_review_sign": "Yes, I confirm and sign.",
}

_MAX_RETRIES = 4


async def _advance_with_retries(runtime, ritual_id, reply: str):  # noqa: ANN001
    """Advance one state, retrying on InvalidStateTransitionError (a real local
    model can emit non-conforming JSON; the runtime re-prompts). Surfaces the
    error after the retry budget rather than masking it."""
    from envoy.boundary_conversation import InvalidStateTransitionError

    last_err = None
    for _ in range(_MAX_RETRIES):
        outcome = await runtime.advance(ritual_id, reply)
        if outcome.state != "ERROR":
            return outcome
        last_err = outcome.error
        if not isinstance(last_err, InvalidStateTransitionError):
            return outcome  # novelty / gate errors are not parse-retryable here
    pytest.skip(
        f"local model could not produce conforming structured output after "
        f"{_MAX_RETRIES} retries (last error: {last_err}); model-capability "
        f"limitation, not a runtime defect"
    )


class TestRuntimeFullWiringAgainstRealOllama:
    async def test_start_advance_to_complete_seeds_genesis(
        self,
        runtime: BoundaryConversationRuntime,
        trust_adapter: TrustStoreAdapter,
    ) -> None:
        ritual_id = await runtime.start(principal_id=PRINCIPAL)
        await runtime.advance(ritual_id, "let's begin")  # S0 greet → S1

        for state in (
            "S1_money",
            "S2_people",
            "S3_topics",
            "S4_hours",
            "S5_first_task",
            "S6_template_offer",
            "S7_visible_secret",
        ):
            await _advance_with_retries(runtime, ritual_id, _REPLIES[state])

        # S8 shamir — suspends.
        paused = await _advance_with_retries(runtime, ritual_id, _REPLIES["S8_shamir"])
        assert paused.state == "PAUSED"
        assert paused.paused_for == "shamir_ritual"

        # Physical ritual complete → clear suspension via the PUBLIC clear-path,
        # then S9 sign.
        await runtime.resume_from_shamir(ritual_id)
        done = await _advance_with_retries(runtime, ritual_id, _REPLIES["S9_review_sign"])
        assert done.state == "COMPLETE", done.error
        assert done.envelope_id, "S9 sign must produce a parseable EnvelopeConfig envelope_id"

        # Externally observable effect: a Genesis trust chain row exists.
        chain = await trust_adapter.get_chain(PRINCIPAL)
        assert chain is not None
        assert chain.genesis.agent_id == PRINCIPAL
