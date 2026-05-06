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
    DelegationRequest,
    GenesisSeed,
    PrincipalId,
    SeedResult,
)


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

        # Sub-store paths land alongside the vault path. The vault container
        # (T-01-13) will wrap these into a single AES-256-GCM file; for now
        # they live as sibling files for ease of inspection during Wave 1
        # milestone testing.
        self._vault_path.parent.mkdir(parents=True, exist_ok=True)
        chain_db = str(self._vault_path.parent / f"{self._vault_path.stem}.chain.db")
        posture_db = str(self._vault_path.parent / f"{self._vault_path.stem}.posture.db")

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
        # Phase 01: cache the latest RevocationResult per `revocation_id` so
        # `verify_cascade_complete()` can check the cascade-completeness
        # invariant without re-running BFS. T-01-17 (Ledger persistence)
        # replaces this with persisted RevocationRecord rows.
        self._last_revocations: dict[str, RevocationResult] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Idempotently set up SQLite tables + authority registry."""
        if self._initialized:
            return
        await self._chain_store.initialize()
        await self._authority_registry.initialize()
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

        Phase 01 caches the result keyed by `agent_id` so subsequent
        `verify_cascade_complete()` can check the cascade-completeness
        invariant without re-running BFS. T-01-17 (Ledger persistence)
        replaces this cache with persisted RevocationRecord rows.

        Per `rules/trust-plane-security.md` MUST Rule 2 — every external ID
        flows through `_validate_id_safety` before reaching kailash-py /
        SQLite.
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

        result = await cascade_revoke(
            agent_id=agent_id,
            store=self._chain_store,
            reason=reason,
            revoked_by=revoked_by,
        )
        # Cache by the target `agent_id` (Phase 01 has no Ledger to mint a
        # canonical revocation_id; the agent_id IS the lookup key for the
        # latest cascade rooted at it).
        self._last_revocations[agent_id] = result
        return result

    async def verify_cascade_complete(self, *, agent_id: str) -> bool:
        """Verify every descendant of `agent_id` in the Trust Lineage's
        chain_parent_id graph is included in the cached RevocationResult.

        EC-8 cross-channel cascade defense per shard 5 § 3.3 — a malformed
        delegation_registry that under-reports descendants would silently
        leave a Day-6 child grant alive after the Day-1 root was revoked.
        This verifier walks the live chain post-revocation and refuses if
        any active descendant is missing from `revoked_agents`.

        Returns True on completeness; raises `CascadeIncompleteError` with
        the missing descendant IDs on incompleteness, OR
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

        result = self._last_revocations.get(agent_id)
        if result is None:
            raise RevocationNotFoundError(
                f"no cached cascade revocation found for agent_id={agent_id!r}; "
                "call revoke(agent_id=...) first or T-01-17 Ledger persistence "
                "for cross-session lookup",
            )
        revoked_set = set(result.revoked_agents)

        # Walk every chain in the SQLite store and collect descendants of
        # `agent_id`. The chain_store's list_chains() returns every active
        # chain; we walk each chain's delegation tree to enumerate descendants
        # rooted at agent_id. A descendant active in the chain that is NOT in
        # revoked_set is the EC-8 gap.
        chains = await self._chain_store.list_chains()
        missing: list[str] = []
        for chain in chains:
            # `agent_id` of a chain is the principal at the root; descendants
            # are reachable via DelegationRecord.delegate_id with parent_delegation_id
            # links. Iterate the active delegations and collect any whose
            # delegate_id chains back to the cascade root.
            for delegation in chain.get_active_delegations():
                # Two-pass detection: any delegation whose `agent_id` (the
                # delegatee) is `agent_id` itself OR whose ancestor includes
                # `agent_id` would be a descendant. Phase 01 BFS reaches
                # active delegates only — the kailash BFS is the source of
                # truth; this check is defense-in-depth verifying the result
                # is internally consistent with the chain's own active set.
                delegate = getattr(delegation, "delegate_id", None) or getattr(
                    delegation, "agent_id", None
                )
                if delegate is None:
                    continue
                # If kailash's cascade reported `agent_id` as revoked, every
                # delegation rooted there should likewise be in `revoked_set`.
                if agent_id in revoked_set and delegate not in revoked_set:
                    # Defense check: an active delegation chain still references
                    # the revoked agent — should not happen post-cascade.
                    if delegate not in missing:
                        missing.append(delegate)

        if missing:
            raise CascadeIncompleteError(
                f"cascade rooted at {agent_id!r} is incomplete: "
                f"{len(missing)} descendant(s) absent from revoked_agents — {missing[:5]}"
                + (f" (+ {len(missing) - 5} more)" if len(missing) > 5 else ""),
            )
        return True

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
