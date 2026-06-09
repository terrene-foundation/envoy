# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Foundation-ops (S10) server-side error taxonomy.

These are the SERVER-side errors the OHTTP Key Config Server + Relay raise.
They are distinct from the heartbeat CLIENT taxonomy in
``envoy/heartbeat/errors.py`` (the 10-error client taxonomy, which already
ships ``OHTTPRelayUnavailableError`` — the client-side "drop heartbeat for this
cycle" failure).

The two relay-failure errors are GENUINELY distinct per the specs and S10
EC-S10.3 requires they "surface distinctly":

- ``OHTTPRelayUnavailableError`` (``envoy.heartbeat.errors`` —
  ``specs/foundation-health-heartbeat.md:52``): the CLIENT-side cycle drop
  ("outbound IP would not be stripped; drop heartbeat for this cycle, counters
  retained until next successful send"). Re-exported here so S10 callers map to
  it without reaching across packages.
- ``OHTTPRelayDownError`` (THIS module — ``specs/foundation-ops.md:108``): the
  Foundation-ops / queue-locally path ("OHTTP relay unreachable; Heartbeat /
  remote-time-anchor cannot deliver → pause Heartbeat send; queue locally up to
  retention bound; auto with backoff"). This is the queue-and-backoff signal,
  NOT the single-cycle drop.

The TLS / SNI / Tor errors are the network-security endpoint-hardening failures
(``specs/network-security.md`` §15/§24/§49) every Foundation OHTTP endpoint
enforces.
"""

from __future__ import annotations

# Re-export the heartbeat-side relay error so an S10 caller can map both
# distinct relay failures from one import surface. The client cycle-drop error
# is OWNED by the heartbeat taxonomy (no new exception class is introduced for
# it here — `rules/orphan-detection.md` Rule 3 / milestone "no new exception
# classes" for the client surface).
from envoy.heartbeat.errors import OHTTPRelayUnavailableError

__all__ = [
    "FoundationOpsError",
    "OHTTPRelayDownError",
    "OHTTPRelayUnavailableError",
    "TLSVersionTooLowError",
    "SNIStrippingDetectedError",
    "TorRouteUnavailableError",
    "KeyConfigSignatureError",
    "KeyConfigExpiredError",
]


class FoundationOpsError(Exception):
    """Base for every Foundation-ops (S10) server-side error.

    Lets consumers ``except FoundationOpsError`` without enumerating the
    taxonomy, matching the convention in sibling envoy packages
    (``envoy.registry.errors.LibraryError``, ``envoy.heartbeat.errors.HeartbeatError``).
    """


class OHTTPRelayDownError(FoundationOpsError):
    """OHTTP relay unreachable; Heartbeat / remote-time-anchor cannot deliver.

    ``specs/foundation-ops.md:108``. User action: pause Heartbeat send; queue
    locally up to the retention bound. Retry: auto with backoff. Distinct from
    the heartbeat-side ``OHTTPRelayUnavailableError`` (single-cycle drop): this
    is the queue-locally-with-backoff path the Foundation-ops layer surfaces.
    """


class TLSVersionTooLowError(FoundationOpsError):
    """Outbound Foundation endpoint negotiated TLS < 1.3.

    ``specs/network-security.md:15,43``. User action: refuse connection; surface
    "endpoint does not support TLS 1.3". Never auto-retry (structural).
    """


class SNIStrippingDetectedError(FoundationOpsError):
    """Strict-SNI mode: handshake completed without SNI or with a mismatched SNI.

    ``specs/network-security.md:24,45``. User action: refuse connection;
    investigate intermediary stripping intent. Never auto-retry (security event).
    """


class TorRouteUnavailableError(FoundationOpsError):
    """Phase 02+ Tor route explicitly requested but the Tor daemon is unreachable.

    ``specs/network-security.md:49``. Surfaces ONLY when Tor was explicitly
    requested per-traffic-class (default is OHTTP-only, Tor opt-in OFF —
    ``network-security.md:77`` item 4 resolved to opt-in). User action: surface
    fallback choice (refuse vs direct); user picks per-traffic-class.
    """


class KeyConfigSignatureError(FoundationOpsError):
    """A published OHTTP key config failed the 2-of-N steward-quorum verify.

    ``specs/foundation-ops.md:79`` — the key config is an operator-signed
    (Ed25519, 2-of-N steward) artifact. A config presented with fewer than 2
    valid distinct steward signatures is rejected by the verifying client path.
    """


class KeyConfigExpiredError(FoundationOpsError):
    """A fetched OHTTP key config is past its ``expires_at`` rotation deadline.

    The published key registry carries expiry/rotation metadata; a config the
    client fetches AFTER its expiry MUST be refused so S11's client never
    encapsulates under a rotated-out key.
    """
