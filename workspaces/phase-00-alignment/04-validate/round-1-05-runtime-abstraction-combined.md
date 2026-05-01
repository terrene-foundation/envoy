# Round 1 Combined Review — doc 05 Runtime Abstraction

**Target:** `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/05-runtime-abstraction.md` (draft v1)
**Anchors (frozen):** doc 00 v3, doc 02 v3, doc 03 v2, doc 09 v3 (all `workspaces/phase-00-alignment/01-analysis/`)
**Date:** 2026-04-21
**Lens:** combined reviewer + adversarial (single pass)
**Verdict:** **Issues found — 17 findings (3 CRITICAL, 8 HIGH, 4 MED, 2 LOW).** Doc 05 v1 is structurally close to landing but has three load-bearing factual errors against the frozen anchors (ledger head-commitment attribution, Genesis/runtime key co-signing of rotation, Ledger entry reference shape) plus several adversarial surfaces that let a compromised runtime, Vault, or attacker convert a "migration" or "orphan resolve" into a capability-laundering path. Fixes are mostly additive clarifications against anchors already in hand — they do NOT require re-opening frozen docs.

---

## Summary Table

| #    | Severity | Area                               | Issue (one-liner)                                                                                                                                                                                                                                                                                                                                                                                          |
| ---- | -------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F-01 | CRITICAL | Cross-ref factual error            | §2.1 `ledger_head_commitment()` + §4.1 both call out "doc 03 §6.3" — but doc 03 §6.3 is the **Trust-Lineage** chain commitment (Genesis-signed). Ledger head commitment is doc 04, signed by runtime device key. Doc 05 conflates two distinct commitments.                                                                                                                                                |
| F-02 | CRITICAL | Rotation signing authority         | §4.1 rotation "dual-signed (old + new runtime keys)" — doc 09 T-050b/T-100 + doc 03 authority model require **Genesis co-signature** for a device-binding rotation; runtime-only dual-sign lets a compromised runtime rotate its own key with no user authority gate.                                                                                                                                      |
| F-03 | CRITICAL | Adversarial runtime switch         | §8.2 runtime switch flow lets the runtime itself write `RuntimeSwitchRecord` signed by user's Genesis key — but Genesis key is in the Trust Vault, not the runtime. The ceremony that unlocks Genesis for a switch is undefined; attacker-controlled runtime can trivially trigger it at first-unlock.                                                                                                     |
| F-04 | HIGH     | Abstract-interface incompleteness  | §2.1 omits primitives doc 02/03/04/09 expect: `content_trust_level` wrapping for LLM-context assembly (doc 02 §18), classifier registry resolution, Grant-Moment primitives, dialog-rendering attestation (T-018), tool-output sanitization (doc 02 §20).                                                                                                                                                  |
| F-05 | HIGH     | Envoy-conformance set wrong        | §5.7 E1–E7 — E3/E4 cite doc 03 §6.2 for cycle detection but doc 03 §6.2 is NOT cycle detection; §6.2 is envelope-version binding. Cascade BFS/DFS set-equality is doc 03 §5.2 (correct); cycle detection lives in doc 03 chain-verify §4. E-series cross-refs broken.                                                                                                                                      |
| F-06 | HIGH     | Binary-verification weakness       | §4.2 binary_hash is signed by the runtime's own device_key — self-attestation. doc 09 T-050b explicitly notes signing-key compromise defeats load-time verification. Doc 05 claims "binary poisoning defense" without acknowledging T-050b chained-dependency that doc 09 already documented.                                                                                                              |
| F-07 | HIGH     | Orphan-resolution attack surface   | §6.3 orphan resolve includes a **Retry** option for idempotent tools — but "idempotent per-tool flag" is in envelope Operational dimension, which an attacker who reached Phase A can have staged. The orphan resolution is a capability-replay surface. No nonce binding against re-execution.                                                                                                            |
| F-08 | HIGH     | Phase B signer-identity drift      | §6.2 Phase B signs with `runtime_device_key`, but doc 02 §17 re-read checkpoint (F-10 of doc 02 review) asks who signs HALTED-by-rollback records. Doc 05 says §4.1 bullet "HALTED-by-rollback Ledger entries"; but the Phase B record is per-intent, and HALTED covers Phase A that never got Phase B — two different flows conflated.                                                                    |
| F-09 | HIGH     | Vault compatibility bypass         | §8.2 step 2 "algorithm_identifier match required" — but Trust Vault carries MANY signed artifacts (Genesis, Delegations, envelope edits, ReasoningCommits, Phase A/B, head-commitments). Does a single `algorithm_identifier` match cover all? Attacker can exploit per-artifact-type drift if check is not per-type.                                                                                      |
| F-10 | HIGH     | Security-review gates missing      | §9.2–§9.5 gates name deliverables but do NOT name the security-review agents (security-reviewer, gold-standards-validator, reviewer per `rules/agents.md`). Gates without named agents are "recommended" that get skipped.                                                                                                                                                                                 |
| F-11 | HIGH     | Runtime identity conflation        | §2.2 `RuntimeIdentity` = `{runtime_family, version, device_bound_pubkey_hex, algorithm_identifier}` — no `binary_hash`. §4.2 RuntimeAttestation DOES include binary_hash. Runtime identity without binary_hash lets a poisoned binary report the same identity as the legitimate one; §2.1 `runtime_identity()` is the check point.                                                                        |
| F-12 | MEDIUM   | Re-read checkpoint vs N2 alignment | §7 claims "invalidated per doc 02 §14 N2 conformance (envelope version bump, role override, etc.)" — doc 02 §14.6 is classifier registry, N2 is the envelope-cache 5-property invalidation. Section number cited (§14) is imprecise; should be §14.5 or explicit N2 cross-ref.                                                                                                                             |
| F-13 | MEDIUM   | Two-phase signing key plumbing     | §6.1 step 3: Phase A signed with `delegation_private_key` + runtime-device-signature. The delegation_private_key is owned by the PRINCIPAL (per doc 03), not the runtime. How does the runtime obtain the private key for signing every tool-call? Unlock ritual? Secure-enclave unwrap? Undefined.                                                                                                        |
| F-14 | MEDIUM   | Orphan-window policy               | §6.3 "default 30 days" orphan window — on a device that went offline for 45 days, all stale orphans fall out of detection. §13 Q-2 flags this but does not resolve; 30 days is a load-bearing default that an attacker can game by inducing a 31-day offline gap.                                                                                                                                          |
| F-15 | MEDIUM   | Algorithm downgrade path           | §10.3 "downgrade refuses if new runtime can't read new records" — but §4.2 claims binary_hash + algorithm_identifier both checked at startup. What if a downgrade runtime's algorithm_identifier is a proper SUBSET? Can the attacker force a downgrade by staging Ledger entries the older runtime can't read, then claiming incompatibility?                                                             |
| F-16 | LOW      | Independence rule posture          | §1 "Apache 2.0, Foundation-owned" for `kailash-runtime` crate — correct, but §4.2 RuntimeAttestation mentions "Foundation-signed manifest" which collides with independence.md if not carefully framed; the manifest is the Foundation-operated distribution manifest for binary hashes, not the SDK source IP.                                                                                            |
| F-17 | LOW      | Type-def completeness              | §2.2 lists 6 Types but §2.1 references 15+ dataclasses (ToolCallIntent, ToolCallOutcome, EnvelopeCheckResult, DelegationRecord, TrustLineageChain, EnvelopeConfig, EffectiveEnvelopeSnapshot, SessionObservedState, BudgetReservation, BudgetSnapshot, ClassifierResult, EnsembleResult, VelocityCheckResult, LedgerEntry, LedgerQuery, ChainVerificationResult). Most cross-refs but none-local-grounded. |

---

## Detail

### F-01 — CRITICAL — Ledger head-commitment attribution conflates doc 03 §6.3 with doc 04

**Issue:** Doc 05 §2.1 exposes `ledger_head_commitment()` as a runtime-level operation. Doc 05 §4.1 describes runtime-device-key use case "Head commitments (doc 03 §6.3)". But doc 03 §6.3 is specifically the **Trust-Lineage chain commitment** signed by the principal's **Genesis key**. Doc 03 §6.3 explicitly states (line 450):

> **Ledger `ledger_head_commitment`** (doc 04, forthcoming) — hashes the tip of the **entire Ledger** … Signed by the **runtime device key** (per doc 05 §4.1). Guards against rollback of the Ledger as a whole…

So there are **two distinct head-commitments**:

1. Trust-Lineage `chain_head_commitment` — doc 03 §6.3, Genesis-signed, per-principal, scope = Delegation Record chain only.
2. Ledger `ledger_head_commitment` — doc 04, runtime-device-key-signed, per-device, scope = entire Ledger.

Doc 05 §2.1 `ledger_head_commitment()` is the second one. But §4.1 bullet "Head commitments (doc 03 §6.3)" points at the first one. The runtime signs only the second; the Genesis key signs the first — and Genesis key lives in the vault, not the runtime.

**Location:** §2.1 method `ledger_head_commitment`; §4.1 bullet; §12 cross-reference list.

**Fix:**

- Rename §2.1 method to `ledger_head_commitment()` explicitly with a docstring: `"Per doc 04 ledger_head_commitment, signed by runtime_device_key. DISTINCT from doc 03 §6.3 chain_head_commitment which is Genesis-signed."`.
- Add §2.1 method `chain_head_commitment(principal_genesis_id)` returning doc 03 §6.3 commitment — explicitly NOT signed by runtime; retrieved from the principal's Trust Lineage.
- §4.1 bullet "Head commitments" → split into two lines: Ledger head (doc 04, runtime-signs), Trust-Lineage chain head (doc 03 §6.3, Genesis-signs, runtime does NOT sign — runtime surfaces it for sync/verify).

**Severity rationale:** CRITICAL. Attribution error in a security-contract-bearing primitive. If an implementer follows §4.1 as written, they will sign the Trust-Lineage chain commitment with the runtime device key, which (a) violates doc 03's authority grammar and (b) defeats T-100 rollback detection because the attacker's compromised runtime now controls the commitment anyway.

---

### F-02 — CRITICAL — Runtime-key rotation "dual-signed old+new runtime keys" omits Genesis co-signature

**Issue:** §4.1 "Rotation: … runtime key rotates via a `RuntimeKeyRotationRecord` in Ledger, dual-signed (old + new runtime keys)."

Dual-signing with old+new runtime keys proves only that the runtime that holds the old private key consented — but by assumption (rotation-on-compromise), the old runtime private key may be in attacker hands. Attacker-controlled runtime signs rotation to a new attacker-controlled key; Ledger has a valid-looking rotation record signed by both old and new runtime keys; no user-authority signal ever intervened.

Compare to doc 03 §8.2 KeyRotationRecord which IS authored by the principal (Genesis-level) with the user's authority. Runtime-device-key rotation MUST carry a Genesis co-signature (or equivalent user-authority ceremony) to be meaningful against T-050b + T-070 (side-channel) compromise.

**Location:** §4.1 Rotation paragraph.

**Fix:** Rewrite rotation to: "`RuntimeKeyRotationRecord` is triple-signed: (a) old runtime key (consenting handoff), (b) new runtime key (proof-of-key-generation), (c) user's Genesis key OR current Delegation key authorized for device-management (user-authority gate). Rotation without Genesis co-signature is refused at Ledger append time." Note: on suspected-compromise, even the Genesis co-signature requires an out-of-band ritual (e.g., Shamir 2-of-5 re-unlock) before the rotation can be recognized by other devices — doc 03 §8.2 already covers this.

**Adversarial note:** Without this, a compromised runtime that survives a single Grant Moment unlock has a permanent forward path: rotate its own device key whenever it likes, invalidating nothing from the user's perspective.

**Severity:** CRITICAL. Defeats the separation-of-duties claim that is the stated rationale for having a distinct runtime key at all.

---

### F-03 — CRITICAL — Runtime switch uses Genesis key but no unlock ceremony is defined

**Issue:** §8.2 step 3: "Write `RuntimeSwitchRecord` to Ledger (signed by user's Genesis key, attests user-authorized switch)."

Genesis key lives in the Trust Vault. Trust Vault unlock requires a user ceremony (passphrase, biometric, Shamir). Doc 05 does not specify what ceremony gates the switch. A compromised runtime that already has a warm unlock can invoke the switch flow silently. The attacker then installs a parallel attacker-controlled runtime, rotates the runtime device key via §4.1 (also unguarded per F-02), and the user has lost both runtimes without a single Grant Moment.

**Location:** §8.2 step 3; §8.1 first-run picker does not define unlock gates either.

**Fix:**

1. §8.2 step 3 MUST require an **explicit Grant Moment** with the visual-secret (doc 09 T-018) rendered at OS level; the Grant Moment text states plainly "You are changing the code that runs your agent — this requires a fresh unlock and your visual secret."
2. The Genesis signature on `RuntimeSwitchRecord` is produced inside a **short-window unlock** (e.g. 60s) that is NOT the same unlock as any concurrent tool-call session. Requires a clean Trust Vault unlock initiated explicitly for the switch.
3. The new runtime's startup `RuntimeAttestation` + its first Phase B record land BEFORE the old runtime terminates (overlap window), so a cross-signed handoff Ledger entry exists.

**Severity:** CRITICAL. The runtime-switch flow is the sovereignty claim's structural expression; if the ceremony is undefined it is exploitable.

---

### F-04 — HIGH — Abstract interface omits primitives that doc 02/03/09 expect the runtime to expose

**Issue:** §1 claims "Abstract `kailash-runtime` interface surface" is "the single source of truth for every operation Envoy performs that must be consistent across SDK implementations." But §2.1 omits:

- **Prompt-assembly primitive** — doc 02 §18 BET-6 byte-identical wire format (`<trusted_context>`, `<untrusted_context>`, `<ledger_entry trust=…>`, `<tool_response>`). The cross-SDK byte-identity of this wire format is explicitly called out as BET-6; runtime must own it, not channel adapters.
- **Tool-output sanitization pipeline** — doc 02 §20, `envoy-registry:prompt-injection-patterns:v1` pattern list. Doc 09 T-011 mitigation. No `tool_output_sanitize()` method in §2.1.
- **Classifier registry resolver** — doc 02 §14.6 mentions classifier registry; `classifier_invoke()` in §2.1 takes `classifier_ref: str` but no `classifier_registry_resolve()` to convert ref → implementation + model-hash.
- **First-time-action gate primitive** — doc 02 §19 is a Phase 01 MUST mitigation for T-010; runtime is the natural owner; no method in §2.1.
- **Turn-N goal-reconfirmation trigger** — doc 02 §16 / doc 09 T-013/T-014/T-016; no method.
- **Grant Moment primitives** — §2.1 has no `grant_moment_present()`, `grant_moment_verify_visual_secret()`, `grant_moment_sign()`. Doc 09 T-018/T-019 depends on runtime-level dialog-rendering attestation.
- **`content_trust_level` parameter validation** — §2.1 `ledger_append()` takes `content_trust_level` but no validation that it is one of the 8 canonical enum values; doc 02 §12 / doc 09 T-012 mandate.

**Location:** §2.1 entire interface.

**Fix:** Add a new subsection §2.1.x "Context assembly + Grant Moment + sanitization" with these primitives. Minimum surface:

```python
@abstractmethod
def assemble_llm_context(self, envelope, user_input, ledger_entries, untrusted_content) -> bytes: ...
@abstractmethod
def sanitize_tool_output(self, tool_name, raw_output) -> SanitizedToolOutput: ...
@abstractmethod
def classifier_registry_resolve(self, classifier_ref) -> ClassifierImpl: ...
@abstractmethod
def first_time_action_check(self, action, session_state) -> FirstTimeActionResult: ...
@abstractmethod
def grant_moment_present(self, moment_data) -> GrantMomentPresentResult: ...
@abstractmethod
def grant_moment_sign(self, moment_data, presented_visual_secret_hash, user_genesis_key) -> bytes: ...
@abstractmethod
def turn_n_goal_reconfirm(self, session_state) -> Optional[GoalReconfirmMoment]: ...
```

Plus §2.1 `ledger_append()` docstring: "`content_trust_level` MUST be one of the 8 canonical values from doc 02 §12; invalid value → `ContentTrustLevelInvalidError`."

**Severity:** HIGH. Doc 05's abstract-interface completeness is its raison-d'être; omitting 7 primitives the frozen specs mandate breaks the "single source of truth" claim.

---

### F-05 — HIGH — E3/E4 conformance cross-refs broken

**Issue:** §5.7 lists:

> - **E3 — Cascade revocation BFS/DFS set-equality** (doc 03 §5.2 15-vector corpus).
> - **E4 — Cycle detection** (doc 03 §6.2 15-vector corpus).

Doc 03 §5.2 IS cascade BFS/DFS parity — correct. But doc 03 §6.2 is **envelope-version binding** (T-104), not cycle detection. Doc 03 cycle detection (mentioned in §1 scope line: "Chain verification algorithm (cycle detection, monotonicity)") is covered in the verify algorithm in §4 territory, not §6.2.

**Location:** §5.7 E3, E4 entries.

**Fix:** E4 → "Cycle detection (doc 03 §4 verify-chain algorithm; 15-vector corpus)" or move cycle-detection vectors under a new numbered section of doc 03 and reference that. Confirm corpus file location (`tests/conformance/trust_lineage/cycle/`?) when committed.

**Severity:** HIGH. Broken cross-reference on a Phase 02 entry-gate artifact — the cross-SDK harness won't run if the vectors can't be found at the cited location.

---

### F-06 — HIGH — Binary-poisoning defense claim collides with T-050b acknowledged residual

**Issue:** §4.2 "Binary poisoning defense (doc 09 T-060): on every startup, `binary_hash` is verified against Foundation-signed manifest. Mismatch refuses to load."

Doc 09 T-050b + §3.8 T-060 entry EXPLICITLY state: "T-060's load-time verification is defeated by T-050b — this chain is now documented." Doc 05 §4.2 sells load-time verification as the defense without flagging the T-050b chained-dependency that doc 09 already documented as a residual. The following paragraph does mention T-050b, but only says "binary_hash + algorithm_identifier must both match" — which does nothing against a signing-key-compromised manifest because both values would be signed by the compromised key.

**Location:** §4.2 two last paragraphs.

**Fix:** Rewrite "Binary poisoning defense" paragraph to say: "binary_hash load-time verification defeats naive T-060 post-install substitution. It does NOT defeat T-050b (signing-key compromise) — per doc 09 §3.7 residual, reproducible-build verification + kailash-py escape are the only defenses against T-050b. High-risk users are directed to kailash-py runtime." Include a pointer to the explicit residual-risk acceptance list in doc 09 §last-table (line 833).

**Severity:** HIGH. Overstating the defense misleads implementers about what they are building.

---

### F-07 — HIGH — Orphan "Retry" path is a capability-replay surface

**Issue:** §6.3 Orphan resolution offers **Retry** as a first option, gated only by "idempotent tools; flag per-tool in envelope Operational dimension."

Adversarial scenarios:

1. Attacker induces a crash between Phase A and Phase B (e.g., OOM from T-015 context exhaustion timed at the right moment).
2. Next session start: orphan-resolution Grant Moment offers Retry. User has habituated to Retry for legitimate tools (T-019).
3. The "idempotent" flag was staged in the envelope by a prior attacker-planted skill (Phase 02 skill ingest is a mutation vector).
4. Retry re-executes, but the side-effect has already occurred — double-execution of a non-idempotent operation the envelope falsely claimed was idempotent.

There is no nonce binding preventing Phase A re-signature with the same intent against a post-crash envelope that has been mutated; no check that the re-execution happens in the same session/context that originally signed Phase A.

**Location:** §6.3 Retry option.

**Fix:**

1. Retry MUST re-compute envelope_snapshot_hash against the CURRENT envelope and fail if it does not match the Phase A intent's `envelope_snapshot_hash`. If envelope changed between crash and restart, Retry is BLOCKED; user must use Record-as-failed or Investigate.
2. Retry-eligibility (idempotent flag) MUST be co-signed by the USER (Genesis or authored-constraint) — a skill cannot by itself declare a tool idempotent.
3. Retry Phase A re-signature uses a NEW `intent_id` and NEW nonce; links back to the orphan via a separate `retry_of_intent_id` field; prevents bit-identical replay.
4. Retry is rate-limited: one retry per orphan; second-retry → Record-as-failed only.

**Severity:** HIGH. Orphan-resolve is a routine recovery flow that users click through; a replay surface here is a high-value exploit path.

---

### F-08 — HIGH — HALTED vs Phase-B record semantics conflated

**Issue:** §4.1 bullet: "HALTED-by-rollback Ledger entries (doc 02 §6.1 Branch 3)" is one use of runtime_device_key. §6.2 Phase B is ALSO signed by runtime_device_key. But a HALTED record describes a Phase-A intent that never reached Phase-B (halted by rollback). The PhaseBRecord schema in §2.2 includes `outcome_type: "halted_by_rollback"` as one of four outcome types.

This conflation leaves two questions unanswered:

1. If the HALTED record IS a PhaseBRecord with `outcome_type: halted_by_rollback`, then §4.1 bullet is redundant with Phase B use — should be merged.
2. If HALTED is a distinct record type (per doc 02 §6.1 Branch 3), the schema in §2.2 should show it as a separate type, not a Phase-B outcome enum.

Currently both readings are possible.

**Location:** §4.1 bullets; §2.2 PhaseBRecord; §6.2 flow.

**Fix:** Pick one model and apply consistently. Recommend: HALTED is a distinct record type `HaltedRecord` with fields `{halted_intent_id, halt_reason: 'envelope_rollback' | 'cascade_revoke' | 'policy_change', halted_at, runtime_signature}`. Phase B outcome enum drops `halted_by_rollback`. Then §4.1 bullet "HALTED-by-rollback" is unambiguous.

**Severity:** HIGH. Schema ambiguity in the signing-authority surface — one implementer will ship one shape, the other will ship the other, and BET-6 byte-identity breaks.

---

### F-09 — HIGH — Vault compatibility "algorithm_identifier match" is per-runtime; vault has per-artifact-type algorithms

**Issue:** §8.2 step 2: "Verify Trust Vault + Ledger are compatible (algorithm_identifier match required)."

Trust Vault holds Genesis Record, multiple Delegation Records, envelope edits, ReasoningCommits, Phase A/B records, head-commitments, Grant Moment signatures. Each carries its own `algorithm_identifier` (per doc 00 §4.1 item 9 + doc 03 §8.3 legacy-verification resolver). The vault will contain a MIX of algorithm versions over time (legacy records stay under their original tag).

A single runtime-level `algorithm_identifier match` check at switch time is wrong:

- If runtime's supported set is a SUBSET of what's in the vault, migration silently succeeds but later the runtime can't verify legacy records.
- If runtime's supported set is a SUPERSET, same check passes but the switch-back path to an older runtime will fail at unknown records.
- If runtime's supported set is DISJOINT, nothing works but the check described may still pass depending on implementation.

**Location:** §8.2 step 2; §10.2 forward-compat; §10.3 backward-compat.

**Fix:** Replace "algorithm_identifier match required" with "runtime declares **supported_algorithm_set**; switch is allowed iff `supported_algorithm_set ⊇ union-of-algorithms-in-vault`. If subset, switch refuses with a concrete list of unsupported records. Legacy-verification resolver (doc 03 §8.3) runs per-record-type at read time; no single vault-level check." Update §10.2/§10.3 accordingly.

**Severity:** HIGH. Silent runtime-switch incompatibility is a data-loss risk.

---

### F-10 — HIGH — Security-review gates do not name agents per `rules/agents.md`

**Issue:** §9.1–§9.5 gates list deliverables but do NOT name review agents. `rules/agents.md` § Quality Gates specifies:

> | Implementation done | `/implement` | **MUST** | **reviewer** + **security-reviewer**: Run as parallel background agents. |
> | Before release | `/release` | **MUST** | **reviewer** + **security-reviewer** + **gold-standards-validator**: Blocking. |

Doc 05's gates should call these out by name per phase so they're not "recommended" that get skipped.

**Location:** §9 subsections.

**Fix:** Per Phase gate, add a "Review agents (MUST)" row listing concrete agents. Examples:

- Phase 01 gates → reviewer + security-reviewer (binary path not yet live, so not yet gold-standards for distribution).
- Phase 02 gates → reviewer + security-reviewer + gold-standards-validator (distribution lands).
- Phase 03/04 → same + pact-specialist + cross-SDK parity agent (if one is defined).

**Severity:** HIGH. Unnamed gates are structurally "recommended"; `rules/agents.md` MUST rule broken.

---

### F-11 — HIGH — `RuntimeIdentity` omits `binary_hash`

**Issue:** §2.2 `RuntimeIdentity` = `{runtime_family, version, device_bound_pubkey_hex, algorithm_identifier}`. §4.2 `RuntimeAttestation` (at-startup record in Ledger) DOES include `binary_hash`. But callers of §2.1 `runtime_identity()` will not see `binary_hash`. A poisoned binary can match all fields of `RuntimeIdentity` as written; only the attestation's binary_hash would distinguish. Since callers get their knowledge of "what runtime is this" from `runtime_identity()`, the poisoned binary passes every subsequent check.

**Location:** §2.2 `RuntimeIdentity` type.

**Fix:** Add `binary_hash: str` to `RuntimeIdentity`. Runtime at startup computes its own binary hash (self-measurement) and carries it in identity. Callers who want attestation assurance also check against the Ledger's latest `RuntimeAttestation` to verify the self-measured hash matches the manifest-verified hash.

**Severity:** HIGH. Identity-without-hash is the attacker's preferred shape.

---

### F-12 — MEDIUM — Re-read checkpoint cross-ref to "doc 02 §14 N2" is imprecise

**Issue:** §7 "Performance: … invalidated per doc 02 §14 N2 conformance (envelope version bump, role override, etc.)." Doc 02 §14 is the algorithm construction pack; §14.6 is classifier registry. The 5-property N2 invalidation is under the PACT-N-vector side of things (doc 05 §5.2 N2 + doc 02 §14.5 or possibly elsewhere). The section number cited is imprecise and will not resolve at implementation time.

**Location:** §7 last paragraph.

**Fix:** Change to "invalidated per N2 conformance (5 properties; see §5.2 this doc)" and drop the doc 02 §14 reference or point to the exact §14.x.

**Severity:** MEDIUM. Precision issue; not a correctness issue, but makes the contract harder to implement.

---

### F-13 — MEDIUM — Two-phase signing: how does the runtime get the delegation private key?

**Issue:** §6.1 step 3 signs Phase A with `delegation_private_key`. In doc 03, delegation private keys are owned by the principal (user) and stored in the Trust Vault. Every tool-call therefore requires an unlock of the vault sufficient to release the delegation key for a single sign operation. Doc 05 does not specify:

- Is the delegation key released once per session (cached in runtime memory — widens T-071 memory-disclosure surface)?
- Once per tool-call (requires an unlock ceremony per tool-call — breaks BET-2 latency budget)?
- Once per tool-call but from a hardware-unlocked Secure Enclave context (plausible but undocumented)?

**Location:** §6.1 step 3; §4.1 Storage paragraph.

**Fix:** Add §6.1 step 3a: "Delegation private keys are used via a Secure-Enclave / TPM session that the runtime holds for the duration of a session; keys never leave the enclave; signing is invoked via enclave API with per-call audit logging. Fallback (software-backed vault): key material is held in a locked memory region (mlock + mprotect NONE except during sign), zeroed on idle-timeout, re-unlocked via ceremony. T-071 memory-disclosure residual: software-backed mode has higher residual; Secure-Enclave mode preferred for high-stakes deployments."

**Severity:** MEDIUM. Load-bearing implementation detail; can be resolved within doc 05's scope without pulling another doc open.

---

### F-14 — MEDIUM — Orphan 30-day window gameable

**Issue:** §6.3 "30 days default" orphan-detection window. §13 Q-2 raises but doesn't resolve. Attacker induces device offline for 31+ days (social engineering, device theft + return) to push orphaned Phase As out of the detection window. On re-login, the orphan is silently forgotten.

**Location:** §6.3 Detection paragraph; §13 Q-2.

**Fix:** Either:

- (A) Orphan window is **unbounded** — every Phase A without a Phase B remains an orphan until resolved. Surface count in Weekly / Monthly Trust Reports.
- (B) Orphan window is per-envelope-Operational-dimension; the envelope author (user) sets it per tool risk tier.
- Prefer (A) for sovereignty default; (B) as advanced user setting.

Document decision and close §13 Q-2.

**Severity:** MEDIUM. Low likelihood but high blast-radius (non-repudiation collapse for the lost window).

---

### F-15 — MEDIUM — Downgrade flow: forced-incompatibility as denial / coercion vector

**Issue:** §10.3 "If new records cannot be read by old runtime → refuse downgrade; surface error to user." Attacker scenario: attacker who wants to coerce a user onto a compromised-binary runtime can stage records in the Ledger that the known-good older runtime cannot read, then tell the user "you can't downgrade because your Ledger has newer entries." User accepts the lock-in.

**Location:** §10.3.

**Fix:** Downgrade refuses to WRITE new records using old algorithm, but MUST remain able to READ the ledger through the legacy-verification resolver (doc 03 §8.3) which handles cross-version verification. "Cannot be read" should be "cannot be written to by the older runtime without losing the current algorithm's semantics" — not "the older runtime can't verify existing records." With legacy-verification resolver, the older runtime CAN read newer records (it just can't emit new records in the newer format).

**Severity:** MEDIUM. Documentation precision issue with adversarial implications if the reading implementer takes the stricter reading.

---

### F-16 — LOW — "Foundation-signed manifest" framing vs independence.md

**Issue:** §4.2 "Trust Vault verifies the binary hash matches Foundation-published manifest." Per `rules/independence.md`, the Foundation owns the standards + open-source SDK; the manifest in question is the Foundation's distribution manifest for the open-source `kailash-py` side. The Rust binary `kailash-rs-bindings` path's manifest is whatever entity owns that distribution — if Foundation-operated, the framing is correct; if the Foundation declines to operate distribution for a Rust-accelerated Python binding, the manifest is a distinct entity's signed artifact. This collision is already acknowledged in doc 00 §7 open question (Foundation board endorsement of runtime-pluggability); doc 05 should reference it rather than silently assume.

**Location:** §4.2.

**Fix:** Add a sentence: "Manifest-operator identity per ADR-0001 / ADR-0009 is the Foundation OR a designated Foundation-authorized distributor. Until the endorsement question is resolved (doc 00 §7 open-Q list), this is a conditional posture."

**Severity:** LOW. Not a correctness issue; posture clarity.

---

### F-17 — LOW — Type-definition completeness: most types referenced but not locally grounded

**Issue:** §2.2 Types lists 6 concrete definitions; §2.1 interface references 15+ dataclasses (including `ToolCallIntent`, `ToolCallOutcome`, `EffectiveEnvelopeSnapshot`, `SessionObservedState`, `BudgetReservation`, `VelocityCheckResult`, etc.). Most are grounded via cross-reference, not local schema. Doc 05 as "single source of truth" should define or explicitly punt every type.

**Location:** §2.2.

**Fix:** Add a table listing every type referenced in §2.1 with owner doc + one-line semantics. Types owned here (RuntimeIdentity, EnvelopeCheckResult, PhaseARecord, PhaseBRecord, LedgerPosition, HeadCommitment) fully defined locally; others get a one-line "defined in doc 0X §Y; key fields: …".

**Severity:** LOW. Completeness hygiene.

---

## Cross-cutting notes

### Adversarial surface summary

The review surfaced four adversarial surfaces that compose:

1. **Runtime-key rotation (F-02) + runtime switch (F-03)** — together let a compromised runtime achieve durable persistence across device rotations with zero Grant Moment signal to the user. These two findings MUST be fixed as a pair; fixing one without the other leaves a bypass.
2. **Binary-poisoning defense overstatement (F-06) + Identity without binary_hash (F-11)** — together let a T-050b attacker evade not only the load-time check but also any downstream "I'm the right runtime" assertion.
3. **Orphan Retry (F-07) + orphan-window gameability (F-14)** — together let an attacker induce a window-expired orphan replay that the user approves because the UX is habituated.
4. **Ledger-head vs Trust-Lineage-head conflation (F-01) + Vault compat check (F-09)** — together let a runtime-switch attacker bypass the rollback-detection invariant by switching runtime during the moment the commitments would have been re-verified.

All four surfaces are closeable with the fixes named in the individual findings.

### Frozen-anchor drift check

- **Doc 00 v3 BET-6 contract parity** — doc 05 v1 §3.1/§3.2 split is faithful.
- **Doc 00 v3 §4.1 item 15 N=3 mirrors** — referenced (§4.2, §8.1) but doc 05 does not add any new constraint beyond doc 00.
- **Doc 02 v3 §17 envelope re-read checkpoint** — faithfully referenced in §7; F-12 is a precision issue on §14 vs §14.5, not a drift.
- **Doc 03 v2 §7.2 SubsetProof verifier** — correctly referenced in §2.1 `trust_verify_subset_proof` with the "signs result with runtime_device_key" contract matching doc 03 §7.2 line 513.
- **Doc 09 v3 T-004 two-phase signing** — structurally faithful; F-07/F-08 are implementation-detail drifts within the two-phase model, not a BET-level drift.

### What's green in doc 05 v1

- Interface surface organization (lifecycle / trust / envelope / two-phase / ledger / classifier / budget / attestation) is clean.
- Byte-identical vs semantically-equivalent partition (§3) is the right shape against BET-6.
- Error taxonomy in §2.3 is tight and names actionable consumer actions.
- Phase migration §8.3 and gating §9 skeletons land in the right sequence.
- Conformance vector decoding for N1/N2/N4/N5 + Envoy E1/E2/E5/E6/E7 is useful new content that doc 00 alluded to but did not ground.

Converge on the 17 findings (especially the 3 CRITICAL + 8 HIGH pair-dependencies) and doc 05 is ready for v2 → `/redteam` Round 2.

---

**End of combined Round 1 review.**
