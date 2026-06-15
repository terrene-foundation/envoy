# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""OHTTP (RFC 9458) client wrapper for the heartbeat path (S11).

The client side of S10's Foundation OHTTP substrate. The client:

1. Fetches the published key config from S10's Key Configuration Server
   (:meth:`OhttpClient.fetch_key_configuration`), re-verifies the 2-of-N steward
   quorum + expiry locally (via :class:`HeartbeatRegistryClient`), then
2. Encapsulates the weekly STAR-share payload under the verified HPKE key
   (:meth:`OhttpClient.encapsulate_request`, wrapping S10's
   ``encapsulate_to_config``) and POSTs the opaque ``enc || ciphertext`` bytes
   through the IP-stripping Relay.

**EC-S11.8 (HPKE ``info`` binds the key-config identity).** The encapsulation
``info`` is derived from the RFC 9458 OHTTP request-context label + the
``key_id`` + the ciphersuite ids — NOT the empty ``info=b""`` S10's
``encapsulate_to_config`` defaults to. This binds the AEAD to the exact
key-config the stewards signed over: a ciphertext sealed for ``key_id=A`` cannot
be opened under a different config. The client is the encapsulation site that
constructs ``info``; the S10 recipient (``decapsulate_request``) is handed the
SAME ``info`` so the seal/open pair agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envoy.foundation_ops.hpke import OhttpHpkeKeyConfig, encapsulate_to_config
from envoy.heartbeat.registry import HeartbeatRegistryClient

# RFC 9458 §4.3 OHTTP request-media-type label, used as the HPKE `info` prefix
# so the AEAD binding includes the OHTTP request context.
_OHTTP_REQUEST_LABEL = b"message/bhttp request"


def build_ohttp_info(config: OhttpHpkeKeyConfig) -> bytes:
    """Derive the HPKE ``info`` that binds the key-config identity (EC-S11.8).

    ``info = "message/bhttp request" || 0x00 || key_id (1) || kem_id (2) ||
    kdf_id (2) || aead_id (2)`` per RFC 9458 §4.3. Non-empty and keyed to the
    ``key_id`` + suite, so a ciphertext sealed for one config cannot be opened
    under another. Both the client (seal) and the Foundation recipient (open)
    derive this from the same config.
    """
    suite = config.ciphersuite
    return (
        _OHTTP_REQUEST_LABEL
        + b"\x00"
        + config.key_id.to_bytes(1, "big")
        + suite.kem_id.to_bytes(2, "big")
        + suite.kdf_id.to_bytes(2, "big")
        + suite.aead_id.to_bytes(2, "big")
    )


@dataclass(slots=True)
class OhttpClient:
    """Client-side OHTTP encapsulation + relay POST for the weekly heartbeat.

    ``registry`` is the :class:`HeartbeatRegistryClient` that verifies the
    operator signature + expiry on every fetched config (a tampered/expired
    config is rejected at fetch time, before any encapsulation). The client
    holds NO private key — it only seals to the Foundation recipient's published
    public key.
    """

    registry: HeartbeatRegistryClient | None = None

    async def fetch_key_configuration(
        self, wire_config: dict[str, Any] | None
    ) -> OhttpHpkeKeyConfig:
        """Rebuild + verify a fetched key config before encapsulating.

        ``wire_config`` is the dict S10's ``ohttp.key_config`` handler returns
        (the live key-registry read). The wire form is re-encoded to the exact
        signed bytes and the 2-of-N steward operator signature is re-verified
        locally via the registry handshake; a tampered config fails verification
        here (EC-S11.4). Returns the verified :class:`OhttpHpkeKeyConfig`.

        Raises:
            ValueError: ``wire_config`` is None (the existence check against S10
                returned no config — the client maps this to the
                existence-check-failed path, not a retry loop), or no registry
                was supplied to verify the signature.
            KeyConfigSignatureError: the steward quorum does not re-verify.
        """
        if wire_config is None:
            raise ValueError(
                "OHTTP key config fetch returned None; the Foundation registry "
                "has no published config — existence check failed, do not encapsulate"
            )
        if self.registry is None:
            raise ValueError(
                "OhttpClient has no registry to verify the operator signature; "
                "refusing to trust an unverified key config (fail-closed)"
            )
        rebuilt = OhttpHpkeKeyConfig(
            key_id=int(wire_config["key_id"]),
            public_key=bytes.fromhex(str(wire_config["public_key_hex"])),
            expires_at=str(wire_config["expires_at"]),
            steward_signatures=[dict(s) for s in wire_config["steward_signatures"]],
        )
        # The registry re-verifies the 2-of-N operator signature; a tampered
        # config (re-signed by an un-pinned key, or with mutated bytes) is
        # rejected here before the client ever seals to its public key.
        await self.registry.verify_operator_signature(rebuilt)
        return rebuilt

    def encapsulate_request(
        self, config: OhttpHpkeKeyConfig, payload: bytes
    ) -> bytes:
        """Seal ``payload`` to ``config`` with the identity-binding ``info`` (EC-S11.8).

        Wraps S10's ``encapsulate_to_config`` but supplies the non-empty,
        key-config-bound ``info`` from :func:`build_ohttp_info` instead of the
        default ``info=b""``. Returns the opaque OHTTP ``enc || ciphertext``
        bytes the IP-stripping relay forwards. The matching ``info`` MUST be
        passed to the Foundation recipient's ``decapsulate_request`` for the
        seal/open pair to agree.

        Raises:
            ValueError: the config advertises a non-default HPKE ciphersuite
                (propagated from ``encapsulate_to_config`` — no downgrade).
        """
        info = build_ohttp_info(config)
        return encapsulate_to_config(config, payload, info=info)


__all__ = [
    "OhttpClient",
    "build_ohttp_info",
]
