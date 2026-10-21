from app.schemas.common import DefectSeverity
from app.schemas.defect_report import DefectReport
from app.schemas.llm_defect_reasoning import InferenceStatus, LLMDefectHypothesis
from app.services.agent_testing_service import _project_files_for_test_type
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.defect_reconciliation_service import DefectReconciliationService
from app.services.verification_service import _has_categorized_project_tests


PROJECT_FILES = {
    "shop/pricing.py": "def apply_discount(value, rate):\n    return value\n",
    "tests/unit/test_unit_pricing.py": "def test_unit_apply_discount(): pass\n",
    "tests/integration/test_integration_checkout.py": "def test_integration_checkout(): pass\n",
    "tests/performance/test_performance_checkout.py": "def test_performance_checkout(): pass\n",
}


def test_categorized_project_suites_are_kept_separate():
    metadata = {"project_files": PROJECT_FILES}
    assert _has_categorized_project_tests(metadata) is True
    for test_type in ("unit", "integration", "performance"):
        selected = _project_files_for_test_type(PROJECT_FILES, test_type)
        test_paths = [path for path in selected if path.startswith("tests/")]
        assert test_paths == [f"tests/{test_type}/test_{test_type}_{'pricing' if test_type == 'unit' else 'checkout'}.py"]


def test_assertion_call_maps_to_multi_file_source_ast():
    filename, line, confidence, provenance = DefectAnalysisService().extract_multi_file_ast_localization(
        stack_trace="assert apply_discount(100, 0.1) == 90",
        test_name="test_unit_apply_discount",
        project_files=PROJECT_FILES,
    )
    assert filename == "shop/pricing.py"
    assert line == 2
    assert confidence == "HIGH"
    assert provenance == "AST_SOURCE_MAPPING"


def test_llm_cannot_move_multi_file_location_to_unrelated_archive_path():
    defect = DefectReport(
        defect_id="def-friday",
        submission_id="sub-friday",
        title="Discount assertion failed",
        severity=DefectSeverity.HIGH,
        description="Verified assertion failure",
        file_path="shop/pricing.py",
        line_number=2,
        confidence="HIGH",
        provenance="AST_SOURCE_MAPPING",
    )
    hypothesis = LLMDefectHypothesis(
        suspected_file="friday_defective_three_tests.zip",
        suspected_line=13,
        predicted_defect_category="functional_bug",
        root_cause_explanation="Discount may be ignored.",
        repair_recommendation="Apply the discount rate.",
        confidence=0.9,
        supporting_evidence_ids=["ev_test_0"],
        validated_evidence_ids=["ev_test_0"],
        inference_status=InferenceStatus.SUCCESS,
        llm_invoked=True,
        model_identifier="qwen2.5-coder:3b",
    )
    reconciled, telemetry, _ = DefectReconciliationService().reconcile(
        deterministic_defects=[defect],
        llm_hypothesis=hypothesis,
        candidate_code=PROJECT_FILES["shop/pricing.py"],
        evaluation_mode="LLM_ASSISTED",
    )
    assert reconciled[0].file_path == "shop/pricing.py"
    assert reconciled[0].line_number == 2
    assert reconciled[0].provenance == "AST_SOURCE_MAPPING"
    assert telemetry.llm_changed_localization is False
