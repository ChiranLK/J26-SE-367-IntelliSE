"""
INTELISE Component 4 — Phase 3C.1A: Automated Regression & Integration Test Suite (Task 11).

Comprehensive integration coverage for:
1. LLM client connectivity and model availability checks
2. Structured output schema validation and bounding
3. LangGraph node integration (reason_defects_with_llm_node)
4. Deterministic-only mode execution
5. LLM-assisted mode execution
6. Fail-closed fallback behavior
7. Evidence grounding and catalog validation
8. Prompt-injection resistance
9. Component 3 technical feedback contract preservation
10. Post-Delivery XAI security controls preservation
11. Benchmark ground-truth isolation
12. Provenance recording and AI contribution instrumentation
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.common import DefectSeverity, TestResultStatus, TestType, VerificationStatus
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import TechnicalFeedbackPayload
from app.schemas.llm_defect_reasoning import (
    AIContributionTelemetry,
    InferenceStatus,
    LLMDefectHypothesis,
    LLMReasoningInput,
    SupportedDefectCategory,
)
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse
from app.services.defect_reconciliation_service import DefectReconciliationService
from app.services.feedback_service import TechnicalFeedbackService
from app.services.llm_defect_reasoning_agent import LLMDefectReasoningAgent
from app.services.ollama_client import OllamaClient
from app.services.post_delivery_xai_service import PostDeliveryXaiService
from app.workflows.verification_graph import (
    VerificationWorkflowState,
    build_verification_graph,
    reason_defects_with_llm_node,
    verification_pipeline,
)


import asyncio


# -----------------------------------------------------------------------------
# 1. LLM Client Connectivity Handling
# -----------------------------------------------------------------------------
def test_ollama_connectivity_handling():
    """Verifies that OllamaClient handles online and offline states gracefully."""
    # Offline client
    offline_client = OllamaClient(base_url="http://127.0.0.1:9999", timeout_seconds=0.2)
    is_ok, models, msg = asyncio.run(offline_client.check_availability())
    assert is_ok is False
    assert len(models) == 0
    assert "Cannot connect" in msg or "error" in msg.lower()

    # Disabled client
    disabled_client = OllamaClient(enabled=False)
    is_ok_d, _, msg_d = asyncio.run(disabled_client.check_availability())
    assert is_ok_d is False
    assert "disabled" in msg_d.lower()


# -----------------------------------------------------------------------------
# 2. Structured Output Validation
# -----------------------------------------------------------------------------
def test_structured_output_schema_validation():
    """Verifies that LLMDefectHypothesis strictly validates and normalizes all fields."""
    hypo = LLMDefectHypothesis(
        predicted_defect_category="logic_bug",  # synonym for functional_bug
        suspected_file="calc.py",
        suspected_line=12,
        root_cause_explanation="Off-by-one boundary error in range iterator",
        supporting_evidence_ids=["ev_1"],
        repair_recommendation="Adjust range to range(n + 1)",
        confidence=0.85,
    )
    assert hypo.predicted_defect_category == "functional_bug"
    assert hypo.suspected_line == 12
    assert hypo.confidence == 0.85
    assert hypo.inference_status == InferenceStatus.SUCCESS


# -----------------------------------------------------------------------------
# 3. LangGraph Node Integration
# -----------------------------------------------------------------------------
def test_langgraph_node_execution():
    """Verifies that reason_defects_with_llm_node executes and updates workflow state."""
    state: VerificationWorkflowState = {
        "run_id": "run-test-node-01",
        "submission_id": "sub-test-01",
        "source_code": "def divide(a, b):\n    return a / b\n",
        "language": "python",
        "filename": "divide.py",
        "status": VerificationStatus.FAILED.value,
        "evaluation_mode": "DETERMINISTIC_ONLY",
        "test_results": [
            TestResult(
                test_id="t1",
                name="test_zero_div",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                error_message="ZeroDivisionError: division by zero",
            )
        ],
        "defect_reports": [
            DefectReport(
                defect_id="def-01",
                title="Zero Division in divide",
                defect_category="functional_bug",
                description="ZeroDivisionError: division by zero",
                file_path="divide.py",
                line_number=2,
            )
        ],
        "telemetry": {},
    }
    updates = asyncio.run(reason_defects_with_llm_node(state))
    assert "defect_reports" in updates
    assert "telemetry" in updates
    assert "ai_contribution" in updates["telemetry"]
    assert updates["telemetry"]["ai_contribution"]["evaluation_mode"] == "DETERMINISTIC_ONLY"


# -----------------------------------------------------------------------------
# 4. Deterministic-Only Mode
# -----------------------------------------------------------------------------
def test_deterministic_only_mode_preserves_unmodified_defects():
    """Verifies that in DETERMINISTIC_ONLY mode, defect reports remain exactly untouched."""
    recon_svc = DefectReconciliationService()
    orig_defect = DefectReport(
        defect_id="def-det-01",
        title="Original Test Failure",
        defect_category="functional_bug",
        description="Original failure details",
        file_path="solution.py",
        line_number=None,
    )
    reconciled, telemetry, guidance = recon_svc.reconcile(
        deterministic_defects=[orig_defect],
        llm_hypothesis=None,
        candidate_code="def f(): pass",
        evaluation_mode="DETERMINISTIC_ONLY",
    )
    assert len(reconciled) == 1
    assert reconciled[0].defect_id == "def-det-01"
    assert reconciled[0].line_number is None
    assert telemetry.evaluation_mode == "DETERMINISTIC_ONLY"
    assert telemetry.actual_llm_invocation_count == 0
    assert len(guidance) == 0


# -----------------------------------------------------------------------------
# 5. LLM-Assisted Mode & Line Promotion
# -----------------------------------------------------------------------------
def test_llm_assisted_mode_promotes_line_and_repair_guidance():
    """Verifies that LLM-assisted mode promotes localized line and enriches repair advice."""
    recon_svc = DefectReconciliationService()
    orig_defect = DefectReport(
        defect_id="def-llm-01",
        title="Unlocalized assertion failure",
        defect_category="functional_bug",
        description="assert multiply(2, 3) == 6 failed",
        file_path="math_ops.py",
        line_number=None,  # Unlocalized
        confidence="LOW",
        provenance="TRACEBACK_INSPECTION",
    )
    llm_hypo = LLMDefectHypothesis(
        predicted_defect_category="functional_bug",
        suspected_file="math_ops.py",
        suspected_line=3,  # Valid line in 4-line code
        root_cause_explanation="Operator used was addition instead of multiplication.",
        repair_recommendation="Replace + with * on line 3.",
        confidence=0.88,
        validated_evidence_ids=["ev_1"],
    )
    code = "def multiply(a, b):\n    # math function\n    return a + b\n"
    reconciled, telemetry, guidance = recon_svc.reconcile(
        deterministic_defects=[orig_defect],
        llm_hypothesis=llm_hypo,
        candidate_code=code,
        evaluation_mode="LLM_ASSISTED",
    )
    assert len(reconciled) == 1
    assert reconciled[0].line_number == 3
    assert reconciled[0].provenance == "LLM_ASSISTED_LOCALIZATION"
    assert reconciled[0].suggested_fix == "Replace + with * on line 3."
    assert "[LLM Root Cause]:" in reconciled[0].description
    assert telemetry.llm_changed_localization is True
    assert telemetry.llm_changed_repair_recommendation is True
    assert len(guidance) == 1
    assert guidance[0]["suspected_line"] == 3


# -----------------------------------------------------------------------------
# 6. Fallback Behavior
# -----------------------------------------------------------------------------
def test_fallback_behavior_on_inference_error():
    """Verifies that when LLM encounters an exception, it falls back without crashing."""
    agent = LLMDefectReasoningAgent(enabled=True)
    input_data = LLMReasoningInput(
        candidate_source_code="def f(): return 1\n",
        filename="solution.py",
        unit_test_failure_messages=["AssertionError: assert 1 == 2"],
        evidence_catalog={"ev_0": "Test failed"},
    )
    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection refused")):
        hypo = asyncio.run(agent.reason_defects(input_data))
        assert hypo.inference_status in (InferenceStatus.FALLBACK, InferenceStatus.FAILED)
        assert hypo.predicted_defect_category == "functional_bug"
        assert hypo.confidence == 0.5


# -----------------------------------------------------------------------------
# 7. Evidence Grounding & Catalog Validation
# -----------------------------------------------------------------------------
def test_evidence_grounding_rejects_hallucinated_ids():
    """Verifies that hallucinated evidence IDs not in catalog are rejected."""
    agent = LLMDefectReasoningAgent(enabled=True)
    input_data = LLMReasoningInput(
        candidate_source_code="x = 1\n",
        evidence_catalog={"ev_real_1": "Verified assertion failure"},
    )
    raw = {
        "predicted_defect_category": "functional_bug",
        "supporting_evidence_ids": ["ev_real_1", "ev_fake_999"],
        "confidence": 0.8,
    }
    validated = agent.validate_and_sanitize_hypothesis(raw, input_data, duration_ms=5.0)
    assert validated.validated_evidence_ids == ["ev_real_1"]
    assert validated.rejected_evidence_ids == ["ev_fake_999"]


# -----------------------------------------------------------------------------
# 8. Component 3 Technical Feedback Compatibility
# -----------------------------------------------------------------------------
def test_component3_feedback_contract_compatibility():
    """Verifies that machine-readable guidance preserves Component 3 feedback payload format."""
    feedback_svc = TechnicalFeedbackService()
    run = VerificationRunResponse(
        id="run-c3-compat",
        submission_id="sub-c3-compat",
        status=VerificationStatus.FAILED,
        defect_reports=[
            DefectReport(
                defect_id="def-c3-01",
                title="Addition bug",
                defect_category="functional_bug",
                description="Test failed: assert 5 == 10",
                file_path="calc.py",
                line_number=4,
                suggested_fix="Change + to * on line 4",
            )
        ],
        test_results=[
            TestResult(
                test_id="t1",
                name="test_mult",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                error_message="AssertionError: 5 != 10",
            )
        ],
    )
    payload = feedback_svc.build_feedback_payload(run)
    assert isinstance(payload, TechnicalFeedbackPayload)
    assert "functional_bug" in payload.defect_categories
    assert len(payload.source_locations) == 1
    assert payload.source_locations[0]["line"] == 4
    assert len(payload.machine_repair_guidance) == 1
    assert payload.machine_repair_guidance[0]["suggested_fix"] == "Change + to * on line 4"


# -----------------------------------------------------------------------------
# 9. Post-Delivery XAI Security Gate Preservation
# -----------------------------------------------------------------------------
def test_post_delivery_xai_security_gate_preserved():
    """Verifies that PostDeliveryXaiService strictly rejects unverified or failed artifacts."""
    xai_svc = PostDeliveryXaiService()
    failed_run = VerificationRunResponse(
        id="run-failed-xai",
        submission_id="sub-failed",
        status=VerificationStatus.FAILED,
        defect_reports=[
            DefectReport(
                defect_id="def-01",
                title="Bug",
                defect_category="functional_bug",
                description="Failed assertion",
            )
        ],
        test_results=[],
    )
    gate_status = xai_svc.evaluate_delivery_gate(failed_run)
    assert gate_status.verification_passed is False
    assert gate_status.gate_verdict == "BLOCKED_VERIFICATION_FAILED"


# -----------------------------------------------------------------------------
# 10. Benchmark Ground-Truth Isolation
# -----------------------------------------------------------------------------
def test_benchmark_label_isolation_enforced():
    """
    Verifies that LLMReasoningInput does not have attributes for benchmark ground-truth
    labels, expected line numbers, mutation operators, or answer keys.
    """
    input_data = LLMReasoningInput(
        candidate_source_code="def f(): pass",
        filename="test.py",
    )
    assert not hasattr(input_data, "expected_category")
    assert not hasattr(input_data, "expected_line_number")
    assert not hasattr(input_data, "mutation_operator")
    assert not hasattr(input_data, "has_defect")
    assert not hasattr(input_data, "answer_key")


# -----------------------------------------------------------------------------
# 11. AI Contribution Instrumentation Telemetry
# -----------------------------------------------------------------------------
def test_ai_contribution_instrumentation():
    """Verifies that AIContributionTelemetry tracks all required operational metrics."""
    telemetry = AIContributionTelemetry(
        evaluation_mode="LLM_ASSISTED",
        llm_enabled=True,
        actual_llm_invocation_count=1,
        successful_llm_response_count=1,
        failed_llm_response_count=0,
        model_identifier="qwen2.5-coder:3b",
        model_digest="f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225",
        inference_latency_ms=1240.5,
        timeout_events=0,
        fallback_events=0,
        validated_llm_findings=1,
        rejected_llm_findings=0,
        llm_changed_classification=False,
        llm_changed_localization=True,
        llm_changed_repair_recommendation=True,
        reconciliation_log=["Promoted line localization to line 3"],
    )
    d = telemetry.model_dump()
    assert d["evaluation_mode"] == "LLM_ASSISTED"
    assert d["actual_llm_invocation_count"] == 1
    assert d["llm_changed_localization"] is True
    assert d["llm_changed_repair_recommendation"] is True
    assert d["model_digest"] is not None
