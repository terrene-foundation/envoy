"""THROWAWAY probe — deliberately failing test to prove the tests-gate ruleset
blocks `gh pr merge --admin` over red CI. This file/branch is never merged."""


def test_intentional_failure_to_prove_ci_hard_block() -> None:
    assert False, "intentional — proving tests-gate ruleset blocks --admin merge"
