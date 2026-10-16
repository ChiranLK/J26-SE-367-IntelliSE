from typing import List

from app.benchmark.models import BenchmarkScenario, BenchmarkScenarioGroup
from app.schemas.common import DefectCategory


PILOT_BENCHMARK_SCENARIOS: List[BenchmarkScenario] = [
    # =========================================================================
    # Group 1: Clean Controls (Table 4: 20% proposed share)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="TX01-01",
        name="Clean Calculator Operations",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        module_code="""
def add(a: float, b: float) -> float:
    return a + b

def multiply(a: float, b: float) -> float:
    return a * b
""",
        test_code="""
import solution

def test_add():
    assert solution.add(10, 5) == 15
    assert solution.add(-1, 1) == 0

def test_multiply():
    assert solution.multiply(4, 5) == 20
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="First-pass convergence with zero repair iterations",
    ),
    BenchmarkScenario(
        scenario_id="TX01-02",
        name="Clean String Formatter Utility",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        module_code="""
def format_user_tag(username: str, role: str) -> str:
    return f"[{role.upper()}] {username.strip()}"
""",
        test_code="""
import solution

def test_format_user_tag():
    assert solution.format_user_tag("alice ", "admin") == "[ADMIN] alice"
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="First-pass convergence with zero repair iterations",
    ),
    BenchmarkScenario(
        scenario_id="TX01-03",
        name="Clean Input Range Validator",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        module_code="""
def is_valid_percentage(val: float) -> bool:
    return 0.0 <= val <= 100.0
""",
        test_code="""
import solution

def test_is_valid_percentage():
    assert solution.is_valid_percentage(50.0) is True
    assert solution.is_valid_percentage(-0.1) is False
    assert solution.is_valid_percentage(100.0) is True
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="First-pass convergence with zero repair iterations",
    ),

    # =========================================================================
    # Group 2: Functional Bugs (Table 4: 25% proposed share)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="TX02-01",
        name="Off-by-One Pagination Slice Boundary",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        module_code="""
def paginate_items(items: list, page: int, page_size: int) -> list:
    # Defect: off-by-one error using 1-based page without index shift
    start = page * page_size
    return items[start : start + page_size]
""",
        test_code="""
import solution

def test_paginate_first_page():
    data = [1, 2, 3, 4, 5]
    # Page 1 with size 2 should return [1, 2]
    res = solution.paginate_items(data, page=1, page_size=2)
    assert res == [1, 2]
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=3,
        expected_system_behavior="Localize, classify as functional bug, generate scoped explanation",
    ),
    BenchmarkScenario(
        scenario_id="TX02-02",
        name="Tax Calculation Missing Tax Rate Branch",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        module_code="""
def calculate_tax(subtotal: float, apply_tax: bool) -> float:
    if apply_tax:
        # Defect: returns flat 10 instead of 10% rate
        return subtotal + 10.0
    return subtotal
""",
        test_code="""
import solution

def test_calculate_tax_rate():
    assert solution.calculate_tax(100.0, apply_tax=True) == 110.0
    assert solution.calculate_tax(200.0, apply_tax=True) == 220.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Localize, classify as functional bug, generate scoped explanation",
    ),
    BenchmarkScenario(
        scenario_id="TX02-03",
        name="Inverted Boolean In-Stock Filter",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        module_code="""
def filter_in_stock(items: list) -> list:
    # Defect: inverted boolean condition
    return [item for item in items if item.get('quantity', 0) <= 0]
""",
        test_code="""
import solution

def test_filter_in_stock():
    inventory = [{'id': 1, 'quantity': 5}, {'id': 2, 'quantity': 0}]
    in_stock = solution.filter_in_stock(inventory)
    assert len(in_stock) == 1
    assert in_stock[0]['id'] == 1
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=3,
        expected_system_behavior="Localize, classify as functional bug, generate scoped explanation",
    ),
    BenchmarkScenario(
        scenario_id="TX02-04",
        name="Discount Tier Strict Inequality Boundary",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        module_code="""
def compute_discount(total: float) -> float:
    # Defect: strictly greater than 100 instead of greater-than-or-equal
    if total > 100.0:
        return total * 0.1
    return 0.0
""",
        test_code="""
import solution

def test_discount_tier_boundary():
    # Exactly 100 should qualify for tier discount
    assert solution.compute_discount(100.0) == 10.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=3,
        expected_system_behavior="Localize, classify as functional bug, generate scoped explanation",
    ),

    # =========================================================================
    # Group 3: Security Vulnerabilities (Table 4: 20% proposed share)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="TX03-01",
        name="OS Command Injection via os.system (CWE-78)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        module_code="""
import os

def ping_host(hostname: str) -> int:
    # Critical security defect: CWE-78 OS command injection
    cmd = f"ping -c 1 {hostname}"
    return os.system(cmd)
""",
        test_code="""
import solution

def test_ping_host_command_injection():
    # Hostname containing unvalidated shell metacharacters
    result = solution.ping_host("127.0.0.1; whoami")
    assert "os.system" not in "safe_runner"
    assert result == 0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-78",
        expected_line_number=6,
        expected_system_behavior="Critical classification (CWE-78); block deployment readiness until resolved",
    ),
    BenchmarkScenario(
        scenario_id="TX03-02",
        name="Hardcoded Secret Credential (CWE-798)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        module_code="""
def get_auth_token() -> str:
    # Critical security defect: CWE-798 hardcoded JWT secret
    api_key = "super_secret_jwt_token_production_value_9988"
    return api_key
""",
        test_code="""
import solution

def test_hardcoded_secret_security():
    token = solution.get_auth_token()
    # Test checking for absence of hardcoded secret
    assert not token.startswith("super_secret_jwt_token")
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-798",
        expected_line_number=3,
        expected_system_behavior="Critical classification (CWE-798); block deployment readiness until resolved",
    ),
    BenchmarkScenario(
        scenario_id="TX03-03",
        name="Path Traversal File Reader (CWE-22)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        module_code="""
def read_user_file(filename: str) -> str:
    # Critical security defect: CWE-22 path traversal without sanitization
    target = f"/var/data/users/{filename}"
    with open(target, 'r') as f:
        return f.read()
""",
        test_code="""
import solution

def test_path_traversal_vulnerability():
    # Attempting to read outside target directory
    try:
        solution.read_user_file("../../etc/passwd")
        assert False, "Should reject directory traversal"
    except Exception:
        assert False, "CWE-22 directory traversal unhandled"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-22",
        expected_line_number=4,
        expected_system_behavior="Critical classification (CWE-22); block deployment readiness until resolved",
    ),
    BenchmarkScenario(
        scenario_id="TX03-04",
        name="Dynamic Execution via Unsafe Eval (CWE-95)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        module_code="""
def evaluate_math_expression(expr: str):
    # Critical security defect: CWE-95 eval injection
    return eval(expr)
""",
        test_code="""
import solution

def test_eval_injection_security():
    # Test evaluating untrusted expression with code execution
    try:
        solution.evaluate_math_expression("__import__('os').system('id')")
        assert False, "Should not evaluate arbitrary directives"
    except Exception:
        assert False, "CWE-95 eval injection exposed"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-95",
        expected_line_number=3,
        expected_system_behavior="Critical classification (CWE-95); block deployment readiness until resolved",
    ),

    # =========================================================================
    # Group 4: Performance Bottlenecks (Table 4: 15% proposed share)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="TX04-01",
        name="Quadratic String Concatenation In Loop",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        module_code="""
import time

def slow_string_aggregator(n: int) -> str:
    # Performance bottleneck: simulated quadratic execution latency
    time.sleep(0.25)  # 250ms breach
    res = ""
    for i in range(n):
        res += str(i)
    return res
""",
        test_code="""
import solution

def test_performance_latency_threshold():
    res = solution.slow_string_aggregator(10)
    assert len(res) > 0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=5,
        expected_system_behavior="Flag via performance thresholds (latency > 200ms) with supporting profiling evidence",
    ),
    BenchmarkScenario(
        scenario_id="TX04-02",
        name="Simulated N+1 Query Bottleneck",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        module_code="""
import time

def fetch_orders_n_plus_one(user_ids: list) -> list:
    orders = []
    # Performance defect: simulated N+1 database roundtrips
    time.sleep(0.3)  # 300ms latency breach
    for u in user_ids:
        orders.append({"user": u, "order": "sample"})
    return orders
""",
        test_code="""
import solution

def test_performance_n_plus_one_latency():
    orders = solution.fetch_orders_n_plus_one([1, 2, 3, 4])
    assert len(orders) == 4
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=6,
        expected_system_behavior="Flag via performance thresholds with profiling evidence",
    ),
    BenchmarkScenario(
        scenario_id="TX04-03",
        name="Unmemoized Exponential Fibonacci",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        module_code="""
import time

def fibonacci_unmemoized(n: int) -> int:
    time.sleep(0.22)  # 220ms breach
    if n <= 1:
        return n
    return fibonacci_unmemoized(n - 1) + fibonacci_unmemoized(n - 2)
""",
        test_code="""
import solution

def test_fibonacci_performance_breach():
    val = solution.fibonacci_unmemoized(5)
    assert val == 5
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=3,
        expected_system_behavior="Flag via latency thresholds (>200ms)",
    ),

    # =========================================================================
    # Group 5: Duplicate / Regression Defect (Table 4: 10% proposed share)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="TX05-01",
        name="Re-introduced Discount Calculation Bug",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        module_code="""
def apply_promo_code(subtotal: float, code: str) -> float:
    # Regression defect: previously fixed discount logic broke again
    if code == "SAVE20":
        return subtotal - 5.0  # Should have been 20%
    return subtotal
""",
        test_code="""
import solution

def test_apply_promo_code_regression():
    assert solution.apply_promo_code(100.0, "SAVE20") == 80.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=4,
        expected_system_behavior="Detecting regression against prior test report history",
    ),
    BenchmarkScenario(
        scenario_id="TX05-02",
        name="Re-introduced NoneType Omission Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        module_code="""
def get_user_display_name(user: dict) -> str:
    # Regression defect: missing null-safe fallback previously present
    return user['profile']['display_name']
""",
        test_code="""
import solution

def test_get_user_display_name_null_safe_regression():
    # User missing profile dict
    try:
        name = solution.get_user_display_name({})
        assert name == "Anonymous"
    except KeyError:
        assert False, "Regression: Null profile threw KeyError"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=3,
        expected_system_behavior="Flagged as regression defect against prior baseline",
    ),

    # =========================================================================
    # Group 6: Non-Convergent & Semantic Drift (Table 4: 10% proposed share)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="TX06-01",
        name="Contradictory Requirements Non-Convergent By Design",
        scenario_group=BenchmarkScenarioGroup.NON_CONVERGENT_BY_DESIGN,
        module_code="""
def resolve_status(status_code: int) -> str:
    return "UNKNOWN"
""",
        test_code="""
import solution

def test_contradictory_requirement():
    # Demands contradictory outcomes that code regeneration cannot resolve
    assert solution.resolve_status(1) == "SUCCESS"
    assert solution.resolve_status(1) == "FAILURE"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        is_non_convergent_by_design=True,
        expected_system_behavior="Loop reaches iteration cap; module escalated to human review",
    ),
    BenchmarkScenario(
        scenario_id="TX07-01",
        name="Assertion Weakened to Trivially Satisfied (Semantic Drift)",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        module_code="""
def calculate_area(radius: float) -> float:
    # Defective area formula
    return 2 * 3.14159 * radius  # circumference instead of area!
""",
        # Weakened test suite that was altered from strict equality to "assert True"
        test_code="""
import solution

def test_calculate_area():
    res = solution.calculate_area(10.0)
    # Weakened assertion replacing strict check 'assert res == 314.159'
    assert True
""",
        has_defect=True,
        has_semantic_drift=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_system_behavior="Not accepted as converged; flagged for human validation due to assertion weakening",
    ),
]

# Backward-compatible reference to pilot scenarios
BENCHMARK_SCENARIOS = PILOT_BENCHMARK_SCENARIOS

# Import revised methodology scenarios
from app.benchmark.revised_dataset import REVISED_BENCHMARK_SCENARIOS

