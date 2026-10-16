"""
Controlled verification tests for Multi-Agent Integration and Verdict Correctness (Proposal SO1, FR02).
Validates Tasks 1, 2, and 5:
- Specialized agents connected into LangGraph.
- Autonomous test generation with docstring contracts vs callable checks.
- Verdict correctness across all combinations (Unit fail, Integ fail, Perf fail, All pass, Error/Timeout).
- Propagation of defect evidence to Defect Analysis, XAI, Governance, and Telemetry.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.schemas.common import (
    DefectCategory,
    ProgrammingLanguage,
    TestResultStatus,
    TestType,
    VerificationStatus,
)
from app.schemas.research_reports import (
    IntegrationTestReport,
    MultiAgentCoordinationPlan,
    PerformanceMetrics,
    PerformanceTestReport,
    UnitTestReport,
)
from app.schemas.submission import CodeSubmissionCreate, SubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunCreate, VerificationRunResponse
from app.services.agent_testing_service import (
    IntegrationTestAgent,
    PerformanceTestAgent,
    TestCoordinationService,
    UnitTestAgent,
)
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.docker_runner import DockerTestRunner, SandboxExecutionResult
from app.services.governance_report_service import GovernanceReportService
from app.services.xai_service import XaiExplanationService
from app.workflows.verification_graph import verification_pipeline


# =============================================================================
# Task 2: Autonomous Unit Test Generation & Oracles
# =============================================================================

def test_autonomous_unit_test_generation_with_docstring_contracts():
    """Validates contract extraction and boundary oracle generation from docstrings."""
    source_code = '''
def calculate_discount(price: float, discount_percent: float) -> float:
    """
    Computes discounted price.
    Contract: calculate_discount(100.0, 20.0) -> 80.0
    Contract: calculate_discount(50.0, 0.0) -> 50.0
    Contract: calculate_discount(100.0, -10.0) raises ValueError
    """
    if discount_percent < 0:
        raise ValueError("Discount cannot be negative")
    return price * (1.0 - discount_percent / 100.0)
'''
    agent = UnitTestAgent()
    test_code, provenance = agent.generate_autonomous_unit_test_suite(
        source_code, filename="solution.py", trust_submitted_docstrings=True
    )

    assert provenance["meaningful_oracle_available"] is True
    assert provenance["contracts_found"] == 3
    assert "calculate_discount" in provenance["functions_covered"]
    assert "calculate_discount" in provenance["functions_with_contracts"]
    assert "test_gen_boundary_calculate_discount_1" in test_code
    assert "test_gen_boundary_calculate_discount_raises_3" in test_code
    assert "pytest.raises(ValueError)" in test_code
    assert "calculate_discount(100.0, 20.0) == 80.0" in test_code


def test_autonomous_unit_test_generation_without_specifications():
    """When specifications are absent, generates callable-only check and reports oracle unavailable."""
    source_code = '''
def unannotated_function(x, y):
    return x * y + 42
'''
    agent = UnitTestAgent()
    test_code, provenance = agent.generate_autonomous_unit_test_suite(source_code, filename="solution.py")

    assert provenance["meaningful_oracle_available"] is False
    assert provenance["contracts_found"] == 0
    assert "test_unannotated_function_callable" in test_code
    assert "hasattr(solution, 'unannotated_function')" in test_code
    assert "Meaningful boundary oracle unavailable" in test_code


# =============================================================================
# Task 5: Multi-Agent Verdict Correctness Matrix
# =============================================================================

@pytest.mark.anyio
async def test_multi_agent_verdict_unit_fails():
    """Scenario 1: Unit fails, Integration passes, Performance passes -> FAILED."""
    coord_service = TestCoordinationService()

    # Mock agents
    coord_service.unit_agent.execute_unit_tests = AsyncMock(
        return_value=UnitTestReport(
            agent_id="agent-unit-01",
            total_tests=2,
            passed_tests=1,
            failed_tests=1,
            duration_ms=10.0,
            test_results=[
                TestResult(test_id="u1", name="test_add", status=TestResultStatus.PASSED, test_type=TestType.UNIT),
                TestResult(test_id="u2", name="test_sub", status=TestResultStatus.FAILED, error_message="AssertionError: 5 != 3", test_type=TestType.UNIT),
            ],
            status="FAILED",
        )
    )
    coord_service.integration_agent.execute_integration_tests = AsyncMock(
        return_value=IntegrationTestReport(
            agent_id="agent-integration-01",
            total_interactions=1,
            passed_interactions=1,
            failed_interactions=0,
            duration_ms=15.0,
            test_results=[
                TestResult(test_id="i1", name="test_api_client", status=TestResultStatus.PASSED, test_type=TestType.INTEGRATION),
            ],
            status="PASSED",
        )
    )
    coord_service.performance_agent.execute_performance_tests = AsyncMock(
        return_value=PerformanceTestReport(
            agent_id="agent-performance-01",
            metrics=PerformanceMetrics(sample_size=5, duration_ms=25.0, mean_latency_ms=5.0, latency_p50_ms=5.0, latency_p95_ms=10.0, latency_p99_ms=12.0, max_latency_ms=12.0, throughput_rps=100.0, threshold_latency_ms=200.0, is_breached=False),
            test_results=[
                TestResult(test_id="p1", name="test_perf_compliance", status=TestResultStatus.PASSED, test_type=TestType.PERFORMANCE),
            ],
            status="PASSED",
        )
    )

    plan = MultiAgentCoordinationPlan(
        plan_id="plan-test-01",
        verification_run_id="run-01",
        assigned_agents=["unit", "integration", "performance"],
    )

    res = await coord_service.execute_coordinated_verification(plan, "code", "tests")
    assert res["overall_status"] == "FAILED"
    assert len(res["test_results"]) == 4
    assert res["agent_reports"]["unit"].status == "FAILED"
    assert res["agent_reports"]["integration"].status == "PASSED"
    assert res["agent_reports"]["performance"].status == "PASSED"


@pytest.mark.anyio
async def test_multi_agent_verdict_integration_fails():
    """Scenario 2: Unit passes, Integration fails, Performance passes -> FAILED."""
    coord_service = TestCoordinationService()

    coord_service.unit_agent.execute_unit_tests = AsyncMock(
        return_value=UnitTestReport(
            agent_id="agent-unit-01",
            total_tests=1,
            passed_tests=1,
            failed_tests=0,
            duration_ms=10.0,
            test_results=[
                TestResult(test_id="u1", name="test_unit", status=TestResultStatus.PASSED, test_type=TestType.UNIT),
            ],
            status="PASSED",
        )
    )
    coord_service.integration_agent.execute_integration_tests = AsyncMock(
        return_value=IntegrationTestReport(
            agent_id="agent-integration-01",
            total_interactions=2,
            passed_interactions=1,
            failed_interactions=1,
            duration_ms=15.0,
            test_results=[
                TestResult(test_id="i1", name="test_service_seam", status=TestResultStatus.PASSED, test_type=TestType.INTEGRATION),
                TestResult(test_id="i2", name="test_db_gateway", status=TestResultStatus.FAILED, error_message="ConnectionRefusedError", test_type=TestType.INTEGRATION),
            ],
            status="FAILED",
        )
    )
    coord_service.performance_agent.execute_performance_tests = AsyncMock(
        return_value=PerformanceTestReport(
            agent_id="agent-performance-01",
            metrics=PerformanceMetrics(sample_size=5, duration_ms=25.0, mean_latency_ms=5.0, latency_p50_ms=5.0, latency_p95_ms=10.0, latency_p99_ms=12.0, max_latency_ms=12.0, throughput_rps=100.0, threshold_latency_ms=200.0, is_breached=False),
            test_results=[
                TestResult(test_id="p1", name="test_perf_compliance", status=TestResultStatus.PASSED, test_type=TestType.PERFORMANCE),
            ],
            status="PASSED",
        )
    )

    plan = MultiAgentCoordinationPlan(
        plan_id="plan-test-02",
        verification_run_id="run-02",
        assigned_agents=["unit", "integration", "performance"],
    )

    res = await coord_service.execute_coordinated_verification(plan, "code", "tests")
    assert res["overall_status"] == "FAILED"
    assert res["agent_reports"]["integration"].status == "FAILED"


@pytest.mark.anyio
async def test_multi_agent_verdict_performance_fails():
    """Scenario 3: Unit passes, Integration passes, Performance fails -> FAILED."""
    coord_service = TestCoordinationService()

    coord_service.unit_agent.execute_unit_tests = AsyncMock(
        return_value=UnitTestReport(
            agent_id="agent-unit-01",
            total_tests=1,
            passed_tests=1,
            failed_tests=0,
            duration_ms=10.0,
            test_results=[
                TestResult(test_id="u1", name="test_unit", status=TestResultStatus.PASSED, test_type=TestType.UNIT),
            ],
            status="PASSED",
        )
    )
    coord_service.integration_agent.execute_integration_tests = AsyncMock(
        return_value=IntegrationTestReport(
            agent_id="agent-integration-01",
            total_interactions=1,
            passed_interactions=1,
            failed_interactions=0,
            duration_ms=15.0,
            test_results=[
                TestResult(test_id="i1", name="test_integ", status=TestResultStatus.PASSED, test_type=TestType.INTEGRATION),
            ],
            status="PASSED",
        )
    )
    coord_service.performance_agent.execute_performance_tests = AsyncMock(
        return_value=PerformanceTestReport(
            agent_id="agent-performance-01",
            metrics=PerformanceMetrics(
                sample_size=10,
                duration_ms=350.0,
                mean_latency_ms=310.0,
                latency_p50_ms=300.0,
                latency_p95_ms=320.0,
                latency_p99_ms=340.0,
                max_latency_ms=350.0,
                throughput_rps=3.0,
                threshold_latency_ms=200.0,
                is_breached=True,
            ),
            bottlenecks_detected=["Latency threshold breach: 95th percentile latency (320.0ms) exceeded allowable threshold (200.0ms)."],
            test_results=[
                TestResult(
                    test_id="perf_sla_breach",
                    name="test_performance_sla_compliance",
                    status=TestResultStatus.FAILED,
                    error_message="Latency threshold breach (320ms > 200ms)",
                    duration_ms=320.0,
                    test_type=TestType.PERFORMANCE,
                ),
            ],
            status="FAILED",
        )
    )

    plan = MultiAgentCoordinationPlan(
        plan_id="plan-test-03",
        verification_run_id="run-03",
        assigned_agents=["unit", "integration", "performance"],
    )

    res = await coord_service.execute_coordinated_verification(plan, "code", "tests")
    assert res["overall_status"] == "FAILED"
    assert res["agent_reports"]["performance"].status == "FAILED"

    # Verify that defect analysis categorizes the SLA breach as PERFORMANCE_BOTTLENECK
    defect_service = DefectAnalysisService()
    defects = defect_service.analyze_test_results(
        run_id="run-03",
        submission_id="sub-03",
        status="FAILED",
        test_results=res["test_results"],
    )
    assert len(defects) == 1
    assert defects[0].defect_category == "performance_bottleneck"
    assert defects[0].performance_metrics["threshold_breached"] is True


@pytest.mark.anyio
async def test_multi_agent_verdict_all_pass():
    """Scenario 4: All three specialized agents pass -> PASSED."""
    coord_service = TestCoordinationService()

    coord_service.unit_agent.execute_unit_tests = AsyncMock(
        return_value=UnitTestReport(
            agent_id="agent-unit-01",
            total_tests=2,
            passed_tests=2,
            failed_tests=0,
            duration_ms=10.0,
            test_results=[
                TestResult(test_id="u1", name="test_1", status=TestResultStatus.PASSED, test_type=TestType.UNIT),
                TestResult(test_id="u2", name="test_2", status=TestResultStatus.PASSED, test_type=TestType.UNIT),
            ],
            status="PASSED",
        )
    )
    coord_service.integration_agent.execute_integration_tests = AsyncMock(
        return_value=IntegrationTestReport(
            agent_id="agent-integration-01",
            total_interactions=1,
            passed_interactions=1,
            failed_interactions=0,
            duration_ms=15.0,
            test_results=[
                TestResult(test_id="i1", name="test_integ", status=TestResultStatus.PASSED, test_type=TestType.INTEGRATION),
            ],
            status="PASSED",
        )
    )
    coord_service.performance_agent.execute_performance_tests = AsyncMock(
        return_value=PerformanceTestReport(
            agent_id="agent-performance-01",
            metrics=PerformanceMetrics(sample_size=5, duration_ms=50.0, mean_latency_ms=10.0, latency_p50_ms=10.0, latency_p95_ms=15.0, latency_p99_ms=20.0, max_latency_ms=20.0, throughput_rps=100.0, threshold_latency_ms=200.0, is_breached=False),
            test_results=[
                TestResult(test_id="p1", name="test_perf", status=TestResultStatus.PASSED, test_type=TestType.PERFORMANCE),
            ],
            status="PASSED",
        )
    )

    plan = MultiAgentCoordinationPlan(
        plan_id="plan-test-04",
        verification_run_id="run-04",
        assigned_agents=["unit", "integration", "performance"],
    )

    res = await coord_service.execute_coordinated_verification(plan, "code", "tests")
    assert res["overall_status"] == "PASSED"
    assert len(res["test_results"]) == 4


@pytest.mark.anyio
async def test_multi_agent_verdict_agent_error_or_timeout():
    """Scenario 5: Required agent times out or crashes -> ERROR (not PASSED)."""
    coord_service = TestCoordinationService()

    coord_service.unit_agent.execute_unit_tests = AsyncMock(
        return_value=UnitTestReport(
            agent_id="agent-unit-01",
            total_tests=1,
            passed_tests=1,
            failed_tests=0,
            duration_ms=10.0,
            test_results=[
                TestResult(test_id="u1", name="test_unit", status=TestResultStatus.PASSED, test_type=TestType.UNIT),
            ],
            status="PASSED",
        )
    )
    # Integration agent raises unhandled exception (e.g. socket timeout / sandbox crash)
    coord_service.integration_agent.execute_integration_tests = AsyncMock(
        side_effect=RuntimeError("Container sandbox crashed unexpectedly")
    )
    coord_service.performance_agent.execute_performance_tests = AsyncMock(
        return_value=PerformanceTestReport(
            agent_id="agent-performance-01",
            metrics=PerformanceMetrics(sample_size=5, duration_ms=20.0, mean_latency_ms=4.0, latency_p50_ms=4.0, latency_p95_ms=5.0, latency_p99_ms=5.0, max_latency_ms=5.0, throughput_rps=200.0, threshold_latency_ms=200.0, is_breached=False),
            test_results=[
                TestResult(test_id="p1", name="test_perf", status=TestResultStatus.PASSED, test_type=TestType.PERFORMANCE),
            ],
            status="PASSED",
        )
    )

    plan = MultiAgentCoordinationPlan(
        plan_id="plan-test-05",
        verification_run_id="run-05",
        assigned_agents=["unit", "integration", "performance"],
    )

    res = await coord_service.execute_coordinated_verification(plan, "code", "tests")
    assert res["overall_status"] == "ERROR"
    assert res["agent_reports"]["integration"].status == "ERROR"
    # Ensure error test result was generated
    err_results = [t for t in res["test_results"] if t.status == TestResultStatus.ERROR]
    assert len(err_results) == 1
    assert "Container sandbox crashed" in err_results[0].error_message


# =============================================================================
# Task 1 & 5: LangGraph Pipeline Multi-Agent Invocation & Telemetry
# =============================================================================

@pytest.mark.anyio
async def test_langgraph_pipeline_respects_requested_test_types(monkeypatch):
    """Verifies that verification_pipeline invokes TestCoordinationService and records telemetry."""
    # Mock Docker runner to avoid needing live container for unit test assertions
    mock_runner = MagicMock()
    mock_runner.check_docker_available.return_value = (True, "Ready")
    mock_runner.ensure_runner_image.return_value = (True, "Ready")

    mock_exec_result = SandboxExecutionResult(
        status=TestResultStatus.PASSED,
        exit_code=0,
        stdout="1 passed",
        stderr="",
        duration_ms=45.0,
        test_results=[
            TestResult(test_id="t1", name="test_func", status=TestResultStatus.PASSED, test_type=TestType.UNIT)
        ],
        is_timeout=False,
        no_oracle=False,
        telemetry={"runner": "mock"},
    )
    mock_runner.execute_verification = AsyncMock(return_value=mock_exec_result)

    monkeypatch.setattr("app.workflows.verification_graph.DockerTestRunner", lambda: mock_runner)
    monkeypatch.setattr("app.services.agent_testing_service.DockerTestRunner", lambda: mock_runner)

    state = {
        "submission_id": "sub-langgraph-01",
        "run_id": "run-langgraph-01",
        "source_code": "def hello(): return 'world'",
        "language": "python",
        "filename": "solution.py",
        "trusted_test_cases": "import solution\ndef test_func(): assert solution.hello() == 'world'",
        "timeout_seconds": 15,
        "requested_test_types": ["unit", "performance"],
        "feedback_iterations": [],
        "telemetry": {},
    }

    result = await verification_pipeline.ainvoke(state)

    assert result["status"] == VerificationStatus.PASSED.value
    assert "agent_reports" in result["telemetry"]
    assert "unit" in result["telemetry"]["agent_reports"]
    assert "performance" in result["telemetry"]["agent_reports"]
    assert result["telemetry"]["coordination_plan_id"].startswith("plan-")


@pytest.mark.anyio
async def test_defect_evidence_reaches_xai_and_governance():
    """Confirms that multi-agent defect evidence propagates to XAI, governance, and persistence."""
    run_obj = VerificationRunResponse(
        id="run-defect-evidence-01",
        submission_id="sub-01",
        status=VerificationStatus.FAILED,
        requested_test_types=["unit", "performance"],
        test_results=[
            TestResult(
                test_id="perf-breach-01",
                name="test_performance_sla_compliance",
                status=TestResultStatus.FAILED,
                error_message="Latency threshold breach: 95th percentile latency (350.0ms) exceeded threshold (200.0ms).",
                duration_ms=350.0,
                test_type=TestType.PERFORMANCE,
            )
        ],
        defect_reports=[],
        execution_telemetry={
            "agent_reports": {
                "performance": {
                    "agent_id": "agent-performance-01",
                    "status": "FAILED",
                    "metrics": {"duration_ms": 350.0, "latency_p95_ms": 350.0, "is_breached": True},
                }
            }
        },
    )

    submission_obj = SubmissionResponse(
        id="sub-01",
        code="import time\ndef slow_func(): time.sleep(0.35)",
        language=ProgrammingLanguage.PYTHON,
        filename="solution.py",
    )

    # 1. Defect Analysis extracts performance defect
    defect_service = DefectAnalysisService()
    defects = defect_service.analyze_run(run_obj, submission_obj)
    assert len(defects) == 1
    assert defects[0].defect_category == "performance_bottleneck"
    run_obj.defect_reports = defects

    # 2. XAI Service generates scoped explanation incorporating performance metrics
    xai_service = XaiExplanationService()
    xai_response = xai_service.generate_explanation(run_obj, submission_obj)
    assert xai_response is not None
    assert xai_response.verification_run_id == "run-defect-evidence-01"

    scoped_payload = xai_service.generate_traceability_scoped_explanation(run_obj, defects[0], submission_obj)
    assert scoped_payload.defect_category.value == "performance_bottleneck"
    assert scoped_payload.defect_id == defects[0].defect_id

    # 3. Governance Report marks deployment as BLOCKED due to defect
    gov_service = GovernanceReportService()
    readiness = gov_service.generate_deployment_readiness_report(run_obj, submission_obj)
    assert readiness.is_ready_for_deployment is False
    assert len(readiness.blocking_reasons) >= 1
