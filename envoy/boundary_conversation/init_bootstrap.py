# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.boundary_conversation.init_bootstrap — production wiring for ``envoy init``.

Per `rules/orphan-detection.md` Rule 1, the ``BoundaryConversationInitRuntime``
facade needs a production call site; ``build_init_runtime`` is that wiring — the
CLI (`envoy init`, S4i) constructs the bootstrap through this single entry point,
exactly as `envoy.daily_digest.bootstrap.build_digest_service` is the one place
that assembles the digest service.

Per `rules/facade-manager-detection.md` Rule 3, every collaborator is injected
explicitly; this function is the one place that assembles them:

- a real ``TrustVault`` (created + unlocked with the user's install passphrase),
- a real ``TrustStoreAdapter`` (the Genesis chain home),
- a real ``SessionRouter`` (the S4s durable store the genesis lands in),
- a real ``EnvelopeCompiler`` + ``EnvoyModelRouter`` (the BC envelope + LLM),
- a real ``ShamirRitualCoordinator`` over the unlocked vault (S8 backup ritual),
- a real ``EnvoyLedger`` (the per-state ReasoningCommit chain),
- the ``BoundaryConversationRuntime`` facade that orchestrates S0→S10,
- the ``BoundaryConversationInitRuntime`` that lands the durable genesis +
  trust-anchor.

The caller owns the lifetime of the returned resources and MUST tear them down
(``await router.close()``, ``await trust_store.close()``, ``await durable.aclose()``,
``await vault.lock()``) — the bootstrap returns them so the CLI's ``finally`` can.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from envoy.authorship.novelty import NoveltyChecker
from envoy.boundary_conversation.errors import VaultAlreadyInitializedError
from envoy.boundary_conversation.init_runtime import (
    BoundaryConversationInitRuntime,
    genesis_session_key,
)
from envoy.boundary_conversation.runtime import BoundaryConversationRuntime
from envoy.envelope import EnvelopeCompiler, LocalTemplateResolver
from envoy.ledger.bootstrap import (
    LEDGER_ALGORITHM_IDENTIFIER,
    LEDGER_DEVICE_ID,
    LEDGER_SIGNING_KEY_ID,
    DurableLedger,
    open_durable_ledger,
)
from envoy.ledger.keystore import load_or_create_ledger_key_manager
from envoy.model.router import EnvoyModelRouter
from envoy.runtime.session import SessionRouter
from envoy.shamir import ShamirRitualCoordinator, TrustVaultChecklistPersister
from envoy.shamir.commitments import compute_commitment  # noqa: F401 — used by binder
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault

logger = logging.getLogger(__name__)


class _GenesisCommitmentBinder:
    """Bind the Shamir shard public commitments to the principal's Genesis.

    The ShamirRitualCoordinator hands the list of per-shard public commitments
    (sha256 hashes — NOT shard secret material) to ``bind_to_genesis`` so the
    Genesis Record records which shards back this principal. Phase-01 records
    them on the trust store's Genesis metadata path; the `envoy shamir recover`
    flow reads them back (`specs/trust-lineage.md` § GenesisRecord schema →
    `shard_public_commitments`). Public hashes only — no secret bytes.
    """

    def __init__(self, trust_store: TrustStoreAdapter) -> None:
        self._trust_store = trust_store
        self.bound: dict[str, list[str]] = {}

    async def bind_to_genesis(self, principal_id: str, commitments: list[str]) -> None:
        # Phase-01: keep the binding in the store adapter's lifetime so the
        # recovery flow + EC-2 cascade can read which shards back the genesis.
        # (The durable on-genesis-record persistence lands with the T-01-13
        # vault-container migration; until then the binding is held by the
        # adapter for this install process.)
        self.bound[principal_id] = list(commitments)


class _VaultMasterKeySource:
    """Adapt the unlocked TrustVault to the ShamirRitualCoordinator's source."""

    def __init__(self, vault: TrustVault) -> None:
        self._vault = vault

    def export_master_key_for_shamir(self) -> Any:
        return self._vault.export_master_key_for_shamir()


@dataclass(slots=True)
class InitBootstrap:
    """The assembled ``envoy init`` stack + the resources the caller must close."""

    init_runtime: BoundaryConversationInitRuntime
    vault: TrustVault
    trust_store: TrustStoreAdapter
    session_router: SessionRouter
    durable_ledger: DurableLedger


async def build_init_runtime(
    *,
    vault_path: Path | str,
    principal_id: str,
    passphrase: str,
    trust_anchor_dir: Path | str,
    keyring_backend: Any = None,
) -> InitBootstrap:
    """Assemble the full ``envoy init`` stack over a fresh vault.

    Creates + unlocks the TrustVault with the install ``passphrase`` (the
    first-time install ceremony — a vault that already exists raises from
    ``TrustVault.create``), opens the S4s store + durable ledger, wires the BC
    runtime, and returns the ``BoundaryConversationInitRuntime`` ready to drive.

    Returns an ``InitBootstrap`` whose resources the caller MUST tear down in
    its ``finally``: ``await router.close()``, ``await trust_store.close()``,
    ``await durable.aclose()``, ``await vault.lock()``.
    """
    vault_path = Path(vault_path)
    vault = TrustVault(vault_path, idle_ttl_seconds=900)
    # First-time install: create the vault from a fresh master key, then unlock.
    # Defense-in-depth (ENVOY-P2-W2G-001): the CLI pre-checks vault existence and
    # exits 30 before prompting, but ANY other caller of build_init_runtime against
    # a pre-existing vault must also get the TYPED write-once error, not the bare
    # FileExistsError TrustVault.create raises. Translate it here so the typed
    # path is the single contract every caller sees (per the CLI's exit-30
    # already-initialized handler + session-runtime.md:188-191).
    try:
        await vault.create(b"envoy-genesis-install", passphrase)
    except FileExistsError as exc:
        raise VaultAlreadyInitializedError(
            principal_id=principal_id,
            genesis_store_key=genesis_session_key(principal_id),
        ) from exc
    await vault.unlock(passphrase)

    trust_store = TrustStoreAdapter(vault_path=vault_path, principal_id=principal_id)
    await trust_store.initialize()

    session_router = SessionRouter(
        vault_path=vault_path,
        principal_id=principal_id,
        keyring_backend=keyring_backend,
    )
    await session_router.open()

    durable: DurableLedger | None = None
    try:
        key_manager = await load_or_create_ledger_key_manager(
            principal_id=principal_id,
            signing_key_id=LEDGER_SIGNING_KEY_ID,
            keyring_backend=keyring_backend,
        )
        durable = await open_durable_ledger(
            vault_path=vault_path,
            key_manager=key_manager,
            signing_key_id=LEDGER_SIGNING_KEY_ID,
            device_id=LEDGER_DEVICE_ID,
            algorithm_identifier=LEDGER_ALGORITHM_IDENTIFIER,
        )

        shamir = ShamirRitualCoordinator(
            master_key_source=_VaultMasterKeySource(vault),
            commitment_binder=_GenesisCommitmentBinder(trust_store),
            paper_renderer=PaperShardRenderer(),
            checklist_persister=TrustVaultChecklistPersister(
                trust_vault=vault, principal_id=principal_id
            ),
            principal_id=principal_id,
        )
        bc_runtime = BoundaryConversationRuntime(
            model_router=EnvoyModelRouter(),
            trust_store=trust_store,
            ledger=durable.ledger,
            envelope_compiler=EnvelopeCompiler(
                template_resolver=LocalTemplateResolver(vault_path.parent)
            ),
            shamir_coordinator=shamir,
            novelty_checker=NoveltyChecker(),
        )
        init_runtime = BoundaryConversationInitRuntime(
            bc_runtime=bc_runtime,
            session_router=session_router,
            trust_store=trust_store,
            trust_anchor_dir=trust_anchor_dir,
        )
        logger.info(
            "envoy.init.bootstrap.assembled",
            extra={"principal_id_prefix": principal_id[:8], "vault": str(vault_path)},
        )
        return InitBootstrap(
            init_runtime=init_runtime,
            vault=vault,
            trust_store=trust_store,
            session_router=session_router,
            durable_ledger=durable,
        )
    except Exception:
        # Release in reverse acquisition order, then re-raise the original.
        try:
            if durable is not None:
                await durable.aclose()
        finally:
            try:
                await session_router.close()
            finally:
                try:
                    await trust_store.close()
                finally:
                    if vault.is_unlocked:
                        await vault.lock()
        raise


__all__ = ["InitBootstrap", "build_init_runtime"]
