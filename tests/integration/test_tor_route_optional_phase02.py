# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S10.6 — Tor route is opt-in, default OFF.

`specs/network-security.md:77` item 4 resolved to opt-in: with Tor unselected
the heartbeat path uses OHTTP-only (no Tor daemon dependency).
`TorRouteUnavailableError` (`network-security.md:49`) surfaces ONLY when Tor was
explicitly requested AND the daemon is unreachable. Default-on is NOT shipped.
"""

from __future__ import annotations

import pytest

from envoy.foundation_ops.errors import TorRouteUnavailableError
from envoy.foundation_ops.ohttp_server import select_route


class TestTorRouteOptional:
    def test_default_route_is_ohttp_only_no_tor_dependency(self) -> None:
        # Tor unselected → OHTTP-only; the Tor daemon is never touched, so its
        # reachability is irrelevant (no TorRouteUnavailableError even when down).
        assert select_route(tor_requested=False, tor_daemon_reachable=False) == "ohttp"
        assert select_route(tor_requested=False, tor_daemon_reachable=True) == "ohttp"

    def test_tor_selected_and_reachable_uses_tor(self) -> None:
        assert select_route(tor_requested=True, tor_daemon_reachable=True) == "tor+ohttp"

    def test_tor_requested_but_daemon_down_raises(self) -> None:
        with pytest.raises(TorRouteUnavailableError):
            select_route(tor_requested=True, tor_daemon_reachable=False)
