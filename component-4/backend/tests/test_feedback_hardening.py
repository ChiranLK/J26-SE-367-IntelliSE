import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from starlette.testclient import TestClient

from app.core.errors import InvalidInputException
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
    DeliveryStatus,
    FeedbackIteration,
    TechnicalFeedbackPayload,
)
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse
from app.services.component3_client import Component3Client
from app.services.feedback_service import TechnicalFeedbackService
from app.services.verification_service import VerificationService


def _create_test_run_with_defects(
    run_id: str = "run-harden-test",
    submission_id: str = "sub-harden-test",
    run_status: VerificationStatus = VerificationStatus.FAILED,
    defects: bool = True,
    infra_failure: bool = False,
) -> tuple[VerificationRunResponse, CodeSubmissionResponse]:
    """Helper to set up test runs with explicit defect reports and test results."""
    sub = CodeSubmissionResponse(
        id=submission_id,
        code="def divide(a, b):\n    return a / b\n",
        language=ProgrammingLanguage.PYTHON,
        filename="math_lib.py",
        created_at=datetime.now(timezone.utc),
    )
    asyncio.run(_in_memory_submission_repo.save(sub))

    defect_reports = []
    if defects:
        defect_reports = [
            DefectReport(
                defect_id="def-math-01",
                verification_run_id=run_id,
                submission_id=submission_id,
                title="ZeroDivisionError on divide by zero",
                description="Unhandled division by zero in divide()",
                failed_test="test_divide_zero",
                failure_category="RUNTIME_EXCEPTION",
                severity=DefectSeverity.HIGH,
                file_path="math_lib.py",
                line_number=2,
                assertion_or_exception="ZeroDivisionError: division by zero",
                expected_value=None,
                actual_value="ZeroDivisionError",
            )
        ]

    test_results = []
    if run_status == VerificationStatus.FAILED:
        test_results = [
            TestResult(
                test_id="t-divide-01",
                name="test_divide_zero",
                test_name="test_divide_zero",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                duration_ms=15.0,
                error_message="ZeroDivisionError: division by zero",
            )
        ]
    elif run_status == VerificationStatus.PASSED:
        test_results = [
            TestResult(
                test_id="t-divide-01",
                name="test_divide_zero",
                test_name="test_divide_zero",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
                duration_ms=10.0,
            )
        ]

    run = VerificationRunResponse(
        id=run_id,
        submission_id=submission_id,
        status=run_status,
        passed_tests=1 if run_status == VerificationStatus.PASSED else 0,
        failed_tests=1 if run_status == VerificationStatus.FAILED else 0,
        total_tests=1,
        test_results=test_results,
        defect_reports=defect_reports,
        execution_telemetry={"docker_available": not infra_failure, "exit_code": 1 if run_status == VerificationStatus.FAILED else 0},
        error_message="Docker runner offline" if infra_failure else None,
        created_at=datetime.now(timezone.utc),
        feedback_iterations=[],
    )
    asyncio.run(_in_memory_verification_repo.save(run))
    return run, sub


# =========================================================================
# 1. Payload Validation & Human Explanation Isolation Tests
# =========================================================================

def test_valid_technical_feedback_payload_passes_validation():
    """Verifies that a well-formed technical feedback payload succeeds validation."""
    run, sub = _create_test_run_with_defects("run-valid-01", "sub-valid-01")
    service = TechnicalFeedbackService()

    payload = service.build_feedback_payload(run, sub)
    assert payload.feedback_id.startswith("fb-")
    assert payload.verification_run_id == run.id
    assert payload.submission_id == sub.id
    assert "def-math-01" in payload.defect_ids
    assert "test_divide_zero" in payload.failed_tests
    assert payload.schema_version == "1.0"
    # Should not raise
    service.validate_technical_feedback_payload(payload, run)


def test_payload_missing_required_references_rejected():
    """Verifies that payloads with missing required identifiers are rejected."""
    run, sub = _create_test_run_with_defects("run-missing-ref", "sub-missing-ref")
    service = TechnicalFeedbackService()
    payload = service.build_feedback_payload(run, sub)

    # Corrupt verification_run_id
    payload.verification_run_id = ""
    with pytest.raises(InvalidInputException) as exc:
        service.validate_technical_feedback_payload(payload, run)
    assert "verification_run_id" in str(exc.value)

    # Empty defect_ids
    payload.verification_run_id = run.id
    payload.defect_ids = []
    with pytest.raises(InvalidInputException) as exc:
        service.validate_technical_feedback_payload(payload, run)
    assert "defect ID" in str(exc.value)


def test_payload_with_unpersisted_or_fabricated_defect_id_rejected():
    """Verifies that payloads referencing unpersisted or fabricated defect IDs are rejected."""
    run, sub = _create_test_run_with_defects("run-bad-def", "sub-bad-def")
    service = TechnicalFeedbackService()
    payload = service.build_feedback_payload(run, sub)

    # Inject fabricated defect ID
    payload.defect_ids.append("def-fake-invented-999")
    with pytest.raises(InvalidInputException) as exc:
        service.validate_technical_feedback_payload(payload, run)
    assert "unpersisted or fabricated defect ID" in str(exc.value)


def test_payload_with_unpersisted_failed_test_name_rejected():
    """Verifies that payloads referencing unverified failed tests are rejected."""
    run, sub = _create_test_run_with_defects("run-bad-test", "sub-bad-test")
    service = TechnicalFeedbackService()
    payload = service.build_feedback_payload(run, sub)

    # Inject fabricated test name
    payload.failed_tests.append("test_completely_invented_suite")
    with pytest.raises(InvalidInputException) as exc:
        service.validate_technical_feedback_payload(payload, run)
    assert "unverified failed test" in str(exc.value)


def test_payload_preserves_legitimate_results_with_missing_optional_evidence():
    """Verifies that legitimate failed runs where optional evidence is empty still pass validation."""
    run, sub = _create_test_run_with_defects("run-opt-evid", "sub-opt-evid")
    service = TechnicalFeedbackService()
    payload = service.build_feedback_payload(run, sub)

    # Clear optional evidence fields
    payload.failed_assertions = []
    payload.value_comparisons = []
    payload.error_logs = []
    payload.test_failure_details = []

    # Should still validate successfully without error
    service.validate_technical_feedback_payload(payload, run)
    assert payload.failed_assertions == []
    assert payload.value_comparisons == []


def test_human_explanation_isolation_strictly_rejects_narratives():
    """
    CRITICAL ISOLATION TEST:
    Verifies that injecting human-facing XAI explanations, narratives, executive summaries,
    or provider metadata into technical feedback payloads is detected and rejected.
    """
    run, sub = _create_test_run_with_defects("run-leak-test", "sub-leak-test")
    service = TechnicalFeedbackService()
    payload = service.build_feedback_payload(run, sub)

    # Test each forbidden field in evidence_references
    forbidden_leak_samples = [
        {"xai_explanation": {"narrative": "The code failed due to missing zero check"}},
        {"summary": "Executive summary for stakeholders: test failed"},
        {"what_failed": "The divisor was zero."},
        {"confirmed_observations": ["Observation: return 0 not implemented"]},
        {"evidence_based_interpretation": "Interpreted root cause is logic error"},
        {"recommendation": "Use if b == 0: raise CustomException"},
        {"suggested_investigations": ["Check lines 2-5"]},
        {"explanation_method": "RULE_BASED"},
        {"provider": "openai/gpt-4o"},
        {"model_name": "claude-3-5-sonnet"},
    ]

    for forbidden_dict in forbidden_leak_samples:
        test_payload = payload.model_copy(deep=True)
        test_payload.evidence_references.update(forbidden_dict)
        with pytest.raises(InvalidInputException) as exc:
            service.validate_technical_feedback_payload(test_payload, run)
        assert "Human explanation isolation violation" in str(exc.value)


def test_client_sanitizer_removes_forbidden_keys_and_credentials():
    """
    Verifies that Component3Client.prepare_sanitized_payload strips forbidden keys and credentials.
    """
    client = Component3Client(
        base_url="https://mock-c3-receiver.internal:8080",
        enabled=True,
    )
    polluted_data = {
        "feedback_id": "fb-test-sanitize",
        "verification_run_id": "run-test",
        "submission_id": "sub-test",
        "verification_status": "FAILED",
        "affected_files": ["math.py"],
        "failed_tests": ["test_div"],
        "defect_ids": ["def-01"],
        # Injected forbidden fields
        "xai_explanation": "narrative leak",
        "summary": "human summary leak",
        "what_failed": "what failed leak",
        "recommendation": "do not divide by zero",
        "provider": "anthropic",
        "api_key": "sk-secret-token-12345",
        "mongodb_uri": "mongodb+srv://admin:pass@cluster0.net",
    }

    sanitized = client.prepare_sanitized_payload(polluted_data)
    assert sanitized["feedback_id"] == "fb-test-sanitize"
    assert "xai_explanation" not in sanitized
    assert "summary" not in sanitized
    assert "what_failed" not in sanitized
    assert "recommendation" not in sanitized
    assert "provider" not in sanitized
    assert "api_key" not in sanitized
    assert "mongodb_uri" not in sanitized


# =========================================================================
# 2. Feedback Approval & Eligibility Tests
# =========================================================================

def test_valid_approval_workflow():
    """Verifies that an eligible failed run can be approved with client-supplied reviewer."""
    run, sub = _create_test_run_with_defects("run-app-01", "sub-app-01")
    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )

    iteration = asyncio.run(
        service.approve_feedback(
            run_id=run.id,
            approver="qa_lead@intelise.internal",
            notes="Ready for automated code correction",
        )
    )

    assert iteration.approval_status == "APPROVED"
    assert iteration.approved_by == "qa_lead@intelise.internal"
    assert iteration.approved_at is not None
    # Crucial: approval does NOT automatically trigger dispatch
    assert iteration.delivery_status == "NOT_DISPATCHED"
    assert iteration.component_3_acknowledged is False


def test_repeated_approval_does_not_create_duplicate_iterations():
    """Verifies that calling approve multiple times on the same run does not create duplicate iterations."""
    run, sub = _create_test_run_with_defects("run-dup-app", "sub-dup-app")
    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )

    # First approval
    iter1 = asyncio.run(service.approve_feedback(run.id, approver="alice", notes="Note 1"))
    # Second approval
    iter2 = asyncio.run(service.approve_feedback(run.id, approver="bob", notes="Note 2"))

    updated_run = asyncio.run(service.get_verification_run(run.id))
    assert len(updated_run.feedback_iterations) == 1
    assert iter2.approved_by == "bob"
    assert iter2.notes == "Note 2"
    assert iter2.iteration_id == iter1.iteration_id


def test_approval_rejected_for_passed_run():
    """Verifies that PASSED runs cannot be approved for technical feedback."""
    run, sub = _create_test_run_with_defects("run-passed-app", "sub-passed-app", run_status=VerificationStatus.PASSED, defects=False)
    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )

    with pytest.raises(InvalidInputException) as exc:
        asyncio.run(service.approve_feedback(run.id))
    assert "zero defects" in str(exc.value).lower() or "passed" in str(exc.value).lower()


def test_approval_cannot_bypass_disabled_integration():
    """Verifies that approving feedback cannot bypass disabled Component 3 configuration."""
    run, sub = _create_test_run_with_defects("run-app-bypass", "sub-app-bypass")
    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )

    # Approve
    asyncio.run(service.approve_feedback(run.id, approver="lead_dev"))

    # Attempt dispatch with disabled client
    client = Component3Client(enabled=False)
    dispatch_res = asyncio.run(
        service.dispatch_feedback(run_id=run.id, approved=True, client=client)
    )

    assert dispatch_res.delivery_status == "NOT_DISPATCHED"
    assert dispatch_res.component_3_acknowledged is False
    assert dispatch_res.error_category == "COMPONENT_3_DISABLED"


# =========================================================================
# 3. Dispatch Safety & Idempotency Tests
# =========================================================================

def test_dispatch_fails_with_placeholder_or_self_referential_url():
    """Verifies that dispatching to a self-referential loopback address (127.0.0.1:8000) is rejected."""
    run, sub = _create_test_run_with_defects("run-loopback", "sub-loopback")
    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )
    asyncio.run(service.approve_feedback(run.id))

    # Client pointing to loopback with allow_placeholder_url=False (default)
    client = Component3Client(
        base_url="http://127.0.0.1:8000",
        enabled=True,
        allow_placeholder_url=False,
    )

    res = asyncio.run(service.dispatch_feedback(run_id=run.id, approved=True, client=client))
    assert res.delivery_status in ("FAILED", "NOT_DISPATCHED")
    assert res.error_category == "CONFIG_ERROR"
    assert "placeholder" in res.message.lower() or "self-referential" in res.message.lower()


def test_dispatch_rejected_without_prior_approval():
    """Verifies that attempting dispatch without approval is rejected with an error."""
    run, sub = _create_test_run_with_defects("run-unapproved-disp", "sub-unapproved-disp")
    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )

    with pytest.raises(InvalidInputException) as exc:
        asyncio.run(service.dispatch_feedback(run_id=run.id, approved=False))
    assert "approval" in str(exc.value).lower()


def test_concurrent_dispatch_protection():
    """
    Verifies that if an iteration is in PENDING_DELIVERY state, concurrent dispatch requests
    are rejected.
    """
    run, sub = _create_test_run_with_defects("run-concurrent", "sub-concurrent")
    service = TechnicalFeedbackService()
    payload = service.build_feedback_payload(run, sub)
    run, iteration = service.approve_feedback(run, sub)

    # Simulate in-flight dispatch lock
    iteration.delivery_status = DeliveryStatus.PENDING_DELIVERY.value

    with pytest.raises(InvalidInputException) as exc:
        asyncio.run(service.dispatch_feedback(run=run, submission=sub))
    assert "in progress" in str(exc.value).lower() or "concurrent" in str(exc.value).lower()


def test_dispatch_timeout_yields_unknown_delivery_status():
    """
    CRITICAL CONTRACT SAFETY TEST:
    Verifies that when an HTTP timeout occurs during dispatch, delivery_status is set to UNKNOWN
    (remote outcome ambiguous) and automatic retry is suppressed.
    """
    run, sub = _create_test_run_with_defects("run-timeout-unknown", "sub-timeout-unknown")
    mock_client = Component3Client(
        base_url="https://mock-c3-receiver.internal:8080",
        enabled=True,
    )

    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )
    asyncio.run(service.approve_feedback(run.id))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ReadTimeout("Read timeout after 10.0 seconds")

        dispatch_res = asyncio.run(
            service.dispatch_feedback(run_id=run.id, approved=True, client=mock_client)
        )

        assert dispatch_res.delivery_status == "UNKNOWN"
        assert dispatch_res.component_3_acknowledged is False
        assert dispatch_res.error_category == "TIMEOUT"
        assert "unknown" in dispatch_res.message.lower() or "timeout" in dispatch_res.message.lower()

        # Check persisted verification run iteration state
        updated_run = asyncio.run(service.get_verification_run(run.id))
        latest_iter = updated_run.feedback_iterations[-1]
        assert latest_iter.delivery_status == "UNKNOWN"
        assert latest_iter.error_category == "TIMEOUT"
        assert latest_iter.attempt_count == 1
        assert len(latest_iter.attempt_timestamps) == 1


def test_dispatch_invalid_acknowledgment_missing_job_id():
    """
    Verifies that if Component 3 responds with HTTP 200 but lacks a valid job ID,
    the delivery is NOT marked as acknowledged, failing closed with INVALID_ACKNOWLEDGMENT.
    """
    run, sub = _create_test_run_with_defects("run-bad-ack", "sub-bad-ack")
    mock_client = Component3Client(
        base_url="https://mock-c3-receiver.internal:8080",
        enabled=True,
    )

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "SUCCESS"}  # Missing job_id

    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )
    asyncio.run(service.approve_feedback(run.id))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        dispatch_res = asyncio.run(
            service.dispatch_feedback(run_id=run.id, approved=True, client=mock_client)
        )

        assert dispatch_res.delivery_status == "FAILED"
        assert dispatch_res.component_3_acknowledged is False
        assert dispatch_res.error_category == "INVALID_ACKNOWLEDGMENT"


def test_mock_receiver_successful_acknowledgment():
    """
    Verifies that a verified receiver acknowledgment results in ACKNOWLEDGED state
    with job ID and attempt tracking.
    """
    run, sub = _create_test_run_with_defects("run-mock-ack", "sub-mock-ack")
    mock_client = Component3Client(
        base_url="https://mock-c3-receiver.internal:8080",
        enabled=True,
    )

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ACCEPTED",
        "job_id": "c3-job-harden-7766",
    }

    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )
    asyncio.run(service.approve_feedback(run.id))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        dispatch_res = asyncio.run(
            service.dispatch_feedback(run_id=run.id, approved=True, client=mock_client)
        )

        assert dispatch_res.delivery_status == "ACKNOWLEDGED"
        assert dispatch_res.component_3_acknowledged is True
        assert dispatch_res.component_3_job_id == "c3-job-harden-7766"
        assert dispatch_res.attempt_count == 1

        # Check persisted run
        updated_run = asyncio.run(service.get_verification_run(run.id))
        latest_iter = updated_run.feedback_iterations[-1]
        assert latest_iter.delivery_status == "ACKNOWLEDGED"
        assert latest_iter.component_3_job_id == "c3-job-harden-7766"
        assert latest_iter.attempt_count == 1
        assert len(latest_iter.attempt_timestamps) == 1


# =========================================================================
# 4. Lifecycle & Historical MongoDB Compatibility Tests
# =========================================================================

def test_attempt_counting_across_retries():
    """Verifies attempt counting and timestamp appending across multiple dispatch attempts."""
    run, sub = _create_test_run_with_defects("run-retry-count", "sub-retry-count")
    mock_client = Component3Client(
        base_url="https://mock-c3-receiver.internal:8080",
        enabled=True,
    )

    service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
    )
    asyncio.run(service.approve_feedback(run.id))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # First attempt times out
        mock_post.side_effect = httpx.ReadTimeout("Timeout")
        res1 = asyncio.run(
            service.dispatch_feedback(run_id=run.id, approved=True, client=mock_client)
        )
        assert res1.delivery_status == "UNKNOWN"
        assert res1.attempt_count == 1

        # Second attempt with force_retry succeeds
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"job_id": "c3-retry-job-002"}
        mock_post.side_effect = None
        mock_post.return_value = mock_resp

        res2 = asyncio.run(
            service.dispatch_feedback(run_id=run.id, approved=True, force_retry=True, client=mock_client)
        )
        assert res2.delivery_status == "ACKNOWLEDGED"
        assert res2.attempt_count == 2
        assert len(res2.iteration.attempt_timestamps) == 2


def test_historical_mongodb_document_backward_compatibility():
    """
    Verifies that historical MongoDB documents created before Milestone 2
    (without attempt_count, attempt_timestamps, sanitized_error_message)
    load and deserialize cleanly with safe defaults.
    """
    old_doc = {
        "id": "run-legacy-mongo",
        "submission_id": "sub-legacy-mongo",
        "status": "FAILED",
        "passed_tests": 0,
        "failed_tests": 1,
        "total_tests": 1,
        "test_results": [],
        "defect_reports": [],
        "feedback_iterations": [
            {
                "iteration_id": "iter-legacy-1",
                "iteration_number": 1,
                "verification_run_id": "run-legacy-mongo",
                "submission_id": "sub-legacy-mongo",
                "defects_count": 1,
                "defect_ids": ["def-legacy-1"],
                "status": "AWAITING_REVISION",
                "component_3_acknowledged": False,
                "created_at": "2026-10-14T10:00:00Z",
                "delivery_status": "NOT_DISPATCHED",
                "approval_status": "APPROVED",
                "approved_by": "qa_tester",
                # Omit attempt_count, attempt_timestamps, sanitized_error_message
            }
        ],
        "created_at": "2026-10-14T10:00:00Z",
        "updated_at": "2026-10-14T10:00:00Z",
    }

    # Deserialization via Pydantic model_validate
    run_obj = VerificationRunResponse.model_validate(old_doc)
    assert len(run_obj.feedback_iterations) == 1
    iter_obj = run_obj.feedback_iterations[0]
    # Check default fallbacks
    assert iter_obj.attempt_count == 0
    assert iter_obj.attempt_timestamps == []
    assert iter_obj.sanitized_error_message is None
    assert iter_obj.delivery_status == "NOT_DISPATCHED"


def test_readiness_checklist_endpoint_status(client: TestClient):
    """
    Verifies that the status endpoint returns the 6-point readiness checklist.
    """
    res = client.get("/api/v1/verifications/integrations/component-3/status")
    assert res.status_code == 200
    data = res.json()
    assert "readiness_checklist" in data
    checklist = data["readiness_checklist"]
    assert "verified_receiver_url" in checklist
    assert "confirmed_endpoint" in checklist
    assert "agreed_request_schema" in checklist
    assert "agreed_acknowledgment_schema" in checklist
    assert "safe_idempotency_defined" in checklist
    assert "explicit_enabled_flag" in checklist
    assert data["dispatch_allowed"] is False
