# Licensing Audit — Follow-ups

**Audit date:** 2026-04-21
**Scope:** `kailash-coc-claude-rs` and `kailash-coc-claude-py` USE templates (Foundation artefacts at `~/repos/loom/`), and related variant-source files under `~/repos/loom/.claude/variants/`.
**Context:** Before Envoy publishes any public artefact that transitively names the Kailash bindings, the Foundation's own template repos need to accurately reflect the locked ground truth: bindings are free, ungated, Foundation-hosted, with a pure-Python peer alternative.

Full audit trail is archived at `~/repos/dev/envoy-internal-research/openclaw-analysis/04-validate/legal-redteam-kailash-coc-claude-rs-2026-04-21.md`. This document captures only the items still open.

## Status at audit close

- **5 HIGH findings fixed inline** on the RS template root (LICENSE, NOTICE, paid-product framing, placeholder URLs, SPDX metadata).
- **1 HIGH finding blocked** by the artefact-flow rule — requires upstream fix at the variant source; needs a user decision between two resolutions (item H6 below).
- **1 MEDIUM finding deferred per audit scope** — sibling PY template carries the same defects; mirror fix needed (item M2).
- **1 LOW finding flagged** — RS `git.md` references a private repo identity in the public USE template (item L1).

## Open items

### H6 — variant-source `independence.md` mismatch

**File:** `~/repos/loom/.claude/variants/rs/rules/independence.md` (sync source for RS USE template).

**Problem:** The variant's `independence.md` describes the target repo as a proprietary-source BUILD repo. That description is accurate for `kailash-rs` (the proprietary BUILD repo) but not for `kailash-coc-claude-rs` (a free Apache 2.0 Foundation USE template). The variant sync carries the wrong description into the USE template and cannot be corrected downstream because sync overwrites direct edits.

**Two resolutions — user picks one:**

- **(a)** Re-scope the variant as BUILD-repo-only. Author a separate USE-template `independence.md` that matches the free-binding + free-template reality.
- **(b)** Extend `sync-manifest.yaml` exclusions so the BUILD-scoped variant does not reach the USE template; the global `rules/independence.md` (Foundation Apache 2.0 voice) flows through instead.

**Drafted replacement text** for the USE template is ready; it will be applied at the variant source once a resolution is chosen.

### M1 — variant-synced files referencing `kailash-enterprise` paid framing

**Files (partial):**

- `~/repos/loom/.claude/variants/rs/rules/testing.md`
- `~/repos/loom/.claude/rules/testing.md`
- `~/repos/loom/.claude/skills/05-enterprise/SKILL.md`
- `~/repos/loom/.claude/skills/06-python-bindings/SKILL.md`
- ~35 additional skill/agent files per grep.

**Status:** Fix at variant source after H6 resolution is picked. Direct edits at the USE template would be overwritten on next `/sync`.

### M2 — mirror RS fixes to `kailash-coc-claude-py`

**Files in `~/repos/loom/kailash-coc-claude-py/`:**

- `LICENSE` — same copyright + field-of-use defect as RS H1.
- `README.md` — placeholder URLs (`your-org`).
- `pyproject.toml` — missing `license = "Apache-2.0"` SPDX.

**Resolution:** Apply the same five fixes already landed on RS: clean Apache 2.0 LICENSE with Foundation copyright, new NOTICE, placeholder replacement with `terrene-foundation`, SPDX metadata, paid-product framing removal (if present).

### L1 — RS `git.md` private-repo reference

**File:** RS USE template ships a branch-protection table naming a private repo. Not load-bearing for users and not a licensing violation, but the public USE template should not advertise a non-public repo identity.

**Resolution:** Filter via `/sync` variant exclusion.

## Follow-ups requiring real legal counsel

1. **CLA / re-licensing posture for historical contributions.** Before the cleaned LICENSE propagates, counsel should confirm that all prior contributions on the old LICENSE terms can be relicensed to clean Apache 2.0 with Foundation copyright.
2. **"Kailash" trademark ownership confirmation.** The templates use "Kailash" freely. Counsel should confirm the Foundation holds the mark and advise on third-party attribution requirements.
3. **IP-transfer-to-Foundation record coverage.** The old LICENSE's prior copyright implies a legacy IP-transfer history. Counsel should confirm the Foundation's IP-transfer record covers each template's contribution history before the reassigned-copyright LICENSE ships.
4. **Export-control crypto notice.** Bindings likely include TLS / crypto code (via transport and auth crates). A cryptographic export-control notice is warranted.

## Files already updated (RS template root)

- `LICENSE` — clean Apache 2.0, Foundation copyright.
- `NOTICE` — new; Foundation attribution, free-distribution statement, `kailash-py` peer option.
- `README.md` — install commands corrected, placeholder URLs replaced, licensing-posture paragraph added.
- `pyproject.toml` — paid-product dependency replaced with free peer; SPDX added.
- `CLAUDE.md` — paid-product references replaced; platform table corrected.

## Next action

1. Resolve H6. This unblocks M1.
2. Apply M2 to the PY template.
3. Engage counsel on the four items above; land decisions in `DECISIONS.md` as a new ADR if they change any Envoy-facing posture.
