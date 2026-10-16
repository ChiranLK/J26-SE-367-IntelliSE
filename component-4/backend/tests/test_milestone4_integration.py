"""
Milestone 4 Integration Readiness, API Contracts, Reliability & Mock Testing

Covers all 12 mandatory integration scenarios:
  1. Successful feedback acceptance
  2. Invalid feedback rejection
  3. Authentication rejection
  4. Connection timeout
  5. Temporary server failure (transient 503 recovered by retry)
  6. Duplicate feedback delivery (idempotency on ACKNOWLEDGED iteration)
  7. Valid corrected-code response (inbound delivery endpoint)
  8. Invalid corrected-code response (syntax error rejection)
  9. Correlation identifier mismatch rejection
 10. Duplicate repair response (idempotency on external_repair_job_id)
 11. Retry exhaustion (persistent failure)
 12. Disabled-integration behavior (fail-closed, no network calls)

Uses an isolated in-memory test environment. Zero production network calls or Atlas DB writes.
"""

import asyncio
from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.repositories import (
    _in_memory_repair_repo,
    _in_memory_submission_repo,
    _in_memory_verification_repo,
)
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
from app.schemas.repair import (
    Component3RepairDeliveryRequest,
    RepairResponseStatus,
    RepairSource,
)
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse
from app.services.component3_client import Component3Client
from app.services.feedback_service import TechnicalFeedbackService
from tests.mock_component3 import MockComponent3Receiver, create_mock_transport_client


async def _setup_failed_run_with_defects_async(
    run_id: str = "run-m4-test-01",
    sub_id: str = "sub-m4-test-01",
    iter_id: str = "iter-m4-test-01",
    correlation_id: str = "corr-m4-test-01",
    approved: bool = True,
    delivery_status: str = "NOT_DISPATCHED",
) -> tuple[VerificationRunResponse, CodeSubmissionResponse]:
    """Sets up an eligible failed verification run in memory asynchronously."""
    sub = CodeSubmissionResponse(
        id=sub_id,
        code="def solve(x):\n    return x - 1\n",
        language=ProgrammingLanguage.PYTHON,
        filename="solution.py",
        test_code="def test_solve():\n    assert solve(5) == 6\n",
        created_at=datetime.now(timezone.utc),
    )
    await _in_memory_submission_repo.save(sub)

    defect = DefectReport(
        defect_id=f"def-{run_id}-01",
        verification_run_id=run_id,
        submission_id=sub_id,
        title="Incorrect calculation outcome",
        description="Expected 6 but received 4",
        failed_test="test_solve",
        failure_category="ASSERTION_FAILURE",
        severity=DefectSeverity.HIGH,
        file_path="solution.py",
        line_number=2,
        assertion_or_exception="assert 4 == 6",
        expected_value="6",
        actual_value="4",
    )

    test_res = TestResult(
        test_id=f"t-{run_id}-01",
        name="test_solve",
        test_name="test_solve",
        test_type=TestType.UNIT,
        status=TestResultStatus.FAILED,
        duration_ms=10.0,
        error_message="assert 4 == 6",
    )

    iteration = FeedbackIteration(
        iteration_id=iter_id,
        iteration_number=1,
        verification_run_id=run_id,
        submission_id=sub_id,
        defects_count=1,
        defect_ids=[defect.defect_id],
        status="AWAITING_REVISION",
        component_3_acknowledged=(delivery_status == "ACKNOWLEDGED"),
        notes="Automated technical feedback cycle #1",
        approval_status="APPROVED" if approved else "PENDING_APPROVAL",
        delivery_status=delivery_status,
        correlation_id=correlation_id,
        component_3_job_id="c3-job-existing-01" if delivery_status == "ACKNOWLEDGED" else None,
        created_at=datetime.now(timezone.utc),
    )

    run = VerificationRunResponse(
        id=run_id,
        submission_id=sub_id,
        status=VerificationStatus.FAILED,
        passed_tests=0,
        failed_tests=1,
        total_tests=1,
        test_results=[test_res],
        defect_reports=[defect],
        feedback_iterations=[iteration],
        execution_telemetry={"docker_available": True, "exit_code": 1},
        created_at=datetime.now(timezone.utc),
    )
    await _in_memory_verification_repo.save(run)
    return run, sub


def _setup_failed_run_with_defects(
    run_id: str = "run-m4-test-01",
    sub_id: str = "sub-m4-test-01",
    iter_id: str = "iter-m4-test-01",
    correlation_id: str = "corr-m4-test-01",
    approved: bool = True,
    delivery_status: str = "NOT_DISPATCHED",
) -> tuple[VerificationRunResponse, CodeSubmissionResponse]:
    """Synchronous helper for TestClient tests."""
    return asyncio.run(_setup_failed_run_with_defects_async(
        run_id=run_id,
        sub_id=sub_id,
        iter_id=iter_id,
        correlation_id=correlation_id,
        approved=approved,
        delivery_status=delivery_status,
    ))


def _extract_error_text(res) -> str:
    """Helper to extract error text regardless of whether detail or error.message was used."""
    data = res.json()
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"]).lower()
        if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
            return str(data["error"]["message"]).lower()
    return str(data).lower()


@pytest.mark.anyio
async def test_scenario_01_successful_feedback_acceptance():
    """Scenario 1: Successful technical feedback dispatch and job_id acknowledgment."""
    receiver = MockComponent3Receiver(scenario="SUCCESS", expected_api_key="secret-key")
    async with create_mock_transport_client(receiver) as mock_http:
        client = Component3Client(
            base_url="http://mock-component-3.test",
            enabled=True,
            api_key="secret-key",
            http_client=mock_http,
            allow_placeholder_url=True,
        )
        run, sub = await _setup_failed_run_with_defects_async(run_id="run-s1", iter_id="iter-s1")
        feedback_svc = TechnicalFeedbackService()
        payload = feedback_svc.build_feedback_payload(run, sub)

        result = await client.dispatch_feedback(
            payload=payload,
            correlation_id="corr-s1",
            idempotency_key="disp-s1",
        )

        assert result.success is True
        assert result.acknowledged is True
        assert result.job_id.startswith("c3-job-success")
        assert result.error_category is None
        assert receiver.call_count == 1
        assert receiver.received_requests[0]["headers"]["x-correlation-id"] == "corr-s1"


@pytest.mark.anyio
async def test_scenario_02_invalid_feedback_rejection():
    """Scenario 2: Component 3 rejects invalid payload with 422 Unprocessable Entity."""
    receiver = MockComponent3Receiver(scenario="VALIDATION_FAIL", expected_api_key="secret-key")
    async with create_mock_transport_client(receiver) as mock_http:
        client = Component3Client(
            base_url="http://mock-component-3.test",
            enabled=True,
            api_key="secret-key",
            http_client=mock_http,
            allow_placeholder_url=True,
        )
        run, sub = await _setup_failed_run_with_defects_async(run_id="run-s2", iter_id="iter-s2")
        feedback_svc = TechnicalFeedbackService()
        payload = feedback_svc.build_feedback_payload(run, sub)

        result = await client.dispatch_feedback(payload=payload, correlation_id="corr-s2")

        assert result.success is False
        assert result.acknowledged is False
        assert result.error_category == "VALIDATION_ERROR"
        assert result.status_code == 422
        # Non-retryable: exactly 1 attempt
        assert receiver.call_count == 1


@pytest.mark.anyio
async def test_scenario_03_authentication_rejection():
    """Scenario 3: Component 3 rejects request with 401 Unauthorized due to bad key."""
    receiver = MockComponent3Receiver(scenario="SUCCESS", expected_api_key="correct-key")
    async with create_mock_transport_client(receiver) as mock_http:
        client = Component3Client(
            base_url="http://mock-component-3.test",
            enabled=True,
            api_key="wrong-key",  # Invalid key
            http_client=mock_http,
            allow_placeholder_url=True,
        )
        run, sub = await _setup_failed_run_with_defects_async(run_id="run-s3", iter_id="iter-s3")
        feedback_svc = TechnicalFeedbackService()
        payload = feedback_svc.build_feedback_payload(run, sub)

        result = await client.dispatch_feedback(payload=payload, correlation_id="corr-s3")

        assert result.success is False
        assert result.acknowledged is False
        assert result.error_category == "AUTHENTICATION_FAILURE"
        assert result.status_code == 401
        assert receiver.call_count == 1


@pytest.mark.anyio
async def test_scenario_04_connection_timeout_suppresses_retry():
    """Scenario 4: Request timeout after transmission marks UNKNOWN and suppresses retry."""
    receiver = MockComponent3Receiver(scenario="TIMEOUT", expected_api_key="secret-key")
    async with create_mock_transport_client(receiver) as mock_http:
        client = Component3Client(
            base_url="http://mock-component-3.test",
            enabled=True,
            api_key="secret-key",
            http_client=mock_http,
            allow_placeholder_url=True,
        )
        run, sub = await _setup_failed_run_with_defects_async(run_id="run-s4", iter_id="iter-s4")
        feedback_svc = TechnicalFeedbackService()
        payload = feedback_svc.build_feedback_payload(run, sub)

        result = await client.dispatch_feedback(payload=payload, correlation_id="corr-s4")

        assert result.success is False
        assert result.acknowledged is False
        assert result.error_category == "TIMEOUT"
        assert "Automatic retry suppressed" in result.message
        # Must not retry to prevent duplicate work on Component 3
        assert receiver.call_count == 1


@pytest.mark.anyio
async def test_scenario_05_temporary_server_failure_recovers_via_retry():
    """Scenario 5: Component 3 returns 503 on 1st attempt, but recovers and succeeds on retry."""
    receiver = MockComponent3Receiver(
        scenario="TRANSIENT_503",
        expected_api_key="secret-key",
        transient_failures_allowed=1,
    )
    async with create_mock_transport_client(receiver) as mock_http:
        client = Component3Client(
            base_url="http://mock-component-3.test",
            enabled=True,
            api_key="secret-key",
            max_retries=2,
            http_client=mock_http,
            allow_placeholder_url=True,
        )
        run, sub = await _setup_failed_run_with_defects_async(run_id="run-s5", iter_id="iter-s5")
        feedback_svc = TechnicalFeedbackService()
        payload = feedback_svc.build_feedback_payload(run, sub)

        result = await client.dispatch_feedback(payload=payload, correlation_id="corr-s5")

        assert result.success is True
        assert result.acknowledged is True
        assert result.status_code == 200
        # Exactly 2 calls: 1 initial failure + 1 successful retry
        assert receiver.call_count == 2


@pytest.mark.anyio
async def test_scenario_06_duplicate_feedback_delivery_idempotency():
    """Scenario 6: Outbound dispatch on an already ACKNOWLEDGED iteration skips network transmission."""
    receiver = MockComponent3Receiver(scenario="SUCCESS")
    async with create_mock_transport_client(receiver) as mock_http:
        client = Component3Client(
            base_url="http://mock-component-3.test",
            enabled=True,
            api_key="secret-key",
            http_client=mock_http,
            allow_placeholder_url=True,
        )
        run, sub = await _setup_failed_run_with_defects_async(
            run_id="run-s6",
            iter_id="iter-s6",
            delivery_status=DeliveryStatus.ACKNOWLEDGED.value,
        )
        feedback_svc = TechnicalFeedbackService()

        updated_run, iteration, skipped, result = await feedback_svc.dispatch_feedback(
            run=run,
            submission=sub,
            client=client,
            force_retry=False,
        )

        assert skipped is True
        assert result is None
        assert iteration.delivery_status == DeliveryStatus.ACKNOWLEDGED.value
        # No network calls made
        assert receiver.call_count == 0


def test_scenario_07_valid_corrected_code_inbound_delivery(client: TestClient):
    """Scenario 7: Component 3 delivers valid corrected Python code via dedicated inbound endpoint."""
    run_id = "run-s7"
    iter_id = "iter-s7"
    corr_id = "corr-s7"
    _setup_failed_run_with_defects(
        run_id=run_id,
        iter_id=iter_id,
        correlation_id=corr_id,
        approved=True,
    )

    payload = {
        "contract_version": "1.0",
        "verification_run_id": run_id,
        "feedback_iteration_id": iter_id,
        "correlation_id": corr_id,
        "external_repair_job_id": "c3-job-s7-442",
        "corrected_code": "def solve(x):\n    return x + 1\n",
        "filename": "solution.py",
        "repair_provenance": "EXTERNAL_COMPONENT_3",
        "notes": "Fixed subtraction to addition",
    }

    res = client.post(
        f"/api/v1/verifications/{run_id}/integrations/component-3/repair-delivery",
        json=payload,
    )

    assert res.status_code == 201
    data = res.json()
    assert data["original_run_id"] == run_id
    assert data["feedback_iteration_id"] == iter_id
    assert data["external_repair_job_id"] == "c3-job-s7-442"
    assert data["status"] == "INGESTED"
    assert data["repair_id"].startswith("rep-")


def test_scenario_08_invalid_corrected_code_rejection(client: TestClient):
    """Scenario 8: Inbound delivery of code with syntax error or bad file extension is rejected."""
    run_id = "run-s8"
    iter_id = "iter-s8"
    _setup_failed_run_with_defects(run_id=run_id, iter_id=iter_id, approved=True)

    # 1. Syntax error
    syntax_error_payload = {
        "contract_version": "1.0",
        "verification_run_id": run_id,
        "feedback_iteration_id": iter_id,
        "external_repair_job_id": "c3-job-s8-err",
        "corrected_code": "def broken(:\n    pass\n",  # Syntax error
        "filename": "solution.py",
    }
    res1 = client.post(
        f"/api/v1/verifications/{run_id}/integrations/component-3/repair-delivery",
        json=syntax_error_payload,
    )
    assert res1.status_code == 400
    assert "syntax error" in _extract_error_text(res1)

    # 2. Non-python extension (.sh)
    bad_ext_payload = {
        "contract_version": "1.0",
        "verification_run_id": run_id,
        "feedback_iteration_id": iter_id,
        "external_repair_job_id": "c3-job-s8-ext",
        "corrected_code": "echo 'malicious'\n",
        "filename": "exploit.sh",
    }
    res2 = client.post(
        f"/api/v1/verifications/{run_id}/integrations/component-3/repair-delivery",
        json=bad_ext_payload,
    )
    assert res2.status_code == 422  # Pydantic schema validation rejects non-.py


def test_scenario_09_correlation_identifier_mismatch(client: TestClient):
    """Scenario 9: Inbound delivery with mismatched correlation_id is rejected."""
    run_id = "run-s9"
    iter_id = "iter-s9"
    _setup_failed_run_with_defects(
        run_id=run_id,
        iter_id=iter_id,
        correlation_id="corr-authorized-99",
        approved=True,
    )

    payload = {
        "contract_version": "1.0",
        "verification_run_id": run_id,
        "feedback_iteration_id": iter_id,
        "correlation_id": "corr-spoofed-attacker-01",  # Mismatch
        "external_repair_job_id": "c3-job-s9",
        "corrected_code": "def solve(x):\n    return x + 1\n",
        "filename": "solution.py",
    }

    res = client.post(
        f"/api/v1/verifications/{run_id}/integrations/component-3/repair-delivery",
        json=payload,
    )

    assert res.status_code == 400
    assert "correlation identifier mismatch" in _extract_error_text(res)


def test_scenario_10_duplicate_repair_response_idempotency(client: TestClient):
    """Scenario 10: Inbound delivery of duplicate external_repair_job_id returns existing record without duplicating submission."""
    run_id = "run-s10"
    iter_id = "iter-s10"
    _setup_failed_run_with_defects(run_id=run_id, iter_id=iter_id, approved=True)

    payload = {
        "contract_version": "1.0",
        "verification_run_id": run_id,
        "feedback_iteration_id": iter_id,
        "external_repair_job_id": "c3-job-duplicate-10",
        "corrected_code": "def solve(x):\n    return x + 1\n",
        "filename": "solution.py",
    }

    # Initial delivery
    res1 = client.post(
        f"/api/v1/verifications/{run_id}/integrations/component-3/repair-delivery",
        json=payload,
    )
    assert res1.status_code == 201
    repair_id_1 = res1.json()["repair_id"]
    sub_id_1 = res1.json()["corrected_submission_id"]

    # Duplicate delivery
    res2 = client.post(
        f"/api/v1/verifications/{run_id}/integrations/component-3/repair-delivery",
        json=payload,
    )
    assert res2.status_code == 201
    repair_id_2 = res2.json()["repair_id"]
    sub_id_2 = res2.json()["corrected_submission_id"]

    # Idempotent: same repair_id and submission_id returned
    assert repair_id_1 == repair_id_2
    assert sub_id_1 == sub_id_2


@pytest.mark.anyio
async def test_scenario_11_retry_exhaustion_on_persistent_failure():
    """Scenario 11: Persistent 503 across all retries exhausts attempts and records failure."""
    receiver = MockComponent3Receiver(scenario="PERSISTENT_503", expected_api_key="secret-key")
    async with create_mock_transport_client(receiver) as mock_http:
        client = Component3Client(
            base_url="http://mock-component-3.test",
            enabled=True,
            api_key="secret-key",
            max_retries=2,  # 1 initial + 2 retries = 3 attempts
            http_client=mock_http,
            allow_placeholder_url=True,
        )
        run, sub = await _setup_failed_run_with_defects_async(run_id="run-s11", iter_id="iter-s11")
        feedback_svc = TechnicalFeedbackService()
        payload = feedback_svc.build_feedback_payload(run, sub)

        result = await client.dispatch_feedback(payload=payload, correlation_id="corr-s11")

        assert result.success is False
        assert result.acknowledged is False
        assert result.error_category in ("SERVER_ERROR", "COMPONENT_3_ERROR_RESPONSE")
        assert result.status_code == 503
        # Exactly 3 attempts: 1 + max_retries(2)
        assert receiver.call_count == 3


@pytest.mark.anyio
async def test_scenario_12_disabled_integration_behavior():
    """Scenario 12: When COMPONENT_3_ENABLED is False, dispatch skips all network calls and returns COMPONENT_3_DISABLED."""
    receiver = MockComponent3Receiver(scenario="SUCCESS")
    async with create_mock_transport_client(receiver) as mock_http:
        client = Component3Client(
            base_url="http://mock-component-3.test",
            enabled=False,  # Disabled
            http_client=mock_http,
            allow_placeholder_url=True,
        )
        run, sub = await _setup_failed_run_with_defects_async(run_id="run-s12", iter_id="iter-s12")
        feedback_svc = TechnicalFeedbackService()
        payload = feedback_svc.build_feedback_payload(run, sub)

        result = await client.dispatch_feedback(payload=payload, correlation_id="corr-s12")

        assert result.success is False
        assert result.acknowledged is False
        assert result.error_category == "COMPONENT_3_DISABLED"
        assert "Actual HTTP delivery was not attempted" in result.message
        # Zero network calls
        assert receiver.call_count == 0
