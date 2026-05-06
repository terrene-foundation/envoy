"""tests/-scope conftest.

Excludes `tests/sdk/test_sdk_patterns.py` from pytest collection. That file is a
standalone smoke script invoked directly via `python tests/sdk/test_sdk_patterns.py`
(per its module docstring `Usage:` block); its `def test(name)` helper is a
decorator factory, not a pytest test, and pytest's default collector misreads it
as a fixture-using test causing `fixture 'name' not found` at collection time.

Disposition: smoke-script workflow predates pytest infrastructure (inherited from
COC scaffold commit `2942013`); the script is correct as-is when invoked directly,
the bug is solely pytest's misclassification. Excluding it from collection per
`rules/orphan-detection.md` MUST Rule 5 (collect-only is a merge gate) — the
collection error blocks the entire suite if not silenced.
"""

collect_ignore_glob = ["sdk/test_sdk_patterns.py"]
