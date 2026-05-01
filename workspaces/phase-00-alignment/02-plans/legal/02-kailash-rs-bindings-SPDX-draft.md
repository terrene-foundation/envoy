# SPDX metadata draft — `kailash-rs-bindings` PyPI wheel

**Status:** DRAFT for legal-counsel review.
**Owner:** envoy Phase-00 (drafted), Terrene Foundation legal counsel (final), `kailash-rs-bindings` maintainers (adoption).
**Source contract:** `DECISIONS.md §ADR-0009` item 2 — SPDX metadata that reads cleanly under FOSSA, Snyk, Sonatype.
**Why this draft exists:** envoy's procurement story depends on automated license scanners (FOSSA, Snyk, Sonatype, Black Duck, ClearlyDefined) classifying `pip install kailash` as fully-redistributable with no commercial-license requirement. A composite SPDX expression must (a) be a valid SPDX 2.3 expression, (b) reference a `LicenseRef-` declaration whose text is shipped inside the wheel, (c) survive scanner heuristics that flag unknown `LicenseRef-` identifiers as "non-OSI / requires manual review."

---

## Recommended SPDX expression

```
Apache-2.0 AND LicenseRef-kailash-rs-bindings-binary-grant
```

**Rationale:**

- `AND` (not `OR`) because both terms apply jointly to the composite work — the user receives Apache 2.0 on the Python glue AND the binary grant on the compiled core. `OR` would imply a choice (incorrect: user does not get to pick one).
- `LicenseRef-kailash-rs-bindings-binary-grant` — namespaced custom license identifier per SPDX spec § 10. The ID is descriptive and unique; no collision with existing SPDX identifiers.
- The `LicenseRef-` text MUST be shipped at the path declared in pyproject.toml (`License-File: LICENSE-BINARY-GRANT`) so scanners that fetch wheel contents can extract verbatim grant text.

## Recommended `pyproject.toml` shape (PEP 639 + SPDX)

```toml
[project]
name = "kailash"                                                    # Final PyPI name TBD per ADR-0002 trademark sweep
version = "X.Y.Z"
description = "Rust-accelerated kailash runtime — binding for Python."
readme = "README.md"
requires-python = ">=3.10"

# PEP 639 — composite SPDX expression
license = "Apache-2.0 AND LicenseRef-kailash-rs-bindings-binary-grant"

# PEP 639 — license-file glob; ALL three must appear in the built wheel
license-files = [
    "LICENSE",
    "LICENSE-APACHE-2.0",
    "LICENSE-BINARY-GRANT",
]

# Classifiers — DO NOT use "License :: OSI Approved :: ..." classifiers
# as they conflict with PEP 639's `license` field per modern packaging
# spec. Counsel should confirm that omitting all License :: classifiers
# is the right call for composite-licensed wheels.
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Rust",
    # NO License :: classifier — see PEP 639 § "License classifiers deprecation"
]
```

## Wheel build — `MANIFEST.in` additions

```
# Include all three license files in the built distribution
include LICENSE
include LICENSE-APACHE-2.0
include LICENSE-BINARY-GRANT
```

## Verification — what scanners must see

After `pip install kailash` and `pip show -f kailash`, the following file paths MUST resolve:

- `kailash-X.Y.Z.dist-info/LICENSE` — composite license summary (PART A + B + C)
- `kailash-X.Y.Z.dist-info/LICENSE-APACHE-2.0` — verbatim Apache 2.0
- `kailash-X.Y.Z.dist-info/LICENSE-BINARY-GRANT` — verbatim PART B text from the composite

After parsing the wheel METADATA file, scanners MUST extract:

- `License-Expression: Apache-2.0 AND LicenseRef-kailash-rs-bindings-binary-grant`
- `License-File: LICENSE`
- `License-File: LICENSE-APACHE-2.0`
- `License-File: LICENSE-BINARY-GRANT`

## Scanner-by-scanner expectations

| Scanner                | Expected classification                                                                                             | Manual-review trigger                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **FOSSA**              | "Apache 2.0 + custom redistributable" — green flag for redistribution; AMBER on `LicenseRef-` for first-time review | First wheel version triggers a one-time policy decision; subsequent versions auto-approve under same hash                       |
| **Snyk**               | Apache 2.0 detected; binary grant flagged for review                                                                | Manual review of `LicenseRef-` text — counsel-readable                                                                          |
| **Sonatype Lifecycle** | Composite expression parsed; AMBER until policy added                                                               | Add Sonatype policy mapping `LicenseRef-kailash-rs-bindings-binary-grant` → "freely redistributable, no commercial restriction" |
| **Black Duck**         | Apache 2.0 + Custom — review required                                                                               | Custom-license registration; one-time                                                                                           |
| **ClearlyDefined**     | Apache-2.0 detected for source files; binary blob unclassified                                                      | Submit a curation PR after first publish so future scans match the curated record                                               |

**Implication:** the FIRST publish triggers manual-review prompts in every scanner; subsequent publishes (same `LicenseRef-` text hash) auto-pass. Document this expectation for procurement teams in advance.

## Open questions for legal counsel

1. **PEP 639 adoption timeline.** PEP 639 is final but tooling support (setuptools, hatchling, scikit-build) has uneven roll-out. Confirm the build system planned for `kailash-rs-bindings` (likely `maturin`) emits the `License-Expression:` and `License-File:` METADATA fields per PEP 639, not the legacy `License:` field.

2. **`License-File` glob expansion.** PEP 639 allows globs in `license-files`. Confirm `["LICENSE*"]` is acceptable shorthand or whether explicit enumeration (recommended above) is preferred.

3. **PyPI display.** PyPI's project-page renders `License-Expression:` if present and falls back to `License:` otherwise. Confirm the rendered display text is acceptable to Foundation comms ("Apache-2.0 AND LicenseRef-kailash-rs-bindings-binary-grant" — slightly opaque to non-legal readers).

4. **Trove classifier conflict.** PEP 639 deprecates `License :: ...` Trove classifiers when `license` is set. Confirm no `License ::` classifier ships, and confirm this does NOT regress filters on PyPI's "browse by license" facets in a way that hurts discoverability.

5. **Conda-forge parity.** If `kailash` ever lands in conda-forge, the SPDX expression maps to conda-forge's `license_family` differently. Confirm the conda-forge recipe (when authored) uses `license_family: Apache` + `license_file: ['LICENSE', 'LICENSE-APACHE-2.0', 'LICENSE-BINARY-GRANT']`.

6. **Trademark expression in metadata.** `description` field uses the working name "kailash". Final mark depends on Phase-00 trademark sweep (ADR-0002). Confirm the SPDX shape is independent of name finalization (it is: `LicenseRef-` text is anchored to text content, not project name).

## Verification harness — envoy CI gate

```python
# tests/integration/test_runtime_license_metadata.py
import importlib.metadata as md
import pytest

def test_kailash_runtime_license_metadata():
    """Envoy's release gate — kailash wheel must declare composite license cleanly."""
    meta = md.metadata("kailash")
    expr = meta.get("License-Expression") or meta.get("License")
    assert "Apache-2.0" in expr, f"License missing Apache-2.0: {expr!r}"
    assert "LicenseRef-kailash-rs-bindings-binary-grant" in expr, (
        f"License missing binary-grant LicenseRef: {expr!r}"
    )
    files = meta.get_all("License-File") or []
    expected = {"LICENSE", "LICENSE-APACHE-2.0", "LICENSE-BINARY-GRANT"}
    assert expected.issubset(set(files)), (
        f"Missing license files; got {files}, expected superset of {expected}"
    )
```

This test runs in envoy CI on every release; if `kailash-rs-bindings` ever ships a wheel with broken license metadata, envoy's release is blocked until the bindings are fixed.

---

**Cross-references:** companion draft `01-kailash-rs-bindings-LICENSE-draft.md` (the LICENSE text); `DECISIONS.md §ADR-0009` items 1, 2; envoy `pyproject.toml` already declares `license = "Apache-2.0"` for envoy itself.
