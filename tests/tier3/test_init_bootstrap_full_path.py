# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 3: ``envoy init`` bootstrap end-to-end (S4i) — durable genesis + trust-anchor.

Source: WS-6 S4i (store-only) — the ``init`` CLI subcommand / Boundary-Conversation
bootstrap. Drives the FULL Boundary Conversation S0→S10 ritual with REAL
infrastructure (real EnvoyLedger Ed25519+chain, real TrustStoreAdapter sqlite,
real EnvelopeCompiler, real ShamirRitualCoordinator SLIP-0039 over a real
TrustVault, real NoveltyChecker, real S4s SessionRouter sqlite store) and then
asserts the two durable artifacts S4i lands:

1. A WRITE-ONCE durable session genesis written to the REAL S4s store — read
   back by a FRESH SessionRouter instance (simulating a new process) per
   `rules/testing.md` § State Persistence Verification.
2. A ``trust-anchor.json`` emitted alongside the Shamir ceremony per
   `specs/independent-verifier.md` § "Trust anchor file format" — asserted
   present + schema-valid (verifiable public material, not a placeholder dict).

Idempotency: a second ``run_first_time_bootstrap`` hits the typed
``VaultAlreadyInitializedError`` path; the durable genesis bytes are unchanged
(read-back assert).

Per `rules/testing.md` Tier 2/3 NO mocking against the store: the S4s store is
real file-backed sqlite, the keychain key is the real persistence path via a
dependency-injected pure-dict backend (NOT the host OS keychain). The ONLY
non-real collaborator is the LLM: per ADR-0006 BYOM the model is the user's
choice, so a deterministic structured-output provider supplies fixed JSON. A
class satisfying the provider duck-type with deterministic output is NOT a mock
of real infra (`rules/testing.md` Tier 2/3 § Protocol Adapters) — it is a BYOM
model returning conforming JSON so the durable-genesis + trust-anchor path is
assertable without an Ollama daemon. The Ollama-real path is the EC-1 gate in
``test_boundary_conversation_full_path.py``; this test targets the S4i durable
writes, which are deterministic.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable
from pathlib import Path

import keyring.errors
import pytest

from envoy.authorship.novelty import NoveltyChecker
from envoy.boundary_conversation import (
    BoundaryConversationInitRuntime,
    BoundaryConversationRuntime,
    VaultAlreadyInitializedError,
    genesis_session_key,
)
from envoy.boundary_conversation.init_runtime import (
    SESSION_STATE_SCHEMA_VERSION,
    TRUST_ANCHOR_SCHEMA_VERSION,
)
from envoy.envelope import EnvelopeCompiler, LocalTemplateResolver
from envoy.ledger import EnvoyLedger
from envoy.runtime.session import SessionRouter
from envoy.shamir import ShamirRitualCoordinator, TrustVaultChecklistPersister
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault

PRINCIPAL = "alice@example"


# ---------------------------------------------------------------------------
# Deterministic BYOM provider + router (mirrors the Tier-2 per-state ledger
# test) — fixed JSON per state so the real ledger/trust/compiler/shamir/store
# path is exercised deterministically. NOT a mock of real infrastructure.
# ---------------------------------------------------------------------------

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

# The scripted free-form replies the init runtime pumps through the BC runtime.
_REPLIES = {state: f"my answer for {state}" for state in _STATE_JSON}


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
        ("tests.tier3.test_init_bootstrap_full_path", "_DeterministicProvider"),
    )
    yield


# ---------------------------------------------------------------------------
# Real-infrastructure fixtures
# ---------------------------------------------------------------------------


class _MemBackend:
    """Pure-dict keyring backend shared across both 'process' router instances.

    Stands in for the OS keychain persisting across process restarts: process A
    generates the session signing key into it; process B (a fresh SessionRouter)
    reloads the SAME key — the cross-process keychain-key lifecycle invariant.
    """

    def __init__(self) -> None:
        self._d: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._d[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._d.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._d:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._d[key]


@pytest.fixture
def keyring_backend() -> _MemBackend:
    return _MemBackend()


@pytest.fixture
def vault_file(tmp_path: Path) -> Path:
    return tmp_path / "init.vault"


@pytest.fixture
async def trust_adapter(vault_file: Path) -> AsyncGenerator[TrustStoreAdapter, None]:
    a = TrustStoreAdapter(vault_path=vault_file, principal_id=PRINCIPAL)
    await a.initialize()
    try:
        yield a
    finally:
        await a.close()


@pytest.fixture
async def session_router(
    vault_file: Path, keyring_backend: _MemBackend
) -> AsyncGenerator[SessionRouter, None]:
    r = SessionRouter(
        vault_path=vault_file, principal_id=PRINCIPAL, keyring_backend=keyring_backend
    )
    await r.open()
    try:
        yield r
    finally:
        await r.close()


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
def init_runtime(
    trust_adapter: TrustStoreAdapter,
    session_router: SessionRouter,
    envoy_ledger: EnvoyLedger,
    unlocked_vault: TrustVault,
    tmp_path: Path,
) -> BoundaryConversationInitRuntime:
    shamir = ShamirRitualCoordinator(
        master_key_source=_MasterKeySource(unlocked_vault),
        commitment_binder=_InMemoryGenesisBinder(),
        paper_renderer=PaperShardRenderer(),
        checklist_persister=TrustVaultChecklistPersister(
            trust_vault=unlocked_vault, principal_id=PRINCIPAL
        ),
        principal_id=PRINCIPAL,
    )
    bc_runtime = BoundaryConversationRuntime(
        model_router=_DeterministicRouter(),
        trust_store=trust_adapter,
        ledger=envoy_ledger,
        envelope_compiler=EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_path)),
        shamir_coordinator=shamir,
        novelty_checker=NoveltyChecker(),
    )
    return BoundaryConversationInitRuntime(
        bc_runtime=bc_runtime,
        session_router=session_router,
        trust_store=trust_adapter,
        trust_anchor_dir=tmp_path / "anchor",
    )


# ---------------------------------------------------------------------------
# AC: init bootstrap writes a durable genesis a fresh process reads back
# ---------------------------------------------------------------------------


class TestInitBootstrapDurableGenesis:
    async def test_bootstrap_writes_genesis_a_fresh_router_reads_back(
        self,
        init_runtime: BoundaryConversationInitRuntime,
        vault_file: Path,
        keyring_backend: _MemBackend,
    ) -> None:
        """The init bootstrap drives S0→S10 and lands a durable genesis; a FRESH
        SessionRouter (new process) over the same vault reads it back."""
        result = await init_runtime.run_first_time_bootstrap(
            principal_id=PRINCIPAL, replies=_REPLIES
        )

        # A parseable EnvelopeConfig came out of S9 sign.
        assert result.envelope_id, "S9 sign MUST produce an envelope_id"
        assert result.genesis_store_key == genesis_session_key(PRINCIPAL)
        assert result.principal_genesis_id.startswith("sha256:")

        # READ-BACK via a SEPARATE router instance (the fresh-process model).
        fresh = SessionRouter(
            vault_path=vault_file, principal_id=PRINCIPAL, keyring_backend=keyring_backend
        )
        await fresh.open()
        try:
            blob = await fresh.load_observed_state(result.genesis_store_key)
        finally:
            await fresh.close()

        assert blob is not None, "fresh process MUST read back the durable genesis"
        genesis = json.loads(blob)
        # The genesis is a real session-state/1.0 SessionObservedState.
        assert genesis["schema_version"] == SESSION_STATE_SCHEMA_VERSION
        assert genesis["session_id"] == result.genesis_session_id
        assert genesis["principal_genesis_id"] == result.principal_genesis_id
        assert genesis["posture_at_session_start"] == "PSEUDO"
        assert genesis["envelope_version_at_session_start"] == 1
        # Genesis session carries the canonical schema shape (empty caches).
        assert genesis["tool_calls_made"] == {}
        assert genesis["reasoning_commits"] == []
        assert genesis["pre_authorized_patterns"] == []

    async def test_bootstrap_seeds_genesis_chain(
        self,
        init_runtime: BoundaryConversationInitRuntime,
        trust_adapter: TrustStoreAdapter,
    ) -> None:
        """The BC ritual seeded a real signed Genesis chain for the principal."""
        await init_runtime.run_first_time_bootstrap(principal_id=PRINCIPAL, replies=_REPLIES)
        chain = await trust_adapter.get_chain(PRINCIPAL)
        assert chain is not None
        assert chain.genesis.agent_id == PRINCIPAL


# ---------------------------------------------------------------------------
# AC: trust-anchor.json emitted + schema-valid (verifiable, not a placeholder)
# ---------------------------------------------------------------------------


class TestInitBootstrapTrustAnchor:
    async def test_trust_anchor_emitted_and_schema_valid(
        self,
        init_runtime: BoundaryConversationInitRuntime,
        trust_adapter: TrustStoreAdapter,
    ) -> None:
        result = await init_runtime.run_first_time_bootstrap(
            principal_id=PRINCIPAL, replies=_REPLIES
        )
        anchor_path = result.trust_anchor_path
        assert anchor_path.exists(), "trust-anchor.json MUST be emitted"
        assert anchor_path.name == "trust-anchor.json"

        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
        # envoy-trust-anchor/1.0 schema per specs/independent-verifier.md.
        assert anchor["schema_version"] == TRUST_ANCHOR_SCHEMA_VERSION
        assert anchor["principal_genesis_id"] == result.principal_genesis_id
        assert anchor["principal_genesis_id"].startswith("sha256:")
        # The pubkey is VERIFIABLE public material — hex-decodable ed25519 key
        # (32 bytes), NOT a placeholder string.
        pubkey_hex = anchor["principal_genesis_pubkey_hex"]
        assert isinstance(pubkey_hex, str) and pubkey_hex
        decoded = bytes.fromhex(pubkey_hex)  # raises if not hex
        assert len(decoded) == 32, "ed25519 public key is 32 bytes"
        # It is the SAME key the trust store holds for the genesis agent.
        assert pubkey_hex == await trust_adapter.genesis_public_key_hex(PRINCIPAL)
        assert anchor["device_attestation_chain"] == []
        assert anchor["anchor_minted_at"]

    async def test_trust_anchor_contains_no_private_key_material(
        self,
        init_runtime: BoundaryConversationInitRuntime,
    ) -> None:
        """Security: the anchor file carries ONLY public verification material —
        never a private key / secret / passphrase (`rules/security.md`)."""
        result = await init_runtime.run_first_time_bootstrap(
            principal_id=PRINCIPAL, replies=_REPLIES
        )
        raw = result.trust_anchor_path.read_text(encoding="utf-8").lower()
        for forbidden in ("private", "secret", "passphrase", "master_key", "seed"):
            assert forbidden not in raw, f"trust-anchor leaked {forbidden!r}"

    async def test_trust_anchor_file_is_owner_only(
        self,
        init_runtime: BoundaryConversationInitRuntime,
    ) -> None:
        """The emitted anchor file is 0o600 (owner read/write only) per
        `rules/trust-plane-security.md` MUST Rule 6 — matches the ledger/vault
        sibling-file discipline."""
        import os
        import stat

        result = await init_runtime.run_first_time_bootstrap(
            principal_id=PRINCIPAL, replies=_REPLIES
        )
        mode = stat.S_IMODE(os.stat(result.trust_anchor_path).st_mode)
        # No group/other bits set.
        assert mode & 0o077 == 0, f"trust-anchor.json mode {oct(mode)} is not owner-only"


# ---------------------------------------------------------------------------
# AC: write-once idempotency — second run is the typed already-initialized path
# ---------------------------------------------------------------------------


class TestInitBootstrapIdempotency:
    async def test_second_run_hits_typed_already_initialized_path(
        self,
        init_runtime: BoundaryConversationInitRuntime,
        session_router: SessionRouter,
    ) -> None:
        first = await init_runtime.run_first_time_bootstrap(
            principal_id=PRINCIPAL, replies=_REPLIES
        )
        # Capture the durable genesis bytes after the first run.
        before = await session_router.load_observed_state(first.genesis_store_key)
        assert before is not None

        # Second run on the initialized vault → typed error, NOT a silent overwrite.
        with pytest.raises(VaultAlreadyInitializedError) as excinfo:
            await init_runtime.run_first_time_bootstrap(principal_id=PRINCIPAL, replies=_REPLIES)
        assert excinfo.value.principal_id == PRINCIPAL
        assert excinfo.value.genesis_store_key == first.genesis_store_key

        # Genesis bytes are UNCHANGED (write-once — never overwritten).
        after = await session_router.load_observed_state(first.genesis_store_key)
        assert after == before, "second init MUST NOT overwrite the durable genesis"
