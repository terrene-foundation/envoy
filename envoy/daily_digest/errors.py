# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.daily_digest.errors — 5 typed errors per `specs/daily-digest.md` § Error taxonomy.

Per `rules/zero-tolerance.md` Rule 2: every error class below carries a docstring
naming the trigger condition + user-action mapping from the spec table. The
taxonomy is closed — adding a new digest failure mode requires editing both the
spec and this module.
"""

from __future__ import annotations


class DailyDigestError(RuntimeError):
    """Base class for every envoy.daily_digest error.

    Subclasses preserve the spec § Error taxonomy 1:1 mapping so logs filtered
    by `event=daily_digest.error` carry the spec's user-action disposition
    inline.
    """


class DigestDeliveryFailedError(DailyDigestError):
    """All configured channels returned `SendTimeoutError` / `ChannelTransportError`.

    Per spec L72: surface in next Digest with "X missed deliveries" banner.
    Retry: auto next morning. Raised by `PerChannelFanout` after every
    `asyncio.gather(..., return_exceptions=True)` future resolved as exception.
    """


class DuressBannerSuppressedError(DailyDigestError):
    """Shadow-segment duress unread but caller is non-primary channel.

    Per spec L73 + T-018 defense: surface duress banner ONLY on primary
    channel; non-primary delivers compact digest. Retry: never (T-018 defense).
    Raised by `DuressBannerReader.check()` when `channel_id` does not match
    the principal's primary channel binding.
    """


class RedactedFieldRenderError(DailyDigestError):
    """Channel cannot render redacted-field markers (e.g. SMS short-form).

    Per spec L74: drop classified rows; render summary count "N classified
    entries hidden". Retry: auto. Raised by `DigestRenderer.render()` when
    the target channel's `RenderCapabilities` cannot encode the canonical
    `format_record_id_for_event` marker.
    """


class LowEngagementFallbackTriggered(DailyDigestError):
    """Advisory — <2 opens/week × 3 weeks per `LowEngagementTracker`.

    Per spec L75: UX offers compact form OR event-only delivery. Retry:
    manual choice. Advisory exception used to signal the form-flip decision
    upward through `DailyDigestService.start()`; the scheduler logs the event
    at WARN and the next digest uses `form="compact"` (T-019 defense).
    """


class DigestSkippedTooLongWarning(DailyDigestError):
    """Skip-digest mode exceeds `PauseDisableState.SKIP_TOO_LONG_THRESHOLD_DAYS`.

    Per spec L76 (30-day threshold): UX prompts re-engagement; cadence
    re-evaluation. Retry: manual. Raised by `PauseDisableState.is_paused()`
    when the persisted pause window crosses 30 days without explicit resume.
    """


__all__ = [
    "DailyDigestError",
    "DigestDeliveryFailedError",
    "DuressBannerSuppressedError",
    "RedactedFieldRenderError",
    "LowEngagementFallbackTriggered",
    "DigestSkippedTooLongWarning",
]
