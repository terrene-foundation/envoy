# distribution

## Purpose

Per-OS install paths, first-run picker, N=3 mirrors + binary verification, upgrade/rollback/uninstall, jurisdictional advisories.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/06-distribution.md v1`.
- **Threats mitigated:** T-050a mirror, T-050b signing-key, T-060 binary poisoning.
- **BETs tested:** BET-3 sovereignty (N=3 mirror + kailash-py escape), BET-4 Foundation infra.

## Phase 01 distribution

- **Surface:** `pipx install envoy-agent` (PyPI). kailash-py sole runtime.
- **Installer:** `envoy init` bootstraps Trust Vault + Genesis + Boundary Conversation.
- **Offline first-run:** local model bundled (Ollama/llama.cpp/MLX).

## Phase 02 distribution

- **macOS:** `curl -sSf https://get.envoy.ai | sh`, `brew install envoy-agent`.
- **Linux:** same curl, `apt`/`dnf` Phase 04.
- **Windows:** `winget install envoy-agent`; MSI Phase 04.
- **Rust:** `cargo install envoy-agent`.
- **Mobile:** App Store + Play Store (Flutter).

## N=3 mirror verification

1. Foundation GitHub (primary).
2. IPFS-pinned (secondary).
3. Community redistributor (Foundation-endorsed list).

Installer fetches binary + manifest from all 3; hash match across ≥ 2 required.

## Binary signing key rotation

Quarterly scheduled + on-demand on suspected compromise. Installer refuses revoked-key binaries. Compromise-response runbook published; target response <72h.

## Reproducible-build verification stream

Rust source for `kailash-rs-bindings` Python glue published; build instructions documented; third-party reproduction + published attestations; installer cross-checks.

## First-run flow (Phase 02)

Runtime picker → Model picker → Boundary Conversation → Shamir ritual → Visible secret setup.

## Upgrade / Rollback / Uninstall

- `envoy upgrade` with hash verification.
- Rollback preserved 30 days.
- `envoy uninstall --destroy-vault` for permanent key destruction.

## Jurisdictional advisories

- EU/UK: GDPR right-to-erasure note.
- US: export-control note (Ed25519+SHA-256 are EAR 742.15(b)(1) exportable).
- Hostile jurisdictions: recommend disabling sync + hidden-envelope (Phase 04).

## Install-to-first-value (Phase 02 acceptance gate; MED-R5-1 closure)

Phase 02 acceptance-metrics.md target: `<10min mobile`. The clock starts at install-tap (App Store / Play Store / curl|sh) and stops at the first user-observable Envoy action (typically the Boundary Conversation S0 greet rendered in the user's primary channel).

Measurement substrate:

- **Mobile:** Flutter app `flutter test integration_test/test_install_to_first_value_mobile.dart` records timestamps at install-complete callback, first-launch, Boundary Conversation S0 render. Reports the delta to the `tests/acceptance/phase_02/test_install_to_first_value_mobile.py` aggregator.
- **Desktop:** `tests/acceptance/phase_02/test_install_to_first_value_desktop.py` shells through `curl|sh` install + `envoy init` + first Grant Moment render.

Failure budget: Phase 02 exit blocked if median across 10 sample installs exceeds 10 min mobile / 5 min desktop. Per-channel breakdown logged to specs/foundation-health-heartbeat.md aggregate.

## Mobile QR-pair (Phase 02 acceptance gate; MED-R5-1 closure)

Phase 02 acceptance-metrics.md target: `mobile QR-pair <30s`. Mobile QR-pair is the cross-device pairing ceremony that binds a mobile install to an existing desktop Trust Vault — the user scans a QR on the desktop UI from the mobile app, the mobile derives a fresh per-device key pair, and the desktop signs a `GenesisDeviceTransferRecord` (per specs/ledger.md §Ledger entry schemas).

Note: this is distinct from the Shared Household co-presence QR-pair in specs/shared-household.md §Co-presence verification (which is cross-principal, not cross-device).

Measurement substrate: `tests/acceptance/phase_02/test_mobile_qr_pair_under_30s.py` — Tier 3, real desktop + mobile harness, asserts end-to-end (display QR → scan → sign → Vault sync) completes ≤30s at p50 across 10 samples.

## Binary size constraint (Phase 02 acceptance gate; MED-R5-1 closure)

Phase 02 acceptance-metrics.md target: `binary <50 MB`. Applies to the Phase 02 static-binary distribution (curl|sh / brew / winget / cargo install on desktop; APK / IPA size cap on mobile is platform-specific and tracked separately).

Measurement substrate: `tests/acceptance/phase_02/test_binary_size_under_50mb.py` — CI-time, `du -sh` on the produced static binary across all 5 Phase-02 build targets (macOS-arm64, macOS-x86_64, linux-x86_64, linux-arm64, windows-x86_64). Fails CI if any target exceeds 50 MB.

Strip discipline: stripping debug symbols is REQUIRED for Phase 02; debug-symbol bundles ship as separate downloadable artifacts under the Phase 02 reproducible-build verification stream.

## Installer security

Signed installer (bash/PowerShell). Platform verification (Gatekeeper/SmartScreen). AppArmor/SELinux profiles (Phase 03). Refuses install if Trust Vault dir world-readable.

## Error taxonomy

| Error                                   | Trigger                                                                                 | User action                                                                                    | Retry                       |
| --------------------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | --------------------------- |
| `MirrorSignatureMismatchError`          | Binary fetched from N=3 mirrors fails hash-match across ≥ 2 mirrors                     | Refuse install; surface "mirror compromise suspected"; user re-tries from alternate mirror set | Never (T-050a defense)      |
| `ReproducibleBuildFailedError`          | Third-party build attestation does not match Foundation-published binary                | Refuse install; surface as supply-chain event; user awaits Foundation incident response        | Never (T-060 defense)       |
| `JurisdictionalGateRefusedError`        | Install attempted in jurisdiction blocked by export-control / sanctions advisory        | Surface advisory; user reviews EAR 742.15(b)(1) status; opt-in continues                       | Manual after acknowledgment |
| `RevokedSigningKeyError`                | Binary signed with key in revocation list (T-050b compromise-response)                  | Refuse install; user fetches post-rotation binary from N=3 mirrors                             | Never                       |
| `TrustVaultDirWorldReadableError`       | Installer detected `~/envoy/` dir mode allows world-read                                | Refuse install; user fixes dir permissions OR uses installer-managed path                      | Manual after chmod          |
| `PlatformVerificationFailedError`       | Gatekeeper / SmartScreen / signature verification refused at OS layer                   | Surface OS-layer message; user routes through Foundation-published install instructions        | Manual after diagnosis      |
| `OfflineFirstRunModelMissingError`      | Bundled local model (Ollama/llama.cpp/MLX) missing or corrupted                         | Surface degraded-mode warning; user re-fetches from mirrors OR completes install with cloud    | Manual after re-fetch       |
| `RollbackWindowExpiredError`            | `envoy rollback` attempted past 30-day preserved window                                 | Refuse rollback; user reinstalls prior version manually from mirrors                           | Never                       |
| `UpgradeHashMismatchError`              | `envoy upgrade` fetched binary hash does not match manifest                             | Refuse upgrade; user re-tries OR escalates via Foundation incident channel                     | Auto with mirror failover   |
| `UninstallVaultDestroyedConfirmError`   | `envoy uninstall --destroy-vault` requires double-confirm acknowledging key destruction | Surface irreversibility warning; user confirms or aborts                                       | N/A                         |
| `AppArmorProfileFailedError` (Phase 03) | Linux AppArmor / SELinux profile install refused                                        | Surface advisory; install continues without sandbox profile (degraded posture)                 | Manual after fix            |

## Cross-references

- specs/runtime-abstraction.md — runtime picker consumer.
- specs/trust-vault.md — Trust Vault initialization.
- specs/shamir-recovery.md — first-run Shamir.
- specs/boundary-conversation.md — first-run ritual.
- specs/foundation-ops.md — N=3 mirror coordination + signing-key rotation runbook.
- specs/network-security.md — TLS + cert pin for mirror fetch.
- specs/threat-model.md — T-050a, T-050b, T-060. (T-061 currently RESERVED in anchor doc 09 v3 §3 for a future binding-specific threat; not claimed by this spec.)

## Test location

Phase 01 distributes via PyPI / `pipx` only; it ships the packaging surface + Trust Vault directory permissions. Tested in-repo:

- `tests/e2e/test_envoy_cli_packaging_acceptance.py` — `pipx install`-shape packaging acceptance (console entry point + subcommand surface + uninstall).
- `tests/tier1/test_sqlite_perms.py` — `chmod_sqlite_family` applies `0o600` to the Trust Vault sqlite + WAL family so governance rows are not left world-readable.

## Out of scope (this phase)

The binary distribution + N=3 mirror layer + offline-model bundle land in Phase 02 (per `specs/mvp-build-sequence.md` Phase-02 hooks item 8):

- First-run offline-model bundle (no network) — Phase 02.
- Upgrade / rollback 30-day window + `--destroy-vault` double-confirm uninstall — Phase 02.
- Jurisdictional (GDPR / EAR) install advisories — Phase 02.
- Phase-02 curl-pipe installer + first-run picker (Tier 3) — Phase 02.
- T-050a/b mirror-signature + revoked-key refusal, T-060 reproducible-build + N=3 mirror-divergence refusal — Phase 02 (binary mirror infra).

## Open questions

1. N=3 mirror Foundation-endorsed list — community redistributor selection criteria + rotation cadence.
2. Reproducible-build attestation diversity — Phase 01 N=2 third-party reproducers sufficient vs Phase 02 N=5+ for stronger attestation.
3. Quarterly signing-key rotation cadence — sufficient against state-actor key-extraction scenarios; on-demand <72h target validation.
4. Hostile-jurisdiction install UX — automatic disable of sync + hidden-envelope vs explicit Grant Moment opt-out per region.
5. AppArmor / SELinux Phase 03 profile distribution — bundled vs OS-package-manager vs Foundation-hosted; coordination with foundation-ops.md.
