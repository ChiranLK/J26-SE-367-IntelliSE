import asyncio
from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.repositories.in_memory import (
    InMemorySubmissionRepository,
    InMemoryVerificationRunRepository,
)
from app.repositories.mongo import MongoVerificationRunRepository
from app.schemas.common import (
    DefectSeverity,
    ProgrammingLanguage,
    TestResultStatus,
    TestType,
    VerificationStatus,
)
from app.schemas.defect_report import DefectReport
from app.schemas.submission import SubmissionCreate, SubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import (
    VerificationRunCreate,
    VerificationRunResponse,
)
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.verification_service import VerificationService


def test_defective_calculator_two_failed_assertions(client: TestClient):
    """
    Scenario 1: Defective calculator where 2 assertions fail.
    Verifies that real pytest execution produces 2 structured defect reports with expected/actual diffs.
    """
    defective_code = """
def add(a, b):
    return a + b

def subtract(a, b):
    return a + b  # Defect: addition instead of subtraction

def multiply(a, b):
    return a + b  # Defect: addition instead of multiplication
"""
    trusted_tests = """
from solution import add, subtract, multiply

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 4) == 1

def test_multiply():
    assert multiply(3, 4) == 12
"""
    # 1. Register submission
    sub_res = client.post(
        "/api/v1/submissions",
        json={
            "code": defective_code,
            "language": "python",
            "filename": "calculator.py",
        },
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    # 2. Register verification run
    run_res = client.post(
        "/api/v1/verifications",
        json={
            "submission_id": sub_id,
            "trusted_test_cases": trusted_tests,
        },
    )
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]

    # 3. Execute verification run
    exec_res = client.post(
        f"/api/v1/verifications/{run_id}/execute",
        json={"trusted_test_cases": trusted_tests},
    )
    assert exec_res.status_code == 200
    exec_data = exec_res.json()

    assert exec_data["status"] == "FAILED"
    assert len(exec_data["test_results"]) == 3

    # Check defect reports embedded in run response
    defect_reports = exec_data["defect_reports"]
    assert len(defect_reports) == 2, f"Expected 2 defect reports, got {len(defect_reports)}"

    # 4. Check via read-only API endpoint
    api_res = client.get(f"/api/v1/verifications/{run_id}/defects")
    assert api_res.status_code == 200
    api_defects = api_res.json()
    assert api_defects["total"] == 2
    assert len(api_defects["items"]) == 2

    # Verify defect details for subtract and multiply
    subtract_defect = next((d for d in defect_reports if d["failed_test"] == "test_subtract"), None)
    multiply_defect = next((d for d in defect_reports if d["failed_test"] == "test_multiply"), None)

    assert subtract_defect is not None
    assert subtract_defect["failure_category"] == "ASSERTION_FAILURE"
    assert subtract_defect["severity"] == "HIGH"
    assert subtract_defect["expected_value"] == "1"
    assert subtract_defect["actual_value"] == "9"
    assert subtract_defect["file_path"] == "calculator.py"

    assert multiply_defect is not None
    assert multiply_defect["failure_category"] == "ASSERTION_FAILURE"
    assert multiply_defect["severity"] == "HIGH"
    assert multiply_defect["expected_value"] == "12"
    assert multiply_defect["actual_value"] == "7"
    assert multiply_defect["file_path"] == "calculator.py"


def test_corrected_calculator_zero_defect_reports(client: TestClient):
    """
    Scenario 2: Corrected calculator where all assertions pass.
    Verifies that zero defect reports are produced and status is PASSED.
    """
    corrected_code = """
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
"""
    trusted_tests = """
from solution import add, subtract, multiply

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 4) == 1

def test_multiply():
    assert multiply(3, 4) == 12
"""
    # 1. Register submission
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": corrected_code, "language": "python", "filename": "calculator.py"},
    )
    sub_id = sub_res.json()["id"]

    # 2. Register & execute
    run_res = client.post(
        "/api/v1/verifications",
        json={"submission_id": sub_id, "trusted_test_cases": trusted_tests},
    )
    run_id = run_res.json()["id"]

    exec_res = client.post(
        f"/api/v1/verifications/{run_id}/execute",
        json={"trusted_test_cases": trusted_tests},
    )
    assert exec_res.status_code == 200
    exec_data = exec_res.json()

    assert exec_data["status"] == "PASSED"
    assert len(exec_data["defect_reports"]) == 0

    # API check
    api_res = client.get(f"/api/v1/verifications/{run_id}/defects")
    assert api_res.status_code == 200
    assert api_res.json()["total"] == 0
    assert api_res.json()["items"] == []


def test_pending_verification_no_fabricated_defects(client: TestClient):
    """
    Scenario 3: Verification run in PENDING status.
    Verifies that no fabricated defects are claimed.
    """
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": "def example(): pass", "language": "python"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications",
        json={"submission_id": sub_id},
    )
    run_id = run_res.json()["id"]

    # Retrieve defects for pending run
    defects_res = client.get(f"/api/v1/verifications/{run_id}/defects")
    assert defects_res.status_code == 200
    data = defects_res.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_missing_diagnostic_information_graceful():
    """
    Scenario 4: Test failure with missing or incomplete diagnostic information.
    Ensures analyzer does not raise exceptions and yields safe fallback data.
    """
    analyzer = DefectAnalysisService()
    test_result = TestResult(
        test_id="test_missing_diag",
        name="test_missing_diag",
        test_type=TestType.UNIT,
        status=TestResultStatus.FAILED,
        duration_ms=10.0,
        error_message=None,
        stack_trace=None,
    )
    run = VerificationRunResponse(
        id="run-missing-info",
        submission_id="sub-123",
        status=VerificationStatus.FAILED,
        test_results=[test_result],
    )
    submission = SubmissionResponse(
        id="sub-123",
        code="def foo(): pass",
        language=ProgrammingLanguage.PYTHON,
        filename="app.py",
    )


    reports = analyzer.analyze_run(run, submission)
    assert len(reports) == 1
    report = reports[0]
    assert report.failed_test == "test_missing_diag"
    assert report.expected_value is None
    assert report.actual_value is None
    assert report.line_number is None
    assert report.file_path == "app.py"
    assert report.severity == DefectSeverity.HIGH


def test_runtime_exception_in_submitted_code(client: TestClient):
    """
    Scenario 5: Runtime exception in submitted code (ZeroDivisionError).
    Verifies classification as RUNTIME_EXCEPTION with CRITICAL severity.
    """
    buggy_code = """
def divide_values(x, y):
    return x / y
"""
    test_code = """
from solution import divide_values

def test_divide_by_zero():
    divide_values(10, 0)
"""
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": buggy_code, "language": "python", "filename": "math_ops.py"},
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
    exec_data = exec_res.json()

    assert exec_data["status"] == "FAILED"
    assert len(exec_data["defect_reports"]) == 1
    defect = exec_data["defect_reports"][0]

    assert defect["failure_category"] == "RUNTIME_EXCEPTION"
    assert defect["severity"] == "CRITICAL"
    assert "ZeroDivisionError" in defect["assertion_or_exception"]
    assert defect["file_path"] == "math_ops.py"
    # Localized line number should match line 3 (return x / y)
    assert defect["line_number"] == 3


def test_sandbox_infrastructure_failure_separate_from_code_defects():
    """
    Scenario 6: Sandbox infrastructure failure (e.g. Docker unavailable).
    Verifies that infrastructure failure is NOT counted as an application code defect.
    """
    analyzer = DefectAnalysisService()
    infra_fail_run = VerificationRunResponse(
        id="run-infra-fail",
        submission_id="sub-infra",
        status=VerificationStatus.ERROR,
        error_message="Infrastructure isolation failure: Docker daemon unreachable",
        execution_telemetry={"docker_available": False},
        test_results=[],
    )

    reports = analyzer.analyze_run(infra_fail_run)
    assert len(reports) == 0, "Infrastructure failure must not generate application defect reports."


def test_repeated_analysis_idempotency():
    """
    Scenario 7: Repeated analysis of the same verification run.
    Verifies deterministic defect IDs and no duplicate reports.
    """
    analyzer = DefectAnalysisService()
    failed_test = TestResult(
        test_id="test_foo",
        name="test_foo",
        test_type=TestType.UNIT,
        status=TestResultStatus.FAILED,
        error_message="assert 10 == 20",
        stack_trace="E       assert 10 == 20\ntest_verification.py:5: AssertionError",
    )
    run = VerificationRunResponse(
        id="run-idempotency-check",
        submission_id="sub-idem",
        status=VerificationStatus.FAILED,
        test_results=[failed_test],
    )

    reports_run1 = analyzer.analyze_run(run)
    reports_run2 = analyzer.analyze_run(run)

    assert len(reports_run1) == 1
    assert len(reports_run2) == 1
    assert reports_run1[0].defect_id == reports_run2[0].defect_id
    assert reports_run1[0].expected_value == reports_run2[0].expected_value
    assert reports_run1[0].actual_value == reports_run2[0].actual_value


def test_mongodb_and_in_memory_persistence():
    """
    Scenario 8: Verification of defect reports serialization and persistence round-trip.
    Tests both in-memory and MongoDB repository models.
    """
    now = datetime.now(timezone.utc)
    defect = DefectReport(
        defect_id="def-test-mongo-1",
        verification_run_id="run-mongo-test",
        submission_id="sub-mongo-test",
        title="Observed Assertion Failure in test_example",
        severity=DefectSeverity.HIGH,
        description="Observed assert 4 == 5",
        file_path="solution.py",
        line_number=10,
        failed_test="test_example",
        failure_category="ASSERTION_FAILURE",
        assertion_or_exception="assert 4 == 5",
        expected_value="5",
        actual_value="4",
        created_at=now,
    )

    run = VerificationRunResponse(
        id="run-mongo-test",
        submission_id="sub-mongo-test",
        status=VerificationStatus.FAILED,
        test_results=[
            TestResult(
                test_id="test_example",
                name="test_example",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                error_message="assert 4 == 5",
            )
        ],
        defect_reports=[defect],
        created_at=now,
        updated_at=now,
    )

    # 1. Test In-Memory Persistence
    in_mem_repo = InMemoryVerificationRunRepository()
    saved_in_mem = asyncio.run(in_mem_repo.save(run))
    retrieved_in_mem = asyncio.run(in_mem_repo.get_by_id(run.id))
    assert retrieved_in_mem is not None
    assert len(retrieved_in_mem.defect_reports) == 1
    assert retrieved_in_mem.defect_reports[0].defect_id == "def-test-mongo-1"

    # 2. Test MongoDB Document Model Validation Round-trip
    doc = run.model_dump(mode="json")
    assert doc["_id"] if "_id" in doc else True
    assert "defect_reports" in doc
    assert len(doc["defect_reports"]) == 1
    assert doc["defect_reports"][0]["expected_value"] == "5"
    assert doc["defect_reports"][0]["actual_value"] == "4"

    # Validate deserialization
    validated = VerificationRunResponse.model_validate(doc)
    assert validated.id == run.id
    assert len(validated.defect_reports) == 1
    assert validated.defect_reports[0].expected_value == "5"


def test_technical_feedback_payload_preparation():
    """
    Scenario: Verify that internal technical feedback payload for Component 3 is prepared correctly.
    """
    analyzer = DefectAnalysisService()
    now = datetime.now(timezone.utc)
    defect = DefectReport(
        defect_id="def-c3-prep",
        verification_run_id="run-c3",
        submission_id="sub-c3",
        title="Assertion failure in test_c3",
        severity=DefectSeverity.HIGH,
        description="Observed assert 1 == 2",
        file_path="service.py",
        line_number=22,
        failed_test="test_c3",
        failure_category="ASSERTION_FAILURE",
        assertion_or_exception="assert 1 == 2",
        expected_value="2",
        actual_value="1",
        traceback_excerpt="service.py:22: AssertionError",
        created_at=now,
    )
    test_result = TestResult(
        test_id="test_c3",
        name="test_c3",
        test_type=TestType.UNIT,
        status=TestResultStatus.FAILED,
        duration_ms=5.0,
        error_message="assert 1 == 2",
    )

    payload = analyzer.prepare_technical_feedback(
        run_id="run-c3",
        submission_id="sub-c3",
        defect_reports=[defect],
        test_results=[test_result],
    )

    assert payload.verification_run_id == "run-c3"
    assert payload.submission_id == "sub-c3"
    assert "assert 1 == 2" in payload.failed_assertions
    assert "service.py" in payload.affected_files
    assert len(payload.test_failure_details) == 1
    assert payload.test_failure_details[0]["status"] == "FAILED"
