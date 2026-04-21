# Phase 00 Plan

**Phase:** 00 — Alignment
**Goal:** Land the concept, verify names, registries, and licensing; secure Foundation sign-off.
**Gates:** Phase 01 (`/analyze` MVP scope) cannot open until all items close.

## Work tracks

### Track A — Naming and namespace (blocks public push)

1. **Trademark sweep.** USPTO + EUIPO + UK IPO, Class 9 (software) + Class 42 (SaaS). Candidates: "Envoy Agent", "Envoy AI", "Envoy.ai", "Terrene Envoy".
2. **Final legal mark decision.** Based on sweep findings; single mark locked for all public collateral.
3. **Namespace reservation.** Confirmed available as of 2026-04-21:
   - npm: `envoy-agent`
   - PyPI: `envoy-agent`
   - crates.io: `envoy-agent`
   - GitHub org: to be reserved (`envoy-agent` or alternative based on trademark outcome).

### Track B — Claim verification (blocks public push)

Every factual claim in `README.md`, `CHARTER.md`, `DECISIONS.md`, `ROADMAP.md`, and downstream website copy must be:

1. Verified against a cited source.
2. Scoped precisely (avoid unverified statistics or third-party adoption figures).
3. Reviewed for compliance with the Foundation communications mandate (vendor-neutral voice; lead with what Envoy offers).

Deliverable: a citation log committed to `04-validate/claims-log.md` (to be created as claims are verified).

### Track C — Licensing and legal counsel (ADR-0009 items)

Seven items blocking public launch; see `DECISIONS.md` §ADR-0009 for full context. Track status in `todos/phase-00.md`:

1. Composite LICENSE file for `kailash-rs-bindings` wheel.
2. SPDX metadata for PyPI.
3. Terrene Foundation charter compatibility statement (board sign-off on runtime-pluggability model).
4. User-facing disclosure text (installer, README, runtime-picker copy).
5. Export-control assessment for Rust binary redistribution.
6. Runtime-swap conformance contract draft.
7. Trademark filings.

### Track D — Foundation COC template licensing follow-ups

Upstream fixes on the Foundation's COC template repos (`kailash-coc-claude-rs`, `kailash-coc-claude-py`). Audit landed 2026-04-21; see [`04-validate/licensing-audit-followups.md`](../04-validate/licensing-audit-followups.md).

Two open items:

1. **H6 — variant-source `independence.md` resolution.** Two resolutions available; user decision gates M1.
2. **M2 — mirror RS fixes to PY template.** Same diff pattern as the RS fixes already applied.

### Track E — Foundation sign-off

1. Terrene Foundation board endorses Envoy as a Foundation project.
2. Board reviews and endorses the runtime-pluggability model (ADR-0001 + ADR-0009).
3. Compatibility review: Apache 2.0 code + CC BY 4.0 methodology + ingesting MIT-licensed `SKILL.md`-format skills.
4. Working concept one-pager published for board review.

## Sequencing

- Tracks A, C, D, E can run in parallel.
- Track B is a continuous sweep; re-run before each major public-facing document change.
- **No public push** (GitHub org creation, PyPI upload, website launch) until Track A + Track C + Track E close.

## Exit

All items closed → promote Phase 00 decisions to ADRs if any are new → open `workspaces/phase-01-mvp/` → `/analyze`.
