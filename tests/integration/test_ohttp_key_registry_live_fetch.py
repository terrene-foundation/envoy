# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S10.5 — live read against the published key-registry endpoint.

The Key Configuration Server is the `gh api`-equivalent live receipt S11's
client MUST existence-check before debugging access
(`rules/verify-resource-existence.md` MUST-2). A live read returns a
signature-valid, non-expired key config. This Tier-2 test drives the REAL
Key Config Server handler through the REAL Nexus-registered handler (the same
callable Nexus exposes over HTTP/CLI/MCP) — not a mock.
"""

from __future__ import annotations

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.foundation_ops.errors import KeyConfigExpiredError
from envoy.foundation_ops.hpke import (
    OhttpHpkeKeyConfig,
    encode_key_config,
    generate_keypair,
    key_config_content_hash,
    verify_key_config_signatures,
)
from envoy.foundation_ops.ohttp_server import (
    OhttpKeyConfigServerHandlers,
    OhttpRelayHandlers,
    build_ohttp_nexus,
)


async def _steward(km: InMemoryKeyManager, key_id: str, ch: str) -> tuple[str, str]:
    _priv, pub = await km.generate_keypair(key_id)
    return pub, km.sign_with_key(key_id, ch.encode("utf-8"))


@pytest.fixture
def build_nexus():  # type: ignore[no-untyped-def]
    """Build OHTTP Nexus apps and close every one at teardown — a Nexus binds
    transport resources, so an unclosed app leaks sockets (ResourceWarning).
    Teardown runs even when an assertion fails mid-test."""
    apps = []

    def _build(*args, **kwargs):  # type: ignore[no-untyped-def]
        app = build_ohttp_nexus(*args, **kwargs)
        apps.append(app)
        return app

    yield _build
    for app in apps:
        app.close()


class TestKeyRegistryLiveFetch:
    async def _publish_signed(
        self, server: OhttpKeyConfigServerHandlers, expires_at: str
    ) -> tuple[OhttpHpkeKeyConfig, InMemoryKeyManager, list[str]]:
        _priv, pub = generate_keypair()
        config = OhttpHpkeKeyConfig(key_id=11, public_key=pub, expires_at=expires_at)
        km = InMemoryKeyManager()
        ch = key_config_content_hash(config)
        pub_a, sig_a = await _steward(km, "steward-a", ch)
        pub_b, sig_b = await _steward(km, "steward-b", ch)
        config.steward_signatures = [
            {"steward_pubkey_hex": pub_a, "signature_hex": sig_a},
            {"steward_pubkey_hex": pub_b, "signature_hex": sig_b},
        ]
        server.publish_config(config)
        return config, km, [pub_a, pub_b]

    async def test_live_fetch_returns_signature_valid_nonexpired_config(self, build_nexus) -> None:
        server = OhttpKeyConfigServerHandlers()
        config, km, pinned = await self._publish_signed(
            server, expires_at="2099-01-01T00:00:00+00:00"
        )
        # Wire through the REAL Nexus-registered handler.
        relay = OhttpRelayHandlers()
        app = build_nexus(server, relay, api_port=18950, mcp_port=18951)
        handler = app._handler_registry["ohttp.key_config"]["handler"]

        wire = handler(key_id=11)
        assert wire is not None
        # The fetched wire form re-encodes to the exact signed bytes.
        rebuilt = OhttpHpkeKeyConfig(
            key_id=wire["key_id"],
            public_key=bytes.fromhex(wire["public_key_hex"]),
            expires_at=wire["expires_at"],
            steward_signatures=wire["steward_signatures"],
        )
        assert encode_key_config(rebuilt) == encode_key_config(config)
        # Signature-valid: the 2-of-N quorum re-verifies against pinned keys.
        assert await verify_key_config_signatures(
            rebuilt,
            threshold=2,
            pinned_pubkeys=pinned,
            revocation_list=[],
            key_manager=km,
        )
        # Non-expired.
        assert server.assert_not_expired(key_id=11) is True

    async def test_empty_registry_returns_none(self, build_nexus) -> None:
        server = OhttpKeyConfigServerHandlers()
        relay = OhttpRelayHandlers()
        app = build_nexus(server, relay, api_port=18952, mcp_port=18953)
        handler = app._handler_registry["ohttp.key_config"]["handler"]
        # Existence check against an unprovisioned registry returns None — the
        # client maps this to the existence-check-failed path, NOT a 403 loop.
        assert handler(key_id=99) is None

    async def test_expired_config_refused(self) -> None:
        server = OhttpKeyConfigServerHandlers(now_iso=lambda: "2030-01-01T00:00:00+00:00")
        await self._publish_signed(server, expires_at="2025-01-01T00:00:00+00:00")
        with pytest.raises(KeyConfigExpiredError):
            server.assert_not_expired(key_id=11)
