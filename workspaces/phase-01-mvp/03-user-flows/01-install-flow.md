# Flow 01 — Install + first launch

**Document role:** Phase 01 user flow #1 of 8 (shard 21 of /analyze). Describes the user-visible journey from `pipx install envoy-agent` through `envoy init` to the moment the user is sitting in front of the first Boundary Conversation prompt.

**Date:** 2026-05-03 (shard 21 of /analyze; wave F user flows).
**Owning primitive shards:** 19 (pipx distribution), 14 (Connection Vault keychain wiring), 5 (Trust store seed), 8 (Boundary Conversation S0 entry).
**Exit criteria served:** This flow is the **prerequisite** to EC-1 (Boundary Conversation completion) and to EC-7 (per-channel onboarding); on its own it does NOT prove an exit criterion, but every other flow assumes the install is done.
**Communication discipline:** Plain language per `rules/communication.md`. Most readers are non-technical.

**Phase-01 CLI-surface note (added 2026-06-07 — `/redteam` F1 disposition):** This storyboard describes the full intended first-run journey. The shipped Phase-01 CLI is 7 of 10 subcommands (`version`, `posture`, `connection`, `model`, `shamir`, `digest`, `ledger`); **`envoy init` is deferred to Phase 02** — it shares the no-durable-pending-grant / no-long-running-session blocker class with `chat` / `grant` (per `specs/mvp-build-sequence.md` Phase-02 hooks item 9 + `journal/0048`). Steps below that invoke `envoy init` describe the intended UX whose CLI entry point lands in Phase 02; the Phase-01 onboarding ritual itself (Boundary Conversation) is exercised directly through its runtime, not through an `init` wrapper.

---

## 1. Persona & context

**Primary persona:** A first-time user who has heard about Envoy, wants to try it on their own laptop, and is willing to spend ~30 minutes on the first run. They are comfortable opening a terminal because the install is `pipx install envoy-agent` (Phase 01 distribution surface per `specs/distribution.md` § Phase 01 distribution lines 13–18). Phase 02 brings `brew install` / `winget install` / mobile apps; not Phase 01.

**Device:** A personal laptop, one of:

- macOS (arm64 or x86_64) — full support, "no surprises" path
- Linux x86_64 with a desktop session running (GNOME, KDE, XFCE) — full support
- Linux x86_64 headless / SSH-only / no desktop session — **degraded**: the Connection Vault primitive needs an OS keychain backend, and on bare Linux the keychain comes from the desktop's Secret Service (per shard 14 § 2.2 + shard 19 § 7.1)
- Windows 11 x86_64 — full support; ARM64 deferred to Phase 02

**Channel at this stage:** CLI only. The user has not yet wired Telegram / Slack / Discord / WhatsApp / iMessage / Signal — those happen in Flow 5 (channel onboarding) once the Boundary Conversation has completed.

---

## 2. Trigger

The user runs:

```
pipx install envoy-agent
envoy init
```

Per shard 19 § 5.3 step 5, `envoy init` is the single entry point that bootstraps everything (Trust Vault seed → `.env` scaffolding → model picker → Boundary Conversation S0).

---

## 3. Happy path (plain language)

### Step 1 — `pipx install envoy-agent` (≈30–90s on a typical home connection)

The user sees pipx download the `envoy-agent` package and ~35 transitive packages (per shard 19 § 3.2). When the install finishes, pipx prints something like:

> "installed package envoy-agent 0.1.0, installed using Python 3.11.9 — these apps are now globally available: envoy"

What just happened in plain terms: a self-contained copy of Envoy is now in the user's account. It cannot affect any other Python project on the laptop.

### Step 2 — `envoy init` first prompt

```
$ envoy init
Hello — I'm Envoy.
Before we start, I'm going to set up three things on this computer:
  1. A safe place for my own keys (your "Trust Vault")
  2. A safe place for the keys I use to talk to other services on your behalf (your "Connection Vault")
  3. A short conversation where you tell me what I'm allowed to do and what I'm not.

This will take about 15–25 minutes. You can stop at any point and pick up where you left off — I'll save your answers.

Press Enter to begin, or Ctrl-C to leave.
```

Plain-language framing per `rules/communication.md`. No jargon ("Ed25519", "SLIP-0039", "envelope") at this point.

### Step 3 — Prerequisite check (≈1–3s)

Envoy silently checks (per shard 19 § 5.3 step 1):

- Python version ≥3.11
- The user's home directory is writable
- An OS keychain backend is available (`keyring.get_keyring()` on macOS Keychain / Windows Credential Locker / Linux Secret Service)

If anything fails, see § 4 (edge cases). If everything passes, no message — the install moves on.

### Step 4 — Trust Vault seed (≈1–2s)

The user sees:

> "Setting up your Trust Vault…"

Per shard 5, this creates the encrypted SQLite file at `~/.envoy/trust-vault.bin`, generates the user's Genesis key (Ed25519), and writes the Genesis Record. The user does not see the cryptographic detail — they just see one progress line.

### Step 5 — `.env` scaffolding (≈instant)

Per shard 19 § 5.2, `~/.envoy/.env` is created with mode `0600` (only the user can read it) and includes commented placeholders for model API keys and channel bot tokens. The user is told:

> "I made a small settings file at `~/.envoy/.env`. You don't need to edit it now — I'll ask you about each setting in the next part."

### Step 6 — Model picker (≈30s of user reading + 1 user choice)

Per shard 13 + ADR-0006, the user picks where their model runs:

```
Where should I run my AI brain?

  [1] Use a cloud model — fast, costs about $0.01–$0.05 per question.
      I'll need an API key from one of:
        - Anthropic (Claude)
        - OpenAI (GPT)
        - DeepSeek
      You can paste this key now or skip and add it later.

  [2] Use a local model on this computer — free, private, slower.
      I can download a small model now (~4 GB, takes a few minutes).

Which would you prefer? [1/2]
```

The user picks. Plain-language framing per `rules/communication.md` ("Should new users verify their email…" pattern — explain the trade-off in business terms, not implementation).

If [1]: the user pastes their API key. It is written to the Connection Vault via `keyring.set_password(...)`, NOT to `.env` (per shard 14 § 3.1 item 9 — the Vault is the source of truth post-first-run).

If [2]: Envoy downloads a default local model (Llama-3 8B GGUF or similar; ~4 GB) into `~/.envoy/models/`. **Caveat per shard 19 § 5.3 step 4:** the wheel itself does NOT ship the model — first-run downloads it; "offline-first" weakens to "offline-CAPABLE if local model already present, online-required for fresh first-run."

### Step 7 — Boundary Conversation S0 hand-off

```
Thank you. Now let's have that short conversation.

I'll ask you about money, people, topics, hours, your first task, and then
we'll set up a few safety things — a "visible secret" so you can recognize
me, and a way to recover your keys if you lose this laptop.

Ready? Press Enter to start.
```

The user presses Enter. Control passes to the Boundary Conversation primitive (shard 8) and Flow 02 takes over.

---

## 4. Edge cases (≥3 required)

### EC-A — `pipx` itself is not installed

The user hits `pipx install envoy-agent` and the shell says `pipx: command not found`.

Plain-language UX: this is a pre-Envoy concern; Envoy cannot help. Phase 01 docs (`README.md` of the `envoy-agent` repo) MUST include a one-liner pointing the user at https://pipx.pypa.io/stable/installation/ and naming the typical macOS / Linux / Windows install commands. **Recovery:** install pipx, retry `pipx install envoy-agent`.

### EC-B — Linux headless / no desktop session

The user is on a VPS or a cloud Linux box with no GNOME/KDE running. `keyring.get_keyring()` returns the `Null` backend (no Secret Service available).

Plain-language UX (per shard 19 § 7.1 disposition):

> "I tried to find a safe place to store passwords on this computer, but it looks like you don't have a desktop session running.
>
> On Linux, the safe place lives inside your desktop session (GNOME Keyring or KDE KWallet).
>
> Two options:
> [1] Open a desktop session and run `envoy init` again from a terminal inside it.
> [2] Stop here. Phase 02 of Envoy will support a HashiCorp Vault backend for headless setups; for now, headless servers aren't fully supported."

Recovery: the user opens a desktop session and re-runs. The init is restartable from scratch — at this stage no Trust Vault exists yet (Step 4 has not happened), so there is nothing to lose.

### EC-C — Network drops mid-model-download

The user picked option [2] (local model) and the wireless cuts out 60% through the 4 GB download.

Plain-language UX:

> "The download stopped. I got 2.4 GB of 4 GB. I'll keep what I have and pick up from where I left off when you reconnect.
>
> Press Enter once your network is back to retry."

Recovery: `envoy init --resume` (per shard 8 spec line 33–35 resume contract — extended to the install bootstrap). The model download is resumable because GGUF files are chunkable; the partial download is kept in `~/.envoy/models/.partial/`.

### EC-D — User Ctrl-C during model picker (Step 6)

User has second thoughts, hits Ctrl-C.

Plain-language UX:

> "OK, I've stopped. Your Trust Vault is set up but no model is wired and no conversation has started.
>
> When you're ready, run `envoy init --resume` to pick up here."

Recovery: per shard 8 spec § Persistence + resume — Trust Vault state persists; init can resume from Step 6. No data loss.

### EC-E — `.env` already exists from a prior install attempt

The user uninstalled Envoy partially (or aborted a prior `envoy init`) and `~/.envoy/.env` is present.

Plain-language UX:

> "I found an existing settings file from a prior setup. Should I:
> [1] Keep it (use the API keys already in it)
> [2] Replace it (start fresh)
>
> Choose [1] or [2]:"

Recovery: user choice. Per `rules/security.md` § "No .env in Git", the file mode is checked (must be `0600`); if it is world-readable, Envoy refuses to use it and forces [2].

---

## 5. Underlying primitives

| Step                   | Primitive (shard)              | What the primitive does                                                                                    |
| ---------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| 1 (pipx install)       | shard 19                       | Defines the dep tree; `kailash[shamir,nexus,kaizen]>=2.13.4` plus `keyring`, `python-dotenv`, channel SDKs |
| 3 (prereq check)       | shard 19 § 5.3, shard 14 § 2.2 | Cross-OS keychain probe                                                                                    |
| 4 (Trust Vault seed)   | shard 5                        | `TrustStoreAdapter.seed_genesis(...)` produces Genesis Record                                              |
| 5 (`.env` scaffolding) | shard 19 § 5.2                 | File at `~/.envoy/.env`, mode `0600`                                                                       |
| 6 (model picker)       | shard 13 + ADR-0006            | `EnvoyModelRouter` provider + `ENVOY_BOUNDARY_MODEL` selection; Connection Vault writes the API key        |
| 7 (S0 hand-off)        | shard 8                        | `BoundaryConversationRuntime.start(principal_id)` returns `ritual_id`                                      |

---

## 6. Acceptance criteria served

This flow does not directly prove any of EC-1..EC-9. It is the **prerequisite** that every other flow assumes complete. Specifically:

- EC-1 (Boundary Conversation completion) requires Steps 1–7 to succeed.
- EC-7 (8-channel onboarding) requires the Connection Vault from Steps 3–4 to exist before any channel adapter can write a credential.
- EC-5 (Shamir backup) requires the Trust Vault from Step 4 to hold a master key.

A failure in this flow blocks all of EC-1, EC-5, EC-7, EC-8.

---

## 7. Failure modes & recovery

| Failure                       | What the user sees                                                                                                                           | Recovery path                                                                                 |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| pipx absent                   | Shell: `pipx: command not found`                                                                                                             | User installs pipx (see Phase 01 README), retries                                             |
| Python <3.11                  | Envoy: "I need Python 3.11 or newer; you have 3.10"                                                                                          | User installs Python 3.11+ via pyenv / system package manager / official installer            |
| Linux headless                | Envoy: "No desktop session — keychain unavailable" (EC-B)                                                                                    | User starts a desktop session OR waits for Phase 02 HashiCorp Vault backend                   |
| Disk full                     | Envoy: "I need about 200 MB of free space in your home directory" (Trust Vault + Connection Vault + .env are tiny; the model is the big one) | User frees disk space, retries                                                                |
| API key paste fails           | Envoy: "That key didn't validate against the provider — please paste it again, or skip and add it later via `envoy model set-key`"           | User retries OR skips and uses `envoy model set-key` post-init                                |
| Model download partial (EC-C) | Envoy: "Got 2.4 GB of 4 GB — press Enter to retry when connected"                                                                            | `envoy init --resume` continues from partial download                                         |
| User Ctrl-C mid-init          | Envoy: stops cleanly; tells user how to resume                                                                                               | `envoy init --resume`                                                                         |
| Existing `.env` (EC-E)        | Envoy asks keep/replace                                                                                                                      | User picks; if existing `.env` is world-readable Envoy forces replace per `rules/security.md` |

All recovery paths converge on a clean resume — **per shard 19 + `rules/zero-tolerance.md` Rule 6, `envoy init` MUST be idempotent and re-runnable.** No partial state is left in a way that requires the user to manually clean up files.

---

## 8. Cross-references

- `workspaces/phase-01-mvp/01-analysis/19-pipx-distribution-architecture.md` § 3 (pyproject shape), § 5.3 (first-run bootstrap)
- `workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md` § 2.2 (keyring backend), § 3.1 item 9 (.env import)
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 3 (Genesis seed)
- `workspaces/phase-01-mvp/01-analysis/13-model-adapter-implementation.md` § 3.2 (per-primitive model)
- `specs/distribution.md` § Phase 01 distribution (lines 13–18), § Installer security (line 88)
- `specs/connection-vault.md` § Platforms, § Error taxonomy
- `rules/communication.md` (plain-language framing)
- `rules/security.md` § "No Hardcoded Secrets", § "No .env in Git"
