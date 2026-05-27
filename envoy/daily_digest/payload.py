# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.payload — DigestPayload + nested dataclasses.

11-field schema/1.0 verbatim per `specs/daily-digest.md` § Schema (lines 39-64).
Frozen dataclasses; no business logic. The 11-field contract pins the
cross-channel byte-identity guarantee (open question 5 in the spec): the
canonical-JSON serialization of `DigestPayload` minus `receipt_hash` is what
`DigestRenderer` hashes to produce `receipt_hash`.

Per `rules/spec-accuracy.md` Rule 1: every field below grep-resolves against
the spec's § Schema block; the schema_version literal "digest/1.0" pins the
forward-compatibility envelope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# Cross-channel byte-identity (open question 5):
# receipt_hash = sha256(canonical_dumps(payload_minus_receipt_hash)).
# The schema_version literal is part of the canonical input so a major-version
# bump invalidates prior receipts deliberately.
DIGEST_SCHEMA_VERSION: str = "digest/1.0"

# Form discriminator — Literal so a misspelled value fails at construction
# rather than at channel-adapter render time.
DigestForm = Literal["rich", "compact", "event_only"]


@dataclass(frozen=True, slots=True)
class DuressBanner:
    """Spec § Schema lines 50-53. Per V2 C-02 fix: primary-channel-only.

    `present` is False when no unread shadow-segment duress event exists OR
    the calling channel is not the principal's primary channel. The
    `DuressBannerReader.check()` method is the single-point gate; consumers
    of `DigestPayload` MUST NOT compute banner presence independently.
    """

    present: bool
    shadow_event_ref: Optional[str]  # ledger-entry-id; None if present is False


@dataclass(frozen=True, slots=True)
class DigestSummary:
    """Spec § Schema lines 54-60. Five immutable section tuples + spend dict.

    Tuples (not lists) ensure the dataclass is hashable and the canonical-JSON
    serialization is stable across cross-channel byte-identity checks. The
    inner dicts carry classified-PK-redacted `ledger_id` values per spec L66
    (`format_record_id_for_event` redaction at single-point filter in
    `LedgerAggregator`).
    """

    actions: tuple  # tuple[dict]: ledger_id, summary, outbox_items
    refusals: tuple  # tuple[dict]: ledger_id, reason_code
    spend: dict  # current_microdollars + monthly_ceiling_microdollars
    pending_grants: tuple  # tuple[dict]: grant_id, summary
    planned_today: tuple  # tuple[dict]: intent_id, summary


@dataclass(frozen=True, slots=True)
class DigestPayload:
    """Spec § Schema lines 39-64 — 11 fields exactly.

    Construct via `DigestRenderer.render()`. Direct construction permitted in
    tests; production callers MUST route through the renderer so receipt_hash
    canonicalization is uniform.

    The `principal_genesis_id` field is the post-redaction value emitted by
    `format_record_id_for_event` (spec L66 + classification-policy.md). Raw
    genesis IDs MUST NOT reach this class.
    """

    schema_version: str  # always "digest/1.0" (DIGEST_SCHEMA_VERSION)
    digest_id: str  # uuid-v7
    principal_genesis_id: str  # sha256:... routed through format_record_id_for_event
    scheduled_for: str  # iso8601
    delivered_at: Optional[str]  # iso8601 | None
    channel_id: str
    form: DigestForm
    duress_banner: DuressBanner
    summary: DigestSummary
    user_reply: Optional[str]
    receipt_hash: str  # sha256:... over canonical_dumps(payload-minus-receipt_hash)


__all__ = [
    "DIGEST_SCHEMA_VERSION",
    "DigestForm",
    "DuressBanner",
    "DigestSummary",
    "DigestPayload",
]
