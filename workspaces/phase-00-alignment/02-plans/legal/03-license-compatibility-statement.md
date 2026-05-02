# Apache 2.0 + CC BY 4.0 + MIT — license-compatibility statement

**Status:** DRAFT for legal-counsel review and Foundation board endorsement.
**Owner:** envoy Phase-00 (drafted), Terrene Foundation legal counsel (final), Foundation board (endorses the runtime-pluggability + skill-ingest model that depends on this analysis).
**Source contract:** ROADMAP.md line 30 — "Apache 2.0 code + CC BY 4.0 methodology + ingesting MIT-licensed `SKILL.md`-formatted skills = compatible". This draft establishes the substantive compatibility analysis the Foundation board will rely on when endorsing ADR-0009 (runtime-pluggability) and ADR-0005 (`SKILL.md` ingest).
**Why this draft exists:** Envoy's distribution touches three license families simultaneously — Apache 2.0 on the code, CC BY 4.0 on the specs the code implements, and MIT (or MIT-like) on the third-party `SKILL.md` content the user installs. Without a written compatibility analysis, downstream redistributors (Linux distros, container-image publishers, enterprise procurement teams) and license scanners (FOSSA, Snyk, Sonatype, Black Duck, ClearlyDefined) will gate Envoy in a manual-review queue. This draft is the substantive precondition for clearing those queues.

---

## 1. The three license families

| Family                                  | License                                                       | Applies to                                                                                                                                                                                                  | Type                                                       | Share-alike? | Patent grant?                                   | Attribution preservation?                          |
| --------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | ------------ | ----------------------------------------------- | -------------------------------------------------- |
| **Apache 2.0**                          | Apache License, Version 2.0                                   | Envoy code; `kailash-runtime` interface; `kailash-py` code; `kailash-rs-bindings` Python glue                                                                                                               | Code                                                       | No           | Yes (explicit § 3 grant + § 3 termination)      | Yes (§ 4 NOTICE preservation)                      |
| **CC BY 4.0**                           | Creative Commons Attribution 4.0 Intl.                        | Foundation specs: CARE (philosophy), PACT (governance), EATP (protocol), CO (methodology); spec text and any quoted spec passages                                                                           | Content                                                    | No           | Limited (§ 2(b)(2): no implicit patent grant)   | Yes (§ 3(a): attribution required)                 |
| **MIT (and MIT-equivalent permissive)** | MIT License (Expat) — text used by most `SKILL.md` publishers | Third-party `SKILL.md`-format community skills authored by individuals or organisations outside the Foundation; ingested by Envoy via the `SKILL.md` → CO-compliant `ENVELOPE.md` translator (per ADR-0005) | Code/content (mixed; depends on the skill author's intent) | No           | No (no patent grant; not termination-protected) | Yes (copyright notice + license text preservation) |

The fourth family — `LicenseRef-kailash-rs-bindings-binary-grant` — covers the freely-redistributable compiled binary inside `kailash-rs-bindings`. Its compatibility is addressed separately in `01-kailash-rs-bindings-LICENSE-draft.md` and `02-kailash-rs-bindings-SPDX-draft.md` and is summarised in §6.4 below.

## 2. The three flow directions

```
     ┌─────────────────────────────────────────────────────────────────┐
     │                       Foundation specs                          │
     │      (CC BY 4.0 — CARE / PACT / EATP / CO)                      │
     └────────────────────────────┬────────────────────────────────────┘
                                  │  consumed-by-implementation
                                  ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │                       Envoy code                                │
     │  (Apache 2.0 — Foundation-owned application + runtime interface)│
     │       ▲                                  │                      │
     │       │                                  │                      │
     │       │ ingested-via-translator          │ distributed-to-user  │
     │       │                                  ▼                      │
     │  ┌──────────────────────┐    ┌──────────────────────────┐       │
     │  │ Third-party SKILLS   │    │     End-user device      │       │
     │  │ (MIT or MIT-like)    │    │ (Envoy + ingested skills)│       │
     │  └──────────────────────┘    └──────────────────────────┘       │
     └─────────────────────────────────────────────────────────────────┘
```

Three directions of license interaction:

- **(a) Code consumes spec.** Envoy's Apache 2.0 code implements the CC BY 4.0 spec family. The compatibility question is whether implementing a CC BY 4.0 specification creates a license obligation on the implementation.
- **(b) Code ingests user-supplied content.** Envoy's Apache 2.0 translator parses an MIT-licensed `SKILL.md`, generates a companion `ENVELOPE.md`, and the user's running Envoy executes the skill. The compatibility question is what license obligations propagate to (i) the generated `ENVELOPE.md`, (ii) Envoy's runtime, (iii) the user's redistribution if any.
- **(c) Aggregated distribution downstream.** A package — Envoy + bundled skills + spec references — moves to a downstream redistributor (e.g. a Linux distro, an enterprise container image, a partner reseller). The compatibility question is what aggregated NOTICE / LICENSE artefacts must accompany the package and whether any single license dominates ("higher-licence-wins") under the bundle.

Each is analysed below.

## 3. License-by-license summary

### 3.1 Apache 2.0

- **Type:** Permissive code license. Allows commercial and non-commercial use, modification, redistribution.
- **Distinguishing feature:** Explicit patent grant (§ 3) covering any patents the contributor holds that read on their contribution, with a termination clause (§ 3) — patent litigation against the project terminates the patent grant for the litigant.
- **Notice preservation:** § 4 requires preserving the LICENSE file, NOTICE file, copyright notices, and a list of any modifications. NOTICE is propagated to downstream binaries.
- **No share-alike:** Derivative works may be distributed under any license, including proprietary, provided § 4 is honoured for the Apache-licensed portion.
- **Outbound compatibility:** Apache 2.0 is one-way compatible with GPL 3.0 (Apache code can be relicensed into GPL 3.0 derivative works) and bidirectionally compatible with permissive licenses (MIT, BSD, ISC, MPL 2.0).

### 3.2 CC BY 4.0

- **Type:** Content license — designed for creative works, data, documentation, specifications. NOT designed for source code (the Creative Commons FAQ explicitly recommends Apache or MIT for code).
- **Distinguishing feature:** Worldwide attribution requirement (§ 3(a)): any redistribution of the licensed material must credit the licensor, link to the license, indicate modifications.
- **Patent posture:** § 2(b)(2) — "Patent and trademark rights are not licensed under this Public License." A spec author's patent on the spec is NOT granted to spec implementers. Implementers acquire patent rights only via independent agreement or under their own implementation's patent grant (e.g. the Apache 2.0 patent grant in Envoy's code).
- **No share-alike:** CC BY (without -SA) does not require derivatives to be CC BY-licensed. Implementations may be Apache 2.0, proprietary, or any other license.
- **Implementation freedom:** Specifications are ideas + textual expression. Implementing the IDEAS expressed in a spec is not a derivative work of the SPEC TEXT — it is an independent work that happens to honour the spec's behavioural requirements. (Standard practice: thousands of Apache-licensed implementations of W3C / IETF / IEEE specs.)

### 3.3 MIT (canonical Expat)

- **Type:** Permissive code license; very short (≈170 words). Allows commercial and non-commercial use, modification, redistribution.
- **Distinguishing feature:** No patent grant. The licensor grants only the copyright permissions enumerated. A patent held by the licensor is NOT licensed. (This is the load-bearing risk in skill ingest — see §6.3.)
- **Notice preservation:** "The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software." A redistributor must preserve the original notice.
- **No share-alike:** Derivative works may be distributed under any license.
- **MIT-like-but-not-MIT variants:** Many `SKILL.md` repos use "MIT" as a label but ship an MIT-derived text with extra restrictions ("non-endorsement", "field-of-use limitation", non-commercial clause). These are NOT MIT and create case-by-case compatibility analysis. Envoy's skill-license validator (see §6.3) MUST refuse non-canonical MIT.

## 4. Pairwise compatibility matrix

The unique pairs are { Apache 2.0 ↔ CC BY 4.0, Apache 2.0 ↔ MIT, CC BY 4.0 ↔ MIT } and { Apache 2.0 self, CC BY 4.0 self, MIT self }. Self-pairs are trivially compatible. The cross-pairs:

| Pair                   | Compatible? | Direction                         | Substantive note                                                                                                                                                                                                                                                                              |
| ---------------------- | ----------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Apache 2.0 ↔ CC BY 4.0 | YES         | Bidirectional (different domains) | Code and content are different artefact domains. Apache governs the code; CC BY governs the spec text. The Envoy code does not embed the spec text verbatim — it implements the spec's behavioural requirements. The two licenses do not encumber the same artefact, so there is no conflict. |
| Apache 2.0 ↔ MIT       | YES         | Bidirectional                     | Standard outcome. Apache 2.0 is one-way compatible "upward" (Apache → GPL 3.0), and bidirectionally compatible with MIT. A bundle containing Apache 2.0 + MIT artefacts may be distributed if both notice-preservation requirements are honoured (Apache § 4 + MIT notice clause).            |
| CC BY 4.0 ↔ MIT        | YES         | Bidirectional (different domains) | CC BY governs the spec; MIT governs the skill content. They never apply to the same artefact in Envoy's flow. The spec is referenced (CC BY attribution); the MIT skill is preserved verbatim with its notice.                                                                                |

The triple Apache 2.0 ⊕ CC BY 4.0 ⊕ MIT is internally compatible because every pairwise interaction is compatible AND no pair shares an artefact domain that would surface a license-conflict reading. The composite distribution is therefore valid as long as **all three notice-preservation requirements are honoured simultaneously**.

## 5. Per-flow analysis

### 5.1 Flow (a) — Apache 2.0 code consuming CC BY 4.0 specs

**Question:** Does Envoy's Apache 2.0 code, by virtue of implementing the Foundation's CC BY 4.0 specs, inherit any CC BY 4.0 license obligations?

**Analysis:**

1. CC BY 4.0 governs the **expression** of the spec — the prose, the diagrams, the JSON examples in the published `terrene.foundation` spec documents. It does not govern the **ideas** the spec describes (constraint dimensions, envelope intersection algorithm, ledger hash-chain structure). Ideas are not copyrightable in any jurisdiction this Foundation operates under (US, EU, Singapore).
2. Envoy's code implements the ideas. The code does not embed substantial blocks of spec text. Where Envoy's code or comments quote a spec passage verbatim (e.g. an algorithm description in a docstring), CC BY 4.0 attribution applies to that passage — same handling as any quoted attribution material.
3. Envoy's NOTICE file already carries "Terrene Foundation specifications referenced here (CARE, EATP, CO, PACT): CC BY 4.0, owned by Terrene Foundation." This satisfies the attribution clause for the implementation-level reference.

**Verdict:** No CC BY 4.0 obligation propagates to Envoy's Apache 2.0 code beyond NOTICE-level attribution. **Compatible.**

**Counsel item:** Confirm that the current NOTICE attribution language ("Terrene Foundation specifications referenced here…") is sufficient under CC BY 4.0 § 3(a)(1)(A) (attribution of the licensor) and § 3(a)(1)(B) (URI to the license).

### 5.2 Flow (b1) — Translator emits CO-compliant ENVELOPE.md from MIT SKILL.md

**Question:** When Envoy's `SKILL.md` translator produces an `ENVELOPE.md` companion to a third-party MIT `SKILL.md`, what license governs the generated `ENVELOPE.md`?

**Analysis:**

1. Per ADR-0005, the original `SKILL.md` is preserved unchanged. The translator does not modify the input.
2. The output `ENVELOPE.md` is a NEW document authored by Envoy's CO-compliance algorithm. It contains:
   - Permission declarations derived from the SKILL.md's `tools:` clause (e.g. `bash:*` → PACT operational-dimension constraint).
   - PACT-dimension mappings: structural translations from SKILL.md format to PACT's five-dimension form.
   - References to the source `SKILL.md` (filename + content hash).
3. The generated content is mechanically derived from the SKILL.md's declared structure, not from its expressive content. The output is an algorithmic derivation; whether it constitutes a "derivative work" under copyright depends on whether the algorithm copies expressive elements of the input.
4. **Conservative posture:** treat the generated `ENVELOPE.md` as a derivative work of the input `SKILL.md` and license it under the most permissive license compatible with downstream distribution — i.e. inherit MIT from the input, OR dual-license MIT + Apache 2.0 (clarify with counsel).
5. **Practical posture:** ship the generated `ENVELOPE.md` with a header that states: "This `ENVELOPE.md` is auto-generated by Envoy's `SKILL.md` translator from `<SKILL.md filename>` (©<author> — MIT). The structure of this file is mechanical translation; the substantive content traces to the source skill. Permission terms and attribution preserve the source license." This makes the inheritance explicit and avoids overclaiming Envoy's authorship over derivative content.

**Verdict:** Generated `ENVELOPE.md` inherits MIT from the source `SKILL.md`; Envoy's translator code itself remains Apache 2.0. **Compatible** — the bundle is "MIT skill + MIT-derived envelope + Apache 2.0 translator, each under its own terms".

**Counsel item:** Confirm the inherit-MIT-on-output posture is acceptable and that the header text above is sufficient. Alternative: if counsel prefers, dual-license output as `MIT OR Apache-2.0` to preserve the user's right to redistribute under either license.

### 5.3 Flow (b2) — Envoy runtime executes ingested MIT skills

**Question:** When Envoy's Apache 2.0 runtime executes an MIT-licensed skill, does the MIT license propagate to the runtime's behaviour, the runtime's logs, or any output the skill produces?

**Analysis:**

1. MIT licenses the skill's expression (the `SKILL.md` text + any code blocks it embeds). Execution is not redistribution. The user's local Envoy invoking the skill is internal use; MIT does not impose any restriction on internal use.
2. Skill output (e.g. results returned by the skill's tool calls) is a runtime byproduct. The skill's MIT license does not propagate to runtime byproducts unless the skill author explicitly claims output ownership in the SKILL.md itself (rare, and would be a non-canonical MIT — see §6.3).
3. Envoy's runtime logs (e.g. ledger entries) recording that "skill X executed" do not constitute redistribution of the skill itself; they reference it. A ledger entry with a hash of the skill is not a copy of the skill.

**Verdict:** No license propagation from MIT skill execution to the Apache 2.0 runtime. **Compatible.**

### 5.4 Flow (c) — Downstream redistribution of the aggregated bundle

**Question:** A downstream redistributor (a Linux distro, an enterprise container image, a partner reseller) ships an Envoy installation that includes (i) Envoy code + runtime, (ii) ingested SKILL.md community skills, (iii) reference text or implementation comments quoting Foundation specs. What license-attribution requirements apply to that redistributor?

**Analysis:**

1. **Apache 2.0 portions** (Envoy app, kailash-runtime, kailash-py code, kailash-rs-bindings glue): redistributor preserves LICENSE + NOTICE + copyright notices in their distribution. § 4 propagates to all derivatives.
2. **CC BY 4.0 portions** (any quoted spec text): redistributor preserves attribution. NOTICE-level reference is sufficient.
3. **MIT skill portions**: redistributor preserves MIT copyright notice and license text for each ingested skill. Practically: the user's `~/.envoy/skills/<skill-id>/SKILL.md` directory contains the MIT notice already; redistribution preserves the directory.
4. **`LicenseRef-kailash-rs-bindings-binary-grant`** (the kailash-rs-bindings compiled binary): redistributor preserves the LICENSE-BINARY-GRANT file (which carries the freely-redistributable grant + no-modification clause) inside the wheel.

**Verdict:** Compatible with all standard downstream redistribution patterns (Debian, Ubuntu, Fedora, Alpine, Docker Hub, enterprise procurement). **Compatible.**

The aggregated NOTICE format Envoy must publish to make this practical for downstream parties is specified in §7.

## 6. Risk surface

### 6.1 Patent grant gap on MIT skills

**Risk:** A skill author publishes an MIT-licensed skill that exercises a patent the author owns. MIT's lack of patent grant means the user has no patent license. The author can later sue users for patent infringement.

**Mitigation:**

1. Foundation-Verified tier (ADR-0004) accepts only skills whose authors sign an additional patent-grant acknowledgement at publish time. This is operationally a 2-of-N Foundation signature on the publish, contingent on the patent-grant acknowledgement being on file.
2. Community tier accepts MIT skills as-is. Envoy's runtime warns the user at `envoy skill install` time: "this skill is published under MIT, which does not include an explicit patent grant. Patents held by the skill author may apply to the skill's use. Foundation-Verified tier skills include explicit patent grants."
3. Counsel item: draft the patent-grant acknowledgement template for Foundation-Verified tier publish.

### 6.2 Non-canonical MIT (MIT-with-extra-restrictions)

**Risk:** A skill labels itself "MIT" but ships text with non-endorsement, non-commercial, or field-of-use restrictions. These are not MIT; they are bespoke licenses that may conflict with Apache 2.0 redistribution.

**Mitigation:**

1. Skill-license validator: at `envoy skill install`, the validator hashes the skill's LICENSE file and compares against a registry of canonical MIT text variants (Expat MIT, X11 MIT, modern OSI MIT). If the hash matches a canonical variant, accept. If not, reject with a clear error: "this skill labels itself MIT but ships non-canonical license text. Please contact the skill author for a canonical license. To override, use `envoy skill install --force-license-override <hash>`."
2. Counsel item: produce the canonical MIT hash registry.

### 6.3 CC BY 4.0 attribution decay over redistribution chain

**Risk:** A multi-hop redistribution (Envoy → distro → enterprise → downstream user) may strip the CC BY 4.0 attribution as each hop edits the NOTICE file.

**Mitigation:**

1. Make the attribution machine-readable: ship a `THIRD-PARTY-NOTICES.json` alongside NOTICE that downstream tooling can parse and re-emit verbatim. Format: SPDX SBOM + per-component attribution string + license URL.
2. Apache 2.0 § 4 "all such NOTICE attributions" already requires propagation; the JSON form is engineering hygiene to make compliance cheap.

### 6.4 Composite license on `kailash-rs-bindings`

**Risk:** The `LicenseRef-kailash-rs-bindings-binary-grant` LicenseRef is custom — license scanners will flag it as "unknown" until each scanner's policy registry is updated.

**Mitigation:** Already addressed in `02-kailash-rs-bindings-SPDX-draft.md` §"Scanner-by-scanner expectations" — first publish triggers a one-time manual review; subsequent publishes auto-pass under the same hash.

### 6.5 Apache 2.0 patent termination cascade

**Risk:** Apache 2.0 § 3 — patent litigation against the licensor terminates the litigant's patent grant. If a SKILL.md author sues Envoy users over patents, Apache 2.0 termination triggers for the litigant's use of Envoy code.

**Mitigation:** This is the desired behaviour — Apache 2.0 § 3 is a defensive patent-termination clause. No mitigation needed; the structural defence is built into the license.

## 7. Aggregated NOTICE format

To satisfy all three license families' attribution requirements simultaneously, Envoy's distribution publishes a single aggregated NOTICE structure:

```
envoy/
├── LICENSE                        # Apache 2.0 (full text)
├── NOTICE                         # Apache 2.0 § 4 NOTICE — Envoy's own copyright + Foundation reference
├── THIRD-PARTY-NOTICES.json       # SBOM + machine-readable attribution per component
└── third-party-notices/
    ├── kailash-rs-bindings/
    │   ├── LICENSE                # Composite: Apache 2.0 + LicenseRef-kailash-rs-bindings-binary-grant
    │   ├── LICENSE-APACHE-2.0
    │   └── LICENSE-BINARY-GRANT
    ├── kailash-py/
    │   └── LICENSE                # Apache 2.0
    ├── specs/
    │   └── ATTRIBUTION.md         # CC BY 4.0 attribution for CARE / PACT / EATP / CO referenced in code/comments
    └── skills/
        └── <skill-id>/
            └── LICENSE            # Per-skill MIT (or other permissive) verbatim
```

The `THIRD-PARTY-NOTICES.json` schema:

```json
{
  "schema_version": "1.0",
  "envoy_version": "0.x.y",
  "components": [
    {
      "name": "kailash-rs-bindings",
      "version": "X.Y.Z",
      "license_expression": "Apache-2.0 AND LicenseRef-kailash-rs-bindings-binary-grant",
      "license_files": [
        "LICENSE",
        "LICENSE-APACHE-2.0",
        "LICENSE-BINARY-GRANT"
      ],
      "copyright": "Copyright (c) 2026 Terrene Foundation Ltd. (Singapore CLG)",
      "homepage": "https://terrene.foundation/kailash"
    },
    {
      "name": "kailash-py",
      "version": "X.Y.Z",
      "license_expression": "Apache-2.0",
      "license_files": ["LICENSE"],
      "copyright": "Copyright (c) 2026 Terrene Foundation Ltd. (Singapore CLG)",
      "homepage": "https://terrene.foundation/kailash-py"
    },
    {
      "name": "Foundation specifications (CARE, PACT, EATP, CO)",
      "version": "see specs/_index.md",
      "license_expression": "CC-BY-4.0",
      "license_files": ["specs/ATTRIBUTION.md"],
      "copyright": "Copyright (c) 2026 Terrene Foundation Ltd. (Singapore CLG)",
      "homepage": "https://terrene.foundation"
    },
    {
      "name": "skill:<skill-id>",
      "version": "<skill-version>",
      "license_expression": "MIT",
      "license_files": ["third-party-notices/skills/<skill-id>/LICENSE"],
      "copyright": "<skill author copyright>",
      "homepage": "<skill source URL>"
    }
  ]
}
```

This single file is the structural defence against attribution decay (§6.3). Downstream redistributors who consume the file mechanically (FOSSA, Snyk, Sonatype, ClearlyDefined) emit the attribution in their own bundle without manual intervention.

## 8. The Foundation-Verified tier license policy

ADR-0004 § Tier 1 (Foundation-Verified) defines the curation bar for Foundation-published envelope and skill templates. The licensing dimension of that bar:

| Status                    | Accepted                                                                            | Rejected                                                                                  |
| ------------------------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Accepted licenses**     | MIT (Expat), Apache 2.0, BSD-2-Clause, BSD-3-Clause, ISC, CC0, Unlicense, CC BY 4.0 | Anything else                                                                             |
| **Rejected — copyleft**   | —                                                                                   | GPL (any version), AGPL, LGPL (any version), MPL 2.0 (mixed file copyleft)                |
| **Rejected — restricted** | —                                                                                   | "MIT-with-additional-restrictions", non-commercial, non-endorsement, field-of-use clauses |
| **Conditional**           | Source-available licenses (BSL, SSPL): case-by-case board review; default reject    | —                                                                                         |

**Rationale:**

1. **Copyleft rejection** at the Foundation-Verified tier prevents copyleft license terms from propagating into Envoy's downstream redistribution. A GPL skill in the Foundation-Verified bundle would force downstream Envoy distributors to expose Envoy code under GPL — incompatible with the Apache 2.0 + freely-redistributable-binary stance.
2. **Community tier (Tier 2)** has no license curation — users may publish any license. Envoy's skill installer warns about non-permissive licenses and refuses to redistribute without explicit `--force-license-override` (per §6.2).
3. **Organisation tier (Tier 3)** is the enterprise's call — the enterprise's own license-policy applies inside its private registry.

**Counsel item:** confirm the accepted-license list is exhaustive and that the rejected-license list is correctly framed (e.g. MPL 2.0's file-level copyleft is genuinely incompatible vs case-by-case acceptable).

## 9. Counsel sign-off checklist

Items legal counsel must confirm before this analysis is final and the Foundation board endorses ADR-0009 and ADR-0005:

1. **§3.1 Apache 2.0** characterisation — patent-grant scope, NOTICE-preservation propagation, GPL-3.0 outbound compatibility.
2. **§3.2 CC BY 4.0** characterisation — implementing-the-ideas vs quoting-the-text distinction; § 3(a) attribution framing for NOTICE-level reference.
3. **§3.3 MIT** characterisation — patent-grant absence; canonical-Expat distinction from MIT-with-additional-restrictions.
4. **§4 Pairwise compatibility matrix** — confirm each cell.
5. **§5.1 Flow (a)** verdict — code consuming spec creates no CC BY 4.0 obligation beyond NOTICE attribution.
6. **§5.2 Flow (b1)** verdict — translator output inherits MIT from input; counsel chooses between inherit-MIT and dual-license MIT-OR-Apache-2.0 posture.
7. **§5.3 Flow (b2)** verdict — runtime execution does not propagate skill license.
8. **§5.4 Flow (c)** verdict — aggregated downstream redistribution is compatible with the listed redistribution patterns.
9. **§6.1 Patent-grant gap on MIT skills** — Foundation-Verified tier patent-grant acknowledgement template.
10. **§6.2 Non-canonical MIT detection** — canonical-MIT hash registry.
11. **§6.3 Attribution decay** — `THIRD-PARTY-NOTICES.json` schema acceptable as machine-readable attribution surface.
12. **§7 Aggregated NOTICE** — directory layout and per-component breakdown sufficient.
13. **§8 Foundation-Verified tier policy** — accepted-license list complete; rejected-license list correctly framed.
14. **Singapore-specific** — confirm the analysis above is sound under Singapore's Copyright Act 2021 (the Foundation's host jurisdiction). Singapore is a Berne signatory and aligns closely with US/UK common-law treatment of these licenses, but the explicit confirmation belongs to counsel.
15. **EU-specific** — confirm the analysis is sound under the EU Copyright Directive 2019/790 (especially Art. 17, the user-uploaded content provisions) and the EU AI Act (effective 2026) — the latter may impose additional disclosure for AI applications that ingest third-party content.

## 10. Foundation board endorsement language

The proposed text for the Foundation board minute (companion to the ADR-0009 endorsement language in `01-envoy-concept-one-pager.md` §"Recommended decision text"):

> The Board confirms that the license-compatibility analysis described in
> Envoy `workspaces/phase-00-alignment/02-plans/legal/03-license-
compatibility-statement.md` is consistent with the Foundation's
> charter and the openness posture described in CHARTER.md. The Board
> endorses the three-license stack — Apache 2.0 (Envoy code), CC BY 4.0
> (Foundation specs), MIT (third-party `SKILL.md` content) — for the
> Envoy distribution, on the basis that (a) every load-bearing
> compatibility question has a published written answer in this
> statement, (b) the aggregated NOTICE format makes downstream
> attribution preservation mechanical, (c) the Foundation-Verified
> tier license policy prevents copyleft propagation through the
> Envoy distribution, (d) the analysis has been signed off by
> Foundation legal counsel.

## 11. Open questions / Phase-01 carry-forward

1. **Translator output license — inherit-MIT vs dual-license.** §5.2 flags two postures. The choice has downstream implications for whether Envoy's auto-generated content is forkable as Apache 2.0 by Envoy users (yes under dual-license; no under inherit-MIT). Counsel preference governs.
2. **Source-available skills (BSL, SSPL).** §8 marks these "case-by-case board review; default reject". Some prosumer skills may legitimately be BSL-licensed. The board may wish to delegate this decision to a Foundation Steward rather than the full board for case-by-case throughput.
3. **EU AI Act effective-date interaction.** §9 item 15 flags this as counsel work. If the EU AI Act creates an attribution-disclosure requirement for ingested AI content, §7's `THIRD-PARTY-NOTICES.json` is the natural place to extend the schema. Phase-02 deliverable.
4. **Patent-grant acknowledgement for Foundation-Verified tier.** §6.1 mitigation depends on a template the Foundation has not yet drafted. Phase-01 carry-forward to draft + adopt at the Foundation operational level.
5. **Cross-language binding consumption.** Envoy ships Python today; Phase-04 ships Rust skills SDK. Wasm-sandbox skills authored in Rust may use crates with licenses outside the §8 accepted-list (e.g. a popular crate is MPL 2.0). Counsel item: revisit §8 when the Rust skills SDK design lands (Phase 04, ADR-0012 placeholder).

---

**Cross-references:**

- ADR-0009 §304–312 (counsel-engagement items)
- ADR-0005 (`SKILL.md` ingest design — flow b1/b2 source)
- ADR-0004 (Envelope Library tier model — §8 source)
- `01-kailash-rs-bindings-LICENSE-draft.md` (composite LICENSE for the Rust binding wheel — §6.4)
- `02-kailash-rs-bindings-SPDX-draft.md` (SPDX expression for the wheel — §6.4)
- `01-envoy-concept-one-pager.md` (Foundation board ask — §10 endorsement language extends that document)
- `01-sweep.md` (Phase-00 claim-verification sweep — anchors the licensing claims this analysis supports)
- NOTICE (current attribution surface — §7 redesign extends this)
- specs/skill-ingest.md (Envoy's `SKILL.md` parser + companion + CO validator — §5.2 implementation reference)
- terrene-naming.md § License Accuracy (canonical license naming this draft is faithful to)

**Drafted:** 2026-05-01 by envoy Phase-00 work, in response to ROADMAP line 30.
**Review owners:** Terrene Foundation legal counsel (substantive sign-off on §3–§9); Foundation Secretary (board minute preparation §10); envoy Phase-00 maintainers (NOTICE format §7 implementation).
