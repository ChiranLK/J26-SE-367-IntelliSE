import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from starlette.testclient import TestClient

from app.core.errors import FileValidationException, InvalidInputException, ResourceNotFoundException
from app.repositories import (
    _in_memory_repair_repo,
    _in_memory_submission_repo,
    _in_memory_test_suite_repo,
    _in_memory_verification_repo,
)
from app.repositories.mongo import MongoRepairRepository, MongoTestSuiteRepository
from app.schemas.test_suite import (
    TestSuiteProvenance,
    TrustedTestSuite,
    TrustedTestSuiteAttachRequest,
    TrustedTestSuiteResponse,
)
from app.schemas.common import (
    DefectSeverity,
    ProgrammingLanguage,
    TestResultStatus,
    TestType,
    VerificationStatus,
)
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import FeedbackIteration
from app.schemas.repair import (
    DefectResolutionComparison,
    DefectResolutionDetail,
    OverallResolutionVerdict,
    RepairAttempt,
    RepairAttemptResponse,
    RepairResponseStatus,
    RepairSource,
    ResolutionStatus,
    is_inconsistent_repair_attempt,
)
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunCreate, VerificationRunResponse
from app.services.defect_resolution_service import DefectResolutionService
from app.services.repair_service import RepairService
from app.services.verification_service import VerificationService


def _setup_failed_run_with_approved_feedback(
    run_id: str = "run-475a39076d8e",
    submission_id: str = "sub-01057496e861",
    iteration_id: str = "iter-efbb1924c93f",
    is_approved: bool = True,
    run_status: VerificationStatus = VerificationStatus.FAILED,
) -> tuple[VerificationRunResponse, CodeSubmissionResponse, FeedbackIteration]:
    """Sets up a failed verification run with an approved feedback iteration in in-memory storage."""
    now = datetime.now(timezone.utc)

    orig_code = (
        "def calculate_total(subtotal, tax_rate):\n"
        "    # Buggy: ignores tax_rate\n"
        "    return subtotal\n"
    )
    test_code = (
        "def test_total_with_tax():\n"
        "    assert calculate_total(100, 0.1) == 110\n"
        "def test_total_without_tax():\n"
        "    assert calculate_total(50, 0.0) == 50\n"
    )

    sub = CodeSubmissionResponse(
        id=submission_id,
        code=orig_code,
        language=ProgrammingLanguage.PYTHON,
        filename="billing.py",
        test_code=test_code,
        created_at=now,
    )
    asyncio.run(_in_memory_submission_repo.save(sub))

    defects = [
        DefectReport(
            defect_id="def-tax-01",
            verification_run_id=run_id,
            submission_id=submission_id,
            title="test_total_with_tax assertion failure",
            description="Expected 110, got 100",
            failed_test="test_total_with_tax",
            assertion_or_exception="assert 100 == 110",
            severity=DefectSeverity.HIGH,
            created_at=now,
        ),
        DefectReport(
            defect_id="def-tax-02",
            verification_run_id=run_id,
            submission_id=submission_id,
            title="test_total_without_tax failure",
            description="Unexpected calculation error",
            failed_test="test_total_without_tax",
            assertion_or_exception="assert 0 == 50",
            severity=DefectSeverity.MEDIUM,
            created_at=now,
        ),
    ]

    test_results = [
        TestResult(
            test_id="t1",
            name="test_total_with_tax",
            test_type=TestType.UNIT,
            status=TestResultStatus.FAILED,
            error_message="assert 100 == 110",
        ),
        TestResult(
            test_id="t2",
            name="test_total_without_tax",
            test_type=TestType.UNIT,
            status=TestResultStatus.FAILED,
            error_message="assert 0 == 50",
        ),
    ]

    iteration = FeedbackIteration(
        iteration_id=iteration_id,
        iteration_number=1,
        verification_run_id=run_id,
        submission_id=submission_id,
        defects_count=2,
        defect_ids=["def-tax-01", "def-tax-02"],
        approval_status="APPROVED" if is_approved else "PENDING_APPROVAL",
        approved_at=now if is_approved else None,
        approved_by="lead_reviewer" if is_approved else None,
        created_at=now,
    )

    run = VerificationRunResponse(
        id=run_id,
        submission_id=submission_id,
        status=run_status,
        triggered_by="manual",
        requested_test_types=[TestType.UNIT],
        test_results=test_results,
        defect_reports=defects,
        feedback_iterations=[iteration],
        execution_telemetry={"trusted_test_cases": test_code},
        created_at=now,
        updated_at=now,
    )
    asyncio.run(_in_memory_verification_repo.save(run))

    return run, sub, iteration


# ---------------------------------------------------------------------------
# Ingestion Tests
# ---------------------------------------------------------------------------


def test_repair_ingestion_success(client: TestClient):
    """Verify successful local repair ingestion creates a new submission and returns 201."""
    run, sub, it = _setup_failed_run_with_approved_feedback()

    corrected_code = (
        "def calculate_total(subtotal, tax_rate):\n"
        "    return subtotal + (subtotal * tax_rate)\n"
    )

    payload = {
        "corrected_code": corrected_code,
        "filename": "billing.py",
        "feedback_iteration_id": it.iteration_id,
        "repair_source": "LOCAL_MANUAL",
        "notes": "Fixed tax computation by adding tax percentage to subtotal.",
    }

    res = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=payload)
    assert res.status_code == 201
    data = res.json()

    assert data["repair_id"].startswith("rep-")
    assert data["original_run_id"] == run.id
    assert data["original_submission_id"] == sub.id
    assert data["feedback_iteration_id"] == it.iteration_id
    assert data["status"] == "INGESTED"
    assert data["corrected_filename"] == "billing.py"
    assert data["corrected_submission_id"].startswith("sub-")
    assert data["corrected_submission_id"] != sub.id  # Must be a separate submission!
    assert data["corrected_run_id"] is None
    assert data["comparison"] is None

    # Verify original submission remains completely unchanged
    stored_orig = asyncio.run(_in_memory_submission_repo.get_by_id(sub.id))
    assert stored_orig is not None
    assert stored_orig.code == sub.code
    assert "return subtotal\n" in stored_orig.code

    # Verify corrected submission holds the new code and inherited test oracle
    stored_corr = asyncio.run(_in_memory_submission_repo.get_by_id(data["corrected_submission_id"]))
    assert stored_corr is not None
    assert stored_corr.code == corrected_code
    assert stored_corr.test_code == sub.test_code


def test_repair_ingestion_omitted_iteration_resolves_latest_approved(client: TestClient):
    """If feedback_iteration_id is omitted, it auto-resolves the latest approved iteration."""
    run, _, it = _setup_failed_run_with_approved_feedback()

    payload = {
        "corrected_code": "def calculate_total(subtotal, tax_rate):\n    return subtotal * (1 + tax_rate)\n",
        "filename": "billing.py",
    }

    res = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["feedback_iteration_id"] == it.iteration_id


def test_repair_ingestion_nonexistent_run_returns_404(client: TestClient):
    """Attempting repair ingestion for an unknown run ID returns 404."""
    res = client.post(
        "/api/v1/verifications/run-unknown-9999/repair-responses",
        json={"corrected_code": "x = 1\n"},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_repair_ingestion_unapproved_feedback_fails(client: TestClient):
    """Ingestion must be rejected if the feedback iteration is not approved."""
    run, _, it = _setup_failed_run_with_approved_feedback(is_approved=False)

    payload = {
        "corrected_code": "def calculate_total(subtotal, tax_rate):\n    return subtotal\n",
        "feedback_iteration_id": it.iteration_id,
    }

    res = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=payload)
    assert res.status_code == 400
    assert "approved" in res.json()["error"]["message"].lower()


def test_repair_ingestion_mismatched_feedback_iteration(client: TestClient):
    """Ingestion must reject a feedback iteration that belongs to a different run."""
    run, _, _ = _setup_failed_run_with_approved_feedback()

    payload = {
        "corrected_code": "def calculate_total(subtotal, tax_rate):\n    return subtotal\n",
        "feedback_iteration_id": "iter-other-run-12345",
    }

    res = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=payload)
    assert res.status_code == 404


def test_repair_ingestion_ineligible_run_passed_status(client: TestClient):
    """Ingestion must reject a verification run that is already PASSED with no defects."""
    now = datetime.now(timezone.utc)
    sub = CodeSubmissionResponse(
        id="sub-passed-01",
        code="def ok(): pass\n",
        language=ProgrammingLanguage.PYTHON,
        created_at=now,
    )
    asyncio.run(_in_memory_submission_repo.save(sub))

    run = VerificationRunResponse(
        id="run-passed-01",
        submission_id=sub.id,
        status=VerificationStatus.PASSED,
        triggered_by="manual",
        test_results=[
            TestResult(
                test_id="t1",
                name="test_ok",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
            )
        ],
        defect_reports=[],
        feedback_iterations=[],
        created_at=now,
        updated_at=now,
    )
    asyncio.run(_in_memory_verification_repo.save(run))

    payload = {"corrected_code": "def ok(): pass\n"}
    res = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=payload)
    assert res.status_code == 400
    assert "not eligible" in res.json()["error"]["message"].lower()


@pytest.mark.parametrize(
    "bad_filename",
    [
        "../solution.py",
        "../../etc/passwd.py",
        "/absolute/solution.py",
        "subdir/solution.py",
        "solution.js",
        "solution.txt",
        "solution.sh",
        "solution.exe",
    ],
)
def test_repair_ingestion_filename_security_rejections(client: TestClient, bad_filename: str):
    """Path traversal and unauthorized file extensions must be rejected."""
    run, _, it = _setup_failed_run_with_approved_feedback()

    payload = {
        "corrected_code": "def calculate_total(s, t):\n    return s\n",
        "filename": bad_filename,
        "feedback_iteration_id": it.iteration_id,
    }

    res = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=payload)
    assert res.status_code in [400, 422]


def test_repair_ingestion_empty_code_rejected(client: TestClient):
    """Empty or whitespace-only code must be rejected."""
    run, _, it = _setup_failed_run_with_approved_feedback()

    res = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={"corrected_code": "   \n\t  ", "feedback_iteration_id": it.iteration_id},
    )
    assert res.status_code in [400, 422]


def test_repair_ingestion_syntax_error_rejected(client: TestClient):
    """Code with Python syntax errors must be caught by static AST validation and rejected."""
    run, _, it = _setup_failed_run_with_approved_feedback()

    malformed_code = "def calculate_total(subtotal, tax_rate:\n    broken syntax\n"

    res = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={"corrected_code": malformed_code, "feedback_iteration_id": it.iteration_id},
    )
    assert res.status_code == 400
    assert "syntax" in res.json()["error"]["message"].lower()


def test_repair_ingestion_idempotency(client: TestClient):
    """Repeated submission of identical corrected code for the same iteration returns the existing attempt."""
    run, _, it = _setup_failed_run_with_approved_feedback()

    payload = {
        "corrected_code": "def calculate_total(s, t):\n    return s * (1 + t)\n",
        "feedback_iteration_id": it.iteration_id,
    }

    res1 = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=payload)
    assert res1.status_code == 201
    rep1_id = res1.json()["repair_id"]

    res2 = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=payload)
    assert res2.status_code == 201
    rep2_id = res2.json()["repair_id"]

    assert rep1_id == rep2_id


# ---------------------------------------------------------------------------
# Re-Verification & Defect Resolution Tests
# ---------------------------------------------------------------------------


def test_reverification_execution_fully_resolved(client: TestClient):
    """
    Re-verification where all previously failing tests pass:
    Verdict must be FULLY_RESOLVED, resolution rate 100%.
    """
    run, sub, it = _setup_failed_run_with_approved_feedback()

    ingest_res = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(subtotal, tax_rate):\n    return subtotal + (subtotal * tax_rate)\n",
            "feedback_iteration_id": it.iteration_id,
        },
    )
    assert ingest_res.status_code == 201
    repair_id = ingest_res.json()["repair_id"]

    # Mock the verification_pipeline.ainvoke to return passing tests
    mock_pipeline_output = {
        "status": VerificationStatus.PASSED.value,
        "test_results": [
            TestResult(
                test_id="t1",
                name="test_total_with_tax",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
            ),
            TestResult(
                test_id="t2",
                name="test_total_without_tax",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
            ),
        ],
        "defect_reports": [],
        "feedback_iterations": [],
        "telemetry": {},
        "error_message": None,
    }

    with patch("app.services.verification_service.verification_pipeline.ainvoke", new=AsyncMock(return_value=mock_pipeline_output)):
        res = client.post(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify")
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "REVERIFIED"
        assert data["corrected_run_id"] is not None
        comparison = data["comparison"]
        assert comparison is not None
        assert comparison["verdict"] == "FULLY_RESOLVED"
        assert comparison["original_defects_count"] == 2
        assert comparison["resolved_defects_count"] == 2
        assert comparison["remaining_defects_count"] == 0
        assert comparison["new_defects_count"] == 0
        assert comparison["resolution_rate"] == 100.0

        # Detailed test comparisons
        test_comps = comparison["test_comparisons"]
        assert len(test_comps) == 2
        for tc in test_comps:
            assert tc["resolution_status"] == "RESOLVED"
            assert tc["original_status"] == "FAILED"
            assert tc["corrected_status"] == "PASSED"


def test_reverification_execution_partially_resolved(client: TestClient):
    """
    Re-verification where 1 test passes and 1 test still fails:
    Verdict must be PARTIALLY_RESOLVED.
    """
    run, _, it = _setup_failed_run_with_approved_feedback()

    ingest_res = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(subtotal, tax_rate):\n    return subtotal + (subtotal * tax_rate)\n",
            "feedback_iteration_id": it.iteration_id,
        },
    )
    repair_id = ingest_res.json()["repair_id"]

    mock_pipeline_output = {
        "status": VerificationStatus.FAILED.value,
        "test_results": [
            TestResult(
                test_id="t1",
                name="test_total_with_tax",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
            ),
            TestResult(
                test_id="t2",
                name="test_total_without_tax",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                error_message="assert 0 == 50",
            ),
        ],
        "defect_reports": [
            DefectReport(
                defect_id="def-rem-01",
                title="test_total_without_tax failure",
                failed_test="test_total_without_tax",
                description="Still failing",
            )
        ],
        "feedback_iterations": [],
        "telemetry": {},
        "error_message": None,
    }

    with patch("app.services.verification_service.verification_pipeline.ainvoke", new=AsyncMock(return_value=mock_pipeline_output)):
        res = client.post(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify")
        assert res.status_code == 200
        data = res.json()
        comp = data["comparison"]
        assert comp["verdict"] == "PARTIALLY_RESOLVED"
        assert comp["resolved_defects_count"] == 1
        assert comp["remaining_defects_count"] == 1
        assert comp["new_defects_count"] == 0
        assert comp["resolution_rate"] == 50.0


def test_reverification_execution_unresolved(client: TestClient):
    """
    Re-verification where all tests continue to fail:
    Verdict must be UNRESOLVED.
    """
    run, _, it = _setup_failed_run_with_approved_feedback()

    ingest_res = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(subtotal, tax_rate):\n    return 0\n",
            "feedback_iteration_id": it.iteration_id,
        },
    )
    repair_id = ingest_res.json()["repair_id"]

    mock_pipeline_output = {
        "status": VerificationStatus.FAILED.value,
        "test_results": [
            TestResult(
                test_id="t1",
                name="test_total_with_tax",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                error_message="assert 0 == 110",
            ),
            TestResult(
                test_id="t2",
                name="test_total_without_tax",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                error_message="assert 0 == 50",
            ),
        ],
        "defect_reports": [],
        "feedback_iterations": [],
        "telemetry": {},
        "error_message": None,
    }

    with patch("app.services.verification_service.verification_pipeline.ainvoke", new=AsyncMock(return_value=mock_pipeline_output)):
        res = client.post(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify")
        assert res.status_code == 200
        comp = res.json()["comparison"]
        assert comp["verdict"] == "UNRESOLVED"
        assert comp["resolved_defects_count"] == 0
        assert comp["remaining_defects_count"] == 2
        assert comp["resolution_rate"] == 0.0


def test_reverification_execution_regression(client: TestClient):
    """
    Re-verification introducing a new test failure:
    Verdict must be REGRESSION_INTRODUCED.
    """
    # Setup original run with 1 passing test and 1 failing test
    now = datetime.now(timezone.utc)
    sub = CodeSubmissionResponse(
        id="sub-reg-01",
        code="def f(): pass\n",
        language=ProgrammingLanguage.PYTHON,
        test_code="def test_a(): pass\ndef test_b(): pass\n",
        created_at=now,
    )
    asyncio.run(_in_memory_submission_repo.save(sub))

    iteration = FeedbackIteration(
        iteration_id="iter-reg-01",
        iteration_number=1,
        verification_run_id="run-reg-01",
        submission_id=sub.id,
        defects_count=1,
        approval_status="APPROVED",
        created_at=now,
    )

    orig_run = VerificationRunResponse(
        id="run-reg-01",
        submission_id=sub.id,
        status=VerificationStatus.FAILED,
        triggered_by="manual",
        test_results=[
            TestResult(
                test_id="t1",
                name="test_a",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
            ),
            TestResult(
                test_id="t2",
                name="test_b",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                error_message="failed b",
            ),
        ],
        defect_reports=[
            DefectReport(
                defect_id="def-b",
                title="test_b failed",
                failed_test="test_b",
                description="Failed b",
            )
        ],
        feedback_iterations=[iteration],
        execution_telemetry={"trusted_test_cases": sub.test_code},
        created_at=now,
        updated_at=now,
    )
    asyncio.run(_in_memory_verification_repo.save(orig_run))

    ingest_res = client.post(
        f"/api/v1/verifications/{orig_run.id}/repair-responses",
        json={"corrected_code": "def f(): pass\n", "feedback_iteration_id": iteration.iteration_id},
    )
    repair_id = ingest_res.json()["repair_id"]

    # In corrected run, test_b now passes, but test_a (which previously passed) now fails!
    mock_pipeline_output = {
        "status": VerificationStatus.FAILED.value,
        "test_results": [
            TestResult(
                test_id="t1",
                name="test_a",
                test_type=TestType.UNIT,
                status=TestResultStatus.FAILED,
                error_message="regression in a",
            ),
            TestResult(
                test_id="t2",
                name="test_b",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
            ),
        ],
        "defect_reports": [],
        "feedback_iterations": [],
        "telemetry": {},
        "error_message": None,
    }

    with patch("app.services.verification_service.verification_pipeline.ainvoke", new=AsyncMock(return_value=mock_pipeline_output)):
        res = client.post(f"/api/v1/verifications/{orig_run.id}/repair-responses/{repair_id}/re-verify")
        assert res.status_code == 200
        comp = res.json()["comparison"]
        assert comp["verdict"] == "REGRESSION_INTRODUCED"
        assert comp["new_defects_count"] == 1


def test_reverification_inconclusive_missing_tests(client: TestClient):
    """If the corrected run omits original test cases, resolution must be flagged INCONCLUSIVE."""
    service = DefectResolutionService()
    now = datetime.now(timezone.utc)

    orig_run = VerificationRunResponse(
        id="run-orig",
        submission_id="sub-1",
        status=VerificationStatus.FAILED,
        test_results=[
            TestResult(test_id="t1", name="test_one", test_type=TestType.UNIT, status=TestResultStatus.FAILED),
            TestResult(test_id="t2", name="test_two", test_type=TestType.UNIT, status=TestResultStatus.PASSED),
        ],
        created_at=now,
        updated_at=now,
    )

    corr_run = VerificationRunResponse(
        id="run-corr",
        submission_id="sub-2",
        status=VerificationStatus.PASSED,
        test_results=[
            # Missing test_two!
            TestResult(test_id="t1", name="test_one", test_type=TestType.UNIT, status=TestResultStatus.PASSED),
        ],
        created_at=now,
        updated_at=now,
    )

    comparison = service.compare_runs(orig_run, corr_run)
    assert comparison.verdict == OverallResolutionVerdict.INCONCLUSIVE
    assert "Missing" in (comparison.notes or "")


def test_reverification_duplicate_prevention(client: TestClient):
    """Calling re-verify on an already re-verified repair returns existing outcome unless forced."""
    run, _, it = _setup_failed_run_with_approved_feedback()

    ingest_res = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={"corrected_code": "def f(): pass\n", "feedback_iteration_id": it.iteration_id},
    )
    repair_id = ingest_res.json()["repair_id"]

    mock_pipeline_output = {
        "status": VerificationStatus.PASSED.value,
        "test_results": [
            TestResult(test_id="t1", name="test_total_with_tax", test_type=TestType.UNIT, status=TestResultStatus.PASSED),
            TestResult(test_id="t2", name="test_total_without_tax", test_type=TestType.UNIT, status=TestResultStatus.PASSED),
        ],
        "defect_reports": [],
        "feedback_iterations": [],
        "telemetry": {},
        "error_message": None,
    }

    invoke_count = 0

    async def _mock_invoke(state):
        nonlocal invoke_count
        invoke_count += 1
        return mock_pipeline_output

    with patch("app.services.verification_service.verification_pipeline.ainvoke", side_effect=_mock_invoke):
        # 1st call executes re-verification
        res1 = client.post(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify")
        assert res1.status_code == 200
        assert invoke_count == 1

        # 2nd call without force_reverify does NOT re-invoke the pipeline
        res2 = client.post(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify")
        assert res2.status_code == 200
        assert invoke_count == 1


def test_list_and_get_repair_attempts(client: TestClient):
    """Verify listing and retrieving individual repair attempts."""
    run, _, it = _setup_failed_run_with_approved_feedback()

    # Ingest two different repairs
    res1 = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={"corrected_code": "code_v1 = 1\n", "feedback_iteration_id": it.iteration_id},
    )
    res2 = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={"corrected_code": "code_v2 = 2\n", "feedback_iteration_id": it.iteration_id},
    )
    rep1_id = res1.json()["repair_id"]
    rep2_id = res2.json()["repair_id"]

    # List
    list_res = client.get(f"/api/v1/verifications/{run.id}/repair-responses")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] == 2
    ids = [i["repair_id"] for i in list_data["items"]]
    assert rep1_id in ids
    assert rep2_id in ids

    # Get single
    get_res = client.get(f"/api/v1/verifications/{run.id}/repair-responses/{rep1_id}")
    assert get_res.status_code == 200
    assert get_res.json()["repair_id"] == rep1_id


def test_get_repair_comparison_endpoints(client: TestClient):
    """Comparison endpoint returns 400 before re-verification, and comparison object after."""
    run, _, it = _setup_failed_run_with_approved_feedback()

    res = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={"corrected_code": "def f(): pass\n", "feedback_iteration_id": it.iteration_id},
    )
    repair_id = res.json()["repair_id"]

    # Before re-verify: 400
    comp_pre = client.get(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/comparison")
    assert comp_pre.status_code == 400

    # Execute re-verify
    mock_pipeline_output = {
        "status": VerificationStatus.PASSED.value,
        "test_results": [
            TestResult(test_id="t1", name="test_total_with_tax", test_type=TestType.UNIT, status=TestResultStatus.PASSED),
            TestResult(test_id="t2", name="test_total_without_tax", test_type=TestType.UNIT, status=TestResultStatus.PASSED),
        ],
        "defect_reports": [],
        "feedback_iterations": [],
        "telemetry": {},
        "error_message": None,
    }
    with patch("app.services.verification_service.verification_pipeline.ainvoke", new=AsyncMock(return_value=mock_pipeline_output)):
        client.post(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify")

    # After re-verify: 200 OK with full comparison
    comp_post = client.get(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/comparison")
    assert comp_post.status_code == 200
    comp_data = comp_post.json()
    assert comp_data["verdict"] == "FULLY_RESOLVED"
    assert comp_data["resolution_rate"] == 100.0


def test_mongo_repair_repository_operations():
    """Verify MongoRepairRepository serialization and operations using a mock database."""
    mock_collection = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection

    repo = MongoRepairRepository(mock_db)
    mock_db.__getitem__.assert_called_with("repair_attempts")

    now = datetime.now(timezone.utc)
    attempt = RepairAttempt(
        id="rep-test-01",
        original_run_id="run-01",
        original_submission_id="sub-01",
        feedback_iteration_id="iter-01",
        corrected_submission_id="sub-02",
        status=RepairResponseStatus.INGESTED,
        created_at=now,
        updated_at=now,
    )

    # Test save for new document
    mock_collection.find_one.return_value = None
    asyncio.run(repo.save(attempt))
    mock_collection.replace_one.assert_called()
    args, kwargs = mock_collection.replace_one.call_args
    assert args[0] == {"_id": "rep-test-01"}
    assert kwargs.get("upsert") is True


def test_repair_identifier_stability_and_unification(client):
    """Confirm ingestion returns a stable canonical identifier where repair_id == id."""
    run, sub, it = _setup_failed_run_with_approved_feedback()

    # 1. Ingestion
    ingest_resp = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(s, t):\n    return s * (1 + t)\n",
            "filename": "calc.py",
        },
    )
    assert ingest_resp.status_code == 201
    ingest_data = ingest_resp.json()
    canonical_id = ingest_data["repair_id"]
    assert canonical_id.startswith("rep-")
    assert ingest_data["id"] == canonical_id

    # 2. Detail retrieval using the canonical identifier
    detail_resp = client.get(f"/api/v1/verifications/{run.id}/repair-responses/{canonical_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["repair_id"] == canonical_id
    assert detail_data["id"] == canonical_id

    # 3. Listing retrieval
    list_resp = client.get(f"/api/v1/verifications/{run.id}/repair-responses")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    item = next(i for i in list_data["items"] if i["repair_id"] == canonical_id)
    assert item["repair_id"] == canonical_id
    assert item["id"] == canonical_id

    # 4. Duplicate ingestion preserves the exact same canonical identifier
    dup_resp = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(s, t):\n    return s * (1 + t)\n",
            "filename": "calc.py",
        },
    )
    assert dup_resp.status_code == 201
    assert dup_resp.json()["repair_id"] == canonical_id
    assert dup_resp.json()["id"] == canonical_id


def test_mongo_repair_repository_legacy_conflicting_id_compatibility():
    """Verify that MongoRepairRepository can retrieve legacy records with conflicting repair_id and id."""
    mock_collection = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    repo = MongoRepairRepository(mock_db)

    # Simulate existing document in Atlas (conflicting repair_id vs _id/id)
    legacy_doc = {
        "_id": "rep-29ccd13f2c12",
        "id": "rep-29ccd13f2c12",
        "repair_id": "rep-5f900fb0183d",
        "original_run_id": "run-475a39076d8e",
        "original_submission_id": "sub-01057496e861",
        "feedback_iteration_id": "iter-efbb1924c93f",
        "corrected_submission_id": "sub-e19bc2a39cd8",
        "status": "INGESTED",
        "corrected_code": "def calculate_total(s, t): return s * (1 + t)\n",
        "corrected_filename": "solution.py",
        "filename": "solution.py",
        "repair_source": "LOCAL_MANUAL",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    mock_collection.find_one.return_value = dict(legacy_doc)

    # 1. Retrieve by advertised repair_id ('rep-5f900fb0183d')
    res = asyncio.run(repo.get_by_id("rep-5f900fb0183d"))
    assert res is not None
    assert res.repair_id == "rep-5f900fb0183d"
    assert res.id == "rep-5f900fb0183d"
    mock_collection.find_one.assert_called_with(
        {"$or": [{"repair_id": "rep-5f900fb0183d"}, {"id": "rep-5f900fb0183d"}, {"_id": "rep-5f900fb0183d"}]}
    )

    # 2. Retrieve by legacy internal id ('rep-29ccd13f2c12')
    mock_collection.find_one.return_value = dict(legacy_doc)
    res2 = asyncio.run(repo.get_by_id("rep-29ccd13f2c12"))
    assert res2 is not None
    assert res2.repair_id == "rep-5f900fb0183d"
    assert res2.id == "rep-5f900fb0183d"

    # 3. Test saving an update to the legacy record preserves the MongoDB _id
    mock_collection.find_one.return_value = dict(legacy_doc)
    res.status = RepairResponseStatus.REVERIFIED
    asyncio.run(repo.save(res))
    replace_args, replace_kwargs = mock_collection.replace_one.call_args
    # Must replace against the existing MongoDB _id
    assert replace_args[0] == {"_id": "rep-29ccd13f2c12"}
    assert replace_args[1]["_id"] == "rep-29ccd13f2c12"
    assert replace_args[1]["repair_id"] == "rep-5f900fb0183d"
    assert replace_args[1]["id"] == "rep-5f900fb0183d"
    assert replace_kwargs.get("upsert") is False


def test_schema_model_validation_restart_simulation():
    """Verify that re-validating a document simulated across server restarts preserves the identifier."""
    doc = {
        "repair_id": "rep-5f900fb0183d",
        "id": "rep-29ccd13f2c12",
        "original_run_id": "run-475a39076d8e",
        "original_submission_id": "sub-01",
        "feedback_iteration_id": "iter-01",
        "corrected_submission_id": "sub-02",
        "status": "INGESTED",
    }

    # First validation
    att1 = RepairAttempt.model_validate(doc)
    assert att1.repair_id == "rep-5f900fb0183d"
    assert att1.id == "rep-5f900fb0183d"

    # Re-serialization (e.g. into API response)
    resp = RepairAttemptResponse.model_validate(att1)
    assert resp.repair_id == "rep-5f900fb0183d"
    assert resp.id == "rep-5f900fb0183d"

    # Simulated server restart / reloading from DB
    serialized = att1.model_dump()
    att2 = RepairAttempt.model_validate(serialized)
    assert att2.repair_id == "rep-5f900fb0183d"
    assert att2.id == "rep-5f900fb0183d"


def test_invalid_repair_id_returns_404(client):
    """Verify that an invalid or nonexistent repair ID returns HTTP 404."""
    run, _, _ = _setup_failed_run_with_approved_feedback()
    resp = client.get(f"/api/v1/verifications/{run.id}/repair-responses/rep-nonexistent-999")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "rep-nonexistent-999" in data["error"]["message"]


# =========================================================================
# Task 5 Automated Regression Tests: Trusted Test Suite Persistence & Re-verification
# =========================================================================

def test_1_test_suite_persistence_during_original_verification(client):
    """Verify that when a verification run executes with trusted test cases, a TrustedTestSuite is durably persisted."""
    now = datetime.now(timezone.utc)
    sub = CodeSubmissionResponse(
        id="sub-test-suite-01",
        code="def add(a, b): return a + b\n",
        language=ProgrammingLanguage.PYTHON,
        filename="math_ops.py",
        created_at=now,
    )
    asyncio.run(_in_memory_submission_repo.save(sub))

    test_source = "def test_add():\n    assert add(1, 2) == 3\n"
    create_payload = {
        "submission_id": sub.id,
        "triggered_by": "test_persistence",
        "test_types": ["unit"],
        "trusted_test_cases": test_source,
    }

    # Execute verification run immediately
    with patch("app.services.verification_service.verification_pipeline.ainvoke") as mock_pipeline:
        mock_pipeline.return_value = {
            "status": "PASSED",
            "test_results": [
                {
                    "test_id": "test_add",
                    "name": "test_add",
                    "status": "PASSED",
                    "test_type": "unit",
                    "duration_ms": 12.0,
                }
            ],
            "defect_reports": [],
            "feedback_iterations": [],
            "telemetry": {},
        }
        resp = client.post("/api/v1/verifications?execute_now=true", json=create_payload)
        assert resp.status_code == 201
        run_data = resp.json()
        assert run_data["test_suite_id"] is not None

        suite = asyncio.run(_in_memory_test_suite_repo.get_by_id(run_data["test_suite_id"]))
        assert suite is not None
        assert suite.verification_run_id == run_data["id"]
        assert suite.test_code == test_source
        assert suite.content_hash == TrustedTestSuite.compute_hash(test_source)
        assert suite.provenance == TestSuiteProvenance.RUN_EXPLICIT


def test_2_test_suite_retrieval_after_backend_restart():
    """Verify that trusted test suites survive backend restarts with exact content and hash fidelity."""
    original_code = "def test_multiply():\n    assert multiply(3, 4) == 12\n"
    suite = TrustedTestSuite(
        suite_id="suite-restart-test-01",
        verification_run_id="run-restart-01",
        submission_id="sub-restart-01",
        test_code=original_code,
        content_hash=TrustedTestSuite.compute_hash(original_code),
        provenance=TestSuiteProvenance.RUN_EXPLICIT,
        test_types=["unit"],
        notes="Pre-restart test specification",
    )

    # Persist in storage
    asyncio.run(_in_memory_test_suite_repo.save(suite))

    # Simulate backend restart: serialize and rehydrate through a brand new repository
    serialized_state = suite.model_dump(mode="json")
    rehydrated_suite = TrustedTestSuite.model_validate(serialized_state)

    new_repo = type(_in_memory_test_suite_repo)()
    asyncio.run(new_repo.save(rehydrated_suite))

    retrieved = asyncio.run(new_repo.get_by_id("suite-restart-test-01"))
    assert retrieved is not None
    assert retrieved.suite_id == suite.suite_id
    assert retrieved.test_code == original_code
    assert retrieved.content_hash == suite.content_hash
    assert retrieved.provenance == TestSuiteProvenance.RUN_EXPLICIT
    assert retrieved.notes == "Pre-restart test specification"

    retrieved_by_run = asyncio.run(new_repo.get_by_run_id("run-restart-01"))
    assert retrieved_by_run is not None
    assert retrieved_by_run.suite_id == suite.suite_id


def test_3_mongodb_suite_persistence_and_roundtrip_integrity():
    """Verify that MongoTestSuiteRepository handles storage, querying, and indexing correctly without PyMongo leaks."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_db.__getitem__.return_value = mock_collection

    repo = MongoTestSuiteRepository(mock_db)

    # 1. Verify indexes created
    index_calls = [c[0][0] for c in mock_collection.create_index.call_args_list]
    assert "suite_id" in index_calls
    assert "verification_run_id" in index_calls
    assert "created_at" in index_calls

    # 2. Test save
    suite = TrustedTestSuite(
        suite_id="suite-mongo-01",
        verification_run_id="run-mongo-01",
        test_code="def test_x(): assert x() == 1\n",
        content_hash=TrustedTestSuite.compute_hash("def test_x(): assert x() == 1\n"),
        provenance=TestSuiteProvenance.RECOVERED_AUTHORIZED,
    )
    saved = asyncio.run(repo.save(suite))
    assert saved.suite_id == "suite-mongo-01"
    mock_collection.replace_one.assert_called_once()
    args, kwargs = mock_collection.replace_one.call_args
    assert args[0] == {"_id": "suite-mongo-01"}
    assert args[1]["_id"] == "suite-mongo-01"
    assert kwargs.get("upsert") is True

    # 3. Test get_by_id
    mock_collection.find_one.return_value = {
        "_id": "suite-mongo-01",
        "suite_id": "suite-mongo-01",
        "verification_run_id": "run-mongo-01",
        "test_code": "def test_x(): assert x() == 1\n",
        "content_hash": suite.content_hash,
        "provenance": "RECOVERED_AUTHORIZED",
        "test_types": ["unit"],
        "execution_config": {},
        "created_at": "2026-10-15T12:00:00Z",
    }
    found = asyncio.run(repo.get_by_id("suite-mongo-01"))
    assert found is not None
    assert found.suite_id == "suite-mongo-01"
    assert found.provenance == TestSuiteProvenance.RECOVERED_AUTHORIZED

    # 4. Test get_by_run_id
    by_run = asyncio.run(repo.get_by_run_id("run-mongo-01"))
    assert by_run is not None
    assert by_run.verification_run_id == "run-mongo-01"


def test_4_exact_suite_reuse_during_reverification(client):
    """Verify that RepairService retrieves the exact authorized suite from persistence and executes it in re-verification."""
    run, sub, iter_obj = _setup_failed_run_with_approved_feedback()

    # Durably persist the original authorized test suite
    test_code = (
        "def test_total_with_tax():\n"
        "    assert calculate_total(100.0, 0.08) == 108.0\n"
        "def test_total_without_tax():\n"
        "    assert calculate_total(100.0, 0.0) == 100.0\n"
    )
    suite = TrustedTestSuite(
        suite_id="suite-exact-reuse-01",
        verification_run_id=run.id,
        submission_id=sub.id,
        test_code=test_code,
        content_hash=TrustedTestSuite.compute_hash(test_code),
        provenance=TestSuiteProvenance.RUN_EXPLICIT,
    )
    asyncio.run(_in_memory_test_suite_repo.save(suite))
    run.test_suite_id = suite.suite_id
    asyncio.run(_in_memory_verification_repo.save(run))

    # Ingest repair
    ingest_payload = {
        "corrected_code": (
            "def calculate_total(price, tax_rate):\n"
            "    return price + (price * tax_rate)\n"
        ),
        "feedback_iteration_id": iter_obj.iteration_id,
        "notes": "Fixed price calculation formula",
    }
    resp = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=ingest_payload)
    assert resp.status_code == 201
    repair_id = resp.json()["repair_id"]

    # Re-verify and inspect pipeline arguments
    with patch("app.services.verification_service.verification_pipeline.ainvoke") as mock_pipeline:
        mock_pipeline.return_value = {
            "status": "PASSED",
            "test_results": [
                {"test_id": "test_total_with_tax", "name": "test_total_with_tax", "status": "PASSED", "test_type": "unit", "duration_ms": 10.0},
                {"test_id": "test_total_without_tax", "name": "test_total_without_tax", "status": "PASSED", "test_type": "unit", "duration_ms": 10.0},
            ],
            "defect_reports": [],
            "feedback_iterations": [],
            "telemetry": {},
        }
        reverify_resp = client.post(
            f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify"
        )
        assert reverify_resp.status_code == 200
        call_state = mock_pipeline.call_args[0][0]
        # Exact suite code was supplied to the Docker verification workflow
        assert call_state["trusted_test_cases"] == test_code


def test_5_missing_suite_handling_produces_inconclusive(client):
    """Verify that missing or unavailable test specifications produce an explicit INCONCLUSIVE resolution outcome."""
    run, sub, iter_obj = _setup_failed_run_with_approved_feedback()
    # Ensure neither submission nor run nor repo has a test suite
    sub.test_code = None
    asyncio.run(_in_memory_submission_repo.save(sub))
    run.test_suite_id = None
    run.execution_telemetry = {}
    asyncio.run(_in_memory_verification_repo.save(run))
    asyncio.run(_in_memory_test_suite_repo.clear())

    ingest_payload = {
        "corrected_code": "def calculate_total(p, r): return p + (p * r)\n",
        "feedback_iteration_id": iter_obj.iteration_id,
    }
    ingest_resp = client.post(f"/api/v1/verifications/{run.id}/repair-responses", json=ingest_payload)
    assert ingest_resp.status_code == 201
    repair_id = ingest_resp.json()["repair_id"]

    # Trigger re-verification when no test suite is available
    reverify_resp = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify"
    )
    assert reverify_resp.status_code == 200
    data = reverify_resp.json()
    assert data["status"] == "BLOCKED"
    assert data["corrected_run_id"] is None
    assert data["comparison"] is not None
    assert data["comparison"]["verdict"] == "INCONCLUSIVE"
    assert data["comparison"]["corrected_status"] == "BLOCKED"
    assert data["comparison"]["corrected_run_id"] is None
    assert data["comparison"]["remaining_defects_count"] == 0
    assert "unavailable" in data["comparison"]["notes"].lower()
    for d in data["comparison"]["defect_comparisons"]:
        assert d["resolution_status"] == "INCONCLUSIVE"


def test_6_historical_record_recovery_with_authoritative_artifact(client):
    """Verify safe recovery workflow for legacy runs using an explicitly authorized test artifact."""
    run, sub, iter_obj = _setup_failed_run_with_approved_feedback(
        run_id="run-475a39076d8e",
        submission_id="sub-01057496e861",
        iteration_id="iter-efbb1924c93f",
    )
    # Remove test suite to simulate historical legacy record
    sub.test_code = None
    asyncio.run(_in_memory_submission_repo.save(sub))
    run.test_suite_id = None
    asyncio.run(_in_memory_verification_repo.save(run))

    authorized_tests = (
        "def test_total_with_tax():\n"
        "    assert calculate_total(100.0, 0.08) == 108.0\n"
        "def test_total_without_tax():\n"
        "    assert calculate_total(100.0, 0.0) == 100.0\n"
    )

    attach_payload = {
        "test_code": authorized_tests,
        "provenance": "RECOVERED_AUTHORIZED",
        "notes": "Independently verified pytest artifact for milestone 3 repair",
    }
    resp = client.post(f"/api/v1/verifications/{run.id}/trusted-test-suite", json=attach_payload)
    assert resp.status_code == 201
    suite_info = resp.json()
    assert suite_info["verification_run_id"] == run.id
    assert suite_info["provenance"] == "RECOVERED_AUTHORIZED"
    assert suite_info["content_hash"] == TrustedTestSuite.compute_hash(authorized_tests)

    # Public metadata GET endpoint does not expose raw executable test source
    meta_resp = client.get(f"/api/v1/verifications/{run.id}/trusted-test-suite")
    assert meta_resp.status_code == 200
    meta_data = meta_resp.json()
    assert meta_data["suite_id"] == suite_info["suite_id"]
    assert "test_code" not in meta_data

    # Verify original run defects and iterations remain unchanged
    updated_run = asyncio.run(_in_memory_verification_repo.get_by_id(run.id))
    assert updated_run.test_suite_id == suite_info["suite_id"]
    assert len(updated_run.defect_reports) == 2
    assert len(updated_run.feedback_iterations) == 1
    assert updated_run.status == VerificationStatus.FAILED


def test_7_rejection_of_fabricated_or_unverified_historical_suites(client):
    """Verify that unverified, malformed, or syntax-violating test suites are rejected on the host."""
    run, _, _ = _setup_failed_run_with_approved_feedback()

    # Syntax error
    invalid_syntax_payload = {
        "test_code": "def test_broken(:\n    assert True",
        "provenance": "RECOVERED_AUTHORIZED",
    }
    resp = client.post(f"/api/v1/verifications/{run.id}/trusted-test-suite", json=invalid_syntax_payload)
    assert resp.status_code == 400
    assert "syntax" in resp.json()["error"]["message"].lower()

    # Empty test code
    empty_payload = {
        "test_code": "   ",
        "provenance": "RECOVERED_AUTHORIZED",
    }
    resp2 = client.post(f"/api/v1/verifications/{run.id}/trusted-test-suite", json=empty_payload)
    assert resp2.status_code == 422

    # Nonexistent verification run
    valid_payload = {
        "test_code": "def test_ok(): assert 1 == 1\n",
        "provenance": "RECOVERED_AUTHORIZED",
    }
    resp3 = client.post("/api/v1/verifications/run-nonexistent-000/trusted-test-suite", json=valid_payload)
    assert resp3.status_code == 404


def test_8_corrected_verification_producing_genuine_results(client):
    """Verify that re-verification executes against the recovered suite and computes genuine defect resolutions."""
    run, sub, iter_obj = _setup_failed_run_with_approved_feedback()

    # Attach authorized suite
    authorized_tests = (
        "def test_total_with_tax():\n"
        "    assert calculate_total(100.0, 0.08) == 108.0\n"
        "def test_total_without_tax():\n"
        "    assert calculate_total(100.0, 0.0) == 100.0\n"
    )
    client.post(
        f"/api/v1/verifications/{run.id}/trusted-test-suite",
        json={"test_code": authorized_tests, "provenance": "RECOVERED_AUTHORIZED"},
    )

    # Ingest corrected solution
    ingest_resp = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(price, tax_rate):\n    return price * (1.0 + tax_rate)\n",
            "feedback_iteration_id": iter_obj.iteration_id,
        },
    )
    assert ingest_resp.status_code == 201
    repair_id = ingest_resp.json()["repair_id"]

    # Re-verify with mocked passing pipeline
    with patch("app.services.verification_service.verification_pipeline.ainvoke") as mock_pipeline:
        mock_pipeline.return_value = {
            "status": "PASSED",
            "test_results": [
                {"test_id": "test_total_with_tax", "name": "test_total_with_tax", "status": "PASSED", "test_type": "unit", "duration_ms": 11.0},
                {"test_id": "test_total_without_tax", "name": "test_total_without_tax", "status": "PASSED", "test_type": "unit", "duration_ms": 11.0},
            ],
            "defect_reports": [],
            "feedback_iterations": [],
            "telemetry": {},
        }
        reverify_resp = client.post(
            f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify"
        )
        assert reverify_resp.status_code == 200
        comp = reverify_resp.json()["comparison"]
        assert comp["verdict"] == "FULLY_RESOLVED"
        assert comp["original_defects_count"] == 2
        assert comp["resolved_defects_count"] == 2
        assert comp["remaining_defects_count"] == 0
        assert comp["resolution_rate"] == 100.0


def test_9_original_records_remain_unchanged_after_reverification(client):
    """Verify that original submission and original verification runs remain completely unaltered by re-verification."""
    run, sub, iter_obj = _setup_failed_run_with_approved_feedback()
    orig_code_snapshot = sub.code
    orig_defects_count = len(run.defect_reports)

    # Ingest & re-verify
    ingest_resp = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(price, tax_rate):\n    return price + (price * tax_rate)\n",
            "feedback_iteration_id": iter_obj.iteration_id,
        },
    )
    repair_id = ingest_resp.json()["repair_id"]

    with patch("app.services.verification_service.verification_pipeline.ainvoke") as mock_pipeline:
        mock_pipeline.return_value = {
            "status": "PASSED",
            "test_results": [
                {"test_id": "test_total_with_tax", "name": "test_total_with_tax", "status": "PASSED", "test_type": "unit", "duration_ms": 10.0},
                {"test_id": "test_total_without_tax", "name": "test_total_without_tax", "status": "PASSED", "test_type": "unit", "duration_ms": 10.0},
            ],
            "defect_reports": [],
            "feedback_iterations": [],
            "telemetry": {},
        }
        client.post(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify")

    # Verify original submission is untouched
    fetched_orig_sub = asyncio.run(_in_memory_submission_repo.get_by_id(sub.id))
    assert fetched_orig_sub.code == orig_code_snapshot

    # Verify original run is untouched
    fetched_orig_run = asyncio.run(_in_memory_verification_repo.get_by_id(run.id))
    assert fetched_orig_run.status == VerificationStatus.FAILED
    assert len(fetched_orig_run.defect_reports) == orig_defects_count


def test_10_duplicate_execution_prevention(client):
    """Verify idempotency and concurrency protection preventing duplicate verification executions."""
    run, sub, iter_obj = _setup_failed_run_with_approved_feedback()

    ingest_resp = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(price, tax_rate):\n    return price + (price * tax_rate)\n",
            "feedback_iteration_id": iter_obj.iteration_id,
        },
    )
    repair_id = ingest_resp.json()["repair_id"]

    with patch("app.services.verification_service.verification_pipeline.ainvoke") as mock_pipeline:
        mock_pipeline.return_value = {
            "status": "PASSED",
            "test_results": [
                {"test_id": "test_total_with_tax", "name": "test_total_with_tax", "status": "PASSED", "test_type": "unit", "duration_ms": 10.0},
                {"test_id": "test_total_without_tax", "name": "test_total_without_tax", "status": "PASSED", "test_type": "unit", "duration_ms": 10.0},
            ],
            "defect_reports": [],
            "feedback_iterations": [],
            "telemetry": {},
        }
        # First execution
        resp1 = client.post(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify")
        assert resp1.status_code == 200
        first_corrected_run_id = resp1.json()["corrected_run_id"]
        assert mock_pipeline.call_count == 1

        # Second execution without force_reverify=true: must NOT invoke pipeline again
        resp2 = client.post(f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify")
        assert resp2.status_code == 200
        assert resp2.json()["corrected_run_id"] == first_corrected_run_id
        assert mock_pipeline.call_count == 1  # No duplicate execution


def test_11_no_docker_execution_attempted_when_suite_missing(client):
    """
    Verify that when trusted test cases are absent, no container execution
    is attempted (pipeline.ainvoke is never called), no fake run is created,
    and status is returned as BLOCKED.
    """
    run, sub, iter_obj = _setup_failed_run_with_approved_feedback()
    sub.test_code = None
    asyncio.run(_in_memory_submission_repo.save(sub))
    run.test_suite_id = None
    run.execution_telemetry = {}
    asyncio.run(_in_memory_verification_repo.save(run))
    asyncio.run(_in_memory_test_suite_repo.clear())

    ingest_resp = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(p, r): return p * (1 + r)\n",
            "feedback_iteration_id": iter_obj.iteration_id,
        },
    )
    assert ingest_resp.status_code == 201
    repair_id = ingest_resp.json()["repair_id"]

    with patch("app.services.verification_service.verification_pipeline.ainvoke") as mock_pipeline:
        reverify_resp = client.post(
            f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify"
        )
        assert reverify_resp.status_code == 200
        data = reverify_resp.json()
        # Invariant: Pipeline must NEVER be called when suite is missing
        assert mock_pipeline.call_count == 0
        assert data["status"] == "BLOCKED"
        assert data["corrected_run_id"] is None
        assert data["comparison"]["verdict"] == "INCONCLUSIVE"
        assert data["comparison"]["corrected_status"] == "BLOCKED"
        assert data["comparison"]["remaining_defects_count"] == 0


def test_12_reverified_lifecycle_invariant_enforcement():
    """
    Enforce invariant: A repair attempt cannot be marked REVERIFIED if corrected_run_id is missing.
    New models attempting this must raise a validation error.
    """
    now = datetime.now(timezone.utc)
    # Valid attempt with run ID succeeds
    valid_attempt = RepairAttempt(
        repair_id="rep-valid-01",
        original_run_id="run-orig-01",
        original_submission_id="sub-orig-01",
        feedback_iteration_id="iter-01",
        corrected_submission_id="sub-corr-01",
        corrected_run_id="run-corr-01",
        status=RepairResponseStatus.REVERIFIED,
    )
    assert valid_attempt.status == RepairResponseStatus.REVERIFIED
    assert valid_attempt.corrected_run_id == "run-corr-01"

    # Attempting to mark REVERIFIED without a corrected_run_id must raise ValueError
    with pytest.raises(ValueError, match="cannot enter REVERIFIED status without a genuine corrected_run_id"):
        RepairAttempt(
            repair_id="rep-invalid-01",
            original_run_id="run-orig-01",
            original_submission_id="sub-orig-01",
            feedback_iteration_id="iter-01",
            corrected_submission_id="sub-corr-01",
            corrected_run_id=None,
            status=RepairResponseStatus.REVERIFIED,
        )


def test_13_historical_inconsistent_status_detection_and_reconciliation():
    """
    Verify detection of historical records matching the exact Atlas problem pattern
    (status=REVERIFIED, corrected_run_id=None, verdict=INCONCLUSIVE) and verify idempotent reconciliation.
    """
    now = datetime.now(timezone.utc)
    comparison = DefectResolutionComparison(
        original_run_id="run-475a39076d8e",
        corrected_run_id=None,
        original_status="FAILED",
        corrected_status="INCONCLUSIVE",
        verdict=OverallResolutionVerdict.INCONCLUSIVE,
        original_defects_count=2,
        resolved_defects_count=0,
        remaining_defects_count=2,  # Old incorrect count
        new_defects_count=0,
        resolution_rate=0.0,
        notes="Original trusted test suite is unavailable; cannot safely execute re-verification.",
    )

    # Legacy record loaded from storage
    legacy_attempt = RepairAttempt(
        repair_id="rep-5f900fb0183d",
        original_run_id="run-475a39076d8e",
        original_submission_id="sub-01057496e861",
        feedback_iteration_id="iter-efbb1924c93f",
        corrected_submission_id="sub-e19bc2a39cd8",
        corrected_run_id=None,
        status=RepairResponseStatus.REVERIFIED,
        notes="Original trusted test suite is unavailable; cannot safely execute re-verification.",
        comparison=comparison,
        created_at=now,
    )

    # 1. Detection
    assert is_inconsistent_repair_attempt(legacy_attempt) is True
    api_model = RepairAttemptResponse.model_validate(legacy_attempt.model_dump())
    assert api_model.is_inconsistent is True

    # 2. Persist to in-memory repo and reconcile via RepairService
    asyncio.run(_in_memory_repair_repo.save(legacy_attempt))

    repair_service = RepairService(
        repair_repo=_in_memory_repair_repo,
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
        verification_service=MagicMock(),
        test_suite_repo=_in_memory_test_suite_repo,
    )

    # Detect list of inconsistent repairs
    inconsistent_list = asyncio.run(repair_service.detect_inconsistent_repairs("run-475a39076d8e"))
    assert len(inconsistent_list) == 1
    assert inconsistent_list[0].repair_id == "rep-5f900fb0183d"

    # Reconcile
    reconciled = asyncio.run(repair_service.reconcile_repair_attempt("rep-5f900fb0183d"))
    assert reconciled.status == RepairResponseStatus.BLOCKED
    assert reconciled.corrected_run_id is None
    assert reconciled.comparison.corrected_status == "BLOCKED"
    assert reconciled.comparison.remaining_defects_count == 0
    assert "unavailable" in reconciled.notes.lower()

    # Inconsistent flag is now False
    assert is_inconsistent_repair_attempt(reconciled) is False

    # Second reconciliation is idempotent
    reconciled_again = asyncio.run(repair_service.reconcile_repair_attempt("rep-5f900fb0183d"))
    assert reconciled_again.status == RepairResponseStatus.BLOCKED


def test_14_durable_trusted_suite_persistence_deferred_execution():
    """
    Verify that create_verification_run with execute_now=False durably persists
    the TrustedTestSuite immediately, associating test_suite_id on the pending run.
    """
    now = datetime.now(timezone.utc)
    sub = CodeSubmissionResponse(
        id="sub-persist-01",
        code="def add(a, b): return a + b\n",
        language=ProgrammingLanguage.PYTHON,
        filename="math_lib.py",
        created_at=now,
    )
    asyncio.run(_in_memory_submission_repo.save(sub))

    verif_service = VerificationService(
        submission_repo=_in_memory_submission_repo,
        verification_repo=_in_memory_verification_repo,
        test_suite_repo=_in_memory_test_suite_repo,
    )

    test_cases = "def test_add(): assert add(1, 2) == 3\n"
    payload = VerificationRunCreate(
        submission_id=sub.id,
        triggered_by="unit_test",
        test_types=[TestType.UNIT],
        trusted_test_cases=test_cases,
    )

    pending_run = asyncio.run(verif_service.create_verification_run(payload, execute_now=False))
    assert pending_run.status == VerificationStatus.PENDING
    assert pending_run.test_suite_id is not None

    # Test retrieval from test suite repository
    suite = asyncio.run(_in_memory_test_suite_repo.get_by_id(pending_run.test_suite_id))
    assert suite is not None
    assert suite.test_code == test_cases
    assert suite.provenance == TestSuiteProvenance.RUN_EXPLICIT
    assert suite.content_hash == TrustedTestSuite.compute_hash(test_cases)


def test_15_genuine_docker_reverification_transition_to_reverified(client):
    """
    Verify that a genuine re-verification with an authorized suite completes
    and correctly marks the attempt REVERIFIED with execution evidence.
    """
    run, sub, iter_obj = _setup_failed_run_with_approved_feedback()

    # Attach authorized suite
    # Attach authorized suite matching original run's test names
    suite_code = (
        "def test_total_with_tax(): assert calculate_total(100, 0.1) == 110\n"
        "def test_total_without_tax(): assert calculate_total(50, 0.0) == 50\n"
    )
    client.post(
        f"/api/v1/verifications/{run.id}/trusted-test-suite",
        json={"test_code": suite_code, "provenance": "RECOVERED_AUTHORIZED"},
    )

    # Ingest fix
    ingest_resp = client.post(
        f"/api/v1/verifications/{run.id}/repair-responses",
        json={
            "corrected_code": "def calculate_total(s, t): return s + (s * t)\n",
            "feedback_iteration_id": iter_obj.iteration_id,
        },
    )
    repair_id = ingest_resp.json()["repair_id"]

    mock_pipeline_output = {
        "status": "PASSED",
        "test_results": [
            TestResult(
                test_id="t1",
                name="test_total_with_tax",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
                duration_ms=15.0,
            ),
            TestResult(
                test_id="t2",
                name="test_total_without_tax",
                test_type=TestType.UNIT,
                status=TestResultStatus.PASSED,
                duration_ms=12.0,
            ),
        ],
        "defect_reports": [],
        "feedback_iterations": [],
        "telemetry": {},
        "error_message": None,
    }

    with patch("app.services.verification_service.verification_pipeline.ainvoke", new=AsyncMock(return_value=mock_pipeline_output)):
        reverify_resp = client.post(
            f"/api/v1/verifications/{run.id}/repair-responses/{repair_id}/re-verify"
        )
        assert reverify_resp.status_code == 200
        data = reverify_resp.json()
        assert data["status"] == "REVERIFIED"
        assert data["corrected_run_id"] is not None
        assert data["corrected_run_id"].startswith("run-")
        assert data["comparison"]["verdict"] in ("FULLY_RESOLVED", "PARTIALLY_RESOLVED")


