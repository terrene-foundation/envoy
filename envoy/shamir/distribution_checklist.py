"""DistributionChecklist persister — opaque-slot-label storage in Trust Vault.

Per `specs/shamir-recovery.md` § Card format (line 29) — H-06 fix:
> Distribution checklist persists only opaque slot labels in Trust Vault;
> real names optional + in hidden envelope (Phase 04) only.

The persister stores the JSON-serialized `DistributionChecklist.to_dict()`
keyed by `ritual_id` inside the Trust Vault's metadata slot
(`metadata["shamir_distribution_checklists"][ritual_id]`). Per shard 15
§ 3.5: persistence MUST round-trip across vault lock/unlock cycles, and
the persisted bytes MUST contain ONLY opaque slot labels — never real
holder names, never the literal string "Envoy".

H-06 enforcement at persistence time: every checklist about to be written
is structurally validated — `slot_labels` MUST be a tuple where each
entry is a non-empty string AND lacks the forbidden token "envoy"
(case-insensitive). The Tier 1 round-trip test asserts this invariant
holds across the full vault unlock → write → lock → re-unlock → read
cycle.

Per `rules/facade-manager-detection.md` Rule 3 (Constructor receives
explicit dependencies): `TrustVaultChecklistPersister` takes its
collaborators (`trust_vault`, `principal_id`) at construction time. No
global lookups, no self-construction of vault instances.

Per `rules/patterns.md` § Paired Public Surface — Consistent Async-ness:
`persist` is async to match the TrustVault's async surface
(`vault.read_metadata` / `vault.write_metadata` are async per the vault's
async I/O contract).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol, runtime_checkable

from envoy.shamir.errors import ChecklistPersisterError, EnvoyLabelOnCardError
from envoy.shamir.types import DistributionChecklist
from envoy.trust.errors import (
    AutoLockIdleTimeoutError,
    VaultLockedError,
)

logger = logging.getLogger(__name__)


# Vault metadata top-level key per shard 15 § 3.5.
_METADATA_KEY_CHECKLISTS = "shamir_distribution_checklists"

# H-06 enforcement is three-layer per security review M-1 + M-2 on PR #15.
# (1) Whitelist regex `^slot-\d+$` — primary defense, defeats Unicode
#     confusables + control-char + name attacks.
# (2) ASCII-only check — explicit Unicode-confusable rejection.
# (3) Substring blacklist — defense-in-depth safety net for any future
#     relaxation that admits non-`slot-N` labels.
# All three duplicated from `envoy/shamir/paper.py` rather than imported,
# to avoid cross-module coupling — the H-06 rule comes from
# `specs/shamir-recovery.md` line 29 and is enforced independently at
# every site that persists slot labels.
_OPAQUE_SLOT_LABEL_RE = re.compile(r"^slot-\d+$")
_FORBIDDEN_LABEL_TOKENS: tuple[str, ...] = ("envoy",)


@runtime_checkable
class _MinimalVault(Protocol):
    """Minimal vault surface the persister depends on.

    Defined as a Protocol (not an `envoy.trust.vault.TrustVault` import)
    so the Tier 1 test can pass a fake vault without dragging the full
    AES-GCM container infrastructure into a unit test. Tier 2 / Tier 3
    pass the real `TrustVault`.
    """

    @property
    def is_unlocked(self) -> bool: ...

    async def read_metadata(self) -> dict[str, Any]: ...

    async def write_metadata(self, metadata: dict[str, Any]) -> None: ...


def _validate_checklist_slot_labels(checklist: DistributionChecklist) -> None:
    """H-06 structural defense at persistence time.

    Raises `EnvoyLabelOnCardError` if any slot_label in the checklist
    contains the forbidden token "envoy" (case-insensitive) OR is empty.
    The persister is the LAST gate before bytes hit disk — even if the
    coordinator's `_opaque_slot_labels()` produced clean labels, a
    malicious / careless caller constructing a `DistributionChecklist`
    directly bypasses that helper. This check closes the gap.
    """
    if not checklist.slot_labels:
        raise EnvoyLabelOnCardError(
            "DistributionChecklist.slot_labels is empty",
            user_message=(
                "Backup checklist cannot be saved — no card slots are "
                "recorded. Re-run the backup ritual to regenerate the "
                "checklist."
            ),
        )
    for label in checklist.slot_labels:
        if not isinstance(label, str) or not label:
            raise EnvoyLabelOnCardError(
                f"slot_label must be a non-empty string; got {label!r}",
                user_message=(
                    "Backup checklist cannot be saved — one of the card "
                    "slot labels is malformed. This is a bug; please "
                    "report it."
                ),
            )
        # Layer 1 — ASCII-only (Unicode confusable defense).
        if not label.isascii():
            raise EnvoyLabelOnCardError(
                f"slot_label {label!r} contains non-ASCII characters — "
                f"H-06 defense rejects Unicode confusables.",
                user_message=(
                    "Backup checklist cannot be saved — a card slot label "
                    "contains special characters or look-alike letters. "
                    "Re-run the backup ritual to regenerate the checklist."
                ),
            )
        # Layer 2 — whitelist regex (primary defense).
        if not _OPAQUE_SLOT_LABEL_RE.fullmatch(label):
            raise EnvoyLabelOnCardError(
                f"slot_label {label!r} does not match opaque pattern "
                f"`^slot-\\d+$` — H-06 enforcement per "
                f"specs/shamir-recovery.md line 29.",
                user_message=(
                    "Backup checklist cannot be saved — a card slot label "
                    "does not use the standard opaque form (slot-1, "
                    "slot-2, ...). Re-run the backup ritual to regenerate "
                    "the checklist."
                ),
            )
        # Layer 3 — substring blacklist (defense-in-depth, redundant
        # with whitelist but kept as belt-and-suspenders).
        lowered = label.lower()
        for token in _FORBIDDEN_LABEL_TOKENS:
            if token in lowered:
                raise EnvoyLabelOnCardError(
                    f"slot_label {label!r} contains forbidden token "
                    f"{token!r} — H-06 violation per "
                    f"specs/shamir-recovery.md line 29",
                    user_message=(
                        "Backup checklist cannot be saved — a card slot "
                        "carries the 'Envoy' label or a real name. The "
                        "checklist must use only the opaque slot labels "
                        "(slot-1, slot-2, ...) the ritual prepared. Real "
                        "names go in the private envelope, never on the "
                        "checklist itself."
                    ),
                )


class TrustVaultChecklistPersister:
    """Implements the `ChecklistPersister` Protocol per `envoy/shamir/types.py`.

    Stores `DistributionChecklist.to_dict()` keyed by `ritual_id` inside
    the Trust Vault's metadata slot. Round-trips across lock/unlock
    cycles via the vault's `read_metadata` / `write_metadata` API.

    Per `rules/facade-manager-detection.md` Rule 3: constructor receives
    explicit `(trust_vault, principal_id)` dependencies. The vault MUST
    be unlocked at `persist()` time; the persister surfaces
    `ChecklistPersisterError` if the vault is sealed.

    Phase 01 single-principal limitation: `principal_id` is recorded
    alongside the checklist for forward-compat with Phase 02
    multi-principal vaults, but the current implementation does not
    namespace by principal — there is one vault per principal in
    Phase 01.
    """

    def __init__(
        self,
        trust_vault: _MinimalVault,
        principal_id: str,
    ) -> None:
        if not principal_id:
            raise ChecklistPersisterError(
                "principal_id must be a non-empty string",
                user_message=(
                    "Cannot save backup checklist — no user identity is "
                    "bound to this Envoy install yet. Complete the "
                    "Boundary Conversation first."
                ),
            )
        self._vault = trust_vault
        self._principal_id = principal_id

    async def persist(self, checklist: DistributionChecklist) -> None:
        """Persist `checklist` to the vault under `ritual_id`.

        Read-modify-write cycle:
        1. `vault.read_metadata()` — current dict, or `{}` if unset.
        2. Append `checklist.to_dict()` under
           `metadata["shamir_distribution_checklists"][ritual_id]`.
        3. `vault.write_metadata(updated)` — atomic-write per the vault's
           own atomic-write contract.

        Raises:
            ChecklistPersisterError: vault is sealed, or the underlying
                write failed (wraps `VaultLockedError` /
                `AutoLockIdleTimeoutError` / `OSError`).
            EnvoyLabelOnCardError: H-06 violation — checklist contains
                a non-opaque slot label.
        """
        _validate_checklist_slot_labels(checklist)

        if not self._vault.is_unlocked:
            raise ChecklistPersisterError(
                "Trust Vault is sealed — cannot persist DistributionChecklist",
                user_message=(
                    "We couldn't save the backup checklist because your "
                    "Trust Vault is locked. Re-unlock the vault and try "
                    "again."
                ),
            )

        try:
            existing = await self._vault.read_metadata()
            checklists_slot = dict(existing.get(_METADATA_KEY_CHECKLISTS, {}))
            checklists_slot[checklist.ritual_id] = checklist.to_dict()

            updated = dict(existing)
            updated[_METADATA_KEY_CHECKLISTS] = checklists_slot

            await self._vault.write_metadata(updated)
        except (VaultLockedError, AutoLockIdleTimeoutError) as exc:
            raise ChecklistPersisterError(
                f"vault became locked mid-persist: {exc!r}",
                user_message=(
                    "We couldn't save the backup checklist because your "
                    "Trust Vault locked while we were writing. Re-unlock "
                    "the vault and re-run the backup ritual."
                ),
            ) from exc
        except OSError as exc:
            raise ChecklistPersisterError(
                f"vault write failed: {exc!r}",
                user_message=(
                    "We couldn't save the backup checklist due to a disk "
                    "error. Check that the Envoy data directory has free "
                    "space and is writable, then re-run the backup ritual."
                ),
            ) from exc

        logger.info(
            "shamir.checklist.persisted",
            extra={
                "ritual_id": checklist.ritual_id,
                "total_shards": checklist.total_shards,
                "threshold": checklist.threshold,
            },
        )

    async def read_all(self) -> dict[str, DistributionChecklist]:
        """Return every persisted checklist keyed by `ritual_id`.

        Used by Phase 02 boundary-conversation (post-recovery audit) and
        by Tier 1 round-trip tests asserting persistence across
        lock/unlock cycles. Phase 01 surface is read-only — there is no
        delete API yet (rotation lands in T-02-35-rotate, not this shard).

        Raises:
            ChecklistPersisterError: vault is sealed.
        """
        if not self._vault.is_unlocked:
            raise ChecklistPersisterError(
                "Trust Vault is sealed — cannot read DistributionChecklists",
                user_message=(
                    "We couldn't load the backup checklists because your "
                    "Trust Vault is locked. Re-unlock the vault and try "
                    "again."
                ),
            )

        metadata = await self._vault.read_metadata()
        raw_slot = metadata.get(_METADATA_KEY_CHECKLISTS, {})
        if not isinstance(raw_slot, dict):
            return {}
        out: dict[str, DistributionChecklist] = {}
        for ritual_id, payload in raw_slot.items():
            if not isinstance(payload, dict):
                continue
            try:
                out[str(ritual_id)] = DistributionChecklist.from_dict(payload)
            except (KeyError, ValueError) as exc:
                # A corrupted entry should NOT prevent loading the rest;
                # surface at WARN with a hashed ritual_id (per
                # `rules/observability.md` Rule 8) so operators can
                # investigate without log-leaking the raw id.
                import hashlib

                rid_hash = hashlib.sha256(str(ritual_id).encode("utf-8")).hexdigest()[:8]
                logger.warning(
                    "shamir.checklist.load_skipped",
                    extra={"ritual_hash": rid_hash, "error": repr(exc)},
                )
        return out


__all__ = [
    "TrustVaultChecklistPersister",
]
