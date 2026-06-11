# skill-ingest

## Purpose

SKILL.md parser, ENVELOPE.md companion generator, CO validator, permission-to-PACT-dimension translator, force_install flag, Envelope Library tiers.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/08-skills-and-envelope-companion.md v1`.
- **Threats mitigated:** T-020 malicious skill author, T-021 envelope publisher, T-022 Sybil, T-092 spam flood, T-090 sandbox DoS.
- **BETs tested:** BET-7 SKILL.md compat, BET-12 authorship-gated posture.

## SKILL.md parser

Parses external ecosystem's canonical format: name, version, description, permissions array, inline code blocks.

## ENVELOPE.md generator

Produces YAML companion declaring `{skill_id, skill_source_hash, publisher{genesis_id, signature}, requested_permissions{financial, operational, temporal, data_access, communication}, co_validator_result{passed, score, warnings, errors}}`.

## Permission → PACT dimension mapping

Foundation-curated registry `envoy-registry:permission-to-pact-dimension:v1`. Maps:

- `bash:*` → Operational + Data Access (Confidential clearance).
- `file-read:*` → Data Access.
- `file-write:*` → Operational.
- `http-post:<domain>` → Communication.
- `http-get:<domain>` → Communication (GET-surface reaches — `requests.get`/`httpx.get`/`urlopen` — inferred by the CO validator's AST walk).
- `mcp:<server>` → Operational + Communication (+ MCP governance middleware).
- `oauth:<service>` → Connection Vault. In the ENVELOPE.md `requested_permissions` (which carries the five axes financial/operational/temporal/data_access/communication and no dedicated connection-vault axis), `oauth:` permissions surface under `operational` with the full pattern string retained so the vault target is not lost.
- `exec:<pattern>` → Operational (HIGH severity).

Unknown → `UnknownPermissionPatternError`.

SKILL.md ingest never populates the `financial` or `temporal` axes — no documented SKILL.md permission pattern maps to them. The companion ships fixed-shape (all five axes always present; those two are empty for SKILL.md-sourced skills).

## CO validator

Checks at install:

1. SKILL.md schema valid.
2. Permission patterns recognized.
3. Declared = inferred (code analysis; Phase 02 automated).
4. Over-privilege warning.
5. Adversarial-pattern detection (quarterly-retrained `envoy-registry:adversarial-skill-patterns:v1`).
6. Publisher signature verifies.

Score thresholds: ≥0.8 pass; 0.5–0.8 pass with warnings; <0.5 fail (requires `force_install=True`).

Step 3 (Phase-02 automated, `envoy/skill_ingest/inference.py` + `comparison.py`) uses a CONSERVATIVE Python `ast` static walk (literal-call-only; never executes skill code) plus an import-graph second opinion that can only WARN, never auto-reject. The asymmetric routing: an AST-proven literal call to an undeclared capability (including literal `getattr`/`eval`/`importlib` dynamic-dispatch constructs) scores <0.5 → reject; an import-graph-only extra scores in the 0.5–0.8 warning band; declared ⊃ inferred (over-declaration) routes to step 4's `OverPrivilegeWarning`, not a reject. Unparseable skill code fails closed (`SkillCodeUnparseableError`). Step 5 is shipped as a typed pending surface (`AdversarialCheckPending`); the active classifier-ensemble adversarial check is out of scope for this step's current surface.

## `force_install=True` (doc 00 v3 §4.1 item 16)

- Visible Ledger flag `force_install_used`.
- Visible envelope flag.
- Visible skill inventory marker.
- User waives governance promise for that skill.
- Monthly Trust Report surfaces count.

## Envelope Library tiers

- **Foundation-Verified:** Reviewed; 2-of-N Foundation signatures; featured default.
- **Community:** Open publishing; Ed25519 publisher keys; ranked adoption × (1 − revocation); anti-Sybil per T-022 (identity-proofing + fork-tracking + adoption-rate cap); anti-spam per T-092 (publish rate-limit + spam classifier + reviewer priority).
- **Organization:** Private per-org registries (Phase 04).

## Skill sandbox

- **Phase 01–03:** Python subprocess + PACT enforcement. CPU + memory + wall-clock limits.
- **Phase 04+:** WASM sandbox via `kailash-plugin-guest` (open-source per doc 00 v3 §4.1).

## Install flow

`envoy skill install @author/skill-name@version` → fetch → parse → generate ENVELOPE.md → CO validator → Grant Moment user review → sign → inventory + Ledger.

## Error taxonomy

| Error                                 | Trigger                                                                                              | User action                                                                           | Retry                      |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | -------------------------- |
| `SkillManifestParseError`             | SKILL.md fails schema validation (missing required fields, malformed permissions array)              | Skill author fixes manifest; user retries install with corrected version              | Manual after fix           |
| `EnvelopeCompanionMissingError`       | SKILL.md installed without ENVELOPE.md generation completing (parser crash, IO failure)              | Re-run install; if persistent, file issue against skill-ingest                        | Auto on next install       |
| `UnknownPermissionPatternError`       | SKILL.md declares permission pattern not present in `envoy-registry:permission-to-pact-dimension:v1` | Wait for registry refresh OR contact Foundation to add pattern                        | Auto on registry refresh   |
| `COValidatorRefusedError`             | CO validator score < 0.5 AND `force_install=False`                                                   | Review validator output; user explicitly opts in via `force_install=True` if accepted | Manual after force_install |
| `AdversarialSkillPatternMatchedError` | CO validator step 5 matches `envoy-registry:adversarial-skill-patterns:v1`                           | Refuse install; if false-positive, user appeals via Foundation moderator queue        | Never (audit needed)       |
| `PublisherSignatureInvalidError`      | CO validator step 6: publisher Ed25519 signature fails verification                                  | Verify publisher key; possible supply-chain tamper                                    | Never                      |
| `OverPrivilegeWarning`                | CO validator detects declared permissions exceed inferred (Phase 02 automated)                       | Surface warning at Grant Moment; user may downscope or accept                         | Manual after review        |
| `SandboxDoSDetectedError`             | Skill exceeds CPU / memory / wall-clock limit during invocation (T-090)                              | Skill killed; Ledger entry written; surface in next digest                            | Auto with rate-limit       |
| `SpamFloodRateLimitError`             | Publisher exceeds Envelope Library publish rate-limit (T-092)                                        | Publisher contacts Foundation moderator for tier review                               | Auto after window          |
| `ForceInstallWaiverRequiredError`     | `force_install=True` attempted without explicit user acknowledgement payload                         | User signs waiver payload (visible Ledger flag + envelope flag)                       | Manual after waiver        |
| `SkillSourceHashMismatchError`        | Fetched skill source bytes do not match declared `skill_source_hash` in ENVELOPE.md                  | Refuse install; suspected mirror tamper or bit-rot                                    | Never                      |

All errors persisted to Ledger with `record_id` redacted via `format_record_id_for_event` per specs/classification-policy.md.

## Cross-references

- specs/envelope-model.md — envelope schema; permission-to-dimension compile.
- specs/grant-moment.md — install-time Grant Moment.
- specs/runtime-abstraction.md — skill invocation contract.
- specs/foundation-ops.md — Envelope Library registry.
- specs/acceptance-metrics.md — 100-benign + 3-adversarial corpus.
- specs/threat-model.md — T-020, T-021, T-022, T-090, T-092.

## Test location

- `tests/integration/test_skill_md_parser_canonical_format.py` — round-trip parser against external ecosystem's canonical SKILL.md format (Tier 2).
- `tests/integration/test_envelope_md_generator_field_complete.py` — every field in `{skill_id, skill_source_hash, publisher, requested_permissions, co_validator_result}` populated.
- `tests/integration/test_co_validator_six_steps.py` (`TestStep2UnknownPattern` + happy path) — documented mapping entries (bash, file-read, file-write, http-post, mcp, oauth) resolve; an unknown category raises.
- `tests/integration/test_co_validator_six_steps.py` — every CO validator step exercised on a known-good skill (Tier 2).
- `tests/integration/test_co_validator_100_benign_corpus.py` + `tests/integration/test_co_validator_3_adversarial_corpus.py` — score-band split: ≥0.8 pass (benign), <0.5 refuse (adversarial), 0.5–0.8 warning (the re-derived 25 of the 100 benign).
- `tests/integration/test_force_install_visible_flags.py` — `force_install=True` writes Ledger flag, envelope flag, inventory marker; surfaces in Monthly Trust Report.
- `tests/integration/test_skill_sandbox_cpu_memory_limits.py` — Phase 01–03 Python subprocess limits enforced (Tier 2).
- `tests/integration/test_envelope_library_tier_signatures.py` — Foundation-Verified 2-of-N + Community Ed25519 publisher signatures.
- `tests/integration/test_install_flow_grant_moment.py` — install → fetch → parse → generate → CO validator → Grant Moment → sign → inventory + Ledger.
- `tests/integration/test_co_validator_100_benign_corpus.py` — 100-benign skill corpus passes CO validator (specs/acceptance-metrics.md).
- `tests/integration/test_co_validator_3_adversarial_corpus.py` — 3-adversarial skill corpus refused (specs/acceptance-metrics.md).
- `tests/regression/test_t020_malicious_skill_author.py` — T-020 adversarial-pattern detection.
- `tests/integration/test_co_validator_six_steps.py` (`TestStep6PublisherSignature`) — T-021 publisher signature verification (bad signature + unpinned publisher both raise).
- `tests/regression/test_t022_sybil_publisher.py` — T-022 identity-proof tier + adoption-rate cap.
- `tests/regression/test_t090_sandbox_dos.py` — T-090 sandbox CPU/memory/wall-clock limits.
- `tests/regression/test_t092_spam_flood.py` — T-092 publish rate-limit + reviewer priority.

## Open questions

1. WASM sandbox migration cadence (Phase 04+) — when does `kailash-plugin-guest` reach feature parity with the Python subprocess sandbox (signal handling, FS isolation, network egress policy), and what is the migration UX for users with installed Phase 01–03 skills?
2. CO validator step 3 (declared = inferred) automation in Phase 02 — what code-analysis tooling produces the inferred-permissions set, and what is the false-positive budget before the validator becomes net-noise?
3. Adversarial-pattern registry refresh cadence — quarterly retraining is documented; how is "quarterly" calendar-anchored, and what is the user-side surface when a previously-installed skill matches a newly-added pattern (auto-uninstall? Warn? Defer)?
4. Permission pattern grammar extensibility — community-published skills may need permission patterns not in the Foundation registry; what is the proposal flow (Foundation moderator queue? Community-tier registry?), and does the Foundation registry pre-emptively register category-prefix patterns?
5. Skill versioning under publisher key rotation — when a publisher rotates their Ed25519 key, do existing installed skills retain their original signature attestation or require re-attestation under the new key?
