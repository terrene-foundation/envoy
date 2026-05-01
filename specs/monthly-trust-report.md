# monthly-trust-report

## Purpose

Month-end PDF + JSON export; shareable delegation graph + budget + posture trajectory.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/01-ux-rituals.md v2 §7`.
- **Threats mitigated:** T-054 covert channel via sharing → redaction per classification-policy.
- **BETs tested:** BET-8 habit, BET-4 credibility.

## Phase 03 deliverable.

## Content

- Full delegation graph (Sankey).
- Budget history (line chart).
- Actions/refusals/escalations.
- Envelope violation attempts.
- Posture trajectory.
- Skill inventory + provenance + force_install flags.
- Classifier-version history.
- Cryptographic receipt hash.

## Delivery

- Archived in `~/envoy/reports/YYYY-MM.{pdf,json}`.
- Signed by user's Genesis key.
- Shareable via `envoy report YYYY-MM share --section X --public` — publicly-shared sections route classified identifiers through `format_record_id_for_event` (sha256-8hex prefix) per classification-policy.

## Error taxonomy

| Error                                | Trigger                                                                                           | User action                                                                               | Retry                  |
| ------------------------------------ | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ---------------------- |
| `ReceiptHashMismatchError`           | Recomputed `receipt_hash` over rendered PDF/JSON bytes does not match signed receipt              | Refuse delivery; surface as integrity event; investigate source-data tamper or render bug | Never (security event) |
| `RedactionFailedOnShareError`        | Share path detected classified identifier that did not route through `format_record_id_for_event` | Refuse share; user runs `envoy report YYYY-MM share --section X --public` again after fix | Manual after redaction |
| `MonthlyReportGenerationFailedError` | Source data (Ledger, posture trajectory, classifier history) unavailable or corrupted             | Surface "report unavailable for YYYY-MM"; investigate Ledger health                       | Auto next month        |
| `SectionRedactionPolicyMissingError` | User attempted `--public` share on a section without classification-policy redaction rule         | Refuse share; user requests policy update OR redacts manually before share                | Manual after policy    |
| `MonthBoundaryStraddleError`         | Report-window straddles a Ledger merge boundary; entries pre/post merge use different schemas     | Re-emit per-month-boundary; user receives split report with explicit boundary marker      | Auto next month        |
| `ShareLinkExpiredWarning` (advisory) | Shared link past Foundation-default retention                                                     | UX prompts re-share; not a hard block                                                     | Manual                 |
| `GenesisSignatureMissingError`       | Final report not signed by user's Genesis key (key unavailable or destroyed)                      | Surface as Trust-Vault-unavailable; user runs Shamir recovery before retry                | Manual after recovery  |

## Cross-references

- specs/ledger.md — data source.
- specs/classification-policy.md — redaction rules for shared sections.
- specs/trust-lineage.md — delegation graph.
- specs/channel-adapters.md — `send_monthly_report` adapter contract.
- specs/threat-model.md — T-054.

## Test location

- `tests/integration/test_monthly_report_generation.py` — month-end PDF + JSON archive at `~/envoy/reports/YYYY-MM.{pdf,json}` (Tier 2).
- `tests/integration/test_monthly_report_receipt_hash_roundtrip.py` — signed receipt_hash recomputed from rendered bytes.
- `tests/regression/test_t054_classified_section_public_share_redaction.py` — T-054 defense; classified identifiers route through `format_record_id_for_event` on `--public` share.
- `tests/integration/test_monthly_report_share_section_filter.py` — `envoy report share --section X` includes only requested section.
- `tests/integration/test_genesis_signature_required.py` — report unsigned without Genesis key access.
- `tests/integration/test_month_boundary_split_report.py` — split report when merge boundary inside window.
- `tests/e2e/test_monthly_report_delivery_via_send_monthly_report.py` — end-to-end delivery through channel adapter (Tier 3).

## Open questions

1. PDF vs JSON parity — what bytes are signed by Genesis (PDF only? JSON canonical? both with separate hashes).
2. Public-share retention — Foundation-hosted preview link TTL; cross-spec coordination with foundation-ops.md.
3. Sankey delegation-graph rendering for users with 1000+ delegations — pagination vs sub-graph view.
4. Classifier-version history granularity — per-action vs per-day rollup.
5. Cross-tenant household reports — Phase 03 multi-principal report aggregation: opt-in vs default.
