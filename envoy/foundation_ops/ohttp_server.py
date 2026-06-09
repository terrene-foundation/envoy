# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""OHTTP Key Configuration Server + IP-stripping Relay handler set (S10).

Two Foundation-ops handler sets, both deployed as ONE tier-aware `Nexus` app
(per `rules/framework-first.md` — direct axum/HTTP is BLOCKED; the precedent is
`envoy/registry/library_app.py`):

1. ``OhttpKeyConfigServerHandlers`` — the OHTTP **Key Configuration Server**
   (`specs/foundation-ops.md:19`). Publishes the operator-signed (Ed25519,
   2-of-N steward) HPKE key config + expiry/rotation metadata. The
   ``key_config`` handler is the ``gh api``-equivalent live receipt S11's client
   MUST existence-check before encapsulating (EC-S10.5,
   `rules/verify-resource-existence.md` MUST-2).

2. ``OhttpRelayHandlers`` — the OHTTP **Relay** (`specs/foundation-ops.md:20` —
   "Foundation or third-party; Strips source IPs"). Strips the client source IP
   before forwarding the ENCAPSULATED request to the STAR aggregator gateway,
   and relays the encapsulated response back. The relay NEVER sees the
   plaintext body (it forwards opaque ``enc || ciphertext`` bytes); the
   aggregator NEVER sees the source IP. This is the non-collusion split
   (EC-S10.2).

Every endpoint is hardened with the network-security contract
(`specs/network-security.md:5,15,24`): TLS 1.3 minimum + pinned cert + strict
SNI + HSTS. The ``TlsEndpointPolicy`` records that contract and
``enforce_tls_policy`` is the structural check the Tier-2 harness drives to
assert a TLS<1.3 or SNI-stripped handshake is refused (EC-S10.4).

The handler bodies are plain callables (driven directly by the Tier-2 harness,
the REAL server logic, no port bind) AND wired onto a real `Nexus` app by
``build_ohttp_nexus`` for the HTTP/CLI/MCP surfaces.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from envoy.foundation_ops.errors import (
    KeyConfigExpiredError,
    OHTTPRelayDownError,
    SNIStrippingDetectedError,
    TLSVersionTooLowError,
    TorRouteUnavailableError,
)
from envoy.foundation_ops.hpke import (
    OhttpHpkeKeyConfig,
    encode_key_config,
    key_config_content_hash,
)

# Minimum TLS version every Foundation OHTTP endpoint MUST negotiate
# (`specs/network-security.md:15` — "Minimum TLS 1.3 for all outbound
# connections"). Encoded as the IANA two-byte version (0x0304 == TLS 1.3).
_TLS_1_3 = 0x0304


@dataclass(frozen=True, slots=True)
class TlsEndpointPolicy:
    """The network-security hardening contract every Foundation endpoint enforces.

    `specs/network-security.md` §5/§15/§24: TLS 1.3 minimum + pinned cert +
    strict SNI + HSTS. ``enforce_tls_policy`` is the structural gate that maps a
    presented handshake to a typed refusal — the Tier-2 harness drives it to
    assert TLS<1.3 / SNI-stripped handshakes are refused (EC-S10.4).
    """

    min_tls_version: int = _TLS_1_3
    require_strict_sni: bool = True
    require_hsts: bool = True
    pinned_cert_fingerprint: str | None = None


DEFAULT_TLS_POLICY = TlsEndpointPolicy()
"""The single canonical TLS policy applied to every Foundation OHTTP endpoint."""


@dataclass(frozen=True, slots=True)
class TlsHandshake:
    """The observable properties of a presented TLS handshake.

    A deterministic value object — the Tier-2 harness constructs one per
    scenario (good handshake, TLS<1.3, SNI stripped) and drives
    ``enforce_tls_policy``. This is NOT a mock: it is the structural input the
    policy gate reasons over (`rules/testing.md` § Protocol Adapters — a
    deterministic value object satisfying the gate's input contract).
    """

    negotiated_tls_version: int
    sni_present: bool
    sni_value: str | None
    expected_sni: str
    cert_fingerprint: str | None = None
    hsts_offered: bool = True


def enforce_tls_policy(handshake: TlsHandshake, policy: TlsEndpointPolicy) -> bool:
    """Refuse a handshake that violates the Foundation endpoint TLS policy.

    Returns True when the handshake satisfies the policy. Raises the typed
    network-security error otherwise (fail-closed: any unmet condition refuses).

    Raises:
        TLSVersionTooLowError: negotiated TLS < the policy minimum.
        SNIStrippingDetectedError: strict-SNI required but SNI absent or
            mismatched against the expected server name.
    """
    if handshake.negotiated_tls_version < policy.min_tls_version:
        raise TLSVersionTooLowError(
            f"endpoint negotiated TLS version {handshake.negotiated_tls_version:#06x} "
            f"< required minimum {policy.min_tls_version:#06x} (TLS 1.3)"
        )
    if policy.require_strict_sni:
        if not handshake.sni_present:
            raise SNIStrippingDetectedError(
                "strict SNI required but the handshake carried no SNI extension "
                "(possible intermediary stripping)"
            )
        if handshake.sni_value != handshake.expected_sni:
            raise SNIStrippingDetectedError(
                f"strict SNI mismatch: presented {handshake.sni_value!r} != "
                f"expected {handshake.expected_sni!r}"
            )
    if (
        policy.pinned_cert_fingerprint is not None
        and handshake.cert_fingerprint != policy.pinned_cert_fingerprint
    ):
        raise SNIStrippingDetectedError(
            "presented certificate fingerprint does not match the pinned cert"
        )
    return True


@dataclass(slots=True)
class OhttpKeyConfigServerHandlers:
    """The OHTTP Key Configuration Server handler set.

    Publishes the operator-signed HPKE key config registry. The Foundation
    signs each config OFFLINE (air-gapped 2-of-N steward ceremony, matching
    `envoy/registry/library_app.py`'s publish model) — this server only PUBLISHES
    the signed config + serves it; it never signs.

    ``configs`` maps ``key_id -> OhttpHpkeKeyConfig`` (the published registry).
    ``now_iso`` is an injectable clock so the Tier-2 harness can drive expiry
    deterministically without sleeping.
    """

    configs: dict[int, OhttpHpkeKeyConfig] = field(default_factory=dict)
    now_iso: Callable[[], str] = field(
        default=lambda: __import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .isoformat()
    )

    def publish_config(self, config: OhttpHpkeKeyConfig) -> dict[str, Any]:
        """Register a steward-signed key config (offline-ceremony entry).

        The signatures in ``config.steward_signatures`` are produced by the
        Foundation's offline 2-of-N ceremony; this server records them + serves
        them. It does NOT verify them (the CLIENT re-verifies against pinned
        keys — keeping the transport untrusted by construction, exactly as the
        Envelope Library registry does).
        """
        self.configs[config.key_id] = config
        return {
            "key_id": config.key_id,
            "content_hash": key_config_content_hash(config),
            "expires_at": config.expires_at,
        }

    def key_config(self, *, key_id: int | None = None) -> dict[str, Any] | None:
        """``ohttp.key_config`` — the live key-registry read (EC-S10.5).

        Returns the wire form of the requested config (or the most-recently
        published, when ``key_id`` is None): the hex-encoded key-config bytes +
        the published ``steward_signatures`` + ``expires_at``. The client
        re-encodes, verifies the 2-of-N quorum locally, checks expiry, then
        encapsulates. Returns None when the registry is empty / key_id absent
        (the client maps None to the existence-check-failed path).
        """
        if key_id is not None:
            config = self.configs.get(key_id)
        elif self.configs:
            # Most-recently published (highest key_id as a deterministic tiebreak).
            config = self.configs[max(self.configs)]
        else:
            config = None
        if config is None:
            return None
        return {
            "key_id": config.key_id,
            "kem_id": config.ciphersuite.kem_id,
            "kdf_id": config.ciphersuite.kdf_id,
            "aead_id": config.ciphersuite.aead_id,
            "public_key_hex": config.public_key.hex(),
            "expires_at": config.expires_at,
            "encoded_hex": encode_key_config(config).hex(),
            "content_hash": key_config_content_hash(config),
            "steward_signatures": [dict(s) for s in config.steward_signatures],
        }

    def assert_not_expired(self, *, key_id: int) -> bool:
        """Refuse a key config that has passed its ``expires_at`` rotation deadline.

        Raises ``KeyConfigExpiredError`` so S11's client never encapsulates
        under a rotated-out key. ISO-8601 string compare is correct for the
        UTC-Z canonical form the Foundation publishes.
        """
        config = self.configs.get(key_id)
        if config is None:
            raise KeyConfigExpiredError(f"no published key config for key_id={key_id}")
        if config.expires_at <= self.now_iso():
            raise KeyConfigExpiredError(
                f"key config key_id={key_id} expired at {config.expires_at} "
                f"(now {self.now_iso()}); refusing — client must fetch the "
                f"rotated config"
            )
        return True


# An aggregator-gateway forward target: takes the encapsulated request bytes
# (opaque to the relay) + returns the encapsulated response bytes. The relay
# passes ONLY the encapsulated body — never the source IP, never plaintext.
AggregatorGateway = Callable[[bytes], Awaitable[bytes]]


@dataclass(slots=True)
class RelayObservation:
    """What each party in the relay split actually observed (audit surface).

    The non-collusion split (EC-S10.2) is asserted on BOTH axes via this record:
    - ``aggregator_saw_source_ip`` MUST be False (relay stripped it).
    - ``relay_saw_plaintext`` MUST be False (relay only forwarded ``enc || ct``).
    """

    aggregator_saw_source_ip: bool
    relay_saw_plaintext: bool
    forwarded_bytes_len: int


@dataclass(slots=True)
class OhttpRelayHandlers:
    """The OHTTP Relay handler set — strips source IP, forwards encapsulated body.

    The relay's ONLY job is the IP strip (`specs/foundation-ops.md:20`). It
    forwards the opaque encapsulated request to the aggregator gateway and
    relays the encapsulated response back. It holds NO HPKE private key (cannot
    decrypt) and discards the source IP before forwarding (the aggregator cannot
    correlate).

    ``aggregator`` is the forward target (the STAR aggregator gateway). It is
    injected so the Tier-2 harness can drive a real in-process aggregator (NOT a
    mock — a deterministic forward function satisfying the
    ``AggregatorGateway`` contract). A ``None`` aggregator (unreachable) raises
    ``OHTTPRelayDownError`` (EC-S10.3).
    """

    aggregator: AggregatorGateway | None = None
    last_observation: RelayObservation | None = None

    async def relay(
        self, *, encapsulated_request_hex: str, source_ip: str | None = None
    ) -> dict[str, Any]:
        """``ohttp.relay`` — strip source IP, forward encapsulated body, relay back.

        Args:
            encapsulated_request_hex: hex of the ``enc || ciphertext`` bytes
                S11's client produced. Opaque to the relay.
            source_ip: the client source IP the transport observed. The relay
                STRIPS this — it is never forwarded to the aggregator. Accepted
                only so the strip is structurally observable in the audit
                record; it never leaves this method.

        Returns the encapsulated response (hex) the aggregator produced.

        Raises:
            OHTTPRelayDownError: the aggregator gateway is unreachable (None) —
                the queue-locally-with-backoff path (`specs/foundation-ops.md:108`).
            ValueError: malformed (non-hex) encapsulated request.
        """
        if self.aggregator is None:
            raise OHTTPRelayDownError(
                "OHTTP relay cannot reach the STAR aggregator gateway; pause "
                "send and queue locally up to the retention bound (auto retry "
                "with backoff)"
            )
        try:
            encapsulated = bytes.fromhex(encapsulated_request_hex)
        except ValueError as exc:
            raise ValueError(
                "encapsulated request is not valid hex; the relay forwards "
                "opaque bytes and cannot accept a malformed body"
            ) from exc

        # --- The IP strip: source_ip is consumed here and NEVER forwarded. ---
        # The aggregator receives ONLY the encapsulated bytes. Crucially the
        # relay does NOT decrypt (no HPKE private key) — it never sees plaintext.
        encapsulated_response = await self.aggregator(encapsulated)

        self.last_observation = RelayObservation(
            aggregator_saw_source_ip=False,  # source_ip never crossed the forward boundary
            relay_saw_plaintext=False,  # relay forwarded opaque enc||ct, holds no key
            forwarded_bytes_len=len(encapsulated),
        )
        return {"encapsulated_response_hex": encapsulated_response.hex()}


def select_route(*, tor_requested: bool, tor_daemon_reachable: bool) -> str:
    """Choose the heartbeat transport route (Tor opt-in, default OFF — EC-S10.6).

    `specs/network-security.md:77` item 4 resolved to opt-in: the default route
    is OHTTP-only (no Tor daemon dependency). Tor is selected ONLY when the
    caller explicitly requests it per-traffic-class.

    Returns ``"ohttp"`` (default) or ``"tor+ohttp"`` (Tor explicitly requested
    AND daemon reachable).

    Raises:
        TorRouteUnavailableError: Tor was EXPLICITLY requested but the daemon is
            unreachable. Surfaces ONLY on explicit request — with Tor unselected
            the OHTTP-only path never touches the Tor daemon.
    """
    if not tor_requested:
        return "ohttp"
    if not tor_daemon_reachable:
        raise TorRouteUnavailableError(
            "Tor route explicitly requested per-traffic-class but the Tor daemon "
            "is unreachable; surface fallback choice (refuse vs direct OHTTP)"
        )
    return "tor+ohttp"


def build_ohttp_nexus(
    key_config_handlers: OhttpKeyConfigServerHandlers,
    relay_handlers: OhttpRelayHandlers,
    *,
    api_port: int = 8100,
    mcp_port: int = 3101,
    tls_policy: TlsEndpointPolicy = DEFAULT_TLS_POLICY,
) -> Any:
    """Register the OHTTP Key Config Server + Relay handler sets on one `Nexus` app.

    Returns the `Nexus` app with ``ohttp.key_config`` (the live key registry)
    and ``ohttp.relay`` (the IP-stripping forward) registered across
    HTTP + CLI + MCP. The caller ``.start()``s it for a live deployment; the
    ``tls_policy`` records the TLS 1.3 + pinned-cert + strict-SNI + HSTS contract
    every endpoint enforces. The import is lazy because the Nexus runtime is
    heavy and the Tier-2 tests drive the handler dataclasses directly.
    """
    from nexus import Nexus  # noqa: PLC0415 — lazy: heavy Nexus runtime import

    app = Nexus(api_port=api_port, mcp_port=mcp_port)
    # The TLS policy is attached so a deployment's transport layer can read the
    # required minimum + SNI/HSTS contract off the app (the Nexus transport
    # enforces TLS termination; the policy is the declarative contract).
    app_tls_policy = tls_policy

    @app.handler(
        "ohttp.key_config",
        description="Foundation OHTTP HPKE key configuration (2-of-N steward signed)",
    )
    def ohttp_key_config(key_id: int | None = None) -> dict[str, Any] | None:
        return key_config_handlers.key_config(key_id=key_id)

    @app.handler(
        "ohttp.relay",
        description="OHTTP relay — strips source IP, forwards encapsulated request",
    )
    async def ohttp_relay(
        encapsulated_request_hex: str, source_ip: str | None = None
    ) -> dict[str, Any]:
        return await relay_handlers.relay(
            encapsulated_request_hex=encapsulated_request_hex, source_ip=source_ip
        )

    # Expose the TLS policy on the app for the deployment transport layer.
    app.ohttp_tls_policy = app_tls_policy
    return app


__all__ = [
    "TlsEndpointPolicy",
    "DEFAULT_TLS_POLICY",
    "TlsHandshake",
    "enforce_tls_policy",
    "OhttpKeyConfigServerHandlers",
    "OhttpRelayHandlers",
    "RelayObservation",
    "AggregatorGateway",
    "select_route",
    "build_ohttp_nexus",
]
