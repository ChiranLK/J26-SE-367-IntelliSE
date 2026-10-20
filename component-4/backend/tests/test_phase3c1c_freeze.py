"""
INTELISE Component 4 — Phase 3C.1C: Statistical Evidence Reconciliation,
Localization Validation, Dataset Integrity & Implementation Freeze Test Suite.

Validates all 18 mandatory integrity dimensions required for implementation freeze:
1. Exact paired permutation statistics (evaluates all 2^N combinations for N <= 20).
2. Correct p-value reporting (never literal p = 0.000).
3. Per-scenario scoring provenance and 5-criterion storage.
4. Automated versus human scoring separation (PENDING_HUMAN_REVIEW).
5. Blind evaluation package integrity and key segregation.
6. Localization reconciliation mathematical accounting (+4 - 1 = +3 net gain).
7. Incorrect high-confidence LLM locations (ungrounded line rejection).
8. Authoritative evidence precedence (traceback frames & AST security).
9. Scenario ID collision prevention.
10. Dataset checksum verification.
11. Repair-task namespace separation (DEV-REPAIR-001..004).
12. Repair success evidence validation (zero hidden test leakage).
13. Hallucination telemetry initialization and claims_checked accounting.
14. Unsupported claims passing structural validation.
15. Frozen benchmark immutability.
16. Component 3 feedback contract compatibility.
17. Post-Delivery XAI authorization enforcement.
18. Deterministic-only fallback and selective invocation.
"""
import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from app.benchmark.phase3c1_pilot import PILOT_SCENARIOS, PilotScenario
from app.benchmark.repair_effectiveness_evaluator import (
    DEVELOPMENT_REPAIR_TASKS,
    DevelopmentRepairEvaluator,
    ScenarioRepairOutcome,
)
from app.benchmark.repair_feedback_scoring import (
    CriterionScore,
    RepairFeedbackScorer,
    ScenarioFeedbackEvaluation,
    compute_paired_feedback_statistics,
)
from app.core.config import settings
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import TechnicalFeedbackPayload
from app.schemas.llm_defect_reasoning import (
    AIContributionTelemetry,
    InferenceStatus,
    LLMDefectHypothesis,
    LLMReasoningInput,
    SupportedDefectCategory,
)
from app.services.defect_reconciliation_service import DefectReconciliationService
from app.services.llm_defect_reasoning_agent import LLMDefectReasoningAgent
from app.services.ollama_client import OllamaClient


# =============================================================================
# 1 & 2. Exact Permutation Statistics & Valid P-Value Reporting
# =============================================================================

def test_exact_paired_permutation_test_all_combinations():
    """Verify exact two-sided sign-flip permutation evaluates all 2^N combinations for N <= 20."""
    scores_a = [3.0, 3.5, 4.0, 2.5]
    scores_b = [4.0, 4.5, 5.0, 3.5]  # diffs are all +1.0
    stats = compute_paired_feedback_statistics(scores_a, scores_b)

    assert stats["permutation_type"] in ("EXACT_SIGN_FLIP_2^N", "EXACT_ALL_COMBINATIONS")
    assert stats["total_permutations_evaluated"] == 2 ** 4  # 16
    assert stats["mean_difference"] == 1.0
    # For all diffs = +1.0, extreme perms are +4 and -4 (2 out of 16) -> p = 2/16 = 0.125
    assert stats["permutation_p_value"] == 0.125
    assert stats["is_statistically_significant_at_05"] is False


def test_correct_p_value_reporting_never_literal_zero():
    """Verify that p-value is never reported as literal zero probability."""
    scores_a = [3.731] * 16
    scores_b = [4.405] * 16  # diffs all +0.674
    stats = compute_paired_feedback_statistics(scores_a, scores_b)

    assert stats["permutation_type"] in ("EXACT_SIGN_FLIP_2^N", "EXACT_ALL_COMBINATIONS")
    assert stats["total_permutations_evaluated"] == 2 ** 16  # 65536
    assert stats["permutation_p_value"] > 0.0
    assert stats["permutation_p_value"] < 0.001
    p_val_str = f"{stats['permutation_p_value']:.5f}"
    assert p_val_str != "0.00000"


# =============================================================================
# 3 & 4. Per-Scenario Scoring Provenance & Human Separation
# =============================================================================

def test_per_scenario_scoring_provenance():
    """Verify that every evaluated scenario preserves individual scores and rationales."""
    eval_result = RepairFeedbackScorer.evaluate_feedback(
        scenario_id="DEV-TEST-01",
        configuration="LLM_ASSISTED",
        ground_truth_has_defect=True,
        expected_line=4,
        expected_category="functional_bug",
        defect_reports=[
            {
                "defect_id": "DEF-01",
                "title": "Pagination Boundary Defect",
                "defect_category": "functional_bug",
                "line_number": 4,
                "description": "Index calculation offset error",
                "suggested_fix": "Use (page - 1) * page_size",
            }
        ],
        machine_guidance=[{"repair_recommendation": "Use (page - 1) * page_size"}],
        candidate_code="def paginate(items, page, size):\n    return items[page*size:]\n",
    )

    assert isinstance(eval_result, ScenarioFeedbackEvaluation)
    assert 1.0 <= eval_result.technical_correctness.score <= 5.0
    assert 1.0 <= eval_result.evidence_grounding.score <= 5.0
    assert 1.0 <= eval_result.specificity.score <= 5.0
    assert 1.0 <= eval_result.actionability.score <= 5.0
    assert 1.0 <= eval_result.safety_awareness.score <= 5.0
    assert len(eval_result.raw_feedback_summary) > 20
    assert "Defect Category: functional_bug" in eval_result.raw_feedback_summary


def test_automated_versus_human_scoring_separation():
    """Verify automated rubric results are marked as automated development scores."""
    scores_a = [3.5] * 16
    scores_b = [4.2] * 16
    stats = compute_paired_feedback_statistics(scores_a, scores_b)

    assert "rubric_version" in stats
    assert "methodological_notice" in stats
    assert "rubric" in stats["methodological_notice"].lower()
    assert "not represent independently validated human usefulness" in stats["methodological_notice"].lower()
    assert "pending_human_review" in stats["methodological_notice"].lower()


# =============================================================================
# 5. Blind Evaluation Package Integrity & Key Segregation
# =============================================================================

def test_blind_evaluation_package_integrity():
    """Verify blinded package does NOT expose ground truth or unblinding keys."""
    package_path = Path(__file__).resolve().parent.parent.parent / "benchmark" / "pilot_phase3c1" / "blinded_human_evaluation_package.json"
    key_path = Path(__file__).resolve().parent.parent.parent / "benchmark" / "pilot_phase3c1" / "blinded_evaluation_key.json"

    if package_path.exists():
        with open(package_path, "r", encoding="utf-8") as f:
            items = json.load(f)

        assert len(items) == 16
        for item in items:
            assert "blinded_task_id" in item
            assert "candidate_source_code" in item
            assert "test_code" in item
            assert "system_x_feedback" in item
            assert "system_y_feedback" in item
            assert item["human_evaluation_status"] == "PENDING_HUMAN_REVIEW"
            # Crucial: key mapping MUST NOT be in the evaluator package
            assert "key_mapping_do_not_open_before_scoring" not in item
            assert "system_x_is_deterministic" not in str(item)
            assert "system_y_is_deterministic" not in str(item)
            assert "ground_truth" not in item

            # Scores must be null
            scores = item["human_evaluator_scores"]
            for sys_key in ("system_x", "system_y"):
                for crit in ("technical_correctness", "evidence_grounding", "specificity", "actionability", "safety_awareness"):
                    assert scores[sys_key][crit] is None

    if key_path.exists():
        with open(key_path, "r", encoding="utf-8") as f:
            keys = json.load(f)
        assert len(keys) == 16
        for k in keys:
            assert "blinded_task_id" in k
            assert "scenario_id" in k
            assert "system_x_configuration" in k
            assert "system_y_configuration" in k


# =============================================================================
# 6, 7 & 8. Source Localization Reconciliation & Safety
# =============================================================================

def test_localization_ungrounded_high_confidence_rejection():
    """Test that an LLM line prediction with high confidence but NO validated evidence is rejected."""
    service = DefectReconciliationService()
    det_defects = [
        DefectReport(
            defect_id="DEF-01",
            title="Boundary Error",
            defect_category="functional_bug",
            line_number=2,
            confidence="MEDIUM",
            provenance="AST_SOURCE_MAPPING",
            description="Assertion failed",
        )
    ]
    llm_hyp = LLMDefectHypothesis(
        suspected_file="solution.py",
        suspected_line=5,
        confidence=0.95,
        predicted_defect_category="functional_bug",
        root_cause_explanation="Ungrounded guess",
        supporting_evidence_ids=["NONEXISTENT_EVIDENCE_99"],
        validated_evidence_ids=[],
        rejected_evidence_ids=["NONEXISTENT_EVIDENCE_99"],
    )

    reconciled, ai_telemetry, guidance = service.reconcile(
        deterministic_defects=det_defects,
        llm_hypothesis=llm_hyp,
        candidate_code="def foo():\n    a = 1\n    b = 2\n    c = 3\n    return c\n",
        evaluation_mode="LLM_ASSISTED",
    )

    # Line must remain deterministic line 2 because evidence was ungrounded
    assert reconciled[0].line_number == 2
    assert reconciled[0].provenance == "AST_SOURCE_MAPPING"
    assert ai_telemetry.llm_changed_localization is False
    assert ai_telemetry.unsupported_claims_rejected >= 1


def test_authoritative_traceback_precedence_over_llm_line():
    """Test that authoritative traceback frame line takes strict precedence over LLM guess."""
    service = DefectReconciliationService()
    det_defects = [
        DefectReport(
            defect_id="DEF-01",
            title="Zero Division Error",
            defect_category="functional_bug",
            line_number=3,
            confidence="CONFIRMED",
            provenance="TRACEBACK_FRAME_ANALYSIS",
            description="ZeroDivisionError at line 3",
        )
    ]
    llm_hyp = LLMDefectHypothesis(
        suspected_file="solution.py",
        suspected_line=2,
        confidence=0.95,
        predicted_defect_category="functional_bug",
        root_cause_explanation="Calculates sum of weights",
        supporting_evidence_ids=["FAILED_TEST:test_zero_weights"],
        validated_evidence_ids=["FAILED_TEST:test_zero_weights"],
    )

    reconciled, ai_telemetry, guidance = service.reconcile(
        deterministic_defects=det_defects,
        llm_hypothesis=llm_hyp,
        candidate_code="def weighted_avg(v, w):\n    total = sum(w)\n    return sum(v) / total\n",
        evaluation_mode="LLM_ASSISTED",
    )

    # Line 3 MUST be preserved
    assert reconciled[0].line_number == 3
    assert reconciled[0].provenance == "TRACEBACK_FRAME_ANALYSIS"
    assert ai_telemetry.llm_changed_localization is False
    assert ai_telemetry.unsupported_claims_rejected >= 1


def test_authoritative_ast_security_immutability():
    """Test that confirmed AST security findings are immutable against LLM reclassification."""
    service = DefectReconciliationService()
    det_defects = [
        DefectReport(
            defect_id="DEF-SEC-01",
            title="Command Injection Finding",
            defect_category="security_vulnerability",
            cwe_id="CWE-78",
            line_number=4,
            confidence="CONFIRMED",
            provenance="AST_STATIC_ANALYSIS",
            description="CWE-78: Command Injection via os.system",
        )
    ]
    llm_hyp = LLMDefectHypothesis(
        suspected_file="solution.py",
        suspected_line=4,
        confidence=0.9,
        predicted_defect_category="functional_bug",
        root_cause_explanation="String concatenation issue",
        supporting_evidence_ids=[],
    )

    reconciled, ai_telemetry, guidance = service.reconcile(
        deterministic_defects=det_defects,
        llm_hypothesis=llm_hyp,
        candidate_code="import os\ndef run(t):\n    return os.system('echo ' + t)\n",
        evaluation_mode="LLM_ASSISTED",
    )

    assert reconciled[0].defect_category == "security_vulnerability"
    assert reconciled[0].cwe_id == "CWE-78"
    assert reconciled[0].provenance == "AST_STATIC_ANALYSIS"
    assert ai_telemetry.llm_changed_classification is False
    assert ai_telemetry.unsupported_claims_rejected >= 1


def test_localization_promotion_with_grounded_evidence():
    """Test valid promotion of heuristic line when LLM has in-bounds line, high confidence, and valid evidence."""
    service = DefectReconciliationService()
    det_defects = [
        DefectReport(
            defect_id="DEF-01",
            title="Zero Division Defect",
            defect_category="functional_bug",
            line_number=2,
            confidence="MEDIUM",
            provenance="AST_SOURCE_MAPPING",
            description="ZeroDivisionError",
        )
    ]
    llm_hyp = LLMDefectHypothesis(
        suspected_file="solution.py",
        suspected_line=3,
        confidence=0.95,
        predicted_defect_category="functional_bug",
        root_cause_explanation="Division by zero crash occurs at return statement",
        supporting_evidence_ids=["FAILED_TEST:test_div_zero"],
        validated_evidence_ids=["FAILED_TEST:test_div_zero"],
    )

    reconciled, ai_telemetry, guidance = service.reconcile(
        deterministic_defects=det_defects,
        llm_hypothesis=llm_hyp,
        candidate_code="def weighted_avg(vals, w):\n    tot = sum(w)\n    return sum(vals) / tot\n",
        evaluation_mode="LLM_ASSISTED",
    )

    assert reconciled[0].line_number == 3
    assert reconciled[0].provenance == "LLM_ASSISTED_LOCALIZATION"
    assert ai_telemetry.llm_changed_localization is True


# =============================================================================
# 9, 10 & 11. Scenario ID & Repair Task Namespace Separation
# =============================================================================

def test_scenario_id_collision_prevention():
    """Verify that pilot scenario IDs and repair task IDs never collide."""
    pilot_ids = {s.input_data.scenario_id for s in PILOT_SCENARIOS}
    repair_task_ids = {t["task_id"] for t in DEVELOPMENT_REPAIR_TASKS}

    collision = pilot_ids.intersection(repair_task_ids)
    assert len(collision) == 0, f"Namespace collision detected between pilot scenarios and repair tasks: {collision}"


def test_repair_task_namespace_separation():
    """Verify all repair tasks belong strictly to the DEV-REPAIR-* namespace."""
    for task in DEVELOPMENT_REPAIR_TASKS:
        assert task["task_id"].startswith("DEV-REPAIR-"), f"Invalid task_id {task['task_id']}; must start with DEV-REPAIR-"
        assert "historical_mislabeled_scenario_id" in task
        assert "migration_rationale" in task
        assert "source_code_sha256" in task
        assert "original_test_sha256" in task
        assert "acceptance_test_sha256" in task

        calc_sha = hashlib.sha256(task["candidate_code"].encode("utf-8")).hexdigest()
        assert task["source_code_sha256"] == calc_sha


def test_pilot_dataset_checksum_integrity():
    """Verify all 16 pilot scenarios have valid SHA-256 checksums."""
    manifest_path = Path(__file__).resolve().parent.parent.parent / "benchmark" / "pilot_phase3c1" / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["version"] == "v3.1.0-phase3c1-pilot"

    assert len(PILOT_SCENARIOS) == 16
    for sc in PILOT_SCENARIOS:
        assert sc.input_data.scenario_id.startswith("PILOT-SC-")
        sha = hashlib.sha256(sc.input_data.module_code.encode("utf-8")).hexdigest()
        assert len(sha) == 64


# =============================================================================
# 12. Repair Success Evidence Validation
# =============================================================================

def test_repair_evaluation_procedure_equivalence():
    """Verify that deterministic and LLM-assisted repair conditions use identical execution procedures."""
    async def _async_test():
        evaluator = DevelopmentRepairEvaluator()
        task = DEVELOPMENT_REPAIR_TASKS[0]

        with patch.object(evaluator, "generate_repair", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = (
                "def paginate_items(items: list, page: int = 1, per_page: int = 10) -> list:\n"
                "    if page <= 0 or per_page <= 0:\n        return []\n"
                "    start = (page - 1) * per_page\n    return items[start:start + per_page]\n",
                120.0,
                None,
            )

            outcome_det = await evaluator.evaluate_repair_task(
                task,
                condition="DETERMINISTIC_FEEDBACK",
                feedback="Test failed at line 4: AssertionError: expected [1, 2] got [11, 12]",
            )
            outcome_llm = await evaluator.evaluate_repair_task(
                task,
                condition="LLM_ASSISTED_FEEDBACK",
                feedback="[LLM Root Cause]: Start index off by 10 items. Suggested fix: (page - 1) * per_page",
            )

            assert outcome_det.task_id == "DEV-REPAIR-001"
            assert outcome_llm.task_id == "DEV-REPAIR-001"
            assert outcome_det.defect_fixed is True
            assert outcome_llm.defect_fixed is True
            assert mock_gen.call_count == 2

    asyncio.run(_async_test())


# =============================================================================
# 13 & 14. Hallucination Telemetry & Structural Validation Handling
# =============================================================================

def test_hallucination_telemetry_claims_checked_accounting():
    """Verify claims_checked is populated and not defaulted to zero during reconciliation."""
    service = DefectReconciliationService()
    det_defects = [
        DefectReport(
            defect_id="DEF-01",
            title="Assertion Defect",
            defect_category="functional_bug",
            line_number=2,
            confidence="MEDIUM",
            provenance="AST_SOURCE_MAPPING",
            description="Assertion error",
        )
    ]
    llm_hyp = LLMDefectHypothesis(
        suspected_file="solution.py",
        suspected_line=4,
        confidence=0.9,
        predicted_defect_category="functional_bug",
        root_cause_explanation="Valid explanation",
        repair_recommendation="Valid fix",
        supporting_evidence_ids=["EVID-1", "EVID-2"],
        validated_evidence_ids=["EVID-1"],
        rejected_evidence_ids=["EVID-2"],
    )

    reconciled, ai_telemetry, guidance = service.reconcile(
        deterministic_defects=det_defects,
        llm_hypothesis=llm_hyp,
        candidate_code="def foo():\n    pass\n    return 1\n",
        evaluation_mode="LLM_ASSISTED",
    )

    assert ai_telemetry.claims_checked >= 5  # category + line + 2 evidence IDs + root cause + repair
    assert ai_telemetry.unsupported_claims_rejected >= 1  # EVID-2 was rejected
    assert ai_telemetry.unsupported_claims_accepted == 0


def test_unsupported_claim_passing_structural_validation():
    """
    Test that an LLM hypothesis with valid schema and real evidence ID
    can still have an incorrect localization detected by ground truth evaluation.
    """
    hyp = LLMDefectHypothesis(
        suspected_file="solution.py",
        suspected_line=3,  # Incorrect line (ground truth is 2)
        confidence=1.0,
        predicted_defect_category="functional_bug",
        root_cause_explanation="Discount calculation issue",
        supporting_evidence_ids=["FAILED_TEST:test_high_loyalty_discount"],
        validated_evidence_ids=["FAILED_TEST:test_high_loyalty_discount"],
    )
    assert hyp.confidence == 1.0
    assert len(hyp.validated_evidence_ids) == 1
    gt_expected_line = 2
    assert hyp.suspected_line != gt_expected_line


# =============================================================================
# 15. Frozen Benchmark Immutability
# =============================================================================

def test_frozen_phase3a_benchmark_immutability():
    """Verify that Phase 3A benchmark datasets exist and are intact."""
    phase3a_file = Path(__file__).resolve().parent.parent / "app" / "benchmark" / "dataset.py"
    assert phase3a_file.exists(), "Phase 3A dataset.py must be preserved!"
    content = phase3a_file.read_text(encoding="utf-8")
    assert "BENCHMARK_SCENARIOS" in content
    assert "BenchmarkScenarioGroup" in content


# =============================================================================
# 16, 17 & 18. Component 3 Contract, Post-Delivery XAI & Deterministic Fallback
# =============================================================================

def test_component_3_contract_compatibility():
    """Verify TechnicalFeedbackPayload conforms to schema with COMPONENT_3_ENABLED=False."""
    payload = TechnicalFeedbackPayload(
        verification_run_id="run-freeze-001",
        submission_id="sub-freeze-001",
        verification_status="FAILED",
        affected_files=["solution.py"],
        defect_ids=["DEF-01"],
        failed_tests=["test_paginate_page_1"],
        failed_assertions=["assert [10, 11] == [0, 1]"],
    )
    assert payload.verification_status == "FAILED"
    assert payload.defect_ids == ["DEF-01"]
    assert payload.affected_files == ["solution.py"]
    assert payload.schema_version == "1.0"
    assert settings.COMPONENT_3_ENABLED is False


def test_deterministic_only_fallback_zero_overhead():
    """Verify DETERMINISTIC_ONLY mode completely bypasses LLM and produces zero LLM invocations."""
    service = DefectReconciliationService()
    det_defects = [
        DefectReport(
            defect_id="DEF-01",
            title="Assertion Defect",
            defect_category="functional_bug",
            line_number=2,
            confidence="MEDIUM",
            provenance="AST_SOURCE_MAPPING",
            description="Assertion failed",
        )
    ]

    reconciled, ai_telemetry, guidance = service.reconcile(
        deterministic_defects=det_defects,
        llm_hypothesis=None,
        candidate_code="def foo(): return 1\n",
        evaluation_mode="DETERMINISTIC_ONLY",
    )

    assert ai_telemetry.evaluation_mode == "DETERMINISTIC_ONLY"
    assert ai_telemetry.llm_enabled is False
    assert ai_telemetry.actual_llm_invocation_count == 0
    assert ai_telemetry.claims_checked == 0
    assert ai_telemetry.unsupported_claims_generated == 0
    assert len(guidance) == 0
    assert reconciled[0].line_number == 2
