# 18 — Runtime abstraction stub (Phase 02 readiness invariant)

**Document role:** Define, in Envoy-implementation terms, the abstract `kailash_runtime` interface contract that every Phase 01 primitive depends on, the kailash-py adapter that satisfies the contract for Phase 01 ship, and the deferred-but-named kailash-rs-bindings adapter slot that Phase 02 wires. Phase 02 mechanicality is the load-bearing invariant: switching the active adapter from kailash-py to kailash-rs-bindings MUST require zero changes to Envoy primitive code, only to the runtime adapter module and (Phase 02) the first-run picker.

**Date:** 2026-05-03 (shard 18 of /analyze).
**Status:** DRAFT — load-bearing for `01-shard-plan.md` shard 18 (no production primitives gate on it directly, but every other Phase 01 primitive imports through this surface, so it gates the import discipline of all 15 sibling deep-dives).
**Source spec:** `specs/runtime-abstraction.md` (FROZEN v1) — DO NOT EDIT in Phase 01.

---

## 1. Source spec citation

The frozen `specs/runtime-abstraction.md` is the contract; this doc cites it by section, never paraphrases. The five load-bearing anchors:

- `specs/runtime-abstraction.md` §Abstract interface — the `KailashRuntime` ABC; every method below MUST be implemented by both kailash-py and kailash-rs-bindings runtimes.
- `specs/runtime-abstraction.md` §Contract partition (BET-6) — the byte-identical-vs-semantically-equivalent split. This shard's job is to translate that partition into Envoy-side type and import discipline.
- `specs/runtime-abstraction.md` §Conformance vectors N1–N6 decoded — what each cross-runtime parity vector class tests; Phase 01 adopts E1–E7 against kailash-py only (N-vectors are Phase 02 cross-runtime gates).
- `specs/runtime-abstraction.md` §Runtime device key — the device-bound signing key surface (Secure Enclave / TPM / software fallback); Phase 01 ships software fallback; Phase 02 introduces Secure Enclave / TPM via the Rust binding.
- `specs/runtime-abstraction.md` §Security gates per phase — Phase 01 row: kailash-py impl; E1–E7 vectors pass; two-phase + envelope re-read functional; algorithm-identifier schema landed.

The cross-runtime contract draft from Phase 00 (`workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md`) is the operational source of truth for which methods sit in which tier; this shard's class-structure sketch in §4 cites that draft's §2.1 / §2.2 / §5 surface-by-surface table directly.

ADR-0001 (`DECISIONS.md` §3 / `00-inheritance-from-phase-00.md` §2.2) binds Phase 01 to wire kailash-py only while requiring the abstract interface to exist as a stub on the Rust side — i.e., the interface MUST accept a Phase 02 adapter without spec churn or a re-organisation of every primitive's import graph.

`00-inheritance-from-phase-00.md` §6 invariant 4 (frozen-redteam-output) restates the invariant in implementation language: "even though Phase 01 ships only kailash-py, the abstract interface MUST distinguish byte-identical-spec methods from semantically-equivalent-LLM methods so Phase 02 wiring is mechanical." This is the BET-6 enabling condition.

## 2. Verified provider state

Not applicable in the usual shard-sense. This shard is Envoy-new-code by design — there is no kailash-py provider whose grade we are extending from the Phase 00 survey, no closed upstream issue that lifts the burden, and no upstream PR to verify. `03-kailash-py-mvp-readiness.md` §3 row 15 states this explicitly: "n/a — Phase 01 defines abstract interface only; only `kailash-py` wired."

What this means operationally:

- The abstract interface lives entirely in Envoy's namespace (`envoy.runtime`), authored by the Phase 01 build, against the FROZEN `specs/runtime-abstraction.md`.
- The kailash-py adapter (`envoy.runtime.adapters.kailash_py`) is a thin shim that maps each `KailashRuntime` ABC method to a kailash-py call. Where kailash-py provides the primitive directly (12 of 13 ISS closed per `03-kailash-py-mvp-readiness.md` §2), the adapter is a one-line dispatch. Where kailash-py is gap (`#596` `TieredAuditDispatcher`, see `03-kailash-py-mvp-readiness.md` §4 row 1), the adapter dispatches into the Envoy-new-code module written for that gap (per shard 6 `06-envoy-ledger-implementation.md`).
- The kailash-rs-bindings adapter slot (`envoy.runtime.adapters.kailash_rs_bindings`) is a deferred module — its file MUST exist in the Phase 01 ship (see §3 below) so that Phase 02 wiring is purely "fill in the methods", not "add a new package and re-route every import."

The "verified provider state" row therefore reads: **kailash-py is the only Phase 01 adapter target; kailash-rs-bindings is a Phase 02 deferred-but-named slot; the abstract interface is Envoy-authored, gating both.**

## 3. Envoy-new-code surface

The Phase 01 deliverable is three modules, none of which exist in kailash-py upstream and all of which Envoy MUST author:

### 3.1 `envoy.runtime` — the abstract interface

A Python `Protocol` class (PEP 544) preferred over `abc.ABC`, because:

- Adapters from kailash-py and kailash-rs-bindings are already-typed objects that we wrap at composition time, not Envoy-derived subclasses; structural typing is the more honest contract.
- Protocol-typed parameters across primitive signatures (e.g., `def append(entry: LedgerEntry, runtime: KailashRuntime) -> ...`) document the dependency at every call site.
- `runtime_checkable` Protocol allows the kailash-py adapter to be a plain object that "happens to satisfy" the interface, which is the desired Phase 02 substitution semantics.

Method-set is exactly the §Abstract interface table from `specs/runtime-abstraction.md` (§Lifecycle, §Trust Lineage, §Envelope, §Two-phase signing, §Ledger, §Classifier, §Budget, §Runtime device-key signing, §Prompt + tool-output). Per `rules/zero-tolerance.md` Rule 6 (implement fully), every method on the FROZEN spec table MUST be on the Protocol; any method that is "not yet exercised in Phase 01" still MUST appear with its full type signature, because Phase 02 substitution has zero tolerance for "we'll add this method later when the Rust adapter needs it."

This is the orphan-detection edge of this shard: under `rules/orphan-detection.md` MUST Rule 1, the abstract interface must have at least one production call site in Phase 01 — see §5 for the enforcement.

### 3.2 `envoy.runtime.adapters.kailash_py` — the Phase 01 production adapter

A concrete class `KailashPyRuntime` that satisfies the Protocol. Internally:

- Imports `kailash` (the kailash-py distribution; `kailash-coc-claude-rs` template variant despite the name; see `CLAUDE.md` §Kailash Platform — the package is `kailash` and the provider for Phase 01 is the open-source pure-Python build, not the Rust-binding wheel).
- Maps each Protocol method to the kailash-py module/class identified in `03-kailash-py-mvp-readiness.md` §3, e.g. `envelope_intersect → kailash.trust.pact.envelopes.intersect_envelopes`, `trust_sign → kailash.trust.signing.crypto.sign`, `budget_reserve → kailash.trust.constraints.BudgetTracker.reserve`.
- For `ledger_append` / `ledger_query` / `ledger_verify_chain` / `head_commitment` (the four methods that depend on the still-OPEN `#596 TieredAuditDispatcher`), the adapter dispatches to the Envoy-new-code Ledger writer that shard 6 (`06-envoy-ledger-implementation.md`) builds. This is the single Phase 01 "Envoy-side substitute for an upstream gap" routing — every other adapter method is a kailash-py forward.
- For methods that depend on a closed-but-not-yet-verified upstream module (the §3 "verify in shard N" rows in the readiness map — `OrchestrationRuntime`, `PlanSuspension`, Shamir wiring), the adapter routes through the upstream symbol with a regression test (`tests/regression/test_runtime_adapter_kailash_py_<method>.py`) per shard 6/9/11/15's verification protocol.

### 3.3 `envoy.runtime.adapters.kailash_rs_bindings` — the Phase 02 deferred slot

A module that MUST exist as a file in Phase 01, with the class declared, every Protocol method present, and every method body raising `NotImplementedError("Phase 02 wiring; tracked in TODO-rs-binding-NN")` with a stable, grep-able tag that Phase 02 entry uses to enumerate the unfinished surface.

This is in tension with `rules/zero-tolerance.md` Rule 2 (no `NotImplementedError` in production). The reconciliation: the Phase 01 ship MUST gate the kailash-rs-bindings adapter behind a feature flag (`envoy.runtime.feature_flags.RS_BINDINGS_ENABLED = False`); the abstract interface's runtime-selection function MUST reject any attempt to instantiate `KailashRsBindingsRuntime` while the flag is False, returning a typed `RsBindingsNotAvailableInPhase01Error` rather than allowing the `NotImplementedError` to surface. The flag flip + adapter-fill is the entirety of Phase 02's runtime-substitution work — nothing else.

The deferred-slot pattern here MUST follow the discipline established in `00-inheritance-from-phase-00.md` §2.2 (ADR-0001 binding) — Phase 01 ships the abstract interface AND a kailash-py adapter that is functional AND a kailash-rs-bindings module shell that is structurally present but feature-flagged off. Phase 02 entry sees a single named module to fill; it does not see a refactor task.

## 4. Class structure sketch

The class structure sketch is intentionally interface-only — Phase 01 implementation deep-dives in shards 4–17 cite this shard's tier classification when wiring per-primitive imports. Per `rules/specs-authority.md` MUST Rule 3 (specs are the authority; this doc does NOT re-derive), every method below cites its source-spec partition in Phase 00 conformance plan §5.

### 4.1 Tier classification (cross-references `01-runtime-swap-contract.md` §5)

The Phase 00 conformance plan `01-runtime-swap-contract.md` §2.1 + §2.2 + §5 provides a per-method tier table. Phase 01 adopts that classification verbatim. This shard's job is NOT to redo the classification; it is to ensure the Envoy-side type system encodes the partition so Phase 02 conformance failures surface at the right boundary.

**Byte-identical surfaces** (per `01-runtime-swap-contract.md` §2.1 + §5):

- Lifecycle: `startup`, `shutdown`, `runtime_identity`
- Trust: `trust_sign`, `trust_verify_chain`, `trust_cascade_revoke`, `trust_verify_subset_proof`
- Envelope: `envelope_canonical_form`, `envelope_intersect`, `envelope_check`, `envelope_re_read_checkpoint`
- Two-phase signing: `phase_a_sign_intent`, `phase_b_sign_outcome`, `phase_a_orphan_resolve`
- Ledger: `ledger_append`, `ledger_query`, `ledger_verify_chain`, `head_commitment`
- Classifier aggregation: `ensemble_aggregate`, `classifier_registry_resolve`
- Budget: `budget_reserve`, `budget_record`, `budget_snapshot`, `budget_velocity_check`
- Runtime device-key: `runtime_sign`, `runtime_verify`
- Prompt assembly canonical hash: `prompt_assemble.rendered_canonical_hash` (the `rendered_bytes` part is semantic)
- Tool-output structural sanitisation: `tool_output_sanitize.verdict`, `tool_output_sanitize.structural_fields`
- First-time-action gate fingerprint: `first_time_action_gate.fingerprint` component
- Grant Moment structured payload: `grant_moment_surface.structured_request`, `grant_moment_surface.structured_result`

**Semantically-equivalent surfaces** (per `01-runtime-swap-contract.md` §2.2 + §5):

- `classifier_invoke` (LLM-driven verdict text; structured `verdict_class` is byte-identical)
- `grant_moment_surface.prompt_text` (LLM-rendered for the user)
- `prompt_assemble.rendered_bytes` (tokenisation may differ; canonical hash is byte-identical)
- `tool_output_sanitize.text_for_user` (LLM-rendered explanation)
- Tool-call timing metadata (wall-clock + jitter)

### 4.2 How the partition becomes Envoy code structure

The partition MUST surface in the Envoy-side type system, not only in the spec text. Three concrete encodings:

1. **Return-type wrappers.** Methods in the byte-identical tier return concrete types whose `__hash__` and `__eq__` operate on the spec-defined canonical form (e.g., `LedgerEntry.__hash__` over the JCS-RFC8785-NFC payload, NOT over the Python `dict`). Methods in the semantically-equivalent tier return wrapped types with an explicit `.canonical_hash` attribute (byte-identical) and a `.semantic_payload` attribute (under similarity oracle); equality on the wrapped type SHOULD raise `ByteEqualityNotDefinedError` to prevent accidental `==` comparisons that silently use Python identity-equality. (Note: Phase 02 `acceptance-metrics.md` may relax this if a stricter `__eq__` is needed; the Phase 01 default is "fail loud, never silent.")

2. **Decorator markers.** Each Protocol method is decorated `@byte_identical` or `@semantically_equivalent` (decorators that attach a `__contract_tier__` attribute, do nothing else). The conformance runner per `01-runtime-swap-contract.md` §7 reflects on this attribute to dispatch the correct comparator. Phase 02 readiness is structurally enforced by a CI lint that fails if any Protocol method is missing one of the two decorators.

3. **Per-method conformance-vector class binding.** Each Protocol method MUST also carry a `__conformance_vectors__: list[VectorClassId]` attribute, citing the N-class or E-class vectors that test it (per `specs/runtime-abstraction.md` §Test location + `01-runtime-swap-contract.md` §5 last column). Phase 01 lint verifies every method has at least one vector class bound; Phase 02 conformance gate verifies every bound vector class actually has corpus entries.

### 4.3 Reference vectors in Phase 01

Phase 01 ships only the kailash-py adapter, so cross-runtime byte-identity (`output_py == output_rs_bindings`) is unverifiable. What Phase 01 CAN verify:

- **Within-runtime determinism for byte-identical methods.** Repeated invocations of the same byte-identical method with the same input MUST produce byte-identical output across kailash-py adapter instances and across process restarts. Vector class: E1–E7 corpus subset that targets the kailash-py adapter only. Test: `tests/conformance/test_e1_envelope_canonical_json.py` through `tests/conformance/test_e7_head_commitment_monotonicity.py` per `specs/runtime-abstraction.md` §Test location.
- **Spec-output conformance for byte-identical methods.** Adapter output for a byte-identical method MUST byte-match the FROZEN spec's worked example (e.g., `specs/envelope-model.md` §Canonical JSON has worked examples that the conformance vectors mint from). Phase 01 acceptance: every E1–E7 vector passes against kailash-py.
- **Type contract for semantically-equivalent methods.** Adapter output must satisfy the structural-payload schema (which IS byte-identical even when the text isn't). Phase 01 acceptance: structured payloads validate against schema; rendered text is captured-and-stored for Phase 02 cross-runtime semantic-equivalence comparison.

This is what `specs/runtime-abstraction.md` §Security gates per phase Phase 01 row "kailash-py impl; E1–E7 vectors pass" actually compiles to in Envoy implementation terms.

### 4.4 Class structure (interfaces only)

```
envoy.runtime
  __init__.py                    # exports: KailashRuntime (Protocol), get_runtime()
  protocol.py                    # KailashRuntime Protocol; @byte_identical + @semantically_equivalent decorators
  errors.py                      # spec §Error taxonomy taxa: RuntimeNotReadyError, ...,
                                 # plus Envoy-internal: RsBindingsNotAvailableInPhase01Error,
                                 # ByteEqualityNotDefinedError
  types.py                       # return-type wrappers per §4.2 encoding 1 (LedgerEntry,
                                 # AssembledPrompt, EnsembleResult, ...); cite specs by anchor
  feature_flags.py               # RS_BINDINGS_ENABLED = False (Phase 01); flipped by Phase 02
  adapters/
    __init__.py                  # exports: KailashPyRuntime; lazy KailashRsBindingsRuntime
    kailash_py.py                # KailashPyRuntime — Phase 01 production adapter
    kailash_rs_bindings.py       # KailashRsBindingsRuntime — Phase 02 deferred slot,
                                 # gated by feature_flags.RS_BINDINGS_ENABLED
  selection.py                   # get_runtime() factory; Phase 01 always returns
                                 # KailashPyRuntime; Phase 02 reads first-run picker output
                                 # per specs/distribution.md §First-run flow
```

`get_runtime()` is the SINGLE entry point every primitive uses. Per §5 below, primitives never import adapter classes directly. This is the Phase 02 mechanicality lock.

## 5. Integration points

The integration story for this shard is uniform across every Phase 01 primitive: each primitive imports from `envoy.runtime`, never from `kailash` directly. This is the discipline that makes Phase 02 substitution mechanical.

### 5.1 Discipline: primitives import from `envoy.runtime`, never from `kailash`

```python
# DO — primitive imports through the abstract interface
from envoy.runtime import get_runtime, KailashRuntime
from envoy.runtime.types import LedgerEntry

class EnvoyLedgerWriter:
    def __init__(self, runtime: KailashRuntime | None = None):
        self._runtime = runtime or get_runtime()

    def append(self, entry: LedgerEntry) -> LedgerEntry:
        return self._runtime.ledger_append(entry)

# DO NOT — primitive imports kailash directly
import kailash  # BLOCKED outside envoy.runtime.adapters.*
```

Per `rules/zero-tolerance.md` Rule 4 (no workarounds for SDK bugs) the discipline has one exception: the `envoy.runtime.adapters.kailash_py` module MAY import `kailash` directly because that IS its job. Every other Envoy module that imports `kailash` is a Phase 02 substitution-failure waiting to happen and MUST be flagged by the Phase 01 lint described in §6.

### 5.2 Per-primitive mapping (cites shard map)

Every Phase 01 primitive (shards 4–17) integrates through this surface:

| Shard | Primitive                       | Runtime methods consumed (cite spec partition)                                                  |
| ----- | ------------------------------- | ----------------------------------------------------------------------------------------------- |
| 4     | Envelope compiler               | `envelope_canonical_form`, `envelope_intersect` (byte-identical)                                |
| 5     | Trust store + lineage           | `trust_sign`, `trust_verify_chain`, `trust_cascade_revoke`, `trust_verify_subset_proof` (BI)    |
| 6     | Envoy Ledger + verifier         | `ledger_append`, `ledger_query`, `ledger_verify_chain`, `head_commitment` (BI)                  |
| 7     | Independent verifier            | n/a — separately-codebased, MUST NOT import `envoy.runtime` (cross-impl independence per EC-9)  |
| 8     | Boundary Conversation           | `prompt_assemble` (BI canonical hash + SE rendered bytes), `classifier_invoke` (SE)             |
| 9     | Authorship Score + posture gate | `envelope_check.effective_posture` (BI, N5)                                                     |
| 10    | Grant Moment                    | `grant_moment_surface` (BI structured + SE prompt text), `phase_a_sign_intent` (BI)             |
| 11    | Daily Digest                    | `ledger_query` (BI), `prompt_assemble` (BI canonical hash + SE rendered bytes)                  |
| 12    | Budget tracker                  | `budget_reserve`, `budget_record`, `budget_snapshot`, `budget_velocity_check` (BI)              |
| 13    | Model adapter                   | `classifier_invoke` (SE), `prompt_assemble.rendered_bytes` (SE)                                 |
| 14    | Connection Vault                | n/a — Phase 01 minimal does not consume runtime methods                                         |
| 15    | Shamir 3-of-5 recovery          | n/a — paper-shard ritual is local-crypto; not a runtime method                                  |
| 16    | Channel adapters                | `grant_moment_surface` (BI structured + SE prompt text), `tool_output_sanitize` (BI + SE split) |
| 17    | Foundation Health Heartbeat     | `runtime_sign` (BI), `runtime_identity` (BI), `runtime_verify` (BI)                             |

(BI = byte-identical, SE = semantically-equivalent; rows cite `01-runtime-swap-contract.md` §5 directly.)

Independent verifier (shard 7) is the sole exception — per `02-mvp-objectives.md` EC-9 the verifier ships in a separate repo, in a separate language preferred (Rust) or by a separate agent, with zero source coupling to Envoy. Importing `envoy.runtime` would break that independence.

### 5.3 Production call site discipline (orphan-detection MUST Rule 1)

`rules/orphan-detection.md` MUST Rule 1 mandates that "every `db.*` / `app.*` facade has a production call site." The abstract interface MUST have at least one Phase 01 production call site that exercises a real adapter method end-to-end against real infrastructure (not a mock).

Every primitive shard 4–17 contributes call sites; the Phase 01 ship has at minimum 12 production-path call sites (the table in §5.2 minus shards 7, 14, 15 which are abstract-interface-independent). The lint check is: `! rg 'from envoy.runtime' src/envoy/ | grep -v 'envoy/runtime/'` should return at least 12 hits before Phase 01 ship.

If a primitive ships with zero call sites to its claimed runtime method, the abstract interface is orphaned for that surface — same failure mode as `rules/orphan-detection.md` §Phase 5.11 post-mortem (`skills/16-validation-patterns/orphan-audit-playbook.md`). Phase 01 redteam (shards 23–24) MUST mechanically grep for missing call sites.

## 6. Tier 2 / Tier 3 test surface

Per `rules/testing.md` and `01-runtime-swap-contract.md` §7 + §10, Phase 01 test surface is:

### 6.1 Tier 2 (real-infrastructure) tests Phase 01 ships

- `tests/integration/test_envoy_runtime_kailash_py_adapter.py` — exercises every byte-identical method on `KailashPyRuntime` against a real kailash-py install + real SQLite + real Ed25519 keypair; asserts within-runtime determinism (per §4.3) — same input, same output across instances.
- `tests/integration/test_envoy_runtime_get_runtime_returns_kailash_py.py` — Phase 01 lock-in: `get_runtime()` always returns `KailashPyRuntime` while `RS_BINDINGS_ENABLED == False`.
- `tests/integration/test_envoy_runtime_rs_bindings_blocked_in_phase01.py` — instantiating `KailashRsBindingsRuntime` directly (bypassing `get_runtime`) raises `RsBindingsNotAvailableInPhase01Error`.
- Per primitive (shards 4–17): each primitive's Tier 2 wiring test (per `rules/facade-manager-detection.md` MUST Rule 2 naming convention) exercises the runtime methods it consumes end-to-end. These are co-owned by the primitive's shard, not this shard, but they ARE this shard's orphan-detection coverage per §5.3.

### 6.2 Tier 3 (E2E) tests Phase 01 ships

- `tests/e2e/test_envoy_runtime_e1_through_e7_kailash_py.py` — runs the full E1–E7 conformance corpus (132 vectors per `01-runtime-swap-contract.md` §4.2) against `KailashPyRuntime`. Phase 01 acceptance: 132/132 pass. This is the Phase 01 row of `specs/runtime-abstraction.md` §Security gates per phase ("E1–E7 vectors pass").

### 6.3 Tier 2 / Tier 3 tests Phase 02 entry will run (NOT Phase 01)

- `tests/integration/test_byte_identity_cross_runtime.py` — every byte-identical method produces identical bytes from kailash-py vs kailash-rs-bindings. Phase 02 RELEASE_BLOCKER per `01-runtime-swap-contract.md` §8.
- `tests/integration/test_semantic_equivalence_cross_runtime.py` — semantically-equivalent methods produce equivalent verdicts under BET-6 (Phase 03 harness lands; Phase 02 enforces structured payload byte-identity only).
- N1–N6 conformance vector runner (kailash-py side closed via kailash-py#605 closure on 2026-04-25; rs side re-verify at Phase 02 entry per `03-kailash-py-mvp-readiness.md` §6).

### 6.4 Phase 01 conformance-runner stub

Per `01-runtime-swap-contract.md` §7.1, the kailash-py runner already lives at `tests/conformance/runner_py.py`. Phase 01 ships:

- The runner file itself (this shard authors it — it IS Envoy-new-code).
- The `cross_runtime_comparator.py` (§7.3) authored but DEGRADED to "single-runtime mode" — emits a `cross-runtime-verdict.json` with `runtime_versions.kailash-rs-bindings: "phase-02-deferred"` and `verdict: "PHASE_01_KAILASH_PY_ONLY"`. Phase 02 entry flips the comparator to true cross-runtime mode.

Authoring the comparator in single-runtime form during Phase 01 IS Phase 02 readiness — the comparator's structure is non-trivial, and deferring it to "we'll write it when Rust binding ships" is exactly the failure mode `rules/orphan-detection.md` §Phase 5.11 documents. The comparator MUST exist and MUST have a production exit code in Phase 01 even when only one runtime reports; flipping to two runtimes is a one-line change.

## 7. Frozen-spec ambiguity

Per `01-shard-plan.md` §4 failure-mode protocol: if a deep-dive surfaces a HIGH gap in the frozen spec, STOP and convene a MUST-Rule-5b sweep. Phase 00 redteam ran 6 rounds against `specs/runtime-abstraction.md`; this shard is checking whether implementation reasoning surfaces ambiguity that didn't appear at spec-level audit.

Re-reading the spec under implementation discipline surfaces five candidate ambiguities. None rise to HIGH; all are filed as Phase 01 build-time decisions that the spec does not constrain (which is correct — the spec is the contract, Envoy implementation chooses HOW to satisfy it).

1. **Protocol-vs-ABC encoding** — `specs/runtime-abstraction.md` §Abstract interface says "`KailashRuntime` (ABC)." Phase 01 implementation prefers PEP 544 `Protocol` (per §3.1 above) for structural-typing-of-already-typed-adapters reasons. This is NOT a spec contradiction — "ABC" in the spec is a generic abstract-interface noun, not a literal `abc.ABC` mandate; the spec's contract is on method-set + tier partition, not on Python encoding. **Disposition:** Phase 01 build chooses Protocol; documents the choice in shard 18's implementation; no spec edit required.

2. **`AssembledPrompt.rendered_bytes` field-by-field tier classification** — `specs/runtime-abstraction.md` §AssembledPrompt fixes the schema; `01-runtime-swap-contract.md` §5 says `prompt_assemble` is "byte-identical (canonical hash) + semantically-equivalent (rendered_bytes)." Implementation question: is `assembled_at` byte-identical (it is in the canonical-form hash inputs, per §6.1 wall-clock-timestamp tolerance band)? **Disposition:** `assembled_at` is excluded from canonical form (general spec-wide convention per `specs/ledger.md` and `01-runtime-swap-contract.md` §6.1); `runtime_signature_hex` is byte-identical because Ed25519 over canonical form is deterministic. Implementation captures this in `envoy.runtime.types.AssembledPrompt.__hash__` definition. No spec edit required.

3. **Feature flag for kailash-rs-bindings adapter slot** — `specs/runtime-abstraction.md` does not specify HOW Phase 01 deferred-slot semantics work; `rules/zero-tolerance.md` Rule 2 forbids `NotImplementedError` in production. The reconciliation in §3.3 above (feature flag + typed exception, no `NotImplementedError` reaches production) is an implementation discipline; the spec is silent on it. **Disposition:** Phase 01 build documents the discipline in `envoy/runtime/feature_flags.py` and `envoy/runtime/adapters/kailash_rs_bindings.py`; no spec edit required.

4. **`tool-call timing metadata` promotion candidacy** — `specs/runtime-abstraction.md` §Open questions §5 lists this as an open question. The promotion question (semantically-equivalent → byte-identical) is a Phase 02+ concern. **Disposition:** Phase 01 implementation marks the surface `@semantically_equivalent` (matching the spec's current partition) and notes the open question in a code comment; no Phase 01 action required.

5. **N3 + N6 corpus filling cadence** — `specs/runtime-abstraction.md` §Open questions §1 lists 10 + 10 vectors as placeholders; `01-runtime-swap-contract.md` §4.2 carries the same numbers. Phase 01 acceptance cites E1–E7 (which are fully populated per the v3 conformance plan), not N1–N6 (which are Foundation Phase-02 cadence). **Disposition:** Phase 01 implementation does not depend on N-vector corpus completeness; the runner is written to consume whatever corpus the Foundation publishes when it lands. No Phase 01 spec edit required.

**No HIGH spec ambiguity surfaces. All five candidate ambiguities are implementation-discipline questions, not spec-contract gaps. Per `01-shard-plan.md` §4 protocol, no MUST-Rule-5b sweep is convened.**

## 8. Cross-references

- Source spec: `specs/runtime-abstraction.md` (FROZEN v1) §Abstract interface, §Contract partition (BET-6), §Conformance vectors N1–N6 decoded, §Runtime device key, §Security gates per phase, §Test location, §Open questions
- Phase 00 conformance plan (the cross-runtime contract): `workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md` §1 (operational definition), §2 (two-tier contract), §3 (vector format), §4 (corpus), §5 (per-method tier table), §6 (tolerance bands), §7 (runner contract), §8 (CI gate)
- Distribution spec (runtime selection): `specs/distribution.md` §First-run flow (Phase 02), §Phase 01 distribution (kailash-py sole runtime)
- ADR-0001: `DECISIONS.md` §3 (runtime architecture; conformance vectors at every release gate)
- ADR-0009: `DECISIONS.md` §276 (runtime-pluggability sub-item 7 — conformance contract)
- Phase 01 inheritance: `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md` §2.2 (frozen ADR bindings) + §6 invariant 4 (frozen-redteam-output)
- Phase 01 readiness: `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` §3 row 15 (Runtime abstraction stub) + §5 (verification protocol)
- Phase 01 objectives: `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` §3 cross-cutting deliverable "kailash-runtime abstract interface stub", §EC-9 (independent verifier — exception to import discipline)
- Sharding plan: `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` §2 shards 4–17 (per-primitive integration table); §4 (failure-mode protocol)
- Methodology trap: `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` (cite-don't-re-derive discipline)
- Capacity rule: `.claude/rules/autonomous-execution.md` §Per-Session Capacity Budget (this shard within budget: 1 abstract interface, ~6 invariants, ~3 cross-spec hops)
- Specs authority: `.claude/rules/specs-authority.md` MUST Rule 5b (spec-edit re-derivation; this shard does NOT edit specs)
- Orphan detection: `.claude/rules/orphan-detection.md` MUST Rule 1 (production call site requirement; §5.3 above), playbook reference `skills/16-validation-patterns/orphan-audit-playbook.md`
- Facade manager detection: `.claude/rules/facade-manager-detection.md` MUST Rule 2 (Tier 2 test naming convention; §6.1 above)
- Zero tolerance: `.claude/rules/zero-tolerance.md` Rule 2 (no `NotImplementedError` in production; §3.3 reconciliation), Rule 4 (no SDK workarounds; §5.1 import discipline), Rule 6 (implement fully; full method-set on Protocol per §3.1)
- Testing: `.claude/rules/testing.md` Tier 2 / Tier 3 + Test-skip triage (§6 above)

---

## Summary (one paragraph for parent)

(a) **Contract-partition shape:** the spec partition lifts directly from `specs/runtime-abstraction.md` §Contract partition (BET-6) + the per-method table in `01-runtime-swap-contract.md` §5 — byte-identical methods are canonical-form / hash-chain / Ed25519-signing / set-equality / integer-arithmetic / structural-aggregation surfaces (24 method-or-method-component slots), semantically-equivalent methods are LLM-rendered text surfaces (5 method-component slots: `classifier_invoke.explanation`, `grant_moment_surface.prompt_text`, `prompt_assemble.rendered_bytes`, `tool_output_sanitize.text_for_user`, tool-call timing metadata); several methods (`prompt_assemble`, `tool_output_sanitize`, `grant_moment_surface`) split internally. (b) **Abstract-interface surface:** Envoy authors three modules — `envoy.runtime` (PEP 544 `Protocol` `KailashRuntime` with every spec method, decorated `@byte_identical` or `@semantically_equivalent` and carrying `__conformance_vectors__`), `envoy.runtime.adapters.kailash_py` (production Phase 01 adapter, forwards to `kailash` for 12 of 13 surfaces and to the Envoy-new Ledger writer for the `#596 TieredAuditDispatcher` gap), and `envoy.runtime.adapters.kailash_rs_bindings` (Phase 02 deferred slot, structurally present but feature-flagged off and gated by typed `RsBindingsNotAvailableInPhase01Error`); every primitive imports `from envoy.runtime import get_runtime`, never from `kailash` directly, which is the Phase 02 mechanicality lock. (c) **HIGH spec ambiguity:** none — five candidate ambiguities surface during implementation reasoning (Protocol-vs-ABC encoding, AssembledPrompt field-tier breakdown, feature-flag discipline for the Phase 02 slot, tool-call-timing promotion candidacy, N3+N6 corpus cadence) and all five are dispositioned as implementation-discipline questions the spec correctly leaves to the build, NOT spec contract gaps; per `01-shard-plan.md` §4 no MUST-Rule-5b sweep convenes. (d) **BETs depending on this contract being correct:** BET-6 (cross-runtime contract partition) directly — the partition encoding in §4.2 IS what Phase 02 cross-runtime conformance gates against; BET-3 (sovereignty / runtime pluggability) depends on Phase 02 mechanicality, which depends on the Phase 01 abstract interface being complete (every spec method on the Protocol per `rules/zero-tolerance.md` Rule 6) and the import-through-`envoy.runtime` discipline being enforced in every primitive shard 4–17 with at least 12 production call sites for orphan-detection §1 compliance.
