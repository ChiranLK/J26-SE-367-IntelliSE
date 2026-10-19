"""
Automated Verification Suite for Empirical Baseline Provenance & Statistical Integrity.
Phase 3B.3 — Tasks 4, 5, and 6.

Validates the 14 mandatory provenance and statistical integrity requirements:
1. Missing Conventional CI predictions rejection.
2. Aggregate-only baseline evidence rejection from paired testing.
3. Synthetic proxy rejection from empirical paired testing.
4. Duplicate scenario IDs rejection.
5. Mismatched prediction sets rejection.
6. Ground-truth mismatch rejection.
7. Valid empirical paired predictions acceptance.
8. Valid verified-log reconstruction acceptance.
9. Incorrect provenance claims rejection.
10. Confusion-matrix arithmetic verification.
11. F1 formula consistency check and paired indeterminacy proof.
12. Scenario-level evidence serialization verification.
13. Label-leakage prevention during baseline detection.
14. Historical benchmark immutability and checksum stability.
"""
import hashlib
import json
import os
from pathlib import Path
import pytest

from app.benchmark.baselines import (
    ConventionalCiBaselineEvaluator,
    StaticAnalysisBaselineEvaluator,
    ScenarioBaselineRecord,
    BaselineExecutionResult,
)
from app.benchmark.evaluator import BenchmarkEvaluator
from app.benchmark.models import BenchmarkScenario, BenchmarkScenarioGroup
from app.benchmark.statistical_analysis import (
    ConfusionMatrix,
    BinaryMetrics,
    PredictionProvenance,
    ProvenanceValidationError,
    ScenarioPrediction,
    validate_paired_empirical_evidence,
    evaluate_empirical_paired_test,
    evaluate_synthetic_proxy_demonstration,
    reconstruct_empirical_aggregate_confusion_matrix,
    explain_paired_indeterminacy_from_aggregates,
    compute_metrics_from_confusion_matrix,
    compute_binary_metrics,
    construct_confusion_matrix,
    exact_mcnemar_test,
)
from app.schemas.common import DefectCategory


# =============================================================================
# Helper Fixtures & Builders
# =============================================================================

def build_mock_scenario_prediction(
    scenario_id: str,
    predicted_has_defect: bool,
    provenance: PredictionProvenance,
    system_name: str = "Component 4",
    ground_truth_has_defect: bool = True,
) -> ScenarioPrediction:
    return ScenarioPrediction(
        scenario_id=scenario_id,
        predicted_has_defect=predicted_has_defect,
        provenance=provenance,
        system_name=system_name,
        ground_truth_has_defect=ground_truth_has_defect,
        ground_truth_category="functional_bug" if ground_truth_has_defect else "clean_control",
    )


# =============================================================================
# Requirement 1: Missing Conventional CI Predictions
# =============================================================================

def test_01_missing_conventional_ci_predictions_rejected():
    """
    Requirement 1: Missing predictions for Conventional CI must cause an explicit
    validation failure and cannot produce paired statistical results.
    """
    preds_c4 = [
        build_mock_scenario_prediction("SC-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4"),
        build_mock_scenario_prediction("SC-02", False, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4"),
    ]
    preds_ci_empty = []

    with pytest.raises(ValueError, match="Predictions for System B cannot be empty"):
        validate_paired_empirical_evidence(preds_c4, preds_ci_empty)

    with pytest.raises(ValueError, match="Predictions for System B cannot be empty"):
        evaluate_empirical_paired_test(preds_c4, preds_ci_empty)


# =============================================================================
# Requirement 2: Aggregate-Only Baseline Evidence
# =============================================================================

def test_02_aggregate_only_baseline_evidence_rejected():
    """
    Requirement 2: When baseline evidence is marked AGGREGATE_ONLY,
    attempting paired empirical analysis must raise ProvenanceValidationError.
    """
    preds_c4 = [
        build_mock_scenario_prediction(f"SC-{i:02d}", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4")
        for i in range(10)
    ]
    preds_ci_aggregate = [
        build_mock_scenario_prediction(f"SC-{i:02d}", True, PredictionProvenance.AGGREGATE_ONLY, "Conventional CI")
        for i in range(10)
    ]

    with pytest.raises(ProvenanceValidationError, match="has non-empirical provenance 'AGGREGATE_ONLY'"):
        validate_paired_empirical_evidence(preds_c4, preds_ci_aggregate, allow_synthetic_demonstration=False)

    with pytest.raises(ProvenanceValidationError, match="non-empirical provenance"):
        evaluate_empirical_paired_test(preds_c4, preds_ci_aggregate)


# =============================================================================
# Requirement 3: Synthetic Proxy Rejection
# =============================================================================

def test_03_synthetic_proxy_rejection_from_empirical_testing():
    """
    Requirement 3: Synthetic proxy predictions must be strictly rejected from
    empirical paired significance testing, and only permitted in labeled demonstrations.
    """
    preds_c4 = [
        build_mock_scenario_prediction(f"SC-{i:02d}", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4")
        for i in range(10)
    ]
    preds_synthetic = [
        build_mock_scenario_prediction(f"SC-{i:02d}", True, PredictionProvenance.SYNTHETIC_PROXY, "Synthetic CI Proxy")
        for i in range(10)
    ]

    # Rejection from empirical test
    with pytest.raises(ProvenanceValidationError, match="has non-empirical provenance 'SYNTHETIC_PROXY'"):
        evaluate_empirical_paired_test(preds_c4, preds_synthetic)

    # Acceptance in synthetic demonstration with explicit non-empirical labeling
    demo_result = evaluate_synthetic_proxy_demonstration(preds_c4, preds_synthetic)
    assert demo_result.is_empirical is False
    assert demo_result.provenance_disclaimer is not None
    assert "NON-EMPIRICAL SYNTHETIC PROXY DEMONSTRATION" in demo_result.provenance_disclaimer


# =============================================================================
# Requirement 4: Duplicate Scenario IDs
# =============================================================================

def test_04_duplicate_scenario_ids_rejected():
    """
    Requirement 4: Duplicate scenario IDs in either system must raise an explicit validation error.
    """
    preds_c4_dups = [
        build_mock_scenario_prediction("SC-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4"),
        build_mock_scenario_prediction("SC-01", False, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4"),
    ]
    preds_ci = [
        build_mock_scenario_prediction("SC-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Conventional CI"),
        build_mock_scenario_prediction("SC-02", False, PredictionProvenance.EMPIRICAL_EXECUTION, "Conventional CI"),
    ]

    with pytest.raises(ValueError, match="Duplicate scenario IDs detected in System A"):
        validate_paired_empirical_evidence(preds_c4_dups, preds_ci)


# =============================================================================
# Requirement 5: Mismatched Prediction Sets
# =============================================================================

def test_05_mismatched_prediction_sets_rejected():
    """
    Requirement 5: Different counts or asymmetric scenario IDs across systems must be rejected.
    """
    preds_c4 = [
        build_mock_scenario_prediction("SC-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4"),
        build_mock_scenario_prediction("SC-02", False, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4"),
    ]
    preds_ci_mismatched_ids = [
        build_mock_scenario_prediction("SC-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Conventional CI"),
        build_mock_scenario_prediction("SC-99", False, PredictionProvenance.EMPIRICAL_EXECUTION, "Conventional CI"),
    ]
    preds_ci_mismatched_count = [
        build_mock_scenario_prediction("SC-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Conventional CI"),
    ]

    with pytest.raises(ValueError, match="Mismatched scenario IDs across systems"):
        validate_paired_empirical_evidence(preds_c4, preds_ci_mismatched_ids)

    with pytest.raises(ValueError, match="Mismatched prediction counts"):
        validate_paired_empirical_evidence(preds_c4, preds_ci_mismatched_count)


# =============================================================================
# Requirement 6: Ground-Truth Mismatch
# =============================================================================

def test_06_ground_truth_mismatch_rejected():
    """
    Requirement 6: Inconsistent ground-truth records across systems or against
    authoritative ground truth must cause a validation failure.
    """
    preds_c4 = [
        build_mock_scenario_prediction("SC-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4", ground_truth_has_defect=True),
    ]
    preds_ci_conflicting_gt = [
        build_mock_scenario_prediction("SC-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Conventional CI", ground_truth_has_defect=False),
    ]

    with pytest.raises(ValueError, match="Ground-truth mismatch for scenario 'SC-01'"):
        validate_paired_empirical_evidence(preds_c4, preds_ci_conflicting_gt)

    # Conflict against authoritative dictionary
    authoritative_gt = {"SC-01": False}  # Conflicts with C4's True
    preds_ci_aligned = [
        build_mock_scenario_prediction("SC-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Conventional CI", ground_truth_has_defect=True),
    ]
    with pytest.raises(ValueError, match="Ground truth conflict for scenario 'SC-01'"):
        validate_paired_empirical_evidence(preds_c4, preds_ci_aligned, ground_truth=authoritative_gt)


# =============================================================================
# Requirement 7: Valid Empirical Paired Predictions
# =============================================================================

def test_07_valid_empirical_paired_predictions_accepted():
    """
    Requirement 7: Genuinely matched empirical predictions evaluate successfully
    and produce empirical paired significance results.
    """
    gt_map = {f"SC-{i:02d}": (i % 2 == 0) for i in range(20)}

    preds_a = [
        build_mock_scenario_prediction(
            sid,
            predicted_has_defect=gt,  # Perfect accuracy
            provenance=PredictionProvenance.EMPIRICAL_EXECUTION,
            system_name="Component 4",
            ground_truth_has_defect=gt,
        )
        for sid, gt in gt_map.items()
    ]
    preds_b = [
        build_mock_scenario_prediction(
            sid,
            predicted_has_defect=(gt if i < 15 else not gt),  # 5 errors
            provenance=PredictionProvenance.EMPIRICAL_EXECUTION,
            system_name="Conventional CI",
            ground_truth_has_defect=gt,
        )
        for i, (sid, gt) in enumerate(gt_map.items())
    ]

    result = evaluate_empirical_paired_test(preds_a, preds_b, ground_truth=gt_map, iterations=1000)
    assert result.is_empirical is True
    assert result.system_a_name == "Component 4"
    assert result.system_b_name == "Conventional CI"
    assert result.scenario_count == 20
    assert result.table.both_correct == 15
    assert result.table.system_a_only == 5
    assert result.table.system_b_only == 0
    assert result.table.both_incorrect == 0
    assert result.table.total == 20
    assert result.mcnemar.discordant_pairs == 5
    assert result.provenance_disclaimer is None


# =============================================================================
# Requirement 8: Valid Verified-Log Reconstruction
# =============================================================================

def test_08_valid_verified_log_reconstruction_accepted():
    """
    Requirement 8: Predictions reconstructed from verified execution logs
    are accepted as empirical evidence for paired statistical analysis.
    """
    gt_map = {"SC-LOG-01": True, "SC-LOG-02": False}

    preds_a = [
        build_mock_scenario_prediction("SC-LOG-01", True, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4", True),
        build_mock_scenario_prediction("SC-LOG-02", False, PredictionProvenance.EMPIRICAL_EXECUTION, "Component 4", False),
    ]
    preds_b_log_reconstructed = [
        build_mock_scenario_prediction("SC-LOG-01", True, PredictionProvenance.VERIFIED_LOG_RECONSTRUCTION, "Conventional CI Log", True),
        build_mock_scenario_prediction("SC-LOG-02", True, PredictionProvenance.VERIFIED_LOG_RECONSTRUCTION, "Conventional CI Log", False),
    ]

    result = evaluate_empirical_paired_test(preds_a, preds_b_log_reconstructed, ground_truth=gt_map, iterations=500)
    assert result.is_empirical is True
    assert result.table.both_correct == 1
    assert result.table.system_a_only == 1
    assert result.table.total == 2


# =============================================================================
# Requirement 9: Incorrect Provenance Claims
# =============================================================================

def test_09_incorrect_provenance_claims_rejected():
    """
    Requirement 9: Invalid provenance labels or missing identification must be rejected.
    """
    # Invalid string provenance coerced or rejected
    with pytest.raises(ProvenanceValidationError, match="Invalid provenance 'UNVERIFIED_GUESS'"):
        ScenarioPrediction(
            scenario_id="SC-01",
            predicted_has_defect=True,
            provenance="UNVERIFIED_GUESS",  # type: ignore
            system_name="System X",
        )

    # Empty scenario ID
    with pytest.raises(ValueError, match="non-empty scenario_id"):
        ScenarioPrediction(
            scenario_id="",
            predicted_has_defect=True,
            provenance=PredictionProvenance.EMPIRICAL_EXECUTION,
            system_name="System X",
        )

    # Empty system name
    with pytest.raises(ValueError, match="must declare a system_name"):
        ScenarioPrediction(
            scenario_id="SC-01",
            predicted_has_defect=True,
            provenance=PredictionProvenance.EMPIRICAL_EXECUTION,
            system_name="   ",
        )


# =============================================================================
# Requirement 10: Confusion-Matrix Arithmetic
# =============================================================================

def test_10_confusion_matrix_arithmetic():
    """
    Requirement 10: Verify TP + FP + TN + FN == N and exact support arithmetic
    across held-out (60), dev (40), and consolidated (100) datasets.
    """
    # Held-Out (60 scenarios: 40 positive, 20 negative)
    c4_heldout_metrics = reconstruct_empirical_aggregate_confusion_matrix(60, 34, 2, 18, 6)
    cm = c4_heldout_metrics.confusion_matrix
    assert cm.total == 60
    assert cm.positive_support == 40
    assert cm.negative_support == 20

    ci_heldout_metrics = reconstruct_empirical_aggregate_confusion_matrix(60, 29, 2, 18, 11)
    cm_ci = ci_heldout_metrics.confusion_matrix
    assert cm_ci.total == 60
    assert cm_ci.positive_support == 40
    assert cm_ci.negative_support == 20

    # Development (40 scenarios: 31 positive, 9 negative)
    c4_dev_metrics = reconstruct_empirical_aggregate_confusion_matrix(40, 26, 1, 8, 5)
    cm_dev = c4_dev_metrics.confusion_matrix
    assert cm_dev.total == 40
    assert cm_dev.positive_support == 31
    assert cm_dev.negative_support == 9

    ci_dev_metrics = reconstruct_empirical_aggregate_confusion_matrix(40, 20, 1, 8, 11)
    cm_dev_ci = ci_dev_metrics.confusion_matrix
    assert cm_dev_ci.total == 40
    assert cm_dev_ci.positive_support == 31
    assert cm_dev_ci.negative_support == 9

    # Consolidated (100 scenarios: 71 positive, 29 negative)
    c4_100_metrics = reconstruct_empirical_aggregate_confusion_matrix(100, 60, 3, 26, 11)
    cm_100 = c4_100_metrics.confusion_matrix
    assert cm_100.total == 100
    assert cm_100.positive_support == 71
    assert cm_100.negative_support == 29

    ci_100_metrics = reconstruct_empirical_aggregate_confusion_matrix(100, 49, 3, 26, 22)
    cm_100_ci = ci_100_metrics.confusion_matrix
    assert cm_100_ci.total == 100
    assert cm_100_ci.positive_support == 71
    assert cm_100_ci.negative_support == 29

    # Inconsistent arithmetic must fail
    with pytest.raises(ValueError, match="does not match declared total"):
        reconstruct_empirical_aggregate_confusion_matrix(25, 10, 2, 5, 1)


# =============================================================================
# Requirement 11: F1 Formula Consistency & Indeterminacy Proof
# =============================================================================

def test_11_f1_formula_consistency_and_paired_indeterminacy():
    """
    Requirement 11: Verify F1 formula consistency and mathematical proof of
    paired indeterminacy from aggregate confusion matrices.
    """
    # Check held-out Component 4 metrics
    c4_metrics = reconstruct_empirical_aggregate_confusion_matrix(60, 34, 2, 18, 6)

    # Precision = 34 / 36 = 0.9444...
    # Recall = 34 / 40 = 0.85
    # F1 = 2 * (34/36) * (34/40) / (34/36 + 34/40) = 2 * 34 / (36 + 40) = 68 / 76 = 0.8947... -> 0.895
    assert round(c4_metrics.accuracy, 3) == 0.867
    assert round(c4_metrics.precision, 3) == 0.944
    assert round(c4_metrics.recall, 3) == 0.850
    assert round(c4_metrics.f1_score, 3) == 0.895

    # Check held-out Conventional CI metrics
    ci_metrics = reconstruct_empirical_aggregate_confusion_matrix(60, 29, 2, 18, 11)

    # Precision = 29 / 31 = 0.9355...
    # Recall = 29 / 40 = 0.725
    # F1 = 2 * 29 / (31 + 40) = 58 / 71 = 0.8169... -> 0.817
    assert round(ci_metrics.accuracy, 3) == 0.783
    assert round(ci_metrics.precision, 3) == 0.935
    assert round(ci_metrics.recall, 3) == 0.725
    assert round(ci_metrics.f1_score, 3) == 0.817

    # Indeterminacy proof: Explain why marginals alone cannot determine paired McNemar p-value
    proof = explain_paired_indeterminacy_from_aggregates(c4_metrics.confusion_matrix, ci_metrics.confusion_matrix)
    assert proof["compatible_table_count"] == 9  # a in [39..47]
    assert round(proof["min_possible_p_value"], 4) == 0.0625
    assert round(proof["max_possible_p_value"], 4) == 0.3833
    assert proof["compatible_tables_sample"][0]["both_correct_a"] == 39
    assert proof["compatible_tables_sample"][-1]["both_correct_a"] == 47
    assert "cannot be performed from aggregate confusion matrices alone" in proof["explanation"]


# =============================================================================
# Requirement 12: Scenario-Level Evidence Serialization
# =============================================================================

def test_12_scenario_level_evidence_serialization():
    """
    Requirement 12: Verify that future benchmark infrastructure captures and serializes
    complete scenario-level observation records for all evaluated systems.
    """
    record = ScenarioBaselineRecord(
        scenario_id="TEST-SEC-01",
        detected_has_defect=True,
        execution_status="FAILED",
        container_exit_code=1,
        timeout=False,
        duration_ms=45.2,
        sanitized_evidence="AssertionError in test_security: Unauthorized access permitted",
        provenance="EMPIRICAL_EXECUTION",
    )

    rec_dict = record.to_dict()
    assert rec_dict["scenario_id"] == "TEST-SEC-01"
    assert rec_dict["detected_has_defect"] is True
    assert rec_dict["execution_status"] == "FAILED"
    assert rec_dict["container_exit_code"] == 1
    assert rec_dict["timeout"] is False
    assert rec_dict["duration_ms"] == 45.2
    assert "AssertionError" in rec_dict["sanitized_evidence"]
    assert rec_dict["provenance"] == "EMPIRICAL_EXECUTION"

    # Check BaselineExecutionResult serialization
    baseline_result = BaselineExecutionResult(
        baseline_name="Conventional CI",
        total_scenarios=1,
        true_positives=1,
        false_positives=0,
        true_negatives=0,
        false_negatives=0,
        precision=1.0,
        recall=1.0,
        f1_score=1.0,
        detection_breakdown={},
        scenario_records=[record],
    )
    b_dict = baseline_result.to_dict()
    assert "scenario_records" in b_dict
    assert len(b_dict["scenario_records"]) == 1
    assert b_dict["scenario_records"][0]["scenario_id"] == "TEST-SEC-01"


# =============================================================================
# Requirement 13: Label-Leakage Prevention
# =============================================================================

def test_13_label_leakage_prevention_in_baseline_evaluators():
    """
    Requirement 13: Verify that baseline execution executes in-process sandbox
    without reading or inspecting scenario ground truth labels during detection.
    """
    code_passing = "def add(a, b): return a + b\n"
    test_passing = "import solution\ndef test_add(): assert solution.add(1, 2) == 3\n"

    # In-process execution sandbox directly accepts raw code and test strings with ZERO scenario object
    evaluator = ConventionalCiBaselineEvaluator(use_real_docker=False)
    failed, exit_code, timeout, dur, evidence = evaluator._execute_in_process_sandbox(
        source_code=code_passing,
        test_code=test_passing,
        filename="solution.py",
    )

    assert failed is False
    assert exit_code == 0
    assert timeout is False
    assert "All tests passed" in evidence

    # Failing code
    code_failing = "def add(a, b): return a - b\n"
    failed_2, exit_code_2, timeout_2, dur_2, evidence_2 = evaluator._execute_in_process_sandbox(
        source_code=code_failing,
        test_code=test_passing,
        filename="solution.py",
    )

    assert failed_2 is True
    assert exit_code_2 == 1
    assert "AssertionError" in evidence_2


# =============================================================================
# Requirement 14: Historical Benchmark Immutability
# =============================================================================

def test_14_historical_benchmark_immutability():
    """
    Requirement 14: Verify that historical Phase 3A benchmark JSON result files
    exist, have valid JSON structure, retain their exact historical metric values,
    and have untouched SHA-256 digests.
    """
    base_dir = Path(__file__).resolve().parent.parent

    historical_files = {
        "heldout": {
            "path": base_dir / "benchmark_results_phase3_heldout.json",
            "expected_sha256": "fbaf6762cba84c9632df6cf4268531d84bfd5bb89160a5ae33ea47c8d5a872a3",
            "total_scenarios": 60,
            "c4_f1": 0.895,
            "ci_f1": 0.817,
        },
        "dev": {
            "path": base_dir / "benchmark_results_phase3_dev.json",
            "expected_sha256": "6b16ea5917276fc14d62cee4610a82bca196e39d2c1b4395d093d7a4b4b9e032",
            "total_scenarios": 40,
            "c4_f1": 0.897,
            "ci_f1": 0.769,
        },
        "100": {
            "path": base_dir / "benchmark_results_phase3_100.json",
            "expected_sha256": "10269c798dfe72eb37906d60a93ad7d12442f042aac349a4de9406f503dadc09",
            "total_scenarios": 100,
            "c4_f1": 0.896,
            "ci_f1": 0.797,
        },
    }

    for name, spec in historical_files.items():
        filepath = spec["path"]
        assert filepath.exists(), f"Historical benchmark file missing: {filepath}"

        raw_bytes = filepath.read_bytes()
        actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        assert actual_sha256 == spec["expected_sha256"], (
            f"IMMUTABILITY VIOLATION: {filepath.name} SHA-256 digest has changed! "
            f"Expected {spec['expected_sha256']}, got {actual_sha256}"
        )

        data = json.loads(raw_bytes.decode("utf-8"))
        assert data.get("total_scenarios") == spec["total_scenarios"]

        c4_res = data.get("binary_detection_metrics", {})
        assert c4_res.get("f1_score") == spec["c4_f1"]

        baselines = data.get("baselines", {})
        assert baselines.get("conventional_ci_f1") == spec["ci_f1"]

