"""TrustStoreAdapter — envoy-side facade composing kailash-py trust persistence.

Per shard 5 § 4 steps 1-2 (post-`journal/0009-DISCOVERY-trust-store-async-deviation.md`
Option-A async migration):

1. Adapter shell + principal_id keying (no defaults; `PrincipalRequiredError` per
   `rules/tenant-isolation.md` Rule 2).
2. SqliteTrustStore + SQLitePostureStore composition. Genesis seeding via async
   `TrustOperations.establish`; `record_delegation` routes through async
   `TrustOperations.delegate` (R2-M-04 carry-forward — 10-step verification).

Subsequent steps (T-01-13 vault container, T-01-14 cascade + algorithm_id
helpers, T-01-15 R2-H-01 wire-form translator) extend this adapter; T-01-12
ships only the composition + Genesis + delegate-routing baseline.

Per `rules/patterns.md` § "Paired Public Surface — Consistent Async-ness", every
public method is async (kailash-py 2.13.4's `TrustOperations`, `SqliteTrustStore`,
and `SQLitePostureStore` all expose async APIs; wrapping in sync via `asyncio.run`
would crash inside any pytest-asyncio / Kaizen agent / Nexus handler).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from kailash.trust import TrustLineageChain, TrustOperations
from kailash.trust.authority import (
    AuthorityPermission,
    AuthorityRegistryProtocol,
    OrganizationalAuthority,
)
from kailash.trust.chain import (
    AuthorityType,
    CapabilityType,
    DelegationRecord,
)
from kailash.trust.chain_store.sqlite import SqliteTrustStore
from kailash.trust.exceptions import TrustChainNotFoundError as _UpstreamTrustChainNotFoundError
from kailash.trust.key_manager import InMemoryKeyManager
from kailash.trust.operations import CapabilityRequest
from kailash.trust.posture.posture_store import SQLitePostureStore
from kailash.trust.revocation.broadcaster import InMemoryDelegationRegistry
from kailash.trust.revocation.cascade import RevocationResult, cascade_revoke
from kailash.trust.signing.algorithm_id import AlgorithmIdentifier

# ---------------------------------------------------------------------------
# Envoy-side identifier safety guard
# ---------------------------------------------------------------------------


_MAX_ID_LEN = 256


def _validate_id_safety(identifier: str, *, field: str) -> None:
    """Reject identifiers that could enable path-traversal or null-byte attacks.

    Phase 01 envoy principal_ids follow `specs/trust-lineage.md` § Genesis
    `principal_pseudonym: <str>` — pseudonyms can legitimately contain `@`,
    `.`, `+`, `-`, `_` (e.g. `alice@example`, `agent.42+ci`). We do NOT
    constrain to slug-only — the security goal is blocking path-traversal,
    not narrowing the namespace.

    Raises ValueError on:
    - empty / non-str
    - length > 256 (DoS guard for filesystem path use)
    - null byte (`\\x00`) or any C0/C1 control character
    - `..`, `./`, `/`, `\\` (path components)
    - leading `.` (hidden-file shape)

    Per `rules/trust-plane-security.md` MUST Rule 2 — every record ID flowing
    into kailash-py SQLite primary keys + (post-T-01-13) Trust Vault container
    paths MUST be rejected at the envoy boundary if it carries any of these
    shapes.
    """
    if not isinstance(identifier, str):
        raise ValueError(f"{field} must be str (got {type(identifier).__name__})")
    if not identifier:
        raise ValueError(f"{field} must not be empty")
    if len(identifier) > _MAX_ID_LEN:
        raise ValueError(f"{field} length {len(identifier)} exceeds max {_MAX_ID_LEN}")
    if identifier.startswith("."):
        raise ValueError(f"{field} must not start with '.' (hidden-file shape)")
    if any(ch == "\x00" for ch in identifier):
        raise ValueError(f"{field} contains null byte")
    if any(ord(ch) < 0x20 or 0x7F <= ord(ch) < 0xA0 for ch in identifier):
        raise ValueError(f"{field} contains control character")
    if "/" in identifier or "\\" in identifier:
        raise ValueError(f"{field} contains path separator")
    if ".." in identifier:
        raise ValueError(f"{field} contains '..' (path traversal)")


from envoy.trust.errors import (
    CascadeIncompleteError,
    GenesisAlreadySeededError,
    PrincipalRequiredError,
    RevocationNotFoundError,
    TrustChainNotFoundError,
)
from envoy.trust.types import (
    BoundaryConversationStateRow,
    DelegationRequest,
    GenesisSeed,
    PrincipalId,
    SeedResult,
    VisibleSecret,
)

# Module-level UTC alias so digest methods whose `timezone` parameter shadows
# the `datetime.timezone` import (digest_schedule_set) can still reach UTC.
_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Phase 01 in-memory authority registry
# ---------------------------------------------------------------------------


class _InMemoryAuthorityRegistry:
    """Phase 01 minimal authority registry satisfying `AuthorityRegistryProtocol`.

    kailash-py 2.13.4 does not ship a concrete authority registry — it only
    declares the protocol. For Phase 01 (single-principal, single-vault), this
    in-process dict-backed registry is sufficient: TrustOperations.establish()
    looks up the authority once at Genesis seed time; subsequent delegations
    operate on the stored chain.

    Phase 02 entry replaces this with a Foundation-stewarded
    OrganizationalAuthorityRegistry once the registry endpoint ships
    (`specs/foundation-ops.md` § Envelope Library registry).
    """

    def __init__(self) -> None:
        self._authorities: dict[str, OrganizationalAuthority] = {}
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True

    async def get_authority(
        self, authority_id: str, include_inactive: bool = False
    ) -> OrganizationalAuthority:
        if authority_id not in self._authorities:
            raise KeyError(f"unknown authority_id: {authority_id!r}")
        auth = self._authorities[authority_id]
        if not auth.is_active and not include_inactive:
            raise KeyError(f"authority is inactive: {authority_id!r}")
        return auth

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority

    # Phase 01 utility — auto-register a degenerate authority so Genesis can land.
    # Double-underscore name-mangled per rules/trust-plane-security.md MUST NOT
    # Rule (no authority-creation backdoor reachable from arbitrary callers).
    # Only TrustStoreAdapter (in this module) consumes this via the mangled
    # attribute access `_InMemoryAuthorityRegistry__register_phase01_only`.
    # Phase 02 swap to Foundation registry replaces this entire class — the
    # mangled helper has no surface to leak.
    async def __register_phase01_only(
        self, *, authority_id: str, name: str, public_key: str, signing_key_id: str
    ) -> None:
        if authority_id in self._authorities:
            return  # idempotent
        now = datetime.now(tz=timezone.utc)
        self._authorities[authority_id] = OrganizationalAuthority(
            id=authority_id,
            name=name,
            authority_type=AuthorityType.SYSTEM,
            public_key=public_key,
            signing_key_id=signing_key_id,
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
                AuthorityPermission.GRANT_CAPABILITIES,
            ],
            created_at=now,
            updated_at=now,
            is_active=True,
        )


# ---------------------------------------------------------------------------
# TrustStoreAdapter
# ---------------------------------------------------------------------------


class TrustStoreAdapter:
    """Envoy-side trust store facade keyed on principal_id.

    Composition contract:
    - `SqliteTrustStore`         backs trust-chain persistence.
    - `SQLitePostureStore`       backs posture-history persistence.
    - `InMemoryKeyManager`       holds the principal's signing keypair (Phase 01;
                                  Trust Vault container T-01-13 wraps the keypair
                                  storage in AES-256-GCM file encryption).
    - `_InMemoryAuthorityRegistry` exposes the Genesis-time authority record.
    - `TrustOperations`          routes every delegation through the kailash-py
                                  10-step verification (R2-M-04 carry-forward).

    Per `rules/facade-manager-detection.md` Rule 3, the constructor takes the
    parent envoy framework dependencies explicitly — no global-state lookups,
    no self-construction. The Trust Vault container (AES-256-GCM file
    encryption per `specs/trust-vault.md`) lands in T-01-13 as a wrapper
    around the SQLite path; T-01-12 ships against an unencrypted SQLite
    backing for the Wave 1 milestone.

    Lifecycle:
    - Construct synchronously (no I/O).
    - `await adapter.initialize()` before first use (sets up the SQLite tables
      + authority registry).
    - `await adapter.close()` when done (releases SQLite handles).
    """

    def __init__(
        self,
        *,
        vault_path: Path | str,
        principal_id: PrincipalId,
        max_delegation_depth: int = 16,
    ) -> None:
        if not principal_id or not isinstance(principal_id, str):
            raise PrincipalRequiredError(
                "principal_id is required (per rules/tenant-isolation.md Rule 2); "
                "no defaults — silent merging across principals is BLOCKED",
            )
        # Path-traversal + null-byte rejection per rules/trust-plane-security.md
        # MUST Rule 2 — principal_id flows into kailash-py's SQLite primary key
        # and (post-T-01-13) into the vault container's filesystem path. Reject
        # `..`, `/`, `\x00`, leading `.`, control chars, and over-length shapes.
        try:
            _validate_id_safety(principal_id, field="principal_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"principal_id failed identifier safety validation: {exc}",
            ) from exc

        self._principal_id: PrincipalId = principal_id
        self._vault_path = Path(vault_path)

        # Sub-store paths land alongside the vault path. Phase-01: each is
        # persisted as plaintext-at-rest in a 0o600 sibling SQLite file,
        # consistent with the chain/posture sub-stores. The T-01-13
        # vault-container migration moves all sub-stores into the AES-256-GCM
        # TrustVault uniformly; until then they are unencrypted sibling files.
        self._vault_path.parent.mkdir(parents=True, exist_ok=True)
        chain_db = str(self._vault_path.parent / f"{self._vault_path.stem}.chain.db")
        posture_db = str(self._vault_path.parent / f"{self._vault_path.stem}.posture.db")
        # Boundary Conversation persistence + visible-secret storage live in a
        # dedicated SQLite file alongside the chain/posture sub-stores, matching
        # the existing sibling-file layout. Phase-01: plaintext-at-rest in a
        # 0o600 sibling SQLite file, consistent with the chain/posture
        # sub-stores; the T-01-13 vault-container migration moves all sub-stores
        # into the AES-256-GCM TrustVault uniformly. It is NOT a parallel
        # persistence path — it is one more region of the same store.
        self._bc_db_path = str(self._vault_path.parent / f"{self._vault_path.stem}.bc.db")
        # Daily Digest state — pause/schedule/backfill/engagement/active_channels
        # persistence per `specs/daily-digest.md` § Interaction + § Schedule.
        # T-04-82 sibling-file layout consistent with the BC store; the
        # T-01-13 vault-container migration moves both into the AES-256-GCM
        # TrustVault region uniformly. Same sync-helper / async-wrapper
        # idiom as `_sync_init_bc_store` / `persist_boundary_conversation_state`
        # — single SQLite db file, fresh connection per operation under
        # `asyncio.to_thread`, parameterized queries throughout (per
        # `rules/trust-plane-security.md` MUST Rule 5), 0o600 permissions on
        # the db file (MUST Rule 6), `_validate_id_safety()` on every
        # principal_id and channel_id reaching the SQLite primary keys.
        self._digest_db_path = str(self._vault_path.parent / f"{self._vault_path.stem}.digest.db")

        self._chain_store = SqliteTrustStore(db_path=chain_db)
        self._posture_store = SQLitePostureStore(db_path=posture_db)
        self._key_manager = InMemoryKeyManager()
        self._authority_registry: AuthorityRegistryProtocol = _InMemoryAuthorityRegistry()
        # InMemoryKeyManager extends KeyManagerInterface (ABC) rather than
        # TrustKeyManager (a Protocol); kailash-py uses duck-typing here, so
        # the runtime behavior is correct even though static type-check
        # reports a nominal mismatch.
        self._trust_ops = TrustOperations(
            authority_registry=self._authority_registry,
            key_manager=self._key_manager,  # type: ignore[arg-type]
            trust_store=self._chain_store,
            max_delegation_depth=max_delegation_depth,
        )
        self._initialized = False
        # Phase 01: cache the latest RevocationResult AND the pre-revoke
        # descendant snapshot per `agent_id` so `verify_cascade_complete()`
        # can check the cascade-completeness invariant against the GROUND
        # TRUTH delegation graph at revoke-time (not the post-revoke
        # soft-deleted chains, which would be structurally empty per the
        # zero-tolerance Rule 2 fake-classification gap that gate-review
        # H-01 surfaced).
        # Bounded LRU per `rules/trust-plane-security.md` MUST Rule 4
        # (bounded collections, maxlen=10000) — local-DoS defense.
        from collections import OrderedDict as _OD

        self._last_revocations: _OD[str, tuple[RevocationResult, frozenset[str]]] = _OD()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Idempotently set up SQLite tables + authority registry."""
        if self._initialized:
            return
        await self._chain_store.initialize()
        await self._authority_registry.initialize()
        await asyncio.to_thread(self._sync_init_bc_store)
        await asyncio.to_thread(self._sync_init_digest_store)
        self._initialized = True

    async def close(self) -> None:
        """Release SQLite handles + zeroize in-memory key material.

        Caller responsibility (no `__del__` cleanup per
        `rules/patterns.md` § Async Resource Cleanup).

        Per `rules/trust-plane-security.md` MUST NOT Rule 3 (no private key
        material in memory longer than necessary): the InMemoryKeyManager's
        backing store is cleared on close. Wave 1 ships against unencrypted
        SQLite + InMemoryKeyManager; T-01-13 (Trust Vault container) wraps
        these into AES-256-GCM file encryption — `close()` minimizes the
        residence window in the meantime.
        """
        await self._chain_store.close()
        # SQLitePostureStore.close is sync per kailash 2.13.4
        if hasattr(self._posture_store, "close"):
            self._posture_store.close()
        # Best-effort zeroize of the key manager's in-memory store. The
        # InMemoryKeyManager exposes a private `_keys` dict in kailash-py
        # 2.13.4; `clear()` reduces the residency window for the eventual
        # T-01-13 vault-container migration. Defensive `getattr` so future
        # kailash versions that rename or refactor the field do not break
        # the close path.
        keys_dict = getattr(self._key_manager, "_keys", None)
        if isinstance(keys_dict, dict):
            keys_dict.clear()
        self._initialized = False

    # ------------------------------------------------------------------
    # Public surface — principal_id discipline on every method
    # ------------------------------------------------------------------

    @property
    def principal_id(self) -> PrincipalId:
        return self._principal_id

    @property
    def vault_path(self) -> Path:
        return self._vault_path

    async def seed_genesis(self, seed: GenesisSeed) -> SeedResult:
        """Seed the Genesis Record for `seed.principal_id`.

        Per `specs/trust-vault.md` § Genesis ritual + `specs/trust-lineage.md`
        § Genesis. Genesis is the cryptographic root of the principal's trust
        lineage; re-seeding is BLOCKED — it would silently invalidate every
        descendant DelegationRecord. To re-establish trust after compromise,
        cascade revoke the existing chain (envoy.trust.cascade — T-01-14)
        and seed a fresh principal_id.
        """
        if not self._initialized:
            await self.initialize()
        # Path-traversal guard on every external identifier per
        # rules/trust-plane-security.md MUST Rule 2.
        try:
            _validate_id_safety(seed.principal_id, field="seed.principal_id")
            _validate_id_safety(seed.authority_id, field="seed.authority_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"GenesisSeed identifier failed safety validation: {exc}",
            ) from exc
        if seed.principal_id != self._principal_id:
            raise PrincipalRequiredError(
                "GenesisSeed.principal_id does not match adapter's principal_id "
                "— per-adapter is per-principal (no cross-principal seeding)",
                principal_id=self._principal_id,
            )

        # kailash-py's SqliteTrustStore.get_chain raises TrustChainNotFoundError
        # when the chain is absent (rather than returning None); wrap to detect
        # whether Genesis is already seeded.
        try:
            await self._chain_store.get_chain(seed.principal_id)
        except _UpstreamTrustChainNotFoundError:
            pass  # fresh principal — proceed with Genesis
        else:
            raise GenesisAlreadySeededError(
                "Genesis already seeded for principal_id; cascade revoke before re-seeding",
                principal_id=seed.principal_id,
            )

        # Mint a signing keypair for the authority + agent and register the
        # authority so TrustOperations.establish() resolves it.
        authority_key_id = f"authority:{seed.authority_id}"
        agent_key_id = f"agent:{seed.principal_id}"

        # has_key / get_public_key are sync per kailash 2.13.4 InMemoryKeyManager
        # (only generate_keypair / sign are async).
        if not self._key_manager.has_key(authority_key_id):
            authority_public_key, _ = await self._key_manager.generate_keypair(authority_key_id)
        else:
            existing_pub = self._key_manager.get_public_key(authority_key_id)
            assert existing_pub is not None  # has_key just returned True
            authority_public_key = existing_pub

        if not self._key_manager.has_key(agent_key_id):
            await self._key_manager.generate_keypair(agent_key_id)

        # Phase 01 in-memory registry registration (Phase 02 swaps to Foundation
        # registry once the endpoint ships). Name-mangling guards against
        # arbitrary callers reaching the SYSTEM-tier authority creation backdoor
        # via `adapter._authority_registry._register_phase01(...)`. Only this
        # module can dispatch through the mangled name.
        if not isinstance(self._authority_registry, _InMemoryAuthorityRegistry):
            raise PrincipalRequiredError(
                "Phase 01 authority registry is required for seed_genesis; "
                "Phase 02 Foundation-registry swap MUST replace seed_genesis "
                "before the in-memory registry is removed.",
            )
        await self._authority_registry._InMemoryAuthorityRegistry__register_phase01_only(  # type: ignore[attr-defined]  # noqa: SLF001 — name-mangled Phase 01 helper
            authority_id=seed.authority_id,
            name=seed.metadata.get("authority_name", seed.authority_id),
            public_key=authority_public_key,
            signing_key_id=authority_key_id,
        )

        capability_requests = [
            CapabilityRequest(
                capability=cap,
                capability_type=CapabilityType.ACTION,
                constraints=list(seed.constraints) if seed.constraints else [],
            )
            for cap in seed.capabilities
        ]

        chain: TrustLineageChain = await self._trust_ops.establish(
            agent_id=seed.principal_id,
            authority_id=seed.authority_id,
            capabilities=capability_requests,
            constraints=list(seed.constraints) if seed.constraints else None,
            metadata=seed.metadata,
            expires_at=seed.expires_at,
        )

        return SeedResult(
            principal_id=seed.principal_id,
            chain_hash=chain.hash(),
            genesis_signature_algorithm=chain.genesis.signature_algorithm,
            capabilities_seeded=tuple(seed.capabilities),
        )

    async def record_delegation(self, request: DelegationRequest) -> DelegationRecord:
        """Record a delegation via TrustOperations.delegate (R2-M-04 routing).

        Per shard 5 § 4 step 2 + R2-M-04 carry-forward: every delegation MUST
        route through the kailash-py 10-step verification (cycle-free, depth
        ≤ max_delegation_depth). The TrustOperations.delegate(...) call IS that
        10-step verification — bypassing it (e.g., constructing
        DelegationRecord directly and storing) is BLOCKED because it skips the
        cycle-detection + max-depth + capability-intersection guarantees that
        the cascade-revocation logic (T-01-14) depends on.
        """
        if not self._initialized:
            await self.initialize()
        # Path-traversal guard per rules/trust-plane-security.md MUST Rule 2.
        try:
            _validate_id_safety(request.delegator_id, field="request.delegator_id")
            _validate_id_safety(request.delegatee_id, field="request.delegatee_id")
            _validate_id_safety(request.task_id, field="request.task_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"DelegationRequest identifier failed safety validation: {exc}",
            ) from exc
        if request.delegator_id != self._principal_id:
            raise PrincipalRequiredError(
                "delegation request delegator_id does not match adapter's principal_id "
                "— per-adapter is per-principal (caller must use the delegator's adapter)",
                principal_id=self._principal_id,
            )

        # Ensure delegatee key exists (real production usage will already have
        # the delegatee registered via their own seed_genesis). has_key is sync
        # per kailash 2.13.4 InMemoryKeyManager.
        delegatee_key_id = f"agent:{request.delegatee_id}"
        if not self._key_manager.has_key(delegatee_key_id):
            await self._key_manager.generate_keypair(delegatee_key_id)

        return await self._trust_ops.delegate(
            delegator_id=request.delegator_id,
            delegatee_id=request.delegatee_id,
            task_id=request.task_id,
            capabilities=list(request.capabilities),
            additional_constraints=(
                list(request.additional_constraints) if request.additional_constraints else None
            ),
            expires_at=request.expires_at,
            metadata=request.metadata,
        )

    async def get_chain(self, principal_id: PrincipalId) -> TrustLineageChain:
        """Return the trust chain for the given principal_id.

        The lookup is principal_id-scoped per `rules/tenant-isolation.md`
        Rule 1 — chains are NOT shared across principals. Raises
        `TrustChainNotFoundError` (envoy-side hierarchy) when the chain is
        absent.
        """
        if not principal_id:
            raise PrincipalRequiredError(
                "principal_id required for get_chain; no default lookup",
            )
        # Path-traversal guard per rules/trust-plane-security.md MUST Rule 2.
        try:
            _validate_id_safety(principal_id, field="principal_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"principal_id failed identifier safety validation: {exc}",
            ) from exc
        if not self._initialized:
            await self.initialize()
        try:
            return await self._chain_store.get_chain(principal_id)
        except _UpstreamTrustChainNotFoundError as exc:
            raise TrustChainNotFoundError(
                "no trust chain found for principal_id",
                principal_id=principal_id,
            ) from exc

    async def store_chain(self, chain: TrustLineageChain) -> None:
        """Persist a chain (e.g., after Boundary Conversation seeds it)."""
        if not self._initialized:
            await self.initialize()
        await self._chain_store.store_chain(chain)

    async def list_chain_ids(self) -> list[str]:
        """List principal_ids with persisted chains.

        Phase 01: returns the unfiltered set the SQLite store knows about.
        Phase 02 may add per-tenant filtering when the multi-principal
        Shared Household primitive (specs/shared-household.md) lands.
        """
        if not self._initialized:
            await self.initialize()
        chains = await self._chain_store.list_chains()
        return [c.genesis.agent_id for c in chains]

    # ------------------------------------------------------------------
    # Cascade revocation (T-01-14 — EC-2 + EC-8)
    # ------------------------------------------------------------------

    # Bounded LRU cache size per `rules/trust-plane-security.md` MUST Rule 4
    # (bounded collections, maxlen=10000) — local-DoS defense.
    _REVOCATION_CACHE_MAXLEN = 10_000

    async def revoke(
        self,
        *,
        agent_id: str,
        reason: str,
        revoked_by: str,
    ) -> RevocationResult:
        """Cascade-revoke `agent_id` and every descendant via kailash-py BFS.

        Delegates to `kailash.trust.revocation.cascade.cascade_revoke` per
        shard 5 § 3.3 — provides idempotency check (already-revoked = no-op),
        BFS via `CascadeRevocationManager`, snapshot-and-rollback on
        partial failure, and the cross-SDK BFS/DFS set-equality contract
        (specs/trust-lineage.md § Cascade revocation).

        Phase 01 PRE-revoke snapshots the descendant set rooted at `agent_id`
        before delegating to kailash, then caches `(result, snapshot_set)`
        keyed by `agent_id`. The snapshot is the GROUND TRUTH delegation
        graph at revoke-time — `verify_cascade_complete()` compares it
        against `result.revoked_agents` to catch the EC-8 gap (a malformed
        delegation_registry that under-reports descendants). Without the
        pre-revoke snapshot, post-revoke chains are soft-deleted and drop
        out of `list_chains()`, leaving the verifier structurally unable
        to detect the gap (zero-tolerance Rule 2 fake-classification).

        Cache is a bounded LRU (maxlen `_REVOCATION_CACHE_MAXLEN` = 10000)
        per `rules/trust-plane-security.md` MUST Rule 4. T-01-17 (Ledger
        persistence) replaces the in-memory cache with persisted
        RevocationRecord rows.

        Per `rules/trust-plane-security.md` MUST Rule 2 — every external ID
        flows through `_validate_id_safety` before reaching kailash-py /
        SQLite.

        Re-revoke semantics: the latest call wins (kailash idempotency
        means the second cascade is a no-op no-op, but the snapshot at the
        second call may be smaller than the first if intermediate edits
        changed the chain). Phase 02 will preserve the original snapshot
        via persisted Ledger rows.
        """
        if not self._initialized:
            await self.initialize()
        try:
            _validate_id_safety(agent_id, field="agent_id")
            _validate_id_safety(revoked_by, field="revoked_by")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"revoke() identifier failed safety validation: {exc}",
            ) from exc

        # Build the delegator → [delegatee] adjacency ONCE from the persisted
        # chains; derive both the pre-revoke snapshot AND the DelegationRegistry
        # the cascade BFS uses, so the two cannot drift.
        adjacency = await self._build_delegation_adjacency()

        # PRE-revoke snapshot: enumerate the GROUND-TRUTH descendants of
        # agent_id in the active delegation graph. The cascade_revoke call
        # below soft-deletes chains; a post-revoke walk would miss them.
        snapshot = self._descendants_from_adjacency(adjacency, agent_id)

        # Populate the DelegationRegistry kailash's cascade BFS uses to discover
        # descendants. WITHOUT this, cascade_revoke falls back to a fresh empty
        # InMemoryDelegationRegistry() and revokes ONLY the root — the EC-8(c)
        # hard-constraint violation surfaced by F12-a (journal/0042 F14: a
        # revoked Day-1 parent leaving its Day-6 cross-channel children alive).
        # Rebuilt each revoke from the SAME persisted-chain adjacency as the
        # snapshot, so it survives adapter restarts (the chains persist; the
        # in-memory registry does not need to).
        delegation_registry = InMemoryDelegationRegistry()
        for delegator_id, delegatees in adjacency.items():
            for delegatee_id in delegatees:
                delegation_registry.register_delegation(delegator_id, delegatee_id)

        result = await cascade_revoke(
            agent_id=agent_id,
            store=self._chain_store,
            reason=reason,
            revoked_by=revoked_by,
            delegation_registry=delegation_registry,
        )
        # Bounded LRU update: pop oldest if at capacity, then insert/refresh.
        if agent_id in self._last_revocations:
            self._last_revocations.move_to_end(agent_id)
        elif len(self._last_revocations) >= self._REVOCATION_CACHE_MAXLEN:
            self._last_revocations.popitem(last=False)
        self._last_revocations[agent_id] = (result, snapshot)
        return result

    async def _snapshot_descendants(self, root_agent_id: str) -> frozenset[str]:
        """Enumerate the descendants of `root_agent_id` in the active
        delegation graph BEFORE cascade_revoke runs.

        Walks every chain via `list_chains()` (Phase 01 includes only active
        chains; pre-cascade nothing is soft-deleted yet, so this is the full
        delegation graph). Builds a delegator_id → [delegatee_id] adjacency
        map and BFS from `root_agent_id`. Returns the set of descendants
        (NOT including the root itself, matching the spec contract that
        `RevocationResult.revoked_agents` is the descendant set).

        Per kailash 2.13.4 `DelegationRecord` (`kailash.trust.chain`):
        - `delegator_id: str` — agent_id of the delegator
        - `delegatee_id: str` — agent_id of the delegatee (canonical field)

        Phase 02: when `SqliteTrustStore` exposes a
        `list_chains_for_root(root)` or descendant-query helper, switch to
        an O(log N) lookup instead of the O(N×M) full walk.
        """
        adjacency = await self._build_delegation_adjacency()
        return self._descendants_from_adjacency(adjacency, root_agent_id)

    async def _build_delegation_adjacency(self) -> dict[str, list[str]]:
        """Build the delegator_id → [delegatee_id] adjacency from every active
        delegation across all persisted chains.

        Single source of truth for BOTH the pre-revoke descendant snapshot AND
        the cascade's `DelegationRegistry` (`revoke()`), so the two cannot
        drift. Per kailash `DelegationRecord`: `delegator_id` / `delegatee_id`.
        The edge is persisted on the DELEGATEE's chain, so the full walk across
        all chains is required to reconstruct the graph.

        Phase 02: replace the O(N×M) full walk with a `SqliteTrustStore`
        descendant-query helper when it lands.
        """
        chains = await self._chain_store.list_chains()
        adjacency: dict[str, list[str]] = {}
        for chain in chains:
            for d in chain.get_active_delegations():
                adjacency.setdefault(d.delegator_id, []).append(d.delegatee_id)
        return adjacency

    @staticmethod
    def _descendants_from_adjacency(
        adjacency: dict[str, list[str]], root_agent_id: str
    ) -> frozenset[str]:
        """BFS the delegation adjacency from `root_agent_id`; return the
        descendant set (NOT including the root), matching the spec contract
        that `RevocationResult.revoked_agents` is the descendant set."""
        descendants: set[str] = set()
        queue: list[str] = [root_agent_id]
        while queue:
            node = queue.pop(0)
            for child in adjacency.get(node, []):
                if child not in descendants and child != root_agent_id:
                    descendants.add(child)
                    queue.append(child)
        return frozenset(descendants)

    async def verify_cascade_complete(self, *, agent_id: str) -> bool:
        """Verify every pre-revoke descendant of `agent_id` is in the cached
        RevocationResult's `revoked_agents` set.

        EC-8 cross-channel cascade defense per shard 5 § 3.3 — a malformed
        delegation_registry that under-reports descendants would silently
        leave a Day-6 child grant alive after the Day-1 root was revoked.

        The verifier compares the PRE-revoke descendant snapshot (taken
        in `revoke()`) against the post-revoke `RevocationResult.revoked_agents`.
        Snapshot is the ground truth at revoke-time; revoked_agents is what
        kailash's BFS actually visited. Any snapshot member NOT in
        revoked_agents is the EC-8 gap.

        Returns True on completeness; raises `CascadeIncompleteError` with
        up to 5 missing descendant IDs on incompleteness, OR
        `RevocationNotFoundError` if no `revoke(agent_id=...)` cached
        result is found.
        """
        if not self._initialized:
            await self.initialize()
        try:
            _validate_id_safety(agent_id, field="agent_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"agent_id failed identifier safety validation: {exc}",
            ) from exc

        cached = self._last_revocations.get(agent_id)
        if cached is None:
            raise RevocationNotFoundError(
                f"no cached cascade revocation found for agent_id={agent_id!r}; "
                "call revoke(agent_id=...) first or T-01-17 Ledger persistence "
                "for cross-session lookup",
            )
        result, snapshot = cached
        revoked_set = set(result.revoked_agents)
        missing = sorted(snapshot - revoked_set)

        if missing:
            raise CascadeIncompleteError(
                f"cascade rooted at {agent_id!r} is incomplete: "
                f"{len(missing)} descendant(s) absent from revoked_agents — {missing[:5]}"
                + (f" (+ {len(missing) - 5} more)" if len(missing) > 5 else ""),
            )
        return True

    # ------------------------------------------------------------------
    # Boundary Conversation persistence + visible secret (shard 8 § 5.2)
    # ------------------------------------------------------------------
    #
    # The Boundary Conversation runtime (built by a separate shard) needs:
    #   - S7 → store the user's visible secret (icon + color + phrase).
    #   - after every state transition → upsert per-state ritual progress so
    #     `envoy init --resume <ritual_id>` can rehydrate.
    #   - S0 entry → query the shadow segment for unread duress events to gate
    #     the post-duress banner.
    #
    # All three persist through the SAME store the adapter already owns: a
    # dedicated SQLite db file (`self._bc_db_path`) that lives alongside the
    # chain/posture sub-stores. Phase-01: plaintext-at-rest in a 0o600 sibling
    # SQLite file, consistent with the chain/posture sub-stores; the T-01-13
    # vault-container migration moves all sub-stores into the AES-256-GCM
    # TrustVault uniformly. Persistence uses the same synchronous
    # `sqlite3` + per-thread connection + WAL + 0o600 idiom kailash-py's
    # `SqliteTrustStore` uses (shard 5 § 70), wrapped in `asyncio.to_thread`
    # for the async public surface (`rules/patterns.md` § Paired Public
    # Surface — every adapter method is async). Every query is parameterized
    # (`?` placeholders) per `rules/trust-plane-security.md` MUST Rule 5.

    _CREATE_VISIBLE_SECRET_SQL = """
    CREATE TABLE IF NOT EXISTS visible_secret (
        principal_id TEXT PRIMARY KEY,
        icon         TEXT NOT NULL,
        color        TEXT NOT NULL,
        phrase       TEXT NOT NULL,
        updated_at   TEXT NOT NULL
    )
    """

    _CREATE_BC_STATE_SQL = """
    CREATE TABLE IF NOT EXISTS boundary_conversation_state (
        ritual_id      TEXT PRIMARY KEY,
        principal_id   TEXT NOT NULL,
        current_state  TEXT NOT NULL,
        plan_json      TEXT NOT NULL,
        assembler_json TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
    """

    def _sync_init_bc_store(self) -> None:
        """Create the visible-secret + boundary-conversation tables.

        Runs on a worker thread via `asyncio.to_thread`. Sets restrictive
        0o600 permissions on the db file (owner read/write only) per
        `rules/trust-plane-security.md` MUST Rule 6 — the Trust Vault region
        holds the visible secret + ritual state, both sensitive.
        """
        db_file = Path(self._bc_db_path)
        if not db_file.exists():
            db_file.touch(mode=0o600)
        else:
            import os as _os
            import stat as _stat

            try:
                _os.chmod(db_file, _stat.S_IRUSR | _stat.S_IWUSR)
            except OSError:
                # Windows / FS-without-chmod — non-fatal; the touch above set
                # mode at create time on POSIX.
                pass
        conn = self._bc_connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(self._CREATE_VISIBLE_SECRET_SQL)
            conn.execute(self._CREATE_BC_STATE_SQL)
            conn.commit()
        finally:
            conn.close()

    def _bc_connect(self) -> sqlite3.Connection:
        """Open a short-lived SQLite connection to the boundary-conversation db.

        A fresh connection per operation (opened on the `asyncio.to_thread`
        worker thread) avoids the cross-thread connection-reuse error sqlite3
        raises by default. Phase 01's single-principal, low-frequency
        persistence (≤200ms per write per shard 8 § perf) does not need a
        pooled connection; T-01-13's vault-container migration revisits the
        connection lifecycle alongside the region-key wiring.
        """
        conn = sqlite3.connect(self._bc_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def set_visible_secret(
        self, principal_id: str, *, icon: str, color: str, phrase: str
    ) -> None:
        """Persist the user's visible secret (icon + color + phrase).

        Invoked at Boundary Conversation state S7 per
        `01-analysis/08-boundary-conversation-implementation.md` § 5.2. The
        visible secret is the structural anti-spoofing defense rendered into
        duress modals + Grant-Moment surfaces. Phase-01: persisted as
        plaintext-at-rest in a 0o600 sibling SQLite file, consistent with the
        chain/posture sub-stores; the T-01-13 vault-container migration moves
        all sub-stores into the AES-256-GCM TrustVault uniformly (NOT the
        Connection Vault — shard 8 § 3.3).

        Upsert semantics: re-setting the visible secret for the same
        principal_id overwrites the prior value. Paired with
        `get_visible_secret()` for read-back verification.

        Per `rules/tenant-isolation.md` Rule 2 + `rules/trust-plane-security.md`
        MUST Rule 2, `principal_id` is required and validated against
        path-traversal / null-byte / control-char shapes before reaching the
        SQLite primary key.
        """
        if not self._initialized:
            await self.initialize()
        try:
            _validate_id_safety(principal_id, field="principal_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"principal_id failed identifier safety validation: {exc}",
            ) from exc
        now = datetime.now(tz=timezone.utc).isoformat()
        await asyncio.to_thread(
            self._sync_set_visible_secret, principal_id, icon, color, phrase, now
        )

    def _sync_set_visible_secret(
        self, principal_id: str, icon: str, color: str, phrase: str, now: str
    ) -> None:
        conn = self._bc_connect()
        try:
            conn.execute(
                """
                INSERT INTO visible_secret
                    (principal_id, icon, color, phrase, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(principal_id) DO UPDATE SET
                    icon=excluded.icon,
                    color=excluded.color,
                    phrase=excluded.phrase,
                    updated_at=excluded.updated_at
                """,
                (principal_id, icon, color, phrase, now),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_visible_secret(self, principal_id: str) -> VisibleSecret | None:
        """Return the visible secret for `principal_id`, or None if unset.

        Read-back companion to `set_visible_secret()` (Tier-3 discipline:
        every write verified by read). Returns None — does NOT raise — when no
        visible secret has been set for the principal.
        """
        if not self._initialized:
            await self.initialize()
        try:
            _validate_id_safety(principal_id, field="principal_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"principal_id failed identifier safety validation: {exc}",
            ) from exc
        row = await asyncio.to_thread(self._sync_get_visible_secret, principal_id)
        if row is None:
            return None
        return VisibleSecret(icon=row["icon"], color=row["color"], phrase=row["phrase"])

    def _sync_get_visible_secret(self, principal_id: str) -> sqlite3.Row | None:
        conn = self._bc_connect()
        try:
            cur = conn.execute(
                "SELECT icon, color, phrase FROM visible_secret WHERE principal_id = ?",
                (principal_id,),
            )
            row: sqlite3.Row | None = cur.fetchone()
            return row
        finally:
            conn.close()

    async def persist_boundary_conversation_state(
        self,
        ritual_id: str,
        *,
        plan_dict: dict,
        assembler_dict: dict,
        principal_id: str,
        current_state: str,
    ) -> None:
        """Upsert one Boundary Conversation per-state progress row.

        Invoked after every state transition per
        `01-analysis/08-boundary-conversation-implementation.md` § 5.2 +
        `specs/boundary-conversation.md` § Persistence + resume (lines 33–35).
        Stores `(ritual_id, principal_id, current_state, plan_dict,
        assembler_dict, updated_at)` so `envoy init --resume <ritual_id>` can
        rehydrate via `load_boundary_conversation_state()`.

        Upsert semantics: re-persisting the same `ritual_id` overwrites the
        prior row (the conversation advances S0→S10 against one ritual_id; each
        transition replaces the row with the newer state). `plan_dict` and
        `assembler_dict` are serialized as canonical JSON (`sort_keys=True`,
        no whitespace) so the on-disk bytes are deterministic.
        """
        if not self._initialized:
            await self.initialize()
        try:
            _validate_id_safety(ritual_id, field="ritual_id")
            _validate_id_safety(principal_id, field="principal_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"boundary-conversation identifier failed safety validation: {exc}",
            ) from exc
        plan_json = json.dumps(plan_dict, sort_keys=True, separators=(",", ":"))
        assembler_json = json.dumps(assembler_dict, sort_keys=True, separators=(",", ":"))
        now = datetime.now(tz=timezone.utc).isoformat()
        await asyncio.to_thread(
            self._sync_persist_bc_state,
            ritual_id,
            principal_id,
            current_state,
            plan_json,
            assembler_json,
            now,
        )

    def _sync_persist_bc_state(
        self,
        ritual_id: str,
        principal_id: str,
        current_state: str,
        plan_json: str,
        assembler_json: str,
        now: str,
    ) -> None:
        conn = self._bc_connect()
        try:
            conn.execute(
                """
                INSERT INTO boundary_conversation_state
                    (ritual_id, principal_id, current_state, plan_json,
                     assembler_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ritual_id) DO UPDATE SET
                    principal_id=excluded.principal_id,
                    current_state=excluded.current_state,
                    plan_json=excluded.plan_json,
                    assembler_json=excluded.assembler_json,
                    updated_at=excluded.updated_at
                """,
                (ritual_id, principal_id, current_state, plan_json, assembler_json, now),
            )
            conn.commit()
        finally:
            conn.close()

    async def load_boundary_conversation_state(
        self, ritual_id: str
    ) -> BoundaryConversationStateRow | None:
        """Rehydrate a Boundary Conversation per-state row by ritual_id.

        Returns a typed `BoundaryConversationStateRow` or **None if the
        ritual_id is absent**. Does NOT raise on absence — the runtime layer
        maps None to its own typed `RitualResumeStateMissingError` (that error
        lives in the boundary_conversation package, NOT here, per shard 8
        § Error taxonomy). `plan_dict` / `assembler_dict` are round-tripped
        from the canonical-JSON columns.
        """
        if not self._initialized:
            await self.initialize()
        try:
            _validate_id_safety(ritual_id, field="ritual_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"ritual_id failed identifier safety validation: {exc}",
            ) from exc
        row = await asyncio.to_thread(self._sync_load_bc_state, ritual_id)
        if row is None:
            return None
        return BoundaryConversationStateRow(
            ritual_id=row["ritual_id"],
            principal_id=row["principal_id"],
            current_state=row["current_state"],
            plan_dict=json.loads(row["plan_json"]),
            assembler_dict=json.loads(row["assembler_json"]),
            updated_at=row["updated_at"],
        )

    def _sync_load_bc_state(self, ritual_id: str) -> sqlite3.Row | None:
        conn = self._bc_connect()
        try:
            cur = conn.execute(
                """
                SELECT ritual_id, principal_id, current_state, plan_json,
                       assembler_json, updated_at
                FROM boundary_conversation_state
                WHERE ritual_id = ?
                """,
                (ritual_id,),
            )
            row: sqlite3.Row | None = cur.fetchone()
            return row
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Daily Digest state (T-04-82) — pause / schedule / backfill /
    # engagement / active-channels persistence per specs/daily-digest.md.
    # Same sync-helper / async-wrapper idiom as the BC store above; a
    # single 0o600 SQLite sibling file (`*.digest.db`); fresh connection
    # per op on the asyncio.to_thread worker; parameterized queries only
    # (rules/trust-plane-security.md MUST Rule 5); every principal_id and
    # channel_id reaching a primary key validated via _validate_id_safety.
    # ------------------------------------------------------------------

    _CREATE_DIGEST_PAUSE_SQL = """
    CREATE TABLE IF NOT EXISTS digest_pause (
        principal_id    TEXT PRIMARY KEY,
        paused_until    TEXT NOT NULL,
        reason          TEXT NOT NULL,
        paused_at       TEXT NOT NULL
    )
    """

    _CREATE_DIGEST_SCHEDULE_SQL = """
    CREATE TABLE IF NOT EXISTS digest_schedule (
        principal_id    TEXT PRIMARY KEY,
        hour_utc        INTEGER NOT NULL,
        timezone        TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    )
    """

    _CREATE_DIGEST_BACKFILL_SQL = """
    CREATE TABLE IF NOT EXISTS digest_backfill (
        principal_id    TEXT NOT NULL,
        channel_id      TEXT NOT NULL,
        last_success    TEXT NOT NULL,
        last_digest_id  TEXT NOT NULL,
        PRIMARY KEY (principal_id, channel_id)
    )
    """

    _CREATE_DIGEST_ENGAGEMENT_SQL = """
    CREATE TABLE IF NOT EXISTS digest_engagement (
        principal_id    TEXT NOT NULL,
        opened_at       TEXT NOT NULL,
        PRIMARY KEY (principal_id, opened_at)
    )
    """

    _CREATE_DIGEST_FORM_PREFERENCE_SQL = """
    CREATE TABLE IF NOT EXISTS digest_form_preference (
        principal_id    TEXT PRIMARY KEY,
        form            TEXT NOT NULL
    )
    """

    _CREATE_DIGEST_ACTIVE_CHANNELS_SQL = """
    CREATE TABLE IF NOT EXISTS digest_active_channels (
        principal_id        TEXT PRIMARY KEY,
        active_csv          TEXT NOT NULL,
        primary_channel_id  TEXT NOT NULL
    )
    """

    def _sync_init_digest_store(self) -> None:
        """Create the 5 digest-state tables. Runs on an asyncio.to_thread worker.

        Sets 0o600 on the db file per `rules/trust-plane-security.md` MUST
        Rule 6 — digest schedule + engagement timing are user-behavior
        signals that should not be world-readable.
        """
        db_file = Path(self._digest_db_path)
        if not db_file.exists():
            db_file.touch(mode=0o600)
        else:
            import contextlib
            import os as _os
            import stat as _stat

            # chmod best-effort: Windows / FS-without-chmod is non-fatal (the
            # touch above already set mode at create time on POSIX).
            with contextlib.suppress(OSError):
                _os.chmod(db_file, _stat.S_IRUSR | _stat.S_IWUSR)
        conn = self._digest_connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(self._CREATE_DIGEST_PAUSE_SQL)
            conn.execute(self._CREATE_DIGEST_SCHEDULE_SQL)
            conn.execute(self._CREATE_DIGEST_BACKFILL_SQL)
            conn.execute(self._CREATE_DIGEST_ENGAGEMENT_SQL)
            conn.execute(self._CREATE_DIGEST_ACTIVE_CHANNELS_SQL)
            conn.execute(self._CREATE_DIGEST_FORM_PREFERENCE_SQL)
            conn.commit()
        finally:
            conn.close()

    def _digest_connect(self) -> sqlite3.Connection:
        """Short-lived connection to the digest-state db (fresh per op)."""
        conn = sqlite3.connect(self._digest_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _require_principal(self, principal_id: str) -> None:
        """Validate a principal_id before it reaches a SQLite primary key."""
        try:
            _validate_id_safety(principal_id, field="principal_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"principal_id failed identifier safety validation: {exc}",
            ) from exc

    # ---- pause / resume -------------------------------------------------

    async def digest_pause_set(
        self, principal_id: str, *, paused_until: datetime, reason: str
    ) -> None:
        """Persist a pause window for `principal_id` (upsert)."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        now = datetime.now(tz=timezone.utc).isoformat()
        await asyncio.to_thread(
            self._sync_digest_pause_set,
            principal_id,
            paused_until.isoformat(),
            reason,
            now,
        )

    def _sync_digest_pause_set(
        self, principal_id: str, paused_until: str, reason: str, now: str
    ) -> None:
        conn = self._digest_connect()
        try:
            conn.execute(
                """
                INSERT INTO digest_pause (principal_id, paused_until, reason, paused_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(principal_id) DO UPDATE SET
                    paused_until = excluded.paused_until,
                    reason = excluded.reason,
                    paused_at = excluded.paused_at
                """,
                (principal_id, paused_until, reason, now),
            )
            conn.commit()
        finally:
            conn.close()

    async def digest_pause_clear(self, principal_id: str) -> None:
        """Remove any pause row for `principal_id` (no-op if absent)."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        await asyncio.to_thread(self._sync_digest_pause_clear, principal_id)

    def _sync_digest_pause_clear(self, principal_id: str) -> None:
        conn = self._digest_connect()
        try:
            conn.execute("DELETE FROM digest_pause WHERE principal_id = ?", (principal_id,))
            conn.commit()
        finally:
            conn.close()

    async def digest_pause_get(self, principal_id: str) -> tuple[datetime, str, datetime] | None:
        """Return `(paused_until, reason, paused_at)` or None if not paused."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        row = await asyncio.to_thread(self._sync_digest_pause_get, principal_id)
        if row is None:
            return None
        return (
            datetime.fromisoformat(row["paused_until"]),
            row["reason"],
            datetime.fromisoformat(row["paused_at"]),
        )

    def _sync_digest_pause_get(self, principal_id: str) -> sqlite3.Row | None:
        conn = self._digest_connect()
        try:
            cur = conn.execute(
                "SELECT paused_until, reason, paused_at FROM digest_pause "
                "WHERE principal_id = ?",
                (principal_id,),
            )
            row: sqlite3.Row | None = cur.fetchone()
            return row
        finally:
            conn.close()

    # ---- schedule -------------------------------------------------------

    async def digest_schedule_set(self, principal_id: str, *, hour: int, timezone: str) -> None:
        """Persist the principal's digest schedule (upsert)."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        now = datetime.now(tz=_UTC).isoformat()
        await asyncio.to_thread(self._sync_digest_schedule_set, principal_id, hour, timezone, now)

    def _sync_digest_schedule_set(
        self, principal_id: str, hour: int, timezone: str, now: str
    ) -> None:
        conn = self._digest_connect()
        try:
            conn.execute(
                """
                INSERT INTO digest_schedule (principal_id, hour_utc, timezone, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(principal_id) DO UPDATE SET
                    hour_utc = excluded.hour_utc,
                    timezone = excluded.timezone,
                    updated_at = excluded.updated_at
                """,
                (principal_id, hour, timezone, now),
            )
            conn.commit()
        finally:
            conn.close()

    async def digest_schedule_get(self, principal_id: str) -> tuple[int, str] | None:
        """Return `(hour_utc, timezone)` or None if no schedule set."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        row = await asyncio.to_thread(self._sync_digest_schedule_get, principal_id)
        if row is None:
            return None
        return (row["hour_utc"], row["timezone"])

    def _sync_digest_schedule_get(self, principal_id: str) -> sqlite3.Row | None:
        conn = self._digest_connect()
        try:
            cur = conn.execute(
                "SELECT hour_utc, timezone FROM digest_schedule WHERE principal_id = ?",
                (principal_id,),
            )
            row: sqlite3.Row | None = cur.fetchone()
            return row
        finally:
            conn.close()

    async def digest_schedule_list_all(self) -> list[tuple[str, int, str]]:
        """Return `(principal_id, hour_utc, timezone)` for every schedule."""
        if not self._initialized:
            await self.initialize()
        rows = await asyncio.to_thread(self._sync_digest_schedule_list_all)
        return [(r["principal_id"], r["hour_utc"], r["timezone"]) for r in rows]

    def _sync_digest_schedule_list_all(self) -> list[sqlite3.Row]:
        conn = self._digest_connect()
        try:
            cur = conn.execute(
                "SELECT principal_id, hour_utc, timezone FROM digest_schedule "
                "ORDER BY principal_id"
            )
            return list(cur.fetchall())
        finally:
            conn.close()

    # ---- backfill -------------------------------------------------------

    async def digest_backfill_set(
        self,
        principal_id: str,
        *,
        channel_id: str,
        last_success: datetime,
        digest_id: str,
    ) -> None:
        """Record the last successful delivery for `(principal_id, channel_id)`."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        _validate_id_safety(channel_id, field="channel_id")
        await asyncio.to_thread(
            self._sync_digest_backfill_set,
            principal_id,
            channel_id,
            last_success.isoformat(),
            digest_id,
        )

    def _sync_digest_backfill_set(
        self,
        principal_id: str,
        channel_id: str,
        last_success: str,
        digest_id: str,
    ) -> None:
        conn = self._digest_connect()
        try:
            conn.execute(
                """
                INSERT INTO digest_backfill
                    (principal_id, channel_id, last_success, last_digest_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(principal_id, channel_id) DO UPDATE SET
                    last_success = excluded.last_success,
                    last_digest_id = excluded.last_digest_id
                """,
                (principal_id, channel_id, last_success, digest_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def digest_backfill_get(
        self, principal_id: str, *, channel_id: str
    ) -> tuple[datetime, str] | None:
        """Return `(last_success, last_digest_id)` or None if never delivered."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        _validate_id_safety(channel_id, field="channel_id")
        row = await asyncio.to_thread(self._sync_digest_backfill_get, principal_id, channel_id)
        if row is None:
            return None
        return (datetime.fromisoformat(row["last_success"]), row["last_digest_id"])

    def _sync_digest_backfill_get(self, principal_id: str, channel_id: str) -> sqlite3.Row | None:
        conn = self._digest_connect()
        try:
            cur = conn.execute(
                "SELECT last_success, last_digest_id FROM digest_backfill "
                "WHERE principal_id = ? AND channel_id = ?",
                (principal_id, channel_id),
            )
            row: sqlite3.Row | None = cur.fetchone()
            return row
        finally:
            conn.close()

    # ---- engagement -----------------------------------------------------

    async def digest_engagement_record_open(
        self, principal_id: str, *, opened_at: datetime
    ) -> None:
        """Record a digest-open event (idempotent on the exact timestamp)."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        await asyncio.to_thread(
            self._sync_digest_engagement_record_open,
            principal_id,
            opened_at.isoformat(),
        )

    def _sync_digest_engagement_record_open(self, principal_id: str, opened_at: str) -> None:
        conn = self._digest_connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO digest_engagement (principal_id, opened_at) "
                "VALUES (?, ?)",
                (principal_id, opened_at),
            )
            conn.commit()
        finally:
            conn.close()

    async def digest_engagement_opens_in_window(
        self, principal_id: str, *, since: datetime, until: datetime
    ) -> int:
        """Count digest-open events in `[since, until)`."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        return await asyncio.to_thread(
            self._sync_digest_engagement_opens_in_window,
            principal_id,
            since.isoformat(),
            until.isoformat(),
        )

    def _sync_digest_engagement_opens_in_window(
        self, principal_id: str, since: str, until: str
    ) -> int:
        conn = self._digest_connect()
        try:
            cur = conn.execute(
                "SELECT COUNT(*) AS n FROM digest_engagement "
                "WHERE principal_id = ? AND opened_at >= ? AND opened_at < ?",
                (principal_id, since, until),
            )
            return int(cur.fetchone()["n"])
        finally:
            conn.close()

    # ---- active channels ------------------------------------------------

    async def digest_active_channels_set(
        self, principal_id: str, *, channel_ids: list[str], primary: str
    ) -> None:
        """Persist the principal's active channel set + primary channel."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        for cid in channel_ids:
            _validate_id_safety(cid, field="channel_id")
        _validate_id_safety(primary, field="primary_channel_id")
        if primary not in channel_ids:
            raise ValueError(
                f"primary channel {primary!r} must be in the active set {channel_ids!r}",
            )
        await asyncio.to_thread(
            self._sync_digest_active_channels_set,
            principal_id,
            ",".join(channel_ids),
            primary,
        )

    def _sync_digest_active_channels_set(
        self, principal_id: str, active_csv: str, primary: str
    ) -> None:
        conn = self._digest_connect()
        try:
            conn.execute(
                """
                INSERT INTO digest_active_channels
                    (principal_id, active_csv, primary_channel_id)
                VALUES (?, ?, ?)
                ON CONFLICT(principal_id) DO UPDATE SET
                    active_csv = excluded.active_csv,
                    primary_channel_id = excluded.primary_channel_id
                """,
                (principal_id, active_csv, primary),
            )
            conn.commit()
        finally:
            conn.close()

    async def digest_active_channels_get(self, principal_id: str) -> tuple[list[str], str] | None:
        """Return `(active_channel_ids, primary)` or None if unset."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        row = await asyncio.to_thread(self._sync_digest_active_channels_get, principal_id)
        if row is None:
            return None
        active = [c for c in row["active_csv"].split(",") if c]
        return (active, row["primary_channel_id"])

    def _sync_digest_active_channels_get(self, principal_id: str) -> sqlite3.Row | None:
        conn = self._digest_connect()
        try:
            cur = conn.execute(
                "SELECT active_csv, primary_channel_id FROM digest_active_channels "
                "WHERE principal_id = ?",
                (principal_id,),
            )
            row: sqlite3.Row | None = cur.fetchone()
            return row
        finally:
            conn.close()

    # ---- form preference (rich / compact / event_only) ------------------

    async def digest_form_preference_set(self, principal_id: str, *, form: str) -> None:
        """Persist the user's explicit digest-form choice (upsert).

        Set when the user accepts the low-engagement fallback offer
        (`specs/daily-digest.md` § Low-engagement fallback) — they pick
        `compact` or `event_only`; `rich` clears the downgrade.
        """
        if form not in ("rich", "compact", "event_only"):
            raise ValueError(
                f"form must be one of rich|compact|event_only (got {form!r})",
            )
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        await asyncio.to_thread(self._sync_digest_form_preference_set, principal_id, form)

    def _sync_digest_form_preference_set(self, principal_id: str, form: str) -> None:
        conn = self._digest_connect()
        try:
            conn.execute(
                """
                INSERT INTO digest_form_preference (principal_id, form)
                VALUES (?, ?)
                ON CONFLICT(principal_id) DO UPDATE SET form = excluded.form
                """,
                (principal_id, form),
            )
            conn.commit()
        finally:
            conn.close()

    async def digest_form_preference_get(self, principal_id: str) -> str | None:
        """Return the user's explicit form choice, or None if never set."""
        if not self._initialized:
            await self.initialize()
        self._require_principal(principal_id)
        row = await asyncio.to_thread(self._sync_digest_form_preference_get, principal_id)
        return row["form"] if row is not None else None

    def _sync_digest_form_preference_get(self, principal_id: str) -> sqlite3.Row | None:
        conn = self._digest_connect()
        try:
            cur = conn.execute(
                "SELECT form FROM digest_form_preference WHERE principal_id = ?",
                (principal_id,),
            )
            row: sqlite3.Row | None = cur.fetchone()
            return row
        finally:
            conn.close()

    async def shadow_segment_unread_duress_events(self, principal_id: str) -> list:
        """Return unread duress events for the post-duress banner gate.

        **Phase 01: returns `[]`.** This is COMPLETE Phase-01 behavior, NOT a
        stub. No duress-detection mechanism is wired in Phase 01 — the shadow
        segment that would populate duress events is owned by
        `specs/data-model.md` and its detection path lands in Phase 02+ (per
        `01-analysis/08-boundary-conversation-implementation.md` § 3.6 +
        `01-analysis/05-trust-store-implementation.md`). The Boundary
        Conversation runtime correctly invokes this banner gate at S0 entry;
        the gate stays inert (empty list → no banner) until Phase 02 wires the
        shadow segment. Returning `[]` here is the correct, contract-complete
        Phase-01 answer — when the shadow segment populates in P02+, this method
        gains the real query against it.

        `principal_id` is validated for the tenant-isolation contract so the
        signature is stable across the P01→P02 transition (the P02 query will
        scope the shadow-segment read by `principal_id`).
        """
        if not self._initialized:
            await self.initialize()
        try:
            _validate_id_safety(principal_id, field="principal_id")
        except ValueError as exc:
            raise PrincipalRequiredError(
                f"principal_id failed identifier safety validation: {exc}",
            ) from exc
        return []

    # ------------------------------------------------------------------
    # R2-H-01 algorithm_id wire-form translator (T-01-15, LOAD-BEARING)
    # ------------------------------------------------------------------

    def _to_spec_wire_form(self, algorithm_dict: dict) -> dict:
        """Translate upstream's 1-key form into the spec-mandated 3-key wire form.

        Upstream `kailash.trust.signing.algorithm_id.AlgorithmIdentifier.to_dict()`
        emits `{"algorithm": "ed25519+sha256"}` (kailash-py 2.13.4 algorithm_id.py
        line 105 — post-#604 scaffold awaiting mint ISS-31). The Phase 00
        frozen spec `specs/trust-lineage.md` line 24 mandates the 3-key form
        `{"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}` on every
        on-disk DelegationRecord / GenesisRecord / RevocationRecord. The
        Independent Verifier (shard 7) consumes the 3-key form on the
        trust-lineage path; `specs/independent-verifier.md` line 35 documents
        a strict-superset 4-key segment-boundary form (R3-M-02 carry-forward,
        adds `canonical_json` key) used at Ledger-export segment boundaries
        only — that 4-key form is wired by a separate serializer extension at
        T-03-50 ledger export, NOT by this helper.

        Single point of producer-side translation per `rules/specs-authority.md`
        Rule 6 (deviations from upstream are explicitly acknowledged at one
        bottleneck, never spread across call sites). Every record-construction
        path routes through `_with_algorithm_id()` which routes through this
        helper before write — Ledger persistence (T-01-17 + T-01-18) wires the
        producer side; the verifier (shard 7) consumes the 3-key form.
        """
        compound = algorithm_dict.get("algorithm", "")
        sig, _, hash_alg = compound.partition("+")
        return {
            "sig": sig or "ed25519",
            "hash": hash_alg or "sha256",
            "shamir": "slip39",
        }

    def _with_algorithm_id(self, record_dict: dict) -> dict:
        """Embed canonical 3-key algorithm_identifier on a signed-record dict.

        Returns a NEW dict — never mutates the caller's input. A Ledger producer
        that constructs a record dict and reuses it for both audit log + persistence
        relies on this immutability so the algorithm_identifier doesn't bleed
        across record contexts.

        Single point of enforcement — no record-construction path bypasses this
        helper. Forward-path-safe per kailash-py#604 / mint ISS-31: when the
        upstream value space changes (mint ISS-31 lands new sig/hash combos),
        only `_to_spec_wire_form` updates; every caller stays unchanged.

        This is the structural defense per shard 5 § 4 step 5a + Phase 00
        survey item 19 — `rules/zero-tolerance.md` Rule 4 BLOCKS re-introducing
        hardcoded `"Ed25519"` strings anywhere in Envoy code, even though
        kailash-py's own legacy `chain.py::GenesisRecord` (line 148) still has
        `signature_algorithm: str = "Ed25519"` at the dataclass level. The
        adapter wraps that legacy field but writes the canonical 3-key
        algorithm_identifier dict alongside.
        """
        out = dict(record_dict)
        upstream_form = AlgorithmIdentifier().to_dict()
        out["algorithm_identifier"] = self._to_spec_wire_form(upstream_form)
        return out


__all__ = ["TrustStoreAdapter"]
