# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.renderer — DigestRenderer.

Per `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
§ 3 step 3 + § 3.2 item 4 — constructs the canonical `DigestPayload` from a
`DigestSummary` + back-fill state + duress-banner state, and computes
`receipt_hash` via the Ledger's shared canonical-JSON contract.

`receipt_hash` (open question 5 — cross-channel byte-identity): defined as
``sha256(canonical_dumps(payload_minus_receipt_hash))``. The byte-identity is
achieved by the **single-render → fan-out** design, NOT by recomputing per
channel: `DailyDigestService._run_pipeline` calls `render()` ONCE (one
`digest_id`, one primary `channel_id`), producing one frozen `DigestPayload`
whose `receipt_hash` is then carried verbatim to every active channel by
`PerChannelFanout`. So every channel delivers the SAME `receipt_hash` over the
SAME canonical content. (The per-channel WIRE rendering may differ — e.g. the
T-018 duress-banner strip for non-primary channels — but the receipt anchors
the canonical structured content, which is identical across channels.) The
canonical input therefore intentionally includes `digest_id` + `channel_id`
(the primary): the receipt is unique per digest, shared across its fan-out.

`principal_genesis_id` is routed through ``format_record_id_for_event`` per
spec L66 — raw genesis IDs never reach the payload.

NL summary (optional): spec § Content template mentions a natural-language
summary. Phase 01 ships the structured payload only; the
``EnvoyModelRouter.for_primitive("daily_digest")`` LLM hook is forward-compat
and NOT exercised in Phase 01 (no LLM call on the digest hot path by default).
Per `rules/agent-reasoning.md` the LLM is reserved for genuine reasoning; the
Phase-01 digest is a deterministic aggregate-and-package flow, so no LLM is
invoked — wiring it in would be reasoning-where-none-is-needed.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import asdict
from datetime import datetime

from dataflow.classification.event_payload import (
    ClassificationPolicy,
    format_record_id_for_event,
)

from envoy.daily_digest.payload import (
    DIGEST_SCHEMA_VERSION,
    DigestForm,
    DigestPayload,
    DigestSummary,
    DuressBanner,
)
from envoy.ledger.canonical import canonical_dumps
from envoy.ledger.facade import EnvoyLedger
from envoy.model.router import EnvoyModelRouter

logger = logging.getLogger(__name__)

_DIGEST_MODEL_NAME: str = "daily_digest"
# pk_field passed to format_record_id_for_event for the genesis id.
_GENESIS_PK_FIELD: str = "principal_genesis_id"


class DigestRenderer:
    """Packages a `DigestSummary` into the canonical 11-field `DigestPayload`.

    Constructed with explicit dependencies per
    `rules/facade-manager-detection.md` Rule 3. `model_router` is held for the
    Phase-02 NL-summary hook; `ledger` is held so the renderer can reuse the
    canonical-dumps contract (the import is direct, but holding the ledger
    keeps the dependency explicit for the Phase-02 receipt-anchoring extension
    where the renderer writes a `ritual_completion` pre-image).
    """

    def __init__(
        self,
        *,
        model_router: EnvoyModelRouter,
        ledger: EnvoyLedger,
        classification_policy: ClassificationPolicy | None = None,
    ) -> None:
        self._model_router = model_router
        self._ledger = ledger
        self._policy = classification_policy

    async def render(
        self,
        *,
        principal_id: str,
        channel_id: str,
        summary: DigestSummary,
        duress_banner: DuressBanner,
        form: DigestForm,
        scheduled_for: datetime,
        back_fill_days: int,
    ) -> DigestPayload:
        """Construct + return the canonical `DigestPayload`.

        `back_fill_days` is recorded in observability but does NOT alter the
        payload shape — the back-filled content is already aggregated into
        `summary` by the caller's wider query window (shard 11 § 3.4). The
        payload's `delivered_at` is None at render time; `PerChannelFanout`
        does not mutate the frozen payload — the delivered timestamp is
        captured in the per-channel `SendReceipt` and the `ritual_completion`
        ledger entry, not back-patched into the payload.
        """
        genesis_redacted = format_record_id_for_event(
            self._policy,
            _DIGEST_MODEL_NAME,
            principal_id,
            _GENESIS_PK_FIELD,
        )

        # Build the payload-minus-receipt_hash, canonicalize, hash, then
        # construct the final frozen payload with the receipt_hash filled in.
        # uuid7 is preferred (time-ordered) but not in the 3.13 stdlib; uuid4
        # is the Phase-01 fallback. Phase-02 pins uuid7 once stdlib-stable.
        digest_id = str(uuid.uuid4())

        receipt_hash = self._compute_receipt_hash(
            schema_version=DIGEST_SCHEMA_VERSION,
            digest_id=digest_id,
            principal_genesis_id=genesis_redacted or "",
            scheduled_for=scheduled_for.isoformat(),
            channel_id=channel_id,
            form=form,
            duress_banner=duress_banner,
            summary=summary,
        )

        payload = DigestPayload(
            schema_version=DIGEST_SCHEMA_VERSION,
            digest_id=digest_id,
            principal_genesis_id=genesis_redacted or "",
            scheduled_for=scheduled_for.isoformat(),
            delivered_at=None,
            channel_id=channel_id,
            form=form,
            duress_banner=duress_banner,
            summary=summary,
            user_reply=None,
            receipt_hash=receipt_hash,
        )

        logger.info(
            "daily_digest.render.ok",
            extra={
                "principal_id_prefix": principal_id[:8],
                "digest_id": digest_id,
                "channel_id": channel_id,
                "form": form,
                "back_fill_days": back_fill_days,
                "duress_banner_present": duress_banner.present,
            },
        )
        return payload

    def _compute_receipt_hash(
        self,
        *,
        schema_version: str,
        digest_id: str,
        principal_genesis_id: str,
        scheduled_for: str,
        channel_id: str,
        form: DigestForm,
        duress_banner: DuressBanner,
        summary: DigestSummary,
    ) -> str:
        """sha256(canonical_dumps(payload_minus_receipt_hash)) per § 3.2 item 4.

        `delivered_at` and `user_reply` are excluded from the canonical input
        (both None at render time AND mutable post-delivery) so the receipt
        anchors the CONTENT, not the delivery metadata — this is what makes
        the hash byte-identical across channels that deliver the same content
        at different wall-clock times.
        """
        canonical_input = {
            "schema_version": schema_version,
            "digest_id": digest_id,
            "principal_genesis_id": principal_genesis_id,
            "scheduled_for": scheduled_for,
            "channel_id": channel_id,
            "form": form,
            "duress_banner": asdict(duress_banner),
            "summary": asdict(summary),
        }
        digest_bytes = canonical_dumps(canonical_input)
        return "sha256:" + hashlib.sha256(digest_bytes).hexdigest()


__all__ = ["DigestRenderer"]
