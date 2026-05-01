# weekly-posture-review

## Purpose

Sunday 90-second ritual for posture + envelope recalibration; batch-to-envelope conversion; authorship nudge.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/01-ux-rituals.md v2 §6`.
- **Threats mitigated:** T-019 rubber-stamp via batch-to-envelope conversion.
- **BETs tested:** BET-8 habit, BET-12 authorship.

## Phase 03 deliverable.

## State machine

W0 intro → W1 summary → W2 posture recommendation → W3 velocity requests → W4 authorship nudge → W5 sign changes → W6 complete.

## Content

- Last-week summary (actions/refusals/spend/Grant Moments).
- Posture recommendation (up/down based on behavior).
- Pending velocity-raise requests (requires 24h cooling-off per H-05 fix).
- Authorship nudge (if score stagnant).

## Discipline

- Skippable; 3-weeks-skipped → cadence re-evaluation prompt.
- All posture RAISES: 5s read-delay before approve.
- Velocity-raise confirmation: 24h cool-off from Sunday sign to Monday effect.

## Error taxonomy

| Error                                  | Trigger                                                                                     | User action                                                                                     | Retry                   |
| -------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------- |
| `BatchToEnvelopeConversionFailedError` | Familiar-repeat batch could not be converted to envelope amendment (rule-AST mismatch)      | Surface convertible vs non-convertible; user signs convertible subset, defers rest              | Manual after triage     |
| `VelocityRaiseCoolingOffError`         | Velocity-raise approval attempted before 24h cool-off (Sunday-sign-to-Monday-effect window) | Wait until Monday effect window; OR escalate via cross-channel Grant Moment per H-05            | Auto after window       |
| `WReviewSkippedTooLongWarning`         | 3 consecutive Sundays skipped → cadence re-evaluation prompt                                | Cadence re-evaluation: continue weekly / shift biweekly / opt-out (require Grant Moment)        | Manual after choice     |
| `PostureRaiseReadDelayError`           | User attempted to approve a posture RAISE before 5s read-delay elapsed                      | UX enforces full read-delay; user re-approves after timer                                       | Manual after delay      |
| `WStatePersistFailedError`             | W0–W6 state-machine progression failed to persist; review enters W_PAUSED                   | Resume on next channel-touch; runtime restores last-persisted W state                           | Auto on resume          |
| `AuthorshipNudgeStaleError`            | Authorship-score nudge data older than week (T-019 batch staleness)                         | Refuse nudge render; recompute against current Ledger; re-issue review                          | Auto after recompute    |
| `VelocityRaiseRequestExpiredError`     | Pending velocity-raise request older than configured retention window                       | Drop request; user re-requests via inline Grant Moment OR next Weekly Review                    | Manual after re-request |
| `CrossChannelReviewMergeError`         | Same review session active on two channels with divergent decisions                         | Surface conflict; user resolves on primary channel; non-primary rendered as "decided elsewhere" | Manual after resolve    |

## Cross-references

- specs/envelope-model.md — posture ratchet + velocity rules.
- specs/grant-moment.md — batch-to-envelope conversion + velocity-raise cooling-off coordination.
- specs/authorship-score.md — score calculations.
- specs/channel-adapters.md — `send_posture_review` adapter contract + W-state receipt.
- specs/budget-tracker.md — velocity-raise approval flow.
- specs/threat-model.md — T-019.

## Test location

- `tests/integration/test_weekly_posture_review_state_machine.py` — W0→W6 progression + W_PAUSED resume (Tier 2).
- `tests/regression/test_t019_batch_to_envelope_conversion.py` — T-019 defense; familiar-repeat batches convertible to envelope amendments.
- `tests/regression/test_t019_5s_read_delay_on_raise.py` — T-019 defense; 5s read-delay enforced before RAISE approval.
- `tests/integration/test_velocity_raise_24h_cooling_off_h05.py` — H-05 fix; Sunday-sign to Monday-effect window.
- `tests/integration/test_w_review_skip_3_weeks_cadence_prompt.py` — 3-week skip triggers cadence re-evaluation.
- `tests/integration/test_authorship_nudge_score_stagnant.py` — nudge surfaces when score plateau detected.
- `tests/integration/test_cross_channel_review_resolve_primary.py` — divergent decisions resolved on primary channel.
- `tests/e2e/test_weekly_posture_review_full_ritual.py` — end-to-end Sunday review across Phase-01 channels (Tier 3).

## Open questions

1. 90-second budget — sufficient for users with high weekly action volume; coordination with daily-digest.md compaction.
2. 24h Sunday-to-Monday effect window — does it shift around DST / locale changes; cross-spec coordination needed.
3. 3-week skip threshold — empirical calibration; some users may have legitimate vacation gaps.
4. Authorship nudge frequency — every review when stagnant vs once per N reviews; risk of nudge fatigue (T-019 sibling).
5. Cadence re-evaluation default — biweekly fallback vs opt-out gate; coordination with foundation-health-heartbeat.md flag for `completed_weekly_posture_review`.
