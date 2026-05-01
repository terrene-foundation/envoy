# cross-domain-flows

## Purpose

Owning spec for `envoy-registry:cross-domain-flows:v1` — the rule engine that evaluates whether a tool action (read / transmit / write) crosses a classification or domain boundary the user has declared off-limits. Consumed by specs/tool-output-sanitization.md + specs/envelope-model.md §Data Access + §Communication dimensions.

## Provenance

- **Source analysis:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 §3.4.4 + §3.5 composition rules` + `06-distribution.md v1 §Registry` + `09-threat-model.md v3 T-005/T-012/T-070`.
- **Threats mitigated:** T-005 semantic envelope bypass via cross-domain write, T-012 feedback-loop poisoning across domains, T-070 side-channel leak across channel-adapter.
- **BETs tested:** BET-2 structural/semantic partition, BET-12 governance-primary-surface (Data Access + Communication dimensions).

## Concept

A "flow" is any tuple `(source_domain, sink_domain, content_classification)` where content classified under source_domain lands in sink_domain. The rule engine evaluates whether the envelope permits this tuple.

Examples:

- Reading `email@work-domain` credentials, then transmitting to `work-domain` recipient → allowed.
- Reading `email@work-domain` credentials, then transmitting to `personal-domain` recipient → `CrossDomainFlowRejectedError`.
- Reading `classification=Confidential` document, then posting to `channel=public-slack` → rejected.
- Reading `user_journal_entry`, then using as plaintext in `github_issue` tool → rejected.

## Rule grammar (total-bounded, per specs/envelope-model.md §Composition-rule DSL)

```json
{
  "rule_id": "<str>",
  "order": <int>,
  "schema_version": "cross-domain-rule/1.0",
  "source": {
    "domain_match_ast": {
      "op": "eq | matches | in_set | is_classified",
      "value": "<domain_pattern> | <classification_level> | [<domain>,<domain>]"
    }
  },
  "sink": {
    "domain_match_ast": {"op": "...", "value": "..."}
  },
  "action": "block | block+grant_moment | flag+allow",
  "rationale": "<str>",
  "rationale_content_hash": "sha256:..."
}
```

Rule AST follows specs/envelope-model.md §Composition-rule DSL bounds (depth ≤ 5, And/Or ≤ 10, In set ≤ 1000). Per-rule evaluation budget: 5ms fail-closed.

## Foundation-curated default rules

`envoy-registry:cross-domain-flows:v1` (specs/foundation-ops.md §Infrastructure inventory #10) ships with the default rule set at Phase 01:

| Rule ID                                   | Intent                                                                               | Action             |
| ----------------------------------------- | ------------------------------------------------------------------------------------ | ------------------ |
| `no-confidential-to-public-channel`       | `classification ≥ Confidential` content to `channel ∈ public-social`.                | block              |
| `no-credentials-outside-origin-domain`    | `connection_vault_entry` origin domain ≠ recipient domain.                           | block              |
| `no-work-to-personal`                     | `domain=work` content to `domain=personal` recipient.                                | block+grant_moment |
| `no-journal-to-external`                  | `user_journal` content to external tool/recipient.                                   | block              |
| `flag-password-plaintext-anywhere`        | Password-shaped string in any outbound surface.                                      | flag+allow         |
| `no-restricted-to-model-provider-default` | `classification=Restricted` content to LLM provider endpoint unless policy override. | block+grant_moment |

Users author additional rules via boundary-conversation + weekly-posture-review ritual surfaces.

## Algorithm

```python
def evaluate_cross_domain_rules(output_bytes, tool_name, envelope, registry_version):
    rules = load_rules(
        envelope.cross_domain_rules_authored + foundation_defaults(registry_version)
    )
    rules.sort(key=lambda r: r.order)

    source = infer_source_domain(output_bytes, tool_name, envelope)
    sink = infer_sink_domain(tool_name, envelope)
    classification = classify(output_bytes, envelope)

    verdicts = []
    total_budget_ms = 10  # total budget across all rules, fail-closed
    for rule in rules:
        t0 = now_ms()
        if match_ast(rule.source.domain_match_ast, source, classification) and \
           match_ast(rule.sink.domain_match_ast, sink, classification):
            verdicts.append(RuleVerdict(
                rule_id=rule.rule_id, action=rule.action, rationale=rule.rationale,
            ))
        elapsed = now_ms() - t0
        total_budget_ms -= elapsed
        if total_budget_ms <= 0:
            raise ComposedRuleTotalBudgetExceededError(...)

    return aggregate_verdicts(verdicts)  # worst-case wins
```

**`aggregate_verdicts`**: block wins over block+grant_moment wins over flag+allow wins over no-rule-matched.

## Source/sink inference

- **Source domain** — from ConnectionVault entry's `service_identifier` domain, from Ledger-recorded document provenance, or from tool-output's declared content origin.
- **Sink domain** — from tool-name (e.g., `send_email(to=x@y.com)` → `domain=y.com`), from channel-adapter destination, or from recipient URL.
- **Classification** — from specs/classification-policy.md `apply_read_classification` result; most-restrictive classification across any field in the output.

Where inference is ambiguous, the engine falls back to `UNKNOWN` and the default rule set has a safety-default `block` for `UNKNOWN → Restricted`.

## User-authored rule onboarding

Onboarded via:

1. **Boundary Conversation** — specs/boundary-conversation.md prompts "Should Envoy ever mix work and personal domains?" and authored rules are added.
2. **Grant Moment approve+author** — when a flow is blocked and the user chooses "approve and add exception", the exception rule is recorded as an authored rule (counts toward Authorship Score per specs/authorship-score.md).
3. **Weekly Posture Review** — specs/weekly-posture-review.md surfaces patterns and lets the user codify new rules.

All authored rules are Ledger-recorded `envelope_edit` entries with `composition_rules` appended.

## Error taxonomy

| Error                                    | Trigger                                                               | User action                                               |
| ---------------------------------------- | --------------------------------------------------------------------- | --------------------------------------------------------- |
| `CrossDomainFlowRejectedError`           | Rule `action=block` matched.                                          | Grant Moment approve+author to add exception; or abandon. |
| `CrossDomainFlowGrantRequiredError`      | Rule `action=block+grant_moment` matched.                             | Approve via Grant Moment; records one-time exception.     |
| `CrossDomainFlowBudgetExceededError`     | Total rule evaluation > 10ms.                                         | Retry after rule-set cleanup; Phase 03 auto-prune.        |
| `CrossDomainFlowInferenceAmbiguousError` | Source or sink cannot be inferred; default block on Restricted fires. | User clarifies via Grant Moment; record chosen domain.    |
| `CrossDomainRegistryMissError`           | Rule references classifier not in current registry version.           | Upgrade registry or retire rule.                          |

## Cross-references

- **specs/envelope-model.md** — cross-domain rules are part of `composition_rules` + per-dimension `semantic_rules`.
- **specs/tool-output-sanitization.md** — primary consumer at tool-return surface.
- **specs/classification-policy.md** — classification-level inputs to rule matching.
- **specs/foundation-ops.md** — `envoy-registry:cross-domain-flows:v1` + user-authored extensions.
- **specs/connection-vault.md** — source-domain inference via credential entry origin.
- **specs/ledger.md** — authored rules recorded as `envelope_edit`; rule matches + verdicts recorded as `tool_output_sanitization_event` (specs/tool-output-sanitization.md).
- **specs/boundary-conversation.md** — rule-authoring UX.
- **specs/grant-moment.md** — approve+author flow.
- **specs/authorship-score.md** — authored cross-domain rules count toward score.
- **specs/threat-model.md** — T-005, T-012, T-070.

## Test location

`tests/integration/test_cross_domain_flows.py` (Phase 01):

- 6 default rules enforce their declared intents.
- Rule composition (block+grant_moment wins over flag+allow aggregation).
- Budget-exceeded error on synthetic large rule set.
- Source/sink inference on ambiguous tool output → safety-default block on Restricted.
- Authored-rule round-trip (envelope edit + rule reload).
- BET-6 byte-identical verdict across runtimes on 20-vector corpus.

Threat tests T-005/T-012/T-070 live here, per specs/threat-model.md §Test location.

## Open questions

1. Default rule set expansion — Phase 03 user research for common everyday-user domains.
2. Inference confidence score — current: binary match/no-match; Phase 04 may quantify.
3. Total rule budget when rule set grows — Phase 03 empirical; current cap 10ms may need raising with LRU early-match cache.
4. Per-tool rule overrides — current: all rules apply to all tools; Phase 04 may add tool-scoped rules.
