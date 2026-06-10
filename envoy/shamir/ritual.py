"""ShamirRitualCoordinator — orchestrates the 6-step Phase 01 backup ritual.

Per shard 15 (`workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md`)
§ 3.1 — wraps `kailash.trust.vault.shamir.generate(...)` with the
6-step ritual sequence:

    1. Read master-key bytes from `MasterKeySource` (T-01-14 hook).
    2. Call `ShamirGenerator(secret=master_key, ritual=ShamirRitual(t,n))`.
    6. Zeroize master-key (immediately, in `finally` after step 2 — even
       on collaborator failure in steps 3-5, the master key MUST NOT
       outlive step 2).
    3. `CommitmentBinder.bind_to_genesis(principal_id, shards)`.
    4. `PaperRenderer.render(shard, slot_label, sequence)` for each shard.
    5. `ChecklistPersister.persist(DistributionChecklist(...))`.

Step ordering note: step 6 (zeroize) fires AFTER step 2 (generate) but
BEFORE steps 3-5. The 6-step labeling matches `specs/shamir-recovery.md`
+ shard 15 § 3.1 ordering; the coordinator's runtime sequence is
`1 → 2 → 6 → 3 → 4 → 5` to minimize master-key residency.

T-02-34 invariants (per
`workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md`):

1. **6-step ritual sequence** — every step fires exactly once per ritual
   in the documented order.
2. **share count = 5** — Phase 01 default per
   `specs/shamir-recovery.md` § Default threshold.
3. **threshold = 3** — Phase 01 default per same.
4. **master-key zeroization** — the bytes returned by `MasterKeySource`
   are overwritten in a local `bytearray` and dropped before the result
   is returned. `MasterKeyZeroizationError` is raised on failure.

T-02-35 (next shard) extends this module with concrete `CommitmentBinder`
+ `PaperRenderer` + `ChecklistPersister` implementations. T-02-37 wires
real `kailash.trust.vault.shamir` into a Tier 2 round-trip.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone

from envoy.shamir.commitments import compute_commitment
from envoy.shamir.errors import (
    MasterKeyZeroizationError,
    RitualPreconditionError,
)
from envoy.shamir.types import (
    ChecklistPersister,
    CommitmentBinder,
    DistributionChecklist,
    MasterKeySource,
    PaperRenderer,
    RitualResult,
    ShamirGenerator,
)

logger = logging.getLogger(__name__)


# Master-key length — 32 bytes (AES-256) per `specs/trust-vault.md` § Encryption.
# Mirrors `envoy.trust.vault._ARGON2_KEY_LEN`; duplicated here to avoid coupling
# the shamir module to the vault module's private constant.
_MASTER_KEY_LEN = 32

# SLIP-0039 group limit — per `kailash.trust.vault.shamir.ShamirRitual`
# documentation; values outside [2, 16] raise at the kailash wrapper level.
_MIN_TOTAL_SHARDS = 2
_MAX_TOTAL_SHARDS = 16
_MIN_THRESHOLD = 2  # Phase 01 default 3-of-5; minimum supported per spec.

# Phase 01 default ritual parameters per
# `specs/shamir-recovery.md` § Default threshold.
DEFAULT_THRESHOLD = 3
DEFAULT_TOTAL_SHARDS = 5


def _default_shamir_generator() -> ShamirGenerator:
    """Bind the production `kailash.trust.vault.shamir.generate` callable.

    Lazy-resolved so the import lands at construction time (not module
    import time) — keeping `envoy.shamir` importable even when the
    `kailash[shamir]` extra is not installed (the actual call still
    requires `shamir-mnemonic` per kailash's lazy-import contract).
    """
    from kailash.trust.vault.shamir import generate

    return generate


def _make_ritual_id(threshold: int, total_shards: int, created_at: datetime) -> str:
    """Per `specs/shamir-recovery.md` § Schema DistributionChecklist:
    "ritual_id = sha256 of the (threshold, total, created_at) tuple".

    Mixes 8 bytes of `secrets.token_bytes` salt to defeat collision under
    same-microsecond ritual construction (rev-4): `threshold ∈ {2..5}`
    and `total_shards ∈ {2..16}` make the (threshold, total, created_at)
    tuple's entropy bottleneck `created_at` resolution. With ISO-format
    isoformat at microsecond precision, two rituals constructed in the
    same microsecond would collide; the salt eliminates that window
    without losing the spec-mandated deterministic prefix shape (sha256
    hex output preserves the wire form).
    """
    salt = secrets.token_bytes(8)
    seed = f"{threshold}:{total_shards}:{created_at.isoformat()}".encode() + salt
    return hashlib.sha256(seed).hexdigest()


def _opaque_slot_labels(total_shards: int) -> tuple[str, ...]:
    """Per `specs/shamir-recovery.md` § Card format (H-06 fix): opaque
    slot labels only (NO real names, NO 'Envoy' string in persisted form).
    """
    return tuple(f"slot-{i}" for i in range(1, total_shards + 1))


class ShamirRitualCoordinator:
    """Orchestrate the first-time-user Trust Vault Shamir backup ritual.

    Construction injects the 5 collaborators (master-key source +
    generator + commitment binder + paper renderer + checklist persister).
    The `ShamirGenerator` defaults to `kailash.trust.vault.shamir.generate`;
    the other four are required arguments because their concrete
    implementations land in T-02-35 (no sensible default exists yet).

    Per `rules/facade-manager-detection.md` Rule 3 (Constructor receives
    explicit dependencies), no global lookups + no self-construction of
    collaborators.
    """

    def __init__(
        self,
        master_key_source: MasterKeySource,
        commitment_binder: CommitmentBinder,
        paper_renderer: PaperRenderer,
        checklist_persister: ChecklistPersister,
        principal_id: str,
        *,
        shamir_generator: ShamirGenerator | None = None,
    ) -> None:
        if not principal_id:
            raise RitualPreconditionError(
                "principal_id must be a non-empty string",
                user_message=(
                    "Cannot start backup ritual — no user identity is bound "
                    "to this Envoy install yet. Complete the Boundary "
                    "Conversation first."
                ),
            )

        self._master_key_source = master_key_source
        self._commitment_binder = commitment_binder
        self._paper_renderer = paper_renderer
        self._checklist_persister = checklist_persister
        self._principal_id = principal_id
        self._shamir_generator: ShamirGenerator = (
            shamir_generator if shamir_generator is not None else _default_shamir_generator()
        )

    @property
    def principal_id(self) -> str:
        return self._principal_id

    async def run_first_time_ritual(
        self,
        *,
        threshold: int = DEFAULT_THRESHOLD,
        total_shards: int = DEFAULT_TOTAL_SHARDS,
        passphrase: bytes = b"",
    ) -> RitualResult:
        """Execute the 6-step Phase 01 ritual.

        Returns a `RitualResult` carrying ritual metadata + raw shards +
        commitments + paper cards + the persisted DistributionChecklist.
        Master-key bytes are NEVER part of the return value — they are
        zeroized between step 2 and step 3.

        Raises:
            RitualPreconditionError: invalid threshold/total_shards or
                the master-key source returned bytes of unexpected size.
            MasterKeyZeroizationError: the post-generate zeroize step
                failed (non-recoverable; see error docstring).
            Any error raised by an injected collaborator (steps 3-5);
                step 6 (zeroize) fires before the propagation.
        """
        self._validate_parameters(threshold=threshold, total_shards=total_shards)

        created_at = datetime.now(timezone.utc)
        ritual_id = _make_ritual_id(threshold, total_shards, created_at)
        slot_labels = _opaque_slot_labels(total_shards)

        # principal_id may be a pseudonym (low risk) OR an email-shaped
        # / DID-shaped identifier (PII-adjacent). Per
        # `rules/observability.md` Rule 8 (Schema-Revealing Field Names
        # MUST Be DEBUG Or Hashed) + Rule 4 (Never Log PII), default-deny
        # at INFO via an 8-char sha256 prefix. Raw value flows at DEBUG
        # only for incident triage. The hash is non-reversible and the
        # 8-char window keeps logs readable while preserving cross-event
        # correlation within a single principal.
        principal_hash = hashlib.sha256(self._principal_id.encode("utf-8")).hexdigest()[:8]

        logger.info(
            "shamir.ritual.start",
            extra={
                "ritual_id": ritual_id,
                "principal_hash": principal_hash,
                "threshold": threshold,
                "total_shards": total_shards,
            },
        )
        logger.debug(
            "shamir.ritual.principal",
            extra={"ritual_id": ritual_id, "principal_id": self._principal_id},
        )

        # Step 1 + 2 + 6: master-key fetch, generate, zeroize.
        # Held in a `bytearray` (mutable) so step 6 can overwrite the
        # in-memory bytes; the immutable `bytes` returned by the source
        # is dropped to GC immediately after the bytearray copy.
        shards = await self._fetch_split_and_zeroize(
            threshold=threshold,
            total_shards=total_shards,
            passphrase=passphrase,
        )

        # Step 3: bind shard public commitments to Genesis Record.
        # **L-2 re-architecture (T-02-35):** the coordinator computes
        # commitments LOCALLY (sha256 over `serialize_shard(shard)`) and
        # passes the pre-computed list to the binder. The binder is now
        # STORAGE-ONLY — it cannot substitute commitments for a different
        # secret because the coordinator owns the computation. See
        # `envoy/shamir/commitments.py` + `envoy/shamir/types.py`
        # CommitmentBinder docstring for the full failure-mode analysis.
        commitments = [compute_commitment(shard) for shard in shards]
        await self._commitment_binder.bind_to_genesis(self._principal_id, commitments)

        # Step 4: render each shard via paper renderer (H-06: opaque slot label).
        paper_cards = tuple(
            self._paper_renderer.render(shard, slot_labels[i], (i + 1, total_shards))
            for i, shard in enumerate(shards)
        )

        # Step 5: persist DistributionChecklist (opaque slot labels only).
        checklist = DistributionChecklist(
            ritual_id=ritual_id,
            threshold=threshold,
            total_shards=total_shards,
            slot_labels=slot_labels,
            created_at=created_at,
        )
        await self._checklist_persister.persist(checklist)

        logger.info(
            "shamir.ritual.ok",
            extra={
                "ritual_id": ritual_id,
                "principal_hash": principal_hash,
                "shard_count": len(shards),
            },
        )

        return RitualResult(
            ritual_id=ritual_id,
            shards=tuple(tuple(shard) for shard in shards),
            threshold=threshold,
            total_shards=total_shards,
            created_at=created_at,
            commitments=tuple(commitments),
            paper_cards=paper_cards,
            checklist=checklist,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_parameters(self, *, threshold: int, total_shards: int) -> None:
        if not (_MIN_TOTAL_SHARDS <= total_shards <= _MAX_TOTAL_SHARDS):
            raise RitualPreconditionError(
                f"total_shards must be between {_MIN_TOTAL_SHARDS} and "
                f"{_MAX_TOTAL_SHARDS}; got {total_shards}",
                user_message=(
                    f"You asked for {total_shards} cards, but Envoy supports "
                    f"between {_MIN_TOTAL_SHARDS} and {_MAX_TOTAL_SHARDS}. "
                    "Try 5 (the default) for the Phase 01 ritual."
                ),
            )
        if threshold < _MIN_THRESHOLD or threshold > total_shards:
            raise RitualPreconditionError(
                f"threshold must be between {_MIN_THRESHOLD} and total_shards "
                f"({total_shards}); got {threshold}",
                user_message=(
                    f"You asked for any {threshold} of {total_shards} cards "
                    f"to recover. Threshold must be at least "
                    f"{_MIN_THRESHOLD} and no more than the total card count."
                ),
            )

    async def _fetch_split_and_zeroize(
        self,
        *,
        threshold: int,
        total_shards: int,
        passphrase: bytes,
    ) -> list[list[str]]:
        """Steps 1 + 2 + 6 — fetch master key, split, zeroize.

        Step 6 (zeroize) is the structural defense per
        `rules/trust-plane-security.md` MUST NOT Rule 3: master-key bytes
        MUST NOT outlive the call site that needed them. The runtime
        sequence is:

        1. **Two-phase zeroize.** First, deterministic zero-fill
           (`master_key_buf[:] = bytes(N)`) — guaranteed even if entropy
           sources are unavailable. THEN best-effort random overwrite
           via `secrets.token_bytes(N)` to distinguish post-zeroize
           state from uninitialized memory in heap-dump forensics. If
           the random overwrite raises (e.g. entropy failure), the
           master key is ALREADY gone (zero-fill ran first) — H-2 fix.
        2. **Atomic slice assignment.** Both overwrites use slice
           assignment (`buf[:] = src`) which is one CPython opcode for
           bytearrays — atomic w.r.t. signal handlers, async
           cancellation, and `KeyboardInterrupt` (H-1 fix). The
           previous byte-by-byte loop allowed partial overwrite if
           cancelled mid-loop.

        **Master-key residency window (honest accounting):** The
        coordinator zeroizes ONLY the local `master_key_buf`. Once the
        bytearray is passed to `kailash.trust.vault.shamir.generate(...)`
        (verified at PR-time to accept bytearray directly per its
        `isinstance(secret, (bytes, bytearray))` guard at
        `kailash/trust/vault/shamir.py`), the kailash wrapper's frame
        locals AND the underlying `shamir-mnemonic` library's internal
        buffers may retain references until Python GC reclaims them —
        out of envoy's structural reach. Passing the bytearray DIRECTLY
        (rather than `bytes(master_key_buf)`) eliminates ONE intermediate
        immutable copy at the boundary; remaining residency is bounded
        by the `generate(...)` frame's lifetime. The `del` of the
        original bytes from `MasterKeySource` and the slice-assignment
        zeroize of the bytearray are the two structural defenses envoy
        controls (C-1 fix).

        **Trust boundary on `MasterKeySource`** (H-4 — architectural,
        deferred): the Protocol-injected source is fully trusted to
        return the correct master key for `principal_id`. A malicious
        source could inject bytes from a different vault and have them
        bound to this principal's Genesis Record (committed-but-wrong-
        secret). Phase 01 trust boundary IS the locally-installed
        envoy package; T-02-43 (Boundary Conversation S8 wiring) and
        Phase 02 hardening will add `master_key_fingerprint` verification
        against Genesis Record at fetch time.
        """
        from kailash.trust.vault.shamir import ShamirRitual

        # Step 1.
        master_key_bytes = await self._master_key_source.export_master_key_for_shamir()
        if not isinstance(master_key_bytes, (bytes, bytearray, memoryview)):
            raise RitualPreconditionError(
                f"master_key_source returned {type(master_key_bytes).__name__}; "
                f"expected bytes-like",
                user_message=(
                    "Backup ritual cannot continue — the Trust Vault did not "
                    "return a valid master key. Please relock and retry."
                ),
            )
        if len(master_key_bytes) != _MASTER_KEY_LEN:
            raise RitualPreconditionError(
                f"master key must be exactly {_MASTER_KEY_LEN} bytes "
                f"(AES-256); got {len(master_key_bytes)} bytes",
                user_message=(
                    "Backup ritual cannot continue — the Trust Vault returned "
                    "an unexpected key size. This is a bug; please report it."
                ),
            )

        # Copy into a mutable bytearray so step 6 can overwrite it
        # in-place. CPython `bytes` is immutable (no in-place overwrite
        # API); dropping the reference is the best caller-side defense.
        # `del master_key_bytes` rebinds this frame's local — `MasterKeySource`
        # is responsible for its own zeroization upstream per the
        # TrustStoreAdapter docstring (`envoy/trust/vault.py:561`).
        master_key_buf = bytearray(master_key_bytes)
        del master_key_bytes

        try:
            # Step 2.
            ritual_spec = ShamirRitual(threshold=threshold, total_shards=total_shards)
            # Pass the bytearray DIRECTLY — verified at PR-time that
            # kailash.trust.vault.shamir.generate accepts both bytes
            # AND bytearray per its `isinstance(secret, (bytes, bytearray))`
            # guard. Passing `bytes(master_key_buf)` here would create
            # an additional immutable copy that survives in the kailash
            # frame locals beyond envoy's reach (C-1 fix).
            shards = self._shamir_generator(
                # Deliberate mutable bytearray (C-1: avoid an immutable bytes
                # copy surviving in kailash frame locals); ShamirGenerator
                # accepts the buffer protocol at runtime.
                master_key_buf,  # type: ignore[arg-type]
                ritual_spec,
                passphrase=passphrase,
            )
        finally:
            # Step 6 — two-phase zeroize. Deterministic zero-fill FIRST
            # so the master key is gone even if entropy is unavailable
            # (H-2 fix). Slice assignment is one CPython opcode —
            # atomic w.r.t. cancellation/signals (H-1 fix). The optional
            # random overwrite then distinguishes post-zeroize state from
            # uninitialized memory in heap-dump forensics.
            buf_len = len(master_key_buf)
            master_key_buf[:] = bytes(buf_len)  # deterministic zero-fill
            try:
                master_key_buf[:] = secrets.token_bytes(buf_len)
            except Exception as zeroize_err:  # pragma: no cover — defensive
                # The master key is ALREADY zeroed at this point; the
                # random-overwrite step is best-effort hardening only.
                # Surface the failure loudly so operators can treat the
                # entropy outage as a system-health concern, but the
                # caller-side memory-residency contract IS already
                # satisfied by the deterministic zero-fill above.
                raise MasterKeyZeroizationError(
                    f"failed to apply random overwrite after zero-fill: {zeroize_err!r}",
                    user_message=(
                        "Backup ritual completed share generation. The master "
                        "key has been securely zeroed in memory, but a final "
                        "best-effort hardening step failed (likely an entropy-"
                        "source outage). Your shards are valid; consider "
                        "investigating system entropy availability before "
                        "running another ritual."
                    ),
                ) from zeroize_err

        # Defensive: validate the generator honored the requested shard
        # count. A generator that returns fewer than total_shards would
        # silently violate invariant #2 (share count = 5).
        if len(shards) != total_shards:
            raise RitualPreconditionError(
                f"shamir_generator returned {len(shards)} shards; " f"expected {total_shards}",
                user_message=(
                    "Backup ritual could not produce the expected number of "
                    "cards. This is a bug; please report it."
                ),
            )

        return shards


__all__ = [
    "ShamirRitualCoordinator",
    "DEFAULT_THRESHOLD",
    "DEFAULT_TOTAL_SHARDS",
]
