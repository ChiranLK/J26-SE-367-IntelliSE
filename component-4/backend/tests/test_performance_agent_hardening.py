"""
Development-Only Verification Suite for Performance Test Agent Hardening (Phase 3B, Tasks 3 & 4).
Tests targeted development fixtures covering:
1. CPU-bound slow algorithms (exponential recursion, quadratic nested loops)
2. Memory-heavy workloads
3. Infinite loops (distinguishing functional hang from performance SLA breaches)
4. Legitimate slow operations (negative controls)
5. Container startup overhead isolation
6. Timeout due to unrelated functional failures
7. Multi-agent taxonomy classification integrity
"""
import asyncio
import pytest
from app.schemas.common import DefectCategory, TestResultStatus, TestType
from app.schemas.verification import TestResult
from app.services.agent_testing_service import PerformanceTestAgent
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.docker_runner import DockerTestRunner, SandboxExecutionResult


class MockRunner(DockerTestRunner):
    """Configurable mock runner for deterministic performance unit testing."""

    def __init__(self, durations=None, is_timeout=False, exit_code=0, error_message=None):
        self._durations = durations or [15.0]
        self._is_timeout = is_timeout
        self._exit_code = exit_code
        self._error_message = error_message

    async def execute_verification(
        self,
        source_code: str,
        trusted_test_cases: str,
        filename: str = "solution.py",
        timeout_seconds: int = 15,
    ) -> SandboxExecutionResult:
        test_results = [
            TestResult(
                test_id=f"t_mock_{idx}",
                name=f"test_workload_{idx}",
                test_type=TestType.PERFORMANCE,
                status=TestResultStatus.TIMEOUT if self._is_timeout else (TestResultStatus.PASSED if d <= 200.0 else TestResultStatus.FAILED),
                duration_ms=d,
                error_message=self._error_message if self._is_timeout else None,
            )
            for idx, d in enumerate(self._durations)
        ]
        total_time = sum(self._durations) + 1200.0  # simulate container startup
        return SandboxExecutionResult(
            status="ERROR" if self._is_timeout else ("FAILED" if any(d > 200.0 for d in self._durations) else "PASSED"),
            exit_code=124 if self._is_timeout else self._exit_code,
            test_results=test_results,
            duration_ms=total_time,
            stdout="",
            stderr="",
            error_message=self._error_message,
            is_timeout=self._is_timeout,
        )


@pytest.mark.anyio
async def test_cpu_bound_slow_algorithms():
    """
    Task 4 Fixture 1: CPU-bound unmemoized recursion and quadratic nested iteration.
    Verifies that PerformanceTestAgent detects the algorithmic scaling bottleneck
    and DefectAnalysisService classifies it as performance_bottleneck.
    """
    # 1. Unmemoized exponential recursion
    exp_code = """
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
"""
    test_code = "import solution\ndef test_fib(): assert solution.fibonacci(32) > 0"
    runner = MockRunner(durations=[350.0])
    agent = PerformanceTestAgent(runner=runner)

    report = await agent.execute_performance_tests(
        source_code=exp_code,
        test_code=test_code,
        latency_threshold_ms=200.0,
    )
    assert report.status == "FAILED"
    assert report.metrics.is_breached is True
    assert report.metrics.latency_p95_ms == 350.0
    assert any("exponential_recursion" in b for b in report.bottlenecks_detected)

    # Classification check
    defect_svc = DefectAnalysisService()
    defects = defect_svc.analyze_test_results(
        run_id="run-exp-01",
        submission_id="sub-exp-01",
        status="FAILED",
        test_results=report.test_results,
        source_code=exp_code,
    )
    assert len(defects) >= 1
    assert defects[0].defect_category == "performance_bottleneck"
    assert defects[0].performance_metrics is not None
    assert "exponential_recursion" in defects[0].performance_metrics["complexity_patterns"]


@pytest.mark.anyio
async def test_memory_heavy_workload():
    """
    Task 4 Fixture 2: Memory-heavy workload accumulating large byte buffers.
    Verifies that repeated buffer allocation is identified as a bottleneck.
    """
    mem_code = """
def generate_buffers(n: int) -> list:
    chunks = []
    for i in range(n):
        buf = bytearray(1024 * 100)  # 100 KB chunks
        chunks.append(buf)
    return chunks
"""
    test_code = "import solution\ndef test_mem(): assert len(solution.generate_buffers(5000)) == 5000"
    runner = MockRunner(durations=[280.0])
    agent = PerformanceTestAgent(runner=runner)

    report = await agent.execute_performance_tests(
        source_code=mem_code,
        test_code=test_code,
        latency_threshold_ms=200.0,
    )
    assert report.status == "FAILED"
    assert report.metrics.is_breached is True
    assert report.metrics.latency_p95_ms == 280.0

    defect_svc = DefectAnalysisService()
    defects = defect_svc.analyze_test_results(
        run_id="run-mem-01",
        submission_id="sub-mem-01",
        status="FAILED",
        test_results=report.test_results,
        source_code=mem_code,
    )
    assert len(defects) >= 1
    assert defects[0].defect_category == "performance_bottleneck"


def test_infinite_loop_classified_as_functional_bug():
    """
    Task 4 Fixture 3: An infinite loop in a functional unit test.
    Crucial Rule: Do NOT classify every timeout automatically as a performance defect.
    A timeout in a non-performance unit test must be classified as functional_bug.
    """
    inf_loop_code = """
def find_item(items, target):
    idx = 0
    while idx < len(items):
        if items[idx] == target:
            return idx
        # Defect: forgot idx += 1 -> infinite loop!
    return -1
"""
    unit_timeout_test = TestResult(
        test_id="t-unit-timeout-01",
        name="test_find_item_unit",
        test_type=TestType.UNIT,  # Regular unit test!
        status=TestResultStatus.TIMEOUT,
        error_message="Execution timed out after 15 seconds",
        duration_ms=15000.0,
    )
    defect_svc = DefectAnalysisService()
    defects = defect_svc.analyze_test_results(
        run_id="run-inf-loop-01",
        submission_id="sub-inf-loop-01",
        status="FAILED",
        test_results=[unit_timeout_test],
        source_code=inf_loop_code,
    )
    assert len(defects) == 1
    assert defects[0].defect_category == "functional_bug"
    assert defects[0].failure_category == "TIMEOUT_ERROR"
    assert "timeout" in defects[0].description.lower() or "pytest" in defects[0].description.lower()


@pytest.mark.anyio
async def test_legitimate_slow_operation_negative_control():
    """
    Task 4 Fixture 4: Legitimate operation running within acceptable limits (<200ms).
    Ensures negative controls remain present and zero false-positive performance alerts occur.
    """
    clean_code = """
def linear_sum(numbers: list[int]) -> int:
    # Efficient O(N) single-pass sum
    total = 0
    for num in numbers:
        total += num
    return total
"""
    test_code = "import solution\ndef test_sum(): assert solution.linear_sum(list(range(50000))) > 0"
    runner = MockRunner(durations=[12.0])  # Fast 12ms
    agent = PerformanceTestAgent(runner=runner)

    report = await agent.execute_performance_tests(
        source_code=clean_code,
        test_code=test_code,
        latency_threshold_ms=200.0,
    )
    assert report.status == "PASSED"
    assert report.metrics.is_breached is False
    assert len(report.bottlenecks_detected) == 0

    defect_svc = DefectAnalysisService()
    defects = defect_svc.analyze_test_results(
        run_id="run-clean-perf-01",
        submission_id="sub-clean-perf-01",
        status="PASSED",
        test_results=report.test_results,
        source_code=clean_code,
    )
    assert len(defects) == 0


@pytest.mark.anyio
async def test_container_startup_overhead_isolated():
    """
    Task 4 Fixture 5: Isolates container startup overhead (~1.5s) from code duration.
    Verifies that container startup latency is not conflated with code latency.
    """
    fast_code = "def fast_op(): return 42"
    test_code = "import solution\ndef test_fast(): assert solution.fast_op() == 42"
    # Code takes 2ms, but total container wall time is 1850ms
    runner = MockRunner(durations=[2.0])
    agent = PerformanceTestAgent(runner=runner)

    report = await agent.execute_performance_tests(
        source_code=fast_code,
        test_code=test_code,
        latency_threshold_ms=200.0,
    )
    assert report.status == "PASSED"
    assert report.metrics.is_breached is False
    assert report.metrics.latency_p95_ms == 2.0  # pure code time!
    assert report.metrics.workload_duration_ms == 2.0
    assert report.metrics.container_startup_overhead_ms >= 1000.0


def test_timeout_due_to_unrelated_syntax_failure():
    """
    Task 4 Fixture 6: Unrelated syntax error or immediate crash.
    Verifies that syntax and import crashes are not falsely attributed to performance.
    """
    syntax_err_test = TestResult(
        test_id="t-syntax-01",
        name="test_syntax",
        test_type=TestType.UNIT,
        status=TestResultStatus.FAILED,
        error_message="SyntaxError: invalid syntax",
        stack_trace="SyntaxError: invalid syntax at line 3",
        duration_ms=1.0,
    )
    defect_svc = DefectAnalysisService()
    defects = defect_svc.analyze_test_results(
        run_id="run-syntax-01",
        submission_id="sub-syntax-01",
        status="FAILED",
        test_results=[syntax_err_test],
        source_code="def broken_syntax(:\n    pass\n",
    )
    assert len(defects) == 1
    assert defects[0].defect_category == "functional_bug"
    assert defects[0].failure_category == "SYNTAX_ERROR"
