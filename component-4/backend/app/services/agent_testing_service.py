import ast
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging import logger
from app.schemas.common import TestResultStatus, TestType
from app.schemas.research_reports import (
    IntegrationTestReport,
    MultiAgentCoordinationPlan,
    PerformanceMetrics,
    PerformanceTestReport,
    UnitTestReport,
)
from app.schemas.test_result import TestResult
from app.services.docker_runner import DockerTestRunner, SandboxExecutionResult


def _project_files_for_test_type(
    project_files: Optional[Dict[str, str]],
    test_type: str,
) -> Optional[Dict[str, str]]:
    """Select explicitly categorized tests while retaining all application files.

    Projects may place trusted tests below ``tests/unit``, ``tests/integration``,
    and ``tests/performance`` (or use a matching ``test_<type>_`` filename).
    When that convention is present, each agent executes only its authorized
    category. Projects without categorized tests retain the legacy behaviour.
    """
    if not project_files:
        return project_files

    def is_test_file(path: str) -> bool:
        normalized = path.replace("\\", "/").lower()
        basename = normalized.rsplit("/", 1)[-1]
        return normalized.endswith(".py") and (
            basename.startswith("test_") or "/tests/" in f"/{normalized}"
        )

    def category(path: str) -> Optional[str]:
        normalized = path.replace("\\", "/").lower()
        basename = normalized.rsplit("/", 1)[-1]
        for candidate in ("unit", "integration", "performance"):
            if (
                f"/tests/{candidate}/" in f"/{normalized}"
                or basename.startswith(f"test_{candidate}_")
            ):
                return candidate
        return None

    categorized_tests = {
        path: category(path)
        for path in project_files
        if is_test_file(path) and category(path) is not None
    }
    if not categorized_tests:
        return project_files

    return {
        path: content
        for path, content in project_files.items()
        if not is_test_file(path) or categorized_tests.get(path) == test_type
    }


def _categorized_project_tests(
    project_files: Optional[Dict[str, str]], test_type: str
) -> List[str]:
    """Return trusted project test files explicitly assigned to one test category."""
    matches: List[str] = []
    for path in (project_files or {}):
        normalized = path.replace("\\", "/").lower()
        basename = normalized.rsplit("/", 1)[-1]
        if not normalized.endswith(".py"):
            continue
        if f"/tests/{test_type}/" in f"/{normalized}" or basename.startswith(f"test_{test_type}_"):
            matches.append(path)
    return matches


def _has_any_categorized_project_tests(project_files: Optional[Dict[str, str]]) -> bool:
    return any(
        _categorized_project_tests(project_files, category)
        for category in ("unit", "integration", "performance")
    )


def _explicit_suite_supports(test_code: str, test_type: str) -> bool:
    """Conservatively classify a standalone trusted suite by its declared intent."""
    code = test_code or ""
    if not code.strip():
        return False
    if test_type == "unit":
        return bool(re.search(r"def\s+test_|\bassert\b|pytest\.", code))
    if test_type == "integration":
        return bool(re.search(r"integration|pytest\.mark\.integration", code, re.IGNORECASE))
    return bool(re.search(r"performance|benchmark|latency|throughput|elapsed", code, re.IGNORECASE))


class UnitTestAgent:
    """
    Dedicated agent responsible for function-level unit test generation and execution (SO1).
    Tests individual functions/methods in isolation.
    """

    AGENT_ID = "agent-unit-01"

    def __init__(self, runner: Optional[DockerTestRunner] = None):
        self.runner = runner or DockerTestRunner()

    def parse_contracts(
        self,
        tree: ast.AST,
        explicit_specs: Optional[Dict[str, Any]] = None,
        trust_submitted_docstrings: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Extracts test contracts from function docstrings and explicit specifications (SO1, FR01).
        By default, docstrings from submitted untrusted code are marked as UNVERIFIED_SUGGESTION
        and not trusted as acceptance oracles without explicit authorization.
        Authoritative expected outcomes must be sourced from explicit specifications,
        trusted test suites, or verified requirements.
        """
        contracts = []

        # 1. Authoritative explicit specifications dictionary
        if explicit_specs:
            for fn_name, cases in explicit_specs.items():
                if isinstance(cases, list):
                    for case in cases:
                        contracts.append({
                            "function": fn_name,
                            "args": case.get("args", ""),
                            "expected": case.get("expected"),
                            "raises": case.get("raises"),
                            "source": "explicit_specification",
                            "is_trusted": True,
                            "trust_status": "AUTHORITATIVE",
                        })

        # 2. Extract from docstrings in AST (untrusted submitted code)
        docstring_trust_status = "AUTHORITATIVE_PROMOTED" if trust_submitted_docstrings else "UNVERIFIED_SUGGESTION"
        is_docstring_trusted = bool(trust_submitted_docstrings)

        for node in getattr(tree, "body", []):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                fn_name = node.name
                docstring = ast.get_docstring(node) or ""
                if not docstring:
                    continue

                # Match doctests: e.g. ">>> func_name(args)\nexpected_output"
                doctest_pattern = re.compile(
                    r">>>\s*" + re.escape(fn_name) + r"\((.*?)\)\s*\n\s*([^\n>]+)"
                )
                for m in doctest_pattern.finditer(docstring):
                    args_str = m.group(1).strip()
                    exp_str = m.group(2).strip()
                    contracts.append({
                        "function": fn_name,
                        "args": args_str,
                        "expected": exp_str,
                        "raises": None,
                        "source": "docstring_doctest",
                        "is_trusted": is_docstring_trusted,
                        "trust_status": docstring_trust_status,
                    })

                # Match Contract lines: e.g. "Contract: func(args) -> expected" or "== expected"
                contract_pattern = re.compile(
                    r"Contract:\s*" + re.escape(fn_name) + r"\((.*?)\)\s*(?:->|==)\s*([^\n#]+)",
                    re.IGNORECASE,
                )
                for m in contract_pattern.finditer(docstring):
                    args_str = m.group(1).strip()
                    exp_str = m.group(2).strip()
                    contracts.append({
                        "function": fn_name,
                        "args": args_str,
                        "expected": exp_str,
                        "raises": None,
                        "source": "docstring_contract",
                        "is_trusted": is_docstring_trusted,
                        "trust_status": docstring_trust_status,
                    })

                # Match Exception Contracts: e.g. "Contract: func(args) raises ExceptionName"
                raises_pattern = re.compile(
                    r"Contract:\s*" + re.escape(fn_name) + r"\((.*?)\)\s*raises\s+([a-zA-Z0-9_]+)",
                    re.IGNORECASE,
                )
                for m in raises_pattern.finditer(docstring):
                    args_str = m.group(1).strip()
                    exc_name = m.group(2).strip()
                    contracts.append({
                        "function": fn_name,
                        "args": args_str,
                        "expected": None,
                        "raises": exc_name,
                        "source": "docstring_contract_exception",
                        "is_trusted": is_docstring_trusted,
                        "trust_status": docstring_trust_status,
                    })

        return contracts

    def generate_autonomous_unit_test_suite(
        self,
        source_code: str,
        filename: str = "solution.py",
        specifications: Optional[Dict[str, Any]] = None,
        trust_submitted_docstrings: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Autonomously generates unit test cases for functions discovered in source code (SO1, FR01).
        Authoritative boundary oracles are strictly sourced from verified explicit specifications
        or authorized requirements.
        Docstrings in submitted untrusted code are treated as unverified suggestions and are NOT
        promoted to trusted acceptance oracles unless explicitly authorized.
        """
        try:
            tree = ast.parse(source_code)
        except Exception as exc:
            logger.warning("AST parse failed during autonomous unit test generation: %s", exc)
            return "", {
                "error": str(exc),
                "meaningful_oracle_available": False,
                "specification_source": "none",
                "trust_status": "NO_SPECIFICATION",
                "contracts_found": 0,
            }

        functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")]
        if not functions:
            return "", {
                "meaningful_oracle_available": False,
                "reason": "No functions found in AST",
                "specification_source": "none",
                "trust_status": "NO_SPECIFICATION",
                "contracts_found": 0,
            }

        module_name = filename.replace(".py", "") if filename.endswith(".py") else "solution"
        contracts = self.parse_contracts(
            tree,
            explicit_specs=specifications,
            trust_submitted_docstrings=trust_submitted_docstrings,
        )

        trusted_contracts = [c for c in contracts if c.get("is_trusted", False)]
        unverified_suggestions = [c for c in contracts if not c.get("is_trusted", False)]

        test_lines = [
            f"# ==============================================================================",
            f"# AUTONOMOUSLY GENERATED UNIT TEST SUITE — AGENT ID: {self.AGENT_ID}",
            f"# Provenance: UnitTestAgent AST Specification & Contract Extractor",
            f"# ==============================================================================",
            "import pytest",
            f"import {module_name}",
            "",
        ]

        generated_count = 0
        functions_with_contracts = set()

        # 1. Generate trusted acceptance assertions from authoritative contracts
        if trusted_contracts:
            for idx, c in enumerate(trusted_contracts, start=1):
                fn = c["function"]
                functions_with_contracts.add(fn)
                args = c["args"]
                generated_count += 1
                if c.get("raises"):
                    test_lines.extend([
                        f"def test_gen_boundary_{fn}_raises_{idx}():",
                        f"    '''Autonomous boundary exception test derived from AUTHORITATIVE {c['source']}.'''",
                        f"    with pytest.raises({c['raises']}):",
                        f"        {module_name}.{fn}({args})",
                        "",
                    ])
                else:
                    test_lines.extend([
                        f"def test_gen_boundary_{fn}_{idx}():",
                        f"    '''Autonomous boundary oracle test derived from AUTHORITATIVE {c['source']}.'''",
                        f"    assert {module_name}.{fn}({args}) == {c['expected']}",
                        "",
                    ])

        # 2. For functions without authoritative specifications, generate distinguishable presence/callable checks
        # If unverified suggestions exist, record them in docstrings without promoting to acceptance assertions
        for fn in functions:
            if fn not in functions_with_contracts:
                generated_count += 1
                unverified_fn_suggestions = [s for s in unverified_suggestions if s["function"] == fn]
                if unverified_fn_suggestions:
                    note = (
                        f"Meaningful authoritative oracle unavailable. "
                        f"Found {len(unverified_fn_suggestions)} unverified docstring suggestion(s) in untrusted code; "
                        f"not authorized as acceptance oracle."
                    )
                else:
                    note = f"Meaningful boundary oracle unavailable without trusted specification for '{fn}'."

                test_lines.extend([
                    f"def test_{fn}_callable():",
                    f"    '''Autonomous presence check. NOTE: {note}'''",
                    f"    assert hasattr({module_name}, '{fn}')",
                    f"    assert callable(getattr({module_name}, '{fn}'))",
                    "",
                ])

        test_suite_code = "\n".join(test_lines)

        # Determine specification provenance
        if specifications:
            spec_source = "explicit_specification"
            trust_status = "AUTHORITATIVE"
        elif trust_submitted_docstrings and contracts:
            spec_source = "submitted_docstring_authorized"
            trust_status = "AUTHORITATIVE_PROMOTED"
        elif unverified_suggestions:
            spec_source = "submitted_docstring_unverified"
            trust_status = "UNVERIFIED_SUGGESTION"
        else:
            spec_source = "none"
            trust_status = "NO_SPECIFICATION"

        meaningful_oracle_available = len(trusted_contracts) > 0

        provenance = {
            "agent_id": self.AGENT_ID,
            "specification_source": spec_source,
            "trust_status": trust_status,
            "meaningful_oracle_available": meaningful_oracle_available,
            "contracts_found": len(trusted_contracts) + len(unverified_suggestions),
            "authoritative_contracts_count": len(trusted_contracts),
            "unverified_suggestions_count": len(unverified_suggestions),
            "unverified_suggestions": [
                {"function": s["function"], "args": s["args"], "expected": s.get("expected"), "source": s["source"]}
                for s in unverified_suggestions
            ],
            "functions_covered": sorted(list(set(functions))),
            "functions_with_contracts": sorted(list(functions_with_contracts)),
            "generated_test_count": generated_count,
            "provenance_tag": (
                "UnitTestAgent:Authoritative_Specification" if trusted_contracts
                else ("UnitTestAgent:Unverified_Docstring_Suggestions_Only" if unverified_suggestions
                else "UnitTestAgent:Callable_Only_Fallback")
            ),
        }
        return test_suite_code, provenance

    def generate_autonomous_unit_tests(
        self,
        source_code: str,
        filename: str = "solution.py",
        specifications: Optional[Dict[str, Any]] = None,
        trust_submitted_docstrings: bool = False,
    ) -> str:
        """Backward-compatible helper returning synthesized test suite string."""
        suite_code, _ = self.generate_autonomous_unit_test_suite(
            source_code,
            filename,
            specifications,
            trust_submitted_docstrings=trust_submitted_docstrings,
        )
        return suite_code

    async def execute_unit_tests(
        self,
        source_code: str,
        test_code: str,
        filename: str = "solution.py",
        timeout_seconds: int = 15,
        specifications: Optional[Dict[str, Any]] = None,
        trust_submitted_docstrings: bool = False,
        project_files: Optional[Dict[str, str]] = None,
    ) -> UnitTestReport:
        """Executes unit tests in the container sandbox and compiles unit test report."""
        effective_test_code = test_code
        generated_code = None
        provenance = None
        meaningful_oracle = False

        categorized = _has_any_categorized_project_tests(project_files)
        has_project_oracle = bool(_categorized_project_tests(project_files, "unit")) if categorized else bool(
            project_files and any(
                f.endswith(".py") and (os.path.basename(f).startswith("test_") or "/tests/" in f"/{f}")
                for f in project_files
            )
        )

        # Explicit specifications may generate authoritative assertions. Without them,
        # callable/presence checks are not accepted as verification evidence.
        if not (effective_test_code or "").strip() and not (
            has_project_oracle
        ) and specifications:
            generated_code, provenance = self.generate_autonomous_unit_test_suite(
                source_code=source_code,
                filename=filename,
                specifications=specifications,
                trust_submitted_docstrings=trust_submitted_docstrings,
            )
            effective_test_code = generated_code
            meaningful_oracle = provenance.get("meaningful_oracle_available", False)

        if not has_project_oracle and not _explicit_suite_supports(effective_test_code, "unit") and not meaningful_oracle:
            return UnitTestReport(
                agent_id=self.AGENT_ID,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                duration_ms=0.0,
                test_results=[],
                functions_covered=[],
                generated_test_count=0,
                generated_test_code=None,
                meaningful_oracle_available=False,
                specification_source="none",
                trust_status="NOT_CONFIGURED",
                generation_provenance={"reason": "No authorized unit-test assertions were supplied."},
                status="NOT_EXECUTED",
            )

        start_time = time.perf_counter()
        exec_kwargs = {
            "source_code": source_code,
            "trusted_test_cases": effective_test_code,
            "filename": filename,
            "timeout_seconds": timeout_seconds,
        }
        if project_files is not None:
            exec_kwargs["project_files"] = _project_files_for_test_type(project_files, "unit")
        exec_result: SandboxExecutionResult = await self.runner.execute_verification(**exec_kwargs)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Filter and tag test results as UNIT
        unit_results = []
        functions_covered = set()
        for tr in exec_result.test_results:
            if tr.test_id == "ast_syntax_check" or "ast_syntax_check" in tr.test_id:
                continue
            tr.test_type = TestType.UNIT
            tr.test_id = f"unit::{tr.test_id}"
            unit_results.append(tr)
            match = re.search(r"test_(?:gen_boundary_|gen_callable_)?([a-zA-Z0-9_]+)", tr.name or "")
            if match:
                functions_covered.add(match.group(1))

        passed = sum(1 for t in unit_results if t.status == TestResultStatus.PASSED)
        failed = sum(1 for t in unit_results if t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR, TestResultStatus.TIMEOUT))

        if exec_result.is_timeout or exec_result.status == TestResultStatus.ERROR.value:
            overall_status = "ERROR"
        elif (exec_result.no_oracle and not meaningful_oracle) or not unit_results:
            overall_status = "NOT_EXECUTED"
        elif failed == 0 and passed > 0:
            overall_status = "PASSED"
        else:
            overall_status = "FAILED"

        spec_source = provenance.get("specification_source") if provenance else ("trusted_test_suite" if (test_code or "").strip() else "none")
        trust_status_val = provenance.get("trust_status") if provenance else ("AUTHORITATIVE" if (test_code or "").strip() else "NO_SPECIFICATION")

        return UnitTestReport(
            agent_id=self.AGENT_ID,
            total_tests=len(unit_results),
            passed_tests=passed,
            failed_tests=failed,
            duration_ms=duration_ms,
            test_results=unit_results,
            functions_covered=sorted(list(functions_covered)),
            generated_test_count=provenance.get("generated_test_count", 0) if provenance else 0,
            generated_test_code=generated_code,
            meaningful_oracle_available=meaningful_oracle or bool((test_code or "").strip()),
            specification_source=spec_source,
            trust_status=trust_status_val,
            generation_provenance=provenance,
            status=overall_status,
        )


class IntegrationTestAgent:
    """
    Dedicated agent responsible for testing interactions between modules, APIs,
    and dependency injection / mockable test-seam boundaries (SO1).
    """

    AGENT_ID = "agent-integration-01"

    def __init__(self, runner: Optional[DockerTestRunner] = None):
        self.runner = runner or DockerTestRunner()

    def discover_test_seams(self, source_code: str) -> List[str]:
        """Discovers mockable entry points, imported modules, and API seams via AST."""
        seams = []
        try:
            tree = ast.parse(source_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        seams.append(f"module:{alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    seams.append(f"package:{node.module}")
                elif isinstance(node, ast.ClassDef):
                    seams.append(f"class:{node.name}")
        except Exception:
            pass
        return seams

    async def execute_integration_tests(
        self,
        source_code: str,
        test_code: str,
        filename: str = "solution.py",
        timeout_seconds: int = 20,
        project_files: Optional[Dict[str, str]] = None,
        require_category_marker: bool = False,
    ) -> IntegrationTestReport:
        """Executes multi-module integration test suites against component seams."""
        start_time = time.perf_counter()
        seams = self.discover_test_seams(source_code)

        categorized = _has_any_categorized_project_tests(project_files)
        has_project_oracle = bool(_categorized_project_tests(project_files, "integration")) if categorized else False
        has_explicit_oracle = _explicit_suite_supports(test_code, "integration") if require_category_marker else bool((test_code or "").strip())
        if not has_project_oracle and not has_explicit_oracle:
            return IntegrationTestReport(
                agent_id=self.AGENT_ID,
                total_interactions=0,
                passed_interactions=0,
                failed_interactions=0,
                duration_ms=0.0,
                test_results=[],
                test_seams_verified=seams,
                status="NOT_EXECUTED",
            )

        exec_kwargs = {
            "source_code": source_code,
            "trusted_test_cases": test_code,
            "filename": filename,
            "timeout_seconds": timeout_seconds,
        }
        if project_files is not None:
            exec_kwargs["project_files"] = _project_files_for_test_type(project_files, "integration")
        exec_result: SandboxExecutionResult = await self.runner.execute_verification(**exec_kwargs)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        integration_results = []
        for tr in exec_result.test_results:
            if tr.test_id == "ast_syntax_check" or "ast_syntax_check" in tr.test_id:
                continue
            tr.test_type = TestType.INTEGRATION
            tr.test_id = f"integration::{tr.test_id}"
            integration_results.append(tr)

        passed = sum(1 for t in integration_results if t.status == TestResultStatus.PASSED)
        failed = sum(1 for t in integration_results if t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR, TestResultStatus.TIMEOUT))

        if exec_result.is_timeout or exec_result.status == TestResultStatus.ERROR.value:
            overall_status = "ERROR"
        elif exec_result.no_oracle or not integration_results:
            overall_status = "NOT_EXECUTED"
        elif failed == 0 and passed > 0:
            overall_status = "PASSED"
        else:
            overall_status = "FAILED"

        return IntegrationTestReport(
            agent_id=self.AGENT_ID,
            total_interactions=len(integration_results),
            passed_interactions=passed,
            failed_interactions=failed,
            duration_ms=duration_ms,
            test_results=integration_results,
            test_seams_verified=seams,
            status=overall_status,
        )


class PerformanceTestAgent:
    """
    Dedicated agent responsible for executing controlled workloads, measuring latency
    and throughput, detecting threshold breaches, and localizing bottlenecks (SO1).
    """

    AGENT_ID = "agent-performance-01"

    def __init__(self, runner: Optional[DockerTestRunner] = None):
        self.runner = runner or DockerTestRunner()

    def build_performance_benchmark_wrapper(
        self,
        module_name: str,
        target_function: str,
        call_args: str = "",
        iterations: int = 10,
    ) -> str:
        """Builds an isolated micro-benchmark script measuring latency percentiles."""
        return f"""
import time
import json
import statistics
import {module_name}

latencies = []
for _ in range({iterations}):
    t0 = time.perf_counter()
    getattr({module_name}, '{target_function}')({call_args})
    t1 = time.perf_counter()
    latencies.append((t1 - t0) * 1000.0)

latencies.sort()
p50 = statistics.median(latencies)
p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]
p99 = latencies[-1]
mean_l = statistics.mean(latencies)
total_duration = sum(latencies)
rps = ({iterations} / (total_duration / 1000.0)) if total_duration > 0 else 0

output = {{
    "sample_size": {iterations},
    "duration_ms": round(total_duration, 2),
    "mean_latency_ms": round(mean_l, 3),
    "latency_p50_ms": round(p50, 3),
    "latency_p95_ms": round(p95, 3),
    "latency_p99_ms": round(p99, 3),
    "max_latency_ms": round(latencies[-1], 3),
    "throughput_rps": round(rps, 2)
}}
print("---BENCHMARK_OUTPUT_START---")
print(json.dumps(output))
print("---BENCHMARK_OUTPUT_END---")
"""

    async def execute_performance_tests(
        self,
        source_code: str,
        test_code: str,
        filename: str = "solution.py",
        latency_threshold_ms: float = 200.0,
        iterations: int = 10,
        project_files: Optional[Dict[str, str]] = None,
        require_category_marker: bool = False,
    ) -> PerformanceTestReport:
        """
        Executes controlled workload against source code, measures latency percentiles,
        and flags threshold breaches.
        """
        categorized = _has_any_categorized_project_tests(project_files)
        has_project_oracle = bool(_categorized_project_tests(project_files, "performance")) if categorized else False
        has_explicit_oracle = _explicit_suite_supports(test_code, "performance") if require_category_marker else bool((test_code or "").strip())
        if not has_project_oracle and not has_explicit_oracle:
            return PerformanceTestReport(
                agent_id=self.AGENT_ID,
                metrics=PerformanceMetrics(
                    sample_size=0, duration_ms=0.0, workload_duration_ms=0.0,
                    container_startup_overhead_ms=0.0, mean_latency_ms=0.0,
                    latency_p50_ms=0.0, latency_p95_ms=0.0, latency_p99_ms=0.0,
                    max_latency_ms=0.0, throughput_rps=0.0,
                    threshold_latency_ms=latency_threshold_ms, is_breached=False,
                ),
                bottlenecks_detected=["No authorized performance workload or threshold assertion was supplied."],
                test_results=[],
                status="NOT_EXECUTED",
            )

        start_time = time.perf_counter()
        exec_kwargs = {
            "source_code": source_code,
            "trusted_test_cases": test_code,
            "filename": filename,
            "timeout_seconds": 25,
        }
        if project_files is not None:
            exec_kwargs["project_files"] = _project_files_for_test_type(project_files, "performance")
        exec_result: SandboxExecutionResult = await self.runner.execute_verification(**exec_kwargs)
        measured_wall_ms = round((time.perf_counter() - start_time) * 1000, 2)
        total_time_ms = round(exec_result.duration_ms if (exec_result.duration_ms and exec_result.duration_ms > 0) else measured_wall_ms, 2)

        # Inspect AST workload complexity patterns for evidence-grounded performance diagnosis
        complexity_patterns = []
        try:
            from app.services.defect_analysis_service import DefectAnalysisService
            complexity_patterns = DefectAnalysisService().inspect_workload_complexity_patterns(source_code)
        except Exception as exc:
            logger.debug("Workload complexity inspection failed: %s", exc)

        # Parse test durations to compute latency statistics
        durations = [t.duration_ms for t in exec_result.test_results if t.duration_ms is not None]
        if not durations:
            durations = [total_time_ms]

        durations.sort()
        count = len(durations)
        mean_l = sum(durations) / count
        p50 = durations[count // 2]
        p95_idx = min(int(count * 0.95), count - 1)
        p95 = durations[p95_idx]
        p99 = durations[-1]
        throughput_rps = round((count / (sum(durations) / 1000.0)), 2) if sum(durations) > 0 else 0.0

        # Separate container startup overhead from raw code duration using independently measured execution intervals
        workload_duration_ms = round(sum(durations), 2)
        container_overhead_ms = round(max(0.0, total_time_ms - workload_duration_ms), 2)

        # Breach condition: empirical SLA threshold breach, timeout under performance load,
        # or confirmed algorithmic complexity pattern with elevated workload execution duration (>= 50.0ms or scale test failure).
        # Container startup overhead is explicitly excluded from triggering breaches.
        is_breached = (
            p95 > latency_threshold_ms
            or exec_result.is_timeout
            or exec_result.status == TestResultStatus.FAILED.value
            or (len(complexity_patterns) > 0 and (p95 >= 50.0 or exec_result.status == TestResultStatus.FAILED.value))
        )

        bottlenecks = []
        if is_breached:
            if p95 > latency_threshold_ms:
                bottlenecks.append(
                    f"Latency SLA threshold breach: 95th percentile latency ({p95:.1f}ms) exceeded maximum allowable threshold ({latency_threshold_ms:.1f}ms)."
                )
            if complexity_patterns:
                pat_descs = [f"{p['pattern']} ({p['complexity']})" for p in complexity_patterns]
                bottlenecks.append(
                    f"Algorithmic bottleneck identified: {', '.join(pat_descs)} resulting in elevated execution latency ({p95:.1f}ms)."
                )
            if exec_result.is_timeout:
                bottlenecks.append("Execution timed out under performance workload: potential non-terminating loop or catastrophic algorithmic scaling.")
            if exec_result.status == TestResultStatus.FAILED.value and not exec_result.is_timeout:
                bottlenecks.append("An authorized performance assertion failed in the submitted performance test suite.")

        metrics = PerformanceMetrics(
            sample_size=count,
            duration_ms=workload_duration_ms,
            workload_duration_ms=workload_duration_ms,
            container_startup_overhead_ms=container_overhead_ms,
            mean_latency_ms=round(mean_l, 2),
            latency_p50_ms=round(p50, 2),
            latency_p95_ms=round(p95, 2),
            latency_p99_ms=round(p99, 2),
            max_latency_ms=round(durations[-1], 2),
            throughput_rps=throughput_rps,
            threshold_latency_ms=latency_threshold_ms,
            is_breached=is_breached,
        )

        status = "FAILED" if is_breached else "PASSED"
        if exec_result.is_timeout:
            # Under performance testing, a timeout is an empirical failure (catastrophic scaling or hang under load)
            status = "FAILED"
        elif exec_result.status == TestResultStatus.ERROR.value and not exec_result.test_results:
            status = "ERROR"

        perf_test_results = []
        for tr in exec_result.test_results:
            tr.test_type = TestType.PERFORMANCE
            tr.test_id = f"performance::{tr.test_id}"
            perf_test_results.append(tr)
        if status == "ERROR":
            perf_test_results.append(
                TestResult(
                    test_id=f"perf-sla-{uuid.uuid4().hex[:8]}",
                    name="test_performance_sla_compliance",
                    status=TestResultStatus.ERROR,
                    error_message=exec_result.error_message or "Execution failed with container infrastructure error.",
                    duration_ms=total_time_ms,
                    test_type=TestType.PERFORMANCE,
                )
            )
        elif status == "FAILED":
            perf_test_results.append(
                TestResult(
                    test_id=f"perf-sla-{uuid.uuid4().hex[:8]}",
                    name="test_performance_sla_compliance",
                    status=TestResultStatus.TIMEOUT if exec_result.is_timeout else TestResultStatus.FAILED,
                    error_message="; ".join(bottlenecks),
                    duration_ms=p95,
                    test_type=TestType.PERFORMANCE,
                )
            )
        else:
            perf_test_results.append(
                TestResult(
                    test_id=f"perf-sla-{uuid.uuid4().hex[:8]}",
                    name="test_performance_sla_compliance",
                    status=TestResultStatus.PASSED,
                    duration_ms=p95,
                    test_type=TestType.PERFORMANCE,
                )
            )

        return PerformanceTestReport(
            agent_id=self.AGENT_ID,
            metrics=metrics,
            bottlenecks_detected=bottlenecks,
            test_results=perf_test_results,
            status=status,
        )


class TestCoordinationService:
    """
    Coordinates Unit, Integration, and Performance Test Agents against a shared test plan (SO1, FR02).
    """

    __test__ = False

    def __init__(self, runner: Optional[DockerTestRunner] = None):
        self.runner = runner or DockerTestRunner()
        self.unit_agent = UnitTestAgent(self.runner)
        self.integration_agent = IntegrationTestAgent(self.runner)
        self.performance_agent = PerformanceTestAgent(self.runner)

    def create_coordination_plan(
        self,
        run_id: str,
        source_code: str,
        requested_test_types: Optional[List[str]] = None,
        latency_threshold_ms: float = 200.0,
    ) -> MultiAgentCoordinationPlan:
        """Constructs a shared test plan assigning scopes to each specialized agent."""
        test_types = requested_test_types or ["unit", "integration", "performance"]
        seams = self.integration_agent.discover_test_seams(source_code)
        return MultiAgentCoordinationPlan(
            plan_id=f"plan-{uuid.uuid4().hex[:12]}",
            verification_run_id=run_id,
            assigned_agents=test_types,
            test_seams=seams,
            nfr_latency_threshold_ms=latency_threshold_ms,
        )

    async def execute_coordinated_verification(
        self,
        plan: MultiAgentCoordinationPlan,
        source_code: str,
        test_code: str,
        filename: str = "solution.py",
        timeout_seconds: int = 25,
        specifications: Optional[Dict[str, Any]] = None,
        project_files: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes agents according to the shared coordination plan and merges results.
        Safely captures agent failures, timeouts, and execution errors.
        Supports multi-file projects through project_files.
        """
        agent_reports = {}
        all_test_results = []

        # 1. Unit Test Agent
        if "unit" in plan.assigned_agents:
            try:
                unit_rep = await self.unit_agent.execute_unit_tests(
                    source_code=source_code,
                    test_code=test_code,
                    filename=filename,
                    timeout_seconds=timeout_seconds,
                    specifications=specifications,
                    project_files=project_files,
                )
                agent_reports["unit"] = unit_rep
                all_test_results.extend(unit_rep.test_results)
            except Exception as exc:
                logger.error("UnitTestAgent execution failed: %s", exc, exc_info=True)
                err_result = TestResult(
                    test_id=f"unit-err-{uuid.uuid4().hex[:8]}",
                    name="unit_agent_execution",
                    status=TestResultStatus.ERROR,
                    error_message=f"UnitTestAgent encountered an unhandled error: {exc}",
                    test_type=TestType.UNIT,
                )
                all_test_results.append(err_result)
                agent_reports["unit"] = UnitTestReport(
                    agent_id=self.unit_agent.AGENT_ID,
                    total_tests=1,
                    passed_tests=0,
                    failed_tests=1,
                    duration_ms=0.0,
                    test_results=[err_result],
                    status="ERROR",
                )

        # 2. Integration Test Agent
        if "integration" in plan.assigned_agents:
            try:
                integ_rep = await self.integration_agent.execute_integration_tests(
                    source_code=source_code,
                    test_code=test_code,
                    filename=filename,
                    timeout_seconds=timeout_seconds,
                    project_files=project_files,
                    require_category_marker=True,
                )
                agent_reports["integration"] = integ_rep
                # Unit and integration agents intentionally execute independently.
                # Preserve both evidence sets even when pytest node names match.
                all_test_results.extend(integ_rep.test_results)
            except Exception as exc:
                logger.error("IntegrationTestAgent execution failed: %s", exc, exc_info=True)
                err_result = TestResult(
                    test_id=f"integ-err-{uuid.uuid4().hex[:8]}",
                    name="integration_agent_execution",
                    status=TestResultStatus.ERROR,
                    error_message=f"IntegrationTestAgent encountered an unhandled error: {exc}",
                    test_type=TestType.INTEGRATION,
                )
                all_test_results.append(err_result)
                agent_reports["integration"] = IntegrationTestReport(
                    agent_id=self.integration_agent.AGENT_ID,
                    total_interactions=1,
                    passed_interactions=0,
                    failed_interactions=1,
                    duration_ms=0.0,
                    test_results=[err_result],
                    test_seams_verified=[],
                    status="ERROR",
                )

        # 3. Performance Test Agent
        if "performance" in plan.assigned_agents:
            try:
                perf_rep = await self.performance_agent.execute_performance_tests(
                    source_code=source_code,
                    test_code=test_code,
                    filename=filename,
                    latency_threshold_ms=plan.nfr_latency_threshold_ms,
                    project_files=project_files,
                    require_category_marker=True,
                )
                agent_reports["performance"] = perf_rep
                existing_ids = {t.test_id for t in all_test_results}
                for tr in perf_rep.test_results:
                    if tr.test_id not in existing_ids:
                        all_test_results.append(tr)
            except Exception as exc:
                logger.error("PerformanceTestAgent execution failed: %s", exc, exc_info=True)
                err_result = TestResult(
                    test_id=f"perf-err-{uuid.uuid4().hex[:8]}",
                    name="performance_agent_execution",
                    status=TestResultStatus.ERROR,
                    error_message=f"PerformanceTestAgent encountered an unhandled error: {exc}",
                    test_type=TestType.PERFORMANCE,
                )
                all_test_results.append(err_result)
                agent_reports["performance"] = PerformanceTestReport(
                    agent_id=self.performance_agent.AGENT_ID,
                    metrics=PerformanceMetrics(
                        sample_size=0,
                        duration_ms=0.0,
                        mean_latency_ms=0.0,
                        latency_p50_ms=0.0,
                        latency_p95_ms=0.0,
                        latency_p99_ms=0.0,
                        max_latency_ms=0.0,
                        throughput_rps=0.0,
                        threshold_latency_ms=plan.nfr_latency_threshold_ms,
                        is_breached=True,
                    ),
                    bottlenecks_detected=[f"Agent execution error: {exc}"],
                    test_results=[err_result],
                    status="ERROR",
                )

        # Calculate strict aggregated overall status
        # NOT_EXECUTED is a valid neutral state (no test oracle supplied for that
        # category), and must not block the verdict when other categories genuinely
        # passed.  If ALL agents are NOT_EXECUTED the overall is BLOCKED because
        # no real testing occurred.
        agent_statuses = [r.status for r in agent_reports.values()]
        if not agent_statuses:
            overall_status = "BLOCKED"
        elif any(s == "ERROR" for s in agent_statuses):
            overall_status = "ERROR"
        elif any(s == "FAILED" for s in agent_statuses):
            overall_status = "FAILED"
        elif any(s in ("PENDING", "BLOCKED", "NOT_EXECUTED") for s in agent_statuses):
            overall_status = "BLOCKED"
        elif all(s == "PASSED" for s in agent_statuses) and len(all_test_results) > 0:
            overall_status = "PASSED"
        else:
            overall_status = "FAILED"

        total_duration_ms = sum(
            getattr(r, "duration_ms", 0.0) if hasattr(r, "duration_ms")
            else (r.metrics.duration_ms if hasattr(r, "metrics") and r.metrics else 0.0)
            for r in agent_reports.values()
        )

        return {
            "overall_status": overall_status,
            "test_results": all_test_results,
            "agent_reports": agent_reports,
            "plan_id": plan.plan_id,
            "duration_ms": round(total_duration_ms, 2),
        }
