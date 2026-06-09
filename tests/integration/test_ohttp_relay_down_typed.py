# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S10.3 — relay-unreachable raises distinct typed failures.

`OHTTPRelayDownError` (`specs/foundation-ops.md:108`) is the
queue-locally-with-backoff path the Foundation-ops layer surfaces. It is
DISTINCT from `OHTTPRelayUnavailableError` (`specs/foundation-health-heartbeat.md:52`,
owned by the heartbeat client taxonomy) which is the single-cycle drop. Both
typed failures MUST assert distinctly — they are not the same class.
"""

from __future__ import annotations

import pytest

from envoy.foundation_ops.errors import (
    OHTTPRelayDownError,
    OHTTPRelayUnavailableError,
)
from envoy.foundation_ops.ohttp_server import OhttpRelayHandlers


class TestRelayDownTyped:
    async def test_unreachable_aggregator_raises_relay_down(self) -> None:
        relay = OhttpRelayHandlers(aggregator=None)  # gateway unreachable
        with pytest.raises(OHTTPRelayDownError):
            await relay.relay(encapsulated_request_hex="00" * 40)

    def test_relay_down_and_unavailable_are_distinct_classes(self) -> None:
        # EC-S10.3: the two relay-failure errors must surface distinctly.
        assert OHTTPRelayDownError is not OHTTPRelayUnavailableError
        assert not issubclass(OHTTPRelayDownError, OHTTPRelayUnavailableError)
        assert not issubclass(OHTTPRelayUnavailableError, OHTTPRelayDownError)

    async def test_malformed_encapsulated_request_rejected(self) -> None:
        async def _gateway(_b: bytes) -> bytes:
            return b""

        relay = OhttpRelayHandlers(aggregator=_gateway)
        with pytest.raises(ValueError, match="hex"):
            await relay.relay(encapsulated_request_hex="not-hex-zzz")
