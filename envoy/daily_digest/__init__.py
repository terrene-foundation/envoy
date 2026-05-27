# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest — morning ritual delivering 2-min action/refusal/spend summary.

Per `specs/daily-digest.md` § Purpose. Wave-4 Phase-01 surface; closes EC-3
(digest fires 7 consecutive days across configured channels).

Public surface
--------------

- :class:`DailyDigestService` — facade owning scheduler lifecycle + dispatch.
- :class:`DigestScheduler` — apscheduler-backed cron registration.
- :class:`DigestPayload` (+ :class:`DigestSummary`, :class:`DuressBanner`) —
  the 11-field schema/1.0 dataclass set per spec § Schema.
- :data:`DIGEST_SCHEMA_VERSION` — pinned schema literal.
- Error taxonomy (5 types) — :class:`DailyDigestError` base + 5 subclasses
  per spec § Error taxonomy.

Aggregator / renderer / fanout / backfill / pause-state / engagement-tracker /
duress-reader land in sibling modules (T-04-81 → T-04-83 of this PR) and are
imported lazily by the facade.

Phase-01 status per orphan-detection.md Rule 1: this package's hot-path
production call site is the CLI subcommand set (T-04-83) AND the Tier-2
wiring tests (T-04-84), both landing in this same PR.
"""

from __future__ import annotations

from envoy.daily_digest.aggregator import LedgerAggregator
from envoy.daily_digest.backfill import BackfillTracker
from envoy.daily_digest.bootstrap import build_digest_service
from envoy.daily_digest.duress import DuressBannerReader
from envoy.daily_digest.engagement import LowEngagementTracker
from envoy.daily_digest.errors import (
    DailyDigestError,
    DigestDeliveryFailedError,
    DigestSkippedTooLongWarning,
    DuressBannerSuppressedError,
    LowEngagementFallbackTriggered,
    RedactedFieldRenderError,
)
from envoy.daily_digest.fanout import PerChannelFanout
from envoy.daily_digest.pause import PauseDisableState
from envoy.daily_digest.payload import (
    DIGEST_SCHEMA_VERSION,
    DigestForm,
    DigestPayload,
    DigestSummary,
    DuressBanner,
)
from envoy.daily_digest.renderer import DigestRenderer
from envoy.daily_digest.schedule_registry import ScheduleRegistry, ScheduleRow
from envoy.daily_digest.scheduler import DigestCallback, DigestScheduler
from envoy.daily_digest.service import DailyDigestService

__all__ = [
    # Facade
    "DailyDigestService",
    # Scheduler
    "DigestCallback",
    "DigestScheduler",
    # Content layer (T-04-81)
    "LedgerAggregator",
    "DigestRenderer",
    # State + fan-out (T-04-82)
    "PerChannelFanout",
    "BackfillTracker",
    "PauseDisableState",
    "LowEngagementTracker",
    "ScheduleRegistry",
    "ScheduleRow",
    # Duress + wiring (T-04-83)
    "DuressBannerReader",
    "build_digest_service",
    # Payload
    "DIGEST_SCHEMA_VERSION",
    "DigestForm",
    "DigestPayload",
    "DigestSummary",
    "DuressBanner",
    # Errors (5 typed + base per spec § Error taxonomy)
    "DailyDigestError",
    "DigestDeliveryFailedError",
    "DuressBannerSuppressedError",
    "RedactedFieldRenderError",
    "LowEngagementFallbackTriggered",
    "DigestSkippedTooLongWarning",
]
