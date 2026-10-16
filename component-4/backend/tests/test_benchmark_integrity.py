"""
Research Methodology Integrity Tests for INTELISE Component 4 (Proposal Section 3.8, SO6).

Validates:
1. Ground-Truth Independence: Altering ground-truth labels without changing source code
   or tests CANNOT alter detector predictions.
2. Semantic Drift Evaluation: Evaluates both positive and negative drift controls
   without inspecting expected drift labels.
3. Category Misclassification Rigor: Misclassifications symmetrically increment False Negatives
   on the expected category and False Positives on the falsely predicted category.
4. Convergence and Escalation Transparency: Reports unmeasured scenarios as NOT EVALUATED
   rather than claiming artificial success.
5. Negative Security Controls: Secure code patterns are not falsely classified as vulnerabilities.
"""
import asyncio
import pytest
from app.benchmark.evaluator import BenchmarkEvaluator
from app.benchmark.models import BenchmarkScenario, BenchmarkScenarioGroup
from app.benchmark.revised_dataset import REVISED_BENCHMARK_SCENARIOS
from app.schemas.common import DefectCategory, TestResultStatus, TestType


def test_ground_truth_label_mutation_cannot_alter_predictions():
    """
    CRITICAL METHODOLOGICAL INTEGRITY TEST:
    Proves mathematically and empirically that mutating ground-truth labels
    (has_defect, expected_defect_category, has_semantic_drift, scenario_group)
    has ZERO effect on the evaluator's observed detection and classification.
    """
    async def _run():
        evaluator = BenchmarkEvaluator(use_real_docker=False)

        # 1. Take a baseline defective functional scenario
        original_scenario = BenchmarkScenario(
            scenario_id="TEST-INTG-01",
            name="Slice Boundary Defect",
            scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
            module_code="""
def slice_items(items, page, size):
    # Bug: off-by-one 1-based page without decrement
    return items[page * size : (page + 1) * size]
""",
            test_code="""
import solution

def test_slice():
    res = solution.slice_items([1, 2, 3, 4], page=1, size=2)
    assert res == [1, 2]
""",
            has_defect=True,
            expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
            has_semantic_drift=False,
            expected_system_behavior="Expose functional defect",
        )

        # 2. Execute original scenario
        test_res_1, _, _ = await evaluator._execute_scenario(original_scenario)
        status_1 = "FAILED" if any(t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR) for t in test_res_1) else "PASSED"
        defects_1 = evaluator.defect_service.analyze_test_results(
            run_id="run-orig",
            submission_id="sub-orig",
            status=status_1,
            test_results=test_res_1,
            affected_filename=original_scenario.filename,
            source_code=original_scenario.module_code,
        )

        # 3. Create adversarial mutation with completely inverted ground-truth labels:
        # claims to be clean control, has_defect=False, expected=SECURITY_VULNERABILITY, has_drift=True
        adversarial_scenario = original_scenario.model_copy(
            update={
                "scenario_group": BenchmarkScenarioGroup.CLEAN_CONTROL,
                "has_defect": False,
                "expected_defect_category": DefectCategory.SECURITY_VULNERABILITY,
                "has_semantic_drift": True,
                "expected_system_behavior": "Adversarial fake label assertion",
            }
        )

        # 4. Execute mutated scenario
        test_res_2, _, _ = await evaluator._execute_scenario(adversarial_scenario)
        status_2 = "FAILED" if any(t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR) for t in test_res_2) else "PASSED"
        defects_2 = evaluator.defect_service.analyze_test_results(
            run_id="run-adv",
            submission_id="sub-adv",
            status=status_2,
            test_results=test_res_2,
            affected_filename=adversarial_scenario.filename,
            source_code=adversarial_scenario.module_code,
        )

        # 5. Predictions MUST be 100% identical regardless of ground-truth mutation
        assert status_1 == status_2 == "FAILED"
        assert len(defects_1) == len(defects_2) == 1
        assert defects_1[0].defect_category == defects_2[0].defect_category == "functional_bug"
        assert defects_1[0].failure_category == defects_2[0].failure_category == "ASSERTION_FAILURE"
        assert defects_1[0].line_number == defects_2[0].line_number

    asyncio.run(_run())


def test_semantic_drift_evaluates_positive_and_negative_controls():
    """
    Verifies that semantic drift analysis executes independently on both
    drift-positive and drift-negative scenarios without checking answer labels.
    """
    async def _run():
        evaluator = BenchmarkEvaluator(use_real_docker=False)

        # Drift scenarios from revised dataset: 2 positive, 2 negative controls
        drift_scenarios = [s for s in REVISED_BENCHMARK_SCENARIOS if "DRIFT" in s.scenario_id]
        assert len(drift_scenarios) == 4

        summary = await evaluator.run_evaluation(scenarios=drift_scenarios, save_to_file=False)

        drift_metrics = summary.semantic_drift_metrics
        assert drift_metrics is not None
        assert drift_metrics["scenarios_evaluated"] == 4
        # 2 true positives (assertion weakened, test deleted)
        assert drift_metrics["true_positives"] == 2
        # 2 true negatives (clean refactoring, test addition)
        assert drift_metrics["true_negatives"] == 2
        # 0 false positives, 0 false negatives
        assert drift_metrics["false_positives"] == 0
        assert drift_metrics["false_negatives"] == 0
        assert drift_metrics["precision"] == 1.0
        assert drift_metrics["recall"] == 1.0
        assert drift_metrics["f1_score"] == 1.0

    asyncio.run(_run())


def test_negative_security_controls_prevent_false_positives():
    """
    Verifies that clean code patterns (parameterized queries, shell=False, path confinement)
    do NOT trigger false positive security classifications.
    """
    async def _run():
        evaluator = BenchmarkEvaluator(use_real_docker=False)
        security_controls = [s for s in REVISED_BENCHMARK_SCENARIOS if s.scenario_id.startswith("REV-CLEAN-0")]

        summary = await evaluator.run_evaluation(scenarios=security_controls, save_to_file=False)

        # Clean controls must have 0 false positives across all categories
        sec_metric = summary.category_metrics["security_vulnerability"]
        assert sec_metric.false_positives == 0

        bin_metric = summary.binary_detection_metrics
        assert bin_metric["false_positives"] == 0
        assert bin_metric["true_negatives"] == len(security_controls)

    asyncio.run(_run())


def test_symmetric_category_misclassification_scoring():
    """
    Verifies that category misclassification correctly increments both
    False Negative for the missed expected category AND False Positive for the falsely predicted category.
    """
    async def _run():
        evaluator = BenchmarkEvaluator(use_real_docker=False)

        # Construct scenario where ground-truth is security_vulnerability,
        # but code only fails a functional assertion without any security AST pattern
        mismatched_scenario = BenchmarkScenario(
            scenario_id="TEST-MISCLASS-01",
            name="Mismatched Category Test",
            scenario_group=BenchmarkScenarioGroup.SECURITY_VULNERABILITY,
            module_code="""
def calculate(a, b):
    return a + b + 1  # Logic bug, zero security patterns
""",
            test_code="""
import solution

def test_calc():
    assert solution.calculate(2, 2) == 4
""",
            has_defect=True,
            expected_defect_category=DefectCategory.SECURITY_VULNERABILITY,  # Ground truth expects security
            has_semantic_drift=False,
            expected_system_behavior="Will predict functional bug, causing symmetric scoring",
        )

        summary = await evaluator.run_evaluation(scenarios=[mismatched_scenario], save_to_file=False)

        # Missed security category must have 1 FN
        assert summary.category_metrics["security_vulnerability"].false_negatives == 1
        assert summary.category_metrics["security_vulnerability"].true_positives == 0

        # Falsely predicted functional_bug category must have 1 FP
        assert summary.category_metrics["functional_bug"].false_positives == 1
        assert summary.category_metrics["functional_bug"].true_positives == 0

    asyncio.run(_run())


def test_single_pass_scenarios_report_convergence_not_evaluated():
    """
    Verifies that scenarios not executed through the iterative repair harness
    are explicitly reported as NOT_EVALUATED rather than falsely counted as successful.
    """
    async def _run():
        evaluator = BenchmarkEvaluator(use_real_docker=False)
        single_pass_scenario = BenchmarkScenario(
            scenario_id="TEST-SINGLE-PASS",
            name="Single Pass Scenario",
            scenario_group=BenchmarkScenarioGroup.FUNCTIONAL_BUG,
            module_code="def f(): return 1",
            test_code="import solution\ndef test_f(): assert solution.f() == 2",
            has_defect=True,
            expected_defect_category=DefectCategory.FUNCTIONAL_BUG,
            is_repair_loop_scenario=False,
            repair_candidate_patches=None,
            expected_system_behavior="Single-pass execution",
        )

        summary = await evaluator.run_evaluation(scenarios=[single_pass_scenario], save_to_file=False)
        assert summary.convergence_repair_metrics["scenarios_evaluated"] == 0

    asyncio.run(_run())
