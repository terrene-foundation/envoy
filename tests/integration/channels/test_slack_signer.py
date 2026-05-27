"""Tier-2 wiring: `SlackSigner` v0 HMAC-SHA256 unit tests.

Per `specs/channel-adapters.md` § Webhook signing (Slack variant):
  base_string = 'v0:' + X-Slack-Request-Timestamp + ':' + body
  HMAC-SHA256(signing_secret, base_string) prefixed 'v0='
  Replay window: |now - ts| > 300 seconds → reject.

Per `rules/testing.md` § Tier 2: no `mock.patch` / `MagicMock`. The
`SlackSigner.verify` method is pure-function (no I/O), so all edge cases
are tested with deterministic real inputs. Time-dependent replay tests
use actual `time.time()` to compute an in-window or out-of-window
timestamp.

Per `rules/security.md` § "No secrets in logs": `signing_secret` is
never logged; tests use fixed test vectors for structural coverage.
"""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from envoy.channels._slack_signer import SlackSigner


def _make_sig(secret: str, ts: str, body: bytes) -> str:
    """Helper: compute the expected v0 HMAC signature for a test vector."""
    body_str = body.decode("utf-8", errors="replace")
    base = f"v0:{ts}:{body_str}"
    digest = hmac.new(
        secret.encode("utf-8"),
        base.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"v0={digest}"


_TEST_SECRET = "8f742231b10e8888abcd99badc0a9199"  # 32-char test-only secret
_TEST_BODY = b"token=xyzz0WbapA4vBCDEFasx0q6G&team_id=T1DC2JH3J&team_domain=testteamnow"


@pytest.mark.regression
class TestSlackSignerConstruction:
    """Contract pin: empty signing_secret raises at construction."""

    def test_empty_secret_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="signing_secret must be non-empty"):
            SlackSigner(signing_secret="")

    def test_whitespace_only_secret_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="signing_secret must be non-empty"):
            SlackSigner(signing_secret="   ")

    def test_non_empty_secret_constructs_successfully(self) -> None:
        signer = SlackSigner(signing_secret=_TEST_SECRET)
        assert signer is not None


@pytest.mark.regression
class TestSlackSignerMissingHeaders:
    """Contract pin: missing or empty required headers → False."""

    def setup_method(self) -> None:
        self._signer = SlackSigner(signing_secret=_TEST_SECRET)
        self._ts = str(int(time.time()))
        self._sig = _make_sig(_TEST_SECRET, self._ts, _TEST_BODY)

    def test_missing_both_headers_returns_false(self) -> None:
        ok = self._signer.verify(headers={}, body=_TEST_BODY)
        assert ok is False

    def test_missing_signature_header_returns_false(self) -> None:
        ok = self._signer.verify(
            headers={"X-Slack-Request-Timestamp": self._ts},
            body=_TEST_BODY,
        )
        assert ok is False

    def test_missing_timestamp_header_returns_false(self) -> None:
        ok = self._signer.verify(
            headers={"X-Slack-Signature": self._sig},
            body=_TEST_BODY,
        )
        assert ok is False

    def test_empty_signature_returns_false(self) -> None:
        ok = self._signer.verify(
            headers={
                "X-Slack-Signature": "",
                "X-Slack-Request-Timestamp": self._ts,
            },
            body=_TEST_BODY,
        )
        assert ok is False

    def test_empty_timestamp_returns_false(self) -> None:
        ok = self._signer.verify(
            headers={
                "X-Slack-Signature": self._sig,
                "X-Slack-Request-Timestamp": "",
            },
            body=_TEST_BODY,
        )
        assert ok is False


@pytest.mark.regression
class TestSlackSignerTimestamp:
    """Contract pin: invalid + out-of-window timestamps → False."""

    def setup_method(self) -> None:
        self._signer = SlackSigner(signing_secret=_TEST_SECRET)

    def test_non_integer_timestamp_returns_false(self) -> None:
        ts = "not-an-integer"
        sig = _make_sig(_TEST_SECRET, ts, _TEST_BODY)
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts},
            body=_TEST_BODY,
        )
        assert ok is False

    def test_float_string_timestamp_returns_false(self) -> None:
        ts = "1531420618.5"
        sig = _make_sig(_TEST_SECRET, ts, _TEST_BODY)
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts},
            body=_TEST_BODY,
        )
        assert ok is False

    def test_replay_too_old_returns_false(self) -> None:
        # 301 seconds in the past → outside 300-second replay window.
        ts = str(int(time.time()) - 301)
        sig = _make_sig(_TEST_SECRET, ts, _TEST_BODY)
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts},
            body=_TEST_BODY,
        )
        assert ok is False

    def test_replay_from_future_too_far_returns_false(self) -> None:
        # 301 seconds in the future → outside window.
        ts = str(int(time.time()) + 301)
        sig = _make_sig(_TEST_SECRET, ts, _TEST_BODY)
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts},
            body=_TEST_BODY,
        )
        assert ok is False

    def test_timestamp_at_boundary_inside_window_passes(self) -> None:
        # Exactly 299 seconds old → inside window.
        ts = str(int(time.time()) - 299)
        sig = _make_sig(_TEST_SECRET, ts, _TEST_BODY)
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts},
            body=_TEST_BODY,
        )
        assert ok is True


@pytest.mark.regression
class TestSlackSignerSignatureMismatch:
    """Contract pin: wrong secret / tampered body / wrong format → False."""

    def setup_method(self) -> None:
        self._signer = SlackSigner(signing_secret=_TEST_SECRET)
        self._ts = str(int(time.time()))

    def test_wrong_secret_returns_false(self) -> None:
        sig = _make_sig("wrong-secret-value-AAAAAAAAAA", self._ts, _TEST_BODY)
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": self._ts},
            body=_TEST_BODY,
        )
        assert ok is False

    def test_tampered_body_returns_false(self) -> None:
        sig = _make_sig(_TEST_SECRET, self._ts, _TEST_BODY)
        tampered = _TEST_BODY + b"&extra=injection"
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": self._ts},
            body=tampered,
        )
        assert ok is False

    def test_missing_v0_prefix_returns_false(self) -> None:
        sig_no_prefix = _make_sig(_TEST_SECRET, self._ts, _TEST_BODY).removeprefix("v0=")
        ok = self._signer.verify(
            headers={
                "X-Slack-Signature": sig_no_prefix,
                "X-Slack-Request-Timestamp": self._ts,
            },
            body=_TEST_BODY,
        )
        assert ok is False

    def test_wrong_version_prefix_returns_false(self) -> None:
        correct_hash = _make_sig(_TEST_SECRET, self._ts, _TEST_BODY)
        v1_sig = "v1=" + correct_hash[3:]  # replace "v0=" with "v1="
        ok = self._signer.verify(
            headers={
                "X-Slack-Signature": v1_sig,
                "X-Slack-Request-Timestamp": self._ts,
            },
            body=_TEST_BODY,
        )
        assert ok is False


@pytest.mark.regression
class TestSlackSignerHappyPath:
    """Contract pin: valid signature + in-window timestamp → True."""

    def setup_method(self) -> None:
        self._signer = SlackSigner(signing_secret=_TEST_SECRET)

    def test_correct_signature_current_timestamp_returns_true(self) -> None:
        ts = str(int(time.time()))
        sig = _make_sig(_TEST_SECRET, ts, _TEST_BODY)
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts},
            body=_TEST_BODY,
        )
        assert ok is True

    def test_empty_body_with_valid_signature_returns_true(self) -> None:
        body = b""
        ts = str(int(time.time()))
        sig = _make_sig(_TEST_SECRET, ts, body)
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts},
            body=body,
        )
        assert ok is True

    def test_binary_body_with_valid_signature_returns_true(self) -> None:
        # Non-UTF-8 bytes — signer uses errors='replace'.
        body = b"\xff\xfe\x00body-data"
        ts = str(int(time.time()))
        sig = _make_sig(_TEST_SECRET, ts, body)
        ok = self._signer.verify(
            headers={"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts},
            body=body,
        )
        assert ok is True

    def test_verify_is_deterministic_across_calls(self) -> None:
        ts = str(int(time.time()))
        sig = _make_sig(_TEST_SECRET, ts, _TEST_BODY)
        headers = {"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts}
        assert self._signer.verify(headers=headers, body=_TEST_BODY) is True
        assert self._signer.verify(headers=headers, body=_TEST_BODY) is True
