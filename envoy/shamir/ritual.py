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
    """
    seed = f"{threshold}:{total_shards}:{created_at.isoformat()}".encode("utf-8")
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

        logger.info(
            "shamir.ritual.start",
            extra={
                "ritual_id": ritual_id,
                "principal_id": self._principal_id,
                "threshold": threshold,
                "total_shards": total_shards,
            },
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
        commitments = await self._commitment_binder.bind_to_genesis(self._principal_id, shards)

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
                "principal_id": self._principal_id,
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
        MUST NOT outlive the call site that needed them. The local
        `bytearray` IS overwritten via `secrets.token_bytes` rather than
        zeros to make the post-zeroize state distinguishable from
        uninitialized memory in heap dumps.
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
        # in-place. The original `bytes` object is immutable in CPython
        # (no in-place overwrite API); dropping the reference is the
        # best caller-side defense per the TrustStoreAdapter docstring
        # (`envoy/trust/vault.py:561`).
        master_key_buf = bytearray(master_key_bytes)
        del master_key_bytes  # drop the immutable copy ASAP

        try:
            # Step 2.
            ritual_spec = ShamirRitual(threshold=threshold, total_shards=total_shards)
            shards = self._shamir_generator(
                bytes(master_key_buf),
                ritual_spec,
                passphrase=passphrase,
            )
        finally:
            # Step 6 — zeroize. Overwrite with random bytes (rather
            # than zeros) so post-zeroize residency is distinguishable
            # from uninitialized memory in heap-dump forensics.
            try:
                random_overwrite = secrets.token_bytes(len(master_key_buf))
                for i in range(len(master_key_buf)):
                    master_key_buf[i] = random_overwrite[i]
            except Exception as zeroize_err:  # pragma: no cover — defensive
                raise MasterKeyZeroizationError(
                    f"failed to zeroize master-key bytearray: {zeroize_err!r}",
                    user_message=(
                        "Backup ritual completed share generation, but a "
                        "memory-hygiene step failed afterward. Please lock "
                        "your vault, restart Envoy, and verify this Envoy "
                        "process is no longer running before continuing."
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
