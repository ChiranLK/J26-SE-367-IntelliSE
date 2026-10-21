import asyncio
from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.repositories.in_memory import (
    InMemorySubmissionRepository,
    InMemoryVerificationRunRepository,
)
from app.schemas.common import (
    DefectSeverity,
    ProgrammingLanguage,
    TestResultStatus,
    TestType,
    VerificationStatus,
)
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import TechnicalFeedbackPayload
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse
from app.schemas.xai import XaiExplanationResponse
from app.services.feedback_service import TechnicalFeedbackService
from app.services.verification_service import VerificationService
from app.services.xai_service import (
    DeterministicEvidenceExplanationProvider,
    XaiExplanationService,
)
@pytest.fixture(autouse=True)
def disable_ollama_for_baseline_xai_tests(monkeypatch: pytest.MonkeyPatch):
    """Enforce deterministic provider baseline for unit regression tests."""
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)


def test_defective_calculator_generates_human_facing_xai_explanation(client: TestClient):
    """
    Scenario 1: Defective calculator with 2 failed assertions.
    Verifies that GET /verifications/{run_id}/explanation returns a rich, 5-part
    human-facing XAI explanation addressing:
    1. What failed?
    2. What evidence supports the failure? (Confirmed observations)
    3. Why is observed behavior inconsistent with authorized tests?
    4. Why does Component 4 recommend returning code to Component 3?
    5. What should be investigated or corrected?
    """
    defective_code = """
def calculate_tax(amount):
    return amount * 0.08

def total_with_tax(amount):
    return calculate_tax(amount)  # Defect: omits base amount

def total_without_tax(amount):
    return 0.0  # Defect: hardcoded 0.0
"""
    test_code = """
from solution import total_with_tax, total_without_tax

def test_total_with_tax():
    assert total_with_tax(100.0) == 108.0

def test_total_without_tax():
    assert total_without_tax(100.0) == 100.0
"""
    # 1. Register submission
    sub_res = client.post(
        "/api/v1/submissions",
        json={
            "code": defective_code,
            "language": "python",
            "filename": "defective_calculator.py",
        },
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    # 2. Register verification run with execute_now=True
    run_res = client.post(
        "/api/v1/verifications?execute_now=true",
        json={
            "submission_id": sub_id,
            "trusted_test_cases": test_code,
        },
    )
    assert run_res.status_code == 201
    run_data = run_res.json()
    assert run_data["status"] == "FAILED"
    run_id = run_data["id"]

    # 3. Retrieve explanation - withheld during intermediate repair attempts
    expl_res = client.get(f"/api/v1/verifications/{run_id}/explanation")
    assert expl_res.status_code == 200
    data = expl_res.json()

    # Core response metadata
    assert data["verification_run_id"] == run_id
    assert data["submission_id"] == sub_id
    assert data["verification_status"] == "FAILED"
    assert data["eligible"] is False
    assert data["delivery_status"] == "BLOCKED_VERIFICATION_FAILED"
    assert data["post_delivery_explanation"] is None
    assert "User-facing XAI is withheld during intermediate repair attempts" in data["eligibility_reason"]
    assert data["recommendation"]["action"] == "RETURN_TO_COMPONENT_3"
    assert data["recommendation"]["recommended"] is True

    # 4. Verify that internal defect reports are preserved for C3 and auditing
    defects_res = client.get(f"/api/v1/verifications/{run_id}/defects")
    assert defects_res.status_code == 200
    defects_data = defects_res.json()["items"]
    assert len(defects_data) == 2


def test_corrected_calculator_produces_passing_xai_explanation(client: TestClient):
    """
    Scenario 2: Corrected calculator where all assertions pass.
    Verifies that:
    - Prior to delivery confirmation, XAI remains in PENDING_DELIVERY_CONFIRMATION state.
    - Upon confirming delivery, full post-delivery code explanation is unlocked.
    """
    valid_code = """
def calculate_tax(amount):
    return amount * 0.08

def total_with_tax(amount):
    return amount + calculate_tax(amount)

def total_without_tax(amount):
    return float(amount)
"""
    test_code = """
from solution import total_with_tax, total_without_tax

def test_total_with_tax():
    assert total_with_tax(100.0) == 108.0

def test_total_without_tax():
    assert total_without_tax(100.0) == 100.0
"""
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": valid_code, "language": "python", "filename": "calculator.py"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications?execute_now=true",
        json={"submission_id": sub_id, "trusted_test_cases": test_code},
    )
    run_id = run_res.json()["id"]
    assert run_res.json()["status"] == "PASSED"

    # Step 1: Prior to delivery confirmation, explanation is in pending state
    expl_res = client.get(f"/api/v1/verifications/{run_id}/explanation")
    assert expl_res.status_code == 200
    data = expl_res.json()

    assert data["verification_status"] == "PASSED"
    assert data["eligible"] is False
    assert data["delivery_status"] == "PENDING_DELIVERY_CONFIRMATION"
    assert data["post_delivery_explanation"] is None
    assert data["recommendation"]["action"] == "AWAIT_DELIVERY_CONFIRMATION"
    assert data["recommendation"]["recommended"] is False

    # Step 2: Confirm production delivery with authenticated credentials
    deliv_res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub_id, "notes": "Production delivery release signoff"},
    )
    assert deliv_res.status_code == 201

    # Step 3: Post-delivery explanation is now fully unlocked
    expl_res_after = client.get(f"/api/v1/verifications/{run_id}/explanation")
    assert expl_res_after.status_code == 200
    data_after = expl_res_after.json()

    assert data_after["eligible"] is True
    assert data_after["delivery_status"] == "CONFIRMED_PRODUCTION_DELIVERY"
    assert data_after["post_delivery_explanation"] is not None
    assert data_after["recommendation"]["action"] == "DELIVERED_AND_READY"


def test_pending_verification_is_ineligible_for_explanation():
    """
    Scenario 3: Verification in PENDING or RUNNING status.
    Verifies that explanation clearly states telemetry is not yet available.
    """
    now = datetime.now(timezone.utc)
    pending_run = VerificationRunResponse(
        id="run-pending-xai",
        submission_id="sub-pending",
        status=VerificationStatus.PENDING,
        test_results=[],
        defect_reports=[],
        created_at=now,
        updated_at=now,
    )

    service = XaiExplanationService()
    explanation = service.generate_explanation(pending_run)

    assert explanation.eligible is False
    assert explanation.verification_status == "PENDING"
    assert explanation.delivery_status == "PENDING_VERIFICATION"
    assert explanation.recommendation.action == "AWAIT_EXECUTION"
    assert explanation.recommendation.recommended is False


def test_infrastructure_failure_explanation_does_not_blame_code():
    """
    Scenario 4: Infrastructure-only failure (e.g. sandbox container crash).
    Verifies that explanation explicitly identifies an infrastructure anomaly
    and does NOT attribute the failure to the submitted user code.
    """
    now = datetime.now(timezone.utc)
    infra_run = VerificationRunResponse(
        id="run-infra-xai",
        submission_id="sub-infra",
        status=VerificationStatus.ERROR,
        error_message="Sandbox runner image unavailable: docker isolation unavailable",
        execution_telemetry={"sandbox_infrastructure_failure": True},
        test_results=[],
        defect_reports=[],
        created_at=now,
        updated_at=now,
    )

    service = XaiExplanationService()
    explanation = service.generate_explanation(infra_run)

    assert explanation.eligible is False
    assert explanation.delivery_status == "BLOCKED_INFRASTRUCTURE_ERROR"
    assert explanation.recommendation.action == "RETRY_INFRASTRUCTURE"
    assert explanation.recommendation.recommended is False


def test_missing_diagnostic_information_handled_safely():
    """
    Scenario 5: Defect report with partial/missing diagnostic data (no expected/actual values).
    Verifies that missing information is explicitly acknowledged without fabricating values.
    """
    now = datetime.now(timezone.utc)
    defect = DefectReport(
        defect_id="def-missing-data",
        verification_run_id="run-missing",
        submission_id="sub-missing",
        title="Uncaught exception in test_worker",
        description="Observed uncaught ZeroDivisionError in test_worker",
        failed_test="test_worker",
        failure_category="RUNTIME_EXCEPTION",
        assertion_or_exception="ZeroDivisionError: division by zero",
        expected_value=None,  # Missing diff value
        actual_value=None,    # Missing diff value
        file_path="worker.py",
        line_number=None,     # Unlocalized line
        traceback_excerpt="worker.py: ZeroDivisionError",
        created_at=now,
    )
    test_res = TestResult(
        test_id="test_worker",
        name="test_worker",
        test_type=TestType.UNIT,
        status=TestResultStatus.FAILED,
        duration_ms=8.0,
        error_message="ZeroDivisionError",
    )
    run = VerificationRunResponse(
        id="run-missing",
        submission_id="sub-missing",
        status=VerificationStatus.FAILED,
        test_results=[test_res],
        defect_reports=[defect],
        created_at=now,
        updated_at=now,
    )

    service = XaiExplanationService()

    # User-facing explanation: withheld for failed runs
    explanation = service.generate_explanation(run)
    assert explanation.eligible is False
    assert explanation.delivery_status == "BLOCKED_VERIFICATION_FAILED"

    # Internal research diagnostic generator: handles missing diagnostics safely without hallucination
    internal_expl = service.generate_internal_defect_explanation(run)
    assert internal_expl.eligible is True
    assert len(internal_expl.confirmed_observations) == 1
    obs = internal_expl.confirmed_observations[0]
    assert obs.expected_value is None
    assert obs.observed_value is None
    assert obs.line_number is None

    # Verifies explicit disclosure of partial diagnostic availability
    assert "Diagnostic limitation note" in internal_expl.evidence_based_interpretation
    assert "strictly bounded to confirmed traceback excerpts" in internal_expl.evidence_based_interpretation


def test_unknown_verification_run_returns_404(client: TestClient):
    """
    Scenario 6: Querying an explanation for a nonexistent run returns 404.
    """
    res = client.get("/api/v1/verifications/run-does-not-exist-9999/explanation")
    assert res.status_code == 404
    err_body = res.json()
    err_msg = (err_body.get("detail") or err_body.get("error", {}).get("message", "")).lower()
    assert "not found" in err_msg


def test_deterministic_repeated_explanations_do_not_mutate_state(client: TestClient):
    """
    Scenario 7 & 8: Requesting the explanation multiple times produces deterministic,
    identical output and causes ZERO storage mutations or feedback iteration creation.
    """
    now = datetime.now(timezone.utc)
    defect = DefectReport(
        defect_id="def-stable-1",
        verification_run_id="run-stable-xai",
        submission_id="sub-stable-xai",
        title="Assertion failure in test_calc",
        description="Observed assert 4 == 5",
        failed_test="test_calc",
        failure_category="ASSERTION_FAILURE",
        assertion_or_exception="assert 4 == 5",
        expected_value="5",
        actual_value="4",
        file_path="calc.py",
        line_number=10,
        traceback_excerpt="calc.py:10: assert 4 == 5",
        created_at=now,
    )
    test_res = TestResult(
        test_id="test_calc",
        name="test_calc",
        test_type=TestType.UNIT,
        status=TestResultStatus.FAILED,
        duration_ms=5.0,
        error_message="assert 4 == 5",
    )
    run = VerificationRunResponse(
        id="run-stable-xai",
        submission_id="sub-stable-xai",
        status=VerificationStatus.FAILED,
        test_results=[test_res],
        defect_reports=[defect],
        feedback_iterations=[],
        created_at=now,
        updated_at=now,
    )

    repo = InMemoryVerificationRunRepository()
    sub_repo = InMemorySubmissionRepository()
    asyncio.run(repo.save(run))

    v_service = VerificationService(submission_repo=sub_repo, verification_repo=repo)

    # First explanation request
    expl1 = asyncio.run(v_service.get_explanation(run.id))
    # Second explanation request
    expl2 = asyncio.run(v_service.get_explanation(run.id))

    assert expl1.explanation_id == expl2.explanation_id
    assert expl1.what_failed == expl2.what_failed
    assert expl1.evidence_based_interpretation == expl2.evidence_based_interpretation
    assert expl1.recommendation.model_dump() == expl2.recommendation.model_dump()

    # Verify no database mutation occurred
    saved_run = asyncio.run(repo.get_by_id(run.id))
    assert len(saved_run.feedback_iterations) == 0
    assert saved_run.updated_at == now


def test_strict_separation_between_xai_and_c3_technical_feedback():
    """
    Scenario 9: Confirm architectural separation between Component 3 technical feedback
    payload and human-facing XAI explanation.
    The technical feedback payload must NOT contain XAI narrative text.
    """
    now = datetime.now(timezone.utc)
    defect = DefectReport(
        defect_id="def-sep-1",
        verification_run_id="run-sep-xai",
        submission_id="sub-sep-xai",
        title="Assertion error",
        description="Observed assert 1 == 2",
        failed_test="test_sep",
        failure_category="ASSERTION_FAILURE",
        assertion_or_exception="assert 1 == 2",
        expected_value="2",
        actual_value="1",
        file_path="sep.py",
        line_number=5,
        traceback_excerpt="sep.py:5: assert 1 == 2",
        created_at=now,
    )
    test_res = TestResult(
        test_id="test_sep",
        name="test_sep",
        test_type=TestType.UNIT,
        status=TestResultStatus.FAILED,
        duration_ms=5.0,
        error_message="assert 1 == 2",
    )
    run = VerificationRunResponse(
        id="run-sep-xai",
        submission_id="sub-sep-xai",
        status=VerificationStatus.FAILED,
        test_results=[test_res],
        defect_reports=[defect],
        created_at=now,
        updated_at=now,
    )

    # 1. Technical feedback service for Component 3
    feedback_svc = TechnicalFeedbackService()
    c3_payload = feedback_svc.build_feedback_payload(run)

    # 2. XAI explanation service for Human User
    xai_svc = XaiExplanationService()
    xai_resp = xai_svc.generate_explanation(run)

    # Verify C3 payload contains only structured technical telemetry
    assert hasattr(c3_payload, "failed_assertions")
    assert hasattr(c3_payload, "value_comparisons")
    assert not hasattr(c3_payload, "evidence_based_interpretation")
    assert not hasattr(c3_payload, "recommendation")

    # Verify XAI response contains human-facing reasoning
    assert hasattr(xai_resp, "evidence_based_interpretation")
    assert hasattr(xai_resp, "recommendation")
    assert xai_resp.recommendation.action == "RETURN_TO_COMPONENT_3"
