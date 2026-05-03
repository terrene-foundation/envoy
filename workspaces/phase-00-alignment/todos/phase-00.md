# Phase 00 — Task Tracker

**Mirrors `ROADMAP.md` Phase 00 with owner/status detail.**

Update status as items progress. When all items complete → Phase 01 opens.

## Naming and namespace

- [ ] USPTO trademark sweep — Class 9 + 42
- [ ] EUIPO trademark sweep — Class 9 + 42
- [ ] UK IPO trademark sweep — Class 9 + 42
- [ ] Final legal mark decision (post-sweep)
- [ ] GitHub org reservation (availability confirmed 2026-05-03; reservation gated on trademark close)
- [ ] npm `envoy-agent` reservation (availability confirmed 2026-04-21 + rechecked 2026-05-03; reservation gated on trademark close)
- [ ] PyPI `envoy-agent` reservation (availability confirmed 2026-04-21 + rechecked 2026-05-03; reservation gated on trademark close)
- [ ] crates.io `envoy-agent` reservation (availability confirmed 2026-04-21 + rechecked 2026-05-03; reservation gated on trademark close)
- [ ] Update `pyproject.toml` + `NOTICE` once mark is final

## Claim verification

- [x] Full sweep of `README.md` factual claims with citations (sweep `02-plans/claim-verification/01-sweep.md`; surgical edits applied in commit f6ec8dc)
- [x] Full sweep of `CHARTER.md` factual claims with citations (same sweep + commit)
- [x] Full sweep of `DECISIONS.md` factual claims with citations (same sweep + commit)
- [x] Full sweep of `ROADMAP.md` factual claims with citations (same sweep + commit)
- [x] Remove any residual comparative framing (keep only neutral `SKILL.md` compatibility references) — DECISIONS §79/§83/§114 reworded in commit f6ec8dc

## Licensing + legal counsel (per ADR-0009)

- [x] Draft composite LICENSE file for `kailash-rs-bindings` PyPI wheel (drafted in `02-plans/legal/01-kailash-rs-bindings-LICENSE-draft.md`, commit 794597c; counsel review pending)
- [x] Finalise SPDX metadata expression for PyPI (drafted in `02-plans/legal/02-kailash-rs-bindings-SPDX-draft.md`, commit 794597c; counsel review pending)
- [ ] Terrene Foundation board approval of runtime-pluggability model
- [x] User-facing disclosure text drafted (installer, README, runtime-picker copy) — `02-plans/user-disclosure/01-installer-readme-runtime-copy.md`, commit 46ef411
- [ ] Export-control assessment of Rust binary redistribution (counsel item)
- [x] Runtime-swap conformance contract drafted (`02-plans/conformance/01-runtime-swap-contract.md`, commit fbc6788)
- [x] Licensing audit of Foundation COC template repositories (2026-04-21; findings in `04-validate/licensing-audit-followups.md`)

## Foundation COC template follow-ups

- [ ] H6 — pick resolution for variant-source `independence.md` (BUILD-only re-scope vs sync-manifest exclusion)
- [ ] Apply drafted variant-source replacement at `~/repos/loom/.claude/variants/rs/rules/independence.md`
- [ ] M1 — re-sweep variant-synced skill/agent files referencing `kailash-enterprise` after H6 fix
- [ ] M2 — apply same fixes (LICENSE, NOTICE, placeholders, SPDX) to `~/repos/loom/kailash-coc-claude-py/`
- [ ] L1 — filter RS `git.md` private-repo reference via `/sync` variant exclusion

## Foundation sign-off

- [ ] Terrene Foundation board endorses Envoy as Foundation project
- [x] Apache 2.0 + CC BY 4.0 + MIT `SKILL.md` skill compatibility — agent-side compatibility statement drafted in `02-plans/legal/03-license-compatibility-statement.md` (commit 9942a67); formal legal review still pending counsel
- [x] Working concept one-pager drafted for board review (`02-plans/board-package/01-envoy-concept-one-pager.md`); formal publication to board pending Foundation Secretary

## Legal counsel engagements (independent of trademark)

- [ ] CLA / re-licensing posture review for historical contributions on COC template repos
- [ ] "Kailash" trademark ownership confirmation
- [ ] IP-transfer-to-Foundation record coverage confirmation
- [ ] Export-control crypto notice drafted (Ed25519, SHA-256, Shamir)

## Status summary (as of 2026-05-03)

**Agent-actionable items: ALL CLOSED.** Every Phase-00 item that does not require an external party (trademark office, Foundation board, legal counsel) has shipped artifacts. Phase-01 entry is gated solely on:

1. Trademark sweep close (USPTO/EUIPO/UK IPO) → final mark decision
2. Foundation board endorsement of runtime-pluggability model (ADR-0009)
3. Counsel sign-off on composite LICENSE + SPDX + export-control + compatibility statement
4. AT-PHASE-DATE-RECHECK §B re-runs (mailbox verification, CoC link, kailash-py PyPI name, namespace re-snapshot immediately before launch)

None of these are agent-actionable. Phase-01 entry remains gated externally.
