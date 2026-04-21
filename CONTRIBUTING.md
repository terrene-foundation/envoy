# Contributing to Envoy

Thank you for considering a contribution to Envoy. Envoy is stewarded by the [Terrene Foundation](https://terrene.foundation) and licensed under Apache 2.0 (code) and CC BY 4.0 (methodology and specifications).

## Project Status

Envoy is in Phase 00 (alignment). See [`ROADMAP.md`](ROADMAP.md) for phase gates and [`CHARTER.md`](CHARTER.md) for the product thesis. During Phase 00, external contributions are welcome for:

- Documentation clarifications and typo fixes
- Research and citations for Phase 00 verification items
- Envelope template proposals for the Foundation-Verified tier (see [`DECISIONS.md`](DECISIONS.md) §ADR-0004)
- Feedback on the public-facing concept documents

Phase 01 opens contributions to the Python MVP itself.

## Code of Conduct

All contributors are expected to follow the [Terrene Foundation Code of Conduct](https://terrene.foundation) in all Envoy community spaces (issues, pull requests, discussions, chat channels, and events).

**In short:** focus on the work, not the person. Technical disagreements are healthy; personal attacks are not. Engage with differing opinions constructively. Assume good faith. Other projects are referenced only as neutral context or as interoperability anchors — never as targets.

## Getting Started

1. Fork the repository on GitHub.
2. Clone your fork locally.
3. Create a branch for your change:
   ```bash
   git checkout -b feat/your-change
   ```
4. Make your change with clear commits.
5. Open a pull request.

## Contribution Guidelines

### Voice and Tone

Public-facing documents (README, CHARTER, DECISIONS, ROADMAP, website copy, release notes) MUST:

- Describe Envoy in positive, factual terms.
- Name other projects only as neutral context (e.g. the `SKILL.md` format for compatibility).
- Avoid comparative or adversarial framing of any third-party project.

Internal research and working notes belong in non-public workspaces, not in the repo.

### Quality Standards

- Prose should be clear and structured. Prefer short paragraphs and concrete examples.
- Technical claims must be verifiable. Cite the specification, test, or external source.
- Avoid unverified statistics, CVE numbers, or adoption figures about third-party projects.

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(envelope): add @terrene/freelancer-v1 reference envelope
docs(charter): clarify runtime-picker wording
fix(roadmap): correct Phase 02 channel count
```

### License

By contributing, you agree that your contributions are licensed under Apache 2.0 (code) or CC BY 4.0 (content), matching the rest of the project. The Foundation reserves the right to relicense Foundation-owned artifacts within the CC BY 4.0 / Apache 2.0 family as necessary.

## Pull Request Process

1. Ensure your change is scoped and focused on one concern.
2. Update related documentation if behaviour or interfaces change.
3. Request review from maintainers.
4. Squash or rebase to a clean commit history before merge.

## Questions

Open an issue on GitHub or contact [info@terrene.foundation](mailto:info@terrene.foundation).
