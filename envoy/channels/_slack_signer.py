"""envoy.channels._slack_signer — `SlackSigner` for Slack v0 HMAC-SHA256.

Implements the Slack v0 request-signing protocol per
`specs/channel-adapters.md` § Webhook signing (Slack variant):

  HMAC-SHA256(signing_secret, 'v0:' + X-Slack-Request-Timestamp + ':' + body)

The result is hex-encoded and prefixed with ``v0=``; comparison MUST use
`hmac.compare_digest` (constant-time) to prevent timing side-channels.

Replay protection: reject any request where
``|time.time() - X-Slack-Request-Timestamp| > 300`` seconds.

Per `rules/security.md` § "No secrets in logs": `signing_secret` is NEVER
logged. The `verify` method is pure-function: no I/O, no logging.
"""

from __future__ import annotations

import hashlib
import hmac
import time


class SlackSigner:
    """Verify Slack webhook request signatures (v0 HMAC-SHA256 scheme).

    Construction validates the signing secret is non-empty so callers cannot
    accidentally construct an adapter with a missing secret that silently
    accepts all requests.

    Usage::

        signer = SlackSigner(signing_secret="8f742231b10e8888abcd99badc0a...")
        ok = signer.verify(
            headers={
                "X-Slack-Signature": "v0=a2114d57b48eac39b9ad189dd8316235049e3b4...",
                "X-Slack-Request-Timestamp": "1531420618",
            },
            body=b'token=xyzz0WbapA4vBCDEFasx0q6G&...',
        )
    """

    def __init__(self, signing_secret: str) -> None:
        if not signing_secret or not signing_secret.strip():
            raise ValueError(
                "SlackSigner: signing_secret must be non-empty. "
                "Retrieve it from the Slack app configuration page."
            )
        self._signing_secret = signing_secret

    def verify(self, headers: dict[str, str], body: bytes) -> bool:
        """Return True iff the request passes v0 HMAC-SHA256 + replay checks.

        Args:
            headers: Raw HTTP headers (case-sensitive; Slack sends the header
                names in their canonical capitalised form).
            body: The raw request body bytes.

        Returns:
            ``True`` if the signature is valid and the timestamp is within the
            300-second replay window.  ``False`` for any failure — missing
            headers, invalid timestamp, replay-window violation, or signature
            mismatch.  Callers MUST treat ``False`` as a hard reject (return
            HTTP 403) per Slack documentation.

        Security note: comparison uses `hmac.compare_digest` (constant-time)
        to prevent timing side-channels per `rules/security.md` § "No secrets".
        """
        sig = headers.get("X-Slack-Signature", "")
        ts = headers.get("X-Slack-Request-Timestamp", "")

        # Both headers MUST be present and non-empty.
        if not sig or not ts:
            return False

        # Timestamp MUST be parseable as an integer Unix epoch.
        try:
            ts_int = int(ts)
        except ValueError:
            return False

        # Replay protection: reject requests older than 5 minutes.
        if abs(time.time() - ts_int) > 300:
            return False

        # Decode the raw body for the base-string; replace-mode ensures the
        # helper never raises on malformed bytes (Slack sends UTF-8 payloads
        # but the spec says "raw body bytes").
        body_str = body.decode("utf-8", errors="replace")

        # Slack v0 base string: "v0:" + timestamp + ":" + body
        base_string = f"v0:{ts}:{body_str}"

        # HMAC-SHA256 of the base string using the signing secret.
        expected_hash = hmac.new(
            self._signing_secret.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        expected_sig = f"v0={expected_hash}"

        # Constant-time compare to prevent timing side-channels.
        return hmac.compare_digest(expected_sig, sig)
