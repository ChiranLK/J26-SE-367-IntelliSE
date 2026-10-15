import asyncio
from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.repositories.in_memory import InMemoryVerificationRunRepository
from app.schemas.common import (
    DefectSeverity,
    ProgrammingLanguage,
    TestResultStatus,
    TestType,
    VerificationStatus,
)
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import (
    FeedbackIteration,
    TechnicalFeedbackPayload,
    TechnicalFeedbackPreviewResponse,
)
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse
from app.services.feedback_service import TechnicalFeedbackService
from app.services.verification_service import VerificationService


def test_defective_calculator_generates_valid_technical_feedback(client: TestClient):
    """
    Scenario 1 & 2: Defective calculator generates a valid technical feedback package.
    Verifies that:
    - Verification run fails with 2 failed assertions.
    - Technical feedback preview returns eligible=True.
    - Both failed assertions and value comparisons (expected vs observed) are present.
    - Schema version is '1.0' and feedback_id is deterministic.
    """
    defective_code = """
def calculate_tax(amount):
    return amount * 0.08

def total_with_tax(amount):
    return calculate_tax(amount)  # Defect: missing base amount

def total_without_tax(amount):
    return 0.0  # Defect: returns zero instead of amount
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

    # 2. Register & execute verification run
    run_res = client.post(
        "/api/v1/verifications",
        json={"submission_id": sub_id, "trusted_test_cases": test_code},
    )
    run_id = run_res.json()["id"]

    exec_res = client.post(
        f"/api/v1/verifications/{run_id}/execute",
        json={"trusted_test_cases": test_code},
    )
    assert exec_res.status_code == 200
    run_data = exec_res.json()
    assert run_data["status"] == "FAILED"
    assert len(run_data["defect_reports"]) == 2

    # Verify LangGraph automatically prepared an initial feedback iteration
    assert len(run_data["feedback_iterations"]) == 1
    initial_iter = run_data["feedback_iterations"][0]
    assert initial_iter["iteration_number"] == 1
    assert initial_iter["defects_count"] == 2
    assert initial_iter["status"] == "AWAITING_REVISION"
    assert initial_iter["payload"] is not None
    assert initial_iter["payload"]["schema_version"] == "1.0"

    # 3. Read-only feedback preview endpoint
    preview_res = client.get(f"/api/v1/verifications/{run_id}/feedback-preview")
    assert preview_res.status_code == 200
    preview_data = preview_res.json()

    assert preview_data["eligible"] is True
    assert "2 application-code defect(s)" in preview_data["reason"]
    feedback = preview_data["feedback"]
    assert feedback is not None

    # Check required fields
    assert feedback["feedback_id"].startswith("fb-")
    assert feedback["verification_run_id"] == run_id
    assert feedback["submission_id"] == sub_id
    assert feedback["verification_status"] == "FAILED"
    assert "defective_calculator.py" in feedback["affected_files"]
    assert "test_total_with_tax" in feedback["failed_tests"]
    assert "test_total_without_tax" in feedback["failed_tests"]
    assert feedback["schema_version"] == "1.0"
    assert len(feedback["defect_ids"]) == 2

    # Check value comparisons
    comparisons = feedback["value_comparisons"]
    assert len(comparisons) == 2

    with_tax = next((c for c in comparisons if c["test_name"] == "test_total_with_tax"), None)
    without_tax = next((c for c in comparisons if c["test_name"] == "test_total_without_tax"), None)

    assert with_tax is not None
    assert with_tax["expected"] == "108.0"
    assert with_tax["observed"] == "8.0"

    assert without_tax is not None
    assert without_tax["expected"] == "100.0"
    assert without_tax["observed"] == "0.0"


def test_corrected_calculator_produces_no_corrective_feedback(client: TestClient):
    """
    Scenario 3: Corrected calculator yields eligible=False and no corrective feedback.
    """
    corrected_code = """
def calculate_tax(amount):
    return amount * 0.08

def total_with_tax(amount):
    return amount + calculate_tax(amount)

def total_without_tax(amount):
    return amount
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
        json={"code": corrected_code, "language": "python", "filename": "calculator.py"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications",
        json={"submission_id": sub_id, "trusted_test_cases": test_code},
    )
    run_id = run_res.json()["id"]

    exec_res = client.post(
        f"/api/v1/verifications/{run_id}/execute",
        json={"trusted_test_cases": test_code},
    )
    assert exec_res.status_code == 200
    assert exec_res.json()["status"] == "PASSED"
    assert len(exec_res.json()["feedback_iterations"]) == 0

    preview_res = client.get(f"/api/v1/verifications/{run_id}/feedback-preview")
    assert preview_res.status_code == 200
    data = preview_res.json()
    assert data["eligible"] is False
    assert "passed successfully" in data["reason"].lower()
    assert data["feedback"] is None


def test_pending_verification_is_ineligible(client: TestClient):
    """
    Scenario 4: Pending verification run is ineligible for technical feedback.
    """
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": "def placeholder(): pass", "language": "python"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post("/api/v1/verifications", json={"submission_id": sub_id})
    run_id = run_res.json()["id"]

    preview_res = client.get(f"/api/v1/verifications/{run_id}/feedback-preview")
    assert preview_res.status_code == 200
    data = preview_res.json()
    assert data["eligible"] is False
    assert "pending" in data["reason"].lower()
    assert data["feedback"] is None


def test_infrastructure_only_failure_is_ineligible():
    """
    Scenario 5: Infrastructure-only failure is ineligible for application-code feedback.
    """
    service = TechnicalFeedbackService()
    infra_run = VerificationRunResponse(
        id="run-infra-only",
        submission_id="sub-infra",
        status=VerificationStatus.ERROR,
        error_message="Infrastructure isolation failure: Docker unavailable",
        execution_telemetry={"docker_available": False},
        test_results=[],
        defect_reports=[],
    )

    eligible, reason = service.check_eligibility(infra_run)
    assert eligible is False
    assert "infrastructure" in reason.lower()

    preview = service.get_feedback_preview(infra_run)
    assert preview.eligible is False
    assert preview.feedback is None


def test_missing_diagnostic_evidence_handled_safely():
    """
    Scenario 6: Test failures with missing/incomplete diagnostics are handled safely.
    """
    service = TechnicalFeedbackService()
    defect = DefectReport(
        defect_id="def-sparse-1",
        verification_run_id="run-sparse",
        submission_id="sub-sparse",
        title="Sparse Test Failure",
        severity=DefectSeverity.HIGH,
        description="Failure without trace",
        file_path=None,
        line_number=None,
        failed_test="test_sparse",
        failure_category="ASSERTION_FAILURE",
        assertion_or_exception=None,
        expected_value=None,
        actual_value=None,
        traceback_excerpt=None,
    )
    sparse_run = VerificationRunResponse(
        id="run-sparse",
        submission_id="sub-sparse",
        status=VerificationStatus.FAILED,
        defect_reports=[defect],
        test_results=[],
        error_message=None,
    )

    eligible, reason = service.check_eligibility(sparse_run)
    assert eligible is True

    payload = service.build_feedback_payload(sparse_run)
    assert payload.feedback_id.startswith("fb-")
    assert payload.affected_files == ["solution.py"]
    assert len(payload.value_comparisons) == 1
    assert payload.value_comparisons[0]["expected"] is None
    assert payload.value_comparisons[0]["observed"] is None
    assert len(payload.error_logs) == 0


def test_repeated_generation_idempotency():
    """
    Scenario 7: Repeated feedback iteration recording for unchanged defects is idempotent.
    """
    service = TechnicalFeedbackService()
    now = datetime.now(timezone.utc)
    defect = DefectReport(
        defect_id="def-idem-1",
        verification_run_id="run-idem",
        submission_id="sub-idem",
        title="Failure in test_idem",
        severity=DefectSeverity.HIGH,
        description="Assert failed",
        failed_test="test_idem",
        failure_category="ASSERTION_FAILURE",
        assertion_or_exception="assert 1 == 2",
        expected_value="2",
        actual_value="1",
        created_at=now,
    )
    run = VerificationRunResponse(
        id="run-idem",
        submission_id="sub-idem",
        status=VerificationStatus.FAILED,
        defect_reports=[defect],
        feedback_iterations=[],
    )

    payload = service.build_feedback_payload(run)

    # First record
    run, it1, created1 = service.record_feedback_iteration(run, payload)
    assert created1 is True
    assert it1.iteration_number == 1
    assert len(run.feedback_iterations) == 1

    # Second record with identical defects
    run, it2, created2 = service.record_feedback_iteration(run, payload)
    assert created2 is False
    assert it2.iteration_id == it1.iteration_id
    assert len(run.feedback_iterations) == 1


def test_feedback_history_preserved_on_revision():
    """
    Scenario 8: Preserves feedback history across distinct iteration cycles.
    """
    service = TechnicalFeedbackService()
    now = datetime.now(timezone.utc)

    # Initial defect
    d1 = DefectReport(
        defect_id="def-cycle-1",
        verification_run_id="run-hist",
        submission_id="sub-hist",
        title="Failure 1",
        severity=DefectSeverity.HIGH,
        description="Defect 1",
        created_at=now,
    )
    run = VerificationRunResponse(
        id="run-hist",
        submission_id="sub-hist",
        status=VerificationStatus.FAILED,
        defect_reports=[d1],
        feedback_iterations=[],
    )
    payload1 = service.build_feedback_payload(run)
    run, it1, _ = service.record_feedback_iteration(run, payload1)

    # New distinct defect in revision
    d2 = DefectReport(
        defect_id="def-cycle-2",
        verification_run_id="run-hist",
        submission_id="sub-hist",
        title="Failure 2",
        severity=DefectSeverity.HIGH,
        description="Defect 2",
        created_at=now,
    )
    run.defect_reports = [d2]
    payload2 = service.build_feedback_payload(run)
    run, it2, created2 = service.record_feedback_iteration(run, payload2)

    assert created2 is True
    assert len(run.feedback_iterations) == 2
    assert run.feedback_iterations[0].iteration_number == 1
    assert run.feedback_iterations[1].iteration_number == 2
    assert run.feedback_iterations[0].defect_ids == ["def-cycle-1"]
    assert run.feedback_iterations[1].defect_ids == ["def-cycle-2"]


def test_mongodb_and_in_memory_persistence():
    """
    Scenario 9: Verification of feedback iteration serialization round-trip for storage backend.
    """
    now = datetime.now(timezone.utc)
    payload = TechnicalFeedbackPayload(
        feedback_id="fb-persist-test",
        verification_run_id="run-persist",
        submission_id="sub-persist",
        verification_status="FAILED",
        affected_files=["solution.py"],
        failed_tests=["test_foo"],
        failed_assertions=["assert False"],
        value_comparisons=[{"test_name": "test_foo", "expected": "True", "observed": "False"}],
        error_logs=["AssertionError: assert False"],
        defect_ids=["def-123"],
        evidence_references={"total_tests": 1},
        generated_at=now,
        schema_version="1.0",
    )
    iteration = FeedbackIteration(
        iteration_id="iter-persist-1",
        iteration_number=1,
        verification_run_id="run-persist",
        submission_id="sub-persist",
        defects_count=1,
        defect_ids=["def-123"],
        payload=payload,
        created_at=now,
    )
    run = VerificationRunResponse(
        id="run-persist",
        submission_id="sub-persist",
        status=VerificationStatus.FAILED,
        test_results=[
            TestResult(
                test_id="test_foo",
                name="test_foo",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
            )
        ],
        defect_reports=[],
        feedback_iterations=[iteration],
    )

    # In-memory repository round-trip
    in_mem_repo = InMemoryVerificationRunRepository()
    asyncio.run(in_mem_repo.save(run))
    retrieved = asyncio.run(in_mem_repo.get_by_id(run.id))
    assert retrieved is not None
    assert len(retrieved.feedback_iterations) == 1
    assert retrieved.feedback_iterations[0].payload.feedback_id == "fb-persist-test"

    # MongoDB doc round-trip validation
    doc = run.model_dump(mode="json")
    assert "feedback_iterations" in doc
    validated = VerificationRunResponse.model_validate(doc)
    assert validated.id == run.id
    assert validated.feedback_iterations[0].payload.schema_version == "1.0"


def test_read_only_preview_api_does_not_mutate_storage(client: TestClient):
    """
    Scenario 10: GET /api/v1/verifications/{run_id}/feedback-preview is strictly read-only
    and never mutates repository storage or adds duplicate feedback iterations.
    """
    defective_code = "def sub(x, y): return x + y"
    test_code = "from solution import sub\ndef test_sub(): assert sub(5, 4) == 1"

    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": defective_code, "language": "python"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications",
        json={"submission_id": sub_id, "trusted_test_cases": test_code},
    )
    run_id = run_res.json()["id"]

    client.post(
        f"/api/v1/verifications/{run_id}/execute",
        json={"trusted_test_cases": test_code},
    )

    # Inspect initial run
    initial_run = client.get(f"/api/v1/verifications/{run_id}").json()
    initial_iterations_count = len(initial_run["feedback_iterations"])

    # Call preview endpoint 5 times
    for _ in range(5):
        preview_res = client.get(f"/api/v1/verifications/{run_id}/feedback-preview")
        assert preview_res.status_code == 200
        assert preview_res.json()["eligible"] is True

    # Confirm storage has NOT mutated
    after_run = client.get(f"/api/v1/verifications/{run_id}").json()
    assert len(after_run["feedback_iterations"]) == initial_iterations_count
    assert after_run["updated_at"] == initial_run["updated_at"]
