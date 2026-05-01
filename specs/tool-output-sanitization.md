# tool-output-sanitization

## Purpose

Owning spec for `tool_output_sanitize(output, tool_name, envelope)` — the runtime boundary that screens tool return values BEFORE they re-enter the LLM's reasoning context. Consumer of `envoy-registry:prompt-injection-patterns:v1` (specs/foundation-ops.md §Infrastructure inventory #11). Structural defense against prompt injection attacks at the tool-return surface.

## Provenance

- **Source analysis:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 §3.4.3 + §14.10` + `05-runtime-abstraction.md v2 §3 tool_output_sanitize` + `09-threat-model.md v3 T-010/T-011 prompt injection`.
- **Threats mitigated:** T-010 direct prompt injection via tool output, T-011 indirect prompt injection via fetched content, T-013 composition-aware feedback loops through tool output.
- **BETs tested:** BET-2 structural/semantic partition, BET-6 byte-identical sanitization contract.

## Surface

Invoked by runtime after every tool call, BEFORE the tool's output bytes are presented to the LLM's reasoning loop. Called at the same code point where specs/ledger.md §Two-phase signing §Phase B records the outcome.

```python
def tool_output_sanitize(
    output: bytes | str | dict,
    tool_name: str,
    envelope: EnvelopeConfig,
) -> SanitizeResult:
    ...
```

Classifier ensemble is resolved from `envelope.semantic_checks.tool_output_classifier_ensemble` per specs/envelope-model.md §Schema; the runtime ABC method (specs/runtime-abstraction.md §Prompt + tool-output) takes the same 3-parameter signature.

Runtime invocation is NOT optional — a runtime that skips this step fails BET-6 contract-parity and cannot pass specs/runtime-abstraction.md §Phase 02 E3 conformance.

## Algorithm

```python
def tool_output_sanitize(output, tool_name, envelope):
    classifier_ensemble = envelope.semantic_checks.tool_output_classifier_ensemble
    # 1. Canonicalize output to UTF-8 bytes with NFC normalization.
    if isinstance(output, dict):
        canonical_bytes = jcs_canonicalize(output).encode("utf-8")
    elif isinstance(output, str):
        canonical_bytes = unicodedata.normalize("NFC", output).encode("utf-8")
    else:
        canonical_bytes = output

    # 2. Size budget check — per envelope.tool_output_budget_bytes;
    #    oversized outputs truncate with explicit marker before downstream feed (T-094 defense).
    if len(canonical_bytes) > envelope.tool_output_budget_bytes:
        canonical_bytes = canonical_bytes[:envelope.tool_output_budget_bytes] + b"\n<<TRUNCATED>>"

    # 3. Structural patterns (fast path, <5ms) — regex against known
    #    prompt-injection syntactic shapes (Ignore previous instructions / System: / [[INSTRUCTION]] / etc.).
    structural_hits = apply_structural_patterns(canonical_bytes, STRUCTURAL_PROMPT_INJECTION_PATTERNS)

    # 4. Semantic classifier ensemble (slow path, <500ms uncached, <50ms cached).
    #    Consume envoy-registry:prompt-injection-patterns:v1 per specs/foundation-ops.md.
    ensemble_verdict = classifier_ensemble.aggregate(
        classifiers=envelope.semantic_checks.tool_output_classifier_ensemble,
        content=canonical_bytes,
        content_type="tool_output",
        cache_key=(sha256(canonical_bytes).hex(), tool_name, envelope.envelope_version),
    )

    # 5. Cross-domain flow check — consume envoy-registry:cross-domain-flows:v1
    #    (specs/cross-domain-flows.md) to reject secret-in-plaintext leaks
    #    from tool output onto public surfaces.
    cross_domain_check = evaluate_cross_domain_rules(
        output_bytes=canonical_bytes, tool_name=tool_name,
        envelope=envelope,
        registry_version=envelope.metadata.algorithm_identifier.cross_domain_rules,
    )

    # 6. Combine verdicts fail-closed (specs/envelope-model.md §unavailability_policy).
    if structural_hits or ensemble_verdict.blocks or cross_domain_check.blocks:
        return SanitizeResult(
            verdict="blocked",
            reason=summarize_for_user(structural_hits, ensemble_verdict, cross_domain_check),
            reason_content_hash=sha256(b"|".join(...)).hexdigest(),
        )

    if ensemble_verdict.flags or cross_domain_check.flags:
        return SanitizeResult(
            verdict="flag_and_allow",
            annotated_output=annotate_output(canonical_bytes, flags),
            reason=...,
        )

    return SanitizeResult(verdict="allow", output=canonical_bytes)
```

## Structural pattern corpus

Foundation-curated, versioned registry `envoy-registry:structural-prompt-injection:v1` (specs/foundation-ops.md §Infrastructure inventory #15). Minimum patterns at Phase 01:

- "Ignore previous instructions" + translations + 20 variants.
- Fake system-role markers (`<|system|>`, `[SYSTEM]`, `[[INST]]`, `<!DOCTYPE`, `{{`).
- Base64/hex-encoded instruction prefixes (detect entropy + leading-marker).
- Delimiter forgery (triple-backtick transitions attempting role-impersonation).
- Homoglyph variants (Cyrillic `о` for Latin `o` in "Override" etc.) — NFC normalization reduces surface but explicit allow-list exceptions.

50 structural vectors in Phase 01 corpus; target <5ms aggregate evaluation.

## Semantic classifier ensemble

Consumes `envoy-registry:prompt-injection-patterns:v1` (specs/foundation-ops.md). Minimum 2 classifiers per semantic check (specs/envelope-model.md §Semantic classifier ensemble). Disagreement fails CLOSED.

Cache key: `(content_hash, tool_name, envelope_version, classifier_version)`. Cache hit rate target: 70% in typical session (same tool output re-read across reasoning iterations).

## Fail-closed policy

Per specs/envelope-model.md §Semantic classifier ensemble §unavailability_policy:

- **Phase 01 default**: fail-closed.
- **Phase 04 FV tier**: fail-open FORBIDDEN.
- On classifier unavailability (network, timeout), the sanitizer raises `ClassifierUnavailableError` which the caller handles per envelope policy.

## Ledger record

Every non-allow verdict produces a Ledger entry:

```json
{
  "type": "tool_output_sanitization_event",
  "schema_version": "tool-output-sanitize/1.0",
  "verdict": "blocked | flag_and_allow",
  "tool_name": "<str>",
  "output_content_hash": "sha256:...",
  "reason_content_hash": "sha256:...",
  "reason_content_trust_level": "system",
  "classifier_ensemble_used": ["<ref>:<version>", ...],
  "envelope_version_at_invocation": <int>,
  "signed_by": "runtime_device_key",
  "signature_hex": "ed25519"
}
```

Registered in specs/ledger.md §Entry types.

## Error taxonomy

| Error                           | Trigger                                                           | User action                                                               |
| ------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `ToolOutputBlockedError`        | verdict=blocked at structural or semantic layer.                  | Review the tool output in Grant Moment; approve+author if false positive. |
| `ToolOutputFlaggedError`        | verdict=flag_and_allow; output enters LLM with annotations.       | None; informational; check Daily Digest for patterns.                     |
| `ClassifierUnavailableError`    | Classifier ensemble fails to reach quorum; unavailability policy. | If fail-closed: run ceremony; if fail-flag: proceed with annotation.      |
| `ToolOutputBudgetExceededError` | Output > envelope.tool_output_budget_bytes.                       | Inform user; output truncated with marker.                                |
| `CrossDomainFlowRejectedError`  | specs/cross-domain-flows.md rule fired.                           | User reviews; per-rule override via envelope edit.                        |

## Cross-references

- **specs/runtime-abstraction.md** — `tool_output_sanitize` abstract method.
- **specs/envelope-model.md** — `semantic_checks.tool_output_classifier_ensemble`, `tool_output_budget_bytes`, `latency_budget_ms`.
- **specs/foundation-ops.md** — `envoy-registry:prompt-injection-patterns:v1`, `envoy-registry:structural-prompt-injection:v1`.
- **specs/cross-domain-flows.md** — cross-domain rule engine consumer.
- **specs/ledger.md** — `tool_output_sanitization_event` entry type.
- **specs/classification-policy.md** — sanitized output still subject to classification redaction if it contains classified fields.
- **specs/grant-moment.md** — surfaces on `ToolOutputBlockedError`.
- **specs/threat-model.md** — T-010, T-011, T-013.

## Test location

`tests/integration/test_tool_output_sanitization.py` (Phase 01):

- 50 structural vectors — all blocked.
- Semantic ensemble on 20 adversarial corpus samples; 100% block rate.
- Fail-closed on classifier unavailability.
- Byte-identical sanitization verdict across runtimes (BET-6 conformance E8).
- Cross-domain flow rule firing.
- Ledger entry emission on every non-allow verdict.

Threat tests T-010/T-011/T-013 live here, per specs/threat-model.md §Test location.

## Open questions

1. Structural pattern corpus growth rate — quarterly update cadence TBD.
2. Cache eviction policy — LRU vs LFU under memory pressure.
3. Ensemble unavailability → UX ceremony — fail-closed adds latency; Phase 03 user research on tolerance.
4. Annotation format for `flag_and_allow` — in-band comment vs out-of-band metadata channel.
