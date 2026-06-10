---
type: DECISION
date: 2026-06-09
created_at: 2026-06-09T11:20:00Z
author: co-authored
session_id: continue-from-wave1
project: phase-02-distribution
topic: /implement Wave 2 batch-1 (S2a + S4r + S10) complete and merged
phase: implement
tags: [implement, wave-2, S2a, S4r, S10, security-fix, H1, parallel-worktree]
---

# Wave 2 batch-1 COMPLETE — S2a + S4r + S10 merged (PR #88)

## What landed

Three dependency-satisfied Wave-2 shards across three milestones, built as a
parallel worktree wave of 3 (disjoint file sets), integrated onto
`feat/phase-02-wave-2`, and merged to `main` (`45db72a`, PR #88, CI green
py3.11 + py3.13):

- **S2a (M1 / WS-1)** — `kailash-rs-bindings` adapter wired behind the frozen
  `KailashRuntime` interface. All 30 Protocol methods forward to the Rust core
  (zero `Phase02SubstrateNotWiredError`); exact sync/async parity; device-key
  signing surface (injectable, software Ed25519 fallback — no Secure Enclave/TPM
  binding exists in `kailash` 2.13.4, so the rs adapter OWNS the device-key seam
  via `device_signer` + validated `device_attestation_type`; `binary_hash`
  attestation is the S3t seam, grep-able sentinel until then).
  `RS_BINDINGS_ENABLED` deliberately NOT flipped — gates on the byte-identity
  conformance corpus (S2b/S2c/S3a/S3b).
- **S4r (M2 / WS-6)** — cross-process grant rendezvous: `asyncio.Future` →
  store-poll-with-monotonic-version-re-check. Poll backoff 50ms→500ms (recorded
  in `specs/session-runtime.md`). Timeout audit row byte-identical to Phase-01.
- **S10 (M4 / WS-5)** — Foundation OHTTP key-config server + IP-stripping relay:
  RFC 9180 HPKE (pinned ciphersuite), 2-of-N steward-signed key configs (reuses
  the shared `verify_steward_quorum`), fail-closed TLS-1.3+strict-SNI build gate,
  relay non-collusion split. New `envoy/foundation_ops/` package.

## Gate reviews — both APPROVE

- **reviewer: APPROVE** (0 CRITICAL/HIGH; mechanical sweeps clean, no orphans,
  spec-accurate).
- **security-reviewer: CHANGES REQUESTED → APPROVE after in-session fix.**
  Surfaced **HIGH H1**: S4r consumed cross-process grant resolutions
  **unauthenticated** — a same-UID process writing the vault sqlite could forge
  an APPROVE on the human-authority grant gate; process A's `await_decision`
  returned the forged `ApproveResolution` and signed it into a valid ledger row.
  The monotonic-version guard defends lost-update, NOT authenticity.

  **Fix (autonomous-execution Rule 4 — gate-surfaced same-bug-class gap, fits
  shard budget → fixed immediately, not deferred):** sign-on-write + fail-closed
  verify-on-read. `resolve_pending_grant` signs the resolution with the session
  key (`SESSION_SIGNING_KEY_ID`, the documented trust anchor) over a
  `request_id`-bound canonical payload (`resolution_signing_payload`), persisted
  in a new `resolution_sig` column atomically with `resolution_json`.
  `_poll_store_for_resolution` verifies via `SessionRouter.verify_resolution_signature`
  BEFORE treating the row as a decision; missing/invalid/tampered/replayed sig →
  new fail-closed `GrantMomentResolutionUnauthenticatedError`. The `request_id`
  binding defeats replay; `verify` catches malformed-sig exceptions and fails
  closed. Same-process `decision_future` fast-path stays trusted by construction.
  Cross-**principal** co-signature verification remains Phase-03 (unchanged).
  Also fixed **M3** (strippable `assert isinstance(.., ResolutionShape)` →
  fail-closed raise) and **M1** (`decapsulate_request` ciphersuite pin symmetry).
  **M2/L1/L2** (MEDIUM/LOW) deferred to S11 as value-anchored EC-S11.8/9/10
  (the OHTTP/STAR client shard constructs the HPKE `info`; security-review gate
  per `threat-model.md:52` caps the ship). Security-reviewer re-reviewed →
  APPROVE (H1 closed, deferrals sound).

## Verification (receipts)

- Full suite over merged `main`: **1864 passed**, 9 skipped, 3 xfailed,
  **0 failed**; coverage **91.24%** (≥90 floor). `mypy envoy/` + `pyright envoy/`
  clean (CI runs both as hard gates; `main` ruleset empty-bypass blocks merge
  over red CI).
- New security regression tests (`TestResolutionAuthenticity`): forged
  direct-sqlite row refused, NULL-sig row refused, verify rejects
  tamper/replay/absent-sig.

## Process notes (for next session)

- **Transient server throttle on the first parallel-3 launch** — all 3 agents
  died at ~13–33s with zero work (only STEP-0 `git status` ran; no orphans). An
  80s backoff cleared it; the re-launched wave of 3 completed cleanly. The
  wave-of-3 cap (`worktree-isolation.md` Rule 4) was honored; this was infra
  backpressure, not over-burst. **Lesson: on `not your usage limit` throttle,
  back off ~80s and retry the same wave.**
- **Harness `isolation:"worktree"` branches from the session base (`957cbd7`),
  NOT the checked-out integration branch.** A delegated H1-fix agent correctly
  STOPPED (its STEP-0 base check caught it) rather than re-implement S4r on the
  wrong base. The H1 fix was done **inline** on the integration branch instead
  (sole-writer, no parallel conflict). Next time a fix must land on an
  integration branch, do it inline OR `git worktree add -b <br> <path>
feat/<integration>` manually (the harness primitive won't target it).
- **Worktree-env false-red**: both S4r and S10 agents reported "59 failures /
  29 collection errors" that were pure worktree-`.venv` artifacts (missing
  `dataflow`/`nexus` extras / kaizen 2.20.0 drift). The real main `.venv`
  collected clean (1788→1864). Always re-run the FULL suite over merged `main`
  in the complete `.venv` — agent worktree-env counts are not authoritative.
- **Upstream-file candidate (human-gated, P6-class):** `kailash` `nexus.Nexus.close()`
  does NOT cascade-close its internal `AsyncLocalRuntime` → GC-time
  ResourceWarning for every Nexus-building test (S8 + S10). Scope-suppressed in
  `pyproject.toml` (message+category) mirroring the existing `@app.handler`
  advisory suppression. envoy is an APPLICATION repo (no `kailash` source).

## For Discussion

1. The H1 fix anchors authenticity on the **device session key** (both processes
   recover the same keystore-backed key). This rejects direct-sqlite-tampering
   and non-keystore forgers, but a same-UID process WITH keychain access could
   still sign. Is the Phase-03 cross-principal co-signature (distinct answerer
   key) the right place to close that residual, or does the `grant` CLI (S4g-1)
   warrant an earlier principal-distinctness check?
2. Counterfactual: had the security-reviewer NOT run (or run only post-merge),
   S4r would have shipped a forge-able grant gate. The gate caught it pre-merge —
   but the brief CLAIMED "JCS-signed / forge-rejected" while S4r's code honestly
   said "will use" (future tense). Should the `/todos` acceptance for S4r have
   listed the authenticity gate explicitly, rather than letting it sit implicitly
   between S4r (mechanism) and S4g-1 (signed resolution)?
3. Wave-2 batch-2 candidates (S8e/S9a independent WS-4; S4i store-only WS-6) vs
   the M1 conformance families (S2b/c/S3a/b, now unblocked) — which delivers more
   user value next? The conformance corpus is the BET-6 correctness core AND
   unblocks the `RS_BINDINGS_ENABLED` flip + S7v verifier; S8e/S9a complete the
   WS-4 Envelope Library FV tier. (Decide at next-session value-rank.)
