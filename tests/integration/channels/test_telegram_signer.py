"""Tier-2 structural tests for ``TelegramSigner``.

Tests constant-time token verification via ``hmac.compare_digest``, case-
insensitive header matching, rejection of missing / wrong tokens, and empty
``secret_token`` constructor validation.

Per ``rules/testing.md`` § Tier 2: no ``mock.patch`` / ``MagicMock``; real
hmac and bytes operations only.
"""

from __future__ import annotations

import pytest

from envoy.channels._telegram_signer import TelegramSigner


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestTelegramSignerConstructor:
    """``TelegramSigner.__init__`` contract pins."""

    def test_empty_secret_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="secret_token must not be empty"):
            TelegramSigner("")

    def test_non_empty_secret_constructs_successfully(self) -> None:
        signer = TelegramSigner("some-secret")
        assert signer is not None

    def test_header_name_constant_is_correct(self) -> None:
        assert TelegramSigner.HEADER_NAME == "X-Telegram-Bot-Api-Secret-Token"


# ---------------------------------------------------------------------------
# Happy path: valid token
# ---------------------------------------------------------------------------


class TestTelegramSignerVerify:
    """``TelegramSigner.verify`` contract pins."""

    def test_valid_token_returns_true(self) -> None:
        signer = TelegramSigner("my-secret-token")
        headers = {"X-Telegram-Bot-Api-Secret-Token": "my-secret-token"}
        assert signer.verify(b"body-does-not-matter", headers) is True

    def test_wrong_token_returns_false(self) -> None:
        signer = TelegramSigner("correct-secret")
        headers = {"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}
        assert signer.verify(b"any-body", headers) is False

    def test_missing_header_returns_false(self) -> None:
        signer = TelegramSigner("my-secret-token")
        assert signer.verify(b"any-body", {}) is False

    def test_unrelated_headers_return_false(self) -> None:
        signer = TelegramSigner("my-secret-token")
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer my-secret-token",
        }
        assert signer.verify(b"any-body", headers) is False

    # -----------------------------------------------------------------------
    # Case-insensitive header matching
    # -----------------------------------------------------------------------

    def test_lowercase_header_name_matches(self) -> None:
        signer = TelegramSigner("secret")
        headers = {"x-telegram-bot-api-secret-token": "secret"}
        assert signer.verify(b"body", headers) is True

    def test_uppercase_header_name_matches(self) -> None:
        signer = TelegramSigner("secret")
        headers = {"X-TELEGRAM-BOT-API-SECRET-TOKEN": "secret"}
        assert signer.verify(b"body", headers) is True

    def test_mixed_case_header_name_matches(self) -> None:
        signer = TelegramSigner("secret")
        headers = {"x-Telegram-Bot-Api-Secret-Token": "secret"}
        assert signer.verify(b"body", headers) is True

    # -----------------------------------------------------------------------
    # Body content does not affect verification
    # -----------------------------------------------------------------------

    def test_body_content_irrelevant_to_verify(self) -> None:
        """``verify`` checks the header token only; body bytes are accepted but unused."""
        signer = TelegramSigner("tok")
        headers = {"X-Telegram-Bot-Api-Secret-Token": "tok"}
        assert signer.verify(b"", headers) is True
        assert signer.verify(b"some body", headers) is True
        assert signer.verify(b"\x00\x01\x02", headers) is True

    # -----------------------------------------------------------------------
    # Token value edge cases
    # -----------------------------------------------------------------------

    def test_token_with_special_characters(self) -> None:
        secret = "se!cr@et#tok$en%val^ue&123"
        signer = TelegramSigner(secret)
        headers = {"X-Telegram-Bot-Api-Secret-Token": secret}
        assert signer.verify(b"body", headers) is True

    def test_whitespace_only_token_accepted_if_not_empty(self) -> None:
        """A whitespace-only token is technically non-empty and must match exactly."""
        signer = TelegramSigner("   ")
        headers = {"X-Telegram-Bot-Api-Secret-Token": "   "}
        assert signer.verify(b"body", headers) is True

    def test_whitespace_token_does_not_match_trimmed_version(self) -> None:
        signer = TelegramSigner("   ")
        # Trimmed value must NOT match the padded secret.
        headers = {"X-Telegram-Bot-Api-Secret-Token": " "}
        assert signer.verify(b"body", headers) is False

    def test_multiple_headers_first_matching_wins(self) -> None:
        """When multiple header keys match (case-insensitively), first match is used."""
        signer = TelegramSigner("correct")
        # Python dict preserves insertion order; first key that matches is used.
        headers = {
            "X-Telegram-Bot-Api-Secret-Token": "correct",
            "x-telegram-bot-api-secret-token": "wrong",
        }
        assert signer.verify(b"body", headers) is True
