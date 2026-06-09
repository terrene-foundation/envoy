# WS-4 — Envelope Library + SKILL.md Ingest (Phase-02 implementation architecture)

Workstream owner: Envelope Library registry (Foundation-Verified tier LIVE), Ed25519
publisher-signature verification, SKILL.md → CO-compliant-envelope translator, the CO
step-3 declared-vs-inferred permission validator, and the `envoy-registry:*` classifier
registry. Community tier stays frozen until Phase-03; Organization tier is Phase-04.

**Verification posture (read this first).** Every WS-4 deliverable is **greenfield Phase-02**.
There is NO `envoy/envelope_library/`, `envoy/skill_ingest/`, `envoy/registry/`, or
`envoy/foundation_ops/` module on `main`. The Phase-01 codebase ships the _seams_ WS-4
slots into — `envoy/envelope/template_resolver.py` (declares the Phase-02 URI schemes and
resolver Protocol), `envoy/ledger/keystore.py` + `kailash.trust.key_manager.InMemoryKeyManager`
(the Ed25519 sign/verify primitive), `envoy/runtime/protocol.py::classifier_registry_resolve`
(the registry-resolve interface method), and its Phase-01 stub in
`envoy/runtime/adapters/kailash_py.py:407` which raises `Phase02SubstrateNotWiredError`.
Every spec citation below was re-grepped against `main`; the three "phantom" classes
Wave-1 found do NOT recur here (see § Brief/spec corrections — all WS-4 citations resolve,
but several resolve to _interface stubs_ not _behavior_, which is the correct Phase-01 state
and is flagged so `/todos` sizes the wiring, not just the net-new code).

---

## Q1 — Envelope Library registry (Nexus-backed HTTP/CLI/MCP; content-addressed; Ed25519; tier model)

### 1.1 What ships this phase vs what stays frozen

`specs/foundation-ops.md:17` (registry #1) is the authority: `envoy-registry:envelope-library:v1`,
"Nexus-backed HTTP/CLI/MCP; Foundation-Verified / Community / Organization tiers. Ed25519
publisher signatures. Content-addressed storage." `DECISIONS.md:172-176` (ADR-0004 Infrastructure)
pins the implementation choices: **Registry API → Kailash Nexus (HTTP + CLI + MCP surfaces);
Publisher signing → Ed25519 via EATP `TrustKeyManager`; Storage → content-addressed via hash;
IPFS or git-mirror optional replication.**

Phase-02 scope (per `specs/envelope-library.md:17` FV row + the Community/Organization rows
being explicitly out-of-phase):

- **Foundation-Verified tier LIVE** — read path (fetch + verify), publish path is
  Foundation-internal only (the 2-of-N steward ceremony, Q2).
- **Community tier registry SHAPE present but publish DISABLED** — the tier enum, the
  `PublisherSignatureInvalidError`/`SybilSuspicionThresholdExceededError` taxonomy
  (`specs/envelope-library.md:65-66`), and the reputation record schema
  (`specs/envelope-library.md:35-47`) are defined, but the publish handler returns a typed
  "Community publishing opens Phase-03" refusal. Web-of-trust depth-≥3 and the per-publisher
  rate-limit are Phase-03.
- **Organization tier** — Phase-04 (`specs/skill-ingest.md:60`, "Private per-org registries
  (Phase 04)").

**Recommendation:** Build the registry as ONE Nexus app whose handler set is tier-aware from
day one (the tier is a field on every record), but gate the Community/Org _publish_ handlers
behind a feature flag that returns `503 + typed refusal`. This is cheaper than building "FV-only"
and retrofitting tiers in Phase-03, and it keeps the read-path verifier (the load-bearing
security surface) identical across tiers — only the _trust-root resolution_ differs (FV → steward
quorum; Community → publisher self-key; Org → org Trust-Lineage root).

### 1.2 The Nexus app shape (HTTP + CLI + MCP from one handler set)

Per the `03-nexus` skill: `NexusApp(NexusConfig(...))` + `@app.handler(name=…)` deploys each
handler to all three channels simultaneously. The registry is NOT a set of hand-written routes;
it is a handler set. The minimal FV-live handler surface:

| Handler                | HTTP                             | CLI                              | MCP                  | Purpose                                                                             |
| ---------------------- | -------------------------------- | -------------------------------- | -------------------- | ----------------------------------------------------------------------------------- |
| `library.fetch`        | `POST /api/library.fetch`        | `envoy library fetch <id>@<ver>` | tool `library.fetch` | Content-addressed read by `template_id@version` OR by `content_hash`                |
| `library.resolve_tier` | `POST /api/library.resolve_tier` | `envoy library tier <id>`        | tool                 | Returns tier + steward signature set for a template (does not return content)       |
| `library.list`         | `GET /api/library.list`          | `envoy library list --tier fv`   | tool                 | Catalog browse (FV-only this phase)                                                 |
| `library.publish`      | `POST /api/library.publish`      | `envoy library publish`          | tool                 | FV: Foundation-internal ceremony entry; Community/Org: typed 503 refusal this phase |

Two distinct deployments share this handler set: the **Foundation-operated** instance (the
canonical registry, holds steward keys for the publish ceremony) and the **client-side**
read-through (the consumer's `envoy` reaching the Foundation Nexus endpoint over OHTTP per
`specs/foundation-ops.md:20`, with `LibraryUnreachableError` + local-cache fallback per
`specs/envelope-library.md:64`). The consumer NEVER trusts the Nexus transport — it
re-verifies signatures locally (§1.4).

**Framework-first note (per `rules/framework-first.md`):** consult **nexus-specialist** before
any direct axum/route wiring. The registry MUST be a `NexusApp` handler set, not manual routes —
direct HTTP framework use is BLOCKED.

### 1.3 Content-addressed storage

Envoy already has the content-addressing primitive: `envoy/envelope/canonical_bytes.py`
(`canonical_bytes()` JCS-RFC8785 + NFC, `content_hash()` SHA-256 hex). `template_resolver.py:95-101`
already computes `template_hash = sha256(canonical)` over the SAME canonical pipeline, "so
cross-SDK byte-identity holds even on imported-constraint provenance trail." The registry's
storage key IS this `template_hash`. Design consequences:

1. **Storage is a content-addressed blob store keyed by `sha256(canonical_bytes(content))`.**
   The DataFlow-backed metadata table (`@db.model` per `rules/framework-first.md` —
   dataflow-specialist gate; raw SQL BLOCKED) maps `template_id@version → content_hash + tier +
steward_signatures[] + published_at`. The blob itself is addressed by hash; IPFS/git-mirror
   replication (`DECISIONS.md:176`) is the optional second tier.
2. **`TemplateHashMismatchError` (`specs/foundation-ops.md:109`) + `SkillSourceHashMismatchError`
   (`specs/skill-ingest.md:85`)** are the integrity gates: fetched bytes are re-hashed and
   compared to the declared `content_hash`. This is the SAME pattern as the registry-schema
   resolver's step (d) "hashes and compares to `artifact_hash`" (`specs/foundation-ops.md:57`).
3. **Fork-tracking (`specs/envelope-library.md:27-29`) is Community-tier**, so
   `parent_template_hash` + `ParentTemplateHashMismatchError` are SHAPE-only this phase.

### 1.4 How a consumer fetches + verifies a published envelope (the end-to-end read path)

This is the load-bearing question. The consumer side is `envoy/envelope/template_resolver.py`.
Phase-01 ships `LocalTemplateResolver` (`local:` URIs only). `TemplateRef` (line 27-28) ALREADY
declares the Phase-02 schemes: `foundation-verified:<id>@<version>` and `community:<author>:<id>`.
The Protocol docstring (line 52-53) ALREADY names the Phase-02 resolvers to add:
`FoundationVerifiedTemplateResolver` + `CommunityTemplateResolver`.

The FV read path (Phase-02 build):

```
envoy envelope import foundation-verified:family-starter@v3
  1. TemplateRef("foundation-verified:family-starter@v3")
  2. FoundationVerifiedTemplateResolver.resolve(ref):
     a. library.fetch over Nexus/OHTTP → {content, content_hash, tier:"FV",
        steward_signatures:[{steward_pubkey_hex, signature_hex}, ...]}
     b. re-hash: sha256(canonical_bytes(content)) == content_hash   → else TemplateHashMismatchError
     c. verify ≥2 distinct steward signatures over content_hash against the
        client-pinned Foundation stewardship key set                → else FVTierMembershipNotProvenError
                                                                          / PublisherSignatureInvalidError
     d. check steward keys not in the cached revocation list (specs/foundation-ops.md:83)
     e. return EnvelopeTemplate(content, template_hash=content_hash, template_origin="foundation-verified")
  3. compiler folds template constraints into per-dimension imported_constraints[]
     with authored=false, template_origin set, template_hash set
     (template_resolver.py:7-8 + envelope-model.md:43)
```

The verify primitive is `kailash.trust.key_manager.InMemoryKeyManager.verify` (the same one
`envoy/ledger/keystore.py:23-24` and `envoy/boundary_conversation/signatures.py` use). The
client's trust anchor is the PINNED Foundation stewardship key set + the revocation list — NOT
the Nexus transport. **`LibraryUnreachableError` + local-cache** (`specs/envelope-library.md:64`)
means the resolver checks a content-addressed local cache before declaring offline; a cached FV
template is still re-verified against pinned keys, so an offline consumer is not a less-secure
consumer.

**Recommendation (Q1):** Implement `FoundationVerifiedTemplateResolver` as a thin Nexus-client +
local-verify wrapper around the existing `canonical_bytes`/`content_hash` + `InMemoryKeyManager.verify`
primitives. The resolver Protocol is already frozen at `template_resolver.py:49-56`; this is a
_new implementation behind a frozen interface_, identical in shape to the WS-1 runtime-second-impl
seam. Size it as ~1 shard (one resolver class + Nexus client + cache); the steward-key pinning +
revocation-refresh is a second shard (it shares the registry-resolve verifier with the classifier
registry, Q4 — build it once).

---

## Q2 — Foundation-Verified signing ceremony (2-of-N steward signing, quarterly rotation)

### 2.1 Ceremony mechanics

`specs/foundation-ops.md:77-83` (§ Signing ceremonies) is the authority: "Foundation-Verified
signatures require 2-of-N Foundation stewards. Ceremony: Air-gapped environment; Per-release key
generation OR long-lived stewardship key rotation; Published revocation list; client-cached +
periodic refresh with revocation check." `specs/envelope-library.md:17` adds "key-rotation
quarterly."

The ceremony produces, for each FV template, a `steward_signatures` array
(`specs/foundation-ops.md:45-48`):

```json
"steward_signatures": [
  {"steward_pubkey_hex": "<str>", "signature_hex": "<ed25519>"}
],
"signing_threshold_met": <bool>
```

Each signature is an Ed25519 signature over the template's `content_hash` (the content-addressed
key, §1.3). 2-of-N means ≥2 distinct steward keys signed; `signing_threshold_met` is the folded
verdict. The mechanics:

1. **N distinct steward keys** enrolled in the Foundation stewardship key set. The threshold is 2. This is structurally the SAME 2-of-N pattern as the classifier registry
   (`specs/foundation-ops.md:22`, "FV classifiers signed 2-of-N") and the migration-allowlist
   registry (`:23`) — ONE quorum-verify primitive serves all three (Q4 cross-cut).
2. **Air-gapped signing** — the steward private keys never touch the online registry host. The
   ceremony is offline; the output (the signature array) is what gets published with the template.
   This is an operational property, not an Envoy code surface — the Envoy code only VERIFIES.
3. **Quarterly rotation** — a new steward key generation each quarter. The registry-schema
   `expires_at` field (`specs/foundation-ops.md:49`) + `RegistryEntryExpiredError` (`:105`) carry
   the rotation cadence into the verifier. `specs/foundation-ops.md:149` open-Q2 notes the
   quarterly-vs-continuous tradeoff is unresolved — flag for `/todos`.

### 2.2 Client-side verification

The consumer verifies WITHOUT any steward private key. Inputs the client holds: the pinned
Foundation stewardship PUBLIC key set + the cached revocation list. The verify is:

```
verify_fv_quorum(content_hash, steward_signatures, pinned_steward_pubkeys, revocation_list):
  valid = [s for s in steward_signatures
           if s.steward_pubkey_hex in pinned_steward_pubkeys
           and s.steward_pubkey_hex not in revocation_list
           and InMemoryKeyManager.verify(content_hash, s.signature_hex, s.steward_pubkey_hex)]
  distinct = {s.steward_pubkey_hex for s in valid}
  if len(distinct) < 2:  raise FVTierMembershipNotProvenError   # specs/envelope-library.md:70
  return True
```

This is byte-for-byte the registry-schema resolver's verify (`specs/foundation-ops.md:57` steps
b-e) specialized to threshold=2. **Build it ONCE as a shared `verify_steward_quorum(threshold, …)`
helper** and call it from both the Envelope Library FV resolver and the classifier registry
resolver (Q4). The `RegistrySignatureMismatchError`/`RegistryThresholdNotMetError`
(`specs/foundation-ops.md:102-103`) and `FVTierMembershipNotProvenError`
(`specs/envelope-library.md:70`) are the SAME failure surfaced under two error taxonomies — the
helper raises a base error each consumer maps to its own taxonomy.

**Quarterly rotation client surface:** the client refreshes the pinned steward key set + revocation
list over OHTTP (`specs/foundation-ops.md:83`, "client-cached + periodic refresh with revocation
check"). A signature by a rotated-out (but not revoked) key is still valid for templates signed
before rotation — rotation is additive (new keys enrolled), revocation is subtractive (compromised
keys blocklisted). The two are distinct and the verifier MUST treat them distinctly (revocation =
hard fail; rotation = old signatures still valid, new templates use new keys).

**Recommendation (Q2):** Implement `verify_steward_quorum(threshold, content_hash, signatures,
pinned_pubkeys, revocation_list)` as the single 2-of-N verify primitive, shared across Envelope
Library FV + classifier registry + (Phase-03) migration-allowlist. Do NOT build a steward
_signing_ path in Envoy — signing is the air-gapped Foundation-operational ceremony, outside Envoy
product code. Envoy verifies; the Foundation signs offline.

---

## Q3 — SKILL.md → envelope translator + CO validator (step-3 is the hard part)

### 3.1 The translator pipeline

`specs/skill-ingest.md` is the authority; `DECISIONS.md:186-206` (ADR-0005) is the decision. The
install flow (`specs/skill-ingest.md:69`):

```
envoy skill install @author/skill-name@version
  → fetch → parse SKILL.md → generate ENVELOPE.md → CO validator
  → Grant Moment user review → sign → inventory + Ledger
```

The CO validator's 6 steps (`specs/skill-ingest.md:37-45`):

1. SKILL.md schema valid
2. Permission patterns recognized (via `envoy-registry:permission-to-pact-dimension:v1`,
   `specs/skill-ingest.md:23-33`)
3. **Declared = inferred (code analysis; Phase 02 automated)** ← the hard part
4. Over-privilege warning
5. Adversarial-pattern detection (`envoy-registry:adversarial-skill-patterns:v1`)
6. Publisher signature verifies

Steps 1, 2, 4, 6 are mechanical: schema validation, registry lookup against the
permission→PACT-dimension table (`bash:* → Operational + Data Access (Confidential)` etc.,
`specs/skill-ingest.md:24-32`), set-difference for over-privilege, and the same Ed25519 verify as
Q2. Step 5 is the classifier-ensemble (Q4). **Step 3 is the net-new Phase-02 hard problem.**

Score thresholds (`specs/skill-ingest.md:46`): ≥0.8 pass; 0.5–0.8 pass-with-warnings; <0.5 fail
(needs `force_install=True`).

### 3.2 Step 3 — declared-permissions == inferred-permissions (the inference tooling)

The skill ships a SKILL.md `permissions` array (declared) + inline code blocks
(`specs/skill-ingest.md:15`, "name, version, description, permissions array, inline code blocks").
Step 3 must INFER what the code actually does and compare to what it DECLARES. The inference target
is the SAME grammar as the declared set: `bash:*`, `file-read:*`, `file-write:*`,
`http-post:<domain>`, `mcp:<server>`, `oauth:<service>`, `exec:<pattern>`
(`specs/skill-ingest.md:24-32`).

**The inference tooling (recommendation, with the false-positive analysis the brief demands):**

Phase-01 ships NO AST tooling (grep confirmed: the only `ast.parse` reference is an unrelated
heartbeat docstring). The inference engine is net-new. The design space:

| Approach                      | What it produces                                                                                                                                                                                               | False-positive profile                                                                                                                                               | Verdict                             |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| **Python `ast` static walk**  | `subprocess`/`os.system`/`os.popen` → `bash:`/`exec:`; `open(…, "r")` → `file-read:`; `open(…, "w")` → `file-write:`; `urllib`/`requests`/`httpx` `.post(url)` → `http-post:<host>`; MCP client calls → `mcp:` | LOW for direct calls; BLIND to dynamic dispatch (`getattr`, `importlib`, `eval`), string-built URLs, indirection through a helper                                    | **Primary engine**                  |
| **Import-graph + call-graph** | which stdlib/3rd-party capability modules are imported AND reached                                                                                                                                             | catches the indirection AST misses; over-broad (an imported-but-unreached module inflates inferred set → false over-privilege-on-the-skill, i.e. false REJECT)       | **Secondary, advisory weight only** |
| **LLM-judge over code**       | semantic "what does this do"                                                                                                                                                                                   | high variance; per `rules/probe-driven-verification.md` an LLM-judge MUST have a JSON-schema output + scoring rule — usable as a TIE-BREAKER, never the primary gate | **Tertiary, schema-bound**          |

**Recommended engine: Python `ast` static walk as the primary, producing a CONSERVATIVE inferred
set (only capabilities reached by a literal call), with the import-graph as an advisory
second-opinion that can only RAISE a warning, never auto-reject.** The comparison is asymmetric and
this asymmetry IS the design:

- **declared ⊋ inferred (declared more than code uses)** → `OverPrivilegeWarning`
  (`specs/skill-ingest.md:81`), step-4. NOT a reject — surfaced at Grant Moment for downscope.
  This is the SAFE direction (the skill asked for more than it needs; the user can trim).
- **inferred ⊋ declared (code does more than it declared)** → the DANGEROUS direction. This is the
  permission-escalation/exfiltration signal. Code that opens a socket but declared no
  `http-post:` is the exact adversarial sample the acceptance gate tests.

### 3.3 The false-positive budget — the verdict the brief demands

**The question:** what is the false-positive budget before the validator becomes net-noise?

The acceptance gate (`specs/acceptance-metrics.md:32`, Phase-02 exit criteria, verbatim:
"CO validator accepts 100 benign + rejects 3 adversarial") sets the budget MECHANICALLY:

- **3 constructed adversarial samples** (permission-escalation, exfiltration, privilege-overreach)
  MUST be rejected → false-NEGATIVE budget = **0** on the adversarial corpus. A miss here is a
  validator that passes an exfiltrating skill — catastrophic. Zero tolerance.
- **100 benign skills** MUST be accepted → false-POSITIVE budget = **0 on the calibration corpus**.
  A false reject on a benign skill forces `force_install=True`, which TRAINS users to reflexively
  force-install (`specs/skill-ingest.md:48-54`) — and once the user reflexively force-installs,
  the validator is net-noise because it no longer changes behavior.

**Verdict (the load-bearing finding):** The false-positive budget is **0% on the 100-benign
acceptance corpus** and the structural defense that makes 0% achievable is the **asymmetric
comparison + the score-threshold band**. The validator MUST NOT auto-REJECT on `inferred ⊋ declared`
from the _static walk alone_, because the static walk's known blind spots (dynamic dispatch, helper
indirection) produce false "code does more than declared" signals. Instead:

- `inferred ⊋ declared` detected by the **conservative AST walk** (a LITERAL call to an undeclared
  capability) → score → <0.5 → REJECT. The AST walk only flags what it can prove via a literal
  call node, so its false-positive rate on benign code is structurally near-zero (a benign skill
  that literally calls `requests.post` to an undeclared host IS mis-declared and SHOULD be flagged).
- `inferred ⊋ declared` detected ONLY by the **import-graph** (module imported, capability not
  proven reached) → score 0.5–0.8 → pass-WITH-WARNING, surfaced at Grant Moment, NOT auto-reject.
  This routes the false-positive-prone signal to the WARNING band, not the REJECT band.

This two-tier routing is what keeps the 100-benign corpus at 0 false-rejects while keeping the
3-adversarial corpus at 0 false-accepts: the adversarial samples (escalation/exfiltration/overreach)
make LITERAL undeclared-capability calls the AST walk catches; the benign skills' "extra" signals
are import-graph-only and land in the warning band. **If a future skill defeats the AST walk via
`getattr`/`eval`/`importlib` indirection, that indirection IS ITSELF an adversarial-pattern signal
for step-5** (`envoy-registry:adversarial-skill-patterns:v1`) — dynamic dispatch in a permission-
sensitive skill is the classifier's job to flag, closing the AST blind spot through a different step.

**Net-noise threshold (explicit):** the validator becomes net-noise when its false-reject rate on
benign skills exceeds the rate at which users will tolerate an extra Grant-Moment friction step
before reflexively force-installing. The 100-benign gate sets that at 0 — any false-reject in the
calibration corpus is a build-blocking finding, not a tuning knob.

**Recommendation (Q3):** Build step-3 as `infer_permissions(skill_code) → InferredPermissionSet`
via a conservative Python `ast` walk (primary, literal-call-only) + an import-graph second opinion
(advisory→warning band only). The comparison `compare_declared_inferred(declared, inferred) →
score` routes literal-undeclared-call to REJECT and import-only-extra to WARNING. Validate against
the 100-benign + 3-adversarial corpus AS the acceptance gate. Per
`rules/probe-driven-verification.md`, the adversarial-rejection test MUST be a STRUCTURAL probe
(assert the validator raises `COValidatorRefusedError` / returns score <0.5 on each of the 3
samples) — NOT a regex over the validator's prose output. Size as 2 shards: (1) the AST inference
engine + comparison, (2) the corpus + the acceptance probe harness. The corpus authoring (100
benign + 3 adversarial) is itself a deliverable per `specs/skill-ingest.md:109-110`.

---

## Q4 — Classifier registry (`envoy-registry:*` namespace; FV classifiers 2-of-N signed)

### 4.1 What it is and how it shares the FV verifier

`specs/foundation-ops.md:22` (registry #6): the classifier registry is the `envoy-registry:*`
NAMESPACE — "any classifier named `envoy-registry:<domain>:<name>:v<N>`", FV classifiers signed
2-of-N, Community same trust model as Envelope Library. The registry-schema (`:36-55`) and the
resolve algorithm (`:57`, `classifier_registry_resolve`) are shared across EVERY `envoy-registry:*`
entry — the Envelope Library (#1), the permission→PACT-dimension table (#9), the
adversarial-skill-patterns classifier (#17), all of them.

The resolve interface ALREADY EXISTS as a frozen Protocol method:
`envoy/runtime/protocol.py:170-173` (`classifier_registry_resolve(registry_id)`, "Fetches,
verifies 2-of-N steward signatures, hash-matches; per specs/foundation-ops.md § Registry schemas").
The Phase-01 stub is `envoy/runtime/adapters/kailash_py.py:407-411`, raising
`Phase02SubstrateNotWiredError("classifier_registry_resolve: requires Wave-3 classifier registry

- 2-of-N steward signatures; tracked at …02-wave-2-…")`. The rs-bindings adapter carries the same
stub shape (`envoy/runtime/adapters/kailash_rs_bindings.py:71+`).

### 4.2 The Phase-02 wiring

`classifier_registry_resolve(registry_id)` implements the 5-step resolve from
`specs/foundation-ops.md:57`:

```
(a) fetch the registry entry (Nexus/OHTTP)
(b) verify signing_threshold_met == true AND steward_signatures match Foundation
    stewardship keys AND expires_at not passed     → verify_steward_quorum(2, …)  [SHARED with Q2]
(c) fetch content_ref (url | ipfs://cid | inline)
(d) hash content and compare to artifact_hash      → RegistryArtifactHashMismatchError
(e) return resolved artifact
```

Step (b) is the EXACT same `verify_steward_quorum(threshold=2, …)` primitive as the Envelope
Library FV verifier (Q2). **This is the strongest cross-cut in WS-4: ONE 2-of-N steward-quorum
verifier serves the Envelope Library FV tier, the classifier registry, AND (Phase-03) the
migration-allowlist registry.** Build it once; the three registries differ only in `content_type`
(`template` vs `classifier` vs `allowlist`, `specs/foundation-ops.md:52`) and their error-taxonomy
mapping.

The classifier registry feeds step-5 of the CO validator (Q3): the `adversarial-skill-patterns:v1`
classifier is resolved through `classifier_registry_resolve` then invoked via `classifier_invoke`

- `ensemble_aggregate` (also currently `Phase02SubstrateNotWiredError` stubs at `kailash_py.py:395-405`).
  The classifier-ensemble (≥2 classifiers, "disagreement fails CLOSED by default", `protocol.py:166-167`)
  is a Wave-3 dependency — flag the ordering for `/todos`.

**Recommendation (Q4):** Wire `classifier_registry_resolve` in BOTH the `kailash_py` and
`kailash_rs_bindings` adapters (cross-runtime parity — the frozen Protocol means both adapters
implement the same interface; per WS-1's conformance harness both MUST be byte/semantically
conformant). Implement step (b) via the shared `verify_steward_quorum`. The classifier-INVOKE
surface (ensemble + aggregate) is a separate, larger Wave-3 deliverable (model adapter dependency)
— size the resolve (this phase) separately from the invoke (Wave-3). The classifier-resolve is
~1 shard sharing the Q2 verifier; do NOT bundle it with the ensemble-invoke wiring.

---

## Spec gaps identified (Phase-02 implementation detail the frozen specs DON'T cover — ADDITIONS ONLY, no spec edits)

1. **Shared `verify_steward_quorum(threshold, …)` helper location.** Three specs
   (`envelope-library.md` FV, `foundation-ops.md` classifier + migration-allowlist) each describe
   2-of-N verify in their own error taxonomy, but no spec names the SHARED primitive. The specs are
   correct as written (each describes its surface); the gap is an implementation-architecture
   decision (`/todos` should name the module — recommend `envoy/registry/steward_quorum.py`).
2. **Community-tier "shape present, publish disabled" mechanism.** `specs/envelope-library.md`
   describes the full Community tier as if live; `specs/skill-ingest.md:60` + `:46` Organization
   note Phase-04. No spec states HOW Community publish is gated off in Phase-02. Recommend a feature
   flag returning a typed "Community publishing opens Phase-03" refusal — this is impl detail, NOT
   a spec change (the spec describes the eventual behavior; the phase-gating lives in todos per
   `rules/spec-accuracy.md` Rule 4).
3. **AST-inference module + corpus location.** `specs/skill-ingest.md:39` says "code analysis;
   Phase 02 automated" but names no tooling (correctly — that's impl). `/todos` should specify
   `envoy/skill_ingest/permission_inference.py` + `tests/acceptance/phase_02/co_validator_corpus/`
   (100 benign + 3 adversarial fixtures).
4. **Local-cache re-verification on offline FV fetch.** `specs/envelope-library.md:64`
   (`LibraryUnreachableError`) says "no local cache entry" triggers the offline notice but doesn't
   state that a cache HIT is still re-verified against pinned keys. Recommend documenting the
   re-verify-on-cache-hit invariant in `/todos` (impl detail; the security property is implied by
   the content-addressing but should be explicit so the cache isn't built as a trust bypass).
5. **Cross-runtime parity for the registry resolvers.** WS-1's conformance harness (N1–N6/E1–E7)
   doesn't currently include registry-resolve vectors. The FV-verify + classifier-resolve are new
   Protocol surfaces both adapters implement; they need conformance vectors. Flag for the WS-1↔WS-4
   integration seam.

## Brief/spec corrections (phantom-citation findings)

**NO phantom citations found in the WS-4 spec surface.** Every brief citation re-grepped clean
against `main`:

- `specs/envelope-library.md:17` (FV tier row) — resolves verbatim.
- `specs/foundation-ops.md:17` (registry #1 Nexus-backed/content-addressed/Ed25519) — verbatim.
- `specs/foundation-ops.md:22` (classifier registry `envoy-registry:*` 2-of-N) — verbatim.
- `specs/skill-ingest.md:41,81,120` (declared-vs-inferred step-3 / OverPrivilegeWarning / open-Q2) — all verbatim.
- `specs/enterprise-deployment.md:15` (Phase-02 EDR schema+verifier+dual-sign with cross-runtime conformance) — verbatim.
- `DECISIONS.md:182,204` (SKILL.md translator + PACT envelope translator = Phase-02 deliverable) — verbatim.
- `specs/acceptance-metrics.md:32` (CO validator accepts 100 benign + rejects 3 adversarial — Phase-02 exit) — verbatim, and it grounds the Q3 false-positive verdict.

**One precision note (NOT a phantom, a state-of-code clarification for `/todos`):** the brief frames
WS-4 as net-new. Several pieces are net-new-CODE _behind already-frozen interfaces_: the registry
resolver Protocol (`template_resolver.py:49-56`), the `foundation-verified:`/`community:` URI
schemes (`template_resolver.py:27-28`), and `classifier_registry_resolve` (`protocol.py:170` +
its `Phase02SubstrateNotWiredError` stub at `kailash_py.py:407`) ALL exist as Phase-01 seams. This
is the CORRECT Phase-01 state (interface frozen, behavior stubbed with a typed error + todo anchor
per `rules/zero-tolerance.md` Rule 6 iterative-TODO carve-out) — NOT a spec-accuracy violation. The
implication for sizing: WS-4 is "implement behind frozen interfaces," the same shape as WS-1's
runtime second-impl, so the conformance discipline applies.

**One EDR scope guard (per the brief's "do NOT over-scope"):** `specs/enterprise-deployment.md:15`
places the EDR schema+verifier+dual-sign in Phase-02 (riding the cross-runtime-conformance landing);
`:16` places DISABLEMENT + cooling-off + N=5 ratchet in Phase-03 and `:17` places the 2-pilot
acceptance in Phase-04. WS-4 builds the EDR _verifier_ (6 steps, `:43-49`) + dual-sign gate ONLY —
NOT the disablement flow. The `tests/integration/test_edr_disablement_24h_cooling_off.py` and
`test_enterprise_n5_posture_ratchet.py` (`:101,103`) are Phase-03 test targets; do not build them
this phase.

## Open questions for `/todos`

1. **Shard ordering for the classifier dependency chain.** The CO validator step-5 needs the
   `adversarial-skill-patterns` classifier, which needs `classifier_registry_resolve` (this phase)
   AND `classifier_invoke`/`ensemble_aggregate` (Wave-3, model-adapter-dependent). Can step-5 ship
   in Phase-02, or is the CO validator initially 5-step (1-4,6) with step-5 landing when the
   ensemble wires? Recommend: ship steps 1-4,6 + step-3 in Phase-02; step-5 deferred to the
   classifier-invoke wiring with a typed "adversarial-pattern check pending ensemble" — surfaced,
   not silent.
2. **Quarterly key rotation cadence** (`specs/foundation-ops.md:149` open-Q2): quarterly vs
   continuous (per-release) steward rotation. Affects the `expires_at` refresh cadence in the
   verifier. Foundation-operational decision; needs a default for the client refresh interval.
3. **100-benign corpus sourcing.** The acceptance gate needs 100 real benign SKILL.md skills. Are
   these drawn from the external ecosystem's public skill library, synthesized, or curated? The
   corpus IS the calibration set for the 0%-false-reject budget — its representativeness determines
   whether 0% in-corpus generalizes to 0% in-the-wild.
4. **Steward-quorum verifier as a shared module across all `envoy-registry:*` consumers** — confirm
   the single-helper decision (gap #1) at `/todos` so Envelope Library + classifier registry +
   (Phase-03) migration-allowlist don't each grow a parallel verify.
5. **Cross-runtime parity vectors for registry-resolve** (gap #5) — does the WS-1 conformance
   harness (N1–N6/E1–E7) gain a registry-resolve vector class, or do the resolvers get a separate
   conformance suite? Both adapters implement `classifier_registry_resolve`; the verdict must be
   byte/semantically conformant per the WS-1 contract.
6. **Community tier publish-disable mechanism** (gap #2) — feature flag returning typed 503, or
   handler-absent? Recommend feature-flag-present-but-refusing so the Phase-03 enable is a flag
   flip, not a new handler.
