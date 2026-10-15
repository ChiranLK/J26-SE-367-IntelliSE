import asyncio
import pytest
from starlette.testclient import TestClient

from app.schemas.common import TestResultStatus, VerificationStatus
from app.services.docker_runner import DockerTestRunner


def test_docker_sandbox_passing_tests():
    """
    Validates that a real Python submission runs inside the restricted Docker container
    against trusted test cases, passing all assertions and extracting per-test telemetry.
    """
    runner = DockerTestRunner()
    source_code = (
        "def calculate_tax(amount: float, rate: float) -> float:\n"
        "    return round(amount * rate, 2)\n"
        "\n"
        "def is_eligible(age: int) -> bool:\n"
        "    return age >= 18\n"
    )
    trusted_tests = (
        "from solution import calculate_tax, is_eligible\n"
        "\n"
        "def test_calculate_tax():\n"
        "    assert calculate_tax(100.0, 0.15) == 15.0\n"
        "    assert calculate_tax(200.0, 0.05) == 10.0\n"
        "\n"
        "def test_eligibility():\n"
        "    assert is_eligible(18) is True\n"
        "    assert is_eligible(17) is False\n"
    )

    result = asyncio.run(
        runner.execute_verification(
            source_code=source_code,
            trusted_test_cases=trusted_tests,
            filename="tax_module.py",
            timeout_seconds=15,
        )
    )

    assert result.status == VerificationStatus.PASSED.value
    assert result.exit_code == 0
    assert result.is_timeout is False
    assert result.error_message is None
    assert len(result.test_results) == 2

    # Check each test case outcome
    tax_test = next((t for t in result.test_results if "test_calculate_tax" in t.name), None)
    eligibility_test = next((t for t in result.test_results if "test_eligibility" in t.name), None)

    assert tax_test is not None
    assert tax_test.status == TestResultStatus.PASSED

    assert eligibility_test is not None
    assert eligibility_test.status == TestResultStatus.PASSED


def test_docker_sandbox_failing_assertion():
    """
    Validates that when submitted code produces incorrect behavior, the container runner
    captures the failed assertion and stack trace without fabricating results.
    """
    runner = DockerTestRunner()
    # Buggy code: subtract instead of add
    buggy_code = (
        "def add_numbers(a: int, b: int) -> int:\n"
        "    return a - b\n"
    )
    trusted_tests = (
        "from solution import add_numbers\n"
        "\n"
        "def test_add_numbers_correctly():\n"
        "    assert add_numbers(10, 5) == 15\n"
    )

    result = asyncio.run(
        runner.execute_verification(
            source_code=buggy_code,
            trusted_test_cases=trusted_tests,
            timeout_seconds=15,
        )
    )

    assert result.status == VerificationStatus.FAILED.value
    assert result.exit_code == 1
    assert result.is_timeout is False
    assert "failed" in (result.error_message or "").lower()
    assert len(result.test_results) == 1

    failed_test = result.test_results[0]
    assert failed_test.status == TestResultStatus.FAILED
    assert failed_test.name == "test_add_numbers_correctly"
    assert failed_test.error_message is not None


def test_docker_sandbox_timeout_enforcement():
    """
    Validates that infinite loops or runaway processes are terminated cleanly at the timeout
    limit and categorized as TIMEOUT, with container killed and resources released.
    """
    runner = DockerTestRunner()
    infinite_loop_code = (
        "def long_running_task():\n"
        "    while True:\n"
        "        pass\n"
    )
    trusted_tests = (
        "from solution import long_running_task\n"
        "\n"
        "def test_hang():\n"
        "    long_running_task()\n"
    )

    # Use a tight 2-second timeout for this test
    result = asyncio.run(
        runner.execute_verification(
            source_code=infinite_loop_code,
            trusted_test_cases=trusted_tests,
            timeout_seconds=2,
        )
    )

    assert result.is_timeout is True
    assert result.status == TestResultStatus.TIMEOUT.value
    assert "timed out" in (result.error_message or "").lower() or "timeout" in (result.error_message or "").lower()
    assert len(result.test_results) == 1
    assert result.test_results[0].status == TestResultStatus.TIMEOUT


def test_no_test_oracle_supplied_is_skipped():
    """
    Enforces Requirement 6: Do not claim arbitrary code is defective without a valid test oracle.
    When no trusted tests are supplied, syntax is validated, status is SKIPPED, and no false defects are created.
    """
    runner = DockerTestRunner()
    valid_code = "def valid_func(x): return x * 2"

    result = asyncio.run(
        runner.execute_verification(
            source_code=valid_code,
            trusted_test_cases=None,  # No oracle supplied
        )
    )

    assert result.status == TestResultStatus.SKIPPED.value
    assert result.no_oracle is True
    assert len(result.test_results) == 1
    assert result.test_results[0].test_id == "ast_syntax_check"
    assert result.test_results[0].status == TestResultStatus.PASSED
    assert "syntax_valid" in result.telemetry


def test_syntax_error_in_submitted_code():
    """
    Validates that malformed syntax fails static AST parsing host-side without executing code,
    and is categorized as ERROR (not a verified functional defect).
    """
    runner = DockerTestRunner()
    malformed_code = "def broken_func(:\n    return 42"
    trusted_tests = "def test_dummy(): assert True"

    result = asyncio.run(
        runner.execute_verification(
            source_code=malformed_code,
            trusted_test_cases=trusted_tests,
        )
    )

    assert result.status == TestResultStatus.ERROR.value
    assert "SyntaxError" in (result.error_message or "")
    assert len(result.test_results) == 1
    assert result.test_results[0].status == TestResultStatus.ERROR


def test_docker_unavailable_fail_closed(monkeypatch):
    """
    Enforces Rule 5: Fail closed if required isolation controls are unavailable.
    Never executes code directly on the host.
    """
    runner = DockerTestRunner()
    monkeypatch.setattr(runner, "check_docker_available", lambda: (False, "Daemon offline mock"))

    result = asyncio.run(
        runner.execute_verification(
            source_code="print('should never run on host')",
            trusted_test_cases="def test_fake(): assert True",
        )
    )

    assert result.status == TestResultStatus.ERROR.value
    assert "Infrastructure isolation failure" in (result.error_message or "")


def test_api_verification_execution_lifecycle_e2e(client: TestClient):
    """
    Full End-to-End API verification lifecycle test:
    1. Ingest submission with accompanying test code.
    2. Create verification run -> status is PENDING.
    3. Execute verification run via POST /verifications/{id}/execute -> executes in Docker.
    4. Verify final status is PASSED and real test results are persisted in storage.
    """
    source_code = "def greet(name: str) -> str: return f'Hello, {name}!'"
    test_code = "from solution import greet\ndef test_greet(): assert greet('Alice') == 'Hello, Alice!'"

    # 1. Create submission
    sub_res = client.post(
        "/api/v1/submissions",
        json={
            "code": source_code,
            "language": "python",
            "filename": "greeter.py",
            "test_code": test_code,
        },
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    # 2. Create verification run (initially PENDING)
    create_res = client.post(
        "/api/v1/verifications",
        json={"submission_id": sub_id, "triggered_by": "e2e_test"},
    )
    assert create_res.status_code == 201
    run_id = create_res.json()["id"]
    assert create_res.json()["status"] == "PENDING"
    assert create_res.json()["test_results"] == []

    # 3. Trigger execution
    exec_res = client.post(f"/api/v1/verifications/{run_id}/execute")
    assert exec_res.status_code == 200
    exec_data = exec_res.json()

    assert exec_data["status"] == "PASSED"
    assert len(exec_data["test_results"]) == 1
    assert exec_data["test_results"][0]["status"] == "PASSED"
    assert exec_data["test_results"][0]["name"] == "test_greet"

    # 4. Fetch details via GET
    get_res = client.get(f"/api/v1/verifications/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "PASSED"

    # 5. Fetch lightweight status
    status_res = client.get(f"/api/v1/verifications/{run_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "PASSED"


def test_api_verification_execute_now_query_param(client: TestClient):
    """
    Verifies that passing ?execute_now=true on creation triggers the LangGraph
    verification pipeline immediately.
    """
    source_code = "def cube(x: int) -> int: return x ** 3"
    trusted_tests = "from solution import cube\ndef test_cube(): assert cube(3) == 27"

    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": source_code, "language": "python"},
    )
    sub_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications?execute_now=true",
        json={
            "submission_id": sub_id,
            "trusted_test_cases": trusted_tests,
        },
    )
    assert run_res.status_code == 201
    data = run_res.json()
    assert data["status"] == "PASSED"
    assert len(data["test_results"]) == 1
    assert data["test_results"][0]["name"] == "test_cube"
