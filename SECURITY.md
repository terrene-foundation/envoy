# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Envoy, please report it responsibly through coordinated disclosure.

**Email:** [security@terrene.foundation](mailto:security@terrene.foundation)

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
- Your preferred credit attribution (or request for anonymity)

### Response timeline

- **Acknowledgment:** within 48 hours of report.
- **Initial assessment:** within 5 business days.
- **Resolution target:** within 30 days for critical issues.

## Scope

Security reports for Envoy include, but are not limited to:

- Flaws in the envelope compiler or runtime enforcement (PACT constraint bypass).
- Delegation or trust-lineage integrity issues (EATP).
- Envoy Ledger integrity (hash-chain verification, tamper detection).
- Shamir Trust Vault recovery (SLIP-0039 integration correctness).
- Grant Moment flow (capability escalation, unsigned actions, replay).
- Prompt-injection defenses in the Boundary Conversation and channel adapters.
- Supply-chain concerns in Envoy's dependency tree (including the runtime bindings).
- Skill validator bypass (CO-compliance validator in `SKILL.md` ingest).

Out of scope for this policy:

- Issues in third-party runtimes Envoy can target (report to those projects directly).
- User-authored envelopes that are overly permissive by design (a policy choice, not a vulnerability).

## Disclosure

Envoy follows coordinated disclosure. Please do not publicly disclose a vulnerability until the Foundation has issued a fix and provided reasonable time for users to update. The Foundation will credit reporters in the advisory unless anonymity is requested.

## Supported Versions

During the Phase 00 / Phase 01 pre-release period, only the latest `main` is supported with security updates. A formal support matrix will be published at the Phase 01 MVP release.

## Security-Relevant Documents

- [`CHARTER.md`](CHARTER.md) — product security posture (governance, audit, cascade revocation)
- [`DECISIONS.md`](DECISIONS.md) §ADR-0003 — Shamir Trust Vault
- [`DECISIONS.md`](DECISIONS.md) §ADR-0009 — licensing and export-control posture
