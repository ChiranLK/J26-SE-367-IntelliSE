"""
Controlled demonstrations verifying Phase 2 improvements:
1. Security vulnerability detection with ordinary unit tests passing (real Docker).
2. Safe code with similar syntax but no actual vulnerability (negative controls, real Docker).
3. Functional defect localization to an implementation line (real Docker).
4. Integration of findings into LangGraph, technical feedback and XAI.
5. Deployment readiness blocking on confirmed critical vulnerabilities.
"""

import asyncio
import pytest

from app.schemas.common import (
    DefectSeverity,
    DeploymentReadinessStatus,
    ProgrammingLanguage,
    TestResultStatus,
    VerificationStatus,
)
from app.schemas.submission import CodeSubmissionResponse, SubmissionResponse
from app.schemas.verification import VerificationRunResponse
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.docker_runner import DockerTestRunner
from app.services.feedback_service import TechnicalFeedbackService
from app.services.governance_report_service import GovernanceReportService
from app.services.xai_service import DeterministicEvidenceExplanationProvider, XaiExplanationService
from app.workflows.verification_graph import verification_pipeline


@pytest.mark.anyio
async def test_real_docker_security_detection_unit_tests_passing():
    """
    Demonstration 1: Real Docker execution where ordinary unit tests pass,
    yet static AST security analysis flags a confirmed critical security vulnerability (CWE-78).
    Also confirms coverage for CWE-95, CWE-22, CWE-798, and CWE-89.
    """
    runner = DockerTestRunner()
    if not runner.check_docker_available():
        pytest.skip("Docker daemon not available for live container demonstration")

    # Code vulnerable to CWE-78 (OS Command Injection)
    vulnerable_code = (
        "import os\n"
        "\n"
        "def query_user(username: str) -> int:\n"
        "    # Vulnerable to command injection via shell command string concatenation\n"
        "    return os.system('echo user ' + username)\n"
    )

    # Unit test tests normal input; inside Docker sandbox echo exits with code 0
    test_code = (
        "import solution\n"
        "\n"
        "def test_query_user_ordinary_input():\n"
        "    # Ordinary functional test passes!\n"
        "    ret = solution.query_user('alice')\n"
        "    assert ret == 0\n"
    )

    result = await runner.execute_verification(
        source_code=vulnerable_code,
        trusted_test_cases=test_code,
        filename="user_ops.py",
        timeout_seconds=20,
    )

    # 1. Real Docker test execution outcome: PASSES
    assert result.status == VerificationStatus.PASSED.value
    assert result.exit_code == 0
    assert len(result.test_results) == 1
    assert result.test_results[0].status == TestResultStatus.PASSED

    # 2. Defect Analysis Service analyzes the run with source code AST inspection
    analyzer = DefectAnalysisService()
    defects = analyzer.analyze_test_results(
        run_id="run-demo-sec-01",
        submission_id="sub-demo-sec-01",
        status=result.status,
        test_results=result.test_results,
        affected_filename="user_ops.py",
        source_code=vulnerable_code,
    )

    # 3. Security vulnerability is detected despite all tests passing!
    assert len(defects) >= 1
    cwe78_defect = next((d for d in defects if d.cwe_id == "CWE-78"), None)
    assert cwe78_defect is not None, "CWE-78 vulnerability was not detected!"
    assert cwe78_defect.severity == DefectSeverity.CRITICAL
    assert cwe78_defect.confidence == "CONFIRMED"
    assert cwe78_defect.provenance == "AST_STATIC_ANALYSIS"
    assert cwe78_defect.file_path == "user_ops.py"
    assert cwe78_defect.line_number == 5

    # 4. Verify all 5 CWEs in static AST analysis
    cwe_95_code = "def run(x): return eval(x)"
    f_95 = analyzer.inspect_static_security_vulnerabilities(cwe_95_code)
    assert any(f["cwe_id"] == "CWE-95" for f in f_95)

    cwe_22_code = "def get(name): return open(f'/var/log/{name}').read()"
    f_22 = analyzer.inspect_static_security_vulnerabilities(cwe_22_code)
    assert any(f["cwe_id"] == "CWE-22" for f in f_22)

    cwe_798_code = "SECRET_TOKEN = 'sk-prod-9948281948291048291'"
    f_798 = analyzer.inspect_static_security_vulnerabilities(cwe_798_code)
    assert any(f["cwe_id"] == "CWE-798" for f in f_798)

    cwe_89_code = "def query(db, usr): return db.execute(f'SELECT * FROM u WHERE id={usr}')"
    f_89 = analyzer.inspect_static_security_vulnerabilities(cwe_89_code)
    assert any(f["cwe_id"] == "CWE-89" for f in f_89)


@pytest.mark.anyio
async def test_real_docker_safe_negative_controls():
    """
    Demonstration 2: Safe code with similar patterns (subprocess shell=False,
    parameterized SQL, safe path basename, environment secret lookup).
    Real Docker execution passes and produces ZERO false-positive security defects.
    """
    runner = DockerTestRunner()
    if not runner.check_docker_available():
        pytest.skip("Docker daemon not available for live container demonstration")

    safe_code = (
        "import os\n"
        "import subprocess\n"
        "\n"
        "def run_safe_command(msg: str) -> str:\n"
        "    # Safe: shell=False with argument list\n"
        "    res = subprocess.run(['echo', msg], shell=False, capture_output=True, text=True)\n"
        "    return res.stdout.strip()\n"
        "\n"
        "def read_safe_file(base_dir: str, filename: str) -> str:\n"
        "    # Safe: sanitized basename prevents directory traversal\n"
        "    safe_name = os.path.basename(filename)\n"
        "    target_path = os.path.join(base_dir, safe_name)\n"
        "    return target_path\n"
        "\n"
        "def query_database(cursor, user_id: int):\n"
        "    # Safe: Parameterized query\n"
        "    return cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))\n"
    )

    test_code = (
        "import solution\n"
        "\n"
        "def test_safe_command():\n"
        "    assert solution.run_safe_command('hello_world') == 'hello_world'\n"
        "\n"
        "def test_safe_path():\n"
        "    path = solution.read_safe_file('/app', '../../etc/passwd')\n"
        "    assert path == '/app/passwd'\n"
    )

    result = await runner.execute_verification(
        source_code=safe_code,
        trusted_test_cases=test_code,
        filename="safe_service.py",
        timeout_seconds=20,
    )

    assert result.status == VerificationStatus.PASSED.value
    assert result.exit_code == 0

    analyzer = DefectAnalysisService()
    findings = analyzer.inspect_static_security_vulnerabilities(safe_code)
    assert len(findings) == 0, f"Expected 0 findings on safe negative control, got: {findings}"

    defects = analyzer.analyze_test_results(
        run_id="run-demo-safe-01",
        submission_id="sub-demo-safe-01",
        status=result.status,
        test_results=result.test_results,
        affected_filename="safe_service.py",
        source_code=safe_code,
    )
    assert len(defects) == 0, "Negative control produced false-positive defect report!"


@pytest.mark.anyio
async def test_real_docker_functional_defect_localization_to_implementation():
    """
    Demonstration 3: Functional defect executed inside real Docker container.
    Verifies that evidence-based localization attributes the failure to the
    implementation file ('solution.py' / statement line), and does NOT attribute it
    to the test suite line.
    """
    runner = DockerTestRunner()
    if not runner.check_docker_available():
        pytest.skip("Docker daemon not available for live container demonstration")

    # Buggy discount logic: returns 5% instead of 10% on line 7
    defective_code = (
        "def calculate_discount(price: float, is_member: bool) -> float:\n"
        "    if price <= 0:\n"
        "        return 0.0\n"
        "    if is_member:\n"
        "        return round(price * 0.20, 2)\n"
        "    # Defective line: should be 0.10 for standard customers\n"
        "    return round(price * 0.05, 2)\n"
    )

    test_code = (
        "import solution\n"
        "\n"
        "def test_member_discount():\n"
        "    assert solution.calculate_discount(100.0, True) == 20.0\n"
        "\n"
        "def test_standard_discount_failing():\n"
        "    # Expected: 10.0, Actual implementation returns: 5.0\n"
        "    assert solution.calculate_discount(100.0, False) == 10.0\n"
    )

    result = await runner.execute_verification(
        source_code=defective_code,
        trusted_test_cases=test_code,
        filename="solution.py",
        timeout_seconds=20,
    )

    # Real Docker execution results in a failing test
    assert result.status == VerificationStatus.FAILED.value
    failed_test = next(t for t in result.test_results if t.status == TestResultStatus.FAILED)
    assert "test_standard_discount_failing" in failed_test.name

    analyzer = DefectAnalysisService()
    defects = analyzer.analyze_test_results(
        run_id="run-demo-func-01",
        submission_id="sub-demo-func-01",
        status=result.status,
        test_results=result.test_results,
        affected_filename="solution.py",
        source_code=defective_code,
    )

    assert len(defects) == 1
    d = defects[0]

    # Localization attributes to implementation, NOT the test suite
    assert d.file_path == "solution.py"
    assert d.line_number is not None
    # Implementation lines for calculate_discount are 1 to 7; test line is ~8 in test_code
    assert 1 <= d.line_number <= 7, f"Line number {d.line_number} was not in implementation function range [1, 7]"
    assert d.confidence in ("CONFIRMED", "HIGH", "MEDIUM")
    assert d.provenance in ("AST_SOURCE_MAPPING", "TRACEBACK_FRAME_ANALYSIS")
    assert d.traceback_excerpt is not None


@pytest.mark.anyio
async def test_findings_integration_into_langgraph_technical_feedback_and_xai():
    """
    Demonstration 4: End-to-end integration of security vulnerability into
    LangGraph verification workflow, TechnicalFeedbackService, and XaiExplanationService.
    Status is overridden from PASSED to FAILED, technical feedback contains CWE/line,
    and XAI explains the defect.
    """
    # Vulnerable module with passing test
    vuln_code = (
        "import os\n"
        "\n"
        "def query_host(ip: str) -> int:\n"
        "    return os.system('echo ' + ip)\n"
    )
    passing_test = (
        "import solution\n"
        "\n"
        "def test_host():\n"
        "    assert solution.query_host('127.0.0.1') == 0\n"
    )

    state = {
        "submission_id": "sub-langgraph-sec-01",
        "run_id": "run-langgraph-sec-01",
        "source_code": vuln_code,
        "language": "python",
        "filename": "host_service.py",
        "trusted_test_cases": passing_test,
        "timeout_seconds": 15,
        "requested_test_types": ["unit"],
        "feedback_iterations": [],
        "telemetry": {},
    }

    workflow_result = await verification_pipeline.ainvoke(state)

    # 1. LangGraph status is overridden to FAILED because of security finding
    assert workflow_result["status"] == VerificationStatus.FAILED.value
    assert workflow_result["telemetry"].get("status_overridden_by_security_analysis") is True
    assert len(workflow_result["defect_reports"]) >= 1

    sec_defect = workflow_result["defect_reports"][0]
    assert sec_defect.cwe_id == "CWE-78"
    assert sec_defect.line_number == 4

    # 2. Technical Feedback contains the defect details
    tf = workflow_result.get("technical_feedback")
    assert tf is not None
    assert len(tf.defect_ids) >= 1
    assert any(d.cwe_id == "CWE-78" for d in workflow_result["defect_reports"])

    # 3. XAI Service generates human-facing explanation with defect location
    xai_provider = DeterministicEvidenceExplanationProvider()
    xai_service = XaiExplanationService(provider=xai_provider)

    run_obj = VerificationRunResponse(
        id="run-langgraph-sec-01",
        submission_id="sub-langgraph-sec-01",
        status=VerificationStatus.FAILED,
        test_results=workflow_result["test_results"],
        defect_reports=workflow_result["defect_reports"],
    )
    sub_obj = CodeSubmissionResponse(
        id="sub-langgraph-sec-01",
        code=vuln_code,
        language=ProgrammingLanguage.PYTHON,
        filename="host_service.py",
    )

    xai_response = xai_service.generate_explanation(run_obj, sub_obj)
    assert xai_response.verification_status == "FAILED"
    assert len(xai_response.what_failed) >= 1
    assert "host_service.py:4" in xai_response.what_failed[0]

    # Traceability-scoped payload incorporates target seam
    scoped = xai_service.generate_traceability_scoped_explanation(run_obj, sec_defect, sub_obj)
    assert scoped.affected_file == "host_service.py"
    assert scoped.line_number == 4
    assert scoped.cwe_id == "CWE-78"
    assert "around line 4" in scoped.regeneration_guidance


def test_deployment_readiness_blocking_on_confirmed_critical_vulnerability():
    """
    Demonstration 5: Deployment readiness check blocks release when a confirmed
    critical security vulnerability exists in the verification run.
    """
    analyzer = DefectAnalysisService()
    findings = analyzer.inspect_static_security_vulnerabilities(
        "import os\ndef ping(ip): return os.system('ping ' + ip)"
    )
    assert len(findings) == 1

    sec_report = analyzer.analyze_test_results(
        run_id="run-gate-test-01",
        submission_id="sub-gate-test-01",
        status="PASSED",
        test_results=[],
        source_code="import os\ndef ping(ip): return os.system('ping ' + ip)",
        affected_filename="net.py",
    )

    run_obj = VerificationRunResponse(
        id="run-gate-test-01",
        submission_id="sub-gate-test-01",
        status=VerificationStatus.FAILED,
        test_results=[],
        defect_reports=sec_report,
    )
    sub_obj = SubmissionResponse(
        id="sub-gate-test-01",
        code="import os\ndef ping(ip): return os.system('ping ' + ip)",
        language=ProgrammingLanguage.PYTHON,
        filename="net.py",
    )

    gov_service = GovernanceReportService()
    report = gov_service.generate_deployment_readiness_report(run_obj, sub_obj)

    assert report.is_ready_for_deployment is False
    assert report.readiness_status == DeploymentReadinessStatus.BLOCKED

    # Gate 2 must fail
    sec_gate = next(g for g in report.gating_checks if g.gate_name == "ZERO_CRITICAL_SECURITY_DEFECTS")
    assert sec_gate.status == "FAILED"
    assert any("unmitigated critical or security defect" in r for r in report.blocking_reasons)
