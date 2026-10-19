"""
Phase 3 Development Dataset (40 Scenarios) for INTELISE Component 4.
Document ID: INTELISE-C4-PHASE3-DEV
Dataset Split: Development (Diagnostic improvement & rule calibration)
Evaluation Rigor: ZERO Ground-Truth Leakage.

Scenarios:
- Clean Controls & Safe Negative Controls: 8 (PH3-DEV-001 to PH3-DEV-008)
- Functional Bugs & Boundary Cases: 10 (PH3-DEV-009 to PH3-DEV-018)
- Security Vulnerabilities: 6 (PH3-DEV-019 to PH3-DEV-024)
- Performance Bottlenecks: 4 (PH3-DEV-025 to PH3-DEV-028)
- Integration & API Compatibility Defects: 4 (PH3-DEV-029 to PH3-DEV-032)
- Regression Defects: 4 (PH3-DEV-033 to PH3-DEV-036)
- Semantic Drift Cases: 2 (PH3-DEV-037 to PH3-DEV-038)
- Non-Convergent Repair-Loop Scenarios: 2 (PH3-DEV-039 to PH3-DEV-040)
"""
from typing import List
from app.benchmark.models import BenchmarkScenario, BenchmarkScenarioGroup
from app.schemas.common import DefectCategory


PHASE3_DEV_SCENARIOS: List[BenchmarkScenario] = [
    # =========================================================================
    # Group 1: Clean Controls & Safe Negative Controls (8 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-DEV-001",
        name="Matrix-Vector Linear Transformation",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="easy",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-001"],
        module_code="""
def matrix_vector_multiply(matrix: list[list[float]], vector: list[float]) -> list[float]:
    if not matrix or not vector:
        return []
    result = []
    for row in matrix:
        if len(row) != len(vector):
            raise ValueError("Dimension mismatch")
        result.append(sum(r * v for r, v in zip(row, vector)))
    return result
""",
        test_code="""
import solution
import pytest

def test_mv_multiplication():
    m = [[1.0, 2.0], [3.0, 4.0]]
    v = [2.0, 1.0]
    assert solution.matrix_vector_multiply(m, v) == [4.0, 10.0]

def test_empty():
    assert solution.matrix_vector_multiply([], [1.0]) == []

def test_mismatch():
    with pytest.raises(ValueError):
        solution.matrix_vector_multiply([[1.0, 2.0]], [1.0])
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-002",
        name="CSV Tokenizer with Quoted Strings",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-002"],
        module_code="""
def tokenize_csv_line(line: str) -> list[str]:
    tokens = []
    current = []
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ',' and not in_quotes:
            tokens.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    tokens.append("".join(current).strip())
    return tokens
""",
        test_code="""
import solution

def test_simple_csv():
    res = solution.tokenize_csv_line("apple, banana, cherry")
    assert res == ["apple", "banana", "cherry"]

def test_quoted_csv():
    res = solution.tokenize_csv_line('alpha, "beta, gamma", delta')
    assert res == ["alpha", "beta, gamma", "delta"]
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-003",
        name="Financial Banker's Rounding Calculator",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="easy",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-003"],
        module_code="""
from decimal import Decimal, ROUND_HALF_EVEN

def round_currency(amount: str, places: int = 2) -> str:
    d = Decimal(amount)
    fmt = Decimal("1." + "0" * places)
    rounded = d.quantize(fmt, rounding=ROUND_HALF_EVEN)
    return str(rounded)
""",
        test_code="""
import solution

def test_rounding_even():
    assert solution.round_currency("2.525") == "2.52"
    assert solution.round_currency("2.535") == "2.54"
    assert solution.round_currency("10.000") == "10.00"
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Clean execution; 0 defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-004",
        name="Safe Parameterized SQL Search (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-004"],
        module_code="""
class MockDb:
    def __init__(self):
        self.last_query = None
        self.last_params = None
    def execute(self, query: str, params: tuple):
        self.last_query = query
        self.last_params = params
        return [{"id": 1, "username": "alice"}]

def query_user_safely(db: MockDb, user_id: int):
    # Parameterized query - prevents CWE-89 SQL injection
    return db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
""",
        test_code="""
import solution

def test_safe_sql():
    db = solution.MockDb()
    res = solution.query_user_safely(db, 42)
    assert len(res) == 1
    assert db.last_params == (42,)
    assert "?" in db.last_query
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-005",
        name="Safe Subprocess List Execution (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-005"],
        module_code="""
import subprocess

def run_git_status(repo_dir: str):
    # Safe list arguments and shell=False - prevents CWE-78 command injection
    cmd = ["git", "-C", repo_dir, "status", "--porcelain"]
    return cmd
""",
        test_code="""
import solution

def test_safe_subprocess():
    cmd = solution.run_git_status("/tmp/safe_repo")
    assert cmd == ["git", "-C", "/tmp/safe_repo", "status", "--porcelain"]
    assert isinstance(cmd, list)
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-006",
        name="Safe Path Confinement with Basename (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-006"],
        module_code="""
import os

def build_safe_attachment_path(base_folder: str, filename: str) -> str:
    # Uses os.path.basename to strip directory traversal sequences
    safe_name = os.path.basename(filename)
    return os.path.join(base_folder, safe_name)
""",
        test_code="""
import solution

def test_safe_path():
    p = solution.build_safe_attachment_path("/var/uploads", "../../etc/passwd")
    assert p == os.path.join("/var/uploads", "passwd")
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-007",
        name="Safe Environment Secret Loader (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="easy",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-007"],
        module_code="""
import os

def get_database_password() -> str:
    # Retrieves secret from environment instead of hardcoding (prevents CWE-798)
    return os.environ.get("DB_PASSWORD", "default_dev_pass")
""",
        test_code="""
import solution
import os

def test_safe_secret_loading(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "prod_secret_token_1234")
    assert solution.get_database_password() == "prod_secret_token_1234"
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-008",
        name="Safe Math Literal Parsing (Negative Security Control)",
        scenario_group=BenchmarkScenarioGroup.CLEAN_CONTROL,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-008"],
        module_code="""
import ast

def evaluate_numeric_tuple(raw_str: str) -> tuple:
    # Safe literal parsing avoiding eval() - prevents CWE-95
    parsed = ast.literal_eval(raw_str)
    if not isinstance(parsed, tuple):
        raise TypeError("Expected tuple literal")
    return parsed
""",
        test_code="""
import solution
import pytest

def test_safe_literal():
    assert solution.evaluate_numeric_tuple("(1, 2, 3)") == (1, 2, 3)

def test_reject_arbitrary():
    with pytest.raises(Exception):
        solution.evaluate_numeric_tuple("__import__('os').system('ls')")
""",
        has_defect=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Safe negative control; 0 security defects reported",
    ),

    # =========================================================================
    # Group 2: Functional Defects & Boundary Cases (10 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-DEV-009",
        name="Off-by-One Pagination Page Index Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-009"],
        module_code="""
def paginate_records(records: list, page: int, per_page: int) -> list:
    # Defect: page is 1-based, but multiplying without decrement skips first page
    start = page * per_page
    return records[start : start + per_page]
""",
        test_code="""
import solution

def test_paginate_first_page():
    data = [1, 2, 3, 4, 5, 6]
    res = solution.paginate_records(data, page=1, per_page=2)
    assert res == [1, 2]
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=5,
        expected_system_behavior="Detect off-by-one assertion failure at line 5",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-010",
        name="Leap Year Century Boundary Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-010"],
        module_code="""
def is_leap_year(year: int) -> bool:
    # Defect: century years divisible by 100 are not leap unless divisible by 400
    if year % 4 == 0:
        return True
    return False
""",
        test_code="""
import solution

def test_century_years():
    assert solution.is_leap_year(2000) is True
    assert solution.is_leap_year(1900) is False
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on century leap year logic",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-011",
        name="Stack Pop Underflow Without Bounds Check",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-011"],
        module_code="""
class SafeStack:
    def __init__(self):
        self._items = []
    def push(self, item):
        self._items.append(item)
    def pop(self):
        # Defect: directly pops without checking empty, raising IndexError instead of returning None
        return self._items.pop()
""",
        test_code="""
import solution

def test_pop_empty():
    stack = solution.SafeStack()
    assert stack.pop() is None
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=9,
        expected_system_behavior="Detect IndexError runtime exception on empty stack pop",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-012",
        name="Discount Calculation Inverted Percentage Logic",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-012"],
        module_code="""
def apply_percentage_discount(price: float, discount_pct: float) -> float:
    # Defect: subtracts raw discount_pct instead of price * (discount_pct / 100.0)
    return round(price - discount_pct, 2)
""",
        test_code="""
import solution

def test_discount():
    assert solution.apply_percentage_discount(200.0, 10.0) == 180.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure in percentage discount calculation",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-013",
        name="Roman Numeral Subtractive Pair Defect (IX)",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-013"],
        module_code="""
def roman_to_int(s: str) -> int:
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
    total = 0
    for ch in s:
        # Defect: purely additive parser; misses subtractive pairs like IX -> 9
        total += values.get(ch, 0)
    return total
""",
        test_code="""
import solution

def test_roman_subtractive():
    assert solution.roman_to_int("IV") == 4
    assert solution.roman_to_int("IX") == 9
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=7,
        expected_system_behavior="Detect assertion failure on roman numeral subtractive parsing",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-014",
        name="Even-Length Median Integer Division Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-014"],
        module_code="""
def compute_median(numbers: list[float]) -> float:
    if not numbers:
        return 0.0
    s = sorted(numbers)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    # Defect: integer division truncates decimal average of two middle elements
    return float((s[n // 2 - 1] + s[n // 2]) // 2)
""",
        test_code="""
import solution

def test_median_even():
    assert solution.compute_median([1.0, 2.0, 3.0, 4.0]) == 2.5
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=10,
        expected_system_behavior="Detect assertion failure from integer division truncation in median",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-015",
        name="Binary Search Upper Bound Truncation Boundary Defect",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-015"],
        module_code="""
def binary_search(arr: list[int], target: int) -> int:
    # Defect: high initialized to len - 2, omitting search for the final element
    low, high = 0, len(arr) - 2
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
""",
        test_code="""
import solution

def test_search_last_element():
    # Last element 8 is missed because high = len(arr) - 2
    assert solution.binary_search([2, 5, 8], 8) == 2
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on binary search omitted last element",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-016",
        name="Fahrenheit to Celsius Conversion Sign Inversion",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="easy",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-016"],
        module_code="""
def fahrenheit_to_celsius(f: float) -> float:
    # Defect: adds 32 instead of subtracting 32
    return round((f + 32.0) * (5.0 / 9.0), 2)
""",
        test_code="""
import solution

def test_boiling():
    assert solution.fahrenheit_to_celsius(212.0) == 100.0

def test_freezing():
    assert solution.fahrenheit_to_celsius(32.0) == 0.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure from inverted sign in temperature conversion",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-017",
        name="Inclusive Date Range Filter Exclusive Boundary",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-017"],
        module_code="""
def filter_events_by_date(events: list[dict], start_day: int, end_day: int) -> list[dict]:
    # Defect: uses < end_day instead of <= end_day, omitting boundary events
    return [e for e in events if start_day <= e["day"] < end_day]
""",
        test_code="""
import solution

def test_inclusive_filter():
    events = [{"id": 1, "day": 10}, {"id": 2, "day": 20}]
    res = solution.filter_events_by_date(events, 10, 20)
    assert len(res) == 2
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure due to boundary omission in date filter",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-018",
        name="Phone Number Regex Missing String Anchors",
        scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requirement_ids=["REQ-DEV-018"],
        module_code=r"""
import re

def is_valid_phone(phone: str) -> bool:
    # Defect: missing ^ and $ anchors permits trailing arbitrary alphabetic text
    pattern = r"\+?[0-9]{10,12}"
    return bool(re.search(pattern, phone))
""",
        test_code=r"""
import solution

def test_reject_trailing_alpha():
    assert solution.is_valid_phone("+12345678901") is True
    assert solution.is_valid_phone("+12345678901INVALID") is False
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=7,
        expected_system_behavior="Detect assertion failure on unanchored regex phone validation",
    ),

    # =========================================================================
    # Group 3: Security Vulnerabilities (6 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-DEV-019",
        name="OS Command Injection via os.system (CWE-78)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="medium",
        provenance="cwe_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-019"],
        module_code="""
import os

def ping_host(host: str):
    # Vulnerability: Direct os.system invocation with unsanitized argument (CWE-78)
    return os.system("ping -c 1 " + host)
""",
        test_code="""
import solution

def test_ping_cmd():
    # Functional unit test passes command string
    res = solution.ping_host("127.0.0.1")
    assert res is not None
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-78",
        expected_line_number=6,
        expected_system_behavior="Detect CWE-78 OS command injection via AST static security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-020",
        name="SQL Injection via String Concatenation (CWE-89)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="medium",
        provenance="cwe_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-020"],
        module_code="""
class MockDbCursor:
    def execute(self, query: str):
        return [{"id": 1, "query": query}]

def fetch_user_record(cursor: MockDbCursor, user_id: str):
    # Vulnerability: Dynamic SQL string formatting (CWE-89)
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return cursor.execute(query)
""",
        test_code="""
import solution

def test_fetch_user():
    cursor = solution.MockDbCursor()
    res = solution.fetch_user_record(cursor, "admin")
    assert len(res) == 1
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-89",
        expected_line_number=8,
        expected_system_behavior="Detect CWE-89 SQL injection via AST static security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-021",
        name="Path Traversal File Read (CWE-22)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="medium",
        provenance="cwe_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-021"],
        module_code="""
def read_log_file(filename: str) -> str:
    # Vulnerability: Dynamic unconfined path concatenation (CWE-22)
    path = f"/var/logs/{filename}"
    with open(path, "r") as f:
        return f.read()
""",
        test_code="""
import solution
import pytest

def test_read_log(monkeypatch):
    # Mock open to verify functionality
    class MockFile:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return "log_entry"
    monkeypatch.setattr("builtins.open", lambda *a, **k: MockFile())
    assert solution.read_log_file("app.log") == "log_entry"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-22",
        expected_line_number=5,
        expected_system_behavior="Detect CWE-22 path traversal via AST static security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-022",
        name="Dynamic Expression Evaluation via eval (CWE-95)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="medium",
        provenance="cwe_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-022"],
        module_code="""
def evaluate_user_formula(formula: str) -> float:
    # Vulnerability: Unsafe dynamic code evaluation (CWE-95)
    return eval(formula)
""",
        test_code="""
import solution

def test_eval_formula():
    assert solution.evaluate_user_formula("10 + 20 * 2") == 50
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-95",
        expected_line_number=4,
        expected_system_behavior="Detect CWE-95 dynamic code evaluation via AST static security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-023",
        name="Hardcoded Secret API Token (CWE-798)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="easy",
        provenance="cwe_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-023"],
        module_code="""
def get_auth_header() -> dict:
    # Vulnerability: Hardcoded private API credential in source code (CWE-798)
    api_key = "live_secret_token_abcdef1234567890"
    return {"Authorization": f"Bearer {api_key}"}
""",
        test_code="""
import solution

def test_auth_header():
    h = solution.get_auth_header()
    assert "Bearer" in h["Authorization"]
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-798",
        expected_line_number=4,
        expected_system_behavior="Detect CWE-798 hardcoded credentials via AST static security scanner",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-024",
        name="Subprocess Invocation with shell=True (CWE-78)",
        scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
        difficulty="medium",
        provenance="cwe_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-024"],
        module_code="""
import subprocess

def compress_folder(folder_path: str):
    # Vulnerability: Subprocess with shell=True and string formatting (CWE-78)
    cmd = f"tar -czf backup.tar.gz {folder_path}"
    return subprocess.run(cmd, shell=True)
""",
        test_code="""
import solution
import subprocess

def test_compress_call(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: 0)
    assert solution.compress_folder("/tmp/data") == 0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,
        expected_cwe_id="CWE-78",
        expected_line_number=7,
        expected_system_behavior="Detect CWE-78 subprocess shell=True invocation via AST scanner",
    ),

    # =========================================================================
    # Group 4: Performance Bottlenecks (4 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-DEV-025",
        name="Quadratic String Concatenation in Loop",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requested_test_types=["performance"],
        requirement_ids=["REQ-DEV-025"],
        module_code="""
def build_large_payload(count: int) -> str:
    # Defect: Inefficient O(N^2) repeated string concatenation copying buffer
    result = ""
    for i in range(count):
        result = result + f"record_item_{i:04d}\\n"
    return result
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_payload_generation():
    res = solution.build_large_payload(35000)
    assert len(res) > 0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=6,
        expected_system_behavior="Breach 200ms latency SLA threshold and classify as performance bottleneck",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-026",
        name="Unmemoized Naive Recursive Fibonacci",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        difficulty="easy",
        provenance="curated_synthetic",
        split="dev",
        requested_test_types=["performance"],
        requirement_ids=["REQ-DEV-026"],
        module_code="""
def fibonacci(n: int) -> int:
    # Defect: Exponential O(2^N) recursion without memoization
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_fib_latency():
    # n=32 takes ~300ms without memoization
    res = solution.fibonacci(32)
    assert res == 2178309
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=6,
        expected_system_behavior="Breach 200ms latency SLA threshold due to exponential recursion",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-027",
        name="Quadratic Pairwise Distance Calculation",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        difficulty="hard",
        provenance="curated_synthetic",
        split="dev",
        requested_test_types=["performance"],
        requirement_ids=["REQ-DEV-027"],
        module_code="""
def count_close_pairs(points: list[tuple[float, float]], threshold: float) -> int:
    # Defect: O(N^2) exhaustive pairwise comparison over large list
    close_count = 0
    n = len(points)
    for i in range(n):
        for j in range(i + 1, n):
            dx = points[i][0] - points[j][0]
            dy = points[i][1] - points[j][1]
            if (dx * dx + dy * dy) ** 0.5 < threshold:
                close_count += 1
    return close_count
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_pairwise_latency():
    pts = [(float(i % 100), float((i * 7) % 100)) for i in range(2500)]
    count = solution.count_close_pairs(pts, 0.5)
    assert count >= 0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=8,
        expected_system_behavior="Breach 200ms latency SLA threshold due to nested O(N^2) comparison",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-028",
        name="Unindexed Linear Lookup Inside Iteration Loop",
        scenario_group=BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
        difficulty="medium",
        provenance="curated_synthetic",
        split="dev",
        requested_test_types=["performance"],
        requirement_ids=["REQ-DEV-028"],
        module_code="""
def enrich_transactions(transactions: list[dict], user_records: list[dict]) -> list[dict]:
    # Defect: Repeated linear scanning of user_records list instead of hash dict
    enriched = []
    for tx in transactions:
        uid = tx["user_id"]
        found_name = None
        for u in user_records:
            if u["id"] == uid:
                found_name = u["name"]
                break
        enriched.append({**tx, "user_name": found_name})
    return enriched
""",
        test_code="""
import solution
import pytest

@pytest.mark.performance
def test_unindexed_enrichment():
    users = [{"id": i, "name": f"User_{i}"} for i in range(3000)]
    txs = [{"tx_id": i, "user_id": (i * 3) % 3000} for i in range(2000)]
    res = solution.enrich_transactions(txs, users)
    assert len(res) == 2000
""",
        has_defect=True,
        expected_defect_category=DefectCategory.PERFORMANCE_BOTTLENECK,
        expected_line_number=9,
        expected_system_behavior="Breach 200ms latency SLA threshold due to repeated linear scanning",
    ),

    # =========================================================================
    # Group 5: Integration & API Compatibility Defects (4 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-DEV-029",
        name="REST Envelope Response Format Mismatch",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="medium",
        provenance="api_contract_spec",
        split="dev",
        requirement_ids=["REQ-DEV-029"],
        module_code="""
def format_api_items_response(items: list[dict]) -> dict:
    # Defect: API contract specifies envelope {'status': 'success', 'data': [...]}
    # but implementation returns raw items array directly
    return items  # Contract requires dict with 'data' envelope!
""",
        test_code="""
import solution

def test_api_envelope_contract():
    items = [{"id": 1, "title": "First"}]
    res = solution.format_api_items_response(items)
    assert isinstance(res, dict)
    assert res.get("status") == "success"
    assert res.get("data") == items
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=5,
        expected_system_behavior="Detect assertion failure on API contract envelope structure",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-030",
        name="HTTP Error Status Code Contract Violation (200 OK on Error)",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="medium",
        provenance="api_contract_spec",
        split="dev",
        requirement_ids=["REQ-DEV-030"],
        module_code="""
def handle_resource_request(resource_id: str, catalog: dict) -> tuple[int, dict]:
    # Defect: API contract requires (404, {'error': 'not found'}) when missing,
    # but handler returns (200, {'error': 'not found'})
    if resource_id not in catalog:
        return 200, {"error": "Not Found"}
    return 200, {"data": catalog[resource_id]}
""",
        test_code="""
import solution

def test_not_found_status_code():
    code, body = solution.handle_resource_request("missing_item", {})
    assert code == 404
    assert "error" in body
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=6,
        expected_system_behavior="Detect assertion failure on HTTP status code contract",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-031",
        name="Timestamp Serialization Epoch Float vs ISO-8601 Mismatch",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="easy",
        provenance="api_contract_spec",
        split="dev",
        requirement_ids=["REQ-DEV-031"],
        module_code="""
import time

def serialize_audit_event(event_name: str) -> dict:
    # Defect: Downstream integration expects ISO-8601 string 'created_at',
    # but returns raw unix float epoch
    return {
        "event": event_name,
        "created_at": time.time(),
    }
""",
        test_code="""
import solution

def test_timestamp_is_iso_string():
    ev = solution.serialize_audit_event("USER_LOGIN")
    assert isinstance(ev["created_at"], str)
    assert "T" in ev["created_at"]
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=8,
        expected_system_behavior="Detect assertion failure from type mismatch in timestamp serialization",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-032",
        name="Webhook Dispatcher Missing Authorization Header",
        scenario_group=BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        difficulty="medium",
        provenance="api_contract_spec",
        split="dev",
        requirement_ids=["REQ-DEV-032"],
        module_code="""
def build_webhook_dispatch_request(url: str, payload: dict, token: str) -> dict:
    # Defect: Fails to attach mandatory 'X-Webhook-Token' header in request dict
    return {
        "url": url,
        "headers": {"Content-Type": "application/json"},
        "json": payload,
    }
""",
        test_code="""
import solution

def test_webhook_header_present():
    req = solution.build_webhook_dispatch_request("https://api.test/webhook", {"id": 1}, "secret_token")
    assert "X-Webhook-Token" in req["headers"]
    assert req["headers"]["X-Webhook-Token"] == "secret_token"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect assertion failure on missing mandatory webhook header",
    ),

    # =========================================================================
    # Group 6: Regression Defects (4 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-DEV-033",
        name="User Profile Serializer Field Renaming Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="medium",
        provenance="regression_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-033"],
        module_code="""
def serialize_user_profile(user: dict) -> dict:
    # Regression: Renamed 'full_name' to 'display_name' breaking legacy consumer expectation
    return {
        "id": user["id"],
        "display_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
    }
""",
        test_code="""
import solution

def test_legacy_full_name_contract():
    u = {"id": 10, "first_name": "John", "last_name": "Doe"}
    res = solution.serialize_user_profile(u)
    # Legacy consumer requires 'full_name' key
    assert "full_name" in res
    assert res["full_name"] == "John Doe"
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=5,
        expected_system_behavior="Detect regression in user profile serializer key",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-034",
        name="Tax Surcharge Calculation Zero-Rated Items Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="medium",
        provenance="regression_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-034"],
        module_code="""
def calculate_item_tax(subtotal: float, is_zero_rated: bool, surcharge: float = 0.0) -> float:
    # Regression: Adding surcharge logic mistakenly applied fixed surcharge to zero_rated items
    if is_zero_rated:
        return surcharge  # Should remain 0.0!
    return round(subtotal * 0.15 + surcharge, 2)
""",
        test_code="""
import solution

def test_zero_rated_tax_regression():
    tax = solution.calculate_item_tax(100.0, is_zero_rated=True, surcharge=5.0)
    assert tax == 0.0
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=5,
        expected_system_behavior="Detect regression on zero-rated tax calculation surcharge",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-035",
        name="Multi-Tenant Cache Key Collision Regression",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="hard",
        provenance="regression_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-035"],
        module_code="""
def build_cache_key(tenant_id: str, resource_type: str, item_id: str) -> str:
    # Regression: Refactoring dropped tenant_id prefix, creating cross-tenant collisions
    return f"{resource_type}:{item_id}"
""",
        test_code="""
import solution

def test_tenant_isolation_cache_key():
    k1 = solution.build_cache_key("tenant_a", "order", "101")
    k2 = solution.build_cache_key("tenant_b", "order", "101")
    assert k1 != k2
    assert "tenant_a" in k1
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=4,
        expected_system_behavior="Detect regression in cache key tenant isolation",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-036",
        name="Sort Stability Regression with Inverted Secondary Ordering",
        scenario_group=BenchmarkScenarioGroup.REGRESSION,
        difficulty="medium",
        provenance="regression_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-036"],
        module_code="""
def sort_items_by_priority(items: list[dict]) -> list[dict]:
    # Regression: Priority bucket grouping mistakenly prepends items, inverting secondary FIFO order
    buckets = {}
    for item in items:
        p = item["priority"]
        buckets.setdefault(p, []).insert(0, item)
    res = []
    for p in sorted(buckets.keys(), reverse=True):
        res.extend(buckets[p])
    return res
""",
        test_code="""
import solution

def test_secondary_ordering_stability():
    items = [
        {"id": "A", "priority": 1},
        {"id": "B", "priority": 1},
        {"id": "C", "priority": 2},
    ]
    res = solution.sort_items_by_priority(items)
    p1_items = [i["id"] for i in res if i["priority"] == 1]
    # Regression check: A must precede B in secondary FIFO order
    assert p1_items == ["A", "B"]
""",
        has_defect=True,
        expected_defect_category=DefectCategory.REGRESSION,
        expected_line_number=8,
        expected_system_behavior="Detect regression failure on secondary ordering inversion",
    ),

    # =========================================================================
    # Group 7: Semantic Drift Cases (2 Scenarios: 1 Positive Drift, 1 Negative Control)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-DEV-037",
        name="Positive Drift: Assertion Weakened to Nullity Check",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        difficulty="medium",
        provenance="semantic_drift_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-037"],
        module_code="""
def calculate_compound_interest(principal: float, rate: float, periods: int) -> float:
    # Defective formula: simple interest instead of compound (1 + rate)^periods
    return round(principal * (1.0 + rate * periods), 2)
""",
        original_test_code="""
import solution

def test_compound_interest():
    res = solution.calculate_compound_interest(1000.0, 0.05, 3)
    assert res == 1157.63  # Strict compound value
""",
        candidate_test_code="""
import solution

def test_compound_interest():
    res = solution.calculate_compound_interest(1000.0, 0.05, 3)
    # Weakened assertion: replaced exact value with is not None
    assert res is not None
""",
        test_code="""
import solution

def test_compound_interest():
    res = solution.calculate_compound_interest(1000.0, 0.05, 3)
    assert res is not None
""",
        has_defect=True,
        has_semantic_drift=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Detect semantic drift (assertion weakening) and block superficial convergence",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-038",
        name="Negative Drift Control: Variable Assignment Refactoring",
        scenario_group=BenchmarkScenarioGroup.SEMANTIC_DRIFT,
        difficulty="medium",
        provenance="semantic_drift_seeded",
        split="dev",
        requirement_ids=["REQ-DEV-038"],
        module_code="""
def calculate_area(length: float, width: float) -> float:
    return length * width
""",
        original_test_code="""
import solution

def test_area():
    assert solution.calculate_area(5.0, 4.0) == 20.0
""",
        candidate_test_code="""
import solution

def test_area():
    area = solution.calculate_area(5.0, 4.0)
    assert area == 20.0
""",
        test_code="""
import solution

def test_area():
    area = solution.calculate_area(5.0, 4.0)
    assert area == 20.0
""",
        has_defect=False,
        has_semantic_drift=False,
        expected_defect_category=DefectCategory.UNKNOWN,
        expected_system_behavior="Identify as clean refactoring; no semantic drift detected",
    ),

    # =========================================================================
    # Group 8: Non-Convergent Repair-Loop Scenarios (2 Scenarios)
    # =========================================================================
    BenchmarkScenario(
        scenario_id="PH3-DEV-039",
        name="Contradictory Requirements Repair Oscillation",
        scenario_group=BenchmarkScenarioGroup.NON_CONVERGENT_BY_DESIGN,
        difficulty="hard",
        provenance="repair_loop_seeded",
        split="dev",
        is_repair_loop_scenario=True,
        requirement_ids=["REQ-DEV-039-A", "REQ-DEV-039-B"],
        module_code="""
def format_phone_international(phone: str) -> str:
    # Initial defective version
    return phone.strip()
""",
        test_code="""
import solution

def test_req_a():
    # REQ-A expects format with plus prefix
    assert solution.format_phone_international("1234567890") == "+1234567890"

def test_req_b():
    # REQ-B expects format with 00 prefix
    assert solution.format_phone_international("1234567890") == "001234567890"
""",
        repair_candidate_patches=[
            # Patch 1 satisfies REQ-A, breaks REQ-B
            """
def format_phone_international(phone: str) -> str:
    return "+" + phone.strip()
""",
            # Patch 2 satisfies REQ-B, breaks REQ-A
            """
def format_phone_international(phone: str) -> str:
    return "00" + phone.strip()
""",
            # Patch 3 flips back to REQ-A
            """
def format_phone_international(phone: str) -> str:
    return "+" + phone.strip()
""",
        ],
        has_defect=True,
        is_non_convergent_by_design=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=4,
        expected_system_behavior="Exhaust 3 repair iterations without convergence and escalate to human governance",
    ),

    BenchmarkScenario(
        scenario_id="PH3-DEV-040",
        name="Persistent Defect Cap Exhaustion Repair Loop",
        scenario_group=BenchmarkScenarioGroup.NON_CONVERGENT_BY_DESIGN,
        difficulty="hard",
        provenance="repair_loop_seeded",
        split="dev",
        is_repair_loop_scenario=True,
        requirement_ids=["REQ-DEV-040"],
        module_code="""
def complex_state_machine_transition(state: str, event: str) -> str:
    return "ERROR"
""",
        test_code="""
import solution

def test_state_flow():
    assert solution.complex_state_machine_transition("IDLE", "START") == "RUNNING"
    assert solution.complex_state_machine_transition("RUNNING", "STOP") == "STOPPED"
""",
        repair_candidate_patches=[
            # Candidate 1: only handles START
            """
def complex_state_machine_transition(state: str, event: str) -> str:
    if event == "START": return "RUNNING"
    return "ERROR"
""",
            # Candidate 2: handles STOP but breaks START
            """
def complex_state_machine_transition(state: str, event: str) -> str:
    if event == "STOP": return "STOPPED"
    return "ERROR"
""",
            # Candidate 3: still invalid
            """
def complex_state_machine_transition(state: str, event: str) -> str:
    return "INVALID"
""",
        ],
        has_defect=True,
        is_non_convergent_by_design=True,
        expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
        expected_line_number=3,
        expected_system_behavior="Exhaust max 3 repair iterations and trigger escalation",
    ),
]
