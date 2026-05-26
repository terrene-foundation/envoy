"""Discord Ed25519 signature verifier.

Implements the ``WebhookSigner`` Protocol for Discord's interaction verification.
Discord signs each webhook delivery with Ed25519 using the application's public key.

Reference:
    https://discord.com/developers/docs/interactions/receiving-and-responding
    #security-and-authorization
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger(__name__)


@runtime_checkable
class WebhookSignerProtocol(Protocol):
    """Structural match for nexus.transports.webhook.WebhookSigner."""

    def verify(self, headers: dict[str, str], body: bytes) -> bool:
        """Return True if the request is authentic, False otherwise."""
        ...


class DiscordSigner:
    """Verify Discord interaction webhook signatures using Ed25519.

    Discord includes two headers per request:
    - ``X-Signature-Ed25519``  — hex-encoded Ed25519 signature of the message
    - ``X-Signature-Timestamp`` — timestamp string prepended before the body

    The message to verify is: ``timestamp.encode() + body``.

    The implementation is deliberately exception-free toward callers: any
    decode error, header-missing condition, or crypto failure returns ``False``
    without propagating an exception.  This satisfies the constant-time-exit
    / no-exception-leakage contract required by the ``WebhookSigner`` Protocol.

    Args:
        application_public_key: Hex-encoded Ed25519 public key from the Discord
            Developer Portal. Must be a 64-character hex string (32 bytes).
    """

    # Header names as Discord specifies them (case-insensitive in HTTP/1.1,
    # but Discord clients always send lower-case; we normalise on lookup).
    _SIG_HEADER = "x-signature-ed25519"
    _TS_HEADER = "x-signature-timestamp"

    def __init__(self, application_public_key: str) -> None:
        if not application_public_key:
            raise ValueError("application_public_key must be a non-empty hex string")
        # Parse and validate the key at construction time so runtime calls
        # cannot fail on a malformed key.
        raw_key = bytes.fromhex(application_public_key)
        self._public_key: Ed25519PublicKey = Ed25519PublicKey.from_public_bytes(raw_key)

    def verify(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify a Discord webhook signature.

        Args:
            headers: HTTP request headers (keys may be any case).
            body: Raw request body bytes.

        Returns:
            ``True`` if the signature is valid; ``False`` for any failure
            (missing header, decode error, invalid signature, wrong key).
        """
        try:
            # Normalise header keys to lower-case for case-insensitive lookup.
            lower = {k.lower(): v for k, v in headers.items()}
            raw_sig = lower.get(self._SIG_HEADER)
            timestamp = lower.get(self._TS_HEADER)

            if not raw_sig or not timestamp:
                logger.debug(
                    "discord_signer.verify: missing required headers "
                    "(sig_present=%s, ts_present=%s)",
                    raw_sig is not None,
                    timestamp is not None,
                )
                return False

            sig_bytes = bytes.fromhex(raw_sig)
            message = timestamp.encode() + body

            # Ed25519 verify raises InvalidSignature on failure; returns None on
            # success (cryptography library convention).
            self._public_key.verify(sig_bytes, message)
            return True

        except InvalidSignature:
            # Expected failure path — not an error, just an invalid request.
            return False
        except Exception:
            # Catches ValueError (bad hex), UnicodeEncodeError, etc.  We must
            # not leak exceptions to the caller per the WebhookSigner contract.
            logger.debug("discord_signer.verify: unexpected exception", exc_info=True)
            return False
