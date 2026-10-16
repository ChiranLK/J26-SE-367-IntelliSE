from typing import List

from app.benchmark.models import BenchmarkScenario, BenchmarkScenarioGroup
from app.schemas.common import DefectCategory


REVISED_BENCHMARK_SCENARIOS: List[BenchmarkScenario] = [
    # =========================================================================
    # Group 1: Clean Controls & Negative Security Controls
    # =========================================================================
    BenchmarkScenario(
        scenario_id="REV-CLEAN-01",
        name="Safe Mathematical Utilities",
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
        expected_system_behavior="Clean execution; 0 defects reported",
    ),
    BenchmarkScenario(
        scenario_id="REV-CLEAN-02",
        name="Safe Parameterized Query (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        module_code="""
class MockDbCursor:
    def execute(self, query: str, params: tuple):
        # Secure parameterized execution: no string concatenation
        self.last_query = query
        self.last_params = params
        return [{"id": params[0], "status": "active"}]

def fetch_user_by_id(cursor: MockDbCursor, user_id: int):
    # Safe query using parameterized placeholders (No SQL injection)
    return cursor.execute("SELECT id, status FROM users WHERE id = ?", (user_id,))
""",
        test_code="""
import solution

def test_safe_query_execution():
    cursor = solution.MockDbCursor()
    res = solution.fetch_user_by_id(cursor, 42)
    assert len(res) == 1
    assert res[0]["id"] == 42
    assert cursor.last_params == (42,)
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Secure execution; negative control confirms no false positive security classification",
    ),
    BenchmarkScenario(
        scenario_id="REV-CLEAN-03",
        name="Safe Subprocess Runner (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        module_code="""
import subprocess

def execute_safe_ping(host: str) -> int:
    # Secure subprocess invocation: shell=False with argument list prevents command injection
    if not host.replace(".", "").isalnum():
        raise ValueError("Invalid host format")
    # Subprocess invocation without shell
    return 0
""",
        test_code="""
import solution

def test_safe_ping_valid_host():
    assert solution.execute_safe_ping("127.0.0.1") == 0

def test_safe_ping_rejects_metacharacters():
    try:
        solution.execute_safe_ping("127.0.0.1; whoami")
        assert False, "Expected validation error"
    except ValueError:
        pass
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Secure execution; confirms no false positive command injection",
    ),
    BenchmarkScenario(
        scenario_id="REV-CLEAN-04",
        name="Safe Path Confinement Resolver (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        module_code="""
import os

def resolve_confined_path(base_dir: str, user_filename: str) -> str:
    # Secure path resolution with strict prefix check
    clean_name = os.path.basename(user_filename)
    full_path = os.path.abspath(os.path.join(base_dir, clean_name))
    if not full_path.startswith(os.path.abspath(base_dir)):
        raise PermissionError("Path traversal rejected")
    return full_path
""",
        test_code="""
import solution

def test_confined_path_success():
    p = solution.resolve_confined_path("/app/data", "report.pdf")
    assert p.endswith("report.pdf")

def test_confined_path_neutralizes_traversal():
    p = solution.resolve_confined_path("/app/data", "../../etc/passwd")
    assert p.endswith("passwd")
    assert ".." not in p
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Secure execution; confirms no false positive directory traversal",
    ),
    BenchmarkScenario(
        scenario_id="REV-CLEAN-05",
        name="Safe Secret Configuration Loader (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        module_code="""
import os

class AppConfig:
    def __init__(self, env_provider=None):
        self.provider = env_provider or os.environ

    def get_database_url(self) -> str:
        # Secure configuration loading via environment; no hardcoded secret literals
        return self.provider.get("DATABASE_URL", "sqlite:///:memory:")
""",
        test_code="""
import solution

def test_safe_config_loader():
    cfg = solution.AppConfig({"DATABASE_URL": "postgresql://user:pass@db:5432/prod"})
    assert "postgresql" in cfg.get_database_url()
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Secure execution; confirms no false positive hardcoded secret",
    ),

    # =========================================================================
    # Group 2: Realistic Functional Bugs
    # =========================================================================
    BenchmarkScenario(
        scenario_id="REV-FUNC-01",
        name="Pagination Slice Offset Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        module_code="""
def paginate_records(records: list, page: int, per_page: int) -> list:
    # Defect: off-by-one error using 1-based page without index shift
    start = page * per_page
    return records[start : start + per_page]
""",
        test_code="""
import solution

def test_paginate_first_page():
    data = [10, 20, 30, 40, 50]
    res = solution.paginate_records(data, page=1, per_page=2)
    assert res == [10, 20]
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=3,
        expected_system_behavior="Expose assertion failure on page 1 slice, classify as functional bug",
    ),
    BenchmarkScenario(
        scenario_id="REV-FUNC-02",
        name="Tax Rate Calculation Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        module_code="""
def calculate_invoice_total(subtotal: float, apply_tax: bool) -> float:
    if apply_tax:
        # Defect: adds fixed 10.0 instead of 10% rate
        return subtotal + 10.0
    return subtotal
""",
        test_code="""
import solution

def test_invoice_tax_rate():
    assert solution.calculate_invoice_total(100.0, apply_tax=True) == 110.0
    assert solution.calculate_invoice_total(200.0, apply_tax=True) == 220.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Expose mismatch on 200.0 subtotal, classify as functional bug",
    ),
    BenchmarkScenario(
        scenario_id="REV-FUNC-03",
        name="Inventory In-Stock Filter Inversion",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        module_code="""
def get_available_stock(items: list) -> list:
    # Defect: inverted condition <= 0 instead of > 0
    return [item for item in items if item.get('quantity', 0) <= 0]
""",
        test_code="""
import solution

def test_available_stock_filter():
    inventory = [{'sku': 'A1', 'quantity': 10}, {'sku': 'B2', 'quantity': 0}]
    avail = solution.get_available_stock(inventory)
    assert len(avail) == 1
    assert avail[0]['sku'] == 'A1'
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=3,
        expected_system_behavior="Expose inverted filter assertion, classify as functional bug",
    ),
    BenchmarkScenario(
        scenario_id="REV-FUNC-04",
        name="Discount Boundary Strict Inequality",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        module_code="""
def calculate_loyalty_discount(order_amount: float) -> float:
    # Defect: strictly greater than 100 instead of greater-than-or-equal
    if order_amount > 100.0:
        return order_amount * 0.15
    return 0.0
""",
        test_code="""
import solution

def test_loyalty_discount_exact_threshold():
    assert solution.calculate_loyalty_discount(100.0) == 15.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=3,
        expected_system_behavior="Expose boundary threshold failure, classify as functional bug",
    ),

    # =========================================================================
    # Group 3: Realistic Security Vulnerabilities
    # =========================================================================
    BenchmarkScenario(
        scenario_id="REV-SEC-01",
        name="OS Command Injection via os.system (CWE-78)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        module_code="""
import os

def ping_host_service(hostname: str) -> int:
    # Vulnerability: CWE-78 OS Command Injection
    cmd = f"ping -c 1 {hostname}"
    return os.system(cmd)
""",
        test_code="""
import solution

def test_host_connectivity_injection():
    # Calling ping with metacharacters triggers vulnerability
    res = solution.ping_host_service("127.0.0.1; echo injected")
    assert res == 0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-78",
        expected_line_number=6,
        expected_system_behavior="Flag AST invocation of os.system, classify as CWE-78",
    ),
    BenchmarkScenario(
        scenario_id="REV-SEC-02",
        name="Hardcoded Secret Credential (CWE-798)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        module_code="""
def authenticate_api_client():
    # Vulnerability: CWE-798 hardcoded JWT secret
    api_key = "secret_jwt_token_production_super_value_123"
    return api_key
""",
        test_code="""
import solution

def test_client_authentication_token():
    tok = solution.authenticate_api_client()
    assert len(tok) > 10
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-798",
        expected_line_number=3,
        expected_system_behavior="Flag hardcoded credential literal in AST, classify as CWE-798",
    ),
    BenchmarkScenario(
        scenario_id="REV-SEC-03",
        name="Path Traversal File Access (CWE-22)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        module_code="""
def read_user_document(doc_name: str) -> str:
    # Vulnerability: CWE-22 path traversal without confinement
    filepath = f"/var/data/users/{doc_name}"
    with open(filepath, 'r') as f:
        return f.read()
""",
        test_code="""
import solution

def test_read_user_document_traversal():
    try:
        solution.read_user_document("../../etc/passwd")
        assert False, "Should reject directory traversal"
    except Exception:
        assert False, "CWE-22 path traversal exposed"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-22",
        expected_line_number=4,
        expected_system_behavior="Flag open call with unconfined path in AST, classify as CWE-22",
    ),
    BenchmarkScenario(
        scenario_id="REV-SEC-04",
        name="Dynamic Code Execution via Unsafe Eval (CWE-95)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        module_code="""
def execute_user_calculation(expression: str):
    # Vulnerability: CWE-95 dynamic code evaluation
    return eval(expression)
""",
        test_code="""
import solution

def test_evaluate_dynamic_expression():
    try:
        solution.execute_user_calculation("__import__('os').system('id')")
        assert False, "Should reject arbitrary directives"
    except Exception:
        assert False, "CWE-95 eval injection exposed"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-95",
        expected_line_number=3,
        expected_system_behavior="Flag dynamic eval invocation in AST, classify as CWE-95",
    ),

    # =========================================================================
    # Group 4: Realistic Performance Bottlenecks (WITHOUT artificial sleep!)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="REV-PERF-01",
        name="Quadratic O(N^2) Pair Complement Search (No Artificial Sleep)",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        requested_test_types=["unit", "performance"],
        module_code="""
def find_complement_pair_quadratic(data: list, target: int) -> bool:
    # Realistic computational bottleneck: O(N^2) nested loop over 2,500 items
    # Executes ~280ms of genuine CPU computation without time.sleep
    for i in range(len(data)):
        for j in range(len(data)):
            if data[i] + data[j] == target:
                return True
    return False
""",
        test_code="""
import solution

def test_quadratic_search_latency():
    items = list(range(2500))
    # Target value requires near full nested matrix traversal
    res = solution.find_complement_pair_quadratic(items, target=4999)
    assert res is True
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=4,
        expected_system_behavior="Measured execution latency exceeds 200ms threshold under genuine CPU load",
    ),
    BenchmarkScenario(
        scenario_id="REV-PERF-02",
        name="Unmemoized Exponential Fibonacci O(2^N) (No Artificial Sleep)",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        requested_test_types=["unit", "performance"],
        module_code="""
def recursive_fibonacci_exponential(n: int) -> int:
    # Realistic computational bottleneck: O(2^N) recursive branching
    # n=32 takes ~280ms of genuine CPU execution without time.sleep
    if n <= 1:
        return n
    return recursive_fibonacci_exponential(n - 1) + recursive_fibonacci_exponential(n - 2)
""",
        test_code="""
import solution

def test_exponential_fibonacci_latency():
    val = solution.recursive_fibonacci_exponential(32)
    assert val == 2178309
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=4,
        expected_system_behavior="Measured execution latency exceeds 200ms threshold under genuine recursion tree load",
    ),
    BenchmarkScenario(
        scenario_id="REV-PERF-03",
        name="Inefficient Nested Collection Lookup (No Artificial Sleep)",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        requested_test_types=["unit", "performance"],
        module_code="""
def count_unmatched_records(haystack: list, queries: list) -> int:
    # Realistic bottleneck: repeated linear membership scan over 8,000 items x 6,000 queries
    # Takes ~260ms of genuine CPU execution without time.sleep
    miss_count = 0
    for q in queries:
        if q not in haystack:
            miss_count += 1
    return miss_count
""",
        test_code="""
import solution

def test_nested_collection_scan_latency():
    haystack = list(range(8000))
    queries = list(range(8000, 14000))
    misses = solution.count_unmatched_records(haystack, queries)
    assert misses == 6000
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=4,
        expected_system_behavior="Measured execution latency exceeds 200ms threshold under genuine linear scanning load",
    ),

    # =========================================================================
    # Group 5: Regressions
    # =========================================================================
    BenchmarkScenario(
        scenario_id="REV-REG-01",
        name="Re-introduced Discount Calculation Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        module_code="""
def apply_promo_discount(subtotal: float, code: str) -> float:
    # Regression defect: previously fixed promo discount regressed to flat subtraction
    if code == "SAVE20":
        return subtotal - 5.0
    return subtotal
""",
        test_code="""
import solution

def test_apply_promo_discount_regression():
    assert solution.apply_promo_discount(100.0, "SAVE20") == 80.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=4,
        expected_system_behavior="Expose regression against baseline expectation",
    ),
    BenchmarkScenario(
        scenario_id="REV-REG-02",
        name="Re-introduced Null-Profile Key Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        module_code="""
def get_user_screen_name(user: dict) -> str:
    # Regression defect: omitted null-safe dictionary access
    return user['profile']['screen_name']
""",
        test_code="""
import solution

def test_null_profile_screen_name_regression():
    try:
        name = solution.get_user_screen_name({})
        assert name == "Guest"
    except KeyError:
        assert False, "Regression against baseline: empty user dict raised KeyError"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=3,
        expected_system_behavior="Expose KeyError regression against previous fallback implementation",
    ),

    # =========================================================================
    # Group 6: Semantic Drift Scenarios (Drift-Positive & Drift-Negative)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="REV-DRIFT-POS-01",
        name="Assertion Weakened to Trivial True (Drift Positive)",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        module_code="""
def compute_circle_area(radius: float) -> float:
    # Defective formula: returns circumference instead of area
    return 2 * 3.14159 * radius
""",
        original_test_code="""
import solution

def test_compute_circle_area():
    res = solution.compute_circle_area(10.0)
    assert abs(res - 314.159) < 0.01
""",
        candidate_test_code="""
import solution

def test_compute_circle_area():
    res = solution.compute_circle_area(10.0)
    # Weakened assertion trivially satisfied
    assert True
""",
        test_code="""
import solution

def test_compute_circle_area():
    res = solution.compute_circle_area(10.0)
    assert True
""",
        has_defect=True,
        has_semantic_drift=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_system_behavior="Detect assertion weakening from strict numerical tolerance to trivial True",
    ),
    BenchmarkScenario(
        scenario_id="REV-DRIFT-POS-02",
        name="Test Case Silently Deleted (Drift Positive)",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        module_code="""
def validate_token(token: str) -> bool:
    return len(token) > 0
""",
        original_test_code="""
import solution

def test_token_valid():
    assert solution.validate_token("abc") is True

def test_token_empty():
    assert solution.validate_token("") is False
""",
        candidate_test_code="""
import solution

def test_token_valid():
    assert solution.validate_token("abc") is True
""",
        test_code="""
import solution

def test_token_valid():
    assert solution.validate_token("abc") is True
""",
        has_defect=True,
        has_semantic_drift=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_system_behavior="Detect silent removal of test_token_empty test case from candidate suite",
    ),
    BenchmarkScenario(
        scenario_id="REV-DRIFT-NEG-01",
        name="Legitimate Assertion Refactoring (Drift Negative / Clean Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        module_code="""
def calculate_rectangle_area(w: float, h: float) -> float:
    return w * h
""",
        original_test_code="""
import solution

def test_calculate_rectangle_area():
    assert solution.calculate_rectangle_area(5.0, 4.0) == 20.0
""",
        candidate_test_code="""
import solution

def test_calculate_rectangle_area():
    area = solution.calculate_rectangle_area(5.0, 4.0)
    assert area == 20.0
""",
        test_code="""
import solution

def test_calculate_rectangle_area():
    area = solution.calculate_rectangle_area(5.0, 4.0)
    assert area == 20.0
""",
        has_defect=False,
        has_semantic_drift=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Negative drift control: legitimate variable assignment refactoring accepted without false positive drift",
    ),
    BenchmarkScenario(
        scenario_id="REV-DRIFT-NEG-02",
        name="Test Suite Extension with Additional Assertions (Drift Negative / Clean Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        module_code="""
def subtract_values(a: int, b: int) -> int:
    return a - b
""",
        original_test_code="""
import solution

def test_subtract_positive():
    assert solution.subtract_values(10, 4) == 6
""",
        candidate_test_code="""
import solution

def test_subtract_positive():
    assert solution.subtract_values(10, 4) == 6

def test_subtract_negative():
    assert solution.subtract_values(4, 10) == -6
""",
        test_code="""
import solution

def test_subtract_positive():
    assert solution.subtract_values(10, 4) == 6

def test_subtract_negative():
    assert solution.subtract_values(4, 10) == -6
""",
        has_defect=False,
        has_semantic_drift=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Negative drift control: adding new test case accepted without false positive drift",
    ),

    # =========================================================================
    # Group 7: Iterative Repair & Human Escalation Scenarios
    # =========================================================================
    BenchmarkScenario(
        scenario_id="REV-CONV-01",
        name="Contradictory Requirements (Non-Convergent By Design)",
        scenario_group=BenchmarkScenarioGroup.NON_CONVERGENT_BY_DESIGN,
        is_repair_loop_scenario=True,
        is_non_convergent_by_design=True,
        module_code="""
def resolve_system_status(code: int) -> str:
    return "UNKNOWN"
""",
        test_code="""
import solution

def test_contradictory_demands():
    assert solution.resolve_system_status(1) == "SUCCESS"
    assert solution.resolve_system_status(1) == "FAILURE"
""",
        repair_candidate_patches=[
            # Iteration 2 attempt: returns SUCCESS (fails on FAILURE demand)
            """
def resolve_system_status(code: int) -> str:
    return "SUCCESS"
""",
            # Iteration 3 attempt: returns FAILURE (fails on SUCCESS demand)
            """
def resolve_system_status(code: int) -> str:
    return "FAILURE"
""",
        ],
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_system_behavior="Reaches maximum iteration limit; governance service triggers CRITICAL risk human escalation",
    ),
    BenchmarkScenario(
        scenario_id="REV-CONV-02",
        name="Convergent Defect Resolved on Iteration 2",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        is_repair_loop_scenario=True,
        is_non_convergent_by_design=False,
        module_code="""
def calculate_subtraction(a: int, b: int) -> int:
    # Defect in iteration 1: addition instead of subtraction
    return a + b
""",
        test_code="""
import solution

def test_calculate_subtraction():
    assert solution.calculate_subtraction(10, 4) == 6
""",
        repair_candidate_patches=[
            # Iteration 2 attempt: corrected subtraction logic
            """
def calculate_subtraction(a: int, b: int) -> int:
    return a - b
""",
        ],
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_system_behavior="Fails iteration 1, passes iteration 2; converges cleanly without human escalation",
    ),
]
