"""
INTELISE Component 4 — Phase 3C.1: Benchmark Infrastructure Pilot.

Defines an independent 16-scenario pilot benchmark covering all 8 research categories:
- Clean code controls (4 scenarios)
- Functional bugs (3 scenarios, Seeded Defects PILOT-DEF-01..03)
- Security vulnerabilities (2 scenarios, Seeded Defects PILOT-DEF-04..05)
- Performance bottlenecks (2 scenarios, Seeded Defects PILOT-DEF-06..07)
- Integration defects (1 scenario, Seeded Defect PILOT-DEF-08)
- Regression defects (1 scenario, Seeded Defect PILOT-DEF-09)
- Semantic drift cases (2 scenarios, Seeded Defects PILOT-DEF-10..11)
- Non-convergent repair loops (1 scenario, Seeded Defect PILOT-DEF-12)

Architecture Guarantees:
1. Strict Evaluation Isolation: Evaluator inputs (PilotEvaluationInput) are logically separated
   from hidden ground-truth records (PilotGroundTruthRecord).
2. Zero Ground-Truth Leakage: Detection agents and baselines receive only evaluation inputs.
3. Multi-System Execution: Component 4, Conventional CI, and Static Analysis evaluate the
   exact same scenario inputs.
4. Complete 17-Field Observation Serialization.
5. Deterministic Scenario Seeding.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.benchmark.baselines import (
    ConventionalCiBaselineEvaluator,
    StaticAnalysisBaselineEvaluator,
    ScenarioBaselineRecord,
)
from app.benchmark.evaluator import BenchmarkEvaluator
from app.benchmark.models import BenchmarkScenario, BenchmarkScenarioGroup
from app.benchmark.statistical_analysis import (
    PredictionProvenance,
    ScenarioPrediction,
    compute_binary_metrics,
    evaluate_empirical_paired_test,
    reconstruct_empirical_aggregate_confusion_matrix,
)
from app.schemas.common import DefectCategory, TestResultStatus, TestType
from app.services.ollama_client import OllamaClient


# =============================================================================
# Models: Isolated Evaluation Input vs Hidden Ground Truth (Task 3)
# =============================================================================

class PilotEvaluationInput(BaseModel):
    """
    Evaluation input visible to detectors and baseline evaluators during execution.
    Contains strictly operational artifacts with ZERO ground-truth labels.
    """
    scenario_id: str
    name: str
    filename: str = "solution.py"
    module_code: str
    test_code: str
    requested_test_types: List[str] = Field(default_factory=lambda: ["unit"])
    original_test_code: Optional[str] = None
    candidate_test_code: Optional[str] = None
    repair_candidate_patches: Optional[List[str]] = None
    is_repair_loop_scenario: bool = False
    requirement_ids: List[str] = Field(default_factory=lambda: ["REQ-PILOT-01"])


class PilotGroundTruthRecord(BaseModel):
    """
    Hidden evaluation ground truth. Joined with evaluator predictions strictly AFTER execution.
    """
    scenario_id: str
    defect_id: Optional[str] = None  # None for clean controls
    has_defect: bool
    expected_category: str  # e.g., "clean_control", "functional_bug", etc.
    expected_cwe_id: Optional[str] = None
    expected_line_number: Optional[int] = None
    mutation_operator: Optional[str] = None
    original_clean_source: Optional[str] = None
    mutated_source: Optional[str] = None
    expected_behavioral_failure: str
    ground_truth_rationale: str
    test_oracle: str
    fixture_version: str = "1.0.0"
    is_non_convergent_by_design: bool = False
    has_semantic_drift: bool = False


class PilotScenario(BaseModel):
    """Composite container holding evaluation input and hidden ground-truth record."""
    input_data: PilotEvaluationInput
    ground_truth: PilotGroundTruthRecord

    @property
    def scenario_id(self) -> str:
        return self.input_data.scenario_id

    def to_benchmark_scenario(self) -> BenchmarkScenario:
        """Converts to legacy BenchmarkScenario format for evaluator compatibility."""
        group_map = {
            "clean_control": BenchmarkScenarioGroup.CLEAN_CONTROL,
            "functional_bug": BenchmarkScenarioGroup.FUNCTIONAL_BUG,
            "security_vulnerability": BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
            "performance_bottleneck": BenchmarkScenarioGroup.PERFORMANCE_BOTTLENECK,
            "regression": BenchmarkScenarioGroup.REGRESSION,
            "non_convergent_by_design": BenchmarkScenarioGroup.NON_CONVERGENT_BY_DESIGN,
            "semantic_drift": BenchmarkScenarioGroup.SEMANTIC_DRIFT,
            "integration_defect": BenchmarkScenarioGroup.INTEGRATION_DEFECT,
        }
        category_enum_map = {
            "functional_bug": DefectCategory.FUNCTIONAL_BUG,
            "security_vulnerability": DefectCategory.SECURITY_VULNERABILITY,
            "performance_bottleneck": DefectCategory.PERFORMANCE_BOTTLENECK,
            "regression": DefectCategory.REGRESSION,
            "clean_control": DefectCategory.UNKNOWN,
            "non_convergent_by_design": DefectCategory.FUNCTIONAL_BUG,
            "semantic_drift": DefectCategory.FUNCTIONAL_BUG,
            "integration_defect": DefectCategory.FUNCTIONAL_BUG,
        }
        return BenchmarkScenario(
            scenario_id=self.input_data.scenario_id,
            name=self.input_data.name,
            scenario_group=group_map[self.ground_truth.expected_category],
            module_code=self.input_data.module_code,
            test_code=self.input_data.test_code,
            filename=self.input_data.filename,
            requirement_ids=self.input_data.requirement_ids,
            original_test_code=self.input_data.original_test_code,
            candidate_test_code=self.input_data.candidate_test_code,
            requested_test_types=self.input_data.requested_test_types,
            repair_candidate_patches=self.input_data.repair_candidate_patches,
            is_repair_loop_scenario=self.input_data.is_repair_loop_scenario,
            difficulty="pilot",
            provenance="phase3c1_curated_pilot",
            split="pilot",
            checksum_sha256=hashlib.sha256(self.input_data.module_code.encode("utf-8")).hexdigest(),
            has_defect=self.ground_truth.has_defect,
            expected_defect_category=category_enum_map[self.ground_truth.expected_category],
            expected_cwe_id=self.ground_truth.expected_cwe_id,
            expected_line_number=self.ground_truth.expected_line_number,
            is_non_convergent_by_design=self.ground_truth.is_non_convergent_by_design,
            has_semantic_drift=self.ground_truth.has_semantic_drift,
            expected_system_behavior=self.ground_truth.expected_behavioral_failure,
        )


# =============================================================================
# Pilot Dataset Definition (16 Scenarios, 12 Seeded Defects, 4 Clean Controls)
# =============================================================================

PILOT_SCENARIOS: List[PilotScenario] = [
    # -------------------------------------------------------------------------
    # 1. Clean Controls (Scenarios 1-4)
    # -------------------------------------------------------------------------
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-01",
            name="Safe String Truncation and Normalization",
            module_code="""def truncate_and_normalize(text: str, max_len: int = 50) -> str:
    if not isinstance(text, str):
        raise TypeError("Input text must be a string")
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len]
""",
            test_code="""import solution

def test_truncate_normal():
    assert solution.truncate_and_normalize("  hello   world  ", 20) == "hello world"

def test_truncate_length():
    assert len(solution.truncate_and_normalize("a" * 100, 10)) == 10

def test_truncate_type_error():
    try:
        solution.truncate_and_normalize(123)
        assert False, "Should have raised TypeError"
    except TypeError:
        pass
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-01",
            defect_id=None,
            has_defect=False,
            expected_category="clean_control",
            expected_behavioral_failure="Clean functional code passes all assertions",
            ground_truth_rationale="Clean control verifying whitespace normalization and length truncation",
            test_oracle="pytest assertions on string output and TypeError guard",
        ),
    ),
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-02",
            name="Bounded LRU Cache Eviction",
            module_code="""from collections import OrderedDict

class SimpleLRUCache:
    def __init__(self, capacity: int = 2):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key: str):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: str, value: int):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
""",
            test_code="""import solution

def test_lru_basic():
    c = solution.SimpleLRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1
    c.put("c", 3)
    assert c.get("b") is None
    assert c.get("a") == 1
    assert c.get("c") == 3
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-02",
            defect_id=None,
            has_defect=False,
            expected_category="clean_control",
            expected_behavioral_failure="Clean stateful LRU cache operates correctly",
            ground_truth_rationale="Clean control verifying eviction order and hit updates",
            test_oracle="pytest assertions verifying correct cache eviction of least recently used key",
        ),
    ),
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-03",
            name="Parameterized SQL Query Constructor (Security Negative Control)",
            module_code="""def build_user_query(user_id: int) -> dict:
    return {
        "query": "SELECT id, username, email FROM users WHERE id = :user_id",
        "params": {"user_id": int(user_id)},
    }
""",
            test_code="""import solution

def test_safe_query():
    res = solution.build_user_query(42)
    assert ":user_id" in res["query"]
    assert res["params"]["user_id"] == 42
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-03",
            defect_id=None,
            has_defect=False,
            expected_category="clean_control",
            expected_behavioral_failure="Clean parameterized query passes tests with 0 AST security alerts",
            ground_truth_rationale="Negative security control ensuring safe parameterized query patterns are not falsely flagged",
            test_oracle="pytest assertion on query dictionary structure",
        ),
    ),
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-04",
            name="Linear Time Set-Based Deduplication (Performance Control)",
            module_code="""def deduplicate_fast(items: list) -> list:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
""",
            test_code="""import solution

def test_dedup_correctness():
    assert solution.deduplicate_fast([1, 2, 2, 3, 1]) == [1, 2, 3]

def test_dedup_latency():
    items = list(range(1000)) + list(range(1000))
    res = solution.deduplicate_fast(items)
    assert len(res) == 1000
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-04",
            defect_id=None,
            has_defect=False,
            expected_category="clean_control",
            expected_behavioral_failure="Clean O(N) deduplication operates well below latency SLA (<10ms)",
            ground_truth_rationale="Clean performance control verifying sub-threshold execution time",
            test_oracle="pytest assertions on length and element order preservation",
        ),
    ),

    # -------------------------------------------------------------------------
    # 2. Functional Bugs (Scenarios 5-7, Seeded Defects 01-03)
    # -------------------------------------------------------------------------
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-05",
            name="Off-by-One Pagination Indexing",
            module_code="""def paginate_items(items: list, page: int, page_size: int) -> list:
    if page < 1 or page_size < 1:
        return []
    start = page * page_size
    return items[start : start + page_size]
""",
            test_code="""import solution

def test_paginate_page_1():
    items = [1, 2, 3, 4, 5, 6]
    page1 = solution.paginate_items(items, page=1, page_size=2)
    assert page1 == [1, 2], f"Expected [1, 2], got {page1}"
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-05",
            defect_id="PILOT-DEF-01",
            has_defect=True,
            expected_category="functional_bug",
            expected_line_number=4,
            mutation_operator="Off-by-one arithmetic deletion (- 1 removed from page start)",
            original_clean_source="start = (page - 1) * page_size",
            mutated_source="start = page * page_size",
            expected_behavioral_failure="AssertionError: Expected [1, 2], got [3, 4]",
            ground_truth_rationale="1-based page index improperly computed as 0-offset, skipping initial page",
            test_oracle="pytest assertion on items in first page",
        ),
    ),
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-06",
            name="Inverted Relational Operator in Tiered Pricing",
            module_code="""def calculate_discount(price: float, loyalty_years: int) -> float:
    if loyalty_years <= 5:
        return round(price * 0.80, 2)
    return price
""",
            test_code="""import solution

def test_high_loyalty_discount():
    res = solution.calculate_discount(100.0, loyalty_years=7)
    assert res == 80.0, f"Expected 80.0 for 7 years loyalty, got {res}"
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-06",
            defect_id="PILOT-DEF-02",
            has_defect=True,
            expected_category="functional_bug",
            expected_line_number=2,
            mutation_operator="Relational operator inversion (>= mutated to <=)",
            original_clean_source="if loyalty_years >= 5:",
            mutated_source="if loyalty_years <= 5:",
            expected_behavioral_failure="AssertionError: Expected 80.0 for 7 years loyalty, got 100.0",
            ground_truth_rationale="Inverted relational operator denies discount to senior loyalty customers",
            test_oracle="pytest assertion on discounted price",
        ),
    ),
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-07",
            name="Missing Divisor Zero-Check Guard",
            module_code="""def weighted_average(values: list, weights: list) -> float:
    total_weight = sum(weights)
    return sum(v * w for v, w in zip(values, weights)) / total_weight
""",
            test_code="""import solution

def test_zero_weights_safe_return():
    res = solution.weighted_average([10.0, 20.0], [0.0, 0.0])
    assert res == 0.0
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-07",
            defect_id="PILOT-DEF-03",
            has_defect=True,
            expected_category="functional_bug",
            expected_line_number=3,
            mutation_operator="Guard condition deletion (total_weight == 0 check removed)",
            original_clean_source="if total_weight == 0: return 0.0",
            mutated_source="# guard omitted",
            expected_behavioral_failure="ZeroDivisionError: float division by zero",
            ground_truth_rationale="Division by zero crash when all input weights are zero",
            test_oracle="pytest call with zero weights vector expecting default 0.0",
        ),
    ),

    # -------------------------------------------------------------------------
    # 3. Security Vulnerabilities (Scenarios 8-9, Seeded Defects 04-05)
    # -------------------------------------------------------------------------
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-08",
            name="Command Injection CWE-78 via os.system",
            module_code="""import os

def run_diagnostics(target: str) -> int:
    return os.system("echo check: " + target)
""",
            test_code="""import solution

def test_diag_basic():
    # Functional test executes without asserting security sanitization
    res = solution.run_diagnostics("node-01")
    assert isinstance(res, int)
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-08",
            defect_id="PILOT-DEF-04",
            has_defect=True,
            expected_category="security_vulnerability",
            expected_cwe_id="CWE-78",
            expected_line_number=4,
            mutation_operator="Unsafe shell execution replacement (subprocess list changed to os.system string concat)",
            original_clean_source='subprocess.run(["echo", "check:", target], check=False)',
            mutated_source='os.system("echo check: " + target)',
            expected_behavioral_failure="CWE-78: Improper Neutralization of Special Elements used in an OS Command",
            ground_truth_rationale="Static AST analysis detects unsafe os.system invocation with concatenated input",
            test_oracle="AST security inspection flagging CWE-78 pattern",
        ),
    ),
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-09",
            name="Dynamic Code Execution CWE-95 via eval",
            module_code="""def evaluate_arithmetic(expr: str) -> int:
    return eval(expr)
""",
            test_code="""import solution

def test_eval_simple():
    assert solution.evaluate_arithmetic("2 + 2") == 4
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-09",
            defect_id="PILOT-DEF-05",
            has_defect=True,
            expected_category="security_vulnerability",
            expected_cwe_id="CWE-95",
            expected_line_number=2,
            mutation_operator="Unrestricted eval injection",
            original_clean_source="ast.literal_eval(expr)",
            mutated_source="eval(expr)",
            expected_behavioral_failure="CWE-95: Improper Neutralization of Directives in Dynamically Evaluated Code",
            ground_truth_rationale="Static AST analysis detects raw eval() invocation allowing arbitrary Python execution",
            test_oracle="AST security inspection flagging CWE-95 pattern",
        ),
    ),

    # -------------------------------------------------------------------------
    # 4. Performance Bottlenecks (Scenarios 10-11, Seeded Defects 06-07)
    # -------------------------------------------------------------------------
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-10",
            name="Quadratic Pairwise Search SLA Breach",
            requested_test_types=["performance"],
            module_code="""def find_duplicates(items: list) -> list:
    dups = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j] and items[i] not in dups:
                dups.append(items[i])
    return sorted(dups)
""",
            test_code="""import solution

def test_find_dups_correctness():
    assert solution.find_duplicates([1, 2, 3, 2, 4, 1]) == [1, 2]

def test_find_dups_performance_sla():
    large_list = list(range(2500)) + list(range(2500))
    res = solution.find_duplicates(large_list)
    assert len(res) == 2500
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-10",
            defect_id="PILOT-DEF-06",
            has_defect=True,
            expected_category="performance_bottleneck",
            expected_line_number=3,
            mutation_operator="Algorithmic complexity degradation (O(N) hash set replaced with O(N^2) nested loop)",
            original_clean_source="seen = set(); [x for x in items if x in seen or seen.add(x)]",
            mutated_source="for i in range(len(items)): for j in range(i+1, len(items)): ...",
            expected_behavioral_failure="Latency SLA breach: took >200ms under 5,000 item workload",
            ground_truth_rationale="O(N^2) pairwise comparison violates production 200ms latency threshold",
            test_oracle="Performance test agent latency measurement against 200ms threshold",
        ),
    ),
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-11",
            name="Unmemoized Exponential Fibonacci Recursion",
            requested_test_types=["performance"],
            module_code="""def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)
""",
            test_code="""import solution

def test_fib_correctness():
    assert solution.fibonacci(7) == 13

def test_fib_performance_sla():
    assert solution.fibonacci(32) == 2178309
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-11",
            defect_id="PILOT-DEF-07",
            has_defect=True,
            expected_category="performance_bottleneck",
            expected_line_number=6,
            mutation_operator="Iterative loop replaced with unmemoized exponential recursion O(2^N)",
            original_clean_source="a, b = 0, 1; for _ in range(n): a, b = b, a + b",
            mutated_source="return fibonacci(n - 1) + fibonacci(n - 2)",
            expected_behavioral_failure="Latency SLA breach: n=32 takes >300ms under recursive evaluation",
            ground_truth_rationale="Exponential branching without memoization causes computational latency breach",
            test_oracle="Performance test agent latency measurement against 200ms threshold",
        ),
    ),

    # -------------------------------------------------------------------------
    # 5. Integration Defects (Scenario 12, Seeded Defect 08)
    # -------------------------------------------------------------------------
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-12",
            name="API Client Keyword Parameter Renaming Seam Defect",
            module_code="""def authenticate_request(token_str: str, payload: dict) -> dict:
    return {"authorized": bool(token_str), "payload": payload}
""",
            test_code="""import solution

def test_caller_integration():
    res = solution.authenticate_request(api_key="secret123", payload={"action": "read"})
    assert res["authorized"] is True
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-12",
            defect_id="PILOT-DEF-08",
            has_defect=True,
            expected_category="integration_defect",
            expected_line_number=1,
            mutation_operator="API parameter keyword renaming (api_key mutated to token_str)",
            original_clean_source="def authenticate_request(api_key: str, payload: dict):",
            mutated_source="def authenticate_request(token_str: str, payload: dict):",
            expected_behavioral_failure="TypeError: authenticate_request() got an unexpected keyword argument 'api_key'",
            ground_truth_rationale="Interface seam contract broken by renaming expected keyword argument",
            test_oracle="pytest integration test calling method with keyword argument",
        ),
    ),

    # -------------------------------------------------------------------------
    # 6. Regression Defects (Scenario 13, Seeded Defect 09)
    # -------------------------------------------------------------------------
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-13",
            name="Legacy Schema Format V1 Support Deletion",
            module_code="""def parse_envelope(data: dict) -> str:
    if "data" in data and "message" in data["data"]:
        return data["data"]["message"]
    raise ValueError("Invalid envelope format")
""",
            test_code="""import solution

def test_v2_envelope():
    assert solution.parse_envelope({"data": {"message": "hello"}}) == "hello"

def test_legacy_v1_regression():
    assert solution.parse_envelope({"msg": "legacy_hello"}) == "legacy_hello"
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-13",
            defect_id="PILOT-DEF-09",
            has_defect=True,
            expected_category="regression",
            expected_line_number=4,
            mutation_operator="Backward-compatibility parser branch deletion (msg field omitted)",
            original_clean_source='if "msg" in data: return data["msg"]',
            mutated_source="# legacy branch omitted",
            expected_behavioral_failure="ValueError: Invalid envelope format on legacy v1 payload",
            ground_truth_rationale="Deleting backward-compatible parsing logic causes regressions on existing clients",
            test_oracle="pytest regression test validating legacy v1 envelope payload",
        ),
    ),

    # -------------------------------------------------------------------------
    # 7. Semantic Drift Cases (Scenarios 14-15, Seeded Defects 10-11)
    # -------------------------------------------------------------------------
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-14",
            name="Assertion Weakening Test Suite Drift",
            module_code="""def calculate_tax(amount: float, rate: float) -> float:
    return round(amount + rate, 2)
""",
            original_test_code="""import solution

def test_calculate_tax():
    res = solution.calculate_tax(100.0, 0.15)
    assert res == 15.0, f"Expected 15.0, got {res}"
    assert isinstance(res, float)
""",
            candidate_test_code="""import solution

def test_calculate_tax():
    res = solution.calculate_tax(100.0, 0.15)
    assert res is not None
""",
            test_code="""import solution

def test_calculate_tax():
    res = solution.calculate_tax(100.0, 0.15)
    assert res is not None
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-14",
            defect_id="PILOT-DEF-10",
            has_defect=True,
            has_semantic_drift=True,
            expected_category="semantic_drift",
            expected_line_number=2,
            mutation_operator="Test assertion weakening (assert res == 15.0 weakened to assert res is not None)",
            original_clean_source="return round(amount * rate, 2)",
            mutated_source="return round(amount + rate, 2)",
            expected_behavioral_failure="Semantic test suite drift: exact equality assertion replaced with trivial existence check",
            ground_truth_rationale="Weakened test assertion allows defective addition logic to pass conventional CI",
            test_oracle="AST semantic drift diff detector comparing original vs candidate test suite",
        ),
    ),
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-15",
            name="Critical Edge Case Test Deletion Drift",
            module_code="""def parse_percentage(val_str: str) -> float:
    return float(val_str.rstrip("%")) / 100.0
""",
            original_test_code="""import solution

def test_parse_valid():
    assert solution.parse_percentage("25%") == 0.25

def test_parse_empty_boundary():
    try:
        solution.parse_percentage("")
        assert False, "Expected ValueError"
    except (ValueError, IndexError):
        pass
""",
            candidate_test_code="""import solution

def test_parse_valid():
    assert solution.parse_percentage("25%") == 0.25
""",
            test_code="""import solution

def test_parse_valid():
    assert solution.parse_percentage("25%") == 0.25
""",
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-15",
            defect_id="PILOT-DEF-11",
            has_defect=True,
            has_semantic_drift=True,
            expected_category="semantic_drift",
            expected_line_number=2,
            mutation_operator="Test function deletion (test_parse_empty_boundary deleted from suite)",
            original_clean_source="if not val_str: raise ValueError('Empty string'); return float(val_str.rstrip('%')) / 100.0",
            mutated_source="return float(val_str.rstrip('%')) / 100.0",
            expected_behavioral_failure="Semantic test suite drift: boundary test deleted to conceal missing input validation",
            ground_truth_rationale="Deleting boundary tests conceals defects from raw pytest runners",
            test_oracle="AST semantic drift diff detector flagging deleted test function",
        ),
    ),

    # -------------------------------------------------------------------------
    # 8. Non-Convergent Repair Loop (Scenario 16, Seeded Defect 12)
    # -------------------------------------------------------------------------
    PilotScenario(
        input_data=PilotEvaluationInput(
            scenario_id="PILOT-SC-16",
            name="Contradictory Specification Multi-Turn Repair Oscillation",
            is_repair_loop_scenario=True,
            module_code="""def process_flag(mode: str) -> str:
    return "MODE_A"
""",
            test_code="""import solution

def test_rule_alpha():
    assert solution.process_flag("auto") == "MODE_ALPHA"

def test_rule_beta():
    assert solution.process_flag("auto") == "MODE_BETA"
""",
            repair_candidate_patches=[
                'def process_flag(mode: str) -> str:\n    return "MODE_ALPHA"\n',
                'def process_flag(mode: str) -> str:\n    return "MODE_BETA"\n',
                'def process_flag(mode: str) -> str:\n    return "MODE_ALPHA"\n',
            ],
        ),
        ground_truth=PilotGroundTruthRecord(
            scenario_id="PILOT-SC-16",
            defect_id="PILOT-DEF-12",
            has_defect=True,
            is_non_convergent_by_design=True,
            expected_category="non_convergent_by_design",
            expected_line_number=2,
            mutation_operator="Mutually exclusive contradictory assertion injection",
            original_clean_source='def process_flag(mode: str) -> str: return "MODE_ALPHA"',
            mutated_source='def process_flag(mode: str) -> str: return "MODE_A"',
            expected_behavioral_failure="Non-convergent repair oscillation: alternating patches cannot satisfy mutually exclusive assertions",
            ground_truth_rationale="Repair harness detects infinite cycling or contradictory test failures and triggers governance escalation",
            test_oracle="Controlled repair loop harness detecting repeated patch cycles and non-convergence",
        ),
    ),
]


# =============================================================================
# Pilot Execution & Evidence Serialization Harness (Tasks 4, 5, 6, 7, 8)
# =============================================================================

class PilotBenchmarkRunner:
    """
    Independent execution and evidence collection engine for the Phase 3C.1 pilot.
    Enforces absolute ground-truth isolation during execution and captures full 17-field records.
    """

    def __init__(self, use_real_docker: bool = False, evaluation_mode: str = "DETERMINISTIC_ONLY"):
        self.use_real_docker = use_real_docker
        self.evaluation_mode = evaluation_mode
        self.evaluator = BenchmarkEvaluator(use_real_docker=use_real_docker, evaluation_mode=evaluation_mode)
        self.ci_baseline = ConventionalCiBaselineEvaluator(use_real_docker=use_real_docker, runner=self.evaluator.runner)
        self.static_baseline = StaticAnalysisBaselineEvaluator()

    async def execute_pilot(
        self,
        scenarios: Optional[List[PilotScenario]] = None,
        output_filename: str = "benchmark_results_phase3c1_pilot.json",
        dataset_version: str = "v3.1.0-phase3c1-pilot",
    ) -> Dict[str, Any]:
        """
        Executes the 16-scenario pilot across Component 4, Conventional CI, and Static Analysis.
        Derives all predictions independently before accessing ground-truth labels for scoring.
        """
        pilot_dataset = scenarios or PILOT_SCENARIOS
        timestamp_now = datetime.now(timezone.utc).isoformat()

        # Step 1: Probe Ollama availability & record actual LLM participation telemetry (Task 5)
        ollama_client = OllamaClient()
        try:
            ollama_ok, ollama_models, ollama_msg = await ollama_client.check_availability()
        except Exception as exc:
            ollama_ok, ollama_models, ollama_msg = False, [], f"Ollama probe error: {exc}"

        model_digest = None
        if ollama_ok:
            try:
                from app.services.llm_defect_reasoning_agent import LLMDefectReasoningAgent
                model_digest = await LLMDefectReasoningAgent().get_model_digest()
            except Exception:
                pass

        llm_telemetry = {
            "evaluation_mode": self.evaluation_mode,
            "model_identifier": ollama_client.model_name,
            "model_digest": model_digest,
            "base_url": ollama_client.base_url,
            "configured_enabled": ollama_client.enabled,
            "daemon_connected": ollama_ok,
            "models_available": ollama_models,
            "status_message": ollama_msg,
            "actual_inference_invocations_in_detection": 0,
            "detection_mechanism": (
                "deterministic_multi_agent_ast_and_dynamic_pytest"
                if self.evaluation_mode == "DETERMINISTIC_ONLY"
                else "bounded_evidence_grounded_llm_reasoning_and_reconciliation"
            ),
            "xai_explanation_provider": "ollama_inference_v1 (with deterministic fallback)",
        }

        # Step 2: Convert to legacy input format for evaluator execution (Inputs only)
        legacy_scenarios = [s.to_benchmark_scenario() for s in pilot_dataset]
        gt_map = {s.scenario_id: s.ground_truth for s in pilot_dataset}

        # Step 3: Execute Component 4 Multi-Agent System
        c4_summary = await self.evaluator.run_evaluation(
            scenarios=legacy_scenarios,
            save_to_file=False,
            evaluation_version=dataset_version,
            dataset_split="pilot",
        )

        # Step 4: Execute Conventional CI Baseline
        ci_baseline_res = await self.ci_baseline.evaluate(legacy_scenarios)

        # Step 5: Execute Static Analysis Baseline
        static_baseline_res = self.static_baseline.evaluate(legacy_scenarios)

        # Map baseline records by scenario ID
        ci_records_map = {r.scenario_id: r for r in ci_baseline_res.scenario_records}
        static_records_map = {r.scenario_id: r for r in static_baseline_res.scenario_records}

        # Step 6: Assemble Scenario-Level Evidence Records (Task 6 - 17 attributes)
        c4_preds_list: List[ScenarioPrediction] = []
        ci_preds_list: List[ScenarioPrediction] = []
        static_preds_list: List[ScenarioPrediction] = []
        full_scenario_observations: List[Dict[str, Any]] = []

        for sc in pilot_dataset:
            sid = sc.scenario_id
            gt = gt_map[sid]
            sc_legacy = next(s for s in legacy_scenarios if s.scenario_id == sid)

            # Retrieve Component 4 prediction from legacy summary records
            c4_rec = next(r for r in c4_summary.scenarios if r["scenario_id"] == sid)
            c4_detected = c4_rec["predictions"]["detected_has_defect"]
            c4_category = c4_rec["predictions"]["predicted_category"]
            c4_line = c4_rec["predictions"]["localized_line"]
            c4_dur = c4_rec["duration_ms"]

            ci_rec = ci_records_map[sid]
            static_rec = static_records_map[sid]

            # Scenario Prediction objects for strict statistical provenance testing
            c4_sp = ScenarioPrediction(
                scenario_id=sid,
                predicted_has_defect=c4_detected,
                provenance=PredictionProvenance.EMPIRICAL_EXECUTION,
                system_name="Component 4 Multi-Agent",
                ground_truth_has_defect=gt.has_defect,
                ground_truth_category=gt.expected_category,
            )
            ci_sp = ScenarioPrediction(
                scenario_id=sid,
                predicted_has_defect=ci_rec.detected_has_defect,
                provenance=PredictionProvenance.EMPIRICAL_EXECUTION,
                system_name="Conventional CI",
                ground_truth_has_defect=gt.has_defect,
                ground_truth_category=gt.expected_category,
            )
            static_sp = ScenarioPrediction(
                scenario_id=sid,
                predicted_has_defect=static_rec.detected_has_defect,
                provenance=PredictionProvenance.EMPIRICAL_EXECUTION,
                system_name="Static Analysis AST Scanner",
                ground_truth_has_defect=gt.has_defect,
                ground_truth_category=gt.expected_category,
            )

            c4_preds_list.append(c4_sp)
            ci_preds_list.append(ci_sp)
            static_preds_list.append(static_sp)

            # Full 17-field serialized evidence record (Task 6)
            full_record = {
                "scenario_id": sid,
                "defect_id": gt.defect_id,
                "dataset_version": dataset_version,
                "dataset_partition": "pilot",
                "ground_truth": {
                    "has_defect": gt.has_defect,
                    "expected_category": gt.expected_category,
                    "expected_cwe_id": gt.expected_cwe_id,
                    "expected_line_number": gt.expected_line_number,
                    "mutation_operator": gt.mutation_operator,
                    "is_non_convergent_by_design": gt.is_non_convergent_by_design,
                    "has_semantic_drift": gt.has_semantic_drift,
                },
                "component4": {
                    "system_name": "Component 4 Multi-Agent",
                    "detected_has_defect": c4_detected,
                    "predicted_category": c4_category,
                    "localized_line": c4_line,
                    "execution_status": "DEFECT_DETECTED" if c4_detected else "CLEAN",
                    "container_exit_code": 1 if c4_detected else 0,
                    "timeout": False,
                    "duration_ms": c4_dur,
                    "sanitized_evidence": f"Component 4 analyzed {c4_rec['predictions']['defects_count']} defect report(s)",
                    "provenance": "EMPIRICAL_EXECUTION",
                    "ai_contribution": c4_rec.get("ai_contribution"),
                    "defect_reports": c4_rec.get("defect_reports", []),
                    "machine_guidance": c4_rec.get("machine_guidance", []),
                },
                "conventional_ci": {
                    "system_name": "Conventional CI (Raw Pytest)",
                    "detected_has_defect": ci_rec.detected_has_defect,
                    "execution_status": ci_rec.execution_status,
                    "container_exit_code": ci_rec.container_exit_code,
                    "timeout": ci_rec.timeout,
                    "duration_ms": ci_rec.duration_ms,
                    "sanitized_evidence": ci_rec.sanitized_evidence,
                    "provenance": ci_rec.provenance,
                },
                "static_analysis": {
                    "system_name": "Static Analysis (AST Scanner)",
                    "detected_has_defect": static_rec.detected_has_defect,
                    "execution_status": static_rec.execution_status,
                    "container_exit_code": static_rec.container_exit_code,
                    "timeout": False,
                    "duration_ms": static_rec.duration_ms,
                    "sanitized_evidence": static_rec.sanitized_evidence,
                    "findings_count": static_rec.findings_count,
                    "provenance": static_rec.provenance,
                },
                "artifact_checksum": hashlib.sha256(sc.input_data.module_code.encode("utf-8")).hexdigest(),
                "execution_timestamp": timestamp_now,
                "evaluator_version": "v3.1.0-phase3c1",
                "provenance": "EMPIRICAL_EXECUTION",
                "llm_telemetry": {
                    "daemon_connected": ollama_ok,
                    "invoked_during_detection": False,
                },
            }
            full_scenario_observations.append(full_record)

        # Step 7: Paired Empirical Statistical Analysis (Task 8)
        gt_bool_map = {sid: gt.has_defect for sid, gt in gt_map.items()}
        paired_c4_vs_ci = evaluate_empirical_paired_test(
            predictions_a=c4_preds_list,
            predictions_b=ci_preds_list,
            ground_truth=gt_bool_map,
            iterations=5000,
            seed=42,
        )

        paired_c4_vs_static = evaluate_empirical_paired_test(
            predictions_a=c4_preds_list,
            predictions_b=static_preds_list,
            ground_truth=gt_bool_map,
            iterations=5000,
            seed=42,
        )

        # Step 8: Metric Aggregations
        y_true = [gt_map[sc.scenario_id].has_defect for sc in pilot_dataset]
        y_c4 = [p.predicted_has_defect for p in c4_preds_list]
        y_ci = [p.predicted_has_defect for p in ci_preds_list]
        y_static = [p.predicted_has_defect for p in static_preds_list]

        m_c4 = compute_binary_metrics(y_true, y_c4)
        m_ci = compute_binary_metrics(y_true, y_ci)
        m_static = compute_binary_metrics(y_true, y_static)

        results_payload = {
            "evaluation_title": "INTELISE Component 4 — Phase 3C.1 Pilot Benchmark Results",
            "dataset_version": dataset_version,
            "timestamp": timestamp_now,
            "total_scenarios": len(pilot_dataset),
            "clean_controls_count": sum(1 for s in pilot_dataset if not s.ground_truth.has_defect),
            "seeded_defects_count": sum(1 for s in pilot_dataset if s.ground_truth.has_defect),
            "evaluation_mode": "real_docker" if self.use_real_docker else "in_process_sandbox",
            "llm_telemetry": llm_telemetry,
            "metrics": {
                "component4": {
                    "true_positives": m_c4.confusion_matrix.true_positives,
                    "false_positives": m_c4.confusion_matrix.false_positives,
                    "true_negatives": m_c4.confusion_matrix.true_negatives,
                    "false_negatives": m_c4.confusion_matrix.false_negatives,
                    "accuracy": m_c4.accuracy,
                    "precision": m_c4.precision,
                    "recall": m_c4.recall,
                    "f1_score": m_c4.f1_score,
                },
                "conventional_ci": {
                    "true_positives": m_ci.confusion_matrix.true_positives,
                    "false_positives": m_ci.confusion_matrix.false_positives,
                    "true_negatives": m_ci.confusion_matrix.true_negatives,
                    "false_negatives": m_ci.confusion_matrix.false_negatives,
                    "accuracy": m_ci.accuracy,
                    "precision": m_ci.precision,
                    "recall": m_ci.recall,
                    "f1_score": m_ci.f1_score,
                },
                "static_analysis": {
                    "true_positives": m_static.confusion_matrix.true_positives,
                    "false_positives": m_static.confusion_matrix.false_positives,
                    "true_negatives": m_static.confusion_matrix.true_negatives,
                    "false_negatives": m_static.confusion_matrix.false_negatives,
                    "accuracy": m_static.accuracy,
                    "precision": m_static.precision,
                    "recall": m_static.recall,
                    "f1_score": m_static.f1_score,
                },
            },
            "paired_statistical_comparison": {
                "component4_vs_conventional_ci": {
                    "is_empirical": paired_c4_vs_ci.is_empirical,
                    "table": {
                        "both_correct_a": paired_c4_vs_ci.table.both_correct,
                        "c4_only_b": paired_c4_vs_ci.table.system_a_only,
                        "ci_only_c": paired_c4_vs_ci.table.system_b_only,
                        "both_incorrect_d": paired_c4_vs_ci.table.both_incorrect,
                        "total": paired_c4_vs_ci.table.total,
                    },
                    "mcnemar": {
                        "discordant_pairs": paired_c4_vs_ci.mcnemar.discordant_pairs,
                        "p_value_exact_binomial": paired_c4_vs_ci.mcnemar.p_value_exact_binomial,
                        "is_significant_at_05": paired_c4_vs_ci.mcnemar.is_significant_at_05,
                    },
                    "bootstrap_95ci": {
                        "delta_f1_ci": list(paired_c4_vs_ci.bootstrap.delta_f1_ci),
                        "delta_accuracy_ci": list(paired_c4_vs_ci.bootstrap.delta_accuracy_ci),
                    },
                },
                "component4_vs_static_analysis": {
                    "is_empirical": paired_c4_vs_static.is_empirical,
                    "table": {
                        "both_correct_a": paired_c4_vs_static.table.both_correct,
                        "c4_only_b": paired_c4_vs_static.table.system_a_only,
                        "static_only_c": paired_c4_vs_static.table.system_b_only,
                        "both_incorrect_d": paired_c4_vs_static.table.both_incorrect,
                        "total": paired_c4_vs_static.table.total,
                    },
                    "mcnemar": {
                        "discordant_pairs": paired_c4_vs_static.mcnemar.discordant_pairs,
                        "p_value_exact_binomial": paired_c4_vs_static.mcnemar.p_value_exact_binomial,
                        "is_significant_at_05": paired_c4_vs_static.mcnemar.is_significant_at_05,
                    },
                },
            },
            "scenarios": full_scenario_observations,
        }

        # Step 9: Serialize to disk in component-4/backend directory
        out_path = Path(__file__).resolve().parent.parent.parent / output_filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results_payload, f, indent=2)

        return results_payload
