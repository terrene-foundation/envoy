# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Foundation registry handshake — aggregator endpoint + operator signature (S11).

The client-side counterpart to S10's Key Configuration Server. Before the
client encapsulates a weekly heartbeat it MUST:

1. Discover the STAR/Prio aggregator endpoint (`specs/foundation-ops.md`
   registry #5 — Foundation-operated aggregator gateway).
2. Verify the published key config carries a valid 2-of-N steward operator
   signature over the canonical config bytes — BEFORE trusting the public key it
   will encapsulate under.

Both gate :meth:`OhttpClient.encapsulate_request` (S10's
``encapsulate_to_config``): a tampered or expired config is rejected here, at
``verify_operator_signature`` / ``fetch_key_configuration``, so the client never
seals a payload for an unverified recipient. Signature verification delegates to
the SHARED ``verify_steward_quorum`` primitive (`envoy.registry.steward_quorum`)
— S11 does NOT grow a parallel quorum verifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from envoy.foundation_ops.hpke import OhttpHpkeKeyConfig, verify_key_config_signatures


@dataclass(frozen=True, slots=True)
class AggregatorEndpoint:
    """The discovered STAR aggregator gateway + the OHTTP relay it routes through.

    ``relay_handler`` is the relay surface the encapsulated request POSTs to
    (S10's ``ohttp.relay``); ``aggregator_label`` names the Foundation-operated
    aggregator registry entry (`specs/foundation-ops.md` registry #5).
    """

    aggregator_label: str
    relay_endpoint: str


@dataclass(slots=True)
class HeartbeatRegistryClient:
    """Client-side Foundation registry handshake for the heartbeat path.

    Holds the client-pinned Foundation steward public keys + the cached
    revocation list (the trust anchor — the transport is untrusted). The
    ``key_manager`` is a kailash ``InMemoryKeyManager`` (or any object exposing
    the async ``verify`` surface) used to check the Ed25519 steward signatures.
    """

    pinned_steward_pubkeys: list[str] = field(default_factory=list)
    revocation_list: list[str] = field(default_factory=list)
    key_manager: object | None = None
    steward_threshold: int = 2

    def fetch_aggregator_endpoint(
        self, *, aggregator_label: str, relay_endpoint: str
    ) -> AggregatorEndpoint:
        """Discover the STAR aggregator gateway + its OHTTP relay endpoint.

        The Foundation publishes the aggregator registry (`foundation-ops.md`
        registry #5); the client resolves the labelled aggregator to the relay
        endpoint it POSTs encapsulated requests to. Returns a frozen
        :class:`AggregatorEndpoint`.

        Raises:
            ValueError: an empty label or endpoint (a degenerate handshake the
                client must not proceed past).
        """
        if not aggregator_label:
            raise ValueError("aggregator_label is empty; cannot resolve the STAR aggregator")
        if not relay_endpoint:
            raise ValueError("relay_endpoint is empty; cannot route the encapsulated request")
        return AggregatorEndpoint(
            aggregator_label=aggregator_label, relay_endpoint=relay_endpoint
        )

    async def verify_operator_signature(self, config: OhttpHpkeKeyConfig) -> bool:
        """Verify the 2-of-N steward operator signature over the key config.

        Delegates to the SHARED ``verify_key_config_signatures`` primitive
        (which itself routes through ``verify_steward_quorum``). Returns True
        only when ``>= steward_threshold`` distinct pinned, non-revoked stewards
        validly signed the canonical config bytes; raises
        ``KeyConfigSignatureError`` otherwise (never fails open).

        Raises:
            ValueError: no ``key_manager`` was supplied (the client cannot
                verify Ed25519 signatures without one — fail-closed, not a
                silent "trust the transport").
        """
        if self.key_manager is None:
            raise ValueError(
                "HeartbeatRegistryClient has no key_manager; cannot verify the "
                "operator signature — refusing to trust an unverified key config"
            )
        return await verify_key_config_signatures(
            config,
            threshold=self.steward_threshold,
            pinned_pubkeys=self.pinned_steward_pubkeys,
            revocation_list=self.revocation_list,
            key_manager=self.key_manager,
        )


__all__ = [
    "AggregatorEndpoint",
    "HeartbeatRegistryClient",
]
