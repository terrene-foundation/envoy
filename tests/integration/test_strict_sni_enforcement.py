# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S10.4 — every Foundation OHTTP endpoint enforces TLS 1.3 + strict SNI.

`specs/network-security.md:15,24`: minimum TLS 1.3, strict SNI, HSTS, pinned
cert. A TLS<1.3 or SNI-stripped handshake is REFUSED with the typed
network-security error. The `enforce_tls_policy` gate is the structural check
the Nexus transport layer applies at TLS termination (the policy is attached to
the built Nexus app via `build_ohttp_nexus`).
"""

from __future__ import annotations

import pytest

from envoy.foundation_ops.errors import (
    SNIStrippingDetectedError,
    TLSVersionTooLowError,
)
from envoy.foundation_ops.ohttp_server import (
    DEFAULT_TLS_POLICY,
    OhttpKeyConfigServerHandlers,
    OhttpRelayHandlers,
    TlsEndpointPolicy,
    TlsHandshake,
    build_ohttp_nexus,
    enforce_tls_policy,
)

_TLS_1_3 = 0x0304
_TLS_1_2 = 0x0303


class TestStrictSniEnforcement:
    def test_compliant_handshake_accepted(self) -> None:
        hs = TlsHandshake(
            negotiated_tls_version=_TLS_1_3,
            sni_present=True,
            sni_value="ohttp.foundation.example",
            expected_sni="ohttp.foundation.example",
        )
        assert enforce_tls_policy(hs, DEFAULT_TLS_POLICY) is True

    def test_tls_below_1_3_refused(self) -> None:
        hs = TlsHandshake(
            negotiated_tls_version=_TLS_1_2,
            sni_present=True,
            sni_value="ohttp.foundation.example",
            expected_sni="ohttp.foundation.example",
        )
        with pytest.raises(TLSVersionTooLowError):
            enforce_tls_policy(hs, DEFAULT_TLS_POLICY)

    def test_sni_stripped_refused(self) -> None:
        hs = TlsHandshake(
            negotiated_tls_version=_TLS_1_3,
            sni_present=False,  # stripped by an intermediary
            sni_value=None,
            expected_sni="ohttp.foundation.example",
        )
        with pytest.raises(SNIStrippingDetectedError):
            enforce_tls_policy(hs, DEFAULT_TLS_POLICY)

    def test_sni_mismatch_refused(self) -> None:
        hs = TlsHandshake(
            negotiated_tls_version=_TLS_1_3,
            sni_present=True,
            sni_value="evil.example",  # mismatched
            expected_sni="ohttp.foundation.example",
        )
        with pytest.raises(SNIStrippingDetectedError):
            enforce_tls_policy(hs, DEFAULT_TLS_POLICY)

    def test_default_policy_requires_tls_1_3_and_strict_sni(self) -> None:
        assert DEFAULT_TLS_POLICY.min_tls_version == _TLS_1_3
        assert DEFAULT_TLS_POLICY.require_strict_sni is True
        assert DEFAULT_TLS_POLICY.require_hsts is True


class TestBuildTimeTlsFloorGate:
    """`build_ohttp_nexus` is fail-closed: it refuses to stand up an OHTTP
    endpoint whose declared TLS contract is weaker than the Foundation floor
    (TLS 1.3 + strict SNI), so the deployment transport layer is never handed a
    sub-floor policy to enforce (`specs/network-security.md` §5/§15/§24)."""

    def test_build_refuses_sub_tls_1_3_policy(self) -> None:
        server = OhttpKeyConfigServerHandlers()
        relay = OhttpRelayHandlers()
        weak = TlsEndpointPolicy(min_tls_version=_TLS_1_2)
        with pytest.raises(TLSVersionTooLowError):
            build_ohttp_nexus(server, relay, tls_policy=weak)

    def test_build_refuses_non_strict_sni_policy(self) -> None:
        server = OhttpKeyConfigServerHandlers()
        relay = OhttpRelayHandlers()
        weak = TlsEndpointPolicy(require_strict_sni=False)
        with pytest.raises(SNIStrippingDetectedError):
            build_ohttp_nexus(server, relay, tls_policy=weak)
