export const meta = {
  name: 'redteam-round',
  description: 'One /redteam round: fine-grained parallel dimension finders → adversarial per-finding verification → confirmed in-scope findings',
  phases: [
    { title: 'Find', detail: 'parallel dimension finders (spec clusters, security×2, code×2, value×2)' },
    { title: 'Verify', detail: 'adversarial refutation of each finding; default refuted unless evidence reproduces' },
  ],
}

// args = { round, priorFindingsNote, only: [dimKeys], alreadyConfirmed: <string> }
const round = (args && args.round) || 1
const priorNote = (args && args.priorFindingsNote) || 'First fresh round at HEAD.'
const onlyKeys = (args && args.only) || null
const alreadyConfirmed = (args && args.alreadyConfirmed) || 'none'

const PREAMBLE = `PROJECT: envoy — Phase-01 MVP, a Python agent-trust system (consumer of Rust-backed kailash bindings).
Production package: envoy/  (envelope, trust, ledger, model, connection_vault, runtime, heartbeat, authorship, shamir, boundary_conversation, grant_moment, budget, channels, daily_digest, cli).
Tests: tests/{tier1,tier2,tier3,integration,regression,e2e,sdk}. Suite GREEN at HEAD 70eea1a (1693 passed).
You are a RED-TEAM finder. Round ${round}. ${priorNote}

SOURCE OF TRUTH: specs/*.md (37 files; specs/_index.md=manifest). EC objectives: workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md. Brief: workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md. User-flows: workspaces/phase-01-mvp/03-user-flows/.
CONVERGENCE BAR: 0 CRITICAL, 0 HIGH; spec 100% AST/grep verified; every NEW module has ≥1 importing test; 0 mock/fake data in production.

KNOWN DISPOSITIONS — NOT findings (do not re-report):
1. ResourceWarning "unclosed database" (sqlite, threading.py:303/pathlib) = UPSTREAM kailash thread-local conns; kailash-py#1245.
2. envoy/runtime/adapters/*.py Phase-02 stubs raising a TYPED error (not bare NotImplementedError) = iterative-TODO carve-out (zero-tolerance Rule 6). The typed-stub PATTERN is correct.
3. grant_moment/resolution.py ResolutionShape.to_decision raising NotImplementedError = ABC override guard.
4. F2 independent ledger verifier = SEPARATE repo (terrene-foundation/envoy-ledger-verifier); in_repo_scope=false.
5. Phase-02 substrate / Windows-host / Redis-down = external blockers; in_repo_scope=false.
6. Spec '## Test location' citing tests/acceptance/phase_0{2,3,4}, tests/conformance, anchor/phase02, verifier/EC-9, enterprise pilots = legitimately-future/out-of-repo; in_repo_scope=false unless the cited test is a Phase-01 primitive's test that exists under a DIFFERENT path (then it's a HIGH phantom-citation drift).

ALREADY CONFIRMED THIS CYCLE (being fixed; do NOT re-report — only report NEW issues): ${alreadyConfirmed}

RIGOR: every assertion MUST cite a LITERAL command (grep -n/-c, python3 -c 'import ast...', uv run pytest --collect-only -q, wc -l) AND its ACTUAL output. "exists: yes"/"looks correct" = BLOCKED. Re-derive from scratch.
SEVERITY: CRITICAL=security/data-integrity/silent-corruption or broken acceptance gate; HIGH=spec divergence w/o logged deviation, new module zero tests, fake/stub-as-real, error-hiding losing a stack trace; MED=actionability/hygiene; LOW=cosmetic/doc.

*** BUDGET + EMIT DISCIPLINE (CRITICAL) ***
Spend AT MOST ~60% of your effort investigating. You have limited budget. Your FINAL action MUST be a single StructuredOutput call carrying your findings array (use findings:[] if you found nothing). Do NOT write a prose report instead of calling StructuredOutput — a prose report with no StructuredOutput call is a FAILED run. Cap at ~8 findings; pick the highest-severity. Stop investigating and EMIT before you run low on budget.`

const FINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['dimension', 'findings'],
  properties: {
    dimension: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'severity', 'title', 'location', 'claim', 'evidence_command', 'evidence_output', 'in_repo_scope', 'suggested_fix'],
        properties: {
          id: { type: 'string' }, severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MED', 'LOW'] },
          title: { type: 'string' }, location: { type: 'string' }, claim: { type: 'string' },
          evidence_command: { type: 'string' }, evidence_output: { type: 'string' },
          in_repo_scope: { type: 'boolean' }, suggested_fix: { type: 'string' },
        },
      },
    },
  },
}
const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['finding_id', 'is_real', 'correct_severity', 'in_repo_scope', 'reproduced', 'refutation_notes'],
  properties: {
    finding_id: { type: 'string' }, is_real: { type: 'boolean' },
    correct_severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MED', 'LOW', 'NOT_A_FINDING'] },
    in_repo_scope: { type: 'boolean' }, reproduced: { type: 'boolean' }, refutation_notes: { type: 'string' },
  },
}

const ALL_DIMS = [
  { key: 'spec-ledger', agentType: 'general-purpose', focus: `SPEC-COMPLIANCE: ledger + ledger-merge. Read specs/ledger.md, specs/ledger-merge.md. Verify every promise (class sig, field, hash-chain, export format, merge semantics) against envoy/ledger/ via grep/ast.parse. Flag field-shape/signature divergence with NO logged deviation.` },
  { key: 'spec-grant', agentType: 'general-purpose', focus: `SPEC-COMPLIANCE: grant-moment + boundary-conversation. Read specs/grant-moment.md, specs/boundary-conversation.md. Verify against envoy/grant_moment/, envoy/boundary_conversation/. (boundary § Test-location phantom citations already confirmed — do not re-report; find NEW divergences: resolution shapes, cascade revoke, EnvelopeConfig output, visible-secret render.)` },
  { key: 'spec-vault', agentType: 'general-purpose', focus: `SPEC-COMPLIANCE: trust-vault + connection-vault + shamir. Read specs/trust-vault.md, specs/connection-vault.md, specs/shamir-recovery.md. Verify against envoy/trust/, envoy/connection_vault/, envoy/shamir/. Focus: vault lock/unlock/zeroize lifecycle, keychain wrapper, Shamir C(5,3)=10 reconstruction, SLIP-0039 fields.` },
  { key: 'spec-author-env', agentType: 'general-purpose', focus: `SPEC-COMPLIANCE: authorship + envelope + classification + posture. Read specs/authorship-score.md, specs/envelope-model.md, specs/envelope-library.md, specs/classification-policy.md, specs/posture-ladder.md. Verify against envoy/authorship/, envoy/envelope/. Focus: authorship-score gate (≥N gates DELEGATING/AUTONOMOUS), envelope intersect/conflict propagation, classification fail-closed default, posture ladder.` },
  { key: 'spec-channels', agentType: 'general-purpose', focus: `SPEC-COMPLIANCE: channels + daily-digest. Read specs/channel-adapters.md, specs/daily-digest.md. Verify against envoy/channels/, envoy/daily_digest/. Focus: which of 6 messaging adapters ship vs de-scoped-to-3 (Telegram/Slack/Discord); daily-digest 7-fire scheduling; cross-channel coherence.` },
  { key: 'spec-runtime', agentType: 'general-purpose', focus: `SPEC-COMPLIANCE: model + runtime + budget + session + heartbeat. Read specs/model-adapter.md, specs/runtime-abstraction.md, specs/budget-tracker.md, specs/session-state.md, specs/foundation-health-heartbeat.md. Verify against envoy/model/, envoy/runtime/, envoy/budget/, envoy/heartbeat/. Typed Phase-02 stubs are OK (disposition #2) — but verify NON-stub methods do the promised work; verify abstract runtime interface EXISTS (brief invariant #2); verify heartbeat ship-vs-descope state matches a logged deviation.` },
  { key: 'sec-code', agentType: 'general-purpose', focus: `SECURITY (code-pattern audit of envoy/ — minimal spec reading). grep envoy/ for: hardcoded secrets (sk-/password=/token=); non-parameterized SQL (f-string/.format/concat into execute); eval/exec/subprocess shell=True; credential decode without null-byte rejection; secret values in log calls; fail-OPEN defaults on clearance/classification/posture (should be most-restrictive). Verify visible-secret render path (grant_moment) actually renders. Cite grep output per finding.` },
  { key: 'sec-threat', agentType: 'general-purpose', focus: `SECURITY (threat→test mapping). Read specs/threat-model.md, specs/network-security.md, specs/tool-output-sanitization.md. For each Phase-01 in-scope threat T-NNN with a "Threats mitigated" owner among shipped primitives, grep tests/ for test_t<NNN>; missing = HIGH. Sanitizer contract: token-replace (STATEMENT_BLOCKED etc.) NOT quote-escape; type-confusion raise NOT coerce. (TEST-02 threat-coverage-gate already confirmed — do not re-report; find specific UNTESTED in-scope threats.)` },
  { key: 'code-orphan', agentType: 'general-purpose', focus: `CODE: orphan + facade + dead-code. For each envoy/**/__init__.py __all__ entry, verify eager import + ≥1 external importer (grep -rln). Flag classes that wrap-and-forward with zero added behavior (facade-manager). Flag documented kwargs accepted but never consumed (silent-fallback at API surface). Flag dual-shape return consumed via hasattr structural guard. Cite grep/ast output.` },
  { key: 'code-hygiene', agentType: 'general-purpose', focus: `CODE: hygiene. NOTE the 6 'except Exception:' sites (ledger/bootstrap.py:152, ledger/facade.py:506, trust/vault.py:285/306/851, daily_digest/bootstrap.py:168) were ALREADY VERIFIED as clean (re-raise or log+proceed) — do NOT report them. Find OTHER error-hiding (bare except:/except: pass/except Exception: return None w/o logging). Find stale path refs in production strings that don't resolve (ZT-1/ZT-2 already found — find NEW ones). Find version mismatch (pyproject.toml vs envoy/__init__.py __version__). Cite output.` },
  { key: 'value-cli', agentType: 'general-purpose', focus: `VALUE/USER-FLOW: CLI + install/export/posture flows. The CLI (envoy/cli/) ships subcommands; session-notes say 7/10 wired (3 deferred). Run 'uv run python -m envoy.cli --help' (or the console entrypoint) and capture verbatim. Read storyboards 01-install-flow, 07-ledger-export-flow, 08-posture-ratchet-flow. Flag: a subcommand advertised in --help/README but unwired (user hits wall); a storyboard step whose backing code is a typed-stub mid-flow. Distinguish DEFERRED-by-design (cite receipt; in_repo_scope per whether fixable) from BROKEN. Cite command+output.` },
  { key: 'value-flows', agentType: 'general-purpose', focus: `VALUE/USER-FLOW: ritual flows. Read storyboards 02-boundary-conversation, 03-grant-moment, 04-daily-digest, 05-channel-onboarding, 06-shamir-backup. Trace each user step through envoy/ modules. Flag a storyboard step whose backing code is a stub/typed-error (user wall) vs deferred-by-design. Flag a value-claim in the brief with no backing code. Cite the trace (grep showing the backing function exists + is non-stub).` },
]

const dims = onlyKeys ? ALL_DIMS.filter((d) => onlyKeys.includes(d.key)) : ALL_DIMS

phase('Find')
log(`Round ${round}: ${dims.length} finders (${dims.map((d) => d.key).join(', ')}) + adversarial verify`)

const results = await pipeline(
  dims,
  (d) => agent(`${PREAMBLE}\n\nYOUR DIMENSION: ${d.focus}`, { agentType: d.agentType, schema: FINDINGS_SCHEMA, label: `find:${d.key}`, phase: 'Find' }),
  (findResult, d) => {
    const findings = (findResult && findResult.findings) || []
    if (!findings.length) return []
    return parallel(
      findings.map((f) => () =>
        agent(
          `${PREAMBLE}\n\nADVERSARIAL VERIFICATION (dimension "${d.key}"). REFUTE this finding. Default is_real=false unless you REPRODUCE the evidence.\nFINDING:\n- id: ${f.id}\n- severity claimed: ${f.severity}\n- title: ${f.title}\n- location: ${f.location}\n- claim: ${f.claim}\n- evidence_command: ${f.evidence_command}\n- claimed output: ${f.evidence_output}\n- in_repo_scope claimed: ${f.in_repo_scope}\n- suggested_fix: ${f.suggested_fix}\nSTEPS: (1) re-run evidence_command via Bash; set reproduced. (2) does the claim hold at HEAD or is the line out of context/handled elsewhere? (3) is it a KNOWN DISPOSITION → is_real=false, NOT_A_FINDING. (4) fixable in THIS repo this session → in_repo_scope. (5) re-grade severity honestly. EMIT the verdict via StructuredOutput as your final action.`,
          { agentType: 'general-purpose', schema: VERDICT_SCHEMA, label: `verify:${d.key}:${f.id}`, phase: 'Verify' },
        ).then((v) => ({ dimension: d.key, finding: f, verdict: v })),
      ),
    )
  },
)

const all = results.flat().filter(Boolean)
const confirmed = all.filter((r) => r.verdict && r.verdict.is_real && r.verdict.reproduced && r.verdict.in_repo_scope && r.verdict.correct_severity !== 'NOT_A_FINDING')
const refuted = all.filter((r) => !(r.verdict && r.verdict.is_real && r.verdict.reproduced && r.verdict.in_repo_scope && r.verdict.correct_severity !== 'NOT_A_FINDING'))
const sev = (s) => confirmed.filter((r) => r.verdict.correct_severity === s).length

log(`Round ${round}: ${all.length} raw → ${confirmed.length} confirmed (CRIT ${sev('CRITICAL')}/HIGH ${sev('HIGH')}/MED ${sev('MED')}/LOW ${sev('LOW')}); ${refuted.length} refuted`)

return {
  round, total_raw: all.length, confirmed_count: confirmed.length,
  counts: { CRITICAL: sev('CRITICAL'), HIGH: sev('HIGH'), MED: sev('MED'), LOW: sev('LOW') },
  confirmed: confirmed.map((r) => ({ dimension: r.dimension, id: r.finding.id, severity: r.verdict.correct_severity, title: r.finding.title, location: r.finding.location, claim: r.finding.claim, evidence_command: r.finding.evidence_command, suggested_fix: r.finding.suggested_fix, refutation_notes: r.verdict.refutation_notes })),
  refuted: refuted.map((r) => ({ dimension: r.dimension, id: r.finding.id, claimed_severity: r.finding.severity, title: r.finding.title, reason: r.verdict ? r.verdict.refutation_notes : 'no verdict' })),
}
