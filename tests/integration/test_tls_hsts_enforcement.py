# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""F1 — HSTS is consumed by enforce_tls_policy (was DEAD config).

`specs/network-security.md:24` mandates "Strict SNI + HSTS for all outbound
HTTPS"; the error taxonomy (`network-security.md:48`) carries
`HSTSPreloadMissingWarning` (advisory — "UX advisory; not a hard block for
non-Foundation endpoints", `Retry: Manual`).

Before this fix, `TlsEndpointPolicy.require_hsts` + `TlsHandshake.hsts_offered`
were never read by `enforce_tls_policy` — a handshake that did not offer HSTS
passed silently with zero signal. This test exercises BOTH branches:
HSTS-present → pass with no warning; required-but-absent → pass + the
spec-mandated advisory `HSTSPreloadMissingWarning`.

Tier-2 per `rules/testing.md`: drives the REAL `enforce_tls_policy` gate over a
deterministic `TlsHandshake` value object (NOT a mock — a protocol-satisfying
deterministic input per `rules/testing.md` § Protocol Adapters).
"""

from __future__ import annotations

import warnings

import pytest

from envoy.foundation_ops.errors import HSTSPreloadMissingWarning
from envoy.foundation_ops.ohttp_server import (
    DEFAULT_TLS_POLICY,
    TlsEndpointPolicy,
    TlsHandshake,
    enforce_tls_policy,
)

_TLS_1_3 = 0x0304


def _compliant_handshake(*, hsts_offered: bool) -> TlsHandshake:
    return TlsHandshake(
        negotiated_tls_version=_TLS_1_3,
        sni_present=True,
        sni_value="ohttp.foundation.example",
        expected_sni="ohttp.foundation.example",
        hsts_offered=hsts_offered,
    )


class TestHstsEnforcement:
    def test_hsts_present_passes_without_warning(self) -> None:
        """require_hsts True + hsts_offered True → pass, NO advisory emitted."""
        hs = _compliant_handshake(hsts_offered=True)
        with warnings.catch_warnings():
            warnings.simplefilter("error", HSTSPreloadMissingWarning)
            # If the warning were (wrongly) emitted, simplefilter("error") would raise.
            assert enforce_tls_policy(hs, DEFAULT_TLS_POLICY) is True

    def test_hsts_required_but_absent_emits_advisory(self) -> None:
        """require_hsts True + hsts_offered False → pass (advisory, not refusal) +
        the spec-mandated HSTSPreloadMissingWarning."""
        hs = _compliant_handshake(hsts_offered=False)
        with pytest.warns(HSTSPreloadMissingWarning):
            result = enforce_tls_policy(hs, DEFAULT_TLS_POLICY)
        # Advisory only — the connection is NOT refused for a missing HSTS commitment.
        assert result is True

    def test_hsts_not_required_skips_advisory(self) -> None:
        """require_hsts False → the advisory branch never fires even with no HSTS."""
        policy = TlsEndpointPolicy(require_hsts=False)
        hs = _compliant_handshake(hsts_offered=False)
        with warnings.catch_warnings():
            warnings.simplefilter("error", HSTSPreloadMissingWarning)
            assert enforce_tls_policy(hs, policy) is True
