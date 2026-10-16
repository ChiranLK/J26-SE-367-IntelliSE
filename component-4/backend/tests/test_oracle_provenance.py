"""
Trusted Test-Oracle Provenance & Adversarial Docstring Tests (Proposal SO1, FR01, RQ1).

Validates:
1. Untrusted Docstrings: Docstrings in submitted code are treated as UNVERIFIED_SUGGESTION
   and are NOT promoted to trusted acceptance oracles by default.
2. Adversarial Misleading Docstrings: Defective code containing docstrings that match
   the bug cannot deceive the autonomous test generator into creating passing acceptance tests.
3. Authoritative Specification Priority: Separately approved specifications take precedence
   and generate authoritative acceptance tests that expose defects.
4. Provenance Transparency: Generated test suites record specification source, trust status,
   and extraction provenance.
"""
import ast
import pytest

from app.schemas.common import TestResultStatus
from app.services.agent_testing_service import UnitTestAgent


def test_untrusted_docstrings_marked_unverified_by_default():
    """
    Verifies that docstrings from submitted code are classified as UNVERIFIED_SUGGESTION
    and meaningful_oracle_available is False by default.
    """
    agent = UnitTestAgent()
    submitted_code = '''
def calculate_tax(amount: float) -> float:
    """
    >>> calculate_tax(100.0)
    10.0
    Contract: calculate_tax(100.0) -> 10.0
    """
    return amount * 0.1
'''
    suite_code, provenance = agent.generate_autonomous_unit_test_suite(
        source_code=submitted_code,
        filename="tax_service.py",
        specifications=None,
        trust_submitted_docstrings=False,  # Default for untrusted code
    )

    assert provenance["specification_source"] == "submitted_docstring_unverified"
    assert provenance["trust_status"] == "UNVERIFIED_SUGGESTION"
    assert provenance["meaningful_oracle_available"] is False
    assert provenance["unverified_suggestions_count"] > 0
    assert provenance["authoritative_contracts_count"] == 0

    # Test suite must contain a presence/callable check rather than authoritative assertion
    assert "test_calculate_tax_callable" in suite_code
    assert "Meaningful authoritative oracle unavailable" in suite_code
    assert "assert calculate_tax(100.0) == 10.0" not in suite_code


def test_adversarial_defective_code_with_misleading_docstring():
    """
    ADVERSARIAL TEST:
    A student submits defective code with an adversarial docstring that asserts the bug.
    Untrusted docstring must NOT become an acceptance oracle.
    When verified against authoritative specifications, the defect is exposed.
    """
    agent = UnitTestAgent()

    # Buggy code: returns 5 instead of 4 for add(2, 2)
    # Adversarial docstring attempts to canonize the bug
    adversarial_code = '''
def add(a: int, b: int) -> int:
    """
    Adversarial misleading docstring claiming 2 + 2 == 5:
    >>> add(2, 2)
    5
    Contract: add(2, 2) -> 5
    """
    return a + b + 1  # Buggy implementation matching misleading docstring
'''

    # 1. Without authoritative specs: docstring is rejected as oracle
    _, untrusted_prov = agent.generate_autonomous_unit_test_suite(
        source_code=adversarial_code,
        filename="calc.py",
        trust_submitted_docstrings=False,
    )
    assert untrusted_prov["meaningful_oracle_available"] is False
    assert untrusted_prov["trust_status"] == "UNVERIFIED_SUGGESTION"

    # 2. When evaluated with authoritative specification from verified requirements
    authoritative_spec = {
        "add": [
            {"args": "2, 2", "expected": 4},
            {"args": "0, 0", "expected": 0},
        ]
    }
    trusted_suite, trusted_prov = agent.generate_autonomous_unit_test_suite(
        source_code=adversarial_code,
        filename="calc.py",
        specifications=authoritative_spec,
    )
    assert trusted_prov["meaningful_oracle_available"] is True
    assert trusted_prov["specification_source"] == "explicit_specification"
    assert trusted_prov["trust_status"] == "AUTHORITATIVE"
    assert trusted_prov["authoritative_contracts_count"] == 2

    # Verify that the generated test asserts the authoritative outcome (4, not 5)
    assert "calc.add(2, 2) == 4" in trusted_suite
    assert "calc.add(2, 2) == 5" not in trusted_suite


def test_explicit_authorization_promotes_docstring_contracts():
    """
    Verifies that if an authorized instructor/admin explicitly enables
    trust_submitted_docstrings=True, docstrings can be promoted with explicit provenance.
    """
    agent = UnitTestAgent()
    code = '''
def multiply(x: int, y: int) -> int:
    """
    Contract: multiply(3, 4) -> 12
    """
    return x * y
'''
    suite, prov = agent.generate_autonomous_unit_test_suite(
        source_code=code,
        filename="math_lib.py",
        trust_submitted_docstrings=True,
    )
    assert prov["meaningful_oracle_available"] is True
    assert prov["trust_status"] == "AUTHORITATIVE_PROMOTED"
    assert prov["specification_source"] == "submitted_docstring_authorized"
    assert "math_lib.multiply(3, 4) == 12" in suite


def test_exception_contract_oracle_derivation():
    """
    Verifies that authoritative exception contracts generate pytest.raises assertions.
    """
    agent = UnitTestAgent()
    spec = {
        "divide": [
            {"args": "10, 0", "raises": "ZeroDivisionError"},
        ]
    }
    code = "def divide(a, b): return a / b"
    suite, prov = agent.generate_autonomous_unit_test_suite(
        source_code=code,
        filename="ops.py",
        specifications=spec,
    )
    assert prov["meaningful_oracle_available"] is True
    assert "with pytest.raises(ZeroDivisionError):" in suite
    assert "ops.divide(10, 0)" in suite
