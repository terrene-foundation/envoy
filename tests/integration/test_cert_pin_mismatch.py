# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""F2 — cert-pin mismatch raises CertPinMismatchError (was wrong error type).

`specs/network-security.md:42` mandates `CertPinMismatchError` when a TLS
handshake to a Foundation-operated endpoint returns a cert NOT in the
pinned-keys allowlist. Before this fix, `enforce_tls_policy` raised
`SNIStrippingDetectedError` on the pin-mismatch branch — the WRONG type, which
would have surfaced "SNI stripping" to the user when the real event is a
suspected Foundation MITM (a different banner, a different T-080 defense row).

This test exercises the pin path (which previously had ZERO coverage):
matching fingerprint → pass; mismatched fingerprint → CertPinMismatchError.
Also pins the documented `None` default behavior on `DEFAULT_TLS_POLICY`.

Tier-2 per `rules/testing.md`: REAL `enforce_tls_policy` over a deterministic
`TlsHandshake` value object.
"""

from __future__ import annotations

import pytest

from envoy.foundation_ops.errors import CertPinMismatchError, SNIStrippingDetectedError
from envoy.foundation_ops.ohttp_server import (
    DEFAULT_TLS_POLICY,
    TlsEndpointPolicy,
    TlsHandshake,
    enforce_tls_policy,
)

_TLS_1_3 = 0x0304
_PINNED_FP = "sha256:aa11bb22cc33dd44ee55ff6600112233445566778899aabbccddeeff00112233"
_ROGUE_FP = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"


def _handshake(cert_fingerprint: str | None) -> TlsHandshake:
    return TlsHandshake(
        negotiated_tls_version=_TLS_1_3,
        sni_present=True,
        sni_value="ohttp.foundation.example",
        expected_sni="ohttp.foundation.example",
        cert_fingerprint=cert_fingerprint,
    )


class TestCertPinMismatch:
    def test_matching_pinned_fingerprint_passes(self) -> None:
        policy = TlsEndpointPolicy(pinned_cert_fingerprint=_PINNED_FP)
        hs = _handshake(_PINNED_FP)
        assert enforce_tls_policy(hs, policy) is True

    def test_mismatched_fingerprint_raises_cert_pin_mismatch(self) -> None:
        policy = TlsEndpointPolicy(pinned_cert_fingerprint=_PINNED_FP)
        hs = _handshake(_ROGUE_FP)
        with pytest.raises(CertPinMismatchError):
            enforce_tls_policy(hs, policy)

    def test_mismatch_is_not_sni_stripping(self) -> None:
        """Regression: the pin-mismatch branch must NOT raise the SNI-stripping
        type — the spec taxonomy assigns these distinct error rows + banners."""
        policy = TlsEndpointPolicy(pinned_cert_fingerprint=_PINNED_FP)
        hs = _handshake(_ROGUE_FP)
        with pytest.raises(CertPinMismatchError):
            enforce_tls_policy(hs, policy)
        # CertPinMismatchError is NOT a subclass of SNIStrippingDetectedError —
        # so an `except SNIStrippingDetectedError` handler must NOT catch it.
        assert not issubclass(CertPinMismatchError, SNIStrippingDetectedError)

    def test_default_policy_none_pin_does_not_check_pin(self) -> None:
        """Documented `None` default: DEFAULT_TLS_POLICY ships
        pinned_cert_fingerprint=None because the canonical pin material ships in
        the WS-2 binary and is injected at the transport layer. With None at
        THIS layer there is nothing to compare against, so any presented cert
        passes the pin check here (the binary-shipped pin enforces fail-closed
        at the transport layer). This pins the documented contract."""
        assert DEFAULT_TLS_POLICY.pinned_cert_fingerprint is None
        # Even a rogue fingerprint passes when no pin is configured at this layer.
        hs = _handshake(_ROGUE_FP)
        assert enforce_tls_policy(hs, DEFAULT_TLS_POLICY) is True
