"""
Executable Baseline Evaluators for INTELISE Component 4 Benchmark (Proposal Section 3.8).
Provides empirical, executable baselines evaluated against frozen benchmark scenarios:
1. ConventionalCiBaselineEvaluator: Standard un-specialized CI runner (raw pytest in Docker or isolated execution).
2. StaticAnalysisBaselineEvaluator: Pure AST static security analysis without dynamic execution.

Enhancements (Phase 3B.3):
- Records granular scenario-level observations (status, exit code, timeout, duration, sanitized evidence, provenance).
- Separates test execution from ground-truth scoring: baseline execution NEVER accesses scenario_group or has_defect.
- Grounds observations in genuine runner output or dynamic test execution.
"""
import importlib.util
import re
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.benchmark.dataset import PILOT_BENCHMARK_SCENARIOS
from app.benchmark.models import BenchmarkScenario, BenchmarkScenarioGroup
from app.schemas.common import DefectCategory, TestResultStatus
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.docker_runner import DockerTestRunner, SandboxExecutionResult


class ScenarioBaselineRecord(BaseModel):
    """Detailed observation recorded for a single scenario under a baseline evaluator."""
    scenario_id: str
    detected_has_defect: bool
    execution_status: str
    container_exit_code: int = 0
    timeout: bool = False
    duration_ms: float = 0.0
    sanitized_evidence: str = ""
    findings_count: int = 0
    provenance: str = "EMPIRICAL_EXECUTION"

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class BaselineExecutionResult(BaseModel):
    """Metrics achieved by an executable baseline on frozen benchmark scenarios."""
    baseline_name: str
    total_scenarios: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    detection_breakdown: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)
    scenario_records: List[ScenarioBaselineRecord] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def _sanitize_evidence(text: str, max_length: int = 500) -> str:
    """Sanitizes sensitive patterns and bounds evidence snippet length."""
    if not text:
        return ""
    # Redact common credentials/paths
    redacted = re.sub(r"(token|secret|password|key)[\s:=]+([^\s,;]+)", r"\1=[REDACTED]", text, flags=re.IGNORECASE)
    cleaned = redacted.replace("\r", " ").strip()
    return cleaned[:max_length]


class ConventionalCiBaselineEvaluator:
    """
    Baseline 1: Conventional CI/CD Pipeline (Raw Pytest Runner).
    Simulates standard CI pipeline execution (e.g., GitHub Actions / Jenkins running pytest).
    Characteristics:
    - Runs pytest inside the Docker container or local dynamic sandbox without specialized testing agents.
    - Has no latency SLA threshold profiling (misses performance bottlenecks).
    - Has no AST semantic drift detector (misses weakened assertions).
    - Has no multi-agent taxonomy classification.
    - Captures per-scenario observations directly from execution without ground-truth access.
    """

    def __init__(self, use_real_docker: bool = False, runner: Optional[DockerTestRunner] = None):
        self.use_real_docker = use_real_docker
        self.runner = runner or (DockerTestRunner() if use_real_docker else None)

    def _execute_in_process_sandbox(self, source_code: str, test_code: str, filename: str) -> Tuple[bool, int, bool, float, str]:
        """
        Executes test code against source code dynamically in a temporary namespace.
        NEVER inspects any scenario labels or expected outcomes.
        Returns: (pytest_failed, exit_code, is_timeout, duration_ms, sanitized_evidence)
        """
        t0 = time.perf_counter()
        mod_name = f"sandbox_baseline_{abs(hash(source_code)) % 10000000}"

        spec = importlib.util.spec_from_loader(mod_name, loader=None)
        if spec is None:
            return True, 1, False, 1.0, "Could not initialize module spec"
        mod = importlib.util.module_from_spec(spec)

        prev_mod = sys.modules.get(mod_name)
        prev_solution = sys.modules.get("solution")
        sys.modules[mod_name] = mod
        sys.modules["solution"] = mod

        try:
            exec(source_code, mod.__dict__)
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000.0
            return True, 1, False, dur, _sanitize_evidence(f"CompilationError: {exc}")
        finally:
            pass

        test_globals: Dict[str, Any] = {
            "solution": mod,
            **mod.__dict__,
        }

        try:
            exec(test_code, test_globals)
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000.0
            if prev_mod is not None:
                sys.modules[mod_name] = prev_mod
            else:
                sys.modules.pop(mod_name, None)
            if prev_solution is not None:
                sys.modules["solution"] = prev_solution
            else:
                sys.modules.pop("solution", None)
            return True, 1, False, dur, _sanitize_evidence(f"CollectionError: {exc}")

        test_funcs = [v for k, v in test_globals.items() if k.startswith("test_") and callable(v)]
        pytest_failed = False
        evidence = "All tests passed"
        exit_code = 0

        for tf in test_funcs:
            try:
                tf()
            except AssertionError as exc:
                pytest_failed = True
                exit_code = 1
                evidence = _sanitize_evidence(f"AssertionError in {tf.__name__}: {exc}")
                break
            except Exception as exc:
                pytest_failed = True
                exit_code = 1
                evidence = _sanitize_evidence(f"{type(exc).__name__} in {tf.__name__}: {exc}")
                break

        dur = (time.perf_counter() - t0) * 1000.0

        if prev_mod is not None:
            sys.modules[mod_name] = prev_mod
        else:
            sys.modules.pop(mod_name, None)
        if prev_solution is not None:
            sys.modules["solution"] = prev_solution
        else:
            sys.modules.pop("solution", None)

        return pytest_failed, exit_code, False, dur, evidence

    async def evaluate(self, scenarios: Optional[List[BenchmarkScenario]] = None) -> BaselineExecutionResult:
        dataset = PILOT_BENCHMARK_SCENARIOS if scenarios is None else scenarios

        tp = 0
        fp = 0
        tn = 0
        fn = 0
        breakdown: Dict[str, Dict[str, int]] = {
            "clean_control": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "functional_bug": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "security_vulnerability": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "performance_bottleneck": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "regression": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "non_convergent_by_design": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "semantic_drift": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "integration_defect": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
        }

        scenario_records: List[ScenarioBaselineRecord] = []

        # =====================================================================
        # PHASE 1: EXECUTION (Zero Ground-Truth Access)
        # =====================================================================
        raw_observations = []
        for sc in dataset:
            if self.use_real_docker and self.runner:
                exec_res: SandboxExecutionResult = await self.runner.execute_verification(
                    source_code=sc.module_code,
                    trusted_test_cases=sc.test_code,
                    filename=sc.filename,
                    timeout_seconds=15,
                )
                failed = exec_res.status == TestResultStatus.FAILED.value or any(
                    t.status in (TestResultStatus.FAILED, TestResultStatus.ERROR, TestResultStatus.TIMEOUT)
                    for t in exec_res.test_results
                )
                is_timeout = exec_res.status == TestResultStatus.TIMEOUT.value
                dur = exec_res.duration_ms
                first_err = next((t.error_message for t in exec_res.test_results if t.error_message), "")
                evidence = _sanitize_evidence(first_err or ("Tests failed" if failed else "All tests passed"))
                exit_code = 1 if failed else 0
                status_str = "FAILED" if failed else "PASSED"
            else:
                failed, exit_code, is_timeout, dur, evidence = self._execute_in_process_sandbox(
                    source_code=sc.module_code,
                    test_code=sc.test_code,
                    filename=sc.filename,
                )
                status_str = "FAILED" if failed else "PASSED"

            raw_observations.append({
                "scenario_id": sc.scenario_id,
                "detected_has_defect": failed,
                "execution_status": status_str,
                "container_exit_code": exit_code,
                "timeout": is_timeout,
                "duration_ms": round(dur, 2),
                "sanitized_evidence": evidence,
                "provenance": "EMPIRICAL_EXECUTION",
            })

        # =====================================================================
        # PHASE 2: METRIC SCORING AGAINST FROZEN GROUND TRUTH
        # =====================================================================
        for sc, obs in zip(dataset, raw_observations):
            group_key = sc.scenario_group.value
            pytest_failed = obs["detected_has_defect"]

            rec = ScenarioBaselineRecord(**obs)
            scenario_records.append(rec)

            if not sc.has_defect:
                if not pytest_failed:
                    tn += 1
                    breakdown[group_key]["correct"] += 1
                else:
                    fp += 1
                    breakdown[group_key]["incorrect"] += 1
            else:
                if pytest_failed:
                    tp += 1
                    breakdown[group_key]["detected"] += 1
                else:
                    fn += 1
                    breakdown[group_key]["missed"] += 1

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 1.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        return BaselineExecutionResult(
            baseline_name="Conventional CI/CD (Single Non-Specialized Agent)",
            total_scenarios=len(dataset),
            true_positives=tp,
            false_positives=fp,
            true_negatives=tn,
            false_negatives=fn,
            precision=round(precision, 3),
            recall=round(recall, 3),
            f1_score=round(f1, 3),
            detection_breakdown=breakdown,
            limitations=[
                "Cannot detect performance SLA threshold breaches (0% recall on performance bottlenecks).",
                "Cannot detect test suite semantic drift or superficial convergence.",
                "Binary pass/fail exit code without defect localization or taxonomy categorization.",
            ],
            scenario_records=scenario_records,
        )


class StaticAnalysisBaselineEvaluator:
    """
    Baseline 2: Static Analysis Only (AST-Based Code Scanner).
    Evaluates pure static code analysis without containerized dynamic test execution.
    Characteristics:
    - Analyzes AST syntax of module_code for known defect patterns (CWE-78, CWE-95, CWE-22, CWE-798).
    - Has no runtime execution: cannot detect dynamic functional bugs or off-by-one errors.
    - Has no performance profiling capability.
    - Captures per-scenario observations directly from AST inspection without ground-truth access.
    """

    def __init__(self):
        self.defect_service = DefectAnalysisService()

    def evaluate(self, scenarios: Optional[List[BenchmarkScenario]] = None) -> BaselineExecutionResult:
        dataset = PILOT_BENCHMARK_SCENARIOS if scenarios is None else scenarios

        tp = 0
        fp = 0
        tn = 0
        fn = 0
        breakdown: Dict[str, Dict[str, int]] = {
            "clean_control": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "functional_bug": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "security_vulnerability": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "performance_bottleneck": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "regression": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "non_convergent_by_design": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "semantic_drift": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
            "integration_defect": {"correct": 0, "incorrect": 0, "detected": 0, "missed": 0},
        }

        scenario_records: List[ScenarioBaselineRecord] = []

        # =====================================================================
        # PHASE 1: EXECUTION (Zero Ground-Truth Access)
        # =====================================================================
        raw_observations = []
        for sc in dataset:
            t0 = time.perf_counter()
            findings = self.defect_service.inspect_static_security_vulnerabilities(sc.module_code)
            dur = (time.perf_counter() - t0) * 1000.0
            static_flagged = len(findings) > 0
            evidence = _sanitize_evidence(
                f"Flagged {len(findings)} vulnerability pattern(s): {[f.get('cwe_id') for f in findings if f.get('cwe_id')]}"
                if static_flagged else "No AST security patterns detected"
            )

            raw_observations.append({
                "scenario_id": sc.scenario_id,
                "detected_has_defect": static_flagged,
                "execution_status": "DEFECT_DETECTED" if static_flagged else "CLEAN",
                "container_exit_code": 1 if static_flagged else 0,
                "timeout": False,
                "duration_ms": round(dur, 2),
                "sanitized_evidence": evidence,
                "findings_count": len(findings),
                "provenance": "EMPIRICAL_EXECUTION",
            })

        # =====================================================================
        # PHASE 2: METRIC SCORING AGAINST FROZEN GROUND TRUTH
        # =====================================================================
        for sc, obs in zip(dataset, raw_observations):
            group_key = sc.scenario_group.value
            static_flagged = obs["detected_has_defect"]

            rec = ScenarioBaselineRecord(**obs)
            scenario_records.append(rec)

            if not sc.has_defect:
                if not static_flagged:
                    tn += 1
                    breakdown[group_key]["correct"] += 1
                else:
                    fp += 1
                    breakdown[group_key]["incorrect"] += 1
            else:
                if static_flagged:
                    tp += 1
                    breakdown[group_key]["detected"] += 1
                else:
                    fn += 1
                    breakdown[group_key]["missed"] += 1

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 1.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        return BaselineExecutionResult(
            baseline_name="Static Analysis Only (AST Scanner)",
            total_scenarios=len(dataset),
            true_positives=tp,
            false_positives=fp,
            true_negatives=tn,
            false_negatives=fn,
            precision=round(precision, 3),
            recall=round(recall, 3),
            f1_score=round(f1, 3),
            detection_breakdown=breakdown,
            limitations=[
                "High precision on static security patterns, but completely blind to runtime functional defects.",
                "Cannot detect dynamic off-by-one errors, infinite loops, or computational regressions.",
                "Cannot measure dynamic runtime latency or workload throughput.",
            ],
            scenario_records=scenario_records,
        )
