# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.fanout — PerChannelFanout.

Per `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
§ 3 step 4 + § 5.1 (write pattern) + § 5.2 (channel substrate) — parallel
fan-out across the principal's active channels with fault isolation, plus one
`ritual_completion` Ledger entry per successful delivery (the EC-3 acceptance
evidence).

Adapter-boundary translation: the structured `DigestPayload` (schema owner) is
rendered to the channels-side wire shape `DailyDigestPayload` (digest_date +
markdown_body + metrics) before `ChannelAdapter.send_digest` is called — per
shard 11 § 5.2 ("the Digest service produces a unified DigestPayload and each
adapter translates to channel-native form"). The per-channel native rendering
(inline buttons, Block Kit, SMS compaction) is the adapter's job; the fanout
produces ONE canonical markdown body.

Fault isolation: `asyncio.gather(..., return_exceptions=True)` so one channel's
`SendTimeoutError` / `ChannelTransportError` does not abort delivery to the
others. If EVERY channel fails, raise `DigestDeliveryFailedError` (spec L72).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from envoy.channels.envelope import DailyDigestPayload
from envoy.daily_digest.errors import DigestDeliveryFailedError

if TYPE_CHECKING:
    from envoy.channels.adapter import ChannelAdapter
    from envoy.channels.envelope import SendReceipt
    from envoy.daily_digest.payload import DigestPayload
    from envoy.ledger.facade import EnvoyLedger

logger = logging.getLogger(__name__)


class PerChannelFanout:
    """Fault-isolated parallel fan-out + per-success ritual_completion write.

    Constructed with explicit dependencies per
    `rules/facade-manager-detection.md` Rule 3: the channel-adapter registry
    (channel_id → adapter) and the Ledger (for ritual_completion writes).
    """

    def __init__(
        self,
        *,
        channel_adapters: dict[str, ChannelAdapter],
        ledger: EnvoyLedger,
    ) -> None:
        self._channel_adapters = channel_adapters
        self._ledger = ledger

    async def emit(
        self,
        *,
        principal_id: str,
        payload: DigestPayload,
        active_channel_ids: list[str],
        timeout_seconds: int = 10,
    ) -> dict[str, SendReceipt | BaseException]:
        """Deliver `payload` to every active channel in parallel.

        Returns a dict keyed by channel_id whose value is the `SendReceipt`
        (success) or the `Exception` (failure). Raises
        `DigestDeliveryFailedError` only when EVERY channel failed.
        """
        if not active_channel_ids:
            raise DigestDeliveryFailedError(
                f"no active channels for principal {principal_id[:8]!r}",
            )

        channel_payload = self._to_channel_payload(payload)

        # Build one task per active channel; unknown channel_ids resolve to a
        # KeyError captured as that channel's result (fault-isolated).
        async def _send(channel_id: str) -> SendReceipt:
            adapter = self._channel_adapters.get(channel_id)
            if adapter is None:
                raise KeyError(f"no adapter registered for channel {channel_id!r}")
            return await adapter.send_digest(
                principal_id, channel_payload, timeout_seconds=timeout_seconds
            )

        results = await asyncio.gather(
            *(_send(cid) for cid in active_channel_ids),
            return_exceptions=True,
        )

        outcome: dict[str, SendReceipt | BaseException] = {}
        success_count = 0
        for channel_id, result in zip(active_channel_ids, results, strict=True):
            if isinstance(result, BaseException):
                # Per rules/observability.md Rule 7 — surface each per-channel
                # failure at WARN with the exception type (not the full chain,
                # to avoid CWE-117 leakage of attacker-controlled transport text).
                logger.warning(
                    "daily_digest.fanout.failure",
                    extra={
                        "principal_id_prefix": principal_id[:8],
                        "channel_id": channel_id,
                        "error_type": type(result).__name__,
                    },
                )
                outcome[channel_id] = result
            else:
                outcome[channel_id] = result
                success_count += 1
                await self._write_ritual_completion(
                    principal_id=principal_id,
                    channel_id=channel_id,
                    payload=payload,
                    receipt=result,
                )

        if success_count == 0:
            raise DigestDeliveryFailedError(
                f"all {len(active_channel_ids)} channel(s) failed for principal "
                f"{principal_id[:8]!r}",
            )

        logger.info(
            "daily_digest.fanout.ok",
            extra={
                "principal_id_prefix": principal_id[:8],
                "delivered": success_count,
                "attempted": len(active_channel_ids),
            },
        )
        return outcome

    def _to_channel_payload(self, payload: DigestPayload) -> DailyDigestPayload:
        """Render the structured DigestPayload to the channels-side wire shape.

        Produces ONE canonical markdown body; per-channel native rendering
        (buttons, Block Kit, SMS compaction) is the adapter's job per shard 11
        § 5.2. `metrics` carries the spend + section counts so an adapter can
        render compact headline numbers without re-parsing the markdown.
        """
        summary = payload.summary
        digest_date = payload.scheduled_for.split("T", 1)[0]

        lines: list[str] = [f"# Daily Digest — {digest_date}"]
        if payload.duress_banner.present:
            lines.append("> ⚠️ **Review duress event** — unread security event.")
        lines.append(f"\n**Actions** ({len(summary.actions)})")
        for a in summary.actions:
            lines.append(f"- {a.get('summary', '')}")
        lines.append(f"\n**Refusals** ({len(summary.refusals)})")
        for r in summary.refusals:
            lines.append(f"- {r.get('reason_code', '')}")
        spend = summary.spend
        lines.append(
            f"\n**Spend**: {spend.get('current_microdollars', 0)} / "
            f"{spend.get('monthly_ceiling_microdollars', 0)} microdollars"
        )
        lines.append(f"\n**Pending approvals** ({len(summary.pending_grants)})")
        for g in summary.pending_grants:
            lines.append(f"- {g.get('summary', '')}")
        lines.append(f"\n**Planned today** ({len(summary.planned_today)})")
        for p in summary.planned_today:
            lines.append(f"- {p.get('summary', '')}")
        lines.append('\nReply "no" to proceed, "yes" to modify, "skip digest" to pause.')

        metrics = {
            "actions": len(summary.actions),
            "refusals": len(summary.refusals),
            "pending_grants": len(summary.pending_grants),
            "planned_today": len(summary.planned_today),
            "current_microdollars": spend.get("current_microdollars", 0),
            "monthly_ceiling_microdollars": spend.get("monthly_ceiling_microdollars", 0),
            "form": payload.form,
            "duress_banner_present": payload.duress_banner.present,
        }

        return DailyDigestPayload(
            digest_date=digest_date,
            markdown_body="\n".join(lines),
            metrics=metrics,
        )

    async def _write_ritual_completion(
        self,
        *,
        principal_id: str,
        channel_id: str,
        payload: DigestPayload,
        receipt: SendReceipt,
    ) -> None:
        """Append a `ritual_completion` Ledger entry for a successful delivery.

        Per specs/ledger.md L73 + L118 (ritual_kind="daily_digest"). The
        entry's content carries digest_id, channel_id, form, delivered_at,
        receipt_hash — sufficient for the EC-3 acceptance test to verify
        consecutive 7-day emission via Ledger query.
        """
        await self._ledger.append(
            entry_type="ritual_completion",
            content={
                "principal_id": principal_id,
                "ritual_kind": "daily_digest",
                "digest_id": payload.digest_id,
                "channel_id": channel_id,
                "form": payload.form,
                "delivered_at": receipt.delivered_at.isoformat(),
                "receipt_hash": payload.receipt_hash,
            },
        )


__all__ = ["PerChannelFanout"]
