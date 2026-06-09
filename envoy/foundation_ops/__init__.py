# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.foundation_ops — Foundation-operated server infrastructure (Phase 02 WS-5, shard S10).

S10 stands up the **server-side** Foundation Health Heartbeat substrate: the
OHTTP (RFC 9458) Key Configuration Server + the IP-stripping Relay. This is
Foundation-ops infrastructure — NOT client crypto. The client side
(`envoy/heartbeat/ohttp.py` + `registry.py`) is S11's domain and
existence-checks THIS server before wiring (`rules/verify-resource-existence.md`
MUST-2). Per the WS-5 deep-dive: "WS-5's first concrete deliverable is
Foundation-ops infrastructure, not client code."

Per `rules/framework-first.md`, the Key Config Server + Relay are ONE
`Nexus` handler set — NOT hand-written axum/HTTP routes (direct framework use
is BLOCKED). The precedent is `envoy/registry/library_app.py` (the Envelope
Library Foundation-ops server): a plain-callable `Handlers` dataclass driven
directly by the Tier-2 harness + a `build_*_nexus()` that wires the same
callables onto a real `Nexus` app across HTTP/CLI/MCP.

Surface:

- ``OhttpHpkeKeyConfig`` / ``RFC9458_CIPHERSUITE`` — the fixed HPKE ciphersuite
  (`DHKEM(X25519, HKDF-SHA256) + HKDF-SHA256 + AES-128-GCM`) + the
  operator-signed key-config encoding S11's client encapsulates under.
- ``encode_key_config`` / ``encapsulate_to_config`` / ``decapsulate_request`` —
  the RFC-9458 key-config wire encoding + HPKE seal/open primitives.
- ``OhttpKeyConfigServerHandlers`` — the Key Configuration Server handler set
  (publishes the 2-of-N-steward-signed key registry; expiry/rotation metadata).
- ``OhttpRelayHandlers`` — the IP-stripping Relay handler set (strips source IP
  before forwarding the encapsulated request to the aggregator gateway; relays
  the encapsulated response back; never observes the plaintext body).
- ``build_ohttp_nexus`` — wires both handler sets onto one tier-aware `Nexus`
  app with TLS 1.3 + cert pinning + strict SNI + HSTS on every endpoint.
- The server-side error taxonomy (`errors.py`): `OHTTPRelayDownError`
  (`specs/foundation-ops.md:108`), TLS/SNI/Tor failures
  (`specs/network-security.md`).
"""

from __future__ import annotations

from envoy.foundation_ops.errors import (
    FoundationOpsError,
    OHTTPRelayDownError,
    SNIStrippingDetectedError,
    TLSVersionTooLowError,
    TorRouteUnavailableError,
)
from envoy.foundation_ops.hpke import (
    RFC9458_CIPHERSUITE,
    HpkeCiphersuite,
    OhttpHpkeKeyConfig,
    decapsulate_request,
    encapsulate_to_config,
    encode_key_config,
    generate_keypair,
    verify_key_config_signatures,
)
from envoy.foundation_ops.ohttp_server import (
    DEFAULT_TLS_POLICY,
    AggregatorGateway,
    OhttpKeyConfigServerHandlers,
    OhttpRelayHandlers,
    RelayObservation,
    TlsEndpointPolicy,
    TlsHandshake,
    build_ohttp_nexus,
    enforce_tls_policy,
    select_route,
)

__all__ = [
    # HPKE ciphersuite + key config.
    "RFC9458_CIPHERSUITE",
    "HpkeCiphersuite",
    "OhttpHpkeKeyConfig",
    "encode_key_config",
    "encapsulate_to_config",
    "decapsulate_request",
    "generate_keypair",
    "verify_key_config_signatures",
    # Server handler sets.
    "OhttpKeyConfigServerHandlers",
    "OhttpRelayHandlers",
    "build_ohttp_nexus",
    "TlsEndpointPolicy",
    "DEFAULT_TLS_POLICY",
    "TlsHandshake",
    "enforce_tls_policy",
    "RelayObservation",
    "AggregatorGateway",
    "select_route",
    # Server-side error taxonomy.
    "FoundationOpsError",
    "OHTTPRelayDownError",
    "TLSVersionTooLowError",
    "SNIStrippingDetectedError",
    "TorRouteUnavailableError",
]
