# foundation-health-heartbeat

## Purpose

Opt-in anonymous aggregate telemetry via STAR/Prio + differential privacy + OHTTP + signed-consent Grant Moment.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md v3 §5.0`.
- **Threats mitigated:** T-052 OHTTP compromise, T-054 covert channel, T-023/T-024 falsifiability measurement, T-041 (defense-in-depth: `DuressFlagLeakageRefusedError` prevents `duress_unlock_detected` from ever appearing in payload).
- **BETs tested:** BET-1, BET-3, BET-4, BET-8, BET-12 measurement substrate.

## Scope

Narrow §4.1 item 7a carveout from no-phone-home posture. Enables BET falsifiability measurement under doc 00 §5.0 methodology.

## Design stack

1. **STAR (Signer-Anonymous Reporting Telemetry) or Prio** — client splits each report into encrypted shares; collector aggregates without individual values; k-anonymity k≥100.
2. **Differential privacy** — bounded noise on each counter; ε per-metric published.
3. **OHTTP (RFC 9458)** — Foundation Key Configuration Server; Relay (optionally third-party) strips source IPs.
4. **Signed consent** — opt-in Grant Moment producing signed Delegation Record; cascade-revocable.

## Payload

Per-install random ID (rotated quarterly; debounced per source analysis doc `01-ux-rituals.md` L-01 fix — heartbeat send MUST NOT trigger within 24h of a ritual to avoid coupling user-observable ritual timing to network payload). Envoy version, 21 boolean flags, aggregated via STAR.

**21 flags:**
`completed_boundary_conversation`, `opened_daily_digest_this_week`, `completed_weekly_posture_review`, `opened_monthly_trust_report`, `grant_moment_novelty_approved`, `grant_moment_novelty_denied`, `force_install_used_skill`, `authorship_score_reached_3`, `authorship_score_reached_5`, `posture_delegating_active`, `posture_autonomous_active`, `budget_monthly_exceeded_50pct`, `budget_monthly_exceeded_80pct`, `channel_telegram_active`, `channel_slack_active`, `channel_discord_active`, `channel_whatsapp_active`, `channel_signal_active`, `channel_imessage_active`, `runtime_kailash_rs_active`, `enterprise_mode_active`.

**Flags NEVER reported:** `duress_unlock_detected` (T-041 privacy preservation).

## Cadence

Weekly heartbeat. Counters reset on successful send.

## Consent layer

First-run Grant Moment with explicit text naming cryptographic properties. Default: opt-OUT. Revocation: cascade-revocable; no further heartbeats.

## Covert-channel defense (T-054)

- Reproducible builds detect compromised client.
- Differential privacy on flag entropy.
- Foundation-side periodic aggregate-payload audit.
- Fixed payload schema (client cannot add arbitrary fields).

## Error taxonomy

| Error                                       | Trigger                                                                                    | User action                                                                                  | Retry                   |
| ------------------------------------------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | ----------------------- |
| `OHTTPRelayUnavailableError`                | Foundation OHTTP relay unreachable; outbound IP would not be stripped                      | Drop heartbeat for this cycle; counters retained until next successful send                  | Auto next weekly cycle  |
| `STARShardCorruptError`                     | STAR/Prio share split failed at client OR collector aggregation rejected malformed share   | Drop heartbeat for this cycle; counters retained; investigate client crypto integrity        | Auto next cycle         |
| `DPBudgetExceededError`                     | Differential-privacy ε budget for a metric exhausted within reporting window               | Drop affected metric for this cycle; non-affected metrics report normally                    | Auto next cycle         |
| `kAnonymityFloorViolatedError`              | Aggregate cohort size for a flag below k=100 floor at collector                            | Collector withholds aggregate; Foundation publishes withholding event in transparency report | Never (privacy gate)    |
| `RitualCouplingDebounceTriggered`           | Heartbeat send window overlaps with ritual within 24h (L-01 fix)                           | Defer send 24h to avoid coupling user-observable ritual timing to network payload            | Auto after debounce     |
| `ConsentRevokedError`                       | User cascade-revoked Foundation Health Heartbeat consent; runtime attempted send           | Stop sends; clear pending counters; runtime continues without telemetry                      | Manual after re-opt-in  |
| `PayloadSchemaDriftError`                   | Client attempted to add field outside fixed payload schema (T-054 covert-channel defense)  | Refuse send; surface as integrity event; investigate client compromise                       | Never (T-054 defense)   |
| `ReproducibleBuildAttestationMissingError`  | Client cannot present reproducible-build attestation when Foundation requests verification | Refuse send; user re-installs from attested binary per specs/distribution.md                 | Manual after re-install |
| `DuressFlagLeakageRefusedError`             | Internal attempt to add `duress_unlock_detected` to payload (T-041 privacy preservation)   | Refuse send; this is a programming error or hostile patch                                    | Never (T-041 defense)   |
| `RandomIdRotationOverdueWarning` (advisory) | Per-install random ID > quarterly rotation window                                          | Auto-rotate at next cycle; user notified in transparency UX                                  | Auto                    |

## Cross-references

- specs/grant-moment.md — consent flow.
- specs/trust-lineage.md — signed consent Delegation Record.
- specs/acceptance-metrics.md — BET falsifiability consumer.
- specs/ledger.md — `FoundationHealthHeartbeatConsent` entry.
- specs/network-security.md — TLS + cert pinning for OHTTP relay.
- specs/foundation-ops.md — Foundation Key Configuration Server registry.
- specs/threat-model.md — T-023, T-024, T-041, T-052, T-054.

## Test location

- `tests/integration/test_heartbeat_consent_grant_moment.py` — first-run opt-in Grant Moment + signed Delegation Record (Tier 2).
- `tests/integration/test_heartbeat_consent_cascade_revoke.py` — cascade revocation halts further sends + clears counters.
- `tests/regression/test_t052_ohttp_relay_compromise.py` — T-052 defense; relay loss → drop cycle, counters retained.
- `tests/regression/test_t054_payload_schema_fixed.py` — T-054 defense; client cannot add arbitrary fields.
- `tests/regression/test_t041_duress_flag_never_reported.py` — T-041 defense; `duress_unlock_detected` never in payload.
- `tests/integration/test_heartbeat_21_flag_payload.py` — exactly 21 flags emitted; flag set matches spec.
- `tests/integration/test_heartbeat_l01_ritual_coupling_debounce.py` — L-01 fix; 24h debounce window after ritual.
- `tests/integration/test_heartbeat_random_id_quarterly_rotation.py` — per-install random ID rotates quarterly.
- `tests/integration/test_heartbeat_dp_epsilon_budget_per_metric.py` — DP ε budget enforced per-metric.
- `tests/integration/test_heartbeat_k_anonymity_floor_100.py` — collector withholds below k=100.
- `tests/e2e/test_heartbeat_full_weekly_cycle.py` — opt-in, 7-day counter accrual, send via OHTTP, counter reset (Tier 3).

## Open questions

1. ε per-metric publication — public values vs privacy-budget aggregate; transparency vs analyzability trade-off.
2. k-anonymity floor 100 — sufficient for low-population channel flags (e.g. `channel_imessage_active` if iMessage rare).
3. OHTTP relay third-party operator selection — Foundation operates default; community relay opt-in cadence.
4. Quarterly random-ID rotation — sufficient against multi-quarter linkage; coordination with reproducible-build attestation cadence.
5. 21-flag set Phase-04 expansion — adding flags requires schema bump + collector readiness; cadence for adding new flags vs deprecating.
