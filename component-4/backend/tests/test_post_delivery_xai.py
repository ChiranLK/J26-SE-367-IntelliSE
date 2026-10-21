from datetime import datetime, timezone
import hashlib
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.schemas.common import VerificationStatus
from app.schemas.feedback import TechnicalFeedbackPayload
from app.schemas.verification import VerificationRunResponse
from app.services.code_analysis import inspect_python_code_ast, sanitize_code_secrets
from app.services.feedback_service import TechnicalFeedbackService
from app.services.post_delivery_xai_service import PostDeliveryXaiService


@pytest.fixture(autouse=True)
def disable_ollama_for_post_delivery_tests(monkeypatch: pytest.MonkeyPatch):
    """Enforce deterministic provider baseline for post-delivery XAI tests."""
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)


def test_no_user_facing_xai_for_failed_verification(client: TestClient):
    """
    Requirement: No user-facing XAI before successful delivery;
    no XAI for blocked or failed verification.
    Verifies that defective code returns eligible=False, BLOCKED_VERIFICATION_FAILED,
    and post_delivery_explanation=None, while internal defect reports remain available.
    """
    defective_code = """
def calculate_tax(amount):
    return amount * 0.08

def total_with_tax(amount):
    return calculate_tax(amount)  # Defect: omits base amount
"""
    test_code = """
from solution import total_with_tax

def test_total_with_tax():
    assert total_with_tax(100.0) == 108.0
"""
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": defective_code, "language": "python", "filename": "calc.py"},
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications?execute_now=true",
        json={"submission_id": sub_id, "trusted_test_cases": test_code},
    )
    assert run_res.status_code == 201
    run_data = run_res.json()
    assert run_data["status"] == "FAILED"
    run_id = run_data["id"]

    # Attempt to fetch explanation
    expl_res = client.get(f"/api/v1/verifications/{run_id}/explanation")
    assert expl_res.status_code == 200
    expl = expl_res.json()

    assert expl["eligible"] is False
    assert expl["delivery_status"] == "BLOCKED_VERIFICATION_FAILED"
    assert expl["post_delivery_explanation"] is None
    assert "User-facing XAI is withheld during intermediate repair attempts" in expl["eligibility_reason"]
    assert expl["recommendation"]["action"] == "RETURN_TO_COMPONENT_3"

    # Verify dedicated post-delivery endpoint rejects with 400
    pdx_res = client.get(f"/api/v1/verifications/{run_id}/post-delivery-explanation")
    assert pdx_res.status_code == 400
    assert "unavailable" in pdx_res.json()["error"]["message"].lower()

    # Verify internal defect reports are preserved for auditing and C3
    defects_res = client.get(f"/api/v1/verifications/{run_id}/defects")
    assert defects_res.status_code == 200
    assert len(defects_res.json()["items"]) == 1


def test_passing_verification_retains_pending_explanation_state_until_delivery_confirmed(client: TestClient):
    """
    Requirement: Do not treat a passing test result alone as proof of successful delivery.
    If delivery confirmation is unavailable, retain a pending explanation state.
    """
    valid_code = """
def calculate_tax(amount):
    return amount * 0.08

def total_with_tax(amount):
    return amount + calculate_tax(amount)
"""
    test_code = """
from solution import total_with_tax

def test_total_with_tax():
    assert total_with_tax(100.0) == 108.0
"""
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": valid_code, "language": "python", "filename": "calc.py"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications?execute_now=true",
        json={"submission_id": sub_id, "trusted_test_cases": test_code},
    )
    run_id = run_res.json()["id"]
    assert run_res.json()["status"] == "PASSED"

    # Step 1: Query explanation BEFORE delivery confirmation
    expl_res_before = client.get(f"/api/v1/verifications/{run_id}/explanation")
    assert expl_res_before.status_code == 200
    expl_before = expl_res_before.json()

    assert expl_before["eligible"] is False
    assert expl_before["delivery_status"] == "PENDING_DELIVERY_CONFIRMATION"
    assert expl_before["post_delivery_explanation"] is None
    assert "pending state until delivery confirmation" in expl_before["eligibility_reason"].lower()
    assert expl_before["recommendation"]["action"] == "AWAIT_DELIVERY_CONFIRMATION"

    # Step 2: Confirm delivery (production delivery with authenticated token)
    deliv_res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={
            "artifact_version": sub_id,
            "delivery_channel": "user_workspace",
            "is_simulation": False,
            "notes": "Production deployment for test harness",
        },
    )
    assert deliv_res.status_code == 201
    deliv_data = deliv_res.json()
    assert deliv_data["is_delivered"] is True
    assert deliv_data["is_simulation"] is False
    assert deliv_data["submission_id"] == sub_id
    assert deliv_data["confirmed_by"] == "authenticated_delivery_service"
    assert deliv_data["artifact_checksum_sha256"] is not None

    # Step 3: Query explanation AFTER delivery confirmation
    expl_res_after = client.get(f"/api/v1/verifications/{run_id}/explanation")
    assert expl_res_after.status_code == 200
    expl_after = expl_res_after.json()

    assert expl_after["eligible"] is True
    assert expl_after["delivery_status"] == "CONFIRMED_PRODUCTION_DELIVERY"
    assert expl_after["post_delivery_explanation"] is not None
    assert expl_after["recommendation"]["action"] == "DELIVERED_AND_READY"

    # Verify dedicated post-delivery endpoint now succeeds
    pdx_res = client.get(f"/api/v1/verifications/{run_id}/post-delivery-explanation")
    assert pdx_res.status_code == 200
    pdx = pdx_res.json()
    assert pdx["submission_id"] == sub_id
    assert pdx["verified_test_count"] == 1


def test_delivery_confirmation_rejected_for_failed_verification(client: TestClient):
    """
    Requirement: Post-delivery XAI must run only when the final code version
    has passed the required verification checks. Delivery cannot be confirmed for failed runs.
    """
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": "def bad(): return 1", "language": "python", "filename": "bad.py"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications?execute_now=true",
        json={"submission_id": sub_id, "trusted_test_cases": "def test_fail(): assert False"},
    )
    run_id = run_res.json()["id"]
    assert run_res.json()["status"] == "FAILED"

    # Attempting to confirm delivery for a failed run must be rejected
    deliv_res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"is_simulation": True},
    )
    assert deliv_res.status_code == 400
    assert "must pass verification tests before delivery" in deliv_res.json()["error"]["message"].lower()


def test_delivery_confirmation_rejected_on_version_mismatch(client: TestClient):
    """
    Requirement: XAI generated for the correct delivered artifact version.
    Rejects delivery confirmation if specified artifact version does not match run submission.
    """
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": "def ok(): return 1", "language": "python", "filename": "ok.py"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications?execute_now=true",
        json={"submission_id": sub_id, "trusted_test_cases": "from solution import ok\ndef test_ok(): assert ok() == 1"},
    )
    run_id = run_res.json()["id"]

    # Deliberate mismatch
    deliv_res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"artifact_version": "sub-completely-different-version", "is_simulation": True},
    )
    assert deliv_res.status_code == 400
    assert "does not match run submission id" in deliv_res.json()["error"]["message"].lower()


def test_post_delivery_explanation_produces_all_eight_dimensions_with_beginner_and_technical_views(client: TestClient):
    """
    Requirement: Produces 8 post-delivery dimensions:
    1. Software overview
    2. Architecture explanation
    3. Module and component responsibilities
    4. Important functions and their behavior
    5. API and data-flow explanations
    6. Relevant algorithms and design decisions
    7. Setup and usage instructions
    8. Known limitations and verification scope
    With distinct Beginner-friendly and Technical explanation layers.
    """
    source_code = '''"""Invoice Calculation Service providing verified arithmetic logic."""

def calculate_tax(amount: float, tax_rate: float = 0.08) -> float:
    """Calculates sales tax for an amount."""
    return amount * tax_rate

def total_with_tax(amount: float, tax_rate: float = 0.08) -> float:
    """Returns subtotal combined with sales tax."""
    return amount + calculate_tax(amount, tax_rate)
'''
    test_code = """
from solution import calculate_tax, total_with_tax

def test_tax_calc():
    assert calculate_tax(100.0, 0.08) == 8.0

def test_total_calc():
    assert total_with_tax(100.0, 0.08) == 108.0
"""
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": source_code, "language": "python", "filename": "invoice_service.py"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications?execute_now=true",
        json={"submission_id": sub_id, "trusted_test_cases": test_code},
    )
    run_id = run_res.json()["id"]

    # Confirm production delivery with credentials
    deliv_res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub_id},
    )
    assert deliv_res.status_code == 201

    pdx_res = client.get(f"/api/v1/verifications/{run_id}/post-delivery-explanation")
    assert pdx_res.status_code == 200
    pdx = pdx_res.json()

    # Dimension 1: Software overview
    assert pdx["software_overview"] is not None
    assert "invoice_service.py" in pdx["software_overview"] or "Invoice" in pdx["software_name"]

    # Dimension 2: Architecture explanation
    assert pdx["architecture_explanation"] is not None
    assert "Architectural Topology" in pdx["architecture_explanation"]

    # Dimension 3: Module responsibilities
    assert len(pdx["module_responsibilities"]) >= 1
    assert pdx["module_responsibilities"][0]["file_path"] == "invoice_service.py"

    # Dimension 4: Important functions (grounded in AST)
    funcs = pdx["important_functions"]
    assert len(funcs) == 2
    func_names = [f["function_name"] for f in funcs]
    assert "calculate_tax" in func_names
    assert "total_with_tax" in func_names
    # Line numbers must be exact physical lines
    calc_func = next(f for f in funcs if f["function_name"] == "calculate_tax")
    assert calc_func["line_number"] == 3
    assert "amount: float" in calc_func["signature"]

    # Dimension 5: API and data flow
    assert "Data Flow & API Entry Points" in pdx["api_and_data_flow"]

    # Dimension 6: Relevant algorithms and design decisions
    assert len(pdx["algorithms_and_design_decisions"]) >= 1

    # Dimension 7: Setup and usage instructions
    assert "### Setup and Usage Guide" in pdx["setup_and_usage"]
    assert "import invoice_service" in pdx["setup_and_usage"]

    # Dimension 8: Known limitations and scope
    assert "### Verification Scope and Operational Boundaries" in pdx["limitations_and_verification_scope"]

    # Check Dual Levels
    beginner = pdx["beginner_level"]
    assert beginner["overview"] is not None
    assert "non-programmer" in beginner["how_to_use"].lower() or "import" in beginner["how_to_use"].lower()
    assert len(beginner["key_capabilities"]) >= 1
    assert beginner["realistic_example"] is not None
    assert "does not prove" in beginner["test_confidence"]

    technical = pdx["technical_level"]
    assert technical["architecture_overview"] is not None
    assert len(technical["important_functions"]) == 2
    assert len(pdx["test_evidence"]) == 2
    assert {item["status"] for item in pdx["test_evidence"]} == {"PASSED"}
    assert pdx["measured_sla"]["verdict"] in {"PASSED", "NOT_ESTABLISHED"}
    assert pdx["evidence_manifest"]["analyzed_source_files"] == ["invoice_service.py"]
    assert beginner["overview"] != technical["architecture_overview"]


def test_zero_fabricated_functions_or_modules():
    """
    Requirement: Never invent functionality or design rationale that cannot be supported by evidence.
    No fabricated functions or modules.
    """
    code = """
def authenticate_user(username, password):
    return username == "admin" and password == "secret"

def generate_session_token(username):
    return f"sess_{username}"
"""
    meta = inspect_python_code_ast(code, filename="auth.py")
    extracted_names = [f["name"] for f in meta["functions"]]

    assert "authenticate_user" in extracted_names
    assert "generate_session_token" in extracted_names
    assert len(extracted_names) == 2

    # Verify that a non-existent function is NOT fabricated
    assert "fabricated_reset_password" not in extracted_names


def test_safe_handling_of_secrets():
    """
    Requirement: Safe handling of secrets. Do not expose secrets, credentials,
    or sensitive runtime information.
    """
    code_with_secrets = """
API_KEY = "AKIAIOSFODNN7EXAMPLE"
PASSWORD = "super_secret_password_12345"
DATABASE_URL = "postgresql://dbuser:mypassword123@localhost:5432/mydb"
BEARER = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"

def get_data():
    return True
"""
    sanitized, redaction_count = sanitize_code_secrets(code_with_secrets)

    assert redaction_count >= 3
    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
    assert "[REDACTED_AWS_KEY]" in sanitized
    assert "super_secret_password_12345" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized
    assert "mypassword123" not in sanitized
    assert "[REDACTED_PASSWORD]" in sanitized


def test_preservation_of_internal_repair_feedback():
    """
    Requirement: Preservation of internal repair feedback for Component 3.
    If verification fails, return structured technical feedback containing failed tests,
    assertions, logs, defect categories, affected files.
    The technical feedback payload must NOT contain user-facing XAI narrative text.
    """
    from datetime import datetime, timezone
    from app.schemas.defect_report import DefectReport
    from app.schemas.test_result import TestResult
    from app.schemas.common import TestType, TestResultStatus

    now = datetime.now(timezone.utc)
    defect = DefectReport(
        defect_id="def-c3-preserve",
        verification_run_id="run-c3-preserve",
        submission_id="sub-c3-preserve",
        title="Assertion failure in test_process",
        description="Observed defect in test_process: assert 10 == 20",
        failed_test="test_process",
        failure_category="ASSERTION_FAILURE",
        assertion_or_exception="assert 10 == 20",
        expected_value="20",
        actual_value="10",
        file_path="process.py",
        line_number=7,
        created_at=now,
    )
    test_res = TestResult(
        test_id="test_process",
        name="test_process",
        test_type=TestType.UNIT,
        status=TestResultStatus.FAILED,
        duration_ms=4.0,
        error_message="assert 10 == 20",
    )
    run = VerificationRunResponse(
        id="run-c3-preserve",
        submission_id="sub-c3-preserve",
        status=VerificationStatus.FAILED,
        test_results=[test_res],
        defect_reports=[defect],
        created_at=now,
        updated_at=now,
    )

    # 1. Technical feedback service builds payload for Component 3
    feedback_svc = TechnicalFeedbackService()
    c3_payload = feedback_svc.build_feedback_payload(run)

    # Check that required structured diagnostic fields are present
    assert len(c3_payload.failed_assertions) == 1
    assert "assert 10 == 20" in c3_payload.failed_assertions[0]
    assert c3_payload.failed_tests == ["test_process"]
    assert len(c3_payload.value_comparisons) == 1
    assert c3_payload.value_comparisons[0]["expected"] == "20"
    assert c3_payload.value_comparisons[0]["observed"] == "10"
    assert c3_payload.defect_ids == ["def-c3-preserve"]

    # Ensure zero user-facing XAI explanation contamination in machine payload
    assert not hasattr(c3_payload, "software_overview")
    assert not hasattr(c3_payload, "beginner_level")
    assert not hasattr(c3_payload, "technical_level")


def test_delivery_gate_blocks_on_hash_mismatch():
    """
    Requirement 7.1: Delivery confirmation must match the exact verified artifact version and content hash.
    If the submission code has changed or the checksum differs, gate must block with BLOCKED_HASH_MISMATCH.
    """
    from datetime import datetime, timezone
    from app.schemas.delivery import DeliveryConfirmation
    from app.schemas.submission import CodeSubmissionResponse
    from app.schemas.test_result import TestResult
    from app.schemas.common import TestType, TestResultStatus

    now = datetime.now(timezone.utc)
    original_code = "def add(a, b): return a + b"
    modified_code = "def add(a, b): return a + b + 1"  # Tampered or stale artifact

    expected_hash = hashlib.sha256(original_code.encode("utf-8")).hexdigest()

    dummy_test = TestResult(
        test_id="test_add",
        name="test_add",
        test_type=TestType.UNIT,
        status=TestResultStatus.PASSED,
        duration_ms=1.0,
    )

    delivery = DeliveryConfirmation(
        delivery_id="dlv-test-hash",
        verification_run_id="run-hash-1",
        submission_id="sub-hash-1",
        artifact_checksum_sha256=expected_hash,
        is_delivered=True,
        is_simulation=False,
    )

    run = VerificationRunResponse(
        id="run-hash-1",
        submission_id="sub-hash-1",
        status=VerificationStatus.PASSED,
        test_results=[dummy_test],
        delivery_confirmation=delivery,
        created_at=now,
        updated_at=now,
    )

    submission_tampered = CodeSubmissionResponse(
        id="sub-hash-1",
        code=modified_code,
        language="python",
        filename="math_lib.py",
        created_at=now,
    )

    service = PostDeliveryXaiService()
    gate_status = service.evaluate_delivery_gate(run, submission=submission_tampered)

    assert gate_status.gate_verdict == "BLOCKED_HASH_MISMATCH"
    assert gate_status.delivery_confirmed is False
    assert "content hash" in gate_status.verdict_reason.lower()
    assert expected_hash in gate_status.verdict_reason


def test_delivery_gate_simulation_flag_and_governance_rejection():
    """
    Requirement 7.1: A simulated delivery confirmation must be explicitly tracked and never conflated
    with production delivery. Governance rejection must block even if delivery confirmation is attempted.
    """
    from datetime import datetime, timezone
    from app.schemas.delivery import DeliveryConfirmation
    from app.schemas.research_reports import DeploymentReadinessReport, ReadinessGatingCheck
    from app.schemas.submission import CodeSubmissionResponse
    from app.schemas.common import DeploymentReadinessStatus, TestType, TestResultStatus
    from app.schemas.test_result import TestResult

    now = datetime.now(timezone.utc)
    code = "def valid(): return True"
    checksum = hashlib.sha256(code.encode("utf-8")).hexdigest()

    dummy_test = TestResult(
        test_id="test_valid",
        name="test_valid",
        test_type=TestType.UNIT,
        status=TestResultStatus.PASSED,
        duration_ms=1.0,
    )

    delivery_sim = DeliveryConfirmation(
        delivery_id="dlv-sim-1",
        verification_run_id="run-sim-1",
        submission_id="sub-sim-1",
        artifact_checksum_sha256=checksum,
        is_delivered=True,
        is_simulation=True,
    )

    run = VerificationRunResponse(
        id="run-sim-1",
        submission_id="sub-sim-1",
        status=VerificationStatus.PASSED,
        test_results=[dummy_test],
        delivery_confirmation=delivery_sim,
        created_at=now,
        updated_at=now,
    )

    submission = CodeSubmissionResponse(
        id="sub-sim-1",
        code=code,
        language="python",
        filename="app.py",
        created_at=now,
    )

    service = PostDeliveryXaiService()

    # 1. Successful simulated delivery
    gate_sim = service.evaluate_delivery_gate(run, submission=submission)
    assert gate_sim.gate_verdict == "SIMULATED_DELIVERY"
    assert gate_sim.is_simulation is True
    assert gate_sim.delivery_confirmed is True

    # 2. Blocked by governance
    gov_rejected = DeploymentReadinessReport(
        report_id="rep-gov-1",
        module_name="app.py",
        verification_run_id="run-sim-1",
        readiness_status=DeploymentReadinessStatus.BLOCKED,
        is_ready_for_deployment=False,
        blocking_reasons=["Security policy violation: unescaped SQL parameter"],
        gating_checks=[
            ReadinessGatingCheck(
                gate_name="SECURITY_SCAN",
                status="FAILED",
                required=True,
                details="High severity injection risk detected",
            )
        ],
        provenance_hash="mock-hash",
        issued_at=now,
    )

    gate_gov_blocked = service.evaluate_delivery_gate(run, submission=submission, governance_report=gov_rejected)
    assert gate_gov_blocked.gate_verdict == "BLOCKED_GOVERNANCE_REJECTED"
    assert gate_gov_blocked.governance_approved is False
    assert gate_gov_blocked.delivery_confirmed is False
    assert "Deployment-readiness governance blocked delivery approval" in gate_gov_blocked.verdict_reason


def _create_passing_run(client: TestClient, code: str = "def solve(): return 42", test: str = "from solution import solve\ndef test_solve(): assert solve() == 42"):
    sub = client.post("/api/v1/submissions", json={"code": code, "language": "python", "filename": "solution.py"}).json()
    run = client.post("/api/v1/verifications?execute_now=true", json={"submission_id": sub["id"], "trusted_test_cases": test}).json()
    return sub["id"], run["id"]


# 1. Missing production credentials
def test_security_01_missing_production_credentials(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"is_simulation": False, "artifact_version": sub_id},
    )
    assert res.status_code == 400
    assert "missing production delivery service credentials" in res.json()["error"]["message"].lower()


# 2. Invalid credentials
def test_security_02_invalid_credentials(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": "invalid_token_attempt_123"},
        json={"is_simulation": False, "artifact_version": sub_id},
    )
    assert res.status_code == 400
    assert "invalid production delivery service credentials" in res.json()["error"]["message"].lower()


# 2b. Compromised / revoked credentials explicitly rejected
def test_security_02b_revoked_compromised_credentials_rejected(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": "intelise_dev_delivery_token_secret"},
        json={"is_simulation": False, "artifact_version": sub_id},
    )
    assert res.status_code == 400
    assert "compromised or revoked" in res.json()["error"]["message"].lower()


# 3. Valid authenticated service identity
def test_security_03_valid_authenticated_service_identity(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub_id},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["is_delivered"] is True
    assert data["is_simulation"] is False
    assert data["confirmed_by"] == "authenticated_delivery_service"


# 4. Caller-supplied forged role strings
def test_security_04_caller_supplied_forged_role_strings(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    # Attempting to supply role string without token
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"is_simulation": False, "artifact_version": sub_id, "confirmed_by": "delivery_orchestrator"},
    )
    assert res.status_code == 400
    assert "missing production delivery service credentials" in res.json()["error"]["message"].lower()

    # Supplying arbitrary role with valid token -> server overrides to authenticated identity
    res_auth = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub_id, "confirmed_by": "super_admin_forged"},
    )
    assert res_auth.status_code == 201
    assert res_auth.json()["confirmed_by"] == "authenticated_delivery_service"


# 5. Unauthorized frontend production confirmation
def test_security_05_unauthorized_frontend_production_confirmation(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"is_simulation": False, "artifact_version": sub_id, "confirmed_by": "frontend_ui"},
    )
    assert res.status_code == 400
    assert "missing production delivery service credentials" in res.json()["error"]["message"].lower()


# 6. Simulation attempts in production mode
def test_security_06_simulation_attempts_in_production_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"is_simulation": True, "artifact_version": sub_id},
    )
    assert res.status_code == 400
    assert "disabled in production" in res.json()["error"]["message"].lower()


# 7. Valid simulation in explicitly enabled development mode
def test_security_07_valid_simulation_in_explicitly_enabled_development_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ALLOW_SIMULATED_DELIVERY", True)
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"is_simulation": True, "artifact_version": sub_id},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["is_delivered"] is True
    assert data["is_simulation"] is True
    assert data["confirmed_by"] == "simulated_harness"

    expl = client.get(f"/api/v1/verifications/{run_id}/explanation").json()
    assert expl["delivery_status"] == "SIMULATED_DELIVERY"
    assert expl["eligible"] is True


# 8. Simulated delivery requesting production-gated explanations
def test_security_08_simulated_delivery_requesting_production_gated_explanations(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"is_simulation": True, "artifact_version": sub_id},
    )
    pdx_res = client.get(f"/api/v1/verifications/{run_id}/post-delivery-explanation")
    assert pdx_res.status_code == 200
    assert pdx_res.json()["verification_run_id"] == run_id


# 9. Artifact checksum mismatch
def test_security_09_artifact_checksum_mismatch(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub_id},
    )

    from app.repositories import get_submission_repository
    sub_repo = get_submission_repository()
    import asyncio
    async def tamper():
        sub = await sub_repo.get_by_id(sub_id)
        sub.code = "def solve(): return 'tampered_code'"
        await sub_repo.save(sub)
    asyncio.run(tamper())

    expl = client.get(f"/api/v1/verifications/{run_id}/explanation").json()
    assert expl["delivery_status"] == "BLOCKED_HASH_MISMATCH"
    assert "hash" in expl["eligibility_reason"].lower()


# 10. Artifact version mismatch
def test_security_10_artifact_version_mismatch(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": "sub-mismatched-id-999"},
    )
    assert res.status_code == 400
    assert "does not match run submission id" in res.json()["error"]["message"].lower()


# 11. Re-verification invalidating delivery confirmation
def test_security_11_reverification_invalidates_delivery_confirmation(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub_id},
    )
    check1 = client.get(f"/api/v1/verifications/{run_id}/explanation").json()
    assert check1["delivery_status"] == "CONFIRMED_PRODUCTION_DELIVERY"

    reverify_res = client.post(
        f"/api/v1/verifications/{run_id}/execute",
    )
    assert reverify_res.status_code == 200

    check2 = client.get(f"/api/v1/verifications/{run_id}/explanation").json()
    assert check2["delivery_status"] == "PENDING_DELIVERY_CONFIRMATION"


# 12. Confirmation replay across different runs
def test_security_12_confirmation_replay_across_different_runs(client: TestClient):
    sub_id1, run_id1 = _create_passing_run(client)
    sub_id2, run_id2 = _create_passing_run(client)

    client.post(
        f"/api/v1/verifications/{run_id1}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub_id1},
    )
    conf1 = client.get(f"/api/v1/verifications/{run_id1}/delivery-confirmation").json()

    from app.repositories import get_verification_repository
    verif_repo = get_verification_repository()
    import asyncio
    from app.schemas.delivery import DeliveryConfirmation
    async def inject_replayed():
        run2 = await verif_repo.get_by_id(run_id2)
        run2.delivery_confirmation = DeliveryConfirmation(**conf1)
        await verif_repo.save(run2)
    asyncio.run(inject_replayed())

    expl = client.get(f"/api/v1/verifications/{run_id2}/explanation").json()
    assert expl["delivery_status"] == "BLOCKED_UNAUTHORIZED_DELIVERY"
    assert "replay across verification runs rejected" in expl["eligibility_reason"].lower()


# 13. Verification failure
def test_security_13_verification_failure_rejects_delivery(client: TestClient):
    sub = client.post("/api/v1/submissions", json={"code": "def bad(): return 1", "language": "python", "filename": "bad.py"}).json()
    run = client.post("/api/v1/verifications?execute_now=true", json={"submission_id": sub["id"], "trusted_test_cases": "def test_fail(): assert False"}).json()
    res = client.post(
        f"/api/v1/verifications/{run['id']}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub["id"]},
    )
    assert res.status_code == 400
    assert "must pass verification tests before delivery" in res.json()["error"]["message"].lower()


# 14. Governance rejection
def test_security_14_governance_rejection_blocks_delivery(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    sub_id, run_id = _create_passing_run(client)
    from app.schemas.research_reports import DeploymentReadinessReport, DeploymentReadinessStatus, ReadinessGatingCheck
    from app.services.verification_service import VerificationService
    import asyncio

    async def mock_report(self, r_id):
        return DeploymentReadinessReport(
            report_id="rep-blocked",
            module_name="solution.py",
            verification_run_id=r_id,
            readiness_status=DeploymentReadinessStatus.BLOCKED,
            is_ready_for_deployment=False,
            blocking_reasons=["Security policy violation: unescaped parameter"],
            gating_checks=[ReadinessGatingCheck(gate_name="SECURITY_POLICY", status="FAILED", required=True, details="Blocked")],
            provenance_hash="mock",
            issued_at=datetime.now(timezone.utc),
        )
    monkeypatch.setattr(VerificationService, "get_deployment_readiness_report", mock_report)

    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub_id},
    )
    assert res.status_code == 400
    assert "governance blocked delivery approval" in res.json()["error"]["message"].lower()


# 15. Successful authorized production confirmation
def test_security_15_successful_authorized_production_confirmation(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"Authorization": f"Bearer {settings.DELIVERY_AUTH_TOKEN}"},
        json={"is_simulation": False, "artifact_version": sub_id, "notes": "Production release signoff"},
    )
    assert res.status_code == 201
    assert res.json()["is_delivered"] is True
    assert res.json()["is_simulation"] is False
    assert res.json()["confirmed_by"] == "authenticated_delivery_service"

    expl = client.get(f"/api/v1/verifications/{run_id}/explanation").json()
    assert expl["delivery_status"] == "CONFIRMED_PRODUCTION_DELIVERY"
    assert expl["eligible"] is True
    assert expl["post_delivery_explanation"] is not None

    pdx = client.get(f"/api/v1/verifications/{run_id}/post-delivery-explanation").json()
    assert pdx["submission_id"] == sub_id


# 16. Secret redaction in logs and API responses
def test_security_16_secret_redaction_in_logs_and_api_responses(client: TestClient):
    sub_id, run_id = _create_passing_run(client)
    res = client.post(
        f"/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": settings.DELIVERY_AUTH_TOKEN},
        json={"is_simulation": False, "artifact_version": sub_id},
    )
    assert res.status_code == 201
    res_str = res.text
    assert settings.DELIVERY_AUTH_TOKEN not in res_str

    expl = client.get(f"/api/v1/verifications/{run_id}/explanation").text
    assert settings.DELIVERY_AUTH_TOKEN not in expl


# 17. Legacy explanation endpoint bypass attempts
def test_security_17_legacy_explanation_endpoint_bypass_attempts(client: TestClient):
    sub = client.post("/api/v1/submissions", json={"code": "def bad(): return 1", "language": "python", "filename": "bad.py"}).json()
    run = client.post("/api/v1/verifications?execute_now=true", json={"submission_id": sub["id"], "trusted_test_cases": "def test_fail(): assert False"}).json()

    expl = client.get(f"/api/v1/verifications/{run['id']}/explanation").json()
    assert expl["eligible"] is False
    assert expl["delivery_status"] == "BLOCKED_VERIFICATION_FAILED"
    assert expl["post_delivery_explanation"] is None

    pdx = client.get(f"/api/v1/verifications/{run['id']}/post-delivery-explanation")
    assert pdx.status_code == 400


