# 08 — Skills + ENVELOPE.md Companion

**Document status:** draft v1 — ready for `/redteam`
**Scope:** External-format `SKILL.md` ingest, generated `ENVELOPE.md` companion, CO-compliance validator, permission-to-PACT-dimension translation, install-time checks, `force_install=True` flag, Envelope Library registry (Foundation-Verified / Community / Organization tiers).
**Sources:** doc 00 v3 ADR-0005 (SKILL.md compat with CO superset), doc 02 v3 (envelope semantics + composition rules), doc 09 v3 (T-020 malicious skill author, T-021 malicious envelope publisher, T-022 Sybil, T-092 envelope spam flood).

---

## 1. Purpose

Envoy ingests `SKILL.md` skills from external ecosystems unchanged and generates an `ENVELOPE.md` companion declaring the skill's required PACT-dimension permissions. CO methodology is the authoritative superset per ADR-0005.

### In scope

- `SKILL.md` parser (ingest unchanged external format).
- `ENVELOPE.md` schema (doc 08's own contribution).
- Permission-to-PACT-dimension mapping.
- CO validator (install-time).
- `force_install=True` UX + Ledger flagging per doc 00 §4.1 item 16.
- Envelope Library registry tiers (FV / Community / Organization).
- Sybil + spam defenses per doc 09 T-020/T-021/T-022/T-092.
- Skill sandbox (Python subprocess Phase 01–03; wasm Phase 04).

### Out of scope

- Envelope schema itself (doc 02).
- Runtime invocation of skills (doc 05).
- MCP governance middleware (doc 02 §14.6 + `McpGovernanceMiddleware` per mint#4).

---

## 2. `SKILL.md` format + parser

Envoy ingests unchanged external format. Canonical structure per external ecosystem conventions:

```markdown
---
name: send-tweet
version: 1.0.0
description: Posts a tweet to user's Twitter account
permissions:
  - http_post:*.twitter.com
  - oauth:twitter
---

# Usage

...skill code...
```

Parser extracts:

- `name`, `version`, `description` (metadata).
- `permissions` array (external format strings).
- Inline code blocks (Python / shell / TypeScript depending on ecosystem).

## 3. `ENVELOPE.md` companion schema

Envoy generates on `SKILL.md` ingest:

```yaml
# ENVELOPE.md
schema_version: envelope-md/1.0
skill_id: <name>@<version>
skill_source_hash: <sha256 of SKILL.md content>
generated_at: <iso8601>
generated_by_co_validator_version: v2
publisher:
  genesis_id: <sha256:publisher_genesis>
  signature_hex: <ed25519 signature over this ENVELOPE.md>

requested_permissions:
  financial:
    per_call_ceiling_microdollars: 100000
    rationale: "http_post:*.twitter.com Twitter API calls cost ~$0.01"
  operational:
    tool_allowlist:
      - http_post
    rate_limits:
      http_post: { per_minute: 5 }
  temporal:
    allowed_windows: []   # no temporal restrictions declared
  data_access:
    classification_clearance: Internal
    field_allowlist_per_model: {}
  communication:
    domain_allowlist: [*.twitter.com]
    content_rules:
      - rule_id: "no-attachments-external"
        when_ast: { type: "Literal", value: true }
        content_types_forbidden: ["attachment_gt_1mb"]

co_validator_result:
  passed: true
  score: 0.92
  warnings:
    - "permission 'oauth:twitter' maps to Connection Vault credential; verify user consent at install"
  errors: []
```

## 4. Permission-to-PACT-dimension mapping

Foundation-curated mapping table at `envoy-registry:permission-to-pact-dimension:v1`:

| External permission pattern | PACT dimension              | Generated constraint                                           |
| --------------------------- | --------------------------- | -------------------------------------------------------------- |
| `bash:*`                    | Operational + Data Access   | tool_allowlist → [`bash`]; data_access clearance: Confidential |
| `file-read:*`               | Data Access                 | field_allowlist_per_model: all                                 |
| `file-write:*`              | Operational                 | tool_allowlist → [`file_write`]                                |
| `http-post:<domain>`        | Communication               | domain_allowlist → [domain]                                    |
| `http-get:<domain>`         | Communication               | domain_allowlist → [domain]                                    |
| `mcp:<server>`              | Operational + Communication | MCP governance middleware                                      |
| `oauth:<service>`           | Connection Vault credential | stored in Connection Vault                                     |
| `exec:<pattern>`            | Operational                 | tool_allowlist → [exec]; HIGH severity warning                 |

Unknown patterns → validator error (`UnknownPermissionPatternError`).

## 5. CO-compliance validator

Runs at install-time. Checks:

1. **Schema validity** of `SKILL.md`.
2. **Permission pattern recognition** — every requested permission maps to a known pattern in the registry.
3. **Consistency check** — declared permissions match inferred permissions from skill code analysis (e.g. if code calls `http.post('twitter.com')`, `http_post:*.twitter.com` must be declared).
4. **Over-privilege warning** — permissions broader than code uses flagged.
5. **Adversarial pattern detection** — registry of known-adversarial patterns (permission-escalation, exfiltration to attacker domains, privilege-overreach).
6. **Signature verification** — publisher signature on `ENVELOPE.md` verifies against publisher key in Envelope Library.

Result: `{passed: bool, score: float, warnings: [...], errors: [...]}`.

**Score thresholds:**

- `score ≥ 0.8`: pass.
- `0.5 ≤ score < 0.8`: pass with warnings surfaced to user.
- `score < 0.5`: fail — requires `force_install=True`.

## 6. `force_install=True` UX (doc 00 §4.1 item 16)

When validator fails OR user explicitly bypasses:

```
⚠️  This skill failed CO validation (score: 0.4).

Validator findings:
  - ERROR: permission 'exec:*' enables arbitrary command execution
  - WARNING: declared permissions exceed inferred code behavior

Installing with --force will:
  ✓ Install the skill
  ✗ Visible-flag in your Ledger: "force_install_used"
  ✗ Visible-flag in your envelope: "this skill operates outside governance promises"
  ✗ Visible-flag in skill inventory: next to skill name

You've waived Envoy's safety promise for this skill.

Proceed with --force? [y/N]
```

Force-installed skills tagged at Ledger, envelope, and inventory. Monthly Trust Report surfaces count + list.

## 7. Envelope Library tiers

### 7.1 Foundation-Verified (FV) tier

- Curated subset; reviewed by Foundation.
- 2-of-N Foundation steward signatures (doc 09 T-051 + doc 02 §14.3 pattern).
- Featured in default registry view.
- Minimum bar: CO/EATP spec-compliance, red-teamed, no force_install needed.

### 7.2 Community tier (Phase 03)

- Open publishing.
- Publisher Ed25519 signatures.
- Ranking: adoption × (1 − revocation rate).
- Sybil defenses per doc 09 T-022:
  - Publisher identity-proofing (Foundation-vouched / proof-of-stake / verified-domain).
  - Publisher-fork tracking (near-duplicate envelopes weighted lower; Jaccard > 0.8 similarity).
  - Adoption-rate cap per publisher-week.
- Spam-flood defense per doc 09 T-092:
  - Publish rate-limit per publisher key.
  - Spam auto-classifier.
  - Reviewer queue priority by publisher identity-proof tier.

### 7.3 Organization tier (Phase 04)

- Private registries per org Trust Lineage root.
- Enterprise attestation (doc 02 §14.3) gates access.

## 8. Skill runtime sandbox

### 8.1 Phase 01–03: Python subprocess + PACT enforcement

- Skill executes in isolated Python subprocess.
- Subprocess has envelope-constrained file/network access via `PactGovernanceEngine` middleware.
- Resource limits: CPU (per-call timeout), memory (bounded heap), wall-clock.
- MCP governance middleware (mint#4) wraps MCP tool calls.

### 8.2 Phase 04+: wasm sandbox

- Rust skills SDK published via `kailash-plugin-guest` (the open-source binding per doc 00 v3 §4.1).
- wasm modules loaded by Envoy runtime.
- Host-function boundary enforces envelope.

## 9. Skill install flow

```
envoy skill install @author/skill-name@version

1. Fetch SKILL.md from Envelope Library.
2. Parse + generate ENVELOPE.md.
3. Run CO validator.
4. If pass: render user-review dialog with visible-secret binding.
5. User reviews requested permissions; approves.
6. Grant Moment signed; skill added to inventory.
7. Ledger entry: skill_install { skill_id, envelope_md_hash, co_score, force_install: false/true }.
```

## 10. Skill inventory

```yaml
installed_skills:
  - skill_id: @terrene-foundation/send-email@1.2.0
    installed_at: <iso8601>
    co_score: 0.95
    force_install: false
    envelope_md_path: skills/send-email@1.2.0/ENVELOPE.md
    grant_moment_ledger_id: sha256:...
    revocation_requested: false
```

## 11. Cross-references

- doc 00 v3 ADR-0005 (SKILL.md compat), §4.1 item 16 (force_install).
- doc 02 v3 envelope schema, §14.6 classifier registry.
- doc 03 v2 signing paths for publisher signatures.
- doc 05 v2 runtime skill invocation.
- doc 07 v1 MCP transport (if skill uses MCP).
- doc 09 v3 T-020 malicious skill author, T-021 malicious envelope publisher, T-022 Sybil, T-092 spam flood.

Cross-SDK: SKILL.md parser + ENVELOPE.md generator + CO validator is Envoy-new-code (doc 02 §14.3 gap). Mint#7 formalizes ENVELOPE.md schema.

## 12. Open questions

1. Permission pattern registry governance — Foundation-curated; community contributions via PR with review.
2. Inferred-vs-declared permissions check — requires code analysis; Phase 02 scope (Phase 01 manual review).
3. Adversarial-pattern detection classifier — quarterly retraining per doc 09 T-020.
4. Organization tier private registry protocol — Phase 04 design; likely HTTP + mutual TLS + org-Genesis-signed requests.

**End of doc 08 v1.**
