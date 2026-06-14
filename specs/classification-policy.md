# classification-policy

## Purpose

PACT classification clearance enum + `@classify` decorator + `apply_read_classification()` + `format_record_id_for_event()` integration.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 §3.4 + 09-threat-model.md v3 T-005`.
- **Threats mitigated:** T-005 semantic envelope bypass, T-012 feedback-loop poisoning (record_id hashing).
- **BETs tested:** BET-2 semantic check substrate.

## Classification enum (canonical per PACT)

`Public | Internal | Confidential | Restricted | HighlyConfidential`.

No synonyms, no reorderings. Any spec or binding that introduces `PII`, `SECRET`, `PRIVATE`, `CONFIDENTIAL_PII`, or other off-enum labels is BLOCKED per `rules/terrene-naming.md` §Canonical terminology.

## `@classify` decorator (kailash-py; kailash-rs uses attribute-based)

Field-level classification marking at model definition time. The decorator argument MUST be a canonical enum member:

```python
from kailash.classification import Classification

@classify(email=Classification.Confidential)
class User:
    email: str
    ssn: str  # unmarked → defaults to Classification.Internal (application-policy default)
```

kailash-rs equivalent: `#[classify(email = Classification::Confidential)]` attribute on struct fields.

**Common mapping (informal name → canonical enum):** "PII" → `Confidential` or `Restricted` depending on data (email → Confidential; SSN / payment data → Restricted). The decorator never accepts informal labels; apps that want a shorter name define their own const (e.g. `PII = Classification.Confidential`) at app level, never at SDK level.

## MaskingStrategy

Redaction policy applied when `caller_clearance < field_classification`:

| Strategy   | Behavior                                                         | Use case                                    |
| ---------- | ---------------------------------------------------------------- | ------------------------------------------- |
| `Redact`   | Replace value with `"[REDACTED]"` sentinel.                      | Default; maximum safety.                    |
| `LastFour` | Show last 4 characters; prefix with `"***"`.                     | Payment identifiers, phone numbers.         |
| `Hash`     | Replace with `f"sha256:{sha256(value)[:8]}"` stable fingerprint. | Forensic correlation without reversibility. |
| `NullOut`  | Replace with `None` / `null`.                                    | Caller-side code treats field as absent.    |

MaskingStrategy is declared at field level in the `@classify` decorator: `@classify(email=(Classification.Confidential, MaskingStrategy.Hash))`. Default on unspecified: `MaskingStrategy.Redact`.

## `apply_read_classification(value, field_classification, masking_strategy, caller_clearance)`

Returns masked value based on policy:

- `caller_clearance ≥ field_classification` → return plain.
- `caller_clearance < field_classification` → apply `MaskingStrategy`.

Binding availability: the pure-Python `kailash-py` package exposes
`apply_read_classification` as an internal API (public exposure tracked
kailash-py#601). The Rust-backed `kailash` binding this project consumes does NOT
expose it — there is no `kailash.dataflow` / `apply_read_classification` /
`MaskingStrategy` / `Classification`-enum surface in the installed binding
(verified by live import + package grep); the binding exposure is tracked
kailash-rs#514 and has not shipped. Envoy's consumer code therefore cannot call
the masking surface yet; it lands with the classifier/masking shard (S6c). The
PACT clearance/envelope surface that IS present in the binding
(`kailash.trust.pact`: `effective_clearance`, `can_access`,
`compute_effective_envelope`, `intersect_envelopes`, `ClearanceSpec`) backs the
structural envelope-check engine (S6a — `envoy.runtime.envelope_check`); the
field-level read-masking half is the S6c deferral recorded under § Out of scope.

## `format_record_id_for_event(policy, model_name, record_id, pk_field)`

Hashes classified-PK values before emission:

- Input types: None → None; integer/float → str; unclassified string → str; classified string → `f"sha256:{sha256(value)[:8]}"`.

kailash-py ✅ at `packages/kailash-dataflow/src/dataflow/classification/event_payload.py`.
kailash-rs: 2026-04-19 fix per `rules/event-payload-classification.md`; cross-SDK prefix stable.

## Envelope integration

Data Access dimension references classification per-model via `field_allowlist_per_model` + `semantic_rules` with classifier ensemble per classification type.

## Semantic classifier ensemble defense (T-005)

Minimum 2 classifiers per semantic check. Weighted vote. Disagreement fails CLOSED. Classifier-version tracked in Ledger for retrospective flagging.

## Error taxonomy

| Error                                 | Trigger                                                                                             | User action                                                                               | Retry                          |
| ------------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------ |
| `OffEnumClassificationError`          | `@classify` decorator argument is not in canonical 5-enum (e.g. `PII`, `SECRET`, `PRIVATE`)         | Replace with canonical enum member (`Confidential` / `Restricted`); fix at app code       | Never (terrene-naming.md gate) |
| `ClearanceComparisonError`            | Caller's clearance unset or absent in thread/async-local context                                    | Set clearance via fail-closed default (`Public`); investigate missing context propagation | Auto after context wired       |
| `MaskingStrategyUnsupportedError`     | MaskingStrategy not implemented for field's type (e.g. `LastFour` on int)                           | Choose compatible strategy; or app converts type before classification                    | Never                          |
| `ClassifierEnsembleDisagreementError` | Semantic check ensemble vote split (no quorum) for "block" / "block+grant_moment"                   | Fail-closed per envelope-model.md unavailability_policy                                   | Manual after envelope edit     |
| `ClassifierVersionMismatchError`      | Ledger-recorded classifier version differs from currently loaded classifier on retrospective replay | Halt replay; investigate registry update; pin to recorded version                         | Never (audit integrity)        |
| `RecordIdHashMismatchError`           | `format_record_id_for_event` cross-SDK prefix mismatch (BET-2 violation)                            | Halt event emission; investigate kailash-py vs kailash-rs hash divergence                 | Never (BET-2 defense)          |

## Cross-references

- specs/envelope-model.md — Data Access dimension semantic rules.
- specs/ledger.md — `content` fields of Ledger entries subject to read-time `apply_read_classification`; classified-PK values emitted in entries are routed through `format_record_id_for_event` per `rules/event-payload-classification.md`.
- specs/monthly-trust-report.md — redaction for public sharing.
- specs/tool-output-sanitization.md — classification is an input to cross-domain rule matching.
- specs/cross-domain-flows.md — classification-aware flow rejection.
- specs/data-model.md — model field-level classification at schema definition.
- specs/threat-model.md — T-005, T-012.

## Test location

Phase 01 ships the `format_record_id_for_event` classified-PK hashing primitive plus the Ledger-emitter classified-redaction routing (no-policy passthrough). Both are tested in-repo:

- `tests/tier1/test_format_record_id_for_event.py` — `format_record_id_for_event` input-type handling (None / int / str / classified-string) + cross-SDK sha256-8hex prefix parity (T-01-17; the T-012 record-id-hash byte-identity half).
- `tests/tier2/test_ledger_emitter_classified_redaction.py` — classified-PK values routed through the redactor before Ledger emission; Phase 01 no-policy passthrough (`test_phase01_no_policy_passes_value_through`).

## Out of scope (this phase)

The full PACT `ClassificationPolicy` enforcement surface lands with the T-01-21 Tier-2 wiring (Phase 02), when a real `ClassificationPolicy` from kailash-dataflow is wired into the ledger emitter (per the deferral note at `envoy/ledger/facade.py`). The following test surfaces land with it and are NOT present in Phase 01:

- `@classify` decorator canonical-only acceptance (5-enum ordering; reject `PII` / `SECRET`) + `apply_read_classification` clearance comparison + MaskingStrategy round-trip (Redact / LastFour / Hash / NullOut).
- T-005 semantic classifier-ensemble disagreement fail-closed.
- Ledger-recorded classifier-version pinning at retrospective replay.
- Full-matrix threat-coverage gate for T-005 / T-012 (per specs/threat-model.md §Test location; the cross-phase threat-coverage meta-gate is the Phase-02 deferral recorded in `workspaces/phase-01-mvp/journal/0053`).

## Open questions

1. Which `@classify` informal-name to canonical-enum mappings should Foundation publish as default (PII → Confidential, SSN → Restricted, etc.)?
2. MaskingStrategy default selection — should `LastFour` be auto-applied for short-numeric-string fields, or always opt-in?
3. Cross-domain promotion semantics — when does `Confidential` data become `Restricted` after combination with other fields (composition).
4. Classifier-version retention — how long to keep classifier weights for retrospective re-replay (compliance window vs storage cost).
5. Per-tenant classification overrides — does a Shared Household member's `Confidential` clearance vary per scope (personal vs household).
