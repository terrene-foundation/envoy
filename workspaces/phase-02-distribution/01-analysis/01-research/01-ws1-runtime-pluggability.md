# WS-1 — Runtime Pluggability (Phase-02 implementation architecture)

**Scope.** Phase-00 froze the architecture (`DECISIONS.md` ADR-0001, ADR-0009);
Phase-01 shipped the abstract `KailashRuntime` Protocol with ONE wired impl
(`kailash-py`) plus a feature-flag-gated structural slot for the second
(`kailash-rs-bindings`). Phase-02 WS-1 wires the second runtime, builds the
cross-runtime conformance harness, and ships the first-run picker +
`envoy runtime switch` + attestation-on-switch. This is implementation
architecture, not product re-derivation.

**Grounding (real code, read this session).**

- Abstract interface: `envoy/runtime/protocol.py:33` (`@runtime_checkable class
KailashRuntime(Protocol)`, 30 methods across 9 groups, `__all__` at `:251`).
- Reference impl: `envoy/runtime/adapters/kailash_py.py:74` (`KailashPyRuntime`,
  forward-or-typed-error per method).
- The Phase-01 stub / seam: `envoy/runtime/adapters/kailash_rs_bindings.py:46`
  (`KailashRsBindingsRuntime`) — every method body raises
  `Phase02SubstrateNotWiredError` (`envoy/runtime/errors.py:91`); constructor
  raises `RsBindingsNotAvailableInPhase01Error` (`errors.py:80`) while the flag
  is False.
- The flag: `envoy/runtime/feature_flags.py:21` (`RS_BINDINGS_ENABLED: bool =
False`).
- The single substitution site: `envoy/runtime/selection.py:37`
  (`get_runtime(family=None)`).
- Wiring test (sole in-package consumer): `tests/tier2/test_envoy_runtime_wiring.py`.

> **Citation correction (brief-verification, per `rules/agents.md` § Parallel
> Brief-Claim Verification).** The brief cites
> `specs/mvp-build-sequence.md:202` as "the `RuntimeBackendNotWired`
> feature-flagged stub Phase-01 shipped." TWO inaccuracies, both verified by
> `grep`: (1) `mvp-build-sequence.md:202` describes the **kailash-rs-bindings
> runtime adapter** Phase-02 hook, but the line says "feature-flagged empty
> module raising `RuntimeBackendNotWired`"; (2) **no symbol named
> `RuntimeBackendNotWired` exists in the source tree** (`grep -rn
RuntimeBackendNotWired --include=*.py .` → 0 hits). The shipped stub raises
> `Phase02SubstrateNotWiredError` (per-method) and
> `RsBindingsNotAvailableInPhase01Error` (constructor). The spec line is itself
> stale relative to the code it describes; flagged in § Spec gaps. The build
> discussion below is grounded in the ACTUAL shipped symbols.

---

## Q1 — Cross-runtime conformance harness (BET-6) — the phase's highest correctness risk

### 1.1 What "byte-identical" vs "semantically-equivalent" actually means

The spec partitions the 30 Protocol methods into two contract tiers
(`specs/runtime-abstraction.md:139-143` § Contract partition):

- **Byte-identical (the spec/crypto path).** For the SAME logical input, both
  runtimes MUST produce the SAME output BYTES (or, where the output is a
  structured object, the same canonical-hash of that object). Members:
  `envelope_canonical_form`, `trust_sign`, `delegation_id` hashing, the ledger
  hash chain (`ledger_append` → `entry_id`/`parent_hash`), `cascade_revoke` SET
  equality, `envelope_intersect`, the subset-proof
  `runtime_verification_signature`, `head_commitment`. The load-bearing
  invariant is `rendered_canonical_hash` equality
  (`runtime-abstraction.md:123`): tokenization details of non-canonical fields
  (whitespace, comment markers) MAY differ, but the JCS-RFC8785 + NFC canonical
  hash MUST match. This is the strongest form of source-isolation — the same
  invariant the independent verifier reuses (`specs/independent-verifier.md:171,
198-200`).
- **Semantically-equivalent (the LLM/dispatch path).** For the SAME input, the
  two runtimes MAY produce DIFFERENT bytes, but the outputs MUST agree on
  meaning. Members (`runtime-abstraction.md:143`): agent LLM responses, Grant
  Moment prompt text, tool-call timing metadata. Verification here CANNOT be
  byte-equality; it MUST be **probe-driven** per
  `rules/probe-driven-verification.md` MUST-1 — a structured judge with a
  JSON-schema answer + deterministic scoring, never regex/keyword scoring of
  prose.

**Design consequence:** the harness needs TWO scoring engines, selected per
method by the method's contract tier. The Protocol does NOT yet carry the tier
as machine-readable metadata — `protocol.py:13` explicitly defers the
`@byte_identical` / `@semantically_equivalent` decorators and the
`__contract_tier__` machinery to a follow-up shard. **WS-1 MUST land that
metadata first** (see § 1.4), because without it the harness has no mechanical
way to know which scorer to apply, and a hand-maintained method→tier map drifts
from the Protocol the moment a method is added.

### 1.2 The vector corpora: N1–N6, E1–E7

Two corpora, decoded at `runtime-abstraction.md:145-154` (N) and `:188-196` (E):

- **N1–N6** (70 vectors total): cross-SDK byte-identity gates inherited from the
  PACT N-vector pattern. N1 Knowledge Filter (10), N2 Envelope Cache 5-property
  invalidation (15), N3 structural-vs-semantic partition (10), N4 verdict
  rendering (10 — structured payload byte-identical, rendered text
  semantically-equivalent), N5 posture ceiling (15), N6 session-scoped cache
  fingerprint (10).
- **E1–E7** (Envoy-specific, ~120+ vectors): E1 envelope canonical JSON (67),
  E2 Delegation Record signing (20), E3 cascade revoke BFS/DFS set-equality
  (15), E4 cycle detection (15), E5 subset-proof adversarial (20), E6 two-phase
  orphan resolution, E7 ledger head-commitment monotonicity.

N3 and N4 are _mixed-tier within a single vector family_: N3 asserts that
structural-class checks NEVER invoke the classifier (byte-identical on
classification-only fixtures) while semantic-class checks always dispatch — so
the N3 scorer is byte-identity on the structural slice + dispatch-occurred on
the semantic slice. N4's structured payload is byte-identical but its rendered
text is semantically-equivalent. **The vector format MUST carry a per-field tier
tag, not just a per-vector one.**

### 1.3 ONE harness, both runtimes — the structural design

Recommended structure (a single pytest-collectable harness, parametrized over
the runtime under test):

```
tests/conformance/
  corpus/                      # the vectors — runtime-agnostic, committed static
    n/  n1.jsonl … n6.jsonl
    e/  e1.jsonl … e7.jsonl
  conftest.py                  # runtime fixtures: both adapters via get_runtime()
  test_byte_identical.py       # tier=byte_identical scorer
  test_semantic_equivalent.py  # tier=semantically_equivalent probe scorer
  scorers.py                   # byte_identity_scorer + semantic_probe_scorer
```

Each vector row is `{vector_id, method, tier, input, expected_canonical_hash?,
probe_schema_ref?}`. The harness loop is:

```python
@pytest.mark.parametrize("runtime", ["kailash-py", "kailash-rs-bindings"])
@pytest.mark.parametrize("vector", load_corpus("n1"), ids=lambda v: v["vector_id"])
def test_n1_knowledge_filter(runtime, vector):
    rt = get_runtime(family=runtime)            # selection.py:37 — the ONE seam
    out = invoke(rt, vector["method"], vector["input"])
    if vector["tier"] == "byte_identical":
        assert canonical_hash(out) == vector["expected_canonical_hash"]
    else:
        assert semantic_probe(out, schema=vector["probe_schema_ref"]).passed
```

The cross-runtime _equivalence_ gate runs the SAME vector through BOTH runtimes
and asserts agreement (byte-identical: hash equality between runtimes;
semantic: both pass the same probe schema). This is the BET-6 acceptance the
spec names at `runtime-abstraction.md:206` ("Phase 02: … BET-6 contract
parity; N1–N6 Python runner").

**Why one harness and not two:** because the corpus is runtime-agnostic (it
expresses _what the contract requires_, not _what a runtime produces_), the
SAME `expected_canonical_hash` proves `kailash-py == contract` AND
`kailash-rs-bindings == contract`, transitively proving the two runtimes equal.
This is exactly the lens-reuse the verifier spec describes
(`independent-verifier.md:198-200`): "the same vectors that prove `kailash-py`
== `kailash-rs-bindings` ALSO prove `envoy-producer` == `envoy-verifier`." WS-1
SHOULD source the E7 vectors from the shared corpus the verifier already pins
(`independent-verifier.md:200`, `tests/fixtures/conformance/e7/`) so there is
ONE E7 truth, not two.

### 1.4 Failure localization — the load-bearing design property

A conformance failure must answer THREE questions mechanically: _which method,
which vector, which field_. Design requirements:

1. **Per-vector IDs** (`ids=lambda v: v["vector_id"]`) so pytest's failure line
   names the exact vector (`test_n2_envelope_cache[kailash-rs-bindings-N2-007]`).
2. **Field-level diff on byte-identity failure.** The byte_identity_scorer MUST,
   on mismatch, emit the canonical-JSON of both sides and the first differing
   byte offset + JSON path — NOT just `assert a == b`. A bare equality assert on
   a 4KB canonical blob is unactionable; the field path ("differs at
   `entries[3].timestamp`: producer microsecond-padded, rs truncated") is the
   one-line fix instruction. This mirrors the verifier's mutation-battery
   localization (`independent-verifier.md:90`, "emit a typed error with the
   failing entry index").
3. **Probe evidence on semantic failure.** The semantic_probe_scorer returns the
   schema-valid judge answer (`{equivalent: bool, divergence_reason: str}`) per
   `probe-driven-verification.md` MUST-2, so a semantic failure says _why_ the
   two Grant Moment texts diverged, not just "not equal."
4. **Runtime axis in the test ID** so a failure that reproduces on BOTH runtimes
   (contract/corpus bug) is visually distinct from one that reproduces on only
   `kailash-rs-bindings` (the new impl is wrong).

**Highest-risk subtlety: cross-language canonicalization drift.** The
byte-identity contract lives or dies on JCS-RFC8785 + NFC + microsecond-padded
ISO-8601 + integer-microdollars being implemented identically in Rust and
Python. The verifier spec already pins these (`independent-verifier.md:163-171`)
and notes the cross-OS NFC drift risk (`:252`: "NFC behaves differently on
macOS HFS+ vs Linux ext4 vs Windows NTFS"). WS-1's harness MUST run the
byte-identity slice across the full OS matrix (`independent-verifier.md:248-251`:
macos-14, ubuntu-22.04/24.04, windows-2022) — a Rust runtime that canonicalizes
correctly on Linux but truncates a combining character on Windows NTFS is a
silent BET-6 falsifier that a single-OS run never catches.

### 1.5 Recommendation (Q1)

**Recommended: land the contract-tier metadata on the Protocol FIRST, then build
ONE parametrized harness with two pluggable scorers, sourcing E7 from the shared
verifier corpus, running the byte-identity slice on the full OS matrix.**

- _Pros:_ the tier metadata is the single source of truth for scorer selection
  (no drift-prone hand map); one harness means `kailash-py`-vs-contract and
  `kailash-rs-bindings`-vs-contract are the same code path (the substitution is
  `get_runtime(family=...)` and nothing else, honoring the
  `selection.py:6-9` "one seam" invariant); shared E7 corpus eliminates a second
  source of truth.
- _Cons (real):_ the tier-metadata shard is pure scaffolding with no
  user-visible output — it will feel like overhead, and a reviewer may push to
  "just hardcode the method→tier map and move on." Resisting that is the whole
  point: the hardcoded map is the drift vector. Second con: the OS-matrix run
  multiplies CI wall-clock by ~4; mitigate by gating the full matrix at the
  `/release` gate and running Linux-only on PR (per
  `rules/git.md` Pre-FIRST-Push parity, the byte-identity slice is the
  load-bearing one to pre-flight).

This is the phase's highest correctness risk; it is also the most
**shardable** — the corpus families (N1–N6, E1–E7) are independent and can be
verified by parallel deep-dive agents, but each _family_ is one shard's worth of
invariants, so size by family, not by "all vectors at once" (per
`rules/autonomous-execution.md` § Per-Session Capacity Budget).

---

## Q2 — Embedding strategy: PyO3 compile-time embed vs uv-managed subprocess

The frozen decision left this as an OPEN sub-decision (`DECISIONS.md:96` ADR-0001
§ Open sub-decisions: "Embedding strategy — PyO3 compile-time vs uv-managed
subprocess at runtime. Lean: uv-style for flexibility. Revisit Phase 02
`/analyze`"). The binary-size envelope is fixed: `<50 MB` desktop
(`specs/distribution.md:78-82`, CI-gated via
`tests/acceptance/phase_02/test_binary_size_under_50mb.py` across 5 targets),
with the embedded-interpreter cost pre-accepted at "+30–40 MB"
(`DECISIONS.md:97`).

The two options are NOT symmetric in what they embed. The product is a Python
application (`envoy`) that consumes a runtime adapter; the runtime is EITHER a
PyO3 `.so` loaded into the same Python process (`kailash-rs-bindings`, the
default per ADR-0001) OR pure Python (`kailash-py`, the opt-out). The embedding
question is about the _Python interpreter itself_ for the single-binary
distribution (`curl|sh`/brew/winget/cargo), not about the Rust core (which is
always a compiled `.so` regardless).

| Axis                       | PyO3 compile-time embed                                                                                                                                                      | uv-managed subprocess                                                                                                                       |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| What ships                 | One static binary: Rust launcher + embedded CPython (via `pyo3` + `python-build-standalone`) + the `.so` core, all in one file                                               | A thin Rust/shell launcher that, on first run, uses `uv` to materialize a managed CPython + the `envoy` wheel into a user-dir venv          |
| Binary size                | Full +30–40 MB interpreter counts against the 50 MB cap on EVERY target                                                                                                      | Launcher is ~MB-scale; the interpreter is fetched, NOT in the shipped binary — trivially under 50 MB                                        |
| Startup latency            | Cold-start is process-spawn only (interpreter is in-image); fast, deterministic                                                                                              | First-run pays a network fetch + venv build (seconds-to-minutes); subsequent runs are warm                                                  |
| Offline / atomic install   | Yes — self-contained, works air-gapped (the offline-first-run requirement at `distribution.md:18,127`)                                                                       | NO — first run needs network for the `uv` fetch unless the wheel+interpreter are pre-bundled, which collapses it back toward the embed cost |
| Packaging complexity       | Higher build-side: cross-compile CPython for 5 targets (`distribution.md:82`), reproducible-build the whole image (`distribution.md:39-41`)                                  | Lower build-side, higher runtime-side: `uv` becomes a runtime dependency whose own supply chain must be N=3-mirror-verified                 |
| Opt-out-to-pure-Python     | The `.so` is embedded but `kailash-py` is still selectable — the picker flips `get_runtime(family="kailash-py")` and the `.so` simply goes unused (dead weight in the image) | The opt-out is cleaner: `uv` just resolves the `kailash-py` wheel instead; no dead binary weight                                            |
| Reproducible-build surface | Larger attestation target (whole image), but ONE artifact to attest — cleaner T-060 story                                                                                    | The attestation must cover the launcher AND the `uv`-resolved closure; more moving parts to reproduce                                       |
| Threat-model fit           | T-060 (binary poisoning) defense is one hash over one artifact (`distribution.md:33` "hash match across ≥2 mirrors")                                                         | T-060 must extend to the `uv`-fetched closure; the fetched interpreter is a second poisoning surface                                        |

### Recommendation (Q2)

**Recommended: PyO3 compile-time embed for the Phase-02 single-binary desktop
distribution, with `kailash-py` remaining a selectable in-image opt-out — NOT
the uv-subprocess lean the frozen ADR tentatively recorded.**

Plain-language framing: ship ONE file that already contains everything Envoy
needs to run, so a user can install it on a laptop with no internet and it just
works; the trade is that the file is ~30–40 MB bigger.

- _Pros:_ satisfies the offline-first-run requirement
  (`distribution.md:18,127`) that the sovereignty narrative depends on
  (`DECISIONS.md:73` "no system Python dependency"); gives the cleanest T-060
  reproducible-build story (one artifact, one hash, the N=3 mirror match at
  `distribution.md:33` is over a single image); makes install atomic and
  rollback-as-file-swap simple (`distribution.md:50` 30-day window); the +30–40
  MB is already pre-accepted and the 50 MB cap holds with strip-discipline
  (`distribution.md:84`, debug symbols ship separately).
- _Cons (real, not glossed):_ the build matrix is heavier — cross-compiling
  CPython for 5 targets is genuine packaging work and a recurring
  release-cycle cost; the embedded `.so` is dead weight (~the binary still
  carries the Rust core even for users who opt out to `kailash-py`), so opt-out
  users pay size they don't use; and reproducible-building a whole interpreter
  image is a larger attestation target than a thin launcher. The frozen ADR's
  uv-lean was motivated by "flexibility," and that flexibility is real for the
  _developer_ install path — so the recommendation is **scoped to the shipped
  single-binary distribution only**: `pip install envoy-agent` / `pipx`
  (the Phase-01 surface, `distribution.md:15`) and `cargo install`
  developer-paths can continue to resolve the interpreter via the normal
  toolchain; the embed is specifically for the `curl|sh`/brew/winget
  end-user binaries where offline-atomic-install is the requirement.

The decision is reversible at low cost (it changes the build pipeline, not the
runtime contract — `get_runtime()` is identical under both), so this is a
"recommend and proceed, revisit if the 50 MB cap is breached on the largest
target" disposition, not a blocking gate.

---

## Q3 — Second-impl wiring: how `kailash-rs-bindings` slots behind the frozen interface

### 3.1 What Phase-01 left as the seam (verified in source)

Phase-01 deliberately engineered the second-impl slot so Phase-02 is a
**one-flag-flip + per-method-body-fill**, NOT a refactor
(`kailash_rs_bindings.py:5-8`). The seam has four parts:

1. **The structural file already exists** —
   `envoy/runtime/adapters/kailash_rs_bindings.py:46` defines
   `KailashRsBindingsRuntime` with ALL 30 Protocol methods present (so the
   Protocol shape is auditable before Phase-02 begins). Each body raises
   `Phase02SubstrateNotWiredError` (`errors.py:91`) — a typed, grep-able error,
   NOT `NotImplementedError` (per `rules/zero-tolerance.md` Rule 2; the
   reconciliation is documented at `kailash_rs_bindings.py:17-20`).
2. **The constructor is flag-gated** — `__init__` raises
   `RsBindingsNotAvailableInPhase01Error` (`errors.py:80`) while
   `RS_BINDINGS_ENABLED == False` (`kailash_rs_bindings.py:56-58`), so in
   Phase-01 no method body is even reachable.
3. **The single substitution site** — `get_runtime(family=...)` at
   `selection.py:37` is the ONLY place any primitive obtains a runtime
   (`selection.py:6-9`: "no primitive holds a hard reference to a specific
   adapter class"). `selection.py:54-69` already routes
   `family="kailash-rs-bindings"` to the rs adapter once the flag is True. This
   is the mechanicality lock: nothing else in the codebase imports an adapter
   class directly (the wiring test imports them, but production code goes
   through `get_runtime`).
4. **The flag** — `feature_flags.py:21`, one module-level constant, read-only at
   import. Phase-02 flips it (`feature_flags.py:12-13`).

### 3.2 The actual Phase-02 wiring work

Flipping the flag with empty bodies surfaces `Phase02SubstrateNotWiredError`
from every method "by design" (`feature_flags.py:18-20`) — a loud regression
detector, not silent no-ops. The real work per method is to replace the raised
error with a forward to the Rust binding's equivalent, exactly mirroring how
`KailashPyRuntime` forwards (`kailash_py.py:8-19`):

- **Byte-identical methods** (`trust_sign`, `envelope_canonical_form`,
  `ledger_append`, `head_commitment`, etc.) forward to the Rust core's
  canonical-JSON + Ed25519 surface. The boundary discipline the py-adapter
  already documents (`kailash_py.py:28-42`: `sign` returns a hex _string_,
  Protocol declares `-> bytes`, encode at the boundary) applies symmetrically —
  the rs adapter must satisfy the SAME `-> bytes` contract, and the conformance
  harness (Q1) is what proves it produces the SAME bytes.
- **Async methods** (`startup`, `shutdown`, `ledger_append`, `ledger_query`,
  `ledger_verify_chain`, `head_commitment` — note these are `async def` in the
  Protocol, `protocol.py:53,138-156`) must be wired so the PyO3 binding's
  sync/async boundary is bridged correctly. The py-adapter already flags a
  sync/async mismatch on `trust_cascade_revoke` (`kailash_py.py:197-231`: the
  Protocol declares it SYNC); the rs adapter must hold the SAME sync/async shape
  per method or `isinstance(adapter, KailashRuntime)` structural typing
  (`protocol.py:44`) silently passes while a call awaits a non-coroutine.
- **Device-key signing** (`runtime_sign`/`runtime_verify`,
  `protocol.py:201-209`): Phase-02 is where Secure Enclave / TPM enter
  (`protocol.py:203-204`, `kailash_py.py:139-141` notes py is software-fallback
  only). The rs binding owns the platform attestation surface
  (`runtime-abstraction.md:175-178` `device_attestation`).

### 3.3 The `isinstance`-passes-but-wrong trap (design caution)

Because the Protocol is `@runtime_checkable` (`protocol.py:33,44`), an rs adapter
with all 30 method _names_ present passes `isinstance(adapter,
KailashRuntime)` even if a body is wrong, an arg shape diverges, or a sync method
is implemented async. Structural-typing is NOT behavioral verification. The
conformance harness (Q1) is the ONLY behavioral gate; the `isinstance` check is
necessary-but-insufficient. WS-1 MUST NOT treat "the rs adapter satisfies the
Protocol" as a completion signal — that's the
`rules/zero-tolerance.md` Rule 3d failure-mode (structural guard resolves True
on a branch that doesn't actually perform the contract).

### 3.4 Recommendation (Q3)

**Recommended: wire the rs adapter method-by-method in conformance-family order
(byte-identical methods first, since those have a mechanical pass/fail gate),
flip `RS_BINDINGS_ENABLED` only after the byte-identical slice is green on BOTH
runtimes, and keep `kailash-py` as the production default until the FULL N1–N6 +
E1–E7 corpus passes.**

- _Pros:_ the byte-identical methods have a deterministic feedback loop (the
  harness), so they qualify for the larger shard budget per
  `rules/autonomous-execution.md` § Feedback Loops Multiply Capacity; wiring
  them first means the flag-flip is gated on a green mechanical signal, not a
  judgment call. Keeping py as default until full-corpus-green means an
  rs-adapter bug never reaches users mid-wiring.
- _Cons:_ the semantic-tier methods (classifier, Grant Moment text) can't be
  byte-gated, so they need the probe harness which has non-deterministic
  failure modes (occasional judge misclassification) — those shards must use the
  base budget, not the multiplied one. Second con: keeping py as default longer
  means the performance USP (the reason rs is the default) lands later in
  Phase-02 than a "flip early" approach — but flipping early ships an unverified
  default, which is the worse trade.

---

## Q4 — First-run picker + `envoy runtime switch` + attestation-on-switch

### 4.1 The picker (first-run UX state)

`specs/runtime-abstraction.md:198-200` § Runtime picker: first-run picker is
"kailash-rs-bindings default vs kailash-py opt-in," surfaced as ONE question
(`DECISIONS.md:47`: "Run Envoy with Rust acceleration (free, faster) or the
pure-Python Foundation runtime (free, fully open-source, forkable, somewhat
slower)? Default is Rust-accelerated. Opt-out is one keystroke"). In the
Phase-02 first-run flow it is the FIRST step (`distribution.md:43-45`: Runtime
picker → Model picker → Boundary Conversation → Shamir ritual → Visible secret
setup).

The picker's output is consumed by `get_runtime()` —
`selection.py:21-24,45-46` already declares "Phase 02: family resolution shifts
to read the first-run picker output per `specs/distribution.md` § First-run
flow." So the implementation seam is: the picker writes a runtime-choice config
(family + chosen-at timestamp + chosen-by Genesis), and `get_runtime(family=None)`
defaults to reading that config instead of the hardcoded `"kailash-py"` at
`selection.py:51`.

There is a real model precedent already in-tree: `envoy/model/byom_picker.py`
(the BYOM model picker, ADR-0006) — same first-launch-picker shape, writes
choice to config. WS-1 SHOULD mirror its structure (a `runtime_picker.py` that
writes a `runtime-choice` config + emits the selection event), NOT invent a new
pattern.

### 4.2 `envoy runtime switch` — the CLI surface

Today there is NO `runtime` CLI command — the CLI is a single click group
(`envoy/cli/main.py:34` `@click.group()`); model/posture/etc. are subcommands.
WS-1 adds an `envoy runtime` subgroup with at least `switch`, `attest`, and a
status/show. `runtime-abstraction.md:162` names `envoy runtime attest`
(on-demand attestation) and `:200` names `envoy runtime switch`.

**Switch requires THREE things** (`runtime-abstraction.md:200`):
(a) **passphrase unlock (not warm)** — the switch is a privileged operation, so
the Trust Vault must be cold-unlocked, not relying on a warm session key;
(b) a **Genesis-signed `runtime_switch` Ledger entry** (lower-snake-case
canonical naming per V-05, `runtime-abstraction.md:200`); (c)
**runtime-attestation verification of the target** runtime BEFORE the switch
record is written.

### 4.3 Attestation-on-switch — the security record (T-015, T-060)

The `RuntimeAttestation` Ledger entry (`runtime-abstraction.md:156-186`) is the
security receipt. It is emitted at THREE moments (`:158-162`): every
`startup()`, every `runtime_switch` (BEFORE the switch record is written — the
target is verified via its attestation), and on-demand via `envoy runtime
attest`. The schema (`:164-185`) binds `runtime_identity` (family, version,
**binary_hash**, device_bound_pubkey_hex, algorithm_identifier) +
`device_attestation` (secure_enclave/tpm/software + attestation_hash) +
`reproducible_build_refs[]`, signed by the `runtime_device_key`.

- **T-060 (runtime-binary-poisoning) defense on switch:** before switching TO
  `kailash-rs-bindings`, the switch flow runs the target's attestation and
  verifies `binary_hash` matches the expected reproducible-build manifest
  (`distribution.md:39-41` reproducible-build stream;
  `runtime-abstraction.md:160` "attests the runtime's binary hash … matches the
  expected manifest"). A poisoned binary fails the hash-match and the switch is
  refused — same fail-closed shape as `MirrorSignatureMismatchError` /
  `ReproducibleBuildFailedError` (`distribution.md:94-95`). The Phase-01
  attestation surface is a stub (`runtime_identity()` returns
  `"binary_hash": "sha256:phase-01-software-fallback"`, `kailash_py.py:148`;
  ledger export emits `runtime_attestation: {}`, `export.py:333-338`) — WS-1
  fills these with the real reproducible-build hash.
- **T-015 (envelope re-read checkpoint) on switch:** a runtime switch changes the
  `algorithm_identifier` and the device-key path, which is exactly an N2
  envelope-cache invalidation trigger (`runtime-abstraction.md:150`: cache MUST
  invalidate on `algorithm_identifier` change). The switch flow MUST force an
  envelope re-read checkpoint (`envelope_re_read_checkpoint`,
  `protocol.py:110`) so no envelope pinned under the old runtime's
  algorithm-identifier survives the switch — the system-prompt pin
  (`runtime-abstraction.md:125` `envelope_pin.envelope_hash`) is re-anchored
  against the new runtime. This is the T-015 defense surface the spec names at
  `:41,125`.

### 4.4 The UX state machine (switch)

```
envoy runtime switch <target>
  → cold passphrase unlock (Vault)                    [refuse if warm-only]
  → attest(target): RuntimeAttestation emitted + binary_hash vs manifest
        ↳ hash mismatch / revoked key → REFUSE (T-060, fail-closed)
  → envelope_re_read_checkpoint (force N2 cache invalidation)   [T-015]
  → Genesis-signed `runtime_switch` Ledger entry written
  → get_runtime() default now resolves to <target>
  → confirm to user: "Active runtime: <target>. Pure-Python alternative
    always available via `envoy runtime switch kailash-py`." [ADR-0009:4
    transparent disclosure, no hidden defaults]
```

### 4.5 Recommendation (Q4)

**Recommended: add an `envoy runtime` click subgroup (`switch`/`attest`/`show`)
that mirrors the `byom_picker` config-write pattern; gate `switch` on the
three-part contract (cold-unlock + target attestation + Genesis-signed
`runtime_switch` entry) with attestation-BEFORE-switch-record ordering, and
force an envelope re-read checkpoint as part of the switch transaction.**

- _Pros:_ reuses an in-tree picker precedent (lower risk than a novel pattern);
  the attestation-before-record ordering means a poisoned target can never get
  a switch record written (fail-closed, T-060); forcing the re-read checkpoint
  closes the T-015 pinned-envelope-survives-switch hole mechanically rather than
  by convention; transparent confirmation copy satisfies ADR-0009 item 4
  (no hidden defaults).
- _Cons:_ requiring a COLD passphrase unlock for every switch is friction — a
  user toggling runtimes to benchmark pays the unlock each time; this is the
  correct trade (the switch IS a trust-root-adjacent operation) but it WILL
  generate "why do I have to type my passphrase again" friction, so the
  confirmation copy must explain _why_ (it's signing a Genesis record). Second
  con: the attestation step adds latency to the switch (a hash-verify against
  the manifest + an N=3 mirror cross-check per `distribution.md:33`) — acceptable
  for a rare operation, but it means `switch` is not instant.

---

## Spec gaps identified (Phase-02 implementation detail the frozen specs DON'T cover)

These are ADDITIONS surfaced by grounding the design in real code — **no spec
edits made**; per `rules/spec-accuracy.md` these belong in todos/analysis, not
inline in `specs/`.

1. **Two distinct `RuntimeIdentity` shapes; spec defines only one.** The
   abstract-interface `RuntimeIdentity` is 5-field (`runtime_family, version,
binary_hash, device_bound_pubkey_hex, algorithm_identifier`,
   `runtime-abstraction.md:93,95`) and is what the adapter returns
   (`kailash_py.py:142-151`). But the SHIPPED `envoy.ledger.head.RuntimeIdentity`
   (`envoy/ledger/head.py:77`) is 3-field (`device_id, signing_key_id,
algorithm_identifier`) — a different dataclass used by the
   `HaltedByRollback` record. WS-1 wiring of `RuntimeAttestation` must reconcile
   which `RuntimeIdentity` the attestation entry uses; the spec's attestation
   schema (`:166-174`) uses the 5-field form, but the ledger module already owns
   a 3-field type by the same name. **Gap: the spec does not name the
   relationship between the two; the conformance harness needs a canonical
   `RuntimeIdentity` for the attestation byte-identity vector.**

2. **No machine-readable contract-tier metadata on the Protocol.**
   `protocol.py:13-16` explicitly defers `@byte_identical` /
   `@semantically_equivalent` decorators and `__conformance_vectors__`. The spec
   states the partition in prose (`runtime-abstraction.md:139-143`) but provides
   no mechanism for the harness to read a method's tier programmatically. **Gap:
   WS-1 must define the metadata format (decorator vs `__contract_tier__` dict);
   the spec assumes a runner exists but doesn't specify how it learns the tier.**

3. **Mixed-tier-within-a-vector (N3, N4) has no field-tier schema.** N3 and N4
   are byte-identical on one slice and semantically-equivalent on another
   (`runtime-abstraction.md:151-152`). The vector format the spec implies (one
   tier per vector) cannot express this. **Gap: the corpus row schema needs a
   per-field tier tag; the spec doesn't define the vector wire format at all.**

4. **`runtime_switch` Ledger entry schema is named but not specified.**
   `runtime-abstraction.md:200` names the entry (`runtime_switch`,
   lower-snake-case) and says it's Genesis-signed, but the field schema is owned
   by `specs/ledger.md` § Entry types (cross-ref only). **Gap: WS-1 needs the
   concrete `runtime_switch` entry fields (from_family, to_family,
   target_attestation_hash, re_read_checkpoint_result, signed_by) — not
   enumerated in any spec read this session.**

5. **Stale spec citation:** `specs/mvp-build-sequence.md:202` describes the stub
   as raising `RuntimeBackendNotWired`, a symbol that does not exist
   (the code raises `Phase02SubstrateNotWiredError` /
   `RsBindingsNotAvailableInPhase01Error`). Per `rules/spec-accuracy.md` MUST-1
   this is a phantom citation. **Gap/correction: the spec line should be updated
   to the real symbols when `specs/` is next touched for a code-landing reason
   (not in this analysis).**

6. **Picker config wire format undefined.** `selection.py:21-24` says Phase-02
   reads "the first-run picker output per `specs/distribution.md` § First-run
   flow," but `distribution.md:43-45` only lists the picker as a flow STEP — no
   config-file schema (path, fields, signing). **Gap: WS-1 must define the
   runtime-choice config schema; the `byom_picker` `.env`-write pattern is the
   in-tree precedent to mirror.**

7. **Embedded-`.so`-as-dead-weight under opt-out is unaddressed.** ADR-0001's
   size accounting (`+30–40 MB`, `DECISIONS.md:97`) assumes the embed is used;
   it does not account for opt-out users carrying the unused Rust `.so`. **Gap:
   no spec states whether the opt-out distribution is a separate
   pure-Python build target or the same image with dead weight.**

---

## Open questions for `/todos`

1. **Contract-tier metadata format** — decorator (`@byte_identical`) vs class
   attribute (`__contract_tier__: dict[str, Tier]`) vs sidecar manifest? This
   blocks the harness (Q1) and is the first shard. (Recommend decorator: it
   co-locates the tier with the method signature, so adding a method without a
   tier is a loud authoring error.)

2. **E7 corpus single-source** — git-submodule-pin the shared verifier corpus
   (`independent-verifier.md:200,275` names this as TBD) or vendor a versioned
   fixture package? Decide before the harness sources E7, to avoid two E7
   truths.

3. **`RuntimeIdentity` reconciliation (gap 1)** — does the 5-field
   attestation `RuntimeIdentity` subsume the 3-field ledger one, or do they
   stay distinct with a documented mapping? This gates the
   `RuntimeAttestation`-entry byte-identity vector.

4. **Embed scope (Q2)** — confirm the embed is single-binary-distribution-only
   (curl|sh/brew/winget) with `pip`/`cargo install` developer paths resolving
   the interpreter normally; confirm opt-out distribution disposition (gap 7).

5. **Switch friction (Q4)** — is COLD passphrase unlock required on EVERY
   switch, or is a warm-session switch acceptable for a benchmark/toggle use
   case with a re-attestation-only (no re-sign) fast path? The spec says cold
   (`runtime-abstraction.md:200`); confirm no fast-path carve-out is wanted.

6. **Sharding the rs-adapter wiring** — by conformance family
   (byte-identical-first) per Q3; confirm the 30 methods partition into
   feedback-loop-backed shards (byte-identical, multiplied budget) vs
   base-budget shards (semantic/probe). Size at `/todos`, not `/implement`
   (`rules/autonomous-execution.md` § MUST NOT defer sharding).

7. **N3/N4 mixed-tier vector schema (gap 3)** — define the per-field tier tag in
   the corpus row format before authoring N3/N4 vectors.

8. **Binary-poisoning manifest source for switch-time attestation** — `envoy
runtime switch` verifies `binary_hash` against "the expected manifest"
   (`runtime-abstraction.md:160`); where does the manifest live and is the N=3
   mirror cross-check (`distribution.md:33`) run on EVERY switch or cached?

---

## Round-3 red-team correction (R3-HIGH) — applied 2026-06-08

**E1–E7 are BYTE-IDENTICAL conformance vectors, NOT semantic-equivalence.** This deep-dive's "byte-identical for spec paths, semantic-equivalence for LLM paths" framing wrongly placed E1–E7 on the semantic side. Per `specs/runtime-abstraction.md:188-196`, E1–E7 are all structural/byte-identical operations: E1 canonical JSON, E2 Delegation signing, E3 cascade-revoke set-equality, E4 cycle detection, E5 subset-proof verify, E6 two-phase orphan resolution, E7 head-commitment monotonicity ("Byte-identical; monotonic" at `:58`). The genuine semantic-equivalence surfaces are the RENDERED TEXT outputs (N4 verdict rendering, Grant Moment text — `:152`,`:239`), and that semantic-equivalence harness is largely Phase-03 (`runtime-abstraction.md:207`). Consequence corrected in the architecture plan: S3a/S3b are byte-identical (loop `live`, hash-equality), not probe-judged/base; the verifier S7v depends on S3b (E7 byte-identical) and the critical path S1→S2a→S3b→S7v is valid. Demoting byte-identical→semantic is BLOCKED (it weakens a security gate). See `journal/0004` R3-HIGH.
