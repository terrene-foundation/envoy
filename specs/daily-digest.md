# daily-digest

## Purpose

Morning ritual delivering 2-min action/refusal/spend summary + pending Grant Moments.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/01-ux-rituals.md v2 §5`.
- **Threats mitigated:** T-019 habituation defense via low-engagement fallback.
- **BETs tested:** BET-8 habit formation.

## Schedule

User-configured delivery time (default 8am local). User-chosen channel (default first-connected).

## Content template

Actions (with outbox items), refusals, spend (of monthly ceiling), pending Grant Moments, today's planned actions, reply prompt.

## Interaction

- Reply "no"/no-reply: proceed with planned actions.
- Reply "yes"/modify: extract user changes + apply.
- Reply "skip digest": temporarily disable.

## Low-engagement fallback

<2 Digest opens/week for 3 weeks → offer 3-line compact form or event-driven-only delivery (fires on Grant Moment pending or budget > 80%).

## Channel-adaptive rendering

Email/Web: rich format + attachments. Telegram/Slack/Discord: inline buttons. SMS/WhatsApp: compact 10-line. CLI: on `envoy digest today`.

## Shadow-segment post-duress surface (V2 C-02 fix)

If unread duress event in shadow segment at Digest time, Digest renders with priority banner + `[Review duress event]` button.

## Schema (digest payload)

```json
{
  "schema_version": "digest/1.0",
  "digest_id": "uuid-v7",
  "principal_genesis_id": "sha256:...",
  "scheduled_for": "<iso8601>",
  "delivered_at": "<iso8601 | null>",
  "channel_id": "<adapter id>",
  "form": "rich | compact | event_only",
  "duress_banner": {
    "present": <bool>,
    "shadow_event_ref": "<ledger-entry-id | null>"
  },
  "summary": {
    "actions": [{"ledger_id": "...", "summary": "...", "outbox_items": [...]}],
    "refusals": [{"ledger_id": "...", "reason_code": "..."}],
    "spend": {"current_microdollars": <int>, "monthly_ceiling_microdollars": <int>},
    "pending_grants": [{"grant_id": "...", "summary": "..."}],
    "planned_today": [{"intent_id": "...", "summary": "..."}]
  },
  "user_reply": "<inline | null>",
  "receipt_hash": "sha256:..."
}
```

Classified `record_id` and `principal_genesis_id` values routed through `format_record_id_for_event` per specs/classification-policy.md.

## Error taxonomy

| Error                                       | Trigger                                                                     | User action                                                                        | Retry                 |
| ------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | --------------------- |
| `DigestDeliveryFailedError`                 | All configured channels return `SendTimeoutError` / `ChannelTransportError` | Surface in next Digest with "X missed deliveries" banner                           | Auto next morning     |
| `DuressBannerSuppressedError`               | Shadow-segment duress unread but caller is non-primary channel              | Surface duress banner ONLY on primary channel; non-primary delivers compact digest | Never (T-018 defense) |
| `RedactedFieldRenderError`                  | Channel cannot render redacted-field markers (e.g. SMS)                     | Drop classified rows; render summary count "N classified entries hidden"           | Auto                  |
| `LowEngagementFallbackTriggered` (advisory) | <2 opens/week × 3 weeks                                                     | UX offers compact form OR event-only delivery                                      | Manual choice         |
| `DigestSkippedTooLongWarning`               | Skip-digest mode exceeds 30 days                                            | UX prompts re-engagement; cadence re-evaluation                                    | Manual                |

## Cross-references

- specs/channel-adapters.md — per-channel rendering + `send_digest`.
- specs/ledger.md — action summary source.
- specs/trust-lineage.md — shadow segment access.
- specs/classification-policy.md — record_id redaction in summary.
- specs/threat-model.md — T-019.

## Test location

- `tests/e2e/test_daily_digest_morning_delivery.py` — scheduled delivery on each Phase-01 channel (Tier 3).
- `tests/integration/test_digest_form_per_channel.py` — rich vs compact vs SMS rendering.
- `tests/integration/test_low_engagement_fallback.py` — <2 opens × 3 weeks → compact offer.
- `tests/integration/test_duress_banner_primary_only.py` — V2 C-02 banner on primary channel only.
- `tests/regression/test_t019_habituation_low_engagement_fallback.py` — T-019 defense.
- `tests/integration/test_digest_reply_no_yes_skip.py` — reply parsing + action extraction.

## Open questions

1. Default 8am local — across timezones in Shared Household, which household member's tz wins.
2. Compact 10-line SMS budget — sufficient for 80% of users vs information density.
3. "Skip digest" duration — temporary (1 week default?) vs indefinite.
4. Reply parsing extensibility — natural-language reply vs structured commands; risk of misinterpretation.
5. Receipt_hash content — what bytes exactly; cross-channel byte-identity guarantee.
