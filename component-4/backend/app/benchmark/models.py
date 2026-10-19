from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.common import DefectCategory


class BenchmarkScenarioGroup(str, Enum):
    """Proposal Table 4 Seeded-defect benchmark scenario groups."""
    CLEAN_CONTROL = "clean_control"
    FUNCTIONAL_BUG = "functional_bug"
    SECURITY_VULNERABILITY = "security_vulnerability"
    PERFORMANCE_BOTTLENECK = "performance_bottleneck"
    REGRESSION = "regression"
    NON_CONVERGENT_BY_DESIGN = "non_convergent_by_design"
    SEMANTIC_DRIFT = "semantic_drift"
    INTEGRATION_DEFECT = "integration_defect"


class BenchmarkScenario(BaseModel):
    """Structured test scenario for research benchmark evaluation (SO6, Table 4, Table 15)."""

    scenario_id: str = Field(description="Unique scenario ID (e.g. TX01-01, PH3-DEV-001, PH3-HELD-001)")
    name: str = Field(description="Human readable scenario title")
    scenario_group: BenchmarkScenarioGroup
    module_code: str = Field(description="Python source code under verification")
    test_code: str = Field(description="Authorized test suite for this scenario")
    filename: str = Field(default="solution.py")
    requirement_ids: List[str] = Field(default_factory=lambda: ["REQ-001"])

    # Operational verification parameters (NOT ground truth labels)
    original_test_code: Optional[str] = Field(default=None, description="Authoritative original test suite for drift/regression evaluation")
    candidate_test_code: Optional[str] = Field(default=None, description="Candidate test suite under test revision check")
    requested_test_types: Optional[List[str]] = Field(default=None, description="Requested test suites (e.g. ['unit', 'performance'])")
    repair_candidate_patches: Optional[List[str]] = Field(default=None, description="Sequence of candidate patch versions for repair loop evaluation")
    is_repair_loop_scenario: bool = Field(default=False, description="True if scenario participates in iterative repair loop harness")

    # Research metadata & Provenance (SO6, Table 4)
    difficulty: Optional[str] = Field(default="medium", description="Scenario difficulty level: easy, medium, hard")
    provenance: Optional[str] = Field(default="curated_synthetic", description="Provenance of source code / defect pattern")
    split: Optional[str] = Field(default=None, description="Dataset split: dev or held_out")
    checksum_sha256: Optional[str] = Field(default=None, description="SHA-256 digest of frozen scenario definition")

    # Ground-truth labels (Accessed ONLY after predictions are finalized for metric scoring)
    has_defect: bool = Field(default=True)
    expected_defect_category: DefectCategory = Field(default=DefectCategory.FUNCTIONAL_BUG)
    expected_cwe_id: Optional[str] = None
    expected_line_number: Optional[int] = None
    is_non_convergent_by_design: bool = Field(default=False)
    has_semantic_drift: bool = Field(default=False)
    expected_system_behavior: str = Field(description="Expected proposal outcome")


class CategoryMetric(BaseModel):
    category: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    target_recall: float = 0.85
    target_met: bool = False


class BenchmarkEvaluationSummary(BaseModel):
    """Aggregated empirical results for research evaluation chapter (SO6, Table 5)."""

    evaluation_version: str = Field(default="v2_methodology_corrected", description="Benchmark version identifier")
    dataset_split: Optional[str] = Field(default=None, description="Dataset partition evaluated: dev, held_out, or all_100")
    manifest_checksum: Optional[str] = Field(default=None, description="Dataset frozen manifest SHA-256 digest")
    total_scenarios: int
    clean_controls_evaluated: int
    functional_bugs_evaluated: int
    security_vulnerabilities_evaluated: int
    performance_bottlenecks_evaluated: int
    regressions_evaluated: int
    non_convergent_evaluated: int
    semantic_drift_cases_evaluated: int
    integration_defects_evaluated: int = 0

    overall_precision: float
    overall_recall: float
    overall_f1: float

    category_metrics: Dict[str, CategoryMetric]

    # Detailed Methodology Evaluation Metrics
    binary_detection_metrics: Optional[Dict[str, Any]] = Field(default=None, description="Overall binary defect detection TP/FP/TN/FN")
    confusion_matrix: Optional[Dict[str, Dict[str, int]]] = Field(default=None, description="Full multiclass confusion matrix")
    localization_metrics: Optional[Dict[str, Any]] = Field(default=None, description="Defect line localization hit rates")
    semantic_drift_metrics: Optional[Dict[str, Any]] = Field(default=None, description="Semantic drift TP/FP/TN/FN metrics")
    convergence_repair_metrics: Optional[Dict[str, Any]] = Field(default=None, description="Observed multi-iteration repair and escalation metrics")

    # Convergence and Drift Metrics
    naive_convergence_rate: float
    semantically_strict_convergence_rate: float
    superficial_convergence_detection_rate: float
    correct_escalation_rate: float

    # Execution Overhead
    mean_execution_time_ms: float
    median_execution_time_ms: float
    p95_execution_time_ms: float

    # Comparative Baselines Results
    single_agent_baseline_f1: float
    static_analysis_baseline_recall: float
    generic_xai_baseline_usefulness: float

    # Provenance and Limitations
    provenance_summary: Optional[Dict[str, Any]] = Field(default=None, description="Execution provenance and environment metadata")
    explicit_limitations: Optional[List[str]] = Field(default=None, description="Methodological boundaries and empirical limits")
