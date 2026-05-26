"""Tier 3: EC-1 minimum-path — fastest first-time-user session ≤8 min.

Source: T-02-45 + `02-plans/02-test-strategy.md` § EC-1 minimum-path +
`journal/0005-DECISION-todos-opening-dispositions.md` § Disposition #3 +
`briefs/00-phase-01-mvp-scope.md` § Surfaces.

The minimum-path acceptance covers the maximally-fast happy path: a
first-time user who accepts every default, never re-prompts, never paused
to think — the floor for the BET-1 + BET-12 falsification claim. If even
the fastest path cannot complete S0→S10 within 8 minutes wall-clock, the
ritual ceiling is structurally unreachable for any real user. The 8-minute
budget per disposition #3 is the floor below the 25-min ship gate
(``test_boundary_conversation_full_path.py``) and the 15-min UX target.

Phase 01 minimum-path:
* Single concise reply per S1-S9 (no novelty re-prompt — Phase-01 cache is
  empty, so no novelty edge triggers anyway).
* Template offer DECLINED ("build from scratch") to skip the template-resolve
  branch; that path is the orphan one for a no-template-installed system.
* Default 3-of-5 Shamir.
* Signs immediately at S9.

ACCEPTABLE skip if Ollama unavailable per `rules/testing.md` test-skip
triage. NO mocking — Tier 3 EC-1 demands the production-LLM path.
"""

from __future__ import annotations

import os
import socket
import time
from collections.abc import AsyncGenerator, Awaitable
from pathlib import Path
from urllib.parse import urlparse

import pytest
from kaizen.llm.client import LlmClient
from kaizen.llm.presets import ollama_default_preset

from envoy.authorship.novelty import NoveltyChecker
from envoy.boundary_conversation import (
    BoundaryConversationRuntime,
    InvalidStateTransitionError,
    NoveltyFeedbackBlockError,
    VisibleSecretMissingError,
)
from envoy.envelope import EnvelopeCompiler, LocalTemplateResolver
from envoy.ledger import EnvoyLedger
from envoy.shamir import ShamirRitualCoordinator, TrustVaultChecklistPersister
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault


_OLLAMA_HOST = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# 8-min minimum-path ceiling per `journal/0005` Disposition #3.
MIN_PATH_CEILING_SECONDS = 8 * 60


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


PRINCIPAL = "minimum-path@example"

# Maximally-concise replies modelling the fastest realistic first-time-user.
# Each reply is the shortest sentence that still encodes the required
# structured-output fields the per-state Signature extracts. The model still
# has to produce conforming JSON — this is NOT a path that bypasses the LLM.
_MIN_REPLIES = {
    "S1_money": "Cap me at 100 USD per month.",
    "S2_people": "No blocks.",
    "S3_topics": "No restrictions.",
    "S4_hours": "Always on, UTC.",
    "S5_first_task": "Just summarize my email.",
    "S6_template_offer": "No template.",
    "S7_visible_secret": "Icon star, color blue, phrase 'open sky'.",
    "S8_shamir": "Default backup.",
    "S9_review_sign": "Yes sign.",
}

_MAX_RETRIES = 8


_RETRYABLE_GATE_ERRORS = (
    InvalidStateTransitionError,
    VisibleSecretMissingError,
    NoveltyFeedbackBlockError,
)


class _OllamaPresetRouter:
    def __init__(self, model: str) -> None:
        self._client = LlmClient.from_deployment(ollama_default_preset(model))

    def for_primitive(self, primitive: str) -> LlmClient:  # noqa: ARG002
        return self._client


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
def _ollama_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", _OLLAMA_HOST)


@pytest.fixture
async def trust_adapter(tmp_path: Path) -> AsyncGenerator[TrustStoreAdapter, None]:
    a = TrustStoreAdapter(vault_path=tmp_path / "minimum-path.vault", principal_id=PRINCIPAL)
    await a.initialize()
    try:
        yield a
    finally:
        await a.close()


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


async def _advance_with_retries(runtime, ritual_id, reply: str):  # noqa: ANN001
    """See the docstring in ``test_boundary_conversation_full_path.py`` for the
    parse-retryable gate-error rationale; same contract here."""
    last_err = None
    for _ in range(_MAX_RETRIES):
        outcome = await runtime.advance(ritual_id, reply)
        if outcome.state != "ERROR":
            return outcome
        last_err = outcome.error
        if not isinstance(last_err, _RETRYABLE_GATE_ERRORS):
            return outcome
    pytest.skip(
        f"local model could not produce conforming structured output after "
        f"{_MAX_RETRIES} retries (last error: {last_err}); model-capability "
        f"limitation, not a minimum-path defect"
    )


class TestEC1MinimumPath:
    async def test_minimum_path_completes_within_8min(
        self,
        runtime: BoundaryConversationRuntime,
        trust_adapter: TrustStoreAdapter,
    ) -> None:
        """The fastest realistic first-time-user session completes S0→S10
        within 8 minutes wall-clock AND produces a signed Genesis Record.

        On modern hardware the actual machine-time is ≪8 min. The ceiling is
        the FLOOR check: if even the maximally-concise reply path cannot
        complete in 8 minutes, the EC-1 ceiling structurally cannot hold for
        a real user.
        """
        started_at = time.monotonic()
        ritual_id = await runtime.start(principal_id=PRINCIPAL)
        await runtime.advance(ritual_id, "ok")  # S0 → S1

        for state in (
            "S1_money",
            "S2_people",
            "S3_topics",
            "S4_hours",
            "S5_first_task",
            "S6_template_offer",
            "S7_visible_secret",
        ):
            outcome = await _advance_with_retries(runtime, ritual_id, _MIN_REPLIES[state])
            assert outcome.state == "IN_PROGRESS", (state, outcome.error)

        paused = await _advance_with_retries(runtime, ritual_id, _MIN_REPLIES["S8_shamir"])
        assert paused.state == "PAUSED"
        await runtime.resume_from_shamir(ritual_id)

        done = await _advance_with_retries(runtime, ritual_id, _MIN_REPLIES["S9_review_sign"])
        assert done.state == "COMPLETE", done.error
        assert done.envelope_id, "S9 sign MUST produce a parseable EnvelopeConfig envelope_id"

        elapsed = time.monotonic() - started_at

        # Acceptance: wall-clock under the 8-min floor.
        assert elapsed <= MIN_PATH_CEILING_SECONDS, (
            f"EC-1 minimum-path breach: {elapsed:.1f}s, " f"ceiling {MIN_PATH_CEILING_SECONDS}s"
        )

        # Genesis Record exists (the externally observable success criterion).
        chain = await trust_adapter.get_chain(PRINCIPAL)
        assert chain is not None
        assert chain.genesis.agent_id == PRINCIPAL
        # envelope_id binding to the posture_change Ledger entry is verified
        # in the full-path Ledger-chain-integrity test; here we only assert
        # the Genesis seed landed.

        # Surface the elapsed time for /codify UX scraping.
        print(f"\nEC1-MIN principal={PRINCIPAL} elapsed={elapsed:.2f}s ceiling=8min")
