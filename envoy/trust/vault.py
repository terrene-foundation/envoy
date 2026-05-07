"""Trust Vault — encrypted local storage for envoy keys + envelope + posture.

Per `specs/trust-vault.md` § Purpose + § File format + § Encryption + §
Memory hygiene. Phase 01 ships a single-region AES-256-GCM container with
Argon2id-derived master key and idle-lock lifecycle. Phase 02+ extends:

- Secure-Enclave / TPM-bound secret XOR (specs/trust-vault.md § Encryption)
- Per-region HKDF-SHA-256 keys (Phase 02)
- Padding buckets {1, 4, 16, 64} MiB (Phase 04)
- Duress passphrase + honeypot Genesis (Phase 04)
- Hidden envelope + shadow segment (Phase 04)
- `envoy vault destroy-keys` CLI (T-042 mitigation; Phase 02)

Phase 01 narrow scope per `01-analysis/05-trust-store-implementation.md` § 4
step 3: AES-256-GCM container + Argon2id passphrase derivation + lifecycle
(unlock / lock / __aexit__ / idle-timer-reset / VaultLockedError per the
R2-M-02 carry-forward disposition).

File format (Phase 01 minimal — a strict subset of the eventual spec layout):

    magic       4 bytes   `b"ETVT"` (Envoy Trust Vault)
    version     1 byte    `0x01`
    payload_len 8 bytes   little-endian; ciphertext_len + 16 (GCM tag)
    salt        16 bytes  Argon2id salt (random per vault)
    argon2_m    4 bytes   little-endian memory cost (KiB) — pinned 2**17
    argon2_t    4 bytes   little-endian time cost — pinned 3
    argon2_p    4 bytes   little-endian parallelism — pinned 1
    nonce       12 bytes  AES-256-GCM nonce (random per encrypt)
    ciphertext  variable  AES-256-GCM(plaintext, AAD=header_bytes) || tag(16)

Total fixed-size header: 53 bytes. AAD covers the FULL 53-byte header
(magic + version + payload_len + salt + Argon2id params + nonce) — any
header byte tamper fails MAC verification per `specs/trust-vault.md`
§ Error taxonomy `VaultMACVerificationFailedError`.

Per `rules/trust-plane-security.md` MUST Rule 7 (atomic-write pattern)
— vault writes use temp file + fsync + `os.replace` to ensure crash-safety.
The kailash `atomic_write` helper is JSON-only (dict→json), so the binary
vault hand-rolls the same pattern at the bytes level rather than routing
through the helper.

Per `rules/trust-plane-security.md` MUST NOT Rule 3 (no private key material
in memory) — the master key is held only between `unlock()` and `lock()`,
and `lock()` zeros the key bytes via best-effort `bytearray` mutation
before releasing the reference.

**Metadata slot (T-02-35).** Phase 01 carves a minimal metadata slot inside
the existing payload via a self-discriminating JSON envelope. `read_metadata()`
returns `{}` if the payload is not a JSON envelope (legacy opaque-bytes
payloads remain compatible); `write_metadata(dict)` serializes
`{"_etmd_v1": <dict>}` and routes through the standard
`write(plaintext)` path. The envelope discriminator key is "_etmd_v1"
(Envoy Trust MetaData v1) — chosen to avoid the literal substring "envoy"
in the on-disk plaintext so H-06 (no "Envoy" label in persisted state) is
honored at envelope-key level too. Used by T-02-35
`TrustVaultChecklistPersister` to persist
`metadata["shamir_distribution_checklists"][ritual_id]` per shard 15 § 3.5.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import struct
import time
import warnings
from pathlib import Path
from typing import Any

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from envoy.trust.errors import (
    Argon2ParameterMismatchError,
    AutoLockIdleTimeoutError,
    MasterKeySizeError,
    VaultLockedError,
    VaultMACVerificationFailedError,
    VaultUnlockFailedError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File format constants
# ---------------------------------------------------------------------------

_MAGIC = b"ETVT"
_VERSION = 0x01

# Argon2id parameters per specs/trust-vault.md § Encryption.
# m=2^17 KiB = 128 MiB; t=3; p=1.
_ARGON2_MEMORY_COST_KIB = 1 << 17
_ARGON2_TIME_COST = 3
_ARGON2_PARALLELISM = 1
_ARGON2_KEY_LEN = 32  # 256-bit master key

_SALT_LEN = 16
_NONCE_LEN = 12
_GCM_TAG_LEN = 16

# Header layout: magic(4) + version(1) + payload_len(8) + salt(16)
# + argon2_m(4) + argon2_t(4) + argon2_p(4) + nonce(12)  =  53
_HEADER_FMT = "<4sBQ16sIII12s"  # little-endian
_HEADER_LEN = struct.calcsize(_HEADER_FMT)

# Phase 01 default idle TTL — 15 minutes per specs/trust-vault.md § Memory hygiene.
DEFAULT_IDLE_TTL_SECONDS = 15 * 60

# Memory-DoS bound on payload size. Phase 04 padding-bucket ceiling is 64 MiB
# per specs/trust-vault.md § Padding buckets; capping payload_len reads to that
# ceiling forecloses the malicious-inflated-payload_len memory-DoS (a tampered
# header can declare any 64-bit length; a reader that f.read(payload_len)
# unbounded would allocate gigabytes before the AES-GCM tag check runs).
_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024


# ---------------------------------------------------------------------------
# TrustVault
# ---------------------------------------------------------------------------


class TrustVault:
    """AES-256-GCM-encrypted single-region container with Argon2id-derived key.

    Phase 01 surface (R2-M-02 carry-forward):

    - `await vault.create(initial_payload, passphrase)` — initialize on disk.
    - `await vault.unlock(passphrase)` — verify passphrase, decrypt payload,
      start idle-lock timer.
    - `await vault.read()` — return plaintext payload (raises `VaultLockedError`
      if sealed; raises `AutoLockIdleTimeoutError` if idle-locked since last
      access).
    - `await vault.write(plaintext)` — re-encrypt payload to disk (resets
      idle timer).
    - `await vault.lock()` — zeroize in-memory key, cancel idle timer.
    - `async with vault.unlocked(passphrase): ...` — context manager that
      auto-locks on exit (regardless of exception path).

    Lifecycle invariants:

    1. Constructed-but-not-unlocked is the initial state. `read()` / `write()`
       BEFORE `unlock()` raises `VaultLockedError`.
    2. `unlock(wrong_passphrase)` raises `VaultUnlockFailedError`. Vault stays
       sealed.
    3. `unlock()` then file-level tamper detected: raises
       `VaultMACVerificationFailedError`. Vault stays sealed.
    4. Idle timer fires after `idle_ttl_seconds` of no activity → `lock()`
       runs. Subsequent `read()` raises `AutoLockIdleTimeoutError`.

    Per `rules/patterns.md` § Async Resource Cleanup — `__del__` emits a
    `ResourceWarning` if the vault is still unlocked at GC time; it does NOT
    call `lock()` (would deadlock the GC finalizer thread on the asyncio
    event loop's logging mutex).
    """

    def __init__(
        self,
        vault_path: Path | str,
        *,
        idle_ttl_seconds: float = DEFAULT_IDLE_TTL_SECONDS,
    ) -> None:
        self._vault_path = Path(vault_path)
        if idle_ttl_seconds <= 0:
            raise ValueError("idle_ttl_seconds must be positive")
        self._idle_ttl_seconds = float(idle_ttl_seconds)

        # Sealed-state defaults — `unlock()` populates these.
        self._master_key: bytearray | None = None  # mutable so we can zero it
        self._payload: bytes | None = None
        self._idle_timer_task: asyncio.Task[None] | None = None
        self._last_activity_ts: float = 0.0
        # `_idle_locked` distinguishes "never unlocked" from "unlocked-then-idle-expired"
        # so the typed error matches the spec's two-error contract.
        self._idle_locked: bool = False

    # ------------------------------------------------------------------
    # Public introspection
    # ------------------------------------------------------------------

    @property
    def vault_path(self) -> Path:
        return self._vault_path

    @property
    def is_unlocked(self) -> bool:
        return self._master_key is not None

    @property
    def exists_on_disk(self) -> bool:
        return self._vault_path.exists() and self._vault_path.is_file()

    # ------------------------------------------------------------------
    # Container creation
    # ------------------------------------------------------------------

    async def create(self, initial_payload: bytes, passphrase: str) -> None:
        """Initialize a fresh vault on disk encrypted under `passphrase`.

        Refuses to overwrite an existing file (re-create after destroy is the
        explicit Phase-02 `envoy vault destroy-keys` workflow). Caller MUST
        pass a non-empty passphrase; the vault is sealed after `create()`
        returns — call `unlock()` to bring the payload back into memory.
        """
        if not isinstance(passphrase, str) or not passphrase:
            raise VaultUnlockFailedError("passphrase must be a non-empty string")
        if self._vault_path.exists():
            raise FileExistsError(
                f"vault already exists at {self._vault_path} — use destroy-keys workflow"
            )

        salt = secrets.token_bytes(_SALT_LEN)
        master_key = self._derive_master_key(passphrase, salt)
        try:
            await self._write_container(
                master_key=master_key,
                salt=salt,
                payload=initial_payload,
            )
        finally:
            _zeroize(master_key)

    # ------------------------------------------------------------------
    # Lifecycle (R2-M-02)
    # ------------------------------------------------------------------

    async def unlock(self, passphrase: str) -> None:
        """Argon2id-derive master key from passphrase, AES-256-GCM-decrypt the
        payload, start the idle-lock timer.

        Wrong passphrase raises `VaultUnlockFailedError` (vault stays sealed).
        File-level tamper detected during AAD verification raises
        `VaultMACVerificationFailedError`. Mismatched stored Argon2id params
        raise `Argon2ParameterMismatchError`.
        """
        # Validate passphrase BEFORE the is_unlocked short-circuit so the
        # empty-passphrase contract holds uniformly: an empty passphrase is
        # always rejected with VaultUnlockFailedError, never silently no-op'd
        # because the vault was already open. Defense against zero-cost brute
        # force AND consistent error contract.
        if not isinstance(passphrase, str) or not passphrase:
            raise VaultUnlockFailedError("passphrase must be a non-empty string")
        if self.is_unlocked:
            return  # idempotent
        if not self.exists_on_disk:
            raise FileNotFoundError(f"no vault at {self._vault_path}")

        header_bytes, salt, argon2_params, nonce, ciphertext = self._read_container()
        self._verify_argon2_params(argon2_params)

        master_key = self._derive_master_key(passphrase, salt)
        owned_by_self = False  # H-1: don't zeroize once vault has installed the key
        try:
            aesgcm = AESGCM(bytes(master_key))
            try:
                payload = aesgcm.decrypt(nonce, ciphertext, header_bytes)
            except InvalidTag as exc:
                # AES-GCM cannot distinguish wrong-key from tampered-content from
                # tampered-header — all three produce InvalidTag. Per
                # specs/trust-vault.md § Error taxonomy we surface
                # `VaultUnlockFailedError` for the common-case (wrong passphrase);
                # operators run a separate file-integrity audit if they suspect
                # tamper. Distinguishing the two requires a sentinel-prefix
                # check inside the decrypted payload, which Phase 02 will add
                # alongside the per-region HKDF refactor.
                raise VaultUnlockFailedError(
                    "passphrase derivation failed AES-256-GCM tag verification "
                    "— re-enter passphrase; if persistent, run Shamir recovery"
                ) from exc

            # Successful decrypt — own the master key + payload, start timer.
            # `owned_by_self = True` BEFORE _touch_activity so a failure inside
            # the timer scheduler (e.g., asyncio internals) does NOT trigger
            # the outer zeroize and corrupt the live vault key.
            self._master_key = master_key
            self._payload = payload
            self._idle_locked = False
            owned_by_self = True
            self._touch_activity()
        except Exception:
            # Only zeroize if the vault has NOT taken ownership; otherwise
            # we'd zero out the live key behind self._master_key (H-1).
            if not owned_by_self:
                _zeroize(master_key)
            raise

    async def lock(self) -> None:
        """Cancel idle timer, zeroize master key, drop payload reference.

        Idempotent — calling on an already-locked vault is a no-op.
        """
        # Cancel timer FIRST so it can't fire mid-lock and observe partially
        # cleared state.
        if self._idle_timer_task is not None and not self._idle_timer_task.done():
            self._idle_timer_task.cancel()
            try:
                await self._idle_timer_task
            except asyncio.CancelledError:
                # Expected — we just cancelled it.
                pass
            except Exception:
                # Per rules/zero-tolerance.md Rule 3: a non-cancellation
                # failure in the idle-timer task is unexpected; log loudly
                # so it surfaces in the operator's WARN+ scan, but proceed
                # to lock — the security-critical path (zeroize + drop
                # payload) MUST still run.
                logger.exception("trust_vault.lock.idle_timer_cleanup_failed")
        self._idle_timer_task = None

        if self._master_key is not None:
            _zeroize(self._master_key)
            self._master_key = None
        # Defensive: payload is plaintext-sensitive too. We can't zeroize a
        # `bytes` (immutable), but we drop the reference so it's GC-eligible.
        # Phase 02 will copy payload into a `bytearray` for explicit zeroize.
        self._payload = None

    async def __aenter__(self) -> "TrustVault":
        # NOTE: this enters an ALREADY-UNLOCKED vault (caller called unlock()
        # before entering). `unlocked()` is the convenience wrapper that
        # unlocks on entry.
        if not self.is_unlocked:
            raise VaultLockedError("__aenter__ on a locked vault — call unlock() first")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.lock()

    def unlocked(self, passphrase: str) -> "_UnlockedVaultCM":
        """Return a context manager that unlocks on entry + locks on exit.

        Usage:

            async with vault.unlocked(passphrase) as v:
                payload = await v.read()
        """
        return _UnlockedVaultCM(self, passphrase)

    # ------------------------------------------------------------------
    # Read / write
    # ------------------------------------------------------------------

    async def read(self) -> bytes:
        """Return the in-memory plaintext payload. Resets idle timer."""
        self._require_unlocked()
        self._touch_activity()
        assert self._payload is not None  # for type checker
        return self._payload

    async def write(self, plaintext: bytes) -> None:
        """Re-encrypt and persist `plaintext` to disk. Resets idle timer.

        Atomic write per `rules/trust-plane-security.md` MUST Rule 7:
        write to a sibling temp file, fsync, then `os.replace` so a crash
        mid-write leaves the previous valid container in place.
        """
        self._require_unlocked()
        assert self._master_key is not None  # type checker
        self._payload = plaintext
        # Re-key the salt? No — salt is per-vault, not per-write. The nonce
        # changes on every encrypt (the AAD covers it).
        salt = self._read_existing_salt()
        await self._write_container(
            master_key=self._master_key,
            salt=salt,
            payload=plaintext,
        )
        self._touch_activity()

    # ------------------------------------------------------------------
    # Metadata slot (T-02-35) — JSON envelope inside vault payload
    # ------------------------------------------------------------------
    #
    # Phase 01 carves a minimal metadata slot inside the existing vault
    # payload via a self-discriminating JSON envelope:
    #
    #     {"_etmd_v1": {<top-level metadata dict>}}
    #
    # The envelope discriminator key (`_etmd_v1` = "Envoy Trust MetaData
    # version 1") deliberately avoids the literal substring "envoy" so
    # the unlocked payload bytes carry zero leakage of the product
    # identity — H-06 (per `specs/shamir-recovery.md` line 29) requires
    # that persisted state contain only opaque labels, and while H-06
    # primarily targets holder-facing labels on cards / checklists, the
    # discriminator-key choice extends the H-06 invariant to internal
    # envelope structure as a defense-in-depth measure (a heap-dump
    # forensics attacker scanning for "envoy" finds nothing).
    #
    # `read_metadata()` returns the inner dict; `write_metadata(d)`
    # serializes the envelope and routes through the standard
    # `write(plaintext)` path. Existing callers using `read()` /
    # `write(bytes)` directly are unaffected — the envelope shape is
    # purely a convention layered on top of the bytes API. Vaults that
    # have NEVER had `write_metadata()` called return `{}` from
    # `read_metadata()` (the fallback covers legacy / non-JSON payloads).
    #
    # Phase 02 may promote this to a structured payload region with its
    # own crypto domain key per `specs/trust-vault.md` § File format
    # ("Shamir commitments / ritual state" region). Phase 01's contract
    # is intentionally minimal: persist arbitrary JSON-serializable
    # metadata across lock/unlock cycles for collaborators that need a
    # safe-on-disk slot (T-02-35 DistributionChecklist persister).

    _METADATA_ENVELOPE_KEY = "_etmd_v1"

    async def read_metadata(self) -> dict[str, Any]:
        """Return the metadata dict stored in the vault's payload.

        Returns a deep-copy of the persisted metadata so callers cannot
        accidentally mutate the locally-parsed envelope (per security
        review L-1 on PR #15). Returns an empty dict if the vault has
        never had `write_metadata()` called OR if the payload bytes are
        not a JSON envelope of the expected shape (legacy opaque-bytes
        payloads). The method does NOT raise on shape mismatch — absence
        of the envelope is the same as "no metadata persisted".

        Use cases (Phase 01): T-02-35 DistributionChecklist persister
        stores `{ritual_id -> checklist_dict}` under
        `metadata["shamir_distribution_checklists"]`.

        Raises:
            VaultLockedError: vault is sealed (propagated from `self.read()`).
            AutoLockIdleTimeoutError: idle-lock fired (propagated from
                `self.read()`).
        """
        import copy as _copy
        import json as _json

        payload = await self.read()
        if not payload:
            return {}
        try:
            envelope = _json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as parse_exc:
            # The payload exists but cannot be JSON-decoded as a metadata
            # envelope. This is either (a) a legacy opaque-bytes payload
            # whose owner never wrote a metadata envelope (intentional
            # passthrough) OR (b) corruption / tamper that survived the
            # AES-GCM tag check (extremely unlikely; the tag covers the
            # full payload). We cannot distinguish the two from inside the
            # vault, so we WARN — operators that grep for
            # `trust_vault.read_metadata.parse_failed` see both cases and
            # can investigate. Returning {} preserves the legacy-payload
            # semantics.
            logger.warning(
                "trust_vault.read_metadata.parse_failed",
                extra={
                    "error_type": type(parse_exc).__name__,
                    "payload_len": len(payload),
                },
            )
            return {}
        if not isinstance(envelope, dict):
            return {}
        inner = envelope.get(self._METADATA_ENVELOPE_KEY)
        if not isinstance(inner, dict):
            return {}
        # Deep-copy per security review L-1: a caller mutating the
        # returned dict MUST NOT be able to corrupt other callers'
        # views of the same vault state.
        return _copy.deepcopy(inner)

    async def write_metadata(self, metadata: dict[str, Any]) -> None:
        """Persist `metadata` as a JSON envelope inside the vault's payload.

        Overwrites any prior metadata. Callers that need read-modify-write
        semantics MUST `read_metadata()` first, mutate, then
        `write_metadata()` — there is no atomic compare-and-swap in
        Phase 01.

        **Race window** (per security review H-1 on PR #15, doc-only fix):
        Concurrent async tasks running `read_metadata → mutate →
        write_metadata` cycles against the SAME vault can clobber each
        other's mutations. The auto-lock timer can also fire BETWEEN
        the read and the write of a single task's cycle, raising
        `AutoLockIdleTimeoutError` on the write half. Phase 02 hardening
        adds `update_metadata(callable)` as a vault-level
        compare-and-swap primitive; until then, callers MUST NOT
        interleave concurrent metadata writes against the same vault
        (single-process single-task is the supported topology for
        Phase 01).

        Raises:
            VaultLockedError: vault is sealed.
            AutoLockIdleTimeoutError: idle-lock fired between read and write.
            TypeError: `metadata` is not a dict.
            ValueError: `metadata` contains values that are not
                JSON-serializable (propagated from `json.dumps`).
        """
        import json as _json

        if not isinstance(metadata, dict):
            raise TypeError(f"metadata must be a dict; got {type(metadata).__name__}")
        envelope = {self._METADATA_ENVELOPE_KEY: metadata}
        payload = _json.dumps(envelope, sort_keys=True).encode("utf-8")
        await self.write(payload)

    # ------------------------------------------------------------------
    # Idle-lock timer
    # ------------------------------------------------------------------

    def _touch_activity(self) -> None:
        """Record activity + reset the idle-lock timer.

        Cancel-and-recreate is the simplest correct semantics: the timer
        always counts down from the most recent activity. Observable order:
        (1) cancel old task; (2) update last_activity_ts; (3) start new task.

        Uses `asyncio.create_task` (3.10+) rather than the deprecated
        `asyncio.get_event_loop()` — this method is only ever called from
        an `async` method body so a running loop is guaranteed.
        """
        self._last_activity_ts = time.monotonic()
        if self._idle_timer_task is not None and not self._idle_timer_task.done():
            self._idle_timer_task.cancel()
        # Schedule a new sleep-then-lock task. We don't await the cancellation
        # because cancel is cooperative — the task observes the cancel and
        # exits at the next await. The newly-scheduled task supersedes it.
        self._idle_timer_task = asyncio.create_task(
            self._idle_lock_after_ttl(self._idle_ttl_seconds)
        )

    async def _idle_lock_after_ttl(self, ttl_seconds: float) -> None:
        """Sleep for `ttl_seconds`; if no activity in the meantime, lock.

        Race-safety: capture the task identity into a local BEFORE sleep so
        a concurrent `_touch_activity()` (which mutates self._idle_timer_task)
        does not race with the post-sleep ownership check. Without the local
        capture, the comparison `self._idle_timer_task is current_task()`
        could observe an updated `self._idle_timer_task` set by a fresher
        activity tick that fired between our sleep return and the check.
        """
        self_task = asyncio.current_task()
        try:
            await asyncio.sleep(ttl_seconds)
        except asyncio.CancelledError:
            return  # superseded by a fresher timer
        # Race-safety: only fire if WE (captured task identity) are still
        # the owner of self._idle_timer_task. A cancel-and-recreate that
        # raced with our sleep-return will have installed a NEW task; we
        # exit silently so the auto-lock fires only once per quiescent TTL.
        if self._idle_timer_task is not self_task:
            return
        # Lock without going through `_require_unlocked` (vault MAY have been
        # locked manually between sleep wakeup and this branch).
        if self._master_key is not None:
            _zeroize(self._master_key)
            self._master_key = None
            self._payload = None
            self._idle_locked = True
            logger.info(
                "trust_vault.auto_lock",
                extra={
                    "vault_path": str(self._vault_path),
                    "ttl_seconds": ttl_seconds,
                },
            )

    def _require_unlocked(self) -> None:
        if self._master_key is None:
            if self._idle_locked:
                raise AutoLockIdleTimeoutError(
                    f"vault auto-locked after {self._idle_ttl_seconds:.0f}s idle "
                    "— re-unlock with passphrase"
                )
            raise VaultLockedError("vault is sealed; call unlock(passphrase) first")

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _read_container(self) -> tuple[bytes, bytes, tuple[int, int, int], bytes, bytes]:
        """Read the file header + ciphertext from disk.

        Returns (header_bytes, salt, (m, t, p), nonce, ciphertext_with_tag).
        Header_bytes is the raw 53-byte header used as AES-GCM AAD.
        """
        with self._open_no_follow_symlinks() as f:
            header_bytes = f.read(_HEADER_LEN)
            if len(header_bytes) < _HEADER_LEN:
                raise VaultMACVerificationFailedError(
                    "vault file truncated (header < expected size)"
                )
            magic, version, payload_len, salt, m, t, p, nonce = struct.unpack(
                _HEADER_FMT, header_bytes
            )
            if magic != _MAGIC:
                raise VaultMACVerificationFailedError(
                    f"vault magic bytes mismatch: expected {_MAGIC!r}, got {magic!r}"
                )
            if version != _VERSION:
                raise VaultMACVerificationFailedError(
                    f"vault version mismatch: expected {_VERSION}, got {version}"
                )
            # Memory-DoS guard — a tampered header can declare any 64-bit length;
            # cap reads at the Phase 04 padding-bucket ceiling so an unbounded
            # f.read(payload_len) does not allocate gigabytes before the AES-GCM
            # tag check runs.
            if payload_len > _MAX_PAYLOAD_BYTES:
                raise VaultMACVerificationFailedError(
                    f"vault declared payload_len={payload_len} exceeds max "
                    f"{_MAX_PAYLOAD_BYTES} bytes — refusing read"
                )
            ciphertext = f.read(payload_len)
            if len(ciphertext) != payload_len:
                raise VaultMACVerificationFailedError(
                    "vault file truncated (ciphertext length < declared payload_len)"
                )
        return header_bytes, salt, (m, t, p), nonce, ciphertext

    def _read_existing_salt(self) -> bytes:
        """Read the salt from the on-disk container without decrypting."""
        with self._open_no_follow_symlinks() as f:
            header_bytes = f.read(_HEADER_LEN)
        if len(header_bytes) < _HEADER_LEN:
            raise VaultMACVerificationFailedError(
                "vault file truncated reading salt (header < expected size)"
            )
        _, _, _, salt, _, _, _, _ = struct.unpack(_HEADER_FMT, header_bytes)
        return salt

    def _open_no_follow_symlinks(self):
        """Open the vault file with O_NOFOLLOW so a symlink redirect — e.g. a
        parent-directory writer pointing the vault path at /etc/shadow — is
        rejected at open time rather than silently followed.

        Per `rules/trust-plane-security.md` MUST Rule 1 ("No bare open() for
        record files"). On platforms without O_NOFOLLOW (Windows), the flag
        is not defined; fall back to bare open. Phase 02 platform abstraction
        will add the Windows-equivalent symlink-rejection path.
        """
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(str(self._vault_path), flags)
        except OSError as exc:
            # POSIX raises ELOOP (symbolic link cycle) on O_NOFOLLOW symlink
            # rejection. Surface as the same typed error class as other
            # file-level integrity rejections so callers handle uniformly.
            raise VaultMACVerificationFailedError(
                f"vault open refused (likely symlink redirect): {exc}"
            ) from exc
        return os.fdopen(fd, "rb")

    async def _write_container(self, *, master_key: bytearray, salt: bytes, payload: bytes) -> None:
        """Encrypt `payload` and write the container atomically.

        AAD = header bytes (everything before the ciphertext). Any tamper at
        the header level fails MAC verification on the next unlock.
        """
        nonce = secrets.token_bytes(_NONCE_LEN)
        # The struct.pack writes the ciphertext_len + GCM tag length so a
        # reader can frame the file correctly.
        # AES-GCM tag is appended to ciphertext by `cryptography`; total length
        # is len(plaintext) + _GCM_TAG_LEN.
        payload_len = len(payload) + _GCM_TAG_LEN
        header = struct.pack(
            _HEADER_FMT,
            _MAGIC,
            _VERSION,
            payload_len,
            salt,
            _ARGON2_MEMORY_COST_KIB,
            _ARGON2_TIME_COST,
            _ARGON2_PARALLELISM,
            nonce,
        )
        aesgcm = AESGCM(bytes(master_key))
        ciphertext = aesgcm.encrypt(nonce, payload, header)

        # Atomic write: temp file + fsync + os.replace.
        #
        # Per `rules/trust-plane-security.md` MUST Rule 1 (no bare `open()`
        # for record files) + security review H-2 on PR #15: open the
        # tmpfile via `os.open` with `O_NOFOLLOW | O_EXCL` to defend
        # against an attacker pre-creating the tmp path as a symlink.
        # `O_NOFOLLOW` rejects an existing symlink at the tmp path
        # (would otherwise let the attacker redirect ciphertext writes
        # to `/etc/shadow` or similar). `O_EXCL` rejects any existing
        # file at the path so two parallel writes do not race on the
        # same tmpfile. Mode 0o600 matches the post-replace `chmod`
        # below so file permissions are correct from creation.
        tmp_path = self._vault_path.with_suffix(self._vault_path.suffix + ".tmp")
        self._vault_path.parent.mkdir(parents=True, exist_ok=True)
        # Best-effort cleanup of any orphaned tmp from a prior crash —
        # `O_EXCL` would otherwise refuse the create.
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(tmp_path), flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(header)
                f.write(ciphertext)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            # On any failure (write error, cancellation), unlink the
            # tmp file before propagating so retries do not collide
            # with `O_EXCL`.
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise
        os.replace(tmp_path, self._vault_path)
        # Restrictive permissions per
        # rules/trust-plane-security.md MUST Rule 6 (database file permissions).
        # The tmp file was opened with mode 0o600, but `os.replace` does NOT
        # copy permissions across filesystems on every POSIX implementation
        # — explicit chmod on the final path is the structural guard.
        if os.name == "posix":
            try:
                os.chmod(self._vault_path, 0o600)
            except OSError:
                # Disk-full / immutable-bit / FS-without-chmod: log loudly
                # so the operator notices the vault may be world-readable.
                # Per rules/zero-tolerance.md Rule 3 and rules/observability.md
                # Rule 5, silent swallow on a security-critical permission
                # set is BLOCKED.
                logger.warning(
                    "trust_vault.write.chmod_failed",
                    extra={"path_repr": repr(str(self._vault_path))},
                )

    # ------------------------------------------------------------------
    # Shamir export / import hooks (T-01-14)
    # ------------------------------------------------------------------

    async def export_master_key_for_shamir(self) -> bytes:
        """Return an independent 32-byte copy of the master key for Shamir splitting.

        Per `specs/shamir-recovery.md` § Algorithm: SLIP-0039 Shamir splits
        the 32-byte master key (AES-256 key) — NOT the passphrase. The
        ShamirRitualCoordinator (T-15, Wave 2) calls this hook to obtain
        the master key bytes to split into m-of-n shards.

        Vault MUST be unlocked. Returns a fresh `bytes` (immutable) buffer
        independent of the in-vault `bytearray` — mutating the in-vault key
        does NOT affect the returned bytes and vice versa.

        **Caller-side memory hygiene** (per `rules/trust-plane-security.md`
        MUST NOT Rule 3): the returned `bytes` is IMMUTABLE — Python provides
        no API to overwrite its bytes in-place. The caller MUST:

        1. Treat the returned bytes as a sensitive secret with the same
           memory residency discipline as the vault's own master key.
        2. For best-effort zeroize, copy into a `bytearray` immediately and
           overwrite the bytearray slot once Shamir splitting completes;
           drop the original `bytes` reference to release it for GC.
        3. NEVER log / print / serialize the returned bytes.

        TODO(T-15): wrap in `Sensitive[bytes]` typed context manager that
        auto-zeroes on `__exit__` (Phase 02 hardening alongside the
        Secure-Enclave binding).
        """
        self._require_unlocked()
        self._touch_activity()
        assert self._master_key is not None  # type checker
        return bytes(self._master_key)

    async def import_master_key_from_shamir(self, reconstructed: bytes) -> None:
        """Install a Shamir-reconstructed 32-byte master key as the vault key.

        Per `specs/shamir-recovery.md` § Recovery flow: Shamir reconstruction
        produces the SAME 32-byte master key the original Argon2id would
        have derived from the passphrase. The on-disk salt + Argon2id params
        are preserved unchanged; this hook simply installs the reconstructed
        key as the vault's in-memory master key and decrypts the on-disk
        payload under it. If the reconstructed key is wrong, AES-GCM tag
        verification fails and `VaultUnlockFailedError` is raised — the
        vault stays sealed.

        The vault MUST exist on disk. The vault MUST be sealed at the start
        of the call (we install a NEW master key rather than rotating an
        existing one). Phase 02 adds an explicit `rotate_master_key`
        operation for the post-recovery passphrase change.

        **Caller-side memory hygiene** (per `rules/trust-plane-security.md`
        MUST NOT Rule 3): the caller's `reconstructed` bytes is IMMUTABLE
        — Python provides no API to overwrite its contents in-place. The
        vault makes its own internal `bytearray` copy (which IS zeroized on
        `lock()`), so the caller's `reconstructed` copy survives until GC.
        The caller is responsible for minimizing residency of the
        reconstructed bytes — e.g., by passing a freshly constructed bytes
        object and dropping the reference immediately after this call
        returns.

        TODO(T-15): accept `Sensitive[bytes]` from the
        ShamirRitualCoordinator that auto-zeroes the caller-side bytes on
        context exit (Phase 02 hardening).
        """
        if self.is_unlocked:
            raise VaultLockedError(
                "import_master_key_from_shamir requires sealed vault — "
                "call lock() first OR construct a fresh adapter"
            )
        if not isinstance(reconstructed, (bytes, bytearray, memoryview)):
            raise MasterKeySizeError(
                f"reconstructed master key must be bytes-like; "
                f"got {type(reconstructed).__name__}"
            )
        if len(reconstructed) != _ARGON2_KEY_LEN:
            raise MasterKeySizeError(
                f"reconstructed master key must be exactly {_ARGON2_KEY_LEN} bytes "
                f"(AES-256); got {len(reconstructed)} bytes — refusing import"
            )
        if not self.exists_on_disk:
            raise FileNotFoundError(f"no vault at {self._vault_path}")

        # Read the existing container's salt + nonce + ciphertext so we can
        # decrypt with the reconstructed key. If the key is wrong, AES-GCM
        # tag verification raises InvalidTag → VaultUnlockFailedError.
        header_bytes, salt, argon2_params, nonce, ciphertext = self._read_container()
        self._verify_argon2_params(argon2_params)

        master_key = bytearray(reconstructed)  # mutable copy so we can zero it
        owned_by_self = False  # H-1: don't zeroize once vault has installed the key
        try:
            aesgcm = AESGCM(bytes(master_key))
            try:
                payload = aesgcm.decrypt(nonce, ciphertext, header_bytes)
            except InvalidTag as exc:
                raise VaultUnlockFailedError(
                    "Shamir-reconstructed master key failed AES-256-GCM tag "
                    "verification — reconstructed key does NOT decrypt this "
                    "vault. Likely causes: wrong vault file; corrupted shards; "
                    "shards from a different ritual."
                ) from exc

            self._master_key = master_key
            self._payload = payload
            self._idle_locked = False
            owned_by_self = True
            self._touch_activity()
        except Exception:
            # Only zeroize if the vault has NOT taken ownership; otherwise
            # we'd zero out the live key behind self._master_key (H-1).
            if not owned_by_self:
                _zeroize(master_key)
            raise

    # ------------------------------------------------------------------
    # KDF + parameter checks
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_master_key(passphrase: str, salt: bytes) -> bytearray:
        """Argon2id derive a 32-byte master key. Returns mutable bytearray so
        the caller can zeroize it on lock."""
        derived = hash_secret_raw(
            secret=passphrase.encode("utf-8"),
            salt=salt,
            time_cost=_ARGON2_TIME_COST,
            memory_cost=_ARGON2_MEMORY_COST_KIB,
            parallelism=_ARGON2_PARALLELISM,
            hash_len=_ARGON2_KEY_LEN,
            type=Type.ID,
        )
        return bytearray(derived)

    @staticmethod
    def _verify_argon2_params(params: tuple[int, int, int]) -> None:
        """Reject vaults with non-canonical Argon2id parameters.

        Phase 01 hard-codes the canonical (m=2^17, t=3, p=1). A vault that
        differs MUST NOT be silently re-derived — the Foundation publishes
        parameter migrations explicitly per `specs/trust-vault.md` § Error
        taxonomy `Argon2ParameterMismatchError`.
        """
        m, t, p = params
        if (m, t, p) != (_ARGON2_MEMORY_COST_KIB, _ARGON2_TIME_COST, _ARGON2_PARALLELISM):
            raise Argon2ParameterMismatchError(
                f"vault Argon2id params (m={m}, t={t}, p={p}) differ from "
                f"binary expected ({_ARGON2_MEMORY_COST_KIB}, {_ARGON2_TIME_COST}, "
                f"{_ARGON2_PARALLELISM}) — run vault migration"
            )

    # ------------------------------------------------------------------
    # GC hygiene
    # ------------------------------------------------------------------

    def __del__(self, _warnings=warnings) -> None:  # noqa: D401
        # Only emit a warning. Calling lock() here would touch the asyncio
        # event loop from a finalizer thread → deadlock per
        # rules/patterns.md § Async Resource Cleanup.
        # `_warnings` is captured as a default argument so this finalizer
        # survives interpreter shutdown — at shutdown the global `warnings`
        # module may already be torn down, but the captured reference stays
        # bound. Per rules/patterns.md § "Use def __del__(self, _warnings=...)
        # signature (survives interpreter shutdown)".
        # Use getattr so partially-constructed instances (where __init__
        # raised before assigning _master_key) finalize cleanly.
        master_key = getattr(self, "_master_key", None)
        if master_key is not None:
            vault_path = getattr(self, "_vault_path", "<unknown>")
            _warnings.warn(
                f"TrustVault({vault_path}) GC'd while unlocked — "
                "call await vault.lock() or use `async with vault.unlocked(...)`",
                ResourceWarning,
                stacklevel=2,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _zeroize(buf: bytearray) -> None:
    """Best-effort overwrite of mutable byte buffer.

    Python's GC may have already moved the original bytes; zeroize the
    bytearray's slot to minimize residency. Phase 02 will add `ctypes.memset`
    / `cryptography.utils.constant_time.bytes_eq` cleansing per platform.
    """
    for i in range(len(buf)):
        buf[i] = 0


class _UnlockedVaultCM:
    """Context manager returned by `vault.unlocked(passphrase)`."""

    def __init__(self, vault: TrustVault, passphrase: str) -> None:
        self._vault = vault
        self._passphrase = passphrase

    async def __aenter__(self) -> TrustVault:
        await self._vault.unlock(self._passphrase)
        return self._vault

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._vault.lock()


__all__ = [
    "TrustVault",
    "DEFAULT_IDLE_TTL_SECONDS",
]
