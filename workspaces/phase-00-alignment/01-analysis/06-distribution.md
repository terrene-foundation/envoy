# 06 — Distribution + Install

**Document status:** draft v1 — ready for `/redteam`
**Scope:** Per-OS install paths, first-run picker UX, binary hash verification + N=3 mirrors, model download flow, upgrade / rollback / uninstall, jurisdictional advisories, first-run offline posture.
**Sources:** doc 00 v3 (ADR-0001 runtime pluggability + §4.1 item 15 N=3 mirrors), doc 05 v2 (runtime picker + switch), doc 09 v3 (T-050a/b binary compromise, T-060 binary poisoning), doc 03 v2 (Genesis generation + Shamir + device attestation).

## 1. Phase 01 distribution

- **Surface:** `pipx install envoy-agent` (PyPI). Python-only. kailash-py sole runtime per ADR-0001.
- **Installer:** `envoy init` bootstraps Trust Vault + Genesis + optional Boundary Conversation.
- **Offline first-run:** installer bundles a minimal local model (Ollama/llama.cpp) so first-launch works without network. User opts in to cloud providers later via Grant Moment.

## 2. Phase 02 distribution

### 2.1 Single static binary paths

- macOS: `curl -sSf https://get.envoy.ai | sh` (Foundation-signed script), `brew install envoy-agent`.
- Linux: same `curl | sh`, `apt`/`dnf` packages Phase 04.
- Windows: `winget install envoy-agent`, MSI installer Phase 04.
- Rust users: `cargo install envoy-agent`.
- Mobile: App Store + Play Store (Flutter clients).

### 2.2 N=3 mirror verification (doc 00 §4.1 item 15; doc 09 T-050a)

- Foundation GitHub (primary mirror).
- IPFS-pinned (secondary).
- Community redistributor (tertiary; Foundation-endorsed list).
- Installer fetches binary + manifest from all 3 independently; hash match required across ≥ 2.

### 2.3 Binary signing key (doc 09 T-050b)

- Foundation signs every release binary with rotating signing key.
- Key-rotation cadence: quarterly scheduled; on-demand on suspected compromise.
- Compromise-response runbook published; installer refuses binaries signed with revoked keys.
- Reproducible-build verification stream: Rust source for `kailash-rs-bindings` Python glue is open; Foundation publishes build instructions; third parties reproduce and publish attestations. Installer cross-checks reproducible-build report.

## 3. First-run flow

Per doc 05 v2 §8.1:

- Runtime picker (kailash-rs-bindings default vs kailash-py opt-in).
- Model picker (local vs cloud) per ADR-0006.
- Boundary Conversation (doc 01 §3) — OR skipped via template import.
- Shamir 3-of-5 ritual (doc 01 §8).
- Visible-secret setup.

## 4. Upgrade

- `envoy upgrade` checks Foundation mirror for new version.
- Hash verification + runtime-attestation before activation.
- Downgrade requires user passphrase + `--allow-downgrade` flag; warning banner.

## 5. Rollback

- Rollback to previous version preserved for 30 days.
- Trust Vault + Ledger must be forward-compatible; if downgrading beyond schema-version boundary, refuses (per doc 02 §6.3).

## 6. Uninstall

- `envoy uninstall` — with `--destroy-vault` flag permanently destroys Trust Vault keys (doc 03 §11.1).
- Without flag, Trust Vault preserved; user can reinstall and recover.

## 7. Jurisdictional advisories

On install, Envoy detects locale + asks user:

- **EU/UK:** GDPR right-to-erasure note; retention policy configurable.
- **US:** export-control note if cross-border crypto; Ed25519 + SHA-256 are standard exportable per EAR 742.15(b)(1).
- **Hostile jurisdictions (user-declared):** recommend disabling sync + using local-only posture; hidden-envelope ritual (Phase 04).

## 8. Installer security

- Signed installer script (bash / PowerShell).
- Platform-level verification (macOS Gatekeeper, Windows SmartScreen).
- AppArmor / SELinux profiles on Linux (Phase 03).
- Installer refuses to run if Trust Vault directory has world-readable permissions.

## 9. Phase 02 exit gates

- N=3 mirror active + signed.
- Key-rotation published.
- Reproducible-build stream live.
- Binary-compromise response runbook published.
- Installer UX tested end-to-end across macOS, Linux, Windows.
- Mobile clients ship via App Store + Play Store; QR-pairing works <30s cold-start.

## 10. Cross-references

- doc 00 v3 §4.1 item 15, ADR-0001/0006.
- doc 05 v2 runtime picker / switch / attestation.
- doc 09 v3 T-050a/b + T-060 + T-080.

## 11. Open questions

- Foundation-endorsed community redistributor list — governance process?
- Reproducible-build attestations — who publishes? Foundation? Community?
- Mobile App Store compliance — any review issues re: on-device LLM?

**End of doc 06 v1.**
