# 15 — Shamir 3-of-5 Recovery — Implementation Analysis

**Document role:** Phase 01 implementation analysis for the SLIP-0039 Shamir 3-of-5 Trust Vault recovery primitive (shard 15 of 25 of the /analyze plan, per `01-shard-plan.md` §2). Identifies the verified `kailash-py` provider modules (the `kailash.trust.vault` package landed via #606 in v2.11.0 on 2026-04-25), the Envoy-new-code surface that wraps them (paper-shard renderer + ritual coordinator + reconstruction CLI + commitment verifier), and the integration points to neighboring primitives (Trust Store hooks, Boundary Conversation ritual host, Channel adapter ritual surfaces). Cites Phase 00 + Phase 01 frozen artifacts; never paraphrases.

**Date:** 2026-05-03 (shard 15 of /analyze).
**Status:** DRAFT — load-bearing for shards 8 (Boundary Conversation), 16 (Channel Adapters), 19 (pipx Distribution — `[shamir]` extra propagation).
**Capacity check:** 1 primitive, 2 source specs (`shamir-recovery.md`, `trust-vault.md`), 4 cross-spec touch-points (`trust-lineage.md` § shard_public_commitments, `boundary-conversation.md` § S8, `connection-vault.md` § post-recovery re-pair, `threat-model.md` § T-002 + T-006), ~8 invariants tracked (10-combo reconstruct exhaustion, cross-tool interop, paper-shard renderability, plain-language errors, master-key-NOT-in-Connection-Vault, ritual-fires-once gate, commitment-verify defense against counterfeit shards, rotation-grace-period). Within `rules/autonomous-execution.md` § Per-Session Capacity Budget.

---

## 1. Source spec citation + ADR-0003

The Shamir recovery primitive is defined by one frozen Phase 00 spec and one architecture decision. Phase 01 implementation MUST NOT re-derive these — per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, the shard's question is "given this spec is frozen, how do I wire `kailash-py` to deliver it?" not "is the spec right?".

- **Shamir recovery (SLIP-0039 ritual)** — `specs/shamir-recovery.md` § Purpose + § Algorithm + § Default threshold + § Distribution guidance + § Card format + § Recovery flow + § Rotation ritual + § Shard public commitments + § Error taxonomy. Key facts cited verbatim:
  - § Algorithm (lines 13–15): "SLIP-0039 via audited libraries: Rust `sharks` / `vsss-rs`; Python `slip39` / `python-shamir-mnemonic`. Phase 00 crypto audit required."
  - § Default threshold (line 19): "3-of-5. User-configurable 2-of-3 to 5-of-9."
  - § Distribution guidance (lines 22–24): "Default: 3 cards in user's own safes, 2 with trusted humans. Alternative: 5 in user's own safes (no human holders) — recommended for high-OPSEC users."
  - § Card format (lines 28–30): "24 BIP-39 words; Trezor-compatible. NO 'Envoy' label; NO name. Distribution checklist persists only opaque slot labels in Trust Vault; real names optional + in hidden envelope (Phase 04) only (H-06 fix)."
  - § Recovery flow (line 33): "Enter words from any 3 cards (any order). Per-card checksum validation at entry (L-03 fix). Reconstruction; vault unlock."
  - § Rotation ritual (line 37): "When shard-holder becomes unreachable (death, estrangement, relocation): `envoy shamir rotate`. New 5 cards; 4 non-rotated old cards remain valid for 30-day grace period, then deprecated."
  - § Shard public commitments (line 41): "Per specs/trust-lineage.md — Genesis Record carries `shard_public_commitments: [algo:hash]` array for recovery verification without shard exposure."
  - § Error taxonomy (lines 45–55): nine typed errors — `InsufficientSharesError`, `ShardChecksumFailedError`, `CommitmentVerificationFailedError`, `RecoveryRateLimitedError`, `ShardSlotLabelMismatchError`, `RotationGracePeriodElapsedError`, `EnvoyLabelOnCardWarning`, `CryptoLibAuditMissingError`, `ShardPublicCommitmentMissingError`.
- **Trust Vault file format (Shamir-wrapped master key region)** — `specs/trust-vault.md` § File format (line 15): "Binary with magic-bytes header, algorithm_identifier, padding-bucket size, **encrypted master key (Shamir-wrapped)**, encrypted regions ..." — confirms the master key is Shamir-wrapped at file-format level. § Cross-references (line 69): "specs/shamir-recovery.md — master key splitting." § Distinct from Connection Vault: Trust Vault holds the cryptographic identity material; Connection Vault holds OS-keychain tokens. The Shamir backup binds ONLY the Trust Vault master key (lines 14–15) — Connection Vault is explicitly out of Shamir scope per `specs/shamir-recovery.md` cross-references line 62 ("specs/connection-vault.md — re-pair after recovery (Connection Vault not Shamir-covered)").
- **ADR-0003** (sovereignty stack — SLIP-0039 + Shamir 3-of-5 default + paper-shard format) — referenced in `briefs/00-phase-01-mvp-scope.md` and `02-mvp-objectives.md` EC-5 acceptance gate. The decision binds: Phase 01 ships SLIP-0039 (not Shamir-Lite or VSSS); 3-of-5 is the default (not 2-of-3); paper-shard format is the canonical interop surface across SDKs. EC-5 (`02-mvp-objectives.md` lines 70–80) is the strongest sovereignty-thesis acceptance gate — failure here directly falsifies BET-9a (Shamir recovery learnable) AND BET-9b (vault portability) AND transitively BET-3 (sovereignty).

EC-5 acceptance gate cited verbatim (`02-mvp-objectives.md` lines 78–80):

> Acceptance gate: (a) The 3-of-5 reconstruct test passes for all C(5,3)=10 share combinations, (b) The Boundary Conversation pauses for the backup ritual at least once, (c) An Envoy-generated SLIP-0039 share reconstructs successfully via a non-Envoy tool (`python-shamir-mnemonic` minimum; Trezor SDK if accessible), (d) Reconstruction failure produces a clear-language error message, not a binary-data dump.

---

## 2. Verified provider citation (post-freshness-gate)

Per `03-kailash-py-mvp-readiness.md` § 5 (verification protocol) + § 3 row 12 (Shamir 3-of-5 recovery), the Phase 00 survey baseline (`02-kailash-py-survey.md` item 26: "SLIP-0039 absent on 04-21 baseline") was extended by the 2026-05-03 freshness gate. Verification was executed for this shard.

### 2.1 Closed-issue + landed-feature evidence

| Phase 00 ISS | GH#                               | Closed     | Landed-feature                                                                                                                                                                                                                                                                                                                                                                                                              | Verified location                                                                                                                                                                                                                                                          |
| ------------ | --------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ISS-37       | terrene-foundation/kailash-py#606 | 2026-04-26 | "SLIP-0039 Shamir secret-sharing integration for Trust Vault backup" — landed in `kailash 2.11.0` (CHANGELOG line 176 + lines 183–188): new package `kailash.trust.vault` with `ShamirRitual` frozen dataclass + `generate` / `reconstruct` / `serialize_shard` / `deserialize_shard` / `rotate_holders` lazy-import helpers + `back_up_vault_key` stub (binding gate awaiting mint ISS-37); new optional extra `[shamir]`. | `~/repos/loom/kailash-py/src/kailash/trust/vault/__init__.py` (lines 1–37, exports surface), `~/repos/loom/kailash-py/src/kailash/trust/vault/shamir.py` (lines 1–536, full wrapper), `~/repos/loom/kailash-py/src/kailash/trust/vault/backup.py` (lines 1–96, gated stub) |

### 2.2 Disposition: which of (a)/(b)/(c) is the upstream state

**Disposition: (b) — wrapper around the audited third-party `shamir-mnemonic` Python package.**

Evidence quoted verbatim from `~/repos/loom/kailash-py/src/kailash/trust/vault/shamir.py`:

- Module docstring lines 5–9: "This module wraps the audited reference implementation `shamir-mnemonic` (SLIP-0039 by SatoshiLabs) to expose an ergonomic `ShamirRitual` surface for splitting and reconstructing Trust Vault key material."
- Lines 22–26: optional extra contract — "Install via: `pip install kailash[shamir]`"
- Lines 122–136 (`_require_shamir_mnemonic`): lazy-import of `shamir_mnemonic` at call time; raises `RuntimeError` with install hint if extra absent (the "loud failure at call site" pattern).
- Line 184 (CHANGELOG): "**New optional extra `[shamir]`** in root `pyproject.toml` pinning `shamir-mnemonic>=0.3` (latest published: 0.3.0). Install via `pip install kailash[shamir]`."
- Lines 281–290 (`generate` body): wraps `shamir_mnemonic.generate_mnemonics(group_threshold=1, groups=[(threshold, total)], master_secret=..., passphrase=...)`.
- Lines 388–392 (`reconstruct` body): wraps `shamir_mnemonic.combine_mnemonics(mnemonics, passphrase=...)`.

Disposition (a) — full Shamir integration with no third-party dep — is FALSE: the upstream module is a wrapper, not a re-implementation.

Disposition (c) — docs only / no executable code — is FALSE: `generate`, `reconstruct`, `serialize_shard`, `deserialize_shard`, `rotate_holders` are all functional in v2.11.0; CHANGELOG line 185 cites "`tests/integration/trust/test_shamir_round_trip.py` (7 cases against real `shamir-mnemonic`)" as Tier 2 evidence the wrapper executes.

**Important sub-finding — `back_up_vault_key` stub.** `~/repos/loom/kailash-py/src/kailash/trust/vault/backup.py` (lines 91–95):

```python
raise NotImplementedError(
    "back_up_vault_key: Trust Vault Shamir binding awaits mint ISS-37 "
    "(see issue #606). The SLIP-0039 wrapper is available today via "
    "kailash.trust.vault.shamir.generate(...) for direct callers."
)
```

The `back_up_vault_key` HIGH-LEVEL binding (which would have resolved a Trust Vault key by id, called `shamir.generate`, and written an audit anchor) is gated on mint ISS-37. Per `~/repos/loom/kailash-py/src/kailash/trust/vault/backup.py` lines 17–20, this is "the ONE permitted stub per `rules/zero-tolerance.md` Rule 2 (issue-linked, gate documented)". For Phase 01, **Envoy uses `kailash.trust.vault.shamir.generate(...)` directly** with the master key bytes pulled via the `export_master_key_for_shamir()` hook on `TrustStoreAdapter` (shard 5, §3.1 hook 6). The high-level `back_up_vault_key` is NOT used — Envoy's own binding logic substitutes for it, threading the master key in directly.

### 2.3 Crypto-audit caveat — security-relevant

Per `~/repos/loom/kailash-py/src/kailash/trust/vault/shamir.py` lines 36–43 (verbatim):

> The reference implementation is **not constant-time** and is documented by its authors as suitable for correctness verification rather than handling of high-value secrets in adversarial settings. Trust Vault deployments that need side-channel resistance MUST evaluate hardened alternatives before production use; the wrapper exists today to (1) freeze the SLIP-0039 API surface so downstream callers can compile against it and (2) enable the end-to-end ritual rehearsal.

`specs/shamir-recovery.md` line 15 already mandates "Phase 00 crypto audit required" and line 54 lists `CryptoLibAuditMissingError` ("Phase 00 crypto audit not landed for selected SLIP-0039 implementation"; "Block recovery feature in production; complete audit before ship"; "Never (release gate)"). The kailash-py wrapper docstring is consistent with the spec — the audit gate stays a Phase 01 release gate. This is logged as a release-gate concern in §7.1 (LOW spec ambiguity — does "Phase 00 crypto audit" refer to `shamir-mnemonic` upstream OR to the kailash-py wrapper specifically?).

### 2.4 Indirectly-relevant closures (per `03-kailash-py-mvp-readiness.md` § 2.2)

- `#604` (algorithm-identifier schema, closed 2026-04-25) — `GenesisRecord.shard_public_commitments` is an `[algo:hash]` array (`specs/trust-lineage.md` line 27 schema example: `"shamir": "slip39"` in `algorithm_identifier`); the `coerce_algorithm_id` helper (`kailash.trust.signing.algorithm_id`) is the canonical wire-shape gate. Envoy must thread `AlgorithmIdentifier()` through every Shamir-related signed record, identical to the Trust Store contract (shard 5 §3.4).
- `#757` / `#756` (Unicode byte vector pinning for canonical-input + canonical-JSON, closed 2026-04-30) — relevant for `serialize_for_signing()` of `ShardPublicCommitment` records (which name a hash value alongside the algorithm). Cross-SDK byte-identity for shard commitments depends on this.

---

## 3. Envoy-new-code surface

Per the disposition (b) finding above, the Envoy-new-code surface for shard 15 is:

**Wrapper-call glue + paper-shard renderer + ritual coordinator + commitment binding to Genesis + reconstruction CLI + plain-language error renderer.**

Concrete surface (5 modules, each scoped to a single responsibility):

### 3.1 `envoy.shamir.ritual` — ritual coordinator (Boundary-Conversation-driven)

A coordinator class that orchestrates the 5-step Phase 01 backup ritual:

1. Read master-key bytes via `TrustStoreAdapter.export_master_key_for_shamir()` (shard 5 §3.1 hook 6).
2. Call `kailash.trust.vault.shamir.generate(secret=master_key, ritual=ShamirRitual(threshold=3, total_shards=5))`.
3. Compute `shard_public_commitments = [f"sha256:{sha256(serialize_shard(s)).hexdigest()}" for s in shards]`. Bind these to the user's Genesis Record (per `specs/trust-lineage.md` line 27 + `specs/shamir-recovery.md` § Shard public commitments).
4. Render each shard via `envoy.shamir.paper.render(shard, slot_label)` for human transcription.
5. Persist the `DistributionChecklist` with **opaque slot labels only** to Trust Vault — NOT real holder names — per `specs/shamir-recovery.md` § Card format (H-06 fix).
6. **Zeroize** the in-memory master-key reference per `~/repos/loom/kailash-py/src/kailash/trust/vault/shamir.py` lines 348–362 ("callers MUST `del` the returned bytes immediately after use").

Boundary-Conversation pause-for-backup hook (EC-5 acceptance gate (b)): the ritual coordinator is invoked from Boundary Conversation step S8 (per `specs/shamir-recovery.md` cross-references line 61: "specs/boundary-conversation.md — S8 ritual step"). The coordinator MUST run AT LEAST ONCE during the first-time-user Boundary Conversation. Failure to fire is BLOCKED at EC-5 acceptance.

### 3.2 `envoy.shamir.paper` — paper-shard format renderer (humans transcribe from cards)

Renders a SLIP-0039 shard (`List[str]` of dictionary words) into a human-usable paper-card format. Per `specs/shamir-recovery.md` § Card format (line 29):

- 24 BIP-39 words (NB: SLIP-0039 uses a SLIP-0039-specific 1024-word dictionary that overlaps but is NOT identical to BIP-39's 2048-word list; spec terminology "BIP-39 words" appears to be loose — see §7.2 spec ambiguity).
- Trezor-compatible (the `shamir-mnemonic` wrapper produces the canonical SLIP-0039 mnemonic which Trezor models accept).
- NO "Envoy" label; NO name on card. Opaque slot label only.
- Per-card checksum validation at entry (the underlying SLIP-0039 mnemonic carries its own checksum; the L-03 fix is to surface checksum failures per-card at entry time, not deferred to combine-time).

The renderer outputs:

- **Plain-text card** — slot label, threshold reminder ("3 of 5"), mnemonic (24 words in 4 rows of 6 for transcription accuracy), per-card checksum cue (last word as visual checksum), card sequence number (1 of 5, 2 of 5, ...).
- **Paper-print PDF** (Phase 01 stretch — `reportlab` or `pypdf`; if PDF generation slips Phase 01 budget, the plain-text + manual-print path satisfies EC-5 acceptance gate (b) sufficiently).

Per `rules/communication.md` § "Plain Language Communication", the card text MUST be plain language: "Card 1 of 5 — keep this somewhere safe. You will need any 3 of these 5 cards to recover your Envoy keys if your computer is lost." NOT "SLIP-0039 mnemonic shard, threshold=3, total=5".

### 3.3 `envoy.shamir.reconstruct` — reconstruction CLI + plain-language error renderer

A CLI subcommand `envoy shamir recover` that:

1. Prompts the user to enter words from any 3 cards (the SLIP-0039 mnemonic-entry surface).
2. Validates per-card SLIP-0039 checksum at entry (the underlying `shamir_mnemonic.combine_mnemonics` will surface `MnemonicError` on checksum failure; Envoy MUST surface this PER-CARD at entry, not deferred to combine-time — the L-03 fix from `specs/shamir-recovery.md` § Recovery flow line 33).
3. Calls `kailash.trust.vault.shamir.reconstruct(shards, passphrase=...)`.
4. Verifies the reconstructed master key against `Genesis.shard_public_commitments` (per `specs/shamir-recovery.md` § Shard public commitments + `specs/trust-lineage.md` § Schema GenesisRecord line 27). Mismatch raises `CommitmentVerificationFailedError` per `specs/shamir-recovery.md` error taxonomy (line 49: "Refuse unlock; investigate counterfeit-shard or social-engineering attack"; "Never (security event)").
5. Calls `TrustStoreAdapter.import_master_key_from_shamir(reconstructed)` to seal the recovered key into a fresh Trust Vault.
6. Triggers Connection Vault re-pair flow (per `specs/shamir-recovery.md` cross-references line 62 — "Connection Vault not Shamir-covered" — meaning third-party API tokens are NOT recovered; user re-authorizes channel adapters fresh).

**Plain-language error renderer (EC-5 acceptance gate (d)):** every error in `specs/shamir-recovery.md` § Error taxonomy (lines 45–55) gets a plain-language string per `rules/communication.md`. Example mapping:

| Typed error                         | Plain-language render                                                                                                                                                                                                                                                                |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `InsufficientSharesError`           | "You need at least 3 cards to recover. You entered N. Please find the missing cards and try again."                                                                                                                                                                                  |
| `ShardChecksumFailedError`          | "The words on Card N don't quite match. Did you transcribe them correctly? The last word is a checksum — if that one is right, the others usually are. Try re-entering this card carefully."                                                                                         |
| `CommitmentVerificationFailedError` | "The cards you entered are valid SLIP-0039 cards, but they don't match this Envoy install's expected fingerprint. This may mean the cards belong to a different Envoy install — or that someone has tampered with them. Recovery is refused. Contact support if this is unexpected." |
| `RecoveryRateLimitedError`          | "You've tried recovery too many times in a short window. Please wait N minutes and try again. (This is to protect your keys from someone in your household trying many guesses.)"                                                                                                    |
| `ShardSlotLabelMismatchError`       | "The card you entered has slot label X, but I'm expecting slot label Y for this position. Did you grab the wrong card? Check the label on the back."                                                                                                                                 |
| `RotationGracePeriodElapsedError`   | "Card N is from a previous backup ritual. The 30-day grace period after rotation has passed. Please use a card from your current set of 5."                                                                                                                                          |
| `EnvoyLabelOnCardWarning`           | "This card has an 'Envoy' or person's name on it. For your safety, please re-print the card without these labels — anyone who finds the card should NOT be able to identify what it's for."                                                                                          |
| `CryptoLibAuditMissingError`        | (release gate, never user-surfaced in production)                                                                                                                                                                                                                                    |
| `ShardPublicCommitmentMissingError` | "This Envoy install was created before the current safety check was added. Please run `envoy shamir migrate` to upgrade — you may need to re-shard your backup cards."                                                                                                               |

Per `rules/communication.md` MUST NOT: never surface raw `MnemonicError` traceback; never surface byte-level dump; never surface "SLIP-0039 spec line N" reference.

### 3.4 `envoy.shamir.commitments` — Genesis-Record commitment binding

Computes `shard_public_commitments` per `specs/shamir-recovery.md` § Shard public commitments + `specs/trust-lineage.md` § Schema GenesisRecord (line 27 — `"shamir_threshold": {"m_of_n": [3,5], "shard_public_commitments": [<algo:hash>]}`).

Contract:

- For each shard `s` produced by `kailash.trust.vault.shamir.generate(...)`, compute `commitment = f"sha256:{sha256(serialize_shard(s)).hexdigest()}"`.
- The commitment is **public**: it can be stored in plaintext alongside the Genesis Record without revealing the shard. This is exactly the property the spec relies on (line 41: "for recovery verification without shard exposure").
- At reconstruct time, after `shamir.reconstruct(...)` returns the secret, the reconstructor MUST also receive the original 3 shards used; recompute their commitments; verify each commitment is present in `Genesis.shard_public_commitments`. Mismatch → `CommitmentVerificationFailedError` per spec line 49.
- Algorithm identifier: per `kailash.trust.signing.algorithm_id` (#604 closure) + `specs/trust-lineage.md` line 24 (`"algorithm_identifier": {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}`), the commitment array's algorithm is `slip39+sha256` until mint ISS-31 finalizes the canonical form. Same scaffold pattern as Trust Store (shard 5 §3.4).

This is the structural defense against counterfeit-shard attacks (T-006 social-graph manipulation per `specs/threat-model.md`): an attacker who obtained 3 shards from a different SLIP-0039 set CANNOT unlock the user's Trust Vault even if they correctly reconstruct _some_ secret — because the commitment in the user's Genesis won't match.

### 3.5 `envoy.shamir.distribution_checklist` — opaque-slot-label persistence

Per `specs/shamir-recovery.md` § Card format (line 29): "Distribution checklist persists only opaque slot labels in Trust Vault; real names optional + in hidden envelope (Phase 04) only (H-06 fix)."

The checklist is a `dataclass` written into the Trust Vault `ritual state` region (per `specs/trust-vault.md` § File format line 15: "encrypted regions (envelope / posture / Shamir commitments / **ritual state** / chain head / enterprise cache / first-time fingerprints / hidden envelope)"). Schema:

```python
@dataclass(frozen=True)
class DistributionChecklist:
    ritual_id: str                    # sha256 of the (threshold, total, created_at) tuple
    threshold: int                    # 3 (default)
    total_shards: int                 # 5 (default)
    slot_labels: list[str]            # ["slot-1", "slot-2", "slot-3", "slot-4", "slot-5"] — OPAQUE
    created_at: datetime              # ritual creation timestamp
    rotation_history: list[str]       # ritual_ids of prior rituals; 30-day grace tracking
    # NO holder names, NO "Envoy" label, NO contact info — those live in Phase 04 hidden envelope only
```

Phase 04 hidden envelope (per `specs/trust-vault.md` § Hidden envelope) is where real holder names + contact info MAY be stored if the user opts in — Phase 01 has the field shape but does NOT populate it.

---

## 4. Class structure sketch (interfaces only)

Pseudocode sketch, not implementation. Per the per-shard structure (`01-shard-plan.md` §2 step 4): "Sketch the primitive's class structure (interfaces, not implementation)."

```python
# envoy/shamir/__init__.py — public surface
from envoy.shamir.ritual import ShamirRitualCoordinator, RitualResult
from envoy.shamir.paper import PaperShardRenderer, PaperShardCard
from envoy.shamir.reconstruct import ShamirReconstructor, ReconstructionResult
from envoy.shamir.commitments import compute_commitment, verify_commitment
from envoy.shamir.distribution_checklist import DistributionChecklist
from envoy.shamir.errors import (
    InsufficientSharesError,
    ShardChecksumFailedError,
    CommitmentVerificationFailedError,
    RecoveryRateLimitedError,
    ShardSlotLabelMismatchError,
    RotationGracePeriodElapsedError,
    EnvoyLabelOnCardWarning,
    CryptoLibAuditMissingError,
    ShardPublicCommitmentMissingError,
)

# envoy/shamir/ritual.py
from kailash.trust.vault.shamir import ShamirRitual, generate, rotate_holders
from envoy.trust.store import TrustStoreAdapter

class ShamirRitualCoordinator:
    """Orchestrate the Boundary-Conversation-pause-for-backup ritual.

    Reads master-key from TrustStoreAdapter; splits via kailash.trust.vault.shamir;
    binds shard_public_commitments to Genesis; renders paper cards; persists
    opaque-slot-label DistributionChecklist; zeroizes master-key reference.
    """

    def __init__(
        self,
        trust_store: TrustStoreAdapter,
        renderer: "PaperShardRenderer",
        principal_id: str,
    ) -> None: ...

    async def run_first_time_ritual(
        self,
        threshold: int = 3,
        total_shards: int = 5,
        passphrase: bytes = b"",
    ) -> RitualResult: ...
    # Returns RitualResult{ritual_id, paper_cards: list[PaperShardCard],
    #                      commitments: list[str], checklist: DistributionChecklist}

    async def run_rotation_ritual(
        self,
        old_shards: list[list[str]],
        new_threshold: int,
        new_total: int,
        passphrase: bytes = b"",
    ) -> RitualResult:
        """Per specs/shamir-recovery.md § Rotation ritual.

        Old 4 non-rotated cards remain valid for 30-day grace period via
        DistributionChecklist.rotation_history; after grace, RotationGracePeriodElapsedError.
        """
        ...

# envoy/shamir/paper.py
from kailash.trust.vault.shamir import serialize_shard

@dataclass(frozen=True)
class PaperShardCard:
    slot_label: str          # "slot-1" — opaque per H-06
    sequence: tuple[int, int]  # (1, 5) for "Card 1 of 5"
    threshold_reminder: str  # "Any 3 of these 5 cards recovers your keys"
    mnemonic_words: list[str]  # 24 SLIP-0039 dictionary words
    transcription_layout: str  # 4 rows × 6 words for human transcription accuracy

class PaperShardRenderer:
    def render(
        self, shard: list[str], slot_label: str, sequence: tuple[int, int]
    ) -> PaperShardCard: ...

    def render_text(self, card: PaperShardCard) -> str:
        """Plain-text card body for terminal/print/copy-paste."""
        ...

    def render_pdf(self, cards: list[PaperShardCard]) -> bytes:
        """Phase 01 stretch — defer to text if PDF deps slip budget."""
        ...

# envoy/shamir/reconstruct.py
from kailash.trust.vault.shamir import reconstruct as _shamir_reconstruct

class ShamirReconstructor:
    """CLI-driven recovery flow with plain-language error rendering."""

    def __init__(
        self,
        genesis_commitments: list[str],
        rate_limiter: "RecoveryRateLimiter",
    ) -> None: ...

    async def reconstruct_with_user_input(
        self,
        prompt_fn: Callable[[int], str],   # injectable for CLI / channel-adapter use
        passphrase: bytes = b"",
    ) -> ReconstructionResult:
        """Prompt user for 3 cards, validate per-card checksum at entry,
        reconstruct, verify commitments, return secret bytes (caller MUST del).
        """
        ...

    def render_error_plain_language(self, err: Exception) -> str:
        """Map any error from § Error taxonomy to plain-language string per
        rules/communication.md MUST."""
        ...

# envoy/shamir/commitments.py
def compute_commitment(shard: list[str]) -> str:
    """Returns 'sha256:<hex>' for the shard. Public; no shard exposure."""
    ...

def verify_commitment(shard: list[str], commitments: list[str]) -> bool:
    """True iff sha256(serialize_shard(shard)) in commitments. Used at
    reconstruct-time as defense against counterfeit shards (T-006)."""
    ...

# envoy/shamir/errors.py
# All 9 errors from specs/shamir-recovery.md § Error taxonomy.
# Each carries a plain-language attribute used by ShamirReconstructor.render_error_plain_language.
```

This sketch is interfaces only; implementation is shard-out-of-scope.

---

## 5. Integration points

The Shamir primitive is a leaf primitive in the Phase 01 dep graph (no downstream Phase 01 primitives depend on it — it gates EC-5 acceptance directly, not via downstream consumption). Inbound dependencies and one explicit non-dependency:

| Neighboring primitive (shard)                | Hook                                                                                                                                                                                                        | Direction         | Spec citation                                                                                                        |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------- |
| Trust Store + Lineage (5)                    | `export_master_key_for_shamir() -> bytes` + `import_master_key_from_shamir(bytes)` per shard 5 §3.1 hook 6                                                                                                  | TS ↔ Shamir       | `specs/shamir-recovery.md` cross-ref → `specs/trust-vault.md`; shard 5 §3.1.6                                        |
| Trust Store + Lineage (5)                    | `Genesis.shard_public_commitments: list[<algo:hash>]` written at ritual time; read at reconstruct time                                                                                                      | TS ↔ Shamir       | `specs/trust-lineage.md` § Schema GenesisRecord line 27                                                              |
| Boundary Conversation (8)                    | `ShamirRitualCoordinator.run_first_time_ritual(...)` invoked at S8 step (EC-5 acceptance gate (b): "Boundary Conversation pauses for the backup ritual at least once")                                      | BC → Shamir       | `specs/shamir-recovery.md` cross-references line 61 + `02-mvp-objectives.md` EC-5                                    |
| Channel Adapters (16)                        | Recovery prompt surface — `envoy shamir recover` runs from any of CLI/Web/6 messaging channels per EC-7. Each adapter renders the 3-card prompt sequence + plain-language errors via `ShamirReconstructor`. | Adapters → Shamir | EC-7 (`02-mvp-objectives.md` lines 96–104) + `rules/communication.md`                                                |
| pipx Distribution (19)                       | `pyproject.toml::[shamir]` extra MUST be a default install for `envoy-agent` — Shamir recovery is a Phase 01 ship-blocker so the optional extra is non-optional in the Envoy distribution manifest          | Dist → Shamir     | `~/repos/loom/kailash-py/CHANGELOG.md` line 184; `02-mvp-objectives.md` EC-5                                         |
| **Connection Vault (14)** — **NOT involved** | **Master key is NEVER stored in OS keychain (Connection Vault). Master key lives in Trust Vault only, behind Argon2id + Secure-Enclave-bound XOR (`specs/trust-vault.md` § Encryption line 20)**            | NOT a hook        | `specs/trust-vault.md` line 68 + `specs/shamir-recovery.md` cross-ref line 62: "Connection Vault not Shamir-covered" |

Per `rules/orphan-detection.md` Rule 1 ("Every `db.*` / `app.*` Facade Has a Production Call Site"), each Shamir module enumerated in §3 MUST have at least one production call site in the Envoy hot path within 5 commits of the facade landing — no method may be exposed without a hot-path consumer. The integration-point table above pre-declares the required call sites.

Per `rules/facade-manager-detection.md` Rule 1 ("Every Manager-Shape Class Has a Tier 2 Test"), `ShamirRitualCoordinator` is a `*Coordinator`-shape class; `PaperShardRenderer` is a `*Renderer`-shape class; `ShamirReconstructor` is a `*Reconstructor`-shape class. All three MUST have at least one Tier 2 test that imports through the framework facade and asserts an externally-observable effect (a paper card actually rendered, a reconstruction round-trip actually succeeding against real `shamir-mnemonic`, a `CommitmentVerificationFailedError` actually surfacing on a counterfeit shard).

Per `rules/orphan-detection.md` Rule 2a ("Crypto-Pair Round-Trip MUST Be Tested Through The Facade"), the `generate / reconstruct` pair (and `serialize_shard / deserialize_shard`, and `compute_commitment / verify_commitment`) MUST round-trip through the Envoy facade — not two unit tests with mocks of each other's halves. The Tier 2 round-trip is the structural defense against the "encrypt uses GCM, decrypt uses CBC" failure pattern at the Shamir scale.

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/testing.md` § "Tier 2 (Integration): Real infrastructure recommended" — real `shamir-mnemonic` package, real Trust Vault SQLite + Argon2id, NO mocking. Phase 01 EC-5 directly requires Shamir integration tests.

### 6.1 Tier 2 — real infrastructure (no mocking; `shamir-mnemonic` and SQLite real)

| Test                                                          | Asserts                                                                                                                                                                                                                                                  | Spec source                                                                                           |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `test_shamir_3_of_5_all_10_combinations.py`                   | **Generate 5 shards from a fixed test secret; for ALL C(5,3)=10 distinct 3-shard combinations, reconstruct produces the SAME secret bytes.** Exhaustive — 10 combos, not "most" or "spot-check." Per `rules/zero-tolerance.md` Rule 6 (implement fully). | `02-mvp-objectives.md` EC-5 acceptance gate (a) line 78                                               |
| `test_shamir_2_of_3_threshold_configurable.py`                | User-configurable threshold 2-of-3 (lower bound) reconstructs from any 2 of 3 shards (C(3,2)=3 combos)                                                                                                                                                   | `specs/shamir-recovery.md` § Default threshold line 19                                                |
| `test_shamir_5_of_9_threshold_configurable.py`                | User-configurable threshold 5-of-9 (upper bound) reconstructs from C(9,5)=126 sampled combos (full exhaustion is property-test-grade — sample at least 10 distinct 5-subsets to validate the threshold contract holds at the upper end)                  | `specs/shamir-recovery.md` § Default threshold line 19                                                |
| `test_shamir_paper_shard_serialize_deserialize_round_trip.py` | `serialize_shard(deserialize_shard(s)) == s` for valid shards; whitespace tolerance per `kailash.trust.vault.shamir.deserialize_shard` line 440 ("any run of ASCII whitespace is treated as a word separator")                                           | `~/repos/loom/kailash-py/src/kailash/trust/vault/shamir.py` lines 402–456                             |
| `test_shamir_per_card_checksum_l03.py`                        | Per-card SLIP-0039 checksum failure surfaces at entry time as `ShardChecksumFailedError`, NOT deferred to combine-time (L-03 fix per `specs/shamir-recovery.md` § Recovery flow line 33)                                                                 | `specs/shamir-recovery.md` line 33 + error taxonomy line 48                                           |
| `test_shamir_commitment_verify_defeats_counterfeit.py`        | An attacker presents 3 valid SLIP-0039 shards from a DIFFERENT secret — reconstruction succeeds (the SLIP-0039 math doesn't know any better) BUT commitment verification raises `CommitmentVerificationFailedError`. Vault unlock is refused.            | `specs/shamir-recovery.md` § Shard public commitments line 41 + error taxonomy line 49 + threat T-006 |
| `test_shamir_envoy_label_on_card_warning_h06.py`              | A user-supplied card carrying "Envoy" or a name in non-mnemonic position triggers `EnvoyLabelOnCardWarning`; recovery still proceeds but UX advisory fires                                                                                               | `specs/shamir-recovery.md` § Card format line 29 + error taxonomy line 53 (H-06)                      |
| `test_shamir_distribution_checklist_opaque_labels.py`         | After ritual, `DistributionChecklist` persisted to Trust Vault contains ONLY opaque slot labels ("slot-1" etc.); NO "Envoy" string in the persisted bytes; NO real names                                                                                 | `specs/shamir-recovery.md` § Card format line 29 (H-06 fix) + spec line 73 test reference             |
| `test_shamir_rotation_30_day_grace.py`                        | Pre-rotation card presented within 30 days post-rotation → reconstruct succeeds with 3 valid old cards; pre-rotation card presented at day 31+ → `RotationGracePeriodElapsedError`                                                                       | `specs/shamir-recovery.md` § Rotation ritual line 37 + error taxonomy line 52                         |
| `test_shamir_master_key_round_trip_through_trust_store.py`    | `TrustStoreAdapter.export_master_key_for_shamir()` → `shamir.generate(...)` → `shamir.reconstruct(...)` → `TrustStoreAdapter.import_master_key_from_shamir(...)` → vault re-unlocks with same passphrase                                                 | shard 5 §3.1 hook 6 + EC-5 acceptance gate (a)                                                        |
| `test_shamir_genesis_commitments_threading.py`                | `Genesis.shard_public_commitments` is populated at ritual time with `[f"sha256:{hex}" for ...]`; reconstruct verifies against this list; algorithm_identifier carries `slip39+sha256` per #604 scaffold                                                  | `specs/trust-lineage.md` § Schema GenesisRecord line 27 + `kailash.trust.signing.algorithm_id`        |
| `test_shamir_ritual_fires_during_boundary_conversation.py`    | A first-time-user Boundary Conversation that completes envelope authoring MUST trigger `ShamirRitualCoordinator.run_first_time_ritual` AT LEAST ONCE before exit. EC-5 gate (b).                                                                         | `02-mvp-objectives.md` EC-5 line 79                                                                   |
| `test_shamir_recovery_rate_limit_t002.py`                     | Repeated recovery attempts exceeding rate ceiling raise `RecoveryRateLimitedError`; window expiry permits re-attempt; defense against T-002 household-adversarial guess attempts                                                                         | `specs/shamir-recovery.md` § Error taxonomy line 50 + threat T-002                                    |
| `test_shamir_plain_language_error_rendering.py`               | For each of 9 error types in § Error taxonomy, `ShamirReconstructor.render_error_plain_language(err)` produces a string with NO byte-dump, NO traceback, NO "SLIP-0039" jargon. EC-5 gate (d).                                                           | `02-mvp-objectives.md` EC-5 line 80 + `rules/communication.md` MUST NOT (raw error messages)          |

### 6.2 Tier 3 — cross-tool interop + cross-OS portability + full ritual

| Test                                                           | Asserts                                                                                                                                                                                                                                                                                       | EC tested |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `test_shamir_cross_tool_reconstruct_python_shamir_mnemonic.py` | An Envoy-generated shard set, fed directly to a NEW Python process that imports `shamir_mnemonic` (NOT `kailash.trust.vault.shamir` — bypass the Envoy wrapper layer entirely) and calls `shamir_mnemonic.combine_mnemonics(...)`, reconstructs the same secret bytes. EC-5 gate (c) minimum. | EC-5      |
| `test_shamir_cross_tool_reconstruct_trezor_sdk.py`             | (If Trezor hardware/SDK accessible in CI) An Envoy-generated shard set is accepted by the Trezor reference SLIP-0039 implementation. EC-5 gate (c) "ideally Trezor SDK if accessible."                                                                                                        | EC-5      |
| `test_shamir_cross_os_paper_card_portability.py` (BET-9b)      | Shards generated on macOS reconstruct correctly on Linux + Windows AND vice versa. The paper-shard format is byte-identical across OS (mnemonic words are dictionary entries — no OS-specific encoding hazards). Per `rules/testing.md` Tier 3 cross-implementation logic.                    | EC-5      |
| `test_shamir_full_ritual_via_boundary_conversation.py`         | End-to-end: spawn a real Boundary Conversation; complete envelope authoring; observe ritual fire; capture rendered paper cards from CLI output; spawn a fresh process; recover via 3 of 5 shards; verify Trust Vault unlocks with same key material.                                          | EC-5      |
| `test_shamir_post_recovery_connection_vault_repair.py`         | After successful Shamir recovery, the Connection Vault is empty (Connection Vault NOT Shamir-covered per spec line 62). User MUST re-pair channel adapters fresh. Re-pair flow proceeds without error.                                                                                        | EC-5      |

### 6.3 Wiring tests (orphan-detection + facade-manager-detection + crypto-pair round-trip)

Per `rules/facade-manager-detection.md` Rule 2 (test file naming convention) + Rule 3 (constructor receives parent framework instance):

- Test files MUST be named `test_<lowercase_class_name>_wiring.py` for grep-detectability:
  - `test_shamir_ritual_coordinator_wiring.py`
  - `test_paper_shard_renderer_wiring.py`
  - `test_shamir_reconstructor_wiring.py`
- Constructors MUST receive explicit dependencies (no global lookups, no self-construction of `TrustStoreAdapter` / `ShamirRitual`).

Per `rules/orphan-detection.md` Rule 2a (Crypto-Pair Round-Trip):

- `generate / reconstruct` — round-trip through the Envoy `ShamirRitualCoordinator` + `ShamirReconstructor` facade in `test_shamir_3_of_5_all_10_combinations.py`. NOT two unit tests mocking each other.
- `serialize_shard / deserialize_shard` — round-trip in `test_shamir_paper_shard_serialize_deserialize_round_trip.py`.
- `compute_commitment / verify_commitment` — round-trip in `test_shamir_commitment_verify_defeats_counterfeit.py`.

Per `rules/zero-tolerance.md` Rule 6 ("Implement Fully"): the all-10-combo test is non-negotiable. "Most combos work" or "happy-path only" is BLOCKED at EC-5.

---

## 7. Frozen-spec ambiguity surfaced during analysis

Per `01-shard-plan.md` § 4 ("Failure modes + mitigations"), HIGH-severity spec ambiguity escalates via the failure-mode protocol — STOP the deep-dive, convene MUST-Rule-5b sweep, edit spec under full-sibling redteam economics. Lower-severity ambiguity is logged here but does not block the shard.

### 7.1 LOW — "Phase 00 crypto audit" scope ambiguity

`specs/shamir-recovery.md` § Algorithm line 15 ("Phase 00 crypto audit required") + § Error taxonomy line 54 (`CryptoLibAuditMissingError`: "Phase 00 crypto audit not landed for selected SLIP-0039 implementation"; "Block recovery feature in production; complete audit before ship"; "Never (release gate)").

The kailash-py wrapper docstring (lines 36–43) explicitly notes the upstream `shamir-mnemonic` reference implementation is "not constant-time" and "suitable for correctness verification rather than handling of high-value secrets in adversarial settings." The spec mandates "Phase 00 crypto audit"; the ambiguity is whether the audit applies to:

- (a) The `shamir-mnemonic` upstream package (one audit, durable across Envoy + any other consumer).
- (b) The kailash-py wrapper (`kailash.trust.vault.shamir`) — its lazy-import contract, its `ShamirRitual` validation, its memory-hygiene `del` discipline.
- (c) The Envoy-new-code surface (paper renderer, ritual coordinator, commitment binding).

**Disposition:** logged as a release-gate concern. Phase 01 release MUST have at least (a) + (c) audited. (b) inherits some assurance from kailash-py's own test suite (CHANGELOG line 185 cites 32 test cases) but the wrapper's freshness is 7 days at Phase 01 entry — an upstream audit on the wrapper is desirable but not strictly necessary if (a) is solid. Not a Phase 01 implementation blocker; surfaces at /redteam round 2 or /codify time.

### 7.2 LOW — "24 BIP-39 words" terminology in card format

`specs/shamir-recovery.md` § Card format line 29: "24 BIP-39 words; Trezor-compatible."

SLIP-0039 uses a SLIP-0039-specific 1024-word dictionary that is NOT identical to BIP-39's 2048-word list. Trezor models accept SLIP-0039 mnemonics directly (Trezor One firmware ≥1.9.0, Trezor Model T firmware ≥2.3.0). The "24 BIP-39 words" phrasing in the spec is loose — the actual format produced by `shamir-mnemonic` is "24 SLIP-0039 dictionary words" (the 256-bit secret encodes to 24 words at SLIP-0039's RS1024 share rate; differs from BIP-39's 24-word seed at 256-bit security).

The user-facing description should say "24 dictionary words" or "24 recovery words"; the technical spec should clarify SLIP-0039 dictionary, not BIP-39 dictionary.

**Disposition:** logged as a Phase 01 spec-clarity concern. Does not affect implementation correctness — `kailash.trust.vault.shamir` produces the canonical SLIP-0039 mnemonics regardless of how the spec describes them. Surface at /codify time as a spec polish item; do NOT trigger MUST-Rule-5b sweep for a wording clarification that doesn't change behavior.

### 7.3 LOW — `back_up_vault_key` gate uncertainty

`~/repos/loom/kailash-py/src/kailash/trust/vault/backup.py` lines 91–95: `back_up_vault_key` raises `NotImplementedError` "until mint ISS-37 stabilises the Trust Vault binding."

For Phase 01, Envoy bypasses this stub and calls `shamir.generate(...)` directly with master-key bytes pulled via `TrustStoreAdapter.export_master_key_for_shamir()`. The spec ambiguity: when mint ISS-37 lands, MUST Envoy migrate to use `back_up_vault_key`, OR is the direct-`generate` path the durable Phase 01+ pattern?

**Disposition:** logged for Phase 02 entry checklist. The direct-`generate` path is functionally complete for Phase 01. When ISS-37 lands, evaluate whether `back_up_vault_key` adds (a) audit-anchor writing per `rules/eatp.md` audit anchor contract (`backup.py` lines 32–37), or (b) clearance-envelope-validated key resolution (`backup.py` lines 27–31). If (a) is the only addition, Envoy can implement audit-anchor writing in `ShamirRitualCoordinator` directly without waiting on ISS-37. If (b) is meaningful, Envoy migrates to `back_up_vault_key` post-ISS-37.

### 7.4 None HIGH-severity surfaced

No HIGH-severity ambiguity surfaced during this shard. The Shamir recovery primitive is well-specified (Phase 00 v2 frozen with H-06 + L-03 + T-002 + T-006 fixes baked in), well-provisioned upstream (#606 closed 2026-04-26 with executable wrapper code in v2.11.0), and the Envoy-new-code surface is composition (ritual coordinator + paper renderer + reconstruction CLI + commitment binding) — not re-implementation.

---

## 8. Cross-references

- **Phase 01 brief:** `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`
- **Inheritance map:** `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md`
- **Sharding plan:** `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (shard 15 row) + § 5 (sequencing — Shamir is in Group B, depends on Trust store (Group A); gates EC-5 directly)
- **MVP objectives:** `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` EC-5 acceptance gate (lines 70–80; strongest sovereignty acceptance gate)
- **kailash-py readiness:** `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 12 (Shamir 3-of-5 recovery) + § 5 verification protocol
- **Trust Store implementation (shard 5):** `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 3.1 hook 6 (`export_master_key_for_shamir` / `import_master_key_from_shamir`)
- **Methodology bridge:** `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` + `journal/0002-DISCOVERY-upstream-readiness-improved.md`
- **Phase 00 survey item:** `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` item 26 (SLIP-0039 absent on 04-21 baseline)
- **Phase 00 reconciliation row:** `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` row 24
- **Phase 00 issue manifest:** `workspaces/phase-00-alignment/issues/manifest.md` ISS-37 (#606) + ISS-37-mint (#8)
- **Source specs (FROZEN — DO NOT EDIT):** `specs/shamir-recovery.md`, `specs/trust-vault.md`, `specs/trust-lineage.md`, `specs/boundary-conversation.md`, `specs/connection-vault.md`, `specs/threat-model.md`
- **Architecture decision:** ADR-0003 (sovereignty stack: SLIP-0039 + Shamir 3-of-5 default + paper-shard format) per `briefs/00-phase-01-mvp-scope.md`
- **Verified provider modules (read-only references):**
  - `~/repos/loom/kailash-py/src/kailash/trust/vault/__init__.py` (lines 1–37 — public exports)
  - `~/repos/loom/kailash-py/src/kailash/trust/vault/shamir.py` (lines 1–536 — `ShamirRitual`, `generate`, `reconstruct`, `serialize_shard`, `deserialize_shard`, `rotate_holders`, `_require_shamir_mnemonic` lazy-import contract)
  - `~/repos/loom/kailash-py/src/kailash/trust/vault/backup.py` (lines 1–96 — gated stub `back_up_vault_key` awaiting mint ISS-37)
- **Closed upstream issue verified:** terrene-foundation/kailash-py#606 (closed 2026-04-26; landed in `kailash 2.11.0` per `~/repos/loom/kailash-py/CHANGELOG.md` lines 176, 183–188)
- **Optional extra contract:** `pip install kailash[shamir]` pinning `shamir-mnemonic>=0.3` (CHANGELOG line 184)
- **Applicable rules:** `.claude/rules/orphan-detection.md` Rule 1 + Rule 2 + Rule 2a (crypto-pair round-trip), `.claude/rules/facade-manager-detection.md` Rule 1 + Rule 2 + Rule 3, `.claude/rules/zero-tolerance.md` Rule 4 (no SDK workarounds) + Rule 6 (implement fully — all 10 combos), `.claude/rules/communication.md` MUST + MUST NOT (plain-language errors), `.claude/rules/testing.md` § Tier 2 + § Tier 3 (real `shamir-mnemonic`, real SQLite, no mocking), `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget
