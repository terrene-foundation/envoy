# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2: SessionRouter payload-column encryption-at-rest (S5o-enc).

Closes the `specs/threat-model.md` § Residual risks "session-store local-file-read
residual": the `request_json` / `resolution_json` (Region 1) and `state_json`
(Region 2) payload columns are AES-256-GCM ciphertext on disk under a
keychain-gated key, not canonical-JSON plaintext. These tests assert the four
acceptance gates:

1. **Ciphertext on disk** — a raw ``sqlite3`` read of the db file shows the
   ``enc:v1:`` token, NOT the plaintext payload needle.
2. **Transparent round-trip** — writing through the store API and reading back
   through a FRESH router (cross-process model) returns the original plaintext.
3. **Keychain-gated** — a router opened with a DIFFERENT keychain (no access to
   the encryption key) cannot decrypt: ``SessionStoreEncryptionError``.
4. **Signing layered over encryption** — ``resolution_sig`` (signed over the
   plaintext) still verifies after the decrypt round-trip; a ciphertext tamper
   is caught.

Tier-2 per `rules/testing.md`: real on-disk SQLite store, real ``cryptography``
AES-256-GCM, real ``InMemoryKeyringBackend`` (a deterministic protocol-satisfying
adapter — NOT a mock; it IS the headless keychain seam ``ENVOY_KEYRING=memory``
selects). Every write is verified with a read-back (§ State Persistence).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from envoy.ledger.keystore import InMemoryKeyringBackend
from envoy.runtime.session import (
    SessionRouter,
    SessionStoreEncryptionError,
    session_db_path,
)

pytestmark = pytest.mark.asyncio

_PRINCIPAL = "principal-enc-test"
# Recognizable needles that MUST NOT appear in cleartext on disk if encryption
# is wired. Distinct per column so a raw-db grep pinpoints any leak.
_REQ_NEEDLE = "REQUEST_PLAINTEXT_NEEDLE_a1b2"
_RES_NEEDLE = "RESOLUTION_PLAINTEXT_NEEDLE_c3d4"
_STATE_NEEDLE = "OBSERVED_STATE_PLAINTEXT_NEEDLE_e5f6"


def _request_json() -> str:
    return json.dumps({"tool_name": "send_email", "why_asking": _REQ_NEEDLE})


def _resolution_json() -> str:
    return json.dumps({"shape": "approve", "decided_by": _RES_NEEDLE})


def _state_json() -> str:
    return json.dumps({"fingerprints": [_STATE_NEEDLE], "goal_reconfirm": 0})


async def _open(vault_path: Path, backend: InMemoryKeyringBackend) -> SessionRouter:
    router = SessionRouter(
        vault_path=vault_path, principal_id=_PRINCIPAL, keyring_backend=backend
    )
    await router.open()
    return router


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "enc.vault"


@pytest.fixture
def backend() -> InMemoryKeyringBackend:
    """ONE shared in-process keychain — models the single OS keychain that two
    processes both open (the precondition cross-process decrypt relies on)."""
    return InMemoryKeyringBackend()


def _raw_columns(vault_path: Path) -> dict[str, list[str]]:
    """Read the payload columns DIRECTLY from the sqlite file, bypassing the
    store API — the on-disk view a local-file-read attacker sees."""
    conn = sqlite3.connect(session_db_path(vault_path))
    try:
        conn.row_factory = sqlite3.Row
        pg = conn.execute("SELECT request_json, resolution_json FROM pending_grant").fetchall()
        sos = conn.execute("SELECT state_json FROM session_observed_state").fetchall()
    finally:
        conn.close()
    return {
        "request_json": [r["request_json"] for r in pg],
        "resolution_json": [r["resolution_json"] for r in pg if r["resolution_json"] is not None],
        "state_json": [r["state_json"] for r in sos],
    }


class TestCiphertextOnDisk:
    async def test_all_payload_columns_are_ciphertext_not_plaintext(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """After writing through the API, a raw sqlite read shows enc:v1: tokens
        and ZERO plaintext needles — the local-file-read residual is closed."""
        router = await _open(vault_path, backend)
        try:
            await router.put_pending_grant(
                request_id="req-1",
                session_id="sess-1",
                request_json=_request_json(),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
            await router.resolve_pending_grant(
                request_id="req-1", resolution_json=_resolution_json(), state="resolved"
            )
            await router.snapshot_observed_state(session_id="sess-1", state_json=_state_json())
        finally:
            await router.close()

        raw = _raw_columns(vault_path)
        # Every payload column carries the versioned ciphertext prefix...
        assert raw["request_json"] and all(v.startswith("enc:v1:") for v in raw["request_json"])
        assert raw["resolution_json"] and all(
            v.startswith("enc:v1:") for v in raw["resolution_json"]
        )
        assert raw["state_json"] and all(v.startswith("enc:v1:") for v in raw["state_json"])
        # ...and NONE of the plaintext needles survive on disk.
        blob = json.dumps(raw)
        assert _REQ_NEEDLE not in blob
        assert _RES_NEEDLE not in blob
        assert _STATE_NEEDLE not in blob

    async def test_index_columns_stay_cleartext(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """Key/index columns MUST stay cleartext so lookups, the CHECK
        constraint, and the lost-update version re-check keep working."""
        router = await _open(vault_path, backend)
        try:
            await router.put_pending_grant(
                request_id="req-idx",
                session_id="sess-idx",
                request_json=_request_json(),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
        finally:
            await router.close()
        conn = sqlite3.connect(session_db_path(vault_path))
        try:
            row = conn.execute(
                "SELECT request_id, session_id, principal_id, state, version "
                "FROM pending_grant WHERE request_id='req-idx'"
            ).fetchone()
        finally:
            conn.close()
        assert row == ("req-idx", "sess-idx", _PRINCIPAL, "pending", 1)


class TestTransparentRoundTrip:
    async def test_fresh_router_decrypts_pending_and_resolution(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """Cross-process model: process A writes, a FRESH process B (same
        keychain) reads back the original plaintext."""
        writer = await _open(vault_path, backend)
        try:
            await writer.put_pending_grant(
                request_id="req-rt",
                session_id="sess-rt",
                request_json=_request_json(),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
            await writer.resolve_pending_grant(
                request_id="req-rt", resolution_json=_resolution_json(), state="resolved"
            )
        finally:
            await writer.close()

        reader = await _open(vault_path, backend)
        try:
            row = await reader.get_pending_grant("req-rt")
        finally:
            await reader.close()
        assert row is not None
        assert json.loads(row.request_json)["why_asking"] == _REQ_NEEDLE
        assert row.resolution_json is not None
        assert json.loads(row.resolution_json)["decided_by"] == _RES_NEEDLE

    async def test_fresh_router_decrypts_observed_state(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        writer = await _open(vault_path, backend)
        try:
            await writer.snapshot_observed_state(session_id="sess-rt", state_json=_state_json())
        finally:
            await writer.close()
        reader = await _open(vault_path, backend)
        try:
            loaded = await reader.load_observed_state("sess-rt")
        finally:
            await reader.close()
        assert loaded is not None
        assert json.loads(loaded)["fingerprints"] == [_STATE_NEEDLE]


class TestKeychainGated:
    async def test_router_without_the_key_cannot_decrypt(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """A process opening the SAME db file but a DIFFERENT keychain (no access
        to the encryption key) cannot decrypt — the residual closure: a local
        file read without the keychain recovers only ciphertext."""
        writer = await _open(vault_path, backend)
        try:
            await writer.put_pending_grant(
                request_id="req-kg",
                session_id="sess-kg",
                request_json=_request_json(),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
        finally:
            await writer.close()

        other_keychain = InMemoryKeyringBackend()  # mints a DIFFERENT random key
        attacker = await _open(vault_path, other_keychain)
        try:
            with pytest.raises(SessionStoreEncryptionError):
                await attacker.get_pending_grant("req-kg")
        finally:
            await attacker.close()


class TestSigningLayeredOverEncryption:
    async def test_resolution_sig_verifies_after_decrypt(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """resolution_sig is signed over the PLAINTEXT; after the decrypt
        round-trip the signature still verifies (defense-in-depth, not a swap)."""
        writer = await _open(vault_path, backend)
        try:
            await writer.put_pending_grant(
                request_id="req-sig",
                session_id="sess-sig",
                request_json=_request_json(),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
            await writer.resolve_pending_grant(
                request_id="req-sig", resolution_json=_resolution_json(), state="resolved"
            )
        finally:
            await writer.close()

        reader = await _open(vault_path, backend)
        try:
            row = await reader.get_pending_grant("req-sig")
            assert row is not None and row.resolution_json is not None
            ok = await reader.verify_resolution_signature(
                request_id="req-sig",
                resolution_json=row.resolution_json,  # decrypted plaintext
                resolution_sig=row.resolution_sig,
            )
            assert ok is True
        finally:
            await reader.close()

    async def test_ciphertext_tamper_is_caught_on_read(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """A byte-level tamper of the on-disk ciphertext fails the AES-256-GCM
        tag check on read (fail-closed)."""
        writer = await _open(vault_path, backend)
        try:
            await writer.put_pending_grant(
                request_id="req-tamper",
                session_id="sess-tamper",
                request_json=_request_json(),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
        finally:
            await writer.close()

        # Flip the last base64 char of the stored ciphertext token.
        conn = sqlite3.connect(session_db_path(vault_path))
        try:
            tok = conn.execute(
                "SELECT request_json FROM pending_grant WHERE request_id='req-tamper'"
            ).fetchone()[0]
            flipped = tok[:-1] + ("A" if tok[-1] != "A" else "B")
            conn.execute(
                "UPDATE pending_grant SET request_json=? WHERE request_id='req-tamper'",
                (flipped,),
            )
            conn.commit()
        finally:
            conn.close()

        reader = await _open(vault_path, backend)
        try:
            with pytest.raises(SessionStoreEncryptionError):
                await reader.get_pending_grant("req-tamper")
        finally:
            await reader.close()


class TestAadBinding:
    async def test_ciphertext_not_swappable_across_columns(
        self, vault_path: Path, backend: InMemoryKeyringBackend
    ) -> None:
        """A request_json ciphertext copied into the resolution_json column of the
        SAME row fails decrypt — the AAD binds each ciphertext to (table, row,
        column), so intra-store ciphertext shuffling is caught."""
        writer = await _open(vault_path, backend)
        try:
            await writer.put_pending_grant(
                request_id="req-aad",
                session_id="sess-aad",
                request_json=_request_json(),
                ttl_expires_at="2099-01-01T00:00:00+00:00",
            )
        finally:
            await writer.close()

        conn = sqlite3.connect(session_db_path(vault_path))
        try:
            req_ct = conn.execute(
                "SELECT request_json FROM pending_grant WHERE request_id='req-aad'"
            ).fetchone()[0]
            # Paste request_json's ciphertext into resolution_json + mark resolved.
            conn.execute(
                "UPDATE pending_grant SET state='resolved', resolution_json=?, "
                "version=version+1 WHERE request_id='req-aad'",
                (req_ct,),
            )
            conn.commit()
        finally:
            conn.close()

        reader = await _open(vault_path, backend)
        try:
            with pytest.raises(SessionStoreEncryptionError):
                await reader.get_pending_grant("req-aad")
        finally:
            await reader.close()
