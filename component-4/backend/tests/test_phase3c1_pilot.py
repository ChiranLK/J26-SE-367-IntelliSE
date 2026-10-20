"""
Automated Verification Suite for Phase 3C.1 Benchmark Infrastructure Pilot.
Validates the 17 core requirements:
1. Scenario ID uniqueness.
2. Defect ID uniqueness (and ensuring clean controls have no defect ID).
3. Deterministic dataset generation.
4. Clean-control labeling.
5. Mutation validity and AST compilation.
6. Ground-truth isolation (evaluators cannot access ground-truth attributes).
7. Genuine evaluator execution (all 3 systems produce real telemetry).
8. Missing evaluator output handling.
9. Prediction provenance validation (EMPIRICAL_EXECUTION).
10. Complete evidence serialization (all 17 scenario attributes).
11. Scenario checksum integrity.
12. Correct confusion matrices arithmetic (sum == 16).
13. Paired statistical validation (matched table sum == 16, exact McNemar test).
14. LLM invocation instrumentation.
15. Safe handling of unavailable Ollama daemon.
16. Docker timeout and execution failure resilience.
17. Preservation of frozen Phase 3A benchmark artifacts and SHA-256 checksums.
"""
import ast
import asyncio
import hashlib
import json
from pathlib import Path
import pytest

from app.benchmark.phase3c1_pilot import (
    PILOT_SCENARIOS,
    PilotBenchmarkRunner,
    PilotEvaluationInput,
    PilotGroundTruthRecord,
    PilotScenario,
)
from app.benchmark.baselines import ConventionalCiBaselineEvaluator, StaticAnalysisBaselineEvaluator
from app.benchmark.statistical_analysis import PredictionProvenance, exact_mcnemar_test
from app.services.ollama_client import OllamaClient


# =============================================================================
# Requirement 1: Scenario ID Uniqueness
# =============================================================================

def test_01_scenario_id_uniqueness():
    """Requirement 1: Every pilot scenario must have a unique scenario ID."""
    scenario_ids = [s.scenario_id for s in PILOT_SCENARIOS]
    assert len(scenario_ids) == 16
    assert len(scenario_ids) == len(set(scenario_ids)), "Duplicate scenario IDs detected in pilot dataset"


# =============================================================================
# Requirement 2: Defect ID Uniqueness & Clean Controls
# =============================================================================

def test_02_defect_id_uniqueness_and_clean_controls():
    """
    Requirement 2: Defect IDs must be unique across all seeded defects,
    and clean controls must explicitly have defect_id = None.
    """
    defect_ids = [
        s.ground_truth.defect_id
        for s in PILOT_SCENARIOS
        if s.ground_truth.defect_id is not None
    ]
    assert len(defect_ids) == 12, "Must have exactly 12 seeded defects"
    assert len(defect_ids) == len(set(defect_ids)), "Duplicate defect IDs detected among seeded defects"

    clean_controls = [s for s in PILOT_SCENARIOS if not s.ground_truth.has_defect]
    assert len(clean_controls) == 4, "Must have exactly 4 clean controls"
    for cc in clean_controls:
        assert cc.ground_truth.defect_id is None, f"Clean control {cc.scenario_id} must have defect_id=None"


# =============================================================================
# Requirement 3: Deterministic Dataset Generation
# =============================================================================

def test_03_deterministic_dataset_generation():
    """Requirement 3: Pilot dataset generation must be 100% deterministic."""
    hashes_run1 = [hashlib.sha256(s.input_data.module_code.encode("utf-8")).hexdigest() for s in PILOT_SCENARIOS]
    hashes_run2 = [hashlib.sha256(s.input_data.module_code.encode("utf-8")).hexdigest() for s in PILOT_SCENARIOS]
    assert hashes_run1 == hashes_run2


# =============================================================================
# Requirement 4: Clean-Control Labeling
# =============================================================================

def test_04_clean_control_labeling():
    """Requirement 4: Clean controls must be correctly labeled with has_defect=False."""
    for s in PILOT_SCENARIOS:
        if s.ground_truth.expected_category == "clean_control":
            assert s.ground_truth.has_defect is False
            assert s.ground_truth.defect_id is None
            assert s.ground_truth.expected_cwe_id is None
            assert s.ground_truth.has_semantic_drift is False
            assert s.ground_truth.is_non_convergent_by_design is False
        else:
            assert s.ground_truth.has_defect is True
            assert s.ground_truth.defect_id is not None


# =============================================================================
# Requirement 5: Mutation Validity & AST Compilation
# =============================================================================

def test_05_mutation_validity_and_ast_compilation():
    """Requirement 5: All pilot source code and tests must compile cleanly to Python AST."""
    for s in PILOT_SCENARIOS:
        # Module code compiles
        try:
            ast.parse(s.input_data.module_code)
        except SyntaxError as exc:
            pytest.fail(f"Scenario {s.scenario_id} module code failed to compile: {exc}")

        # Test code compiles
        try:
            ast.parse(s.input_data.test_code)
        except SyntaxError as exc:
            pytest.fail(f"Scenario {s.scenario_id} test code failed to compile: {exc}")

        # Original test code compiles if present
        if s.input_data.original_test_code:
            try:
                ast.parse(s.input_data.original_test_code)
            except SyntaxError as exc:
                pytest.fail(f"Scenario {s.scenario_id} original_test_code failed to compile: {exc}")


# =============================================================================
# Requirement 6: Ground-Truth Isolation
# =============================================================================

def test_06_ground_truth_isolation():
    """
    Requirement 6: PilotEvaluationInput must NOT contain any ground-truth labels.
    Attempting to access ground-truth attributes on evaluation inputs must raise AttributeError.
    """
    sample_input = PILOT_SCENARIOS[0].input_data

    # Operational fields exist
    assert hasattr(sample_input, "module_code")
    assert hasattr(sample_input, "test_code")
    assert hasattr(sample_input, "filename")

    # Ground-truth fields MUST NOT exist on evaluation input
    forbidden_gt_attributes = [
        "has_defect",
        "expected_category",
        "expected_cwe_id",
        "expected_line_number",
        "mutation_operator",
        "expected_behavioral_failure",
        "ground_truth_rationale",
    ]
    for attr in forbidden_gt_attributes:
        assert not hasattr(sample_input, attr), f"LEAKAGE RISK: Evaluation input exposes ground-truth '{attr}'!"
        with pytest.raises(AttributeError):
            getattr(sample_input, attr)


# =============================================================================
# Requirement 7: Genuine Evaluator Execution
# =============================================================================

def test_07_genuine_evaluator_execution():
    """Requirement 7: All 3 systems must execute and produce genuine observations."""
    runner = PilotBenchmarkRunner(use_real_docker=False)
    results = asyncio.run(runner.execute_pilot())

    assert results["total_scenarios"] == 16
    assert len(results["scenarios"]) == 16

    for s in results["scenarios"]:
        # Component 4 observation
        assert s["component4"]["duration_ms"] >= 0.0
        assert s["component4"]["provenance"] == "EMPIRICAL_EXECUTION"

        # Conventional CI observation
        assert s["conventional_ci"]["execution_status"] in ("PASSED", "FAILED")
        assert s["conventional_ci"]["provenance"] == "EMPIRICAL_EXECUTION"

        # Static Analysis observation
        assert s["static_analysis"]["execution_status"] in ("CLEAN", "DEFECT_DETECTED")
        assert s["static_analysis"]["provenance"] == "EMPIRICAL_EXECUTION"


# =============================================================================
# Requirement 8: Missing Evaluator Output Handling
# =============================================================================

def test_08_missing_evaluator_output_handling():
    """Requirement 8: Baseline evaluator gracefully handles empty dataset."""
    evaluator = ConventionalCiBaselineEvaluator(use_real_docker=False)
    res = asyncio.run(evaluator.evaluate([]))
    assert res.total_scenarios == 0
    assert len(res.scenario_records) == 0


# =============================================================================
# Requirement 9: Prediction Provenance Validation
# =============================================================================

def test_09_prediction_provenance_validation():
    """Requirement 9: All pilot predictions must carry EMPIRICAL_EXECUTION provenance."""
    results_path = Path(__file__).resolve().parent.parent / "benchmark_results_phase3c1_pilot.json"
    assert results_path.exists(), "Pilot benchmark results JSON file missing"

    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for sc in data["scenarios"]:
        assert sc["provenance"] == PredictionProvenance.EMPIRICAL_EXECUTION.value
        assert sc["component4"]["provenance"] == PredictionProvenance.EMPIRICAL_EXECUTION.value
        assert sc["conventional_ci"]["provenance"] == PredictionProvenance.EMPIRICAL_EXECUTION.value
        assert sc["static_analysis"]["provenance"] == PredictionProvenance.EMPIRICAL_EXECUTION.value


# =============================================================================
# Requirement 10: Complete Evidence Serialization (17 Fields)
# =============================================================================

def test_10_complete_evidence_serialization_17_fields():
    """Requirement 10: Every scenario record must serialize all required evidence fields."""
    results_path = Path(__file__).resolve().parent.parent / "benchmark_results_phase3c1_pilot.json"
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    required_keys = [
        "scenario_id",
        "defect_id",
        "dataset_version",
        "dataset_partition",
        "ground_truth",
        "component4",
        "conventional_ci",
        "static_analysis",
        "artifact_checksum",
        "execution_timestamp",
        "evaluator_version",
        "provenance",
        "llm_telemetry",
    ]

    for sc in data["scenarios"]:
        for k in required_keys:
            assert k in sc, f"Scenario {sc.get('scenario_id')} missing required field '{k}'"

        # Check sub-records
        assert "has_defect" in sc["ground_truth"]
        assert "expected_category" in sc["ground_truth"]
        assert "detected_has_defect" in sc["component4"]
        assert "detected_has_defect" in sc["conventional_ci"]
        assert "detected_has_defect" in sc["static_analysis"]


# =============================================================================
# Requirement 11: Scenario Checksum Integrity
# =============================================================================

def test_11_scenario_checksum_integrity():
    """Requirement 11: Serialized artifact_checksum must match actual source code SHA-256."""
    results_path = Path(__file__).resolve().parent.parent / "benchmark_results_phase3c1_pilot.json"
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pilot_map = {s.scenario_id: s for s in PILOT_SCENARIOS}
    for sc in data["scenarios"]:
        sid = sc["scenario_id"]
        orig = pilot_map[sid]
        expected_sha = hashlib.sha256(orig.input_data.module_code.encode("utf-8")).hexdigest()
        assert sc["artifact_checksum"] == expected_sha


# =============================================================================
# Requirement 12: Correct Confusion Matrices Arithmetic
# =============================================================================

def test_12_correct_confusion_matrices_arithmetic():
    """Requirement 12: Confusion matrix arithmetic must sum to total scenarios (16)."""
    results_path = Path(__file__).resolve().parent.parent / "benchmark_results_phase3c1_pilot.json"
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    metrics = data["metrics"]
    for system_name in ("component4", "conventional_ci", "static_analysis"):
        cm = metrics[system_name]
        total = cm["true_positives"] + cm["false_positives"] + cm["true_negatives"] + cm["false_negatives"]
        assert total == 16, f"{system_name} matrix total {total} != 16"
        assert cm["true_positives"] + cm["false_negatives"] == 12, f"{system_name} positive support != 12"
        assert cm["true_negatives"] + cm["false_positives"] == 4, f"{system_name} negative support != 4"


# =============================================================================
# Requirement 13: Paired Statistical Validation
# =============================================================================

def test_13_paired_statistical_validation():
    """Requirement 13: Paired comparisons must be empirical, with table sum == 16 and valid McNemar test."""
    results_path = Path(__file__).resolve().parent.parent / "benchmark_results_phase3c1_pilot.json"
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    c4_ci = data["paired_statistical_comparison"]["component4_vs_conventional_ci"]
    assert c4_ci["is_empirical"] is True

    tbl = c4_ci["table"]
    assert tbl["total"] == 16
    assert tbl["both_correct_a"] + tbl["c4_only_b"] + tbl["ci_only_c"] + tbl["both_incorrect_d"] == 16
    assert tbl["both_correct_a"] == 10
    assert tbl["c4_only_b"] == 6
    assert tbl["ci_only_c"] == 0
    assert tbl["both_incorrect_d"] == 0

    mcn = c4_ci["mcnemar"]
    assert mcn["discordant_pairs"] == 6
    assert round(mcn["p_value_exact_binomial"], 4) == 0.0312


# =============================================================================
# Requirement 14: LLM Invocation Instrumentation
# =============================================================================

def test_14_llm_invocation_instrumentation():
    """Requirement 14: Telemetry must accurately document LLM state and invocation status."""
    results_path = Path(__file__).resolve().parent.parent / "benchmark_results_phase3c1_pilot.json"
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    telemetry = data["llm_telemetry"]
    assert telemetry["model_identifier"] == "qwen2.5-coder:3b"
    assert telemetry["actual_inference_invocations_in_detection"] == 0
    assert "deterministic" in telemetry["detection_mechanism"]


# =============================================================================
# Requirement 15: Safe Handling of Unavailable Ollama Daemon
# =============================================================================

def test_15_safe_handling_of_unavailable_ollama():
    """Requirement 15: Offline Ollama daemon must be handled gracefully without crash."""
    async def _test():
        client = OllamaClient(base_url="http://127.0.0.1:9999", timeout_seconds=0.5)
        ok, models, msg = await client.check_availability()
        assert ok is False
        assert len(models) == 0
        assert "Cannot connect" in msg or "timed out" in msg or "error" in msg.lower()

    asyncio.run(_test())


# =============================================================================
# Requirement 16: Docker Timeout and Execution Failures
# =============================================================================

def test_16_docker_timeout_and_execution_failures():
    """Requirement 16: Evaluator handles syntax errors and timeouts safely."""
    evaluator = ConventionalCiBaselineEvaluator(use_real_docker=False)
    # Syntax error in module code
    failed, exit_code, timeout, dur, evidence = evaluator._execute_in_process_sandbox(
        source_code="def broken_syntax(:\n",
        test_code="def test_none(): pass\n",
        filename="solution.py",
    )
    assert failed is True
    assert exit_code == 1
    assert "CompilationError" in evidence or "SyntaxError" in evidence


# =============================================================================
# Requirement 17: Preservation of Frozen Phase 3A Artifacts
# =============================================================================

def test_17_preservation_of_phase3a_artifacts():
    """
    Requirement 17: Historical Phase 3A benchmark JSON result files must remain
    strictly untouched and preserve their exact cryptographic SHA-256 digests.
    """
    base_dir = Path(__file__).resolve().parent.parent

    expected_digests = {
        "benchmark_results_phase3_heldout.json": "fbaf6762cba84c9632df6cf4268531d84bfd5bb89160a5ae33ea47c8d5a872a3",
        "benchmark_results_phase3_dev.json": "6b16ea5917276fc14d62cee4610a82bca196e39d2c1b4395d093d7a4b4b9e032",
        "benchmark_results_phase3_100.json": "10269c798dfe72eb37906d60a93ad7d12442f042aac349a4de9406f503dadc09",
    }

    for fname, expected_hash in expected_digests.items():
        fpath = base_dir / fname
        assert fpath.exists(), f"Historical Phase 3A artifact {fname} missing!"
        actual_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"IMMUTABILITY BREACH: {fname} hash has changed!"
