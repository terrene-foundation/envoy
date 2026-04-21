# Envoy — Workspaces

This directory holds working state for the COC workflow (`/analyze`, `/todos`, `/implement`, `/redteam`, `/codify`). Each subdirectory is a named workspace scoped to a phase or initiative.

## Content policy

Everything in `workspaces/` is **tracked in git and goes public**. Content here MUST follow the Terrene Foundation communications mandate:

- Vendor-neutral voice.
- Lead with what Envoy offers; do not frame third-party projects adversarially.
- Technical critique is fine when aimed at Envoy's own artefacts (audit findings, risk logs, red-team notes on our code).
- External projects are referenced only as neutral context or interoperability anchors.

If you have material that does not meet this bar — first-pass competitive analysis, private strategic briefs, raw research with charged voice — put it in the sibling archive:

```
~/repos/dev/envoy-internal-research/
```

That directory is outside this repo and is not published.

## Workspace layout

Each workspace follows the COC standard subdirectory pattern:

| Subdir          | Purpose                                                          |
| --------------- | ---------------------------------------------------------------- |
| `01-analysis/`  | Research outputs from `/analyze`                                 |
| `02-plans/`     | Plans, briefs, and architectural designs                         |
| `03-implement/` | Implementation notes and state (created on demand)               |
| `04-validate/`  | Validation, QA, red-team outputs, audit findings                 |
| `briefs/`       | Intake briefs for new work threads                               |
| `journal/`      | Numbered decision records (promoted to `DECISIONS.md` if they earn an ADR) |
| `todos/`        | Phase-scoped task tracking                                       |

## Active workspaces

- [`phase-00-alignment/`](phase-00-alignment/) — Phase 00 alignment gate work: trademark sweep, namespace reservation, legal-counsel items, Foundation board endorsement, licensing-audit follow-ups.

## Journal voice

Decision records in `journal/` use Foundation voice. Record:

- The decision.
- The rationale in Envoy-positive terms.
- The consequences.

Do not record the adversarial framing of why an alternative was rejected. If a decision was between two external products or approaches, record it as "we chose X because X satisfies Envoy constraint Y" — not "we rejected Z because Z is bad."

## Archive reference

Historical internal research (first-pass analyses, original strategic briefs, internal decision trail) is preserved at `~/repos/dev/envoy-internal-research/` as a read-only reference. Do not copy from the archive into this directory without rewriting to Foundation voice first.
