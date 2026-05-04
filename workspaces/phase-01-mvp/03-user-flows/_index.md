# Phase 01 MVP — User Flows Index

**Document role:** Lean lookup table for every Phase 01 `/analyze` user-flow artifact under `03-user-flows/`. Per `rules/specs-authority.md` MUST Rule 1, this manifest is one-line descriptions only — the actual flow narratives live in the linked files. `/todos` reads selected rows when sequencing user-visible deliverables; `/implement` reads the row matching the EC the current todo serves; `/redteam` reads ALL rows in audit mode (re-derived per round).

**Date:** 2026-05-03 (shard 25 of /analyze; closure).
**Status:** Closed for /analyze; load-bearing for /todos.

---

| File                               | Domain                       | Description                                                                                                                                                                                                                           |
| ---------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `01-install-flow.md`               | Install                      | `pipx install envoy-agent` → first launch through `envoy init`; cross-OS keychain caveats; `.env` template; failure modes for missing desktop env on Linux                                                                            |
| `02-boundary-conversation-flow.md` | Boundary Conversation        | First-run S0→S10 ritual; structured-output Signature pattern; persistent resume via `envoy init --resume <ritual_id>`; envelope materialization; gates EC-1                                                                           |
| `03-grant-moment-flow.md`          | Grant Moment                 | M0→M4 state machine; 3 resolution shapes (Approve / Decline / ApproveWithModification); cascade-revocation on decline; signed-consent 3-artifact wire format; gates EC-2                                                              |
| `04-daily-digest-flow.md`          | Daily Digest                 | Morning render at scheduled time; per-channel fan-out; pause-state Trust-store-backed; 1 HIGH UX risk: Singapore user sees digest at 4pm local under Option A; cohort recommendation: EC-7 N=3 MUST include at least one non-UTC user |
| `05-channel-onboarding-flow.md`    | Channel onboarding           | Per-channel webhook setup across 8 channels (CLI + Web + 6 messaging); credential paste via OS-keychain; cross-channel coherence delegated to Trust store + Ledger; gates EC-7                                                        |
| `06-shamir-backup-flow.md`         | Shamir backup                | 3-of-5 paper-shard ritual; cold-storage co-location of Shamir + trust-anchor (cross-flow invariant); reconstruction CLI; gates EC-5                                                                                                   |
| `07-ledger-export-flow.md`         | Ledger export + verification | `envoy ledger export` produces bundle; user runs separate `envoy-ledger-verifier` CLI; first-verification self-anchoring trust model; gates EC-4 + EC-9                                                                               |
| `08-posture-ratchet-flow.md`       | Posture ratchet (Day 30)     | Authorship-Score-driven posture transition (PSEUDO → TOOL → SUPERVISED → DELEGATING); fail-closed PostureGate; cooling-off under Option A timezone consistency                                                                        |

---

## Cross-flow invariants (surfaced shard 21)

1. **Trust Vault is the cross-flow state surface** — every flow that persists state writes to a Trust-store-backed key (per shard 5).
2. **Cold-storage co-location** of Shamir paper shards + trust-anchor (per flow 06 + flow 07; failure mode: separated storage = recoverable but unverifiable).
3. **Plain-language error mapping** per spec error class (per `rules/communication.md`); each flow has a per-error UX line.
4. **Fail-closed defaults compose** — a partial failure in one primitive does not silently degrade a downstream flow (per `rules/security.md` § Fail-Closed Security Defaults).
5. **Timezone Option A** has highest UX visibility in Flow 04 — escalated to shard 22 HIGH; HUMAN DECISION at /todos opening.

---

## Cross-references

- Analysis: `01-analysis/_index.md`
- Plans: `02-plans/_index.md`
- Redteam rounds: `04-validate/round-{1,2,3,4}-implementation-comprehensive.md`
- Brief: `briefs/00-phase-01-mvp-scope.md`
