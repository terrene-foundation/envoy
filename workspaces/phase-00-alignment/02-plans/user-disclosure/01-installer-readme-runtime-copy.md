# User-facing disclosure — installer / README / runtime-picker copy

**Status:** DRAFT for Phase-00 exit gate (ROADMAP §23 + ADR-0009 sub-item 4).
**Audience:** envoy maintainers (adoption), Foundation legal counsel (substantive review of the disclosure language), Foundation Secretary (board minute paragraph that endorses the disclosure language).
**Source contract:**

- ROADMAP.md line 23 — "Draft user-facing disclosure text (installer screen, README, runtime-picker copy)."
- ADR-0009 §309 sub-item 4 — "User-facing disclosure. Installer screen + README + runtime-picker copy explicitly name the closed-binary component and the fully open-source alternative."

**Why this draft exists:** ADR-0009 commits envoy to "no hidden defaults — installer discloses transparently which runtime is active and how to switch." That commitment lives or dies on the WORDS the user actually reads. This draft proposes those words across three surfaces. The legal substance is in `01-...LICENSE-draft.md` + `02-...SPDX-draft.md` + `03-license-compatibility-statement.md`; this draft translates that substance into plain language a non-technical user can act on, per `rules/communication.md`.

The three surfaces this disclosure covers:

1. **Installer screen** — what the user sees during `pipx install envoy-agent` (Phase 01) and `curl ... | sh` / `brew install` / `winget install` (Phase 02+).
2. **README licensing section** — the 30-second version of the licensing posture, scannable on the GitHub project page.
3. **Runtime-picker copy** — the first-run choice between `kailash-rs-bindings` (default) and `kailash-py` (opt-in alternative). Phase 02+.

A fourth surface — the runtime-swap CLI command (`envoy runtime switch`) — inherits the runtime-picker copy with a small "you've already chosen X; switch to Y?" preface; the inheritance shape is documented in §4.4.

---

## 1. Drafting principles

The Foundation rule `.claude/rules/communication.md` governs this draft. The relevant clauses:

- **Plain language.** "Match the user's level if they speak technically." On the installer screen the user has not yet typed a single command — assume a non-technical reader. On the runtime-picker the user has at least typed `envoy init` — assume slightly higher technical comfort but still no Foundation-spec vocabulary.
- **Outcomes, not implementation.** "Users can now sign up and receive a welcome email" not "Implemented POST /api/users endpoint with SendGrid integration." Applied here: "Envoy runs faster" not "kailash-rs-bindings is a PyO3-built wheel that ships compiled Rust core via composite LicenseRef-kailash-rs-bindings-binary-grant".
- **Frame decisions as impact.** "What each option does (plain language), what it means for users/business, the trade-off, the recommendation."
- **No unexplained jargon.** Where a Foundation term does need to appear (e.g. "Apache 2.0", "Terrene Foundation", "Trust Vault"), the first occurrence is followed by a one-line plain-language gloss.
- **Approval gates.** The installer's "do you accept these terms" prompt MUST give the user a path to read the actual license text before consenting. The runtime-picker MUST give the user a path to "?" → see the full FAQ before choosing.

The disclosure is also bound by ADR-0009's "no hidden defaults" commitment. Any surface that picks a runtime for the user MUST disclose that pick AND the alternative AND how to switch.

## 2. Phase migration of the disclosure

The disclosure copy varies by phase because the install surface and the runtime model evolve:

| Phase    | Install surface                                                                      | Runtime model                                                 | Disclosure surfaces                                                        |
| -------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 01 (MVP) | `pipx install envoy-agent` (interim, Python only)                                    | `kailash-py` only — no picker yet                             | Installer §3.1; README §4 (Phase-01 variant)                               |
| 02+      | `curl ... \| sh` static binary + `brew install` + `winget install` + `cargo install` | Pluggable, picker on first run; default `kailash-rs-bindings` | Installer §3.2; README §4 (Phase-02 variant); Runtime-picker §5            |
| 04+      | Mobile (Flutter iOS + Android via QR pairing)                                        | Pluggable; mobile bundles `kailash-rs-bindings`               | Mobile pairing screen — out of scope for this draft (Phase-04 deliverable) |

**Phase-00 deliverable:** all three sets of copy below. Adoption happens at the start of each corresponding phase.

## 3. Installer disclosure copy

### 3.1 Phase 01 — `pipx install envoy-agent`

The Phase 01 install path is `pipx install envoy-agent`. This is a standard pip-style install; the user does not see an interactive consent screen during install itself. The disclosure runs at first launch (`envoy init`), before any data is collected and before the Trust Vault is created.

```
$ envoy init

Welcome to Envoy.

Before you continue, here's what you should know.

  • Envoy is open-source software. The code is Apache 2.0 — you can read it,
    fork it, modify it, redistribute it. Source: github.com/<envoy-repo>.

  • Envoy is stewarded by the Terrene Foundation, a non-profit organisation
    in Singapore. The Foundation has no commercial interest in your data —
    Envoy never calls home, never registers your device, and there is no
    paid tier.

  • You will be asked, in the next 15 minutes, to set boundaries on what
    Envoy may do for you. Those boundaries are the heart of the product.
    Envoy will refuse to act outside them.

  • Envoy stores everything locally. Your messages, your boundaries, and
    a permanent log of every action Envoy takes for you are kept on this
    device, encrypted with a passphrase you choose.

This is the Phase 01 (MVP) release. The runtime is fully open-source Python.
Phase 02 will add a faster Rust runtime as the default; you'll be able to
keep the open-source one if you prefer.

Continue with setup? [Y/n]
```

**Design notes:**

- No legal vocabulary in the consent prompt. "Apache 2.0" appears once with a plain-language gloss ("you can read it, fork it, modify it, redistribute it"). "Terrene Foundation" appears once with a plain-language gloss ("a non-profit organisation in Singapore"). No "CC BY 4.0" — the user is consenting to install Envoy, not to license the spec family.
- The "calls home / registers / paid tier" sentence preempts the three concerns most prosumers have at first install. This is structural — it says what Envoy _doesn't_ do, which is more reassuring than a list of what it does do.
- The Phase-02 forward-look ("you'll be able to keep the open-source one if you prefer") is included because users installing Phase 01 will upgrade to Phase 02 and the disclosure surface will change. Mentioning it now removes the "wait, did I sign up for something different?" reaction at upgrade.
- The default response is `Y` — the user has already opted in by typing `envoy init`. The `n` option exits without creating a Trust Vault.

### 3.2 Phase 02+ — `curl … | sh` / `brew` / `winget` / `cargo`

Phase 02 has multiple install paths. The shared disclosure runs on the first `envoy init` after install (same trigger point as Phase 01) but with one extra paragraph for the runtime model:

```
$ envoy init

Welcome to Envoy.

Before you continue, here's what you should know.

  • Envoy is open-source software. The code is Apache 2.0 — you can read it,
    fork it, modify it, redistribute it. Source: github.com/<envoy-repo>.

  • Envoy is stewarded by the Terrene Foundation, a non-profit organisation
    in Singapore. The Foundation has no commercial interest in your data —
    Envoy never calls home, never registers your device, and there is no
    paid tier.

  • Envoy ships with two runtime options:
      [1] Fast (default) — a Rust-built runtime from the Terrene Foundation.
          Free, no registration, freely shareable. Source for the wrapper
          is open; the compiled core is distributed as a binary.
      [2] Open — a fully open-source Python runtime from the Foundation.
          Free, source you can read, fork, and modify. About 8× slower on
          the hot path; same security and behaviour as option 1.

    Both work the same. You can switch later with `envoy runtime switch`.
    The next screen lets you pick.

  • Envoy stores everything locally. Your messages, your boundaries, and
    a permanent log of every action Envoy takes for you are kept on this
    device, encrypted with a passphrase you choose.

  • You will be asked, in the next 15 minutes, to set boundaries on what
    Envoy may do for you. Envoy will refuse to act outside them.

Continue with setup? [Y/n]
```

**Design notes (delta from Phase 01):**

- The runtime bullet replaces the Phase-01 "Phase 02 will add" forward-look. It IS Phase 02 — the user is choosing now.
- "About 8× slower on the hot path" is a honest, quantified disclosure. The exact number traces to acceptance-metrics.md (Rust <10ms, Python <80ms hot-path P50). Not "somewhat slower" — that hides the magnitude.
- "Same security and behaviour as option 1" addresses the concern most users have when they see "default vs alternative" — that the alternative is the worse path. The runtime conformance contract (`01-runtime-swap-contract.md`) makes this claim verifiable. The sentence is the disclosure-surface manifestation of that contract.
- The "freely shareable" phrase replaces "freely-redistributable binary" — same legal meaning, plain language.

### 3.3 The full-license read path

After the consent prompt above, a user pressing `?` (or any non-y/n key) sees:

```
Choose one to read more, or press Enter to return:
  [1] Envoy's licence (Apache 2.0)                    — code you can fork
  [2] Foundation specifications licence (CC BY 4.0)    — methodology you can build on
  [3] How the Rust runtime is distributed              — composite licence, freely shareable
  [4] What Envoy does NOT do (privacy posture)         — telemetry, accounts, networking
  [5] Foundation Trust Lineage and what gets signed    — your keys, your audit log
  [6] Where to read more                               — links to CHARTER, DECISIONS, ROADMAP

Choice [1-6] or Enter:
```

Each option opens a paginated text screen with the relevant content. The actual license text (LICENSE file) is shown verbatim under [1]. The Phase-02 "[3] How the Rust runtime is distributed" option shows the LICENSE-BINARY-GRANT text (the freely-redistributable grant, no-modification clause, export-control note) verbatim plus a 3-paragraph plain-language summary.

**Design notes:**

- Six options, each addresses a real concern users have. None are filler.
- The user is not required to read any of them — `Enter` returns to the install flow with consent still pending.
- Option [3] makes the composite-license disclosure inspectable. This is what closes the "no hidden defaults" commitment from ADR-0009.

## 4. README licensing section

The README's licensing section is currently 4 lines (README.md §65). The proposed replacement gives the 30-second version with link-outs for users who want detail. The replacement is for the section currently titled "## License":

```markdown
## Licensing — what's free, what's open

**Short version**

| Layer                                                     | Licence                                                              | Free | Source                         |
| --------------------------------------------------------- | -------------------------------------------------------------------- | ---- | ------------------------------ |
| Envoy itself (this repo)                                  | Apache 2.0                                                           | Yes  | Open                           |
| Foundation methodology (CARE / EATP / CO / PACT)          | CC BY 4.0                                                            | Yes  | Open                           |
| `kailash-py` runtime (open Python alternative)            | Apache 2.0                                                           | Yes  | Open                           |
| `kailash-rs-bindings` runtime (Rust-accelerated, default) | Apache 2.0 (wrapper) + freely-redistributable binary (compiled core) | Yes  | Wrapper open; core binary-only |
| Community skills via `SKILL.md` (you install)             | MIT or similar permissive licence (the skill author chooses)         | Yes  | Open                           |

**No payment, no registration, no commercial terms — at any layer, ever.**

**Two runtimes, your choice.**
On first run Envoy asks which runtime to use. The default is `kailash-rs-bindings` because it's faster on the hot path. The alternative is `kailash-py` because it's fully open-source. Both are free, both are hosted by the Terrene Foundation. You can switch later with `envoy runtime switch`. See [DECISIONS §ADR-0009](DECISIONS.md) for the full architecture.

**Why a binary at all?**
The Rust runtime ships with a compiled core because compiling Rust on the user's machine on first install is slow, fragile, and requires a Rust toolchain most users don't have. The compiled binary is freely redistributable — you can copy it, ship it inside your own product, include it in a Linux distribution. The wrapper around it is open-source Apache 2.0 code. If you prefer not to use the binary at all, the open-source `kailash-py` runtime is one keystroke away.

**Reading the actual licences.**

- Envoy code: [LICENSE](LICENSE)
- Foundation specs: CC BY 4.0 — see [terrene.foundation](https://terrene.foundation)
- `kailash-rs-bindings` composite: [legal draft](workspaces/phase-00-alignment/02-plans/legal/01-kailash-rs-bindings-LICENSE-draft.md) (becomes a real LICENSE file in the wheel at Phase 02)
- License compatibility analysis: [03-license-compatibility-statement.md](workspaces/phase-00-alignment/02-plans/legal/03-license-compatibility-statement.md)
- Why these choices: [DECISIONS §ADR-0009](DECISIONS.md)
```

**Design notes:**

- The table is the 5-second version: a user scanning README sees Free/Open at every layer and gets a confidence signal in two seconds.
- The "Why a binary at all?" paragraph anticipates the question every open-source-fluent reader will ask. Answering preemptively is more credible than waiting for the GitHub issue.
- The Phase-01 README has the same shape but the runtime row reads "`kailash-py` runtime (Phase 01: only runtime; Phase 02+: opt-in alternative)" and the "Two runtimes" paragraph is replaced with "Phase 01 ships with `kailash-py` only — pure Python, fully open. Phase 02 will add a faster Rust runtime as the default; you'll be able to keep the open one if you prefer."
- The `MIT or similar permissive licence` row for community skills clarifies the third license family (per the compatibility statement §1) without forcing the user to read the compatibility statement.

## 5. Runtime-picker copy (Phase 02+)

The runtime-picker is the SECOND screen of `envoy init` in Phase 02+. It runs after the consent prompt in §3.2 and before the Boundary Conversation begins. The picker IS the choice the consent prompt previewed.

```
$ envoy init

  ...consent prompt accepted...

Pick your runtime.

Both options are free. Both are hosted by the Terrene Foundation. Both
deliver the same security and behaviour. The difference is performance
and licensing posture.

  [1] Fast — kailash-rs-bindings (default, recommended)
      Speed:        ~8× faster than option 2 on the hot path
      Wrapper:      Apache 2.0, source open
      Compiled:     Rust core ships as a binary; freely shareable;
                    no fee, no registration, no terms beyond redistribute-as-is
      Hosted by:    Terrene Foundation, on PyPI as part of the kailash package
      Switch later: yes, with `envoy runtime switch`

  [2] Open — kailash-py (alternative)
      Speed:        baseline (about 8× slower than option 1)
      Wrapper + core: pure Python, Apache 2.0, fully forkable
      Hosted by:    Terrene Foundation, on PyPI
      Switch later: yes, with `envoy runtime switch`

Press 1 or 2 to choose. Press ? for the FAQ. Press q to abort setup.

Choice [1/2/?/q]:
```

**Pressing `?` shows:**

```
Frequently asked questions

Q: Are both runtimes really equivalent?
A: For everything that matters — yes. They use the same security
   primitives, produce the same audit log, and refuse the same
   actions. Behaviour is verified by a published conformance test
   suite that runs on every release.

Q: Why isn't the Rust core open-source?
A: The Foundation distributes the compiled binary so you don't need
   a Rust toolchain to install Envoy. The Rust source itself is held
   by the Foundation and not on a public registry. If you want a
   fully-open path, choose option 2.

Q: Will my Trust Vault work on either runtime?
A: Yes. The encrypted vault format is identical across runtimes.
   You can switch back and forth without losing anything.

Q: What happens if the Foundation stops distributing the Rust binary?
A: Option 2 (kailash-py) continues to work indefinitely. The Foundation
   has an obligation under its charter to maintain at least one
   fully-open-source runtime. If option 1 ever became unavailable,
   `envoy runtime switch open` keeps you running.

Q: Can I see what each runtime does?
A: Yes. Option 1's Python wrapper is at github.com/<bindings-repo>;
   the Rust core's behaviour is documented in published specifications
   (terrene.foundation). Option 2's source is at
   github.com/terrene-foundation/kailash-py.

Q: Does either runtime call home or share my data?
A: Neither does. Envoy runs entirely on this device. The runtimes
   contain only local logic — no telemetry, no analytics, no
   account registration. You can verify this with a network monitor.

Q: Is option 1's binary signed?
A: Yes. The binary's hash is signed by the Foundation and verified
   on every Envoy startup. If the binary on disk doesn't match the
   signed hash, Envoy refuses to start and prints an error.

Q: Can I install option 1 and inspect the binary first?
A: Yes. After install, run `envoy runtime attest` to see the
   binary hash, the Foundation's signature, and the algorithm
   identifier. Compare the hash against the Foundation's published
   release notes.

Q: What's the catch?
A: Option 1's binary is closed-source — you can run it and ship it
   but not modify it. If that bothers you, option 2 is right for
   you. There's no other catch.

Press q to return to the picker.
```

**Design notes:**

- Nine FAQ entries. Each one is a question a real user will have. None are marketing.
- The "What's the catch?" entry is the most important. Users are conditioned to suspect a catch when something free is presented as fast-and-default. The honest answer ("the binary is closed-source") preempts the suspicion.
- The "Foundation has an obligation under its charter" sentence is the durability commitment ADR-0009 §300 makes operational. It is a real charter commitment, not marketing.
- "Run `envoy runtime attest`" is a verifiable affordance. Users who care about provenance can check it themselves.
- Each FAQ answer is ≤4 lines. A user who reads the whole FAQ takes ~90 seconds.
- The default highlight on `[1]` (the recommended option) is intentional and disclosed. ADR-0009 commits to this default; the picker's `recommended` annotation is the disclosure surface.

### 5.1 The "no choice" path

If a user types `envoy init` headless (e.g. CI / scripted install / mobile bootstrap) the runtime-picker degrades gracefully. The CLI accepts a `--runtime <fast|open>` flag that pre-answers the picker, suppresses the prompt, and writes a Ledger entry recording the non-interactive choice:

```
$ envoy init --runtime open

  ...consent prompt skipped via --consent flag if also passed...
  Runtime: kailash-py (chosen via --runtime open)
  ...Boundary Conversation begins...
```

In the Ledger, the entry records that the choice was non-interactive so a future audit knows the user did not see the disclosure screen. This satisfies ADR-0009 "no hidden defaults" — even in headless mode, the choice is auditable.

### 5.2 The "switch later" command — `envoy runtime switch`

```
$ envoy runtime switch

You're currently running:
  kailash-rs-bindings (Fast, default)

Switching to the open runtime:
  kailash-py (Open, fully-open-source)

This will:
  - Stop the current Envoy session.
  - Verify the new runtime's binary attestation.
  - Migrate your Trust Vault. (No data loss; vault format is identical.)
  - Restart Envoy on kailash-py.

You will be asked for your Trust Vault passphrase before the switch.
This is required by the Foundation security policy — switching
runtimes is a sensitive operation that touches your keys.

Proceed? [y/N]
```

The switch command inherits the runtime-picker's plain-language framing. A user who has already chosen once doesn't re-read the FAQ; they confirm a sensitive operation.

**Design notes:**

- The default is `N` for the switch (unlike `Y` for first-run setup). A switch is a sensitive operation; the conservative default protects against accidental keypress.
- The four bullets describe the operation in plain English. "No data loss" is the load-bearing reassurance.
- The passphrase requirement is disclosed as a Foundation security policy, not as an envoy-internal hurdle. This frames the friction as protective, not bureaucratic.

### 5.3 The "show what runtime is active" affordance

ADR-0009 §299 commits to "no hidden defaults". The `envoy status` command MUST surface the active runtime:

```
$ envoy status

Envoy: ready
Runtime: kailash-rs-bindings 0.X.Y (Fast, default)
Binary attestation: verified at 2026-05-01T09:14:22Z (sha256:abc123…)
Trust Vault: locked (run `envoy unlock` to use)
Ledger: 1,247 entries; head sha256:def456…
Boundary set: parent-household-v1 + custom additions

To switch runtime: envoy runtime switch
To inspect runtime: envoy runtime attest
```

This is the third-most-frequent place the runtime is disclosed (after install and runtime-picker). Including it in `envoy status` means a user who never read the install screen still sees the runtime every time they check Envoy's state.

## 6. Mobile pairing screen (Phase 04+)

The Phase-04 Flutter clients pair to a desktop Envoy via QR code. The pairing screen is out of scope for this draft (Phase 04 deliverable per ROADMAP §83) but the disclosure inheritance pattern is fixed:

- The mobile app inherits the desktop's runtime choice — there is no second runtime-picker on mobile.
- The mobile pairing screen displays the desktop's runtime in plain language: "This Envoy is running the Fast runtime." The user MAY initiate `envoy runtime switch` on the desktop from the mobile app's settings; the actual switch happens on the desktop.

The Phase-04 disclosure draft adopts the same plain-language patterns established here.

## 7. Strings table for translation

For Phase 02+ the disclosure surfaces are translated to the supported locales (Phase 02 ships English; Phase 03+ adds locales per channel-adapter coverage). The strings below are the canonical English entries; translations preserve the plain-language register and the legal accuracy.

| Key                                 | English                                                                                                                                                                                                                                            |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `installer.welcome`                 | "Welcome to Envoy."                                                                                                                                                                                                                                |
| `installer.consent.opensource`      | "Envoy is open-source software. The code is Apache 2.0 — you can read it, fork it, modify it, redistribute it."                                                                                                                                    |
| `installer.consent.foundation`      | "Envoy is stewarded by the Terrene Foundation, a non-profit organisation in Singapore. The Foundation has no commercial interest in your data — Envoy never calls home, never registers your device, and there is no paid tier."                   |
| `installer.consent.boundaries`      | "You will be asked, in the next 15 minutes, to set boundaries on what Envoy may do for you. Envoy will refuse to act outside them."                                                                                                                |
| `installer.consent.local`           | "Envoy stores everything locally. Your messages, your boundaries, and a permanent log of every action Envoy takes for you are kept on this device, encrypted with a passphrase you choose."                                                        |
| `installer.consent.runtime.preview` | "Envoy ships with two runtime options: a Fast Rust runtime (default) and a fully open-source Python runtime. Both work the same. The next screen lets you pick."                                                                                   |
| `installer.consent.proceed`         | "Continue with setup? [Y/n]"                                                                                                                                                                                                                       |
| `picker.heading`                    | "Pick your runtime."                                                                                                                                                                                                                               |
| `picker.fast.label`                 | "Fast — kailash-rs-bindings (default, recommended)"                                                                                                                                                                                                |
| `picker.fast.speed`                 | "~8× faster than option 2 on the hot path"                                                                                                                                                                                                         |
| `picker.fast.wrapper`               | "Apache 2.0, source open"                                                                                                                                                                                                                          |
| `picker.fast.compiled`              | "Rust core ships as a binary; freely shareable; no fee, no registration, no terms beyond redistribute-as-is"                                                                                                                                       |
| `picker.open.label`                 | "Open — kailash-py (alternative)"                                                                                                                                                                                                                  |
| `picker.open.speed`                 | "baseline (about 8× slower than option 1)"                                                                                                                                                                                                         |
| `picker.open.both`                  | "pure Python, Apache 2.0, fully forkable"                                                                                                                                                                                                          |
| `picker.faq.equivalent.q`           | "Are both runtimes really equivalent?"                                                                                                                                                                                                             |
| `picker.faq.equivalent.a`           | "For everything that matters — yes. They use the same security primitives, produce the same audit log, and refuse the same actions. Behaviour is verified by a published conformance test suite that runs on every release."                       |
| `picker.faq.binary.q`               | "Why isn't the Rust core open-source?"                                                                                                                                                                                                             |
| `picker.faq.binary.a`               | "The Foundation distributes the compiled binary so you don't need a Rust toolchain to install Envoy. The Rust source itself is held by the Foundation and not on a public registry. If you want a fully-open path, choose option 2."               |
| `picker.faq.vault.q`                | "Will my Trust Vault work on either runtime?"                                                                                                                                                                                                      |
| `picker.faq.vault.a`                | "Yes. The encrypted vault format is identical across runtimes. You can switch back and forth without losing anything."                                                                                                                             |
| `picker.faq.unavailable.q`          | "What happens if the Foundation stops distributing the Rust binary?"                                                                                                                                                                               |
| `picker.faq.unavailable.a`          | "Option 2 (kailash-py) continues to work indefinitely. The Foundation has an obligation under its charter to maintain at least one fully-open-source runtime. If option 1 ever became unavailable, `envoy runtime switch open` keeps you running." |
| `picker.faq.callhome.q`             | "Does either runtime call home or share my data?"                                                                                                                                                                                                  |
| `picker.faq.callhome.a`             | "Neither does. Envoy runs entirely on this device. The runtimes contain only local logic — no telemetry, no analytics, no account registration. You can verify this with a network monitor."                                                       |
| `picker.faq.signed.q`               | "Is option 1's binary signed?"                                                                                                                                                                                                                     |
| `picker.faq.signed.a`               | "Yes. The binary's hash is signed by the Foundation and verified on every Envoy startup. If the binary on disk doesn't match the signed hash, Envoy refuses to start and prints an error."                                                         |
| `picker.faq.attest.q`               | "Can I install option 1 and inspect the binary first?"                                                                                                                                                                                             |
| `picker.faq.attest.a`               | "Yes. After install, run `envoy runtime attest` to see the binary hash, the Foundation's signature, and the algorithm identifier. Compare the hash against the Foundation's published release notes."                                              |
| `picker.faq.catch.q`                | "What's the catch?"                                                                                                                                                                                                                                |
| `picker.faq.catch.a`                | "Option 1's binary is closed-source — you can run it and ship it but not modify it. If that bothers you, option 2 is right for you. There's no other catch."                                                                                       |
| `switch.preface`                    | "You're currently running:"                                                                                                                                                                                                                        |
| `switch.target`                     | "Switching to the open runtime:" / "Switching to the fast runtime:"                                                                                                                                                                                |
| `switch.steps`                      | "This will: stop the current Envoy session; verify the new runtime's binary attestation; migrate your Trust Vault. (No data loss; vault format is identical.) Restart Envoy on the new runtime."                                                   |
| `switch.passphrase`                 | "You will be asked for your Trust Vault passphrase before the switch. This is required by the Foundation security policy — switching runtimes is a sensitive operation that touches your keys."                                                    |
| `switch.proceed`                    | "Proceed? [y/N]"                                                                                                                                                                                                                                   |
| `status.runtime`                    | "Runtime: {runtime_name} {version} ({label})"                                                                                                                                                                                                      |
| `status.attestation`                | "Binary attestation: verified at {timestamp} ({hash_prefix})"                                                                                                                                                                                      |

## 8. What this disclosure does NOT cover

The disclosure surfaces above intentionally do NOT mention:

- **Foundation specs (CARE / EATP / CO / PACT) by name.** The user is not consenting to a spec; they are using software that implements them. CC BY 4.0 attribution lives in NOTICE / THIRD-PARTY-NOTICES.json (per the compatibility statement §7), not in the user-facing copy. The README's licensing table is the only user-facing surface that names them, and even there the framing is "methodology you can build on".
- **The conformance contract.** The user does not need to know test-vector details. They need to know "behaviour is verified by a published conformance test suite that runs on every release" — the FAQ entry covers this in 35 words.
- **The legal-counsel sub-items in ADR-0009.** Counsel-engagement items (EU AI Act disclosure, EU Software Directive Art. 6 carve-out, Singapore CLG capacity-to-grant) are pre-publication concerns; once published, the user reads the LICENSE file as final, not the counsel discussion.
- **The Foundation board endorsement.** Once endorsed, the runtime-pluggability model is just "how Envoy is distributed" — the user doesn't need to read the board minute. The board endorsement stays in DECISIONS / CHARTER.

This narrowness is deliberate. The disclosure must be CLEAR (`rules/communication.md`) — not COMPREHENSIVE.

## 9. Counsel + Foundation review checklist

Before adoption, this draft requires sign-off from:

1. **Foundation legal counsel** — confirm the §3.x consent prompts and §5 picker copy are legally sufficient as the user-facing disclosure required by ADR-0009 sub-item 4. Specifically: does "freely shareable" + "freely-redistributable" parity in §3.2 satisfy the binary-grant disclosure obligation (per `01-...LICENSE-draft.md` PART B (1))?
2. **Foundation Secretary** — confirm the §5 FAQ "What happens if the Foundation stops distributing the Rust binary?" answer accurately reflects the charter obligation. The answer claims "The Foundation has an obligation under its charter to maintain at least one fully-open-source runtime." If this is not a current charter clause, either the charter is amended OR the FAQ is reworded.
3. **`kailash-rs-bindings` maintainers** — confirm the Phase-02 picker speed claim "~8× faster on the hot path" matches the achievable performance per their benchmarks. The number traces to acceptance-metrics.md (Rust <10ms, Python <80ms hot-path P50). If the gap turns out to be larger or smaller, update the picker copy and the README.
4. **`kailash-py` maintainers** — confirm the Phase-02 picker "fully forkable" claim is accurate (no contributor-license-agreement clauses that would prevent forks).
5. **envoy maintainers** — adopt §5.1 `--runtime <fast|open>` flag in the CLI design; adopt §5.3 `envoy status` runtime-disclosure line.

## 10. Open questions / Phase-02 carry-forward

1. **The "kailash" PyPI package name vs the runtime label.** The picker copy uses "kailash-rs-bindings" and "kailash-py" as runtime labels. If the actual PyPI distribution uses different names (per claim-verification sweep §NOTICE concern about NOTICE §20), the labels need to match what the user sees in `pip list`. Phase-02 carry-forward.
2. **Locale support for Phase 02.** Strings table §7 is English-canonical. Phase 02 ships with English only; Phase 03+ adds locales. Translations must preserve plain-language register; the legal-substantive phrases (`Apache 2.0`, `Terrene Foundation`, `freely-redistributable`) MUST translate to legally-equivalent terms in each locale, with counsel review per locale.
3. **First-run-headless install.** §5.1 introduces a non-interactive runtime override (`--runtime`). Should the Ledger entry for headless installs include the rationale (CI environment? Mobile bootstrap? Explicit `--non-interactive` flag?), so a future audit can distinguish "user opted out of disclosure" from "automation skipped disclosure"? Phase-02 design item.
4. **Trademark substitution.** Once ADR-0002 closes (legal mark final), every "Envoy" in the disclosure is replaced with the legal mark. This is mechanical — no copy rewrite, just a name-change pass. Carry to post-Phase-00.
5. **Foundation charter clause for runtime-availability obligation.** §5 FAQ "What happens if the Foundation stops distributing…" relies on a specific charter commitment. If the charter does not yet have this clause, ADR-0013 (placeholder) is the channel for amending the charter to include it. Phase-00 carry-forward to the Foundation board.
6. **The runtime-attestation publication channel.** §5 FAQ "Is option 1's binary signed?" claims the Foundation publishes signed binary hashes. The Foundation's release-notes channel (URL? RSS feed? GitHub Releases? `terrene.foundation/releases/`?) is not yet operationalised. Phase-02 carry-forward.

---

**Cross-references:**

- `01-kailash-rs-bindings-LICENSE-draft.md` — the legal text the §3.3 [3] option shows verbatim
- `02-kailash-rs-bindings-SPDX-draft.md` — the SPDX expression that scanners see (no user-facing surface)
- `03-license-compatibility-statement.md` — three-license analysis the README §"Licensing — what's free, what's open" table summarises
- `01-envoy-concept-one-pager.md` §"Appendix — what users see" — the prior installer-screen draft this document supersedes (the appendix is suitable for a board paragraph; this draft is the production user-facing copy)
- `01-sweep.md` §A item 4 (channel-count framing) — README revision aligns with that finding
- ADR-0009 §299 — "Installer discloses transparently which runtime is active and how to switch. No hidden defaults." (the contract this draft delivers)
- ADR-0009 §309 sub-item 4 — "User-facing disclosure" (the gate-item this draft closes)
- specs/runtime-abstraction.md §Runtime picker — the technical surface the picker copy sits on top of
- specs/acceptance-metrics.md — performance numbers ("~8× faster on the hot path") trace to Phase-03 P50 latency targets
- .claude/rules/communication.md — drafting principles in §1
- ROADMAP.md §23 — the gate-item this draft closes

**Drafted:** 2026-05-01 by envoy Phase-00 work, in response to ROADMAP §23 + ADR-0009 sub-item 4.
**Review owners:** Foundation legal counsel (§3 + §5 legal sufficiency); Foundation Secretary (§5 charter-clause confirmation); `kailash-rs-bindings` + `kailash-py` maintainers (§9 items 3 + 4); envoy maintainers (§9 item 5 — adoption).
