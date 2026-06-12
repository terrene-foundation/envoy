# network-security

## Purpose

TLS 1.3 + certificate pinning for Foundation endpoints + strict SNI + HSTS + Tor option.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/09-threat-model.md v3 T-080 + 06-distribution.md`.
- **Threats mitigated:** T-080 network MITM + TLS downgrade.
- **BETs tested:** BET-3 sovereignty under network transit.

## TLS

- Minimum TLS 1.3 for all outbound connections.
- Cipher suites per RFC 9325 + Envoy allowlist.

## Certificate pinning

- Foundation-operated endpoints (Envelope Library, OHTTP relay, sync node, migration-allowlist registry): pinned certificates shipped with Envoy binary.
- Updates delivered via signed binary release (not via live update).
- User-added CAs for Foundation endpoints REFUSED — prevents corporate MITM.

## Strict SNI + HSTS for all outbound HTTPS.

## Third-party endpoints

Standard OS trust store for cloud model providers + channel transports. Per-provider certificate pinning optional (user-configurable in envelope.communication).

## Tor option (Phase 02+)

Optional route-through-Tor for privacy-sensitive traffic (Foundation Health Heartbeat, time anchor).

## Residual risk

State-actor MITM with stolen CA keys — out of §1.2 scope.

## Error taxonomy

| Error                                  | Trigger                                                                                   | User action                                                                                      | Retry                        |
| -------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------------------------- |
| `CertPinMismatchError`                 | TLS handshake to Foundation-operated endpoint returns cert NOT in pinned-keys allowlist   | Refuse connection; surface "Foundation MITM suspected" banner; user verifies via signed binary   | Never (T-080 defense)        |
| `TLSVersionTooLowError`                | Outbound endpoint negotiates TLS < 1.3                                                    | Refuse connection; surface "endpoint does not support TLS 1.3"; user reports OR updates endpoint | Never (structural)           |
| `RevocationCheckFailedError`           | OCSP / CRL lookup fails for non-pinned third-party endpoint                               | Soft-fail per RFC 6066 stapling rules; surface advisory; user may opt to refuse                  | Auto with backoff            |
| `SNIStrippingDetectedError`            | Strict SNI mode: handshake completed without SNI extension or with mismatched SNI         | Refuse connection; investigate intermediary stripping intent                                     | Never (security event)       |
| `UserAddedCAForFoundationError`        | OS trust store added a user CA, then a Foundation-endpoint connection attempted to use it | Refuse connection; user removes CA OR connects to non-Foundation endpoint via that CA            | Never (corporate-MITM block) |
| `CipherSuiteRefusedError`              | Endpoint negotiated cipher suite outside Envoy allowlist (RFC 9325 + Envoy curated list)  | Refuse connection; surface allowlist mismatch; investigate endpoint config                       | Never                        |
| `HSTSPreloadMissingWarning` (advisory) | Outbound HTTPS endpoint missing HSTS or not in preload list                               | UX advisory; not a hard block for non-Foundation endpoints                                       | Manual                       |
| `TorRouteUnavailableError`             | Phase 02+ Tor route requested but Tor daemon unreachable                                  | Surface fallback choice (refuse vs direct); user picks per-traffic-class                         | Manual after choice          |
| `BinaryReleaseSignatureInvalidError`   | Pinned-cert update bundled in binary release fails signature verification                 | Refuse update; user re-fetches binary via N=3 mirrors per specs/distribution.md                  | Manual after re-fetch        |

## Cross-references

- specs/foundation-health-heartbeat.md — OHTTP relay uses pinned certs.
- specs/remote-time-anchor.md — same.
- specs/distribution.md — installer-level binary signature verification.
- specs/channel-adapters.md — third-party channel TLS; Discord webhook SSRF guard (`_validate_webhook_url_ssrf`) blocks private/loopback/metadata IPs and hostile-encoded URLs at adapter startup (see § Network security in channel-adapters.md).
- specs/foundation-ops.md — Foundation endpoint registry + cert pin manifest.
- specs/threat-model.md — T-080.

## Test location

- `tests/integration/test_strict_sni_enforcement.py` (`test_tls_below_1_3_refused`) — outbound to a sub-TLS-1.3 endpoint refused (Tier 2).
- `tests/integration/test_cert_pin_mismatch.py` — T-080 defense; a presented certificate whose fingerprint ≠ the pinned cert raises `CertPinMismatchError`.
- `tests/integration/test_user_added_ca_foundation_refused.py` — corporate-MITM CA refused for Foundation endpoints.
- `tests/integration/test_strict_sni_enforcement.py` — handshake without SNI refused.
- `tests/integration/test_cipher_suite_allowlist.py` — RFC 9325 + Envoy allowlist enforcement.
- `tests/integration/test_cert_rotation_drill.py` — quarterly pin-rotation flow via signed binary release.
- `tests/integration/test_third_party_optional_pin.py` — user-configurable per-provider pin in envelope.communication.
- `tests/integration/test_tor_route_optional_phase02.py` — Phase 02+ Tor route opt-in (Tier 2 with tor in CI).

## Open questions

1. Pinned-cert distribution cadence vs emergency rotation — quarterly default sufficient for state-actor cert-compromise scenarios.
2. Strict SNI vs ECH (Encrypted Client Hello) — Phase 02 ECH adoption breaks strict-SNI assertions; coordination needed.
3. OCSP stapling soft-fail vs hard-fail policy per traffic class (Foundation vs third-party).
4. Tor route default-on for `Foundation Health Heartbeat` — privacy benefit vs Tor exit-node risk; opt-in granularity.
5. User-CA refusal UX on corporate-laptop deployments — surfacing the refusal without false-alarming legitimate enterprise CAs not targeting Foundation endpoints.
