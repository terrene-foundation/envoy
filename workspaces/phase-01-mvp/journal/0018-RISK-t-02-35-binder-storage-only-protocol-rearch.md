---
type: RISK
date: 2026-05-07
created_at: 2026-05-10T00:00:00Z
author: agent
session_id: phase-01-wave-2-implement
session_turn: 3
project: phase-01-mvp
topic: T-02-35 CommitmentBinder Protocol re-architected to storage-only (L-2 carry-forward from T-02-34)
phase: implement
tags:
  [
    shamir,
    commitment-binder,
    trust-boundary,
    protocol-rearch,
    security-review,
    l-2-carry-forward,
    wave-2,
  ]
---

# RISK: CommitmentBinder Protocol re-architected to STORAGE-ONLY in T-02-35 (commit `6ec5fde5`)

T-02-34 (commit `573757e`, PR #13) shipped `ShamirRitualCoordinator` with a `CommitmentBinder` Protocol that **computed** commitments inside the binder:

```python
# T-02-34 Protocol shape (the shape that shipped)
class CommitmentBinder(Protocol):
    async def bind_to_genesis(
        self, principal_id: PrincipalId, shards: Sequence[Shard]
    ) -> list[str]: ...   # returns commitments computed by the binder
```

Security review on PR #13 (carry-forward L-2) flagged this as a **trust-boundary violation**. The binder is collaborator-supplied (T-02-37 wires `TrustStoreAdapter`); a malicious binder implementation could substitute commitments for a different secret without coordinator detection. The coordinator's Shamir share generation uses entropy `r₁`; a hostile binder receives the shards, computes commitments over a DIFFERENT secret with entropy `r₂`, and returns the substituted commitments. At recovery time, the substituted commitments validate (because the malicious binder generated a self-consistent set), and the secret reconstructed is `r₂`-derived, NOT `r₁`-derived. The user thinks they recovered Trust State A; the attacker has handed them Trust State B.

## Re-architecture: storage-only Protocol

T-02-35 (commit `6ec5fde5`) closes the boundary by stripping the binder's authority to compute commitments:

```python
# T-02-35 Protocol shape (storage-only)
class CommitmentBinder(Protocol):
    async def bind_to_genesis(
        self, principal_id: PrincipalId, commitments: Sequence[str]
    ) -> None: ...   # binder receives pre-computed commitments; CANNOT forge
```

The coordinator now computes commitments LOCALLY via `compute_commitment(shard) -> str` (`envoy/shamir/commitments.py`, `f"sha256:{hexdigest}"` over `serialize_shard(shard)` per `specs/shamir-recovery.md` § Shard public commitments). The pre-computed list is passed to the binder for STORAGE only; the binder signature does not return commitments.

**At recovery time** (T-02-36), the coordinator recomputes commitments over the reconstructed shards via the same `compute_commitment`. Any mismatch against the bound commitments fails recovery. The binder cannot forge a commitment that survives the coordinator's local recomputation — the commitment derivation lives entirely within the coordinator's trust boundary.

## Why the original T-02-34 shape passed initial review

The T-02-34 implementation passed gate review (analyst + security-reviewer + reviewer all signed off on PR #13) because the threat model at the time scoped the binder as "trusted because Trust Store IS the binder." This is true for the production wiring (T-02-37 makes `TrustStoreAdapter` the binder), but Protocols are public surface — any third-party binder implementation receiving the original `Sequence[Shard]` argument has **read access to every share's plaintext**, in addition to commitment-derivation authority. Both halves of the boundary violation needed to close.

The **L-2 carry-forward** is the flag that surfaced it: gate-review on PR #13 noted the concern as out-of-scope-for-T-02-34 but explicitly carried the finding to T-02-35 prerequisites (commit `fa1ec7b1` recorded the carry in the wave-2 todo). T-02-35 had to close it before the renderer + persister + commitment computer could ship coherently.

## Vault metadata slot (additive scope)

T-02-35 also added a **vault metadata slot** API (`read_metadata` / `write_metadata` on `TrustVault`) — a JSON envelope inside the existing payload, discriminator key `_etmd_v1` (deliberately avoids "envoy" substring per spec § H-06 hardening, so the unlocked plaintext carries zero product-identity leakage). The persister `TrustVaultChecklistPersister` stores `DistributionChecklist.to_dict()` keyed by `ritual_id` under `metadata["shamir_distribution_checklists"]`. Backwards-compatible: legacy opaque-bytes payloads return `{}` from `read_metadata`.

This is the LAST H-06 gate — every `slot_label` is structurally validated before bytes reach disk (see entry 0019 for the three-layer Unicode-confusable defense applied at the persister).

## Tests added

Test count: 383 → 427 (+44 across 5 files):

- `tests/tier1/test_shamir_commitments.py` (9 tests) — round-trip per `rules/orphan-detection.md` Rule 2a (Crypto-Pair Round-Trip).
- `tests/tier1/test_shamir_paper_renderer.py` (19 tests) — H-06 enforcement, plain-language output, dataclass invariants.
- `tests/tier1/test_shamir_distribution_checklist_persister.py` (9 tests) — vault round-trip across lock/unlock, H-06 byte-level invariant (zero "Envoy" / "envoy" in persisted bytes).
- `tests/tier1/test_trust_vault_lifecycle.py` (+7 tests) — vault metadata slot read_metadata / write_metadata round-trip.
- `tests/tier1/test_shamir_ritual_coordinator_orchestration.py` — 38 existing cases updated for new binder Protocol shape (storage-only); +1 test asserts coordinator passes pre-computed commitments to binder.

`inspect.signature` sweep (7th in streak per journal/0012): clean.

## Risk that surfaces this entry

The latent risk this RISK entry pins: **collaborator Protocols that grant computational authority on a security primitive are a forge-vector**. The reviewable fix is structural — strip the authority by passing pre-computed values. Any future Protocol added to the Shamir / Trust boundary MUST distinguish between:

- **Coordinator-derived value** (computed locally; passed as data) — safe to give to a collaborator.
- **Coordinator-needed value** (computed by collaborator; returned to coordinator) — UNSAFE for security-relevant primitives.

The L-2 finding is the template: every PR that adds a new Protocol method on the Shamir / Trust boundary should pass an audit asking "could a malicious implementation substitute the return value for an attacker-controlled equivalent?" If yes, the Protocol needs to be re-shaped to take the value as input, not return it.

## For Discussion

1. The original T-02-34 Protocol shape passed THREE independent gate-reviewer agents (analyst, security-reviewer, reviewer) before shipping to PR #13. The L-2 finding surfaced only on a SECOND security pass. Should `commands/redteam` Round 1 explicitly include a "Protocol method authority audit" — for every Protocol method on a security boundary, walk the threat model with the binder being adversarial? (Counterfactual: had T-02-34 included this audit, the re-arch would have happened in PR #13 and T-02-35 would not have inherited the L-2 carry-forward.)

2. The vault metadata slot uses discriminator key `_etmd_v1` deliberately avoiding the "envoy" substring (so unlocked plaintext carries zero product-identity leakage per H-06). This is good defensive practice, but it creates a maintenance burden: every future schema migration on the metadata slot must preserve the property. Should `rules/trust-plane-security.md` add a MUST rule "discriminator keys in encrypted-payload contexts MUST NOT contain product-identifier substrings", with a grep-able audit, so the property cannot silently drift in a future migration?

3. The storage-only re-arch closes the **commitment forgery** vector but does NOT close a related vector: a malicious binder receiving the pre-computed commitments could **drop** the persistence (return success without storing), making recovery fail. The current Protocol returns `None` on success and raises on failure; a binder that lies about success would be detected only at recovery time when no commitments are found. Should the Protocol be augmented with an idempotent confirmation hook (`confirm_bind(principal_id) -> Sequence[str]` returning the stored commitments) that the coordinator calls post-bind to verify the bind landed? Or is recovery-time detection sufficient because the coordinator-side commitment list is the source of truth and a missing-on-disk binding fails closed?
