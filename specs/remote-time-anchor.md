# remote-time-anchor

## Purpose

Optional quorum time-anchor for Temporal dimension enforcement. Opt-in per doc 00 v3 §4.1 item 7b.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md v3 §4.1 item 7b + 09-threat-model.md v3 T-001`.
- **Threats mitigated:** T-001 clock-skew bypass of Temporal dimension.
- **BETs tested:** BET-3 sovereignty under Temporal envelope strength.

## Phase 02 deliverable.

## Design

Quorum of public time-stamp authorities (TSAs): FreeTSA + DigiCert + Apple trust roots. ≥ 2 of 3 required for anchor to be accepted.

## Query cadence

Hourly default. User-configurable.

## Anchor record (Ledger entry type `time_anchor`)

```json
{
  "type": "time_anchor",
  "tsa_responses": [
    {"tsa_id": "freetsa", "timestamp": "...", "signature_hex": "..."},
    {"tsa_id": "digicert", "timestamp": "...", "signature_hex": "..."}
  ],
  "quorum_achieved": 2,
  "envoy_local_time_at_query": "...",
  "anchor_time_at_quorum": "...",
  "skew_ms": <int>,
  "signed_by_runtime_device_key": "..."
}
```

## Consent

Opt-in via distinct Grant Moment — separate from Foundation Health Heartbeat (§7a). Both consents separately cascade-revocable.

## Privacy

- OHTTP relay for TSA queries (IP unlinkability).
- Rate-limited (hourly).
- No user-identifying payload; request contains only Envoy version + standard TSA protocol RFC 3161.

## Consumption by Temporal dimension

envelope.temporal checks use `max(Ledger monotonic clock, most_recent_anchor.anchor_time)` when user has opted in. Strong enforcement if anchor recent; degrades gracefully if anchor stale beyond user-declared window.

## Residual risk

Per doc 09 v3 T-001: clock-forward spoofing during narrow attack window still possible; user receives no positive assurance that their Temporal envelope is absolutely enforced against clock attackers with device control.

## Error taxonomy

| Error                                      | Trigger                                                                                     | User action                                                                                  | Retry                  |
| ------------------------------------------ | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------- |
| `ClockSkewExceededError`                   | `skew_ms` between Envoy local clock and quorum anchor exceeds user-declared envelope window | Surface "device clock untrusted" banner; user re-syncs OS clock OR widens window             | Manual after re-sync   |
| `QuorumNotReachedError`                    | Fewer than 2-of-3 TSA responses returned valid signatures within query timeout              | Anchor not refreshed; degrade gracefully if anchor stale beyond user-declared window         | Auto next hourly cycle |
| `AnchorVerifyFailedError`                  | TSA response signature does not verify against pinned TSA trust roots                       | Refuse anchor; surface as TSA-rotation-or-MITM event; investigate                            | Never (security event) |
| `TSAUnavailableError`                      | Single TSA endpoint timeout or non-200; quorum may still be reached if 2-of-3 succeeded     | No user action if quorum reached; if quorum failed, see `QuorumNotReachedError`              | Auto next hourly cycle |
| `OHTTPRelayUnavailableError`               | OHTTP relay refused TSA query (privacy gate failure)                                        | Refuse query; user opts to skip this anchor cycle OR enables direct query (degraded privacy) | Auto next cycle        |
| `RFC3161MalformedResponseError`            | TSA response not parseable per RFC 3161                                                     | Refuse anchor from this TSA; report TSA registry maintainer                                  | Auto next cycle        |
| `AnchorConsentRevokedError`                | User has cascade-revoked Remote Time Anchor consent; runtime attempted query                | Stop queries; clear pending anchor cache; Temporal envelope falls back to local Lamport      | Manual after re-opt-in |
| `AnchorStaleWarning` (advisory)            | Most-recent anchor older than user-declared staleness window                                | UX advisory; Temporal envelope continues with degraded enforcement                           | Auto next cycle        |
| `LocalClockForwardSpoofWarning` (advisory) | Local OS clock advanced > anchor_time + skew tolerance (T-001 narrow-window risk)           | Surface advisory; user investigates device clock tampering                                   | N/A                    |

## Cross-references

- specs/envelope-model.md — Temporal dimension.
- specs/ledger.md — `time_anchor` entries.
- specs/foundation-health-heartbeat.md — sibling opt-in Grant Moment pattern.
- specs/network-security.md — TLS + cert pinning for TSA endpoints.
- specs/grant-moment.md — opt-in consent flow.
- specs/threat-model.md — T-001.

## Test location

- `tests/integration/test_remote_time_anchor_quorum_reached.py` — 2-of-3 TSA response success; anchor accepted (Tier 2).
- `tests/integration/test_remote_time_anchor_quorum_failed.py` — 1-of-3 TSA response; anchor refused.
- `tests/regression/test_t001_clock_skew_bypass_envelope.py` — T-001 defense; local clock-forward spoof flagged.
- `tests/integration/test_anchor_signature_verify_pinned_root.py` — TSA cert outside pinned trust roots refused.
- `tests/integration/test_anchor_ohttp_relay.py` — TSA query routes via OHTTP relay; IP unlinkability assertion.
- `tests/integration/test_anchor_consent_cascade_revoke.py` — cascade revocation halts queries + clears cache.
- `tests/integration/test_anchor_stale_window_temporal_degrade.py` — Temporal envelope graceful degradation under stale anchor.
- `tests/integration/test_anchor_hourly_cadence.py` — default hourly query + user-configurable cadence.
- `tests/e2e/test_anchor_phase02_tor_route.py` — Phase 02 Tor-routed TSA query (Tier 3, optional).

## Open questions

1. TSA quorum membership — FreeTSA + DigiCert + Apple sufficient diversity, or add fourth (e.g. Sectigo) for resilience.
2. User-declared staleness window default — 24h reasonable for most users, but high-OPSEC may want 1h; Phase 01 telemetry will inform.
3. Tor route default for TSA queries — privacy benefit vs Tor exit-node observability; opt-in granularity vs Foundation Health Heartbeat parity.
4. Anchor consent UX — distinct Grant Moment vs combined "privacy bundle" with Foundation Health Heartbeat; cross-spec coordination.
5. T-001 residual narrow-window risk — what positive assurance can be surfaced beyond advisory; coordination with envelope-model.md Temporal dimension strength tiers.
