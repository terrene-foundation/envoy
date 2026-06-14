# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: the `envoy chat` CLI surface (WS-6 S6c; 10th of 10 commands).

`envoy chat` starts the resident chat-session loop: it reads messages from stdin
(one per line), acks each to stdout, and on EOF (Ctrl-D / channel disconnect)
fires the S5b session boundary against a real durable Ledger. This suite drives
the command through `CliRunner` with a real file-backed vault + the headless
`ENVOY_KEYRING=memory` seam (journal/0017 Pattern 1) — the same end-to-end path a
human hits, per `rules/user-flow-validation.md`.

Per `rules/testing.md` Tier 2: real file-backed SQLite store + real durable
Ledger; no mocking. (The `ChatResidentLoop` behaviour — grant drive, crash
recovery, T-013 boundary reset — is proven at the loop layer in
`tests/tier2/test_chat_resident_loop.py`; this suite proves the CLI wiring.)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from envoy.cli.main import cli


def _env(monkeypatch: pytest.MonkeyPatch, vault: Path) -> None:
    monkeypatch.setenv("ENVOY_KEYRING", "memory")
    monkeypatch.setenv("ENVOY_PRINCIPAL_ID", "sha256:cli-chat-test-principal")
    monkeypatch.setenv("ENVOY_VAULT_PATH", str(vault))
    monkeypatch.setenv("ENVOY_SESSION_ID", "clichatsession01")


def test_chat_acks_each_message_and_exits_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(monkeypatch, tmp_path / "vault.db")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--log-level", "WARNING", "chat"], input="hello envoy\nwhat can you do\n"
    )
    assert result.exit_code == 0, result.output
    # Each inbound line is acknowledged through the real CLI channel send path.
    assert result.output.count("[ack] received") == 2


def test_chat_empty_session_exits_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Immediate EOF (no messages) is a clean zero-turn session: the boundary
    # still fires, the command exits 0.
    _env(monkeypatch, tmp_path / "vault.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["--log-level", "WARNING", "chat"], input="")
    assert result.exit_code == 0, result.output
    assert "[ack]" not in result.output


def test_chat_blank_lines_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, tmp_path / "vault.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["--log-level", "WARNING", "chat"], input="\n\nreal message\n\n")
    assert result.exit_code == 0, result.output
    # Only the one non-blank line is acked.
    assert result.output.count("[ack] received") == 1


def test_chat_bad_keyring_selector_exits_32(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(monkeypatch, tmp_path / "vault.db")
    monkeypatch.setenv("ENVOY_KEYRING", "not-a-real-backend")
    runner = CliRunner()
    result = runner.invoke(cli, ["--log-level", "WARNING", "chat"], input="hi\n")
    assert result.exit_code == 32, result.output


def test_chat_missing_principal_is_clean_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENVOY_KEYRING", "memory")
    monkeypatch.delenv("ENVOY_PRINCIPAL_ID", raising=False)
    monkeypatch.setenv("ENVOY_VAULT_PATH", str(tmp_path / "vault.db"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--log-level", "WARNING", "chat"], input="hi\n")
    # Click surfaces a usage error (exit 2 from ClickException), not a traceback.
    assert result.exit_code != 0
    assert "no principal" in result.output
