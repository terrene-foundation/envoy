# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.aggregator — LedgerAggregator.

Per `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
§ 3 step 2 + § 5.1 — given a `(principal_id, window_start, window_end)`,
queries `EnvoyLedger.query(filter, since, until)` for each digest summary
section and returns a `DigestSummary`.

Section → entry-type mapping (shard 11 § 5.1, lines 530-534):

- ``actions``        ← ``PhaseBRecord`` (post-execution outcomes)
- ``refusals``       ← ``posture_change`` (decision=deny) OR ``system_error``
                       (refusal-class fault codes)
- ``spend``          ← Phase-01: summed from ``PhaseBRecord`` content
                       ``cost_microdollars``; ``monthly_ceiling_microdollars``
                       from the latest entry carrying it. Live budget counter
                       is shard-12 / Phase-02 — until then the aggregator reads
                       spend from ledger content (real aggregation, not a stub).
- ``pending_grants`` ← ``grant_moment`` entries with ``content.state="pending"``
- ``planned_today``  ← ``PhaseARecord`` (intents signed but not yet executed)

Single-point redaction site (spec L66 + `rules/event-payload-classification.md`
Rule 1): every ``record_id`` (ledger entry id) and ``principal_genesis_id``
placed into the returned ``DigestSummary`` is routed through
``format_record_id_for_event`` BEFORE placement. The aggregator is THE filter
site — downstream (renderer, fanout, channel adapters) trust the summary
already-redacted.

Per `rules/observability.md` § 1: aggregate() emits start/ok structured logs
with a principal_id PREFIX only (never the full id) per Rule 8 (schema-revealing
identifiers stay short).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from dataflow.classification.event_payload import format_record_id_for_event

from envoy.daily_digest.payload import DigestSummary
from envoy.ledger.facade import EnvoyLedger
from envoy.ledger.hash_chain import EntryEnvelope

logger = logging.getLogger(__name__)

# Model name passed to format_record_id_for_event for digest-section record_ids.
# The helper hashes classified-PK values; when no policy is registered (Phase-01
# default) values pass through as strings per the helper's contract.
_DIGEST_MODEL_NAME: str = "daily_digest"

# Entry types per shard 11 § 5.1 + specs/ledger.md § Entry types table.
_ACTION_TYPE = "PhaseBRecord"
_REFUSAL_TYPES = ("posture_change", "system_error")
_PENDING_GRANT_TYPE = "grant_moment"
_PLANNED_TYPE = "PhaseARecord"


class LedgerAggregator:
    """Builds a `DigestSummary` from the previous-window Ledger entries.

    Constructed with explicit dependencies per
    `rules/facade-manager-detection.md` Rule 3 — no global lookups. The
    optional `classification_policy` threads through to
    `format_record_id_for_event`; when None (Phase-01 default, no
    classifications registered) record_ids pass through as strings.
    """

    def __init__(
        self,
        *,
        ledger: EnvoyLedger,
        classification_policy: object | None = None,
    ) -> None:
        self._ledger = ledger
        self._policy = classification_policy

    async def aggregate(
        self,
        *,
        principal_id: str,
        since: datetime,
        until: datetime,
    ) -> DigestSummary:
        """Return the 5-section `DigestSummary` for `[since, until)`.

        Each section tuple is sorted ascending by the source entry's
        ``sequence`` (stable, deterministic — matches the chain-walk order).
        Every ``ledger_id`` is the post-redaction form from
        ``format_record_id_for_event``.
        """
        logger.info(
            "daily_digest.aggregate.start",
            extra={
                "principal_id_prefix": principal_id[:8],
                "since": since.isoformat(),
                "until": until.isoformat(),
            },
        )

        actions_entries = await self._ledger.query(
            filter={"principal_id": principal_id, "event_type": _ACTION_TYPE},
            since=since,
            until=until,
        )
        refusal_entries = await self._ledger.query(
            filter={"principal_id": principal_id, "event_types": _REFUSAL_TYPES},
            since=since,
            until=until,
        )
        grant_entries = await self._ledger.query(
            filter={"principal_id": principal_id, "event_type": _PENDING_GRANT_TYPE},
            since=since,
            until=until,
        )
        planned_entries = await self._ledger.query(
            filter={"principal_id": principal_id, "event_type": _PLANNED_TYPE},
            since=since,
            until=until,
        )

        actions = tuple(self._action_row(e) for e in actions_entries)
        refusals = tuple(self._refusal_row(e) for e in refusal_entries if self._is_refusal(e))
        pending_grants = tuple(
            self._grant_row(e) for e in grant_entries if (e.content or {}).get("state") == "pending"
        )
        planned_today = tuple(self._planned_row(e) for e in planned_entries)
        spend = self._spend_section(actions_entries)

        logger.info(
            "daily_digest.aggregate.ok",
            extra={
                "principal_id_prefix": principal_id[:8],
                "actions": len(actions),
                "refusals": len(refusals),
                "pending_grants": len(pending_grants),
                "planned_today": len(planned_today),
            },
        )

        return DigestSummary(
            actions=actions,
            refusals=refusals,
            spend=spend,
            pending_grants=pending_grants,
            planned_today=planned_today,
        )

    # ---- Per-section row builders (single-point redaction) -------------

    def _redact(self, record_id: str) -> str:
        """Route a record_id through the classification-policy redactor.

        Spec L66: classified record_ids become `sha256:<8hex>`; unclassified
        pass through as strings. The aggregator is the single-point filter.
        """
        return format_record_id_for_event(self._policy, _DIGEST_MODEL_NAME, record_id)

    def _action_row(self, entry: EntryEnvelope) -> dict[str, Any]:
        content = entry.content or {}
        return {
            "ledger_id": self._redact(entry.entry_id),
            "summary": content.get("summary", ""),
            "outbox_items": tuple(content.get("outbox_items", ())),
        }

    def _refusal_row(self, entry: EntryEnvelope) -> dict[str, Any]:
        content = entry.content or {}
        return {
            "ledger_id": self._redact(entry.entry_id),
            "reason_code": content.get("reason_code", content.get("decision", "unknown")),
        }

    def _grant_row(self, entry: EntryEnvelope) -> dict[str, Any]:
        content = entry.content or {}
        return {
            "grant_id": self._redact(content.get("grant_id", entry.entry_id)),
            "summary": content.get("summary", ""),
        }

    def _planned_row(self, entry: EntryEnvelope) -> dict[str, Any]:
        content = entry.content or {}
        return {
            "intent_id": self._redact(content.get("intent_id", entry.entry_id)),
            "summary": content.get("summary", ""),
        }

    @staticmethod
    def _is_refusal(entry: EntryEnvelope) -> bool:
        """True iff the entry represents a refusal.

        ``posture_change`` entries are refusals only when ``decision=deny``;
        ``system_error`` entries are refusals only when the fault code is in
        the refusal class (``content.refusal_class`` truthy). This avoids
        surfacing benign posture changes (e.g. upgrade to autonomous) or
        non-refusal runtime faults as user-facing refusals.
        """
        content = entry.content or {}
        if entry.type == "posture_change":
            return content.get("decision") == "deny"
        if entry.type == "system_error":
            return bool(content.get("refusal_class"))
        return False

    def _spend_section(self, action_entries: list[EntryEnvelope]) -> dict[str, int]:
        """Sum spend from PhaseBRecord content; read ceiling from latest entry.

        Phase-01 reads spend from ledger content because the live budget
        counter (shard 12) is Phase-02. ``current_microdollars`` is the sum of
        ``cost_microdollars`` across the window's PhaseBRecords;
        ``monthly_ceiling_microdollars`` is taken from the most recent entry
        carrying it (entries are pre-sorted by sequence ascending, so the last
        non-None ceiling wins).
        """
        current = 0
        ceiling = 0
        for entry in action_entries:
            content = entry.content or {}
            cost = content.get("cost_microdollars")
            if isinstance(cost, int):
                current += cost
            entry_ceiling = content.get("monthly_ceiling_microdollars")
            if isinstance(entry_ceiling, int):
                ceiling = entry_ceiling
        return {
            "current_microdollars": current,
            "monthly_ceiling_microdollars": ceiling,
        }


__all__ = ["LedgerAggregator"]
