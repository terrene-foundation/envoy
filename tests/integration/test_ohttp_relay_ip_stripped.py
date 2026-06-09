# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S10.2 — OHTTP relay strips the source IP; aggregator never sees it.

Tier-2 per `rules/testing.md`: drives the REAL `OhttpRelayHandlers` against a
REAL in-process aggregator gateway (a deterministic forward function satisfying
the `AggregatorGateway` contract — NOT a mock per the Protocol-Adapter
carve-out). The non-collusion split is asserted on BOTH axes:

- the aggregator never observes the originating source IP (relay stripped it);
- the relay never observes the plaintext body (it forwards opaque enc||ct and
  holds no HPKE private key).
"""

from __future__ import annotations

import pytest

from envoy.foundation_ops.hpke import (
    OhttpHpkeKeyConfig,
    decapsulate_request,
    encapsulate_to_config,
    generate_keypair,
)
from envoy.foundation_ops.ohttp_server import OhttpRelayHandlers


class _AggregatorGatewaySpy:
    """A real in-process STAR aggregator gateway target.

    Records every argument it is invoked with so the test can assert the relay
    forwarded ONLY the encapsulated bytes — no source IP, no plaintext. Holds
    the HPKE private key (the aggregator IS the recipient) and decapsulates, so
    the test can confirm the body round-trips while the relay never decrypts.
    """

    def __init__(self, config: OhttpHpkeKeyConfig, private_key: bytes) -> None:
        self._config = config
        self._private_key = private_key
        self.received_payloads: list[bytes] = []
        self.recovered_plaintext: bytes | None = None

    async def __call__(self, encapsulated: bytes) -> bytes:
        self.received_payloads.append(encapsulated)
        # The aggregator (recipient) decapsulates — proving the body survived
        # the relay opaque-forward. The relay itself never does this.
        self.recovered_plaintext = decapsulate_request(
            self._config, self._private_key, encapsulated
        )
        # Produce an (encapsulated) response — for the test, echo a fixed ack.
        return b"\x00" * 32 + b"AGG-ACK"


@pytest.fixture
def hpke() -> tuple[OhttpHpkeKeyConfig, bytes]:
    priv, pub = generate_keypair()
    config = OhttpHpkeKeyConfig(key_id=3, public_key=pub, expires_at="2099-01-01T00:00:00+00:00")
    return config, priv


class TestRelayIpStrip:
    async def test_aggregator_never_sees_source_ip(
        self, hpke: tuple[OhttpHpkeKeyConfig, bytes]
    ) -> None:
        config, priv = hpke
        gateway = _AggregatorGatewaySpy(config, priv)
        relay = OhttpRelayHandlers(aggregator=gateway)

        plaintext = b'{"flags": 21, "shares": "..."}'
        encapsulated = encapsulate_to_config(config, plaintext)

        await relay.relay(
            encapsulated_request_hex=encapsulated.hex(),
            source_ip="203.0.113.42",  # client IP the transport observed
        )

        # Axis 1: the aggregator received ONLY the encapsulated bytes.
        assert gateway.received_payloads == [encapsulated]
        # The source IP never reached the aggregator (the spy records every
        # arg; it has no source-IP parameter — the relay never forwarded it).
        assert relay.last_observation is not None
        assert relay.last_observation.aggregator_saw_source_ip is False

    async def test_relay_never_sees_plaintext(self, hpke: tuple[OhttpHpkeKeyConfig, bytes]) -> None:
        config, priv = hpke
        gateway = _AggregatorGatewaySpy(config, priv)
        relay = OhttpRelayHandlers(aggregator=gateway)

        plaintext = b'{"flags": 21}'
        encapsulated = encapsulate_to_config(config, plaintext)
        await relay.relay(encapsulated_request_hex=encapsulated.hex(), source_ip="198.51.100.7")

        # Axis 2: the relay forwarded opaque enc||ct; the aggregator (holding
        # the key) recovered the plaintext — proving the relay itself never did.
        assert relay.last_observation is not None
        assert relay.last_observation.relay_saw_plaintext is False
        assert gateway.recovered_plaintext == plaintext

    async def test_response_relays_back(self, hpke: tuple[OhttpHpkeKeyConfig, bytes]) -> None:
        config, priv = hpke
        gateway = _AggregatorGatewaySpy(config, priv)
        relay = OhttpRelayHandlers(aggregator=gateway)
        encapsulated = encapsulate_to_config(config, b"x")
        out = await relay.relay(encapsulated_request_hex=encapsulated.hex())
        assert "encapsulated_response_hex" in out
        assert bytes.fromhex(out["encapsulated_response_hex"]).endswith(b"AGG-ACK")
