# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.bootstrap — production wiring for DailyDigestService.

Per `rules/orphan-detection.md` Rule 1, the facade needs a production call
site within ≤5 commits; `build_digest_service` is that wiring — the CLI
(`envoy digest …`, T-04-83) and the EC-3 Tier-3 acceptance battery (T-04-84)
both construct the service through this single entry point.

Per `rules/facade-manager-detection.md` Rule 3, every collaborator is
injected explicitly; this function is the one place that assembles them.

Phase-01 ledger backing: `InMemoryAuditStore` + `InMemoryKeyManager`,
matching the project-wide Phase-01 pattern (every Tier-2 test uses
`InMemoryAuditStore` — file-backed `SqliteAuditStore` persistence is the
T-01-21 follow-up per `tests/tier2/test_envoy_ledger_wiring.py:19`). The
aggregator reads via `EnvoyLedger.query()` (not `verify_chain()`), so the
process-local signing key does not affect digest aggregation. Cross-process
ledger persistence arrives with T-01-21; the digest wiring is unchanged when
it does (only the audit-store backend swaps).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

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
from envoy.ledger.facade import EnvoyLedger
from envoy.model.router import EnvoyModelRouter
from envoy.trust.store import TrustStoreAdapter

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# Phase-01 3-key algorithm identifier (sig + hash + shamir) per
# specs/trust-lineage.md L24 — the wire form every EnvoyLedger entry carries.
_PHASE01_ALGO = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
_DIGEST_DEVICE_ID = "envoy-digest-device"
_DIGEST_SIGNING_KEY = "envoy-digest-signing-key"


async def build_digest_service(
    *,
    vault_path: Path | str,
    principal_id: str,
) -> tuple[DailyDigestService, TrustStoreAdapter, dict[str, CLIChannelAdapter]]:
    """Assemble a fully-wired `DailyDigestService` plus its Trust store.

    Returns `(service, trust_store, channel_adapters)`. The caller owns
    lifecycle: channel adapters are returned UN-started (the delivery path —
    `today` — starts the adapter it needs around `trigger_now`; the lighter
    state subcommands — pause/resume/schedule — never touch the terminal).
    On shutdown: `await service.stop()`, close any started adapters, then
    `await trust_store.close()`.
    """
    trust_store = TrustStoreAdapter(vault_path=vault_path, principal_id=principal_id)
    await trust_store.initialize()

    key_manager = InMemoryKeyManager()  # type: ignore[no-untyped-call]  # kailash ctor is untyped
    await key_manager.generate_keypair(_DIGEST_SIGNING_KEY)
    ledger = EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=key_manager,
        signing_key_id=_DIGEST_SIGNING_KEY,
        device_id=_DIGEST_DEVICE_ID,
        algorithm_identifier=_PHASE01_ALGO,
    )

    model_router = EnvoyModelRouter()
    cli_adapter = CLIChannelAdapter()
    channel_adapters = {"cli": cli_adapter}

    schedule_registry = ScheduleRegistry(trust_store=trust_store)
    # Ensure the CLI channel is bound as active+primary when no binding exists
    # yet — the CLI delivers to the terminal, so "cli" is the principal's
    # default channel. Idempotent: an existing binding (e.g. a Tier-3 test
    # that bound bot channels) is left untouched.
    if await schedule_registry.active_channels(principal_id) == ():
        await schedule_registry.set_active_channels(
            principal_id, channel_ids=["cli"], primary="cli"
        )
    pause_state = PauseDisableState(trust_store=trust_store)
    backfill = BackfillTracker(trust_store=trust_store)
    low_engagement = LowEngagementTracker(trust_store=trust_store)
    duress_reader = DuressBannerReader(trust_store=trust_store, schedule_registry=schedule_registry)
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
    return service, trust_store, channel_adapters


__all__ = ["build_digest_service"]
