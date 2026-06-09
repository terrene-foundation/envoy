# WS-5 — Foundation Health Heartbeat Infrastructure (Phase-02 `/analyze` deep-dive)

**Workstream:** WS-5 — privacy-preserving aggregate telemetry (STAR/Prio + DP + OHTTP + signed-consent).
**Scope:** stand up the real infrastructure that Phase-01 stubbed (5-stub partition under `envoy/heartbeat/`).
**Budget (specs):** 2–3 autonomous sessions (`specs/mvp-build-sequence.md:84,201`).
**Largest single de-scoped Phase-01 item.** Phase-01 ships ~100 LOC of stubs; Phase-02 stands up the live crypto + network + consent substrate.

This is an IMPLEMENTATION-architecture document. Every citation below resolves against working code on `main` at deep-dive time (per `rules/spec-accuracy.md` MUST-1). Where the brief or a spec asserts a symbol that does NOT ground to real code, it is flagged in § "Brief/spec corrections" as a phantom-citation finding (wave-1 found 3).

---

## 0. The actual wiring seam — grounded in real source

The brief says "4 stub modules". **The real code ships a 5-stub partition**, deliberately partitioned by Round-2 finding R2-H-02 into two structurally distinct categories. This is the single most load-bearing correction in this document because every WS-5 implementation shard wires against these exact symbols.

Source of truth: `envoy/heartbeat/__init__.py:1-100` (the partition docstring), and the partition regression at `tests/regression/test_r2_h_02_heartbeat_stub_partition.py:1-50`.

### Category A — GENUINE no-op (Phase-01 production code CALLS this)

| Symbol                                         | Path                              | Phase-01 body                                        | Phase-02 swap                                                                                |
| ---------------------------------------------- | --------------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `HeartbeatClient.maybe_record_flag(flag_name)` | `envoy/heartbeat/client.py:48-72` | literal `pass` (no exception, no Ledger, no network) | validate flag → increment consent-gated per-week counter → weekly emit via STAR/Prio + OHTTP |

`maybe_record_flag` is the hot-path consumer the 21 emit-site primitives (Boundary Conversation completion, Daily Digest open, Grant Moment approve, Authorship Score, Posture ladder, Budget tracker, Channel adapters, Runtime, Enterprise mode) will call as a one-line counter increment. It is NOT a `zero-tolerance.md` Rule-2 stub — the Phase-01 contract IS "do nothing", and the no-op is what keeps emit-site primitives from crashing on first emit before WS-5 lands (`client.py:18-37`).

### Category B — RAISE `PhaseDeferredError` (Phase-01 production code MUST NEVER call)

These 4 are the brief's "4 stub modules". Each `__init__`/helper raises `PhaseDeferredError` (`envoy/heartbeat/errors.py:145-163`); the regression grep at `tests/regression/test_r2_h_02_heartbeat_stub_partition.py:150-191` enforces zero non-test imports.

| Deferred module                     | Class                     | Module helpers                                           | Phase-02 contract source                                     |
| ----------------------------------- | ------------------------- | -------------------------------------------------------- | ------------------------------------------------------------ |
| `envoy/heartbeat/star_prio.py`      | `StarPrioClient`          | `split_into_shares`, `check_client_side_k_anonymity`     | spec § "Design stack" item 1                                 |
| `envoy/heartbeat/ohttp.py`          | `OhttpClient`             | `fetch_key_configuration`, `encapsulate_request`         | spec § "Design stack" item 3 (RFC 9458)                      |
| `envoy/heartbeat/signed_consent.py` | `SignedConsentRecorder`   | `record_grant_moment`, `record_cascade_revoke`           | spec § "Consent layer"                                       |
| `envoy/heartbeat/registry.py`       | `HeartbeatRegistryClient` | `fetch_aggregator_endpoint`, `verify_operator_signature` | `specs/foundation-ops.md` § "Infrastructure inventory" row 3 |

### Phase-01 structural defenses that ALREADY ship (do NOT re-build in WS-5)

- `HeartbeatPayload` — frozen 21-flag dataclass (`envoy/heartbeat/payload.py:60-87`).
- `_validate_payload_schema` — T-054 covert-channel + T-041 duress-leak defenses, both ACTIVELY raised today (`payload.py:90-138`). T-041 check runs FIRST (more-specific error surfaces ahead of generic schema-drift).
- `ALLOWED_FLAGS` frozenset (21 entries) + `DURESS_FLAG_NEVER_REPORTED` constant (`payload.py:30-58`).
- The full 10-error taxonomy (`errors.py:36-163`) — defined Phase-01 so WS-5 wires raise sites WITHOUT adding exception classes.

**The seam, stated precisely:** WS-5 replaces the `PhaseDeferredError` bodies in the 4 Category-B modules with real implementations, AND swaps the `pass` body of `maybe_record_flag` for the real counter+emit pipeline. When the Category-B bodies become real, the partition regression grep flips green automatically (`errors.py:154-162`); any premature caller surfaces as HIGH BEFORE the swap. No new module paths, no new exception classes — the import surface is pre-declared. This is a clean seam by design.

---

## Q1 — OHTTP (RFC 9458) Key Configuration Server + Relay

### What the Foundation operates vs delegates

Per `specs/foundation-ops.md` § "Infrastructure inventory":

| Component                          | Operator                                  | Spec row | Strips source IP?                  |
| ---------------------------------- | ----------------------------------------- | -------- | ---------------------------------- |
| **OHTTP Key Configuration Server** | Foundation (operates)                     | row 3    | n/a (publishes encapsulation keys) |
| **OHTTP Relay**                    | Foundation OR third-party (delegate-able) | row 4    | YES — this is its only job         |
| **STAR/Prio aggregator**           | Foundation (operates)                     | row 5    | n/a (sees only shares)             |

The privacy property is the **non-collusion split**: the Relay sees the client IP but NOT the (encrypted) request body; the aggregator (gateway) sees the request body but NOT the client IP. The threat model names "relay+aggregator colluding" as an accepted residual risk (`specs/threat-model.md:42`), which is exactly why third-party relay operation is offered (`spec § Open questions item 3`).

### Client flow (the 3 steps WS-5 wires)

1. **Key discovery** — client fetches the Key Configuration from the Foundation Key Config Server. Wiring point: `ohttp.fetch_key_configuration` (`envoy/heartbeat/ohttp.py:44-50`) for the raw fetch, gated by `registry.fetch_aggregator_endpoint` + `registry.verify_operator_signature` (`registry.py:44-58`) for operator-signed config + endpoint discovery. The Key Config is an operator-signed artifact (Ed25519, 2-of-N Foundation stewards per `foundation-ops.md` § "Signing ceremonies"); the registry handshake verifies the signature + expiry/rotation BEFORE the key is trusted.
2. **Encapsulation (HPKE)** — client encapsulates the binary HTTP request to the aggregator under the fetched public key. Wiring point: `ohttp.encapsulate_request` (`ohttp.py:52-58`). RFC 9458 OHTTP uses HPKE (RFC 9180); the encapsulated request is opaque to the relay.
3. **Routing through the relay** — client POSTs the encapsulated request to the Relay; the Relay forwards to the aggregator (gateway) with the source IP stripped, and relays the encapsulated response back. Wiring point: the real `OhttpClient` body (`ohttp.py:32-41`), which today raises `PhaseDeferredError`.

### Foundation-side infra WS-5 MUST stand up first

`ohttp.py:4-19` and `registry.py:4-19` are explicit: as of the shard-17 DECISION there is **no deployment plan, no operator, no published key registry** for the Key Config Server. WS-5's first concrete deliverable is therefore **Foundation-ops infrastructure, not client code** — stand up the Key Config Server + Relay + aggregator endpoints, publish the operator-signed key registry, THEN wire the client. This is why the budget is 2–3 sessions, not 1: roughly one session is server-side standup that the client cannot proceed without (existence-check-first discipline, `rules/verify-resource-existence.md` MUST-2 — the client MUST verify the live endpoint exists before debugging access).

### Transport hardening (already specified, WS-5 inherits)

- TLS 1.3 + cert pinning + strict SNI + HSTS for all Foundation endpoints; pinned certs ship in the binary (`specs/network-security.md:5,20`). `OHTTPRelayUnavailableError` (`errors.py:48-52`) is the typed failure when the relay refuses connection.
- **Tor option (Phase-02+)** — optional route-through-Tor for Heartbeat traffic (`specs/network-security.md:30-32`). `TorRouteUnavailableError` is the typed failure (`network-security.md:49`). Default-on-vs-opt-in is an open question (`network-security.md:77` item 4) — Tor exit-node risk vs privacy benefit. **Recommendation:** ship Tor as opt-in (default off) in WS-5 because OHTTP already provides IP-stripping; Tor is defense-in-depth, and default-on adds an exit-node-MITM surface for marginal benefit once the relay is non-colluding. Pros: belt-and-suspenders IP privacy. Cons: exit-node observation risk, added latency, daemon dependency. The opt-in granularity lets privacy-sensitive users opt up without imposing the cost on everyone.

---

## Q2 — STAR/Prio aggregator + k-anonymity (k ≥ 100)

### STAR vs Prio — recommendation: **STAR (single-server), with k-anonymity as the hard gate**

| Property                 | STAR (Distributed Aggregation Protocol — Sharded Threshold Aggregation)                                           | Prio / Prio3 (verifiable secret-shared aggregation)                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Server topology          | **Single aggregation server** (k-threshold recovery)                                                              | **≥2 non-colluding servers** (MPC)                                          |
| What it computes         | threshold-gated reveal: a value is only recoverable once ≥k clients submitted the SAME measurement                | arbitrary aggregate statistics (sums, histograms) over secret-shared inputs |
| k-anonymity              | **native** — k-threshold IS the recovery condition; below k, the share is information-theoretically unrecoverable | enforced as a post-aggregation policy gate, NOT structural                  |
| Operator burden          | one Foundation server                                                                                             | two independently-operated non-colluding servers                            |
| Fit for 21 boolean flags | excellent — boolean cohort counts are exactly STAR's shape                                                        | overkill — Prio's verifiable-arithmetic strength is unused on booleans      |

**Recommendation: STAR.** Rationale (per `rules/recommendation-quality.md`):

- **Pros:** (a) k-anonymity is structural, not a policy gate — below k=100 the value is cryptographically unrecoverable, so a misconfiguration cannot leak a sub-threshold cohort; (b) single-server is one Foundation operator, matching the `foundation-ops.md` row-5 "Foundation-operated" declaration (Prio's two-non-colluding-server requirement would need a SECOND operator the spec never provisions); (c) the payload is 21 booleans — STAR's threshold-reveal is the exact primitive, Prio's verifiable arithmetic is unused.
- **Cons (real, not glossed):** (a) STAR cannot compute arbitrary statistics — if Phase-04 wants distributional metrics beyond boolean cohort counts (spec § Open questions item 5, "21-flag set Phase-04 expansion"), STAR will not stretch and Prio would. (b) STAR's single-server trust is weaker than Prio's split-trust on paper — but OHTTP already provides the IP-unlinkability that the single STAR server would otherwise need a second party for, so the composition (OHTTP relay + STAR) recovers the non-collusion property at the network layer.
- **The composition is the answer:** OHTTP strips IPs (Q1) so the STAR server never sees who submitted; STAR's k-threshold ensures it can't reveal a value until k≥100 distinct submitters. Together they deliver Prio-class privacy with one Foundation operator.

The spec itself hedges ("STAR ... or Prio", `foundation-health-heartbeat.md:19`); `star_prio.py:14-19` names STAR as the primary ("STAR (Signer-Anonymous Reporting Telemetry) / Prio"). Note the module's STAR expansion ("Signer-Anonymous Reporting Telemetry") differs from the canonical academic STAR ("Distributed Aggregation Protocol / Sharded-Threshold-Aggregation-for-Revelation"); flagged in § Brief/spec corrections as a naming nuance, not a phantom citation.

### Aggregation protocol + k-anonymity enforcement point

1. **Client share-split** — each weekly report is split into shares. Wiring point: `star_prio.split_into_shares` (`star_prio.py:44-50`). Each share carries the STAR encryption of the measurement keyed by the measurement value itself (so identical measurements across clients produce combinable shares).
2. **Client-side k-anonymity pre-check** — `star_prio.check_client_side_k_anonymity` (`star_prio.py:52-58`) is the client's advisory floor check before submit.
3. **Aggregator k-floor enforcement (the authoritative gate)** — the Foundation STAR aggregator withholds any aggregate whose cohort size < 100. This is the SERVER-side enforcement point and the hard privacy gate. Typed failure: `kAnonymityFloorViolatedError` (`errors.py:62-68`, lowercase `k` preserved verbatim per spec). On withhold, the Foundation publishes a withholding event in the transparency report (spec error-taxonomy row 4) — the withhold is auditable, not silent.

`STARShardCorruptError` (`errors.py:54-55`) is the typed failure for share-split failure at client OR aggregation rejection of a malformed share.

### Low-population flag caveat (open question, real design risk)

`channel_imessage_active` / `channel_signal_active` may never reach k=100 if those channels are rare (spec § Open questions item 2). Under STAR this is SELF-CORRECTING — the share is simply never revealed, so a rare-channel flag is structurally withheld rather than leaked. **Recommendation:** accept the withhold (correct privacy behavior) and surface "metric withheld: cohort below k=100" in the transparency report so the rare-channel signal's ABSENCE is itself documented, rather than padding the cohort (which would corrupt the count).

---

## Q3 — Differential privacy: ε budgeting + noise injection point

### Where noise is injected — recommendation: **client-side (local DP), per-counter, before share-split**

The spec says "bounded noise on each counter; ε per-metric published" (`foundation-health-heartbeat.md:20`). Two architectural choices:

- **Client-side (local DP):** each client perturbs its own counter before splitting into shares. Pro: the Foundation server NEVER sees a true per-client value even in principle — DP holds even against a fully-compromised aggregator. Con: more noise per query (each client adds independent noise).
- **Aggregator-side (central DP):** the aggregator adds noise to the revealed aggregate. Pro: less total noise (one noise draw per metric). Con: requires trusting the aggregator to actually add it AND to have seen true values pre-noise.

**Recommendation: client-side / local DP**, injected at the counter BEFORE `split_into_shares` (`star_prio.py:44`). Rationale: the whole WS-5 thesis is "collector aggregates without seeing individual values" (`foundation-health-heartbeat.md:19`). Central DP reintroduces a trusted-aggregator assumption that STAR+OHTTP spent the whole stack removing. The cost (more noise) is acceptable at the population scale where k≥100 already holds — and the covert-channel defense explicitly lists "Differential privacy on flag entropy" as a client-side defense (`foundation-health-heartbeat.md:44`), which only makes sense if noise is added at the client (a compromised client's flag entropy is bounded BEFORE it leaves the device).

- **Pros:** holds against compromised aggregator; matches the covert-channel-defense framing; no added trust assumption.
- **Cons:** higher aggregate variance; ε budget is consumed per-client-per-week and must be tracked locally (the `DPBudgetExceededError` path below).

### ε budgeting per-metric — recommendation: **fixed published per-counter ε, per weekly reporting window, with per-metric budget tracking**

- Each of the 21 flags gets its own published ε (the spec mandates "ε per-metric published", `:20`, and Open question item 1 frames the publication trade-off: public per-metric values vs an aggregate privacy-budget number).
- **Recommendation: publish per-metric ε values** (not just an aggregate budget). Pro: full transparency — a user/auditor can see exactly the privacy cost of each flag, which is the BET-falsifiability-measurement substrate's whole point (transparency IS the product). Con: per-metric publication gives an adversary a slightly sharper model of the noise distribution per flag. The con is marginal at k≥100 and the transparency benefit dominates for a privacy-first product whose thesis is auditability.
- **Budget enforcement point:** `DPBudgetExceededError` (`errors.py:58-59`) fires when a metric's ε budget is exhausted within the reporting window. Per spec error-taxonomy row 3: drop the AFFECTED metric for that cycle; non-affected metrics report normally (per-metric budgets are independent — one exhausted metric does not block the others).
- **Test contract already declared:** `tests/integration/test_heartbeat_dp_epsilon_budget_per_metric.py` (spec § Test location) — WS-5 wires this to real per-metric tracking. Per `rules/probe-driven-verification.md`, the ε-budget assertion is STRUCTURAL (counter-of-ε-spent vs published-budget, exit-code/numeric), so deterministic enforcement is verifiable without an LLM judge.

---

## Q4 — Signed-consent opt-in Grant Moment + cascade revocation

### Consent flow (first-run, default opt-OUT)

Per spec § "Consent layer" (`foundation-health-heartbeat.md:37-39`):

1. **First-run Grant Moment** with explicit text naming the cryptographic properties (STAR k-anonymity, DP ε, OHTTP IP-stripping). Default is **opt-OUT** — telemetry sends nothing until the user affirmatively grants.
2. **Grant produces a signed Delegation Record** — a cascade-revocable consent artifact. Wiring point: `signed_consent.record_grant_moment` (`envoy/heartbeat/signed_consent.py:44-50`). The Delegation Record's structure + signing live in `specs/trust-lineage.md` (cross-ref `foundation-health-heartbeat.md:66`); the Ledger entry type is `FoundationHealthHeartbeatConsent` (cross-ref `:68`, and `specs/ledger.md`).
3. **Ledger entry types already reserved Phase-01:** `heartbeat_consent_granted` / `heartbeat_consent_revoked` (`specs/mvp-build-sequence.md:79`). `signed_consent.py:13-18` is explicit that the Ledger entry type IS reserved in Phase-01 — this module covers the **heartbeat-side consent EMISSION path the aggregator consumes**, NOT the ledger entry type itself. So WS-5 wires the emission path against an already-existing ledger entry type — clean seam.

### How revocation cascades stop telemetry

1. **User cascade-revokes** consent. Wiring point: `signed_consent.record_cascade_revoke` (`signed_consent.py:52-58`). "Cascade" means the revocation propagates through the Delegation Record's descendant tree (`specs/trust-lineage.md` semantics) — any child delegation derived from the heartbeat consent is also revoked.
2. **Runtime attempts a send after revoke → blocked.** Typed failure: `ConsentRevokedError` (`errors.py:70-71`). Per spec error-taxonomy row 6: stop sends, **clear pending counters**, runtime continues without telemetry. Re-enable requires manual re-opt-in (a fresh Grant Moment).
3. **Test contracts already declared** (spec § Test location): `test_heartbeat_consent_grant_moment.py` (Tier-2 opt-in + signed Delegation Record) and `test_heartbeat_consent_cascade_revoke.py` (revocation halts sends + clears counters). WS-5 wires both to real implementations.

### Consent-to-emit gating (the integration with `maybe_record_flag`)

The clean seam: `maybe_record_flag` (Category-A no-op today) becomes, in WS-5, "validate flag → IF consent-granted-and-not-revoked, increment per-week counter → on weekly cadence, emit". The consent check is the FIRST guard inside the real `maybe_record_flag` body (`client.py:60-68` documents this Phase-02 plan). A revoked-or-never-granted user's `maybe_record_flag` calls remain effectively no-ops — which is why the no-op contract is forward-compatible with consent: opt-out users see exactly today's behavior.

---

## Cadence + payload (WS-5 inherits, do not redesign)

- **Weekly heartbeat; counters reset on successful send** (`foundation-health-heartbeat.md:33-35`).
- **L-01 ritual-coupling debounce:** heartbeat send MUST NOT fire within 24h of a ritual, to avoid coupling user-observable ritual timing to network payload. Typed: `RitualCouplingDebounceTriggered` (`errors.py:66-67`). Test: `test_heartbeat_l01_ritual_coupling_debounce.py`.
- **Per-install random ID, quarterly rotation.** Typed advisory: `RandomIdRotationOverdueWarning` (subclasses `Warning`, NOT `HeartbeatError` — advisory severity, `errors.py:140-145`). Open question item 4: sufficiency against multi-quarter linkage.
- **Reproducible-build attestation:** `ReproducibleBuildAttestationMissingError` (`errors.py:114-115`) — covert-channel defense (T-054); ties to `specs/distribution.md` reproducible-build stream (a separate Phase-02 hook, `mvp-build-sequence.md:208`).

---

## Phase-02 security-review gate (MUST clear before WS-5 ships)

`specs/threat-model.md:52` — **Phase-02 gate: "OHTTP/STAR review"** (alongside full binding security audit, FV tier signing ceremony, CRDT-merge external review, reproducible-build stream). WS-5's crypto + network stack does NOT ship until the OHTTP/STAR external review clears. Threats this stack mitigates (spec § Provenance): T-052 (OHTTP compromise), T-054 (covert channel), T-023/T-024 (falsifiability measurement), T-041 (duress-flag never reported). The "relay+aggregator colluding" residual (`threat-model.md:42`) is the named accepted risk — the review gate's job is to confirm the non-collusion architecture is sound.

---

## Spec gaps identified (additions only — NO spec edits per `rules/spec-accuracy.md`)

1. **STAR-vs-Prio is left unresolved in the spec** ("STAR ... or Prio", `:19`). WS-5 `/todos` MUST pick one before implementation; this document recommends STAR. The spec should be EXTENDED (Phase-02, after the decision lands) to name the chosen protocol — but only after code ships per spec-accuracy MUST-5 (code first, spec describes what landed).
2. **DP noise-injection locus (client vs aggregator) is unspecified.** Spec says "bounded noise on each counter" without naming where. WS-5 `/todos` MUST decide; this document recommends client-side/local DP. Gap is an addition-needed, not a spec defect.
3. **ε-publication granularity is an open question, not a decision** (Open question item 1). Recommend per-metric publication; `/todos` decision needed.
4. **No spec names the HPKE ciphersuite** for OHTTP encapsulation (RFC 9180 KEM/KDF/AEAD triple). WS-5 must select one (recommend the RFC-9458-default `DHKEM(X25519, HKDF-SHA256) + HKDF-SHA256 + AES-128-GCM`); add to spec after code lands.
5. **Foundation Key Config Server has no deployment plan / operator** (explicit in `ohttp.py:13-18`, `registry.py:16-19`). This is a Foundation-OPS gap, not a code gap — WS-5's first session is server standup, and `specs/foundation-ops.md` should gain a deployment-cadence row after the server is live.

---

## Brief/spec corrections (phantom-citation findings)

| #   | Claim source                       | Claim                                                                                               | Reality (grep against `main`)                                                                                                                                                                                                                                                 | Disposition                                                                                                                                                                                                                                                            |
| --- | ---------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Brief**                          | "the 4 stub modules (STAR/Prio, OHTTP, signed-consent, registry handshake)" — implies 4 total stubs | **5-stub partition**: 4 `PhaseDeferredError` modules (Category B) PLUS `HeartbeatClient` (Category A, genuine no-op, `client.py:48`). The brief omits the hot-path no-op consumer, which is the MOST important wiring seam (it's what production calls).                      | **CORRECTION** — not a phantom citation but an undercount that hides the load-bearing seam. WS-5 `/todos` must wire 5 symbols, not 4. Grounded in `envoy/heartbeat/__init__.py:8-35` + `tests/regression/test_r2_h_02_heartbeat_stub_partition.py:14-20`.              |
| 2   | **Spec `:21` + brief**             | OHTTP class symbol implied as `OHTTPClient`                                                         | Real symbol is **`OhttpClient`** (lower-case `httpc`), `ohttp.py:32`. Helpers are `fetch_key_configuration`, `encapsulate_request` (`ohttp.py:44,52`).                                                                                                                        | **CORRECTION** — delegation prompts citing `OHTTPClient` would not resolve. Use `OhttpClient`.                                                                                                                                                                         |
| 3   | **Spec `:19` + `star_prio.py:14`** | STAR expanded as "Signer-Anonymous Reporting Telemetry"                                             | The canonical academic STAR is "**D**istributed **A**ggregation **P**rotocol / Sharded-Threshold-Aggregation-for-Revelation" (Sharma et al., the Brave/CDN-deployed protocol). The spec/module expansion "Signer-Anonymous Reporting Telemetry" is a project-local backronym. | **NAMING NUANCE (not a phantom citation)** — the SYMBOL `StarPrioClient` grounds (`star_prio.py:32`); only the prose expansion differs from the literature. Flag so the OHTTP/STAR external-review gate uses the academically-correct STAR when sourcing the reviewer. |

No CRITICAL phantom citations found: every spec-named symbol used in the wiring seam (`StarPrioClient`, `OhttpClient`, `SignedConsentRecorder`, `HeartbeatRegistryClient`, `HeartbeatClient`, `HeartbeatPayload`, `_validate_payload_schema`, all 10 errors) resolves against `main`. The 3 findings above are an undercount (Q1) + a casing mismatch + a backronym — all HIGH-or-below, none CRITICAL.

---

## Open questions for `/todos`

1. **STAR vs Prio — DECIDE.** Recommend STAR (single-server, native k-anonymity, matches the one-Foundation-operator `foundation-ops.md` row-5 declaration; OHTTP recovers the non-collusion property at the network layer). Blocks Q2 implementation.
2. **DP noise locus — DECIDE.** Recommend client-side/local DP before share-split (holds against compromised aggregator; matches covert-channel-defense framing). Blocks Q3 implementation.
3. **ε publication granularity — DECIDE.** Recommend per-metric published ε (transparency dominates at k≥100). Blocks the transparency-report design.
4. **Tor default — DECIDE.** Recommend opt-in (default off; OHTTP already strips IPs; Tor is defense-in-depth with exit-node cost). `network-security.md:77` item 4.
5. **Session sharding.** Budget is 2–3 sessions. Proposed shard split (per `rules/autonomous-execution.md` capacity budget): **Shard 1** = Foundation-ops server standup (Key Config Server + Relay + STAR aggregator + operator-signed key registry) — this is the existence-check-first prerequisite, ~1 session, no client code. **Shard 2** = client crypto+network (`star_prio` + `ohttp` + `registry` bodies + DP noise + `maybe_record_flag` real body) — load-bearing crypto, invariants: k-floor, ε-budget, share-split correctness, IP-strip, fixed-schema (≈5 invariants, fits one shard). **Shard 3** = consent (`signed_consent` body + cascade-revoke + Ledger emission + the 4 Tier-2/Tier-3 consent/cycle tests). Each shard has a live test feedback loop (the spec § Test-location files), so each may use the 3–5× feedback-loop budget multiplier.
6. **Low-population flags (`channel_imessage_active` etc.) below k=100** — confirm the STAR structural-withhold + transparency-report-the-absence disposition is acceptable, vs adding flags only when cohort viability is established (Open question item 2).
7. **OHTTP/STAR external review gate** (`threat-model.md:52`) — schedule BEFORE WS-5 ships; source a reviewer using the academically-correct STAR naming (correction #3).
