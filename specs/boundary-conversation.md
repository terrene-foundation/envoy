# boundary-conversation

## Purpose

First-run onboarding dialogue that compiles EnvelopeConfig.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/01-ux-rituals.md v2 §3`.
- **Threats mitigated:** T-018 visible secret setup, T-023 Authorship Score seeding.
- **BETs tested:** BET-1 authorship, BET-12 palatability.

## State machine

S0 greet → S1 money → S2 people → S3 topics → S4 hours → S5 first task → S6 template offer → S7 visible secret setup → S8 Shamir ritual → S9 review & sign → S10 complete.

## Questions

S1: monthly ceiling USD.
S2: blocked contacts.
S3: blocked topics (semantic rules).
S4: operating hours.
S5: first-task intent.
S6: template import (Foundation-Verified only in Phase 01 local cache) OR from-scratch.
S7: visible secret (icon + color + phrase).
S8: Shamir 3-of-5 default; 5-in-safes alternative; custom.
S9: plain-language envelope summary + sign.

## Duration

~15min target. 8min minimum-path (template + visible secret + Shamir).

## Persistence + resume

Every answer transition persists state to Trust Vault. `envoy init --resume <ritual_id>` rehydrates.

## Novelty feedback (T-023)

If user-authored answer compiles to near-duplicate (Jaccard > 0.85 or adversarial-wording classifier > 0.8) of template constraint, UX prompts user to rephrase or re-choose.

## Post-duress review step (§3.5a — V2 C-02 fix)

After first-run real unlock, if shadow segment contains unread duress event, a banner surfaces above Boundary Conversation with visible-secret-bound Modal detailing duress time + recommended immediate actions.

## Error taxonomy

| Error                             | Trigger                                                                                       | User action                                                     | Retry                  |
| --------------------------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ---------------------- |
| `RitualResumeStateMissingError`   | `envoy init --resume <ritual_id>` references a ritual_id absent from Trust Vault              | Restart from S0; OR Shamir-recover Trust Vault                  | Manual                 |
| `InvalidStateTransitionError`     | User input does not satisfy state's input-validation rules (e.g. empty monthly ceiling at S1) | Re-prompt at current state; surface plain-language guidance     | Manual                 |
| `TemplateNotInLocalCacheError`    | S6 template offered but Foundation-Verified template not present in Phase 01 local cache      | Skip template; from-scratch path; OR online sync (Phase 02)     | Auto after sync        |
| `ShamirRitualIncompleteError`     | S8 Shamir card distribution incomplete at S9                                                  | Force back to S8; cannot sign envelope without backup           | Manual                 |
| `NoveltyFeedbackBlockError`       | User-authored answer fails novelty (Jaccard ≥ 0.85 or adversarial ≥ 0.8) at S3/S5             | UX prompts rephrase or re-choose template                       | Manual after re-author |
| `VisibleSecretMissingError`       | S7 not completed before sign at S9                                                            | Force back to S7                                                | Manual                 |
| `DuressBannerUnacknowledgedError` | Post-duress review (§3.5a) banner not acknowledged before S0 advance                          | Acknowledge duress event; consult recommended immediate actions | Manual                 |

## Cross-references

- specs/envelope-model.md — EnvelopeConfig compile target.
- specs/authorship-score.md — novelty + minimum-impact algorithms.
- specs/shamir-recovery.md — ritual flow.
- specs/trust-vault.md — visible secret + ritual state storage.
- specs/data-model.md — shadow segment for duress.
- specs/threat-model.md — T-018, T-023.

## Test location

- `tests/tier3/test_boundary_conversation_full_path.py` — S0→S10 happy-path (Tier 3, ~15min budget).
- `tests/tier3/test_boundary_conversation_minimum_path.py` — 8-minute template+visible-secret+Shamir path.
- `tests/tier2/test_resume_from_each_state.py` — `envoy init --resume` from S1..S9 (Tier 2).
- `tests/tier2/test_visible_secret_render_check.py` — visible secret rendered correctly post-S7 (T-018; spoofing-defense counterpart `tests/regression/test_t018_dialog_spoofing_visible_secret.py`).
- `tests/tier2/test_envoy_novelty_checker.py` — duplicate AST surfaces novelty feedback before S9 (T-023).
- `tests/tier2/test_post_duress_banner.py` — §3.5a banner gates state advance.

## Open questions

1. 15min target — empirical Phase 01 telemetry; if median exceeds 22min, simplify.
2. State-resume across machine boundary (laptop ↔ phone) — Phase 02 multi-device pairing concern.
3. S5 first-task corpus diversity — should Foundation curate per-domain examples to seed authorship.
4. Custom Shamir distribution UX (5-in-safes vs custom) — too many options vs too few.
5. Monthly ceiling defaults — should Foundation publish region-anchored defaults to reduce decision fatigue.
