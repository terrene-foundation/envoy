"""envoy.trust dataclass types.

Lightweight envoy-side types that wrap `kailash.trust.chain.GenesisRecord`,
`DelegationRecord`, and `TrustLineageChain` with envoy-namespaced aliases —
keeping the envoy import surface stable across kailash-py versions.

Per shard 5 § 4 step 1 + `rules/tenant-isolation.md` Rule 2: every type that
touches per-principal state carries `principal_id` (no defaults).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# `PrincipalId` is the canonical envoy alias for kailash-py's "agent_id" (which
# kailash-py uses generically). The envoy spec uses "principal_id" everywhere
# for `rules/tenant-isolation.md` consistency. We expose both names so callers
# from either spec read cleanly.
PrincipalId = str


@dataclass(frozen=True, slots=True)
class GenesisSeed:
    """Inputs to `TrustStoreAdapter.seed_genesis()`.

    Per `specs/trust-vault.md` § Genesis ritual. The capabilities list seeds
    the principal's initial authority surface; subsequent delegations
    (`TrustStoreAdapter.record_delegation()`) fan out from this Genesis.
    """

    principal_id: PrincipalId
    authority_id: str
    capabilities: tuple[str, ...]
    constraints: tuple[str, ...] = ()
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Output of `TrustStoreAdapter.seed_genesis()`.

    Mirrors a stripped-down view of `kailash.trust.chain.TrustLineageChain` —
    enough for downstream primitives (Boundary Conversation, Grant Moment,
    Daily Digest) to reference the Genesis without importing the full chain
    type.
    """

    principal_id: PrincipalId
    chain_hash: str  # hex sha256
    genesis_signature_algorithm: str  # e.g. "ed25519+sha256"
    capabilities_seeded: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DelegationRequest:
    """Inputs to `TrustStoreAdapter.record_delegation()`.

    Per shard 5 § 4 step 2 (R2-M-04 carry-forward): delegations route through
    `kailash.trust.TrustOperations.delegate(...)` 10-step verification (cycle-
    free, depth ≤ 16). The record produced has its `algorithm_identifier`
    routed through `_with_algorithm_id()` (T-01-15 R2-H-01 LOAD-BEARING) so the
    spec-mandated 3-key wire form lands on disk.
    """

    delegator_id: PrincipalId
    delegatee_id: PrincipalId
    task_id: str
    capabilities: tuple[str, ...]
    additional_constraints: tuple[str, ...] = ()
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VisibleSecret:
    """The user's visible secret (icon + color + phrase).

    Set at Boundary Conversation state S7 per
    `specs/boundary-conversation.md` § Questions (lines 17–27) and
    `01-analysis/08-boundary-conversation-implementation.md` § 5.2 (S7 →
    `set_visible_secret`). The visible secret is the structural
    anti-spoofing defense — it is rendered into duress modals and
    Grant-Moment surfaces so the user can confirm a prompt genuinely
    originated from Envoy (a spoofer cannot reproduce the user's chosen
    icon/color/phrase combination).

    Phase-01: persisted as plaintext-at-rest in a 0o600 sibling SQLite
    file, consistent with the chain/posture sub-stores; the T-01-13
    vault-container migration moves all sub-stores into the AES-256-GCM
    TrustVault uniformly (NOT the Connection Vault — Connection Vault
    holds API credentials per shard 8 § 3.3).
    """

    icon: str
    color: str
    phrase: str


@dataclass(frozen=True, slots=True)
class BoundaryConversationStateRow:
    """A persisted Boundary Conversation per-state row for `envoy init --resume`.

    Per `specs/boundary-conversation.md` § Persistence + resume (lines
    33–35) + `01-analysis/08-boundary-conversation-implementation.md`
    § 5.2: every answer transition persists `(ritual_id, principal_id,
    current_state, plan_dict, assembler_dict, updated_at)` to a dedicated
    table in the boundary-conversation sub-store (Phase-01: plaintext-at-rest
    in a 0o600 sibling SQLite file; the T-01-13 vault-container migration moves
    all sub-stores into the AES-256-GCM TrustVault uniformly).
    `load_boundary_conversation_state(ritual_id)`
    rehydrates this row; the runtime reconstructs the in-flight `Plan` from
    `plan_dict` and the envelope assembler from `assembler_dict`.

    `plan_dict` and `assembler_dict` are the JSON-round-trippable forms of
    `kaizen.l3.plan.types.Plan.to_dict()` and the envelope assembler's
    accumulated `EnvelopeConfigInput`, respectively.
    """

    ritual_id: str
    principal_id: PrincipalId
    current_state: str
    plan_dict: dict[str, Any]
    assembler_dict: dict[str, Any]
    updated_at: str  # ISO-8601 UTC timestamp
