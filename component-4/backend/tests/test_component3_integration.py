import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.repositories import _in_memory_submission_repo, _in_memory_verification_repo
from app.schemas.common import (
    DefectSeverity,
    ProgrammingLanguage,
    TestResultStatus,
    TestType,
    VerificationStatus,
)
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import (
    Component3StatusResponse,
    FeedbackDispatchResponse,
    FeedbackIteration,
    TechnicalFeedbackPayload,
)
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse
from app.services.component3_client import (
    Component3Client,
    Component3ClientError,
    Component3ConfigError,
    Component3ConnectionError,
    Component3ResponseError,
    Component3TimeoutError,
)
from app.services.feedback_service import TechnicalFeedbackService
from app.services.verification_service import VerificationService


def _create_sample_run(
    run_status: VerificationStatus = VerificationStatus.FAILED,
    with_defects: bool = True,
    infra_failure: bool = False,
) -> tuple[VerificationRunResponse, CodeSubmissionResponse]:
    """Helper to register a mock submission and verification run in memory."""
    sub = CodeSubmissionResponse(
        id="sub-test-milestone1",
        code="def add(a, b):\n    return a - b\n",
        language=ProgrammingLanguage.PYTHON,
        tags=["math", "addition"],
        metadata={"author": "test_user"},
        created_at=datetime.now(timezone.utc),
    )
    asyncio.run(_in_memory_submission_repo.save(sub))

    defect_reports = []
    if with_defects:
        defect_reports = [
            DefectReport(
                defect_id="def-test-01",
                verification_run_id="run-test-milestone1",
                submission_id=sub.id,
                title="Assertion failure in test_add_positive",
                description="Observed -1 when expected 3",
                failed_test="test_add_positive",
                failure_category="ASSERTION_FAILURE",
                severity=DefectSeverity.HIGH,
                file_path="solution.py",
                line_number=2,
                assertion_or_exception="assert -1 == 3",
                expected_value="3",
                actual_value="-1",
            )
        ]

    test_results = []
    if run_status == VerificationStatus.FAILED:
        test_results = [
            TestResult(
                test_id="t-1",
                name="test_add_positive",
                test_name="test_add_positive",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                duration_ms=12.0,
                error_message="assert -1 == 3",
            )
        ]
    elif run_status == VerificationStatus.PASSED:
        test_results = [
            TestResult(
                test_id="t-1",
                name="test_add_positive",
                test_name="test_add_positive",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
                duration_ms=10.0,
            )
        ]

    run = VerificationRunResponse(
        id="run-test-milestone1",
        submission_id=sub.id,
        status=run_status,
        passed_tests=1 if run_status == VerificationStatus.PASSED else 0,
        failed_tests=1 if run_status == VerificationStatus.FAILED else 0,
        total_tests=1,
        test_results=test_results,
        defect_reports=defect_reports,
        execution_telemetry={"docker_available": not infra_failure},
        error_message="Docker daemon offline" if infra_failure else None,
        created_at=datetime.now(timezone.utc),
        feedback_iterations=[],
    )
    asyncio.run(_in_memory_verification_repo.save(run))
    return run, sub


def test_component3_status_endpoint(client: TestClient):
    """
    Verifies that GET /api/v1/verifications/integrations/component-3/status
    returns the expected discovery status: contract under development, dispatch disabled.
    """
    res = client.get("/api/v1/verifications/integrations/component-3/status")
    assert res.status_code == 200
    data = res.json()
    assert data["contract_status"] == "UNDER_DEVELOPMENT"
    assert data["dispatch_allowed"] is False
    assert "reason" in data
    assert "Component 3" in data["reason"]


def test_approval_eligible_failed_run(client: TestClient):
    """
    Verifies that a human can explicitly approve technical feedback for an eligible FAILED run.
    """
    run, sub = _create_sample_run(run_status=VerificationStatus.FAILED, with_defects=True)

    res = client.post(
        f"/api/v1/verifications/{run.id}/approve-feedback",
        json={"approver": "lead_engineer@example.com", "notes": "Approved for C3 regeneration"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["approval_status"] == "APPROVED"
    assert data["approved_by"] == "lead_engineer@example.com"
    assert data["approved_at"] is not None
    assert data["delivery_status"] == "NOT_DISPATCHED"
    assert data["component_3_acknowledged"] is False

    # Check persistence in verification run
    run_res = client.get(f"/api/v1/verifications/{run.id}")
    assert run_res.status_code == 200
    iterations = run_res.json()["feedback_iterations"]
    assert len(iterations) == 1
    assert iterations[0]["approval_status"] == "APPROVED"


def test_approval_rejected_for_passed_run(client: TestClient):
    """
    Verifies that PASSED runs cannot be approved for dispatch (returns 400).
    """
    run, _ = _create_sample_run(run_status=VerificationStatus.PASSED, with_defects=False)

    res = client.post(
        f"/api/v1/verifications/{run.id}/approve-feedback",
        json={"approver": "engineer@example.com"},
    )
    assert res.status_code == 400
    msg = res.json()["error"]["message"]
    assert "Cannot approve feedback" in msg or "zero defects" in msg or "ineligible" in msg


def test_approval_rejected_for_pending_run(client: TestClient):
    """
    Verifies that PENDING runs cannot be approved for dispatch (returns 400).
    """
    run, _ = _create_sample_run(run_status=VerificationStatus.PENDING, with_defects=False)

    res = client.post(
        f"/api/v1/verifications/{run.id}/approve-feedback",
        json={"approver": "engineer@example.com"},
    )
    assert res.status_code == 400


def test_approval_rejected_for_infrastructure_failure(client: TestClient):
    """
    Verifies that runs with sandbox infrastructure failures cannot be approved for code correction.
    """
    run, _ = _create_sample_run(
        run_status=VerificationStatus.ERROR, with_defects=False, infra_failure=True
    )

    res = client.post(
        f"/api/v1/verifications/{run.id}/approve-feedback",
        json={"approver": "engineer@example.com"},
    )
    assert res.status_code == 400
    assert "infrastructure" in res.json()["error"]["message"].lower()


def test_dispatch_fails_closed_when_component3_disabled(client: TestClient):
    """
    Verifies that dispatching feedback when Component 3 is disabled fails closed safely,
    recording delivery_status='NOT_DISPATCHED' and error_category='COMPONENT_3_DISABLED'.
    """
    run, _ = _create_sample_run(run_status=VerificationStatus.FAILED, with_defects=True)

    # First approve
    client.post(
        f"/api/v1/verifications/{run.id}/approve-feedback",
        json={"approver": "tester@example.com"},
    )

    # Dispatch while disabled
    res = client.post(
        f"/api/v1/verifications/{run.id}/dispatch-feedback",
        json={"approved": True, "approver": "tester@example.com"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["delivery_status"] == "NOT_DISPATCHED"
    assert data["component_3_acknowledged"] is False
    assert data["error_category"] == "COMPONENT_3_DISABLED"
    assert "disabled" in data["message"].lower() or "under development" in data["message"].lower()


def test_dispatch_rejected_without_explicit_approval(client: TestClient):
    """
    Verifies that dispatch without approval (approved=False on an unapproved run) is rejected.
    """
    run, _ = _create_sample_run(run_status=VerificationStatus.FAILED, with_defects=True)

    res = client.post(
        f"/api/v1/verifications/{run.id}/dispatch-feedback",
        json={"approved": False, "approver": "tester@example.com"},
    )
    assert res.status_code == 400
    assert "approval" in res.json()["error"]["message"].lower()


def test_mock_http_client_successful_dispatch():
    """
    Verifies that when Component 3 is enabled, a successful HTTP 200/202 response
    with job_id marks the iteration as ACKNOWLEDGED with valid job ID and correlation ID.
    """
    run, sub = _create_sample_run(run_status=VerificationStatus.FAILED, with_defects=True)

    mock_client = Component3Client(
        base_url="http://127.0.0.1:8000",
        feedback_endpoint="/api/v1/correction-feedback",
        enabled=True,
    )

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = {
        "status": "QUEUED",
        "job_id": "c3-job-success-9988",
        "message": "Feedback accepted for code correction",
    }

    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_http_response

        dispatch_resp = asyncio.run(
            service.dispatch_feedback(
                run_id=run.id,
                approved=True,
                approver="lead_dev",
                client=mock_client,
            )
        )

        assert dispatch_resp.delivery_status == "ACKNOWLEDGED"
        assert dispatch_resp.component_3_acknowledged is True
        assert dispatch_resp.component_3_job_id == "c3-job-success-9988"
        assert dispatch_resp.correlation_id.startswith("corr-")

        # Verify persisted verification run
        updated_run = asyncio.run(service.get_verification_run(run.id))
        latest_iter = updated_run.feedback_iterations[-1]
        assert latest_iter.delivery_status == "ACKNOWLEDGED"
        assert latest_iter.component_3_job_id == "c3-job-success-9988"
        assert latest_iter.dispatched_at is not None
        assert latest_iter.acknowledged_at is not None


def test_mock_http_client_timeout_handling():
    """
    Verifies that HTTP connection / read timeouts fail gracefully with error_category='TIMEOUT'.
    """
    run, sub = _create_sample_run(run_status=VerificationStatus.FAILED, with_defects=True)

    mock_client = Component3Client(
        base_url="http://127.0.0.1:8000",
        feedback_endpoint="/api/v1/correction-feedback",
        enabled=True,
    )

    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Read timed out after 10.0s")

        dispatch_resp = asyncio.run(
            service.dispatch_feedback(
                run_id=run.id,
                approved=True,
                approver="lead_dev",
                client=mock_client,
            )
        )

        assert dispatch_resp.delivery_status == "FAILED"
        assert dispatch_resp.component_3_acknowledged is False
        assert dispatch_resp.error_category == "TIMEOUT"
        assert "timeout" in dispatch_resp.message.lower()


def test_mock_http_client_server_error_handling():
    """
    Verifies that HTTP 500 error responses from Component 3 are handled safely with error_category='HTTP_ERROR'.
    """
    run, sub = _create_sample_run(run_status=VerificationStatus.FAILED, with_defects=True)

    mock_client = Component3Client(
        base_url="http://127.0.0.1:8000",
        feedback_endpoint="/api/v1/correction-feedback",
        enabled=True,
    )

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.status_code = 500
    mock_http_response.text = "Internal Server Error in C3 pipeline"

    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_http_response

        dispatch_resp = asyncio.run(
            service.dispatch_feedback(
                run_id=run.id,
                approved=True,
                approver="lead_dev",
                client=mock_client,
            )
        )

        assert dispatch_resp.delivery_status == "FAILED"
        assert dispatch_resp.component_3_acknowledged is False
        assert dispatch_resp.error_category in ("HTTP_ERROR", "COMPONENT_3_ERROR_RESPONSE")


def test_duplicate_dispatch_idempotency():
    """
    Verifies that re-dispatching an already ACKNOWLEDGED feedback iteration is idempotent:
    it returns the existing iteration without sending a duplicate request or creating a new record.
    """
    run, sub = _create_sample_run(run_status=VerificationStatus.FAILED, with_defects=True)

    mock_client = Component3Client(
        base_url="http://127.0.0.1:8000",
        feedback_endpoint="/api/v1/correction-feedback",
        enabled=True,
    )

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = {
        "status": "ACCEPTED",
        "job_id": "c3-job-unique-123",
    }

    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_http_response

        # 1. First dispatch
        resp1 = asyncio.run(
            service.dispatch_feedback(
                run_id=run.id,
                approved=True,
                approver="lead_dev",
                client=mock_client,
            )
        )
        assert resp1.delivery_status == "ACKNOWLEDGED"
        assert mock_post.call_count == 1

        # 2. Second dispatch without force_retry
        resp2 = asyncio.run(
            service.dispatch_feedback(
                run_id=run.id,
                approved=True,
                approver="lead_dev",
                client=mock_client,
                force_retry=False,
            )
        )
        # Should be intercepted as already dispatched
        assert resp2.delivery_status == "ACKNOWLEDGED"
        assert resp2.component_3_job_id == "c3-job-unique-123"
        assert "already delivered" in resp2.message.lower()
        # Call count should STILL be 1 (no duplicate HTTP request)
        assert mock_post.call_count == 1

        # Check iterations count in database is still 1
        updated_run = asyncio.run(service.get_verification_run(run.id))
        assert len(updated_run.feedback_iterations) == 1


def test_strict_exclusion_of_xai_narratives_from_c3_payload():
    """
    CRITICAL SAFETY TEST:
    Verifies that the payload prepared for Component 3 contains ONLY technical defect data
    and NEVER contains human-facing XAI narratives, explanations, or recommendations.
    """
    client = Component3Client(
        base_url="http://127.0.0.1:8000",
        feedback_endpoint="/api/v1/correction-feedback",
        enabled=True,
    )

    # Prepare a payload that simulates accidental inclusion of XAI keys
    polluted_payload = {
        "schema_version": "1.0",
        "feedback_id": "fb-test-safe",
        "submission_id": "sub-test",
        "verification_run_id": "run-test",
        "test_results_summary": {"total": 2, "passed": 1, "failed": 1},
        "defects": [
            {
                "defect_id": "def-1",
                "failed_test_name": "test_tax",
                "defect_type": "AssertionFailure",
                "severity": "HIGH",
                "error_message": "assert 8.0 == 108.0",
                "suspected_file": "solution.py",
                "suspected_line_number": 6,
                "assertion_detail": {"expected": "108.0", "observed": "8.0"},
            }
        ],
        # XAI narrative fields that must NEVER reach Component 3
        "what_failed": "The tax calculation returned 8.0 instead of 108.0.",
        "confirmed_observations": ["Missing base amount in addition."],
        "evidence_based_interpretation": "The function omits the principal sum.",
        "recommendation": "Add amount + tax before returning.",
        "explanation_method": "RULE_BASED",
        "provider": "anthropic/claude-3.5-sonnet",
        "xai_explanation": {"detailed": "Forbidden narrative"},
    }

    sanitized = client.prepare_sanitized_payload(polluted_payload)

    # Technical fields must be preserved
    assert "feedback_id" in sanitized
    assert "defects" in sanitized
    assert len(sanitized["defects"]) == 1
    assert sanitized["defects"][0]["defect_id"] == "def-1"

    # Human-facing XAI fields must be strictly removed
    forbidden_keys = [
        "what_failed",
        "confirmed_observations",
        "evidence_based_interpretation",
        "recommendation",
        "suggested_investigations",
        "explanation_method",
        "provider",
        "xai_explanation",
    ]
    for key in forbidden_keys:
        assert key not in sanitized, f"Forbidden XAI key '{key}' was found in sanitized C3 payload!"
