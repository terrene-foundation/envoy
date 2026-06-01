# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.bootstrap — production wiring for DailyDigestService.

Per `rules/orphan-detection.md` Rule 1, the facade needs a production call
site within ≤5 commits; `build_digest_service` is that wiring — the CLI
(`envoy digest …`, T-04-83) and the EC-3 Tier-3 acceptance battery (T-04-84)
both construct the service through this single entry point.

Per `rules/facade-manager-detection.md` Rule 3, every collaborator is
injected explicitly; this function is the one place that assembles them.

Durable ledger backing (EC-4/EC-9): the ledger is opened through
`envoy.ledger.bootstrap.open_durable_ledger` — the file-backed
`SqliteAuditStore`, chain-rehydrated from the persisted tail — over a signing
key persisted in the OS keychain via
`envoy.ledger.keystore.load_or_create_ledger_key_manager`. A fresh process
therefore reopens the SAME on-disk ledger signed by the SAME key, which is the
cross-process property `envoy ledger export` (EC-4) and the independent
verifier (EC-9) require. The aggregator reads via `EnvoyLedger.query()`; the
durable backing additionally makes those writes survive process exit so a
later `envoy ledger export` reader sees them.

This is also the production call site that keeps `open_durable_ledger` +
`load_or_create_ledger_key_manager` out of the orphan set — shards A + B1
landed those primitives standalone (no production caller by design); B3 wires
them here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from envoy.channels.cli import CLIChannelAdapter
from envoy.daily_digest.aggregator import LedgerAggregator
from envoy.daily_digest.backfill import BackfillTracker
from envoy.daily_digest.duress import DuressBannerReader
from envoy.daily_digest.engagement import LowEngagementTracker
from envoy.daily_digest.fanout import PerChannelFanout
from envoy.daily_digest.pause import PauseDisableState
from envoy.daily_digest.renderer import DigestRenderer
from envoy.daily_digest.schedule_registry import ScheduleRegistry
from envoy.daily_digest.scheduler import DigestScheduler
from envoy.daily_digest.service import DailyDigestService
from envoy.ledger.bootstrap import (
    LEDGER_ALGORITHM_IDENTIFIER,
    LEDGER_DEVICE_ID,
    LEDGER_SIGNING_KEY_ID,
    DurableLedger,
    open_durable_ledger,
)
from envoy.ledger.keystore import load_or_create_ledger_key_manager
from envoy.model.router import EnvoyModelRouter
from envoy.trust.store import TrustStoreAdapter

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# The durable-ledger identity (signing key / device / algorithm) is shared with
# the `envoy ledger export` reader — single source of truth in
# `envoy.ledger.bootstrap` (LEDGER_SIGNING_KEY_ID / LEDGER_DEVICE_ID /
# LEDGER_ALGORITHM_IDENTIFIER) so writer and reader open the SAME ledger.


async def build_digest_service(
    *,
    vault_path: Path | str,
    principal_id: str,
    keyring_backend: Any = None,
) -> tuple[DailyDigestService, TrustStoreAdapter, dict[str, CLIChannelAdapter], DurableLedger]:
    """Assemble a fully-wired `DailyDigestService`, its Trust store, the channel
    adapters, and the durable ledger whose lifetime the caller owns.

    Returns `(service, trust_store, channel_adapters, durable_ledger)`. The
    caller owns lifecycle: channel adapters are returned UN-started (the
    delivery path — `today` — starts the adapter it needs around `trigger_now`;
    the lighter state subcommands — pause/resume/schedule/form — never touch the
    terminal). On shutdown: `await service.stop()`, close any started adapters,
    then `await durable_ledger.aclose()` (releases the ledger SQLite pool), then
    `await trust_store.close()`.

    `keyring_backend` is dependency-injectable for tests — a pure-dict backend
    satisfying `envoy.ledger.keystore`'s contract, so coverage exercises the
    real durable-key persistence path without touching the host OS keychain.
    Production passes `None` (the OS-selected backend).
    """
    trust_store = TrustStoreAdapter(vault_path=vault_path, principal_id=principal_id)
    await trust_store.initialize()

    # Partial-construction safety: until the 4-tuple is returned the caller holds
    # no handle, so its `finally` cannot run. Any failure in this window — the
    # fail-loud keychain errors, a durable-open / rehydrate error, or a
    # trust-store write while binding the default channel — MUST release the
    # already-acquired resources here, or the trust-store SQLite handles and
    # (once opened) the durable ledger pool leak with no owner. On the EC-3
    # in-process cron daemon that would accumulate per failed tick. Cleanup
    # re-raises the original error (fail-loud — never swallowed).
    durable: DurableLedger | None = None
    try:
        # Durable signing key (OS keychain) — the SAME key across process
        # restarts, so a fresh `envoy ledger export` reader verifies the
        # persisted entries + re-minted head against it (EC-4 invariant).
        # Fail-loud: never an ephemeral fallback (which would make cross-process
        # verification silently unverifiable).
        key_manager = await load_or_create_ledger_key_manager(
            principal_id=principal_id,
            signing_key_id=LEDGER_SIGNING_KEY_ID,
            keyring_backend=keyring_backend,
        )
        # File-backed, chain-rehydrated ledger over the vault-sibling `.audit.db`.
        # The returned `DurableLedger` owns the SQLite pool — the caller MUST
        # `await durable.aclose()` (threaded through every teardown below).
        durable = await open_durable_ledger(
            vault_path=vault_path,
            key_manager=key_manager,
            signing_key_id=LEDGER_SIGNING_KEY_ID,
            device_id=LEDGER_DEVICE_ID,
            algorithm_identifier=LEDGER_ALGORITHM_IDENTIFIER,
        )
        ledger = durable.ledger

        model_router = EnvoyModelRouter()
        cli_adapter = CLIChannelAdapter()
        channel_adapters = {"cli": cli_adapter}

        schedule_registry = ScheduleRegistry(trust_store=trust_store)
        # Ensure the CLI channel is bound as active+primary when no binding
        # exists yet — the CLI delivers to the terminal, so "cli" is the
        # principal's default channel. Idempotent: an existing binding (e.g. a
        # Tier-3 test that bound bot channels) is left untouched.
        if await schedule_registry.active_channels(principal_id) == ():
            await schedule_registry.set_active_channels(
                principal_id, channel_ids=["cli"], primary="cli"
            )
        pause_state = PauseDisableState(trust_store=trust_store)
        backfill = BackfillTracker(trust_store=trust_store)
        low_engagement = LowEngagementTracker(trust_store=trust_store)
        duress_reader = DuressBannerReader(
            trust_store=trust_store, schedule_registry=schedule_registry
        )
        aggregator = LedgerAggregator(ledger=ledger)
        renderer = DigestRenderer(model_router=model_router, ledger=ledger)
        fanout = PerChannelFanout(channel_adapters=channel_adapters, ledger=ledger)

        service = DailyDigestService(
            scheduler=DigestScheduler(),
            aggregator=aggregator,
            renderer=renderer,
            fanout=fanout,
            backfill=backfill,
            pause_state=pause_state,
            low_engagement=low_engagement,
            duress_reader=duress_reader,
            schedule_registry=schedule_registry,
        )

        logger.info(
            "daily_digest.bootstrap.built",
            extra={
                "principal_id_prefix": principal_id[:8],
                "channels": sorted(channel_adapters.keys()),
            },
        )
        return service, trust_store, channel_adapters, durable
    except Exception:
        # Release in reverse acquisition order. `trust_store.close()` runs even
        # if `durable.aclose()` raises, so a secondary cleanup error never
        # strands the trust store; then re-raise the original failure.
        try:
            if durable is not None:
                await durable.aclose()
        finally:
            await trust_store.close()
        raise


__all__ = ["build_digest_service"]
