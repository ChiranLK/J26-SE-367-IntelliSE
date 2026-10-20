from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.logging import logger
from app.schemas.common import ProgrammingLanguage, TestResultStatus, TestType, VerificationStatus
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import FeedbackIteration, TechnicalFeedbackPayload
from app.schemas.test_result import TestResult
from app.services.agent_testing_service import TestCoordinationService
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.defect_reconciliation_service import DefectReconciliationService
from app.services.docker_runner import DockerTestRunner, SandboxExecutionResult
from app.services.feedback_service import TechnicalFeedbackService
from app.services.llm_defect_reasoning_agent import LLMDefectReasoningAgent
from app.schemas.llm_defect_reasoning import LLMReasoningInput


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
    requested_test_types: Optional[List[str]]

    # Research evaluation mode: "DETERMINISTIC_ONLY" or "LLM_ASSISTED"
    evaluation_mode: Optional[str]
    llm_defect_hypotheses: Optional[List[Dict[str, Any]]]
    ai_contribution: Optional[Dict[str, Any]]

    # Flow evaluation flags
    is_supported: bool
    error_message: Optional[str]

    # Execution outcomes
    status: str
    test_results: List[TestResult]
    defect_reports: List[DefectReport]
    technical_feedback: Optional[TechnicalFeedbackPayload]
    feedback_iterations: List[FeedbackIteration]
    agent_reports: Optional[Dict[str, Any]]
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
    """Node 3: Executes tests inside the short-lived Docker sandbox via specialized testing agents."""
    if not state.get("is_supported", False) or state.get("status") == VerificationStatus.ERROR.value:
        return {}

    source_code = state.get("source_code", "")
    trusted_test_cases = state.get("trusted_test_cases")
    filename = state.get("filename") or "solution.py"
    timeout = state.get("timeout_seconds") or 25
    run_id = state.get("run_id", "run-default")

    # Respect requested_test_types; default to ["unit"] for unit-only backwards compatibility
    raw_requested = state.get("requested_test_types") or ["unit"]
    normalized_agents = []
    for t in raw_requested:
        val = t.value if hasattr(t, "value") else str(t)
        normalized_agents.append(val.lower())
    if not normalized_agents:
        normalized_agents = ["unit"]

    runner = DockerTestRunner()
    coordination_service = TestCoordinationService(runner=runner)

    plan = coordination_service.create_coordination_plan(
        run_id=run_id,
        source_code=source_code,
        requested_test_types=normalized_agents,
    )

    coord_result = await coordination_service.execute_coordinated_verification(
        plan=plan,
        source_code=source_code,
        test_code=trusted_test_cases or "",
        filename=filename,
        timeout_seconds=timeout,
    )

    raw_overall = coord_result.get("overall_status", "FAILED")
    if raw_overall == "PASSED":
        final_status = VerificationStatus.PASSED.value
    elif raw_overall == "PENDING":
        final_status = VerificationStatus.PENDING.value
    elif raw_overall == "ERROR":
        final_status = VerificationStatus.ERROR.value
    else:
        final_status = VerificationStatus.FAILED.value

    # Serialize agent reports for telemetry and persistence
    agent_reports_serialized = {}
    for agent_key, rep in coord_result.get("agent_reports", {}).items():
        if hasattr(rep, "model_dump"):
            agent_reports_serialized[agent_key] = rep.model_dump()
        elif hasattr(rep, "dict"):
            agent_reports_serialized[agent_key] = rep.dict()
        else:
            agent_reports_serialized[agent_key] = rep

    test_results = coord_result.get("test_results", [])
    duration_ms = coord_result.get("duration_ms", 0.0)

    # Capture diagnostic error message if any agent produced an error
    error_msg = state.get("error_message")
    if not error_msg and final_status == VerificationStatus.ERROR.value:
        for r in coord_result.get("agent_reports", {}).values():
            if getattr(r, "status", None) == "ERROR":
                for tr in getattr(r, "test_results", []):
                    if tr.status in (TestResultStatus.ERROR, TestResultStatus.TIMEOUT) and tr.error_message:
                        error_msg = tr.error_message
                        break

    agent_telemetry = {
        "coordination_plan_id": plan.plan_id,
        "assigned_agents": plan.assigned_agents,
        "agent_reports": agent_reports_serialized,
        "total_coordinated_tests": len(test_results),
        "duration_ms": duration_ms,
    }

    return {
        "status": final_status,
        "test_results": test_results,
        "agent_reports": agent_reports_serialized,
        "error_message": error_msg,
        "stdout": "",
        "stderr": "",
        "duration_ms": duration_ms,
        "telemetry": {
            **state.get("telemetry", {}),
            **agent_telemetry,
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
        source_code=state.get("source_code"),
    )
    updates: Dict[str, Any] = {"defect_reports": reports}
    if reports and status_str == VerificationStatus.PASSED.value:
        updates["status"] = VerificationStatus.FAILED.value
        updates["telemetry"] = {**telemetry, "status_overridden_by_security_analysis": True}

    return updates


async def reason_defects_with_llm_node(state: VerificationWorkflowState) -> Dict[str, Any]:
    """Node 4.5: Evaluates defects with LLMDefectReasoningAgent and reconciles findings."""
    eval_mode = (state.get("evaluation_mode") or "LLM_ASSISTED").upper()
    source_code = state.get("source_code") or ""
    filename = state.get("filename") or "solution.py"
    defect_reports = state.get("defect_reports") or []
    test_results = state.get("test_results") or []
    telemetry = state.get("telemetry") or {}
    status_str = state.get("status", "")

    reconciliation_svc = DefectReconciliationService()

    # If verification PASSED or ERROR due to infrastructure, or DETERMINISTIC_ONLY mode requested
    if eval_mode == "DETERMINISTIC_ONLY" or status_str in (VerificationStatus.PASSED.value, VerificationStatus.ERROR.value):
        reconciled, ai_telemetry, guidance = reconciliation_svc.reconcile(
            deterministic_defects=defect_reports,
            llm_hypothesis=None,
            candidate_code=source_code,
            evaluation_mode=eval_mode,
            telemetry=telemetry,
        )
        return {
            "defect_reports": reconciled,
            "telemetry": {**telemetry, "ai_contribution": ai_telemetry.model_dump()},
            "ai_contribution": ai_telemetry.model_dump(),
        }

    # Gather permitted evidence only
    failure_msgs = []
    stack_traces = []
    catalog = {}
    ev_idx = 0

    for tr in test_results:
        status_val = tr.status.value if hasattr(tr.status, "value") else str(tr.status)
        if status_val in ("FAILED", "ERROR", "TIMEOUT"):
            ev_id = f"ev_test_{ev_idx}"
            ev_idx += 1
            msg = tr.error_message or f"Test {tr.name} failed"
            failure_msgs.append(f"{tr.name}: {msg}")
            catalog[ev_id] = f"Test failure in {tr.name}: {msg}"
            if tr.stack_trace:
                stack_traces.append(tr.stack_trace)

    sec_findings = []
    for d in defect_reports:
        if d.cwe_id:
            sec_ev_id = f"ev_sec_{ev_idx}"
            ev_idx += 1
            sec_desc = f"{d.cwe_id} ({d.title}) line {d.line_number}"
            catalog[sec_ev_id] = sec_desc
            sec_findings.append({
                "cwe_id": d.cwe_id,
                "title": d.title,
                "line_number": d.line_number,
                "severity": d.severity.value if hasattr(d.severity, "value") else str(d.severity),
            })

    reasoning_input = LLMReasoningInput(
        candidate_source_code=source_code,
        filename=filename,
        unit_test_failure_messages=failure_msgs,
        integration_test_failure_messages=[],
        performance_observations=telemetry.get("performance_metrics"),
        ast_security_findings=sec_findings,
        semantic_drift_evidence=telemetry.get("semantic_drift"),
        relevant_stack_traces=stack_traces,
        evidence_catalog=catalog,
    )

    reasoning_agent = LLMDefectReasoningAgent()
    hypothesis = await reasoning_agent.reason_defects(reasoning_input)

    reconciled, ai_telemetry, guidance = reconciliation_svc.reconcile(
        deterministic_defects=defect_reports,
        llm_hypothesis=hypothesis,
        candidate_code=source_code,
        evaluation_mode=eval_mode,
        telemetry=telemetry,
    )

    return {
        "defect_reports": reconciled,
        "llm_defect_hypotheses": [hypothesis.model_dump()],
        "telemetry": {**telemetry, "ai_contribution": ai_telemetry.model_dump()},
        "ai_contribution": ai_telemetry.model_dump(),
    }


def prepare_technical_feedback_node(state: VerificationWorkflowState) -> Dict[str, Any]:
    """Node 5: Prepares structured technical feedback package for Component 3 if eligible."""
    status_str = state.get("status", "")
    defect_reports = state.get("defect_reports", [])
    run_id = state.get("run_id", "unknown_run")
    submission_id = state.get("submission_id", "unknown_submission")
    test_results = state.get("test_results", [])
    telemetry = state.get("telemetry", {})
    error_msg = state.get("error_message")
    filename = state.get("filename")
    existing_iterations = state.get("feedback_iterations") or []

    try:
        v_status = VerificationStatus(status_str)
    except ValueError:
        v_status = VerificationStatus.ERROR

    from app.schemas.verification import VerificationRunResponse
    from app.schemas.submission import CodeSubmissionResponse

    run_obj = VerificationRunResponse(
        id=run_id,
        submission_id=submission_id,
        status=v_status,
        test_results=test_results,
        defect_reports=defect_reports,
        feedback_iterations=list(existing_iterations),
        execution_telemetry=telemetry,
        error_message=error_msg,
    )
    submission_obj = CodeSubmissionResponse(
        id=submission_id,
        code=state.get("source_code", ""),
        language=ProgrammingLanguage(state.get("language", "python")),
        filename=filename,
    )

    feedback_service = TechnicalFeedbackService()
    is_eligible, _ = feedback_service.check_eligibility(run_obj)
    if not is_eligible:
        return {
            "technical_feedback": None,
            "feedback_iterations": existing_iterations,
        }

    payload = feedback_service.build_feedback_payload(run_obj, submission_obj)
    updated_run, iteration, created = feedback_service.record_feedback_iteration(run_obj, payload)

    return {
        "technical_feedback": payload,
        "feedback_iterations": updated_run.feedback_iterations,
    }


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
    workflow.add_node("reason_defects_with_llm", reason_defects_with_llm_node)
    workflow.add_node("prepare_technical_feedback", prepare_technical_feedback_node)

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
    workflow.add_edge("analyze_defects", "reason_defects_with_llm")
    workflow.add_edge("reason_defects_with_llm", "prepare_technical_feedback")
    workflow.add_edge("prepare_technical_feedback", END)

    return workflow.compile()


# Precompiled singleton graph instance
verification_pipeline = build_verification_graph()


