from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.logging import logger
from app.schemas.common import ProgrammingLanguage, TestResultStatus, TestType, VerificationStatus
from app.schemas.defect_report import DefectReport
from app.schemas.test_result import TestResult
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.docker_runner import DockerTestRunner, SandboxExecutionResult


class VerificationWorkflowState(TypedDict, total=False):
    """State object for the LangGraph verification pipeline."""

    submission_id: str
    run_id: str
    source_code: str
    language: str
    filename: Optional[str]
    requirement_ids: Optional[List[str]]
    trusted_test_cases: Optional[str]
    timeout_seconds: Optional[int]

    # Flow evaluation flags
    is_supported: bool
    error_message: Optional[str]

    # Execution outcomes
    status: str
    test_results: List[TestResult]
    defect_reports: List[DefectReport]
    telemetry: Dict[str, Any]
    stdout: str
    stderr: str
    duration_ms: float



def validate_submission_node(state: VerificationWorkflowState) -> Dict[str, Any]:
    """Node 1: Validates that the submitted code belongs to a supported language for real execution."""
    language = (state.get("language") or "").lower()
    source_code = state.get("source_code") or ""

    if not source_code.strip():
        logger.warning("Empty source code submitted to verification workflow: run=%s", state.get("run_id"))
        return {
            "is_supported": False,
            "status": VerificationStatus.ERROR.value,
            "error_message": "Submitted code cannot be empty.",
            "test_results": [],
            "telemetry": {"stage": "validation", "error": "empty_code"},
        }

    if language != ProgrammingLanguage.PYTHON.value and language != "python":
        logger.info(
            "Non-Python language '%s' submitted. Phase 2B Milestone 1 real runner supports Python.",
            language,
        )
        return {
            "is_supported": False,
            "status": VerificationStatus.PENDING.value,
            "error_message": f"Real containerized execution for language '{language}' is scheduled for subsequent milestones.",
            "test_results": [],
            "telemetry": {"stage": "validation", "unsupported_language": language},
        }

    return {"is_supported": True, "error_message": None}


def check_docker_node(state: VerificationWorkflowState) -> Dict[str, Any]:
    """Node 2: Verifies host Docker engine and sandbox runner readiness with fail-closed security."""
    if not state.get("is_supported", False):
        return {}

    runner = DockerTestRunner()
    docker_ok, docker_msg = runner.check_docker_available()
    if not docker_ok:
        logger.error("Docker engine check failed for run=%s: %s", state.get("run_id"), docker_msg)
        return {
            "status": VerificationStatus.ERROR.value,
            "error_message": f"Docker isolation unavailable: {docker_msg}",
            "test_results": [],
            "telemetry": {"docker_available": False, "reason": docker_msg},
        }

    image_ok, image_msg = runner.ensure_runner_image()
    if not image_ok:
        logger.error("Runner image check failed for run=%s: %s", state.get("run_id"), image_msg)
        return {
            "status": VerificationStatus.ERROR.value,
            "error_message": f"Sandbox runner image unavailable: {image_msg}",
            "test_results": [],
            "telemetry": {"image_ready": False, "reason": image_msg},
        }

    return {"telemetry": {"docker_ready": True}}


async def execute_tests_node(state: VerificationWorkflowState) -> Dict[str, Any]:
    """Node 3: Executes tests inside the short-lived, unprivileged Docker container."""
    if not state.get("is_supported", False) or state.get("status") == VerificationStatus.ERROR.value:
        return {}

    source_code = state.get("source_code", "")
    trusted_test_cases = state.get("trusted_test_cases")
    filename = state.get("filename")
    timeout = state.get("timeout_seconds")

    runner = DockerTestRunner()
    exec_result: SandboxExecutionResult = await runner.execute_verification(
        source_code=source_code,
        trusted_test_cases=trusted_test_cases,
        filename=filename,
        timeout_seconds=timeout,
    )

    # Determine final verification run status
    # If no oracle, retain PENDING or SKIPPED
    if exec_result.no_oracle:
        final_status = VerificationStatus.PENDING.value
    elif exec_result.is_timeout:
        final_status = VerificationStatus.ERROR.value
    elif exec_result.status == TestResultStatus.PASSED.value:
        final_status = VerificationStatus.PASSED.value
    elif exec_result.status == TestResultStatus.FAILED.value:
        final_status = VerificationStatus.FAILED.value
    else:
        final_status = VerificationStatus.ERROR.value

    return {
        "status": final_status,
        "test_results": exec_result.test_results,
        "error_message": exec_result.error_message,
        "stdout": exec_result.stdout,
        "stderr": exec_result.stderr,
        "duration_ms": exec_result.duration_ms,
        "telemetry": {
            **state.get("telemetry", {}),
            **exec_result.telemetry,
            "exit_code": exec_result.exit_code,
            "duration_ms": exec_result.duration_ms,
            "is_timeout": exec_result.is_timeout,
            "no_oracle": exec_result.no_oracle,
        },
    }


def analyze_defects_node(state: VerificationWorkflowState) -> Dict[str, Any]:
    """Node 4: Synthesizes structured defect reports from real pytest failures."""
    status_str = state.get("status", "")
    test_results = state.get("test_results", [])
    run_id = state.get("run_id", "unknown_run")
    submission_id = state.get("submission_id", "unknown_submission")
    filename = state.get("filename")
    telemetry = state.get("telemetry", {})
    error_msg = state.get("error_message")
    req_ids = state.get("requirement_ids")
    req_id = req_ids[0] if req_ids else None

    defect_service = DefectAnalysisService()
    reports = defect_service.analyze_test_results(
        run_id=run_id,
        submission_id=submission_id,
        status=status_str,
        test_results=test_results,
        affected_filename=filename,
        execution_telemetry=telemetry,
        error_message=error_msg,
        requirement_id=req_id,
    )
    return {"defect_reports": reports}


def should_execute_tests(state: VerificationWorkflowState) -> str:
    """Conditional router determining whether to proceed to sandbox execution."""
    if not state.get("is_supported", False):
        return END
    if state.get("status") == VerificationStatus.ERROR.value:
        return END
    return "execute_tests"


def build_verification_graph():
    """Constructs and compiles the LangGraph verification workflow."""
    workflow = StateGraph(VerificationWorkflowState)

    # Add workflow nodes
    workflow.add_node("validate_submission", validate_submission_node)
    workflow.add_node("check_docker", check_docker_node)
    workflow.add_node("execute_tests", execute_tests_node)
    workflow.add_node("analyze_defects", analyze_defects_node)

    # Define edges and conditional transitions
    workflow.add_edge(START, "validate_submission")
    workflow.add_edge("validate_submission", "check_docker")
    workflow.add_conditional_edges(
        "check_docker",
        should_execute_tests,
        {
            "execute_tests": "execute_tests",
            END: END,
        },
    )
    workflow.add_edge("execute_tests", "analyze_defects")
    workflow.add_edge("analyze_defects", END)

    return workflow.compile()


# Precompiled singleton graph instance
verification_pipeline = build_verification_graph()

