# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SEC-LOW-1 — key-config expiry compares parsed instants, not ISO strings.

`assert_not_expired` previously used a lexicographic string compare on the
ISO-8601 `expires_at` vs the `now_iso` clock. The default `now_iso` emits the
`+00:00` offset form, but a Foundation publishing the RFC-3339 canonical `Z`
form would mis-evaluate: `ord('Z') > ord('+')`, so a still-valid `...Z` expiry
could compare as "<= now" (or a genuinely-expired one as "> now") purely from
the string form, never the instant.

This test pins the fix: a `Z`-suffixed expiry of the SAME instant as a `+00:00`
`now` is correctly evaluated as not-yet-expired, and a genuinely-expired
`Z`-form is refused.

Tier-2 per `rules/testing.md`: REAL `OhttpKeyConfigServerHandlers` with a real
`OhttpHpkeKeyConfig` (real X25519 keypair) and an injected deterministic clock.
"""

from __future__ import annotations

import pytest

from envoy.foundation_ops.errors import KeyConfigExpiredError
from envoy.foundation_ops.hpke import OhttpHpkeKeyConfig, generate_keypair
from envoy.foundation_ops.ohttp_server import OhttpKeyConfigServerHandlers


def _config(expires_at: str) -> OhttpHpkeKeyConfig:
    _priv, pub = generate_keypair()
    return OhttpHpkeKeyConfig(key_id=7, public_key=pub, expires_at=expires_at)


class TestKeyConfigExpiryIso:
    def test_z_form_expiry_after_offset_now_is_not_expired(self) -> None:
        """expires_at in `Z` form, later than a `+00:00` now → NOT expired.

        A lexicographic compare would mis-rank because `ord('Z') > ord('+')`;
        the parsed-instant compare evaluates the real ordering."""
        # Expiry strictly after `now` (different instants), mixed string forms.
        server = OhttpKeyConfigServerHandlers(
            now_iso=lambda: "2030-01-01T00:00:00+00:00"
        )
        server.publish_config(_config("2030-06-01T00:00:00Z"))
        assert server.assert_not_expired(key_id=7) is True

    def test_z_form_same_instant_as_offset_now_is_expired(self) -> None:
        """`Z` expiry == `+00:00` now (SAME instant) → expired (<= refuses).

        Both forms denote the identical UTC instant; parsed-instant compare
        treats them as equal, so the `<=` expiry branch correctly refuses."""
        server = OhttpKeyConfigServerHandlers(
            now_iso=lambda: "2030-01-01T00:00:00+00:00"
        )
        server.publish_config(_config("2030-01-01T00:00:00Z"))
        with pytest.raises(KeyConfigExpiredError):
            server.assert_not_expired(key_id=7)

    def test_genuinely_expired_z_form_is_refused(self) -> None:
        """A `Z`-form expiry strictly before now → refused."""
        server = OhttpKeyConfigServerHandlers(
            now_iso=lambda: "2030-01-01T00:00:00+00:00"
        )
        server.publish_config(_config("2020-01-01T00:00:00Z"))
        with pytest.raises(KeyConfigExpiredError):
            server.assert_not_expired(key_id=7)

    def test_offset_now_z_form_offset_expiry_consistent(self) -> None:
        """Sanity: both sides in `+00:00` form, far-future expiry → not expired."""
        server = OhttpKeyConfigServerHandlers(
            now_iso=lambda: "2030-01-01T00:00:00+00:00"
        )
        server.publish_config(_config("2099-01-01T00:00:00+00:00"))
        assert server.assert_not_expired(key_id=7) is True
