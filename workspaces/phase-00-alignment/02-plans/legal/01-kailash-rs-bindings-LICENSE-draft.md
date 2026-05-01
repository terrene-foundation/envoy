# Composite LICENSE draft — `kailash-rs-bindings` PyPI wheel

**Status:** DRAFT for legal-counsel review.
**Owner:** envoy Phase-00 (drafted), Terrene Foundation legal counsel (final), `kailash-rs-bindings` maintainers (adoption).
**Source contract:** `DECISIONS.md §ADR-0009` item 1 — composite LICENSE for the kailash-rs-bindings wheel.
**Why this draft exists:** envoy's distribution depends on `pip install kailash` resolving to a wheel whose LICENSE file (a) cleanly delineates the Apache 2.0 Python glue from the freely-redistributable compiled binary, (b) grants explicit end-user rights compatible with envoy's Apache 2.0 redistribution, (c) reads cleanly under FOSSA / Snyk / Sonatype scanners. This draft proposes the shape; legal counsel finalises wording.

---

## Proposed file: `LICENSE` (root of `kailash-rs-bindings` source + included in built wheel)

```
================================================================
kailash-rs-bindings — Composite License
================================================================

Copyright (c) 2026 Terrene Foundation Ltd. (Singapore CLG)
All rights reserved.

This package is distributed as a composite work under two distinct
licensing terms covering two distinct components. The terms below
apply jointly. By installing or using this package, you agree to
both sets of terms.

----------------------------------------------------------------
PART A — Python source ("the Glue")
----------------------------------------------------------------

The Python source code in this package — including but not limited
to all `.py` files, `.pyi` type stubs, packaging metadata, and
documentation under `docs/` — is licensed under the Apache License,
Version 2.0 (the "Apache License").

You may obtain a copy of the Apache License at:

    http://www.apache.org/licenses/LICENSE-2.0

The full text of the Apache License is reproduced verbatim in
`LICENSE-APACHE-2.0` in this distribution.

----------------------------------------------------------------
PART B — Compiled native binary ("the Core")
----------------------------------------------------------------

The compiled native binary distributed with this package — including
all `.so`, `.dylib`, `.pyd`, and `.dll` files compiled from Rust
source by the Terrene Foundation — is provided to you under the
following terms:

(1) FREELY REDISTRIBUTABLE BINARY GRANT. The Terrene Foundation
    grants you a perpetual, worldwide, royalty-free, non-exclusive
    license to use, copy, and redistribute the compiled binary
    in unmodified form, alone or as part of an application, library,
    container image, operating-system distribution, or other
    aggregate work, with no requirement to register, pay, or accept
    additional terms.

(2) NO MODIFICATION OF THE BINARY. You may not modify, reverse-
    engineer, decompile, or disassemble the compiled binary. The
    binary is provided in compiled form only; the corresponding
    Rust source is not distributed with this license.

(3) NO WARRANTY. THE BINARY IS PROVIDED "AS IS", WITHOUT WARRANTY
    OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
    THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
    PURPOSE, AND NONINFRINGEMENT. IN NO EVENT SHALL THE TERRENE
    FOUNDATION BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY
    ARISING FROM, OUT OF, OR IN CONNECTION WITH THE BINARY OR THE
    USE OR OTHER DEALINGS IN THE BINARY.

(4) FREE OF CHARGE; NO REGISTRATION; NO COMMERCIAL TERMS. The
    binary is distributed at no cost, without registration, account
    creation, license-key activation, telemetry, network call-home,
    or commercial terms of any kind. No paid tier exists.

(5) ALTERNATIVE FULLY OPEN-SOURCE IMPLEMENTATION AVAILABLE. The
    Terrene Foundation publishes `kailash-py`, a fully open-source
    Python implementation of the same specifications (CARE, EATP,
    CO, PACT — CC BY 4.0; code Apache 2.0). The two implementations
    are designed for byte-identical conformance per published test
    vectors. End users who wish to use, modify, or redistribute a
    fully-open-source runtime may switch to `kailash-py` at any
    time without changing application code beyond an installer flag.

(6) EXPORT CONTROL. The binary may include cryptographic primitives
    (Ed25519 signature, SHA-256 hashing, Shamir secret sharing).
    Users redistributing the binary across jurisdictional boundaries
    are responsible for compliance with applicable export-control
    regulations including but not limited to the U.S. Export
    Administration Regulations (EAR) and Singapore's Strategic
    Goods (Control) Act. The Terrene Foundation makes no
    representations regarding such compliance.

----------------------------------------------------------------
PART C — Specifications referenced
----------------------------------------------------------------

Specifications implemented by this package — CARE, EATP, CO, PACT —
are owned by the Terrene Foundation and licensed under the Creative
Commons Attribution 4.0 International License (CC BY 4.0). Full
text at:

    https://creativecommons.org/licenses/by/4.0/

================================================================
End of composite license.
================================================================
```

## Companion file: `LICENSE-APACHE-2.0`

Verbatim Apache License 2.0 text. (Same as envoy's existing `LICENSE` file at repo root.)

## Companion file: `LICENSE-BINARY-GRANT`

Verbatim copy of PART B above, isolated for SPDX `LicenseRef-` resolution.

---

## Open questions for legal counsel

1. **Reverse-engineering carve-out.** PART B (2) blocks reverse-engineering. Some jurisdictions (e.g. EU Software Directive Art. 6) grant a non-waivable right to reverse-engineer for interoperability. Should PART B (2) include an explicit "except where mandated by applicable law" clause? Recommendation: yes.

2. **Sublicense vs grant language.** PART B uses "grants you a license." Should this be a grant of permissions (no license terminology) to avoid implying GPL-style downstream sublicense obligations? Recommendation: counsel preference.

3. **Termination.** Apache 2.0 has implicit termination on patent litigation. PART B does not. Should termination clauses be added to PART B for parity? Recommendation: optional; not adding may be cleaner.

4. **Warranty disclaimer overlap.** PART A (Apache 2.0) and PART B (3) both disclaim warranty. Acceptable redundancy or should the file consolidate? Recommendation: keep both — Apache 2.0 disclaimer is in the referenced file, the binary disclaimer needs to be in the composite file because a downstream redistributor reading only the composite file must see it.

5. **EU AI Act binary-component disclosure.** Does the EU AI Act (effective 2026) require additional disclosure when redistributing AI-related binaries with downstream products? Recommendation: counsel investigates; placeholder section may be needed.

6. **Singapore CLG capacity to grant.** Confirm Terrene Foundation's CLG memorandum permits granting these specific binary-redistribution rights without additional board action. Recommendation: counsel confirms; board minute may be needed.

## Rejected alternatives

- **Pure Apache 2.0 on the entire wheel.** Rejected: requires source distribution of the Rust core, which conflicts with the closed-source-binary aspect of ADR-0009.
- **Proprietary EULA on the wheel.** Rejected: violates ADR-0009 "every user path is free, no commercial ToS" principle. Composite is the structural compromise.
- **Dual Apache 2.0 / MIT on the glue.** Rejected: no benefit to envoy; pure Apache 2.0 is sufficient and matches envoy itself.

## Adoption pathway

1. envoy → kailash-rs-bindings maintainers: present this draft + counsel's revisions.
2. kailash-rs-bindings maintainers: adopt LICENSE + LICENSE-APACHE-2.0 + LICENSE-BINARY-GRANT in the wheel build; add to `MANIFEST.in` so all three ship inside the `.whl`.
3. envoy CI gate: `pip-licenses --with-license-file --format=json` on a fresh install of `kailash` must resolve all three license files; diff against expected fingerprint.

---

**Cross-references:** `DECISIONS.md §ADR-0009` items 1, 2, 3 (charter compat); `ROADMAP.md` Phase 00 Licensing track; companion draft `02-kailash-rs-bindings-SPDX-draft.md` for the PyPI metadata side.
