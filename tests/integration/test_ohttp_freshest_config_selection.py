# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S11.9 — key_config(key_id=None) selects the freshest NON-EXPIRED config.

When the client fetches a key config WITHOUT pinning a key_id, the server
SHOULD select the latest non-expired config by ``expires_at`` — NOT the
numerically-highest key_id (a higher key_id is not necessarily the freshest
config). Tier-2 per `rules/testing.md`: drives the REAL Key Config Server
handler, no mocks. This is an availability/hygiene change (the client re-verifies
quorum + expiry regardless), folded into S11 per the queued S10 deferral.
"""

from __future__ import annotations

from envoy.foundation_ops.hpke import OhttpHpkeKeyConfig, generate_keypair
from envoy.foundation_ops.ohttp_server import OhttpKeyConfigServerHandlers


def _config(key_id: int, expires_at: str) -> OhttpHpkeKeyConfig:
    _priv, pub = generate_keypair()
    return OhttpHpkeKeyConfig(key_id=key_id, public_key=pub, expires_at=expires_at)


class TestFreshestConfigSelection:
    def test_unpinned_fetch_selects_latest_expiry_not_highest_key_id(self) -> None:
        """key_id=None picks the config with the FURTHEST expiry, not the max key_id."""
        server = OhttpKeyConfigServerHandlers()
        # key_id=1 expires LATER than key_id=2 — the higher key_id is the OLDER config.
        server.publish_config(_config(1, "2099-01-01T00:00:00+00:00"))
        server.publish_config(_config(2, "2030-01-01T00:00:00+00:00"))

        wire = server.key_config(key_id=None)
        assert wire is not None
        # Freshest by expiry is key_id=1, NOT the numerically-highest key_id=2.
        assert wire["key_id"] == 1
        assert wire["expires_at"] == "2099-01-01T00:00:00+00:00"

    def test_unpinned_fetch_breaks_expiry_ties_on_higher_key_id(self) -> None:
        """Equal expiry → deterministic tiebreak on the higher key_id."""
        server = OhttpKeyConfigServerHandlers()
        server.publish_config(_config(3, "2099-01-01T00:00:00+00:00"))
        server.publish_config(_config(7, "2099-01-01T00:00:00+00:00"))
        wire = server.key_config(key_id=None)
        assert wire is not None
        assert wire["key_id"] == 7

    def test_pinned_fetch_unchanged(self) -> None:
        """A pinned key_id still returns exactly that config (selection only affects None)."""
        server = OhttpKeyConfigServerHandlers()
        server.publish_config(_config(1, "2099-01-01T00:00:00+00:00"))
        server.publish_config(_config(2, "2030-01-01T00:00:00+00:00"))
        wire = server.key_config(key_id=2)
        assert wire is not None
        assert wire["key_id"] == 2

    def test_empty_registry_returns_none(self) -> None:
        server = OhttpKeyConfigServerHandlers()
        assert server.key_config(key_id=None) is None
