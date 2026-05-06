"""Tier 1 unit-test conftest.

Per `rules/testing.md` § Tier 1: mocking allowed; <1s per test. Pure-function
and dataclass surfaces; no real infrastructure.
"""

import pytest


@pytest.fixture
def principal_id() -> str:
    """Canonical test principal_id per rules/tenant-isolation.md."""
    return "test-principal-alpha"
