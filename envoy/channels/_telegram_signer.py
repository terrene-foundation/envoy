"""Telegram webhook signature verifier.

Validates the ``X-Telegram-Bot-Api-Secret-Token`` header supplied on every
Telegram webhook delivery.  Uses ``hmac.compare_digest`` for constant-time
comparison to prevent timing-oracle attacks.
"""

from __future__ import annotations

import hmac


class TelegramSigner:
    """WebhookSigner implementation for Telegram Bot API webhooks.

    Telegram delivers a ``X-Telegram-Bot-Api-Secret-Token`` header whose value
    is the verbatim secret token you configured when registering the webhook
    (``setWebhook`` ``secret_token`` parameter).  There is no HMAC; we simply
    compare the provided token against the expected value in constant time.

    Parameters
    ----------
    secret_token:
        The shared secret configured via ``setWebhook``.  Must not be empty.

    Raises
    ------
    ValueError
        If *secret_token* is empty.
    """

    HEADER_NAME: str = "X-Telegram-Bot-Api-Secret-Token"

    def __init__(self, secret_token: str) -> None:
        if not secret_token:
            raise ValueError("secret_token must not be empty")
        # Store as bytes once; avoids repeated encode() calls per request.
        self._expected: bytes = secret_token.encode()

    # ------------------------------------------------------------------
    # WebhookSigner protocol
    # ------------------------------------------------------------------

    def verify(self, body: bytes, headers: dict[str, str]) -> bool:  # noqa: ARG002
        """Return True iff the ``X-Telegram-Bot-Api-Secret-Token`` header matches.

        Parameters
        ----------
        body:
            Raw request body bytes (unused by Telegram's verification scheme but
            required by the ``WebhookSigner`` protocol).
        headers:
            HTTP headers mapping — compared case-insensitively for the token
            header so that proxies can normalise capitalisation without
            breaking validation.

        Returns
        -------
        bool
            ``True`` when the token matches, ``False`` otherwise.
        """
        # Normalise to lower-case header look-up so proxies that forward
        # ``x-telegram-bot-api-secret-token`` still verify correctly.
        token: str | None = None
        for key, value in headers.items():
            if key.lower() == self.HEADER_NAME.lower():
                token = value
                break

        if token is None:
            return False

        provided: bytes = token.encode()
        # hmac.compare_digest performs a constant-time comparison, preventing
        # timing-oracle attacks regardless of matching prefix length.
        return hmac.compare_digest(provided, self._expected)
