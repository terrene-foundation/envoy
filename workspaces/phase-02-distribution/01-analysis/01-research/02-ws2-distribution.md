# WS-2 Distribution Surfaces — Phase-02 Implementation Architecture

**Workstream:** WS-2 (Distribution surfaces)
**Phase:** 02 (single static Rust binary, 5 OS targets, signed N=3 mirror layer, reproducible builds)
**Scope boundary:** Phase-01 ships `pipx install envoy-agent` (PyPI, kailash-py runtime only — `specs/distribution.md:15`, `DECISIONS.md:64`). Phase-02 ships the static binary. This document is implementation architecture, isolating buildable engineering from the open-legal-gate release tail.

**Authoritative sources read:** `specs/distribution.md` (full Phase-02 section), `DECISIONS.md` ADR-0001 (`:64-65`, `:96-98`) + ADR-0009 legal items (`:303-313`), `specs/threat-model.md` (T-050a/b, T-060), `specs/network-security.md` (TLS/cert-pin for the install channel), `specs/runtime-abstraction.md` (§Security gates per phase, §Runtime attestation).

**One-line release-gate boundary:** Everything that BUILDS and TESTS the binary is unblocked and is autonomous-execution work now; everything that PUBLISHES under the trademarked name or REDISTRIBUTES crypto across borders is gated on ADR-0009 open legal items (`DECISIONS.md:311-312`). The two are cleanly separable at the artifact boundary — see §4.

---

## Q1 — The 5-target build matrix

### The matrix (canonical, per `DECISIONS.md:98` + `specs/distribution.md:82`)

| #   | Target triple                                   | Channel                        | CI host class                                | Risk     |
| --- | ----------------------------------------------- | ------------------------------ | -------------------------------------------- | -------- |
| 1   | `aarch64-apple-darwin` (macOS arm64)            | `curl\|sh`, `brew`             | self-hosted Mac Studio (native)              | LOW      |
| 2   | `x86_64-apple-darwin` (macOS x86_64)            | `curl\|sh`, `brew`             | self-hosted Mac (native or `--target` cross) | LOW      |
| 3   | `x86_64-unknown-linux-gnu` (Linux x86_64)       | `curl\|sh`, apt/dnf P04        | self-hosted Linux / GH-hosted ubuntu         | LOW      |
| 4   | `aarch64-unknown-linux-gnu` (Linux arm64)       | `curl\|sh`                     | self-hosted `esperie-linux-arm` (native)     | MED      |
| 5   | `x86_64-unknown-linux-musl` (Linux musl static) | `curl\|sh` (distroless/Alpine) | self-hosted Linux + musl toolchain           | **HIGH** |
| 6   | `x86_64-pc-windows-msvc` (Windows x86_64)       | `winget`, MSI P04              | GH-hosted `windows-latest` or self-hosted    | MED      |

Note: the spec enumerates **5** size-gate targets (`specs/distribution.md:82`: macOS-arm64, macOS-x86_64, linux-x86_64, linux-arm64, windows-x86_64). ADR-0001 (`:98`) additionally names **musl** in the cross-compilation matrix. **This is a spec gap** — musl is a 6th cell that the size-gate test does not enumerate (see §Spec gaps). I treat musl as a real 6th target because ADR-0001 names it and because it is the riskiest cell.

### CI cross-compile strategy

**Self-hosted runners are the spine.** The kailash-rs self-hosted runners already exist (`.claude/rules/ci-runners.md`; operator-local hosts Jacks-Mac-Studio, Esperies-Mini, esperie-mac, label `esperie-linux-arm` per `ci-runners.operator.local.md`). The binary build runs there because: (a) native macOS arm64 + x86_64 builds need real Apple hardware for code-signing/notarization (Gatekeeper, `specs/distribution.md:88`); (b) native Linux-arm64 build avoids QEMU-emulated cross slowness; (c) the release-cycle wall-clock note is ~45 min Mac Studio + bindings (`ci-runners.operator.local.md` §11).

Recommended cross-compile approach **per cell**:

- **Cells 1–2 (macOS):** native build on Mac Studio. Build arm64 natively; build x86_64 either natively on an Intel Mac or via `cargo build --target x86_64-apple-darwin` (Apple ships the cross-SDK in Xcode). **Recommend native-per-arch over `lipo` universal binary** — a universal binary doubles size against the <50 MB ceiling (Q2), and the channels (`curl\|sh` detecting `uname -m`, `brew` bottles per-arch) want per-arch artifacts anyway.
- **Cell 3 (linux-gnu x86_64):** standard. Self-hosted Linux or GH-hosted `ubuntu-latest`. Build against an old glibc (manylinux-style or `ubuntu-20.04` image) so the binary runs on older distros.
- **Cell 4 (linux-gnu arm64):** native on `esperie-linux-arm` (the runner already exists and was the host for the v3.20.x tag-time bugs per `ci-runners.operator.local.md` §8). Native build avoids `cross`/QEMU.
- **Cell 6 (windows-msvc):** GH-hosted `windows-latest` is the path of least resistance for SmartScreen/Authenticode signing tooling. Embedded-CPython on Windows is well-trodden (python-build-standalone ships `.msvc` artifacts).

### The HIGH-risk cell: musl static + embedded CPython

**Why it is the riskiest cell.** musl static linking + an embedded CPython interpreter is the one combination that does NOT "just work," for three compounding reasons:

1. **CPython is built and tested primarily against glibc.** A fully-static musl CPython must be a deliberately-produced artifact. The canonical source is **`python-build-standalone`** (the same project `uv`/`rye` consume), which ships `x86_64-unknown-linux-musl` standalone interpreters — but the musl variants historically have caveats (static vs dynamic, `install_only` vs `full`).
2. **`dlopen` of C-extension `.so` files breaks under full-static musl.** A fully statically-linked binary cannot `dlopen()` shared objects at runtime. If the embedded Python stack loads any C-extension wheel (and the kailash-rs-bindings runtime is itself a compiled `.so` per ADR-0001 `:55`), a 100%-static musl build will fail at import time. This is the load-bearing failure mode.
3. **`getaddrinfo`/NSS under static musl** differs from glibc — DNS resolution for the N=3 mirror fetch (`specs/distribution.md:33`) can silently misbehave in a fully-static binary.

**Recommended musl strategy (recommendation, with cons stated):**

> **Recommend: ship the musl target as a _mostly-static_ binary (static-CRT-linked Rust + bundled musl-built CPython that retains the ability to load extensions), NOT a 100%-static single ELF — and gate it behind an explicit Tier-3 import-smoke test that actually imports the kailash-rs-bindings `.so` and runs `envoy init` inside an Alpine container.**

- **Pros:** avoids the `dlopen`-under-full-static dead end; reuses `python-build-standalone`'s musl artifact which is maintained upstream; the import-smoke test catches the exact failure mode (extension import) that unit tests cannot see.
- **Cons (real, not glossed):** "mostly-static" weakens the sovereignty pitch slightly (the binary is not a single self-contained ELF with zero runtime deps); it adds an Alpine-container Tier-3 lane to CI; and if `python-build-standalone` drops or breaks its musl variant upstream, the cell loses its source (mitigated by pinning the exact standalone release + mirroring it). The alternative — a true 100%-static build with `dlopen` disabled and ALL extensions statically linked into the interpreter — is a multi-session research spike with no upstream support and is NOT recommended for Phase-02.

**Verdict (build-matrix risk):** 5 of 6 cells are routine native/cross builds on existing self-hosted hardware and carry LOW–MED risk. **The musl cell is the single HIGH-risk item and is the gating engineering uncertainty for Q1.** It does not block the other 5 — recommend building cells 1–4 + 6 first (they unblock `curl\|sh`/brew/winget for the majority of users), and treating musl as a parallel shard with its own import-smoke acceptance gate. If musl proves intractable within its budget, the honest fallback is to ship `linux-gnu` only at Phase-02 and defer musl to a follow-up with a tracking issue — musl users can run the gnu binary on glibc distros, and the pure-Python `kailash-py` escape hatch (ADR-0001 `:75`) remains for the rest.

---

## Q2 — Hitting <50 MB with an embedded interpreter

**The ceiling** (`specs/distribution.md:80`, acceptance gate): every one of the 5 (6) targets must be `<50 MB` measured by `du -sh` on the produced static binary (`tests/acceptance/phase_02/test_binary_size_under_50mb.py`). ADR-0001 (`:97`) pre-accepts the embedded interpreter's **+30–40 MB** cost: "ship with Python interpreter embedded ... Cost: +30–40 MB binary size. Accept."

The arithmetic is tight: 30–40 MB of interpreter leaves **10–20 MB** for the Rust binary + glue + any bundled assets. That is workable but leaves NO room for an offline model in the same artifact (see the tension below).

### Embedding strategy — size implications of each (decision deferred to WS-1)

ADR-0001 `:96` leaves PyO3-compile-time vs uv-managed-subprocess as an **open sub-decision** ("Lean: uv-style for flexibility. Revisit Phase 02 `/analyze`"). **WS-1 owns the pick.** WS-2's job is to state the size implication of each so WS-1 can decide with the size ceiling in view:

| Embedding                                                                                                 | What ships in the binary                                                      | Size implication                                                                                                                                                                                                              | Offline/atomic-install implication                                                                                                             |
| --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **PyO3 compile-time embed** (`pyo3` with `auto-initialize`, interpreter statically linked)                | The CPython interpreter is linked INTO the single Rust binary                 | **Largest single artifact** — the full interpreter (~30–40 MB) is inside the one ELF/Mach-O/PE. Hardest to strip independently. Closest to "one true static binary."                                                          | Fully atomic + offline (ADR-0001 `:97` target). One file, no first-launch fetch.                                                               |
| **uv-managed subprocess** (binary bundles or fetches a `python-build-standalone` interpreter, shells out) | A launcher binary + a managed interpreter dir (possibly fetched on first run) | **Smaller launcher**, but the interpreter still lands on disk (same 30–40 MB, just beside the binary not inside it). If fetched-on-first-launch, the _shipped artifact_ is small but the install is no longer offline-atomic. | If bundled: atomic+offline but not a single file. If fetched: violates the offline-first-run requirement (`specs/distribution.md:17`, `:127`). |

**WS-2's size-only recommendation to WS-1 (not the embedding decision itself):** if the offline-atomic-install requirement (`specs/distribution.md:127` "no network" first-run) is treated as hard — and it is, because `OfflineFirstRunModelMissingError` is in the error taxonomy (`specs/distribution.md:100`) — then **fetch-on-first-launch is disqualified on the offline axis regardless of its size advantage.** That collapses the choice to PyO3-embed vs uv-bundle, both of which land ~30–40 MB on disk. PyO3-embed gives the cleaner single-file sovereignty story (`DECISIONS.md:73`); uv-bundle gives easier independent stripping of the interpreter. WS-1 picks; WS-2 confirms both fit the 10–20 MB headroom for the Rust side.

### How to hit the ceiling — the levers

1. **Strip discipline (REQUIRED, `specs/distribution.md:84`).** "stripping debug symbols is REQUIRED for Phase 02; debug-symbol bundles ship as separate downloadable artifacts under the reproducible-build verification stream." Concretely: `Cargo.toml` release profile `strip = "symbols"`, `panic = "abort"` (drops unwind tables), `opt-level = "z"` or `"s"` (size-optimize), `lto = "fat"`, `codegen-units = 1`. The split-debuginfo goes to a sidecar `.dwp`/`.dSYM`/`.pdb` published separately (this also serves the reproducible-build attestation stream — `specs/distribution.md:39-41`).
2. **Python stdlib pruning.** The embedded CPython does NOT need the full stdlib. Drop `test/`, `idlelib`, `tkinter`, `ensurepip`, `distutils`/`lib2to3`, `__pycache__` for unused modules, and unused encodings. `python-build-standalone`'s `install_only` variant is already pruned; further pruning to only the modules Envoy's `kailash-runtime` actually imports can recover several MB. (Validate the prune list against an import trace of `envoy init` — do not guess.)
3. **Dependency pruning on the Rust side.** Audit the dependency tree with `cargo bloat --release` and `cargo tree`. The bindings glue should pull only what `kailash-runtime` (`DECISIONS.md:33`) needs. Avoid pulling a second TLS stack — reuse one (rustls, which the cert-pinning layer needs anyway per `specs/network-security.md:15`).
4. **Compression as the escape valve.** If a target still overshoots after strip+prune, a self-extracting compressed binary (UPX-style, or a zstd-compressed payload the launcher decompresses to a cache dir on first run) trades startup latency for shipped size. **Recommend AGAINST UPX** (it trips Gatekeeper/SmartScreen/AV heuristics — directly conflicts with `PlatformVerificationFailedError` avoidance, `specs/distribution.md:99`). A zstd-decompress-to-cache approach is safer but reintroduces a first-run write step. Treat compression as a last resort per-target, not a default.

### The offline-model tension (the real size pressure)

`specs/distribution.md:17` + `:127` require an offline local-model bundle (Ollama/llama.cpp/MLX) for offline first-run, AND `:59-61` requires install-to-first-value `<10min mobile / 5min desktop`. A bundled local model is **hundreds of MB to gigabytes** — it CANNOT fit inside the 50 MB binary.

**Recommend: the 50 MB ceiling applies to the binary ONLY; the offline model is a SEPARATE, lazily-fetched-or-side-bundled artifact, never inside the size-gated binary.** This is consistent with the spec — the size gate measures "the produced static binary" (`specs/distribution.md:80-82`), and the model is explicitly a distinct "offline-model bundle" item (`:125`). The first-run flow (`specs/distribution.md:45`) runs Model-picker as a step, so the model is selected/fetched at first-run, not embedded.

- **Pros:** keeps the binary svelte and within gate; lets the user pick their model (BYOM, ADR-0006); avoids shipping a giant model nobody on cloud-inference will use.
- **Cons (real):** "offline first-run with no network" (`specs/distribution.md:127`) then requires the model to arrive via SOME offline path — either (a) a separate downloadable model bundle the user pre-stages, or (b) a degraded-mode minimal prompt-template runtime that can drive the Boundary Conversation without a full LLM (ADR-0006 `:229` already specifies exactly this degraded mode). **Recommend leaning on the ADR-0006 degraded-mode runtime as the true offline-zero-network path**, and treating the bundled local model as an optional larger download — this resolves the tension without bloating the binary. Surface this explicitly in the install-to-first-value test (`specs/distribution.md:66`).

---

## Q3 — N=3 mirror + reproducible-build + signing-key rotation (supply chain)

This is the supply-chain trust spine. Four interlocking mechanisms, each mapping to a threat and an error-taxonomy entry.

### 3a. N=3 mirror-signature verification (T-050a)

**Topology** (`specs/distribution.md:27-33`): (1) Foundation GitHub (primary), (2) IPFS-pinned (secondary), (3) community redistributor from a Foundation-endorsed list. **Installer fetches binary + manifest from all 3; hash match across ≥2 required.** Failure → `MirrorSignatureMismatchError`, **Retry: Never** (`specs/distribution.md:94`).

Implementation shape:

- The signed **manifest** is the trust object — it carries `{binary_hash (sha256), version, signing_key_fingerprint, signature}` for each target. The installer fetches the manifest from all 3 mirrors, verifies each manifest's signature against the pinned Foundation signing key, then fetches the binary and confirms `sha256(binary)` matches the manifest hash on ≥2 of 3 mirrors.
- The fetch channel is TLS 1.3 + **pinned certs shipped with the binary** (`specs/network-security.md:20-22`) — the Foundation mirror endpoints are in the pinned-cert allowlist; user-added CAs are REFUSED for them (`:22`, blocks corporate MITM). `get.envoy.ai` (`specs/distribution.md:21`) is the curl entry point and must be in the pin set.
- ≥2-of-3 quorum is the structural defense: a single compromised mirror cannot poison because its divergent hash loses the 2-of-3 vote. The residual is "all-3-mirrors compromised" (explicitly accepted, `specs/threat-model.md:42`).

### 3b. Reproducible-build determinism across targets (T-060)

**Goal** (`specs/distribution.md:39-41`): third parties independently rebuild the binary from published source and publish attestations; the installer cross-checks. Mismatch → `ReproducibleBuildFailedError`, **Retry: Never** (`specs/distribution.md:95`).

Determinism requires eliminating every source of build-output variance, **per target** (each target triple has its own deterministic output; reproducibility is within-target, not across-target):

- **Pinned toolchain:** exact `rustc` version (`rust-toolchain.toml`), exact CPython standalone release hash, exact dependency lockfile (`Cargo.lock` committed).
- **Strip embedded paths:** `--remap-path-prefix` to erase `/Users/...`/build-host paths; `RUSTFLAGS=-Cdebuginfo=0` already from strip discipline.
- **Zero timestamps:** `SOURCE_DATE_EPOCH` for any embedded build-time; deterministic archive ordering for any bundled assets; reproducible `mtime` in any tar/zip.
- **No build-host nondeterminism:** `codegen-units=1` (already set for size) also helps determinism; disable any `build.rs` that embeds hostname/timestamp/random.
- The reproducible-build refs feed the **`RuntimeAttestation` Ledger entry** (`specs/runtime-abstraction.md:179-184` `reproducible_build_refs[]`), and runtime `startup()` verifies binary hash vs manifest (`:21`). Open question carried from the spec: does startup gate on N-reproducer-confirmations or first-confirmation (`specs/runtime-abstraction.md:240`)?

Note: code-signing/notarization (Gatekeeper/Authenticode) is **applied AFTER** the reproducible build and is itself non-deterministic (signatures embed timestamps). The reproducible-build attestation must therefore be computed on the **pre-signature** binary, and the manifest must record both the unsigned-reproducible hash and the signed-distributable hash. **This is a spec gap** (see §Spec gaps).

### 3c. Signing-key rotation + revoked-key refusal (T-050b)

**Policy** (`specs/distribution.md:35-37`): quarterly scheduled rotation + on-demand on suspected compromise; **installer refuses revoked-key binaries** (`RevokedSigningKeyError`, Retry: Never, `specs/distribution.md:97`); compromise-response runbook with **<72h** target response.

Mechanism:

- **Revocation list** is itself a signed, versioned object the installer fetches (and which must be pin-protected like the manifest). A binary whose manifest `signing_key_fingerprint` appears in the current revocation list is refused — even if its hash matches across mirrors. Revocation dominates hash-match.
- **Rotation** uses an old-key-signs-new-key chain so a client holding only the old pinned key can validate the new key's authority (this is the cert-pin-update-via-signed-binary-release pattern, `specs/network-security.md:21`: "Updates delivered via signed binary release, not via live update"). The runbook lives in `specs/foundation-ops.md` (cross-ref `specs/distribution.md:112`).
- The N=3-mirror + revocation-list + rotation-chain compose: fetch manifest (≥2/3) → verify manifest sig against pinned key OR rotation-chain-validated successor → check fingerprint NOT in revocation list → confirm hash → install.

### 3d. Key-rotation mechanism — recommendation

> **Recommend: rotation = old-key-co-signs-new-key (rotation record), distributed via the same signed-binary-release channel as cert-pin updates, with the revocation list as a separate always-fetched signed object that the installer consults BEFORE hash verification.**

- **Pros:** clients with only the original pinned key can bootstrap trust in every successor key without a live key-server (preserves sovereignty/offline posture); revocation-before-hash means a compromised-but-hash-matching binary is still refused; reuses the cert-pin-update channel already specified in `specs/network-security.md`.
- **Cons (real):** quarterly rotation means the rotation chain grows over time and old clients that never updated must walk a longer chain (mitigated by checkpoint super-keys); the <72h on-demand-revocation target (`specs/distribution.md:37`) depends on the revocation-list-fetch actually reaching offline/air-gapped installs, which it structurally cannot for a truly offline user (accepted residual — an offline user can't learn of a revocation until they reconnect). Surface this honestly in the runbook.

---

## Q4 — Legal-gate isolation (buildable+testable NOW vs SHIP-gated)

The release of this workstream is blocked on **open external legal gates** (ADR-0009 `:303-312`, status "Accepted with pending legal-counsel items"; the three that bite WS-2 are **trademark** `:312`, **composite LICENSE** `:307`, **export-control** `:311`). The design MUST isolate the buildable engineering from the release tail. It cleanly does — here is the explicit map.

### Buildable + testable NOW (no legal gate; autonomous-execution work)

Everything that produces and validates the artifact, under an internal/codename, is unblocked:

| Deliverable                                                                | Why unblocked                                          | Test/acceptance evidence                                                                           |
| -------------------------------------------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| 5(6)-target cross-compile CI (Q1)                                          | Building a binary is not publishing it                 | green build per cell on self-hosted runners                                                        |
| Embedded-interpreter integration + size gate (Q2)                          | Size is a pure engineering property                    | `tests/acceptance/phase_02/test_binary_size_under_50mb.py` (`specs/distribution.md:82`)            |
| musl import-smoke + Alpine Tier-3 (Q1)                                     | Local container test, no distribution                  | import-smoke harness (new, this WS)                                                                |
| N=3 mirror-verify logic + ≥2/3 quorum (Q3a)                                | Can be tested against test-fixture mirrors             | `MirrorSignatureMismatchError` regression test (`specs/distribution.md:94`)                        |
| Reproducible-build determinism (Q3b)                                       | Determinism is verifiable in-house (build twice, diff) | `ReproducibleBuildFailedError` path + diff harness                                                 |
| Signing-key rotation + revoked-key refusal logic (Q3c/d)                   | Testable with throwaway test keys                      | `RevokedSigningKeyError` regression test (`specs/distribution.md:97`)                              |
| Cert-pinning install channel (Q3a)                                         | Pin-verify logic is local                              | `tests/integration/test_t080_cert_pin_mismatch_synthetic_mitm.py` (`specs/network-security.md:64`) |
| First-run flow, upgrade/rollback/uninstall (`specs/distribution.md:43-51`) | Pure application logic                                 | install-to-first-value acceptance (`specs/distribution.md:65-66`)                                  |
| `RuntimeAttestation` wiring (`specs/runtime-abstraction.md:156`)           | Local attestation                                      | startup attestation test                                                                           |

These run on real infrastructure under a **codename / internal mark** and **internal-only signing keys**. The whole pipeline can be green end-to-end without touching a single legal gate.

### SHIP-gated (cannot release until the open legal gate closes)

| Release action                                                                                               | Gating legal item                                                                                                                                                 | Where it bites                                                                                                             |
| ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Publish under the name "Envoy Agent" / "Envoy AI" on `get.envoy.ai`, brew, winget, crates.io, App/Play Store | **Trademark** — ADR-0009 `:312` (USPTO Class 9+42, EUIPO, UK IPO sweep); ADR-0002 `:107` "Accepted (pending trademark sweep)"                                     | the public channel names + the `envoy-agent` namespace + the curl domain                                                   |
| Ship the `kailash-rs-bindings` composite-licensed artifact to end users                                      | **Composite LICENSE** — ADR-0009 `:307` (delineate Apache-2.0 glue + freely-redistributable binary) + SPDX metadata `:308`                                        | the distributed binary's LICENSE file + PyPI/SPDX metadata; release gate runs the `pip-licenses` diff (`DECISIONS.md:322`) |
| Redistribute the binary across borders carrying compiled crypto (Ed25519, SHA-256, Shamir libs)              | **Export-control** — ADR-0009 `:311` + the EAR 742.15(b)(1) advisory (`specs/distribution.md:56`) + `JurisdictionalGateRefusedError` (`specs/distribution.md:96`) | the N=3 mirror redistribution + the jurisdictional install advisory                                                        |

### The isolation boundary (recommendation)

> **Recommend: build, sign-with-internal-keys, and fully test the entire pipeline under a codename now; gate ONLY the three release-tail actions (public-name publish, composite-LICENSE attach, cross-border crypto redistribution) behind the legal items. Wire each gate as a release-time CI check that hard-fails if the corresponding legal artifact is absent — exactly as `DECISIONS.md:322` already mandates for the composite-license check — so the gate is structural, not a human checklist.**

- **Pros:** the ~3–5 autonomous sessions of build/test engineering proceed in full parallel with the (calendar-bound, human-authority, NOT 10x-multipliable per `rules/autonomous-execution.md`) legal track; when the legal gates close, release is a near-zero-effort re-tag + re-sign with production keys + flip the public name; nothing is blocked on nothing.
- **Cons (real):** the codename binary and the production binary differ in name-strings + signing-key + LICENSE-file, so the **reproducible-build attestation must be re-run on the production-named binary** (the codename attestation does not transfer — name strings change the bytes). Budget one reproducibility re-run at release. Also, the export-control gate is jurisdiction-dependent (`JurisdictionalGateRefusedError`): the _binary_ is buildable everywhere, but the _mirror redistribution_ must enforce the jurisdictional advisory at install time — that enforcement logic IS buildable now (it's the `JurisdictionalGateRefusedError` path), only its _legal parameters_ (which jurisdictions) are gated.

**Net:** the legal gates touch only naming, license-file content, and which-jurisdictions-may-fetch. None of them touch whether the binary compiles, fits 50 MB, verifies across N=3 mirrors, or reproduces. The workstream's engineering is fully autonomous-execution work today.

---

## Spec gaps identified (additions only — specs NOT edited per `rules/spec-accuracy.md` + task instruction)

1. **musl is a 6th target in ADR-0001 (`:98`) but absent from the size-gate's 5-target enumeration (`specs/distribution.md:82`).** The size gate must either add `x86_64-unknown-linux-musl` to its target list or the matrix must explicitly drop musl. Recommend adding it (with the import-smoke caveat from Q1). → file as a `/todos` item against `specs/distribution.md` § Binary size constraint.
2. **Pre-signature vs post-signature hash ambiguity in the reproducible-build + manifest contract.** Code-signing (Gatekeeper/Authenticode notarization) is non-deterministic and runs AFTER the reproducible build. The manifest (`specs/distribution.md:33`) and `RuntimeAttestation.reproducible_build_refs` (`specs/runtime-abstraction.md:179`) do not distinguish the reproducible (unsigned) hash from the distributed (signed) hash. The N=3 hash-match and the reproducibility attestation must operate on the unsigned hash; the installer's downloaded-binary check operates on the signed hash. → spec needs a two-hash manifest field.
3. **Offline-model-bundle size is not bounded relative to the 50 MB binary gate.** `specs/distribution.md:80-82` gates the binary; `:17/:125/:127` require an offline model but never state whether it counts against the gate or how it arrives offline-with-no-network. Q2 recommends it is separate + leans on ADR-0006 degraded mode, but the spec should say so explicitly. → spec clarification needed.
4. **Revocation-list fetch path is unspecified for offline installs.** `specs/distribution.md:37` requires <72h revocation response, but an offline-first-run binary (`:127`) has no fetch path to learn of a revocation. The structural residual (offline user can't learn of revocation until reconnect) should be named explicitly in the threat residuals. → cross-ref `specs/foundation-ops.md` runbook.
5. **Universal-binary vs per-arch macOS decision is unstated.** The size ceiling effectively forbids a `lipo` universal binary (it ~doubles size); the spec should record per-arch as the macOS distribution shape. → spec note.

---

## Open questions for /todos

1. **Embedding strategy hand-off:** WS-1 owns the PyO3-embed vs uv-bundle pick (`DECISIONS.md:96`). WS-2 has shown fetch-on-first-launch is disqualified by the offline requirement. Confirm WS-1 decides between the two on-disk options with the 10–20 MB Rust-side headroom as a hard constraint. **Sequencing: WS-1 embedding decision blocks WS-2 size-gate finalization.**
2. **musl shard disposition:** approve the "mostly-static + import-smoke" recommendation, OR explicitly defer musl to a follow-up with a tracking issue and ship `linux-gnu` only at Phase-02? (Recommend the former; the latter is the honest fallback if the shard overruns its budget.)
3. **`python-build-standalone` dependency:** accept the upstream dependency for the embedded interpreter (esp. musl), with a pinned-release + mirror-it mitigation? Or build CPython from source in-CI for full reproducibility control? (Source-build is more reproducible but is a multi-session spike per target.)
4. **Reproducer count gate:** does runtime `startup()` gate on first-reproducer-confirmation or N-confirmations (`specs/runtime-abstraction.md:240`, `specs/distribution.md` OQ#2)? Affects whether install blocks on attestation availability.
5. **Codename for the pre-trademark build pipeline:** pick an internal codename + internal signing-key set so the full build/test pipeline runs now under a name that is provably NOT the trademarked mark. (Trivial but blocks starting the buildable work cleanly.)
6. **Jurisdiction parameter source for `JurisdictionalGateRefusedError`:** the enforcement logic is buildable now; the jurisdiction LIST is export-control-gated. Where does the install-time advisory read the current jurisdiction parameters from, and who signs that list? (Cross-ref `specs/foundation-ops.md`.)
7. **Compression last-resort policy:** if a target overshoots 50 MB after strip+prune, confirm zstd-decompress-to-cache (NOT UPX, which trips Gatekeeper/SmartScreen) as the sanctioned escape valve — and accept the first-run write step it reintroduces.
