# 09 — Authorship Score + Posture Gate — Implementation Analysis

**Document role:** Phase 01 implementation analysis for the Authorship Score + Posture Gate primitive (shard 9 of 25 of the /analyze plan, per `01-shard-plan.md` §2). Identifies the verified `kailash-py` provider modules (post-ISS-12 closure), the Envoy-new-code surface that delivers the deterministic-replay scorer + the posture-transition enforcement gate, and the integration points to neighboring primitives. Cites Phase 00 + Phase 01 frozen artifacts; never paraphrases.

**Date:** 2026-05-03 (shard 9 of /analyze).
**Status:** DRAFT — load-bearing for shard 10 (Grant Moment posture-ratchet ceremony), shard 11 (Daily Digest posture-progress rendering), shard 16 (Channel adapters posture-aware UI), and the Phase 01 EC-2 Grant Moment cascade contract via `posture_change` Ledger entries.
**Capacity check:** 1 primitive, 2 source specs (`authorship-score.md`, `posture-ladder.md`), 3 cross-spec touch-points (`trust-lineage.md` cascade-revocation hook, `ledger.md` `posture_change` entry type, `envelope-model.md` `metadata.authorship_score` schema), ~7 invariants tracked. Within `rules/autonomous-execution.md` § Per-Session Capacity Budget.

---

## 1. Source spec citation

The Authorship Score + Posture Gate primitive is defined by two frozen Phase 00 specs, with three cross-spec touch-points. Phase 01 implementation MUST NOT re-derive these — per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, the shard's question is "given this spec is frozen, how do I wire `kailash-py` to deliver it?" not "is the spec right?". Per `rules/specs-authority.md` MUST Rule 4 + MUST Rule 7, the analysis cites by path + section.

- **Authorship Score** — `specs/authorship-score.md` § Purpose + § Score computation + § Stored counters + § Re-derivation from the Ledger + § Novelty de-duplication algorithm + § Minimum-impact check algorithm + § Cold-start + § Posture-ratchet gate + § Stored vs recomputed (M-05 fix from doc 02 R1) + § Error taxonomy. Key facts cited verbatim:
  - § Purpose: "BET-12 structural enforcement primitive. Semantic de-dup + minimum-impact + posture-ratchet gate."
  - § Score computation: "AuthorshipScore = count of envelope.\*.authored_constraints where: authored: true; novelty_check_passed: true (Jaccard < 0.85 on AST canonical form + adversarial-wording classifier < 0.8); minimum_impact_check_passed: true (dry-run corpus + user's 30-day Ledger history)".
  - § Stored counters: three signed counters in `envelope.metadata.authorship_score` schema — `authored_count` (gates posture ratchet), `imported_count` (does NOT gate), `template_provenance` (ordered list of template_id+template_hash bindings).
  - § Re-derivation from the Ledger: "rederive_authorship_counters(envelope, ledger_slice)" — pure-function recomputation from a Ledger slice over the five canonical dimensions (financial, operational, temporal, data_access, communication).
  - § Stored vs recomputed (M-05 fix): "`metadata.authorship_score.authored_count` signed at sign time. Runtime recomputes at verify. Mismatch → `AuthorshipScoreDivergenceError` audit alert."
  - § Posture-ratchet gate (Personal mode thresholds): "N=3 for DELEGATING; N=5 for AUTONOMOUS." (Enterprise: "N=5 DELEGATING; AUTONOMOUS NOT reachable on shared templates.")
- **Posture Ladder** — `specs/posture-ladder.md` § Canonical enum + § State-transition contract + § Per-tier semantics + § Algorithm + § Error taxonomy + § Cross-references. Key facts cited verbatim:
  - § Canonical enum: "PSEUDO = 0; TOOL = 1; SUPERVISED = 2; DELEGATING = 3; AUTONOMOUS = 4. Integer ordering is load-bearing — `AUTONOMOUS > DELEGATING > SUPERVISED > TOOL > PSEUDO`. `>=` comparisons appear in composition rules and posture-ratchet gates."
  - § Canonical enum / Wire format: "string name in JSON (e.g. `\"DELEGATING\"`); integer value in internal comparisons. JCS canonical form uses the string name (per specs/envelope-model.md §Canonical JSON)."
  - § State-transition contract / Ratchet-up: requires (1) Authorship Score threshold; (2) Grant Moment co-signature by user's Genesis key; (3) Envelope version bump; (4) Cooling-off window not active. PSEUDO→TOOL needs N=0; TOOL→SUPERVISED N=1; SUPERVISED→DELEGATING N=3 personal / N=5 enterprise; DELEGATING→AUTONOMOUS N=5 personal only.
  - § Algorithm `posture_change(current, target, evidence)`: target>current ratchets up under PostureAuthorshipInsufficientError / PostureGenesisGrantMissingError / PostureCoolingOffActiveError gates; target<current always permitted; target==current raises PostureNoopError. Successful transition writes a `posture_change` Ledger entry signed by Genesis key.
  - § Cross-SDK: "mirrors kailash-py `PostureStore` / `PostureEvidence` / `SQLitePostureStore` primitives (filed mint#4 + kailash-py#597 for spec parity)."
- **Trust Lineage cascade-revocation hook** — `specs/trust-lineage.md` § Algorithms — Cascade revocation. The posture gate MUST emit a cascade-revocation hook on demotion via kill-criterion or annual decay so descendant DelegationRecords issued under the higher posture are revoked. (Demotion is permitted unconditionally per `posture-ladder.md` § Ratchet-down; the cascade hook is what makes "demoted" ≠ "left dangling.")
- **Ledger `posture_change` entry type** — `specs/ledger.md` § Entry types row "`posture_change` | specs/ledger.md §Ledger entry schemas §`posture_change` + specs/posture-ladder.md §Algorithm | Genesis key". The Authorship Score's deterministic re-derivation reads the Ledger slice composed of `posture_change` + envelope-edit entries.
- **Envelope-model `metadata.authorship_score` schema** — `specs/authorship-score.md` § Stored counters references `specs/envelope-model.md` §Schema. Re-derivation operates on the envelope dataclass + Ledger slice; the envelope is the source of `authored_constraints[*].authored | novelty_check_passed | minimum_impact_check_passed` flags.

---

## 2. Verified provider citation (post-freshness-gate)

Per `03-kailash-py-mvp-readiness.md` § 5 (verification protocol) + § 3 row 6 (Authorship Score + posture gate), the Phase 00 survey baseline (`02-kailash-py-survey.md` items 5 + 6, Phase-13 type bundle) was extended by the 2026-05-03 freshness gate. Verification was executed for this shard.

### 2.1 Closed-issue reference

| Phase 00 ISS | GH#                               | Closed               | Closure shape                                                                                                                                                                           |
| ------------ | --------------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ISS-12       | terrene-foundation/kailash-py#597 | 2026-04-24T17:02:09Z | "[parity] Confirm Phase-13 posture/verification type bundle completeness" — closed by spec-confirmation (no `closedByPullRequestsReferences` entries; the canonical bundle pre-existed) |

The closure shape matters: ISS-12 is a **parity-confirmation closure**, not a "feature landed" closure. The Phase-13 5-posture bundle and the `SQLitePostureStore` concrete persistence have been in `kailash-py` since before Phase 00; the issue was filed to confirm the kailash-py side mirrors the kailash-rs Phase-13 bundle and to publish the cross-SDK type-mapping table. Per `journal/0001` "closed-status ≠ landed-feature" trap and `03-kailash-py-mvp-readiness.md` § 2.1, this shard verified the underlying code surface directly rather than treating the closure as proof-of-feature.

### 2.2 Verified module + symbol export

Confirmed by reading absolute-path source under `~/repos/loom/kailash-py/src/kailash/trust/posture/`:

- **`kailash.trust.posture.posture_store.SQLitePostureStore`** — verified at `~/repos/loom/kailash-py/src/kailash/trust/posture/posture_store.py:221`. Module-level `__all__` exports `SQLitePostureStore` + `validate_agent_id` (lines 46–49). Class surface:
  - `__init__(db_path: str)` (line 244) — validates db_path, creates parent dirs, sets 0o600 permissions on POSIX, opens per-thread connection, runs DDL + transition_type migration.
  - `get_posture(agent_id: str) -> TrustPosture` (line 301) — returns `TrustPosture.SUPERVISED` if unknown (line 323).
  - `set_posture(agent_id: str, posture: TrustPosture) -> None` (line 327) — INSERT OR REPLACE upsert.
  - `record_transition(result: TransitionResult) -> None` (line 355) — appends to `transitions` table; agent_id read from `result.metadata["agent_id"]`.
  - `get_history(agent_id: str, limit: int = 100) -> list[TransitionResult]` (line 406) — newest-first, capped at `_MAX_HISTORY_LIMIT = 10_000` (line 57).
  - `close()` (line 445), `__enter__`/`__exit__` (lines 458, 462) for context-manager use.
  - DDL (lines 122–141): `postures(agent_id TEXT PRIMARY KEY, posture TEXT, updated_at TEXT)` + `transitions(id, agent_id, from_posture, to_posture, success, timestamp, metadata, transition_type)`.
- **`kailash.trust.posture.postures.TrustPosture`** — verified at `~/repos/loom/kailash-py/src/kailash/trust/posture/postures.py:21`. Canonical 5-member set `AUTONOMOUS="autonomous" / DELEGATING="delegating" / SUPERVISED="supervised" / TOOL="tool" / PSEUDO="pseudo"` (lines 36–40). `autonomy_level` property (lines 84–94): AUTONOMOUS=5, DELEGATING=4, SUPERVISED=3, TOOL=2, PSEUDO=1. Comparison dunders `__lt__/__le__/__gt__/__ge__` defined on `autonomy_level` (lines 104+). Backward-compat aliases (lines 44–47, 56–82) accept old `DELEGATED/CONTINUOUS_INSIGHT/SHARED_PLANNING/PSEUDO_AGENT` names.
- **`kailash.trust.posture.postures.PostureEvidence`** — verified at `~/repos/loom/kailash-py/src/kailash/trust/posture/postures.py:230`. Dataclass fields: `observation_count: int`, `success_rate: float` (validated `[0.0,1.0]`, finite), `time_at_current_posture_hours: float` (non-negative, finite), `anomaly_count: int` (non-negative), `source: str`, `timestamp: datetime` (UTC default), `metadata: dict[str,Any]`. `__post_init__` (lines 254–278) enforces `math.isfinite()` on all numeric fields per `rules/security.md` § Rust-flavoured "Fail-Closed Defaults" Python equivalent.
- **`kailash.trust.posture.postures.PostureTransition`** — verified at `postures.py:129` — enum `UPGRADE / DOWNGRADE / MAINTAIN` (per the `_determine_transition_type` helper at `posture_store.py:203`); the EATP RT-06 fix preserves stored `transition_type` (line 182) so EMERGENCY_DOWNGRADE round-trips without inference.
- **`kailash.trust.posture.postures.TransitionResult`** — verified at `postures.py:196`. Carries `success / from_posture / to_posture / transition_type / reason / blocked_by / timestamp / metadata`.
- **Package-level export gap (NOT-A-BLOCKER, but flagged):** the package `__init__.py` at `~/repos/loom/kailash-py/src/kailash/trust/posture/__init__.py` exports `TrustPosture`, `PostureEvidence`, `PostureStore` (Protocol), `PostureEvaluationResult`, `TransitionResult`, etc. (lines 25–66) but does NOT re-export the concrete `SQLitePostureStore`. Envoy code MUST import the concrete class via the submodule path: `from kailash.trust.posture.posture_store import SQLitePostureStore`. This is a downstream-readability concern only; the symbol exists and is module-`__all__`-listed at the submodule. Not escalating — see § 7.3.

### 2.3 Indirectly-relevant closures (per `03-kailash-py-mvp-readiness.md` § 2.2)

These improve Authorship Score reliability without being primary providers:

- `#604` (ISS-32) — algorithm-identifier schema closed: signed `authored_count` will carry `algorithm_identifier` matching the Trust Store adapter's `_with_algorithm_id()` helper (per `05-trust-store-implementation.md` § 3.4). The deterministic-replay scorer's signature-verification path inherits the Trust Store's algorithm-versioning discipline.
- `#598` (ISS-13) — `PlanSuspension` parity closed: relevant for SUPERVISED-tier plans whose mid-plan posture demotion suspends the plan rather than aborting it.
- `#735` — Kaizen ThreadPoolExecutor `contextvars` propagation fix: relevant for the Boundary Conversation context that seeds the initial PSEUDO posture (shard 8 → shard 9).

---

## 3. Envoy-new-code surface

Per `03-kailash-py-mvp-readiness.md` § 3 row 6: "**Envoy-new-code:** `AuthorshipScore` computation; `PostureGate` enforcement at DELEGATING/AUTONOMOUS transition; BET-12 measurement hook." Concrete surface, scoped to the four required hooks per the shard prompt.

### 3.1 `envoy.authorship.AuthorshipScore` — deterministic computation from Ledger entries (NOT just PostureStore reads)

The score primitive's source-of-truth is the **Ledger** (per `specs/authorship-score.md` § Re-derivation from the Ledger), not the PostureStore. The PostureStore tracks the _current_ posture and its transition history; the Ledger tracks the _signed authoring events_ that gate posture transitions. These are different surfaces:

- **PostureStore (kailash-py-provided)** — reads/writes "what posture is agent X at right now" and "history of posture transitions for X."
- **Ledger (Envoy-built, shard 6)** — append-only signed record of every `envelope_edit`, `posture_change`, `grant_moment`, etc. Authoring events that mutate `envelope.*.authored_constraints[*].authored` flags appear here.

`envoy.authorship.AuthorshipScore` is therefore a **pure function over (envelope, ledger_slice)** that re-derives the three signed counters per `specs/authorship-score.md` § Re-derivation:

```python
counters = AuthorshipScore.recompute(envelope, ledger_slice)
# returns AuthorshipCounters(authored_count, imported_count, template_provenance)
```

**Determinism + replayability + auditability invariant (load-bearing):**

> Recomputing the score from the same `(envelope, ledger_slice)` MUST yield byte-identical `AuthorshipCounters`. This is the verifier hook that backs the `AuthorshipScoreDivergenceError` audit alert in `specs/authorship-score.md` § Stored vs recomputed (M-05 fix).

Determinism is preserved by:

1. **Iteration order pinned** — iterate the five envelope dimensions in canonical order `("financial", "operational", "temporal", "data_access", "communication")` (per `rules/terrene-naming.md` § Canonical Terminology — these exact five names, no synonyms, no reordering); within each dimension, iterate `authored_constraints` in their canonical-JSON-sorted order per `specs/envelope-model.md` § Canonical JSON (JCS + NFC).
2. **Novelty + minimum-impact functions are pure** — `novelty_check(c, envelope, ledger_slice)` and `minimum_impact_check(c, envelope, ledger_slice)` MUST NOT call `time.time()`, `random`, OS-locale-dependent collation, or any PostureStore lookup. Network-fetched classifier registries MUST be pinned by hash before the recompute begins (see § 3.4 below).
3. **Template-provenance ordering** — the deduplication-via-set in the spec pseudocode (`origin not in {(t["template_id"], t["template_hash"]) for t in template_provenance}`) is order-independent for set membership but the `template_provenance` _list_ is order-preserving (insertion-order). Iteration over `imported_constraints` happens in canonical-JSON order; `template_provenance` insertion order is therefore deterministic.
4. **Ledger slice is content-addressed** — `ledger_slice` is identified by `(start_entry_id, end_entry_id)` pair (both SHA-256 content hashes per `specs/ledger.md` § Entry envelope schema); two recomputes against the same slice IDs produce the same slice bytes.
5. **No mutable global state** — the `AuthorshipScore` class MUST be a stateless pure-function holder; no module-level caches keyed by mutable inputs.

**Fail-closed defaults (per `rules/security.md` § Rust: Fail-Closed Security Defaults — Python equivalent):**

- `recompute(envelope, ledger_slice=None)` with `ledger_slice is None` MUST raise `LedgerSliceRequiredError`, NOT default to "use the local Ledger." The Ledger is the source of truth; the caller MUST pass it explicitly so the recompute is bound to a specific Ledger snapshot.
- `recompute(envelope=None, ...)` MUST raise `EnvelopeRequiredError`.
- Numeric-NaN/Inf in `success_rate` / `time_at_current_posture_hours` is already validated by `PostureEvidence.__post_init__` per `postures.py:254-278` — Envoy MUST NOT bypass this validation by constructing `PostureEvidence` from `dict` without validation.

### 3.2 `envoy.authorship.PostureGate` — enforcement at posture-transition entry points

The gate primitive is the **structural enforcement of the §2.2 category-move thesis**. Without it, DELEGATING/AUTONOMOUS posture transitions have no structural enforcement and the §2.3 Authorship-as-agency claim collapses to "consent to envelope" (Little Snitch class — per the shard prompt and `02-mvp-objectives.md` § 3 cross-cutting deliverable "Authorship Score primitive + posture gate"). BET-12 (governance-primary-surface) is what falsifies if the gate fails to enforce.

Surface:

```python
class PostureGate:
    def __init__(
        self,
        *,
        principal_id: str,
        trust_store_adapter: "TrustStoreAdapter",   # shard 5
        ledger: "EnvoyLedger",                      # shard 6
        score_primitive: "AuthorshipScore",         # § 3.1
        bet12_emitter: "BET12CadenceEmitter",       # § 3.3
    ) -> None: ...

    async def request_transition(
        self,
        *,
        principal_id: str,
        agent_id: str,
        current: TrustPosture,
        target: TrustPosture,
        envelope,                     # current Envelope dataclass
        ledger_slice_id: str,         # content-addressed slice for the recompute
        mode: Literal["personal", "enterprise"],
        genesis_signed_grant: Optional[bytes],   # Grant Moment co-signature (None on raw call)
        cooling_off_active: bool,                # source: weekly-posture-review state
    ) -> "PostureChangeResult":
        """Five-step enforcement.

        1. Recompute AuthorshipCounters via score_primitive.recompute(envelope, ledger_slice).
        2. Verify metadata.authorship_score.authored_count signed value matches recomputed
           authored_count; mismatch -> AuthorshipScoreDivergenceError (T-023 defense).
        3. Compute N_required for (current, target, mode) per specs/posture-ladder.md
           § State-transition contract; if recomputed authored_count < N_required AND
           target > current -> PostureAuthorshipInsufficientError (refuse, fail-closed).
        4. Verify genesis_signed_grant present on ratchet-up (PostureGenesisGrantMissingError);
           verify cooling-off NOT active (PostureCoolingOffActiveError).
        5. Enterprise + target == AUTONOMOUS -> PostureEnterpriseAutonomousForbidden.

        On success: append posture_change Ledger entry (Genesis-signed, NOT runtime-signed
        per specs/ledger.md Entry types), call SQLitePostureStore.set_posture(...),
        SQLitePostureStore.record_transition(...), and emit BET-12 cadence event.
        """
```

**Fail-closed enforcement (load-bearing per `rules/security.md` § Fail-Closed):**

- The default verdict on missing or error data is **REFUSE**. Specifically:
  - `ledger_slice_id` not resolvable → `LedgerSliceUnavailableError`, **deny**.
  - PostureStore connection error → `PostureStoreUnavailableError`, **deny**.
  - `score_primitive.recompute()` raises any unexpected error → re-raise as `AuthorshipScoreRecomputeError`, **deny**.
  - `current` and `target` are not both members of the canonical 5-set → `PostureUnknownError`, **deny**.
  - Backward-compat alias values (e.g. raw "delegated") are accepted at the API boundary (kailash-py's `_missing_` resolver canonicalizes them per `postures.py:50-82`), but the gate logs a `PostureLegacyAliasUsage` ledger entry so cohort tracking can phase the aliases out.
- The `request_transition` method MUST NEVER return `PostureChangeResult(success=True)` on any error path. Per `rules/zero-tolerance.md` Rule 3 (No Silent Fallbacks): no `except: pass`, no `except Exception: return None` without raising.

**Tenant-isolation Rule 1 hook (per `rules/tenant-isolation.md`):**

- Every key, every cache, every metric label MUST carry `principal_id` from day 1, even though Phase 01 is single-principal. Canonical key shape: `envoy:authorship:v1:{principal_id}:{agent_id}:counters`. Drop-`principal_id` "because there's only one principal in MVP" is BLOCKED — same hedge as Trust Store (per `05-trust-store-implementation.md` § 3.2).
- Strict mode (Rule 2): missing `principal_id` raises `PrincipalRequiredError`. The PostureGate constructor REQUIRES `principal_id` (kw-only; no default); the score primitive's `recompute()` does NOT take `principal_id` because it is a pure function over `(envelope, ledger_slice)` — but the _caller_ (PostureGate or any other consumer) MUST scope the ledger_slice to the principal. The Ledger slice query API (shard 6) takes `principal_id` as a required keyword argument.
- Cascade-revocation hook (Rule 3): on demotion via kill-criterion or annual decay, the gate MUST call `trust_store_adapter.revoke(principal_id=..., agent_id=..., reason="posture_demotion", revoked_by=<principal_genesis_id>)` to cascade-revoke any DelegationRecord whose envelope was authored under the higher posture.

### 3.3 `envoy.authorship.BET12CadenceEmitter` — cohort-level posture-transition cadence hook

Per the shard prompt: "BET-12 measurement hook: Phase 01 must capture cohort-level posture-transition cadence for the BET measurement, even if the BET itself converges in Phase 02+." Per `02-mvp-objectives.md` § 3, BET-12 (governance-primary-surface palatability) requires falsifiable measurement — without a cadence emitter shipped in Phase 01, the BET is unfalsifiable until Phase 02. The emitter is a structural prerequisite, not an exit criterion.

Surface:

```python
class BET12CadenceEmitter:
    """Emits cohort-level posture-transition cadence events.

    Captures per-transition (from, to, principal_id_hashed, timestamp,
    days_at_current_posture, authored_count_at_transition). Sink is
    pluggable: Phase 01 default sink is local-only (writes to Ledger
    'ritual_completion' entry type with bet_id="BET-12"); Phase 02
    Foundation Health Heartbeat sink (per specs/foundation-health-heartbeat.md)
    aggregates across consenting principals.
    """

    async def emit(
        self,
        *,
        principal_id: str,
        from_level: TrustPosture,
        to_level: TrustPosture,
        days_at_current_posture: float,
        authored_count_at_transition: int,
    ) -> None: ...
```

**Privacy-preserving cohort hook (forward-compat with `specs/foundation-health-heartbeat.md` STAR/Prio):**

- The emitter MUST hash `principal_id` via the same fingerprint shape used by `format_record_id_for_event` (per `rules/event-payload-classification.md` Rule 2) so cross-SDK forensic correlation works without leaking raw principal IDs into the eventual Heartbeat aggregation. Hash shape: `f"sha256:{hashlib.sha256(principal_id.encode()).hexdigest()[:8]}"`.
- The emitter MUST NOT emit `posture` _content_ in payloads beyond the (from, to) levels — content beyond the level enum (e.g. envelope hash, authored_constraints names) is BLOCKED per `rules/event-payload-classification.md` Rule 3 (classified field names MUST NOT appear in `fields_changed` / event payloads).

### 3.4 Pinned-classifier-registry contract (determinism preservation)

The score's `novelty_check` invokes `envoy-registry:novelty.adversarial-wording:v1` per `specs/authorship-score.md` § Novelty de-duplication algorithm step 3. The classifier registry is mutable across Foundation quarterly retrains (per `specs/authorship-score.md` § Cold-start + § Open questions item 1), so determinism breaks if `recompute()` re-fetches the live classifier each call.

The structural defense:

- `AuthorshipScore.recompute(envelope, ledger_slice, *, classifier_pin: ClassifierPin)` REQUIRES a pinned classifier reference. `ClassifierPin = (registry_uri, registry_hash)` — both SHA-256 content-addressed.
- The pin is captured at envelope-sign time and stored alongside `metadata.authorship_score.authored_count` (per `specs/authorship-score.md` § Stored counters + § Stored vs recomputed). Recompute reads the pin from the envelope, fetches the classifier bytes from the local registry cache (which is itself content-addressed), verifies the hash, and only then runs the adversarial-wording check.
- Pin-mismatch at recompute (e.g. user manually upgraded the classifier registry between sign + verify) raises `ClassifierRegistryMissError` per `specs/authorship-score.md` § Error taxonomy (refuse novelty check fail-closed, user re-prompts after registry sync). This is the same surface the spec already names; the Envoy-new-code is the pinning + verification machinery.

This is the structural defense against the `specs/authorship-score.md` § Open questions item 5 — "Re-derivation cost on long Ledger histories — caching strategy to keep verify <50ms latency budget" — without compromising determinism: cached results are content-addressed by `(envelope_hash, ledger_slice_id, classifier_pin)` triple; cache hit is byte-identical-by-construction.

---

## 4. Class structure sketch (interfaces only)

This is a pseudocode sketch, not implementation. Per the per-shard structure (`01-shard-plan.md` § 2 step 4): "Sketch the primitive's class structure (interfaces, not implementation)."

```python
# envoy/authorship/score.py — deterministic re-derivation from the Ledger

from dataclasses import dataclass
from typing import Literal, Optional

from kailash.trust.posture.postures import (
    TrustPosture, PostureEvidence, TransitionResult, PostureTransition,
)
from kailash.trust.posture.posture_store import SQLitePostureStore


@dataclass(frozen=True)
class ClassifierPin:
    """Content-addressed pin to a specific novelty-classifier version."""
    registry_uri: str          # "envoy-registry:novelty.adversarial-wording:v1"
    registry_hash: str         # "sha256:..."


@dataclass(frozen=True)
class AuthorshipCounters:
    """Result of AuthorshipScore.recompute(); mirrors specs/authorship-score.md."""
    authored_count: int
    imported_count: int
    template_provenance: tuple[tuple[str, str], ...]   # ((template_id, hash), ...)


class LedgerSliceRequiredError(Exception): ...
class EnvelopeRequiredError(Exception): ...
class AuthorshipScoreRecomputeError(Exception): ...
class AuthorshipScoreDivergenceError(Exception): ...   # specs/authorship-score.md § Error taxonomy
class ClassifierRegistryMissError(Exception): ...      # specs/authorship-score.md § Error taxonomy


class AuthorshipScore:
    """Pure-function deterministic re-derivation from (envelope, ledger_slice).

    Stateless — no instance state. The class is a namespace for
    recompute() and its helpers; instances are NOT constructed.
    """

    @staticmethod
    def recompute(
        envelope,                 # specs/envelope-model.md §Schema
        ledger_slice,             # specs/ledger.md slice
        *,
        classifier_pin: ClassifierPin,
    ) -> AuthorshipCounters:
        """Re-derive authored / imported / template_provenance from inputs.

        MUST be deterministic, replayable, auditable. Same inputs -> same
        AuthorshipCounters bytes. No clock reads, no random, no live network.
        """
        if envelope is None:
            raise EnvelopeRequiredError(...)
        if ledger_slice is None:
            raise LedgerSliceRequiredError(...)
        # iterate 5 dimensions in canonical order; iterate authored_constraints
        # in JCS-sorted order; novelty_check + minimum_impact_check are pure
        ...


# envoy/authorship/gate.py — posture-transition enforcement


class PrincipalRequiredError(Exception): ...
class PostureUnknownError(Exception): ...
class PostureAuthorshipInsufficientError(Exception): ...
class PostureGenesisGrantMissingError(Exception): ...
class PostureCoolingOffActiveError(Exception): ...
class PostureEnterpriseAutonomousForbidden(Exception): ...
class PostureStoreUnavailableError(Exception): ...
class LedgerSliceUnavailableError(Exception): ...


@dataclass(frozen=True)
class PostureChangeResult:
    """Mirrors specs/posture-ladder.md § Algorithm `PostureChangeResult`."""
    new_level: TrustPosture
    ledger_entry_id: str         # sha256: of the appended posture_change entry


# Personal-mode + enterprise-mode threshold tables, frozen module constants
_PERSONAL_THRESHOLDS = {   # (current, target) -> N_required
    (TrustPosture.PSEUDO, TrustPosture.TOOL): 0,
    (TrustPosture.TOOL, TrustPosture.SUPERVISED): 1,
    (TrustPosture.SUPERVISED, TrustPosture.DELEGATING): 3,
    (TrustPosture.DELEGATING, TrustPosture.AUTONOMOUS): 5,
}
_ENTERPRISE_THRESHOLDS = {
    (TrustPosture.PSEUDO, TrustPosture.TOOL): 0,
    (TrustPosture.TOOL, TrustPosture.SUPERVISED): 1,
    (TrustPosture.SUPERVISED, TrustPosture.DELEGATING): 5,
    # DELEGATING -> AUTONOMOUS forbidden in enterprise (per spec)
}


class PostureGate:
    """Posture-transition enforcement gate.

    Composes SQLitePostureStore (kailash-py) + EnvoyLedger (shard 6) +
    AuthorshipScore (this shard) + BET12CadenceEmitter.

    Every transition entry-point goes through this gate; bypassing
    is BLOCKED (orphan-detection.md MUST Rule 1 — there is exactly
    one production call site path: this gate).
    """

    def __init__(
        self,
        *,
        principal_id: str,
        posture_store: SQLitePostureStore,
        trust_store_adapter,                # shard 5 TrustStoreAdapter
        ledger,                              # shard 6 EnvoyLedger
        score_primitive: type[AuthorshipScore] = AuthorshipScore,
        bet12_emitter: "BET12CadenceEmitter",
    ) -> None:
        if not principal_id:
            raise PrincipalRequiredError(...)
        ...

    async def request_transition(
        self,
        *,
        principal_id: str,
        agent_id: str,
        current: TrustPosture,
        target: TrustPosture,
        envelope,
        ledger_slice_id: str,
        classifier_pin: ClassifierPin,
        mode: Literal["personal", "enterprise"],
        genesis_signed_grant: Optional[bytes],
        cooling_off_active: bool,
    ) -> PostureChangeResult:
        """5-step enforcement; fail-closed on every error path."""
        ...

    async def emergency_demote(
        self,
        *,
        principal_id: str,
        agent_id: str,
        target: TrustPosture,
        reason: str,
        revoked_by: str,
    ) -> PostureChangeResult:
        """Kill-criterion / annual-decay demotion path.

        Demotion is always permitted (per posture-ladder.md § Ratchet-down).
        MUST cascade-revoke descendant DelegationRecords issued under the
        higher posture via trust_store_adapter.revoke(...).
        """
        ...


# envoy/authorship/bet12.py — cohort-level cadence emitter


class BET12CadenceEmitter:
    """Hash-fingerprinted posture-transition cadence emitter.

    Phase 01 sink: writes ritual_completion Ledger entry with
    bet_id='BET-12'. Phase 02 sink: Foundation Health Heartbeat
    STAR/Prio aggregation per specs/foundation-health-heartbeat.md.
    """

    def __init__(self, *, sink: "BET12Sink") -> None: ...

    async def emit(
        self,
        *,
        principal_id: str,        # hashed before emission per Rule 2 above
        from_level: TrustPosture,
        to_level: TrustPosture,
        days_at_current_posture: float,
        authored_count_at_transition: int,
    ) -> None: ...
```

This sketch is interfaces only; implementation is shard-out-of-scope.

---

## 5. Integration points

The Authorship Score + Posture Gate underpins (and is underpinned by) five neighboring primitives. Each is one Envoy-primitive ↔ Authorship-Score hop.

| Neighboring primitive (shard) | Hook                                                                                                                                                                                                                              | Direction          | Spec citation                                                                                                     |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| Trust Store (5)               | Posture writes go through `SQLitePostureStore` opened by the TrustStoreAdapter; cascade-revoke on demotion goes through `trust_store_adapter.revoke(...)` (per `05-trust-store-implementation.md` § 3.3)                          | AS → TS write      | `specs/posture-ladder.md` § Algorithm; `specs/trust-lineage.md` § Cascade revocation                              |
| Envoy Ledger (6)              | Read: `recompute()` consumes a content-addressed Ledger slice (envelope_edit + posture_change + grant_moment entries). Write: every successful `request_transition` appends a Genesis-signed `posture_change` entry to the Ledger | AS ↔ Ledger        | `specs/ledger.md` § Entry types row `posture_change`; `specs/authorship-score.md` § Re-derivation                 |
| Boundary Conversation (8)     | First-time-user conversation seeds initial `PSEUDO` posture via `posture_store.set_posture(agent_id, TrustPosture.PSEUDO)`. PSEUDO→TOOL ratchet at end of Boundary Conversation if user authored ≥0 constraints (N=0 threshold)   | BC → AS write      | `specs/posture-ladder.md` § Per-tier semantics PSEUDO; `specs/boundary-conversation.md` (out of scope this shard) |
| Grant Moment (10)             | Grant Moment co-signature feeds `genesis_signed_grant` parameter to `request_transition`. The ratchet-up ceremony IS a Grant Moment per `specs/posture-ladder.md` § Cross-references                                              | GM → AS            | `specs/posture-ladder.md` § State-transition contract step 2; `specs/grant-moment.md`                             |
| Daily Digest (11)             | Reads PostureStore history + BET-12 ledger entries to render "your posture progress" panel; surfaces cooling-off windows + annual-decay countdown                                                                                 | AS → DD read       | `specs/posture-ladder.md` § Cross-references; `specs/daily-digest.md`                                             |
| Channel adapters (16)         | Channel-native posture rendering ("[posture: SUPERVISED]" per channel UI); cross-channel coherence (EC-8): a posture ratchet-up ceremony co-signed on Telegram is honored by a Slack action 3 days later                          | Adapters → AS read | `02-mvp-objectives.md` EC-8 acceptance gate; `specs/channel-adapters.md`                                          |
| Weekly Posture Review (─)     | Weekly review ritual calls `request_transition` for user-initiated ratchet OR `emergency_demote` for user-initiated downgrade; cooling-off window state is sourced from Weekly Review ledger entries                              | WPR ↔ AS           | `specs/weekly-posture-review.md`                                                                                  |

Per `rules/orphan-detection.md` MUST Rule 1 ("Every `db.*` / `app.*` Facade Has a Production Call Site"), each `PostureGate` method enumerated in §4 MUST have at least one production call site in the Envoy hot path within 5 commits of the facade landing. The integration-point table above pre-declares the required call sites (BC seeds initial posture; GM feeds ratchet-up; WPR drives both ratchet directions; emergency_demote fires on kill-criterion).

Per `rules/facade-manager-detection.md` MUST Rule 1 ("Every Manager-Shape Class Has a Tier 2 Test"), `PostureGate` is a `*Gate`-shape class on the framework's top-level surface (Envoy treats `*Gate` as part of the manager-shape class set per the rule's intent — load-bearing classes that own state and enforce invariants); it MUST have at least one Tier 2 test that imports it through the framework facade and asserts an externally-observable effect (a `posture_change` row in the Ledger SQLite, a posture row update in the PostureStore SQLite, a successful cascade-revoke propagation).

Per `rules/facade-manager-detection.md` MUST Rule 3 ("Manager Constructor Receives the Framework Instance"), `PostureGate.__init__` takes `posture_store / trust_store_adapter / ledger / score_primitive / bet12_emitter` as explicit dependencies — no global lookup, no self-construction of the underlying `SQLitePostureStore`. The `SQLitePostureStore` instance is owned by the TrustStoreAdapter and passed in (single source of the SQLite handle; consistent with `05-trust-store-implementation.md` § 3.1 hook 3).

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/testing.md` § "Tier 2 (Integration): Real infrastructure recommended" — real SQLite + real Ed25519 keys + real Ledger, NO mocking. Per `rules/orphan-detection.md` MUST Rule 2 ("Every Wired Manager Has a Tier 2 Integration Test"). Phase 01 EC-2 (Grant Moments triggered + cascade), EC-6 (redteam clean), EC-8 (cross-channel coherence) all transitively require Authorship Score + Posture Gate integration tests.

### 6.1 Tier 2 — real infrastructure

| Test                                                            | Asserts                                                                                                                                                                                                                                                                                 | Spec source                                                                                         |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `test_authorship_score_recompute_deterministic_replay.py`       | Construct envelope + N (e.g. 50) ledger entries. Run `recompute()` 100 times in a row. Assert all 100 results are byte-identical `AuthorshipCounters`. Assert iteration order pinned across the five canonical dimensions.                                                              | `specs/authorship-score.md` § Re-derivation; § Stored vs recomputed (M-05 fix); § Score computation |
| `test_authorship_score_recompute_from_ledger_matches_signed.py` | Sign envelope with `metadata.authorship_score.authored_count = 3`. Recompute against the Ledger slice; assert recomputed `authored_count == 3`. Mutate one Ledger entry (flip one `authored=true` → `false`); recompute again; assert mismatch raises `AuthorshipScoreDivergenceError`. | `specs/authorship-score.md` § Stored vs recomputed (M-05 fix); T-023 defense                        |
| `test_authorship_score_classifier_pin_required.py`              | `recompute()` without `classifier_pin` raises; with stale pin raises `ClassifierRegistryMissError`; with valid pin succeeds.                                                                                                                                                            | `specs/authorship-score.md` § Error taxonomy `ClassifierRegistryMissError`                          |
| `test_posture_gate_fail_closed_on_missing_ledger_slice.py`      | `request_transition` with unresolvable `ledger_slice_id` raises `LedgerSliceUnavailableError`; PostureStore is NOT mutated; no `posture_change` Ledger entry written.                                                                                                                   | `rules/security.md` § Fail-Closed Defaults; `rules/zero-tolerance.md` Rule 3                        |
| `test_posture_gate_refuses_delegating_below_threshold.py`       | Personal-mode SUPERVISED → DELEGATING request with `authored_count = 2` (N_required = 3) raises `PostureAuthorshipInsufficientError`; PostureStore unchanged; Ledger unchanged.                                                                                                         | `specs/posture-ladder.md` § State-transition contract step 1                                        |
| `test_posture_gate_refuses_delegating_without_genesis_grant.py` | SUPERVISED → DELEGATING with `authored_count = 3` but `genesis_signed_grant = None` raises `PostureGenesisGrantMissingError`.                                                                                                                                                           | `specs/posture-ladder.md` § State-transition contract step 2                                        |
| `test_posture_gate_refuses_autonomous_in_enterprise_mode.py`    | Enterprise-mode DELEGATING → AUTONOMOUS raises `PostureEnterpriseAutonomousForbidden` (T-024 defense).                                                                                                                                                                                  | `specs/posture-ladder.md` § Per-tier semantics AUTONOMOUS                                           |
| `test_posture_gate_writes_posture_change_ledger_entry.py`       | Successful SUPERVISED → DELEGATING transition writes a `posture_change` Ledger entry signed by Genesis key (NOT runtime); entry carries `from_level / to_level / authorship_at_promotion` per `specs/posture-ladder.md` § Algorithm.                                                    | `specs/ledger.md` Entry types row `posture_change`; `specs/posture-ladder.md` § Algorithm           |
| `test_posture_gate_emergency_demote_cascade_revokes.py`         | Build 3-deep delegation tree under DELEGATING. Trigger `emergency_demote` to TOOL. Assert cascade-revoke fires, all descendant DelegationRecords revoked, `RevocationResult.revoked_agents` covers full subtree.                                                                        | `specs/trust-lineage.md` § Cascade revocation; `specs/posture-ladder.md` § Ratchet-down             |
| `test_posture_gate_principal_dimension_required.py`             | `PostureGate.__init__(principal_id="")` raises `PrincipalRequiredError`; canonical key shape `envoy:authorship:v1:{principal_id}:{agent_id}:counters` honored.                                                                                                                          | `rules/tenant-isolation.md` Rule 1 + Rule 2                                                         |
| `test_posture_gate_cooling_off_blocks_ratchet_up.py`            | `cooling_off_active=True` blocks any ratchet-up; ratchet-down unaffected.                                                                                                                                                                                                               | `specs/posture-ladder.md` § State-transition contract step 4                                        |
| `test_posture_gate_legacy_alias_logs_usage.py`                  | Calling `request_transition(current=TrustPosture("delegated"), ...)` (legacy alias for AUTONOMOUS) succeeds via `_missing_` resolver but emits a `PostureLegacyAliasUsage` Ledger entry; cohort-tracking can phase aliases out.                                                         | `~/repos/loom/kailash-py/src/kailash/trust/posture/postures.py:50-82`                               |
| `test_bet12_cadence_emitter_hashes_principal_id.py`             | Emitted event payload contains `principal_id_hash` of shape `sha256:XXXXXXXX` (8 hex chars); raw `principal_id` does NOT appear in `repr(payload)`.                                                                                                                                     | `rules/event-payload-classification.md` Rule 2; `rules/tenant-isolation.md` Rule 4                  |

### 6.2 Tier 3 — cross-OS portability + cross-channel coherence

| Test                                                        | Asserts                                                                                                                                                                                                                                                 | EC tested |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `test_posture_gate_cross_os_score_byte_identity.py` (BET-6) | Sign envelope on macOS; transmit to Linux; recompute() on Linux; assert byte-identical `AuthorshipCounters`. Tests JCS+NFC canonical-form determinism + cross-OS UTF-8 normalization.                                                                   | EC-6      |
| `test_posture_gate_cross_channel_coherence_7day.py`         | Day 1: ratchet-up co-signature on Telegram → DELEGATING. Day 6: action initiated from Slack against the same envelope honors the DELEGATING posture. Day 7: kill-criterion fires; PostureGate `emergency_demote`s via Discord; iMessage action refused. | EC-8      |
| `test_authorship_score_replay_on_long_ledger_history.py`    | Replay `recompute()` against a 30-day Ledger history with ≥10k entries; assert <50ms latency budget per `specs/authorship-score.md` § Open questions item 5; assert byte-identity across 10 replays.                                                    | EC-6      |

### 6.3 Wiring tests (orphan-detection + facade-manager-detection)

Per `rules/facade-manager-detection.md` Rule 2 (test file naming convention) + Rule 3 (constructor receives parent framework instance):

- Test file MUST be named `test_posture_gate_wiring.py` (gate-shape, predictable name; `/redteam` automatically detects missing wiring per `rules/agents.md` § "Reviewer Prompts Include Mechanical AST/Grep Sweep").
- Constructor MUST receive explicit `principal_id / posture_store / trust_store_adapter / ledger / bet12_emitter` (no global lookup, no self-construction).

Per `rules/orphan-detection.md` Rule 1 (production call site within 5 commits):

- Boundary Conversation seeds initial PSEUDO via `posture_store.set_posture(agent_id, TrustPosture.PSEUDO)` (shard 8 → shard 9 hot path).
- Grant Moment passes `genesis_signed_grant` to `request_transition` (shard 10 → shard 9 hot path).
- Weekly Posture Review drives both `request_transition` (ratchet-up) and `emergency_demote` (user-initiated downgrade).
- Daily Digest consumes BET-12 emitter output via Ledger `ritual_completion` entries (shard 11 → shard 9 read path).

Per `rules/orphan-detection.md` Rule 2a (Crypto-Pair Round-Trip): `request_transition` (ratchet-up signed by Genesis) ↔ `verify_posture_change_signature` (Genesis-signed verify) MUST be exercised through the gate facade in at least one Tier 2 round-trip test (not two unit tests with mocks of each other's halves).

---

## 7. Frozen-spec ambiguity surfaced during analysis

Per `01-shard-plan.md` § 4 ("Failure modes + mitigations"), HIGH-severity spec ambiguity escalates via the failure-mode protocol — STOP the deep-dive, convene MUST-Rule-5b sweep per `rules/specs-authority.md`, edit spec under full-sibling redteam economics. Lower-severity ambiguity is logged here but does not block the shard.

### 7.1 LOW — `PostureLevel.IntEnum` (spec) vs `TrustPosture(str, Enum)` (provider) — wire-format-aligned, integer-value-divergent

`specs/posture-ladder.md` § Canonical enum declares `class PostureLevel(IntEnum): PSEUDO = 0 ... AUTONOMOUS = 4`. The kailash-py provider at `postures.py:21` declares `class TrustPosture(str, Enum)` with wire-format string values and `autonomy_level` property mapping AUTONOMOUS→5 ... PSEUDO→1. Both sides agree on:

- The 5-member canonical set (PSEUDO/TOOL/SUPERVISED/DELEGATING/AUTONOMOUS).
- The string wire-format names (uppercase enum members; lowercase string values per kailash-py).
- Integer-ordering direction (AUTONOMOUS > DELEGATING > SUPERVISED > TOOL > PSEUDO).

Both sides DISAGREE on:

- The integer values themselves (spec 0..4; provider 1..5 via `autonomy_level`).

The wire format (string name) is what's load-bearing for cross-SDK byte-identity per BET-6; the integer values are internal-comparison-only on each side and do NOT cross the wire. The Envoy adapter MUST use the `TrustPosture` provider class (not redefine `PostureLevel(IntEnum)`) and rely on the `<` / `>` / `<=` / `>=` dunders defined on `autonomy_level` for ordering checks — not on raw integer values.

**Disposition:** logged as a cross-SDK terminology drift; not a Phase 01 blocker; recommend the spec `posture-ladder.md` annotate that the integer values 0..4 are illustrative-of-ordering-not-of-implementation. Tracked for future spec edit; NOT escalating to HIGH because the wire-format contract is unambiguous.

### 7.2 LOW — PostureEvidence shape divergence: spec uses `evidence.authorship_score` / `evidence.mode` / `evidence.genesis_signed_grant` / `evidence.cooling_off_active`; provider uses `observation_count / success_rate / time_at_current_posture_hours / anomaly_count / source / timestamp / metadata`

`specs/posture-ladder.md` § Algorithm function signature is `posture_change(current, target, evidence: PostureEvidence)` and accesses `evidence.authorship_score / evidence.mode / evidence.genesis_signed_grant / evidence.cooling_off_active`. The kailash-py `PostureEvidence` dataclass at `postures.py:230` has a fundamentally operational shape (observation_count, success_rate, time_at_current_posture_hours, anomaly_count) — the kailash-py `PostureEvidence` is the type used for runtime-monitoring-evidence-driven posture _recommendations_, while the spec's `PostureEvidence` is the type used for _ratchet-ceremony_ evidence.

These are **two different evidence concepts** wearing the same name. The Envoy `PostureGate.request_transition` therefore takes the ceremony-evidence fields as explicit kwargs (`mode`, `genesis_signed_grant`, `cooling_off_active`) rather than as a `PostureEvidence` payload — this avoids name-collision with the kailash-py monitoring-evidence dataclass. The kailash-py `PostureEvidence` IS used (separately) by the BET-12 emitter for cohort-cadence telemetry where the operational metrics are exactly what's needed.

**Disposition:** logged as cross-spec terminology overload; resolved at the Envoy adapter layer by separating `request_transition`'s ceremony-evidence parameters from the `BET12CadenceEmitter`'s use of kailash-py `PostureEvidence`. Not a spec edit; the spec's `evidence.X` accessor pattern is internal-pseudocode notation, not a name-export claim. NOT escalating.

### 7.3 LOW — `SQLitePostureStore` not re-exported at package level

The kailash-py package `__init__.py` at `posture/__init__.py:25-66` exports `TrustPosture`, `PostureEvidence`, `PostureStore` (Protocol), `TransitionResult`, etc., but does NOT re-export the concrete `SQLitePostureStore`. Envoy code MUST import from the submodule path: `from kailash.trust.posture.posture_store import SQLitePostureStore`. This is a developer-experience concern, not a correctness concern — the symbol exists, is module-`__all__`-listed at the submodule, and works as expected when imported directly.

**Disposition:** flagged for upstream filing as a follow-up convenience PR (per `rules/upstream-issue-hygiene.md` — gated, body-redacted); NOT a Phase 01 blocker. Envoy code uses the submodule import path directly.

### 7.4 None HIGH-severity surfaced

No HIGH-severity ambiguity surfaced during this shard. The Authorship Score primitive's score formula is well-specified (the pseudocode in `specs/authorship-score.md` § Re-derivation is unambiguous for deterministic implementation); the posture-transition contract is well-specified (`specs/posture-ladder.md` § State-transition contract names every required check with thresholds + signers + cooling-off semantics); and the cross-SDK provider gap is bridge-able at the Envoy adapter layer.

**On the score-formula determinism specifically (per shard prompt):** the spec's pseudocode uses `for c in getattr(envelope, dim).authored_constraints:` which depends on `authored_constraints` having a deterministic iteration order. Per `specs/envelope-model.md` § Canonical JSON (JCS + NFC), the envelope dataclass canonicalizes its constraint lists in JCS-sorted order; the `authored_constraints` list MUST be sorted at envelope construction time. This is a requirement Envoy MUST honor in the envelope compiler (shard 4) — it's not a frozen-spec ambiguity, it's an implementation contract that crosses shards. Logged here as a cross-shard invariant for shard 4 to verify.

---

## 8. Cross-references

- **Phase 01 brief:** `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`
- **Inheritance map:** `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md`
- **Sharding plan:** `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (shard 9 row) + § 5 (sequencing — Authorship Score is in Group B, depends on Trust Store from Group A; gates Grant Moment (10) ratchet-up ceremony + Weekly Posture Review)
- **MVP objectives:** `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` § 3 cross-cutting deliverable "Authorship Score primitive + posture gate"; EC-2 (Grant Moments cascade), EC-6 (redteam clean), EC-8 (cross-channel coherence)
- **kailash-py readiness:** `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 6 + § 5 verification protocol
- **Trust Store implementation:** `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 2.2 verified provider; § 3.1 TrustStoreAdapter composition wrapper; § 3.2 principal-dimension key-shape; § 3.3 cascade-revocation glue; § 5 integration table row "Authorship Score"
- **Methodology bridge:** `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`
- **Phase 00 survey items:** `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` items 5 (PostureStore), 6 (Phase-13 type bundle)
- **Phase 00 reconciliation:** `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` rows 5, 6
- **Phase 00 thesis:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` § 2.3 (Authorship as agency); § 5 BET-12 (governance-primary-surface)
- **Source specs (FROZEN — DO NOT EDIT):** `specs/authorship-score.md`, `specs/posture-ladder.md`, `specs/trust-lineage.md` (cascade-revocation hook), `specs/ledger.md` (`posture_change` entry type), `specs/envelope-model.md` (`metadata.authorship_score` schema), `specs/foundation-health-heartbeat.md` (BET-12 sink forward-compat)
- **Verified provider modules (read-only references):**
  - `~/repos/loom/kailash-py/src/kailash/trust/posture/posture_store.py` (SQLitePostureStore at line 221; `__all__` at lines 46–49)
  - `~/repos/loom/kailash-py/src/kailash/trust/posture/postures.py` (TrustPosture at line 21; PostureEvidence at line 230; PostureTransition at line 129; TransitionResult at line 196)
  - `~/repos/loom/kailash-py/src/kailash/trust/posture/__init__.py` (package exports lines 25–66; SQLitePostureStore NOT re-exported at package level — see § 7.3)
- **Closed upstream issues verified:** terrene-foundation/kailash-py#597 (closed 2026-04-24T17:02:09Z, "Confirm Phase-13 posture/verification type bundle completeness"; closed by spec-confirmation, not PR-merge)
- **Applicable rules:** `.claude/rules/security.md` § Fail-Closed Defaults (Python equivalent of Rust pattern), `.claude/rules/tenant-isolation.md` Rule 1 + Rule 2 + Rule 4 (bounded label cardinality), `.claude/rules/orphan-detection.md` Rule 1 + Rule 2 + Rule 2a, `.claude/rules/facade-manager-detection.md` Rule 1 + Rule 2 + Rule 3, `.claude/rules/event-payload-classification.md` Rule 2 + Rule 3, `.claude/rules/zero-tolerance.md` Rule 3 (no silent fallbacks) + Rule 4 (no SDK workarounds), `.claude/rules/testing.md` § Tier 2 + § Tier 3, `.claude/rules/specs-authority.md` MUST Rule 4 (read specs before acting) + MUST Rule 7 (delegation includes spec content), `.claude/rules/terrene-naming.md` § Canonical Terminology (five constraint dimensions), `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget, `.claude/rules/upstream-issue-hygiene.md` (for the § 7.3 follow-up convenience PR)
